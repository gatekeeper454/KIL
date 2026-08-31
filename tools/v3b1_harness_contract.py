"""Pure closed contracts for sanitized V3B-1 integration transcripts."""

from __future__ import annotations

from base64 import urlsafe_b64decode
from dataclasses import dataclass
import errno as errno_module
import http.client
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Mapping


SCHEMA_VERSION = "kil.v3b1-integration-contract.v1"
DRIVER_TOPOLOGY_SCHEMA_VERSION = "kil.v3b1-integration-contract.v2"
_HEX = re.compile(r"^[a-f0-9]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_CASE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")
_ENVIRONMENT_VALUE = re.compile(r"^[A-Z_][A-Z0-9_]*=.*$")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"
)
_GITHUB_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,})"
    r"(?![A-Za-z0-9_])"
)
_AWS_ACCESS_KEY = re.compile(
    r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"
)
_BEARER_TOKEN = re.compile(r"(?i)(?:^|\s)bearer\s+\S+")
_COMPACT_JWS_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    r"(?![A-Za-z0-9_-])"
)
_TRACK_SLUG = (
    r"(?:credential-policy-baseline|signed-state-only|signed-plus-local-reduce)"
)
_LEGACY_V1_CONTAINER_NAME = re.compile(
    rf"^kil-v3b1-(?:authz|target|envoy|validate)-{_TRACK_SLUG}-[a-f0-9]{{12}}$"
)
_DRIVER_TOPOLOGY_CONTAINER_NAME = re.compile(
    rf"^kil-v3b1-(?:authz|target|envoy|driver|validate)-{_TRACK_SLUG}-[a-f0-9]{{12}}$"
)
_LEGACY_V1_NETWORK_NAME = re.compile(
    rf"^kil-v3b1-network-{_TRACK_SLUG}-[a-f0-9]{{12}}$"
)
_SEGMENT_NETWORK_NAME = re.compile(
    rf"^kil-v3b1-(?:frontend|backend)-{_TRACK_SLUG}-[a-f0-9]{{12}}$"
)
_INVENTORY_NAME_PATTERNS = {
    SCHEMA_VERSION: {
        "container": _LEGACY_V1_CONTAINER_NAME,
        "network": _LEGACY_V1_NETWORK_NAME,
    },
    DRIVER_TOPOLOGY_SCHEMA_VERSION: {
        "container": _DRIVER_TOPOLOGY_CONTAINER_NAME,
        "network": _SEGMENT_NETWORK_NAME,
    },
}
_MAX_FIXTURE_BYTES = 1_000_000
_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_TRACKS = {
    "credential_policy_baseline",
    "signed_state_only",
    "signed_plus_local_reduce",
}
_SOURCES = {"authz_decisions", "target_markers", "envoy_access"}
_SOURCE_ROLES = {
    "authz_decisions": "authz",
    "target_markers": "target",
    "envoy_access": "envoy",
}
_STATUSES = {"copied", "missing", "copy_error", "malformed"}
_EXCEPTION_CLASSES = {
    "OSError",
    "TimeoutError",
    "ConnectionError",
    "BrokenPipeError",
    "ConnectionAbortedError",
    "ConnectionRefusedError",
    "ConnectionResetError",
}
_FAILURE_STAGES = {"request_send", "response_headers", "response_body"}
_DRIVER_LIFECYCLE_EVENTS = {
    "driver_start_intent",
    "driver_start_complete",
    "driver_readiness_complete",
    "driver_readiness_set_complete",
    "readiness_cancel_intent",
    "readiness_cancel_complete",
    "readiness_diagnostic_complete",
}
_FORBIDDEN_KEYS = {
    "authorization",
    "credential",
    "credentials",
    "docker_host",
    "docker_config",
    "env",
    "environ",
    "environment",
    "exception_message",
    "jws",
    "message",
    "manifest_path",
    "password",
    "private_key",
    "private_path",
    "q_state",
    "raw_exception_message",
    "raw_message",
    "refresh_token",
    "secret",
    "signed_state",
    "socket_path",
    "stderr",
    "stdout",
    "token",
}


class ContractError(ValueError):
    """Raised when a harness transcript is not closed and public-safe."""


