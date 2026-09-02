# KIL Native PowerPoint Presentation Design

## 1. Decision and scope

Create one native, editable, widescreen PowerPoint presentation that tells the
KIL story at two depths without maintaining two conflicting decks:

- a coherent executive spine comprising the front matter, eight core incident
  scenes, and a conclusion; and
- one or two scene-adjacent technical drill-in slides after every core incident
  scene, plus two optional foundation drill-ins in the front matter.

The full deck is the authoritative presentation asset. A presenter may hide or
skip any technical drill-in without breaking the executive narrative. The
founder will control hidden-slide choices, custom shows, and final timing in
PowerPoint.

This work changes presentation artifacts only. It does not change KTP, KIL
protocol semantics, the trust-decay model, the canonical scenario, evidence
schemas, authorization behavior, or any live laboratory environment. It does
not authorize a V3B-1 execution.

## 2. Communication job

By the end, a mixed executive and technical audience should understand why
ambient breach requires ambient enforcement, how KIL extends KTP into an
infrastructure-consumed enforcement profile, where the modeled KIL boundary
changes the Hugging Face incident path, and which claims are observed,
modeled, locally reproduced, or still pending.

The deck should leave an executive audience with one durable conclusion:

> Valid credentials cannot distinguish service from attack when autonomous
> agents act at machine speed; KIL proposes to make fresh, bounded authority a
> continuously enforced property of consequential transport.

The technical audience should additionally be able to inspect the state
contract, trust-decay mechanics, two-timescale architecture, incident
dependency graph, Envoy mapping, three-track comparison, safety constraints,
and evidence-promotion gates.

## 3. Deliverable contract

- Format: native `.pptx`, 16:9 widescreen.
- Default navigation: manual presenter advance.
- Optional timing support: PowerPoint-native timings may be attached to the
  executive spine, but the deck must not depend on autoplay.
- Script: a complete talk track in speaker notes for every slide.
- Sources: every externally sourced non-trivial claim and asset receives a
  `[Sources]` block in the same slide's speaker notes.
- Editability: titles, labels, evidence status, and simple annotations remain
  editable PowerPoint objects where practical. High-aesthetic hero artwork may
  remain raster.
- Static integrity: every slide must communicate its central claim without
  animation and remain meaningful when printed or exported to PDF.
- Runtime profiles:
  - executive path: approximately 5–7 minutes with all technical drill-ins
    skipped or hidden;
  - complete guided path: approximately 12–15 minutes using the full scene and
    drill-in sequence.

## 4. Shared-deck architecture

### 4.1 Slide classes

The deck contains four slide classes:

1. **Cover:** cinematic-dark, minimal, and high-impact.
2. **Foundation:** executive-level explanation of ambient breach, KIL, KTP,
   and the governing architecture.
3. **Core scene:** one of eight numbered incident-story slides. Every core
   scene advances the causal story and contains all information required to
   understand the next core scene.
4. **Technical drill-in:** one focused expansion placed immediately after its
   parent scene. It adds mechanics, topology, evidence, or limitations but
   never introduces a fact required by the next core scene.

Technical drill-ins use the same scene number plus a letter, such as `3A` and
`3B`. A restrained `TECHNICAL DRILL-IN` marker appears in a consistent corner
so the founder can identify or hide them quickly. The marker is not styled like
a button, badge, or navigation control.

### 4.2 Narrative-independence rule

Each core scene must satisfy all three conditions:

- it states one complete, audience-facing claim;
- its speaker notes contain an executive transition directly to the next core
  scene; and
- it does not refer forward to a technical slide as if that slide must be
  shown.

Each technical drill-in must satisfy all three conditions:

- it begins by visually inheriting the parent scene's focal object or path;
- it answers one technical question raised by the parent scene; and
- its closing note returns to the next core-scene transition rather than
  opening a separate narrative branch.

This produces a single ordered file with two valid reading paths:

```text
Executive: foundation -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> close
Guided:    foundation -> 1 -> 1A -> 2 -> 2A -> ... -> 8 -> 8A/8B -> close
```

## 5. Slide sequence

### 5.1 Cover and foundation

