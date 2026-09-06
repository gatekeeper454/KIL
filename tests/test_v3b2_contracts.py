import copy
from dataclasses import FrozenInstanceError, fields
import json
import os
from pathlib import Path
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


def valid_profile() -> dict[str, object]:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


class V3B2ProfileTests(unittest.TestCase):
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
        self.assertEqual(set(valid_profile()), PROFILE_FIELDS)
        self.assertEqual({field.name for field in fields(V3B2Profile)}, PROFILE_FIELDS)
        self.assertEqual(
            SCHEMA_FIELDS,
            {
                PROFILE_SCHEMA: PROFILE_FIELDS,
                JOURNAL_SCHEMA: JOURNAL_FIELDS,
                PRIVATE_MANIFEST_SCHEMA: PRIVATE_MANIFEST_FIELDS,
                PUBLIC_MANIFEST_SCHEMA: PUBLIC_MANIFEST_FIELDS,
                CAMPAIGN_SCHEMA: CAMPAIGN_FIELDS,
            },
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
            oversized = root / "oversized.json"
            oversized.write_bytes(b" " * (64 * 1024 + 1))
            for path in (symlink, oversized, root):
                with self.subTest(path=path.name):
                    with self.assertRaises(SchemaError):
                        V3B2Profile.load(path)

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

        with self.assertRaisesRegex(SchemaError, "campaign_not_implemented"):
            dispatch_schema({"schema_version": CAMPAIGN_SCHEMA})


if __name__ == "__main__":
    unittest.main()
