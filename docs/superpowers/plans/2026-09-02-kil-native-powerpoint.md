# KIL Native PowerPoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish one verified 30-slide native PowerPoint that preserves a coherent 14-slide executive spine and supplies 16 scene-adjacent technical drill-ins with complete speaker notes and sources.

**Architecture:** Author the deck from the approved 2026-09-02 design using one data-driven JavaScript ES module and `@oai/artifact-tool`. Use the approved cinematic-dark cover asset, the hybrid cinematic-to-blueprint visual system, original generated artwork for high-aesthetic scenes, and dedicated diagram assets for topology and evidence mechanics. Export the final editable `.pptx` into the tracked repository, render every slide, verify both reading paths, and leave all lab artifacts unchanged.

**Tech Stack:** `@oai/artifact-tool`, JavaScript ES modules, PowerPoint `.pptx`, original image-generation assets, Graphviz for complex topology where needed, the presentation plugin render/overflow helpers, and repository citation tests.

---

## File structure

- Create: `docs/presentation/KIL-Ambient-Enforcement-Demo.pptx` — final native PowerPoint.
- Create: `docs/presentation/README.md` — purpose, slide-path contract, evidence caveat, and source pointers.
- Create in temporary build directory: `build-kil-powerpoint.mjs` — data-driven artifact-tool authoring module.
- Create in temporary build directory: `source-notes.txt` — source and visual provenance ledger.
- Create in temporary build directory: `rendered/` — rendered slide PNGs for QA.
- Create in temporary build directory: `montage.png` — deck-level visual-flow review.
- Reuse: `docs/design-drafts/assets/presentation-style-studies/kil-cinematic-dark-cover-study.png`.
- Reuse: `docs/design-drafts/assets/presentation-style-studies/kil-hybrid-walkthrough-study.png`.
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md` — append implementation and verification result.
- Do not modify: `src/`, canonical scenario inputs, lab orchestration, evidence bundles, or generated V3 artifacts.

### Task 1: Establish the build and source contract

- [ ] **Step 1: Load the bundled presentation runtime**

Call the workspace-dependency loader and record the returned Node executable,
Node modules path, and binary directory as command-scoped `RUNTIME_NODE`,
`RUNTIME_NODE_MODULES`, and `RUNTIME_BIN_DIR` values.

- [ ] **Step 2: Create an isolated temporary build directory**

Run:

```bash
mkdir -p /private/tmp/kil-native-powerpoint-2026-09-02/rendered
ln -s /Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules /private/tmp/kil-native-powerpoint-2026-09-02/node_modules
```

Expected: the build directory exists and the module symlink resolves without
modifying the bundled dependency directory.

- [ ] **Step 3: Capture source provenance**

Create `source-notes.txt` containing the canonical KTP citation, KTP v2.0.0,
KTP Enterprise architecture, KTP Constitution, Hugging Face disclosure, KIL
paper, trust-decay draft, incident draft, approved deck design, and the two
approved original style studies.

- [ ] **Step 4: Verify the non-lab boundary before authoring**

Run:

```bash
git status --short
git diff -- src docs/lab artifacts/generated
```

Expected: only presentation-design documentation may be changed; no live lab,
model, scenario, or evidence artifact is modified.

### Task 2: Build the visual asset set

- [ ] **Step 1: Inventory the 30-slide visual jobs**

Use the approved slide table in
`docs/superpowers/specs/2026-09-02-kil-native-powerpoint-design.md` and assign
one composition to every slide: cinematic hero, hybrid transformation,
blueprint topology, trajectory plot, evidence flow, comparison, or restrained
typographic close.

- [ ] **Step 2: Generate original high-aesthetic scene assets**

Generate widescreen, text-free images for the incident overview, foothold,
first cutoff, cascade, incident-to-lab transformation, three-track comparison,
and evidence-promotion close. Preserve the approved palette and semantic color
mapping; do not include fabricated readouts, watermarks, logos, or unsupported
incident detail.

- [ ] **Step 3: Generate precise technical diagrams**

Create dedicated diagram assets for signed-state evaluation, trust-decay and
class isolation, dependency reachability, reducing-only non-expansion, safety
governance, Envoy topology, evidence joins, three-track reason-code comparison,
and validation gates. Keep labels concise and reserve detailed language for
native PowerPoint text and speaker notes.

- [ ] **Step 4: Inspect each asset**

Verify aspect ratio, safe margins, semantic colors, absence of pseudo-text, and
legibility at slide scale. Replace any blurred, distorted, or semantically
ambiguous asset before authoring.

### Task 3: Author the native PowerPoint

- [ ] **Step 1: Read the artifact-tool API references**

Read:

```text
artifact_tool_docs/API_QUICK_START.md
artifact_tool_docs/api/API_DOCS.md
```

- [ ] **Step 2: Mark the artifact operation exactly once**

From the presentation-skill directory, run:

```bash
node container_tools/mark_artifact_operation_started.mjs --operation-kind create --expected-output-count 1 --output-format pptx
```

Expected: the operation marker completes successfully before the authoring
module runs.

- [ ] **Step 3: Implement the data model**

In `build-kil-powerpoint.mjs`, define one ordered `slides` array with exactly
30 entries. Each entry contains:

```javascript
{
  id: "3A",
  kind: "technical",
  parent: "3",
  title: "A signed, fresh, class-bound state is evaluated before forwarding",
  status: "Proposed KIL extension",
  visual: "signed-state-evaluation.png",
  notes: "Complete presenter script...",
  sources: ["https://github.com/nmcitra/ktp-rfc/tree/v2.0.0"]
}
```

Assert that core IDs are exactly `C`, `F1`, `F2`, `F3`, `F4`, `1` through `8`,
and `Z`; assert that there are 14 core and 16 technical entries.

- [ ] **Step 4: Implement the visual masters**

Implement cinematic cover, hybrid core, and blueprint technical layouts with
consistent typography, evidence labels, margins, scene identifiers, and
source-note handling. Keep deck title at least 50 pt, slide titles at least
35 pt, mid-level text at least 24 pt, and body text at least 16 pt.

- [ ] **Step 5: Add speaker notes and sources**

For every slide, attach the full script followed by:

```text
[Sources]
- https://github.com/nmcitra/ktp-rfc/tree/v2.0.0
[/Sources]
```

No timing scaffolds, production notes, or URLs appear on the audience-facing
canvas.

- [ ] **Step 6: Export the deck**

Run the builder with the exact loader-provided runtime and export to:

```text
docs/presentation/KIL-Ambient-Enforcement-Demo.pptx
```

Expected: one non-empty native `.pptx` containing exactly 30 slides.

- [ ] **Step 7: Add the presentation README**

Document the 14-slide executive spine, the 16 optional drill-ins, how to hide
drill-ins in PowerPoint, the evidence-status contract, and the authoritative
source files.

### Task 4: Render and visually verify every slide

- [ ] **Step 1: Render all slides**

Run:

```bash
/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 /Users/mistorm/.codex/plugins/cache/openai-primary-runtime/presentations/26.826.12353/skills/presentations/container_tools/render_slides.py docs/presentation/KIL-Ambient-Enforcement-Demo.pptx --output_dir /private/tmp/kil-native-powerpoint-2026-09-02/rendered
```

Expected: 30 slide PNGs.

- [ ] **Step 2: Create the deck montage**

Run:

```bash
/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 /Users/mistorm/.codex/plugins/cache/openai-primary-runtime/presentations/26.826.12353/skills/presentations/container_tools/create_montage.py --input_dir /private/tmp/kil-native-powerpoint-2026-09-02/rendered --output_file /private/tmp/kil-native-powerpoint-2026-09-02/montage.png
```

Expected: one montage showing a coherent cinematic-to-blueprint rhythm and
varied adjacent silhouettes.

- [ ] **Step 3: Inspect every slide at full size**

Check title wrapping, text clipping, raster crop quality, diagram legibility,
status-label consistency, contrast, visual hierarchy, and parent-to-drill-in
continuity. Fix every problem and re-render affected slides.

- [ ] **Step 4: Run overflow checks**

Run:

```bash
/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 /Users/mistorm/.codex/plugins/cache/openai-primary-runtime/presentations/26.826.12353/skills/presentations/container_tools/slides_test.py docs/presentation/KIL-Ambient-Enforcement-Demo.pptx
```

Expected: no slide-canvas overflow. Investigate and resolve every overlap or
overflow warning rather than dismissing it automatically.

### Task 5: Verify narrative, notes, and evidence

- [ ] **Step 1: Verify the executive spine**

Inspect the deck with technical IDs excluded and confirm this exact sequence:

```text
C -> F1 -> F2 -> F3 -> F4 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> Z
```

Expected: every transition is meaningful and no core slide references omitted
technical content as required context.

- [ ] **Step 2: Verify the full guided sequence**

Confirm each technical slide immediately follows its parent, inherits the
parent's focal visual or path, answers one question, and returns to the next
core scene.

- [ ] **Step 3: Verify speaker notes**

Inspect all 30 slides and confirm each contains a complete script and a balanced
`[Sources]` block. Confirm core slides contain both the drill-in transition and
the direct-to-next-core transition in notes.

- [ ] **Step 4: Scan for claim violations**

Search extracted slide text and notes for `proved`, `historically prevented`,
`absolute denial`, unqualified `validated`, unmeasured `microsecond`, and
unlabeled `0.95` or `0.90`. Correct every unsupported occurrence.

- [ ] **Step 5: Run repository checks**

Run:

```bash
git diff --check
python3 -m unittest tests.test_document_citation
```

Expected: clean diff and all citation tests pass.

### Task 6: Publish and checkpoint

- [ ] **Step 1: Append the specialist lineage**

Record the build result, deck paths, slide counts, verification results,
evidence boundaries, unresolved presentation refinements, and next gate in
`docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`.

- [ ] **Step 2: Confirm no lab changes**

Run:

```bash
git diff --name-only 3afa23b..HEAD
git status --short
```

Expected: only presentation, design/plan, and lineage artifacts changed.

- [ ] **Step 3: Commit and push**

Run:

```bash
git add docs/presentation docs/superpowers/plans/2026-09-02-kil-native-powerpoint.md docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md
git commit -m "feat: add KIL native PowerPoint presentation"
git push origin codex/v3b1-foreign-snapshot-contract
```

Expected: the feature branch and GitHub are synchronized and clean.

- [ ] **Step 4: Open the final deck for founder review**

Open `docs/presentation/KIL-Ambient-Enforcement-Demo.pptx` in the Codex
presentation panel and report the verified output path, slide counts, commit,
and any remaining aesthetic decisions.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
