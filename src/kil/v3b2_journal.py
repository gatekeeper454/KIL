"""Durable V3B-2a lifecycle journal and closed recovery authority."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, fields
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
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
_KIL_IMAGE = re.compile(r"kil\.local/kil-v3b2:sha256-[0-9a-f]{64}")
_ENVOY_IMAGE = re.compile(r"docker\.io/envoyproxy/envoy@sha256:[0-9a-f]{64}")
_ENV_KEYS = ("DOCKER_CONFIG", "DOCKER_HOST")
COLIMA_START_ARGV = (
    "colima", "start", "--profile", LAB_IDENTITY, "--runtime", "docker",
    "--activate=false", "--ssh-config=false", "--cpus", "4", "--memory", "8", "--disk", "60",
    "--vm-type", "vz", "--kubernetes=false", "--arch=aarch64", "--save-config=true",
    "--template=false", "--binfmt=false", "--vz-rosetta=false", "--mount-inotify=false",
    "--network-mode=shared", "--network-address=false", "--network-host-addresses=false",
    "--network-preferred-route=false", "--port-forwarder=ssh", "--ssh-agent=false",
    "--mount", "none", "--mount-type=virtiofs",
)
_APPLICATION_NAMESPACES = (
    "kil-v3-baseline",
    "kil-v3-local-reduce",
    "kil-v3-signed",
)
from kil.v3b2_envoy_quiescence import (
    ENVOY_DRAIN_SCRIPT as _ENVOY_DRAIN_SCRIPT,
    ENVOY_STATS_SCRIPT as _ENVOY_STATS_SCRIPT,
)


class JournalError(ValueError):
    """Raised when journal bytes or recovery authority are not closed."""


def _exact_string(label: str, value: object, *, maximum: int = 4096) -> str:
    if type(value) is not str or not value:
        raise JournalError(f"{label} must be an exact bounded nonempty string")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise JournalError(f"{label} contains invalid Unicode") from error
    if len(encoded) > maximum:
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
        try:
            oversized_argv = any(len(value.encode("utf-8")) > 65536 for value in self.argv)
        except UnicodeEncodeError as error:
            raise JournalError("command argv contains invalid Unicode") from error
        if oversized_argv:
            raise JournalError("command argument exceeds its byte bound")
        if type(self.timeout_s) is not int or self.timeout_s <= 0 or self.timeout_s > 900:
            raise JournalError("command timeout must be an exact bounded positive integer")
        if self.stdin is not None and type(self.stdin) is not bytes:
            raise JournalError("command stdin must be exact bytes or null")
        stdin_limit = 1024 * 1024 * 1024 if self.argv == ("docker", "load") and self.mutating else 1024 * 1024
        if self.stdin is not None and len(self.stdin) > stdin_limit:
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
            try:
                oversized_binding = len(pair[0].encode("utf-8")) > 256 or len(pair[1].encode("utf-8")) > 65536
            except UnicodeEncodeError as error:
                raise JournalError("command env binding contains invalid Unicode") from error
            if oversized_binding:
                raise JournalError("command env binding exceeds its byte bound")
            keys.append(pair[0])
        if len(keys) != len(set(keys)) or tuple(sorted(self.env)) != self.env:
            raise JournalError("command env bindings must be unique and sorted")
        if type(self.mutating) is not bool:
            raise JournalError("command mutating flag must be an exact boolean")
        environment = dict(self.env)
        raw_executable = self.argv[0]
        executable_path = Path(raw_executable)
        locked_tool = (
            executable_path.is_absolute()
            and ".." not in executable_path.parts
            and len(executable_path.parts) >= 3
            and executable_path.parts[-3:-1] == (".tools", "bin")
            and executable_path.name in {"docker", "kind", "kubectl"}
        )
        executable = executable_path.name if locked_tool else raw_executable
        if executable not in {"colima", "docker", "git", "kind", "kubectl", "limactl"}:
            raise JournalError("command executable is outside the closed allowlist")
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
        version_argv = {
            "docker": (raw_executable, "--version"),
            "kind": (raw_executable, "version"),
            "kubectl": (raw_executable, "version", "--client", "-o", "json"),
        }
        locked_version_read = locked_tool and self.argv == version_argv[executable]
        global_context_read = executable == "docker" and self.argv == ("docker", "context", "show")
        if executable in {"docker", "kind"} and not global_context_read and not locked_version_read:
            if tuple(environment) != _ENV_KEYS:
                raise JournalError("Docker/Kind commands require only both isolated bindings")
            _absolute_path("Docker configuration directory", environment["DOCKER_CONFIG"])
            endpoint = _exact_string("Docker endpoint", environment["DOCKER_HOST"])
            if not endpoint.startswith("unix:///") or not endpoint.endswith("/kil-v3-lab/docker.sock"):
                raise JournalError("Docker/Kind command endpoint is not journal-bound")
        if executable == "kind" and self.mutating:
            is_image_load = len(self.argv) >= 3 and self.argv[1:3] == ("load", "docker-image")
            if names != (LAB_IDENTITY,) or (not is_image_load and len(kubeconfigs) != 1) or (is_image_load and kubeconfigs):
                raise JournalError("mutating Kind command may name only kil-v3-lab")
        if executable == "kubectl" and not locked_version_read:
            if len(self.argv) < 3 or self.argv[1] != "--kubeconfig" or kubeconfigs != (self.argv[2],):
                raise JournalError("kubectl command requires an explicit leading kubeconfig")
            _absolute_path("kubectl kubeconfig", self.argv[2])
        if executable == "colima" and self.mutating:
            if profiles != (LAB_IDENTITY,):
                raise JournalError("mutating Colima command may name only kil-v3-lab")
        if locked_tool:
            if not locked_version_read or self.mutating or self.stdin is not None or self.env:
                raise JournalError("locked tool command is outside the closed version grammar")
        elif executable == "colima":
            allowed = {
                ("colima", "version"): False,
                COLIMA_START_ARGV: True,
                ("colima", "stop", "--profile", LAB_IDENTITY): True,
                ("colima", "delete", "--profile", LAB_IDENTITY, "--force", "--data"): True,
                ("colima", "status", "--profile", LAB_IDENTITY): False,
                ("colima", "list", "--json"): False,
            }
            if self.argv not in allowed or self.mutating is not allowed[self.argv]:
                raise JournalError("Colima command is outside the closed argv grammar")
            if self.stdin is not None or (self.env and set(environment) != {'DOCKER_CONFIG', 'TMPDIR'}):
                raise JournalError("Colima command carries unreviewed input or environment")
            if self.env:
                for key in ('DOCKER_CONFIG', 'TMPDIR'):
                    _absolute_path('Colima private ' + key, environment[key])
                if Path(environment['DOCKER_CONFIG']).name != 'docker-config' or Path(environment['TMPDIR']) != Path(environment['DOCKER_CONFIG']).parent / 'runtime-tmp':
                    raise JournalError('Colima private environment is not one owned directory')
        elif executable == "limactl":
            disk_delete = self.argv == ('limactl', 'disk', 'delete', 'colima-kil-v3-lab')
            if disk_delete:
                if not self.mutating or self.stdin is not None or set(environment) != {'LIMA_HOME'}:
                    raise JournalError('Lima disk fallback lacks scoped authority')
                _absolute_path('Lima home', environment['LIMA_HOME'])
                if Path(environment['LIMA_HOME']).parts[-2:] != ('.colima', '_lima'):
                    raise JournalError('Lima fallback home is not Colima-owned')
            elif self.argv != ("limactl", "--version") or self.mutating or self.stdin is not None or self.env:
                raise JournalError("Lima command is outside the closed version grammar")
        elif executable == "docker":
            image_mutation = (
                self.argv == ("docker", "load") and self.stdin is not None
            ) or (
                len(self.argv) == 4 and self.argv[:2] == ("docker", "tag")
                and re.fullmatch(r"sha256:[0-9a-f]{64}", self.argv[2]) is not None
                and _KIL_IMAGE.fullmatch(self.argv[3]) is not None
            ) or (
                len(self.argv) == 3 and self.argv[:2] == ("docker", "pull")
                and _ENVOY_IMAGE.fullmatch(self.argv[2]) is not None
            )
            image_read = (
                len(self.argv) == 4 and self.argv[:3] == ("docker", "image", "inspect")
                and (_KIL_IMAGE.fullmatch(self.argv[3]) is not None or _ENVOY_IMAGE.fullmatch(self.argv[3]) is not None)
            )
            node_image_read = (
                len(self.argv) == 12 and self.argv[:2] == ("docker", "exec")
                and _HEX64.fullmatch(self.argv[2]) is not None
                and self.argv[3:] == ("/usr/local/bin/ctr", "--address", "/run/containerd/containerd.sock",
                    "--namespace", "k8s.io", "images", "check", "--snapshotter", "overlayfs")
            )
            node_cri_image_read = (
                len(self.argv) == 15 and self.argv[:2] == ("docker", "exec")
                and _HEX64.fullmatch(self.argv[2]) is not None
                and self.argv[3:14] == (
                    "/usr/local/bin/crictl", "--runtime-endpoint", "unix:///run/containerd/containerd.sock",
                    "--image-endpoint", "unix:///run/containerd/containerd.sock", "--timeout", "10s",
                    "inspecti", "--quiet", "--output", "json")
                and (_KIL_IMAGE.fullmatch(self.argv[14]) is not None
                     or _ENVOY_IMAGE.fullmatch(self.argv[14]) is not None)
            )
            control_plane_manifest_read = (
                len(self.argv) == 6
                and self.argv[:2] == ("docker", "exec")
                and _HEX64.fullmatch(self.argv[2]) is not None
                and self.argv[3:5] == ("/bin/cat", "--")
                and self.argv[5] in {
                    "/etc/kubernetes/manifests/kube-apiserver.yaml",
                    "/etc/kubernetes/manifests/kube-controller-manager.yaml",
                }
            )
            if (control_plane_manifest_read
                    and Path(environment["DOCKER_CONFIG"]).name != "docker-config"):
                raise JournalError("control-plane manifest read requires private Docker configuration")
            if self.argv not in {
                ("docker", "inspect", f"{LAB_IDENTITY}-control-plane"),
                ("docker", "context", "show"),
                ("docker", "container", "ls", "--all", "--no-trunc", "--format", "{{json .}}"),
            } and not image_mutation and not image_read and not node_image_read and not node_cri_image_read and not control_plane_manifest_read:
                raise JournalError("Docker command is outside the closed argv grammar")
            if self.mutating is not image_mutation:
                raise JournalError("Docker command mutation classification is invalid")
            if self.stdin is not None and self.argv != ("docker", "load"):
                raise JournalError("Docker command carries unreviewed input")
            if global_context_read and self.env:
                raise JournalError("global Docker context read must not carry isolated authority")
        elif executable == "git":
            if self.argv not in {
                ("git", "rev-parse", "HEAD"),
                ("git", "rev-parse", "origin/main"),
                ("git", "status", "--porcelain"),
            } or self.mutating or self.stdin is not None or self.env:
                raise JournalError("Git command is outside the closed argv grammar")
        elif executable == "kind":
            image_load = (
                len(self.argv) == 6
                and self.argv[1:3] == ("load", "docker-image")
                and (_KIL_IMAGE.fullmatch(self.argv[3]) is not None or _ENVOY_IMAGE.fullmatch(self.argv[3]) is not None)
                and self.argv[4:] == ("--name", LAB_IDENTITY)
            )
            allowed = set()
            if len(kubeconfigs) == 1:
                kubeconfig = _absolute_path("Kind kubeconfig", kubeconfigs[0])
                config = str(Path(kubeconfig).parent / "kind-config.yaml")
                allowed = {
                    ("kind", "create", "cluster", "--name", LAB_IDENTITY, "--config", config, "--kubeconfig", kubeconfig),
                    ("kind", "delete", "cluster", "--name", LAB_IDENTITY, "--kubeconfig", kubeconfig),
                }
            if (self.argv not in allowed and not image_load) or not self.mutating:
                raise JournalError("Kind command is outside the closed argv grammar")
            if self.stdin is not None:
                raise JournalError("Kind command carries unreviewed input")
        elif executable == "kubectl":
            arguments = self.argv[3:]
            fixed_reads = {
                ("get", "all", "--namespace", "kube-system", "--output", "json"),
                ("get", "all,networkpolicies", "--all-namespaces", "--output", "json"),
                ("get", "pods", "--all-namespaces", "--output", "json"),
                ("get", "namespace", "kube-system", "--output", "json"),
                (
                    "get",
                    "namespaces,pods,services,endpoints,endpointslices,serviceaccounts,configmaps,deployments,daemonsets,networkpolicies,nodes,replicasets",
                    "--all-namespaces",
                    "--output",
                    "json",
                ),
            }
            reviewed_read = arguments in fixed_reads
            if len(arguments) == 6 and arguments[:2] == ("get", "pods,deployments,replicasets"):
                reviewed_read = (
                    arguments[2] == "--namespace"
                    and arguments[3] in _APPLICATION_NAMESPACES
                    and arguments[4:] == ("--output", "json")
                )
            if len(arguments) == 7 and arguments[:2] == ("get", "pod"):
                pod = arguments[2]
                reviewed_read = (
                    (pod == "driver" or re.fullmatch(r"(?:authz|envoy|target)-[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", pod) is not None)
                    and
                    arguments[3] == "--namespace"
                    and arguments[4] in _APPLICATION_NAMESPACES
                    and arguments[5:] == ("--output", "json")
                )
            if len(arguments) == 7 and arguments[0] == "get":
                calico_name = {
                    "daemonset": "calico-node",
                    "deployment": "calico-kube-controllers",
                }.get(arguments[1])
                reviewed_read = reviewed_read or (
                    calico_name is not None
                    and arguments[2] == calico_name
                    and arguments[3:5] == ("--namespace", "kube-system")
                    and arguments[5:] == ("--output", "json")
                )
            if len(arguments) == 8 and arguments[:2] == ("get", "endpointslices"):
                reviewed_read = (
                    arguments[2] == "--namespace"
                    and arguments[3] in _APPLICATION_NAMESPACES
                    and arguments[4] == "--selector"
                    and arguments[5] in {
                        "kubernetes.io/service-name=envoy",
                        "kubernetes.io/service-name=authz",
                        "kubernetes.io/service-name=target",
                    }
                    and arguments[6:] == ("--output", "json")
                )
            if len(arguments) == 9 and arguments[:2] == ("get", "pod"):
                uid = arguments[6][len("metadata.uid="):] if arguments[6].startswith("metadata.uid=") else ""
                reviewed_read = (
                    arguments[2] == "driver"
                    and arguments[3] == "--namespace"
                    and arguments[4] in _APPLICATION_NAMESPACES
                    and arguments[5] == "--field-selector"
                    and bool(uid)
                    and arguments[7] == "--output"
                )
                # The final output value is intentionally checked separately so
                # no authority-like option can occupy it.
                reviewed_read = reviewed_read and arguments[8] == "name"
                if reviewed_read:
                    _exact_string("kubectl Pod UID selector", uid)
            if len(arguments) == 5 and arguments[0] == "logs":
                resource = arguments[1]
                pod_log = (
                    resource.startswith("pod/")
                    and (
                        resource == "pod/driver"
                        or re.fullmatch(r"pod/(?:authz|envoy|target)-[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", resource) is not None
                    )
                )
                reviewed_read = (
                    (pod_log or resource in {"deployment/authz", "deployment/envoy", "deployment/target"})
                    and arguments[2] == "--namespace"
                    and arguments[3] in _APPLICATION_NAMESPACES
                    and arguments[4:] == ("--limit-bytes=1048576",)
                )
            ledger_read = (
                len(arguments) == 11 and arguments[0] == "exec"
                and re.fullmatch(r"pod/(?:authz|target)-[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", arguments[1]) is not None
                and arguments[2] == "--namespace" and arguments[3] in _APPLICATION_NAMESPACES
                and arguments[4] == "--container" and arguments[5] in {"authz", "target"}
                and arguments[1].startswith("pod/" + arguments[5] + "-")
                and arguments[6:10] == ("--", "head", "-c", "1048577")
                and arguments[10] == {"authz": "/evidence/decisions.jsonl", "target": "/evidence/targets.jsonl"}[arguments[5]]
            )
            envoy_control = (
                len(arguments) == 10 and arguments[0] == "exec"
                and re.fullmatch(r"pod/envoy-[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", arguments[1]) is not None
                and arguments[2] == "--namespace" and arguments[3] in _APPLICATION_NAMESPACES
                and arguments[4:9] == ("--container", "envoy", "--", "/bin/bash", "-pceu")
                and arguments[9] in {_ENVOY_DRAIN_SCRIPT, _ENVOY_STATS_SCRIPT}
            )
            envoy_drain = envoy_control and arguments[9] == _ENVOY_DRAIN_SCRIPT
            apply_stdin = arguments == ("apply", "-f", "-")
            object_read_stdin = arguments == ("get", "--filename", "-", "--output", "json")
            reviewed_read = reviewed_read or object_read_stdin
            if apply_stdin or object_read_stdin:
                if self.stdin is None:
                    raise JournalError("kubectl apply requires exact manifest stdin")
                try:
                    manifest = json.loads(self.stdin)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise JournalError("kubectl apply manifest is invalid") from error
                if (
                    type(manifest) is not dict
                    or set(manifest) != {"apiVersion", "items", "kind"}
                    or manifest.get("apiVersion") != "v1"
                    or manifest.get("kind") != "List"
                    or type(manifest.get("items")) is not list
                    or self.stdin != _canonical_bytes(manifest)
                ):
                    raise JournalError("kubectl apply manifest is not a canonical List")
            apply_calico = (
                len(arguments) == 3
                and arguments[0:2] == ("apply", "-f")
                and Path(arguments[2]).name == "calico-v3.32.0.yaml"
            )
            if apply_calico:
                _absolute_path("Calico manifest", arguments[2])
                if self.stdin is not None:
                    raise JournalError("kubectl Calico apply carries unreviewed stdin")
            attach = (
                len(arguments) == 5
                and arguments[0:2] == ("attach", "pod/driver")
                and arguments[2] == "--namespace"
                and arguments[3] in _APPLICATION_NAMESPACES
                and arguments[4:] == ("--stdin",)
            )
            wait_ready = (
                len(arguments) == 6
                and arguments[0] == "wait"
                and arguments[1] == "--for=condition=Available"
                and arguments[2] in {"deployment/envoy", "deployment/authz", "deployment/target"}
                and arguments[3] == "--namespace"
                and arguments[4] in _APPLICATION_NAMESPACES
                and arguments[5] == "--timeout=1s"
            )
            if attach:
                if self.stdin is None:
                    raise JournalError("kubectl attach requires one canonical instruction")
                if self.stdin != b"":
                    from kil.v3b1_driver_protocol import DriverProtocolError, parse_instruction
                    expected_track = next(
                        track for track, namespace in TRACK_NAMESPACES if namespace == arguments[3]
                    )
                    try:
                        parse_instruction(self.stdin, expected_track=expected_track)
                    except DriverProtocolError as error:
                        raise JournalError("kubectl attach instruction is invalid") from error
            raw_delete = (
                len(arguments) == 5
                and arguments[0:2] == ("delete", "--raw")
                and arguments[3:] == ("-f", "-")
            )
            if raw_delete:
                uri = arguments[2]
                prefix = "/api/v1/namespaces/"
                pieces = uri[len(prefix):].split("/") if uri.startswith(prefix) else []
                if len(pieces) != 3 or pieces[0] not in _APPLICATION_NAMESPACES or pieces[1:] != ["pods", "driver"]:
                    raise JournalError("kubectl raw delete URI is outside the closed grammar")
                if self.stdin is None:
                    raise JournalError("kubectl raw delete requires DeleteOptions stdin")
                try:
                    options = json.loads(self.stdin)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise JournalError("kubectl raw delete has invalid DeleteOptions") from error
                if type(options) is not dict or set(options) != {"apiVersion", "kind", "preconditions"}:
                    raise JournalError("kubectl raw delete DeleteOptions fields are not closed")
                preconditions = options.get("preconditions")
                if (
                    options.get("apiVersion") != "v1"
                    or options.get("kind") != "DeleteOptions"
                    or type(preconditions) is not dict
                    or set(preconditions) != {"uid"}
                ):
                    raise JournalError("kubectl raw delete DeleteOptions are not exact")
                _exact_string("kubectl raw delete UID", preconditions["uid"])
                if self.stdin != _canonical_bytes(options):
                    raise JournalError("kubectl raw delete DeleteOptions are not canonical")
            elif apply_stdin or apply_calico or attach or envoy_drain:
                if not self.mutating:
                    raise JournalError("kubectl mutation classification does not match its grammar")
                if attach is False and apply_stdin is False and self.stdin is not None:
                    raise JournalError("kubectl mutation carries unreviewed stdin")
            elif not (reviewed_read or wait_ready or ledger_read or envoy_control) or self.mutating or (self.stdin is not None and not object_read_stdin):
                raise JournalError("kubectl command is outside the closed argv grammar")
            if not (apply_stdin or apply_calico or attach or envoy_drain) and raw_delete is not self.mutating:
                raise JournalError("kubectl mutation classification does not match its grammar")
            if self.env:
                raise JournalError("kubectl command carries an unreviewed environment")


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
    next_intent: tuple[str, tuple[tuple[str, object], ...]] | None = None

    def __post_init__(self) -> None:
        if type(self.commands) is not tuple or any(type(item) is not Command for item in self.commands):
            raise JournalError("recovery commands must contain exact Command records")
        if type(self.requests_to_send) is not tuple or any(
            type(item) is not Command for item in self.requests_to_send
        ):
            raise JournalError("recovery request commands must contain exact Command records")
        if type(self.publication_allowed) is not bool:
            raise JournalError("publication_allowed must be an exact boolean")
        if self.next_intent is not None:
            if (
                type(self.next_intent) is not tuple
                or len(self.next_intent) != 2
                or type(self.next_intent[0]) is not str
                or type(self.next_intent[1]) is not tuple
            ):
                raise JournalError("recovery next intent must be an exact immutable record")
            pairs = self.next_intent[1]
            if any(type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str for pair in pairs):
                raise JournalError("recovery next intent details are invalid")
            if len({pair[0] for pair in pairs}) != len(pairs):
                raise JournalError("recovery next intent details are duplicated")
            family, stage, _key = _validate_event_details(self.next_intent[0], dict(pairs))
            if stage != "intent" or not family:
                raise JournalError("recovery next event must be a reviewed intent")


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
    lifecycle_mode: str = "nominal"
    expected_inputs_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not str or self.schema_version != JOURNAL_SCHEMA:
            raise JournalError("journal schema version is not V3B-2")
        _exact_digest("run ID", self.run_id)
        _exact_digest("execution nonce", self.execution_nonce)
        _exact_digest("source commit", self.source_commit, _HEX40)
        _exact_digest("profile SHA-256", self.profile_sha256)
        if self.expected_inputs_sha256 is not None:
            _exact_digest("expected inputs SHA-256", self.expected_inputs_sha256)
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
        if type(self.expected_objects) is not tuple:
            raise JournalError("expected objects must be an exact tuple of strings")
        for item in self.expected_objects:
            _exact_string("expected object", item, maximum=4096)
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
        if type(self.lifecycle_mode) is not str or self.lifecycle_mode not in {"nominal", "request-free"}:
            raise JournalError("journal lifecycle mode is not reviewed")


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
        "lifecycle_mode": inputs.lifecycle_mode,
        "teardown_from_sequence": None,
        "profile_start_refused_sequence": None,
        "expected_inputs_sha256": inputs.expected_inputs_sha256,
        "owned_identity": _identity_mapping(inputs.owned_identity),
        "events": [],
    }


def _canonical_bytes(value: object) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    except (UnicodeError, TypeError, ValueError, RecursionError) as error:
        raise JournalError("canonical journal value is not closed UTF-8 JSON") from error


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
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise JournalError("journal string contains invalid Unicode") from error
        if len(encoded) > _MAX_STRING_BYTES:
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


def _require_canonical_directory_ancestry(directory: Path) -> Path:
    try:
        resolved = directory.resolve(strict=True)
    except OSError as error:
        raise JournalError(f"journal directory ancestry is unavailable: {error}") from error
    if directory != resolved or str(directory) != str(resolved):
        raise JournalError("journal directory ancestry must be a canonical path without symlinks")
    current = Path(directory.anchor)
    for component in directory.parts[1:]:
        current /= component
        try:
            inspected = os.stat(current, follow_symlinks=False)
        except OSError as error:
            raise JournalError(f"journal directory ancestor is unavailable: {error}") from error
        if stat.S_ISLNK(inspected.st_mode):
            raise JournalError("journal directory ancestry must not contain symlinks")
        if not stat.S_ISDIR(inspected.st_mode):
            raise JournalError("journal directory ancestry must contain only directories")
    return resolved


def _private_location(path: Path, *, create_parent: bool) -> tuple[Path, Path]:
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise JournalError("journal path must be an absolute normalized path")
    private = path.parent
    if path.name in {"", ".", ".."} or private == path or path.parent.parent == path.parent:
        raise JournalError("journal must be a direct child of a private root")
    if create_parent and not private.exists():
        _require_canonical_directory_ancestry(private.parent)
        try:
            private.mkdir(mode=0o700)
        except OSError as error:
            raise JournalError(f"cannot create private journal root: {error}") from error
    resolved_private = _require_canonical_directory_ancestry(private)
    try:
        inspected = os.stat(private, follow_symlinks=False)
    except OSError as error:
        raise JournalError(f"private journal root is unavailable: {error}") from error
    if not stat.S_ISDIR(inspected.st_mode) or stat.S_ISLNK(inspected.st_mode):
        raise JournalError("private journal root must be a non-symlink directory")
    if stat.S_IMODE(inspected.st_mode) != 0o700:
        raise JournalError("private journal root must have mode 0700")
    if inspected.st_uid != os.geteuid():
        raise JournalError("private journal root must be owned by the current user")
    if private != resolved_private or path != resolved_private / path.name:
        raise JournalError("journal path must be canonical and contained by its private root")
    _require_canonical_directory_ancestry(private)
    return path, resolved_private


def _fsync_parent(parent: Path) -> None:
    descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _journal_append_lock(path: Path):
    """Serialize the full append transaction on a stable private lock inode."""
    journal, private = _private_location(path, create_parent=False)
    lock = private / f".{journal.name}.lock"
    flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    created = False
    locked = False
    try:
        try:
            descriptor = os.open(lock, flags | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
            _fsync_parent(private)
        except FileExistsError:
            descriptor = os.open(lock, flags)
        current = os.fstat(descriptor)
        named = os.stat(lock, follow_symlinks=False)
        if (
            not stat.S_ISREG(current.st_mode)
            or stat.S_ISLNK(named.st_mode)
            or (current.st_dev, current.st_ino) != (named.st_dev, named.st_ino)
            or current.st_nlink != 1
            or stat.S_IMODE(current.st_mode) != 0o600
            or current.st_uid != os.geteuid()
        ):
            raise JournalError("journal lock must be an owned 0600 single-link regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        after = os.stat(lock, follow_symlinks=False)
        if stat.S_ISLNK(after.st_mode) or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino):
            raise JournalError("journal lock identity changed during acquisition")
        yield
    except JournalError:
        raise
    except OSError as error:
        operation = "create" if created else "acquire"
        raise JournalError(f"cannot {operation} journal lock safely: {error}") from error
    finally:
        release_error: OSError | None = None
        if descriptor is not None:
            if locked:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                except OSError as error:
                    release_error = error
            try:
                os.close(descriptor)
            except OSError as error:
                release_error = release_error or error
        if release_error is not None:
            raise JournalError(f"cannot release journal lock safely: {release_error}") from release_error


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
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
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
            lifecycle_mode=value["lifecycle_mode"],  # type: ignore[arg-type]
            expected_inputs_sha256=value["expected_inputs_sha256"],
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
    "control_plane_manifest_source": frozenset({"kind_cluster"}),
    "image_import": frozenset({"archive_sha256", "image", "envoy_image"}),
    "image_load": frozenset({"image", "envoy_image"}),
    "calico_apply": frozenset({"manifest_sha256"}),
    "application_apply": frozenset({"manifest_sha256"}),
    "readiness": frozenset({"attestation_sha256"}),
    "envoy_quiesce": frozenset({"attestation_sha256"}),
    "driver_start": frozenset({"namespace", "pod", "uid"}),
    "driver_cancel": frozenset({"namespace", "pod", "uid"}),
    "evidence_freeze": frozenset({"evidence_sha256"}),
    "cluster_absence_proof": frozenset({"kind_cluster", "node_container_id"}),
    "profile_absence_proof": frozenset({"colima_profile"}),
    "foreign_snapshot_comparison": frozenset({"unchanged", "attestation_sha256"}),
    "publication": frozenset({
        "destination", "public_commitment_sha256", "tree_commitment_sha256",
    }),
}
_REQUEST_INTENT_FIELDS = frozenset({"track", "request_id", "case_sha256"})
_REQUEST_RESULT_FIELDS = frozenset({"track", "request_id", "case_sha256", "result_sha256"})
_CLUSTER_COMPLETE_FIELDS = frozenset(
    {"kind_cluster", "kubeconfig", "cluster_incarnation_uid", "node_container_id", "docker_host"}
)
_FAILURE_FIELDS = frozenset({"failure_category", "proof_sha256"})
_ABANDONMENT_FIELDS = frozenset({
    "abandoned_family", "stage_category", "observation_sha256",
    "promotion_forbidden",
})
_FAILURE_FAMILIES = frozenset({
    "profile_start", "profile_stop", "profile_delete", "cluster_create",
    "cluster_delete", "control_plane_manifest_source", "image_import", "image_load",
    "calico_apply", "application_apply",
    "envoy_quiesce", "driver_start", "driver_cancel",
})


def _event_family(name: str) -> tuple[str, str]:
    if name == "request_intent":
        return "request", "intent"
    if name == "request_result":
        return "request", "complete"
    for suffix, stage in (
        ("_abandoned_for_teardown", "abandoned"),
        ("_intent", "intent"), ("_complete", "complete"),
        ("_failed", "failed"),
    ):
        if name.endswith(suffix):
            family = name[: -len(suffix)]
            if family in _PAIR_DETAILS:
                return family, stage
    raise JournalError(f"unknown journal event: {name}")


def _validate_event_details(name: str, details: object) -> tuple[str, str, tuple[object, ...]]:
    family, stage = _event_family(name)
    if family != "request" and stage != "intent" and type(details) is dict and "observed_proof_sha256" in details:
        _exact_digest("observed proof SHA-256", details["observed_proof_sha256"])
        details = {key: value for key, value in details.items() if key != "observed_proof_sha256"}
        if family == 'profile_start' and stage in {'complete', 'abandoned'} and 'profile_binding' in details:
            from kil.v3b2_profile_state import validate_binding
            validate_binding(details['profile_binding'])
            details = {key: value for key, value in details.items() if key != 'profile_binding'}
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
    if stage == "failed":
        expected |= _FAILURE_FIELDS
    elif stage == "abandoned":
        expected |= _ABANDONMENT_FIELDS
    if stage == "failed" and family not in _FAILURE_FAMILIES:
        raise JournalError("failure transition is not permitted for this family")
    if family == "cluster_create" and stage == "complete":
        value = _closed_details(details, _CLUSTER_COMPLETE_FIELDS, name)
        _exact_string("cluster incarnation UID", value["cluster_incarnation_uid"])
        _exact_digest("node container ID", value["node_container_id"])
        endpoint = _exact_string("Docker endpoint", value["docker_host"])
        if not endpoint.startswith("unix:///"):
            raise JournalError("Docker endpoint must be an explicit Unix socket")
    else:
        value = _closed_details(details, expected, name)
    if stage == "failed":
        if value["failure_category"] not in {
            "execution_not_started", "not_applied",
        }:
            raise JournalError("failure category is not reviewed")
        _exact_digest("failure proof SHA-256", value["proof_sha256"])
    if stage == "abandoned":
        if family in {"request", "publication"}:
            raise JournalError("family cannot be abandoned for teardown")
        if (
            value["abandoned_family"] != family
            or value["stage_category"] != "uncertain_or_partial"
            or value["promotion_forbidden"] is not True
        ):
            raise JournalError("abandonment identity/category is invalid")
        _exact_digest("abandonment observation SHA-256", value["observation_sha256"])
    if "colima_profile" in value and (type(value["colima_profile"]) is not str or value["colima_profile"] != LAB_IDENTITY):
        raise JournalError("event may name only the owned Colima profile")
    if "kind_cluster" in value and (type(value["kind_cluster"]) is not str or value["kind_cluster"] != LAB_IDENTITY):
        raise JournalError("event may name only the owned Kind cluster")
    if "kubeconfig" in value:
        _absolute_path("event kubeconfig", value["kubeconfig"])
    for key in (
        "manifest_sha256", "attestation_sha256", "evidence_sha256",
        "public_commitment_sha256", "tree_commitment_sha256",
    ):
        if key in value:
            _exact_digest(key, value[key])
    if "node_container_id" in value:
        _exact_digest("node container ID", value["node_container_id"])
    if family in {"image_import", "image_load"} and (
        type(value["image"]) is not str or _KIL_IMAGE.fullmatch(value["image"]) is None
        or type(value["envoy_image"]) is not str or _ENVOY_IMAGE.fullmatch(value["envoy_image"]) is None
    ):
        raise JournalError("image load content reference is not exact")
    if family == "image_import":
        _exact_digest("image archive SHA-256", value["archive_sha256"])
    if family == "publication":
        _absolute_path("publication destination", value["destination"])
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


def _validate_history(events: object, lifecycle_mode: str, teardown_from_sequence: int | None = None) -> None:
    if type(events) is not list or len(events) > 10_000:
        raise JournalError("journal events must be a bounded exact list")
    states: dict[tuple[str, tuple[object, ...]], tuple[str, dict[str, object]]] = {}
    active: tuple[str, tuple[object, ...]] | None = None
    completed: set[tuple[str, tuple[object, ...]]] = set()
    driver_starts: dict[str, tuple[str, str, str]] = {}
    driver_cancels: set[str] = set()
    request_claims: list[str] = []
    request_results: set[str] = set()
    foreign_comparison_unchanged: bool | None = None
    failed_families: set[str] = set()
    abandoned_families: set[str] = set()
    track_namespace = dict(TRACK_NAMESPACES)
    forward_families = {
        "control_plane_manifest_source", "image_import", "image_load",
        "calico_apply", "application_apply", "readiness", "driver_start",
        "request",
    }

    def done(family: str) -> bool:
        return (family, ()) in completed

    def begun(family: str) -> bool:
        return (family, ()) in states

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
        request_pending = bool(request_claims and request_claims[-1] not in request_results)
        request_abandoned = request_pending and done("evidence_freeze")
        if stage == "intent":
            if prior is not None:
                message = "request already claimed" if family == "request" else f"{family} intent is duplicated or already pending"
                raise JournalError(message)
            if active is not None:
                raise JournalError("journal lifecycle has overlapping pending intents")
            teardown_only = bool(failed_families or abandoned_families) or (teardown_from_sequence is not None and sequence >= teardown_from_sequence)
            if teardown_only and family not in {
                "driver_cancel", "envoy_quiesce", "evidence_freeze",
                "cluster_delete", "cluster_absence_proof", "profile_stop",
                "profile_delete", "profile_absence_proof",
                "foreign_snapshot_comparison",
            }:
                raise JournalError("failed lifecycle permits only safe teardown")
            if request_pending and not request_abandoned and family not in {"envoy_quiesce", "evidence_freeze"}:
                raise JournalError("request intent is terminal-pending until its result or evidence freeze")
            if request_abandoned and family not in {
                "driver_cancel",
                "cluster_delete",
                "cluster_absence_proof",
                "profile_stop",
                "profile_delete",
                "profile_absence_proof",
                "foreign_snapshot_comparison",
                "publication",
            }:
                raise JournalError("abandoned request permits only ordered teardown and publication")
            if family in forward_families:
                require(
                    not begun("cluster_delete")
                    and not begun("cluster_absence_proof"),
                    "forward phase cannot begin after cluster deletion or absence",
                )
            if family == "profile_start":
                require(sequence == 1, "profile start must be first")
            elif family == "cluster_create":
                require(done("profile_start"), "cluster create requires profile start completion")
            elif family == "control_plane_manifest_source":
                require(done("cluster_create"),
                        "control-plane manifest source requires cluster create completion")
            elif family == "calico_apply":
                require(done("cluster_create") and done("image_load"), "Calico apply requires cluster and image load completion")
            elif family == "image_import":
                require(done("cluster_create") and done("control_plane_manifest_source"),
                        "image import requires control-plane manifest source completion")
            elif family == "image_load":
                require(done("cluster_create") and done("image_import"), "image load requires cluster and import completion")
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
                if driver_starts and lifecycle_mode == "nominal":
                    prior_track = TRACKS[len(driver_starts) - 1]
                    require(prior_track in request_results, "next-track driver requires prior request result")
            elif family == "request":
                details = record["details"]
                assert isinstance(details, dict)
                track = str(details["track"])
                require(lifecycle_mode == "nominal", "request-free mode prohibits request events")
                require(done("readiness") and not done("evidence_freeze"), "request requires readiness before freeze")
                require(track == TRACKS[len(request_claims)], "requests are out of fixed track order")
                require(track_namespace[track] in driver_starts, "request lacks a completed bound driver")
                if request_claims:
                    require(request_claims[-1] in request_results, "prior request is still pending")
            elif family == "evidence_freeze":
                require(done("readiness"), "evidence freeze requires completed readiness")
                if lifecycle_mode == "request-free" and driver_starts:
                    require(set(driver_starts) == driver_cancels, "request-free freeze requires all waiting drivers canceled")
                    require(
                        done("envoy_quiesce") or "envoy_quiesce" in abandoned_families,
                        "request-free freeze requires Envoy quiescence or diagnostic abandonment",
                    )
            elif family == "envoy_quiesce":
                require(done("readiness") and not done("evidence_freeze"), "Envoy quiescence requires readiness before freeze")
                if lifecycle_mode == "request-free":
                    require(teardown_only or len(driver_starts) == len(TRACKS), "request-free quiescence requires all waiting drivers")
                    require(set(driver_starts) == driver_cancels, "request-free quiescence requires waiting-driver cancellation")
            elif family == "driver_cancel":
                require(
                    done("evidence_freeze") or lifecycle_mode == "request-free",
                    "driver cancellation requires durable evidence freeze",
                )
                details = record["details"]
                assert isinstance(details, dict)
                namespace = str(details["namespace"])
                if namespace not in driver_starts and teardown_only and done("readiness"):
                    # The observed-proof writer must bind the exact existing Pod
                    # against the durable readiness inventory before completion.
                    driver_starts[namespace] = (namespace, str(details["pod"]), str(details["uid"]))
                require(namespace in driver_starts, "driver cancellation lacks a started driver")
                require(driver_starts[namespace] == (namespace, str(details["pod"]), str(details["uid"])), "driver cancellation UID does not match start")
                require(namespace not in driver_cancels, "driver cancellation is duplicated")
                remaining = [
                    candidate
                    for _track, candidate in TRACK_NAMESPACES
                    if candidate in driver_starts and candidate not in driver_cancels
                ]
                require(bool(remaining) and namespace == remaining[0], "driver cancellations are out of fixed order")
            elif family == "cluster_delete":
                require(done("cluster_create") or "cluster_create" in abandoned_families, "cluster deletion requires proved creation ownership")
                require(set(driver_starts) == driver_cancels, "cluster deletion requires all drivers canceled")
                require(
                    not done("readiness") or done("evidence_freeze") or bool(abandoned_families),
                    "post-readiness deletion requires evidence freeze or diagnostic abandonment",
                )
            elif family == "cluster_absence_proof":
                require(done("cluster_delete"), "cluster absence requires delete completion")
            elif family == "profile_stop":
                require(done("profile_start") or "profile_start" in abandoned_families, "profile stop requires proved start ownership")
                require(not (done("cluster_create") or "cluster_create" in abandoned_families) or done("cluster_absence_proof"), "profile stop requires cluster absence")
            elif family == "profile_delete":
                require(done("profile_stop"), "profile delete requires stop completion")
            elif family == "profile_absence_proof":
                require(done("profile_delete") or "profile_start" in failed_families, "profile absence requires delete completion or proven start absence")
            elif family == "foreign_snapshot_comparison":
                require(done("profile_absence_proof"), "foreign comparison requires owned absence")
            elif family == "publication":
                require(not teardown_only, "failed lifecycle cannot publish nominal evidence")
                require(done("foreign_snapshot_comparison"), "publication requires foreign comparison")
                require(foreign_comparison_unchanged is True, "promotable publication requires unchanged foreign resources")
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
        if family == "request" and teardown_from_sequence is not None and sequence >= teardown_from_sequence:
            raise JournalError("teardown-only lifecycle cannot promote a late request result")
        if family == "request" and (
            active is not None or any(candidate[0] == "evidence_freeze" for candidate in states)
        ):
            raise JournalError(
                "request completion lifecycle order/overlap violation: terminal after recovery begins"
            )
        intent = prior[1]
        completion = record["details"]
        assert isinstance(completion, dict)
        for name, expected in intent.items():
            if (family == 'foreign_snapshot_comparison' and stage == 'complete'
                    and 'observed_proof_sha256' in completion and name in {'unchanged', 'attestation_sha256'}):
                # These are observed results, not mutation parameters. The
                # writer and offline replay derive both from the same raw
                # inventory/context proof; a pending recovery may observe drift.
                continue
            if completion.get(name) != expected:
                raise JournalError(f"{family} completion details do not match intent")
        states[state_key] = (stage, completion)
        if stage == "complete":
            completed.add(state_key)
        elif stage == "failed":
            failed_families.add(family)
        else:
            require(family in {"profile_start", "cluster_create"} or done("cluster_create") or "cluster_create" in abandoned_families,
                    "abandonment requires exact established ownership")
            abandoned_families.add(family)
        if family == "request":
            request_results.add(str(completion["track"]))
        else:
            if active != state_key:
                raise JournalError(f"{family} completion is out of lifecycle order")
            active = None
        if (
            family == "driver_cancel"
            and stage == "abandoned"
        ):
            driver_cancels.add(str(completion["namespace"]))
        if stage in {"failed", "abandoned"}:
            continue
        if family == "driver_start":
            driver_starts[str(completion["namespace"])] = (
                str(completion["namespace"]), str(completion["pod"]), str(completion["uid"])
            )
        elif family == "driver_cancel":
            driver_cancels.add(str(completion["namespace"]))
        elif family == "foreign_snapshot_comparison":
            foreign_comparison_unchanged = completion["unchanged"]


def _validate_journal(value: object) -> None:
    if type(value) is not dict or set(value) != JOURNAL_FIELDS:
        raise JournalError("journal fields are not closed")
    inputs = _inputs_from_journal(value)
    if type(value["phase"]) is not str or not value["phase"]:
        raise JournalError("journal phase is invalid")
    events = value["events"]
    latch = value["teardown_from_sequence"]
    if latch is not None and (type(latch) is not int or latch < 1 or latch > len(events) + 1):
        raise JournalError("teardown latch sequence is invalid")
    _validate_history(events, inputs.lifecycle_mode, latch)
    assert isinstance(events, list)
    refused = value["profile_start_refused_sequence"]
    if refused is not None and (
            type(refused) is not int or refused != 1 or len(events) != 1
            or events[0]["sequence"] != refused or events[0]["event"] != "profile_start_intent"
            or latch is None):
        raise JournalError("profile start refusal must retain its exact pending intent and teardown latch")
    expected_phase = "prepared" if not events else events[-1]["event"]
    if value["phase"] != expected_phase:
        raise JournalError("journal phase does not match its event history")
    inputs.owned_identity.__post_init__()


def _replace_journal(path: Path, value: dict[str, object]) -> None:
    journal, private = _private_location(path, create_parent=False)
    prior = load_journal(path)
    if value["expected_inputs_sha256"] != prior["expected_inputs_sha256"]:
        raise JournalError("immutable expected inputs commitment cannot change")
    if prior["teardown_from_sequence"] is not None and value["teardown_from_sequence"] != prior["teardown_from_sequence"]:
        raise JournalError("permanent teardown latch cannot be cleared or moved")
    if (prior["profile_start_refused_sequence"] is not None
            and value["profile_start_refused_sequence"] != prior["profile_start_refused_sequence"]):
        raise JournalError("permanent profile start refusal cannot be cleared or moved")
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
    with _journal_append_lock(path):
        value = load_journal(path)
        family, stage = _event_family(event)
        if value["expected_inputs_sha256"] is not None and family != "request" and stage != "intent":
            raise JournalError("non-request terminal requires the observed proof writer")
        events = value["events"]
        assert isinstance(events, list)
        record = {"sequence": len(events) + 1, "event": event, "details": dict(details)}
        candidate = {**value, "phase": event, "events": [*events, record]}
        _validate_json_budget(candidate)
        _validate_journal(candidate)
        _replace_journal(path, candidate)
        return candidate


def latch_teardown(path: Path) -> dict[str, object]:
    """Permanently forbid forward work from the next journal sequence."""
    with _journal_append_lock(path):
        value = load_journal(path)
        if value["teardown_from_sequence"] is not None:
            return value
        candidate = {**value, "teardown_from_sequence": len(value["events"]) + 1}
        _validate_journal(candidate)
        _replace_journal(path, candidate)
        return candidate


def latch_profile_start_refusal(path: Path) -> dict[str, object]:
    """Retain a controller dispatch refusal, never a claim about runtime state."""
    with _journal_append_lock(path):
        value = load_journal(path)
        if value["profile_start_refused_sequence"] is not None:
            return value
        events = value["events"]
        if len(events) != 1 or events[0]["event"] != "profile_start_intent":
            raise JournalError("profile start refusal requires the exact pending start intent")
        candidate = {**value, "profile_start_refused_sequence": events[0]["sequence"],
                     "teardown_from_sequence": value["teardown_from_sequence"] or len(events) + 1}
        _validate_journal(candidate)
        _replace_journal(path, candidate)
        return candidate


def _publish_observed_proof(private: Path, name: str, payload: bytes) -> None:
    """Publish only complete fsynced proof bytes, atomically and without replace.

    A process crash during writing can leave only an unrelated hidden staging
    name. A crash after rename can reuse the exact final bytes. No hardlinks are
    used, so every published proof retains the single-link invariant.
    """
    from kil.v3b2_evidence import _rename_directory_exclusive
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent = os.open(private, flags)
    descriptor = None
    temporary = None
    staged_identity = None

    def verify_existing():
        existing = os.open(name, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
        try:
            before = os.fstat(existing)
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISREG(before.st_mode) or before.st_size != len(payload)
                    or before.st_nlink != 1 or before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) != 0o600
                    or (named.st_dev, named.st_ino) != (before.st_dev, before.st_ino)):
                raise JournalError("durable proof is not an exact owned private file")
            offset = 0
            while offset < len(payload):
                chunk = os.read(existing, min(65536, len(payload) - offset))
                if not chunk or chunk != payload[offset:offset + len(chunk)]:
                    raise JournalError("durable proof differs from its commitment")
                offset += len(chunk)
            after = os.fstat(existing)
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            keys = ("st_dev", "st_ino", "st_size", "st_mode", "st_nlink", "st_uid", "st_mtime_ns", "st_ctime_ns")
            if os.read(existing, 1) or any(getattr(before, key) != getattr(after, key)
                    or getattr(before, key) != getattr(current, key) for key in keys):
                raise JournalError("durable proof identity changed during verification")
            os.fsync(existing)
        finally:
            os.close(existing)

    try:
        anchor = os.fstat(parent)
        named_parent = os.stat(private, follow_symlinks=False)
        if (not stat.S_ISDIR(anchor.st_mode) or stat.S_IMODE(anchor.st_mode) != 0o700
                or anchor.st_uid != os.geteuid()
                or (anchor.st_dev, anchor.st_ino) != (named_parent.st_dev, named_parent.st_ino)):
            raise JournalError("private proof directory identity changed")
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            temporary = "." + name + "." + secrets.token_hex(16) + ".tmp"
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=parent)
            os.fchmod(descriptor, 0o600)
            staged = os.fstat(descriptor)
            staged_identity = (staged.st_dev, staged.st_ino)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                if stream.write(payload) != len(payload):
                    raise JournalError("proof staging write was incomplete")
                stream.flush()
                os.fsync(descriptor)
            current = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1 or current.st_uid != os.geteuid()
                    or stat.S_IMODE(current.st_mode) != 0o600 or current.st_size != len(payload)
                    or (current.st_dev, current.st_ino) != staged_identity):
                raise JournalError("proof staging identity changed")
            try:
                # The existing helper's renameatx_np(RENAME_EXCL) / renameat2
                # (RENAME_NOREPLACE) primitive supports regular files too.
                _rename_directory_exclusive(parent, temporary, parent, name)
            except FileExistsError:
                # A raced destination is never replaced, including symlinks
                # and corrupt evidence; it must pass the same strict verifier.
                pass
            else:
                temporary = None
        verify_existing()
        os.fsync(parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None and staged_identity is not None:
            try:
                current = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if (current.st_dev, current.st_ino) == staged_identity:
                    os.unlink(temporary, dir_fd=parent)
        os.close(parent)


def append_observed_terminal(path: Path, context, observations):
    """The shared normal/recovery terminal boundary; persist raw proof first."""
    from kil.v3b2_proofs import ExpectedContext, decide, decode, decode_proof_bundle, observation_bundle, terminal_event
    if type(context) is not ExpectedContext:
        raise JournalError("terminal writer requires an immutable expected context")
    with _journal_append_lock(path):
        value = load_journal(path)
        events = value["events"]
        if (not events or value["run_id"] != context.run_id
                or events[-1]["sequence"] != context.intent_sequence
                or events[-1]["event"] != context.family + "_intent"
                or events[-1]["details"] != decode(context.intent)):
            raise JournalError("proof does not bind the exact pending intent")
        if value["expected_inputs_sha256"] is not None:
            independently_derived = load_expected_context(path, value)
            if context != independently_derived:
                raise JournalError("observed context differs from immutable expected inputs")
        decision = decide(context, observations)
        payload = observation_bundle(context, observations, decision)
        # Never commit a terminal whose serialized envelope cannot pass the
        # exact replay decoder's budget and JSON checks.
        decode_proof_bundle(payload)
        digest = hashlib.sha256(payload).hexdigest()
        _journal, private = _private_location(path, create_parent=False)
        proof = private / f"proof-{context.intent_sequence}-{digest}.json"
        _publish_observed_proof(private, proof.name, payload)
        if decision.outcome == "unknown":
            return decision
        record = terminal_event(context, decision, digest)
        candidate = {**value, "phase": record["event"], "events": [*events, record]}
        if decision.outcome != "complete" and candidate["teardown_from_sequence"] is None:
            candidate["teardown_from_sequence"] = len(candidate["events"]) + 1
        _validate_json_budget(candidate)
        _validate_journal(candidate)
        _replace_journal(path, candidate)
        return decision


def load_expected_context(path: Path, value=None, *, state_only=False):
    """One disk-backed, hash-verifying expected context loader for all callers."""
    from kil.v3b2_proofs import expected_context, MAX_OBSERVATION_BYTES, MAX_PROOF_BUNDLE_BYTES
    value = load_journal(path) if value is None else value
    private = path.parent
    def read_regular(target, maximum):
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_size > maximum or before.st_nlink != 1
                    or before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o600):
                raise JournalError("expected inputs/proof is not an owned bounded private file")
            chunks, length = [], 0
            while length <= maximum:
                chunk = os.read(descriptor, min(65536, maximum + 1 - length))
                if not chunk:
                    break
                chunks.append(chunk)
                length += len(chunk)
            after = os.fstat(descriptor)
            if length != before.st_size or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise JournalError("expected inputs/proof changed while reading")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    if state_only:
        events = value["events"]
        # A synthetic read-only query is never persisted or accepted by the
        # terminal writer; it exposes only preceding, revalidated proof bindings.
        if not events or not events[-1]["event"].endswith("_intent") or events[-1]["event"] == "request_intent":
            value = {**value, "events": [*events, {"sequence": len(events) + 1, "event": "state_intent", "details": {}}]}
    return expected_context(read_regular(private / "expected-inputs.json", MAX_OBSERVATION_BYTES), value,
                            lambda sequence, digest: read_regular(private / f"proof-{sequence}-{digest}.json", MAX_PROOF_BUNDLE_BYTES))


def select_lifecycle_mode(path: Path, lifecycle_mode: str) -> dict[str, object]:
    """Atomically bind an event-free prepared journal to the requested mode."""
    if type(lifecycle_mode) is not str or lifecycle_mode not in {"nominal", "request-free"}:
        raise JournalError("journal lifecycle mode is not reviewed")
    with _journal_append_lock(path):
        value = load_journal(path)
        events = value["events"]
        if type(events) is not list or events:
            if value["lifecycle_mode"] != lifecycle_mode:
                raise JournalError("lifecycle mode cannot change after events")
            return value
        candidate = {**value, "lifecycle_mode": lifecycle_mode}
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
    if operation == "start":
        return colima_start_command()
    suffix = ("--force", "--data") if operation == "delete" else ()
    return Command(("colima", operation, "--profile", LAB_IDENTITY, *suffix), 300, mutating=True)


def colima_start_command() -> Command:
    return Command(COLIMA_START_ARGV, 900, mutating=True)


def docker_context_command() -> Command:
    return Command(("docker", "context", "show"), 60)


def kind_delete_command(identity: OwnedIdentity) -> Command:
    _require_complete_identity(identity)
    assert identity.kubeconfig is not None
    return Command(
        ("kind", "delete", "cluster", "--name", LAB_IDENTITY, "--kubeconfig", identity.kubeconfig),
        300,
        env=_docker_environment(identity),
        mutating=True,
    )


def kind_create_command(identity: OwnedIdentity) -> Command:
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


def kind_load_command(identity: OwnedIdentity, image: str) -> Command:
    _require_complete_identity(identity)
    if type(image) is not str or not (
        _KIL_IMAGE.fullmatch(image) or _ENVOY_IMAGE.fullmatch(image)
    ):
        raise JournalError("Kind load image is not the exact KIL content reference")
    return Command(
        ("kind", "load", "docker-image", image, "--name", LAB_IDENTITY),
        300,
        env=_docker_environment(identity),
        mutating=True,
    )


def docker_image_import_commands(
    identity: OwnedIdentity, archive: bytes, source_image_id: str,
    image: str, envoy_image: str,
) -> tuple[Command, ...]:
    _require_complete_identity(identity)
    if type(archive) is not bytes or not archive or len(archive) > 1024 * 1024 * 1024:
        raise JournalError("image archive bytes are invalid")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", source_image_id) is None:
        raise JournalError("source image identity is invalid")
    if _KIL_IMAGE.fullmatch(image) is None or _ENVOY_IMAGE.fullmatch(envoy_image) is None:
        raise JournalError("import image references are invalid")
    environment = _docker_environment(identity)
    return (
        Command(("docker", "load"), 300, stdin=archive, env=environment, mutating=True),
        Command(("docker", "tag", source_image_id, image), 60, env=environment, mutating=True),
        Command(("docker", "pull", envoy_image), 300, env=environment, mutating=True),
        Command(("docker", "image", "inspect", image), 60, env=environment),
        Command(("docker", "image", "inspect", envoy_image), 60, env=environment),
    )


def kubectl_apply_command(identity: OwnedIdentity, manifest: bytes) -> Command:
    return _kubectl(identity, "apply", "-f", "-", mutating=True, stdin=manifest)


def kubectl_apply_calico_command(identity: OwnedIdentity, path: Path) -> Command:
    if not isinstance(path, Path):
        raise JournalError("Calico manifest path must be a Path")
    return _kubectl(identity, "apply", "-f", str(path), mutating=True)


def kubectl_attach_command(identity: OwnedIdentity, namespace: str, instruction: bytes) -> Command:
    return _kubectl(
        identity, "attach", "pod/driver", "--namespace", namespace, "--stdin",
        mutating=True, stdin=instruction,
    )


def kubectl_driver_pod_command(identity: OwnedIdentity, namespace: str) -> Command:
    if type(namespace) is not str or namespace not in _APPLICATION_NAMESPACES:
        raise JournalError("driver namespace is not reviewed")
    return _kubectl(
        identity, "get", "pod", "driver", "--namespace", namespace,
        "--output", "json",
    )


def kubectl_source_pod_command(identity: OwnedIdentity, namespace: str, pod: str) -> Command:
    if type(namespace) is not str or namespace not in _APPLICATION_NAMESPACES:
        raise JournalError("source namespace is not reviewed")
    if type(pod) is not str or not (
        pod == "driver"
        or re.fullmatch(r"(?:authz|envoy|target)-[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", pod)
    ):
        raise JournalError("source Pod is not reviewed")
    return _kubectl(
        identity, "get", "pod", pod, "--namespace", namespace,
        "--output", "json",
    )


def kubectl_source_read_command(identity: OwnedIdentity, namespace: str, pod: str, role: str) -> Command:
    kubectl_source_pod_command(identity, namespace, pod)
    paths = {"authz": "/evidence/decisions.jsonl", "target": "/evidence/targets.jsonl"}
    if role not in paths or not pod.startswith(role + "-"):
        raise JournalError("ledger source is not exact")
    return _kubectl(
        identity, "exec", f"pod/{pod}", "--namespace", namespace,
        "--container", role, "--", "head", "-c", "1048577", paths[role],
    )


def kubectl_ready_endpoint_command(identity: OwnedIdentity, namespace: str, role: str) -> Command:
    if namespace not in _APPLICATION_NAMESPACES or role not in {"envoy", "authz", "target"}:
        raise JournalError("ready endpoint target is not reviewed")
    return _kubectl(
        identity, "get", "endpointslices", "--namespace", namespace,
        "--selector", f"kubernetes.io/service-name={role}", "--output", "json",
    )


def kubectl_calico_workload_command(identity: OwnedIdentity, kind: str) -> Command:
    values = {
        "DaemonSet": ("daemonset", "calico-node"),
        "Deployment": ("deployment", "calico-kube-controllers"),
    }
    if type(kind) is not str or kind not in values:
        raise JournalError("Calico workload kind is not reviewed")
    resource, name = values[kind]
    return _kubectl(
        identity, "get", resource, name, "--namespace", "kube-system",
        "--output", "json",
    )


def kubectl_workload_ready_command(identity: OwnedIdentity, namespace: str, role: str) -> Command:
    if namespace not in _APPLICATION_NAMESPACES or role not in {"envoy", "authz", "target"}:
        raise JournalError("application readiness target is not reviewed")
    return _kubectl(
        identity, "wait", "--for=condition=Available", f"deployment/{role}",
        "--namespace", namespace, "--timeout=1s",
    )


def kubectl_envoy_quiesce_commands(identity: OwnedIdentity, namespace: str, pod: str) -> tuple[Command, Command]:
    kubectl_source_pod_command(identity, namespace, pod)
    if not pod.startswith("envoy-"):
        raise JournalError("Envoy quiescence Pod is not exact")
    prefix = ("exec", f"pod/{pod}", "--namespace", namespace, "--container", "envoy", "--", "/bin/bash", "-pceu")
    return (
        _kubectl(identity, *prefix, _ENVOY_DRAIN_SCRIPT, mutating=True),
        _kubectl(identity, *prefix, _ENVOY_STATS_SCRIPT),
    )


def _kubectl(
    identity: OwnedIdentity,
    *arguments: str,
    mutating: bool = False,
    stdin: bytes | None = None,
) -> Command:
    _require_complete_identity(identity)
    assert identity.kubeconfig is not None
    return Command(
        ("kubectl", "--kubeconfig", identity.kubeconfig, *arguments),
        300,
        stdin=stdin,
        mutating=mutating,
    )


def owned_commands(identity: OwnedIdentity) -> tuple[Command, ...]:
    """Return the closed owned mutation vocabulary; never discovery-selected names."""
    return (
        _colima_command("start"),
        kind_create_command(identity),
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
    if family in {"image_import", "image_load"}:
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
    if family == "envoy_quiesce":
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


def kubectl_cancel_driver_command(identity: OwnedIdentity, details: Mapping[str, object]) -> Command:
    namespace = str(details["namespace"])
    pod = str(details["pod"])
    uid = _exact_string("driver Pod UID", details["uid"])
    if namespace not in _APPLICATION_NAMESPACES or pod != "driver":
        raise JournalError("driver deletion identity is outside the reviewed set")
    _require_complete_identity(identity)
    assert identity.kubeconfig is not None
    _exact_string("driver cancellation UID", uid)
    return _kubectl(
        identity, "attach", "pod/driver", "--namespace", namespace, "--stdin",
        stdin=b"", mutating=True,
    )


_driver_delete = kubectl_cancel_driver_command


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
            "namespaces,pods,services,endpoints,endpointslices,serviceaccounts,configmaps,deployments,daemonsets,networkpolicies,nodes,replicasets",
            "--all-namespaces",
            "--output",
            "json",
        )
    )
    return tuple(commands)


def _evidence_freeze_intent(
    identity: OwnedIdentity, drivers: tuple[tuple[str, str, str], ...]
) -> tuple[str, tuple[tuple[str, object], ...]]:
    """Commit the exact immutable source plan before diagnostic collection."""
    commands = _evidence_freeze_commands(identity, drivers)
    commitment = {
        "schema": "kil.v3b2-evidence-freeze-plan.v1",
        "drivers": [list(driver) for driver in drivers],
        "commands": [
            {
                "argv": list(command.argv),
                "timeout_s": command.timeout_s,
                "stdin": None,
            }
            for command in commands
        ],
    }
    digest = hashlib.sha256(_canonical_bytes(commitment)).hexdigest()
    return _recovery_intent("evidence_freeze_intent", {"evidence_sha256": digest})


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
    return tuple(
        started[namespace]
        for _track, namespace in TRACK_NAMESPACES
        if namespace in started and namespace not in canceled
    )


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


def _recovery_intent(
    event: str, details: Mapping[str, object]
) -> tuple[str, tuple[tuple[str, object], ...]]:
    frozen_details = tuple(sorted(details.items()))
    _validate_event_details(event, dict(frozen_details))
    return event, frozen_details


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
    command_pending = [(family, details) for family, details in pending if family != "request"]
    if command_pending:
        if len(command_pending) != 1:
            raise JournalError("manual_recovery_required: multiple owned mutations are pending")
        if command_pending[0][0] == "evidence_freeze":
            return RecoveryPlan(_evidence_freeze_commands(identity, drivers))
        family, details = command_pending[0]
        if family == "driver_cancel":
            if observed is None:
                return RecoveryPlan((_driver_uid_attestation(identity, details),))
            expected = (str(details["namespace"]), str(details["pod"]), str(details["uid"]))
            if expected not in set(observed.driver_pods):
                return RecoveryPlan((_driver_uid_attestation(identity, details),))
            return RecoveryPlan((_driver_delete(identity, details),))
        if family == "cluster_delete":
            if observed is None or observed.kind_cluster is None:
                return RecoveryPlan((_docker_inspect_node(identity),))
            return RecoveryPlan((kind_delete_command(identity),))
        if family in {"profile_stop", "profile_delete"}:
            status = Command(("colima", "status", "--profile", LAB_IDENTITY), 60)
            if observed is None or observed.colima_profile is None:
                return RecoveryPlan((status,))
            operation = "stop" if family == "profile_stop" else "delete"
            return RecoveryPlan((_colima_command(operation),))
        command = _pending_command(*command_pending[0], identity)
        return RecoveryPlan(()) if command is None else RecoveryPlan((command,))
    if (request_claimed or readiness_complete) and not frozen:
        uid_attestations = tuple(
            _driver_uid_attestation(
                identity, {"namespace": item[0], "pod": item[1], "uid": item[2]}
            )
            for item in drivers
        )
        return RecoveryPlan(
            (*uid_attestations, *_evidence_freeze_commands(identity, drivers)),
            requests_to_send=(),
            publication_allowed=False,
            next_intent=_evidence_freeze_intent(identity, drivers),
        )
    if frozen and drivers:
        next_driver = drivers[0]
        details = {"namespace": next_driver[0], "pod": next_driver[1], "uid": next_driver[2]}
        return RecoveryPlan(
            tuple(
                _driver_uid_attestation(
                    identity, {"namespace": item[0], "pod": item[1], "uid": item[2]}
                )
                for item in drivers
            ),
            requests_to_send=(),
            publication_allowed=False,
            next_intent=_recovery_intent("driver_cancel_intent", details),
        )
    completed = {record["event"] for record in typed_events}
    if not typed_events:
        return RecoveryPlan((Command(("colima", "status", "--profile", LAB_IDENTITY), 60),))
    if "cluster_create_complete" in completed and "cluster_delete_complete" not in completed:
        details = {"kind_cluster": LAB_IDENTITY, "kubeconfig": identity.kubeconfig}
        return RecoveryPlan(
            _cluster_attestations(identity),
            next_intent=_recovery_intent("cluster_delete_intent", details),
        )
    if "cluster_delete_complete" in completed and "cluster_absence_proof_complete" not in completed:
        details = {"kind_cluster": LAB_IDENTITY, "node_container_id": identity.node_container_id}
        return RecoveryPlan(
            (_docker_inspect_node(identity),),
            next_intent=_recovery_intent("cluster_absence_proof_intent", details),
        )
    if "profile_start_complete" in completed and "profile_stop_complete" not in completed:
        status = Command(("colima", "status", "--profile", LAB_IDENTITY), 60)
        return RecoveryPlan(
            (status,),
            next_intent=_recovery_intent("profile_stop_intent", {"colima_profile": LAB_IDENTITY}),
        )
    if "profile_stop_complete" in completed and "profile_delete_complete" not in completed:
        status = Command(("colima", "status", "--profile", LAB_IDENTITY), 60)
        return RecoveryPlan(
            (status,),
            next_intent=_recovery_intent("profile_delete_intent", {"colima_profile": LAB_IDENTITY}),
        )
    if "profile_delete_complete" in completed and "profile_absence_proof_complete" not in completed:
        status = Command(("colima", "status", "--profile", LAB_IDENTITY), 60)
        return RecoveryPlan(
            (status,),
            next_intent=_recovery_intent("profile_absence_proof_intent", {"colima_profile": LAB_IDENTITY}),
        )
    if "profile_absence_proof_complete" in completed and "foreign_snapshot_comparison_complete" not in completed:
        return RecoveryPlan((Command(("colima", "list", "--json"), 60),))
    comparison_unchanged = any(
        record["event"] == "foreign_snapshot_comparison_complete"
        and isinstance(record["details"], dict)
        and record["details"].get("unchanged") is True
        for record in typed_events
    )
    publication_allowed = comparison_unchanged and {
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
    "colima_start_command",
    "create_journal",
    "docker_context_command",
    "docker_image_import_commands",
    "kind_create_command",
    "kind_load_command",
    "kind_delete_command",
    "kubectl_apply_calico_command",
    "kubectl_apply_command",
    "kubectl_attach_command",
    "kubectl_calico_workload_command",
    "kubectl_driver_pod_command",
    "kubectl_ready_endpoint_command",
    "kubectl_source_pod_command",
    "kubectl_source_read_command",
    "kubectl_workload_ready_command",
    "kubectl_envoy_quiesce_commands",
    "load_journal",
    "owned_commands",
    "recovery_plan",
    "select_lifecycle_mode",
]
