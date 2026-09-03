# Self-Contained HTML Readers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and commit one deterministic, self-contained, offline `.htm` reader beside every tracked KIL Markdown document.

**Architecture:** A Python 3.11+ build-time tool discovers tracked Markdown through Git, renders safe static HTML with pinned `markdown-it-py`, rewrites sibling-document links, and either atomically updates or byte-checks the complete output set. Every output embeds the approved document-reader CSS and bounded progressive-enhancement JavaScript; Markdown remains canonical and `make validate` rejects missing, extra, or stale siblings.

**Tech Stack:** Python 3.11+, `markdown-it-py==4.2.0`, `mdurl==0.1.2`, `unittest`, Git, Make, GitHub Actions, static HTML/CSS/JavaScript

---

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

## File map

- Create `requirements-docs.txt`: exact documentation-build dependency pins.
- Create `tools/render_markdown.py`: pure renderer, safe Git-backed discovery,
  generation, and `--check` command.
- Create `tests/test_markdown_html.py`: renderer, security, determinism, CLI,
  and real-corpus contract tests.
- Modify `tests/test_dependency_contract.py`: dependency, CI, Make help, and
  bootstrap contract tests.
- Modify `pyproject.toml`: add the exact `docs` optional dependency group.
- Modify `.github/workflows/ci.yml`: install lab and documentation pins.
- Modify `Makefile`: add `docs-html`, `docs-html-check`, and validation wiring.
- Modify `README.md`: document the canonical/generated relationship and local
  regeneration workflow.
- Modify `tools/README.md`: document renderer behavior and command use.
- Modify `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`: record confirmed
  implementation and verification gates.
- Generate one sibling `.htm` for every tracked `.md`, including this plan and
  the approved design specification.

## Task 1: Pin and disclose the documentation toolchain

**Files:**

- Create: `requirements-docs.txt`
- Modify: `pyproject.toml:12-14`
- Modify: `.github/workflows/ci.yml:15-22`
- Modify: `README.md:115-140`
- Modify: `Makefile:1-15`
- Modify: `tests/test_dependency_contract.py:1-45`

- [ ] **Step 1: Add failing dependency-contract tests**

Extend `DependencyContractTest` with exact, order-sensitive assertions:

```python
    def test_docs_extra_matches_the_exact_requirements_pins(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        requirements = (ROOT / "requirements-docs.txt").read_text().splitlines()
        optional = metadata["project"].get("optional-dependencies", {})

        self.assertEqual(
            requirements,
            ["markdown-it-py==4.2.0", "mdurl==0.1.2"],
        )
        self.assertEqual(optional.get("docs"), requirements)

    def test_ci_installs_docs_requirements_before_validation(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        install = (
            "python -m pip install --disable-pip-version-check "
            "-r requirements-lab.txt -r requirements-docs.txt"
        )

        self.assertIn(install, workflow)
        self.assertLess(workflow.index(install), workflow.index("make validate"))

    def test_bootstrap_documents_both_extras(self):
        readme = (ROOT / "README.md").read_text()

        self.assertIn('python -m pip install -e ".[lab,docs]"', readme)

    def test_make_help_discloses_the_docs_dependency(self):
        makefile = (ROOT / "Makefile").read_text()

        self.assertIn("docs-html", makefile)
        self.assertIn("requires lab and docs dependencies", makefile)
```

Replace the existing CI install assertion with the combined two-file command
and replace the existing bootstrap/help assertions with the combined extras
language so no stale one-extra contract remains.

- [ ] **Step 2: Run the dependency tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest \
  tests.test_dependency_contract -v
```

Expected: failures report missing `requirements-docs.txt`, missing `docs`
metadata, the old CI installation command, and old bootstrap/help text.

- [ ] **Step 3: Add exact pins and integration text**

Create `requirements-docs.txt` with exactly:

```text
markdown-it-py==4.2.0
mdurl==0.1.2
```

Add to `pyproject.toml`:

```toml
docs = [
  "markdown-it-py==4.2.0",
  "mdurl==0.1.2",
]
```

Change the GitHub Actions installation step to:

```yaml
      - run: python -m pip install --disable-pip-version-check -r requirements-lab.txt -r requirements-docs.txt
