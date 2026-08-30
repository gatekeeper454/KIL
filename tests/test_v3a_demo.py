import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
KTP_CITATION_URL = "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff"


class V3ADemoTest(unittest.TestCase):
    def test_demo_emits_visible_modeled_process_contract_bundle(self):
        with TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["PYTHONPATH"] = "src"
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/v3a_demo.py",
                    "--output",
                    directory,
                    "--implementation-version",
                    "test-commit",
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=True,
            )
            lines = completed.stdout.strip().splitlines()
            self.assertEqual(
                lines[:3],
                [
                    "credential_policy_baseline permit markers=1 proof=valid",
                    "signed_state_only permit markers=1 proof=valid",
                    "signed_plus_local_reduce deny markers=0 proof=valid",
                ],
            )
            self.assertTrue(lines[3].startswith("bundle "))
            bundle = Path(lines[3].removeprefix("bundle "))
            self.assertEqual(bundle.parent, Path(directory))

            manifest = json.loads(
                (bundle / "manifest.json").read_text(encoding="utf-8")
            )
            joins = tuple(
                json.loads(line)
                for line in (bundle / "joins.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            live = (bundle / "live.html").read_text(encoding="utf-8")
            summary = (bundle / "summary.md").read_text(encoding="utf-8")
            checksums = (bundle / "SHA256SUMS").read_text(encoding="utf-8")
            verification_key = json.loads(
                (bundle / "verification-key.json").read_text(encoding="utf-8")
            )
            signed_states = tuple(
                json.loads(line)
                for line in (bundle / "q-states.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )

            self.assertEqual(manifest["evidence_class"], "modeled")
            self.assertEqual(manifest["validation_scope"], "process_contract_only")
            self.assertEqual(manifest["implementation_version"], "test-commit")
            self.assertEqual(
                manifest["verification_key"], verification_key
            )
            self.assertEqual(verification_key["algorithm"], "Ed25519")
            self.assertRegex(
                verification_key["public_key_thumbprint"], r"^sha256:[a-f0-9]{64}$"
            )
            self.assertEqual(
                verification_key["provenance"],
                "deterministic_repository_fixture_bytes_range_32",
            )
            self.assertEqual(
                verification_key["assurance"], "software_level_1_lab"
            )
            self.assertFalse(verification_key["production_key"])
            self.assertEqual(verification_key["jwk"]["kty"], "OKP")
            self.assertEqual(verification_key["jwk"]["crv"], "Ed25519")
            self.assertRegex(verification_key["jwk"]["x"], r"^[A-Za-z0-9_-]{43}$")
            self.assertEqual(len(signed_states), 2)
            self.assertEqual(
                tuple(item["track"] for item in signed_states),
                ("signed_state_only", "signed_plus_local_reduce"),
            )
            self.assertTrue(
                all(len(item["compact_jws"].split(".")) == 3 for item in signed_states)
            )
            self.assertEqual(len(joins), 3)
            self.assertTrue(all(item["proof_valid"] for item in joins))
            self.assertEqual(joins[2]["track"], "signed_plus_local_reduce")
            self.assertEqual(joins[2]["marker_count"], 0)
            self.assertIn("credential_policy_baseline", live)
            self.assertIn("signed_state_only", live)
            self.assertIn("signed_plus_local_reduce", live)
            self.assertIn("PERMIT / PERMIT / DENY", live)
            self.assertIn("<img", live)
            self.assertIn("v3-envoy-live-validation.svg", live)
            self.assertIn(
                "This V3A process-contract demonstration is modeled, not a "
                "validated cluster run.",
                summary,
            )
            self.assertIn(KTP_CITATION_URL, summary)
            for name in (
                "manifest.json",
                "decisions.jsonl",
                "joins.jsonl",
                "targets.jsonl",
                "summary.md",
                "live.html",
                "verification-key.json",
                "q-states.jsonl",
            ):
                self.assertIn(f"  {name}\n", checksums)

            verification = subprocess.run(
                ["shasum", "-a", "256", "-c", "SHA256SUMS"],
                cwd=bundle,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(verification.stdout.count("OK"), 8)


if __name__ == "__main__":
    unittest.main()
