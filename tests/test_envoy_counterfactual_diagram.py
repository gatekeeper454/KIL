import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGRAM_PATH = ROOT / "docs" / "demo" / "envoy-lab-counterfactual-first.html"
DEMO_PATH = ROOT / "docs" / "demo" / "kil-presenter-audience-demo.html"
README_PATH = ROOT / "README.md"

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
        self.ids = set()
        self.labelledby_references = []
        self.elements = []
        self.track_groups = []
        self._active_track = None
        self._track_depth = 0
        self._inside_svg = False
        self.svg_title_count = 0
        self.svg_desc_count = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.elements.append((tag, attributes))
        classes = set(attributes.get("class", "").split())
        if self._active_track is not None:
            self._track_depth += 1
        if "kil-track" in classes:
            self._active_track = {"attributes": attributes, "text": []}
            self._track_depth = 1
        if tag == "svg":
            self._inside_svg = True
        elif self._inside_svg and tag == "title":
            self.svg_title_count += 1
        elif self._inside_svg and tag == "desc":
            self.svg_desc_count += 1
        self._inspect(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))
        self._inspect(tag, attrs)

    def handle_data(self, data):
        if self._active_track is not None:
            self._active_track["text"].append(data)

    def handle_endtag(self, tag):
        if self._active_track is not None:
            self._track_depth -= 1
            if self._track_depth == 0:
                self._active_track["text"] = re.sub(
                    r"\s+", " ", " ".join(self._active_track["text"])
                ).strip()
                self.track_groups.append(self._active_track)
                self._active_track = None
        if tag == "svg":
            self._inside_svg = False

    def _inspect(self, tag, attrs):
        if tag.lower() in self.FORBIDDEN_TAGS:
            self.violations.append(f"forbidden tag: {tag}")
        for name, value in attrs:
            attribute = name.lower()
            if attribute == "id" and value:
                self.ids.add(value)
            if attribute == "aria-labelledby" and value:
                self.labelledby_references.extend(value.split())
            if attribute.startswith("on"):
                self.violations.append(f"event-handler attribute: {name}")
            if attribute == "href" and not (value or "").startswith(("https://", "#")):
                self.violations.append(f"non-passive href: {value}")


