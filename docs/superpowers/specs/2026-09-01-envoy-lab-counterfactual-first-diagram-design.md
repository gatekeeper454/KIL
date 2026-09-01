# Envoy Laboratory Counterfactual-First Diagram Design

**Date:** 2026-09-01  
**Status:** Founder-approved composition and narrative; revised written
specification pending founder review
**Delivery targets:** Standalone presentation-quality diagram and synchronized
Presenter/Audience demonstration scene  
**Implementation authority:** Not granted by this specification

## 1. Decision and scope

The Envoy laboratory explanation will use the founder-approved
**counterfactual-first** composition. The visual preserves the disclosed
incident as the dominant story, isolates one consequential mediated action in
the harmless three-track Envoy laboratory, and closes with the bounded modeled
result that dependent downstream actions become conditionally unreachable.

The composition contains three bands in this order:

1. **Observed incident** — the source-cited breach path and its escalating
   dependency chain;
2. **Envoy lab model** — the same normalized harmless request evaluated in
   three isolated enforcement tracks; and
3. **KIL counterfactual result** — the modeled derived transport effect and
   its dependency-aware reachability consequence.

This specification governs only the visual and explanatory contract. It does
not change the canonical scenario, trust-decay mathematics, KTP or KIL decision
semantics, application behavior, test environment, evidence bundles,
containers, Envoy configuration, laboratory configuration, or live services.

## 2. Narrative introduction — why this is being demonstrated

The executive-facing explanation must establish the urgency before introducing
the incident topology or laboratory mechanics. The following founder-supplied
narrative is the controlling introduction:

> Cybersecurity is currently at an inflection point where reliance on static or
> AI-Assisted SOC (Security Operations Centers) and traditional AI-augmented
> controls is no longer sufficient to counter modern, adversarial AI.
>
> To remain effective, the practice must transcend the legacy
> detect-and-prevent paradigm and evolve into a state of ambient enforcement.
> We are transitioning from a landscape of 'ambient risk' and 'ambient threat'
> into an era of pervasive, continuous 'ambient breach', necessitating a shift
> toward autonomous, real-time mitigation that functions at speed and scale
> independent of human intervention.
>
> 'Ambient enforcement' represents this critical evolution by decoupling
> defenses from static, procedural constraints and utilizing kinetic
> infrastructure to match the velocity of AI adversaries in real time. By
> leveraging the same transport mechanisms as the threat itself and
> instantiating immutable controls that enforce security through physics, we
> move toward a future where cybersecurity functions not as a reactive overlay,
> but as an autonomous, omnipresent force capable of neutralizing AI-driven
> threats with the same speed and adaptability as the intelligence it seeks to
> contain.

The standalone executive presentation places this narrative immediately before
the three-band diagram. The synchronized Presenter/Audience scene may reveal it
in concise visual beats, but must preserve all three transitions:

```text
legacy detection is insufficient at adversarial-AI speed
  -> ambient breach creates the operating urgency
  -> ambient enforcement moves mitigation into kinetic infrastructure
```

The phrase `pervasive, continuous ambient breach` names the persistent systemic
condition in which authenticated service and attack cannot reliably be
distinguished before consequence. It does not claim that every system is
continuously compromised. Action without verified current authority remains a
concrete manifestation of that broader condition, not its complete definition.

## 3. Controlling sources and alignment

The diagram must align with:

- KTP v2.0.0: <https://github.com/nmcitra/ktp-rfc/tree/v2.0.0>;
- KTP-Core section 6.6 decision-result semantics:
  <https://github.com/nmcitra/ktp-rfc/blob/v2.0.0/rfc-src/ktp-core.md>;
- KTP-Enforce:
  <https://github.com/nmcitra/ktp-rfc/blob/v2.0.0/rfc-src/ktp-enforce.md>;
- the Kinetic Envelope:
  <https://github.com/nmcitra/ktp-rfc/blob/v2.0.0/specifications/kinetic-envelope.md>;
- canonical KTP citation metadata:
  <https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff>;
- the Hugging Face technical timeline:
  <https://huggingface.co/blog/agent-intrusion-technical-timeline>; and
- the approved KIL authoritative-alignment design:
  `docs/superpowers/specs/2026-09-01-kil-ktp-authoritative-alignment-design.md`.

The normative KTP result is a supervision level plus a tighten-only constraint
set. `Permit`, `constrain`, `deny`, and `indeterminate` may appear only as
human-facing derived readings. HTTP `200` and `403` are Envoy adapter transport
effects, not KTP wire-enumeration values.

## 4. Communication objective

