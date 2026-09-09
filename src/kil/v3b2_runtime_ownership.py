"""Extract fixed ownership relations from one retained full runtime API List.

Only source paths consumed by the existing ownership validators are interpreted.
Other spec/status/metadata remain retained, not certified as full API or admitted
configuration. Deployment replicas come from spec, never status. Generated Pod
placement, images, CNI, platform joins, configuration continuity and readiness
remain separate. The three direct drivers are excluded only by exact fixed
identity, still participating in the global identity/UID collision domain.
"""
from dataclasses import dataclass
import json
import re

from kil.v3b2_contracts import V3B2Profile, TRACK_NAMESPACES
from kil.v3b2_deployment_ownership import DeploymentOwnershipProof, validate_deployment_ownership
from kil.v3b2_node_ownership import NodeOwnershipProof, validate_node_ownership
from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_manifests import WorkloadIdentity, render_objects

_MAX_BYTES = 8 * 1024 * 1024
_FAMILIES = {"Deployment", "ReplicaSet", "Pod", "Node", "DaemonSet"}


class RuntimeOwnershipError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise RuntimeOwnershipError("duplicate JSON member")
        result[key] = value
    return result


def _bounded(value, depth=0, budget=None):
    if budget is None: budget = [0]
    budget[0] += 1
    if depth > 32 or budget[0] > 200000: raise RuntimeOwnershipError("runtime JSON exceeds structural bound")
    if value is None or type(value) is bool: return
    if type(value) is int:
        if value.bit_length() > 64: raise RuntimeOwnershipError("unbounded integer")
        return
    if type(value) is str:
        if len(value) > 262144 or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise RuntimeOwnershipError("unbounded or invalid string")
        return
    if type(value) is list:
        if len(value) > 512: raise RuntimeOwnershipError("unbounded array")
        for item in value: _bounded(item, depth + 1, budget)
        return
    if type(value) is dict:
        if len(value) > 512 or any(type(key) is not str or not key or len(key) > 4096 for key in value):
            raise RuntimeOwnershipError("invalid object keys")
        for key, item in value.items():
            _bounded(key, depth + 1, budget); _bounded(item, depth + 1, budget)
        return
    raise RuntimeOwnershipError("non-JSON value")


