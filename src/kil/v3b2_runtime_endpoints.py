"""Same-source endpoint extraction, without full admission or runtime completion.

The retained ownership proof supplies the only raw List and expected context.
Ready condition and InternalIP selection each require exactly one matching record;
other condition/address roles stay in raw evidence, outside this projection claim.
Optional absent deletion timestamps, selectors and producer-absent API-server slice
owner/target/node fields map to None, never invented references. Other required
values are read directly. A narrow compatibility seam builds an internal KIL
ServiceAllocation without reviewed API metadata additions and uninterpreted
status; the full original allocation is retained publicly and both are rederived
on replay. Status is only bounded JSON, not certified by the metadata normalizer.
Extra root/endpoint fields retained in ownership raw bytes are not certified by
this endpoint projection; only explicitly extracted relations are established.
Legacy KIL Endpoints are retained but not certified; their unknown identities fail.
"""
from copy import deepcopy
from dataclasses import dataclass
import json

from kil.v3b2_runtime_ownership import RuntimeOwnershipProof
from kil.v3b2_service_bindings import ServiceAllocation, validate_service_allocations
from kil.v3b2_platform_endpoints import PlatformEndpointProof, validate_platform_endpoints
from kil.v3b2_kil_endpoint_ownership import KilEndpointOwnershipProof, validate_kil_endpoint_ownership
from kil.v3b2_contracts import TRACK_NAMESPACES


class RuntimeEndpointsError(ValueError):
    pass


def _base(row, *, timestamp=False, node=False):
    metadata = row["metadata"]
    result = {"apiVersion": row["apiVersion"], "kind": row["kind"],
              **{key: metadata[key] for key in ("name", "uid", "resourceVersion")}}
    if not node: result["namespace"] = metadata["namespace"]
    if timestamp: result["creationTimestamp"] = metadata["creationTimestamp"]
    return result


def _selected(values, field, expected):
    if type(values) is not list or any(type(row) is not dict or type(row.get(field)) is not str for row in values):
        raise RuntimeEndpointsError("invalid typed source records")
    result = [row for row in values if row[field] == expected]
    if len(result) != 1: raise RuntimeEndpointsError("source selection is missing or ambiguous")
    return result[0]


def _pod(row, *, timestamp=False):
    status = row["status"]
    ready = _selected(status["conditions"], "type", "Ready")
    return {**_base(row, timestamp=timestamp), "nodeName": row["spec"]["nodeName"],
            "deletionTimestamp": row["metadata"].get("deletionTimestamp"),
            **{key: status[key] for key in ("phase", "podIP", "podIPs")},
            "conditions": [{key: ready[key] for key in ("type", "status")}]}


def _target(value):
    # Both pinned producers initialize precisely these ObjectReference fields.
    # https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/controller/endpoint/endpoints_controller.go
    # https://github.com/kubernetes/kubernetes/blob/v1.36.1/staging/src/k8s.io/endpointslice/utils.go
    if type(value) is not dict or set(value) != {"kind", "namespace", "name", "uid"}:
        raise RuntimeEndpointsError("targetRef is not the exact four-field pinned producer shape")
    return {key: value[key] for key in ("kind", "namespace", "name", "uid")}


def _owner(row, *, absent=False):
    metadata = row["metadata"]
    if absent and "ownerReferences" not in metadata: return None
    owners = metadata.get("ownerReferences")
    if type(owners) is not list or len(owners) != 1 or type(owners[0]) is not dict:
        raise RuntimeEndpointsError("ownerReferences must be exactly one source record")
    return owners[0]


def _slice(row, *, platform=False):
    api = row["metadata"].get("namespace") == "default" and row["metadata"].get("name") == "kubernetes"
    endpoints = []
    for endpoint in row["endpoints"]:
        projected = {key: endpoint[key] for key in ("addresses", "conditions")}
        projected["targetRef"] = None if api and "targetRef" not in endpoint else _target(endpoint["targetRef"])
        projected["nodeName"] = endpoint.get("nodeName") if api else endpoint["nodeName"]
        endpoints.append(projected)
    return {**_base(row, timestamp=platform), "labels": row["metadata"]["labels"],
            "ownerReference": _owner(row, absent=api), "addressType": row["addressType"],
            "ports": row["ports"], "endpoints": endpoints}


def _legacy(row):
    subsets = deepcopy(row["subsets"])
    for subset in subsets:
        for address in subset["addresses"]:
            if "targetRef" in address: address["targetRef"] = _target(address["targetRef"])
    return {**_base(row, timestamp=True), "labels": row["metadata"]["labels"], "subsets": subsets}


def _service(row):
    spec = row["spec"]
    return {**_base(row, timestamp=True), "labels": row["metadata"]["labels"],
            "annotations": row["metadata"].get("annotations", {}), "selector": spec.get("selector"),
            **{key: spec[key] for key in ("clusterIP", "clusterIPs", "ipFamilies", "ipFamilyPolicy", "type",
                                         "sessionAffinity", "internalTrafficPolicy", "ports")}}


def _compute(ownership):
    if type(ownership) is not RuntimeOwnershipProof:
        raise RuntimeEndpointsError("ownership dependency type must be exact")
    ownership.__post_init__()
    return _extract_endpoints(ownership)


