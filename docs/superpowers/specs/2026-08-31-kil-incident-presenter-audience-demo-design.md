# KIL Presenter/Audience Demo Design: Primer and Incident Case Study

## 1. Decision and scope

KIL will provide one browser-based, incident-centered demonstration with two
synchronized views:

- **Presenter mode** controls the scene, exposes a 30–45-second talk track,
  shows claim boundaries, and can open a linked audience view.
- **Audience mode** follows the presenter automatically and shows only the
  current story graphic, concise labels, evidence status, and takeaway.

The demonstration has two acts. A four-part front matter introduces the
ambient-breach problem, defines KIL, establishes its extension relationship to
KTP, and explains why class-bound authority can decay and be reduced at an
infrastructure boundary. The approved eight-scene incident story follows.

The principal case-study visual is an animated branching topological timeline.
Its upper lane reconstructs the disclosed incident path. Its lower lane shows
a counterfactual KIL path terminating at the first mediated Kubernetes
control-plane request. A persistent system topology changes with the selected
scene so every event remains grounded in the affected component. Later scenes
transform that incident boundary into the three-track V3 laboratory topology.

This design changes presentation behavior only. It does not change KTP, the KIL
trust-decay model, the canonical scenario, authorization behavior, lab
orchestration, evidence schemas, or validation status. It does not authorize a
V3B-1 central run.

## 2. Communication objective

The demonstration must let a mixed executive and technical audience answer
seven questions without reading a paper:

1. Why do ambient breach and agent-speed action exceed a checkpoint-only
   defensive model?
2. What is the Kinetic Infrastructure Layer?
3. How does KIL extend KTP rather than replace or override it?
4. Why can trajectory-derived, class-bound, expiring authority change the
   enforcement result?
5. What happened in the disclosed intrusion?
6. At which enforceable boundary could KIL conditionally change the outcome?
7. What does the local laboratory reproduce, and what remains modeled or
   pending?

The default presenter path should take approximately eight minutes. It must
remain useful as a self-guided audience walkthrough when no presenter view is
attached. A presenter may skip the front matter for an audience already
familiar with KIL, but the case-study act always retains its evidence labels.

## 3. Evidence language

Every prelude and case-study scene carries exactly one prominent claim-status
label and may include a secondary boundary note:

- **KTP source:** a construct grounded in the cited KTP v2.0.0 release,
  enterprise architecture, or Constitution.
- **Proposed KIL thesis:** the project's motivating interpretation of ambient
  breach and ambient enforcement, presented as a design thesis rather than an
  empirical result.
- **Proposed KIL extension:** a KIL-specific architecture, consumption profile,
  or governance proposal that is not represented as existing KTP v2.0.0
  normative behavior.
- **Observed incident:** a fact summarized from Hugging Face's public technical
  timeline. This does not imply access to raw incident telemetry.
- **Modeled counterfactual:** a KIL input or result produced from synthetic,
  declared scenario context. The Phase 1 divergence value `d_t = 0.95` is in
  this class.
- **Lab-observed:** behavior reproduced by a local run whose cited evidence
  bundle satisfies the applicable gate.
- **Pending validation:** a planned or expected live result that has not yet
  satisfied the accepted-evidence gate.

The words `validated`, `prevented`, `proved the historical breach would have
stopped`, and `absolute denial` are prohibited unless the underlying local
evidence supports the exact claim. The primary counterfactual uses:

> Modeled deny at the first mediated privileged egress. Dependent downstream
> actions are conditionally unreachable under the declared model.

Downstream phases made unreachable by an upstream deny are not counted as
separate detections or preventions.

## 4. Two-act story architecture

The page uses a four-part KIL primer followed by the approved eight-scene case
study. One scene button, previous/next controls, and the presenter keyboard
controls all update the same state. The control surface visibly separates
`KIL primer` from `Hugging Face case study`; it does not flatten the material
into an undifferentiated twelve-step list.

### 4.1 Act I — KIL front matter

| Prelude | Visible title | Claim status | Principal visual | Story purpose |
|---:|---|---|---|---|
| P1 | Ambient breach requires ambient enforcement | Proposed KIL thesis | Credential checkpoint passing an authentic request while machine-speed behavior branches beyond it | Establish that cryptographic validity and policy allowance do not establish behavioral legitimacy. |
| P2 | KIL turns authorization into a property of motion | Proposed KIL extension | Focused comparison of credential/policy checkpoints and KIL ambient enforcement | Define KIL, the question it asks, and infrastructure-level consumption of live authority. |
| P3 | KIL is a proposed extension of KTP | KTP source; secondary: proposed KIL extension | Hybrid two-timescale architecture | Show authoritative KTP-derived signed state feeding a faster reducing-only enforcement loop. |
| P4 | Why kinetic authority works | Proposed KIL extension; secondary: modeled parameters | One animated charge trajectory with class isolation and declared-change callouts | Explain slow replenishment, passive decay, rapid loss, per-class history, coupling, and fail-constrained change. |

