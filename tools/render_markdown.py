"""Pure, deterministic Markdown-to-HTML rendering for KIL readers."""

from __future__ import annotations

from hashlib import sha256
from html import escape
from pathlib import Path, PurePosixPath
import posixpath
import re
from typing import Iterable
from unicodedata import normalize
from urllib.parse import quote_from_bytes, unquote_to_bytes, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = "KIL Markdown Reader 1"
GENERATED_MARKER = '<meta name="generator" content="KIL Markdown Reader 1">'
_CSP = (
    "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; font-src 'none'; connect-src 'none'; "
    "object-src 'none'; base-uri 'none'; form-action 'none'"
)

_CSS = """
:root { color-scheme: light dark; --canvas: #ebe7df; --paper: #fffdf8; --ink: #1d1b18; --muted: #6b665d; --line: #ded8cc; --accent: #8c3f1d; --code: #f3efe6; }
:root[data-theme="dark"] { --canvas: #11100f; --paper: #191817; --ink: #eee9df; --muted: #b8b0a5; --line: #48433c; --accent: #ffad7b; --code: #272421; }
* { box-sizing: border-box; }
html { background: var(--canvas); color: var(--ink); font-family: ui-serif, Georgia, serif; line-height: 1.65; }
body { background: var(--canvas); margin: 0; min-height: 100vh; }
a { color: var(--accent); text-underline-offset: .16em; }
.reader-chrome { border-bottom: 1px solid var(--line); font-family: ui-sans-serif, system-ui, sans-serif; padding: .75rem clamp(1rem, 4vw, 3rem); }
.reader-bar { align-items: center; display: flex; flex-wrap: wrap; gap: .6rem; justify-content: space-between; }
.reader-notice { color: var(--muted); font-size: .82rem; margin: .7rem 0 0; }
.reader-controls { display: flex; gap: .5rem; }
.reader-mobile-header { display: none; }
.reader-mobile-support, .reader-mobile-outline { display: none; }
button, input { font: inherit; }
button { background: var(--paper); border: 1px solid var(--line); border-radius: .3rem; color: inherit; cursor: pointer; padding: .32rem .55rem; }
input { background: var(--paper); border: 1px solid var(--line); border-radius: .3rem; color: inherit; padding: .32rem .55rem; }
.reader-search { align-items: center; display: flex; flex-wrap: wrap; gap: .45rem; }
.reader-search-output { color: var(--muted); font-size: .85rem; }
.reader-stage { min-height: 100vh; padding: clamp(1.5rem, 5vw, 4rem) clamp(1rem, 4vw, 3rem); }
.reader-layout { align-items: start; display: grid; gap: clamp(1.5rem, 5vw, 4rem); grid-template-columns: minmax(12rem, 15rem) minmax(0, 46rem); justify-content: center; margin: 0 auto; max-width: 70rem; }
.reader-outline { align-self: stretch; font-family: ui-sans-serif, system-ui, sans-serif; font-size: .88rem; height: 100vh; overflow-y: auto; padding: 1.25rem .75rem 1.25rem 0; position: sticky; top: 0; }
.reader-outline h2 { font-size: .9rem; margin: 0 0 .65rem; }
.reader-outline ol { border-left: 1px solid var(--line); list-style: none; margin: 0; padding-left: .7rem; }
.reader-outline li { margin: .3rem 0; }
.reader-outline a { color: var(--muted); text-decoration: none; }
.reader-outline a[aria-current="true"] { color: var(--accent); font-weight: 700; }
.reader-outline .level-2 { margin-left: .65rem; }.reader-outline .level-3 { margin-left: 1.3rem; }
.reader-main { min-width: 0; }
.reader-paper { background: var(--paper); border: 1px solid var(--line); border-radius: .75rem; box-shadow: 0 1rem 3rem rgb(40 34 25 / .12); padding: clamp(1.5rem, 5vw, 4rem); }
#reader-article { font-size: clamp(1rem, .98rem + .12vw, 1.1rem); overflow-wrap: break-word; }
#reader-article > :first-child { margin-top: 0; }
#reader-article h1, #reader-article h2, #reader-article h3, #reader-article h4, #reader-article h5, #reader-article h6 { line-height: 1.18; scroll-margin-top: 1.5rem; }
#reader-article h1 { font-size: clamp(2rem, 7vw, 3.4rem); letter-spacing: -.035em; }
#reader-article h2 { margin-top: 2.5em; }
#reader-article [data-reader-active] { border-left: .22rem solid var(--accent); padding-left: .5rem; }
#reader-article img { height: auto; max-width: 100%; }
#reader-article table { border-collapse: collapse; display: block; max-width: 100%; overflow-x: auto; }
#reader-article th, #reader-article td { border: 1px solid var(--line); padding: .4rem .65rem; text-align: left; }
#reader-article pre { background: var(--code); overflow-x: auto; padding: 1rem; }
#reader-article code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em; }
#reader-article :not(pre) > code { background: var(--code); padding: .08em .25em; }
mark.reader-match { background: #ffe58a; color: #201c10; }
@media (max-width: 820px) { .reader-chrome { display: none; } .reader-mobile-header { display: flex; align-items: center; background: var(--canvas); border-bottom: 1px solid var(--line); font-family: ui-sans-serif, system-ui, sans-serif; gap: .75rem; justify-content: space-between; padding: .6rem 1rem; position: sticky; top: 0; z-index: 1; } .reader-mobile-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .reader-mobile-controls { display: flex; flex: none; gap: .4rem; } .reader-mobile-support { display: block; font-family: ui-sans-serif, system-ui, sans-serif; padding: .75rem 1rem; } .reader-mobile-notice { color: var(--muted); font-size: .78rem; margin: .65rem 0 0; } .reader-mobile-outline { display: block; font-family: ui-sans-serif, system-ui, sans-serif; margin-bottom: 1rem; } .reader-mobile-outline summary { cursor: pointer; font-weight: 700; } .reader-mobile-outline nav { padding: .7rem 0; } .reader-mobile-outline ol { margin: 0; padding-left: 1.25rem; } .reader-outline { display: none; } .reader-stage { padding: 1rem; } .reader-layout { display: block; } .reader-paper { border-radius: .5rem; padding: clamp(1.25rem, 6vw, 2rem); } }
@media print { :root { color-scheme: light; --canvas: white; --paper: white; --ink: black; } .reader-chrome, .reader-mobile-header, .reader-mobile-support, .reader-mobile-outline, .reader-outline { display: none !important; } .reader-stage, .reader-layout { display: block; max-width: none; padding: 0; } .reader-paper { background: transparent; border: 0; border-radius: 0; box-shadow: none; padding: 0; } a { color: inherit; text-decoration: none; } #reader-article { font-size: 11pt; } #reader-article table { display: table; table-layout: fixed; width: 100%; } #reader-article th, #reader-article td, #reader-article pre, #reader-article code { overflow-wrap: anywhere; white-space: pre-wrap; } }
""".strip()

