#!/usr/bin/env python3
"""Run the closed, local-only V3B-1 pinned Envoy boundary proof."""

from argparse import ArgumentParser
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import hmac
from html import escape
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
    DriverProtocolError,
    LINUX_ERRNO_NAMES,
    canonical_record,
    driver_definition,
    parse_instruction as parse_driver_instruction,
    parse_result as parse_driver_result,
)
from kil.v3b_preflight import EVIDENCE_SCOPE, LAB_IDENTITY, V3BProfile

try:
    from tools.v3b1_driver_transport import (
        DriverProcessFactory,
        DriverSession,
        DriverTransportError,
        SubprocessDriverProcessFactory,
        attest_cancelled_exit,
        cleanup_driver_process,
        close_instruction_stream,
        attest_driver_result_exit,
        read_driver_result,
        read_readiness_record,
        remaining_seconds,
        start_attached_driver,
        write_instruction,
    )
    from tools.bootstrap_v3b_tools import verify_content_lock
except ModuleNotFoundError:  # Direct execution places ``tools`` on sys.path.
    from v3b1_driver_transport import (  # type: ignore[no-redef]
        DriverProcessFactory,
        DriverSession,
        DriverTransportError,
        SubprocessDriverProcessFactory,
        attest_cancelled_exit,
        cleanup_driver_process,
        close_instruction_stream,
        attest_driver_result_exit,
        read_driver_result,
        read_readiness_record,
        remaining_seconds,
        start_attached_driver,
        write_instruction,
    )
    from bootstrap_v3b_tools import verify_content_lock

