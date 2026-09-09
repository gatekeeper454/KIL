"""Bounded apply-time direct-Pod configuration proof, not application completion.

Pinned admission rules: Kubernetes v1.36.1 priority and defaulttolerationseconds
plugins, plus core/v1 defaults (plan B.2). A caller supplies complete metadata
and spec projections, excluding status; it must not remove CNI annotations or
unknown metadata to obtain acceptance. The reviewed single-stack CNI ADD shape
is an equal nonempty podIP/podIPs pair, optionally with a sandbox containerID.
Calico writes this pair in one annotation patch before kubelet may write Pod IP
status; DELETE clears both IP strings and preserves the sandbox ID. Cleared or
partial shapes are rejected, and status/network/runtime joins remain later gates.
Source: https://github.com/projectcalico/calico/blob/v3.32.0/libcalico-go/lib/backend/k8s/resources/workloadendpoint.go
Optional managedFields and last-applied annotations use the existing reviewed
metadata validator and remain in retained bytes. Last-applied is bounded opaque
metadata, never desired-configuration authority. Global projection limits remain
stricter: depth 12, 4096 values per Pod, 64 entries per collection, 4096 characters
per string and 196608 total canonical bytes.
The collector/source-byte join and later ready-incarnation proof remain separate.
OwnedIdentity binds the reviewed single-node Kind context, not a fresh Node read.
"""
from copy import deepcopy
from dataclasses import dataclass
from ipaddress import IPv4Network
import json
import re

from kil.v3b2_api_defaults import _equal, matches_configuration
from kil.v3b2_contracts import V3B2Profile, TRACK_NAMESPACES
from kil.v3b2_driver_pod_admission import _precheck, _uid, _rv, _timestamp, _TOLERATIONS, _pod_ip
from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_manifests import WorkloadIdentity, render_objects

_NODE = "kil-v3-lab-control-plane"
_NAMESPACES = tuple(sorted(namespace for _, namespace in TRACK_NAMESPACES))
_MAX_PODS_BYTES = 196608
_METADATA = {"name", "namespace", "labels", "annotations", "uid", "resourceVersion",
             "generation", "creationTimestamp"}


class DriverPodConfigurationError(ValueError):
    """Configuration evidence does not meet this apply-time contract."""


def _canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _rows(pods):
    if type(pods) is not list or len(pods) != 3:
        raise DriverPodConfigurationError("expected an exact list of three Pod projections")
    for row in pods:
        if type(row) is not dict:
            raise DriverPodConfigurationError("Pod projection must be an exact dict")
        _precheck(row, 0, [0])
    raw = _canonical(pods)
    if len(raw) > _MAX_PODS_BYTES:
        raise DriverPodConfigurationError("Pod projections exceed byte bound")
    return raw


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DriverPodConfigurationError("duplicate JSON member")
        result[key] = value
    return result


def _cni_annotations(annotations, spec, profile):
    prefix = "cni.projectcalico.org/"
    cni = {key: value for key, value in annotations.items() if key.startswith(prefix)}
    if not cni:
        return {}, None, None
    pair = {prefix + "podIP", prefix + "podIPs"}
    if set(cni) not in (pair, pair | {prefix + "containerID"}):
        raise DriverPodConfigurationError("CNI annotation keys do not form the reviewed ADD shape")
    cidr = cni[prefix + "podIP"]
    if (type(cidr) is not str or not cidr.endswith("/32")
            or type(cni[prefix + "podIPs"]) is not str or cni[prefix + "podIPs"] != cidr):
        raise DriverPodConfigurationError("CNI IP pair must be one equal canonical IPv4 /32")
    ip = _pod_ip(cidr[:-3], IPv4Network(profile.pod_subnet))
    if spec.get("nodeName") != _NODE:
        raise DriverPodConfigurationError("CNI annotations require scheduling to the owned Node")
    sandbox = cni.get(prefix + "containerID")
    if prefix + "containerID" in cni and (
            type(sandbox) is not str or re.fullmatch(r"[0-9a-f]{64}", sandbox) is None):
        raise DriverPodConfigurationError("CNI sandbox ID must be nonempty lowercase hex64")
    return cni, ip, sandbox


