"""Closed admission and runtime identity proof for the three direct driver Pods."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv4Network
import json
import re

from kil.v3b2_api_defaults import _equal, configuration
from kil.v3b2_contracts import TRACK_NAMESPACES, V3B2Profile
from kil.v3b2_manifests import WorkloadIdentity, render_objects, validate_rendered_objects
from kil.v3b2_platform_endpoints import PlatformEndpointProof


_NODE = "kil-v3-lab-control-plane"
_NAMESPACES = tuple(sorted(namespace for _, namespace in TRACK_NAMESPACES))
_UID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_UINT64_MAX = 2**64 - 1
_TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_RUNTIME_CONTAINER = re.compile(r"containerd://([0-9a-f]{64})")
_POD_METADATA_KEYS = frozenset({
    "name", "namespace", "labels", "annotations", "uid", "resourceVersion",
    "generation", "creationTimestamp",
})
_STATUS_KEYS = frozenset({
    "phase", "hostIP", "podIP", "podIPs", "conditions", "containerStatuses",
})
_CONTAINER_STATUS_KEYS = frozenset({
    "name", "image", "imageID", "containerID", "ready", "started", "restartCount", "state",
})
_TOLERATIONS = [
    {"key": "node.kubernetes.io/not-ready", "operator": "Exists",
     "effect": "NoExecute", "tolerationSeconds": 300},
    {"key": "node.kubernetes.io/unreachable", "operator": "Exists",
     "effect": "NoExecute", "tolerationSeconds": 300},
]


class DriverPodAdmissionError(ValueError):
    """The directly applied driver Pod set is not the admitted runtime set."""


def _closed(value: object, keys: frozenset[str], label: str) -> dict:
    if (type(value) is not dict or len(value) != len(keys)
            or any(type(key) is not str for key in value) or set(value) != keys):
        raise DriverPodAdmissionError(f"{label} shape is not exact")
    return value


def _text(label: str, value: object, maximum: int = 253) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise DriverPodAdmissionError(f"{label} must be an exact bounded string")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise DriverPodAdmissionError(f"{label} contains a surrogate")
    return value


def _uid(value: object) -> str:
    result = _text("UID", value, 128)
    if _UID.fullmatch(result) is None:
        raise DriverPodAdmissionError("UID is not a bounded API identity")
    return result


def _rv(value: object) -> str:
    result = _text("resourceVersion", value, 20)
    if (not result.isascii() or not result.isdigit() or result.startswith("0")
            or int(result) > _UINT64_MAX):
        raise DriverPodAdmissionError("resourceVersion is not a canonical positive uint64")
    return result


def _timestamp(value: object) -> str:
    result = _text("creationTimestamp", value, 40)
    if _TIMESTAMP.fullmatch(result) is None:
        raise DriverPodAdmissionError("creationTimestamp is not canonical UTC RFC3339")
    try:
        datetime.fromisoformat(result[:-1] + "+00:00")
    except ValueError as error:
        raise DriverPodAdmissionError("creationTimestamp is not a calendar timestamp") from error
    return result


def _precheck(value: object, depth: int, budget: list[int]) -> None:
    budget[0] += 1
    if depth > 12 or budget[0] > 4096:
        raise DriverPodAdmissionError("projection exceeds its structural bound")
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        _text("projection string", value, 4096) if value else None
        return
    if type(value) is list:
        if len(value) > 64:
            raise DriverPodAdmissionError("projection list exceeds its bound")
        for item in value: _precheck(item, depth + 1, budget)
        return
    if type(value) is dict:
        if len(value) > 64 or any(type(key) is not str or not key or len(key) > 256 for key in value):
            raise DriverPodAdmissionError("projection object exceeds its bound")
        for item in value.values(): _precheck(item, depth + 1, budget)
        return
    raise DriverPodAdmissionError("projection contains a non-JSON value")


def _pod_ip(value: object, network: IPv4Network) -> str:
    text = _text("Pod IP", value, 15)
    try:
        address = IPv4Address(text)
    except ValueError as error:
        raise DriverPodAdmissionError("Pod IP is not IPv4") from error
    if str(address) != text or address not in network or address in {network.network_address, network.broadcast_address}:
        raise DriverPodAdmissionError("Pod IP is not canonical and usable in the Pod CIDR")
    return text


def _revalidate_dependencies(profile: object, workload: object,
                             platform: object) -> tuple[V3B2Profile, WorkloadIdentity, PlatformEndpointProof]:
    if type(profile) is not V3B2Profile or type(workload) is not WorkloadIdentity:
        raise DriverPodAdmissionError("profile and workload types must be exact")
    if type(platform) is not PlatformEndpointProof:
        raise DriverPodAdmissionError("platform endpoint proof type must be exact")
    try:
        profile.__post_init__(); workload.__post_init__(); platform.__post_init__()
    except (TypeError, ValueError, UnicodeError, AttributeError) as error:
        raise DriverPodAdmissionError("an accepted dependency no longer validates") from error
    if platform.node_name != _NODE:
        raise DriverPodAdmissionError("platform proof is for another Node")
    return profile, workload, platform


def _desired_drivers(rendered: object, profile: V3B2Profile,
                     workload: WorkloadIdentity) -> dict[str, dict]:
    if type(rendered) is bytes:
        if len(rendered) > 2 * 1024 * 1024:
            raise DriverPodAdmissionError("rendered manifest exceeds its byte bound")
        expected_bytes = render_objects(profile, workload)
        if rendered != expected_bytes:
            raise DriverPodAdmissionError("rendered bytes differ from the canonical reviewed output")
        # Only parse the renderer-owned bounded value after byte equality; an
        # attacker-controlled JSON parser traversal never occurs on this path.
        document = json.loads(expected_bytes)
    elif type(rendered) is dict:
        _precheck(rendered, 0, [0])
        document = deepcopy(rendered)
    else:
        raise DriverPodAdmissionError("rendered manifest must be exact bytes or dict")
    _precheck(document, 0, [0])
    validate_rendered_objects(document, profile, workload)
    # Re-rendering makes the desired input source-bound, rather than merely a
    # second internally consistent manifest supplied by the caller.
    if document != json.loads(render_objects(profile, workload)):
        raise DriverPodAdmissionError("rendered manifest differs from the reviewed renderer")
    drivers = {item["metadata"]["namespace"]: item for item in document["items"]
               if item["apiVersion"] == "v1" and item["kind"] == "Pod"
               and item["metadata"]["name"] == "driver"}
    if tuple(sorted(drivers)) != _NAMESPACES:
        raise DriverPodAdmissionError("rendered driver Pod set is not exact")
    return drivers


@dataclass(frozen=True, slots=True, order=True)
class DriverPodBinding:
    namespace: str
    name: str
    run_id: str
    kil_image_id: str
    kil_config_digest: str
    uid: str
    resource_version: str
    generation: int
    creation_timestamp: str
    pod_ip: str
    cni_sandbox_id: str
    app_container_id: str

    def __post_init__(self) -> None:
        if (type(self.namespace) is not str or type(self.name) is not str
                or self.namespace not in _NAMESPACES or self.name != "driver"):
            raise DriverPodAdmissionError("binding identity is not a reviewed driver Pod")
        try:
            WorkloadIdentity(self.run_id, self.kil_image_id,
                             "invalid@sha256:" + "0" * 64)
        except ValueError as error:
            raise DriverPodAdmissionError("binding workload identity is invalid") from error
        if type(self.kil_config_digest) is not str or _SHA256.fullmatch(self.kil_config_digest) is None:
            raise DriverPodAdmissionError("binding KIL config digest is invalid")
        _uid(self.uid); _rv(self.resource_version); _timestamp(self.creation_timestamp)
        if type(self.generation) is not int or self.generation != 1:
            raise DriverPodAdmissionError("driver generation must be exact one")
        _pod_ip(self.pod_ip, IPv4Network("10.244.0.0/16"))
        if type(self.cni_sandbox_id) is not str or _HEX64.fullmatch(self.cni_sandbox_id) is None:
            raise DriverPodAdmissionError("CNI sandbox identity is not lowercase hex")
        match = _RUNTIME_CONTAINER.fullmatch(self.app_container_id) if type(self.app_container_id) is str else None
        if match is None or match.group(1) == self.cni_sandbox_id:
            raise DriverPodAdmissionError("app container identity is invalid or aliases the sandbox")


@dataclass(frozen=True, slots=True)
class DriverPodAdmissionProof:
    node_name: str
    node_uid: str
    node_resource_version: str
    node_internal_ip: str
    workload: WorkloadIdentity
    expected_kil_config_digest: str
    platform_endpoints: PlatformEndpointProof
    bindings: tuple[DriverPodBinding, ...]
    runtime_contract_complete: bool = False

    def __post_init__(self) -> None:
        if type(self.node_name) is not str or self.node_name != _NODE:
            raise DriverPodAdmissionError("proof Node is not reviewed")
        _uid(self.node_uid); _rv(self.node_resource_version)
        _text("Node InternalIP", self.node_internal_ip, 15)
        if type(self.workload) is not WorkloadIdentity:
            raise DriverPodAdmissionError("retained workload type is not exact")
        if (type(self.expected_kil_config_digest) is not str
                or _SHA256.fullmatch(self.expected_kil_config_digest) is None):
            raise DriverPodAdmissionError("retained KIL config digest is invalid")
        if type(self.platform_endpoints) is not PlatformEndpointProof:
            raise DriverPodAdmissionError("retained platform proof type is not exact")
        try:
            self.workload.__post_init__(); self.platform_endpoints.__post_init__()
        except (TypeError, ValueError, UnicodeError, AttributeError) as error:
            raise DriverPodAdmissionError("a retained dependency no longer validates") from error
        if ((self.node_name, self.node_uid, self.node_resource_version,
             self.node_internal_ip) !=
                (self.platform_endpoints.node_name, self.platform_endpoints.node_uid,
                 self.platform_endpoints.node_resource_version,
                 self.platform_endpoints.node_internal_ip)):
            raise DriverPodAdmissionError("retained Node authority differs from platform proof")
        if (type(self.bindings) is not tuple or len(self.bindings) != 3
                or any(type(item) is not DriverPodBinding for item in self.bindings)):
            raise DriverPodAdmissionError("proof bindings are not exact")
        for item in self.bindings: item.__post_init__()
        if (self.bindings != tuple(sorted(self.bindings))
                or tuple(item.namespace for item in self.bindings) != _NAMESPACES):
            raise DriverPodAdmissionError("proof bindings are not canonical")
        if any((item.run_id, item.kil_image_id, item.kil_config_digest)
               != (self.workload.run_id, self.workload.kil_image_id,
                   self.expected_kil_config_digest)
               for item in self.bindings):
            raise DriverPodAdmissionError("bindings differ from retained workload identity")
        for attribute in ("uid", "pod_ip", "cni_sandbox_id", "app_container_id"):
            if len({getattr(item, attribute) for item in self.bindings}) != 3:
                raise DriverPodAdmissionError(f"proof {attribute} values collide")
        container_hex = [item.app_container_id.removeprefix("containerd://")
                         for item in self.bindings]
        if len(set(container_hex + [item.cni_sandbox_id for item in self.bindings])) != 6:
            raise DriverPodAdmissionError("sandbox and app container identity domains collide")
        retained_uids = set(self.platform_endpoints.dependency_uids)
        retained_ips = {self.platform_endpoints.node_internal_ip}
        retained_ips.update(item.address for item in self.platform_endpoints.coredns_pods)
        for item in self.platform_endpoints.bindings:
            retained_uids.update((item.service_uid, item.endpoints_uid,
                                  item.endpoint_slice_uid))
            retained_ips.add(item.cluster_ip)
        if {item.uid for item in self.bindings} & retained_uids:
            raise DriverPodAdmissionError("proof driver UIDs collide with retained platform identities")
        if {item.pod_ip for item in self.bindings} & retained_ips:
            raise DriverPodAdmissionError("proof driver addresses collide with retained platform addresses")
        if type(self.runtime_contract_complete) is not bool or self.runtime_contract_complete:
            raise DriverPodAdmissionError("driver admission cannot complete runtime readiness")


def _validate_pod(row: dict, desired: dict, platform: PlatformEndpointProof,
                  workload: WorkloadIdentity, expected_kil_config_digest: str,
                  network: IPv4Network) -> DriverPodBinding:
    metadata = _closed(row.get("metadata"), _POD_METADATA_KEYS, "Pod metadata")
    desired_metadata = desired["metadata"]
    if (metadata["name"] != "driver" or metadata["namespace"] != desired_metadata["namespace"]
            or metadata["labels"] != desired_metadata["labels"]):
        raise DriverPodAdmissionError("Pod metadata identity or labels differ from desired")
    uid, rv = _uid(metadata["uid"]), _rv(metadata["resourceVersion"])
    if type(metadata["generation"]) is not int or metadata["generation"] != 1:
        raise DriverPodAdmissionError("Pod generation must be exact one")
    stamp = _timestamp(metadata["creationTimestamp"])
    annotations = metadata["annotations"]
    expected_annotation_keys = set(desired_metadata["annotations"]) | {
        "cni.projectcalico.org/containerID", "cni.projectcalico.org/podIP",
        "cni.projectcalico.org/podIPs",
    }
    if type(annotations) is not dict or set(annotations) != expected_annotation_keys:
        raise DriverPodAdmissionError("Pod annotations are not the exact desired and Calico set")
    if annotations["kil.dev/run-id"] != workload.run_id:
        raise DriverPodAdmissionError("Pod run annotation differs")
    sandbox = annotations["cni.projectcalico.org/containerID"]
    if type(sandbox) is not str or _HEX64.fullmatch(sandbox) is None:
        raise DriverPodAdmissionError("Calico containerID is not a bare lowercase sandbox identity")

    spec = row.get("spec")
    if type(spec) is not dict:
        raise DriverPodAdmissionError("Pod spec must be an exact dict")
    if spec.get("priority") != 0 or type(spec.get("priority")) is not int:
        raise DriverPodAdmissionError("driver priority is not exact zero")
    if spec.get("preemptionPolicy") != "PreemptLowerPriority" or spec.get("nodeName") != platform.node_name:
        raise DriverPodAdmissionError("driver scheduling admission differs")
    if spec.get("tolerations") != _TOLERATIONS:
        raise DriverPodAdmissionError("driver tolerations are not the exact default pair")
    if "imagePullSecrets" in spec:
        raise DriverPodAdmissionError("driver Pod must not inherit imagePullSecrets")
    admitted = deepcopy(desired)
    admitted["spec"].update({"priority": 0, "preemptionPolicy": "PreemptLowerPriority",
                             "nodeName": platform.node_name, "tolerations": deepcopy(_TOLERATIONS)})
    actual_static = deepcopy(row)
    actual_static["metadata"]["annotations"] = deepcopy(desired_metadata["annotations"])
    if not _equal(configuration(actual_static), configuration(admitted)):
        raise DriverPodAdmissionError("admitted Pod spec differs from exact normalized desired")

    status = _closed(row.get("status"), _STATUS_KEYS, "Pod status")
    if status["phase"] != "Running" or status["hostIP"] != platform.node_internal_ip:
        raise DriverPodAdmissionError("Pod phase or hostIP differs")
    pod_ip = _pod_ip(status["podIP"], network)
    if status["podIPs"] != [{"ip": pod_ip}]:
        raise DriverPodAdmissionError("Pod status address set is not exact")
    cidr = pod_ip + "/32"
    if (annotations["cni.projectcalico.org/podIP"] != cidr
            or annotations["cni.projectcalico.org/podIPs"] != cidr):
        raise DriverPodAdmissionError("Calico annotations disagree with canonical status address")
    if status["conditions"] != [{"type": "Ready", "status": "True"}]:
        raise DriverPodAdmissionError("Pod Ready condition is not exact true")
    statuses = status["containerStatuses"]
    if type(statuses) is not list or len(statuses) != 1:
        raise DriverPodAdmissionError("driver must have exactly one container status")
    runtime = _closed(statuses[0], _CONTAINER_STATUS_KEYS, "container status")
    desired_container = desired["spec"]["containers"][0]
    if (runtime["name"] != "driver" or runtime["image"] != desired_container["image"]
            or runtime["imageID"] != expected_kil_config_digest or runtime["ready"] is not True
            or runtime["started"] is not True or type(runtime["restartCount"]) is not int
            or runtime["restartCount"] != 0):
        raise DriverPodAdmissionError("driver container runtime state differs")
    state = _closed(runtime["state"], frozenset({"running"}), "container state")
    running = _closed(state["running"], frozenset({"startedAt"}), "running state")
    _timestamp(running["startedAt"])
    container_id = runtime["containerID"]
    match = _RUNTIME_CONTAINER.fullmatch(container_id) if type(container_id) is str else None
    if match is None or match.group(1) == sandbox:
        raise DriverPodAdmissionError("runtime app container identity is invalid or aliases sandbox")
    return DriverPodBinding(metadata["namespace"], "driver", workload.run_id,
                            workload.kil_image_id, expected_kil_config_digest,
                            uid, rv, 1, stamp, pod_ip, sandbox, container_id)


def validate_driver_pod_admission(*, profile: V3B2Profile, workload: WorkloadIdentity,
                                  expected_kil_config_digest: str,
                                  rendered_objects: bytes | dict,
                                  platform_endpoints: PlatformEndpointProof,
                                  pods: list[dict]) -> DriverPodAdmissionProof:
    """Validate exact bounded projections of the three direct Pods; never templates.

    Callers must project every field named by this contract from the API object;
    these records intentionally are not accepted as arbitrary full Pod objects.
    The expected KIL config digest is independent accepted-content authority and
    must never be derived from a candidate Pod.  This slice does not establish
    the later CRI image-reference chain or complete runtime readiness.
    """
    try:
        if type(pods) is not list or len(pods) != 3:
            raise DriverPodAdmissionError("pods must be an exact list of three records")
        for row in pods:
            if type(row) is not dict: raise DriverPodAdmissionError("Pod records must be exact dicts")
            _precheck(row, 0, [0])
        checked_profile, checked_workload, platform = _revalidate_dependencies(
            profile, workload, platform_endpoints,
        )
        if (type(expected_kil_config_digest) is not str
                or _SHA256.fullmatch(expected_kil_config_digest) is None):
            raise DriverPodAdmissionError("expected KIL config digest must be canonical sha256")
        desired = _desired_drivers(rendered_objects, checked_profile, checked_workload)
        by_namespace = {}
        bindings = []
        network = IPv4Network(checked_profile.pod_subnet)
        for row in pods:
            namespace = row.get("metadata", {}).get("namespace")
            if type(namespace) is not str or namespace not in desired or namespace in by_namespace:
                raise DriverPodAdmissionError("observed driver identities are unexpected or duplicated")
            by_namespace[namespace] = row
            bindings.append(_validate_pod(row, desired[namespace], platform,
                                          checked_workload,
                                          expected_kil_config_digest, network))
        if tuple(sorted(by_namespace)) != _NAMESPACES:
            raise DriverPodAdmissionError("observed driver Pod set is incomplete")
        result = tuple(sorted(bindings))
        dependency_ips = {platform.node_internal_ip}
        dependency_ips.update(item.address for item in platform.coredns_pods)
        dependency_ips.update(item.cluster_ip for item in platform.bindings)
        if {item.uid for item in result} & set(platform.dependency_uids):
            raise DriverPodAdmissionError("driver UIDs collide with dependency identities")
        platform_binding_uids = set()
        for item in platform.bindings:
            platform_binding_uids.update((item.service_uid, item.endpoints_uid,
                                          item.endpoint_slice_uid))
        if {item.uid for item in result} & platform_binding_uids:
            raise DriverPodAdmissionError("driver UIDs collide with platform endpoint resources")
        if {item.pod_ip for item in result} & dependency_ips:
            raise DriverPodAdmissionError("driver addresses collide with dependency addresses")
        return DriverPodAdmissionProof(platform.node_name, platform.node_uid,
                                       platform.node_resource_version,
                                       platform.node_internal_ip, checked_workload,
                                       expected_kil_config_digest, platform,
                                       result, False)
    except DriverPodAdmissionError:
        raise
    except (TypeError, ValueError, UnicodeError, OverflowError, AttributeError,
            KeyError, IndexError, json.JSONDecodeError) as error:
        raise DriverPodAdmissionError("driver Pod admission evidence is malformed") from error


__all__ = ("DriverPodAdmissionError", "DriverPodBinding",
           "DriverPodAdmissionProof", "validate_driver_pod_admission")
