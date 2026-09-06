"""Durable V3B-2a lifecycle journal and closed recovery authority."""

from __future__ import annotations

from dataclasses import dataclass, fields
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Mapping

from kil.v3b2_contracts import (
    JOURNAL_FIELDS,
    JOURNAL_SCHEMA,
    LAB_IDENTITY,
    TRACK_NAMESPACES,
    TRACKS,
)


_MAX_JOURNAL_BYTES = 1024 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_ITEMS = 100_000
_MAX_STRING_BYTES = 64 * 1024
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_SAFE_NAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
_ENV_KEYS = ("DOCKER_CONFIG", "DOCKER_HOST")
_APPLICATION_NAMESPACES = (
    "kil-v3-baseline",
    "kil-v3-local-reduce",
    "kil-v3-signed",
)


class JournalError(ValueError):
    """Raised when journal bytes or recovery authority are not closed."""


def _exact_string(label: str, value: object, *, maximum: int = 4096) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > maximum:
        raise JournalError(f"{label} must be an exact bounded nonempty string")
    return value


def _exact_digest(label: str, value: object, pattern: re.Pattern[str] = _HEX64) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise JournalError(f"{label} must be an exact lowercase hexadecimal digest")
    return value


def _absolute_path(label: str, value: object) -> str:
    text = _exact_string(label, value)
    path = Path(text)
    if not path.is_absolute() or ".." in path.parts or str(path) != text:
        raise JournalError(f"{label} must be a normalized absolute path")
    return text


@dataclass(frozen=True, slots=True)
class Command:
    argv: tuple[str, ...]
    timeout_s: int
    stdin: bytes | None = None
    env: tuple[tuple[str, str], ...] = ()
    mutating: bool = False

    def __post_init__(self) -> None:
        if type(self.argv) is not tuple or not self.argv:
            raise JournalError("command argv must be an exact nonempty tuple")
        if len(self.argv) > 256:
            raise JournalError("command argv exceeds its argument bound")
        if any(type(value) is not str or not value for value in self.argv):
            raise JournalError("command argv values must be exact nonempty strings")
        if any(len(value.encode("utf-8")) > 65536 for value in self.argv):
            raise JournalError("command argument exceeds its byte bound")
        if type(self.timeout_s) is not int or self.timeout_s <= 0 or self.timeout_s > 900:
            raise JournalError("command timeout must be an exact bounded positive integer")
        if self.stdin is not None and type(self.stdin) is not bytes:
            raise JournalError("command stdin must be exact bytes or null")
        if self.stdin is not None and len(self.stdin) > 1024 * 1024:
            raise JournalError("command stdin exceeds its byte bound")
        if type(self.env) is not tuple:
            raise JournalError("command env must be an exact tuple")
        if len(self.env) > 16:
            raise JournalError("command env exceeds its record bound")
        keys: list[str] = []
        for pair in self.env:
            if (
                type(pair) is not tuple
                or len(pair) != 2
                or type(pair[0]) is not str
                or type(pair[1]) is not str
                or not pair[0]
                or not pair[1]
            ):
                raise JournalError("command env contains an invalid binding")
            if len(pair[0].encode("utf-8")) > 256 or len(pair[1].encode("utf-8")) > 65536:
                raise JournalError("command env binding exceeds its byte bound")
            keys.append(pair[0])
        if len(keys) != len(set(keys)) or tuple(sorted(self.env)) != self.env:
            raise JournalError("command env bindings must be unique and sorted")
        if type(self.mutating) is not bool:
            raise JournalError("command mutating flag must be an exact boolean")
        environment = dict(self.env)
        executable = self.argv[0]
        def authority_values(flag: str) -> tuple[str, ...]:
            if any(item.startswith(f"{flag}=") for item in self.argv):
                raise JournalError(f"alternate {flag} syntax is prohibited")
            positions = tuple(index for index, item in enumerate(self.argv) if item == flag)
            if any(index + 1 >= len(self.argv) for index in positions):
                raise JournalError(f"{flag} lacks its value")
            return tuple(self.argv[index + 1] for index in positions)

        profiles = authority_values("--profile")
        names = authority_values("--name")
        kubeconfigs = authority_values("--kubeconfig")
        if len(profiles) > 1 or len(names) > 1 or len(kubeconfigs) > 1:
            raise JournalError("command authority flags must not be duplicated or overridden")
        if executable in {"docker", "kind"}:
            if tuple(environment) != _ENV_KEYS:
                raise JournalError("Docker/Kind commands require only both isolated bindings")
            _absolute_path("Docker configuration directory", environment["DOCKER_CONFIG"])
            endpoint = _exact_string("Docker endpoint", environment["DOCKER_HOST"])
            if not endpoint.startswith("unix:///") or not endpoint.endswith("/kil-v3-lab/docker.sock"):
                raise JournalError("Docker/Kind command endpoint is not journal-bound")
        if executable == "kind" and self.mutating:
            if names != (LAB_IDENTITY,) or len(kubeconfigs) != 1:
                raise JournalError("mutating Kind command may name only kil-v3-lab")
        if executable == "kubectl":
            if len(self.argv) < 3 or self.argv[1] != "--kubeconfig" or kubeconfigs != (self.argv[2],):
                raise JournalError("kubectl command requires an explicit leading kubeconfig")
            _absolute_path("kubectl kubeconfig", self.argv[2])
        if executable == "colima" and self.mutating:
            if profiles != (LAB_IDENTITY,):
                raise JournalError("mutating Colima command may name only kil-v3-lab")