def _document(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_BYTES:
        raise RuntimeOwnershipError("runtime List must be bounded exact bytes")
    document = json.loads(raw, object_pairs_hook=_pairs)
    if (type(document) is not dict or set(document) not in (
            {"apiVersion", "kind", "items"}, {"apiVersion", "kind", "items", "metadata"})
            or document["apiVersion"] != "v1" or document["kind"] != "List"
            or type(document["items"]) is not list or not 44 <= len(document["items"]) <= 512
            or ("metadata" in document and document["metadata"] != {"resourceVersion": ""})):
        raise RuntimeOwnershipError("runtime root is not a bounded API List")
    _bounded(document)
    return document["items"]


def _base(row, *, node=False):
    metadata = row["metadata"]
    result = {"apiVersion": row["apiVersion"], "kind": row["kind"],
              "name": metadata["name"], "uid": metadata["uid"], "resourceVersion": metadata["resourceVersion"]}
    if not node: result["namespace"] = metadata["namespace"]
    return result


def _owner(row):
    owners = row["metadata"].get("ownerReferences")
    if type(owners) is not list or len(owners) != 1 or type(owners[0]) is not dict:
        raise RuntimeOwnershipError("ownership requires exactly one metadata.ownerReferences record")
    return owners[0]


def _extract_ownership(profile, workload, rendered_objects, owned_identity, runtime_objects,
                       *, expected_direct_drivers):
    if type(expected_direct_drivers) is not int or expected_direct_drivers not in (0, 3):
        raise RuntimeOwnershipError("unreviewed ownership phase")
    rows = _document(runtime_objects)
    if (type(profile) is not V3B2Profile or type(workload) is not WorkloadIdentity
            or type(owned_identity) is not OwnedIdentity):
        raise RuntimeOwnershipError("expected dependency types must be exact")
    profile.__post_init__(); workload.__post_init__(); owned_identity.__post_init__()
    if any(getattr(owned_identity, field) is None for field in
           ("docker_host", "kind_cluster", "kubeconfig", "cluster_incarnation_uid", "node_container_id")):
        raise RuntimeOwnershipError("owned Kind identity is incomplete")
    if (type(rendered_objects) is not bytes or len(rendered_objects) > 2 * 1024 * 1024
            or rendered_objects != render_objects(profile, workload)):
        raise RuntimeOwnershipError("rendered expectations differ from independent inputs")
    node_name = owned_identity.kind_cluster + "-control-plane"
    indexed, uids = {}, set()
    families = {kind: [] for kind in _FAMILIES}
    for row in rows:
        if type(row) is not dict or type(row.get("metadata")) is not dict:
            raise RuntimeOwnershipError("runtime object metadata is invalid")
        metadata = row["metadata"]
        key = (row.get("apiVersion"), row.get("kind"), metadata.get("namespace", ""), metadata.get("name"))
        if (any(type(part) is not str or len(part) > 253 for part in key)
                or not all(key[i] for i in (0, 1, 3)) or key in indexed):
            raise RuntimeOwnershipError("runtime object identity is invalid or duplicated")
        uid, rv = metadata.get("uid"), metadata.get("resourceVersion")
        if (type(uid) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", uid) is None
                or type(rv) is not str or re.fullmatch(r"[1-9][0-9]{0,19}", rv) is None
                or int(rv) > 2**64 - 1 or uid in uids):
            raise RuntimeOwnershipError("runtime API UID/RV is invalid or UID duplicated")
        if ((uid == owned_identity.cluster_incarnation_uid) != (key == ("v1", "Namespace", "", "kube-system"))):
            raise RuntimeOwnershipError("cluster namespace UID does not match retained authority")
        indexed[key] = row; uids.add(uid)
        if key[1] in families: families[key[1]].append(row)
    if {kind: len(value) for kind, value in families.items()} != {
            "Deployment": 12, "ReplicaSet": 12, "Pod": 19 + expected_direct_drivers, "Node": 1, "DaemonSet": 2}:
        raise RuntimeOwnershipError("runtime ownership families are not exact")
    deployments, replicas, generated, daemon_pods, static_pods, direct = [], [], [], [], [], []
    for row in families["Deployment"]:
        deployments.append({**_base(row), "replicas": row["spec"]["replicas"],
                            "revision": row["metadata"]["annotations"]["deployment.kubernetes.io/revision"]})
    for row in families["ReplicaSet"]:
        replicas.append({**_base(row), "revision": row["metadata"]["annotations"]["deployment.kubernetes.io/revision"],
                         "podTemplateHash": row["metadata"]["labels"]["pod-template-hash"], "ownerReference": _owner(row)})
    namespaces = tuple(sorted(namespace for _, namespace in TRACK_NAMESPACES))
    for row in families["Pod"]:
        metadata = row["metadata"]
        if metadata.get("namespace") in namespaces and metadata["name"] == "driver":
            if row["apiVersion"] != "v1" or "ownerReferences" in metadata:
                raise RuntimeOwnershipError("direct driver must not have controller owners")
            direct.append(metadata["namespace"])
            continue
        owner = _owner(row)
        projection = {**_base(row), "ownerReference": owner}
        if owner.get("kind") == "ReplicaSet":
            generated.append({**projection, "podTemplateHash": metadata["labels"]["pod-template-hash"]})
        elif owner.get("kind") == "DaemonSet":
            daemon_pods.append({**projection, "nodeName": row["spec"]["nodeName"]})
        elif owner.get("kind") == "Node":
            annotations = metadata["annotations"]
            static_pods.append({**projection, "nodeName": row["spec"]["nodeName"],
                "component": metadata["labels"]["component"], "configSource": annotations["kubernetes.io/config.source"],
                "configHash": annotations["kubernetes.io/config.hash"], "mirrorHash": annotations["kubernetes.io/config.mirror"]})
        else:
            raise RuntimeOwnershipError("unreviewed generated Pod owner")
    if tuple(sorted(direct)) != (namespaces if expected_direct_drivers == 3 else ()):
        raise RuntimeOwnershipError("direct driver identity set is not exact")
    node = families["Node"][0]
    if node["metadata"]["name"] != node_name or "namespace" in node["metadata"]:
        raise RuntimeOwnershipError("Node is not the sole owned cluster Node")
    daemon_sets = [{**_base(row), "desiredNumberScheduled": row["status"]["desiredNumberScheduled"]}
                   for row in families["DaemonSet"]]
    deployment = validate_deployment_ownership(deployments=deployments, replica_sets=replicas,
                                               pods=generated, application_namespaces=namespaces)
    node_proof = validate_node_ownership(node=_base(node, node=True), daemon_sets=daemon_sets,
        daemon_pods=daemon_pods, static_pods=static_pods, cluster_name=owned_identity.kind_cluster)
    return deployment, node_proof


def _compute(profile, workload, rendered_objects, owned_identity, runtime_objects):
    return _extract_ownership(profile, workload, rendered_objects, owned_identity, runtime_objects,
                              expected_direct_drivers=3)


@dataclass(frozen=True, slots=True)
class RuntimeOwnershipProof:
    profile: V3B2Profile
    workload: WorkloadIdentity
    rendered_objects: bytes
    owned_identity: OwnedIdentity
    runtime_objects: bytes
    deployment_ownership: DeploymentOwnershipProof
    node_ownership: NodeOwnershipProof
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in
                   (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise RuntimeOwnershipError("ownership cannot establish full completion")
            if type(self.deployment_ownership) is not DeploymentOwnershipProof or type(self.node_ownership) is not NodeOwnershipProof:
                raise RuntimeOwnershipError("retained ownership proof types must be exact")
            self.deployment_ownership.__post_init__(); self.node_ownership.__post_init__()
            deployment, node = _compute(self.profile, self.workload, self.rendered_objects,
                                        self.owned_identity, self.runtime_objects)
            if deployment != self.deployment_ownership or node != self.node_ownership:
                raise RuntimeOwnershipError("ownership differs from same-source reconstruction")
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, RuntimeOwnershipError): raise
            raise RuntimeOwnershipError("invalid runtime ownership proof") from error


def validate_runtime_ownership(*, profile, workload, rendered_objects, owned_identity, runtime_objects):
    """Validate source-path ownership only; preserve all other raw evidence for later joins."""
    try:
        deployment, node = _compute(profile, workload, rendered_objects, owned_identity, runtime_objects)
        return RuntimeOwnershipProof(profile, workload, rendered_objects, owned_identity,
                                     runtime_objects, deployment, node)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, RuntimeOwnershipError): raise
        raise RuntimeOwnershipError("invalid runtime ownership observation") from error
