import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_PATH = ROOT / "docs" / "demo" / "kil-presenter-audience-demo.html"

EXPECTED_IDS = [
    "primer-ambient-breach",
    "primer-kinetic-infrastructure",
    "primer-ktp-extension",
    "primer-trust-physics",
    "case-ambient-breach",
    "case-foothold",
    "case-first-divergence",
    "case-cascade",
    "case-kil-mechanics",
    "case-lab-mapping",
    "case-three-tracks",
    "case-evidence",
]

REQUIRED_KEYS = {
    "id",
    "act",
    "order",
    "title",
    "status",
    "takeaway",
    "script",
    "source",
    "visual",
}

REQUIRED_HOOKS = (
    "data-mode-label",
    "data-sync-status",
    "data-act-controls",
    "data-scene-controls",
    "data-visual",
    "data-presenter-notes",
    "data-prev",
    "data-next",
    "data-open-audience",
)

REQUIRED_REFERENCES = (
    "https://github.com/nmcitra/ktp-rfc/tree/v2.0.0",
    "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff",
    "https://kinetic-trust-protocol.net/enterprise/architecture",
    "https://kinetic-trust-protocol.net/learn/constitution",
    "https://huggingface.co/blog/agent-intrusion-technical-timeline",
)

PROHIBITED_PUBLIC_CLAIMS = (
    "absolute denial",
    "prevented structurally",
    "microsecond enforcement",
    "classic zero trust failure",
    "perfectly valid credentials",
    "killed before",
    "for free",
    "0 bytes exfiltrated",
    "validated live kubernetes",
)

PRIMER_VISUALS = {
    "ambient-breach": "renderAmbientBreach",
    "kil-comparison": "renderKILComparison",
    "hybrid-architecture": "renderHybridArchitecture",
    "trust-physics": "renderTrustPhysics",
}

CASE_VISUALS = {
    "incident-overview": "renderIncidentOverview",
    "foothold": "renderFoothold",
    "branching-cutoff": "renderBranchingCutoff",
    "incident-topology": "renderIncidentTopology",
    "hybrid-applied": "renderHybridApplied",
    "lab-mapping": "renderLabMapping",
    "three-tracks": "renderThreeTracks",
    "evidence-ladder": "renderEvidenceLadder",
}


class PresenterAudienceDemoContractTest(unittest.TestCase):
    def _html(self) -> str:
        if not DEMO_PATH.exists():
            self.skipTest("canonical presenter/audience demo is not created yet")
        return DEMO_PATH.read_text(encoding="utf-8")

    def _scenes(self):
        html = self._html()
        match = re.search(
            r'<script\s+id="kil-demo-scenes"\s+type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "scene JSON script is missing")
        return json.loads(match.group(1))

    def test_canonical_demo_exists(self):
        self.assertTrue(DEMO_PATH.is_file(), f"missing canonical demo: {DEMO_PATH}")

    def test_scene_records_are_closed_complete_and_ordered(self):
        scenes = self._scenes()
        self.assertEqual([scene["id"] for scene in scenes], EXPECTED_IDS)
        self.assertTrue(all(set(scene) == REQUIRED_KEYS for scene in scenes))
        self.assertEqual([scene["act"] for scene in scenes[:4]], ["primer"] * 4)
        self.assertEqual([scene["act"] for scene in scenes[4:]], ["case-study"] * 8)
        self.assertEqual([scene["order"] for scene in scenes], list(range(1, 13)))

    def test_every_scene_has_a_balanced_talk_track(self):
        for scene in self._scenes():
            with self.subTest(scene=scene["id"]):
                word_count = len(scene["script"].split())
                self.assertGreaterEqual(word_count, 70)
                self.assertLessEqual(word_count, 90)
                self.assertTrue(scene["takeaway"].strip())
                self.assertTrue(scene["source"].strip())

    def test_dom_hooks_and_source_references_are_present(self):
        html = self._html()
        for hook in REQUIRED_HOOKS:
            with self.subTest(hook=hook):
                self.assertIn(hook, html)
        for reference in REQUIRED_REFERENCES:
            with self.subTest(reference=reference):
                self.assertIn(reference, html)

    def test_public_copy_avoids_prohibited_claims(self):
        html = self._html().lower()
        for claim in PROHIBITED_PUBLIC_CLAIMS:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, html)

    def test_primer_visuals_have_dedicated_renderers(self):
        html = self._html()
        scenes = self._scenes()
        self.assertEqual(
            [scene["visual"] for scene in scenes[:4]],
            list(PRIMER_VISUALS),
        )
        for visual, renderer in PRIMER_VISUALS.items():
            with self.subTest(visual=visual):
                self.assertIn(f"function {renderer}(", html)
        self.assertIn("Signed, short-lived composite KTP enforcement state", html)
        self.assertIn("Reducing-only local overlay", html)
        self.assertIn("Earn slowly", html)
        self.assertIn("Lose quickly", html)

    def test_case_visuals_have_dedicated_bounded_renderers(self):
        html = self._html()
        scenes = self._scenes()
        self.assertEqual(
            [scene["visual"] for scene in scenes[4:]],
            list(CASE_VISUALS),
        )
        for visual, renderer in CASE_VISUALS.items():
            with self.subTest(visual=visual):
                self.assertIn(f"function {renderer}(", html)
        for required_copy in (
            "0.95 modeled",
            "0.90 modeled",
            "Conditionally unreachable",
            "PERMIT · PERMIT · DENY",
            "200 · 200 · 403",
            "V3A modeled",
            "V3B-1 pending",
            "V3B-2 future",
        ):
            with self.subTest(required_copy=required_copy):
                self.assertIn(required_copy, html)


if __name__ == "__main__":
    unittest.main()
