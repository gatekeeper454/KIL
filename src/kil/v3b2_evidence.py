"""Bounded capture, semantic joins, and offline V3B-2a evidence verification."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Callable, Mapping, Protocol, Sequence

from kil.v3b2_contracts import (
    PRIVATE_MANIFEST_FIELDS,
    PRIVATE_MANIFEST_SCHEMA,
    PUBLIC_MANIFEST_FIELDS,
    PUBLIC_MANIFEST_SCHEMA,
    TRACKS,
    dispatch_schema,
    require_closed_object,
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
            if type(value) is not str or not value or len(value.encode("utf-8")) > 4096:
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
            if type(value) is not str:
                raise EvidenceError("verified bundle contains an invalid string")
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
    """Persist malformed source bytes and a closed hash binding in a private area."""
    target = Path(os.path.abspath(path))
    try:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.parent.is_symlink() or target.exists() or target.is_symlink():
            raise EvidenceError("private diagnostic destination is unsafe")
        _write_regular(target, payload)
        _write_regular(
            target.with_name(target.name + ".diagnostic.json"),
            _canonical_bytes(
                {
                    "category": "malformed_source_bytes",
                    "byte_count": len(payload),
                    "sha256": sha256(payload).hexdigest(),
                }
            ),
        )
    except EvidenceError:
        raise
    except OSError:
        raise EvidenceError("private diagnostic persistence failed closed") from None


def _closed_record(label: str, value: object, fields: frozenset[str]) -> dict[str, object]:
    try:
        return require_closed_object(label, value, fields)
    except Exception:
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
        if type(record["status"]) is not str or record["status"] not in {"Running", "Stopped"}:
            raise EvidenceError("foreign profile status is invalid")
        if any(type(record[field]) is not int or record[field] < 0 for field in ("cpus", "memory", "disk")):
            raise EvidenceError("foreign profile resource is invalid")
        if any(type(record[field]) is not str or not record[field] for field in ("arch", "runtime")):
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


def build_public_bundle(private: object) -> dict[str, object]:
    manifest = _private_manifest(private)
    runtime = manifest["runtime_identities"]
    assert type(runtime) is dict
    cases = manifest["request_cases"]
    assert type(cases) is list
    if cases:
        joins = join_nominal_evidence(manifest)
        grouped = _records(manifest)
        drivers = [
            next(record for record in grouped["driver"] if record["track"] == track)
            for track in TRACKS
        ]
        request_results = [
            {
                **driver,
                "target_markers": joins[index]["target_markers"],
            }
            for index, driver in enumerate(drivers)
        ]
        result_class = RESULT_CLASS
    else:
        if any(_records(manifest).values()):
            raise EvidenceError("request-free evidence contains application records")
        joins = []
        request_results = []
        result_class = REQUEST_FREE_RESULT_CLASS
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
    if not foreign["unchanged"] or not unchanged_context:
        result_class = "diagnostic_foreign_state_mismatch"
        joins = []
    public: dict[str, object] = {
        "schema_version": PUBLIC_MANIFEST_SCHEMA,
        "run_id": manifest["run_id"],
        "source_commit": manifest["source_commit"],
        "profile_sha256": manifest["profile_sha256"],
        "evidence_scope": "kind_calico_boundary",
        "result_class": result_class,
        "promotion_status": PROMOTION_STATUS,
        "content_identities": manifest["content_identities"],
        "topology_attestation": runtime.get("topology_attestation"),
        "policy_attestation": runtime.get("policy_attestation"),
        "request_results": request_results,
        "semantic_joins": joins,
        "source_attestations": _public_source_attestations(manifest["source_attestations"]),
        "foreign_profile_attestation": foreign,
        "global_context_unchanged": unchanged_context,
        "owned_teardown": teardown,
        "claim_exclusions": list(CLAIM_EXCLUSIONS),
        "public_commitment_sha256": "",
    }
    validate_public_projection(public)
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


def validate_public_projection(value: object) -> None:
    """Reject secret-shaped field names and values at any nesting depth."""
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
                if type(key) is not str or any(token in key.lower() for token in _PRIVATE_KEYS):
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
            if len(member.encode("utf-8")) > 65536:
                raise PublicBoundaryError("public string exceeds its bound")
        elif type(member) not in (int, bool, type(None), float):
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


def _write_regular(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def publish_bundle(private: object, public_parent: Path) -> Path:
    """Build privately, verify semantically, then publish with one rename."""
    public = build_public_bundle(private)
    run_id = str(public["run_id"])
    parent = Path(os.path.abspath(public_parent))
    if parent.is_symlink():
        raise EvidenceError("public parent is unsafe")
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not parent.is_dir():
        raise EvidenceError("public parent is unsafe")
    destination = parent / run_id
    if destination.exists() or destination.is_symlink():
        raise EvidenceError("public destination clobber is forbidden")
    staging = Path(tempfile.mkdtemp(prefix=f".{run_id}.private-", dir=parent))
    os.chmod(staging, 0o700)
    try:
        artifacts = _artifacts(public)
        public["public_commitment_sha256"] = _public_commitment(public, artifacts)
        validate_public_projection(public)
        payloads = {"manifest.json": _canonical_bytes(public), **artifacts}
        for name in sorted(payloads):
            _write_regular(staging / name, payloads[name])
        sums = "".join(f"{sha256(payloads[name]).hexdigest()}  {name}\n" for name in sorted(payloads)).encode("ascii")
        _write_regular(staging / "SHA256SUMS", sums)
        directory_fd = os.open(staging, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
        verify_bundle(staging)
        os.rename(staging, destination)
        parent_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try: os.fsync(parent_fd)
        finally: os.close(parent_fd)
        verify_bundle(destination)
        return destination
    except EvidenceError:
        raise
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        raise EvidenceError("atomic publication failed closed") from None


def _read_tree(bundle: Path, expected: set[str], before_completion: Callable[[], None] | None = None) -> dict[str, bytes]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise EvidenceError("evidence directory is missing or unsafe")
    directory_before = os.stat(bundle, follow_symlinks=False)
    directory_identity = (directory_before.st_dev, directory_before.st_ino)
    observed = {path.name for path in bundle.iterdir()}
    if observed != expected:
        raise EvidenceError("evidence file set is not exact")
    payloads: dict[str, bytes] = {}
    identities: dict[str, tuple[int, int, int, int]] = {}
    for name in sorted(expected):
        path = bundle / name
        try:
            before = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_FILE_BYTES:
                raise EvidenceError("evidence file is unsafe or oversized")
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(fd)
                chunks: list[bytes] = []
                remaining = _MAX_FILE_BYTES + 1
                while remaining:
                    chunk = os.read(fd, min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                data = b"".join(chunks)
                if len(data) > _MAX_FILE_BYTES:
                    raise EvidenceError("evidence file exceeds its byte bound")
            finally:
                os.close(fd)
            after = os.stat(path, follow_symlinks=False)
        except EvidenceError:
            raise
        except OSError:
            raise EvidenceError("evidence file changed during bounded read") from None
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if identity != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) or identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise EvidenceError("evidence file was replaced during validation")
        identities[name] = identity; payloads[name] = data
    if before_completion is not None:
        before_completion()
    if {path.name for path in bundle.iterdir()} != expected:
        raise EvidenceError("evidence tree changed during validation")
    directory_after = os.stat(bundle, follow_symlinks=False)
    if not stat.S_ISDIR(directory_after.st_mode) or directory_identity != (directory_after.st_dev, directory_after.st_ino):
        raise EvidenceError("evidence directory was replaced during validation")
    for name, identity in identities.items():
        current = os.stat(bundle / name, follow_symlinks=False)
        if not stat.S_ISREG(current.st_mode) or identity != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns):
            raise EvidenceError("evidence tree was replaced after validation")
    return payloads


def _read_manifest_only(bundle: Path) -> bytes:
    if bundle.is_symlink() or not bundle.is_dir():
        raise EvidenceError("evidence directory is missing or unsafe")
    path = bundle / "manifest.json"
    try:
        before = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_FILE_BYTES:
            raise EvidenceError("evidence manifest is unsafe or oversized")
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
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
        after = os.stat(path, follow_symlinks=False)
    except EvidenceError:
        raise
    except OSError:
        raise EvidenceError("evidence manifest changed during bounded read") from None
    identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    if len(payload) > _MAX_FILE_BYTES or identity != (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
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
    if value.get("promotion_status") != PROMOTION_STATUS or value.get("claim_exclusions") != list(CLAIM_EXCLUSIONS) or value.get("evidence_scope") != "kind_calico_boundary":
        raise EvidenceError("V3B-2 claim boundary is invalid")
    if type(value.get("content_identities")) is not dict or type(value.get("topology_attestation")) is not dict or type(value.get("policy_attestation")) is not dict:
        raise EvidenceError("V3B-2 public attestations have invalid exact types")
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
        if joins or value.get("foreign_profile_attestation", {}).get("unchanged") is not False:  # type: ignore[union-attr]
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
            or request.get("http_status") != status
            or proxy.get("upstream_status") != (status if attempted else None)
            or proxy.get("upstream_attempted") is not attempted
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
    if any(target.get("track") not in TRACKS for target in targets):
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
    bundle = Path(os.path.abspath(path))
    manifest = _parse_json(_read_manifest_only(bundle), "public manifest")
    schema = manifest.get("schema_version")
    try:
        family = dispatch_schema(manifest)
    except Exception:
        raise EvidenceError("bundle schema dispatch failed closed") from None
    if schema == PUBLIC_MANIFEST_SCHEMA:
        expected = set(PUBLIC_FILES)
        payloads = _read_tree(bundle, expected, before_completion=before_completion)
        _verify_sums(payloads, expected)
        return _verify_v3b2(payloads)
    if type(schema) is str and schema.startswith("kil.v3b1-public-manifest.") and family == schema:
        try:
            from tools.v3b1_local_envoy import (
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
            except Exception:
                continue
        if not accepted:
            raise EvidenceError("V3B-1 bundle failed its independent verifier")
        run_id = manifest.get("run_id", "")
        if type(run_id) is not str:
            raise EvidenceError("V3B-1 run ID is invalid")
        return VerifiedBundle("v3b1", run_id, str(manifest.get("bundle_class", "v3b1")), str(manifest.get("promotion_status", "not_promoted")), sha256(_canonical_bytes(manifest)).hexdigest())
    raise EvidenceError("bundle schema family is not implemented")
