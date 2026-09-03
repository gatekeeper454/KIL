# KIL Presenter/Audience Technical Deep-Dive PowerPoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a separate 12-slide PPTX that faithfully preserves every audience scene, word, graphic, status, takeaway, and presenter script from the existing KIL Presenter/Audience HTML demo.

**Architecture:** A deterministic capture script loads the local HTML at a fixed 1280×720 viewport, advances through the source scene array, and captures the complete audience-view application for each scene. A JavaScript Artifact Tool builder embeds the 12 PNG captures as full-slide images and copies each scene's existing `script` and `source` fields into the corresponding speaker notes.

**Tech Stack:** Local HTML/CSS/SVG, bundled Chromium-compatible browser runtime, JavaScript ES modules, `@oai/artifact-tool`, PowerPoint PPTX, repository Python test suite.

---

### Task 1: Establish the immutable source manifest

**Files:**
- Read: `docs/demo/kil-presenter-audience-demo.html`
- Create: temporary `source-scenes.json`

- [ ] **Step 1: Extract the `kil-demo-scenes` JSON block without rewriting it**

Use a temporary JavaScript script to parse the `<script id="kil-demo-scenes">`
payload and write its 12 records as UTF-8 JSON.

- [ ] **Step 2: Assert the closed source order**

Verify the exact IDs are:
`primer-ambient-breach`, `primer-kinetic-infrastructure`,
`primer-ktp-extension`, `primer-trust-physics`, `case-ambient-breach`,
`case-foothold`, `case-first-divergence`, `case-cascade`,
`case-kil-mechanics`, `case-lab-mapping`, `case-three-tracks`, and
`case-evidence`.

### Task 2: Capture the 12 audience scenes

**Files:**
- Read: `docs/demo/kil-presenter-audience-demo.html`
- Create: temporary `captures/scene-01.png` through `scene-12.png`
- Create: temporary `capture-manifest.json`

- [ ] **Step 1: Load the HTML at a fixed 1280×720 viewport**

Use the audience presentation surface, hide only synchronization/navigation
chrome that audience mode already hides, and preserve all title, metadata,
visual, takeaway, and footer content.

- [ ] **Step 2: Advance through all scenes deterministically**

Select each source scene in array order, wait for its SVG and text render, and
capture the complete application region.

- [ ] **Step 3: Record capture provenance**

Write each source ID, title, status, progress label, screenshot filename, and
SHA-256 into the temporary manifest.

### Task 3: Build the PowerPoint

**Files:**
- Create: temporary `build-presenter-audience-deck.mjs`
- Create: `docs/presentation/KIL-Presenter-Audience-Technical-Deep-Dive.pptx`

- [ ] **Step 1: Create a 1280×720 presentation**

Use `Presentation.create({ slideSize: { width: 1280, height: 720 } })` and add
exactly one slide for every source scene.

- [ ] **Step 2: Embed each capture without cropping or restyling**

Add each PNG as a byte-backed full image using `fit: "contain"` and position
`{ left: 0, top: 0, width: 1280, height: 720 }` against the source background.

- [ ] **Step 3: Copy the presenter material verbatim**

Set every slide's speaker notes to the exact scene `script`, followed by its
exact `source` field and a `[Sources]` block containing the five canonical URLs
already linked from the HTML footer.

- [ ] **Step 4: Export the standalone PPTX**

Save only the final deck in `docs/presentation`; keep scripts, manifests,
previews, and captures in the temporary build directory.

### Task 4: Verify visual and semantic fidelity

**Files:**
- Read: final PPTX and temporary source/capture manifests

- [ ] **Step 1: Render every PPTX slide**

Use `render_slides.py` and create a 12-slide montage for sequence-level review.

- [ ] **Step 2: Inspect every slide at full size**

Confirm no crop, color-mode drift, clipping, scaling distortion, missing SVG,
or hidden title/takeaway/footer content.

- [ ] **Step 3: Verify the closed semantic contract**

Assert 12 slide parts, 12 notes parts, exact scene order, exact title/status/
takeaway strings, and one `[Sources]` block per notes page.

- [ ] **Step 4: Run presentation and repository tests**

Run `slides_test.py`, `git diff --check`, and the full `make test` suite using
the bundled Python runtime. Expected result: no slide overflow and all current
repository tests pass.

### Task 5: Document and synchronize

**Files:**
- Modify: `docs/presentation/README.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

- [ ] **Step 1: Document the technical-deep-dive deck**

Record its 12-scene fidelity contract, relationship to the executive deck, and
intentional raster-canvas editability tradeoff.

- [ ] **Step 2: Append the implementation result to the specialist lineage**

Record the confirmed input, fidelity interpretation, evidence implementation
status, affected artifacts, evidence boundaries, unresolved founder review,
and next gate with the canonical KTP citation.

- [ ] **Step 3: Commit and push the verified result**

Commit the plan, final PPTX, README, and lineage update to
`codex/v3b1-foreign-snapshot-contract`, push the branch, and verify local HEAD
equals the remote-tracking revision with a clean worktree except for any
user-owned Microsoft Office lock file.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
