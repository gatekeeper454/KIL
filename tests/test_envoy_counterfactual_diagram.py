import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGRAM_PATH = ROOT / "docs" / "demo" / "envoy-lab-counterfactual-first.html"

REQUIRED_SOURCES = (
    "https://github.com/nmcitra/ktp-rfc/tree/v2.0.0",
    "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff",
    "https://huggingface.co/blog/agent-intrusion-technical-timeline",
)


class EnvoyCounterfactualDiagramContractTest(unittest.TestCase):
    def test_standalone_diagram_exists_and_cites_required_sources(self):
        self.assertTrue(DIAGRAM_PATH.is_file(), f"missing standalone diagram: {DIAGRAM_PATH}")
        html = DIAGRAM_PATH.read_text(encoding="utf-8")
        self.assertIn("<title>KIL — Counterfactual-First Envoy Laboratory</title>", html)
        for source in REQUIRED_SOURCES:
            with self.subTest(source=source):
                self.assertIn(source, html)


if __name__ == "__main__":
    unittest.main()
