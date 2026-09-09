"""Same-source runtime incarnation/image joins for the twelve KIL Pods.

Known optional ContainerStatus fields are retained in the ownership raw List but
only outer-typed and bounded here.  They do not establish resource allocation,
user, mount, or full status-schema claims.  Fresh restart-zero containers admit
only an absent or empty ``lastState``.
"""
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv4Network
import json, re
from pathlib import Path

from kil.v3b2_generated_kil_pod_configuration import GeneratedKilPodConfigurationProof
from kil.v3b2_runtime_endpoints import RuntimeEndpointsProof
from kil.v3b2_node_image_references import NodeImageReferenceProof
from kil.v3b2_driver_pod_configuration import DriverPodConfigurationProof, validate_driver_pod_configuration

_HEX = re.compile(r"[0-9a-f]{64}")
_CID = re.compile(r"containerd://([0-9a-f]{64})")
_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z")
_CONTAINER_STATUS_REQUIRED = {"name","image","imageID","containerID","ready","started","restartCount","state"}
_CONTAINER_STATUS_OPTIONAL = {"lastState","allocatedResources","resources","volumeMounts","user",
                              "allocatedResourcesStatus","stopSignal"}

class KilPodRuntimeError(ValueError): pass

def _exact(value, keys, label):
    if type(value) is not dict or set(value) != keys:
        raise KilPodRuntimeError(label + " shape is not exact")
    return value

def _time(value):
    if type(value) is not str or _TIME.fullmatch(value) is None:
        raise KilPodRuntimeError("running startedAt is invalid")
    datetime.fromisoformat(value[:-1] + "+00:00")
    return value

def _ip(value, network):
    if type(value) is not str:
        raise KilPodRuntimeError("Pod IP type is invalid")
    address = IPv4Address(value)
    if str(address) != value or address not in network or address in {network.network_address, network.broadcast_address}:
        raise KilPodRuntimeError("Pod IP is not canonical usable address")
    return value

def _container_status(value):
    if (type(value) is not dict or not _CONTAINER_STATUS_REQUIRED <= set(value)
            or set(value) - _CONTAINER_STATUS_REQUIRED - _CONTAINER_STATUS_OPTIONAL):
        raise KilPodRuntimeError("container status shape is not source-known")
    if "lastState" in value and (type(value["lastState"]) is not dict or value["lastState"] != {}):
        raise KilPodRuntimeError("fresh running container lastState must be absent or empty")
    for key in ("allocatedResources", "resources", "user"):
        if key in value and type(value[key]) is not dict:
            raise KilPodRuntimeError(key + " must be an exact object")
    for key in ("volumeMounts", "allocatedResourcesStatus"):
        if key in value and type(value[key]) is not list:
            raise KilPodRuntimeError(key + " must be an exact array")
    if ("stopSignal" in value and (type(value["stopSignal"]) is not str
            or len(value["stopSignal"]) > 64)):
        raise KilPodRuntimeError("stopSignal must be a bounded exact string")
    return {key:value[key] for key in _CONTAINER_STATUS_REQUIRED}

@dataclass(frozen=True, slots=True, order=True)
class KilPodRuntimeBinding:
    namespace: str; role: str; name: str; uid: str; resource_version: str
    pod_ip: str; cni_sandbox_id: str; app_container_id: str
    runtime_image: str; image_ref: str; started_at: str
    def __post_init__(self):
        from kil.v3b2_driver_pod_admission import _uid, _rv
        if any(type(x) is not str or not x for x in (self.namespace,self.role,self.name,self.runtime_image,self.image_ref)):
            raise KilPodRuntimeError("binding strings are invalid")
        if self.role not in {"driver","authz","envoy","target"}: raise KilPodRuntimeError("role invalid")
        _uid(self.uid); _rv(self.resource_version); _ip(self.pod_ip, IPv4Network("10.244.0.0/16")); _time(self.started_at)
        if type(self.cni_sandbox_id) is not str or _HEX.fullmatch(self.cni_sandbox_id) is None: raise KilPodRuntimeError("sandbox invalid")
        match = _CID.fullmatch(self.app_container_id) if type(self.app_container_id) is str else None
        if match is None or match.group(1) == self.cni_sandbox_id: raise KilPodRuntimeError("container identity invalid")

