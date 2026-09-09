"""Pure proof that reviewed policy configuration preceded workload observation.

This bounded stage proves neither CNI enforcement nor application completion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from pathlib import Path

from kil.canonical import canonical_json
from kil.v3b2_api_defaults import _equal
from kil.v3b2_contracts import V3B2Profile, TRACK_NAMESPACES
from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_manifests import WorkloadIdentity, render_kind_config, render_objects
from kil.v3b2_proofs import ExpectedContext, RawObservation, canonical


_HEX = re.compile(r"[0-9a-f]{64}")
_MAX_RAW = 2 * 1024 * 1024


class ApplicationPolicyStageError(ValueError):
    """Policy-stage evidence is malformed, unbound, or incomplete."""


@dataclass(frozen=True, slots=True, order=True)
class ApplicationPolicyBinding:
    kind: str
    namespace: str
    name: str
    uid: str
    resource_version: str

    def __post_init__(self):
        from kil.v3b2_driver_pod_admission import _uid, _rv
        if (type(self.kind) is not str or self.kind not in {"Namespace", "NetworkPolicy"}
                or type(self.namespace) is not str or type(self.name) is not str
                or not self.name):
            raise ApplicationPolicyStageError("policy binding identity is invalid")
        _uid(self.uid); _rv(self.resource_version)


def _desired(profile, workload, rendered_objects):
    if type(profile) is not V3B2Profile or type(workload) is not WorkloadIdentity:
        raise ApplicationPolicyStageError("profile/workload types are not exact")
    profile.__post_init__(); workload.__post_init__()
    if type(rendered_objects) is not bytes or len(rendered_objects) > _MAX_RAW:
        raise ApplicationPolicyStageError("rendered objects are not bounded bytes")
    expected = render_objects(profile, workload)
    if rendered_objects != expected:
        raise ApplicationPolicyStageError("rendered objects differ from independent expectations")
    items = json.loads(expected)["items"]
    policy = [row for row in items if row["kind"] in {"Namespace", "NetworkPolicy"}]
    if (sum(row["kind"] == "Namespace" for row in policy) != 3
            or sum(row["kind"] == "NetworkPolicy" for row in policy) != 15):
        raise ApplicationPolicyStageError("rendered policy set is not exact")
    return items, policy


def policy_request_bytes(profile: V3B2Profile, workload: WorkloadIdentity) -> bytes:
    rendered = render_objects(profile, workload)
    _, policy = _desired(profile, workload, rendered)
    return (canonical_json({"apiVersion": "v1", "kind": "List", "items": policy}) + "\n").encode("utf-8")


def application_policy_observation_specs(identity: OwnedIdentity):
    if type(identity) is not OwnedIdentity:
        raise ApplicationPolicyStageError("owned identity type is not exact")
    identity.__post_init__()
    if any(getattr(identity, key) is None for key in ("docker_host", "kind_cluster", "kubeconfig",
                                                       "cluster_incarnation_uid", "node_container_id")):
        raise ApplicationPolicyStageError("owned identity is incomplete")
    docker_env = (("DOCKER_CONFIG", str(Path(identity.kubeconfig).parent / "docker-config")),
                  ("DOCKER_HOST", identity.docker_host))
    node = ("docker", "inspect", "kil-v3-lab-control-plane")
    kubectl = ("kubectl", "--kubeconfig", identity.kubeconfig)
    rows = [("node_before", node, docker_env),
            ("policy_objects", (*kubectl, "get", "--filename", "-", "--output", "json"), ())]
    rows.extend((namespace + ":workload_absence",
                 (*kubectl, "get", "pods,deployments,replicasets", "--namespace", namespace, "--output", "json"), ())
                for _, namespace in TRACK_NAMESPACES)
    rows.extend((("node", node, docker_env),
                 ("cluster_namespace", (*kubectl, "get", "namespace", "kube-system", "--output", "json"), ()),
                 ("kind_configuration", (), ())))
    return tuple(rows)


def _raw_bytes(observations):
    if type(observations) is not tuple or len(observations) != 8:
        raise ApplicationPolicyStageError("observations must be an exact tuple of eight")
    for row in observations:
        if type(row) is not RawObservation:
            raise ApplicationPolicyStageError("observation type is not exact")
        row.__post_init__()
    if sum(len(row.stdout) + len(row.stderr) for row in observations) > (_MAX_RAW // 2):
        raise ApplicationPolicyStageError("observations exceed pre-serialization byte bound")
    raw = canonical([{"label": row.label, "argv": list(row.argv), "env": [list(pair) for pair in row.env],
                      "returncode": row.returncode, "stdout_hex": row.stdout.hex(),
                      "stderr_hex": row.stderr.hex()} for row in observations])
    if len(raw) > _MAX_RAW:
        raise ApplicationPolicyStageError("observations exceed retained byte bound")
    return raw


def _observation_shape(row):
    if (type(row.label) is not str or not 1 <= len(row.label) <= 128
            or type(row.argv) is not tuple or len(row.argv) > 16
            or type(row.env) is not tuple or len(row.env) > 2
            or any(type(value) is not str or len(value) > 4096 for value in row.argv)):
        raise ApplicationPolicyStageError("observation command metadata is not bounded exact strings")
    for pair in row.env:
        if (type(pair) is not tuple or len(pair) != 2
                or any(type(value) is not str or len(value) > 4096 for value in pair)):
            raise ApplicationPolicyStageError("observation environment metadata is not exact")


def _decode_raw(raw):
    try:
        from kil.v3b2_proofs import decode
        if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_RAW:
            raise ApplicationPolicyStageError("retained observations exceed byte bound")
        rows = decode(raw, maximum=_MAX_RAW)
        if type(rows) is not list or len(rows) != 8:
            raise ApplicationPolicyStageError("retained observation cardinality is invalid")
        return tuple(RawObservation(row["label"], tuple(row["argv"]), tuple(tuple(pair) for pair in row["env"]),
                                    row["returncode"], bytes.fromhex(row["stdout_hex"]),
                                    bytes.fromhex(row["stderr_hex"])) for row in rows)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise ApplicationPolicyStageError("retained observations are invalid") from error


def _list_metadata_is_source_backed(document):
    return ("metadata" not in document or document["metadata"] == {}
            or document["metadata"] == {"resourceVersion": ""})


def _compute(context, expected_context_commitment, profile, workload, rendered_objects,
             owned_identity, observations):
    if type(observations) is not tuple or len(observations) != 8 or any(
            type(row) is not RawObservation for row in observations):
        raise ApplicationPolicyStageError("observations must be an exact tuple of eight")
    for row in observations: _observation_shape(row)
    if type(context) is not ExpectedContext or type(owned_identity) is not OwnedIdentity:
        raise ApplicationPolicyStageError("context/identity types are not exact")
    context.__post_init__(); owned_identity.__post_init__()
    if (type(expected_context_commitment) is not str or _HEX.fullmatch(expected_context_commitment) is None
            or expected_context_commitment != context.commitment or context.family != "application_apply"):
        raise ApplicationPolicyStageError("expected context commitment/family is not exact")
    items, desired = _desired(profile, workload, rendered_objects)
    inputs = json.loads(context.inputs)
    intent = json.loads(context.intent)
    if (not _equal(intent, {"manifest_sha256": sha256(rendered_objects).hexdigest()})
            or context.run_id != workload.run_id.removeprefix("v3b2-")
            or inputs.get("run_id") != context.run_id
            or V3B2Profile.from_mapping(inputs.get("profile")) != profile
            or not _equal(inputs.get("workload"), json.loads(canonical(asdict(workload))))
            or not _equal(inputs.get("owned_identity"), json.loads(canonical(asdict(owned_identity))))
            or not _equal(inputs.get("application_objects"), items)
            or inputs.get("runtime_contract_complete") is not False
            or inputs.get("kind_node_image") != profile.kind_node_image
            or inputs.get("kind_config_sha256") != sha256(render_kind_config(profile)).hexdigest()
            or inputs.get("kind_config_path") != str(Path(owned_identity.kubeconfig).parent / "kind-config.yaml")):
        raise ApplicationPolicyStageError("context differs from independent policy expectations")
    specs = application_policy_observation_specs(owned_identity)
    if tuple((row.label, row.argv, row.env) for row in observations) != specs:
        raise ApplicationPolicyStageError("policy observation registry is not exact")
    raw = _raw_bytes(observations)
    if any(row.returncode != 0 or row.stderr for row in observations):
        raise ApplicationPolicyStageError("policy observation transport failed")

    from kil.v3b2_proofs import _cluster, validate_applied_objects, decode
    cluster = _cluster(context, observations)
    if cluster.outcome != "complete":
        raise ApplicationPolicyStageError("cluster identity did not revalidate")
    def node_projection(label):
        row = next(item for item in observations if item.label == label)
        document = decode(row.stdout)
        if type(document) is not list or len(document) != 1 or type(document[0]) is not dict:
            raise ApplicationPolicyStageError("node bracket is ambiguous")
        node = document[0]
        return {"Name": node["Name"], "Id": node["Id"], "Image": node["Image"],
                "Config.Image": node["Config"]["Image"], "Config.Labels": node["Config"]["Labels"]}
    if node_projection("node_before") != node_projection("node"):
        raise ApplicationPolicyStageError("node changed across policy stage")

    policy_row = observations[1]
    document = decode(policy_row.stdout)
    if (type(document) is not dict or set(document) not in ({"apiVersion", "kind", "items"},
            {"apiVersion", "kind", "metadata", "items"})
            or document["apiVersion"] != "v1" or document["kind"] != "List"):
        raise ApplicationPolicyStageError("policy readback envelope is not exact")
    if not _list_metadata_is_source_backed(document):
        raise ApplicationPolicyStageError("policy List metadata is not source-backed empty metadata")
    validate_applied_objects(desired, policy_row.stdout)
    bindings = []
    for row in document["items"]:
        metadata = row["metadata"]
        bindings.append(ApplicationPolicyBinding(row["kind"], metadata.get("namespace", ""),
                                                  metadata["name"], metadata["uid"],
                                                  metadata["resourceVersion"]))
    if len({row.uid for row in bindings}) != 18 or owned_identity.cluster_incarnation_uid in {row.uid for row in bindings}:
        raise ApplicationPolicyStageError("policy UIDs collide")
    for observation in observations[2:5]:
        absence = decode(observation.stdout)
        if (type(absence) is not dict or set(absence) not in ({"apiVersion", "kind", "items"},
                {"apiVersion", "kind", "metadata", "items"}) or absence["apiVersion"] != "v1"
                or absence["kind"] != "List" or absence["items"] != []
                or not _list_metadata_is_source_backed(absence)):
            raise ApplicationPolicyStageError("workload absence List is not exact")
    return raw, tuple(sorted(bindings)), policy_request_bytes(profile, workload)


@dataclass(frozen=True, slots=True)
class ApplicationPolicyStageProof:
    context: ExpectedContext
    expected_context_commitment: str
    profile: V3B2Profile
    workload: WorkloadIdentity
    rendered_objects: bytes
    owned_identity: OwnedIdentity
    raw_observations: bytes
    policy_request: bytes
    bindings: tuple[ApplicationPolicyBinding, ...]
    runtime_contract_complete: bool = False

    def __post_init__(self):
        if type(self.runtime_contract_complete) is not bool or self.runtime_contract_complete:
            raise ApplicationPolicyStageError("policy stage cannot complete runtime")
        if (type(self.raw_observations) is not bytes or not 1 <= len(self.raw_observations) <= _MAX_RAW
                or not self.raw_observations.endswith(b"\n")):
            raise ApplicationPolicyStageError("retained observation bytes are not canonical")
        if type(self.policy_request) is not bytes or not 1 <= len(self.policy_request) <= _MAX_RAW:
            raise ApplicationPolicyStageError("retained policy request is not bounded bytes")
        if (type(self.bindings) is not tuple or len(self.bindings) != 18
                or any(type(row) is not ApplicationPolicyBinding for row in self.bindings)):
            raise ApplicationPolicyStageError("retained policy bindings are not exact")
        for binding in self.bindings: binding.__post_init__()
        observations = _decode_raw(self.raw_observations)
        raw, bindings, request = _compute(self.context, self.expected_context_commitment, self.profile,
                                          self.workload, self.rendered_objects, self.owned_identity,
                                          observations)
        if raw != self.raw_observations or bindings != self.bindings or request != self.policy_request:
            raise ApplicationPolicyStageError("reconstructed policy proof differs")


def validate_application_policy_stage(*, context, expected_context_commitment, profile, workload,
                                      rendered_objects, owned_identity, observations):
    try:
        raw, bindings, request = _compute(context, expected_context_commitment, profile, workload,
                                          rendered_objects, owned_identity, observations)
        return ApplicationPolicyStageProof(context, expected_context_commitment, profile, workload,
                                           rendered_objects, owned_identity, raw, request, bindings)
    except ApplicationPolicyStageError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError) as error:
        raise ApplicationPolicyStageError("invalid policy-stage evidence") from error


__all__ = ("ApplicationPolicyBinding", "ApplicationPolicyStageError", "ApplicationPolicyStageProof",
           "application_policy_observation_specs", "policy_request_bytes",
           "validate_application_policy_stage")