```

Change README bootstrap installation to:

```bash
python -m pip install -e ".[lab,docs]"
```

Change Make help text to say the complete tests require both lab and docs
dependencies. Add help lines for `docs-html` and `docs-html-check`; their
targets are implemented in Task 4.

- [ ] **Step 4: Install the pins and verify GREEN**

Run:

```bash
python -m pip install --disable-pip-version-check -r requirements-docs.txt
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest \
  tests.test_dependency_contract -v
```

Expected: dependency-contract tests pass and the installed versions are exactly
`markdown-it-py 4.2.0` and `mdurl 0.1.2`.

- [ ] **Step 5: Commit the dependency contract**

```bash
git add requirements-docs.txt pyproject.toml .github/workflows/ci.yml \
  README.md Makefile tests/test_dependency_contract.py
git commit -m "build: pin Markdown reader toolchain"
```

## Task 2: Build the safe deterministic renderer

**Files:**

- Create: `tests/test_markdown_html.py`
- Create: `tools/render_markdown.py`

- [ ] **Step 1: Write failing pure-renderer tests**

Create `tests/test_markdown_html.py` with imports and fixtures that load the
tool directly from its repository path:

```python
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path, PurePosixPath
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location(
    "render_markdown", ROOT / "tools/render_markdown.py"
)
assert SPEC is not None and SPEC.loader is not None
render_markdown = module_from_spec(SPEC)
SPEC.loader.exec_module(render_markdown)


class MarkdownRendererTest(unittest.TestCase):
    def setUp(self):
        self.source = PurePosixPath("docs/guide.md")
        self.sources = frozenset(
            {self.source, PurePosixPath("docs/other.md")}
        )

    def render(self, markdown: str) -> str:
        return render_markdown.render_document(
            markdown.encode("utf-8"), self.source, self.sources
        ).decode("utf-8")

    def test_renders_static_article_tables_code_and_unicode(self):
        rendered = self.render(
            "# Café Guide\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n"
            "```python\nprint('safe')\n```\n"
        )

        self.assertIn('<h1 id="café-guide">Café Guide</h1>', rendered)
        self.assertIn("<table>", rendered)
        self.assertIn('<code class="language-python">', rendered)
        self.assertIn("print('safe')", rendered)
        self.assertIn('<main class="reader-main">', rendered)

    def test_rewrites_only_tracked_relative_markdown_links(self):
        rendered = self.render(
            "[Other](other.md?view=1#part) "
            "[Web](https://example.com/readme.md) "
            "[Missing](missing.md) [Here](#part)\n"
        )

        self.assertIn('href="other.htm?view=1#part"', rendered)
        self.assertIn('href="https://example.com/readme.md"', rendered)
        self.assertIn('href="missing.md"', rendered)
        self.assertIn('href="#part"', rendered)

    def test_escapes_raw_html_and_uses_no_remote_runtime_assets(self):
        rendered = self.render(
            "# Safe\n\n<script>alert(1)</script>\n"
            "<img src=x onerror=alert(2)>\n"
        )

        article = rendered.split('<article id="reader-article">', 1)[1]
        self.assertNotIn("<script>", article)
        self.assertIn("&lt;script&gt;", article)
        self.assertIn("&lt;img src=x onerror=alert(2)&gt;", article)
        self.assertNotIn("<img src=x", article)
        self.assertNotRegex(rendered, r'<script[^>]+src=')
        self.assertNotRegex(rendered, r'<link[^>]+stylesheet')
        self.assertNotIn("fetch(", rendered)
        self.assertIn("connect-src &#x27;none&#x27;", rendered)

    def test_heading_ids_are_unique_and_deterministic(self):
        rendered = self.render("## Same\n\n## Same\n\n## !!!\n")

        self.assertIn('id="same"', rendered)
        self.assertIn('id="same-2"', rendered)
        self.assertIn('id="section"', rendered)
        self.assertEqual(rendered, self.render("## Same\n\n## Same\n\n## !!!\n"))

    def test_embeds_source_identity_and_full_no_script_content(self):
        source = b"# Identity\n\nComplete article.\n"
        rendered = render_markdown.render_document(
            source, self.source, self.sources
        ).decode("utf-8")

        self.assertIn('content="docs/guide.md"', rendered)
        self.assertIn(
            f'content="{sha256(source).hexdigest()}"', rendered
        )
        self.assertIn("Complete article.", rendered)
        self.assertNotIn("document.write", rendered)
