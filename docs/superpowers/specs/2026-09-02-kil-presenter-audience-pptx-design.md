# KIL Presenter/Audience Technical Deep-Dive PowerPoint Design

Date: 2026-09-02
Status: Founder-approved design

## Objective

Create a separate PowerPoint backup of
`docs/demo/kil-presenter-audience-demo.html` for technical deep-dive use beside
`KIL-Ambient-Enforcement-Executive-Spine.pptx`.

## Fidelity contract

The PowerPoint must preserve the source demo's current look, feel, context,
wording, storyline, evidence labels, graphics, and scene order. It must not
rewrite, reinterpret, restyle, condense, or expand the source narrative.

The source contains 12 scenes in this exact order:

1. four primer scenes;
2. eight incident, counterfactual, lab, and evidence scenes.

Each scene becomes one 16:9 slide. The slide canvas is an exact raster capture
of the scene's audience view at the fixed presentation viewport. Presenter
controls and on-screen presenter notes are excluded because the audience mode
is the presentation surface. The original `script` and `source` fields are
copied verbatim into the slide's PowerPoint speaker notes. The notes also carry
the canonical external source URLs already referenced by the HTML.

## Output

Final file:

`docs/presentation/KIL-Presenter-Audience-Technical-Deep-Dive.pptx`

The deck is self-contained and works offline. Rasterized scene canvases are an
intentional fidelity choice; they are not individually editable PowerPoint
objects.

## Evidence and protocol boundaries

The conversion preserves the existing distinctions among observed incident
facts, modeled KIL counterfactuals, V3A local process-contract evidence, and
pending V3B-1 validation. It preserves KTP as the authoritative protocol layer,
KIL as a proposed reducing-only infrastructure-consumption extension, and
Envoy HTTP status as a derived transport effect rather than a KTP wire
decision.

No wording in the HTML source is promoted, corrected, or silently modernized
during conversion. Any future semantic revision must first be made in the HTML
and then deliberately re-exported.

## Non-goals

- Do not change the HTML demo.
- Do not change the live laboratory or its configuration.
- Do not change the 14-slide executive deck or 30-slide technical deck.
- Do not add new scenes, transitions, claims, metrics, or artwork.
- Do not reconstruct the browser SVGs as approximate PowerPoint diagrams.

## Verification

The completed deck must pass all of the following:

- exactly 12 slides in source order;
- exact visible text comparison against the scene data;
- exactly 12 speaker-note sections with source blocks;
- full-slide render comparison and individual visual inspection;
- no clipping or slide-canvas overflow;
- repository tests remain green;
- clean local/remote feature-branch synchronization after commit.

## Source authority

- KIL Presenter/Audience demo:
  `docs/demo/kil-presenter-audience-demo.html`
- KTP v2.0.0: <https://github.com/nmcitra/ktp-rfc/tree/v2.0.0>
- KTP Enterprise architecture:
  <https://kinetic-trust-protocol.net/enterprise/architecture>
- KTP Constitution:
  <https://kinetic-trust-protocol.net/learn/constitution>
- Hugging Face technical timeline:
  <https://huggingface.co/blog/agent-intrusion-technical-timeline>

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
