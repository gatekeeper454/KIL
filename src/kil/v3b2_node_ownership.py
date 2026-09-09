"""Closed, non-runtime proof of the V3B-2a node and generated-Pod joins."""

from __future__ import annotations

from dataclasses import dataclass
import re


__all__ = (
    "NodeOwnershipError",
    "DaemonPodBinding",
    "StaticPodBinding",
    "NodeOwnershipProof",
    "validate_node_ownership",
)


_CLUSTER = "kil-v3-lab"
_NODE = "kil-v3-lab-control-plane"
_NAMESPACE = "kube-system"
_DAEMONS = ("calico-node", "kube-proxy")
_COMPONENTS = ("etcd", "kube-apiserver", "kube-controller-manager", "kube-scheduler")
_UINT64_MAX = 2**64 - 1
_UID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_RV = re.compile(r"[1-9][0-9]{0,19}")
_DNS = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
# Pinned kubelet producer: FNV-128a is hex-encoded as the static Pod UID,
# then copied into config.hash and config.mirror. These are opaque relationship
# identifiers; equality does not independently verify a manifest digest.
# https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/config/common.go
# https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/pod/mirror_client.go
_STATIC_CONFIG_HASH = re.compile(r"[0-9a-f]{32}")
_DAEMON_SUFFIX = re.compile(r"[a-z0-9]{5}")
_NODE_KEYS = frozenset(("apiVersion", "kind", "name", "uid", "resourceVersion"))
_DAEMON_SET_KEYS = frozenset((
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "desiredNumberScheduled",
))
_DAEMON_POD_KEYS = frozenset((
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "nodeName", "ownerReference",
))
_STATIC_POD_KEYS = frozenset((
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "nodeName", "component", "configSource", "configHash", "mirrorHash",
    "ownerReference",
))
_DAEMON_OWNER_KEYS = frozenset((
    "apiVersion", "kind", "name", "uid", "controller", "blockOwnerDeletion",
))
# mirror_client.go creates a Node controller reference without blockOwnerDeletion.
_STATIC_OWNER_KEYS = frozenset(("apiVersion", "kind", "name", "uid", "controller"))


class NodeOwnershipError(ValueError):
    """The node/owner projection is open, malformed, or not joined by UID."""


def _utf8(value: str) -> bytes:
    return value.encode("utf-8")


def _text(label: str, value: object, maximum: int = 253) -> str:
    if type(value) is not str or not value:
        raise NodeOwnershipError(f"{label} must be an exact nonempty string")
    if len(value) > maximum:
        raise NodeOwnershipError(f"{label} is unbounded")
    try:
        encoded = _utf8(value)
    except UnicodeEncodeError as error:
        raise NodeOwnershipError(f"{label} is not a Unicode scalar sequence") from error
    if len(encoded) > maximum:
        raise NodeOwnershipError(f"{label} is unbounded")
    return value


def _literal(label: str, value: object, expected: str) -> str:
    text = _text(label, value)
    if text != expected:
        raise NodeOwnershipError(f"{label} is not the reviewed identity")
    return text


def _dns(label: str, value: object) -> str:
    text = _text(label, value)
    if _DNS.fullmatch(text) is None:
        raise NodeOwnershipError(f"{label} is not a conservative DNS name")
    return text


def _uid(value: object) -> str:
    text = _text("UID", value, 128)
    if _UID.fullmatch(text) is None:
        raise NodeOwnershipError("UID is not a bounded opaque API identity")
    return text


def _rv(value: object) -> str:
    text = _text("resourceVersion", value, 20)
    if _RV.fullmatch(text) is None or int(text) > _UINT64_MAX:
        raise NodeOwnershipError("resourceVersion is not a canonical positive uint64")
    return text


def _static_config_hash(label: str, value: object) -> str:
    text = _text(label, value, 32)
    if _STATIC_CONFIG_HASH.fullmatch(text) is None:
        raise NodeOwnershipError(f"{label} is not a 32-character lowercase kubelet identifier")
    return text


