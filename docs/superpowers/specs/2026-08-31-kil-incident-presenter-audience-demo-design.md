# KIL Incident Presenter/Audience Demo Design

## 1. Decision and scope

KIL will provide one browser-based, incident-centered demonstration with two
synchronized views:

- **Presenter mode** controls the scene, exposes a 30–45-second talk track,
  shows claim boundaries, and can open a linked audience view.
- **Audience mode** follows the presenter automatically and shows only the
  current story graphic, concise labels, evidence status, and takeaway.

The principal visual is an animated branching topological timeline. Its upper
lane reconstructs the disclosed incident path. Its lower lane shows a
counterfactual KIL path terminating at the first mediated Kubernetes
control-plane request. A persistent system topology changes with the selected
scene so every event remains grounded in the affected component. Later scenes
transform that incident boundary into the three-track V3 laboratory topology.

This design changes presentation behavior only. It does not change KTP, the KIL
trust-decay model, the canonical scenario, authorization behavior, lab
orchestration, evidence schemas, or validation status. It does not authorize a
V3B-1 central run.

## 2. Communication objective

The demonstration must let a mixed executive and technical audience answer
four questions without reading a paper:

1. What happened in the disclosed intrusion?
2. Why did possession of valid credentials allow the incident to expand?
3. At which enforceable boundary could KIL conditionally change the outcome?
4. What does the local laboratory reproduce, and what remains modeled or
   pending?

The page should tell this story in approximately five minutes. It must remain
useful as a self-guided audience walkthrough when no presenter view is attached.

## 3. Evidence language

Every scene carries exactly one prominent claim-status label and may include a
secondary boundary note:

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

## 4. Story architecture

The page uses eight scenes. One scene button, previous/next controls, and the
presenter keyboard controls all update the same scene state.

| Scene | Visible title | Evidence status | Story purpose |
|---:|---|---|---|
| 1 | From ambient threat to ambient breach | Observed incident + thesis | Establish why agent-speed credential use defeats checkpoint defenses. |
| 2 | A trusted worker becomes the foothold | Observed incident | Show the renderer-to-worker transition without claiming the current transport lab sees the local read. |
| 3 | The first mediated divergence | Modeled counterfactual | Contrast the observed cluster/API path with KIL withholding the first privileged egress. |
| 4 | One credential path becomes a cascade | Observed incident | Animate node privilege, bulk secret access, cross-cluster administration, mesh enrollment, forged tokens, and CI targeting. |
| 5 | KIL changes authority in motion | Modeled counterfactual | Explain signed composite KTP state, local kinetic reduction, class-bound charge, freshness, and non-expansion. |
| 6 | The incident boundary becomes a lab boundary | Modeled lab mapping | Map incident components to request driver, Envoy, authorization service, and harmless target. |
| 7 | Same request, three enforcement tracks | Modeled V3A + pending V3B-1 | Show baseline permit, signed-state permit, and signed-plus-local-reduction deny. |
| 8 | What is evidence today? | Observed, modeled, pending | Close with provenance, accepted-claim rules, and the current live gate. |

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

The first render is static and complete. Scene changes animate only the path,
node emphasis, authority-charge indicator, and reachability state. Motion never
loops and is disabled when `prefers-reduced-motion` is active.

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

Scene 6 transforms the topology without changing the narrative meaning:

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

Scene 7 displays the same normalized action across:

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
- progress such as `3 of 8`.

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
claim-boundary sentence. The implementation source stores each scene's title,
takeaway, script, status, topology state, and source reference in one immutable
scene object so visual and spoken claims cannot drift independently.

The narrative anchors are:

1. **Ambient breach:** valid credentials are moving at agent speed, so delayed
   detection cannot be the sole control.
2. **Foothold:** distinguish the disclosed application compromise from the
   transport boundary tested by the lab.
3. **First divergence:** explain that `0.95` is modeled and that the deny is a
   conditional counterfactual.
4. **Cascade:** show how privilege and a high-value secret read create several
   dependent branches.
5. **KIL mechanics:** explain signed, short-lived composite KTP state and
   reduction-only local enforcement.
6. **Lab mapping:** show that harmless components preserve the authorization
   question without recreating the breach.
7. **Three tracks:** explain what differs between the tracks and why the third
   is expected to withhold.
8. **Evidence close:** state exactly what is observed, modeled, lab-observed,
   and pending.

## 11. Canonical source and generated export

The implementation will move the durable source into the repository rather
than treating the thread visualization directory as the only editable copy:

- tracked source: `docs/demo/kil-incident-presenter-audience.html`;
- ignored standalone export:
  `artifacts/generated/kil-incident-presenter-audience.html`; and
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

1. every scene ID has a title, 70–90-word script, takeaway, claim status,
   topology state, and source boundary;
2. all eight controls select the correct scene;
3. previous/next and keyboard navigation respect the scene bounds;
4. Presenter mode shows notes and Audience mode omits them;
5. two same-origin pages synchronize a scene change, recover across a presenter
   reload, and reject stale, wrong-session, or unknown-type messages;
6. the first-divergence scene labels `d_t = 0.95` modeled and does not use the
   prohibited absolute claim language;
7. phases 2–8 become conditionally unreachable only in the counterfactual
   state;
8. incident-to-lab mappings are complete and the non-expansion invariant is
   visible;
9. V3A and V3B-1 statuses remain correctly separated;
10. the page has no console error, undefined identifier, missing queried
    element, or external data request; and
11. layouts are visually checked at 736 and 360 pixels in light and dark themes.

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
cutoff.

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
