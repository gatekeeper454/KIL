# KIL Presenter/Audience Editable PowerPoint Reconstruction Design

Date: 2026-09-03
Status: Founder-approved design

## Objective

Create a separate, fully editable PowerPoint edition of the 12-scene KIL
Presenter/Audience technical demonstration. Preserve the approved dark visual
system, narrative sequence, visible wording, evidence boundaries, source
statements, and speaker notes while replacing every full-slide raster with
native PowerPoint objects.

## Source authority

The reconstruction has two complementary authorities:

1. `docs/demo/kil-presenter-audience-demo.html` is authoritative for scene
   order, visible wording, diagram meaning, presenter script, source statement,
   evidence labels, and KTP-versus-KIL boundary language.
2. `docs/presentation/KIL-Presenter-Audience-Technical-Deep-Dive.pptx` is the
   visual reference for the approved rendered composition, scale, palette, and
   pacing.

The existing HTML and raster-fidelity PPTX remain unchanged.

## Output

Create:

`docs/presentation/KIL-Presenter-Audience-Technical-Deep-Dive-Editable.pptx`

The output is a separate 16:9, offline-capable deck containing exactly 12
slides in this order:

1. Ambient breach requires ambient enforcement
2. KIL turns authorization into a property of motion
3. KIL is a proposed extension of KTP
4. Why kinetic authority works
5. From ambient threat to ambient breach
6. A trusted worker becomes the foothold
7. The first mediated divergence
8. One credential path becomes a cascade
9. KIL changes authority in motion
10. Observed breach, controlled lab, bounded result
11. Same request, three enforcement tracks
12. What is evidence today?

## Native-object contract

Every audience-facing element must be independently editable in PowerPoint.
The deck may use:

- text boxes for all titles, labels, status text, takeaways, and source rails;
- rectangles, rounded rectangles, circles, and polygons for nodes and frames;
- native lines, connectors, arrows, and arrowheads for flows and dependencies;
- native freeform or line-series geometry for the trust trajectory;
- native grouped objects for reusable headers, scene navigation, nodes, and
  multi-part diagram elements.

The final slides must contain no full-slide screenshots, flattened diagram
images, or opaque visual overlays. Text may not be converted to outlines.
Simple pictograms must be built from native PowerPoint geometry so they remain
editable. Decorative shadows and glows may be omitted where PowerPoint cannot
reproduce the browser effect reliably without flattening.

## Visual system

Retain the source-supported dark palette:

- canvas: `#10151C`;
- primary panel: `#18212C`;
- primary text: `#EDF4FA`;
- muted text: `#AAB9C5`;
- structural line: `#40505D`;
- KIL blue: `#69AEF5`;
- incident red: `#FF766C`;
- verified green: `#63C98E`.

Use Aptos or Arial as the PowerPoint-safe substitute for the HTML's Inter
stack. Preserve the visible hierarchy: blue uppercase eyebrow, compact status
and progress row, bold white scene title, act/scene navigation, bordered dark
diagram field, one-sentence takeaway, and muted source rail. The scene canvas
remains centered with the same compact technical-instrument character as the
approved reference deck.

The reconstruction aims for strong visual correspondence, not false
pixel-identity. Minor font metrics and antialiasing differences between Brave
and PowerPoint are acceptable. Semantic layout, relative placement, hierarchy,
color, and diagram meaning are not.

## Slide reconstruction map

### Slides 1–4 — Primer

- Slide 1: editable AI-agent node, credential checkpoint, successful pass,
  machine-speed branch fan-out, explanatory callout, and source rail.
- Slide 2: editable side-by-side credential-checkpoint and ambient-enforcement
  comparison, including token/pass nodes and the trajectory curve.
- Slide 3: editable two-timescale architecture with a slower KTP authoritative
  derivation rail, signed short-lived composite enforcement state, fast
  infrastructure verification rail, reducing-only local overlay, and explicit
  non-expansion invariant.
- Slide 4: editable trust-charge trajectory showing slow accumulation, passive
  decay, rapid loss, and the separate authority-class isolation callout.

