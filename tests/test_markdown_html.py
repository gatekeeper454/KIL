from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from inspect import signature
from io import StringIO
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("render_markdown", ROOT / "tools/render_markdown.py")
assert SPEC is not None and SPEC.loader is not None
render_markdown = module_from_spec(SPEC)
SPEC.loader.exec_module(render_markdown)


class MarkdownRendererTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PurePosixPath("docs/guide.md")
        self.sources = frozenset(
            {self.source, PurePosixPath("docs/other.md")}
        )

    def render(self, markdown: str) -> str:
        return render_markdown.render_document(
            markdown.encode("utf-8"), self.source, self.sources
        ).decode("utf-8")

    def test_renders_static_article_tables_code_and_unicode(self) -> None:
        rendered = self.render(
            "# Café Guide\n\nA *clear* paragraph.\n\n> Quoted\n\n"
            "- one\n- two\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n"
            "[Reference][ref]\n\n[ref]: https://example.com\n\n"
            "```python\nprint('safe')\n```\n"
        )

        self.assertIn('<article id="reader-article">', rendered)
        self.assertIn('<h1 id="café-guide">Café Guide</h1>', rendered)
        self.assertIn("<em>clear</em>", rendered)
        self.assertIn("<blockquote>", rendered)
        self.assertIn("<ul>", rendered)
        self.assertIn("<table>", rendered)
        self.assertIn('<code class="language-python">', rendered)
        self.assertIn("print('safe')", rendered)
        self.assertIn('href="https://example.com"', rendered)

    def test_rewrites_only_tracked_relative_markdown_links(self) -> None:
        rendered = self.render(
            "[Other](other.md?view=1#part) "
            "[Web](https://example.com/readme.md) "
            "[Missing](missing.md) [Here](#part) "
            "![Image](other.md) [Text](notes.txt)\n"
        )

        self.assertIn('href="other.htm?view=1#part"', rendered)
        self.assertIn('href="https://example.com/readme.md"', rendered)
        self.assertIn('href="missing.md"', rendered)
        self.assertIn('href="#part"', rendered)
        self.assertIn('src="other.md"', rendered)
        self.assertIn('href="notes.txt"', rendered)
        self.assertEqual(
            "notes.txt",
            render_markdown.rewrite_destination(
                "notes.txt",
                self.source,
                frozenset({self.source, PurePosixPath("docs/notes.txt")}),
            ),
        )

    def test_preserves_non_relative_link_destinations(self) -> None:
        for destination in (
            "//example.com/readme.md",
            "/docs/other.md",
            "mailto:readers@example.com",
        ):
            with self.subTest(destination=destination):
                self.assertEqual(
                    destination,
                    render_markdown.rewrite_destination(
                        destination, self.source, self.sources
                    ),
                )

    def test_rejects_relative_links_that_escape_the_repository(self) -> None:
        for destination in ("../../outside.md", "../../../docs/other.md"):
            with self.subTest(destination=destination):
                with self.assertRaises(ValueError):
                    render_markdown.rewrite_destination(
                        destination, self.source, self.sources
                    )

    def test_rewrites_sufficient_parent_traversal_inside_repository(self) -> None:
        source = PurePosixPath("docs/guides/deep/guide.md")
        sources = frozenset({source, PurePosixPath("docs/other.md")})

        self.assertEqual(
            "../../other.htm",
            render_markdown.rewrite_destination("../../other.md", source, sources),
        )

    def test_rewrites_percent_encoded_tracked_paths_canonically(self) -> None:
        sources = frozenset(
            {
                self.source,
                PurePosixPath("docs/café.md"),
                PurePosixPath("docs/other file.md"),
                PurePosixPath("docs/literal#%.md"),
            }
        )

        self.assertEqual(
            "caf%C3%A9.htm?view=%25#part%23",
            render_markdown.rewrite_destination(
                "caf%C3%A9.md?view=%25#part%23", self.source, sources
            ),
        )
        self.assertEqual(
            "other%20file.htm",
            render_markdown.rewrite_destination(
                "other%20file.md", self.source, sources
            ),
        )
        self.assertEqual(
            "literal%23%25.htm",
            render_markdown.rewrite_destination(
                "literal%23%25.md", self.source, sources
            ),
        )

    def test_preserves_exact_empty_query_and_fragment_delimiters(self) -> None:
        sources = frozenset(
            {
                self.source,
                PurePosixPath("docs/other.md"),
                PurePosixPath("docs/other?.md"),
                PurePosixPath("docs/other#.md"),
            }
        )

        for destination, expected in (
            ("other.md?", "other.htm?"),
            ("other.md#", "other.htm#"),
            ("other.md?#", "other.htm?#"),
            ("other.md?x#", "other.htm?x#"),
            ("other%3F.md?x#", "other%3F.htm?x#"),
            ("other%23.md?#", "other%23.htm?#"),
        ):
            with self.subTest(destination=destination):
                self.assertEqual(
                    expected,
                    render_markdown.rewrite_destination(
                        destination, self.source, sources
                    ),
                )
    def test_rejects_unsafe_percent_encoded_relative_paths(self) -> None:
        for destination in (
            "%2e%2e/%2e%2e/outside.md",
            "%2E%2e/%2e%2e/outside.md",
            ".%2e/%2e%2e/outside.md",
            "%2e./%2e%2e/outside.md",
            "other\\file.md",
            "other%2ffile.md",
            "other%5Cfile.md",
            "other%.md",
            "other%2.md",
            "other%zz.md",
            "other%FF.md",
        ):
            with self.subTest(destination=destination):
                with self.assertRaises(ValueError):
                    render_markdown.rewrite_destination(
                        destination, self.source, self.sources
                    )

    def test_escapes_raw_html_without_creating_hostile_nodes(self) -> None:
        rendered = self.render(
            "# Safe\n\n<script>alert(1)</script>\n"
            "<img src=x onerror=alert(2)>\n"
        )

        article = rendered.split('<article id="reader-article">', 1)[1].split(
            "</article>", 1
        )[0]
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", article)
        self.assertIn("&lt;img src=x onerror=alert(2)&gt;", article)
        self.assertNotIn("<script>", article)
        self.assertNotIn("<img src=x", article)

    def test_mermaid_is_a_labeled_escaped_code_fence(self) -> None:
        rendered = self.render("```mermaid\ngraph TD; A-->B;\n```\n")

        self.assertIn('<code class="language-mermaid">', rendered)
        self.assertIn("graph TD; A--&gt;B;", rendered)
        self.assertNotIn("mermaid.initialize", rendered)

    def test_emits_no_remote_runtime_assets_or_network_apis(self) -> None:
        rendered = self.render("# Offline\n")

        self.assertNotRegex(rendered, r'<script[^>]+\bsrc=')
        self.assertNotRegex(rendered, r'<link[^>]+\b(?:href|rel)=')
        self.assertNotRegex(rendered, r'<(?:iframe|embed|object|audio|video)\b')
        self.assertNotIn("fetch(", rendered)
        self.assertNotIn("XMLHttpRequest", rendered)
        self.assertNotIn("import(", rendered)
        self.assertNotIn("serviceWorker", rendered)
        self.assertNotIn("document.write", rendered)

    def test_csp_contains_required_semantic_directives(self) -> None:
        rendered = self.render("# Policy\n")
        policy = (
            "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; font-src 'none'; connect-src 'none'; "
            "object-src 'none'; base-uri 'none'; form-action 'none'"
        )

        self.assertIn('http-equiv="Content-Security-Policy"', rendered)
        self.assertIn(policy.replace("'", "&#x27;"), rendered)

    def test_heading_ids_are_unique_and_deterministic(self) -> None:
        rendered = self.render("## Same\n\n## Same\n\n## !!!\n")

        self.assertIn('id="same"', rendered)
        self.assertIn('id="same-2"', rendered)
        self.assertIn('id="section"', rendered)
        self.assertEqual(rendered, self.render("## Same\n\n## Same\n\n## !!!\n"))
        counts: dict[str, int] = {}
        self.assertEqual(
            ["same", "same-2", "same-3"],
            [render_markdown._slug(value, counts) for value in ("Same", "Same-2", "Same")],
        )

    def test_slug_normalizes_nfkc_and_casefold_equivalent_headings(self) -> None:
        counts: dict[str, int] = {}

        self.assertEqual("café", render_markdown._slug("Café", counts))
        self.assertEqual("café-2", render_markdown._slug("ＣＡＦÉ", counts))

    def test_slug_converts_underscores_and_preserves_non_latin_alphanumerics(self) -> None:
        counts: dict[str, int] = {}

        self.assertEqual("snake-case", render_markdown._slug("snake_case", counts))
        self.assertEqual("привет-世界", render_markdown._slug("Привет 世界", counts))

    def test_multiline_heading_uses_spaces_for_title_outline_and_slug(self) -> None:
        for heading in (
            "First line\nsecond line\n---\n",
            "First line  \nsecond line\n---\n",
        ):
            with self.subTest(heading=heading):
                rendered = self.render(heading)

                self.assertIn("<title>First line second line</title>", rendered)
                self.assertIn('id="first-line-second-line"', rendered)
                outline = rendered.split('<nav class="reader-outline"', 1)[1].split(
                    "</nav>", 1
                )[0]
                self.assertIn(
                    'href="#first-line-second-line">First line second line', outline
                )

    def test_title_precedence_is_h1_then_heading_then_source_stem(self) -> None:
        self.assertIn("<title>Main</title>", self.render("# Main\n\n## Later\n"))
        self.assertIn("<title>First</title>", self.render("## First\n"))
        self.assertIn("<title>Fourth</title>", self.render("#### Fourth\n"))
        self.assertIn("<title>guide</title>", self.render("Plain body.\n"))

    def test_outline_contains_only_h1_through_h3(self) -> None:
        rendered = self.render("# One\n\n## Two\n\n### Three\n\n#### Four\n")

        outline = rendered.split('<nav class="reader-outline"', 1)[1].split(
            "</nav>", 1
        )[0]
        self.assertIn('href="#one"', outline)
        self.assertIn('href="#two"', outline)
        self.assertIn('href="#three"', outline)
        self.assertNotIn('href="#four"', outline)
        self.assertIn("data-reader-active", rendered)

    def test_embeds_source_identity_and_all_static_content(self) -> None:
        source = b"# Identity\n\nComplete article.\n"
        rendered = render_markdown.render_document(
            source, self.source, self.sources
        ).decode("utf-8")

        self.assertIn('name="source-path" content="docs/guide.md"', rendered)
        self.assertIn(
            f'name="source-sha256" content="{sha256(source).hexdigest()}"',
            rendered,
        )
        self.assertIn("Complete article.", rendered)
        self.assertIn("edit the Markdown source, not this reader", rendered)

    def test_rendering_is_byte_identical_and_has_one_final_newline(self) -> None:
        source = b"# Repeat\n\nStable output.\n"
        first = render_markdown.render_document(source, self.source, self.sources)
        second = render_markdown.render_document(source, self.source, self.sources)

        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))
        self.assertFalse(first.endswith(b"\n\n"))

    def test_uses_paper_stage_and_compact_mobile_reader_chrome(self) -> None:
        rendered = self.render("# Layout\n")

        self.assertIn("--canvas:", rendered)
        self.assertIn("--paper:", rendered)
        self.assertIn('<div class="reader-stage">', rendered)
        self.assertIn('<main class="reader-main reader-paper">', rendered)
        self.assertIn('<header class="reader-mobile-header">', rendered)
        self.assertRegex(
            rendered,
            r"\.reader-outline \{[^}]*height: 100vh;[^}]*position: sticky;",
        )
        self.assertIn("box-shadow:", rendered)
        self.assertIn("@media (max-width: 820px)", rendered)
        self.assertIn(".reader-outline { display: none; }", rendered)
        self.assertIn(".reader-mobile-header { display: flex;", rendered)
        self.assertIn(
            ".reader-chrome, .reader-mobile-header, .reader-mobile-support", rendered
        )
        self.assertIn("box-shadow: none", rendered)

    def test_wide_layout_directive_is_scoped_and_hidden(self) -> None:
        wide = self.render("<!-- reader-layout: wide -->\n# Wide\n")
        standard = self.render("# Standard\n")

        self.assertIn('<body class="reader-wide">', wide)
        self.assertNotIn("reader-layout: wide", wide)
        self.assertIn(
            "body.reader-wide .reader-layout {", wide
        )
        self.assertIn("minmax(0, 68rem)", wide)
        self.assertIn("@media (max-width: 1120px)", wide)
        self.assertIn("<body>", standard)
        self.assertNotIn('<body class="reader-wide">', standard)

    def test_mobile_reader_keeps_search_notice_and_semantic_outline(self) -> None:
        rendered = self.render("# Mobile\n\n## Section\n")
        identifiers = re.findall(r'(?<![-\w])id="([^"]+)"', rendered)

        self.assertIn('<label for="reader-mobile-search">Search</label>', rendered)
        self.assertIn('class="reader-mobile-notice"', rendered)
        self.assertIn('<details class="reader-mobile-outline">', rendered)
        self.assertIn("<summary>On this page</summary>", rendered)
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertIn(".reader-mobile-support { display: block;", rendered)
        self.assertIn(".reader-mobile-outline { display: block;", rendered)

    def test_search_uses_original_text_regex_and_normalizes_between_queries(self) -> None:
        self.assertEqual(
            [(1, 3), (3, 5)],
            render_markdown._literal_match_spans("banana", "an"),
        )
        self.assertEqual(
            [(1, 2), (3, 4), (5, 6)],
            render_markdown._literal_match_spans("banana", "a"),
        )
        self.assertEqual(
            [(2, 3)], render_markdown._literal_match_spans("İxyz", "y")
        )
        self.assertEqual(
            [(3, 5)], render_markdown._literal_match_spans("Cafe\u0301", "e\u0301")
        )
        self.assertIn("article.normalize()", render_markdown._JAVASCRIPT)
        self.assertIn('new RegExp(', render_markdown._JAVASCRIPT)
        self.assertIn('"giu"', render_markdown._JAVASCRIPT)
        self.assertNotIn("toLocaleLowerCase", render_markdown._JAVASCRIPT)

    def test_search_synchronizes_peer_controls_before_marking(self) -> None:
        synchronization = "searches.forEach((peer) => { peer.value = search.value; });"

        self.assertIn(synchronization, render_markdown._JAVASCRIPT)
        self.assertLess(
            render_markdown._JAVASCRIPT.index(synchronization),
            render_markdown._JAVASCRIPT.index("markMatches(search.value)"),
        )

    def test_print_rules_wrap_tables_and_code(self) -> None:
        rendered = self.render("# Print\n")

        self.assertIn("table-layout: fixed", rendered)
        self.assertIn("white-space: pre-wrap", rendered)


class RepositoryGenerationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "KIL Test"],
            cwd=self.root,
            check=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def track(self, relative: str, content: str | bytes) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "--", relative], cwd=self.root, check=True)

    def test_generates_exact_siblings_and_check_is_read_only(self) -> None:
        self.track("README.md", "# Root\n\n[Guide](docs/guide.md)\n")
        self.track("docs/guide.md", "# Guide\n")
        source_before = {
            relative: (self.root / relative).read_bytes()
            for relative in ("README.md", "docs/guide.md")
        }

        self.assertEqual([], render_markdown.render_repository(self.root))
        outputs_before = {
            relative: (self.root / relative).read_bytes()
            for relative in ("README.htm", "docs/guide.htm")
        }
        self.assertIn(b'href="docs/guide.htm"', outputs_before["README.htm"])
        self.assertEqual(
            [], render_markdown.render_repository(self.root, check=True)
        )
        self.assertEqual(
            outputs_before,
            {
                relative: (self.root / relative).read_bytes()
                for relative in outputs_before
            },
        )
        self.assertEqual(
            source_before,
            {
                relative: (self.root / relative).read_bytes()
                for relative in source_before
            },
        )

    def test_tracked_sources_exclude_untracked_and_ignored_markdown(self) -> None:
        self.track("tracked.md", "# Tracked\n")
        (self.root / "untracked.md").write_text("# Untracked\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
        ignored = self.root / "ignored/private.md"
        ignored.parent.mkdir()
        ignored.write_text("# Private\n", encoding="utf-8")

        self.assertEqual(
            (PurePosixPath("tracked.md"),),
            render_markdown.discover_sources(self.root),
        )
        self.assertEqual([], render_markdown.render_repository(self.root))
        self.assertTrue((self.root / "tracked.htm").is_file())
        self.assertFalse((self.root / "untracked.htm").exists())
        self.assertFalse((self.root / "ignored/private.htm").exists())

    def test_untracked_html_is_visible_but_ignored_html_is_not(self) -> None:
        self.track("README.md", "# Root\n")
        (self.root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
        ignored = self.root / "ignored/private.htm"
        ignored.parent.mkdir()
        ignored.write_text("private", encoding="utf-8")
        (self.root / "extra.htm").write_text("manual", encoding="utf-8")

        self.assertEqual(
            ["missing README.htm", "unexpected extra.htm"],
            render_markdown.render_repository(self.root, check=True),
        )
        self.assertEqual(
            ["unexpected extra.htm"],
            render_markdown.render_repository(self.root),
        )
        self.assertFalse((self.root / "README.htm").exists())
        self.assertEqual("private", ignored.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "posix", "control filenames require POSIX")
    def test_default_mode_rejects_an_ignored_expected_sibling(self) -> None:
        self.track("line\nbreak.md", "# Root\n")
        (self.root / ".gitignore").write_text("*.htm\n", encoding="utf-8")

        self.assertEqual(
            [r"missing line\nbreak.htm"],
            render_markdown.render_repository(self.root, check=True),
        )
        with self.assertRaisesRegex(
            ValueError, r"expected HTML output is ignored: line\\nbreak.htm"
        ):
            render_markdown.render_repository(self.root)
        self.assertFalse((self.root / "line\nbreak.htm").exists())

    def test_deleted_tracked_expected_output_is_missing_and_repairable(self) -> None:
        self.track("README.md", "# Root\n")
        self.assertEqual([], render_markdown.render_repository(self.root))
        subprocess.run(
            ["git", "add", "--", "README.htm"], cwd=self.root, check=True
        )
        self.track(".gitignore", "*.htm\n")
        (self.root / "README.htm").unlink()

        self.assertEqual(
            ["missing README.htm"],
            render_markdown.render_repository(self.root, check=True),
        )
        self.assertEqual([], render_markdown.render_repository(self.root))
        self.assertTrue((self.root / "README.htm").is_file())
        self.assertEqual([], render_markdown.render_repository(self.root, check=True))

    @unittest.skipUnless(os.name == "posix", "control filenames require POSIX")
    def test_path_diagnostics_are_line_safe_unicode_preserving_and_sorted(self) -> None:
        for relative in (
            "carriage\rreturn.md",
            "escape\x1bname.md",
            "line\nbreak.md",
            "next\u0085line.md",
            'quote"slash\\name.md',
            "right\u202eto-left.md",
            "separator\u2028line.md",
            "word\u200bjoin.md",
            "isolate\u2066name.md",
            "unicodé.md",
        ):
            self.track(relative, "# Document\n")
        (self.root / "manual\nextra.htm").write_bytes(b"manual")

        first = render_markdown.render_repository(self.root, check=True)
        second = render_markdown.render_repository(self.root, check=True)

        self.assertEqual(first, second)
        self.assertEqual(
            sorted(
                [
                    r"missing carriage\rreturn.htm",
                    r"missing escape\u001bname.htm",
                    r"missing line\nbreak.htm",
                    r"missing next\u0085line.htm",
                    r'missing quote\"slash\\name.htm',
                    r"missing right\u202eto-left.htm",
                    r"missing separator\u2028line.htm",
                    r"missing word\u200bjoin.htm",
                    r"missing isolate\u2066name.htm",
                    "missing unicodé.htm",
                    r"unexpected manual\nextra.htm",
                ],
                key=lambda value: value.encode("utf-8"),
            ),
            first,
        )
        for problem in first:
            self.assertNotIn("\n", problem)
            self.assertNotIn("\r", problem)
            self.assertNotIn("\x1b", problem)
            self.assertNotIn("\u0085", problem)
            self.assertNotIn("\u2028", problem)
            self.assertNotIn("\u202e", problem)
            self.assertNotIn("\u2066", problem)
            self.assertNotIn("\u200b", problem)

    @unittest.skipUnless(os.name == "posix", "NAME_MAX test requires POSIX")
    def test_near_name_max_source_generates_with_a_short_staging_name(self) -> None:
        name_max = os.pathconf(self.root, "PC_NAME_MAX")
        stem = "n" * (name_max - len(".htm"))
        self.track(f"{stem}.md", "# Long name\n")

        self.assertEqual([], render_markdown.render_repository(self.root))
        self.assertTrue((self.root / f"{stem}.htm").is_file())
        self.assertEqual([], list(self.root.glob(".kil-reader-*.tmp")))

    def test_check_reports_missing_stale_and_unexpected_in_sorted_order(self) -> None:
        self.track("z-last.md", "# Last\n")
        self.track("a-first.md", "# First\n")
        render_markdown.render_repository(self.root)
        (self.root / "a-first.htm").write_text("stale", encoding="utf-8")
        (self.root / "z-last.htm").unlink()
        (self.root / "middle.htm").write_text("manual", encoding="utf-8")

        self.assertEqual(
            [
                "missing z-last.htm",
                "stale a-first.htm",
                "unexpected middle.htm",
            ],
            render_markdown.render_repository(self.root, check=True),
        )

    def test_check_never_repairs_or_removes_outputs(self) -> None:
        self.track("README.md", "# Root\n")
        (self.root / "README.htm").write_bytes(b"stale")
        (self.root / "extra.htm").write_bytes(b"manual")
        before = {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.root.glob("*.htm")
        }

        problems = render_markdown.render_repository(self.root, check=True)

        self.assertEqual(
            ["stale README.htm", "unexpected extra.htm"], problems
        )
        self.assertEqual(
            before,
            {
                path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.glob("*.htm")
            },
        )

    def test_preflight_render_failure_preserves_every_existing_output(self) -> None:
        self.track("a.md", "# A\n")
        self.track("z.md", "# Z\n")
        self.assertEqual([], render_markdown.render_repository(self.root))
        before = {
            relative: (self.root / relative).read_bytes()
            for relative in ("a.htm", "z.htm")
        }
        (self.root / "z.md").write_bytes(b"\xff")

        with self.assertRaises(UnicodeDecodeError):
            render_markdown.render_repository(self.root)

        self.assertEqual(
            before,
            {
                relative: (self.root / relative).read_bytes()
                for relative in before
            },
        )

    def test_replace_failure_cleans_staging_and_leaves_detectable_drift(self) -> None:
        self.track("a.md", "# A old\n")
        self.track("z.md", "# Z old\n")
        self.assertEqual([], render_markdown.render_repository(self.root))
        before = {
            relative: (self.root / relative).read_bytes()
            for relative in ("a.htm", "z.htm")
        }
        (self.root / "a.md").write_text("# A new\n", encoding="utf-8")
        (self.root / "z.md").write_text("# Z new\n", encoding="utf-8")
        real_replace = render_markdown.os.replace
        replacement_count = 0

        def fail_second_replacement(source: Path, destination: Path) -> None:
            nonlocal replacement_count
            replacement_count += 1
            if replacement_count == 2:
                raise OSError("injected replacement failure")
            real_replace(source, destination)

        with patch.object(
            render_markdown.os, "replace", side_effect=fail_second_replacement
        ):
            with self.assertRaisesRegex(OSError, "injected replacement failure"):
                render_markdown.render_repository(self.root)

        self.assertNotEqual(before["a.htm"], (self.root / "a.htm").read_bytes())
        self.assertEqual(before["z.htm"], (self.root / "z.htm").read_bytes())
        self.assertEqual([], list(self.root.glob(".*.tmp")))
        self.assertEqual(
            ["stale z.htm"],
            render_markdown.render_repository(self.root, check=True),
        )

    def test_mapping_changes_only_the_final_lowercase_md_suffix(self) -> None:
        self.track("nested/archive.md.md", "# Nested\n")
        self.track("UPPER.MD", "# Upper\n")

        self.assertEqual(
            (PurePosixPath("nested/archive.md.md"),),
            render_markdown.discover_sources(self.root),
        )
        self.assertEqual([], render_markdown.render_repository(self.root))
        self.assertTrue((self.root / "nested/archive.md.htm").is_file())
        self.assertFalse((self.root / "nested/archive.htm").exists())
        self.assertFalse((self.root / "UPPER.htm").exists())

    def test_spaces_and_unicode_paths_are_sorted_by_utf8_bytes(self) -> None:
        for relative in ("é.md", "a space.md", "docs/ß.md"):
            self.track(relative, f"# {relative}\n")

        sources = render_markdown.discover_sources(self.root)

        self.assertEqual(
            tuple(sorted(sources, key=lambda value: value.as_posix().encode("utf-8"))),
            sources,
        )
        self.assertEqual([], render_markdown.render_repository(self.root))
        for source in sources:
            self.assertTrue((self.root / source.with_suffix(".htm")).is_file())

    def test_rejects_duplicate_sources_before_an_output_collision(self) -> None:
        self.track("same.md", "# Same\n")
        original = render_markdown.discover_sources
        render_markdown.discover_sources = lambda root: (
            PurePosixPath("same.md"),
            PurePosixPath("same.md"),
        )
        try:
            with self.assertRaisesRegex(ValueError, "output collision: same.htm"):
                render_markdown.expected_documents(self.root)
        finally:
            render_markdown.discover_sources = original

    @unittest.skipUnless(os.name == "posix", "symlink contract requires POSIX")
    def test_rejects_symlinked_sources_and_outputs(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.md"
        outside.write_text("# Outside\n", encoding="utf-8")

        def make_symlink(link: Path) -> None:
            try:
                os.symlink(outside, link)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink creation unavailable: {error}")

        try:
            make_symlink(self.root / "linked.md")
            subprocess.run(
                ["git", "add", "--", "linked.md"], cwd=self.root, check=True
            )
            with self.assertRaisesRegex(ValueError, "unsafe Markdown source"):
                render_markdown.discover_sources(self.root)

            subprocess.run(
                ["git", "rm", "-q", "--cached", "linked.md"],
                cwd=self.root,
                check=True,
            )
            (self.root / "linked.md").unlink()
            self.track("safe.md", "# Safe\n")
            make_symlink(self.root / "safe.htm")
            with self.assertRaisesRegex(ValueError, "unsafe HTML output"):
                render_markdown.render_repository(self.root, check=True)
        finally:
            outside.unlink(missing_ok=True)

    def test_default_mode_refuses_unexpected_output_before_any_write(self) -> None:
        self.track("a.md", "# A\n")
        self.track("z.md", "# Z\n")
        render_markdown.render_repository(self.root)
        (self.root / "a.md").write_text("# A changed\n", encoding="utf-8")
        before = (self.root / "a.htm").read_bytes()
        (self.root / "manual.htm").write_bytes(b"manual")
        (self.root / "z.htm").unlink()

        self.assertEqual(
            ["unexpected manual.htm"],
            render_markdown.render_repository(self.root),
        )
        self.assertEqual(before, (self.root / "a.htm").read_bytes())
        self.assertFalse((self.root / "z.htm").exists())

    def test_main_reports_generation_check_problems_and_errors(self) -> None:
        self.track("README.md", "# Root\n")
        old_root = render_markdown.ROOT
        render_markdown.ROOT = self.root
        try:
            standard_output = StringIO()
            standard_error = StringIO()
            with redirect_stdout(standard_output), redirect_stderr(standard_error):
                self.assertEqual(0, render_markdown.main([]))
            self.assertEqual(
                "generated 1 Markdown readers\n", standard_output.getvalue()
            )
            self.assertEqual("", standard_error.getvalue())

            (self.root / "README.htm").write_bytes(b"stale")
            standard_output = StringIO()
            standard_error = StringIO()
            with redirect_stdout(standard_output), redirect_stderr(standard_error):
                self.assertEqual(1, render_markdown.main(["--check"]))
            self.assertEqual("", standard_output.getvalue())
            self.assertEqual("stale README.htm\n", standard_error.getvalue())

            (self.root / "README.md").write_bytes(b"\xff")
            standard_error = StringIO()
            with redirect_stderr(standard_error):
                self.assertEqual(1, render_markdown.main(["--check"]))
            self.assertIn("markdown reader error:", standard_error.getvalue())
        finally:
            render_markdown.ROOT = old_root

    def test_main_discovers_sources_once_and_counts_that_snapshot(self) -> None:
        self.track("README.md", "# Root\n")
        original = render_markdown.discover_sources
        calls = 0

        def discover_once(root: Path) -> tuple[PurePosixPath, ...]:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise AssertionError("source discovery repeated")
            return original(root)

        old_root = render_markdown.ROOT
        render_markdown.ROOT = self.root
        try:
            standard_output = StringIO()
            with patch.object(
                render_markdown, "discover_sources", side_effect=discover_once
            ), redirect_stdout(standard_output):
                self.assertEqual(0, render_markdown.main([]))
            self.assertEqual(1, calls)
            self.assertEqual(
                "generated 1 Markdown readers\n", standard_output.getvalue()
            )
        finally:
            render_markdown.ROOT = old_root

    def test_snapshot_reuse_is_internal_to_the_public_repository_api(self) -> None:
        self.assertEqual(
            ("root", "check"),
            tuple(signature(render_markdown.render_repository).parameters),
        )
        self.assertEqual(
            ("root",),
            tuple(signature(render_markdown.expected_documents).parameters),
        )


class RepositoryPublicationContractTest(unittest.TestCase):
    def test_every_tracked_markdown_has_exact_tracked_generated_sibling(self) -> None:
        sources = render_markdown.discover_sources(ROOT)
        expected = {source.with_suffix(".htm") for source in sources}
        tracked_output = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.htm"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        tracked = {
            PurePosixPath(raw.decode("utf-8"))
            for raw in tracked_output.split(b"\0")
            if raw
        }

        self.assertEqual(expected, tracked)

    def test_checked_in_readers_are_current_and_sources_are_unchanged(self) -> None:
        sources = render_markdown.discover_sources(ROOT)
        before = {source: (ROOT / source).read_bytes() for source in sources}

        self.assertEqual([], render_markdown.render_repository(ROOT, check=True))
        self.assertEqual(
            before,
            {source: (ROOT / source).read_bytes() for source in sources},
        )

    def test_byte_preserved_drafts_match_their_recorded_checksums(self) -> None:
        recorded = dict(
            reversed(line.split("  ", 1))
            for line in (
                ROOT / "research/source-material/SHA256SUMS"
            ).read_text(encoding="utf-8").splitlines()
            if line
        )
        for name in (
            "docs/drafts/kil-trust-decay-model.md",
            "docs/drafts/ambient-enforcement-vs-huggingface-incident.md",
        ):
            digest = sha256((ROOT / name).read_bytes()).hexdigest()
            self.assertEqual(recorded[name], digest)

    def test_make_wires_generation_and_check_into_validation(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

        self.assertIn(".PHONY: help check-python test docs-html docs-html-check validate", makefile)
        self.assertIn(
            "docs-html: check-python\n"
            "\tPYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src $(PYTHON) "
            "tools/render_markdown.py\n",
            makefile,
        )
        self.assertIn(
            "docs-html-check: check-python\n"
            "\tPYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src $(PYTHON) "
            "tools/render_markdown.py --check\n",
            makefile,
        )
        self.assertIn("validate: test docs-html-check\n", makefile)


if __name__ == "__main__":
    unittest.main()
