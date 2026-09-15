"""Closed, identity-bracketed source for two control-plane manifests."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re

from kil.v3b2_closed_yaml import decode_closed_yaml
from kil.v3b2_journal import Command, OwnedIdentity
from kil.v3b2_proofs import (
    ExpectedContext,
    ObservationRequest,
    RawObservation,
    canonical,
    decode,
)


COMPONENT_PATHS = (
    ("kube-apiserver", "/etc/kubernetes/manifests/kube-apiserver.yaml"),
    ("kube-controller-manager", "/etc/kubernetes/manifests/kube-controller-manager.yaml"),
)
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_SOURCE_RECORD_BYTES = 4 * 1024 * 1024


class ControlPlaneManifestSourceError(ValueError):
    """Manifest source evidence is malformed, unbound, or incomplete."""


@dataclass(frozen=True, slots=True)
class ControlPlaneManifestBinding:
    component: str
    path: str
    byte_count: int
    sha256: str
    semantic_sha256: str

    def __post_init__(self) -> None:
        paths = dict(COMPONENT_PATHS)
        if (type(self.component) is not str or self.component not in paths
                or type(self.path) is not str or self.path != paths[self.component]):
            raise ControlPlaneManifestSourceError("manifest binding component/path is invalid")
        if (type(self.byte_count) is not int or not 1 <= self.byte_count <= MAX_MANIFEST_BYTES):
            raise ControlPlaneManifestSourceError("manifest binding byte count is invalid")
        if (type(self.sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None
                or type(self.semantic_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", self.semantic_sha256) is None):
            raise ControlPlaneManifestSourceError("manifest binding digest is invalid")


@dataclass(frozen=True, slots=True)
class ControlPlaneManifestSourceProof:
    run_id: str
    cluster_uid: str
    node_container_id: str
    node_config_id: str
    raw_observations: tuple[bytes, ...]
    bindings: tuple[ControlPlaneManifestBinding, ...]
    runtime_complete: bool = False
    application_complete: bool = False

    def __post_init__(self) -> None:
        try:
            if type(self.run_id) is not str or re.fullmatch(r"[0-9a-f]{64}", self.run_id) is None:
                raise ControlPlaneManifestSourceError("manifest source run ID is invalid")
            if (type(self.cluster_uid) is not str
                    or re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                                    self.cluster_uid) is None):
                raise ControlPlaneManifestSourceError("manifest source cluster UID is invalid")
            if (type(self.node_container_id) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", self.node_container_id) is None):
                raise ControlPlaneManifestSourceError("manifest source node ID is invalid")
            if (type(self.node_config_id) is not str
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", self.node_config_id) is None):
                raise ControlPlaneManifestSourceError("manifest source node config ID is invalid")
            if (type(self.runtime_complete) is not bool or self.runtime_complete
                    or type(self.application_complete) is not bool or self.application_complete):
                raise ControlPlaneManifestSourceError("manifest source cannot assert completion")
            if (type(self.raw_observations) is not tuple or len(self.raw_observations) != 4
                    or any(type(row) is not bytes for row in self.raw_observations)):
                raise ControlPlaneManifestSourceError("retained raw observation tuple is invalid")
            if (type(self.bindings) is not tuple or len(self.bindings) != 2
                    or any(type(binding) is not ControlPlaneManifestBinding
                           for binding in self.bindings)):
                raise ControlPlaneManifestSourceError("retained manifest bindings are invalid")
            for binding in self.bindings:
                binding.__post_init__()
            context, identity = _retained_authority(self.raw_observations)
            if (self.run_id != context.run_id
                    or self.cluster_uid != identity.cluster_incarnation_uid
                    or self.node_container_id != identity.node_container_id):
                raise ControlPlaneManifestSourceError(
                    "manifest source identity differs from retained authority")
            rows = tuple(_decode_raw_observation(row)
                         for row in self.raw_observations)
            specs = control_plane_manifest_observation_specs(identity)
            if tuple((row.label, row.argv, row.env) for row in rows) != tuple(
                    (spec.label, spec.command.argv, spec.command.env) for spec in specs):
                raise ControlPlaneManifestSourceError(
                    "manifest source registry differs from retained authority")
            config_id, calculated = _compute_retained(rows, self.node_container_id)
            requested_image = _context_authority(context, identity)
            if _node_projection(rows[0].stdout)["Config.Image"] != requested_image:
                raise ControlPlaneManifestSourceError(
                    "manifest source image differs from retained authority")
            if self.node_config_id != config_id or self.bindings != calculated:
                raise ControlPlaneManifestSourceError(
                    "manifest source proof differs from raw reconstruction")
            _require_record_budget(self.run_id, self.cluster_uid, self.node_container_id,
                                   self.node_config_id, self.raw_observations, self.bindings)
        except ControlPlaneManifestSourceError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError,
                OverflowError, RecursionError) as error:
            raise ControlPlaneManifestSourceError("manifest source proof is malformed") from error


def control_plane_manifest_read_argv(node_container_id: str,
                                     component: str) -> tuple[str, ...]:
    if (type(node_container_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", node_container_id) is None):
        raise ControlPlaneManifestSourceError("owned node container ID is invalid")
    paths = dict(COMPONENT_PATHS)
    if type(component) is not str or component not in paths:
        raise ControlPlaneManifestSourceError("control-plane component is not reviewed")
    return ("docker", "exec", node_container_id, "/bin/cat", "--", paths[component])


def control_plane_manifest_observation_specs(identity: OwnedIdentity) -> tuple[ObservationRequest, ...]:
    if type(identity) is not OwnedIdentity:
        raise ControlPlaneManifestSourceError("owned identity type is not exact")
    try:
        identity.__post_init__()
    except (TypeError, ValueError, AttributeError) as error:
        raise ControlPlaneManifestSourceError("owned identity no longer validates") from error
    if any(getattr(identity, name) is None for name in (
            "docker_host", "kind_cluster", "kubeconfig",
            "cluster_incarnation_uid", "node_container_id")):
        raise ControlPlaneManifestSourceError("owned identity is incomplete")
    assert identity.kubeconfig is not None
    assert identity.docker_host is not None
    assert identity.node_container_id is not None
    environment = (
        ("DOCKER_CONFIG", str(Path(identity.kubeconfig).parent / "docker-config")),
        ("DOCKER_HOST", identity.docker_host),
    )
    node = ("docker", "inspect", "kil-v3-lab-control-plane")
    commands = (
        ("node_before", node),
        ("kube-apiserver", control_plane_manifest_read_argv(
            identity.node_container_id, "kube-apiserver")),
        ("kube-controller-manager", control_plane_manifest_read_argv(
            identity.node_container_id, "kube-controller-manager")),
        ("node_after", node),
    )
    return tuple(ObservationRequest(label, Command(argv, 60, env=environment))
                 for label, argv in commands)


_RAW_FIELDS = frozenset({"label", "argv", "env", "returncode", "stdout_hex", "stderr_hex"})
_RAW_AUTHORITY_FIELDS = _RAW_FIELDS | {"expected_context"}
_RAW_COMMITMENT_FIELDS = _RAW_FIELDS | {"expected_context_sha256"}
_CONTEXT_FIELDS = frozenset({"run_id", "intent_sequence", "family", "intent", "inputs"})
_EXPECTED_LABELS = ("node_before", "kube-apiserver", "kube-controller-manager", "node_after")
_KIND_IMAGE = re.compile(r"kindest/node:v1\.36\.1@sha256:[0-9a-f]{64}")


def _expected_context_document(context: ExpectedContext) -> dict[str, object]:
    return {
        "run_id": context.run_id,
        "intent_sequence": context.intent_sequence,
        "family": context.family,
        "intent": decode(context.intent),
        "inputs": decode(context.inputs),
    }


def _encode_raw_observation(row: RawObservation, context: ExpectedContext,
                            *, retain_context: bool) -> bytes:
    document = {
        "label": row.label,
        "argv": list(row.argv),
        "env": [list(pair) for pair in row.env],
        "returncode": row.returncode,
        "stdout_hex": row.stdout.hex(),
        "stderr_hex": row.stderr.hex(),
    }
    if retain_context:
        document["expected_context"] = _expected_context_document(context)
    else:
        document["expected_context_sha256"] = context.commitment
    return canonical(document)


def _raw_document(payload: bytes) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > MAX_SOURCE_RECORD_BYTES:
        raise ControlPlaneManifestSourceError("retained raw observation bytes are invalid")
    document = decode(payload, maximum=MAX_SOURCE_RECORD_BYTES)
    if (type(document) is not dict or frozenset(document) not in {
            _RAW_AUTHORITY_FIELDS, _RAW_COMMITMENT_FIELDS}
            or canonical(document) != payload):
        raise ControlPlaneManifestSourceError("retained raw observation is not canonical and closed")
    return document


def _decode_raw_observation(payload: bytes) -> RawObservation:
    document = _raw_document(payload)
    if (type(document["label"]) is not str or type(document["argv"]) is not list
            or any(type(value) is not str for value in document["argv"])
            or type(document["env"]) is not list
            or any(type(pair) is not list or len(pair) != 2
                   or any(type(value) is not str for value in pair)
                   for pair in document["env"])
            or type(document["returncode"]) is not int
            or type(document["stdout_hex"]) is not str
            or type(document["stderr_hex"]) is not str):
        raise ControlPlaneManifestSourceError("retained raw observation fields are invalid")
    try:
        stdout = bytes.fromhex(document["stdout_hex"])
        stderr = bytes.fromhex(document["stderr_hex"])
    except ValueError as error:
        raise ControlPlaneManifestSourceError("retained raw observation hex is invalid") from error
    if (document["stdout_hex"] != stdout.hex()
            or document["stderr_hex"] != stderr.hex()):
        raise ControlPlaneManifestSourceError(
            "retained raw observation hex is not lowercase and contiguous")
    row = RawObservation(document["label"], tuple(document["argv"]),
                         tuple(tuple(pair) for pair in document["env"]),
                         document["returncode"], stdout, stderr)
    row.__post_init__()
    return row


def _retained_authority(raw_observations: tuple[bytes, ...]
                        ) -> tuple[ExpectedContext, OwnedIdentity]:
    documents = tuple(_raw_document(payload) for payload in raw_observations)
    if (set(documents[0]) != _RAW_AUTHORITY_FIELDS
            or any(set(document) != _RAW_COMMITMENT_FIELDS for document in documents[1:])):
        raise ControlPlaneManifestSourceError("retained context authority placement is invalid")
    retained = documents[0]["expected_context"]
    if type(retained) is not dict or set(retained) != _CONTEXT_FIELDS:
        raise ControlPlaneManifestSourceError("retained expected context is not closed")
    if (type(retained["run_id"]) is not str
            or type(retained["intent_sequence"]) is not int
            or type(retained["family"]) is not str
            or type(retained["intent"]) is not dict or type(retained["inputs"]) is not dict):
        raise ControlPlaneManifestSourceError("retained expected context types are invalid")
    context = ExpectedContext(
        retained["run_id"], retained["intent_sequence"], retained["family"],
        canonical(retained["intent"]), canonical(retained["inputs"]))
    context.__post_init__()
    if any(document["expected_context_sha256"] != context.commitment
           for document in documents[1:]):
        raise ControlPlaneManifestSourceError("retained expected context commitment changed")
    inputs = retained["inputs"]
    identity_fields = tuple(field.name for field in fields(OwnedIdentity))
    authority = inputs.get("owned_identity")
    if type(authority) is not dict or set(authority) != set(identity_fields):
        raise ControlPlaneManifestSourceError("retained owned identity is not closed")
    identity = OwnedIdentity(*(authority[name] for name in identity_fields))
    _context_authority(context, identity)
    return context, identity


def _pod(payload: bytes) -> dict:
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_MANIFEST_BYTES:
        raise ControlPlaneManifestSourceError("manifest stdout exceeds its exact byte bound")
    try:
        text = payload.decode("utf-8", errors="strict")
        pod = decode_closed_yaml(text)
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise ControlPlaneManifestSourceError("manifest is not strict closed UTF-8 YAML") from error
    if (type(pod) is not dict
            or set(pod) != {"apiVersion", "kind", "metadata", "spec"}
            or pod.get("apiVersion") != "v1" or pod.get("kind") != "Pod"
            or type(pod.get("metadata")) is not dict or type(pod.get("spec")) is not dict):
        raise ControlPlaneManifestSourceError("manifest root is not one exact v1 Pod")
    return pod


def _node_projection(payload: bytes) -> dict[str, object]:
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_MANIFEST_BYTES:
        raise ControlPlaneManifestSourceError("node inspect stdout exceeds its exact byte bound")
    try:
        text = payload.decode("utf-8", errors="strict")

        def object_from_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ControlPlaneManifestSourceError("node inspect JSON has a duplicate field")
                result[key] = value
            return result

        def reject_constant(_value):
            raise ControlPlaneManifestSourceError("node inspect JSON has a nonfinite value")

        document = json.loads(text, object_pairs_hook=object_from_pairs,
                              parse_constant=reject_constant)
        if type(document) is not list or len(document) != 1 or type(document[0]) is not dict:
            raise ControlPlaneManifestSourceError("node inspect root is ambiguous")
        node = document[0]
        config = node["Config"]
        state = node["State"]
        if type(config) is not dict or type(state) is not dict:
            raise ControlPlaneManifestSourceError("node inspect configuration/state is invalid")
        labels = config["Labels"]
        projection = {
            "Id": node["Id"], "Name": node["Name"], "Image": node["Image"],
            "Config.Image": config["Image"], "Config.Labels": labels,
            "State.Running": state["Running"],
        }
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        if isinstance(error, ControlPlaneManifestSourceError):
            raise
        raise ControlPlaneManifestSourceError("node inspect projection is incomplete") from error
    if (type(projection["Id"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", projection["Id"]) is None
            or projection["Name"] != "/kil-v3-lab-control-plane"
            or type(projection["Image"]) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", projection["Image"]) is None
            or type(projection["Config.Image"]) is not str
            or _KIND_IMAGE.fullmatch(projection["Config.Image"]) is None
            or type(projection["Config.Labels"]) is not dict
            or projection["Config.Labels"] != {
                "io.x-k8s.kind.cluster": "kil-v3-lab",
                "io.x-k8s.kind.role": "control-plane",
            }
            or projection["State.Running"] is not True):
        raise ControlPlaneManifestSourceError("node differs from the running owned Kind node")
    return projection


def _compute_retained(rows: tuple[RawObservation, ...], node_container_id: str
                      ) -> tuple[str, tuple[ControlPlaneManifestBinding, ...]]:
    if type(rows) is not tuple or len(rows) != 4 or any(type(row) is not RawObservation for row in rows):
        raise ControlPlaneManifestSourceError("source requires exactly four raw observations")
    for row in rows:
        row.__post_init__()
        _validate_observation_primitives(row)
    if tuple(row.label for row in rows) != _EXPECTED_LABELS:
        raise ControlPlaneManifestSourceError("source observation order is not exact")
    environment = rows[0].env
    if (tuple(row.env for row in rows) != (environment,) * 4
            or tuple(pair[0] for pair in environment) != ("DOCKER_CONFIG", "DOCKER_HOST")):
        raise ControlPlaneManifestSourceError("retained Docker authority is not exact")
    docker_config, docker_host = environment[0][1], environment[1][1]
    config_path = Path(docker_config)
    socket_text = docker_host.removeprefix("unix://")
    socket_path = Path(socket_text)
    if (not config_path.is_absolute() or ".." in config_path.parts
            or str(config_path) != docker_config or config_path.name != "docker-config"
            or not docker_host.startswith("unix:///") or not socket_path.is_absolute()
            or ".." in socket_path.parts or str(socket_path) != socket_text
            or not docker_host.endswith("/kil-v3-lab/docker.sock")):
        raise ControlPlaneManifestSourceError("retained Docker authority is not isolated")
    expected_argv = (
        ("docker", "inspect", "kil-v3-lab-control-plane"),
        control_plane_manifest_read_argv(node_container_id, "kube-apiserver"),
        control_plane_manifest_read_argv(node_container_id, "kube-controller-manager"),
        ("docker", "inspect", "kil-v3-lab-control-plane"),
    )
    if tuple(row.argv for row in rows) != expected_argv:
        raise ControlPlaneManifestSourceError("retained source command registry is not exact")
    if any(row.returncode != 0 or row.stderr != b"" for row in rows):
        raise ControlPlaneManifestSourceError("source observation transport was unsuccessful or truncated")
    if any(len(row.stdout) > MAX_MANIFEST_BYTES for row in rows):
        raise ControlPlaneManifestSourceError("source observation stdout exceeds one MiB")
    before = _node_projection(rows[0].stdout)
    after = _node_projection(rows[3].stdout)
    if before != after or before["Id"] != node_container_id:
        raise ControlPlaneManifestSourceError("node identity changed across manifest reads")
    bindings: list[ControlPlaneManifestBinding] = []
    for (component, path), row in zip(COMPONENT_PATHS, rows[1:3], strict=True):
        pod = _pod(row.stdout)
        bindings.append(ControlPlaneManifestBinding(
            component, path, len(row.stdout), sha256(row.stdout).hexdigest(),
            sha256(canonical(pod)).hexdigest()))
    result = tuple(sorted(bindings, key=lambda binding: binding.component))
    return before["Image"], result  # type: ignore[return-value]


def _validate_observation_primitives(row: RawObservation) -> None:
    if (type(row.label) is not str or type(row.argv) is not tuple
            or any(type(value) is not str for value in row.argv)
            or type(row.env) is not tuple
            or any(type(pair) is not tuple or len(pair) != 2
                   or any(type(value) is not str for value in pair) for pair in row.env)
            or type(row.returncode) is not int or type(row.stdout) is not bytes
            or type(row.stderr) is not bytes):
        raise ControlPlaneManifestSourceError("source observation primitives are not exact")


def _require_record_budget(run_id: str, cluster_uid: str, node_container_id: str,
                           node_config_id: str, raw_observations: tuple[bytes, ...],
                           bindings: tuple[ControlPlaneManifestBinding, ...]) -> None:
    proof_document = {
        "run_id": run_id,
        "cluster_uid": cluster_uid,
        "node_container_id": node_container_id,
        "node_config_id": node_config_id,
        "raw_observations": [decode(row, maximum=MAX_SOURCE_RECORD_BYTES)
                             for row in raw_observations],
        "bindings": [asdict(binding) for binding in bindings],
        "runtime_complete": False,
        "application_complete": False,
    }
    context, _identity = _retained_authority(raw_observations)
    record = {
        "schema": "kil.v4.control-plane-manifest-source.v1",
        "context": _expected_context_document(context),
        "proof": proof_document,
    }
    if len(canonical(record)) > MAX_SOURCE_RECORD_BYTES:
        raise ControlPlaneManifestSourceError("manifest source proof exceeds four MiB")


def _context_authority(context: ExpectedContext, owned_identity: OwnedIdentity) -> str:
    if type(context) is not ExpectedContext or type(owned_identity) is not OwnedIdentity:
        raise ControlPlaneManifestSourceError("context/owned identity types are not exact")
    context.__post_init__()
    owned_identity.__post_init__()
    if any(getattr(owned_identity, name) is None for name in (
            "docker_host", "kind_cluster", "kubeconfig",
            "cluster_incarnation_uid", "node_container_id")):
        raise ControlPlaneManifestSourceError("owned identity is incomplete")
    inputs = decode(context.inputs)
    intent = decode(context.intent)
    expected_identity = {field.name: getattr(owned_identity, field.name)
                         for field in fields(OwnedIdentity)}
    if (type(inputs) is not dict or type(context.family) is not str
            or context.family != "control_plane_manifest_source"
            or context.run_id != inputs.get("run_id")
            or intent != {"kind_cluster": "kil-v3-lab"}
            or inputs.get("owned_identity") != expected_identity
            or owned_identity.kind_cluster != "kil-v3-lab"
            or type(inputs.get("kind_node_image")) is not str
            or _KIND_IMAGE.fullmatch(inputs["kind_node_image"]) is None):
        raise ControlPlaneManifestSourceError("context differs from owned source authority")
    return inputs["kind_node_image"]


def validate_control_plane_manifest_source(*, context, owned_identity, observations):
    try:
        requested_image = _context_authority(context, owned_identity)
        if (type(observations) is not tuple or len(observations) != 4
                or any(type(row) is not RawObservation for row in observations)):
            raise ControlPlaneManifestSourceError("source requires an exact four-observation tuple")
        specs = control_plane_manifest_observation_specs(owned_identity)
        if tuple((row.label, row.argv, row.env) for row in observations) != tuple(
                (spec.label, spec.command.argv, spec.command.env) for spec in specs):
            raise ControlPlaneManifestSourceError("source observation registry is not exact")
        for row in observations:
            row.__post_init__()
            _validate_observation_primitives(row)
        assert owned_identity.node_container_id is not None
        assert owned_identity.cluster_incarnation_uid is not None
        node_config_id, bindings = _compute_retained(observations, owned_identity.node_container_id)
        before = _node_projection(observations[0].stdout)
        if before["Config.Image"] != requested_image:
            raise ControlPlaneManifestSourceError("requested Kind image differs from node")
        raw = tuple(_encode_raw_observation(row, context, retain_context=index == 0)
                    for index, row in enumerate(observations))
        return ControlPlaneManifestSourceProof(
            context.run_id, owned_identity.cluster_incarnation_uid,
            owned_identity.node_container_id, node_config_id, raw, bindings)
    except ControlPlaneManifestSourceError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError,
            OverflowError, RecursionError) as error:
        raise ControlPlaneManifestSourceError("malformed control-plane manifest source") from error


def control_plane_manifest_pod(*, source, component):
    try:
        if type(source) is not ControlPlaneManifestSourceProof:
            raise ControlPlaneManifestSourceError("manifest source proof type is not exact")
        source.__post_init__()
        paths = dict(COMPONENT_PATHS)
        if type(component) is not str or component not in paths:
            raise ControlPlaneManifestSourceError("control-plane component is not reviewed")
        rows = tuple(_decode_raw_observation(row) for row in source.raw_observations)
        index = tuple(name for name, _path in COMPONENT_PATHS).index(component) + 1
        return _pod(rows[index].stdout)
    except ControlPlaneManifestSourceError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError,
            OverflowError, RecursionError) as error:
        raise ControlPlaneManifestSourceError("malformed retained manifest source") from error


__all__ = (
    "COMPONENT_PATHS", "MAX_MANIFEST_BYTES", "MAX_SOURCE_RECORD_BYTES",
    "ControlPlaneManifestBinding", "ControlPlaneManifestSourceError",
    "ControlPlaneManifestSourceProof", "control_plane_manifest_observation_specs",
    "control_plane_manifest_pod", "control_plane_manifest_read_argv",
    "validate_control_plane_manifest_source",
)