def _compute(configuration, endpoints, node_images):
    if (type(configuration) is not GeneratedKilPodConfigurationProof or type(endpoints) is not RuntimeEndpointsProof
            or type(node_images) is not NodeImageReferenceProof): raise KilPodRuntimeError("dependency types are not exact")
    configuration.__post_init__(); endpoints.__post_init__(); node_images.__post_init__()
    ownership = configuration.ownership
    if ownership != endpoints.ownership or node_images.identity != ownership.owned_identity:
        raise KilPodRuntimeError("dependencies do not retain the same runtime authority")
    rows = json.loads(ownership.runtime_objects)["items"]
    pods = [row for row in rows if row["kind"] == "Pod" and row["metadata"].get("namespace", "").startswith("kil-")]
    if len(pods) != 12: raise KilPodRuntimeError("KIL Pod set must be exactly twelve")
    drivers = []
    for row in pods:
        if row["metadata"]["name"] == "driver":
            if set(row) not in ({"apiVersion","kind","metadata","spec"},{"apiVersion","kind","metadata","spec","status"}):
                raise KilPodRuntimeError("driver root is open")
            drivers.append({key:value for key,value in row.items() if key != "status"})
    driver_proof = validate_driver_pod_configuration(profile=ownership.profile, workload=ownership.workload,
        rendered_objects=ownership.rendered_objects, owned_identity=ownership.owned_identity, pods=drivers)
    expected = {(b.namespace,b.name):(b.deployment_name,b.uid,b.resource_version) for b in configuration.bindings}
    expected.update({(b.namespace,b.name):("driver",b.uid,b.resource_version) for b in driver_proof.bindings})
    return driver_proof, _extract_runtime_bindings(ownership, node_images, endpoints.platform_endpoints,
                                                 endpoints.kil_endpoints, expected)