_JAVASCRIPT = r"""
(() => {
  const article = document.getElementById("reader-article");
  const searches = [...document.querySelectorAll("[data-reader-search]")];
  const outputs = [...document.querySelectorAll("[data-reader-search-output]")];
  const themes = [...document.querySelectorAll("[data-theme-toggle]")];
  const prints = [...document.querySelectorAll("[data-print]")];
  const root = document.documentElement;
  const clearMarks = () => article.querySelectorAll("mark.reader-match").forEach((mark) => {
    mark.replaceWith(document.createTextNode(mark.textContent));
  });
  const escapeRegex = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const markMatches = (value) => {
    clearMarks();
    article.normalize();
    const query = value.trim();
    if (!query) { outputs.forEach((output) => { output.textContent = ""; }); return; }
    const nodes = [];
    const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) { nodes.push(walker.currentNode); }
    let matches = 0;
    nodes.forEach((node) => {
      const text = node.nodeValue;
      const found = [...text.matchAll(new RegExp(escapeRegex(query), "giu"))];
      if (!found.length) { return; }
      const fragment = document.createDocumentFragment();
      let start = 0;
      found.forEach((match) => {
        const index = match.index;
        fragment.append(document.createTextNode(text.slice(start, index)));
        const mark = document.createElement("mark");
        mark.className = "reader-match";
        mark.textContent = match[0];
        fragment.append(mark);
        matches += 1;
        start = index + match[0].length;
      });
      fragment.append(document.createTextNode(text.slice(start)));
      node.replaceWith(fragment);
    });
    outputs.forEach((output) => { output.textContent = `${matches} match${matches === 1 ? "" : "es"}`; });
  };
  searches.forEach((search) => search.addEventListener("input", () => {
    searches.forEach((peer) => { peer.value = search.value; });
    markMatches(search.value);
  }));
  themes.forEach((theme) => theme.addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    themes.forEach((control) => control.setAttribute("aria-pressed", String(root.dataset.theme === "dark")));
  }));
  prints.forEach((print) => print.addEventListener("click", () => window.print()));
  const links = [...document.querySelectorAll(".reader-outline a[data-section-id]")];
  if ("IntersectionObserver" in window && links.length) {
    const byId = new Map(links.map((link) => [link.dataset.sectionId, link]));
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (!entry.isIntersecting) { return; }
      links.forEach((link) => link.removeAttribute("aria-current"));
      article.querySelectorAll("[data-reader-active]").forEach((section) => section.removeAttribute("data-reader-active"));
      entry.target.setAttribute("data-reader-active", "true");
      byId.get(entry.target.id)?.setAttribute("aria-current", "true");
    }), { rootMargin: "-12% 0px -78% 0px" });
    links.forEach((link) => {
      const section = document.getElementById(link.dataset.sectionId);
      if (section) { observer.observe(section); }
    });
  }
})();
""".strip()


