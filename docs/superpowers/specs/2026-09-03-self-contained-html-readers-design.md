# Self-Contained HTML Readers Design

**Status:** Approved design

**Date:** 2026-09-03

**Scope:** Deterministic sibling `.htm` readers for every tracked Markdown
document in KIL

## Context

KIL currently stores its prose, plans, fixtures, repository instructions, and
research records as Markdown. A reader without a Markdown renderer must either
read the source syntax or install separate tooling. The maintainer requires an
offline-readable `.htm` sibling beside every tracked `.md` file, with a strict
one-to-one mapping and the single-page reader experience approved in the
`kinetic-infrastructure.md` visual sample.

Markdown remains canonical. HTML readers are deterministic derived artifacts.
This feature changes presentation and publication mechanics only; it does not
change KIL behavior, KTP semantics, evidence classifications, or laboratory
claims.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

## Goals

1. Give every tracked Markdown document an immediately discoverable sibling
   reader: `path/name.md` maps to `path/name.htm`.
2. Make every reader open directly from a local filesystem without a server,
   network dependency, package installation, or Markdown converter.
3. Preserve complete rendered content when JavaScript is disabled.
4. Provide bounded single-page enhancements: outline navigation, document
   search, theme switching, active-section indication, and print styling.
5. Rewrite relative links between tracked Markdown documents so HTML readers
   continue through the sibling HTML corpus.
6. Make generation reproducible and make missing, extra, or stale outputs fail
   repository validation.
7. Preserve every source Markdown byte, including files under `docs/drafts/`.

## Non-goals

- Hosting or deploying a website.
- Combining the corpus into one cross-document application or search index.
- Replacing Markdown as the source of record.
- Rendering Mermaid in the browser or adding syntax-highlighting libraries.
- Fetching remote fonts, styles, scripts, images, telemetry, or analytics.
- Editing KTP content or changing the meaning of KIL claims.
- Making an external citation available offline; external destinations remain
  ordinary links and require connectivity only when selected.

## Publication boundary and mapping

The generator obtains the publication set from Git rather than from a broad
filesystem walk:

```text
git ls-files -z -- *.md
```

It decodes paths as UTF-8, converts them to repository-relative POSIX paths,
sorts them by their encoded path value, and rejects duplicate or unsafe paths.
No tracked Markdown file is excluded. The set therefore includes root files,
repository instructions, reader-facing documentation, internal plans and
specifications, historical drafts, research records, and test fixtures.

For every source, the output changes only the final suffix:

```text
README.md                                    -> README.htm
docs/paper/kinetic-infrastructure.md         -> docs/paper/kinetic-infrastructure.htm
tests/fixtures/example/summary.md            -> tests/fixtures/example/summary.htm
```

The `.htm` namespace is reserved for these generated readers. Local validation
requires the non-ignored on-disk `.htm` set to equal the mapped tracked `.md`
set exactly, allowing validation immediately after generation and before Git
staging. Committed delivery separately requires every expected `.htm` to be
tracked and no other `.htm` file to be tracked.
The generator discovers the final count at execution time. The repository had
45 tracked Markdown files before this design was added; the design and its
implementation plan are themselves Markdown sources and therefore also receive
sibling readers.

## Toolchain and dependencies

