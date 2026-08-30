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

            self.assertEqual(manifest["evidence_class"], "modeled")
            self.assertEqual(manifest["validation_scope"], "process_contract_only")
            self.assertEqual(manifest["implementation_version"], "test-commit")
            self.assertEqual(len(joins), 3)
            self.assertTrue(all(item["proof_valid"] for item in joins))
            self.assertEqual(joins[2]["track"], "signed_plus_local_reduce")
            self.assertEqual(joins[2]["marker_count"], 0)
            self.assertIn("credential_policy_baseline", live)
            self.assertIn("signed_state_only", live)
            self.assertIn("signed_plus_local_reduce", live)
            self.assertIn("PERMIT / PERMIT / DENY", live)
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
            ):
                self.assertIn(f"  {name}\n", checksums)

            verification = subprocess.run(
                ["shasum", "-a", "256", "-c", "SHA256SUMS"],
                cwd=bundle,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(verification.stdout.count("OK"), 6)


if __name__ == "__main__":
    unittest.main()