| ID | Slide claim | Depth | Visual and narrative job |
|---|---|---|---|
| C | Ambient enforcement for agent-speed cybersecurity | Core | Cinematic-dark cover. Establish urgency without technical density. |
| F1 | Cybersecurity has crossed from ambient threat into ambient breach | Core | Introduce the inflection-point statement and define ambient breach as both acting without verified trust and the wider inability to distinguish service from attack at machine speed. |
| F2 | Credential validity cannot establish behavioral legitimacy | Core | Show an authentic/allowed request passing a checkpoint while novel action branches beyond it. |
| F3 | KIL makes fresh authority enforceable where actions become consequences | Core | Define ambient enforcement and the infrastructure boundary in plain language. |
| F3A | KIL is a proposed KTP extension profile, not a replacement trust system | Drill-in | Show KTP-derived constructs, signed short-lived composite state, non-expansion, and the future KTP 2.1/3.0 governance path. |
| F4 | KIL separates authoritative state derivation from fast enforcement | Core | Introduce the hybrid two-timescale architecture with one visual loop and one boundary. |
| F4A | Authority is class-bound, earned slowly, decays, and can be lost quickly | Drill-in | Present the trust-decay profile and parameter-status caveat. |

The cinematic-dark cover is reserved for the opening. Foundation slides begin
the transition into the approved hybrid cinematic-to-blueprint system.

### 5.2 Eight core scenes and technical drill-ins

| ID | Slide claim | Evidence status | Technical expansion |
|---|---|---|---|
| 1 | The disclosed incident turns ambient breach into a concrete sequence | Observed incident + KIL framing | Establish the source-cited phase rail and the bounded counterfactual question. |
| 1A | Observed facts, modeled inputs, and pending validation remain separate | Observed / modeled / pending | Show the provenance legend, source boundary, and canonical phase normalization. |
| 2 | A trusted worker became the foothold before the tested transport boundary | Observed incident | Explain the renderer-to-worker transition and why the current Envoy lab does not claim visibility into the local file read. |
| 2A | Enforcement placement determines which actions KIL can observe or stop | Architecture boundary | Compare application-aware, kernel-aware, and current Envoy-mediated visibility without claiming implementation of unbuilt adapters. |
| 3 | The first mediated divergence occurs when the worker addresses the cluster API | Modeled counterfactual | Contrast the disclosed path with modeled KIL withholding at the first privileged egress. |
| 3A | A signed, fresh, class-bound state is evaluated before the request is forwarded | Proposed KIL extension | Walk through signature, expiry, identity/class/action binding, veto, envelope, threshold, and decision record. |
| 3B | Modeled divergence `d_t = 0.95` reduces effective authority below threshold | Modeled input and result | Show the weighted diagonal standardized-distance input and reducing-only result without presenting the value as incident telemetry. |
| 4 | The observed path cascaded from control-plane access into multiple high-consequence branches | Observed incident | Show node privilege, bulk secret access, cross-cluster reach, mesh enrollment, token creation, and CI/source-control targeting. |
| 4A | Dependency-aware reachability reveals the leverage of one early cutoff | Modeled reachability | Display the incident dependency graph and mark descendants conditionally unreachable rather than separately prevented. |
| 4B | Later cut points remain independently meaningful if the early boundary is absent | Observed + modeled | Examine the modeled `d_t = 0.90` Phase 4 secret-read cutoff and why correctly signed forged tokens remain insufficient under class-bound trajectory state. |
| 5 | KIL changes authority in motion without expanding KTP-authorized authority | Modeled counterfactual | Apply the hybrid architecture to the worker-to-control-plane action. |
| 5A | Local evidence may tighten the decision but can never clear a KTP veto or add authority | Proposed KIL invariant | Show the non-expansion inequality, reducing-only overlay, freshness, and reconciliation path. |
| 5B | Safety requires fail-closed or fail-constrained behavior with auditable change | Proposed safety/governance | Explain class-based failure behavior, declared-change envelopes, provenance, recovery, and contested-decision governance. |
| 6 | The lab reproduces one enforcement boundary, not the historical intrusion | Modeled lab mapping | Transform the incident roles into request driver, Envoy, authorization service, and harmless target. |
| 6A | Six isolated network segments and fixed one-shot drivers constrain the experiment | Implemented lab architecture; live result pending | Show the local Envoy topology, exact trust boundaries, no host publication, and the tested component responsibility. |
| 6B | Canonical records join request intent, decision, proxy, and target evidence | Implemented evidence contract; live result pending | Trace evidence production and integrity joining without implying a promoted V3B-1 run. |
| 7 | The same normalized request produces a modeled `permit / permit / deny` comparison | V3A modeled; V3B-1 pending | Present the three tracks and their Envoy-derived HTTP effects `200 / 200 / 403` with target markers `1 / 1 / 0`. |
| 7A | The third track isolates the effect of fresh reducing-only local divergence | Modeled process contract | Compare inputs and reason codes across the three tracks; state that HTTP is an Envoy effect, not a KTP wire decision. |
| 7B | A live result requires exact readiness, one-shot execution, evidence joins, and teardown | Pending validation | Present the no-retry and accepted-evidence gate without claiming the pending run succeeded. |
| 8 | The evidence ladder prevents the presentation from outrunning the project | Observed / modeled / locally reproduced / pending | Close the case by distinguishing V1, V2, V3A, V3B-1, V3B-2, and V4. |
| 8A | Claims advance only when immutable evidence satisfies the corresponding gate | Evidence governance | Show promotion rules, SHA-256 integrity, negative results, and the reserved meaning of `validated`. |
| 8B | The next proof is bounded and falsifiable | Pending validation | State what the live Envoy proof must demonstrate, what would fail the gate, and what it still cannot establish. |
| Z | Ambient enforcement turns trust into an active property of consequential traffic | Core close | Resolve the opening: KIL is a proposed, testable KTP extension whose claims advance only with evidence. |

