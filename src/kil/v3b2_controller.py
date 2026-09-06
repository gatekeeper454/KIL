"""Closed V3B-2a Kind/Calico lifecycle orchestration."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import time
from typing import Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kil.canonical import canonical_json
from kil.q_state import QStateClaims, issue_q_state
from kil.v3b1_driver_protocol import canonical_record, parse_instruction
from kil.v3b2_contracts import (
    JOURNAL_SCHEMA,
    LAB_IDENTITY,
    NOMINAL_REQUEST_ID,
    TRACK_NAMESPACES,
    TRACKS,
    V3B2Profile,
)
from kil.v3b2_evidence import CapturedSource, SourceIdentity, publish_bundle, verify_bundle
from kil.v3b2_journal import (
    Command,
    JournalInputs,
    OwnedIdentity,
    RecoveryObservation,
    append_event,
    colima_start_command,
    create_journal,
    docker_context_command,
    kind_create_command,
    kind_delete_command,
    kubectl_apply_command,
    kubectl_apply_calico_command,
    kubectl_attach_command,
    kubectl_quiesce_command,
    load_journal,
    recovery_plan,
)
from kil.v3b2_manifests import (
    WorkloadIdentity,
    expected_object_keys,
    expected_policy_graph,
    render_kind_config,
    render_objects,
)


_HEX40 = set("0123456789abcdef")
_PROFILE_STATES = {"Running", "Stopped"}
_EXPECTED_TUPLE = (("permit", 200, 1), ("permit", 200, 1), ("deny", 403, 0))
_TOOL_VERSION_ARGV = {
    "docker": ("--version",),
    "kind": ("version",),
    "kubectl": ("version", "--client", "-o", "json"),
}
_TOOL_LOCK_FIELDS = frozenset({"schema_version", "profile_sha256", "tools"})
_TOOL_ROW_FIELDS = frozenset({
    "archive_sha256", "byte_size", "checksum_attestation",
    "executable_sha256", "source_url", "version_output",
})
_ACCEPTED_V3B1_RUN = "v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94"
_ACCEPTED_V3B1_MANIFEST_SHA256 = "fa39212f1ffad95a1b5a674021ac5ce4ed9458025ce0dcc80077070355141cd0"
_ACCEPTED_V3B1_COMMITMENT = "8d5ea5e8e12913945006af636bd674c39681a96b6d09a045e1b071ca77429ec2"


class ControllerError(RuntimeError):
    """A closed stage code for a lifecycle failure."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    def __post_init__(self) -> None:
        if type(self.returncode) is not int or type(self.stdout) is not str or type(self.stderr) is not str:
            raise ControllerError("invalid_command_result")


class CommandRunner(Protocol):
    def run(self, command: Command) -> CommandResult: ...


class SubprocessCommandRunner:
    """The sole process-execution boundary; commands arrive already validated."""

    def __init__(self, repository: Path | None = None, tools: Path | None = None) -> None:
        self.repository = repository
        self.tools = tools
        if repository is not None and (not repository.is_absolute() or repository.resolve() != repository):
            raise ControllerError("invalid_runner_paths")
        if tools is not None and (not tools.is_absolute() or tools.resolve() != tools):
            raise ControllerError("invalid_runner_paths")

    def run(self, command: Command) -> CommandResult:
        if type(command) is not Command:
            raise ControllerError("invalid_command")
        command.__post_init__()
        environment = os.environ.copy()
        environment.update(dict(command.env))
        argv = command.argv
        if self.tools is not None and argv[0] in {"docker", "kind", "kubectl"}:
            argv = (str(self.tools / argv[0]), *argv[1:])
        try:
            completed = subprocess.run(
                argv,
                input=command.stdin,
                capture_output=True,
                check=False,
                timeout=command.timeout_s,
                env=environment,
                cwd=self.repository,
            )
        except (OSError, subprocess.SubprocessError):
            raise ControllerError("command_execution_failed") from None
        return CommandResult(
            completed.returncode,
            completed.stdout.decode("utf-8", errors="replace"),
            completed.stderr.decode("utf-8", errors="replace"),
        )


@dataclass(frozen=True, slots=True)
class ControllerPaths:
    repository: Path
    profile: Path
    tools: Path
    private: Path
    public: Path

    def __post_init__(self) -> None:
        if any(not isinstance(getattr(self, field.name), Path) for field in fields(self)):
            raise ControllerError("invalid_paths")
        root = self.repository
        if not root.is_absolute() or ".." in root.parts or root.resolve() != root:
            raise ControllerError("invalid_paths")
        for field in fields(self)[1:]:
            path = getattr(self, field.name)
            if not path.is_absolute() or ".." in path.parts or path.resolve(strict=False) != path:
                raise ControllerError("invalid_paths")
            try:
                path.relative_to(root)
            except ValueError:
                raise ControllerError("invalid_paths") from None


