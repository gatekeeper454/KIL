"""Validate the exact Kind-rendered CoreDNS and local-path ConfigMaps.

The resulting proof binds only source configuration and observed API identity.
It does not establish ownership, generated state, readiness, or runtime contract
completion, and it deliberately does not interpret other platform ConfigMaps.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re

from .canonical import canonical_json
from .v3b2_api_defaults import configuration


_MAX_PAYLOAD_BYTES = 1024 * 1024
_MAX_ANNOTATION_BYTES = 256 * 1024
_MAX_DEPTH = 64
_MAX_TREE_ITEMS = 32_768
_UINT64_MAX = 2**64 - 1
_UID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_RESOURCE_VERSION = re.compile(r"[1-9][0-9]{0,19}")
_LAST_APPLIED = "kubectl.kubernetes.io/last-applied-configuration"

_COREFILE = ".:53 {\n    errors\n    health {\n       lameduck 5s\n    }\n    ready\n    kubernetes cluster.local in-addr.arpa ip6.arpa {\n       pods insecure\n       fallthrough in-addr.arpa ip6.arpa\n       ttl 30\n    }\n    prometheus :9153\n    forward . /etc/resolv.conf {\n       max_concurrent 1000\n    }\n    cache 30 {\n       disable success cluster.local\n       disable denial cluster.local\n    }\n    loop\n    reload\n    loadbalance\n}\n"
_CONFIG = "{\n        \"nodePathMap\":[\n        {\n                \"node\":\"DEFAULT_PATH_FOR_NON_LISTED_NODES\",\n                \"paths\":[\"/var/local-path-provisioner\"]\n        }\n        ]\n}"
_SETUP = "#!/bin/sh\nset -eu\nmkdir -m 0777 -p \"$VOL_DIR\""
_TEARDOWN = "#!/bin/sh\nset -eu\nrm -rf \"$VOL_DIR\""
_HELPER = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: helper-pod\nspec:\n  priorityClassName: system-node-critical\n  tolerations:\n    - key: node.kubernetes.io/disk-pressure\n      operator: Exists\n      effect: NoSchedule\n  containers:\n  - name: helper-pod\n    image: docker.io/kindest/local-path-helper:v20260131-7181c60a\n    imagePullPolicy: IfNotPresent"
_CORE_IDENTITY = ("kube-system", "coredns")
_LOCAL_PATH_IDENTITY = ("local-path-storage", "local-path-config")
_EXPECTED_IDENTITIES = frozenset((_CORE_IDENTITY, _LOCAL_PATH_IDENTITY))
_BASE_METADATA_KEYS = frozenset({
    "name", "namespace", "uid", "resourceVersion", "creationTimestamp",
    "managedFields",
})


class SourceRenderedConfigMapError(ValueError):
    """The bounded observation is malformed or differs from pinned sources."""


def _expected_data(identity: tuple[str, str]) -> dict[str, str]:
    """Return a fresh source map so module constants cannot be mutated indirectly."""
    if identity == _CORE_IDENTITY:
        return {"Corefile": _COREFILE}
    if identity == _LOCAL_PATH_IDENTITY:
        return {
            "config.json": _CONFIG,
            "setup": _SETUP,
            "teardown": _TEARDOWN,
            "helperPod.yaml": _HELPER,
        }
    raise SourceRenderedConfigMapError("source configuration identity is not exact")


def _source_configuration_digest(identity: tuple[str, str]) -> str:
    source = {
        "apiVersion": "v1", "kind": "ConfigMap",
        "metadata": {"name": identity[1], "namespace": identity[0]},
        "data": _expected_data(identity),
    }
    try:
        return sha256(canonical_json(source).encode("utf-8")).hexdigest()
    except (ValueError, TypeError, RecursionError) as error:
        raise SourceRenderedConfigMapError("source configuration is not canonical") from error


def _exact_string(label: str, value: object) -> str:
    if type(value) is not str:
        raise SourceRenderedConfigMapError(f"{label} must be an exact string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise SourceRenderedConfigMapError(f"{label} is not a Unicode scalar sequence") from error
    return value


def _uid(value: object) -> str:
    text = _exact_string("UID", value)
    if _UID.fullmatch(text) is None:
        raise SourceRenderedConfigMapError("UID is not a bounded opaque API identity")
    return text


def _resource_version(value: object) -> str:
    text = _exact_string("resourceVersion", value)
    if _RESOURCE_VERSION.fullmatch(text) is None or int(text) > _UINT64_MAX:
        raise SourceRenderedConfigMapError("resourceVersion is not a canonical positive uint64")
    return text


@dataclass(frozen=True, slots=True, order=True)
class SourceRenderedConfigMapBinding:
    api_version: str
    kind: str
    namespace: str
    name: str
    uid: str
    resource_version: str
    source_configuration_sha256: str

    def __post_init__(self) -> None:
        if type(self.api_version) is not str or type(self.kind) is not str:
            raise SourceRenderedConfigMapError("binding API identity fields must be exact strings")
        if self.api_version != "v1" or self.kind != "ConfigMap":
            raise SourceRenderedConfigMapError("binding API identity is not v1 ConfigMap")
        identity = (_exact_string("namespace", self.namespace),
                    _exact_string("name", self.name))
        if identity not in _EXPECTED_IDENTITIES:
            raise SourceRenderedConfigMapError("binding identity is not source-rendered")
        _uid(self.uid)
        _resource_version(self.resource_version)
        if (type(self.source_configuration_sha256) is not str
                or self.source_configuration_sha256 != _source_configuration_digest(identity)):
            raise SourceRenderedConfigMapError("source configuration digest does not match its identity")


@dataclass(frozen=True, slots=True)
class SourceRenderedConfigMapsProof:
    bindings: tuple[SourceRenderedConfigMapBinding, ...]
    runtime_contract_complete: bool = False

    def __post_init__(self) -> None:
        if type(self.bindings) is not tuple or len(self.bindings) != 2 or any(
            type(binding) is not SourceRenderedConfigMapBinding for binding in self.bindings
        ):
            raise SourceRenderedConfigMapError("proof bindings are not exact")
        for binding in self.bindings:
            binding.__post_init__()
        if self.bindings != tuple(sorted(self.bindings)) or {
            (binding.namespace, binding.name) for binding in self.bindings
        } != _EXPECTED_IDENTITIES:
            raise SourceRenderedConfigMapError("proof bindings are not the canonical exact set")
        if self.runtime_contract_complete is not False:
            raise SourceRenderedConfigMapError("source proof cannot complete the runtime contract")


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SourceRenderedConfigMapError("duplicate JSON object key")
        result[key] = value
    return result


def _bounded_integer(value: str) -> int:
    if len(value.lstrip("-")) > 128:
        raise SourceRenderedConfigMapError("JSON integer is unbounded")
    return int(value)


def _reject_float(_: str) -> float:
    raise SourceRenderedConfigMapError("floating-point JSON is not admitted")


def _reject_constant(_: str) -> object:
    raise SourceRenderedConfigMapError("nonfinite JSON value")


def _validate_tree(value: object) -> None:
    pending = [(value, 0)]
    count = 0
    while pending:
        current, depth = pending.pop()
        count += 1
        if depth > _MAX_DEPTH or count > _MAX_TREE_ITEMS:
            raise SourceRenderedConfigMapError("JSON tree is unbounded")
        if type(current) is str:
            _exact_string("JSON string", current)
        elif current is None or type(current) in {bool, int}:
            continue
        elif type(current) is list:
            pending.extend((item, depth + 1) for item in current)
        elif type(current) is dict:
            for key, item in current.items():
                _exact_string("JSON key", key)
                pending.append((item, depth + 1))
        else:
            raise SourceRenderedConfigMapError("value is not exact JSON")


def _decode_json(text: str, *, label: str) -> object:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_closed_object,
            parse_int=_bounded_integer,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
        _validate_tree(value)
        return value
    except SourceRenderedConfigMapError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError) as error:
        raise SourceRenderedConfigMapError(f"{label} JSON is invalid") from error


def _decode_payload(payload: object) -> dict[str, object]:
    if type(payload) is not bytes or len(payload) > _MAX_PAYLOAD_BYTES:
        raise SourceRenderedConfigMapError("response must be bounded bytes")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise SourceRenderedConfigMapError("response is not strict UTF-8") from error
    value = _decode_json(text, label="response")
    if (type(value) is not dict or set(value) != {"apiVersion", "kind", "items"}
            or value.get("apiVersion") != "v1" or value.get("kind") != "List"
            or type(value.get("items")) is not list or len(value["items"]) != 2
            or any(type(item) is not dict for item in value["items"])):
        raise SourceRenderedConfigMapError("response is not the exact two-item Kubernetes v1 List")
    return value


def _exact_data(value: object, expected: dict[str, str]) -> dict[str, str]:
    if type(value) is not dict or set(value) != set(expected):
        raise SourceRenderedConfigMapError("ConfigMap data keys are not exact")
    for key, expected_value in expected.items():
        if type(value[key]) is not str or value[key] != expected_value:
            raise SourceRenderedConfigMapError("ConfigMap source data differs from the pinned value")
    return value


def _validate_last_applied(annotation: object) -> None:
    text = _exact_string("last-applied annotation", annotation)
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as error:  # Kept local to normalize future changes.
        raise SourceRenderedConfigMapError("last-applied annotation is not UTF-8") from error
    if len(encoded) > _MAX_ANNOTATION_BYTES:
        raise SourceRenderedConfigMapError("last-applied annotation is unbounded")
    value = _decode_json(text, label="last-applied annotation")
    if (type(value) is not dict or set(value) != {"apiVersion", "kind", "metadata", "data"}
            or value.get("apiVersion") != "v1" or value.get("kind") != "ConfigMap"):
        raise SourceRenderedConfigMapError("last-applied annotation root is not exact")
    metadata = value.get("metadata")
    allowed_metadata = {"name", "namespace"}
    if type(metadata) is not dict or set(metadata) not in (
        allowed_metadata, allowed_metadata | {"annotations"}
    ) or metadata.get("name") != "local-path-config" or metadata.get(
        "namespace"
    ) != "local-path-storage":
        raise SourceRenderedConfigMapError("last-applied metadata is not exact")
    if "annotations" in metadata and (
        type(metadata["annotations"]) is not dict or metadata["annotations"] != {}
    ):
        raise SourceRenderedConfigMapError("last-applied annotations are not absent or empty")
    _exact_data(value.get("data"), _expected_data(_LOCAL_PATH_IDENTITY))


def _binding(item: dict[str, object]) -> SourceRenderedConfigMapBinding:
    if (set(item) != {"apiVersion", "kind", "metadata", "data"}
            or item.get("apiVersion") != "v1" or item.get("kind") != "ConfigMap"):
        raise SourceRenderedConfigMapError("observed ConfigMap root is not exact")
    metadata = item.get("metadata")
    if type(metadata) is not dict:
        raise SourceRenderedConfigMapError("observed ConfigMap metadata is not an object")
    identity = (metadata.get("namespace"), metadata.get("name"))
    if identity not in _EXPECTED_IDENTITIES:
        raise SourceRenderedConfigMapError("observed ConfigMap identity is not exact")
    required = _BASE_METADATA_KEYS | ({"annotations"} if identity == _LOCAL_PATH_IDENTITY else set())
    if set(metadata) != required:
        raise SourceRenderedConfigMapError("observed ConfigMap metadata keys are not exact")
    uid = _uid(metadata.get("uid"))
    resource_version = _resource_version(metadata.get("resourceVersion"))
    if identity == _LOCAL_PATH_IDENTITY:
        annotations = metadata.get("annotations")
        if type(annotations) is not dict or set(annotations) != {_LAST_APPLIED}:
            raise SourceRenderedConfigMapError("local-path producer annotation is not exact")
        _validate_last_applied(annotations[_LAST_APPLIED])
    expected = _expected_data(identity)
    _exact_data(item.get("data"), expected)
    try:
        # Reuse the reviewed Kubernetes API timestamp and managedFields checks.
        configuration(item)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise SourceRenderedConfigMapError("runtime metadata is invalid") from error
    digest = _source_configuration_digest(identity)
    return SourceRenderedConfigMapBinding(
        "v1", "ConfigMap", identity[0], identity[1], uid, resource_version, digest
    )


def validate_source_rendered_configmaps(payload: bytes) -> SourceRenderedConfigMapsProof:
    """Validate and bind only the two pinned source-rendered ConfigMaps."""
    try:
        root = _decode_payload(payload)
        bindings = tuple(sorted(_binding(item) for item in root["items"]))
        if len({(binding.namespace, binding.name) for binding in bindings}) != 2:
            raise SourceRenderedConfigMapError("ConfigMap identities are missing or duplicated")
        return SourceRenderedConfigMapsProof(bindings)
    except SourceRenderedConfigMapError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError) as error:
        raise SourceRenderedConfigMapError("source-rendered ConfigMap validation failed") from error


__all__ = [
    "SourceRenderedConfigMapBinding", "SourceRenderedConfigMapError",
    "SourceRenderedConfigMapsProof", "validate_source_rendered_configmaps",
]