#### P1 — Ambient breach requires ambient enforcement

The visual adapts the supplied `valid credentials hide novel behavior` graphic.
It shows an authentic credential and allowed action crossing a conventional
credential/policy checkpoint while the resulting machine-speed behavior fans
into novel actions. The graphic asks two different questions:

```text
Checkpoint: Is the credential authentic and is this operation allowed?
KIL: Does this identity's current trajectory carry enough fresh,
class-bound authority for this action now?
```

The page must not describe zero trust generally as only an application-layer or
one-time check. It identifies the narrower structural problem as a
`credential/policy checkpoint pattern` and presents KIL as a proposed evolution
of continuous enforcement into the infrastructure substrate.

No invented operation rate, MITRE technique, token identifier, or anomaly trace
from the reference graphic is retained. The takeaway is: `Valid math can
authenticate a credential without legitimizing the behavior performed with it.`

#### P2 — KIL turns authorization into a property of motion

The visual adapts the supplied classic-versus-ambient comparison into four
claim-safe rows:

| Dimension | Credential/policy checkpoint pattern | KIL ambient enforcement |
|---|---|---|
| Primary question | Is this credential authentic and is the action allowed? | Does fresh, class-bound authority remain sufficient for this action now? |
| Authority | Often represented by a credential, policy result, and expiry window | Consumes signed, short-lived composite KTP state and may apply reducing-only local evidence |
| Enforcement | A decision point beside or ahead of the consequential path | A mediated infrastructure boundary that can forward, constrain, or withhold |
| Time behavior | Authority may remain usable until policy, revocation, or expiry changes | State expires, charge decays, and high divergence can reduce effective authority before the next refresh |

This is an architectural comparison, not a claim that all existing zero-trust
systems share one implementation. The audience takeaway defines ambient
enforcement as pervasive, continuous consumption of fresh authority at the
boundary where actions become consequences.

#### P3 — KIL is a proposed extension of KTP

The visual uses the hybrid two-timescale architecture already integrated into
the KIL paper:

```text
Authoritative loop — KTP-derived, slower
  trajectory + standing + environment + constraints
  -> derive and sign short-lived Q_i,c
  -> only this loop may expose increased composite authority

Fast enforcement loop — KIL consumption profile
  request + authentic/fresh Q_i,c + veto/environment checks
  + optional fresh local reduction
  -> permit | constrain | deny | indeterminate
```

The page states that KIL is a proposed KTP extension profile, initially scoped
against KTP v2.0.0 and potentially expressible through a future 2.1 or 3.0
governance path. Existing KTP constructs remain authoritative. KIL adds the
composition, binding, freshness, reducing-only consumption, and decision-record
requirements needed at infrastructure enforcement points.

The audience view includes a concise source footer linking the KTP v2.0.0
release, Enterprise architecture, Constitution, and canonical `CITATION.cff`.
The presenter view carries the fuller boundary note distinguishing KTP source
constructs from proposed KIL behavior.

The non-expansion invariant is always visible:

```text
KIL_effective_authority <= KTP_authorized_authority
```

The visual must say `fast enforcement path`, not `microsecond enforcement`,
until measured evidence supports a latency claim.

#### P4 — Why kinetic authority works

The visual synthesizes the supplied trust-decay graphics into one readable
trajectory rather than four permanent panels. It steps through:

1. **Earn slowly:** confirmed low-divergence behavior can contribute only to a
   later authentic signed state; an action never earns authority for itself.
2. **Remain class-bound:** assigned-data read history does not subsidize a
   first cluster-admin, token-minting, or external-egress action.
3. **Decay passively:** silence does not preserve standing authority
   indefinitely; charge and signed state age.
4. **Lose quickly:** superlinear modeled loss can clamp effective authority for
   the requested class after high divergence.
5. **Couple carefully:** a versioned directed graph may reduce related
   higher-consequence classes; coupling coefficients remain modeled.
6. **Handle legitimate change:** an auditable declared-change envelope widens
   only a bounded expected range and cannot override a KTP veto or expand an
   undeclared authority class.