@dataclass(frozen=True, slots=True)
class NominalBundle:
    run_id: str
    result_tuple: tuple[tuple[str, int, int], ...]
    instructions_sent: int
    owned_teardown: bool


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _read_regular(path: Path, maximum: int) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise ControllerError("content_identity_failed") from None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ControllerError("content_identity_failed")
        payload = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
        if len(payload) != before.st_size or (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ControllerError("content_identity_failed")
        return payload
    finally:
        os.close(descriptor)


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError:
        raise ControllerError("private_materialization_failed") from None
    try:
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
    except OSError:
        path.unlink(missing_ok=True)
        raise ControllerError("private_materialization_failed") from None
    finally:
        os.close(descriptor)


class V3B2Controller:
    """One-use controller for one journal-bound owned lifecycle."""

    def __init__(self, paths: ControllerPaths, runner: CommandRunner) -> None:
        if type(paths) is not ControllerPaths or not hasattr(runner, "run"):
            raise ControllerError("invalid_controller_inputs")
        paths.__post_init__()
        self.paths = paths
        self.runner = runner
        self.profile = V3B2Profile.load(paths.profile)
        self.journal_path = paths.private / "journal.json"
        self.kubeconfig = paths.private / "kubeconfig"
        self.kind_config = paths.private / "kind-config.yaml"
        self.docker_config = paths.private / "docker-config"
        self.runtime_projection_path = paths.private / "runtime-projection.json"
        self.foreign_snapshot_path = paths.private / "foreign-before.json"
        self.docker_host = f"unix://{Path.home()}/.colima/{LAB_IDENTITY}/docker.sock"
        self.run_digest = secrets.token_hex(32)
        self.run_id = "v3b2-" + self.run_digest
        self.execution_nonce = secrets.token_hex(32)
        self._prepared = False
        self._up = False
        self._used_mode: str | None = None
        self._foreign_before: tuple[tuple[str, str], ...] = ()
        self._foreign_records_before: list[dict[str, object]] = []
        self._foreign_records_after: list[dict[str, object]] = []
        self._context_after = ""
        self._context_before = ""
        self._identity = OwnedIdentity(
            LAB_IDENTITY, self.docker_host, LAB_IDENTITY, str(self.kubeconfig), None, None
        )
        self._drivers: list[tuple[str, str, str]] = []
        self._canceled: set[str] = set()
        self._events: list[tuple[str, dict[str, object]]] = []
        self._captured_sources: list[CapturedSource] = []
        self._tool_identities: dict[str, str] = {}
        self._source_commit = ""
        self._profile_sha256 = ""
        self._workload: WorkloadIdentity | None = None
        self._application_records = 0
        self._runtime_projection: dict[str, object] | None = None
        self._source_attestations: list[dict[str, object]] = []
        self._request_cases: list[dict[str, object]] = []
        self.published_path: Path | None = None
        self.owned_absence_proven = False
        if self.journal_path.exists():
            self._hydrate()

    @property
    def events(self) -> tuple[tuple[str, dict[str, object]], ...]:
        return tuple(self._events)

    def _run(self, command: Command, stage: str, *, allow_absent: bool = False) -> CommandResult:
        try:
            result = self.runner.run(command)
        except Exception:
            raise ControllerError(stage) from None
        if type(result) is not CommandResult:
            raise ControllerError(stage)
        if result.returncode != 0 and not allow_absent:
            raise ControllerError(stage)
        return result

    def _hydrate(self) -> None:
        value = load_journal(self.journal_path)
        self.run_digest = str(value["run_id"])
        self.run_id = "v3b2-" + self.run_digest
        self.execution_nonce = str(value["execution_nonce"])
        self._foreign_before = tuple(tuple(item) for item in value["foreign_profiles_before"])  # type: ignore[arg-type]
        self._context_before = str(value["global_context_before"])
        raw_identity = value["owned_identity"]
        assert isinstance(raw_identity, dict)
        self._identity = OwnedIdentity(**raw_identity)
        raw_events = value["events"]
        assert isinstance(raw_events, list)
        self._events = [(str(item["event"]), dict(item["details"])) for item in raw_events]
        for name, details in self._events:
            if name == "cluster_create_complete":
                self._identity = OwnedIdentity(
                    LAB_IDENTITY, str(details["docker_host"]), LAB_IDENTITY,
                    str(details["kubeconfig"]), str(details["cluster_incarnation_uid"]),
                    str(details["node_container_id"]),
                )
            elif name == "driver_start_complete":
                self._drivers.append((str(details["namespace"]), str(details["pod"]), str(details["uid"])))
            elif name == "driver_cancel_complete":
                self._canceled.add(str(details["namespace"]))
        names = {name for name, _details in self._events}
        self._prepared = True
        self._up = "cluster_create_complete" in names and "cluster_delete_complete" not in names
        self.owned_absence_proven = "profile_absence_proof_complete" in names
        if self._events:
            self._used_mode = str(value["lifecycle_mode"])
        if self.runtime_projection_path.exists():
            try:
                projection = json.loads(_read_regular(self.runtime_projection_path, 8 * 1024 * 1024))
            except (json.JSONDecodeError, UnicodeError):
                raise ControllerError("runtime_inventory_invalid") from None
            if type(projection) is not dict:
                raise ControllerError("runtime_inventory_invalid")
            self._runtime_projection = projection
        if self.foreign_snapshot_path.exists():
            try:
                rows = json.loads(_read_regular(self.foreign_snapshot_path, 1024 * 1024))
            except (json.JSONDecodeError, UnicodeError):
                raise ControllerError("ambiguous_profile_inventory") from None
            if type(rows) is not list or any(type(row) is not dict for row in rows):
                raise ControllerError("ambiguous_profile_inventory")
            self._foreign_records_before = [dict(row) for row in rows]

    def _select_mode(self, mode: str) -> None:
        if not self.journal_path.exists():
            return
        value = load_journal(self.journal_path)
        events = value["events"]
        if events:
            if value["lifecycle_mode"] != mode:
                raise ControllerError("lifecycle_mode_mismatch")
            return
        if value["lifecycle_mode"] == mode:
            return
        raw_identity = value["owned_identity"]
        assert isinstance(raw_identity, dict)
        inputs = JournalInputs(
            schema_version=str(value["schema_version"]), run_id=str(value["run_id"]),
            execution_nonce=str(value["execution_nonce"]), source_commit=str(value["source_commit"]),
            profile_sha256=str(value["profile_sha256"]), phase="prepared",
            global_context_before=str(value["global_context_before"]),
            foreign_profiles_before=tuple(tuple(item) for item in value["foreign_profiles_before"]),  # type: ignore[arg-type]
            expected_objects=tuple(value["expected_objects"]),  # type: ignore[arg-type]
            owned_identity=OwnedIdentity(**raw_identity), lifecycle_mode=mode,
        )
        self.journal_path.unlink()
        create_journal(self.journal_path, inputs)

    def _journal_pair(
        self,
        family: str,
        intent: dict[str, object],
        action,
        complete: dict[str, object] | None = None,
    ) -> CommandResult:
        append_event(self.journal_path, family + "_intent", intent)
        result = action()
        append_event(self.journal_path, family + "_complete", intent if complete is None else complete)
        self._events.extend(((family + "_intent", dict(intent)), (family + "_complete", dict(intent if complete is None else complete))))
        return result

    @staticmethod
    def _profiles(payload: str) -> tuple[tuple[str, str], ...]:
        try:
            value = json.loads(payload)
        except (json.JSONDecodeError, UnicodeError):
            raise ControllerError("ambiguous_profile_inventory") from None
        if type(value) is not list or len(value) > 1024:
            raise ControllerError("ambiguous_profile_inventory")
        records: list[tuple[str, str]] = []
        for item in value:
            if type(item) is not dict or not {"name", "status"}.issubset(item):
                raise ControllerError("ambiguous_profile_inventory")
            name, status = item["name"], item["status"]
            if type(name) is not str or not name or type(status) is not str or status not in _PROFILE_STATES:
                raise ControllerError("ambiguous_profile_inventory")
            records.append((name, status))
        if len({name for name, _status in records}) != len(records):
            raise ControllerError("ambiguous_profile_inventory")
        return tuple(sorted(records))

    @staticmethod
    def _foreign_records(payload: str) -> list[dict[str, object]]:
        try:
            value = json.loads(payload)
        except (json.JSONDecodeError, UnicodeError):
            try:
                value = [json.loads(line) for line in payload.splitlines() if line.strip()]
            except (json.JSONDecodeError, UnicodeError):
                raise ControllerError("ambiguous_profile_inventory") from None
        if type(value) is dict:
            value = [value]
        fields = frozenset({"name", "status", "arch", "cpus", "memory", "disk", "runtime"})
        result: list[dict[str, object]] = []
        if type(value) is not list:
            raise ControllerError("ambiguous_profile_inventory")
        for raw in value:
            if type(raw) is not dict or frozenset(raw) != fields:
                raise ControllerError("ambiguous_profile_inventory")
            if (
                type(raw["name"]) is not str or not raw["name"]
                or type(raw["status"]) is not str or raw["status"] not in _PROFILE_STATES
                or type(raw["arch"]) is not str or raw["arch"] not in {"aarch64", "arm64", "amd64", "x86_64"}
                or type(raw["runtime"]) is not str or raw["runtime"] not in {"docker", "containerd"}
                or any(type(raw[name]) is not int or raw[name] <= 0 for name in ("cpus", "memory", "disk"))
            ):
                raise ControllerError("ambiguous_profile_inventory")
            result.append(dict(raw))
        if len({str(row["name"]) for row in result}) != len(result):
            raise ControllerError("ambiguous_profile_inventory")
        return sorted(result, key=lambda row: str(row["name"]))

    def _verify_tool_lock(self) -> dict[str, str]:
        lock_path = self.paths.tools.parent / "locks/v3b-tools.json"
        payload = _read_regular(lock_path, 256 * 1024)
        try:
            value = json.loads(payload)
        except (json.JSONDecodeError, UnicodeError):
            raise ControllerError("tool_identity_mismatch") from None
        if (
            type(value) is not dict
            or frozenset(value) != _TOOL_LOCK_FIELDS
            or payload != _canonical_bytes(value)
            or value.get("schema_version") != "kil.v3b-tools-lock.v1"
            or type(value.get("tools")) is not dict
            or frozenset(value["tools"]) != frozenset(_TOOL_VERSION_ARGV)
        ):
            raise ControllerError("tool_identity_mismatch")
        legacy_profile = _read_regular(self.paths.repository / "deploy/kind/v3b-profile.json", 64 * 1024)
        if value.get("profile_sha256") != _digest(legacy_profile):
            raise ControllerError("tool_identity_mismatch")
        verified: dict[str, str] = {}
        for name, version_argv in _TOOL_VERSION_ARGV.items():
            row = value["tools"].get(name)
            binary = self.paths.tools / name
            if (
                type(row) is not dict
                or frozenset(row) != _TOOL_ROW_FIELDS
                or type(row.get("byte_size")) is not int
                or type(row.get("executable_sha256")) is not str
                or type(row.get("version_output")) is not str
            ):
                raise ControllerError("tool_identity_mismatch")
            binary_payload = _read_regular(binary, 256 * 1024 * 1024)
            try:
                mode = os.stat(binary, follow_symlinks=False).st_mode
            except OSError:
                raise ControllerError("tool_identity_mismatch") from None
            if (
                not mode & stat.S_IXUSR
                or len(binary_payload) != row["byte_size"]
                or _digest(binary_payload) != row["executable_sha256"]
            ):
                raise ControllerError("tool_identity_mismatch")
            version = self._run(
                Command((str(binary), *version_argv), 30),
                "tool_identity_mismatch",
            )
            actual = (version.stdout + version.stderr).strip()
            if actual != row["version_output"]:
                raise ControllerError("tool_identity_mismatch")
            verified[name] = _digest(binary_payload)
        colima = self._run(Command(("colima", "version"), 30), "tool_identity_mismatch")
        lima = self._run(Command(("limactl", "--version"), 30), "tool_identity_mismatch")
        if (
            colima.stdout.strip() != f"colima version {self.profile.colima_version}"
            or lima.stdout.strip() != f"limactl version {self.profile.lima_version}"
        ):
            raise ControllerError("tool_identity_mismatch")
        return verified

    def _accepted_workload(self) -> WorkloadIdentity:
        bundle = self.paths.repository / "artifacts/generated/v3b1-local-envoy" / _ACCEPTED_V3B1_RUN
        manifest_path = bundle / "manifest.json"
        try:
            manifest_bytes = _read_regular(manifest_path, 1024 * 1024)
            manifest = json.loads(manifest_bytes)
            images = manifest["immutable_images"]
            kil_image = images["kil_image_id"]
            envoy_image = images["envoy_digest"]
        except Exception:
            raise ControllerError("content_identity_failed") from None
        if (
            manifest.get("schema_version") != "kil.v3b1-public-manifest.v3"
            or _digest(manifest_bytes) != _ACCEPTED_V3B1_MANIFEST_SHA256
            or manifest.get("promotion_status") != "not_promoted"
            or manifest.get("public_commitment_sha256") != _ACCEPTED_V3B1_COMMITMENT
            or type(kil_image) is not str
            or type(envoy_image) is not str
        ):
            raise ControllerError("content_identity_failed")
        try:
            return WorkloadIdentity(self.run_id, kil_image, envoy_image)
        except Exception:
            raise ControllerError("content_identity_failed") from None

    def _runtime_from_kubernetes(self, value: object) -> dict[str, object]:
        if self._workload is None or type(value) is not dict or value.get("apiVersion") != "v1" or value.get("kind") != "List" or type(value.get("items")) is not list:
            raise ControllerError("runtime_inventory_invalid")
        items = value["items"]
        expected_keys = set(expected_object_keys(self.profile)) | {
            ("v1", "Namespace", "", "kube-system"),
            ("apps/v1", "DaemonSet", "kube-system", "calico-node"),
            ("apps/v1", "Deployment", "kube-system", "calico-kube-controllers"),
        }
        indexed: dict[tuple[str, str, str, str], dict[str, object]] = {}
        for item in items:
            if type(item) is not dict or type(item.get("metadata")) is not dict:
                raise ControllerError("runtime_inventory_invalid")
            metadata = item["metadata"]
            key = (item.get("apiVersion"), item.get("kind"), metadata.get("namespace", ""), metadata.get("name"))
            if any(type(part) is not str for part in key) or key in indexed:
                raise ControllerError("runtime_inventory_invalid")
            indexed[key] = item
        if not expected_keys.issubset(indexed):
            raise ControllerError("runtime_inventory_invalid")
        objects = []
        for key in sorted(expected_keys):
            metadata = indexed[key]["metadata"]
            assert type(metadata) is dict
            uid, version = metadata.get("uid"), metadata.get("resourceVersion")
            if type(uid) is not str or type(version) is not str:
                raise ControllerError("runtime_inventory_invalid")
            objects.append({"api_version": key[0], "kind": key[1], "namespace": key[2], "name": key[3], "uid": uid, "resource_version": version})
        namespaces = sorted(key[3] for key in indexed if key[1] == "Namespace" and key[0] == "v1")
        if namespaces != sorted((*self.profile.system_namespaces, *self.profile.application_namespaces)):
            raise ControllerError("runtime_inventory_invalid")
        pod_images: list[dict[str, object]] = []
        expected_workload_image = "kil.local/kil-v3b2:sha256-" + self._workload.kil_image_id.removeprefix("sha256:")
        for key, item in sorted(indexed.items()):
            if key[1] != "Pod":
                continue
            namespace, pod = key[2], key[3]
            if namespace not in {*self.profile.application_namespaces, "kube-system"}:
                continue
            if namespace == "kube-system" and not (pod.startswith("calico-node-") or pod.startswith("calico-kube-controllers-")):
                continue
            metadata, status = item.get("metadata"), item.get("status")
            if type(metadata) is not dict or type(status) is not dict:
                raise ControllerError("runtime_inventory_invalid")
            conditions = status.get("conditions")
            ready = type(conditions) is list and any(type(condition) is dict and condition.get("type") == "Ready" and condition.get("status") == "True" for condition in conditions)
            for field, container_type in (("initContainerStatuses", "init"), ("containerStatuses", "regular")):
                rows = status.get(field, [])
                if type(rows) is not list:
                    raise ControllerError("runtime_inventory_invalid")
                for row in rows:
                    if type(row) is not dict:
                        raise ControllerError("runtime_inventory_invalid")
                    container = row.get("name")
                    role = {"upgrade-ipam": "calico-cni", "install-cni": "calico-cni", "ebpf-bootstrap": "calico-node", "calico-node": "calico-node", "calico-kube-controllers": "calico-kube-controllers"}.get(container, "workload")
                    image, image_id = row.get("image"), row.get("imageID")
                    expected_image = dict(self.profile.calico_images).get({"calico-cni": "cni", "calico-node": "node", "calico-kube-controllers": "kube_controllers"}.get(role, ""))
                    if role == "workload":
                        expected_image = self._workload.envoy_image_digest if container == "envoy" else expected_workload_image
                    if type(container) is not str or image != expected_image or type(image_id) is not str or not ready:
                        raise ControllerError("runtime_image_identity_mismatch")
                    expected_digest = str(image).rsplit(":", 1)[-1].removeprefix("sha256-")
                    if image_id.rsplit(":", 1)[-1] != expected_digest:
                        raise ControllerError("runtime_image_identity_mismatch")
                    pod_images.append({"image_role": role, "container_type": container_type, "namespace": namespace, "pod": pod, "container": container, "uid": metadata.get("uid"), "resource_version": metadata.get("resourceVersion"), "image": image, "image_id": image_id, "ready": ready})
        endpoints: list[dict[str, object]] = []
        for key, item in sorted(indexed.items()):
            if key[1] != "Endpoints" or key[2] not in self.profile.application_namespaces or key[3] not in {"authz", "envoy", "target"}:
                continue
            subsets = item.get("subsets")
            if type(subsets) is not list or len(subsets) != 1 or type(subsets[0]) is not dict:
                raise ControllerError("runtime_inventory_invalid")
            addresses = sorted(row.get("ip") for row in subsets[0].get("addresses", []) if type(row) is dict)
            ports = subsets[0].get("ports")
            if type(ports) is not list:
                raise ControllerError("runtime_inventory_invalid")
            for port in ports:
                if type(port) is not dict:
                    raise ControllerError("runtime_inventory_invalid")
                endpoints.append({"source_kind": "Endpoints", "source_name": key[3], "namespace": key[2], "service": key[3], "addresses": addresses, "port_name": port.get("name"), "protocol": port.get("protocol"), "port": port.get("port")})
        rendered = json.loads(render_objects(self.profile, self._workload))["items"]
        expected_specs = {(item["metadata"]["namespace"], item["metadata"]["name"]): item["spec"] for item in rendered if item["kind"] == "NetworkPolicy"}
        actual_policies = {(key[2], key[3]): item.get("spec") for key, item in indexed.items() if key[1] == "NetworkPolicy"}
        if actual_policies != expected_specs:
            raise ControllerError("runtime_policy_mismatch")
        if len(objects) != 63 or len(pod_images) != 17 or len(endpoints) != 9:
            raise ControllerError("runtime_inventory_invalid")
        calico_node = indexed[("apps/v1", "DaemonSet", "kube-system", "calico-node")].get("status")
        calico_controller = indexed[("apps/v1", "Deployment", "kube-system", "calico-kube-controllers")].get("status")
        if type(calico_node) is not dict or type(calico_controller) is not dict:
            raise ControllerError("runtime_inventory_invalid")
        readiness = {"node_desired": calico_node.get("desiredNumberScheduled"), "node_ready": calico_node.get("numberReady"), "controller_desired": calico_controller.get("replicas"), "controller_ready": calico_controller.get("readyReplicas")}
        if set(readiness.values()) != {1}:
            raise ControllerError("runtime_readiness_failed")
        cluster_uid = indexed[("v1", "Namespace", "", "kube-system")]["metadata"]["uid"]
        return {
            "topology_attestation": {"cluster_incarnation_uid": cluster_uid, "node_container_id": self._identity.node_container_id, "namespaces": namespaces, "objects": objects, "pod_images": sorted(pod_images, key=lambda row: tuple(str(row[name]) for name in ("image_role", "container_type", "namespace", "pod", "container"))), "endpoints": sorted(endpoints, key=lambda row: tuple(str(row[name]) for name in ("source_kind", "source_name", "namespace", "service"))), "calico_readiness": readiness},
            "policy_attestation": {"edges": [{"namespace": edge.namespace, "source_roles": list(edge.source_roles), "destination_namespace": edge.destination_namespace, "destination_roles": list(edge.destination_roles), "protocol_ports": [list(pair) for pair in edge.protocol_ports]} for edge in sorted(expected_policy_graph(self.profile))]},
        }

    def preflight(self) -> dict[str, object]:
        if self._prepared or self.journal_path.exists():
            raise ControllerError("lifecycle_already_prepared")
        head = self._run(Command(("git", "rev-parse", "HEAD"), 30), "source_head_failed").stdout.strip()
        main = self._run(Command(("git", "rev-parse", "origin/main"), 30), "source_main_failed").stdout.strip()
        dirty = self._run(Command(("git", "status", "--porcelain"), 30), "source_status_failed").stdout
        if len(head) != 40 or any(ch not in _HEX40 for ch in head) or head != main or dirty:
            raise ControllerError("source_not_synchronized")
        self._tool_identities = self._verify_tool_lock()
        self._workload = self._accepted_workload()
        listed = self._run(Command(("colima", "list", "--json"), 60), "profile_inventory_failed")
        full_profiles = self._foreign_records(listed.stdout)
        profiles = tuple((str(row["name"]), str(row["status"])) for row in full_profiles)
        if any(name == LAB_IDENTITY for name, _status in profiles):
            raise ControllerError("owned_profile_present")
        context = self._run(docker_context_command(), "global_context_failed").stdout.strip()
        if not context or len(context.encode("utf-8")) > 4096:
            raise ControllerError("global_context_invalid")
        profile_bytes = _read_regular(self.paths.profile, 64 * 1024)
        calico_path = self.paths.repository / self.profile.calico_manifest_path
        calico_bytes = _read_regular(calico_path, 16 * 1024 * 1024)
        if _digest(calico_bytes) != self.profile.calico_manifest_sha256:
            raise ControllerError("calico_identity_mismatch")
        self.paths.private.mkdir(parents=True, mode=0o700)
        os.chmod(self.paths.private, 0o700)
        self.docker_config.mkdir(mode=0o700)
        expected = tuple(sorted("/".join(key[1:]) for key in expected_object_keys(self.profile)))
        foreign = tuple(item for item in profiles if item[0] != LAB_IDENTITY)
        create_journal(
            self.journal_path,
            JournalInputs(
                JOURNAL_SCHEMA,
                self.run_digest,
                self.execution_nonce,
                head,
                _digest(profile_bytes),
                "prepared",
                context,
                foreign,
                expected,
                self._identity,
                lifecycle_mode="request-free" if self._used_mode == "request-free" else "nominal",
            ),
        )
        self._foreign_before = foreign
        self._foreign_records_before = [row for row in full_profiles if row["name"] != LAB_IDENTITY]
        _write_exclusive(self.foreign_snapshot_path, _canonical_bytes(self._foreign_records_before))
        self._context_before = context
        self._source_commit = head
        self._profile_sha256 = _digest(profile_bytes)
        self._prepared = True
        return {"owned_profile": "absent", "foreign_profile_count": len(foreign), "run_id": self.run_id}

    def _identity_from_cluster(self) -> OwnedIdentity:
        inspected = self._run(
            Command(
                ("docker", "inspect", f"{LAB_IDENTITY}-control-plane"),
                60,
                env=(("DOCKER_CONFIG", str(self.docker_config)), ("DOCKER_HOST", self.docker_host)),
            ),
            "node_identity_failed",
        )
        namespace = self._run(
            Command(("kubectl", "--kubeconfig", str(self.kubeconfig), "get", "namespace", "kube-system", "--output", "json"), 60),
            "cluster_identity_failed",
        )
        try:
            node_record = json.loads(inspected.stdout)[0]
            node = node_record["Id"]
            requested_node_image = node_record["Config"]["Image"]
            uid = json.loads(namespace.stdout)["metadata"]["uid"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            raise ControllerError("cluster_identity_invalid") from None
        if requested_node_image != self.profile.kind_node_image:
            raise ControllerError("node_image_identity_mismatch")
        return OwnedIdentity(LAB_IDENTITY, self.docker_host, LAB_IDENTITY, str(self.kubeconfig), uid, node)

    def up(self) -> dict[str, object]:
        if not self._prepared:
            self.preflight()
        if self._workload is None:
            self._tool_identities = self._verify_tool_lock()
            self._workload = self._accepted_workload()
        if self._up:
            raise ControllerError("lifecycle_reuse_forbidden")
        _write_exclusive(self.kind_config, render_kind_config(self.profile))
        profile_details = {"colima_profile": LAB_IDENTITY}
        self._journal_pair("profile_start", profile_details, lambda: self._run(colima_start_command(), "profile_start_failed"))
        cluster_details = {"kind_cluster": LAB_IDENTITY, "kubeconfig": str(self.kubeconfig)}
        append_event(self.journal_path, "cluster_create_intent", cluster_details)
        self._events.append(("cluster_create_intent", dict(cluster_details)))
        self._run(kind_create_command(self._identity), "cluster_create_failed")
        self._identity = self._identity_from_cluster()
        cluster_complete = {
            **cluster_details,
            "cluster_incarnation_uid": self._identity.cluster_incarnation_uid,
            "node_container_id": self._identity.node_container_id,
            "docker_host": self.docker_host,
        }
        append_event(self.journal_path, "cluster_create_complete", cluster_complete)
        self._events.append(("cluster_create_complete", dict(cluster_complete)))
        calico_bytes = _read_regular(
            self.paths.repository / self.profile.calico_manifest_path,
            16 * 1024 * 1024,
        )
        private_calico = self.paths.private / "calico-v3.32.0.yaml"
        _write_exclusive(private_calico, calico_bytes)
        calico_details = {"manifest_sha256": _digest(calico_bytes)}
        self._journal_pair(
            "calico_apply",
            calico_details,
            lambda: self._run(
                kubectl_apply_calico_command(
                    self._identity,
                    private_calico,
                ),
                "calico_apply_failed",
            ),
        )
        workload = self._workload
        if workload is None:
            raise ControllerError("content_identity_failed")
        rendered = json.loads(render_objects(self.profile, workload))
        namespaces = [item for item in rendered["items"] if item["kind"] == "Namespace"]
        policies = [item for item in rendered["items"] if item["kind"] == "NetworkPolicy"]
        workloads = [item for item in rendered["items"] if item["kind"] not in {"Namespace", "NetworkPolicy"}]
        payloads = tuple(_canonical_bytes({"apiVersion": "v1", "kind": "List", "items": items}) for items in (namespaces, policies, workloads))
        app_details = {"manifest_sha256": _digest(render_objects(self.profile, workload))}
        append_event(self.journal_path, "application_apply_intent", app_details)
        self._events.append(("application_apply_intent", dict(app_details)))
        for payload in payloads:
            self._run(kubectl_apply_command(self._identity, payload), "application_apply_failed")
        append_event(self.journal_path, "application_apply_complete", app_details)
        self._events.append(("application_apply_complete", dict(app_details)))
        inventory = self._run(
            Command(("kubectl", "--kubeconfig", str(self.kubeconfig), "get", "pods", "--all-namespaces", "--output", "json"), 300),
            "readiness_failed",
        )
        readiness = {"attestation_sha256": _digest(inventory.stdout.encode())}
        self._journal_pair("readiness", readiness, lambda: CommandResult(0, "", ""))
        projection = self._run(
            Command((
                "kubectl", "--kubeconfig", str(self.kubeconfig), "get",
                "namespaces,pods,services,endpoints,endpointslices,serviceaccounts,configmaps,deployments,daemonsets,networkpolicies",
                "--all-namespaces", "--output", "json",
            ), 300),
            "runtime_inventory_failed",
        )
        try:
            if len(projection.stdout.encode("utf-8")) > 8 * 1024 * 1024:
                raise ControllerError("runtime_inventory_invalid")
            projected = json.loads(projection.stdout)
        except (json.JSONDecodeError, UnicodeError):
            raise ControllerError("runtime_inventory_invalid") from None
        if type(projected) is dict and projected.get("apiVersion") == "v1" and projected.get("kind") == "List":
            projected = self._runtime_from_kubernetes(projected)
        if (
            type(projected) is not dict
            or frozenset(projected) != frozenset({"topology_attestation", "policy_attestation"})
            or type(projected["topology_attestation"]) is not dict
            or type(projected["policy_attestation"]) is not dict
        ):
            raise ControllerError("runtime_inventory_invalid")
        self._runtime_projection = projected
        _write_exclusive(self.runtime_projection_path, _canonical_bytes(projected))
        self._up = True
        return {"cluster": LAB_IDENTITY, "run_id": self.run_id, "ready": True}

    def _start_driver(self, track: str) -> tuple[str, str, str]:
        namespace = dict(TRACK_NAMESPACES)[track]
        uid = "driver-" + sha256((self.run_id + track).encode()).hexdigest()[:32]
        details = {"namespace": namespace, "pod": "driver", "uid": uid}
        self._journal_pair("driver_start", details, lambda: CommandResult(0, "", ""))
        identity = (namespace, "driver", uid)
        self._drivers.append(identity)
        return identity

    @staticmethod
    def _claims(audience: str, issued: int) -> QStateClaims:
        return QStateClaims(
            "kil.q-state.v0", f"q-v3b2-{audience}", "https://lab-issuer.kil.invalid",
            "spiffe://kil.local/workload/demo", audience, "admin_action", "consequential_admin",
            issued, issued, issued + 10, issued - 1, "tp-v3b2-1", "sha256:" + "a" * 64,
            "ke-v3b2-1", "sha256:" + "b" * 64, "kil-lab-v3@0", Decimal("80"),
            Decimal("40"), 5, 2, True, True, Decimal("0"), Decimal("100"),
            "kil-decay-v1", "kil-v3b2-fixture-v1",
        )

    def _instruction(self, track: str) -> bytes:
        headers = {
            "authorization": "Bearer v3b1-lab-credential",
            "x-request-id": NOMINAL_REQUEST_ID,
            "x-kil-run-id": "v3b1-" + self.run_digest,
            "x-envoy-hedge-on-per-try-timeout": "false", "x-envoy-max-retries": "0",
            "x-kil-decision-digest": "f" * 64, "x-kil-issuer": "https://attacker.invalid",
            "x-kil-local-evidence": '{"divergence":"0"}', "x-kil-mode": "credential_policy_baseline",
            "x-kil-track": "client-selected-track", "x-kil-verified-subject": "spiffe://attacker.invalid/workload",
        }
        if track != TRACKS[0]:
            audience = "kil-v3-signed" if track == TRACKS[1] else "kil-v3-local"
            headers["x-kil-q-state"] = issue_q_state(
                self._claims(audience, int(time.time())),
                Ed25519PrivateKey.from_private_bytes(bytes(range(32))),
            )
        payload = canonical_record({
            "schema_version": "kil.v3b1-driver-instruction.v1", "track": track,
            "method": "POST", "path": "/consequential/admin", "headers": headers,
            "body_byte_count": 0,
        })
        parse_instruction(payload, expected_track=track)
        return payload

    def _freeze(self) -> None:
        if self._runtime_projection is None:
            raise ControllerError("runtime_inventory_missing")
        topology = self._runtime_projection["topology_attestation"]
        assert type(topology) is dict
        images = topology.get("pod_images")
        if type(images) is not list:
            raise ControllerError("runtime_inventory_invalid")
        captured: list[CapturedSource] = []
        attestations: list[dict[str, object]] = []
        payloads: list[bytes] = []
        kind_roles = (("driver", "driver"), ("decision", "authz"), ("envoy", "envoy"), ("target", "target"))
        for track, namespace in TRACK_NAMESPACES:
            for kind, role in kind_roles:
                resource = "pod/driver" if role == "driver" else f"deployment/{role}"
                result = self._run(
                    Command(("kubectl", "--kubeconfig", str(self.kubeconfig), "logs", resource, "--namespace", namespace, "--limit-bytes=1048576"), 300),
                    "source_capture_failed",
                )
                payload = result.stdout.encode("utf-8")
                try:
                    records = [json.loads(line) for line in payload.splitlines() if line]
                except (UnicodeError, json.JSONDecodeError):
                    raise ControllerError("source_capture_invalid") from None
                matches = [item for item in images if type(item) is dict and item.get("namespace") == namespace and item.get("container") == role]
                if len(matches) != 1:
                    raise ControllerError("source_identity_invalid")
                source = matches[0]
                if any(type(source.get(name)) is not str or not source[name] for name in ("uid", "resource_version", "image_id")):
                    raise ControllerError("source_identity_invalid")
                identity = SourceIdentity(
                    f"{track}:{kind}", str(source["uid"]), str(source["resource_version"]),
                    str(source["image_id"]), len(payload), _digest(payload),
                )
                captured.append(CapturedSource(identity, payload))
                payloads.append(payload)
                self._application_records += len(records)
                if records or self._used_mode == "nominal":
                    attestations.append({"kind": kind, "track": track, "records": records})
        self._captured_sources = captured
        self._source_attestations = attestations
        freeze = {"evidence_sha256": _digest(b"".join(payloads))}
        self._journal_pair("evidence_freeze", freeze, lambda: CommandResult(0, "", ""))

    def _cancel_drivers(self) -> None:
        remaining = [item for item in self._drivers if item[0] not in self._canceled]
        for driver_index, (namespace, pod, uid) in enumerate(remaining):
            details = {"namespace": namespace, "pod": pod, "uid": uid}
            append_event(self.journal_path, "driver_cancel_intent", details)
            self._events.append(("driver_cancel_intent", dict(details)))
            delete = recovery_plan(
                load_journal(self.journal_path),
                RecoveryObservation(
                    self.docker_host, LAB_IDENTITY, LAB_IDENTITY,
                    self._identity.cluster_incarnation_uid, self._identity.node_container_id,
                    tuple(sorted(remaining[driver_index:])),
                ),
            ).commands[-1]
            self._run(delete, "driver_cancel_failed", allow_absent=True)
            append_event(self.journal_path, "driver_cancel_complete", details)
            self._events.append(("driver_cancel_complete", dict(details)))
            self._canceled.add(namespace)

    def _quiesce(self) -> None:
        command_digest = _digest(_canonical_bytes([
            list(kubectl_quiesce_command(self._identity, namespace).argv)
            for _track, namespace in TRACK_NAMESPACES
        ]))
        details = {"attestation_sha256": command_digest}
        append_event(self.journal_path, "envoy_quiesce_intent", details)
        self._events.append(("envoy_quiesce_intent", dict(details)))
        for _track, namespace in TRACK_NAMESPACES:
            self._run(kubectl_quiesce_command(self._identity, namespace), "envoy_quiesce_failed")
        append_event(self.journal_path, "envoy_quiesce_complete", details)
        self._events.append(("envoy_quiesce_complete", dict(details)))

    def _teardown(self) -> None:
        self._cancel_drivers()
        cluster = {"kind_cluster": LAB_IDENTITY, "kubeconfig": str(self.kubeconfig)}
        self._journal_pair("cluster_delete", cluster, lambda: self._run(kind_delete_command(self._identity), "cluster_delete_failed"))
        absence = {"kind_cluster": LAB_IDENTITY, "node_container_id": self._identity.node_container_id}
        self._journal_pair("cluster_absence_proof", absence, lambda: self._run(Command(("docker", "inspect", f"{LAB_IDENTITY}-control-plane"), 60, env=(("DOCKER_CONFIG", str(self.docker_config)), ("DOCKER_HOST", self.docker_host))), "cluster_absence_failed", allow_absent=True))
        profile = {"colima_profile": LAB_IDENTITY}
        stop = Command(("colima", "stop", "--profile", LAB_IDENTITY), 300, mutating=True)
        delete = Command(("colima", "delete", "--profile", LAB_IDENTITY, "--force", "--data"), 300, mutating=True)
        self._journal_pair("profile_stop", profile, lambda: self._run(stop, "profile_stop_failed"))
        self._journal_pair("profile_delete", profile, lambda: self._run(delete, "profile_delete_failed"))
        self._journal_pair("profile_absence_proof", profile, lambda: self._run(Command(("colima", "status", "--profile", LAB_IDENTITY), 60), "profile_absence_failed", allow_absent=True))
        for path in (self.kubeconfig, self.kind_config, self.paths.private / "calico-v3.32.0.yaml"):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                raise ControllerError("private_active_state_present") from None
        try:
            self.docker_config.rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            raise ControllerError("private_active_state_present") from None
        if any(path.exists() for path in (self.kubeconfig, self.kind_config, self.paths.private / "calico-v3.32.0.yaml", self.docker_config)):
            raise ControllerError("private_active_state_present")
        after_result = self._run(Command(("colima", "list", "--json"), 60), "foreign_snapshot_failed")
        self._foreign_records_after = self._foreign_records(after_result.stdout)
        after = tuple((str(row["name"]), str(row["status"])) for row in self._foreign_records_after)
        context = self._run(docker_context_command(), "global_context_failed").stdout.strip()
        self._context_after = context
        unchanged = after == self._foreign_before and context == self._context_before
        compare = {"unchanged": unchanged, "attestation_sha256": _digest(_canonical_bytes([list(item) for item in after]))}
        self._journal_pair("foreign_snapshot_comparison", compare, lambda: CommandResult(0, "", ""))
        if not unchanged:
            raise ControllerError("foreign_state_changed")
        self.owned_absence_proven = True

    def _publish(self) -> Path:
        if (
            not self.owned_absence_proven
            or self._runtime_projection is None
            or self._workload is None
            or not self._foreign_records_before and self._foreign_before
            or not self._foreign_records_after and self._foreign_before
        ):
            raise ControllerError("evidence_incomplete")
        topology = self._runtime_projection["topology_attestation"]
        policy = self._runtime_projection["policy_attestation"]
        assert type(topology) is dict and type(policy) is dict
        if (
            topology.get("cluster_incarnation_uid") != self._identity.cluster_incarnation_uid
            or topology.get("node_container_id") != self._identity.node_container_id
        ):
            raise ControllerError("runtime_identity_mismatch")
        objects = topology.get("objects")
        images = topology.get("pod_images")
        endpoints = topology.get("endpoints")
        if not all(type(value) is list for value in (objects, images, endpoints)):
            raise ControllerError("runtime_inventory_invalid")
        expected_topology = {
            "namespaces": topology.get("namespaces"),
            "object_keys": sorted([[item["api_version"], item["kind"], item["namespace"], item["name"]] for item in objects]),
            "pod_image_keys": [[item["image_role"], item["container_type"], item["namespace"], item["container"]] for item in images],
            "endpoint_keys": [[item["namespace"], item["service"], item["port_name"], item["protocol"], item["port"]] for item in endpoints],
            "calico_readiness": topology.get("calico_readiness"),
        }
        content = {
            "run_id": self.run_id,
            "profile_sha256": self._profile_sha256 or str(load_journal(self.journal_path)["profile_sha256"]),
            "kind_config_sha256": _digest(render_kind_config(self.profile)),
            "objects_manifest_sha256": _digest(render_objects(self.profile, self._workload)),
            "calico_manifest_sha256": self.profile.calico_manifest_sha256,
            "kind_node_image": self.profile.kind_node_image,
            "calico_images": dict(self.profile.calico_images),
            "kil_image_id": self._workload.kil_image_id,
            "envoy_image_digest": self._workload.envoy_image_digest,
        }
        journal = load_journal(self.journal_path)
        private = {
            "schema_version": "kil.v3b2-private-manifest.v1",
            "run_id": self.run_id,
            "execution_nonce": self.execution_nonce,
            "source_commit": self._source_commit or str(journal["source_commit"]),
            "profile_sha256": content["profile_sha256"],
            "tool_identities": dict(self._tool_identities),
            "content_identities": content,
            "expected_topology": expected_topology,
            "expected_policy_graph": policy,
            "request_cases": list(self._request_cases),
            "runtime_identities": {
                "topology_attestation": topology,
                "policy_attestation": policy,
                "foreign_profiles_after": self._foreign_records_after,
                "global_context_after": self._context_after,
                "owned_teardown": {"cluster_absent": True, "profile_absent": True, "private_active_state_absent": True},
            },
            "source_attestations": list(self._source_attestations),
            "foreign_profiles_before": self._foreign_records_before,
            "global_context_before": self._context_before,
        }
        commitment = _digest(_canonical_bytes(private))
        details = {"public_commitment_sha256": commitment}
        append_event(self.journal_path, "publication_intent", details)
        self._events.append(("publication_intent", dict(details)))
        try:
            published = publish_bundle(private, self.paths.public)
        except Exception:
            raise ControllerError("publication_failed") from None
        append_event(self.journal_path, "publication_complete", details)
        self._events.append(("publication_complete", dict(details)))
        self.published_path = published
        return published

    def request_free(self) -> dict[str, object]:
        if self._used_mode is not None:
            raise ControllerError("lifecycle_reuse_forbidden")
        self._used_mode = "request-free"
        self._select_mode("request-free")
        self.up()
        for track in TRACKS:
            self._start_driver(track)
        self._cancel_drivers()
        self._quiesce()
        self._freeze()
        self._teardown()
        if self._application_records:
            raise ControllerError("request_free_records_present")
        published = self._publish()
        return {"run_id": self.run_id, "instructions_sent": 0, "application_records": self._application_records, "owned_teardown": True, "bundle": str(published)}

    def nominal(self) -> NominalBundle:
        if self._used_mode is not None:
            raise ControllerError("lifecycle_reuse_forbidden")
        self._used_mode = "nominal"
        self._select_mode("nominal")
        self.up()
        results: list[tuple[str, int, int]] = []
        failure: ControllerError | None = None
        for track in TRACKS:
            self._start_driver(track)
            instruction = self._instruction(track)
            case = {"track": track, "request_id": NOMINAL_REQUEST_ID, "case_sha256": _digest(instruction)}
            append_event(self.journal_path, "request_intent", case)
            self._events.append(("request_intent", dict(case)))
            self._events.append(("kubectl_attach", {"track": track, "request_id": NOMINAL_REQUEST_ID}))
            result = self._run(
                kubectl_attach_command(self._identity, dict(TRACK_NAMESPACES)[track], instruction),
                "request_transport_failed",
                allow_absent=True,
            )
            if result.returncode != 0:
                failure = ControllerError("request_transport_failed")
                break
            try:
                record = json.loads(result.stdout)
                item = (str(record["outcome"]), int(record["http_status"]), int(record["target_marker_count"]))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                failure = ControllerError("request_result_invalid")
                break
            results.append(item)
            self._request_cases.append({
                "track": track,
                "request_id": NOMINAL_REQUEST_ID,
                "expected_decision": item[0],
                "expected_http_status": item[1],
                "expected_target_markers": item[2],
            })
            complete = {**case, "result_sha256": _digest(result.stdout.encode())}
            append_event(self.journal_path, "request_result", complete)
            self._events.append(("request_result", dict(complete)))
        self._quiesce()
        self._freeze()
        self._teardown()
        if failure is not None:
            raise failure
        result_tuple = tuple(results)
        if result_tuple != _EXPECTED_TUPLE:
            raise ControllerError("nominal_tuple_invalid")
        self._publish()
        return NominalBundle(self.run_id, result_tuple, len(results), True)

    def down(self) -> dict[str, object]:
        if not self.journal_path.exists():
            raise ControllerError("journal_missing")
        if not self._up:
            raise ControllerError("runtime_not_bound")
        if not any(event[0] == "evidence_freeze_complete" for event in self._events):
            if not any(event[0] == "envoy_quiesce_complete" for event in self._events):
                self._quiesce()
            self._freeze()
        self._teardown()
        return {"owned_teardown": True}

    def recover(self) -> dict[str, object]:
        journal = load_journal(self.journal_path)
        pending: dict[tuple[str, tuple[tuple[str, object], ...]], dict[str, object]] = {}
        for record in journal["events"]:
            name = str(record["event"])
            if name.endswith("_intent"):
                family = name[:-7]
                details = dict(record["details"])
                pending[(family, tuple(sorted(details.items())))] = details
            elif name.endswith("_complete") or name == "request_result":
                family = "request" if name == "request_result" else name[:-9]
                details = dict(record["details"])
                for key in tuple(pending):
                    if key[0] == family and all(details.get(field) == value for field, value in key[1]):
                        pending.pop(key)
        command_pending = [(family, details) for (family, _key), details in pending.items() if family != "request"]
        if len(command_pending) > 1:
            raise ControllerError("manual_recovery_required")
        if command_pending:
            family, details = command_pending[0]
            if family == "publication":
                try:
                    verified = verify_bundle(self.paths.public / self.run_id)
                except Exception:
                    raise ControllerError("manual_recovery_required") from None
                if verified.run_id != self.run_id:
                    raise ControllerError("manual_recovery_required")
                append_event(self.journal_path, "publication_complete", details)
                return {"commands_run": 0, "publication_allowed": True, "completed": family}
            plan = recovery_plan(journal)
            if plan.requests_to_send or any("attach" in command.argv for command in plan.commands):
                raise ControllerError("recovery_request_forbidden")
            results = [self._run(command, "recovery_attestation_failed", allow_absent=True) for command in plan.commands]
            if family == "cluster_create":
                self._identity = self._identity_from_cluster()
                completion = {
                    **details,
                    "cluster_incarnation_uid": self._identity.cluster_incarnation_uid,
                    "node_container_id": self._identity.node_container_id,
                    "docker_host": self.docker_host,
                }
            else:
                completion = details
            if family == "driver_cancel" and results and results[-1].returncode == 0:
                action = recovery_plan(
                    journal,
                    RecoveryObservation(
                        self.docker_host, LAB_IDENTITY, LAB_IDENTITY,
                        self._identity.cluster_incarnation_uid, self._identity.node_container_id,
                        ((str(details["namespace"]), str(details["pod"]), str(details["uid"])),),
                    ),
                )
                self._run(action.commands[-1], "recovery_action_failed", allow_absent=True)
            elif family == "cluster_delete" and results and results[-1].returncode == 0:
                action = recovery_plan(
                    journal,
                    RecoveryObservation(
                        self.docker_host, LAB_IDENTITY, LAB_IDENTITY,
                        self._identity.cluster_incarnation_uid, self._identity.node_container_id,
                        (),
                    ),
                )
                self._run(action.commands[-1], "recovery_action_failed", allow_absent=True)
            elif family in {"profile_stop", "profile_delete"} and results and results[-1].returncode == 0:
                action = recovery_plan(
                    journal,
                    RecoveryObservation(
                        self.docker_host, LAB_IDENTITY, LAB_IDENTITY,
                        self._identity.cluster_incarnation_uid, self._identity.node_container_id,
                        (),
                    ),
                )
                self._run(action.commands[-1], "recovery_action_failed", allow_absent=True)
            append_event(self.journal_path, family + "_complete", completion)
            return {"commands_run": len(plan.commands), "publication_allowed": False, "completed": family}
        plan = recovery_plan(journal)
        if plan.requests_to_send:
            raise ControllerError("recovery_request_forbidden")
        next_event: str | None = None
        next_details: dict[str, object] | None = None
        if plan.next_intent is not None:
            next_event = plan.next_intent[0]
            next_details = dict(plan.next_intent[1])
            if next_event == "evidence_freeze_intent":
                append_event(self.journal_path, next_event, next_details)
        for command in plan.commands:
            if "attach" in command.argv:
                raise ControllerError("recovery_request_forbidden")
            self._run(command, "recovery_action_failed", allow_absent=True)
        completed = None
        if next_event == "evidence_freeze_intent" and next_details is not None:
            append_event(self.journal_path, "evidence_freeze_complete", next_details)
            completed = "evidence_freeze"
        elif next_event is not None and next_details is not None:
            append_event(self.journal_path, next_event, next_details)
        return {"commands_run": len(plan.commands), "publication_allowed": plan.publication_allowed, "completed": completed}


__all__ = [
    "CommandResult", "CommandRunner", "ControllerError", "ControllerPaths",
    "NominalBundle", "SubprocessCommandRunner", "V3B2Controller",
]
