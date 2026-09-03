# KIL native PowerPoint presentation

`KIL-Ambient-Enforcement-Demo.pptx` is the editable, 16:9 presentation asset
for the Kinetic Infrastructure Layer (KIL) ambient-enforcement story and the
bounded Hugging Face incident counterfactual.

## Presentation paths

`KIL-Ambient-Enforcement-Executive-Spine.pptx` is the separate cinematic
14-slide executive presentation. It uses the approved `C`, `F1` through `F4`,
`1` through `8`, and `Z` sequence, with one graphic-led argument per slide.
Use it for an uninterrupted executive walkthrough of the KIL premise, the
Hugging Face incident counterfactual, the Envoy lab contract, and the evidence
boundary.

The executive deck does not replace the 30-slide technical deck. Both are
self-contained, work offline, and include a short talk track, transition, and
`[Sources]` block in every slide's speaker notes.

`KIL-Presenter-Audience-Technical-Deep-Dive.pptx` is the fidelity-first
PowerPoint backup of `docs/demo/kil-presenter-audience-demo.html`. It contains
the four primer scenes followed by all eight case-study scenes in the HTML's
exact order. Each slide uses the complete rendered audience scene without
rewriting, cropping, or restyling it, and its existing presenter script and
source statement are preserved in speaker notes.

The technical-deep-dive deck is intentionally rasterized. This makes the slide
canvas non-editable, but preserves the HTML demo's precise browser composition
and keeps the deck self-contained for offline presentation. Semantic changes
must be made in the HTML authority first and then deliberately re-exported.

`KIL-Presenter-Audience-Technical-Deep-Dive-Editable.pptx` is the native-object
companion to that fidelity baseline. It preserves the same four primer scenes,
eight case-study scenes, visible wording, scene order, dark KIL palette, and
speaker notes, while rebuilding every diagram and label with editable
PowerPoint text boxes, shapes, lines, and connectors. It contains no embedded
slide images or flattened diagrams. The raster deck remains the visual
reference; the editable deck is intended for founder-led adjustment, animation,
and audience-specific tailoring.

The complete deck contains 30 slides:

- a 14-slide executive spine: `C`, `F1`, `F2`, `F3`, `F4`, `1` through `8`,
  and `Z`; and
- 16 optional technical drill-ins: `F3A`, `F4A`, and the scene-adjacent
  slides whose IDs end in `A` or `B`.

Hide the technical drill-ins for the executive presentation. The remaining
slides form a complete narrative without editing. Use the full sequence for a
technical walkthrough.

Every slide contains a speaker script and a `[Sources]` block in its PowerPoint
speaker notes. Audience-facing labels and diagrams remain editable where
practical; cinematic bridge illustrations are embedded raster assets so the
deck is self-contained and works offline.

## Evidence boundary

The presentation distinguishes observed incident facts, modeled inputs and
counterfactuals, locally reproduced behavior, and pending validation. The word
`validated` remains reserved for claims backed by an accepted evidence bundle
at the relevant gate. The deck does not claim that the live V3B-1 result has
been accepted, and it does not claim to reproduce the historical intrusion.

KIL is presented as a proposed KTP extension profile that consumes signed,
short-lived composite KTP enforcement state and can only preserve or reduce
KTP-authorized authority. Envoy produces the illustrated HTTP transport
effects; those effects are not KTP wire decisions.

## Canonical citation

Kinetic Trust Protocol contributors. *Kinetic Trust Protocol*. Canonical
citation metadata: [KTP `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
