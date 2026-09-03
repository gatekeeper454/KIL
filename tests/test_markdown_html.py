from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path, PurePosixPath
import re
import unittest


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


if __name__ == "__main__":
    unittest.main()
