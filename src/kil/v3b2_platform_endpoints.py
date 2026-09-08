"""Closed networking proof for the fixed Kubernetes and CoreDNS Services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv4Network
import re

from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_deployment_ownership import DeploymentOwnershipProof
from kil.v3b2_node_ownership import NodeOwnershipProof


_NODE = "kil-v3-lab-control-plane"
_SERVICE_KEYS = frozenset({
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "creationTimestamp", "labels", "annotations", "selector", "clusterIP",
    "clusterIPs", "ipFamilies", "ipFamilyPolicy", "type", "sessionAffinity",
    "internalTrafficPolicy", "ports",
})
_NODE_KEYS = frozenset({
    "apiVersion", "kind", "name", "uid", "resourceVersion",
    "creationTimestamp", "addresses",
})
_POD_KEYS = frozenset({
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "creationTimestamp", "nodeName", "phase", "deletionTimestamp", "podIP",
    "podIPs", "conditions",
})
_ENDPOINTS_KEYS = frozenset({
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "creationTimestamp", "labels", "subsets",
})
_SLICE_KEYS = frozenset({
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "creationTimestamp", "labels", "ownerReference", "addressType", "ports",
    "endpoints",
})
_PORT_KEYS = frozenset({"name", "protocol", "port"})
_SERVICE_PORT_KEYS = frozenset({"name", "protocol", "port", "targetPort"})
_OWNER_KEYS = frozenset({
    "apiVersion", "kind", "name", "uid", "controller", "blockOwnerDeletion",
})
_TARGET_KEYS = frozenset({"kind", "namespace", "name", "uid"})
_UID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_DNS = re.compile(r"[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?")
_SLICE = re.compile(r"kube-dns-[a-z0-9]{5}")
_TIMESTAMP = re.compile(
    r"(?:[0-9]{4})-(?:[0-9]{2})-(?:[0-9]{2})T"
    r"(?:[0-9]{2}):(?:[0-9]{2}):(?:[0-9]{2})(?:\.[0-9]{1,9})?Z"
)
_UINT64_MAX = 2**64 - 1


class PlatformEndpointError(ValueError):
    """The platform Service/endpoint projection is incomplete or ambiguous."""


def _text(label: str, value: object, maximum: int = 253, *, empty: bool = False) -> str:
    if type(value) is not str or (not empty and not value) or len(value) > maximum:
        raise PlatformEndpointError(f"{label} must be an exact bounded string")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise PlatformEndpointError(f"{label} contains a surrogate")
    try:
        if len(value.encode("utf-8")) > maximum * 4:
            raise PlatformEndpointError(f"{label} exceeds its byte bound")
    except UnicodeEncodeError as error:
        raise PlatformEndpointError(f"{label} is not Unicode scalar text") from error
    return value


def _constant(label: str, value: object, expected: str) -> str:
    result = _text(label, value, max(32, len(expected)))
    if result != expected:
        raise PlatformEndpointError(f"{label} is not the reviewed value")
    return result


def _name(label: str, value: object) -> str:
    result = _text(label, value, 63)
    if _DNS.fullmatch(result) is None:
        raise PlatformEndpointError(f"{label} is not a conservative DNS label")
    return result


def _uid(value: object) -> str:
    result = _text("UID", value, 128)
    if _UID.fullmatch(result) is None:
        raise PlatformEndpointError("UID is not a bounded API identity")
    return result


def _rv(value: object) -> str:
    result = _text("resourceVersion", value, 20)
    if (not result.isascii() or not result.isdigit() or result.startswith("0")
            or int(result) > _UINT64_MAX):
        raise PlatformEndpointError("resourceVersion is not a canonical positive uint64")
    return result


def _timestamp(value: object) -> str:
    result = _text("creationTimestamp", value, 40)
    if _TIMESTAMP.fullmatch(result) is None:
        raise PlatformEndpointError("creationTimestamp is not canonical UTC RFC3339")
    try:
        datetime.fromisoformat(result[:-1] + "+00:00")
    except ValueError as error:
        raise PlatformEndpointError("creationTimestamp is not a calendar timestamp") from error
    return result


def _closed(value: object, keys: frozenset[str], label: str) -> dict:
    if (type(value) is not dict or len(value) != len(keys)
            or any(type(key) is not str for key in value) or set(value) != keys):
        raise PlatformEndpointError(f"{label} shape is not exact")
    return value


def _precheck_value(value: object, depth: int, budget: list[int]) -> None:
    budget[0] += 1
    if depth > 12 or budget[0] > 2048:
        raise PlatformEndpointError("projection exceeds its structural bound")
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        if len(value) > 1024:
            raise PlatformEndpointError("projection string exceeds its bound")
        return
    if type(value) is list:
        if len(value) > 32:
            raise PlatformEndpointError("projection list exceeds its bound")
        for item in value:
            _precheck_value(item, depth + 1, budget)
        return
    if type(value) is dict:
        if len(value) > 32 or any(type(key) is not str or len(key) > 128 for key in value):
            raise PlatformEndpointError("projection object exceeds its bound")
        for item in value.values():
            _precheck_value(item, depth + 1, budget)
        return
    raise PlatformEndpointError("projection contains a non-JSON value")


def _precheck_rows(value: object, count: int, label: str) -> list[dict]:
    if type(value) is not list or len(value) != count:
        raise PlatformEndpointError(f"{label} cardinality is not exactly {count}")
    for row in value:
        if type(row) is not dict:
            raise PlatformEndpointError(f"{label} records must be exact dicts")
        _precheck_value(row, 0, [0])
    return value


def _ipv4(label: str, value: object, network: IPv4Network | None = None) -> str:
    text = _text(label, value, 15)
    try:
        address = IPv4Address(text)
    except ValueError as error:
        raise PlatformEndpointError(f"{label} is not IPv4") from error
    if str(address) != text or (network is not None and address not in network):
        raise PlatformEndpointError(f"{label} is not canonical or in the reviewed network")
    return text


def _pod_ip(label: str, value: object) -> str:
    network = IPv4Network("10.244.0.0/16")
    text = _ipv4(label, value, network)
    if IPv4Address(text) in {network.network_address, network.broadcast_address}:
        raise PlatformEndpointError(f"{label} is not a usable Pod address")
    return text


def _node_ip(value: object) -> str:
    text = _ipv4("Node InternalIP", value)
    address = IPv4Address(text)
    if address in IPv4Network("10.244.0.0/16") or address in IPv4Network("10.96.0.0/16"):
        raise PlatformEndpointError("Node InternalIP overlaps a cluster allocation subnet")
    return text


def _metadata(record: dict, *, api_version: str, kind: str,
              namespace: str | None, name: str) -> tuple[str, str]:
    _constant("apiVersion", record["apiVersion"], api_version)
    _constant("kind", record["kind"], kind)
    if namespace is not None:
        _constant("namespace", record["namespace"], namespace)
    _constant("name", record["name"], name)
    uid, resource_version = _uid(record["uid"]), _rv(record["resourceVersion"])
    _timestamp(record["creationTimestamp"])
    return uid, resource_version


def _port(record: object, expected: tuple[str, str, int], *, service: bool = False,
          service_port: int | None = None) -> None:
    row = _closed(record, _SERVICE_PORT_KEYS if service else _PORT_KEYS, "port")
    name, protocol, port = expected
    if (row["name"] != name or row["protocol"] != protocol
            or type(row["port"]) is not int or row["port"] != (service_port or port)):
        raise PlatformEndpointError("port is not the exact reviewed port")
    if service and (type(row["targetPort"]) is not int or row["targetPort"] != port):
        raise PlatformEndpointError("Service targetPort is not the exact numeric target")


def _ports(value: object, expected: tuple[tuple[str, str, int], ...], *,
           service: bool = False, service_ports: tuple[int, ...] | None = None) -> None:
    if type(value) is not list or len(value) != len(expected):
        raise PlatformEndpointError("ports cardinality is not exact")
    for index, (row, item) in enumerate(zip(value, expected)):
        _port(row, item, service=service,
              service_port=None if service_ports is None else service_ports[index])


def _dependency_domain(deployments: object, node: object):
    if type(deployments) is not DeploymentOwnershipProof:
        raise PlatformEndpointError("deployment proof type is not exact")
    if type(node) is not NodeOwnershipProof:
        raise PlatformEndpointError("node proof type is not exact")
    try:
        deployments.__post_init__(); node.__post_init__()
    except (TypeError, ValueError, UnicodeError, AttributeError) as error:
        raise PlatformEndpointError("an accepted dependency no longer validates") from error
    coredns = [binding for binding in deployments.bindings
               if (binding.namespace, binding.deployment_name) == ("kube-system", "coredns")]
    if len(coredns) != 1 or coredns[0].replicas != 2:
        raise PlatformEndpointError("Deployment proof lacks exactly two CoreDNS Pods")
    if node.node_name != _NODE:
        raise PlatformEndpointError("Node proof is for another node")
    deployment_uids: list[str] = []
    for binding in deployments.bindings:
        deployment_uids.extend((binding.deployment_uid, binding.replica_set_uid))
        deployment_uids.extend(pod_uid for _, pod_uid, _ in binding.pods)
    node_uids = [node.node_uid]
    for binding in node.daemon_pods:
        node_uids.extend((binding.daemon_set_uid, binding.pod_uid))
    node_uids.extend(binding.pod_uid for binding in node.static_pods)
    for uid in (*deployment_uids, *node_uids):
        _uid(uid)
    if (len(deployment_uids) != 37 or len(node_uids) != 9
            or len(set(deployment_uids)) != 37 or len(set(node_uids)) != 9
            or set(deployment_uids) & set(node_uids)):
        raise PlatformEndpointError("accepted proof UID domains collide or are incomplete")
    return coredns[0], tuple(sorted((*deployment_uids, *node_uids)))


def _revalidate(profile: object, deployments: object, node: object):
    if type(profile) is not V3B2Profile:
        raise PlatformEndpointError("profile must be an exact V3B2Profile")
    try:
        profile.__post_init__()
    except (TypeError, ValueError, UnicodeError, AttributeError) as error:
        raise PlatformEndpointError("profile no longer validates") from error
    coredns, dependency_uids = _dependency_domain(deployments, node)
    return profile, coredns, node, dependency_uids


@dataclass(frozen=True, slots=True, order=True)
class CoreDNSPodEndpoint:
    name: str
    uid: str
    resource_version: str
    address: str

    def __post_init__(self) -> None:
        name = _name("CoreDNS Pod name", self.name)
        if re.fullmatch(r"coredns-[a-z0-9]{10}-[a-z0-9]{5}", name) is None:
            raise PlatformEndpointError("CoreDNS Pod name is not generated by its ReplicaSet")
        _uid(self.uid)
        _rv(self.resource_version)
        _pod_ip("CoreDNS Pod address", self.address)


@dataclass(frozen=True, slots=True, order=True)
class PlatformEndpointBinding:
    namespace: str
    service_name: str
    service_uid: str
    service_resource_version: str
    cluster_ip: str
    endpoints_uid: str
    endpoints_resource_version: str
    endpoint_slice_name: str
    endpoint_slice_uid: str
    endpoint_slice_resource_version: str
    targets: tuple[tuple[str, str], ...]

    @property
    def addresses(self) -> tuple[str, ...]:
        return tuple(address for address, _ in self.targets)

    @property
    def target_uids(self) -> tuple[str, ...]:
        return tuple(uid for _, uid in self.targets if uid)

    def __post_init__(self) -> None:
        _name("binding namespace", self.namespace)
        _name("binding Service name", self.service_name)
        identity = (self.namespace, self.service_name)
        if identity not in {("default", "kubernetes"), ("kube-system", "kube-dns")}:
            raise PlatformEndpointError("binding Service identity is not reviewed")
        for value in (self.service_uid, self.endpoints_uid, self.endpoint_slice_uid):
            _uid(value)
        for value in (self.service_resource_version, self.endpoints_resource_version,
                      self.endpoint_slice_resource_version):
            _rv(value)
        expected_cluster_ip = ("10.96.0.1" if identity == ("default", "kubernetes")
                               else "10.96.0.10")
        if _ipv4("clusterIP", self.cluster_ip, IPv4Network("10.96.0.0/16")) != expected_cluster_ip:
            raise PlatformEndpointError("binding Service IP is not its fixed allocation")
        _name("binding EndpointSlice name", self.endpoint_slice_name)
        expected_count = 1 if identity == ("default", "kubernetes") else 2
        if (type(self.targets) is not tuple or len(self.targets) != expected_count
                or any(type(target) is not tuple or len(target) != 2 for target in self.targets)):
            raise PlatformEndpointError("binding targets are not exact and canonical")
        for address, target_uid in self.targets:
            if identity == ("default", "kubernetes"):
                _node_ip(address)
                _text("empty Kubernetes target UID", target_uid, 1, empty=True)
            else:
                _pod_ip("binding Pod address", address)
                _uid(target_uid)
        if self.targets != tuple(sorted(self.targets)) or len(set(self.targets)) != expected_count:
            raise PlatformEndpointError("binding targets are not exact and canonical")
        if identity == ("default", "kubernetes"):
            if (self.endpoint_slice_name != "kubernetes"
                    or self.targets != ((self.addresses[0], ""),)):
                raise PlatformEndpointError("Kubernetes endpoint producer contract differs")
        else:
            if _SLICE.fullmatch(self.endpoint_slice_name) is None:
                raise PlatformEndpointError("CoreDNS EndpointSlice name differs")
            if (type(self.target_uids) is not tuple or len(self.target_uids) != 2
                    or len(set(self.target_uids)) != 2):
                raise PlatformEndpointError("CoreDNS target UIDs are not exact and canonical")
            for value in self.target_uids:
                _uid(value)
        if len({self.service_uid, self.endpoints_uid, self.endpoint_slice_uid}) != 3:
            raise PlatformEndpointError("binding resource UIDs collide")


@dataclass(frozen=True, slots=True)
class PlatformEndpointProof:
    node_name: str
    node_uid: str
    node_resource_version: str
    node_internal_ip: str
    dependency_uids: tuple[str, ...]
    coredns_pods: tuple[CoreDNSPodEndpoint, ...]
    deployment_ownership: DeploymentOwnershipProof
    node_ownership: NodeOwnershipProof
    bindings: tuple[PlatformEndpointBinding, ...]
    runtime_contract_complete: bool = False

    def __post_init__(self) -> None:
        _constant("node name", self.node_name, _NODE)
        _uid(self.node_uid); _rv(self.node_resource_version); _node_ip(self.node_internal_ip)
        if (type(self.dependency_uids) is not tuple or len(self.dependency_uids) != 46
                or any(type(value) is not str for value in self.dependency_uids)):
            raise PlatformEndpointError("dependency UID domain is not exact")
        for value in self.dependency_uids:
            _uid(value)
        if (self.dependency_uids != tuple(sorted(self.dependency_uids))
                or len(set(self.dependency_uids)) != 46 or self.node_uid not in self.dependency_uids):
            raise PlatformEndpointError("dependency UID domain is not canonical")
        coredns_owner, computed_uids = _dependency_domain(
            self.deployment_ownership, self.node_ownership,
        )
        if computed_uids != self.dependency_uids:
            raise PlatformEndpointError("retained dependency UID domain differs from ownership proofs")
        if ((self.node_name, self.node_uid, self.node_resource_version)
                != (self.node_ownership.node_name, self.node_ownership.node_uid,
                    self.node_ownership.node_resource_version)):
            raise PlatformEndpointError("retained Node identity differs from Node ownership proof")
        if (type(self.coredns_pods) is not tuple or len(self.coredns_pods) != 2
                or any(type(item) is not CoreDNSPodEndpoint for item in self.coredns_pods)):
            raise PlatformEndpointError("CoreDNS endpoint identities are not exact")
        for item in self.coredns_pods:
            item.__post_init__()
        if self.coredns_pods != tuple(sorted(self.coredns_pods)):
            raise PlatformEndpointError("CoreDNS endpoint identities are not canonical")
        owner_identities = tuple(sorted(coredns_owner.pods))
        endpoint_identities = tuple(
            (item.name, item.uid, item.resource_version) for item in self.coredns_pods
        )
        if endpoint_identities != owner_identities:
            raise PlatformEndpointError(
                "CoreDNS endpoints do not preserve the Deployment-owned Pod role")
        if (type(self.bindings) is not tuple or len(self.bindings) != 2
                or any(type(item) is not PlatformEndpointBinding for item in self.bindings)):
            raise PlatformEndpointError("proof bindings are not exact")
        for item in self.bindings:
            item.__post_init__()
        if (self.bindings != tuple(sorted(self.bindings))
                or tuple((item.namespace, item.service_name) for item in self.bindings)
                != (("default", "kubernetes"), ("kube-system", "kube-dns"))):
            raise PlatformEndpointError("proof bindings are not canonical and complete")
        if self.bindings[0].targets != ((self.node_internal_ip, ""),):
            raise PlatformEndpointError("Kubernetes endpoint does not equal Node InternalIP")
        coredns_targets = tuple(sorted((item.address, item.uid) for item in self.coredns_pods))
        if self.bindings[1].targets != coredns_targets:
            raise PlatformEndpointError("kube-dns targets differ from role-bound CoreDNS Pods")
        allocated_addresses = [self.node_internal_ip]
        allocated_addresses.extend(item.cluster_ip for item in self.bindings)
        allocated_addresses.extend(self.bindings[1].addresses)
        if len(allocated_addresses) != len(set(allocated_addresses)):
            raise PlatformEndpointError("Node, Service, and Pod addresses collide")
        new_uids = []
        for item in self.bindings:
            new_uids.extend((item.service_uid, item.endpoints_uid, item.endpoint_slice_uid))
        if len(new_uids) != len(set(new_uids)) or set(new_uids) & set(self.dependency_uids):
            raise PlatformEndpointError("new resource UIDs collide with accepted identities")
        if type(self.runtime_contract_complete) is not bool or self.runtime_contract_complete:
            raise PlatformEndpointError("platform endpoint proof is not runtime complete")


def _service_rows(rows: list[dict], service_network: IPv4Network):
    expected = {
        ("default", "kubernetes"): {
            "offset": 1, "labels": {"component": "apiserver", "provider": "kubernetes"},
            "annotations": {}, "selector": None,
            "ports": (("https", "TCP", 6443),), "service_ports": (443,),
        },
        ("kube-system", "kube-dns"): {
            "offset": 10,
            "labels": {"k8s-app": "kube-dns", "kubernetes.io/cluster-service": "true",
                       "kubernetes.io/name": "CoreDNS"},
            "annotations": {"prometheus.io/port": "9153", "prometheus.io/scrape": "true"},
            "selector": {"k8s-app": "kube-dns"},
            "ports": (("dns", "UDP", 53), ("dns-tcp", "TCP", 53), ("metrics", "TCP", 9153)),
            "service_ports": (53, 53, 9153),
        },
    }
    result = {}
    for raw in rows:
        row = _closed(raw, _SERVICE_KEYS, "Service")
        namespace, name = _name("namespace", row["namespace"]), _name("name", row["name"])
        key = (namespace, name)
        if key not in expected or key in result:
            raise PlatformEndpointError("Service identity is not the exact platform set")
        uid, rv = _metadata(row, api_version="v1", kind="Service", namespace=namespace, name=name)
        spec = expected[key]
        address = _ipv4("clusterIP", row["clusterIP"], service_network)
        if address != str(service_network[spec["offset"]]):
            raise PlatformEndpointError("Service allocation is not the pinned offset")
        if (row["labels"] != spec["labels"] or row["annotations"] != spec["annotations"]
                or row["selector"] != spec["selector"] or row["clusterIPs"] != [address]
                or row["ipFamilies"] != ["IPv4"] or row["ipFamilyPolicy"] != "SingleStack"
                or row["type"] != "ClusterIP" or row["sessionAffinity"] != "None"
                or row["internalTrafficPolicy"] != "Cluster"):
            raise PlatformEndpointError("Service configuration differs from its producer contract")
        _ports(row["ports"], spec["ports"], service=True, service_ports=spec["service_ports"])
        result[key] = (uid, rv, address, spec["ports"])
    if set(result) != set(expected):
        raise PlatformEndpointError("Service set is incomplete")
    return result


def _node_row(row: dict, proof: NodeOwnershipProof) -> str:
    row = _closed(row, _NODE_KEYS, "Node network projection")
    uid, rv = _metadata(row, api_version="v1", kind="Node", namespace=None, name=_NODE)
    if (uid, rv) != (proof.node_uid, proof.node_resource_version):
        raise PlatformEndpointError("Node network identity does not join Node proof")
    addresses = row["addresses"]
    if type(addresses) is not list or len(addresses) != 1:
        raise PlatformEndpointError("Node must project exactly one address")
    address = _closed(addresses[0], frozenset({"type", "address"}), "Node address")
    if address["type"] != "InternalIP":
        raise PlatformEndpointError("Node address is not InternalIP")
    return _node_ip(address["address"])


def _pods(rows: list[dict], coredns, pod_network: IPv4Network):
    expected = {name: (uid, rv) for name, uid, rv in coredns.pods}
    result = {}
    for raw in rows:
        row = _closed(raw, _POD_KEYS, "CoreDNS Pod")
        name = _name("Pod name", row["name"])
        if name not in expected or name in result:
            raise PlatformEndpointError("CoreDNS Pod identity is unexpected")
        uid, rv = _metadata(row, api_version="v1", kind="Pod", namespace="kube-system", name=name)
        if (uid, rv) != expected[name]:
            raise PlatformEndpointError("CoreDNS Pod identity does not join Deployment proof")
        ip = _pod_ip("Pod IP", row["podIP"])
        if IPv4Address(ip) not in pod_network:
            raise PlatformEndpointError("Pod IP is outside the profile Pod subnet")
        if (row["nodeName"] != _NODE or row["phase"] != "Running"
                or row["deletionTimestamp"] is not None or row["podIPs"] != [{"ip": ip}]
                or row["conditions"] != [{"type": "Ready", "status": "True"}]):
            raise PlatformEndpointError("CoreDNS Pod is not exact ready nondeleting state")
        result[name] = (uid, rv, ip)
    if set(result) != set(expected) or len({value[2] for value in result.values()}) != 2:
        raise PlatformEndpointError("CoreDNS Pod set or addresses are not exact")
    return result


def _legacy(rows, services, node_ip, pods):
    result = {}
    for raw in rows:
        row = _closed(raw, _ENDPOINTS_KEYS, "Endpoints")
        key = (_name("namespace", row["namespace"]), _name("name", row["name"]))
        if key not in services or key in result:
            raise PlatformEndpointError("Endpoints identity is unexpected")
        uid, rv = _metadata(row, api_version="v1", kind="Endpoints", namespace=key[0], name=key[1])
        expected_labels = (
            {"endpointslice.kubernetes.io/skip-mirror": "true"}
            if key == ("default", "kubernetes") else
            {"k8s-app": "kube-dns",
             "kubernetes.io/cluster-service": "true",
             "kubernetes.io/name": "CoreDNS",
             "endpoints.kubernetes.io/managed-by": "endpoint-controller"}
        )
        if row["labels"] != expected_labels:
            raise PlatformEndpointError("Endpoints labels differ from the source-specific producer")
        subsets = row["subsets"]
        if type(subsets) is not list or len(subsets) != 1:
            raise PlatformEndpointError("Endpoints subsets are not exact")
        subset = _closed(subsets[0], frozenset({"addresses", "ports"}), "EndpointSubset")
        _, _, _, expected_ports = services[key]
        _ports(subset["ports"], expected_ports)
        addresses = subset["addresses"]
        expected_count = 1 if key == ("default", "kubernetes") else 2
        if type(addresses) is not list or len(addresses) != expected_count:
            raise PlatformEndpointError("Endpoints address cardinality is not exact")
        bindings = []
        for item in addresses:
            if key == ("default", "kubernetes"):
                address = _closed(item, frozenset({"ip"}), "Kubernetes EndpointAddress")
                if address["ip"] != node_ip:
                    raise PlatformEndpointError("Kubernetes Endpoints address differs from Node")
                bindings.append((node_ip, ""))
            else:
                address = _closed(item, frozenset({"ip", "nodeName", "targetRef"}), "DNS EndpointAddress")
                target = _closed(address["targetRef"], _TARGET_KEYS, "DNS targetRef")
                name = target["name"]
                if (target.get("kind") != "Pod" or target.get("namespace") != "kube-system"
                        or name not in pods or target.get("uid") != pods[name][0]
                        or address["ip"] != pods[name][2] or address["nodeName"] != _NODE):
                    raise PlatformEndpointError("DNS Endpoints target does not join ready Pod")
                bindings.append((address["ip"], target["uid"]))
        bindings.sort()
        if len(set(bindings)) != expected_count:
            raise PlatformEndpointError("Endpoints addresses collide")
        result[key] = (uid, rv, tuple(bindings))
    if set(result) != set(services):
        raise PlatformEndpointError("Endpoints set is incomplete")
    return result


def _slices(rows, services, legacy, node_ip, pods):
    result = {}
    for raw in rows:
        row = _closed(raw, _SLICE_KEYS, "EndpointSlice")
        namespace, name = _name("namespace", row["namespace"]), _name("slice name", row["name"])
        key = (namespace, "kubernetes" if namespace == "default" else "kube-dns")
        if key not in services or key in result:
            raise PlatformEndpointError("EndpointSlice identity is unexpected")
        if ((key == ("default", "kubernetes") and name != "kubernetes")
                or (key == ("kube-system", "kube-dns") and _SLICE.fullmatch(name) is None)):
            raise PlatformEndpointError("EndpointSlice name differs from producer contract")
        uid, rv = _metadata(row, api_version="discovery.k8s.io/v1", kind="EndpointSlice",
                            namespace=namespace, name=name)
        service_uid, _, _, expected_ports = services[key]
        if row["addressType"] != "IPv4":
            raise PlatformEndpointError("EndpointSlice addressType is not IPv4")
        _ports(row["ports"], expected_ports)
        if key == ("default", "kubernetes"):
            if (row["labels"] != {"kubernetes.io/service-name": "kubernetes"}
                    or row["ownerReference"] is not None):
                raise PlatformEndpointError("Kubernetes slice must retain its distinct producer metadata")
        else:
            if row["labels"] != {
                "kubernetes.io/service-name": "kube-dns",
                "endpointslice.kubernetes.io/managed-by": "endpointslice-controller.k8s.io",
            }:
                raise PlatformEndpointError("DNS slice controller labels are not exact")
            owner = _closed(row["ownerReference"], _OWNER_KEYS, "EndpointSlice ownerReference")
            if owner != {"apiVersion": "v1", "kind": "Service", "name": "kube-dns",
                         "uid": service_uid, "controller": True, "blockOwnerDeletion": True}:
                raise PlatformEndpointError("DNS slice owner does not join Service UID")
        endpoints = row["endpoints"]
        expected_count = 1 if key == ("default", "kubernetes") else 2
        if type(endpoints) is not list or len(endpoints) != expected_count:
            raise PlatformEndpointError("EndpointSlice endpoint cardinality is not exact")
        bindings = []
        for item in endpoints:
            endpoint = _closed(item, frozenset({"addresses", "conditions", "targetRef", "nodeName"}),
                               "EndpointSlice endpoint")
            if type(endpoint["addresses"]) is not list or len(endpoint["addresses"]) != 1:
                raise PlatformEndpointError("EndpointSlice endpoint address is not singular")
            address = endpoint["addresses"][0]
            if key == ("default", "kubernetes"):
                if (address != node_ip or endpoint["conditions"] != {"ready": True}
                        or endpoint["targetRef"] is not None or endpoint["nodeName"] is not None):
                    raise PlatformEndpointError("Kubernetes slice endpoint differs from lease producer")
                bindings.append((address, ""))
            else:
                target = _closed(endpoint["targetRef"], _TARGET_KEYS, "slice targetRef")
                pod_name = target["name"]
                if (endpoint["conditions"] != {"ready": True, "serving": True, "terminating": False}
                        or endpoint["nodeName"] != _NODE or target.get("kind") != "Pod"
                        or target.get("namespace") != "kube-system" or pod_name not in pods
                        or target.get("uid") != pods[pod_name][0] or address != pods[pod_name][2]):
                    raise PlatformEndpointError("DNS slice endpoint does not join ready Pod")
                bindings.append((address, target["uid"]))
        bindings.sort()
        if tuple(bindings) != legacy[key][2]:
            raise PlatformEndpointError("EndpointSlice and legacy Endpoints disagree")
        result[key] = (name, uid, rv, tuple(bindings))
    if set(result) != set(services):
        raise PlatformEndpointError("EndpointSlice set is incomplete")
    return result


def validate_platform_endpoints(*, profile: V3B2Profile,
                                deployment_ownership: DeploymentOwnershipProof,
                                node_ownership: NodeOwnershipProof,
                                node_network: dict, services: list[dict],
                                coredns_pods: list[dict], endpoints: list[dict],
                                endpoint_slices: list[dict]) -> PlatformEndpointProof:
    """Validate the two source-distinct platform endpoint producer contracts."""
    try:
        service_rows = _precheck_rows(services, 2, "Services")
        pod_rows = _precheck_rows(coredns_pods, 2, "CoreDNS Pods")
        endpoints_rows = _precheck_rows(endpoints, 2, "Endpoints")
        slice_rows = _precheck_rows(endpoint_slices, 2, "EndpointSlices")
        if type(node_network) is not dict:
            raise PlatformEndpointError("Node network projection must be an exact dict")
        _precheck_value(node_network, 0, [0])
        checked_profile, coredns, checked_node, dependency_uids = _revalidate(
            profile, deployment_ownership, node_ownership,
        )
        service_network = IPv4Network(checked_profile.service_subnet)
        pod_network = IPv4Network(checked_profile.pod_subnet)
        node_ip = _node_row(node_network, checked_node)
        service_values = _service_rows(service_rows, service_network)
        pod_values = _pods(pod_rows, coredns, pod_network)
        endpoint_values = _legacy(endpoints_rows, service_values, node_ip, pod_values)
        slice_values = _slices(slice_rows, service_values, endpoint_values, node_ip, pod_values)
        bindings = []
        for key in sorted(service_values):
            service_uid, service_rv, cluster_ip, _ = service_values[key]
            endpoints_uid, endpoints_rv, target_values = endpoint_values[key]
            slice_name, slice_uid, slice_rv, _ = slice_values[key]
            bindings.append(PlatformEndpointBinding(
                key[0], key[1], service_uid, service_rv, cluster_ip,
                endpoints_uid, endpoints_rv, slice_name, slice_uid, slice_rv,
                target_values,
            ))
        coredns_endpoints = tuple(sorted(
            CoreDNSPodEndpoint(name, uid, resource_version, address)
            for name, (uid, resource_version, address) in pod_values.items()
        ))
        return PlatformEndpointProof(
            checked_node.node_name, checked_node.node_uid,
            checked_node.node_resource_version, node_ip, dependency_uids,
            coredns_endpoints, deployment_ownership, node_ownership,
            tuple(bindings), False,
        )
    except PlatformEndpointError:
        raise
    except (TypeError, ValueError, UnicodeError, OverflowError, AttributeError,
            KeyError, RecursionError) as error:
        raise PlatformEndpointError("platform endpoint evidence is malformed") from error


__all__ = (
    "PlatformEndpointError", "CoreDNSPodEndpoint", "PlatformEndpointBinding",
    "PlatformEndpointProof",
    "validate_platform_endpoints",
)