The resulting design contains 14 core slides including cover, foundation, eight
incident scenes, and close; it contains 16 technical drill-ins. The complete
deck therefore contains 30 slides. Hiding all slides whose ID ends in a letter
after a scene number, plus F3A and F4A, yields the executive sequence without
editing slide content.

## 6. Visual system

### 6.1 Approved dual register

- **Cinematic dark:** cover and rare act-transition moments only. Near-black,
  midnight navy, controlled crimson, electric cobalt, and dimensional light
  establish urgency.
- **Hybrid cinematic-to-blueprint:** master language for the walkthrough.
  Adversarial pressure is cinematic; verified structure, KTP/KIL mechanics,
  topology, and evidence resolve into bright architectural precision.
- **Blueprint detail:** technical drill-ins may lean further into warm-white
  grid, graphite structure, cobalt enforcement, and crimson incident paths,
  while retaining the hybrid deck's typography and geometry.

The visual system must avoid dashboards, dense card grids, fake telemetry,
invented measurement marks, generic padlocks, hooded attackers, decorative
code, and pseudo-technical labels. Graphical intensity comes from composition,
scale, paths, boundaries, topology, contrast, and transformation.

### 6.2 Stable visual semantics

- crimson solid path: observed incident action or adversarial pressure;
- crimson ghosted/dashed path: modeled downstream counterfactual;
- cobalt: KTP/KIL-derived authority, constraint, or enforcement boundary;
- graphite: neutral infrastructure and structural relationships;
- low-contrast dashed nodes: conditionally unreachable under the declared
  model;
- explicit text label plus line treatment: every meaning encoded by color.

Observed, modeled, locally reproduced, and pending are never distinguished by
color alone. Each receives a concise visible label and a fuller note-level
explanation.

## 7. Motion and transitions

Motion is manual, presenter-triggered, non-looping, and semantic. Approved
motion categories are:

- trajectory travel along an already visible path;
- progressive topology reveal;
- authority decay or collapse;
- transport cutoff;
- downstream nodes becoming conditionally unreachable;
- incident topology transforming into the Envoy lab topology;
- evidence layers joining into one accepted or rejected run bundle.

Every slide begins or ends in a useful static composition. Builds do not hide
qualifying language, evidence status, or limitations. Technical drill-ins use a
visual handoff from the parent scene so entering or skipping them does not feel
like changing decks. Decorative fades, continuous background motion, and
automatic loops are prohibited.

## 8. Speaker notes and navigation

Each core scene receives:

- a 20–35-second executive talk track;
- an optional transition into its technical drill-in;
- a direct transition to the next core scene if drill-ins are skipped; and
- a `[Sources]` block.

