import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGRAM_PATH = ROOT / "docs" / "demo" / "envoy-lab-counterfactual-first.html"

REQUIRED_SOURCES = (
    "https://github.com/nmcitra/ktp-rfc/tree/v2.0.0",
    "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff",
    "https://huggingface.co/blog/agent-intrusion-technical-timeline",
)


class PassiveDocumentParser(HTMLParser):
    FORBIDDEN_TAGS = {"script", "iframe", "object", "embed", "form"}

    def __init__(self):
        super().__init__()
        self.violations = []

    def handle_starttag(self, tag, attrs):
        self._inspect(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._inspect(tag, attrs)

    def _inspect(self, tag, attrs):
        if tag.lower() in self.FORBIDDEN_TAGS:
            self.violations.append(f"forbidden tag: {tag}")
        for name, value in attrs:
            attribute = name.lower()
            if attribute.startswith("on"):
                self.violations.append(f"event-handler attribute: {name}")
            if attribute == "href" and not (value or "").startswith(("https://", "#")):
                self.violations.append(f"non-passive href: {value}")


class EnvoyCounterfactualDiagramContractTest(unittest.TestCase):
    def read_html(self):
        return DIAGRAM_PATH.read_text(encoding="utf-8")

    def normalized_html(self):
        return re.sub(r"\s+", " ", self.read_html()).strip()

    def test_standalone_diagram_exists_and_cites_required_sources(self):
        self.assertTrue(DIAGRAM_PATH.is_file(), f"missing standalone diagram: {DIAGRAM_PATH}")
        html = self.read_html()
        self.assertIn("<title>KIL — Counterfactual-First Envoy Laboratory</title>", html)
        for source in REQUIRED_SOURCES:
            with self.subTest(source=source):
                self.assertIn(source, html)

    def test_frames_ambient_breach_as_an_operating_condition(self):
        html = self.normalized_html()
        for phrase in (
            "Cybersecurity is currently at an inflection point",
            "pervasive, continuous ‘ambient breach’",
            "Ambient enforcement represents this critical evolution",
            "does not mean every system is continuously compromised",
        ):
            self.assertIn(phrase, html)

    def test_composes_observed_lab_and_counterfactual_result_bands(self):
        html = self.normalized_html()
        bands = re.findall(r'data-band="(observed|lab|result)"', html)
        self.assertEqual(["observed", "lab", "result"], bands)
        for phrase in (
            "Observed incident",
            "Envoy lab model",
            "KIL counterfactual result",
            "Signed composite KTP state",
            "supervision plus tighten-only constraints",
            "derived HTTP 403",
            "200 / 200 / 403",
            "1 / 1 / 0",
            "Conditionally unreachable",
            "Pending validation",
        ):
            self.assertIn(phrase, html)

    def test_is_passive_accessible_responsive_and_calibrated(self):
        html = self.read_html()
        parser = PassiveDocumentParser()
        parser.feed(html)
        self.assertEqual([], parser.violations)
        for marker in (
            'role="img"',
            "<title id=",
            "<desc id=",
            "aria-labelledby=",
            "@media (max-width: 640px)",
            "@media (prefers-reduced-motion: reduce)",
        ):
            self.assertIn(marker, html)
        lower_html = html.lower()
        self.assertNotIn("microsecond enforcement", lower_html)
        self.assertNotIn("validated live", lower_html)


if __name__ == "__main__":
    unittest.main()
