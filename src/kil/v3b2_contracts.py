"""Closed schemas and immutable profile for the V3B-2a Kind/Calico boundary."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
from types import MappingProxyType
from typing import Mapping


LAB_IDENTITY = "kil-v3-lab"
TRACKS = (
    "credential_policy_baseline",
    "signed_state_only",
    "signed_plus_local_reduce",
)
APPLICATION_NAMESPACES = (
    "kil-v3-baseline",
    "kil-v3-signed",
    "kil-v3-local-reduce",
)
TRACK_NAMESPACES = tuple(zip(TRACKS, APPLICATION_NAMESPACES, strict=True))
NOMINAL_REQUEST_ID = "v3b1-central-request"

PROFILE_SCHEMA = "kil.v3b2-profile.v1"
JOURNAL_SCHEMA = "kil.v3b2-journal.v1"
PRIVATE_MANIFEST_SCHEMA = "kil.v3b2-private-manifest.v1"
PUBLIC_MANIFEST_SCHEMA = "kil.v3b2-public-manifest.v1"
CAMPAIGN_SCHEMA = "kil.v3b2-campaign.v1"

PROFILE_FIELDS = frozenset(
    {
        "schema_version",
        "host_os",
        "host_arch",
        "colima_version",
        "colima_profile",
        "lima_version",
        "docker_cli_version",
        "kind_version",
        "kubernetes_version",
        "kind_node_image",
        "kubectl_version",
        "envoy_image",
        "calico_version",
        "calico_upstream_url",
        "calico_upstream_sha256",
        "calico_manifest_path",
        "calico_manifest_sha256",
        "calico_images",
        "cluster_name",
        "pod_subnet",
        "service_subnet",
        "system_namespaces",
        "application_namespaces",
        "evidence_scope",
    }
)
JOURNAL_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "execution_nonce",
        "source_commit",
        "profile_sha256",
        "phase",
        "global_context_before",
        "foreign_profiles_before",
        "expected_objects",
        "owned_identity",
        "events",
    }
)
PRIVATE_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "execution_nonce",
        "source_commit",
        "profile_sha256",
        "tool_identities",
        "content_identities",
        "expected_topology",
        "expected_policy_graph",
        "request_cases",
        "runtime_identities",
        "source_attestations",
        "foreign_profiles_before",
        "global_context_before",
    }
)
PUBLIC_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "source_commit",
        "profile_sha256",
        "evidence_scope",
        "result_class",
        "promotion_status",
        "content_identities",
        "topology_attestation",
        "policy_attestation",
        "request_results",
        "semantic_joins",
        "source_attestations",
        "foreign_profile_attestation",
        "global_context_unchanged",
        "owned_teardown",
        "claim_exclusions",
        "public_commitment_sha256",
    }
)
CAMPAIGN_FIELDS = frozenset(
    {
        "schema_version",
        "source_commit",
        "case_contract_sha256",
        "cases",
        "run_bundles",
        "coverage",
        "duplicate_case_ids",
        "omitted_case_ids",
        "promotion_status",
        "claim_exclusions",
        "public_commitment_sha256",
    }
)
SCHEMA_FIELDS = MappingProxyType(
    {
        PROFILE_SCHEMA: PROFILE_FIELDS,
        JOURNAL_SCHEMA: JOURNAL_FIELDS,
        PRIVATE_MANIFEST_SCHEMA: PRIVATE_MANIFEST_FIELDS,
        PUBLIC_MANIFEST_SCHEMA: PUBLIC_MANIFEST_FIELDS,
        CAMPAIGN_SCHEMA: CAMPAIGN_FIELDS,
    }
)

_MAX_PROFILE_BYTES = 64 * 1024
_V3B1_VERIFIER_SCHEMAS = frozenset(
    {
        "kil.v3b1-manifest.v1",
        "kil.v3b1-manifest.v2",
        "kil.v3b1-manifest.v3",
        "kil.v3b1-public-manifest.v1",
        "kil.v3b1-public-manifest.v2",
        "kil.v3b1-public-manifest.v3",
        "kil.v3b1-driver-result.v1",
    }
)
_SYSTEM_NAMESPACES = (
    "default",
    "kube-node-lease",
    "kube-public",
    "kube-system",
    "local-path-storage",
)
_CALICO_IMAGES = (
    (
        "cni",
        "quay.io/calico/cni@sha256:"
        "1cfc6aa9c4dad3575fdf36b78185fd7d68bcd4acc95778f8342be4fb6a851a14",
    ),
    (
        "node",
        "quay.io/calico/node@sha256:"
        "f4fafd8ba641d96c5a91b01e5a519117d77d55dee789a3562ba3ad4aa125b36a",
    ),
    (
        "kube_controllers",
        "quay.io/calico/kube-controllers@sha256:"
        "adf0ac895796d21bca5383bc81c4cd2614be3a4308085b47857d7999f4cc2b1f",
    ),
)

_EXACT_SCALARS = {
    "schema_version": PROFILE_SCHEMA,
    "host_os": "darwin",
    "host_arch": "arm64",
    "colima_version": "0.10.3",
    "colima_profile": LAB_IDENTITY,
    "lima_version": "2.2.0",
    "docker_cli_version": "29.7.2",
    "kind_version": "0.32.0",
    "kubernetes_version": "1.36.1",
    "kind_node_image": "kindest/node:v1.36.1@sha256:"
    "3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5",
    "kubectl_version": "1.36.3",
    "envoy_image": "docker.io/envoyproxy/envoy:v1.39.1",
    "calico_version": "3.32.0",
    "calico_upstream_url": (
        "https://raw.githubusercontent.com/projectcalico/calico/"
        "v3.32.0/manifests/calico.yaml"
    ),
    "calico_upstream_sha256": (
        "bccabc607685551db918f66da724893eca3e69a50c5a3e3077029b02dbab8d35"
    ),
    "calico_manifest_path": "deploy/kind/calico-v3.32.0.yaml",
    "calico_manifest_sha256": (
        "ac5ab7451dda57cfbf47d584ee901b896b1a9ff388d95b6f01b59f1e1130fdfa"
    ),
    "cluster_name": LAB_IDENTITY,
    "pod_subnet": "10.244.0.0/16",
    "service_subnet": "10.96.0.0/16",
    "evidence_scope": "kind_calico_boundary",
}


class SchemaError(ValueError):
    """Raised when bytes do not implement a closed V3B-2a schema."""


def require_closed_object(
    label: str, value: object, expected_fields: frozenset[str]
) -> dict[str, object]:
    """Return an exact-key plain JSON object, rejecting open or missing fields."""

    if type(value) is not dict:
        raise SchemaError(f"{label} must be a JSON object")
    if any(type(key) is not str for key in value):
        raise SchemaError(f"{label} field names must be strings")
    actual = set(value)
    unknown = actual - expected_fields
    missing = expected_fields - actual
    if unknown:
        raise SchemaError(f"unknown {label} fields: {sorted(unknown)}")
    if missing:
        raise SchemaError(f"missing {label} fields: {sorted(missing)}")
    return value


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SchemaError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _read_bounded_regular_file(path: Path) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        inspected = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(inspected.st_mode):
            raise SchemaError("V3B-2 profile must be a non-symlink regular file")
        descriptor = os.open(path, flags)
    except OSError as error:
        raise SchemaError(f"cannot open V3B-2 profile safely: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SchemaError("V3B-2 profile must be a regular file")
        if (metadata.st_dev, metadata.st_ino) != (inspected.st_dev, inspected.st_ino):
            raise SchemaError("V3B-2 profile was replaced during safe open")
        if metadata.st_size > _MAX_PROFILE_BYTES:
            raise SchemaError("V3B-2 profile exceeds 64 KiB")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            content = stream.read(_MAX_PROFILE_BYTES + 1)
        if len(content) > _MAX_PROFILE_BYTES:
            raise SchemaError("V3B-2 profile exceeds 64 KiB")
        return content
    except OSError as error:
        raise SchemaError(f"cannot read V3B-2 profile safely: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class V3B2Profile:
    schema_version: str
    host_os: str
    host_arch: str
    colima_version: str
    colima_profile: str
    lima_version: str
    docker_cli_version: str
    kind_version: str
    kubernetes_version: str
    kind_node_image: str
    kubectl_version: str
    envoy_image: str
    calico_version: str
    calico_upstream_url: str
    calico_upstream_sha256: str
    calico_manifest_path: str
    calico_manifest_sha256: str
    calico_images: tuple[tuple[str, str], ...]
    cluster_name: str
    pod_subnet: str
    service_subnet: str
    system_namespaces: tuple[str, ...]
    application_namespaces: tuple[str, ...]
    evidence_scope: str

    @classmethod
    def load(cls, path: Path) -> V3B2Profile:
        try:
            text = _read_bounded_regular_file(path).decode("utf-8", errors="strict")
            value = json.loads(text, object_pairs_hook=_closed_json_object)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise SchemaError(f"cannot decode V3B-2 profile: {error}") from error
        return cls.from_mapping(value)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> V3B2Profile:
        value = require_closed_object("V3B-2 profile", mapping, PROFILE_FIELDS)

        for name, expected in _EXACT_SCALARS.items():
            actual = value[name]
            if type(actual) is not str or actual != expected:
                raise SchemaError(f"{name} must be exactly {expected}")

        system_namespaces = value["system_namespaces"]
        application_namespaces = value["application_namespaces"]
        if type(system_namespaces) is not list or any(
            type(item) is not str for item in system_namespaces
        ):
            raise SchemaError("system_namespaces must be a JSON string array")
        if tuple(system_namespaces) != _SYSTEM_NAMESPACES:
            raise SchemaError("system_namespaces must be the exact approved sequence")
        if type(application_namespaces) is not list or any(
            type(item) is not str for item in application_namespaces
        ):
            raise SchemaError("application_namespaces must be a JSON string array")
        if tuple(application_namespaces) != APPLICATION_NAMESPACES:
            raise SchemaError(
                "application_namespaces must be the exact approved sequence"
            )

        images = require_closed_object(
            "calico_images",
            value["calico_images"],
            frozenset(name for name, _ in _CALICO_IMAGES),
        )
        for name, expected in _CALICO_IMAGES:
            actual = images[name]
            if type(actual) is not str or actual != expected:
                raise SchemaError(f"calico_images.{name} must be digest-pinned")

        values = dict(value)
        values["calico_images"] = _CALICO_IMAGES
        values["system_namespaces"] = tuple(system_namespaces)
        values["application_namespaces"] = tuple(application_namespaces)
        return cls(**values)  # type: ignore[arg-type]


def dispatch_schema(value: object) -> str:
    """Classify closed V3B-2a objects without coupling to the V3B-1 controller."""

    if type(value) is not dict:
        raise SchemaError("schema-bearing value must be a JSON object")
    schema = value.get("schema_version")
    if type(schema) is not str:
        raise SchemaError("schema_version must be present and a string")
    if schema in _V3B1_VERIFIER_SCHEMAS:
        return schema
    if schema == CAMPAIGN_SCHEMA:
        require_closed_object(schema, value, CAMPAIGN_FIELDS)
        raise SchemaError("campaign_not_implemented")
    expected_fields = SCHEMA_FIELDS.get(schema)
    if expected_fields is None:
        raise SchemaError(f"unknown schema_version: {schema}")
    if schema == PROFILE_SCHEMA:
        V3B2Profile.from_mapping(value)
    else:
        require_closed_object(schema, value, expected_fields)
    return schema
