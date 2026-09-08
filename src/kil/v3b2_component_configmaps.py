"""Validate uploaded kubeadm and kubelet configuration ConfigMaps.

This proof binds exact source content and independently trusted configuration
semantics.  It does not cover kube-proxy, node-local patches, ownership, or
runtime readiness.
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
_IDENTITIES = frozenset((
    ("kube-system", "kubeadm-config"),
    ("kube-system", "kubelet-config"),
))
_METADATA_KEYS = frozenset((
    "name", "namespace", "uid", "resourceVersion", "creationTimestamp",
    "managedFields",
))
_PINNED = {
    "cluster_name": "kil-v3-lab",
    "kubernetes_version": "v1.36.1",
    "pod_subnet": "10.244.0.0/16",
    "service_subnet": "10.96.0.0/16",
    "dns_domain": "cluster.local",
    "cluster_dns": "10.96.0.10",
}


class ComponentConfigMapError(ValueError):
    """The uploaded component configuration observation is invalid."""


def _exact_string(label: str, value: object, maximum: int = _MAX_TREE_BYTES) -> str:
    if type(value) is not str:
        raise ComponentConfigMapError(f"{label} must be an exact string")
    if len(value) > maximum:
        raise ComponentConfigMapError(f"{label} is unbounded")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ComponentConfigMapError(f"{label} is not Unicode scalar text") from error
    if len(encoded) > maximum:
        raise ComponentConfigMapError(f"{label} is unbounded")
    return value


def _uid(value: object) -> str:
    text = _exact_string("UID", value, 128)
    if _UID.fullmatch(text) is None:
        raise ComponentConfigMapError("UID is not a bounded opaque API identity")
    return text


def _resource_version(value: object) -> str:
    text = _exact_string("resourceVersion", value, 20)
    if _RESOURCE_VERSION.fullmatch(text) is None or int(text) > _UINT64_MAX:
        raise ComponentConfigMapError("resourceVersion is not a canonical positive uint64")
    return text


def _digest(label: str, value: object) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ComponentConfigMapError(f"{label} is not a lowercase SHA-256 digest")
    return value


def _proof_identity(api_version: object, kind: object, namespace: object,
                    name: object) -> tuple[str, str]:
    if (_exact_string("apiVersion", api_version, 16) != "v1"
            or _exact_string("kind", kind, 32) != "ConfigMap"):
        raise ComponentConfigMapError("proof is not a v1 ConfigMap")
    identity = (_exact_string("namespace", namespace, 128),
                _exact_string("name", name, 128))
    if identity not in _IDENTITIES:
        raise ComponentConfigMapError("proof identity is outside the exact component set")
    return identity


@dataclass(frozen=True, slots=True, order=True)
class ComponentConfigMapProof:
    api_version: str
    kind: str
    namespace: str
    name: str
    uid: str
    resource_version: str
    raw_content_sha256: str
    semantic_sha256: str
    expected_sha256: str
    provider_rootless: bool = False
    runtime_contract_complete: bool = False

    def __post_init__(self) -> None:
        try:
            _proof_identity(self.api_version, self.kind, self.namespace, self.name)
            _uid(self.uid)
            _resource_version(self.resource_version)
            _digest("raw content digest", self.raw_content_sha256)
            semantic = _digest("semantic digest", self.semantic_sha256)
            expected = _digest("expected digest", self.expected_sha256)
            if semantic != expected:
                raise ComponentConfigMapError(
                    "semantic and trusted expected digests are inconsistent")
            if self.provider_rootless is not False:
                raise ComponentConfigMapError("provider rootless binding is not exact false")
            if self.runtime_contract_complete is not False:
                raise ComponentConfigMapError(
                    "component ConfigMap proof cannot complete the runtime contract")
        except ComponentConfigMapError:
            raise
        except (AttributeError, TypeError, ValueError, OverflowError,
                RecursionError) as error:
            raise ComponentConfigMapError("component proof is malformed") from error


def _string_size(value: object, remaining: int, *, key: bool = False) -> int:
    label = "JSON key" if key else "JSON string"
    if type(value) is not str:
        raise ComponentConfigMapError(f"{label} must be an exact string")
    if remaining < 0 or len(value) > remaining:
        raise ComponentConfigMapError("decoded JSON tree is unbounded")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ComponentConfigMapError(f"{label} is not Unicode scalar text") from error
    if len(encoded) > remaining:
        raise ComponentConfigMapError("decoded JSON tree is unbounded")
    return len(encoded)


def _validate_tree(*roots: object) -> None:
    if len(roots) > _MAX_TREE_ITEMS:
        raise ComponentConfigMapError("decoded JSON tree is unbounded")
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
            raise ComponentConfigMapError("decoded JSON tree is unbounded")
        if type(current) is str:
            size += _string_size(current, _MAX_TREE_BYTES - size) + 2
        elif current is None or type(current) is bool:
            size += 5
        elif type(current) is int:
            if current.bit_length() > _MAX_INTEGER_BITS:
                raise ComponentConfigMapError("decoded JSON integer is unbounded")
            size += len(str(current))
        elif type(current) in (dict, list):
            marker = id(current)
            if marker in active:
                raise ComponentConfigMapError("decoded JSON tree contains a cycle")
            child_cost = len(current) * (2 if type(current) is dict else 1)
            if child_cost > remaining_items or (current and depth >= _MAX_DEPTH):
                raise ComponentConfigMapError("decoded JSON tree is unbounded")
            remaining_items -= child_cost
            active.add(marker)
            pending.append((True, current, depth))
            size += 2
            if type(current) is list:
                for child in current:
                    pending.append((False, child, depth + 1))
            else:
                for key, child in current.items():
                    size += _string_size(key, _MAX_TREE_BYTES - size,
                                         key=True) + 3
                    pending.append((False, child, depth + 1))
        else:
            raise ComponentConfigMapError("decoded value is not exact JSON")
        if size > _MAX_TREE_BYTES:
            raise ComponentConfigMapError("decoded JSON tree is unbounded")


def _pinned_inputs(**values: object) -> None:
    for label, expected in _PINNED.items():
        if _exact_string(label, values[label], 128) != expected:
            raise ComponentConfigMapError(f"{label} is not the pinned nominal value")
    if values["provider_rootless"] is not False:
        raise ComponentConfigMapError("provider_rootless must be exact false")


def _require_string_member(container: dict, key: str, expected: str,
                           label: str) -> None:
    if _exact_string(label, container.get(key), 256) != expected:
        raise ComponentConfigMapError(f"{label} does not match its independent input")


def _validate_kubeadm(expected: dict, *, cluster_name: str,
                      kubernetes_version: str, pod_subnet: str,
                      service_subnet: str, dns_domain: str) -> None:
    _require_string_member(expected, "apiVersion", "kubeadm.k8s.io/v1beta4",
                           "kubeadm apiVersion")
    _require_string_member(expected, "kind", "ClusterConfiguration", "kubeadm kind")
    _require_string_member(expected, "clusterName", cluster_name, "clusterName")
    _require_string_member(expected, "kubernetesVersion", kubernetes_version,
                           "kubernetesVersion")
    _require_string_member(expected, "controlPlaneEndpoint",
                           "kil-v3-lab-control-plane:6443", "controlPlaneEndpoint")
    networking = expected.get("networking")
    if type(networking) is not dict:
        raise ComponentConfigMapError("kubeadm networking is not an exact object")
    for key, value in (("dnsDomain", dns_domain), ("podSubnet", pod_subnet),
                       ("serviceSubnet", service_subnet)):
        _require_string_member(networking, key, value, f"networking.{key}")
    controller = expected.get("controllerManager")
    args = controller.get("extraArgs") if type(controller) is dict else None
    if type(args) is not list:
        raise ComponentConfigMapError("controllerManager.extraArgs is not an exact list")
    names: set[str] = set()
    hostpath = 0
    for argument in args:
        if type(argument) is not dict or set(argument) != {"name", "value"}:
            raise ComponentConfigMapError("controllerManager extraArg shape is not exact")
        name = _exact_string("controllerManager extraArg name", argument.get("name"), 256)
        value = _exact_string("controllerManager extraArg value", argument.get("value"), 4096)
        if name in names:
            raise ComponentConfigMapError("controllerManager extraArg name is duplicated")
        names.add(name)
        if name == "enable-hostpath-provisioner":
            hostpath += value == "true"
            if value != "true":
                raise ComponentConfigMapError("hostpath provisioner value is not exact")
    if hostpath != 1:
        raise ComponentConfigMapError("hostpath provisioner extraArg is not exact")


def _validate_kubelet(expected: dict, *, dns_domain: str, cluster_dns: str) -> None:
    _require_string_member(expected, "apiVersion", "kubelet.config.k8s.io/v1beta1",
                           "kubelet apiVersion")
    _require_string_member(expected, "kind", "KubeletConfiguration", "kubelet kind")
    _require_string_member(expected, "clusterDomain", dns_domain, "clusterDomain")
    dns = expected.get("clusterDNS")
    if (type(dns) is not list or len(dns) != 1 or type(dns[0]) is not str
            or dns[0] != cluster_dns):
        raise ComponentConfigMapError("clusterDNS is not the exact one-entry list")


def _identity(document: dict) -> tuple[str, str]:
    if (set(document) != {"apiVersion", "kind", "metadata", "data"}
            or type(document.get("apiVersion")) is not str
            or document.get("apiVersion") != "v1"
            or type(document.get("kind")) is not str
            or document.get("kind") != "ConfigMap"):
        raise ComponentConfigMapError("observed root is not an exact v1 ConfigMap")
    metadata = document.get("metadata")
    if type(metadata) is not dict:
        raise ComponentConfigMapError("observed metadata is not an exact object")
    identity = (metadata.get("namespace"), metadata.get("name"))
    if (any(type(part) is not str for part in identity)
            or identity not in _IDENTITIES):
        raise ComponentConfigMapError("observed identity is outside the exact component set")
    return identity


def _proof(document: dict, identity: tuple[str, str], expected: dict) -> ComponentConfigMapProof:
    metadata = document["metadata"]
    if set(metadata) != _METADATA_KEYS:
        raise ComponentConfigMapError("observed metadata keys are not exact")
    uid = _uid(metadata.get("uid"))
    resource_version = _resource_version(metadata.get("resourceVersion"))
    try:
        configuration(document)
    except (ValueError, TypeError, KeyError, AttributeError,
            RecursionError) as error:
        raise ComponentConfigMapError("runtime metadata is invalid") from error
    data_key = "ClusterConfiguration" if identity[1] == "kubeadm-config" else "kubelet"
    data = document.get("data")
    if type(data) is not dict or set(data) != {data_key}:
        raise ComponentConfigMapError("component ConfigMap data key is not exact")
    raw = _exact_string("component configuration YAML", data.get(data_key))
    try:
        observed = decode_closed_yaml(raw)
        _validate_tree(observed)
        semantic_digest = canonical_digest(observed)
        expected_digest = canonical_digest(expected)
    except (ClosedYAMLError, ValueError, TypeError, UnicodeError,
            RecursionError) as error:
        raise ComponentConfigMapError("component configuration YAML is invalid") from error
    if semantic_digest != expected_digest:
        raise ComponentConfigMapError("observed semantics differ from trusted expected configuration")
    return ComponentConfigMapProof(
        "v1", "ConfigMap", identity[0], identity[1], uid, resource_version,
        sha256(raw.encode("utf-8")).hexdigest(), semantic_digest,
        expected_digest,
    )


def validate_component_configmaps(
    *, documents: list[dict], expected_kubeadm_configuration: dict,
    expected_kubelet_configuration: dict, cluster_name: str,
    kubernetes_version: str, pod_subnet: str, service_subnet: str,
    dns_domain: str, cluster_dns: str, provider_rootless: bool,
) -> tuple[ComponentConfigMapProof, ComponentConfigMapProof]:
    """Validate the exact two uploaded generic component configurations."""
    try:
        if (type(documents) is not list or len(documents) != 2
                or any(type(document) is not dict for document in documents)
                or type(expected_kubeadm_configuration) is not dict
                or type(expected_kubelet_configuration) is not dict):
            raise ComponentConfigMapError("documents and expected configurations have wrong types")
        _pinned_inputs(
            cluster_name=cluster_name, kubernetes_version=kubernetes_version,
            pod_subnet=pod_subnet, service_subnet=service_subnet,
            dns_domain=dns_domain, cluster_dns=cluster_dns,
            provider_rootless=provider_rootless,
        )
        _validate_tree(documents, expected_kubeadm_configuration,
                       expected_kubelet_configuration)
        _validate_kubeadm(
            expected_kubeadm_configuration, cluster_name=cluster_name,
            kubernetes_version=kubernetes_version, pod_subnet=pod_subnet,
            service_subnet=service_subnet, dns_domain=dns_domain,
        )
        _validate_kubelet(expected_kubelet_configuration,
                          dns_domain=dns_domain, cluster_dns=cluster_dns)
        expected_by_name = {
            "kubeadm-config": expected_kubeadm_configuration,
            "kubelet-config": expected_kubelet_configuration,
        }
        proofs: list[ComponentConfigMapProof] = []
        seen: set[tuple[str, str]] = set()
        for document in documents:
            identity = _identity(document)
            if identity in seen:
                raise ComponentConfigMapError("component ConfigMap identity is duplicated")
            seen.add(identity)
            proofs.append(_proof(document, identity, expected_by_name[identity[1]]))
        if seen != _IDENTITIES:
            raise ComponentConfigMapError("component ConfigMap identity set is incomplete")
        return tuple(sorted(proofs))  # type: ignore[return-value]
    except ComponentConfigMapError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError,
            OverflowError, RecursionError) as error:
        raise ComponentConfigMapError("component ConfigMap validation failed") from error


__all__ = (
    "ComponentConfigMapError",
    "ComponentConfigMapProof",
    "validate_component_configmaps",
)