The reference graphics' `bypass`, `instant irreversible`, `threat detected`,
and universal-physics wording is rejected. Initial weights, thresholds, decay
constants, loss rates, exponents, and coupling coefficients remain modeled
parameters subject to sensitivity testing.

### 4.2 Act II — eight-scene Hugging Face case study

| Scene | Visible title | Evidence status | Story purpose |
|---:|---|---|---|
| 1 | From ambient threat to ambient breach | Observed incident + thesis | Establish why agent-speed credential use defeats checkpoint defenses. |
| 2 | A trusted worker becomes the foothold | Observed incident | Show the renderer-to-worker transition without claiming the current transport lab sees the local read. |
| 3 | The first mediated divergence | Modeled counterfactual | Contrast the observed cluster/API path with KIL withholding the first privileged egress. |
| 4 | One credential path becomes a cascade | Observed incident | Animate node privilege, bulk secret access, cross-cluster administration, mesh enrollment, forged tokens, and CI targeting. |
| 5 | KIL changes authority in motion | Modeled counterfactual | Apply the primer's signed state, local reduction, class charge, freshness, and non-expansion concepts to the incident. |
| 6 | The incident boundary becomes a lab boundary | Modeled lab mapping | Map incident components to request driver, Envoy, authorization service, and harmless target. |
| 7 | Same request, three enforcement tracks | Modeled V3A + pending V3B-1 | Show baseline permit, signed-state permit, and signed-plus-local-reduction deny. |
| 8 | What is evidence today? | Observed, modeled, pending | Close with provenance, accepted-claim rules, and the current live gate. |

### 4.3 Transition into the case study

After P4 the interface displays a clear act transition:

> The July 2026 Hugging Face disclosure now gives us a source-cited sequence
> against which to ask a counterfactual question: where would the modeled KIL
> boundary first withhold authority, and what dependent actions would then be
> unreachable?

The transition adapts the supplied escalating-blast-radius graphic but does not
call the incident a `classic zero trust failure`, claim that every credential
was `perfectly valid`, or describe modeled cutoffs as observed physical facts.

### 4.4 Supplied graphic selection and corrections

The supplied graphics are design references, not evidence artifacts. The
implementation recreates their useful explanatory structures in responsive
HTML/SVG and applies these rules:

| Reference concept | Demo use | Required correction |
|---|---|---|
| Valid credential crossing a checkpoint while behavior branches | P1 | Remove invented operations-per-second, technique IDs, token IDs, and synthetic traces. |
| Checkpoint pattern versus ambient enforcement | P2 | Avoid claiming all zero-trust architectures are static, one-time, or application-only. |
| Hybrid two-timescale loop | P3 and case-study Scene 5 | Preserve KTP authority, `Q_i,c`, expiry, and reducing-only local overlay; remove unmeasured `microsecond` language. |
| Earn slowly, decay passively, lose quickly, isolate classes | P4 | Use the paper's weighted diagonal standardized distance, not a full Mahalanobis claim; remove `irreversible` and `bypass` language. |
| Escalating incident blast radius | Transition and Scene 4 | Use the canonical source-cited dependency graph; do not label the whole incident a generic zero-trust failure. |
| Phase 1 transport cutoff | Scene 3 | Label `d_t = 0.95` and the deny modeled; state that descendants are conditionally unreachable. |
| Phase 4 bulk secret read | Scene 4 | Use canonical modeled divergence `0.90`, not `>0.99`; do not claim measured microsecond latency or validated zero-byte exfiltration. |
| Correctly signed forged token | Scene 4 | State that signature validity is necessary but insufficient under the model; avoid the absolute slogan that trajectory always survives key theft. |
| Single cutoff and downstream defense | Scene 4 | Replace `for free`, `killed`, and separate-prevention counts with dependency-aware reachability language. |
| Validation ladder | Scenes 7–8 | Show V1 deterministic, V2 modeled historical replay, V3A modeled process contract, pending V3B-1 local Envoy, future V3B-2 Kind/Calico, and V4 publication; do not depict current V3B-1 as a live Kubernetes result. |

Decorative ruler marks, fake telemetry windows, fabricated hashes, timestamps,
and pseudo-measurement readouts are omitted. The engineering-drawing aesthetic
may be retained through restrained grid, boundary, lane, and annotation motifs
that do not imply measurement.

## 5. Primary branching timeline

### 5.1 Composition