```

- [ ] **Step 2: Run the renderer tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest \
  tests.test_markdown_html.MarkdownRendererTest -v
```

Expected: import fails because `tools/render_markdown.py` does not exist.

- [ ] **Step 3: Implement path rewriting, slugs, and token processing**

Create `tools/render_markdown.py` with these public constants and helpers:

```python
from __future__ import annotations

from argparse import ArgumentParser
from hashlib import sha256
from html import escape
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit
import os
import posixpath
import re
import subprocess
import sys
import unicodedata

from markdown_it import MarkdownIt
from markdown_it.token import Token


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = "KIL Markdown Reader 1"
GENERATED_MARKER = '<meta name="generator" content="KIL Markdown Reader 1">'


def _slug(value: str, counts: dict[str, int]) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    base = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE).strip("-")
    base = base or "section"
    counts[base] = counts.get(base, 0) + 1
    return base if counts[base] == 1 else f"{base}-{counts[base]}"


def _inline_text(token: Token) -> str:
    pieces: list[str] = []
    for child in token.children or []:
        if child.type in {"text", "code_inline", "image"}:
            pieces.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            pieces.append(" ")
    return "".join(pieces).strip()


def rewrite_destination(
    destination: str,
    source: PurePosixPath,
    sources: frozenset[PurePosixPath],
) -> str:
    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return destination
    if parsed.path.startswith("/"):
        return destination
    normalized = posixpath.normpath(
        (source.parent / PurePosixPath(parsed.path)).as_posix()
    )
    target = PurePosixPath(normalized)
    if target.is_absolute() or ".." in target.parts:
        raise ValueError(f"link escapes repository: {destination}")
    if target not in sources:
        return destination
    output = target.with_suffix(".htm")
    relative = posixpath.relpath(output.as_posix(), source.parent.as_posix())
    return urlunsplit(("", "", relative, parsed.query, parsed.fragment))


def _prepare_tokens(
    parser: MarkdownIt,
    markdown: str,
    source: PurePosixPath,
    sources: frozenset[PurePosixPath],
) -> tuple[list[Token], list[tuple[int, str, str]]]:
    tokens = parser.parse(markdown)
    outline: list[tuple[int, str, str]] = []
    counts: dict[str, int] = {}
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            inline = tokens[index + 1]
            title = _inline_text(inline)
            identifier = _slug(title, counts)
            token.attrSet("id", identifier)
            outline.append((int(token.tag[1]), identifier, title))
        if token.type != "inline":
            continue
        for child in token.children or []:
            if child.type != "link_open":
                continue
            href = child.attrGet("href")
            if href is not None:
                child.attrSet(
                    "href", rewrite_destination(href, source, sources)
                )
    return tokens, outline
```

- [ ] **Step 4: Implement the self-contained template and renderer**

Add a compact, complete static template. The exact implementation may wrap the
following constants for line length, but must preserve these declarations and
behaviors verbatim:

```python
READER_CSS = r"""
:root{color-scheme:light;--canvas:#eef1eb;--paper:#fffdf7;--ink:#18201d;
--muted:#65716b;--line:#d8ddd4;--accent:#087f6b;--soft:#dff3ec;
--code:#16211e;--code-ink:#d8f5e9}
:root[data-theme="dark"]{color-scheme:dark;--canvas:#101714;--paper:#17201c;
--ink:#edf5f0;--muted:#a2b1aa;--line:#314039;--accent:#5bd7b8;
--soft:#1d4439;--code:#0b100e;--code-ink:#baf0dc}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--canvas);
color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}
.reader-shell{min-height:100vh;display:grid;grid-template-columns:290px minmax(0,1fr)}
.reader-rail{position:sticky;top:0;height:100vh;padding:28px 22px;border-right:1px solid
var(--line);background:var(--paper);overflow:auto}.reader-rail a{color:var(--muted);
text-decoration:none}.reader-rail a:hover,.reader-rail a.active{color:var(--accent)}
.reader-search{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:9px;
background:var(--canvas);color:var(--ink)}.reader-outline{display:grid;gap:7px;margin-top:20px}
.reader-outline .level-2{padding-left:12px}.reader-outline .level-3{padding-left:24px}
.reader-stage{min-width:0;padding:42px clamp(24px,6vw,88px) 80px}.reader-paper{width:min(900px,100%);
margin:auto;padding:clamp(34px,7vw,84px);border:1px solid var(--line);border-radius:18px;
background:var(--paper)}.generated-note{padding:11px 14px;border:1px solid var(--line);
border-radius:9px;background:var(--soft);color:var(--accent);font-size:.82rem}
article{font-family:Georgia,'Times New Roman',serif;font-size:1.08rem;line-height:1.78}
article h1,article h2,article h3{scroll-margin-top:24px;line-height:1.18}
article h1{font-size:clamp(2.5rem,7vw,4.7rem)}article h2{margin-top:2.2em;border-bottom:1px solid var(--line)}
article img{max-width:100%;height:auto}article table{display:block;max-width:100%;overflow:auto;
border-collapse:collapse}th,td{padding:8px 10px;border:1px solid var(--line)}pre{overflow:auto;
padding:18px 20px;border-radius:10px;background:var(--code);color:var(--code-ink)}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}a{color:var(--accent)}mark{background:#ffe27a;color:#202018}
.reader-actions{display:flex;gap:8px;margin-top:24px}.reader-actions button{padding:8px;border:1px solid
var(--line);border-radius:8px;background:transparent;color:var(--muted)}
@media(max-width:820px){.reader-shell{display:block}.reader-rail{position:static;width:auto;height:auto;
border-right:0;border-bottom:1px solid var(--line)}.reader-stage{padding:18px 12px 50px}.reader-paper{padding:32px 22px}}
@media print{.reader-rail,.generated-note{display:none}.reader-shell{display:block}.reader-stage,
.reader-paper{width:auto;margin:0;padding:0;border:0}}
""".strip()

READER_JS = r"""
const root=document.documentElement;
const article=document.getElementById('reader-article');
const search=document.getElementById('reader-search');
const original=article.innerHTML;
document.getElementById('theme-toggle').addEventListener('click',()=>{
  root.dataset.theme=root.dataset.theme==='dark'?'':'dark';
});
document.getElementById('print-reader').addEventListener('click',()=>window.print());
search.addEventListener('input',()=>{
  const query=search.value.trim();article.innerHTML=original;
  if(query.length<2)return;
  const walker=document.createTreeWalker(article,NodeFilter.SHOW_TEXT);const nodes=[];
  while(walker.nextNode())nodes.push(walker.currentNode);
  for(const node of nodes){const index=node.data.toLowerCase().indexOf(query.toLowerCase());
    if(index<0)continue;const hit=document.createElement('mark');
    hit.textContent=node.data.slice(index,index+query.length);
    node.replaceWith(document.createTextNode(node.data.slice(0,index)),hit,
      document.createTextNode(node.data.slice(index+query.length)));}
  article.querySelector('mark')?.scrollIntoView({block:'center'});
});
const links=[...document.querySelectorAll('.reader-outline a')];
const observer=new IntersectionObserver(entries=>{for(const entry of entries){if(!entry.isIntersecting)continue;
  links.forEach(link=>link.classList.toggle('active',link.hash==='#'+entry.target.id));}},
  {rootMargin:'-15% 0px -70%'});
document.querySelectorAll('#reader-article h1[id],#reader-article h2[id],#reader-article h3[id]')
  .forEach(heading=>observer.observe(heading));
""".strip()


def render_document(
    source_bytes: bytes,
    source: PurePosixPath,
    sources: frozenset[PurePosixPath],
) -> bytes:
    markdown = source_bytes.decode("utf-8")
    parser = MarkdownIt("commonmark", {"html": False, "typographer": False})
    parser.enable("table")
    tokens, outline = _prepare_tokens(parser, markdown, source, sources)
    body = parser.renderer.render(tokens, parser.options, {})
    title_entry = next((item for item in outline if item[0] == 1), None)
    title_entry = title_entry or (outline[0] if outline else None)
    title = title_entry[2] if title_entry else source.stem
    outline_html = "".join(
        f'<a class="level-{level}" href="#{escape(identifier, quote=True)}">'
        f"{escape(label)}</a>"
        for level, identifier, label in outline
        if level <= 3
    )
    digest = sha256(source_bytes).hexdigest()
    policy = (
        "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
        "script-src 'unsafe-inline'; font-src 'none'; connect-src 'none'; "
        "object-src 'none'; base-uri 'none'; form-action 'none'"
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{escape(policy, quote=True)}">
{GENERATED_MARKER}
<meta name="source-path" content="{escape(source.as_posix(), quote=True)}">
<meta name="source-sha256" content="{digest}">
<title>{escape(title)} — KIL Reader</title><style>{READER_CSS}</style></head>
<body><div class="reader-shell"><aside class="reader-rail">
<strong>{escape(title)}</strong>
<input class="reader-search" id="reader-search" type="search" placeholder="Find in this document…">
<nav class="reader-outline" aria-label="Document outline">{outline_html}</nav>
<div class="reader-actions"><button id="theme-toggle" type="button">Theme</button>
<button id="print-reader" type="button">Print</button></div></aside>
<main class="reader-main reader-stage"><div class="reader-paper">
<p class="generated-note">Generated from <code>{escape(source.as_posix())}</code>
({digest}). Edit the Markdown source, not this reader.</p>
<article id="reader-article">{body}</article></div></main></div>
<script>{READER_JS}</script></body></html>
"""
    return document.encode("utf-8")
```