Each technical drill-in receives:

- a 20–40-second detailed explanation;
- one explicit claim-boundary or limitation statement;
- a return transition into the next core scene; and
- its own `[Sources]` block.

The audience-facing canvas does not display speaker instructions, timing
scaffolds, or source URLs. Slide IDs and drill-in markers remain small and
consistent so the founder can manage hidden slides and custom shows. No
hyperlink navigation is required for the first release because manual linear
advance is more reliable and the founder will manage presentation variants.

## 9. Evidence and terminology controls

The presentation inherits the repository-wide evidence contract:

- `observed`: supported by a named primary source;
- `modeled`: a declared synthetic input or counterfactual result;
- `locally reproduced`: behavior reproduced by the reference implementation
  without automatically validating a historical counterfactual; and
- `validated`: reserved for a claim backed by an accepted local evidence
  bundle at the relevant gate.

The following boundaries are mandatory:

- KTP provides authoritative constructs, supervision, and tighten-only
  constraints.
- KIL is a proposed KTP extension profile for signed, short-lived composite
  enforcement state and reducing-only infrastructure consumption.
- Envoy derives the HTTP `200` or `403` transport effect; KTP does not emit an
  HTTP wire decision.
- `d_t = 0.95` and `d_t = 0.90` are modeled scenario values, not disclosed raw
  telemetry.
- An upstream modeled deny makes descendants conditionally unreachable; it
  does not prove seven additional preventions.
- The initial foothold precedes the action mediated by the current Envoy lab.
- V3B-1 remains pending until an accepted evidence bundle exists.

## 10. Implementation boundary

The deck will be authored from scratch using the approved custom visual
direction. It will not use a generic presentation template. High-aesthetic
hero and scientific-illustration assets may be generated as original raster
artwork. Simple labels and annotations remain native PowerPoint objects.
Complex topology graphics may be generated as dedicated visual assets when
that improves legibility, but their claim semantics must originate from the
canonical repository sources.

Implementation must not:

- start, stop, configure, or modify the live Envoy laboratory;
- alter canonical scenario inputs, model constants, or evidence status;
- imply that visual motion is measured latency;
- copy unsupported wording or fabricated values from supplied visual
  references; or
- depend on a network connection during presentation.

## 11. Verification and acceptance

Before delivery:

1. Render every slide to an image and inspect it at full size.
2. Inspect a deck-level montage for visual rhythm and adjacent-slide
   silhouette variety.
3. Run overflow and overlap checks; resolve every unintended warning.
4. Verify titles remain one line where designed and text meets minimum size.
5. Confirm every slide has speaker notes and every sourced slide has a
   `[Sources]` block.
6. Verify the executive path by hiding every technical drill-in and reading the
   remaining slides in sequence.
7. Verify the full guided path and every parent-to-detail-to-next-scene
   transition.
8. Search visible text and notes for prohibited overclaims, stale terminology,
   invented measurements, unresolved placeholders, and unsupported source
   statements.
9. Confirm the final `.pptx` opens as a native editable presentation and the
   rendered slides match the authored deck.
10. Confirm no lab, model, canonical scenario, or evidence artifact changed.

Acceptance requires a coherent 14-slide executive path, a coherent 30-slide
full path, complete speaker notes, traceable sources, consistent evidence
labels, approved visual semantics, and no unintended clipping or overlap.

## 12. Authoritative sources

- KTP v2.0.0: <https://github.com/nmcitra/ktp-rfc/tree/v2.0.0>
- KTP Enterprise architecture:
  <https://kinetic-trust-protocol.net/enterprise/architecture>
- KTP Constitution:
  <https://kinetic-trust-protocol.net/learn/constitution>
- KTP canonical citation metadata:
  <https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff>
- Hugging Face technical timeline:
  <https://huggingface.co/blog/agent-intrusion-technical-timeline>
- KIL paper: `docs/paper/kinetic-infrastructure.md`
- KIL trust-decay source: `docs/drafts/kil-trust-decay-model.md`
- KIL incident source: `docs/drafts/ambient-enforcement-vs-huggingface-incident.md`
- Existing Presenter/Audience semantic baseline:
  `docs/superpowers/specs/2026-08-31-kil-incident-presenter-audience-demo-design.md`

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