The founder-supplied reference establishes the visual grammar. The production
graphic will be responsive, semantic HTML plus inline SVG rather than a raster
copy.

The upper lane is labeled `Disclosed incident` and uses a solid attack path.
The lower lane is labeled `KIL counterfactual · modeled` and uses a distinct
solid path. Both reach a vertical enforcement boundary positioned at Phase 1.

In the disclosed lane, the path continues through the later phases and branches
after the high-value secret access into:

- cross-cluster administration;
- mesh/VPN enrollment;
- forged identity tokens; and
- source-control and CI targeting.

In the KIL lane, an action envelope reaches the enforcement boundary, the
modeled authority charge moves to zero for the requested class, and the request
is withheld. Phases 2–8 remain visible but become low-contrast, dashed, and
marked `Conditionally unreachable`. Color is always paired with lane labels,
line style, icons, and explanatory text.

### 5.2 Claim-safe corrections to the reference

The production graphic must:

- label `d_t = 0.95` as a modeled scenario input;
- replace `absolute denial` with `modeled deny at mediated boundary`;
- replace `prevented structurally` with `conditionally unreachable under the
  declared model`;
- identify Phase 4 as a later leverage point in the observed incident, not the
  first KIL cutoff; and
- remove the duplicated `timeline-timeline` subtitle.

### 5.3 Scene transitions

When the case-study act begins, its first render is static and complete. Scene
changes animate only the path, node emphasis, authority-charge indicator, and
reachability state. Motion never loops and is disabled when
`prefers-reduced-motion` is active.

## 6. Persistent incident topology

The topology remains adjacent to or immediately below the primary graphic on
wide screens and follows it on narrow screens. It contains these labeled nodes:

```text
External evaluation agent / sandbox
  -> dataset configuration renderer
  -> production dataset worker pod
  -> KIL-mediated egress boundary
       -> Kubernetes control plane
       -> cloud metadata / temporary credentials
  -> privileged workload / node
  -> cluster secret store
       -> shared connector -> other clusters
       -> mesh credential -> corporate mesh
       -> signing capability -> forged identity tokens
       -> source-control installation token -> CI / source control
```

The diagram is a topology, not a claim that every edge occurred in one exact
packet sequence. Scene selection highlights the relevant disclosed transition,
and dependency edges show why an upstream modeled deny changes descendant
reachability.

The KIL enforcement boundary overlays the worker's outbound path. The diagram
may show the earlier renderer/file-read anomaly as `trajectory signal visible
to an application- or kernel-aware adapter`, but it must not claim the current
Envoy laboratory can block that local read.

## 7. Incident-to-lab mapping

Case-study Scene 6 transforms the topology without changing the narrative
meaning:

| Incident role | Lab representation | Meaning preserved |
|---|---|---|
| Compromised dataset worker | One-shot request driver | Originates the normalized consequential action. |
| Workload outbound boundary | Envoy | Only transport path to authorization and target. |
| Signed KTP/KIL enforcement state | Authorization-service input | Supplies fresh class-bound authority without granting expansion. |
| Live trajectory divergence | Local kinetic reduction input | Can reduce or withhold authority, never override a veto or add authority. |
| Kubernetes/cloud consequential action | Harmless target marker | Makes forwarding or withholding observable without reproducing harm. |
| Incident and decision provenance | Canonical records and integrity bundle | Separates source facts, modeled inputs, decisions, and lab evidence. |

Mapping connectors visibly join each incident role to its laboratory analogue.
The page states that the lab reproduces the enforcement boundary, not the full
historical intrusion or production Kubernetes estate.

## 8. Three-track comparison

Case-study Scene 7 displays the same normalized action across:

1. credential-policy baseline;
2. signed composite KTP state only; and
3. signed state plus live local kinetic reduction.

The current modeled comparison is `permit / permit / deny`, represented as
`HTTP 200 / 200 / 403` and target markers `1 / 1 / 0`. Until an accepted V3B-1
bundle exists, the page identifies these outcomes as V3A modeled
process-contract evidence and marks the central live result pending.

The track display must not visually imply that signed state alone is defective.
Its purpose is to show the distinct contribution of fresh local reduction when
the authoritative signed state has not yet refreshed. Every view restates the
non-expansion invariant: local evidence can only reduce or withhold authority.

## 9. Presenter and audience views

### 9.1 Presenter mode

Presenter mode contains:

- scene buttons and previous/next controls;
- a visible 30–45-second `Say this` script for the selected scene;
- the current audience takeaway;
- claim-status and source-boundary notes;
- an `Open audience view` action; and
- a connection indicator showing whether an audience view has acknowledged the
  current scene.

