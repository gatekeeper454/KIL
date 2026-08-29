import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReplayCliTest(unittest.TestCase):
    def test_cli_emits_the_first_modeled_integrity_checked_bundle(self):
        with TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/replay.py",
                    "--output",
                    directory,
                    "--implementation-version",
                    "test-commit",
                ],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": "src"},
                text=True,
                capture_output=True,
                check=True,
            )
            bundle = Path(completed.stdout.strip())
            manifest = json.loads(
                (bundle / "manifest.json").read_text(encoding="utf-8")
            )
            metrics = json.loads(
                (bundle / "metrics.json").read_text(encoding="utf-8")
            )

            self.assertTrue(bundle.is_dir())
            self.assertTrue((bundle / "SHA256SUMS").is_file())
            self.assertEqual(manifest["evidence_class"], "modeled")
            self.assertEqual(manifest["implementation_version"], "test-commit")
            self.assertEqual(manifest["scenario_id"], "hf-july-2026-eight-phase")
            self.assertEqual(metrics["event_count"], 8)
            self.assertEqual(metrics["baseline_permits"], 8)
            self.assertEqual(metrics["signed_state_only_denies"], 8)
            self.assertEqual(metrics["signed_plus_local_reduce_denies"], 8)
            self.assertNotIn("validated", manifest.values())

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