The diagram must let a mixed executive and technical audience answer five
questions in approximately 30–45 seconds:

1. What happened in the disclosed incident?
2. Which incident action does the current Envoy lab model?
3. How do the three isolated tracks differ?
4. Why does only the local-reduction track change the modeled transport result?
5. Which claims are observed, modeled, or still pending live validation?

The visual must not require the audience to understand KTP notation before
following the story. Technical labels remain available for specialists without
competing with the narrative hierarchy.

## 5. Evidence contract

The three evidence categories remain visually and verbally distinct.

### 5.1 Observed

The incident band summarizes the public Hugging Face sequence. It does not
claim access to raw telemetry beyond the disclosure and does not imply that the
current lab reproduces the original application foothold.

### 5.2 Modeled

The following are modeled inputs or process-contract results:

- local divergence `d_t = 0.95` for the normalized cluster-control-plane
  request;
- HTTP outcomes `200 / 200 / 403`;
- harmless target markers `1 / 1 / 0`; and
- downstream phases becoming conditionally unreachable if the first mediated
  request is withheld under the declared model.

The diagram must not call those results historically observed, empirically
validated, or proof that the disclosed incident would certainly have been
prevented.

### 5.3 Pending validation

The V3B-1 Envoy topology is implemented and has request-free lifecycle
evidence, but its accepted live enforcement result remains pending. V3B-2
Kind/Calico remains future work. No lab behavior becomes `validated` merely
because it is shown in the diagram.

## 6. Three-band composition

### 6.1 Band 1 — observed incident

The first band is the dominant narrative. It uses a solid incident rail with
these source-cited dependency stages:

```text
worker foothold
  -> cluster API request
  -> cloud and node privilege
  -> 136-key secret read
  -> cross-cluster access
  -> mesh enrollment
  -> token and CI pivot
```

The `cluster API request` node receives a distinct mapped-state treatment and a
connector into the lab band. The label is:

> first mediated action normalized into a harmless request

The systemic ambient-breach framing remains visible:

> Authenticated, service-like activity carried attack through ordinary
> interfaces before consequence.

This is not a claim that every system is continuously compromised. It states
the approved KIL thesis that defenders cannot safely presume authenticated
service appearance is distinguishable from attack before machine-speed
consequence.

### 6.2 Band 2 — Envoy lab model

The lab band shows one normalized harmless request crossing three isolated
tracks. Each track renders the same four functional components:

```text
request driver -> Envoy frontend -> authorization service -> harmless target
```

Each track remains isolated from the other two. The six internal network
segments are explained in the detailed topology or accessible description
rather than rendered as six competing foreground labels.

#### Track A — credential policy

- Purpose: checkpoint baseline.
- Authorization input: credential validity and configured policy.
- Modeled transport result: HTTP `200`.
- Harmless target marker: `1`.

#### Track B — signed composite KTP state

- Purpose: signed-state consumption without the KIL local reduction.
- Authorization input: authentic, fresh, short-lived composite state whose KTP
  content is supervision plus tighten-only constraints.
- Modeled transport result: HTTP `200`.
- Harmless target marker: `1`.

#### Track C — signed state plus modeled local reduction

- Purpose: isolate the KIL-specific reducing-only contribution.
- Authorization input: the same authentic and fresh composite state plus the
  declared local divergence `d_t = 0.95`.
- State effect: the local contribution may tighten but never widen the
  KTP-authorized envelope.
- Envoy adapter effect: derived HTTP `403`.
- Harmless target marker: `0`; the target is not reached.

The permanent lab-band qualifier is:

> KTP supplies supervision plus tighten-only constraints; the Envoy adapter
> derives the transport effect.

### 6.3 Band 3 — KIL counterfactual result

The closing band shows the signed composite state and modeled local reduction
reaching a visible infrastructure boundary. A solid boundary marks the point
where the Envoy adapter derives HTTP `403`. The remaining dependency chain is
low contrast and dashed:

```text
cloud and node privilege
  -> 136-key secret read
  -> cross-cluster, mesh, and CI descendants
```

The result label is:

> Downstream phases are conditionally unreachable under the declared model.

The action-scale ambient-breach relationship may appear in the presenter note:
the requested control-plane action lacks verified current authority under the
declared trajectory evidence. It must not replace or narrow the systemic
ambient-breach definition in Band 1.

## 7. Incident-to-lab topology mapping

The visual must make the mapping explicit without claiming the current Envoy
rail mediated the historical foothold.