def _extract_runtime_bindings(ownership, node_images, platform_endpoints, kil_endpoints, expected):
    """Join raw Pods against phase-derived configuration and endpoint expectations."""
    if type(node_images) is not NodeImageReferenceProof:
        raise KilPodRuntimeError("node image dependency type is not exact")
    node_images.__post_init__()
    if node_images.identity != ownership.owned_identity:
        raise KilPodRuntimeError("node images do not retain the same runtime authority")
    if node_images.docker_config != str(Path(ownership.owned_identity.kubeconfig).parent / "docker-config"):
        raise KilPodRuntimeError("node image Docker configuration is outside owned authority")
    workload = ownership.workload
    images = {binding.expected.role: binding for binding in node_images.bindings}
    if (images["kil"].expected.target_digest != workload.kil_image_id
            or images["envoy"].expected.query_reference != workload.envoy_image_digest):
        raise KilPodRuntimeError("node image targets differ from independent workload")
    rows = json.loads(ownership.runtime_objects)["items"]
    pods = [row for row in rows if row["kind"] == "Pod" and row["metadata"].get("namespace", "").startswith("kil-")]
    if len(pods) != len(expected) or {(r['metadata']['namespace'],r['metadata']['name']) for r in pods} != set(expected):
        raise KilPodRuntimeError("KIL Pod set differs from phase-derived expectations")
    endpoint = {(b.namespace,b.pod_name):b for b in kil_endpoints.bindings}
    node_ip = platform_endpoints.node_internal_ip
    reserved_ips = {node_ip, *(p.address for p in platform_endpoints.coredns_pods)}
    reserved_ips.update(b.cluster_ip for b in platform_endpoints.bindings)
    reserved_ips.update(b.service_cluster_ip for b in kil_endpoints.bindings)
    identities = {ownership.owned_identity.node_container_id}; bindings=[]
    for row in pods:
        metadata,status=row["metadata"],row["status"]; key=(metadata["namespace"],metadata["name"])
        if key not in expected: raise KilPodRuntimeError("unexpected KIL Pod")
        role,uid,rv=expected[key]
        if (metadata["uid"],metadata["resourceVersion"]) != (uid,rv): raise KilPodRuntimeError("Pod incarnation changed")
        if type(status) is not dict or any(key in status for key in ("initContainerStatuses", "ephemeralContainerStatuses")):
            raise KilPodRuntimeError("unsupported container status family is present")
        conditions=status["conditions"]
        if (type(conditions) is not list or any(type(item) is not dict
                or type(item.get("type")) is not str or type(item.get("status")) is not str
                for item in conditions)):
            raise KilPodRuntimeError("Pod conditions are not exact typed records")
        ready=[x for x in conditions if x["type"]=="Ready"]
        if len(ready)!=1 or ready[0].get("status")!="True": raise KilPodRuntimeError("Ready condition is not exact")
        if status.get("phase")!="Running" or status.get("hostIP")!=node_ip: raise KilPodRuntimeError("Pod runtime placement is invalid")
        ip=_ip(status.get("podIP"),IPv4Network("10.244.0.0/16"))
        if status.get("podIPs") != [{"ip":ip}]: raise KilPodRuntimeError("Pod IP status is not exact single-stack")
        annotations=metadata["annotations"]; cid=annotations.get("cni.projectcalico.org/containerID")
        if (annotations.get("cni.projectcalico.org/podIP") != ip+"/32"
                or annotations.get("cni.projectcalico.org/podIPs") != ip+"/32"
                or type(cid) is not str or _HEX.fullmatch(cid) is None): raise KilPodRuntimeError("Calico ADD identity differs")
        statuses=status.get("containerStatuses")
        if type(statuses) is not list or len(statuses)!=1: raise KilPodRuntimeError("container status cardinality differs")
        cs=_container_status(statuses[0])
        if cs["name"] != role or cs["ready"] is not True or cs["started"] is not True or type(cs["restartCount"]) is not int or cs["restartCount"] != 0:
            raise KilPodRuntimeError("container state booleans differ")
        running=_exact(cs["state"],{"running"},"container state")["running"]
        started=_time(_exact(running,{"startedAt"},"running state")["startedAt"])
        image=images["envoy" if role=="envoy" else "kil"]
        if cs["image"] != image.runtime_image or cs["imageID"] != image.image_ref: raise KilPodRuntimeError("runtime image chain differs")
        binding=KilPodRuntimeBinding(key[0],role,key[1],uid,rv,ip,cid,cs["containerID"],cs["image"],cs["imageID"],started)
        if ip in reserved_ips or cid in identities or binding.app_container_id.removeprefix("containerd://") in identities:
            raise KilPodRuntimeError("runtime address or identity collides")
        reserved_ips.add(ip); identities.update((cid,binding.app_container_id.removeprefix("containerd://")))
        if role != "driver":
            joined=endpoint.get(key)
            if joined is None or (joined.pod_uid,joined.pod_resource_version,joined.pod_ip)!=(uid,rv,ip): raise KilPodRuntimeError("endpoint Pod join differs")
        bindings.append(binding)
    return tuple(sorted(bindings))

@dataclass(frozen=True, slots=True)
class KilPodRuntimeProof:
    configuration: GeneratedKilPodConfigurationProof; endpoints: RuntimeEndpointsProof; node_images: NodeImageReferenceProof
    driver_configuration: object; bindings: tuple[KilPodRuntimeBinding,...]
    runtime_contract_complete: bool=False; full_application_contract_complete: bool=False
    def __post_init__(self):
        if self.runtime_contract_complete is not False or self.full_application_contract_complete is not False: raise KilPodRuntimeError("proof cannot complete runtime")
        if type(self.driver_configuration) is not DriverPodConfigurationProof or type(self.bindings) is not tuple or len(self.bindings) != 12 or any(type(row) is not KilPodRuntimeBinding for row in self.bindings):
            raise KilPodRuntimeError("retained proof fields are not exact")
        self.driver_configuration.__post_init__()
        for row in self.bindings: row.__post_init__()
        driver,bindings=_compute(self.configuration,self.endpoints,self.node_images)
        if self.driver_configuration != driver or self.bindings != bindings: raise KilPodRuntimeError("reconstructed proof differs")

def validate_kil_pod_runtime(*, configuration,endpoints,node_images):
    try:
        driver,bindings=_compute(configuration,endpoints,node_images)
        return KilPodRuntimeProof(configuration,endpoints,node_images,driver,bindings)
    except KilPodRuntimeError: raise
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,RecursionError) as error:
        raise KilPodRuntimeError("invalid KIL Pod runtime evidence") from error

__all__=("KilPodRuntimeError","KilPodRuntimeBinding","KilPodRuntimeProof","validate_kil_pod_runtime")
