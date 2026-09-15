"""Closed V3B-2a Kind/Calico lifecycle orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
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
from kil.v3b1_driver_protocol import (
    DriverProtocolError,
    MAX_RESULT_BYTES,
    canonical_record,
    parse_instruction,
    parse_result,
)
from kil.v3b2_contracts import (
    JOURNAL_SCHEMA,
    LAB_IDENTITY,
    NOMINAL_REQUEST_ID,
    TRACK_NAMESPACES,
    TRACKS,
    V3B2Profile,
)
from kil.v3b2_evidence import (
    CapturedSource,
    SourceIdentity,
    capture_source,
    adapt_producer_sources,
    prepare_publication,
    publish_prepared,
    verify_publication_identity,
)
from kil.v3b2_journal import (
    Command,
    JournalInputs,
    OwnedIdentity,
    append_event,
    append_observed_terminal,
    load_expected_context,
    colima_start_command,
    create_journal,
    docker_context_command,
    docker_image_import_commands,
    kind_create_command,
    kind_delete_command,
    kind_load_command,
    kubectl_apply_command,
    kubectl_apply_calico_command,
    kubectl_calico_workload_command,
    kubectl_attach_command,
    kubectl_driver_pod_command,
    kubectl_cancel_driver_command,
    kubectl_ready_endpoint_command,
    kubectl_source_pod_command,
    kubectl_source_read_command,
    kubectl_workload_ready_command,
    kubectl_envoy_quiesce_commands,
    load_journal,
    latch_teardown,
    latch_profile_start_refusal,
    select_lifecycle_mode,
)
from kil.v3b2_manifests import (
    WorkloadIdentity,
    expected_object_keys,
    render_kind_config,
    render_objects,
)
from kil.v3b2_inventory import (
    InventoryError,
    parse_calico_runtime_workload,
    parse_proved_runtime_inventory,
    parse_runtime_pod_identity,
    parse_ready_endpoint_slice,
)
from kil.v3b2_proofs import OPERATIONS, MAX_OBSERVATION_BYTES, RawObservation, ProofError, calico_objects, decode, canonical as proof_canonical


_HEX40 = set("0123456789abcdef")
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
_ACCEPTED_KIL_ARCHIVE_SHA256 = "07c12f338c7d764812ef6271ec8942f0535d05019288f4df1e1b54f6cd75e4b6"
_ACCEPTED_KIL_CONFIG_DIGEST = "sha256:f21285be21c8f691b9b60b7e38bb309564a5cc238512c7455eb7759f4d922ddb"
# Reserved synthetic transport statuses, never an observed process exit or
# POSIX signal. Both remain unsuccessful to every operation validator.
# -1000 retains all bytes captured up to timeout (not a complete process run).
# -1001 explicitly marks retained stdout/stderr as prefixes, NOT full raw output.
COMMAND_TIMEOUT_RETURN_CODE = -1000
COMMAND_TIMEOUT_TRUNCATED_RETURN_CODE = -1001
# Leave room for hex encoding, other observations and immutable expected inputs
# in the bounded durable proof bundle. Oversized captures retain at most half
# this allowance from each stream, without prepending or replacing its bytes.
MAX_TIMEOUT_CAPTURE_BYTES = MAX_OBSERVATION_BYTES // 4


class ControllerError(RuntimeError):
    """A closed stage code for a lifecycle failure."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    raw_stdout: bytes | None = None
    raw_stderr: bytes | None = None

    def __post_init__(self) -> None:
        if type(self.returncode) is not int or type(self.stdout) is not str or type(self.stderr) is not str:
            raise ControllerError("invalid_command_result")
        for raw, text in ((self.raw_stdout, self.stdout), (self.raw_stderr, self.stderr)):
            if raw is not None and (type(raw) is not bytes or raw.decode("utf-8", errors="replace") != text):
                raise ControllerError("invalid_raw_command_result")

    @property
    def stdout_bytes(self):
        return self.stdout.encode("utf-8") if self.raw_stdout is None else self.raw_stdout

    @property
    def stderr_bytes(self):
        return self.stderr.encode("utf-8") if self.raw_stderr is None else self.raw_stderr


class CommandRunner(Protocol):
    def run(self, command: Command) -> CommandResult: ...


class _KubectlSourceReader:
    """Bounded SourceReader over one already-attested Kubernetes container log."""

    def __init__(
        self,
        controller: "V3B2Controller",
        command: Command,
        identity_command: Command,
        *,
        source_kind: str,
        namespace: str,
        pod: str,
        container: str,
        image: str,
        uid: str,
        resource_version: str,
        container_id: str,
    ) -> None:
        self._controller = controller
        self._command = command
        self._identity_command = identity_command
        self._kind = source_kind
        self._namespace = namespace
        self._pod = pod
        self._container = container
        self._image = image
        self._uid = uid
        self._resource_version = resource_version
        self._container_id = container_id

    def _bytes(self) -> bytes:
        result = self._controller._run(self._command, "source_capture_failed")
        try:
            payload = result.stdout_bytes
        except UnicodeError:
            raise ControllerError("source_capture_invalid") from None
        if len(payload) > 1024 * 1024:
            raise ControllerError("source_capture_invalid")
        return payload

    def identity(self) -> SourceIdentity:
        result = self._controller._run(self._identity_command, "source_identity_failed")
        try:
            pod = parse_runtime_pod_identity(
                result.stdout_bytes,
                expected_namespace=self._namespace,
                expected_pod=self._pod,
                expected_container=self._container,
                expected_image=self._image,
                require_ready=False,
            )
        except (InventoryError, UnicodeError):
            raise ControllerError("source_identity_invalid") from None
        if (
            pod.uid != self._uid
            or pod.container_id != self._container_id
        ):
            raise ControllerError("source_identity_invalid")
        payload = self._bytes()
        return SourceIdentity(
            self._kind, self._uid, pod.resource_version, self._container_id,
            len(payload), _digest(payload),
        )

    def read(self, maximum: int) -> bytes:
        payload = self._bytes()
        return payload if len(payload) <= maximum else payload[: maximum + 1]