class EnvoyCounterfactualDiagramContractTest(unittest.TestCase):
    def read_html(self):
        return DIAGRAM_PATH.read_text(encoding="utf-8")

    def normalized_html(self):
        return re.sub(r"\s+", " ", self.read_html()).strip()

    def presenter_html(self):
        return DEMO_PATH.read_text(encoding="utf-8")

    def lab_mapping_scene_block(self):
        match = re.search(
            r'(?P<block>\{\s*"id": "case-lab-mapping".*?\n  \}),\n  \{',
            self.presenter_html(),
            re.DOTALL,
        )
        self.assertIsNotNone(match, "case-lab-mapping scene block is missing")
        return match.group("block")

    def lab_mapping_renderer_block(self):
        match = re.search(
            r"(?P<block>function renderLabMapping\(\) \{.*?)"
            r"(?=\n      function renderThreeTracks\(\))",
            self.presenter_html(),
            re.DOTALL,
        )
        self.assertIsNotNone(match, "renderLabMapping function block is missing")
        return match.group("block")

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

    def test_maps_cluster_api_request_into_the_controlled_lab(self):
        parser = PassiveDocumentParser()
        parser.feed(self.read_html())
        mapped_actions = [
            attributes
            for _, attributes in parser.elements
            if "kil-mapped-action" in attributes.get("class", "").split()
        ]
        self.assertEqual(1, len(mapped_actions))
        mapping_label = mapped_actions[0].get("aria-label", "")
        self.assertIn("Cluster API request", mapping_label)
        self.assertIn("first mediated action", mapping_label)
        self.assertIn("controlled lab", mapping_label)

    def test_tracks_share_named_driver_to_harmless_target_topology(self):
        html = self.read_html()
        parser = PassiveDocumentParser()
        parser.feed(html)
        self.assertEqual(3, len(parser.track_groups))
        self.assertEqual(3, html.count('class="kil-track-input"'))
        authorization_services = (
            "Policy authorization service",
            "KTP state authorization service",
            "KTP state + local reduction authorization service",
        )
        outcomes = ("HTTP 200", "HTTP 200", "derived HTTP 403")
        for track, authorization_service, outcome in zip(
            parser.track_groups, authorization_services, outcomes
        ):
            attributes = track["attributes"]
            self.assertEqual("group", attributes.get("role"))
            self.assertTrue(attributes.get("aria-label", "").strip())
            positions = [
                track["text"].index(label)
                for label in (
                    "Driver",
                    "Envoy frontend",
                    authorization_service,
                    "Harmless target marker",
                    outcome,
                )
            ]
            self.assertEqual(sorted(positions), positions)

    def test_calibrates_model_input_downstream_claim_and_mobile_fallback(self):
        html = self.normalized_html()
        calibration = "Conditionally unreachable under the declared model"
        self.assertRegex(
            html, rf'<svg class="kil-result-svg".*?{calibration}.*?</svg>'
        )
        self.assertRegex(
            html, rf'<div class="kil-mobile-result">.*?{calibration}.*?</div>'
        )
        self.assertIn(
            "d_t = 0.95 modeled divergence input; reducing-only local contribution; "
            "derived transport outcomes.",
            html,
        )
        self.assertNotIn("0.95 reduction", html)
        self.assertRegex(
            html,
            r"@media \(max-width: 760px\) \{ "
            r"\.kil-result-svg \{ display: none; \} "
            r"\.kil-mobile-result \{ display: block; \} \}",
        )

    def test_is_passive_accessible_responsive_and_calibrated(self):
        html = self.read_html()
        parser = PassiveDocumentParser()
        parser.feed(html)
        self.assertEqual([], parser.violations)
        unresolved = set(parser.labelledby_references) - parser.ids
        self.assertEqual(set(), unresolved)
        self.assertEqual(1, parser.svg_title_count)
        self.assertEqual(1, parser.svg_desc_count)
        self.assertEqual(3, len(parser.track_groups))
        for track in parser.track_groups:
            self.assertEqual("group", track["attributes"].get("role"))
            self.assertTrue(track["attributes"].get("aria-label", "").strip())
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

    def test_presenter_integrates_counterfactual_lab_mapping(self):
        scene = self.lab_mapping_scene_block()
        for marker in (
            '"title": "Observed breach, controlled lab, bounded result"',
            '"status": "Modeled lab mapping"',
            '"takeaway": "The lab isolates one mediated action and shows where reducing-only KIL evidence changes the derived transport effect."',
            '"script": "Start with the observed incident rail: a worker foothold expanded into control-plane access and dependent escalation. The lab maps only the first mediated cluster API request into three harmless, isolated Envoy tracks. KTP supplies supervision plus tighten-only constraints; HTTP status is an Envoy-derived effect, not a KTP wire decision. Tracks A and B reach their targets. Track C applies the modeled local reduction, derives HTTP four hundred three, and leaves dependent phases conditionally unreachable. Live V3B-1 enforcement remains pending."',
            '"source": "Hugging Face technical timeline; KTP v2.0.0; KIL V3A process contract and V3B-1 gate status."',
            '"visual": "lab-mapping"',
        ):
            with self.subTest(scene_marker=marker):
                self.assertIn(marker, scene)

        renderer = self.lab_mapping_renderer_block()
        for marker in (
            "KTP result: supervision + tighten-only constraints",
            "Envoy-derived effect: HTTP 403",
            "Observed · modeled · pending validation",
            "not a KTP wire decision",
        ):
            with self.subTest(renderer_marker=marker):
                self.assertIn(marker, renderer)

    def test_presenter_lab_mapping_has_dedicated_mobile_alternative(self):
        html = re.sub(r"\s+", " ", self.presenter_html()).strip()
        renderer = self.lab_mapping_renderer_block()
        self.assertIn('<div class="lab-mapping-desktop">', renderer)
        self.assertIn(
            '<section class="lab-mapping-mobile" '
            'aria-labelledby="lab-mapping-mobile-title">',
            renderer,
        )
        self.assertIn('<h2 id="lab-mapping-mobile-title">', renderer)
        self.assertNotRegex(
            renderer,
            r'class="lab-mapping-mobile"[^>]*\brole="img"',
        )
        self.assertIn('class="lab-mapping-band"', renderer)
        self.assertIn('class="lab-mapping-track"', renderer)
        self.assertIn(".lab-mapping-mobile { display: none; }", html)
        self.assertRegex(
            html,
            r"@media \(max-width: 640px\) \{ .*?"
            r"\.lab-mapping-desktop \{ display: none; \} .*?"
            r"\.lab-mapping-mobile \{ display: grid; .*?\} .*?\}",
        )

    def test_presenter_lab_mapping_stays_within_default_svg_canvas(self):
        html = self.presenter_html()
        renderer = self.lab_mapping_renderer_block()
        self.assertIn(
            "function svgShell(title, description, content, viewBox = '0 0 1000 500')",
            html,
        )
        self.assertEqual(1, renderer.count("svgShell("))
        y_coordinates = [
            float(value) for value in re.findall(r'\by="([0-9]+(?:\.[0-9]+)?)"', renderer)
        ]
        self.assertTrue(y_coordinates, "renderer has no y coordinates to check")
        self.assertLessEqual(max(y_coordinates), 480)
        self.assertNotIn('y="508"', renderer)

    def test_readme_links_standalone_counterfactual_diagram(self):
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("docs/demo/envoy-lab-counterfactual-first.html", readme)


if __name__ == "__main__":
    unittest.main()
