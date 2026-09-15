# Wide Review Reader Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Turnkey Blue Zone review reader wide enough for its tables, diagrams, and preformatted text without changing ordinary KIL readers.

**Architecture:** Add an exact, source-controlled `reader-layout: wide` Markdown comment directive. The renderer removes the directive from article content, adds a `reader-wide` body class, and uses responsive CSS that provides a wider article on large screens and collapses the sidebar before it constrains the article on medium screens.

**Tech Stack:** Python 3.12, `markdown-it-py`, `unittest`, self-contained HTML/CSS.

---

### Task 1: Add and apply the wide reader mode

**Files:**
- Modify: `tests/test_markdown_html.py`
- Modify: `tools/render_markdown.py`
- Modify: `docs/design-drafts/2026-09-14-turnkey-blue-zone-strategy.md`
- Generate: `docs/design-drafts/2026-09-14-turnkey-blue-zone-strategy.htm`

- [x] **Step 1: Write the failing renderer test**

Add a test that renders `<!-- reader-layout: wide -->`, requires `<body class="reader-wide">`, requires the directive to be absent from the article, checks the wide 68-rem column and 1120-pixel collapse breakpoint, and confirms an ordinary document still renders `<body>` without the class.

- [x] **Step 2: Run the focused test and verify failure**

Run: `.venv/bin/python -m unittest tests.test_markdown_html.MarkdownRendererTest.test_wide_layout_directive_is_scoped_and_hidden -v`

Expected: FAIL because the renderer does not yet recognize the directive.

- [x] **Step 3: Implement the minimal renderer behavior**

Recognize only an exact leading `<!-- reader-layout: wide -->` line, remove it before Markdown tokenization, keep the original source bytes for the SHA-256 identity, add `class="reader-wide"` to `<body>`, and add scoped wide-layout CSS. Keep the existing standard-reader CSS unchanged.

- [x] **Step 4: Apply the directive to the strategy source**

Place `<!-- reader-layout: wide -->` before the strategy H1 so regeneration selects the reusable layout without manual HTML edits.

- [x] **Step 5: Run focused and full renderer tests**

Run the focused test, then `.venv/bin/python -m unittest tests.test_markdown_html -v`.

Expected: the focused test passes. The full suite remains at its recorded
publication-contract baseline: one failure for the three intentionally
untracked design-draft reader pairs, with no additional failures.

- [x] **Step 6: Regenerate and measure the standalone reader**

Regenerate the strategy and lineage readers. At a 1280-pixel viewport, require the article content width to exceed the previous widest 764-pixel block. At 1000 pixels, require the sidebar to collapse and the document body to have no horizontal overflow. Confirm the embedded image, source hash, HTTPS/internal links, inline assets, and print rules remain intact.

- [x] **Step 7: Record the KIL lineage and final checks**

Append the diagnosis, scoped decision, affected artifacts, verification evidence, and next gate to `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`; regenerate its standalone HTML reader; run `git diff --check`; and report the reviewable `.htm` artifact.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
