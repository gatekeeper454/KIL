"""Bounded capture, semantic joins, and offline V3B-2a evidence verification."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable, Mapping, Protocol, Sequence

from kil.v3b2_contracts import (
    PRIVATE_MANIFEST_FIELDS,
    PRIVATE_MANIFEST_SCHEMA,
    PUBLIC_MANIFEST_FIELDS,
    PUBLIC_MANIFEST_SCHEMA,
    TRACKS,
    SchemaError,
    dispatch_schema,
    require_closed_object,
    V3B2Profile,
)
from kil.v3b2_inventory import (
    EndpointIdentity,
    ObjectIdentity,
    PodImageIdentity,
    PolicyEdge,
)
from kil.v3b2_manifests import (
    WorkloadIdentity,
    expected_object_keys,
    expected_policy_graph,
    render_kind_config,
    render_objects,
)


RESULT_CLASS = "intermediate_provisional_kind_calico_nominal"
REQUEST_FREE_RESULT_CLASS = "diagnostic_request_free_kind_calico_readiness"
PROMOTION_STATUS = "not_promoted"
CLAIM_EXCLUSIONS = (
    "complete_v3b2_validation",
    "complete_networkpolicy_validation",
    "repeated_reliability",
    "performance",
    "production_validation",
    "historical_prevention",
)

PUBLIC_FILES = frozenset(
    {
        "manifest.json",
        "requests.jsonl",
        "decisions.jsonl",
        "envoy.jsonl",
        "targets.jsonl",
        "kubernetes.jsonl",
        "policies.jsonl",
        "joins.jsonl",
        "summary.md",
        "live.html",
        "SHA256SUMS",
    }
)
_DATA_FILES = PUBLIC_FILES - {"manifest.json", "SHA256SUMS"}
_MAX_SOURCE_BYTES = 8 * 1024 * 1024
_MAX_FILE_BYTES = 8 * 1024 * 1024
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX40 = re.compile(r"[0-9a-f]{40}")
_SAFE_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_V3B2_RUN = re.compile(r"v3b2-[0-9a-f]{64}")
_PROFILE_PATH = Path(__file__).resolve().parents[2] / "deploy/kind/v3b2-profile.json"
_PROFILE_SHA256 = "cc630f343f87f89180a2cfc98baf1d23686e0b39e364569ff579b3e8efa8cee8"
_TOPOLOGY_FIELDS = frozenset({"cluster_incarnation_uid", "node_container_id", "namespaces", "objects", "pod_images", "endpoints", "calico_readiness"})
_CONTENT_FIELDS = frozenset({"run_id", "profile_sha256", "kind_config_sha256", "objects_manifest_sha256", "calico_manifest_sha256", "kind_node_image", "calico_images", "kil_image_id", "envoy_image_digest"})
_EXPECTED_TOPOLOGY_FIELDS = frozenset(
    {"namespaces", "object_keys", "pod_image_keys", "endpoint_keys", "calico_readiness"}
)
_PRIVATE_KEYS = (
    "execution_nonce",
    "projection_key",
    "credential",
    "signed_state",
    "private_journal",
    "foreign_profile_name",
    "original_name",
    "password",
    "secret",
    "access_token",
    "refresh_token",
    "host_path",
)
_PRIVATE_TEXT = (
    "/users/",
    "bearer ",
    "kil-private",
    "execution_nonce",
    "signed_state",
    "private_journal",
    "foreign-profile-name",
)


class EvidenceError(ValueError):
    """Raised when evidence is incomplete, ambiguous, or unsafe."""


class PublicBoundaryError(EvidenceError):
    """Raised when a public projection contains private material."""


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    logical_name: str
    object_uid: str
    resource_version: str
    container_id: str
    byte_count: int
    sha256: str

    def __post_init__(self) -> None:
        for label, value in (
            ("logical name", self.logical_name),
            ("object UID", self.object_uid),
            ("resource version", self.resource_version),
            ("container ID", self.container_id),
        ):
            try:
                invalid = type(value) is not str or not value or len(value.encode("utf-8")) > 4096
            except UnicodeEncodeError:
                raise EvidenceError(f"source {label} contains invalid Unicode") from None
            if invalid:
                raise EvidenceError(f"source {label} must be an exact bounded string")
        if type(self.byte_count) is not int or self.byte_count < 0 or self.byte_count > _MAX_SOURCE_BYTES:
            raise EvidenceError("source byte count is outside the closed bound")
        if type(self.sha256) is not str or _HEX64.fullmatch(self.sha256) is None:
            raise EvidenceError("source SHA-256 is invalid")


@dataclass(frozen=True, slots=True)
class CapturedSource:
    identity: SourceIdentity
    payload: bytes

    def __post_init__(self) -> None:
        if type(self.identity) is not SourceIdentity or type(self.payload) is not bytes:
            raise EvidenceError("captured source types are not exact")
        if (
            len(self.payload) != self.identity.byte_count
            or sha256(self.payload).hexdigest() != self.identity.sha256
        ):
            raise EvidenceError("captured source bytes do not match their identity")


@dataclass(frozen=True, slots=True)
class VerifiedBundle:
    schema_family: str
    run_id: str
    result_class: str
    promotion_status: str
    public_commitment: str

    def __post_init__(self) -> None:
        if type(self.schema_family) is not str or self.schema_family not in {"v3b1", "v3b2-run"}:
            raise EvidenceError("verified schema family is invalid")
        for value in (self.run_id, self.result_class, self.promotion_status):
            try:
                invalid = type(value) is not str or not value or len(value.encode("utf-8")) > 4096
            except UnicodeEncodeError:
                raise EvidenceError("verified bundle contains invalid Unicode") from None
            if invalid:
                raise EvidenceError("verified bundle contains an invalid bounded string")
        if type(self.public_commitment) is not str or _HEX64.fullmatch(self.public_commitment) is None:
            raise EvidenceError("verified public commitment is invalid")


class SourceReader(Protocol):
    def identity(self) -> SourceIdentity: ...
    def read(self, maximum: int) -> bytes: ...


def _canonical_bytes(value: object) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise EvidenceError("evidence is not canonical JSON") from error


def capture_source(
    reader: SourceReader,
    expected: SourceIdentity,
    maximum: int = _MAX_SOURCE_BYTES,
    *,
    private_diagnostic_path: Path | None = None,
) -> CapturedSource:
    """Read one source between two exact identity observations."""
    if type(expected) is not SourceIdentity:
        raise EvidenceError("expected source identity type is invalid")
    if type(maximum) is not int or maximum < 0 or maximum > _MAX_SOURCE_BYTES:
        raise EvidenceError("source read maximum is invalid")
    try:
        before = reader.identity()
        payload = reader.read(maximum)
        after = reader.identity()
    except Exception:
        raise EvidenceError("source capture failed closed") from None
    if type(before) is not SourceIdentity or type(after) is not SourceIdentity or type(payload) is not bytes:
        raise EvidenceError("source reader returned an invalid exact type")
    if before != expected or after != expected:
        raise EvidenceError("source identity drifted during capture")
    if len(payload) > maximum or len(payload) != expected.byte_count or sha256(payload).hexdigest() != expected.sha256:
        raise EvidenceError("source bytes do not match the bound identity")
    captured = CapturedSource(expected, payload)
    try:
        records = _parse_jsonl(payload, expected.logical_name)
        encoded = [_canonical_bytes(record) for record in records]
        if len(encoded) != len(set(encoded)):
            raise EvidenceError("source JSONL contains a duplicate record")
    except EvidenceError:
        if private_diagnostic_path is not None:
            _persist_private_diagnostic(private_diagnostic_path, payload)
        raise
    return captured


def _persist_private_diagnostic(path: Path, payload: bytes) -> None:
    """Atomically publish one private raw/hash diagnostic directory."""
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise EvidenceError("private diagnostic path must be absolute and normalized")
    parent, parent_fd, parent_identity = _prepare_private_diagnostic_parent(path)
    staging_fd = -1
    staging_name = ""
    renamed = False
    try:
        if _entry_exists(parent_fd, path.name):
            raise EvidenceError("private diagnostic destination is unsafe")
        diagnostic_payload = _canonical_bytes(
            {
                "category": "malformed_source_bytes",
                "byte_count": len(payload),
                "sha256": sha256(payload).hexdigest(),
            }
        )
        token = sha256(os.urandom(32)).hexdigest()
        staging_name = f".{path.name}.{token}.tmp"
        os.mkdir(staging_name, 0o700, dir_fd=parent_fd)
        staging_fd = _open_child_directory(parent_fd, staging_name, "private diagnostic staging")
        _write_regular_at(staging_fd, "raw.bin", payload)
        _write_regular_at(staging_fd, "diagnostic.json", diagnostic_payload)
        os.fsync(staging_fd)
        _assert_anchor_path(parent, parent_identity, "private diagnostic parent")
        _rename_directory_exclusive(parent_fd, staging_name, parent_fd, path.name)
        renamed = True
        persisted = _read_tree_fd(
            staging_fd,
            {"raw.bin", "diagnostic.json"},
        )
        if persisted != {
            "raw.bin": payload,
            "diagnostic.json": diagnostic_payload,
        }:
            raise EvidenceError("private diagnostic unit content changed")
        os.fsync(staging_fd)
        published = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        staged = os.fstat(staging_fd)
        if _directory_identity(published) != _directory_identity(staged):
            raise EvidenceError("private diagnostic unit changed during publication")
        os.fsync(parent_fd)
        if _directory_identity(
            os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        ) != _directory_identity(staged):
            raise EvidenceError("private diagnostic unit was replaced after publication")
        _assert_anchor_path(parent, parent_identity, "private diagnostic parent")
        _assert_anchor_path(
            path,
            _directory_identity(staged),
            "private diagnostic unit",
        )
    except EvidenceError:
        raise
    except (OSError, TypeError, ValueError, UnicodeError):
        raise EvidenceError("private diagnostic persistence failed closed") from None
    finally:
        if staging_fd >= 0:
            if not renamed:
                _cleanup_staging_directory(parent_fd, staging_fd, staging_name)
            os.close(staging_fd)
        os.close(parent_fd)


def _closed_record(label: str, value: object, fields: frozenset[str]) -> dict[str, object]:
    try:
        return require_closed_object(label, value, fields)
    except SchemaError:
        raise EvidenceError(f"{label} fields are not closed") from None


_CASE_FIELDS = frozenset({"track", "request_id", "expected_decision", "expected_http_status", "expected_target_markers"})
_DRIVER_FIELDS = frozenset({"track", "request_id", "attempt", "decision", "http_status", "decision_digest"})
_DECISION_FIELDS = frozenset({"track", "request_id", "decision", "decision_digest"})
_ENVOY_FIELDS = frozenset({"track", "request_id", "decision_digest", "upstream_attempted", "upstream_status"})
_TARGET_FIELDS = frozenset({"track", "request_id", "marker"})
_ATTESTATION_FIELDS = frozenset({"kind", "track", "records"})


def _private_manifest(private: object) -> dict[str, object]:
    value = _closed_record("V3B-2 private manifest", private, PRIVATE_MANIFEST_FIELDS)
    if value.get("schema_version") != PRIVATE_MANIFEST_SCHEMA:
        raise EvidenceError("private manifest schema is invalid")
    for name in ("run_id", "execution_nonce", "source_commit", "profile_sha256", "global_context_before"):
        if type(value.get(name)) is not str or not value[name]:
            raise EvidenceError(f"private manifest {name} is invalid")
    if _SAFE_RUN.fullmatch(str(value["run_id"])) is None:
        raise EvidenceError("private manifest run ID is unsafe")
    if (
        _HEX64.fullmatch(str(value["execution_nonce"])) is None
        or _HEX40.fullmatch(str(value["source_commit"])) is None
        or _HEX64.fullmatch(str(value["profile_sha256"])) is None
    ):
        raise EvidenceError("private manifest digest identity is invalid")
    if type(value["request_cases"]) is not list or type(value["source_attestations"]) is not list:
        raise EvidenceError("private manifest evidence arrays are invalid")
    for name in ("content_identities", "expected_topology", "expected_policy_graph", "runtime_identities"):
        if type(value[name]) is not dict:
            raise EvidenceError(f"private manifest {name} must be an exact object")
    return value


def _records(private: Mapping[str, object]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {name: [] for name in ("driver", "decision", "envoy", "target")}
    seen_attestations: set[tuple[str, str]] = set()
    attestations = private["source_attestations"]
    assert type(attestations) is list
    for raw in attestations:
        item = _closed_record("source attestation", raw, _ATTESTATION_FIELDS)
        kind, track, values = item["kind"], item["track"], item["records"]
        if type(kind) is not str or kind not in grouped or type(track) is not str or track not in TRACKS or type(values) is not list:
            raise EvidenceError("source attestation identity is invalid")
        if (kind, track) in seen_attestations:
            raise EvidenceError("source attestation is duplicated")
        seen_attestations.add((kind, track))
        for raw_record in values:
            record = _closed_record(f"{kind} record", raw_record, {"driver": _DRIVER_FIELDS, "decision": _DECISION_FIELDS, "envoy": _ENVOY_FIELDS, "target": _TARGET_FIELDS}[kind])
            if record.get("track") != track:
                raise EvidenceError("cross-track evidence is prohibited")
            grouped[kind].append(record)
    return grouped


def join_nominal_evidence(private: object) -> list[dict[str, object]]:
    """Independently rederive the fixed three-track semantic joins."""
    manifest = _private_manifest(private)
    cases = manifest["request_cases"]
    assert type(cases) is list
    if len(cases) != 3:
        raise EvidenceError("nominal evidence requires exactly three cases")
    grouped = _records(manifest)
    expected_tuple = (("permit", 200, 1), ("permit", 200, 1), ("deny", 403, 0))
    joins: list[dict[str, object]] = []
    for index, track in enumerate(TRACKS):
        case = _closed_record("request case", cases[index], _CASE_FIELDS)
        expected_decision, expected_status, expected_markers = expected_tuple[index]
        if (
            type(case.get("track")) is not str
            or type(case.get("request_id")) is not str
            or type(case.get("expected_decision")) is not str
            or type(case.get("expected_http_status")) is not int
            or type(case.get("expected_target_markers")) is not int
        ):
            raise EvidenceError("request case scalar types are invalid")
        if case != {
            "track": track,
            "request_id": "v3b1-central-request",
            "expected_decision": expected_decision,
            "expected_http_status": expected_status,
            "expected_target_markers": expected_markers,
        }:
            raise EvidenceError("request cases differ from the closed nominal contract")
        selected: dict[str, list[dict[str, object]]] = {
            kind: [record for record in records if record.get("track") == track]
            for kind, records in grouped.items()
        }
        if len(selected["driver"]) != 1 or len(selected["decision"]) != 1 or len(selected["envoy"]) != 1 or len(selected["target"]) != expected_markers:
            raise EvidenceError("semantic source cardinality is invalid")
        driver, decision, envoy = selected["driver"][0], selected["decision"][0], selected["envoy"][0]
        if (
            any(type(driver.get(name)) is not str for name in ("track", "request_id", "decision", "decision_digest"))
            or type(driver.get("attempt")) is not int
            or type(driver.get("http_status")) is not int
            or any(type(decision.get(name)) is not str for name in ("track", "request_id", "decision", "decision_digest"))
            or any(type(envoy.get(name)) is not str for name in ("track", "request_id", "decision_digest"))
            or type(envoy.get("upstream_attempted")) is not bool
            or (envoy.get("upstream_status") is not None and type(envoy.get("upstream_status")) is not int)
            or any(
                type(target.get("track")) is not str
                or type(target.get("request_id")) is not str
                or type(target.get("marker")) is not int
                for target in selected["target"]
            )
        ):
            raise EvidenceError("semantic source scalar types are invalid")
        identity = (track, "v3b1-central-request")
        if any((record.get("track"), record.get("request_id")) != identity for record in (driver, decision, envoy, *selected["target"])):
            raise EvidenceError("semantic join identity is invalid")
        digests = (driver.get("decision_digest"), decision.get("decision_digest"), envoy.get("decision_digest"))
        if any(type(item) is not str or _HEX64.fullmatch(item) is None for item in digests) or len(set(digests)) != 1:
            raise EvidenceError("decision digests do not join exactly")
        attempted = envoy.get("upstream_attempted")
        upstream_status = envoy.get("upstream_status")
        if (
            type(driver.get("attempt")) is not int
            or driver["attempt"] != 1
            or driver.get("decision") != expected_decision
            or decision.get("decision") != expected_decision
            or type(driver.get("http_status")) is not int
            or driver["http_status"] != expected_status
            or type(attempted) is not bool
            or attempted is not (expected_decision == "permit")
            or (upstream_status != expected_status if expected_decision == "permit" else upstream_status is not None)
            or any(type(target.get("marker")) is not int or target.get("marker") != 1 for target in selected["target"])
        ):
            raise EvidenceError("nominal semantic outcome is invalid")
        joins.append(
            {
                "track": track,
                "request_id": "v3b1-central-request",
                "decision": expected_decision,
                "http_status": expected_status,
                "target_markers": expected_markers,
                "decision_digest_equal": True,
                "decision_digest": digests[0],
                "envoy_upstream_attempted": attempted,
            }
        )
    if any(len([r for r in records if r.get("track") not in TRACKS]) for records in grouped.values()):
        raise EvidenceError("unreviewed cross-track evidence exists")
    return joins


_FOREIGN_FIELDS = frozenset({"name", "status", "arch", "cpus", "memory", "disk", "runtime"})


def _foreign_records(value: object) -> list[dict[str, object]]:
    if type(value) is not list:
        raise EvidenceError("foreign profile inventory must be an exact array")
    normalized: list[dict[str, object]] = []
    names: set[str] = set()
    for raw in value:
        record = _closed_record("foreign profile", raw, _FOREIGN_FIELDS)
        name = record["name"]
        if type(name) is not str or not name or name == "kil-v3-lab" or name in names:
            raise EvidenceError("foreign profile identity is ambiguous")
        try:
            if len(name.encode("utf-8")) > 4096:
                raise EvidenceError("foreign profile identity exceeds its bound")
        except UnicodeEncodeError:
            raise EvidenceError("foreign profile identity contains invalid Unicode") from None
        if type(record["status"]) is not str or record["status"] not in {"Running", "Stopped"}:
            raise EvidenceError("foreign profile status is invalid")
        if any(type(record[field]) is not int or record[field] < 0 for field in ("cpus", "memory", "disk")):
            raise EvidenceError("foreign profile resource is invalid")
        for field in ("arch", "runtime"):
            text = record[field]
            try:
                invalid_text = (
                    type(text) is not str
                    or not text
                    or len(text.encode("utf-8")) > 4096
                )
            except UnicodeEncodeError:
                raise EvidenceError(
                    "foreign profile resource text contains invalid Unicode"
                ) from None
            if invalid_text:
                raise EvidenceError("foreign profile resource text is invalid")
        names.add(name)
        normalized.append(dict(record))
    return sorted(normalized, key=lambda item: str(item["name"]))


def project_foreign_profiles(before: object, after: object, key: bytes) -> dict[str, object]:
    if type(key) is not bytes or not key:
        raise EvidenceError("foreign projection key is invalid")
    left, right = _foreign_records(before), _foreign_records(after)
    def project(records: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
        result = []
        for record in records:
            name = str(record["name"])
            result.append({
                "pseudonym": hmac.new(key, name.encode("utf-8"), "sha256").hexdigest(),
                "status": record["status"], "arch": record["arch"], "cpus": record["cpus"],
                "memory": record["memory"], "disk": record["disk"], "runtime": record["runtime"],
            })
        return sorted(result, key=lambda item: str(item["pseudonym"]))
    projected_before, projected_after = project(left), project(right)
    return {"before": projected_before, "after": projected_after, "unchanged": projected_before == projected_after}


def _public_commitment(manifest: Mapping[str, object], artifacts: Mapping[str, bytes]) -> str:
    projected = dict(manifest)
    projected["public_commitment_sha256"] = ""
    value = {
        "schema_version": "kil.v3b2-public-commitment.v1",
        "manifest": projected,
        "file_sha256": {name: sha256(artifacts[name]).hexdigest() for name in sorted(artifacts)},
    }
    return sha256(_canonical_bytes(value)).hexdigest()


def _trusted_profile() -> V3B2Profile:
    try:
        payload = _PROFILE_PATH.read_bytes()
        if sha256(payload).hexdigest() != _PROFILE_SHA256:
            raise EvidenceError("approved V3B-2 profile identity is unavailable")
        return V3B2Profile.load(_PROFILE_PATH)
    except EvidenceError:
        raise
    except (OSError, ValueError, TypeError, UnicodeError):
        raise EvidenceError("approved V3B-2 profile identity is unavailable") from None


def _validate_content_identities(
    value: object, *, run_id: object, profile_sha256: object
) -> dict[str, object]:
    content = _closed_record("content identities", value, _CONTENT_FIELDS)
    profile = _trusted_profile()
    for name in _CONTENT_FIELDS:
        if name != "calico_images" and type(content[name]) is not str:
            raise EvidenceError("content identity scalar types are invalid")
    if (
        type(run_id) is not str
        or _V3B2_RUN.fullmatch(run_id) is None
        or content["run_id"] != run_id
        or profile_sha256 != _PROFILE_SHA256
        or content["profile_sha256"] != profile_sha256
        or content["kind_config_sha256"] != sha256(render_kind_config(profile)).hexdigest()
        or content["calico_manifest_sha256"] != profile.calico_manifest_sha256
        or content["kind_node_image"] != profile.kind_node_image
    ):
        raise EvidenceError("content identities do not bind the approved profile and run")
    expected_calico = {name: image for name, image in profile.calico_images}
    if type(content["calico_images"]) is not dict or content["calico_images"] != expected_calico:
        raise EvidenceError("content identities do not bind the approved Calico images")
    try:
        workload = WorkloadIdentity(
            content["run_id"],
            content["kil_image_id"],
            content["envoy_image_digest"],
        )
    except (TypeError, ValueError):
        raise EvidenceError("content workload identities are invalid") from None
    if content["objects_manifest_sha256"] != sha256(render_objects(profile, workload)).hexdigest():
        raise EvidenceError("application manifest identity does not bind the approved run")
    return content


def _validate_topology_attestation(
    value: object, content: Mapping[str, object]
) -> dict[str, object]:
    topology = _closed_record("topology attestation", value, _TOPOLOGY_FIELDS)
    if (
        type(topology["cluster_incarnation_uid"]) is not str
        or not topology["cluster_incarnation_uid"]
        or type(topology["node_container_id"]) is not str
        or _HEX64.fullmatch(topology["node_container_id"]) is None
    ):
        raise EvidenceError("cluster incarnation or node identity is invalid")
    profile = _trusted_profile()
    expected_namespaces = (
        "default",
        "kil-v3-baseline",
        "kil-v3-local-reduce",
        "kil-v3-signed",
        "kube-node-lease",
        "kube-public",
        "kube-system",
        "local-path-storage",
    )
    if type(topology["namespaces"]) is not list or tuple(topology["namespaces"]) != expected_namespaces or any(type(item) is not str for item in topology["namespaces"]):
        raise EvidenceError("topology namespace inventory is not exact")
    if type(topology["objects"]) is not list or len(topology["objects"]) != 63:
        raise EvidenceError("topology object inventory cardinality is invalid")
    objects: list[ObjectIdentity] = []
    for raw in topology["objects"]:
        record = _closed_record("topology object", raw, frozenset({"api_version", "kind", "namespace", "name", "uid", "resource_version"}))
        try:
            objects.append(ObjectIdentity(**record))
        except (TypeError, ValueError):
            raise EvidenceError("topology object identity is invalid") from None
    expected_keys = tuple(sorted((*expected_object_keys(profile), ("v1", "Namespace", "", "kube-system"), ("apps/v1", "DaemonSet", "kube-system", "calico-node"), ("apps/v1", "Deployment", "kube-system", "calico-kube-controllers"))))
    keys = tuple((item.api_version, item.kind, item.namespace, item.name) for item in objects)
    if tuple(sorted(objects)) != tuple(objects) or len(set(objects)) != len(objects) or keys != expected_keys:
        raise EvidenceError("topology object keys or ordering differ from the fixed inventory")
    system_namespace = next(item for item in objects if (item.api_version, item.kind, item.namespace, item.name) == ("v1", "Namespace", "", "kube-system"))
    if system_namespace.uid != topology["cluster_incarnation_uid"]:
        raise EvidenceError("cluster incarnation UID is not bound to kube-system")
    _validate_pod_images(topology["pod_images"], content, profile, objects)
    _validate_endpoints(topology["endpoints"])
    readiness = _closed_record("Calico readiness", topology["calico_readiness"], frozenset({"node_desired", "node_ready", "controller_desired", "controller_ready"}))
    if any(type(readiness[name]) is not int or readiness[name] != 1 for name in readiness):
        raise EvidenceError("Calico readiness inventory is not exactly one ready node and controller")
    return topology


def _validate_pod_images(
    value: object,
    content: Mapping[str, object],
    profile: V3B2Profile,
    objects: Sequence[ObjectIdentity],
) -> None:
    if type(value) is not list or len(value) != 17:
        raise EvidenceError("Pod image inventory cardinality is invalid")
    records: list[PodImageIdentity] = []
    fields = frozenset({"image_role", "container_type", "namespace", "pod", "container", "uid", "resource_version", "image", "image_id", "ready"})
    for raw in value:
        item = _closed_record("Pod image identity", raw, fields)
        try:
            records.append(PodImageIdentity(**item))
        except (TypeError, ValueError):
            raise EvidenceError("Pod image identity is invalid") from None
    if tuple(sorted(records)) != tuple(records) or len(set(records)) != len(records) or any(item.ready is not True for item in records):
        raise EvidenceError("Pod image identities are not unique, sorted, and ready")
    calico_pins = {"calico-cni": dict(profile.calico_images)["cni"], "calico-node": dict(profile.calico_images)["node"], "calico-kube-controllers": dict(profile.calico_images)["kube_controllers"]}
    expected_calico = {("calico-cni", "init", "install-cni"), ("calico-cni", "init", "upgrade-ipam"), ("calico-node", "init", "ebpf-bootstrap"), ("calico-node", "regular", "calico-node"), ("calico-kube-controllers", "regular", "calico-kube-controllers")}
    calico = [item for item in records if item.image_role != "workload"]
    if {(item.image_role, item.container_type, item.container) for item in calico} != expected_calico or any(item.namespace != "kube-system" or item.image != calico_pins[item.image_role] for item in calico):
        raise EvidenceError("Calico Pod image identities differ from approved pins")
    if any(
        not item.pod.startswith(
            "calico-kube-controllers-"
            if item.image_role == "calico-kube-controllers"
            else "calico-node-"
        )
        for item in calico
    ):
        raise EvidenceError("Calico Pod names differ from the fixed workload families")
    workload = [item for item in records if item.image_role == "workload"]
    expected_workloads = {(namespace, role) for namespace in ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed") for role in ("driver", "envoy", "authz", "target")}
    if {(item.namespace, item.container) for item in workload} != expected_workloads:
        raise EvidenceError("workload Pod image placements are not exact")
    kil_digest = str(content["kil_image_id"]).removeprefix("sha256:")
    expected_kil = "kil.local/kil-v3b2:sha256-" + kil_digest
    if any(item.image != (content["envoy_image_digest"] if item.container == "envoy" else expected_kil) for item in workload):
        raise EvidenceError("workload Pod image identities differ from content identities")
    for item in workload:
        valid_pod = (
            item.pod == "driver"
            if item.container == "driver"
            else re.fullmatch(
                rf"{re.escape(item.container)}-"
                r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?",
                item.pod,
            )
            is not None
        )
        if not valid_pod:
            raise EvidenceError("workload Pod name is outside the fixed inventory")
        if item.container == "driver":
            bound = next(
                record
                for record in objects
                if record.kind == "Pod"
                and record.namespace == item.namespace
                and record.name == "driver"
            )
            if (item.uid, item.resource_version) != (bound.uid, bound.resource_version):
                raise EvidenceError("driver Pod image identity is detached from its object UID")


def _validate_endpoints(value: object) -> None:
    if type(value) is not list or len(value) != 9:
        raise EvidenceError("endpoint inventory cardinality is invalid")
    records: list[EndpointIdentity] = []
    fields = frozenset({"source_kind", "source_name", "namespace", "service", "addresses", "port_name", "protocol", "port"})
    for raw in value:
        item = _closed_record("endpoint identity", raw, fields)
        if type(item["addresses"]) is not list:
            raise EvidenceError("endpoint addresses are not an exact array")
        converted = dict(item)
        converted["addresses"] = tuple(item["addresses"])
        try:
            records.append(EndpointIdentity(**converted))
        except (TypeError, ValueError):
            raise EvidenceError("endpoint identity is invalid") from None
    expected = {(namespace, service, "http", "TCP", 8080) for namespace in ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed") for service in ("envoy", "authz", "target")}
    keys = {(item.namespace, item.service, item.port_name, item.protocol, item.port) for item in records}
    if tuple(sorted(records)) != tuple(records) or len(set(records)) != len(records) or keys != expected:
        raise EvidenceError("endpoint identities or ordering differ from the fixed inventory")
    if any(item.source_kind != "Endpoints" or item.source_name != item.service for item in records):
        raise EvidenceError("endpoint source identity is not exact")
    from ipaddress import IPv4Address, IPv4Network
    network = IPv4Network("10.244.0.0/16")
    try:
        if any(IPv4Address(address) not in network for item in records for address in item.addresses):
            raise EvidenceError("endpoint address is outside the fixed Pod CIDR")
    except ValueError:
        raise EvidenceError("endpoint address is invalid") from None


def _validate_policy_attestation(value: object) -> dict[str, object]:
    policy = _closed_record("policy attestation", value, frozenset({"edges"}))
    if type(policy["edges"]) is not list or len(policy["edges"]) != 12:
        raise EvidenceError("policy graph cardinality is invalid")
    edges: list[PolicyEdge] = []
    fields = frozenset({"namespace", "source_roles", "destination_namespace", "destination_roles", "protocol_ports"})
    for raw in policy["edges"]:
        item = _closed_record("policy edge", raw, fields)
        if type(item["source_roles"]) is not list or type(item["destination_roles"]) is not list or type(item["protocol_ports"]) is not list:
            raise EvidenceError("policy edge array types are invalid")
        try:
            edge = PolicyEdge(item["namespace"], tuple(item["source_roles"]), item["destination_namespace"], tuple(item["destination_roles"]), tuple(tuple(pair) if type(pair) is list else pair for pair in item["protocol_ports"]))
        except (TypeError, ValueError):
            raise EvidenceError("policy edge is invalid") from None
        edges.append(edge)
    profile = _trusted_profile()
    expected = tuple(sorted(PolicyEdge(item.namespace, item.source_roles, item.destination_namespace, item.destination_roles, item.protocol_ports) for item in expected_policy_graph(profile)))
    if tuple(edges) != expected:
        raise EvidenceError("policy graph differs from the exact twelve approved edges")
    return policy


def _trusted_expected_topology(profile: V3B2Profile) -> dict[str, object]:
    object_keys = sorted((
        *expected_object_keys(profile),
        ("v1", "Namespace", "", "kube-system"),
        ("apps/v1", "DaemonSet", "kube-system", "calico-node"),
        ("apps/v1", "Deployment", "kube-system", "calico-kube-controllers"),
    ))
    pod_image_keys = sorted((
        ("calico-cni", "init", "kube-system", "install-cni"),
        ("calico-cni", "init", "kube-system", "upgrade-ipam"),
        ("calico-node", "init", "kube-system", "ebpf-bootstrap"),
        ("calico-node", "regular", "kube-system", "calico-node"),
        ("calico-kube-controllers", "regular", "kube-system", "calico-kube-controllers"),
        *(("workload", "regular", namespace, role)
          for namespace in ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed")
          for role in ("driver", "envoy", "authz", "target")),
    ))
    endpoint_keys = [
        (namespace, service, "http", "TCP", 8080)
        for service in ("authz", "envoy", "target")
        for namespace in ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed")
    ]
    return {
        "namespaces": [
            "default", "kil-v3-baseline", "kil-v3-local-reduce",
            "kil-v3-signed", "kube-node-lease", "kube-public",
            "kube-system", "local-path-storage",
        ],
        "object_keys": [list(item) for item in object_keys],
        "pod_image_keys": [list(item) for item in pod_image_keys],
        "endpoint_keys": [list(item) for item in endpoint_keys],
        "calico_readiness": {
            "node_desired": 1, "node_ready": 1,
            "controller_desired": 1, "controller_ready": 1,
        },
    }


def _trusted_expected_policy(profile: V3B2Profile) -> dict[str, object]:
    return {
        "edges": [
            {
                "namespace": edge.namespace,
                "source_roles": list(edge.source_roles),
                "destination_namespace": edge.destination_namespace,
                "destination_roles": list(edge.destination_roles),
                "protocol_ports": [list(pair) for pair in edge.protocol_ports],
            }
            for edge in sorted(
                expected_policy_graph(profile),
                key=lambda item: (
                    item.namespace, item.source_roles,
                    item.destination_namespace, item.destination_roles,
                    item.protocol_ports,
                ),
            )
        ]
    }


def _validate_private_expectations(
    expected_topology: object,
    expected_policy: object,
    topology: Mapping[str, object],
    policy: Mapping[str, object],
) -> None:
    profile = _trusted_profile()
    closed_topology = _closed_record(
        "private expected topology", expected_topology, _EXPECTED_TOPOLOGY_FIELDS
    )
    trusted_topology = _trusted_expected_topology(profile)
    if closed_topology != trusted_topology:
        raise EvidenceError("private expected topology differs from the trusted contract")
    runtime_topology = {
        "namespaces": topology["namespaces"],
        "object_keys": [
            [item["api_version"], item["kind"], item["namespace"], item["name"]]
            for item in topology["objects"]  # type: ignore[union-attr]
        ],
        "pod_image_keys": [
            [item["image_role"], item["container_type"], item["namespace"], item["container"]]
            for item in topology["pod_images"]  # type: ignore[union-attr]
        ],
        "endpoint_keys": [
            [item["namespace"], item["service"], item["port_name"], item["protocol"], item["port"]]
            for item in topology["endpoints"]  # type: ignore[union-attr]
        ],
        "calico_readiness": topology["calico_readiness"],
    }
    if runtime_topology != trusted_topology:
        raise EvidenceError("runtime topology is detached from the private expectation")
    closed_policy = _closed_record(
        "private expected policy graph", expected_policy, frozenset({"edges"})
    )
    trusted_policy = _trusted_expected_policy(profile)
    if closed_policy != trusted_policy or policy != trusted_policy:
        raise EvidenceError("private and runtime policy graphs differ from the trusted contract")


def build_public_bundle(private: object) -> dict[str, object]:
    """Build a closed public projection while totalizing malformed input."""
    try:
        return _build_public_bundle(private)
    except EvidenceError:
        raise
    except (KeyError, IndexError, TypeError, ValueError, UnicodeError, RecursionError):
        raise EvidenceError("private evidence is malformed") from None


def _build_public_bundle(private: object) -> dict[str, object]:
    manifest = _private_manifest(private)
    runtime = manifest["runtime_identities"]
    assert type(runtime) is dict
    cases = manifest["request_cases"]
    assert type(cases) is list
    content = _validate_content_identities(
        manifest["content_identities"],
        run_id=manifest["run_id"],
        profile_sha256=manifest["profile_sha256"],
    )
    topology = _validate_topology_attestation(
        runtime.get("topology_attestation"), content
    )
    policy = _validate_policy_attestation(runtime.get("policy_attestation"))
    _validate_private_expectations(
        manifest["expected_topology"],
        manifest["expected_policy_graph"],
        topology,
        policy,
    )
    try:
        key = sha256((str(manifest["execution_nonce"]) + ":foreign-profile-projection").encode("utf-8")).digest()
        foreign = project_foreign_profiles(manifest["foreign_profiles_before"], runtime["foreign_profiles_after"], key)
    except KeyError:
        raise EvidenceError("foreign state attestation is incomplete") from None
    unchanged_context = runtime.get("global_context_after") == manifest["global_context_before"]
    teardown = runtime.get("owned_teardown")
    if (
        type(teardown) is not dict
        or any(type(teardown.get(name)) is not bool for name in ("cluster_absent", "profile_absent", "private_active_state_absent"))
        or teardown != {
        "cluster_absent": True,
        "profile_absent": True,
        "private_active_state_absent": True,
        }
    ):
        raise EvidenceError("owned teardown attestation is invalid")
    grouped = _records(manifest)
    if not foreign["unchanged"] or not unchanged_context:
        if cases or any(grouped.values()):
            raise EvidenceError("foreign mismatch diagnostic contains request evidence")
        result_class = "diagnostic_foreign_state_mismatch"
        joins = []
        request_results = []
    elif cases:
        joins = join_nominal_evidence(manifest)
        drivers = [
            next(record for record in grouped["driver"] if record["track"] == track)
            for track in TRACKS
        ]
        request_results = [
            {**driver, "target_markers": joins[index]["target_markers"]}
            for index, driver in enumerate(drivers)
        ]
        result_class = RESULT_CLASS
    else:
        if any(grouped.values()):
            raise EvidenceError("request-free evidence contains application records")
        joins = []
        request_results = []
        result_class = REQUEST_FREE_RESULT_CLASS
    public: dict[str, object] = {
        "schema_version": PUBLIC_MANIFEST_SCHEMA,
        "run_id": manifest["run_id"],
        "source_commit": manifest["source_commit"],
        "profile_sha256": manifest["profile_sha256"],
        "evidence_scope": "kind_calico_boundary",
        "result_class": result_class,
        "promotion_status": PROMOTION_STATUS,
        "content_identities": content,
        "topology_attestation": topology,
        "policy_attestation": policy,
        "request_results": request_results,
        "semantic_joins": joins,
        "source_attestations": _public_source_attestations(manifest["source_attestations"]),
        "foreign_profile_attestation": foreign,
        "global_context_unchanged": unchanged_context,
        "owned_teardown": teardown,
        "claim_exclusions": list(CLAIM_EXCLUSIONS),
        "public_commitment_sha256": "",
    }
    before_names = tuple(
        record["name"]
        for record in _foreign_records(manifest["foreign_profiles_before"])
    )
    after_names = tuple(
        record["name"]
        for record in _foreign_records(runtime["foreign_profiles_after"])
    )
    validate_public_projection(
        public, forbidden_names=(*before_names, *after_names)
    )
    return public


def _public_source_attestations(value: object) -> list[dict[str, object]]:
    if type(value) is not list:
        raise EvidenceError("source attestations are invalid")
    result = []
    for item in value:
        record = _closed_record("source attestation", item, _ATTESTATION_FIELDS)
        payload = b"".join(_canonical_bytes(member) for member in record["records"]) if type(record["records"]) is list else b""
        result.append({"kind": record["kind"], "track": record["track"], "byte_count": len(payload), "sha256": sha256(payload).hexdigest()})
    return result


def validate_public_projection(
    value: object, *, forbidden_names: Sequence[str] = ()
) -> None:
    """Reject secret-shaped field names and values at any nesting depth."""
    if type(value) is not dict:
        raise PublicBoundaryError("public projection must be an exact object")
    if type(forbidden_names) not in (tuple, list) or any(
        type(name) is not str or not name for name in forbidden_names
    ):
        raise PublicBoundaryError("foreign-name boundary is invalid")
    try:
        if any(len(name.encode("utf-8")) > 4096 for name in forbidden_names):
            raise PublicBoundaryError("foreign-name boundary exceeds its bound")
    except UnicodeEncodeError:
        raise PublicBoundaryError("foreign-name boundary contains invalid Unicode") from None
    unique_names = tuple(sorted(set(forbidden_names)))
    seen: set[int] = set()
    def walk(member: object, depth: int) -> None:
        if depth > 32:
            raise PublicBoundaryError("public projection nesting is excessive")
        if type(member) in (dict, list):
            identity = id(member)
            if identity in seen:
                raise PublicBoundaryError("public projection is recursive")
            seen.add(identity)
        if type(member) is dict:
            for key, child in member.items():
                try:
                    invalid_key = (
                        type(key) is not str
                        or len(key.encode("utf-8")) > 4096
                        or any(token in key.lower() for token in _PRIVATE_KEYS)
                        or any(name in key for name in unique_names)
                    )
                except UnicodeEncodeError:
                    raise PublicBoundaryError(
                        "public field name contains invalid Unicode"
                    ) from None
                if invalid_key:
                    raise PublicBoundaryError("public projection contains a private field name")
                walk(child, depth + 1)
        elif type(member) is list:
            for child in member:
                walk(child, depth + 1)
        elif type(member) is str:
            lowered = member.lower()
            if (
                member not in TRACKS
                and any(token in lowered for token in _PRIVATE_TEXT)
            ) or member.startswith("/"):
                raise PublicBoundaryError("public projection contains private material")
            try:
                encoded = member.encode("utf-8")
            except UnicodeEncodeError:
                raise PublicBoundaryError(
                    "public string contains invalid Unicode"
                ) from None
            if len(encoded) > 65536:
                raise PublicBoundaryError("public string exceeds its bound")
            for name in unique_names:
                if name in member:
                    raise PublicBoundaryError(
                        "public projection contains a foreign profile name"
                    )
        elif type(member) not in (int, bool, type(None)):
            raise PublicBoundaryError("public projection contains a non-JSON exact type")
    walk(value, 0)


def _artifacts(public: Mapping[str, object]) -> dict[str, bytes]:
    joins = public["semantic_joins"]
    requests = public["request_results"]
    request_records = [{key: item[key] for key in ("track", "request_id", "attempt", "decision", "http_status", "decision_digest")} for item in requests]  # type: ignore[index]
    decisions = [{"track": item["track"], "request_id": item["request_id"], "decision": item["decision"], "decision_digest": item["decision_digest"]} for item in requests]  # type: ignore[index]
    envoy = [{"track": item["track"], "request_id": item["request_id"], "decision_digest": item["decision_digest"], "upstream_attempted": item["decision"] == "permit", "upstream_status": item["http_status"] if item["decision"] == "permit" else None} for item in requests]  # type: ignore[index]
    targets = [{"track": item["track"], "request_id": item["request_id"], "marker": index + 1} for item in requests for index in range(item["target_markers"])]  # type: ignore[index]
    def jsonl(records: object) -> bytes:
        assert type(records) is list
        return b"".join(_canonical_bytes(record) for record in records)
    summary = (
        "# KIL V3B-2a Kind/Calico evidence\n\n"
        f"Result class: `{public['result_class']}`\n\n"
        "Promotion status: `not_promoted`\n\n"
        "This is an intermediate nominal or request-free diagnostic result; it does not establish complete V3B-2 validation, performance, production validation, or historical prevention.\n"
    ).encode("utf-8")
    live = (
        "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><title>KIL V3B-2a evidence</title>"
        f"<h1>KIL V3B-2a Kind/Calico evidence</h1><p>{public['result_class']}</p><p>not_promoted</p>"
        "<p>Intermediate evidence only; no complete NetworkPolicy, reliability, performance, production, or historical-prevention claim.</p></html>\n"
    ).encode("utf-8")
    return {
        "requests.jsonl": jsonl(request_records),
        "decisions.jsonl": jsonl(decisions),
        "envoy.jsonl": jsonl(envoy),
        "targets.jsonl": jsonl(targets),
        "kubernetes.jsonl": jsonl([public["topology_attestation"]]),
        "policies.jsonl": jsonl([public["policy_attestation"]]),
        "joins.jsonl": jsonl(joins),
        "summary.md": summary,
        "live.html": live,
    }


def _write_regular_at(directory_fd: int, name: str, payload: bytes) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=directory_fd,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def _directory_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_uid, value.st_mode & 0o777)


def _open_child_directory(parent_fd: int, name: str, label: str) -> int:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        inspected = os.fstat(descriptor)
        if not stat.S_ISDIR(inspected.st_mode):
            raise OSError("not directory")
        return descriptor
    except OSError:
        raise EvidenceError(f"{label} is unavailable or unsafe") from None


def _open_directory_anchor(
    path: object, label: str
) -> tuple[Path, int, tuple[int, int, int, int]]:
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise EvidenceError(f"{label} must be an absolute normalized path")
    descriptor = -1
    try:
        descriptor = os.open(
            path.anchor,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        for component in path.parts[1:]:
            child = _open_child_directory(descriptor, component, label)
            os.close(descriptor)
            descriptor = child
        inspected = os.fstat(descriptor)
        return path, descriptor, _directory_identity(inspected)
    except EvidenceError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        raise EvidenceError(f"{label} ancestry is unavailable") from None


def _assert_anchor_path(
    path: Path, identity: tuple[int, int, int, int], label: str
) -> None:
    _, descriptor, current = _open_directory_anchor(path, label)
    os.close(descriptor)
    if current != identity:
        raise EvidenceError(f"{label} changed after identity anchoring")


def _entry_exists(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        raise EvidenceError("directory entry cannot be inspected safely") from None


def _rename_directory_exclusive(
    source_fd: int, source: str, destination_fd: int, destination: str
) -> None:
    """Atomically rename a directory without replacing a raced destination."""
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = source.encode("utf-8")
    destination_bytes = destination.encode("utf-8")
    if hasattr(library, "renameatx_np"):
        operation = library.renameatx_np
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        operation.restype = ctypes.c_int
        result = operation(
            source_fd, source_bytes, destination_fd, destination_bytes, 0x00000004
        )
    elif hasattr(library, "renameat2"):
        operation = library.renameat2
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        operation.restype = ctypes.c_int
        result = operation(
            source_fd, source_bytes, destination_fd, destination_bytes, 0x00000001
        )
    else:
        raise EvidenceError("exclusive atomic directory rename is unavailable")
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, "exclusive directory rename failed")


def _cleanup_staging_directory(parent_fd: int, staging_fd: int, name: str) -> None:
    try:
        for child in os.listdir(staging_fd):
            os.unlink(child, dir_fd=staging_fd)
        os.rmdir(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except OSError:
        pass


def _prepare_directory_parent(
    path: object, label: str, *, private: bool
) -> tuple[Path, int, tuple[int, int, int, int]]:
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise EvidenceError(f"{label} must be an absolute normalized path")
    try:
        result = _open_directory_anchor(path, label)
        descriptor = result[1]
        inspected = os.fstat(descriptor)
    except EvidenceError:
        _, ancestor_fd, _ = _open_directory_anchor(
            path.parent, f"{label} ancestor"
        )
        try:
            os.mkdir(path.name, 0o700, dir_fd=ancestor_fd)
            os.fsync(ancestor_fd)
            descriptor = _open_child_directory(ancestor_fd, path.name, label)
        except (OSError, EvidenceError):
            os.close(ancestor_fd)
            raise EvidenceError(f"{label} cannot be created safely") from None
        os.close(ancestor_fd)
        inspected = os.fstat(descriptor)
        result = (path, descriptor, _directory_identity(inspected))
    if private and (
        inspected.st_uid != os.geteuid() or inspected.st_mode & 0o077
    ):
        os.close(descriptor)
        raise EvidenceError(f"{label} permissions or ownership are unsafe")
    return result


def _prepare_public_parent(
    path: object,
) -> tuple[Path, int, tuple[int, int, int, int]]:
    return _prepare_directory_parent(path, "public parent", private=False)


def _prepare_private_diagnostic_parent(
    target: Path,
) -> tuple[Path, int, tuple[int, int, int, int]]:
    if not target.name or target.name in {".", ".."}:
        raise EvidenceError("private diagnostic file name is invalid")
    return _prepare_directory_parent(
        target.parent, "private diagnostic parent", private=True
    )


def publish_bundle(private: object, public_parent: Path) -> Path:
    """Build privately, verify semantically, then publish with one rename."""
    try:
        return _publish_bundle(private, public_parent)
    except EvidenceError:
        raise
    except (OSError, TypeError, ValueError, UnicodeError, RuntimeError):
        raise EvidenceError("publication inputs are invalid") from None


def _publish_bundle(private: object, public_parent: Path) -> Path:
    public = build_public_bundle(private)
    parent, parent_fd, parent_identity = _prepare_public_parent(public_parent)
    run_id = str(public["run_id"])
    private_manifest = _private_manifest(private)
    runtime = private_manifest["runtime_identities"]
    assert type(runtime) is dict
    foreign_names = tuple(
        record["name"]
        for record in (
            *_foreign_records(private_manifest["foreign_profiles_before"]),
            *_foreign_records(runtime["foreign_profiles_after"]),
        )
    )
    destination = parent / run_id
    if _entry_exists(parent_fd, run_id):
        os.close(parent_fd)
        raise EvidenceError("public destination clobber is forbidden")
    token = sha256(os.urandom(32)).hexdigest()
    staging_name = f".{run_id}.private-{token}"
    staging_fd = -1
    renamed = False
    try:
        _assert_anchor_path(parent, parent_identity, "public parent")
        os.mkdir(staging_name, 0o700, dir_fd=parent_fd)
        staging_fd = _open_child_directory(
            parent_fd, staging_name, "private publication staging"
        )
        staging_identity = _directory_identity(os.fstat(staging_fd))
        artifacts = _artifacts(public)
        for name, payload in artifacts.items():
            try:
                text = payload.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                raise PublicBoundaryError("public artifact is not UTF-8") from None
            for foreign_name in foreign_names:
                if foreign_name in text:
                    raise PublicBoundaryError(
                        "public artifact contains a foreign profile name"
                    )
        public["public_commitment_sha256"] = _public_commitment(public, artifacts)
        validate_public_projection(public)
        payloads = {"manifest.json": _canonical_bytes(public), **artifacts}
        for name in sorted(payloads):
            _write_regular_at(staging_fd, name, payloads[name])
        sums = "".join(f"{sha256(payloads[name]).hexdigest()}  {name}\n" for name in sorted(payloads)).encode("ascii")
        _write_regular_at(staging_fd, "SHA256SUMS", sums)
        os.fsync(staging_fd)
        staged_payloads = _read_tree_fd(staging_fd, set(PUBLIC_FILES))
        _verify_sums(staged_payloads, set(PUBLIC_FILES))
        _verify_v3b2(staged_payloads)
        _assert_anchor_path(parent, parent_identity, "public parent")
        _rename_directory_exclusive(parent_fd, staging_name, parent_fd, run_id)
        renamed = True
        published_identity = os.stat(run_id, dir_fd=parent_fd, follow_symlinks=False)
        if staging_identity != _directory_identity(published_identity):
            raise EvidenceError("published directory identity changed during rename")
        os.fsync(parent_fd)
        final_payloads = _read_tree_fd(staging_fd, set(PUBLIC_FILES))
        _verify_sums(final_payloads, set(PUBLIC_FILES))
        _verify_v3b2(final_payloads)
        if _directory_identity(
            os.stat(run_id, dir_fd=parent_fd, follow_symlinks=False)
        ) != staging_identity:
            raise EvidenceError("published directory was replaced after verification")
        _assert_anchor_path(parent, parent_identity, "public parent")
        return destination
    except EvidenceError:
        # After publication no portable rename primitive can condition its
        # source on the inode we own.  Leave the destination name untouched:
        # the absent completion event makes recovery/manual inspection safe,
        # while cleanup here could move a raced replacement.
        raise
    except (OSError, ValueError, TypeError, UnicodeError):
        raise EvidenceError("atomic publication failed closed") from None
    finally:
        if staging_fd >= 0:
            if not renamed:
                _cleanup_staging_directory(parent_fd, staging_fd, staging_name)
            os.close(staging_fd)
        os.close(parent_fd)


def _read_tree_fd(
    directory_fd: int,
    expected: set[str],
    before_completion: Callable[[], None] | None = None,
) -> dict[str, bytes]:
    directory_before = os.fstat(directory_fd)
    if not stat.S_ISDIR(directory_before.st_mode) or set(os.listdir(directory_fd)) != expected:
        raise EvidenceError("evidence file set is not exact")
    payloads: dict[str, bytes] = {}
    identities: dict[str, tuple[int, int, int, int]] = {}
    for name in sorted(expected):
        try:
            before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_FILE_BYTES:
                raise EvidenceError("evidence file is unsafe or oversized")
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            try:
                opened = os.fstat(descriptor)
                chunks: list[bytes] = []
                remaining = _MAX_FILE_BYTES + 1
                while remaining:
                    chunk = os.read(descriptor, min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                data = b"".join(chunks)
            finally:
                os.close(descriptor)
            after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except EvidenceError:
            raise
        except OSError:
            raise EvidenceError("evidence file changed during bounded read") from None
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if (
            len(data) > _MAX_FILE_BYTES
            or identity != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            or identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise EvidenceError("evidence file was replaced during validation")
        identities[name] = identity
        payloads[name] = data
    if before_completion is not None:
        before_completion()
    if set(os.listdir(directory_fd)) != expected:
        raise EvidenceError("evidence tree changed during validation")
    if _directory_identity(os.fstat(directory_fd)) != _directory_identity(directory_before):
        raise EvidenceError("evidence directory changed during validation")
    for name, identity in identities.items():
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(current.st_mode) or identity != (
            current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns
        ):
            raise EvidenceError("evidence tree was replaced after validation")
    return payloads


def _read_manifest_only_fd(directory_fd: int) -> bytes:
    try:
        before = os.stat("manifest.json", dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_FILE_BYTES:
            raise EvidenceError("evidence manifest is unsafe or oversized")
        descriptor = os.open(
            "manifest.json",
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        try:
            opened = os.fstat(descriptor)
            chunks: list[bytes] = []
            remaining = _MAX_FILE_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
        finally:
            os.close(descriptor)
        after = os.stat("manifest.json", dir_fd=directory_fd, follow_symlinks=False)
    except EvidenceError:
        raise
    except OSError:
        raise EvidenceError("evidence manifest changed during bounded read") from None
    identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    if len(payload) > _MAX_FILE_BYTES or identity != (
        opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns
    ) or identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise EvidenceError("evidence manifest changed during bounded read")
    return payload


def _parse_json(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise EvidenceError(f"{label} is malformed") from None
    if type(value) is not dict or payload != _canonical_bytes(value):
        raise EvidenceError(f"{label} is not canonical")
    return value


def _parse_jsonl(payload: bytes, label: str) -> list[dict[str, object]]:
    if not payload:
        return []
    if not payload.endswith(b"\n") or b"\n\n" in payload:
        raise EvidenceError(f"{label} JSONL is partial or duplicated")
    records = []
    for line in payload.splitlines(keepends=True):
        record = _parse_json(line, label)
        records.append(record)
    return records


def _verify_sums(payloads: Mapping[str, bytes], expected_files: set[str]) -> None:
    try:
        lines = payloads["SHA256SUMS"].decode("ascii").splitlines()
    except UnicodeError:
        raise EvidenceError("checksum file is malformed") from None
    names: list[str] = []
    for line in lines:
        if line.count("  ") != 1:
            raise EvidenceError("checksum line is malformed")
        digest, name = line.split("  ", 1)
        if _HEX64.fullmatch(digest) is None or name.startswith("/") or "/" in name or name in names:
            raise EvidenceError("checksum entry is invalid or duplicated")
        names.append(name)
        if name not in payloads or sha256(payloads[name]).hexdigest() != digest:
            raise EvidenceError("checksum mismatch")
    wanted = sorted(expected_files - {"SHA256SUMS"})
    if names != wanted:
        raise EvidenceError("checksum order or coverage is invalid")


def _verify_v3b2(payloads: Mapping[str, bytes]) -> VerifiedBundle:
    manifest = _parse_json(payloads["manifest.json"], "public manifest")
    value = _closed_record("V3B-2 public manifest", manifest, PUBLIC_MANIFEST_FIELDS)
    if value.get("schema_version") != PUBLIC_MANIFEST_SCHEMA:
        raise EvidenceError("V3B-2 public schema is invalid")
    validate_public_projection(value)
    if (
        type(value.get("run_id")) is not str
        or _V3B2_RUN.fullmatch(value["run_id"]) is None
        or type(value.get("source_commit")) is not str
        or _HEX40.fullmatch(value["source_commit"]) is None
        or type(value.get("profile_sha256")) is not str
        or _HEX64.fullmatch(value["profile_sha256"]) is None
    ):
        raise EvidenceError("V3B-2 public run or source identity is invalid")
    if value.get("promotion_status") != PROMOTION_STATUS or value.get("claim_exclusions") != list(CLAIM_EXCLUSIONS) or value.get("evidence_scope") != "kind_calico_boundary":
        raise EvidenceError("V3B-2 claim boundary is invalid")
    if type(value.get("content_identities")) is not dict or type(value.get("topology_attestation")) is not dict or type(value.get("policy_attestation")) is not dict:
        raise EvidenceError("V3B-2 public attestations have invalid exact types")
    content = _validate_content_identities(
        value["content_identities"],
        run_id=value.get("run_id"),
        profile_sha256=value.get("profile_sha256"),
    )
    _validate_topology_attestation(value["topology_attestation"], content)
    _validate_policy_attestation(value["policy_attestation"])
    teardown = value.get("owned_teardown")
    if type(teardown) is not dict or any(type(teardown.get(name)) is not bool for name in ("cluster_absent", "profile_absent", "private_active_state_absent")) or teardown != {
        "cluster_absent": True,
        "profile_absent": True,
        "private_active_state_absent": True,
    } or type(value.get("global_context_unchanged")) is not bool:
        raise EvidenceError("V3B-2 teardown or context attestation is invalid")
    _verify_foreign_projection(value.get("foreign_profile_attestation"))
    parsed = {
        name: _parse_jsonl(payloads[name], name)
        for name in ("requests.jsonl", "decisions.jsonl", "envoy.jsonl", "targets.jsonl", "kubernetes.jsonl", "policies.jsonl", "joins.jsonl")
    }
    artifacts = {name: payloads[name] for name in _DATA_FILES}
    if value.get("public_commitment_sha256") != _public_commitment(value, artifacts):
        raise EvidenceError("public semantic commitment does not match")
    expected_artifacts = _artifacts(value)
    if any(payloads[name] != expected_artifacts[name] for name in _DATA_FILES):
        raise EvidenceError("public artifacts do not rederive from the manifest")
    joins = value.get("semantic_joins")
    requests = value.get("request_results")
    result_class = value.get("result_class")
    if type(joins) is not list or type(requests) is not list or type(result_class) is not str:
        raise EvidenceError("public semantic fields have invalid types")
    if result_class == RESULT_CLASS:
        wanted = (("permit", 200, 1), ("permit", 200, 1), ("deny", 403, 0))
        got = tuple((item.get("decision"), item.get("http_status"), item.get("target_markers")) for item in requests if type(item) is dict)
        if got != wanted or len(joins) != 3:
            raise EvidenceError("public nominal tuple is invalid")
        _verify_nominal_public_records(parsed, requests, joins)
        _verify_public_source_attestations(value.get("source_attestations"), parsed)
        if value.get("global_context_unchanged") is not True or value["foreign_profile_attestation"]["unchanged"] is not True:  # type: ignore[index]
            raise EvidenceError("nominal bundle foreign state is not unchanged")
    elif result_class == REQUEST_FREE_RESULT_CLASS:
        if requests or joins or value.get("source_attestations") != []:
            raise EvidenceError("request-free bundle contains requests or joins")
        if value.get("global_context_unchanged") is not True or value["foreign_profile_attestation"]["unchanged"] is not True:  # type: ignore[index]
            raise EvidenceError("request-free bundle foreign state is not unchanged")
    elif result_class == "diagnostic_foreign_state_mismatch":
        if (
            requests
            or joins
            or value.get("source_attestations") != []
            or any(parsed[name] for name in (
                "requests.jsonl", "decisions.jsonl", "envoy.jsonl",
                "targets.jsonl", "joins.jsonl",
            ))
            or value.get("foreign_profile_attestation", {}).get("unchanged") is not False  # type: ignore[union-attr]
        ):
            raise EvidenceError("foreign mismatch diagnostic is invalid")
    else:
        raise EvidenceError("public result class is invalid")
    commitment = value["public_commitment_sha256"]
    run_id = value["run_id"]
    if type(commitment) is not str or type(run_id) is not str:
        raise EvidenceError("public identities are invalid")
    return VerifiedBundle("v3b2-run", run_id, result_class, PROMOTION_STATUS, commitment)


def _verify_foreign_projection(value: object) -> None:
    record = _closed_record(
        "foreign profile attestation",
        value,
        frozenset({"before", "after", "unchanged"}),
    )
    if type(record["before"]) is not list or type(record["after"]) is not list or type(record["unchanged"]) is not bool:
        raise EvidenceError("foreign profile attestation types are invalid")
    fields = frozenset({"pseudonym", "status", "arch", "cpus", "memory", "disk", "runtime"})
    for side in (record["before"], record["after"]):
        pseudonyms: list[str] = []
        for raw in side:
            item = _closed_record("foreign profile projection", raw, fields)
            pseudonym = item["pseudonym"]
            if type(pseudonym) is not str or _HEX64.fullmatch(pseudonym) is None:
                raise EvidenceError("foreign profile pseudonym is invalid")
            if type(item["status"]) is not str or item["status"] not in {"Running", "Stopped"}:
                raise EvidenceError("foreign profile projected status is invalid")
            if any(type(item[name]) is not int or item[name] < 0 for name in ("cpus", "memory", "disk")):
                raise EvidenceError("foreign profile projected resources are invalid")
            if any(type(item[name]) is not str or not item[name] for name in ("arch", "runtime")):
                raise EvidenceError("foreign profile projected resource text is invalid")
            pseudonyms.append(pseudonym)
        if pseudonyms != sorted(pseudonyms) or len(pseudonyms) != len(set(pseudonyms)):
            raise EvidenceError("foreign profile projections are not unique and sorted")
    if record["unchanged"] is not (record["before"] == record["after"]):
        raise EvidenceError("foreign profile equality flag is not rederived")


def _verify_public_source_attestations(
    attestations: object, parsed: Mapping[str, list[dict[str, object]]]
) -> None:
    if type(attestations) is not list or len(attestations) != 12:
        raise EvidenceError("public source attestation cardinality is invalid")
    file_for_kind = {
        "driver": "requests.jsonl",
        "decision": "decisions.jsonl",
        "envoy": "envoy.jsonl",
        "target": "targets.jsonl",
    }
    expected_pairs = [(kind, track) for track in TRACKS for kind in file_for_kind]
    observed_pairs: list[tuple[object, object]] = []
    for raw in attestations:
        record = _closed_record(
            "public source attestation",
            raw,
            frozenset({"kind", "track", "byte_count", "sha256"}),
        )
        kind, track = record["kind"], record["track"]
        observed_pairs.append((kind, track))
        if type(kind) is not str or kind not in file_for_kind or type(track) is not str or track not in TRACKS:
            raise EvidenceError("public source attestation identity is invalid")
        selected = [item for item in parsed[file_for_kind[kind]] if item.get("track") == track]
        payload = b"".join(_canonical_bytes(item) for item in selected)
        if (
            type(record.get("byte_count")) is not int
            or type(record.get("sha256")) is not str
            or record.get("byte_count") != len(payload)
            or record.get("sha256") != sha256(payload).hexdigest()
        ):
            raise EvidenceError("public source attestation does not bind its records")
    if observed_pairs != expected_pairs:
        raise EvidenceError("public source attestations are not in canonical order")


def _verify_nominal_public_records(
    parsed: Mapping[str, list[dict[str, object]]],
    requests: list[object],
    joins: list[object],
) -> None:
    expected_outcomes = (("permit", 200, 1, True), ("permit", 200, 1, True), ("deny", 403, 0, False))
    request_records = parsed["requests.jsonl"]
    decisions, envoy, targets = parsed["decisions.jsonl"], parsed["envoy.jsonl"], parsed["targets.jsonl"]
    if len(request_records) != 3 or len(decisions) != 3 or len(envoy) != 3 or len(requests) != 3:
        raise EvidenceError("public nominal source cardinality is invalid")
    for index, track in enumerate(TRACKS):
        decision_name, status, marker_count, attempted = expected_outcomes[index]
        request, raw_request, decision, proxy, join = requests[index], request_records[index], decisions[index], envoy[index], joins[index]
        if any(type(item) is not dict for item in (request, raw_request, decision, proxy, join)):
            raise EvidenceError("public nominal record type is invalid")
        assert type(request) is dict and type(join) is dict
        digest = decision.get("decision_digest")
        track_targets = [target for target in targets if target.get("track") == track]
        if (
            request.get("track") != track
            or raw_request.get("track") != track
            or decision.get("track") != track
            or proxy.get("track") != track
            or join.get("track") != track
            or any(item.get("request_id") != "v3b1-central-request" for item in (request, raw_request, decision, proxy, join, *track_targets))
            or set(request) != (_DRIVER_FIELDS | {"target_markers"})
            or set(raw_request) != _DRIVER_FIELDS
            or set(decision) != _DECISION_FIELDS
            or set(proxy) != _ENVOY_FIELDS
            or set(join) != frozenset({"track", "request_id", "decision", "http_status", "target_markers", "decision_digest_equal", "decision_digest", "envoy_upstream_attempted"})
            or any(set(target) != _TARGET_FIELDS for target in track_targets)
            or raw_request != {key: request[key] for key in _DRIVER_FIELDS}
            or decision.get("decision") != decision_name
            or request.get("decision") != decision_name
            or join.get("decision") != decision_name
            or request.get("http_status") != status
            or join.get("http_status") != status
            or join.get("target_markers") != marker_count
            or proxy.get("upstream_status") != (status if attempted else None)
            or proxy.get("upstream_attempted") is not attempted
            or join.get("envoy_upstream_attempted") is not attempted
            or join.get("decision_digest_equal") is not True
            or join.get("decision_digest") != digest
            or raw_request.get("decision_digest") != digest
            or proxy.get("decision_digest") != digest
            or raw_request.get("attempt") != 1
            or type(raw_request.get("attempt")) is not int
            or type(request.get("http_status")) is not int
            or type(request.get("target_markers")) is not int
            or type(digest) is not str
            or _HEX64.fullmatch(digest) is None
            or len(track_targets) != marker_count
            or any(type(target.get("marker")) is not int or target.get("marker") != number + 1 for number, target in enumerate(track_targets))
        ):
            raise EvidenceError("public nominal semantic join is invalid")
    if len(targets) != 2 or any(target.get("track") not in TRACKS for target in targets):
        raise EvidenceError("public target evidence is cross-track")


def verify_bundle(path: Path, *, before_completion: Callable[[], None] | None = None) -> VerifiedBundle:
    """Verify one bounded no-follow bundle with independent schema dispatch."""
    try:
        return _verify_bundle(path, before_completion=before_completion)
    except EvidenceError:
        raise
    except (OSError, TypeError, ValueError, UnicodeError, RecursionError):
        raise EvidenceError("bundle verification failed closed") from None


def _verify_bundle(path: Path, *, before_completion: Callable[[], None] | None = None) -> VerifiedBundle:
    bundle, directory_fd, identity = _open_directory_anchor(path, "evidence bundle")
    try:
        manifest = _parse_json(_read_manifest_only_fd(directory_fd), "public manifest")
        schema = manifest.get("schema_version")
        try:
            family = dispatch_schema(manifest)
        except SchemaError:
            raise EvidenceError("bundle schema dispatch failed closed") from None
        if schema == PUBLIC_MANIFEST_SCHEMA:
            expected = set(PUBLIC_FILES)
            payloads = _read_tree_fd(
                directory_fd, expected, before_completion=before_completion
            )
            _verify_sums(payloads, expected)
            result = _verify_v3b2(payloads)
            _assert_anchor_path(bundle, identity, "evidence bundle")
            return result
        if type(schema) is str and schema.startswith("kil.v3b1-public-manifest.") and family == schema:
            _assert_anchor_path(bundle, identity, "evidence bundle")
            try:
                from tools.v3b1_local_envoy import (
                    ControllerError,
                    _verify_failure_presenter_bundle,
                    verify_presenter_bundle,
                )
            except (ImportError, AttributeError):
                raise EvidenceError("V3B-1 verifier is unavailable") from None
            accepted = False
            for verifier in (verify_presenter_bundle, _verify_failure_presenter_bundle):
                try:
                    verifier(bundle, before_completion=before_completion)
                    accepted = True
                    break
                except (ControllerError, OSError):
                    continue
            if not accepted:
                raise EvidenceError("V3B-1 bundle failed its independent verifier")
            _assert_anchor_path(bundle, identity, "evidence bundle")
            run_id = manifest.get("run_id", "")
            if type(run_id) is not str:
                raise EvidenceError("V3B-1 run ID is invalid")
            return VerifiedBundle("v3b1", run_id, str(manifest.get("bundle_class", "v3b1")), str(manifest.get("promotion_status", "not_promoted")), sha256(_canonical_bytes(manifest)).hexdigest())
        raise EvidenceError("bundle schema family is not implemented")
    finally:
        os.close(directory_fd)