- [ ] **Step 5: Run the pure-renderer tests and verify GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest \
  tests.test_markdown_html.MarkdownRendererTest -v
```

Expected: all renderer tests pass with no network or filesystem writes.

- [ ] **Step 6: Commit the pure renderer**

```bash
git add tools/render_markdown.py tests/test_markdown_html.py
git commit -m "feat: render self-contained Markdown readers"
```

## Task 3: Add safe repository discovery, write, and check modes

**Files:**

- Modify: `tests/test_markdown_html.py`
- Modify: `tools/render_markdown.py`

- [ ] **Step 1: Add failing discovery and lifecycle tests**

Add a temporary Git-repository test class. It initializes each repository with
local test-only author configuration and uses `render_repository` directly:

```python
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from tempfile import TemporaryDirectory
import subprocess


class RepositoryGenerationTest(unittest.TestCase):
    def setUp(self):
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

    def tearDown(self):
        self.temporary.cleanup()

    def track(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "--", relative], cwd=self.root, check=True)

    def test_generates_exact_sibling_set_and_check_is_read_only(self):
        self.track("README.md", "# Root\n\n[Guide](docs/guide.md)\n")
        self.track("docs/guide.md", "# Guide\n")
        before = {
            path: (self.root / path).read_bytes()
            for path in ("README.md", "docs/guide.md")
        }

        self.assertEqual(render_markdown.render_repository(self.root), [])
        self.assertTrue((self.root / "README.htm").is_file())
        self.assertTrue((self.root / "docs/guide.htm").is_file())
        html_before = (self.root / "README.htm").read_bytes()
        self.assertEqual(
            render_markdown.render_repository(self.root, check=True), []
        )
        self.assertEqual((self.root / "README.htm").read_bytes(), html_before)
        self.assertEqual(
            {path: (self.root / path).read_bytes() for path in before}, before
        )

    def test_check_reports_missing_stale_and_unexpected_outputs(self):
        self.track("README.md", "# Root\n")
        self.assertEqual(
            render_markdown.render_repository(self.root, check=True),
            ["missing README.htm"],
        )
        render_markdown.render_repository(self.root)
        (self.root / "README.htm").write_text("stale", encoding="utf-8")
        self.assertEqual(
            render_markdown.render_repository(self.root, check=True),
            ["stale README.htm"],
        )
        render_markdown.render_repository(self.root)
        (self.root / "extra.htm").write_text("manual", encoding="utf-8")
        self.assertEqual(
            render_markdown.render_repository(self.root, check=True),
            ["unexpected extra.htm"],
        )

    def test_render_failure_preserves_existing_output(self):
        self.track("README.md", "# Root\n")
        render_markdown.render_repository(self.root)
        output = self.root / "README.htm"
        before = output.read_bytes()
        (self.root / "README.md").write_bytes(b"\xff")

        with self.assertRaises(UnicodeDecodeError):
            render_markdown.render_repository(self.root)

        self.assertEqual(output.read_bytes(), before)

    def test_ignored_html_does_not_expand_the_publication_set(self):
        self.track("README.md", "# Root\n")
        (self.root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
        (self.root / "ignored").mkdir()
        (self.root / "ignored/private.htm").write_text("private", encoding="utf-8")

        render_markdown.render_repository(self.root)
        self.assertEqual(
            render_markdown.render_repository(self.root, check=True), []
        )
```

- [ ] **Step 2: Run lifecycle tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest \
  tests.test_markdown_html.RepositoryGenerationTest -v
```

Expected: failures report that `render_repository` is absent.

- [ ] **Step 3: Implement Git-backed discovery and exact checking**

Add these functions to `tools/render_markdown.py`:

```python
def _git_paths(root: Path, patterns: tuple[str, ...]) -> tuple[PurePosixPath, ...]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *patterns],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    values = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        relative = PurePosixPath(raw.decode("utf-8"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe repository path: {relative}")
        values.append(relative)
    if len(values) != len(set(values)):
        raise ValueError("duplicate repository path")
    return tuple(sorted(values, key=lambda value: value.as_posix().encode("utf-8")))


def discover_sources(root: Path) -> tuple[PurePosixPath, ...]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    sources = tuple(
        sorted(
            (PurePosixPath(raw.decode("utf-8")) for raw in tracked.split(b"\0") if raw),
            key=lambda value: value.as_posix().encode("utf-8"),
        )
    )
    if len(sources) != len(set(sources)):
        raise ValueError("duplicate Markdown source")
    for source in sources:
        path = root / source
        if source.is_absolute() or ".." in source.parts or path.is_symlink() or not path.is_file():
            raise ValueError(f"unsafe Markdown source: {source}")
        path.resolve().relative_to(root.resolve())
    return sources


def _visible_html(root: Path) -> frozenset[PurePosixPath]:
    return frozenset(_git_paths(root, ("*.htm",)))


def expected_documents(root: Path) -> dict[PurePosixPath, bytes]:
    sources = discover_sources(root)
    source_set = frozenset(sources)
    expected: dict[PurePosixPath, bytes] = {}
    for source in sources:
        output = source.with_suffix(".htm")
        if output in expected:
            raise ValueError(f"output collision: {output}")
        expected[output] = render_document((root / source).read_bytes(), source, source_set)
    return expected


def render_repository(root: Path = ROOT, check: bool = False) -> list[str]:
    expected = expected_documents(root)
    visible = _visible_html(root)
    problems = [f"missing {path}" for path in sorted(set(expected) - visible)]
    problems.extend(f"unexpected {path}" for path in sorted(visible - set(expected)))
    for relative, payload in expected.items():
        path = root / relative
        if path.is_file() and path.read_bytes() != payload:
            problems.append(f"stale {relative}")
    problems = sorted(set(problems))
    if check:
        return problems
    unexpected = sorted(visible - set(expected))
    if unexpected:
        return [f"unexpected {path}" for path in unexpected]

    temporary: list[tuple[Path, Path]] = []
    try:
        for relative, payload in expected.items():
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
            staging.write_bytes(payload)
            temporary.append((staging, destination))
        for staging, destination in temporary:
            os.replace(staging, destination)
    finally:
        for staging, _ in temporary:
            if staging.exists():
                staging.unlink()
    return []
```

During implementation, use a dedicated `discover_sources` command rather than
the broader `_git_paths` helper for `.md`: untracked Markdown is not part of the
publication set, whereas generated untracked `.htm` must be visible immediately
after generation. Keep that asymmetry covered by the tests.

- [ ] **Step 4: Add the command-line entry point**

```python
def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Render tracked Markdown as sibling HTML readers")
    parser.add_argument("--check", action="store_true", help="verify without writing")
    arguments = parser.parse_args(argv)
    try:
        problems = render_repository(ROOT, check=arguments.check)
    except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"markdown reader error: {error}", file=sys.stderr)
        return 1
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    action = "verified" if arguments.check else "generated"
    print(f"{action} {len(discover_sources(ROOT))} Markdown readers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run lifecycle and renderer tests and verify GREEN**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest \
  tests.test_markdown_html -v
```

Expected: all pure-renderer and repository-generation tests pass.

- [ ] **Step 6: Commit lifecycle support**

```bash
git add tools/render_markdown.py tests/test_markdown_html.py
git commit -m "feat: generate and verify sibling HTML corpus"
```

## Task 4: Wire Make, documentation, CI, and the real corpus

**Files:**

- Modify: `Makefile`
- Modify: `README.md`
- Modify: `tools/README.md`
- Modify: `tests/test_markdown_html.py`
- Generate: every tracked `*.htm` sibling

- [ ] **Step 1: Add failing real-repository contract tests**

Add to `tests/test_markdown_html.py`:

```python
class RepositoryPublicationContractTest(unittest.TestCase):
    def test_every_tracked_markdown_has_exact_generated_sibling(self):
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

        self.assertGreaterEqual(len(sources), 47)
        self.assertEqual(tracked, expected)

    def test_checked_in_readers_are_current_and_sources_are_unchanged(self):
        before = {
            source: (ROOT / source).read_bytes()
            for source in render_markdown.discover_sources(ROOT)
        }

        self.assertEqual(
            render_markdown.render_repository(ROOT, check=True), []
        )
        self.assertEqual(
            {source: (ROOT / source).read_bytes() for source in before}, before
        )

    def test_byte_preserved_drafts_match_their_recorded_checksums(self):
        recorded = dict(
            reversed(line.split("  ", 1))
            for line in (
                ROOT / "research/source-material/SHA256SUMS"
            ).read_text().splitlines()
            if line
        )
        for name in (
            "docs/drafts/kil-trust-decay-model.md",
            "docs/drafts/ambient-enforcement-vs-huggingface-incident.md",
        ):
            digest = sha256((ROOT / name).read_bytes()).hexdigest()
            self.assertEqual(digest, recorded[name])
```

- [ ] **Step 2: Run the publication test and verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest \
  tests.test_markdown_html.RepositoryPublicationContractTest -v
```

Expected: failure because the sibling `.htm` corpus is not generated or tracked.

- [ ] **Step 3: Add Make targets and documentation**

Add to `.PHONY` and implement:

```make
docs-html: check-python
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src $(PYTHON) tools/render_markdown.py

docs-html-check: check-python
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src $(PYTHON) tools/render_markdown.py --check
```

Change validation ordering to:

```make
validate: test docs-html-check
	$(PYTHON) -c "from pathlib import Path; assert '[project]' in Path('pyproject.toml').read_text()"
	git diff --check
```

Add this contract to the root README near bootstrap instructions:

````markdown
## Offline HTML readers

Every tracked Markdown document has a generated `.htm` sibling in the same
directory. Markdown is canonical; do not edit generated readers directly.

```bash
make docs-html
make docs-html-check
```

The readers are self-contained and open directly from disk. Regeneration
requires the `docs` optional dependency; `make validate` rejects missing,
unexpected, or stale siblings.
````

Add the command, source-of-record rule, safe rendering policy, and `--check`
behavior to `tools/README.md` using the same precise claims.

- [ ] **Step 4: Generate and stage the exact corpus**

Run:

```bash
make docs-html PYTHON=python
git add -- '*.htm' '**/*.htm'
```

If shell glob behavior is inconsistent, stage from the generator's exact mapped
path list rather than using a broad force-add. Do not add ignored visual
companion or generated lab artifacts.

Expected: one sibling is generated for every tracked Markdown source, including
the design and this plan; no source Markdown byte changes as a consequence of
generation.

- [ ] **Step 5: Verify GREEN and deterministic regeneration**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest \
  tests.test_markdown_html -v
make docs-html-check PYTHON=python
make docs-html PYTHON=python
git diff --exit-code -- '*.htm'
```

Expected: all tests pass, check mode reports the exact reader count, a second
generation produces no tracked HTML changes, and Markdown source hashes remain
unchanged except for explicitly authored README/tool/lineage documentation.

- [ ] **Step 6: Commit build integration and generated readers**

```bash
git add Makefile README.md tools/README.md tests/test_markdown_html.py \
  .github/workflows/ci.yml pyproject.toml requirements-docs.txt
git add -- '*.htm' '**/*.htm'
git commit -m "docs: publish self-contained HTML readers"
```

## Task 5: Inspect representative readers and close the evidence gate

**Files:**

- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Regenerate: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm`

- [ ] **Step 1: Run complete automated verification**

```bash
make validate PYTHON=python
git diff --check
```

Expected: all unit tests, publication freshness, metadata, and diff-hygiene
checks pass with zero failures.

- [ ] **Step 2: Inspect representative documents**

Open and inspect these local files at desktop and narrow viewport widths:

```text
README.htm
docs/paper/kinetic-infrastructure.htm
docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm
docs/superpowers/plans/2026-08-29-v2-historical-replay.htm
tests/fixtures/v3b1-public-bundle-v1/README.htm
```

Confirm full content without JavaScript, working outline fragments, responsive
tables/code, local images, sibling `.htm` navigation, search, theme, print
styles, source path/digest notice, and no automatic network request.

- [ ] **Step 3: Obtain an independent code review**

Ask a reviewer to compare the implementation against the approved design and
inspect safety, deterministic regeneration, corpus coverage, source
preservation, tests, and documentation. Resolve every Critical or Important
finding and rerun focused plus complete verification. Record Minor findings and
their disposition explicitly.

- [ ] **Step 4: Append the implementation lineage entry and regenerate it**

Record input, interpretation, confirmed implementation status, rationale,
affected artifacts, exact test count, representative visual inspection,
review disposition, unresolved questions, and the final push gate in
`docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`. Then run:

```bash
make docs-html PYTHON=python
make docs-html-check PYTHON=python
```

The updated lineage Markdown and HTML digest must agree.

- [ ] **Step 5: Run final clean-state verification and commit evidence**

```bash
make validate PYTHON=python
git diff --check
git status --short
git add docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md \
  docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm
git commit -m "docs: record HTML reader verification"
```

Expected: the complete suite passes, only intended files are committed, and the
working tree is clean after the evidence commit.

- [ ] **Step 6: Push once and verify exact synchronization**

```bash
git push -u origin codex/self-contained-html-readers
git rev-parse HEAD
git rev-parse '@{upstream}'
git ls-remote --heads origin codex/self-contained-html-readers
```

Expected: all three commands resolve to the same full commit hash. Do not create
a pull request, merge, comment on issues, close issues, or start a KIL lab
service unless the maintainer separately requests it.
