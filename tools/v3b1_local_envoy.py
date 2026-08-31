#!/usr/bin/env python3
"""Run the closed, local-only V3B-1 pinned Envoy boundary proof."""

from argparse import ArgumentParser
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from html import escape
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from typing import Callable, Mapping, Protocol, Sequence

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from kil.canonical import canonical_json
from kil.live_authz import LiveTrack
from kil.q_state import QStateClaims, issue_q_state, key_id
from kil.v3b_envoy import render_envoy_json
from kil.v3b1_driver_protocol import (
    DRIVER_RUNTIME_POLICY,
    canonical_record,
    driver_definition,
)
from kil.v3b_preflight import EVIDENCE_SCOPE, LAB_IDENTITY, V3BProfile

try:
    from tools.bootstrap_v3b_tools import verify_content_lock
except ModuleNotFoundError:  # Direct execution places ``tools`` on sys.path.
    from bootstrap_v3b_tools import verify_content_lock

try:
    from tools.v3b1_harness_contract import (
        ContractError as HarnessContractError,
        DRIVER_TOPOLOGY_SCHEMA_VERSION,
        DockerInventory,
        DockerInventoryEntry,
        RequestFailureProvenance,
        SourceCollectionStatus,
        normalize_transport_exception,
        parse_inventory_rows,
        reject_sensitive_material,
    )
except ModuleNotFoundError:  # Direct execution places ``tools`` on sys.path.
    from v3b1_harness_contract import (  # type: ignore[no-redef]
        ContractError as HarnessContractError,
        DRIVER_TOPOLOGY_SCHEMA_VERSION,
        DockerInventory,
        DockerInventoryEntry,
        RequestFailureProvenance,
        SourceCollectionStatus,
        normalize_transport_exception,
        parse_inventory_rows,
        reject_sensitive_material,
    )


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_STATE_PATH = ROOT / ".tools/state/v3b1-active.json"
PYTHON_IMAGE_TAG = "docker.io/library/python:3.12.13-slim"
REQUEST_ID = "v3b1-central-request"
AUTHORIZATION = "Bearer v3b1-lab-credential"
SUBJECT = "spiffe://kil.local/workload/demo"
PLATFORM = "linux/arm64"
LEGACY_MANIFEST_SCHEMA = "kil.v3b1-manifest.v1"
MANIFEST_SCHEMA = "kil.v3b1-manifest.v2"
STATE_SCHEMA = "kil.v3b1-active-state.v2"
JOURNAL_SCHEMA = "kil.v3b1-lifecycle-journal.v1"
READINESS_POISON_SCHEMA = "kil.v3b1-readiness-poison.v1"
JOIN_SCHEMA = "kil.v3b1-join.v1"
_HEX = re.compile(r"^[a-f0-9]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[a-f0-9]{64}$")
_DIGEST_REF = re.compile(
    r"^(?P<repository>[a-z0-9.-]+(?::[0-9]+)?/[a-z0-9._/-]+)"
    r"@sha256:(?P<digest>[a-f0-9]{64})$"
)
_ANY_DIGEST_REF = re.compile(
    r"^(?P<repository>[a-z0-9._/-]+(?::[0-9]+)?(?:/[a-z0-9._/-]+)*)"
    r"@sha256:(?P<digest>[a-f0-9]{64})$"
)
_TRACKS = tuple(LiveTrack)
_TRACK_PORTS = dict(zip(_TRACKS, (18080, 18081, 18082), strict=True))
_BUILD_CONTEXT_FILES = (
    "README.md",
    "pyproject.toml",
    "deploy/kind/Dockerfile.v3b",
    "deploy/kind/Dockerfile.v3b.dockerignore",
    "deploy/kind/requirements-v3b-build.txt",
    "deploy/kind/requirements-v3b-runtime.txt",
    "src/kil/__init__.py",
    "src/kil/canonical.py",
    "src/kil/decay.py",
    "src/kil/domain.py",
    "src/kil/engine.py",
    "src/kil/ext_authz_http.py",
    "src/kil/live_authz.py",
    "src/kil/q_state.py",
    "src/kil/target_http.py",
    "src/kil/v3b1_driver_protocol.py",
    "src/kil/v3b1_request_driver.py",
)
RETRY_CONTROL_HEADERS = {
    "x-envoy-hedge-on-per-try-timeout": "false",
    "x-envoy-max-retries": "0",
}
_READINESS_DEADLINE_NS = 30_000_000_000
_READINESS_CONNECT_TIMEOUT_S = 1.0
_READINESS_ROUND_DELAY_S = 0.25
REQUEST_TIMEOUT_S = 5.0
ADVERSARIAL_HEADERS = {
    "x-kil-decision-digest": "f" * 64,
    "x-kil-issuer": "https://attacker.invalid",
    "x-kil-local-evidence": '{"divergence":"0"}',
    "x-kil-mode": "credential_policy_baseline",
    "x-kil-track": "client-selected-track",
    "x-kil-verified-subject": "spiffe://attacker.invalid/workload",
}
_AUTHZ_BOOTSTRAP = (
    "import os,runpy;"
    "fd=os.open('/evidence/decisions.jsonl',"
    "os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);"
    "os.close(fd);"
    "runpy.run_module('kil.ext_authz_http',run_name='__main__')"
)
_TARGET_BOOTSTRAP = (
    "import os,runpy;"
    "fd=os.open('/evidence/targets.jsonl',"
    "os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);"
    "os.close(fd);"
    "runpy.run_module('kil.target_http',run_name='__main__')"
)
_EVIDENCE_FILES = (
    "requests.jsonl",
    "decisions.jsonl",
    "envoy.jsonl",
    "targets.jsonl",
    "joins.jsonl",
    "manifest.json",
    "summary.md",
    "live.html",
)
_KTP_CITATION_URL = "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff"
_KTP_CITATION = f"KTP citation: [canonical `CITATION.cff`]({_KTP_CITATION_URL}).\n"
_FREEZE_SOURCES = ("envoy_access", "authz_decisions", "target_markers")
_LEDGER_PATH = {
    "authz_decisions": "/evidence/decisions.jsonl",
    "target_markers": "/evidence/targets.jsonl",
}
_SOURCE_ROLE = {
    "envoy_access": "envoy",
    "authz_decisions": "authz",
    "target_markers": "target",
}
_ENVOY_LOG_NAME = "envoy.stdout.jsonl"
_FREEZE_FILE_NAME = {
    "envoy_access": _ENVOY_LOG_NAME,
    "authz_decisions": "decisions.jsonl",
    "target_markers": "targets.jsonl",
}
_LEDGER_PROBE = (
    "import hashlib,json,os,stat,sys;"
    "p=sys.argv[1];"
    "r={'exists':False,'regular_file':False,'byte_count':None,'sha256':None};"
    "\ntry:s=os.lstat(p)\n"
    "except FileNotFoundError:pass\n"
    "else:\n"
    " r['exists']=True;r['regular_file']=stat.S_ISREG(s.st_mode)\n"
    " if r['regular_file']:\n"
    "  h=hashlib.sha256();n=0\n"
    "  with open(p,'rb') as f:\n"
    "   while True:\n"
    "    b=f.read(1048576)\n"
    "    if not b:break\n"
    "    n+=len(b);h.update(b)\n"
    "  r['byte_count']=n;r['sha256']=h.hexdigest()\n"
    "print(json.dumps(r,sort_keys=True,separators=(',',':')))"
)
_MAX_LEDGER_EXPORT_BYTES = 128 * 1024 + 1
_MAX_LEDGER_EXPORT_OUTPUT_BYTES = 2 * _MAX_LEDGER_EXPORT_BYTES + 256
_LEDGER_EXPORT = (
    "import hashlib,json,os,stat,sys;"
    "p=sys.argv[1];m=int(sys.argv[2]);"
    "fd=os.open(p,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0));"
    "\ntry:\n"
    " s=os.fstat(fd)\n"
    " if not stat.S_ISREG(s.st_mode):raise RuntimeError('not_regular')\n"
    " b=b''\n"
    " while len(b)<=m:\n"
    "  c=os.read(fd,min(65536,m+1-len(b)))\n"
    "  if not c:break\n"
    "  b+=c\n"
    " e=os.fstat(fd)\n"
    "\nfinally:os.close(fd)\n"
    "c=os.lstat(p);"
    "\nif (s.st_dev,s.st_ino)!=(e.st_dev,e.st_ino) or "
    "(s.st_dev,s.st_ino)!=(c.st_dev,c.st_ino) or "
    "s.st_size!=e.st_size or e.st_size!=len(b) or len(b)>m:"
    "raise RuntimeError('changed_or_oversize')\n"
    "r={'byte_count':len(b),'payload_hex':b.hex(),"
    "'sha256':hashlib.sha256(b).hexdigest()};"
    "print(json.dumps(r,sort_keys=True,separators=(',',':')))"
)


class ControllerError(RuntimeError):
    """Raised when the closed controller cannot preserve its invariants."""


@dataclass(frozen=True, slots=True)
class PresenterTrack:
    track: str
    outcome: str
    http_status: int
    target_marker_count: int
    forwarded: bool
    decision_digest: str
    adapter_reasons: tuple[str, ...]
    engine_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PresenterModel:
    run_id: str
    request_id: str
    evidence_scope: str
    source_commit: str
    tracks: tuple[PresenterTrack, ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout_s: float = 30,
    ) -> CommandResult: ...


class SubprocessCommandRunner:
    """Execute explicit argv lists without a shell."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        input_text: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout_s: float = 30,
    ) -> CommandResult:
        if not argv or any(type(part) is not str or not part for part in argv):
            raise ControllerError("command must be a nonempty string list")
        try:
            completed = subprocess.run(
                list(argv),
                cwd=cwd,
                input=input_text,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_s,
                env=None if env is None else dict(env),
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ControllerError(f"command execution failed: {argv[0]}") from error
        return CommandResult(
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )


@dataclass(frozen=True, slots=True)
class MaterializedInputs:
    runtime_root: Path
    requests: Mapping[LiveTrack, dict[str, object]]


@dataclass(frozen=True, slots=True)
class EvidenceFreezeResult:
    collection_epoch: str
    statuses: tuple[SourceCollectionStatus, ...]
    raw_paths: Mapping[tuple[str, str], Path]
    complete: bool


def _digest_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _digest_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _closed_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ControllerError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _load_json_bytes(payload: bytes, label: str) -> dict[str, object]:
    try:
        text = payload.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_closed_object)
    except ControllerError:
        raise
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ControllerError(f"{label} is not closed UTF-8 JSON") from error
    if type(value) is not dict:
        raise ControllerError(f"{label} must be a JSON object")
    return value


def _write_file(path: Path, payload: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ControllerError(f"refusing symbolic-link output: {path}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _require_sha256(name: str, value: object) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ControllerError(f"{name} must be a SHA-256 digest")
    return value


def _require_digest_ref(name: str, value: object) -> str:
    if type(value) is not str or _DIGEST_REF.fullmatch(value) is None:
        raise ControllerError(f"{name} must be an immutable registry digest")
    return value


def _require_contained(path: Path, parent: Path, label: str) -> Path:
    resolved_parent = parent.resolve()
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(resolved_parent)
    except ValueError as error:
        raise ControllerError(f"{label} is not contained in its private root") from error
    current = Path(os.path.abspath(path))
    while True:
        if current.is_symlink():
            raise ControllerError(f"symbolic-link {label} component is unsafe: {current}")
        if current.resolve(strict=False) == resolved_parent:
            break
        if current.parent == current:
            raise ControllerError(f"{label} containment root is unreachable")
        current = current.parent
    return resolved


def comparison_facts_sha256(facts: Mapping[str, object]) -> str:
    """Hash the one approved shared request projection used by all tracks."""
    expected = {
        "method",
        "path",
        "authorization_sha256",
        "adversarial_headers",
        "retry_control_headers",
    }
    if type(facts) is not dict or set(facts) != expected:
        raise ControllerError("comparison facts are not closed")
    if facts["method"] != "POST" or facts["path"] != "/consequential/admin":
        raise ControllerError("comparison facts are not the approved central request")
    _require_sha256("comparison authorization_sha256", facts["authorization_sha256"])
    if facts["adversarial_headers"] != ADVERSARIAL_HEADERS:
        raise ControllerError("comparison adversarial headers are invalid")
    if facts["retry_control_headers"] != RETRY_CONTROL_HEADERS:
        raise ControllerError("comparison retry controls are invalid")
    return _digest_bytes(canonical_json(dict(facts)).encode("utf-8"))


def _freeze_relative_path(track: object, source: object) -> str:
    try:
        fixed_track = LiveTrack(track)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ControllerError("frozen-byte track is invalid") from error
    if type(source) is not str or source not in _FREEZE_FILE_NAME:
        raise ControllerError("frozen-byte source is invalid")
    return f"{fixed_track.value}/{_FREEZE_FILE_NAME[source]}"


def _journal_binding(value: Mapping[str, object]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "binding_sha256"}
    return _digest_bytes(canonical_json(unsigned).encode("utf-8"))


def _validate_lifecycle_event_details(
    event_name: str,
    details: Mapping[str, object],
    requests: Mapping[str, object] | None = None,
) -> None:
    if event_name == "partial_up_evidence_rejected":
        expected = {
            "reason_code",
            "up_complete_observed",
            "promotable",
            "container_count",
            "network_count",
            "survivor_identity_sha256",
        }
        if (
            set(details) != expected
            or details["reason_code"] != "up_complete_absent"
            or details["up_complete_observed"] is not False
            or details["promotable"] is not False
            or type(details["container_count"]) is not int
            or not 0 <= details["container_count"] <= 15
            or type(details["network_count"]) is not int
            or not 0 <= details["network_count"] <= 6
        ):
            raise ControllerError("partial-up rejection provenance is invalid")
        _require_sha256(
            "partial-up survivor identity",
            details["survivor_identity_sha256"],
        )
        return
    if event_name in {
        "container_create_intent",
        "container_create_complete",
        "network_create_intent",
        "network_create_complete",
        "validator_create_intent",
        "validator_create_complete",
    }:
        kind = (
            "container"
            if event_name.startswith(("container_", "validator_"))
            else "network"
        )
        expected = {"name"}
        if event_name.endswith("_complete"):
            expected.add("id")
        if set(details) != expected:
            raise ControllerError("Docker creation fields are not closed")
        try:
            DockerInventoryEntry(
                kind,
                str(details.get("id", "0" * 64)),
                details["name"],  # type: ignore[arg-type]
                DRIVER_TOPOLOGY_SCHEMA_VERSION,
            )
        except HarnessContractError as error:
            raise ControllerError("Docker creation identity is invalid") from error
        return
    if event_name in {"network_connect_intent", "network_connect_complete"}:
        expected = {
            "container_id",
            "container_name",
            "network_id",
            "network_name",
            "alias",
        }
        if set(details) != expected or details.get("alias") != "envoy":
            raise ControllerError("network connect fields are not closed")
        try:
            DockerInventoryEntry(
                "container",
                details["container_id"],  # type: ignore[arg-type]
                details["container_name"],  # type: ignore[arg-type]
                DRIVER_TOPOLOGY_SCHEMA_VERSION,
            )
            DockerInventoryEntry(
                "network",
                details["network_id"],  # type: ignore[arg-type]
                details["network_name"],  # type: ignore[arg-type]
                DRIVER_TOPOLOGY_SCHEMA_VERSION,
            )
        except HarnessContractError as error:
            raise ControllerError("network connect identity is invalid") from error
        container_match = re.fullmatch(
            r"kil-v3b1-envoy-(?P<track>credential-policy-baseline|"
            r"signed-state-only|signed-plus-local-reduce)-(?P<suffix>[a-f0-9]{12})",
            str(details["container_name"]),
        )
        network_match = re.fullmatch(
            r"kil-v3b1-frontend-(?P<track>credential-policy-baseline|"
            r"signed-state-only|signed-plus-local-reduce)-(?P<suffix>[a-f0-9]{12})",
            str(details["network_name"]),
        )
        if (
            container_match is None
            or network_match is None
            or container_match.groupdict() != network_match.groupdict()
        ):
            raise ControllerError("network connect roles do not match")
        return
    if event_name in {"config_validate_intent", "config_validate_complete"}:
        try:
            DockerInventoryEntry.from_mapping(
                details,
                "container",
                schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION,
            )
        except HarnessContractError as error:
            raise ControllerError("validator execution identity is invalid") from error
        return
    if event_name in {
        "container_remove_intent",
        "container_remove_complete",
        "network_remove_intent",
        "network_remove_complete",
    }:
        kind = "container" if event_name.startswith("container_") else "network"
        try:
            DockerInventoryEntry.from_mapping(
                details, kind, schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION
            )
        except HarnessContractError as error:
            raise ControllerError("Docker removal identity is invalid") from error
        return
    if event_name == "evidence_freeze_started":
        if set(details) != {"collection_epoch", "execution_nonce", "run_id"}:
            raise ControllerError("evidence freeze start fields are not closed")
        _require_sha256("collection_epoch", details["collection_epoch"])
        _require_sha256("freeze execution_nonce", details["execution_nonce"])
        if (
            type(details["run_id"]) is not str
            or re.fullmatch(r"v3b1-[a-f0-9]{64}", details["run_id"]) is None
        ):
            raise ControllerError("evidence freeze run ID is invalid")
        return
    if event_name == "source_collection_intent":
        expected = {
            "collection_epoch",
            "track",
            "source",
            "container_id",
            "container_name",
        }
        if set(details) != expected:
            raise ControllerError("source collection intent fields are not closed")
        _require_sha256("collection_epoch", details["collection_epoch"])
        try:
            SourceCollectionStatus.from_mapping(
                {
                    "track": details["track"],
                    "source": details["source"],
                    "status": "missing",
                    "container_id": details["container_id"],
                    "container_name": details["container_name"],
                    "source_byte_count": None,
                    "source_sha256": None,
                    "copied_byte_count": None,
                    "copied_sha256": None,
                    "error_class": "source_missing",
                }
            )
        except HarnessContractError as error:
            raise ControllerError("source collection intent identity is invalid") from error
        return
    if event_name == "evidence_freeze_leg_bytes_persisted":
        expected = {
            "collection_epoch",
            "track",
            "source",
            "path_relative",
            "byte_count",
            "sha256",
        }
        if set(details) != expected:
            raise ControllerError("frozen-byte persistence fields are not closed")
        _require_sha256("collection_epoch", details["collection_epoch"])
        if details["path_relative"] != _freeze_relative_path(
            details["track"], details["source"]
        ):
            raise ControllerError("frozen-byte relative path is invalid")
        if type(details["byte_count"]) is not int or details["byte_count"] < 0:
            raise ControllerError("frozen-byte count is invalid")
        _require_sha256("frozen-byte sha256", details["sha256"])
        return
    if event_name == "source_collection_terminal":
        if set(details) != {"collection_epoch", "record"}:
            raise ControllerError("source collection terminal fields are not closed")
        _require_sha256("collection_epoch", details["collection_epoch"])
        try:
            SourceCollectionStatus.from_mapping(details["record"])
        except HarnessContractError as error:
            raise ControllerError("source collection terminal record is invalid") from error
        return
    if event_name == "evidence_freeze_complete":
        expected = {
            "collection_epoch",
            "terminal_count",
            "records_sha256",
            "promotable",
        }
        if set(details) != expected:
            raise ControllerError("evidence freeze completion fields are not closed")
        _require_sha256("collection_epoch", details["collection_epoch"])
        _require_sha256("freeze records_sha256", details["records_sha256"])
        if details["terminal_count"] != 9 or type(details["terminal_count"]) is not int:
            raise ControllerError("evidence freeze terminal count is invalid")
        if type(details["promotable"]) is not bool:
            raise ControllerError("evidence freeze promotability is invalid")
        return
    if event_name == "readiness_session_started":
        if set(details) != {"readiness_nonce"}:
            raise ControllerError("readiness session event fields are not closed")
        _require_sha256("readiness_nonce", details["readiness_nonce"])
        return
    if event_name == "readiness_connect_complete":
        expected = {
            "readiness_nonce",
            "round",
            "host",
            "tracks",
            "ports",
            "ready_monotonic_ns",
        }
        if set(details) != expected:
            raise ControllerError("readiness event fields are not closed")
        _require_sha256("readiness_nonce", details["readiness_nonce"])
        if (
            type(details["round"]) is not int
            or details["round"] < 1
            or details["host"] != "127.0.0.1"
            or details["tracks"] != [track.value for track in _TRACKS]
            or details["ports"] != list(_TRACK_PORTS.values())
            or type(details["ready_monotonic_ns"]) is not int
            or details["ready_monotonic_ns"] < 0
        ):
            raise ControllerError("readiness completion event is invalid")
        return
    if event_name == "readiness_connect_failed":
        expected = {
            "readiness_nonce",
            "track",
            "host",
            "port",
            "round",
            "connect_monotonic_ns",
            "failure_monotonic_ns",
            "exception_class",
            "errno",
            "errno_name",
            "request_bytes_may_have_been_sent",
        }
        if set(details) != expected:
            raise ControllerError("readiness event fields are not closed")
        _require_sha256("readiness_nonce", details["readiness_nonce"])
        try:
            track = LiveTrack(details["track"])
        except (TypeError, ValueError) as error:
            raise ControllerError("readiness failure track is invalid") from error
        if (
            details["host"] != "127.0.0.1"
            or details["port"] != _TRACK_PORTS[track]
            or type(details["round"]) is not int
            or details["round"] < 1
            or details["request_bytes_may_have_been_sent"] is not False
        ):
            raise ControllerError("readiness failure event is invalid")
        try:
            RequestFailureProvenance(
                stage="request_send",
                exception_class=details["exception_class"],  # type: ignore[arg-type]
                errno=details["errno"],  # type: ignore[arg-type]
                errno_name=details["errno_name"],  # type: ignore[arg-type]
                connect_monotonic_ns=details["connect_monotonic_ns"],  # type: ignore[arg-type]
                send_monotonic_ns=details["connect_monotonic_ns"],  # type: ignore[arg-type]
                failure_monotonic_ns=details["failure_monotonic_ns"],  # type: ignore[arg-type]
                request_bytes_may_have_been_sent=False,
                attempt_count=1,
                retry_performed=False,
            )
        except HarnessContractError as error:
            raise ControllerError("readiness failure event is invalid") from error
        return
    if event_name == "request_send_failed":
        minimal = {"track", "record_sha256"}
        transport = minimal | {"intent_id", "provenance"}
        detail_fields = set(details)
        if detail_fields != minimal and detail_fields != transport:
            raise ControllerError("request failure event fields are not closed")
        try:
            track = LiveTrack(details["track"])
        except (TypeError, ValueError) as error:
            raise ControllerError("request failure event track is invalid") from error
        if details["record_sha256"] is not None:
            raise ControllerError("failed request event cannot bind a record")
        if detail_fields == transport:
            intent_id = _require_sha256(
                "request failure intent_id", details["intent_id"]
            )
            try:
                RequestFailureProvenance.from_mapping(details["provenance"])
            except HarnessContractError as error:
                raise ControllerError("request failure provenance is invalid") from error
            if requests is not None:
                request = requests.get(track.value)
                if (
                    type(request) is not dict
                    or request.get("status") != "failed"
                    or request.get("intent_id") != intent_id
                ):
                    raise ControllerError(
                        "request failure provenance does not bind its durable intent"
                    )
        return
    if event_name == "request_send_intent":
        if set(details) != {"track", "intent_id"}:
            raise ControllerError("request intent event fields are not closed")
        if type(details["track"]) is not str:
            raise ControllerError("request intent track is invalid")
        try:
            LiveTrack(details["track"])
        except (TypeError, ValueError) as error:
            raise ControllerError("request intent track is invalid") from error
        _require_sha256("request intent_id", details["intent_id"])
        return
    if event_name == "request_send_complete":
        if set(details) != {"track", "record_sha256"}:
            raise ControllerError("request completion event fields are not closed")
        if type(details["track"]) is not str:
            raise ControllerError("request completion track is invalid")
        try:
            LiveTrack(details["track"])
        except (TypeError, ValueError) as error:
            raise ControllerError("request completion track is invalid") from error
        _require_sha256("request completion record_sha256", details["record_sha256"])
        return
    if event_name == "connection_close_failed":
        expected = {
            "readiness_nonce",
            "stage",
            "primary_failure",
            "failures",
        }
        if set(details) != expected:
            raise ControllerError("connection close event fields are not closed")
        _require_sha256("readiness_nonce", details["readiness_nonce"])
        if details["stage"] not in {"readiness_round", "request_finalization"}:
            raise ControllerError("connection close event stage is invalid")
        if details["primary_failure"] not in {
            None,
            "readiness_connect_failed",
            "request_processing",
            "request_send",
            "response_headers",
            "response_body",
        }:
            raise ControllerError("connection close primary failure is invalid")
        failures = details["failures"]
        if type(failures) is not list or not failures:
            raise ControllerError("connection close failures are invalid")
        tracks: set[str] = set()
        for failure in failures:
            if (
                type(failure) is not dict
                or set(failure) != {"track", "category"}
                or type(failure["track"]) is not str
                or failure["track"] not in {track.value for track in _TRACKS}
                or failure["track"] in tracks
                or failure["category"] not in {"close_raised", "close_unconfirmed"}
            ):
                raise ControllerError("connection close failure is not closed")
            tracks.add(failure["track"])


def _validate_lifecycle_history(
    events: Sequence[Mapping[str, object]],
    requests: Mapping[str, object],
) -> tuple[str | None, bool]:
    current_readiness: str | None = None
    readiness_complete = False
    seen_readiness_nonces: set[str] = set()
    poisoned_readiness_nonces: set[str] = set()
    lifecycle_readiness_poisoned = False
    replayed: dict[str, dict[str, object]] = {
        track.value: {"status": "not_attempted", "intent_id": None}
        for track in _TRACKS
    }
    freeze_epoch: str | None = None
    freeze_intents: dict[tuple[str, str], Mapping[str, object]] = {}
    freeze_bytes: dict[tuple[str, str], Mapping[str, object]] = {}
    freeze_terminals: dict[tuple[str, str], SourceCollectionStatus] = {}
    freeze_completed = False
    removals: dict[tuple[str, str, str], str] = {}
    creations: dict[tuple[str, str], str] = {}
    creation_ids: dict[tuple[str, str], str] = {}
    validations: dict[tuple[str, str], str] = {}
    network_connections: dict[tuple[str, str], tuple[str, Mapping[str, object]]] = {}
    for event in events:
        event_name = event["event"]
        details = event["details"]
        assert isinstance(event_name, str)
        assert isinstance(details, Mapping)
        if event_name in {
            "container_create_intent",
            "container_create_complete",
            "network_create_intent",
            "network_create_complete",
            "validator_create_intent",
            "validator_create_complete",
        }:
            kind = (
                "validator"
                if event_name.startswith("validator_")
                else "container"
                if event_name.startswith("container_")
                else "network"
            )
            key = (kind, str(details["name"]))
            if event_name.endswith("_intent"):
                if key in creations:
                    raise ControllerError("Docker creation intent is duplicated")
                creations[key] = "pending"
            else:
                if creations.get(key) != "pending":
                    raise ControllerError(
                        "Docker creation completion lacks its exact intent"
                    )
                creations[key] = "complete"
                creation_ids[key] = str(details["id"])
            continue
        if event_name in {"config_validate_intent", "config_validate_complete"}:
            key = (str(details["id"]), str(details["name"]))
            if event_name.endswith("_intent"):
                creation_key = ("validator", key[1])
                if (
                    creations.get(creation_key) != "complete"
                    or creation_ids.get(creation_key) != key[0]
                ):
                    raise ControllerError(
                        "validator execution lacks its exact created identity"
                    )
                if key in validations:
                    raise ControllerError("validator execution intent is duplicated")
                validations[key] = "pending"
            else:
                if validations.get(key) != "pending":
                    raise ControllerError(
                        "validator execution completion lacks its exact intent"
                    )
                validations[key] = "complete"
            continue
        if event_name in {"network_connect_intent", "network_connect_complete"}:
            key = (str(details["container_id"]), str(details["network_id"]))
            if event_name.endswith("_intent"):
                container_key = ("container", str(details["container_name"]))
                network_key = ("network", str(details["network_name"]))
                if (
                    creations.get(container_key) != "complete"
                    or creation_ids.get(container_key) != details["container_id"]
                    or creations.get(network_key) != "complete"
                    or creation_ids.get(network_key) != details["network_id"]
                ):
                    raise ControllerError(
                        "network connect intent lacks exact created identities"
                    )
                if key in network_connections:
                    raise ControllerError("network connect intent is duplicated")
                network_connections[key] = ("pending", details)
            else:
                transition = network_connections.get(key)
                if transition is None or transition[0] != "pending":
                    raise ControllerError(
                        "network connect completion lacks its exact intent"
                    )
                if dict(transition[1]) != dict(details):
                    raise ControllerError("network connect completion identity changed")
                network_connections[key] = ("complete", details)
            continue
        if event_name in {
            "container_remove_intent",
            "container_remove_complete",
            "network_remove_intent",
            "network_remove_complete",
        }:
            kind = "container" if event_name.startswith("container_") else "network"
            key = (kind, str(details["id"]), str(details["name"]))
            if event_name.endswith("_intent"):
                if key in removals:
                    raise ControllerError("Docker removal intent is duplicated")
                removals[key] = "pending"
            else:
                if removals.get(key) != "pending":
                    raise ControllerError(
                        "Docker removal completion lacks its exact intent"
                    )
                removals[key] = "complete"
            continue
        if event_name == "evidence_freeze_started":
            if freeze_epoch is not None:
                raise ControllerError("evidence freeze epoch may start only once")
            freeze_epoch = str(details["collection_epoch"])
        elif event_name == "source_collection_intent":
            if freeze_epoch is None or details["collection_epoch"] != freeze_epoch:
                raise ControllerError("source collection intent lacks its freeze epoch")
            if freeze_completed:
                raise ControllerError("source collection intent follows freeze completion")
            key = (str(details["track"]), str(details["source"]))
            if key in freeze_intents:
                raise ControllerError("source collection intent is duplicated")
            freeze_intents[key] = details
        elif event_name == "evidence_freeze_leg_bytes_persisted":
            if freeze_epoch is None or details["collection_epoch"] != freeze_epoch:
                raise ControllerError("frozen bytes lack their freeze epoch")
            if freeze_completed:
                raise ControllerError("frozen bytes follow freeze completion")
            key = (str(details["track"]), str(details["source"]))
            if (
                key not in freeze_intents
                or key in freeze_bytes
                or key in freeze_terminals
            ):
                raise ControllerError("frozen bytes lack one unfinished intent")
            freeze_bytes[key] = details
        elif event_name == "source_collection_terminal":
            if freeze_epoch is None or details["collection_epoch"] != freeze_epoch:
                raise ControllerError("source terminal lacks its freeze epoch")
            if freeze_completed:
                raise ControllerError("source terminal follows freeze completion")
            try:
                record = SourceCollectionStatus.from_mapping(details["record"])
            except HarnessContractError as error:
                raise ControllerError("source terminal record is invalid") from error
            key = (record.track, record.source)
            intent = freeze_intents.get(key)
            if intent is None or key in freeze_terminals:
                raise ControllerError("source terminal lacks one durable intent")
            if (
                intent["container_id"] != record.container_id
                or intent["container_name"] != record.container_name
            ):
                raise ControllerError("source terminal identity diverges from its intent")
            persisted = freeze_bytes.get(key)
            if record.status in {"copied", "malformed"}:
                if (
                    persisted is None
                    or persisted["byte_count"] != record.copied_byte_count
                    or persisted["sha256"] != record.copied_sha256
                ):
                    raise ControllerError(
                        "source terminal lacks its persisted-byte binding"
                    )
            elif persisted is not None:
                raise ControllerError(
                    "noncopied source terminal has a persisted-byte binding"
                )
            freeze_terminals[key] = record
        elif event_name == "evidence_freeze_complete":
            expected_keys = {
                (track.value, source)
                for track in _TRACKS
                for source in _FREEZE_SOURCES
            }
            if (
                freeze_epoch is None
                or details["collection_epoch"] != freeze_epoch
                or set(freeze_intents) != expected_keys
                or set(freeze_terminals) != expected_keys
                or freeze_completed
            ):
                raise ControllerError("evidence freeze completion is not terminal")
            ordered_records = [
                freeze_terminals[(track.value, source)].to_mapping()
                for track in _TRACKS
                for source in _FREEZE_SOURCES
            ]
            if details["records_sha256"] != _digest_bytes(
                canonical_json(ordered_records).encode("utf-8")
            ):
                raise ControllerError("evidence freeze terminal binding is invalid")
            promotable = all(
                status.status == "copied" for status in freeze_terminals.values()
            ) and all(
                request["status"] == "completed" for request in replayed.values()
            )
            if details["promotable"] is not promotable:
                raise ControllerError("evidence freeze promotability is inconsistent")
            freeze_completed = True
        elif event_name == "readiness_session_started":
            if lifecycle_readiness_poisoned:
                raise ControllerError(
                    "lifecycle readiness is poisoned; teardown or manual recovery is required"
                )
            readiness_nonce = str(details["readiness_nonce"])
            if readiness_nonce in seen_readiness_nonces:
                raise ControllerError("readiness session nonce reuse is forbidden")
            seen_readiness_nonces.add(readiness_nonce)
            current_readiness = readiness_nonce
            readiness_complete = False
        elif event_name in {"readiness_connect_failed", "readiness_connect_complete"}:
            if (
                current_readiness is None
                or details["readiness_nonce"] != current_readiness
            ):
                raise ControllerError(
                    "readiness event does not bind the current readiness session"
                )
            if current_readiness in poisoned_readiness_nonces:
                raise ControllerError("readiness session is permanently poisoned")
            readiness_complete = event_name == "readiness_connect_complete"
        elif event_name == "connection_close_failed":
            if details["readiness_nonce"] != current_readiness:
                raise ControllerError(
                    "connection close event does not bind the current readiness session"
                )
            if current_readiness in poisoned_readiness_nonces:
                raise ControllerError("readiness session is permanently poisoned")
            assert current_readiness is not None
            poisoned_readiness_nonces.add(current_readiness)
            lifecycle_readiness_poisoned = True
            readiness_complete = False
        elif event_name == "request_send_intent":
            if (
                current_readiness is None
                or current_readiness in poisoned_readiness_nonces
                or not readiness_complete
            ):
                raise ControllerError(
                    "request intent lacks a complete current readiness set"
                )
            track = str(details["track"])
            if replayed[track]["status"] != "not_attempted":
                raise ControllerError("request intent transition is invalid")
            replayed[track] = {
                "status": "intent_persisted",
                "intent_id": details["intent_id"],
            }
        elif event_name in {"request_send_complete", "request_send_failed"}:
            track = str(details["track"])
            if replayed[track]["status"] != "intent_persisted":
                raise ControllerError("request completion transition is invalid")
            replayed[track]["status"] = (
                "completed" if event_name == "request_send_complete" else "failed"
            )
    if replayed != requests:
        raise ControllerError("request events do not bind lifecycle request state")
    return current_readiness, readiness_complete


def _removal_transition(
    events: Sequence[Mapping[str, object]],
    kind: str,
    identity: Mapping[str, object],
) -> str:
    """Replay the durable transition for one exact Docker identity."""
    if kind not in {"container", "network"}:
        raise ControllerError("Docker removal kind is invalid")
    try:
        expected = DockerInventoryEntry.from_mapping(
            identity, kind, schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION
        )
    except HarnessContractError as error:
        raise ControllerError("Docker removal identity is invalid") from error
    intent_name = f"{kind}_remove_intent"
    complete_name = f"{kind}_remove_complete"
    transition = "unstarted"
    for event in events:
        if type(event) is not dict or event.get("event") not in {
            intent_name,
            complete_name,
        }:
            continue
        details = event.get("details")
        try:
            observed = DockerInventoryEntry.from_mapping(
                details, kind, schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION
            )
        except HarnessContractError as error:
            raise ControllerError("Docker removal history is invalid") from error
        if observed != expected:
            continue
        if event["event"] == intent_name:
            if transition != "unstarted":
                raise ControllerError("Docker removal intent is duplicated")
            transition = "pending"
        else:
            if transition != "pending":
                raise ControllerError(
                    "Docker removal completion lacks its exact intent"
                )
            transition = "complete"
    return transition


def _creation_transition(
    events: Sequence[Mapping[str, object]],
    kind: str,
    name: str,
) -> tuple[str, str | None]:
    """Replay one fixed-name Docker creation without doing discovery-by-delete."""
    if kind not in {"container", "network", "validator"}:
        raise ControllerError("Docker creation kind is invalid")
    inventory_kind = "container" if kind == "validator" else kind
    try:
        DockerInventoryEntry(
            inventory_kind,
            "0" * 64,
            name,
            DRIVER_TOPOLOGY_SCHEMA_VERSION,
        )
    except HarnessContractError as error:
        raise ControllerError("Docker creation name is invalid") from error
    prefix = "validator_create" if kind == "validator" else f"{kind}_create"
    transition = "unstarted"
    object_id: str | None = None
    for event in events:
        if type(event) is not dict or event.get("event") not in {
            f"{prefix}_intent",
            f"{prefix}_complete",
        }:
            continue
        details = event.get("details")
        if type(details) is not dict or details.get("name") != name:
            continue
        if event["event"].endswith("_intent"):
            if transition != "unstarted":
                raise ControllerError("Docker creation intent is duplicated")
            transition = "pending"
            continue
        if transition != "pending":
            raise ControllerError("Docker creation completion lacks its intent")
        try:
            object_id = DockerInventoryEntry.from_mapping(
                {"id": details.get("id"), "name": name},
                inventory_kind,
                schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION,
            ).object_id
        except HarnessContractError as error:
            raise ControllerError("Docker creation identity is invalid") from error
        transition = "complete"
    return transition, object_id


def create_lifecycle_journal(
    journal_path: Path,
    *,
    private_root: Path,
    repository_root: Path,
    docker_host: str,
    source_commit: str,
    execution_nonce: str,
    global_context: str,
) -> dict[str, object]:
    """Create durable private ownership state before the first Colima mutation."""
    repository = Path(os.path.abspath(repository_root))
    private = _require_contained(private_root, repository, "private root")
    journal = _require_contained(journal_path, private, "lifecycle journal")
    if journal.exists():
        raise ControllerError("lifecycle journal already exists; explicit recovery required")
    if type(docker_host) is not str or not docker_host.startswith("unix:///"):
        raise ControllerError("journal Docker host is invalid")
    if type(source_commit) is not str or re.fullmatch(r"[a-f0-9]{40}", source_commit) is None:
        raise ControllerError("journal source commit is invalid")
    _require_sha256("execution_nonce", execution_nonce)
    if type(global_context) is not str or not global_context:
        raise ControllerError("journal global Docker context is invalid")
    private.mkdir(parents=True, exist_ok=True)
    os.chmod(private, 0o700)
    value: dict[str, object] = {
        "schema_version": JOURNAL_SCHEMA,
        "repository_root": str(repository),
        "private_root": str(private),
        "docker_host": docker_host,
        "source_commit": source_commit,
        "execution_nonce": execution_nonce,
        "global_context_before": global_context,
        "phase": "prepared",
        "profile_created": False,
        "manifest_path": None,
        "manifest_sha256": None,
        "events": [],
        "requests": {
            track.value: {"status": "not_attempted", "intent_id": None}
            for track in _TRACKS
        },
    }
    value["binding_sha256"] = _journal_binding(value)
    _write_file(journal, _canonical_bytes(value), 0o600)
    return value


def load_lifecycle_journal(journal_path: Path) -> dict[str, object]:
    if journal_path.is_symlink() or not journal_path.is_file():
        raise ControllerError("lifecycle journal is missing or unsafe")
    value = _load_json_bytes(journal_path.read_bytes(), "lifecycle journal")
    expected = {
        "schema_version", "repository_root", "private_root", "docker_host",
        "source_commit", "execution_nonce", "global_context_before", "phase",
        "profile_created", "manifest_path", "manifest_sha256", "events",
        "requests", "binding_sha256",
    }
    if set(value) != expected or value["schema_version"] != JOURNAL_SCHEMA:
        raise ControllerError("lifecycle journal fields are not closed")
    if value["binding_sha256"] != _journal_binding(value):
        raise ControllerError("lifecycle journal binding does not match")
    repository = Path(str(value["repository_root"]))
    private = Path(str(value["private_root"]))
    _require_contained(private, repository, "private root")
    _require_contained(journal_path, private, "lifecycle journal")
    manifest_path = value["manifest_path"]
    manifest_sha = value["manifest_sha256"]
    if (manifest_path is None) != (manifest_sha is None):
        raise ControllerError("lifecycle private manifest binding is incomplete")
    if manifest_path is not None:
        if type(manifest_path) is not str or type(manifest_sha) is not str:
            raise ControllerError("lifecycle private manifest binding is invalid")
        bound_manifest = _require_contained(
            Path(manifest_path), private, "private manifest"
        )
        _require_sha256("lifecycle manifest_sha256", manifest_sha)
        if bound_manifest.is_symlink() or not bound_manifest.is_file() or _digest_file(bound_manifest) != manifest_sha:
            raise ControllerError("lifecycle private manifest binding does not match")
    requests = value["requests"]
    if type(requests) is not dict or set(requests) != {track.value for track in _TRACKS}:
        raise ControllerError("lifecycle request state is not closed")
    for request in requests.values():
        if (
            type(request) is not dict
            or set(request) != {"status", "intent_id"}
            or request["status"] not in {"not_attempted", "intent_persisted", "completed", "failed"}
        ):
            raise ControllerError("lifecycle request state is invalid")
        if request["status"] == "not_attempted":
            if request["intent_id"] is not None:
                raise ControllerError("unattempted request has an intent")
        else:
            _require_sha256("lifecycle request intent_id", request["intent_id"])
    events = value["events"]
    if type(events) is not list:
        raise ControllerError("lifecycle events are invalid")
    for index, event in enumerate(events, start=1):
        if type(event) is not dict or set(event) != {"sequence", "event", "details"}:
            raise ControllerError("lifecycle event fields are invalid")
        if event["sequence"] != index or type(event["event"]) is not str or type(event["details"]) is not dict:
            raise ControllerError("lifecycle event ordering is invalid")
        _validate_lifecycle_event_details(
            event["event"], event["details"], requests
        )
    freeze_start = next(
        (event for event in events if event["event"] == "evidence_freeze_started"),
        None,
    )
    if freeze_start is not None:
        details = freeze_start["details"]
        if details["execution_nonce"] != value["execution_nonce"]:
            raise ControllerError("evidence freeze nonce does not bind the lifecycle")
        if manifest_path is None:
            raise ControllerError("evidence freeze lacks a bound private manifest")
        bound_value = _load_json_bytes(
            Path(str(manifest_path)).read_bytes(), "freeze-bound private manifest"
        )
        _validate_manifest(bound_value)
        if details["run_id"] != bound_value["run_id"]:
            raise ControllerError("evidence freeze run ID does not bind the manifest")
    _validate_lifecycle_history(events, requests)
    return value


def _persist_journal(journal_path: Path, value: dict[str, object]) -> dict[str, object]:
    value["binding_sha256"] = _journal_binding(value)
    _write_file(journal_path, _canonical_bytes(value), 0o600)
    return value


def journal_event(
    journal_path: Path, event: str, details: Mapping[str, object]
) -> dict[str, object]:
    value = load_lifecycle_journal(journal_path)
    if type(event) is not str or not re.fullmatch(r"[a-z0-9_]+", event):
        raise ControllerError("lifecycle event name is invalid")
    if type(details) is not dict:
        raise ControllerError("lifecycle event details must be an object")
    requests = value["requests"]
    assert isinstance(requests, dict)
    _validate_lifecycle_event_details(event, details, requests)
    events = value["events"]
    assert isinstance(events, list)
    events.append({"sequence": len(events) + 1, "event": event, "details": dict(details)})
    _validate_lifecycle_history(events, requests)
    value["phase"] = event
    if event == "colima_attestation_complete":
        value["profile_created"] = True
    return _persist_journal(journal_path, value)


def _bind_journal_manifest(
    journal_path: Path, manifest_path: Path, manifest: dict[str, object]
) -> dict[str, object]:
    _validate_manifest(manifest)
    if manifest_path.is_symlink() or manifest_path.read_bytes() != _canonical_bytes(manifest):
        raise ControllerError("private manifest binding input is unsafe")
    value = load_lifecycle_journal(journal_path)
    private = Path(str(value["private_root"]))
    resolved = _require_contained(manifest_path, private, "private manifest")
    value["manifest_path"] = str(resolved)
    value["manifest_sha256"] = _digest_file(resolved)
    events = value["events"]
    assert isinstance(events, list)
    events.append(
        {
            "sequence": len(events) + 1,
            "event": "manifest_persisted",
            "details": {
                "run_id": manifest["run_id"],
                "manifest_sha256": value["manifest_sha256"],
            },
        }
    )
    value["phase"] = "manifest_persisted"
    return _persist_journal(journal_path, value)


def _complete_request_attempt(
    journal_path: Path,
    track: LiveTrack,
    *,
    success: bool,
    record_sha256: str | None,
    failure_provenance: RequestFailureProvenance | None = None,
) -> dict[str, object]:
    value = load_lifecycle_journal(journal_path)
    requests = value["requests"]
    assert isinstance(requests, dict)
    request = requests[track.value]
    assert isinstance(request, dict)
    if request["status"] != "intent_persisted":
        raise ControllerError("request completion lacks a durable intent")
    if success is not (record_sha256 is not None):
        raise ControllerError("request success/record SHA nullability mismatch")
    if success and failure_provenance is not None:
        raise ControllerError("successful request cannot carry failure provenance")
    if failure_provenance is not None and not isinstance(
        failure_provenance, RequestFailureProvenance
    ):
        raise ControllerError("request failure provenance is invalid")
    if record_sha256 is not None:
        _require_sha256("request record_sha256", record_sha256)
    request["status"] = "completed" if success else "failed"
    events = value["events"]
    assert isinstance(events, list)
    event = "request_send_complete" if success else "request_send_failed"
    details: dict[str, object] = {
        "track": track.value,
        "record_sha256": record_sha256,
    }
    if failure_provenance is not None:
        details.update(
            {
                "intent_id": request["intent_id"],
                "provenance": failure_provenance.to_mapping(),
            }
        )
    events.append(
        {"sequence": len(events) + 1, "event": event, "details": details}
    )
    _validate_lifecycle_history(events, requests)
    value["phase"] = event
    return _persist_journal(journal_path, value)


def _tool_identity_projection(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {"docker", "kind", "kubectl"}:
        raise ControllerError("verified tool identity set is not closed")
    projected: dict[str, object] = {}
    for name, record in sorted(value.items()):
        if type(name) is not str:
            raise ControllerError("verified tool identity name is invalid")
        if isinstance(record, Mapping):
            source = record
        else:
            source = {
                key: getattr(record, key)
                for key in (
                    "archive_sha256", "executable_sha256", "byte_size",
                    "version_output", "checksum_attestation",
                )
                if hasattr(record, key)
            }
        projected[name] = {
            key: source[key]
            for key in (
                "archive_sha256", "executable_sha256", "byte_size",
                "version_output", "checksum_attestation",
            )
            if key in source
        }
    _validate_public_provenance(projected, None)
    return projected


def _validate_public_provenance(
    tool_identities: Mapping[str, object],
    engine_provenance: Mapping[str, object] | None,
) -> None:
    tool_fields = {
        "archive_sha256", "executable_sha256", "byte_size", "version_output",
        "checksum_attestation",
    }
    versions = {
        "docker": "29.7.2",
        "kind": "v0.32.0",
        "kubectl": "v1.36.3",
    }
    if type(tool_identities) is not dict or set(tool_identities) != set(versions):
        raise ControllerError("public tool identity set is not closed")
    _reject_public_secrets(tool_identities)
    for name, marker in versions.items():
        record = tool_identities[name]
        if type(record) is not dict or set(record) != tool_fields:
            raise ControllerError("public tool identity fields are not closed")
        _require_sha256("tool archive_sha256", record["archive_sha256"])
        _require_sha256("tool executable_sha256", record["executable_sha256"])
        if type(record["byte_size"]) is not int or record["byte_size"] <= 0:
            raise ControllerError("public tool byte_size is invalid")
        version = record["version_output"]
        if (
            type(version) is not str
            or not version.strip()
            or len(version.encode("utf-8")) > 4096
            or marker not in version
        ):
            raise ControllerError("public tool version identity is invalid")
        if record["checksum_attestation"] not in {
            "locally_observed", "upstream_sidecar",
        }:
            raise ControllerError("public tool checksum attestation is invalid")
    if engine_provenance is None:
        return
    engine_fields = {
        "server_version", "api_version", "git_commit", "go_version", "os",
        "architecture", "kernel_version", "storage_driver", "cgroup_driver",
        "cgroup_version",
    }
    if type(engine_provenance) is not dict or set(engine_provenance) != engine_fields:
        raise ControllerError("public engine provenance fields are not closed")
    _reject_public_secrets(engine_provenance)
    if any(
        type(value) is not str
        or not value.strip()
        or len(value.encode("utf-8")) > 4096
        for value in engine_provenance.values()
    ):
        raise ControllerError("public engine provenance values are invalid")
    if (
        engine_provenance["os"] != "linux"
        or engine_provenance["architecture"] != "arm64"
    ):
        raise ControllerError("public engine provenance is not linux/arm64")


def claim_request_attempt(
    journal_path: Path,
    track: LiveTrack,
    *,
    readiness_nonce: str | None = None,
) -> dict[str, object]:
    if not isinstance(track, LiveTrack):
        raise ControllerError("request track is invalid")
    value = load_lifecycle_journal(journal_path)
    if readiness_nonce is None:
        raise ControllerError("request intent lacks fresh readiness authorization")
    readiness_nonce = _require_sha256("readiness_nonce", readiness_nonce)
    events = value["events"]
    assert isinstance(events, list)
    current_readiness, readiness_complete = _validate_lifecycle_history(
        events, value["requests"]  # type: ignore[arg-type]
    )
    if current_readiness != readiness_nonce or not readiness_complete:
        raise ControllerError("request intent lacks a complete fresh readiness set")
    requests = value["requests"]
    assert isinstance(requests, dict)
    request = requests[track.value]
    assert isinstance(request, dict)
    if request["status"] != "not_attempted":
        raise ControllerError("request was already attempted or remains ambiguous")
    intent_id = secrets.token_hex(32)
    request.update({"status": "intent_persisted", "intent_id": intent_id})
    events.append(
        {
            "sequence": len(events) + 1,
            "event": "request_send_intent",
            "details": {"track": track.value, "intent_id": intent_id},
        }
    )
    _validate_lifecycle_history(events, requests)
    value["phase"] = "request_send_intent"
    _persist_journal(journal_path, value)
    return {"track": track.value, "status": "intent_persisted", "intent_id": intent_id}


def recovery_plan(journal: Mapping[str, object]) -> dict[str, object]:
    events = journal.get("events")
    if type(events) is not list:
        raise ControllerError("recovery journal events are invalid")
    last = "prepared" if not events else events[-1].get("event")
    return {
        "last_event": last,
        "fail_closed": True,
        "resume_mode": "exact_recorded_objects_only",
        "request_replay_forbidden": any(
            isinstance(item, dict) and item.get("status") != "not_attempted"
            for item in (journal.get("requests") or {}).values()
        ) if isinstance(journal.get("requests"), dict) else True,
    }


def validate_request_journal(
    records: Sequence[Mapping[str, object]],
    journal: Mapping[str, object],
    *,
    require_all: bool,
) -> None:
    if type(journal) is not dict:
        raise ControllerError("request lifecycle journal is invalid")
    requests = journal.get("requests")
    events = journal.get("events")
    if type(requests) is not dict or type(events) is not list:
        raise ControllerError("request lifecycle journal fields are invalid")
    record_by_track: dict[str, Mapping[str, object]] = {}
    for record in records:
        _request_closed(record)
        track = record["track"]
        assert isinstance(track, str)
        if track in record_by_track:
            raise ControllerError("request journal has duplicate request records")
        record_by_track[track] = record
    expected_tracks = {track.value for track in _TRACKS}
    if require_all and set(record_by_track) != expected_tracks:
        raise ControllerError("request journal does not cover all fixed tracks")
    if not set(record_by_track).issubset(expected_tracks):
        raise ControllerError("request journal contains an unknown track")
    completions: dict[str, list[Mapping[str, object]]] = {}
    for event in events:
        if not isinstance(event, Mapping) or event.get("event") != "request_send_complete":
            continue
        details = event.get("details")
        if type(details) is not dict or set(details) != {"track", "record_sha256"}:
            raise ControllerError("request completion event fields are not closed")
        track = details["track"]
        if type(track) is not str:
            raise ControllerError("request completion track is invalid")
        completions.setdefault(track, []).append(details)
    if set(completions) != set(record_by_track):
        raise ControllerError("request records and successful completions do not match")
    for track, record in record_by_track.items():
        events_for_track = completions[track]
        if len(events_for_track) != 1:
            raise ControllerError("request record must have exactly one successful completion")
        recorded_sha = events_for_track[0]["record_sha256"]
        _require_sha256("request completion record SHA", recorded_sha)
        if recorded_sha != _digest_bytes(_canonical_bytes(record)):
            raise ControllerError("request record SHA does not match journal completion")
        request_state = requests.get(track)
        if (
            type(request_state) is not dict
            or request_state.get("status") != "completed"
            or type(request_state.get("intent_id")) is not str
            or _HEX.fullmatch(str(request_state["intent_id"])) is None
        ):
            raise ControllerError("request record lacks completed journal state")


def stage_build_context(repository_root: Path, staging_root: Path) -> dict[str, object]:
    """Copy only Dockerfile-required files and attest the complete context."""
    repository = Path(os.path.abspath(repository_root))
    if staging_root.is_symlink():
        raise ControllerError("staged Docker build context cannot be a symbolic link")
    if staging_root.exists() and any(staging_root.iterdir()):
        raise ControllerError("staged Docker build context would clobber existing data")
    staging_root.mkdir(parents=True, exist_ok=True)
    os.chmod(staging_root, 0o700)
    hashes: dict[str, str] = {}
    for relative in _BUILD_CONTEXT_FILES:
        source = repository / relative
        _require_contained(source, repository, "Docker build input")
        if source.is_symlink() or not source.is_file():
            raise ControllerError(f"closed Docker build input is missing: {relative}")
        destination = staging_root / relative
        _require_contained(destination, staging_root, "staged Docker build input")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o400)
        hashes[relative] = _digest_file(destination)
    context_sha = _digest_bytes(canonical_json(hashes).encode("utf-8"))
    return {"files": list(_BUILD_CONTEXT_FILES), "file_sha256": hashes, "context_sha256": context_sha}


def driver_bootstrap_sha256(attestation: Mapping[str, object]) -> str:
    """Return the exact staged request-driver module digest."""
    if type(attestation) is not dict:
        raise ControllerError("build-context attestation is invalid")
    hashes = attestation.get("file_sha256")
    if type(hashes) is not dict:
        raise ControllerError("build-context file hashes are unavailable")
    digest = hashes.get("src/kil/v3b1_request_driver.py")
    _require_sha256("request-driver bootstrap", digest)
    return digest


def validate_image_architecture(value: Mapping[str, object]) -> None:
    if type(value) is not dict or set(value) != {"Os", "Architecture"}:
        raise ControllerError("image architecture inspection fields are not closed")
    if value != {"Os": "linux", "Architecture": "arm64"}:
        raise ControllerError("image architecture is not exact linux/arm64")


def _validate_container_labels(
    actual: object,
    immutable: object,
    managed: Mapping[str, str],
) -> None:
    image_labels = {} if immutable is None else immutable
    if (
        type(actual) is not dict
        or type(image_labels) is not dict
        or type(managed) is not dict
        or any(
            type(key) is not str or type(value) is not str
            for labels in (actual, image_labels, managed)
            for key, value in labels.items()
        )
    ):
        raise ControllerError("container labels are not closed string maps")
    if any(key.startswith("kil.v3b1.") for key in image_labels):
        raise ControllerError(
            "immutable image label conflict with reserved kil.v3b1. namespace"
        )
    conflicts = {
        key
        for key, value in managed.items()
        if key in image_labels and image_labels[key] != value
    }
    if conflicts:
        raise ControllerError("immutable image label conflicts with managed label")
    expected = {**image_labels, **managed}
    if actual != expected:
        raise ControllerError("container labels are not the exact image/runtime merge")


def validate_container_attestation(
    actual: Mapping[str, object], expected: Mapping[str, object]
) -> dict[str, object]:
    actual_fields = {
        "id", "name", "image_id", "user", "readonly_rootfs", "cap_drop",
        "security_opt", "nano_cpus", "memory", "memory_swap", "pids_limit",
        "restart_policy", "stop_timeout", "log_driver", "log_options", "tmpfs",
        "mounts", "networks", "network_aliases", "port_bindings",
        "published_ports", "platform", "entrypoint", "command", "environment",
        "state", "stdin_open", "tty", "healthcheck", "privileged",
        "network_mode", "pid_mode", "ipc_mode", "uts_mode", "userns_mode",
    }
    expected_fields = {
        "name", "role", "track", "image_id", "networks", "config_path",
        "config_sha256", "gateway_port", "required_aliases",
        "driver_definition", "required_state", "primary_network",
    }
    if type(actual) is not dict or set(actual) != actual_fields:
        raise ControllerError("container attestation fields are not closed")
    if type(expected) is not dict or set(expected) != expected_fields:
        raise ControllerError("expected container attestation is not closed")
    if type(actual["id"]) is not str or _HEX.fullmatch(actual["id"]) is None:
        raise ControllerError("container ID attestation is invalid")
    if actual["name"] != expected["name"] or actual["image_id"] != expected["image_id"]:
        raise ControllerError("container identity/image attestation failed")
    if actual["user"] != "65532:65532" or actual["readonly_rootfs"] is not True:
        raise ControllerError("container non-root/read-only attestation failed")
    if actual["cap_drop"] != ["ALL"] or actual["security_opt"] != ["no-new-privileges"]:
        raise ControllerError("container capability/security attestation failed")
    if (
        actual["nano_cpus"] != 500_000_000
        or actual["memory"] != 268_435_456
        or actual["memory_swap"] != 268_435_456
        or actual["pids_limit"] != 128
    ):
        raise ControllerError("container CPU/memory/pids resource attestation failed")
    if actual["restart_policy"] != "no" or actual["stop_timeout"] != 10:
        raise ControllerError("container restart/stop policy attestation failed")
    if actual["privileged"] is not False:
        raise ControllerError("container privileged mode is forbidden")
    if (
        type(expected["primary_network"]) is not str
        or not expected["primary_network"]
        or type(actual["network_mode"]) is not str
        or actual["network_mode"] != expected["primary_network"]
    ):
        raise ControllerError("container primary network mode attestation failed")
    if any(
        type(actual[field]) is not str or actual[field] != ""
        for field in ("pid_mode", "ipc_mode", "uts_mode", "userns_mode")
    ):
        raise ControllerError("container host namespace mode is forbidden")
    if actual["log_driver"] != "json-file" or actual["log_options"] != {"max-file": "1", "max-size": "1m"}:
        raise ControllerError("container bounded log attestation failed")
    role = expected["role"]
    if role not in {"authz", "target", "envoy", "driver"}:
        raise ControllerError("container role attestation is invalid")
    expected_tmpfs = {
        "/tmp": "rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700"
    }
    if role in {"authz", "target"}:
        expected_tmpfs["/evidence"] = "rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700"
    if actual["tmpfs"] != expected_tmpfs:
        raise ControllerError("container tmpfs attestation failed")
    mounts = actual["mounts"]
    if role == "driver":
        if mounts != [] or expected["config_path"] is not None or expected["config_sha256"] is not None:
            raise ControllerError("driver must not have a config mount")
    else:
        expected_destination = (
            "/etc/envoy/envoy.json"
            if role == "envoy"
            else f"/config/{role}.json"
        )
        if (
            type(mounts) is not list
            or len(mounts) != 1
            or type(mounts[0]) is not dict
            or mounts[0].get("source") != expected["config_path"]
            or mounts[0].get("destination") != expected_destination
            or mounts[0].get("rw") is not False
        ):
            raise ControllerError("container read-only config mount attestation failed")
    if actual["networks"] != sorted(expected["networks"]):  # type: ignore[arg-type]
        raise ControllerError("container per-track network attestation failed")
    aliases = actual["network_aliases"]
    required_aliases = expected["required_aliases"]
    if (
        type(aliases) is not dict
        or set(aliases) != set(actual["networks"])  # type: ignore[arg-type]
        or type(required_aliases) is not dict
        or set(required_aliases) != set(actual["networks"])  # type: ignore[arg-type]
    ):
        raise ControllerError("container network aliases are not closed")
    for network, values in aliases.items():
        required = required_aliases[network]
        if (
            type(values) is not list
            or any(type(value) is not str or not value for value in values)
            or len(values) != len(set(values))
            or type(required) is not list
            or any(type(value) is not str or not value for value in required)
            or not set(required).issubset(values)
        ):
            raise ControllerError("container network aliases are invalid")
    if actual["platform"] != PLATFORM:
        raise ControllerError("container architecture attestation failed")
    environment = actual["environment"]
    if (
        type(environment) is not list
        or not environment
        or any(type(item) is not str or "=" not in item for item in environment)
        or len({item.split("=", 1)[0] for item in environment}) != len(environment)
    ):
        raise ControllerError("container environment attestation is invalid")
    if role == "authz":
        expected_entrypoint = []
        expected_command = [
            "python", "-c", _AUTHZ_BOOTSTRAP, "--config", "/config/authz.json",
        ]
    elif role == "target":
        expected_entrypoint = []
        expected_command = [
            "python", "-c", _TARGET_BOOTSTRAP, "--config", "/config/target.json",
        ]
    elif role == "envoy":
        expected_entrypoint = ["/usr/local/bin/envoy"]
        expected_command = [
            "--config-path", "/etc/envoy/envoy.json", "--disable-hot-restart",
            "--concurrency", "1",
        ]
    else:
        expected_entrypoint = []
        expected_command = [
            "python", "-m", "kil.v3b1_request_driver", "--track",
            str(expected["track"]), "--endpoint", "envoy:8080",
        ]
    if actual["entrypoint"] != expected_entrypoint or actual["command"] != expected_command:
        raise ControllerError("container executed process attestation failed")
    published_ports = actual["published_ports"]
    live_ports_empty = published_ports is None or (
        type(published_ports) is dict
        and all(
            type(port) is str and bindings in (None, [])
            for port, bindings in published_ports.items()
        )
    )
    if (
        expected["gateway_port"] is not None
        or actual["port_bindings"] != {}
        or not live_ports_empty
    ):
        raise ControllerError("container host publication is forbidden")
    required_state = expected["required_state"]
    if required_state is not None and actual["state"] != required_state:
        raise ControllerError("container lifecycle state attestation failed")
    if actual["tty"] is not False:
        raise ControllerError("container TTY attestation failed")
    if role == "driver":
        definition = expected["driver_definition"]
        if (
            type(definition) is not dict
            or definition.get("track") != expected["track"]
            or definition.get("image_id") != expected["image_id"]
            or definition.get("endpoint") != {"host": "envoy", "port": 8080}
            or definition.get("runtime_policy") != DRIVER_RUNTIME_POLICY
            or actual["state"] != "created"
            or actual["stdin_open"] is not True
            or actual["healthcheck"] != "disabled"
        ):
            raise ControllerError("driver runtime definition attestation failed")
    elif (
        expected["driver_definition"] is not None
        or actual["stdin_open"] is not False
        or actual["healthcheck"] not in {None, "disabled", "configured"}
    ):
        raise ControllerError("service runtime definition attestation failed")
    return dict(actual)


def _container_attestation_matches(
    recorded: object,
    current: object,
    *,
    allow_stopped: bool,
) -> bool:
    """Compare an owned container while totalizing a controlled service stop."""
    if current == recorded:
        return True
    if (
        not allow_stopped
        or type(recorded) is not dict
        or type(current) is not dict
        or set(recorded) != set(current)
        or recorded.get("role") == "driver"
    ):
        return False
    recorded_runtime = recorded.get("runtime_attestation")
    current_runtime = current.get("runtime_attestation")
    if (
        type(recorded_runtime) is not dict
        or type(current_runtime) is not dict
        or set(recorded_runtime) != set(current_runtime)
        or recorded_runtime.get("state") != "running"
        or current_runtime.get("state") not in {"exited", "dead"}
    ):
        return False
    recorded_without_runtime = {
        key: value for key, value in recorded.items() if key != "runtime_attestation"
    }
    current_without_runtime = {
        key: value for key, value in current.items() if key != "runtime_attestation"
    }
    if recorded_without_runtime != current_without_runtime:
        return False
    return {
        key: value for key, value in recorded_runtime.items() if key != "state"
    } == {
        key: value for key, value in current_runtime.items() if key != "state"
    }


def _normalize_inspected_tmpfs(value: object) -> dict[str, str]:
    if type(value) is not dict or any(type(path) is not str or type(options) is not str for path, options in value.items()):
        raise ControllerError("container tmpfs inspection is invalid")
    normalized: dict[str, str] = {}
    canonical = "rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700"
    for path, options in value.items():
        parts = options.split(",")
        flags = {part for part in parts if "=" not in part}
        pairs = dict(part.split("=", 1) for part in parts if "=" in part)
        if (
            flags != {"rw", "noexec", "nosuid", "nodev"}
            or pairs.get("size") not in {"16m", "16777216"}
            or pairs.get("uid") != "65532"
            or pairs.get("gid") != "65532"
            or pairs.get("mode") not in {"0700", "700", "448"}
            or set(pairs) != {"size", "uid", "gid", "mode"}
        ):
            raise ControllerError("container tmpfs options do not match the closed policy")
        normalized[path] = canonical
    return normalized


def _repository_from_tag(tag: str) -> str:
    if "@" in tag or ":" not in tag.rsplit("/", 1)[-1]:
        raise ControllerError("image source must be an explicit mutable tag")
    return _canonical_repository(tag.rsplit(":", 1)[0])


def _canonical_repository(repository: str) -> str:
    parts = repository.split("/")
    if len(parts) == 1:
        return f"docker.io/library/{repository}"
    if "." not in parts[0] and ":" not in parts[0] and parts[0] != "localhost":
        return f"docker.io/{repository}"
    if parts[0] == "index.docker.io":
        parts[0] = "docker.io"
    return "/".join(parts)


def select_registry_digest(tag: str, inspect_output: str) -> str:
    """Select the one exact same-repository digest returned for a tag."""
    repository = _repository_from_tag(tag)
    try:
        values = json.loads(inspect_output, object_pairs_hook=_closed_object)
    except (json.JSONDecodeError, ControllerError) as error:
        raise ControllerError("image inspection did not return registry digests") from error
    if type(values) is not list or not values or any(type(item) is not str for item in values):
        raise ControllerError("image inspection did not return registry digests")
    matches = []
    for item in values:
        match = _ANY_DIGEST_REF.fullmatch(item)
        if match is not None and _canonical_repository(match.group("repository")) == repository:
            matches.append(f"{repository}@sha256:{match.group('digest')}")
    if not matches:
        if any(_ANY_DIGEST_REF.fullmatch(item) is not None for item in values):
            raise ControllerError("registry digest repository does not match source")
        raise ControllerError("image inspection did not return a registry digest")
    if len(set(matches)) != 1:
        raise ControllerError("image tag resolved to multiple registry digests")
    return matches[0]


def parse_colima_profiles(output: str) -> tuple[dict[str, object], ...]:
    """Parse Colima's exact closed list-record shape without discarding resources."""
    try:
        raw = json.loads(output, object_pairs_hook=_closed_object)
    except (json.JSONDecodeError, ControllerError):
        try:
            raw = [
                json.loads(line, object_pairs_hook=_closed_object)
                for line in output.splitlines()
                if line.strip()
            ]
        except (json.JSONDecodeError, ControllerError) as error:
            raise ControllerError("Colima profile list is not closed JSON") from error
    if type(raw) is dict:
        raw = [raw]
    if type(raw) is not list:
        raise ControllerError("Colima profile list must be a JSON array")
    records = []
    for item in raw:
        expected_fields = {
            "name", "status", "arch", "cpus", "memory", "disk", "runtime",
        }
        if type(item) is not dict or set(item) != expected_fields:
            raise ControllerError("Colima profile fields are not closed")
        if any(
            type(item[name]) is not str or not item[name]
            for name in ("name", "status", "arch", "runtime")
        ) or any(
            type(item[name]) is not int or item[name] <= 0
            for name in ("cpus", "memory", "disk")
        ):
            raise ControllerError("Colima profile values are invalid")
        records.append(dict(item))
    return tuple(records)


def validate_colima_profiles(records: Sequence[Mapping[str, object]]) -> None:
    for record in records:
        if record.get("status", "").lower() == "running" and record.get("name") != LAB_IDENTITY:
            raise ControllerError("a non-dedicated Colima profile is running")


def _colima_cpu_count(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ControllerError("dedicated Colima CPUs are invalid")
    return value


def _colima_size_gib(name: str, value: object) -> int:
    gib = 1024 ** 3
    if type(value) is not int or value <= 0 or value % gib:
        raise ControllerError(f"dedicated Colima {name} is invalid")
    return value // gib


def validate_dedicated_colima_profile(
    record: Mapping[str, object],
) -> dict[str, object]:
    fields = {"name", "status", "arch", "cpus", "memory", "disk", "runtime"}
    if type(record) is not dict or set(record) != fields:
        raise ControllerError("dedicated Colima profile fields are not closed")
    canonical = {
        "name": record["name"],
        "status": record["status"],
        "arch": record["arch"],
        "cpus": _colima_cpu_count(record["cpus"]),
        "memory": _colima_size_gib("memory", record["memory"]),
        "disk": _colima_size_gib("disk", record["disk"]),
        "runtime": record["runtime"],
    }
    if canonical != {
        "name": LAB_IDENTITY,
        "status": "Running",
        "arch": "aarch64",
        "cpus": 4,
        "memory": 8,
        "disk": 60,
        "runtime": "docker",
    }:
        raise ControllerError("dedicated Colima profile does not match exact resources")
    return canonical


def _parse_saved_colima_config(payload: bytes, staging_root: Path) -> dict[str, object]:
    if len(payload) > 64 * 1024:
        raise ControllerError("saved Colima config is not bounded")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ControllerError("saved Colima config is not UTF-8") from error
    logical_lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    logical_text = "\n".join(logical_lines)
    if any(token in logical_text for token in ("\t", "&", "*", "!")):
        raise ControllerError("saved Colima config contains unsupported YAML features")
    required_top_level = {
        "cpu": "cpu: 4",
        "memory": "memory: 8",
        "disk": "disk: 60",
        "arch": "arch: aarch64",
        "runtime": "runtime: docker",
        "vm_type": "vmType: vz",
        "mount_type": "mountType: virtiofs",
        "mount_inotify": "mountInotify: false",
        "rosetta": "rosetta: false",
        "binfmt": "binfmt: false",
        "ssh_config": "sshConfig: false",
        "forward_agent": "forwardAgent: false",
        "nested_virtualization": "nestedVirtualization: false",
        "port_forwarder": "portForwarder: ssh",
    }
    for name, expected in required_top_level.items():
        if logical_lines.count(expected) != 1:
            raise ControllerError(f"saved Colima config {name} is not exact")

    def section(header: str) -> list[str]:
        if logical_lines.count(header) != 1:
            raise ControllerError(f"saved Colima config {header} section is not exact")
        start = logical_lines.index(header) + 1
        end = start
        while end < len(logical_lines) and logical_lines[end].startswith(" "):
            end += 1
        return logical_lines[start:end]

    kubernetes = section("kubernetes:")
    if kubernetes.count("  enabled: false") != 1:
        raise ControllerError("saved Colima Kubernetes configuration is not disabled")
    required_network = {
        "  mode: shared", "  address: false", "  hostAddresses: false",
        "  preferredRoute: false",
    }
    network = section("network:")
    if any(network.count(expected) != 1 for expected in required_network):
        raise ControllerError("saved Colima network configuration is not restricted")
    mounts = section("mounts:")
    locations = [line for line in mounts if line.startswith("  - location: ")]
    if len(locations) != 1:
        raise ControllerError("saved Colima config staging mount is not exact")
    if len([line for line in mounts if line.startswith("  - ")]) != 1:
        raise ControllerError("saved Colima config includes an unexpected mount")
    location = locations[0]
    recorded_location = Path(location.removeprefix("  - location: "))
    if (
        not recorded_location.is_absolute()
        or recorded_location != staging_root
    ):
        raise ControllerError("saved Colima config staging mount is not exact")
    index = mounts.index(location)
    mount_item = mounts[index:]
    if mount_item.count("    writable: false") != 1:
        raise ControllerError("saved Colima staging mount is not read-only")
    return {
        "runtime": "docker",
        "kubernetes": False,
        "vm_type": "vz",
        "arch": "aarch64",
        "cpus": 4,
        "memory_gib": 8,
        "disk_gib": 60,
        "mount": str(staging_root),
        "mount_type": "virtiofs",
        "mount_writable": False,
    }
def _track_slug(track: LiveTrack) -> str:
    return track.value.replace("_", "-")


def _runtime_root(root: Path, manifest: Mapping[str, object]) -> Path:
    execution_nonce = _require_sha256(
        "runtime execution nonce", manifest.get("execution_nonce")
    )
    return (
        root
        / ".tools/v3b1-staging"
        / execution_nonce
        / str(manifest["run_id"])
    )


def _segment_definitions() -> list[dict[str, object]]:
    """Return the six canonical, name-independent internal segments."""
    return [
        {
            "schema_version": "kil.v3b1-segment-definition.v1",
            "track": track.value,
            "segment": segment,
            "internal": True,
        }
        for track in _TRACKS
        for segment in ("frontend", "backend")
    ]


def _driver_definitions(
    *,
    kil_image_id: str,
    bootstrap_sha256: str,
    segment_definitions: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Return three definitions whose inputs never include runtime identity."""
    frontend_by_track = {
        str(item["track"]): _digest_bytes(_canonical_bytes(dict(item)))
        for item in segment_definitions
        if item.get("segment") == "frontend"
    }
    if set(frontend_by_track) != {track.value for track in _TRACKS}:
        raise ControllerError("frontend segment definitions are incomplete")
    return [
        driver_definition(
            track=track.value,
            image_id=kil_image_id,
            bootstrap_sha256=bootstrap_sha256,
            frontend_segment_sha256=frontend_by_track[track.value],
        )
        for track in _TRACKS
    ]


def _manifest_identity(
    profile: V3BProfile,
    *,
    profile_sha256: str,
    python_image_digest: str,
    envoy_image_digest: str,
    envoy_image_id: str,
    kil_image_id: str,
    kil_archive_sha256: str,
    source_commit: str,
    execution_nonce: str,
    dockerfile_sha256: str,
    dockerignore_sha256: str,
    build_context_sha256: str,
    segment_definitions: Sequence[Mapping[str, object]],
    driver_definitions: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "kil.v3b1-content-identity.v3",
        "profile_sha256": profile_sha256,
        "colima_profile": profile.colima_profile,
        "docker_endpoint": {
            "transport": "unix",
            "logical_locator": "colima_profile_socket",
            "profile": profile.colima_profile,
        },
        "platform": PLATFORM,
        "source_commit": source_commit,
        "execution_nonce_sha256": _digest_bytes(execution_nonce.encode("ascii")),
        "dockerfile_sha256": dockerfile_sha256,
        "dockerignore_sha256": dockerignore_sha256,
        "build_context_sha256": build_context_sha256,
        "python_image_digest": python_image_digest,
        "envoy_image_digest": envoy_image_digest,
        "envoy_image_id": envoy_image_id,
        "kil_image_id": kil_image_id,
        "kil_archive_sha256": kil_archive_sha256,
        "request_id": REQUEST_ID,
        "driver_endpoint": {
            "transport": "tcp",
            "host": "envoy",
            "port": 8080,
        },
        "segment_definitions": [dict(item) for item in segment_definitions],
        "driver_definition_sha256": [
            {
                "track": item["track"],
                "sha256": _digest_bytes(canonical_record(item)),
            }
            for item in driver_definitions
        ],
    }


def _manifest_runtime_projection(
    *,
    identity_sha256: str,
    kil_image_id: str,
    envoy_image_digest: str,
    driver_definition_sha256: Sequence[Mapping[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """Derive the private runtime projection after content identity exists."""
    _require_sha256("runtime projection content identity", identity_sha256)
    suffix = identity_sha256[:12]
    driver_hashes = {
        str(item.get("track")): _require_sha256(
            "runtime projection driver definition", item.get("sha256")
        )
        for item in driver_definition_sha256
        if type(item) is dict
    }
    if set(driver_hashes) != {track.value for track in _TRACKS}:
        raise ControllerError("runtime projection driver definitions are incomplete")
    networks: list[dict[str, object]] = []
    tracks: list[dict[str, object]] = []
    containers: list[dict[str, object]] = []
    endpoint = {"transport": "tcp", "host": "envoy", "port": 8080}
    for track in _TRACKS:
        slug = _track_slug(track)
        names = {
            role: f"kil-v3b1-{role}-{slug}-{suffix}"
            for role in ("authz", "target", "envoy", "driver")
        }
        network_names = {
            segment: f"kil-v3b1-{segment}-{slug}-{suffix}"
            for segment in ("frontend", "backend")
        }
        for segment in ("frontend", "backend"):
            networks.append(
                {
                    "track": track.value,
                    "segment": segment,
                    "name": network_names[segment],
                }
            )
        tracks.append(
            {
                "track": track.value,
                "driver_endpoint": dict(endpoint),
                "authz_container": names["authz"],
                "target_container": names["target"],
                "envoy_container": names["envoy"],
                "driver_container": names["driver"],
                "frontend_network": network_names["frontend"],
                "backend_network": network_names["backend"],
                "decision_source": f"{track.value}/decisions.jsonl",
                "target_source": f"{track.value}/targets.jsonl",
                "envoy_source": f"{track.value}/envoy.stdout.jsonl",
                "driver_definition_sha256": driver_hashes[track.value],
            }
        )
        for role in ("authz", "target", "envoy", "driver"):
            containers.append(
                {
                    "name": names[role],
                    "role": role,
                    "track": track.value,
                    "image": (
                        envoy_image_digest if role == "envoy" else kil_image_id
                    ),
                    "command_definition_sha256": (
                        driver_hashes[track.value] if role == "driver" else None
                    ),
                }
            )
    return {
        "networks": networks,
        "tracks": tracks,
        "containers": containers,
    }


def create_run_manifest(
    profile: V3BProfile,
    *,
    profile_sha256: str,
    python_image_digest: str,
    envoy_image_digest: str,
    envoy_image_id: str | None = None,
    kil_image_id: str,
    kil_archive_sha256: str,
    driver_bootstrap_sha256: str,
    docker_host: str,
    source_commit: str = "0" * 40,
    source_clean: bool = True,
    execution_nonce: str = "0" * 64,
    dockerfile_sha256: str = "0" * 64,
    dockerignore_sha256: str = "0" * 64,
    build_context_sha256: str = "0" * 64,
) -> dict[str, object]:
    """Create a manifest whose run identifier binds its immutable inputs."""
    if not isinstance(profile, V3BProfile) or profile.colima_profile != LAB_IDENTITY:
        raise ControllerError("profile must be the closed V3B profile")
    _require_sha256("profile_sha256", profile_sha256)
    _require_digest_ref("python_image_digest", python_image_digest)
    _require_digest_ref("envoy_image_digest", envoy_image_digest)
    if envoy_image_id is None:
        envoy_image_id = "sha256:" + envoy_image_digest.rsplit(":", 1)[1]
    if _IMAGE_ID.fullmatch(envoy_image_id) is None:
        raise ControllerError("envoy_image_id must be an immutable image ID")
    if _IMAGE_ID.fullmatch(kil_image_id) is None:
        raise ControllerError("kil_image_id must be an immutable image ID")
    _require_sha256("kil_archive_sha256", kil_archive_sha256)
    _require_sha256("driver_bootstrap_sha256", driver_bootstrap_sha256)
    if type(docker_host) is not str or not docker_host.startswith("unix:///"):
        raise ControllerError("docker_host must be an explicit Unix socket")
    if (
        type(source_commit) is not str
        or re.fullmatch(r"[a-f0-9]{40}", source_commit) is None
        or source_clean is not True
    ):
        raise ControllerError("source must be a clean recorded Git commit")
    _require_sha256("execution_nonce", execution_nonce)
    _require_sha256("dockerfile_sha256", dockerfile_sha256)
    _require_sha256("dockerignore_sha256", dockerignore_sha256)
    _require_sha256("build_context_sha256", build_context_sha256)
    segments = _segment_definitions()
    drivers = _driver_definitions(
        kil_image_id=kil_image_id,
        bootstrap_sha256=driver_bootstrap_sha256,
        segment_definitions=segments,
    )
    identity = _manifest_identity(
        profile,
        profile_sha256=profile_sha256,
        python_image_digest=python_image_digest,
        envoy_image_digest=envoy_image_digest,
        envoy_image_id=envoy_image_id,
        kil_image_id=kil_image_id,
        kil_archive_sha256=kil_archive_sha256,
        source_commit=source_commit,
        execution_nonce=execution_nonce,
        dockerfile_sha256=dockerfile_sha256,
        dockerignore_sha256=dockerignore_sha256,
        build_context_sha256=build_context_sha256,
        segment_definitions=segments,
        driver_definitions=drivers,
    )
    identity_sha256 = _digest_bytes(canonical_json(identity).encode("utf-8"))
    run_id = f"v3b1-{identity_sha256}"
    runtime = _manifest_runtime_projection(
        identity_sha256=identity_sha256,
        kil_image_id=kil_image_id,
        envoy_image_digest=envoy_image_digest,
        driver_definition_sha256=identity["driver_definition_sha256"],  # type: ignore[arg-type]
    )
    return {
        "schema_version": MANIFEST_SCHEMA,
        "evidence_scope": EVIDENCE_SCOPE,
        "content_identity_sha256": identity_sha256,
        "content_identity": identity,
        "run_id": run_id,
        "request_id": REQUEST_ID,
        "colima_profile": profile.colima_profile,
        "docker_host": docker_host,
        "execution_nonce": execution_nonce,
        "platform": PLATFORM,
        "source_commit": source_commit,
        "python_image_digest": python_image_digest,
        "envoy_image_digest": envoy_image_digest,
        "envoy_image_id": envoy_image_id,
        "kil_image_id": kil_image_id,
        "kil_archive_sha256": kil_archive_sha256,
        "segment_definitions": segments,
        "driver_definitions": drivers,
        "networks": runtime["networks"],
        "tracks": runtime["tracks"],
        "containers": runtime["containers"],
        "teardown": {
            "status": "pending",
            "containers_removed": False,
            "network_removed": False,
            "profile_deleted": False,
        },
    }


def _validate_manifest_v1(value: object) -> dict[str, object]:
    expected = {
        "schema_version",
        "evidence_scope",
        "content_identity_sha256",
        "content_identity",
        "run_id",
        "request_id",
        "colima_profile",
        "docker_host",
        "execution_nonce",
        "platform",
        "source_commit",
        "python_image_digest",
        "envoy_image_digest",
        "envoy_image_id",
        "kil_image_id",
        "kil_archive_sha256",
        "networks",
        "tracks",
        "containers",
        "teardown",
    }
    if type(value) is not dict or set(value) != expected:
        raise ControllerError("manifest fields are not closed")
    if value["schema_version"] != LEGACY_MANIFEST_SCHEMA or value["evidence_scope"] != EVIDENCE_SCOPE:
        raise ControllerError("manifest identity is invalid")
    identity = value["content_identity"]
    identity_fields = {
        "schema_version",
        "profile_sha256",
        "colima_profile",
        "docker_endpoint",
        "platform",
        "source_commit",
        "execution_nonce_sha256",
        "dockerfile_sha256",
        "dockerignore_sha256",
        "build_context_sha256",
        "python_image_digest",
        "envoy_image_digest",
        "envoy_image_id",
        "kil_image_id",
        "kil_archive_sha256",
        "request_id",
        "tracks",
    }
    if type(identity) is not dict or set(identity) != identity_fields:
        raise ControllerError("manifest content identity is invalid")
    if identity["schema_version"] != "kil.v3b1-content-identity.v2":
        raise ControllerError("manifest content identity schema is invalid")
    for name in (
        "profile_sha256",
        "execution_nonce_sha256",
        "dockerfile_sha256",
        "dockerignore_sha256",
        "build_context_sha256",
    ):
        _require_sha256(name, identity[name])
    endpoint = identity["docker_endpoint"]
    if endpoint != {
        "transport": "unix",
        "logical_locator": "colima_profile_socket",
        "profile": LAB_IDENTITY,
    }:
        raise ControllerError("manifest logical Docker endpoint is invalid")
    digest = _digest_bytes(canonical_json(identity).encode("utf-8"))
    if value["content_identity_sha256"] != digest or value["run_id"] != f"v3b1-{digest}":
        raise ControllerError("manifest content address is invalid")
    if value["request_id"] != REQUEST_ID or value["colima_profile"] != LAB_IDENTITY:
        raise ControllerError("manifest fixed identifiers are invalid")
    for name in (
        "request_id",
        "colima_profile",
        "platform",
        "source_commit",
        "python_image_digest",
        "envoy_image_digest",
        "envoy_image_id",
        "kil_image_id",
        "kil_archive_sha256",
    ):
        if value[name] != identity[name]:
            raise ControllerError(f"manifest {name} diverges from content identity")
    execution_nonce = _require_sha256(
        "manifest execution nonce", value["execution_nonce"]
    )
    if identity["execution_nonce_sha256"] != _digest_bytes(
        execution_nonce.encode("ascii")
    ):
        raise ControllerError("manifest execution nonce diverges from content identity")
    if identity["colima_profile"] != value["colima_profile"]:
        raise ControllerError("manifest profile diverges from content identity")
    if type(value["docker_host"]) is not str or not value["docker_host"].startswith(
        "unix:///"
    ):
        raise ControllerError("manifest Docker host is invalid")
    if value["platform"] != PLATFORM:
        raise ControllerError("manifest platform is invalid")
    if type(value["source_commit"]) is not str or re.fullmatch(
        r"[a-f0-9]{40}", value["source_commit"]
    ) is None:
        raise ControllerError("manifest source commit is invalid")
    _require_digest_ref("python_image_digest", value["python_image_digest"])
    _require_digest_ref("envoy_image_digest", value["envoy_image_digest"])
    if type(value["envoy_image_id"]) is not str or _IMAGE_ID.fullmatch(
        value["envoy_image_id"]
    ) is None:
        raise ControllerError("manifest Envoy image ID is invalid")
    if type(value["kil_image_id"]) is not str or _IMAGE_ID.fullmatch(value["kil_image_id"]) is None:
        raise ControllerError("manifest KIL image ID is invalid")
    _require_sha256("kil_archive_sha256", value["kil_archive_sha256"])
    tracks = value["tracks"]
    containers = value["containers"]
    if type(tracks) is not list or len(tracks) != 3:
        raise ControllerError("manifest tracks are invalid")
    if type(containers) is not list or len(containers) != 9:
        raise ControllerError("manifest containers are invalid")
    expected_tracks = [track.value for track in _TRACKS]
    networks = value["networks"]
    if (
        type(networks) is not list
        or len(networks) != 3
        or [item.get("track") for item in networks if type(item) is dict]
        != expected_tracks
        or any(
            type(item) is not dict
            or set(item) != {"track", "name"}
            or not str(item["name"]).startswith("kil-v3b1-network-")
            for item in networks
        )
    ):
        raise ControllerError("manifest per-track networks are invalid")
    if [item.get("track") for item in tracks if type(item) is dict] != expected_tracks:
        raise ControllerError("manifest tracks are not fixed")
    expected_ports = [18080, 18081, 18082]
    track_fields = {
        "track",
        "gateway_port",
        "authz_container",
        "target_container",
        "envoy_container",
        "network",
        "decision_source",
        "target_source",
        "envoy_source",
    }
    if any(type(item) is not dict or set(item) != track_fields for item in tracks):
        raise ControllerError("manifest track fields are not closed")
    if [item["gateway_port"] for item in tracks] != expected_ports:
        raise ControllerError("manifest gateway ports are not fixed")
    if identity["tracks"] != [
        {"track": item["track"], "gateway_port": item["gateway_port"]}
        for item in tracks
    ]:
        raise ControllerError("manifest tracks diverge from content identity")
    network_by_track = {item["track"]: item["name"] for item in networks}
    if any(item["network"] != network_by_track[item["track"]] for item in tracks):
        raise ControllerError("manifest track network binding is invalid")
    names = []
    for item in containers:
        if type(item) is not dict or set(item) != {"name", "role", "track", "image"}:
            raise ControllerError("manifest container fields are invalid")
        if not str(item["name"]).startswith("kil-v3b1-"):
            raise ControllerError("manifest container name is invalid")
        names.append(item["name"])
    if len(set(names)) != 9:
        raise ControllerError("manifest container names are not unique")
    expected_role_tracks = {
        (role, track.value) for track in _TRACKS for role in ("authz", "target", "envoy")
    }
    if {(item["role"], item["track"]) for item in containers} != expected_role_tracks:
        raise ControllerError("manifest container roles/tracks are invalid")
    teardown = value["teardown"]
    if type(teardown) is not dict or set(teardown) != {
        "status",
        "containers_removed",
        "network_removed",
        "profile_deleted",
    }:
        raise ControllerError("manifest teardown fields are invalid")
    if teardown not in (
        {
            "status": "pending",
            "containers_removed": False,
            "network_removed": False,
            "profile_deleted": False,
        },
        {
            "status": "complete",
            "containers_removed": True,
            "network_removed": True,
            "profile_deleted": True,
        },
    ):
        raise ControllerError("manifest teardown state is invalid")
    return value


def _validate_manifest_v2(value: object) -> dict[str, object]:
    expected = {
        "schema_version", "evidence_scope", "content_identity_sha256",
        "content_identity", "run_id", "request_id", "colima_profile",
        "docker_host", "execution_nonce", "platform", "source_commit",
        "python_image_digest", "envoy_image_digest", "envoy_image_id",
        "kil_image_id", "kil_archive_sha256", "segment_definitions",
        "driver_definitions", "networks", "tracks", "containers", "teardown",
    }
    if type(value) is not dict or set(value) != expected:
        raise ControllerError("manifest fields are not closed")
    if (
        value["schema_version"] != MANIFEST_SCHEMA
        or value["evidence_scope"] != EVIDENCE_SCOPE
    ):
        raise ControllerError("manifest identity is invalid")

    identity = value["content_identity"]
    identity_fields = {
        "schema_version", "profile_sha256", "colima_profile",
        "docker_endpoint", "platform", "source_commit",
        "execution_nonce_sha256", "dockerfile_sha256",
        "dockerignore_sha256", "build_context_sha256",
        "python_image_digest", "envoy_image_digest", "envoy_image_id",
        "kil_image_id", "kil_archive_sha256", "request_id",
        "driver_endpoint", "segment_definitions", "driver_definition_sha256",
    }
    if type(identity) is not dict or set(identity) != identity_fields:
        raise ControllerError("manifest content identity is invalid")
    if identity["schema_version"] != "kil.v3b1-content-identity.v3":
        raise ControllerError("manifest content identity schema is invalid")
    for name in (
        "profile_sha256", "execution_nonce_sha256", "dockerfile_sha256",
        "dockerignore_sha256", "build_context_sha256",
    ):
        _require_sha256(name, identity[name])
    if identity["docker_endpoint"] != {
        "transport": "unix",
        "logical_locator": "colima_profile_socket",
        "profile": LAB_IDENTITY,
    }:
        raise ControllerError("manifest logical Docker endpoint is invalid")
    endpoint = {"transport": "tcp", "host": "envoy", "port": 8080}
    if identity["driver_endpoint"] != endpoint:
        raise ControllerError("manifest driver endpoint is invalid")

    segments = value["segment_definitions"]
    if segments != _segment_definitions() or identity["segment_definitions"] != segments:
        raise ControllerError("manifest segment definitions are invalid")
    drivers = value["driver_definitions"]
    if type(drivers) is not list or len(drivers) != len(_TRACKS):
        raise ControllerError("manifest driver definitions are invalid")
    if any(type(item) is not dict for item in drivers):
        raise ControllerError("manifest driver definitions are invalid")
    bootstrap_values = {item.get("bootstrap_sha256") for item in drivers}
    if len(bootstrap_values) != 1:
        raise ControllerError("manifest driver bootstrap binding is invalid")
    bootstrap_sha256 = next(iter(bootstrap_values))
    _require_sha256("manifest driver bootstrap", bootstrap_sha256)
    expected_drivers = _driver_definitions(
        kil_image_id=str(value["kil_image_id"]),
        bootstrap_sha256=bootstrap_sha256,
        segment_definitions=segments,
    )
    if drivers != expected_drivers:
        raise ControllerError("manifest driver definitions are invalid")
    expected_driver_hashes = [
        {
            "track": item["track"],
            "sha256": _digest_bytes(canonical_record(item)),
        }
        for item in drivers
    ]
    if identity["driver_definition_sha256"] != expected_driver_hashes:
        raise ControllerError("manifest driver definition hashes are invalid")

    digest = _digest_bytes(canonical_json(identity).encode("utf-8"))
    if (
        value["content_identity_sha256"] != digest
        or value["run_id"] != f"v3b1-{digest}"
    ):
        raise ControllerError("manifest content address is invalid")
    if value["request_id"] != REQUEST_ID or value["colima_profile"] != LAB_IDENTITY:
        raise ControllerError("manifest fixed identifiers are invalid")
    for name in (
        "request_id", "colima_profile", "platform", "source_commit",
        "python_image_digest", "envoy_image_digest", "envoy_image_id",
        "kil_image_id", "kil_archive_sha256",
    ):
        if value[name] != identity[name]:
            raise ControllerError(f"manifest {name} diverges from content identity")
    execution_nonce = _require_sha256(
        "manifest execution nonce", value["execution_nonce"]
    )
    if identity["execution_nonce_sha256"] != _digest_bytes(
        execution_nonce.encode("ascii")
    ):
        raise ControllerError("manifest execution nonce diverges from content identity")
    if type(value["docker_host"]) is not str or not value["docker_host"].startswith(
        "unix:///"
    ):
        raise ControllerError("manifest Docker host is invalid")
    if value["platform"] != PLATFORM:
        raise ControllerError("manifest platform is invalid")
    if type(value["source_commit"]) is not str or re.fullmatch(
        r"[a-f0-9]{40}", value["source_commit"]
    ) is None:
        raise ControllerError("manifest source commit is invalid")
    _require_digest_ref("python_image_digest", value["python_image_digest"])
    _require_digest_ref("envoy_image_digest", value["envoy_image_digest"])
    for name in ("envoy_image_id", "kil_image_id"):
        if type(value[name]) is not str or _IMAGE_ID.fullmatch(value[name]) is None:
            raise ControllerError("manifest image ID is invalid")
    _require_sha256("kil_archive_sha256", value["kil_archive_sha256"])

    expected_runtime = _manifest_runtime_projection(
        identity_sha256=digest,
        kil_image_id=str(value["kil_image_id"]),
        envoy_image_digest=str(value["envoy_image_digest"]),
        driver_definition_sha256=expected_driver_hashes,
    )

    containers = value["containers"]
    if type(containers) is not list or len(containers) != 12:
        raise ControllerError("manifest containers are invalid")
    container_map: dict[tuple[object, object], dict[str, object]] = {}
    for item in containers:
        if type(item) is not dict or set(item) != {
            "name", "role", "track", "image", "command_definition_sha256",
        }:
            raise ControllerError("manifest container fields are invalid")
        key = (item["track"], item["role"])
        if key in container_map:
            raise ControllerError("manifest container mapping is duplicated")
        container_map[key] = item
    expected_container_map = {
        (item["track"], item["role"]): item
        for item in expected_runtime["containers"]
    }
    if set(container_map) != set(expected_container_map):
        raise ControllerError("manifest container mappings are incomplete")
    for key, expected_container in expected_container_map.items():
        if container_map[key] != expected_container:
            raise ControllerError("manifest container binding is invalid")
    container_names = [str(item["name"]) for item in containers]
    if len(set(container_names)) != len(container_names):
        raise ControllerError("manifest container names are not unique")

    networks = value["networks"]
    if type(networks) is not list or len(networks) != 6:
        raise ControllerError("manifest networks are invalid")
    network_map: dict[tuple[object, object], dict[str, object]] = {}
    for item in networks:
        if type(item) is not dict or set(item) != {"track", "segment", "name"}:
            raise ControllerError("manifest network fields are invalid")
        key = (item["track"], item["segment"])
        if key in network_map:
            raise ControllerError("manifest network mapping is duplicated")
        network_map[key] = item
    expected_network_map = {
        (item["track"], item["segment"]): item
        for item in expected_runtime["networks"]
    }
    if set(network_map) != set(expected_network_map):
        raise ControllerError("manifest network mappings are incomplete")
    for key, expected_network in expected_network_map.items():
        if network_map[key] != expected_network:
            raise ControllerError("manifest network binding is invalid")
    network_names = [str(item["name"]) for item in networks]
    if len(set(network_names)) != len(network_names):
        raise ControllerError("manifest network names are not unique")

    tracks = value["tracks"]
    if type(tracks) is not list or len(tracks) != 3:
        raise ControllerError("manifest tracks are invalid")
    track_map: dict[object, dict[str, object]] = {}
    for item in tracks:
        if type(item) is not dict:
            raise ControllerError("manifest track fields are invalid")
        track = item.get("track")
        if track in track_map:
            raise ControllerError("manifest track mapping is duplicated")
        track_map[track] = item
    expected_track_map = {
        item["track"]: item for item in expected_runtime["tracks"]
    }
    if set(track_map) != set(expected_track_map):
        raise ControllerError("manifest track mappings are incomplete")
    for track, expected_track in expected_track_map.items():
        if track_map[track] != expected_track:
            raise ControllerError("manifest track binding is invalid")
    teardown = value["teardown"]
    if type(teardown) is not dict or set(teardown) != {
        "status", "containers_removed", "network_removed", "profile_deleted",
    }:
        raise ControllerError("manifest teardown fields are invalid")
    if teardown not in (
        {
            "status": "pending", "containers_removed": False,
            "network_removed": False, "profile_deleted": False,
        },
        {
            "status": "complete", "containers_removed": True,
            "network_removed": True, "profile_deleted": True,
        },
    ):
        raise ControllerError("manifest teardown state is invalid")
    return value


def _validate_manifest(value: object) -> dict[str, object]:
    """Dispatch private manifests without accepting hybrid schema shapes."""
    if type(value) is not dict:
        raise ControllerError("manifest fields are not closed")
    schema = value.get("schema_version")
    if schema == LEGACY_MANIFEST_SCHEMA:
        return _validate_manifest_v1(value)
    if schema == MANIFEST_SCHEMA:
        return _validate_manifest_v2(value)
    raise ControllerError("manifest schema is invalid")


def _claims(audience: str, issued_at_s: int) -> QStateClaims:
    return QStateClaims(
        schema_version="kil.q-state.v0",
        state_id=f"q-v3b1-{audience}",
        issuer="https://lab-issuer.kil.invalid",
        subject=SUBJECT,
        audience=audience,
        authority_class="admin_action",
        action_class="consequential_admin",
        issued_at_s=issued_at_s,
        not_before_s=issued_at_s,
        expires_at_s=issued_at_s + 10,
        evidence_horizon_s=issued_at_s - 1,
        trust_proof_id="tp-v3b1-1",
        trust_proof_digest="sha256:" + "a" * 64,
        envelope_result_id="ke-v3b1-1",
        envelope_result_digest="sha256:" + "b" * 64,
        deployment_profile="kil-lab-v3@0",
        charge=Decimal("80"),
        threshold=Decimal("40"),
        history_count=5,
        minimum_history=2,
        veto_clear=True,
        envelope_allows=True,
        decay_rate=Decimal("0"),
        maximum_charge=Decimal("100"),
        model_version="kil-decay-v1",
        parameter_version="kil-v3b1-fixture-v1",
    )


def _b64url(payload: bytes) -> str:
    return urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _track_manifest(manifest: Mapping[str, object], track: LiveTrack) -> dict[str, object]:
    tracks = manifest["tracks"]
    assert isinstance(tracks, list)
    for item in tracks:
        if isinstance(item, dict) and item.get("track") == track.value:
            return item
    raise ControllerError(f"manifest omits track {track.value}")


def _runtime_networks(
    manifest: Mapping[str, object],
) -> list[dict[str, object]]:
    """Return the schema-bound network projection without hybrid inference."""
    networks = manifest["networks"]  # type: ignore[assignment]
    assert isinstance(networks, list)
    return [dict(item) for item in networks]


def _network_segment(item: Mapping[str, object]) -> str:
    """Map legacy single networks to backend while preserving v2 segments."""
    segment = item.get("segment", "backend")
    if segment not in {"frontend", "backend"}:
        raise ControllerError("runtime network segment is invalid")
    return str(segment)


def materialize_run_inputs(root: Path, manifest: dict[str, object]) -> MaterializedInputs:
    """Write deterministic, read-only service configs and central fixtures."""
    _validate_manifest(manifest)
    runtime_root = _runtime_root(root, manifest)
    runtime_root.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_record = {
        "key_id": key_id(public_key),
        "raw_base64url": _b64url(public_bytes),
    }
    authorization_digest = _digest_bytes(AUTHORIZATION.encode("utf-8"))
    fixture = {
        "request_id": manifest["request_id"],
        "method": "POST",
        "path": "/consequential/admin",
        "identity": SUBJECT,
        "authority_class": "admin_action",
        "action_class": "consequential_admin",
        "expected_authorization_sha256": authorization_digest,
        "policy_allows_action": True,
        "local_evidence": {
            "divergence": "0.9",
            "coupled_loss": "0",
            "fresh": True,
        },
        "reduction_profile": {
            "divergence_threshold": "0.25",
            "loss_rate": "25",
            "exponent": 3,
        },
    }
    requests: dict[LiveTrack, dict[str, object]] = {}
    for track in _TRACKS:
        track_root = runtime_root / track.value
        track_root.mkdir(parents=True, exist_ok=True)
        public_keys = [] if track is LiveTrack.CREDENTIAL_POLICY_BASELINE else [public_record]
        authz = {
            "schema_version": "kil.v3b-authz-http.v1",
            "track": track.value,
            "bind_host": "0.0.0.0",
            "bind_port": 8080,
            "records_path": "/evidence/decisions.jsonl",
            "public_keys": public_keys,
            "revoked_state_ids": [],
            "fixtures": [fixture],
        }
        target = {
            "schema_version": "kil.v3b-target-http.v1",
            "run_id": manifest["run_id"],
            "track": track.value,
            "bind_host": "0.0.0.0",
            "bind_port": 8080,
            "ledger_path": "/evidence/targets.jsonl",
        }
        track_info = _track_manifest(manifest, track)
        envoy = render_envoy_json(
            track,
            str(track_info["authz_container"]),
            str(track_info["target_container"]),
        )
        for name, payload in (
            ("authz.json", _canonical_bytes(authz)),
            ("target.json", _canonical_bytes(target)),
            ("envoy.json", (envoy + "\n").encode("utf-8")),
        ):
            _write_file(track_root / name, payload, 0o444)
        requests[track] = {
            "method": "POST",
            "path": "/consequential/admin",
            "authorization": AUTHORIZATION,
            "q_state": None,
            "adversarial_headers": dict(ADVERSARIAL_HEADERS),
            "retry_control_headers": dict(RETRY_CONTROL_HEADERS),
        }
    return MaterializedInputs(runtime_root, requests)


def _docker_prefix(
    docker_binary: Path,
    manifest: Mapping[str, object],
    docker_config: Path | None = None,
) -> list[str]:
    host = manifest.get("docker_host")
    if type(host) is not str or not host.startswith("unix:///"):
        raise ControllerError("manifest Docker host is invalid")
    config = docker_config or docker_binary.parent.parent / "v3b1-docker-config"
    return [str(docker_binary), "--config", str(config), "--host", host]


def _labels(manifest: Mapping[str, object], role: str, track: LiveTrack) -> list[str]:
    return [
        "--label",
        "kil.v3b1.managed=true",
        "--label",
        f"kil.v3b1.run-id={manifest['run_id']}",
        "--label",
        f"kil.v3b1.role={role}",
        "--label",
        f"kil.v3b1.track={track.value}",
    ]


def _hardened_kil_options() -> list[str]:
    return [
        "--platform",
        PLATFORM,
        "--pull=never",
        "--read-only",
        "--user",
        "65532:65532",
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "--cpus",
        "0.50",
        "--memory",
        "256m",
        "--memory-swap",
        "256m",
        "--pids-limit",
        "128",
        "--restart=no",
        "--stop-timeout",
        "10",
        "--log-driver",
        "json-file",
        "--log-opt",
        "max-size=1m",
        "--log-opt",
        "max-file=1",
        "--tmpfs",
        "/evidence:rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700",
    ]


def build_runtime_commands(
    root: Path,
    manifest: dict[str, object],
    *,
    docker_binary: Path,
) -> list[list[str]]:
    """Construct validators, six internal segments, services, and drivers."""
    _validate_manifest(manifest)
    runtime_root = _runtime_root(root, manifest)
    prefix = _docker_prefix(
        docker_binary, manifest, root / ".tools/v3b1-docker-config"
    )
    commands: list[list[str]] = []
    for track in _TRACKS:
        config = runtime_root / track.value / "envoy.json"
        commands.append(
            [
                *prefix,
                "run",
                "-d",
                "--name",
                f"kil-v3b1-validate-{_track_slug(track)}-{str(manifest['content_identity_sha256'])[:12]}",
                *_labels(manifest, "validator", track),
                "--platform",
                PLATFORM,
                "--pull=never",
                "--network",
                "none",
                "--read-only",
                "--user",
                "65532:65532",
                "--security-opt",
                "no-new-privileges",
                "--cap-drop",
                "ALL",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700",
                "--mount",
                f"type=bind,src={config},dst=/etc/envoy/envoy.json,readonly",
                "--entrypoint",
                "/usr/local/bin/envoy",
                str(manifest["envoy_image_digest"]),
                "--mode",
                "validate",
                "--config-path",
                "/etc/envoy/envoy.json",
                "--disable-hot-restart",
                "--concurrency",
                "1",
            ]
        )
    for segment in ("backend", "frontend"):
        for network in _runtime_networks(manifest):
            if _network_segment(network) != segment:
                continue
            commands.append(
                [
                    *prefix,
                    "network",
                    "create",
                    "--driver",
                    "bridge",
                    "--internal",
                    "--label",
                    f"kil.v3b1.run-id={manifest['run_id']}",
                    "--label",
                    "kil.v3b1.managed=true",
                    "--label",
                    f"kil.v3b1.track={network['track']}",
                    str(network["name"]),
                ]
            )
    for track in _TRACKS:
        track_root = runtime_root / track.value
        item = _track_manifest(manifest, track)
        common_network = ["--network", str(item["backend_network"])]
        authz_name = str(item["authz_container"])
        target_name = str(item["target_container"])
        envoy_name = str(item["envoy_container"])
        commands.append(
            [
                *prefix,
                "run",
                "-d",
                "--name",
                authz_name,
                "--network-alias",
                authz_name,
                *common_network,
                *_labels(manifest, "authz", track),
                *_hardened_kil_options(),
                "--mount",
                f"type=bind,src={track_root / 'authz.json'},dst=/config/authz.json,readonly",
                str(manifest["kil_image_id"]),
                "python",
                "-c",
                _AUTHZ_BOOTSTRAP,
                "--config",
                "/config/authz.json",
            ]
        )
        commands.append(
            [
                *prefix,
                "run",
                "-d",
                "--name",
                target_name,
                "--network-alias",
                target_name,
                *common_network,
                *_labels(manifest, "target", track),
                *_hardened_kil_options(),
                "--mount",
                f"type=bind,src={track_root / 'target.json'},dst=/config/target.json,readonly",
                str(manifest["kil_image_id"]),
                "python",
                "-c",
                _TARGET_BOOTSTRAP,
                "--config",
                "/config/target.json",
            ]
        )
        commands.append(
            [
                *prefix,
                "run",
                "-d",
                "--name",
                envoy_name,
                "--network-alias",
                envoy_name,
                *common_network,
                *_labels(manifest, "envoy", track),
                "--platform",
                PLATFORM,
                "--pull=never",
                "--read-only",
                "--user",
                "65532:65532",
                "--security-opt",
                "no-new-privileges",
                "--cap-drop",
                "ALL",
                "--cpus",
                "0.50",
                "--memory",
                "256m",
                "--memory-swap",
                "256m",
                "--pids-limit",
                "128",
                "--restart=no",
                "--stop-timeout",
                "10",
                "--log-driver",
                "json-file",
                "--log-opt",
                "max-size=1m",
                "--log-opt",
                "max-file=1",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700",
                "--mount",
                f"type=bind,src={track_root / 'envoy.json'},dst=/etc/envoy/envoy.json,readonly",
                "--entrypoint",
                "/usr/local/bin/envoy",
                str(manifest["envoy_image_digest"]),
                "--config-path",
                "/etc/envoy/envoy.json",
                "--disable-hot-restart",
                "--concurrency",
                "1",
            ]
        )
        driver_name = str(item["driver_container"])
        commands.append(
            [
                *prefix,
                "create",
                "--interactive",
                "--no-healthcheck",
                "--name",
                driver_name,
                "--network-alias",
                driver_name,
                "--network",
                str(item["frontend_network"]),
                *_labels(manifest, "driver", track),
                "--platform",
                PLATFORM,
                "--pull=never",
                "--read-only",
                "--user",
                "65532:65532",
                "--security-opt",
                "no-new-privileges",
                "--cap-drop",
                "ALL",
                "--cpus",
                "0.50",
                "--memory",
                "256m",
                "--memory-swap",
                "256m",
                "--pids-limit",
                "128",
                "--restart=no",
                "--stop-timeout",
                "10",
                "--log-driver",
                "json-file",
                "--log-opt",
                "max-size=1m",
                "--log-opt",
                "max-file=1",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700",
                str(manifest["kil_image_id"]),
                "python",
                "-m",
                "kil.v3b1_request_driver",
                "--track",
                track.value,
                "--endpoint",
                "envoy:8080",
            ]
        )
    return commands


def _network_connect_command(
    docker_prefix: Sequence[str], details: Mapping[str, object]
) -> list[str]:
    """Build the closed full-ID Envoy-to-frontend network attachment command."""
    _validate_lifecycle_event_details("network_connect_intent", details)
    return [
        *docker_prefix,
        "network",
        "connect",
        "--alias",
        "envoy",
        str(details["network_id"]),
        str(details["container_id"]),
    ]


def collection_commands(
    root: Path,
    manifest: dict[str, object],
    *,
    docker_binary: Path,
) -> list[list[str]]:
    """Return exact per-container evidence extraction commands."""
    _validate_manifest(manifest)
    prefix = _docker_prefix(
        docker_binary, manifest, root / ".tools/v3b1-docker-config"
    )
    collected = _runtime_root(root, manifest) / "collected"
    commands = []
    for track in _TRACKS:
        destination = collected / track.value
        item = _track_manifest(manifest, track)
        commands.extend(
            [
                [
                    *prefix,
                    "cp",
                    f"{item['authz_container']}:/evidence/decisions.jsonl",
                    str(destination / "decisions.jsonl"),
                ],
                [
                    *prefix,
                    "cp",
                    f"{item['target_container']}:/evidence/targets.jsonl",
                    str(destination / "targets.jsonl"),
                ],
                [*prefix, "logs", str(item["envoy_container"])],
            ]
        )
    return commands


def _object_labels(run_id: str, role: str | None, track: str | None) -> dict[str, str]:
    labels = {"kil.v3b1.managed": "true", "kil.v3b1.run-id": run_id}
    if role is not None:
        labels["kil.v3b1.role"] = role
    if track is not None:
        labels["kil.v3b1.track"] = track
    return labels


def _state_binding(value: Mapping[str, object]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "binding_sha256"}
    return _digest_bytes(canonical_json(unsigned).encode("utf-8"))


def _synthetic_state_object(
    manifest: Mapping[str, object], item: Mapping[str, object]
) -> dict[str, object]:
    role = str(item["role"])
    track = str(item["track"])
    name = str(item["name"])
    object_id = _digest_bytes(name.encode("utf-8"))
    image_id = (
        manifest["envoy_image_id"] if role == "envoy" else manifest["kil_image_id"]
    )
    config_path = (
        None if role == "driver" else f"/unavailable/{track}/{role}.json"
    )
    track_record = next(
        record
        for record in manifest["tracks"]  # type: ignore[union-attr]
        if record["track"] == track
    )
    tmpfs = {
        "/tmp": "rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700"
    }
    if role in {"authz", "target"}:
        tmpfs["/evidence"] = "rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700"
    destination = (
        "/etc/envoy/envoy.json"
        if role == "envoy"
        else f"/config/{role}.json"
    )
    if role == "envoy":
        networks = [
            track_record["backend_network"],
            track_record["frontend_network"],
        ]
    elif role == "driver":
        networks = [track_record["frontend_network"]]
    else:
        networks = [
            track_record.get("backend_network", track_record.get("network"))
        ]
    aliases = {
        str(network): [
            "envoy"
            if role == "envoy" and network == track_record.get("frontend_network")
            else name,
            object_id[:12],
        ]
        for network in networks
    }
    runtime = {
        "id": object_id,
        "name": name,
        "image_id": image_id,
        "user": "65532:65532",
        "readonly_rootfs": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "nano_cpus": 500_000_000,
        "memory": 268_435_456,
        "memory_swap": 268_435_456,
        "pids_limit": 128,
        "restart_policy": "no",
        "stop_timeout": 10,
        "log_driver": "json-file",
        "log_options": {"max-file": "1", "max-size": "1m"},
        "tmpfs": tmpfs,
        "mounts": (
            []
            if role == "driver"
            else [{"source": config_path, "destination": destination, "rw": False}]
        ),
        "networks": sorted(str(network) for network in networks),
        "network_aliases": aliases,
        "port_bindings": {},
        "published_ports": None,
        "platform": PLATFORM,
        "entrypoint": ["/usr/local/bin/envoy"] if role == "envoy" else [],
        "command": (
            [
                "--config-path", "/etc/envoy/envoy.json", "--disable-hot-restart",
                "--concurrency", "1",
            ]
            if role == "envoy"
            else [
                "python", "-m", "kil.v3b1_request_driver", "--track", track,
                "--endpoint", "envoy:8080",
            ]
            if role == "driver"
            else [
                "python", "-c",
                _AUTHZ_BOOTSTRAP if role == "authz" else _TARGET_BOOTSTRAP,
                "--config", f"/config/{role}.json",
            ]
        ),
        "environment": ["PATH=/usr/local/bin"],
        "state": "created" if role == "driver" else "running",
        "stdin_open": role == "driver",
        "tty": False,
        "healthcheck": "disabled" if role == "driver" else None,
        "privileged": False,
        "network_mode": str(
            track_record["frontend_network"]
            if role == "driver"
            else track_record.get("backend_network", track_record.get("network"))
        ),
        "pid_mode": "",
        "ipc_mode": "",
        "uts_mode": "",
        "userns_mode": "",
    }
    return {
        "name": name,
        "id": object_id,
        "role": role,
        "track": track,
        "labels": _object_labels(str(manifest["run_id"]), role, track),
        "image_id": image_id,
        "image_reference": item["image"],
        "config_path": config_path,
        "config_sha256": None if role == "driver" else "0" * 64,
        "runtime_attestation": runtime,
    }


def persist_active_state(
    state_path: Path,
    manifest_path: Path,
    manifest: dict[str, object],
    *,
    objects: Sequence[Mapping[str, object]] | None = None,
    network_objects: Sequence[Mapping[str, object]] | None = None,
    profile_created: bool = True,
) -> None:
    """Persist an ignored exact state cryptographically bound to a manifest."""
    _validate_manifest(manifest)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ControllerError("active manifest path is not a regular file")
    manifest_payload = manifest_path.read_bytes()
    if manifest_payload != _canonical_bytes(manifest):
        raise ControllerError("active manifest is not canonical")
    run_id = str(manifest["run_id"])
    if objects is None:
        objects = [
            _synthetic_state_object(manifest, item)
            for item in manifest["containers"]  # type: ignore[union-attr]
        ]
    if network_objects is None:
        network_objects = [
            {
                "name": item["name"],
                "id": _digest_bytes(str(item["name"]).encode("utf-8")),
                "track": item["track"],
                "segment": _network_segment(item),
                "labels": _object_labels(run_id, None, str(item["track"])),
            }
            for item in _runtime_networks(manifest)
        ]
    base: dict[str, object] = {
        "schema_version": STATE_SCHEMA,
        "run_id": run_id,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": _digest_bytes(manifest_payload),
        "colima_profile": manifest["colima_profile"],
        "profile_created": profile_created,
        "docker_host": manifest["docker_host"],
        "docker_config": str(state_path.parents[1] / "v3b1-docker-config"),
        "networks": manifest["networks"],
        "objects": [dict(item) for item in objects],
        "network_objects": [dict(item) for item in network_objects],
    }
    base["binding_sha256"] = _state_binding(base)
    _write_file(state_path, _canonical_bytes(base), 0o600)


def _validate_state_objects(
    state: Mapping[str, object], manifest: Mapping[str, object]
) -> None:
    objects = state.get("objects")
    if type(objects) is not list or len(objects) != 12:
        raise ControllerError("active state Docker objects are invalid")
    expected = {
        item["name"]: item
        for item in manifest["containers"]  # type: ignore[union-attr]
    }
    seen = set()
    for item in objects:
        if type(item) is not dict or set(item) != {
            "name",
            "id",
            "role",
            "track",
            "labels",
            "image_id",
            "image_reference",
            "config_path",
            "config_sha256",
            "runtime_attestation",
        }:
            raise ControllerError("active state Docker object fields are invalid")
        name = item["name"]
        if name not in expected or name in seen:
            raise ControllerError("active state Docker names do not match manifest")
        seen.add(name)
        if type(item["id"]) is not str or _HEX.fullmatch(item["id"]) is None:
            raise ControllerError("active state Docker object ID is invalid")
        source = expected[name]
        if item["role"] != source["role"] or item["track"] != source["track"]:
            raise ControllerError("active state Docker role does not match manifest")
        if item["labels"] != _object_labels(
            str(state["run_id"]), str(item["role"]), str(item["track"])
        ):
            raise ControllerError("active state Docker labels are invalid")
        expected_image_id = (
            manifest["envoy_image_id"]
            if item["role"] == "envoy"
            else manifest["kil_image_id"]
        )
        if item["image_id"] != expected_image_id or item["image_reference"] != source["image"]:
            raise ControllerError("active state Docker image identity is invalid")
        if item["role"] == "driver":
            if item["config_path"] is not None or item["config_sha256"] is not None:
                raise ControllerError("active driver config attestation is invalid")
        elif (
            type(item["config_path"]) is not str
            or not Path(item["config_path"]).is_absolute()
            or type(item["config_sha256"]) is not str
            or _HEX.fullmatch(item["config_sha256"]) is None
        ):
            raise ControllerError("active state config attestation is invalid")
        track_record = next(
            record
            for record in manifest["tracks"]  # type: ignore[union-attr]
            if record["track"] == item["track"]
        )
        if item["role"] == "envoy":
            expected_networks = [
                track_record["backend_network"],
                track_record["frontend_network"],
            ]
        elif item["role"] == "driver":
            expected_networks = [track_record["frontend_network"]]
        else:
            expected_networks = [
                track_record.get("backend_network", track_record.get("network"))
            ]
        required_aliases = {
            str(network): [
                "envoy"
                if item["role"] == "envoy"
                and network == track_record.get("frontend_network")
                else str(item["name"])
            ]
            for network in expected_networks
        }
        driver_definition_value = None
        if item["role"] == "driver":
            driver_definition_value = next(
                definition
                for definition in manifest["driver_definitions"]  # type: ignore[union-attr]
                if definition["track"] == item["track"]
            )
        expected_runtime = {
            "name": item["name"],
            "role": item["role"],
            "track": item["track"],
            "image_id": item["image_id"],
            "networks": sorted(str(network) for network in expected_networks),
            "config_path": item["config_path"],
            "config_sha256": item["config_sha256"],
            "gateway_port": None,
            "required_aliases": required_aliases,
            "driver_definition": driver_definition_value,
            "required_state": "created" if item["role"] == "driver" else "running",
            "primary_network": str(
                track_record["frontend_network"]
                if item["role"] == "driver"
                else track_record.get(
                    "backend_network", track_record.get("network")
                )
            ),
        }
        runtime = validate_container_attestation(
            item["runtime_attestation"], expected_runtime
        )
        if runtime["id"] != item["id"]:
            raise ControllerError("active state runtime ID does not match object ID")
    networks = state.get("network_objects")
    expected_networks = {
        item["name"]: item
        for item in _runtime_networks(manifest)
    }
    if type(networks) is not list or len(networks) != 6:
        raise ControllerError("active state network objects are invalid")
    seen_networks: set[object] = set()
    for network in networks:
        if type(network) is not dict or set(network) != {
            "name", "id", "track", "segment", "labels"
        }:
            raise ControllerError("active state network object is invalid")
        if (
            network["name"] not in expected_networks
            or expected_networks[network["name"]]["track"] != network["track"]
            or _network_segment(expected_networks[network["name"]])
            != network["segment"]
            or type(network["id"]) is not str
            or _HEX.fullmatch(network["id"]) is None
        ):
            raise ControllerError("active state network identity is invalid")
        if network["name"] in seen_networks:
            raise ControllerError("active state network identity is duplicated")
        seen_networks.add(network["name"])
        if network["labels"] != _object_labels(
            str(state["run_id"]), None, str(network["track"])
        ):
            raise ControllerError("active state network labels are invalid")
    if seen_networks != set(expected_networks):
        raise ControllerError("active state networks do not match manifest")


def load_bound_active_state(state_path: Path) -> dict[str, object]:
    """Load active state only after checking both state and manifest bindings."""
    if state_path.is_symlink() or not state_path.is_file():
        raise ControllerError("active state is missing or unsafe")
    state = _load_json_bytes(state_path.read_bytes(), "active state")
    expected = {
        "schema_version",
        "run_id",
        "manifest_path",
        "manifest_sha256",
        "colima_profile",
        "profile_created",
        "docker_host",
        "docker_config",
        "networks",
        "objects",
        "network_objects",
        "binding_sha256",
    }
    if set(state) != expected or state["schema_version"] != STATE_SCHEMA:
        raise ControllerError("active state fields are not closed")
    if state["binding_sha256"] != _state_binding(state):
        raise ControllerError("active state binding does not match")
    manifest_path = Path(str(state["manifest_path"]))
    if not manifest_path.is_absolute() or manifest_path.is_symlink() or not manifest_path.is_file():
        raise ControllerError("active manifest is missing or unsafe")
    payload = manifest_path.read_bytes()
    if state["manifest_sha256"] != _digest_bytes(payload):
        raise ControllerError("active manifest hash does not match state")
    manifest = _load_json_bytes(payload, "active manifest")
    _validate_manifest(manifest)
    if payload != _canonical_bytes(manifest):
        raise ControllerError("active manifest is not canonical")
    for name in ("run_id", "colima_profile", "docker_host", "networks"):
        if state[name] != manifest[name]:
            raise ControllerError(f"active manifest {name} does not match state")
    if state["profile_created"] is not True:
        raise ControllerError("active state does not prove profile ownership")
    _validate_state_objects(state, manifest)
    state["manifest"] = manifest
    return state


def teardown_commands(
    state: Mapping[str, object], *, docker_binary: Path
) -> list[list[str]]:
    """Construct exact ID-addressed cleanup; never discover deletion targets."""
    if state.get("profile_created") is not True:
        raise ControllerError("profile ownership is not proven")
    if state.get("colima_profile") != LAB_IDENTITY:
        raise ControllerError("profile ownership identity is invalid")
    manifest = state.get("manifest")
    if isinstance(manifest, dict):
        _validate_state_objects(state, manifest)
    prefix = [
        str(docker_binary),
        "--config",
        str(state["docker_config"]),
        "--host",
        str(state["docker_host"]),
    ]
    objects = state.get("objects")
    if type(objects) is not list or len(objects) != 12:
        raise ControllerError("exact teardown objects are unavailable")
    running = [
        item for role in ("envoy", "authz", "target")
        for item in objects
        if isinstance(item, dict) and item.get("role") == role
    ]
    ordered = [
        item for role in ("envoy", "authz", "target", "driver")
        for item in objects
        if isinstance(item, dict) and item.get("role") == role
    ]
    commands = [
        [*prefix, "stop", "--timeout", "10", str(item["id"])]
        for item in running
    ]
    commands.extend([*prefix, "rm", str(item["id"])] for item in ordered)
    networks = state.get("network_objects")
    if type(networks) is not list or len(networks) != 6:
        raise ControllerError("exact teardown networks are unavailable")
    commands.extend(
        [*prefix, "network", "rm", str(network["id"])]
        for network in networks
        if isinstance(network, dict)
    )
    commands.extend(
        [
            ["colima", "stop", "--profile", LAB_IDENTITY],
            [
                "colima",
                "delete",
                "--profile",
                LAB_IDENTITY,
                "--force",
                "--data",
            ],
        ]
    )
    return commands


def _record_key(record: Mapping[str, object]) -> tuple[str, str]:
    track = record.get("track")
    request_id = record.get("request_id")
    if type(track) is not str or type(request_id) is not str:
        raise ControllerError("evidence record is missing its fixed join key")
    try:
        LiveTrack(track)
    except ValueError as error:
        raise ControllerError("evidence record track is invalid") from error
    return track, request_id


def _index_unique(
    label: str, records: Sequence[Mapping[str, object]]
) -> dict[tuple[str, str], Mapping[str, object]]:
    result = {}
    for record in records:
        if type(record) is not dict:
            raise ControllerError(f"{label} record must be an object")
        key = _record_key(record)
        if key in result:
            raise ControllerError(f"duplicate {label} record for fixed join key")
        result[key] = record
    return result


def _request_closed(record: Mapping[str, object]) -> None:
    expected = {
        "schema_version",
        "run_id",
        "request_id",
        "track",
        "method",
        "path",
        "attempt_count",
        "retry_observed",
        "retry_control_headers",
        "authorization_sha256",
        "q_state_present",
        "q_state_sha256",
        "adversarial_headers",
        "comparison_facts_sha256",
        "send_monotonic_ns",
        "receive_monotonic_ns",
        "client_response_status",
        "client_decision_digest",
    }
    if set(record) != expected:
        raise ControllerError("request record fields are not closed")
    if record["schema_version"] != "kil.v3b1-request.v1":
        raise ControllerError("request record schema is invalid")
    if (
        type(record["run_id"]) is not str
        or type(record["request_id"]) is not str
        or type(record["track"]) is not str
        or type(record["method"]) is not str
        or type(record["path"]) is not str
        or type(record["attempt_count"]) is not int
        or type(record["retry_observed"]) is not bool
        or type(record["retry_control_headers"]) is not dict
        or type(record["q_state_present"]) is not bool
        or type(record["adversarial_headers"]) is not dict
        or type(record["send_monotonic_ns"]) is not int
        or type(record["receive_monotonic_ns"]) is not int
        or type(record["client_response_status"]) is not int
    ):
        raise ControllerError("request record values are invalid")
    _require_sha256("authorization_sha256", record["authorization_sha256"])
    _require_sha256("comparison_facts_sha256", record["comparison_facts_sha256"])
    if record["q_state_sha256"] is not None:
        _require_sha256("q_state_sha256", record["q_state_sha256"])
    if record["client_decision_digest"] is not None:
        _require_sha256("client_decision_digest", record["client_decision_digest"])
    if record["adversarial_headers"] != ADVERSARIAL_HEADERS:
        raise ControllerError("request adversarial header record is invalid")
    if record["send_monotonic_ns"] < 0 or record["receive_monotonic_ns"] < record["send_monotonic_ns"]:
        raise ControllerError("request monotonic timing is invalid")


def _decision_closed(record: Mapping[str, object]) -> None:
    expected = {
        "schema_version",
        "request_id",
        "track",
        "method",
        "path",
        "outcome",
        "http_status",
        "decision_digest",
        "adapter_reasons",
        "engine_reasons",
        "untrusted_header_names",
        "monotonic_ns",
    }
    if set(record) != expected or record["schema_version"] != "kil.v3b-authz-record.v1":
        raise ControllerError("decision record fields are not closed")
    if (
        record["method"] != "POST"
        or record["path"] != "/consequential/admin"
        or record["outcome"] not in {"permit", "deny", "error"}
        or type(record["http_status"]) is not int
        or type(record["monotonic_ns"]) is not int
        or record["monotonic_ns"] < 0
    ):
        raise ControllerError("decision record values are invalid")
    allowed_adapter = {
        "untrusted_mode_header_ignored", "credential_invalid", "policy_denied",
        "baseline_permitted", "q_state_missing", "q_state_verification_failed",
    }
    allowed_engine = {
        "permitted", "identity_mismatch", "class_mismatch", "immutable_veto",
        "outside_environmental_envelope", "state_unauthentic",
        "state_not_yet_valid", "state_expired", "arithmetic_failure",
        "local_evidence_stale", "insufficient_charge", "insufficient_history",
    }
    allowed_untrusted = set(ADVERSARIAL_HEADERS)
    for name, allowed in (
        ("adapter_reasons", allowed_adapter),
        ("engine_reasons", allowed_engine),
        ("untrusted_header_names", allowed_untrusted),
    ):
        values = record[name]
        if (
            type(values) is not list
            or len(values) != len(set(values))
            or any(type(value) is not str or value not in allowed for value in values)
        ):
            raise ControllerError(f"decision {name} type/value/redaction is invalid")
    encoded = canonical_json(dict(record)).lower()
    if "bearer " in encoded or "eyj" in encoded or "authorization" in encoded:
        raise ControllerError("decision record redaction is invalid")


def _envoy_closed(record: Mapping[str, object]) -> None:
    expected = {
        "run_id",
        "request_id",
        "track",
        "response_code",
        "upstream_host",
        "upstream_service_time",
        "decision_digest",
    }
    if set(record) != expected:
        raise ControllerError("Envoy record fields are not closed")
    if any(type(record[name]) is not str for name in expected):
        raise ControllerError("Envoy record values are invalid")
    service_time = record["upstream_service_time"]
    if service_time != "-" and (
        len(service_time) > 20
        or re.fullmatch(r"0|[1-9][0-9]*", service_time) is None
    ):
        raise ControllerError("Envoy upstream service time is not canonical")


def _target_closed(record: Mapping[str, object]) -> None:
    expected = {
        "schema_version",
        "run_id",
        "request_id",
        "track",
        "path",
        "decision_digest",
        "received_monotonic_ns",
        "response_monotonic_ns",
    }
    if set(record) != expected or record["schema_version"] != "kil.v3b-target-record.v1":
        raise ControllerError("target record fields are not closed")
    if (
        type(record["path"]) is not str
        or type(record["received_monotonic_ns"]) is not int
        or type(record["response_monotonic_ns"]) is not int
        or record["received_monotonic_ns"] < 0
        or record["response_monotonic_ns"] < record["received_monotonic_ns"]
    ):
        raise ControllerError("target timestamps are invalid")


def _exact_digest(name: str, value: object) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ControllerError(f"{name} must be an exact decision digest")
    return value


def _join_evidence_records(
    manifest: Mapping[str, object],
    requests: Sequence[Mapping[str, object]],
    decisions: Sequence[Mapping[str, object]],
    envoy: Sequence[Mapping[str, object]],
    targets: Sequence[Mapping[str, object]],
    *,
    require_all_tracks: bool = True,
) -> list[dict[str, object]]:
    """Join closed records using an already validated evidence identity."""
    request_index = _index_unique("request", requests)
    decision_index = _index_unique("decision", decisions)
    envoy_index = _index_unique("envoy", envoy)
    target_index = _index_unique("target", targets)
    expected_tracks = list(_TRACKS) if require_all_tracks else [
        track for track in _TRACKS if (track.value, str(manifest["request_id"])) in request_index
    ]
    expected_keys = {
        (track.value, str(manifest["request_id"])) for track in expected_tracks
    }
    if set(request_index) != expected_keys:
        raise ControllerError("request evidence does not cover the fixed tracks exactly")
    if set(decision_index) != expected_keys or set(envoy_index) != expected_keys:
        raise ControllerError("decision and Envoy evidence must cover request keys exactly")
    if not set(target_index).issubset(expected_keys):
        raise ControllerError("target evidence contains an unplanned join key")
    joins = []
    comparison_hash: str | None = None
    for track in expected_tracks:
        key = (track.value, str(manifest["request_id"]))
        request = request_index[key]
        decision = decision_index[key]
        proxy = envoy_index[key]
        target = target_index.get(key)
        _request_closed(request)
        _decision_closed(decision)
        _envoy_closed(proxy)
        if target is not None:
            _target_closed(target)
        if request["run_id"] != manifest["run_id"]:
            raise ControllerError("request run_id does not match fixed manifest")
        if proxy["run_id"] != manifest["run_id"]:
            raise ControllerError("Envoy run_id does not match fixed manifest")
        if target is not None and target["run_id"] != manifest["run_id"]:
            raise ControllerError("target run_id does not match fixed manifest")
        if (
            request["attempt_count"] != 1
            or request["retry_observed"] is not False
            or request["retry_control_headers"] != RETRY_CONTROL_HEADERS
        ):
            raise ControllerError("retry evidence invalidates the run")
        if request["method"] != "POST" or request["path"] != "/consequential/admin":
            raise ControllerError("request facts are not the central case")
        if request["authorization_sha256"] != _digest_bytes(AUTHORIZATION.encode("utf-8")):
            raise ControllerError("request authorization digest is not fixed")
        expected_q_present = track is not LiveTrack.CREDENTIAL_POLICY_BASELINE
        if request["q_state_present"] is not expected_q_present or (
            expected_q_present and request["q_state_sha256"] is None
        ) or (not expected_q_present and request["q_state_sha256"] is not None):
            raise ControllerError("request Q-state presence does not match fixed track")
        projected = {
            "method": request["method"],
            "path": request["path"],
            "authorization_sha256": request["authorization_sha256"],
            "adversarial_headers": request["adversarial_headers"],
            "retry_control_headers": request["retry_control_headers"],
        }
        calculated_comparison = comparison_facts_sha256(projected)
        if request["comparison_facts_sha256"] != calculated_comparison:
            raise ControllerError("request comparison facts digest is invalid")
        if comparison_hash is None:
            comparison_hash = calculated_comparison
        elif comparison_hash != calculated_comparison:
            raise ControllerError("request comparison facts differ across tracks")
        if decision["method"] != request["method"] or decision["path"] != request["path"]:
            raise ControllerError("decision facts do not match request")
        if target is not None:
            if target["path"] != request["path"]:
                raise ControllerError("target path does not match central request path")
            if target["received_monotonic_ns"] > target["response_monotonic_ns"]:
                raise ControllerError("target timestamps are invalid")
        try:
            response_code = str(proxy["response_code"])
            if re.fullmatch(r"[1-9][0-9]{2}", response_code) is None:
                raise ValueError
            status = int(response_code)
        except ValueError as error:
            raise ControllerError("Envoy response code is invalid") from error
        if type(decision["http_status"]) is not int or decision["http_status"] != status:
            raise ControllerError("decision and Envoy HTTP statuses do not match")
        if request["client_response_status"] != status:
            raise ControllerError("client response status does not match observed boundary")
        upstream_raw = proxy["upstream_host"]
        if type(upstream_raw) is not str or not upstream_raw:
            raise ControllerError("Envoy upstream value is invalid")
        upstream = None if upstream_raw == "-" else upstream_raw
        service_raw = proxy["upstream_service_time"]
        if (upstream is None) != (service_raw == "-"):
            raise ControllerError("deny/upstream service time sentinel disagrees with upstream")
        upstream_service_time = None if service_raw == "-" else int(service_raw)
        proxy_digest_raw = proxy["decision_digest"]
        if status >= 500:
            proxy_digest = (
                None
                if proxy_digest_raw == "-"
                else _exact_digest("5xx Envoy decision_digest", proxy_digest_raw)
            )
        else:
            if proxy_digest_raw == "-":
                raise ControllerError(f"{status} Envoy digest cannot be the sentinel")
            proxy_digest = _exact_digest("Envoy decision_digest", proxy_digest_raw)
        decision_digest = decision["decision_digest"]
        marker_count = 1 if target is not None else 0
        outcome = decision["outcome"]
        if status == 200:
            if outcome != "permit" or upstream is None or target is None:
                raise ControllerError("permit requires KIL permit, upstream, and one target")
            digest = _exact_digest("decision_digest", decision_digest)
            target_digest = _exact_digest("target decision_digest", target["decision_digest"])
            if digest != proxy_digest or digest != target_digest:
                raise ControllerError("permit decision digest equality failed")
            if request["client_decision_digest"] != digest:
                raise ControllerError("client response decision digest does not match permit")
        elif status == 403:
            if outcome != "deny" or upstream is not None or target is not None:
                raise ControllerError("policy deny requires no upstream and zero targets")
            digest = _exact_digest("decision_digest", decision_digest)
            if digest != proxy_digest:
                raise ControllerError("policy deny decision digest equality failed")
            if request["client_decision_digest"] != digest:
                raise ControllerError("client response decision digest does not match deny")
        elif status >= 500:
            if outcome != "error" or upstream is not None or target is not None:
                raise ControllerError("authz error requires a KIL error and no forwarding")
            if proxy_digest_raw != "-" or proxy_digest is not None:
                raise ControllerError("5xx Envoy digest must be the raw sentinel")
            if request["client_decision_digest"] is not None:
                raise ControllerError("5xx client digest must be absent")
            if decision_digest is not None:
                _exact_digest("error decision_digest", decision_digest)
        else:
            raise ControllerError("unapproved evidence response status")
        joins.append(
            {
                "schema_version": JOIN_SCHEMA,
                "run_id": manifest["run_id"],
                "request_id": manifest["request_id"],
                "track": track.value,
                "outcome": outcome,
                "http_status": status,
                "decision_digest": decision_digest,
                "envoy_decision_digest": proxy_digest,
                "upstream_host": upstream,
                "upstream_service_time_ms": upstream_service_time,
                "client_response_status": request["client_response_status"],
                "client_decision_digest": request["client_decision_digest"],
                "target_marker_count": marker_count,
                "valid": True,
            }
        )
    if require_all_tracks:
        tuple_value = [
            (item["outcome"], item["http_status"], item["target_marker_count"])
            for item in joins
        ]
        if tuple_value != [
            ("permit", 200, 1),
            ("permit", 200, 1),
            ("deny", 403, 0),
        ]:
            raise ControllerError(
                "central result must be permit / permit / deny with 200 / 200 / 403 and 1 / 1 / 0 markers"
            )
        causal_reasons = {
            LiveTrack.CREDENTIAL_POLICY_BASELINE: (
                ["baseline_permitted"],
                [],
            ),
            LiveTrack.SIGNED_STATE_ONLY: (
                [],
                ["permitted"],
            ),
            LiveTrack.SIGNED_PLUS_LOCAL_REDUCE: (
                [],
                ["insufficient_charge"],
            ),
        }
        for track in _TRACKS:
            decision = decision_index[(track.value, str(manifest["request_id"]))]
            expected_adapter, expected_engine = causal_reasons[track]
            if (
                decision["adapter_reasons"] != expected_adapter
                or decision["engine_reasons"] != expected_engine
            ):
                raise ControllerError(
                    f"{track.value} decision reasons do not prove the fixed causal path"
                )
            if decision["untrusted_header_names"] != []:
                raise ControllerError(
                    f"{track.value} decision violates the filtered header boundary"
                )
    return joins


def join_evidence(
    manifest: dict[str, object],
    requests: Sequence[Mapping[str, object]],
    decisions: Sequence[Mapping[str, object]],
    envoy: Sequence[Mapping[str, object]],
    targets: Sequence[Mapping[str, object]],
    *,
    require_all_tracks: bool = True,
) -> list[dict[str, object]]:
    """Join closed records using manifest run, fixed track, and request ID."""
    _validate_manifest(manifest)
    return _join_evidence_records(
        manifest,
        requests,
        decisions,
        envoy,
        targets,
        require_all_tracks=require_all_tracks,
    )


def _jsonl_payload(records: Sequence[Mapping[str, object]]) -> bytes:
    return b"".join(_canonical_bytes(dict(record)) for record in records)


def _parse_jsonl_bytes(
    payload: bytes,
    label: str,
    validator: Callable[[Mapping[str, object]], None],
    *,
    allow_empty: bool,
) -> list[dict[str, object]]:
    if len(payload) > 64 * 1024 * 1024 or (payload and not payload.endswith(b"\n")):
        raise ControllerError(f"{label} is not bounded complete JSONL")
    if not payload and not allow_empty:
        raise ControllerError(f"{label} must not be empty")
    records = []
    for raw_line in payload.splitlines():
        if not raw_line or len(raw_line) > 128 * 1024:
            raise ControllerError(f"{label} contains an invalid record")
        record = _load_json_bytes(raw_line, label)
        try:
            validator(record)
            canonical_record = canonical_json(record)
        except ControllerError:
            raise
        except (TypeError, ValueError, UnicodeError, RecursionError) as error:
            raise ControllerError(f"{label} record validation failed") from error
        try:
            decoded_line = raw_line.decode("utf-8")
        except UnicodeError as error:
            raise ControllerError(f"{label} is not closed UTF-8 JSON") from error
        if decoded_line != canonical_record:
            raise ControllerError(f"{label} contains non-canonical JSON")
        records.append(record)
    return records


def _summary(manifest: Mapping[str, object], joins: Sequence[Mapping[str, object]]) -> str:
    teardown = manifest["teardown"]
    assert isinstance(teardown, dict)
    outcomes = " / ".join(str(item["outcome"]) for item in joins)
    markers = " / ".join(str(item["target_marker_count"]) for item in joins)
    return (
        "# KIL V3B-1 local Envoy boundary evidence\n\n"
        f"- Run ID: `{manifest['run_id']}`\n"
        f"- Evidence scope: `{EVIDENCE_SCOPE}`\n"
        f"- Outcomes: `{outcomes}`\n"
        f"- Target markers: `{markers}`\n"
        f"- Teardown: {teardown['status']}\n\n"
        "This bundle is limited to the local pinned Envoy authorization boundary. "
        "It does not establish cluster orchestration, past-event causality, or "
        "workload benchmarking.\n\n"
        f"{_KTP_CITATION}"
    )


_PRESENTER_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; "
    "font-src 'none'; media-src 'none'; object-src 'none'; script-src 'none'; "
    "connect-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
)
_PRESENTER_FORBIDDEN = (
    "/Users/",
    "/home/",
    "C:\\Users\\",
    "unix:///",
    "Bearer ",
    "v3b1-lab-credential",
    "compact_jws",
)
_PUBLIC_COMMITMENT_SCHEMA = "kil.v3b1-public-commitment.v1"
_PUBLIC_COMMITMENT_SCHEMA_V2 = "kil.v3b1-public-commitment.v2"
_PUBLIC_COMMITMENT_RULE = (
    "sha256_of_canonical_manifest_without_public_commitment_sha256_and_"
    "all_public_file_sha256_except_manifest_and_SHA256SUMS"
)


def _presenter_safe_text(label: str, value: object) -> str:
    if type(value) is not str or not value:
        raise ControllerError(f"presenter {label} is invalid")
    if any(token.lower() in value.lower() for token in _PRESENTER_FORBIDDEN):
        raise ControllerError(f"presenter {label} contains private material")
    return value


def _presenter_model(
    manifest: Mapping[str, object],
    decisions: Sequence[Mapping[str, object]],
    joins: Sequence[Mapping[str, object]],
) -> PresenterModel:
    run_id = _presenter_safe_text("run_id", manifest.get("run_id"))
    request_id = _presenter_safe_text("request_id", manifest.get("request_id"))
    evidence_scope = _presenter_safe_text(
        "evidence_scope", manifest.get("evidence_scope")
    )
    source_commit = _presenter_safe_text(
        "source_commit", manifest.get("source_commit")
    )
    if evidence_scope != EVIDENCE_SCOPE:
        raise ControllerError("presenter evidence scope is invalid")
    if re.fullmatch(r"v3b1-[a-f0-9]{64}", run_id) is None:
        raise ControllerError("presenter run_id is invalid")
    if re.fullmatch(r"[a-f0-9]{40}", source_commit) is None:
        raise ControllerError("presenter source commit is invalid")
    if not joins:
        return PresenterModel(
            run_id, request_id, evidence_scope, source_commit, (), False
        )
    decisions_by_track = {
        str(item.get("track")): item for item in decisions
    }
    joins_by_track = {str(item.get("track")): item for item in joins}
    if (
        len(decisions_by_track) != len(decisions)
        or len(joins_by_track) != len(joins)
        or set(decisions_by_track) != {track.value for track in _TRACKS}
        or set(joins_by_track) != {track.value for track in _TRACKS}
    ):
        raise ControllerError("presenter records do not cover fixed tracks exactly")
    tracks: list[PresenterTrack] = []
    for track in _TRACKS:
        decision = decisions_by_track[track.value]
        join = joins_by_track[track.value]
        if (
            join.get("run_id") != run_id
            or join.get("request_id") != request_id
            or join.get("valid") is not True
            or decision.get("run_id") != run_id
            or decision.get("request_id") != request_id
        ):
            raise ControllerError("presenter record identity or validity is invalid")
        if decision.get("untrusted_header_names") != []:
            raise ControllerError("presenter decision contains untrusted headers")
        outcome = _presenter_safe_text("outcome", join.get("outcome"))
        http_status = join.get("http_status")
        marker_count = join.get("target_marker_count")
        decision_digest = _presenter_safe_text(
            "decision_digest", join.get("decision_digest")
        )
        normalized_decision_digest = _exact_digest(
            "presenter normalized decision_digest",
            decision.get("decision_digest"),
        )
        if (
            decision_digest != normalized_decision_digest
            or decision.get("outcome") != outcome
            or decision.get("http_status") != http_status
        ):
            raise ControllerError("presenter decision and join do not match")
        upstream = join.get("upstream_host")
        adapter_reasons = decision.get("adapter_reasons")
        engine_reasons = decision.get("engine_reasons")
        if (
            type(http_status) is not int
            or type(marker_count) is not int
            or upstream is not None and type(upstream) is not str
            or type(adapter_reasons) is not list
            or type(engine_reasons) is not list
            or any(type(item) is not str for item in adapter_reasons)
            or any(type(item) is not str for item in engine_reasons)
        ):
            raise ControllerError("presenter record values are invalid")
        safe_adapter = tuple(
            _presenter_safe_text("adapter reason", item) for item in adapter_reasons
        )
        safe_engine = tuple(
            _presenter_safe_text("engine reason", item) for item in engine_reasons
        )
        tracks.append(
            PresenterTrack(
                track.value,
                outcome,
                http_status,
                marker_count,
                upstream is not None,
                decision_digest,
                safe_adapter,
                safe_engine,
            )
        )
    expected = (
        ("permit", 200, 1, True),
        ("permit", 200, 1, True),
        ("deny", 403, 0, False),
    )
    observed = tuple(
        (
            item.outcome,
            item.http_status,
            item.target_marker_count,
            item.forwarded,
        )
        for item in tracks
    )
    if observed != expected:
        raise ControllerError("presenter result is not the fixed local boundary proof")
    causal = tuple(
        (item.adapter_reasons, item.engine_reasons) for item in tracks
    )
    if causal != (
        (("baseline_permitted",), ()),
        ((), ("permitted",)),
        ((), ("insufficient_charge",)),
    ):
        raise ControllerError("presenter causal reasons are not the fixed proof")
    return PresenterModel(
        run_id, request_id, evidence_scope, source_commit, tuple(tracks), True
    )


def _render_live_html(model: PresenterModel) -> bytes:
    if not isinstance(model, PresenterModel):
        raise ControllerError("presenter model is invalid")
    run_id = escape(_presenter_safe_text("run_id", model.run_id), quote=True)
    source_commit = escape(
        _presenter_safe_text("source_commit", model.source_commit), quote=True
    )
    if model.complete:
        cards = []
        for item in model.tracks:
            reasons = ", ".join((*item.adapter_reasons, *item.engine_reasons)) or "none"
            cards.append(
                "<article class=\"track-card\">"
                f"<h2>{escape(item.track, quote=True)}</h2>"
                f"<p class=\"outcome\">{escape(item.outcome.upper(), quote=True)}</p>"
                f"<dl><dt>HTTP</dt><dd>{item.http_status}</dd>"
                f"<dt>Target markers</dt><dd>{item.target_marker_count}</dd>"
                f"<dt>Upstream</dt><dd>{'forwarded' if item.forwarded else 'withheld'}</dd>"
                f"<dt>Reason</dt><dd>{escape(reasons, quote=True)}</dd>"
                f"<dt>Decision digest</dt><dd><code>{escape(item.decision_digest, quote=True)}</code></dd>"
                "</dl></article>"
            )
        result = (
            "<p class=\"result\">PERMIT / PERMIT / DENY</p>"
            "<p class=\"markers\">TARGET MARKERS · 1 / 1 / 0</p>"
            f"<section class=\"tracks\">{''.join(cards)}</section>"
        )
    else:
        result = (
            "<section class=\"incomplete\"><h2>INCOMPLETE · NOT PRESENTABLE</h2>"
            "<p>No partial outcome is represented by this derived page.</p></section>"
        )
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{escape(_PRESENTER_CSP, quote=True)}">
<title>KIL V3B-1 — Local Envoy Boundary</title>
<style>
:root {{ color-scheme: dark; }}
body {{ margin: 0; background: #07131f; color: #e2e8f0; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 36px 24px 60px; }}
h1 {{ margin-bottom: 8px; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.badge {{ border: 1px solid #38bdf8; border-radius: 999px; padding: 7px 11px; font-weight: 700; }}
.warning {{ border-color: #f59e0b; color: #fde68a; }}
.result {{ color: #a7f3d0; font-size: 28px; font-weight: 900; }}
.markers {{ color: #bae6fd; font-weight: 800; }}
.tracks {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
.track-card {{ border: 1px solid #334155; border-radius: 14px; padding: 16px; background: #0b1f33; overflow-wrap: anywhere; }}
.outcome {{ font-size: 24px; font-weight: 900; }}
dt {{ color: #94a3b8; margin-top: 8px; }} dd {{ margin-left: 0; }}
.boundary, .incomplete {{ margin-top: 24px; border: 1px solid #f59e0b; padding: 16px; border-radius: 12px; }}
code {{ overflow-wrap: anywhere; }}
@media (max-width: 820px) {{ .tracks {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body><main>
<h1>KIL V3B-1 — Local Envoy Boundary</h1>
<div class="badges">
<span class="badge">OBSERVED · LOCAL ENVOY AUTHORIZATION BOUNDARY</span>
<span class="badge warning">INTERMEDIATE · NOT PROMOTED</span>
<span class="badge">MODELED INPUTS · OBSERVED OUTPUTS</span>
</div>
<p>Run <code>{run_id}</code> · source <code>{source_commit}</code></p>
{result}
<section class="boundary">
<strong>DERIVED PRESENTER · JSONL + manifest.json + SHA256SUMS CONTROL</strong>
<p>VERIFY THE BUNDLE BEFORE PRESENTATION; THIS PAGE DOES NOT ATTEST TEARDOWN BY ITSELF.</p>
<p>DOES NOT ESTABLISH KIND ORCHESTRATION, KUBERNETES NETWORKPOLICY, HISTORICAL INCIDENT PREVENTION, OR PRODUCTION PERFORMANCE.</p>
</section>
</main></body></html>
"""
    payload = html.encode("utf-8")
    if len(payload) > 256 * 1024:
        raise ControllerError("presenter output exceeds its byte bound")
    encoded = html.lower()
    if any(token.lower() in encoded for token in _PRESENTER_FORBIDDEN):
        raise ControllerError("presenter output contains private material")
    return payload


def _write_sums(output: Path) -> None:
    paths = [output / name for name in _EVIDENCE_FILES]
    raw_root = output / "raw/decisions"
    if raw_root.is_dir():
        paths.extend(sorted(raw_root.glob("*.jsonl")))
    lines = []
    for path in sorted(paths, key=lambda item: item.relative_to(output).as_posix()):
        if not path.is_file() or path.is_symlink():
            raise ControllerError("evidence checksum input is missing or unsafe")
        relative = path.relative_to(output).as_posix()
        lines.append(f"{_digest_bytes(path.read_bytes())}  {relative}\n")
    _write_file(output / "SHA256SUMS", "".join(lines).encode("utf-8"), 0o444)


def _verify_sums(output: Path) -> None:
    path = output / "SHA256SUMS"
    if path.is_symlink() or not path.is_file():
        raise ControllerError("evidence checksum file is missing or unsafe")
    seen = set()
    for line in path.read_text(encoding="ascii").splitlines():
        if "  " not in line:
            raise ControllerError("evidence checksum line is malformed")
        digest, relative = line.split("  ", 1)
        _require_sha256("evidence checksum", digest)
        if (
            not relative
            or relative.startswith("/")
            or ".." in Path(relative).parts
            or relative in seen
        ):
            raise ControllerError("evidence checksum path is invalid")
        seen.add(relative)
        target = output / relative
        if target.is_symlink() or not target.is_file():
            raise ControllerError("checksummed evidence file is missing or unsafe")
        if _digest_bytes(target.read_bytes()) != digest:
            raise ControllerError("evidence checksum mismatch")


def verify_public_checksums(output: Path) -> None:
    """Verify SHA256SUMS is sorted and covers every other public file exactly."""
    if output.is_symlink() or not output.is_dir():
        raise ControllerError("public evidence directory is missing or unsafe")
    checksum_path = output / "SHA256SUMS"
    if checksum_path.is_symlink() or not checksum_path.is_file():
        raise ControllerError("public checksum file is missing or unsafe")
    expected_files = []
    for path in output.rglob("*"):
        if path == checksum_path:
            continue
        if path.is_symlink():
            raise ControllerError("public evidence contains an unchecked symbolic link")
        if path.is_file():
            expected_files.append(path.relative_to(output).as_posix())
        elif not path.is_dir():
            raise ControllerError("public evidence contains an unsafe unchecked object")
    expected_files.sort()
    lines = checksum_path.read_text(encoding="ascii").splitlines()
    recorded: list[str] = []
    for line in lines:
        if "  " not in line:
            raise ControllerError("public checksum line is malformed")
        digest, relative = line.split("  ", 1)
        _require_sha256("public checksum", digest)
        if not relative or relative.startswith("/") or ".." in Path(relative).parts:
            raise ControllerError("public checksum path is invalid")
        target = output / relative
        if target.is_symlink() or not target.is_file():
            raise ControllerError("public checksum target is missing or unsafe")
        if _digest_file(target) != digest:
            raise ControllerError("public checksum mismatch")
        recorded.append(relative)
    if recorded != sorted(recorded):
        raise ControllerError("public checksum entries are not sorted")
    if recorded != expected_files:
        raise ControllerError("public checksum set is incomplete: unchecked file or omission")


def _snapshot_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_stable_public_file_at(
    directory_fd: int,
    name: str,
    *,
    maximum_bytes: int = 64 * 1024 * 1024,
) -> tuple[bytes, tuple[int, int, int, int, int]]:
    if not name or "/" in name or name in {".", ".."}:
        raise ControllerError("public evidence file name is invalid")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as error:
        raise ControllerError("public evidence file is missing or unsafe") from error
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > maximum_bytes:
            raise ControllerError("public evidence file is not a bounded regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise ControllerError("public evidence file exceeds its byte bound")
        finished = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        current = os.stat(
            name, dir_fd=directory_fd, follow_symlinks=False
        )
    except OSError as error:
        raise ControllerError("public evidence file changed during snapshot") from error
    identity = _snapshot_identity(opened)
    if (
        identity != _snapshot_identity(finished)
        or identity != _snapshot_identity(current)
    ):
        raise ControllerError("public evidence file changed during snapshot")
    return b"".join(chunks), identity


def _public_bundle_snapshot(
    output: Path,
    *,
    validator: Callable[[dict[str, bytes]], object] | None = None,
    before_completion: Callable[[], None] | None = None,
    complete: Callable[[dict[str, bytes]], None] | None = None,
    after_completion: Callable[[], None] | None = None,
) -> object:
    if output.is_symlink() or not output.is_dir():
        raise ControllerError("public evidence directory is missing or unsafe")
    expected = _authoritative_file_names()
    root_names = set(_EVIDENCE_FILES) | {"SHA256SUMS", "raw"}
    raw_decision_names = {f"{track.value}.jsonl" for track in _TRACKS}
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    root_fd = raw_fd = decisions_fd = -1
    try:
        try:
            root_fd = os.open(output, directory_flags)
            root_opened = os.fstat(root_fd)
            raw_fd = os.open("raw", directory_flags, dir_fd=root_fd)
            raw_opened = os.fstat(raw_fd)
            decisions_fd = os.open(
                "decisions", directory_flags, dir_fd=raw_fd
            )
            decisions_opened = os.fstat(decisions_fd)
        except OSError as error:
            raise ControllerError(
                "public evidence directory component is missing or unsafe"
            ) from error
        if not all(
            stat.S_ISDIR(item.st_mode)
            for item in (root_opened, raw_opened, decisions_opened)
        ):
            raise ControllerError("public evidence component is not a directory")
        root_identity = _snapshot_identity(root_opened)
        raw_identity = _snapshot_identity(raw_opened)
        decisions_identity = _snapshot_identity(decisions_opened)
        if (
            set(os.listdir(root_fd)) != root_names
            or set(os.listdir(raw_fd)) != {"decisions"}
            or set(os.listdir(decisions_fd)) != raw_decision_names
        ):
            raise ControllerError("public evidence artifact set is not closed")
        if raw_identity != _snapshot_identity(
            os.stat("raw", dir_fd=root_fd, follow_symlinks=False)
        ) or decisions_identity != _snapshot_identity(
            os.stat("decisions", dir_fd=raw_fd, follow_symlinks=False)
        ):
            raise ControllerError("public evidence directory identity is unstable")
        payloads: dict[str, bytes] = {}
        identities: dict[str, tuple[int, str, tuple[int, int, int, int, int]]] = {}
        for relative in sorted(expected):
            if relative.startswith("raw/decisions/"):
                directory_fd = decisions_fd
                name = relative.rsplit("/", 1)[1]
            else:
                directory_fd = root_fd
                name = relative
            maximum = (
                1024 * 1024
                if relative in {"SHA256SUMS", "manifest.json", "live.html"}
                else 64 * 1024 * 1024
            )
            payloads[relative], identity = _read_stable_public_file_at(
                directory_fd, name, maximum_bytes=maximum
            )
            identities[relative] = (directory_fd, name, identity)
        try:
            checksum_text = payloads["SHA256SUMS"].decode("ascii")
        except UnicodeError as error:
            raise ControllerError(
                "public checksum file is not closed ASCII"
            ) from error
        recorded: list[str] = []
        for line in checksum_text.splitlines():
            if "  " not in line:
                raise ControllerError("public checksum line is malformed")
            digest, relative = line.split("  ", 1)
            _require_sha256("public checksum", digest)
            if relative not in expected or relative == "SHA256SUMS":
                raise ControllerError("public checksum path is invalid")
            if _digest_bytes(payloads[relative]) != digest:
                raise ControllerError("public checksum mismatch")
            recorded.append(relative)
        if recorded != sorted(expected - {"SHA256SUMS"}):
            raise ControllerError(
                "public checksum set is incomplete or unsorted"
            )
        if (
            root_identity != _snapshot_identity(os.fstat(root_fd))
            or raw_identity != _snapshot_identity(os.fstat(raw_fd))
            or decisions_identity != _snapshot_identity(os.fstat(decisions_fd))
            or set(os.listdir(root_fd)) != root_names
            or set(os.listdir(raw_fd)) != {"decisions"}
            or set(os.listdir(decisions_fd)) != raw_decision_names
        ):
            raise ControllerError("public evidence inventory changed during snapshot")
        try:
            root_path = os.stat(output, follow_symlinks=False)
            raw_path = os.stat("raw", dir_fd=root_fd, follow_symlinks=False)
            decisions_path = os.stat(
                "decisions", dir_fd=raw_fd, follow_symlinks=False
            )
        except OSError as error:
            raise ControllerError(
                "public evidence directory changed during snapshot"
            ) from error
        if (
            root_identity != _snapshot_identity(root_path)
            or raw_identity != _snapshot_identity(raw_path)
            or decisions_identity != _snapshot_identity(decisions_path)
        ):
            raise ControllerError("public evidence directory changed during snapshot")
        for directory_fd, name, identity in identities.values():
            try:
                current = os.stat(
                    name, dir_fd=directory_fd, follow_symlinks=False
                )
            except OSError as error:
                raise ControllerError(
                    "public evidence changed after snapshot"
                ) from error
            if identity != _snapshot_identity(current):
                raise ControllerError("public evidence changed after snapshot")
        def recheck_snapshot(stage: str) -> None:
            if (
                root_identity != _snapshot_identity(os.fstat(root_fd))
                or raw_identity != _snapshot_identity(os.fstat(raw_fd))
                or decisions_identity
                != _snapshot_identity(os.fstat(decisions_fd))
                or set(os.listdir(root_fd)) != root_names
                or set(os.listdir(raw_fd)) != {"decisions"}
                or set(os.listdir(decisions_fd)) != raw_decision_names
            ):
                raise ControllerError(
                    f"public evidence inventory changed {stage}"
                )
            try:
                if root_identity != _snapshot_identity(
                    os.stat(output, follow_symlinks=False)
                ):
                    raise ControllerError(
                        f"public evidence directory changed {stage}"
                    )
                if raw_identity != _snapshot_identity(
                    os.stat("raw", dir_fd=root_fd, follow_symlinks=False)
                ) or decisions_identity != _snapshot_identity(
                    os.stat("decisions", dir_fd=raw_fd, follow_symlinks=False)
                ):
                    raise ControllerError(
                        f"public evidence directory identity changed {stage}"
                    )
                for directory_fd, name, identity in identities.values():
                    if identity != _snapshot_identity(
                        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    ):
                        raise ControllerError(
                            f"public evidence file identity changed {stage}"
                        )
            except OSError as error:
                raise ControllerError(
                    f"public evidence changed {stage}"
                ) from error

        result = payloads if validator is None else validator(payloads)
        if before_completion is not None:
            before_completion()
        recheck_snapshot("after validation")
        if complete is not None:
            complete(payloads)
        recheck_snapshot("during completion")
        if after_completion is not None:
            after_completion()
        recheck_snapshot("after completion cleanup")
        return result
    except OSError as error:
        raise ControllerError(
            "public evidence changed during snapshot"
        ) from error
    finally:
        for descriptor in (decisions_fd, raw_fd, root_fd):
            if descriptor >= 0:
                os.close(descriptor)


def _validate_public_manifest_v1(
    value: Mapping[str, object],
    payloads: Mapping[str, bytes],
    *,
    completed: bool = True,
) -> None:
    _reject_public_secrets(value)
    expected = {
        "schema_version", "run_id", "request_id", "evidence_scope",
        "bundle_class", "promotion_status", "run_complete", "platform",
        "source_commit", "content_identity_sha256", "content_identity",
        "immutable_images", "build_inputs", "verified_tool_identities",
        "docker_engine_provenance", "global_context_attestation",
        "evidence_policy", "source_attestations", "artifact_hash_rule",
        "artifact_sha256", "public_commitment_rule",
        "public_commitment_sha256", "teardown",
        "claim_exclusions",
    }
    if type(value) is not dict or set(value) != expected:
        raise ControllerError("public manifest fields are not closed")
    if (
        value["schema_version"] != "kil.v3b1-public-manifest.v1"
        or type(value["run_id"]) is not str
        or re.fullmatch(r"v3b1-[a-f0-9]{64}", value["run_id"]) is None
        or value["request_id"] != REQUEST_ID
        or value["evidence_scope"] != EVIDENCE_SCOPE
        or value["bundle_class"]
        != (
            "intermediate_provisional_local_boundary"
            if completed
            else "intermediate_provisional_failure_local_boundary"
        )
        or value["promotion_status"] != "not_promoted"
        or value["run_complete"] is not completed
        or value["platform"] != PLATFORM
        or type(value["source_commit"]) is not str
        or re.fullmatch(r"[a-f0-9]{40}", value["source_commit"]) is None
    ):
        raise ControllerError("public manifest is not an accepted local boundary run")
    for name in ("content_identity_sha256", "public_commitment_sha256"):
        _require_sha256(f"public manifest {name}", value[name])
    identity = value["content_identity"]
    identity_fields = {
        "schema_version", "profile_sha256", "colima_profile",
        "docker_endpoint", "platform", "source_commit",
        "execution_nonce_sha256", "dockerfile_sha256",
        "dockerignore_sha256", "build_context_sha256",
        "python_image_digest", "envoy_image_digest", "envoy_image_id",
        "kil_image_id", "kil_archive_sha256", "request_id", "tracks",
    }
    if type(identity) is not dict or set(identity) != identity_fields:
        raise ControllerError("public content identity fields are not closed")
    if identity["schema_version"] != "kil.v3b1-content-identity.v2":
        raise ControllerError("public content identity schema is invalid")
    for name in (
        "profile_sha256", "execution_nonce_sha256", "dockerfile_sha256",
        "dockerignore_sha256", "build_context_sha256",
    ):
        _require_sha256(f"public content identity {name}", identity[name])
    _require_digest_ref(
        "public content identity Python image", identity["python_image_digest"]
    )
    _require_digest_ref(
        "public content identity Envoy image", identity["envoy_image_digest"]
    )
    for name in ("envoy_image_id", "kil_image_id"):
        if type(identity[name]) is not str or _IMAGE_ID.fullmatch(identity[name]) is None:
            raise ControllerError("public content identity image ID is invalid")
    _require_sha256(
        "public content identity KIL archive", identity["kil_archive_sha256"]
    )
    if identity["docker_endpoint"] != {
        "transport": "unix",
        "logical_locator": "colima_profile_socket",
        "profile": LAB_IDENTITY,
    }:
        raise ControllerError("public content identity endpoint is invalid")
    if (
        identity["colima_profile"] != LAB_IDENTITY
        or identity["platform"] != value["platform"]
        or identity["source_commit"] != value["source_commit"]
        or identity["request_id"] != value["request_id"]
        or identity["tracks"]
        != [
            {"track": track.value, "gateway_port": port}
            for track, port in zip(_TRACKS, (18080, 18081, 18082), strict=True)
        ]
    ):
        raise ControllerError("public content identity cross-binding is invalid")
    identity_digest = _digest_bytes(canonical_json(identity).encode("utf-8"))
    if (
        value["content_identity_sha256"] != identity_digest
        or value["run_id"] != f"v3b1-{identity_digest}"
    ):
        raise ControllerError("public run identity does not match content identity")
    immutable = value["immutable_images"]
    if type(immutable) is not dict or set(immutable) != {
        "python", "envoy_digest", "envoy_image_id", "kil_image_id",
        "kil_archive_sha256",
    }:
        raise ControllerError("public immutable image fields are not closed")
    _require_digest_ref("public python image", immutable["python"])
    _require_digest_ref("public Envoy digest", immutable["envoy_digest"])
    for name in ("envoy_image_id", "kil_image_id"):
        if type(immutable[name]) is not str or _IMAGE_ID.fullmatch(immutable[name]) is None:
            raise ControllerError("public image ID is invalid")
    _require_sha256("public KIL archive", immutable["kil_archive_sha256"])
    if (
        identity["python_image_digest"] != immutable["python"]
        or identity["envoy_image_digest"] != immutable["envoy_digest"]
        or any(
            identity[name] != immutable[name]
            for name in (
                "envoy_image_id", "kil_image_id", "kil_archive_sha256",
            )
        )
    ):
        raise ControllerError("public content identity image pins diverge")
    build = value["build_inputs"]
    if type(build) is not dict or set(build) != {
        "dockerfile_sha256", "dockerignore_sha256", "build_context_sha256",
        "context_strategy",
    } or build["context_strategy"] != "controller_exact_allowlist_for_legacy_builder":
        raise ControllerError("public build inputs are not closed")
    for name in ("dockerfile_sha256", "dockerignore_sha256", "build_context_sha256"):
        _require_sha256(f"public build input {name}", build[name])
        if identity[name] != build[name]:
            raise ControllerError("public content identity build pins diverge")
    tools = value["verified_tool_identities"]
    engine = value["docker_engine_provenance"]
    if type(tools) is not dict or type(engine) is not dict:
        raise ControllerError("public provenance is invalid")
    _validate_public_provenance(tools, engine)
    context = value["global_context_attestation"]
    if type(context) is not dict or set(context) != {"before", "after", "unchanged"} or context["unchanged"] is not True or context["before"] != context["after"] or type(context["before"]) is not str:
        raise ControllerError("public global context attestation is invalid")
    _validate_global_context(
        "public global Docker context", context["before"]
    )
    if value["evidence_policy"] != {"inputs": "modeled", "outputs": "observed"}:
        raise ControllerError("public evidence policy is invalid")
    sources = value["source_attestations"]
    if type(sources) is not list:
        raise ControllerError("public source attestations are invalid")
    _validate_source_attestations(sources, completed=completed)
    if not completed and sources:
        raise ControllerError("failure public source attestations must be empty")
    if value["artifact_hash_rule"] != "sha256_excludes_manifest_summary_and_SHA256SUMS":
        raise ControllerError("public artifact hash rule is invalid")
    hashes = value["artifact_sha256"]
    hash_names = _authoritative_file_names() - {
        "manifest.json", "summary.md", "SHA256SUMS"
    }
    if type(hashes) is not dict or set(hashes) != hash_names:
        raise ControllerError("public artifact hash map is incomplete")
    for relative in sorted(hash_names):
        _require_sha256("public artifact digest", hashes[relative])
        if hashes[relative] != _digest_bytes(payloads[relative]):
            raise ControllerError("public artifact digest mismatch")
    teardown = value["teardown"]
    if teardown != {"status": "complete", "verified_before_publication": True}:
        raise ControllerError("public teardown attestation is incomplete")
    if value["claim_exclusions"] != [
        "kind_cluster_validated", "historical_prevention",
        "production_performance", "network_policy_validation",
    ]:
        raise ControllerError("public claim exclusions are invalid")
    if value["public_commitment_rule"] != _PUBLIC_COMMITMENT_RULE:
        raise ControllerError("public commitment rule is invalid")
    if value["public_commitment_sha256"] != _public_commitment_sha256(
        value, payloads
    ):
        raise ControllerError("public commitment does not bind the snapshot")


def _validate_public_manifest_v2(
    value: Mapping[str, object],
    payloads: Mapping[str, bytes],
    *,
    completed: bool = True,
) -> None:
    """Validate the driver-era public manifest without widening v1."""
    if type(value) is not dict or value.get("schema_version") != (
        "kil.v3b1-public-manifest.v2"
    ):
        raise ControllerError("public manifest schema is invalid")
    identity = value.get("content_identity")
    identity_fields = {
        "schema_version", "profile_sha256", "colima_profile",
        "docker_endpoint", "platform", "source_commit",
        "execution_nonce_sha256", "dockerfile_sha256",
        "dockerignore_sha256", "build_context_sha256",
        "python_image_digest", "envoy_image_digest", "envoy_image_id",
        "kil_image_id", "kil_archive_sha256", "request_id",
        "driver_endpoint", "segment_definitions", "driver_definition_sha256",
    }
    if type(identity) is not dict or set(identity) != identity_fields:
        raise ControllerError("public content identity fields are not closed")
    if identity["schema_version"] != "kil.v3b1-content-identity.v3":
        raise ControllerError("public content identity schema is invalid")
    for name in (
        "profile_sha256", "execution_nonce_sha256", "dockerfile_sha256",
        "dockerignore_sha256", "build_context_sha256",
    ):
        _require_sha256(f"public content identity {name}", identity[name])
    if identity["docker_endpoint"] != {
        "transport": "unix",
        "logical_locator": "colima_profile_socket",
        "profile": LAB_IDENTITY,
    }:
        raise ControllerError("public content identity endpoint is invalid")
    if identity["driver_endpoint"] != {
        "transport": "tcp", "host": "envoy", "port": 8080,
    }:
        raise ControllerError("public driver endpoint is invalid")
    if identity["segment_definitions"] != _segment_definitions():
        raise ControllerError("public segment definitions are invalid")
    hashes = identity["driver_definition_sha256"]
    if (
        type(hashes) is not list
        or len(hashes) != len(_TRACKS)
        or [item.get("track") for item in hashes if type(item) is dict]
        != [track.value for track in _TRACKS]
        or any(
            type(item) is not dict
            or set(item) != {"track", "sha256"}
            for item in hashes
        )
    ):
        raise ControllerError("public driver definition hashes are invalid")
    for item in hashes:
        _require_sha256("public driver definition", item["sha256"])
    if (
        identity["colima_profile"] != LAB_IDENTITY
        or identity["platform"] != value.get("platform")
        or identity["source_commit"] != value.get("source_commit")
        or identity["request_id"] != value.get("request_id")
    ):
        raise ControllerError("public content identity cross-binding is invalid")
    identity_digest = _digest_bytes(canonical_json(identity).encode("utf-8"))
    if (
        value.get("content_identity_sha256") != identity_digest
        or value.get("run_id") != f"v3b1-{identity_digest}"
    ):
        raise ControllerError("public run identity does not match content identity")

    # Reuse the unchanged v1 validator for every common closed field by
    # projecting only the version-specific identity and commitment inputs.
    projected = dict(value)
    projected["schema_version"] = "kil.v3b1-public-manifest.v1"
    legacy_identity = {
        key: identity[key]
        for key in (
            "profile_sha256", "colima_profile", "docker_endpoint", "platform",
            "source_commit", "execution_nonce_sha256", "dockerfile_sha256",
            "dockerignore_sha256", "build_context_sha256",
            "python_image_digest", "envoy_image_digest", "envoy_image_id",
            "kil_image_id", "kil_archive_sha256", "request_id",
        )
    }
    legacy_identity["schema_version"] = "kil.v3b1-content-identity.v2"
    legacy_identity["tracks"] = [
        {"track": track.value, "gateway_port": port}
        for track, port in zip(_TRACKS, _TRACK_PORTS.values(), strict=True)
    ]
    legacy_digest = _digest_bytes(canonical_json(legacy_identity).encode("utf-8"))
    projected["content_identity"] = legacy_identity
    projected["content_identity_sha256"] = legacy_digest
    projected["run_id"] = f"v3b1-{legacy_digest}"
    projected["public_commitment_sha256"] = _public_commitment_sha256(
        projected, payloads
    )
    _validate_public_manifest_v1(projected, payloads, completed=completed)
    if value.get("public_commitment_sha256") != _public_commitment_sha256(
        value, payloads
    ):
        raise ControllerError("public commitment does not bind the snapshot")


def _validate_public_manifest(
    value: Mapping[str, object],
    payloads: Mapping[str, bytes],
    *,
    completed: bool = True,
) -> None:
    """Dispatch public manifests with no legacy/new field union."""
    if type(value) is not dict:
        raise ControllerError("public manifest fields are not closed")
    schema = value.get("schema_version")
    if schema == "kil.v3b1-public-manifest.v1":
        _validate_public_manifest_v1(value, payloads, completed=completed)
        return
    if schema == "kil.v3b1-public-manifest.v2":
        _validate_public_manifest_v2(value, payloads, completed=completed)
        return
    raise ControllerError("public manifest schema is invalid")


def _normalized_presenter_decision_closed(record: Mapping[str, object]) -> None:
    _normalized_presenter_source(record)


def _normalized_presenter_source(
    record: Mapping[str, object],
) -> dict[str, object]:
    if (
        record.get("schema_version") != "kil.v3b1-collected-decision.v1"
        or record.get("run_id_provenance") != "manifest_attested_enrichment"
        or type(record.get("source_schema_version")) is not str
    ):
        raise ControllerError("presenter decision provenance is invalid")
    source = {
        "schema_version": record["source_schema_version"],
        **{
            key: value for key, value in record.items()
            if key not in {
                "schema_version", "source_schema_version", "source_record_sha256",
                "run_id_provenance", "run_id",
            }
        },
    }
    _decision_closed(source)
    if record.get("source_record_sha256") != _digest_bytes(
        canonical_json(source).encode("utf-8")
    ):
        raise ControllerError("presenter decision source digest is invalid")
    return source


def _presenter_join_closed(record: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "run_id", "request_id", "track", "outcome",
        "http_status", "decision_digest", "envoy_decision_digest",
        "upstream_host", "upstream_service_time_ms", "client_response_status",
        "client_decision_digest", "target_marker_count", "valid",
    }
    if set(record) != expected or record.get("schema_version") != JOIN_SCHEMA:
        raise ControllerError("presenter join fields are not closed")
    if (
        record.get("track") not in {track.value for track in _TRACKS}
        or record.get("outcome") not in {"permit", "deny"}
        or type(record.get("http_status")) is not int
        or type(record.get("client_response_status")) is not int
        or type(record.get("target_marker_count")) is not int
        or record.get("valid") is not True
    ):
        raise ControllerError("presenter join values are invalid")
    decision_digest = _exact_digest(
        "presenter decision_digest", record["decision_digest"]
    )
    envoy_digest = _exact_digest(
        "presenter Envoy decision_digest", record["envoy_decision_digest"]
    )
    client_digest = _exact_digest(
        "presenter client decision_digest", record["client_decision_digest"]
    )
    if not decision_digest == envoy_digest == client_digest:
        raise ControllerError("presenter join decision digests do not match")
    if record["client_response_status"] != record["http_status"]:
        raise ControllerError("presenter join response statuses do not match")
    if record["outcome"] == "permit":
        if (
            record["http_status"] != 200
            or record["target_marker_count"] != 1
            or type(record["upstream_host"]) is not str
            or not record["upstream_host"]
            or type(record["upstream_service_time_ms"]) is not int
            or record["upstream_service_time_ms"] < 0
        ):
            raise ControllerError("presenter permit join is invalid")
        upstream = _presenter_safe_text("upstream host", record["upstream_host"])
        host, separator, port = upstream.rpartition(":")
        octets = host.split(".")
        if (
            separator != ":"
            or port != "8080"
            or len(octets) != 4
            or any(
                not octet.isascii()
                or not octet.isdigit()
                or len(octet) > 3
                or str(int(octet)) != octet
                or not 0 <= int(octet) <= 255
                for octet in octets
            )
        ):
            raise ControllerError("presenter permit upstream is invalid")
        address = tuple(int(octet) for octet in octets)
        if not (
            address[0] == 10
            or (address[0] == 172 and 16 <= address[1] <= 31)
            or (address[0] == 192 and address[1] == 168)
        ):
            raise ControllerError("presenter permit upstream is not internal")
    elif (
        record["http_status"] != 403
        or record["target_marker_count"] != 0
        or record["upstream_host"] is not None
        or record["upstream_service_time_ms"] is not None
    ):
        raise ControllerError("presenter deny join is invalid")


def _validate_presenter_records(
    payloads: Mapping[str, bytes], manifest: Mapping[str, object]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    requests = _parse_jsonl_bytes(
        payloads["requests.jsonl"],
        "presenter requests",
        _request_closed,
        allow_empty=False,
    )
    decisions = _parse_jsonl_bytes(
        payloads["decisions.jsonl"],
        "presenter decisions",
        _normalized_presenter_decision_closed,
        allow_empty=False,
    )
    envoy = _parse_jsonl_bytes(
        payloads["envoy.jsonl"],
        "presenter Envoy records",
        _envoy_closed,
        allow_empty=False,
    )
    targets = _parse_jsonl_bytes(
        payloads["targets.jsonl"],
        "presenter target records",
        _target_closed,
        allow_empty=False,
    )
    joins = _parse_jsonl_bytes(
        payloads["joins.jsonl"],
        "presenter joins",
        _presenter_join_closed,
        allow_empty=False,
    )
    fixed_order = tuple(track.value for track in _TRACKS)
    target_order = fixed_order[:2]
    for label, records, order in (
        ("requests", requests, fixed_order),
        ("decisions", decisions, fixed_order),
        ("Envoy records", envoy, fixed_order),
        ("target records", targets, target_order),
        ("joins", joins, fixed_order),
    ):
        if tuple(item.get("track") for item in records) != order:
            raise ControllerError(f"presenter {label} track order is invalid")
    raw_decisions: list[dict[str, object]] = []
    for track in _TRACKS:
        relative = f"raw/decisions/{track.value}.jsonl"
        records = _parse_jsonl_bytes(
            payloads[relative],
            f"presenter raw decisions {track.value}",
            _decision_closed,
            allow_empty=False,
        )
        if len(records) != 1 or records[0].get("track") != track.value:
            raise ControllerError("presenter raw decision cardinality is invalid")
        raw_decisions.extend(records)
    normalized = _normalized_decision_records(manifest, raw_decisions)
    if decisions != normalized or payloads["decisions.jsonl"] != _jsonl_payload(
        normalized
    ):
        raise ControllerError("presenter decisions do not normalize raw sources")
    sources = manifest["source_attestations"]
    assert isinstance(sources, list)
    seen_container_ids: set[str] = set()
    immutable = manifest["immutable_images"]
    assert isinstance(immutable, dict)
    for track, attestation in zip(_TRACKS, sources, strict=True):
        track_envoy = [item for item in envoy if item["track"] == track.value]
        track_targets = [item for item in targets if item["track"] == track.value]
        raw_relative = f"raw/decisions/{track.value}.jsonl"
        observed = {
            "raw_decisions_sha256": _digest_bytes(payloads[raw_relative]),
            "raw_decision_count": 1,
            "raw_envoy_sha256": _digest_bytes(_jsonl_payload(track_envoy)),
            "raw_envoy_count": len(track_envoy),
            "raw_targets_sha256": _digest_bytes(_jsonl_payload(track_targets)),
            "raw_target_count": len(track_targets),
        }
        if any(attestation[name] != value for name, value in observed.items()):
            raise ControllerError(
                "presenter source attestation does not bind public source bytes"
            )
        if attestation["image_ids"] != {
            "authz": immutable["kil_image_id"],
            "target": immutable["kil_image_id"],
            "envoy": immutable["envoy_image_id"],
        }:
            raise ControllerError("presenter source image identity is invalid")
        container_ids = attestation["container_ids"]
        assert isinstance(container_ids, dict)
        if seen_container_ids.intersection(container_ids.values()):
            raise ControllerError("presenter source container identity is reused")
        seen_container_ids.update(container_ids.values())
    derived_joins = _join_evidence_records(
        manifest, requests, raw_decisions, envoy, targets
    )
    if joins != derived_joins or payloads["joins.jsonl"] != _jsonl_payload(
        derived_joins
    ):
        raise ControllerError("presenter joins do not derive from public sources")
    return decisions, joins


def _validate_failure_presenter_records(
    payloads: Mapping[str, bytes], manifest: Mapping[str, object]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Validate all preserved incomplete records without promoting a join."""
    requests = _parse_jsonl_bytes(
        payloads["requests.jsonl"],
        "failure presenter requests",
        _request_closed,
        allow_empty=True,
    )
    decisions = _parse_jsonl_bytes(
        payloads["decisions.jsonl"],
        "failure presenter decisions",
        _normalized_presenter_decision_closed,
        allow_empty=True,
    )
    envoy = _parse_jsonl_bytes(
        payloads["envoy.jsonl"],
        "failure presenter Envoy records",
        _envoy_closed,
        allow_empty=True,
    )
    targets = _parse_jsonl_bytes(
        payloads["targets.jsonl"],
        "failure presenter target records",
        _target_closed,
        allow_empty=True,
    )
    joins = _parse_jsonl_bytes(
        payloads["joins.jsonl"],
        "failure presenter joins",
        _presenter_join_closed,
        allow_empty=True,
    )
    if joins or payloads["joins.jsonl"] != b"":
        raise ControllerError("failure presenter joins must be empty")
    track_order = {track.value: index for index, track in enumerate(_TRACKS)}
    for label, records in (
        ("requests", requests),
        ("decisions", decisions),
        ("Envoy records", envoy),
        ("target records", targets),
    ):
        observed_tracks = [item.get("track") for item in records]
        if (
            any(track not in track_order for track in observed_tracks)
            or len(observed_tracks) != len(set(observed_tracks))
            or observed_tracks
            != sorted(observed_tracks, key=lambda track: track_order[track])
        ):
            raise ControllerError(f"failure presenter {label} order is invalid")
        for record in records:
            if record.get("request_id") != manifest["request_id"]:
                raise ControllerError(
                    f"failure presenter {label} request identity is invalid"
                )
            if "run_id" in record and record["run_id"] != manifest["run_id"]:
                raise ControllerError(
                    f"failure presenter {label} run identity is invalid"
                )
    raw_decisions: list[dict[str, object]] = []
    for track in _TRACKS:
        relative = f"raw/decisions/{track.value}.jsonl"
        records = _parse_jsonl_bytes(
            payloads[relative],
            f"failure presenter raw decisions {track.value}",
            _decision_closed,
            allow_empty=True,
        )
        if len(records) > 1 or any(
            item.get("track") != track.value
            or item.get("request_id") != manifest["request_id"]
            for item in records
        ):
            raise ControllerError(
                "failure presenter raw decision cardinality is invalid"
            )
        raw_decisions.extend(records)
    normalized = _normalized_decision_records(manifest, raw_decisions)
    if decisions != normalized or payloads["decisions.jsonl"] != _jsonl_payload(
        normalized
    ):
        raise ControllerError(
            "failure presenter decisions do not normalize preserved sources"
        )
    return decisions, joins


def _validate_presenter_snapshot(
    payloads: dict[str, bytes], *, completed: bool
) -> dict[str, object]:
    try:
        manifest = _load_json_bytes(
            payloads["manifest.json"], "public manifest"
        )
        _validate_public_manifest(manifest, payloads, completed=completed)
        if payloads["summary.md"] != _public_summary(manifest).encode("utf-8"):
            raise ControllerError("public summary does not match accepted evidence")
        decisions, joins = (
            _validate_presenter_records(payloads, manifest)
            if completed
            else _validate_failure_presenter_records(payloads, manifest)
        )
        expected = _render_live_html(
            _presenter_model(manifest, decisions, joins)
        )
        if payloads["live.html"] != expected:
            raise ControllerError("public presenter does not match accepted evidence")
        return manifest
    except ControllerError:
        raise
    except (
        AttributeError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise ControllerError("public evidence semantic validation failed") from error


def verify_presenter_bundle(
    output: Path,
    *,
    before_completion: Callable[[], None] | None = None,
    complete: Callable[[dict[str, bytes]], None] | None = None,
    after_completion: Callable[[], None] | None = None,
) -> Path:
    """Verify one accepted immutable bundle and return its offline presenter."""
    candidate = Path(os.path.abspath(output))
    if candidate.is_symlink():
        raise ControllerError("public evidence directory is missing or unsafe")
    try:
        bundle = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ControllerError(
            "public evidence directory is missing or unsafe"
        ) from error
    def validate_snapshot(payloads: dict[str, bytes]) -> Path:
        _validate_presenter_snapshot(payloads, completed=True)
        return bundle / "live.html"

    result = _public_bundle_snapshot(
        bundle,
        validator=validate_snapshot,
        before_completion=before_completion,
        complete=complete,
        after_completion=after_completion,
    )
    if not isinstance(result, Path):
        raise ControllerError("public evidence validation result is invalid")
    return result


def _verify_failure_presenter_bundle(
    output: Path,
    *,
    before_completion: Callable[[], None] | None = None,
    complete: Callable[[dict[str, bytes]], None] | None = None,
    after_completion: Callable[[], None] | None = None,
) -> Path:
    """Verify one immutable, explicitly nonpresentable failure bundle."""
    candidate = Path(os.path.abspath(output))
    if candidate.is_symlink():
        raise ControllerError("public failure evidence directory is unsafe")
    try:
        bundle = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ControllerError(
            "public failure evidence directory is missing or unsafe"
        ) from error

    def validate_snapshot(payloads: dict[str, bytes]) -> Path:
        _validate_presenter_snapshot(payloads, completed=False)
        return bundle / "live.html"

    result = _public_bundle_snapshot(
        bundle,
        validator=validate_snapshot,
        before_completion=before_completion,
        complete=complete,
        after_completion=after_completion,
    )
    if not isinstance(result, Path):
        raise ControllerError("public failure evidence validation result is invalid")
    return result


_AUTHORITATIVE_BUNDLE_SCHEMA = "kil.v3b1-authoritative-bundle.v1"
_FAILURE_BUNDLE_REPLACEMENT = "deterministic_empty_failure_v1"


def _authoritative_file_names() -> set[str]:
    return {
        *_EVIDENCE_FILES,
        "SHA256SUMS",
        *{f"raw/decisions/{track.value}.jsonl" for track in _TRACKS},
    }


def _public_commitment_sha256(
    manifest: Mapping[str, object], payloads: Mapping[str, bytes]
) -> str:
    """Recompute the non-circular commitment for one public snapshot."""
    file_names = _authoritative_file_names() - {
        "manifest.json",
        "SHA256SUMS",
    }
    if not file_names.issubset(payloads):
        raise ControllerError("public commitment file set is incomplete")
    projected_manifest = dict(manifest)
    projected_manifest.pop("public_commitment_sha256", None)
    public_schema = manifest.get("schema_version")
    if public_schema == "kil.v3b1-public-manifest.v1":
        commitment_schema = _PUBLIC_COMMITMENT_SCHEMA
    elif public_schema == "kil.v3b1-public-manifest.v2":
        commitment_schema = _PUBLIC_COMMITMENT_SCHEMA_V2
    else:
        raise ControllerError("public commitment manifest schema is invalid")
    commitment = {
        "schema_version": commitment_schema,
        "manifest": projected_manifest,
        "file_sha256": {
            relative: _digest_bytes(payloads[relative])
            for relative in sorted(file_names)
        },
    }
    return _digest_bytes(canonical_json(commitment).encode("utf-8"))


def _public_commitment_from_output(
    output: Path, manifest: Mapping[str, object]
) -> str:
    payloads = {
        relative: (output / relative).read_bytes()
        for relative in _authoritative_file_names()
        if relative not in {"manifest.json", "SHA256SUMS"}
    }
    return _public_commitment_sha256(manifest, payloads)


def _validate_authoritative_attestation(
    value: Mapping[str, object],
) -> dict[str, object]:
    if type(value) is not dict or set(value) != {
        "schema_version", "file_sha256", "binding_sha256",
    }:
        raise ControllerError("authoritative bundle attestation fields are not closed")
    if value["schema_version"] != _AUTHORITATIVE_BUNDLE_SCHEMA:
        raise ControllerError("authoritative bundle attestation schema is invalid")
    hashes = value["file_sha256"]
    if type(hashes) is not dict or set(hashes) != _authoritative_file_names():
        raise ControllerError("authoritative bundle attestation file set is not closed")
    for relative, digest in hashes.items():
        if type(relative) is not str:
            raise ControllerError("authoritative bundle attestation path is invalid")
        _require_sha256("authoritative artifact sha256", digest)
    _require_sha256("authoritative binding_sha256", value["binding_sha256"])
    bound = {
        "schema_version": _AUTHORITATIVE_BUNDLE_SCHEMA,
        "file_sha256": dict(hashes),
    }
    expected_binding = _digest_bytes(canonical_json(bound).encode("utf-8"))
    if value["binding_sha256"] != expected_binding:
        raise ControllerError("authoritative bundle attestation binding is invalid")
    return {**bound, "binding_sha256": expected_binding}


def authoritative_bundle_attestation(output: Path) -> dict[str, object]:
    """Bind every byte in one closed, checksummed provisional bundle."""
    verify_public_checksums(output)
    hashes = {
        relative: _digest_file(output / relative)
        for relative in sorted(_authoritative_file_names())
    }
    bound: dict[str, object] = {
        "schema_version": _AUTHORITATIVE_BUNDLE_SCHEMA,
        "file_sha256": hashes,
    }
    bound["binding_sha256"] = _digest_bytes(
        canonical_json(bound).encode("utf-8")
    )
    return _validate_authoritative_attestation(bound)


def _reattest_authoritative_bundle(
    output: Path, expected: Mapping[str, object]
) -> dict[str, object]:
    recorded = _validate_authoritative_attestation(expected)
    try:
        observed = authoritative_bundle_attestation(output)
    except ControllerError as error:
        raise ControllerError(
            "authoritative provisional bundle changed after durable binding"
        ) from error
    if observed != recorded:
        raise ControllerError(
            "authoritative provisional bundle changed after durable binding"
        )
    return observed


def _journal_authoritative_attestation(
    events: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    for event in reversed(events):
        details = event.get("details")
        if type(details) is dict and "authoritative_attestation" in details:
            attestation = details["authoritative_attestation"]
            if type(attestation) is not dict:
                raise ControllerError(
                    "durable authoritative bundle attestation is malformed"
                )
            return _validate_authoritative_attestation(attestation)
    raise ControllerError("durable authoritative bundle attestation is missing")


def _publication_recovery_contract(
    events: Sequence[Mapping[str, object]],
    private_manifest: Mapping[str, object],
) -> tuple[bool, list[dict[str, object]], dict[str, object]]:
    """Reconstruct publication class, provenance, and byte authority durably."""
    run_id = private_manifest["run_id"]
    failure_transition = _post_teardown_failure_transition(events, str(run_id))
    if failure_transition is not None:
        _, prepared = failure_transition
        if prepared is None:
            raise ControllerError(
                "published failure bundle lacks durable prepared authority"
            )
        completed = False
        source_attestations: list[dict[str, object]] = []
        details = prepared["details"]
        assert isinstance(details, Mapping)
        authority_value = details["authoritative_attestation"]
        if type(authority_value) is not dict:
            raise ControllerError("published failure authority is malformed")
        authority = _validate_authoritative_attestation(authority_value)
    else:
        completions = [
            event
            for event in events
            if event.get("event") == "evidence_collect_complete"
        ]
        if not completions:
            raise ControllerError("publication lacks durable evidence completion")
        completion_details = completions[-1].get("details")
        if (
            type(completion_details) is not dict
            or set(completion_details)
            != {"completed", "bundle_sha256", "authoritative_attestation"}
            or type(completion_details.get("completed")) is not bool
            or type(completion_details.get("authoritative_attestation")) is not dict
        ):
            raise ControllerError("durable evidence completion is malformed")
        completed = completion_details["completed"]
        authority = _validate_authoritative_attestation(
            completion_details["authoritative_attestation"]
        )
        _require_sha256(
            "durable evidence bundle sha256",
            completion_details["bundle_sha256"],
        )
        authority_hashes = authority["file_sha256"]
        assert isinstance(authority_hashes, dict)
        if (
            completion_details["bundle_sha256"]
            != authority_hashes["SHA256SUMS"]
        ):
            raise ControllerError(
                "durable evidence completion does not bind its authority"
            )
        source_events = [
            event
            for event in events
            if event.get("event") == "source_attestations_persisted"
        ]
        if not source_events:
            raise ControllerError("publication lacks durable source provenance")
        source_details = source_events[-1].get("details")
        if (
            type(source_details) is not dict
            or set(source_details) != {"source_attestations"}
            or type(source_details["source_attestations"]) is not list
        ):
            raise ControllerError("durable source provenance is malformed")
        source_attestations = []
        for item in source_details["source_attestations"]:
            if type(item) is not dict:
                raise ControllerError("durable source provenance is malformed")
            source_attestations.append(dict(item))
        _validate_source_attestations(
            source_attestations, completed=completed
        )
        if not completed and source_attestations:
            raise ControllerError(
                "incomplete publication source provenance must be empty"
            )
    intents = [
        event for event in events if event.get("event") == "publication_intent"
    ]
    if not intents:
        raise ControllerError("published evidence lacks its durable publication intent")
    intent = intents[-1].get("details")
    if (
        type(intent) is not dict
        or set(intent) != {"run_id", "completed"}
        or intent["run_id"] != run_id
        or type(intent["completed"]) is not bool
        or intent["completed"] is not completed
    ):
        raise ControllerError("durable publication intent identity/class is invalid")
    return completed, source_attestations, authority


def _verify_recovered_publication(
    output: Path,
    private_manifest: Mapping[str, object],
    *,
    completed: bool,
    source_attestations: Sequence[Mapping[str, object]],
    authoritative_attestation: Mapping[str, object],
    tool_identities: Mapping[str, object],
    engine_provenance: Mapping[str, object],
    global_context: str,
    before_completion: Callable[[], None] | None = None,
    publication_complete: Callable[[str], None] | None = None,
    publication_cleanup: Callable[[], None] | None = None,
) -> None:
    """Hold one public snapshot while reattesting semantics and private authority."""
    authority = _validate_authoritative_attestation(authoritative_attestation)
    authority_hashes = authority["file_sha256"]
    assert isinstance(authority_hashes, dict)
    invariant_names = _authoritative_file_names() - {
        "manifest.json",
        "summary.md",
        "SHA256SUMS",
    }

    def validate_snapshot(payloads: dict[str, bytes]) -> None:
        public_manifest = _validate_presenter_snapshot(
            payloads, completed=completed
        )
        expected_private_projection = {
            "run_id": private_manifest["run_id"],
            "request_id": private_manifest["request_id"],
            "source_commit": private_manifest["source_commit"],
            "content_identity_sha256": private_manifest[
                "content_identity_sha256"
            ],
            "content_identity": private_manifest["content_identity"],
            "immutable_images": {
                "python": private_manifest["python_image_digest"],
                "envoy_digest": private_manifest["envoy_image_digest"],
                "envoy_image_id": private_manifest["envoy_image_id"],
                "kil_image_id": private_manifest["kil_image_id"],
                "kil_archive_sha256": private_manifest["kil_archive_sha256"],
            },
        }
        for name, expected in expected_private_projection.items():
            if public_manifest.get(name) != expected:
                raise ControllerError(
                    "public publication identity diverges from private authority"
                )
        if public_manifest.get("source_attestations") != [
            dict(item) for item in source_attestations
        ]:
            raise ControllerError(
                "public publication source provenance diverges from journal"
            )
        if (
            public_manifest.get("verified_tool_identities")
            != dict(tool_identities)
            or public_manifest.get("docker_engine_provenance")
            != dict(engine_provenance)
            or public_manifest.get("global_context_attestation")
            != {
                "before": global_context,
                "after": global_context,
                "unchanged": True,
            }
        ):
            raise ControllerError(
                "public publication provenance diverges from lifecycle journal"
            )
        if authority_hashes["manifest.json"] != _digest_bytes(
            _canonical_bytes(private_manifest)
        ):
            raise ControllerError(
                "durable publication authority does not bind the private manifest"
            )
        for relative in sorted(invariant_names):
            if authority_hashes[relative] != _digest_bytes(payloads[relative]):
                raise ControllerError(
                    "public publication artifact diverges from durable authority"
                )

    def complete_snapshot(payloads: dict[str, bytes]) -> None:
        if publication_complete is not None:
            publication_complete(_digest_bytes(payloads["manifest.json"]))

    _public_bundle_snapshot(
        output,
        validator=validate_snapshot,
        before_completion=before_completion,
        complete=complete_snapshot,
        after_completion=publication_cleanup,
    )


def _post_teardown_failure_transition(
    events: Sequence[Mapping[str, object]], run_id: str
) -> tuple[Mapping[str, object], Mapping[str, object] | None] | None:
    intent_fields = {"run_id", "evidence_rejection", "replacement"}
    completion_fields = {
        *intent_fields,
        "intent_sequence",
        "authoritative_attestation",
    }
    latest_intent: Mapping[str, object] | None = None
    for event in events:
        if event.get("event") != "post_teardown_failure_bundle_intent":
            continue
        details = event.get("details")
        if (
            type(details) is not dict
            or set(details) != intent_fields
            or details["run_id"] != run_id
            or type(details["evidence_rejection"]) is not str
            or not details["evidence_rejection"]
            or details["replacement"] != _FAILURE_BUNDLE_REPLACEMENT
            or type(event.get("sequence")) is not int
        ):
            raise ControllerError("failure bundle replacement intent is invalid")
        latest_intent = event
    if latest_intent is None:
        return None
    intent_sequence = latest_intent["sequence"]
    matches: list[Mapping[str, object]] = []
    for event in events:
        if event.get("event") != "post_teardown_failure_bundle_prepared":
            continue
        details = event.get("details")
        if type(details) is not dict or details.get("intent_sequence") != intent_sequence:
            continue
        if (
            set(details) != completion_fields
            or details["run_id"] != run_id
            or details["evidence_rejection"]
            != latest_intent["details"]["evidence_rejection"]  # type: ignore[index]
            or details["replacement"] != _FAILURE_BUNDLE_REPLACEMENT
            or type(details["authoritative_attestation"]) is not dict
        ):
            raise ControllerError("failure bundle replacement completion is invalid")
        _validate_authoritative_attestation(
            details["authoritative_attestation"]  # type: ignore[arg-type]
        )
        matches.append(event)
    if len(matches) > 1:
        raise ControllerError("failure bundle replacement completion is duplicated")
    return latest_intent, matches[0] if matches else None


def _public_summary(public_manifest: Mapping[str, object]) -> str:
    completion = "verified teardown completed" if public_manifest["run_complete"] else "failed/incomplete lifecycle"
    return (
        "# KIL V3B-1 provisional local Envoy boundary bundle\n\n"
        f"- Run ID: `{public_manifest['run_id']}`\n"
        f"- Evidence scope: `{EVIDENCE_SCOPE}`\n"
        f"- Bundle class: `{public_manifest['bundle_class']}`\n"
        f"- Promotion: `not_promoted`\n"
        f"- Lifecycle: {completion}\n"
        "- Teardown: complete before publication\n\n"
        "This is a provisional, non-promoted observation of the pinned local Envoy "
        "authorization boundary. Inputs are modeled and outputs are observed. It does "
        "not establish cluster orchestration, past-event guarantees, workload "
        "benchmarking, or cross-track network-policy enforcement.\n\n"
        f"{_KTP_CITATION}"
    )


def _reject_public_secrets(value: object) -> None:
    try:
        reject_sensitive_material(value)
    except HarnessContractError as error:
        raise ControllerError(
            "public manifest contains private or sensitive material"
        ) from error
    except (AttributeError, TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ControllerError("public manifest safety scan failed") from error


def _validate_global_context(label: str, value: object) -> str:
    if type(value) is not str or not value.strip():
        raise ControllerError(f"{label} must be a nonempty string")
    if "\r" in value or "\n" in value:
        raise ControllerError(f"{label} must be one closed line")
    try:
        if len(value.encode("utf-8")) > 4096:
            raise ControllerError(f"{label} is too large")
    except UnicodeError as error:
        raise ControllerError(f"{label} contains invalid Unicode") from error
    _reject_public_secrets(value)
    return value


def _validate_provisional_tree(output: Path, *, completed: bool) -> None:
    expected = _authoritative_file_names()
    actual = set()
    for path in output.rglob("*"):
        if path.is_symlink():
            raise ControllerError("provisional bundle contains a symbolic link")
        if path.is_file():
            actual.add(path.relative_to(output).as_posix())
        elif not path.is_dir():
            raise ControllerError("provisional bundle contains an unsafe object")
    if actual != expected:
        raise ControllerError("provisional bundle public artifact set is not closed")
    for track in _TRACKS:
        records = _parse_jsonl_bytes(
            (output / "raw/decisions" / f"{track.value}.jsonl").read_bytes(),
            f"raw decisions {track.value}",
            _decision_closed,
            allow_empty=not completed,
        )
        if (completed and len(records) != 1) or len(records) > 1:
            raise ControllerError("provisional raw decision cardinality is invalid")
        if any(record["track"] != track.value for record in records):
            raise ControllerError("provisional raw decision track is invalid")
    if not completed and (output / "joins.jsonl").read_bytes() != b"":
        raise ControllerError("incomplete provisional joins must be empty")


def _validate_source_attestations(
    source_attestations: Sequence[Mapping[str, object]], *, completed: bool
) -> None:
    if type(source_attestations) not in (list, tuple):
        raise ControllerError("source attestations must be a closed sequence")
    if len(source_attestations) == 0 and not completed:
        return
    fields = {
        "track", "container_ids", "image_ids", "config_sha256",
        "raw_decisions_sha256", "raw_decision_count", "raw_envoy_sha256",
        "raw_envoy_count", "raw_targets_sha256", "raw_target_count",
    }
    roles = {"authz", "target", "envoy"}
    if len(source_attestations) != len(_TRACKS) or any(
        type(item) is not dict for item in source_attestations
    ):
        raise ControllerError("source attestations are not three closed objects")
    container_ids_seen: set[str] = set()
    for index, item in enumerate(source_attestations):
        assert isinstance(item, dict)
        if type(item) is not dict or set(item) != fields:
            raise ControllerError("source attestation fields are not closed")
        for name in ("container_ids", "image_ids", "config_sha256"):
            mapping = item[name]
            if type(mapping) is not dict or set(mapping) != roles:
                raise ControllerError(f"source attestation {name} is not closed")
        if any(
            type(value) is not str or _HEX.fullmatch(value) is None
            for value in item["container_ids"].values()  # type: ignore[union-attr]
        ):
            raise ControllerError("source attestation container IDs are invalid")
        track_container_ids = set(item["container_ids"].values())  # type: ignore[union-attr]
        if (
            len(track_container_ids) != len(roles)
            or container_ids_seen.intersection(track_container_ids)
        ):
            raise ControllerError(
                "source attestation container IDs are not distinct"
            )
        container_ids_seen.update(track_container_ids)
        if any(
            type(value) is not str or _IMAGE_ID.fullmatch(value) is None
            for value in item["image_ids"].values()  # type: ignore[union-attr]
        ):
            raise ControllerError("source attestation image IDs are invalid")
        for value in item["config_sha256"].values():  # type: ignore[union-attr]
            _require_sha256("source config_sha256", value)
        for name in (
            "raw_decisions_sha256", "raw_envoy_sha256", "raw_targets_sha256",
        ):
            _require_sha256(f"source {name}", item[name])
        expected_target_count = 0 if index == 2 else 1
        if (
            type(item["raw_decision_count"]) is not int
            or type(item["raw_envoy_count"]) is not int
            or type(item["raw_target_count"]) is not int
            or item["raw_decision_count"] not in ({1} if completed else {0, 1})
            or item["raw_envoy_count"] not in ({1} if completed else {0, 1})
            or (
                completed
                and item["raw_target_count"] != expected_target_count
            )
            or (not completed and item["raw_target_count"] not in {0, 1})
        ):
            raise ControllerError("source attestation counts are invalid")
    if [item["track"] for item in source_attestations] != [
        track.value for track in _TRACKS
    ] or len(container_ids_seen) != 9:
        raise ControllerError("source attestations are not in fixed track order")


def _validate_source_attestation_bindings(
    output: Path,
    source_attestations: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
) -> None:
    if not source_attestations:
        return
    envoy = _parse_jsonl_bytes(
        (output / "envoy.jsonl").read_bytes(),
        "published Envoy source",
        _envoy_closed,
        allow_empty=True,
    )
    targets = _parse_jsonl_bytes(
        (output / "targets.jsonl").read_bytes(),
        "published target source",
        _target_closed,
        allow_empty=True,
    )
    seen_container_ids: set[str] = set()
    for track, attestation in zip(_TRACKS, source_attestations, strict=True):
        raw_decisions = (
            output / "raw/decisions" / f"{track.value}.jsonl"
        ).read_bytes()
        decision_records = _parse_jsonl_bytes(
            raw_decisions,
            f"published raw decisions {track.value}",
            _decision_closed,
            allow_empty=True,
        )
        track_envoy = [item for item in envoy if item["track"] == track.value]
        track_targets = [item for item in targets if item["track"] == track.value]
        bindings = {
            "raw_decisions_sha256": _digest_bytes(raw_decisions),
            "raw_decision_count": len(decision_records),
            "raw_envoy_sha256": _digest_bytes(_jsonl_payload(track_envoy)),
            "raw_envoy_count": len(track_envoy),
            "raw_targets_sha256": _digest_bytes(_jsonl_payload(track_targets)),
            "raw_target_count": len(track_targets),
        }
        if any(attestation[name] != value for name, value in bindings.items()):
            raise ControllerError("source attestation does not bind published source bytes")
        image_ids = attestation["image_ids"]
        assert isinstance(image_ids, dict)
        if image_ids != {
            "authz": manifest["kil_image_id"],
            "target": manifest["kil_image_id"],
            "envoy": manifest["envoy_image_id"],
        }:
            raise ControllerError("source attestation image IDs diverge from manifest")
        container_ids = attestation["container_ids"]
        assert isinstance(container_ids, dict)
        if seen_container_ids.intersection(container_ids.values()):
            raise ControllerError("source attestation reuses a container ID")
        seen_container_ids.update(container_ids.values())


def _artifact_hash_map(output: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    excluded = {"manifest.json", "summary.md", "SHA256SUMS"}
    for path in sorted(
        output.rglob("*"), key=lambda item: item.relative_to(output).as_posix()
    ):
        relative = path.relative_to(output).as_posix()
        if relative in excluded:
            continue
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise ControllerError("provisional evidence contains an unsafe artifact")
        if path.is_file():
            hashes[relative] = _digest_file(path)
    return hashes


def _directory_object_identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _open_verified_directory(path: Path, label: str) -> tuple[int, tuple[int, int]]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
        raise ControllerError(f"{label} is missing or unsafe") from error
    identity = _directory_object_identity(opened)
    if not stat.S_ISDIR(opened.st_mode) or identity != _directory_object_identity(
        current
    ):
        os.close(descriptor)
        raise ControllerError(f"{label} identity is unstable")
    return descriptor, identity


def _require_directory_identity(
    descriptor: int,
    path: Path,
    identity: tuple[int, int],
    label: str,
) -> None:
    try:
        opened = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise ControllerError(f"{label} changed during publication") from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or identity != _directory_object_identity(opened)
        or identity != _directory_object_identity(current)
    ):
        raise ControllerError(f"{label} changed during publication")


def _quarantine_publication_leaf(
    public_parent_fd: int,
    destination_name: str,
    private_parent_fd: int,
    run_id: str,
) -> None:
    try:
        current = os.stat(
            destination_name,
            dir_fd=public_parent_fd,
            follow_symlinks=False,
        )
    except OSError as error:
        raise ControllerError(
            "failed publication destination cannot be quarantined"
        ) from error
    identity = _directory_object_identity(current)
    for counter in range(10_000):
        quarantine_name = (
            f".failed-publication-{run_id}-{identity[0]:x}-{identity[1]:x}-"
            f"{counter}"
        )
        try:
            os.stat(
                quarantine_name,
                dir_fd=private_parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            os.rename(
                destination_name,
                quarantine_name,
                src_dir_fd=public_parent_fd,
                dst_dir_fd=private_parent_fd,
            )
            os.fsync(public_parent_fd)
            os.fsync(private_parent_fd)
            return
        except OSError as error:
            raise ControllerError(
                "failed publication quarantine inventory is unsafe"
            ) from error
    raise ControllerError("failed publication quarantine names are exhausted")


def finalize_publication(
    provisional: Path,
    public_parent: Path,
    private_manifest: dict[str, object],
    *,
    source_attestations: Sequence[Mapping[str, object]],
    tool_identities: Mapping[str, object],
    engine_provenance: Mapping[str, object],
    global_context_before: str,
    global_context_after: str,
    completed: bool,
    authoritative_attestation: Mapping[str, object],
    publication_fault: Callable[[str, Path], None] | None = None,
    publication_complete: Callable[[str], None] | None = None,
    publication_cleanup: Callable[[], None] | None = None,
    repository_root: Path | None = None,
    publication_staging_root: Path | None = None,
) -> Path:
    """Finalize privately, then atomically rename one immutable public bundle."""
    _validate_manifest(private_manifest)
    safety_root = (
        repository_root.resolve()
        if repository_root is not None
        else Path(
            os.path.commonpath(
                [str(provisional.absolute()), str(public_parent.absolute())]
            )
        ).resolve()
    )
    _require_contained(provisional, safety_root, "authoritative provisional")
    _require_contained(public_parent, safety_root, "public evidence root")
    if provisional.is_symlink() or not provisional.is_dir():
        raise ControllerError("provisional evidence directory is missing or unsafe")
    if public_parent.is_symlink():
        raise ControllerError("public evidence root cannot be a symbolic link")
    destination = public_parent / str(private_manifest["run_id"])
    _require_contained(destination, public_parent, "public evidence destination")
    if provisional.resolve() == destination.resolve(strict=False) or destination.exists():
        raise ControllerError("public evidence clobber is forbidden")
    manifest_path = provisional / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ControllerError("provisional manifest is missing or unsafe")
    recorded_private = _load_json_bytes(manifest_path.read_bytes(), "provisional manifest")
    _validate_manifest(recorded_private)
    if recorded_private != private_manifest:
        raise ControllerError("provisional manifest diverges from private lifecycle state")
    global_context_before = _validate_global_context(
        "global Docker context before", global_context_before
    )
    global_context_after = _validate_global_context(
        "global Docker context after", global_context_after
    )
    if global_context_before != global_context_after:
        raise ControllerError("global Docker context changed during controller lifecycle")
    if type(source_attestations) not in (list, tuple):
        raise ControllerError("source attestations must be a sequence")
    _validate_public_provenance(tool_identities, engine_provenance)
    _validate_source_attestations(source_attestations, completed=completed)
    _validate_provisional_tree(provisional, completed=completed)
    authoritative = _reattest_authoritative_bundle(
        provisional, authoritative_attestation
    )
    _validate_source_attestation_bindings(
        provisional, source_attestations, private_manifest
    )
    artifact_hashes = _artifact_hash_map(provisional)
    bundle_class = (
        "intermediate_provisional_local_boundary"
        if completed
        else "intermediate_provisional_failure_local_boundary"
    )
    identity = private_manifest["content_identity"]
    assert isinstance(identity, dict)
    public_manifest: dict[str, object] = {
        "schema_version": "kil.v3b1-public-manifest.v2",
        "run_id": private_manifest["run_id"],
        "request_id": private_manifest["request_id"],
        "evidence_scope": EVIDENCE_SCOPE,
        "bundle_class": bundle_class,
        "promotion_status": "not_promoted",
        "run_complete": completed,
        "platform": PLATFORM,
        "source_commit": private_manifest["source_commit"],
        "content_identity_sha256": private_manifest["content_identity_sha256"],
        "content_identity": dict(identity),
        "immutable_images": {
            "python": private_manifest["python_image_digest"],
            "envoy_digest": private_manifest["envoy_image_digest"],
            "envoy_image_id": private_manifest["envoy_image_id"],
            "kil_image_id": private_manifest["kil_image_id"],
            "kil_archive_sha256": private_manifest["kil_archive_sha256"],
        },
        "build_inputs": {
            "dockerfile_sha256": identity["dockerfile_sha256"],
            "dockerignore_sha256": identity["dockerignore_sha256"],
            "build_context_sha256": identity["build_context_sha256"],
            "context_strategy": "controller_exact_allowlist_for_legacy_builder",
        },
        "verified_tool_identities": dict(tool_identities),
        "docker_engine_provenance": dict(engine_provenance),
        "global_context_attestation": {
            "before": global_context_before,
            "after": global_context_after,
            "unchanged": True,
        },
        "evidence_policy": {"inputs": "modeled", "outputs": "observed"},
        "source_attestations": [dict(item) for item in source_attestations],
        "artifact_hash_rule": "sha256_excludes_manifest_summary_and_SHA256SUMS",
        "artifact_sha256": artifact_hashes,
        "public_commitment_rule": _PUBLIC_COMMITMENT_RULE,
        "teardown": {
            "status": "complete",
            "verified_before_publication": True,
        },
        "claim_exclusions": [
            "kind_cluster_validated",
            "historical_prevention",
            "production_performance",
            "network_policy_validation",
        ],
    }
    _reject_public_secrets(public_manifest)
    publication_root = (
        publication_staging_root
        if publication_staging_root is not None
        else provisional.parent / ".publication-staging"
    )
    _require_contained(publication_root, safety_root, "private publication staging")
    if publication_root.is_symlink():
        raise ControllerError("private publication staging cannot be a symbolic link")
    publication_root.mkdir(parents=True, exist_ok=True)
    _require_contained(publication_root, safety_root, "private publication staging")
    if publication_root.is_symlink() or not publication_root.is_dir():
        raise ControllerError("private publication staging is missing or unsafe")
    staging = publication_root / (
        f"{private_manifest['run_id']}-{secrets.token_hex(16)}"
    )
    _require_contained(staging, safety_root, "private publication staging run")
    shutil.copytree(provisional, staging, symlinks=True)
    _validate_provisional_tree(staging, completed=completed)
    _reattest_authoritative_bundle(staging, authoritative)
    if publication_fault is not None:
        publication_fault("after_copy", staging)
    staging_manifest = staging / "manifest.json"
    public_summary = _public_summary(public_manifest).encode("utf-8")
    commitment_payloads = {
        relative: (staging / relative).read_bytes()
        for relative in _authoritative_file_names()
        if relative not in {"manifest.json", "SHA256SUMS"}
    }
    commitment_payloads["summary.md"] = public_summary
    public_manifest["public_commitment_sha256"] = _public_commitment_sha256(
        public_manifest, commitment_payloads
    )
    _write_file(staging_manifest, _canonical_bytes(public_manifest), 0o444)
    _write_file(
        staging / "summary.md",
        public_summary,
        0o444,
    )
    if publication_fault is not None:
        publication_fault("after_public_manifest", staging)
    if publication_fault is not None:
        publication_fault("before_atomic_rename", staging)
    staged_manifest = _load_json_bytes(
        (staging / "manifest.json").read_bytes(), "staged public manifest"
    )
    if staged_manifest != public_manifest:
        raise ControllerError("staged public manifest changed before publication")
    _validate_provisional_tree(staging, completed=completed)
    staged_artifact_hashes = _artifact_hash_map(staging)
    if staged_artifact_hashes != public_manifest["artifact_sha256"]:
        raise ControllerError("staged artifact hash map changed before publication")
    _validate_source_attestation_bindings(
        staging, source_attestations, private_manifest
    )
    expected_summary = _public_summary(staged_manifest).encode("utf-8")
    if (staging / "summary.md").read_bytes() != expected_summary:
        raise ControllerError("staged public summary changed before publication")
    staged_decisions = _parse_jsonl_bytes(
        (staging / "decisions.jsonl").read_bytes(),
        "staged presenter decisions",
        lambda record: None,
        allow_empty=not completed,
    )
    staged_joins = _parse_jsonl_bytes(
        (staging / "joins.jsonl").read_bytes(),
        "staged presenter joins",
        lambda record: None,
        allow_empty=not completed,
    )
    expected_presenter = _render_live_html(
        _presenter_model(staged_manifest, staged_decisions, staged_joins)
    )
    if (staging / "live.html").read_bytes() != expected_presenter:
        raise ControllerError("staged public presenter changed before publication")
    _write_sums(staging)
    verify_public_checksums(staging)
    _require_contained(publication_root, safety_root, "private publication staging")
    _require_contained(staging, publication_root, "private publication staging run")
    if publication_root.is_symlink() or staging.is_symlink():
        raise ControllerError("private publication staging changed before rename")
    public_parent.mkdir(parents=True, exist_ok=True)
    _require_contained(public_parent, safety_root, "public evidence root")
    _require_contained(destination, public_parent, "public evidence destination")
    publication_fd = public_fd = staging_fd = -1
    renamed = False
    try:
        publication_fd, publication_identity = _open_verified_directory(
            publication_root, "private publication staging"
        )
        public_fd, public_identity = _open_verified_directory(
            public_parent, "public evidence root"
        )
        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            staging_fd = os.open(
                staging.name,
                directory_flags,
                dir_fd=publication_fd,
            )
        except OSError as error:
            raise ControllerError(
                "private publication staging run changed before rename"
            ) from error
        staging_identity = _directory_object_identity(os.fstat(staging_fd))
        _require_directory_identity(
            publication_fd,
            publication_root,
            publication_identity,
            "private publication staging",
        )
        _require_directory_identity(
            public_fd,
            public_parent,
            public_identity,
            "public evidence root",
        )
        try:
            os.stat(
                destination.name,
                dir_fd=public_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError as error:
            raise ControllerError(
                "public evidence destination inventory is unsafe"
            ) from error
        else:
            raise ControllerError("public evidence clobber is forbidden")
        os.rename(
            staging.name,
            destination.name,
            src_dir_fd=publication_fd,
            dst_dir_fd=public_fd,
        )
        renamed = True
        os.fsync(publication_fd)
        os.fsync(public_fd)
        if publication_fault is not None:
            publication_fault("after_atomic_rename", destination)
        _require_directory_identity(
            publication_fd,
            publication_root,
            publication_identity,
            "private publication staging",
        )
        _require_directory_identity(
            public_fd,
            public_parent,
            public_identity,
            "public evidence root",
        )
        destination_identity = _directory_object_identity(
            os.stat(
                destination.name,
                dir_fd=public_fd,
                follow_symlinks=False,
            )
        )
        if destination_identity != staging_identity:
            raise ControllerError(
                "public evidence destination identity changed after rename"
            )
        def before_completion() -> None:
            if publication_fault is not None:
                publication_fault("after_postrename_validation", destination)

        def complete_snapshot(payloads: dict[str, bytes]) -> None:
            if publication_complete is not None:
                publication_complete(_digest_bytes(payloads["manifest.json"]))

        verifier = (
            verify_presenter_bundle
            if completed
            else _verify_failure_presenter_bundle
        )
        verifier(
            destination,
            before_completion=before_completion,
            complete=complete_snapshot,
            after_completion=publication_cleanup,
        )
        _require_directory_identity(
            publication_fd,
            publication_root,
            publication_identity,
            "private publication staging",
        )
        _require_directory_identity(
            public_fd,
            public_parent,
            public_identity,
            "public evidence root",
        )
        if staging_identity != _directory_object_identity(os.fstat(staging_fd)):
            raise ControllerError(
                "public evidence tree identity changed after validation"
            )
        return destination
    except (ControllerError, OSError) as error:
        if renamed:
            try:
                _quarantine_publication_leaf(
                    public_fd,
                    destination.name,
                    publication_fd,
                    str(private_manifest["run_id"]),
                )
            except ControllerError as quarantine_error:
                raise ControllerError(
                    "invalid public evidence could not be quarantined"
                ) from quarantine_error
        if isinstance(error, ControllerError):
            raise
        raise ControllerError("public evidence rename transaction failed") from error
    finally:
        for descriptor in (staging_fd, public_fd, publication_fd):
            if descriptor >= 0:
                os.close(descriptor)


def write_evidence_bundle(
    evidence_root: Path,
    manifest: dict[str, object],
    *,
    requests: Sequence[Mapping[str, object]],
    decisions: Sequence[Mapping[str, object]],
    envoy: Sequence[Mapping[str, object]],
    targets: Sequence[Mapping[str, object]],
    joins: Sequence[Mapping[str, object]],
    raw_decisions: Mapping[LiveTrack, bytes] | None = None,
    resume_attested: bool = False,
) -> Path:
    """Rebuild the exact public bundle from verified source records."""
    _validate_manifest(manifest)
    output = evidence_root / str(manifest["run_id"])
    if output.exists() and any(output.iterdir()) and not resume_attested:
        raise ControllerError("evidence run already exists; attested resume required")
    output.mkdir(parents=True, exist_ok=True)
    allowed = set(_EVIDENCE_FILES) | {"SHA256SUMS", "raw"}
    unexpected = {item.name for item in output.iterdir()} - allowed
    if unexpected:
        raise ControllerError(f"evidence directory contains unexpected files: {sorted(unexpected)}")
    raw_root = output / "raw/decisions"
    raw_root.mkdir(parents=True, exist_ok=True)
    if raw_decisions is None:
        raw_decisions = {
            track: _jsonl_payload(
                [record for record in decisions if record.get("track") == track.value]
            )
            for track in _TRACKS
        }
    if set(raw_decisions) != set(_TRACKS):
        raise ControllerError("raw decision sources must cover the three fixed tracks")
    for track in _TRACKS:
        payload = raw_decisions[track]
        parsed = _parse_jsonl_bytes(
            payload,
            f"raw decisions for {track.value}",
            _decision_closed,
            allow_empty=False,
        )
        if any(record["track"] != track.value for record in parsed):
            raise ControllerError("raw decision source track does not match fixed file")
        _write_file(raw_root / f"{track.value}.jsonl", payload, 0o444)
    normalized_decisions = _normalized_decision_records(manifest, decisions)
    _write_file(output / "requests.jsonl", _jsonl_payload(requests), 0o444)
    _write_file(
        output / "decisions.jsonl", _jsonl_payload(normalized_decisions), 0o444
    )
    _write_file(output / "envoy.jsonl", _jsonl_payload(envoy), 0o444)
    _write_file(output / "targets.jsonl", _jsonl_payload(targets), 0o444)
    _write_file(output / "joins.jsonl", _jsonl_payload(joins), 0o444)
    _write_file(output / "manifest.json", _canonical_bytes(manifest), 0o444)
    _write_file(output / "summary.md", _summary(manifest, joins).encode("utf-8"), 0o444)
    _write_file(
        output / "live.html",
        _render_live_html(_presenter_model(manifest, normalized_decisions, joins)),
        0o444,
    )
    _write_sums(output)
    _verify_sums(output)
    return output


def _normalized_decision_records(
    manifest: Mapping[str, object], decisions: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    return [
        {
            "schema_version": "kil.v3b1-collected-decision.v1",
            "source_schema_version": record["schema_version"],
            "source_record_sha256": _digest_bytes(
                canonical_json(record).encode("utf-8")
            ),
            "run_id": manifest["run_id"],
            "run_id_provenance": "manifest_attested_enrichment",
            **{
                key: value
                for key, value in record.items()
                if key != "schema_version"
            },
        }
        for record in decisions
    ]


def _prepare_failure_provisional(
    provisional_root: Path,
    manifest: dict[str, object],
    *,
    requests: Sequence[Mapping[str, object]] | None = None,
    raw_decisions: Mapping[LiveTrack, bytes] | None = None,
    envoy: Sequence[Mapping[str, object]] | None = None,
    targets: Sequence[Mapping[str, object]] | None = None,
    reset: bool = False,
) -> Path:
    """Preserve an incomplete lifecycle without representing it as promotable proof."""
    _validate_manifest(manifest)
    output = provisional_root / str(manifest["run_id"])
    output.mkdir(parents=True, exist_ok=True)
    allowed = set(_EVIDENCE_FILES) | {"SHA256SUMS", "raw"}
    unexpected = {item.name for item in output.iterdir()} - allowed
    if unexpected:
        raise ControllerError("failure provisional contains unexpected files")
    raw_root = output / "raw/decisions"
    raw_root.mkdir(parents=True, exist_ok=True)
    if raw_decisions is not None and set(raw_decisions) != set(_TRACKS):
        raise ControllerError("failure raw decisions do not cover fixed tracks")
    parsed_decisions: list[dict[str, object]] = []
    for track in _TRACKS:
        path = raw_root / f"{track.value}.jsonl"
        if raw_decisions is not None:
            payload = raw_decisions[track]
            parsed = _parse_jsonl_bytes(
                payload,
                f"failure raw decisions {track.value}",
                _decision_closed,
                allow_empty=True,
            )
            if any(record["track"] != track.value for record in parsed):
                raise ControllerError("failure raw decision track is invalid")
            parsed_decisions.extend(parsed)
            _write_file(path, payload, 0o444)
        elif reset or not path.exists():
            _write_file(path, b"", 0o444)
    supplied = {
        "requests.jsonl": requests,
        "decisions.jsonl": (
            _normalized_decision_records(manifest, parsed_decisions)
            if raw_decisions is not None
            else None
        ),
        "envoy.jsonl": envoy,
        "targets.jsonl": targets,
        "joins.jsonl": None,
    }
    for name, records in supplied.items():
        path = output / name
        if records is not None:
            _write_file(path, _jsonl_payload(records), 0o444)
        elif reset or not path.exists():
            _write_file(path, b"", 0o444)
    _write_file(output / "manifest.json", _canonical_bytes(manifest), 0o444)
    _write_file(
        output / "summary.md",
        (
            "# KIL V3B-1 incomplete private lifecycle evidence\n\n"
            "This provisional bundle is non-promotable and awaits verified teardown.\n\n"
            f"{_KTP_CITATION}"
        ).encode("utf-8"),
        0o444,
    )
    normalized = (
        _normalized_decision_records(manifest, parsed_decisions)
        if parsed_decisions
        else []
    )
    _write_file(
        output / "live.html",
        _render_live_html(_presenter_model(manifest, normalized, [])),
        0o444,
    )
    _write_sums(output)
    _verify_sums(output)
    return output


def finalize_teardown_evidence(output: Path, run_id: str) -> None:
    """Finalize teardown only after exact runtime cleanup has completed."""
    manifest_path = output / "manifest.json"
    manifest = _load_json_bytes(manifest_path.read_bytes(), "evidence manifest")
    _validate_manifest(manifest)
    if manifest["run_id"] != run_id:
        raise ControllerError("teardown run does not match evidence manifest")
    teardown = manifest["teardown"]
    assert isinstance(teardown, dict)
    teardown.update(
        {
            "status": "complete",
            "containers_removed": True,
            "network_removed": True,
            "profile_deleted": True,
        }
    )
    joins = _parse_jsonl_bytes(
        (output / "joins.jsonl").read_bytes(),
        "joins",
        lambda record: None,
        allow_empty=False,
    )
    decisions = _parse_jsonl_bytes(
        (output / "decisions.jsonl").read_bytes(),
        "presenter decisions",
        lambda record: None,
        allow_empty=False,
    )
    expected_presenter = _render_live_html(
        _presenter_model(manifest, decisions, joins)
    )
    if (output / "live.html").read_bytes() != expected_presenter:
        raise ControllerError("teardown presenter changed before finalization")
    _write_file(manifest_path, _canonical_bytes(manifest), 0o444)
    _write_file(output / "summary.md", _summary(manifest, joins).encode("utf-8"), 0o444)
    _write_sums(output)
    _verify_sums(output)


def _default_port_probe(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.1)
        return probe.connect_ex(("127.0.0.1", port)) == 0


class LocalEnvoyController:
    """Exact lifecycle controller with an injected argv command runner."""

    def __init__(
        self,
        root: Path = ROOT,
        runner: CommandRunner | None = None,
        *,
        home: Path | None = None,
        port_probe: Callable[[int], bool] = _default_port_probe,
        tool_verifier: Callable[[], object] | None = None,
        connection_factory: Callable[..., object] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
        sleeper: Callable[[float], None] | None = None,
        publication_fault: Callable[[str, Path], None] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.runner = runner or SubprocessCommandRunner()
        self.home = (home or Path.home()).resolve()
        self.profile_path = self.root / "deploy/kind/v3b-profile.json"
        self.profile = V3BProfile.load(self.profile_path)
        self.docker_binary = self.root / ".tools/bin/docker"
        self.docker_config = self.root / ".tools/v3b1-docker-config"
        self.staging_root = self.root / ".tools/v3b1-staging"
        self.private_root = self.root / ".tools/v3b1-private"
        self.journal_path = self.private_root / "journal.json"
        self.readiness_poison_path = self.private_root / "readiness-poison.json"
        self.manifest_root = self.private_root / "manifests"
        self.provisional_root = self.private_root / "provisional"
        self.source_freeze_root = self.private_root / "source-freezes"
        self.completed_root = self.private_root / "completed"
        self.publication_staging_root = self.private_root / "publication-staging"
        self.state_path = self.root / ".tools/state/v3b1-active.json"
        self.evidence_root = self.root / "artifacts/generated/v3b1-local-envoy"
        self.docker_host = (
            f"unix://{self.home}/.colima/{LAB_IDENTITY}/docker.sock"
        )
        self.port_probe = port_probe
        self.tool_verifier = tool_verifier or self._verify_tool_lock
        self.connection_factory = (
            http.client.HTTPConnection
            if connection_factory is None
            else connection_factory
        )
        self.monotonic_ns = time.monotonic_ns if monotonic_ns is None else monotonic_ns
        self.sleeper = time.sleep if sleeper is None else sleeper
        self.publication_fault = publication_fault
        self.command_env = {
            "HOME": str(self.home),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.environ.get("PATH", os.defpath),
        }
        self.docker_env = {**self.command_env, "DOCKER_BUILDKIT": "0"}

    def _execute(
        self,
        argv: Sequence[str],
        *,
        timeout_s: float,
        docker: bool = False,
    ) -> CommandResult:
        if not argv or any(type(part) is not str or not part for part in argv):
            raise ControllerError("controller command is not an explicit argv list")
        if docker:
            required_prefix = [
                str(self.docker_binary),
                "--config",
                str(self.docker_config),
                "--host",
                self.docker_host,
            ]
            if list(argv[:5]) != required_prefix:
                raise ControllerError("Docker command is not explicitly isolated")
            if not self.docker_config.is_dir() or any(self.docker_config.iterdir()):
                raise ControllerError("controller Docker config is not an empty directory")
        result = self.runner.run(
            list(argv),
            cwd=self.root,
            env=self.docker_env if docker else self.command_env,
            timeout_s=timeout_s,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[:1000]
            raise ControllerError(f"command failed ({argv[0]}): {detail}")
        return result

    def _execute_optional(
        self,
        argv: Sequence[str],
        *,
        timeout_s: float,
        docker: bool = False,
    ) -> CommandResult:
        if not argv or any(type(part) is not str or not part for part in argv):
            raise ControllerError("controller command is not an explicit argv list")
        if docker:
            required_prefix = [
                str(self.docker_binary), "--config", str(self.docker_config),
                "--host", self.docker_host,
            ]
            if list(argv[:5]) != required_prefix:
                raise ControllerError("Docker command is not explicitly isolated")
            if not self.docker_config.is_dir() or any(self.docker_config.iterdir()):
                raise ControllerError("controller Docker config is not an empty directory")
        return self.runner.run(
            list(argv),
            cwd=self.root,
            env=self.docker_env if docker else self.command_env,
            timeout_s=timeout_s,
        )

    def _verify_tool_lock(self) -> object:
        version_arguments = {
            "docker": ("--version",),
            "kind": ("version",),
            "kubectl": ("version", "--client", "-o", "json"),
        }

        def version_runner(name: str, binary: Path) -> str:
            result = self._execute(
                [str(binary), *version_arguments[name]], timeout_s=20
            )
            return (result.stdout + result.stderr).strip()

        return verify_content_lock(
            self.root / ".tools/locks/v3b-tools.json",
            self.profile_path,
            self.root / ".tools",
            version_runner=version_runner,
            require_complete=True,
        )

    def _execution_staging_root(
        self, execution_nonce: str, *, create: bool = False
    ) -> Path:
        _require_sha256("execution staging nonce", execution_nonce)
        path = self.staging_root / execution_nonce
        _require_contained(path, self.staging_root, "execution staging root")
        if path.is_symlink():
            raise ControllerError("execution staging root cannot be a symbolic link")
        if create:
            path.mkdir(parents=False, exist_ok=True)
            _require_contained(path, self.staging_root, "execution staging root")
            if path.is_symlink() or not path.is_dir():
                raise ControllerError("execution staging root is missing or unsafe")
            os.chmod(path, 0o700)
        return path

    def colima_start_command(self, execution_nonce: str) -> list[str]:
        execution_staging = self._execution_staging_root(execution_nonce)
        return [
            "colima",
            "start",
            "--profile",
            LAB_IDENTITY,
            "--runtime",
            "docker",
            "--activate=false",
            "--ssh-config=false",
            "--cpus",
            "4",
            "--memory",
            "8",
            "--disk",
            "60",
            "--vm-type",
            "vz",
            "--kubernetes=false",
            "--arch=aarch64",
            "--save-config=true",
            "--template=false",
            "--binfmt=false",
            "--vz-rosetta=false",
            "--mount-inotify=false",
            "--network-mode=shared",
            "--network-address=false",
            "--network-host-addresses=false",
            "--network-preferred-route=false",
            "--port-forwarder=ssh",
            "--ssh-agent=false",
            "--mount",
            str(execution_staging),
            "--mount-type=virtiofs",
        ]

    def docker_command(self, *arguments: str) -> list[str]:
        if any(type(item) is not str or not item for item in arguments):
            raise ControllerError("Docker arguments must be nonempty strings")
        return [
            str(self.docker_binary),
            "--config",
            str(self.docker_config),
            "--host",
            self.docker_host,
            *arguments,
        ]

    def validate_ports(self) -> None:
        for port in _TRACK_PORTS.values():
            if self.port_probe(port):
                raise ControllerError(f"gateway port {port} is occupied")

    def preflight(self) -> dict[str, object]:
        tools = self.tool_verifier()
        colima = self._execute(["colima", "version"], timeout_s=20)
        lima = self._execute(["limactl", "--version"], timeout_s=20)
        if self.profile.colima_version not in (colima.stdout + colima.stderr):
            raise ControllerError("Colima version does not match profile")
        if self.profile.lima_version not in (lima.stdout + lima.stderr):
            raise ControllerError("Lima version does not match profile")
        listed = self._execute(["colima", "list", "--json"], timeout_s=20)
        profiles = parse_colima_profiles(listed.stdout)
        validate_colima_profiles(profiles)
        self.validate_ports()
        return {
            "profiles": profiles,
            "ports": tuple(_TRACK_PORTS.values()),
            "tool_identities": _tool_identity_projection(tools),
        }

    def _prepare_private_roots(self) -> None:
        for path, label in (
            (self.staging_root, "Colima staging root"),
            (self.docker_config, "Docker config root"),
            (self.private_root, "controller private root"),
            (self.state_path.parent, "active state directory"),
            (self.evidence_root, "public evidence root"),
        ):
            _require_contained(path, self.root, label)
            if path.is_symlink():
                raise ControllerError(f"{label} cannot be a symbolic link")
            path.mkdir(parents=True, exist_ok=True)
        if any(self.docker_config.iterdir()):
            raise ControllerError("controller Docker config directory must be empty")
        os.chmod(self.staging_root, 0o700)
        os.chmod(self.docker_config, 0o700)
        os.chmod(self.private_root, 0o700)
        self._ensure_private_child(self.manifest_root, "private manifest root")
        self._ensure_private_child(self.provisional_root, "private provisional root")
        self._ensure_private_child(self.source_freeze_root, "private source freeze root")
        self._ensure_private_child(self.completed_root, "private completed root")
        self._ensure_private_child(
            self.publication_staging_root, "private publication staging root"
        )

    def _ensure_private_child(self, path: Path, label: str) -> Path:
        _require_contained(path, self.private_root, label)
        if path.is_symlink():
            raise ControllerError(f"{label} cannot be a symbolic link")
        path.mkdir(parents=False, exist_ok=True)
        resolved = _require_contained(path, self.private_root, label)
        if path.is_symlink() or not path.is_dir() or resolved != path.resolve():
            raise ControllerError(f"{label} is missing or unsafe")
        os.chmod(path, 0o700)
        return path

    def _private_manifest_root(self) -> Path:
        return self._ensure_private_child(
            self.manifest_root, "private manifest root"
        )

    def _private_provisional_root(self) -> Path:
        return self._ensure_private_child(
            self.provisional_root, "private provisional root"
        )

    def _private_completed_root(self) -> Path:
        return self._ensure_private_child(
            self.completed_root, "private completed root"
        )

    def _private_source_freeze_root(self) -> Path:
        return self._ensure_private_child(
            self.source_freeze_root, "private source freeze root"
        )

    def _private_publication_root(self) -> Path:
        return self._ensure_private_child(
            self.publication_staging_root, "private publication staging root"
        )

    def _load_readiness_poison(self) -> dict[str, object] | None:
        path = self.readiness_poison_path
        _require_contained(path, self.private_root, "readiness poison sentinel")
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise ControllerError("readiness poison sentinel is unsafe")
        if (path.stat().st_mode & 0o7777) != 0o600:
            raise ControllerError("readiness poison sentinel mode is unsafe")
        payload = path.read_bytes()
        value = _load_json_bytes(payload, "readiness poison sentinel")
        expected = {
            "schema_version",
            "execution_nonce",
            "readiness_nonce",
            "reason_category",
            "binding_sha256",
        }
        if (
            set(value) != expected
            or value["schema_version"] != READINESS_POISON_SCHEMA
        ):
            raise ControllerError("readiness poison sentinel fields are not closed")
        if payload != _canonical_bytes(value):
            raise ControllerError("readiness poison sentinel is not canonical")
        _require_sha256("readiness poison execution nonce", value["execution_nonce"])
        _require_sha256("readiness poison readiness nonce", value["readiness_nonce"])
        if value["reason_category"] != "connection_close_ambiguous":
            raise ControllerError("readiness poison reason category is invalid")
        if value["binding_sha256"] != _journal_binding(value):
            raise ControllerError("readiness poison sentinel binding does not match")
        journal = load_lifecycle_journal(self.journal_path)
        if value["execution_nonce"] != journal["execution_nonce"]:
            raise ControllerError("readiness poison sentinel lifecycle does not match")
        events = journal["events"]
        assert isinstance(events, list)
        if not any(
            event["event"] == "readiness_session_started"
            and event["details"]["readiness_nonce"] == value["readiness_nonce"]
            for event in events
        ):
            raise ControllerError("readiness poison sentinel session does not match")
        return value

    def _assert_no_readiness_poison(self) -> None:
        if self._load_readiness_poison() is not None:
            raise ControllerError(
                "readiness is poisoned; teardown or manual recovery is required"
            )

    def _persist_readiness_poison(
        self,
        *,
        readiness_nonce: str,
        reason_category: str,
    ) -> None:
        _require_sha256("readiness poison readiness nonce", readiness_nonce)
        if reason_category != "connection_close_ambiguous":
            raise ControllerError("readiness poison reason category is invalid")
        journal = load_lifecycle_journal(self.journal_path)
        events = journal["events"]
        assert isinstance(events, list)
        current_readiness, _ = _validate_lifecycle_history(
            events, journal["requests"]  # type: ignore[arg-type]
        )
        if current_readiness != readiness_nonce:
            raise ControllerError("readiness poison session is not current")
        unsigned = {
            "schema_version": READINESS_POISON_SCHEMA,
            "execution_nonce": journal["execution_nonce"],
            "readiness_nonce": readiness_nonce,
            "reason_category": reason_category,
        }
        value = {**unsigned, "binding_sha256": _journal_binding(unsigned)}
        existing = self._load_readiness_poison()
        if existing is not None:
            if existing != value:
                raise ControllerError("readiness poison sentinel would be clobbered")
            return
        _require_contained(
            self.readiness_poison_path,
            self.private_root,
            "readiness poison sentinel",
        )
        _write_file(
            self.readiness_poison_path,
            _canonical_bytes(value),
            0o600,
        )
        if self._load_readiness_poison() != value:
            raise ControllerError("readiness poison sentinel write was not durable")

    def _clear_readiness_poison(self, execution_nonce: str) -> None:
        _require_sha256("readiness poison execution nonce", execution_nonce)
        value = self._load_readiness_poison()
        if value is None:
            return
        if value["execution_nonce"] != execution_nonce:
            raise ControllerError("readiness poison sentinel lifecycle does not match")
        self.readiness_poison_path.unlink()
        directory_fd = os.open(self.private_root, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _capture_global_context(self) -> str:
        """Observe, but never mutate, the user's global Docker context."""
        result = self._execute(
            [str(self.docker_binary), "context", "show"], timeout_s=20
        )
        context = result.stdout.strip()
        if not context or "\n" in context or "\r" in context:
            raise ControllerError("global Docker context observation is invalid")
        return context

    def _capture_engine_provenance(self) -> dict[str, object]:
        version = self._execute(
            self.docker_command("version", "--format", "{{json .Server}}"),
            timeout_s=60,
            docker=True,
        )
        info = self._execute(
            self.docker_command("info", "--format", "{{json .}}"),
            timeout_s=60,
            docker=True,
        )
        try:
            version_value = json.loads(version.stdout, object_pairs_hook=_closed_object)
            info_value = json.loads(info.stdout, object_pairs_hook=_closed_object)
        except (json.JSONDecodeError, ControllerError) as error:
            raise ControllerError("Docker engine provenance is not closed JSON") from error
        if type(version_value) is not dict or type(info_value) is not dict:
            raise ControllerError("Docker engine provenance is invalid")
        observed_architecture = info_value.get("Architecture")
        result = {
            "server_version": version_value.get("Version"),
            "api_version": version_value.get("ApiVersion"),
            "git_commit": version_value.get("GitCommit"),
            "go_version": version_value.get("GoVersion"),
            "os": info_value.get("OSType"),
            "architecture": "arm64" if observed_architecture in {"aarch64", "arm64"} else observed_architecture,
            "kernel_version": info_value.get("KernelVersion"),
            "storage_driver": info_value.get("Driver"),
            "cgroup_driver": info_value.get("CgroupDriver"),
            "cgroup_version": info_value.get("CgroupVersion"),
        }
        if result["os"] != "linux" or result["architecture"] != "arm64":
            raise ControllerError("Docker engine is not the required linux/arm64 server")
        if any(value is None for value in result.values()):
            raise ControllerError("Docker engine provenance is incomplete")
        return result

    def _verify_profile_absent(self) -> None:
        listed = self._execute(["colima", "list", "--json"], timeout_s=30)
        profiles = parse_colima_profiles(listed.stdout)
        if any(record["name"] == LAB_IDENTITY for record in profiles):
            raise ControllerError("dedicated Colima profile remains after deletion")

    def _validate_controller_identity(self, execution_nonce: str) -> str:
        _require_sha256("Colima execution nonce", execution_nonce)
        execution_staging = self._execution_staging_root(execution_nonce)
        identity_path = execution_staging / f"ownership-{execution_nonce}.json"
        _require_contained(
            identity_path, execution_staging, "Colima ownership identity"
        )
        expected = _canonical_bytes(
            {
                "schema_version": "kil.v3b1-colima-ownership.v1",
                "execution_nonce": execution_nonce,
                "profile": LAB_IDENTITY,
            }
        )
        if (
            identity_path.is_symlink()
            or not identity_path.is_file()
            or identity_path.read_bytes() != expected
        ):
            raise ControllerError("controller-specific Colima identity is unavailable")
        return _digest_bytes(expected)

    def _attest_colima_after_start(
        self, execution_nonce: str
    ) -> dict[str, object]:
        listed = self._execute(["colima", "list", "--json"], timeout_s=30)
        profiles = parse_colima_profiles(listed.stdout)
        matches = [record for record in profiles if record["name"] == LAB_IDENTITY]
        if len(matches) != 1:
            raise ControllerError("dedicated Colima profile identity is not unique")
        profile = validate_dedicated_colima_profile(matches[0])
        identity_sha256 = self._validate_controller_identity(execution_nonce)
        config_path = self.home / ".colima" / LAB_IDENTITY / "colima.yaml"
        _require_contained(config_path, self.home, "saved Colima config")
        if config_path.is_symlink() or not config_path.is_file():
            raise ControllerError("saved Colima config is missing or unsafe")
        saved_config = _parse_saved_colima_config(
            config_path.read_bytes(), self._execution_staging_root(execution_nonce)
        )
        return {
            "profile": profile,
            "saved_config": saved_config,
            "controller_identity_sha256": identity_sha256,
        }

    def _resolve_image(self, tag: str) -> tuple[str, str]:
        self._execute(
            self.docker_command("image", "pull", "--platform", PLATFORM, tag),
            timeout_s=900,
            docker=True,
        )
        inspected = self._execute(
            self.docker_command(
                "image", "inspect", "--format", "{{json .RepoDigests}}", tag
            ),
            timeout_s=60,
            docker=True,
        )
        digest = select_registry_digest(tag, inspected.stdout.strip())
        image = self._execute(
            self.docker_command("image", "inspect", "--format", "{{.Id}}", digest),
            timeout_s=60,
            docker=True,
        ).stdout.strip()
        if _IMAGE_ID.fullmatch(image) is None:
            raise ControllerError("resolved image did not produce an immutable image ID")
        architecture = self._execute(
            self.docker_command(
                "image", "inspect", "--format", "{{json .}}", image
            ),
            timeout_s=60,
            docker=True,
        )
        try:
            raw = json.loads(architecture.stdout, object_pairs_hook=_closed_object)
            validate_image_architecture(
                {"Os": raw.get("Os"), "Architecture": raw.get("Architecture")}
            )
        except (json.JSONDecodeError, ControllerError) as error:
            raise ControllerError("resolved image architecture attestation failed") from error
        return digest, image

    def _clean_source_identity(self) -> str:
        status = self._execute(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            timeout_s=30,
        )
        if status.stdout:
            raise ControllerError("source tree must be clean before live execution")
        commit = self._execute(
            ["git", "rev-parse", "HEAD"], timeout_s=30
        ).stdout.strip()
        if re.fullmatch(r"[a-f0-9]{40}", commit) is None:
            raise ControllerError("Git source commit is invalid")
        return commit

    def _build_kil_image(
        self, python_digest: str, *, build_key: str | None = None
    ) -> tuple[str, str]:
        if build_key is None:
            build_key = secrets.token_hex(32)
        _require_sha256("build_key", build_key)
        build_root = self.staging_root / "build" / build_key
        _require_contained(build_root, self.staging_root, "per-execution build root")
        build_root.mkdir(parents=True, exist_ok=True)
        context_root = build_root / "context"
        self._build_context_attestation = stage_build_context(self.root, context_root)
        iid_path = build_root / "kil-image.id"
        archive_path = build_root / "kil-image.tar"
        for path in (iid_path, archive_path):
            if path.exists():
                path.unlink()
        dockerfile = context_root / "deploy/kind/Dockerfile.v3b"
        dockerignore = context_root / "deploy/kind/Dockerfile.v3b.dockerignore"
        if any(path.is_symlink() or not path.is_file() for path in (dockerfile, dockerignore)):
            raise ControllerError("closed Docker build inputs are missing or unsafe")
        self._execute(
            self.docker_command(
                "build",
                "--platform",
                PLATFORM,
                "--pull=false",
                "--file",
                str(dockerfile),
                "--build-arg",
                f"PYTHON_BASE_IMAGE={python_digest}",
                "--iidfile",
                str(iid_path),
                str(context_root),
            ),
            timeout_s=1800,
            docker=True,
        )
        if iid_path.is_symlink() or not iid_path.is_file():
            raise ControllerError("Docker build did not record an image ID")
        image_id = iid_path.read_text(encoding="ascii").strip()
        if _IMAGE_ID.fullmatch(image_id) is None:
            raise ControllerError("built KIL image ID is not immutable")
        confirmed = self._execute(
            self.docker_command("image", "inspect", "--format", "{{.Id}}", image_id),
            timeout_s=60,
            docker=True,
        ).stdout.strip()
        if confirmed != image_id:
            raise ControllerError("built KIL image ID changed after build")
        architecture = self._execute(
            self.docker_command(
                "image", "inspect", "--format", "{{json .}}", image_id
            ),
            timeout_s=60,
            docker=True,
        )
        try:
            raw = json.loads(architecture.stdout, object_pairs_hook=_closed_object)
            validate_image_architecture(
                {"Os": raw.get("Os"), "Architecture": raw.get("Architecture")}
            )
        except (json.JSONDecodeError, ControllerError) as error:
            raise ControllerError("built image architecture attestation failed") from error
        self._execute(
            self.docker_command(
                "image", "save", "--output", str(archive_path), image_id
            ),
            timeout_s=900,
            docker=True,
        )
        if archive_path.is_symlink() or not archive_path.is_file():
            raise ControllerError("KIL image archive was not saved")
        return image_id, _digest_file(archive_path)

    def _config_path(self, manifest: Mapping[str, object], role: str, track: str) -> Path:
        name = "envoy.json" if role == "envoy" else f"{role}.json"
        return _runtime_root(self.root, manifest) / track / name

    def _inspect_container(
        self,
        identifier: str,
        manifest: Mapping[str, object],
        role: str,
        track: str,
        *,
        require_running: bool = True,
    ) -> dict[str, object]:
        if role not in {"authz", "target", "envoy", "driver"}:
            raise ControllerError("container role inspection is invalid")
        output = self._execute(
            self.docker_command(
                "inspect",
                "--format",
                "{{json .}}",
                identifier,
            ),
            timeout_s=60,
            docker=True,
        ).stdout
        try:
            raw = json.loads(output, object_pairs_hook=_closed_object)
        except (json.JSONDecodeError, ControllerError) as error:
            raise ControllerError("container inspection is not closed JSON") from error
        if type(raw) is not dict:
            raise ControllerError("container inspection shape is invalid")
        try:
            object_id = raw["Id"]
            name = raw["Name"]
            image_id = raw["Image"]
            config_value = raw["Config"]
            host = raw["HostConfig"]
            state_value = raw["State"]
            network_settings = raw["NetworkSettings"]
            mounts_value = raw["Mounts"]
            assert isinstance(config_value, dict)
            assert isinstance(host, dict)
            assert isinstance(state_value, dict)
            assert isinstance(network_settings, dict)
            assert isinstance(mounts_value, list)
            image_reference = config_value["Image"]
            labels = config_value["Labels"]
            privileged = host["Privileged"]
            network_mode = host["NetworkMode"]
            pid_mode = host["PidMode"]
            ipc_mode = host["IpcMode"]
            uts_mode = host["UTSMode"]
            userns_mode = host["UsernsMode"]
        except (KeyError, TypeError, AssertionError) as error:
            raise ControllerError("container inspection required fields are missing") from error
        expected_labels = _object_labels(str(manifest["run_id"]), role, track)
        track_manifest = _track_manifest(manifest, LiveTrack(track))
        expected_name = str(track_manifest[f"{role}_container"])
        health_value = state_value.get("Health")
        health = (
            health_value.get("Status") if isinstance(health_value, dict) else "none"
        )
        running = state_value.get("Running") is True
        state_status = state_value.get("Status")
        if type(state_status) is not str:
            state_status = "running" if running else "exited"
        if (
            type(object_id) is not str
            or _HEX.fullmatch(object_id) is None
            or name != f"/{expected_name}"
            or (require_running and role != "driver" and not running)
            or (role == "driver" and (running or state_status != "created"))
            or (require_running and role not in {"envoy", "driver"} and health != "healthy")
            or (require_running and role == "envoy" and health not in {"healthy", "none"})
        ):
            raise ControllerError("container ID/name/label/running attestation failed")
        expected_image_id = (
            manifest["envoy_image_id"] if role == "envoy" else manifest["kil_image_id"]
        )
        expected_reference = (
            manifest["envoy_image_digest"] if role == "envoy" else manifest["kil_image_id"]
        )
        if image_id != expected_image_id or image_reference != expected_reference:
            raise ControllerError("container immutable image attestation failed")
        architecture = self._execute(
            self.docker_command(
                "image", "inspect", "--format", "{{json .}}", str(image_id)
            ),
            timeout_s=60,
            docker=True,
        )
        try:
            image_value = json.loads(
                architecture.stdout, object_pairs_hook=_closed_object
            )
            validate_image_architecture(
                {
                    "Os": image_value.get("Os"),
                    "Architecture": image_value.get("Architecture"),
                }
            )
            image_config = image_value.get("Config")
            if type(image_config) is not dict or config_value.get("Env") != image_config.get("Env"):
                raise ControllerError("container environment diverges from immutable image")
        except (json.JSONDecodeError, ControllerError, AttributeError) as error:
            raise ControllerError("container image architecture attestation failed") from error
        _validate_container_labels(
            labels, image_config.get("Labels"), expected_labels
        )
        config: Path | None = None
        if role != "driver":
            config = self._config_path(manifest, role, track)
            if (
                config.is_symlink()
                or not config.is_file()
                or config.stat().st_mode & 0o222
            ):
                raise ControllerError("container config is not fixed read-only input")
        security = host.get("SecurityOpt") or []
        if security == ["no-new-privileges:true"]:
            security = ["no-new-privileges"]
        raw_networks = network_settings.get("Networks")
        if type(raw_networks) is not dict:
            raise ControllerError("container network inspection is invalid")
        network_aliases: dict[str, list[str]] = {}
        for network_name, endpoint in raw_networks.items():
            if type(network_name) is not str or type(endpoint) is not dict:
                raise ControllerError("container network inspection is invalid")
            aliases = endpoint.get("Aliases")
            if aliases is None:
                aliases = []
            if (
                type(aliases) is not list
                or any(type(alias) is not str or not alias for alias in aliases)
            ):
                raise ControllerError("container network aliases are invalid")
            network_aliases[network_name] = list(aliases)
        raw_log = host.get("LogConfig")
        if type(raw_log) is not dict:
            raise ControllerError("container log inspection is invalid")
        actual = {
            "id": object_id,
            "name": expected_name,
            "image_id": image_id,
            "user": config_value.get("User"),
            "readonly_rootfs": host.get("ReadonlyRootfs"),
            "cap_drop": host.get("CapDrop") or [],
            "security_opt": security,
            "nano_cpus": host.get("NanoCpus"),
            "memory": host.get("Memory"),
            "memory_swap": host.get("MemorySwap"),
            "pids_limit": host.get("PidsLimit"),
            "restart_policy": (
                host.get("RestartPolicy") or {}
            ).get("Name"),
            "stop_timeout": config_value.get("StopTimeout"),
            "log_driver": raw_log.get("Type"),
            "log_options": raw_log.get("Config") or {},
            "tmpfs": _normalize_inspected_tmpfs(host.get("Tmpfs") or {}),
            "mounts": [
                {
                    "source": item.get("Source"),
                    "destination": item.get("Destination"),
                    "rw": item.get("RW"),
                }
                for item in mounts_value
                if isinstance(item, dict)
            ],
            "networks": sorted(raw_networks),
            "network_aliases": {
                name: network_aliases[name] for name in sorted(network_aliases)
            },
            "port_bindings": host.get("PortBindings"),
            "published_ports": network_settings.get("Ports"),
            "platform": PLATFORM,
            "entrypoint": config_value.get("Entrypoint") or [],
            "command": config_value.get("Cmd") or [],
            "environment": config_value.get("Env") or [],
            "state": state_status,
            "stdin_open": config_value.get("OpenStdin", False),
            "tty": config_value.get("Tty", False),
            "healthcheck": (
                "disabled"
                if config_value.get("Healthcheck") == {"Test": ["NONE"]}
                else None
                if config_value.get("Healthcheck") is None
                else "configured"
            ),
            "privileged": privileged,
            "network_mode": network_mode,
            "pid_mode": pid_mode,
            "ipc_mode": "" if ipc_mode == "private" else ipc_mode,
            "uts_mode": uts_mode,
            "userns_mode": userns_mode,
        }
        if role == "envoy":
            expected_networks = [
                str(track_manifest["backend_network"]),
                str(track_manifest["frontend_network"]),
            ]
        elif role == "driver":
            expected_networks = [str(track_manifest["frontend_network"])]
        else:
            expected_networks = [
                str(track_manifest.get("backend_network", track_manifest.get("network")))
            ]
        required_aliases = {
            network: [
                "envoy"
                if role == "envoy" and network == track_manifest.get("frontend_network")
                else expected_name
            ]
            for network in expected_networks
        }
        driver_definition_value: dict[str, object] | None = None
        if role == "driver":
            definitions = manifest.get("driver_definitions")
            if type(definitions) is not list:
                raise ControllerError("driver definition is unavailable")
            driver_definition_value = next(
                (
                    dict(item)
                    for item in definitions
                    if type(item) is dict and item.get("track") == track
                ),
                None,
            )
            if driver_definition_value is None:
                raise ControllerError("driver definition is unavailable")
        expected = {
            "name": expected_name,
            "role": role,
            "track": track,
            "image_id": expected_image_id,
            "networks": sorted(expected_networks),
            "config_path": None if config is None else str(config),
            "config_sha256": None if config is None else _digest_file(config),
            "gateway_port": None,
            "required_aliases": required_aliases,
            "driver_definition": driver_definition_value,
            "required_state": (
                "created" if role == "driver" else "running" if require_running else None
            ),
            "primary_network": str(
                track_manifest["frontend_network"]
                if role == "driver"
                else track_manifest.get(
                    "backend_network", track_manifest.get("network")
                )
            ),
        }
        validate_container_attestation(actual, expected)
        return {
            "name": expected_name,
            "id": object_id,
            "role": role,
            "track": track,
            "labels": expected_labels,
            "image_id": image_id,
            "image_reference": image_reference,
            "config_path": None if config is None else str(config),
            "config_sha256": (
                None if config is None else _digest_bytes(config.read_bytes())
            ),
            "runtime_attestation": actual,
        }

    def _inspect_network(
        self,
        identifier: str,
        manifest: Mapping[str, object],
        track: str,
        *,
        segment: str = "backend",
        require_complete_membership: bool = True,
        require_empty_membership: bool = False,
    ) -> dict[str, object]:
        if segment not in {"backend", "frontend"}:
            raise ControllerError("network segment inspection is invalid")
        raw_output = self._execute(
            self.docker_command(
                "network",
                "inspect",
                "--format",
                "{{json .}}",
                identifier,
            ),
            timeout_s=60,
            docker=True,
        ).stdout
        try:
            raw = json.loads(raw_output, object_pairs_hook=_closed_object)
        except (json.JSONDecodeError, ControllerError) as error:
            raise ControllerError("network inspection is not closed JSON") from error
        required = {"Id", "Name", "Driver", "Internal", "Labels", "Containers"}
        if type(raw) is not dict or not required.issubset(raw):
            raise ControllerError("network inspection shape is invalid")
        object_id = raw["Id"]
        name = raw["Name"]
        driver = raw["Driver"]
        internal = raw["Internal"]
        labels = raw["Labels"]
        containers = raw["Containers"]
        track_value = _track_manifest(manifest, LiveTrack(track))
        expected_name = str(
            track_value[
                f"{segment}_network"
                if f"{segment}_network" in track_value
                else "network"
            ]
        )
        expected_labels = _object_labels(str(manifest["run_id"]), None, track)
        if (
            type(object_id) is not str
            or _HEX.fullmatch(object_id) is None
            or (_HEX.fullmatch(identifier) is not None and object_id != identifier)
            or type(name) is not str
            or name != expected_name
            or type(driver) is not str
            or driver != "bridge"
            or type(internal) is not bool
            or internal is not True
            or type(labels) is not dict
            or any(
                type(key) is not str or type(value) is not str
                for key, value in labels.items()
            )
            or labels != expected_labels
        ):
            raise ControllerError(
                "network identity/label/internal type attestation failed"
            )
        if type(containers) is not dict:
            raise ControllerError("network membership shape is invalid")
        endpoint_fields = {
            "Name", "EndpointID", "MacAddress", "IPv4Address", "IPv6Address",
        }
        members: list[str] = []
        for container_id, endpoint in containers.items():
            if (
                type(container_id) is not str
                or _HEX.fullmatch(container_id) is None
                or type(endpoint) is not dict
                or set(endpoint) != endpoint_fields
                or any(type(value) is not str for value in endpoint.values())
                or not endpoint["Name"]
                or _HEX.fullmatch(endpoint["EndpointID"]) is None
            ):
                raise ControllerError("network membership shape is invalid")
            members.append(endpoint["Name"])
        expected_roles = (
            {"envoy", "authz", "target"}
            if segment == "backend"
            else {"envoy", "driver"}
        )
        expected_members = {
            str(item["name"])
            for item in manifest["containers"]  # type: ignore[union-attr]
            if item["track"] == track and item["role"] in expected_roles
        }
        if (
            not set(members).issubset(expected_members)
            or len(members) != len(set(members))
            or (require_complete_membership and set(members) != expected_members)
            or (require_empty_membership and members)
        ):
            raise ControllerError(
                f"cross-track or incomplete {segment} network membership"
            )
        return {
            "name": name,
            "id": object_id,
            "track": track,
            "segment": segment,
            "labels": labels,
        }

    def _inspect_validation_container(
        self, identifier: str, manifest: Mapping[str, object], track: LiveTrack
    ) -> dict[str, object]:
        raw_output = self._execute(
            self.docker_command("inspect", "--format", "{{json .}}", identifier),
            timeout_s=60,
            docker=True,
        ).stdout
        try:
            raw = json.loads(raw_output, object_pairs_hook=_closed_object)
        except (json.JSONDecodeError, ControllerError) as error:
            raise ControllerError("Envoy validator inspection is not closed JSON") from error
        if type(raw) is not dict or type(raw.get("Config")) is not dict or type(raw.get("HostConfig")) is not dict:
            raise ControllerError("Envoy validator inspection fields are invalid")
        config = raw["Config"]
        host = raw["HostConfig"]
        assert isinstance(config, dict) and isinstance(host, dict)
        name = f"kil-v3b1-validate-{_track_slug(track)}-{str(manifest['content_identity_sha256'])[:12]}"
        labels = _object_labels(str(manifest["run_id"]), "validator", track.value)
        security = host.get("SecurityOpt") or []
        if security == ["no-new-privileges:true"]:
            security = ["no-new-privileges"]
        if (
            type(raw.get("Id")) is not str
            or _HEX.fullmatch(str(raw["Id"])) is None
            or raw["Id"] != identifier
            or raw.get("Name") != f"/{name}"
            or raw.get("Image") != manifest["envoy_image_id"]
            or config.get("Image") != manifest["envoy_image_digest"]
            or config.get("User") != "65532:65532"
            or config.get("Entrypoint") != ["/usr/local/bin/envoy"]
            or config.get("Cmd") != [
                "--mode", "validate", "--config-path", "/etc/envoy/envoy.json",
                "--disable-hot-restart", "--concurrency", "1",
            ]
            or host.get("ReadonlyRootfs") is not True
            or host.get("AutoRemove") is not False
            or host.get("CapDrop") != ["ALL"]
            or security != ["no-new-privileges"]
            or host.get("NetworkMode") != "none"
            or (host.get("PortBindings") or {}) != {}
        ):
            raise ControllerError("Envoy validator immutable/sandbox attestation failed")
        image_inspection = self._execute(
            self.docker_command(
                "image", "inspect", "--format", "{{json .}}",
                str(manifest["envoy_image_id"]),
            ),
            timeout_s=60,
            docker=True,
        ).stdout
        try:
            image_value = json.loads(
                image_inspection, object_pairs_hook=_closed_object
            )
            if type(image_value) is not dict:
                raise ControllerError("Envoy validator image inspection is invalid")
            validate_image_architecture(
                {
                    "Os": image_value.get("Os"),
                    "Architecture": image_value.get("Architecture"),
                }
            )
            image_config = image_value.get("Config")
            if type(image_config) is not dict:
                raise ControllerError("Envoy validator image config is invalid")
        except (json.JSONDecodeError, ControllerError) as error:
            raise ControllerError(
                "Envoy validator immutable image attestation failed"
            ) from error
        _validate_container_labels(
            config.get("Labels"), image_config.get("Labels"), labels
        )
        return {
            "id": raw["Id"],
            "name": name,
            "role": "validator",
            "track": track.value,
            "labels": labels,
            "image_id": manifest["envoy_image_id"],
            "image_reference": manifest["envoy_image_digest"],
        }

    def _attest_runtime(
        self, manifest: dict[str, object]
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        deadline = time.monotonic() + 60
        while True:
            try:
                objects = []
                for item in manifest["containers"]:
                    objects.append(
                        self._inspect_container(
                            str(item["name"]),
                            manifest,
                            str(item["role"]),
                            str(item["track"]),
                            require_running=item["role"] != "driver",
                        )
                    )
                break
            except ControllerError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
        networks = [
            self._inspect_network(
                str(item["name"]),
                manifest,
                str(item["track"]),
                segment=_network_segment(item),
            )
            for item in _runtime_networks(manifest)
        ]
        return objects, networks

    def _run_validator_command(
        self,
        command: Sequence[str],
        manifest: dict[str, object],
        track: LiveTrack,
    ) -> dict[str, object]:
        """Create, wait for, and attest one explicitly retained validator."""
        expected_name = (
            f"kil-v3b1-validate-{_track_slug(track)}-"
            f"{str(manifest['content_identity_sha256'])[:12]}"
        )
        parts = list(command)
        if (
            "run" not in parts
            or "-d" not in parts
            or "--rm" in parts
            or "--name" not in parts
            or parts[parts.index("--name") + 1] != expected_name
            or "kil.v3b1.role=validator" not in parts
        ):
            raise ControllerError("validator creation command is not exact")
        journal_event(
            self.journal_path,
            "validator_create_intent",
            {"name": expected_name},
        )
        result = self._execute(parts, timeout_s=300, docker=True)
        object_id = result.stdout.strip()
        if _HEX.fullmatch(object_id) is None:
            raise ControllerError(
                "validator creation did not return an exact object ID"
            )
        identity = {"id": object_id, "name": expected_name}
        journal_event(
            self.journal_path,
            "validator_create_complete",
            identity,
        )
        journal_event(
            self.journal_path,
            "config_validate_intent",
            identity,
        )
        waited = self._execute(
            self.docker_command("wait", object_id),
            timeout_s=300,
            docker=True,
        )
        if waited.stdout != "0\n":
            raise ControllerError("Envoy validator did not exit successfully")
        current = self._inspect_validation_container(
            object_id, manifest, track
        )
        if (
            current.get("id") != object_id
            or current.get("name") != expected_name
            or current.get("role") != "validator"
            or current.get("track") != track.value
        ):
            raise ControllerError("Envoy validator identity changed after execution")
        journal_event(
            self.journal_path,
            "config_validate_complete",
            identity,
        )
        return current

    def _docker_inventory(self, kind: str) -> DockerInventory:
        """Read one no-truncation ID/name inventory; never infer from stderr."""
        if kind == "container":
            command = self.docker_command(
                "ps",
                "--all",
                "--no-trunc",
                "--format",
                '{"id":{{json .ID}},"name":{{json .Names}}}',
            )
        elif kind == "network":
            command = self.docker_command(
                "network",
                "ls",
                "--no-trunc",
                "--filter",
                "type=custom",
                "--format",
                '{"id":{{json .ID}},"name":{{json .Name}}}',
            )
        else:
            raise ControllerError("Docker inventory kind is invalid")
        result = self._execute(command, timeout_s=60, docker=True)
        try:
            return parse_inventory_rows(
                result.stdout,
                kind,
                schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION,
            )
        except (
            HarnessContractError,
            UnicodeError,
            ValueError,
            TypeError,
            RecursionError,
        ) as error:
            raise ControllerError(f"Docker {kind} inventory is invalid") from error

    @staticmethod
    def _require_exact_inventory(
        kind: str,
        actual: Mapping[str, str],
        expected: Mapping[str, str],
    ) -> None:
        """Require the exact full-ID/name bijection for one Docker object kind."""
        if kind not in {"container", "network"}:
            raise ControllerError("Docker inventory kind is invalid")
        try:
            if type(actual) is not dict or type(expected) is not dict:
                raise HarnessContractError("Docker inventory mapping is invalid")
            actual_entries = tuple(
                DockerInventoryEntry(
                    kind,
                    object_id,
                    name,
                    DRIVER_TOPOLOGY_SCHEMA_VERSION,
                )
                for object_id, name in actual.items()
            )
            expected_entries = tuple(
                DockerInventoryEntry(
                    kind,
                    object_id,
                    name,
                    DRIVER_TOPOLOGY_SCHEMA_VERSION,
                )
                for object_id, name in expected.items()
            )
            DockerInventory(
                kind,
                actual_entries,
                DRIVER_TOPOLOGY_SCHEMA_VERSION,
            )
            DockerInventory(
                kind,
                expected_entries,
                DRIVER_TOPOLOGY_SCHEMA_VERSION,
            )
        except (
            HarnessContractError,
            UnicodeError,
            ValueError,
            TypeError,
            RecursionError,
        ) as error:
            raise ControllerError(f"Docker {kind} inventory is invalid") from error
        if actual != expected:
            raise ControllerError(f"Docker {kind} inventory does not match ownership")

    @staticmethod
    def _inventory_mapping(inventory: DockerInventory) -> dict[str, str]:
        return {entry.object_id: entry.name for entry in inventory.entries}

    def _load_for_down(
        self,
    ) -> tuple[dict[str, object], dict[str, object] | None, dict[str, object]]:
        journal = load_lifecycle_journal(self.journal_path)
        if journal["docker_host"] != self.docker_host:
            raise ControllerError("lifecycle Docker host ownership does not match")
        manifest: dict[str, object] | None = None
        if journal["manifest_path"] is not None:
            manifest_path = Path(str(journal["manifest_path"]))
            manifest = _load_json_bytes(manifest_path.read_bytes(), "private manifest")
            _validate_manifest(manifest)
            if _digest_file(manifest_path) != journal["manifest_sha256"]:
                raise ControllerError("private manifest does not match lifecycle journal")
        bound_state_present = self.state_path.exists()
        if bound_state_present:
            bound = load_bound_active_state(self.state_path)
            if manifest is None or bound["manifest"] != manifest:
                raise ControllerError("active state and lifecycle manifest diverge")
            candidate_objects = bound["objects"]
            candidate_networks = bound["network_objects"]
        elif manifest is not None:
            candidate_objects = manifest["containers"]
            candidate_networks = _runtime_networks(manifest)
        else:
            candidate_objects = []
            candidate_networks = []
        events = journal["events"]
        assert isinstance(events, list)
        container_inventory = self._inventory_mapping(
            self._docker_inventory("container")
        )
        network_inventory = self._inventory_mapping(
            self._docker_inventory("network")
        )
        container_by_name = {
            name: object_id for object_id, name in container_inventory.items()
        }
        network_by_name = {
            name: object_id for object_id, name in network_inventory.items()
        }
        pending_absences: list[tuple[str, dict[str, str]]] = []

        def resolve_identity(
            kind: str,
            item: Mapping[str, object],
            by_id: Mapping[str, str],
            by_name: Mapping[str, str],
        ) -> tuple[str, str] | None:
            inventory_kind = "container" if kind == "validator" else kind
            name = str(item["name"])
            recorded_id = item.get("id")
            if type(recorded_id) is str:
                try:
                    DockerInventoryEntry(
                        inventory_kind,
                        recorded_id,
                        name,
                        DRIVER_TOPOLOGY_SCHEMA_VERSION,
                    )
                except HarnessContractError as error:
                    raise ControllerError(
                        "recorded Docker recovery identity is invalid"
                    ) from error
            elif bound_state_present and kind != "validator":
                raise ControllerError("bound Docker recovery identity lacks its ID")
            else:
                creation, created_id = _creation_transition(
                    events, kind, name
                )
                if creation == "unstarted":
                    if name in by_name:
                        raise ControllerError(
                            "unowned Docker object appeared during partial-up recovery"
                        )
                    return None
                if creation == "pending":
                    if name in by_name:
                        raise ControllerError(
                            "partial-up Docker object lacks a durably anchored full ID"
                        )
                    return None
                else:
                    recorded_id = created_id
            assert isinstance(recorded_id, str)
            identity = {"id": recorded_id, "name": name}
            transition = _removal_transition(events, inventory_kind, identity)
            actual_name = by_id.get(recorded_id)
            actual_id = by_name.get(name)
            if actual_name is not None or actual_id is not None:
                if actual_name != name or actual_id != recorded_id:
                    raise ControllerError(
                        f"recorded {kind} identity changed during recovery"
                    )
                if transition == "complete":
                    raise ControllerError(
                        f"completed {kind} removal identity reappeared"
                    )
                return recorded_id, name
            if transition == "pending":
                pending_absences.append((inventory_kind, identity))
                return None
            if transition == "complete":
                return None
            raise ControllerError(
                f"recorded {kind} disappeared before an exact removal intent"
            )

        objects: list[dict[str, object]] = []
        if manifest is not None:
            for item in candidate_objects:  # type: ignore[union-attr]
                resolved = resolve_identity(
                    "container",
                    item,
                    container_inventory,
                    container_by_name,
                )
                if resolved is None:
                    continue
                identifier, _ = resolved
                current = self._inspect_container(
                    identifier,
                    manifest,
                    str(item["role"]),
                    str(item["track"]),
                    require_running=False,
                )
                if "id" in item and not _container_attestation_matches(
                    item, current, allow_stopped=True
                ):
                    raise ControllerError("recorded container attestation changed during recovery")
                objects.append(current)
        networks: list[dict[str, object]] = []
        if manifest is not None:
            for item in candidate_networks:  # type: ignore[union-attr]
                resolved = resolve_identity(
                    "network",
                    item,
                    network_inventory,
                    network_by_name,
                )
                if resolved is None:
                    continue
                identifier, _ = resolved
                current = self._inspect_network(
                    identifier,
                    manifest,
                    str(item["track"]),
                    segment=str(item.get("segment", "backend")),
                    require_complete_membership=False,
                )
                if "id" in item and current != item:
                    raise ControllerError("recorded network attestation changed during recovery")
                networks.append(current)
        transient_objects: list[dict[str, object]] = []
        if manifest is not None:
            for track in _TRACKS:
                name = (
                    f"kil-v3b1-validate-{_track_slug(track)}-"
                    f"{str(manifest['content_identity_sha256'])[:12]}"
                )
                resolved = resolve_identity(
                    "validator",
                    {"name": name},
                    container_inventory,
                    container_by_name,
                )
                if resolved is None:
                    continue
                actual_id, _ = resolved
                current = self._inspect_validation_container(
                    actual_id, manifest, track
                )
                transient_objects.append(current)
        self._require_exact_inventory(
            "container",
            container_inventory,
            {
                str(item["id"]): str(item["name"])
                for item in [*objects, *transient_objects]
            },
        )
        self._require_exact_inventory(
            "network",
            network_inventory,
            {
                str(item["id"]): str(item["name"])
                for item in networks
            },
        )
        for kind, identity in pending_absences:
            journal_event(
                self.journal_path,
                f"{kind}_remove_complete",
                identity,
            )
        journal = load_lifecycle_journal(self.journal_path)
        state: dict[str, object] = {
            "objects": objects,
            "transient_objects": transient_objects,
            "network_objects": networks,
            "profile_created": journal["profile_created"],
            "colima_profile": LAB_IDENTITY,
            "docker_host": self.docker_host,
            "docker_config": str(self.docker_config),
        }
        return state, manifest, journal

    def up(self) -> dict[str, object]:
        if self.state_path.exists() or self.journal_path.exists():
            raise ControllerError("an active V3B-1 lifecycle already exists")
        preflight = self.preflight()
        profiles = preflight["profiles"]
        if any(record["name"] == LAB_IDENTITY for record in profiles):
            raise ControllerError("pre-existing dedicated profile is not controller-owned")
        source_commit = self._clean_source_identity()
        self._prepare_private_roots()
        execution_nonce = secrets.token_hex(32)
        execution_staging = self._execution_staging_root(
            execution_nonce, create=True
        )
        global_context = self._capture_global_context()
        create_lifecycle_journal(
            self.journal_path,
            private_root=self.private_root,
            repository_root=self.root,
            docker_host=self.docker_host,
            source_commit=source_commit,
            execution_nonce=execution_nonce,
            global_context=global_context,
        )
        ownership_path = execution_staging / f"ownership-{execution_nonce}.json"
        ownership_payload = _canonical_bytes(
            {
                "schema_version": "kil.v3b1-colima-ownership.v1",
                "execution_nonce": execution_nonce,
                "profile": LAB_IDENTITY,
            }
        )
        _write_file(ownership_path, ownership_payload, 0o400)
        journal_event(
            self.journal_path,
            "preflight_complete",
            {
                "tool_identities": preflight["tool_identities"],
                "ports": list(_TRACK_PORTS.values()),
                "dedicated_profile_absent": True,
            },
        )
        start_command = self.colima_start_command(execution_nonce)
        journal_event(
            self.journal_path,
            "colima_start_intent",
            {
                "profile": LAB_IDENTITY,
                "command_sha256": _digest_bytes(_canonical_bytes(start_command)),
            },
        )
        self._execute(start_command, timeout_s=900)
        journal_event(
            self.journal_path,
            "colima_start_returned",
            {"profile": LAB_IDENTITY, "command_returned_success": True},
        )
        journal_event(
            self.journal_path,
            "colima_attestation_intent",
            {"profile": LAB_IDENTITY},
        )
        try:
            colima_attestation = self._attest_colima_after_start(execution_nonce)
        except Exception as error:
            journal_event(
                self.journal_path,
                "colima_attestation_failed",
                {"reason": f"{type(error).__name__}: {error}"[:1000]},
            )
            raise
        journal_event(
            self.journal_path,
            "colima_attestation_complete",
            {"profile": LAB_IDENTITY, "attestation": colima_attestation},
        )
        engine = self._capture_engine_provenance()
        journal_event(self.journal_path, "engine_provenance_observed", engine)
        journal_event(
            self.journal_path,
            "image_resolution_intent",
            {"tag": PYTHON_IMAGE_TAG},
        )
        python_digest, python_image_id = self._resolve_image(PYTHON_IMAGE_TAG)
        journal_event(
            self.journal_path,
            "image_resolution_complete",
            {"tag": PYTHON_IMAGE_TAG, "digest": python_digest, "image_id": python_image_id},
        )
        journal_event(
            self.journal_path,
            "image_resolution_intent",
            {"tag": self.profile.envoy_image},
        )
        envoy_digest, envoy_image_id = self._resolve_image(self.profile.envoy_image)
        journal_event(
            self.journal_path,
            "image_resolution_complete",
            {"tag": self.profile.envoy_image, "digest": envoy_digest, "image_id": envoy_image_id},
        )
        journal_event(
            self.journal_path,
            "image_build_intent",
            {"base_digest": python_digest, "platform": PLATFORM},
        )
        kil_image_id, archive_sha = self._build_kil_image(
            python_digest, build_key=execution_nonce
        )
        journal_event(
            self.journal_path,
            "image_build_complete",
            {
                "image_id": kil_image_id,
                "archive_sha256": archive_sha,
                "build_context": self._build_context_attestation,
            },
        )
        if self._clean_source_identity() != source_commit:
            raise ControllerError("source commit changed while staging build inputs")
        staged_hashes = self._build_context_attestation.get("file_sha256")
        if type(staged_hashes) is not dict:
            raise ControllerError("staged build input hashes are unavailable")
        dockerfile_hash = staged_hashes.get("deploy/kind/Dockerfile.v3b")
        dockerignore_hash = staged_hashes.get(
            "deploy/kind/Dockerfile.v3b.dockerignore"
        )
        _require_sha256("staged Dockerfile", dockerfile_hash)
        _require_sha256("staged Docker ignore", dockerignore_hash)
        manifest = create_run_manifest(
            self.profile,
            profile_sha256=_digest_bytes(self.profile_path.read_bytes()),
            python_image_digest=python_digest,
            envoy_image_digest=envoy_digest,
            envoy_image_id=envoy_image_id,
            kil_image_id=kil_image_id,
            kil_archive_sha256=archive_sha,
            driver_bootstrap_sha256=driver_bootstrap_sha256(
                self._build_context_attestation
            ),
            docker_host=self.docker_host,
            source_commit=source_commit,
            source_clean=True,
            execution_nonce=execution_nonce,
            dockerfile_sha256=dockerfile_hash,
            dockerignore_sha256=dockerignore_hash,
            build_context_sha256=str(self._build_context_attestation["context_sha256"]),
        )
        output = self._private_provisional_root() / str(manifest["run_id"])
        public_output = self.evidence_root / str(manifest["run_id"])
        if output.exists() or public_output.exists():
            raise ControllerError("content-addressed run output would clobber existing evidence")
        output.mkdir(parents=True)
        private_manifest_path = (
            self._private_manifest_root() / f"{manifest['run_id']}.json"
        )
        if private_manifest_path.exists():
            raise ControllerError("private content-addressed manifest would clobber existing state")
        _write_file(private_manifest_path, _canonical_bytes(manifest), 0o400)
        _write_file(output / "manifest.json", _canonical_bytes(manifest), 0o444)
        _bind_journal_manifest(self.journal_path, private_manifest_path, manifest)
        materialize_run_inputs(self.root, manifest)
        created_ids: dict[str, str] = {}
        validator_objects: list[dict[str, object]] = []
        for command in build_runtime_commands(
            self.root, manifest, docker_binary=self.docker_binary
        ):
            if "kil.v3b1.role=validator" in command:
                name = command[command.index("--name") + 1]
                track = next(
                    (
                        candidate
                        for candidate in _TRACKS
                        if name
                        == (
                            f"kil-v3b1-validate-{_track_slug(candidate)}-"
                            f"{str(manifest['content_identity_sha256'])[:12]}"
                        )
                    ),
                    None,
                )
                if track is None:
                    raise ControllerError("validator command track is invalid")
                validator_objects.append(
                    self._run_validator_command(command, manifest, track)
                )
                continue
            if "network" in command and "create" in command:
                event = "network_create"
                name = command[-1]
                details: dict[str, object] = {"name": name}
            elif "run" in command and "-d" in command:
                event = "container_create"
                name = command[command.index("--name") + 1]
                details = {"name": name}
            elif "create" in command and "kil.v3b1.role=driver" in command:
                event = "container_create"
                name = command[command.index("--name") + 1]
                details = {"name": name}
            else:
                raise ControllerError("runtime creation command is unclassified")
            journal_event(self.journal_path, f"{event}_intent", details)
            result = self._execute(command, timeout_s=300, docker=True)
            completed_details = dict(details)
            if event in {"network_create", "container_create"}:
                object_id = result.stdout.strip()
                if _HEX.fullmatch(object_id) is None:
                    raise ControllerError(f"{event} did not return an exact object ID")
                completed_details["id"] = object_id
                created_ids[str(details["name"])] = object_id
            journal_event(
                self.journal_path, f"{event}_complete", completed_details
            )
        for track in _TRACKS:
            track_value = _track_manifest(manifest, track)
            envoy_name = str(track_value["envoy_container"])
            network_name = str(track_value["frontend_network"])
            try:
                connect_details = {
                    "container_id": created_ids[envoy_name],
                    "container_name": envoy_name,
                    "network_id": created_ids[network_name],
                    "network_name": network_name,
                    "alias": "envoy",
                }
            except KeyError as error:
                raise ControllerError(
                    "network connect lacks an exact created identity"
                ) from error
            journal_event(
                self.journal_path,
                "network_connect_intent",
                connect_details,
            )
            self._execute(
                _network_connect_command(self.docker_command(), connect_details),
                timeout_s=60,
                docker=True,
            )
            journal_event(
                self.journal_path,
                "network_connect_complete",
                connect_details,
            )
        objects, networks = self._attest_runtime(manifest)
        attested_ids = {
            str(item["name"]): str(item["id"]) for item in [*objects, *networks]
        }
        if created_ids != attested_ids:
            raise ControllerError("created Docker object IDs diverge from later attestation")
        self._assert_only_recorded_managed(
            {
                "objects": objects,
                "transient_objects": validator_objects,
                "network_objects": networks,
            },
            expect_present=True,
        )
        persist_active_state(
            self.state_path,
            private_manifest_path,
            manifest,
            objects=objects,
            network_objects=networks,
            profile_created=True,
        )
        journal_event(
            self.journal_path,
            "up_complete",
            {
                "state_path": str(self.state_path),
                "state_sha256": _digest_file(self.state_path),
            },
        )
        return manifest

    def _load_and_reverify(self) -> tuple[dict[str, object], dict[str, object]]:
        state = load_bound_active_state(self.state_path)
        manifest = state["manifest"]
        assert isinstance(manifest, dict)
        for record in state["objects"]:  # type: ignore[union-attr]
            current = self._inspect_container(
                str(record["id"]),
                manifest,
                str(record["role"]),
                str(record["track"]),
                require_running=record["role"] != "driver",
            )
            if current != record:
                raise ControllerError("recorded container attestation changed")
        for record in state["network_objects"]:  # type: ignore[union-attr]
            current = self._inspect_network(
                str(record["id"]),
                manifest,
                str(record["track"]),
                segment=str(record.get("segment", "backend")),
            )
            if current != record:
                raise ControllerError("recorded network attestation changed")
        return state, manifest

    def _request_records(self, manifest: Mapping[str, object]) -> list[dict[str, object]]:
        path = _runtime_root(self.root, manifest) / "requests.jsonl"
        if path.is_symlink() or not path.is_file():
            raise ControllerError("recorded central requests are unavailable")
        records = _parse_jsonl_bytes(
            path.read_bytes(), "requests", _request_closed, allow_empty=False
        )
        validate_request_journal(
            records, load_lifecycle_journal(self.journal_path), require_all=True
        )
        return records

    @staticmethod
    def _freeze_epoch(manifest: Mapping[str, object]) -> tuple[str, str]:
        execution_nonce = manifest.get("execution_nonce")
        _require_sha256("freeze execution_nonce", execution_nonce)
        epoch = _digest_bytes(
            canonical_json(
                {
                    "execution_nonce": execution_nonce,
                    "purpose": "v3b1-evidence-freeze-v1",
                    "run_id": manifest["run_id"],
                }
            ).encode("utf-8")
        )
        return execution_nonce, epoch  # type: ignore[return-value]

    def _freeze_raw_paths(
        self, manifest: Mapping[str, object], collection_epoch: str
    ) -> dict[tuple[str, str], Path]:
        _require_sha256("collection_epoch", collection_epoch)
        freeze_parent = self._private_source_freeze_root()
        run_root = freeze_parent / str(manifest["run_id"])
        epoch_root = run_root / collection_epoch
        for path, label in (
            (run_root, "source freeze run root"),
            (epoch_root, "source freeze epoch root"),
        ):
            _require_contained(path, freeze_parent, label)
            if path.is_symlink():
                raise ControllerError(f"{label} cannot be a symbolic link")
            path.mkdir(parents=False, exist_ok=True)
            if not path.is_dir() or path.is_symlink():
                raise ControllerError(f"{label} is unsafe")
            os.chmod(path, 0o700)
        paths: dict[tuple[str, str], Path] = {}
        for track in _TRACKS:
            track_root = epoch_root / track.value
            _require_contained(track_root, epoch_root, "source freeze track root")
            if track_root.is_symlink():
                raise ControllerError("source freeze track root cannot be a symbolic link")
            track_root.mkdir(parents=False, exist_ok=True)
            os.chmod(track_root, 0o700)
            paths[(track.value, "envoy_access")] = track_root / _ENVOY_LOG_NAME
            paths[(track.value, "authz_decisions")] = track_root / "decisions.jsonl"
            paths[(track.value, "target_markers")] = track_root / "targets.jsonl"
        return paths

    @staticmethod
    def _parse_probe_observation(payload: str) -> tuple[bool, int | None, str | None]:
        encoded = payload.encode("utf-8")
        observation = _load_json_bytes(encoded, "ledger probe")
        if encoded != _canonical_bytes(observation) or set(observation) != {
            "exists",
            "regular_file",
            "byte_count",
            "sha256",
        }:
            raise ControllerError("ledger probe result is not closed canonical JSON")
        exists = observation["exists"]
        regular = observation["regular_file"]
        count = observation["byte_count"]
        digest = observation["sha256"]
        if type(exists) is not bool or type(regular) is not bool:
            raise ControllerError("ledger probe booleans are invalid")
        if not exists:
            if regular or count is not None or digest is not None:
                raise ControllerError("missing ledger probe shape is invalid")
            return False, None, None
        if not regular:
            if count is not None or digest is not None:
                raise ControllerError("non-regular ledger probe shape is invalid")
            raise ControllerError("ledger source is not a regular file")
        if type(count) is not int or count < 0:
            raise ControllerError("ledger probe byte count is invalid")
        _require_sha256("ledger probe sha256", digest)
        return True, count, digest  # type: ignore[return-value]

    @staticmethod
    def _parse_ledger_export(payload: str) -> tuple[bytes, int, str]:
        try:
            encoded = payload.encode("utf-8")
        except UnicodeError as error:
            raise ControllerError("ledger export contains invalid Unicode") from error
        if len(encoded) > _MAX_LEDGER_EXPORT_OUTPUT_BYTES:
            raise ControllerError("ledger export exceeds the closed output bound")
        export = _load_json_bytes(encoded, "ledger export")
        try:
            canonical_export = _canonical_bytes(export)
        except (TypeError, ValueError, UnicodeError, RecursionError) as error:
            raise ControllerError("ledger export canonicalization failed") from error
        if encoded != canonical_export or set(export) != {
            "byte_count",
            "payload_hex",
            "sha256",
        }:
            raise ControllerError("ledger export is not closed canonical JSON")
        byte_count = export["byte_count"]
        payload_hex = export["payload_hex"]
        digest = export["sha256"]
        if (
            type(byte_count) is not int
            or not 0 <= byte_count <= _MAX_LEDGER_EXPORT_BYTES
            or type(payload_hex) is not str
            or len(payload_hex) != byte_count * 2
            or re.fullmatch(r"[0-9a-f]*", payload_hex) is None
        ):
            raise ControllerError("ledger export byte payload is invalid")
        _require_sha256("ledger export sha256", digest)
        try:
            exported = bytes.fromhex(payload_hex)
        except ValueError as error:
            raise ControllerError("ledger export byte payload is invalid") from error
        if len(exported) != byte_count or _digest_bytes(exported) != digest:
            raise ControllerError("ledger export self-attestation is invalid")
        return exported, byte_count, digest  # type: ignore[return-value]

    @staticmethod
    def _source_malformed_class(
        payload: bytes,
        *,
        track: LiveTrack,
        source: str,
        attempted_complete: bool,
    ) -> str | None:
        validator = {
            "authz_decisions": _decision_closed,
            "target_markers": _target_closed,
            "envoy_access": _envoy_closed,
        }[source]
        try:
            records = _parse_jsonl_bytes(
                payload,
                f"frozen {source} {track.value}",
                validator,
                allow_empty=True,
            )
        except ControllerError:
            return "invalid_json"
        if any(record["track"] != track.value for record in records):
            return "invalid_cardinality"
        if attempted_complete:
            expected = (
                0
                if source == "target_markers"
                and track is LiveTrack.SIGNED_PLUS_LOCAL_REDUCE
                else 1
            )
            if len(records) != expected:
                return "invalid_cardinality"
        elif len(records) > 1:
            return "invalid_cardinality"
        return None

    def _read_attested_frozen_bytes(
        self,
        path: Path,
        *,
        byte_count: object,
        sha256_digest: object,
    ) -> bytes:
        if type(byte_count) is not int or byte_count < 0:
            raise ControllerError("frozen source byte count is invalid")
        _require_sha256("frozen source sha256", sha256_digest)
        _require_contained(
            path, self._private_source_freeze_root(), "frozen source path"
        )
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise ControllerError("frozen source bytes are missing or unsafe") from error
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise ControllerError("frozen source path is not a regular file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            finished = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        try:
            current = os.stat(path, follow_symlinks=False)
        except OSError as error:
            raise ControllerError("frozen source path changed during attestation") from error
        if (
            not stat.S_ISREG(current.st_mode)
            or (opened.st_dev, opened.st_ino) != (finished.st_dev, finished.st_ino)
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            or opened.st_size != finished.st_size
        ):
            raise ControllerError("frozen source path changed during attestation")
        payload = b"".join(chunks)
        if len(payload) != byte_count or _digest_bytes(payload) != sha256_digest:
            raise ControllerError("frozen source bytes changed after collection")
        return payload

    def _attest_frozen_status_bytes(
        self, status: SourceCollectionStatus, path: Path
    ) -> bytes | None:
        if status.copied_byte_count is None:
            if path.is_symlink() or path.exists():
                raise ControllerError("uncopied source has unexpected frozen bytes")
            return None
        payload = self._read_attested_frozen_bytes(
            path,
            byte_count=status.copied_byte_count,
            sha256_digest=status.copied_sha256,
        )
        return payload if status.status in {"copied", "malformed"} else None

    def _reattest_frozen_status(
        self, status: SourceCollectionStatus, path: Path
    ) -> None:
        self._attest_frozen_status_bytes(status, path)

    def _quarantine_unattested_frozen_path(self, path: Path) -> Path:
        _require_contained(
            path.parent,
            self._private_source_freeze_root(),
            "unattested frozen source parent",
        )
        if not path.is_symlink() and not path.exists():
            raise ControllerError("unattested frozen source path is absent")
        name_digest = _digest_bytes(path.name.encode("utf-8"))
        for counter in range(1_000_000):
            quarantine = path.with_name(
                f".{path.name}.unattested.{name_digest}.{counter:06d}"
            )
            try:
                reservation = os.open(
                    quarantine,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o400,
                )
            except FileExistsError:
                continue
            except OSError as error:
                raise ControllerError(
                    "unattested frozen source quarantine reservation failed"
                ) from error
            else:
                os.close(reservation)
            try:
                os.replace(path, quarantine)
            except OSError as error:
                raise ControllerError(
                    "unattested frozen source quarantine move failed"
                ) from error
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            if path.is_symlink() or path.exists():
                raise ControllerError(
                    "unattested frozen source remained active after quarantine"
                )
            return quarantine
        raise ControllerError("unattested frozen source quarantine namespace exhausted")

    def _collect_freeze_leg(
        self,
        *,
        manifest: dict[str, object],
        item: Mapping[str, object],
        track: LiveTrack,
        source: str,
        path: Path,
        collection_epoch: str,
        attempted_complete: bool,
    ) -> SourceCollectionStatus:
        identity = {
            "track": track.value,
            "source": source,
            "container_id": item["id"],
            "container_name": item["name"],
        }
        if path.is_symlink() or path.exists():
            raise ControllerError("unfinished source path requires recovery handling")
        try:
            current = self._inspect_container(
                str(item["id"]),
                manifest,
                str(item["role"]),
                track.value,
                require_running=source != "envoy_access",
            )
            if not _container_attestation_matches(
                item,
                current,
                allow_stopped=source == "envoy_access",
            ):
                raise ControllerError("source container identity changed before freeze")
        except (ControllerError, OSError, UnicodeError):
            return SourceCollectionStatus(
                **identity,
                status="copy_error",
                source_byte_count=None,
                source_sha256=None,
                copied_byte_count=None,
                copied_sha256=None,
                error_class="command_failed",
            )
        if source == "envoy_access":
            try:
                logs = self._execute(
                    self.docker_command("logs", str(item["id"])),
                    timeout_s=60,
                    docker=True,
                )
                source_bytes = logs.stdout.encode("utf-8")
                source_count = len(source_bytes)
                source_sha = _digest_bytes(source_bytes)
                _write_file(path, source_bytes, 0o400)
                copied_bytes = path.read_bytes()
            except (ControllerError, OSError, UnicodeError):
                if path.is_symlink() or path.exists():
                    self._quarantine_unattested_frozen_path(path)
                return SourceCollectionStatus(
                    **identity,
                    status="copy_error",
                    source_byte_count=None,
                    source_sha256=None,
                    copied_byte_count=None,
                    copied_sha256=None,
                    error_class="command_failed",
                )
        else:
            source_path = _LEDGER_PATH[source]
            try:
                probe = self._execute(
                    self.docker_command(
                        "exec",
                        str(item["id"]),
                        "/usr/local/bin/python",
                        "-c",
                        _LEDGER_PROBE,
                        source_path,
                    ),
                    timeout_s=60,
                    docker=True,
                )
                present, source_count, source_sha = self._parse_probe_observation(
                    probe.stdout
                )
            except (ControllerError, OSError, UnicodeError):
                return SourceCollectionStatus(
                    **identity,
                    status="copy_error",
                    source_byte_count=None,
                    source_sha256=None,
                    copied_byte_count=None,
                    copied_sha256=None,
                    error_class="command_failed",
                )
            if not present:
                return SourceCollectionStatus(
                    **identity,
                    status="missing",
                    source_byte_count=None,
                    source_sha256=None,
                    copied_byte_count=None,
                    copied_sha256=None,
                    error_class="source_missing",
                )
            assert source_count is not None and source_sha is not None
            if source_count > _MAX_LEDGER_EXPORT_BYTES:
                return SourceCollectionStatus(
                    **identity,
                    status="copy_error",
                    source_byte_count=source_count,
                    source_sha256=source_sha,
                    copied_byte_count=None,
                    copied_sha256=None,
                    error_class="command_failed",
                )
            try:
                self._execute(
                    self.docker_command(
                        "cp", f"{item['id']}:{source_path}", str(path)
                    ),
                    timeout_s=60,
                    docker=True,
                )
                if path.is_symlink() or not path.is_file():
                    raise ControllerError("Docker copy did not produce a regular file")
                copied_bytes = path.read_bytes()
                _write_file(path, copied_bytes, 0o400)
                copied_bytes = path.read_bytes()
            except (ControllerError, OSError, UnicodeError):
                if path.is_symlink() or path.exists():
                    self._quarantine_unattested_frozen_path(path)
                try:
                    export = self._execute(
                        self.docker_command(
                            "exec",
                            str(item["id"]),
                            "/usr/local/bin/python",
                            "-c",
                            _LEDGER_EXPORT,
                            source_path,
                            str(_MAX_LEDGER_EXPORT_BYTES),
                        ),
                        timeout_s=60,
                        docker=True,
                    )
                    exported_bytes, exported_count, exported_sha = (
                        self._parse_ledger_export(export.stdout)
                    )
                    if (
                        exported_count != source_count
                        or exported_sha != source_sha
                    ):
                        raise ControllerError(
                            "ledger export changed after source observation"
                        )
                    _write_file(path, exported_bytes, 0o400)
                    copied_bytes = self._read_attested_frozen_bytes(
                        path,
                        byte_count=exported_count,
                        sha256_digest=exported_sha,
                    )
                except (ControllerError, OSError, UnicodeError):
                    if path.is_symlink() or path.exists():
                        self._quarantine_unattested_frozen_path(path)
                    return SourceCollectionStatus(
                        **identity,
                        status="copy_error",
                        source_byte_count=source_count,
                        source_sha256=source_sha,
                        copied_byte_count=None,
                        copied_sha256=None,
                        error_class="command_failed",
                    )
        copied_count = len(copied_bytes)
        copied_sha = _digest_bytes(copied_bytes)
        if copied_count != source_count:
            return SourceCollectionStatus(
                **identity,
                status="copy_error",
                source_byte_count=source_count,
                source_sha256=source_sha,
                copied_byte_count=copied_count,
                copied_sha256=copied_sha,
                error_class="size_mismatch",
            )
        if copied_sha != source_sha:
            return SourceCollectionStatus(
                **identity,
                status="copy_error",
                source_byte_count=source_count,
                source_sha256=source_sha,
                copied_byte_count=copied_count,
                copied_sha256=copied_sha,
                error_class="digest_mismatch",
            )
        journal_event(
            self.journal_path,
            "evidence_freeze_leg_bytes_persisted",
            {
                "collection_epoch": collection_epoch,
                "track": track.value,
                "source": source,
                "path_relative": _freeze_relative_path(track.value, source),
                "byte_count": copied_count,
                "sha256": copied_sha,
            },
        )
        malformed = self._source_malformed_class(
            copied_bytes,
            track=track,
            source=source,
            attempted_complete=attempted_complete,
        )
        return SourceCollectionStatus(
            **identity,
            status="malformed" if malformed is not None else "copied",
            source_byte_count=source_count,
            source_sha256=source_sha,
            copied_byte_count=copied_count,
            copied_sha256=copied_sha,
            error_class=malformed,
        )

    def _freeze_sources(
        self,
        state: Mapping[str, object],
        manifest: dict[str, object],
        *,
        attempted_complete: bool,
    ) -> EvidenceFreezeResult:
        if type(attempted_complete) is not bool:
            raise ControllerError("freeze request completion state is invalid")
        execution_nonce, collection_epoch = self._freeze_epoch(manifest)
        paths = self._freeze_raw_paths(manifest, collection_epoch)
        journal = load_lifecycle_journal(self.journal_path)
        requests_state = journal["requests"]
        assert isinstance(requests_state, dict)
        if attempted_complete is not all(
            request["status"] == "completed" for request in requests_state.values()
        ):
            raise ControllerError("freeze request state does not bind the lifecycle")
        events = journal["events"]
        assert isinstance(events, list)
        started = next(
            (event for event in events if event["event"] == "evidence_freeze_started"),
            None,
        )
        start_details = {
            "collection_epoch": collection_epoch,
            "execution_nonce": execution_nonce,
            "run_id": manifest["run_id"],
        }
        if started is None:
            journal_event(self.journal_path, "evidence_freeze_started", start_details)
        elif started["details"] != start_details:
            raise ControllerError("persisted evidence freeze epoch binding changed")
        journal = load_lifecycle_journal(self.journal_path)
        events = journal["events"]
        assert isinstance(events, list)
        terminals = {
            (record.track, record.source): record
            for record in (
                SourceCollectionStatus.from_mapping(event["details"]["record"])
                for event in events
                if event["event"] == "source_collection_terminal"
            )
        }
        completed_event = next(
            (event for event in events if event["event"] == "evidence_freeze_complete"),
            None,
        )
        if completed_event is not None:
            ordered = tuple(
                terminals[(track.value, source)]
                for track in _TRACKS
                for source in _FREEZE_SOURCES
            )
            for status in ordered:
                self._reattest_frozen_status(
                    status, paths[(status.track, status.source)]
                )
            promotable = attempted_complete and all(
                status.status == "copied" for status in ordered
            )
            if completed_event["details"]["promotable"] is not promotable:
                raise ControllerError("freeze recovery promotability changed")
            return EvidenceFreezeResult(
                collection_epoch, ordered, paths, promotable
            )
        source_state = (
            load_bound_active_state(self.state_path)
            if self.state_path.exists()
            else state
        )
        if source_state.get("manifest") not in (None, manifest):
            raise ControllerError("freeze source state diverges from the manifest")
        by_role_track = {
            (str(item["role"]), str(item["track"])): item
            for item in source_state["objects"]  # type: ignore[union-attr]
        }
        try:
            expected = [
                (track, source, by_role_track[(_SOURCE_ROLE[source], track.value)])
                for track in _TRACKS
                for source in _FREEZE_SOURCES
            ]
        except KeyError as error:
            raise ControllerError(
                "unfinished evidence freeze lost an exact source container"
            ) from error
        intended = {
            (event["details"]["track"], event["details"]["source"])
            for event in events
            if event["event"] == "source_collection_intent"
        }
        for track, source, item in expected:
            key = (track.value, source)
            if key not in intended:
                journal_event(
                    self.journal_path,
                    "source_collection_intent",
                    {
                        "collection_epoch": collection_epoch,
                        "track": track.value,
                        "source": source,
                        "container_id": item["id"],
                        "container_name": item["name"],
                    },
                )
        journal = load_lifecycle_journal(self.journal_path)
        events = journal["events"]
        assert isinstance(events, list)
        terminals = {
            (record.track, record.source): record
            for record in (
                SourceCollectionStatus.from_mapping(event["details"]["record"])
                for event in events
                if event["event"] == "source_collection_terminal"
            )
        }
        persisted_bytes = {
            (str(event["details"]["track"]), str(event["details"]["source"])):
            event["details"]
            for event in events
            if event["event"] == "evidence_freeze_leg_bytes_persisted"
        }
        execution_order = [
            *[(track, "envoy_access", by_role_track[("envoy", track.value)]) for track in _TRACKS],
            *[
                (track, source, by_role_track[(_SOURCE_ROLE[source], track.value)])
                for track in _TRACKS
                for source in ("authz_decisions", "target_markers")
            ],
        ]
        for track, source, item in execution_order:
            key = (track.value, source)
            if key in terminals:
                self._reattest_frozen_status(terminals[key], paths[key])
                continue
            if key in persisted_bytes:
                persisted = persisted_bytes[key]
                copied_bytes = self._read_attested_frozen_bytes(
                    paths[key],
                    byte_count=persisted["byte_count"],
                    sha256_digest=persisted["sha256"],
                )
                malformed = self._source_malformed_class(
                    copied_bytes,
                    track=track,
                    source=source,
                    attempted_complete=attempted_complete,
                )
                status = SourceCollectionStatus(
                    track=track.value,
                    source=source,
                    container_id=str(item["id"]),
                    container_name=str(item["name"]),
                    status="malformed" if malformed is not None else "copied",
                    source_byte_count=len(copied_bytes),
                    source_sha256=_digest_bytes(copied_bytes),
                    copied_byte_count=len(copied_bytes),
                    copied_sha256=_digest_bytes(copied_bytes),
                    error_class=malformed,
                )
                journal_event(
                    self.journal_path,
                    "source_collection_terminal",
                    {
                        "collection_epoch": collection_epoch,
                        "record": status.to_mapping(),
                    },
                )
                terminals[key] = status
                continue
            if paths[key].is_symlink() or paths[key].exists():
                self._quarantine_unattested_frozen_path(paths[key])
            status = self._collect_freeze_leg(
                manifest=manifest,
                item=item,
                track=track,
                source=source,
                path=paths[key],
                collection_epoch=collection_epoch,
                attempted_complete=attempted_complete,
            )
            journal_event(
                self.journal_path,
                "source_collection_terminal",
                {
                    "collection_epoch": collection_epoch,
                    "record": status.to_mapping(),
                },
            )
            terminals[key] = status
        ordered = tuple(
            terminals[(track.value, source)]
            for track in _TRACKS
            for source in _FREEZE_SOURCES
        )
        promotable = attempted_complete and all(
            status.status == "copied" for status in ordered
        )
        journal_event(
            self.journal_path,
            "evidence_freeze_complete",
            {
                "collection_epoch": collection_epoch,
                "terminal_count": len(ordered),
                "records_sha256": _digest_bytes(
                    canonical_json(
                        [status.to_mapping() for status in ordered]
                    ).encode("utf-8")
                ),
                "promotable": promotable,
            },
        )
        return EvidenceFreezeResult(collection_epoch, ordered, paths, promotable)

    def _stop_and_attest_container(
        self,
        item: Mapping[str, object],
        manifest: dict[str, object],
    ) -> None:
        if item["role"] == "validator":
            current = self._inspect_validation_container(
                str(item["id"]), manifest, LiveTrack(str(item["track"]))
            )
        else:
            current = self._inspect_container(
                str(item["id"]),
                manifest,
                str(item["role"]),
                str(item["track"]),
                require_running=False,
            )
        if item["role"] == "validator":
            current_matches = current == item
        else:
            current_matches = _container_attestation_matches(
                item, current, allow_stopped=True
            )
        if not current_matches:
            raise ControllerError("container changed before exact stop")
        running = self._execute(
            self.docker_command(
                "inspect", "--format", "{{.State.Running}}", str(item["id"])
            ),
            timeout_s=30,
            docker=True,
        ).stdout.strip()
        if running not in {"true", "false"}:
            raise ControllerError("container running state is invalid")
        if running == "true":
            journal_event(
                self.journal_path,
                "container_stop_intent",
                {
                    "id": item["id"],
                    "name": item["name"],
                    "role": item["role"],
                },
            )
            self._execute(
                self.docker_command("stop", "--timeout", "10", str(item["id"])),
                timeout_s=30,
                docker=True,
            )
            stopped = self._execute(
                self.docker_command(
                    "inspect",
                    "--format",
                    "{{.State.Running}}",
                    str(item["id"]),
                ),
                timeout_s=30,
                docker=True,
            ).stdout.strip()
            if stopped != "false":
                raise ControllerError("recorded container did not stop")
            if item["role"] == "validator":
                after = self._inspect_validation_container(
                    str(item["id"]), manifest, LiveTrack(str(item["track"]))
                )
            else:
                after = self._inspect_container(
                    str(item["id"]),
                    manifest,
                    str(item["role"]),
                    str(item["track"]),
                    require_running=False,
                )
            if item["role"] == "validator":
                after_matches = after == item
            else:
                after_matches = _container_attestation_matches(
                    item, after, allow_stopped=True
                )
            if not after_matches:
                raise ControllerError("container changed after exact stop")
            journal_event(
                self.journal_path,
                "container_stop_complete",
                {"id": item["id"], "name": item["name"]},
            )

    def _freeze_before_service_teardown(
        self,
        state: Mapping[str, object],
        manifest: dict[str, object],
        *,
        attempted_complete: bool,
        transient_objects: Sequence[Mapping[str, object]],
    ) -> EvidenceFreezeResult:
        objects = state["objects"]
        if type(objects) is not list:
            raise ControllerError("runtime object state is invalid")
        for item in objects:
            if item["role"] == "envoy":
                self._stop_and_attest_container(item, manifest)
        freeze = self._freeze_sources(
            state, manifest, attempted_complete=attempted_complete
        )
        for role in ("authz", "target"):
            for item in objects:
                if item["role"] == role:
                    self._stop_and_attest_container(item, manifest)
        for item in transient_objects:
            self._stop_and_attest_container(item, manifest)
        return freeze

    def _copy_sources(
        self,
        state: Mapping[str, object],
        manifest: dict[str, object],
        name: str,
        *,
        allow_incomplete: bool = False,
    ) -> tuple[
        dict[LiveTrack, bytes],
        list[dict[str, object]],
        list[dict[str, object]],
    ]:
        root = _runtime_root(self.root, manifest) / name
        raw_decisions = {}
        envoy_records = []
        target_records = []
        object_by_role_track = {
            (item["role"], item["track"]): item
            for item in state["objects"]  # type: ignore[union-attr]
        }
        for track in _TRACKS:
            destination = root / track.value
            destination.mkdir(parents=True, exist_ok=True)
            decision_path = destination / "decisions.jsonl"
            target_path = destination / "targets.jsonl"
            envoy_path = destination / "envoy.stdout.jsonl"
            for path in (decision_path, target_path, envoy_path):
                if path.exists():
                    path.unlink()
            authz = object_by_role_track[("authz", track.value)]
            target = object_by_role_track[("target", track.value)]
            proxy = object_by_role_track[("envoy", track.value)]
            self._execute(
                self.docker_command(
                    "cp",
                    f"{authz['id']}:/evidence/decisions.jsonl",
                    str(decision_path),
                ),
                timeout_s=60,
                docker=True,
            )
            self._execute(
                self.docker_command(
                    "cp",
                    f"{target['id']}:/evidence/targets.jsonl",
                    str(target_path),
                ),
                timeout_s=60,
                docker=True,
            )
            logs = self._execute(
                self.docker_command("logs", str(proxy["id"])),
                timeout_s=60,
                docker=True,
            )
            _write_file(envoy_path, logs.stdout.encode("utf-8"), 0o444)
            raw_decisions[track] = decision_path.read_bytes()
            decisions = _parse_jsonl_bytes(
                raw_decisions[track],
                f"decisions {track.value}",
                _decision_closed,
                allow_empty=allow_incomplete,
            )
            if len(decisions) > 1 or (
                not allow_incomplete and len(decisions) != 1
            ) or any(item["track"] != track.value for item in decisions):
                raise ControllerError("authz source cardinality/track is invalid")
            targets = _parse_jsonl_bytes(
                target_path.read_bytes(),
                f"targets {track.value}",
                _target_closed,
                allow_empty=True,
            )
            if any(item["track"] != track.value for item in targets):
                raise ControllerError("target source track is invalid")
            if len(targets) > 1:
                raise ControllerError("target source cardinality is invalid")
            proxies = _parse_jsonl_bytes(
                envoy_path.read_bytes(),
                f"Envoy {track.value}",
                _envoy_closed,
                allow_empty=allow_incomplete,
            )
            if len(proxies) > 1 or (
                not allow_incomplete and len(proxies) != 1
            ) or any(item["track"] != track.value for item in proxies):
                raise ControllerError("Envoy source cardinality/track is invalid")
            envoy_records.extend(proxies)
            target_records.extend(targets)
        return raw_decisions, envoy_records, target_records

    def collect(self) -> Path:
        provisional_root = self._private_provisional_root()
        journal_event(
            self.journal_path,
            "evidence_collect_intent",
            {"mode": "independent_runtime_reverification"},
        )
        state, manifest = self._load_and_reverify()
        requests = self._request_records(manifest)
        raw, envoy, targets = self._copy_sources(
            state, manifest, f"collect-{time.monotonic_ns()}"
        )
        decisions = []
        for track in _TRACKS:
            decisions.extend(
                _parse_jsonl_bytes(
                    raw[track],
                    f"decisions {track.value}",
                    _decision_closed,
                    allow_empty=False,
                )
            )
        joins = join_evidence(manifest, requests, decisions, envoy, targets)
        output = write_evidence_bundle(
            provisional_root,
            manifest,
            requests=requests,
            decisions=decisions,
            envoy=envoy,
            targets=targets,
            joins=joins,
            raw_decisions=raw,
            resume_attested=True,
        )
        authoritative = authoritative_bundle_attestation(output)
        journal_event(
            self.journal_path,
            "evidence_collect_complete",
            {
                "completed": True,
                "provisional_sha256s": {
                    name: _digest_file(output / name)
                    for name in _EVIDENCE_FILES
                },
                "authoritative_attestation": authoritative,
            },
        )
        return output

    def _monotonic_now(self) -> int:
        value = self.monotonic_ns()
        if type(value) is not int or value < 0:
            raise ControllerError("monotonic clock returned an invalid value")
        return value

    @staticmethod
    def _close_connections(
        connections: Mapping[LiveTrack, object],
    ) -> list[dict[str, str]]:
        failures: list[dict[str, str]] = []
        for track, connection in connections.items():
            try:
                connection.close()  # type: ignore[attr-defined]
            except Exception:
                failures.append({"track": track.value, "category": "close_raised"})
                continue
            try:
                if hasattr(connection, "closed"):
                    confirmed = connection.closed is True  # type: ignore[attr-defined]
                elif hasattr(connection, "sock"):
                    confirmed = connection.sock is None  # type: ignore[attr-defined]
                else:
                    confirmed = False
            except Exception:
                confirmed = False
            if not confirmed:
                failures.append(
                    {"track": track.value, "category": "close_unconfirmed"}
                )
        return failures

    def _record_close_failures(
        self,
        *,
        readiness_nonce: str,
        stage: str,
        primary_failure: str | None,
        failures: list[dict[str, str]],
    ) -> None:
        try:
            journal_event(
                self.journal_path,
                "connection_close_failed",
                {
                    "readiness_nonce": readiness_nonce,
                    "stage": stage,
                    "primary_failure": primary_failure,
                    "failures": failures,
                },
            )
        except Exception as journal_error:
            try:
                self._persist_readiness_poison(
                    readiness_nonce=readiness_nonce,
                    reason_category="connection_close_ambiguous",
                )
            except Exception as poison_error:
                raise ControllerError(
                    "independent readiness poison persistence failed"
                ) from poison_error
            raise journal_error

    @staticmethod
    def _reset_request_timeouts(
        connections: Mapping[LiveTrack, object],
    ) -> None:
        reset_failed = False
        for connection in connections.values():
            try:
                socket_object = connection.sock  # type: ignore[attr-defined]
                settimeout = socket_object.settimeout
                if not callable(settimeout):
                    raise TypeError("socket settimeout is not callable")
                settimeout(REQUEST_TIMEOUT_S)
            except Exception:
                reset_failed = True
        if reset_failed:
            raise ControllerError(
                "retained gateway request timeout reset failed"
            ) from None

    def _readiness_failure_event(
        self,
        *,
        track: LiveTrack,
        port: int,
        round_number: int,
        connect_ns: int,
        failure_ns: int,
        error: BaseException,
        readiness_nonce: str,
    ) -> None:
        try:
            exception_class, error_number, error_name = normalize_transport_exception(
                error
            )
        except HarnessContractError as contract_error:
            raise ControllerError("readiness transport failure is not closed") from contract_error
        journal_event(
            self.journal_path,
            "readiness_connect_failed",
            {
                "readiness_nonce": readiness_nonce,
                "track": track.value,
                "host": "127.0.0.1",
                "port": port,
                "round": round_number,
                "connect_monotonic_ns": connect_ns,
                "failure_monotonic_ns": failure_ns,
                "exception_class": exception_class,
                "errno": error_number,
                "errno_name": error_name,
                "request_bytes_may_have_been_sent": False,
            },
        )

    def _connect_ready_gateways(
        self,
        readiness_nonce: str,
    ) -> tuple[dict[LiveTrack, object], dict[LiveTrack, int]]:
        self._assert_no_readiness_poison()
        _require_sha256("readiness_nonce", readiness_nonce)
        start_ns = self._monotonic_now()
        deadline_ns = start_ns + _READINESS_DEADLINE_NS
        round_number = 0
        while True:
            round_number += 1
            connections: dict[LiveTrack, object] = {}
            connect_times: dict[LiveTrack, int] = {}
            ownership_transferred = False
            close_primary_failure = "request_processing"
            sleep_s: float | None = None
            try:
                failure: tuple[
                    LiveTrack, int, int, int, BaseException
                ] | None = None
                for track, port in zip(
                    _TRACKS, _TRACK_PORTS.values(), strict=True
                ):
                    connect_ns = self._monotonic_now()
                    remaining_ns = deadline_ns - connect_ns
                    if remaining_ns <= 0:
                        failure = (
                            track,
                            port,
                            connect_ns,
                            connect_ns,
                            TimeoutError("gateway readiness deadline expired"),
                        )
                        break
                    timeout_s = min(
                        _READINESS_CONNECT_TIMEOUT_S,
                        remaining_ns / 1_000_000_000,
                    )
                    try:
                        connection = self.connection_factory(
                            "127.0.0.1", port, timeout=timeout_s
                        )
                        connections[track] = connection
                        connection.connect()  # type: ignore[attr-defined]
                    except (OSError, http.client.HTTPException) as error:
                        failure = (
                            track,
                            port,
                            connect_ns,
                            self._monotonic_now(),
                            error,
                        )
                        break
                    connected_ns = self._monotonic_now()
                    if connected_ns >= deadline_ns:
                        failure = (
                            track,
                            port,
                            connect_ns,
                            connected_ns,
                            TimeoutError("gateway readiness deadline expired"),
                        )
                        break
                    connect_times[track] = connected_ns
                if failure is None:
                    ready_ns = self._monotonic_now()
                    journal_event(
                        self.journal_path,
                        "readiness_connect_complete",
                        {
                            "readiness_nonce": readiness_nonce,
                            "round": round_number,
                            "host": "127.0.0.1",
                            "tracks": [track.value for track in _TRACKS],
                            "ports": list(_TRACK_PORTS.values()),
                            "ready_monotonic_ns": ready_ns,
                        },
                    )
                    ownership_transferred = True
                    return connections, connect_times

                close_primary_failure = "readiness_connect_failed"
                track, port, connect_ns, failure_ns, error = failure
                self._readiness_failure_event(
                    track=track,
                    port=port,
                    round_number=round_number,
                    connect_ns=connect_ns,
                    failure_ns=failure_ns,
                    error=error,
                    readiness_nonce=readiness_nonce,
                )
                if failure_ns >= deadline_ns:
                    raise ControllerError(
                        "gateway TCP readiness deadline expired"
                    ) from None
                sleep_s = min(
                    _READINESS_ROUND_DELAY_S,
                    (deadline_ns - failure_ns) / 1_000_000_000,
                )
                if sleep_s <= 0:
                    raise ControllerError("gateway TCP readiness deadline expired")
            finally:
                if not ownership_transferred:
                    active_error = sys.exc_info()[1]
                    close_failures = self._close_connections(connections)
                    if close_failures:
                        try:
                            self._record_close_failures(
                                readiness_nonce=readiness_nonce,
                                stage="readiness_round",
                                primary_failure=close_primary_failure,
                                failures=close_failures,
                            )
                        except Exception:
                            if active_error is None:
                                raise
                        if active_error is None:
                            raise ControllerError(
                                "gateway readiness failed and connection closure "
                                "is ambiguous"
                            ) from None
            assert sleep_s is not None
            self.sleeper(sleep_s)

    def _request_failure_provenance(
        self,
        *,
        stage: str,
        error: BaseException,
        connect_ns: int,
        send_ns: int,
    ) -> RequestFailureProvenance:
        try:
            exception_class, error_number, error_name = normalize_transport_exception(
                error
            )
            return RequestFailureProvenance(
                stage=stage,
                exception_class=exception_class,
                errno=error_number,
                errno_name=error_name,
                connect_monotonic_ns=connect_ns,
                send_monotonic_ns=send_ns,
                failure_monotonic_ns=self._monotonic_now(),
                request_bytes_may_have_been_sent=True,
                attempt_count=1,
                retry_performed=False,
            )
        except HarnessContractError as contract_error:
            raise ControllerError("request failure provenance is not closed") from contract_error

    def _record_transport_failure(
        self,
        *,
        track: LiveTrack,
        stage: str,
        error: BaseException,
        connect_ns: int,
        send_ns: int,
    ) -> None:
        provenance = self._request_failure_provenance(
            stage=stage,
            error=error,
            connect_ns=connect_ns,
            send_ns=send_ns,
        )
        _complete_request_attempt(
            self.journal_path,
            track,
            success=False,
            record_sha256=None,
            failure_provenance=provenance,
        )

    def run(self) -> Path:
        self._assert_no_readiness_poison()
        state, manifest = self._load_and_reverify()
        runtime_root = _runtime_root(self.root, manifest)
        request_path = runtime_root / "requests.jsonl"
        if request_path.exists():
            raise ControllerError("central request was already attempted")
        journal = load_lifecycle_journal(self.journal_path)
        if journal["manifest_sha256"] != _digest_file(Path(str(state["manifest_path"]))):
            raise ControllerError("request lifecycle journal does not bind active manifest")
        if any(
            request["status"] != "not_attempted"
            for request in journal["requests"].values()
        ):
            raise ControllerError("central request was already attempted; replay is forbidden")
        readiness_nonce = secrets.token_hex(32)
        journal_event(
            self.journal_path,
            "readiness_session_started",
            {"readiness_nonce": readiness_nonce},
        )
        connections, connect_times = self._connect_ready_gateways(readiness_nonce)
        primary_failure: str | None = None
        try:
            self._reset_request_timeouts(connections)
            private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
            records: list[dict[str, object]] = []
            comparison = {
                "method": "POST",
                "path": "/consequential/admin",
                "authorization_sha256": _digest_bytes(AUTHORIZATION.encode("utf-8")),
                "adversarial_headers": dict(ADVERSARIAL_HEADERS),
                "retry_control_headers": dict(RETRY_CONTROL_HEADERS),
            }
            comparison_sha = comparison_facts_sha256(comparison)
            for track, port in zip(_TRACKS, _TRACK_PORTS.values(), strict=True):
                issued = int(time.time())
                q_state = None
                if track is LiveTrack.SIGNED_STATE_ONLY:
                    q_state = issue_q_state(_claims("kil-v3-signed", issued), private_key)
                elif track is LiveTrack.SIGNED_PLUS_LOCAL_REDUCE:
                    q_state = issue_q_state(_claims("kil-v3-local", issued), private_key)
                headers = {
                    "authorization": AUTHORIZATION,
                    "x-request-id": str(manifest["request_id"]),
                    "x-kil-run-id": str(manifest["run_id"]),
                    **ADVERSARIAL_HEADERS,
                    **RETRY_CONTROL_HEADERS,
                }
                if q_state is not None:
                    headers["x-kil-q-state"] = q_state
                if q_state is not None and int(time.time()) >= issued + 10:
                    raise ControllerError("signed-state request validity expired before send")
                claim_request_attempt(
                    self.journal_path,
                    track,
                    readiness_nonce=readiness_nonce,
                )
                connection = connections[track]
                send_ns = self._monotonic_now()
                try:
                    connection.request(  # type: ignore[attr-defined]
                        "POST", "/consequential/admin", body=b"", headers=headers
                    )
                except (OSError, http.client.HTTPException) as error:
                    primary_failure = "request_send"
                    self._record_transport_failure(
                        track=track,
                        stage="request_send",
                        error=error,
                        connect_ns=connect_times[track],
                        send_ns=send_ns,
                    )
                    raise ControllerError(
                        "central request failed during request_send without retry"
                    ) from None
                try:
                    response = connection.getresponse()  # type: ignore[attr-defined]
                except (OSError, http.client.HTTPException) as error:
                    primary_failure = "response_headers"
                    self._record_transport_failure(
                        track=track,
                        stage="response_headers",
                        error=error,
                        connect_ns=connect_times[track],
                        send_ns=send_ns,
                    )
                    raise ControllerError(
                        "central request failed during response_headers without retry"
                    ) from None
                try:
                    response.read(4096)
                except (OSError, http.client.HTTPException) as error:
                    primary_failure = "response_body"
                    self._record_transport_failure(
                        track=track,
                        stage="response_body",
                        error=error,
                        connect_ns=connect_times[track],
                        send_ns=send_ns,
                    )
                    raise ControllerError(
                        "central request failed during response_body without retry"
                    ) from None
                receive_ns = self._monotonic_now()
                if q_state is not None and int(time.time()) >= issued + 10:
                    _complete_request_attempt(
                        self.journal_path,
                        track,
                        success=False,
                        record_sha256=None,
                    )
                    raise ControllerError(
                        "signed-state request missed its 10-second validity window"
                    )
                client_digest = response.getheader("x-kil-decision-digest")
                if response.status in {200, 403}:
                    client_digest = _exact_digest(
                        "client response decision digest", client_digest
                    )
                elif response.status >= 500:
                    if client_digest is not None:
                        _complete_request_attempt(
                            self.journal_path,
                            track,
                            success=False,
                            record_sha256=None,
                        )
                        raise ControllerError(
                            "authz 5xx exposed a forbidden client digest"
                        )
                else:
                    _complete_request_attempt(
                        self.journal_path,
                        track,
                        success=False,
                        record_sha256=None,
                    )
                    raise ControllerError(
                        "client received an unapproved response status"
                    )
                record = {
                    "schema_version": "kil.v3b1-request.v1",
                    "run_id": manifest["run_id"],
                    "request_id": manifest["request_id"],
                    "track": track.value,
                    "method": "POST",
                    "path": "/consequential/admin",
                    "attempt_count": 1,
                    "retry_observed": False,
                    "retry_control_headers": dict(RETRY_CONTROL_HEADERS),
                    "authorization_sha256": comparison["authorization_sha256"],
                    "q_state_present": q_state is not None,
                    "q_state_sha256": (
                        None
                        if q_state is None
                        else _digest_bytes(q_state.encode("utf-8"))
                    ),
                    "adversarial_headers": dict(ADVERSARIAL_HEADERS),
                    "comparison_facts_sha256": comparison_sha,
                    "send_monotonic_ns": send_ns,
                    "receive_monotonic_ns": receive_ns,
                    "client_response_status": response.status,
                    "client_decision_digest": client_digest,
                }
                _request_closed(record)
                records.append(record)
                _write_file(request_path, _jsonl_payload(records), 0o444)
                _complete_request_attempt(
                    self.journal_path,
                    track,
                    success=True,
                    record_sha256=_digest_bytes(_canonical_bytes(record)),
                )
        finally:
            close_failures = self._close_connections(connections)
            if close_failures:
                if primary_failure is None and any(
                    request["status"] == "intent_persisted"
                    for request in load_lifecycle_journal(self.journal_path)[
                        "requests"
                    ].values()
                ):
                    primary_failure = "request_processing"
                self._record_close_failures(
                    readiness_nonce=readiness_nonce,
                    stage="request_finalization",
                    primary_failure=primary_failure,
                    failures=close_failures,
                )
                if primary_failure is None:
                    raise ControllerError(
                        "central request connection closure is ambiguous"
                    ) from None
                raise ControllerError(
                    f"central request failed during {primary_failure}; "
                    "connection closure is ambiguous"
                ) from None
        return self.collect()

    def _assert_only_recorded_managed(
        self, state: Mapping[str, object], *, expect_present: bool
    ) -> None:
        containers = self._inventory_mapping(self._docker_inventory("container"))
        networks = self._inventory_mapping(self._docker_inventory("network"))
        if expect_present:
            expected_containers = {
                str(item["id"]): str(item["name"])
                for item in state["objects"]  # type: ignore[union-attr]
            }
            expected_containers.update(
                {
                    str(item["id"]): str(item["name"])
                    for item in state.get("transient_objects", [])  # type: ignore[union-attr]
                }
            )
            expected_networks = {
                str(item["id"]): str(item["name"])
                for item in state["network_objects"]  # type: ignore[union-attr]
            }
        else:
            expected_containers = {}
            expected_networks = {}
        self._require_exact_inventory(
            "container", containers, expected_containers
        )
        self._require_exact_inventory("network", networks, expected_networks)

    def _prepare_teardown_evidence(
        self,
        manifest: dict[str, object],
        objects: list[dict[str, object]],
        freeze: EvidenceFreezeResult,
    ) -> tuple[Path | None, list[dict[str, object]], bool, str | None]:
        """Build only from the durable pre-teardown source freeze."""
        try:
            provisional_root = self._private_provisional_root()
            status_by_key = {
                (status.track, status.source): status for status in freeze.statuses
            }
            expected_keys = {
                (track.value, source)
                for track in _TRACKS
                for source in _FREEZE_SOURCES
            }
            if set(status_by_key) != expected_keys:
                raise ControllerError("durable source freeze is not nine closed legs")
            raw: dict[tuple[str, str], bytes] = {}
            for key, status in status_by_key.items():
                payload = self._attest_frozen_status_bytes(
                    status, freeze.raw_paths[key]
                )
                if payload is not None:
                    raw[key] = payload
            copied_raw = {
                track: raw[(track.value, "authz_decisions")]
                for track in _TRACKS
                if (track.value, "authz_decisions") in raw
            }
            copied_envoy: list[dict[str, object]] = []
            copied_targets: list[dict[str, object]] = []
            completed = freeze.complete
            if completed:
                if set(copied_raw) != set(_TRACKS):
                    raise ControllerError("complete freeze lacks decision bytes")
                for track in _TRACKS:
                    copied_envoy.extend(
                        _parse_jsonl_bytes(
                            raw[(track.value, "envoy_access")],
                            f"frozen Envoy {track.value}",
                            _envoy_closed,
                            allow_empty=False,
                        )
                    )
                    copied_targets.extend(
                        _parse_jsonl_bytes(
                            raw[(track.value, "target_markers")],
                            f"frozen targets {track.value}",
                            _target_closed,
                            allow_empty=True,
                        )
                    )
                requests = self._request_records(manifest)
                decisions: list[dict[str, object]] = []
                for track in _TRACKS:
                    decisions.extend(
                        _parse_jsonl_bytes(
                            copied_raw[track],
                            f"decisions {track.value}",
                            _decision_closed,
                            allow_empty=False,
                        )
                    )
                joins = join_evidence(
                    manifest, requests, decisions, copied_envoy, copied_targets
                )
                output = write_evidence_bundle(
                    provisional_root,
                    manifest,
                    requests=requests,
                    decisions=decisions,
                    envoy=copied_envoy,
                    targets=copied_targets,
                    joins=joins,
                    raw_decisions=copied_raw,
                    resume_attested=True,
                )
                if {
                    track: (
                        output / "raw/decisions" / f"{track.value}.jsonl"
                    ).read_bytes()
                    for track in _TRACKS
                } != copied_raw:
                    raise ControllerError(
                        "stopped-container decision byte comparison failed"
                    )
                if (output / "envoy.jsonl").read_bytes() != _jsonl_payload(copied_envoy):
                    raise ControllerError("stopped-container Envoy byte comparison failed")
                if (output / "targets.jsonl").read_bytes() != _jsonl_payload(copied_targets):
                    raise ControllerError("stopped-container target byte comparison failed")
            else:
                partial_requests: list[dict[str, object]] | None = None
                request_path = _runtime_root(self.root, manifest) / "requests.jsonl"
                partial_requests = (
                    _parse_jsonl_bytes(
                        request_path.read_bytes(),
                        "incomplete central requests",
                        _request_closed,
                        allow_empty=True,
                    )
                    if request_path.is_file() and not request_path.is_symlink()
                    else []
                )
                if partial_requests:
                    validate_request_journal(
                        partial_requests,
                        load_lifecycle_journal(self.journal_path),
                        require_all=False,
                    )
                failure_raw_decisions = {
                    track: (
                        raw[(track.value, "authz_decisions")]
                        if status_by_key[
                            (track.value, "authz_decisions")
                        ].status
                        == "copied"
                        else b""
                    )
                    for track in _TRACKS
                }
                failure_envoy: list[dict[str, object]] = []
                failure_targets: list[dict[str, object]] = []
                for track in _TRACKS:
                    envoy_key = (track.value, "envoy_access")
                    if status_by_key[envoy_key].status == "copied":
                        failure_envoy.extend(
                            _parse_jsonl_bytes(
                                raw[envoy_key],
                                f"incomplete frozen Envoy {track.value}",
                                _envoy_closed,
                                allow_empty=True,
                            )
                        )
                    target_key = (track.value, "target_markers")
                    if status_by_key[target_key].status == "copied":
                        failure_targets.extend(
                            _parse_jsonl_bytes(
                                raw[target_key],
                                f"incomplete frozen targets {track.value}",
                                _target_closed,
                                allow_empty=True,
                            )
                        )
                output = _prepare_failure_provisional(
                    provisional_root,
                    manifest,
                    requests=partial_requests,
                    raw_decisions=failure_raw_decisions,
                    envoy=failure_envoy,
                    targets=failure_targets,
                    reset=True,
                )
            source_attestations: list[dict[str, object]] = []
            if completed:
                by_track_role = {
                    (item["track"], item["role"]): item
                    for item in objects
                    if item["role"] in {"authz", "target", "envoy"}
                }
                if len(by_track_role) != 9:
                    bound_state = load_bound_active_state(self.state_path)
                    by_track_role = {
                        (item["track"], item["role"]): item
                        for item in bound_state["objects"]
                        if item["role"] in {"authz", "target", "envoy"}
                    }
                for track in _TRACKS:
                    target_records = [
                        item for item in copied_targets if item["track"] == track.value
                    ]
                    envoy_records = [
                        item for item in copied_envoy if item["track"] == track.value
                    ]
                    source_attestations.append(
                        {
                            "track": track.value,
                            "container_ids": {
                                role: by_track_role[(track.value, role)]["id"]
                                for role in ("authz", "target", "envoy")
                            },
                            "image_ids": {
                                role: by_track_role[(track.value, role)]["image_id"]
                                for role in ("authz", "target", "envoy")
                            },
                            "config_sha256": {
                                role: by_track_role[(track.value, role)]["config_sha256"]
                                for role in ("authz", "target", "envoy")
                            },
                            "raw_decisions_sha256": _digest_bytes(copied_raw[track]),
                            "raw_decision_count": len(copied_raw[track].splitlines()),
                            "raw_envoy_sha256": _digest_bytes(
                                _jsonl_payload(envoy_records)
                            ),
                            "raw_envoy_count": len(envoy_records),
                            "raw_targets_sha256": _digest_bytes(
                                _jsonl_payload(target_records)
                            ),
                            "raw_target_count": len(target_records),
                        }
                    )
            authoritative = authoritative_bundle_attestation(output)
            journal_event(
                self.journal_path,
                "evidence_collect_complete",
                {
                    "completed": completed,
                    "bundle_sha256": _digest_file(output / "SHA256SUMS"),
                    "authoritative_attestation": authoritative,
                },
            )
            journal_event(
                self.journal_path,
                "source_attestations_persisted",
                {"source_attestations": source_attestations},
            )
            return output, source_attestations, completed, None
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"[:1000]
            journal_event(
                self.journal_path,
                "evidence_rejected_before_teardown",
                {"reason": reason},
            )
            return None, [], False, reason

    def down(self) -> Path:
        journal = load_lifecycle_journal(self.journal_path)
        listed = self._execute(["colima", "list", "--json"], timeout_s=30)
        profiles = parse_colima_profiles(listed.stdout)
        dedicated = next(
            (record for record in profiles if record["name"] == LAB_IDENTITY), None
        )
        if journal["profile_created"] is not True:
            if dedicated is not None:
                raise ControllerError(
                    "ambiguous Colima start requires manual recovery; dedicated profile left untouched"
                )
            else:
                journal_event(
                    self.journal_path,
                    "down_complete_without_owned_profile",
                    {"profile_absent": True},
                )
                global_after = self._capture_global_context()
                if global_after != journal["global_context_before"]:
                    raise ControllerError("global Docker context changed during lifecycle")
                archive_root = self._private_completed_root()
                archived = archive_root / f"preprofile-{journal['execution_nonce']}.journal.json"
                if archived.exists():
                    raise ControllerError("pre-profile lifecycle journal archive would clobber")
                self._clear_readiness_poison(str(journal["execution_nonce"]))
                os.rename(self.journal_path, archived)
                return self.private_root

        if dedicated is not None:
            if str(dedicated["status"]).lower() not in {"running", "stopped"}:
                raise ControllerError("owned Colima profile status is invalid")
            validate_dedicated_colima_profile(
                {**dedicated, "status": "Running"}
            )

        events = journal["events"]
        assert isinstance(events, list)
        if dedicated is None:
            if not any(event["event"] == "colima_delete_intent" for event in events):
                raise ControllerError("owned profile disappeared before an exact deletion intent")
            if journal["manifest_path"] is None:
                global_after = self._capture_global_context()
                if global_after != journal["global_context_before"]:
                    raise ControllerError("global Docker context changed during lifecycle")
                archive_root = self._private_completed_root()
                archived = archive_root / f"premanifest-{journal['execution_nonce']}.journal.json"
                if archived.exists():
                    raise ControllerError("pre-manifest lifecycle journal archive would clobber")
                self._clear_readiness_poison(str(journal["execution_nonce"]))
                os.rename(self.journal_path, archived)
                return self.private_root
            manifest = _load_json_bytes(
                Path(str(journal["manifest_path"])).read_bytes(), "private manifest"
            )
            _validate_manifest(manifest)
            published = self.evidence_root / str(manifest["run_id"])

            def complete_publication(public_manifest_sha256: str) -> None:
                _require_sha256(
                    "public manifest completion sha256",
                    public_manifest_sha256,
                )
                completion = {
                    "run_id": manifest["run_id"],
                    "public_manifest_sha256": public_manifest_sha256,
                }
                current = load_lifecycle_journal(self.journal_path)
                current_events = current["events"]
                assert isinstance(current_events, list)
                recorded = [
                    event
                    for event in current_events
                    if event["event"] == "publication_complete"
                ]
                if recorded:
                    if recorded[-1]["details"] != completion:
                        raise ControllerError(
                            "durable publication completion does not bind public evidence"
                        )
                    return
                journal_event(
                    self.journal_path,
                    "publication_complete",
                    completion,
                )

            def before_publication_completion() -> None:
                if self.publication_fault is not None:
                    self.publication_fault(
                        "after_postrename_validation", published
                    )

            def cleanup_completed_publication() -> None:
                archive_root = self._private_completed_root()
                archived = archive_root / f"{manifest['run_id']}.journal.json"
                if archived.exists():
                    raise ControllerError(
                        "completed lifecycle journal archive would clobber"
                    )
                if self.state_path.exists():
                    self.state_path.unlink()
                self._clear_readiness_poison(str(journal["execution_nonce"]))
                os.rename(self.journal_path, archived)

            if not published.exists():
                failure_transition = _post_teardown_failure_transition(
                    events, str(manifest["run_id"])
                )
                if failure_transition is not None:
                    intent, prepared = failure_transition
                    intent_details = intent["details"]
                    assert isinstance(intent_details, dict)
                    source_attestations = []
                    completed = False
                    provisional = (
                        self._private_provisional_root()
                        / str(manifest["run_id"])
                    )
                    if prepared is None:
                        provisional = _prepare_failure_provisional(
                            self._private_provisional_root(), manifest, reset=True
                        )
                        authoritative = authoritative_bundle_attestation(
                            provisional
                        )
                        updated = journal_event(
                            self.journal_path,
                            "post_teardown_failure_bundle_prepared",
                            {
                                **intent_details,
                                "intent_sequence": intent["sequence"],
                                "authoritative_attestation": authoritative,
                            },
                        )
                        updated_events = updated["events"]
                        assert isinstance(updated_events, list)
                        events = updated_events
                    else:
                        prepared_details = prepared["details"]
                        assert isinstance(prepared_details, dict)
                        authoritative = _validate_authoritative_attestation(
                            prepared_details["authoritative_attestation"]  # type: ignore[arg-type]
                        )
                else:
                    source_attestations = next(
                        (
                            event["details"]["source_attestations"]
                            for event in events
                            if event["event"] == "source_attestations_persisted"
                        ),
                        [],
                    )
                    completed = next(
                        (
                            bool(event["details"]["completed"])
                            for event in reversed(events)
                            if event["event"] == "evidence_collect_complete"
                        ),
                        False,
                    )
                    authoritative = _journal_authoritative_attestation(events)
                tool_identities = next(
                    (
                        event["details"].get("tool_identities", {})
                        for event in events
                        if event["event"] == "preflight_complete"
                    ),
                    {},
                )
                engine_provenance = next(
                    (
                        event["details"]
                        for event in events
                        if event["event"] == "engine_provenance_observed"
                    ),
                    {},
                )
                provisional = self._private_provisional_root() / str(manifest["run_id"])
                if not provisional.is_dir():
                    raise ControllerError("post-delete provisional evidence is unavailable")
                global_after = self._capture_global_context()
                if not any(
                    event["event"] == "publication_intent"
                    for event in events
                ):
                    updated = journal_event(
                        self.journal_path,
                        "publication_intent",
                        {
                            "run_id": manifest["run_id"],
                            "completed": completed,
                        },
                    )
                    updated_events = updated["events"]
                    assert isinstance(updated_events, list)
                    events = updated_events
                published = finalize_publication(
                    provisional,
                    self.evidence_root,
                    manifest,
                    source_attestations=source_attestations,
                    tool_identities=tool_identities,
                    engine_provenance=engine_provenance,
                    global_context_before=str(journal["global_context_before"]),
                    global_context_after=global_after,
                    completed=completed,
                    authoritative_attestation=authoritative,
                    publication_fault=self.publication_fault,
                    publication_complete=complete_publication,
                    repository_root=self.root,
                    publication_staging_root=self._private_publication_root(),
                )
            recovered_journal = load_lifecycle_journal(self.journal_path)
            recovered_events = recovered_journal["events"]
            assert isinstance(recovered_events, list)
            completed, source_attestations, authoritative = (
                _publication_recovery_contract(recovered_events, manifest)
            )
            tool_identities = next(
                (
                    event["details"].get("tool_identities", {})
                    for event in recovered_events
                    if event["event"] == "preflight_complete"
                ),
                {},
            )
            engine_provenance = next(
                (
                    event["details"]
                    for event in recovered_events
                    if event["event"] == "engine_provenance_observed"
                ),
                {},
            )
            if (
                type(tool_identities) is not dict
                or type(engine_provenance) is not dict
            ):
                raise ControllerError(
                    "durable publication provenance is malformed"
                )
            _validate_public_provenance(tool_identities, engine_provenance)
            global_after = self._capture_global_context()
            if global_after != recovered_journal["global_context_before"]:
                raise ControllerError(
                    "global Docker context changed during lifecycle"
                )
            _verify_recovered_publication(
                published,
                manifest,
                completed=completed,
                source_attestations=source_attestations,
                authoritative_attestation=authoritative,
                tool_identities=tool_identities,
                engine_provenance=engine_provenance,
                global_context=str(recovered_journal["global_context_before"]),
                before_completion=before_publication_completion,
                publication_complete=complete_publication,
                publication_cleanup=cleanup_completed_publication,
            )
            return published
        if dedicated["status"].lower() != "running":
            journal_event(
                self.journal_path,
                "colima_recovery_start_intent",
                {"profile": LAB_IDENTITY},
            )
            self._execute(
                self.colima_start_command(str(journal["execution_nonce"])),
                timeout_s=900,
            )
            journal_event(
                self.journal_path,
                "colima_recovery_start_complete",
                {"profile": LAB_IDENTITY},
            )
        try:
            recovery_attestation = self._attest_colima_after_start(
                str(journal["execution_nonce"])
            )
        except Exception as error:
            journal_event(
                self.journal_path,
                "colima_recovery_attestation_failed",
                {"reason": f"{type(error).__name__}: {error}"[:1000]},
            )
            raise ControllerError(
                "Colima recovery attestation failed; manual recovery required and profile left untouched"
            ) from error
        else:
            journal_event(
                self.journal_path,
                "colima_recovery_attested",
                {"attestation": recovery_attestation},
            )

        state, manifest, journal = self._load_for_down()
        if manifest is None:
            self._assert_only_recorded_managed(state, expect_present=True)
            journal_event(
                self.journal_path,
                "colima_stop_intent",
                {"profile": LAB_IDENTITY, "pre_manifest_failure": True},
            )
            self._execute(
                ["colima", "stop", "--profile", LAB_IDENTITY], timeout_s=300
            )
            journal_event(
                self.journal_path,
                "colima_stop_complete",
                {"profile": LAB_IDENTITY, "pre_manifest_failure": True},
            )
            journal_event(
                self.journal_path,
                "colima_delete_intent",
                {"profile": LAB_IDENTITY, "pre_manifest_failure": True},
            )
            self._execute(
                [
                    "colima", "delete", "--profile", LAB_IDENTITY,
                    "--force", "--data",
                ],
                timeout_s=300,
            )
            self._verify_profile_absent()
            global_after = self._capture_global_context()
            if global_after != journal["global_context_before"]:
                raise ControllerError("global Docker context changed during lifecycle")
            journal_event(
                self.journal_path,
                "colima_delete_complete",
                {"profile": LAB_IDENTITY, "verified_absent": True},
            )
            archive_root = self._private_completed_root()
            archived = archive_root / f"premanifest-{journal['execution_nonce']}.journal.json"
            if archived.exists():
                raise ControllerError("pre-manifest lifecycle journal archive would clobber")
            self._clear_readiness_poison(str(journal["execution_nonce"]))
            os.rename(self.journal_path, archived)
            return self.private_root
        self._assert_only_recorded_managed(state, expect_present=True)
        objects = state["objects"]
        assert isinstance(objects, list)
        transient_objects = state.get("transient_objects", [])
        assert isinstance(transient_objects, list)
        running_ordered = list(transient_objects) + [
            item
            for role in ("envoy", "authz", "target")
            for item in objects
            if item["role"] == role
        ]
        ordered = running_ordered + [
            item for item in objects if item["role"] == "driver"
        ]
        lifecycle_events = journal["events"]
        assert isinstance(lifecycle_events, list)
        up_complete_observed = any(
            event["event"] == "up_complete" for event in lifecycle_events
        )
        partial_rejections = [
            event
            for event in lifecycle_events
            if event["event"] == "partial_up_evidence_rejected"
        ]
        if len(partial_rejections) > 1 or (
            up_complete_observed and partial_rejections
        ):
            raise ControllerError("partial-up evidence status is contradictory")
        failure_details: dict[str, object] | None = None
        failure_intent_sequence: int | None = None
        if not up_complete_observed:
            if not partial_rejections:
                survivor_identities = {
                    "containers": sorted(
                        (
                            {"id": str(item["id"]), "name": str(item["name"])}
                            for item in ordered
                        ),
                        key=lambda item: (item["name"], item["id"]),
                    ),
                    "networks": sorted(
                        (
                            {"id": str(item["id"]), "name": str(item["name"])}
                            for item in state["network_objects"]  # type: ignore[union-attr]
                        ),
                        key=lambda item: (item["name"], item["id"]),
                    ),
                }
                journal_event(
                    self.journal_path,
                    "partial_up_evidence_rejected",
                    {
                        "reason_code": "up_complete_absent",
                        "up_complete_observed": False,
                        "promotable": False,
                        "container_count": len(survivor_identities["containers"]),
                        "network_count": len(survivor_identities["networks"]),
                        "survivor_identity_sha256": _digest_bytes(
                            canonical_json(survivor_identities).encode("utf-8")
                        ),
                    },
                )
            output = None
            source_attestations = []
            completed = False
            evidence_rejection = "partial_up:up_complete_absent"
            failure_details = {
                "run_id": manifest["run_id"],
                "evidence_rejection": evidence_rejection,
                "replacement": _FAILURE_BUNDLE_REPLACEMENT,
            }
            failure_transition = _post_teardown_failure_transition(
                load_lifecycle_journal(self.journal_path)["events"],  # type: ignore[arg-type]
                str(manifest["run_id"]),
            )
            if failure_transition is None:
                intent_journal = journal_event(
                    self.journal_path,
                    "post_teardown_failure_bundle_intent",
                    failure_details,
                )
                intent_events = intent_journal["events"]
                assert isinstance(intent_events, list)
                failure_intent_sequence = len(intent_events)
            else:
                failure_intent, _ = failure_transition
                if failure_intent["details"] != failure_details:
                    raise ControllerError(
                        "partial-up failure replacement provenance changed"
                    )
                failure_intent_sequence = int(failure_intent["sequence"])
            for item in running_ordered:
                self._stop_and_attest_container(item, manifest)
        else:
            requests_state = journal["requests"]
            assert isinstance(requests_state, dict)
            attempted_complete = all(
                item["status"] == "completed" for item in requests_state.values()
            )
            freeze = self._freeze_before_service_teardown(
                state,
                manifest,
                attempted_complete=attempted_complete,
                transient_objects=transient_objects,
            )
            output, source_attestations, completed, evidence_rejection = (
                self._prepare_teardown_evidence(
                    manifest, objects, freeze
                )
            )

        remaining_containers = list(ordered)
        remaining_networks = list(state["network_objects"])
        for item in ordered:
            current = (
                self._inspect_validation_container(
                    str(item["id"]), manifest, LiveTrack(str(item["track"]))
                )
                if item["role"] == "validator"
                else self._inspect_container(
                    str(item["id"]),
                    manifest,
                    str(item["role"]),
                    str(item["track"]),
                    require_running=False,
                )
            )
            if item["role"] == "validator":
                current_matches = current == item
            else:
                current_matches = _container_attestation_matches(
                    item, current, allow_stopped=True
                )
            if not current_matches:
                raise ControllerError("container changed before exact removal")
            identity = {"id": item["id"], "name": item["name"]}
            transition = _removal_transition(
                load_lifecycle_journal(self.journal_path)["events"],  # type: ignore[arg-type]
                "container",
                identity,
            )
            if transition == "complete":
                raise ControllerError("completed container removal reappeared")
            if transition == "unstarted":
                journal_event(
                    self.journal_path,
                    "container_remove_intent",
                    identity,
                )
            self._execute(
                self.docker_command("rm", str(item["id"])),
                timeout_s=30,
                docker=True,
            )
            remaining_containers.remove(item)
            self._assert_only_recorded_managed(
                {
                    **state,
                    "objects": [
                        record
                        for record in remaining_containers
                        if record["role"] != "validator"
                    ],
                    "transient_objects": [
                        record
                        for record in remaining_containers
                        if record["role"] == "validator"
                    ],
                    "network_objects": remaining_networks,
                },
                expect_present=True,
            )
            journal_event(
                self.journal_path,
                "container_remove_complete",
                identity,
            )
        networks = state["network_objects"]
        assert isinstance(networks, list)
        for item in networks:
            current = self._inspect_network(
                str(item["id"]),
                manifest,
                str(item["track"]),
                segment=str(item.get("segment", "backend")),
                require_complete_membership=False,
                require_empty_membership=True,
            )
            if current != item:
                raise ControllerError("network changed before exact removal")
            identity = {"id": item["id"], "name": item["name"]}
            transition = _removal_transition(
                load_lifecycle_journal(self.journal_path)["events"],  # type: ignore[arg-type]
                "network",
                identity,
            )
            if transition == "complete":
                raise ControllerError("completed network removal reappeared")
            if transition == "unstarted":
                journal_event(
                    self.journal_path,
                    "network_remove_intent",
                    identity,
                )
            self._execute(
                self.docker_command("network", "rm", str(item["id"])),
                timeout_s=30,
                docker=True,
            )
            remaining_networks.remove(item)
            self._assert_only_recorded_managed(
                {
                    **state,
                    "objects": [],
                    "transient_objects": [],
                    "network_objects": remaining_networks,
                },
                expect_present=True,
            )
            journal_event(
                self.journal_path,
                "network_remove_complete",
                identity,
            )
        empty_state = {
            **state,
            "objects": [],
            "transient_objects": [],
            "network_objects": [],
        }
        self._assert_only_recorded_managed(empty_state, expect_present=False)
        journal_event(
            self.journal_path, "colima_stop_intent", {"profile": LAB_IDENTITY}
        )
        self._execute(["colima", "stop", "--profile", LAB_IDENTITY], timeout_s=300)
        journal_event(
            self.journal_path, "colima_stop_complete", {"profile": LAB_IDENTITY}
        )
        journal_event(
            self.journal_path, "colima_delete_intent", {"profile": LAB_IDENTITY}
        )
        self._execute(
            [
                "colima", "delete", "--profile", LAB_IDENTITY, "--force", "--data",
            ],
            timeout_s=300,
        )
        self._verify_profile_absent()
        journal_event(
            self.journal_path,
            "colima_delete_complete",
            {"profile": LAB_IDENTITY, "verified_absent": True},
        )
        global_after = self._capture_global_context()
        if global_after != journal["global_context_before"]:
            raise ControllerError("global Docker context changed during lifecycle")
        if output is None:
            if failure_details is None:
                failure_details = {
                    "run_id": manifest["run_id"],
                    "evidence_rejection": evidence_rejection,
                    "replacement": _FAILURE_BUNDLE_REPLACEMENT,
                }
                intent_journal = journal_event(
                    self.journal_path,
                    "post_teardown_failure_bundle_intent",
                    failure_details,
                )
                intent_events = intent_journal["events"]
                assert isinstance(intent_events, list)
                failure_intent_sequence = len(intent_events)
            assert failure_intent_sequence is not None
            output = _prepare_failure_provisional(
                self._private_provisional_root(), manifest, reset=True
            )
            source_attestations = []
            completed = False
            authoritative = authoritative_bundle_attestation(output)
            journal_event(
                self.journal_path,
                "post_teardown_failure_bundle_prepared",
                {
                    **failure_details,
                    "intent_sequence": failure_intent_sequence,
                    "authoritative_attestation": authoritative,
                },
            )
        events = load_lifecycle_journal(self.journal_path)["events"]
        assert isinstance(events, list)
        authoritative = _journal_authoritative_attestation(events)
        tool_identities = next(
            (
                event["details"].get("tool_identities", {})
                for event in events
                if event["event"] == "preflight_complete"
            ),
            {},
        )
        engine_provenance = next(
            (
                event["details"]
                for event in events
                if event["event"] == "engine_provenance_observed"
            ),
            {},
        )
        journal_event(
            self.journal_path,
            "publication_intent",
            {"run_id": manifest["run_id"], "completed": completed},
        )

        def complete_publication(public_manifest_sha256: str) -> None:
            _require_sha256(
                "public manifest completion sha256",
                public_manifest_sha256,
            )
            journal_event(
                self.journal_path,
                "publication_complete",
                {
                    "run_id": manifest["run_id"],
                    "public_manifest_sha256": public_manifest_sha256,
                },
            )

        def cleanup_completed_publication() -> None:
            archive_root = self._private_completed_root()
            archived_journal = (
                archive_root / f"{manifest['run_id']}.journal.json"
            )
            if archived_journal.exists():
                raise ControllerError(
                    "completed lifecycle journal would clobber an archive"
                )
            if self.state_path.exists():
                self.state_path.unlink()
            self._clear_readiness_poison(str(journal["execution_nonce"]))
            os.rename(self.journal_path, archived_journal)

        published = finalize_publication(
            output,
            self.evidence_root,
            manifest,
            source_attestations=source_attestations,
            tool_identities=tool_identities,
            engine_provenance=engine_provenance,
            global_context_before=str(journal["global_context_before"]),
            global_context_after=global_after,
            completed=completed,
            authoritative_attestation=authoritative,
            publication_fault=self.publication_fault,
            publication_complete=complete_publication,
            publication_cleanup=cleanup_completed_publication,
            repository_root=self.root,
            publication_staging_root=self._private_publication_root(),
        )
        return published


def make_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "up", "run", "collect", "down"):
        subparsers.add_parser(command)
    view = subparsers.add_parser("view")
    view.add_argument("--bundle", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = make_parser().parse_args(argv)
    try:
        if arguments.command == "view":
            presenter = verify_presenter_bundle(arguments.bundle)
            print(f"accepted presenter {presenter}")
            return 0
        controller = LocalEnvoyController()
        result = getattr(controller, arguments.command)()
    except ControllerError as error:
        raise SystemExit(f"v3b1-local-envoy: {error}") from error
    if isinstance(result, Path):
        print(result)
    else:
        print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
