"""Closed, immutable inventory attestations for the V3B-2a cluster boundary."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from .canonical import canonical_json


_MAX_KUBECTL_BYTES = 8 * 1024 * 1024
_NODE_ID = re.compile(r"[0-9a-f]{64}")
_DIGEST_REFERENCE = re.compile(r"[^@\s]+@sha256:[0-9a-f]{64}")
_KIL_CONTENT_REFERENCE = re.compile(r"kil\.local/kil-v3b2:sha256-[0-9a-f]{64}")
_IMAGE_ID = re.compile(
    r"(?:docker-pullable://[^@\s]+@sha256:[0-9a-f]{64}|"
    r"docker://sha256:[0-9a-f]{64})"
)
_ALLOWED_NAMESPACES = (
    "default",
    "kil-v3-baseline",
    "kil-v3-local-reduce",
    "kil-v3-signed",
    "kube-node-lease",
    "kube-public",
    "kube-system",
    "local-path-storage",
)


def _closed_policy_graph() -> tuple[PolicyEdge, ...]:
    records: list[PolicyEdge] = []
    for namespace in ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed"):
        records.extend((
            PolicyEdge(namespace, ("driver",), namespace, ("envoy",), (("TCP", 8080),)),
            PolicyEdge(namespace, ("envoy",), namespace, ("authz",), (("TCP", 8080),)),
            PolicyEdge(namespace, ("envoy",), namespace, ("target",), (("TCP", 8080),)),
            PolicyEdge(
                namespace, ("driver", "envoy"), "kube-system", ("kube-dns",),
                (("TCP", 53), ("UDP", 53)),
            ),
        ))
    return tuple(sorted(records))


class InventoryError(ValueError):
    """Raised when runtime inventory is open, ambiguous, or identity-unstable."""


def _exact_string(label: str, value: object, *, empty: bool = False) -> str:
    if type(value) is not str or (not empty and not value):
        qualifier = "" if empty else " nonempty"
        raise InventoryError(f"{label} must be an exact{qualifier} string")
    return value


def _exact_string_tuple(label: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple or any(type(item) is not str or not item for item in value):
        raise InventoryError(f"{label} must be an exact tuple of exact strings")
    if tuple(sorted(value)) != value or len(set(value)) != len(value):
        raise InventoryError(f"{label} must be duplicate-free and sorted")
    return value


def _sorted_records(label: str, value: object, record_type: type) -> tuple:
    if type(value) is not tuple or any(type(item) is not record_type for item in value):
        raise InventoryError(f"{label} must contain only exact {record_type.__name__} records")
    for item in value:
        item.__post_init__()
    if tuple(sorted(value)) != value or len(set(value)) != len(value):
        raise InventoryError(f"{label} must be duplicate-free and sorted")
    return value


@dataclass(frozen=True, slots=True, order=True)
class ObjectIdentity:
    api_version: str
    kind: str
    namespace: str
    name: str
    uid: str
    resource_version: str

    def __post_init__(self) -> None:
        _exact_string("api_version", self.api_version)
        _exact_string("kind", self.kind)
        _exact_string("namespace", self.namespace, empty=True)
        _exact_string("name", self.name)
        _exact_string("uid", self.uid)
        _exact_string("resource_version", self.resource_version)


@dataclass(frozen=True, slots=True, order=True)
class PodImageIdentity:
    namespace: str
    pod: str
    container: str
    uid: str
    resource_version: str
    image: str
    image_id: str
    ready: bool

    def __post_init__(self) -> None:
        for label in ("namespace", "pod", "container", "uid", "resource_version"):
            _exact_string(label, getattr(self, label))
        _exact_string("image", self.image)
        if not (
            _DIGEST_REFERENCE.fullmatch(self.image)
            or _KIL_CONTENT_REFERENCE.fullmatch(self.image)
        ):
            raise InventoryError("image must be an immutable digest or KIL content reference")
        if type(self.image_id) is not str or _IMAGE_ID.fullmatch(self.image_id) is None:
            raise InventoryError("imageID must be an immutable realized digest identity")
        if type(self.ready) is not bool:
            raise InventoryError("ready condition must be an exact boolean")


@dataclass(frozen=True, slots=True, order=True)
class EndpointIdentity:
    namespace: str
    service: str
    addresses: tuple[str, ...]
    port_name: str
    protocol: str
    port: int

    def __post_init__(self) -> None:
        _exact_string("endpoint namespace", self.namespace)
        _exact_string("endpoint service", self.service)
        _exact_string_tuple("endpoint addresses", self.addresses)
        if not self.addresses:
            raise InventoryError("endpoint addresses must not be empty")
        _exact_string("endpoint port_name", self.port_name)
        if type(self.protocol) is not str or self.protocol != "TCP":
            raise InventoryError("endpoint protocol must be exact TCP")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise InventoryError("endpoint port must be an exact integer in range")


@dataclass(frozen=True, slots=True, order=True)
class PolicyEdge:
    namespace: str
    source_roles: tuple[str, ...]
    destination_namespace: str
    destination_roles: tuple[str, ...]
    protocol_ports: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        _exact_string("policy namespace", self.namespace)
        _exact_string_tuple("source_roles", self.source_roles)
        _exact_string("destination namespace", self.destination_namespace)
        _exact_string_tuple("destination_roles", self.destination_roles)
        if not self.source_roles or not self.destination_roles:
            raise InventoryError("policy roles must not be empty")
        if type(self.protocol_ports) is not tuple or not self.protocol_ports:
            raise InventoryError("protocol_ports must be an exact nonempty tuple")
        for pair in self.protocol_ports:
            if (
                type(pair) is not tuple
                or len(pair) != 2
                or type(pair[0]) is not str
                or pair[0] not in {"TCP", "UDP"}
                or type(pair[1]) is not int
                or not 1 <= pair[1] <= 65535
            ):
                raise InventoryError("policy protocol_ports contain an invalid entry")
        if (
            tuple(sorted(self.protocol_ports)) != self.protocol_ports
            or len(set(self.protocol_ports)) != len(self.protocol_ports)
        ):
            raise InventoryError("protocol_ports must be duplicate-free and sorted")


_EXPECTED_POLICY_GRAPH = _closed_policy_graph()


def _validate_common(record: object) -> None:
    _exact_string("cluster_incarnation_uid", record.cluster_incarnation_uid)
    if type(record.node_container_id) is not str or _NODE_ID.fullmatch(record.node_container_id) is None:
        raise InventoryError("Kind node container ID must be 64 lowercase hexadecimal characters")
    if (
        type(record.docker_host) is not str
        or not record.docker_host.startswith("unix:///")
        or not record.docker_host.endswith("/.colima/kil-v3-lab/docker.sock")
    ):
        raise InventoryError("Docker host must be explicitly bound to kil-v3-lab")
    _exact_string_tuple("namespaces", record.namespaces)
    if record.namespaces != _ALLOWED_NAMESPACES:
        raise InventoryError("namespace inventory differs from the closed allowlist")
    _sorted_records("objects", record.objects, ObjectIdentity)
    _sorted_records("pod_images", record.pod_images, PodImageIdentity)
    _sorted_records("endpoints", record.endpoints, EndpointIdentity)
    _sorted_records("policy_graph", record.policy_graph, PolicyEdge)
    if record.policy_graph != _EXPECTED_POLICY_GRAPH:
        raise InventoryError("policy_graph differs from the exact twelve-edge contract")
    for label in (
        "calico_node_desired", "calico_node_ready",
        "calico_controller_desired", "calico_controller_ready",
    ):
        value = getattr(record, label)
        if type(value) is not int or value < 0:
            raise InventoryError(f"{label} must be an exact nonnegative integer")


@dataclass(frozen=True, slots=True)
class InventorySnapshot:
    cluster_incarnation_uid: str
    node_container_id: str
    docker_host: str
    namespaces: tuple[str, ...]
    objects: tuple[ObjectIdentity, ...]
    pod_images: tuple[PodImageIdentity, ...]
    endpoints: tuple[EndpointIdentity, ...]
    policy_graph: tuple[PolicyEdge, ...]
    calico_node_desired: int
    calico_node_ready: int
    calico_controller_desired: int
    calico_controller_ready: int

    def __post_init__(self) -> None:
        _validate_common(self)


@dataclass(frozen=True, slots=True)
class ExpectedInventory:
    cluster_incarnation_uid: str
    node_container_id: str
    docker_host: str
    namespaces: tuple[str, ...]
    objects: tuple[ObjectIdentity, ...]
    pod_images: tuple[PodImageIdentity, ...]
    endpoints: tuple[EndpointIdentity, ...]
    policy_graph: tuple[PolicyEdge, ...]
    calico_node_desired: int
    calico_node_ready: int
    calico_controller_desired: int
    calico_controller_ready: int

    def __post_init__(self) -> None:
        _validate_common(self)


@dataclass(frozen=True, slots=True)
class InventoryAttestation:
    cluster_incarnation_uid: str
    node_container_id: str
    objects: tuple[ObjectIdentity, ...]
    pod_images: tuple[PodImageIdentity, ...]
    endpoints: tuple[EndpointIdentity, ...]
    policy_graph: tuple[PolicyEdge, ...]
    calico_ready: bool

    def __post_init__(self) -> None:
        _exact_string("cluster_incarnation_uid", self.cluster_incarnation_uid)
        if type(self.node_container_id) is not str or _NODE_ID.fullmatch(self.node_container_id) is None:
            raise InventoryError("Kind node container ID is invalid")
        _sorted_records("objects", self.objects, ObjectIdentity)
        _sorted_records("pod_images", self.pod_images, PodImageIdentity)
        _sorted_records("endpoints", self.endpoints, EndpointIdentity)
        _sorted_records("policy_graph", self.policy_graph, PolicyEdge)
        if type(self.calico_ready) is not bool:
            raise InventoryError("calico_ready must be an exact boolean")


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InventoryError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _keys(label: str, value: object, expected: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        raise InventoryError(f"{label} must be an exact JSON object")
    if any(type(key) is not str for key in value):
        raise InventoryError(f"{label} keys must be exact strings")
    if frozenset(value) != expected:
        raise InventoryError(f"{label} has missing or extra fields")
    return value


def parse_kubectl_list(payload: bytes, expected_kind: str) -> tuple[ObjectIdentity, ...]:
    """Parse one bounded canonical projection of a Kubernetes List."""

    if type(payload) is not bytes or len(payload) > _MAX_KUBECTL_BYTES:
        raise InventoryError("kubectl response must be bytes of at most 8 MiB")
    _exact_string("expected_kind", expected_kind)
    try:
        text = payload.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_closed_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InventoryError(f"invalid kubectl JSON: {error}") from error
    envelope = _keys(
        "Kubernetes List envelope", value,
        frozenset({"apiVersion", "kind", "metadata", "items"}),
    )
    if envelope["apiVersion"] != "v1" or envelope["kind"] != "List":
        raise InventoryError("kubectl response is not an exact Kubernetes List envelope")
    metadata = _keys("List metadata", envelope["metadata"], frozenset({"resourceVersion"}))
    _exact_string("List resourceVersion", metadata["resourceVersion"], empty=True)
    if type(envelope["items"]) is not list:
        raise InventoryError("List items must be an exact JSON array")
    records: list[ObjectIdentity] = []
    for item in envelope["items"]:
        closed = _keys("List item", item, frozenset({"apiVersion", "kind", "metadata"}))
        if type(closed["kind"]) is not str or closed["kind"] != expected_kind:
            raise InventoryError("List item kind differs from expected_kind")
        item_metadata = _keys(
            "item metadata", closed["metadata"],
            frozenset({"namespace", "name", "uid", "resourceVersion"}),
        )
        records.append(ObjectIdentity(
            closed["apiVersion"],
            closed["kind"],
            item_metadata["namespace"],
            item_metadata["name"],
            item_metadata["uid"],
            item_metadata["resourceVersion"],
        ))
    ordered = tuple(sorted(records))
    object_keys = tuple(
        (item.api_version, item.kind, item.namespace, item.name) for item in ordered
    )
    if len(set(object_keys)) != len(object_keys):
        raise InventoryError("Kubernetes List contains duplicate object identities")
    if payload != (canonical_json(value) + "\n").encode("utf-8"):
        raise InventoryError("kubectl response must be canonical JSON followed by one newline")
    return ordered


def _validated_snapshot(value: object, label: str) -> InventorySnapshot:
    if type(value) is not InventorySnapshot:
        raise InventoryError(f"{label} must be an exact InventorySnapshot")
    value.__post_init__()
    return value


def validate_inventory(
    snapshot: InventorySnapshot,
    expected: ExpectedInventory,
) -> InventoryAttestation:
    """Attest a closed snapshot only after exact inventory equality and readiness."""

    current = _validated_snapshot(snapshot, "snapshot")
    if type(expected) is not ExpectedInventory:
        raise InventoryError("expected must be an exact ExpectedInventory")
    expected.__post_init__()
    kube_system = tuple(
        item for item in current.objects
        if item.api_version == "v1" and item.kind == "Namespace"
        and item.namespace == "" and item.name == "kube-system"
    )
    if len(kube_system) != 1 or kube_system[0].uid != current.cluster_incarnation_uid:
        raise InventoryError("kube-system namespace UID does not bind the cluster incarnation")
    if current.calico_node_desired < 1 or current.calico_node_ready != current.calico_node_desired:
        raise InventoryError("Calico node DaemonSet is not fully ready")
    if current.calico_controller_desired != 1 or current.calico_controller_ready != 1:
        raise InventoryError("Calico kube-controllers Deployment is not exactly one ready replica")
    for field in (
        "cluster_incarnation_uid", "node_container_id", "docker_host", "namespaces",
        "objects", "pod_images", "endpoints", "policy_graph",
        "calico_node_desired", "calico_node_ready",
        "calico_controller_desired", "calico_controller_ready",
    ):
        if getattr(current, field) != getattr(expected, field):
            name = "namespace" if field == "namespaces" else field
            raise InventoryError(f"{name} inventory differs from the closed expectation")
    return InventoryAttestation(
        current.cluster_incarnation_uid,
        current.node_container_id,
        current.objects,
        current.pod_images,
        current.endpoints,
        current.policy_graph,
        True,
    )


def stable_source(before: InventorySnapshot, after: InventorySnapshot) -> InventorySnapshot:
    """Require all source and realized runtime identities to remain unchanged."""

    first = _validated_snapshot(before, "before")
    second = _validated_snapshot(after, "after")
    for field in (
        "cluster_incarnation_uid", "node_container_id", "docker_host", "namespaces",
        "objects", "pod_images", "endpoints", "policy_graph",
    ):
        if getattr(first, field) != getattr(second, field):
            raise InventoryError(f"stable source {field} identity changed")
    return second


__all__ = (
    "EndpointIdentity",
    "ExpectedInventory",
    "InventoryAttestation",
    "InventoryError",
    "InventorySnapshot",
    "ObjectIdentity",
    "PodImageIdentity",
    "PolicyEdge",
    "parse_kubectl_list",
    "stable_source",
    "validate_inventory",
)