def _daemon_pod_name(daemon: str, value: object) -> str:
    name = _dns("daemon Pod name", value)
    prefix = daemon + "-"
    if not name.startswith(prefix) or _DAEMON_SUFFIX.fullmatch(name[len(prefix):]) is None:
        raise NodeOwnershipError("daemon Pod name is not the exact generated form")
    return name


@dataclass(frozen=True, slots=True, order=True)
class DaemonPodBinding:
    namespace: str
    daemon_set_name: str
    daemon_set_uid: str
    daemon_set_resource_version: str
    pod_name: str
    pod_uid: str
    pod_resource_version: str
    node_name: str

    def __post_init__(self) -> None:
        _literal("DaemonSet namespace", self.namespace, _NAMESPACE)
        daemon = _dns("DaemonSet name", self.daemon_set_name)
        if daemon not in _DAEMONS:
            raise NodeOwnershipError("DaemonSet identity is not reviewed")
        _uid(self.daemon_set_uid)
        _rv(self.daemon_set_resource_version)
        _daemon_pod_name(daemon, self.pod_name)
        _uid(self.pod_uid)
        _rv(self.pod_resource_version)
        _literal("node name", self.node_name, _NODE)
        if self.daemon_set_uid == self.pod_uid:
            raise NodeOwnershipError("DaemonSet and Pod UIDs are not unique")


@dataclass(frozen=True, slots=True, order=True)
class StaticPodBinding:
    component: str
    pod_name: str
    pod_uid: str
    pod_resource_version: str
    node_name: str
    owner_node_uid: str
    config_hash: str
    mirror_hash: str

    def __post_init__(self) -> None:
        component = _dns("static component", self.component)
        if component not in _COMPONENTS:
            raise NodeOwnershipError("static component is not reviewed")
        _literal("static Pod name", self.pod_name, f"{component}-{_NODE}")
        _uid(self.pod_uid)
        _rv(self.pod_resource_version)
        _literal("node name", self.node_name, _NODE)
        _uid(self.owner_node_uid)
        config_hash = _static_config_hash("config hash", self.config_hash)
        if _static_config_hash("mirror hash", self.mirror_hash) != config_hash:
            raise NodeOwnershipError("static Pod config and mirror identifiers do not match")


def _bindings(label: str, value: object, cls: type, count: int) -> tuple:
    if type(value) is not tuple or len(value) != count or any(type(item) is not cls for item in value):
        raise NodeOwnershipError(f"{label} bindings are not exact")
    for item in value:
        try:
            item.__post_init__()
        except NodeOwnershipError:
            raise
        except (TypeError, ValueError, UnicodeError, OverflowError, AttributeError) as error:
            raise NodeOwnershipError(f"{label} binding is partial or malformed") from error
    if tuple(sorted(value)) != value or len(set(value)) != count:
        raise NodeOwnershipError(f"{label} bindings are not canonical")
    return value


@dataclass(frozen=True, slots=True)
class NodeOwnershipProof:
    node_name: str
    node_uid: str
    node_resource_version: str
    daemon_pods: tuple[DaemonPodBinding, ...]
    static_pods: tuple[StaticPodBinding, ...]
    runtime_complete: bool = False

    def __post_init__(self) -> None:
        _literal("node name", self.node_name, _NODE)
        node_uid = _uid(self.node_uid)
        _rv(self.node_resource_version)
        daemons = _bindings("daemon Pod", self.daemon_pods, DaemonPodBinding, 2)
        statics = _bindings("static Pod", self.static_pods, StaticPodBinding, 4)
        if tuple(item.daemon_set_name for item in daemons) != _DAEMONS:
            raise NodeOwnershipError("DaemonSet identities are not exact")
        if tuple(item.component for item in statics) != _COMPONENTS:
            raise NodeOwnershipError("static component identities are not exact")
        if any(item.node_name != self.node_name for item in (*daemons, *statics)):
            raise NodeOwnershipError("Pod bindings do not select the reviewed node")
        if any(item.owner_node_uid != node_uid for item in statics):
            raise NodeOwnershipError("static Pod owner UIDs do not join the reviewed node")
        uids = [node_uid]
        for item in daemons:
            uids.extend((item.daemon_set_uid, item.pod_uid))
        uids.extend(item.pod_uid for item in statics)
        if len(uids) != 9 or len(set(uids)) != 9:
            raise NodeOwnershipError("node ownership UIDs are not globally unique")
        if type(self.runtime_complete) is not bool or self.runtime_complete:
            raise NodeOwnershipError("node ownership is not runtime-complete evidence")


