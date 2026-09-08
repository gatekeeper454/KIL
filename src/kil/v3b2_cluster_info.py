"""Fail-closed proof of one kubeadm public ``cluster-info`` ConfigMap."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit
import base64, binascii, hmac, json, re
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from .v3b2_api_defaults import configuration
_MAX_TREE_BYTES, _MAX_TREE_ITEMS, _MAX_DEPTH = 1024 * 1024, 32_768, 64
_MAX_KUBECONFIG_BYTES, _MAX_JWS_BYTES = 256 * 1024, 8192
_UINT64_MAX = 2**64 - 1
_UID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}"); _RV = re.compile(r"[1-9][0-9]{0,19}")
_DIGEST = re.compile(r"[0-9a-f]{64}"); _TOKEN_ID = re.compile(r"[a-z0-9]{6}")
_TOKEN_SECRET = re.compile(rb"[a-z0-9]{16}")
_TIMESTAMP = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?Z")
_B64URL = re.compile(r"[A-Za-z0-9_-]+")
_B64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")
_PEM = re.compile(
    rb"[ \t\r\n\f\v]*-----BEGIN CERTIFICATE-----[ \t\r\n\f\v]+"
    rb"[A-Za-z0-9+/= \t\r\n\f\v]+-----END CERTIFICATE-----[ \t\r\n\f\v]*")
_METADATA_KEYS = frozenset(("name", "namespace", "uid", "resourceVersion", "creationTimestamp", "managedFields"))
class ClusterInfoError(ValueError):
    """The cluster-info observation or private token evidence is invalid."""
def _string(label: str, value: object, *, maximum: int | None = None) -> str:
    if type(value) is not str:
        raise ClusterInfoError(f"{label} must be an exact string")
    if maximum is not None and len(value) > maximum:
        raise ClusterInfoError(f"{label} is unbounded")
    try:
        raw = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ClusterInfoError(f"{label} is not a Unicode scalar sequence") from error
    if maximum is not None and len(raw) > maximum:
        raise ClusterInfoError(f"{label} is unbounded")
    return value
def _digest(label: str, value: object) -> str:
    if type(value) is not str or len(value) != 64 or _DIGEST.fullmatch(value) is None:
        raise ClusterInfoError(f"{label} is not a lowercase SHA-256 digest")
    return value
def _uid(value: object) -> str:
    text = _string("UID", value, maximum=128)
    if _UID.fullmatch(text) is None:
        raise ClusterInfoError("UID is not a bounded opaque API identity")
    return text
def _rv(value: object) -> str:
    text = _string("resourceVersion", value, maximum=20)
    if _RV.fullmatch(text) is None or int(text) > _UINT64_MAX:
        raise ClusterInfoError("resourceVersion is not a canonical positive uint64")
    return text
def _time(label: str, value: object) -> tuple[str, tuple[datetime, int]]:
    text = _string(label, value, maximum=30)
    match = _TIMESTAMP.fullmatch(text)
    if match is None:
        raise ClusterInfoError(f"{label} is not an exact UTC RFC3339 timestamp")
    try:
        second = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise ClusterInfoError(f"{label} is not a real UTC timestamp") from error
    nanos = int((match.group(2) or "").ljust(9, "0"))
    return text, (second, nanos)
def _server(value: object) -> str:
    text = _string("internal server", value, maximum=2048)
    try:
        parsed = urlsplit(text)
        _ = parsed.port
    except ValueError as error:
        raise ClusterInfoError("internal server is not a valid HTTPS URL") from error
    authority = re.fullmatch(r"(?:\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9._~!$&'()*+,;=-]+)(?::[0-9]+)?", parsed.netloc)
    path = re.fullmatch(r"(?:[A-Za-z0-9._~!$&'()*+,;=:@/-]|%[0-9A-Fa-f]{2})*", parsed.path)
    if (parsed.scheme != "https" or not parsed.netloc or not parsed.hostname
            or authority is None or path is None
            or parsed.username is not None or parsed.password is not None
            or "?" in text or "#" in text
            or any(character.isspace() for character in text)):
        raise ClusterInfoError("internal server is not a closed HTTPS URL")
    return text
def _token(token_id: object, token_secret: object) -> tuple[str, bytes]:
    if type(token_id) is not str or len(token_id) != 6 or _TOKEN_ID.fullmatch(token_id) is None:
        raise ClusterInfoError("token ID is not exactly six lowercase alphanumerics")
    if type(token_secret) is not bytes or _TOKEN_SECRET.fullmatch(token_secret) is None:
        raise ClusterInfoError("token secret is not exactly sixteen lowercase alphanumerics")
    return token_id, token_secret
def _validate_tree(document: dict) -> None:
    pending: list[tuple[bool, object, int]] = [(False, document, 0)]
    active: set[int] = set(); items = size = 0; remaining = _MAX_TREE_ITEMS - 1
    while pending:
        exiting, current, depth = pending.pop()
        if exiting:
            active.remove(id(current))
            continue
        items += 1
        if items > _MAX_TREE_ITEMS or depth > _MAX_DEPTH:
            raise ClusterInfoError("decoded JSON tree is unbounded")
        if type(current) is str:
            if len(current) > _MAX_TREE_BYTES - size - 2: raise ClusterInfoError("decoded JSON tree is unbounded")
            size += len(_string("JSON string", current).encode("utf-8")) + 2
        elif current is None or type(current) is bool:
            size += 5
        elif type(current) is int:
            if current.bit_length() > 426:
                raise ClusterInfoError("decoded JSON integer is unbounded")
            size += len(str(current))
        elif type(current) in (dict, list):
            marker = id(current)
            if marker in active:
                raise ClusterInfoError("decoded JSON tree contains a cycle")
            if current and depth >= _MAX_DEPTH:
                raise ClusterInfoError("decoded JSON tree is unbounded")
            if len(current) > remaining:
                raise ClusterInfoError("decoded JSON tree is unbounded")
            remaining -= len(current)
            active.add(marker)
            pending.append((True, current, depth))
            size += 2
            if type(current) is list:
                for child in reversed(current):
                    pending.append((False, child, depth + 1))
            else:
                for key in reversed(current):
                    if type(key) is not str:
                        raise ClusterInfoError("decoded JSON key is not an exact string")
                    if len(key) > _MAX_TREE_BYTES - size - 3: raise ClusterInfoError("decoded JSON tree is unbounded")
                    size += len(_string("JSON key", key).encode("utf-8")) + 3
                    pending.append((False, current[key], depth + 1))
        else:
            raise ClusterInfoError("decoded value is not exact JSON")
        if size > _MAX_TREE_BYTES:
            raise ClusterInfoError("decoded JSON tree is unbounded")
def _yaml_pair(line: str, indent: int) -> tuple[str, str]:
    if len(line) - len(line.lstrip(" ")) != indent:
        raise ClusterInfoError("kubeconfig indentation is outside the closed subset")
    body = line[indent:]
    if ":" not in body:
        raise ClusterInfoError("kubeconfig line is not a mapping entry")
    key, separator, value = body.partition(":")
    if not key or separator != ":" or (value and not value.startswith(" ")):
        raise ClusterInfoError("kubeconfig mapping syntax is not exact")
    return key, value[1:] if value else ""
def _empty(value: str, *, sequence: bool = False) -> bool:
    return value in (("", "null", "[]") if sequence else ("{}",))
def _parse_cluster(lines: list[str]) -> dict[str, str]:
    if not lines or not lines[0].startswith("- "):
        raise ClusterInfoError("clusters is not a one-entry sequence")
    first_key, first_value = _yaml_pair(lines[0][2:], 0)
    if first_key not in {"name", "cluster"}:
        raise ClusterInfoError("cluster entry fields are not exact")
    entry: dict[str, object] = {}; index = 0
    while index < len(lines):
        line = lines[index]
        if index == 0:
            key, value = first_key, first_value
        else:
            if line.startswith("- "):
                raise ClusterInfoError("clusters contains more than one entry")
            key, value = _yaml_pair(line, 2)
        if key in entry or key not in {"name", "cluster"}:
            raise ClusterInfoError("cluster entry fields are not exact")
        if key == "name":
            if value not in ('""', "''"):
                raise ClusterInfoError("cluster name is not the empty string")
            entry[key] = ""
            index += 1
            continue
        if value:
            raise ClusterInfoError("cluster mapping is not nested")
        nested: dict[str, str] = {}
        index += 1
        while index < len(lines) and lines[index].startswith("    "):
            nested_key, nested_value = _yaml_pair(lines[index], 4)
            if (nested_key in nested
                    or nested_key not in {"certificate-authority-data", "server"}
                    or not nested_value):
                raise ClusterInfoError("cluster TLS fields are not exact")
            nested[nested_key] = nested_value
            index += 1
        entry[key] = nested
    if set(entry) != {"name", "cluster"} or set(entry["cluster"]) != {
            "certificate-authority-data", "server"}:
        raise ClusterInfoError("cluster entry is incomplete")
    return entry["cluster"]  # type: ignore[return-value]
def _parse_kubeconfig(value: object, server: str, ca_digest: str) -> str:
    text = _string("kubeconfig", value, maximum=_MAX_KUBECONFIG_BYTES)
    if not text.endswith("\n") or text.endswith("\n\n") or "\r" in text or "\t" in text:
        raise ClusterInfoError("kubeconfig must use one final LF and no tabs")
    lines = text[:-1].split("\n")
    if not lines or any(not line for line in lines):
        raise ClusterInfoError("kubeconfig contains empty lines")
    blocks: dict[str, tuple[str, list[str]]] = {}; index = 0
    while index < len(lines):
        if lines[index].startswith((" ", "- ")):
            raise ClusterInfoError("kubeconfig has an orphan nested entry")
        key, scalar = _yaml_pair(lines[index], 0)
        if key in blocks:
            raise ClusterInfoError("kubeconfig has a duplicate top-level key")
        index += 1
        nested: list[str] = []
        while index < len(lines) and lines[index].startswith((" ", "- ")):
            nested.append(lines[index])
            index += 1
        blocks[key] = (scalar, nested)
    allowed = {"apiVersion", "kind", "clusters", "contexts", "users",
               "current-context", "preferences"}
    if set(blocks) - allowed or not {"apiVersion", "kind", "clusters"} <= blocks.keys():
        raise ClusterInfoError("kubeconfig top-level fields are not exact")
    if blocks["apiVersion"] != ("v1", []) or blocks["kind"] != ("Config", []):
        raise ClusterInfoError("kubeconfig type is not v1 Config")
    scalar, cluster_lines = blocks["clusters"]
    if scalar:
        raise ClusterInfoError("clusters is not a nested sequence")
    cluster = _parse_cluster(cluster_lines)
    for key in ("contexts", "users"):
        if key in blocks and (blocks[key][1] or not _empty(blocks[key][0], sequence=True)):
            raise ClusterInfoError(f"{key} is not semantically empty")
    if "current-context" in blocks and blocks["current-context"] not in (('""', []), ("''", [])):
        raise ClusterInfoError("current-context is not absent or empty")
    if "preferences" in blocks and (blocks["preferences"][1]
                                    or not _empty(blocks["preferences"][0])):
        raise ClusterInfoError("preferences is not absent or empty")
    if cluster["server"] != server:
        raise ClusterInfoError("kubeconfig server does not match internal evidence")
    _verify_ca(cluster["certificate-authority-data"], ca_digest)
    return text
def _verify_ca(encoded: str, expected_digest: str) -> None:
    if (not encoded or len(encoded) % 4 or _B64.fullmatch(encoded) is None):
        raise ClusterInfoError("certificate-authority-data is not canonical base64")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ClusterInfoError("certificate-authority-data is invalid") from error
    if base64.b64encode(raw).decode("ascii") != encoded:
        raise ClusterInfoError("certificate-authority-data is not canonical base64")
    if (raw.count(b"-----BEGIN CERTIFICATE-----") != 1
            or raw.count(b"-----END CERTIFICATE-----") != 1
            or _PEM.fullmatch(raw) is None):
        raise ClusterInfoError("certificate-authority-data is not exactly one PEM certificate")
    certificates = x509.load_pem_x509_certificates(raw.strip(b" \t\r\n\f\v"))
    if len(certificates) != 1:
        raise ClusterInfoError("certificate-authority-data is not one certificate")
    certificate = certificates[0]
    constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints).value
    if constraints.ca is not True:
        raise ClusterInfoError("cluster certificate is not a CA")
    der = certificate.public_bytes(serialization.Encoding.DER)
    if not hmac.compare_digest(sha256(der).hexdigest(), expected_digest):
        raise ClusterInfoError("cluster certificate does not match private evidence")
def _decode_segment(label: str, segment: str) -> bytes:
    if _B64URL.fullmatch(segment) is None:
        raise ClusterInfoError(f"JWS {label} is not unpadded base64url")
    try:
        raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (ValueError, binascii.Error) as error:
        raise ClusterInfoError(f"JWS {label} is invalid") from error
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != segment:
        raise ClusterInfoError(f"JWS {label} is not canonical base64url")
    return raw
def _verify_jws(value: object, config: str, token_id: str, secret: bytes) -> str:
    text = _string("detached JWS", value, maximum=_MAX_JWS_BYTES)
    try:
        text.encode("ascii")
    except UnicodeEncodeError as error:
        raise ClusterInfoError("detached JWS is not ASCII") from error
    parts = text.split(".")
    if len(parts) != 3 or not parts[0] or parts[1] or not parts[2]:
        raise ClusterInfoError("detached JWS compact serialization is invalid")
    header_raw = _decode_segment("protected header", parts[0]); signature = _decode_segment("signature", parts[2])
    if len(header_raw) > 4096 or len(signature) != sha256().digest_size:
        raise ClusterInfoError("detached JWS component is unbounded or malformed")
    def pairs(rows: list[tuple[str, object]]) -> dict:
        result = {}
        for key, item in rows:
            if key in result:
                raise ClusterInfoError("protected header has a duplicate key")
            result[key] = item
        return result
    try:
        header = json.loads(header_raw.decode("utf-8"), object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                ClusterInfoError("protected header constant is invalid")))
    except ClusterInfoError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ClusterInfoError("protected header is not strict UTF-8 JSON") from error
    if type(header) is not dict or header != {"alg": "HS256", "kid": token_id}:
        raise ClusterInfoError("protected header is not the exact HS256 token binding")
    content = base64.urlsafe_b64encode(config.encode("utf-8")).rstrip(b"=").decode("ascii")
    message = f"{parts[0]}.{content}".encode("ascii"); expected = hmac.new(secret, message, sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise ClusterInfoError("detached JWS signature is invalid")
    return sha256(text.encode("ascii")).hexdigest()
@dataclass(frozen=True, slots=True)
class ClusterInfoProof:
    api_version: str; kind: str; namespace: str; name: str
    uid: str; resource_version: str; internal_server: str
    cluster_ca_certificate_der_sha256: str; token_id: str
    token_expiration: str; captured_at: str; kubeconfig_sha256: str
    signature_present: bool; jws_sha256_or_none: str | None
    runtime_contract_complete: bool = False
    def __post_init__(self) -> None:
        try:
            if (type(self.api_version) is not str or self.api_version != "v1"
                    or type(self.kind) is not str or self.kind != "ConfigMap"
                    or type(self.namespace) is not str or self.namespace != "kube-public"
                    or type(self.name) is not str or self.name != "cluster-info"):
                raise ClusterInfoError("proof ConfigMap identity is not exact")
            _uid(self.uid); _rv(self.resource_version); _server(self.internal_server)
            _digest("cluster CA", self.cluster_ca_certificate_der_sha256)
            if type(self.token_id) is not str or _TOKEN_ID.fullmatch(self.token_id) is None:
                raise ClusterInfoError("proof token ID is invalid")
            _, expiration = _time("token expiration", self.token_expiration)
            _, captured = _time("captured at", self.captured_at); _digest("kubeconfig", self.kubeconfig_sha256)
            if type(self.signature_present) is not bool:
                raise ClusterInfoError("signature presence is not an exact boolean")
            if self.signature_present:
                _digest("JWS", self.jws_sha256_or_none)
                if not captured < expiration:
                    raise ClusterInfoError("signature proof is not from the active lifetime")
            elif self.jws_sha256_or_none is not None or captured < expiration:
                raise ClusterInfoError("signature absence is inconsistent with token lifetime")
            if self.runtime_contract_complete is not False:
                raise ClusterInfoError("cluster-info proof cannot complete the runtime contract")
        except ClusterInfoError:
            raise
        except (AttributeError, TypeError, ValueError, OverflowError) as error:
            raise ClusterInfoError("cluster-info proof is partially initialized or malformed") from error
def _prior(value: object) -> ClusterInfoProof | None:
    if value is None:
        return None
    if type(value) is not ClusterInfoProof:
        raise ClusterInfoError("prior proof type is not exact")
    value.__post_init__()
    return value
def validate_cluster_info(
    document: dict, *, internal_server: str,
    cluster_ca_certificate_der_sha256: str, token_id: str, token_secret: bytes,
    token_expiration: str, captured_at: str, prior: ClusterInfoProof | None = None,
    prior_document: dict | None = None,
) -> ClusterInfoProof:
    """Validate one decoded cluster-info ConfigMap and private token evidence."""
    try:
        if type(document) is not dict:
            raise ClusterInfoError("document must be one exact built-in dict")
        _validate_tree(document)
        previous = _prior(prior); server = _server(internal_server)
        ca_digest = _digest("cluster CA", cluster_ca_certificate_der_sha256)
        token, secret = _token(token_id, token_secret)
        expiration_text, expiration = _time("token expiration", token_expiration)
        captured_text, captured = _time("captured at", captured_at)
        if set(document) != {"apiVersion", "kind", "metadata", "data"}:
            raise ClusterInfoError("ConfigMap root keys are not exact")
        if (_string("apiVersion", document.get("apiVersion")) != "v1"
                or _string("kind", document.get("kind")) != "ConfigMap"):
            raise ClusterInfoError("document is not a v1 ConfigMap")
        metadata = document.get("metadata")
        if type(metadata) is not dict or set(metadata) != _METADATA_KEYS:
            raise ClusterInfoError("ConfigMap metadata keys are not exact")
        if (_string("metadata name", metadata.get("name")) != "cluster-info"
                or _string("metadata namespace", metadata.get("namespace")) != "kube-public"):
            raise ClusterInfoError("ConfigMap identity is not kube-public/cluster-info")
        uid = _uid(metadata.get("uid")); resource_version = _rv(metadata.get("resourceVersion"))
        try:
            configuration(document)
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            raise ClusterInfoError("ConfigMap runtime metadata is invalid") from error
        data = document.get("data")
        if type(data) is not dict:
            raise ClusterInfoError("ConfigMap data is not an exact object")
        config = _parse_kubeconfig(data.get("kubeconfig"), server, ca_digest)
        config_digest = sha256(config.encode("utf-8")).hexdigest(); active = captured < expiration
        signature_key = f"jws-kubeconfig-{token}"
        if active:
            if set(data) != {"kubeconfig", signature_key}:
                raise ClusterInfoError("active cluster-info data keys are not exact")
            jws_digest = _verify_jws(data.get(signature_key), config, token, secret)
        else:
            if set(data) != {"kubeconfig"}:
                raise ClusterInfoError("expired cluster-info retained a signature or extra data")
            jws_digest = None
        if previous is not None:
            bindings = ((previous.uid, uid), (previous.internal_server, server),
                        (previous.cluster_ca_certificate_der_sha256, ca_digest),
                        (previous.token_id, token), (previous.token_expiration, expiration_text),
                        (previous.kubeconfig_sha256, config_digest))
            if any(left != right for left, right in bindings):
                raise ClusterInfoError("cluster-info continuity binding drifted")
            _, previous_captured = _time("prior captured at", previous.captured_at)
            if int(resource_version) < int(previous.resource_version) or captured < previous_captured:
                raise ClusterInfoError("cluster-info resourceVersion or time regressed")
            if (resource_version == previous.resource_version
                    and (not active or not previous.signature_present
                         or jws_digest != previous.jws_sha256_or_none)):
                raise ClusterInfoError("equal resourceVersion changed signature evidence")
        if not active:
            if (previous is None or not previous.signature_present
                    or type(prior_document) is not dict
                    or not _time("prior captured at", previous.captured_at)[1] < expiration
                    or int(resource_version) <= int(previous.resource_version)):
                raise ClusterInfoError("signature removal lacks a qualifying active prior proof")
            rederived = validate_cluster_info(
                prior_document, internal_server=server,
                cluster_ca_certificate_der_sha256=ca_digest, token_id=token,
                token_secret=secret, token_expiration=expiration_text,
                captured_at=previous.captured_at,
            )
            if rederived != previous:
                raise ClusterInfoError("prior raw evidence does not derive the supplied proof")
        return ClusterInfoProof(
            "v1", "ConfigMap", "kube-public", "cluster-info", uid, resource_version,
            server, ca_digest, token, expiration_text, captured_text, config_digest,
            active, jws_digest, False,
        )
    except ClusterInfoError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError,
            OverflowError, RecursionError, x509.ExtensionNotFound,
            x509.DuplicateExtension) as error:
        raise ClusterInfoError("cluster-info validation failed") from error
__all__ = ("ClusterInfoError", "ClusterInfoProof", "validate_cluster_info")