@dataclass(frozen=True, slots=True)
class OwnedIdentity:
    colima_profile: str
    docker_host: str | None
    kind_cluster: str | None
    kubeconfig: str | None
    cluster_incarnation_uid: str | None
    node_container_id: str | None

    def __post_init__(self) -> None:
        if type(self.colima_profile) is not str or self.colima_profile != LAB_IDENTITY:
            raise JournalError("owned Colima profile must be exact kil-v3-lab")
        if self.docker_host is not None:
            value = _exact_string("owned Docker endpoint", self.docker_host)
            if not value.startswith("unix:///") or not value.endswith("/kil-v3-lab/docker.sock"):
                raise JournalError("owned Docker endpoint must bind the kil-v3-lab socket")
        if self.kind_cluster is not None and (
            type(self.kind_cluster) is not str or self.kind_cluster != LAB_IDENTITY
        ):
            raise JournalError("owned Kind cluster must be exact kil-v3-lab")
        if self.kubeconfig is not None:
            _absolute_path("owned kubeconfig", self.kubeconfig)
        if self.cluster_incarnation_uid is not None:
            _exact_string("cluster incarnation UID", self.cluster_incarnation_uid)
        if self.node_container_id is not None:
            _exact_digest("Kind node container ID", self.node_container_id)


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    commands: tuple[Command, ...]
    requests_to_send: tuple[Command, ...] = ()
    publication_allowed: bool = False

    def __post_init__(self) -> None:
        if type(self.commands) is not tuple or any(type(item) is not Command for item in self.commands):
            raise JournalError("recovery commands must contain exact Command records")
        if type(self.requests_to_send) is not tuple or any(
            type(item) is not Command for item in self.requests_to_send
        ):
            raise JournalError("recovery request commands must contain exact Command records")
        if type(self.publication_allowed) is not bool:
            raise JournalError("publication_allowed must be an exact boolean")


@dataclass(frozen=True, slots=True)
class RecoveryObservation:
    """External read-only identity observation used only to gate recovery actions."""

    docker_host: str | None
    colima_profile: str | None
    kind_cluster: str | None
    cluster_incarnation_uid: str | None
    node_container_id: str | None
    driver_pods: tuple[tuple[str, str, str], ...]

    def __post_init__(self) -> None:
        if self.docker_host is not None:
            endpoint = _exact_string("observed Docker endpoint", self.docker_host)
            if not endpoint.startswith("unix:///"):
                raise JournalError("observed Docker endpoint must be an explicit Unix socket")
        if self.colima_profile is not None and type(self.colima_profile) is not str:
            raise JournalError("observed Colima profile must be an exact string or null")
        if self.kind_cluster is not None and type(self.kind_cluster) is not str:
            raise JournalError("observed Kind cluster must be an exact string or null")
        if self.cluster_incarnation_uid is not None:
            _exact_string("observed cluster incarnation UID", self.cluster_incarnation_uid)
        if self.node_container_id is not None:
            _exact_digest("observed node container ID", self.node_container_id)
        if type(self.driver_pods) is not tuple:
            raise JournalError("observed driver Pods must be an exact tuple")
        for item in self.driver_pods:
            if type(item) is not tuple or len(item) != 3:
                raise JournalError("observed driver Pod identity is invalid")
            namespace, pod, uid = item
            if type(namespace) is not str or namespace not in _APPLICATION_NAMESPACES:
                raise JournalError("observed driver namespace is not reviewed")
            if type(pod) is not str or pod != "driver":
                raise JournalError("observed driver Pod name is not fixed")
            _exact_string("observed driver Pod UID", uid)
        if tuple(sorted(self.driver_pods)) != self.driver_pods or len(set(self.driver_pods)) != len(self.driver_pods):
            raise JournalError("observed driver Pods must be sorted and duplicate-free")


@dataclass(frozen=True, slots=True)
class JournalInputs:
    schema_version: str
    run_id: str
    execution_nonce: str
    source_commit: str
    profile_sha256: str
    phase: str
    global_context_before: str
    foreign_profiles_before: tuple[tuple[str, str], ...]
    expected_objects: tuple[str, ...]
    owned_identity: OwnedIdentity

    def __post_init__(self) -> None:
        if type(self.schema_version) is not str or self.schema_version != JOURNAL_SCHEMA:
            raise JournalError("journal schema version is not V3B-2")
        _exact_digest("run ID", self.run_id)
        _exact_digest("execution nonce", self.execution_nonce)
        _exact_digest("source commit", self.source_commit, _HEX40)
        _exact_digest("profile SHA-256", self.profile_sha256)
        if type(self.phase) is not str or self.phase != "prepared":
            raise JournalError("new journal phase must be exact prepared")
        _exact_string("global Docker context", self.global_context_before)
        if type(self.foreign_profiles_before) is not tuple:
            raise JournalError("foreign profile snapshot must be an exact tuple")
        if len(self.foreign_profiles_before) > 1024:
            raise JournalError("foreign profile snapshot exceeds its record bound")
        names: list[str] = []
        for pair in self.foreign_profiles_before:
            if (
                type(pair) is not tuple
                or len(pair) != 2
                or type(pair[0]) is not str
                or _SAFE_NAME.fullmatch(pair[0]) is None
                or pair[0] == LAB_IDENTITY
                or type(pair[1]) is not str
                or pair[1] not in {"Running", "Stopped"}
            ):
                raise JournalError("foreign profile snapshot contains an invalid record")
            names.append(pair[0])
        if (
            tuple(sorted(self.foreign_profiles_before)) != self.foreign_profiles_before
            or len(names) != len(set(names))
        ):
            raise JournalError("foreign profile snapshot must be sorted and duplicate-free")
        if type(self.expected_objects) is not tuple or any(
            type(item) is not str or not item or len(item.encode("utf-8")) > 4096
            for item in self.expected_objects
        ):
            raise JournalError("expected objects must be an exact tuple of strings")
        if len(self.expected_objects) > 4096:
            raise JournalError("expected objects exceed their record bound")
        if (
            tuple(sorted(self.expected_objects)) != self.expected_objects
            or len(self.expected_objects) != len(set(self.expected_objects))
        ):
            raise JournalError("expected objects must be sorted and duplicate-free")
        if type(self.owned_identity) is not OwnedIdentity:
            raise JournalError("owned identity must be an exact OwnedIdentity record")
        self.owned_identity.__post_init__()