### Slides 5–12 — Case study and evidence

- Slide 5: editable eight-phase observed incident sequence and expanding blast
  radius, followed by a bounded counterfactual-discipline rail.
- Slide 6: editable worker-foothold-to-mediated-egress flow with observed and
  modeled labels and a visible mediation boundary.
- Slide 7: editable observed-path versus KIL-path branching comparison, the
  modeled `0.95` divergence label, and conditionally unreachable descendants.
- Slide 8: editable dependency topology from control-plane access through the
  high-value secret read to four downstream branches, with the modeled `0.90`
  label and conditional-reachability boundary.
- Slide 9: editable signed-state, fresh-evidence, Envoy authorization, and
  reducing-only local-overlay data flow with separate authoritative and local
  evidence paths.
- Slide 10: editable three-rail lab mapping covering the observed incident,
  normalized lab request, three harmless tracks, and bounded counterfactual
  result.
- Slide 11: editable three-column comparison of credential policy, signed
  state, and signed state plus reduction, preserving the `200 / 200 / 403` and
  `1 / 1 / 0` outcomes and V3 status language.
- Slide 12: editable evidence ladder from V1 through V4, with distinct observed,
  modeled, pending, and publication states plus the current-claim boundary.

## Wording and notes contract

All visible text must match the current HTML scene data. The corresponding
`script` and `source` fields must be preserved verbatim in the matching slide's
speaker notes. Each notes page must retain a `[Sources]` block containing:

- KTP v2.0.0;
- canonical KTP citation;
- KTP Enterprise architecture;
- KTP Constitution;
- Hugging Face technical timeline.

No evidence status may be promoted during reconstruction. In particular,
observed incident facts, modeled KIL counterfactuals, V3A modeled evidence, and
pending V3B-1 live validation must remain visibly distinct.

## Editability and grouping

Objects must be named and grouped by function where supported, using stable
scene-oriented names such as `header`, `navigation`, `diagram`, `takeaway`, and
`source-rail`. Diagram nodes and labels must remain accessible within their
groups. Connectors must be created before node shapes so they render behind
nodes and remain easy to reroute.

No essential information may exist only in grouping metadata or speaker notes.
The deck must remain understandable in ordinary slideshow mode.

## Error handling and fidelity decisions

If a browser visual cannot be represented exactly with native PowerPoint
primitives, preserve its meaning, hierarchy, and color using the nearest native
construction. Do not substitute a raster asset. Record each intentional visual
deviation in the build workspace and review it during QA.

If exact source wording does not fit due to PowerPoint font metrics, adjust the
native container or line breaks before reducing font size. Do not rewrite or
delete source wording.

## Non-goals

- Do not modify the HTML demo.
- Do not overwrite the raster-fidelity technical deck.
- Do not modify the executive or 30-slide technical decks.
- Do not modify the live lab, scenario, protocol, model, or evidence state.
- Do not add new claims, scenes, transitions, animations, or external artwork.
- Do not use screenshots, generated images, or flattened SVGs in the editable
  edition.

## Verification gates

The final deck must satisfy all of the following:

- exactly 12 slides in authoritative source order;
- zero full-slide raster images and zero flattened diagram images;
- visible text matches the HTML scene data;
- exactly 12 speaker-note sections with preserved scripts and source blocks;
- every slide contains native editable text and diagram geometry;
- all connectors, labels, nodes, and outcomes render without unintended
  overlap, clipping, or wrapping;
- individual full-size visual inspection of all 12 rendered slides;
- deck-level montage review for sequence, palette, and pacing;
- PowerPoint slide-overflow test passes;
- repository tests remain green;
- local and GitHub feature branches synchronize cleanly after commit.

## Acceptance criterion

The founder can open the new deck in Microsoft PowerPoint, select and edit each
title, label, node, line, connector, and diagram component without encountering
a full-slide screenshot, while the presentation tells the same 12-scene story
and retains the same speaker notes and evidence boundaries as the approved
raster edition.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