def _slug(value: str, counts: dict[str, int]) -> str:
    """Return a stable, unique heading id for visible heading text."""
    base = "".join(
        character if character.isalnum() else "-"
        for character in normalize("NFKC", value).casefold()
    )
    base = re.sub(r"-+", "-", base).strip("-")
    base = base or "section"
    if base not in counts:
        counts[base] = 1
        return base
    number = counts[base] + 1
    candidate = f"{base}-{number}"
    while candidate in counts:
        number += 1
        candidate = f"{base}-{number}"
    counts[base] = number
    counts[candidate] = 1
    return candidate


def _literal_match_spans(text: str, query: str) -> list[tuple[int, int]]:
    """Return literal Unicode-insensitive match spans in original text offsets."""
    if not query:
        return []
    return [
        (match.start(), match.end())
        for match in re.finditer(re.escape(query), text, flags=re.IGNORECASE)
    ]


def _inline_text(token: Token) -> str:
    """Extract visible text from a Markdown inline token."""
    if not token.children:
        return token.content.strip()
    text: list[str] = []
    for child in token.children:
        if child.type in {"softbreak", "hardbreak"}:
            text.append(" ")
        elif child.type in {"text", "code_inline", "image"}:
            text.append(child.content)
    return "".join(text).strip()


def _decode_path_segment(segment: str) -> str:
    """Decode one URL path segment without permitting separator ambiguity."""
    if "\\" in segment:
        raise ValueError("relative link contains a backslash")
    for index, character in enumerate(segment):
        if character == "%" and (
            index + 2 >= len(segment)
            or segment[index + 1] not in "0123456789abcdefABCDEF"
            or segment[index + 2] not in "0123456789abcdefABCDEF"
        ):
            raise ValueError("relative link contains an invalid percent escape")
    try:
        decoded = unquote_to_bytes(segment).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("relative link is not valid UTF-8") from error
    if "/" in decoded or "\\" in decoded:
        raise ValueError("relative link contains an encoded separator")
    return decoded


def _decode_relative_path(path: str) -> str:
    """Strictly decode a relative URL path segment by segment for lookup."""
    return "/".join(_decode_path_segment(segment) for segment in path.split("/"))


def _normalise_path(base: PurePosixPath, destination: str) -> PurePosixPath:
    target = PurePosixPath(posixpath.normpath(posixpath.join(str(base), destination)))
    if target.is_absolute() or (target.parts and target.parts[0] == ".."):
        raise ValueError("relative link resolves outside the repository")
    return target


def _encode_relative_path(path: str) -> str:
    """Encode every UTF-8 path segment consistently for an HTML destination."""
    return "/".join(
        quote_from_bytes(segment.encode("utf-8"), safe="-._~")
        for segment in PurePosixPath(path).parts
    )


def _raw_suffix(destination: str) -> str:
    """Return the exact query-or-fragment suffix, including empty delimiters."""
    positions = [
        position
        for position in (destination.find("?"), destination.find("#"))
        if position >= 0
    ]
    return destination[min(positions) :] if positions else ""


def rewrite_destination(
    destination: str, source: PurePosixPath, sources: frozenset[PurePosixPath]
) -> str:
    """Rewrite a tracked relative Markdown document link to its HTML sibling."""
    parsed = urlsplit(destination)
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path
        or parsed.path.startswith("/")
    ):
        return destination
    target = _normalise_path(source.parent, _decode_relative_path(parsed.path))
    if target.suffix != ".md" or target not in sources:
        return destination
    output = target.with_suffix(".htm")
    relative = posixpath.relpath(str(output), start=str(source.parent))
    return _encode_relative_path(relative) + _raw_suffix(destination)


def _walk_tokens(tokens: Iterable[Token]) -> Iterable[Token]:
    for token in tokens:
        yield token
        if token.children:
            yield from _walk_tokens(token.children)