The generator uses Python 3.11 or newer, matching KIL's existing runtime floor.
Markdown parsing uses `markdown-it-py==4.2.0`, with its direct URL dependency
explicitly fixed as `mdurl==0.1.2`. Both are documentation-build dependencies,
not KIL runtime dependencies. `markdown-it-py` 4.2.0 is the current stable
release and supports Python 3.10 and newer according to its
[authoritative PyPI record](https://pypi.org/project/markdown-it-py/4.2.0/).

The pins appear in both places used by this repository's dependency contract:

- a `docs` optional dependency group in `pyproject.toml`; and
- `requirements-docs.txt`, installed by CI beside `requirements-lab.txt`.

The parser is configured from the CommonMark preset with the table rule
enabled. Raw HTML is disabled. Linkification, typographic substitution,
third-party plugins, syntax highlighting, and runtime diagram rendering remain
disabled so the result is bounded and deterministic.

## Components

### `tools/render_markdown.py`

This module owns source discovery, parsing, heading identity, link rewriting,
template rendering, output verification, and command-line behavior. It exposes
small pure functions so formatting and safety behavior can be tested without
writing repository files.

The command has two modes:

```text
python tools/render_markdown.py
python tools/render_markdown.py --check
```

The default mode stages all expected bytes and then updates sibling outputs.
`--check` writes nothing; it compares each existing sibling byte-for-byte with
the expected rendering and rejects missing, unexpected, or stale `.htm` files.
Both modes return nonzero for an invalid path, non-UTF-8 source, parser failure,
output collision, unsafe resolved link, or filesystem error.

### `tests/test_markdown_html.py`

This test module covers pure rendering behavior, link resolution, security
properties, deterministic bytes, command failure behavior, and the real
repository's one-to-one publication contract.

### Make and CI integration

The Makefile adds:

```text
docs-html        regenerate every sibling reader
docs-html-check  verify exact coverage and freshness without writing
```

`validate` depends on `docs-html-check` after the unit suite. Help output
documents both targets and the documentation dependency. GitHub Actions installs
both pinned requirements files before running `make validate`.

### Repository guidance

The root README and `tools/README.md` explain that Markdown is canonical, HTML
is generated, `make docs-html` performs regeneration, and `make validate`
rejects drift. They also warn contributors not to edit `.htm` siblings by hand.

## Rendering data flow

For one source document, generation proceeds as follows:

```text
tracked UTF-8 Markdown bytes
  -> SHA-256 source identity
  -> markdown-it token stream
  -> stable heading IDs and outline
  -> resolved sibling-link rewrites
  -> escaped static article HTML
  -> self-contained reader template
  -> UTF-8 bytes with one final newline
```

The first level-one heading becomes the display title. If no level-one heading
exists, the first heading of any level is used. If no heading exists, the source
filename without `.md` becomes the title.

Heading IDs are derived from visible heading text by Unicode NFKC
normalization, case folding, conversion of non-alphanumeric runs to hyphens,
and removal of leading or trailing hyphens. An empty result becomes `section`.
Repeated IDs receive `-2`, `-3`, and later numeric suffixes in document order.
The outline includes levels one through three and links to those stable IDs.

## Link rewriting

Only link destination tokens are eligible for rewriting. Code, literal text,
and image destinations are never rewritten as prose.

For a destination without a URI scheme or network location, the generator:

1. separates its path, query, and fragment;
2. resolves the path against the source Markdown directory;
3. rejects traversal outside the repository root;
4. checks whether the resolved path is a tracked Markdown source; and
5. if so, changes the destination suffix from `.md` to `.htm` while preserving
   query and fragment components.

Pure fragment links remain within the current document. Absolute URLs,
protocol-relative URLs, `mailto:`, and other explicit schemes remain unchanged.
Relative links to images, schemas, source files, PDFs, and existing HTML remain
unchanged. A relative `.md` link that does not resolve to the tracked source set
also remains unchanged so generation does not disguise an existing broken or
external-by-convention reference.

## Reader application

Each `.htm` is an independent document-centric single-page application. The
complete article is present in the initial HTML document. Outline selections
use local fragments and do not load a new application route. No action performs
an automatic network request.

The reader uses the approved visual direction:

- a restrained paper surface on a neutral canvas;
- a sticky desktop outline and compact mobile header;
- system fonts only;
- responsive tables and code blocks with horizontal overflow;
- readable measure, contrast, and spacing;
- light and dark themes;
- print rules that remove application chrome; and
- an explicit generated-file notice with the source path and source digest.

JavaScript progressively enhances search, theme switching, current-section
highlighting, and print activation. Search operates only on text nodes already
present in the article. It neither evaluates source content nor sends queries
elsewhere. If JavaScript is disabled or blocked, the full document, links,
outline, images, tables, and code remain readable; only those enhancements are
unavailable.

## Offline and content-security boundary

All CSS and JavaScript are embedded. The output contains no stylesheet link,
script source, module import, remote font, preload, iframe, media embed,
analytics beacon, service worker, or fetch/XHR call.

Raw Markdown HTML is treated as text and escaped by the parser. This prevents a
tracked Markdown file from turning a generated local reader into an executable
HTML injection surface. Fenced Mermaid blocks remain escaped, labeled code
blocks rather than acquiring a diagram runtime.

Each reader contains a content-security policy equivalent to:

```text
default-src 'none';
img-src 'self' data:;
style-src 'unsafe-inline';
script-src 'unsafe-inline';
font-src 'none';
connect-src 'none';
object-src 'none';
base-uri 'none';
form-action 'none'
```

Inline style and script allowances are intentionally narrow consequences of a
single-file offline artifact. The generator supplies all executable bytes; raw
Markdown cannot supply HTML or script nodes. External hyperlinks remain
clickable user-initiated navigation and do not weaken the resource-loading
policy.

## Determinism and freshness

Readers contain no timestamp, host name, absolute filesystem path, Git branch,
or commit-dependent value. Stable inputs are:

- exact tracked source paths and bytes;
- generator source and template version;
- fixed parser configuration; and
- pinned parser dependency versions.

The output metadata includes:

```text
generator: KIL Markdown Reader 1
source-path: repository-relative Markdown path
source-sha256: lowercase hexadecimal SHA-256 of exact source bytes
```

Freshness is established by full deterministic regeneration, not by trusting
metadata alone. `--check` renders expected bytes in memory and requires exact
equality with every sibling.

Before writing, default mode discovers and reads every source, computes every
output, and validates output uniqueness and safety. Only after the entire
corpus renders successfully does it create temporary files in the destination
directories and replace siblings with `os.replace`. A parse or validation
failure therefore leaves all existing siblings untouched. An operating-system
failure during the final series of replacements is reported as an error;
`--check` identifies any resulting mixed generation and must pass before a
commit.

## Test strategy

Implementation follows test-driven development. Focused tests first establish
the following behavior:

1. tracked path mapping is exhaustive, stable, and collision-free;
2. titles and duplicate Unicode heading IDs are deterministic;
3. paragraphs, emphasis, block quotes, lists, tables, reference links, code
   fences, and Unicode render as expected;
4. raw HTML and hostile attributes remain escaped text;
5. tracked relative Markdown links rewrite to `.htm` with query and fragment
   preservation;
6. external, fragment-only, image, and non-Markdown links remain unchanged;
7. repository traversal is rejected;
8. output contains full static article content and all offline reader controls;
9. no external executable or presentation dependency appears in the output;
10. source path and exact SHA-256 metadata are correct;
11. two renders from identical inputs are byte-identical;
12. `--check` rejects a missing, altered, stale, or unexpected sibling and
    never writes;
13. a default generation failure before replacement preserves prior outputs;
14. every tracked `.md` has exactly one non-ignored on-disk `.htm`, and the
    committed repository tracks exactly that generated output set; and
15. source hashes, including the two historical drafts, remain unchanged by
    regeneration.

After focused tests pass, `make docs-html` creates the complete corpus and
`make validate` proves unit behavior, exact output freshness, project metadata,
and diff hygiene. Representative long-form, table-heavy, code-heavy, root, and
fixture readers receive visual inspection at desktop and narrow widths.

## Delivery

The implementation is complete only when:

- the design and implementation plan have sibling readers too;
- all tracked Markdown/HTML sibling sets are exactly equal;
- a second generation changes no bytes;
- focused and complete repository validation pass;
- representative readers have been visually inspected;
- source Markdown files changed only where documentation or the required KIL
  specialist lineage explicitly demands an authored update;
- the feature commit is pushed to its dedicated branch; and
- local HEAD, its upstream tracking ref, and the remote branch resolve to the
  same commit.

No pull request, merge, issue comment, or issue closure is implied by the final
push.