The presenter can hide notes for rehearsal, but hiding them does not change
audience state. Left/right arrow keys advance scenes when focus is not inside a
control.

### 9.2 Audience mode

Audience mode contains:

- the selected scene title;
- the primary graphic and persistent topology;
- one concise takeaway;
- the claim-status label; and
- act-aware progress such as `Primer P3 of P4` or `Case study 3 of 8`.

It hides presenter scripts, source notes, synchronization diagnostics, and
editing controls. It remains self-guided if no presenter is connected: scene
buttons and previous/next controls appear only after the view determines it is
standalone, not when it is following a presenter.

### 9.3 Local synchronization contract

The canonical page supports query parameters:

```text
?mode=presenter&session=<random-session-id>
?mode=audience&session=<same-session-id>
```

For pages served from the same localhost origin, synchronization uses a
run-scoped `BroadcastChannel` named from the session ID. No network service,
external dependency, or telemetry is required. Messages use a closed envelope;
the presenter-state message is:

```json
{
  "schema_version": "kil.presenter-state.v1",
  "message_type": "state",
  "session_id": "<session>",
  "presenter_epoch": "<random-id-created-at-presenter-load>",
  "sequence": 7,
  "scene_id": "first-divergence",
  "sent_at": "<ISO-8601 timestamp>"
}
```

The other closed message types are `request_state` and `ack`. Each carries the
same schema version and session ID. An acknowledgement also carries a random
audience ID, the presenter epoch, and the applied sequence.

The presenter is the only state authority. Audience views reject unknown
message types, wrong sessions, invalid scenes, and stale sequence numbers
within the current presenter epoch. On load or reconnect an audience sends a
state request and the presenter replies with the complete current state. A new
presenter epoch resets the audience's sequence comparison only after a valid
full-state reply, so a presenter reload cannot leave the audience permanently
stale. If the synchronization API is unavailable, both modes remain operable
and display a concise `Not synchronized` status; they do not silently claim a
connection.

The synchronized dual-window mode is supported on the existing localhost demo
surface. A directly opened standalone file may be used independently, but
cross-window synchronization is not claimed for opaque `file:` origins.

## 10. Talk-track contract

Each script is 70–90 spoken words, uses plain language, and ends with a
claim-boundary sentence. The implementation source stores each prelude or
case-study scene's act, title, takeaway, script, status, topology state, and
source reference in one immutable scene object so visual and spoken claims
cannot drift independently.

The primer anchors are:

1. **Ambient breach:** explain why cryptographic validity and policy allowance
   do not establish behavioral legitimacy at agent speed.
2. **KIL definition:** define ambient enforcement as continuous consumption of
   fresh authority at the infrastructure boundary where action becomes
   consequence.
3. **KTP relationship:** explain that KTP remains authoritative while KIL adds
   a proposed signed-state consumption and reducing-only enforcement profile.
4. **Why it works:** explain slow replenishment, passive decay, rapid modeled
   loss, class isolation, coupling, and bounded declared change.

The case-study anchors are:

1. **Ambient breach in the incident:** connect valid credential use at agent
   speed to the disclosed sequence without generalizing beyond the source.
2. **Foothold:** distinguish the disclosed application compromise from the
   transport boundary tested by the lab.
3. **First divergence:** explain that `0.95` is modeled and that the deny is a
   conditional counterfactual.
4. **Cascade:** show how privilege and a high-value secret read create several
   dependent branches.
5. **KIL mechanics applied:** explain signed, short-lived composite KTP state
   and reduction-only local enforcement in this scenario.
6. **Lab mapping:** show that harmless components preserve the authorization
   question without recreating the breach.
7. **Three tracks:** explain what differs between the tracks and why the third
   is expected to withhold.
8. **Evidence close:** state exactly what is observed, modeled, lab-observed,
   and pending.

## 11. Canonical source and generated export

The implementation will move the durable source into the repository rather
than treating the thread visualization directory as the only editable copy:

- tracked source: `docs/demo/kil-presenter-audience-demo.html`;
- ignored standalone export:
  `artifacts/generated/kil-presenter-audience-demo.html`; and
- optional thread visualization copy for inline inspection.

The tracked file is self-contained, uses no remote data, and can be served by a
localhost-only static server. Generated exports must identify the source commit
and build timestamp without claiming that presentation generation validates
lab evidence.

## 12. Accessibility and responsive behavior