| Incident concept | Laboratory representation | Boundary |
|---|---|---|
| Compromised worker identity | Deterministic request driver and declared identity | Modeled, not the historical pod |
| Cluster control-plane request | Harmless normalized HTTP request | First action selected for mediated comparison |
| Network enforcement boundary | Envoy frontend | Implemented V3B-1 topology; accepted live result pending |
| Authorization evaluation | Track-specific authorization service | Baseline, signed state, or signed state plus local reduction |
| Consequential target | Harmless marker service | Records `1` only when reached |
| Downstream escalation | Dependency-aware unreachable descendants | Counterfactual consequence, not separate detections |

The application foothold remains outside the current Envoy mediation claim.
The diagram therefore connects the observed cluster API request—not the local
file read or renderer exploit—to the laboratory tracks.

## 8. Presenter/Audience behavior

The production deliverable has two synchronized uses:

- **Standalone diagram:** one presentation-quality, self-explanatory visual;
- **Presenter/Audience scene:** the same semantic structure, with the presenter
  receiving a 30–45-second talk track and the audience receiving only the
  graphic, evidence labels, and takeaway.

The presenter sequence is:

1. follow the observed rail from worker foothold to the expanding blast radius;
2. point to the first mediated request mapped into the controlled lab;
3. compare identical requests across Tracks A, B, and C;
4. emphasize that the KTP result is not an HTTP status code;
5. show the derived `403` and target marker `0`; and
6. close on the observed/modeled/pending evidence labels.

No animation may imply that a pending V3B-1 result has already occurred. If an
animated path is used, it must stop at the evidence boundary and leave pending
elements visibly identified.

## 9. Visual grammar and accessibility

- Incident behavior uses one stable series color, solid line, and explicit
  `Observed incident` label.
- The mapped action and KIL path use a second stable series color plus labels;
  meaning never depends on color alone.
- Modeled-unreachable descendants use neutral low contrast and dashed borders.
- Evidence status is written directly; decorative pseudo-telemetry, fabricated
  hashes, fake timestamps, and unmeasured latency values are prohibited.
- Text remains readable at presentation width and reflows into stacked nodes at
  narrow widths rather than shrinking below readable size.
- Every diagram band and laboratory track has an accessible name or text
  alternative.
- Keyboard and reduced-motion behavior follow the existing demonstration's
  conventions.
- Light and dark themes must preserve contrast and state distinctions.

## 10. Failure handling

If implementation cannot preserve the evidence labels at a supported viewport,
the layout must reflow or simplify; it must not omit the labels. If existing
documentation tests reject the authoritative KTP wording, implementation stops
at a new founder gate rather than changing tests. If the visual would require a
live-service, laboratory, scenario, or evidence-bundle modification, that work
is out of scope and requires separate validation and approval.

## 11. Verification design

The later implementation plan must use test-first verification for presentation
behavior while preserving the current laboratory. At minimum it will specify:

1. source assertions for the three bands, exact evidence labels, KTP-result
   qualifier, `200 / 200 / 403`, and `1 / 1 / 0`;
2. protection checks proving no test, fixture, scenario, controller, Envoy,
   container, evidence, or live-service path changed;
3. standalone and Presenter/Audience visual inspection in Brave/Chromium at
   desktop and narrow widths, in light and dark themes;
4. keyboard, accessible-name, and reduced-motion checks;
5. documentation tests already authorized by the repository; and
6. a final diff review separating observed facts, modeled assumptions, and
   pending validation.

This design does not authorize changing a failing test or starting a live lab.

## 12. Acceptance criteria

The implementation is acceptable only when:

- the observed incident remains the first and dominant story;
- the first mediated cluster API request is the only incident action mapped
  into the current laboratory claim;
- the three isolated tracks consume the same harmless normalized request;
- Track C is the only track with the modeled reducing-only local contribution;
- HTTP status codes are labeled as derived Envoy effects, not KTP wire results;
- the KTP result is described as supervision plus tighten-only constraints;
- downstream phases are conditionally unreachable, not separately prevented;
- observed, modeled, and pending evidence remain visually distinct;
- the full systemic and action-scale ambient-breach relationship is preserved;
- the standalone and synchronized demo forms share the same semantics; and
- no test or live/laboratory artifact changes without separate founder
  validation.

## 13. Approved preview provenance

The founder approved the reconciled composition displayed on 2026-09-01. Its
conversation-scoped source had SHA-256:

```text
9cf1bb01b4febc11b164f52b32eef4b2e4c3a1426fcd3ea9e6f44d9cb2d0b8e6
```

The hash records the approved visual review input. This specification is the
durable controlling design for implementation; the conversation-scoped preview
is not a publication artifact.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
