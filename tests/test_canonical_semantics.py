from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "docs/paper/kinetic-infrastructure.md"
ARCHITECTURE = ROOT / "docs/design-drafts/hybrid-two-timescale-architecture.html"


class CanonicalSemanticsTest(unittest.TestCase):
    def test_paper_uses_corrected_model_and_evidence_contract(self):
        text = PAPER.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        for marker in (
            "signed, short-lived composite KTP enforcement state",
            "weighted diagonal standardized distance",
            "signed-state-only",
            "signed state plus local reduction",
            "observed",
            "modeled",
            "validated",
        ):
            self.assertIn(marker, normalized)
        self.assertNotIn("E_i,c", text)
        self.assertNotIn("weighted Mahalanobis distance", text)

    def test_architecture_separates_timescales_from_execution_rails(self):
        text = ARCHITECTURE.read_text(encoding="utf-8")
        for marker in (
            "Authoritative signed-state loop",
            "Fast enforcement loop",
            "Execution rails—not timescales",
            "Signed Qᵢ,c",
            "Local reducing-only overlay",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("Ephemeral charge Qᵢ,c", text)


if __name__ == "__main__":
    unittest.main()