def _require_fields(value: object, expected: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != expected:
        raise ContractError(f"{label} fields are not closed")
    return value


def _require_object_id(value: object) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ContractError("Docker object ID must be exactly 64 lowercase hex characters")
    return value


def _require_name(value: object, label: str = "Docker object name") -> str:
    if (
        type(value) is not str
        or len(value.encode("utf-8")) > 128
        or _NAME.fullmatch(value) is None
    ):
        raise ContractError(f"{label} is invalid or exceeds its bound")
    return value


def _require_schema_version(value: object) -> str:
    if type(value) is not str or value not in _INVENTORY_NAME_PATTERNS:
        raise ContractError("integration transcript schema is invalid")
    return value


def _require_inventory_name(
    value: object,
    kind: str,
    schema_version: str,
) -> str:
    name = _require_name(value)
    schema = _require_schema_version(schema_version)
    if kind not in {"container", "network"}:
        raise ContractError("Docker inventory kind is invalid")
    pattern = _INVENTORY_NAME_PATTERNS[schema][kind]
    if pattern.fullmatch(name) is None:
        raise ContractError(f"Docker {kind} name is outside the fixed KIL pattern")
    return name


def _require_sha256(value: object) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ContractError("source SHA-256 is invalid")
    return value


def _validate_byte_observation(
    byte_count: object,
    digest: object,
    label: str,
) -> bool:
    present = byte_count is not None or digest is not None
    if not present:
        return False
    if (
        type(byte_count) is not int
        or byte_count < 0
        or byte_count > _MAX_SOURCE_BYTES
    ):
        raise ContractError(f"{label} byte count is invalid")
    _require_sha256(digest)
    return True


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _looks_like_compact_jws(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 3 or any(
        not part or re.fullmatch(r"[A-Za-z0-9_-]+", part) is None
        for part in parts
    ):
        return False
    try:
        header = urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4))
        decoded = json.loads(header)
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(decoded, dict) and bool({"alg", "typ"}.intersection(decoded))


def _contains_compact_jws(value: str) -> bool:
    return any(
        _looks_like_compact_jws(match.group(0))
        for match in _COMPACT_JWS_CANDIDATE.finditer(value)
    )


def _reject_sensitive_material(value: object) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ContractError("transcript keys must be strings")
            normalized = key.lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise ContractError("transcript contains a forbidden sensitive field")
            _reject_sensitive_material(key)
            _reject_sensitive_material(item)
        return
    if type(value) in (list, tuple):
        for item in value:
            _reject_sensitive_material(item)
        return
    if type(value) is not str:
        return
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise ContractError("transcript contains invalid Unicode") from error
    if (
        value.startswith(("/", "~/", "~\\"))
        or _WINDOWS_ABSOLUTE.match(value) is not None
        or "/Users/" in value
        or "/home/" in value
        or "/private/var/folders/" in value
        or "/tmp/" in value
        or "/var/tmp/" in value
        or re.search(r"(?i)[A-Z]:[\\/]Users[\\/]", value) is not None
    ):
        raise ContractError("transcript contains an absolute private path")
    if any(
        _ENVIRONMENT_VALUE.fullmatch(line) is not None
        for line in value.splitlines()
    ):
        raise ContractError("transcript contains environment material")
    if (
        _PRIVATE_KEY_BLOCK.search(value) is not None
        or _GITHUB_TOKEN.search(value) is not None
        or _AWS_ACCESS_KEY.search(value) is not None
        or _BEARER_TOKEN.search(value) is not None
        or _contains_compact_jws(value)
        or "v3b1-lab-credential" in value
    ):
        raise ContractError("transcript contains secret or credential material")