def _identity_mapping(identity: OwnedIdentity) -> dict[str, object]:
    identity.__post_init__()
    return {field.name: getattr(identity, field.name) for field in fields(OwnedIdentity)}


def _inputs_mapping(inputs: JournalInputs) -> dict[str, object]:
    inputs.__post_init__()
    return {
        "schema_version": inputs.schema_version,
        "run_id": inputs.run_id,
        "execution_nonce": inputs.execution_nonce,
        "source_commit": inputs.source_commit,
        "profile_sha256": inputs.profile_sha256,
        "phase": inputs.phase,
        "global_context_before": inputs.global_context_before,
        "foreign_profiles_before": [list(item) for item in inputs.foreign_profiles_before],
        "expected_objects": list(inputs.expected_objects),
        "owned_identity": _identity_mapping(inputs.owned_identity),
        "events": [],
    }


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _duplicate_rejecting_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise JournalError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _validate_json_budget(value: object, *, depth: int = 0) -> int:
    if depth > _MAX_JSON_DEPTH:
        raise JournalError("journal JSON nesting is too deep")
    if value is None or type(value) in {bool, int}:
        return 1
    if type(value) is str:
        if len(value.encode("utf-8")) > _MAX_STRING_BYTES:
            raise JournalError("journal string exceeds its bound")
        return 1
    if type(value) is list:
        count = 1 + sum(_validate_json_budget(item, depth=depth + 1) for item in value)
    elif type(value) is dict:
        count = 1
        for key, item in value.items():
            if type(key) is not str:
                raise JournalError("journal object keys must be strings")
            count += _validate_json_budget(key, depth=depth + 1)
            count += _validate_json_budget(item, depth=depth + 1)
    else:
        raise JournalError("journal contains a non-JSON value")
    if count > _MAX_JSON_ITEMS:
        raise JournalError("journal JSON contains too many items")
    return count


def _private_location(path: Path, *, create_parent: bool) -> tuple[Path, Path]:
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise JournalError("journal path must be an absolute normalized path")
    private = path.parent
    if path.name in {"", ".", ".."} or private == path or path.parent.parent == path.parent:
        raise JournalError("journal must be a direct child of a private root")
    if create_parent and not private.exists():
        try:
            private.mkdir(mode=0o700)
        except OSError as error:
            raise JournalError(f"cannot create private journal root: {error}") from error
    try:
        inspected = os.stat(private, follow_symlinks=False)
    except OSError as error:
        raise JournalError(f"private journal root is unavailable: {error}") from error
    if not stat.S_ISDIR(inspected.st_mode) or stat.S_ISLNK(inspected.st_mode):
        raise JournalError("private journal root must be a non-symlink directory")
    if stat.S_IMODE(inspected.st_mode) != 0o700:
        raise JournalError("private journal root must have mode 0700")
    resolved_private = private.resolve(strict=True)
    if path.parent.resolve(strict=True) != resolved_private:
        raise JournalError("journal is not contained by its private root")
    return path, resolved_private


