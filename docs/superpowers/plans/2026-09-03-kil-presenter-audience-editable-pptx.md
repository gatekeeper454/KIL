# KIL Presenter/Audience Editable PowerPoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the approved 12-scene KIL Presenter/Audience technical deck as a separate PowerPoint whose visible text, diagrams, connectors, and notes are native editable objects.

**Architecture:** Parse the authoritative scene data from the existing HTML, construct a fresh 1280×720 presentation with a shared native chrome layer, and implement each scene as a bounded native-diagram function. Export slide previews, layout evidence, a montage, and the final PPTX; then validate slide order, notes, text coverage, native object counts, absence of raster images, overflow, and repository integrity.

**Tech Stack:** JavaScript ES modules, `@oai/artifact-tool`, bundled Codex presentation renderers, Brave-derived source references, XML/package inspection, and the KIL Python test suite.

---

### Task 1: Establish the source and verification contracts

**Files:**

- Read: `docs/demo/kil-presenter-audience-demo.html`
- Read: `docs/presentation/KIL-Presenter-Audience-Technical-Deep-Dive.pptx`
- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/source-notes.txt`
- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/source-scenes.json`
- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/verify-editable-deck.mjs`

- [ ] **Step 1: Record the immutable inputs**

Write `source-notes.txt` with the absolute HTML path, raster-reference PPTX
path, both SHA-256 hashes, the 12 scene identifiers, the canonical KTP source
URLs, and the Hugging Face disclosure URL.

- [ ] **Step 2: Extract the authoritative scene JSON**

Parse the `kil-demo-scenes` script element and write all 12 objects to
`source-scenes.json` without rewriting `title`, `status`, `takeaway`, `script`,
or `source`.

- [ ] **Step 3: Write the failing structural verifier**

Create `verify-editable-deck.mjs` to fail unless the final package has exactly
12 slides, 12 notes pages, no entries under `ppt/media/`, at least one native
text shape and one native non-text shape on every slide, and one `[Sources]`
block on every notes page.

- [ ] **Step 4: Run the verifier before authoring**

Run:

```bash
$RUNTIME_NODE /private/tmp/kil-editable-presenter-deck-2026-09-03/verify-editable-deck.mjs docs/presentation/KIL-Presenter-Audience-Technical-Deep-Dive-Editable.pptx
```

Expected: failure because the editable PPTX does not yet exist.

### Task 2: Build the native slide system

**Files:**

- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/theme.mjs`
- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/components.mjs`
- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/build-editable-deck.mjs`

- [ ] **Step 1: Define the presentation theme**

Define the 1280×720 canvas, the eight approved colors, PowerPoint-safe font
families, fixed content frame, text styles, line weights, node dimensions, and
semantic colors for observed, modeled, verified, and pending states.

- [ ] **Step 2: Create shared native components**

Implement reusable functions for the eyebrow, metadata/progress row, title,
act and scene navigation, diagram field, takeaway, source rail, labeled node,
status dot, arrow connector, conditional node, and evidence badge. Assign
stable object names to every created shape.

- [ ] **Step 3: Create notes and source helpers**

Implement a notes helper that copies each scene's `script` and `source`
verbatim and appends the same five canonical URLs under `[Sources]`.

- [ ] **Step 4: Create the deck entry point**

Initialize one fresh `Presentation` with 12 slides, apply the shared chrome,
dispatch each scene to its native-diagram function, export individual PNGs and
layout JSON, create a montage, and save the final PPTX to the approved output
path.

### Task 3: Reconstruct the four primer scenes

**Files:**

- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/scenes-primer.mjs`
- Modify: `/private/tmp/kil-editable-presenter-deck-2026-09-03/build-editable-deck.mjs`

- [ ] **Step 1: Build Slide 1**

Create the AI-agent circle, credential checkpoint, pass node, red fan-out
arrows, explanatory callout, and the source scene's exact visible labels.

- [ ] **Step 2: Build Slide 2**

Create the two-question comparison with native token/pass nodes on the left and
an editable multi-segment trajectory curve with infrastructure-boundary arrow
on the right.

- [ ] **Step 3: Build Slide 3**

Create the slower KTP authoritative rail above the faster infrastructure
consumption rail, with signed-state and reducing-only overlay nodes connected
in the authoritative direction.

- [ ] **Step 4: Build Slide 4**

Create the editable trust-charge path from slow ascent through passive decay to
rapid loss, plus the separate per-class isolation callout and all exact labels.

- [ ] **Step 5: Render and inspect Slides 1–4**

Export the four slides at native resolution and compare them against source
slides 1–4 for hierarchy, relative geometry, wording, palette, and line
semantics. Record deviations in `deviation-log.txt`.

### Task 4: Reconstruct case-study scenes 5–8

**Files:**

- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/scenes-case-a.mjs`
- Modify: `/private/tmp/kil-editable-presenter-deck-2026-09-03/build-editable-deck.mjs`

