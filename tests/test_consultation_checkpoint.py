from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "docs/checkpoints/2026-08-24-specialist-consultation.md"
ARCHITECTURE = ROOT / "docs/design-drafts/hybrid-two-timescale-architecture.html"
CITATION_URL = "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff"


class ConsultationCheckpointTest(unittest.TestCase):
    def test_checkpoint_preserves_the_pause_and_resume_contract(self):
        self.assertTrue(CHECKPOINT.is_file(), "the consultation checkpoint must exist")
        text = CHECKPOINT.read_text(encoding="utf-8")
        for marker in (
            "Paused for specialist consultation",
            "Decisions already accepted",
            "Design awaiting approval",
            "Questions for the specialist",
            "Exact resume point",
            "Architecture Section 1",
        ):
            self.assertIn(marker, text)
        self.assertIn(CITATION_URL, text)

    def test_architecture_visual_is_saved_with_its_governance_boundary(self):
        self.assertTrue(ARCHITECTURE.is_file(), "the architecture visual must be saved")
        text = ARCHITECTURE.read_text(encoding="utf-8")
        self.assertIn("Hybrid two-timescale enforcement", text)
        self.assertIn("Authoritative signed-state loop", text)
        self.assertIn("Fast enforcement loop", text)
        self.assertIn("Execution rails—not timescales", text)
        self.assertIn("Local reducing-only overlay", text)
        self.assertIn("Q can reduce or withhold authority", text)
        self.assertIn(CITATION_URL, text)


if __name__ == "__main__":
    unittest.main()
