"""Closed Pod and EndpointSlice ownership evidence for the nine KIL Services.

The inputs are deliberately small projections.  They join API incarnation
identity from already accepted Deployment and Service proofs to the ready Pod
network identity and to the EndpointSlice emitted by the pinned controller.
They do not assert that the wider V3B-2 runtime contract is complete.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
import json
import re

from kil.canonical import canonical_json
from kil.v3b2_api_defaults import _metadata
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_deployment_ownership import (
    DeploymentBinding,
    DeploymentOwnershipProof,
)
from kil.v3b2_service_bindings import ServiceAllocation


_APPLICATION_NAMESPACES = (
    "kil-v3-baseline",
    "kil-v3-local-reduce",
    "kil-v3-signed",
)
_TRACK_BY_NAMESPACE = {
    "kil-v3-baseline": "credential_policy_baseline",
    "kil-v3-local-reduce": "signed_plus_local_reduce",
    "kil-v3-signed": "signed_state_only",
}
_SERVICE_NAMES = ("authz", "envoy", "target")
_EXPECTED = frozenset(
    (namespace, service)
    for namespace in _APPLICATION_NAMESPACES
    for service in _SERVICE_NAMES
)
_NODE_NAME = "kil-v3-lab-control-plane"
_MANAGER = "endpointslice-controller.k8s.io"
_POD_KEYS = frozenset({
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "nodeName", "phase", "deletionTimestamp", "podIP", "podIPs", "conditions",
})
_SLICE_KEYS = frozenset({
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "labels", "ownerReference", "addressType", "ports", "endpoints",
})
_OWNER_KEYS = frozenset({
    "apiVersion", "kind", "name", "uid", "controller", "blockOwnerDeletion",
})
_LABEL_KEYS = frozenset({
    "kubernetes.io/service-name", "endpointslice.kubernetes.io/managed-by",
})
_PORT_KEYS = frozenset({"name", "protocol", "port"})
_ENDPOINT_KEYS = frozenset({
    "addresses", "conditions", "targetRef", "nodeName",
})
_ENDPOINT_CONDITION_KEYS = frozenset({"ready", "serving", "terminating"})
_TARGET_KEYS = frozenset({"kind", "namespace", "name", "uid"})
_POD_CONDITION_KEYS = frozenset({"type", "status"})
_POD_IP_KEYS = frozenset({"ip"})
_DNS_LABEL = re.compile(r"[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?")
_SLICE_SUFFIX = re.compile(r"[a-z0-9]{5}")
_API_UID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_RUN_ID = re.compile(r"v3b2-[0-9a-f]{64}")
_UINT64_MAX = 18_446_744_073_709_551_615
_MAX_PROOF_BYTES = 1024 * 1024


class KilEndpointOwnershipError(ValueError):
    """Raised when KIL Pod/EndpointSlice ownership is open or ambiguous."""


def _canonical(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _text(
    label: str,
    value: object,
    *,
    max_chars: int,
    max_bytes: int,
    empty: bool = False,
) -> str:
    if type(value) is not str or (not empty and not value):
        raise KilEndpointOwnershipError(f"{label} must be an exact bounded string")
    if len(value) > max_chars:
        raise KilEndpointOwnershipError(f"{label} exceeds its character bound")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise KilEndpointOwnershipError(f"{label} must contain Unicode scalar values")
    if len(value.encode("utf-8")) > max_bytes:
        raise KilEndpointOwnershipError(f"{label} exceeds its byte bound")
    return value


def _name(label: str, value: object) -> str:
    result = _text(label, value, max_chars=63, max_bytes=63)
    if _DNS_LABEL.fullmatch(result) is None:
        raise KilEndpointOwnershipError(f"{label} must be a conservative DNS label")
    return result


def _api_uid(label: str, value: object) -> str:
    result = _text(label, value, max_chars=128, max_bytes=128)
    if _API_UID.fullmatch(result) is None:
        raise KilEndpointOwnershipError(f"{label} is not an exact API UID")
    return result


def _uint64(label: str, value: object) -> str:
    result = _text(label, value, max_chars=20, max_bytes=20)
    if not result.isascii() or not result.isdigit() or result.startswith("0"):
        raise KilEndpointOwnershipError(f"{label} must be a canonical positive uint64")
    if int(result) > _UINT64_MAX:
        raise KilEndpointOwnershipError(f"{label} exceeds uint64")
    return result


def _constant(label: str, value: object, expected: str) -> None:
    if _text(label, value, max_chars=max(32, len(expected)),
             max_bytes=max(32, len(expected))) != expected:
        raise KilEndpointOwnershipError(f"{label} must be {expected}")


def _closed(value: object, keys: frozenset[str], label: str) -> dict:
    if type(value) is not dict:
        raise KilEndpointOwnershipError(f"{label} must be an exact dict")
    if len(value) != len(keys) or any(type(key) is not str for key in value):
        raise KilEndpointOwnershipError(f"{label} has an open or incomplete shape")
    if set(value) != keys:
        raise KilEndpointOwnershipError(f"{label} has an open or incomplete shape")
    return value


def _precheck_value(value: object, *, depth: int, budget: list[int]) -> None:
    """Bound the plain projection before any semantic or relational traversal."""
    budget[0] += 1
    if budget[0] > 4096 or depth > 12:
        raise KilEndpointOwnershipError("projection exceeds its structural bound")
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        _text("projection string", value, max_chars=1024, max_bytes=4096, empty=True)
        return
    if type(value) is list:
        if len(value) > 32:
            raise KilEndpointOwnershipError("projection list exceeds its bound")
        for item in value:
            _precheck_value(item, depth=depth + 1, budget=budget)
        return
    if type(value) is dict:
        if len(value) > 32:
            raise KilEndpointOwnershipError("projection object exceeds its bound")
        for key, item in value.items():
            _text("projection key", key, max_chars=128, max_bytes=512, empty=False)
            _precheck_value(item, depth=depth + 1, budget=budget)
        return
    raise KilEndpointOwnershipError("projection must contain exact JSON value types")


def _precheck_rows(value: object, *, label: str) -> list[dict]:
    if type(value) is not list or len(value) != 9:
        raise KilEndpointOwnershipError(f"{label} must be an exact list of nine records")
    for row in value:
        if type(row) is not dict:
            raise KilEndpointOwnershipError(f"{label} records must be exact dicts")
        _precheck_value(row, depth=0, budget=[0])
    return value


def _pod_address(label: str, value: object, network: IPv4Network) -> str:
    text = _text(label, value, max_chars=15, max_bytes=15)
    try:
        address = IPv4Address(text)
    except ValueError as error:
        raise KilEndpointOwnershipError(f"{label} is not canonical IPv4") from error
    if (str(address) != text or address not in network
            or address in {network.network_address, network.broadcast_address}):
        raise KilEndpointOwnershipError(f"{label} is outside the usable Pod subnet")
    return text


def _service_address(label: str, value: object, network: IPv4Network) -> str:
    text = _text(label, value, max_chars=15, max_bytes=15)
    try:
        address = IPv4Address(text)
    except ValueError as error:
        raise KilEndpointOwnershipError(f"{label} is not canonical IPv4") from error
    if (str(address) != text or address not in network
            or address in {network.network_address, network.broadcast_address,
                           network[1], network[10]}):
        raise KilEndpointOwnershipError(f"{label} is outside application Service space")
    return text


def _json_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise KilEndpointOwnershipError("proof JSON contains invalid or duplicate keys")
        result[key] = value
    return result


def _bounded_integer(value: str) -> int:
    if len(value) > 20:
        raise KilEndpointOwnershipError("proof JSON integer exceeds its bound")
    return int(value)


def _reject_constant(_: str) -> object:
    raise KilEndpointOwnershipError("proof JSON non-finite value is forbidden")


def _decode_canonical(value: object, label: str) -> list:
    if type(value) is not bytes or not value or len(value) > _MAX_PROOF_BYTES:
        raise KilEndpointOwnershipError(f"{label} must be bounded exact bytes")
    try:
        decoded = json.loads(
            value.decode("utf-8", errors="strict"),
            object_pairs_hook=_json_pairs,
            parse_int=_bounded_integer,
            parse_constant=_reject_constant,
        )
    except KilEndpointOwnershipError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise KilEndpointOwnershipError(f"{label} is invalid JSON") from error
    _precheck_value(decoded, depth=0, budget=[0])
    if type(decoded) is not list or _canonical(decoded) != value:
        raise KilEndpointOwnershipError(f"{label} must be a canonical JSON array")
    return decoded


def _revalidate_profile(profile: object) -> V3B2Profile:
    if type(profile) is not V3B2Profile:
        raise KilEndpointOwnershipError("profile must be an exact V3B2Profile")
    try:
        profile.__post_init__()
    except (TypeError, ValueError, UnicodeError, AttributeError) as error:
        raise KilEndpointOwnershipError("profile is no longer valid") from error
    return profile


def _revalidate_deployment_proof(value: object) -> dict[tuple[str, str], DeploymentBinding]:
    if type(value) is not DeploymentOwnershipProof:
        raise KilEndpointOwnershipError("deployment_proof has the wrong type")
    try:
        value.__post_init__()
    except (TypeError, ValueError, UnicodeError, AttributeError) as error:
        raise KilEndpointOwnershipError("deployment_proof is no longer valid") from error
    for binding in value.bindings:
        _api_uid("Deployment proof Deployment UID", binding.deployment_uid)
        _api_uid("Deployment proof ReplicaSet UID", binding.replica_set_uid)
        for _, pod_uid, _ in binding.pods:
            _api_uid("Deployment proof Pod UID", pod_uid)
    result = {
        (binding.namespace, binding.deployment_name): binding
        for binding in value.bindings
        if binding.namespace in _APPLICATION_NAMESPACES
    }
    if set(result) != _EXPECTED or any(binding.replicas != 1 for binding in result.values()):
        raise KilEndpointOwnershipError("deployment proof lacks the nine KIL Pod owners")
    return result


def _revalidate_service_allocation(
    value: object,
    *,
    service_network: IPv4Network,
) -> dict[tuple[str, str], tuple[str, str, tuple[str, str, int]]]:
    if type(value) is not ServiceAllocation:
        raise KilEndpointOwnershipError("service_allocation has the wrong type")
    bindings = _decode_canonical(value.bindings, "Service allocation bindings")
    configurations = _decode_canonical(
        value.configurations, "Service allocation configurations",
    )
    if len(bindings) != 9 or len(configurations) != 9:
        raise KilEndpointOwnershipError("Service allocation proof cardinality is not exact")

    by_key: dict[tuple[str, str], tuple[str, str]] = {}
    service_uids: set[str] = set()
    service_ips: set[str] = set()
    for raw in bindings:
        row = _closed(
            raw, frozenset({"namespace", "name", "uid", "cluster_ip"}),
            "Service binding",
        )
        namespace = _name("Service namespace", row["namespace"])
        name = _name("Service name", row["name"])
        uid = _api_uid("Service UID", row["uid"])
        cluster_ip = _service_address(
            "Service cluster IP", row["cluster_ip"], service_network,
        )
        key = (namespace, name)
        if key in by_key or uid in service_uids or cluster_ip in service_ips:
            raise KilEndpointOwnershipError("Service bindings collide")
        by_key[key] = (uid, cluster_ip)
        service_uids.add(uid)
        service_ips.add(cluster_ip)
    if set(by_key) != _EXPECTED or bindings != sorted(
        bindings, key=lambda row: (row["namespace"], row["name"]),
    ):
        raise KilEndpointOwnershipError("Service bindings are not the exact canonical set")

    config_ports: dict[tuple[str, str], tuple[str, str, int]] = {}
    configuration_keys: list[tuple[str, str]] = []
    run_id: str | None = None
    for raw in configurations:
        row = _closed(raw, frozenset({"apiVersion", "kind", "metadata", "spec"}),
                      "Service configuration")
        _constant("Service.apiVersion", row["apiVersion"], "v1")
        _constant("Service.kind", row["kind"], "Service")
        metadata = _closed(
            row["metadata"],
            frozenset({"annotations", "creationTimestamp", "labels", "name",
                       "namespace", "resourceVersion", "uid"}),
            "Service metadata",
        )
        try:
            _metadata(deepcopy(metadata), ("v1", "Service"))
        except (TypeError, ValueError, UnicodeError, AttributeError) as error:
            raise KilEndpointOwnershipError(
                "Service metadata no longer satisfies its producer validator",
            ) from error
        namespace = _name("Service metadata namespace", metadata["namespace"])
        name = _name("Service metadata name", metadata["name"])
        key = (namespace, name)
        if key not in by_key or key in config_ports:
            raise KilEndpointOwnershipError("Service configuration identity is unexpected")
        if _api_uid("Service metadata UID", metadata["uid"]) != by_key[key][0]:
            raise KilEndpointOwnershipError("Service configuration UID differs from binding")
        _uint64("Service resourceVersion", metadata["resourceVersion"])
        _text("Service creationTimestamp", metadata["creationTimestamp"],
              max_chars=64, max_bytes=64)
        labels = _closed(
            metadata["labels"],
            frozenset({"kil.dev/managed", "kil.dev/role", "kil.dev/track"}),
            "Service labels",
        )
        expected_labels = {
            "kil.dev/managed": "v3b2",
            "kil.dev/role": name,
            "kil.dev/track": _TRACK_BY_NAMESPACE.get(namespace),
        }
        if labels != expected_labels:
            raise KilEndpointOwnershipError("Service labels differ from the fixed KIL identity")
        annotations = _closed(
            metadata["annotations"], frozenset({"kil.dev/run-id"}),
            "Service annotations",
        )
        candidate_run_id = _text(
            "Service run id", annotations["kil.dev/run-id"],
            max_chars=128, max_bytes=128,
        )
        if _RUN_ID.fullmatch(candidate_run_id) is None:
            raise KilEndpointOwnershipError(
                "Service run id must be v3b2- followed by 64 lowercase hex",
            )
        if run_id is None:
            run_id = candidate_run_id
        elif candidate_run_id != run_id:
            raise KilEndpointOwnershipError("Service configurations have mixed run identity")
        spec = _closed(
            row["spec"],
            frozenset({"internalTrafficPolicy", "ports", "selector",
                       "sessionAffinity", "type"}),
            "Service spec",
        )
        _constant("Service type", spec["type"], "ClusterIP")
        _constant("Service sessionAffinity", spec["sessionAffinity"], "None")
        _constant("Service internalTrafficPolicy", spec["internalTrafficPolicy"], "Cluster")
        if spec["selector"] != labels:
            raise KilEndpointOwnershipError("Service selector differs from its fixed labels")
        ports = spec["ports"]
        if type(ports) is not list or len(ports) != 1:
            raise KilEndpointOwnershipError("Service must have exactly one port")
        port = _closed(
            ports[0], frozenset({"name", "port", "protocol", "targetPort"}),
            "Service port",
        )
        if (port["name"] != "http" or port["protocol"] != "TCP"
                or type(port["port"]) is not int or port["port"] != 8080
                or type(port["targetPort"]) is not int or port["targetPort"] != 8080):
            raise KilEndpointOwnershipError("Service port differs from fixed rendered input")
        config_ports[key] = (port["name"], port["protocol"], port["targetPort"])
        configuration_keys.append(key)
    if set(config_ports) != _EXPECTED or configuration_keys != sorted(_EXPECTED):
        raise KilEndpointOwnershipError("Service configurations are incomplete")
    return {
        key: (by_key[key][0], by_key[key][1], config_ports[key])
        for key in sorted(_EXPECTED)
    }


@dataclass(frozen=True, slots=True, order=True)
class KilEndpointBinding:
    namespace: str
    service_name: str
    service_uid: str
    service_cluster_ip: str
    port_name: str
    protocol: str
    port: int
    pod_name: str
    pod_uid: str
    pod_resource_version: str
    pod_ip: str
    endpoint_slice_name: str
    endpoint_slice_uid: str
    endpoint_slice_resource_version: str

    def __post_init__(self) -> None:
        try:
            namespace = _name("binding namespace", self.namespace)
            service_name = _name("binding Service name", self.service_name)
            if (namespace, service_name) not in _EXPECTED:
                raise KilEndpointOwnershipError("binding identity is not a fixed KIL Service")
            _api_uid("binding Service UID", self.service_uid)
            _service_address(
                "binding Service IP", self.service_cluster_ip,
                IPv4Network("10.96.0.0/16"),
            )
            if (self.port_name, self.protocol, self.port) != ("http", "TCP", 8080):
                raise KilEndpointOwnershipError("binding port is not the fixed resolved port")
            _name("binding Pod name", self.pod_name)
            if re.fullmatch(
                re.escape(service_name) + r"-[a-z0-9]{10}-[a-z0-9]{5}",
                self.pod_name,
            ) is None:
                raise KilEndpointOwnershipError("binding Pod name is not Deployment generated")
            _api_uid("binding Pod UID", self.pod_uid)
            _uint64("binding Pod resourceVersion", self.pod_resource_version)
            _pod_address(
                "binding Pod IP", self.pod_ip, IPv4Network("10.244.0.0/16"),
            )
            slice_name = _name("binding EndpointSlice name", self.endpoint_slice_name)
            prefix = service_name + "-"
            if (not slice_name.startswith(prefix)
                    or _SLICE_SUFFIX.fullmatch(slice_name[len(prefix):]) is None):
                raise KilEndpointOwnershipError("EndpointSlice name lacks its supplemental prefix")
            _api_uid("binding EndpointSlice UID", self.endpoint_slice_uid)
            _uint64(
                "binding EndpointSlice resourceVersion",
                self.endpoint_slice_resource_version,
            )
            if len({self.service_uid, self.pod_uid, self.endpoint_slice_uid}) != 3:
                raise KilEndpointOwnershipError("binding incarnation UIDs collide")
        except KilEndpointOwnershipError:
            raise
        except (TypeError, ValueError, UnicodeError, OverflowError, AttributeError) as error:
            raise KilEndpointOwnershipError("invalid KIL endpoint binding") from error


@dataclass(frozen=True, slots=True)
class KilEndpointOwnershipProof:
    application_namespaces: tuple[str, ...]
    node_name: str
    bindings: tuple[KilEndpointBinding, ...]
    runtime_contract_complete: bool = False

    def __post_init__(self) -> None:
        try:
            if (type(self.application_namespaces) is not tuple
                    or self.application_namespaces != _APPLICATION_NAMESPACES):
                raise KilEndpointOwnershipError("application_namespaces are not exact and canonical")
            _constant("node_name", self.node_name, _NODE_NAME)
            if type(self.bindings) is not tuple or len(self.bindings) != 9:
                raise KilEndpointOwnershipError("proof must contain exactly nine bindings")
            if any(type(binding) is not KilEndpointBinding for binding in self.bindings):
                raise KilEndpointOwnershipError("proof bindings have the wrong type")
            for binding in self.bindings:
                binding.__post_init__()
            if self.bindings != tuple(sorted(self.bindings)):
                raise KilEndpointOwnershipError("proof bindings are not canonical")
            if {(binding.namespace, binding.service_name) for binding in self.bindings} != _EXPECTED:
                raise KilEndpointOwnershipError("proof bindings are not the exact KIL set")
            for attribute in ("service_uid", "service_cluster_ip", "pod_uid",
                              "pod_ip", "endpoint_slice_uid"):
                values = [getattr(binding, attribute) for binding in self.bindings]
                if len(set(values)) != len(values):
                    raise KilEndpointOwnershipError(f"proof {attribute} values collide")
            slice_identities = [
                (binding.namespace, binding.endpoint_slice_name)
                for binding in self.bindings
            ]
            if len(set(slice_identities)) != len(slice_identities):
                raise KilEndpointOwnershipError("proof EndpointSlice identities collide")
            all_uids = [binding.service_uid for binding in self.bindings]
            all_uids.extend(binding.pod_uid for binding in self.bindings)
            all_uids.extend(binding.endpoint_slice_uid for binding in self.bindings)
            if len(set(all_uids)) != len(all_uids):
                raise KilEndpointOwnershipError("proof UIDs collide across resource families")
            if type(self.runtime_contract_complete) is not bool or self.runtime_contract_complete:
                raise KilEndpointOwnershipError("endpoint proof cannot complete the runtime contract")
        except KilEndpointOwnershipError:
            raise
        except (TypeError, ValueError, UnicodeError, OverflowError, AttributeError) as error:
            raise KilEndpointOwnershipError("invalid KIL endpoint proof") from error


def _validate(
    pods: object,
    endpoint_slices: object,
    profile: object,
    deployment_proof: object,
    service_allocation: object,
) -> KilEndpointOwnershipProof:
    checked_profile = _revalidate_profile(profile)
    pod_rows = _precheck_rows(pods, label="pods")
    slice_rows = _precheck_rows(endpoint_slices, label="endpoint_slices")
    deployment_bindings = _revalidate_deployment_proof(deployment_proof)
    service_bindings = _revalidate_service_allocation(
        service_allocation,
        service_network=IPv4Network(checked_profile.service_subnet),
    )
    pod_network = IPv4Network(checked_profile.pod_subnet)

    pods_by_key: dict[tuple[str, str], tuple[str, str, str]] = {}
    pod_uids: set[str] = set()
    pod_ips: set[str] = set()
    for raw in pod_rows:
        row = _closed(raw, _POD_KEYS, "Pod")
        _constant("Pod.apiVersion", row["apiVersion"], "v1")
        _constant("Pod.kind", row["kind"], "Pod")
        namespace = _name("Pod.namespace", row["namespace"])
        name = _name("Pod.name", row["name"])
        uid = _api_uid("Pod.uid", row["uid"])
        resource_version = _uint64("Pod.resourceVersion", row["resourceVersion"])
        key = (namespace, name)
        if key in pods_by_key or uid in pod_uids:
            raise KilEndpointOwnershipError("Pod identities and UIDs must be unique")
        _constant("Pod.nodeName", row["nodeName"], _NODE_NAME)
        _constant("Pod.phase", row["phase"], "Running")
        if row["deletionTimestamp"] is not None:
            raise KilEndpointOwnershipError("ready KIL Pod must not be deleting")
        pod_ip = _pod_address("Pod.podIP", row["podIP"], pod_network)
        pod_ips_value = row["podIPs"]
        if type(pod_ips_value) is not list or len(pod_ips_value) != 1:
            raise KilEndpointOwnershipError("Pod.podIPs must contain one address")
        pod_ip_row = _closed(pod_ips_value[0], _POD_IP_KEYS, "Pod.podIPs entry")
        if _pod_address("Pod.podIPs[0].ip", pod_ip_row["ip"], pod_network) != pod_ip:
            raise KilEndpointOwnershipError("Pod.podIP and podIPs differ")
        conditions = row["conditions"]
        if type(conditions) is not list or len(conditions) != 1:
            raise KilEndpointOwnershipError("Pod condition projection must contain Ready exactly once")
        condition = _closed(conditions[0], _POD_CONDITION_KEYS, "Pod Ready condition")
        if condition != {"type": "Ready", "status": "True"}:
            raise KilEndpointOwnershipError("Pod Ready condition is not exact true")
        if pod_ip in pod_ips:
            raise KilEndpointOwnershipError("Pod IPs must be unique")
        pods_by_key[key] = (uid, resource_version, pod_ip)
        pod_uids.add(uid)
        pod_ips.add(pod_ip)

    expected_pods: dict[tuple[str, str], tuple[str, str, str, str]] = {}
    for service_key, binding in deployment_bindings.items():
        if len(binding.pods) != 1:
            raise KilEndpointOwnershipError("KIL Deployment does not have one Pod")
        pod_name, pod_uid, pod_rv = binding.pods[0]
        expected_pods[(binding.namespace, pod_name)] = (
            binding.deployment_name, pod_uid, pod_rv, binding.namespace,
        )
    if set(pods_by_key) != set(expected_pods):
        raise KilEndpointOwnershipError("Pod observation is not the exact owned KIL Pod set")
    pod_by_service: dict[tuple[str, str], tuple[str, str, str, str]] = {}
    for pod_key, expected in expected_pods.items():
        service_name, expected_uid, expected_rv, namespace = expected
        uid, resource_version, pod_ip = pods_by_key[pod_key]
        if (uid, resource_version) != (expected_uid, expected_rv):
            raise KilEndpointOwnershipError("Pod incarnation differs from Deployment proof")
        pod_by_service[(namespace, service_name)] = (
            pod_key[1], uid, resource_version, pod_ip,
        )

    slice_by_service: dict[tuple[str, str], tuple[str, str, str, str, str, str, int]] = {}
    slice_uids: set[str] = set()
    slice_names: set[tuple[str, str]] = set()
    for raw in slice_rows:
        row = _closed(raw, _SLICE_KEYS, "EndpointSlice")
        _constant("EndpointSlice.apiVersion", row["apiVersion"], "discovery.k8s.io/v1")
        _constant("EndpointSlice.kind", row["kind"], "EndpointSlice")
        namespace = _name("EndpointSlice.namespace", row["namespace"])
        name = _name("EndpointSlice.name", row["name"])
        uid = _api_uid("EndpointSlice.uid", row["uid"])
        resource_version = _uint64(
            "EndpointSlice.resourceVersion", row["resourceVersion"],
        )
        if (namespace, name) in slice_names or uid in slice_uids:
            raise KilEndpointOwnershipError("EndpointSlice identity or UID collides")
        labels = _closed(row["labels"], _LABEL_KEYS, "EndpointSlice labels")
        service_name = _name(
            "EndpointSlice Service label", labels["kubernetes.io/service-name"],
        )
        _constant(
            "EndpointSlice manager label",
            labels["endpointslice.kubernetes.io/managed-by"], _MANAGER,
        )
        service_key = (namespace, service_name)
        service = service_bindings.get(service_key)
        if service is None or service_key in slice_by_service:
            raise KilEndpointOwnershipError("EndpointSlice Service identity is unexpected or duplicated")
        prefix = service_name + "-"
        if (not name.startswith(prefix)
                or _SLICE_SUFFIX.fullmatch(name[len(prefix):]) is None):
            raise KilEndpointOwnershipError("EndpointSlice generated name is not supplemental-bound")
        owner = _closed(row["ownerReference"], _OWNER_KEYS, "EndpointSlice ownerReference")
        _constant("EndpointSlice owner apiVersion", owner["apiVersion"], "v1")
        _constant("EndpointSlice owner kind", owner["kind"], "Service")
        if (_name("EndpointSlice owner name", owner["name"]) != service_name
                or _api_uid("EndpointSlice owner UID", owner["uid"]) != service[0]
                or owner["controller"] is not True
                or owner["blockOwnerDeletion"] is not True):
            raise KilEndpointOwnershipError("EndpointSlice does not have the exact Service controller owner")
        _constant("EndpointSlice.addressType", row["addressType"], "IPv4")
        ports = row["ports"]
        if type(ports) is not list or len(ports) != 1:
            raise KilEndpointOwnershipError("EndpointSlice must have one port")
        port = _closed(ports[0], _PORT_KEYS, "EndpointSlice port")
        if (port["name"] != service[2][0] or port["protocol"] != service[2][1]
                or type(port["port"]) is not int or port["port"] != service[2][2]):
            raise KilEndpointOwnershipError("EndpointSlice port differs from resolved Service port")
        endpoints = row["endpoints"]
        if type(endpoints) is not list or len(endpoints) != 1:
            raise KilEndpointOwnershipError("EndpointSlice must contain one endpoint")
        endpoint = _closed(endpoints[0], _ENDPOINT_KEYS, "EndpointSlice endpoint")
        addresses = endpoint["addresses"]
        if type(addresses) is not list or len(addresses) != 1:
            raise KilEndpointOwnershipError("EndpointSlice endpoint must have one address")
        address = _pod_address("EndpointSlice address", addresses[0], pod_network)
        conditions = _closed(
            endpoint["conditions"], _ENDPOINT_CONDITION_KEYS,
            "EndpointSlice conditions",
        )
        if conditions != {"ready": True, "serving": True, "terminating": False}:
            raise KilEndpointOwnershipError("EndpointSlice conditions differ from ready non-terminating Pod")
        target = _closed(endpoint["targetRef"], _TARGET_KEYS, "EndpointSlice targetRef")
        _constant("EndpointSlice target kind", target["kind"], "Pod")
        target_namespace = _name("EndpointSlice target namespace", target["namespace"])
        target_name = _name("EndpointSlice target name", target["name"])
        target_uid = _api_uid("EndpointSlice target UID", target["uid"])
        _constant("EndpointSlice endpoint nodeName", endpoint["nodeName"], _NODE_NAME)
        expected_pod = pod_by_service[service_key]
        if ((target_namespace, target_name, target_uid, address)
                != (namespace, expected_pod[0], expected_pod[1], expected_pod[3])):
            raise KilEndpointOwnershipError("EndpointSlice target differs from ready owned Pod")
        slice_by_service[service_key] = (
            name, uid, resource_version, address,
            port["name"], port["protocol"], port["port"],
        )
        slice_names.add((namespace, name))
        slice_uids.add(uid)
    if set(slice_by_service) != _EXPECTED:
        raise KilEndpointOwnershipError("EndpointSlice observation is not the exact KIL set")
    bindings: list[KilEndpointBinding] = []
    for key in sorted(_EXPECTED):
        service_uid, cluster_ip, _ = service_bindings[key]
        pod_name, pod_uid, pod_rv, pod_ip = pod_by_service[key]
        slice_name, slice_uid, slice_rv, address, port_name, protocol, port = slice_by_service[key]
        if address != pod_ip:
            raise KilEndpointOwnershipError("EndpointSlice address differs from Pod IP")
        bindings.append(KilEndpointBinding(
            namespace=key[0], service_name=key[1], service_uid=service_uid,
            service_cluster_ip=cluster_ip, port_name=port_name,
            protocol=protocol, port=port, pod_name=pod_name, pod_uid=pod_uid,
            pod_resource_version=pod_rv, pod_ip=pod_ip,
            endpoint_slice_name=slice_name, endpoint_slice_uid=slice_uid,
            endpoint_slice_resource_version=slice_rv,
        ))
    return KilEndpointOwnershipProof(
        _APPLICATION_NAMESPACES, _NODE_NAME, tuple(bindings), False,
    )


def validate_kil_endpoint_ownership(
    *,
    pods: list[dict],
    endpoint_slices: list[dict],
    profile: V3B2Profile,
    deployment_proof: DeploymentOwnershipProof,
    service_allocation: ServiceAllocation,
) -> KilEndpointOwnershipProof:
    """Validate the fixed nine KIL ready Pod-to-Service endpoint relations."""
    try:
        return _validate(
            pods, endpoint_slices, profile, deployment_proof, service_allocation,
        )
    except KilEndpointOwnershipError:
        raise
    except (TypeError, ValueError, UnicodeError, OverflowError, AttributeError,
            KeyError, IndexError) as error:
        raise KilEndpointOwnershipError("invalid KIL endpoint ownership projection") from error


__all__ = (
    "KilEndpointBinding",
    "KilEndpointOwnershipError",
    "KilEndpointOwnershipProof",
    "validate_kil_endpoint_ownership",
)
