"""Validate ten kubeadm trust ConfigMaps; never prove readiness or ownership."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import re
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from .v3b2_api_defaults import configuration
_MAX_TREE_BYTES = 2 * 1024 * 1024
_MAX_PEM_BYTES = 1024 * 1024
_MAX_DEPTH = 64
_MAX_TREE_ITEMS = 32_768
_UINT64_MAX = 2**64 - 1
_UID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_RESOURCE_VERSION = re.compile(r"[1-9][0-9]{0,19}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z")
_UTC_DATE = re.compile(r"\d{4}-\d\d-\d\d")
_PEM_SHAPE = re.compile(
    rb"[ \t\r\n\f\v]*-----BEGIN CERTIFICATE-----[ \t\r\n\f\v]+"
    rb"[A-Za-z0-9+/= \t\r\n\f\v]+-----END CERTIFICATE-----[ \t\r\n\f\v]*"
)
_ROOT_NAMESPACES = frozenset(("default", "kube-node-lease", "kube-public", "kube-system",
                              "local-path-storage", "kil-v3-baseline", "kil-v3-signed",
                              "kil-v3-local-reduce"))
_ROOT_NAME = "kube-root-ca.crt"
_EXTENSION_NAME = "extension-apiserver-authentication"
_LEGACY_NAME = "kube-apiserver-legacy-service-account-token-tracking"
_DESCRIPTION = (
    "Contains a CA bundle that can be used to verify the kube-apiserver when "
    "using internal endpoints such as the internal service IP or "
    "kubernetes.default.svc. No other usage is guaranteed across distributions."
)
_BASE_METADATA_KEYS = frozenset(("name", "namespace", "uid", "resourceVersion",
                                 "creationTimestamp", "managedFields"))
_EXTENSION_VALUES = (
    ("requestheader-username-headers", '["X-Remote-User"]'),
    ("requestheader-group-headers", '["X-Remote-Group"]'),
    ("requestheader-extra-headers-prefix", '["X-Remote-Extra-"]'),
    ("requestheader-allowed-names", '["front-proxy-client"]'),
)
class TrustConfigMapsError(ValueError):
    """The bounded trust observation or its evidence is invalid."""
def _exact_string(label: str, value: object) -> str:
    if type(value) is not str:
        raise TrustConfigMapsError(f"{label} must be an exact string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise TrustConfigMapsError(f"{label} is not a Unicode scalar sequence") from error
    return value
def _uid(value: object) -> str:
    text = _exact_string("UID", value)
    if _UID.fullmatch(text) is None:
        raise TrustConfigMapsError("UID is not a bounded opaque API identity")
    return text
def _resource_version(value: object) -> str:
    text = _exact_string("resourceVersion", value)
    if _RESOURCE_VERSION.fullmatch(text) is None or int(text) > _UINT64_MAX:
        raise TrustConfigMapsError("resourceVersion is not a canonical positive uint64")
    return text
def _digest(value: object, label: str) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise TrustConfigMapsError(f"{label} is not a lowercase SHA-256 digest")
    return value
def _timestamp_date(value: object) -> date:
    text = _exact_string("creationTimestamp", value)
    if _TIMESTAMP.fullmatch(text) is None:
        raise TrustConfigMapsError("creationTimestamp is not an exact UTC API timestamp")
    try:
        return datetime.fromisoformat(text[:-1] + "+00:00").date()
    except ValueError as error:
        raise TrustConfigMapsError("creationTimestamp is not a real UTC time") from error
def _since_date(value: object) -> date:
    text = _exact_string("legacy since", value)
    if _UTC_DATE.fullmatch(text) is None:
        raise TrustConfigMapsError("legacy since is not YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise TrustConfigMapsError("legacy since is not a real UTC date") from error
def _base_identity(api_version: object, kind: object, namespace: object,
                   name: object, uid: object, resource_version: object) -> tuple[str, str]:
    if (_exact_string("apiVersion", api_version) != "v1"
            or _exact_string("kind", kind) != "ConfigMap"):
        raise TrustConfigMapsError("binding is not a v1 ConfigMap")
    identity = (_exact_string("namespace", namespace), _exact_string("name", name))
    _uid(uid)
    _resource_version(resource_version)
    return identity
@dataclass(frozen=True, slots=True, order=True)
class RootCABinding:
    api_version: str
    kind: str
    namespace: str
    name: str
    uid: str
    resource_version: str
    cluster_certificate_der_sha256: str

    def __post_init__(self) -> None:
        identity = _base_identity(
            self.api_version, self.kind, self.namespace, self.name,
            self.uid, self.resource_version,
        )
        if identity[0] not in _ROOT_NAMESPACES or identity[1] != _ROOT_NAME:
            raise TrustConfigMapsError("root CA binding identity is not exact")
        _digest(self.cluster_certificate_der_sha256, "cluster certificate")
@dataclass(frozen=True, slots=True)
class ExtensionAuthBinding:
    api_version: str
    kind: str
    namespace: str
    name: str
    uid: str
    resource_version: str
    cluster_client_certificate_der_sha256: str
    front_proxy_certificate_der_sha256: str

    def __post_init__(self) -> None:
        if _base_identity(
            self.api_version, self.kind, self.namespace, self.name,
            self.uid, self.resource_version,
        ) != ("kube-system", _EXTENSION_NAME):
            raise TrustConfigMapsError("extension authentication identity is not exact")
        cluster = _digest(self.cluster_client_certificate_der_sha256, "cluster client certificate")
        front = _digest(self.front_proxy_certificate_der_sha256, "front-proxy certificate")
        if cluster == front:
            raise TrustConfigMapsError("cluster and front-proxy certificate roles are not distinct")
@dataclass(frozen=True, slots=True)
class LegacyTrackingBinding:
    api_version: str
    kind: str
    namespace: str
    name: str
    uid: str
    resource_version: str
    since_utc_date: str
    creation_timestamp: str

    def __post_init__(self) -> None:
        if _base_identity(
            self.api_version, self.kind, self.namespace, self.name,
            self.uid, self.resource_version,
        ) != ("kube-system", _LEGACY_NAME):
            raise TrustConfigMapsError("legacy tracking identity is not exact")
        since = _since_date(self.since_utc_date)
        created = _timestamp_date(self.creation_timestamp)
        if (created - since).days not in (0, 1):
            raise TrustConfigMapsError("legacy since is not creation day or previous UTC day")
@dataclass(frozen=True, slots=True)
class TrustConfigMapsProof:
    root_ca_bindings: tuple[RootCABinding, ...]
    extension_auth_binding: ExtensionAuthBinding
    legacy_tracking_binding: LegacyTrackingBinding
    runtime_contract_complete: bool = False

    def __post_init__(self) -> None:
        try:
            self._revalidate()
        except TrustConfigMapsError:
            raise
        except (AttributeError, TypeError, ValueError, OverflowError, RecursionError) as error:
            raise TrustConfigMapsError("trust proof contains a malformed binding") from error

    def _revalidate(self) -> None:
        if (type(self.root_ca_bindings) is not tuple
                or len(self.root_ca_bindings) != len(_ROOT_NAMESPACES)
                or any(type(row) is not RootCABinding for row in self.root_ca_bindings)
                or type(self.extension_auth_binding) is not ExtensionAuthBinding
                or type(self.legacy_tracking_binding) is not LegacyTrackingBinding):
            raise TrustConfigMapsError("proof binding types and counts are not exact")
        for row in self.root_ca_bindings:
            row.__post_init__()
        self.extension_auth_binding.__post_init__()
        self.legacy_tracking_binding.__post_init__()
        if (self.root_ca_bindings != tuple(sorted(self.root_ca_bindings))
                or {row.namespace for row in self.root_ca_bindings} != _ROOT_NAMESPACES):
            raise TrustConfigMapsError("root CA proof is not the canonical exact namespace set")
        cluster = self.extension_auth_binding.cluster_client_certificate_der_sha256
        if any(row.cluster_certificate_der_sha256 != cluster for row in self.root_ca_bindings):
            raise TrustConfigMapsError("root and extension cluster CA digests are inconsistent")
        if self.runtime_contract_complete is not False:
            raise TrustConfigMapsError("trust proof cannot complete the runtime contract")

def _tree_string_size(label: str, value: object, remaining: int) -> int:
    if type(value) is not str:
        raise TrustConfigMapsError(f"{label} must be an exact string")
    if remaining < 0 or len(value) > remaining:
        raise TrustConfigMapsError("decoded JSON tree is unbounded")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise TrustConfigMapsError(f"{label} is not a Unicode scalar sequence") from error
    if len(encoded) > remaining:
        raise TrustConfigMapsError("decoded JSON tree is unbounded")
    return len(encoded)

def _validate_tree(documents: tuple[dict, ...]) -> None:
    if len(documents) > _MAX_TREE_ITEMS:
        raise TrustConfigMapsError("decoded JSON tree is unbounded")
    pending: list[tuple[bool, object, int]] = [
        (False, document, 0) for document in reversed(documents)
    ]
    active: set[int] = set()
    remaining_items = _MAX_TREE_ITEMS - len(documents)
    size = 0
    while pending:
        exiting, current, depth = pending.pop()
        if exiting:
            active.remove(id(current))
            continue
        if depth > _MAX_DEPTH:
            raise TrustConfigMapsError("decoded JSON tree is unbounded")
        if type(current) is str:
            size += _tree_string_size(
                "JSON string", current, _MAX_TREE_BYTES - size - 2,
            ) + 2
        elif current is None or type(current) is bool:
            size += 5
        elif type(current) is int:
            if current.bit_length() > 426:
                raise TrustConfigMapsError("JSON integer is unbounded")
            size += len(str(current))
        elif type(current) in (dict, list):
            marker = id(current)
            if marker in active:
                raise TrustConfigMapsError("decoded JSON tree contains a cycle")
            child_cost = len(current) * (2 if type(current) is dict else 1)
            if child_cost > remaining_items or (current and depth >= _MAX_DEPTH):
                raise TrustConfigMapsError("decoded JSON tree is unbounded")
            remaining_items -= child_cost
            active.add(marker)
            pending.append((True, current, depth))
            size += 2
            if type(current) is list:
                for item in reversed(current):
                    pending.append((False, item, depth + 1))
            else:
                for key in reversed(current):
                    size += _tree_string_size(
                        "JSON key", key, _MAX_TREE_BYTES - size - 3,
                    ) + 3
                    pending.append((False, current[key], depth + 1))
        else:
            raise TrustConfigMapsError("decoded value is not exact JSON")
        if size > _MAX_TREE_BYTES:
            raise TrustConfigMapsError("decoded JSON tree is unbounded")
def _certificate_digest(value: object, label: str, *, text: bool) -> str:
    if text:
        raw = _exact_string(label, value).encode("utf-8")
    elif type(value) is bytes:
        raw = value
    else:
        raise TrustConfigMapsError(f"{label} must be exact bytes")
    if not raw or len(raw) > _MAX_PEM_BYTES:
        raise TrustConfigMapsError(f"{label} PEM is empty or unbounded")
    if (raw.count(b"-----BEGIN CERTIFICATE-----") != 1
            or raw.count(b"-----END CERTIFICATE-----") != 1
            or _PEM_SHAPE.fullmatch(raw) is None):
        raise TrustConfigMapsError(f"{label} is not exactly one PEM certificate")
    certificates = x509.load_pem_x509_certificates(raw.strip(b" \t\r\n\f\v"))
    if len(certificates) != 1:
        raise TrustConfigMapsError(f"{label} is not a unique single certificate")
    certificate = certificates[0]
    constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints).value
    if constraints.ca is not True:
        raise TrustConfigMapsError(f"{label} certificate is not a CA")
    der = certificate.public_bytes(serialization.Encoding.DER)
    return sha256(der).hexdigest()
def _metadata(item: dict, identity: tuple[str, str], *, root: bool) -> tuple[str, str, str]:
    metadata = item.get("metadata")
    if type(metadata) is not dict:
        raise TrustConfigMapsError("ConfigMap metadata is not an exact object")
    expected_keys = _BASE_METADATA_KEYS | ({"annotations"} if root else set())
    if set(metadata) != expected_keys:
        raise TrustConfigMapsError("ConfigMap metadata keys are not exact")
    namespace = _exact_string("metadata namespace", metadata.get("namespace"))
    name = _exact_string("metadata name", metadata.get("name"))
    if (namespace, name) != identity:
        raise TrustConfigMapsError("ConfigMap metadata identity changed during validation")
    uid = _uid(metadata.get("uid"))
    resource_version = _resource_version(metadata.get("resourceVersion"))
    creation_timestamp = _exact_string("creationTimestamp", metadata.get("creationTimestamp"))
    try:
        configuration(item)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise TrustConfigMapsError("runtime metadata is invalid") from error
    return uid, resource_version, creation_timestamp
def _identity(item: dict) -> tuple[str, str]:
    if set(item) != {"apiVersion", "kind", "metadata", "data"}:
        raise TrustConfigMapsError("observed ConfigMap root keys are not exact")
    if (_exact_string("apiVersion", item.get("apiVersion")) != "v1"
            or _exact_string("kind", item.get("kind")) != "ConfigMap"):
        raise TrustConfigMapsError("observed object is not a v1 ConfigMap")
    metadata = item.get("metadata")
    if type(metadata) is not dict:
        raise TrustConfigMapsError("observed ConfigMap metadata is not an object")
    return (_exact_string("namespace", metadata.get("namespace")),
            _exact_string("name", metadata.get("name")))
def validate_trust_configmaps(
    documents: tuple[dict, ...], *, cluster_ca_pem: bytes, front_proxy_ca_pem: bytes,
) -> TrustConfigMapsProof:
    """Validate and bind the exact ten fresh kubeadm trust ConfigMaps."""
    try:
        if (type(documents) is not tuple or len(documents) != 10
                or any(type(item) is not dict for item in documents)):
            raise TrustConfigMapsError("documents must be an exact ten-dict tuple")
        _validate_tree(documents)
        cluster_digest = _certificate_digest(cluster_ca_pem, "cluster CA evidence", text=False)
        front_digest = _certificate_digest(front_proxy_ca_pem, "front-proxy CA evidence", text=False)
        if cluster_digest == front_digest:
            raise TrustConfigMapsError("cluster and front-proxy evidence certificates are identical")
        roots: list[RootCABinding] = []
        extension: ExtensionAuthBinding | None = None
        legacy: LegacyTrackingBinding | None = None
        seen: set[tuple[str, str]] = set()
        for item in documents:
            identity = _identity(item)
            if identity in seen:
                raise TrustConfigMapsError("ConfigMap identity is duplicated")
            seen.add(identity)
            is_root = identity[1] == _ROOT_NAME and identity[0] in _ROOT_NAMESPACES
            uid, resource_version, creation_timestamp = _metadata(item, identity, root=is_root)
            data = item.get("data")
            if type(data) is not dict:
                raise TrustConfigMapsError("ConfigMap data is not an exact object")
            if is_root:
                annotations = item["metadata"]["annotations"]
                if (type(annotations) is not dict
                        or set(annotations) != {"kubernetes.io/description"}
                        or _exact_string("root CA description", annotations.get("kubernetes.io/description")) != _DESCRIPTION):
                    raise TrustConfigMapsError("root CA annotation is not exact")
                if set(data) != {"ca.crt"}:
                    raise TrustConfigMapsError("root CA data keys are not exact")
                observed_digest = _certificate_digest(data.get("ca.crt"), "root CA", text=True)
                if observed_digest != cluster_digest:
                    raise TrustConfigMapsError("root CA does not match cluster CA evidence")
                roots.append(RootCABinding(
                    "v1", "ConfigMap", identity[0], identity[1], uid,
                    resource_version, observed_digest,
                ))
            elif identity == ("kube-system", _EXTENSION_NAME):
                expected_keys = {"client-ca-file", "requestheader-client-ca-file"} | {
                    key for key, _ in _EXTENSION_VALUES
                }
                if set(data) != expected_keys:
                    raise TrustConfigMapsError("extension authentication data keys are not exact")
                for key, expected in _EXTENSION_VALUES:
                    if _exact_string(key, data.get(key)) != expected:
                        raise TrustConfigMapsError("extension authentication header value is not exact")
                observed_cluster = _certificate_digest(data.get("client-ca-file"), "client CA", text=True)
                observed_front = _certificate_digest(
                    data.get("requestheader-client-ca-file"), "requestheader client CA", text=True,
                )
                if observed_cluster != cluster_digest or observed_front != front_digest:
                    raise TrustConfigMapsError("extension CA roles do not match independent evidence")
                extension = ExtensionAuthBinding(
                    "v1", "ConfigMap", identity[0], identity[1], uid, resource_version,
                    observed_cluster, observed_front,
                )
            elif identity == ("kube-system", _LEGACY_NAME):
                if set(data) != {"since"}:
                    raise TrustConfigMapsError("legacy tracking data keys are not exact")
                legacy = LegacyTrackingBinding(
                    "v1", "ConfigMap", identity[0], identity[1], uid, resource_version,
                    _exact_string("legacy since", data.get("since")), creation_timestamp,
                )
            else:
                raise TrustConfigMapsError("ConfigMap identity is outside the exact trust set")
        if extension is None or legacy is None:
            raise TrustConfigMapsError("required trust ConfigMap identity is missing")
        return TrustConfigMapsProof(tuple(sorted(roots)), extension, legacy)
    except TrustConfigMapsError:
        raise
    except (ValueError, x509.ExtensionNotFound, x509.DuplicateExtension, TypeError,
            KeyError, AttributeError, UnicodeError, OverflowError, RecursionError) as error:
        raise TrustConfigMapsError("trust ConfigMap validation failed") from error
__all__ = ("ExtensionAuthBinding", "LegacyTrackingBinding", "RootCABinding",
           "TrustConfigMapsError", "TrustConfigMapsProof", "validate_trust_configmaps")