def _keys(label: str, value: dict, expected: frozenset[str]) -> None:
    if any(type(key) is not str for key in value) or set(value) != expected:
        raise NodeOwnershipError(f"{label} keys are not exact")


def _precheck(node: object, daemon_sets: object, daemon_pods: object,
              static_pods: object) -> tuple[dict, list, list, list]:
    if type(daemon_sets) is not list or len(daemon_sets) != 2:
        raise NodeOwnershipError("DaemonSet cardinality is not exactly two")
    if type(daemon_pods) is not list or len(daemon_pods) != 2:
        raise NodeOwnershipError("daemon Pod cardinality is not exactly two")
    if type(static_pods) is not list or len(static_pods) != 4:
        raise NodeOwnershipError("static Pod cardinality is not exactly four")
    records = ((node, len(_NODE_KEYS), "Node"),
               *((item, len(_DAEMON_SET_KEYS), "DaemonSet") for item in daemon_sets),
               *((item, len(_DAEMON_POD_KEYS), "daemon Pod") for item in daemon_pods),
               *((item, len(_STATIC_POD_KEYS), "static Pod") for item in static_pods))
    for record, count, label in records:
        if type(record) is not dict or len(record) != count:
            raise NodeOwnershipError(f"{label} record shape is not exact")
    owned = (*((record, _DAEMON_OWNER_KEYS) for record in daemon_pods),
             *((record, _STATIC_OWNER_KEYS) for record in static_pods))
    for record, owner_keys in owned:
        owner = record.get("ownerReference")
        if type(owner) is not dict or len(owner) != len(owner_keys):
            raise NodeOwnershipError("ownerReference record shape is not exact")
    _keys("Node", node, _NODE_KEYS)
    for record in daemon_sets: _keys("DaemonSet", record, _DAEMON_SET_KEYS)
    for record in daemon_pods: _keys("daemon Pod", record, _DAEMON_POD_KEYS)
    for record in static_pods: _keys("static Pod", record, _STATIC_POD_KEYS)
    for record, owner_keys in owned: _keys("ownerReference", record["ownerReference"], owner_keys)
    return node, daemon_sets, daemon_pods, static_pods


def _owner(record: dict, *, api_version: str, kind: str, name: str, uid: str) -> None:
    owner = record["ownerReference"]
    if type(owner["controller"]) is not bool or owner["controller"] is not True:
        raise NodeOwnershipError("ownerReference controller flags are not exact true booleans")
    if kind == "DaemonSet" and (type(owner["blockOwnerDeletion"]) is not bool
                                or owner["blockOwnerDeletion"] is not True):
        raise NodeOwnershipError("DaemonSet blockOwnerDeletion is not an exact true boolean")
    _literal("owner apiVersion", owner["apiVersion"], api_version)
    _literal("owner kind", owner["kind"], kind)
    _literal("owner name", owner["name"], name)
    if _uid(owner["uid"]) != uid:
        raise NodeOwnershipError("ownerReference UID does not join the owner")


