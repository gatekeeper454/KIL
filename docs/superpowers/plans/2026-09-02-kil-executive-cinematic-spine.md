# KIL Executive Cinematic Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate, native, self-contained 14-slide cinematic PowerPoint that presents the complete KIL executive story with stronger graphical continuity.

**Architecture:** Generate one original 16:9 cinematic illustration for each narrative beat that does not already have an approved unique asset, then assemble those assets with editable titles, evidence labels, results, and speaker notes using `@oai/artifact-tool`. Preserve the existing 30-slide deck and all lab artifacts. Verify slide count, notes/source blocks, rendering, overflow, and repository cleanliness before publication.

**Tech Stack:** OpenAI ImageGen, JavaScript ES modules, `@oai/artifact-tool`, bundled presentation render/overflow helpers, Git.

---

### Task 1: Establish the production workspace and source ledger

**Files:**
- Create: `/private/tmp/kil-executive-spine-2026-09-02/source-notes.txt`
- Create: `/private/tmp/kil-executive-spine-2026-09-02/build-executive-spine.mjs`
- Create: `docs/presentation/assets/executive-spine/`

- [ ] **Step 1: Create the isolated temporary build directories**

Run:

```bash
mkdir -p /private/tmp/kil-executive-spine-2026-09-02/rendered docs/presentation/assets/executive-spine
```

Expected: both directories exist and no live-lab file changes.

- [ ] **Step 2: Record the authoritative sources**

Write `source-notes.txt` with the KTP v2.0.0 repository, canonical
`CITATION.cff`, Hugging Face technical timeline, local KIL white paper,
trust-decay model, and counterfactual/lab specifications.

- [ ] **Step 3: Verify the existing technical deck is not selected as output**

Run:

```bash
test -f docs/presentation/KIL-Ambient-Enforcement-Demo.pptx
```

Expected: exit 0. The new output path is
`docs/presentation/KIL-Ambient-Enforcement-Executive-Spine.pptx`.

### Task 2: Generate the cinematic story visuals

**Files:**
- Create: `docs/presentation/assets/executive-spine/*.png`

- [ ] **Step 1: Generate original text-free 16:9 illustrations**

Create unique cinematic scenes for ambient-breach convergence, credential
blind spot, consequence boundary, hybrid two-timescale architecture, worker
foothold, first cluster-API cutoff, downstream cascade, reducing-only authority,
three-track comparison, and closing synthesis. Use near-black/navy environments,
crimson adversarial trajectories, cobalt enforcement fields, restrained green
permit effects, and amber modeled/pending emphasis.

- [ ] **Step 2: Inspect every generated asset**

Check each image at full size for legibility, aspect ratio, crop space, no
embedded prose, no logos, no fake UI, and no unsupported numerical claims.

- [ ] **Step 3: Copy approved assets into the repository**

Use stable filenames matching the slide IDs and keep one unique hero asset per
slide. Existing approved cover, incident-cascade, Envoy-lab, and evidence-ladder
assets may be copied into this dedicated asset directory.

### Task 3: Author the native 14-slide PowerPoint

**Files:**
- Create: `/private/tmp/kil-executive-spine-2026-09-02/build-executive-spine.mjs`
- Create: `docs/presentation/KIL-Ambient-Enforcement-Executive-Spine.pptx`

- [ ] **Step 1: Initialize a 1280×720 presentation**

Use:

```js
import { Presentation, PresentationFile } from '@oai/artifact-tool';
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
```

- [ ] **Step 2: Implement the approved slide data contract**

Define exactly these IDs in order:

```js
const slideIds = ['C','F1','F2','F3','F4','1','2','3','4','5','6','7','8','Z'];
```

Each entry must include a takeaway title, evidence label where applicable,
unique embedded image, 20–35-second speaker script, transition, and source list.

- [ ] **Step 3: Preserve editability and visual hierarchy**

Keep titles at least 35 pt, the cover title at least 50 pt, evidence labels at
least 16 pt, and outcome callouts at least 24 pt. Use editable PowerPoint text
and simple annotations over the cinematic art. Do not expose production notes
on the audience canvas.

- [ ] **Step 4: Add speaker notes and sources**

Use:

```js
slide.speakerNotes.textFrame.setText(`${talkTrack}\n\n${transition}\n\n[Sources]\n${sources.join('\n')}`);
```

Expected: all 14 slides contain a complete script and `[Sources]` block.

- [ ] **Step 5: Export the final deck**

Use:

```js
const file = await PresentationFile.exportPptx(presentation);
await file.save(finalPath);
```

Expected: the new executive deck exists without modifying the 30-slide deck.

### Task 4: Render and verify every slide

**Files:**
- Create: `/private/tmp/kil-executive-spine-2026-09-02/rendered/slide-*.png`
- Create: `/private/tmp/kil-executive-spine-2026-09-02/montage.png`

- [ ] **Step 1: Render all 14 slides**

Run the bundled `render_slides.py` with the exact runtime variables returned by
the workspace dependency loader.

Expected: 14 PNG files.

- [ ] **Step 2: Inspect individual slides and the montage**

Verify full-size crops, title wrapping, evidence-label clarity, visual handoffs,
and coherent slide-to-slide progression. Fix every unintended overlap or crop.

- [ ] **Step 3: Run overflow verification**

Run the bundled `slides_test.py` against the final `.pptx`.

Expected: `Test passed. No overflow detected.`

- [ ] **Step 4: Verify deck internals**

Inspect the PPTX archive and assert:

```text
slides=14 notes=14 source_blocks=14
```

### Task 5: Document, test, and publish

**Files:**
- Modify: `docs/presentation/README.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

- [ ] **Step 1: Document the executive deck**

Add its purpose, 14-slide order, relationship to the 30-slide technical deck,
offline behavior, evidence boundary, and canonical KTP citation.

- [ ] **Step 2: Append the specialist lineage entry**

Record the founder-approved cinematic direction, implementation result,
verification evidence, unchanged lab boundary, unresolved PowerPoint timing,
and next review gate.

- [ ] **Step 3: Run repository tests**

Run:

```bash
make test PYTHON=/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
```

Expected: all tests pass.

- [ ] **Step 4: Commit and push**

Commit the plan, deck, dedicated assets, README, and lineage. Push
`codex/v3b1-foreign-snapshot-contract` and verify local `HEAD` equals the remote
branch with a clean worktree.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