@dataclass(frozen=True, slots=True, order=True)
class DriverPodConfigurationBinding:
    namespace: str
    name: str
    uid: str
    resource_version: str

    def __post_init__(self):
        if (type(self.namespace) is not str or self.namespace not in _NAMESPACES
                or type(self.name) is not str or self.name != "driver"):
            raise DriverPodConfigurationError("binding is not an expected driver identity")
        try:
            _uid(self.uid); _rv(self.resource_version)
        except ValueError as error:
            raise DriverPodConfigurationError("binding API identity is invalid") from error


def _compute(profile, workload, rendered_objects, owned_identity, pods):
    # Cardinality and structural bounds precede rendering, copying or comparison.
    _rows(pods)
    if (type(profile) is not V3B2Profile or type(workload) is not WorkloadIdentity
            or type(owned_identity) is not OwnedIdentity):
        raise DriverPodConfigurationError("expected dependency types must be exact")
    profile.__post_init__(); workload.__post_init__(); owned_identity.__post_init__()
    if any(getattr(owned_identity, key) is None for key in
           ("docker_host", "kind_cluster", "kubeconfig", "cluster_incarnation_uid", "node_container_id")):
        raise DriverPodConfigurationError("owned Kind identity must be complete")
    if type(rendered_objects) is not bytes or len(rendered_objects) > 2 * 1024 * 1024:
        raise DriverPodConfigurationError("rendered input must be bounded exact bytes")
    independently_rendered = render_objects(profile, workload)
    if rendered_objects != independently_rendered:
        raise DriverPodConfigurationError("rendered input differs from independent expectations")
    desired = {row["metadata"]["namespace"]: row
               for row in json.loads(independently_rendered)["items"] if row["kind"] == "Pod"}
    bindings, cni_ips, cni_sandboxes = [], set(), {owned_identity.node_container_id}
    for row in pods:
        if set(row) != {"apiVersion", "kind", "metadata", "spec"}:
            raise DriverPodConfigurationError("projection must contain only apiVersion/kind/metadata/spec; status is outside scope")
        metadata = row["metadata"]
        if (type(metadata) is not dict or not _METADATA <= set(metadata)
                or set(metadata) - _METADATA - {"managedFields"}):
            raise DriverPodConfigurationError("complete projected Pod metadata shape is unsupported")
        namespace = metadata["namespace"]
        if type(namespace) is not str or namespace not in desired:
            raise DriverPodConfigurationError("Pod namespace is not expected")
        annotations = metadata["annotations"]
        if type(annotations) is not dict:
            raise DriverPodConfigurationError("annotations must be exact dict")
        _uid(metadata["uid"]); _rv(metadata["resourceVersion"])
        _timestamp(metadata["creationTimestamp"])
        if type(metadata["generation"]) is not int or metadata["generation"] != 1:
            raise DriverPodConfigurationError("Pod generation must be exact one")
        spec = row["spec"]
        if type(spec) is not dict:
            raise DriverPodConfigurationError("Pod spec must be exact dict")
        if (type(spec.get("priority")) is not int or spec["priority"] != 0
                or spec.get("preemptionPolicy") != "PreemptLowerPriority"
                or not _equal(spec.get("tolerations"), _TOLERATIONS)):
            raise DriverPodConfigurationError("direct Pod admission defaults are not exact")
        if "imagePullSecrets" in spec:
            raise DriverPodConfigurationError("inherited imagePullSecrets are forbidden")
        cni, ip, sandbox = _cni_annotations(annotations, spec, profile)
        if ip is not None:
            if ip in cni_ips:
                raise DriverPodConfigurationError("CNI Pod IP collides with another driver")
            cni_ips.add(ip)
        if sandbox is not None:
            if sandbox in cni_sandboxes:
                raise DriverPodConfigurationError("CNI sandbox collides with retained runtime identity")
            cni_sandboxes.add(sandbox)
        admitted = deepcopy(desired[namespace])
        # Only the locally validated source-specific annotation values augment
        # independently rendered expectations; never strip arbitrary metadata.
        admitted["metadata"]["annotations"].update(cni)
        admitted["spec"].update(priority=0, preemptionPolicy="PreemptLowerPriority",
                                  tolerations=deepcopy(_TOLERATIONS))
        if "nodeName" in spec:
            if type(spec["nodeName"]) is not str or spec["nodeName"] != _NODE:
                raise DriverPodConfigurationError("scheduled Pod does not select the fixed owned Node")
            admitted["spec"]["nodeName"] = _NODE
        if not matches_configuration(admitted, row):
            raise DriverPodConfigurationError("Pod differs from independently rendered admitted configuration")
        bindings.append(DriverPodConfigurationBinding(namespace, metadata["name"],
                                                       metadata["uid"], metadata["resourceVersion"]))
    result = tuple(sorted(bindings))
    if (tuple(item.namespace for item in result) != _NAMESPACES
            or len({item.uid for item in result}) != 3):
        raise DriverPodConfigurationError("driver identities are duplicated or incomplete")
    if owned_identity.cluster_incarnation_uid in {item.uid for item in result}:
        raise DriverPodConfigurationError("driver UID collides with retained cluster namespace UID")
    return result