try:
    from tools.v3b1_harness_contract import (
        ContractError as HarnessContractError,
        DRIVER_TOPOLOGY_SCHEMA_VERSION,
        DockerInventory,
        DockerInventoryEntry,
        RequestFailureProvenance,
        SourceCollectionStatus,
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
DRIVER_MANIFEST_SCHEMA = "kil.v3b1-manifest.v2"
MANIFEST_SCHEMA = "kil.v3b1-manifest.v3"
STATE_SCHEMA = "kil.v3b1-active-state.v2"
LEGACY_JOURNAL_SCHEMA = "kil.v3b1-lifecycle-journal.v1"
JOURNAL_SCHEMA = "kil.v3b1-lifecycle-journal.v2"
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
_DRIVER_CLEANUP_DEADLINE_NS = 5_000_000_000
_EVIDENCE_READ_DEADLINE_NS = 5_000_000_000
_EVIDENCE_READ_POLL_S = 0.05
_DRIVER_STATE_FORMAT = "{{.Id}} {{.State.Running}} {{.State.Status}}"
_DRIVER_READINESS_FAILURE_CATEGORIES = {
    "clock_failure",
    "cleanup_ambiguous",
    "cleanup_kill",
    "cleanup_persistence",
    "cleanup_pipe_close",
    "cleanup_poll",
    "cleanup_read_worker",
    "cleanup_wait",
    "cleanup_wait_timeout",
    "container_stop",
    "container_inspect",
    "container_stop_verify",
    "controller_persistence",
    "deadline_expired",
    "extra_stdout",
    "invalid_command",
    "invalid_identity",
    "nonzero_exit",
    "pipe_oversize",
    "pipe_read",
    "pipe_unavailable",
    "process_poll",
    "process_start",
    "process_wait",
    "process_wait_timeout",
    "protocol_invalid",
    "readiness_framing",
    "stderr_present",
    "stdin_close",
    "stdin_close_ambiguous",
    "stdout_eof",
    "stdout_oversize",
    "stdout_read",
    "termination_ambiguous",
}
_DRIVER_READINESS_FAILURE_STAGES = {
    "readiness_deadline",
    "start_intent",
    "process_start",
    "start_complete",
    "readiness_record",
    "readiness_complete",
    "cancel_signal",
    "cancel_exit",
    "readiness_set_complete",
    "diagnostic_complete",
}
_DRIVER_READINESS_CONTROLLER_STAGES = {
    "readiness_deadline",
    "readiness_set_complete",
    "diagnostic_complete",
}
_DRIVER_CLEANUP_OUTCOMES = {"already_exited", "terminated", "killed"}
_TEARDOWN_SERVICE_ROLES = ("envoy", "authz", "target")
_TEARDOWN_REMOVAL_ROLES = ("driver", "envoy", "authz", "target")


@dataclass(frozen=True, slots=True)
class _DriverCancellationOutcome:
    track: LiveTrack
    driver_id: str
    status: str
    category: str | None

    def __post_init__(self) -> None:
        _require_sha256("cancelled driver full ID", self.driver_id)
        if self.status not in {
            "clean_cancel",
            "cleanup_complete",
            "cleanup_failed",
            "cleanup_ambiguous",
        }:
            raise ControllerError("driver cancellation outcome is invalid")
        if (self.status in {"clean_cancel", "cleanup_complete"}) is not (
            self.category is None
        ):
            raise ControllerError("driver cancellation category is invalid")
        if self.category is not None and self.category not in (
            _DRIVER_READINESS_FAILURE_CATEGORIES | {"cleanup_persistence"}
        ):
            raise ControllerError("driver cancellation failure is invalid")
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
    driver_boundary: bool = False


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
    if event_name in {
        "foreign_profile_snapshot_before",
        "foreign_profile_snapshot_after",
    }:
        capture_stage = (
            "before_colima_mutation"
            if event_name.endswith("_before")
            else "after_owned_profile_deletion"
        )
        _validate_foreign_profile_snapshot(details, capture_stage=capture_stage)
        return
    if event_name == "foreign_profile_mismatch":
        if set(details) != {
            "before_sha256", "after_sha256", "mismatch_categories"
        }:
            raise ControllerError("foreign profile mismatch fields are not closed")
        _require_sha256("foreign before snapshot", details["before_sha256"])
        _require_sha256("foreign after snapshot", details["after_sha256"])
        categories = details["mismatch_categories"]
        if (
            type(categories) is not list
            or not categories
            or categories != [
                name for name in _FOREIGN_MISMATCH_CATEGORIES if name in categories
            ]
        ):
            raise ControllerError("foreign profile mismatch categories are invalid")
        return
    if event_name == "topology_absence_attested":
        if set(details) != {
            "container_count",
            "network_count",
            "container_identity_sha256",
            "network_identity_sha256",
            "survivor_containers",
            "survivor_networks",
        }:
            raise ControllerError("topology absence fields are not closed")
        if (
            details["container_count"] != 15
            or details["network_count"] != 6
            or details["survivor_containers"] != []
            or details["survivor_networks"] != []
        ):
            raise ControllerError("topology absence cardinality is invalid")
        _require_sha256(
            "topology container identity", details["container_identity_sha256"]
        )
        _require_sha256(
            "topology network identity", details["network_identity_sha256"]
        )
        return
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
    if event_name in {"container_stop_intent", "container_stop_complete"}:
        expected = {"id", "name", "role"} if event_name.endswith("_intent") else {"id", "name"}
        if set(details) != expected:
            raise ControllerError("container stop fields are not closed")
        try:
            DockerInventoryEntry.from_mapping(
                {"id": details["id"], "name": details["name"]},
                "container",
                schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION,
            )
        except (HarnessContractError, KeyError) as error:
            raise ControllerError("container stop identity is invalid") from error
        if event_name.endswith("_intent"):
            role = details["role"]
            if type(role) is not str or role not in {
                "envoy", "authz", "target", "validator"
            }:
                raise ControllerError("container stop role is invalid")
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
    if event_name in {
        "driver_start_intent",
        "driver_start_complete",
        "driver_readiness_complete",
        "readiness_cancel_intent",
        "readiness_cancel_complete",
    }:
        expected = {"readiness_nonce", "track", "driver_id"}
        if event_name == "driver_readiness_complete":
            expected.add("record_sha256")
        if event_name == "readiness_cancel_complete":
            expected.add("exit_code")
        if set(details) != expected:
            raise ControllerError("driver readiness event fields are not closed")
        _require_sha256("driver readiness nonce", details["readiness_nonce"])
        _require_sha256("driver full ID", details["driver_id"])
        try:
            LiveTrack(details["track"])
        except (TypeError, ValueError) as error:
            raise ControllerError("driver readiness track is invalid") from error
        if event_name == "driver_readiness_complete":
            _require_sha256("driver readiness record", details["record_sha256"])
        if event_name == "readiness_cancel_complete" and details["exit_code"] != 0:
            raise ControllerError("driver readiness cancellation exit is invalid")
        return
    if event_name in {
        "driver_stop_intent",
        "driver_stop_complete",
        "driver_stop_failed",
    }:
        expected = {"readiness_nonce", "track", "driver_id"}
        if event_name == "driver_stop_failed":
            expected.add("category")
        if set(details) != expected:
            raise ControllerError("driver stop event fields are not closed")
        _require_sha256("driver readiness nonce", details["readiness_nonce"])
        _require_sha256("driver full ID", details["driver_id"])
        try:
            LiveTrack(details["track"])
        except (TypeError, ValueError) as error:
            raise ControllerError("driver stop track is invalid") from error
        if (
            event_name == "driver_stop_failed"
            and details["category"]
            not in {
                "cleanup_persistence",
                "container_inspect",
                "container_stop",
                "container_stop_verify",
            }
        ):
            raise ControllerError("driver stop failure is invalid")
        return
    if event_name in {
        "driver_cleanup_intent",
        "driver_cleanup_complete",
        "driver_cleanup_failed",
    }:
        expected = {"readiness_nonce", "track", "driver_id"}
        if event_name == "driver_cleanup_complete":
            expected |= {"outcome", "exit_code"}
        elif event_name == "driver_cleanup_failed":
            expected.add("category")
        if set(details) != expected:
            raise ControllerError("driver cleanup event fields are not closed")
        _require_sha256("driver readiness nonce", details["readiness_nonce"])
        _require_sha256("driver full ID", details["driver_id"])
        try:
            LiveTrack(details["track"])
        except (TypeError, ValueError) as error:
            raise ControllerError("driver cleanup track is invalid") from error
        if event_name == "driver_cleanup_complete" and (
            details["outcome"] not in _DRIVER_CLEANUP_OUTCOMES
            or type(details["exit_code"]) is not int
        ):
            raise ControllerError("driver cleanup completion is invalid")
        if event_name == "driver_cleanup_failed" and (
            details["category"] not in _DRIVER_READINESS_FAILURE_CATEGORIES
        ):
            raise ControllerError("driver cleanup failure is invalid")
        return
    if event_name == "driver_readiness_set_complete":
        if set(details) != {
            "readiness_nonce",
            "tracks",
            "complete_monotonic_ns",
        }:
            raise ControllerError("driver readiness set fields are not closed")
        _require_sha256("driver readiness nonce", details["readiness_nonce"])
        if (
            details["tracks"] != [track.value for track in _TRACKS]
            or type(details["complete_monotonic_ns"]) is not int
            or details["complete_monotonic_ns"] < 0
        ):
            raise ControllerError("driver readiness set completion is invalid")
        return
    if event_name == "readiness_diagnostic_complete":
        if set(details) != {"readiness_nonce", "lifecycle_mode"}:
            raise ControllerError("readiness diagnostic fields are not closed")
        _require_sha256("driver readiness nonce", details["readiness_nonce"])
        if details["lifecycle_mode"] != "diagnostic_only":
            raise ControllerError("readiness diagnostic mode is invalid")
        return
    if event_name == "driver_readiness_failed":
        if set(details) != {
            "readiness_nonce",
            "scope",
            "track",
            "driver_id",
            "category",
            "stage",
        }:
            raise ControllerError("driver readiness failure fields are not closed")
        _require_sha256("driver readiness nonce", details["readiness_nonce"])
        if details["scope"] == "driver":
            _require_sha256("driver full ID", details["driver_id"])
            try:
                LiveTrack(details["track"])
            except (TypeError, ValueError) as error:
                raise ControllerError(
                    "driver readiness failure track is invalid"
                ) from error
            if details["stage"] in _DRIVER_READINESS_CONTROLLER_STAGES:
                raise ControllerError(
                    "driver readiness failure stage is not driver-scoped"
                )
        elif details["scope"] == "controller":
            if details["track"] is not None or details["driver_id"] is not None:
                raise ControllerError(
                    "controller readiness failure identity is not closed"
                )
            expected_category = (
                "clock_failure"
                if details["stage"] == "readiness_deadline"
                else "controller_persistence"
            )
            if (
                details["category"] != expected_category
                or details["stage"] not in _DRIVER_READINESS_CONTROLLER_STAGES
            ):
                raise ControllerError(
                    "controller readiness failure attribution is invalid"
                )
        else:
            raise ControllerError("driver readiness failure scope is invalid")
        if details["category"] not in _DRIVER_READINESS_FAILURE_CATEGORIES:
            raise ControllerError("driver readiness failure category is invalid")
        if details["stage"] not in _DRIVER_READINESS_FAILURE_STAGES:
            raise ControllerError("driver readiness failure stage is invalid")
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
            provenance = details["provenance"]
            try:
                RequestFailureProvenance.from_mapping(provenance)
            except HarnessContractError:
                _validate_request_failure_provenance(provenance)
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
    if event_name == "driver_instruction_write_intent":
        if set(details) != {
            "readiness_nonce",
            "track",
            "driver_id",
            "intent_id",
        }:
            raise ControllerError("driver instruction intent fields are not closed")
        _require_sha256("driver instruction readiness nonce", details["readiness_nonce"])
        _require_sha256("driver instruction full ID", details["driver_id"])
        _require_sha256("driver instruction request intent", details["intent_id"])
        try:
            LiveTrack(details["track"])
        except (TypeError, ValueError) as error:
            raise ControllerError("driver instruction track is invalid") from error
        return
    if event_name == "driver_result_persisted":
        if set(details) != {
            "driver_definition_sha256",
            "readiness_nonce",
            "track",
            "driver_id",
            "intent_id",
            "result_sha256",
        }:
            raise ControllerError("driver result persistence fields are not closed")
        for label, field in (
            ("driver result readiness nonce", "readiness_nonce"),
            ("driver result full ID", "driver_id"),
            ("driver result request intent", "intent_id"),
            ("driver result digest", "result_sha256"),
            ("driver result definition", "driver_definition_sha256"),
        ):
            _require_sha256(label, details[field])
        try:
            LiveTrack(details["track"])
        except (TypeError, ValueError) as error:
            raise ControllerError("driver result track is invalid") from error
        return
    if event_name == "request_record_persisted":
        if set(details) != {"track", "intent_id", "record_sha256"}:
            raise ControllerError("request record persistence fields are not closed")
        _require_sha256("request record intent", details["intent_id"])
        _require_sha256("request record digest", details["record_sha256"])
        try:
            LiveTrack(details["track"])
        except (TypeError, ValueError) as error:
            raise ControllerError("request record persistence track is invalid") from error
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


def _validate_foreign_snapshot_history(
    events: Sequence[Mapping[str, object]], journal_schema: str
) -> None:
    snapshot_names = {
        "foreign_profile_snapshot_before",
        "foreign_profile_snapshot_after",
        "foreign_profile_mismatch",
    }
    if journal_schema == LEGACY_JOURNAL_SCHEMA:
        if any(event.get("event") in snapshot_names for event in events):
            raise ControllerError("legacy journal contains v2 snapshot evidence")
        return
    if journal_schema != JOURNAL_SCHEMA:
        raise ControllerError("lifecycle journal schema is invalid")

    positions = {
        name: [
            index for index, event in enumerate(events)
            if event.get("event") == name
        ]
        for name in snapshot_names
    }
    before_positions = positions["foreign_profile_snapshot_before"]
    after_positions = positions["foreign_profile_snapshot_after"]
    mismatch_positions = positions["foreign_profile_mismatch"]
    if len(before_positions) > 1:
        raise ControllerError("foreign profile before snapshot is duplicated")
    if len(after_positions) > 1:
        raise ControllerError("foreign profile after snapshot is duplicated")
    if len(mismatch_positions) > 1:
        raise ControllerError("foreign profile mismatch is duplicated")

    preflight_positions = [
        index for index, event in enumerate(events)
        if event.get("event") == "preflight_complete"
    ]
    mutation_positions = [
        index for index, event in enumerate(events)
        if event.get("event") in {"colima_start_intent", "colima_recovery_start_intent"}
    ]
    publication_positions = [
        index for index, event in enumerate(events)
        if event.get("event") == "publication_intent"
    ]
    if mutation_positions and not before_positions:
        raise ControllerError("Colima mutation lacks a durable foreign profile before snapshot")
    if before_positions:
        before_position = before_positions[0]
        if (
            preflight_positions and before_position > preflight_positions[0]
        ) or (
            mutation_positions and before_position > mutation_positions[0]
        ):
            raise ControllerError("foreign profile before snapshot is phase-invalid")
    if after_positions:
        if not before_positions:
            raise ControllerError("foreign profile after snapshot lacks its before snapshot")
        before_position = before_positions[0]
        after_position = after_positions[0]
        if before_position >= after_position:
            raise ControllerError("foreign profile before snapshot is phase-invalid")
        verified_deletes = [
            index for index, event in enumerate(events)
            if event.get("event") in {
                "colima_delete_complete",
                "down_complete_without_owned_profile",
            }
            and type(event.get("details")) is dict
            and (
                event["details"].get("verified_absent") is True
                or event["details"].get("profile_absent") is True
            )
        ]
        absence_lower_bound = max([before_position, *mutation_positions])
        if not any(
            absence_lower_bound < position < after_position
            for position in verified_deletes
        ):
            raise ControllerError("foreign profile after snapshot precedes verified deletion")
        if publication_positions and after_position > publication_positions[0]:
            raise ControllerError("foreign profile after snapshot follows publication intent")
    if publication_positions and not after_positions:
        raise ControllerError("publication lacks a durable foreign profile after snapshot")

    if mismatch_positions:
        if not after_positions:
            raise ControllerError(
                "foreign profile mismatch lacks its after snapshot"
            )
        mismatch_position = mismatch_positions[0]
        if mismatch_position < after_positions[0] or (
            publication_positions
            and mismatch_position > publication_positions[0]
        ):
            raise ControllerError("foreign profile mismatch is phase-invalid")

    if before_positions and after_positions:
        before_event = events[before_positions[0]]
        after_event = events[after_positions[0]]
        before = before_event["details"]
        after = after_event["details"]
        assert isinstance(before, Mapping)
        assert isinstance(after, Mapping)
        comparison = compare_foreign_profile_snapshots(before, after)
        if comparison["unchanged"] is True:
            if mismatch_positions:
                raise ControllerError("unchanged foreign profiles have mismatch evidence")
        elif publication_positions and not mismatch_positions:
            raise ControllerError("changed foreign profiles lack mismatch evidence")
        if mismatch_positions:
            mismatch_position = mismatch_positions[0]
            if mismatch_position < after_positions[0] or (
                publication_positions and mismatch_position > publication_positions[0]
            ):
                raise ControllerError("foreign profile mismatch is phase-invalid")
            details = events[mismatch_position]["details"]
            assert isinstance(details, Mapping)
            expected = {
                "before_sha256": _digest_bytes(
                    canonical_json(before).encode("utf-8")
                ),
                "after_sha256": _digest_bytes(
                    canonical_json(after).encode("utf-8")
                ),
                "mismatch_categories": comparison["mismatch_categories"],
            }
            if dict(details) != expected:
                raise ControllerError("foreign profile mismatch does not bind snapshots")


def _validate_lifecycle_history(
    events: Sequence[Mapping[str, object]],
    requests: Mapping[str, object],
    journal_schema: str = LEGACY_JOURNAL_SCHEMA,
) -> tuple[str | None, bool]:
    _validate_foreign_snapshot_history(events, journal_schema)
    current_readiness: str | None = None
    readiness_complete = False
    readiness_session_terminal = True
    seen_readiness_nonces: set[str] = set()
    poisoned_readiness_nonces: set[str] = set()
    lifecycle_readiness_poisoned = False
    driver_states: dict[str, tuple[str, str]] = {}
    diagnostic_only = False
    replayed: dict[str, dict[str, object]] = {
        track.value: {"status": "not_attempted", "intent_id": None}
        for track in _TRACKS
    }
    request_driver_stages: dict[str, str] = {
        track.value: "not_attempted" for track in _TRACKS
    }
    request_driver_results: dict[str, Mapping[str, object]] = {}
    freeze_epoch: str | None = None
    freeze_intents: dict[tuple[str, str], Mapping[str, object]] = {}
    freeze_bytes: dict[tuple[str, str], Mapping[str, object]] = {}
    freeze_terminals: dict[tuple[str, str], SourceCollectionStatus] = {}
    freeze_completed = False
    removals: dict[tuple[str, str, str], str] = {}
    creations: dict[tuple[str, str], str] = {}
    creation_ids: dict[tuple[str, str], str] = {}
    validations: dict[tuple[str, str], str] = {}
    container_stops: dict[tuple[str, str], tuple[str, str]] = {}
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
        if event_name in {"container_stop_intent", "container_stop_complete"}:
            key = (str(details["id"]), str(details["name"]))
            if event_name.endswith("_intent"):
                role = str(details["role"])
                creation_kind = "validator" if role == "validator" else "container"
                creation_key = (creation_kind, key[1])
                if (
                    creations.get(creation_key) != "complete"
                    or creation_ids.get(creation_key) != key[0]
                ):
                    raise ControllerError(
                        "container stop intent lacks its exact created identity"
                    )
                if key in container_stops:
                    raise ControllerError("container stop intent is duplicated")
                container_stops[key] = ("pending", role)
            else:
                transition = container_stops.get(key)
                if transition is None or transition[0] != "pending":
                    raise ControllerError(
                        "container stop completion lacks its exact intent"
                    )
                container_stops[key] = ("complete", transition[1])
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
            if diagnostic_only:
                raise ControllerError(
                    "readiness diagnostic is teardown-only; down is required"
                )
            if current_readiness is not None and not readiness_session_terminal:
                raise ControllerError(
                    "previous readiness session is incomplete; down is required"
                )
            readiness_nonce = str(details["readiness_nonce"])
            if readiness_nonce in seen_readiness_nonces:
                raise ControllerError("readiness session nonce reuse is forbidden")
            seen_readiness_nonces.add(readiness_nonce)
            current_readiness = readiness_nonce
            readiness_complete = False
            readiness_session_terminal = False
            driver_states = {}
        elif event_name in {
            "driver_start_intent",
            "driver_start_complete",
            "driver_readiness_complete",
            "readiness_cancel_intent",
            "readiness_cancel_complete",
        }:
            if (
                current_readiness is None
                or details["readiness_nonce"] != current_readiness
                or current_readiness in poisoned_readiness_nonces
            ):
                raise ControllerError(
                    "driver event does not bind the current readiness session"
                )
            track = str(details["track"])
            driver_id = str(details["driver_id"])
            state, recorded_id = driver_states.get(track, ("unstarted", driver_id))
            if recorded_id != driver_id:
                raise ControllerError("driver readiness identity changed")
            expected_state = {
                "driver_start_intent": "unstarted",
                "driver_start_complete": "start_intent",
                "driver_readiness_complete": "started",
                "readiness_cancel_intent": {"started", "ready"},
                "readiness_cancel_complete": "cancel_intent",
            }[event_name]
            if (
                state not in expected_state
                if isinstance(expected_state, set)
                else state != expected_state
            ):
                raise ControllerError("driver readiness transition is invalid")
            driver_states[track] = (
                {
                    "driver_start_intent": "start_intent",
                    "driver_start_complete": "started",
                    "driver_readiness_complete": "ready",
                    "readiness_cancel_intent": "cancel_intent",
                    "readiness_cancel_complete": "cancelled",
                }[event_name],
                driver_id,
            )
        elif event_name in {
            "driver_stop_intent",
            "driver_stop_complete",
            "driver_stop_failed",
            "driver_cleanup_intent",
            "driver_cleanup_complete",
            "driver_cleanup_failed",
        }:
            if (
                current_readiness is None
                or details["readiness_nonce"] != current_readiness
            ):
                raise ControllerError(
                    "driver cleanup does not bind the current readiness session"
                )
            track = str(details["track"])
            driver_id = str(details["driver_id"])
            state, recorded_id = driver_states.get(track, ("unstarted", driver_id))
            if recorded_id != driver_id or state == "unstarted":
                raise ControllerError("driver cleanup identity changed")
            allowed = {
                "driver_stop_intent": {
                    "start_intent",
                    "started",
                    "ready",
                    "cancel_intent",
                    "cancelled",
                    "stop_failed",
                    "cleaned",
                    "cleanup_failed",
                },
                "driver_stop_complete": {"stop_intent"},
                "driver_stop_failed": {"stop_intent"},
                "driver_cleanup_intent": {
                    "start_intent",
                    "started",
                    "ready",
                    "cancel_intent",
                    "cancelled",
                    "stop_intent",
                    "stop_complete",
                    "stop_failed",
                },
                "driver_cleanup_complete": {"cleanup_intent"},
                "driver_cleanup_failed": {"cleanup_intent"},
            }[event_name]
            if state not in allowed:
                raise ControllerError("driver cleanup transition is invalid")
            driver_states[track] = (
                {
                    "driver_stop_intent": "stop_intent",
                    "driver_stop_complete": "stop_complete",
                    "driver_stop_failed": "stop_failed",
                    "driver_cleanup_intent": "cleanup_intent",
                    "driver_cleanup_complete": "cleaned",
                    "driver_cleanup_failed": "cleanup_failed",
                }[event_name],
                driver_id,
            )
        elif event_name == "driver_readiness_set_complete":
            if (
                current_readiness is None
                or details["readiness_nonce"] != current_readiness
                or set(driver_states) != {track.value for track in _TRACKS}
                or any(state != "ready" for state, _ in driver_states.values())
            ):
                raise ControllerError("driver readiness set is incomplete")
            readiness_complete = True
        elif event_name == "readiness_diagnostic_complete":
            if (
                current_readiness is None
                or details["readiness_nonce"] != current_readiness
                or not readiness_complete
                or set(driver_states) != {track.value for track in _TRACKS}
                or any(state != "cancelled" for state, _ in driver_states.values())
            ):
                raise ControllerError("readiness diagnostic is incomplete")
            diagnostic_only = True
            readiness_complete = False
            readiness_session_terminal = True
        elif event_name == "driver_readiness_failed":
            if (
                current_readiness is None
                or details["readiness_nonce"] != current_readiness
            ):
                raise ControllerError(
                    "driver readiness failure does not bind the current session"
                )
            failed_state = (
                driver_states.get(str(details["track"]))
                if details["scope"] == "driver"
                else None
            )
            if (
                failed_state is not None
                and failed_state[1] != details["driver_id"]
            ):
                raise ControllerError("driver readiness failure identity changed")
            poisoned_readiness_nonces.add(current_readiness)
            lifecycle_readiness_poisoned = True
            readiness_complete = False
            readiness_session_terminal = True
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
            if event_name == "readiness_connect_complete":
                readiness_session_terminal = True
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
            readiness_session_terminal = True
        elif event_name == "request_send_intent":
            if (
                current_readiness is None
                or current_readiness in poisoned_readiness_nonces
                or not readiness_complete
                or diagnostic_only
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
            request_driver_stages[track] = "request_intent"
        elif event_name == "driver_instruction_write_intent":
            track = str(details["track"])
            driver_state = driver_states.get(track)
            if (
                current_readiness is None
                or details["readiness_nonce"] != current_readiness
                or not readiness_complete
                or driver_state is None
                or driver_state != ("ready", details["driver_id"])
                or replayed[track]["status"] != "intent_persisted"
                or replayed[track]["intent_id"] != details["intent_id"]
                or request_driver_stages[track] != "request_intent"
            ):
                raise ControllerError("driver instruction intent lacks exact readiness/request binding")
            request_driver_stages[track] = "instruction_intent"
        elif event_name == "driver_result_persisted":
            track = str(details["track"])
            driver_state = driver_states.get(track)
            if (
                current_readiness is None
                or details["readiness_nonce"] != current_readiness
                or driver_state is None
                or driver_state != ("ready", details["driver_id"])
                or replayed[track]["status"] != "intent_persisted"
                or replayed[track]["intent_id"] != details["intent_id"]
                or request_driver_stages[track] != "instruction_intent"
            ):
                raise ControllerError("driver result lacks exact instruction binding")
            request_driver_results[track] = details
            request_driver_stages[track] = "result_persisted"
        elif event_name == "request_record_persisted":
            track = str(details["track"])
            if (
                replayed[track]["status"] != "intent_persisted"
                or replayed[track]["intent_id"] != details["intent_id"]
                or request_driver_stages[track] != "result_persisted"
            ):
                raise ControllerError("request record lacks exact driver-result binding")
            request_driver_stages[track] = "request_persisted"
        elif event_name in {"request_send_complete", "request_send_failed"}:
            track = str(details["track"])
            if replayed[track]["status"] != "intent_persisted":
                raise ControllerError("request completion transition is invalid")
            if (
                event_name == "request_send_complete"
                and request_driver_stages[track]
                not in {"request_intent", "request_persisted"}
            ):
                raise ControllerError("request completion lacks persisted request record")
            provenance = details.get("provenance")
            if (
                event_name == "request_send_failed"
                and type(provenance) is dict
                and provenance.get("provenance_source")
                == "linux_request_driver"
            ):
                persisted = request_driver_results.get(track)
                if (
                    persisted is None
                    or provenance.get("track") != track
                    or provenance.get("driver_full_id")
                    != persisted.get("driver_id")
                    or provenance.get("driver_result_sha256")
                    != persisted.get("result_sha256")
                    or provenance.get("driver_definition_sha256")
                    != persisted.get("driver_definition_sha256")
                ):
                    raise ControllerError(
                        "driver transport provenance lacks exact result binding"
                    )
            replayed[track]["status"] = (
                "completed" if event_name == "request_send_complete" else "failed"
            )
            request_driver_stages[track] = replayed[track]["status"]
    if replayed != requests:
        raise ControllerError("request events do not bind lifecycle request state")
    return current_readiness, readiness_complete


def _readiness_history_blocks_new_session(
    events: Sequence[Mapping[str, object]],
) -> bool:
    """Recognize an incomplete or permanently terminal latest readiness session."""
    current: str | None = None
    terminal = True
    blocked_terminal = False
    for event in events:
        event_name = event["event"]
        details = event["details"]
        assert isinstance(details, Mapping)
        if event_name == "readiness_session_started":
            current = str(details["readiness_nonce"])
            terminal = False
            blocked_terminal = False
        elif current is not None and details.get("readiness_nonce") == current:
            if event_name == "readiness_connect_complete":
                terminal = True
                blocked_terminal = False
            elif event_name in {
                "connection_close_failed",
                "driver_readiness_failed",
                "readiness_diagnostic_complete",
            }:
                terminal = True
                blocked_terminal = True
    return current is not None and (not terminal or blocked_terminal)


def _driver_recovery_authority(
    events: Sequence[Mapping[str, object]],
    track: str,
    driver_id: str,
) -> dict[str, object]:
    """Derive one driver's allowed recovery state from durable journal facts."""
    try:
        LiveTrack(track)
    except (TypeError, ValueError) as error:
        raise ControllerError("driver recovery track is invalid") from error
    _require_sha256("driver recovery full ID", driver_id)
    if type(events) not in {list, tuple}:
        raise ControllerError("driver recovery events are invalid")

    starts: list[Mapping[str, object]] = []
    output_terminals: list[Mapping[str, object]] = []
    stop_terminals: list[Mapping[str, object]] = []
    process_cleanup_events: list[Mapping[str, object]] = []
    results: list[Mapping[str, object]] = []
    request_terminals: list[Mapping[str, object]] = []
    for event in events:
        if type(event) is not dict or type(event.get("details")) is not dict:
            raise ControllerError("driver recovery event is invalid")
        event_name = event.get("event")
        details = event["details"]
        assert isinstance(details, dict)
        if details.get("track") != track:
            continue
        if event_name == "driver_start_intent":
            starts.append(event)
        elif event_name == "driver_result_persisted":
            results.append(event)
        elif event_name == "readiness_cancel_complete":
            output_terminals.append(event)
        elif event_name == "driver_stop_complete":
            stop_terminals.append(event)
        elif event_name == "driver_cleanup_complete":
            process_cleanup_events.append(event)
        elif event_name in {"request_send_complete", "request_send_failed"}:
            request_terminals.append(event)

    if len(starts) > 1:
        raise ControllerError("driver start intent is duplicated")
    identity_events = [
        *starts,
        *results,
        *output_terminals,
        *stop_terminals,
        *process_cleanup_events,
    ]
    if any(
        event["details"].get("driver_id") != driver_id
        for event in identity_events
    ):
        raise ControllerError("driver recovery identity changed")
    if not starts:
        if results or output_terminals or stop_terminals or process_cleanup_events:
            raise ControllerError("driver terminal event lacks its start intent")
        return {
            "phase": "pre_start",
            "allowed_states": ("created",),
            "request_eligible": True,
            "terminal_source": None,
        }

    readiness_nonce = starts[0]["details"].get("readiness_nonce")
    _require_sha256("driver recovery readiness nonce", readiness_nonce)
    if any(
        event["details"].get("readiness_nonce") != readiness_nonce
        for event in identity_events
    ):
        raise ControllerError("driver recovery readiness identity changed")

    if len(results) > 1 or len(output_terminals) > 1:
        raise ControllerError("driver terminal evidence is duplicated")
    result_terminal = False
    terminal_event: Mapping[str, object] | None = None
    if results:
        result = results[0]
        result_sequence = result.get("sequence")
        result_intent = result["details"].get("intent_id")
        terminal_event = next(
            (
                event
                for event in request_terminals
                if type(event.get("sequence")) is int
                and type(result_sequence) is int
                and event["sequence"] > result_sequence
            ),
            None,
        )
        result_terminal = (
            terminal_event is not None
            and type(result_intent) is str
            and _HEX.fullmatch(result_intent) is not None
            and (
                terminal_event["event"] == "request_send_complete"
                or (
                    terminal_event["event"] == "request_send_failed"
                    and type(terminal_event["details"].get("provenance")) is dict
                    and terminal_event["details"]["provenance"].get(
                        "provenance_source"
                    )
                    == "linux_request_driver"
                    and terminal_event["details"]["provenance"].get(
                        "driver_full_id"
                    )
                    == driver_id
                    and terminal_event["details"]["provenance"].get(
                        "driver_result_sha256"
                    )
                    == result["details"].get("result_sha256")
                )
            )
        )
    if result_terminal:
        return {
            "phase": "trusted_terminal",
            "allowed_states": ("dead", "exited"),
            "request_eligible": True,
            "terminal_source": "bound_driver_result",
        }
    if output_terminals:
        return {
            "phase": "trusted_terminal",
            "allowed_states": ("dead", "exited"),
            "request_eligible": False,
            "terminal_source": str(output_terminals[0]["event"]),
        }
    if stop_terminals:
        return {
            "phase": "teardown_quiesced",
            "allowed_states": ("created", "dead", "exited"),
            "request_eligible": False,
            "terminal_source": str(stop_terminals[-1]["event"]),
        }
    return {
        "phase": "ambiguous",
        "allowed_states": ("created", "dead", "exited", "running"),
        "request_eligible": False,
        "terminal_source": None,
    }


def _driver_stop_transition(
    events: Sequence[Mapping[str, object]],
    track: str,
    driver_id: str,
) -> str:
    """Replay the latest exact driver stop attempt without duplicating intent."""
    _driver_recovery_authority(events, track, driver_id)
    transition = "unstarted"
    for event in events:
        if type(event) is not dict or type(event.get("details")) is not dict:
            raise ControllerError("driver stop history is invalid")
        event_name = event.get("event")
        if event_name not in {
            "driver_stop_intent",
            "driver_stop_complete",
            "driver_stop_failed",
        }:
            continue
        details = event["details"]
        assert isinstance(details, dict)
        if details.get("track") != track:
            continue
        if details.get("driver_id") != driver_id:
            raise ControllerError("driver stop identity changed")
        if event_name == "driver_stop_intent":
            if transition not in {"unstarted", "failed"}:
                raise ControllerError("driver stop intent is duplicated")
            transition = "pending"
        elif event_name == "driver_stop_complete":
            if transition != "pending":
                raise ControllerError("driver stop completion lacks its intent")
            transition = "complete"
        else:
            if transition != "pending":
                raise ControllerError("driver stop failure lacks its intent")
            transition = "failed"
    return transition


def _container_stop_transition(
    events: Sequence[Mapping[str, object]],
    identity: Mapping[str, object],
) -> str:
    """Replay one exact service or validator stop without duplicating intent."""
    if type(identity) is not dict or set(identity) != {"id", "name", "role"}:
        raise ControllerError("container stop identity is not closed")
    role = identity["role"]
    if type(role) is not str or role not in {
        "envoy", "authz", "target", "validator"
    }:
        raise ControllerError("container stop role is invalid")
    try:
        expected = DockerInventoryEntry.from_mapping(
            {"id": identity["id"], "name": identity["name"]},
            "container",
            schema_version=DRIVER_TOPOLOGY_SCHEMA_VERSION,
        )
    except HarnessContractError as error:
        raise ControllerError("container stop identity is invalid") from error
    creation_kind = "validator" if role == "validator" else "container"
    creation, created_id = _creation_transition(
        events, creation_kind, expected.name
    )
    if creation != "complete" or created_id != expected.object_id:
        raise ControllerError("container stop lacks its exact created identity")
    transition = "unstarted"
    for event in events:
        if type(event) is not dict or event.get("event") not in {
            "container_stop_intent", "container_stop_complete"
        }:
            continue
        details = event.get("details")
        if type(details) is not dict:
            raise ControllerError("container stop history is invalid")
        observed_id = details.get("id")
        observed_name = details.get("name")
        if observed_id != expected.object_id and observed_name != expected.name:
            continue
        if observed_id != expected.object_id or observed_name != expected.name:
            raise ControllerError("container stop identity changed")
        if event["event"] == "container_stop_intent":
            if set(details) != {"id", "name", "role"} or details.get("role") != role:
                raise ControllerError("container stop intent identity changed")
            if transition != "unstarted":
                raise ControllerError("container stop intent is duplicated")
            transition = "pending"
        else:
            if set(details) != {"id", "name"}:
                raise ControllerError("container stop completion identity changed")
            if transition != "pending":
                raise ControllerError("container stop completion lacks its intent")
            transition = "complete"
    return transition


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
    schema_version: str = LEGACY_JOURNAL_SCHEMA,
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
    if schema_version not in {LEGACY_JOURNAL_SCHEMA, JOURNAL_SCHEMA}:
        raise ControllerError("journal schema version is invalid")
    private.mkdir(parents=True, exist_ok=True)
    os.chmod(private, 0o700)
    value: dict[str, object] = {
        "schema_version": schema_version,
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
    if set(value) != expected or value["schema_version"] not in {
        LEGACY_JOURNAL_SCHEMA, JOURNAL_SCHEMA
    }:
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
    _validate_lifecycle_history(events, requests, str(value["schema_version"]))
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
    _validate_lifecycle_history(events, requests, str(value["schema_version"]))
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


_DRIVER_CONTROL_STAGES = {
    "instruction_write",
    "stdout_read",
    "process_wait",
    "termination",
}
_DRIVER_WAIT_FAILURE_CATEGORIES = {
    "clock_failure",
    "deadline_expired",
    "process_wait",
    "process_wait_timeout",
}


def _driver_control_failure_stage(stage: str, error: Exception) -> str:
    if stage != "process_wait":
        return stage
    if (
        isinstance(error, DriverTransportError)
        and error.category not in _DRIVER_WAIT_FAILURE_CATEGORIES
    ):
        return "termination"
    return "process_wait"


def _validate_driver_control_provenance(value: object) -> dict[str, object]:
    expected = {
        "attempt_count",
        "failure_monotonic_ns",
        "request_bytes_may_have_been_sent",
        "retry_performed",
        "stage",
    }
    if type(value) is not dict or set(value) != expected:
        raise ControllerError("driver-control failure provenance is not closed")
    if (
        value["stage"] not in _DRIVER_CONTROL_STAGES
        or type(value["failure_monotonic_ns"]) is not int
        or value["failure_monotonic_ns"] < 0
        or type(value["request_bytes_may_have_been_sent"]) is not bool
        or value["attempt_count"] != 1
        or value["retry_performed"] is not False
        or (
            value["stage"] != "instruction_write"
            and value["request_bytes_may_have_been_sent"] is not True
        )
    ):
        raise ControllerError("driver-control failure provenance is invalid")
    return value


def _validate_driver_transport_provenance(
    value: object,
) -> dict[str, object]:
    expected = {
        "attempt_count",
        "connect_monotonic_ns",
        "driver_definition_sha256",
        "driver_full_id",
        "driver_request_bytes_may_have_been_sent",
        "driver_result_schema_version",
        "driver_result_sha256",
        "driver_status",
        "errno",
        "errno_name",
        "exception_class",
        "failure_monotonic_ns",
        "provenance_source",
        "request_bytes_may_have_been_sent",
        "retry_performed",
        "send_monotonic_ns",
        "stage",
        "track",
    }
    if type(value) is not dict or set(value) != expected:
        raise ControllerError("driver transport provenance is not closed")
    if (
        value["provenance_source"] != "linux_request_driver"
        or value["driver_result_schema_version"]
        != "kil.v3b1-driver-result.v1"
        or value["driver_status"] != "transport_failure"
        or value["request_bytes_may_have_been_sent"] is not True
    ):
        raise ControllerError("driver transport provenance source is invalid")
    _require_sha256("driver transport full ID", value["driver_full_id"])
    _require_sha256(
        "driver transport definition", value["driver_definition_sha256"]
    )
    _require_sha256("driver transport result", value["driver_result_sha256"])
    source_result = {
        "attempt_count": value["attempt_count"],
        "connect_monotonic_ns": value["connect_monotonic_ns"],
        "errno": value["errno"],
        "errno_name": value["errno_name"],
        "exception_class": value["exception_class"],
        "failure_monotonic_ns": value["failure_monotonic_ns"],
        "request_bytes_may_have_been_sent": value[
            "driver_request_bytes_may_have_been_sent"
        ],
        "retry_performed": value["retry_performed"],
        "schema_version": value["driver_result_schema_version"],
        "send_monotonic_ns": value["send_monotonic_ns"],
        "stage": value["stage"],
        "status": value["driver_status"],
        "track": value["track"],
    }
    try:
        parsed = parse_driver_result(
            canonical_record(source_result),
            expected_track=str(value["track"]),
        )
    except (DriverProtocolError, TypeError, ValueError):
        raise ControllerError("driver transport provenance is invalid") from None
    number = parsed["errno"]
    name = parsed["errno_name"]
    if number is not None and LINUX_ERRNO_NAMES.get(number) != name:
        raise ControllerError("driver transport provenance errno is invalid")
    if _digest_bytes(canonical_record(source_result)) != value[
        "driver_result_sha256"
    ]:
        raise ControllerError(
            "driver transport provenance lacks exact result binding"
        )
    return value


def _validate_request_failure_provenance(
    value: object,
) -> dict[str, object]:
    if type(value) is dict and value.get("provenance_source") is not None:
        return _validate_driver_transport_provenance(value)
    return _validate_driver_control_provenance(value)


def _driver_failure_result_from_provenance(
    track: LiveTrack, provenance: object
) -> dict[str, object]:
    """Reconstruct the one canonical terminal result bound by journal provenance."""
    if not isinstance(track, LiveTrack):
        raise ControllerError("driver failure track is invalid")
    validated = _validate_request_failure_provenance(provenance)
    if validated.get("provenance_source") == "linux_request_driver":
        if validated["track"] != track.value:
            raise ControllerError("driver failure provenance track is invalid")
        result = {
            "attempt_count": validated["attempt_count"],
            "connect_monotonic_ns": validated["connect_monotonic_ns"],
            "errno": validated["errno"],
            "errno_name": validated["errno_name"],
            "exception_class": validated["exception_class"],
            "failure_monotonic_ns": validated["failure_monotonic_ns"],
            "request_bytes_may_have_been_sent": validated[
                "driver_request_bytes_may_have_been_sent"
            ],
            "retry_performed": validated["retry_performed"],
            "schema_version": validated["driver_result_schema_version"],
            "send_monotonic_ns": validated["send_monotonic_ns"],
            "stage": validated["stage"],
            "status": validated["driver_status"],
            "track": track.value,
        }
    else:
        result = {
            "attempt_count": validated["attempt_count"],
            "failure_monotonic_ns": validated["failure_monotonic_ns"],
            "request_bytes_may_have_been_sent": validated[
                "request_bytes_may_have_been_sent"
            ],
            "retry_performed": validated["retry_performed"],
            "schema_version": "kil.v3b1-driver-result.v1",
            "stage": validated["stage"],
            "status": "driver_control_failure",
            "track": track.value,
        }
    payload = canonical_record(result)
    try:
        parsed = parse_driver_result(payload, expected_track=track.value)
    except (DriverProtocolError, TypeError, ValueError, UnicodeError) as error:
        raise ControllerError(
            "driver failure provenance cannot reconstruct a closed result"
        ) from error
    if parsed != result:
        raise ControllerError("driver failure result reconstruction is unstable")
    return result


def _driver_failure_journal_details(
    track: LiveTrack,
    intent_id: str,
    provenance: Mapping[str, object],
) -> dict[str, object]:
    _require_sha256("driver failure request intent", intent_id)
    _driver_failure_result_from_provenance(track, provenance)
    return {
        "track": track.value,
        "record_sha256": None,
        "intent_id": intent_id,
        "provenance": dict(provenance),
    }


def _complete_request_attempt(
    journal_path: Path,
    track: LiveTrack,
    *,
    success: bool,
    record_sha256: str | None,
    failure_provenance: RequestFailureProvenance | Mapping[str, object] | None = None,
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
    if failure_provenance is not None:
        if isinstance(failure_provenance, RequestFailureProvenance):
            provenance_mapping = failure_provenance.to_mapping()
        else:
            provenance_mapping = _validate_request_failure_provenance(
                failure_provenance
            )
    else:
        provenance_mapping = None
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
                "provenance": provenance_mapping,
            }
        )
    events.append(
        {"sequence": len(events) + 1, "event": event, "details": details}
    )
    _validate_lifecycle_history(events, requests, str(value["schema_version"]))
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
        events,
        value["requests"],  # type: ignore[arg-type]
        str(value["schema_version"]),
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
    _validate_lifecycle_history(events, requests, str(value["schema_version"]))
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


_EXPANDED_HEALTHCHECK_FIELDS = frozenset(
    {"Test", "Interval", "Timeout", "StartPeriod", "Retries"}
)


def _classify_inspected_healthcheck(
    actual: object, immutable: object
) -> str | None:
    """Classify only closed Docker healthcheck representations as disabled."""
    if actual is None:
        return None
    if type(actual) is not dict:
        return "configured"

    # Docker 29.7.2 retains the immutable image timing/retry fields when
    # replacing only Test with NONE. Bind every retained scalar, including its
    # exact JSON type, to the already-inspected immutable image definition.
    if (
        set(actual) != _EXPANDED_HEALTHCHECK_FIELDS
        or actual.get("Test") != ["NONE"]
        or type(immutable) is not dict
        or set(immutable) != _EXPANDED_HEALTHCHECK_FIELDS
    ):
        return "configured"
    immutable_test = immutable.get("Test")
    if (
        type(immutable_test) is not list
        or len(immutable_test) < 2
        or any(type(item) is not str or not item for item in immutable_test)
        or immutable_test[0] not in {"CMD", "CMD-SHELL"}
    ):
        return "configured"
    scalar_constraints = {
        "Interval": lambda value: value > 0,
        "Timeout": lambda value: value > 0,
        "StartPeriod": lambda value: value >= 0,
        "Retries": lambda value: value > 0,
    }
    for field, valid in scalar_constraints.items():
        actual_value = actual[field]
        immutable_value = immutable[field]
        if (
            type(actual_value) is not int
            or type(immutable_value) is not int
            or not valid(immutable_value)
            or actual_value != immutable_value
        ):
            return "configured"
    return "disabled"


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
        "cgroupns_mode",
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
    if actual["cgroupns_mode"] != "private":
        raise ControllerError("container cgroup namespace mode is not private")
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
        allowed = set(required) | {str(expected["name"]), str(actual["id"])[:12]}
        if (
            type(values) is not list
            or any(type(value) is not str or not value for value in values)
            or len(values) != len(set(values))
            or type(required) is not list
            or any(type(value) is not str or not value for value in required)
            or not set(required).issubset(values)
            or not set(values).issubset(allowed)
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
        expected_entrypoint = ["python"]
        expected_command = [
            "-c", _AUTHZ_BOOTSTRAP, "--config", "/config/authz.json",
        ]
    elif role == "target":
        expected_entrypoint = ["python"]
        expected_command = [
            "-c", _TARGET_BOOTSTRAP, "--config", "/config/target.json",
        ]
    elif role == "envoy":
        expected_entrypoint = ["/usr/local/bin/envoy"]
        expected_command = [
            "--config-path", "/etc/envoy/envoy.json", "--disable-hot-restart",
            "--concurrency", "1",
        ]
    else:
        expected_entrypoint = ["python"]
        expected_command = [
            "-m", "kil.v3b1_request_driver", "--track",
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
            or expected["required_state"]
            not in {"created", "running", "exited", "dead"}
            or actual["state"] != expected["required_state"]
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
    allowed_driver_states: set[str] | frozenset[str] | None = None,
) -> bool:
    """Compare an owned container while totalizing a controlled service stop."""
    if current == recorded:
        if (
            type(recorded) is dict
            and recorded.get("role") == "driver"
            and allowed_driver_states is not None
        ):
            runtime = recorded.get("runtime_attestation")
            return (
                type(allowed_driver_states) in {set, frozenset}
                and bool(allowed_driver_states)
                and allowed_driver_states.issubset(
                    {"created", "running", "exited", "dead"}
                )
                and type(runtime) is dict
                and runtime.get("state") in allowed_driver_states
            )
        return True
    if (
        allow_stopped
        and type(recorded) is dict
        and type(current) is dict
        and set(recorded) == set(current)
        and recorded.get("role") == "driver"
        and type(allowed_driver_states) in {set, frozenset}
        and bool(allowed_driver_states)
        and allowed_driver_states.issubset({"created", "running", "exited", "dead"})
    ):
        recorded_runtime = recorded.get("runtime_attestation")
        current_runtime = current.get("runtime_attestation")
        if (
            type(recorded_runtime) is dict
            and type(current_runtime) is dict
            and set(recorded_runtime) == set(current_runtime)
            and recorded_runtime.get("state")
            in {"created", "running", "exited", "dead"}
            and current_runtime.get("state") in allowed_driver_states
            and {
                key: value
                for key, value in recorded.items()
                if key != "runtime_attestation"
            }
            == {
                key: value
                for key, value in current.items()
                if key != "runtime_attestation"
            }
            and {
                key: value
                for key, value in recorded_runtime.items()
                if key != "state"
            }
            == {
                key: value
                for key, value in current_runtime.items()
                if key != "state"
            }
        ):
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
    recorded_without_state = {
        key: value for key, value in recorded_runtime.items() if key != "state"
    }
    current_without_state = {
        key: value for key, value in current_runtime.items() if key != "state"
    }
    if recorded_without_state == current_without_state:
        return True
    recorded_ports = recorded_runtime.get("published_ports")
    current_ports = current_runtime.get("published_ports")
    service_ports = {
        "authz": {"8080/tcp": None},
        "target": {"8080/tcp": None},
        "envoy": {"10000/tcp": None},
    }
    role = recorded.get("role")
    if type(role) is not str or role not in service_ports:
        return False
    unbound_ports_before_stop = service_ports[role]
    if (
        recorded_ports != unbound_ports_before_stop
        or current_ports != {}
    ):
        return False
    return {
        key: value
        for key, value in recorded_runtime.items()
        if key not in {"state", "published_ports"}
    } == {
        key: value
        for key, value in current_runtime.items()
        if key not in {"state", "published_ports"}
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


FOREIGN_SNAPSHOT_SCHEMA = "kil.v3b1-foreign-profile-snapshot.v1"
FOREIGN_ATTESTATION_SCHEMA = "kil.v3b1-foreign-profile-attestation.v1"
_FOREIGN_CAPTURE_STAGES = {
    "before_colima_mutation",
    "after_owned_profile_deletion",
}
_FOREIGN_PROFILE_FIELDS = {
    "name",
    "status",
    "arch",
    "cpus",
    "memory",
    "disk",
    "runtime",
}
_FOREIGN_RESOURCE_FIELDS = (
    "status",
    "arch",
    "cpus",
    "memory",
    "disk",
    "runtime",
)
_FOREIGN_MISMATCH_CATEGORIES = ("profile_set", *_FOREIGN_RESOURCE_FIELDS)
_FOREIGN_PROFILE_REF_DOMAIN = b"kil.v3b1-foreign-profile-ref.v1\0"


def _closed_foreign_profile(record: Mapping[str, object]) -> dict[str, object]:
    if type(record) is not dict or set(record) != _FOREIGN_PROFILE_FIELDS:
        raise ControllerError("foreign Colima profile fields are not closed")
    if any(
        type(record[name]) is not str or not record[name]
        for name in ("name", "status", "arch", "runtime")
    ) or any(
        type(record[name]) is not int or record[name] <= 0
        for name in ("cpus", "memory", "disk")
    ):
        raise ControllerError("foreign Colima profile values are invalid")
    try:
        for name in ("name", "status", "arch", "runtime"):
            str(record[name]).encode("utf-8")
    except UnicodeEncodeError as error:
        raise ControllerError("foreign Colima profile contains invalid Unicode") from error
    return {name: record[name] for name in (
        "name", "status", "arch", "cpus", "memory", "disk", "runtime"
    )}


def canonical_foreign_profile_snapshot(
    records: Sequence[Mapping[str, object]], capture_stage: str
) -> dict[str, object]:
    """Validate and sort one exact private foreign-profile observation."""
    if capture_stage not in _FOREIGN_CAPTURE_STAGES:
        raise ControllerError("foreign profile capture stage is invalid")
    if type(records) not in (list, tuple):
        raise ControllerError("foreign profile snapshot must be a closed sequence")
    closed = [_closed_foreign_profile(record) for record in records]
    names = [str(record["name"]) for record in closed]
    if len(names) != len(set(names)):
        raise ControllerError("foreign Colima profile names are duplicated")
    foreign = [record for record in closed if record["name"] != LAB_IDENTITY]
    foreign.sort(key=lambda record: str(record["name"]).encode("utf-8"))
    return {
        "schema_version": FOREIGN_SNAPSHOT_SCHEMA,
        "capture_stage": capture_stage,
        "profiles": foreign,
    }


def _validate_foreign_profile_snapshot(
    value: Mapping[str, object], *, capture_stage: str
) -> dict[str, object]:
    if type(value) is not dict or set(value) != {
        "schema_version", "capture_stage", "profiles"
    }:
        raise ControllerError("foreign profile snapshot fields are not closed")
    if (
        value["schema_version"] != FOREIGN_SNAPSHOT_SCHEMA
        or value["capture_stage"] != capture_stage
        or type(value["profiles"]) is not list
    ):
        raise ControllerError("foreign profile snapshot identity is invalid")
    canonical = canonical_foreign_profile_snapshot(
        value["profiles"], capture_stage  # type: ignore[arg-type]
    )
    if canonical != value:
        raise ControllerError("foreign profile snapshot is not canonical")
    return canonical


def project_foreign_profile_snapshot(
    snapshot: Mapping[str, object], execution_nonce: str
) -> list[dict[str, object]]:
    """Replace exact private names with run-scoped HMAC references."""
    if type(snapshot) is not dict or snapshot.get("capture_stage") not in (
        _FOREIGN_CAPTURE_STAGES
    ):
        raise ControllerError("foreign profile snapshot capture stage is invalid")
    capture_stage = str(snapshot["capture_stage"])
    private = _validate_foreign_profile_snapshot(
        snapshot, capture_stage=capture_stage
    )
    nonce = _require_sha256("foreign profile execution nonce", execution_nonce)
    key = bytes.fromhex(nonce)
    projected = []
    for record in private["profiles"]:
        assert isinstance(record, dict)
        name = str(record["name"])
        profile_ref = hmac.new(
            key,
            _FOREIGN_PROFILE_REF_DOMAIN + name.encode("utf-8"),
            sha256,
        ).hexdigest()
        projected.append(
            {
                "profile_ref": profile_ref,
                **{field: record[field] for field in _FOREIGN_RESOURCE_FIELDS},
            }
        )
    references = [str(record["profile_ref"]) for record in projected]
    if len(references) != len(set(references)):
        raise ControllerError("foreign profile references are duplicated")
    projected.sort(key=lambda record: str(record["profile_ref"]))
    return projected


def compare_foreign_profile_snapshots(
    before: Mapping[str, object], after: Mapping[str, object]
) -> dict[str, object]:
    """Return exact equality plus sorted closed mismatch categories."""
    before_value = _validate_foreign_profile_snapshot(
        before, capture_stage="before_colima_mutation"
    )
    after_value = _validate_foreign_profile_snapshot(
        after, capture_stage="after_owned_profile_deletion"
    )
    before_by_name = {
        str(record["name"]): record for record in before_value["profiles"]
    }
    after_by_name = {
        str(record["name"]): record for record in after_value["profiles"]
    }
    if set(before_by_name) != set(after_by_name):
        categories = ["profile_set"]
    else:
        categories = [
            field
            for field in _FOREIGN_RESOURCE_FIELDS
            if any(
                before_by_name[name][field] != after_by_name[name][field]
                for name in sorted(before_by_name)
            )
        ]
    return {
        "unchanged": not categories,
        "mismatch_categories": categories,
    }


def _validate_foreign_profile_attestation(
    value: Mapping[str, object], *, completed: bool
) -> dict[str, object]:
    """Validate one name-free public before/after projection."""
    if type(value) is not dict or set(value) != {
        "schema_version", "before", "after", "unchanged"
    }:
        raise ControllerError("foreign profile attestation fields are not closed")
    if (
        value["schema_version"] != FOREIGN_ATTESTATION_SCHEMA
        or type(value["before"]) is not list
        or type(value["after"]) is not list
        or type(value["unchanged"]) is not bool
    ):
        raise ControllerError("foreign profile attestation identity is invalid")
    expected_fields = {"profile_ref", *_FOREIGN_RESOURCE_FIELDS}
    arrays: list[list[dict[str, object]]] = []
    for label in ("before", "after"):
        records = value[label]
        assert isinstance(records, list)
        closed: list[dict[str, object]] = []
        for record in records:
            if type(record) is not dict or set(record) != expected_fields:
                raise ControllerError(
                    "foreign profile attestation record fields are not closed"
                )
            _require_sha256("foreign profile reference", record["profile_ref"])
            if any(
                type(record[name]) is not str or not record[name]
                for name in ("status", "arch", "runtime")
            ) or any(
                type(record[name]) is not int or record[name] <= 0
                for name in ("cpus", "memory", "disk")
            ):
                raise ControllerError(
                    "foreign profile attestation record values are invalid"
                )
            try:
                for name in ("status", "arch", "runtime"):
                    str(record[name]).encode("utf-8")
            except UnicodeEncodeError as error:
                raise ControllerError(
                    "foreign profile attestation contains invalid Unicode"
                ) from error
            closed.append(dict(record))
        references = [str(record["profile_ref"]) for record in closed]
        if references != sorted(references) or len(references) != len(set(references)):
            raise ControllerError(
                "foreign profile attestation references are unordered or duplicated"
            )
        arrays.append(closed)
    unchanged = arrays[0] == arrays[1]
    if value["unchanged"] is not unchanged:
        raise ControllerError("foreign profile attestation unchanged flag is untruthful")
    if completed and not unchanged:
        raise ControllerError("complete evidence requires unchanged foreign profiles")
    _reject_public_secrets(value)
    return {
        "schema_version": FOREIGN_ATTESTATION_SCHEMA,
        "before": arrays[0],
        "after": arrays[1],
        "unchanged": unchanged,
    }


def _journal_foreign_profile_attestation(
    events: Sequence[Mapping[str, object]], execution_nonce: str
) -> dict[str, object]:
    """Derive the public projection only from the two durable journal records."""
    snapshots: dict[str, Mapping[str, object]] = {}
    for event_name, stage in (
        ("foreign_profile_snapshot_before", "before_colima_mutation"),
        ("foreign_profile_snapshot_after", "after_owned_profile_deletion"),
    ):
        matches = [
            event for event in events if event.get("event") == event_name
        ]
        if len(matches) != 1 or type(matches[0].get("details")) is not dict:
            raise ControllerError(
                "foreign profile journal snapshots are incomplete or duplicated"
            )
        snapshots[event_name] = _validate_foreign_profile_snapshot(
            matches[0]["details"],  # type: ignore[arg-type]
            capture_stage=stage,
        )
    before = snapshots["foreign_profile_snapshot_before"]
    after = snapshots["foreign_profile_snapshot_after"]
    comparison = compare_foreign_profile_snapshots(before, after)
    attestation = {
        "schema_version": FOREIGN_ATTESTATION_SCHEMA,
        "before": project_foreign_profile_snapshot(before, execution_nonce),
        "after": project_foreign_profile_snapshot(after, execution_nonce),
        "unchanged": comparison["unchanged"],
    }
    return _validate_foreign_profile_attestation(attestation, completed=False)


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
        value["schema_version"] != DRIVER_MANIFEST_SCHEMA
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
    if schema == DRIVER_MANIFEST_SCHEMA:
        return _validate_manifest_v2(value)
    if schema == MANIFEST_SCHEMA:
        projected = dict(value)
        projected["schema_version"] = DRIVER_MANIFEST_SCHEMA
        _validate_manifest_v2(projected)
        return value
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


def _network_member_identities(
    objects: Sequence[Mapping[str, object]],
    track: str,
    segment: str,
) -> dict[str, dict[str, str]]:
    """Project exact full-ID/name/role ownership for one network segment."""
    roles = (
        {"envoy", "authz", "target"}
        if segment == "backend"
        else {"envoy", "driver"}
        if segment == "frontend"
        else None
    )
    if roles is None:
        raise ControllerError("network member segment is invalid")
    result: dict[str, dict[str, str]] = {}
    names: set[str] = set()
    for item in objects:
        if item.get("track") != track or item.get("role") not in roles:
            continue
        object_id = item.get("id")
        name = item.get("name")
        role = item.get("role")
        if (
            type(object_id) is not str
            or _HEX.fullmatch(object_id) is None
            or type(name) is not str
            or not name
            or type(role) is not str
            or object_id in result
            or name in names
        ):
            raise ControllerError("network member ownership is invalid")
        result[object_id] = {"name": name, "role": role}
        names.add(name)
    return result


def _envoy_attachment_expectations(
    events: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    """Replay each Envoy/frontend attachment from exact durable identities."""
    expectations: dict[str, dict[str, object]] = {}
    by_container_name: dict[str, str] = {}
    by_network_name: dict[str, str] = {}
    for track in _TRACKS:
        track_value = _track_manifest(manifest, track)
        container_name = str(track_value["envoy_container"])
        network_name = str(track_value["frontend_network"])
        expectations[track.value] = {
            "track": track.value,
            "phase": "unstarted",
            "container_id": None,
            "container_name": container_name,
            "network_id": None,
            "network_name": network_name,
            "alias": "envoy",
        }
        by_container_name[container_name] = track.value
        by_network_name[network_name] = track.value
    for event in events:
        if type(event) is not dict:
            raise ControllerError("Envoy attachment history is invalid")
        event_name = event.get("event")
        details = event.get("details")
        if type(details) is not dict:
            raise ControllerError("Envoy attachment history is invalid")
        if event_name == "container_create_complete":
            track = by_container_name.get(str(details.get("name")))
            if track is not None:
                object_id = details.get("id")
                if type(object_id) is not str or _HEX.fullmatch(object_id) is None:
                    raise ControllerError("Envoy attachment container ID is invalid")
                expectations[track]["container_id"] = object_id
        elif event_name == "network_create_complete":
            track = by_network_name.get(str(details.get("name")))
            if track is not None:
                object_id = details.get("id")
                if type(object_id) is not str or _HEX.fullmatch(object_id) is None:
                    raise ControllerError("Envoy attachment network ID is invalid")
                expectations[track]["network_id"] = object_id
        elif event_name in {"network_connect_intent", "network_connect_complete"}:
            container_track = by_container_name.get(
                str(details.get("container_name"))
            )
            network_track = by_network_name.get(str(details.get("network_name")))
            if container_track is None or container_track != network_track:
                raise ControllerError("Envoy attachment crosses track identities")
            expectation = expectations[container_track]
            if (
                details.get("alias") != "envoy"
                or details.get("container_id") != expectation["container_id"]
                or details.get("network_id") != expectation["network_id"]
            ):
                raise ControllerError("Envoy attachment durable identity changed")
            required_phase = (
                "unstarted"
                if event_name == "network_connect_intent"
                else "pending"
            )
            if expectation["phase"] != required_phase:
                raise ControllerError("Envoy attachment phase transition is invalid")
            expectation["phase"] = (
                "pending"
                if event_name == "network_connect_intent"
                else "complete"
            )
    for expectation in expectations.values():
        if expectation["phase"] != "unstarted" and (
            expectation["container_id"] is None
            or expectation["network_id"] is None
        ):
            raise ControllerError("Envoy attachment lacks exact durable identities")
    return expectations


def _validate_envoy_attachment_expectation(
    value: Mapping[str, object],
    manifest: Mapping[str, object],
    track: str,
) -> dict[str, object]:
    fields = {
        "track",
        "phase",
        "container_id",
        "container_name",
        "network_id",
        "network_name",
        "alias",
    }
    if type(value) is not dict or set(value) != fields:
        raise ControllerError("Envoy attachment expectation is not closed")
    track_value = _track_manifest(manifest, LiveTrack(track))
    if (
        value["track"] != track
        or value["phase"] not in {"unstarted", "pending", "complete"}
        or value["container_name"] != track_value["envoy_container"]
        or value["network_name"] != track_value["frontend_network"]
        or value["alias"] != "envoy"
    ):
        raise ControllerError("Envoy attachment expectation identity is invalid")
    for field in ("container_id", "network_id"):
        object_id = value[field]
        if object_id is not None and (
            type(object_id) is not str or _HEX.fullmatch(object_id) is None
        ):
            raise ControllerError("Envoy attachment expectation ID is invalid")
    if value["phase"] != "unstarted" and (
        value["container_id"] is None or value["network_id"] is None
    ):
        raise ControllerError("Envoy attachment expectation lacks its IDs")
    return dict(value)


def _network_member_identity_options(
    objects: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
    track: str,
    segment: str,
    attachment: Mapping[str, object],
) -> tuple[dict[str, dict[str, str]], ...]:
    exact = _network_member_identities(objects, track, segment)
    endpoint_states: dict[str, str] = {}
    for object_id in exact:
        matches = [
            item
            for item in objects
            if item.get("track") == track and item.get("id") == object_id
        ]
        if len(matches) != 1:
            raise ControllerError("network member ownership is invalid")
        runtime_attestation = matches[0].get("runtime_attestation")
        state_error = (
            "frontend driver state is invalid"
            if exact[object_id]["role"] == "driver"
            else "network member state is invalid"
        )
        if type(runtime_attestation) is not dict:
            raise ControllerError(state_error)
        state = runtime_attestation.get("state")
        if type(state) is not str or state not in {
            "created", "running", "exited", "dead"
        }:
            raise ControllerError(state_error)
        endpoint_states[object_id] = state
    physical = {
        object_id: identity
        for object_id, identity in exact.items()
        if endpoint_states[object_id] == "running"
    }
    if segment == "backend":
        return (physical,)
    if segment != "frontend":
        raise ControllerError("network member segment is invalid")
    expectation = _validate_envoy_attachment_expectation(
        attachment, manifest, track
    )
    envoy_ids = [
        object_id
        for object_id, identity in exact.items()
        if identity["role"] == "envoy"
    ]
    if len(envoy_ids) > 1:
        raise ControllerError("frontend Envoy ownership is not unique")
    driver_objects = [
        item
        for item in objects
        if item.get("track") == track
        and item.get("role") == "driver"
    ]
    if len(driver_objects) > 1:
        raise ControllerError("frontend driver ownership is not unique")
    if driver_objects:
        driver = driver_objects[0]
        runtime_attestation = driver.get("runtime_attestation")
        if type(runtime_attestation) is not dict:
            raise ControllerError("frontend driver state is invalid")
        driver_state = runtime_attestation.get("state")
        if type(driver_state) is not str or driver_state not in {
            "created", "running", "exited", "dead"
        }:
            raise ControllerError("frontend driver state is invalid")
    base = {
        object_id: identity
        for object_id, identity in physical.items()
        if identity["role"] != "envoy"
    }
    attached = dict(base)
    if envoy_ids:
        envoy_id = envoy_ids[0]
        if expectation["container_id"] != envoy_id:
            raise ControllerError("frontend Envoy ID is not journal-bound")
        if endpoint_states[envoy_id] == "running":
            attached[envoy_id] = exact[envoy_id]
    phase = expectation["phase"]
    if phase == "unstarted":
        return (base,)
    if phase == "pending" and attached != base:
        return (base, attached)
    return (attached,)


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
        "--cgroupns=private",
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
                "--cgroupns=private",
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
                "--entrypoint",
                "python",
                str(manifest["kil_image_id"]),
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
                "--entrypoint",
                "python",
                str(manifest["kil_image_id"]),
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
                "--cgroupns=private",
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
                "--cgroupns=private",
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
                "--entrypoint",
                "python",
                str(manifest["kil_image_id"]),
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
        "entrypoint": ["/usr/local/bin/envoy"] if role == "envoy" else ["python"],
        "command": (
            [
                "--config-path", "/etc/envoy/envoy.json", "--disable-hot-restart",
                "--concurrency", "1",
            ]
            if role == "envoy"
            else [
                "-m", "kil.v3b1_request_driver", "--track", track,
                "--endpoint", "envoy:8080",
            ]
            if role == "driver"
            else [
                "-c",
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
        "cgroupns_mode": "private",
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


def _closed_teardown_validators(
    validator_objects: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """Validate exact retained validator identities without name discovery."""
    if type(validator_objects) not in {list, tuple} or len(validator_objects) != 3:
        raise ControllerError("exact validator teardown identities are unavailable")
    expected_outer = {
        "id", "name", "role", "track", "labels", "image_id",
        "image_reference", "runtime_attestation",
    }
    expected_runtime = {
        "privileged", "network_mode", "pid_mode", "ipc_mode", "uts_mode",
        "userns_mode", "cgroupns_mode", "state", "entrypoint", "command",
        "mounts", "networks", "port_bindings", "published_ports",
    }
    by_track: dict[str, Mapping[str, object]] = {}
    ids: set[str] = set()
    names: set[str] = set()
    for record in validator_objects:
        if type(record) is not dict or set(record) != expected_outer:
            raise ControllerError("validator teardown identity is not closed")
        track_value = record["track"]
        if type(track_value) is not str:
            raise ControllerError("validator teardown track is invalid")
        try:
            track = LiveTrack(track_value)
        except ValueError as error:
            raise ControllerError("validator teardown track is invalid") from error
        expected_name = (
            f"kil-v3b1-validate-{_track_slug(track)}-"
            f"{str(manifest['content_identity_sha256'])[:12]}"
        )
        object_id = record["id"]
        name = record["name"]
        runtime = record["runtime_attestation"]
        expected_labels = _object_labels(
            str(manifest["run_id"]), "validator", track.value
        )
        if (
            type(object_id) is not str
            or _HEX.fullmatch(object_id) is None
            or object_id in ids
            or name != expected_name
            or name in names
            or record["role"] != "validator"
            or record["labels"] != expected_labels
            or record["image_id"] != manifest["envoy_image_id"]
            or record["image_reference"] != manifest["envoy_image_digest"]
            or type(runtime) is not dict
            or set(runtime) != expected_runtime
        ):
            raise ControllerError("validator teardown identity is invalid")
        mounts = runtime["mounts"]
        published_ports = runtime["published_ports"]
        published_ports_empty = published_ports is None or (
            type(published_ports) is dict
            and all(
                type(port) is str and port and bindings in (None, [])
                for port, bindings in published_ports.items()
            )
        )
        if (
            runtime["privileged"] is not False
            or runtime["network_mode"] != "none"
            or any(
                type(runtime[field]) is not str or runtime[field] != ""
                for field in ("pid_mode", "ipc_mode", "uts_mode", "userns_mode")
            )
            or runtime["cgroupns_mode"] != "private"
            or runtime["state"] != "exited"
            or runtime["entrypoint"] != ["/usr/local/bin/envoy"]
            or runtime["command"] != [
                "--mode", "validate", "--config-path", "/etc/envoy/envoy.json",
                "--disable-hot-restart", "--concurrency", "1",
            ]
            or type(mounts) is not list
            or len(mounts) != 1
            or type(mounts[0]) is not dict
            or set(mounts[0]) != {"source", "destination", "rw"}
            or type(mounts[0]["source"]) is not str
            or not Path(str(mounts[0]["source"])).is_absolute()
            or mounts[0]["destination"] != "/etc/envoy/envoy.json"
            or mounts[0]["rw"] is not False
            or runtime["networks"] != {}
            or runtime["port_bindings"] != {}
            or not published_ports_empty
        ):
            raise ControllerError("validator teardown runtime identity is invalid")
        ids.add(object_id)
        names.add(str(name))
        if track.value in by_track:
            raise ControllerError("validator teardown track is duplicated")
        by_track[track.value] = record
    if set(by_track) != {track.value for track in _TRACKS}:
        raise ControllerError("validator teardown track inventory is incomplete")
    return [by_track[track.value] for track in _TRACKS]


def _closed_teardown_driver_authorities(
    objects: Sequence[Mapping[str, object]],
    authorities: Mapping[str, Mapping[str, object]],
) -> None:
    """Require journal-derived proof that every pure-plan driver is quiescent."""
    drivers = [item for item in objects if item.get("role") == "driver"]
    tracks = {track.value for track in _TRACKS}
    if (
        type(authorities) is not dict
        or set(authorities) != tracks
        or len(drivers) != len(tracks)
    ):
        raise ControllerError("driver teardown authority set is incomplete")
    expected_fields = {
        "phase",
        "allowed_states",
        "request_eligible",
        "terminal_source",
        "driver_id",
        "track",
        "observed_state",
    }
    for driver in drivers:
        track = str(driver.get("track"))
        authority = authorities.get(track)
        if type(authority) is not dict or set(authority) != expected_fields:
            raise ControllerError("driver teardown authority is not closed")
        if (
            authority["track"] != track
            or authority["driver_id"] != driver.get("id")
            or type(authority["allowed_states"]) is not tuple
            or authority["observed_state"] not in authority["allowed_states"]
        ):
            raise ControllerError("driver teardown authority identity changed")
        phase = authority["phase"]
        valid = False
        if phase == "pre_start":
            valid = authority == {
                "phase": "pre_start",
                "allowed_states": ("created",),
                "request_eligible": True,
                "terminal_source": None,
                "driver_id": driver["id"],
                "track": track,
                "observed_state": "created",
            }
        elif phase == "trusted_terminal":
            source = authority["terminal_source"]
            eligible = authority["request_eligible"]
            valid = (
                authority["allowed_states"] == ("dead", "exited")
                and authority["observed_state"] in {"dead", "exited"}
                and (
                    (source == "bound_driver_result" and eligible is True)
                    or (source == "readiness_cancel_complete" and eligible is False)
                )
            )
        elif phase == "teardown_quiesced":
            valid = (
                authority["allowed_states"] == ("created", "dead", "exited")
                and authority["observed_state"] in {"created", "dead", "exited"}
                and authority["request_eligible"] is False
                and authority["terminal_source"] == "driver_stop_complete"
            )
        if not valid:
            raise ControllerError(
                "driver teardown phase does not prove container quiescence"
            )


def teardown_commands(
    state: Mapping[str, object], *,
    validator_objects: Sequence[Mapping[str, object]],
    driver_authorities: Mapping[str, Mapping[str, object]],
    docker_binary: Path,
) -> list[list[str]]:
    """Plan exact cleanup only after journal-authoritative driver quiescence."""
    if state.get("profile_created") is not True:
        raise ControllerError("profile ownership is not proven")
    if state.get("colima_profile") != LAB_IDENTITY:
        raise ControllerError("profile ownership identity is invalid")
    manifest = state.get("manifest")
    if type(manifest) is not dict:
        raise ControllerError("validator teardown manifest is unavailable")
    _validate_state_objects(state, manifest)
    validators = _closed_teardown_validators(validator_objects, manifest)
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
    _closed_teardown_driver_authorities(objects, driver_authorities)
    running = [
        item for role in _TEARDOWN_SERVICE_ROLES
        for item in objects
        if isinstance(item, dict) and item.get("role") == role
    ]
    ordered = [
        item for role in _TEARDOWN_REMOVAL_ROLES
        for item in objects
        if isinstance(item, dict) and item.get("role") == role
    ] + list(validators)
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
    common = {
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
    v2 = {
        "request_transport",
        "driver_role",
        "driver_full_id",
        "driver_image_id",
        "driver_definition_sha256",
        "driver_result_sha256",
    }
    schema = record.get("schema_version")
    expected = common if schema == "kil.v3b1-request.v1" else common | v2
    if set(record) != expected:
        raise ControllerError("request record fields are not closed")
    if schema not in {"kil.v3b1-request.v1", "kil.v3b1-request.v2"}:
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
    if schema == "kil.v3b1-request.v2":
        if (
            record["request_transport"] != "in_network_request_driver"
            or record["driver_role"] != "request_driver"
        ):
            raise ControllerError("request driver transport identity is invalid")
        _require_sha256("request driver full ID", record["driver_full_id"])
        if type(record["driver_image_id"]) is not str or _IMAGE_ID.fullmatch(
            record["driver_image_id"]
        ) is None:
            raise ControllerError("request driver image ID is invalid")
        _require_sha256(
            "request driver definition", record["driver_definition_sha256"]
        )
        _require_sha256("request driver result", record["driver_result_sha256"])


def _driver_failure_request_closed(record: Mapping[str, object]) -> None:
    expected = {
        "schema_version",
        "run_id",
        "request_id",
        "track",
        "request_transport",
        "driver_role",
        "driver_full_id",
        "driver_image_id",
        "driver_definition_sha256",
        "driver_result_sha256",
        "driver_status",
        "intent_id",
        "journal_sequence",
        "journal_event_sha256",
        "failure_provenance",
    }
    if (
        set(record) != expected
        or record.get("schema_version") != "kil.v3b1-request-failure.v1"
        or record.get("request_transport") != "in_network_request_driver"
        or record.get("driver_role") != "request_driver"
        or type(record.get("run_id")) is not str
        or type(record.get("request_id")) is not str
    ):
        raise ControllerError("driver failure request fields are not closed")
    try:
        track = LiveTrack(record["track"])
    except (TypeError, ValueError) as error:
        raise ControllerError("driver failure request track is invalid") from error
    _require_sha256("driver failure full ID", record["driver_full_id"])
    image_id = record["driver_image_id"]
    if type(image_id) is not str or _IMAGE_ID.fullmatch(image_id) is None:
        raise ControllerError("driver failure image ID is invalid")
    _require_sha256(
        "driver failure definition", record["driver_definition_sha256"]
    )
    _require_sha256("driver failure result", record["driver_result_sha256"])
    intent_id = _require_sha256("driver failure intent", record["intent_id"])
    journal_digest = _require_sha256(
        "driver failure journal event", record["journal_event_sha256"]
    )
    journal_sequence = record["journal_sequence"]
    if type(journal_sequence) is not int or journal_sequence < 1:
        raise ControllerError("driver failure journal sequence is invalid")
    provenance = record["failure_provenance"]
    result = _driver_failure_result_from_provenance(track, provenance)
    if record["driver_status"] != result["status"]:
        raise ControllerError("driver failure request status is invalid")
    result_payload = canonical_record(result)
    if record["driver_result_sha256"] != _digest_bytes(result_payload):
        raise ControllerError("driver failure request result binding is invalid")
    assert isinstance(provenance, dict)
    journal_details = _driver_failure_journal_details(
        track, intent_id, provenance
    )
    journal_event = {
        "sequence": journal_sequence,
        "event": "request_send_failed",
        "details": journal_details,
    }
    if journal_digest != _digest_bytes(canonical_record(journal_event)):
        raise ControllerError("driver failure request journal binding is invalid")
    if provenance.get("provenance_source") == "linux_request_driver" and (
        record["driver_full_id"] != provenance["driver_full_id"]
        or record["driver_definition_sha256"]
        != provenance["driver_definition_sha256"]
        or record["driver_result_sha256"] != provenance["driver_result_sha256"]
    ):
        raise ControllerError("driver transport request provenance diverges")
    _reject_public_secrets(dict(record))


def _failure_evidence_request_closed(record: Mapping[str, object]) -> None:
    if record.get("schema_version") == "kil.v3b1-request-failure.v1":
        _driver_failure_request_closed(record)
        return
    _request_closed(record)


def _validate_driver_result_bindings(
    payloads: Mapping[str, bytes],
    manifest: Mapping[str, object],
    requests: Sequence[Mapping[str, object]],
    *,
    completed: bool,
) -> dict[str, dict[str, object]]:
    """Reconstruct exact v2 driver sources and bind their normalized requests."""
    generation = _bundle_generation(manifest.get("schema_version"))
    if generation == 1:
        if any(
            request.get("schema_version") != "kil.v3b1-request.v1"
            for request in requests
        ):
            raise ControllerError("legacy presenter request schema is invalid")
        return {}
    request_by_track = {str(request.get("track")): request for request in requests}
    if len(request_by_track) != len(requests):
        raise ControllerError("driver request track identity is duplicated")
    allowed_request_schemas = {"kil.v3b1-request.v2"}
    if not completed:
        allowed_request_schemas.add("kil.v3b1-request-failure.v1")
    if any(request.get("schema_version") not in allowed_request_schemas for request in requests):
        raise ControllerError("driver presenter request generation is invalid")
    identity = manifest.get("content_identity")
    immutable = manifest.get("immutable_images")
    if type(identity) is not dict:
        raise ControllerError("driver presenter manifest identity is invalid")
    kil_image_id = (
        immutable.get("kil_image_id")
        if type(immutable) is dict
        else manifest.get("kil_image_id")
    )
    definition_values = identity.get("driver_definition_sha256")
    if type(definition_values) is not list:
        raise ControllerError("driver presenter definitions are invalid")
    definition_by_track = {
        str(item.get("track")): item.get("sha256")
        for item in definition_values
        if type(item) is dict
    }
    results: dict[str, dict[str, object]] = {}
    driver_ids: set[str] = set()
    for track in _TRACKS:
        relative = f"raw/drivers/{track.value}.json"
        if relative not in payloads:
            raise ControllerError("driver result artifact set is incomplete")
        payload = payloads[relative]
        request = request_by_track.get(track.value)
        if payload == b"":
            if completed or request is not None:
                raise ControllerError("commanded driver result must not be empty")
            continue
        try:
            result = parse_driver_result(payload, expected_track=track.value)
        except (DriverProtocolError, TypeError, ValueError, UnicodeError) as error:
            raise ControllerError(
                "driver result is not exact canonical public evidence"
            ) from error
        _reject_public_secrets(result)
        if canonical_record(result) != payload:
            raise ControllerError("driver result bytes are not canonical")
        results[track.value] = result
        if request is None:
            raise ControllerError("commanded driver result lacks normalized request")
        request_schema = request.get("schema_version")
        if request_schema == "kil.v3b1-request-failure.v1":
            _driver_failure_request_closed(request)
        else:
            _request_closed(request)
        full_id = request["driver_full_id"]
        if full_id in driver_ids:
            raise ControllerError("driver full ID is reused across tracks")
        driver_ids.add(str(full_id))
        result_digest = _digest_bytes(payload)
        if (
            request["run_id"] != manifest.get("run_id")
            or request["request_id"] != manifest.get("request_id")
            or request["driver_image_id"] != kil_image_id
            or request["driver_definition_sha256"]
            != definition_by_track.get(track.value)
            or request["driver_result_sha256"] != result_digest
        ):
            raise ControllerError("driver request identity or result binding is invalid")
        if request_schema == "kil.v3b1-request-failure.v1":
            expected_result = _driver_failure_result_from_provenance(
                track, request["failure_provenance"]
            )
            if result != expected_result:
                raise ControllerError(
                    "driver failure result does not match journal projection"
                )
        else:
            expected_projection = {
                "attempt_count": request["attempt_count"],
                "decision_digest": request["client_decision_digest"],
                "receive_monotonic_ns": request["receive_monotonic_ns"],
                "response_status": request["client_response_status"],
                "retry_performed": request["retry_observed"],
                "send_monotonic_ns": request["send_monotonic_ns"],
                "status": "complete",
                "track": request["track"],
            }
            if any(
                result.get(name) != value
                for name, value in expected_projection.items()
            ):
                raise ControllerError(
                    "driver result normalized request projection is invalid"
                )
    if completed and set(results) != {track.value for track in _TRACKS}:
        raise ControllerError("accepted bundle requires three driver results")
    return results


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
_PUBLIC_COMMITMENT_SCHEMA_V3 = "kil.v3b1-public-commitment.v3"
_PUBLIC_COMMITMENT_RULE = (
    "sha256_of_canonical_manifest_without_public_commitment_sha256_and_"
    "all_public_file_sha256_except_manifest_and_SHA256SUMS"
)
_LEGACY_PUBLIC_MANIFEST_SCHEMA = "kil.v3b1-public-manifest.v1"
_DRIVER_PUBLIC_MANIFEST_SCHEMA = "kil.v3b1-public-manifest.v2"
_FOREIGN_PUBLIC_MANIFEST_SCHEMA = "kil.v3b1-public-manifest.v3"
_LEGACY_AUTHORITATIVE_BUNDLE_SCHEMA = "kil.v3b1-authoritative-bundle.v1"
_DRIVER_AUTHORITATIVE_BUNDLE_SCHEMA = "kil.v3b1-authoritative-bundle.v2"
_FOREIGN_AUTHORITATIVE_BUNDLE_SCHEMA = "kil.v3b1-authoritative-bundle.v3"


def _bundle_generation(schema_version: object) -> int:
    if schema_version in {
        LEGACY_MANIFEST_SCHEMA,
        _LEGACY_PUBLIC_MANIFEST_SCHEMA,
    }:
        return 1
    if schema_version in {DRIVER_MANIFEST_SCHEMA, _DRIVER_PUBLIC_MANIFEST_SCHEMA}:
        return 2
    if schema_version in {MANIFEST_SCHEMA, _FOREIGN_PUBLIC_MANIFEST_SCHEMA}:
        return 3
    raise ControllerError("evidence manifest schema is invalid")


def _driver_result_file_names() -> set[str]:
    return {f"raw/drivers/{track.value}.json" for track in _TRACKS}


def _authoritative_file_names(schema_version: object) -> set[str]:
    names = {
        *_EVIDENCE_FILES,
        "SHA256SUMS",
        *{f"raw/decisions/{track.value}.jsonl" for track in _TRACKS},
    }
    if _bundle_generation(schema_version) in {2, 3}:
        names.update(_driver_result_file_names())
    return names


def _manifest_schema_from_output(output: Path) -> str:
    path = output / "manifest.json"
    if path.is_symlink() or not path.is_file():
        raise ControllerError("evidence manifest is missing or unsafe")
    value = _load_json_bytes(path.read_bytes(), "evidence manifest")
    schema = value.get("schema_version")
    _bundle_generation(schema)
    assert isinstance(schema, str)
    return schema


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
            run_id,
            request_id,
            evidence_scope,
            source_commit,
            (),
            False,
            _bundle_generation(manifest.get("schema_version")) in {2, 3},
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
        run_id,
        request_id,
        evidence_scope,
        source_commit,
        tuple(tracks),
        True,
        _bundle_generation(manifest.get("schema_version")) in {2, 3},
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
    driver_boundary = ""
    if model.driver_boundary:
        driver_boundary = """
<section class="boundary driver-boundary">
<h2>In-network request path</h2>
<p><strong>request driver -&gt; Envoy -&gt; authorization -&gt; target or withhold</strong></p>
<p>No host publication</p>
<p>The driver is a laboratory transport witness, not KIL enforcement</p>
<p>Evidence scope: local_envoy_boundary</p>
</section>
"""
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
{driver_boundary}<section class="boundary">
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
    schema = _manifest_schema_from_output(output)
    paths = [
        output / relative
        for relative in sorted(
            _authoritative_file_names(schema) - {"SHA256SUMS"}
        )
    ]
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
    raw_decision_names = {f"{track.value}.jsonl" for track in _TRACKS}
    raw_driver_names = {f"{track.value}.json" for track in _TRACKS}
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    root_fd = raw_fd = decisions_fd = drivers_fd = -1
    try:
        try:
            root_fd = os.open(output, directory_flags)
            root_opened = os.fstat(root_fd)
            manifest_payload, manifest_identity = _read_stable_public_file_at(
                root_fd, "manifest.json", maximum_bytes=1024 * 1024
            )
            manifest_value = _load_json_bytes(
                manifest_payload, "public manifest"
            )
            schema = manifest_value.get("schema_version")
            generation = _bundle_generation(schema)
            expected = _authoritative_file_names(schema)
            root_names = set(_EVIDENCE_FILES) | {"SHA256SUMS", "raw"}
            raw_fd = os.open("raw", directory_flags, dir_fd=root_fd)
            raw_opened = os.fstat(raw_fd)
            decisions_fd = os.open(
                "decisions", directory_flags, dir_fd=raw_fd
            )
            decisions_opened = os.fstat(decisions_fd)
            if generation in {2, 3}:
                drivers_fd = os.open(
                    "drivers", directory_flags, dir_fd=raw_fd
                )
                drivers_opened = os.fstat(drivers_fd)
            else:
                drivers_opened = None
        except OSError as error:
            raise ControllerError(
                "public evidence directory component is missing or unsafe"
            ) from error
        directory_stats = [root_opened, raw_opened, decisions_opened]
        if drivers_opened is not None:
            directory_stats.append(drivers_opened)
        if not all(stat.S_ISDIR(item.st_mode) for item in directory_stats):
            raise ControllerError("public evidence component is not a directory")
        root_identity = _snapshot_identity(root_opened)
        raw_identity = _snapshot_identity(raw_opened)
        decisions_identity = _snapshot_identity(decisions_opened)
        drivers_identity = (
            None
            if drivers_opened is None
            else _snapshot_identity(drivers_opened)
        )
        expected_raw_names = {"decisions"} | (
            {"drivers"} if generation in {2, 3} else set()
        )
        if (
            set(os.listdir(root_fd)) != root_names
            or set(os.listdir(raw_fd)) != expected_raw_names
            or set(os.listdir(decisions_fd)) != raw_decision_names
            or generation in {2, 3}
            and set(os.listdir(drivers_fd)) != raw_driver_names
        ):
            raise ControllerError("public evidence artifact set is not closed")
        if raw_identity != _snapshot_identity(
            os.stat("raw", dir_fd=root_fd, follow_symlinks=False)
        ) or decisions_identity != _snapshot_identity(
            os.stat("decisions", dir_fd=raw_fd, follow_symlinks=False)
        ) or generation in {2, 3} and drivers_identity != _snapshot_identity(
            os.stat("drivers", dir_fd=raw_fd, follow_symlinks=False)
        ):
            raise ControllerError("public evidence directory identity is unstable")
        payloads: dict[str, bytes] = {"manifest.json": manifest_payload}
        identities: dict[
            str, tuple[int, str, tuple[int, int, int, int, int]]
        ] = {"manifest.json": (root_fd, "manifest.json", manifest_identity)}
        for relative in sorted(expected):
            if relative == "manifest.json":
                continue
            if relative.startswith("raw/decisions/"):
                directory_fd = decisions_fd
                name = relative.rsplit("/", 1)[1]
            elif relative.startswith("raw/drivers/"):
                directory_fd = drivers_fd
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
            or generation in {2, 3}
            and drivers_identity != _snapshot_identity(os.fstat(drivers_fd))
            or set(os.listdir(root_fd)) != root_names
            or set(os.listdir(raw_fd)) != expected_raw_names
            or set(os.listdir(decisions_fd)) != raw_decision_names
            or generation in {2, 3}
            and set(os.listdir(drivers_fd)) != raw_driver_names
        ):
            raise ControllerError("public evidence inventory changed during snapshot")
        try:
            root_path = os.stat(output, follow_symlinks=False)
            raw_path = os.stat("raw", dir_fd=root_fd, follow_symlinks=False)
            decisions_path = os.stat(
                "decisions", dir_fd=raw_fd, follow_symlinks=False
            )
            drivers_path = (
                None
                if generation == 1
                else os.stat("drivers", dir_fd=raw_fd, follow_symlinks=False)
            )
        except OSError as error:
            raise ControllerError(
                "public evidence directory changed during snapshot"
            ) from error
        if (
            root_identity != _snapshot_identity(root_path)
            or raw_identity != _snapshot_identity(raw_path)
            or decisions_identity != _snapshot_identity(decisions_path)
            or generation in {2, 3}
            and drivers_identity != _snapshot_identity(drivers_path)
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
                or generation in {2, 3}
                and drivers_identity != _snapshot_identity(os.fstat(drivers_fd))
                or set(os.listdir(root_fd)) != root_names
                or set(os.listdir(raw_fd)) != expected_raw_names
                or set(os.listdir(decisions_fd)) != raw_decision_names
                or generation in {2, 3}
                and set(os.listdir(drivers_fd)) != raw_driver_names
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
                ) or generation in {2, 3} and drivers_identity != _snapshot_identity(
                    os.stat("drivers", dir_fd=raw_fd, follow_symlinks=False)
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
        for descriptor in (drivers_fd, decisions_fd, raw_fd, root_fd):
            if descriptor >= 0:
                os.close(descriptor)


def _validate_public_manifest_v1(
    value: Mapping[str, object],
    payloads: Mapping[str, bytes],
    *,
    completed: bool = True,
    file_schema_version: str = _LEGACY_PUBLIC_MANIFEST_SCHEMA,
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
    hash_names = _authoritative_file_names(file_schema_version) - {
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
    _validate_public_manifest_v1(
        projected,
        payloads,
        completed=completed,
        file_schema_version=_DRIVER_PUBLIC_MANIFEST_SCHEMA,
    )
    if value.get("public_commitment_sha256") != _public_commitment_sha256(
        value, payloads
    ):
        raise ControllerError("public commitment does not bind the snapshot")


def _validate_public_manifest_v3(
    value: Mapping[str, object],
    payloads: Mapping[str, bytes],
    *,
    completed: bool = True,
) -> None:
    """Validate driver evidence plus the closed foreign-profile attestation."""
    if type(value) is not dict or value.get("schema_version") != (
        _FOREIGN_PUBLIC_MANIFEST_SCHEMA
    ):
        raise ControllerError("public manifest schema is invalid")
    foreign = value.get("foreign_profile_attestation")
    if type(foreign) is not dict:
        raise ControllerError("public foreign profile attestation is required")
    _validate_foreign_profile_attestation(foreign, completed=completed)
    projected = dict(value)
    projected.pop("foreign_profile_attestation")
    projected["schema_version"] = _DRIVER_PUBLIC_MANIFEST_SCHEMA
    projected["public_commitment_sha256"] = _public_commitment_sha256(
        projected, payloads
    )
    _validate_public_manifest_v2(projected, payloads, completed=completed)
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
    if schema == _FOREIGN_PUBLIC_MANIFEST_SCHEMA:
        _validate_public_manifest_v3(value, payloads, completed=completed)
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
    _validate_driver_result_bindings(
        payloads, manifest, requests, completed=True
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
        _failure_evidence_request_closed,
        allow_empty=True,
    )
    _validate_driver_result_bindings(
        payloads, manifest, requests, completed=False
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


_FAILURE_BUNDLE_REPLACEMENT = "deterministic_empty_failure_v1"


def _public_commitment_sha256(
    manifest: Mapping[str, object], payloads: Mapping[str, bytes]
) -> str:
    """Recompute the non-circular commitment for one public snapshot."""
    file_names = _authoritative_file_names(manifest.get("schema_version")) - {
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
    elif public_schema == _FOREIGN_PUBLIC_MANIFEST_SCHEMA:
        commitment_schema = _PUBLIC_COMMITMENT_SCHEMA_V3
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
        for relative in _authoritative_file_names(manifest.get("schema_version"))
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
    schema = value["schema_version"]
    if schema == _LEGACY_AUTHORITATIVE_BUNDLE_SCHEMA:
        manifest_schema = LEGACY_MANIFEST_SCHEMA
    elif schema == _DRIVER_AUTHORITATIVE_BUNDLE_SCHEMA:
        manifest_schema = DRIVER_MANIFEST_SCHEMA
    elif schema == _FOREIGN_AUTHORITATIVE_BUNDLE_SCHEMA:
        manifest_schema = MANIFEST_SCHEMA
    else:
        raise ControllerError("authoritative bundle attestation schema is invalid")
    hashes = value["file_sha256"]
    if type(hashes) is not dict or set(hashes) != _authoritative_file_names(
        manifest_schema
    ):
        raise ControllerError("authoritative bundle attestation file set is not closed")
    for relative, digest in hashes.items():
        if type(relative) is not str:
            raise ControllerError("authoritative bundle attestation path is invalid")
        _require_sha256("authoritative artifact sha256", digest)
    _require_sha256("authoritative binding_sha256", value["binding_sha256"])
    bound = {
        "schema_version": schema,
        "file_sha256": dict(hashes),
    }
    expected_binding = _digest_bytes(canonical_json(bound).encode("utf-8"))
    if value["binding_sha256"] != expected_binding:
        raise ControllerError("authoritative bundle attestation binding is invalid")
    return {**bound, "binding_sha256": expected_binding}


def authoritative_bundle_attestation(output: Path) -> dict[str, object]:
    """Bind every byte in one closed, checksummed provisional bundle."""
    manifest_schema = _manifest_schema_from_output(output)
    authority_schema = {
        1: _LEGACY_AUTHORITATIVE_BUNDLE_SCHEMA,
        2: _DRIVER_AUTHORITATIVE_BUNDLE_SCHEMA,
        3: _FOREIGN_AUTHORITATIVE_BUNDLE_SCHEMA,
    }[_bundle_generation(manifest_schema)]
    verify_public_checksums(output)
    hashes = {
        relative: _digest_file(output / relative)
        for relative in sorted(_authoritative_file_names(manifest_schema))
    }
    bound: dict[str, object] = {
        "schema_version": authority_schema,
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
    authority_hashes = authority["file_sha256"]
    assert isinstance(authority_hashes, dict)
    if set(authority_hashes) != _authoritative_file_names(
        private_manifest.get("schema_version")
    ):
        raise ControllerError(
            "durable publication authority generation diverges from manifest"
        )
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
    foreign_profile_attestation: Mapping[str, object] | None = None,
    before_completion: Callable[[], None] | None = None,
    publication_complete: Callable[[str], None] | None = None,
    publication_cleanup: Callable[[], None] | None = None,
) -> None:
    """Hold one public snapshot while reattesting semantics and private authority."""
    authority = _validate_authoritative_attestation(authoritative_attestation)
    authority_hashes = authority["file_sha256"]
    assert isinstance(authority_hashes, dict)
    private_schema = private_manifest.get("schema_version")
    private_generation = _bundle_generation(private_schema)
    expected_public_schema = {
        1: _LEGACY_PUBLIC_MANIFEST_SCHEMA,
        2: _DRIVER_PUBLIC_MANIFEST_SCHEMA,
        3: _FOREIGN_PUBLIC_MANIFEST_SCHEMA,
    }[private_generation]
    if private_generation == 3:
        if type(foreign_profile_attestation) is not dict:
            raise ControllerError(
                "v3 recovery requires foreign profile attestation"
            )
        expected_foreign = _validate_foreign_profile_attestation(
            foreign_profile_attestation,
            completed=completed,
        )
    else:
        if foreign_profile_attestation is not None:
            raise ControllerError(
                "legacy recovery rejects foreign profile attestation"
            )
        expected_foreign = None
    expected_authority_names = _authoritative_file_names(private_schema)
    if set(authority_hashes) != expected_authority_names:
        raise ControllerError(
            "recovered publication authority generation is mixed"
        )
    invariant_names = expected_authority_names - {
        "manifest.json",
        "summary.md",
        "SHA256SUMS",
    }

    def validate_snapshot(payloads: dict[str, bytes]) -> None:
        public_manifest = _validate_presenter_snapshot(
            payloads, completed=completed
        )
        if public_manifest.get("schema_version") != expected_public_schema:
            raise ControllerError(
                "recovered public/private manifest generation diverges"
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
        if private_generation == 3 and public_manifest.get(
            "foreign_profile_attestation"
        ) != expected_foreign:
            raise ControllerError(
                "public foreign profile attestation diverges from journal"
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
    manifest = _load_json_bytes(
        (output / "manifest.json").read_bytes(), "provisional manifest"
    )
    schema = manifest.get("schema_version")
    expected = _authoritative_file_names(schema)
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


def _validate_provisional_driver_bindings(
    output: Path, *, completed: bool
) -> None:
    manifest = _load_json_bytes(
        (output / "manifest.json").read_bytes(), "provisional manifest"
    )
    if _bundle_generation(manifest.get("schema_version")) == 1:
        return
    requests = _parse_jsonl_bytes(
        (output / "requests.jsonl").read_bytes(),
        "provisional requests",
        _request_closed if completed else _failure_evidence_request_closed,
        allow_empty=not completed,
    )
    _validate_driver_result_bindings(
        {
            relative: (output / relative).read_bytes()
            for relative in _driver_result_file_names()
        },
        manifest,
        requests,
        completed=completed,
    )


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
    foreign_profile_attestation: Mapping[str, object] | None = None,
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
    private_schema = private_manifest.get("schema_version")
    generation = _bundle_generation(private_schema)
    public_schema = {
        1: _LEGACY_PUBLIC_MANIFEST_SCHEMA,
        2: _DRIVER_PUBLIC_MANIFEST_SCHEMA,
        3: _FOREIGN_PUBLIC_MANIFEST_SCHEMA,
    }[generation]
    private_file_names = _authoritative_file_names(private_schema)
    public_file_names = _authoritative_file_names(public_schema)
    if private_file_names != public_file_names:
        raise ControllerError("private/public evidence generations diverge")
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
    if generation == 3:
        if type(foreign_profile_attestation) is not dict:
            raise ControllerError("v3 publication requires foreign profile attestation")
        foreign_profile_attestation = _validate_foreign_profile_attestation(
            foreign_profile_attestation,
            completed=completed,
        )
    elif foreign_profile_attestation is not None:
        raise ControllerError(
            "legacy publication rejects foreign profile attestation"
        )
    if type(source_attestations) not in (list, tuple):
        raise ControllerError("source attestations must be a sequence")
    _validate_public_provenance(tool_identities, engine_provenance)
    _validate_source_attestations(source_attestations, completed=completed)
    _validate_provisional_tree(provisional, completed=completed)
    authoritative = _reattest_authoritative_bundle(
        provisional, authoritative_attestation
    )
    _validate_provisional_driver_bindings(provisional, completed=completed)
    _validate_source_attestation_bindings(
        provisional, source_attestations, private_manifest
    )
    artifact_hashes = _artifact_hash_map(provisional)
    expected_artifact_names = private_file_names - {
        "manifest.json", "summary.md", "SHA256SUMS",
    }
    if set(artifact_hashes) != expected_artifact_names:
        raise ControllerError("provisional artifact generation is mixed")
    bundle_class = (
        "intermediate_provisional_local_boundary"
        if completed
        else "intermediate_provisional_failure_local_boundary"
    )
    identity = private_manifest["content_identity"]
    assert isinstance(identity, dict)
    public_manifest: dict[str, object] = {
        "schema_version": public_schema,
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
    if generation == 3:
        assert foreign_profile_attestation is not None
        public_manifest["foreign_profile_attestation"] = dict(
            foreign_profile_attestation
        )
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
    _validate_provisional_driver_bindings(staging, completed=completed)
    if publication_fault is not None:
        publication_fault("after_copy", staging)
    staging_manifest = staging / "manifest.json"
    public_summary = _public_summary(public_manifest).encode("utf-8")
    commitment_payloads = {
        relative: (staging / relative).read_bytes()
        for relative in public_file_names
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


_PRIVATE_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


@dataclass(slots=True)
class _PrivateEvidenceTransaction:
    parent_path: Path
    evidence_root: Path
    output: Path
    parent_fd: int
    root_fd: int
    run_fd: int
    parent_identity: tuple[int, int]
    root_identity: tuple[int, int]
    run_identity: tuple[int, int]
    output_existed: bool
    raw_fd: int = -1
    decisions_fd: int = -1
    drivers_fd: int = -1
    raw_identity: tuple[int, int] | None = None
    decisions_identity: tuple[int, int] | None = None
    drivers_identity: tuple[int, int] | None = None

    def close(self) -> None:
        for name in ("drivers_fd", "decisions_fd", "raw_fd", "run_fd", "root_fd", "parent_fd"):
            descriptor = getattr(self, name)
            if descriptor >= 0:
                os.close(descriptor)
                setattr(self, name, -1)


def _private_directory_names(descriptor: int, label: str) -> set[str]:
    try:
        return set(os.listdir(descriptor))
    except OSError as error:
        raise ControllerError(f"{label} inventory is unavailable or unsafe") from error


def _open_or_create_private_directory_at(
    parent_fd: int,
    name: str,
    label: str,
) -> tuple[int, tuple[int, int], bool]:
    if not name or "/" in name or name in {".", ".."}:
        raise ControllerError(f"{label} name is invalid")
    existed = True
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        existed = False
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except OSError as error:
            raise ControllerError(f"{label} could not be safely created") from error
    except OSError as error:
        raise ControllerError(f"{label} is unavailable or unsafe") from error
    else:
        if not stat.S_ISDIR(current.st_mode):
            raise ControllerError(f"{label} is not a safe directory")
    descriptor = -1
    try:
        descriptor = os.open(name, _PRIVATE_DIRECTORY_FLAGS, dir_fd=parent_fd)
        opened = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
        raise ControllerError(f"{label} changed during creation") from error
    identity = _directory_object_identity(opened)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or identity != _directory_object_identity(current)
    ):
        os.close(descriptor)
        raise ControllerError(f"{label} identity is unstable")
    return descriptor, identity, existed


def _prepare_private_evidence_output(
    evidence_root: Path, run_id: str
) -> _PrivateEvidenceTransaction:
    evidence_root = Path(os.path.abspath(evidence_root))
    parent_path = evidence_root.parent
    parent_fd = root_fd = run_fd = -1
    try:
        parent_fd, parent_identity = _open_verified_directory(
            parent_path, "private evidence parent"
        )
        root_fd, root_identity, _ = _open_or_create_private_directory_at(
            parent_fd, evidence_root.name, "private evidence root"
        )
        run_fd, run_identity, output_existed = _open_or_create_private_directory_at(
            root_fd, run_id, "private evidence run directory"
        )
        return _PrivateEvidenceTransaction(
            parent_path,
            evidence_root,
            evidence_root / run_id,
            parent_fd,
            root_fd,
            run_fd,
            parent_identity,
            root_identity,
            run_identity,
            output_existed,
        )
    except BaseException:
        for descriptor in (run_fd, root_fd, parent_fd):
            if descriptor >= 0:
                os.close(descriptor)
        raise


def _prepare_private_evidence_raw_directories(
    transaction: _PrivateEvidenceTransaction, *, include_drivers: bool
) -> None:
    raw_fd = decisions_fd = drivers_fd = -1
    try:
        raw_fd, raw_identity, _ = _open_or_create_private_directory_at(
            transaction.run_fd, "raw", "private evidence raw directory"
        )
        decisions_fd, decisions_identity, _ = _open_or_create_private_directory_at(
            raw_fd, "decisions", "private evidence decision directory"
        )
        if include_drivers:
            drivers_fd, drivers_identity, _ = _open_or_create_private_directory_at(
                raw_fd, "drivers", "private evidence driver directory"
            )
        else:
            drivers_identity = None
        transaction.raw_fd = raw_fd
        transaction.decisions_fd = decisions_fd
        transaction.drivers_fd = drivers_fd
        transaction.raw_identity = raw_identity
        transaction.decisions_identity = decisions_identity
        transaction.drivers_identity = drivers_identity
        raw_fd = decisions_fd = drivers_fd = -1
        expected_raw = {"decisions"} | ({"drivers"} if include_drivers else set())
        if _private_directory_names(
            transaction.raw_fd, "private evidence raw directory"
        ) != expected_raw:
            raise ControllerError("private evidence raw directory is not closed")
        decision_names = {f"{track.value}.jsonl" for track in _TRACKS}
        if not _private_directory_names(
            transaction.decisions_fd, "private evidence decision directory"
        ).issubset(decision_names):
            raise ControllerError("private evidence decision directory is not closed")
        if include_drivers:
            driver_names = {f"{track.value}.json" for track in _TRACKS}
            if not _private_directory_names(
                transaction.drivers_fd, "private evidence driver directory"
            ).issubset(driver_names):
                raise ControllerError("private evidence driver directory is not closed")
    except BaseException:
        for descriptor in (drivers_fd, decisions_fd, raw_fd):
            if descriptor >= 0:
                os.close(descriptor)
        raise


def _require_private_directory_identity_at(
    parent_fd: int,
    name: str,
    descriptor: int,
    identity: tuple[int, int],
    label: str,
) -> None:
    try:
        opened = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as error:
        raise ControllerError(f"{label} changed during evidence transaction") from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or identity != _directory_object_identity(opened)
        or identity != _directory_object_identity(current)
    ):
        raise ControllerError(f"{label} identity changed during evidence transaction")


def _require_private_evidence_tree(transaction: _PrivateEvidenceTransaction) -> None:
    _require_directory_identity(
        transaction.parent_fd,
        transaction.parent_path,
        transaction.parent_identity,
        "private evidence parent",
    )
    _require_private_directory_identity_at(
        transaction.parent_fd,
        transaction.evidence_root.name,
        transaction.root_fd,
        transaction.root_identity,
        "private evidence root",
    )
    _require_private_directory_identity_at(
        transaction.root_fd,
        transaction.output.name,
        transaction.run_fd,
        transaction.run_identity,
        "private evidence run directory",
    )
    if transaction.raw_fd >= 0:
        assert transaction.raw_identity is not None
        assert transaction.decisions_identity is not None
        _require_private_directory_identity_at(
            transaction.run_fd,
            "raw",
            transaction.raw_fd,
            transaction.raw_identity,
            "private evidence raw directory",
        )
        _require_private_directory_identity_at(
            transaction.raw_fd,
            "decisions",
            transaction.decisions_fd,
            transaction.decisions_identity,
            "private evidence decision directory",
        )
    if transaction.drivers_fd >= 0:
        assert transaction.drivers_identity is not None
        _require_private_directory_identity_at(
            transaction.raw_fd,
            "drivers",
            transaction.drivers_fd,
            transaction.drivers_identity,
            "private evidence driver directory",
        )


def _private_file_location(
    transaction: _PrivateEvidenceTransaction, relative: str
) -> tuple[int, str]:
    parts = relative.split("/")
    if len(parts) == 1:
        descriptor = transaction.run_fd
        name = parts[0]
    elif len(parts) == 3 and parts[:2] == ["raw", "decisions"]:
        descriptor = transaction.decisions_fd
        name = parts[2]
    elif len(parts) == 3 and parts[:2] == ["raw", "drivers"]:
        descriptor = transaction.drivers_fd
        name = parts[2]
    else:
        raise ControllerError("private evidence relative path is invalid")
    if descriptor < 0 or not name or name in {".", ".."} or "/" in name:
        raise ControllerError("private evidence file location is unavailable")
    return descriptor, name


def _read_private_file_at(
    directory_fd: int,
    name: str,
    *,
    maximum_bytes: int = 64 * 1024 * 1024,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > maximum_bytes:
            raise ControllerError("private evidence file is not a bounded regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise ControllerError("private evidence file exceeds its byte bound")
        finished = os.fstat(descriptor)
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as error:
        raise ControllerError("private evidence file is missing or unsafe") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    identity = _snapshot_identity(opened)
    if (
        identity != _snapshot_identity(finished)
        or identity != _snapshot_identity(current)
    ):
        raise ControllerError("private evidence file changed during snapshot")
    return b"".join(chunks)


def _private_file_exists_at(directory_fd: int, name: str) -> bool:
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise ControllerError("private evidence file inventory is unsafe") from error
    if not stat.S_ISREG(current.st_mode):
        raise ControllerError("private evidence file inventory is unsafe")
    return True


def _write_private_file_at(
    directory_fd: int,
    name: str,
    payload: bytes,
    mode: int = 0o600,
) -> None:
    if type(payload) is not bytes or not name or "/" in name or name in {".", ".."}:
        raise ControllerError("private evidence leaf write is invalid")
    _private_file_exists_at(directory_fd, name)
    temporary_name: str | None = None
    temporary_fd = -1
    try:
        for _ in range(100):
            candidate = f".{name}.{secrets.token_hex(16)}"
            try:
                temporary_fd = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    mode,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if temporary_name is None or temporary_fd < 0:
            raise ControllerError("private evidence temporary names are exhausted")
        offset = 0
        while offset < len(payload):
            written = os.write(temporary_fd, payload[offset:])
            if written <= 0:
                raise OSError("private evidence write made no progress")
            offset += written
        os.fsync(temporary_fd)
        os.fchmod(temporary_fd, mode)
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = -1
        os.rename(
            temporary_name,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        temporary_name = None
        os.fsync(directory_fd)
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(current.st_mode)
            or stat.S_IMODE(current.st_mode) != mode
            or _read_private_file_at(directory_fd, name) != payload
        ):
            raise ControllerError("private evidence leaf write did not persist exactly")
    except OSError as error:
        raise ControllerError("private evidence leaf write failed safely") from error
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except FileNotFoundError:
                pass


def _write_private_file(
    transaction: _PrivateEvidenceTransaction,
    relative: str,
    payload: bytes,
    mode: int = 0o600,
) -> None:
    descriptor, name = _private_file_location(transaction, relative)
    _write_private_file_at(descriptor, name, payload, mode)


def _private_checksum_payload(
    transaction: _PrivateEvidenceTransaction, schema_version: object
) -> bytes:
    lines = []
    for relative in sorted(
        _authoritative_file_names(schema_version) - {"SHA256SUMS"}
    ):
        descriptor, name = _private_file_location(transaction, relative)
        payload = _read_private_file_at(descriptor, name)
        lines.append(f"{_digest_bytes(payload)}  {relative}\n")
    return "".join(lines).encode("ascii")


def _write_and_verify_private_sums(
    transaction: _PrivateEvidenceTransaction, schema_version: object
) -> None:
    expected = _private_checksum_payload(transaction, schema_version)
    _write_private_file(transaction, "SHA256SUMS", expected, 0o444)
    if _read_private_file_at(transaction.run_fd, "SHA256SUMS") != expected:
        raise ControllerError("private evidence checksum mismatch")


def _require_private_bundle_inventory(
    transaction: _PrivateEvidenceTransaction, schema_version: object
) -> None:
    generation = _bundle_generation(schema_version)
    if _private_directory_names(
        transaction.run_fd, "private evidence run directory"
    ) != set(_EVIDENCE_FILES) | {"SHA256SUMS", "raw"}:
        raise ControllerError("private evidence artifact set is not closed")
    if _private_directory_names(
        transaction.raw_fd, "private evidence raw directory"
    ) != {"decisions"} | ({"drivers"} if generation in {2, 3} else set()):
        raise ControllerError("private evidence raw artifact set is not closed")
    if _private_directory_names(
        transaction.decisions_fd, "private evidence decision directory"
    ) != {f"{track.value}.jsonl" for track in _TRACKS}:
        raise ControllerError("private evidence decision artifact set is not closed")
    if generation in {2, 3} and _private_directory_names(
        transaction.drivers_fd, "private evidence driver directory"
    ) != {f"{track.value}.json" for track in _TRACKS}:
        raise ControllerError("private evidence driver artifact set is not closed")


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
    raw_driver_results: Mapping[LiveTrack, bytes] | None = None,
    resume_attested: bool = False,
    private_evidence_fault: Callable[[str, Path], None] | None = None,
) -> Path:
    """Rebuild the exact public bundle from verified source records."""
    _validate_manifest(manifest)
    generation = _bundle_generation(manifest.get("schema_version"))
    transaction = _prepare_private_evidence_output(
        evidence_root, str(manifest["run_id"])
    )
    try:
        initial_names = _private_directory_names(
            transaction.run_fd, "private evidence run directory"
        )
        if (
            transaction.output_existed
            and initial_names
            and not resume_attested
        ):
            raise ControllerError(
                "evidence run already exists; attested resume required"
            )
        allowed = set(_EVIDENCE_FILES) | {"SHA256SUMS", "raw"}
        unexpected = initial_names - allowed
        if unexpected:
            raise ControllerError(
                f"evidence directory contains unexpected files: {sorted(unexpected)}"
            )
        _prepare_private_evidence_raw_directories(
            transaction, include_drivers=generation in {2, 3}
        )
        if private_evidence_fault is not None:
            private_evidence_fault("after_prepare", transaction.output)
        _require_private_evidence_tree(transaction)
        if raw_decisions is None:
            raw_decisions = {
                track: _jsonl_payload(
                    [
                        record
                        for record in decisions
                        if record.get("track") == track.value
                    ]
                )
                for track in _TRACKS
            }
        if set(raw_decisions) != set(_TRACKS):
            raise ControllerError(
                "raw decision sources must cover the three fixed tracks"
            )
        for track in _TRACKS:
            payload = raw_decisions[track]
            parsed = _parse_jsonl_bytes(
                payload,
                f"raw decisions for {track.value}",
                _decision_closed,
                allow_empty=False,
            )
            if any(record["track"] != track.value for record in parsed):
                raise ControllerError(
                    "raw decision source track does not match fixed file"
                )
            _write_private_file(
                transaction,
                f"raw/decisions/{track.value}.jsonl",
                payload,
                0o444,
            )
        if generation in {2, 3}:
            if (
                type(raw_driver_results) is not dict
                or set(raw_driver_results) != set(_TRACKS)
            ):
                raise ControllerError(
                    "v2 driver results must cover the three fixed tracks"
                )
            driver_payloads: dict[str, bytes] = {}
            for track in _TRACKS:
                payload = raw_driver_results[track]
                if type(payload) is not bytes:
                    raise ControllerError("driver result source must be exact bytes")
                relative = f"raw/drivers/{track.value}.json"
                driver_payloads[relative] = payload
                _write_private_file(transaction, relative, payload, 0o444)
            _validate_driver_result_bindings(
                driver_payloads,
                manifest,
                requests,
                completed=True,
            )
        elif raw_driver_results is not None:
            raise ControllerError("legacy evidence cannot contain driver results")
        normalized_decisions = _normalized_decision_records(manifest, decisions)
        _write_private_file(
            transaction, "requests.jsonl", _jsonl_payload(requests), 0o444
        )
        _write_private_file(
            transaction,
            "decisions.jsonl",
            _jsonl_payload(normalized_decisions),
            0o444,
        )
        _write_private_file(
            transaction, "envoy.jsonl", _jsonl_payload(envoy), 0o444
        )
        _write_private_file(
            transaction, "targets.jsonl", _jsonl_payload(targets), 0o444
        )
        _write_private_file(
            transaction, "joins.jsonl", _jsonl_payload(joins), 0o444
        )
        _write_private_file(
            transaction, "manifest.json", _canonical_bytes(manifest), 0o444
        )
        _write_private_file(
            transaction,
            "summary.md",
            _summary(manifest, joins).encode("utf-8"),
            0o444,
        )
        _write_private_file(
            transaction,
            "live.html",
            _render_live_html(
                _presenter_model(manifest, normalized_decisions, joins)
            ),
            0o444,
        )
        _write_and_verify_private_sums(
            transaction, manifest["schema_version"]
        )
        _require_private_bundle_inventory(
            transaction, manifest["schema_version"]
        )
        _require_private_evidence_tree(transaction)
        return transaction.output
    finally:
        transaction.close()


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
    raw_driver_results: Mapping[LiveTrack, bytes] | None = None,
    envoy: Sequence[Mapping[str, object]] | None = None,
    targets: Sequence[Mapping[str, object]] | None = None,
    reset: bool = False,
    private_evidence_fault: Callable[[str, Path], None] | None = None,
) -> Path:
    """Preserve an incomplete lifecycle without representing it as promotable proof."""
    _validate_manifest(manifest)
    generation = _bundle_generation(manifest.get("schema_version"))
    transaction = _prepare_private_evidence_output(
        provisional_root, str(manifest["run_id"])
    )
    try:
        allowed = set(_EVIDENCE_FILES) | {"SHA256SUMS", "raw"}
        unexpected = _private_directory_names(
            transaction.run_fd, "failure provisional"
        ) - allowed
        if unexpected:
            raise ControllerError("failure provisional contains unexpected files")
        _prepare_private_evidence_raw_directories(
            transaction, include_drivers=generation in {2, 3}
        )
        if private_evidence_fault is not None:
            private_evidence_fault("after_prepare", transaction.output)
        _require_private_evidence_tree(transaction)
        if raw_decisions is not None and set(raw_decisions) != set(_TRACKS):
            raise ControllerError("failure raw decisions do not cover fixed tracks")
        parsed_decisions: list[dict[str, object]] = []
        for track in _TRACKS:
            name = f"{track.value}.jsonl"
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
                _write_private_file_at(
                    transaction.decisions_fd, name, payload, 0o444
                )
            elif reset or not _private_file_exists_at(
                transaction.decisions_fd, name
            ):
                _write_private_file_at(
                    transaction.decisions_fd, name, b"", 0o444
                )
        if generation in {2, 3}:
            if (
                type(raw_driver_results) is not dict
                or set(raw_driver_results) != set(_TRACKS)
            ):
                raise ControllerError(
                    "failure v2 driver results must cover fixed tracks"
                )
            driver_payloads: dict[str, bytes] = {}
            for track in _TRACKS:
                payload = raw_driver_results[track]
                if type(payload) is not bytes:
                    raise ControllerError(
                        "failure driver result must be exact bytes"
                    )
                relative = f"raw/drivers/{track.value}.json"
                driver_payloads[relative] = payload
                _write_private_file(transaction, relative, payload, 0o444)
            _validate_driver_result_bindings(
                driver_payloads,
                manifest,
                requests or [],
                completed=False,
            )
        elif raw_driver_results is not None:
            raise ControllerError(
                "legacy failure evidence cannot contain driver results"
            )
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
            if records is not None:
                _write_private_file_at(
                    transaction.run_fd, name, _jsonl_payload(records), 0o444
                )
            elif reset or not _private_file_exists_at(transaction.run_fd, name):
                _write_private_file_at(transaction.run_fd, name, b"", 0o444)
        _write_private_file(
            transaction, "manifest.json", _canonical_bytes(manifest), 0o444
        )
        _write_private_file(
            transaction,
            "summary.md",
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
        _write_private_file(
            transaction,
            "live.html",
            _render_live_html(_presenter_model(manifest, normalized, [])),
            0o444,
        )
        _write_and_verify_private_sums(
            transaction, manifest["schema_version"]
        )
        _require_private_bundle_inventory(
            transaction, manifest["schema_version"]
        )
        _require_private_evidence_tree(transaction)
        return transaction.output
    finally:
        transaction.close()


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
        driver_process_factory: DriverProcessFactory | None = None,
        monotonic_ns: Callable[[], int] | None = None,
        sleep: Callable[[float], None] | None = None,
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
        self.monotonic_ns = time.monotonic_ns if monotonic_ns is None else monotonic_ns
        self.sleep = time.sleep if sleep is None else sleep
        self.publication_fault = publication_fault
        self.command_env = {
            "HOME": str(self.home),
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": os.environ.get("PATH", os.defpath),
        }
        self.docker_env = {**self.command_env, "DOCKER_BUILDKIT": "0"}
        self.driver_process_factory = (
            SubprocessDriverProcessFactory(
                cwd=self.root,
                env={
                    **self.docker_env,
                    "DOCKER_CONFIG": str(self.docker_config),
                    "DOCKER_HOST": self.docker_host,
                },
            )
            if driver_process_factory is None
            else driver_process_factory
        )

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

    def _capture_foreign_profile_snapshot(
        self, capture_stage: str
    ) -> dict[str, object]:
        listed = self._execute(["colima", "list", "--json"], timeout_s=20)
        profiles = parse_colima_profiles(listed.stdout)
        if any(record.get("name") == LAB_IDENTITY for record in profiles):
            raise ControllerError(
                "dedicated Colima profile is present at foreign snapshot boundary"
            )
        return canonical_foreign_profile_snapshot(profiles, capture_stage)

    def _record_after_foreign_profile_snapshot(
        self,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        journal = load_lifecycle_journal(self.journal_path)
        if journal["schema_version"] != JOURNAL_SCHEMA:
            raise ControllerError("foreign profile snapshots require a v2 journal")
        events = journal["events"]
        assert isinstance(events, list)
        before_events = [
            event
            for event in events
            if event.get("event") == "foreign_profile_snapshot_before"
        ]
        after_events = [
            event
            for event in events
            if event.get("event") == "foreign_profile_snapshot_after"
        ]
        if len(before_events) != 1 or len(after_events) > 1:
            raise ControllerError("foreign profile snapshot history is incomplete")
        absence_verified = any(
            event.get("event") == "colima_delete_complete"
            and type(event.get("details")) is dict
            and event["details"].get("verified_absent") is True
            for event in events
        ) or any(
            event.get("event") == "down_complete_without_owned_profile"
            and type(event.get("details")) is dict
            and event["details"].get("profile_absent") is True
            for event in events
        )
        if not absence_verified:
            raise ControllerError(
                "foreign profile after snapshot requires verified owned-profile deletion"
            )
        before_details = before_events[0]["details"]
        assert isinstance(before_details, Mapping)
        before = _validate_foreign_profile_snapshot(
            before_details, capture_stage="before_colima_mutation"
        )
        if after_events:
            after_details = after_events[0]["details"]
            assert isinstance(after_details, Mapping)
            after = _validate_foreign_profile_snapshot(
                after_details, capture_stage="after_owned_profile_deletion"
            )
        else:
            after = self._capture_foreign_profile_snapshot(
                "after_owned_profile_deletion"
            )
            journal_event(
                self.journal_path,
                "foreign_profile_snapshot_after",
                after,
            )
        comparison = compare_foreign_profile_snapshots(before, after)
        if comparison["unchanged"] is not True:
            current = load_lifecycle_journal(self.journal_path)
            current_events = current["events"]
            assert isinstance(current_events, list)
            mismatches = [
                event
                for event in current_events
                if event.get("event") == "foreign_profile_mismatch"
            ]
            details = {
                "before_sha256": _digest_bytes(
                    canonical_json(before).encode("utf-8")
                ),
                "after_sha256": _digest_bytes(
                    canonical_json(after).encode("utf-8")
                ),
                "mismatch_categories": comparison["mismatch_categories"],
            }
            if mismatches:
                if len(mismatches) != 1 or mismatches[0].get("details") != details:
                    raise ControllerError("foreign profile mismatch history changed")
            else:
                journal_event(
                    self.journal_path,
                    "foreign_profile_mismatch",
                    details,
                )
        return before, after, comparison

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
        if value["reason_category"] not in {
            "connection_close_ambiguous",
            "driver_readiness_failed",
        }:
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
        journal = load_lifecycle_journal(self.journal_path)
        events = journal["events"]
        assert isinstance(events, list)
        if _readiness_history_blocks_new_session(events):
            raise ControllerError(
                "readiness lifecycle is incomplete or poisoned; down is required"
            )

    def _persist_readiness_poison_independent(
        self,
        *,
        execution_nonce: str,
        readiness_nonce: str,
        reason_category: str,
    ) -> None:
        """Persist the poison sentinel without depending on later journal writes."""
        _require_sha256("readiness poison execution nonce", execution_nonce)
        _require_sha256("readiness poison readiness nonce", readiness_nonce)
        if reason_category not in {
            "connection_close_ambiguous",
            "driver_readiness_failed",
        }:
            raise ControllerError("readiness poison reason category is invalid")
        unsigned = {
            "schema_version": READINESS_POISON_SCHEMA,
            "execution_nonce": execution_nonce,
            "readiness_nonce": readiness_nonce,
            "reason_category": reason_category,
        }
        value = {**unsigned, "binding_sha256": _journal_binding(unsigned)}
        expected = _canonical_bytes(value)
        path = self.readiness_poison_path
        _require_contained(path, self.private_root, "readiness poison sentinel")
        if path.exists():
            if (
                path.is_symlink()
                or not path.is_file()
                or (path.stat().st_mode & 0o7777) != 0o600
                or path.read_bytes() != expected
            ):
                raise ControllerError("readiness poison sentinel would be clobbered")
            return
        _write_file(path, expected, 0o600)
        if (
            path.is_symlink()
            or not path.is_file()
            or (path.stat().st_mode & 0o7777) != 0o600
            or path.read_bytes() != expected
        ):
            raise ControllerError("readiness poison sentinel write was not durable")

    def _persist_readiness_poison(
        self,
        *,
        readiness_nonce: str,
        reason_category: str,
    ) -> None:
        _require_sha256("readiness poison readiness nonce", readiness_nonce)
        if reason_category not in {
            "connection_close_ambiguous",
            "driver_readiness_failed",
        }:
            raise ControllerError("readiness poison reason category is invalid")
        journal = load_lifecycle_journal(self.journal_path)
        events = journal["events"]
        assert isinstance(events, list)
        current_readiness, _ = _validate_lifecycle_history(
            events,
            journal["requests"],  # type: ignore[arg-type]
            str(journal["schema_version"]),
        )
        if current_readiness != readiness_nonce:
            raise ControllerError("readiness poison session is not current")
        self._persist_readiness_poison_independent(
            execution_nonce=str(journal["execution_nonce"]),
            readiness_nonce=readiness_nonce,
            reason_category=reason_category,
        )
        if self._load_readiness_poison() is None:
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
        envoy_attachment: Mapping[str, object] | None = None,
        allowed_driver_states: set[str] | frozenset[str] | None = None,
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
            assert type(config_value) is dict
            assert type(host) is dict
            assert type(state_value) is dict
            assert type(network_settings) is dict
            assert type(mounts_value) is list
            assert all(type(item) is dict for item in mounts_value)
            image_reference = config_value["Image"]
            labels = config_value["Labels"]
            entrypoint = config_value["Entrypoint"]
            command = config_value["Cmd"]
            running_value = state_value["Running"]
            state_status = state_value["Status"]
            raw_networks = network_settings["Networks"]
            published_ports = network_settings["Ports"]
            privileged = host["Privileged"]
            network_mode = host["NetworkMode"]
            pid_mode = host["PidMode"]
            ipc_mode = host["IpcMode"]
            uts_mode = host["UTSMode"]
            userns_mode = host["UsernsMode"]
            cgroupns_mode = host["CgroupnsMode"]
            port_bindings = host["PortBindings"]
        except (KeyError, TypeError, AssertionError) as error:
            raise ControllerError("container inspection required fields are missing") from error
        if (
            type(running_value) is not bool
            or type(state_status) is not str
            or not state_status
            or type(entrypoint) is not list
            or not entrypoint
            or any(type(item) is not str or not item for item in entrypoint)
            or type(command) is not list
            or not command
            or any(type(item) is not str or not item for item in command)
            or type(raw_networks) is not dict
            or type(port_bindings) is not dict
            or not (
                published_ports is None
                or (
                    type(published_ports) is dict
                    and all(
                        type(port) is str
                        and port
                        and (
                            bindings is None
                            or (
                                type(bindings) is list
                                and all(type(binding) is dict for binding in bindings)
                            )
                        )
                        for port, bindings in published_ports.items()
                    )
                )
            )
        ):
            raise ControllerError("container inspection process/state/port fields are invalid")
        expected_labels = _object_labels(str(manifest["run_id"]), role, track)
        track_manifest = _track_manifest(manifest, LiveTrack(track))
        expected_name = str(track_manifest[f"{role}_container"])
        health_value = state_value.get("Health")
        health = (
            health_value.get("Status") if isinstance(health_value, dict) else "none"
        )
        running = running_value is True
        driver_states = (
            {"created"}
            if allowed_driver_states is None
            else set(allowed_driver_states)
        )
        if role != "driver" and allowed_driver_states is not None:
            raise ControllerError("driver lifecycle states applied to a service")
        if (
            role == "driver"
            and (
                not driver_states
                or not driver_states.issubset(
                    {"created", "running", "exited", "dead"}
                )
            )
        ):
            raise ControllerError("driver lifecycle state authority is invalid")
        if (
            type(object_id) is not str
            or _HEX.fullmatch(object_id) is None
            or name != f"/{expected_name}"
            or state_status not in {"created", "running", "exited", "dead"}
            or running != (state_status == "running")
            or (require_running and role != "driver" and not running)
            or (
                role == "driver"
                and (
                    state_status not in driver_states
                )
            )
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
        network_aliases: dict[str, list[str]] = {}
        for network_name, endpoint in raw_networks.items():
            if type(network_name) is not str or type(endpoint) is not dict:
                raise ControllerError("container network inspection is invalid")
            if "Aliases" not in endpoint:
                raise ControllerError("container network aliases are missing")
            aliases = endpoint["Aliases"]
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
            ],
            "networks": sorted(raw_networks),
            "network_aliases": {
                name: network_aliases[name] for name in sorted(network_aliases)
            },
            "port_bindings": port_bindings,
            "published_ports": published_ports,
            "platform": PLATFORM,
            "entrypoint": entrypoint,
            "command": command,
            "environment": config_value.get("Env") or [],
            "state": state_status,
            "stdin_open": config_value.get("OpenStdin", False),
            "tty": config_value.get("Tty", False),
            "healthcheck": _classify_inspected_healthcheck(
                config_value.get("Healthcheck"),
                image_config.get("Healthcheck"),
            ),
            "privileged": privileged,
            "network_mode": network_mode,
            "pid_mode": pid_mode,
            "ipc_mode": "" if ipc_mode == "private" else ipc_mode,
            "uts_mode": uts_mode,
            "userns_mode": userns_mode,
            "cgroupns_mode": cgroupns_mode,
        }
        if role == "envoy":
            if envoy_attachment is None:
                raise ControllerError("Envoy attachment expectation is required")
            attachment = _validate_envoy_attachment_expectation(
                envoy_attachment, manifest, track
            )
            if attachment["container_id"] != object_id:
                raise ControllerError("Envoy attachment container ID changed")
            backend_networks = [str(track_manifest["backend_network"])]
            dual_networks = [
                str(track_manifest["backend_network"]),
                str(track_manifest["frontend_network"]),
            ]
            network_options = (
                [backend_networks]
                if attachment["phase"] == "unstarted"
                else [backend_networks, dual_networks]
                if attachment["phase"] == "pending"
                else [dual_networks]
            )
            matching_options = [
                option
                for option in network_options
                if sorted(option) == actual["networks"]
            ]
            if len(matching_options) != 1:
                raise ControllerError(
                    "Envoy attachment network shape is not journal-authorized"
                )
            expected_networks = matching_options[0]
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
                state_status
                if role == "driver"
                else "running" if require_running else None
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
        expected_members: Mapping[str, Mapping[str, str]],
        allowed_member_options: Sequence[
            Mapping[str, Mapping[str, str]]
        ] | None = None,
        envoy_attachment: Mapping[str, object] | None = None,
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
        if segment == "frontend":
            if envoy_attachment is None:
                raise ControllerError("Envoy attachment expectation is required")
            attachment = _validate_envoy_attachment_expectation(
                envoy_attachment, manifest, track
            )
            if attachment["network_id"] != object_id:
                raise ControllerError("Envoy attachment frontend network ID changed")
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
        if type(expected_members) is not dict:
            raise ControllerError("expected network membership is invalid")
        def validate_expected(
            candidate: Mapping[str, Mapping[str, str]],
        ) -> tuple[dict[str, str], set[str]]:
            if type(candidate) is not dict:
                raise ControllerError("expected network membership is invalid")
            pairs: dict[str, str] = {}
            names: set[str] = set()
            roles: set[str] = set()
            for container_id, identity in candidate.items():
                if (
                    type(container_id) is not str
                    or _HEX.fullmatch(container_id) is None
                    or type(identity) is not dict
                    or set(identity) != {"name", "role"}
                    or type(identity["name"]) is not str
                    or type(identity["role"]) is not str
                    or identity["role"] not in expected_roles
                    or identity["name"]
                    != str(track_value[f"{identity['role']}_container"])
                    or identity["name"] in names
                ):
                    raise ControllerError(
                        "expected network member identity is invalid"
                    )
                pairs[container_id] = identity["name"]
                names.add(identity["name"])
                roles.add(identity["role"])
            return pairs, roles

        expected_pairs, expected_member_roles = validate_expected(
            expected_members
        )
        allowed_pairs: list[dict[str, str]] | None = None
        if allowed_member_options is not None:
            if (
                type(allowed_member_options) not in {list, tuple}
                or not 1 <= len(allowed_member_options) <= 2
            ):
                raise ControllerError("allowed network membership is invalid")
            allowed_pairs = [
                validate_expected(option)[0]
                for option in allowed_member_options
            ]
            if expected_pairs != allowed_pairs[0] or len(
                {canonical_json(option) for option in allowed_pairs}
            ) != len(allowed_pairs):
                raise ControllerError("allowed network membership is not closed")
        actual_pairs = {
            container_id: endpoint["Name"]
            for container_id, endpoint in containers.items()
        }
        if (
            len(members) != len(set(members))
            or (
                allowed_pairs is not None
                and actual_pairs not in allowed_pairs
            )
            or (
                allowed_pairs is None
                and any(
                    expected_pairs.get(container_id) != member_name
                    for container_id, member_name in actual_pairs.items()
                )
            )
            or (
                allowed_pairs is None
                and require_complete_membership
                and (
                    actual_pairs != expected_pairs
                    or expected_member_roles != expected_roles
                )
            )
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
        if type(raw) is not dict:
            raise ControllerError("Envoy validator inspection fields are invalid")
        try:
            object_id = raw["Id"]
            object_name = raw["Name"]
            image_id = raw["Image"]
            config = raw["Config"]
            host = raw["HostConfig"]
            state = raw["State"]
            network_settings = raw["NetworkSettings"]
            mounts = raw["Mounts"]
            assert type(config) is dict
            assert type(host) is dict
            assert type(state) is dict
            assert type(network_settings) is dict
            assert type(mounts) is list
            assert all(type(item) is dict for item in mounts)
            image_reference = config["Image"]
            actual_labels = config["Labels"]
            user = config["User"]
            entrypoint = config["Entrypoint"]
            command = config["Cmd"]
            privileged = host["Privileged"]
            readonly_rootfs = host["ReadonlyRootfs"]
            auto_remove = host["AutoRemove"]
            cap_drop = host["CapDrop"]
            security_value = host["SecurityOpt"]
            network_mode = host["NetworkMode"]
            pid_mode = host["PidMode"]
            ipc_mode = host["IpcMode"]
            uts_mode = host["UTSMode"]
            userns_mode = host["UsernsMode"]
            cgroupns_mode = host["CgroupnsMode"]
            port_bindings = host["PortBindings"]
            running = state["Running"]
            state_status = state["Status"]
            networks = network_settings["Networks"]
            published_ports = network_settings["Ports"]
        except (KeyError, TypeError, AssertionError) as error:
            raise ControllerError(
                "Envoy validator inspection required fields are invalid"
            ) from error
        name = f"kil-v3b1-validate-{_track_slug(track)}-{str(manifest['content_identity_sha256'])[:12]}"
        labels = _object_labels(str(manifest["run_id"]), "validator", track.value)
        security = security_value
        if security == ["no-new-privileges:true"]:
            security = ["no-new-privileges"]
        normalized_mounts = [
            {
                "source": item.get("Source"),
                "destination": item.get("Destination"),
                "rw": item.get("RW"),
            }
            for item in mounts
        ]
        live_ports_empty = published_ports is None or (
            type(published_ports) is dict
            and all(
                type(port) is str and port and bindings in (None, [])
                for port, bindings in published_ports.items()
            )
        )
        none_network_fields = {
            "IPAMConfig",
            "Links",
            "Aliases",
            "DriverOpts",
            "GwPriority",
            "NetworkID",
            "EndpointID",
            "Gateway",
            "IPAddress",
            "MacAddress",
            "IPPrefixLen",
            "IPv6Gateway",
            "GlobalIPv6Address",
            "GlobalIPv6PrefixLen",
            "DNSNames",
        }
        canonical_networks: dict[str, object] | None = None
        if type(networks) is dict and networks == {}:
            canonical_networks = {}
        elif type(networks) is dict and set(networks) == {"none"}:
            none_network = networks["none"]
            if (
                type(none_network) is dict
                and set(none_network) == none_network_fields
                and none_network["IPAMConfig"] is None
                and none_network["Links"] is None
                and none_network["Aliases"] is None
                and none_network["DriverOpts"] is None
                and type(none_network["GwPriority"]) is int
                and none_network["GwPriority"] == 0
                and type(none_network["NetworkID"]) is str
                and _HEX.fullmatch(none_network["NetworkID"]) is not None
                and type(none_network["EndpointID"]) is str
                and none_network["EndpointID"] == ""
                and type(none_network["Gateway"]) is str
                and none_network["Gateway"] == ""
                and type(none_network["IPAddress"]) is str
                and none_network["IPAddress"] == ""
                and type(none_network["MacAddress"]) is str
                and none_network["MacAddress"] == ""
                and type(none_network["IPPrefixLen"]) is int
                and none_network["IPPrefixLen"] == 0
                and type(none_network["IPv6Gateway"]) is str
                and none_network["IPv6Gateway"] == ""
                and type(none_network["GlobalIPv6Address"]) is str
                and none_network["GlobalIPv6Address"] == ""
                and type(none_network["GlobalIPv6PrefixLen"]) is int
                and none_network["GlobalIPv6PrefixLen"] == 0
                and none_network["DNSNames"] is None
            ):
                canonical_networks = {}
        if (
            type(object_id) is not str
            or _HEX.fullmatch(object_id) is None
            or object_id != identifier
            or object_name != f"/{name}"
            or image_id != manifest["envoy_image_id"]
            or image_reference != manifest["envoy_image_digest"]
            or user != "65532:65532"
            or entrypoint != ["/usr/local/bin/envoy"]
            or command != [
                "--mode", "validate", "--config-path", "/etc/envoy/envoy.json",
                "--disable-hot-restart", "--concurrency", "1",
            ]
            or privileged is not False
            or readonly_rootfs is not True
            or auto_remove is not False
            or cap_drop != ["ALL"]
            or security != ["no-new-privileges"]
            or network_mode != "none"
            or type(pid_mode) is not str
            or pid_mode != ""
            or type(ipc_mode) is not str
            or ipc_mode not in {"", "private"}
            or type(uts_mode) is not str
            or uts_mode != ""
            or type(userns_mode) is not str
            or userns_mode != ""
            or cgroupns_mode != "private"
            or port_bindings != {}
            or running is not False
            or state_status != "exited"
            or canonical_networks is None
            or not live_ports_empty
            or len(normalized_mounts) != 1
            or type(normalized_mounts[0]["source"]) is not str
            or not Path(str(normalized_mounts[0]["source"])).is_absolute()
            or normalized_mounts[0]["destination"] != "/etc/envoy/envoy.json"
            or normalized_mounts[0]["rw"] is not False
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
            actual_labels, image_config.get("Labels"), labels
        )
        runtime_attestation = {
            "privileged": privileged,
            "network_mode": network_mode,
            "pid_mode": pid_mode,
            "ipc_mode": "" if ipc_mode == "private" else ipc_mode,
            "uts_mode": uts_mode,
            "userns_mode": userns_mode,
            "cgroupns_mode": cgroupns_mode,
            "state": state_status,
            "entrypoint": entrypoint,
            "command": command,
            "mounts": normalized_mounts,
            "networks": canonical_networks,
            "port_bindings": port_bindings,
            "published_ports": published_ports,
        }
        return {
            "id": object_id,
            "name": name,
            "role": "validator",
            "track": track.value,
            "labels": labels,
            "image_id": manifest["envoy_image_id"],
            "image_reference": manifest["envoy_image_digest"],
            "runtime_attestation": runtime_attestation,
        }

    def _attest_runtime(
        self, manifest: dict[str, object]
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        journal = load_lifecycle_journal(self.journal_path)
        events = journal["events"]
        assert isinstance(events, list)
        envoy_attachments = _envoy_attachment_expectations(events, manifest)
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
                            envoy_attachment=(
                                envoy_attachments[str(item["track"])]
                                if item["role"] == "envoy"
                                else None
                            ),
                        )
                    )
                break
            except ControllerError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
        networks = []
        for item in _runtime_networks(manifest):
            track = str(item["track"])
            segment = _network_segment(item)
            member_options = _network_member_identity_options(
                objects,
                manifest,
                track,
                segment,
                envoy_attachments[track],
            )
            networks.append(
                self._inspect_network(
                    str(item["name"]),
                    manifest,
                    track,
                    segment=segment,
                    expected_members=member_options[0],
                    allowed_member_options=member_options,
                    envoy_attachment=(
                        envoy_attachments[track]
                        if segment == "frontend"
                        else None
                    ),
                )
            )
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
        envoy_attachments = (
            _envoy_attachment_expectations(events, manifest)
            if manifest is not None
            else {}
        )
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
                allowed_driver_states = None
                if item["role"] == "driver":
                    authority = _driver_recovery_authority(
                        events, str(item["track"]), identifier
                    )
                    allowed_driver_states = set(
                        authority["allowed_states"]  # type: ignore[arg-type]
                    )
                inspect_kwargs: dict[str, object] = {
                    "require_running": False,
                    "envoy_attachment": (
                        envoy_attachments[str(item["track"])]
                        if item["role"] == "envoy"
                        else None
                    ),
                }
                if allowed_driver_states is not None:
                    inspect_kwargs["allowed_driver_states"] = allowed_driver_states
                current = self._inspect_container(
                    identifier,
                    manifest,
                    str(item["role"]),
                    str(item["track"]),
                    **inspect_kwargs,
                )
                if "id" in item and not _container_attestation_matches(
                    item,
                    current,
                    allow_stopped=True,
                    allowed_driver_states=allowed_driver_states,
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
                segment = str(item.get("segment", "backend"))
                track = str(item["track"])
                member_options = _network_member_identity_options(
                    objects,
                    manifest,
                    track,
                    segment,
                    envoy_attachments[track],
                )
                current = self._inspect_network(
                    identifier,
                    manifest,
                    track,
                    segment=segment,
                    expected_members=member_options[0],
                    allowed_member_options=member_options,
                    envoy_attachment=(
                        envoy_attachments[track]
                        if segment == "frontend"
                        else None
                    ),
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
            "envoy_attachments": envoy_attachments,
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
            schema_version=JOURNAL_SCHEMA,
        )
        before_snapshot = self._capture_foreign_profile_snapshot(
            "before_colima_mutation"
        )
        journal_event(
            self.journal_path,
            "foreign_profile_snapshot_before",
            before_snapshot,
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
        journal = load_lifecycle_journal(self.journal_path)
        events = journal["events"]
        assert isinstance(events, list)
        envoy_attachments = _envoy_attachment_expectations(events, manifest)
        if any(
            attachment["phase"] != "complete"
            for attachment in envoy_attachments.values()
        ):
            raise ControllerError("active runtime lacks complete Envoy attachments")
        current_objects: list[dict[str, object]] = []
        for record in state["objects"]:  # type: ignore[union-attr]
            driver_authority = None
            allowed_driver_states = None
            if record["role"] == "driver":
                driver_authority = _driver_recovery_authority(
                    events, str(record["track"]), str(record["id"])
                )
                if driver_authority["phase"] == "pre_start":
                    allowed_driver_states = {"created"}
                elif driver_authority["request_eligible"] is True:
                    allowed_driver_states = {"exited"}
                else:
                    raise ControllerError(
                        "driver start is ambiguous or teardown-only; down is required"
                    )
            inspect_kwargs: dict[str, object] = {
                "require_running": record["role"] != "driver",
                "envoy_attachment": (
                    envoy_attachments[str(record["track"])]
                    if record["role"] == "envoy"
                    else None
                ),
            }
            if allowed_driver_states is not None:
                inspect_kwargs["allowed_driver_states"] = allowed_driver_states
            current = self._inspect_container(
                str(record["id"]),
                manifest,
                str(record["role"]),
                str(record["track"]),
                **inspect_kwargs,
            )
            if record["role"] == "driver":
                current_matches = _container_attestation_matches(
                    record,
                    current,
                    allow_stopped=True,
                    allowed_driver_states=allowed_driver_states,
                )
            else:
                current_matches = current == record
            if not current_matches:
                raise ControllerError("recorded container attestation changed")
            current_objects.append(current)
        for record in state["network_objects"]:  # type: ignore[union-attr]
            track = str(record["track"])
            segment = str(record.get("segment", "backend"))
            member_options = _network_member_identity_options(
                current_objects,
                manifest,
                track,
                segment,
                envoy_attachments[track],
            )
            current = self._inspect_network(
                str(record["id"]),
                manifest,
                track,
                segment=segment,
                expected_members=member_options[0],
                allowed_member_options=member_options,
                envoy_attachment=(
                    envoy_attachments[track]
                    if segment == "frontend"
                    else None
                ),
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

    def _failure_request_records(
        self, manifest: Mapping[str, object]
    ) -> list[dict[str, object]]:
        """Normalize durable request outcomes for nonpromotable evidence."""
        journal = load_lifecycle_journal(self.journal_path)
        requests_state = journal["requests"]
        events = journal["events"]
        assert isinstance(requests_state, dict)
        assert isinstance(events, list)
        runtime_path = _runtime_root(self.root, manifest) / "requests.jsonl"
        if not runtime_path.is_symlink() and runtime_path.is_file():
            successful = _parse_jsonl_bytes(
                runtime_path.read_bytes(),
                "partial normalized requests",
                _request_closed,
                allow_empty=True,
            )
        elif all(
            isinstance(request, dict) and request.get("status") == "completed"
            for request in requests_state.values()
        ):
            successful = self._request_records(manifest)
        else:
            successful = []
        successful_by_track = {
            str(record["track"]): record for record in successful
        }
        if len(successful_by_track) != len(successful):
            raise ControllerError("partial normalized request tracks are duplicated")
        identity = manifest.get("content_identity")
        if type(identity) is not dict:
            raise ControllerError("failure request manifest identity is invalid")
        definitions = identity.get("driver_definition_sha256")
        if type(definitions) is not list:
            raise ControllerError("failure request driver definitions are invalid")
        definition_by_track = {
            str(item.get("track")): item.get("sha256")
            for item in definitions
            if type(item) is dict
        }
        normalized: list[dict[str, object]] = []
        for track in _TRACKS:
            state = requests_state[track.value]
            assert isinstance(state, dict)
            status = state.get("status")
            if status == "not_attempted":
                if track.value in successful_by_track:
                    raise ControllerError(
                        "uncommanded request has a normalized record"
                    )
                continue
            if status == "completed":
                record = successful_by_track.get(track.value)
                if record is None:
                    raise ControllerError(
                        "completed request lacks its exact normalized record"
                    )
                normalized.append(record)
                continue
            if status == "intent_persisted":
                raise ControllerError(
                    "commanded request lacks terminal closed provenance"
                )
            if status != "failed":
                raise ControllerError("durable request state is invalid")
            matches = [
                event
                for event in events
                if event.get("event") == "request_send_failed"
                and isinstance(event.get("details"), dict)
                and event["details"].get("track") == track.value
            ]
            if len(matches) != 1:
                raise ControllerError(
                    "commanded failure lacks one durable terminal event"
                )
            details = matches[0]["details"]
            assert isinstance(details, dict)
            if set(details) != {
                "track", "record_sha256", "intent_id", "provenance",
            }:
                raise ControllerError(
                    "commanded failure lacks closed reconstruction provenance"
                )
            intent_id = _require_sha256(
                "failure request intent", details["intent_id"]
            )
            provenance = _validate_request_failure_provenance(
                details["provenance"]
            )
            result = _driver_failure_result_from_provenance(track, provenance)
            result_payload = canonical_record(result)
            instruction_intents = [
                event
                for event in events
                if event.get("event") == "driver_instruction_write_intent"
                and isinstance(event.get("details"), dict)
                and event["details"].get("track") == track.value
                and event["details"].get("intent_id") == intent_id
            ]
            if len(instruction_intents) > 1:
                raise ControllerError("driver instruction intent is duplicated")
            if instruction_intents:
                driver_id = instruction_intents[0]["details"]["driver_id"]
            else:
                if (
                    result.get("stage") != "instruction_write"
                    or result.get("request_bytes_may_have_been_sent") is not False
                ):
                    raise ControllerError(
                        "driver failure stage lacks its instruction intent"
                    )
                readiness = [
                    event
                    for event in events
                    if event.get("event") == "driver_readiness_complete"
                    and isinstance(event.get("details"), dict)
                    and event["details"].get("track") == track.value
                    and event["sequence"] < matches[0]["sequence"]
                ]
                if not readiness:
                    raise ControllerError(
                        "commanded failure lacks durable driver identity"
                    )
                driver_id = readiness[-1]["details"]["driver_id"]
            definition_sha = definition_by_track.get(track.value)
            _require_sha256("failure request definition", definition_sha)
            journal_details = _driver_failure_journal_details(
                track, intent_id, provenance
            )
            record = {
                "schema_version": "kil.v3b1-request-failure.v1",
                "run_id": manifest["run_id"],
                "request_id": manifest["request_id"],
                "track": track.value,
                "request_transport": "in_network_request_driver",
                "driver_role": "request_driver",
                "driver_full_id": driver_id,
                "driver_image_id": manifest["kil_image_id"],
                "driver_definition_sha256": definition_sha,
                "driver_result_sha256": _digest_bytes(result_payload),
                "driver_status": result["status"],
                "intent_id": intent_id,
                "journal_sequence": matches[0]["sequence"],
                "journal_event_sha256": _digest_bytes(
                    canonical_record(matches[0])
                ),
                "failure_provenance": dict(provenance),
            }
            _driver_failure_request_closed(record)
            normalized.append(record)
        if set(successful_by_track) - {
            str(record["track"])
            for record in normalized
            if record.get("schema_version") == "kil.v3b1-request.v2"
        }:
            raise ControllerError("normalized request is not durably completed")
        completed_records = [
            record
            for record in normalized
            if record.get("schema_version") == "kil.v3b1-request.v2"
        ]
        if completed_records:
            validate_request_journal(
                completed_records, journal, require_all=False
            )
        return normalized

    def _private_driver_result_sources(
        self, manifest: Mapping[str, object]
    ) -> dict[LiveTrack, bytes]:
        normalized = {
            str(record["track"]): record
            for record in self._failure_request_records(manifest)
        }
        root = self.private_root / "driver-results" / str(manifest["run_id"])
        _require_contained(root, self.private_root, "private driver result root")
        results: dict[LiveTrack, bytes] = {}
        for track in _TRACKS:
            path = root / f"{track.value}.json"
            _require_contained(path, root, "private driver result")
            request = normalized.get(track.value)
            if path.is_symlink():
                raise ControllerError("private driver result is unsafe")
            if not path.exists():
                if request is None:
                    results[track] = b""
                    continue
                if request.get("schema_version") != (
                    "kil.v3b1-request-failure.v1"
                ):
                    raise ControllerError(
                        "commanded driver result is missing without failure provenance"
                    )
                result = _driver_failure_result_from_provenance(
                    track, request["failure_provenance"]
                )
                results[track] = canonical_record(result)
                continue
            if not path.is_file():
                raise ControllerError("private driver result is unsafe")
            payload = path.read_bytes()
            if len(payload) > 8 * 1024:
                raise ControllerError("private driver result exceeds its bound")
            if request is None:
                raise ControllerError(
                    "uncommanded track has a private driver result"
                )
            expected_digest = request["driver_result_sha256"]
            if _digest_bytes(payload) != expected_digest:
                raise ControllerError(
                    "private driver result diverges from durable command state"
                )
            results[track] = payload
        return results

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
            envoy_attachment = None
            if item["role"] == "envoy":
                journal = load_lifecycle_journal(self.journal_path)
                events = journal["events"]
                assert isinstance(events, list)
                envoy_attachment = _envoy_attachment_expectations(
                    events, manifest
                )[track.value]
            current = self._inspect_container(
                str(item["id"]),
                manifest,
                str(item["role"]),
                track.value,
                require_running=source != "envoy_access",
                envoy_attachment=envoy_attachment,
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
        *,
        envoy_attachment: Mapping[str, object] | None = None,
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
                envoy_attachment=(
                    envoy_attachment if item["role"] == "envoy" else None
                ),
            )
        if item["role"] == "validator":
            current_matches = current == item
        else:
            current_matches = _container_attestation_matches(
                item, current, allow_stopped=True
            )
        if not current_matches:
            raise ControllerError("container changed before exact stop")
        stop_identity = {
            "id": item["id"],
            "name": item["name"],
            "role": item["role"],
        }
        journal = load_lifecycle_journal(self.journal_path)
        events = journal["events"]
        assert isinstance(events, list)
        transition = _container_stop_transition(events, stop_identity)
        running = self._execute(
            self.docker_command(
                "inspect", "--format", "{{.State.Running}}", str(item["id"])
            ),
            timeout_s=30,
            docker=True,
        ).stdout.strip()
        if running not in {"true", "false"}:
            raise ControllerError("container running state is invalid")
        if transition == "complete":
            if running == "true":
                raise ControllerError("completed container stop is running")
            return
        if transition == "unstarted" and running == "false":
            return
        if running == "true":
            if transition == "unstarted":
                journal_event(
                    self.journal_path,
                    "container_stop_intent",
                    stop_identity,
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
                    envoy_attachment=(
                        envoy_attachment if item["role"] == "envoy" else None
                    ),
                )
            if item["role"] == "validator":
                after_matches = after == item
            else:
                after_matches = _container_attestation_matches(
                    item, after, allow_stopped=True
                )
            if not after_matches:
                raise ControllerError("container changed after exact stop")
        if transition == "pending" or running == "true":
            journal_event(
                self.journal_path,
                "container_stop_complete",
                {"id": item["id"], "name": item["name"]},
            )

    def _quiesce_driver_for_teardown(
        self,
        item: Mapping[str, object],
        manifest: dict[str, object],
    ) -> dict[str, object]:
        """Make one exact started driver nonrunning without ever starting it."""
        if item.get("role") != "driver":
            raise ControllerError("driver teardown received a non-driver")
        track = str(item.get("track"))
        driver_id = str(item.get("id"))
        journal = load_lifecycle_journal(self.journal_path)
        events = journal["events"]
        assert isinstance(events, list)
        authority = _driver_recovery_authority(events, track, driver_id)
        observed_state = item.get("runtime_attestation", {}).get("state")
        if observed_state not in authority["allowed_states"]:
            raise ControllerError("driver state is outside journal recovery authority")
        if authority["phase"] == "pre_start":
            if observed_state != "created":
                raise ControllerError("unstarted driver is not exactly created")
            return authority
        if authority["phase"] in {"trusted_terminal", "teardown_quiesced"}:
            if observed_state not in {"created", "exited", "dead"}:
                raise ControllerError("terminal driver unexpectedly remains running")
            return authority

        starts = [
            event
            for event in events
            if event.get("event") == "driver_start_intent"
            and isinstance(event.get("details"), dict)
            and event["details"].get("track") == track
        ]
        if len(starts) != 1:
            raise ControllerError("driver teardown lacks one exact start intent")
        readiness_nonce = starts[0]["details"].get("readiness_nonce")
        _require_sha256("driver teardown readiness nonce", readiness_nonce)
        identity = {
            "readiness_nonce": readiness_nonce,
            "track": track,
            "driver_id": driver_id,
        }
        transition = _driver_stop_transition(events, track, driver_id)
        if transition == "complete":
            if observed_state == "running":
                raise ControllerError("completed driver stop is running")
            return _driver_recovery_authority(events, track, driver_id)
        if transition in {"unstarted", "failed"}:
            journal_event(self.journal_path, "driver_stop_intent", identity)
        if observed_state == "running":
            try:
                self._execute(
                    self.docker_command("stop", "--timeout", "10", driver_id),
                    timeout_s=30,
                    docker=True,
                )
            except Exception:
                journal_event(
                    self.journal_path,
                    "driver_stop_failed",
                    {**identity, "category": "container_stop"},
                )
                raise
        current = self._inspect_container(
            driver_id,
            manifest,
            "driver",
            track,
            require_running=False,
            allowed_driver_states={"created", "exited", "dead"},
        )
        if not _container_attestation_matches(
            item,
            current,
            allow_stopped=True,
            allowed_driver_states={"created", "exited", "dead"},
        ):
            raise ControllerError("driver changed during exact teardown stop")
        journal_event(self.journal_path, "driver_stop_complete", identity)
        return _driver_recovery_authority(
            load_lifecycle_journal(self.journal_path)["events"],  # type: ignore[arg-type]
            track,
            driver_id,
        )

    def _freeze_before_service_teardown(
        self,
        state: Mapping[str, object],
        manifest: dict[str, object],
        *,
        attempted_complete: bool,
        transient_objects: Sequence[Mapping[str, object]],
        envoy_attachments: Mapping[str, Mapping[str, object]] | None = None,
    ) -> EvidenceFreezeResult:
        objects = state["objects"]
        if type(objects) is not list:
            raise ControllerError("runtime object state is invalid")
        if envoy_attachments is None:
            journal = load_lifecycle_journal(self.journal_path)
            events = journal["events"]
            assert isinstance(events, list)
            envoy_attachments = _envoy_attachment_expectations(events, manifest)
        for item in objects:
            if item["role"] == "envoy":
                self._stop_and_attest_container(
                    item,
                    manifest,
                    envoy_attachment=envoy_attachments[str(item["track"])],
                )
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

    def _copy_live_ledger(
        self,
        *,
        container_id: str,
        source_path: str,
        destination: Path,
    ) -> bytes:
        """Copy one exact live ledger under a shared monotonic deadline."""
        _require_sha256("live ledger container ID", container_id)
        if source_path not in frozenset(_LEDGER_PATH.values()):
            raise ControllerError("live ledger source path is not allowed")
        _require_contained(destination, self.root, "live ledger destination")
        if destination.exists() or destination.is_symlink():
            raise ControllerError("live ledger destination already exists")

        deadline_ns = self.monotonic_ns() + _EVIDENCE_READ_DEADLINE_NS

        def remaining_seconds() -> float:
            remaining_ns = deadline_ns - self.monotonic_ns()
            if remaining_ns <= 0:
                raise ControllerError(
                    "live ledger availability deadline exceeded"
                )
            return remaining_ns / 1_000_000_000

        while True:
            probe = self._execute(
                self.docker_command(
                    "exec",
                    container_id,
                    "/usr/local/bin/python",
                    "-c",
                    _LEDGER_PROBE,
                    source_path,
                ),
                timeout_s=remaining_seconds(),
                docker=True,
            )
            present, source_count, source_sha = self._parse_probe_observation(
                probe.stdout
            )
            if present:
                break
            pause_s = min(_EVIDENCE_READ_POLL_S, remaining_seconds())
            self.sleep(pause_s)

        assert source_count is not None and source_sha is not None
        if source_count > _MAX_LEDGER_EXPORT_BYTES:
            raise ControllerError("live ledger exceeds the closed size bound")
        try:
            self._execute(
                self.docker_command(
                    "cp", f"{container_id}:{source_path}", str(destination)
                ),
                timeout_s=remaining_seconds(),
                docker=True,
            )
            descriptor = os.open(
                destination, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
            try:
                opened = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_size != source_count
                ):
                    raise ControllerError(
                        "live ledger copied byte count changed"
                    )
                chunks: list[bytes] = []
                copied_count = 0
                while copied_count <= source_count:
                    chunk = os.read(
                        descriptor,
                        min(1024 * 1024, source_count + 1 - copied_count),
                    )
                    if not chunk:
                        break
                    chunks.append(chunk)
                    copied_count += len(chunk)
                finished = os.fstat(descriptor)
                os.fchmod(descriptor, 0o400)
            finally:
                os.close(descriptor)
            current = os.stat(destination, follow_symlinks=False)
            if (
                not stat.S_ISREG(current.st_mode)
                or (opened.st_dev, opened.st_ino)
                != (finished.st_dev, finished.st_ino)
                or (opened.st_dev, opened.st_ino)
                != (current.st_dev, current.st_ino)
                or opened.st_size != finished.st_size
            ):
                raise ControllerError("live ledger copy changed during read")
            copied = b"".join(chunks)
            if len(copied) != source_count:
                raise ControllerError("live ledger copied byte count changed")
            if _digest_bytes(copied) != source_sha:
                raise ControllerError("live ledger copied SHA-256 changed")
            return copied
        except (ControllerError, OSError, UnicodeError) as error:
            if destination.is_symlink() or destination.exists():
                destination.unlink(missing_ok=True)
            if isinstance(error, ControllerError):
                raise
            raise ControllerError("live ledger copy failed") from error

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
            decision_bytes = self._copy_live_ledger(
                container_id=str(authz["id"]),
                source_path="/evidence/decisions.jsonl",
                destination=decision_path,
            )
            target_bytes = self._copy_live_ledger(
                container_id=str(target["id"]),
                source_path="/evidence/targets.jsonl",
                destination=target_path,
            )
            logs = self._execute(
                self.docker_command("logs", str(proxy["id"])),
                timeout_s=60,
                docker=True,
            )
            _write_file(envoy_path, logs.stdout.encode("utf-8"), 0o444)
            raw_decisions[track] = decision_bytes
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
                target_bytes,
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
        raw_driver_results = self._private_driver_result_sources(manifest)
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
            raw_driver_results=raw_driver_results,
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
    def _driver_identity_details(
        session: DriverSession,
        readiness_nonce: str,
    ) -> dict[str, object]:
        return {
            "readiness_nonce": readiness_nonce,
            "track": session.track,
            "driver_id": session.full_id,
        }

    def _inspect_driver_cleanup_running(self, full_id: str) -> bool:
        """Read one exact driver ID's closed running state for failure cleanup."""
        _require_sha256("driver cleanup full ID", full_id)
        result = self._execute(
            self.docker_command(
                "inspect",
                "--format",
                _DRIVER_STATE_FORMAT,
                full_id,
            ),
            timeout_s=5,
            docker=True,
        )
        fields = result.stdout.strip().split()
        if len(fields) != 3 or fields[0] != full_id:
            raise ControllerError("driver container state inspection is ambiguous")
        running_text, status = fields[1], fields[2]
        if running_text == "true" and status == "running":
            return True
        if running_text == "false" and status in {"created", "exited", "dead"}:
            return False
        raise ControllerError("driver container state inspection is ambiguous")

    def _fail_driver_readiness_sessions(
        self,
        *,
        execution_nonce: str,
        readiness_nonce: str,
        deadline_ns: int,
        sessions: Mapping[LiveTrack, DriverSession],
        active_identity: tuple[str, LiveTrack | None, str | None, str],
        error: Exception,
        primary: tuple[
            str, LiveTrack | None, str | None, str, DriverTransportError
        ]
        | None = None,
        cancellation_intents: set[LiveTrack] | None = None,
        cancellation_attempts: set[LiveTrack] | None = None,
        cancellation_completions: set[LiveTrack] | None = None,
    ) -> None:
        """Poison, cancel, and clean one failed attached-driver readiness set."""
        intents = cancellation_intents if cancellation_intents is not None else set()
        attempts = cancellation_attempts if cancellation_attempts is not None else set()
        completions = (
            cancellation_completions
            if cancellation_completions is not None
            else set()
        )
        if primary is None:
            if isinstance(error, DriverTransportError):
                primary_error = error
            elif active_identity[3] == "readiness_deadline":
                primary_error = DriverTransportError("clock_failure")
            else:
                primary_error = DriverTransportError("controller_persistence")
            primary = (
                active_identity[0],
                active_identity[1],
                active_identity[2],
                active_identity[3],
                primary_error,
            )
        failed_scope, failed_track, failed_id, failed_stage, primary_error = primary
        category = primary_error.category
        try:
            self._persist_readiness_poison_independent(
                execution_nonce=execution_nonce,
                readiness_nonce=readiness_nonce,
                reason_category="driver_readiness_failed",
            )
        except Exception:
            pass
        for track, session in sessions.items():
            if track in intents:
                continue
            try:
                journal_event(
                    self.journal_path,
                    "readiness_cancel_intent",
                    self._driver_identity_details(session, readiness_nonce),
                )
                intents.add(track)
            except Exception:
                pass
            try:
                close_instruction_stream(session)
            except Exception:
                pass
        for track, session in sessions.items():
            if track in attempts or track in completions:
                continue
            attempts.add(track)
            try:
                exit_code = attest_cancelled_exit(
                    session,
                    deadline_ns=deadline_ns,
                    monotonic_ns=self.monotonic_ns,
                )
            except Exception:
                continue
            if track not in intents:
                continue
            try:
                journal_event(
                    self.journal_path,
                    "readiness_cancel_complete",
                    {
                        **self._driver_identity_details(session, readiness_nonce),
                        "exit_code": exit_code,
                    },
                )
                completions.add(track)
            except Exception:
                pass
        for session in sessions.values():
            identity = self._driver_identity_details(session, readiness_nonce)
            container_category: str | None = None
            try:
                running = self._inspect_driver_cleanup_running(session.full_id)
            except Exception:
                running = None
                container_category = "container_inspect"
            if running is True:
                try:
                    journal_event(self.journal_path, "driver_stop_intent", identity)
                except Exception:
                    container_category = "cleanup_persistence"
                else:
                    stop_deadline_ns = (
                        time.monotonic_ns() + _DRIVER_CLEANUP_DEADLINE_NS
                    )
                    try:
                        self._execute(
                            self.docker_command(
                                "stop", "--timeout", "1", session.full_id
                            ),
                            timeout_s=min(
                                5.0,
                                remaining_seconds(
                                    stop_deadline_ns, time.monotonic_ns
                                ),
                            ),
                            docker=True,
                        )
                    except Exception:
                        container_category = "container_stop"
                    if container_category is None:
                        try:
                            still_running = self._inspect_driver_cleanup_running(
                                session.full_id
                            )
                        except Exception:
                            container_category = "container_inspect"
                        else:
                            if still_running:
                                container_category = "container_stop_verify"
                    try:
                        journal_event(
                            self.journal_path,
                            (
                                "driver_stop_complete"
                                if container_category is None
                                else "driver_stop_failed"
                            ),
                            (
                                identity
                                if container_category is None
                                else {**identity, "category": container_category}
                            ),
                        )
                    except Exception:
                        container_category = "cleanup_persistence"
            cleanup_intent = False
            try:
                journal_event(self.journal_path, "driver_cleanup_intent", identity)
                cleanup_intent = True
            except Exception:
                pass
            cleanup = None
            process_category: str | None = None
            try:
                cleanup = cleanup_driver_process(
                    session,
                    deadline_ns=time.monotonic_ns()
                    + _DRIVER_CLEANUP_DEADLINE_NS,
                    monotonic_ns=time.monotonic_ns,
                )
            except Exception as cleanup_error:
                process_category = (
                    cleanup_error.category
                    if isinstance(cleanup_error, DriverTransportError)
                    and cleanup_error.category in _DRIVER_READINESS_FAILURE_CATEGORIES
                    else "protocol_invalid"
                )
            cleanup_category = container_category or process_category
            if not cleanup_intent:
                cleanup_category = cleanup_category or "cleanup_persistence"
            if cleanup_intent:
                try:
                    if cleanup_category is None and cleanup is not None:
                        journal_event(
                            self.journal_path,
                            "driver_cleanup_complete",
                            {
                                **identity,
                                "outcome": cleanup.outcome,
                                "exit_code": cleanup.exit_code,
                            },
                        )
                    else:
                        journal_event(
                            self.journal_path,
                            "driver_cleanup_failed",
                            {
                                **identity,
                                "category": cleanup_category or "protocol_invalid",
                            },
                        )
                except Exception:
                    pass
        if category not in _DRIVER_READINESS_FAILURE_CATEGORIES:
            category = "protocol_invalid"
        try:
            journal_event(
                self.journal_path,
                "driver_readiness_failed",
                {
                    "readiness_nonce": readiness_nonce,
                    "scope": failed_scope,
                    "track": (
                        failed_track.value if failed_track is not None else None
                    ),
                    "driver_id": failed_id,
                    "category": category,
                    "stage": failed_stage,
                },
            )
        except Exception:
            pass
        raise ControllerError(
            "driver readiness failed closed; down is required"
        ) from None

    def readiness(self) -> dict[str, object]:
        """Run the request-free attached-driver readiness diagnostic once."""
        self._assert_no_readiness_poison()
        state, _ = self._load_and_reverify()
        journal = load_lifecycle_journal(self.journal_path)
        execution_nonce = str(journal["execution_nonce"])
        _require_sha256("driver readiness execution nonce", execution_nonce)
        events = journal["events"]
        assert isinstance(events, list)
        if any(
            event["event"] in {
                "driver_start_intent",
                "driver_start_complete",
                "driver_readiness_set_complete",
                "readiness_diagnostic_complete",
            }
            for event in events
        ):
            raise ControllerError(
                "driver readiness was already started; down is required"
            )
        if any(
            request["status"] != "not_attempted"
            for request in journal["requests"].values()
        ):
            raise ControllerError("driver readiness requires unattempted requests")
        drivers = {
            str(item["track"]): item
            for item in state["objects"]  # type: ignore[union-attr]
            if item["role"] == "driver"
        }
        if set(drivers) != {track.value for track in _TRACKS}:
            raise ControllerError("exact driver readiness identities are unavailable")

        readiness_nonce = secrets.token_hex(32)
        journal_event(
            self.journal_path,
            "readiness_session_started",
            {"readiness_nonce": readiness_nonce},
        )
        deadline_ns = 0
        sessions: dict[LiveTrack, DriverSession] = {}
        cancellation_intents: set[LiveTrack] = set()
        cancellation_attempts: set[LiveTrack] = set()
        cancellation_completions: set[LiveTrack] = set()
        primary: tuple[
            str, LiveTrack | None, str | None, str, DriverTransportError
        ] | None = None
        active_identity: tuple[str, LiveTrack | None, str | None, str] = (
            "controller",
            None,
            None,
            "readiness_deadline",
        )

        try:
            deadline_ns = self._monotonic_now() + _READINESS_DEADLINE_NS
            for track in _TRACKS:
                record = drivers[track.value]
                full_id = str(record["id"])
                identity = {
                    "readiness_nonce": readiness_nonce,
                    "track": track.value,
                    "driver_id": full_id,
                }
                active_identity = ("driver", track, full_id, "start_intent")
                journal_event(self.journal_path, "driver_start_intent", identity)
                active_identity = ("driver", track, full_id, "process_start")
                session = start_attached_driver(
                    self.driver_process_factory,
                    docker_binary=str(self.docker_binary),
                    track=track.value,
                    full_id=full_id,
                )
                sessions[track] = session
                active_identity = ("driver", track, full_id, "start_complete")
                journal_event(self.journal_path, "driver_start_complete", identity)

            for track in _TRACKS:
                session = sessions[track]
                active_identity = (
                    "driver", track, session.full_id, "readiness_record"
                )
                try:
                    payload = read_readiness_record(
                        session,
                        deadline_ns=deadline_ns,
                        monotonic_ns=self.monotonic_ns,
                    )
                    readiness_record = parse_driver_result(
                        payload, expected_track=track.value
                    )
                    if (
                        readiness_record.get("schema_version")
                        != "kil.v3b1-driver-readiness.v1"
                        or readiness_record.get("status") != "ready"
                    ):
                        raise DriverProtocolError(
                            "driver readiness schema/status is invalid"
                        )
                except DriverProtocolError:
                    if primary is None:
                        primary = (
                            "driver",
                            track,
                            session.full_id,
                            "readiness_record",
                            DriverTransportError("protocol_invalid"),
                        )
                    continue
                except DriverTransportError as error:
                    if primary is None:
                        primary = (
                            "driver",
                            track,
                            session.full_id,
                            "readiness_record",
                            error,
                        )
                    continue
                active_identity = (
                    "driver", track, session.full_id, "readiness_complete"
                )
                journal_event(
                    self.journal_path,
                    "driver_readiness_complete",
                    {
                        **self._driver_identity_details(session, readiness_nonce),
                        "record_sha256": _digest_bytes(payload),
                    },
                )

            if primary is not None:
                raise primary[4]
            active_identity = (
                "controller", None, None, "readiness_set_complete"
            )
            journal_event(
                self.journal_path,
                "driver_readiness_set_complete",
                {
                    "readiness_nonce": readiness_nonce,
                    "tracks": [track.value for track in _TRACKS],
                    "complete_monotonic_ns": self._monotonic_now(),
                },
            )

            for track in _TRACKS:
                session = sessions[track]
                active_identity = (
                    "driver", track, session.full_id, "cancel_signal"
                )
                journal_event(
                    self.journal_path,
                    "readiness_cancel_intent",
                    self._driver_identity_details(session, readiness_nonce),
                )
                cancellation_intents.add(track)
                try:
                    close_instruction_stream(session)
                except DriverTransportError as error:
                    if primary is None:
                        primary = (
                            "driver",
                            track,
                            session.full_id,
                            "cancel_signal",
                            error,
                        )

            for track in _TRACKS:
                session = sessions[track]
                active_identity = (
                    "driver", track, session.full_id, "cancel_exit"
                )
                cancellation_attempts.add(track)
                try:
                    exit_code = attest_cancelled_exit(
                        session,
                        deadline_ns=deadline_ns,
                        monotonic_ns=self.monotonic_ns,
                    )
                except DriverTransportError as error:
                    if primary is None:
                        primary = (
                            "driver",
                            track,
                            session.full_id,
                            "cancel_exit",
                            error,
                        )
                    continue
                journal_event(
                    self.journal_path,
                    "readiness_cancel_complete",
                    {
                        **self._driver_identity_details(session, readiness_nonce),
                        "exit_code": exit_code,
                    },
                )
                cancellation_completions.add(track)

            if primary is not None:
                raise primary[4]
            active_identity = (
                "controller", None, None, "diagnostic_complete"
            )
            journal_event(
                self.journal_path,
                "readiness_diagnostic_complete",
                {
                    "readiness_nonce": readiness_nonce,
                    "lifecycle_mode": "diagnostic_only",
                },
            )
            return {
                "status": "diagnostic_only",
                "readiness_nonce": readiness_nonce,
                "ready_tracks": [track.value for track in _TRACKS],
            }
        except Exception as error:
            self._fail_driver_readiness_sessions(
                execution_nonce=execution_nonce,
                readiness_nonce=readiness_nonce,
                deadline_ns=deadline_ns,
                sessions=sessions,
                active_identity=active_identity,
                error=error,
                primary=primary,
                cancellation_intents=cancellation_intents,
                cancellation_attempts=cancellation_attempts,
                cancellation_completions=cancellation_completions,
            )
            raise AssertionError("unreachable")

    def _start_ready_driver_set(
        self,
        state: Mapping[str, object],
    ) -> tuple[str, int, dict[LiveTrack, DriverSession]]:
        objects = state.get("objects")
        if type(objects) is not list:
            raise ControllerError("exact driver readiness identities are unavailable")
        drivers = {
            str(item["track"]): item
            for item in objects
            if type(item) is dict and item.get("role") == "driver"
        }
        if set(drivers) != {track.value for track in _TRACKS}:
            raise ControllerError("exact driver readiness identities are unavailable")
        journal = load_lifecycle_journal(self.journal_path)
        journal_events = journal["events"]
        assert isinstance(journal_events, list)
        if any(
            event["event"] == "driver_start_intent"
            for event in journal_events
        ):
            raise ControllerError(
                "driver start was already attempted; down is required"
            )
        execution_nonce = str(journal["execution_nonce"])
        _require_sha256("driver readiness execution nonce", execution_nonce)
        readiness_nonce = secrets.token_hex(32)
        journal_event(
            self.journal_path,
            "readiness_session_started",
            {"readiness_nonce": readiness_nonce},
        )
        deadline_ns = 0
        sessions: dict[LiveTrack, DriverSession] = {}
        primary: tuple[
            str, LiveTrack | None, str | None, str, DriverTransportError
        ] | None = None
        active_identity: tuple[str, LiveTrack | None, str | None, str] = (
            "controller",
            None,
            None,
            "readiness_deadline",
        )
        try:
            deadline_ns = self._monotonic_now() + _READINESS_DEADLINE_NS
            for track in _TRACKS:
                full_id = str(drivers[track.value]["id"])
                identity = {
                    "readiness_nonce": readiness_nonce,
                    "track": track.value,
                    "driver_id": full_id,
                }
                active_identity = ("driver", track, full_id, "start_intent")
                journal_event(self.journal_path, "driver_start_intent", identity)
                active_identity = ("driver", track, full_id, "process_start")
                session = start_attached_driver(
                    self.driver_process_factory,
                    docker_binary=str(self.docker_binary),
                    track=track.value,
                    full_id=full_id,
                )
                sessions[track] = session
                active_identity = ("driver", track, full_id, "start_complete")
                journal_event(self.journal_path, "driver_start_complete", identity)
            for track in _TRACKS:
                session = sessions[track]
                active_identity = (
                    "driver", track, session.full_id, "readiness_record"
                )
                try:
                    payload = read_readiness_record(
                        session,
                        deadline_ns=deadline_ns,
                        monotonic_ns=self.monotonic_ns,
                    )
                    record = parse_driver_result(payload, expected_track=track.value)
                    if (
                        record.get("schema_version")
                        != "kil.v3b1-driver-readiness.v1"
                        or record.get("status") != "ready"
                    ):
                        raise DriverProtocolError(
                            "driver readiness schema/status is invalid"
                        )
                except DriverProtocolError:
                    if primary is None:
                        primary = (
                            "driver",
                            track,
                            session.full_id,
                            "readiness_record",
                            DriverTransportError("protocol_invalid"),
                        )
                    continue
                except DriverTransportError as error:
                    if primary is None:
                        primary = (
                            "driver",
                            track,
                            session.full_id,
                            "readiness_record",
                            error,
                        )
                    continue
                active_identity = (
                    "driver", track, session.full_id, "readiness_complete"
                )
                journal_event(
                    self.journal_path,
                    "driver_readiness_complete",
                    {
                        **self._driver_identity_details(session, readiness_nonce),
                        "record_sha256": _digest_bytes(payload),
                    },
                )
            if primary is not None:
                raise primary[4]
            active_identity = (
                "controller", None, None, "readiness_set_complete"
            )
            journal_event(
                self.journal_path,
                "driver_readiness_set_complete",
                {
                    "readiness_nonce": readiness_nonce,
                    "tracks": [track.value for track in _TRACKS],
                    "complete_monotonic_ns": self._monotonic_now(),
                },
            )
            return readiness_nonce, deadline_ns, sessions
        except Exception as error:
            self._fail_driver_readiness_sessions(
                execution_nonce=execution_nonce,
                readiness_nonce=readiness_nonce,
                deadline_ns=deadline_ns,
                sessions=sessions,
                active_identity=active_identity,
                error=error,
                primary=primary,
            )
            raise AssertionError("unreachable")

    def _poison_request_driver_session(
        self,
        *,
        execution_nonce: str,
        readiness_nonce: str,
    ) -> None:
        try:
            self._persist_readiness_poison_independent(
                execution_nonce=execution_nonce,
                readiness_nonce=readiness_nonce,
                reason_category="driver_readiness_failed",
            )
        except Exception:
            pass

    def _cleanup_request_driver(self, session: DriverSession) -> None:
        try:
            cleanup_driver_process(
                session,
                deadline_ns=time.monotonic_ns() + _DRIVER_CLEANUP_DEADLINE_NS,
                monotonic_ns=time.monotonic_ns,
            )
        except Exception:
            pass

    @staticmethod
    def _driver_cleanup_failure_category(error: Exception) -> str:
        if (
            isinstance(error, DriverTransportError)
            and error.category in _DRIVER_READINESS_FAILURE_CATEGORIES
        ):
            return error.category
        return "protocol_invalid"

    def _recover_uncommanded_driver(
        self,
        *,
        track: LiveTrack,
        session: DriverSession,
        identity: Mapping[str, object],
        observed_cleanup_error: Exception | None = None,
    ) -> _DriverCancellationOutcome:
        """Physically clean and durably close one ambiguous cancellation."""
        cleanup_intent = False
        try:
            journal_event(self.journal_path, "driver_cleanup_intent", identity)
            cleanup_intent = True
        except Exception:
            pass

        cleanup = None
        cleanup_category = (
            None
            if observed_cleanup_error is None
            else self._driver_cleanup_failure_category(observed_cleanup_error)
        )
        if observed_cleanup_error is None:
            try:
                cleanup = cleanup_driver_process(
                    session,
                    deadline_ns=(
                        time.monotonic_ns() + _DRIVER_CLEANUP_DEADLINE_NS
                    ),
                    monotonic_ns=time.monotonic_ns,
                )
            except Exception as error:
                cleanup_category = self._driver_cleanup_failure_category(error)

        if not cleanup_intent:
            try:
                journal_event(self.journal_path, "driver_cleanup_intent", identity)
                cleanup_intent = True
            except Exception:
                return _DriverCancellationOutcome(
                    track=track,
                    driver_id=session.full_id,
                    status="cleanup_ambiguous",
                    category="cleanup_persistence",
                )

        if cleanup_category is None and cleanup is not None:
            event_name = "driver_cleanup_complete"
            details = {
                **identity,
                "outcome": cleanup.outcome,
                "exit_code": cleanup.exit_code,
            }
            outcome = _DriverCancellationOutcome(
                track=track,
                driver_id=session.full_id,
                status="cleanup_complete",
                category=None,
            )
        else:
            event_name = "driver_cleanup_failed"
            details = {
                **identity,
                "category": cleanup_category or "protocol_invalid",
            }
            outcome = _DriverCancellationOutcome(
                track=track,
                driver_id=session.full_id,
                status="cleanup_failed",
                category=cleanup_category or "protocol_invalid",
            )
        try:
            journal_event(self.journal_path, event_name, details)
            return outcome
        except Exception:
            fallback = {**identity, "category": "cleanup_persistence"}
            try:
                journal_event(
                    self.journal_path,
                    "driver_cleanup_failed",
                    fallback,
                )
            except Exception:
                return _DriverCancellationOutcome(
                    track=track,
                    driver_id=session.full_id,
                    status="cleanup_ambiguous",
                    category="cleanup_persistence",
                )
            return _DriverCancellationOutcome(
                track=track,
                driver_id=session.full_id,
                status="cleanup_failed",
                category="cleanup_persistence",
            )

    def _cancel_uncommanded_drivers(
        self,
        *,
        first_track: LiveTrack,
        readiness_nonce: str,
        sessions: Mapping[LiveTrack, DriverSession],
    ) -> tuple[_DriverCancellationOutcome, ...]:
        cancel = False
        selected: list[tuple[LiveTrack, DriverSession, dict[str, object]]] = []
        signal_failures: dict[LiveTrack, Exception] = {}
        for track in _TRACKS:
            if track is first_track:
                cancel = True
            if not cancel:
                continue
            session = sessions[track]
            identity = self._driver_identity_details(session, readiness_nonce)
            selected.append((track, session, identity))
            try:
                journal_event(self.journal_path, "readiness_cancel_intent", identity)
            except Exception as error:
                signal_failures[track] = error
            try:
                close_instruction_stream(session)
            except Exception as error:
                signal_failures.setdefault(track, error)

        outcomes: list[_DriverCancellationOutcome] = []
        for track, session, identity in selected:
            if track in signal_failures:
                outcomes.append(
                    self._recover_uncommanded_driver(
                        track=track,
                        session=session,
                        identity=identity,
                    )
                )
                continue
            try:
                exit_code = attest_cancelled_exit(
                    session,
                    deadline_ns=(
                        time.monotonic_ns() + _DRIVER_CLEANUP_DEADLINE_NS
                    ),
                    monotonic_ns=time.monotonic_ns,
                )
                journal_event(
                    self.journal_path,
                    "readiness_cancel_complete",
                    {**identity, "exit_code": exit_code},
                )
            except Exception:
                outcomes.append(
                    self._recover_uncommanded_driver(
                        track=track,
                        session=session,
                        identity=identity,
                    )
                )
                continue
            try:
                cleanup_driver_process(
                    session,
                    deadline_ns=(
                        time.monotonic_ns() + _DRIVER_CLEANUP_DEADLINE_NS
                    ),
                    monotonic_ns=time.monotonic_ns,
                )
            except Exception as error:
                outcomes.append(
                    self._recover_uncommanded_driver(
                        track=track,
                        session=session,
                        identity=identity,
                        observed_cleanup_error=error,
                    )
                )
                continue
            outcomes.append(
                _DriverCancellationOutcome(
                    track=track,
                    driver_id=session.full_id,
                    status="clean_cancel",
                    category=None,
                )
            )
        return tuple(outcomes)

    def _record_driver_control_failure(
        self,
        track: LiveTrack,
        *,
        manifest: Mapping[str, object],
        stage: str,
        request_bytes_may_have_been_sent: bool,
    ) -> None:
        provenance = {
            "stage": stage,
            "failure_monotonic_ns": self._monotonic_now(),
            "request_bytes_may_have_been_sent": request_bytes_may_have_been_sent,
            "attempt_count": 1,
            "retry_performed": False,
        }
        result = _driver_failure_result_from_provenance(track, provenance)
        raw_root = (
            self.private_root / "driver-results" / str(manifest["run_id"])
        )
        _require_contained(raw_root, self.private_root, "private driver result root")
        try:
            _write_file(
                raw_root / f"{track.value}.json",
                canonical_record(result),
                0o600,
            )
        except (ControllerError, OSError):
            # The closed journal provenance remains sufficient to reconstruct
            # the identical bytes if the private result write is the failure.
            pass
        _complete_request_attempt(
            self.journal_path,
            track,
            success=False,
            record_sha256=None,
            failure_provenance=provenance,
        )

    def run(self) -> Path:
        self._assert_no_readiness_poison()
        current = load_lifecycle_journal(self.journal_path)
        current_events = current["events"]
        assert isinstance(current_events, list)
        if any(
            event["event"] == "driver_start_intent"
            for event in current_events
        ):
            raise ControllerError(
                "driver start was already attempted; down is required"
            )
        if any(
            event["event"] == "readiness_diagnostic_complete"
            for event in current_events
        ):
            raise ControllerError(
                "readiness diagnostic is teardown-only; down is required"
            )
        state, manifest = self._load_and_reverify()
        runtime_root = _runtime_root(self.root, manifest)
        request_path = runtime_root / "requests.jsonl"
        if request_path.exists():
            raise ControllerError("central request was already attempted")
        journal = load_lifecycle_journal(self.journal_path)
        if journal["manifest_sha256"] != _digest_file(
            Path(str(state["manifest_path"]))
        ):
            raise ControllerError("request lifecycle journal does not bind active manifest")
        if any(
            request["status"] != "not_attempted"
            for request in journal["requests"].values()
        ):
            raise ControllerError("central request was already attempted; replay is forbidden")

        execution_nonce = str(journal["execution_nonce"])
        _require_sha256("request execution nonce", execution_nonce)
        readiness_nonce, deadline_ns, sessions = self._start_ready_driver_set(state)
        active_track = _TRACKS[0]
        active_stage = "instruction_write"
        instruction_delivery_started = False
        driver_terminal = False
        transport_provenance: Mapping[str, object] | None = None
        q_state: str | None = None
        headers: dict[str, str] = {}
        instruction_payload = b""
        try:
            private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
            records: list[dict[str, object]] = []
            comparison = {
                "method": "POST",
                "path": "/consequential/admin",
                "authorization_sha256": _digest_bytes(
                    AUTHORIZATION.encode("utf-8")
                ),
                "adversarial_headers": dict(ADVERSARIAL_HEADERS),
                "retry_control_headers": dict(RETRY_CONTROL_HEADERS),
            }
            comparison_sha = comparison_facts_sha256(comparison)
            objects = {
                (str(item["track"]), str(item["role"])): item
                for item in state["objects"]  # type: ignore[index]
                if type(item) is dict
            }
            definitions = {
                str(item["track"]): item
                for item in manifest["driver_definitions"]  # type: ignore[index]
                if type(item) is dict
            }

            for track in _TRACKS:
                active_track = track
                active_stage = "instruction_write"
                instruction_delivery_started = False
                driver_terminal = False
                transport_provenance = None
                session = sessions[track]
                issued = int(time.time())
                q_state = None
                if track is LiveTrack.SIGNED_STATE_ONLY:
                    q_state = issue_q_state(
                        _claims("kil-v3-signed", issued), private_key
                    )
                elif track is LiveTrack.SIGNED_PLUS_LOCAL_REDUCE:
                    q_state = issue_q_state(
                        _claims("kil-v3-local", issued), private_key
                    )
                if q_state is not None and int(time.time()) >= issued + 10:
                    raise ControllerError(
                        "signed-state request validity expired before intent"
                    )

                intent = claim_request_attempt(
                    self.journal_path,
                    track,
                    readiness_nonce=readiness_nonce,
                )
                headers = {
                    "authorization": AUTHORIZATION,
                    "x-request-id": str(manifest["request_id"]),
                    "x-kil-run-id": str(manifest["run_id"]),
                    **ADVERSARIAL_HEADERS,
                    **RETRY_CONTROL_HEADERS,
                }
                if q_state is not None:
                    headers["x-kil-q-state"] = q_state
                instruction = {
                    "schema_version": "kil.v3b1-driver-instruction.v1",
                    "track": track.value,
                    "method": "POST",
                    "path": "/consequential/admin",
                    "body_byte_count": 0,
                    "headers": headers,
                }
                instruction_payload = canonical_record(instruction)
                parse_driver_instruction(
                    instruction_payload, expected_track=track.value
                )
                q_state_sha256 = (
                    None
                    if q_state is None
                    else _digest_bytes(q_state.encode("utf-8"))
                )
                identity = {
                    **self._driver_identity_details(session, readiness_nonce),
                    "intent_id": intent["intent_id"],
                }
                journal_event(
                    self.journal_path,
                    "driver_instruction_write_intent",
                    identity,
                )
                instruction_delivery_started = True
                write_instruction(
                    session,
                    instruction_payload,
                    deadline_ns=deadline_ns,
                    monotonic_ns=self.monotonic_ns,
                )
                instruction = None
                instruction_payload = b""
                headers = {}
                q_state = None
                active_stage = "stdout_read"
                raw_result = read_driver_result(
                    session,
                    deadline_ns=deadline_ns,
                    monotonic_ns=self.monotonic_ns,
                )
                result = parse_driver_result(
                    raw_result, expected_track=track.value
                )
                if result["schema_version"] != "kil.v3b1-driver-result.v1":
                    raise DriverProtocolError(
                        "terminal driver result schema is invalid"
                    )
                active_stage = "process_wait"
                expected_exit = 0 if result["status"] == "complete" else 1
                attest_driver_result_exit(
                    session,
                    expected_exit_code=expected_exit,
                    deadline_ns=deadline_ns,
                    monotonic_ns=self.monotonic_ns,
                )
                driver_terminal = True
                active_stage = "termination"
                cleanup_driver_process(
                    session,
                    deadline_ns=time.monotonic_ns()
                    + _DRIVER_CLEANUP_DEADLINE_NS,
                    monotonic_ns=time.monotonic_ns,
                )

                result_sha = _digest_bytes(raw_result)
                definition = definitions[track.value]
                definition_sha = _digest_bytes(canonical_record(definition))
                raw_root = (
                    self.private_root
                    / "driver-results"
                    / str(manifest["run_id"])
                )
                _require_contained(
                    raw_root, self.private_root, "private driver result root"
                )
                raw_path = raw_root / f"{track.value}.json"
                _write_file(raw_path, raw_result, 0o600)
                journal_event(
                    self.journal_path,
                    "driver_result_persisted",
                    {
                        **identity,
                        "driver_definition_sha256": definition_sha,
                        "result_sha256": result_sha,
                    },
                )

                if result["status"] == "transport_failure":
                    transport_provenance = {
                        "attempt_count": result["attempt_count"],
                        "connect_monotonic_ns": result["connect_monotonic_ns"],
                        "driver_definition_sha256": definition_sha,
                        "driver_full_id": session.full_id,
                        "driver_request_bytes_may_have_been_sent": result[
                            "request_bytes_may_have_been_sent"
                        ],
                        "driver_result_schema_version": result["schema_version"],
                        "driver_result_sha256": result_sha,
                        "driver_status": result["status"],
                        "errno": result["errno"],
                        "errno_name": result["errno_name"],
                        "exception_class": result["exception_class"],
                        "failure_monotonic_ns": result["failure_monotonic_ns"],
                        "provenance_source": "linux_request_driver",
                        "request_bytes_may_have_been_sent": True,
                        "retry_performed": result["retry_performed"],
                        "send_monotonic_ns": result["send_monotonic_ns"],
                        "stage": result["stage"],
                        "track": track.value,
                    }
                    _validate_driver_transport_provenance(transport_provenance)
                    raise ControllerError(
                        "driver reported terminal transport failure"
                    )
                if result["status"] != "complete":
                    raise ControllerError("driver result status is terminal")

                expected_status = (
                    403
                    if track is LiveTrack.SIGNED_PLUS_LOCAL_REDUCE
                    else 200
                )
                if result["response_status"] != expected_status:
                    raise ControllerError("driver response status is invalid")

                driver_object = objects[(track.value, "driver")]
                record = {
                    "schema_version": "kil.v3b1-request.v2",
                    "run_id": manifest["run_id"],
                    "request_id": manifest["request_id"],
                    "track": track.value,
                    "method": "POST",
                    "path": "/consequential/admin",
                    "attempt_count": 1,
                    "retry_observed": False,
                    "retry_control_headers": dict(RETRY_CONTROL_HEADERS),
                    "authorization_sha256": comparison["authorization_sha256"],
                    "q_state_present": (
                        track is not LiveTrack.CREDENTIAL_POLICY_BASELINE
                    ),
                    "q_state_sha256": q_state_sha256,
                    "adversarial_headers": dict(ADVERSARIAL_HEADERS),
                    "comparison_facts_sha256": comparison_sha,
                    "send_monotonic_ns": result["send_monotonic_ns"],
                    "receive_monotonic_ns": result["receive_monotonic_ns"],
                    "client_response_status": result["response_status"],
                    "client_decision_digest": result["decision_digest"],
                    "request_transport": "in_network_request_driver",
                    "driver_role": "request_driver",
                    "driver_full_id": session.full_id,
                    "driver_image_id": driver_object["image_id"],
                    "driver_definition_sha256": definition_sha,
                    "driver_result_sha256": result_sha,
                }
                _request_closed(record)
                records.append(record)
                _write_file(request_path, _jsonl_payload(records), 0o444)
                record_sha = _digest_bytes(_canonical_bytes(record))
                journal_event(
                    self.journal_path,
                    "request_record_persisted",
                    {
                        "track": track.value,
                        "intent_id": intent["intent_id"],
                        "record_sha256": record_sha,
                    },
                )
                _complete_request_attempt(
                    self.journal_path,
                    track,
                    success=True,
                    record_sha256=record_sha,
                )
        except Exception as request_error:
            instruction_payload = b""
            headers = {}
            q_state = None
            failure_stage = _driver_control_failure_stage(
                active_stage, request_error
            )
            self._poison_request_driver_session(
                execution_nonce=execution_nonce,
                readiness_nonce=readiness_nonce,
            )
            request_status = None
            try:
                failed_journal = load_lifecycle_journal(self.journal_path)
                failed_requests = failed_journal["requests"]
                assert isinstance(failed_requests, dict)
                failed_request = failed_requests[active_track.value]
                assert isinstance(failed_request, dict)
                request_status = failed_request["status"]
            except Exception:
                request_status = None
            if request_status == "intent_persisted":
                try:
                    if transport_provenance is not None:
                        _complete_request_attempt(
                            self.journal_path,
                            active_track,
                            success=False,
                            record_sha256=None,
                            failure_provenance=transport_provenance,
                        )
                    else:
                        self._record_driver_control_failure(
                            active_track,
                            manifest=manifest,
                            stage=failure_stage,
                            request_bytes_may_have_been_sent=(
                                instruction_delivery_started
                            ),
                        )
                except Exception:
                    pass
            current_index = _TRACKS.index(active_track)
            if instruction_delivery_started or driver_terminal:
                self._cleanup_request_driver(sessions[active_track])
                cancel_index = current_index + 1
            else:
                cancel_index = current_index
            if cancel_index < len(_TRACKS):
                cancellation_outcomes = self._cancel_uncommanded_drivers(
                    first_track=_TRACKS[cancel_index],
                    readiness_nonce=readiness_nonce,
                    sessions=sessions,
                )
                expected_cancellations = _TRACKS[cancel_index:]
                if (
                    tuple(item.track for item in cancellation_outcomes)
                    != expected_cancellations
                    or any(
                        item.status
                        not in {"clean_cancel", "cleanup_complete"}
                        for item in cancellation_outcomes
                    )
                ):
                    self._poison_request_driver_session(
                        execution_nonce=execution_nonce,
                        readiness_nonce=readiness_nonce,
                    )
            raise ControllerError(
                "driver request failed terminally; teardown is required"
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

    def _complete_topology_absence_details(
        self, manifest: Mapping[str, object]
    ) -> dict[str, object]:
        """Reconstruct the exact fifteen/six identity commitment."""
        events = load_lifecycle_journal(self.journal_path)["events"]
        assert isinstance(events, list)
        containers: list[dict[str, str]] = []
        for item in manifest["containers"]:  # type: ignore[index]
            name = str(item["name"])
            transition, object_id = _creation_transition(
                events, "container", name
            )
            if transition != "complete" or object_id is None:
                raise ControllerError("complete lifecycle lacks container identity")
            containers.append({"id": object_id, "name": name})
        for track in _TRACKS:
            name = (
                f"kil-v3b1-validate-{_track_slug(track)}-"
                f"{str(manifest['content_identity_sha256'])[:12]}"
            )
            transition, object_id = _creation_transition(
                events, "validator", name
            )
            if transition != "complete" or object_id is None:
                raise ControllerError("complete lifecycle lacks validator identity")
            containers.append({"id": object_id, "name": name})
        networks: list[dict[str, str]] = []
        for item in manifest["networks"]:  # type: ignore[index]
            name = str(item["name"])
            transition, object_id = _creation_transition(events, "network", name)
            if transition != "complete" or object_id is None:
                raise ControllerError("complete lifecycle lacks network identity")
            networks.append({"id": object_id, "name": name})
        if len(containers) != 15 or len(networks) != 6:
            raise ControllerError("complete topology identity count is invalid")
        for label, identities in (
            ("container", containers),
            ("network", networks),
        ):
            if len({item["id"] for item in identities}) != len(identities):
                raise ControllerError(
                    f"complete topology {label} identity is duplicated"
                )
            if len({item["name"] for item in identities}) != len(identities):
                raise ControllerError(
                    f"complete topology {label} name is duplicated"
                )
        for identity in containers:
            if _removal_transition(events, "container", identity) != "complete":
                raise ControllerError("complete topology container is not absent")
        for identity in networks:
            if _removal_transition(events, "network", identity) != "complete":
                raise ControllerError("complete topology network is not absent")
        return {
            "container_count": 15,
            "network_count": 6,
            "container_identity_sha256": _digest_bytes(
                canonical_json(
                    sorted(containers, key=lambda item: (item["name"], item["id"]))
                ).encode("utf-8")
            ),
            "network_identity_sha256": _digest_bytes(
                canonical_json(
                    sorted(networks, key=lambda item: (item["name"], item["id"]))
                ).encode("utf-8")
            ),
            "survivor_containers": [],
            "survivor_networks": [],
        }

    def _attest_complete_topology_absence(
        self, manifest: Mapping[str, object]
    ) -> None:
        """Bind the exact fifteen/six owned identities to final empty inventories."""
        details = self._complete_topology_absence_details(manifest)
        events = load_lifecycle_journal(self.journal_path)["events"]
        assert isinstance(events, list)
        recorded = [
            event
            for event in events
            if event.get("event") == "topology_absence_attested"
        ]
        if recorded:
            if len(recorded) != 1 or recorded[0]["details"] != details:
                raise ControllerError("topology absence attestation changed")
            return
        journal_event(self.journal_path, "topology_absence_attested", details)

    def _require_complete_topology_absence(
        self, manifest: Mapping[str, object]
    ) -> None:
        """Refuse publication unless its exact full-topology absence is durable."""
        expected = self._complete_topology_absence_details(manifest)
        events = load_lifecycle_journal(self.journal_path)["events"]
        assert isinstance(events, list)
        recorded = [
            event
            for event in events
            if event.get("event") == "topology_absence_attested"
        ]
        if len(recorded) != 1 or recorded[0].get("details") != expected:
            raise ControllerError(
                "complete topology absence proof is required before publication"
            )

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
            copied_driver_results = self._private_driver_result_sources(manifest)
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
                    raw_driver_results=copied_driver_results,
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
                partial_requests = self._failure_request_records(manifest)
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
                    raw_driver_results=copied_driver_results,
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

    def _close_stranded_request_intents(
        self, manifest: Mapping[str, object]
    ) -> bool:
        """Close crash-stranded intents conservatively without any replay."""
        journal = load_lifecycle_journal(self.journal_path)
        requests = journal["requests"]
        events = journal["events"]
        assert isinstance(requests, dict)
        assert isinstance(events, list)
        recovered = False
        for track in _TRACKS:
            request = requests[track.value]
            assert isinstance(request, dict)
            if request["status"] != "intent_persisted":
                continue
            intent_id = request["intent_id"]
            instruction_intents = [
                event
                for event in events
                if event.get("event") == "driver_instruction_write_intent"
                and isinstance(event.get("details"), dict)
                and event["details"].get("track") == track.value
                and event["details"].get("intent_id") == intent_id
            ]
            if len(instruction_intents) > 1:
                raise ControllerError("stranded driver instruction intent is duplicated")
            self._record_driver_control_failure(
                track,
                manifest=manifest,
                stage=("termination" if instruction_intents else "instruction_write"),
                request_bytes_may_have_been_sent=bool(instruction_intents),
            )
            recovered = True
            journal = load_lifecycle_journal(self.journal_path)
            requests = journal["requests"]
            events = journal["events"]
            assert isinstance(requests, dict)
            assert isinstance(events, list)
        return recovered

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
                if journal["schema_version"] == JOURNAL_SCHEMA:
                    self._record_after_foreign_profile_snapshot()
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
            if not any(event["event"] == "colima_delete_complete" for event in events):
                journal_event(
                    self.journal_path,
                    "colima_delete_complete",
                    {"profile": LAB_IDENTITY, "verified_absent": True},
                )
            foreign_comparison: dict[str, object] | None = None
            if journal["schema_version"] == JOURNAL_SCHEMA:
                _, _, foreign_comparison = (
                    self._record_after_foreign_profile_snapshot()
                )
            journal = load_lifecycle_journal(self.journal_path)
            events = journal["events"]
            assert isinstance(events, list)
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
            if any(event["event"] == "up_complete" for event in events):
                self._require_complete_topology_absence(manifest)

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
                if (
                    failure_transition is None
                    and foreign_comparison is not None
                    and foreign_comparison["unchanged"] is not True
                ):
                    categories = foreign_comparison["mismatch_categories"]
                    assert isinstance(categories, list)
                    failure_details = {
                        "run_id": manifest["run_id"],
                        "evidence_rejection": (
                            "foreign_profile_mismatch:" + ",".join(categories)
                        ),
                        "replacement": _FAILURE_BUNDLE_REPLACEMENT,
                    }
                    updated = journal_event(
                        self.journal_path,
                        "post_teardown_failure_bundle_intent",
                        failure_details,
                    )
                    updated_events = updated["events"]
                    assert isinstance(updated_events, list)
                    events = updated_events
                    failure_transition = _post_teardown_failure_transition(
                        events, str(manifest["run_id"])
                    )
                    assert failure_transition is not None
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
                            self._private_provisional_root(),
                            manifest,
                            requests=self._failure_request_records(manifest),
                            raw_driver_results=self._private_driver_result_sources(
                                manifest
                            ),
                            reset=True,
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
                foreign_attestation = (
                    _journal_foreign_profile_attestation(
                        events, str(journal["execution_nonce"])
                    )
                    if _bundle_generation(manifest.get("schema_version")) == 3
                    else None
                )
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
                    foreign_profile_attestation=foreign_attestation,
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
            recovered_foreign_attestation = (
                _journal_foreign_profile_attestation(
                    recovered_events,
                    str(recovered_journal["execution_nonce"]),
                )
                if _bundle_generation(manifest.get("schema_version")) == 3
                else None
            )
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
                foreign_profile_attestation=recovered_foreign_attestation,
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
            journal_event(
                self.journal_path,
                "colima_delete_complete",
                {"profile": LAB_IDENTITY, "verified_absent": True},
            )
            if journal["schema_version"] == JOURNAL_SCHEMA:
                self._record_after_foreign_profile_snapshot()
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
        self._assert_only_recorded_managed(state, expect_present=True)
        objects = state["objects"]
        assert isinstance(objects, list)
        transient_objects = state.get("transient_objects", [])
        assert isinstance(transient_objects, list)
        drivers = [item for item in objects if item["role"] == "driver"]
        running_ordered = [
            item
            for role in _TEARDOWN_SERVICE_ROLES
            for item in objects
            if item["role"] == role
        ] + list(transient_objects)
        ordered = [
            item
            for role in _TEARDOWN_REMOVAL_ROLES
            for item in objects
            if item["role"] == role
        ] + list(transient_objects)
        lifecycle_events = journal["events"]
        assert isinstance(lifecycle_events, list)
        envoy_attachments = _envoy_attachment_expectations(
            lifecycle_events, manifest
        )
        recorded_attachments = state.get("envoy_attachments")
        if (
            recorded_attachments is not None
            and recorded_attachments != envoy_attachments
        ):
            raise ControllerError("recovered Envoy attachment state changed")
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
        stranded_request_recovered = self._close_stranded_request_intents(
            manifest
        )
        driver_authorities = {
            str(item["track"]): self._quiesce_driver_for_teardown(
                item, manifest
            )
            for item in drivers
        }
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
                self._stop_and_attest_container(
                    item,
                    manifest,
                    envoy_attachment=(
                        envoy_attachments[str(item["track"])]
                        if item["role"] == "envoy"
                        else None
                    ),
                )
        else:
            current_journal = load_lifecycle_journal(self.journal_path)
            requests_state = current_journal["requests"]
            assert isinstance(requests_state, dict)
            attempted_complete = all(
                item["status"] == "completed" for item in requests_state.values()
            ) and not stranded_request_recovered and all(
                authority["request_eligible"] is True
                for authority in driver_authorities.values()
            )
            freeze = self._freeze_before_service_teardown(
                state,
                manifest,
                attempted_complete=attempted_complete,
                transient_objects=transient_objects,
                envoy_attachments=envoy_attachments,
            )
            output, source_attestations, completed, evidence_rejection = (
                self._prepare_teardown_evidence(
                    manifest, objects, freeze
                )
            )

        def inspect_removal_candidate(
            record: Mapping[str, object],
        ) -> dict[str, object]:
            allowed_driver_states = None
            if record["role"] == "driver":
                current_events = load_lifecycle_journal(
                    self.journal_path
                )["events"]
                assert isinstance(current_events, list)
                authority = _driver_recovery_authority(
                    current_events,
                    str(record["track"]),
                    str(record["id"]),
                )
                allowed_driver_states = set(
                    authority["allowed_states"]  # type: ignore[arg-type]
                )
            if record["role"] == "validator":
                current = self._inspect_validation_container(
                    str(record["id"]),
                    manifest,
                    LiveTrack(str(record["track"])),
                )
            else:
                inspect_kwargs: dict[str, object] = {
                    "require_running": False,
                    "envoy_attachment": (
                        envoy_attachments[str(record["track"])]
                        if record["role"] == "envoy"
                        else None
                    ),
                }
                if allowed_driver_states is not None:
                    inspect_kwargs["allowed_driver_states"] = allowed_driver_states
                current = self._inspect_container(
                    str(record["id"]),
                    manifest,
                    str(record["role"]),
                    str(record["track"]),
                    **inspect_kwargs,
                )
            current_matches = (
                current == record
                if record["role"] == "validator"
                else _container_attestation_matches(
                    record,
                    current,
                    allow_stopped=True,
                    allowed_driver_states=allowed_driver_states,
                )
            )
            if not current_matches:
                raise ControllerError("container changed before exact removal")
            return current

        fresh_ordered = [
            inspect_removal_candidate(item) for item in ordered
        ]
        remaining_containers = list(fresh_ordered)
        remaining_networks = list(state["network_objects"])
        for item in fresh_ordered:
            inspect_removal_candidate(item)
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
            if item["role"] == "driver":
                frontend = next(
                    network
                    for network in remaining_networks
                    if network["track"] == item["track"]
                    and network.get("segment") == "frontend"
                )
                remaining_objects = [
                    record
                    for record in remaining_containers
                    if record["role"] != "validator"
                ]
                member_options = _network_member_identity_options(
                    remaining_objects,
                    manifest,
                    str(item["track"]),
                    "frontend",
                    envoy_attachments[str(item["track"])],
                )
                self._inspect_network(
                    str(frontend["id"]),
                    manifest,
                    str(item["track"]),
                    segment="frontend",
                    expected_members=member_options[0],
                    allowed_member_options=member_options,
                    envoy_attachment=envoy_attachments[str(item["track"])],
                    require_complete_membership=False,
                )
        networks = state["network_objects"]
        assert isinstance(networks, list)
        for item in networks:
            current = self._inspect_network(
                str(item["id"]),
                manifest,
                str(item["track"]),
                segment=str(item.get("segment", "backend")),
                expected_members={},
                allowed_member_options=({},),
                envoy_attachment=(
                    envoy_attachments[str(item["track"])]
                    if str(item.get("segment", "backend")) == "frontend"
                    else None
                ),
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
        if up_complete_observed:
            self._attest_complete_topology_absence(manifest)
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
        foreign_comparison: dict[str, object] | None = None
        if journal["schema_version"] == JOURNAL_SCHEMA:
            _, _, foreign_comparison = (
                self._record_after_foreign_profile_snapshot()
            )
        global_after = self._capture_global_context()
        if global_after != journal["global_context_before"]:
            raise ControllerError("global Docker context changed during lifecycle")
        if (
            foreign_comparison is not None
            and foreign_comparison["unchanged"] is not True
            and output is not None
        ):
            categories = foreign_comparison["mismatch_categories"]
            assert isinstance(categories, list)
            output = None
            source_attestations = []
            completed = False
            evidence_rejection = (
                "foreign_profile_mismatch:" + ",".join(categories)
            )
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
                self._private_provisional_root(),
                manifest,
                requests=self._failure_request_records(manifest),
                raw_driver_results=self._private_driver_result_sources(manifest),
                reset=True,
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
        if up_complete_observed:
            self._require_complete_topology_absence(manifest)
        foreign_attestation = (
            _journal_foreign_profile_attestation(
                events, str(journal["execution_nonce"])
            )
            if _bundle_generation(manifest.get("schema_version")) == 3
            else None
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
            foreign_profile_attestation=foreign_attestation,
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
    for command in ("preflight", "up", "readiness", "run", "collect", "down"):
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
