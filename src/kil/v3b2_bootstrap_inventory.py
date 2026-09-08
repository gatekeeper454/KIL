"""Exact bootstrap identity/cardinality bindings for Namespace, SA and ConfigMap.

This module deliberately does not establish workload topology, configuration
semantics for platform ConfigMaps, an InventorySnapshot, or runtime readiness.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .canonical import canonical_json
from .v3b2_api_defaults import configuration, matches_configuration


_MAX_BYTES = 8 * 1024 * 1024
_MAX_DEPTH = 64
_MAX_ITEMS = 250_000
_UINT64_MAX = 2**64 - 1
_UID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_RV = re.compile(r"[1-9][0-9]{0,19}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_NAMESPACES = (
    "default", "kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed",
    "kube-node-lease", "kube-public", "kube-system", "local-path-storage",
)
_APP_NAMESPACES = ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed")
_CONTROLLER_ACCOUNTS = (
    "attachdetach-controller", "bootstrap-signer", "certificate-controller",
    "clusterrole-aggregation-controller", "cronjob-controller",
    "daemon-set-controller", "deployment-controller",
    "device-taint-eviction-controller", "disruption-controller",
    "endpoint-controller", "endpointslice-controller",
    "endpointslicemirroring-controller", "ephemeral-volume-controller",
    "expand-controller", "generic-garbage-collector",
    "horizontal-pod-autoscaler", "job-controller",
    "legacy-service-account-token-cleaner", "namespace-controller",
    "node-controller", "persistent-volume-binder", "pod-garbage-collector",
    "pv-protection-controller", "pvc-protection-controller",
    "replicaset-controller", "replication-controller",
    "resource-claim-controller", "resourcequota-controller",
    "root-ca-cert-publisher", "service-account-controller",
    "service-cidrs-controller", "statefulset-controller", "token-cleaner",
    "ttl-after-finished-controller", "ttl-controller",
    "validatingadmissionpolicy-status-controller",
    "volumeattributesclass-protection-controller",
)
_PLATFORM_SERVICE_ACCOUNTS = frozenset(
    [(namespace, "default") for namespace in _NAMESPACES]
    + [("kube-system", name) for name in _CONTROLLER_ACCOUNTS]
    + [
        ("kube-system", "coredns"), ("kube-system", "kube-proxy"),
        ("local-path-storage", "local-path-provisioner-service-account"),
    ]
)
_CALICO_SERVICE_ACCOUNTS = frozenset(
    ("kube-system", name)
    for name in ("calico-node", "calico-cni-plugin", "calico-kube-controllers")
)
_KIL_SERVICE_ACCOUNTS = frozenset(
    (namespace, name) for namespace in _APP_NAMESPACES
    for name in ("driver", "envoy", "authz", "target")
)
_PLATFORM_CONFIG_MAPS = frozenset(
    [(namespace, "kube-root-ca.crt") for namespace in _NAMESPACES]
    + [
        ("kube-system", "coredns"),
        ("kube-system", "extension-apiserver-authentication"),
        ("kube-system", "kube-apiserver-legacy-service-account-token-tracking"),
        ("kube-system", "kube-proxy"), ("kube-system", "kubeadm-config"),
        ("kube-system", "kubelet-config"), ("kube-public", "cluster-info"),
        ("local-path-storage", "local-path-config"),
    ]
)
_CALICO_CONFIG_MAPS = frozenset({("kube-system", "calico-config")})
_KIL_CONFIG_MAPS = frozenset(
    (namespace, name) for namespace in _APP_NAMESPACES
    for name in ("authz-config", "target-config", "envoy-config")
)
_SERVICE_ACCOUNTS = (
    _PLATFORM_SERVICE_ACCOUNTS | _CALICO_SERVICE_ACCOUNTS | _KIL_SERVICE_ACCOUNTS
)
_CONFIG_MAPS = _PLATFORM_CONFIG_MAPS | _CALICO_CONFIG_MAPS | _KIL_CONFIG_MAPS


class BootstrapInventoryError(ValueError):
    """The selected bootstrap inventory is open, malformed, or replaced."""


def _exact_string(label: str, value: object) -> str:
    if type(value) is not str or not value:
        raise BootstrapInventoryError(f"{label} must be an exact nonempty string")
    return value


def _resource_version(value: object) -> str:
    if type(value) is not str or _RV.fullmatch(value) is None or int(value) > _UINT64_MAX:
        raise BootstrapInventoryError("resourceVersion must be a canonical positive uint64")
    return value


@dataclass(frozen=True, slots=True, order=True)
class BootstrapIdentityBinding:
    api_version: str
    kind: str
    namespace: str
    name: str
    uid: str
    resource_version: str

    def __post_init__(self) -> None:
        if self.api_version != "v1" or self.kind not in {"Namespace", "ServiceAccount", "ConfigMap"}:
            raise BootstrapInventoryError("binding API identity is not reviewed")
        if type(self.namespace) is not str:
            raise BootstrapInventoryError("binding namespace must be an exact string")
        _exact_string("binding name", self.name)
        if type(self.uid) is not str or _UID.fullmatch(self.uid) is None:
            raise BootstrapInventoryError("UID is not a bounded opaque API identity")
        _resource_version(self.resource_version)


@dataclass(frozen=True, slots=True, order=True)
class UnvalidatedPlatformConfiguration:
    namespace: str
    name: str
    unvalidated_configuration_sha256: str

    def __post_init__(self) -> None:
        _exact_string("ConfigMap namespace", self.namespace)
        _exact_string("ConfigMap name", self.name)
        if type(self.unvalidated_configuration_sha256) is not str or _SHA256.fullmatch(
            self.unvalidated_configuration_sha256
        ) is None:
            raise BootstrapInventoryError("unvalidated configuration digest is invalid")


def _records(label: str, value: object, kind: str, count: int) -> tuple[BootstrapIdentityBinding, ...]:
    if type(value) is not tuple or len(value) != count or any(
        type(item) is not BootstrapIdentityBinding or item.kind != kind for item in value
    ):
        raise BootstrapInventoryError(f"{label} bindings are not exact")
    for item in value:
        item.__post_init__()
    if tuple(sorted(value)) != value or len(set(value)) != len(value):
        raise BootstrapInventoryError(f"{label} bindings are not canonical")
    return value


@dataclass(frozen=True, slots=True)
class BootstrapIdentitySnapshot:
    namespace_bindings: tuple[BootstrapIdentityBinding, ...]
    service_account_bindings: tuple[BootstrapIdentityBinding, ...]
    config_map_bindings: tuple[BootstrapIdentityBinding, ...]
    unvalidated_platform_configurations: tuple[UnvalidatedPlatformConfiguration, ...]

    def __post_init__(self) -> None:
        _records("Namespace", self.namespace_bindings, "Namespace", 8)
        _records("ServiceAccount", self.service_account_bindings, "ServiceAccount", 63)
        _records("ConfigMap", self.config_map_bindings, "ConfigMap", 26)
        actual_keys = {
            (item.kind, item.namespace, item.name)
            for rows in (self.namespace_bindings, self.service_account_bindings,
                         self.config_map_bindings) for item in rows
        }
        expected_keys = (
            {("Namespace", "", name) for name in _NAMESPACES}
            | {("ServiceAccount", *key) for key in _SERVICE_ACCOUNTS}
            | {("ConfigMap", *key) for key in _CONFIG_MAPS}
        )
        if actual_keys != expected_keys or len({
            item.uid for rows in (self.namespace_bindings, self.service_account_bindings,
                                  self.config_map_bindings) for item in rows
        }) != 97:
            raise BootstrapInventoryError("bootstrap snapshot identities are not exact")
        values = self.unvalidated_platform_configurations
        if type(values) is not tuple or len(values) != 16 or any(
            type(item) is not UnvalidatedPlatformConfiguration for item in values
        ):
            raise BootstrapInventoryError("platform ConfigMap diagnostics are not exact")
        for item in values:
            item.__post_init__()
        if tuple(sorted(values)) != values or len(set(values)) != len(values):
            raise BootstrapInventoryError("platform ConfigMap diagnostics are not canonical")
        if {(item.namespace, item.name) for item in values} != _PLATFORM_CONFIG_MAPS:
            raise BootstrapInventoryError("platform ConfigMap diagnostic identities are not exact")


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BootstrapInventoryError("duplicate JSON object key")
        result[key] = value
    return result


def _bounded_integer(value: str) -> int:
    if len(value.lstrip("-")) > 128:
        raise BootstrapInventoryError("JSON integer is unbounded")
    return int(value)


def _json_tree(value: object) -> None:
    pending = [(value, 0)]
    count = 0
    while pending:
        current, depth = pending.pop()
        count += 1
        if depth > _MAX_DEPTH or count > _MAX_ITEMS:
            raise BootstrapInventoryError("bootstrap JSON tree is unbounded")
        if type(current) is str:
            try:
                current.encode("utf-8")
            except UnicodeEncodeError as error:
                raise BootstrapInventoryError("JSON string is not a Unicode scalar sequence") from error
            continue
        if current is None or type(current) in {int, bool}:
            continue
        if type(current) is list:
            pending.extend((item, depth + 1) for item in current)
        elif type(current) is dict:
            if any(type(key) is not str for key in current):
                raise BootstrapInventoryError("JSON object key is not an exact string")
            try:
                for key in current:
                    key.encode("utf-8")
            except UnicodeEncodeError as error:
                raise BootstrapInventoryError("JSON key is not a Unicode scalar sequence") from error
            pending.extend((item, depth + 1) for item in current.values())
        else:
            raise BootstrapInventoryError("bootstrap value is not exact JSON")


def _decode(payload: object) -> dict[str, object]:
    if type(payload) is not bytes or len(payload) > _MAX_BYTES:
        raise BootstrapInventoryError("bootstrap response must be bounded bytes")
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"), object_pairs_hook=_closed_object,
            parse_int=_bounded_integer,
            parse_constant=lambda _: (_ for _ in ()).throw(
                BootstrapInventoryError("nonfinite JSON value")
            ),
        )
    except BootstrapInventoryError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise BootstrapInventoryError("bootstrap response JSON is invalid") from error
    _json_tree(value)
    if type(value) is not dict or set(value) != {"apiVersion", "kind", "items"} or (
        value.get("apiVersion"), value.get("kind")
    ) != ("v1", "List") or type(value.get("items")) is not list:
        raise BootstrapInventoryError("bootstrap response is not an exact Kubernetes List")
    return value


def _expected_configurations(profile: object, workload: object) -> dict[tuple[str, str, str], dict]:
    from .v3b2_contracts import V3B2Profile
    from .v3b2_manifests import WorkloadIdentity, render_objects
    from .v3b2_proofs import calico_objects

    if type(profile) is not V3B2Profile or type(workload) is not WorkloadIdentity:
        raise BootstrapInventoryError("profile and workload contracts must be exact")
    try:
        profile.__post_init__()
        workload.__post_init__()
        application = json.loads(render_objects(profile, workload))["items"]
        root = Path(__file__).resolve().parents[2]
        calico = calico_objects(
            (root / "deploy/kind/calico-v3.32.0.yaml").read_bytes(),
            (root / "deploy/kind/calico-v3.32.0.objects.json").read_bytes(),
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise BootstrapInventoryError("reviewed expected configurations are unavailable") from error
    wanted = {
        *(('Namespace', '', name) for name in _APP_NAMESPACES),
        *(('ServiceAccount', namespace, name) for namespace, name in _CALICO_SERVICE_ACCOUNTS | _KIL_SERVICE_ACCOUNTS),
        *(('ConfigMap', namespace, name) for namespace, name in _CALICO_CONFIG_MAPS | _KIL_CONFIG_MAPS),
    }
    result: dict[tuple[str, str, str], dict] = {}
    for item in (*application, *calico):
        if type(item) is not dict or type(item.get("metadata")) is not dict:
            raise BootstrapInventoryError("expected configuration projection is malformed")
        key = (item.get("kind"), item["metadata"].get("namespace", ""), item["metadata"].get("name"))
        if key in wanted:
            if key in result:
                raise BootstrapInventoryError("expected configuration identity is duplicated")
            result[key] = item
    if set(result) != wanted:
        raise BootstrapInventoryError("expected configuration identity set is incomplete")
    return result


def _identity(item: object) -> tuple[tuple[str, str, str], dict, BootstrapIdentityBinding] | None:
    if type(item) is not dict or item.get("kind") not in {"Namespace", "ServiceAccount", "ConfigMap"}:
        return None
    if type(item.get("metadata")) is not dict:
        raise BootstrapInventoryError("bootstrap metadata is invalid")
    metadata = item["metadata"]
    kind = item["kind"]
    if item.get("apiVersion") != "v1":
        raise BootstrapInventoryError("bootstrap API version is not exact v1")
    name = _exact_string("bootstrap name", metadata.get("name"))
    if kind == "Namespace":
        namespace = metadata.get("namespace", "")
        if namespace != "" or type(namespace) is not str:
            raise BootstrapInventoryError("Namespace must be canonically cluster-scoped")
    else:
        namespace = _exact_string("bootstrap namespace", metadata.get("namespace"))
    binding = BootstrapIdentityBinding(
        "v1", kind, namespace, name,
        _exact_string("bootstrap UID", metadata.get("uid")),
        _resource_version(metadata.get("resourceVersion")),
    )
    return (kind, namespace, name), item, binding


def _platform_namespace(name: str) -> dict[str, object]:
    return {
        "apiVersion": "v1", "kind": "Namespace",
        "metadata": {"name": name, "labels": {"kubernetes.io/metadata.name": name}},
        "spec": {"finalizers": ["kubernetes"]},
    }


def _platform_service_account(namespace: str, name: str) -> dict[str, object]:
    return {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"namespace": namespace, "name": name}}


def _platform_config_digest(item: dict, namespace: str, name: str) -> UnvalidatedPlatformConfiguration:
    if set(item) - {"apiVersion", "kind", "metadata", "data"}:
        raise BootstrapInventoryError("platform ConfigMap has an unknown root field")
    metadata = item["metadata"]
    if set(metadata) - {
        "name", "namespace", "uid", "resourceVersion", "creationTimestamp",
        "managedFields", "labels", "annotations",
    }:
        raise BootstrapInventoryError("platform ConfigMap has unknown metadata")
    for field in ("labels", "annotations"):
        if field in metadata and (
            type(metadata[field]) is not dict or len(metadata[field]) > 256
            or any(type(key) is not str or type(value) is not str or not key
                   or len(key) > 512 or len(value.encode("utf-8")) > 262_144
                   for key, value in metadata[field].items())
        ):
            raise BootstrapInventoryError(f"platform ConfigMap {field} is invalid")
    for field in ("data",):
        values = item.get(field)
        if field in item and (
            type(values) is not dict or any(
                type(key) is not str or not key or len(key) > 253 or type(value) is not str
                for key, value in values.items()
            )
        ):
            raise BootstrapInventoryError(f"platform ConfigMap {field} is invalid")
    try:
        configuration(item)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise BootstrapInventoryError("platform ConfigMap runtime metadata is invalid") from error
    document = deepcopy(item)
    for field in ("uid", "resourceVersion", "creationTimestamp", "managedFields"):
        document["metadata"].pop(field, None)
    try:
        digest = sha256(canonical_json(document).encode("utf-8")).hexdigest()
    except (ValueError, TypeError, RecursionError) as error:
        raise BootstrapInventoryError("platform ConfigMap content is unbounded") from error
    return UnvalidatedPlatformConfiguration(namespace, name, digest)


def _continuity(current: BootstrapIdentitySnapshot, prior: object) -> None:
    if prior is None:
        return
    if type(prior) is not BootstrapIdentitySnapshot:
        raise BootstrapInventoryError("prior bootstrap snapshot must be exact")
    prior.__post_init__()
    for old_rows, new_rows in (
        (prior.namespace_bindings, current.namespace_bindings),
        (prior.service_account_bindings, current.service_account_bindings),
        (prior.config_map_bindings, current.config_map_bindings),
    ):
        old = {(row.kind, row.namespace, row.name): row for row in old_rows}
        for row in new_rows:
            before = old[(row.kind, row.namespace, row.name)]
            if row.uid != before.uid or int(row.resource_version) < int(before.resource_version):
                raise BootstrapInventoryError("bootstrap identity was replaced or resourceVersion regressed")


def validate_bootstrap_identities(
    payload: bytes, *, profile: object, workload: object,
    cluster_incarnation_uid: str, prior: BootstrapIdentitySnapshot | None = None,
) -> BootstrapIdentitySnapshot:
    """Bind only the exact bootstrap identities; platform CM digests are diagnostic."""
    expected = _expected_configurations(profile, workload)
    if type(cluster_incarnation_uid) is not str or _UID.fullmatch(cluster_incarnation_uid) is None:
        raise BootstrapInventoryError("cluster incarnation UID is invalid")
    root = _decode(payload)
    selected: dict[tuple[str, str, str], tuple[dict, BootstrapIdentityBinding]] = {}
    for item in root["items"]:
        parsed = _identity(item)
        if parsed is None:
            continue
        key, document, binding = parsed
        if key in selected:
            raise BootstrapInventoryError("bootstrap identity is duplicated")
        selected[key] = (document, binding)
    expected_keys = (
        {("Namespace", "", name) for name in _NAMESPACES}
        | {("ServiceAccount", *key) for key in _SERVICE_ACCOUNTS}
        | {("ConfigMap", *key) for key in _CONFIG_MAPS}
    )
    if set(selected) != expected_keys:
        raise BootstrapInventoryError("bootstrap identity cardinality differs from the exact set")
    if selected[("Namespace", "", "kube-system")][1].uid != cluster_incarnation_uid:
        raise BootstrapInventoryError("kube-system UID differs from the cluster incarnation")
    if len({binding.uid for _, binding in selected.values()}) != 97:
        raise BootstrapInventoryError("bootstrap UIDs are not globally distinct")

    diagnostics: list[UnvalidatedPlatformConfiguration] = []
    for key, (document, _) in selected.items():
        kind, namespace, name = key
        comparable = document
        if kind == "Namespace":
            if set(document) - {"apiVersion", "kind", "metadata", "spec", "status"} or document.get("status") != {"phase": "Active"}:
                raise BootstrapInventoryError("Namespace state is not exactly Active")
            comparable = deepcopy(document)
            comparable["metadata"].pop("namespace", None)
            desired = expected.get(key, _platform_namespace(name))
            if not matches_configuration(desired, comparable):
                raise BootstrapInventoryError("Namespace configuration differs from the exact contract")
        elif kind == "ServiceAccount":
            if "status" in document:
                raise BootstrapInventoryError("ServiceAccount has unexpected status")
            desired = expected.get(key, _platform_service_account(namespace, name))
            if not matches_configuration(desired, document):
                raise BootstrapInventoryError("ServiceAccount configuration differs from the exact contract")
        elif (namespace, name) in _PLATFORM_CONFIG_MAPS:
            diagnostics.append(_platform_config_digest(document, namespace, name))
        else:
            if "status" in document or not matches_configuration(expected[key], document):
                raise BootstrapInventoryError("managed ConfigMap configuration differs from its source")

    snapshot = BootstrapIdentitySnapshot(
        tuple(sorted(binding for key, (_, binding) in selected.items() if key[0] == "Namespace")),
        tuple(sorted(binding for key, (_, binding) in selected.items() if key[0] == "ServiceAccount")),
        tuple(sorted(binding for key, (_, binding) in selected.items() if key[0] == "ConfigMap")),
        tuple(sorted(diagnostics)),
    )
    _continuity(snapshot, prior)
    return snapshot


__all__ = [
    "BootstrapIdentityBinding", "BootstrapIdentitySnapshot", "BootstrapInventoryError",
    "UnvalidatedPlatformConfiguration", "validate_bootstrap_identities",
]
