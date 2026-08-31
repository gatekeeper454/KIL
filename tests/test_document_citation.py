from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CITATION_URL = "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff"
BYTE_PRESERVED_DRAFTS = {
    Path("docs/drafts/kil-trust-decay-model.md"),
    Path("docs/drafts/ambient-enforcement-vs-huggingface-incident.md"),
}
REPOSITORY_INTERNAL_DIRS = {".git", ".worktrees"}
LEGACY_IMMUTABLE_RUNTIME_SUMMARIES = {
    Path(
        ".tools/v3b1-private/provisional/"
        "v3b1-1db8b5914ce26e2e6c60e74124bcc1b2c9ed66b7dd68c2d3cf4ea1bc0d18c9b3/"
        "summary.md"
    ),
    Path(
        "artifacts/generated/v3b1-local-envoy/"
        "v3b1-1db8b5914ce26e2e6c60e74124bcc1b2c9ed66b7dd68c2d3cf4ea1bc0d18c9b3/"
        "summary.md"
    ),
}


def _is_citation_target(relative: Path) -> bool:
    return relative not in LEGACY_IMMUTABLE_RUNTIME_SUMMARIES and not any(
        part in REPOSITORY_INTERNAL_DIRS for part in relative.parts
    )


class DocumentCitationTest(unittest.TestCase):
    def test_citation_scan_excludes_repository_worktree_copies(self):
        self.assertFalse(
            _is_citation_target(
                Path(
                    ".worktrees/v1-deterministic-kernel/docs/drafts/"
                    "kil-trust-decay-model.md"
                )
            )
        )
        self.assertFalse(_is_citation_target(Path(".git/README.md")))
        self.assertTrue(_is_citation_target(Path("docs/paper/kinetic-infrastructure.md")))

    def test_citation_scan_excludes_only_the_frozen_legacy_runtime_summaries(self):
        for relative in LEGACY_IMMUTABLE_RUNTIME_SUMMARIES:
            with self.subTest(relative=relative):
                self.assertFalse(_is_citation_target(relative))
                self.assertTrue(
                    _is_citation_target(
                        relative.parent.parent
                        / "v3b1-future-runtime-bundle"
                        / "summary.md"
                    )
                )

    def test_every_kil_authored_markdown_document_cites_ktp(self):
        missing = []
        for document in sorted(ROOT.rglob("*.md")):
            relative = document.relative_to(ROOT)
            if not _is_citation_target(relative):
                continue
            if relative in BYTE_PRESERVED_DRAFTS:
                continue
            if CITATION_URL not in document.read_text(encoding="utf-8"):
                missing.append(str(relative))
        self.assertEqual(missing, [], "documents missing the canonical KTP citation")

    def test_notice_cites_ktp(self):
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertIn(CITATION_URL, notice)


if __name__ == "__main__":
    unittest.main()