def reject_sensitive_material(value: object) -> None:
    """Reject recursively nested private material with a total public error."""
    try:
        _reject_sensitive_material(value)
    except ContractError:
        raise
    except (AttributeError, TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ContractError("transcript sensitive-material scan failed") from error


def normalize_transport_exception(
    error: BaseException,
) -> tuple[str, int | None, str | None]:
    """Map a transport exception to closed provenance without retaining its text."""
    if isinstance(error, http.client.IncompleteRead):
        exception_class = "ConnectionError"
    elif isinstance(error, http.client.RemoteDisconnected):
        exception_class = "ConnectionResetError"
    elif isinstance(error, http.client.HTTPException):
        exception_class = "ConnectionError"
    elif isinstance(error, BrokenPipeError):
        exception_class = "BrokenPipeError"
    elif isinstance(error, ConnectionAbortedError):
        exception_class = "ConnectionAbortedError"
    elif isinstance(error, ConnectionRefusedError):
        exception_class = "ConnectionRefusedError"
    elif isinstance(error, ConnectionResetError):
        exception_class = "ConnectionResetError"
    elif isinstance(error, TimeoutError):
        exception_class = "TimeoutError"
    elif isinstance(error, ConnectionError):
        exception_class = "ConnectionError"
    elif isinstance(error, OSError):
        exception_class = "OSError"
    else:
        raise ContractError("exception is not an allowlisted transport failure")

    number = error.errno if isinstance(error, OSError) else None
    if type(number) is not int or number not in errno_module.errorcode:
        return exception_class, None, None
    return exception_class, number, errno_module.errorcode[number]


@dataclass(frozen=True, slots=True)
class RequestFailureProvenance:
    stage: str
    exception_class: str
    errno: int | None
    errno_name: str | None
    connect_monotonic_ns: int
    send_monotonic_ns: int
    failure_monotonic_ns: int
    request_bytes_may_have_been_sent: bool
    attempt_count: int
    retry_performed: bool

    def __post_init__(self) -> None:
        if type(self.stage) is not str or self.stage not in _FAILURE_STAGES:
            raise ContractError("request failure stage is invalid")
        if (
            type(self.exception_class) is not str
            or self.exception_class not in _EXCEPTION_CLASSES
        ):
            raise ContractError("request failure exception class is not allowlisted")
        if (self.errno is None) != (self.errno_name is None):
            raise ContractError("request failure errno fields are inconsistent")
        if self.errno is not None:
            if (
                type(self.errno) is not int
                or self.errno < 0
                or type(self.errno_name) is not str
                or errno_module.errorcode.get(self.errno) != self.errno_name
            ):
                raise ContractError("request failure errno is invalid")
        times = (
            self.connect_monotonic_ns,
            self.send_monotonic_ns,
            self.failure_monotonic_ns,
        )
        if (
            any(type(item) is not int or item < 0 for item in times)
            or not times[0] <= times[1] <= times[2]
        ):
            raise ContractError("request failure monotonic times are invalid")
        if type(self.request_bytes_may_have_been_sent) is not bool:
            raise ContractError("request byte ambiguity flag is invalid")
        if self.stage != "request_send" and not self.request_bytes_may_have_been_sent:
            raise ContractError("response-stage failure must acknowledge sent request bytes")
        if (
            type(self.attempt_count) is not int
            or self.attempt_count != 1
            or self.retry_performed is not False
        ):
            raise ContractError("request failure must record one attempt and no retry")

    @classmethod
    def from_mapping(cls, value: object) -> RequestFailureProvenance:
        fields = {
            "attempt_count",
            "connect_monotonic_ns",
            "errno",
            "errno_name",
            "exception_class",
            "failure_monotonic_ns",
            "request_bytes_may_have_been_sent",
            "retry_performed",
            "send_monotonic_ns",
            "stage",
        }
        record = _require_fields(value, fields, "request failure provenance")
        reject_sensitive_material(record)
        return cls(**record)  # type: ignore[arg-type]

    def to_mapping(self) -> dict[str, object]:
        return {
            "attempt_count": self.attempt_count,
            "connect_monotonic_ns": self.connect_monotonic_ns,
            "errno": self.errno,
            "errno_name": self.errno_name,
            "exception_class": self.exception_class,
            "failure_monotonic_ns": self.failure_monotonic_ns,
            "request_bytes_may_have_been_sent": self.request_bytes_may_have_been_sent,
            "retry_performed": self.retry_performed,
            "send_monotonic_ns": self.send_monotonic_ns,
            "stage": self.stage,
        }


@dataclass(frozen=True, slots=True)
class SourceCollectionStatus:
    track: str
    source: str
    status: str
    container_id: str
    container_name: str
    source_byte_count: int | None
    source_sha256: str | None
    copied_byte_count: int | None
    copied_sha256: str | None
    error_class: str | None

    def __post_init__(self) -> None:
        if (
            type(self.track) is not str
            or self.track not in _TRACKS
            or type(self.source) is not str
            or self.source not in _SOURCES
        ):
            raise ContractError("source track or source kind is invalid")
        if type(self.status) is not str or self.status not in _STATUSES:
            raise ContractError("source collection status is invalid")
        _require_object_id(self.container_id)
        _require_name(self.container_name, "source container name")
        expected_name = re.compile(
            rf"^kil-v3b1-{_SOURCE_ROLES[self.source]}-"
            rf"{re.escape(self.track.replace('_', '-'))}-[a-f0-9]{{12}}$"
        )
        if expected_name.fullmatch(self.container_name) is None:
            raise ContractError("source container name does not match its role and track")
        source_present = _validate_byte_observation(
            self.source_byte_count,
            self.source_sha256,
            "source",
        )
        copied_present = _validate_byte_observation(
            self.copied_byte_count,
            self.copied_sha256,
            "copied source",
        )
        observations_match = (
            source_present
            and copied_present
            and self.source_byte_count == self.copied_byte_count
            and self.source_sha256 == self.copied_sha256
        )
        if self.status == "copied":
            if not observations_match or self.error_class is not None:
                raise ContractError("copied source status fields are inconsistent")
        elif self.status == "missing":
            if source_present or copied_present or self.error_class != "source_missing":
                raise ContractError("missing source status fields are inconsistent")
        elif self.status == "copy_error":
            if type(self.error_class) is not str or self.error_class not in {
                "command_failed",
                "digest_mismatch",
                "size_mismatch",
            }:
                raise ContractError("copy-error source class is invalid")
            if self.error_class == "command_failed":
                if copied_present:
                    raise ContractError("command failure cannot attest a host copy")
            elif not source_present or not copied_present:
                raise ContractError("copy mismatch requires both byte observations")
            elif self.error_class == "digest_mismatch":
                if (
                    self.source_byte_count != self.copied_byte_count
                    or self.source_sha256 == self.copied_sha256
                ):
                    raise ContractError("digest-mismatch evidence is inconsistent")
            elif (
                self.source_byte_count == self.copied_byte_count
                or self.source_sha256 == self.copied_sha256
            ):
                raise ContractError("size-mismatch evidence is inconsistent")
        elif (
            not observations_match
            or type(self.error_class) is not str
            or self.error_class not in {"invalid_json", "invalid_cardinality"}
        ):
            raise ContractError("malformed source status fields are inconsistent")

    @classmethod
    def from_mapping(cls, value: object) -> SourceCollectionStatus:
        fields = {
            "container_id",
            "container_name",
            "copied_byte_count",
            "copied_sha256",
            "error_class",
            "source",
            "source_byte_count",
            "source_sha256",
            "status",
            "track",
        }
        record = _require_fields(value, fields, "source collection status")
        reject_sensitive_material(record)
        return cls(**record)  # type: ignore[arg-type]

    def to_mapping(self) -> dict[str, object]:
        return {
            "container_id": self.container_id,
            "container_name": self.container_name,
            "copied_byte_count": self.copied_byte_count,
            "copied_sha256": self.copied_sha256,
            "error_class": self.error_class,
            "source": self.source,
            "source_byte_count": self.source_byte_count,
            "source_sha256": self.source_sha256,
            "status": self.status,
            "track": self.track,
        }


@dataclass(frozen=True, slots=True)
class DockerInventoryEntry:
    kind: str
    object_id: str
    name: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in {"container", "network"}:
            raise ContractError("Docker inventory kind is invalid")
        _require_schema_version(self.schema_version)
        _require_object_id(self.object_id)
        _require_inventory_name(self.name, self.kind, self.schema_version)

    @classmethod
    def from_mapping(
        cls,
        value: object,
        kind: str,
        *,
        schema_version: str = SCHEMA_VERSION,
    ) -> DockerInventoryEntry:
        record = _require_fields(value, {"id", "name"}, "Docker inventory entry")
        reject_sensitive_material(record)
        return cls(  # type: ignore[arg-type]
            kind=kind,
            object_id=record["id"],
            name=record["name"],
            schema_version=schema_version,
        )

    def to_mapping(self) -> dict[str, str]:
        return {"id": self.object_id, "name": self.name}


@dataclass(frozen=True, slots=True)
class DockerInventory:
    kind: str
    entries: tuple[DockerInventoryEntry, ...]
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in {"container", "network"}:
            raise ContractError("Docker inventory kind is invalid")
        _require_schema_version(self.schema_version)
        if type(self.entries) is not tuple or any(
            not isinstance(item, DockerInventoryEntry)
            or item.kind != self.kind
            or item.schema_version != self.schema_version
            for item in self.entries
        ):
            raise ContractError("Docker inventory entries are invalid")
        ids = [item.object_id for item in self.entries]
        names = [item.name for item in self.entries]
        maximum = {
            SCHEMA_VERSION: {"container": 12, "network": 3},
            DRIVER_TOPOLOGY_SCHEMA_VERSION: {"container": 15, "network": 6},
        }[self.schema_version][self.kind]
        if len(self.entries) > maximum:
            raise ContractError("Docker inventory cardinality exceeds its closed maximum")
        if len(ids) != len(set(ids)):
            raise ContractError("Docker inventory contains a duplicate ID")
        if len(names) != len(set(names)):
            raise ContractError("Docker inventory contains a duplicate name")


@dataclass(frozen=True, slots=True)
class DriverLifecycleRecord:
    """One sanitized, v2-only attached-driver lifecycle transcript record."""

    event: str
    details: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.event not in _DRIVER_LIFECYCLE_EVENTS:
            raise ContractError("driver lifecycle event is invalid")
        if type(self.details) is not dict:
            raise ContractError("driver lifecycle details are invalid")
        reject_sensitive_material(self.details)
        details = dict(self.details)
        base = {"driver_id", "readiness_nonce", "track"}
        expected = {
            "driver_start_intent": base,
            "driver_start_complete": base,
            "driver_readiness_complete": base | {"record_sha256"},
            "driver_readiness_set_complete": {
                "readiness_nonce",
                "tracks",
                "complete_monotonic_ns",
            },
            "readiness_cancel_intent": base,
            "readiness_cancel_complete": base | {"exit_code"},
            "readiness_diagnostic_complete": {
                "readiness_nonce",
                "lifecycle_mode",
            },
        }[self.event]
        if set(details) != expected:
            raise ContractError("driver lifecycle fields are not closed")
        nonce = details.get("readiness_nonce")
        if type(nonce) is not str or _HEX.fullmatch(nonce) is None:
            raise ContractError("driver lifecycle nonce is invalid")
        if self.event == "driver_readiness_set_complete":
            if (
                details["tracks"]
                != [
                    "credential_policy_baseline",
                    "signed_state_only",
                    "signed_plus_local_reduce",
                ]
                or type(details["complete_monotonic_ns"]) is not int
                or details["complete_monotonic_ns"] < 0
            ):
                raise ContractError("driver readiness set is invalid")
        elif self.event == "readiness_diagnostic_complete":
            if details["lifecycle_mode"] != "diagnostic_only":
                raise ContractError("driver diagnostic mode is invalid")
        else:
            _require_object_id(details.get("driver_id"))
            if details.get("track") not in _TRACKS:
                raise ContractError("driver lifecycle track is invalid")
            if self.event == "driver_readiness_complete":
                digest = details["record_sha256"]
                if type(digest) is not str or _HEX.fullmatch(digest) is None:
                    raise ContractError("driver readiness record digest is invalid")
            if (
                self.event == "readiness_cancel_complete"
                and details["exit_code"] != 0
            ):
                raise ContractError("driver readiness exit is invalid")
        object.__setattr__(self, "details", MappingProxyType(details))

    @classmethod
    def from_mapping(
        cls,
        value: object,
        *,
        schema_version: str,
    ) -> DriverLifecycleRecord:
        if schema_version != DRIVER_TOPOLOGY_SCHEMA_VERSION:
            raise ContractError("driver lifecycle records require the v2 schema")
        record = _require_fields(value, {"event", "details"}, "driver lifecycle")
        event = record["event"]
        details = record["details"]
        if type(event) is not str or type(details) is not dict:
            raise ContractError("driver lifecycle record is invalid")
        return cls(event=event, details=details)


def parse_inventory_rows(
    payload: str | bytes,
    kind: str,
    *,
    schema_version: str = SCHEMA_VERSION,
) -> DockerInventory:
    if type(kind) is not str or kind not in {"container", "network"}:
        raise ContractError("Docker inventory kind is invalid")
    schema = _require_schema_version(schema_version)
    try:
        if type(payload) is bytes:
            text = payload.decode("utf-8")
        elif type(payload) is str:
            text = payload
        else:
            raise ContractError("Docker inventory payload must be text or bytes")
        if not text:
            return DockerInventory(kind, (), schema)
        if (
            len(text.encode("utf-8")) > _MAX_FIXTURE_BYTES
            or not text.endswith("\n")
        ):
            raise ContractError(
                "Docker inventory rows are not bounded canonical JSONL"
            )
        entries = []
        for line in text[:-1].split("\n"):
            if not line:
                raise ContractError("Docker inventory contains a blank row")
            try:
                value = json.loads(line, object_pairs_hook=_closed_object)
            except (ValueError, ContractError) as error:
                raise ContractError(
                    "Docker inventory row is not closed JSON"
                ) from error
            if line != _canonical_json(value):
                raise ContractError("Docker inventory row is not canonical JSON")
            entries.append(
                DockerInventoryEntry.from_mapping(
                    value,
                    kind,
                    schema_version=schema,
                )
            )
        return DockerInventory(kind, tuple(entries), schema)
    except ContractError:
        raise
    except (
        UnicodeError,
        ValueError,
        TypeError,
        OverflowError,
        RecursionError,
    ) as error:
        raise ContractError("Docker inventory parsing failed closed") from error


@dataclass(frozen=True, slots=True)
class TranscriptCase:
    name: str
    provenance: str
    record_type: str
    record: (
        RequestFailureProvenance
        | SourceCollectionStatus
        | DockerInventory
        | DriverLifecycleRecord
    )

    def __post_init__(self) -> None:
        if type(self.name) is not str or _CASE_NAME.fullmatch(self.name) is None:
            raise ContractError("transcript case name is invalid")
        if (
            type(self.provenance) is not str
            or self.provenance not in {"observed", "reconstructed"}
        ):
            raise ContractError("transcript provenance must be observed or reconstructed")
        if type(self.record_type) is not str:
            raise ContractError("transcript record type is invalid")
        expected_type = {
            "request_failure": RequestFailureProvenance,
            "source_collection": SourceCollectionStatus,
            "docker_inventory": DockerInventory,
            "driver_lifecycle": DriverLifecycleRecord,
        }.get(self.record_type)
        if expected_type is None or not isinstance(self.record, expected_type):
            raise ContractError("transcript record type does not match its record")


@dataclass(frozen=True, slots=True)
class IntegrationContractFixture:
    schema_version: str
    cases: tuple[TranscriptCase, ...]

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        if type(self.cases) is not tuple:
            raise ContractError("integration transcript fixture identity is invalid")
        if any(not isinstance(case, TranscriptCase) for case in self.cases):
            raise ContractError("integration transcript fixture cases are invalid")
        if any(
            isinstance(case.record, DockerInventory)
            and case.record.schema_version != self.schema_version
            for case in self.cases
        ):
            raise ContractError("integration transcript inventory schema is inconsistent")
        names = [case.name for case in self.cases]
        if len(names) != len(set(names)):
            raise ContractError("integration transcript contains duplicate case names")


def _load_case(value: object, schema_version: str) -> TranscriptCase:
    schema = _require_schema_version(schema_version)
    case = _require_fields(
        value,
        {"name", "provenance", "record", "record_type"},
        "transcript case",
    )
    name = case["name"]
    provenance = case["provenance"]
    record_type = case["record_type"]
    if (
        type(name) is not str
        or type(provenance) is not str
        or type(record_type) is not str
    ):
        raise ContractError("transcript case labels must be strings")
    if record_type == "request_failure":
        record: (
            RequestFailureProvenance
            | SourceCollectionStatus
            | DockerInventory
            | DriverLifecycleRecord
        ) = RequestFailureProvenance.from_mapping(case["record"])
    elif record_type == "source_collection":
        record = SourceCollectionStatus.from_mapping(case["record"])
    elif record_type == "docker_inventory":
        inventory = _require_fields(case["record"], {"kind", "rows"}, "inventory transcript")
        kind = inventory["kind"]
        rows = inventory["rows"]
        if type(kind) is not str or type(rows) is not list:
            raise ContractError("inventory transcript fields are invalid")
        record = DockerInventory(
            kind,
            tuple(
                DockerInventoryEntry.from_mapping(
                    row,
                    kind,
                    schema_version=schema,
                )
                for row in rows
            ),
            schema,
        )
    elif record_type == "driver_lifecycle":
        record = DriverLifecycleRecord.from_mapping(
            case["record"], schema_version=schema
        )
    else:
        raise ContractError("transcript record type is invalid")
    return TranscriptCase(name, provenance, record_type, record)


def _lstat_fixture_path(path: Path) -> os.stat_result:
    final_info: os.stat_result | None = None
    try:
        chain = tuple(reversed(path.parents)) + (path,)
        for candidate in chain:
            info = os.lstat(candidate)
            if stat.S_ISLNK(info.st_mode):
                raise ContractError("integration transcript fixture has symlink ancestry")
            if candidate == path:
                final_info = info
            elif not stat.S_ISDIR(info.st_mode):
                raise ContractError("integration transcript fixture ancestry is invalid")
    except ContractError:
        raise
    except OSError as error:
        raise ContractError("integration transcript fixture path is unavailable") from error
    if final_info is None or not stat.S_ISREG(final_info.st_mode):
        raise ContractError("integration transcript fixture is not a regular file")
    return final_info


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _read_bounded_fixture(path: Path) -> bytes:
    if not isinstance(path, Path) or ".." in path.parts:
        raise ContractError("integration transcript fixture path is unsafe")
    absolute = path if path.is_absolute() else Path.cwd() / path
    before = _lstat_fixture_path(absolute)
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(absolute, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not _same_file_identity(before, opened)
        ):
            raise ContractError("integration transcript fixture identity changed")
        if opened.st_size <= 0 or opened.st_size > _MAX_FIXTURE_BYTES:
            raise ContractError("integration transcript fixture size is invalid")
        chunks: list[bytes] = []
        remaining = _MAX_FIXTURE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after_read = os.fstat(descriptor)
    except ContractError:
        raise
    except OSError as error:
        raise ContractError("integration transcript fixture read failed") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass

    after_path = _lstat_fixture_path(absolute)
    if (
        len(payload) > _MAX_FIXTURE_BYTES
        or len(payload) != opened.st_size
        or after_read.st_size != opened.st_size
        or after_path.st_size != opened.st_size
        or not _same_file_identity(opened, after_read)
        or not _same_file_identity(opened, after_path)
    ):
        raise ContractError("integration transcript fixture identity or size changed")
    return payload


def load_integration_contract(path: Path) -> IntegrationContractFixture:
    payload = _read_bounded_fixture(path)
    try:
        text = payload.decode("utf-8")
    except UnicodeError as error:
        raise ContractError("integration transcript fixture is not UTF-8") from error
    try:
        value = json.loads(text, object_pairs_hook=_closed_object)
    except ContractError:
        raise
    except ValueError as error:
        raise ContractError("integration transcript fixture is not JSON") from error
    reject_sensitive_material(value)
    if payload != (_canonical_json(value) + "\n").encode("utf-8"):
        raise ContractError("integration transcript fixture is not canonical JSON")
    fixture = _require_fields(value, {"cases", "schema_version"}, "integration transcript")
    cases = fixture["cases"]
    if type(cases) is not list or len(cases) > 100:
        raise ContractError("integration transcript cases are invalid")
    schema_version = _require_schema_version(fixture["schema_version"])
    return IntegrationContractFixture(
        schema_version=schema_version,
        cases=tuple(_load_case(case, schema_version) for case in cases),
    )
