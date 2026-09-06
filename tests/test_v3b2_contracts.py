import copy
from dataclasses import FrozenInstanceError, fields
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from kil.v3b2_contracts import (
    APPLICATION_NAMESPACES,
    CAMPAIGN_FIELDS,
    CAMPAIGN_SCHEMA,
    JOURNAL_FIELDS,
    JOURNAL_SCHEMA,
    LAB_IDENTITY,
    PRIVATE_MANIFEST_FIELDS,
    PRIVATE_MANIFEST_SCHEMA,
    PROFILE_FIELDS,
    PROFILE_SCHEMA,
    PUBLIC_MANIFEST_FIELDS,
    PUBLIC_MANIFEST_SCHEMA,
    SCHEMA_FIELDS,
    TRACK_NAMESPACES,
    TRACKS,
    NOMINAL_REQUEST_ID,
    SchemaError,
    V3B2Profile,
    dispatch_schema,
    require_closed_object,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "deploy/kind/v3b2-profile.json"
CALICO_PATH = ROOT / "deploy/kind/calico-v3.32.0.yaml"

EXPECTED_PROFILE_FIELDS = frozenset(
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
EXPECTED_JOURNAL_FIELDS = frozenset(
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
EXPECTED_PRIVATE_MANIFEST_FIELDS = frozenset(
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
EXPECTED_PUBLIC_MANIFEST_FIELDS = frozenset(
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
EXPECTED_CAMPAIGN_FIELDS = frozenset(
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
EXPECTED_PROFILE_DOCUMENT = {
    "schema_version": "kil.v3b2-profile.v1",
    "host_os": "darwin",
    "host_arch": "arm64",
    "colima_version": "0.10.3",
    "colima_profile": "kil-v3-lab",
    "lima_version": "2.2.0",
    "docker_cli_version": "29.7.2",
    "kind_version": "0.32.0",
    "kubernetes_version": "1.36.1",
    "kind_node_image": (
        "kindest/node:v1.36.1@sha256:"
        "3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5"
    ),
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
    "calico_images": {
        "cni": (
            "quay.io/calico/cni@sha256:"
            "1cfc6aa9c4dad3575fdf36b78185fd7d68bcd4acc95778f8342be4fb6a851a14"
        ),
        "node": (
            "quay.io/calico/node@sha256:"
            "f4fafd8ba641d96c5a91b01e5a519117d77d55dee789a3562ba3ad4aa125b36a"
        ),
        "kube_controllers": (
            "quay.io/calico/kube-controllers@sha256:"
            "adf0ac895796d21bca5383bc81c4cd2614be3a4308085b47857d7999f4cc2b1f"
        ),
    },
    "cluster_name": "kil-v3-lab",
    "pod_subnet": "10.244.0.0/16",
    "service_subnet": "10.96.0.0/16",
    "system_namespaces": [
        "default",
        "kube-node-lease",
        "kube-public",
        "kube-system",
        "local-path-storage",
    ],
    "application_namespaces": [
        "kil-v3-baseline",
        "kil-v3-signed",
        "kil-v3-local-reduce",
    ],
    "evidence_scope": "kind_calico_boundary",
}


def valid_profile() -> dict[str, object]:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def valid_constructor_values() -> dict[str, object]:
    values = copy.deepcopy(EXPECTED_PROFILE_DOCUMENT)
    images = values["calico_images"]
    assert isinstance(images, dict)
    values["calico_images"] = tuple(images.items())
    values["system_namespaces"] = tuple(values["system_namespaces"])
    values["application_namespaces"] = tuple(values["application_namespaces"])
    return values


class V3B2ProfileTests(unittest.TestCase):
    def test_profile_document_matches_an_independent_full_literal_oracle(self) -> None:
        self.assertEqual(valid_profile(), EXPECTED_PROFILE_DOCUMENT)

    def test_public_constants_and_profile_field_closure(self) -> None:
        self.assertEqual(LAB_IDENTITY, "kil-v3-lab")
        self.assertEqual(
            TRACKS,
            (
                "credential_policy_baseline",
                "signed_state_only",
                "signed_plus_local_reduce",
            ),
        )
        self.assertEqual(
            APPLICATION_NAMESPACES,
            ("kil-v3-baseline", "kil-v3-signed", "kil-v3-local-reduce"),
        )
        self.assertEqual(
            TRACK_NAMESPACES,
            tuple(zip(TRACKS, APPLICATION_NAMESPACES, strict=True)),
        )
        self.assertEqual(NOMINAL_REQUEST_ID, "v3b1-central-request")
        self.assertEqual(PROFILE_SCHEMA, "kil.v3b2-profile.v1")
        self.assertEqual(JOURNAL_SCHEMA, "kil.v3b2-journal.v1")
        self.assertEqual(PRIVATE_MANIFEST_SCHEMA, "kil.v3b2-private-manifest.v1")
        self.assertEqual(PUBLIC_MANIFEST_SCHEMA, "kil.v3b2-public-manifest.v1")
        self.assertEqual(CAMPAIGN_SCHEMA, "kil.v3b2-campaign.v1")
        self.assertEqual(PROFILE_FIELDS, EXPECTED_PROFILE_FIELDS)
        self.assertEqual(JOURNAL_FIELDS, EXPECTED_JOURNAL_FIELDS)
        self.assertEqual(PRIVATE_MANIFEST_FIELDS, EXPECTED_PRIVATE_MANIFEST_FIELDS)
        self.assertEqual(PUBLIC_MANIFEST_FIELDS, EXPECTED_PUBLIC_MANIFEST_FIELDS)
        self.assertEqual(CAMPAIGN_FIELDS, EXPECTED_CAMPAIGN_FIELDS)
        self.assertEqual(set(valid_profile()), EXPECTED_PROFILE_FIELDS)
        self.assertEqual(
            {field.name for field in fields(V3B2Profile)},
            EXPECTED_PROFILE_FIELDS,
        )
        self.assertEqual(
            SCHEMA_FIELDS,
            {
                PROFILE_SCHEMA: EXPECTED_PROFILE_FIELDS,
                JOURNAL_SCHEMA: EXPECTED_JOURNAL_FIELDS,
                PRIVATE_MANIFEST_SCHEMA: EXPECTED_PRIVATE_MANIFEST_FIELDS,
                PUBLIC_MANIFEST_SCHEMA: EXPECTED_PUBLIC_MANIFEST_FIELDS,
                CAMPAIGN_SCHEMA: EXPECTED_CAMPAIGN_FIELDS,
            },
        )

    def test_vendored_calico_reconstructs_the_approved_upstream_bytes(self) -> None:
        vendored = CALICO_PATH.read_bytes()
        self.assertEqual(
            hashlib.sha256(vendored).hexdigest(),
            "ac5ab7451dda57cfbf47d584ee901b896b1a9ff388d95b6f01b59f1e1130fdfa",
        )
        substitutions = (
            (
                b"quay.io/calico/cni@sha256:"
                b"1cfc6aa9c4dad3575fdf36b78185fd7d68bcd4acc95778f8342be4fb6a851a14",
                b"quay.io/calico/cni:v3.32.0",
                2,
            ),
            (
                b"quay.io/calico/node@sha256:"
                b"f4fafd8ba641d96c5a91b01e5a519117d77d55dee789a3562ba3ad4aa125b36a",
                b"quay.io/calico/node:v3.32.0",
                2,
            ),
            (
                b"quay.io/calico/kube-controllers@sha256:"
                b"adf0ac895796d21bca5383bc81c4cd2614be3a4308085b47857d7999f4cc2b1f",
                b"quay.io/calico/kube-controllers:v3.32.0",
                1,
            ),
        )
        expected_images = {digest for digest, _, _ in substitutions}
        image_references = re.findall(rb"(?m)^\s*image:\s+(\S+)\s*$", vendored)
        self.assertEqual(set(image_references), expected_images)

        reconstructed = vendored
        for digest_reference, tag_reference, count in substitutions:
            self.assertEqual(vendored.count(digest_reference), count)
            self.assertNotIn(tag_reference, vendored)
            reconstructed = reconstructed.replace(digest_reference, tag_reference)
        self.assertEqual(sum(vendored.count(item) for item in expected_images), 5)
        self.assertEqual(len(reconstructed), 349123)
        self.assertEqual(
            hashlib.sha256(reconstructed).hexdigest(),
            "bccabc607685551db918f66da724893eca3e69a50c5a3e3077029b02dbab8d35",
        )

    def test_loads_the_pinned_v3b2_profile(self) -> None:
        profile = V3B2Profile.load(PROFILE_PATH)
        self.assertEqual(profile.schema_version, PROFILE_SCHEMA)
        self.assertEqual(profile.colima_profile, LAB_IDENTITY)
        self.assertEqual(profile.cluster_name, LAB_IDENTITY)
        self.assertEqual(profile.evidence_scope, "kind_calico_boundary")
        self.assertEqual(profile.application_namespaces, APPLICATION_NAMESPACES)
        self.assertEqual(
            profile.calico_manifest_sha256,
            "ac5ab7451dda57cfbf47d584ee901b896b1a9ff388d95b6f01b59f1e1130fdfa",
        )
        self.assertIsInstance(profile.system_namespaces, tuple)
        self.assertIsInstance(profile.calico_images, tuple)

    def test_profile_is_frozen_and_slotted(self) -> None:
        profile = V3B2Profile.load(PROFILE_PATH)
        with self.assertRaises(FrozenInstanceError):
            profile.cluster_name = "changed"  # type: ignore[misc]
        self.assertFalse(hasattr(profile, "__dict__"))

    def test_valid_direct_construction_is_deeply_immutable(self) -> None:
        profile = V3B2Profile(**valid_constructor_values())  # type: ignore[arg-type]
        self.assertEqual(profile.application_namespaces, APPLICATION_NAMESPACES)
        self.assertIsInstance(profile.calico_images, tuple)
        self.assertTrue(all(isinstance(item, tuple) for item in profile.calico_images))
        with self.assertRaises(TypeError):
            profile.calico_images[0][0] = "changed"  # type: ignore[index]

    def test_direct_construction_rejects_noncanonical_values(self) -> None:
        cases = (
            ("foreign-colima", "colima_profile", "foreign"),
            ("foreign-cluster", "cluster_name", "foreign"),
            ("wrong-scalar-type", "host_arch", 64),
            ("mutable-node-image", "kind_node_image", "kindest/node:v1.36.1"),
            (
                "reordered-app-namespaces",
                "application_namespaces",
                (
                    "kil-v3-signed",
                    "kil-v3-baseline",
                    "kil-v3-local-reduce",
                ),
            ),
            (
                "wrong-system-namespaces",
                "system_namespaces",
                ("default", "kube-system"),
            ),
            (
                "list-app-namespaces",
                "application_namespaces",
                list(APPLICATION_NAMESPACES),
            ),
            (
                "list-system-namespaces",
                "system_namespaces",
                list(EXPECTED_PROFILE_DOCUMENT["system_namespaces"]),
            ),
            (
                "dict-images",
                "calico_images",
                copy.deepcopy(EXPECTED_PROFILE_DOCUMENT["calico_images"]),
            ),
        )
        for label, name, replacement in cases:
            with self.subTest(label=label):
                values = valid_constructor_values()
                values[name] = replacement
                with self.assertRaises(SchemaError):
                    V3B2Profile(**values)  # type: ignore[arg-type]

        values = valid_constructor_values()
        images = list(values["calico_images"])
        images[0] = ("cni", "quay.io/calico/cni:v3.32.0")
        values["calico_images"] = tuple(images)
        with self.assertRaises(SchemaError):
            V3B2Profile(**values)  # type: ignore[arg-type]

    def test_rejects_unknown_missing_and_cross_generation_fields(self) -> None:
        for label, mutation in (
            ("unknown", lambda value: value.update(extra="no")),
            ("missing", lambda value: value.pop("host_os")),
            (
                "cross-generation",
                lambda value: value.update(schema_version="kil.v3b-profile.v2"),
            ),
        ):
            with self.subTest(label=label):
                value = valid_profile()
                mutation(value)
                with self.assertRaises(SchemaError):
                    V3B2Profile.from_mapping(value)

    def test_rejects_non_objects_and_type_coercion(self) -> None:
        for value in ([], (), "profile", None):
            with self.subTest(value=value):
                with self.assertRaises(SchemaError):
                    V3B2Profile.from_mapping(value)  # type: ignore[arg-type]
        for field_name, invalid in (
            ("host_arch", 64),
            ("kind_version", True),
            ("system_namespaces", "default"),
            ("system_namespaces", ["default", 1]),
            ("application_namespaces", tuple(APPLICATION_NAMESPACES)),
            ("calico_images", []),
            ("calico_images", {"cni": True, "node": "x", "kube_controllers": "y"}),
        ):
            with self.subTest(field=field_name, invalid=invalid):
                value = valid_profile()
                value[field_name] = invalid
                with self.assertRaises(SchemaError):
                    V3B2Profile.from_mapping(value)

    def test_rejects_identity_namespace_cidr_path_and_image_drift(self) -> None:
        changes = (
            ("colima_profile", "foreign"),
            ("cluster_name", "foreign"),
            (
                "application_namespaces",
                ["kil-v3-signed", "kil-v3-baseline", "kil-v3-local-reduce"],
            ),
            ("system_namespaces", ["default", "kube-system", "calico-system"]),
            ("pod_subnet", "10.244.0.1/16"),
            ("service_subnet", "10.96.0.0/12"),
            ("kind_node_image", "kindest/node:v1.36.1"),
            ("envoy_image", "docker.io/envoyproxy/envoy:latest"),
            ("calico_manifest_path", "/tmp/calico.yaml"),
            ("calico_manifest_path", "deploy/kind/../calico.yaml"),
        )
        for name, replacement in changes:
            with self.subTest(name=name, replacement=replacement):
                value = valid_profile()
                value[name] = replacement
                with self.assertRaises(SchemaError):
                    V3B2Profile.from_mapping(value)

        for image_name in ("cni", "node", "kube_controllers"):
            with self.subTest(image=image_name):
                value = valid_profile()
                images = copy.deepcopy(value["calico_images"])
                assert isinstance(images, dict)
                images[image_name] = (
                    str(images[image_name]).split("@", 1)[0] + ":v3.32.0"
                )
                value["calico_images"] = images
                with self.assertRaises(SchemaError):
                    V3B2Profile.from_mapping(value)

    def test_load_rejects_duplicate_nonobject_and_invalid_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            raw = PROFILE_PATH.read_text(encoding="utf-8")
            duplicate.write_text(raw.replace("{", '{"host_os":"darwin",', 1))
            nonobject = root / "nonobject.json"
            nonobject.write_text("[]", encoding="utf-8")
            malformed = root / "malformed.json"
            malformed.write_bytes(b"{\xff}")
            for path in (duplicate, nonobject, malformed):
                with self.subTest(path=path.name):
                    with self.assertRaises(SchemaError):
                        V3B2Profile.load(path)

    def test_load_is_bounded_no_follow_and_regular_file_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            target.write_text(
                PROFILE_PATH.read_text(encoding="utf-8"), encoding="utf-8"
            )
            symlink = root / "link.json"
            symlink.symlink_to(target)
            for path in (symlink, root):
                with self.subTest(path=path.name):
                    with self.assertRaises(SchemaError):
                        V3B2Profile.load(path)

    def test_load_accepts_exactly_64_kib_but_rejects_one_byte_more(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            at_limit = root / "at-limit.json"
            at_limit.write_bytes(b" " * (64 * 1024 - 1) + b"[")
            self.assertEqual(at_limit.stat().st_size, 64 * 1024)
            with self.assertRaises(SchemaError) as malformed:
                V3B2Profile.load(at_limit)
            self.assertIn("cannot decode", str(malformed.exception))
            self.assertNotIn("exceeds 64 KiB", str(malformed.exception))

            oversized = root / "oversized.json"
            oversized.write_bytes(b" " * (64 * 1024 + 1))
            with self.assertRaisesRegex(SchemaError, "exceeds 64 KiB"):
                V3B2Profile.load(oversized)

    def test_load_rejects_path_replacement_between_inspection_and_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "profile.json"
            replacement = root / "replacement.json"
            content = PROFILE_PATH.read_text(encoding="utf-8")
            path.write_text(content, encoding="utf-8")
            replacement.write_text(content, encoding="utf-8")
            original_open = os.open

            def replace_then_open(candidate: object, flags: int) -> int:
                replacement.replace(path)
                return original_open(candidate, flags)

            with mock.patch(
                "kil.v3b2_contracts.os.open", side_effect=replace_then_open
            ):
                with self.assertRaises(SchemaError):
                    V3B2Profile.load(path)


class SchemaDispatchTests(unittest.TestCase):
    def test_require_closed_object_returns_a_dict_for_exact_keys(self) -> None:
        value = {"schema_version": "example", "value": 1}
        self.assertEqual(
            require_closed_object(
                "example", value, frozenset({"schema_version", "value"})
            ),
            value,
        )
        for invalid in (
            [value],
            {"schema_version": "example"},
            {"schema_version": "example", "value": 1, "extra": 2},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(SchemaError):
                    require_closed_object(
                        "example",
                        invalid,
                        frozenset({"schema_version", "value"}),
                    )

    def test_schema_fields_mapping_is_immutable(self) -> None:
        with self.assertRaises(TypeError):
            SCHEMA_FIELDS["new"] = frozenset()  # type: ignore[index]

    def test_dispatches_each_exact_v3b2_schema(self) -> None:
        profile = valid_profile()
        self.assertEqual(dispatch_schema(profile), PROFILE_SCHEMA)
        for schema, field_set in (
            (JOURNAL_SCHEMA, JOURNAL_FIELDS),
            (PRIVATE_MANIFEST_SCHEMA, PRIVATE_MANIFEST_FIELDS),
            (PUBLIC_MANIFEST_SCHEMA, PUBLIC_MANIFEST_FIELDS),
        ):
            value = {name: None for name in field_set}
            value["schema_version"] = schema
            with self.subTest(schema=schema):
                self.assertEqual(dispatch_schema(value), schema)

    def test_dispatch_preserves_v3b1_independence(self) -> None:
        schema = "kil.v3b1-driver-result.v1"
        self.assertEqual(dispatch_schema({"schema_version": schema}), schema)

    def test_dispatch_rejects_malformed_and_unknown_v3b1_like_schemas(self) -> None:
        for schema in (
            "kil.v3b1-.v",
            "kil.v3b1-not-a-real-schema.v999",
            "kil.v3b1-public-manifest.v999",
        ):
            with self.subTest(schema=schema):
                with self.assertRaises(SchemaError):
                    dispatch_schema({"schema_version": schema})

    def test_profile_dispatch_runs_the_exact_profile_validator(self) -> None:
        value = valid_profile()
        value["cluster_name"] = "foreign"
        with self.assertRaises(SchemaError):
            dispatch_schema(value)

    def test_dispatch_rejects_invalid_hybrid_and_campaign_schemas(self) -> None:
        for value in (
            {},
            {"schema_version": 1},
            {"schema_version": "kil.unknown.v1"},
            {
                "schema_version": PROFILE_SCHEMA,
                **{
                    name: None
                    for name in JOURNAL_FIELDS - {"schema_version"}
                },
            },
        ):
            with self.subTest(value=value):
                with self.assertRaises(SchemaError):
                    dispatch_schema(value)

        campaign = {name: None for name in EXPECTED_CAMPAIGN_FIELDS}
        campaign["schema_version"] = CAMPAIGN_SCHEMA
        with self.assertRaisesRegex(SchemaError, "campaign_not_implemented"):
            dispatch_schema(campaign)

        missing = dict(campaign)
        missing.pop("coverage")
        extra = {**campaign, "unexpected": None}
        for label, invalid in (("missing", missing), ("extra", extra)):
            with self.subTest(label=label):
                with self.assertRaises(SchemaError) as raised:
                    dispatch_schema(invalid)
                self.assertNotIn("campaign_not_implemented", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
