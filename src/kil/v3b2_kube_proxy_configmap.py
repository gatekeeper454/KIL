"""Validate the pinned uploaded kube-proxy configuration ConfigMap.

The resulting proof binds trusted configuration semantics and the exact
kubeadm-generated file-reference kubeconfig.  It never retains raw YAML or
embedded authentication material and cannot prove runtime readiness.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .canonical import canonical_digest
from .v3b2_api_defaults import configuration
from .v3b2_closed_yaml import ClosedYAMLError, decode_closed_yaml


_MAX_TREE_BYTES = 2 * 1024 * 1024
_MAX_TREE_ITEMS = 32_768
_MAX_DEPTH = 64
_MAX_INTEGER_BITS = 4096
_UINT64_MAX = 2**64 - 1
_UID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_RESOURCE_VERSION = re.compile(r"[1-9][0-9]{0,19}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_ROOT_KEYS = frozenset(("apiVersion", "kind", "metadata", "data"))
_METADATA_KEYS = frozenset((
    "name", "namespace", "labels", "uid", "resourceVersion",
    "creationTimestamp", "managedFields",
))
_DATA_KEYS = frozenset(("config.conf", "kubeconfig.conf"))
_ENDPOINT = "https://kil-v3-lab-control-plane:6443"
_PINNED = {
    "cluster_name": "kil-v3-lab",
    "pod_subnet": "10.244.0.0/16",
    "control_plane_endpoint": _ENDPOINT,
}
_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
_CONFIG_PATH = "/var/lib/kube-proxy/kubeconfig.conf"


class KubeProxyConfigMapError(ValueError):
    """The kube-proxy ConfigMap observation is invalid."""


def _exact_string(label: str, value: object, maximum: int = _MAX_TREE_BYTES) -> str:
    if type(value) is not str:
        raise KubeProxyConfigMapError(f"{label} must be an exact string")
    if len(value) > maximum:
        raise KubeProxyConfigMapError(f"{label} is unbounded")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise KubeProxyConfigMapError(f"{label} is not Unicode scalar text") from error
    if len(encoded) > maximum:
        raise KubeProxyConfigMapError(f"{label} is unbounded")
    return value


def _uid(value: object) -> str:
    text = _exact_string("UID", value, 128)
    if _UID.fullmatch(text) is None:
        raise KubeProxyConfigMapError("UID is not a bounded opaque API identity")
    return text


def _resource_version(value: object) -> str:
    text = _exact_string("resourceVersion", value, 20)
    if _RESOURCE_VERSION.fullmatch(text) is None or int(text) > _UINT64_MAX:
        raise KubeProxyConfigMapError(
            "resourceVersion is not a canonical positive uint64")
    return text


def _digest(label: str, value: object) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise KubeProxyConfigMapError(
            f"{label} is not a lowercase SHA-256 digest")
    return value


def _proof_identity(api_version: object, kind: object, namespace: object,
                    name: object) -> None:
    if (_exact_string("apiVersion", api_version, 16) != "v1"
            or _exact_string("kind", kind, 32) != "ConfigMap"
            or _exact_string("namespace", namespace, 128) != "kube-system"
            or _exact_string("name", name, 128) != "kube-proxy"):
        raise KubeProxyConfigMapError("proof identity is not the pinned ConfigMap")


@dataclass(frozen=True, slots=True)
class KubeProxyConfigMapProof:
    api_version: str
    kind: str
    namespace: str
    name: str
    uid: str
    resource_version: str
    config_raw_sha256: str
    kubeconfig_raw_sha256: str
    config_semantic_sha256: str
    kubeconfig_semantic_sha256: str
    expected_config_sha256: str
    control_plane_endpoint: str
    provider_rootless: bool = False
    runtime_contract_complete: bool = False

    def __post_init__(self) -> None:
        try:
            _proof_identity(self.api_version, self.kind, self.namespace, self.name)
            _uid(self.uid)
            _resource_version(self.resource_version)
            _digest("config raw digest", self.config_raw_sha256)
            _digest("kubeconfig raw digest", self.kubeconfig_raw_sha256)
            semantic = _digest("config semantic digest",
                               self.config_semantic_sha256)
            _digest("kubeconfig semantic digest", self.kubeconfig_semantic_sha256)
            expected = _digest("trusted expected config digest",
                               self.expected_config_sha256)
            if semantic != expected:
                raise KubeProxyConfigMapError(
                    "semantic and trusted expected config digests differ")
            if (_exact_string("control plane endpoint",
                              self.control_plane_endpoint, 256) != _ENDPOINT):
                raise KubeProxyConfigMapError("proof endpoint is not pinned")
            if self.provider_rootless is not False:
                raise KubeProxyConfigMapError("provider rootless binding is not exact false")
            if self.runtime_contract_complete is not False:
                raise KubeProxyConfigMapError(
                    "kube-proxy ConfigMap proof cannot complete the runtime contract")
        except KubeProxyConfigMapError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError,
                RecursionError) as error:
            raise KubeProxyConfigMapError("kube-proxy proof is malformed") from error


def _string_size(value: object, remaining: int, *, key: bool = False) -> int:
    label = "JSON key" if key else "JSON string"
    if type(value) is not str:
        raise KubeProxyConfigMapError(f"{label} must be an exact string")
    if remaining < 0 or len(value) > remaining:
        raise KubeProxyConfigMapError("decoded JSON tree is unbounded")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise KubeProxyConfigMapError(f"{label} is not Unicode scalar text") from error
    if len(encoded) > remaining:
        raise KubeProxyConfigMapError("decoded JSON tree is unbounded")
    return len(encoded)


def _validate_tree(*roots: object) -> None:
    if len(roots) > _MAX_TREE_ITEMS:
        raise KubeProxyConfigMapError("decoded JSON tree is unbounded")
    pending: list[tuple[bool, object, int]] = [
        (False, root, 0) for root in roots
    ]
    active: set[int] = set()
    remaining_items = _MAX_TREE_ITEMS - len(roots)
    size = 0
    while pending:
        exiting, current, depth = pending.pop()
        if exiting:
            active.remove(id(current))
            continue
        if depth > _MAX_DEPTH:
            raise KubeProxyConfigMapError("decoded JSON tree is unbounded")
        if type(current) is str:
            size += _string_size(current, _MAX_TREE_BYTES - size) + 2
        elif current is None or type(current) is bool:
            size += 5
        elif type(current) is int:
            if current.bit_length() > _MAX_INTEGER_BITS:
                raise KubeProxyConfigMapError("decoded JSON integer is unbounded")
            size += len(str(current))
        elif type(current) in (dict, list):
            marker = id(current)
            if marker in active:
                raise KubeProxyConfigMapError("decoded JSON tree contains a cycle")
            child_cost = len(current) * (2 if type(current) is dict else 1)
            if child_cost > remaining_items or (current and depth >= _MAX_DEPTH):
                raise KubeProxyConfigMapError("decoded JSON tree is unbounded")
            remaining_items -= child_cost
            active.add(marker)
            pending.append((True, current, depth))
            size += 2
            if type(current) is list:
                for child in current:
                    pending.append((False, child, depth + 1))
            else:
                for key, child in current.items():
                    size += _string_size(key, _MAX_TREE_BYTES - size, key=True) + 3
                    pending.append((False, child, depth + 1))
        else:
            raise KubeProxyConfigMapError("decoded value is not exact JSON")
        if size > _MAX_TREE_BYTES:
            raise KubeProxyConfigMapError("decoded JSON tree is unbounded")


def _pinned_inputs(*, cluster_name: object, pod_subnet: object,
                   control_plane_endpoint: object,
                   provider_rootless: object) -> None:
    supplied = {
        "cluster_name": cluster_name,
        "pod_subnet": pod_subnet,
        "control_plane_endpoint": control_plane_endpoint,
    }
    for label, expected in _PINNED.items():
        if _exact_string(label, supplied[label], 256) != expected:
            raise KubeProxyConfigMapError(f"{label} is not the pinned nominal value")
    if provider_rootless is not False:
        raise KubeProxyConfigMapError("provider_rootless must be exact false")


def _member(container: dict, key: str, expected: str, label: str) -> None:
    if _exact_string(label, container.get(key), 512) != expected:
        raise KubeProxyConfigMapError(f"{label} does not match its independent input")


def _validate_expected(expected: dict, *, pod_subnet: str) -> None:
    _member(expected, "apiVersion", "kubeproxy.config.k8s.io/v1alpha1",
            "proxy apiVersion")
    _member(expected, "kind", "KubeProxyConfiguration", "proxy kind")
    _member(expected, "mode", "iptables", "proxy mode")
    _member(expected, "clusterCIDR", pod_subnet, "proxy clusterCIDR")
    client = expected.get("clientConnection")
    if type(client) is not dict:
        raise KubeProxyConfigMapError("clientConnection is not an exact object")
    _member(client, "kubeconfig", _CONFIG_PATH, "proxy kubeconfig path")
    iptables = expected.get("iptables")
    if type(iptables) is not dict:
        raise KubeProxyConfigMapError("iptables is not an exact object")
    _member(iptables, "minSyncPeriod", "1s", "iptables.minSyncPeriod")
    conntrack = expected.get("conntrack")
    if (type(conntrack) is not dict or type(conntrack.get("maxPerCore")) is not int
            or conntrack.get("maxPerCore") != 0):
        raise KubeProxyConfigMapError("conntrack.maxPerCore is not exact int zero")


def _expected_kubeconfig(endpoint: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{
            "cluster": {"certificate-authority": _CA_PATH, "server": endpoint},
            "name": "default",
        }],
        "contexts": [{
            "context": {
                "cluster": "default", "namespace": "default", "user": "default",
            },
            "name": "default",
        }],
        "current-context": "default",
        "users": [{
            "name": "default", "user": {"tokenFile": _TOKEN_PATH},
        }],
    }


def _identity(document: dict) -> tuple[dict, str, str]:
    if (set(document) != _ROOT_KEYS or document.get("apiVersion") != "v1"
            or type(document.get("apiVersion")) is not str
            or document.get("kind") != "ConfigMap"
            or type(document.get("kind")) is not str):
        raise KubeProxyConfigMapError("observed root is not an exact v1 ConfigMap")
    metadata = document.get("metadata")
    if type(metadata) is not dict or set(metadata) != _METADATA_KEYS:
        raise KubeProxyConfigMapError("observed metadata keys are not exact")
    if (type(metadata.get("name")) is not str or metadata.get("name") != "kube-proxy"
            or type(metadata.get("namespace")) is not str
            or metadata.get("namespace") != "kube-system"):
        raise KubeProxyConfigMapError("observed identity is not the pinned ConfigMap")
    labels = metadata.get("labels")
    if (type(labels) is not dict or set(labels) != {"app"}
            or type(labels.get("app")) is not str
            or labels.get("app") != "kube-proxy"):
        raise KubeProxyConfigMapError("observed kube-proxy label is not exact")
    return metadata, _uid(metadata.get("uid")), _resource_version(
        metadata.get("resourceVersion"))


def validate_kube_proxy_configmap(
    *, document: dict, expected_proxy_configuration: dict, cluster_name: str,
    pod_subnet: str, control_plane_endpoint: str, provider_rootless: bool,
) -> KubeProxyConfigMapProof:
    """Validate one exact source-generated kube-proxy ConfigMap observation."""
    try:
        if type(document) is not dict or type(expected_proxy_configuration) is not dict:
            raise KubeProxyConfigMapError("document and expected config require exact objects")
        _pinned_inputs(
            cluster_name=cluster_name, pod_subnet=pod_subnet,
            control_plane_endpoint=control_plane_endpoint,
            provider_rootless=provider_rootless,
        )
        _validate_tree(document, expected_proxy_configuration)
        metadata, uid, resource_version = _identity(document)
        try:
            configuration(document)
        except (ValueError, TypeError, KeyError, AttributeError,
                RecursionError) as error:
            raise KubeProxyConfigMapError("runtime metadata is invalid") from error
        data = document.get("data")
        if type(data) is not dict or set(data) != _DATA_KEYS:
            raise KubeProxyConfigMapError("kube-proxy data keys are not exact")
        config_raw = _exact_string("config.conf", data.get("config.conf"))
        kubeconfig_raw = _exact_string("kubeconfig.conf", data.get("kubeconfig.conf"))
        _validate_expected(expected_proxy_configuration, pod_subnet=pod_subnet)
        try:
            config = decode_closed_yaml(config_raw)
            kubeconfig = decode_closed_yaml(kubeconfig_raw)
            _validate_tree(config, kubeconfig)
            config_semantic = canonical_digest(config)
            expected_semantic = canonical_digest(expected_proxy_configuration)
            kubeconfig_semantic = canonical_digest(kubeconfig)
            source_kubeconfig = _expected_kubeconfig(control_plane_endpoint)
            source_kubeconfig_semantic = canonical_digest(source_kubeconfig)
        except (ClosedYAMLError, ValueError, TypeError, UnicodeError,
                RecursionError) as error:
            raise KubeProxyConfigMapError("kube-proxy YAML is invalid") from error
        if config_semantic != expected_semantic:
            raise KubeProxyConfigMapError(
                "observed proxy semantics differ from trusted expected config")
        if kubeconfig_semantic != source_kubeconfig_semantic:
            raise KubeProxyConfigMapError("kube-proxy kubeconfig semantics are not exact")
        return KubeProxyConfigMapProof(
            "v1", "ConfigMap", "kube-system", "kube-proxy", uid,
            resource_version, sha256(config_raw.encode("utf-8")).hexdigest(),
            sha256(kubeconfig_raw.encode("utf-8")).hexdigest(),
            config_semantic, kubeconfig_semantic, expected_semantic,
            control_plane_endpoint,
        )
    except KubeProxyConfigMapError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, UnicodeError,
            OverflowError, RecursionError) as error:
        raise KubeProxyConfigMapError("kube-proxy validation failed") from error


__all__ = (
    "KubeProxyConfigMapError",
    "KubeProxyConfigMapProof",
    "validate_kube_proxy_configmap",
)
