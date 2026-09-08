"""Closed, immutable inventory attestations for the V3B-2a cluster boundary."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
import json
from pathlib import PurePosixPath
import re

_MAX_KUBECTL_BYTES = 8 * 1024 * 1024
_MAX_JSON_DEPTH = 64
_MAX_JSON_ITEMS = 250_000
_MAX_INTEGER_DIGITS = 128
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
_USERNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}")
_CALICO_PINS = {
    "calico-cni": (
        "quay.io/calico/cni@sha256:"
        "1cfc6aa9c4dad3575fdf36b78185fd7d68bcd4acc95778f8342be4fb6a851a14"
    ),
    "calico-node": (
        "quay.io/calico/node@sha256:"
        "f4fafd8ba641d96c5a91b01e5a519117d77d55dee789a3562ba3ad4aa125b36a"
    ),
    "calico-kube-controllers": (
        "quay.io/calico/kube-controllers@sha256:"
        "adf0ac895796d21bca5383bc81c4cd2614be3a4308085b47857d7999f4cc2b1f"
    ),
}
_CALICO_CONTAINER_CONTRACT = {
    ("calico-cni", "init", "upgrade-ipam"): _CALICO_PINS["calico-cni"],
    ("calico-cni", "init", "install-cni"): _CALICO_PINS["calico-cni"],
    ("calico-node", "init", "ebpf-bootstrap"): _CALICO_PINS["calico-node"],
    ("calico-node", "regular", "calico-node"): _CALICO_PINS["calico-node"],
    (
        "calico-kube-controllers", "regular", "calico-kube-controllers",
    ): _CALICO_PINS["calico-kube-controllers"],
}


def _closed_object_keys() -> tuple[tuple[str, str, str, str], ...]:
    """Return rendered objects plus the fixed Calico system projections."""
    records: list[tuple[str, str, str, str]] = []
    for namespace in ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed"):
        records.append(("v1", "Namespace", "", namespace))
        records.extend(("v1", "ServiceAccount", namespace, role) for role in ("driver", "envoy", "authz", "target"))
        records.extend(("v1", "ConfigMap", namespace, name) for name in ("authz-config", "target-config", "envoy-config"))
        records.extend(("networking.k8s.io/v1", "NetworkPolicy", namespace, name) for name in ("default-deny", "allow-dns", "allow-driver-egress-envoy", "allow-envoy-ingress-egress", "allow-backends-ingress-envoy"))
        records.extend(("v1", "Service", namespace, role) for role in ("envoy", "authz", "target"))
        records.extend(("apps/v1", "Deployment", namespace, role) for role in ("envoy", "authz", "target"))
        records.append(("v1", "Pod", namespace, "driver"))
    records.extend((
        ("v1", "Namespace", "", "kube-system"),
        ("apps/v1", "DaemonSet", "kube-system", "calico-node"),
        ("apps/v1", "Deployment", "kube-system", "calico-kube-controllers"),
        ("v1", "ServiceAccount", "kube-system", "calico-node"),
        ("v1", "ServiceAccount", "kube-system", "calico-cni-plugin"),
        ("v1", "ServiceAccount", "kube-system", "calico-kube-controllers"),
        ("v1", "ConfigMap", "kube-system", "calico-config"),
    ))
    return tuple(sorted(records))


_EXPECTED_OBJECT_KEYS = _closed_object_keys()
_EXPECTED_WORKLOAD_KEYS = tuple(sorted(
    (namespace, "regular", role)
    for namespace in ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed")
    for role in ("driver", "envoy", "authz", "target")
))
_EXPECTED_ENDPOINT_KEYS = tuple(sorted(
    (namespace, service, "http", "TCP", 8080)
    for namespace in ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed")
    for service in ("envoy", "authz", "target")
))
_POD_NETWORK = IPv4Network("10.244.0.0/16")


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
    image_role: str
    container_type: str
    namespace: str
    pod: str
    container: str
    uid: str
    resource_version: str
    image: str
    image_id: str
    ready: bool
    container_id: str = ""

    def __post_init__(self) -> None:
        if type(self.image_role) is not str or self.image_role not in {
            "workload", *_CALICO_PINS,
        }:
            raise InventoryError("image_role must be an exact reviewed role")
        if type(self.container_type) is not str or self.container_type not in {
            "init", "regular",
        }:
            raise InventoryError("container_type must be exact init or regular")
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
        if self.image.rsplit(":", 1)[-1].removeprefix("sha256-") != self.image_id.rsplit(":", 1)[-1]:
            raise InventoryError("requested and realized image digests differ")
        if type(self.ready) is not bool:
            raise InventoryError("ready condition must be an exact boolean")
        if self.container_id and re.fullmatch(r"(?:docker|containerd)://[0-9a-f]{64}", self.container_id) is None:
            raise InventoryError("containerID must be an exact runtime incarnation")


@dataclass(frozen=True, slots=True)
class RuntimePodIdentity:
    namespace: str
    pod: str
    uid: str
    resource_version: str
    container: str
    image: str
    image_id: str
    ready: bool
    container_id: str = ""
    terminated_exit_code: int | None = None

    def __post_init__(self) -> None:
        for name in ("namespace", "pod", "uid", "resource_version", "container"):
            _exact_string(name, getattr(self, name))
        if not (_DIGEST_REFERENCE.fullmatch(self.image) or _KIL_CONTENT_REFERENCE.fullmatch(self.image)):
            raise InventoryError("runtime Pod image is not immutable")
        if _IMAGE_ID.fullmatch(self.image_id) is None:
            raise InventoryError("runtime Pod realized image identity is invalid")
        if self.image.rsplit(":", 1)[-1].removeprefix("sha256-") != self.image_id.rsplit(":", 1)[-1]:
            raise InventoryError("runtime Pod requested and realized images differ")
        if type(self.ready) is not bool:
            raise InventoryError("runtime Pod readiness must be exact")
        if re.fullmatch(r"(?:docker|containerd)://[0-9a-f]{64}", self.container_id) is None:
            raise InventoryError("runtime Pod containerID is invalid")
        if self.terminated_exit_code is not None and (
            type(self.terminated_exit_code) is not int
            or not 0 <= self.terminated_exit_code <= 255
        ):
            raise InventoryError("runtime Pod termination exit code is invalid")


@dataclass(frozen=True, slots=True, order=True)
class EndpointIdentity:
    source_kind: str
    source_name: str
    namespace: str
    service: str
    addresses: tuple[str, ...]
    port_name: str
    protocol: str
    port: int

    def __post_init__(self) -> None:
        if type(self.source_kind) is not str or self.source_kind not in {
            "Endpoints", "EndpointSlice",
        }:
            raise InventoryError("endpoint source_kind is not reviewed")
        _exact_string("endpoint source_name", self.source_name)
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
    if type(record.docker_host) is not str or not record.docker_host.startswith("unix://"):
        raise InventoryError("Docker host must be explicitly bound to kil-v3-lab")
    socket_text = record.docker_host.removeprefix("unix://")
    socket_path = PurePosixPath(socket_text)
    if (
        str(socket_path) != socket_text
        or len(socket_path.parts) != 6
        or socket_path.parts[0:2] != ("/", "Users")
        or _USERNAME.fullmatch(socket_path.parts[2]) is None
        or socket_path.parts[3:] != (".colima", "kil-v3-lab", "docker.sock")
    ):
        raise InventoryError("Docker host must be explicitly bound to kil-v3-lab")
    _exact_string_tuple("namespaces", record.namespaces)
    if record.namespaces != _ALLOWED_NAMESPACES:
        raise InventoryError("namespace inventory differs from the closed allowlist")
    _sorted_records("objects", record.objects, ObjectIdentity)
    _sorted_records("pod_images", record.pod_images, PodImageIdentity)
    _sorted_records("endpoints", record.endpoints, EndpointIdentity)
    object_keys = tuple(
        (item.api_version, item.kind, item.namespace, item.name)
        for item in record.objects
    )
    if object_keys != _EXPECTED_OBJECT_KEYS:
        raise InventoryError("object inventory differs from the fixed topology oracle")
    workload = tuple(item for item in record.pod_images if item.image_role == "workload")
    workload_keys = tuple(sorted(
        (item.namespace, item.container_type, item.container) for item in workload
    ))
    if workload_keys != _EXPECTED_WORKLOAD_KEYS:
        raise InventoryError("application workload container inventory is not exact")
    for item in workload:
        if item.container == "driver":
            valid_pod = item.pod == "driver"
        else:
            valid_pod = re.fullmatch(
                rf"{re.escape(item.container)}-"
                r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?",
                item.pod,
            ) is not None
        if not valid_pod:
            raise InventoryError("application workload Pod family is not exact")
    calico = tuple(item for item in record.pod_images if item.image_role != "workload")
    actual_calico_contract = tuple(sorted(
        (item.image_role, item.container_type, item.container) for item in calico
    ))
    if actual_calico_contract != tuple(sorted(_CALICO_CONTAINER_CONTRACT)):
        raise InventoryError("Calico container inventory or multiplicity differs from the manifest")
    for item in calico:
        key = (item.image_role, item.container_type, item.container)
        pod_prefix = (
            "calico-kube-controllers-"
            if item.image_role == "calico-kube-controllers"
            else "calico-node-"
        )
        if (
            item.namespace != "kube-system"
            or not item.pod.startswith(pod_prefix)
            or item.image != _CALICO_CONTAINER_CONTRACT[key]
        ):
            raise InventoryError("Calico image differs from the exact profile pin")
    endpoint_keys = tuple(
        (item.namespace, item.service, item.port_name, item.protocol, item.port)
        for item in record.endpoints
    )
    if len(set(endpoint_keys)) != len(endpoint_keys):
        raise InventoryError("ambiguous Endpoints/EndpointSlice source for Service port")
    source_kinds: dict[tuple[str, str], set[str]] = {}
    for item in record.endpoints:
        source_kinds.setdefault((item.namespace, item.service), set()).add(
            item.source_kind
        )
    if any(len(kinds) != 1 for kinds in source_kinds.values()):
        raise InventoryError("ambiguous mixed Endpoints and EndpointSlice Service sources")
    if tuple(sorted(endpoint_keys)) != _EXPECTED_ENDPOINT_KEYS:
        raise InventoryError("endpoint inventory differs from the fixed Service oracle")
    for item in record.endpoints:
        if item.source_kind == "Endpoints":
            valid_source_name = item.source_name == item.service
        else:
            valid_source_name = re.fullmatch(
                rf"{re.escape(item.service)}-"
                r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?",
                item.source_name,
            ) is not None
        if not valid_source_name:
            raise InventoryError("endpoint source name is outside the Service family")
        for address in item.addresses:
            try:
                parsed_address = IPv4Address(address)
            except ValueError as error:
                raise InventoryError("endpoint address is not canonical IPv4") from error
            if str(parsed_address) != address or parsed_address not in _POD_NETWORK:
                raise InventoryError("endpoint address is not canonical or outside the Pod CIDR")
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


def _bounded_integer(text: str) -> int:
    digits = text[1:] if text.startswith("-") else text
    if len(digits) > _MAX_INTEGER_DIGITS:
        raise ValueError("JSON integer exceeds the inventory grammar")
    return int(text)


def _reject_constant(text: str) -> object:
    raise ValueError(f"non-finite JSON constant is forbidden: {text}")


def _validate_json_tree(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 0)]
    count = 0
    while stack:
        current, depth = stack.pop()
        if depth > _MAX_JSON_DEPTH:
            raise InventoryError("kubectl JSON exceeds the depth limit")
        count += 1
        if count > _MAX_JSON_ITEMS:
            raise InventoryError("kubectl JSON exceeds the item limit")
        if current is None or type(current) in {str, int, bool}:
            continue
        if type(current) is list:
            stack.extend((item, depth + 1) for item in current)
            continue
        if type(current) is dict:
            if any(type(key) is not str for key in current):
                raise InventoryError("kubectl JSON object keys must be exact strings")
            stack.extend((item, depth + 1) for item in current.values())
            continue
        raise InventoryError("kubectl JSON contains a non-JSON value")


def _canonical_inventory_bytes(value: object) -> bytes:
    try:
        text = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        return (text + "\n").encode("utf-8", errors="strict")
    except (TypeError, ValueError, RecursionError, UnicodeEncodeError) as error:
        raise InventoryError(f"kubectl JSON cannot be canonicalized: {error}") from error


def _decode_list(payload: bytes, expected_kind: str) -> list[dict[str, object]]:
    if type(payload) is not bytes or len(payload) > _MAX_KUBECTL_BYTES:
        raise InventoryError("kubectl response must be bytes of at most 8 MiB")
    _exact_string("expected_kind", expected_kind)
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_closed_object,
            parse_int=_bounded_integer,
            parse_constant=_reject_constant,
        )
    except InventoryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise InventoryError(f"invalid kubectl JSON: {error}") from error
    _validate_json_tree(value)
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
    if payload != _canonical_inventory_bytes(value):
        raise InventoryError("kubectl response must be canonical JSON followed by one newline")
    items = envelope["items"]
    identities: set[tuple[str, str, str, str]] = set()
    for value_item in items:
        if type(value_item) is not dict:
            raise InventoryError("List item must be an exact JSON object")
        metadata_value = value_item.get("metadata")
        if type(metadata_value) is not dict:
            raise InventoryError("List item metadata must be an exact JSON object")
        identity = (
            value_item.get("apiVersion"), value_item.get("kind"),
            metadata_value.get("namespace"), metadata_value.get("name"),
        )
        if any(type(part) is not str for part in identity):
            raise InventoryError("List item identity fields must be exact strings")
        if value_item["kind"] != expected_kind:
            raise InventoryError("List item kind differs from expected_kind")
        if identity in identities:
            raise InventoryError("Kubernetes List contains duplicate object identities")
        identities.add(identity)
    return items


def _runtime_metadata(value: object, *, labels: bool = False) -> dict[str, object]:
    fields = {"namespace", "name", "uid", "resourceVersion"}
    if labels:
        fields.add("labels")
    metadata = _keys("runtime metadata", value, frozenset(fields))
    for name in ("namespace", "name", "uid", "resourceVersion"):
        _exact_string(f"metadata {name}", metadata[name])
    return metadata


def _exact_array(label: str, value: object) -> list[object]:
    if type(value) is not list:
        raise InventoryError(f"{label} must be an exact JSON array")
    return value


def _parse_pod_image_list(payload: bytes) -> tuple[PodImageIdentity, ...]:
    records: list[PodImageIdentity] = []
    for item in _decode_list(payload, "Pod"):
        closed = _keys(
            "Pod", item, frozenset({"apiVersion", "kind", "metadata", "status"})
        )
        if closed["apiVersion"] != "v1":
            raise InventoryError("Pod apiVersion is not v1")
        metadata = _runtime_metadata(closed["metadata"])
        status = _keys(
            "Pod status", closed["status"],
            frozenset({"conditions", "containerStatuses", "initContainerStatuses"}),
        )
        conditions = _exact_array("Pod conditions", status["conditions"])
        if len(conditions) != 1:
            raise InventoryError("Pod must have exactly one projected Ready condition")
        condition = _keys(
            "Pod condition", conditions[0], frozenset({"type", "status"})
        )
        if (
            type(condition["type"]) is not str
            or type(condition["status"]) is not str
            or condition["type"] != "Ready"
            or condition["status"] not in {"True", "False"}
        ):
            raise InventoryError("unknown or ambiguous Pod condition")
        ready = condition["status"] == "True"
        seen_containers: set[str] = set()
        observed_placements: set[tuple[str, str]] = set()
        for field in ("containerStatuses", "initContainerStatuses"):
            container_type = "regular" if field == "containerStatuses" else "init"
            for raw in _exact_array(field, status[field]):
                container = _keys(
                    "container status", raw, frozenset({"name", "image", "imageID", "containerID"})
                )
                name = _exact_string("container name", container["name"])
                if name in seen_containers:
                    raise InventoryError("duplicate container status")
                seen_containers.add(name)
                role = {
                    "upgrade-ipam": "calico-cni",
                    "install-cni": "calico-cni",
                    "ebpf-bootstrap": "calico-node",
                    "calico-node": "calico-node",
                    "calico-kube-controllers": "calico-kube-controllers",
                }.get(name, "workload")
                if (
                    metadata["namespace"] == "kube-system"
                    and (
                        metadata["name"].startswith("calico-node-")
                        or metadata["name"].startswith("calico-kube-controllers-")
                    )
                    and role == "workload"
                ):
                    raise InventoryError("unknown Calico Pod container role")
                observed_placements.add((container_type, name))
                records.append(PodImageIdentity(
                    role, container_type, metadata["namespace"], metadata["name"], name,
                    metadata["uid"], metadata["resourceVersion"],
                    container["image"], container["imageID"], ready,
                    _exact_string("containerID", container.get("containerID")),
                ))
        if metadata["namespace"] == "kube-system":
            if metadata["name"].startswith("calico-node-"):
                expected_placements = {
                    ("init", "upgrade-ipam"), ("init", "install-cni"),
                    ("init", "ebpf-bootstrap"), ("regular", "calico-node"),
                }
                if observed_placements != expected_placements:
                    raise InventoryError("Calico node Pod container inventory is not exact")
            elif metadata["name"].startswith("calico-kube-controllers-"):
                if observed_placements != {("regular", "calico-kube-controllers")}:
                    raise InventoryError("Calico controller Pod container inventory is not exact")
    ordered = tuple(sorted(records))
    if len(set(ordered)) != len(ordered):
        raise InventoryError("duplicate Pod image identity")
    return ordered


def _parse_endpoint_list(
    payload: bytes, expected_kind: str
) -> tuple[EndpointIdentity, ...]:
    if type(expected_kind) is not str or expected_kind not in {"Endpoints", "EndpointSlice"}:
        raise InventoryError("endpoint source kind is not reviewed")
    records: list[EndpointIdentity] = []
    for item in _decode_list(payload, expected_kind):
        if expected_kind == "Endpoints":
            closed = _keys(
                "Endpoints", item,
                frozenset({"apiVersion", "kind", "metadata", "subsets"}),
            )
            if closed["apiVersion"] != "v1":
                raise InventoryError("Endpoints apiVersion is not v1")
            metadata = _runtime_metadata(closed["metadata"])
            subsets = _exact_array("Endpoints subsets", closed["subsets"])
            if len(subsets) != 1:
                raise InventoryError("ambiguous Endpoints subsets")
            subset = _keys(
                "Endpoints subset", subsets[0], frozenset({"addresses", "ports"})
            )
            addresses = tuple(sorted(
                _exact_string(
                    "endpoint address",
                    _keys("endpoint address", address, frozenset({"ip"}))["ip"],
                )
                for address in _exact_array("endpoint addresses", subset["addresses"])
            ))
            ports = _exact_array("endpoint ports", subset["ports"])
            service = metadata["name"]
        else:
            closed = _keys(
                "EndpointSlice", item,
                frozenset({
                    "apiVersion", "kind", "metadata", "addressType", "endpoints", "ports",
                }),
            )
            if closed["apiVersion"] != "discovery.k8s.io/v1" or closed["addressType"] != "IPv4":
                raise InventoryError("EndpointSlice apiVersion or addressType is not reviewed")
            metadata = _runtime_metadata(closed["metadata"], labels=True)
            labels = _keys(
                "EndpointSlice labels", metadata["labels"],
                frozenset({"kubernetes.io/service-name"}),
            )
            service = _exact_string(
                "EndpointSlice service label", labels["kubernetes.io/service-name"]
            )
            address_values: list[str] = []
            for endpoint in _exact_array("EndpointSlice endpoints", closed["endpoints"]):
                endpoint_value = _keys(
                    "EndpointSlice endpoint", endpoint,
                    frozenset({"addresses", "conditions"}),
                )
                condition = _keys(
                    "EndpointSlice conditions", endpoint_value["conditions"],
                    frozenset({"ready"}),
                )
                if type(condition["ready"]) is not bool or condition["ready"] is not True:
                    raise InventoryError("EndpointSlice has unknown or unready condition")
                address_values.extend(
                    _exact_string("EndpointSlice address", address)
                    for address in _exact_array("EndpointSlice addresses", endpoint_value["addresses"])
                )
            addresses = tuple(sorted(address_values))
            ports = _exact_array("EndpointSlice ports", closed["ports"])
        if not addresses or len(set(addresses)) != len(addresses):
            raise InventoryError("endpoint addresses are empty or ambiguous")
        for raw_port in ports:
            port = _keys(
                "endpoint port", raw_port, frozenset({"name", "protocol", "port"})
            )
            records.append(EndpointIdentity(
                expected_kind, metadata["name"], metadata["namespace"], service,
                addresses, port["name"], port["protocol"], port["port"],
            ))
    ordered = tuple(sorted(records))
    keys = tuple(
        (item.namespace, item.service, item.port_name, item.protocol, item.port)
        for item in ordered
    )
    if len(set(keys)) != len(keys):
        raise InventoryError("ambiguous endpoint sources or Service ports")
    return ordered


def _parse_policy_list(payload: bytes) -> tuple[PolicyEdge, ...]:
    records: list[PolicyEdge] = []
    for item in _decode_list(payload, "NetworkPolicy"):
        closed = _keys(
            "NetworkPolicy", item,
            frozenset({"apiVersion", "kind", "metadata", "spec"}),
        )
        if closed["apiVersion"] != "networking.k8s.io/v1":
            raise InventoryError("NetworkPolicy apiVersion is not reviewed")
        metadata = _runtime_metadata(closed["metadata"])
        spec = _keys(
            "policy projection", closed["spec"],
            frozenset({"sourceRoles", "direction", "peers", "ports"}),
        )
        if spec["direction"] != "Egress":
            raise InventoryError("policy direction projection must be exact Egress")
        source_roles = tuple(_exact_array("sourceRoles", spec["sourceRoles"]))
        peers = _exact_array("policy peers", spec["peers"])
        if len(peers) != 1:
            raise InventoryError("policy peer projection is ambiguous")
        peer = _keys("policy peer", peers[0], frozenset({"namespace", "roles"}))
        destination_roles = tuple(_exact_array("destination roles", peer["roles"]))
        protocol_ports: list[tuple[str, int]] = []
        for raw_port in _exact_array("policy ports", spec["ports"]):
            port = _keys("policy port", raw_port, frozenset({"protocol", "port"}))
            protocol_ports.append((port["protocol"], port["port"]))
        edge = PolicyEdge(
            metadata["namespace"], source_roles, peer["namespace"],
            destination_roles, tuple(sorted(protocol_ports)),
        )
        if edge not in _EXPECTED_POLICY_GRAPH:
            raise InventoryError("policy selector, peer, direction, or port is not reviewed")
        records.append(edge)
    ordered = tuple(sorted(records))
    if len(set(ordered)) != len(ordered):
        raise InventoryError("duplicate policy edge")
    return ordered


def _parse_calico_workload_list(
    payload: bytes, expected_kind: str
) -> tuple[int, int, tuple[tuple[str, str, str], ...]]:
    if type(expected_kind) is not str or expected_kind not in {"DaemonSet", "Deployment"}:
        raise InventoryError("Calico workload kind is not reviewed")
    items = _decode_list(payload, expected_kind)
    if len(items) != 1:
        raise InventoryError("Calico workload inventory must contain exactly one object")
    item = _keys(
        "Calico workload", items[0],
        frozenset({"apiVersion", "kind", "metadata", "spec", "status"}),
    )
    if item["apiVersion"] != "apps/v1":
        raise InventoryError("Calico workload apiVersion is not apps/v1")
    metadata = _runtime_metadata(item["metadata"])
    expected_name = "calico-node" if expected_kind == "DaemonSet" else "calico-kube-controllers"
    if metadata["namespace"] != "kube-system" or metadata["name"] != expected_name:
        raise InventoryError("Calico workload identity is not reviewed")
    spec = _keys(
        "Calico workload spec", item["spec"],
        frozenset({"containers", "initContainers"}),
    )
    images: list[tuple[str, str, str]] = []
    for field in ("containers", "initContainers"):
        container_type = "regular" if field == "containers" else "init"
        for raw_container in _exact_array(field, spec[field]):
            container = _keys(
                "Calico container", raw_container, frozenset({"name", "image"})
            )
            name = _exact_string("Calico container name", container["name"])
            role = {
                "upgrade-ipam": "calico-cni",
                "install-cni": "calico-cni",
                "ebpf-bootstrap": "calico-node",
                "calico-node": "calico-node",
                "calico-kube-controllers": "calico-kube-controllers",
            }.get(name)
            contract_key = (role, container_type, name)
            if (
                role is None
                or contract_key not in _CALICO_CONTAINER_CONTRACT
                or container["image"] != _CALICO_CONTAINER_CONTRACT[contract_key]
            ):
                raise InventoryError("Calico container image does not match a profile pin")
            images.append((container_type, name, container["image"]))
    if len(set((placement, name) for placement, name, _ in images)) != len(images):
        raise InventoryError("duplicate Calico container identity")
    expected_containers = (
        {
            ("init", "upgrade-ipam"), ("init", "install-cni"),
            ("init", "ebpf-bootstrap"), ("regular", "calico-node"),
        }
        if expected_kind == "DaemonSet"
        else {("regular", "calico-kube-controllers")}
    )
    if {(placement, name) for placement, name, _ in images} != expected_containers:
        raise InventoryError("Calico workload container inventory is not exact")
    status_fields = (
        frozenset({"desiredNumberScheduled", "numberReady"})
        if expected_kind == "DaemonSet"
        else frozenset({"replicas", "readyReplicas"})
    )
    status = _keys("Calico workload status", item["status"], status_fields)
    if expected_kind == "DaemonSet":
        desired_name, ready_name = "desiredNumberScheduled", "numberReady"
    else:
        desired_name, ready_name = "replicas", "readyReplicas"
    desired, ready = status[desired_name], status[ready_name]
    if type(desired) is not int or type(ready) is not int or desired < 0 or ready < 0:
        raise InventoryError("Calico readiness counts must be exact nonnegative integers")
    return desired, ready, tuple(sorted(images))


def parse_calico_runtime_workload(
    payload: bytes, expected_kind: str
) -> tuple[int, int, tuple[tuple[str, str, str], ...]]:
    """Parse one canonical Calico workload projection and require exact readiness."""
    if type(payload) is not bytes or len(payload) > _MAX_KUBECTL_BYTES:
        raise InventoryError("Calico kubectl response must be bounded bytes")
    try:
        item = json.loads(
            payload.decode("utf-8", errors="strict"), object_pairs_hook=_closed_object,
            parse_int=_bounded_integer, parse_constant=_reject_constant,
        )
    except InventoryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise InventoryError("invalid Calico kubectl JSON") from error
    _validate_json_tree(item)
    if payload != _canonical_inventory_bytes(item):
        raise InventoryError("Calico kubectl response must be canonical JSON followed by one newline")
    envelope = {
        "apiVersion": "v1", "items": [item], "kind": "List",
        "metadata": {"resourceVersion": ""},
    }
    desired, ready, images = _parse_calico_workload_list(
        _canonical_inventory_bytes(envelope), expected_kind,
    )
    if desired != 1 or ready != 1:
        raise InventoryError("Calico workload is not exactly one ready replica")
    return desired, ready, images


def parse_kubectl_list(payload: bytes, expected_kind: str) -> tuple[ObjectIdentity, ...]:
    """Parse one bounded canonical projection of a Kubernetes List."""

    records: list[ObjectIdentity] = []
    for item in _decode_list(payload, expected_kind):
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
    return ordered


def parse_runtime_pod_identity(
    payload: bytes,
    *,
    expected_namespace: str,
    expected_pod: str,
    expected_container: str,
    expected_image: str,
    require_ready: bool = True,
) -> RuntimePodIdentity:
    """Normalize one bounded, duplicate-safe kubectl Pod into a closed identity."""
    if type(payload) is not bytes or len(payload) > _MAX_KUBECTL_BYTES:
        raise InventoryError("kubectl Pod response must be bounded bytes")
    for label, value in (
        ("expected namespace", expected_namespace), ("expected Pod", expected_pod),
        ("expected container", expected_container), ("expected image", expected_image),
    ):
        _exact_string(label, value)
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"), object_pairs_hook=_closed_object,
            parse_int=_bounded_integer, parse_constant=_reject_constant,
        )
    except InventoryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise InventoryError("invalid kubectl Pod JSON") from error
    _validate_json_tree(value)
    if type(require_ready) is not bool:
        raise InventoryError("runtime Pod readiness mode is invalid")
    def required(label: str, item: object, names: frozenset[str]) -> dict[str, object]:
        if type(item) is not dict or not names.issubset(item):
            raise InventoryError(f"{label} lacks required fields")
        return item
    pod = required("runtime Pod", value, frozenset({"apiVersion", "kind", "metadata", "status"}))
    if pod["apiVersion"] != "v1" or pod["kind"] != "Pod":
        raise InventoryError("runtime Pod type is not exact")
    metadata = required(
        "runtime Pod metadata", pod["metadata"],
        frozenset({"name", "namespace", "resourceVersion", "uid"}),
    )
    if metadata["namespace"] != expected_namespace or metadata["name"] != expected_pod:
        raise InventoryError("runtime Pod identity is not the requested object")
    status = required(
        "runtime Pod status", pod["status"],
        frozenset({"conditions", "containerStatuses"}),
    )
    conditions = _exact_array("runtime Pod conditions", status["conditions"])
    ready_conditions = [item for item in conditions if type(item) is dict and item.get("type") == "Ready"]
    if len(ready_conditions) != 1:
        raise InventoryError("runtime Pod Ready condition is ambiguous")
    condition = required("runtime Pod condition", ready_conditions[0], frozenset({"status", "type"}))
    containers = _exact_array("runtime Pod containers", status["containerStatuses"])
    matches = [item for item in containers if type(item) is dict and item.get("name") == expected_container]
    if len(matches) != 1:
        raise InventoryError("runtime Pod container identity is ambiguous")
    container = required(
        "runtime Pod container", matches[0],
        frozenset({"containerID", "image", "imageID", "name", "ready"}),
    )
    ready = condition.get("status") == "True" and container.get("ready") is True
    if (
        condition.get("status") not in {"True", "False"}
        or container["image"] != expected_image
        or (require_ready and not ready)
    ):
        raise InventoryError("runtime Pod is not ready with the expected image")
    terminated_exit_code = None
    state = container.get("state")
    if state is not None:
        state = required("runtime Pod container state", state, frozenset())
        if set(state) == {"terminated"}:
            terminated = required(
                "runtime Pod terminated state", state["terminated"],
                frozenset({"exitCode"}),
            )
            terminated_exit_code = terminated["exitCode"]
        elif set(state) not in ({"running"}, {"waiting"}):
            raise InventoryError("runtime Pod container state is ambiguous")
    return RuntimePodIdentity(
        str(metadata["namespace"]), str(metadata["name"]),
        _exact_string("runtime Pod UID", metadata["uid"]),
        _exact_string("runtime Pod resourceVersion", metadata["resourceVersion"]),
        str(container["name"]), str(container["image"]),
        _exact_string("runtime Pod imageID", container["imageID"]), ready,
        _exact_string("runtime Pod containerID", container["containerID"]),
        terminated_exit_code,
    )


def parse_ready_endpoint_slice(
    payload: bytes, *, expected_namespace: str, expected_service: str,
) -> tuple[EndpointIdentity, str]:
    """Normalize one exact ready service EndpointSlice and its Pod UID."""
    if type(payload) is not bytes or len(payload) > _MAX_KUBECTL_BYTES:
        raise InventoryError("EndpointSlice response must be bounded bytes")
    _exact_string("expected namespace", expected_namespace)
    if expected_service not in {"envoy", "authz", "target"}:
        raise InventoryError("EndpointSlice service is not reviewed")
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"), object_pairs_hook=_closed_object,
            parse_int=_bounded_integer, parse_constant=_reject_constant,
        )
    except InventoryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise InventoryError("EndpointSlice JSON is invalid") from error
    _validate_json_tree(value)

    def required(label: str, item: object, fields: frozenset[str]) -> dict[str, object]:
        if type(item) is not dict or not fields.issubset(item):
            raise InventoryError(f"{label} lacks required fields")
        return item

    decoded = required("EndpointSlice response", value, frozenset({"apiVersion", "kind"}))
    if decoded["apiVersion"] == "v1" and decoded["kind"] == "List":
        items = _exact_array("EndpointSlice List items", decoded.get("items"))
        if len(items) != 1:
            raise InventoryError("EndpointSlice List cardinality is not exact")
        value = items[0]
    root = required(
        "EndpointSlice", value,
        frozenset({"apiVersion", "kind", "metadata", "addressType", "ports", "endpoints"}),
    )
    metadata = required("EndpointSlice metadata", root["metadata"], frozenset({"name", "namespace", "labels"}))
    labels = required("EndpointSlice labels", metadata["labels"], frozenset({"kubernetes.io/service-name"}))
    if (
        root["apiVersion"] != "discovery.k8s.io/v1"
        or root["kind"] != "EndpointSlice"
        or root["addressType"] != "IPv4"
        or metadata["namespace"] != expected_namespace
        or labels["kubernetes.io/service-name"] != expected_service
    ):
        raise InventoryError("EndpointSlice identity is not exact")
    ports = _exact_array("EndpointSlice ports", root["ports"])
    endpoints = _exact_array("EndpointSlice endpoints", root["endpoints"])
    if len(ports) != 1 or len(endpoints) != 1:
        raise InventoryError("EndpointSlice cardinality is not exact")
    port = required("EndpointSlice port", ports[0], frozenset({"name", "port", "protocol"}))
    endpoint = required("EndpointSlice endpoint", endpoints[0], frozenset({"addresses", "conditions", "targetRef"}))
    conditions = required("EndpointSlice conditions", endpoint["conditions"], frozenset({"ready"}))
    target = required("EndpointSlice target", endpoint["targetRef"], frozenset({"kind", "name", "namespace", "uid"}))
    addresses = tuple(sorted(_exact_array("EndpointSlice addresses", endpoint["addresses"])))
    if (
        port["name"] != "http" or port["protocol"] != "TCP" or port["port"] != 8080
        or conditions["ready"] is not True or target["kind"] != "Pod"
        or target["namespace"] != expected_namespace
        or not str(target["name"]).startswith(expected_service + "-")
    ):
        raise InventoryError("EndpointSlice is not exactly ready")
    identity = EndpointIdentity(
        "EndpointSlice", _exact_string("EndpointSlice name", metadata["name"]),
        expected_namespace, expected_service, addresses, "http", "TCP", 8080,
    )
    return identity, _exact_string("EndpointSlice target UID", target["uid"])


def parse_runtime_inventory(
    payload: bytes,
    *,
    profile: object,
    workload: object,
    node_container_id: str,
    docker_host: str,
) -> InventorySnapshot:
    """Parse the one closed multi-resource kubectl projection into typed inventory."""
    from kil.v3b2_contracts import V3B2Profile
    from kil.v3b2_manifests import (
        WorkloadIdentity, expected_object_keys, expected_policy_graph, render_objects,
    )

    if type(profile) is not V3B2Profile or type(workload) is not WorkloadIdentity:
        raise InventoryError("runtime inventory contracts are not exact")
    if type(payload) is not bytes or len(payload) > _MAX_KUBECTL_BYTES:
        raise InventoryError("runtime inventory response must be bounded bytes")
    try:
        root = json.loads(
            payload.decode("utf-8", errors="strict"), object_pairs_hook=_closed_object,
            parse_int=_bounded_integer, parse_constant=_reject_constant,
        )
    except InventoryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise InventoryError("runtime inventory JSON is invalid") from error
    _validate_json_tree(root)
    if type(root) is not dict or root.get("apiVersion") != "v1" or root.get("kind") != "List" or type(root.get("items")) is not list:
        raise InventoryError("runtime inventory is not a Kubernetes List")
    expected_keys = set(_EXPECTED_OBJECT_KEYS)
    indexed: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for raw in root["items"]:
        if type(raw) is not dict or type(raw.get("metadata")) is not dict:
            raise InventoryError("runtime inventory item identity is invalid")
        metadata = raw["metadata"]
        key = (raw.get("apiVersion"), raw.get("kind"), metadata.get("namespace", ""), metadata.get("name"))
        if any(type(part) is not str for part in key) or key in indexed:
            raise InventoryError("runtime inventory item identity is ambiguous")
        indexed[key] = raw
    if not expected_keys.issubset(indexed):
        raise InventoryError("runtime inventory omits a fixed topology object")
    objects = tuple(sorted(ObjectIdentity(
        key[0], key[1], key[2], key[3],
        _exact_string("object UID", indexed[key]["metadata"].get("uid")),
        _exact_string("object resourceVersion", indexed[key]["metadata"].get("resourceVersion")),
    ) for key in expected_keys))
    namespaces = tuple(sorted(key[3] for key in indexed if key[0:2] == ("v1", "Namespace")))
    expected_namespaces = tuple(sorted((*profile.system_namespaces, *profile.application_namespaces)))
    if namespaces != expected_namespaces:
        raise InventoryError("namespace inventory differs from the closed allowlist")

    def reviewed_platform_object(key: tuple[str, str, str, str]) -> bool:
        api_version, kind, namespace, name = key
        if api_version == "v1" and kind == "ServiceAccount" and name == "default" and namespace in expected_namespaces:
            return True
        if api_version == "v1" and kind == "ConfigMap" and name == "kube-root-ca.crt" and namespace in expected_namespaces:
            return True
        if key in {
            ("v1", "Service", "default", "kubernetes"),
            ("v1", "Endpoints", "default", "kubernetes"),
            ("v1", "Service", "kube-system", "kube-dns"),
            ("v1", "Endpoints", "kube-system", "kube-dns"),
            ("apps/v1", "Deployment", "kube-system", "coredns"),
            ("apps/v1", "DaemonSet", "kube-system", "kube-proxy"),
            ("v1", "ServiceAccount", "kube-system", "coredns"),
            ("v1", "ServiceAccount", "kube-system", "kube-proxy"),
            ("apps/v1", "Deployment", "local-path-storage", "local-path-provisioner"),
            ("v1", "ServiceAccount", "local-path-storage", "local-path-provisioner-service-account"),
            ("v1", "ConfigMap", "local-path-storage", "local-path-config"),
        }:
            return True
        patterns = {
            ("v1", "Pod", "kube-system"): (
                r"coredns-[a-z0-9]+-[a-z0-9]+",
                r"etcd-kil-v3-lab-control-plane",
                r"kube-apiserver-kil-v3-lab-control-plane",
                r"kube-controller-manager-kil-v3-lab-control-plane",
                r"kube-proxy-[a-z0-9]+",
                r"kube-scheduler-kil-v3-lab-control-plane",
            ),
            ("v1", "Pod", "local-path-storage"): (
                r"local-path-provisioner-[a-z0-9]+(?:-[a-z0-9]+)?",
            ),
            ("discovery.k8s.io/v1", "EndpointSlice", "default"): (
                r"kubernetes(?:-[a-z0-9]+)?",
            ),
            ("discovery.k8s.io/v1", "EndpointSlice", "kube-system"): (
                r"kube-dns-[a-z0-9]+",
            ),
        }
        return any(
            re.fullmatch(pattern, name)
            for pattern in patterns.get((api_version, kind, namespace), ())
        )

    allowed = set(expected_keys)
    allowed.update(
        key for key in indexed
        if key[0:3] == ("v1", "Namespace", "") and key[3] in profile.system_namespaces
    )
    allowed.update(key for key in indexed if reviewed_platform_object(key))
    pod_images: list[PodImageIdentity] = []
    expected_kil = "kil.local/kil-v3b2:sha256-" + workload.kil_image_id.removeprefix("sha256:")
    for key, item in sorted(indexed.items()):
        if key[1] != "Pod" or key in expected_keys:
            continue
        if reviewed_platform_object(key):
            continue
        namespace, pod_name = key[2], key[3]
        app_role = next((role for role in ("envoy", "authz", "target") if namespace in profile.application_namespaces and pod_name.startswith(role + "-")), None)
        calico_pod = namespace == "kube-system" and (pod_name.startswith("calico-node-") or pod_name.startswith("calico-kube-controllers-"))
        if app_role is None and not calico_pod:
            raise InventoryError("runtime inventory contains an extra Pod family")
        allowed.add(key)
        metadata, status = item.get("metadata"), item.get("status")
        if type(metadata) is not dict or type(status) is not dict:
            raise InventoryError("runtime Pod projection is invalid")
        ready_conditions = [entry for entry in status.get("conditions", []) if type(entry) is dict and entry.get("type") == "Ready"] if type(status.get("conditions")) is list else []
        if len(ready_conditions) != 1 or ready_conditions[0].get("status") != "True":
            raise InventoryError("runtime Pod is not exactly ready")
        seen: set[tuple[str, str]] = set()
        for field, placement in (("initContainerStatuses", "init"), ("containerStatuses", "regular")):
            rows = status.get(field, [])
            if type(rows) is not list:
                raise InventoryError("runtime Pod status list is invalid")
            for row in rows:
                if type(row) is not dict:
                    raise InventoryError("runtime container status is invalid")
                name, image, image_id = row.get("name"), row.get("image"), row.get("imageID")
                if type(name) is not str or (placement, name) in seen:
                    raise InventoryError("runtime container identity is ambiguous")
                seen.add((placement, name))
                role = {"upgrade-ipam": "calico-cni", "install-cni": "calico-cni", "ebpf-bootstrap": "calico-node", "calico-node": "calico-node", "calico-kube-controllers": "calico-kube-controllers"}.get(name, "workload")
                expected_image = dict(profile.calico_images).get({"calico-cni": "cni", "calico-node": "node", "calico-kube-controllers": "kube_controllers"}.get(role, ""))
                if role == "workload":
                    expected_image = workload.envoy_image_digest if name == "envoy" else expected_kil
                if image != expected_image or type(image_id) is not str:
                    raise InventoryError("runtime container image differs from the content identity")
                pod_images.append(PodImageIdentity(
                    role, placement, namespace, pod_name, name,
                    _exact_string("Pod UID", metadata.get("uid")),
                    _exact_string("Pod resourceVersion", metadata.get("resourceVersion")),
                    image, image_id, True, _exact_string("containerID", row.get("containerID")),
                ))
    # Driver Pods are rendered objects and carry their runtime images directly.
    for namespace in profile.application_namespaces:
        key = ("v1", "Pod", namespace, "driver")
        item = indexed[key]
        metadata, status = item.get("metadata"), item.get("status")
        if type(metadata) is not dict or type(status) is not dict or type(status.get("containerStatuses")) is not list or len(status["containerStatuses"]) != 1:
            raise InventoryError("driver Pod status is invalid")
        row = status["containerStatuses"][0]
        if type(row) is not dict or row.get("name") != "driver" or row.get("image") != expected_kil:
            raise InventoryError("driver Pod image is invalid")
        pod_images.append(PodImageIdentity(
            "workload", "regular", namespace, "driver", "driver",
            _exact_string("driver UID", metadata.get("uid")),
            _exact_string("driver resourceVersion", metadata.get("resourceVersion")),
            expected_kil, _exact_string("driver imageID", row.get("imageID")), True,
            _exact_string("driver containerID", row.get("containerID")),
        ))
    for namespace in profile.application_namespaces:
        for role in ("driver", "envoy", "authz", "target"):
            matches = [
                item for item in pod_images
                if item.namespace == namespace and item.container == role
                and item.container_type == "regular"
            ]
            if len(matches) != 1:
                raise InventoryError("runtime workload Pod topology is not exact")
    endpoints: list[EndpointIdentity] = []
    for key, item in sorted(indexed.items()):
        if key[1] != "Endpoints":
            continue
        if reviewed_platform_object(key):
            continue
        allowed.add(key)
        if key[2] not in profile.application_namespaces or key[3] not in {"envoy", "authz", "target"}:
            raise InventoryError("runtime endpoint is outside the fixed services")
        subsets = item.get("subsets")
        if type(subsets) is not list or len(subsets) != 1 or type(subsets[0]) is not dict:
            raise InventoryError("runtime endpoint subset is ambiguous")
        addresses = tuple(sorted(entry.get("ip") for entry in subsets[0].get("addresses", []) if type(entry) is dict))
        ports = subsets[0].get("ports")
        if type(ports) is not list:
            raise InventoryError("runtime endpoint ports are invalid")
        for port in ports:
            if type(port) is not dict:
                raise InventoryError("runtime endpoint port is invalid")
            endpoints.append(EndpointIdentity("Endpoints", key[3], key[2], key[3], addresses, port.get("name"), port.get("protocol"), port.get("port")))
    ready_slices: set[tuple[str, str]] = set()
    for key, item in sorted(indexed.items()):
        if key[1] != "EndpointSlice" or reviewed_platform_object(key):
            continue
        namespace = key[2]
        service = next(
            (role for role in ("envoy", "authz", "target") if key[3].startswith(role + "-")),
            None,
        )
        if namespace not in profile.application_namespaces or service is None:
            raise InventoryError("runtime EndpointSlice is outside the fixed services")
        try:
            endpoint, target_uid = parse_ready_endpoint_slice(
                _canonical_inventory_bytes(item),
                expected_namespace=namespace, expected_service=service,
            )
        except InventoryError:
            raise InventoryError("runtime EndpointSlice is invalid") from None
        if (namespace, service) in ready_slices:
            raise InventoryError("runtime EndpointSlice service is duplicated")
        target_matches = [
            image for image in pod_images
            if image.namespace == namespace and image.container == service
            and image.uid == target_uid
        ]
        if len(target_matches) != 1 or endpoint.addresses not in {
            current.addresses for current in endpoints
            if current.namespace == namespace and current.service == service
        }:
            raise InventoryError("runtime EndpointSlice target identity differs from the ready Pod")
        ready_slices.add((namespace, service))
        allowed.add(key)
    if ready_slices != {
        (namespace, role)
        for namespace in profile.application_namespaces
        for role in ("envoy", "authz", "target")
    }:
        raise InventoryError("runtime EndpointSlice topology is incomplete")
    rendered = json.loads(render_objects(profile, workload))["items"]
    expected_specs = {(item["metadata"]["namespace"], item["metadata"]["name"]): item["spec"] for item in rendered if item["kind"] == "NetworkPolicy"}
    actual_specs = {(key[2], key[3]): item.get("spec") for key, item in indexed.items() if key[1] == "NetworkPolicy"}
    if actual_specs != expected_specs:
        raise InventoryError("runtime policy graph differs from rendered content")
    if set(indexed) != allowed:
        raise InventoryError("runtime inventory contains extra object identities")
    node_status = indexed[("apps/v1", "DaemonSet", "kube-system", "calico-node")].get("status")
    controller_status = indexed[("apps/v1", "Deployment", "kube-system", "calico-kube-controllers")].get("status")
    if type(node_status) is not dict or type(controller_status) is not dict:
        raise InventoryError("Calico readiness projection is invalid")
    cluster_uid = next(item.uid for item in objects if (item.api_version, item.kind, item.namespace, item.name) == ("v1", "Namespace", "", "kube-system"))
    return InventorySnapshot(
        cluster_uid, node_container_id, docker_host, namespaces, objects,
        tuple(sorted(pod_images)), tuple(sorted(endpoints)),
        tuple(sorted(PolicyEdge(
            edge.namespace, edge.source_roles, edge.destination_namespace,
            edge.destination_roles, edge.protocol_ports,
        ) for edge in expected_policy_graph(profile))),
        node_status.get("desiredNumberScheduled"), node_status.get("numberReady"),
        controller_status.get("replicas"), controller_status.get("readyReplicas"),
    )


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
    if current.calico_node_desired != 1 or current.calico_node_ready != 1:
        raise InventoryError("Calico node DaemonSet is not exactly one ready node")
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
    "RuntimePodIdentity",
    "parse_kubectl_list",
    "parse_calico_runtime_workload",
    "parse_runtime_pod_identity",
    "parse_ready_endpoint_slice",
    "parse_runtime_inventory",
    "stable_source",
    "validate_inventory",
)
