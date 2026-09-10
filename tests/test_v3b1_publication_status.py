from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94"


class V3B1PublicationStatusTest(unittest.TestCase):
    def source(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_current_status_declares_the_bounded_completion(self):
        for relative in (
            "README.md",
            "docs/lab/V3-PROGRESS.md",
            "docs/paper/kinetic-infrastructure.md",
        ):
            with self.subTest(relative=relative):
                text = self.source(relative)
                self.assertIn("V3B-1 Complete", text)
                self.assertIn("local_envoy_boundary", text)
                self.assertIn(RUN_ID, text)
                self.assertIn("not proof that KIL would have prevented", text)

    def test_milestone_visual_places_publication_before_v4_future(self):
        text = self.source("docs/architecture/v3-publication-roadmap.svg")
        labels = [
            text.index(label)
            for label in ("V1", "V2", "V3A", "V3B-1 Complete", "Publication", "V4 Future")
        ]
        self.assertEqual(labels, sorted(labels))
        self.assertNotIn("V3B-2", text)

    def test_additional_validation_retains_exact_accepted_facts(self):
        text = self.source("docs/lab/V3-PROGRESS.md")
        for fact in (
            RUN_ID,
            "permit / permit / deny",
            "200 / 200 / 403",
            "1 / 1 / 0",
            "all nine authoritative",
            "15 owned containers",
            "six networks",
            "not_promoted",
        ):
            with self.subTest(fact=fact):
                self.assertIn(fact, text)

    def test_current_architecture_calls_cluster_work_v4_future(self):
        text = self.source("docs/architecture/hybrid-two-timescale-architecture.html")
        self.assertIn("Current · V3B-1 Complete", text)
        self.assertIn("Post-publication · V4 Future", text)
        self.assertNotIn("Future · V3B-2 Kind/Calico", text)


if __name__ == "__main__":
    unittest.main()