def _prepare_tokens(
    parser: MarkdownIt,
    markdown: str,
    source: PurePosixPath,
    sources: frozenset[PurePosixPath],
) -> tuple[list[Token], list[tuple[int, str, str]]]:
    """Parse once, add stable heading ids, build an outline, and rewrite links."""
    tokens = parser.parse(markdown)
    counts: dict[str, int] = {}
    outline: list[tuple[int, str, str]] = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        level = int(token.tag[1:])
        inline = tokens[index + 1]
        text = _inline_text(inline)
        heading_id = _slug(text, counts)
        token.attrSet("id", heading_id)
        if level <= 3:
            outline.append((level, heading_id, text))
    for token in _walk_tokens(tokens):
        if token.type != "link_open":
            continue
        href = token.attrGet("href")
        if href is not None:
            token.attrSet("href", rewrite_destination(href, source, sources))
    return tokens, outline


def _outline_html(outline: list[tuple[int, str, str]]) -> str:
    items = "".join(
        '<li class="level-{level}"><a data-section-id="{identifier}" href="#{identifier}">{text}</a></li>'.format(
            level=level, identifier=escape(identifier, quote=True), text=escape(text)
        )
        for level, identifier, text in outline
    )
    return (
        '<nav class="reader-outline" aria-label="Document outline">'
        "<h2>On this page</h2><ol>" + items + "</ol></nav>"
    )


def _mobile_outline_html(outline: list[tuple[int, str, str]]) -> str:
    """Render a semantic small-screen outline without duplicating heading ids."""
    items = "".join(
        '<li class="level-{level}"><a href="#{identifier}">{text}</a></li>'.format(
            level=level, identifier=escape(identifier, quote=True), text=escape(text)
        )
        for level, identifier, text in outline
    )
    return (
        '<details class="reader-mobile-outline"><summary>On this page</summary>'
        '<nav aria-label="Document outline"><ol>' + items + "</ol></nav></details>"
    )


def render_document(
    source_bytes: bytes, source: PurePosixPath, sources: frozenset[PurePosixPath]
) -> bytes:
    """Render UTF-8 Markdown as a deterministic, self-contained HTML reader."""
    markdown = source_bytes.decode("utf-8", errors="strict")
    parser = MarkdownIt("commonmark", {"html": False, "typographer": False}).enable(
        "table"
    )
    tokens, outline = _prepare_tokens(parser, markdown, source, sources)
    first_heading: str | None = None
    first_h1: str | None = None
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        text = _inline_text(tokens[index + 1])
        first_heading = first_heading if first_heading is not None else text
        if token.tag == "h1" and first_h1 is None:
            first_h1 = text
    title = first_h1 or first_heading or source.stem
    article = parser.renderer.render(tokens, parser.options, {})
    source_path = str(source)
    digest = sha256(source_bytes).hexdigest()
    rendered = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
{GENERATED_MARKER}
<meta name="source-path" content="{escape(source_path, quote=True)}">
<meta name="source-sha256" content="{digest}">
<meta http-equiv="Content-Security-Policy" content="{escape(_CSP, quote=True)}">
<style>{_CSS}</style>
</head>
<body>
<header class="reader-chrome">
<div class="reader-bar"><div class="reader-search"><label for="reader-search">Search</label><input id="reader-search" data-reader-search type="search"><output id="reader-search-output" data-reader-search-output class="reader-search-output" aria-live="polite"></output></div><div class="reader-controls"><button data-theme-toggle type="button" aria-pressed="false">Theme</button><button data-print type="button">Print</button></div></div>
<p class="reader-notice">Generated from <code>{escape(source_path)}</code> (<code>{digest}</code>); edit the Markdown source, not this reader.</p>
</header>
<header class="reader-mobile-header">
<strong class="reader-mobile-title">{escape(title)}</strong><div class="reader-mobile-controls"><button data-theme-toggle type="button" aria-pressed="false">Theme</button><button data-print type="button">Print</button></div>
</header>
<div class="reader-mobile-support"><div class="reader-search"><label for="reader-mobile-search">Search</label><input id="reader-mobile-search" data-reader-search type="search"><output data-reader-search-output class="reader-search-output" aria-live="polite"></output></div><p class="reader-mobile-notice">Generated from <code>{escape(source_path)}</code> (<code>{digest}</code>); edit the Markdown source, not this reader.</p></div>
<div class="reader-stage">{_mobile_outline_html(outline)}<div class="reader-layout">
{_outline_html(outline)}
<main class="reader-main reader-paper"><article id="reader-article">
{article}</article></main>
</div></div>
<script>{_JAVASCRIPT}</script>
</body>
</html>
"""
    return rendered.encode("utf-8")