def _validate(node: object, daemon_sets: object, daemon_pods: object,
              static_pods: object, cluster_name: object) -> NodeOwnershipProof:
    node, daemon_sets, daemon_pods, static_pods = _precheck(
        node, daemon_sets, daemon_pods, static_pods)
    cluster = _literal("cluster name", cluster_name, _CLUSTER)
    node_name = _literal("Node name", node["name"], f"{cluster}-control-plane")
    _literal("Node apiVersion", node["apiVersion"], "v1")
    _literal("Node kind", node["kind"], "Node")
    node_uid, node_rv = _uid(node["uid"]), _rv(node["resourceVersion"])

    owners: dict[str, tuple[str, str]] = {}
    for record in daemon_sets:
        _literal("DaemonSet apiVersion", record["apiVersion"], "apps/v1")
        _literal("DaemonSet kind", record["kind"], "DaemonSet")
        _literal("DaemonSet namespace", record["namespace"], _NAMESPACE)
        name = _dns("DaemonSet name", record["name"])
        if name not in _DAEMONS or name in owners:
            raise NodeOwnershipError("DaemonSet identities are not exact")
        if type(record["desiredNumberScheduled"]) is not int or record["desiredNumberScheduled"] != 1:
            raise NodeOwnershipError("DaemonSet desired count is not exact one")
        owners[name] = (_uid(record["uid"]), _rv(record["resourceVersion"]))
    if set(owners) != set(_DAEMONS):
        raise NodeOwnershipError("DaemonSet identities are not exact")

    daemon_bindings = []
    seen_daemons: set[str] = set()
    for record in daemon_pods:
        _literal("daemon Pod apiVersion", record["apiVersion"], "v1")
        _literal("daemon Pod kind", record["kind"], "Pod")
        _literal("daemon Pod namespace", record["namespace"], _NAMESPACE)
        _literal("daemon Pod nodeName", record["nodeName"], node_name)
        owner_name = _dns("owner name", record["ownerReference"]["name"])
        if owner_name not in owners or owner_name in seen_daemons:
            raise NodeOwnershipError("daemon Pod ownership cardinality is not exact")
        owner_uid, owner_rv = owners[owner_name]
        _owner(record, api_version="apps/v1", kind="DaemonSet",
               name=owner_name, uid=owner_uid)
        daemon_bindings.append(DaemonPodBinding(
            _NAMESPACE, owner_name, owner_uid, owner_rv,
            _daemon_pod_name(owner_name, record["name"]), _uid(record["uid"]),
            _rv(record["resourceVersion"]), node_name,
        ))
        seen_daemons.add(owner_name)
    if seen_daemons != set(_DAEMONS):
        raise NodeOwnershipError("daemon Pod ownership cardinality is not exact")

    static_bindings = []
    seen_components: set[str] = set()
    for record in static_pods:
        _literal("static Pod apiVersion", record["apiVersion"], "v1")
        _literal("static Pod kind", record["kind"], "Pod")
        _literal("static Pod namespace", record["namespace"], _NAMESPACE)
        _literal("static Pod nodeName", record["nodeName"], node_name)
        component = _dns("static component", record["component"])
        if component not in _COMPONENTS or component in seen_components:
            raise NodeOwnershipError("static component identities are not exact")
        _literal("static Pod name", record["name"], f"{component}-{node_name}")
        _literal("static config source", record["configSource"], "file")
        _owner(record, api_version="v1", kind="Node", name=node_name, uid=node_uid)
        config_hash = _static_config_hash("config hash", record["configHash"])
        mirror_hash = _static_config_hash("mirror hash", record["mirrorHash"])
        if mirror_hash != config_hash:
            raise NodeOwnershipError("static Pod config and mirror identifiers do not match")
        static_bindings.append(StaticPodBinding(
            component, record["name"], _uid(record["uid"]),
            _rv(record["resourceVersion"]), node_name, node_uid,
            config_hash, mirror_hash,
        ))
        seen_components.add(component)
    if seen_components != set(_COMPONENTS):
        raise NodeOwnershipError("static component identities are not exact")
    return NodeOwnershipProof(node_name, node_uid, node_rv,
                              tuple(sorted(daemon_bindings)),
                              tuple(sorted(static_bindings)), False)


def validate_node_ownership(*, node: dict, daemon_sets: list, daemon_pods: list,
                            static_pods: list, cluster_name: str) -> NodeOwnershipProof:
    """Validate the exact reviewed node/Pod ownership projection."""
    try:
        return _validate(node, daemon_sets, daemon_pods, static_pods, cluster_name)
    except NodeOwnershipError:
        raise
    except (TypeError, ValueError, UnicodeError, OverflowError, AttributeError,
            RecursionError) as error:
        raise NodeOwnershipError("node ownership evidence is malformed") from error