@dataclass(frozen=True, slots=True)
class DriverPodConfigurationProof:
    profile: V3B2Profile
    workload: WorkloadIdentity
    rendered_objects: bytes
    owned_identity: OwnedIdentity
    pods: bytes
    bindings: tuple[DriverPodConfigurationBinding, ...]
    runtime_contract_complete: bool = False

    def __post_init__(self):
        try:
            if type(self.runtime_contract_complete) is not bool or self.runtime_contract_complete:
                raise DriverPodConfigurationError("configuration cannot establish runtime completeness")
            if type(self.pods) is not bytes or not 1 <= len(self.pods) <= _MAX_PODS_BYTES:
                raise DriverPodConfigurationError("retained projections must be bounded bytes")
            if type(self.bindings) is not tuple or len(self.bindings) != 3:
                raise DriverPodConfigurationError("retained bindings must be an exact tuple of three")
            for binding in self.bindings:
                if type(binding) is not DriverPodConfigurationBinding:
                    raise DriverPodConfigurationError("retained binding type is invalid")
                binding.__post_init__()
            rows = json.loads(self.pods, object_pairs_hook=_pairs)
            if _rows(rows) != self.pods:
                raise DriverPodConfigurationError("retained projections are not canonical")
            computed = _compute(self.profile, self.workload, self.rendered_objects,
                                self.owned_identity, rows)
            if computed != self.bindings:
                raise DriverPodConfigurationError("retained bindings differ from replayed evidence")
        except (TypeError, ValueError, AttributeError, KeyError, RecursionError) as error:
            if isinstance(error, DriverPodConfigurationError): raise
            raise DriverPodConfigurationError("invalid configuration proof") from error


def validate_driver_pod_configuration(*, profile: V3B2Profile, workload: WorkloadIdentity,
                                      rendered_objects: bytes, owned_identity: OwnedIdentity,
                                      pods: list[dict]) -> DriverPodConfigurationProof:
    """Accept complete metadata/spec projections of exactly three direct Pods.

    This function does not collect observations, prove scheduling/readiness or
    status/CNI/runtime agreement, or complete application_apply. Do not strip
    unsupported fields to manufacture this projection.
    """
    try:
        raw = _rows(pods)
        bindings = _compute(profile, workload, rendered_objects, owned_identity, pods)
        return DriverPodConfigurationProof(profile, workload, rendered_objects,
                                            owned_identity, raw, bindings)
    except (TypeError, ValueError, AttributeError, KeyError, RecursionError) as error:
        if isinstance(error, DriverPodConfigurationError): raise
        raise DriverPodConfigurationError("invalid direct Pod configuration") from error