- All scene and navigation controls are native buttons with pressed/current
  state.
- Dynamic scene summaries use `aria-live="polite"`; animations do not announce
  every frame.
- Every SVG has a title, description, and equivalent text summary.
- Meaning never depends only on color.
- Presenter and audience layouts work at 736 pixels and 360 pixels without
  horizontal page overflow.
- On narrow screens the primary timeline, topology, and notes stack in that
  order.
- Essential labels remain at least 11 screen pixels and do not overlap paths or
  nodes.
- Keyboard navigation and reduced-motion behavior are verified explicitly.

## 13. Test and review strategy

Implementation follows a test-first plan. At minimum, automated or browser
checks must prove:

1. every prelude and case-study ID has an act, title, 70–90-word script,
   takeaway, claim status, visual state, and source boundary;
2. all four primer controls and all eight case-study controls select the correct
   state without collapsing the two acts into one unlabeled sequence;
3. previous/next and keyboard navigation respect act and scene bounds;
4. Presenter mode shows notes and Audience mode omits them;
5. two same-origin pages synchronize a scene change, recover across a presenter
   reload, and reject stale, wrong-session, or unknown-type messages;
6. the KTP-extension prelude displays the non-expansion invariant and labels
   KIL-specific behavior proposed;
7. the first-divergence scene labels `d_t = 0.95` modeled and does not use the
   prohibited absolute claim language;
8. phases 2–8 become conditionally unreachable only in the counterfactual
   state;
9. incident-to-lab mappings are complete and the non-expansion invariant is
   visible;
10. V3A, V3B-1, and future V3B-2 statuses remain correctly separated;
11. no visual contains invented latency, throughput, telemetry, hash, anomaly,
    validation, or production-Kubernetes claims;
12. the page has no console error, undefined identifier, missing queried
    element, or external data request; and
13. layouts are visually checked at 736 and 360 pixels in light and dark themes.

The generated export must be compared against the tracked source and opened on
the localhost demonstration surface before handoff.

## 14. Non-goals

This design does not:

- reproduce or simulate harmful exploitation;
- assert access to unpublished Hugging Face telemetry;
- claim KIL would certainly have prevented the historical intrusion;
- claim the Envoy rail mediates local file reads, kernel calls, SmartNICs, SDN,
  or all Kubernetes admission paths;
- change the canonical scenario values or trust-decay mathematics;
- consume live evidence dynamically from an unverified run directory;
- expose private lifecycle evidence or foreign-resource names; or
- unlock, execute, or promote the pending V3B-1 central run.

## 15. Rejected alternatives

### Static image only

Rejected because it cannot keep the presenter narrative, topology, phase state,
and evidence boundary synchronized. The founder reference is used as visual
direction, not shipped as the sole explanatory artifact.

### Dense side-by-side incident-versus-KIL dashboard

Rejected because it forces the audience to compare too many simultaneous
labels and weakens the causal moment at the first mediated divergence.

### Separate incident presentation and laboratory presentation

Rejected because the audience must mentally reconstruct the mapping between the
historical action and the harmless local enforcement boundary.

### Audience control of shared state

Rejected because competing controls make a live presentation nondeterministic.
Audience mode follows one presenter authority and becomes self-guided only when
not connected.

## 16. Approval and next gate

The founder has approved the incident-centered direction, synchronized
Presenter/Audience model, branching visual grammar, 30–45-second scripts, and
the first mediated privileged egress as the principal KIL counterfactual
cutoff. Founder review then added a four-part front matter covering ambient
breach, KIL, the KTP extension boundary, and the trust-decay mechanism. This
revision incorporates that direction and requires renewed written-design
approval before implementation.

This written specification requires founder review before implementation. After
approval, the next gate is a test-first implementation plan. The V3B-1 foreign
resource snapshot specification remains a separate approval dependency for the
central laboratory run; this presentation design does not bypass it.

## References

1. Hugging Face, [Anatomy of a Frontier Lab Agent Intrusion: A Technical
   Timeline of the July 2026 Incident](https://huggingface.co/blog/agent-intrusion-technical-timeline).
2. Kinetic Trust Protocol, [version 2.0.0
   specification](https://github.com/nmcitra/ktp-rfc/tree/v2.0.0).
3. Kinetic Trust Protocol, [enterprise
   architecture](https://kinetic-trust-protocol.net/enterprise/architecture).
4. Kinetic Trust Protocol, [Constitution and Zeroth
   Law](https://kinetic-trust-protocol.net/learn/constitution).

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