def _extract_endpoints(ownership):
    """Extract from the full raw List of an already validated phase proof."""
    rows = json.loads(ownership.runtime_objects)["items"]
    indexed = {(row["apiVersion"], row["kind"], row["metadata"].get("namespace", ""), row["metadata"]["name"]): row for row in rows}
    namespaces = tuple(namespace for _, namespace in TRACK_NAMESPACES)
    kil_keys = {(namespace, role) for namespace in namespaces for role in ("authz", "envoy", "target")}
    platform_keys = {("default", "kubernetes"), ("kube-system", "kube-dns")}
    services = [row for row in rows if row["kind"] == "Service"]
    slices = [row for row in rows if row["kind"] == "EndpointSlice"]
    if len(services) != 11 or len(slices) != 11:
        raise RuntimeEndpointsError("Service and EndpointSlice families must each contain exactly eleven")
    if {(row["apiVersion"], row["metadata"].get("namespace"), row["metadata"]["name"]) for row in services} != {
            ("v1", namespace, name) for namespace, name in kil_keys | platform_keys}:
        raise RuntimeEndpointsError("Service identities are not the reviewed closed set")
    kil_services = [row for row in services if (row["metadata"]["namespace"], row["metadata"]["name"]) in kil_keys]
    allocation = validate_service_allocations(kil_services, profile=ownership.profile, workload=ownership.workload)
    compatible = deepcopy(kil_services)
    for row in compatible:
        if set(row) not in ({"apiVersion", "kind", "metadata", "spec"},
                             {"apiVersion", "kind", "metadata", "spec", "status"}):
            raise RuntimeEndpointsError("unreviewed KIL Service root fields")
        row.pop("status", None)
        # The full validator checked these finite metadata additions. Status
        # above is excluded only as uninterpreted bounded JSON, not validated
        # runtime state. No unknown metadata/annotation is removed by this seam.
        for key in ("managedFields", "generation"): row["metadata"].pop(key, None)
        row["metadata"].get("annotations", {}).pop("kubectl.kubernetes.io/last-applied-configuration", None)
    compatible_allocation = validate_service_allocations(compatible, profile=ownership.profile, workload=ownership.workload)
    platform_slices, kil_slices = [], []
    for row in slices:
        key = (row["metadata"].get("namespace"), row["metadata"].get("labels", {}).get("kubernetes.io/service-name"))
        if key in platform_keys: platform_slices.append(_slice(row, platform=True))
        elif key in kil_keys: kil_slices.append(_slice(row))
        else: raise RuntimeEndpointsError("unreviewed EndpointSlice service identity")
    legacy = []
    for row in rows:
        if row["kind"] != "Endpoints": continue
        key = (row["metadata"].get("namespace"), row["metadata"]["name"])
        if row["apiVersion"] != "v1" or key not in kil_keys | platform_keys:
            raise RuntimeEndpointsError("unreviewed legacy Endpoints identity")
        if key in platform_keys: legacy.append(_legacy(row))
    node = indexed[("v1", "Node", "", ownership.node_ownership.node_name)]
    address = _selected(node["status"]["addresses"], "type", "InternalIP")
    node_network = {**_base(node, timestamp=True, node=True), "addresses": [
        {key: address[key] for key in ("type", "address")}]}
    coredns, kil_pods = [], []
    for binding in ownership.deployment_ownership.bindings:
        if (binding.namespace, binding.deployment_name) == ("kube-system", "coredns"):
            coredns.extend(_pod(indexed[("v1", "Pod", binding.namespace, name)], timestamp=True)
                           for name, _, _ in binding.pods)
        elif (binding.namespace, binding.deployment_name) in kil_keys:
            kil_pods.extend(_pod(indexed[("v1", "Pod", binding.namespace, name)]) for name, _, _ in binding.pods)
    platform = validate_platform_endpoints(profile=ownership.profile,
        deployment_ownership=ownership.deployment_ownership, node_ownership=ownership.node_ownership,
        node_network=node_network, services=[_service(row) for row in services
            if (row["metadata"]["namespace"], row["metadata"]["name"]) in platform_keys],
        coredns_pods=coredns, endpoints=legacy, endpoint_slices=platform_slices)
    kil = validate_kil_endpoint_ownership(pods=kil_pods, endpoint_slices=kil_slices,
        profile=ownership.profile, deployment_proof=ownership.deployment_ownership,
        service_allocation=compatible_allocation)
    return allocation, platform, kil


@dataclass(frozen=True, slots=True)
class RuntimeEndpointsProof:
    ownership: RuntimeOwnershipProof
    service_allocation: ServiceAllocation
    platform_endpoints: PlatformEndpointProof
    kil_endpoints: KilEndpointOwnershipProof
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise RuntimeEndpointsError("endpoint extraction cannot establish full completion")
            if (type(self.service_allocation) is not ServiceAllocation or type(self.platform_endpoints) is not PlatformEndpointProof
                    or type(self.kil_endpoints) is not KilEndpointOwnershipProof):
                raise RuntimeEndpointsError("retained endpoint proof types must be exact")
            if any(type(raw) is not bytes or len(raw) > 8 * 1024 * 1024 for raw in
                   (self.service_allocation.bindings, self.service_allocation.configurations)):
                raise RuntimeEndpointsError("retained allocation fields must be bounded bytes")
            self.platform_endpoints.__post_init__(); self.kil_endpoints.__post_init__()
            allocation, platform, kil = _compute(self.ownership)
            if (allocation != self.service_allocation or platform != self.platform_endpoints or kil != self.kil_endpoints):
                raise RuntimeEndpointsError("retained endpoint proofs differ from same-source reconstruction")
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError) as error:
            if isinstance(error, RuntimeEndpointsError): raise
            raise RuntimeEndpointsError("invalid runtime endpoint proof") from error


def validate_runtime_endpoints(*, ownership):
    """Derive both endpoint relations exclusively from the accepted ownership raw List."""
    try:
        allocation, platform, kil = _compute(ownership)
        return RuntimeEndpointsProof(ownership, allocation, platform, kil)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError) as error:
        if isinstance(error, RuntimeEndpointsError): raise
        raise RuntimeEndpointsError("invalid runtime endpoint source") from error