def _fsync_parent(parent: Path) -> None:
    descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_journal(path: Path, inputs: JournalInputs) -> dict[str, object]:
    """Exclusively create durable ownership state before any owned mutation."""
    if type(inputs) is not JournalInputs:
        raise JournalError("journal inputs must be an exact JournalInputs record")
    value = _inputs_mapping(inputs)
    _validate_journal(value)
    payload = _canonical_bytes(value)
    if len(payload) > _MAX_JOURNAL_BYTES:
        raise JournalError("new journal exceeds its byte bound")
    journal, private = _private_location(path, create_parent=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(journal, flags, 0o600)
    except FileExistsError as error:
        raise JournalError("journal already exists; explicit recovery required") from error
    except OSError as error:
        raise JournalError(f"cannot create journal safely: {error}") from error
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.fchmod(descriptor, 0o600)
    except BaseException:
        try:
            journal.unlink()
        finally:
            raise
    finally:
        os.close(descriptor)
    _fsync_parent(private)
    return value


def _read_bounded(path: Path) -> bytes:
    journal, _ = _private_location(path, create_parent=False)
    try:
        inspected = os.stat(journal, follow_symlinks=False)
        if stat.S_ISLNK(inspected.st_mode) or not stat.S_ISREG(inspected.st_mode):
            raise JournalError("journal must be a safe non-symlink regular file")
        if stat.S_IMODE(inspected.st_mode) != 0o600:
            raise JournalError("journal must have mode 0600")
        if inspected.st_size > _MAX_JOURNAL_BYTES:
            raise JournalError("journal exceeds its byte bound")
        descriptor = os.open(journal, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    except JournalError:
        raise
    except OSError as error:
        raise JournalError(f"cannot open journal safely: {error}") from error
    try:
        current = os.fstat(descriptor)
        if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (inspected.st_dev, inspected.st_ino):
            raise JournalError("journal identity changed while opening")
        payload = bytearray()
        while len(payload) <= _MAX_JOURNAL_BYTES:
            chunk = os.read(descriptor, min(65536, _MAX_JOURNAL_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > _MAX_JOURNAL_BYTES:
            raise JournalError("journal exceeds its byte bound")
        final = os.fstat(descriptor)
        if (final.st_dev, final.st_ino, final.st_size) != (current.st_dev, current.st_ino, current.st_size):
            raise JournalError("journal changed during its bounded read")
        return bytes(payload)
    finally:
        os.close(descriptor)


def load_journal(path: Path) -> dict[str, object]:
    payload = _read_bounded(path)
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_duplicate_rejecting_object)
    except JournalError:
        raise
    except (UnicodeError, ValueError, RecursionError) as error:
        raise JournalError("journal is not closed UTF-8 JSON") from error
    if type(value) is not dict:
        raise JournalError("journal must be a JSON object")
    _validate_json_budget(value)
    if payload != _canonical_bytes(value):
        raise JournalError("journal JSON is not canonical")
    _validate_journal(value)
    return value


def _identity_from_mapping(value: object) -> OwnedIdentity:
    expected = {field.name for field in fields(OwnedIdentity)}
    if type(value) is not dict or set(value) != expected:
        raise JournalError("owned identity fields are not closed")
    try:
        return OwnedIdentity(**value)
    except TypeError as error:
        raise JournalError("owned identity fields are invalid") from error


def _inputs_from_journal(value: Mapping[str, object]) -> JournalInputs:
    try:
        foreign = value["foreign_profiles_before"]
        objects = value["expected_objects"]
        if type(foreign) is not list or any(type(item) is not list or len(item) != 2 for item in foreign):
            raise JournalError("foreign profile snapshot is not canonical")
        if type(objects) is not list:
            raise JournalError("expected objects are not canonical")
        return JournalInputs(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            run_id=value["run_id"],  # type: ignore[arg-type]
            execution_nonce=value["execution_nonce"],  # type: ignore[arg-type]
            source_commit=value["source_commit"],  # type: ignore[arg-type]
            profile_sha256=value["profile_sha256"],  # type: ignore[arg-type]
            phase="prepared",
            global_context_before=value["global_context_before"],  # type: ignore[arg-type]
            foreign_profiles_before=tuple(tuple(item) for item in foreign),  # type: ignore[arg-type]
            expected_objects=tuple(objects),  # type: ignore[arg-type]
            owned_identity=_identity_from_mapping(value["owned_identity"]),
        )
    except KeyError as error:
        raise JournalError(f"journal is missing field: {error.args[0]}") from error


def _closed_details(details: object, expected: frozenset[str], label: str) -> dict[str, object]:
    if type(details) is not dict or set(details) != expected:
        raise JournalError(f"{label} details fields are not closed")
    return details


_PAIR_DETAILS: dict[str, frozenset[str]] = {
    "profile_start": frozenset({"colima_profile"}),
    "profile_stop": frozenset({"colima_profile"}),
    "profile_delete": frozenset({"colima_profile"}),
    "cluster_create": frozenset({"kind_cluster", "kubeconfig"}),
    "cluster_delete": frozenset({"kind_cluster", "kubeconfig"}),
    "calico_apply": frozenset({"manifest_sha256"}),
    "application_apply": frozenset({"manifest_sha256"}),
    "readiness": frozenset({"attestation_sha256"}),
    "driver_start": frozenset({"namespace", "pod", "uid"}),
    "driver_cancel": frozenset({"namespace", "pod", "uid"}),
    "evidence_freeze": frozenset({"evidence_sha256"}),
    "cluster_absence_proof": frozenset({"kind_cluster", "node_container_id"}),
    "profile_absence_proof": frozenset({"colima_profile"}),
    "foreign_snapshot_comparison": frozenset({"unchanged", "attestation_sha256"}),
    "publication": frozenset({"public_commitment_sha256"}),
}
_REQUEST_INTENT_FIELDS = frozenset({"track", "request_id", "case_sha256"})
_REQUEST_RESULT_FIELDS = frozenset({"track", "request_id", "case_sha256", "result_sha256"})
_CLUSTER_COMPLETE_FIELDS = frozenset(
    {"kind_cluster", "kubeconfig", "cluster_incarnation_uid", "node_container_id", "docker_host"}
)


def _event_family(name: str) -> tuple[str, str]:
    if name == "request_intent":
        return "request", "intent"
    if name == "request_result":
        return "request", "complete"
    for suffix, stage in (("_intent", "intent"), ("_complete", "complete")):
        if name.endswith(suffix):
            family = name[: -len(suffix)]
            if family in _PAIR_DETAILS:
                return family, stage
    raise JournalError(f"unknown journal event: {name}")


def _validate_event_details(name: str, details: object) -> tuple[str, str, tuple[object, ...]]:
    family, stage = _event_family(name)
    if family == "request":
        expected = _REQUEST_INTENT_FIELDS if stage == "intent" else _REQUEST_RESULT_FIELDS
        value = _closed_details(details, expected, name)
        if type(value["track"]) is not str or value["track"] not in TRACKS:
            raise JournalError("request track is not reviewed")
        if type(value["request_id"]) is not str or value["request_id"] != "v3b1-central-request":
            raise JournalError("request ID is not the fixed nominal request")
        _exact_digest("request case SHA-256", value["case_sha256"])
        if stage == "complete":
            _exact_digest("request result SHA-256", value["result_sha256"])
        return family, stage, (value["track"], value["request_id"])
    expected = _PAIR_DETAILS[family]
    if family == "cluster_create" and stage == "complete":
        value = _closed_details(details, _CLUSTER_COMPLETE_FIELDS, name)
        _exact_string("cluster incarnation UID", value["cluster_incarnation_uid"])
        _exact_digest("node container ID", value["node_container_id"])
        endpoint = _exact_string("Docker endpoint", value["docker_host"])
        if not endpoint.startswith("unix:///"):
            raise JournalError("Docker endpoint must be an explicit Unix socket")
    else:
        value = _closed_details(details, expected, name)
    if "colima_profile" in value and (type(value["colima_profile"]) is not str or value["colima_profile"] != LAB_IDENTITY):
        raise JournalError("event may name only the owned Colima profile")
    if "kind_cluster" in value and (type(value["kind_cluster"]) is not str or value["kind_cluster"] != LAB_IDENTITY):
        raise JournalError("event may name only the owned Kind cluster")
    if "kubeconfig" in value:
        _absolute_path("event kubeconfig", value["kubeconfig"])
    for key in ("manifest_sha256", "attestation_sha256", "evidence_sha256", "public_commitment_sha256"):
        if key in value:
            _exact_digest(key, value[key])
    if "node_container_id" in value:
        _exact_digest("node container ID", value["node_container_id"])
    if family in {"driver_start", "driver_cancel"}:
        if type(value["namespace"]) is not str or value["namespace"] not in _APPLICATION_NAMESPACES:
            raise JournalError("driver namespace is not reviewed")
        if type(value["pod"]) is not str or value["pod"] != "driver":
            raise JournalError("driver Pod name is not fixed")
        _exact_string("driver Pod UID", value["uid"])
        key = (value["namespace"], value["pod"], value["uid"])
    else:
        key = ()
    if family == "foreign_snapshot_comparison" and type(value["unchanged"]) is not bool:
        raise JournalError("foreign comparison result must be an exact boolean")
    return family, stage, key


def _validate_history(events: object) -> None:
    if type(events) is not list or len(events) > 10_000:
        raise JournalError("journal events must be a bounded exact list")
    states: dict[tuple[str, tuple[object, ...]], tuple[str, dict[str, object]]] = {}
    active: tuple[str, tuple[object, ...]] | None = None
    completed: set[tuple[str, tuple[object, ...]]] = set()
    driver_starts: dict[str, tuple[str, str, str]] = {}
    driver_cancels: set[str] = set()
    request_claims: list[str] = []
    request_results: set[str] = set()
    track_namespace = dict(TRACK_NAMESPACES)

    def done(family: str) -> bool:
        return (family, ()) in completed

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise JournalError(f"journal lifecycle phase/order violation: {message}")

    for sequence, record in enumerate(events, start=1):
        if type(record) is not dict or set(record) != {"sequence", "event", "details"}:
            raise JournalError("journal event fields are not closed")
        if type(record["sequence"]) is not int or record["sequence"] != sequence:
            raise JournalError("journal event sequence is not contiguous")
        if type(record["event"]) is not str:
            raise JournalError("journal event name must be an exact string")
        family, stage, key = _validate_event_details(record["event"], record["details"])
        state_key = (family, key)
        prior = states.get(state_key)
        if stage == "intent":
            if prior is not None:
                message = "request already claimed" if family == "request" else f"{family} intent is duplicated or already pending"
                raise JournalError(message)
            if active is not None:
                raise JournalError("journal lifecycle has overlapping pending intents")
            if family == "profile_start":
                require(sequence == 1, "profile start must be first")
            elif family == "cluster_create":
                require(done("profile_start"), "cluster create requires profile start completion")
            elif family == "calico_apply":
                require(done("cluster_create"), "Calico apply requires cluster create completion")
            elif family == "application_apply":
                require(done("calico_apply"), "application apply requires Calico completion")
            elif family == "readiness":
                require(done("application_apply"), "readiness requires application completion")
            elif family == "driver_start":
                require(done("readiness") and not done("evidence_freeze"), "driver start requires readiness before freeze")
                details = record["details"]
                assert isinstance(details, dict)
                namespace = str(details["namespace"])
                expected_namespaces = tuple(namespace for _track, namespace in TRACK_NAMESPACES)
                require(namespace not in driver_starts, "driver start is duplicated")
                require(namespace == expected_namespaces[len(driver_starts)], "driver starts are out of fixed order")
            elif family == "request":
                details = record["details"]
                assert isinstance(details, dict)
                track = str(details["track"])
                require(done("readiness") and not done("evidence_freeze"), "request requires readiness before freeze")
                require(track == TRACKS[len(request_claims)], "requests are out of fixed track order")
                require(track_namespace[track] in driver_starts, "request lacks a completed bound driver")
                if request_claims:
                    require(request_claims[-1] in request_results, "prior request is still pending")
            elif family == "evidence_freeze":
                require(done("readiness"), "evidence freeze requires completed readiness")
            elif family == "driver_cancel":
                require(done("evidence_freeze"), "driver cancellation requires durable evidence freeze")
                details = record["details"]
                assert isinstance(details, dict)
                namespace = str(details["namespace"])
                require(namespace in driver_starts, "driver cancellation lacks a started driver")
                require(driver_starts[namespace] == (namespace, str(details["pod"]), str(details["uid"])), "driver cancellation UID does not match start")
                require(namespace not in driver_cancels, "driver cancellation is duplicated")
            elif family == "cluster_delete":
                require(done("cluster_create"), "cluster deletion requires completed creation")
                require(set(driver_starts) == driver_cancels, "cluster deletion requires all drivers canceled")
                require(not done("readiness") or done("evidence_freeze"), "post-readiness deletion requires evidence freeze")
            elif family == "cluster_absence_proof":
                require(done("cluster_delete"), "cluster absence requires delete completion")
            elif family == "profile_stop":
                require(done("profile_start"), "profile stop requires start completion")
                require(not done("cluster_create") or done("cluster_absence_proof"), "profile stop requires cluster absence")
            elif family == "profile_delete":
                require(done("profile_stop"), "profile delete requires stop completion")
            elif family == "profile_absence_proof":
                require(done("profile_delete"), "profile absence requires delete completion")
            elif family == "foreign_snapshot_comparison":
                require(done("profile_absence_proof"), "foreign comparison requires owned absence")
            elif family == "publication":
                require(done("foreign_snapshot_comparison"), "publication requires foreign comparison")
            states[state_key] = ("pending", record["details"])
            if family == "request":
                details = record["details"]
                assert isinstance(details, dict)
                request_claims.append(str(details["track"]))
            else:
                active = state_key
            continue
        if prior is None or prior[0] != "pending":
            raise JournalError(f"{family} completion lacks its exact intent")
        if family == "request" and active is not None:
            raise JournalError("request completion overlaps another pending lifecycle intent")
        intent = prior[1]
        completion = record["details"]
        assert isinstance(completion, dict)
        for name, expected in intent.items():
            if completion.get(name) != expected:
                raise JournalError(f"{family} completion details do not match intent")
        states[state_key] = ("complete", completion)
        completed.add(state_key)
        if family == "request":
            request_results.add(str(completion["track"]))
        else:
            if active != state_key:
                raise JournalError(f"{family} completion is out of lifecycle order")
            active = None
        if family == "driver_start":
            driver_starts[str(completion["namespace"])] = (
                str(completion["namespace"]), str(completion["pod"]), str(completion["uid"])
            )
        elif family == "driver_cancel":
            driver_cancels.add(str(completion["namespace"]))


def _validate_journal(value: object) -> None:
    if type(value) is not dict or set(value) != JOURNAL_FIELDS:
        raise JournalError("journal fields are not closed")
    inputs = _inputs_from_journal(value)
    if type(value["phase"]) is not str or not value["phase"]:
        raise JournalError("journal phase is invalid")
    events = value["events"]
    _validate_history(events)
    assert isinstance(events, list)
    expected_phase = "prepared" if not events else events[-1]["event"]
    if value["phase"] != expected_phase:
        raise JournalError("journal phase does not match its event history")
    inputs.owned_identity.__post_init__()


def _replace_journal(path: Path, value: dict[str, object]) -> None:
    journal, private = _private_location(path, create_parent=False)
    payload = _canonical_bytes(value)
    if len(payload) > _MAX_JOURNAL_BYTES:
        raise JournalError("updated journal exceeds its byte bound")
    temporary: Path | None = None
    descriptor: int | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{journal.name}.", dir=private)
        temporary = Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, journal)
        temporary = None
        _fsync_parent(private)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def append_event(path: Path, event: str, details: Mapping[str, object]) -> dict[str, object]:
    """Validate and durably append one exact event via atomic replacement."""
    if type(event) is not str:
        raise JournalError("event name must be an exact string")
    if type(details) is not dict:
        raise JournalError("event details must be an exact dict")
    value = load_journal(path)
    events = value["events"]
    assert isinstance(events, list)
    record = {"sequence": len(events) + 1, "event": event, "details": dict(details)}
    candidate = {**value, "phase": event, "events": [*events, record]}
    _validate_json_budget(candidate)
    _validate_journal(candidate)
    _replace_journal(path, candidate)
    return candidate


def _docker_environment(identity: OwnedIdentity) -> tuple[tuple[str, str], ...]:
    if type(identity) is not OwnedIdentity:
        raise JournalError("command authority must be an exact OwnedIdentity record")
    identity.__post_init__()
    if identity.docker_host is None or identity.kubeconfig is None:
        raise JournalError("Docker/Kind command lacks exact journal-bound environment")
    docker_config = str(Path(identity.kubeconfig).parent / "docker-config")
    return (("DOCKER_CONFIG", docker_config), ("DOCKER_HOST", identity.docker_host))


def _require_complete_identity(identity: OwnedIdentity) -> None:
    if type(identity) is not OwnedIdentity:
        raise JournalError("command authority must be an exact OwnedIdentity record")
    identity.__post_init__()
    if identity.kind_cluster != LAB_IDENTITY or identity.kubeconfig is None:
        raise JournalError("Kind command lacks exact journal-bound identity")


def _colima_command(operation: str) -> Command:
    if operation not in {"start", "stop", "delete"}:
        raise JournalError("Colima operation is not closed")
    suffix = ("--force", "--data") if operation == "delete" else ()
    return Command(("colima", operation, "--profile", LAB_IDENTITY, *suffix), 300, mutating=True)


def kind_delete_command(identity: OwnedIdentity) -> Command:
    _require_complete_identity(identity)
    assert identity.kubeconfig is not None
    return Command(
        ("kind", "delete", "cluster", "--name", LAB_IDENTITY, "--kubeconfig", identity.kubeconfig),
        300,
        env=_docker_environment(identity),
        mutating=True,
    )


def _kind_create_command(identity: OwnedIdentity) -> Command:
    _require_complete_identity(identity)
    assert identity.kubeconfig is not None
    config = str(Path(identity.kubeconfig).parent / "kind-config.yaml")
    return Command(
        (
            "kind", "create", "cluster", "--name", LAB_IDENTITY,
            "--config", config, "--kubeconfig", identity.kubeconfig,
        ),
        600,
        env=_docker_environment(identity),
        mutating=True,
    )


def _kubectl(identity: OwnedIdentity, *arguments: str, mutating: bool = False) -> Command:
    _require_complete_identity(identity)
    assert identity.kubeconfig is not None
    return Command(("kubectl", "--kubeconfig", identity.kubeconfig, *arguments), 300, mutating=mutating)


def owned_commands(identity: OwnedIdentity) -> tuple[Command, ...]:
    """Return the closed owned mutation vocabulary; never discovery-selected names."""
    return (
        _colima_command("start"),
        _kind_create_command(identity),
        kind_delete_command(identity),
        _colima_command("stop"),
        _colima_command("delete"),
    )


def _bound_identity(journal: Mapping[str, object]) -> OwnedIdentity:
    identity = _identity_from_mapping(journal.get("owned_identity"))
    events = journal.get("events")
    if type(events) is not list:
        raise JournalError("manual_recovery_required: journal events are invalid")
    observed_uid: str | None = None
    observed_node: str | None = None
    for record in events:
        if type(record) is not dict:
            raise JournalError("manual_recovery_required: event identity is invalid")
        details = record.get("details")
        if type(details) is not dict:
            raise JournalError("manual_recovery_required: event identity is invalid")
        for field, expected in (
            ("docker_host", identity.docker_host),
            ("kubeconfig", identity.kubeconfig),
            ("kind_cluster", identity.kind_cluster),
            ("colima_profile", identity.colima_profile),
        ):
            if field in details and details[field] != expected:
                raise JournalError(f"manual_recovery_required: {field} mismatch")
        if "node_container_id" in details and identity.node_container_id not in {
            None,
            details["node_container_id"],
        }:
            raise JournalError("manual_recovery_required: node container ID mismatch")
        if "cluster_incarnation_uid" in details and identity.cluster_incarnation_uid not in {
            None,
            details["cluster_incarnation_uid"],
        }:
            raise JournalError("manual_recovery_required: cluster-incarnation UID mismatch")
        if record.get("event") != "cluster_create_complete":
            continue
        observed_uid = details.get("cluster_incarnation_uid")  # type: ignore[assignment]
        observed_node = details.get("node_container_id")  # type: ignore[assignment]
        if identity.cluster_incarnation_uid not in {None, observed_uid}:
            raise JournalError("manual_recovery_required: cluster-incarnation UID mismatch")
        if identity.node_container_id not in {None, observed_node}:
            raise JournalError("manual_recovery_required: node container ID mismatch")
    return OwnedIdentity(
        identity.colima_profile,
        identity.docker_host,
        identity.kind_cluster,
        identity.kubeconfig,
        observed_uid or identity.cluster_incarnation_uid,
        observed_node or identity.node_container_id,
    )


def _pending_events(events: list[dict[str, object]]) -> list[tuple[str, dict[str, object]]]:
    pending: dict[tuple[str, tuple[object, ...]], tuple[str, dict[str, object]]] = {}
    for record in events:
        name = record["event"]
        details = record["details"]
        assert isinstance(name, str) and isinstance(details, dict)
        family, stage, key = _validate_event_details(name, details)
        state_key = (family, key)
        if stage == "intent":
            pending[state_key] = (family, details)
        else:
            pending.pop(state_key, None)
    return list(pending.values())


def _pending_command(family: str, details: dict[str, object], identity: OwnedIdentity) -> Command | None:
    if family in {"profile_start", "profile_stop", "profile_delete", "profile_absence_proof"}:
        return Command(("colima", "status", "--profile", LAB_IDENTITY), 60)
    if family in {"cluster_create", "cluster_delete", "cluster_absence_proof"}:
        return _docker_inspect_node(identity)
    if family in {"calico_apply", "application_apply"}:
        if family == "calico_apply":
            return _kubectl(identity, "get", "all", "--namespace", "kube-system", "--output", "json")
        return _kubectl(identity, "get", "all,networkpolicies", "--all-namespaces", "--output", "json")
    if family == "driver_start":
        return _driver_uid_attestation(identity, details)
    if family == "driver_cancel":
        return _driver_uid_attestation(identity, details)
    if family == "evidence_freeze":
        return _evidence_freeze_commands(identity, ())[0]
    if family == "readiness":
        return _kubectl(identity, "get", "pods", "--all-namespaces", "--output", "json")
    if family == "foreign_snapshot_comparison":
        return Command(("colima", "list", "--json"), 60)
    return None


def _docker_inspect_node(identity: OwnedIdentity) -> Command:
    return Command(
        ("docker", "inspect", f"{LAB_IDENTITY}-control-plane"),
        60,
        env=_docker_environment(identity),
    )


def _cluster_attestations(identity: OwnedIdentity) -> tuple[Command, ...]:
    return (
        _docker_inspect_node(identity),
        _kubectl(identity, "get", "namespace", "kube-system", "--output", "json"),
    )


def _driver_uid_attestation(identity: OwnedIdentity, details: Mapping[str, object]) -> Command:
    return _kubectl(
        identity,
        "get",
        "pod",
        str(details["pod"]),
        "--namespace",
        str(details["namespace"]),
        "--field-selector",
        f"metadata.uid={details['uid']}",
        "--output",
        "name",
    )


def _driver_delete(identity: OwnedIdentity, details: Mapping[str, object]) -> Command:
    return _kubectl(
        identity,
        "delete",
        "pod",
        str(details["pod"]),
        "--namespace",
        str(details["namespace"]),
        "--wait=true",
        mutating=True,
    )


def _evidence_freeze_commands(
    identity: OwnedIdentity, drivers: tuple[tuple[str, str, str], ...]
) -> tuple[Command, ...]:
    commands: list[Command] = []
    for namespace, pod, _uid in drivers:
        commands.append(_kubectl(identity, "logs", f"pod/{pod}", "--namespace", namespace, "--limit-bytes=1048576"))
    for _track, namespace in TRACK_NAMESPACES:
        for role in ("authz", "envoy", "target"):
            commands.append(_kubectl(identity, "logs", f"deployment/{role}", "--namespace", namespace, "--limit-bytes=1048576"))
    commands.append(
        _kubectl(
            identity,
            "get",
            "namespaces,pods,services,endpoints,endpointslices,serviceaccounts,configmaps,deployments,daemonsets,networkpolicies",
            "--all-namespaces",
            "--output",
            "json",
        )
    )
    return tuple(commands)


def _completed_driver_identities(events: list[dict[str, object]]) -> tuple[tuple[str, str, str], ...]:
    started: dict[str, tuple[str, str, str]] = {}
    canceled: set[str] = set()
    for record in events:
        details = record["details"]
        assert isinstance(details, dict)
        if record["event"] == "driver_start_complete":
            started[str(details["namespace"])] = (
                str(details["namespace"]), str(details["pod"]), str(details["uid"])
            )
        elif record["event"] == "driver_cancel_complete":
            canceled.add(str(details["namespace"]))
    return tuple(sorted(identity for namespace, identity in started.items() if namespace not in canceled))


def _validate_observation(
    observation: RecoveryObservation | None,
    identity: OwnedIdentity,
    drivers: tuple[tuple[str, str, str], ...],
) -> RecoveryObservation | None:
    if observation is None:
        return None
    if type(observation) is not RecoveryObservation:
        raise JournalError("manual_recovery_required: observation type is invalid")
    observation.__post_init__()
    endpoint_absent_after_owned_teardown = (
        observation.docker_host is None
        and observation.colima_profile is None
        and observation.kind_cluster is None
    )
    if observation.docker_host != identity.docker_host and not endpoint_absent_after_owned_teardown:
        raise JournalError("manual_recovery_required: observed Docker endpoint mismatch")
    if observation.colima_profile not in {None, identity.colima_profile}:
        raise JournalError("manual_recovery_required: observed Colima profile mismatch")
    if observation.colima_profile is None and observation.kind_cluster is not None:
        raise JournalError("manual_recovery_required: cluster cannot outlive its owned profile")
    if observation.kind_cluster is not None:
        if observation.kind_cluster != identity.kind_cluster:
            raise JournalError("manual_recovery_required: observed Kind cluster mismatch")
        if observation.cluster_incarnation_uid != identity.cluster_incarnation_uid:
            raise JournalError("manual_recovery_required: observed cluster-incarnation UID mismatch")
        if observation.node_container_id != identity.node_container_id:
            raise JournalError("manual_recovery_required: observed node container ID mismatch")
    elif observation.cluster_incarnation_uid is not None or observation.node_container_id is not None:
        raise JournalError("manual_recovery_required: absent cluster has residual identity")
    if observation.kind_cluster is None and observation.driver_pods:
        raise JournalError("manual_recovery_required: driver Pods cannot outlive the cluster")
    expected_by_namespace = {item[0]: item for item in drivers}
    for observed in observation.driver_pods:
        expected = expected_by_namespace.get(observed[0])
        if expected is None or observed != expected:
            raise JournalError("manual_recovery_required: observed driver Pod UID mismatch")
    return observation


def recovery_plan(
    journal: Mapping[str, object], observation: RecoveryObservation | None = None
) -> RecoveryPlan:
    """Derive bounded idempotent recovery from validated journal authority only."""
    if type(journal) is not dict:
        raise JournalError("manual_recovery_required: recovery journal must be an exact dict")
    try:
        _validate_journal(journal)
        identity = _bound_identity(journal)
    except JournalError as error:
        if "manual_recovery_required" in str(error):
            raise
        raise JournalError(f"manual_recovery_required: {error}") from error
    events = journal["events"]
    assert isinstance(events, list)
    typed_events = events  # validation proved the closed record shape
    pending = _pending_events(typed_events)  # type: ignore[arg-type]
    drivers = _completed_driver_identities(typed_events)  # type: ignore[arg-type]
    observed = _validate_observation(observation, identity, drivers)
    request_claimed = any(record["event"] == "request_intent" for record in typed_events)
    frozen = any(record["event"] == "evidence_freeze_complete" for record in typed_events)
    readiness_complete = any(record["event"] == "readiness_complete" for record in typed_events)
    if (request_claimed or readiness_complete) and not frozen:
        return RecoveryPlan(
            _evidence_freeze_commands(identity, drivers),
            requests_to_send=(),
            publication_allowed=False,
        )
    if frozen and drivers and observed is None:
        return RecoveryPlan(
            tuple(_driver_uid_attestation(identity, {"namespace": item[0], "pod": item[1], "uid": item[2]}) for item in drivers),
            requests_to_send=(),
            publication_allowed=False,
        )
    if frozen and drivers:
        assert observed is not None
        observed_set = set(observed.driver_pods)
        commands: list[Command] = []
        for item in drivers:
            if item not in observed_set:
                continue
            details = {"namespace": item[0], "pod": item[1], "uid": item[2]}
            commands.extend((_driver_uid_attestation(identity, details), _driver_delete(identity, details)))
        return RecoveryPlan(tuple(commands), requests_to_send=(), publication_allowed=False)
    command_pending = [(family, details) for family, details in pending if family != "request"]
    if command_pending:
        if len(command_pending) != 1:
            raise JournalError("manual_recovery_required: multiple owned mutations are pending")
        if command_pending[0][0] == "evidence_freeze":
            return RecoveryPlan(_evidence_freeze_commands(identity, drivers))
        command = _pending_command(*command_pending[0], identity)
        return RecoveryPlan(()) if command is None else RecoveryPlan((command,))
    completed = {record["event"] for record in typed_events}
    if not typed_events:
        return RecoveryPlan((Command(("colima", "status", "--profile", LAB_IDENTITY), 60),))
    if "cluster_create_complete" in completed and "cluster_delete_complete" not in completed:
        if observed is None or observed.kind_cluster is None:
            return RecoveryPlan(_cluster_attestations(identity))
        return RecoveryPlan((*_cluster_attestations(identity), kind_delete_command(identity)))
    if "profile_start_complete" in completed and "profile_stop_complete" not in completed:
        status = Command(("colima", "status", "--profile", LAB_IDENTITY), 60)
        if observed is None or observed.colima_profile is None:
            return RecoveryPlan((status,))
        return RecoveryPlan((status, _colima_command("stop")))
    if "profile_stop_complete" in completed and "profile_delete_complete" not in completed:
        status = Command(("colima", "status", "--profile", LAB_IDENTITY), 60)
        if observed is None or observed.colima_profile is None:
            return RecoveryPlan((status,))
        return RecoveryPlan((status, _colima_command("delete")))
    publication_allowed = {
        "cluster_absence_proof_complete",
        "profile_absence_proof_complete",
        "foreign_snapshot_comparison_complete",
        "publication_complete",
    }.issubset(completed)
    return RecoveryPlan((), publication_allowed=publication_allowed)


__all__ = [
    "Command",
    "JournalError",
    "JournalInputs",
    "OwnedIdentity",
    "RecoveryPlan",
    "RecoveryObservation",
    "append_event",
    "create_journal",
    "kind_delete_command",
    "load_journal",
    "owned_commands",
    "recovery_plan",
]