- [ ] **Step 1: Build Slide 5**

Create eight source-cited phase nodes, their observed sequence connectors, the
expanding-authority arrow, and the bounded counterfactual-discipline rail.

- [ ] **Step 2: Build Slide 6**

Create the application foothold, observed red flow, infrastructure mediation
boundary, modeled blue flow, and outbound-request node.

- [ ] **Step 3: Build Slide 7**

Create parallel observed and KIL paths, the `0.95 modeled` cutoff, the
infrastructure boundary, and dimmed conditionally unreachable descendants.

- [ ] **Step 4: Build Slide 8**

Create the dependency topology with four sequential nodes, four downstream
branches, the `0.90 modeled` label, and the conditional-reachability enclosure.

- [ ] **Step 5: Render and inspect Slides 5–8**

Export the four slides and verify exact labels, connector routing, observed
versus modeled styling, and the absence of unintended overlap.

### Task 5: Reconstruct case-study scenes 9–12

**Files:**

- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/scenes-case-b.mjs`
- Modify: `/private/tmp/kil-editable-presenter-deck-2026-09-03/build-editable-deck.mjs`

- [ ] **Step 1: Build Slide 9**

Create signed-state and fresh-evidence nodes, their separate vertical flows,
Envoy authorization and reducing-only overlay nodes, and the blue derived
transport connection.

- [ ] **Step 2: Build Slide 10**

Create the observed-incident rail, the normalized-request rail with three
native track boxes and `200 / 200 / 403` plus `1 / 1 / 0`, and the bounded
counterfactual-result rail.

- [ ] **Step 3: Build Slide 11**

Create three editable comparison columns for credential policy, signed state,
and state plus reduction, retaining the permit/permit/deny results and V3
status statements.

- [ ] **Step 4: Build Slide 12**

Create the V1–V4 evidence ladder, intermediate V3A/V3B labels, the current
claim-boundary callout, and the observed/modeled/pending distinctions.

- [ ] **Step 5: Render and inspect Slides 9–12**

Export the four slides and verify the architecture arrows, numeric outcomes,
evidence labels, topology, and final narrative resolution.

### Task 6: Export and validate the editable deck

**Files:**

- Create: `docs/presentation/KIL-Presenter-Audience-Technical-Deep-Dive-Editable.pptx`
- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/final-render/`
- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/final-layout/`
- Create: `/private/tmp/kil-editable-presenter-deck-2026-09-03/final-montage.webp`

- [ ] **Step 1: Mark and execute the authoring operation**

Run the presentation operation marker exactly once with `operation-kind create`,
`expected-output-count 1`, and `output-format pptx`, then execute the builder
with the bundled runtime environment.

- [ ] **Step 2: Run the structural verifier**

Run `verify-editable-deck.mjs` against the final PPTX.

Expected: 12 slides, 12 notes pages, zero media images, native editable objects
on every slide, and 12 `[Sources]` blocks.

- [ ] **Step 3: Run the overflow verifier**

Run the bundled `slides_test.py` with `RUNTIME_NODE`, `RUNTIME_NODE_MODULES`,
and `RUNTIME_BIN_DIR` set to the workspace dependency paths.

Expected: `Test passed. No overflow detected.`

- [ ] **Step 4: Inspect every slide individually**

Review all 12 native renders at full size, then inspect the montage for palette,
sequence, scale, density, and narrative pacing. Fix any unintended overlap,
clipping, wrapping, broken connector, or incomplete visual hierarchy and rerun
Steps 2–4.

### Task 7: Document and synchronize

**Files:**

- Modify: `docs/presentation/README.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Add: `docs/presentation/KIL-Presenter-Audience-Technical-Deep-Dive-Editable.pptx`

- [ ] **Step 1: Document the editable edition**

Add the output name, its 12-slide relationship to the HTML authority, its
native-object editability, its unchanged raster companion, and its notes/source
contract to the presentation README.

- [ ] **Step 2: Append the specialist lineage entry**

Record implementation results, verification evidence, affected artifacts,
remaining founder review questions, and the next gate without rewriting prior
entries.

- [ ] **Step 3: Run repository verification**

Run:

```bash
git diff --check
make test PYTHON=/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
```

Expected: no whitespace errors and 504 passing tests or the current complete
test count with zero failures.

- [ ] **Step 4: Commit and synchronize**

Stage only the final PPTX, README, implementation plan, and lineage log. Commit
with `docs: add editable presenter demo PowerPoint`, push
`codex/v3b1-foreign-snapshot-contract`, and verify that local `HEAD` equals the
remote tracking ref.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
