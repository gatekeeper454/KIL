"""Configuration-only proof for nine ReplicaSet-generated KIL service Pods.

Kubernetes v1.36.1 GetPodFromTemplate copies template metadata/spec and appends
the owner; getPodsPrefix uses the short valid ReplicaSet name plus '-'.
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/controller/controller_utils.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/controller/replicaset/replica_set.go

The ownership proof retains the entire raw source. Only status is excluded from
configuration comparison after checking root fields. This establishes no Ready,
runtime image identity, full status schema or full application completion.
IP uniqueness is limited to validated CNI annotation domains (nine generated
Pods and three direct drivers), not Node/status/platform network authority.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import re

from kil.v3b2_api_defaults import _equal, matches_configuration
from kil.v3b2_contracts import TRACK_NAMESPACES
from kil.v3b2_driver_pod_configuration import _precheck, _uid, _rv, _timestamp, _TOLERATIONS, _cni_annotations
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof

_NAMESPACES = tuple(sorted(namespace for _, namespace in TRACK_NAMESPACES))
_ROLES = ("authz", "envoy", "target")
_METADATA = {"name", "namespace", "generateName", "labels", "annotations", "ownerReferences",
             "uid", "resourceVersion", "generation", "creationTimestamp"}


class GeneratedKilPodConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True, order=True)
class GeneratedKilPodConfigurationBinding:
    namespace: str
    deployment_name: str
    replica_set_name: str
    name: str
    uid: str
    resource_version: str

    def __post_init__(self):
        if type(self.namespace) is not str or self.namespace not in _NAMESPACES or type(self.deployment_name) is not str or self.deployment_name not in _ROLES:
            raise GeneratedKilPodConfigurationError("binding role/namespace is not expected")
        for name in (self.replica_set_name, self.name):
            if type(name) is not str or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,252}", name) is None:
                raise GeneratedKilPodConfigurationError("binding generated name is invalid")
        _uid(self.uid); _rv(self.resource_version)


def _compute(ownership):
    if type(ownership) is not RuntimeOwnershipProof:
        raise GeneratedKilPodConfigurationError("ownership dependency must be exact")
    ownership.__post_init__()
    return _extract_configuration(ownership, driver_namespaces=_NAMESPACES)


def _extract_configuration(ownership, *, driver_namespaces):
    """Extract from phase-validated ownership; callers derive driver reservations."""
    rows = json.loads(ownership.runtime_objects)["items"]
    pods = {(row["metadata"]["namespace"], row["metadata"]["name"]): row for row in rows if row["kind"] == "Pod"}
    templates = {(row["metadata"]["namespace"], row["metadata"]["name"]): row["spec"]["template"]
                 for row in json.loads(ownership.rendered_objects)["items"] if row["kind"] == "Deployment"}
    selected = [binding for binding in ownership.deployment_ownership.bindings
                if (binding.namespace, binding.deployment_name) in templates]
    if len(selected) != 9 or any(len(binding.pods) != 1 for binding in selected):
        raise GeneratedKilPodConfigurationError("generated KIL Pod ownership set is not exact")
    ips, sandboxes = set(), {ownership.owned_identity.node_container_id}
    def reserve(annotations, spec):
        cni, ip, sandbox = _cni_annotations(annotations, spec, ownership.profile)
        if ip is not None:
            if ip in ips: raise GeneratedKilPodConfigurationError("CNI address collides with retained annotation domain")
            ips.add(ip)
        if sandbox is not None:
            if sandbox in sandboxes: raise GeneratedKilPodConfigurationError("CNI sandbox collides with retained runtime identity")
            sandboxes.add(sandbox)
        return cni
    for namespace in driver_namespaces:
        driver = pods[(namespace, "driver")]
        _precheck(driver, 0, [0])
        annotations, spec = driver["metadata"].get("annotations", {}), driver["spec"]
        if type(annotations) is not dict or type(spec) is not dict:
            raise GeneratedKilPodConfigurationError("driver CNI source paths are invalid")
        reserve(annotations, spec)
    bindings = []
    for binding in selected:
        name, uid, rv = binding.pods[0]
        row = pods[(binding.namespace, name)]
        _precheck(row, 0, [0])
        if set(row) not in ({"apiVersion", "kind", "metadata", "spec"},
                            {"apiVersion", "kind", "metadata", "spec", "status"}):
            raise GeneratedKilPodConfigurationError("generated Pod root includes unreviewed fields")
        template = templates[(binding.namespace, binding.deployment_name)]
        metadata = row["metadata"]
        allowed = _METADATA | {"managedFields"}
        if "finalizers" in template["metadata"]: allowed.add("finalizers")
        if not _METADATA <= set(metadata) or set(metadata) - allowed:
            raise GeneratedKilPodConfigurationError("generated metadata shape is not reviewed")
        _uid(metadata["uid"]); _rv(metadata["resourceVersion"]); _timestamp(metadata["creationTimestamp"])
        if (metadata["name"] != name or metadata["uid"] != uid or metadata["resourceVersion"] != rv
                or metadata["generateName"] != binding.replica_set_name + "-"
                or type(metadata["generation"]) is not int or metadata["generation"] != 1):
            raise GeneratedKilPodConfigurationError("generated metadata differs from owner-bound incarnation")
        owner = {"apiVersion": "apps/v1", "kind": "ReplicaSet", "name": binding.replica_set_name,
                 "uid": binding.replica_set_uid, "controller": True, "blockOwnerDeletion": True}
        if not _equal(metadata["ownerReferences"], [owner]):
            raise GeneratedKilPodConfigurationError("generated Pod owner is not the sole accepted ReplicaSet")
        spec = row["spec"]
        if (type(spec) is not dict or type(spec.get("priority")) is not int or spec["priority"] != 0
                or spec.get("preemptionPolicy") != "PreemptLowerPriority"
                or not _equal(spec.get("tolerations"), _TOLERATIONS) or "imagePullSecrets" in spec):
            raise GeneratedKilPodConfigurationError("generated Pod admission additions differ")
        annotations = metadata["annotations"]
        if type(annotations) is not dict: raise GeneratedKilPodConfigurationError("invalid annotation source")
        cni = reserve(annotations, spec)
        desired = {"apiVersion": "v1", "kind": "Pod", "metadata": deepcopy(template["metadata"]),
                   "spec": deepcopy(template["spec"])}
        desired["metadata"].update(name=name, namespace=binding.namespace,
                                    generateName=binding.replica_set_name + "-", ownerReferences=[owner])
        desired["metadata"]["labels"]["pod-template-hash"] = binding.pod_template_hash
        desired["metadata"]["annotations"].update(cni)
        desired["spec"].update(priority=0, preemptionPolicy="PreemptLowerPriority", tolerations=deepcopy(_TOLERATIONS))
        if "nodeName" in spec:
            node = ownership.owned_identity.kind_cluster + "-control-plane"
            if type(spec["nodeName"]) is not str or spec["nodeName"] != node:
                raise GeneratedKilPodConfigurationError("generated Pod scheduling differs from owned Node")
            desired["spec"]["nodeName"] = node
        projection = {key: value for key, value in row.items() if key != "status"}
        if not matches_configuration(desired, projection):
            raise GeneratedKilPodConfigurationError("generated configuration differs from independent template")
        bindings.append(GeneratedKilPodConfigurationBinding(binding.namespace, binding.deployment_name,
                         binding.replica_set_name, name, uid, rv))
    return tuple(sorted(bindings))


@dataclass(frozen=True, slots=True)
class GeneratedKilPodConfigurationProof:
    ownership: RuntimeOwnershipProof
    bindings: tuple[GeneratedKilPodConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise GeneratedKilPodConfigurationError("configuration cannot establish completion")
            if type(self.bindings) is not tuple or len(self.bindings) != 9:
                raise GeneratedKilPodConfigurationError("bindings must be an exact tuple of nine")
            for binding in self.bindings:
                if type(binding) is not GeneratedKilPodConfigurationBinding:
                    raise GeneratedKilPodConfigurationError("binding type must be exact")
                binding.__post_init__()
            if self.bindings != _compute(self.ownership):
                raise GeneratedKilPodConfigurationError("bindings differ from same-source reconstruction")
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, GeneratedKilPodConfigurationError): raise
            raise GeneratedKilPodConfigurationError("invalid generated configuration proof") from error


def validate_generated_kil_pod_configuration(*, ownership):
    """Validate exactly nine generated configurations, never runtime status/images."""
    try:
        return GeneratedKilPodConfigurationProof(ownership, _compute(ownership))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, GeneratedKilPodConfigurationError): raise
        raise GeneratedKilPodConfigurationError("invalid generated Pod source") from error
