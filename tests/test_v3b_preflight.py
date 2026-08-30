from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest

from kil.v3b_preflight import ProfileError, V3BProfile


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "deploy/kind/v3b-profile.json"


class V3BProfileTest(unittest.TestCase):
    def raw_profile(self) -> dict[str, object]:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

    def test_loads_the_closed_released_profile(self):
        profile = V3BProfile.load(PROFILE_PATH)

        self.assertEqual(profile.kind_version, "0.32.0")
        self.assertEqual(profile.kubernetes_version, "1.36.1")
        self.assertEqual(profile.envoy_version, "1.39.0")
        self.assertEqual(profile.cluster_name, "kil-v3-lab")
        self.assertEqual(profile.colima_profile, "kil-v3-lab")
        self.assertEqual(profile.evidence_scope, "local_envoy_boundary")
        self.assertEqual(profile.gateway_ports, (18080, 18081, 18082))

    def test_profile_is_frozen_and_slotted(self):
        profile = V3BProfile.load(PROFILE_PATH)

        with self.assertRaises(FrozenInstanceError):
            profile.kind_version = "latest"  # type: ignore[misc]
        self.assertFalse(hasattr(profile, "__dict__"))

    def test_rejects_unknown_profile_fields(self):
        raw = self.raw_profile()
        raw["validated"] = True

        with self.assertRaisesRegex(ProfileError, "unknown"):
            V3BProfile.from_mapping(raw)

    def test_rejects_missing_profile_fields(self):
        raw = self.raw_profile()
        del raw["envoy_version"]

        with self.assertRaisesRegex(ProfileError, "missing"):
            V3BProfile.from_mapping(raw)

    def test_rejects_json_type_coercion(self):
        raw = self.raw_profile()
        raw["docker_cli_version"] = 29.7

        with self.assertRaisesRegex(ProfileError, "docker_cli_version"):
            V3BProfile.from_mapping(raw)

    def test_refuses_any_other_cluster_or_colima_profile(self):
        for field in ("cluster_name", "colima_profile"):
            with self.subTest(field=field):
                raw = self.raw_profile()
                raw[field] = "default"
                with self.assertRaisesRegex(ProfileError, "kil-v3-lab"):
                    V3BProfile.from_mapping(raw)

    def test_requires_the_exact_digest_pinned_node_image(self):
        raw = self.raw_profile()
        raw["kind_node_image"] = "kindest/node:v1.36.1"

        with self.assertRaisesRegex(ProfileError, "kind_node_image"):
            V3BProfile.from_mapping(raw)

    def test_rejects_non_https_and_non_allowlisted_downloads(self):
        cases = (
            "http://github.com/kind",
            "https://example.invalid/kind",
            "https://github.com.evil.invalid/kind",
        )
        for value in cases:
            with self.subTest(value=value):
                raw = self.raw_profile()
                raw["kind_url"] = value
                with self.assertRaisesRegex(ProfileError, "kind_url"):
                    V3BProfile.from_mapping(raw)

    def test_rejects_a_different_asset_on_an_allowlisted_host(self):
        raw = self.raw_profile()
        raw["kind_url"] = "https://github.com/example/example/releases/kind"

        with self.assertRaisesRegex(ProfileError, "kind_url"):
            V3BProfile.from_mapping(raw)

    def test_rejects_invalid_url_ports_as_profile_errors(self):
        raw = self.raw_profile()
        raw["kind_url"] = "https://github.com:99999/kind"

        with self.assertRaisesRegex(ProfileError, "kind_url"):
            V3BProfile.from_mapping(raw)

    def test_rejects_boolean_duplicate_and_privileged_ports(self):
        cases = ([True, 18081, 18082], [18080, 18080, 18082], [80, 18081, 18082])
        for ports in cases:
            with self.subTest(ports=ports):
                raw = self.raw_profile()
                raw["gateway_ports"] = ports
                with self.assertRaisesRegex(ProfileError, "gateway_ports"):
                    V3BProfile.from_mapping(raw)

    def test_rejects_a_different_valid_port_set(self):
        raw = self.raw_profile()
        raw["gateway_ports"] = [19080, 19081, 19082]

        with self.assertRaisesRegex(ProfileError, "gateway_ports"):
            V3BProfile.from_mapping(raw)

    def test_load_rejects_non_object_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ProfileError, "object"):
                V3BProfile.load(path)


if __name__ == "__main__":
    unittest.main()