class SubprocessCommandRunner:
    """The sole process-execution boundary; commands arrive already validated."""

    def __init__(self, repository: Path | None = None, tools: Path | None = None) -> None:
        self.repository = repository
        self.tools = tools
        from kil.v3b2_profile_state import passwd_home
        self._home = str(passwd_home())
        self._global_docker_config = os.environ.get('DOCKER_CONFIG', str(Path(self._home) / '.docker'))
        if repository is not None and (not repository.is_absolute() or repository.resolve() != repository):
            raise ControllerError("invalid_runner_paths")
        if tools is not None and (not tools.is_absolute() or tools.resolve() != tools):
            raise ControllerError("invalid_runner_paths")

    def run(self, command: Command) -> CommandResult:
        if type(command) is not Command:
            raise ControllerError("invalid_command")
        command.__post_init__()
        # Inherited CLI authority (including Docker context, proxy configuration,
        # and alternate Colima/Lima homes) must never redirect owned commands.
        environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
        environment["HOME"] = self._home
        if command.argv == ('docker', 'context', 'show'):
            environment['DOCKER_CONFIG'] = self._global_docker_config
        if command.argv[0] == 'colima' and command.mutating and not command.env:
            raise ControllerError('colima_private_environment_missing')
        environment.update(dict(command.env))
        if command.argv[0] in {'docker', 'kind'} and command.argv != ('docker', 'context', 'show'):
            configuration = dict(command.env).get('DOCKER_CONFIG')
            if configuration is not None:
                environment['TMPDIR'] = str(Path(configuration).parent / 'runtime-tmp')
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
        except subprocess.TimeoutExpired as error:
            stdout = b"" if error.output is None else error.output
            stderr = b"" if error.stderr is None else error.stderr
            if type(stdout) is not bytes or type(stderr) is not bytes:
                raise ControllerError("command_timeout_capture_invalid") from None
            returncode = COMMAND_TIMEOUT_RETURN_CODE
            if len(stdout) + len(stderr) > MAX_TIMEOUT_CAPTURE_BYTES:
                returncode = COMMAND_TIMEOUT_TRUNCATED_RETURN_CODE
                stdout = stdout[:MAX_TIMEOUT_CAPTURE_BYTES // 2]
                stderr = stderr[:MAX_TIMEOUT_CAPTURE_BYTES // 2]
            return CommandResult(returncode, stdout.decode("utf-8", errors="replace"),
                                 stderr.decode("utf-8", errors="replace"), stdout, stderr)
        except (OSError, subprocess.SubprocessError):
            raise ControllerError("command_execution_failed") from None
        return CommandResult(
            completed.returncode,
            completed.stdout.decode("utf-8", errors="replace"),
            completed.stderr.decode("utf-8", errors="replace"),
            completed.stdout,
            completed.stderr,
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
    bundle: str
    public_commitment: str


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _archive_digest(value: bytes) -> str:
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

    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


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
        self.expected_inputs_path = paths.private / "expected-inputs.json"
        from kil.v3b2_profile_state import ProfilePaths
        self.profile_paths = ProfilePaths.bind(paths.private)
        self.global_docker_config = (runner._global_docker_config if isinstance(runner, SubprocessCommandRunner)
                                     else str(self.profile_paths.home / '.docker'))
        if isinstance(runner, SubprocessCommandRunner) and runner._home != str(self.profile_paths.home):
            raise ControllerError('runner_home_differs_from_passwd_home')
        self.docker_host = f"unix://{self.profile_paths.profile}/docker.sock"
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
        self._kil_archive_bytes: bytes | None = None
        self._application_records = 0
        self._runtime_projection: dict[str, object] | None = None
        self._source_attestations: list[dict[str, object]] = []
        self._source_producer_invalid = False
        self._request_cases: list[dict[str, object]] = []
        self.published_path: Path | None = None
        self.public_commitment: str | None = None
        self.owned_absence_proven = False
        if self.journal_path.exists():
            self._hydrate()

    @property
    def events(self) -> tuple[tuple[str, dict[str, object]], ...]:
        return tuple(self._events)

    def _observe(self, command: Command, stage: str) -> CommandResult:
        if command.mutating and not self.journal_path.exists():
            raise ControllerError('mutation_requires_prepared_journal')
        if command.argv[0] == 'colima':
            environment = (('DOCKER_CONFIG', str(self.docker_config)), ('TMPDIR', str(self.profile_paths.tmp)))
            if command.env and command.env != environment:
                raise ControllerError('colima_private_environment_mismatch')
            command = Command(command.argv, command.timeout_s, stdin=command.stdin, env=environment, mutating=command.mutating)
        if command.mutating and self.journal_path.exists():
            journal = load_journal(self.journal_path)
            try:
                expected = decode(load_expected_context(self.journal_path, journal, state_only=True).inputs)
            except (OSError, ValueError, KeyError, TypeError):
                raise ControllerError("expected_inputs_or_prior_proof_invalid") from None
            owned = expected["owned_identity"]
            if command.argv[0] in {"docker", "kind"} and dict(command.env) != {
                    "DOCKER_CONFIG": str(Path(owned["kubeconfig"]).parent / "docker-config"),
                    "DOCKER_HOST": owned["docker_host"]}:
                raise ControllerError("command_authority_differs_from_expected_inputs")
            if command.argv[0] == "kubectl" and command.argv[1:3] != ("--kubeconfig", owned["kubeconfig"]):
                raise ControllerError("command_authority_differs_from_expected_inputs")
            if expected['profile_paths'] != self.profile_paths.document():
                raise ControllerError('profile_authority_differs_from_expected_inputs')
            if command.argv[0] == 'limactl':
                if command.env != (('LIMA_HOME', str(self.profile_paths.lima)),):
                    raise ControllerError('lima_private_environment_mismatch')
                from kil.v3b2_proofs import cleanup_commands
                try:
                    context = load_expected_context(self.journal_path)
                    permitted = context.family == 'profile_delete' and command in cleanup_commands(context, self._collect_observations(context))
                except (ValueError, OSError, KeyError, TypeError):
                    permitted = False
                if not permitted:
                    raise ControllerError('lima_fallback_registry_authority_unproved')
            elif command.argv[:2] != ('colima', 'start'):
                from kil.v3b2_profile_state import capture, unchanged
                try:
                    valid = unchanged(expected['profile_paths'], capture(self.profile_paths), expected['profile_binding'],
                                      stopped=command.argv[:2] == ('colima', 'delete'))
                except (ValueError, KeyError, TypeError, OSError):
                    valid = False
                if not valid:
                    raise ControllerError('profile_creation_binding_changed_before_mutation')
            if journal["teardown_from_sequence"] is not None:
                argv = command.argv
                allowed_cleanup = (
                    argv[:2] in {("colima", "stop"), ("colima", "delete")}
                    or argv == ('limactl', 'disk', 'delete', 'colima-kil-v3-lab')
                    or argv[:3] == ("kind", "delete", "cluster")
                    or ("attach" in argv and command.stdin == b"")
                    or ("exec" in argv and "drain_listeners" in argv[-1])
                )
                if not allowed_cleanup:
                    raise ControllerError("teardown_only_forward_command_forbidden")
        if command.mutating and command.argv[:2] == ('colima', 'start'):
            from kil.v3b2_profile_state import require_pristine
            try:
                require_pristine(self.profile_paths)
            except (ValueError, OSError):
                latch_profile_start_refusal(self.journal_path)
                raise ControllerError('owned_profile_remnant_or_unsafe_parent') from None
        try:
            result = self.runner.run(command)
        except Exception:
            raise ControllerError(stage) from None
        if type(result) is not CommandResult:
            raise ControllerError(stage)
        return result

    def _run(self, command: Command, stage: str) -> CommandResult:
        result = self._observe(command, stage)
        if result.returncode != 0:
            raise ControllerError(stage)
        return result

    def _hydrate(self) -> None:
        value = load_journal(self.journal_path)
        try:
            state = decode(load_expected_context(self.journal_path, value, state_only=True).inputs)
        except (OSError, ValueError, KeyError, TypeError):
            raise ControllerError("expected_inputs_or_prior_proof_invalid") from None
        self.run_digest = str(value["run_id"])
        self.run_id = "v3b2-" + self.run_digest
        self.execution_nonce = str(value["execution_nonce"])
        self._foreign_before = tuple(tuple(item) for item in value["foreign_profiles_before"])  # type: ignore[arg-type]
        self._context_before = str(value["global_context_before"])
        raw_identity = value["owned_identity"]
        assert isinstance(raw_identity, dict)
        self._identity = OwnedIdentity(**state["owned_identity"])
        if self._identity.docker_host != self.docker_host or self._identity.kubeconfig != str(self.kubeconfig):
            raise ControllerError("expected_inputs_authority_changed")
        if state['profile_paths'] != self.profile_paths.document():
            raise ControllerError('expected_profile_authority_changed')
        if state['global_docker_config'] != self.global_docker_config:
            raise ControllerError('global_docker_configuration_authority_changed')
        raw_events = value["events"]
        assert isinstance(raw_events, list)
        self._events = [(str(item["event"]), dict(item["details"])) for item in raw_events]
        for name, details in self._events:
            if name == "driver_start_complete":
                self._drivers.append((str(details["namespace"]), str(details["pod"]), str(details["uid"])))
            elif name == "driver_cancel_complete":
                self._canceled.add(str(details["namespace"]))
            elif (
                name == "driver_cancel_abandoned_for_teardown"
            ):
                self._canceled.add(str(details["namespace"]))
        names = {name for name, _details in self._events}
        self._prepared = True
        self._up = self._identity.node_container_id is not None and "cluster_delete_complete" not in names
        self.owned_absence_proven = "profile_absence_proof_complete" in names
        if self._events:
            self._used_mode = str(value["lifecycle_mode"])
        if state["source_images"] and self.runtime_projection_path.exists():
            try:
                projection = json.loads(_read_regular(self.runtime_projection_path, 8 * 1024 * 1024))
            except (json.JSONDecodeError, UnicodeError):
                raise ControllerError("runtime_inventory_invalid") from None
            if type(projection) is not dict:
                raise ControllerError("runtime_inventory_invalid")
            self._runtime_projection = projection
        if self.foreign_snapshot_path.exists():
            rows = self._foreign_records(_read_regular(self.foreign_snapshot_path, 1024 * 1024))
            if rows != state['foreign_before'] or any(row['name'] == LAB_IDENTITY for row in rows):
                raise ControllerError("ambiguous_profile_inventory")
            self._foreign_records_before = rows
        self._restore_foreign_comparison(state)

    def _restore_foreign_comparison(self, state):
        """Use only bindings independently rederived from a retained raw proof."""
        comparison = state.get('foreign_comparison')
        if comparison is not None:
            self._foreign_records_after = [dict(row) for row in comparison['foreign_after']]
            self._context_after = comparison['global_context_after']

    def _select_mode(self, mode: str) -> None:
        if not self.journal_path.exists():
            return
        try:
            select_lifecycle_mode(self.journal_path, mode)
        except Exception:
            raise ControllerError("lifecycle_mode_mismatch") from None

    def _journal_pair(
        self,
        family: str,
        intent: dict[str, object],
        action,
    ) -> CommandResult:
        if family == 'profile_start':
            from kil.v3b2_profile_state import require_pristine
            try:
                require_pristine(self.profile_paths)
            except (ValueError, OSError):
                raise ControllerError('owned_profile_remnant_or_unsafe_parent') from None
        append_event(self.journal_path, family + "_intent", intent)
        failure = None
        try:
            result = action()
        except ControllerError as error:
            failure = error
            latch_teardown(self.journal_path)
            result = CommandResult(-1, "", "action_failed")
        decision = self._observe_terminal()
        if failure is not None:
            raise failure
        if decision.outcome != "complete":
            latch_teardown(self.journal_path)
            if decision.outcome == "unknown":
                self._observe_terminal()
            raise ControllerError(family + "_postcondition_unproved")
        return result

    def _pending_runtime_image_authority(self, workload):
        """Authenticate image source while application_apply still owns the intent."""
        from kil.v3b2_proofs import reconstruct_prior_node_image_references
        try:
            context = load_expected_context(self.journal_path)
            inputs = decode(context.inputs)
            if (type(self.profile) is not V3B2Profile or type(workload) is not WorkloadIdentity
                    or type(self._identity) is not OwnedIdentity
                    or context.family != 'application_apply'
                    or V3B2Profile.from_mapping(inputs['profile']) != self.profile
                    or WorkloadIdentity(**inputs['workload']) != workload
                    or OwnedIdentity(**inputs['owned_identity']) != self._identity):
                raise ControllerError('runtime_image_authority_context_mismatch')
            return reconstruct_prior_node_image_references(context)
        except ControllerError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, OSError, RecursionError) as error:
            raise ControllerError('runtime_image_authority_invalid') from error

    def _abandon_for_teardown(self, family: str, intent: dict[str, object]) -> None:
        latch_teardown(self.journal_path)
        context = load_expected_context(self.journal_path)
        if context.family != family or decode(context.intent) != intent:
            raise ControllerError("pending_operation_mismatch")
        self._observe_terminal()

    def _start_profile(self) -> CommandResult:
        return self._run(colima_start_command(), "profile_start_failed")

    def _preflight_application_evidence(self, details):
        from kil.v3b2_application_evidence_budget import validate_application_dispatch_budget
        try:
            value = load_journal(self.journal_path)
            prospective = {**value, 'events': [*value['events'], {
                'sequence': len(value['events']) + 1, 'event': 'application_apply_intent',
                'details': details}]}
            context = load_expected_context(self.journal_path, prospective)
            if validate_application_dispatch_budget(context):
                requests = OPERATIONS['application_apply'].requests(context)
                observations = tuple(RawObservation(request.label,
                    () if request.command is None else request.command.argv,
                    () if request.command is None else request.command.env, 0, b'', b'') for request in requests)
                validate_application_dispatch_budget(context, observations)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ControllerError('application_evidence_budget_failed') from error

    def _collect_observations(self, context, *, requests=None):
        observations = []
        try:
            if requests is None:
                requests = OPERATIONS[context.family].requests(context)
        except (KeyError, ValueError, TypeError):
            return ()
        for request in requests:
            argv, env = (), ()
            try:
                if request.command is not None:
                    argv, env = request.command.argv, request.command.env
                    result = self._observe(request.command, "observation_transport_failed")
                    raw = RawObservation(request.label, argv, env, result.returncode,
                                         result.stdout_bytes, result.stderr_bytes)
                else:
                    if request.source == 'pre_driver_checkpoint':
                        from kil.v3b2_pre_driver_checkpoint import read_pre_driver_checkpoint_bytes
                        from kil.v3b2_application_evidence_budget import MAX_APPLICATION_CHECKPOINT_BYTES
                        if context.family != 'application_apply':
                            raise ControllerError('pre_driver_checkpoint_source_invalid')
                        payload = read_pre_driver_checkpoint_bytes(self.journal_path, context,
                            maximum=MAX_APPLICATION_CHECKPOINT_BYTES)
                    elif request.source == "policy_stage_checkpoint":
                        from kil.v3b2_policy_stage_checkpoint import read_policy_stage_checkpoint_bytes
                        if context.family != "application_apply":
                            raise ControllerError("policy_checkpoint_source_invalid")
                        payload = read_policy_stage_checkpoint_bytes(self.journal_path, context)
                    elif request.source == "control_plane_manifest_source":
                        from kil.v3b2_control_plane_manifest_source_record import (
                            encode_control_plane_manifest_source_record,
                            read_control_plane_manifest_source_record,
                        )
                        if context.family != "control_plane_manifest_source":
                            raise ControllerError(
                                "control_plane_manifest_source_invalid")
                        proof = read_control_plane_manifest_source_record(
                            path=self._control_plane_manifest_checkpoint_path(context),
                            context=context,
                        )
                        payload = encode_control_plane_manifest_source_record(
                            proof=proof, context=context,
                        )
                    elif request.source in {'profile_state', 'profile_roster'}:
                        from kil.v3b2_profile_state import capture, _paths
                        from kil.v3b2_colima_inventory import capture_roster
                        authority = decode(context.inputs)['profile_paths']
                        if authority != self.profile_paths.document():
                            raise ControllerError('profile_observation_authority_changed')
                        observer = capture if request.source == 'profile_state' else capture_roster
                        payload = _canonical_bytes(observer(_paths(authority)))
                    elif request.source == "file":
                        payload = _read_regular(Path(request.paths[0]), MAX_OBSERVATION_BYTES)
                    elif request.source == "hash":
                        path = Path(request.paths[0])
                        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                        try:
                            before = os.fstat(descriptor)
                            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 1024 * 1024 * 1024:
                                raise ControllerError("archive_observation_invalid")
                            digest, length = sha256(), 0
                            while True:
                                chunk = os.read(descriptor, 1024 * 1024)
                                if not chunk:
                                    break
                                length += len(chunk)
                                if length > 1024 * 1024 * 1024:
                                    raise ControllerError("archive_observation_invalid")
                                digest.update(chunk)
                            after = os.fstat(descriptor)
                            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or length != before.st_size:
                                raise ControllerError("archive_observation_changed")
                            payload = _canonical_bytes({"path": str(path), "byte_count": length, "sha256": digest.hexdigest()})
                        finally:
                            os.close(descriptor)
                    elif request.source == "lstat":
                        measured = {}
                        for name in request.paths:
                            try:
                                observed = Path(name).lstat()
                            except FileNotFoundError:
                                measured[name] = None
                            else:
                                measured[name] = {"mode": observed.st_mode, "inode": observed.st_ino, "device": observed.st_dev}
                        payload = _canonical_bytes(measured)
                    elif request.source == "tree":
                        from kil.v3b2_evidence import PUBLIC_FILES
                        directory = Path(request.paths[0])
                        if directory.is_symlink() or set(item.name for item in directory.iterdir()) != PUBLIC_FILES:
                            raise ControllerError("publication_tree_invalid")
                        payload = _canonical_bytes({name: _read_regular(directory / name, MAX_OBSERVATION_BYTES).hex() for name in PUBLIC_FILES})
                    else:
                        raise ControllerError("unrecognized_observation_source")
                    raw = RawObservation(request.label, (), (), 0, payload, b"")
            except (OSError, ValueError, ControllerError, ProofError, UnicodeError):
                raw = RawObservation(request.label, argv, env, -1, b"", b"observation_unavailable")
            observations.append(raw)
        return tuple(observations)

    def _observe_terminal(self):
        """The sole non-request terminal path in both normal execution and recovery."""
        context = load_expected_context(self.journal_path)
        decision = append_observed_terminal(self.journal_path, context, self._collect_observations(context))
        value = load_journal(self.journal_path)
        self._events = [(row["event"], dict(row["details"])) for row in value["events"]]
        state = decode(load_expected_context(self.journal_path, value, state_only=True).inputs)
        self._identity = OwnedIdentity(**state["owned_identity"])
        self._restore_foreign_comparison(state)
        self.owned_absence_proven = any(name == "profile_absence_proof_complete" for name, _ in self._events)
        return decision

    def _require_observed_terminal(self):
        decision = self._observe_terminal()
        if decision.outcome != "complete":
            latch_teardown(self.journal_path)
            raise ControllerError("operation_postcondition_unproved:" + decision.category)
        return decision

    def _checkpoint_application_policy(self):
        """Normal-dispatch barrier only; recovery never recollects this stage."""
        from kil.v3b2_application_policy_stage import application_policy_observation_specs, policy_request_bytes
        from kil.v3b2_policy_stage_checkpoint import publish_policy_stage_checkpoint
        from kil.v3b2_proofs import ObservationRequest
        try:
            context = load_expected_context(self.journal_path)
            inputs = decode(context.inputs)
            identity = OwnedIdentity(**inputs["owned_identity"])
            profile = V3B2Profile.from_mapping(inputs["profile"])
            workload = WorkloadIdentity(**inputs["workload"])
            requests = tuple(
                ObservationRequest(label, source="file", paths=(inputs["kind_config_path"],))
                if label == "kind_configuration" else ObservationRequest(label,
                    Command(argv, 60, env=env,
                            stdin=policy_request_bytes(profile, workload) if label == "policy_objects" else None))
                for label, argv, env in application_policy_observation_specs(identity))
            observations = self._collect_observations(context, requests=requests)
            publish_policy_stage_checkpoint(self.journal_path, context, observations)
        except (OSError, ValueError, TypeError, KeyError, ControllerError) as error:
            raise ControllerError("policy_stage_checkpoint_failed") from error

    def _control_plane_manifest_checkpoint_path(self, context) -> Path:
        return self.paths.private / (
            f"control-plane-manifest-source-{context.intent_sequence}.json"
        )

    def _checkpoint_control_plane_manifest_source(self) -> CommandResult:
        from kil.v3b2_control_plane_manifest_source import (
            control_plane_manifest_observation_specs,
            validate_control_plane_manifest_source,
        )
        from kil.v3b2_control_plane_manifest_source_record import (
            publish_control_plane_manifest_source_record,
        )

        context = load_expected_context(self.journal_path)
        identity = OwnedIdentity(**decode(context.inputs)["owned_identity"])
        observations = []
        for spec in control_plane_manifest_observation_specs(identity):
            result = self._observe(
                spec.command, "control_plane_manifest_source_invalid")
            observations.append(RawObservation(
                spec.label, spec.command.argv, spec.command.env,
                result.returncode, result.stdout_bytes, result.stderr_bytes,
            ))
        proof = validate_control_plane_manifest_source(
            context=context, owned_identity=identity,
            observations=tuple(observations),
        )
        publish_control_plane_manifest_source_record(
            path=self._control_plane_manifest_checkpoint_path(context),
            proof=proof, context=context,
        )
        return CommandResult(0, "", "")

    def _checkpoint_pre_driver_runtime(self):
        """Fresh normal-dispatch barrier; recovery never recollects this stage."""
        from kil.v3b2_pre_driver_checkpoint import pre_driver_observation_specs, publish_pre_driver_checkpoint
        from kil.v3b2_proofs import ObservationRequest
        try:
            context = load_expected_context(self.journal_path)
            inputs = decode(context.inputs)
            if (context.family != "application_apply"
                    or type(self.profile) is not V3B2Profile
                    or type(self._workload) is not WorkloadIdentity
                    or type(self._identity) is not OwnedIdentity
                    or V3B2Profile.from_mapping(inputs["profile"]) != self.profile
                    or WorkloadIdentity(**inputs["workload"]) != self._workload
                    or OwnedIdentity(**inputs["owned_identity"]) != self._identity
                    or inputs["kind_config_path"] != str(self.kind_config)):
                raise ControllerError("pre_driver_context_mismatch")
            requests = tuple(
                ObservationRequest(label, source="file", paths=(str(self.kind_config),))
                if label == "kind_configuration" else ObservationRequest(label,
                    Command(argv, 300 if label == "runtime_inventory" else 60, env=env))
                for label, argv, env in pre_driver_observation_specs(self._identity))
            observations = self._collect_observations(context, requests=requests)
            publish_pre_driver_checkpoint(self.journal_path, context, observations)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, ControllerError) as error:
            raise ControllerError("pre_driver_checkpoint_failed") from error

    @staticmethod
    def _profiles(payload: str) -> tuple[tuple[str, str], ...]:
        return tuple((row['name'], row['status']) for row in V3B2Controller._foreign_records(payload))

    @staticmethod
    def _foreign_records(payload: str) -> list[dict[str, object]]:
        from kil.v3b2_colima_inventory import decode_inventory
        try:
            return decode_inventory(payload.encode('utf-8') if type(payload) is str else payload)
        except ValueError:
            raise ControllerError('ambiguous_profile_inventory') from None

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
            archive_sha256 = images["kil_archive_sha256"]
        except Exception:
            raise ControllerError("content_identity_failed") from None
        if (
            manifest.get("schema_version") != "kil.v3b1-public-manifest.v3"
            or _digest(manifest_bytes) != _ACCEPTED_V3B1_MANIFEST_SHA256
            or manifest.get("promotion_status") != "not_promoted"
            or manifest.get("public_commitment_sha256") != _ACCEPTED_V3B1_COMMITMENT
            or type(kil_image) is not str
            or type(envoy_image) is not str
            or archive_sha256 != _ACCEPTED_KIL_ARCHIVE_SHA256
        ):
            raise ControllerError("content_identity_failed")
        archive_path = self.paths.tools.parent / "v3b2-input/kil-image.tar"
        try:
            archive = _read_regular(archive_path, 1024 * 1024 * 1024)
        except ControllerError:
            raise ControllerError("kil_image_archive_unavailable") from None
        if _archive_digest(archive) != archive_sha256:
            raise ControllerError("kil_image_archive_unavailable")
        self._kil_archive_bytes = archive
        try:
            return WorkloadIdentity(self.run_id, kil_image, envoy_image)
        except Exception:
            raise ControllerError("content_identity_failed") from None

    def preflight(self) -> dict[str, object]:
        if self._prepared or self.journal_path.exists():
            raise ControllerError("lifecycle_already_prepared")
        from kil.v3b2_profile_state import require_pristine
        try:
            require_pristine(self.profile_paths)
        except ValueError:
            raise ControllerError('owned_profile_remnant_or_unsafe_parent') from None
        self.paths.private.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.paths.private, 0o700)
        self.profile_paths.tmp.mkdir(mode=0o700, exist_ok=True)
        head = self._run(Command(("git", "rev-parse", "HEAD"), 30), "source_head_failed").stdout.strip()
        main = self._run(Command(("git", "rev-parse", "origin/main"), 30), "source_main_failed").stdout.strip()
        dirty = self._run(Command(("git", "status", "--porcelain"), 30), "source_status_failed").stdout
        if len(head) != 40 or any(ch not in _HEX40 for ch in head) or head != main or dirty:
            raise ControllerError("source_not_synchronized")
        self._tool_identities = self._verify_tool_lock()
        self._workload = self._accepted_workload()
        from kil.v3b2_proofs import _profile_rows
        try:
            full_profiles = _profile_rows(self._collect_profile_inventory(), self.profile_paths.document())
        except ValueError:
            raise ControllerError('ambiguous_or_incomplete_profile_inventory') from None
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
        self.docker_config.mkdir(mode=0o700)
        expected = tuple(sorted("/".join(key[1:]) for key in expected_object_keys(self.profile)))
        foreign = tuple(item for item in profiles if item[0] != LAB_IDENTITY)
        # Reviewed expectations are committed before the first owned mutation.
        # Recovery never rebuilds this document from a live candidate or a
        # potentially changed checkout.
        if self._workload is None or self._kil_archive_bytes is None:
            raise ControllerError("content_identity_failed")
        workload = self._workload
        projection_path = calico_path.with_suffix(".objects.json")
        calico_expected = calico_objects(calico_bytes, _read_regular(projection_path, 1024 * 1024))
        retained_archive = self.paths.private / "kil-image.tar"
        _write_exclusive(retained_archive, self._kil_archive_bytes)
        expected_inputs = {
            "run_id": self.run_digest, "node_image_source_version": 1,
            "control_plane_manifest_source_version": 1,
            "application_source_version": 1,
            "owned_identity": asdict(self._identity),
            "profile": json.loads(profile_bytes), "profile_sha256": _digest(profile_bytes),
            "profile_configuration": {"name": LAB_IDENTITY, "arch": "aarch64", "runtime": "docker",
                                      "cpus": 4, "memory": 8589934592, "disk": 64424509440},
            "workload": asdict(workload), "kind_node_image": self.profile.kind_node_image,
            "kind_config_path": str(self.kind_config), "kind_config_sha256": _digest(render_kind_config(self.profile)),
            "archive_path": str(retained_archive), "archive_sha256": _ACCEPTED_KIL_ARCHIVE_SHA256,
            "archive_byte_count": len(self._kil_archive_bytes),
            "images": [
                {"reference": "kil.local/kil-v3b2:sha256-" + workload.kil_image_id.removeprefix("sha256:"),
                 "manifest_digest": workload.kil_image_id,
                 "config_digest": _ACCEPTED_KIL_CONFIG_DIGEST,
                 # Media type is verified from the accepted archive's index
                 # and hash-matched manifest, never from a node observation.
                 "target_media_type": "application/vnd.oci.image.manifest.v1+json",
                 "allowed_repo_tags": ["kil.local/kil-v3b2:sha256-" + workload.kil_image_id.removeprefix("sha256:")],
                 # Optional content-addressed alias must join this exact
                 # independently accepted target; its presence is not assumed.
                 "allowed_repo_digests": ["kil.local/kil-v3b2@" + workload.kil_image_id]},
                {"reference": workload.envoy_image_digest,
                 "manifest_digest": "sha256:" + workload.envoy_image_digest.rsplit(":", 1)[1],
                 "config_digest": "sha256:ef846ec85aabf01a2ff7176a185260e476ca43d20478f57281d88f7a66d5671f",
                 # Pinned registry body SHA, descriptor header, and body
                 # mediaType independently agree on this OCI index type.
                 "target_media_type": "application/vnd.oci.image.index.v1+json",
                 "allowed_repo_tags": [],
                 "allowed_repo_digests": [workload.envoy_image_digest]}],
            "calico_objects": calico_expected,
            "application_objects": json.loads(render_objects(self.profile, workload))["items"],
            "runtime_contract_complete": False,
            "profile_paths": self.profile_paths.document(),
            "private_path": str(self.paths.private), "public_parent": str(self.paths.public),
            "active_paths": [str(path) for path in (self.kubeconfig, self.kind_config,
                self.paths.private / "calico-v3.32.0.yaml", self.docker_config)],
            "foreign_before": [row for row in full_profiles if row["name"] != LAB_IDENTITY],
            "global_context_before": context,
            'global_docker_config': self.global_docker_config,
        }
        expected_bytes = proof_canonical(expected_inputs)
        _write_exclusive(self.expected_inputs_path, expected_bytes)
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
                expected_inputs_sha256=_digest(expected_bytes),
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
        try:
            return self._up_lifecycle()
        except Exception:
            self._recover_to_owned_absence()
            raise

    def _up_lifecycle(self) -> dict[str, object]:
        if not self._prepared:
            self.preflight()
        if self._workload is None:
            self._tool_identities = self._verify_tool_lock()
            self._workload = self._accepted_workload()
        if self._up:
            raise ControllerError("lifecycle_reuse_forbidden")
        _write_exclusive(self.kind_config, render_kind_config(self.profile))
        profile_details = {"colima_profile": LAB_IDENTITY}
        self._journal_pair("profile_start", profile_details, self._start_profile)
        cluster_details = {"kind_cluster": LAB_IDENTITY, "kubeconfig": str(self.kubeconfig)}
        self._journal_pair("cluster_create", cluster_details,
                           lambda: self._run(kind_create_command(self._identity), "cluster_create_failed"))
        self._journal_pair(
            "control_plane_manifest_source",
            {"kind_cluster": LAB_IDENTITY},
            self._checkpoint_control_plane_manifest_source,
        )
        workload = self._workload
        if workload is None:
            raise ControllerError("content_identity_failed")
        kil_image = (
            "kil.local/kil-v3b2:sha256-"
            + workload.kil_image_id.removeprefix("sha256:")
        )
        envoy_image = workload.envoy_image_digest
        import_details = {
            "archive_sha256": _ACCEPTED_KIL_ARCHIVE_SHA256,
            "image": kil_image,
            "envoy_image": envoy_image,
        }
        def import_images() -> CommandResult:
            if self._kil_archive_bytes is None:
                raise ControllerError("kil_image_archive_unavailable")
            expected_images = decode(load_expected_context(self.journal_path).inputs)["images"]
            results = [
                self._run(command, "image_import_failed")
                for command in docker_image_import_commands(
                    self._identity, self._kil_archive_bytes, expected_images[0]["config_digest"],
                    kil_image, envoy_image,
                )
            ]
            for result, expected, expected_id in zip(
                results[-2:], (kil_image, envoy_image),
                tuple(row["config_digest"] for row in expected_images),
            ):
                try:
                    value = json.loads(result.stdout)
                except (json.JSONDecodeError, UnicodeError):
                    raise ControllerError("image_import_identity_invalid") from None
                if (
                    len(result.stdout.encode("utf-8")) > 1024 * 1024
                    or type(value) is not list or len(value) != 1
                    or type(value[0]) is not dict
                    or value[0].get("Id") != expected_id
                    or (
                        expected not in value[0].get("RepoTags", [])
                        and expected not in value[0].get("RepoDigests", [])
                    )
                ):
                    raise ControllerError("image_import_identity_invalid")
            return results[-1]
        self._journal_pair("image_import", import_details, import_images)
        self._journal_pair(
            "image_load",
            {"image": kil_image, "envoy_image": envoy_image},
            lambda: [
                self._run(kind_load_command(self._identity, image), "image_load_failed")
                for image in (kil_image, envoy_image)
            ][-1],
        )
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
        calico_ready = False
        for _attempt in range(60):
            try:
                for kind in ("DaemonSet", "Deployment"):
                    result = self._run(
                        kubectl_calico_workload_command(self._identity, kind),
                        "calico_readiness_failed",
                    )
                    parse_calico_runtime_workload(
                        result.stdout.encode("utf-8", errors="strict"), kind,
                    )
                calico_ready = True
                break
            except (InventoryError, UnicodeError):
                continue
        if not calico_ready:
            raise ControllerError("calico_readiness_failed")
        rendered = json.loads(render_objects(self.profile, workload))
        namespaces = [item for item in rendered["items"] if item["kind"] == "Namespace"]
        policies = [item for item in rendered["items"] if item["kind"] == "NetworkPolicy"]
        workloads = [item for item in rendered["items"] if item["kind"] not in {"Namespace", "NetworkPolicy", "Pod"}]
        drivers = [item for item in rendered["items"] if item["kind"] == "Pod"]
        payloads = tuple(_canonical_bytes({"apiVersion": "v1", "kind": "List", "items": items}) for items in (namespaces, policies, workloads))
        app_details = {"manifest_sha256": _digest(render_objects(self.profile, workload))}
        self._preflight_application_evidence(app_details)
        append_event(self.journal_path, "application_apply_intent", app_details)
        self._events.append(("application_apply_intent", dict(app_details)))
        try:
            node_image_authority = self._pending_runtime_image_authority(workload)
            for payload in payloads[:2]:
                self._run(kubectl_apply_command(self._identity, payload), "application_apply_failed")
            self._checkpoint_application_policy()
            self._run(kubectl_apply_command(self._identity, payloads[2]), "application_apply_failed")
            for _attempt in range(60):
                results = [
                    self._observe(
                        kubectl_workload_ready_command(self._identity, namespace, role),
                        "application_readiness_failed",
                    )
                    for _track, namespace in TRACK_NAMESPACES
                    for role in ("envoy", "authz", "target")
                ]
                if not all(result.returncode == 0 for result in results):
                    continue
                try:
                    ready = []
                    for _track, namespace in TRACK_NAMESPACES:
                        for role in ("envoy", "authz", "target"):
                            endpoint_result = self._run(
                                kubectl_ready_endpoint_command(self._identity, namespace, role),
                                "application_readiness_failed",
                            )
                            endpoint, pod_uid = parse_ready_endpoint_slice(
                                endpoint_result.stdout.encode("utf-8"),
                                expected_namespace=namespace, expected_service=role,
                            )
                            ready.append((endpoint, pod_uid))
                    if len(ready) == 9:
                        break
                except (InventoryError, UnicodeError, ControllerError):
                    continue
            else:
                raise ControllerError("application_readiness_failed")
            self._checkpoint_pre_driver_runtime()
            self._run(
                kubectl_apply_command(
                    self._identity,
                    _canonical_bytes({"apiVersion": "v1", "kind": "List", "items": drivers}),
                ),
                "application_apply_failed",
            )
        except ControllerError:
            self._abandon_for_teardown("application_apply", app_details)
            raise
        self._require_observed_terminal()
        snapshot = None
        for _attempt in range(60):
            projection = self._observe(
                Command((
                    "kubectl", "--kubeconfig", str(self.kubeconfig), "get",
                    "namespaces,pods,services,endpoints,endpointslices,serviceaccounts,configmaps,deployments,daemonsets,networkpolicies,nodes,replicasets",
                    "--all-namespaces", "--output", "json",
                ), 300),
                "runtime_inventory_failed",
            )
            if projection.returncode != 0:
                continue
            try:
                candidate = parse_proved_runtime_inventory(
                    projection.stdout.encode("utf-8", errors="strict"),
                    profile=self.profile, workload=workload,
                    owned_identity=self._identity, node_images=node_image_authority,
                )
                snapshot = candidate
                break
            except (InventoryError, UnicodeError, TypeError):
                continue
        if snapshot is None:
            raise ControllerError("runtime_inventory_invalid") from None
        projected = {
            "topology_attestation": {
                "cluster_incarnation_uid": snapshot.cluster_incarnation_uid,
                "node_container_id": snapshot.node_container_id,
                "namespaces": list(snapshot.namespaces),
                "objects": [asdict(item) for item in snapshot.objects],
                "pod_images": [asdict(item) for item in snapshot.pod_images],
                "endpoints": [{**asdict(item), "addresses": list(item.addresses)} for item in snapshot.endpoints],
                "calico_readiness": {
                    "node_desired": snapshot.calico_node_desired,
                    "node_ready": snapshot.calico_node_ready,
                    "controller_desired": snapshot.calico_controller_desired,
                    "controller_ready": snapshot.calico_controller_ready,
                },
            },
            "policy_attestation": {
                "edges": [{
                    "namespace": item.namespace,
                    "source_roles": list(item.source_roles),
                    "destination_namespace": item.destination_namespace,
                    "destination_roles": list(item.destination_roles),
                    "protocol_ports": [list(pair) for pair in item.protocol_ports],
                } for item in snapshot.policy_graph],
            },
        }
        self._runtime_projection = projected
        _write_exclusive(self.runtime_projection_path, _canonical_bytes(projected))
        readiness = {"attestation_sha256": _digest(_canonical_bytes(projected))}
        self._journal_pair("readiness", readiness, lambda: CommandResult(0, "", ""))
        self._up = True
        return {"cluster": LAB_IDENTITY, "run_id": self.run_id, "ready": True}

    def _start_driver(self, track: str) -> tuple[str, str, str]:
        namespace = dict(TRACK_NAMESPACES)[track]
        if self._workload is None:
            raise ControllerError("content_identity_failed")
        expected_image = (
            "kil.local/kil-v3b2:sha256-"
            + self._workload.kil_image_id.removeprefix("sha256:")
        )
        pod_result = self._run(
            kubectl_driver_pod_command(self._identity, namespace),
            "driver_identity_failed",
        )
        try:
            pod = parse_runtime_pod_identity(
                pod_result.stdout.encode("utf-8"),
                expected_namespace=namespace,
                expected_pod="driver",
                expected_container="driver",
                expected_image=expected_image,
            )
        except (InventoryError, UnicodeError):
            raise ControllerError("driver_identity_invalid") from None
        readiness_command = Command((
            "kubectl", "--kubeconfig", str(self.kubeconfig), "logs", "pod/driver",
            "--namespace", namespace, "--limit-bytes=1048576",
        ), 300)
        readiness = None
        for _attempt in range(60):
            readiness_result = self._run(readiness_command, "driver_readiness_failed")
            try:
                lines = tuple(line + b"\n" for line in readiness_result.stdout.encode("utf-8").splitlines())
                if len(lines) != 1 or len(lines[0]) > MAX_RESULT_BYTES:
                    raise DriverProtocolError("driver readiness record count is not exact")
                candidate = parse_result(lines[0], expected_track=track)
                if candidate.get("schema_version") != "kil.v3b1-driver-readiness.v1":
                    raise DriverProtocolError("driver readiness schema is not exact")
                readiness = candidate
                break
            except (DriverProtocolError, UnicodeError):
                continue
        if readiness is None:
            raise ControllerError("driver_readiness_invalid")
        details = {"namespace": namespace, "pod": pod.pod, "uid": pod.uid}
        self._journal_pair("driver_start", details, lambda: CommandResult(0, "", ""))
        identity = (namespace, pod.pod, pod.uid)
        self._drivers.append(identity)
        return identity

    def _runtime_pod_identity(
        self, namespace: str, pod: str, container: str, image: str,
        *, require_ready: bool,
    ):
        observed = self._run(
            kubectl_source_pod_command(self._identity, namespace, pod),
            "pod_identity_failed",
        )
        try:
            return parse_runtime_pod_identity(
                observed.stdout.encode("utf-8"),
                expected_namespace=namespace,
                expected_pod=pod,
                expected_container=container,
                expected_image=image,
                require_ready=require_ready,
            )
        except (InventoryError, UnicodeError):
            raise ControllerError("pod_identity_invalid") from None

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

    def _capture_sources(self) -> dict[str, object]:
        if self._runtime_projection is None:
            raise ControllerError("runtime_inventory_missing")
        topology = self._runtime_projection["topology_attestation"]
        assert type(topology) is dict
        images = topology.get("pod_images")
        if type(images) is not list:
            raise ControllerError("runtime_inventory_invalid")
        captured: list[CapturedSource] = []
        attestations: list[dict[str, object]] = []
        source_bindings: list[dict[str, object]] = []
        journal = load_journal(self.journal_path)
        instructions = {row["details"]["track"]: row["details"]["case_sha256"]
                        for row in journal["events"] if row["event"] == "request_intent"}
        kind_roles = (("driver", "driver"), ("decision", "authz"), ("envoy", "envoy"), ("target", "target"))
        for track, namespace in TRACK_NAMESPACES:
            for kind, role in kind_roles:
                matches = [item for item in images if type(item) is dict and item.get("namespace") == namespace and item.get("container") == role]
                if len(matches) != 1:
                    raise ControllerError("source_identity_invalid")
                source = matches[0]
                if any(type(source.get(name)) is not str or not source[name] for name in ("pod", "uid", "resource_version", "image", "image_id", "container_id")):
                    raise ControllerError("source_identity_invalid")
                pod_name = str(source["pod"])
                command = (
                    kubectl_source_read_command(self._identity, namespace, pod_name, role)
                    if role in {"authz", "target"}
                    else Command((
                        "kubectl", "--kubeconfig", str(self.kubeconfig), "logs", f"pod/{pod_name}",
                        "--namespace", namespace, "--limit-bytes=1048576",
                    ), 300)
                )
                reader = _KubectlSourceReader(
                    self, command, kubectl_source_pod_command(self._identity, namespace, pod_name),
                    source_kind=f"{track}:{kind}", namespace=namespace,
                    pod=pod_name, container=role, image=str(source["image"]),
                    uid=str(source["uid"]), resource_version=str(source["resource_version"]),
                    container_id=str(source["container_id"]),
                )
                try:
                    capture = capture_source(
                        reader,
                        reader.identity(),
                        1024 * 1024,
                        private_diagnostic_path=(
                            self.paths.private / f"diagnostic-{track}-{kind}.json"
                        ),
                    )
                except Exception:
                    raise ControllerError("source_capture_invalid") from None
                payload = capture.payload
                try:
                    records = [json.loads(line) for line in payload.splitlines() if line]
                except (UnicodeError, json.JSONDecodeError):
                    raise ControllerError("source_capture_invalid") from None
                captured.append(capture)
                capture_path = self.paths.private / f"source-{track}-{kind}.jsonl"
                if capture_path.exists():
                    if _read_regular(capture_path, 1024 * 1024) != payload:
                        raise ControllerError("frozen_source_changed")
                else:
                    _write_exclusive(capture_path, payload)
                binding = {
                    "namespace": namespace, "pod": pod_name, "container": role,
                    "uid": capture.identity.object_uid,
                    "resource_version": capture.identity.resource_version,
                    "container_id": capture.identity.container_id,
                    "byte_count": capture.identity.byte_count, "sha256": capture.identity.sha256,
                    "raw_records": records,
                }
                source_bindings.append({"kind": kind, "track": track, "capture": binding,
                                        "instruction_sha256": instructions.get(track)})
        binding_bytes = _canonical_bytes({"run_id": self.run_id, "sources": source_bindings})
        binding_path = self.paths.private / "source-captures.json"
        if binding_path.exists():
            if _read_regular(binding_path, 16 * 1024 * 1024) != binding_bytes:
                raise ControllerError("frozen_source_binding_changed")
        else:
            _write_exclusive(binding_path, binding_bytes)
        for track in TRACKS:
            sources = {row["kind"]: row["capture"]["raw_records"] for row in source_bindings if row["track"] == track}
            try:
                reduced = adapt_producer_sources(sources, track=track, run_id=self.run_id)
            except Exception:
                self._source_producer_invalid = True
                continue
            for row in source_bindings:
                if row["track"] == track:
                    records = reduced[row["kind"]]
                    self._application_records += len(records)
                    attestations.append({**row, "records": records})
        self._captured_sources = captured
        self._source_attestations = attestations
        return {"evidence_sha256": _digest(binding_bytes)}

    def _freeze(self) -> None:
        freeze = self._capture_sources()
        self._journal_pair("evidence_freeze", freeze, lambda: CommandResult(0, "", ""))

    def _cancel_drivers(self) -> None:
        state = decode(load_expected_context(self.journal_path, state_only=True).inputs)
        if state["teardown_only"]:
            # Only source incarnations established by a preceding durable proof
            # may be canceled without a separate driver-start registration.
            observed = {row["namespace"]: (row["namespace"], row["pod"], row["uid"])
                        for row in state["source_images"] if row["container"] == "driver"}
            self._drivers = [observed[namespace] for _track, namespace in TRACK_NAMESPACES if namespace in observed]
        failed = False
        for namespace, pod, uid in self._drivers:
            if namespace in self._canceled:
                continue
            details = {"namespace": namespace, "pod": pod, "uid": uid}
            append_event(self.journal_path, "driver_cancel_intent", details)
            # Observe-first for normal cancellation too: matching Pod UID is
            # insufficient when its container process has restarted.
            result = self.recover()
            if result["proof_outcome"] not in {"complete", "teardown_only"}:
                raise ControllerError("driver_cancel_postcondition_unproved")
            self._canceled.add(namespace)
            failed = failed or result["proof_outcome"] == "teardown_only"
        if failed:
            raise ControllerError("driver_cancel_postcondition_invalid")

    def _quiesce(self) -> None:
        # Current control targets come from replayed prior proofs, never the
        # convenience projection file or a candidate observation.
        images = decode(load_expected_context(self.journal_path, state_only=True).inputs)["source_images"]
        if not images:
            raise ControllerError("runtime_inventory_missing")
        commands: list[tuple[dict[str, object], Command, Command]] = []
        for _track, namespace in TRACK_NAMESPACES:
            matches = [row for row in images if type(row) is dict and row.get("namespace") == namespace and row.get("container") == "envoy"]
            if len(matches) != 1 or type(matches[0].get("pod")) is not str:
                raise ControllerError("source_identity_invalid")
            commands.append((matches[0], *kubectl_envoy_quiesce_commands(self._identity, namespace, str(matches[0]["pod"]))))
        command_digest = _digest(_canonical_bytes([
            [list(command.argv) for command in pair[1:]] for pair in commands
        ]))
        details = {"attestation_sha256": command_digest}
        append_event(self.journal_path, "envoy_quiesce_intent", details)
        self._events.append(("envoy_quiesce_intent", dict(details)))
        try:
            required = {
                "http.kil_v3b_ingress.downstream_cx_active",
                "http.kil_v3b_ingress.downstream_rq_active",
                "cluster.kil-v3b-authz.upstream_rq_active",
                "cluster.kil-v3b-target.upstream_rq_active",
            }
            for source, drain, inspect in commands:
                before = self._runtime_pod_identity(
                    str(source["namespace"]), str(source["pod"]), "envoy",
                    str(source["image"]), require_ready=True,
                )
                if before.uid != source.get("uid") or before.container_id != source.get("container_id"):
                    raise ControllerError("envoy_quiesce_identity_invalid")
                drained = self._run(drain, "envoy_quiesce_failed")
                if drained.stdout != '{"drain_requested":true}\n':
                    raise ControllerError("envoy_quiesce_invalid")
                observed = self._run(inspect, "envoy_quiesce_failed")
                try:
                    value = json.loads(observed.stdout)
                    rows = value["stats"]
                    selected = {row["name"]: row["value"] for row in rows if type(row) is dict and row.get("name") in required}
                except (KeyError, TypeError, json.JSONDecodeError):
                    raise ControllerError("envoy_quiesce_invalid") from None
                if set(selected) != required or any(value != 0 for value in selected.values()):
                    raise ControllerError("envoy_quiesce_invalid")
                after = self._runtime_pod_identity(
                    before.namespace, before.pod, before.container, before.image,
                    require_ready=False,
                )
                if after.uid != before.uid or after.container_id != before.container_id:
                    raise ControllerError("envoy_quiesce_identity_invalid")
        except ControllerError:
            self._abandon_for_teardown("envoy_quiesce", details)
            raise
        self._require_observed_terminal()

    def _teardown(self) -> None:
        # Normal teardown uses the same observe-first cleanup operations as
        # recovery, but does not latch a successful lifecycle into failure.
        for _attempt in range(32):
            result = self._advance_teardown()
            self._events = [(row["event"], dict(row["details"])) for row in load_journal(self.journal_path)["events"]]
            if any(name == "foreign_snapshot_comparison_complete" for name, _ in self._events):
                return
            if result["proof_outcome"] == "unknown":
                raise ControllerError("owned_teardown_postcondition_unproved")
        raise ControllerError("owned_teardown_bound_exceeded")

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
        try:
            prepared = prepare_publication(private, self.paths.public)
        except Exception:
            raise ControllerError("publication_failed") from None
        details = {
            "destination": str(prepared.destination),
            "public_commitment_sha256": prepared.public_commitment,
            "tree_commitment_sha256": prepared.tree_commitment,
        }
        append_event(self.journal_path, "publication_intent", details)
        self._events.append(("publication_intent", dict(details)))
        try:
            from kil.v3b2_public_image_provenance import validate_public_image_provenance
            context = load_expected_context(self.journal_path)
            validate_public_image_provenance(context, dict(prepared.payloads)['manifest.json'])
            published = publish_prepared(prepared)
            verify_publication_identity(
                published,
                run_id=self.run_id,
                public_commitment=prepared.public_commitment,
                tree_commitment=prepared.tree_commitment,
            )
        except Exception:
            raise ControllerError("publication_failed") from None
        self._require_observed_terminal()
        self.published_path = published
        self.public_commitment = prepared.public_commitment
        return published

    def request_free(self) -> dict[str, object]:
        if self._used_mode is not None:
            raise ControllerError("lifecycle_reuse_forbidden")
        self._used_mode = "request-free"
        self._select_mode("request-free")
        try:
            self.up()
            for track in TRACKS:
                self._start_driver(track)
            self._cancel_drivers()
            self._quiesce()
            self._freeze()
            self._teardown()
            if self._source_producer_invalid:
                raise ControllerError("source_producer_invalid")
            if self._application_records:
                raise ControllerError("request_free_records_present")
            published = self._publish()
            return {"run_id": self.run_id, "instructions_sent": 0, "application_records": self._application_records, "owned_teardown": True, "bundle": str(published), "public_commitment": self.public_commitment}
        except Exception:
            self._recover_to_owned_absence()
            raise

    def nominal(self) -> NominalBundle:
        if self._used_mode is not None:
            raise ControllerError("lifecycle_reuse_forbidden")
        self._used_mode = "nominal"
        self._select_mode("nominal")
        try:
            return self._nominal_lifecycle()
        except Exception:
            self._recover_to_owned_absence()
            raise

    def _nominal_lifecycle(self) -> NominalBundle:
        self.up()
        results: list[tuple[str, int, int]] = []
        failure: ControllerError | None = None
        for track in TRACKS:
            self._start_driver(track)
            instruction = self._instruction(track)
            _write_exclusive(self.paths.private / f"instruction-{track}.json", instruction)
            case = {"track": track, "request_id": NOMINAL_REQUEST_ID, "case_sha256": _digest(instruction)}
            append_event(self.journal_path, "request_intent", case)
            self._events.append(("request_intent", dict(case)))
            self._events.append(("kubectl_attach", {"track": track, "request_id": NOMINAL_REQUEST_ID}))
            try:
                result = self._run(
                    kubectl_attach_command(self._identity, dict(TRACK_NAMESPACES)[track], instruction),
                    "request_transport_failed",
                )
            except ControllerError as error:
                failure = error
                break
            try:
                payload = result.stdout.encode("utf-8")
                if len(payload) > 2 * MAX_RESULT_BYTES:
                    raise DriverProtocolError("driver result exceeds bound")
                lines = tuple(line + b"\n" for line in payload.splitlines())
                if len(lines) not in {1, 2}:
                    raise DriverProtocolError("driver attach stream cardinality is invalid")
                parsed = tuple(parse_result(line, expected_track=track) for line in lines)
                if len(parsed) == 2 and parsed[0].get("schema_version") != "kil.v3b1-driver-readiness.v1":
                    raise DriverProtocolError("driver attach readiness prefix is invalid")
                record = parsed[-1]
                if record.get("schema_version") != "kil.v3b1-driver-result.v1" or record.get("status") != "complete":
                    raise DriverProtocolError("driver result is not complete")
                expected_item = _EXPECTED_TUPLE[len(results)]
                if record.get("response_status") != expected_item[1]:
                    raise DriverProtocolError("driver response status differs from case")
                item = expected_item
            except (DriverProtocolError, UnicodeError):
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
        if self._source_producer_invalid:
            raise ControllerError("source_producer_invalid")
        if failure is not None:
            raise failure
        result_tuple = tuple(results)
        if result_tuple != _EXPECTED_TUPLE:
            raise ControllerError("nominal_tuple_invalid")
        published = self._publish()
        if self.public_commitment is None:
            raise ControllerError("publication_failed")
        return NominalBundle(
            self.run_id, result_tuple, len(results), True,
            str(published), self.public_commitment,
        )

    def _recover_to_owned_absence(self) -> None:
        if not self.journal_path.exists():
            return
        latch_teardown(self.journal_path)
        for _attempt in range(64):
            resumed = V3B2Controller(self.paths, self.runner)
            names = {name for name, _ in resumed.events}
            if "foreign_snapshot_comparison_complete" in names:
                comparison = next(details for name, details in resumed.events if name == "foreign_snapshot_comparison_complete")
                self.owned_absence_proven = resumed.owned_absence_proven
                if comparison["unchanged"] is not True:
                    raise ControllerError("foreign_state_changed")
                return
            result = resumed.recover()
            if result["proof_outcome"] == "unknown":
                raise ControllerError("safe_cleanup_unproved:" + result.get("proof_category", "unknown"))
        raise ControllerError("safe_cleanup_unproved:bounded_recovery_exhausted")

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
        events = journal["events"]
        if events and events[-1]["event"].endswith("_intent") and events[-1]["event"] != "request_intent":
            context = load_expected_context(self.journal_path)
            observations = self._collect_observations(context)
            decision = append_observed_terminal(self.journal_path, context, observations)
            if decision.outcome == "unknown":
                from kil.v3b2_proofs import cleanup_commands
                commands = cleanup_commands(context, observations)
                for command in commands:
                    self._observe(command, "recovery_cleanup_transport_failed")
                if context.family == "profile_delete":
                    self._clear_active_paths_if_profile_absent()
                if commands or context.family == "profile_delete":
                    decision = self._observe_terminal()
            value = load_journal(self.journal_path)
            self._events = [(row["event"], dict(row["details"])) for row in value['events']]
            self._restore_foreign_comparison(decode(load_expected_context(self.journal_path, value, state_only=True).inputs))
            return {"commands_run": sum(row.command is not None for row in OPERATIONS[context.family].requests(context)),
                    "publication_allowed": decision.outcome == "complete" and context.family == "publication",
                    "completed": context.family if decision.outcome == "complete" else None,
                    "proof_outcome": decision.outcome, "proof_category": decision.category}
        # Explicit recovery never resumes setup or requests. Once no operation is
        # pending, advance only one exact owned cleanup stage.
        latch_teardown(self.journal_path)
        return self._advance_teardown()

    def _clear_active_paths_if_profile_absent(self):
        from kil.v3b2_proofs import _profile_rows
        context = load_expected_context(self.journal_path, state_only=True)
        observations = self._collect_profile_inventory()
        try:
            rows = _profile_rows(observations, self.profile_paths.document())
        except ValueError:
            return False
        if any(row["name"] == LAB_IDENTITY for row in rows):
            return False
        expected = decode(context.inputs)
        from kil.v3b2_profile_state import absent, capture, clear_private_docker
        try:
            profile_absent = absent(expected['profile_paths'], capture(self.profile_paths))
        except (ValueError, OSError):
            # Invalid or unreadable disk-container metadata remains an unknown
            # proof, with all private recovery material retained.
            return False
        if not profile_absent:
            return False
        for name in expected["active_paths"]:
            path = Path(name)
            try:
                row = path.lstat()
            except FileNotFoundError:
                continue
            if path == self.docker_config and stat.S_ISDIR(row.st_mode):
                clear_private_docker(self.profile_paths)
            elif path in {self.kubeconfig, self.kind_config, self.paths.private / "calico-v3.32.0.yaml"} and stat.S_ISREG(row.st_mode):
                path.unlink()
            else:
                raise ControllerError("private_active_state_identity_invalid")
        descriptor = os.open(self.paths.private, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return True

    def _collect_profile_inventory(self):
        from kil.v3b2_proofs import ExpectedContext, inventory_requests
        inputs = {'profile_paths': self.profile_paths.document()}
        context = ExpectedContext(self.run_digest, 1, 'profile_start', b'{}\n', proof_canonical(inputs))
        return self._collect_observations(context, requests=inventory_requests(inputs))

    def _advance_teardown(self):
        journal = load_journal(self.journal_path)
        names = {row["event"] for row in journal["events"]}
        state = decode(load_expected_context(self.journal_path, journal, state_only=True).inputs)
        self._identity = OwnedIdentity(**state["owned_identity"])
        profile = {"colima_profile": LAB_IDENTITY}
        noop = lambda: CommandResult(0, "", "")
        if "profile_absence_proof_complete" in names:
            self.owned_absence_proven = True
            if "foreign_snapshot_comparison_complete" not in names:
                self._compare_foreign()
            return {"proof_outcome": "complete", "completed": "owned_teardown", "publication_allowed": False, "commands_run": 0}
        if "profile_start_failed" in names:
            self._clear_active_paths_if_profile_absent()
            self._journal_pair("profile_absence_proof", profile, noop)
        elif "profile_delete_complete" in names:
            self._journal_pair("profile_absence_proof", profile, noop)
        elif "profile_stop_complete" in names:
            append_event(self.journal_path, "profile_delete_intent", profile)
            return self.recover()
        elif "cluster_absence_proof_complete" in names or (
            self._identity.node_container_id is None and not any(row["event"].startswith("cluster_create_") for row in journal["events"])
        ):
            append_event(self.journal_path, "profile_stop_intent", profile)
            return self.recover()
        elif "cluster_delete_complete" in names:
            self._journal_pair("cluster_absence_proof",
                {"kind_cluster": LAB_IDENTITY, "node_container_id": self._identity.node_container_id}, noop)
        elif self._identity.node_container_id is not None:
            if "readiness_complete" in names and "evidence_freeze_complete" not in names:
                if journal["lifecycle_mode"] == "request-free":
                    self._cancel_drivers()
                if "envoy_quiesce_complete" not in names and "envoy_quiesce_abandoned_for_teardown" not in names:
                    self._quiesce()
                self._freeze()
            self._cancel_drivers()
            # Append intent, then let the registry prove either absence or exact
            # current ownership before the first (or a repeated) deletion.
            append_event(self.journal_path, "cluster_delete_intent",
                         {"kind_cluster": LAB_IDENTITY, "kubeconfig": str(self.kubeconfig)})
            return self.recover()
        else:
            return {"proof_outcome": "unknown", "proof_category": "ownership_not_established",
                    "completed": None, "publication_allowed": False, "commands_run": 0}
        return {"proof_outcome": "complete", "completed": load_journal(self.journal_path)["phase"],
                "publication_allowed": False, "commands_run": 0}

    def _compare_foreign(self):
        # Intent records the expected baseline. Its observed result and private
        # after-state come solely from the registry's one retained complete sample.
        compare = {"unchanged": True, "attestation_sha256": _digest(_canonical_bytes(
            {"profiles": self._foreign_records_before, "global_context": self._context_before}))}
        self._journal_pair("foreign_snapshot_comparison", compare, lambda: CommandResult(0, "", ""))
        if self._foreign_records_after != self._foreign_records_before or self._context_after != self._context_before:
            raise ControllerError("foreign_state_changed")


__all__ = [
    "CommandResult", "CommandRunner", "ControllerError", "ControllerPaths",
    "NominalBundle", "SubprocessCommandRunner", "V3B2Controller",
]
