# KIL–KTP specialist lineage log

## Purpose

This is the durable briefing and decision log for KTP specialists reviewing the
Kinetic Infrastructure Layer (KIL). It preserves why the project exists, how
its architecture evolves, where it relies on KTP, what it may add to KTP, and
which claims remain unapproved or unvalidated.

This log records lineage; it is not itself the normative KIL specification.
Later entries may refine or supersede proposals, but earlier entries remain as
an audit trail.

## Logging convention

Every substantive KIL turn records:

- the input or question;
- the current interpretation;
- whether the result is confirmed, proposed, or unresolved;
- the rationale and protocol implications;
- affected artifacts; and
- the next design gate.

Evidence language retains the project-wide meanings:

- `observed`: directly supported by a named primary source;
- `modeled`: an explicit counterfactual assumption or synthetic signal; and
- `validated`: behavior reproduced in the local reference implementation.

## Lineage before the formal log

### L-001 — Original ambition

**Status:** Historical context

The founder asked for a deeply innovative public demonstration of how AI has
changed and accelerated cybersecurity. The initial option space included an AI
Security Debt Index, AI red/blue arena, LLM pentest toolkit, AI-attacker
honeypots, Zero Trust for Agents, and a security accelerator with a standardized
red-team gauntlet.

### L-002 — KTP changes the center of gravity

**Status:** Historical context

Adding KTP redirected the work toward trajectory-bound authorization for
autonomous agents. The central opportunity became demonstrating that authority
can depend on how an identity is moving through a system, rather than only on a
static credential or one-time policy decision.

### L-003 — Ambient enforcement and KIL

**Status:** Foundational concept; implementation not yet approved

The work reframed zero trust from a checkpoint decision into a continuously
recomputed property enforced at an infrastructure boundary. This produced the
terms **Kinetic Infrastructure Layer** and **ambient enforcement**. The concept
includes decaying authority, trajectory evidence, infrastructure enforcement,
decision provenance, and safe degradation for legitimate rare events.

### L-004 — Incident replay and trust model

**Status:** Source drafts; not validated

The July 2026 Hugging Face agent-intrusion timeline was selected as the public
counterfactual case. Two source drafts were created: a side-by-side incident
timeline and a trust-decay model. They remain preserved inputs, not approved
specifications or proof that KIL would have prevented the incident.

### L-005 — Paired project and evidence contract

**Status:** Confirmed

KIL became a paired technical paper and executable reference implementation,
with an offline deterministic incident replay and local Kubernetes validation.
The project adopted the `observed` / `modeled` / `validated` evidence contract
and explicitly reserved `validated` for locally reproduced behavior.

### L-006 — First architecture candidate

**Status:** Proposed; awaiting architecture approval

The initial hybrid two-timescale candidate used one deterministic decision
interface for replay and live enforcement:

```text
permit = veto_clear ∧ A(action) ≤ E(environment) ∧ Q_i,c ≥ τ_c ∧ evidence_fresh
```

`Q_i,c` was provisionally described as ephemeral, identity- and
authority-class-bound trajectory charge. Its reducing-only boundary prevents it
from overriding a KTP veto or expanding the KTP environmental envelope.

## Turn-by-turn specialist record

### T-001 — 2026-08-27 — Resume at Architecture Gate 1

**Input:** Resume work at the first architecture approval gate.

**Interpretation:** No lab implementation begins until the KTP/KIL semantic
boundary, components, data flow, safety behavior, and test strategy are approved
and written as a reviewed specification.

**Status:** Confirmed process gate.

**Affected artifacts:**

- `docs/checkpoints/2026-08-24-specialist-consultation.md`
- `docs/design-drafts/hybrid-two-timescale-architecture.html`

**Next gate:** Resolve whether `Q_i,c` is a KIL extension, an expression of KTP,
or an implementation-local metric.

### T-002 — 2026-08-27 — Specialist interpretation of `Q_i,c`

**Input:** The KTP specialist views `Q_i,c` as an expression of existing KTP
constructs. He views KIL as a layer on top of KTP that extends the protocol and
could become part of KTP 2.1 or possibly 3.0.

**Working interpretation:**

- `Q_i,c` should not be introduced as an independent trust primitive competing
  with KTP.
- KIL should derive the runtime quantity from explicitly mapped existing KTP
  constructs.
- The extension candidate is the operational contract for continuous,
  transport-bound enforcement: how derived KTP state is carried, refreshed,
  consumed, constrained, and audited at the infrastructure layer.
- Version placement remains unresolved. A backward-compatible, optional
  extension may fit KTP 2.1; changes to core semantics or wire invariants may
  require KTP 3.0.

**Status:** Specialist direction confirmed; exact construct mapping and version
classification remain proposed pending detailed review.

**Rationale:** This preserves KTP as the source of trust semantics while making
KIL the execution and enforcement realization. It avoids inventing a parallel
trust system and keeps the reference implementation useful whether the
extension is standardized in 2.1 or deferred to 3.0.

**Affected artifacts:** The architecture draft and later extension proposal
must replace language that presents `Q_i,c` as a standalone KIL primitive with
language describing a derived KTP enforcement state. No artifact has been
modified yet; Architecture Section 1 remains unapproved.

**Next gate:** Identify the existing KTP constructs that contribute to the
derived runtime state and define the minimum new transport-enforcement contract.

### T-003 — 2026-08-27 — Preliminary check against KTP v2.0.0 structure

**Input:** Before refining the architecture, compare the specialist direction
with the authoritative KTP v2.0.0 RFC inventory rather than relying on earlier
brainstorming terminology.

**Preliminary mapping:** The published KTP structure already assigns the likely
inputs and enforcement responsibilities across existing specifications:

- KTP-Core: Trust Score, Context Tensor, Trust Proof, Silent Veto, and
  anti-Goodhart measures;
- KTP-Identity: Vector Identity, Trajectory Chains, and Proof of Resilience;
- KTP-Gravity: real-time constraints and the physics of denial;
- KTP-Enforce: Policy Enforcement Points, Trust Tiers, Adaptive Dormancy, and
  Mass Ceiling;
- KTP-Transport: wire formats and real-time transport protocols; and
- KTP-Audit: Decision Geometry, immutable logging, forensics, and
  counterfactual analysis.

**Working interpretation:** These existing constructs support the specialist's
view that `Q_i,c` should be derived rather than standardized as a second trust
score. The plausible new KIL contribution is a narrow composition and runtime
binding contract across existing RFCs, plus reference behavior and conformance
vectors for transport-native enforcement.

**Status:** Preliminary. The RFC inventory supports the direction, but the full
normative text must be mapped clause-by-clause before declaring an extension
gap or selecting KTP 2.1 versus 3.0.

**Primary source:** [KTP v2.0.0 RFC repository](https://github.com/nmcitra/ktp-rfc/tree/v2.0.0).

**Next gate:** Decide whether KIL exposes one composite derived enforcement
state or preserves the contributing KTP values independently through the hot
path.

### T-004 — 2026-08-27 — Composite enforcement state selected

**Input:** KIL enforcement points should consume a **signed, short-lived
composite KTP enforcement state** rather than independently recomputing
authority from all individual KTP inputs on every action.

**Decision:** Confirmed architectural direction.

**Interpretation:**

- KTP remains authoritative for the trust semantics and derivation of the
  effective enforcement state.
- The hot-path KIL adapter verifies and consumes a compact, signed state rather
  than ingesting raw Context Tensor observations or reproducing the complete
  KTP computation.
- The state must be bound to the relevant identity, authority class, execution
  environment or zone, action scope, issuance time, expiry time, ordering or
  freshness data, and the applicable veto/envelope result.
- The state must carry or reference sufficient derivation and evidence digests
  for KTP-Audit Decision Geometry without exposing unnecessary raw context at
  every enforcement point.
- Expiry or failed verification cannot expand authority. Exact stale-state
  behavior remains part of the safety design.

**Why this direction:** It gives eBPF, service-mesh, Kubernetes, and later
enforcement adapters one stable verification contract; reduces latency and
privacy exposure; prevents different enforcement points from deriving
inconsistent authority; and creates a concrete candidate extension across
KTP-Transport, KTP-Enforce, and KTP-Audit.

**Still unresolved:**

- the normative name and schema of the composite state;
- which KTP component or quorum may issue and sign it;
- TTL and refresh semantics by authority class;
- revocation and anti-replay behavior; and
- whether a KIL enforcement point may apply a local reducing-only overlay
  between signed refreshes.

**Affected artifacts:** The later architecture specification and extension
proposal will define the composite-state contract. The current visual remains a
draft until the local-overlay and failure semantics are approved.

**Next gate:** Decide whether local enforcement points may immediately reduce
the signed state using newer local evidence, or must wait for a newly signed KTP
state for every change.

### T-005 — 2026-08-29 — Main-paper opening thesis added

**Input:** The founder supplied the opening statement for the main paper on
Kinetic Infrastructure.

**Interpretation:** The paper will begin by framing cybersecurity as moving from
ambient risk and ambient threat toward continuous ambient breach, requiring a
corresponding move from detect-and-prevent operations to ambient enforcement.
Kinetic infrastructure is presented as the mechanism for enforcing immutable
constraints at adversarial AI speed rather than as a reactive security overlay.

**Decision:** Confirmed editorial direction. The supplied statement is now the
introduction of the main manuscript, with only spacing, HTML-entity, punctuation,
and minor grammatical normalization.

**Evidence status:** This is the paper's thesis and motivation, not a validated
result. Claims about the insufficiency of current controls, ambient breach,
autonomy, speed, and threat neutralization require sources, definitions, and
careful qualification during manuscript development.

**Rationale:** The introduction communicates the project's public purpose before
the paper enters KTP semantics, the extension boundary, formal model, replay,
local validation, limitations, and falsifiable claims.

**Affected artifacts:**

- `docs/paper/kinetic-infrastructure.md`
- `docs/paper/README.md`

**Unresolved questions:** The final paper title, citations supporting the
opening claims, operational definitions for `ambient breach` and `ambient
enforcement`, and whether “independent of human intervention” needs a safety
qualification in the opening remain subject to editorial review.

**Next gate:** Return to Architecture Gate 1 and decide whether local
enforcement points may apply an immediate reducing-only constraint between
signed KTP state refreshes.

### T-006 — 2026-08-29 — `Q_i,c` confirmed as a new KTP extension

**Input:** The founder clarified that `Q_i,c` is a new extension and should
relate to KTP as an extension for KTP 2.0, with a possible future expression in
KTP 2.1 or 3.0.

**Decision:** Confirmed architectural and protocol direction.

**Clarification of earlier lineage:** Entries T-002 and T-003 correctly preserve
the requirement that `Q_i,c` derive from existing KTP constructs and must not
become a competing trust system. This entry supersedes any reading of those
entries that would classify `Q_i,c` as merely an implementation-local metric or
as having no normative extension semantics.

**Current interpretation:**

- `Q_i,c` is a new, signed, short-lived KIL composite enforcement state.
- Existing KTP constructs supply its authoritative trust, trajectory,
  constraint, identity, enforcement, transport, and audit semantics.
- KIL adds the normative composition, binding, freshness, consumption,
  reducing-only enforcement, and audit contract required at infrastructure
  enforcement points.
- The initial specification is an extension profile layered on KTP v2.0.0.
- Backward-compatible standardization may fit KTP 2.1; changes to core
  invariants, mandatory processing, or wire semantics may require KTP 3.0.

**Rationale:** Treating the composite state as an extension makes KIL
interoperable and testable rather than leaving a critical authorization value as
private implementation behavior. Deriving it from KTP preserves semantic
continuity and prevents duplication of KTP trust primitives.

**Affected artifacts:**

- `docs/extension/README.md`
- `docs/checkpoints/2026-08-24-specialist-consultation.md`
- the future architecture specification, extension schema, conformance vectors,
  and transport adapters

**Unresolved questions:** Exact contributing KTP fields, schema name, issuer and
signature authority, TTL classes, revocation, replay protection, local
reducing-only behavior, and final KTP version placement.

**Next gate:** Decide whether local enforcement points may immediately apply a
reducing-only constraint between signed KTP state refreshes.

### T-007 — 2026-08-29 — Official KIL white paper initiated

**Input:** The founder directed the project to develop the official KIL white
paper using the KIL trust-decay model and the ambient-enforcement analysis of
the Hugging Face incident. The paper must be a handout deliverable, such as a
PDF, and must be tied directly to the lab/demo as supporting and authoritative
information. The founder-approved opening statement has already been supplied.

**Decision:** Confirmed deliverable and publication contract.

**Interpretation:**

- The white paper is a primary KIL deliverable, not retrospective marketing
  material added after the implementation.
- The canonical manuscript, executable replay, lab scenario, decision records,
  tables, and figures must derive from the same versioned evidence and result
  artifacts.
- Historical incident facts remain `observed`; counterfactual KIL inputs and
  outcomes remain `modeled`; only locally reproduced lab behavior may be called
  `validated`.
- The trust-decay and incident-timeline drafts are source material to be
  reconciled with KTP v2.0.0, the confirmed KIL extension direction, and primary
  incident sources before they become authoritative prose.
- The PDF must remain understandable as a standalone handout while providing
  precise references back to reproducible lab artifacts.

**Rationale:** A shared evidence chain prevents the paper and demo from drifting
into separate stories. It makes every quantitative figure, cutoff point, and
performance statement traceable to a source manifest, model version, or lab
run, while keeping unexecuted counterfactuals visibly distinct from validation.

**Affected artifacts:**

- `docs/paper/kinetic-infrastructure.md`
- `docs/drafts/kil-trust-decay-model.md`
- `docs/drafts/ambient-enforcement-vs-huggingface-incident.md`
- the future paper design specification, citation database, figure sources,
  generated PDF, replay reports, and lab run manifests

**Unresolved questions:** Primary audience, target length, handout context,
technical depth, author attribution, visual identity, publication versioning,
and the exact mechanism connecting manuscript claims to lab evidence.

**Next gate:** Select the paper's primary audience and target length before
choosing among executive, dual-layer, and research-paper structures.

### T-008 — 2026-08-29 — Hybrid two-timescale architecture required in paper

**Input:** The founder required the hybrid two-timescale architecture to be
integrated correctly into the official KIL white paper.

**Decision:** Confirmed publication and architecture-integration requirement.

**Interpretation:**

- The architecture will be part of the paper's central technical argument,
  rather than a detached illustration or optional appendix.
- The phrase *two-timescale* refers to two temporal control loops: (1) a slower
  authoritative loop that derives, signs, expires, and refreshes the composite
  KTP enforcement state, and (2) a faster data-plane loop that evaluates each
  requested action at the transport enforcement point.
- The offline historical replay and the live local-cluster validation are two
  execution rails that exercise the same decision contract; they are not the
  two timescales themselves.
- The paper, architecture figure, implementation interfaces, telemetry, and lab
  measurements must use the same terms and expose both loops distinctly.
- Whether the fast loop may impose a new local reducing-only constraint between
  signed refreshes remains an unresolved normative choice. The paper must not
  silently assume that authority until it is approved.

**Rationale:** Separating temporal loops from experimental rails prevents an
architectural category error. It also makes the lab capable of measuring state
freshness and refresh behavior separately from per-action enforcement latency,
while preserving the requirement that KIL cannot expand KTP authority.

**Affected artifacts:**

- `docs/paper/kinetic-infrastructure.md`
- `docs/design-drafts/hybrid-two-timescale-architecture.html`
- the future white-paper design specification and PDF figure set
- the future signed-state issuer, enforcement adapter, replay engine, telemetry
  schema, and lab result manifests

**Unresolved questions:** The permitted scope of fast-loop reducing-only local
constraints; refresh cadence and TTL by authority class; stale-state behavior;
paper audience and length; and the exact measurements shown in the figure and
demo.

**Next gate:** Decide whether the fast enforcement loop may immediately reduce
or withhold authority between signed composite-state refreshes, without ever
increasing authority or overriding a KTP veto.

### T-009 — 2026-08-29 — Authoritative KTP and incident citations required

**Input:** The founder required the white paper to cite the KTP v2.0.0 RFC
release, the official Enterprise KTP architecture, the KTP Constitution, and
the Hugging Face technical incident timeline.

**Decision:** Confirmed source and citation policy; initial citations added to
the canonical manuscript.

**Interpretation:**

- KTP v2.0.0 is the versioned normative baseline for protocol terminology and
  behavior used by the paper.
- The Enterprise KTP architecture is an official explanatory source for the
  action-authorization plane, enforcement surfaces, and least-trajectory
  framing.
- The KTP Constitution is the governing source for the principles against which
  KIL safety, graceful degradation, accountability, and immutable constraints
  are evaluated.
- The Hugging Face technical timeline is the primary source for observed facts
  in the public incident case study.
- No citation to the incident report converts a KIL counterfactual into a
  validated result. Modeled inputs and outcomes remain labeled as such until
  reproduced in the local lab.
- The canonical KTP `CITATION.cff` remains included for formal attribution.

**Rationale:** Assigning each source a defined evidentiary role prevents
explanatory pages from silently becoming normative protocol text and prevents
incident facts from being conflated with untested KIL prevention claims.

**Affected artifacts:**

- `docs/paper/kinetic-infrastructure.md`
- the future citation database, claim-evidence matrix, figure captions, and PDF
- the future replay trace and lab result manifests

**Unresolved questions:** Final bibliography style; author and institutional
attribution; archival snapshots or persistent identifiers for web sources; and
the exact paragraph-, event-, and figure-level citation mapping.

**Next gate:** Resolve the fast-loop reducing-only authority question, then
select the paper's primary audience and target length.

### T-010 — 2026-08-29 — Trust model and incident analysis to become one asset

**Input:** The founder directed that the complete scope of the local trust-decay
model and the supporting ambient-enforcement analysis of the Hugging Face
incident be incorporated into the official paper as one unified asset.

**Decision:** Confirmed consolidation requirement. Manuscript structure and
normalization rules remain proposed pending founder approval.

**Interpretation:**

- The trust-decay draft will supply the mechanism: definitions, trajectory
  divergence, passive decay, asymmetric replenishment and loss,
  authority-class isolation and coupling, thresholds, cold start, declared
  trajectory changes, and known calibration gaps.
- The incident-analysis draft will supply a phase-by-phase worked application of
  that mechanism, followed by the executable replay and local validation design.
- The hybrid two-timescale architecture will connect the theory and example:
  signed composite-state issuance and refresh in the slower loop, per-action
  transport enforcement in the faster loop, and the offline and live rails as
  two executions of the same decision contract.
- The documents will not be concatenated verbatim. Duplicate introductions,
  incompatible notation, unsupported certainty, and repeated conclusions will
  be reconciled into one argument.
- The trust quantity currently named `E_i,c` in the source draft must be mapped
  to the confirmed `Q_i,c` KIL extension vocabulary, with `E(environment)`
  reserved for the KTP environmental envelope to avoid symbol collision.
- The current diagonal weighted standardized-distance formula must not be called
  a full Mahalanobis distance unless covariance is actually represented.
- Incident parameters and counterfactual outcomes are `modeled`; observed event
  facts are cited to the Hugging Face disclosure; only reproduced local lab
  outcomes may be `validated`.
- Strong statements such as “would block” or “credentials are irrelevant” must
  be expressed as conditional model outcomes with explicit sensor, placement,
  freshness, and enforcement assumptions until validated.

**Rationale:** A unified paper can serve simultaneously as the conceptual
argument, protocol-extension rationale, mathematical specification, public case
study, and lab companion only if its notation, evidence classes, and execution
contract are consistent end to end.

**Affected artifacts:**

- `docs/paper/kinetic-infrastructure.md`
- `docs/drafts/kil-trust-decay-model.md` (preserved source input)
- `docs/drafts/ambient-enforcement-vs-huggingface-incident.md` (preserved source
  input)
- `docs/design-drafts/hybrid-two-timescale-architecture.html`
- the future paper design specification, claim-evidence matrix, figures, PDF,
  replay reports, and lab manifests

**Unresolved questions:** Founder approval of the unified paper structure;
fast-loop reducing-only authority; mathematical profile for the first reference
implementation; final paper length and primary audience; and which incident
phases can be faithfully reproduced in the local lab.

**Next gate:** Approve or revise the proposed dual-layer unified-paper structure
before manuscript consolidation begins.

### T-011 — 2026-08-29 — Lab and demo validation phase initiated

**Input:** The founder directed the project to begin the validation phase with
the KIL lab/demo.

**Decision:** Confirmed transition into lab-validation design. This entry does
not claim that any KIL behavior has yet been validated.

**Interpretation:**

- The unified paper structure is sufficiently accepted to proceed with its
  evidence-producing lab workstream.
- Validation will be artifact-driven: each run must bind the scenario version,
  input provenance, model and parameter version, signed-state profile,
  enforcement mode, decision records, environment manifest, and measured
  outcomes.
- The first phase should be deterministic and offline so arithmetic,
  provenance, evidence labels, cutoff claims, and decision reproducibility can
  be tested before a cluster adds timing and platform variability.
- The live phase should then run paired benign and adversarial trajectories in a
  local Kubernetes environment and compare a defined credential/policy
  baseline with the KIL decision contract.
- The fast-loop reducing-only question should be represented as two explicit
  experimental modes: signed-state consumption only, and signed state plus a
  bounded local reducing-only overlay. Experimental comparison does not itself
  approve the overlay as a normative KTP extension behavior.
- A claim may enter the paper as `validated` only when it is reproduced by the
  implementation and its run bundle passes integrity and provenance checks.
- The current host has a suitable bundled Python 3.12 runtime, but no `docker`,
  `kind`, `kubectl`, or `helm` executable was discovered. Live-cluster setup is
  therefore a prerequisite decision; it must not block deterministic replay
  validation.

**Proposed validation sequence:**

1. Specify falsifiable claims, controls, evidence schema, and run-bundle format.
2. Implement the pure deterministic decision kernel with unit and property
   tests, using test-first development.
3. Normalize a source-cited subset of the Hugging Face trace and label all
   synthetic KTP context inputs as `modeled`.
4. Execute paired baseline and KIL replays and generate machine-readable
   decision records plus a paper-ready report.
5. Provision the selected local cluster substrate and reproduce representative
   benign and adversarial trajectories against the same decision interface.
6. Test stale state, missing evidence, false-positive controls, declared
   trajectory changes, signature failure, replay attempts, and reducing-only
   invariants.
7. Promote only reproducible local outcomes to `validated` and bind the paper's
   tables and figures to immutable run identifiers.

**Rationale:** Leading with the deterministic rail creates a falsifiable and
reviewable model before platform details can obscure errors. A later live rail
then validates enforcement behavior and latency without conflating a local
experiment with proof of the historical counterfactual.

**Affected artifacts:**

- the future lab-validation design specification and implementation plan
- `src/kil/`, `schemas/`, `scenarios/hugging-face-july-2026/`, and `tests/`
- `adapters/kubernetes/` and `deploy/kind/` or the selected replacement
- `docs/paper/kinetic-infrastructure.md`
- future replay reports, lab run bundles, figures, and claim-evidence matrix

**Unresolved questions:** Approval of the phased validation sequence; selection
and installation of a local container and Kubernetes substrate; exact baseline
control; first incident cut points; model profile and parameters; and normative
status of the local reducing-only overlay.

**Next gate:** Approve the deterministic-first, paired-replay-then-live-cluster
validation design before the specification and test-first implementation plan
are written.

### T-012 — 2026-08-29 — Deterministic-first validation design approved

**Input:** The founder selected option 1: deterministic replay first, followed
by the live local-cluster rail.

**Decision:** Confirmed validation architecture and sequencing. A formal design
specification has been created for founder review.

**Interpretation:**

- The pure decision kernel, evidence model, normalized historical scenario, and
  replay run bundle stabilize before any Kubernetes adapter is implemented.
- The control, signed-state-only mode, and signed-plus-local-reduction mode are
  evaluated over identical normalized actions.
- The local overlay remains experimental and reducing-only; testing it does not
  grant it final normative KTP status.
- The live rail reuses the replay schemas and decision contract and begins only
  after deterministic and historical-replay acceptance gates pass.
- The lab specification defines falsifiable gates, safety cases, metrics,
  artifact integrity, and the rule for promoting a paper claim to `validated`.

**Rationale:** This order isolates model and provenance errors before introducing
cluster variability and makes the later visual demo an execution of an already
reviewable contract.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-29-kil-lab-validation-design.md`
- the future deterministic-rail implementation plan
- future code, schemas, tests, scenario fixtures, run bundles, paper results,
  and live-cluster design

**Unresolved questions:** Founder review of the specification; concrete signed
state encoding and signature profile after KTP compatibility review; exact
reference parameters; live adapter and cluster substrate; and final normative
status of the local reducing-only overlay.

**Next gate:** Founder reviews the lab-validation design specification. After
approval, produce the test-first deterministic-rail implementation plan.

### T-013 — 2026-08-29 — Correction propagation status clarified

**Input:** The founder asked whether all corrected elements are retroactive to
the project's main data.

**Status:** Clarification confirmed; propagation is incomplete by design and by
current implementation stage.

**Interpretation:**

- The corrected terminology, evidence rules, two-timescale distinction,
  reducing-only invariants, and initial mathematical profile are authoritative
  in the approved-direction lab-validation specification and this lineage.
- The canonical paper currently contains the corrected citation and evidence
  boundary, but it does not yet contain the consolidated trust model, incident
  analysis, or full corrected notation.
- The saved architecture visual still requires revision to distinguish the
  authoritative refresh loop from the fast enforcement loop and to distinguish
  those timescales from the offline and live execution rails.
- The two files under `docs/drafts/` intentionally retain `E_i,c`, the
  “Mahalanobis” wording, and categorical counterfactual language because they
  are byte-preserved source artifacts with pinned checksums. They must not be
  retroactively edited.
- Scenario fixtures, schemas, code, replay data, and lab run bundles do not yet
  exist, so there is no implemented main dataset to migrate. They must be
  created directly from the corrected specification rather than generated from
  the preserved drafts without normalization.

**Rationale:** Provenance requires preserving original source artifacts while
canonical and generated artifacts adopt the latest approved semantics. Calling
all data corrected before that propagation occurs would hide real drift and
weaken the evidence chain.

**Affected artifacts:**

- `docs/paper/kinetic-infrastructure.md` (partial propagation)
- `docs/design-drafts/hybrid-two-timescale-architecture.html` (revision needed)
- `docs/drafts/kil-trust-decay-model.md` and
  `docs/drafts/ambient-enforcement-vs-huggingface-incident.md` (intentionally
  preserved)
- future normalized scenario, schemas, implementation, run bundles, figures,
  and PDF (must use corrected semantics from inception)

**Unresolved questions:** Whether to add an automated semantic-invariant test
covering canonical paper, architecture, schemas, code, and generated artifacts;
and when to revise the architecture visual relative to deterministic-rail
implementation planning.

**Next gate:** Founder decides whether to authorize a correction-propagation
pass across all mutable canonical artifacts before the implementation plan is
written.

### T-014 — 2026-08-29 — Canonical correction propagation completed

**Input:** The founder agreed with the propagation recommendation and directed
the project to execute it.

**Decision:** Completed across all current mutable canonical paper and
architecture artifacts. Preserved source drafts remain unchanged.

**Implementation:**

- The official manuscript now unifies the ambient-enforcement thesis, KTP
  extension boundary, corrected hybrid two-timescale architecture, formal
  trust-decay profile, Hugging Face incident counterfactual, validation lab,
  safety constraints, limitations, and authoritative references.
- Canonical notation uses `Q_i,c` for the signed composite enforcement state and
  reserves `E(environment)` for the KTP environmental envelope.
- The first mathematical profile is identified as a weighted diagonal
  standardized distance, not a full Mahalanobis distance.
- The manuscript separates observed incident facts, modeled context and
  counterfactual decisions, and locally validated results.
- The architecture visual now distinguishes the authoritative signed-state loop
  from the fast enforcement loop and labels offline replay and live validation
  as execution rails rather than timescales.
- The visual exposes the experimental local reducing-only overlay and states
  that the fast loop cannot replenish authority.
- Automated semantic-invariant tests now reject reintroduction of the old
  notation, overstated distance name, old charge label, or rail/timescale
  conflation in the canonical paper and visual.

**Rationale:** Corrections are now executable repository invariants rather than
editorial guidance. The main paper, visual, approved validation specification,
and future generated artifacts share one vocabulary and evidence boundary while
the provenance record remains intact.

**Affected artifacts:**

- `docs/paper/kinetic-infrastructure.md`
- `docs/design-drafts/hybrid-two-timescale-architecture.html`
- `docs/superpowers/plans/2026-08-29-canonical-correction-propagation.md`
- `tests/test_canonical_semantics.py`
- `tests/test_consultation_checkpoint.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Preserved artifacts:**

- `docs/drafts/kil-trust-decay-model.md`
- `docs/drafts/ambient-enforcement-vs-huggingface-incident.md`
- all checksum-pinned transition and source-material records

**Unresolved questions:** Final signed-state encoding and KTP compatibility
mapping; reference parameter profile; live cluster substrate and adapter;
empirical status of the local reducing-only overlay; and author, design, and
publication metadata for the final PDF.

**Next gate:** Produce the detailed test-first implementation plan for the V1
deterministic decision kernel and V2 historical replay.

### T-015 — 2026-08-29 — V1 and V2 implementation plans completed

**Input:** The founder directed the project to advance to the next gate after
canonical correction propagation.

**Decision:** The approved validation design has been decomposed into two
independently executable, test-first implementation plans: V1 deterministic
kernel and V2 historical replay. No enforcement behavior has been implemented
or labeled validated at this gate.

**V1 plan decisions:**

- Use the bundled Python 3.12 runtime and parameterize the Makefile so the
  current host's Python 3.9 cannot silently execute a Python 3.11+ project.
- Separate evidence typing, deterministic `Decimal` arithmetic, immutable
  domain records, decision evaluation, and canonical serialization.
- Consume authentication as an algorithm-neutral state property; concrete
  signature encoding remains gated on KTP compatibility review.
- Implement both signed-state-only and signed-plus-local-reduction modes.
- Make failure disposition explicit: fail closed by default, fail constrained
  only when configured, and never let stale evidence mask a veto or envelope
  violation.
- Test identity, authority-class, envelope, veto, authenticity, validity,
  history, passive decay, coupling, monotonic reduction, and the prohibition on
  action self-authorization.

**V2 plan decisions:**

- Normalize one versioned, source-cited event stream and evaluate it with the
  credential-policy control and both KIL modes.
- Represent observed summaries, control assumptions, synthetic composite state,
  and local evidence as separately labeled evidence values with rationales.
- Cover eight stable incident cut points while preserving dependency edges.
- Compute independent decisions and mode-specific reachability so downstream
  effects are not double counted.
- Emit a deterministic run bundle containing manifest, scenario, states,
  decisions, metrics, summary, and SHA-256 integrity data.
- Keep every historical counterfactual output labeled modeled, even when the
  replay implementation itself is locally reproduced.

**Self-review findings resolved:**

- immutable-veto precedence over stale local evidence;
- missing fail-constrained behavior;
- incomplete independent-gate and coupling coverage;
- unlabeled credential-policy and composite-state assumptions;
- missing downstream reachability accounting;
- incomplete run-bundle contents; and
- Python runtime mismatch on the current host.

**Affected artifacts:**

- `docs/superpowers/plans/2026-08-29-v1-deterministic-kernel.md`
- `docs/superpowers/plans/2026-08-29-v2-historical-replay.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Execution mode for V1; concrete KTP-compatible signed
state encoding; review of phase-level source-location labels during V2 fixture
construction; and the live cluster substrate after V1 and V2 pass.

**Next gate:** Execute V1 using the approved test-first plan. V2 begins only
after the V1 exit criteria pass and its decision contract is stable.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-016 — 2026-08-29 — V1 Task 0 runtime parameterization completed

**Input:** The V1 implementation gate required pinning the supported local
Python runtime through the Makefile, validating with bundled Python 3.12, and
recording the progress checkpoint.

**Interpretation:** This is a build-configuration and evidence-ledger change;
it does not alter KIL decision behavior. The bundled runtime reports Python
3.12.13, above the required Python 3.11 floor.

**Decision:** Confirmed Task 0 implementation complete: Make targets now use
the overridable `PYTHON` variable, validation passed with 11 existing tests,
and spec and quality review remain pending.

**Rationale:** Parameterizing the interpreter prevents the host Python 3.9
from silently executing a Python 3.11+ project while preserving the existing
test, project-metadata, and git-diff checks.

**Affected artifacts:**

- `Makefile`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** None for Task 0; spec and quality review of the
runtime change remain outstanding.

**Next gate:** Complete independent spec and quality review, then proceed to
V1 Task 1 evidence-contract implementation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-017 — 2026-08-29 — Python floor enforcement review fix

**Input:** Quality review found that `PYTHON ?= python3` still allowed plain
`make validate` to run silently under the host Python 3.9.6.

**Interpretation:** Runtime parameterization needs an executable floor check;
otherwise the supported bundled interpreter is only opt-in and unsupported
hosts can run the suite.

**Decision:** Confirmed the Makefile now provides a `check-python` target that
rejects versions below Python 3.11 with a clear message, and `test` depends on
that target so both `make test` and `make validate` enforce the floor.

**Rationale:** The gate fails before test discovery on unsupported hosts while
retaining the overridable `PYTHON` variable for the bundled Python 3.12 path.

**Affected artifacts:**

- `Makefile`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Quality re-review remains pending; no Task 0
behavioral questions remain after the explicit floor check.

**Next gate:** Re-run quality review, then proceed to V1 Task 1 evidence-
contract implementation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-018 — 2026-08-29 — V1 evidence classification contract implemented

**Input:** V1 Task 1 required an explicit, immutable evidence contract that
distinguishes observed facts, modeled assumptions, and locally reproduced
validation results before later kernel and replay work can consume them.

**Interpretation:** Evidence class is provenance metadata, not a trust score or
authorization grant. Each class therefore requires its own explicit support:
observed values cite a source, modeled values state a rationale, and validated
values identify the reproducing run.

**Decision:** Confirmed implementation of the algorithm-neutral
`EvidenceClass` and generic frozen, slotted `LabeledValue` contract. Invalid
construction is rejected when the evidence class lacks its required metadata.
The four focused contract tests pass, and the complete validation suite passes
15 tests. Independent spec and quality reviews remain pending.

**Rationale:** Encoding evidentiary boundaries in immutable domain values keeps
later calculations and reports from silently promoting synthetic context or
historical counterfactuals into observed or validated claims.

**Affected artifacts:**

- `src/kil/evidence.py`
- `tests/test_evidence.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The requested direct focused-test invocation does not
set the repository's `PYTHONPATH=src`, so it cannot import the local `kil`
package in an uninstalled checkout. The same focused suite passes 4 tests with
the repository import path used by the Makefile. Spec and quality review remain
outstanding; no KTP-compatible signature encoding is decided by this task.

**Next gate:** Complete independent spec and quality review of Task 1, then
proceed to V1 Task 2 deterministic trust-decay arithmetic.

This checkpoint is software-development evidence only. It does not validate
cryptographic enforcement, historical prevention claims, or live KIL behavior.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-019 — 2026-08-29 — Evidence invariant quality-review hardening

**Input:** Independent quality review found that runtime callers could bypass
the Task 1 contract by supplying a raw string or arbitrary object as the
evidence class, or by supplying whitespace-only or non-string required
metadata.

**Interpretation:** Python annotations do not enforce runtime boundaries. A
provenance contract must reject untyped class values rather than normalize
them, and required metadata must be a string containing non-whitespace text.

**Decision:** Confirmed implementation of strict runtime checks for an actual
`EvidenceClass` instance and class-specific nonblank string metadata. New
regression tests first reproduced eight bypass failures, then passed after the
fix. The focused suite now passes 6 tests and the full suite passes 17 tests.
Spec review is approved; quality re-review remains pending.

**Rationale:** Invalid provenance labels must fail at construction so later KIL
components cannot mistake malformed or unclassified inputs for observed,
modeled, or validated evidence.

**Affected artifacts:**

- `src/kil/evidence.py`
- `tests/test_evidence.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent quality re-review remains outstanding.
This change does not select a cryptographic representation or alter KTP
protocol semantics.

**Next gate:** Obtain quality re-review approval for Task 1, then proceed to V1
Task 2 deterministic trust-decay arithmetic.

This is software-development evidence only, not validated cryptographic,
historical, cluster, or live enforcement behavior.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-020 — 2026-08-29 — V1 deterministic trust-decay arithmetic implemented

**Input:** V1 Task 2 required a dependency-free, deterministic `Decimal`
implementation of weighted diagonal distance, logistic squashing, passive
decay, superlinear divergence loss, and reducing-only local charge adjustment.

**Interpretation:** These functions are arithmetic primitives for the V1
reference kernel. They encode the approved trust-decay model mechanics but do
not independently establish a KTP authority grant, incident-prevention claim,
cryptographic authenticity result, or live enforcement outcome.

**Decision status:** Proposed implementation complete; independent spec and
quality review are pending. The focused test-first run first failed with the
expected missing-module error, then passed six specified behavior tests. The
full repository validation passed 23 tests with no failures.

**Rationale:** Fixed-precision local `Decimal` contexts, sorted feature-key
iteration, explicit input domains, and reducing-only clamping make the
arithmetic reproducible and prevent local evidence from increasing the
decayed composite charge. The superlinear loss remains zero inside its normal
band and rises cubically in the specified reference case.

**Affected artifacts:**

- `src/kil/decay.py`
- `tests/test_decay.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent spec and quality review remain pending.
Task 2 does not calibrate feature means, scales, weights, loss rates, or decay
rates from local-cluster telemetry; those values remain future experimental
inputs governed by the evidence contract.

**Next gate:** Complete independent spec and quality review for Task 2, then
proceed to V1 Task 3 immutable domain records only if both reviews approve.

This checkpoint is software-development evidence only. It does not validate
historical counterfactuals, cryptographic enforcement, cluster behavior, or
live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-021 — 2026-08-29 — Decay exponent aligned with domain contract

**Input:** Independent spec review found that `superlinear_loss` declared its
exponent as `Decimal`, while the approved V1 plan and downstream
`ReductionProfile` contract require an integer exponent greater than one.

**Interpretation:** The exponent representation is part of the stable V1
decision contract, not a calibration preference. Permitting decimal or other
non-integer values would create an avoidable mismatch between the arithmetic
primitive and the immutable domain record that will supply it.

**Decision status:** Confirmed correction implemented; spec re-review and
quality review remain pending. A regression test first demonstrated that a
`Decimal("3")` exponent was silently accepted, then passed after the function
was narrowed to an integer-only API with runtime validation. The focused suite
passes seven tests and the full repository validation passes 24 tests.

**Rationale:** Requiring a true integer greater than one keeps the arithmetic
API aligned with the approved downstream profile and prevents callers from
silently introducing fractional-power semantics that V1 does not specify.

**Affected artifacts:**

- `src/kil/decay.py`
- `tests/test_decay.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent spec re-review and quality review remain
pending. Calibration of the integer exponent and other profile values remains
future experimental work subject to the evidence contract.

**Next gate:** Obtain spec re-review and quality approval for Task 2 before
proceeding to V1 Task 3 immutable domain records.

This correction is software-development evidence only. It does not validate
historical counterfactuals, cryptographic enforcement, cluster behavior, or
live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-022 — 2026-08-29 — Decay arithmetic made context independent

**Input:** Independent quality review found two Task 2 determinism gaps: public
arithmetic inherited parts of the caller's decimal context, and non-`Decimal`
or non-finite operands could be accepted or escape as `decimal`/type
exceptions rather than deterministic `ValueError` results.

**Interpretation:** A deterministic reference kernel must own its complete
numeric execution context and validate every operand before comparisons or
arithmetic. This applies equally to scalar parameters, mapped feature values,
and the reducing-only local charge operation.

**Decision status:** Confirmed quality findings fixed; quality re-review
remains pending and spec review is approved. Test-first regressions reproduced
four caller-context-dependent outputs plus seven failures and six errors from
invalid operand handling. The corrected focused suite passes ten tests, and
the full repository validation passes 27 tests.

**Rationale:** Every public arithmetic function now executes inside a local
copy of one fixed 28-digit, half-even decimal context with explicit exponent
bounds and traps. All accepted numeric operands must be finite `Decimal`
instances before domain validation or arithmetic, preventing NaN, infinity,
float, string, and other invalid values from changing behavior according to
ambient caller state.

**Affected artifacts:**

- `src/kil/decay.py`
- `tests/test_decay.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent quality re-review remains pending.
Telemetry-driven calibration of decay and loss parameters remains future
experimental work governed by the evidence contract.

**Next gate:** Obtain quality re-review approval for Task 2 before proceeding
to V1 Task 3 immutable domain records.

This correction is software-development evidence only. It does not validate
historical counterfactuals, cryptographic enforcement, cluster behavior, or
live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-023 — 2026-08-29 — Exact reducing-only charge clamp enforced

**Input:** Final Task 2 quality review supplied a precision-boundary case where
fixed-context subtraction rounded the local effective charge above the exact
input charge despite positive loss, violating the reducing-only invariant.

**Interpretation:** Context independence alone does not guarantee monotonic
reduction at a precision boundary. The invariant is defined against the exact
incoming decayed charge, so the final result must be bounded by that original
value in addition to the configured maximum and zero floor.

**Decision status:** Confirmed finding fixed; quality re-review remains
pending and spec review is approved. The exact reviewer regression first
failed with a result of `1.000000000000000000000000000` for an incoming charge
of `0.99999999999999999999999999996`, then passed after the final clamp was
strengthened. The focused suite passes 11 tests and the full repository suite
passes 28 tests.

**Rationale:** Clamping the rounded subtraction result against the original
finite `Decimal` charge makes the reducing-only guarantee explicit even when
28-digit half-even rounding crosses above the exact operand.

**Affected artifacts:**

- `src/kil/decay.py`
- `tests/test_decay.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent quality re-review remains pending.
Calibration and live enforcement behavior remain outside this software
arithmetic checkpoint.

**Next gate:** Obtain quality re-review approval for Task 2 before proceeding
to V1 Task 3 immutable domain records.

This correction is software-development evidence only. It does not validate
historical counterfactuals, cryptographic enforcement, cluster behavior, or
live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-024 — 2026-08-29 — Immutable V1 decision-domain records implemented

**Input:** The approved V1 deterministic-kernel plan called for immutable,
slotted domain records representing action requests, signed composite KTP
enforcement state, optional local reducing evidence, reduction profiles, and
decision outputs. The protocol boundary continues to treat composite-state
authenticity as an algorithm-neutral Boolean input; concrete signature encoding
is outside V1.

**Interpretation:** The domain layer must reject runtime type bypasses and
non-finite authority values before the decision engine performs any arithmetic
or gate evaluation. It must preserve the reducing-only architecture without
embedding later decision-engine policy into record construction.

**Decision status:** Confirmed V1 Task 3 implementation complete; independent
specification and quality reviews remain pending. Test-first execution recorded
the expected missing-module failure. The implemented suite now passes 11
focused domain tests and all 39 repository tests under bundled Python 3.12;
preserved-source checksums and `git diff --check` also pass.

**Rationale:** Frozen, slotted dataclasses provide a small immutable boundary.
Exact integer and Boolean checks prevent Python's Boolean-as-integer behavior
from bypassing field contracts; finite `Decimal` checks prevent NaN and
infinity from entering authority calculations. Stable string enums preserve
the public decision vocabulary. The records validate construction invariants
but intentionally do not encode cryptographic formats or pre-decide engine
outcomes.

**Affected artifacts:**

- `src/kil/domain.py`
- `tests/test_domain.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent spec and quality review are pending.
Concrete KTP signature encoding and authenticated composite-state transport
remain a later compatibility gate, not part of this software-domain checkpoint.

**Next gate:** Obtain Task 3 specification compliance and quality approval
before implementing the deterministic decision engine in V1 Task 4.

This checkpoint is software-development evidence only. It does not validate
historical counterfactuals, cryptographic enforcement, cluster behavior, or
live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-025 — 2026-08-29 — Decision-record authority and reason invariants hardened

**Input:** Independent Task 3 quality review identified that a caller could
construct a decision record whose decayed or locally effective charge exceeded
its upstream value, or pair outcomes with contradictory or missing reason
codes.

**Interpretation:** A reducing-only KIL decision record must make the authority
chain structurally explicit: effective charge cannot exceed decayed charge,
and decayed charge cannot exceed the signed composite-state charge. Outcome and
reason fields are one decision assertion and therefore cannot contradict each
other. Planned stale-local handling still requires `INDETERMINATE` to accept a
relevant non-permitted reason without imposing additional policy here.

**Decision status:** Confirmed quality findings fixed; specification review is
approved and quality re-review remains pending. Test-first regressions exposed
two increasing-authority paths and five inconsistent outcome/reason paths. The
corrected suite passes 14 focused domain tests and all 42 repository tests under
bundled Python 3.12; preserved-source checksums and `git diff --check` pass.

**Rationale:** `DecisionRecord` now enforces
`0 <= effective_charge <= decayed_charge <= signed_charge`. A permit has exactly
the permitted reason; non-permit outcomes cannot claim permission; deny and
constrain outcomes require an actionable reason. `INDETERMINATE` remains able
to carry `LOCAL_EVIDENCE_STALE`, preserving the approved Task 4 contract.

**Affected artifacts:**

- `src/kil/domain.py`
- `tests/test_domain.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent quality re-review remains pending.
Concrete KTP signature encoding and live enforcement remain outside this V1
domain-model checkpoint.

**Next gate:** Obtain Task 3 quality approval before implementing the
deterministic decision engine in V1 Task 4.

This correction is software-development evidence only. It does not validate
historical counterfactuals, cryptographic enforcement, cluster behavior, or
live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-026 — 2026-08-29 — Deterministic V1 decision engine implemented

**Input:** The approved V1 plan called for a deterministic engine that evaluates
an action against a signed, short-lived composite KTP enforcement state, applies
independent binding, veto, environmental-envelope, authenticity, validity,
charge, and history gates, and optionally consumes a strictly reducing local
overlay. Missing or stale local evidence must fail closed unless constrained
failure is explicitly selected.

**Interpretation:** Authority exists before the current action and cannot be
created or refreshed by it. The slow-loop signed charge is passively decayed at
the action timestamp. The fast loop may only subtract divergence and coupled
loss; signed-state-only mode does not consume local evidence. An immutable veto
or any other decisive reason yields denial even when local-evidence failure was
configured to constrain.

**Decision status:** Confirmed Task 4 implementation ready for independent
specification and quality review. The expected missing-module RED was recorded.
A second test-first runtime-contract checkpoint exposed two failures and three
errors before deterministic input validation was added. Fourteen focused engine
tests and all 56 repository tests now pass under bundled Python 3.12; preserved
source checksums and `git diff --check` also pass.

**Rationale:** The engine preserves the reducing-only authority chain
`effective_charge <= decayed_charge <= signed_charge`, treats expiration as
inclusive at `timestamp >= expires_at`, distinguishes explicit constrained
degradation from the default closed disposition, and emits exactly `PERMITTED`
only when no actionable reason exists. Runtime enum and record inputs are
validated before evaluation, while missing local components follow the explicit
stale-evidence path rather than creating authority.

**Affected artifacts:**

- `src/kil/engine.py`
- `tests/test_engine.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent Task 4 specification and quality reviews
remain pending. Concrete cryptographic signature encoding, historical incident
replay, cluster enforcement, and telemetry-calibrated thresholds remain outside
this software decision-engine checkpoint.

**Next gate:** Obtain independent Task 4 specification compliance and code
quality approval before beginning V1 Task 5 canonical decision serialization
and invariant sweeps.

This checkpoint is software-development evidence only. It does not validate
historical counterfactuals, cryptographic enforcement, cluster behavior, or live
KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-027 — 2026-08-29 — Unrepresentable engine inputs fail closed

**Input:** Independent Task 4 quality review found that unbounded Python integer
timestamps could reach elapsed-time conversion and that an accepted finite but
extreme decay rate could raise a trapped `Decimal` arithmetic exception out of
the decision boundary instead of producing an enforcement decision.

**Interpretation:** KIL decision inputs require an explicit transport-safe time
representation, and a numeric failure inside authority reduction cannot become
an implicit fail-open or an unclassified engine crash. This is a domain and
decision-boundary correction, not parameter calibration or cryptographic
validation.

**Decision status:** Confirmed quality fix implemented; specification review is
approved and quality re-review remains pending. Test-first regressions exposed
seven timestamp/enum failures and two escaping Decimal overflow errors. The
corrected domain-and-engine suite passes 32 tests, and all 60 repository tests
pass under bundled Python 3.12; preserved-source checksums and
`git diff --check` also pass.

**Rationale:** Action and composite-state timestamps are now restricted to
signed 64-bit seconds, including exact boundary acceptance and Boolean
rejection. Only the `DivisionByZero`, `InvalidOperation`, and `Overflow`
conditions trapped by the deterministic Decimal kernel are translated into an
`ARITHMETIC_FAILURE` denial. The fallback record sets decayed and effective
charge to zero, preserving the reducing-only authority invariant. Existing
veto and gate reasons remain ordered before the arithmetic reason and still
force denial.

**Affected artifacts:**

- `src/kil/domain.py`
- `src/kil/engine.py`
- `tests/test_domain.py`
- `tests/test_engine.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent quality re-review remains pending.
Concrete signed-state encoding, live transport integration, historical replay,
and telemetry-calibrated parameter bounds remain later validation gates.

**Next gate:** Obtain Task 4 quality approval before beginning V1 Task 5
canonical serialization and invariant sweeps.

This correction is software-development evidence only. It does not validate
historical counterfactuals, cryptographic enforcement, cluster behavior, or
live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-028 — 2026-08-29 — Canonical V1 decision serialization implemented

**Input:** The approved V1 plan called for deterministic canonical JSON and a
SHA-256 digest for KIL decision artifacts, invariant sweeps proving that the
fast local loop cannot increase signed-state authority, and a development
version marking completion of the deterministic software kernel.

**Interpretation:** Canonicalization is a software evidence and interoperability
boundary, not cryptographic verification. Dataclass records, enum values,
finite decimal values, and ordered sequences require one stable representation.
Ambiguous non-string dictionary keys, unordered sets, binary values, floats,
non-finite decimals, and other unsupported runtime objects must be rejected
rather than silently coerced. The local overlay remains strictly reducing over
the signed-state result throughout the sampled divergence domain.

**Decision status:** Confirmed Task 5 implementation ready for independent
specification and quality review. Test-first execution recorded the expected
missing-module RED and a separate package-version RED. The focused V1 suite
passes 59 tests and full repository validation passes 69 tests under bundled
Python 3.12; preserved-source checksums and `git diff --check` pass.

**Rationale:** Canonical JSON now recursively normalizes dataclass records,
enums, finite `Decimal` values, dictionaries with string-only keys, lists, and
tuples before stable JSON encoding. The digest is SHA-256 over the UTF-8
canonical representation. Tests cover dictionary insertion-order stability,
decision-record serialization, nested sequences, caller Decimal-context
independence, unsupported and non-finite inputs, and reducing-only authority
invariants across divergence sweeps. Package version `0.1.0-dev1` identifies
this development gate without implying production or cryptographic readiness.

**Affected artifacts:**

- `src/kil/canonical.py`
- `src/kil/__init__.py`
- `tests/test_kernel_invariants.py`
- `tests/test_package.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent Task 5 specification and quality reviews
remain pending. Concrete KTP signature encoding and verification, live
infrastructure adapters, historical replay, cluster enforcement, and
telemetry-calibrated thresholds remain outside this deterministic V1 software
gate.

**Next gate:** Obtain independent Task 5 specification compliance and code
quality approval, then perform the whole-V1 completion review.

This checkpoint is software-development evidence only. It does not validate
historical counterfactuals, cryptographic enforcement, cluster behavior, or
live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-029 — 2026-08-29 — Canonical encoding hardened at the trust boundary

**Input:** Independent Task 5 quality review identified value-collision,
Unicode, and resource-bounding weaknesses in the initial canonicalizer. Decimal
formatting preserved insignificant zeros, collided with ordinary JSON strings,
and could expand extreme exponents. Lone surrogates could reach UTF-8 digest
encoding, while cycles or deeply nested and oversized structures could escape
as runtime or resource failures.

**Interpretation:** A canonical decision encoding is part of the deterministic
trust boundary. Equal finite decimal values require one typed representation,
distinct from user strings and mappings. All text must be valid Unicode scalar
data before hashing, and every recursive input must terminate within explicit,
auditable depth, item, and output bounds. These are serialization invariants,
not a concrete KTP signature format.

**Decision status:** Confirmed quality fixes implemented; Task 5 specification
review is approved and quality re-review remains pending. The quality tests
first failed on the absent limit constants and then exposed nine behavioral
failures plus one raw recursion error. The corrected focused V1 suite passes 66
tests and full repository validation passes 76 tests under bundled Python 3.12;
preserved-source checksums and `git diff --check` pass.

**Rationale:** Finite decimals now use a reserved, typed coefficient/exponent
encoding derived directly from `Decimal.as_tuple()`. Trailing coefficient zeros
are removed while adjusting the exponent, both signs of zero collapse to one
value, and large positive exponents remain compact. The reserved type-tag key
cannot be supplied by an ordinary mapping. Strings and keys are UTF-8 validated
before JSON or digest encoding. Dataclasses are traversed field by field rather
than through an unbounded deep copy, with active-path cycle detection and fixed
depth, item-count, integer-size, and UTF-8 output limits. SHA-256 remains over
the resulting UTF-8 canonical JSON.

**Affected artifacts:**

- `src/kil/canonical.py`
- `tests/test_kernel_invariants.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent quality re-review and the whole-V1 review
remain pending. Standardizing the reserved decimal representation inside a
future KTP wire schema, concrete signature verification, live adapters,
historical replay, and calibrated operational limits remain later gates.

**Next gate:** Obtain Task 5 quality approval, then perform the whole-V1
completion review before any merge or historical replay claim.

This checkpoint is software-development evidence only. It does not validate
historical counterfactuals, cryptographic enforcement, cluster behavior, or
live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-030 — 2026-08-29 — Passive decay clamped to signed authority

**Input:** Whole-V1 review identified a cross-module precision defect using an
exact signed charge of `0.99999999999999999999999999996` with zero decay rate
and zero elapsed time. Fixed-context multiplication returned
`1.000000000000000000000000000`, after which the decision engine correctly
rejected the record because decayed authority exceeded signed authority.

**Interpretation:** The decision-record invariant was functioning correctly;
the defect originated in passive decay, where fixed-precision rounding could
increase the exact incoming charge. Passive decay must therefore bound its
computed value by the original signed charge after fixed-context arithmetic.

**Decision status:** Confirmed fix implemented; whole-V1 re-review remains
pending. Test-first regressions reproduced one focused decay failure and one
engine-level record-construction error. After the minimal arithmetic fix, the
combined decay and engine suites pass 29 tests and full repository validation
passes 78 tests.

**Rationale:** The fixed context still governs exponential decay computation,
but the returned value is clamped outside that arithmetic context against the
exact original charge and zero. This preserves nonnegative behavior, caller-
context independence, and the authority ordering `effective <= decayed <=
signed` without weakening the decision-record validation boundary.

**Affected artifacts:**

- `src/kil/decay.py`
- `tests/test_decay.py`
- `tests/test_engine.py`
- `docs/lab/V1-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent whole-V1 re-review of the Task 2 and
Task 4 gates remains pending. Concrete KTP signature verification, calibrated
telemetry, historical replay, and live enforcement remain later gates.

**Next gate:** Obtain whole-V1 re-review approval for the corrected passive-
decay and engine authority chain before merge or V2 historical replay work.

This correction is software-development evidence only. It does not validate
historical counterfactuals, cryptographic enforcement, cluster behavior, or
live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-031 — 2026-08-29 — V1 pull-request publication selected; authentication pending

**Input:** The user selected integration option 2: push
`feature/v1-deterministic-kernel` and create a pull request against `main`, then
asked to retry after the first GitHub authentication check failed.

**Interpretation:** V1 is approved for publication as a reviewable feature
branch, while merge remains a later, explicit decision. The implementation
worktree must remain available for pull-request feedback.

**Decision status:** Confirmed publication path; externally blocked before
push. The local branch remains complete and clean, but GitHub CLI reports the
saved token for `gatekeeper454` is invalid. A replacement device-authentication
flow was initiated and is waiting for the user to sign in to GitHub and approve
the one-time device authorization. No branch push or pull request has yet been
created in this checkpoint.

**Rationale:** Publishing through a pull request preserves the isolated V1
commit history, exposes the deterministic-kernel evidence for review, and keeps
merge authority separate from implementation completion. Authentication cannot
be supplied or inferred by the implementation process.

**Affected artifacts:**

- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Local branch `feature/v1-deterministic-kernel`
- Planned remote pull request targeting `main`

**Unresolved questions:** Completion of GitHub device authorization, successful
remote push, and creation/readback of the pull request remain pending. Concrete
KTP signature verification, calibrated telemetry, historical replay, and live
enforcement remain outside V1.

**Next gate:** After the user completes GitHub sign-in and device authorization,
verify the authenticated account, commit this publication checkpoint, push the
feature branch, create the pull request, and read back its URL and state.

This checkpoint records repository-publication status only. It does not add or
validate historical counterfactual, cryptographic, cluster, or live-enforcement
evidence.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-032 — 2026-08-29 — V1 pull request published for review

**Input:** GitHub device authorization completed for `gatekeeper454` after the
user selected pull-request integration and asked to retry authentication.

**Interpretation:** The approved V1 deterministic-kernel branch can now enter
remote peer review without merging into `main`. The isolated implementation
worktree remains the active location for any pull-request feedback.

**Decision status:** Confirmed publication completed. Branch
`feature/v1-deterministic-kernel` was pushed to `origin`, and GitHub pull request
[#1](https://github.com/gatekeeper454/KIL/pull/1) was created against `main`.
Merge has not been authorized or performed.

**Rationale:** A pull request exposes the complete V1 implementation, tests,
review corrections, evidence boundaries, and specialist lineage as one
auditable change set while preserving a separate merge gate.

**Affected artifacts:**

- Remote branch `origin/feature/v1-deterministic-kernel`
- GitHub pull request [gatekeeper454/KIL#1](https://github.com/gatekeeper454/KIL/pull/1)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Pull-request review and merge disposition remain
pending. Concrete KTP signature verification, calibrated telemetry, historical
replay, cluster integration, and live enforcement remain later validation
gates.

**Next gate:** Review pull request #1 and either address requested changes or
explicitly authorize merge. Preserve the feature worktree until that gate is
resolved.

This publication establishes a reviewable software-development artifact only.
It does not validate historical counterfactuals, cryptographic enforcement,
cluster behavior, or live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-033 — 2026-08-29 — V1 merge confirmed; merged-tree citation scan corrected

**Input:** The user advanced to the next gate after pull request #1 was
published. GitHub reported that `gatekeeper454` had merged the pull request into
`main` and that both CI bootstrap checks completed successfully.

**Interpretation:** Remote merge completion moved V1 from publication review to
post-merge verification. Validation must run from the actual primary checkout,
where managed implementation worktrees exist beneath `.worktrees/`, rather
than relying only on the isolated feature-worktree environment.

**Decision status:** Merge confirmed at `ee2f5b8`; local `main` was
fast-forwarded to that commit. Post-merge validation reproduced one failure in
the citation-policy test because its recursive filesystem scan entered the
managed `.worktrees/` tree and treated byte-preserved draft copies as new KIL
documents. A test-first correction on branch `fix/citation-scan-worktrees`
first failed when the scanner classified the worktree path as a target, then
passed after the scanner excluded `.git` and `.worktrees` repository-internal
paths. The focused citation suite passes three tests and the full isolated suite
passes 79 tests; all five preserved-source checksums and `git diff --check`
pass. Follow-up remote review remains pending.

**Rationale:** The citation rule applies to KIL-authored documents in the
checkout, not duplicate checkouts and Git metadata stored inside it. Restricting
only these repository-internal path components preserves coverage of ordinary
authored Markdown while making validation independent of whether managed
worktrees are present.

**Affected artifacts:**

- `tests/test_document_citation.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Local branch and worktree `fix/citation-scan-worktrees`
- Local `main` synchronized to merge commit `ee2f5b8`

**Unresolved questions:** The correction still requires commit, remote push,
follow-up pull-request CI, merge, and validation from the primary checkout.
Cleanup of the two managed implementation worktrees and their local branches is
deferred until the correction is merged and verified.

**Next gate:** Publish the narrowly scoped citation-scan correction for review,
verify its CI, merge only after explicit or external approval, re-run validation
from synchronized `main`, and then perform provenance-safe worktree cleanup.

This checkpoint validates repository test-boundary behavior only. It does not
add historical counterfactual, cryptographic, cluster, or live-enforcement
evidence.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-034 — 2026-08-29 — Citation-scan correction published and CI-approved

**Input:** The test-first merged-tree correction and lineage checkpoint from
T-033 were committed on `fix/citation-scan-worktrees` and published for remote
review.

**Interpretation:** This is a narrowly scoped repository-validation correction,
separate from the V1 enforcement semantics already merged through pull request
#1. Passing remote CI is required before requesting a second merge decision.

**Decision status:** Confirmed publication and CI success. Pull request
[#2](https://github.com/gatekeeper454/KIL/pull/2) is open from
`fix/citation-scan-worktrees` into `main`, GitHub reports it clean and mergeable,
and both bootstrap CI checks passed. Merge remains pending explicit or external
authorization.

**Rationale:** A second pull request keeps the post-merge test-harness correction
auditable and prevents an unreviewed direct write to remote `main`. The change
does not modify KIL trust arithmetic, decision semantics, canonical encoding, or
evidence classification.

**Affected artifacts:**

- GitHub pull request [gatekeeper454/KIL#2](https://github.com/gatekeeper454/KIL/pull/2)
- Remote branch `origin/fix/citation-scan-worktrees`
- `tests/test_document_citation.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Merge authorization, post-merge validation from the
primary checkout, and provenance-safe cleanup of the V1 and citation-fix
worktrees remain pending.

**Next gate:** Obtain the merge decision for pull request #2. If merged,
synchronize local `main`, run the full suite with managed worktrees still
present to prove the original failure is resolved, then clean up merged local
worktrees and branches.

This checkpoint validates publication and repository CI only. It does not add
historical counterfactual, cryptographic, cluster, or live-enforcement evidence.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-035 — 2026-08-29 — V1 closed and V2 historical replay opened

**Input:** The user reported pull request #2 complete and directed execution to
the next gate.

**Interpretation:** The next approved gate is V2 historical replay: normalize
the source-cited Hugging Face sequence and execute one common event stream under
the modeled credential-policy baseline and both V1 KIL enforcement modes. This
does not promote counterfactual output to validated evidence.

**Decision status:** Confirmed transition. Pull request #2 was merged by
`gatekeeper454` at `261474c`; local `main` was fast-forwarded and passed 79
tests from the primary checkout while both managed worktrees were still
present. All five preserved-source hashes and `git diff --check` passed. The two
clean, fully merged V1 worktrees and their local branches were then removed.
V2 is open on isolated branch `feature/v2-historical-replay` from `261474c`.

**Rationale:** Verifying before cleanup proves the citation-scanner correction
against the exact environment that caused the post-merge failure. V2 begins
only after V1 kernel semantics and repository validation are closed. Plan review
also makes three implementation constraints explicit: no permissive JSON type
coercion, modeled provenance must be structural, and replay bundle failures and
resource limits must be deterministic.

**Affected artifacts:**

- Local and remote `main` at merge commit `261474c`
- Removed local worktrees `v1-deterministic-kernel` and `citation-scan-fix`
- New worktree and branch `feature/v2-historical-replay`
- `docs/lab/V2-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- `docs/superpowers/plans/2026-08-29-v2-historical-replay.md`

**Unresolved questions:** V2 scenario-loader conformance, paired replay,
deterministic bundles, eight-phase incident normalization, CLI execution, and
whole-V2 review remain pending. The public incident source does not disclose raw
KTP telemetry or policy-engine traces, so replay outputs must remain modeled.

**Next gate:** Implement Task 1 with test-first schema and loader validation,
including exact JSON runtime types, unknown-field rejection, dependency order,
and observed-versus-modeled provenance invariants.

This transition validates V1 software and repository behavior only. It does not
validate historical prevention, concrete KTP cryptography, cluster behavior, or
live KIL enforcement.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-036 — 2026-08-29 — V2 scenario schema and strict loader implemented

**Input:** V2 Task 1 required a versioned scenario schema and loader that keeps
source-cited incident facts distinct from synthetic KTP state, local evidence,
and credential-policy assumptions.

**Interpretation:** “Strict” requires more than unknown-field rejection. JSON
booleans, integers, decimal strings, identifiers, URIs, dependency order, and
UTF-8 text must retain exact types and representations; permissive conversions
could silently turn malformed evidence into executable modeled state.

**Decision status:** Confirmed Task 1 implementation complete under local
review. The initial focused run failed because `kil.scenario` did not exist. A
second test-first boundary check demonstrated that lone UTF-16 surrogates could
enter the loader before UTF-8 validation was added. The corrected focused suite
passes 10 tests and full repository validation passes 89 tests under bundled
Python 3.12. The schema parses as JSON, all five preserved-source hashes pass,
and `git diff --check` passes.

**Rationale:** The loader now mirrors the versioned schema without coercing
strings, booleans, integers, or decimal fields. It rejects unknown fields at
every level, empty scenarios, duplicate event IDs, forward dependencies,
invalid primary-source URIs, and text that cannot enter canonical UTF-8.
Observed summaries receive source references; control, composite-state, and
local-evidence values receive explicit modeled rationales through the V1
`LabeledValue` contract.

**Affected artifacts:**

- `schemas/scenario-v1.schema.json`
- `src/kil/scenario.py`
- `tests/fixtures/scenario-minimal-v1.json`
- `tests/test_scenario.py`
- `docs/lab/V2-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Independent whole-V2 review remains pending. The
generic scenario schema does not itself supply historical truth; individual
event summaries and source labels must still be verified when the eight-phase
scenario is populated. Concrete KTP signature encoding remains outside V2.

**Next gate:** Implement Task 2 so the modeled credential-policy baseline and
both KIL modes consume the same immutable event stream, preserve unreachable
descendant decisions, and cannot label replay output validated.

This checkpoint validates deterministic loader behavior only. It does not
validate the historical counterfactual, raw KTP telemetry, cryptographic
enforcement, cluster behavior, or live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-037 — 2026-08-29 — Common-stream paired replay implemented

**Input:** V2 Task 2 required the modeled credential-policy baseline,
signed-state-only KIL, and signed-plus-local-reduction KIL to evaluate one
common scenario stream while preserving causal reachability.

**Interpretation:** A counterfactual action can still be computed after an
earlier KIL denial, but it must be marked unreachable under that mode rather
than silently removed. Historical outputs and their individual decisions must
also be structurally fixed to modeled evidence so callers cannot relabel them
validated.

**Decision status:** Confirmed Task 2 implementation complete under local
review. The expected RED run failed because `kil.replay` did not exist. The
corrected focused suite passes five tests and full repository validation passes
94 tests; all five preserved-source hashes and `git diff --check` pass.

**Rationale:** The replay engine evaluates every event once per mode, records
the credential-policy permit independently from reachability, and maintains
separate success sets for the baseline and both KIL modes. Descendant
reachability therefore reflects each mode’s causal path without hiding the
decision that would have been produced. `PairedDecision` and `ReplayReport`
accept only `EvidenceClass.MODELED`, and replay rejects mislabeled inputs and
runtime type bypasses.

**Affected artifacts:**

- `src/kil/replay.py`
- `tests/test_replay.py`
- `docs/lab/V2-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Whole-V2 review remains pending. Event-level
credential and policy results are modeled assumptions until source-specific
scenario data is populated. Replay does not verify concrete KTP signatures or
claim that historical infrastructure actually emitted these decisions.

**Next gate:** Implement deterministic run bundles whose identity and checksums
derive from the scenario, modeled report, implementation version, and profile,
and whose manifest can never claim validated evidence.

This checkpoint validates paired replay software behavior only. It does not
validate historical prevention, raw telemetry, cryptographic enforcement,
cluster behavior, or live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-038 — 2026-08-29 — Deterministic modeled replay bundles implemented

**Input:** V2 Task 3 required reproducible run directories containing the
scenario, modeled states and decisions, metrics, human-readable summary,
manifest, and integrity hashes.

**Interpretation:** Bundle identity must derive from the complete canonical
scenario and replay report plus explicit implementation and profile identities.
Publication must be atomic, aligned to one scenario, and structurally unable to
claim that a historical counterfactual is validated.

**Decision status:** Confirmed Task 3 implementation complete under local
review. The expected RED run failed because `kil.run_bundle` did not exist. The
corrected focused suite passes five tests and full repository validation passes
99 tests; all five preserved-source hashes and `git diff --check` pass.

**Rationale:** The writer rejects mismatched scenario/report identities,
ambiguous metadata, non-modeled reports, and reordered decisions. It derives a
stable run ID from canonical inputs, constructs all public artifacts before an
atomic directory rename, and emits SHA-256 entries for every public artifact.
Independent output roots produce byte-identical files. The manifest and metrics
carry modeled evidence, and the summary states explicitly that the historical
decisions are modeled, not validated.

**Affected artifacts:**

- `src/kil/run_bundle.py`
- `tests/test_run_bundle.py`
- `docs/lab/V2-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Whole-V2 review remains pending. The current 16-hex
run directory name is a deterministic local artifact identifier, not a
cryptographic signature or global uniqueness guarantee. Concrete signing,
external attestations, retention policy, and cluster artifact collection remain
later gates.

**Next gate:** Populate and source-check the canonical eight-phase Hugging Face
scenario, preserving observed summaries separately from all synthetic KTP and
credential-policy values.

This checkpoint validates deterministic bundle generation and integrity hashes
only. It does not validate historical prevention, raw telemetry, cryptographic
enforcement, cluster behavior, or live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-039 — 2026-08-29 — Canonical eight-phase incident scenario normalized

**Input:** V2 Task 4 required the Hugging Face July 2026 incident to become a
canonical eight-phase replay scenario aligned with the paper's phase map and
the approved rule that disclosed incident facts may be combined with clearly
labeled synthetic KTP context signals.

**Interpretation:** The event summaries and source-section anchors represent
observed public disclosure. Credential-policy results, composite KTP
enforcement state (`Q_i,c`), local divergence and coupling values, and every
derived decision are counterfactual inputs or outputs and must remain modeled.
Section labels are audit locators, not representations of raw telemetry.

**Decision status:** Confirmed Task 4 implementation complete under local
review. The expected RED run failed while the canonical scenario file was
absent. Four focused scenario tests now pass, full repository validation passes
103 tests under bundled Python 3.12, the scenario parses as JSON, all five
preserved-source hashes pass, and `git diff --check` passes. A replay smoke
check produces eight modeled baseline permits; both KIL modes deny phase 1 and
mark its seven causal descendants unreachable while still computing and
retaining their modeled decisions.

**Rationale:** Stable event IDs, authority classes, dependencies, paper-aligned
summaries, and primary-source anchors prevent narrative drift. Exact decimal
strings and uniform modeled rationales make the first counterfactual profile
reproducible without implying that Hugging Face disclosed KTP state or complete
policy-engine records. The scenario README makes the evidence boundary and the
reserved meaning of “validated” explicit.

**Affected artifacts:**

- `scenarios/hugging-face-july-2026/scenario-v1.json`
- `scenarios/hugging-face-july-2026/README.md`
- `tests/test_hugging_face_scenario.py`
- `docs/lab/V2-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The eight modeled numerical profiles still require
calibration against approved local-cluster telemetry. Public source-section
anchors may need more granular immutable locators if the upstream disclosure
changes. V2 still needs its supported CLI, first integrity-checked bundle, and
whole-phase review. Concrete KTP signatures remain outside this gate.

**Next gate:** Implement the reproducible replay CLI and documented Make target,
then emit and inspect the first modeled integrity-checked report bundle before
whole-V2 review.

This checkpoint validates scenario structure, provenance separation, and
deterministic replay behavior only. It does not validate historical prevention,
the modeled signal values, cryptographic enforcement, cluster behavior, or live
KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-040 — 2026-08-29 — Reproducible V2 CLI and first modeled report completed

**Input:** V2 Task 5 required a supported command-line interface, documented
Make target, and first integrity-checked modeled report suitable for inspection
and later white-paper figures.

**Interpretation:** A report intended for publication support must identify an
immutable implementation commit, emit exactly one deterministic bundle, expose
its evidence class in machine-readable metadata, and verify every public
artifact. Generated historical output remains local modeled evidence; it does
not become validated merely because the software and checksums pass.

**Decision status:** Confirmed Task 5 implementation complete under local
review. The expected RED test failed because `tools/replay.py` was absent. The
CLI test, all 25 V2-focused tests, and all 104 repository tests pass under
bundled Python 3.12. All five preserved-source hashes pass. The first report,
run `1ab32d9f4ea27624`, was generated from implementation commit
`e803cd144d785c13d07f9d96670a5c52e796314f`; all six public-artifact hashes
verify.

**Rationale:** The CLI fixes the first reduction profile to
`weighted-diagonal-v0-modeled`, loads the versioned canonical scenario, runs
all three comparison modes over one stream, and delegates atomic publication
to the tested bundle writer. The Make target requires explicit output and
implementation-version values. The report records eight modeled baseline
permits, eight denials in each KIL mode, and seven unreachable descendants in
each KIL mode after the phase-1 denial.

**Affected artifacts:**

- `tools/replay.py`
- `tests/test_replay_cli.py`
- `Makefile`
- `README.md`
- `docs/lab/V2-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Local generated bundle
  `artifacts/generated/v2-historical-replay/1ab32d9f4ea27624`

**Unresolved questions:** Whole-V2 diff review and integration remain pending.
The generated bundle is intentionally ignored by Git and is not a signed
attestation. The modeled profile still requires local-cluster calibration, and
concrete KTP signature verification remains a later gate. The all-deny first
profile is a testable counterfactual, not evidence of historical prevention.

**Next gate:** Perform whole-V2 review against the approved plan and evidence
contract, rerun final verification from the clean feature branch, then present
the integration options without merging or pushing automatically.

This checkpoint validates deterministic CLI and bundle behavior only. It does
not validate historical prevention, modeled parameter accuracy, cryptographic
enforcement, cluster behavior, or live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-041 — 2026-08-29 — Whole-V2 review passed with evidence-language fixes

**Input:** The completed V2 branch required a whole-diff review against the
approved historical-replay plan, evidence contract, reproducibility claims, and
integration boundary.

**Interpretation:** Passing incremental tests is insufficient for release
review. The complete branch diff must also pass whitespace checks; “validated”
must retain the founder-approved local-cluster meaning; source locators must not
be described as working URL anchors unless verified; and the exact persisted
report must reproduce byte-for-byte from its recorded implementation commit.

**Decision status:** Confirmed whole-V2 implementation ready for integration
selection after review fixes. The review found and corrected four committed
Markdown hard-break spaces, narrowed the README definition of validated to an
approved local-cluster validation protocol, and renamed incident source
anchors as section-level labels. The first report was regenerated in an
independent temporary root with the same run ID and byte-identical files; all
six public-artifact hashes verified. Full clean-branch verification is the
remaining procedural check before integration options are presented.

**Rationale:** The V2 exit criteria are satisfied: eight primary-source-labeled
cut points, structurally modeled synthetic values, one common event stream,
modeled-only historical decisions, deterministic bundle identity and contents,
an executable CLI, and integrity verification. The branch does not silently
promote software correctness into historical or live-cluster validation.

**Affected artifacts:**

- `README.md`
- `scenarios/hugging-face-july-2026/README.md`
- `docs/lab/V2-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Reviewed branch `feature/v2-historical-replay`
- Reproduced local run `1ab32d9f4ea27624`

**Unresolved questions:** The first approved profile denies every action at the
signed-state gate, so it does not yet provide a case where signed state permits
and fresh local evidence reduces authority. That two-timescale differentiation
should be a separately declared modeled calibration scenario or a later local
cluster experiment. The report is not signed, the source labels are not
immutable upstream anchors, concrete KTP signature verification is pending, and
no historical-prevention or live-enforcement claim is validated.

**Next gate:** Run final verification from the committed feature branch, then
choose local merge, push-and-PR, branch preservation, or explicit discard.

This review approves V2 software and evidence-contract behavior for integration
selection only. It does not validate modeled parameter accuracy, historical
prevention, cryptographic enforcement, cluster behavior, or live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-042 — 2026-08-29 — V2 merged, synchronized, and locally closed

**Input:** The founder selected push-and-pull-request integration, then reported
that GitHub pull request #3 was merged.

**Interpretation:** Merge completion must be verified from GitHub, local `main`
must be synchronized to the exact merge commit, the merged checkout and
persistent modeled bundle must be reverified, and the owned feature worktree
may be removed only after it is clean and fully merged. PR merge does not change
the evidence class of any historical output.

**Decision status:** Confirmed [pull request #3](https://github.com/gatekeeper454/KIL/pull/3)
merged eight V2 commits into `main` as `ddad70c0b6e4ec91acecca1c2076c1248f50cfaf`
after two successful checks. Local `main` fast-forwarded to that commit. The
merged checkout passes all 104 tests under bundled Python 3.12 and all five
preserved-source hashes; all six public-artifact hashes for modeled run
`1ab32d9f4ea27624` also verify. The clean managed V2 worktree was removed and
its local feature branch deleted. GitHub retained its default PR title and no
description because the founder merged before the proposed metadata edit.

**Rationale:** Verification on the actual merge commit establishes that V2
behavior survived integration. Cleaning only the owned, merged worktree closes
the local feature lifecycle while preserving the remote record, commit history,
merged source, and persistent ignored run bundle. The obsolete post-merge PR
metadata edit was not attempted.

**Affected artifacts:**

- V2 merge commit `ddad70c0b6e4ec91acecca1c2076c1248f50cfaf`
  in local and remote `main` history
- [GitHub pull request #3](https://github.com/gatekeeper454/KIL/pull/3)
- Removed local worktree `.worktrees/v2-historical-replay`
- Deleted local branch `feature/v2-historical-replay`
- Persistent modeled run
  `artifacts/generated/v2-historical-replay/1ab32d9f4ea27624`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Gate V3 has an approved design specification but no
implementation plan. The live cluster substrate, concrete signed composite KTP
state representation and verification boundary, repeat-count protocol, failure
and safety cases, and a trajectory that specifically differentiates
signed-state-only from local reduction must be resolved before implementation.
No V2 result is validated by this merge.

**Next gate:** Prepare and review the test-first Gate V3 live local-validation
implementation plan, beginning with environment preflight and a controlled
two-timescale case before cluster enforcement claims are allowed.

This transition validates merged V2 software and artifact integrity only. It
does not validate modeled parameter accuracy, historical prevention, concrete
KTP cryptography, cluster behavior, or live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-043 — 2026-08-29 — Gate V3 live-lab readiness assessed

**Input:** The founder asked whether KIL is ready to begin live lab validation
after V2 merge and closeout.

**Interpretation:** “Ready to begin” must be separated from “ready to execute a
validation run” and “ready to publish validated claims.” V1 and V2 provide a
stable decision/evidence contract, but Gate V3 also requires an approved
implementation plan, isolated runtime, concrete pre-execution adapter, signed
state fixture or verifier, workload generators, collector, controller, failure
experiments, and measurement protocol.

**Decision status:** Confirmed ready to begin Gate V3 planning and test-first
implementation; not yet ready to execute or label a live run validated. The V3
design baseline and acceptance criteria exist. Repository paths
`adapters/kubernetes/` and `deploy/kind/` contain README scaffolds only. No live
manifests, adapter, issuer, collector, controller, or integration tests exist.
On this host, Colima v0.10.3 and Lima 2.2.0 are installed, but Colima is stopped;
`docker`, `kubectl`, `kind`, and `helm` are not available in `PATH`.

**Rationale:** The merged V1/V2 kernel, schemas, provenance types, replay modes,
and bundle format are sufficient foundations for V3. Beginning with cluster
execution before selecting and specifying the enforcement boundary would make
the experiment irreproducible and could produce results that do not support the
paper's transport-enforcement claim. Missing local tooling is resolvable only
after the environment and dependency versions are approved.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-29-kil-lab-validation-design.md`
- `adapters/kubernetes/README.md`
- `deploy/kind/README.md`
- `tests/README.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Gate V3 needs a reviewed implementation plan and a
selected first enforcement boundary. The concrete composite-state encoding and
verification fixture, safe benign/adversarial action pair, local-reduction
differentiation case, failure profiles, repetition counts, latency collection,
tool versions, and isolated-cluster teardown contract remain open. Dependency
installation and starting Colima require explicit execution authority.

**Next gate:** Write and review the test-first V3 implementation plan. The plan
should begin with environment preflight and isolation guards, then implement a
minimal observable pre-execution transport adapter and the controlled case
where signed state permits but fresh local evidence reduces or denies. Only
after those checks pass should the cluster be created and validation runs begin.

This checkpoint is a readiness assessment only. It does not validate the host,
cluster, adapter, signed-state cryptography, modeled parameters, historical
prevention, or live KIL behavior.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-044 — 2026-08-29 — Gate V3 planning authorized; adapter boundary pending

**Input:** The founder authorized proceeding with the Gate V3 live-lab plan.

**Interpretation:** Authorization covers collaborative design and creation of a
test-first implementation plan. It does not yet authorize dependency
installation, starting Colima, creating a cluster, or running live experiments.
The existing V3 design baseline leaves the first enforcement adapter as an
explicit approval gate, so that boundary must be resolved before the detailed
specification and implementation plan can be finalized.

**Decision status:** Confirmed V3 planning is active. Proposed, not confirmed:
use a Kind-hosted Envoy external-authorization gateway as the first live
pre-execution transport boundary. Kubernetes admission is a narrower fallback
for workload-creation actions; eBPF is deferred because it would add kernel and
portability variables before the validation contract is proven.

**Rationale:** Envoy external authorization can block a request before the
upstream workload executes, reuse the V1 decision contract, expose both KIL
modes, and produce measurable allow/deny outcomes and latency without claiming
eBPF, SmartNIC, SDN, or production-scale enforcement. It keeps the first live
experiment focused on evidence quality and reproducibility.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-29-kil-lab-validation-design.md`
- Planned V3 design specification and implementation plan
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Founder approval of the Envoy external-authorization
boundary is pending. After that choice, the safe workload pair, concrete signed
state fixture, failure profiles, repetition counts, latency clock, dependency
versions, and teardown contract must be fixed in the design before plan writing.

**Next gate:** Confirm or reject the proposed first adapter boundary, then
compare the complete V3 implementation approaches and present the design for
incremental approval.

This checkpoint authorizes planning only. It does not validate or authorize
host changes, cluster creation, adapter behavior, signed-state cryptography,
modeled parameters, historical prevention, or live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-045 — 2026-08-29 — Envoy external authorization selected for V3

**Input:** The founder approved the proposed Kind-hosted Envoy external-
authorization gateway as the first Gate V3 live enforcement boundary.

**Interpretation:** V3 will validate pre-upstream request enforcement through
Envoy `ext_authz`, not Kubernetes admission or eBPF. The selected boundary must
remain infrastructure-controlled: a workload request cannot choose, bypass, or
downgrade the active comparison mode.

**Decision status:** Confirmed first live adapter boundary: Envoy `ext_authz`
inside an isolated Kind cluster. Kubernetes admission and eBPF are deferred and
must not be claimed by V3 results.

**Rationale:** Envoy can withhold a request before target execution, exposes
observable allow/deny and latency behavior, and can consume the existing V1
decision contract through a focused authorization service. It gives the lab a
transport-faithful first validation surface without introducing kernel-specific
variables or conflating workload admission with continuous request transport.

**Affected artifacts:**

- Planned V3 design specification
- Planned `adapters/envoy/` authorization adapter
- Planned Kind deployment and live integration suite
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The component topology, mode isolation, safe target
workload, signed-state fixture, local-evidence injection, collection contract,
failure matrix, repetitions, latency method, and tool versions still require
design approval.

**Next gate:** Approve the V3 component and data-flow architecture, including
mode isolation and the observable definition of pre-execution denial.

This decision selects an experimental adapter only. It does not validate or
authorize host changes, cluster creation, Envoy behavior, signed-state
cryptography, modeled parameters, historical prevention, or live KIL operation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-046 — 2026-08-29 — V3 topology, extension envelope, and diagram approved

**Input:** The founder approved the three-track Envoy architecture and directed
implementation to begin without another design prompt. The founder also
required a documented graphical diagram during implementation.

**Interpretation:** Approval fixes the V3 topology and permits direct transition
from specification to an inline, test-first implementation plan. It does not
remove normal host-security approval gates for dependency installation or
runtime mutation. The signed state must be expressed as a narrow KIL extension
that consumes and references KTP v2.0.0 Trust Proof and Kinetic Envelope
artifacts rather than replacing them.

**Decision status:** Confirmed: three isolated, infrastructure-fixed tracks
(`credential_policy_baseline`, `signed_state_only`, and
`signed_plus_local_reduce`) behind Envoy HTTP `ext_authz`; same normalized
requests; no client-controlled mode; harmless targets with append-only
invocation ledgers; and a denial proof requiring a joined KIL decision, Envoy
non-forwarding outcome, and absent target marker. Confirmed experimental
signature profile: Ed25519 compact JWS, software Level 1 lab key, maximum
ten-second lifetime, track-bound audience, and explicit non-conformance label
`kil.q-state.v0`. Confirmed evidence boundary: cluster behavior may become
validated, while synthetic Q values and local context remain modeled.

**Rationale:** KTP v2.0.0 already provides a signed Trust Proof, a ten-second
validity ceiling, the Kinetic Envelope tightening contract, and a gateway
consumption boundary. KIL's contribution is the authority-class-bound composite
state and reducing-only transport consumption profile. Separate tracks prevent
request-level downgrade, while target-side markers establish whether denial
occurred before the representative action executed.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`
- `docs/superpowers/specs/2026-08-29-kil-lab-validation-design.md`
- `docs/architecture/v3-envoy-live-validation.svg`
- `docs/paper/kinetic-infrastructure.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The implementation has not yet verified the exact
Envoy container digest, local runtime installation path, Kind networking,
container hardening compatibility, or latency behavior. The KTP specialist
must still determine whether the extension is expressed in KTP 2.1 or 3.0.

**Next gate:** Self-review and commit the V3 design, write the complete
test-first implementation plan, create an isolated worktree, and begin V3A
contract and process-level enforcement work.

This approval authorizes implementation but does not itself validate the host,
cluster, adapter, signature profile, modeled inputs, historical prevention, or
live KIL behavior.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-047 — 2026-08-29 — V3A implementation plan fixed for inline execution

**Input:** The founder authorized implementation without another design prompt
after approving the Envoy topology and requiring a documented graphical
diagram.

**Interpretation:** The multi-subsystem V3 design is split at a falsifiable
boundary. V3A implements the signed-state and authorization core plus a visible
process-contract demonstration. V3B introduces Envoy and Kind only after the
cryptographic, binding, fixed-mode, no-forward, and evidence-join contracts pass
without cluster variables.

**Decision status:** Confirmed V3A plan for inline execution. It will implement
the strict `kil.q-state.v0` payload, Ed25519 compact JWS, maximum ten-second
lifetime, exact subject/audience/class/action binding, revocation, three fixed
tracks, downgrade-header resistance, harmless target markers, proof joins, and
a modeled visible bundle. V3A output cannot use the project evidence label
`validated`; V3B remains the first live-cluster validation gate.

**Rationale:** Separating cryptographic and adapter contracts from cluster
orchestration makes failures attributable and keeps the first software increment
small enough for strict red-green testing. The reference gateway can prove the
join logic and target-marker semantics without pretending to prove Envoy
behavior.

**Affected artifacts:**

- `docs/superpowers/plans/2026-08-29-v3a-signed-state-authorization-core.md`
- Planned `schemas/q-state-v0.schema.json`
- Planned `src/kil/q_state.py`
- Planned `src/kil/live_authz.py`
- Planned `src/kil/reference_gateway.py`
- Planned `tools/v3a_demo.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** V3B still must resolve the installed Docker client,
Kind and kubectl installation, Envoy and application image digests, exact HTTP
header mapping, NetworkPolicy behavior under Kind, and cluster-level latency.

**Next gate:** Commit the V3A plan, create an ignored isolated worktree, verify
the 104-test baseline, then execute Task 1 with a witnessed failing test before
production code is added.

This plan authorizes process-level implementation only. It does not validate
Envoy, Kubernetes, modeled parameters, historical prevention, or live KIL
behavior.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-048 — 2026-08-29 — V3A signed-state and authorization core implemented

**Input:** The founder directed implementation to proceed without another
prompt and required the implementation documentation to include a graphical
diagram. The approved V3A plan required a signed, short-lived composite KTP
enforcement state, three fixed comparison tracks, a harmless target marker,
and a visible but explicitly modeled process-contract bundle.

**Interpretation:** V3A is the executable contract beneath the approved V3B
Envoy topology. It may prove strict signature consumption, reducing-only local
authorization, fixed-mode behavior, and joined forward-or-withhold semantics in
one process. It cannot prove Envoy, Kind, network isolation, cluster latency,
or historical prevention.

**Decision status:** Confirmed implemented: closed `kil.q-state.v0` claims;
canonical bounded fixed-point decimal wire values; Ed25519 compact JWS with a
ten-second maximum lifetime; revocation and exact time, subject, audience,
authority-class, and action-class binding; immutable adapter tracks; rejection
of malformed non-ASCII segments through the fail-closed path; three same-input
tracks; harmless target markers; and content-addressed evidence. Confirmed
review-complete modeled result: `permit / permit / deny`, marker counts
`1 / 1 / 0`, and valid proof joins. This is not a validated cluster result.

**Rationale:** Review found four material contract gaps before closeout: an
uncontrolled Unicode exception, a reassignable adapter track, noncanonical and
unbounded decimal encodings, and insufficient verification-key provenance.
Each runtime issue received a witnessed failing regression test before the
boundary fix. The evidence bundle now publishes the two signed state fixtures,
public JWK, full public-key thumbprint, deterministic software Level 1 fixture
provenance, graphical architecture, and eight integrity-checked artifacts.

**Affected artifacts:**

- `schemas/q-state-v0.schema.json`
- `src/kil/q_state.py`
- `src/kil/live_authz.py`
- `src/kil/reference_gateway.py`
- `tools/v3a_demo.py`
- `tests/test_q_state.py`
- `tests/test_live_authz.py`
- `tests/test_reference_gateway.py`
- `tests/test_v3a_demo.py`
- `docs/architecture/v3-envoy-live-validation.svg`
- `docs/lab/V3-PROGRESS.md`
- `adapters/envoy/README.md`
- `README.md`
- `tools/README.md`

**Evidence:** The pre-review run `52c90309d00439e7` at commit
`ad3db6aa7686781761bd8622a435c279f534df05` passed 121 tests but is development
history only. The review-complete run `b0cdc26b471c9539` at implementation
commit `700b307a573e3668024d51e3b156d7044b03fca3` passed 125 tests and all eight
published checksum checks. Both runs remain labeled `modeled` with validation
scope `process_contract_only`.

**Unresolved questions:** V3B still must install or resolve the local container
toolchain, pin Envoy and workload image digests, implement the frozen HTTP
adapter contract, prove NetworkPolicy and target isolation under Kind, execute
the full failure matrix, and measure cluster-level latency. The KTP specialist
must still decide whether the extension belongs in KTP 2.1 or 3.0.

**Next gate:** Review and integrate the V3A feature branch, then write and
execute the V3B Envoy/Kind implementation plan against the approved diagram and
the frozen adapter contract. Only a passing joined cluster run may introduce
`validated` for the observed transport result.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-049 — 2026-08-29 — V3A zero-exponent allocation boundary closed

**Input:** Final re-review of the T-048 implementation found that a Decimal zero
with an extreme negative exponent passed the calculated 64-character wire
bound but still entered Python fixed-point formatting before trailing-zero
normalization.

**Interpretation:** The mathematical value and calculated canonical wire value
were both zero, but the serializer's intermediate representation could still
allocate memory proportional to the attacker- or issuer-controlled exponent.
This was an availability defect in the experimental issuer path and meant the
T-048 evidence run was not yet the final review-complete implementation.

**Decision status:** Confirmed fixed. Any accepted Decimal zero now serializes
directly to the literal `"0"` before fixed-point formatting. A witnessed failing
regression uses a guarded formatter to prove that an extreme-exponent zero does
not reach the expansion operation. The T-048 run `b0cdc26b471c9539` remains
development history and is superseded by canonical modeled run
`ca26ff63c09cd78b`.

**Rationale:** A declared maximum wire length must bound intermediate work as
well as the final string. Short-circuiting the unique canonical zero form
preserves wire determinism and removes exponent-sized allocation without
changing charge semantics.

**Affected artifacts:**

- `src/kil/q_state.py`
- `tests/test_q_state.py`
- `docs/lab/V3-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Evidence:** Implementation commit
`4e02ed3727096174456de0b6edcb33403d7870df` passes 126 tests. Canonical modeled
run `ca26ff63c09cd78b` reproduces `permit / permit / deny`, marker counts
`1 / 1 / 0`, valid joins, and eight passing checksum verifications. Its scope
remains `process_contract_only`, not validated cluster behavior.

**Unresolved questions:** The V3B container toolchain, image digests, Envoy
adapter implementation, Kind network isolation, failure matrix, and cluster
latency remain unvalidated. KTP 2.1 versus 3.0 placement remains a specialist
decision.

**Next gate:** Obtain final feature review, integrate V3A, and then execute the
separately planned V3B Envoy/Kind live-cluster validation without relabeling the
modeled V3A evidence.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-050 — 2026-08-29 — V3A feature branch published for pull request

**Input:** After the final V3A review reported no remaining blockers, the
founder selected integration option 2: push the feature branch and create a
GitHub pull request.

**Interpretation:** Publication exposes the reviewed implementation for normal
repository review without merging it into `main`. The generated V3A evidence
remains modeled and the pull request must retain the V3A/V3B validation
boundary.

**Decision status:** Confirmed branch publication. Branch
`feature/v3a-signed-state-authz` is pushed to `origin` at commit `fb84507` plus
this lineage closeout. Pull-request title and description are prepared in the
authenticated GitHub interface; final creation is pending the required
action-time confirmation for external submission.

**Rationale:** A pull request preserves the isolated worktree for review and
iteration. The proposed description records 126 passing tests, canonical
modeled run `ca26ff63c09cd78b`, eight verified checksums, the independent review
result, and the prohibition on treating V3A as Envoy or Kind validation.

**Affected artifacts:**

- Remote branch `origin/feature/v3a-signed-state-authz`
- Prepared GitHub pull request from the feature branch to `main`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The pull request has not yet been submitted. Merge
review and the separate V3B live-cluster plan remain future gates.

**Next gate:** Confirm and submit the prepared GitHub pull request, record its
number and URL, then preserve the feature worktree for review feedback.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-051 — 2026-08-29 — V3A pull request 4 created

**Input:** The founder confirmed the prepared GitHub pull-request submission
after selecting integration option 2.

**Interpretation:** The confirmed external submission completes branch
publication while preserving the feature worktree for review feedback. It does
not authorize merge or advance the evidence class of any V3A result.

**Decision status:** Confirmed pull request created: [gatekeeper454/KIL
#4](https://github.com/gatekeeper454/KIL/pull/4), titled “Implement V3A
signed-state authorization core,” from `feature/v3a-signed-state-authz` into
`main`. The PR description records the canonical modeled run, verification
count, checksum result, independent review, graphical architecture, and V3A/V3B
claim boundary.

**Rationale:** The pull-request path provides a durable review surface without
merging or deleting the isolated implementation branch. The worktree remains
available for corrections and review responses.

**Affected artifacts:**

- [GitHub pull request #4](https://github.com/gatekeeper454/KIL/pull/4)
- Remote branch `origin/feature/v3a-signed-state-authz`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Pull-request review and merge remain pending. Gate V3B
still requires its separate Envoy/Kind implementation and live-cluster
validation plan.

**Next gate:** Review and merge pull request #4 when accepted, preserve V3A's
modeled/process-only classification, then begin the approved V3B planning gate.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-052 — 2026-08-29 — Pull request 4 CI dependency failure diagnosed

**Input:** The founder reported that pull request 4 was failing and requested a
check of the pull-request validation state.

**Interpretation:** Both red checks are executions of the same `bootstrap` job,
once for the branch `push` event and once for the `pull_request` event. The
immediate task was diagnosis only; no workflow, dependency, implementation, or
remote pull-request change was authorized.

**Decision status:** Confirmed diagnosis; no fix applied. The clean GitHub
Actions Python 3.11 runner executes `make validate` without first installing
`requirements-lab.txt`. Test discovery then raises
`ModuleNotFoundError: No module named 'cryptography'` in
`test_live_authz.py`, `test_q_state.py`, and `test_reference_gateway.py`; the
V3A demonstration test fails downstream when its subprocess imports the same
missing library. The separate GitHub Actions Node.js 20 deprecation annotation
is a warning and is not the cause of this run's failure.

**Rationale:** `requirements-lab.txt` pins `cryptography==50.0.0`, while
`.github/workflows/ci.yml` proceeds directly from Python setup to
`make validate`. The repository's dependency metadata also requires
reconciliation: `pyproject.toml` currently declares `dependencies = []`, even
though the V3A implementation imports `cryptography` at module load, and the
Makefile still describes the entire test suite as dependency-free.

**Affected artifacts:**

- [GitHub pull request #4](https://github.com/gatekeeper454/KIL/pull/4)
- `.github/workflows/ci.yml`
- `requirements-lab.txt`
- `pyproject.toml`
- `Makefile`
- `src/kil/q_state.py`
- `src/kil/live_authz.py`
- `tools/v3a_demo.py`
- `tests/test_live_authz.py`
- `tests/test_q_state.py`
- `tests/test_reference_gateway.py`
- `tests/test_v3a_demo.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The immediate workflow repair and the durable package
dependency contract have not yet been selected or implemented. The duplicate
`push` and `pull_request` executions may be intentional, so trigger
deduplication is a separate maintenance decision rather than part of the
failure cause.

**Next gate:** Authorize a focused CI/dependency repair. At minimum, install the
pinned lab requirements before `make validate`; before merge, also decide
whether `cryptography` is a required project dependency or a documented
optional lab extra, then make `pyproject.toml`, the Makefile description, and
the CI bootstrap path express the same contract.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-053 — 2026-08-29 — V3A CI dependency contract repaired locally

**Input:** After reviewing the pull-request failure diagnosis, the founder
authorized execution of the recommended repair steps on pull request 4.

**Interpretation:** The approved V3A design already classifies
`cryptography==50.0.0` as an optional laboratory dependency so the V1 decision
kernel can retain its standard-library-only boundary. The repair therefore
must expose and install the V3A lab dependency without recasting it as a V1
kernel dependency or changing any KIL/KTP protocol semantics.

**Decision status:** Confirmed implemented and locally verified. GitHub Actions
now installs the exact `requirements-lab.txt` pin before `make validate`;
`pyproject.toml` publishes a matching `lab` optional extra; Makefile help and
README bootstrap instructions disclose the dependency boundary. Four
repository-contract regressions were observed failing before implementation
and passing afterward. The complete Python 3.12.13 validation run passes 130
tests, the metadata check, and `git diff --check`.

**Rationale:** A clean runner must materialize every dependency required by the
suite it invokes. Keeping one exact version in both the existing lab
requirements pin and the `lab` project extra makes the installation path
discoverable while preserving the approved split between the deterministic V1
kernel and V3A cryptographic validation. The regression test makes divergence
between those declarations, CI ordering, command help, and bootstrap guidance
visible in future changes.

**Affected artifacts:**

- `.github/workflows/ci.yml`
- `requirements-lab.txt` (unchanged canonical pin)
- `pyproject.toml`
- `Makefile`
- `README.md`
- `tests/test_dependency_contract.py`
- `docs/superpowers/plans/2026-08-29-v3a-ci-dependency-repair.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- [GitHub pull request #4](https://github.com/gatekeeper454/KIL/pull/4)

**Unresolved questions:** Fresh GitHub-hosted `push` and `pull_request` jobs
must still verify the branch after publication. The duplicate event triggers
and the noncausal GitHub Actions Node.js runtime warning remain separate
maintenance questions. No V3A result changes evidence class: the process
bundle remains `modeled`, not validated cluster evidence.

**Next gate:** Publish the repair commit to pull request 4 and require both
fresh bootstrap checks to pass. If green, the pull request returns to its merge
review gate; V3B Envoy/Kind execution remains the next validation phase after
integration.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-054 — 2026-08-30 — V3B opened with a closed toolchain and boundary profile

**Input:** The founder directed the project to begin the next phase after V3A
was merged and the repository was synchronized.

**Interpretation:** The next approved phase is V3B live Envoy/Kind validation.
Execution is divided into two falsifiable increments: V3B-1 first proves the
existing V3A authorization contract through a pinned local Envoy HTTP
`ext_authz` boundary; V3B-2 then reuses those exact artifacts in the approved
Kind/Calico namespace and NetworkPolicy topology. This sequencing does not
change the three fixed comparison tracks, signed-state semantics, or evidence
classes.

**Decision status:** Confirmed phase start and Task 1 implementation on the
isolated branch `feature/v3b-envoy-kind-live-validation`. The released profile
is now closed at Kind 0.32.0, the official digest-pinned Kubernetes 1.36.1 node,
kubectl 1.36.3, Envoy 1.39.0, and Calico 3.32.0. The earlier
0.33.0/1.37.0/1.39.1 tuple remains visible as the original planning target and
is not represented as released evidence. Thirteen new fail-closed profile
tests and the complete 143-test repository suite pass locally. No Envoy
container, Kind cluster, NetworkPolicy, or live enforcement result exists yet;
all earlier V3A evidence retains its `modeled` classification.

**Rationale:** Release identities must be real, mutually compatible, and
content-resolvable before they can enter a validation manifest. A closed,
immutable profile prevents silent version drift, alternate asset substitution,
unsafe URL or port changes, mutable node-image use, and accidental operations
against a default cluster. Envoy's raw HTTP protocol automatically conveys
method, path, Authorization, Host, and Content-Length; documentation now
separates those transport facts from KIL's five trusted semantic inputs. Only
`x-request-id` and `x-kil-q-state` need explicit `allowed_headers` matchers,
while Host and Content-Length are ignored by authorization evaluation.

**Affected artifacts:**

- `docs/superpowers/plans/2026-08-30-v3b1-toolchain-http-boundary.md`
- `deploy/kind/v3b-profile.json`
- `src/kil/v3b_preflight.py`
- `tests/test_v3b_preflight.py`
- `docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`
- `adapters/envoy/README.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The Docker CLI archive still requires a locally
observed source hash because its official index publishes no sidecar checksum.
Kind and kubectl downloads, executable hashes, Envoy and Python image digests,
the HTTP adapter, harmless target ledger, deterministic Envoy configuration,
local boundary proof, and full Kind/Calico matrix remain unexecuted. The first
live run must continue to prove denial with the joined KIL decision, absent
Envoy upstream, and zero target markers; none may be inferred from Task 1.

**Next gate:** Implement and test the bounded, atomic V3B tool bootstrap without
network access, then cross the explicit download gate to materialize the
allowlisted tools under ignored `.tools/` and record their content identities.
Starting Colima, pulling images, and creating containers remain a later,
separate runtime-mutation gate.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-055 — 2026-08-30 — V3B tool bootstrap materialized and content-locked

**Input:** The founder directed the project to proceed to the next V3B gate.

**Interpretation:** Execute V3B-1 Task 2 without broad host modification:
implement the security-sensitive downloader and extractor test-first, install
only the exact profile assets under the isolated worktree's ignored `.tools/`
directory, and produce a locally verifiable content lock. This gate does not
start Colima, pull container images, create a Kind cluster, or produce live
enforcement evidence.

**Decision status:** Confirmed implemented and locally verified. Fourteen new
bootstrap tests were observed failing before implementation and now pass. The
complete repository suite passes 157 tests. The explicit network gate installed
and independently re-verified these identities:

- Docker CLI 29.7.2, build `a7dcaa6`; archive SHA-256
  `b8683ed19d1f06048a496f9b8429e2c71d0b088d475b7487c054ea3666c02a3c`;
  executable SHA-256
  `a078469d8b77683b81e1604ee35af488ef143a8a0230897f05f0839b2f42d1dd`;
  archive attestation `locally_observed`.
- Kind v0.32.0, Go 1.26.3, darwin/arm64; executable SHA-256
  `dca67911095a110c2b5c36e26df6cac860c602033e456c0db47be498cdef1ebb`;
  attestation `upstream_sidecar`.
- kubectl v1.36.3, commit `0f29094e5b73085e3802ecc1298ecae13866bfe6`,
  darwin/arm64; executable SHA-256
  `fc8582acde13869a606730a79379d6515f30c68afcced0b5ac8789d5d002b7d6`;
  attestation `upstream_sidecar`.

The content lock binds profile SHA-256
`7800ccef61346eaadabaec3b6f40f2e5bb70c299c61792313fe0068190e8f3ec`
to the source URL, archive hash, executable hash, byte size, attestation class,
and captured version output for every installed tool. A second preflight read
the installed bytes and version output and matched the lock. Downloaded
binaries and the local lock remain ignored and are not repository artifacts.

**Rationale:** Exact profile admission, bounded reads, restricted redirects,
safe tar inspection, publisher-checksum verification before atomic replacement,
fixed executable modes, and command-local PATH usage prevent the bootstrap
from becoming an uncontrolled supply-chain or host-configuration mechanism.
The Docker static archive's official index provides no checksum sidecar, so its
observed hash is recorded without claiming publisher attestation. No shell
startup file or global Docker context was changed.

**Affected artifacts:**

- `.gitignore`
- `Makefile`
- `tools/bootstrap_v3b_tools.py`
- `tests/test_v3b_tool_bootstrap.py`
- `docs/superpowers/plans/2026-08-30-v3b1-toolchain-http-boundary.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- `.tools/locks/v3b-tools.json` (local, ignored evidence input)
- `.tools/bin/docker` (local, ignored)
- `.tools/bin/kind` (local, ignored)
- `.tools/bin/kubectl` (local, ignored)

**Unresolved questions:** Docker's publisher identity remains weaker than Kind
and kubectl because no official sidecar is available. Envoy and Python base
image tags still require registry-digest resolution. The HTTP authorization
adapter, harmless target ledger, deterministic Envoy configuration, local
container boundary proof, Kind/Calico topology, failure matrix, and repetition
protocol remain unexecuted. Tool materialization is not live KIL validation.

**Next gate:** Implement V3B-1 Task 3, the fixed-track raw HTTP authorization
boundary, test-first. It must preserve the five-input semantic contract, keep
track selection in read-only process configuration, delegate authorization to
the existing immutable adapter, redact credential and signed state from logs,
and fail closed with generic client responses.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-056 — 2026-08-30 — Fixed-track HTTP authorization boundary implemented

**Input:** The founder directed execution of V3B-1 Task 3.

**Interpretation:** Implement the process-level raw HTTP authorization service
that will sit behind Envoy's `ext_authz` filter. Preserve the existing immutable
`AuthorizationAdapter` decision semantics, fix the validation track at process
construction from read-only configuration, accept only the five planned
semantic inputs, and create no live-cluster or live-Envoy evidence claim at
this gate.

**Decision status:** Confirmed implemented and locally verified at the process
boundary. Nineteen focused tests and the complete 176-test repository suite
pass. The service exposes immutable request and response values, resolves
server-held fixtures by request ID, maps the original method and path, compares
the presented authorization value to the server-held digest in constant time,
accepts the signed composite KTP enforcement state only through
`x-kil-q-state`, and obtains action mapping, expected identity, and local
evidence only from the selected server fixture. Track selection is fixed when
the application is constructed and cannot be selected by a request header.

Permit, policy denial, and parsing/internal failure map to HTTP 200, generic
HTTP 403, and generic HTTP 503 respectively. Responses expose a decision digest
when one exists. Canonical JSONL records exclude credentials, signed Q-state,
private keys, and internal client-facing denial detail; unknown request-header
values are not retained. The server enforces a 16 KiB header limit and a zero
request-body contract. `/healthz` bypasses authorization and produces no
decision record, while still rejecting a nonzero request body. Configuration
is closed-schema, read-only, size-bounded, fixed to the container bind contract,
and admits public verification keys but no private key material. A review-found
failure path was reproduced test-first and corrected so an already-computed
decision digest remains in the generic 503 response and error record when the
durable recorder cannot append.

**Rationale:** This preserves the distinction between transport carriage and
authorization semantics. Envoy may convey the planned request context, but it
cannot choose a KIL validation track or supply authoritative identity and local
evidence. Reusing the existing adapter avoids creating a second policy engine,
while generic client responses and secret-free durable records constrain the
new HTTP surface. The no-activation server-construction test is paired with
pure request/health behavior tests because this execution sandbox prohibits
loopback socket binding; production construction continues to bind and
activate by default.

**Affected artifacts:**

- `src/kil/ext_authz_http.py`
- `tests/test_ext_authz_http.py`
- `docs/superpowers/plans/2026-08-30-v3b1-toolchain-http-boundary.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- `src/kil/live_authz.py` (delegated to unchanged)

**Unresolved questions:** Raw HTTP interoperability with the selected Envoy
image has not yet been exercised. No Envoy filter configuration, container
image, live socket exchange, Colima runtime, Kind cluster, Calico policy, or
target-side marker evidence exists at this gate. The harmless target ledger,
deterministic Envoy configuration, image-digest binding, local container
boundary proof, and full live failure matrix remain pending.

**Next gate:** Execute V3B-1 Task 4 test-first: implement the harmless target
ledger process with append-before-response semantics so later live validation
can prove both successful delivery and the absence of a target marker on
denial.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-057 — 2026-08-30 — Harmless V3B target ledger process implemented

**Input:** The founder directed execution of V3B-1 Task 4.

**Interpretation:** Implement the target-side half of the later Envoy
forward-or-withhold proof without introducing any consequential handler. The
target must fix run and track identity at process construction, treat the
forwarded request ID, track, and decision digest as bounded join assertions,
and make a durable invocation marker observable before returning success.

**Decision status:** Confirmed implemented and locally verified at the process
boundary. Sixteen focused tests and the complete 192-test repository suite
pass. The application admits only `GET /benign/read` and
`POST /consequential/admin` as marker-producing routes. Both are no-effect
representations: their only side effect is appending one canonical target
record. A successful record contains the fixed run ID, bounded request ID,
fixed track, exact path, decision digest, and monotonic receive/response-ready
timestamps. The dedicated JSONL ledger uses owner-only mode, append semantics,
`fsync`, and an in-process lock; the append completes before HTTP 200 is
returned.

Unknown or method-mismatched routes return 404 without a marker. Missing,
duplicate, malformed, or cross-track join headers and body-bearing requests
return 400 without a marker. Duplicate request IDs return 409, mark the ledger
invalid, and do not append a second line. Existing canonical ledger records are
validated and reloaded at startup, so duplicate detection survives a target
process restart. Ledger or clock failure marks the evidence stream invalid and
returns generic HTTP 503. Authorization and signed Q-state headers are ignored
and never enter either in-memory or durable target records. `/healthz` creates
no target marker.

The stdlib HTTP entry point uses a closed, size-bounded, read-only JSON
configuration that fixes run ID, `LiveTrack`, container bind
`0.0.0.0:8080`, and an absolute dedicated ledger path. Tests construct the
server without activating a socket because the execution sandbox prohibits
loopback binding; production construction binds and activates by default.

**Rationale:** A target response is not proof of execution. The durable marker
is the target-side evidence source and must therefore exist before success is
reported, remain unambiguous across restarts, and contain only the minimum join
fields. Fixing run and track at startup prevents a forwarded header from
selecting a comparison mode, while duplicate invalidation prevents two target
invocations from being misrepresented as one valid permit.

**Affected artifacts:**

- `src/kil/target_http.py`
- `tests/test_target_http.py`
- `docs/superpowers/plans/2026-08-30-v3b1-toolchain-http-boundary.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- `src/kil/reference_gateway.py` (unchanged modeled predecessor)

**Unresolved questions:** The target has not yet received a request through
Envoy, and no live socket, container image, image digest, Envoy access record,
upstream-host observation, Colima runtime, Kind cluster, or NetworkPolicy
evidence exists at this gate. A duplicate conflict is observable through the
409 response and invalid in-memory ledger state; joined runtime collection of
that failure remains Task 6 work.

**Next gate:** Execute V3B-1 Task 5 test-first: render the deterministic Envoy
raw-HTTP `ext_authz` configuration, prove the exact header/filter/fail-closed
contract, and add the digest-supplied hardened KIL service image without
starting the container runtime.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-058 — 2026-08-30 — Deterministic Envoy and hardened image contract locked

**Input:** The founder directed execution of V3B-1 Task 5 and asked whether
multiple agents could accelerate the work.

**Interpretation:** Implement the static Envoy raw-HTTP `ext_authz` and KIL
service-image contracts test-first, without starting Colima, pulling an image,
building a container, or claiming live enforcement. Parallel work was limited
to disjoint Envoy, container, and read-only contract-audit streams; the streams
were then cross-reviewed and integrated in the shared Task 5 gate.

**Decision status:** Confirmed implemented and statically verified. The Envoy
renderer emits a fresh canonical bootstrap with one port-8080 listener, an
`ext_authz` filter immediately before the router, a 250 ms authorization
timeout, fail-closed `ServiceUnavailable` behavior, no authorization retries,
no route-cache clearing, and two fixed `STRICT_DNS` clusters. The track and
target cluster are process configuration, never request-selected. The
top-level Envoy 1.39 matcher adds exactly `x-request-id` and `x-kil-q-state` to
the automatically conveyed raw-HTTP context. Host and Content-Length remain
transport metadata ignored by KIL evaluation. Authorization and Q-state are
removed before the target; a client track value is overwritten; only the
decision digest may flow from authz to the target or client.

The JSON stdout access record has a closed seven-field join schema. Envoy
preserves the exact authz response digest for HTTP 200 permits and HTTP 403
policy denials. Envoy 1.39.1 converts an authz HTTP 5xx to an authorization
error before response-header and dynamic-metadata extraction, so the digest
field is explicitly `"-"` for that path. Such an error must be joined by fixed
run, fixed track, request ID, the KIL decision record, Envoy no-upstream
evidence, and zero target markers; the experiment may not infer a digest Envoy
discarded.

The KIL service image contract now requires both build stages to receive the
same externally supplied digest-pinned Python base. A Dockerfile-specific
ignore file excludes the repository by default and admits only the exact
source, metadata, and dependency-lock inputs, so private and generated
material is excluded before context transfer. The build backend
`setuptools==82.0.0` and the arm64 runtime closure
`cryptography==50.0.0`, `cffi==2.1.1`, and `pycparser==3.0` are exact and
hash-locked to official PyPI release metadata. Local `.[lab]` installation
disables dependency resolution and build isolation. Only `/install` crosses
into the runtime stage, which runs as UID/GID 65532, exposes only 8080, has a
stdlib health check, and is compatible with a read-only root filesystem when
the controller supplies the explicit read-only config and writable ledger
mounts.

The initially recorded Envoy 1.39.0 profile remains visible in earlier lineage
entries. Task 5 corrects the active profile to Envoy 1.39.1 because the
2026-08-27 security release superseded it with two additional HTTP
`ext_authz` fixes. This is a security-profile correction, not a change to the
approved topology, KTP extension boundary, or evidence classes. The ignored
local tool lock was rebound to the corrected profile SHA-256
`8d6da1c20bf0def2ab5495dc5c87586b99d0ef024cd6c42236b2dc8bfd4afe62`;
all three existing tool bytes, modes, and version outputs re-verified without
redownloading them.

Thirty-six focused Envoy, container, and profile tests pass. The complete
repository suite passes 215 tests; the new Python files compile, the local V3B
tool preflight passes, and `git diff --check` passes. Independent audit and
both cross-reviews approved the remediated static contract with no remaining
Task 5 blocker.

**Rationale:** A deterministic configuration is insufficient if its schema is
deprecated, its evidence fields promise values Envoy cannot preserve, its
build context exposes unrelated repository content, or its dependencies remain
mutable. Locking the current Envoy API, honest error-path semantics, the
pre-transfer context boundary, dependency artifacts, fixed route/track, and
non-root runtime creates a falsifiable input to the live proof without
prematurely promoting static checks to runtime validation.

**Affected artifacts:**

- `src/kil/v3b_envoy.py`
- `tests/test_v3b_envoy.py`
- `deploy/kind/Dockerfile.v3b`
- `deploy/kind/Dockerfile.v3b.dockerignore`
- `deploy/kind/requirements-v3b-build.txt`
- `deploy/kind/requirements-v3b-runtime.txt`
- `tests/test_v3b_container_contract.py`
- `deploy/kind/v3b-profile.json`
- `src/kil/v3b_preflight.py`
- `tests/test_v3b_preflight.py`
- `docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`
- `docs/superpowers/plans/2026-08-30-v3b1-toolchain-http-boundary.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- `.tools/locks/v3b-tools.json` (local, ignored, profile binding refreshed)

**Unresolved questions:** The rendered JSON has not been parsed by the exact
Envoy 1.39.1 executable. The Python base and Envoy image tags still require
registry-digest resolution. The image has not been built, inspected, or run on
arm64, so wheel compatibility, layer contents, numeric identity, read-only-root
operation, and health behavior remain unvalidated. No live permit, policy
denial, authz-5xx, timeout, retry-header, header-sanitization, upstream-host, or
target-marker evidence exists yet. Colima, containers, Kind, Calico, and
NetworkPolicy remain unstarted.

**Next gate:** Execute V3B-1 Task 6. First resolve the Python and Envoy tags to
registry digests, validate the bootstrap with exact Envoy 1.39.1, build and
inspect the content-identified KIL image, and run the local three-track boundary
proof. The run must treat `"-"` as absent, require digest equality only where
Envoy preserves it, cross-check request-carried run IDs, inject client retry
controls, and prove exactly one target marker for a permit and zero for every
denial or error before any V3B-2 Kind claim.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-059 — 2026-08-30 — V3B-1 controller code-quality review identified blockers

**Input:** Review only the finished uncommitted V3B-1 local Envoy controller
and focused tests for correctness, maintainability, security pitfalls, and test
gaps without editing those files or invoking Colima, Docker, the network, or
other live operations.

**Interpretation:** Perform a static post-implementation audit of
`tools/v3b1_local_envoy.py` and `tests/test_v3b1_local_envoy.py`, limited to the
approved V3B-1 local boundary and excluding V3B-2 scope.

**Decision status:** Review not approved. The focused 18-test suite passes and
both files compile, but static counterexamples show that the evidence join
accepts an all-deny three-track result even though the central run is accepted
only for `permit / permit / deny`; it also accepts a permit marker for a target
path that differs from the central request and accepts reduced request records
that omit the authorization, Q-state, and adversarial-header attestations.
Lifecycle mutation is not recoverable if `up`, a partially issued `run`, or
`down` fails between durable checkpoints, and private controller directories
are prepared without rejecting symbolic-link roots.

**Rationale:** Passing happy-path construction and join tests does not establish
the experiment's acceptance predicate or safe lifecycle recovery. The live gate
must not begin while an internally consistent but wrong three-track outcome can
be marked valid, while unrelated target evidence can satisfy a permit join, or
while an ordinary command/HTTP/teardown failure can leave the dedicated profile
outside controller-managed recovery.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (reviewed only; no changes)
- `tests/test_v3b1_local_envoy.py` (reviewed only; no changes)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The blockers require implementation and regression
tests. No assertion is made about live Envoy, image, Colima, container, or
network behavior because this review intentionally ran no live operations.

**Next gate:** Enforce the exact central three-track acceptance tuple, bind the
target path and complete request facts into the join, add durable resumable or
exact rollback checkpoints for every mutating lifecycle phase, reject symbolic
link private roots, then rerun the focused static suite and independent review
before the runtime-mutation gate.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-060 — 2026-08-30 — V3B-1 controller remediation re-review

**Input:** Re-review the finished Task 6 controller and tests after remediation,
including durable-journal recovery, exact central outcomes, request/target
evidence, private-root safety, and test quality, without live operations.

**Interpretation:** Verify closure of the T-059 findings and inspect the newly
expanded recovery and publication paths for current correctness or security
defects, still limited to V3B-1.

**Decision status:** Review remains unapproved. The prior central-outcome,
complete-request-schema, target-path, and three primary private-root findings
are substantially corrected, and the focused suite now passes 31 tests. Current
static counterexamples nevertheless show that the full-run join requires an
`untrusted_mode_header_ignored` reason even though the pinned Envoy header
allowlist prevents `x-kil-mode` from reaching authz, so correct live records
cannot pass the claimed causal tuple. Authz-5xx evidence can again claim an
Envoy/client digest that pinned Envoy discards, while state and public evidence
paths still accept unchecked symbolic-link ancestors. The ambiguous
Colima-start recovery also upgrades mere intent plus prior absence into profile
ownership, which can authorize deletion of a later unrelated profile. Journal
request hashes are recorded but not checked against the recovered request file,
and the mutation-phase test only echoes synthetic event names rather than
executing failure recovery.

**Rationale:** Durable intent improves crash handling, but an intent is not
proof that a particular profile was created by the controller, and unused
record hashes do not bind recovered evidence. Publication and deletion must
remain fail-safe under ambiguous external state and redirected filesystem
paths.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (reviewed only; no changes)
- `tests/test_v3b1_local_envoy.py` (reviewed only; no changes)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The current findings require focused fixes and real
injected-runner recovery tests. No live Envoy, Colima, Docker, image, socket, or
network behavior was exercised by this re-review.

**Next gate:** Align the causal-reason tuple with the pinned Envoy request-header
boundary, require pinned-Envoy 5xx sentinels, close every writable state and
publication path against symlink ancestors, replace intent-only profile
ownership reconciliation with uniquely observed ownership or fail-safe manual
recovery, verify completed-request journal hashes during collection/down, and
exercise actual controller failures before the runtime-mutation gate.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-061 — 2026-08-30 — V3B-1 controller final remediation re-review

**Input:** Perform a final static code-quality and correctness re-review after
the second Task 6 remediation, verifying causal reasons, ambiguous-profile
handling, symlink ancestry, authz-5xx sentinels, journal/request hash binding,
teardown continuation, and atomic publication without live operations.

**Interpretation:** Re-run the focused isolated tests and inspect only the
current V3B-1 local Envoy controller and tests, with special attention to
failure/retry boundaries introduced by the latest remediation.

**Decision status:** Review remains unapproved on one filesystem-safety
blocker. The five previously enumerated behavioral findings are corrected:
the live causal tuple matches the filtered header boundary, ambiguous Colima
start remains manual and non-destructive, configured state/evidence ancestors
are rejected when symbolic links, 5xx requires the raw Envoy sentinel and no
client digest, and request records are hash-bound to exactly one successful
journal completion. Teardown evidence rejection now continues exact owned
cleanup and publication staging is private and atomic. However, fixed child
directories under the validated private root are not themselves validated.
A pre-existing `.tools/v3b1-private/manifests` symbolic link is followed by
the manifest write before `_bind_journal_manifest` checks containment, and the
same class of redirection exists for the `completed` journal archive path.

**Rationale:** Validating a parent root once does not make attacker- or
stale-state-controlled descendants safe. The controller must reject every
lexical ancestor before the first write or rename, rather than detect the
redirection only after data has already been written outside the private root.
The focused 34-test suite otherwise passes, and no live Envoy, Colima, Docker,
image, socket, or network operation was performed.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (reviewed only; no changes)
- `tests/test_v3b1_local_envoy.py` (reviewed only; no changes)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Add regression coverage for symbolic-link
`manifests`, `provisional`, and `completed` child directories, including the
guarantee that rejection occurs before any external write or journal move.

**Next gate:** Validate and create all fixed private child directories through
the same ancestor-walking containment primitive before mutation, then rerun
the focused static suite and final review before the runtime-mutation gate.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-062 — 2026-08-30 — V3B-1 child-symlink and final ownership/publication verification

**Input:** Narrowly verify the remediated manifest, provisional, and completed
child-directory symbolic-link attacks, then inspect start ownership and staged
publication revalidation without edits or live operations.

**Interpretation:** Reproduce the filesystem counterexamples entirely in
temporary directories, run the focused static suite, and examine only the new
ownership and publication-boundary logic.

**Decision status:** Review remains unapproved on two blockers. The three
private child-directory attacks are closed: `manifests`, `provisional`, and
`completed` symbolic links are rejected before external writes, and the
completed-archive regression leaves the journal in place. However, a successful
`colima start` command now marks the profile owned before post-start identity
attestation. If attestation fails before a manifest exists, cleanup relies only
on the controller's local nonce file and can stop/delete a same-name profile
that raced into existence and was never bound to that nonce. Separately,
publication revalidates the staged manifest and evidence artifact hashes but
does not compare the staged summary to the canonical public summary. A fault
injection that rewrites `summary.md` after public-manifest creation is accepted,
checksummed, renamed, and published.

**Rationale:** Command success plus an unbound local file is insufficient
identity evidence for destructive deletion when the profile attestation failed.
Likewise, checksum correctness only proves the bytes that were checksummed; it
does not prove that an excluded, human-readable claim artifact has the expected
canonical content.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (reviewed only; no changes)
- `tests/test_v3b1_local_envoy.py` (reviewed only; no changes)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Bind a successful start to profile-observed nonce
identity before authorizing deletion, with manual recovery on failed identity
attestation, and compare staged `summary.md` bytes to `_public_summary(...)`
after the final fault boundary.

**Next gate:** Correct both fail-safe checks, add race/failed-attestation and
summary-mutation regressions, then rerun the focused suite and independent
review before live mutation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-063 — 2026-08-30 — V3B-1 final static recovery and publication review passed

**Input:** Perform the final narrow read-only review of profile deletion
authority, canonical staged publication, symbolic-link ancestry, journal
recovery, and teardown/publication invariants, with focused tests and no live
operations.

**Interpretation:** Verify closure of T-062 using independent temporary-path
counterexamples, the complete focused controller suite, compilation, and a
static trace of mutation/recovery boundaries.

**Decision status:** Confirmed static code-quality/recovery review pass. Profile
ownership is now granted only by `colima_attestation_complete`; a successful
start followed by failed attestation remains manual and cannot stop or delete
the profile. Recovery re-attests the nonce-specific saved mount before owned
cleanup. Publication compares the staged manifest, artifact hashes, source
bindings, and exact canonical summary after the fault hooks and before checksum
generation and atomic rename. Manifest, provisional, and completed child
symbolic links are rejected before external mutation, request evidence remains
journal-hash-bound, and evidence rejection does not block exact owned teardown.

**Rationale:** The focused 36-test suite passes, both reviewed Python files
compile, and independent temporary-directory replays rejected all three child
symbolic links with empty external targets. No current correctness, security,
or recovery blocker was found within the V3B-1 scope. No Envoy, Colima, Docker,
image, socket, or network operation was performed.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (reviewed only; no changes)
- `tests/test_v3b1_local_envoy.py` (reviewed only; no changes)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** None for this static Task 6 gate. Runtime behavior
still requires the separately authorized live mutation/evidence gate.

**Next gate:** Proceed only through the approved live V3B-1 runtime mutation
and evidence workflow; do not infer any V3B-2 result from this static pass.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-064 — 2026-08-30 — V3B-1 installed-runtime command-contract review passed

**Input:** Perform the final narrow read-only runtime-safety review of the
latest V3B-1 controller and tests, specifically covering Colima YAML
full-comment handling, attestation-gated profile ownership and deletion,
nonce-bound saved staging mounts, installed Colima/Docker command semantics,
and all previously identified runtime blockers. Run only focused tests and the
read-only preflight; perform no live runtime mutation.

**Interpretation:** Compare the controller's exact argv and readback contracts
to locally installed Colima 0.10.3, Lima 2.2.0, and Docker CLI 29.7.2; parse an
in-memory desired-value transformation of Colima's actual generated YAML; and
trace the journal authority transition from start intent through exact
post-start attestation and recovery deletion.

**Decision status:** Confirmed static runtime-safety implementation pass. The
saved-config parser removes full-line comments before rejecting active YAML
alias/tag syntax, so Colima's generated comments containing `&&` and `!` are
accepted. Colima list memory and disk byte values are normalized to exact GiB,
the named profile config path is correct, `forwardAgent: false` and the whole
network section are checked, and no fabricated status-JSON dependency remains.
The read-only mount must be the exact lexical nonce-specific staging directory;
a resolving symbolic-link alias is rejected. Profile deletion authority is
granted only by `colima_attestation_complete`, and both initial and recovery
attestation bind the exact profile resources, saved mount/config, and nonce
ownership record. A successful start without attestation remains manual and
cannot stop or delete the profile.

**Rationale:** The focused 36-test controller suite and read-only preflight
pass. An in-memory transformation of the host's actual Colima 0.10.3 generated
config to the desired 4 CPU, 8 GiB, 60 GiB, Docker, disabled-emulation, and
nonce-mount values also passes the closed parser. Local help confirms every
used Colima and Docker flag, including the Colima network, VZ, mount, and
no-Kubernetes controls; Docker build/run/save controls; and `docker stop
--timeout`. No Colima or Docker daemon was started or stopped, and no image,
container, network, or external network operation occurred.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (reviewed only; no changes)
- `tests/test_v3b1_local_envoy.py` (reviewed only; no changes)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md` (this append-only entry)

**Unresolved questions:** No static implementation blocker remains. The live
gate must still observe named-profile YAML serialization, linux/arm64 Python
and Envoy availability, legacy-builder execution, virtiofs read-only mount
behavior, Docker inspect/health normalization, localhost-only forwarding, and
single-attempt HTTP behavior with the retry-control headers.

**Next gate:** Commit the reviewed controller and tests on a clean tree, then
run the separately authorized V3B-1 live mutation workflow. Accept evidence
only if post-start and recovery attestations, runtime object attestations,
joined outcomes, checksums, exact teardown, profile absence, and unchanged
global Docker context all pass.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-065 — 2026-08-30 — V3B-1 final evidence-publication audit found an authority-binding blocker

**Input:** Independently audit the latest Task 6 controller and focused tests
against Task 6 of the V3B-1 toolchain/HTTP-boundary plan, with particular
attention to staged and public byte binding (including `summary.md`), public
provenance closure, exact track/outcome/cardinality joins, authz-5xx semantics,
sanitization, complete checksums, atomic publication, and the
`local_envoy_boundary` claim scope. Run focused tests only and perform no live
runtime mutation.

**Interpretation:** Trace evidence from stopped-container collection through
the authoritative private provisional bundle, publication staging, public
manifest construction, checksum generation, and atomic rename. Treat the
collection-time bundle/journal binding as the authority that public artifacts
must preserve, rather than allowing publication to create a new authority from
whatever bytes happen to be present later.

**Decision status:** Static audit failed on one precise publication-provenance
blocker. `finalize_publication` correctly rechecks the staged public manifest,
artifact hash map, source attestations, exact generated summary, complete
sorted `SHA256SUMS`, and destination clobber checks after all fault hooks.
However, before copying, it does not verify the authoritative provisional
bundle's existing `SHA256SUMS` or compare that checksum-file digest with the
recorded `evidence_collect_complete.bundle_sha256` journal event. It instead
derives the public artifact map from the provisional bytes currently on disk.
Consequently, a pre-publication mutation of `requests.jsonl`, normalized
`decisions.jsonl`, or `joins.jsonl` can be adopted into a newly self-consistent
public manifest and checksum set; current source-attestation rebinding covers
raw decisions, Envoy, and target bytes but not those three derived/request
artifacts.

**Rationale:** The focused controller suite passes 36/36. Exact
`permit / permit / deny`, `200 / 200 / 403`, and `1 / 1 / 0` joins; duplicate
and retry rejection; raw `-`/normalized-null authz-5xx handling; closed
tool/engine/source provenance schemas; socket/path sanitization; exact staged
summary regeneration; complete public checksum coverage; private staging plus
atomic rename; and local-boundary claim exclusions all conform. The remaining
gap is not detected by the current staged-mutation tests because those mutate
only after the public manifest's artifact map has been constructed.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (audited only; no implementation change)
- `tests/test_v3b1_local_envoy.py` (audited only; no implementation change)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md` (this append-only entry)

**Unresolved questions:** The implementation must choose the exact durable
authority check: at minimum verify the provisional checksum set and bind its
`SHA256SUMS` digest to the collection journal event immediately before
publication. A regression should mutate each uncovered authoritative source
class before finalization and require rejection without creating the public
destination.

**Next gate:** Add the authority-binding regression and fix, rerun the focused
suite, then repeat this publication audit before any live V3B-1 mutation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-066 — 2026-08-30 — V3B-1 T-065 fix passed, post-teardown binding recovery blocked

**Input:** Independently re-audit the T-065 authority-binding fix by mutating
`requests.jsonl`, `decisions.jsonl`, and `joins.jsonl` after collection while
rewriting `SHA256SUMS`, and verify destination absence, authoritative snapshot
immutability, durable recovery binding, failure-bundle continuation, and all
prior publication/recovery invariants without live operations.

**Interpretation:** Exercise the new closed authoritative-bundle attestation at
direct finalization and recovery boundaries, then inspect crash ordering around
the post-teardown failure-bundle replacement.

**Decision status:** The T-065 publication mutation is corrected: all three
checksum-consistent mutations are rejected against the recorded full-file
attestation, no public destination is created, and the original authoritative
snapshot remains unchanged. The focused 36-test suite passes and both reviewed
Python files compile. Review nevertheless remains unapproved on one recovery
ordering blocker. After the owned profile has been deleted, an evidence
rejection causes the controller to overwrite the authoritative provisional with
a reset failure bundle, compute its new attestation, and only then journal that
replacement. A crash between the overwrite and journal event leaves the new
failure bytes on disk but only the old collection binding durable. Post-delete
recovery selects that old binding and fails re-attestation, so it cannot publish
the non-promotable failure bundle or finish journal archival.

**Rationale:** The new binding correctly prevents adoption of rewritten
evidence, but authority replacement must itself be crash-consistent. A durable
old binding plus new on-disk bytes is intentionally rejected and therefore
cannot serve as a recovery protocol without a deterministic, journal-directed
repair path or a separately staged immutable failure bundle.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (reviewed only; no changes)
- `tests/test_v3b1_local_envoy.py` (reviewed only; no changes)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Choose an atomic authority-transition design. The
smallest recovery-oriented option is to durably record failure-bundle intent,
then have post-delete recovery deterministically rebuild, attest, and journal
the failure bundle before publication. A separate immutable failure path bound
before selection would also avoid overwriting the prior authority.

**Next gate:** Add a fault injection between failure-bundle reset and durable
binding, make post-delete recovery complete safely from that state, and repeat
the focused publication/recovery audit before live mutation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-067 — 2026-08-30 — V3B-1 T-066 failure-authority recovery review passed

**Input:** Re-audit only the T-066 fix and final publication/recovery boundary,
including a crash after durable failure-replacement intent and byte replacement
but before replacement completion, while rechecking the T-065 mutation cases.

**Interpretation:** Trace and execute the post-delete two-phase replacement
protocol through deterministic reconstruction, new durable attestation,
publication, completion, and journal archival without live operations.

**Decision status:** Confirmed static review pass. The pending replacement
intent is durably closed over run ID, evidence-rejection reason, and the fixed
deterministic replacement strategy. After the injected crash, post-delete
recovery detects that exact unmatched intent, deterministically rewrites the
failure bundle, computes and journals one new authoritative attestation tied to
the intent sequence, and publishes from that authority. The stale collection
authority is not selected, no profile stop/delete command is repeated, exactly
one non-promotable destination is created, and the completed lifecycle journal
is archived with exactly one matching replacement completion. A prepared
replacement is also re-attested by finalization before publication.

**Rationale:** The focused 37-test suite and `py_compile` pass. The T-065
checksum-consistent mutations of `requests.jsonl`, `decisions.jsonl`, and
`joins.jsonl` remain rejected without a public destination and with the
authoritative source snapshot unchanged. Prior profile-ownership, symlink,
canonical-summary, checksum-completeness, atomic-rename, teardown-continuation,
and recovery invariants remain enforced. No live Envoy, Colima, Docker, image,
socket, or network operation was performed.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (reviewed only; no changes)
- `tests/test_v3b1_local_envoy.py` (reviewed only; no changes)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** None for the T-066 static recovery fix. The separately
authorized live gate remains responsible for runtime evidence.

**Next gate:** Proceed only through the approved V3B-1 live mutation/evidence
workflow; do not infer V3B-2 validation from this static pass.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-068 — 2026-08-30 — V3B-1 implementation committed; live start refused on foreign profile

**Input:** Execute Task 6 with visible progress after the static controller,
runtime-safety, evidence-publication, and crash-recovery gates pass.

**Interpretation:** Establish a clean implementation identity before any live
mutation, repeat preflight from that exact commit, then invoke `up` through the
closed lifecycle controller. Treat every non-dedicated Colima profile as
outside Task 6 ownership even when it blocks the experiment.

**Decision status:** The reviewed implementation was committed as
`c0a02f1b6153904e66adc17e9d2da4a55690b6c5` after 37 focused tests, all 252
repository tests, `py_compile`, and diff checks passed. The clean-tree
preflight passed while the pre-existing `default` Colima profile was reported
`Broken`. At the subsequent live `up` gate, `default` was reported `Running`
with the containerd runtime. The controller failed closed before creating the
dedicated profile or any Task 6 runtime resource. Readback confirmed that only
`default` exists, `kil-v3-lab` is absent, and the Task 6 active-state file is
absent.

**Rationale:** Stopping or changing the user's non-dedicated `default` profile
would exceed Task 6 ownership. The guard prevented interference with unrelated
local workloads and preserved the exact experiment precondition. A successful
static preflight is not authority to mutate a foreign profile if its state
changes before `up`.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/superpowers/plans/2026-08-30-v3b1-toolchain-http-boundary.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored visible status board
  `artifacts/generated/v3b1-task6-live-status.md`

**Unresolved questions:** May Task 6 temporarily stop the pre-existing
`default` Colima profile, or will its owner stop it before the next attempt?
The controller will not proceed while any non-dedicated profile is running.

**Next gate:** After explicit authorization or independent shutdown of
`default`, repeat clean preflight and run `up`, `run`, and `down` from the exact
implementation commit. Accept only the provisional `local_envoy_boundary`
claim if evidence joins, checksums, exact teardown, profile absence, and global
Docker-context invariants all pass.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-069 — 2026-08-30 — V3B-1 inherited-image-label review found validator recovery gap

**Input:** Independently review the live-discovered Envoy inherited-label fix,
including Docker image/runtime label merging, KIL-label ownership projection,
stopped-container recovery, pinned Envoy label fixtures, focused tests, and
Python compilation, without live operations.

**Interpretation:** Trace every inspection path for a container created from
the pinned Envoy image, not only the nine persistent runtime containers, and
reproduce Docker's `Config.Labels` result as the exact immutable image labels
merged with the controller's four managed labels.

**Decision status:** Review remains unapproved on one recovery blocker. The
persistent-container inspector correctly compares the complete container label
map to the exact immutable-image/runtime merge, rejects conflicting values and
unexpected runtime extras, returns only the four KIL ownership labels, and uses
the same rule when `require_running=False`. However, the transient Envoy
validator inspector still compares `Config.Labels` directly to the four KIL
labels and does not inspect or account for immutable Envoy labels. Replaying
the pinned fixture `org.opencontainers.image.version=22.04` plus the four
validator labels is rejected. Consequently, a validator surviving an
interrupted synchronous validation cannot be reconstructed by `down` for exact
owned teardown.

**Rationale:** Docker inherits immutable image labels for every container,
including `docker run --rm` validators. Recovery must apply the same
image/runtime merge validation before persisting the reduced KIL ownership
projection. The focused 38-test suite and `py_compile` pass, showing that this
specific transient recovery path is not covered. No Docker, Colima, image,
container, network, socket, or external network operation was performed.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (reviewed only; no changes)
- `tests/test_v3b1_local_envoy.py` (reviewed only; no changes)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md` (this append-only entry)

**Unresolved questions:** Apply `_validate_container_labels` to transient
validator inspection using the pinned immutable image's labels, retain only
the four KIL labels in recovered state, and add an interrupted-validator
recovery regression. Clarify and enforce whether the entire `kil.v3b1.` image
label namespace is reserved; the current helper rejects differing collisions
but permits same-valued or additional inherited KIL-namespace labels.

**Next gate:** Correct and test transient-validator inherited-label recovery,
resolve the KIL-namespace collision policy, rerun focused tests and compilation,
and obtain independent static approval before resuming live mutation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-070 — 2026-08-30 — V3B-1 inherited-image-label remediation independently passes

**Input:** Re-review the latest worktree after the T-069 transient-validator
finding while another specialist's remediation became visible, reproducing the
pinned Envoy image-label fixture and rerunning focused tests and compilation
without live operations.

**Interpretation:** Apply Docker's container-label contract uniformly: the
complete container `Config.Labels` map must equal immutable image labels merged
with exactly four controller-managed labels; the image may own no label in the
reserved `kil.v3b1.` namespace; persisted ownership remains only those four
managed labels; stopped persistent and transient containers use the same rule.

**Decision status:** Confirmed PASS for implementation readiness, superseding
the T-069 blocker against the newer worktree state. Both persistent-container
and transient-validator inspectors now read immutable image labels and invoke
the shared exact-merge validator. The validator rejects all immutable
`kil.v3b1.` labels and every missing, changed, or extra container label, while
both inspectors return only the four KIL ownership labels. The persistent path
applies the rule with `require_running=False`; the transient recovery path has
no running-state prerequisite and now accepts the pinned stopped-validator
fixture.

**Rationale:** The pinned fixture uses immutable
`org.opencontainers.image.version=22.04` merged with the exact validator KIL
labels and persists only the KIL projection. The focused 39-test suite and
`py_compile` pass, and diff whitespace validation passes. No Docker, Colima,
image, container, network, socket, or external network operation was
performed.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (reviewed only; no changes by this specialist)
- `tests/test_v3b1_local_envoy.py` (reviewed only; no changes by this specialist)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md` (this append-only entry)

**Unresolved questions:** Only the separately authorized live runtime gate can
confirm the pinned Envoy image's observed labels and installed Docker execution
behavior; no static label-contract blocker remains.

**Next gate:** Proceed through the approved clean preflight and live lifecycle
only when the foreign-profile ownership prerequisite is satisfied, retaining
the fail-closed readbacks and exact teardown/evidence gates.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-071 — 2026-08-30 — V3B-1 single-snapshot Docker network inspection passes

**Input:** Independently re-audit the network-inspection remediation against
Docker 29.7.2's `network inspect --format '{{json .}}'` object and exact versus
partial teardown membership semantics, without live runtime operations.

**Interpretation:** Treat one closed Docker JSON object as the only authority
for network identity, ownership, configuration, and endpoint membership. Parse
all nested objects with duplicate-key rejection; attest the network ID, fixed
name, bridge driver, boolean internal mode, and exact KIL labels; then accept
only well-shaped endpoint records whose unique names belong to the fixed track.
Require the full three-container set during runtime attestation and allow only
a subset, including empty, during resumable teardown.

**Decision status:** Confirmed PASS for static implementation readiness. The
inspector issues one `network inspect --format '{{json .}}'`, parses it through
the recursive closed-object hook, validates the expected Docker network and
five-field endpoint shapes, rejects invalid IDs or types, duplicate JSON keys,
duplicate endpoint names, unknown or cross-track names, extra labels, and
incomplete membership when completeness is required. Recovery invokes the same
inspector with partial membership enabled and compares any previously persisted
network projection before teardown.

**Rationale:** The remediation removes the former time-of-check/time-of-use
split between identity and membership inspections. The focused 40-test suite,
`py_compile`, and diff whitespace validation pass. Static fixtures cover the
Docker network object, complete membership, permitted recovery subset,
malformed internal type, duplicate membership, unknown member, and extra-label
rejections. No Docker daemon, Colima profile, image, container, network, socket,
or external network operation was performed. The Docker client executable was
not available on this shell's `PATH` or standard Homebrew locations, so no
client-side help/version probe contributed to this decision.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (reviewed only; no changes by this specialist)
- `tests/test_v3b1_local_envoy.py` (reviewed only; no changes by this specialist)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md` (this append-only entry)

**Unresolved questions:** The separately authorized live gate remains
responsible for confirming the installed engine's emitted endpoint object and
successful lifecycle behavior; no static network-inspection blocker remains.

**Next gate:** Proceed only through the approved clean live lifecycle after the
foreign-profile prerequisite is satisfied, retaining exact runtime membership
and subset-only teardown recovery checks.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-072 — 2026-08-30 — V3B-1 live attempts paused for integration-contract redesign

**Input:** Complete Task 6 live validation after authorization to pause and
restore the user's pre-existing `default` Colima profile, while showing visible
progress and using independent runtime, evidence, and recovery review.

**Interpretation:** Treat installed-runtime behavior as evidence, preserve each
failed lifecycle privately, never replay the one central request after intent,
and stop ad-hoc retrying when successive live gates expose a systemic gap
between unit fixtures and Docker/Colima integration contracts.

**Decision status:** Confirmed NO-GO for a fourth live proof cycle until a
formal V3B-1 integration-contract phase is implemented and reviewed. Three
failed runs are preserved under ignored `.tools/v3b1-failed-runs/`. No run is
accepted, promoted, or labeled validated. The user-authorized `default` Colima
profile was restored to its original `Running`, containerd, 4 CPU, 4 GiB
memory, 20 GiB disk, no-Kubernetes state. The dedicated `kil-v3-lab` profile,
all 27 containers across the three attempts, and all nine networks were removed
by exact recorded IDs; no Task 6 active lifecycle remains.

The first live attempt exposed immutable Envoy image-label inheritance. The
test-first correction now requires the exact immutable-image plus KIL runtime
label map on persistent and transient validators, reserves `kil.v3b1.*`, and
passed 39 focused and 254 repository tests before commit `5a4ab4c`. The second
attempt exposed a literal-backslash network template. The correction now uses
one closed Docker JSON network snapshot, passed 40 focused and 255 repository
tests, and was committed as `d48ead7`.

The third `up` passed and attested three internal networks, nine hardened
containers, digest-pinned Python and Envoy images, the locked KIL image, and
localhost port bindings. Its first and only baseline request then raised an
undifferentiated `OSError`; the controller persisted failure and did not retry.
Because the exception handler spans connect, send, response headers, and body
and stores no stage or errno, the archive cannot establish host-forwarding
delay, refusal, reset, timeout, or whether request bytes reached Envoy.

During `down`, all nine containers were stopped before evidence copy. Authz and
target ledgers live on tmpfs, so their precreated files were lost on stop; the
missing file therefore does not prove that no request reached authz. Collection
then aborted at the first copy error instead of preserving independent partial
legs. Exact container removals completed. The first network removal also
completed operationally, but version-specific Docker not-found prose was
classified as ambiguous before durable completion. Exact manual cleanup removed
the two remaining networks and dedicated profile before restoring `default`.

**Rationale:** The failure pattern is systemic integration-contract
incompleteness, not a single remaining local defect. Another direct patch and
live cycle would risk consuming an irreversible request before proving host
reachability and would retain teardown paths that can destroy or reject failure
evidence. Independent controller, runtime, and code-quality reviews agree on
the NO-GO.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored visible status board
  `artifacts/generated/v3b1-task6-live-status.md`
- three immutable private failed-run directories under
  `.tools/v3b1-failed-runs/`

**Unresolved questions:** The next design must specify: a bounded TCP-only
readiness gate that emits no HTTP bytes before request intent; closed sanitized
request-failure provenance; evidence freeze/copy while authz and target tmpfs
remain alive; per-leg `copied`/`missing`/`copy_error`/`malformed` status; and
inventory-based exact absence verification independent of unstable stderr.

**Next gate:** Approve and execute a formal transcript-driven V3B-1
integration-contract phase. Require a contract-only `up`/`down` smoke cycle
with zero central requests before authorizing another proof attempt. Preserve
the rule that any post-intent ambiguity is nonpromotable and never replayed.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-073 — 2026-08-30 — Demo-readiness assessment separates showcase from publication validation

**Input:** Confirm whether KIL can reach an executable demonstration and identify
the remaining work before that demonstration can be constructed and run.

**Interpretation:** Distinguish an immediately available modeled presentation,
a minimum credible live Envoy showcase, and the complete publication-grade Kind
validation. Do not make completion of the full research protocol a prerequisite
for honestly demonstrating the already-implemented KIL mechanism.

**Decision status:** Confirmed feasible. The deterministic Hugging Face replay
and V3A three-track process-contract demonstration already execute and can be
shown now with explicit `modeled` and `process_contract_only` boundaries. A live
KIL showcase becomes eligible after the formal V3B-1 integration-contract
redesign, a zero-request lifecycle smoke cycle, and one accepted local Envoy
`permit / permit / deny` proof with target markers `1 / 1 / 0`. The resulting
presenter view may claim only `local_envoy_boundary`. Full local-cluster
validation remains V3B-2; repetitions, latency, publication promotion, and
white-paper run-ID integration remain V3C/V4 work.

**Rationale:** The core signed-state, reducing-only authorization, harmless
target, Envoy configuration, lifecycle controller, evidence joiner, architecture
graphics, and modeled HTML view already exist. The blocking work is evidence
integrity at the installed-runtime boundary: non-consuming readiness, sanitized
request-stage provenance, evidence freeze before tmpfs-bearing services stop,
independent per-leg collection status, and inventory-based exact absence. These
gaps must be closed before another live proof request, but they do not invalidate
the existing modeled demonstrations or require the entire Kind/performance
program before a bounded live showcase.

**Affected artifacts:**

- `artifacts/generated/v3b1-task6-live-status.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- reviewed `docs/lab/V3-PROGRESS.md`
- reviewed `docs/superpowers/plans/2026-08-30-v3b1-toolchain-http-boundary.md`
- reviewed `docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`
- reviewed `docs/paper/kinetic-infrastructure.md`

**Unresolved questions:** Whether the first public showcase should stop at the
accepted local Envoy boundary or wait for the stronger Kind/Calico topology.
This is a presentation-scope choice, not an architectural blocker. The live
runtime cycle will again require explicit authorization to pause and restore the
pre-existing `default` Colima profile.

**Next gate:** Implement and independently review the transcript-driven V3B-1
integration contract, pass the zero-request `up`/`down` smoke cycle, then request
authorization for exactly one new central proof attempt. Construct the live
presenter view only from an accepted integrity-checked bundle; continue to
V3B-2 and V3C for publication-grade validation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-074 — 2026-08-30 — Transcript-driven harness-hardening phase approved

**Input:** Use multiple specialists to validate and repair the V3B-1 harness,
keep the work outside KIL's durable trust and authorization semantics, prove the
harness, and publish all commits so public and local repositories are fully
synchronized for offline backup.

**Interpretation:** The T-072 integration-contract redesign and T-073 minimum
live-showcase boundary are approved for execution. Parallel specialists may
audit independent harness domains, but one implementation stream owns shared
controller files. The KIL decay engine, signed composite state, authorization
decisions, Envoy enforcement policy, and target semantics are frozen.

**Decision status:** Confirmed execution gate. The design specifies three
pre-proof requirements: non-consuming three-port readiness with already-open
sockets; closed per-stage request failure provenance; and evidence freeze with
independent source status before tmpfs-bearing services stop. Docker object
absence moves from error prose to closed full-ID/name inventories. A zero-request
live smoke must pass before exactly one new central proof attempt. Publication
requires reviewed commits, GitHub merge, equal public/local `main` identities,
fresh tests, valid public checksums, and explicit separation of ignored private
failed-run evidence.

**Rationale:** Three live attempts showed that the remaining uncertainty is in
host/runtime orchestration and evidence durability, not the KIL decision model.
Freezing KIL semantics while making the harness transcript-driven allows the
lab to prove what happened without silently changing the behavior under test.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-30-v3b1-integration-contract-design.md`
- `docs/superpowers/plans/2026-08-30-v3b1-integration-contract.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- planned harness-only changes to `tools/v3b1_local_envoy.py`,
  `tools/v3b1_harness_contract.py`, fixtures, and controller tests

**Unresolved questions:** Exact historical socket errno and Docker not-found
stderr were not durably retained by the third failed run. Any reconstructed
test fixture must be labeled reconstructed; new installed-runtime behavior will
be captured exactly without raw secrets. The separate offline backup may or may
not include ignored private failed-run directories, at the user's discretion.

**Next gate:** Complete parallel read-only audits, implement Tasks 1–4 test-first
with two-stage review, pass the full static suite, then execute the zero-request
live smoke from a committed source identity.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-075 — 2026-08-30 — V3B-1 teardown now freezes all evidence before service destruction

**Input:** Implement Task 3 of the approved transcript-driven harness plan:
stop and attest all three Envoys as an ingress barrier, collect nine independent
source legs while authorization and target services remain alive, persist a
nonce-bound recoverable freeze, and allow exact cleanup to continue without
changing KIL, authorization, Envoy, or target semantics.

**Interpretation:** Evidence durability is a host-controller responsibility.
Each Envoy log and tmpfs ledger must receive its own durable intent and terminal
`copied`, `missing`, `copy_error`, or `malformed` record. Positive in-container
size/SHA-256 observation precedes every ledger copy, copied bytes are rehashed,
malformed bytes remain private and hash-bound, and no incomplete freeze may
produce joins or a promotable bundle.

**Decision status:** Confirmed Task 3 implementation complete, pending the
independent harness review and later live smoke gate. The controller now writes
all nine intents before collection, captures all stopped Envoy logs before any
ledger probe, persists all terminal records plus a collection-epoch binding,
and only then stops authorization and target containers. Recovery reattests and
skips completed legs, retries unfinished legs only against the exact recorded
live container, and never recopies a completed freeze after sources disappear.

**Rationale:** The earlier post-stop `docker cp` path could destroy tmpfs-backed
evidence before it was preserved and allowed one source failure to obscure the
others. The new ordering makes the evidence boundary explicit and durable while
keeping the enforcement behavior under test frozen. Zero-byte files require a
positive source observation and matching host copy; missing files remain
missing; byte mismatches and malformed/cardinality failures are nonpromotable.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker or Colima operation was authorized or
performed in this task. Exact installed-runtime behavior remains to be proven
by the separately gated zero-request smoke after the remaining teardown
inventory task and independent reviews are complete.

**Next gate:** Complete Task 4 inventory-based exact absence, run independent
specification and quality reviews over the complete harness, then execute the
committed zero-request lifecycle smoke before any central proof request.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-076 — 2026-08-30 — Incomplete evidence freeze integrity closed after review

**Input:** Address the Task 3 specification review findings: prevent stale
joins from surviving an incomplete freeze, totalize adversarial JSON and
record-type failures without interrupting the remaining collection legs, and
durably re-persist every copied tmpfs ledger before recording its terminal
collection status.

**Interpretation:** A previously successful provisional tree cannot contribute
any proof relation to a later incomplete collection. Only legs with terminal
`copied` status may enter the rebuilt nonpromotable provisional tree; malformed
raw bytes remain preserved and hash-bound solely in the private freeze. Parser
domain failures are evidence-quality outcomes, while filesystem and process
failures retain their distinct collection-error classification.

**Decision status:** Confirmed controller-only correction complete, pending
independent re-review and the separately gated live smoke. Incomplete trees are
reset with empty joins, retain only independently copied partial sources, and
are rejected by publication validation if joins are nonempty. Overlong JSON
integers and unhashable semantic fields now normalize through `ControllerError`
to a malformed terminal record, allowing all nine legs and cleanup to finish.
Copied ledger bytes now traverse the atomic writer, including file and parent
directory fsync, before their terminal journal event.

**Rationale:** Reusing a prior provisional directory without reset allowed
stale joins to outlive a failed recollection. Separately, Python JSON integer
limits and set membership over unhashable values could escape the controller's
closed malformed path. Finally, a successful `docker cp` did not itself prove
the destination bytes and directory entry were durably persisted before the
journal claimed collection completion.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker or Colima operation was performed.
Installed-runtime behavior remains subject to the committed zero-request smoke
and full harness review; KIL, authorization, Envoy, and target semantics remain
unchanged.

**Next gate:** Obtain independent Task 3 re-review, complete the remaining
harness tasks, then execute the zero-request live smoke from the reviewed and
committed source identity.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-077 — 2026-08-30 — Recursive malformed source parsing is totalized

**Input:** Close the final Task 3 parser-totality blocker by ensuring deeply
nested JSON cannot escape evidence collection, suppress the other eight source
legs, or prevent teardown.

**Interpretation:** `RecursionError` raised by bounded source JSON decoding,
record validation, or canonicalization is a malformed-source classification,
not a controller crash. This normalization is limited to the parser boundary;
unrelated process and filesystem failures retain their existing classifications.

**Decision status:** Confirmed harness-only correction complete, pending
independent re-review. A roughly 10,000-level nested array now becomes a
terminal `malformed` / `invalid_json` source record. Its raw target-ledger bytes,
size, and SHA-256 remain preserved, all nine collection terminals and the freeze
completion record are written, and service teardown continues.

**Rationale:** Python's JSON decoder, semantic validators, and canonicalizer can
raise `RecursionError` independently of `ValueError` and `TypeError`. Leaving it
outside the closed parser-domain exceptions allowed one adversarial but bounded
ledger record to interrupt the entire evidence freeze.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker or Colima operation was performed.
Installed-runtime behavior remains gated on the reviewed zero-request smoke;
KIL, authorization, Envoy, and target semantics remain unchanged.

**Next gate:** Independent Task 3 re-review, followed by the remaining harness
integration and committed zero-request live smoke.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-078 — 2026-08-30 — Frozen evidence bytes gain crash-safe adoption and final reattestation

**Input:** Resolve the Task 3 quality findings around the crash window between
durable source-file persistence and terminal journaling, and prevent mutated or
redirected frozen paths from entering teardown evidence.

**Interpretation:** Durable bytes and terminal interpretation are separate
state transitions. A closed, epoch-bound preterminal event must attest the
relative path, byte count, and SHA-256 after atomic persistence but before
parsing. Recovery may adopt only bytes matching that durable event. Unbound
regular bytes are preserved under a deterministic quarantine name and are
never silently deleted or claimed.

**Decision status:** Confirmed harness-only correction complete, pending
independent re-review. Each successfully matched host copy now records
`evidence_freeze_leg_bytes_persisted` before its terminal status. Recovery
single-reads and reattests bound bytes, parses them, and can finish the terminal
record without contacting an unavailable source. Teardown evidence independently
single-reads every terminal copied or malformed source through a no-follow,
regular-file, inode-stability, size, and digest check; missing and copy-error
legs contribute no consumed bytes.

**Rationale:** The former recovery path unlinked any regular file lacking a
terminal record, even when the copy had already been atomically persisted. It
also reread frozen paths into a provisional tree without comparing the terminal
copy observation, allowing post-freeze replacement or symlink redirection to
alter evidence. The new intermediate binding closes the crash window while the
final attestation makes publication fail closed and nonpromotable.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker or Colima operation was performed.
Installed-runtime behavior remains gated on the reviewed zero-request smoke;
KIL, authorization, Envoy, and target semantics remain unchanged.

**Next gate:** Independent Task 3 quality re-review, then complete harness
integration and the committed zero-request live smoke.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-079 — 2026-08-30 — Frozen-source recovery becomes collision-safe and idempotent

**Input:** Close two Task 3 recovery defects: reattest privately retained copy
mismatches, and make quarantine safe across repeated crashes, destination
collisions, and unbound symbolic links.

**Interpretation:** Whether bytes may enter a bundle is distinct from whether
their terminal integrity must be rechecked. Every terminal with a copied byte
count and digest, including size and digest mismatches, must be rehashed during
recovery; mismatch bytes remain private. An unattested active path cannot be
followed, overwritten, deleted, or terminalized in place. It must first move
atomically into a contained, collision-safe quarantine and the directory entry
must be fsynced.

**Decision status:** Confirmed harness-only correction complete, pending
independent re-review. Mismatch files now traverse the same no-follow,
single-read integrity attestation as copied and malformed sources, while still
returning no bytes to evidence construction. Quarantine destinations use a
deterministic full SHA-256 name component plus a reserved monotonic counter, so
repeated prebinding crashes preserve every generation without clobbering prior
files or symlinks. Unbound symlinks are renamed as links without following
their targets before any terminal is recorded.

**Rationale:** The earlier returnability check skipped integrity verification
for mismatch statuses. The initial single fixed quarantine name also made the
second crash cycle persist a terminal while the active unattested path still
existed. Separating attestation from bundle eligibility and reserving unique
destinations makes recovery repeatable and fail closed.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker or Colima operation was performed.
Installed-runtime behavior remains gated on the reviewed zero-request smoke;
KIL, authorization, Envoy, and target semantics remain unchanged.

**Next gate:** Independent Task 3 recovery re-review, then complete harness
integration and the committed zero-request live smoke.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-080 — 2026-08-30 — Failed Envoy freezes now quarantine durable bytes before terminal status

**Input:** Close the final Task 3 asymmetry by handling an Envoy-log error that
occurs after the atomic writer has persisted bytes but before the preterminal
byte binding is recorded.

**Interpretation:** Envoy logs and service ledgers share the same frozen-source
invariant. If either path fails after creating an unattested active file or
symbolic link, that object must move into the collision-safe quarantine and the
directory entry must be fsynced before a `copy_error` terminal can persist.

**Decision status:** Confirmed harness-only correction complete, pending
independent re-review. The Envoy post-write exception path now detects any
active regular file or symlink and invokes the same contained, no-follow,
collision-safe quarantine used for failed ledger copies. Recovery observes no
unattested active path, preserves the original bytes privately, and completes
the remaining freeze and teardown safely.

**Rationale:** Ledger collection already quarantined a partial or durably
written destination in its exception path, but Envoy collection returned a
terminal error directly. That left terminal state inconsistent with the active
filesystem and caused later recovery attestation to fail.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker or Colima operation was performed.
Installed-runtime behavior remains gated on the reviewed zero-request smoke;
KIL, authorization, Envoy, and target semantics remain unchanged.

**Next gate:** Independent Task 3 final re-review, then complete harness
integration and the committed zero-request live smoke.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-081 — 2026-08-30 — V3B-1 teardown now follows exact durable Docker inventories

**Input:** Harden and prove the local V3B-1 harness without changing durable
KIL behavior: replace stderr-derived object-existence decisions with exact
Docker inventories, make interrupted deletion replayable, cover partial-up and
validator recovery, and leave live Docker and Colima untouched until review.

**Interpretation:** Teardown authority comes only from the dedicated profile's
durable creation/removal history and a command-local, no-truncation inventory
of full object IDs paired with fixed KIL names. Error text is not evidence of
absence. A delete is safe only after an exact intent; each successful delete
must be followed by an exact survivor inventory, and a network can be removed
only after its membership is observed empty.

**Decision status:** Confirmed harness-only implementation complete, pending
independent review. Container and custom-network inventories are parsed as
bounded canonical JSONL with full 64-hex IDs and exact KIL names. Creation and
removal transitions are closed and replayed from the private lifecycle
journal. Pending-plus-absent removal is completed without a second delete;
absence without intent, ID/name drift, duplicate or shortened identities,
unexpected objects, and reappearance after completion fail closed without a
mutation. Interrupted fixed-name validators and partial-up resources are
recovered only when their durable creation intent and immutable runtime
attestation agree.

**Rationale:** Docker's human-readable stderr is not a stable state protocol,
and an ID-only set comparison cannot detect name reuse or identity drift.
Exact ID/name bijections plus durable transitions make recovery deterministic,
idempotent, and auditable. Re-inventorying both object kinds after every
ID-addressed removal prevents subsequent operations from proceeding across an
unobserved survivor set.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker or Colima operation was performed.
Installed-runtime formatting and timing remain gated on the reviewed
zero-request smoke. KIL, signed composite state, authorization, Envoy routing,
and target semantics are unchanged.

**Next gate:** Independent Task 4 specification and code-quality review, then
the committed zero-request live smoke before any accepted central proof run.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-082 — 2026-08-30 — V3B-1 recovery IDs and validators are now fully explicit

**Input:** Close four independent Task 4 review blockers without changing KIL
semantics: forbid name-only adoption during partial creation, replace implicit
validator auto-removal with an explicit lifecycle, defer absent completions
until both inventories validate together, and totalize the pure inventory
parser.

**Interpretation:** A fixed KIL name is not ownership proof. Recovery may act
only after a full object ID is durably paired with its kind and name. The two
Docker inventories form one validation observation for recovery purposes, so
no inferred completion may enter the journal until both exact survivor sets
are accepted. Validators are owned Docker objects and require the same explicit
identity, inspection, stop, removal-intent, and survivor-inventory discipline
as service containers.

**Decision status:** Confirmed harness-only corrections complete, pending
independent re-review. Pending creations no longer adopt a current name; a
present object without a persisted full ID fails closed untouched. Validators
now run detached without `--rm`, persist their returned full ID, execute under
an exact ID-bound validation intent, wait for a zero exit, attest immutable
configuration and `AutoRemove=false`, and remain available for exact teardown.
Pending absent removals, including validators, are collected without mutation,
both captured inventories are validated against exact survivors, and only then
are completion records appended. Inventory parsing now converts bounded
encoding, recursion, canonicalization, record, and final-construction failures
to `ContractError`.

**Rationale:** Name reuse, implicit Docker deletion, and partially committed
cross-inventory observations each create an unprovable ownership gap. Durable
full IDs, retained validators, and two-phase recovery preserve the evidence
needed to distinguish a completed owned mutation from replacement or ambient
state. Parser totalization keeps malformed engine output inside the closed
contract boundary.

**Affected artifacts:**

- `tools/v3b1_harness_contract.py`
- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker or Colima operation was performed.
Installed Docker formatting, validator timing, and teardown behavior remain
gated on the reviewed zero-request smoke. KIL, signed composite state,
authorization, Envoy routing, and target semantics remain unchanged.

**Next gate:** Independent Task 4 re-review, followed only after acceptance by
the committed zero-request live smoke and then the single accepted proof run.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-083 — 2026-08-30 — Incomplete V3B-1 up now has a non-evidentiary teardown path

**Input:** Correct the final Task 4 harness blocker: when `up_complete` was
never durably recorded, `down` must not attempt the nine-source evidence
freeze. It must recover and clean an exactly owned service, validator, or
network survivor without changing KIL authorization or runtime semantics.

**Interpretation:** Absence of `up_complete` is a closed lifecycle fact that
precludes an evidence claim; it is not a reason to strand resources. The
controller may use only the already-bound manifest, durable full-ID ownership
history, exact current inventories, and already-observed preflight and engine
provenance. Present container survivors still require exact identity
attestation and stop verification before the existing removal protocol runs.

**Decision status:** Confirmed harness-only correction complete, pending
independent re-review. Partial-up teardown now writes a single closed
`partial_up_evidence_rejected` event with fixed reason, false promotion status,
bounded survivor counts, and a canonical identity-set digest. A replay must
match that provenance exactly. The controller skips source freezing and does
not fabricate source attestations; it stops and reattests recovered service or
validator containers, then rejoins the existing full-ID removal, exact survivor
inventory, final-empty, and dedicated-profile deletion gates. The resulting
public bundle is explicitly incomplete and classified as a failure boundary.

**Rationale:** A nine-source freeze assumes the full runtime reached its
durable ready boundary. Applying it to a partially created topology cannot
produce complete evidence and can prevent safe cleanup. Separating the
non-evidentiary recovery path preserves teardown safety while preventing an
incomplete run from being mistaken for validated KIL behavior.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker or Colima operation was performed.
Installed-runtime recovery behavior remains gated on independent review and
the committed zero-request smoke. KIL, signed composite state, authorization,
Envoy routing, target behavior, and evidence acceptance semantics are
unchanged.

**Next gate:** Independent Task 4 re-review, then the committed zero-request
live smoke before the single accepted proof run.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-084 — 2026-08-30 — Partial V3B-1 teardown retries preserve first-observation provenance

**Input:** Make the incomplete-up teardown path retry-safe across crashes after
a removal intent, after an actual removal but before completion, after durable
removal completion, and after the final-empty inventory gate. Preserve the
initial rejection record and retain replacement-identity fail-closed behavior.

**Interpretation:** `partial_up_evidence_rejected` attests the exact survivor
set observed when incomplete-up teardown first began. It is immutable lineage,
not a checksum of the progressively shrinking survivor set. Subsequent
authorization comes from the durable full-ID creation/removal transitions and
the jointly validated current container and custom-network inventories loaded
by `_load_for_down()`.

**Decision status:** Confirmed harness-only correction complete, pending
independent re-review. A retry retains the first closed rejection event
unchanged and does not recompute or compare its identity digest against current
survivors. Pending-and-absent removal is completed only after both inventories
validate; durably completed removals remain absent; exact remaining objects are
stopped, attested, and removed by full ID; and the final-empty and profile
deletion gates remain mandatory. A same-name replacement with a different full
ID fails closed, is never sent to Docker removal, and cleanup resumes only once
the ambiguity is absent.

**Rationale:** Legitimate teardown progress necessarily changes the current
inventory. Comparing that current set to the initial rejection digest strands
owned resources after a crash and misuses historical provenance as mutable
state. Keeping the two roles separate preserves both auditability and safe,
idempotent cleanup.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker or Colima operation was performed.
Installed-runtime retry timing remains gated on independent review and the
committed zero-request smoke. KIL, signed composite state, authorization,
Envoy routing, target behavior, and evidence acceptance semantics are
unchanged.

**Next gate:** Independent Task 4 retry-safety re-review, followed by the
committed zero-request live smoke before the single accepted proof run.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-085 — 2026-08-30 — Partial-up failure replacement is authorized before profile deletion

**Input:** Close the final partial-up publication recovery gap by persisting
failure-bundle replacement intent before any profile mutation, then prove
recovery across crashes after profile delete intent, after actual profile
disappearance, and after durable delete completion but before preparation or
publication.

**Interpretation:** The partial-up rejection establishes that no promotable
source evidence exists. Before teardown can make the dedicated profile
unavailable, the journal must durably authorize the one permitted replacement:
the deterministic empty failure bundle. That intent is provenance, while the
authoritative provisional attestation can only be created later from the
materialized replacement bytes.

**Decision status:** Confirmed harness-only correction complete, pending
independent re-review. Immediately after the partial-up path sets `output` to
none, the controller writes or reuses one closed
`post_teardown_failure_bundle_intent`, bound to the run ID, fixed partial-up
rejection reason, and fixed replacement class. Its sequence precedes container,
network, and profile mutation. After verified profile absence, either the same
invocation or the absent-profile recovery path materializes the deterministic
failure provisional, derives its authoritative attestation, binds preparation
to the original intent sequence, publishes a truthful incomplete/nonpromotable
bundle, and archives the lifecycle journal.

**Rationale:** If profile deletion wins the race before replacement intent is
durable, recovery has neither source evidence nor authority to manufacture a
failure artifact and incorrectly depends on an attestation that cannot exist.
Separating early authorization from later byte attestation makes every crash
boundary recoverable without inventing evidence.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker or Colima operation was performed.
Installed-runtime deletion timing remains gated on independent review and the
committed zero-request smoke. KIL, signed composite state, authorization,
Envoy routing, target behavior, and evidence acceptance semantics are
unchanged.

**Next gate:** Independent Task 4 publication-order re-review, then the
committed zero-request live smoke before the single accepted proof run.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-086 — 2026-08-30 — Accepted V3B-1 bundles include an authoritative offline presenter

**Input:** Add the smallest deterministic offline presenter for the V3B-1
local Envoy harness without changing KIL, authorization, Envoy routing, target,
or live-runtime semantics. Make the page part of the authoritative evidence
set, and provide a read-only CLI verifier that accepts only the completed local
permit/permit/deny proof.

**Interpretation:** A demonstrator may derive presentation only from the
accepted public manifest plus canonical decision and join records. The derived
page is evidence only when its bytes are frozen before `SHA256SUMS`, included
in the authoritative and public artifact hashes, deterministically reproduced
at teardown and publication, and re-derived by an offline verifier from one
bounded snapshot of an exact closed bundle.

**Decision status:** Confirmed harness-only implementation complete, pending
independent review and the final full-suite gate. `live.html` is now a
deterministic UTF-8 page with a deny-by-default content-security policy, inline
CSS only, no scripts or external assets, escaped projected values, and fixed
`local`, `intermediate`, `not promoted`, modeled-input/observed-output, and
claim-exclusion labels. Completed evidence renders only the exact
permit/permit/deny, 200/200/403, 1/1/0 result with fixed causal reasons;
incomplete evidence renders only `INCOMPLETE · NOT PRESENTABLE`. The new
`view --bundle PATH` path executes before controller construction, performs no
writes or browser/runtime interaction, verifies the exact public file and
directory set, stable regular-file identities, checksums, closed final public
manifest, deterministic summary, canonical decision/join semantics and digest
bindings, and exact presenter bytes, then prints only the resolved presenter
path. Repaired checksums do not authorize altered claims, causal reasons,
digests, track order, summary, or page bytes.

**Rationale:** A standalone HTML file is easy to demonstrate offline, but it
must not become a second mutable source of claims. Deriving and rechecking it
from already accepted records preserves the bundle's evidence boundary while
making the result legible, portable, and checksum-complete. Closed snapshot
and semantic verification prevents a locally edited page or recomputed hash
file from being reported as an accepted run.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker, Colima, browser, KIL, Envoy, authz,
or target operation was performed. The page and verifier establish only the
already bounded local intermediate evidence claim; installed-runtime smoke and
the single accepted proof run remain separate gates.

**Next gate:** Independent Task 5b review, then the committed zero-request
smoke and single accepted proof run before public evidence publication and the
offline backup.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-087 — 2026-08-30 — Offline presenter acceptance rederives complete public evidence

**Input:** Close two Task 5b integrity gaps: the offline verifier must derive
its result from every public record and source binding, and its filesystem
snapshot must remain bound to the same directory components throughout the
read. Replace the unrecomputable public copy of the private authoritative
attestation with an explicitly recomputable, non-circular public commitment.

**Interpretation:** Checksums and a deterministic page establish byte
consistency but do not establish that requests, raw decisions, normalized
decisions, Envoy observations, target markers, joins, and source attestations
describe the same run. Likewise, `O_NOFOLLOW` on a leaf does not protect a
parent directory component replaced after enumeration. Acceptance therefore
requires one held directory-descriptor tree plus semantic rederivation from
the bytes read through that tree.

**Decision status:** Confirmed harness-only implementation complete, pending
independent re-review and the final verification gate. `view` now opens and
holds the bundle root, `raw`, and `raw/decisions` with
`O_DIRECTORY|O_NOFOLLOW`; reads every bounded regular leaf relative to the
held descriptor; and rechecks exact inventories plus file and directory
device, inode, size, modification time, and change time before acceptance.
Symlink and same-content directory replacement fail closed. From that single
snapshot it parses every canonical public JSONL record in fixed track order,
requires one raw decision per track, reproduces normalized decisions exactly,
binds source-attestation counts and hashes to the raw decision, Envoy, and
target bytes, checks immutable image and unique container identities, and
reuses the controller's join derivation for the complete request-to-target
relationship. Permitted upstreams must be canonical RFC1918 IPv4 endpoints on
port 8080; denied traffic has no upstream. Run ID must equal the declared
content-identity digest prefix, while source identity and all public metadata
are covered by the public commitment.

The public commitment algorithm is exactly SHA-256 over canonical JSON with
schema `kil.v3b1-public-commitment.v1`, containing (1) the closed public
manifest with `public_commitment_sha256` removed and (2) a sorted path-to-SHA256
map for every authoritative public file except `manifest.json` and
`SHA256SUMS`. Excluding the manifest's self-field and the checksum file removes
circularity; including all remaining files covers the deterministic summary,
presenter, public JSONL, and raw sources. The former public
`authoritative_bundle_sha256` and `private_manifest_sha256` claims were removed
because their private preimages were unavailable to an offline verifier.

**Rationale:** Repaired local hashes must not turn an incomplete or
cross-substituted record set into an accepted demonstration. Sharing the same
join derivation used to construct evidence avoids a second, weaker semantic
contract. Descriptor-relative traversal prevents validation from crossing a
swapped directory boundary, and the public-only commitment makes the claimed
bundle binding independently reproducible without exposing private host paths
or lifecycle material.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The public commitment proves internal consistency,
not publisher authenticity; external distribution still requires a trusted
Git revision, release signature, or separately conveyed checksum. No live
Docker, Colima, browser, KIL, Envoy, authz, or target operation was performed.

**Next gate:** Independent Task 5b integrity re-review, then the committed
zero-request smoke and single accepted proof run before publication and the
verified offline backup.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-088 — 2026-08-30 — Public presenter rederives the safe run identity

**Input:** Close the remaining Task 5b provenance gap by making the original
run/content identity exactly recomputable from public evidence without
publishing the host's private Docker socket path or raw execution nonce.

**Interpretation:** Merely comparing `run_id` with a claimed digest does not
prove that the digest binds the public source commit, fixed request and track
identity, profile, build inputs, and immutable image pins. The run preimage
must itself be safe to publish and must remain the one used by the harness to
derive its run ID.

**Decision status:** Confirmed harness-only implementation complete, pending
independent re-review and the final verification gate. Content identity schema
`kil.v3b1-content-identity.v2` replaces the raw Docker socket path with the
closed logical endpoint `{transport: unix, logical_locator:
colima_profile_socket, profile: kil-v3-lab}` and replaces the raw execution
nonce with its SHA-256. The private run manifest retains the exact raw
`docker_host` and `execution_nonce` as top-level runtime inputs; staging and
freeze addressing consume that private top-level nonce. The public manifest
now includes the exact safe content-identity preimage. `view` canonicalizes and
hashes it, reconstructs `run_id`, and cross-checks source commit, request ID,
fixed tracks and ports, profile/endpoint, platform, build hashes, image digests
and IDs, and KIL archive digest against the other public fields.

**Rationale:** A logical endpoint preserves the intended Colima-profile
binding while avoiding personal absolute paths. Hashing the private nonce
preserves per-execution uniqueness in the public run identity without
disclosing the staging locator. Publishing the exact remaining preimage lets
an offline verifier detect coherent source/run/content rewrites instead of
trusting an opaque digest claim.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The recomputable public identity and commitment
establish internal provenance consistency, not publisher authenticity;
distribution still requires a trusted Git revision, release signature, or
separately conveyed checksum. No live Docker, Colima, browser, KIL, Envoy,
authz, or target operation was performed.

**Next gate:** Independent Task 5b integrity re-review, then the committed
zero-request smoke and single accepted proof run before publication and the
verified offline backup.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-089 — 2026-08-30 — Close the public presenter safety boundary

**Input:** Close the final Task 5b public-boundary gaps: recursively reject
sensitive material in every public-manifest string, bound and validate the
global Docker context, require nine distinct source-container identities, and
totalize malformed source-attestation structures.

**Interpretation:** Closed top-level fields do not make nested strings public
safe, and checksums cannot make credentials, environment material, private
paths, or malformed provenance acceptable. Source identity also requires
distinct authz, target, and Envoy containers per track and across the complete
three-track run. Every untrusted JSON shape must fail as a controller error,
never as a Python traceback.

**Decision status:** Confirmed harness-only implementation complete, pending
independent re-review and the final verification gate. Publication and offline
view now share the integration contract's recursive sensitive-material scan
over keys and values. It rejects personal Unix and Windows paths, environment
records, private-key markers, GitHub and AWS credential forms, bearer tokens,
compact JWS values, the fixed lab credential, forbidden sensitive keys, and
invalid Unicode. The global context must be equal before/after, nonblank,
valid UTF-8, at most 4096 bytes, and pass the same scan. Source attestations
must be exactly three closed mappings in fixed track order; each track's three
container IDs and all nine IDs globally must be distinct. Scalar, list,
deeply nested, surrogate, and otherwise malformed source structures normalize
to `ControllerError`, including through the `view` CLI.

**Rationale:** The public manifest is an offline presentation boundary, so its
privacy and provenance rules must apply recursively rather than relying on a
small encoded-substring screen. Reusing one sanitizer prevents the transcript
and presenter contracts from drifting, while early type checks eliminate
exception paths before mapping access or canonicalization.

**Affected artifacts:**

- `tools/v3b1_harness_contract.py`
- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker, Colima, browser, KIL, Envoy, authz,
or target operation was performed. Publisher authenticity remains external to
the internally consistent public bundle.

**Next gate:** Independent Task 5b boundary re-review, then the committed
zero-request smoke and single accepted proof run before publication and the
verified offline backup.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-090 — 2026-08-30 — Harden presenter publication and verification races

**Input:** Close four final Task 5b quality gaps around atomic publication,
untrusted-manifest totality, embedded host paths, and descriptor lifetime
through offline semantic verification.

**Interpretation:** A path-based rename can publish into a replaced parent,
and validating snapshotted bytes after closing directory descriptors leaves a
post-snapshot replacement window. A failed post-rename validation must remove
the invalid final-name entry without deleting evidence, and malformed public
JSON must never escape as a Python exception.

**Decision status:** Confirmed harness-only implementation complete, pending
independent re-review and the final verification gate. Final publication opens
the private staging parent, public parent, and staged run with
`O_DIRECTORY|O_NOFOLLOW`, records device/inode identities, renames the single
leaf with `src_dir_fd`/`dst_dir_fd`, fsyncs both parents, and reattests parent,
tree, checksum, presenter, and semantic identity before returning. A failed
post-rename validation atomically moves the exact no-follow destination into a
collision-safe, device/inode-bound `.failed-publication-*` name under the
contained private staging parent, leaving the public run name free for retry.

Offline `view` now retains the root, `raw`, and `raw/decisions` descriptors and
all file identities while parsing and rederiving the presentation, then repeats
the exact directory inventory and file/tree identity checks immediately before
return. Its semantic boundary normalizes residual attribute, type, value,
Unicode, and recursion failures to `ControllerError`, with identity pin types
validated before canonicalization. The shared privacy scan additionally rejects
embedded `/private/var/folders`, `/tmp`, `/var/tmp`, and Windows user paths in
public provenance while retaining fixed safe logical URIs. Global Docker
context values are single-line as well as nonblank, bounded, and UTF-8 safe.

**Rationale:** Descriptor-relative mutation and identity-bound quarantine make
publication fail closed across parent replacement and after-rename corruption
without clobbering a later retry. Holding the snapshot through semantic use
ensures the bytes accepted by `view` still name the exact final files returned
to the operator.

**Affected artifacts:**

- `tools/v3b1_harness_contract.py`
- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker, Colima, browser, KIL, Envoy, authz,
or target operation was performed. Publisher authenticity remains external to
the internally consistent public bundle.

**Next gate:** Independent Task 5b quality re-review, then the committed
zero-request smoke and single accepted proof run before publication and the
verified offline backup.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-091 — 2026-08-30 — V3B-1 publication documentation matches the completed static harness

**Input:** Prepare the completed V3B-1 static harness and authoritative offline
presenter for a first public pull request without changing runtime behavior,
claiming a live result, exposing private paths, broadening generated-artifact
tracking, or silently selecting a license for original KIL material.

**Interpretation:** Publication readiness requires the tracked status, approved
designs, execution plans, contribution and security boundaries, and private
operator board to describe the same gate as implementation commit
`14ed92dfb1431fb2e4c3f588ff19ad07122f11fe`. Static harness and presenter
completion are implementation facts; they do not accept, promote, or validate
any of the three rejected exploratory cycles.

**Decision status:** Confirmed documentation-only alignment complete. Public
documentation now records 166 controller tests and 381 repository tests at the
reviewed implementation checkpoint, the completed transcript-driven readiness,
evidence-freeze, exact-inventory recovery and offline presenter contracts, and
the still-mandatory zero-request smoke. The fixed bearer string and
deterministic signing seeds are identified as public non-secret laboratory
fixtures. Personal Python paths were replaced with the repository virtual
environment, while synthetic `/Users/lab` adversarial fixtures remain intact.

The authoritative design now includes retained full-ID validators, joint
container/network inventory completion, retry-safe partial-up rejection and
failure-bundle ordering, safe public run identity, recursive privacy checks,
atomic presenter publication, and descriptor-held offline verification. The
generated root remains ignored: only one exact accepted run may be force-added
after `view`, checksum, and secret review; broad force-adds and standalone
`live.html` publication are prohibited.

**Rationale:** A public repository must not imply that static tests or an
offline visualization are live enforcement evidence. Aligning status and
publication instructions before the smoke prevents stale V3A-era language,
private filesystem disclosure, accidental failed-run publication, and a
presenter detached from its authoritative source bundle.

**Affected artifacts:**

- `README.md`
- `docs/lab/V3-PROGRESS.md`
- `adapters/envoy/README.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`
- `docs/superpowers/specs/2026-08-30-v3b1-integration-contract-design.md`
- `docs/superpowers/plans/2026-08-30-v3b1-integration-contract.md`
- `docs/superpowers/plans/2026-08-30-v3b1-toolchain-http-boundary.md`
- `artifacts/generated/v3b1-task6-live-status.md` (ignored private operator
  board)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No Docker, Colima, browser, KIL, authorization,
Envoy, target, or central-request operation occurred. No V3B-1 run is accepted,
promoted, or validated. Publisher authenticity remains external to the bundle,
and the explicit no-license posture for original KIL material remains unchanged
pending a separate founder and legal decision.

**Next gate:** Commit this documentation-only checkpoint, then execute exactly
one zero-request `preflight` / `up` / `down` smoke from the final committed
identity. A central request remains prohibited until the smoke bundle and exact
teardown pass review.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-092 — 2026-08-30 — Reattest publication before recovery archive

**Input:** Close the final whole-branch V3B-1 blocker in post-delete recovery:
an already-present public destination must not become archiveable merely because
its rewritten `SHA256SUMS` is internally consistent. Correct the associated
design text so it names only provenance the current harness actually records.

**Interpretation:** After the owned Colima profile is absent, the private
lifecycle journal, bound manifest, source-provenance event, publication intent,
and authoritative/prepared bundle attestation remain the recovery authority.
Checksums establish only self-consistency. Recovery must hold one no-follow
snapshot while it rederives the public bundle's semantics and compares every
publication-invariant artifact to those durable private bindings, and it must
retain journal, active state, readiness poison, and archive authority whenever
that comparison fails.

**Decision status:** Confirmed harness-only implementation complete, pending
independent re-review and the final live gate. Recovery now reconstructs the
complete/failure class and source attestations from durable lifecycle events,
requires the exact run-bound publication intent, and cross-checks the public
run/content/source/image projection against the bound private manifest. Complete
bundles run the full accepted-presenter derivation. Failure bundles run a closed
held-descriptor verifier that requires the failure class, empty source
attestations and joins, canonical bounded partial records, normalized preserved
decisions, and the deterministic nonpresentable page. Both classes compare all
JSONL, raw-decision, and `live.html` digests to the journaled authoritative
attestation and compare tool, engine, and global-context provenance to the
journal before recording publication completion or discarding recovery state.

Repaired-checksum mutations of complete and incomplete presenters, public
class/run rewrites, and clean crash-after-rename recovery are covered
test-first. Rejected recovery retains the journal, exact active state, readiness
poison, and absence of a completed archive. The design specification now states
that preflight records profile/port/tool identities; engine and global-context
provenance are captured later; the Python image digest is resolved during later
immutable-image preparation; and the current harness does not record an exact
host OS build or an explicit cryptography/library identity.

**Rationale:** A checksum an attacker can rewrite alongside altered evidence is
not an independent recovery authority. Reusing the descriptor-held presenter
semantics and binding unchanged public bytes back to the durable private
attestation prevents a post-rename crash from laundering altered evidence into
a completed archive while preserving deterministic recovery of an unchanged
publication.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker, Colima, browser, KIL, authorization,
Envoy, target, or central-request operation was performed. Publisher
authenticity remains external to the internally bound public bundle, and no
V3B-1 live result is accepted by this change.

**Next gate:** Independent review of the recovery reattestation, then the
committed zero-request smoke. Only after that smoke and exact teardown pass may
one central proof run be attempted and considered for exact-file publication.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-093 — 2026-08-30 — Close the publication-completion race

**Input:** Close the remaining TOCTOU window in both normal publication and
post-delete recovery: a public tree coherently rewritten after initial semantic
verification but before `publication_complete` must never be accepted, and its
manifest completion digest must never come from a later path-based reread.

**Interpretation:** Public checksum and semantic verification, durable
completion, and lifecycle cleanup form one transaction boundary. The public
tree descriptors and original file identities must remain held while the
controller injects the completion-boundary fault gate, rechecks the exact tree,
derives the manifest digest from the verified snapshot bytes, persists or
validates `publication_complete`, performs cleanup/archive, and rechecks the
public identities once more. A mutation before completion must occur before any
authority is discarded; a mutation during completion must leave the durable
journal authority available either active or archived.

**Decision status:** Confirmed harness-only implementation complete, pending
independent re-review and the live gate. `_public_bundle_snapshot` now exposes
closed pre-completion, durable-completion, and post-completion cleanup callbacks
inside its descriptor lifetime. It performs exact directory inventory and
file/device/inode/size/time reattestation after semantic validation, after the
completion callback, and after cleanup. Normal complete/failure publication and
complete/failure recovery derive `public_manifest_sha256` only from the held
`manifest.json` bytes. Controller cleanup and journal archival execute while
those public descriptors remain held. The prior separate path digest reads were
removed.

Four test-first regressions coherently rewrite `live.html`, the public manifest
commitment and artifact hashes, and `SHA256SUMS` at the exact post-validation
hook. Complete and failure normal publication both reject and quarantine the
invalid final leaf without recording completion. Complete and failure recovery
both reject without clearing the journal, active state, readiness poison, or
authoritative archive opportunity. Fresh static verification passes 174
controller tests and 389 repository tests.

**Rationale:** A self-consistent second path read does not prove it is the file
that passed semantic validation. Passing snapshotted bytes directly to the
durable completion callback and retaining the descriptor identity set across
completion makes the recorded digest describe the exact verified object. The
ordered rechecks prevent a coherent checksum rewrite at the completion boundary
from being mistaken for a successful publication.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/lab/V3-PROGRESS.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No live Docker, Colima, browser, KIL, authorization,
Envoy, target, or central-request operation was performed. This transaction
binds local publication completion; publisher authenticity and distribution
signing remain external gates.

**Next gate:** Independent code-quality re-review, then exactly one committed
zero-request smoke. A central request remains prohibited until that smoke and
its exact teardown/failure-bundle evidence pass review.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-094 — 2026-08-30 — V3B-1 inventory contract tests become CI-hermetic

**Input:** Correct the two failed public PR #5 CI runs without weakening the
production Docker-isolation contract. Three inventory-focused controller tests
passed locally only because the ignored repository directory
`.tools/v3b1-docker-config` already existed and was empty; a fresh CI checkout
correctly lacked it, so `_execute` failed before the injected `FakeRunner`.

**Interpretation:** These tests exercise Docker command construction, inventory
parser totality, and exact survivor ownership. Their fixture must establish the
same precondition required in production—an explicitly prepared, contained,
exactly empty Docker configuration directory—rather than depending on ambient
ignored repository state. The `_execute` isolation guard is correct and must
remain unchanged.

**Decision status:** Confirmed test-only hermetic correction complete. A shared
`ControllerContractTest` helper now creates a fresh temporary repository root,
copies the closed V3B profile, constructs the controller with an isolated home,
calls `_prepare_private_roots()`, and asserts the Docker configuration directory
is present and exactly empty. The three affected tests use that helper and
retain their original command, parser, and ownership assertions. The failure
was reproduced against a fresh temporary root before the correction and the
same isolated reproduction passes afterward.

**Rationale:** A fake command runner does not waive controller preconditions.
Provisioning the production isolation boundary inside the test fixture removes
the clean-checkout dependency while continuing to prove that Docker execution
cannot proceed with a missing or nonempty configuration root.

**Affected artifacts:**

- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The two failures were public CI test runs, not live
KIL demonstrations. No Docker, Colima, browser, KIL, authorization, Envoy,
target, or central-request operation occurred. The controller remains at 174
tests and the repository at 389 tests, so `docs/lab/V3-PROGRESS.md` requires no
count update. No V3B-1 run is accepted, promoted, or validated by this change.

**Next gate:** Commit the test-only correction, rerun the public PR checks, and
retain the prohibition on a central request until the committed zero-request
smoke passes with exact teardown and failure-bundle evidence.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-095 — 2026-08-30 — Zero-request V3B-1 smoke exposes service-ledger freeze gap

**Input:** Execute the approved zero-request `preflight` / `up` / `down` gate
from synchronized public main, publish no failed evidence, restore the foreign
runtime, and determine whether one central V3B-1 proof may proceed.

**Interpretation:** This gate tests lifecycle safety, evidence freeze, exact
ownership teardown, publication recovery, and ambient-runtime restoration. It
must never call `run` and therefore cannot establish enforcement behavior. A
passing result is intentionally incomplete and nonpromotable: all request and
downstream evidence records must remain empty while their absence is preserved
truthfully.

**Decision status:** Confirmed zero-request smoke completed but did not pass the
evidence-freeze gate from public source
commit `47c0614d49ec1a7484cdefd04cc5d080adc73ca2`. After an initial fail-closed
refusal observed the foreign `default` profile running, that profile was
temporarily stopped under the prior authorization. The single owned cycle then
created exactly three internal networks and nine attested service containers
under run
`v3b1-1db8b5914ce26e2e6c60e74124bcc1b2c9ed66b7dd68c2d3cf4ea1bc0d18c9b3`.
No request command was invoked. `down` attempted to freeze all nine source legs
before service removal and produced zero-byte request, normalized-decision,
Envoy, target, join, and three raw-decision JSONLs.

The public-safe smoke manifest is `run_complete=false`,
`promotion_status=not_promoted`, class
`intermediate_provisional_failure_local_boundary`, and records teardown
complete and verified before publication. Its manifest SHA-256 is
`24176666cc860cfe0b66a67f8a63d0f63d66b4f91329e06464b1475eb84e55c4`; its
`SHA256SUMS` file SHA-256 is
`45ed57ddf1603f965fb971cf09a22f4a1380b6cf498262f5dc8b4e63dbf043b7`.
All checksums verified. The lifecycle left no active state, readiness poison,
or active journal; nine service containers, three transient validator
containers, three networks, and only `kil-v3-lab` were removed. An escalated
host-state read confirmed the foreign `default` profile restored to Running,
containerd, arm64, 4 CPU, 4 GiB memory, and 20 GiB disk.

The durable journal records all three request states as `not_attempted`, no
readiness or request events, and nine source observations of zero bytes with
the empty SHA-256. The three Envoy legs were copied and byte-bound.
All six authorization and target ledger legs instead terminated
`copy_error(command_failed)` with no copied-byte binding, and the public
manifest consequently contains no source attestations.

**Rationale:** The request-state journal and in-container observations support
the conclusion that no central action was attempted, while exact removal and
restored foreign state demonstrate lifecycle safety. The empty failure bundle
does not independently prove authorization or target source absence because
six ledger copies failed. A central request therefore remains prohibited. The
first unmutating `up` refusal separately confirms the non-dedicated-profile
guard operates at the mutation boundary.

**Affected artifacts:**

- `README.md`
- `docs/lab/V3-PROGRESS.md`
- `docs/superpowers/plans/2026-08-30-v3b1-integration-contract.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- `artifacts/generated/v3b1-local-envoy/v3b1-1db8b5914ce26e2e6c60e74124bcc1b2c9ed66b7dd68c2d3cf4ea1bc0d18c9b3/`
  (ignored private nonpromotable smoke bundle)

**Unresolved questions:** The exact reason Docker copy failed after successful
zero-byte service-ledger probes must be corrected with a bounded byte-preserving
export, without synthesizing evidence from metadata. No enforcement result is
accepted, promoted, or validated. Kind, NetworkPolicy, historical prevention,
and production performance remain excluded. The temporary sandboxed Colima
read misreported the restored foreign profile as `Broken`; the subsequent
authorized host-level read confirmed it was running, so host-process state must
continue to be read outside the sandbox.

**Next gate:** Implement, test, review, publish, and merge the bounded exact-byte
service-ledger export correction. From synchronized public main, repeat exactly
one zero-request `preflight` / `up` / `down` smoke and require all nine source
legs to be copied and byte-bound. Only then may one central proof be attempted.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-096 — 2026-08-30 — Exact-byte service-ledger export correction is statically verified

**Input:** Correct the six authorization and target ledger copy failures exposed
by the first committed zero-request smoke without weakening the evidence-freeze
gate, reconstructing evidence from metadata, or authorizing a central request.
Also ensure generated private and public evidence summaries carry the canonical
KTP citation before checksum and commitment binding.

**Interpretation:** The existing in-container probes established that the real
service ledgers existed and were zero bytes, but a failed Docker copy left no
host-held byte binding. A safe correction must transfer the real ledger bytes
through an independent bounded path, compare them to the pre-copy observation,
and preserve all existing fail-closed and recovery behavior. It must not turn a
size and digest observation into a synthetic empty file.

**Decision status:** Confirmed implementation and static verification. After a
normal Docker copy failure, the controller may invoke a fixed no-shell Python
exporter inside the attested authorization or target container. The exporter
opens the exact ledger with `O_NOFOLLOW`, requires a stable regular inode and
size, reads no more than the 131,073-byte closed one-record limit, and emits a
canonical ASCII envelope containing the exact lowercase-hex bytes, byte count,
and SHA-256. The host bounds and parses the envelope, recomputes its digest,
requires its count and digest to equal the independent pre-copy probe, then
performs an atomic, fsynced private write and inode/digest reattestation before
the leg can be recorded as `copied`. Invalid, oversized, altered, truncated, or
failed exports leave no active frozen source and remain `copy_error`; exact
malformed bytes remain preserved and classified malformed.

Complete private, incomplete private, and public generated summaries now emit
the canonical KTP citation before `SHA256SUMS`, authoritative-attestation, and
public-commitment binding. The citation scan excludes only the two immutable
summary paths from the already-closed first smoke; future runtime summaries
remain subject to the citation requirement.

The implementation passed 180 controller tests and 396 repository tests,
Python compilation, and diff hygiene. Direct subprocess tests execute the real
exporter for empty and nonempty exact round trips and for fail-closed oversized
and symlink inputs. An independent read-only review found no Important or
Critical issue and confirmed that successful fallback status derives from the
actual service bytes rather than metadata reconstruction.

**Rationale:** The dual observation and export bindings close the gap without
changing the authority or claim model. A copied leg is earned only when actual
source bytes survive two independently parsed measurements and host-side
reattestation. The immutable prior smoke remains unchanged and nonpromotable;
the correction applies prospectively to a new public-source run.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `tests/test_document_citation.py`
- `README.md`
- `docs/lab/V3-PROGRESS.md`
- `docs/superpowers/plans/2026-08-30-v3b1-integration-contract.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The correction is statically and directly
subprocess-tested but has not yet traversed the actual Docker copy failure in a
fresh live cycle. The subprocess runner buffers output before the semantic host
bound is checked; under the present pinned trusted image and fixed exporter this
is a low residual risk, but a future hostile-container threat model should use
a hard bounded stream reader. No central enforcement result is accepted,
promoted, or validated.

**Next gate:** Commit, publish, pass public CI, merge, and synchronize the exact-
byte correction. Then repeat exactly one zero-request `preflight` / `up` /
`down` smoke from clean public main and require all nine source legs to be
copied and byte-bound before authorizing any central request.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-097 — 2026-08-30 — Pre-profile launch incompatibility is isolated and corrected

**Input:** Repeat the zero-request gate from merged public main after the exact-
byte ledger correction, preserve foreign runtime state, and do not authorize or
send a central request unless the full smoke passes.

**Interpretation:** A launch failure before profile creation is not a retry of a
central request, but it must still be treated as a durable lifecycle and closed
through the controller's recovery path. Host dependency discovery and Colima
CLI compatibility are execution prerequisites; neither may be worked around by
leaving ambiguous ownership or weakening post-start configuration attestation.

**Decision status:** Confirmed two pre-profile failures from public source
commit `20a83da1f753a681671db4a8a5c06b5f709450ba`. The first stopped at
`colima_start_intent` because the elevated host PATH did not expose the repo-
pinned Docker CLI to Colima's dependency check. Journal
`preprofile-ccc0510fbd4e62091d7c06ed927fe40b1dcfc3e29164121f0275f1a945bf766b`
records `profile_created=false` and all request states `not_attempted`; `down`
verified the dedicated profile absent and archived the lifecycle.

The second attempt used an explicit PATH containing the pinned Docker CLI and
reached Colima argument processing, where Colima v0.10.3 rejected
`--nested-virtualization=false` before profile creation. Journal
`preprofile-26e4cfbf7774d5313b7b5d0b1f2d93b12d33ea07060c2f6fef2e7c9cf3d88527`
likewise records `profile_created=false` and all requests `not_attempted`; it was
closed and archived through `down`. No KIL profile, container, network,
authorization action, target action, or central request resulted from either
attempt. The foreign `default` profile was restored and host-verified as
Running, containerd, arm64, 4 CPU, 4 GiB memory, and 20 GiB disk.

The minimal implementation correction removes only the explicit
`--nested-virtualization=false` launch argument. Colima's saved configuration is
still parsed after startup and must contain exact `nestedVirtualization: false`
before any KIL service container may deploy. The correction passed its TDD
contract test, 180 controller tests, 396 repository tests, Python compilation,
and diff hygiene.

**Rationale:** The false-valued CLI flag is redundant with the stronger post-
start saved-config attestation and is not portable across the observed Colima
launch behavior. Removing it restores compatibility without accepting an
unknown or enabled nested-virtualization state. Durable pre-profile closure and
exact foreign-runtime restoration preserve the lifecycle boundary.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `README.md`
- `docs/lab/V3-PROGRESS.md`
- `docs/superpowers/plans/2026-08-30-v3b1-integration-contract.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- `.tools/v3b1-private/completed/preprofile-*.journal.json` (ignored private
  recovery evidence)

**Unresolved questions:** The corrected command has not yet completed a real
profile start. The next smoke must verify the saved configuration before
deployment and must still prove all nine exact source legs. No enforcement
result is accepted, promoted, or validated.

**Next gate:** Commit, publish, pass CI, merge, and synchronize the Colima
compatibility correction. Then stop the foreign runtime only for one new
zero-request `preflight` / `up` / `down` smoke from clean public main. Require
saved-config attestation, nine copied and byte-bound source legs, exact teardown,
and foreign-runtime restoration before any central request.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-098 — 2026-08-30 — Corrected zero-request V3B-1 gate passes all nine source legs

**Input:** After merging the exact-byte ledger and Colima launch corrections,
repeat exactly one zero-request `preflight` / `up` / `down` lifecycle from clean
public main, restore the foreign runtime, and authorize a central request only
if every source leg is copied and byte-bound.

**Interpretation:** The gate is a lifecycle and evidence-freeze proof, not an
enforcement proof. It must create the reviewed isolated boundary, send no
request, freeze the actual empty service sources, tear down only owned objects,
publish an incomplete nonpromotable bundle, and restore the pre-existing host
state. Presenter rejection is expected because no accepted run exists.

**Decision status:** Confirmed gate passed from synchronized public source
commit `6706859d265204e0a569ebb6817d187dc1728f9d` as run
`v3b1-0374c771b23adcab64060cd8c854d12b72417ff8e4713d24e6f6a550e20bdbea`.
The saved Colima configuration attestation passed before deployment. Exactly
three isolated networks and nine service containers were created; no `run`
command, readiness event, request intent, authorization action, or target action
occurred.

All nine source terminals are `copied`: three Envoy access logs, three
authorization decision ledgers, and three target marker ledgers. For every leg,
the observed and copied byte counts are zero and both SHA-256 values equal
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
The eight public JSONL files are zero bytes and all 11 `SHA256SUMS` entries
verify. The public manifest remains correctly `run_complete=false`,
`promotion_status=not_promoted`, and
`intermediate_provisional_failure_local_boundary`, with claim exclusions for
cluster, historical-prevention, performance, and NetworkPolicy validation. Its
SHA-256 is
`bbc69830f67508d5f83055ff69ce756f4a200db5a03062744e649d813680cf60`;
the `SHA256SUMS` SHA-256 is
`a935c4a895e84c76b3e4b5294047f67d394f27bc01a7f20cb81d24031f78e753`.

Teardown removed nine services, three transient validator containers, all three
networks, and only `kil-v3-lab` before publication. The active journal, state,
and readiness poison are absent. Host-level verification confirmed the foreign
`default` profile restored to Running, containerd, arm64, 4 CPU, 4 GiB memory,
and 20 GiB disk. Offline `view --bundle` rejects this smoke as designed because
it is not an accepted local-boundary run.

**Rationale:** Unlike the first smoke, each service source now has actual copied
bytes bound to its independent observation and durable terminal status. Exact
teardown and foreign-state restoration close the lifecycle. The result therefore
authorizes one central local-boundary request sequence while establishing no
enforcement outcome by itself.

**Affected artifacts:**

- `README.md`
- `docs/lab/V3-PROGRESS.md`
- `docs/superpowers/plans/2026-08-30-v3b1-integration-contract.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- `artifacts/generated/v3b1-local-envoy/v3b1-0374c771b23adcab64060cd8c854d12b72417ff8e4713d24e6f6a550e20bdbea/`
  (ignored private nonpromotable smoke bundle)
- `.tools/v3b1-private/completed/v3b1-0374c771b23adcab64060cd8c854d12b72417ff8e4713d24e6f6a550e20bdbea.journal.json`
  (ignored private lifecycle journal)

**Unresolved questions:** No central enforcement result is yet accepted,
promoted, or validated. The next proof remains limited to the pinned local
Envoy boundary; V3B-2 cluster and NetworkPolicy behavior, historical prevention,
and production performance remain excluded.

**Next gate:** Commit and publish these public-safe smoke references, pass CI,
merge, and synchronize main. Then execute exactly one central V3B-1
`preflight` / `up` / `run` / `down` proof with no retry after request intent and
require `permit / permit / deny`, target markers `1 / 1 / 0`, complete joins,
checksums, exact teardown, restored foreign state, and presenter acceptance.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-099 — 2026-08-30 — Central proof pauses at clean pre-lifecycle shutdown boundary

**Input:** Pause the current central-proof operation at the next safe stopping
point so the host can shut down, and advise when shutdown is safe.

**Interpretation:** The only clean pause after authorization is before `up`
creates a lifecycle. Because the foreign `default` profile had just been
temporarily stopped in preparation, it must be restored and host-verified before
declaring the shutdown boundary safe.

**Decision status:** Confirmed paused before the central KIL lifecycle began.
Public main and local main are synchronized at
`229e1b774633a5f93ab1d72a4813b127345eb433`. No KIL `up`, request intent,
request, profile, container, network, authorization action, target action, or
new evidence bundle was created for the central proof. The foreign `default`
profile was restored and host-verified as Running, containerd, arm64, 4 CPU,
4 GiB memory, and 20 GiB disk. Active KIL journal, state, and readiness-poison
files are absent.

**Rationale:** Stopping before `up` preserves the no-retry central-request
contract and requires no lifecycle recovery after restart. Restoring the
foreign profile returns the host to its exact pre-proof state.

**Affected artifacts:**

- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The central local-boundary proof remains authorized
but unexecuted. No enforcement result is accepted, promoted, or validated.

**Next gate:** After restart, synchronize and verify public main, record the
foreign profile state, then resume the approved one-time central
`preflight` / `up` / `run` / `down` proof. Do not retry after request intent.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-100 — 2026-08-31 — Central proof stops before request intent; Docker suppresses the internal-network publication

**Input:** Resume the approved central V3B-1 proof after host restart, verify
GitHub authentication when requested, continue visibly, preserve the no-retry
contract, and diagnose any pre-request failure without weakening the KIL
authorization design.

**Interpretation:** A `run` invocation that fails during zero-payload TCP
readiness and before request intent is not enforcement evidence. It must be
closed as a nonpromotable lifecycle, followed by a bounded request-free
diagnostic that distinguishes the Envoy listener, Docker guest publication,
and Colima host-forward boundaries. No readiness workaround may silently alter
the KIL trust or authorization semantics.

**Decision status:** Confirmed GitHub CLI authentication was already active for
`gatekeeper454` with repository and workflow access. The authentication check
interrupted run
`v3b1-f61f5d84f7130895222ada03b51a8f494380655f7141314685e45556c9f21f` only
after `up`; it was torn down without `run`, readiness, or request intent and is
nonpromotable.

The central lifecycle from synchronized public source commit
`47e1eecf351e71ff64b404b5c75b64eb3c248fa3` was invoked once as run
`v3b1-df61bc558ba506191439f60b0b317c61c654a27aec3b8db243647f7cd3c9f21f`.
All nine service containers and three networks passed creation and running-state
attestation. Readiness then produced 115 `ECONNREFUSED` observations plus its
terminal deadline observation against `127.0.0.1:18080` over approximately
30 seconds. Every observation records that no request bytes may have been sent;
all three lifecycle requests remained `not_attempted`. `down` removed all owned
objects, published a checksum-valid nonpromotable failure bundle, and restored
the pre-existing `default` profile to its restart baseline of Stopped.

A separate request-free diagnostic lifecycle,
`v3b1-395c5ccab37d6112ade63bea0ef968fff60b3f83ea93272db5522b20ac357d53`,
proved the exact failed boundary. A zero-payload TCP connection from the track's
authorization container reached the Envoy listener at its internal address on
port 8080. Docker reported the requested
`HostConfig.PortBindings` value of `127.0.0.1:18080 -> 8080`, but the live
`NetworkSettings.Ports` entries for ports 8080 and 10000 were both null; `docker
ps` exposed no host mapping, macOS had no listening process on port 18080, and a
macOS zero-payload TCP connection was refused. The Envoy container's internal
network record also had an empty gateway, consistent with the intentionally
`--internal` Docker bridge. The diagnostic was torn down without `run`,
readiness, or request intent. Its public bundle verifies all checksums and is
nonpromotable.

**Rationale:** The failure is below KIL enforcement logic: Envoy is healthy and
reachable inside the isolated track, while Docker does not instantiate the
requested published port for the internal-only bridge. The current `up`
attestation verifies requested `HostConfig.PortBindings` but not effective
`NetworkSettings.Ports`, so it incorrectly declares the host boundary ready for
later probing. Retrying the same topology cannot produce valid evidence. The
fix must preserve per-track isolation and add an effective-boundary attestation
before any request intent.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py` (diagnosed; not yet changed)
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- `artifacts/generated/v3b1-local-envoy/v3b1-f61f5d84f7130895222ada03b51a8f494380655f7141314685e45556c9f21f/`
  (ignored private nonpromotable interruption bundle)
- `artifacts/generated/v3b1-local-envoy/v3b1-df61bc558ba506191439f60b0b317c61c654a27aec3b8db243647f7cd3c9f21f/`
  (ignored private nonpromotable readiness-failure bundle)
- `artifacts/generated/v3b1-local-envoy/v3b1-395c5ccab37d6112ade63bea0ef968fff60b3f83ea93272db5522b20ac357d53/`
  (ignored private request-free diagnostic bundle)
- `.tools/v3b1-private/completed/*.journal.json` (ignored private lifecycle
  journals)

**Unresolved questions:** The replacement request path must be selected before
implementation. Options include a dedicated in-network request driver, a
controller-owned loopback SSH forward into the internal bridge, or a second
non-internal frontend network with additional egress controls. No central
enforcement result is accepted, promoted, or validated.

**Next gate:** Approve a replacement request-boundary design that preserves the
internal per-track networks. Write and commit its focused design and execution
plan, implement it test-first, require a request-free live boundary proof, and
publish that correction before authorizing a new central enforcement sequence.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-101 — 2026-08-31 — In-network one-shot request-driver design approved and specified

**Input:** Approve the recommended replacement for the failed host publication:
a dedicated request driver inside each isolated V3B-1 track.

**Interpretation:** Approval selects the request-driver approach over an SSH
tunnel or a second non-internal frontend network. The design must remove host
publication without changing KIL trust, signed composite KTP enforcement state,
Envoy authorization, or target semantics, and it must preserve the pre-intent
zero-byte readiness and post-intent no-retry contracts.

**Decision status:** Confirmed architecture decision. Each track gains one
controller-owned, pre-created, one-shot driver container attached only to its
existing internal bridge. At `run`, all three drivers start concurrently,
connect to their fixed Envoy aliases, emit closed readiness records, and retain
their TCP connections. Only after all are ready does the controller persist one
request intent per track and transmit the bounded request instruction through
stdin. Each driver sends exactly one HTTP request, emits one non-secret closed
result, closes, and exits. Envoy has no published host port, and no driver may
restart, reconnect, or retry after request intent.

The written design also requires immutable created-state driver attestation,
four-member per-track network membership, a new content-identity schema,
closed driver-control failure provenance, exact driver lifecycle recovery,
private binding of raw driver output, public normalized response hashes, old-
bundle verification compatibility, twelve-container teardown, and a separate
request-free live driver-readiness gate before a new central proof.

**Rationale:** Moving the laboratory client inside the existing isolated track
preserves the internal-network security property that suppressed Docker host
publication. It removes the failed Colima forwarding dependency without giving
Envoy an egress-capable network or introducing a separate SSH-tunnel lifecycle.
The driver remains a transport witness and cannot become an authorization or
trust-computation component.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-31-v3b1-in-network-request-driver-design.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Implementation has not begun. The written design must
pass the user review gate, after which a test-first implementation plan will
define exact schema migrations, driver protocol fixtures, recovery tests, live
readiness-only execution, documentation/diagram updates, review, and
publication checkpoints.

**Next gate:** Commit and publish the design checkpoint for user review. After
explicit written-spec approval, create the implementation plan; do not change
production code before that approval.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-102 — 2026-08-31 — Independent review closes five request-driver design gaps

**Input:** Independently review the approved written request-driver design for
lifecycle, isolation, recovery, content-identity, and offline-evidence gaps
before committing it.

**Interpretation:** The selected in-network driver remains approved, but its
written form must prevent direct driver access to the authorization service or
target, avoid circular content identity, define whole-run failure behavior,
make readiness-only cancellation deterministic, and give the offline verifier
the actual bytes behind every claimed result binding.

**Decision status:** Confirmed five Important design issues and no Critical
issue. The corrected design now splits every track into two internal segments:
a driver/Envoy frontend and an Envoy/authorization/target backend. Envoy is the
only dual-homed component, so topology makes it the sole driver path to the
consequential services. A non-circular `driver_definition` containing only
pre-runtime facts enters content identity; Docker IDs and run-derived
names/labels remain later runtime attestations.

Any post-intent failure now aborts every later track, cancels uncommanded ready
drivers by EOF, and leaves their requests `not_attempted`. EOF before an
instruction is the sole successful readiness-only cancellation: it sends no
HTTP bytes, emits no additional stdout, exits zero, and requires a durable
`readiness_cancel_complete` record. Successful driver result records are exact,
canonical, secret-free public bundle files, checksummed and reconstructible by
the offline verifier rather than supported by opaque private-only hashes.

The closed topology is therefore twelve track containers, three validators,
and six internal networks, with exact two-member frontend and three-member
backend membership per track.

**Rationale:** These corrections keep the driver a constrained transport
witness instead of a broadly connected trusted client. They also preserve the
content-addressed run's acyclic construction, make terminal failure behavior
unambiguous, and ensure accepted public evidence can be verified without
private controller state.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-31-v3b1-in-network-request-driver-design.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The corrected design still requires user review.
Implementation details belong in the subsequent plan and must be realized
test-first without changing KIL enforcement semantics.

**Next gate:** Commit and publish the corrected design checkpoint, then obtain
explicit written-spec approval before creating or executing the implementation
plan.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-103 — 2026-08-31 — Re-review removes endpoint circularity and clarifies transient credentials

**Input:** Re-review the corrected request-driver specification after closing
the first five Important design findings.

**Interpretation:** Content identity must not depend indirectly on the
content-derived Envoy container name, and the driver must be described honestly
as transiently credential-bearing after request intent even though it has no
standing credential.

**Decision status:** Confirmed two remaining Important issues and no Critical
issue. The driver definition now uses fixed endpoint `envoy:8080`; every
isolated frontend segment assigns and separately attests the fixed per-network
alias `envoy`, independent of run-derived names and labels. Static validation
must prove that changes limited to those later runtime attestations cannot alter
the content-identity preimage.

The design now states that the authorization value and compact Q-state are
transient credentials present only in bounded driver memory after durable
request intent. They may enter only through stdin and may never appear in
arguments, environment variables, mounts, stdout, stderr, container logs,
journals, or evidence files.

**Rationale:** A fixed network-local alias closes the last content-addressing
cycle while retaining exact runtime identity attestation. Explicitly naming the
driver's transient credential boundary avoids understating its trusted handling
responsibilities and makes secret-exclusion tests enforceable.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-31-v3b1-in-network-request-driver-design.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No Critical or Important design finding is known.
The written specification still awaits the required user review checkpoint;
implementation has not begun.

**Next gate:** Run final placeholder, consistency, and diff checks; commit and
publish the design branch; then obtain explicit user approval of the written
specification before writing the implementation plan.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-104 — 2026-08-31 — Opening scope aligned with the split-network driver topology

**Input:** Perform a final independent consistency pass over the request-driver
specification after closing endpoint and credential-boundary findings.

**Interpretation:** The opening scope must name the same dedicated frontend and
backend segmentation required by the normative topology section; otherwise a
reader could implement the rejected flat-network form.

**Decision status:** Confirmed and corrected one remaining Important wording
conflict. The opening decision now requires a dedicated internal driver/Envoy
frontend segment for each track and makes the existing internal segment
backend-only, with Envoy as the sole dual-homed container. It no longer directs
the driver onto the authorization/target backend.

**Rationale:** Aligning the summary with the normative topology prevents the
primary bypass correction from being lost during implementation handoff.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-31-v3b1-in-network-request-driver-design.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No Critical or Important written-design issue remains
known. The user review and subsequent implementation-plan gates remain.

**Next gate:** Commit and publish the design checkpoint for explicit user
review. Only after approval of the written specification may the implementation
plan be created.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-105 — 2026-08-31 — Written driver specification approved; implementation plan authorized

**Input:** Approve the written request-driver specification, move immediately to
the next phase, use as many agents as useful, and prioritize a visible live lab
today.

**Interpretation:** The user approval closes the written-spec gate and
authorizes planning and test-first implementation of the selected driver
boundary. Parallel agents may map independent runtime, evidence/recovery, and
documentation/live-gate domains, but implementation remains ordered where
files and state machines overlap. A live consequential request remains gated by
the merged implementation and a passing request-free readiness lifecycle.

**Decision status:** Confirmed specification approved. PR #10 passed both CI
bootstrap jobs and is merged. Local and public main were synchronized cleanly at
`ea27be02d347f2fc089cac1edd8b506138e4a9c5` before creating branch
`codex/v3b1-in-network-request-driver`.

Three parallel read-only planning agents mapped: container/runtime topology and
interactive driver control; content identity, public evidence, offline
verification, recovery, and teardown; and the visible readiness gate,
architecture diagram, paper/demo, publication, backup, and notification
boundaries. Their results were reconciled into the test-first plan
`docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`.

The plan creates separate shared-protocol, container-executable, and host-
transport modules; preserves legacy bundle verification by schema dispatch;
implements six internal segments, twelve track containers, and three stopped
one-shot drivers; adds concurrent zero-byte readiness and deterministic EOF
cancellation; routes exactly one post-intent request through each retained
driver connection; publishes exact canonical driver results; and makes recovery
and teardown phase-aware. It then requires independent review, an implementation
PR and merge, a request-free live gate, and only then one no-retry central proof.

**Rationale:** Decomposing protocol, container, and host transport responsibilities
keeps the existing controller from absorbing another unrelated state machine.
The ordered gates provide the fastest defensible route to a visible lab while
preserving isolation, public evidence verifiability, and the no-retry boundary.

**Affected artifacts:**

- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- GitHub PR #10 and merged public main `ea27be02d347f2fc089cac1edd8b506138e4a9c5`

**Unresolved questions:** Implementation and both live gates remain unexecuted.
The offline backup still requires an explicit destination and a choice about
including ignored private failed-run evidence. No external email connector is
currently available in this execution context, so completion must not be
claimed as emailed unless that capability becomes available.

**Next gate:** Commit the implementation plan, establish an isolated worktree,
and execute Tasks 1-9 through fresh implementer plus spec and quality review
agents. After merge and synchronization, run the request-free live readiness
gate visibly; authorize the central request only if that gate passes exactly.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-106 — 2026-08-31 — Closed request-driver protocol passes specification and quality gates

**Input:** Begin the approved in-network request-driver implementation rapidly,
use parallel agents where safe, keep progress visible, and reach a demonstrable
lab today.

**Interpretation:** Task 1 must freeze the legacy public-bundle verifier before
new schemas are introduced, then establish one closed, non-circular protocol
used by the future driver, controller, and offline verifier. Parallelism is
appropriate for independent review, but corrections to the same protocol
surface remain serialized through the original implementer.

**Decision status:** Confirmed Task 1 complete after independent specification
and code-quality review. Commits `a356797c4f92e5b02e628cc3121d6e4104a487fb`,
`73c25b89ed7571b66e25a0b21b7d96a557a9dad6`, and
`07a653a46503eb2d9365b828bdc306a492fe7e54` freeze a deterministic synthetic
`kil.v3b1-public-manifest.v1` compatibility bundle; add closed driver
definition, readiness, private instruction, result, transport-failure, and
driver-control-failure contracts; and separate legacy-v1 from
driver-topology-v2 inventory parsing.

Review corrections made the inventory contracts bidirectionally reject
cross-version names, froze a platform-independent Linux errno ABI for producer
and verifier agreement, removed credential-bearing material from private parse
exceptions and their cause/context/traceback, and closed retry controls,
adversarial demonstration headers, identifiers, authorization shape, Q-state
shape, ASCII, size, and control-character rules. The frozen v1 presenter bundle
remains accepted without reinterpretation as a driver result.

**Rationale:** The driver will transiently receive signed state and an
authorization value, so its byte protocol must be smaller and more rigid than
a general HTTP-client interface. Host-independent failure semantics and
secret-free error boundaries are required for the same evidence to verify on
the Linux driver and macOS laboratory controller without leaking the private
instruction into logs or public artifacts.

**Affected artifacts:**

- `src/kil/v3b1_driver_protocol.py`
- `tools/v3b1_harness_contract.py`
- `tests/test_v3b1_request_driver.py`
- `tests/test_v3b1_local_envoy.py`
- `tests/fixtures/v3b1-request-driver-protocol.json`
- `tests/fixtures/v3b1-integration-contract.json`
- `tests/fixtures/v3b1-driver-topology-integration-contract.json`
- `tests/fixtures/v3b1-public-bundle-v1/`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Verification:** The final implementer sweep passed 413 repository tests,
protocol and harness compilation, and diff hygiene. The final independent
quality re-review passed 83 focused non-runtime tests, accepted the frozen v1
bundle, and reported no remaining Critical or Important finding. No Docker,
Colima, network, or live request was invoked.

**Unresolved questions:** The executable driver, immutable image binding,
split-network topology, attached-session lifecycle, evidence v2, recovery,
documentation, request-free readiness gate, and one central proof remain to be
implemented or executed.

**Next gate:** Implement Task 2 test-first: one retained `envoy:8080`
connection, readiness before stdin, exact EOF cancellation, one bounded
instruction and result, no reconnect or retry, bounded response consumption,
and immutable image/build-context attestation. Then repeat independent
specification and quality review before advancing schemas.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-107 — 2026-08-31 — White paper identifies its author and founder

**Input:** Add the founder's name to `kinetic-infrastructure.md` as author and
founder while the laboratory implementation continues.

**Interpretation:** The official manuscript needs visible authorship and
founder attribution in its title metadata. The repository's established Git
author identity is `Storm`, so that exact existing form is used without
inferring a longer legal or institutional name.

**Decision status:** Confirmed publication metadata change. The manuscript now
states `Author and founder: Storm` directly below the subtitle. This change does
not alter KIL architecture, protocol semantics, evidence status, or validation
claims.

**Rationale:** Prominent and unambiguous attribution preserves authorship in
Markdown, generated handouts, and future PDF renderings without coupling the
technical paper to unconfirmed affiliation details.

**Affected artifacts:**

- `docs/paper/kinetic-infrastructure.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Whether the publication form should later use a full
legal name, institutional affiliation, contact address, ORCID, or separate KTP
and KIL founder titles remains unconfirmed.

**Next gate:** Continue Task 2 of the approved V3B-1 request-driver plan. Before
final PDF publication, confirm the preferred full author byline and any
affiliation metadata.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-108 — 2026-08-31 — Founder byline refined to publication form

**Input:** A concurrent founder-owned refinement changed the newly added white-
paper byline from the repository shorthand `Storm` to `Mike Storm,
Distinguished Engineer`.

**Interpretation:** The more specific name and professional title supersede the
initial shorthand for publication display. The existing T-107 entry remains as
the historical record of the first attribution rather than being silently
rewritten.

**Decision status:** Confirmed byline refinement preserved. The manuscript now
states `Author and founder: Mike Storm, Distinguished Engineer`. The Task 2
implementation agent confirmed it did not create or inspect this unrelated
change and will not overwrite it.

**Rationale:** Preserving a concurrent founder-owned edit avoids losing the
preferred publication identity while maintaining a transparent lineage from
the initial repository-derived shorthand.

**Affected artifacts:**

- `docs/paper/kinetic-infrastructure.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Institutional affiliation, contact address, ORCID,
and whether `Distinguished Engineer` should appear on the author line or a
separate affiliation line remain optional publication decisions.

**Next gate:** Continue Task 2 and independently review its executable driver
and immutable image binding before advancing to topology schemas.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-109 — 2026-08-31 — Publication role refined from founder to creator

**Input:** A second concurrent founder-owned byline refinement changed the role
label from `Author and founder` to `Author and Creator` while retaining `Mike
Storm, Distinguished Engineer`.

**Interpretation:** `Creator` is the currently preferred publication role for
Kinetic Infrastructure. The exact user-owned Markdown wording is preserved;
the prior T-107 and T-108 entries remain as historical lineage and are not
silently rewritten.

**Decision status:** Confirmed latest byline preserved as `Author and Creator`
with the name and title `Mike Storm, Distinguished Engineer`. This metadata
change does not alter KIL architecture, protocol alignment, validation status,
or evidence claims.

**Rationale:** Authorship terminology is a founder-controlled publication
decision. Preserving the latest explicit edit avoids substituting an inferred
role while the technical implementation continues independently.

**Affected artifacts:**

- `docs/paper/kinetic-infrastructure.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Final typography may later add punctuation or place
the professional title on a separate line; affiliation, contact address, and
ORCID remain optional publication decisions.

**Next gate:** Complete Task 2 specification and quality review, then record
the executable-driver checkpoint before advancing to topology schemas.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-110 — 2026-08-31 — One-shot in-network request driver passes both review gates

**Input:** Continue the approved V3B-1 implementation toward a visible lab
today, with independent verification at each durable boundary.

**Interpretation:** Task 2 must turn the closed protocol into a container-side
client that can prove connectivity without sending a request, then reuse that
same connection for at most one consequential request. Its executed bytes must
be part of the immutable image identity before topology work begins.

**Decision status:** Confirmed Task 2 complete after specification and quality
approval. Commits `b9df1d44d828677da8191cd2ce5add195dedfe9a` and
`4203a56face5cde6690a7cad33f39f374372069a` add the one-shot driver, exact
Docker build allowlists, staged-module digest binding, and executable/container
contract tests. The driver explicitly connects once to `envoy:8080`, disables
`HTTPConnection` auto-reopen, emits and flushes readiness before reading stdin,
cancels on EOF with zero HTTP bytes, consumes at most one closed instruction,
and emits at most one closed result without reconnect or retry.

Independent quality review reproduced and corrected partial stdout writes and
premature response EOF. Canonical records now require complete bounded writes
and flush; readiness output failure prevents stdin and request activity; a
declared `Content-Length` must be fully consumed; and only OS/HTTP protocol
failures become transport evidence. Unexpected programming faults propagate to
the process-control boundary and the CLI remains silent.

**Rationale:** Readiness is an authorization-independent proof of the retained
transport path. Exact output framing and declared-body completeness are
evidence-integrity properties: neither a truncated readiness/result record nor
a truncated HTTP response may be promoted as a successful attempt.

**Affected artifacts:**

- `src/kil/v3b1_request_driver.py`
- `tests/test_v3b1_request_driver.py`
- `deploy/kind/Dockerfile.v3b`
- `deploy/kind/Dockerfile.v3b.dockerignore`
- `tools/v3b1_local_envoy.py`
- `tests/test_v3b_container_contract.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Verification:** The final implementation sweep passed 429 repository tests,
Python compilation, and diff hygiene. Independent quality re-review passed 40
focused driver/container tests and the same 429-test full suite, with no
remaining Critical or Important finding. No Docker, Colima, external network,
or live laboratory runtime was invoked.

**Unresolved questions:** The driver is not yet present in an instantiated
split-network runtime. Profile, content identity, private manifest, active
state, topology attestation, attached sessions, public evidence v2, recovery,
and both live gates remain.

**Next gate:** Execute Task 3 test-first: remove host gateway ports from the
released profile and advance content identity, manifest, and active-state
schemas to bind six name-independent segment definitions plus three
non-circular driver definitions without admitting run-derived names or IDs into
the content-identity preimage.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-111 — 2026-08-31 — Driver-era content identity and runtime projection approved

**Input:** Continue the V3B-1 implementation from the approved one-shot driver
into the profile, content-identity, private-manifest, and active-state schema
boundary.

**Interpretation:** Content identity must bind the immutable topology and driver
definitions without becoming circular or depending on generated runtime
object names. The private manifest must nevertheless derive and cross-bind the
exact future 12-container/6-network runtime projection so creation,
attestation, recovery, and teardown cannot disagree about owned objects.

**Decision status:** Confirmed Task 3 complete after specification and quality
approval. Commits `ff2a99e5a6414f1c5193cfd2639e6187406cf1f7` and
`a86e848216283146f9cc483b725dbfa8b63816aa` introduce the closed v2 profile
without host gateway ports; v2 private manifest; v3 content identity; six
canonical name-independent frontend/backend segment definitions; three
non-circular driver definitions and hashes; and explicit legacy/new private and
public schema dispatch. The legacy v1 presenter remains independently
verifiable and cannot accept driver-era fields.

Quality review reproduced acceptance of a detached runtime name that could
make creation and teardown address different objects. The corrected manifest
now deterministically derives and requires exact equality for all 12
`(track, role)` container records and six `(track, segment)` network records,
including track pointers, immutable images, approved source paths, driver
references, and run-derived name suffixes. Duplicate, missing, extra, detached,
or mismatched records fail validation. The coherent runtime projection remains
outside the content preimage, so generated-name changes cannot redefine the
immutable topology.

**Rationale:** Excluding generated runtime identities from the content hash
prevents circular identity; cross-binding them in the private manifest prevents
ownership ambiguity. Both properties are required simultaneously for safe
recovery and teardown.

**Affected artifacts:**

- `deploy/kind/v3b-profile.json`
- `src/kil/v3b_preflight.py`
- `tests/test_v3b_preflight.py`
- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Verification:** The final correction sweep passed 432 repository tests,
compilation, and diff hygiene. Independent quality re-review passed 79 focused
lifecycle, attestation, and recovery tests plus the full suite, with no
remaining Critical or Important finding. No Docker, Colima, network, or live
laboratory runtime was invoked.

**Unresolved questions:** The manifest carries the future 12/6 projection, but
runtime commands intentionally still instantiate only the transitional nine
service containers and three backend networks. A minor diagnostics issue
remains: some unhashable malformed private-manifest key values can surface as
`TypeError` rather than normalized `ControllerError`; they remain non-accepted
and cannot redirect ownership.

**Next gate:** Execute Task 4 test-first: create and attest six internal
frontend/backend networks, nine running service containers, and three stopped
drivers; make Envoy the sole dual-homed service with fixed frontend alias
`envoy`; remove all host publication; and maintain exact inventory ownership.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-112 — 2026-08-31 — Split internal topology and phase-aware ownership recovery approved

**Input:** Implement the Task 4 runtime topology rapidly but keep all work
static and independently reviewed before any Docker or laboratory execution.

**Interpretation:** The private 12-container/6-network projection must become
exact runtime commands and attestations: three isolated frontend/backend pairs,
Envoy as the sole dual-homed service, stopped one-shot drivers, no host
publication, exact full-ID ownership, and recovery that remains safe at every
possible frontend-attachment crash point.

**Decision status:** Confirmed Task 4 complete after specification and repeated
quality review. Commits `74e1a3da1da3c9d4f90022e9ce95a0421557cf0c`,
`cb1e5ec2fb55d66852ed8429ffb85e3f92ec4ffd`,
`5571d5cd0207da5c6f3f3db41be7d3ddad789d90`, and
`67a1a79698d1e9346dfa4055688f5d8fea579910` implement six internal bridge
segments; nine running authz/target/Envoy services; three stopped, stdin-open,
mountless drivers; three transient validators; and zero host-published ports.
Envoy starts on its backend and is attached by exact full IDs to its frontend
under durable connect intent/completion with the fixed `envoy` alias.

Review corrections added direct attestation of privilege, primary network,
PID/IPC/UTS/user/cgroup namespaces for persistent and validator containers;
pinned private cgroup namespaces; rejected malformed raw inspect shapes before
normalization; closed alias upper bounds so only Envoy owns the reserved
frontend alias; bound exact network full-ID-to-name membership; and expanded
pure teardown to the exact 15-container/6-network owned inventory.

The final recovery correction derives per-track `unstarted`, `pending`, or
`complete` Envoy attachment state from durable journal events and recorded full
IDs. Unstarted accepts backend-only and rejects unjournaled frontend
attachment. Pending accepts exactly backend-only or the exact dual-homed shape.
Complete requires exact dual-homing. The same phase object reaches load,
state/runtime reverify, evidence freeze, stop, pre-removal reinspection, and
network membership validation.

**Rationale:** Runtime isolation is meaningful only when observed state, not
command intent, proves the boundary. Phase-aware exact-ID recovery prevents
both stranded owned objects and silent acceptance of mutations that were never
durably journaled.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tools/v3b1_harness_contract.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Verification:** The final implementation sweep passed 105 focused lifecycle
tests, 193 local-Envoy tests, and 437 repository tests plus compilation and diff
hygiene. Independent quality re-review passed 83 focused recovery/contract
tests and the full 437-test suite with no remaining Critical or Important
finding. No Docker, Colima, network, or live laboratory runtime was invoked.

**Unresolved questions:** The stopped drivers have not yet been started through
attached control sessions. Readiness records, deterministic EOF cancellation,
diagnostic-only lifecycle state, request sequencing, driver evidence, and both
live gates remain unimplemented or unexecuted.

**Next gate:** Execute Task 5 test-first: start all three exact stopped drivers
through attached sessions, require all readiness records under one deadline,
provide a request-free `readiness-only` lifecycle that sends EOF and proves
zero request intent/HTTP bytes, and poison the lifecycle on malformed output or
nonzero cancellation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-113 — 2026-08-31 — Request-free attached-driver readiness lifecycle approved

**Input:** Continue from the approved split topology into an observable but
request-free driver lifecycle before permitting any consequential lab traffic.

**Interpretation:** All three stopped drivers must start through exact attached
processes before the controller waits on any one of them. One common deadline,
closed readiness records, deterministic EOF cancellation, exact cleanup, and a
permanent diagnostic-only lifecycle must prove the transport path without
creating request intent or sending HTTP bytes.

**Decision status:** Confirmed Task 5 complete after specification and quality
approval. Commits `3c6424d049bdb4c9680572ae864334578f0bfa67`,
`11bea32429b31ef91b0cfd41892f5dd7975db735`, and
`94c76fffc07810d18bdd69f8748f86efd74af324` add the bounded host transport
adapter, exact `docker start --attach --interactive <full-id>` sessions, the
`readiness` CLI lifecycle, closed v2 driver-lifecycle fixture records, and
failure cleanup/replay hardening. Legacy v1 integration fixtures remain
unchanged and reject driver-era records.

All three processes start before any readiness read. One common monotonic
deadline governs selector and non-file-descriptor streams. Success requires an
exact readiness schema/status for each bound full ID and track, then EOF to all
stdin streams, no later stdout or stderr, and zero exits. Requests remain
`not_attempted`; no instruction or request intent is created; the lifecycle is
durably diagnostic-only and `run` is forbidden until `down`.

Review corrections added bounded terminate/kill/reap cleanup, exact primary
failure attribution before each mutation, independent first-failure poison,
replay rejection after any incomplete prior readiness session, controller-
scoped aggregate failures, strict readiness schema discrimination, and exact
container-state inspection before stop decisions. Local attached-client exit
is never treated as proof the driver container stopped. Exact-ID stop and
post-stop reinspection proceed even when cleanup journaling fails, while raw
stdout/stderr and persistence exception text remain excluded.

**Rationale:** A request-free readiness run is valuable only if failure cannot
leave a retained credential-capable socket or permit a second attempt. The
controller must prove process, container, journal, and diagnostic state as one
closed lifecycle while sending zero consequential traffic.

**Affected artifacts:**

- `tools/v3b1_driver_transport.py`
- `tools/v3b1_local_envoy.py`
- `tools/v3b1_harness_contract.py`
- `tests/test_v3b1_local_envoy.py`
- `tests/fixtures/v3b1-driver-topology-integration-contract.json`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Verification:** The final implementation sweep passed 21 readiness tests,
150 focused lifecycle tests, 459 repository tests, compilation, diff hygiene,
and a real OS-pipe selector smoke test. Independent quality re-review passed
215 local-Envoy tests and manually confirmed terminal-plus-poison double-fault
cleanup/replay behavior, with no remaining Critical or Important finding. No
Docker, Colima, network, or live laboratory runtime was invoked.

**Unresolved questions:** Task 6 has not yet replaced the legacy direct-host
request path with driver instructions. Driver result evidence, phase-aware
post-request recovery/teardown, documentation, the request-free live run, and
the one accepted central proof remain.

**Next gate:** Execute Task 6 test-first: after all three readiness records are
durable, write exactly one bounded canonical instruction per track under a
durable request intent, collect one closed result, abort later tracks after any
post-intent failure, and never reconnect, restart, replace, or retry a driver.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-114 — 2026-08-31 — One-shot in-network request sequencing approved

**Input:** Replace the remaining host-controller HTTP request path with the
approved one-shot instruction/result exchange through the retained in-network
drivers, while keeping the implementation static until later live gates.

**Interpretation:** Aggregate driver readiness must precede every request.
Signed state may be issued only afterward and immediately before its bound
instruction. Durable request and instruction intent must precede the only stdin
write. Every result, exit, persistence boundary, later-driver cancellation,
and failure provenance must be terminal, secret-free, exact-ID-bound, and
non-retryable.

**Decision status:** Confirmed Task 6 complete after specification and quality
approval. Commits `ac8568aa45dd3794e1be3f949393c45ed63e2656`,
`935dbc86eedcdec755087dffa6e9e92e588f4948`,
`5de1394c555152c9d8a990626e17fa75b6c472b0`, and
`22ba6a3135e4ed7afb52a852fb8292868d6d6f45` remove the host gateway
connection/reset/direct-request path and route the three fixed tracks through
their retained attached drivers in order: credential baseline, signed state,
and signed state plus local reduction.

All three readiness records become durable before Q-state issuance. Per track,
the controller persists request intent and instruction-write intent, writes one
bounded canonical instruction, closes stdin, reads one bounded closed result,
attests exact terminal output/exit, persists the private 0600 raw result,
persists normalized request v2, and completes the request attempt. Bearer and
Q-state values exist only in the bounded in-memory stdin payload after intent;
they never enter commands, environment, mounts, stdout/stderr, journal, or
public evidence.

Review corrections introduced one outer session-ownership guard over all
post-readiness setup and persistence; shared the robust readiness poison and
cleanup core between diagnostic readiness and run; guarded real clock and
persistence exceptions after the durable session boundary; restored equivalent
driver-era coverage for relevant removed host tests; conservatively set
post-intent sent provenance true; preserved exact protocol-owned Linux errno
facts independent of macOS; bound raw result digest, driver definition, full
ID, and track; classified real waits as `process_wait` and output/exit integrity
as `termination`; and made later-driver cancellation use fresh bounded cleanup
deadlines with ordered, consumed, durable outcomes.

**Rationale:** Once instruction delivery begins, the system can no longer prove
that zero bytes crossed the socket. Conservative sent provenance, one owner for
all ready sessions, and exact terminal evidence prevent a partial attempt from
being retried or presented as a clean comparison.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tools/v3b1_driver_transport.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Verification:** The final implementation sweep passed 112 focused request,
readiness, journal, teardown, and driver tests plus 442 repository tests,
compilation, diff hygiene, host-path absence, and secret-containment audits.
Independent quality re-review passed 53 focused tests and the full suite with
no remaining Critical or Important finding. No Docker, Colima, network, or
live laboratory runtime was invoked.

**Unresolved questions:** Exact driver result files remain private and are not
yet incorporated into the public v2 bundle, commitment, offline verifier, or
presenter. Broader post-request recovery/teardown hardening, documentation,
implementation merge, request-free live gate, and one accepted proof remain.

**Next gate:** Execute Task 7 test-first: publish exact canonical driver result
files, bind their hashes and driver facts into request v2 and public commitment,
dispatch v1/v2 verification without hybrid acceptance, and update the presenter
to show `request driver -> Envoy -> authorization -> target or withhold` with no
host publication and explicit transport-witness scope.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-115 — 2026-08-31 — Exact driver evidence and private-public projection approved

**Input:** Bind the three one-shot in-network driver results into the v2
evidence bundle and derived presenter while preserving the frozen v1 evidence
contract, secret boundaries, and the distinction between a transport witness
and KIL enforcement.

**Interpretation:** Every commanded track must publish its exact canonical
driver-result bytes, and those bytes must be joined to the normalized request,
driver definition, full container identity, track, Envoy, authorization,
target, request ID, decision digest, commitment, checksums, manifest, and
offline authority decision. A v1 bundle must reject driver-era files; a v2
bundle must require all three results for acceptance. Private provisional
evidence must remain contained even if directory entries are replaced during
publication.

**Decision status:** Confirmed Task 7 complete after final specification and
quality approval. Commits `b0cb37e`, `8d38c5c`, `6d72875`, and `f167ea7` add
the three exact `raw/drivers/<track>.json` files, explicit v1/v2 writer and
verifier dispatch, deterministic nonpromotable failure reconstruction, public
commitment and checksum bindings, and the v2 presenter statements:
`request driver -> Envoy -> authorization -> target or withhold`, `No host
publication`, `The driver is a laboratory transport witness, not KIL
enforcement`, and `Evidence scope: local_envoy_boundary`.

Review corrections closed a live `run()` to `collect()` handoff that omitted
the required private driver sources, rejected dangling and pre-existing
symlink ancestry, and replaced path-reopened private writes with a held
`O_DIRECTORY | O_NOFOLLOW` descriptor transaction. Accepted, failure, and
resumed publication now use descriptor-relative bounded reads, atomic writes,
checksums, inventories, and final device/inode re-attestation for the `raw` and
`drivers` directory-swap matrix. The independent reviewer also injected swaps
during active writes; every case failed closed with zero outside writes.

**Rationale:** The driver can support an authoritative laboratory claim only
when its exact output is public, independently rehashed, and joined to the
other enforcement evidence. The private-to-public projection is itself a
security boundary, so validation that can be invalidated between checking and
writing would undermine the evidence even when the final verifier later
rejects it.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Verification:** The final implementation and independent re-reviews passed
74 focused Task 7 tests, 210 local-Envoy tests, and the full 454-test
non-runtime repository suite. Compilation, diff hygiene, CSP and secret scans,
the accepted/failure/resume by raw/drivers swap matrix, and the frozen v1
fixture and presenter bytes all passed. The worktree was clean. No Docker,
Colima, network, or live laboratory runtime was invoked.

**Unresolved questions:** Post-start driver state has not yet been made
phase-aware for recovery and teardown. The request-free live gate, one central
proof, future Kind/Calico V3B-2 validation, historical prevention, and
production performance remain unexecuted and unclaimed.

**Next gate:** Execute Task 8 test-first: accept only exact created drivers
before start intent, never start or command a driver during recovery, require
trusted terminal or exact stop/re-attestation before any Envoy stop, preserve
the nine authoritative service sources, and prove all fifteen containers and
six networks absent through durable exact-ID teardown.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-116 — 2026-08-31 — Driver-aware recovery and exact teardown approved

**Input:** Make partial-up, post-readiness, post-request, and crash recovery
aware of the retained one-shot request drivers without ever replaying a start,
attach, instruction, or request, and make all teardown paths prove the complete
driver-era topology absent before publishing evidence.

**Interpretation:** The persisted ownership snapshot remains the exact
created-state baseline. Live driver state is admitted only through closed,
journal-derived phases. A persisted driver result or clean readiness
cancellation proves output termination; Docker-client cleanup proves only the
client was reaped; stop and cleanup completions prove teardown quiescence only.
Every ambiguous post-start driver remains nonpromotable but must still be
stopped and removed through its recorded full ID. Pure and imperative teardown
must share the same driver-first authority and role ordering.

**Decision status:** Confirmed Task 8 complete after final specification and
quality approval. Commits `75161f0` and `48bd81a` add phase-scoped immutable
driver attestation, a zero-restart recovery gate, conservative closure of
stranded request intents, crash-idempotent exact driver stopping, exact
frontend membership shrink, driver finalization before Envoy shutdown, the
unchanged nine-service-source freeze, shared teardown ordering, and exact
driver/Envoy/authz/target/validator/network removal.

The final publication gate recomputes one durable commitment for all twelve
manifest containers, three validators, and six manifest networks from the
validated manifest plus exact creation and removal transitions. It requires
unique full IDs and names, exact cardinalities and digests, empty survivor
inventories, and one matching `topology_absence_attested` event before any
complete-run publication action. The reconstruction no longer depends on the
active-state file, so a crash after state unlink but before journal archival
can validate, complete exactly once, and recover.

Review corrections established real end-to-end partial-up and full `down()`
proofs; separated attached-client cleanup from container termination; aligned
the pure planner with imperative teardown; gated normal, provisional, renamed,
and post-delete publication paths; and covered stop, absence, state-unlink,
and journal-archive crash boundaries. The serialized public harness v1/v2
schemas remain unchanged because the new facts are private recovery-journal
records.

**Rationale:** Driver-era recovery is safe only when journal phase determines
which live states may be inspected and cleaned, never which actions may be
replayed. Evidence is durable only when a complete-run publication is
cryptographically and procedurally downstream of exact absence for every
owned runtime object, including across the cleanup crash window.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Verification:** Final implementation and independent re-reviews passed 222
local-Envoy tests, 38 teardown-continuation tests, seven focused correction
proofs, and the full 466-test non-runtime repository suite. Compilation and
diff hygiene passed. The exact partial-up survivor, immutable mutation matrix,
full 12-plus-3 container/six-network fake runtime, missing and mismatched proof
suppression, post-delete recovery, and state-unlink-to-journal-archive crash
tests all passed. The worktree was clean. No Docker, Colima, network, or live
laboratory runtime was invoked.

**Unresolved questions:** The driver mechanism and teardown are implemented
and statically approved but not yet exercised in the live dedicated profile.
Request-free readiness, the one central proof, future Kind/Calico V3B-2,
historical prevention, and production performance remain pending or unclaimed.

**Next gate:** Execute Task 9: update all current-facing documentation, the
white paper, the local-Envoy architecture SVG, the hybrid two-timescale HTML,
progress state, supersession notes, and the ignored live board so every asset
describes the implemented six-network driver topology and labels both live
gates as pending. Then pass the complete static documentation and code gate.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-117 — 2026-08-31 — Driver-era publication set reaches the final static review gate

**Input:** Unify the repository overview, controller and Envoy guidance, lab
status, Kinetic Infrastructure paper, architecture visuals, superseded design
records, and local live board around the approved V3B-1 in-network request
driver without overstating an unexecuted live result or erasing pre-driver
history.

**Interpretation:** Current-facing material must distinguish Docker
attach/stdin host control from consequential `driver -> Envoy -> authorization
-> target or withhold` traffic; show three fixed tracks over six internal
networks; identify Envoy as the sole dual-homed component; bind three driver
results and nine service sources; keep the driver a transport witness rather
than KIL enforcement; and make request-free readiness the prerequisite for one
central proof. The credential-policy baseline remains the no-signed-state
control, while only the two KIL tracks consume signed composite KTP state.

**Decision status:** Proposed publication checkpoint ready for final quality
re-review. The narrative set now reports the Task 8 implementation checkpoint
as 466 tests and the fresh Task 9 complete static gate as 474 tests. It preserves
the founder-approved opening and exact `**Author and Creator** Mike Storm,
Distinguished Engineer` byline. Detailed nine-service/three-network smoke and
launch records remain in a labeled historical pre-driver section and cannot be
promoted to the current six-network contract. The older 2026-08-29 design and
2026-08-30 plan retain byte-identical original prefixes followed by append-only
supersession notes linking the approved 2026-08-31 driver design and plan.

The local-Envoy SVG now separates host control, per-track frontend and backend
networks, the two signed-state KIL tracks, baseline control, and two independent
evidence inputs joined before verification. The hybrid two-timescale source
remains a passive inline fragment; a passive, self-contained UTF-8 standalone
publication wrapper provides durable desktop and narrow-width rendering. The
paper links the standalone hybrid architecture and embeds the local-Envoy SVG.
Both visuals separate current V3B-1 from future Kind/Calico V3B-2 and retain the
canonical KTP citation.

**Rationale:** Static implementation and historical development records answer
different evidentiary questions. A unified publication must show exactly what
is built and statically proved while keeping live acceptance, historical
prevention, performance, Kubernetes, and NetworkPolicy claims outside the
current evidence boundary.

**Affected artifacts:**

- `README.md`
- `tools/README.md`
- `adapters/envoy/README.md`
- `docs/lab/V3-PROGRESS.md`
- `docs/paper/kinetic-infrastructure.md`
- `docs/architecture/v3-envoy-live-validation.svg`
- `docs/design-drafts/hybrid-two-timescale-architecture.html`
- `docs/architecture/hybrid-two-timescale-architecture.html`
- `docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`
- `docs/superpowers/plans/2026-08-30-v3b1-integration-contract.md`
- `tests/test_v3b1_documentation.py`
- ignored `artifacts/generated/v3b1-task6-live-status.md`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Verification:** Eight new documentation regressions and sixteen focused
documentation, citation, canonical-semantics, and consultation tests pass. The
request-driver suite passes 28 tests; preflight, container, and local-Envoy
modules pass 246 tests; the complete repository passes 474 tests. Python
compilation, `make validate`, SVG XML parsing, passive-content checks, citation
and historical-prefix checks, ignored-board hermeticity, and diff hygiene pass.
The standalone hybrid wrapper was visually inspected at 1440 and 360 pixels;
the SVG was rendered and inspected after evidence-arrow correction. No Docker,
Colima, network, or live laboratory runtime was invoked.

**Unresolved questions:** Independent final quality approval remains pending.
The request-free live gate and one conditional central proof are unexecuted.
Future Kind/Calico V3B-2, historical prevention, repetition, and production
performance remain unvalidated or unclaimed.

**Next gate:** Obtain final Task 9 specification and quality approval, commit
the tracked publication set while leaving the live board ignored, publish and
merge the correction, synchronize local and public main, then execute exactly
one request-free `preflight -> up -> readiness -> down` lifecycle.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-118 — 2026-08-31 — Unified V3B-1 publication set passes both review gates

**Input:** Final independent specification and quality re-review of the Task 9
publication set after correcting track semantics, evidence-flow geometry,
standalone visualization rendering, test hermeticity, and plan inventory.

**Interpretation:** Publication readiness requires both semantic agreement and
durable presentation: the baseline must remain the credential-policy control;
only the two KIL tracks consume signed composite KTP state; driver results and
service sources must join as independent evidence; the paper must render or
link both architecture views; and a clean clone must pass without the ignored
local live board.

**Decision status:** Confirmed Task 9 approved. Independent specification and
quality reviewers found no remaining Critical or Important issue. The tracked
publication set is ready to commit. The ignored live status board remains local
and untracked by design.

**Rationale:** The lab can advance only from a public record that accurately
states what is implemented, what has merely passed static verification, and
what remains contingent on live evidence.

**Affected artifacts:** The Task 9 artifacts enumerated in T-117, plus this
final approval record and the completed Task 9 plan checkboxes.

**Verification:** Sixteen focused publication, citation, canonical-semantics,
and consultation tests and the full 474-test repository suite pass. Python
compilation, `make validate`, SVG XML parsing, passive-content and clean-clone
hermeticity checks, visual inspection at desktop and 360-pixel widths, secret
and private-path review, and diff hygiene pass. No Docker, Colima, network, or
live laboratory runtime was invoked.

**Unresolved questions:** Request-free live readiness and one conditional
central local-Envoy proof remain unexecuted. V3B-2 Kind/Calico, historical
prevention, repetition, and production performance remain outside the present
claim boundary.

**Next gate:** Commit and publish Task 9, require CI and merge, synchronize
local and public main, then execute exactly one request-free live
`preflight -> up -> readiness -> down` lifecycle with visible status updates.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-119 — 2026-08-31 — First driver-era live gate stops at a closed Docker null-network representation

**Input:** After PR #11 merged, synchronize local, origin, and GitHub `main`,
then execute the Task 10 request-free live gate visibly from the exact
published commit without invoking the central `run` command.

**Interpretation:** The gate must preserve the pre-existing host state, pass
preflight, create only the dedicated local runtime, obtain three driver
readiness records, cancel all three drivers without instructions, and tear down
exactly. Any failure after runtime mutation must preserve the first error,
forbid request traffic, and enter bounded recovery rather than retrying the
experiment.

**Decision status:** Confirmed rejected first live attempt; narrow correction
approved but not yet published. PR #11 merged as
`81758e82a60a3eea0758c5ef4660b3d8b6f2b7a5`; both required GitHub bootstrap
checks passed, and local `main`, `origin/main`, and GitHub `main` matched that
commit with clean primary and feature worktrees. The host inventory contained
only the stopped foreign `default` profile with containerd, aarch64, 4 CPU,
4 GiB memory, and 20 GiB disk.

The first preflight stopped before mutation because the ignored local tool lock
still bound the pre-driver profile SHA-256
`8d6da1c20bf0def2ab5495dc5c87586b99d0ef024cd6c42236b2dc8bfd4afe62`
instead of published profile-v2 SHA-256
`567fb0472c596d651e79ce6457f3f3929a9712776058900499b4d377233c3399`.
All three source URLs, executable digests, modes, and live versions remained
exact. The canonical `make v3b-tools` installer refreshed the ignored binding;
fresh verification passed with unchanged executable digests, no tracked
change, and no runtime mutation. Lifecycle preflight then passed.

`up` created and attested only the dedicated Colima boundary through manifest
persistence, then stopped while inspecting the first exited Envoy validator
with `Envoy validator immutable/sandbox attestation failed`. The mandatory
single `down` preserved the same failure and left the isolated runtime
untouched. Read-only inspection established the root cause: Docker 29.7.2
represents an exited container created with `--network none` as
`HostConfig.NetworkMode = "none"` plus one closed
`NetworkSettings.Networks["none"]` record. The controller admitted only the
older empty `{}` representation even though the observed record had no
endpoint, address, gateway, MAC, alias, link, DNS, IPAM, driver option, port
binding, or published port. The validator exited zero and every other immutable
property matched.

The isolated correction commit
`89d52a60635defb590ade0589b5209b62162b711` admits only the exact closed
Docker null-network sentinel or legacy `{}`, requires a lowercase 64-hex null
network ID and empty/zero/null connectivity fields with exact types, rejects
missing, extra, custom, populated, or malformed network state, and canonicalizes
both accepted forms back to `{}`. It does not weaken the authoritative
`NetworkMode = "none"`, no-binding, no-publication, immutable-image, identity,
mount, namespace, capability, or read-only-root requirements.

**Rationale:** A Docker API representation difference is not evidence of
connectivity, but permissive normalization could hide a real attachment. A
closed, typed sentinel contract preserves fail-closed sandbox attestation and
deterministic recovery equality while allowing the exact pinned runtime output
actually observed in the lab.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored `artifacts/generated/v3b1-task6-live-status.md`
- ignored local `.tools/locks/v3b-tools.json`
- private lifecycle `v3b1-e81dc498e2ef1693640b56a7b04575c8ff5a788cb931e371bf7087830de129b7`

**Verification:** The exact observed Docker 29.7.2 record reproduced the prior
failure before the correction and passed afterward. Nineteen malformed or
connected variants remain rejected. Independent specification and
quality/security reviews approved the correction with no Critical or Important
finding. Eight runtime-attestation tests, 222 local-Envoy tests, and the full
474-test repository suite pass; Python compilation and diff hygiene pass. No
`readiness`, driver instruction, request intent, HTTP action, evidence
promotion, or central `run` occurred.

**Unresolved questions:** The correction must pass public CI and merge before
it may govern recovery. The currently isolated dedicated profile contains only
the exited first validator and must be removed through the corrected bounded
recovery path. The complete request-free lifecycle, three clean cancellations,
nine empty authoritative source copies, checksum verification, exact teardown,
foreign-state restoration, and the later one-shot central proof remain pending.

**Next gate:** Publish and merge the closed null-network correction, synchronize
all `main` references, execute bounded recovery for the rejected attempt, and
verify exact profile and foreign-state restoration. Then start one fresh
request-free `preflight -> up -> readiness -> down` lifecycle from the new
published commit. Do not invoke the central `run` command unless that fresh gate
passes and its public-safe record is merged.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-120 — 2026-08-31 — Driver healthcheck attestation binds Docker disablement to the immutable image

**Input:** After the closed Docker null-network correction merged and bounded
recovery restored the host exactly, execute one fresh Task 10 request-free
`preflight -> up -> readiness -> down` lifecycle from corrected public `main`.

**Interpretation:** The fresh gate must remain request-free and fail closed on
any live runtime record that does not match its immutable definition. If Docker
represents a requested runtime override by replacing one field while retaining
immutable fields, acceptance must bind the complete observed record to the
already-attested immutable image rather than adding a permissive value test.

**Decision status:** Confirmed rejected second live attempt; corrected
healthcheck contract independently approved but not yet published. The first
rejected lifecycle `v3b1-e81dc498e2ef1693640b56a7b04575c8ff5a788cb931e371bf7087830de129b7`
was recovered by merged correction `397b524f97995f95b7a8c4b24840e132faa9105b`.
Its dedicated profile was removed, the stopped foreign `default` profile and
resources were restored exactly, active journal/state/poison were absent, all
failure-bundle checksums passed, and all request, decision, Envoy, target, and
join files were zero bytes.

Fresh preflight then passed from `397b524f97995f95b7a8c4b24840e132faa9105b`.
`up` validated all three Envoy configurations, created six internal networks
and twelve service/driver containers, connected each Envoy to its frontend,
then failed closed with `driver runtime definition attestation failed`. The
mandatory single `down` preserved the same primary failure. No driver was
started; no readiness record, instruction, request intent, HTTP action, or
central `run` occurred.

Read-only inspection of rejected lifecycle
`v3b1-05211715589b45f79dac4ebe5700004831c07b28af7ca42bce5111db47007801`
showed the driver correctly created with `--no-healthcheck`, open stdin, no
TTY, created state, exact command, fixed frontend network, and no host
publication. Docker 29.7.2 replaced the immutable image healthcheck `Test`
with `["NONE"]` but retained the image's `Interval`, `Timeout`, `StartPeriod`,
and `Retries`. The controller recognized only a synthetic one-field
`{"Test":["NONE"]}` record and therefore mislabeled the live disabled record as
configured.

Correction commits `9f31ccc83502d38318744db8e085451797a29155` and
`80ca1fe9c4d8a36c15b0e62709a27918cee1f7ac` now classify a driver healthcheck
as disabled only when the runtime object has exactly the five pinned fields,
`Test` is exactly `["NONE"]`, every retained scalar has an exact integer type
and value match to the immutable image record, and that immutable record is
itself a closed active `CMD` or `CMD-SHELL` healthcheck with valid values. An
initial compatibility proposal retained the unbound one-field form;
specification review rejected it as an Important gap. The final correction
removes that path and proves the singleton fails both with valid and missing
immutable metadata. Service health and readiness requirements remain
unchanged.

**Rationale:** `--no-healthcheck` is a runtime override, not authority to
discard provenance. Deriving the sole accepted disabled form from the exact
immutable image prevents missing, extra, changed, malformed, or type-confused
fields from masquerading as the pinned driver contract and preserves strict
recovery equality.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored `artifacts/generated/v3b1-task6-live-status.md`
- private lifecycle `v3b1-05211715589b45f79dac4ebe5700004831c07b28af7ca42bce5111db47007801`

**Verification:** The exact Docker 29.7.2 expanded disabled record reproduced
the prior driver-attestation failure before the correction and passed after it.
Closed negative cases reject missing, extra, changed, wrong-type, Boolean,
non-`NONE`, malformed-image, and unbound-singleton records. Independent
specification and quality/security reviews approved the final correction with
no remaining Critical or Important finding. Ten runtime-attestation tests, 224
local-Envoy tests, and the complete 476-test repository suite pass; Python
compilation, `make validate`, worktree cleanliness, and diff hygiene pass.

**Unresolved questions:** The correction must pass public CI and merge before
it may govern recovery. The dedicated profile for the rejected second attempt
is isolated in a broken status with the durable journal and owned objects left
untouched. Corrected bounded recovery, exact foreign-state restoration, the
complete request-free gate, three clean cancellations, nine empty source
copies, and the later one-shot central proof remain pending.

**Next gate:** Publish and merge the image-bound healthcheck correction,
synchronize every `main` reference, and execute bounded recovery for the
rejected second attempt. Verify exact object/profile absence and foreign-state
restoration, then start one new request-free lifecycle from that merged commit.
The central `run` command remains prohibited until a complete Task 10 record is
public, reviewed, merged, and synchronized.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-121 — 2026-08-31 — Created driver attachment is distinct from a materialized frontend endpoint

**Input:** After PR #13 merged the image-bound disabled-healthcheck contract,
resume bounded recovery of rejected Task 10 lifecycle
`v3b1-05211715589b45f79dac4ebe5700004831c07b28af7ca42bce5111db47007801`
without starting a driver or invoking readiness, an instruction, a request
intent, an HTTP action, or the central `run` command.

**Interpretation:** Docker's container-side network configuration and its
network-side physical endpoint inventory are related but not identical. A
never-started driver in exact `created` state may be configured for the exact
same-track frontend and alias while its endpoint IDs and addresses remain
unrealized and the frontend network's `Containers` map contains only Envoy.
Recovery must distinguish that closed state from a missing, cross-track, or
post-start endpoint.

**Decision status:** Confirmed rejected recovery attempt; narrow correction
implemented and locally verified but not yet published. PR #13 merged as
`1c4707b6c5cec0049399e15584f61618625a1b48`, its required CI checks passed,
and local `main`, `origin/main`, and GitHub `main` were synchronized and clean.
The corrected `down` re-attested the owned Colima profile, then failed closed
before any removal transition with `cross-track or incomplete frontend network
membership`.

Read-only inspection proved the same state on all three tracks. Every driver
remained never-started in `created` state with exact full ID, name, image,
labels, fixed frontend name and alias, and empty endpoint/network/address
fields. Each corresponding frontend network contained exactly the journal-
bound Envoy full ID and name and no driver endpoint. All six network identities,
all twelve service/driver identities, all three retained validator identities,
and the durable journal remained intact. There were zero driver-start,
instruction, request-intent, HTTP, removal, or central-run transitions.

The isolated correction makes frontend physical membership singular and
state-derived: an exactly attested `created` driver is omitted because its
endpoint is not materialized; `running`, `exited`, or `dead` requires the exact
same-track driver endpoint. Malformed or missing driver runtime state fails
closed. Envoy attachment phases remain journal-bound, backend membership stays
exact, and unknown, cross-track, missing required, or extra members remain
rejected. Reverification now derives membership from the freshly inspected
container records rather than persisted pre-readiness state, so an executed
driver cannot later inherit the created-state omission.

The first PR #14 CI pair exposed an independent pre-existing test-fixture
race: one runner failed and its twin stalled in
`test_non_fileno_blocking_read_uses_common_deadline_and_cleans_up`. The test
used a 0.5-second host-scheduler join to infer success before proving that its
synthetic blocking read had started. The fixture now exposes exact
`all_started` and `read_started` events, waits boundedly for those causal
milestones, and only then evaluates the controller's simulated common
deadline. Production transport and deadline behavior are unchanged.

**Rationale:** Treating configured attachment as physical membership made the
pinned Docker representation impossible to recover, while broadly permitting
subsets would hide real topology drift. Binding the sole accepted physical
shape to a fresh, exact driver lifecycle state preserves the configured
network/alias attestation and full-ID ownership while matching the runtime's
actual endpoint lifecycle.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `README.md`
- `adapters/envoy/README.md`
- `tools/README.md`
- `docs/lab/V3-PROGRESS.md`
- `docs/superpowers/specs/2026-08-31-v3b1-in-network-request-driver-design.md`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/architecture/v3-envoy-live-validation.svg`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored `artifacts/generated/v3b1-task6-live-status.md`
- private rejected lifecycle `v3b1-05211715589b45f79dac4ebe5700004831c07b28af7ca42bce5111db47007801`

**Verification:** The exact live mismatch was independently reproduced by
three read-only audits. A RED regression first showed that complete Envoy
attachment plus a created driver incorrectly required the unrealized driver
endpoint. The corrected state table proves `created -> {Envoy}` and
`running|exited|dead -> {driver, Envoy}`, rejects invalid states, and proves
active reverification uses fresh exited state instead of the persisted created
record. All 29 controller-contract tests and all 226 local-Envoy tests pass.
Independent specification and quality reviews approved the correction with no
Critical or Important finding. All 478 repository tests, Python compilation,
and diff hygiene passed before publication. The scheduler-sensitive deadline
test passes 20 consecutive event-synchronized repetitions, and the full
478-test repository suite plus diff hygiene pass again after that fixture-only
correction. Public CI must rerun on the new commit.

**Unresolved questions:** The correction must pass public CI, merge, and
synchronize before it may touch the isolated runtime. Bounded recovery must
then prove exact evidence classification, checksum validity, complete
owned-object/profile
absence, no active journal/state/poison, and exact restoration of the foreign
stopped `default` profile. The fresh request-free Task 10 lifecycle and later
central proof remain pending.

**Next gate:** Publish and merge the state-aware endpoint correction,
synchronize all `main` references, and resume only the bounded `down`. If
recovery and foreign-state restoration pass, start a fresh request-free
`preflight -> up -> readiness -> down`
lifecycle. The central `run` command remains prohibited until that gate's
public-safe record is reviewed and merged.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-122 — 2026-08-31 — Controlled service stop preserves the no-publication invariant across Docker port normalization

**Input:** After PR #14 merged as
`7677052f6fd2b4287f419dc01ec9a1a859191777`, synchronize every `main`
reference and resume only the bounded `down` for rejected Task 10 lifecycle
`v3b1-05211715589b45f79dac4ebe5700004831c07b28af7ca42bce5111db47007801`.
Do not start a driver or invoke readiness, an instruction, a request intent, an
HTTP action, or the central `run` command.

**Interpretation:** Docker 29.7.2 represents exposed-but-unpublished service
ports differently across an exact stop. While running, the three fixed KIL
service roles report `{"8080/tcp":null}` for authorization and target services
and `{"10000/tcp":null}` for Envoy. After a controlled stop, Docker reports
`{}`. Both shapes prove the same no-host-publication invariant, but the recovery
comparator previously permitted only the concurrent `running -> exited|dead`
state change.

**Decision status:** Confirmed rejected recovery attempt; narrow correction
implemented and locally verified but not yet published. The merged recovery
re-attested the complete owned topology, retained all three never-started
drivers in exact `created` state, durably classified the partial-up evidence as
nonpromotable, and stopped only the baseline Envoy. Docker returned exit code
zero, then the controller failed closed with
`container changed after exact stop` before writing the stop-complete event or
touching another container.

Read-only inspection proved the stopped Envoy differed from its pre-stop
normalized attestation in exactly two lifecycle fields: `state` changed from
`running` to `exited`, and `published_ports` changed from
`{"10000/tcp":null}` to `{}`. The other 34 normalized runtime fields remained
unchanged. All six running authorization/target services retained their exact
unbound `{"8080/tcp":null}` projection, both sibling Envoys retained
`{"10000/tcp":null}`, all three drivers remained never-started, all three
validators remained exited, and the six networks remained owned and bounded.
The foreign stopped `default` profile was unchanged. Every request state
remained `not_attempted`; no driver start, instruction, request intent, HTTP
action, removal, or central-run transition occurred.

The correction totalizes only this one-way controlled-stop representation. It
requires a non-driver service transition from `running` to `exited|dead`, exact
top-level identity, and exact equality for every runtime field except `state`
and `published_ports`. The sole non-equal port alternatives are the role-bound
running projections `authz|target -> {"8080/tcp":null}` and
`envoy -> {"10000/tcp":null}` becoming exactly `{}`. Host bindings, wrong
ports, reverse or same-state changes, drivers, and every additional field
change remain rejected. Persisted live inspection is not rewritten.

**Rationale:** An empty map and a fixed exposed-port map with null bindings both
mean that no host port exists. Treating their Docker stop-time representation
as equivalent prevents cleanup from deadlocking after an owned exact stop,
while role-bound port literals and equality of every other attested field keep
the exception narrower than a general semantic relaxation.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `docs/lab/V3-PROGRESS.md`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored `artifacts/generated/v3b1-task6-live-status.md`
- private rejected lifecycle `v3b1-05211715589b45f79dac4ebe5700004831c07b28af7ca42bce5111db47007801`

**Verification:** A RED comparator test first reproduced the live rejection; a
second RED mutation proved that a generic all-null port collapse was too broad.
The corrected unit matrix accepts the three exact role-bound service shapes
only during controlled stop and rejects disabled stop authority, a still-running
container, a host binding, wrong pre-stop or post-stop ports, unrelated network
drift, and missing, unknown, or unhashable roles. The last case first reproduced
a `TypeError`; the final exact-string guard totalizes it to rejection. A
controller-level regression records exactly one stop intent and one stop
completion for the accepted transition, while the network-drift twin retains
only the stop intent and raises the original fail-closed error. Independent
read-only runtime audit confirmed that no other normalized field changed.
Independent specification and quality/security reviews approved the final
correction with no Critical or Important finding. All 228 local-Envoy
controller tests, the complete 480-test repository suite, `make validate`,
Python compilation, and diff hygiene pass.

**Unresolved questions:** The correction must pass public CI, merge, and
synchronization before it may govern the remaining teardown. The isolated
runtime still contains one cleanly stopped Envoy, eight running services, three
created drivers, three exited validators, and six internal networks. Exact
object/profile absence, foreign-state restoration, the fresh request-free gate,
three clean cancellations, nine empty source copies, and the later one-shot
central proof remain pending.

**Next gate:** Publish and merge the role-bound stopped-port correction,
synchronize all `main` references, update the live board, and resume only the
bounded `down`. If exact recovery and foreign-state restoration pass, start one
fresh request-free `preflight -> up -> readiness -> down` lifecycle. The
central `run` command remains prohibited until that gate's public-safe record
is reviewed, merged, and synchronized.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-123 — 2026-08-31 — Physical network membership is derived from fresh running state during exact recovery

**Input:** After PR #15 merged as
`3dce7cbd0153716b9e52cae791b97f50131989f7`, synchronize `main` and resume
only the bounded `down` for rejected Task 10 lifecycle
`v3b1-05211715589b45f79dac4ebe5700004831c07b28af7ca42bce5111db47007801`.
Keep all request drivers unstarted and prohibit readiness, instruction,
request-intent, HTTP, and central `run` transitions.

**Interpretation:** Docker network configuration and Docker's physical endpoint
inventory are distinct facts. A container remains configured for its networks
after it stops, but Docker removes that stopped container from each network's
`.Containers` map. Logical ownership therefore remains the exact configured
topology, while physical membership must be reconstructed from fresh container
state: only a `running` role contributes an endpoint.

**Decision status:** Confirmed rejected recovery and locally verified narrow
correction; publication is pending. The PR #15 recovery wrote only the exact
Colima recovery attestation at journal sequence 75, then failed closed before
another lifecycle mutation with `cross-track or incomplete frontend network
membership`. Read-only inspection showed the stopped baseline Envoy absent
from both of its physical network inventories. Its backend contained only the
running authorization and target services and its frontend was empty. The two
untouched tracks retained their running Envoy, authorization, and target
backend endpoints and their Envoy-only frontend endpoints. All drivers
remained never-started in `created` state, all request states remained
`not_attempted`, and journal sequence 74 remained the sole pending baseline
Envoy stop intent.

The correction preserves `_network_member_identities` as the exact logical
ownership projection and derives physical membership only from a fresh,
closed runtime attestation whose state is one of `created`, `running`,
`exited`, or `dead`. `running` contributes the exact full-ID endpoint;
`created`, `exited`, and `dead` contribute none. Missing, malformed, paused,
unknown, cross-track, extra, or stale endpoints fail closed. The journal-bound
Envoy identity and attachment phase remain mandatory even when the Envoy is
stopped.

Controlled service stopping is now exact and replayable. Stop intent is bound
to the prior exact creation and role; completion is bound to its exact intent.
The replay matrix permits `unstarted/running`, `pending/running`,
`pending/stopped`, and `complete/stopped` recovery without duplicating an
intent or stop, while `complete/running` fails closed. The pending sequence-74
baseline stop will therefore be completed without a second Docker stop.

Independent review identified one important stale-snapshot issue before
publication: teardown stopped services, but its later removal projection still
used pre-stop runtime attestations. The final implementation freshly
re-inspects every post-stop driver, service, and validator before the first
removal, exact-compares those attestations, uses that fresh set for network
projection, and re-inspects each candidate again immediately before exact
removal. This ensures stopped Envoy endpoints are absent from the projected
physical topology and prevents a state change from inheriting stale authority.

**Rationale:** Accepting any configured member as a physical endpoint makes
recovery impossible after a legitimate exact stop; accepting arbitrary
subsets would conceal topology drift. Deriving the sole accepted physical
shape from fresh, closed, exact runtime state matches Docker's endpoint
lifecycle while preserving journal-bound ownership, full-ID identity, fixed
same-track aliases, and fail-closed rejection of every unmodeled shape. This
entry supersedes only T-121's provisional claim that exited or dead drivers
remain physical members; their configured ownership remains, but their
physical endpoints are absent.

**Affected artifacts:**

- `tools/v3b1_local_envoy.py`
- `tests/test_v3b1_local_envoy.py`
- `README.md`
- `adapters/envoy/README.md`
- `tools/README.md`
- `docs/lab/V3-PROGRESS.md`
- `docs/superpowers/specs/2026-08-31-v3b1-in-network-request-driver-design.md`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/architecture/v3-envoy-live-validation.svg`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored `artifacts/generated/v3b1-task6-live-status.md`
- private rejected lifecycle `v3b1-05211715589b45f79dac4ebe5700004831c07b28af7ca42bce5111db47007801`

**Verification:** The observed stopped-baseline shape is covered directly:
backend `{authz, target}` and empty frontend. State-table tests prove that only
running drivers and services contribute endpoints, invalid states fail closed,
and stale stopped endpoints are rejected. Stop-history tests prove exact
creation binding, closed fields, identity and role stability, duplicate and
orphan rejection, and the five replay rows. A complete-down regression derives
network membership independently from the freshly transitioned service state
and first failed before the post-stop refresh was implemented. The corrected
implementation passes all 232 local controller tests and all 484 repository
tests through `make validate`; Python bytecode compilation and diff hygiene
also pass. Three independent specification, ledger/replay, and documentation/
test reviews report no Critical or Important finding after the stale-snapshot
correction.

**Unresolved questions:** The correction must pass public CI, merge, and exact
local/remote synchronization before governing the live runtime. One bounded
recovery `down` must then prove complete owned container/network/profile
absence, exact evidence classification and checksums, no residual active
state or poison, and restoration of the foreign stopped `default` profile.
The fresh request-free Task 10 lifecycle and its public gate record remain
pending.

**Next gate:** Publish the stopped-endpoint correction, merge it only after
both public CI jobs pass, synchronize all `main` references, update the visible
live board, and execute exactly one bounded recovery `down`. Only after clean
recovery may a fresh request-free `preflight -> up -> readiness -> down`
lifecycle begin. The central `run` command remains prohibited until that gate
record is public, reviewed, merged, and synchronized.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-124 — 2026-08-31 — Driver-era request-free Task 10 gate passes from merged stopped-endpoint source

**Input:** PR #16 was merged after both required public CI jobs passed. Confirm
GitHub, `origin/main`, and local `main` at the exact merge commit; rerun the
complete merged static gate; perform the single bounded recovery `down`; then,
only if recovery proves exact absence and foreign-state restoration, execute one
fresh request-free `preflight -> up -> readiness -> down` lifecycle. Do not
invoke the central `run` command.

**Interpretation:** Task 10 is a lifecycle, topology, readiness, evidence-
freeze, teardown, and restoration gate. Its intentional absence of a
consequential request means a passing result must remain incomplete,
provisional, and nonpromotable. It cannot establish an enforcement result,
historical prevention, Kind/Calico or NetworkPolicy behavior, repetition, or
performance.

**Decision status:** Confirmed Task 10 request-free live gate passed at the
local Envoy boundary; public-safe gate record implemented and locally verified,
independently reviewed with no remaining Critical, Important, or Minor finding,
but not yet published. PR #16 merged as
`a46e8dc98a1af64ceadb5700e91c2f87840564fe`; both GitHub `bootstrap` jobs
reported `SUCCESS`, and GitHub's merge commit, `origin/main`, and local `main`
were exact. The merged source passed all 484 then-current repository tests.
The central `run` was not executed and remains prohibited until the Task 10
record is reviewed, merged through public CI, and synchronized.

The one bounded recovery of rejected lifecycle
`v3b1-05211715589b45f79dac4ebe5700004831c07b28af7ca42bce5111db47007801`
completed without a retry. Its archived journal records 15 exact container
removals, six exact network removals, dedicated profile deletion verified, and
no request-side event. Its public bundle is correctly classified
`intermediate_provisional_failure_local_boundary`, `run_complete=false`, and
`not_promoted`; every request, decision, Envoy, target, join, raw-decision, and
raw-driver file is zero bytes and every checksum verifies. Active state, active
journal, and readiness poison were absent. The public manifest binds the
foreign context name as `default` before and after; a post-recovery readback
observed `Stopped/containerd/aarch64/4 CPU/4 GiB/20 GiB`, but the exact resource
tuple was not durably bound at both boundaries.

Fresh preflight passed with the three fixed ports free, exact pinned tool
identities, clean merged source, and only that foreign stopped profile. Fresh
up and request-free readiness then produced run
`v3b1-d2b26f6c8136dcd26a6e6727b9bb1381076a1e03b71a5a44df9b2b2ef9db6cf9`
from the exact merge commit. All three tracks produced exact readiness records
and three clean cancellations. The archived 185-event journal contains three
driver starts, three readiness completions, three cancellation completions,
zero instruction/request events, nine terminal source collections, nine
persisted evidence-freeze legs, 15 container removals, six network removals,
and an explicit zero-survivor topology attestation.

The resulting public-safe bundle is bound by public commitment
`18bfe97801cfb5f43774c68581da58576147e698f05d56dfac53cc7fa1097da7`
and manifest SHA-256
`e7dfc3e371a3057152850b196005753b40bafd384fd470b3d501bffa34d0acae`.
All eleven request-side and raw-source files are zero bytes and bind to the
empty SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
Every `SHA256SUMS` entry verifies. Teardown was complete and verified before
publication; active state, active journal, and readiness poison were absent;
and the dedicated profile was absent. The public manifest binds the foreign
context name as `default` before and after. A post-run readback observed its
stopped resource tuple, but the exact resource tuple was not durably bound at
both boundaries and therefore is not cryptographic restoration proof.

**Rationale:** Passing request-free readiness before a central proof separates
transport/lifecycle safety from enforcement behavior. It proves that all three
in-network witnesses can become ready together and be cancelled without
instruction, that zero-request evidence is preserved rather than synthesized,
and that teardown preserves the bound foreign context name while recording a
post-run profile observation. Exact foreign-resource restoration remains
unproven because the before-resource tuple was not durably bound. Keeping the
bundle incomplete and nonpromotable prevents this safety gate from being
mislabeled as an authorization result.

**Affected artifacts:**

- `docs/lab/V3B1-TASK10-REQUEST-FREE-GATE.md`
- `docs/lab/V3-PROGRESS.md`
- `README.md`
- `tests/test_v3b1_documentation.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored `artifacts/generated/v3b1-task6-live-status.md`
- ignored bundle `artifacts/generated/v3b1-local-envoy/v3b1-d2b26f6c8136dcd26a6e6727b9bb1381076a1e03b71a5a44df9b2b2ef9db6cf9/`
- private archived journal `.tools/v3b1-private/completed/v3b1-d2b26f6c8136dcd26a6e6727b9bb1381076a1e03b71a5a44df9b2b2ef9db6cf9.journal.json`

**Verification:** The public-safe record was developed test-first: its binding
and claim-boundary test failed while the record and current status were absent,
then passed after the exact source/run/commitment/manifest identifiers,
readiness/cancellation counts, 15-by-6 absence proof, zero-request facts, and
central-run prohibition were recorded. Independent review then corrected the
draft's restoration language: only the context name is bound before and after;
the exact resource tuple was operator-observed after the run but not durably
bound at both boundaries. All 485 repository tests pass through `make validate`,
including citation enforcement and diff hygiene. Read-only post-run checks
independently verified every public checksum, zero-byte source size, active-
state absence, exact local/remote merge equality, and the sole foreign Colima
profile's post-run stopped resource tuple.

**Unresolved questions:** The Task 10 public-safe record still requires public
CI, merge, and exact local/remote synchronization. The central proof has not
been executed.
Before it can execute, a controller and public-evidence extension must durably
bind exact before/after foreign-resource snapshots and the offline verifier
must require their exact equality; that prerequisite remains unimplemented.
Its no-retry request boundary, exact three-result join, target-marker outcomes,
teardown, and presenter acceptance remain unobserved.

**Next gate:** Review and publish the Task 10 record. Only after both public CI
jobs pass and the record is merged and synchronized may the project implement,
test, review, merge, and synchronize exact before/after foreign-resource
snapshot binding and verifier equality. Only after that prerequisite may one
fresh central `preflight -> up -> run -> down` proof execute. No retry is
permitted after request intent. The prospective outcome remains `permit / permit / deny`, HTTP
`200 / 200 / 403`, and target markers `1 / 1 / 0` with exact joins, checksums,
teardown, foreign-state restoration, and offline presenter acceptance.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-125 — 2026-09-02 — Apache-2.0 selected for original KIL material

**Input:** The maintainer directed implementation of GitHub issue #18's
recommendation to select and apply a license for KIL original material. The
issue recommends Apache License 2.0 and requires a root license file, updated
notice, package metadata, README declaration, and a green validation gate.

**Interpretation:** Apply Apache-2.0 to original KIL material while preserving
the separate KTP attribution and the repository's byte-preserved treatment of
the two historical drafts. This is a repository licensing and publication
change; it does not alter KTP protocol semantics, implementation behavior,
scenario evidence, or laboratory state.

**Decision status:** Confirmed implementation. Apache License 2.0 is the
selected license for original KIL material. Package metadata points to the
root license text, and public repository documentation states the same choice.

**Rationale:** Apache-2.0 matches the KTP repository's license, provides an
express patent grant, and removes the prior no-license condition that blocked
reuse and prospective upstream contribution. Retaining explicit KTP citation
and historical-draft provenance keeps licensing distinct from authorship and
source lineage.

**Affected artifacts:**

- `LICENSE`
- `NOTICE`
- `pyproject.toml`
- `README.md`
- `tests/test_repository_license.py`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Publication to GitHub, public CI verification, and
closure of issue #18 remain separate maintainer actions. This entry records the
local implementation and does not claim those external steps have occurred.

**Next gate:** Run the focused repository-license contract and complete
`make validate`; review the exact diff before any commit, push, pull request,
or issue-state change.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-126 — 2026-09-03 — Sibling HTML reader design exploration

**Input:** The maintainer requested a sibling `.htm` file for every Markdown
file in the repository so readers do not need a Markdown converter, specified
a single-page-application experience, and asked to see a sample based on
`docs/paper/kinetic-infrastructure.md` before deciding the design.

**Interpretation:** Treat the requested HTML files as deterministic,
self-contained reading views derived from the Markdown sources and stored in
the same directories. Before defining the generator or committing generated
artifacts, present a non-repository visual mockup using representative content
from the canonical white-paper manuscript. The mockup explores an outline,
responsive paper layout, in-document search, theme toggle, print behavior, and
offline-compatible styling without changing the manuscript.

**Decision status:** Proposal under review. The mockup is a brainstorming
artifact only; no converter, generated sibling `.htm` file, build target, or
generated-file contract has been approved or implemented.

**Rationale:** A repository-wide conversion affects dozens of documents and
creates an ongoing synchronization obligation. Validating the reading
experience first avoids encoding an unwanted layout into every generated
artifact. Keeping the preview outside tracked publication files also preserves
the distinction between a design sample and an authoritative rendering.

**Affected artifacts:**

- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored visual-companion mockup
  `.superpowers/brainstorm/41059-1788436733/content/kinetic-paper-reader-sample.html`

**Unresolved questions:** The maintainer has not yet selected the visual
direction or confirmed whether every tracked Markdown file—including
`AGENTS.md`, historical drafts, test fixtures, and internal planning/spec
documents—belongs in the publication set. The update and stale-output policy,
link rewriting rules, source disclosure, and JavaScript fallback behavior also
remain undecided.

**Next gate:** Obtain feedback on the `kinetic-infrastructure.md` reader
mockup, clarify publication scope one question at a time, compare implementation
approaches, and secure approval of a written design before implementation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-127 — 2026-09-03 — Offline self-contained reader constraint approved

**Input:** After reviewing the `kinetic-infrastructure.md` reader mockup, the
maintainer approved its visual direction and asked whether the final files
would be self-contained rather than hosted.

**Interpretation:** Each generated sibling `.htm` file must be a standalone
offline artifact. Its rendered document, outline navigation, search, theme
control, responsive layout, and print styling must use only embedded HTML, CSS,
and JavaScript. The file must not require a server, CDN, remote font, analytics
endpoint, or runtime package installation. Explicit citations and source links
may remain normal hyperlinks whose destinations naturally require connectivity
when a reader chooses to follow them.

**Decision status:** Confirmed design constraint. The visual direction and
offline/self-contained delivery model are approved; publication-set scope and
the generation/update contract remain proposals.

**Rationale:** A sibling reader is useful to people without Markdown tooling
only if double-clicking it works in an ordinary browser. Embedding presentation
and behavior also prevents hosting availability or third-party resource changes
from altering the local reading experience.

**Affected artifacts:**

- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored visual-companion mockup
  `.superpowers/brainstorm/41059-1788436733/content/kinetic-paper-reader-sample.html`

**Unresolved questions:** Whether the publication set includes repository
instructions, historical drafts, fixtures, and internal plans/specifications;
whether generated siblings are committed or CI-produced; and how Markdown links
to sibling documents are rewritten remain undecided.

**Next gate:** Confirm the publication-set boundary, then compare generator and
update approaches before presenting the complete design for approval.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-128 — 2026-09-03 — One-to-one sibling publication boundary confirmed

**Input:** The maintainer asked whether every existing Markdown file would have
a corresponding `.htm` file in the same folder on a one-to-one basis.

**Interpretation:** The publication set is every tracked repository file whose
name ends in `.md`. Each source maps deterministically to a sibling with the
same relative directory and basename and a changed suffix: `path/name.md`
becomes `path/name.htm`. This includes root documents, reader-facing material,
internal plans and specifications, fixtures, repository instructions, and the
historical-draft directory. Adding a sibling does not modify source Markdown
bytes.

**Decision status:** Confirmed design constraint. The source-to-output mapping
is literal, exhaustive, and one-to-one.

**Rationale:** A complete basename-preserving mapping is predictable for
readers and mechanically verifiable. Keeping the HTML beside its Markdown
source avoids a separate site hierarchy and makes each offline document easy
to locate.

**Affected artifacts:**

- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Link rewriting between generated siblings, the
repeatable generator/update command, stale-output enforcement, and the exact
progressive-enhancement behavior when JavaScript is disabled remain undecided.

**Next gate:** Compare generator and synchronization approaches, then present
the complete repository-wide reader design for approval.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-129 — 2026-09-03 — Sibling navigation and final synchronization approved

**Input:** The maintainer approved rewriting Markdown-document links in the
generated readers to their sibling `.htm` targets, directed continuation, and
requested a final commit and synchronization with GitHub after completion.

**Interpretation:** Generated readers will keep external URLs and non-Markdown
relative targets unchanged while mapping relative `.md` destinations to `.htm`
and preserving query and fragment components. Publication is authorized only
after the complete design, implementation, exhaustive generated set, and
validation gates pass. Partial design or generation work must not be pushed.

**Decision status:** Confirmed design and delivery constraints. The exact
converter implementation remains to be selected. The current inventory is 45
tracked Markdown files; the final one-to-one count will also include any
tracked Markdown design and implementation-plan artifacts added before
generation.

**Rationale:** Sibling rewrites let offline readers remain within the readable
HTML corpus instead of returning users to raw Markdown. Deferring Git
synchronization until all outputs are regenerated and verified prevents a
partial publication set from appearing complete.

**Affected artifacts:**

- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The build-time Markdown engine, dependency strategy,
raw-HTML policy, deterministic freshness marker, and progressive enhancement
contract remain to be approved.

**Next gate:** Select the generator approach, approve the complete design,
write and review the design specification, then plan, implement, validate,
commit, push, and verify exact local/remote commit equality.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-130 — 2026-09-03 — Python build-time reader generator selected

**Input:** The maintainer selected option 1 and directed execution: a Python
build-time generator producing self-contained sibling HTML readers.

**Interpretation:** Use the repository's established Python 3.11+ toolchain and
a pinned documentation-only Markdown parser. Rendering occurs during
maintenance and publication; generated `.htm` files contain complete static
HTML, embedded CSS, and bounded progressive-enhancement JavaScript but no
runtime Markdown parser or package dependency.

**Decision status:** Confirmed architectural selection. Detailed data flow,
security policy, deterministic freshness contract, tests, and failure behavior
still require explicit design approval before implementation.

**Rationale:** A Python generator avoids adding a second project toolchain,
supports deterministic file discovery and link rewriting, and keeps parser
weight out of every generated reader. Pinning the parser as a documentation
dependency makes maintainer regeneration reproducible without changing the
runtime dependency set for KIL itself.

**Affected artifacts:**

- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- stopped and ignored visual-companion session
  `.superpowers/brainstorm/41059-1788436733/`

**Unresolved questions:** The detailed design and written specification are not
yet approved. No generator, dependency, build target, regression test, or
sibling `.htm` output has been created.

**Next gate:** Present the generator architecture and data flow, then the
reader safety/freshness and verification contracts, for maintainer approval.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-131 — 2026-09-03 — HTML generator architecture approved

**Input:** The maintainer approved the proposed Python generator architecture
and source-to-output data flow.

**Interpretation:** The generator will discover tracked Markdown sources in a
stable order, produce same-directory basename-preserving `.htm` siblings,
render full static documents with the approved reader interface, rewrite only
relative links that resolve to tracked Markdown sources, and embed source-path
and source-SHA-256 metadata. A generation target will update outputs; validation
will reject missing, extra, or stale generated siblings.

**Decision status:** Confirmed architecture and data-flow design. Safety,
progressive enhancement, failure atomicity, and the exact verification matrix
remain at the final design gate.

**Rationale:** Git-backed discovery defines an auditable publication set while
stable ordering and embedded source identity make deterministic regeneration
and drift detection testable. Resolving a link before rewriting avoids changing
external URLs or unrelated `.md` text that is not a repository document.

**Affected artifacts:**

- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The raw-HTML policy, content-security boundary,
JavaScript-disabled behavior, all-or-nothing write behavior, and complete
validation cases await approval.

**Next gate:** Present and approve the second design section covering safety,
failure handling, generated-artifact policy, and tests.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-132 — 2026-09-03 — Self-contained HTML reader design approved and specified

**Input:** The maintainer approved the final safety, failure-handling,
progressive-enhancement, generated-artifact, and verification section of the
sibling HTML reader design.

**Interpretation:** The complete approved contract is now captured in a written
design. Markdown remains canonical; generated `.htm` siblings are committed,
fully static, readable without JavaScript, protected from raw-Markdown HTML
execution, deterministic, and validated one-to-one. The reader uses embedded
presentation and bounded interaction only. CI installs pinned documentation
dependencies, and final publication requires exact local/remote equality.

**Decision status:** Confirmed design. `markdown-it-py==4.2.0` and
`mdurl==0.1.2` are selected as documentation-only pins based on their current
authoritative package records. Implementation has not begun and remains gated
on maintainer review of the written specification.

**Rationale:** The approved constraints give readers a portable offline format
without weakening the source-of-record boundary or allowing authored Markdown
to inject executable HTML. Full deterministic regeneration makes source/output
drift mechanically detectable rather than relying on metadata or timestamps.

**Affected artifacts:**

- `docs/superpowers/specs/2026-09-03-self-contained-html-readers-design.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The written specification still requires maintainer
review. The detailed implementation plan, test-first implementation, generated
corpus, visual verification, commit, and remote synchronization remain pending.

**Next gate:** Commit the reviewed design record, obtain maintainer acceptance
of the written specification, then create the implementation plan before any
production code or sibling generation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-133 — 2026-09-03 — HTML reader specification approved and implementation planned

**Input:** The maintainer approved the written self-contained HTML reader
specification and authorized progression to implementation planning.

**Interpretation:** Translate the approved design into five test-first,
commit-sized tasks covering documentation dependency pins, pure safe rendering,
Git-backed generation and check modes, Make/CI/documentation integration and
the complete sibling corpus, then independent review, visual inspection,
lineage closure, validation, and exact Git synchronization.

**Decision status:** Confirmed specification and complete implementation plan.
No production renderer code or repository `.htm` sibling has been created. The
execution mode remains the next explicit workflow choice.

**Rationale:** Separating pure rendering from repository discovery and file
lifecycle behavior makes link, escaping, determinism, and offline properties
testable without bulk writes. Staging the complete corpus only after the tool
passes focused tests preserves the one-to-one publication boundary.

**Affected artifacts:**

- `docs/superpowers/plans/2026-09-03-self-contained-html-readers.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Implementation execution mode is not yet selected.
All code, dependencies, generated readers, visual checks, independent review,
full validation, final commits, and GitHub synchronization remain pending.

**Next gate:** Select subagent-driven or inline plan execution, then implement
each task with observed red/green tests and defer the remote push until every
gate is complete.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-134 — 2026-09-03 — Documentation reader dependency contract implemented

**Input:** Task 1 implementation request for a pinned Markdown reader toolchain
and matching build, CI, bootstrap, and Make help disclosures.

**Interpretation:** Markdown remains canonical; the future HTML reader will use
`markdown-it-py==4.2.0` and `mdurl==0.1.2`, disclosed identically through the
requirements file and `docs` optional extra.

**Decision status:** Confirmed dependency contract. Local commit `110623e` was
created; no merge or push occurred. Renderer and generated siblings remain out
of scope for this task.

**Rationale:** Exact pins and one CI installation command make the documentation
toolchain reproducible and ensure validation has its required parser available.

**Affected artifacts:** `requirements-docs.txt`, `pyproject.toml`,
`.github/workflows/ci.yml`, `README.md`, `Makefile`, and
`tests/test_dependency_contract.py`.

**Unresolved questions:** The renderer's implementation and generated corpus
remain pending in subsequent tasks.

**Next gate:** Complete spec and quality review, then proceed to Task 2.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-135 — 2026-09-03 — Task 1 quality-review correction

**Input:** Code-quality review identified that T-134 omitted the lineage log
itself from its affected-artifacts list and that the Make help contract test
did not execute the actual help target or enforce standalone lines.

**Interpretation:** Correct the record with this additive entry and make the
dependency disclosure test validate `make help` stdout exactly. Documentation
targets disclose only their docs dependency; the complete test suite continues
to disclose both lab and docs dependencies.

**Decision status:** Confirmed quality-review correction. The amended local
commit records these changes; no merge or push occurred.

**Rationale:** Executing the real help target prevents stale or overlapping
source-text assertions from allowing an inaccurate user-facing contract.

**Affected artifacts:** `tests/test_dependency_contract.py`, `Makefile`, and
`docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`.

**Unresolved questions:** The HTML reader implementation and generated corpus
remain pending in subsequent tasks.

**Next gate:** Complete Task 1 review, then proceed to Task 2.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-136 — 2026-09-03 — Safe deterministic Markdown reader renderer implemented

**Input:** Task 2 implementation request for a pure Markdown-to-self-contained
HTML renderer with test-first evidence, stable source identity, offline runtime
policy, safe raw-HTML handling, and no repository generation work.

**Interpretation:** Markdown remains canonical. The renderer is limited to
in-memory bytes and explicit repository-relative source identities; it assigns
deterministic heading IDs, emits the complete static article immediately,
rewrites only tracked relative Markdown document links, and adds bounded
JavaScript enhancements without network capabilities.

**Decision status:** Confirmed local implementation. The focused test suite was
first observed RED because `tools/render_markdown.py` did not exist, then GREEN
after the renderer and its tests were added. No push or merge occurred.

**Rationale:** Keeping parsing, sanitizing, source identity, and reader-shell
generation pure makes deterministic output and offline safety independently
verifiable before Git discovery, corpus generation, or lifecycle checks are
introduced.

**Affected artifacts:** `tools/render_markdown.py`,
`tests/test_markdown_html.py`, and
`docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`.

**Unresolved questions:** Git-backed repository discovery, generated-sibling
creation and check modes, Make/CI integration, complete corpus generation,
visual review, and final repository synchronization remain pending in later
tasks.

**Next gate:** Review this pure renderer task, then implement the separate
repository generation and check-mode task without expanding this renderer's
scope.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-137 — 2026-09-03 — Task 2 renderer specification-review corrections

**Input:** Specification review of Task 2 identified a leading-parent traversal
bypass, lost visible spacing in multiline headings, incomplete paper-reader
layout treatment, and coverage gaps for reference links, destination classes,
and Unicode normalization.

**Interpretation:** Preserve leading traversal during POSIX normalization and
reject every result that remains outside the repository; visible Markdown
softbreaks and hardbreaks become one trimmed space for title, outline, and ID
derivation. The static reader shell also restores a neutral canvas, paper card,
desktop rail, and compact mobile chrome without adding a runtime dependency.

**Decision status:** Confirmed additive correction to Task 2. New regression
tests were observed RED for the odd traversal bypass, multiline heading text,
and missing paper/mobile structure, then GREEN after the fixes. No push or
merge occurred.

**Rationale:** The corrections close a repository-boundary escape and make
reader semantics and responsive presentation conform to the approved contract
while retaining the pure, offline, no-JavaScript-required reading path.

**Affected artifacts:** `tools/render_markdown.py`,
`tests/test_markdown_html.py`, and
`docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`.

**Unresolved questions:** Task 3 Git discovery, generation, and check-mode
work, followed by later integration, corpus, visual-review, and synchronization
gates, remains outside this correction.

**Next gate:** Amend the local Task 2 commit after focused verification, then
proceed only to the separately scoped Task 3 work.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-138 — 2026-09-03 — Task 2 URL, search, and mobile quality corrections

**Input:** Code-quality review required strict canonical treatment of encoded
relative links, source-text-safe search highlighting, mobile reader semantics,
Unicode slug correction, print wrapping, and a confirmed future publication
invariant for every tracked Markdown document.

**Interpretation:** Relative URL paths are now validated and decoded
segment-by-segment before repository lookup, then rewritten with consistent
UTF-8 percent encoding. Search marking normalizes previously inserted fragments
and matches against original text offsets. The mobile reader keeps labeled
search and provenance available, exposes a semantic outline, and retains the
static article-first reading path. The confirmed permanent invariant is that
every new tracked `.md` must have a self-contained sibling `.htm`; enforcement
belongs to the later discovery, check, validation, and corpus tasks.

**Decision status:** Confirmed additive Task 2 quality correction. Focused
regressions were observed RED for encoded-source lookup, encoded traversal and
separator safety, missing original-text search mechanics, mobile semantics,
underscore slugging, and print wrapping; they were then observed GREEN. No
push or merge occurred.

**Rationale:** Canonical URL comparison prevents encoded paths from bypassing
repository boundaries or missing legitimate tracked files, while the reader
corrections preserve offline safety, accessible mobile use, deterministic
output, and readable printing without adding runtime dependencies.

**Affected artifacts:** `tools/render_markdown.py`,
`tests/test_markdown_html.py`, and
`docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`.

**Unresolved questions:** Task 3 repository discovery, generation, and
check-mode implementation; Task 4 integration and validation enforcement; and
complete sibling-corpus generation and review remain pending.

**Next gate:** Amend the local Task 2 commit after final focused verification,
then implement the separately scoped later tasks that dynamically enforce the
tracked-Markdown/sibling-HTML invariant.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-139 — 2026-09-03 — Task 2 suffix and responsive-search cleanup

**Input:** Final narrow Task 2 review identified that URL serialization lost
empty query and fragment delimiter bytes, and that responsive search controls
could diverge after an input event.

**Interpretation:** A rewritten tracked Markdown link preserves the exact raw
suffix beginning with the first unencoded `?` or `#`, including empty delimiter
forms, while percent-encoded question marks and hashes remain path data.
Shipped JavaScript now copies an active search value to its peer controls before
marking article text; browser-executed interaction verification is explicitly
deferred to Task 5 because this focused unit suite has no DOM runtime.

**Decision status:** Confirmed additive Task 2 cleanup. The new suffix and
search-control regressions were observed RED, then GREEN after the pure URL
suffix preservation and static synchronization changes. No push or merge
occurred.

**Rationale:** Preserving delimiter bytes avoids output drift for semantically
intentional URL forms, and synchronizing responsive controls keeps visible UI
state consistent with already-rendered search matches without compromising the
static reader.

**Affected artifacts:** `tools/render_markdown.py`,
`tests/test_markdown_html.py`, and
`docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`.

**Unresolved questions:** Task 3 discovery/generation/check enforcement, Task
4 integration and validation, Task 5 browser interaction tests, and corpus
generation/review remain pending.

**Next gate:** Amend the local Task 2 commit after focused verification, then
continue only with the separately scoped later tasks.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-140 — 2026-09-03 — Dynamic sibling-reader lifecycle enforcement

**Input:** The maintainer confirmed that every new `.md` file must have a
self-contained `.htm` partner in the repository, and Task 3 required safe
Git-backed discovery, generation, read-only checking, and command-line
behavior without generating the real corpus yet.

**Interpretation:** Tracked lowercase-`.md` paths are the dynamically
discovered canonical source set. Each maps by changing only its final suffix
to a same-directory `.htm`; tracked and non-ignored untracked `.htm` files form
the visible output namespace. Check mode reports every missing, stale, or
unexpected output without writing. Default mode renders all source bytes in
memory before staging any output, refuses unexpected or ignored output states,
and rejects unsafe, duplicate, colliding, non-file, or symlinked paths.

**Decision status:** Confirmed Task 3 implementation. Temporary Git-repository
tests observed the absent lifecycle API as RED, then verified generation,
checking, deterministic diagnostics, CLI results, tracked/untracked and
ignored asymmetry, Unicode and spaced paths, suffix mapping, collision and
symlink rejection, source preservation, and pre-write failure atomicity as
GREEN. No real sibling corpus was generated, and no push or merge occurred.

**Rationale:** Deriving the source set from the Git index makes the permanent
one-to-one invariant update automatically when a Markdown file is added or
removed. Treating all visible `.htm` paths as a reserved namespace detects
manual extras, while complete in-memory rendering and preflight validation
prevent predictable failures from partially updating derived artifacts.

**Affected artifacts:** `tools/render_markdown.py`,
`tests/test_markdown_html.py`, and
`docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`.

**Unresolved questions:** Make/CI integration, repository guidance, real-corpus
generation, tracked publication verification, browser interaction and visual
inspection, and final synchronization remain for Tasks 4 and 5.

**Next gate:** Review and commit the scoped Task 3 lifecycle implementation,
then wire validation and generate the complete tracked corpus in Task 4.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-141 — 2026-09-03 — Task 3 lifecycle boundary corrections

**Input:** Task 3 quality review found that deleted tracked readers were
misclassified as unsafe, path-bearing diagnostics could contain literal
control characters, destination-derived staging names could exceed filesystem
limits, the CLI rediscovered Markdown after generation, and replacement-fault
cleanup lacked an explicit regression.

**Interpretation:** Git-index membership and on-disk HTML visibility are
separate sets. A tracked reader absent from disk is missing and repairable,
including when an ignore rule matches its tracked path; an existing or broken
symlink remains unsafe through `lexists`-aware validation. Every lifecycle path
is rendered through one Unicode-preserving, JSON-style, line-safe formatter.
Staging uses a fixed short name in the destination directory. The CLI captures
one validated source snapshot, passes it through rendering, and reports that
snapshot's count. Replacement remains sequentially atomic per file: an
operating-system failure may leave completed replacements, always cleans
unconsumed staging files, and is made observable by read-only checking.

**Decision status:** Confirmed additive Task 3 correction. Regressions were
observed RED for deleted tracked output repair, control-safe diagnostics,
near-`NAME_MAX` generation, and repeated CLI discovery, then GREEN after the
boundary fixes. Fault injection also confirms the documented mixed-generation
failure state and cleanup. The permanent invariant remains that every tracked
`.md` dynamically maps to exactly one same-directory self-contained `.htm`.
No real corpus was generated, and no push or merge occurred.

**Rationale:** Index entries describe repository membership but cannot prove a
working-tree file exists. Keeping those concepts separate restores ordinary
repair behavior without weakening symlink safety. Stable escaped diagnostics,
bounded staging names, and a single source snapshot remove injection,
filesystem-limit, and post-operation race hazards while preserving the
approved deterministic publication model.

**Affected artifacts:** `tools/render_markdown.py`,
`tests/test_markdown_html.py`, and
`docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`.

**Unresolved questions:** Task 4 Make/CI and repository-guidance integration,
real-corpus generation and tracked publication proof, plus Task 5 browser
interaction and visual inspection, remain pending.

**Next gate:** Amend the existing Task 3 commit after focused and complete
validation, then proceed to the separately scoped Task 4 integration gate.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-142 — 2026-09-03 — Task 3 diagnostic and portability hardening

**Input:** Final Task 3 review requested format-control escaping, explicit
POSIX scoping for filesystem-specific regressions, capability-aware symlink
skips, and removal of the pre-discovered source snapshot from the public
repository-rendering API.

**Interpretation:** Line-safe path formatting now escapes Unicode format
controls as well as control, line-separator, and paragraph-separator code
points, including bidirectional overrides and isolates and zero-width spaces.
Filename-control and `NAME_MAX` tests run on POSIX systems, retaining Linux and
macOS coverage, while symlink tests skip only when creation is unsupported or
denied. Public `render_repository(root, check)` and
`expected_documents(root)` discover their own tracked sources; the CLI alone
uses a documented internal helper with one trusted pre-discovered snapshot to
avoid post-operation rediscovery.

**Decision status:** Confirmed additive Task 3 hardening. Format-control and
public-API regressions were observed RED, then GREEN after escaping category
`Cf` and moving snapshot reuse behind internal helpers. The permanent invariant
remains that every tracked `.md` maps dynamically to exactly one same-directory
self-contained `.htm`. No Task 4 work, real corpus generation, push, or merge
occurred.

**Rationale:** Invisible directionality and formatting controls can make an
otherwise single-line diagnostic misleading, and platform assumptions should
not turn unsupported filesystem behavior into false failures. Keeping the
snapshot parameter internal prevents callers from mistaking arbitrary paths
for the Git-authoritative publication set while retaining a race-free CLI
count.

**Affected artifacts:** `tools/render_markdown.py`,
`tests/test_markdown_html.py`, and
`docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`.

**Unresolved questions:** Task 4 Make/CI integration, guidance, real-corpus
generation and tracked-set proof, followed by Task 5 browser interaction and
visual review, remain pending.

**Next gate:** Amend the existing Task 3 commit after focused verification,
then proceed only to the separately scoped Task 4 integration work.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-143 — 2026-09-03 — Repository-wide offline-reader publication contract

**Input:** The user approved publishing a self-contained `.htm` partner beside
every current Markdown document and confirmed the permanent rule that every new
tracked lowercase-final-suffix `.md` file must receive the same partner.

**Interpretation:** Git-tracked Markdown is canonical. Each tracked path ending
in lowercase `.md` dynamically maps to exactly one tracked same-directory path
with only its final suffix changed to `.htm`. The generated reader embeds its
article, styles, and bounded controls and requires no hosted runtime. Local
relative images remain local file references rather than embedded binaries;
remote content and network APIs remain blocked by the reader content security
policy.

**Decision status:** Confirmed Task 4 implementation. Make exposes generation
and read-only checking, validation depends on the check, repository guidance
states the source-of-record and safe-rendering rules, and the initial real-corpus
gate passed with 47 tracked sources and 47 exact staged readers. Final
regeneration after this entry and complete-suite verification are the remaining
Task 4 evidence steps. No laboratory service was started, and no push or merge
occurred.

**Rationale:** Deriving both generation and validation from the Git index makes
the one-to-one rule apply without maintaining a hand-written inventory. A
committed offline reader gives people without a Markdown converter a directly
openable view while preserving Markdown as the reviewable authority. Reporting
missing, stale, and unexpected readers in read-only mode prevents silent
publication drift. The reader beside the frozen V3B fixture's `summary.md` is
repository publication metadata, not runtime evidence: fixture test scaffolding
projects it out while the production verifier continues to reject every
undeclared artifact.

**Affected artifacts:** `Makefile`, `README.md`, `tools/README.md`,
`tests/test_markdown_html.py`, `tests/test_v3b1_local_envoy.py`, this lineage,
and the exact generated `.htm` siblings of all 47 tracked Markdown sources.

**Unresolved questions:** Task 5 browser interaction and representative visual
inspection remain pending, followed by final repository synchronization with
the remote Git branch.

**Next gate:** Regenerate after this lineage entry, prove deterministic output
and the complete validation suite, commit Task 4, then perform the Task 5
browser and visual evidence review before final synchronization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-144 — 2026-09-03 — Reader publication and frozen-fixture projection corrections

**Input:** Task 4 review found that the frozen V3B compatibility fixture used a
recursive basename ignore in one copy path, another copy path could reject the
generated `summary.htm` before reaching its intended injected-driver check, and
the publication test imposed an unnecessary minimum count of 47 Markdown
sources.

**Interpretation:** The repository fixture contains `summary.htm` only because
the permanent publication invariant maps every tracked lowercase-final-suffix
`.md` to an exact same-directory `.htm`. Runtime evidence remains the manifest-
and-checksum-bound closed bundle. Every test that copies this frozen fixture now
uses one projection helper: it copies the repository directory, then removes
only the root-relative `summary.htm`. The V1 driver rejection test verifies this
projected baseline before injecting `raw/drivers`, so its failure is causally
bound to the injected artifact. Exact source/output set equality enforces the
dynamic publication invariant without freezing a repository-size floor.

**Decision status:** Confirmed additive Task 4 correction. The causal baseline
assertion was observed RED against the earlier direct copy and then GREEN after
the exact projection helper. Focused compatibility, injected-driver, generation,
and dynamic publication tests pass. Final regeneration, deterministic checking,
and complete-suite validation remain before the amended commit. Production V3B
verification semantics and frozen evidence bytes and checksums are unchanged;
no laboratory service, push, or merge occurred.

**Rationale:** Recursive basename exclusion could hide a future nested artifact
with the same name, while direct copying lets repository publication metadata
mask the actual rejection under test. One exact root-relative projection keeps
the repository accessibility requirement separate from runtime evidence
closure. Set equality already adapts to valid paired additions and removals, so
a numeric source floor adds brittleness without strengthening the invariant.

**Affected artifacts:** `tests/test_v3b1_local_envoy.py`,
`tests/test_markdown_html.py`,
`tests/fixtures/v3b1-public-bundle-v1/README.md`, this lineage, and the refreshed
HTML partners for the fixture README and lineage.

**Unresolved questions:** Task 5 browser interaction and representative visual
inspection remain pending, followed by final synchronization of the verified
branch with remote Git.

**Next gate:** Regenerate the complete corpus after these Markdown changes,
prove exact pairs, freshness, deterministic second generation, focused tests,
and full validation, then amend the Task 4 commit and proceed to Task 5 review.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-145 — 2026-09-03 — Automated reader verification complete; browser gate pending

**Input:** Task 5 required complete automated verification, an independent
whole-feature review, and representative desktop, narrow-viewport, search,
theme, print, outline, local-image, and network-boundary inspection before the
final evidence commit and authorized Git synchronization.

**Interpretation:** The implementation and all 47 tracked Markdown/HTML pairs
are ready for browser inspection. Direct `file://` navigation was rejected by
the in-app browser's security policy, so that restriction will not be bypassed
by starting another service or using an alternate browser surface. The safe
next step is for the maintainer to open the final reader through the existing
localhost preview, after which the browser interaction gate can proceed on the
user-opened page.

**Decision status:** Automated and review gates confirmed; representative
browser gate pending. `make validate` passed 538 tests, verified all 47 readers,
and passed diff hygiene. Five representative generated scripts passed syntax
and required-structure checks. Independent whole-feature review found no
Critical or Important issues; its only Minor finding is the intentionally
unresolved lack of executed production-browser behavior. No laboratory service,
push, merge, issue mutation, or remote synchronization occurred.

**Rationale:** Static and unit evidence proves deterministic generation,
source-digest binding, exact dynamic publication coverage, restrictive CSP,
safe Markdown rendering, and shipped-script syntax, but it cannot substitute
for executing responsive and interactive behavior in a real browser. Respecting
the browser policy preserves the security boundary while keeping the remaining
gate explicit and independently auditable.

**Affected artifacts:** This lineage and its generated `.htm` partner. The
verified implementation remains in `tools/render_markdown.py`, `Makefile`,
repository guidance and tests, plus the exact 47-reader corpus.

**Unresolved questions:** The maintainer must expose the final reader in the
already-running localhost preview so desktop/mobile interaction, print styling,
local-image behavior, and network observations can be completed.

**Next gate:** Inspect the user-opened final localhost reader and representative
sibling pages, append the conclusive verification entry, regenerate and validate
the lineage partner, commit the evidence, then push once and verify exact local,
upstream, and remote-head synchronization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-146 — 2026-09-03 — Companion-reader location and publication handoff

**Input:** The maintainer reported that no `.htm` companions were visible in
the normal repository checkout and directed the work to continue without the
extended browser gate.

**Interpretation:** The 47 companions had been generated and committed in the
Codex-managed `codex/self-contained-html-readers` worktree, while the normal
`main` checkout remained at its earlier revision. The absence observed by the
maintainer was therefore a branch/worktree visibility issue, not a generation
failure. Browser interaction remains unexecuted and is not represented as
validated.

**Decision status:** Confirmed publication handoff. Finish the reader evidence
commit and push the feature branch so every companion is visible in Git. Do not
overwrite the normal checkout's unrelated uncommitted OTCS lineage and input
work while attempting a local fast-forward.

**Rationale:** Publishing the completed branch provides the requested artifacts
immediately and preserves unrelated maintainer work. Exact local-main
integration can follow once those uncommitted changes are committed, moved, or
otherwise resolved by the maintainer.

**Affected artifacts:** This lineage and its generated `.htm` partner; the
existing exact set of 47 tracked `.md`/`.htm` pairs remains unchanged.

**Unresolved questions:** The normal `main` checkout contains unrelated
uncommitted OTCS work, so it cannot be safely fast-forwarded without a
maintainer decision. Browser behavior was structurally reviewed but not
executed because direct local-file navigation was blocked and the maintainer
redirected the task toward artifact availability.

**Next gate:** Regenerate and verify the lineage partner, commit the evidence,
push `codex/self-contained-html-readers`, verify the remote branch hash, and
report the exact artifact locations and the dirty-`main` integration blocker.
### T-125 — 2026-09-03 — KIL receives an observed OTCS coordinate record

**Input:** Fill the repository copy of the Open Trust Coordinate System (OTCS)
0.1 coordinate-record template with KIL data, using the KTP coordinate-map page
as the reference for the coordinate meanings and chart constraints.

**Interpretation:** This is an observed reading of KIL at immutable repository
revision `ab2667941b9328739c8201d626694770e2387fe9`, not a normative
self-declaration by KIL and not a validation result. The coordinate system's
sparse-record rule requires omitting capabilities, environmental conditions,
and interfaces that the published project does not explicitly support. Function
weights describe operational emphasis; the evidence block separately describes
claim maturity.

**Decision status:** Confirmed artifact creation. The record identifies KIL as
an implementation of KTP, places its declared enforcement point at the local
Envoy `ext_authz` transport boundary, and records specification and
implementation at M2 because reproducible source, schemas, tests, and run
contracts exist. Independent validation remains explicitly M0. The particular
coordinate selection and weights are a reviewable observed reading, not an
approved KIL or KTP registry position.

**Rationale:** KIL governs AI-agent and service actions through signed,
authority-class-bound state; interprets identity binding, local divergence,
freshness, and class history; reduces authority without expanding it; issues
permit/constrain/deny decisions; enforces at a declared pre-upstream Envoy
boundary; and preserves canonical evidence records. The environmental list is
limited to identity confidence, threat pressure, uncertainty, and cumulative
trajectory. System and dependency health are exercised by the validation
harness but are not inputs to the current action decision, so they are not
claimed. Repair and learning are also omitted because teardown/retry behavior
is not capacity restoration and no outcome-to-model learning loop is
implemented. Registry interfaces remain empty because no mutually agreed seam
identifier is available from this observed reading.

**Affected artifacts:**

- `Inputs/coordinate-record-template.yaml`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** KIL maintainers may revise the observed weights,
choose a registry-specific identifier for the KTP lineage target, or coordinate
matching `provides`/`consumes` seam identifiers with KTP. The central V3B-1
enforcement run and external validation remain pending and must not be inferred
from this map record.

**Next gate:** Validate the YAML against the OTCS 0.1 map parser and obtain
maintainer review before presenting the coordinates as KIL's own declaration or
registering any inter-project seam.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-147 — 2026-09-03 — Project-boundary reference cleanup design approved

**Input:** The maintainer directed removal of every current-file reference to
an unrelated external project because KIL shares no components, data, or
concepts with it. The maintainer explicitly excluded Git-history rewriting and
approved the proposed KIL-only rewrite design.

**Interpretation:** Rewrite the affected current Markdown sentences so they
describe KIL and KTP without naming or indirectly preserving the unrelated
project comparison. Regenerate the corresponding self-contained readers. The
same narrow cleanup applies to the occurrence in the maintainer's uncommitted
OTCS lineage work, while all other OTCS changes remain preserved and
uncommitted.

**Decision status:** Cleanup design confirmed; implementation pending written
spec review. Historical commits, third-party dependencies, and caches remain
outside scope.

**Rationale:** Direct KIL-only language preserves useful repository-boundary
and protocol guidance without retaining an irrelevant project association.
Separating the cleanup commit from the maintainer's OTCS work prevents an
unrelated partial change set from entering project history.

**Affected artifacts:**
`docs/superpowers/specs/2026-09-03-project-boundary-reference-cleanup-design.md`,
this lineage, and their generated `.htm` partners. Implementation will update
the three identified Markdown sources and their generated partners; the normal
checkout's uncommitted lineage pair will receive the same narrow cleanup after
integration.

**Unresolved questions:** None. Current files are in scope; Git history is not.

**Next gate:** Commit the design record and generated readers, obtain maintainer
review of the written specification, then write and execute the implementation
plan, validate zero current-file matches, and synchronize `main` without
committing unrelated OTCS work.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-148 — 2026-09-03 — Project-boundary cleanup execution planned

**Input:** After reviewing the still-unchanged README, the maintainer reiterated
that the current-file references must be removed. This confirms execution of
the approved design rather than another documentation-only checkpoint.

**Interpretation:** Apply exact KIL-only rewrites to the three authoritative
Markdown sources, add a tracked-file regression test, regenerate every reader,
and validate the whole repository. Then integrate and push while preserving the
normal checkout's unrelated OTCS work as uncommitted changes; narrowly remove
the same name from its lineage occurrence after restoration.

**Decision status:** Confirmed implementation plan; execution begins inline on
the isolated cleanup branch.

**Rationale:** The visible README is the maintainer's immediate acceptance
surface. A source-first rewrite plus deterministic reader generation corrects
both `.md` and `.htm`, while the regression test prevents the project boundary
from drifting back into tracked content.

**Affected artifacts:**
`docs/superpowers/plans/2026-09-03-project-boundary-reference-cleanup.md`, this
lineage, and their `.htm` partners. Planned implementation also affects
`PROJECT.md`, `README.md`, the specialist-consultation checkpoint, their
readers, and `tests/test_project_boundaries.py`.

**Unresolved questions:** None. The scope is current project files only; Git
history remains unchanged.

**Next gate:** Execute the regression test red/green cycle, regenerate and
validate all readers, commit and push the branch, preserve and restore OTCS
work around the `main` fast-forward, then prove local/remote synchronization
and zero current-file matches.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-149 — 2026-09-03 — Project-boundary reference cleanup verified

**Input:** Execute the approved current-file cleanup after the maintainer
confirmed that the README and its reader must no longer name the unrelated
external project.

**Interpretation:** Replace the three source-document comparisons with direct
KIL/KTP statements, regenerate their readers, and enforce the boundary with a
case-insensitive tracked-file regression test that does not itself store the
removed name contiguously.

**Decision status:** Cleanup implementation confirmed on the isolated branch.
The regression test first failed on exactly six stale tracked artifacts, then
passed after the three Markdown sources and their readers were corrected. Full
validation passed 539 tests and verified all 49 Markdown/HTML pairs.

**Rationale:** The final text now states what KIL owns and which KTP telemetry
interfaces it accepts, without preserving an irrelevant relationship or
discarding useful protocol-boundary guidance. The source-first generation path
keeps human-readable Markdown and self-contained readers consistent.

**Affected artifacts:** `PROJECT.md`, `README.md`,
`docs/checkpoints/2026-08-24-specialist-consultation.md`, their `.htm`
partners, `tests/test_project_boundaries.py`, the approved design and execution
plan pairs, and this lineage pair.

**Unresolved questions:** None for committed current files. The normal
checkout's uncommitted OTCS lineage occurrence still requires the same narrow
rewrite during integration; its other content must remain uncommitted and
preserved. Git history remains outside scope.

**Next gate:** Regenerate this lineage reader, repeat full validation and the
zero-match search, commit and push the cleanup branch, restore the preserved
OTCS work around a fast-forward of `main`, remove its remaining current-file
occurrence, regenerate its reader, and verify local/remote synchronization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-150 — 2026-09-03 — Strict no-reference boundary correction

**Input:** Before final handoff, re-evaluate whether the committed regression
guard itself complied with the maintainer's instruction that the unrelated
project have no references anywhere in current KIL files.

**Interpretation:** A guard that reconstructs the removed name from string
fragments remains a project reference even when literal searches report no
match. Remove that test and revise the execution plan so verification uses the
maintainer-supplied search term externally without storing or reconstructing it
in KIL source.

**Decision status:** Confirmed correction. This entry supersedes only the
regression-guard portion of T-148 and T-149; the KIL-only document rewrites,
reader regeneration, validation evidence, and current-files-only scope remain
unchanged.

**Rationale:** The requested boundary is semantic, not merely a way to satisfy
a literal search. Retaining an encoded name in a test would contradict the
maintainer's explicit statement that the projects share no components, data,
or concepts.

**Affected artifacts:** `tests/test_project_boundaries.py` is removed;
`docs/superpowers/plans/2026-09-03-project-boundary-reference-cleanup.md`, this
lineage, and their `.htm` partners are refreshed.

**Unresolved questions:** None. The verification term remains external to
current project files; Git history and safety stashes remain outside the
maintainer-confirmed current-file scope.

**Next gate:** Regenerate all readers, verify zero current-file references,
repeat the full repository validation, commit and push the correction, then
fast-forward `main` while preserving the uncommitted OTCS work.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-151 — 2026-09-05 — V3B-1 testing started at the prerequisite gate

**Input:** Begin V3B-1 testing and auto-approve in-scope prompts.

**Interpretation:** Start with the exact synchronized public source and execute
only the non-requesting static and host-preflight gates. Preserve the
maintainer's unrelated uncommitted OTCS/lineage work in the normal checkout.
Do not invoke the central request-bearing `run` while the repository's durable
before/after foreign-resource snapshot prerequisite remains unimplemented.

**Decision status:** Confirmed test-start result. An isolated
`codex/v3b1-testing` worktree at
`b7f1f1565943ee6a06c64051949a1b465a83e527` matched `origin/main`. The full
static gate passed 538 tests, verified all 49 Markdown readers, and passed
`git diff --check`. The pinned Docker, Kind, and kubectl content lock verified,
and controller `preflight` passed with ports 18080–18082 free. The only observed
Colima profile was the stopped foreign `default` profile with
`aarch64/containerd`, 4 CPUs, 4 GiB memory, and 20 GiB disk. No `up`,
`readiness`, `run`, `collect`, or `down` command was invoked.

**Rationale:** The Task 11 contract expressly prohibits the consequential run
until a tested, reviewed, merged, and synchronized evidence extension durably
binds and verifies exact foreign-resource snapshots before and after the
lifecycle. Passing static validation and preflight establishes that the current
source, pinned tools, host versions, profile allowlist, and fixed ports are
ready without weakening that gate or creating request evidence.

**Affected artifacts:** This lineage source; isolated ignored worktree
`.worktrees/v3b1-testing`. Runtime checks confirmed the dedicated
`kil-v3-lab` Docker endpoint, active state, active journal, and readiness poison
were absent after preflight. Existing maintainer changes in `Inputs/` and the
lineage pair remain otherwise untouched.

**Unresolved questions:** The exact before/after foreign-resource snapshot
schema, journal events, public commitment fields, and offline verifier equality
checks still require design and implementation before request-bearing live
testing can begin.

**Next gate:** Design and implement the foreign-resource snapshot extension
with tests, pass review and complete static validation, merge and synchronize
the prerequisite, then begin one fresh Task 11 lifecycle with `preflight` and
`up`. Invoke the central `run` exactly once only after those conditions pass.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-152 — 2026-09-05 — V3B-1 foreign-resource prerequisite implemented and approved

**Input:** Advance to the next V3B-1 testing phase with in-scope prompts
auto-approved.

**Interpretation:** Resolve the Task 11 prerequisite before any request-bearing
run: design, implement, test, document, and independently review durable exact
before/after snapshots of foreign Colima profiles. Continue in the isolated
`codex/v3b1-testing` worktree so the maintainer's unrelated normal-checkout
changes remain untouched.

**Decision status:** Confirmed implementation on the isolated branch, not yet
integrated into `main`. Eight commits from `22c750f` through `5ebf21a` add the
approved design and plan, closed snapshot and comparison contracts, lifecycle
journal authority, nonce-keyed public projections, V3 evidence bindings,
offline verification, recovery hardening, and synchronized operator guidance.
Independent code review initially found four important issues; all were fixed
with regressions and the re-review approved the branch with no remaining
findings. Final `make validate` passed 561 tests, verified all 51 generated
Markdown readers, and passed `git diff --check`.

**Rationale:** The extension now proves whether every non-owned Colima profile
is unchanged across the owned lab lifecycle without publishing raw profile
names. It fails closed on reordered or incomplete journal authority, a same-name
dedicated-profile race, sensitive public fields, and crash recovery after a
foreign-profile mismatch. A mismatch can publish only deterministic,
nonpromotable failure evidence. This meets the prerequisite gate without
issuing a central request or weakening the one-attempt protocol.

**Affected artifacts:** Isolated branch `codex/v3b1-testing`; foreign snapshot,
journal, evidence, publication, recovery, and verifier logic in
`tools/v3b1_local_envoy.py`; controller and documentation regressions; V3B-1
README, adapter, progress, Task 10, design, and execution-plan source/reader
pairs; and this lineage source. No `up`, `readiness`, `run`, `collect`, or live
`down` lifecycle command was invoked during this phase.

**Unresolved questions:** The reviewed branch still requires an explicit
integration choice. The normal checkout contains unrelated uncommitted lineage
and `Inputs/` work that must be preserved. A live request-free V3 lifecycle
must begin only from merged, synchronized `main`; the central `run` remains
prohibited until its pre-request gates pass.

**Next gate:** Choose local merge, pull-request publication, or branch
preservation. After integration and synchronization, start one fresh V3
lifecycle with `preflight` and `up`, complete request-free readiness checks,
and invoke the central `run` exactly once only if every gate remains green.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-153 — 2026-09-05 — V3B-1 prerequisite fast-forwarded into local main

**Input:** Select local merge for the completed `codex/v3b1-testing` branch.

**Interpretation:** Fast-forward local `main` only after refreshing
`origin/main`, confirming the branch base and non-overlap with the maintainer's
uncommitted lineage and `Inputs/` work, then verify the exact merged commit
before removing the isolated worktree and feature branch.

**Decision status:** Confirmed local integration. `main` advanced by fast-forward
from `b7f1f15` to reviewed commit `5ebf21a`. Post-merge validation of that exact
commit passed 561 tests, verified all 51 Markdown readers, and passed
`git diff --check`. The clean `.worktrees/v3b1-testing` worktree was removed,
its registration pruned, and the merged local branch deleted.

**Rationale:** A fast-forward preserves the reviewed commit identities and
avoids an unreviewed merge result. Verifying in the clean isolated checkout at
the same commit prevented the maintainer's unrelated uncommitted files from
being rewritten or folded into the validation result.

**Affected artifacts:** Local `main` now contains commits `22c750f` through
`5ebf21a`; this lineage source records the integration. The pre-existing
uncommitted lineage pair and `Inputs/` directory remain present. No V3B-1 live
lifecycle or central request was invoked.

**Unresolved questions:** Local `main` is eight commits ahead of `origin/main`;
the merge choice did not authorize a push. The generated lineage reader remains
part of the maintainer's pre-existing uncommitted work and was not regenerated
or overwritten here.

**Next gate:** Explicitly synchronize local `main` with the remote, then begin
one fresh request-free V3 lifecycle from synchronized source using `preflight`
and `up`. The central `run` remains a later, exactly-once action gated on all
request-free checks passing.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-154 — 2026-09-05 — V3B-1 request-free V3 gate completed and published

**Input:** Execute and finish the next V3B-1 testing phase with all in-scope
prompts approved.

**Interpretation:** First synchronize the reviewed foreign-resource snapshot
prerequisite to public `main`, then execute exactly the request-free lifecycle
`preflight` → `up` → `readiness` → `down` from that source. Do not invoke
`run` or `collect`. Verify the resulting nonpromotable V3 diagnostic bundle,
correct any specification inconsistency exposed by the real run, obtain
independent review and public CI, merge the publication checkpoint, and
synchronize local `main` without disturbing unrelated maintainer work.

**Decision status:** Confirmed gate completion. Public `main` first advanced to
prerequisite commit `5ebf21a`. The isolated lifecycle produced run
`v3b1-4ac0b6eef70b0483f7883c8a26753d15a007f612953b25e23b8ecb6afd021a8f`
from that exact source. All three drivers reached readiness and were cancelled;
the private journal contains no request-attempt, instruction, result, or request
record. Teardown proved all 15 owned containers and all 6 owned networks absent.
The V3 foreign-profile attestation reports exact before/after equality for the
one observed foreign profile while exposing only its pseudonymous public
reference; its retained tuple is stopped, `aarch64/containerd`, 4 CPUs, 4 GiB
memory, and 20 GiB disk. The public manifest is schema
`kil.v3b1-public-manifest.v3`, `run_complete: false`, class
`intermediate_provisional_failure_local_boundary`, and `not_promoted`, with
manifest SHA-256
`3572ad5b9f7a2da66ce8b5cf13c020179283c5b1635aef8302977e8c562bb475`.
All published checksums and the offline failure-bundle verifier passed. The
final tree passed 562 tests, verified 51 Markdown readers, and passed
`git diff --check`; independent specification review returned PASS and quality
review returned APPROVE. PR #20 passed public CI and merged as `6e7ee57`, and
local `main` was fast-forwarded to the same commit.

**Rationale:** The real request-free run demonstrated that the V3 snapshot,
journal, teardown, privacy, and recovery contracts operate together on the
approved host without crossing the exactly-once request boundary. The run also
exposed a documentation contradiction: the request-free diagnostic bundle was
incorrectly required to pass the completed-run public `view` command. The
published correction requires the dedicated failure-bundle verifier for this
nonpromotable evidence and reserves public `view --bundle` for completed central
evidence. A regression test now keeps that distinction consistent.

**Affected artifacts:** PR #20 updates the README, Envoy adapter guide, V3
progress record, Task 10 gate record, request-driver plan, foreign-resource
snapshot design, all paired generated readers, and
`tests/test_v3b1_documentation.py`. The ignored public bundle and archived
private journal remain in the isolated
`.worktrees/v3b1-request-free-v3` worktree for an explicit offline-backup
decision. This lineage source records the checkpoint; the maintainer's existing
lineage reader edit and `Inputs/` directory remain otherwise preserved.

**Unresolved questions:** No request was issued, so the central Task 11
exactly-once run and its completed promotable evidence remain outstanding. A
destination and retention policy for the ignored request-free bundle and
private journal have not yet been selected.

**Next gate:** Choose the offline-backup disposition for the retained private
evidence. Then start a new clean synchronized lifecycle, repeat `preflight`,
`up`, and request-free readiness checks, and invoke the central `run` exactly
once only if every documented Task 11 gate remains green; follow with
`collect`, `down`, verification, independent review, and publication.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-155 — 2026-09-05 — Task 11 exactly-once attempt failed closed

**Input:** Complete the next V3B-1 testing phase.

**Interpretation:** Execute Task 11 from newly synchronized public `main` in a
separate clean worktree: pass static and host gates, create one fresh topology,
invoke the central `run` exactly once, then collect, tear down, and publish only
if the complete proof passes its closed verifier. After request intent, never
retry the consequential request under the same authorization.

**Decision status:** Confirmed terminal failed-closed result; the accepted-proof
phase is not complete. The clean worktree at public commit `6e7ee57` passed 562
tests and all 51 Markdown readers. A first sandbox-blocked `up` stopped before
profile creation or request activity and was closed through the controller's
pre-profile `down` recovery. A new lifecycle then created run
`v3b1-f8152ed1b52e33264b9f3339f4eeb8255260703f6c2c62824c3cb2379c76b4b1`.
Immediately before the central command, all three request states were
`not_attempted`. Exactly one `run` was invoked. Its three in-network drivers
each completed one attempt with no retry and observed HTTP `200 / 200 / 403`
with the expected decision digests and target-marker cardinality `1 / 1 / 0`.
The command then failed during its internal evidence collection when a direct
Docker copy reported one authorization ledger path absent. The consequential
request was not retried. Exactly one `down` completed owned teardown and
published a nonpromotable V3 failure bundle. Post-teardown preflight passed,
the exact pseudonymous foreign-resource arrays remained equal, all 15 owned
containers and 6 networks were absent, active state/journal/poison paths were
absent, every published checksum passed, and the offline failure-bundle
verifier accepted `live.html`.

**Rationale:** Durable teardown evidence exposed a real-runtime contract gap
that the synthetic tests did not model. The stopped authorization ledgers and
Envoy logs each contained one valid JSON record, but the current closed parsers
rejected them. Envoy injected the fixed transport headers
`x-envoy-expected-rq-timeout-ms` and `x-envoy-internal`; the decision validator
currently permits only the adversarial-header names even though those client
headers are correctly stripped before authorization. Envoy's JSON access log
also emitted numeric response codes and `null` denial upstream fields, while
the evidence validator requires string response codes and `"-"` sentinels.
Those deterministic mismatches prevent complete joins and make the observed
run ineligible for promotion even though the enforcement response tuple itself
matched expectations.

**Affected artifacts:** Ignored live board
`artifacts/generated/v3b1-task6-live-status.md`; ignored nonpromotable bundle
`artifacts/generated/v3b1-local-envoy/v3b1-f8152ed1b52e33264b9f3339f4eeb8255260703f6c2c62824c3cb2379c76b4b1`;
the archived private central-run journal, raw driver results, and frozen source
bytes under `.tools/v3b1-private/` in worktree
`.worktrees/v3b1-central-proof-v3`; and this lineage source. No failed bundle or
private evidence was staged, committed, or published.

**Unresolved questions:** The evidence contract needs a test-driven correction
for the observed Envoy-added header names, typed JSON access-log values, and the
direct live-copy failure boundary. Because request intent was durably crossed,
a fresh central attempt requires explicit new authorization after that
correction passes review, CI, merge, and synchronization.

**Next gate:** Preserve the failed-run evidence, implement and independently
review a source-level correction using the exact observed public-safe record
shapes, pass the full suite and publication gate, then request explicit approval
for one new clean exactly-once lifecycle. Do not invoke `run` again under the
current authorization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-156 — 2026-09-05 — Runtime evidence source-format design approved

**Input:** Approve the revised correction design after rejecting
post-collection normalization that would weaken raw-source byte binding.

**Interpretation:** Specify a producer-side correction that preserves the V3
schema and legacy verification: classify only the two observed fixed
Envoy-generated headers as transport metadata, make Envoy emit the existing
canonical string/sentinel JSON record directly, and bound ledger availability
polling without providing any path to retry the consequential request.

**Decision status:** Confirmed design approval. Commit `5e71d08` on isolated
branch `codex/v3b1-central-proof-v3` adds the source specification and generated
reader. The specification fixes a shared five-second monotonic evidence-read
deadline, clips subprocess timeouts to its remaining budget, uses an injected
50-millisecond poll interval, preserves exact raw-source attestation, and keeps
the first failed Task 11 run immutable and nonpromotable. No implementation or
additional live request was performed at this checkpoint.

**Rationale:** Producer-side canonical output keeps emitted, frozen, parsed,
joined, published, hashed, and verified bytes identical. A narrow exact
transport-header classification preserves the client-header exclusion boundary,
while a bounded read-only ledger wait addresses availability without touching
drivers, instructions, or HTTP.

**Affected artifacts:**
`docs/superpowers/specs/2026-09-05-v3b1-runtime-evidence-source-format-design.md`
and its generated `.htm` reader in the isolated correction worktree; this
lineage source. The prior failed bundle and private frozen evidence remain
ignored and unchanged.

**Unresolved questions:** The written specification awaits maintainer review.
Implementation tasks and tests have not yet been planned or executed.

**Next gate:** Obtain maintainer approval of the written specification, create
the test-first implementation plan, then execute it through review, CI, merge,
and synchronization before the separately authorized new exactly-once run.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-157 — 2026-09-05 — Evidence correction merged; clean rerun preflight blocked by foreign runtime

**Input:** Approve the written source-format design and implementation plan,
publish the correction, then execute the newly authorized Task 11 proof from
synchronized public `main` with all routine prompts preapproved.

**Interpretation:** Implement the three approved corrections test-first,
require local validation and public CI before runtime use, synchronize the merge,
and start a separate clean proof worktree. Preserve the earlier failed evidence,
never retry its requests, and never mutate a foreign Colima profile.

**Decision status:** Confirmed implementation and publication; runtime proof is
blocked safely before mutation. The correction classifies only the two exact
Envoy-generated transport headers, emits canonical JSON text at the Envoy
producer, and bounds live-ledger availability to one five-second monotonic
deadline with no-follow descriptor, inode, size, and SHA-256 attestation. The
focused 52-test gate, complete 257-test controller module, and full 566-test /
53-reader repository gate passed. Separate specification and quality/security
reviews found no unresolved Critical or Important issue. PR #21 passed both
public CI jobs and merged as `514e910ea9427e0497c4fe8a1ec279b554e75176`;
local `main`, `origin/main`, and the GitHub branch agreed. A clean worktree on
that exact commit passed the full gate and installed and verified the locked
toolchain. Its controller `preflight` then rejected the currently `Running`
foreign non-dedicated profile before creating the dedicated profile, topology,
driver instruction, request intent, or HTTP request.

**Rationale:** The merged correction preserves source-byte provenance and the
closed V3 schema instead of normalizing evidence after collection. The live
controller is also correct to refuse coexistence with a running foreign
runtime: stopping or changing that profile would violate the explicit
foreign-resource noninterference boundary.

**Affected artifacts:** Merged correction design, plan, code, tests,
documentation, and generated readers through PR #21; clean ignored live board
in `.worktrees/v3b1-central-proof-v3-rerun`; preserved failed-run and
request-free worktrees; and this lineage source. No new run ID, owned runtime
object, request instruction, request intent, HTTP action, or public proof bundle
was created.

**Unresolved questions:** The foreign profile must be returned to `Stopped` by
its owner or existing workflow. KIL is not authorized to mutate it, and the
central proof cannot begin while it is running.

**Next gate:** After external confirmation that the foreign profile is stopped,
rerun the controller's read-only `preflight` in the clean worktree. If it passes,
continue with exactly one `up`, one central `run`, and mandatory `down`, with no
request retry.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-158 — 2026-09-05 — Central local-Envoy proof accepted and published with dedicated-profile ownership

**Input:** Complete the newly authorized V3B-1 proof, publish its accepted
evidence, and make the project safe for manual backup and host shutdown. The
user further required KIL to own a unique `kil-v3-lab` Colima profile and to
start or stop only that profile because other profiles serve other projects.

**Interpretation:** Execute the authorized request path once, never retry after
request intent, complete mandatory teardown under every outcome, publish only
verified public evidence, and make dedicated-profile isolation an explicit
durable contract. Do not start, stop, delete, or otherwise mutate any foreign
Colima profile.

**Decision status:** Confirmed execution and publication. Source
`514e910ea9427e0497c4fe8a1ec279b554e75176` produced run
`v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94`.
The one central `run` reached all three terminal request states and was not
repeated after a post-request Docker copy visibility error. Mandatory `down`
froze the authoritative sources and published a complete bundle accepted by
the offline verifier as an observed intermediate local-Envoy boundary result:
`permit / permit / deny`, HTTP `200 / 200 / 403`, and target markers
`1 / 1 / 0`, with exactly one attempt per track and no retry. All nine source
legs, exact 15-container/6-network teardown, checksums, and equal pseudonymous
foreign-resource snapshots passed. The result remains `not_promoted` and does
not establish Kind/Calico or NetworkPolicy validation, historical prevention,
or production performance. PR #22 passed both public CI jobs and merged as
`fd3ce6bb24f5c63644c07cfe1e34b244f02ff617`; local and remote `main` were
synchronized to that commit. Final read-only shutdown checks confirmed that
the `kil-v3-lab` profile is absent and that the accepted worktree has no active
lifecycle state, journal, or readiness poison.

**Rationale:** Teardown recovery is authoritative because it froze the same
owned container sources after the single request sequence and completed before
publication. The dedicated profile name is fixed and uniquely KIL-owned; every
other profile is foreign state and remains outside KIL mutation authority. A
separate foreign profile that appeared after the bundle's bound lifecycle
window affected only an optional post-teardown readback and did not change the
accepted evidence or teardown result.

**Affected artifacts:** Accepted public evidence bundle, README and Envoy
adapter documentation, V3 progress and paper, execution plans, generated HTML
readers, documentation regression tests, ignored live status, preserved private
worktrees, and this append-only lineage source. No foreign Colima profile was
mutated.

**Unresolved questions:** The user will choose and perform the offline backup
manually, including the retention decision for ignored private failed-run and
accepted-run worktree evidence.

**Next gate:** The user may perform the manual offline backup and shut down the
host. After backup and restart, V3B-2 Kind/Calico design or V3C
repetition/performance remains a separate future gate.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-159 — 2026-09-06 — Post-backup continuation re-established at the V3B-2/V3C decision gate

**Input:** Continue from the safe-shutdown checkpoint after the accepted V3B-1
proof was merged and prepared for manual backup.

**Interpretation:** Re-establish repository and runtime state before selecting
or designing the next experimental increment. Preserve all user-local work and
private evidence worktrees, and continue enforcing the rule that KIL may mutate
only its unique `kil-v3-lab` Colima profile.

**Decision status:** Confirmed checkpoint recovery; next-gate selection remains
open. Local `main` and `origin/main` remain at merged proof commit
`fd3ce6bb24f5c63644c07cfe1e34b244f02ff617`. The user-local lineage sources and
`Inputs/` remain present, the preserved V3B-1 worktrees remain registered, and
the read-only Colima inventory confirms `kil-v3-lab` is absent. Existing design
records identify V3B-2 Kind/Calico cluster validation and V3C repetition and
performance as separate future gates.

**Rationale:** The next phase changes experimental architecture and evidence
scope, so it requires an explicit gate choice and design review rather than
silently extending the accepted local-Envoy result. Runtime noninterference is
preserved by keeping all foreign Colima profiles outside KIL authority.

**Affected artifacts:** This append-only lineage source only. No repository
implementation, lab runtime, Colima profile, or published evidence changed.

**Unresolved questions:** Whether to design V3B-2 Kind/Calico validation next or
move first to the independent V3C repetition/performance gate; and whether the
user wants a visual architecture companion during design.

**Next gate:** Resolve the visual-companion preference, then select the next
experimental increment and compare design approaches before writing a spec.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-160 — 2026-09-06 — Visual design companion approved for next-gate architecture work

**Input:** Approve use of the browser-based visual companion while continuing
from the V3B-1 completion checkpoint.

**Interpretation:** Use diagrams when spatial architecture or data flow is
materially clearer visually, while keeping requirements, scope, and technical
tradeoff decisions in the main conversation.

**Decision status:** Confirmed process preference. No experimental gate has yet
been selected and no visual server, implementation, runtime, or Colima profile
has been started.

**Rationale:** The next likely work involves cluster topology and evidence flow,
which can benefit from diagrams, but the first choice between V3B-2 cluster
validation and V3C repetition/performance is conceptual and should remain a
textual decision.

**Affected artifacts:** This append-only lineage source only.

**Unresolved questions:** Which independent gate should be designed next.

**Next gate:** Select V3B-2 or V3C, then compare two or three bounded design
approaches before presenting the chosen architecture.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-161 — 2026-09-06 — V3B-2 selected before V3C

**Input:** Select V3B-2 Kind/Calico cluster validation next, followed by V3C
repetition and performance measurement.

**Interpretation:** Treat the phases as dependent gates: first establish the
cluster transport and NetworkPolicy enforcement boundary, then repeat and
measure the accepted cluster workload. Do not use the local-Envoy-only result
as the final performance substrate.

**Decision status:** Confirmed sequence: V3B-2, then V3C. V3B-2 design scope
and staging remain under discussion; no implementation or runtime action is
authorized by this sequencing decision.

**Rationale:** Measurements become materially more relevant when they describe
the intended Kind/Calico enforcement topology. This preserves the evidence
hierarchy and prevents local-boundary timing from being presented as
cluster-level performance.

**Affected artifacts:** This append-only lineage source only.

**Unresolved questions:** Whether V3B-2 should accept nominal cluster parity and
the complete failure matrix in one gate or as two ordered sub-gates.

**Next gate:** Resolve V3B-2 acceptance staging, then compare bounded topology
and evidence-collection approaches.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-162 — 2026-09-06 — V3B-2 staged-gate topology approaches presented

**Input:** Proceed with the recommended V3B-2 staging after selecting V3B-2
before V3C.

**Interpretation:** Treat nominal cluster parity and the functional failure
matrix as two ordered V3B-2 sub-gates, and compare deployment topologies before
fixing the new cluster evidence contract.

**Decision status:** Confirmed two-sub-gate staging; topology selection is
pending user review. Three approaches were presented: a recommended
three-namespace mirror of the frozen V3B-1 tracks in one Kind cluster, a compact
shared-service topology, and a maximum-isolation per-track multi-cluster
topology. The first preserves the approved single-cluster contract and provides
the cleanest V3B-1 parity and NetworkPolicy evidence.

**Rationale:** Separating nominal parity from failure injection prevents a
failure-case anomaly from obscuring whether the base Kind/Calico deployment is
sound. Mirrored namespaces preserve comparison independence without expanding
the Colima ownership boundary beyond `kil-v3-lab`.

**Affected artifacts:** Ignored visual-companion screen under
`.superpowers/brainstorm/40366-1788698387/` and this append-only lineage source.
No tracked design, implementation, cluster, or Colima profile changed.

**Unresolved questions:** User selection or revision of the topology approach;
the exact V3B-2a evidence acquisition boundary remains to be designed.

**Next gate:** Confirm a topology, then present the architecture and nominal
evidence-flow design section for approval.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-163 — 2026-09-06 — V3B-2 namespace-isolated mirror selected; architecture section presented

**Input:** Approve topology approach A for V3B-2.

**Interpretation:** Design one `kil-v3-lab` Kind cluster with three
infrastructure-fixed namespaces that mirror the V3B-1 baseline, signed-state,
and local-reduction tracks. Keep the controller outside the consequential HTTP
path and bind nominal parity before designing failure injection.

**Decision status:** Confirmed topology approach; detailed architecture section
is proposed for review. The proposal uses one digest-pinned Kind node, vendored
Calico, deny-first NetworkPolicy, one driver/Envoy/authz/target chain per
namespace, no public Service, one canonical instruction per track through
`kubectl attach`, bounded pod-evidence freeze, and exact KIL-owned teardown.
Only `kil-v3-lab` may be created or deleted; all foreign profiles remain outside
KIL authority.

**Rationale:** This topology gives the strongest causal comparison with the
accepted V3B-1 result while adding the intended Kubernetes and NetworkPolicy
boundary. Per-track namespaces avoid shared authorization state, and a
host-controlled instruction with an in-cluster request keeps the controller out
of the tested HTTP enforcement path.

**Affected artifacts:** Ignored V3B-2a architecture screen in the approved
visual-companion session and this append-only lineage source. No tracked spec,
implementation, runtime, Kind cluster, or Colima profile changed.

**Unresolved questions:** User approval of the architecture section; exact
evidence schemas, failure behavior, and tests remain to be designed.

**Next gate:** Obtain architecture-section approval, then present the nominal
evidence contract and acceptance criteria.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-164 — 2026-09-06 — V3B-2a architecture approved; nominal evidence contract presented

**Input:** Approve the one-cluster, three-namespace V3B-2a architecture and
continue with the next design actions.

**Interpretation:** Fix the selected architecture and define the evidence that
must be durably cross-bound before teardown, the exact nominal acceptance
tuple, and the claims that remain excluded until V3B-2b and V3C.

**Decision status:** Confirmed architecture; evidence-contract approval is
pending. The proposed contract binds reviewed source and tool identities,
digest-pinned node and Calico assets, cluster/namespace/Pod identities, image
IDs, Services, policies, the existing driver/decision/Envoy/target proof, exact
teardown, and pseudonymous foreign-profile equality. Proposed V3B-2a acceptance
requires one attempt per track with `permit / permit / deny`, HTTP
`200 / 200 / 403`, and target markers `1 / 1 / 0`. The proposed bundle remains
`not_promoted` with class `intermediate_provisional_kind_calico_nominal`.

**Rationale:** Nominal traffic plus a closed policy inventory establishes that
the frozen semantic workload operates through the intended cluster boundary,
while reserving adversarial policy and component-failure claims for the fresh
V3B-2b lifecycle. Separate immutable bundles preserve causal clarity.

**Affected artifacts:** Updated ignored visual-companion screen and this
append-only lineage source. No tracked design, implementation, request, cluster,
or Colima profile changed.

**Unresolved questions:** User approval or revision of the V3B-2a evidence and
claim boundary; detailed error handling and V3B-2b case inventory remain to be
designed.

**Next gate:** Approve the nominal evidence contract, then present failure and
recovery behavior plus the test strategy.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-165 — 2026-09-06 — V3B-2a evidence contract approved; failure strategy presented

**Input:** Approve the proposed nominal evidence contract and continue with the
next design section.

**Interpretation:** Freeze the nominal evidence and claim boundary, then define
the V3B-2 fail-closed lifecycle, ordered V3B-2b case groups, recovery authority,
and pre-runtime test gates.

**Decision status:** Confirmed V3B-2a evidence contract. Its proposed public
class remains `intermediate_provisional_kind_calico_nominal` with
`not_promoted`, exact semantic tuple and Kubernetes/Calico identity joins,
exact KIL-owned teardown, and foreign-profile equality. The failure/recovery
section is proposed for review: policy-isolation probes, state/authority
failures, availability/evidence failures, terminal no-retry behavior after case
intent, and bounded recovery limited to journal-bound KIL resources.

**Rationale:** The staged contract distinguishes nominal cluster parity from a
complete failure-matrix result. It also prevents a partial or poisoned case
from being retried or obscuring an incomplete matrix while ensuring cleanup can
continue without discovery-based deletion.

**Affected artifacts:** Ignored failure/recovery visual-companion screen and
this append-only lineage source. No tracked specification, implementation,
request, cluster, or Colima profile changed.

**Unresolved questions:** User approval of the failure groups, terminal-run
behavior, recovery authority, and test/publication gates.

**Next gate:** Approve the final design section, then write and self-review the
complete V3B-2 design specification for explicit user review.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-166 — 2026-09-06 — Complete V3B-2 design specification committed for review

**Input:** Approve the final V3B-2 failure, recovery, and testing section and
continue with the next action.

**Interpretation:** Consolidate the approved design sections into a complete
written specification, self-review the closed contracts, generate its reader,
validate the repository, and stop at the explicit written-spec review gate
before implementation planning.

**Decision status:** Confirmed design specification committed as `91d1045` on
the isolated `codex/v3b2-kind-calico-design` branch. The specification fixes
V3B-2a nominal parity before the V3B-2b failure campaign, one KIL-owned
`kil-v3-lab` Colima profile, one single-node Kind cluster with three track
namespaces, an in-cluster one-shot driver, deny-first Calico policy, exact
Kubernetes and V3B-1 semantic joins, terminal no-retry behavior after intent,
and exact teardown with foreign-profile noninterference. V3B-2 remains
immutable and `not_promoted`; a later V3C publication must use a separate
promotion index.

**Rationale:** Self-review closed ambiguities around coexistence with running
foreign profiles, the waiting driver Pod, disabled default CNI and fixed CIDRs,
the system-namespace allowlist, cluster-incarnation identity, clean lifecycle
isolation for terminal failure cases, immutable promotion semantics, explicit
schema names, and command-level proof that every Colima mutation names only
`kil-v3-lab`. Full validation passed 567 tests and verified 55 generated
Markdown readers; the staged diff was whitespace-clean.

**Affected artifacts:** Added the V3B-2 design source and generated reader under
`docs/superpowers/specs/` in the isolated design worktree and appended this
lineage entry in the main checkout. The ignored visual companion remains local.
No implementation, runtime, Kind cluster, or Colima profile changed; existing
main-checkout lineage HTML and `Inputs/` changes were not modified.

**Unresolved questions:** User review of the complete written specification.
The implementation plan has not been written and no implementation has begun.

**Next gate:** Obtain explicit approval of the written specification, then use
the writing-plans workflow to produce the V3B-2 implementation plan.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-167 — 2026-09-06 — V3B-2a implementation plan committed

**Input:** Approve the complete V3B-2 written specification and proceed to the
next phase.

**Interpretation:** Apply the writing-plans workflow, split the sequential
V3B-2 work at its accepted causal gate, and produce a test-first implementation
plan for V3B-2a static implementation, request-free validation, and the one-shot
nominal proof. Leave the V3B-2b failure campaign for a separate plan after
V3B-2a acceptance.

**Decision status:** Confirmed implementation plan committed as `1df30df` on
`codex/v3b2-kind-calico-design`. The plan defines ten tasks across closed
profiles and schemas, deterministic manifests, Kubernetes and policy inventory,
journal-bound recovery, evidence and offline verification, a thin controller,
documentation, review and synchronization, request-free execution, and nominal
execution. It preserves `v3b1-central-request` scoped by track and requires
every Colima mutation to name only `kil-v3-lab`.

**Rationale:** The split makes V3B-2a independently testable and publicly
reviewable before V3B-2b introduces multi-lifecycle campaign behavior. Planning
resolved the Calico v3.32.0 upstream manifest at SHA-256
`bccabc607685551db918f66da724893eca3e69a50c5a3e3077029b02dbab8d35`,
three Quay index digests, and a deterministic digest-pinned manifest at
`ac5ab7451dda57cfbf47d584ee901b896b1a9ff388d95b6f01b59f1e1130fdfa`.
Self-review corrected the application-object count to 60, included Kind's
`local-path-storage` system namespace, and made Docker/Kind environment binding
explicit. Fresh validation passed 567 tests and verified 56 readers.

**Affected artifacts:** Added the V3B-2a implementation-plan source and
generated reader under `docs/superpowers/plans/` in the isolated design
worktree, and appended this lineage entry in the main checkout. The planning
fetch used only `/private/tmp`. No implementation, runtime, cluster, or Colima
profile changed; existing main-checkout lineage HTML and `Inputs/` changes were
left untouched.

**Unresolved questions:** Execution workflow selection. V3B-2a implementation
has not started, no runtime authorization has been exercised, and V3B-2b and
V3C remain closed behind their accepted gates.

**Next gate:** Choose subagent-driven task execution with review between tasks,
or inline execution in this session with batch checkpoints, then begin Task 1
test-first in a fresh implementation worktree.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-168 — 2026-09-06 — V3B-2a static implementation through evidence; controller rework paused

**Input:** Execute the approved V3B-2a plan with subagent-driven development,
continue through successive review gates, preserve the unique `kil-v3-lab`
Colima boundary, and pause until 19:30 local time before resuming.

**Interpretation:** Implement each static task test-first in the isolated
`codex/v3b2-kind-calico-implementation` worktree, require independent
specification and quality acceptance, and keep all Colima, Docker, Kind, and
Kubernetes actions simulated until the live gates. Pause the active Task 6
rework without discarding its uncommitted state and schedule the same task to
resume in this thread.

**Decision status:** Confirmed Tasks 1 through 5 are implemented and accepted.
The reviewed commits cover the fixed profile/contracts and vendored Calico,
the exact 60-object manifest and deny-first policy graph, closed runtime
inventory, durable journal/recovery authority, and bounded semantic evidence
publication. Task 6's first controller commit was rejected by specification
review for synthetic live observations and is being reworked. Two confirmed
design amendments now bind `lifecycle_mode` in the journal and permit closed
`failed` or permanently nonpromotable `abandoned_for_teardown` transitions
only under the documented proof and ownership conditions. The lifecycle-mode
amendment is committed as `dda765c`; the teardown amendment is edited but not
yet committed pending resumed verification.

**Rationale:** Repeated adversarial reviews closed attach/readiness semantics,
non-root volume ownership, exact Calico container multiplicity, expected-state
mirroring, malformed-input totalization, UID-preconditioned deletion,
concurrent journal appends, symlink ancestry, semantic repaired-hash attacks,
foreign-name privacy, and post-rename races. Task 6 must consume those trusted
boundaries directly: strict inventory parsing, real V3B-1 readiness/results,
stable source capture, exact image import and Calico readiness, postcondition-
checked recovery, and prepared publication. The latest completed full static
gate before the controller rework passed 711 tests and 56 Markdown readers;
the interrupted rework reported 136 focused V3B-2 and 285 V3B-1 tests green.

**Affected artifacts:** In the isolated implementation worktree, Tasks 1–5
added or changed the V3B-2 contracts, manifests, inventory, journal, evidence,
vendored Calico/profile, and their tests. Task 6 currently has uncommitted
integration changes across controller, inventory, journal, evidence, CLI, and
tests. This entry alone was appended in the main checkout; its existing lineage
HTML and `Inputs/` changes remain untouched. No live runtime, cluster, Docker
context, or Colima profile was started, stopped, deleted, or modified.

**Unresolved questions:** Complete and independently review the Task 6
controller rework, regenerate the two design/plan readers after the amendments,
then finish Task 7 static acceptance. Request-free and nominal live gates have
not begun; V3B-2b and V3C remain closed.

**Next gate:** At 19:30 America/Los_Angeles, resume the interrupted Task 6
implementer from the uncommitted worktree, complete the governed uncertain-
mutation teardown path and recovery matrix, then repeat specification, Task
3–5 regression, quality, and full static validation before Task 7.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-169 — 2026-09-07 — Resume Task 6; close real-runtime integration gaps before live testing

**Input:** Resume the paused V3B-2a implementation with the previously approved
subagent-driven workflow and exclusive ownership of `kil-v3-lab`.

**Interpretation:** Continue the preserved controller rework in the isolated
implementation worktree. Static implementation and independent review remain
prerequisites to the request-free lifecycle; resumption does not bypass those
gates or authorize interference with foreign Colima profiles.

**Decision status:** Resumed Task 6. The implementer reports 78 focused journal
and controller tests passing at the governed uncertain-mutation teardown
checkpoint; this is not independent acceptance of the full controller. Root
regenerated the previously stale plan/design readers, then clarified the source-
preservation requirements in their Markdown sources. Those later clarifications
still require reader regeneration. Task 6 remains in progress and uncommitted.

**Rationale:** Read-only inspection identified an exact retained accepted KIL
image archive with SHA-256
`07c12f338c7d764812ef6271ec8942f0535d05019288f4df1e1b54f6cd75e4b6`.
Its OCI manifest identity matches the accepted V3B-1 image, but image identity
alone does not put bytes into a fresh owned Docker daemon or Kind node.
Further integration checks require actual raw Kubernetes responses, readiness
before one-shot driver connections, source-preserving driver cancellation and
Envoy quiescence, real authorization/target file-ledger reads, and stable
capture-time workload identities. Empty stdout cannot substitute for those
ledgers, and deleting their Pods before freeze destroys the required sources.
An independent in-process smoke check using the real authorization adapter,
rendered fixtures, and controller-issued instructions returned the expected
`200 / 200 / 403` and `permit / permit / deny` tuple. This is static semantic
evidence only, not Kind/Calico or NetworkPolicy validation.

**Affected artifacts:** Controller, journal, inventory, evidence, CLI, and tests
remain under revision in `.worktrees/v3b2-kind-calico-implementation`; plan and
design sources there now explicitly preserve evidence through cancellation and
quiescence. This append is the only main-checkout edit in the resumed turn so
far; existing lineage HTML and `Inputs/` changes remain untouched. No live
Colima, Docker, Kind, or Kubernetes mutation was performed at this checkpoint.

**Unresolved questions:** Complete real-runtime integration, regenerate readers,
then independently review and validate Task 6. The exact archive will be staged
to a fixed content-verified input path before the eventual live gate, without
using any foreign Docker daemon. Request-free and nominal live execution,
V3B-2b acceptance, and V3C remain uncompleted.

**Next gate:** Finish the controller's image-import and source-preserving
lifecycle integration with representative runtime fixtures; require independent
specification and quality reviews and full static validation before Task 7.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-170 — 2026-09-07 — Task 6 full static gate rejected; shared-proof corrective pass

**Input:** Continue the resumed V3B-2a implementation through independent review
without using any Colima profile other than `kil-v3-lab`.

**Interpretation:** Passing simulated tests is necessary but does not establish
the real-runtime contracts. Preserve the implementation checkpoint, investigate
repeated review failures at their shared boundaries, and correct those
boundaries before permitting Task 7 or any live experiment.

**Decision status:** Root independently ran `make validate` in the isolated
implementation worktree: 753 tests passed in 47.872 seconds, all 56 readers
were current, and diff hygiene passed. Independent specification review then
returned **NOT COMPLIANT**. No Task 6 acceptance, merge, or live authorization
gate was passed. A corrective section was added to the existing approved plan,
readers were regenerated, and a fresh implementer was assigned that bounded
correction using the already selected subagent workflow.

**Rationale:** Review confirmed that the raw inventory omitted pinned Calico
and Kind objects; expected inventory largely mirrored observations; normal and
recovery paths could record completion without exact postcondition evidence;
arbitrary command failure could be mislabeled absence; inherited process
environment could override Docker authority; and failure cleanup could advance
missing drivers. EOF cancellation incorrectly used a not-applied failure event
for an observed nonzero terminal mutation. Capture-time identities and full
bytes were not carried into the bundle. A further verified interface defect
forwarded real producer records into incompatible reduced schemas; the test
runner masked this by supplying already-reduced synthetic records.

The common correction is an immutable expected context and operation-specific
observation validator shared by normal execution and recovery, with durable
proof-bound terminal events and a permanent teardown-only failure state. Actual
producer adapters must derive reduced semantic joins while retaining and
binding raw capture bytes, current UID/resourceVersion/container incarnation,
and individual source lengths/hashes. The corrective plan enumerates these
requirements and the per-event proof/recovery matrix. It does not weaken the
approved semantics or expand the live-testing scope.

**Affected artifacts:** The implementation worktree retains its unstaged
controller, journal, inventory, manifest, evidence, CLI, and test changes;
the plan/design sources and generated readers also remain modified. The new
corrective pass may add a focused proof module and tests. Main-checkout edits
remain append-only lineage entries; existing lineage HTML and `Inputs/` changes
are preserved. Read-only source research verified the pinned Envoy drain
handler, and Bash syntax checks passed without executing control scripts. The
safety hook flagged the helper's fixed loopback TCP syntax; no guard was
bypassed and no live control helper was executed.

**Unresolved questions:** Complete and independently review the shared-proof,
authority, actual-inventory, and raw-source-adapter corrections. The source-
preserving control path still requires eventual guarded live validation after
the static/review/merge gates. No live Colima, Docker, Kind, or Kubernetes
mutation occurred in this turn at this checkpoint.

**Next gate:** Targeted RED/GREEN verification of the corrective pass, a fresh
complete static gate, independent specification acceptance, and then quality
review before Task 7. Request-free and nominal live runs remain pending;
V3B-2b and V3C remain closed.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-171 — 2026-09-07 — Resume bounded Task 6 integration and resolve pinned inputs

**Input:** User requested "resume" after the pause, retaining the exclusive
`kil-v3-lab` ownership constraint and approved subagent workflow.

**Interpretation:** Continue the unfinished corrective work, not live testing
or acceptance of the previous simulated checkpoint. Divide the incomplete
correction into smaller integration and resource-validation slices.

**Decision status:** The prior corrective implementer explicitly returned
NOT DONE with a partial shared proof kernel and source adapters. It was
redispatched only to integrate normal/recovery terminal writing, immutable
expected inputs, and exact teardown authority. Read-only researchers resolved
pinned ARM64 image identities and the Kind/Kubernetes bootstrap inventory.
Task 6 remains unaccepted at this checkpoint.

**Rationale:** Root independently verified all 38 canonical Calico JSON
documents against a safe parse of the checksummed YAML; projection SHA-256 is
`de76213b8097d55a674cbe88ef9ac349317b067fb3c6fc326d4280d17c7104a8`.
Registry index, platform-manifest, and container-config digests must remain
distinct. Tagged source research identified the finite system ConfigMap and
ServiceAccount sets plus owner-chain requirements absent from earlier fixtures.
The old V3B-2 profile-only start command omitted explicit non-activation and
isolation settings. The correction preserves the accepted V3B-1 4-CPU,
8-GiB-memory, 60-GiB-data-disk configuration and explicitly disables global
context activation, SSH-config generation, template inheritance, and host
mounts. V3B-2 transfers inputs through bound command streams, so no shared
staging mount is required. No foreign profile is to be resized or altered.

**Affected artifacts:** Implementation-worktree plan/design sources now record
the required teardown latch, proof-bound terminals, immutable expected-input
commitment, safe Calico projection, isolation settings, and pinned bootstrap
inventory. Controller/journal/proof integration is still under revision.
Existing main-checkout lineage HTML and `Inputs/` remain untouched; this entry
is append-only. No live Colima, Docker, Kind, or Kubernetes mutation occurred.

**Unresolved questions:** Finish integration, explicit server-default and
generated-owner validation, manifest/config identity use, source-preserving
quiescence classification, and incomplete-evidence diagnostics. Passing partial
tests does not resolve these requirements or establish the live boundary.

**Next gate:** Stable corrected Task 6 tree, fresh full static verification,
independent specification and quality acceptance, then Task 7. Live request-free
and nominal gates, V3B-2b, and V3C remain pending.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-172 — 2026-09-07 — Shared-proof integration slice verified; whole Task 6 still open

**Input:** Continue the approved resumed implementation through review, with
all runtime ownership confined to `kil-v3-lab`.

**Interpretation:** Verify a bounded completion/recovery integration slice
before completing the remaining resource and evidence contracts. Slice
acceptance does not reopen the live gate or supersede the earlier rejection
of the whole Task 6 checkpoint.

**Decision status:** Root independently ran the stable contracts, proofs,
journal, and observed-lifecycle modules: **113 tests passed in 9.615 seconds**.
All 56 implementation-worktree Markdown readers regenerated and diff hygiene
passed. Independent specification rereview accepted this bounded slice;
independent quality review is active. No full-suite or Task 6 acceptance claim
is made. The older controller suite was stopped after errors and is explicitly
not a passing checkpoint.

**Rationale:** Normal and recovery completion now share registry-bound actual
observations, immutable expected inputs, durable proof-before-terminal writes,
and complete terminal-event revalidation. Repaired journal event labels cannot
turn failure proofs into success. The permanent teardown latch, profile-only
cleanup, exact interrupted-creation identity, and same-container cancellation
have focused regression coverage. Specification review caught discarded output
from timed-out commands; the fix preserves original bytes, including malformed
UTF-8, with explicit unsuccessful timeout/prefix-only transport codes. The
reviewer independently reran that reproducer and four timeout regressions.

Additional tagged-source tracing distinguished Docker/CRI config IDs from
Kubernetes public Pod imageID, which uses the runtime ImageRef and may contain
the repository index digest. The plan now records that distinction alongside
verified ARM64 index/manifest/config chains and kind/path-specific Kubernetes
defaulting and omission rules.

**Affected artifacts:** Controller, journal, proof/contracts, and focused tests
in the implementation worktree remain uncommitted. Plan/design sources and
readers record the new contracts and follow-on inputs. Root alone appends the
main lineage source; pre-existing main lineage HTML and `Inputs/` are preserved.
No live Colima, Docker, Kind, or Kubernetes operation was performed.

**Unresolved questions:** Complete saved-profile configuration and actual
Colima/Lima active-state absence proofs; finite bootstrap and generated-owner
validation; server-default normalization and image representation joins;
explicit Envoy refusal evidence and partial-capture diagnostics/publication.
Readiness is deliberately fail-closed while these contracts are incomplete.

**Next gate:** Quality acceptance of this slice, remaining bounded Task 6
corrections, a fresh full static gate and whole-task specification/quality
review, then Task 7. Request-free/nominal live runs, V3B-2b, and V3C remain gated.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-173 — 2026-09-07 — Proof slice accepted; exact profile-state correction underway

**Input:** Continue the user's approved resumed V3B-2a work, preserving the
exclusive `kil-v3-lab` runtime scope and manual-backup boundary.

**Interpretation:** Finish the bounded Task 6 corrections under the selected
subagent implementation and independent two-stage review workflow. Approval
of one slice does not imply approval of the unfinished controller as a whole.

**Decision status:** Independent specification and quality reviewers accepted
the shared-proof integration slice. Root's fresh focused run passed **118 tests
in 11.063 seconds**. The quality review's large-proof replay and interrupted
write findings were fixed and independently reverified. All 56 worktree
Markdown readers regenerated. Whole Task 6 and its full static gate remain open.

**Rationale:** A consistent proof-envelope bound and atomic no-replace
publication prevent successful writes that cannot later reload and partial
writes that poison recovery. The next bounded slice must replace ambient-home
authority with passwd-derived paths, verify both saved profile configurations,
bind exact VM and disk identities, and require actual owned-state absence after
deletion. Colima's conditional data-disk deletion makes exit status alone
insufficient; scoped orphan recovery requires existing creation provenance.

**Affected artifacts:** Implementation worktree proof/controller/journal tests,
plan section B.3 and generated readers; a fresh implementer owns the new focused
profile-state module and its integration/tests. Root retains documentation and
Git ownership. Main's pre-existing lineage HTML and `Inputs/` remain untouched.
No live Colima, Docker, Kind, or Kubernetes operations were performed.

**Unresolved questions:** Profile-state implementation/review; finite runtime
resource and default-normalization contracts; producer-instruction joins and
partial-capture diagnostics. Readiness remains deliberately fail-closed.

**Next gate:** Profile-state specification then quality acceptance, remaining
Task 6 slices and full static/review gates, then Task 7. Live validation,
V3B-2b, and V3C remain closed.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-174 — 2026-09-07 — Clarify source-association and partial-diagnostic contracts

**Input:** Continue correcting Task 6's actual producer interfaces while the
profile-state implementation proceeds; preserve the approved design's complete
or calibrated failure publication requirement.

**Interpretation:** A valid hexadecimal commitment is not sufficient evidence
of its relationship to saved instruction bytes, a journal event, or the actual
captured driver terminal. Missing capture must not become either synthetic empty
evidence or a permanent obstacle to ownership-proved cleanup.

**Decision status:** Adopted corrective plan sections C.1–C.3 after read-only
source-contract analysis. These are implementation requirements, not completed
capabilities. Cases will separately bind actual instruction digests; private
replay will join persisted instruction, case, attach bytes, journal terminal,
and captured terminal. The existing shared driver protocol remains unchanged.
The supported claim is controller/journal-bound association, not a producer
attestation that it consumed a particular instruction digest.

**Rationale:** Public verification can rederive safe case and terminal
commitments, but cannot recompute a sensitive private instruction without its
bytes. Explicit public projection and an honest verification boundary are
required. Partial capture receives closed per-source statuses and a teardown-only
classification. A separate nonpromotable public partial-diagnostic result within
the same eleven files remains required before Task 6 acceptance; an intermediate
private-only cleanup slice does not discharge that requirement. Exact Envoy
connection refusal must come from the producer's actual observation, not a
generic TCP failure; existing four-zero-gauge proof rules remain unchanged.

**Affected artifacts:** Corrective plan C.1–C.3, test-fixture guidance in D, and
regenerated worktree readers. Main lineage source only is appended here.
Profile-state implementation is ongoing and not yet reviewed. No live runtime
operations or Git mutations were performed.

**Unresolved questions:** Complete and review all remaining integrations. For
the profile slice, an orphan disk with unproved absence of references from other
Lima instances must require manual recovery; it must not trigger commands
against those instances. Normal exact owned cleanup must still support unrelated
profiles being present. This conservative fallback boundary requires explicit
tests and must not be misreported as a confirmed foreign reference.

**Next gate:** Profile-state integration and independent reviews, remaining
resource and evidence corrections, whole Task 6 static and review acceptance.
No live, V3B-2b, or V3C gate is opened.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-175 — 2026-09-07 — Profile integration tested; disk-format review correction required

**Input:** Verify the bounded B.3 profile-state implementation before continuing
the approved Task 6 correction sequence.

**Interpretation:** Focused tests support implementation progress, but independent
review must also challenge the exact conditions that authorize owned mutation.

**Decision status:** Root independently passed **139 focused tests in 15.417
seconds**; the specification reviewer independently passed the same 139 tests in
15.472 seconds. The reviewer nevertheless rejected slice acceptance for one
confirmed disk-format defect. Correction is underway; quality review has not
opened, and neither the slice nor whole Task 6 is accepted.

**Rationale:** The state observer classified every non-QCOW2 header as raw.
Replacing a creation-bound test disk's initial bytes with a VHDX signature while
preserving its inode and size left deletion authorized. Pinned Lima recognizes
additional image-container formats before falling back to raw. Unsupported
formats must remain manual recovery. This correction concerns image-container
metadata and unreadable/truncated observations, not a filesystem-content audit
or hashing a running guest's changing disk.

**Affected artifacts:** New profile-state module/tests and controller, registry,
journal, and temporary-home fixture integration remain uncommitted. The plan
records CLI defaults versus template defaults, conservative orphan boundaries,
and a separate focused API-default normalization module for the next resource
slice. All 56 worktree readers regenerated; main's prior dirty HTML and `Inputs/`
remain preserved. No live runtime operations or Git mutations occurred.

**Unresolved questions:** Disk-format correction and specification rereview,
then independent quality review; finite resource/defaulting and actual producer
evidence contracts remain incomplete. The Envoy refusal contract may use exact
bounded C-locale Bash diagnostics, but does not claim numeric errno output or
unobserved compatibility with the pinned image; unfamiliar live grammar must
fail closed.

**Next gate:** Correct and independently reverify B.3, then complete remaining
Task 6 slices and the full static/review gate. Readiness remains fail-closed;
live testing, V3B-2b, and V3C remain gated.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-176 — 2026-09-07 — Profile disk correction passes specification rereview

**Input:** Correct and reverify the disk-format mutation-authority defect found
in the bounded profile-state slice.

**Interpretation:** Match the pinned image reader's bounded format probes and
revalidate their actual retained bytes during recovery. Ordinary raw guest-sector
changes must not be mistaken for a changed resource identity.

**Decision status:** Independent specification rereview accepted B.3 after the
correction. Root passed **143 focused tests in 24.781 seconds**; the reviewer
independently passed 143 tests in 23.970 seconds and confirmed the original
normal-delete and orphan reproductions both return unknown, issue zero mutations,
and retain the disk. Independent quality review is now active. Whole Task 6
remains incomplete and unaccepted.

**Rationale:** Complete 512-byte probes are retained and independently classified
again during pure proof replay. All seven pinned non-raw format families and ten
signatures were checked against tagged sources. Unsupported or incomplete probes
cannot authorize deletion. The pinned stub probes inspect the first sector, not
a footer; this deliberately remains bounded container-format validation rather
than a guest filesystem audit. An invalid orphan observation now preserves
recovery material and returns unknown instead of escaping through cleanup.

**Affected artifacts:** Profile-state module, controller cleanup handling and
focused regressions; plan source links and regenerated readers. All work remains
uncommitted. Main's pre-existing HTML and `Inputs/` remain untouched. No live
Colima, Docker, Kind, or Kubernetes command was executed.

**Unresolved questions:** Quality acceptance of B.3; Kubernetes API defaulting,
finite generated-resource ownership, source/result association, calibrated
partial diagnostics, and real Envoy refusal producer behavior remain open.

**Next gate:** Close B.3 quality review, then the remaining bounded Task 6
corrections and whole-task static/specification/quality gates. No live test,
V3B-2b, or V3C phase is opened.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-177 — 2026-09-07 — Quality review requires fresh startup and coherent capture checks

**Input:** Independent quality review of the specification-accepted B.3 slice.

**Interpretation:** Keep the slice open until both review stages accept it.
Ordinary focused success does not override counterexamples to mutation authority
or retained-proof consistency.

**Decision status:** Quality review returned **With Fixes**, with two Important
findings and no Critical/Minor findings. Its independent focused run passed
143 tests in 24.881 seconds. A correction turn is now active; no subsequent
resource implementation or live phase has started.

**Rationale:** First, pristine state was checked at preflight but not immediately
before Colima start, so a resumed prepared journal could adopt a footprint created
in the intervening time. Actual start dispatch must freshly refuse such remnants
without a mutation or creation binding, while pending-start recovery remains
observe-first. Second, pure capture validation accepted absent parent directories
alongside present child files. Both direct absence and the real deletion registry
could treat that contradictory record as complete. Central parent/child presence
and membership validation is required even though collector anchor checks already
protect ordinary filesystem observations.

**Affected artifacts:** Controller startup guard, profile-state pure validation,
and focused normal/recovery/replay regressions. Root retains documentation/Git
ownership; previous dirty main HTML and `Inputs/` are preserved. No live runtime
operation was performed.

**Unresolved questions:** Correct both findings and obtain quality rereview
acceptance; then finish API normalization, finite owner/resource joins, actual
producer association and calibrated diagnostics before whole Task 6 acceptance.

**Next gate:** Stable focused verification and B.3 review acceptance. Readiness
stays fail-closed; Task 7, live validation, V3B-2b, and V3C remain gated.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-178 — 2026-09-07 — Profile slice accepted; static API normalization underway

**Input:** Finish the B.3 quality corrections and continue the approved bounded
Task 6 correction sequence without opening the live gate.

**Interpretation:** Preserve the accepted filesystem/command boundary while
separating static Kubernetes default normalization from later dynamic ownership
and incarnation proofs.

**Decision status:** B.3 passed independent quality rereview after both findings
were fixed. Root independently passed **148 tests in 26.621 seconds**; the
reviewer passed 148 in 26.672 seconds and reran the original counterexamples.
There are no remaining findings in that bounded delta. A fresh implementer is
now building the focused API-default module; its initial 159-test pass is an
implementation checkpoint, not review acceptance or whole Task 6 completion.

**Rationale:** Fresh checks guard both startup intent and dispatch. A required,
nullable, monotonic `profile_start_refused_sequence` prevents a refused intent
from gaining ownership through error handling or restart; older missing-field
journals fail closed. Parent/child coherence is independently checked during
capture validation and replay. These controls do not claim atomic exclusion
against an uncooperative external Colima invocation.

For API normalization, dynamic Service allocation, actual Pod admission and
generated-owner additions remain fail-closed until the resource slice supplies
independent context. Pinned source review clarified that enableServiceLinks is
defaulted by SetDefaults_Pod, not SetDefaults_PodSpec; template insertion would
be incorrect. Static metadata validation is not an incarnation proof.

**Affected artifacts:** Profile/journal/proof contracts and focused tests;
new API-default module/tests and the applied-object wrapper in progress; updated
corrective plan and regenerated readers. No live runtime operation or Git
mutation was performed. Main's pre-existing HTML and `Inputs/` remain preserved.

**Unresolved questions:** Root's independent Colima source check found a
separate compatibility gap: optional foreign address fields and valid runtime
variants are rejected by the existing duplicate seven-field decoders. Plan B.4
now requires a shared closed decoder, private full-state comparison, privacy-safe
keyed public commitments, and roster completeness assessment before live work.
This is pending implementation, not part of the accepted B.3 claim. Dynamic
resource joins, source/result associations and calibrated diagnostics also remain
open.

**Next gate:** Static API-default specification and quality acceptance, then the
remaining inventory/resource/evidence corrections and whole Task 6 static/review
gate. Readiness stays false; Task 7, live tests, V3B-2b and V3C remain gated.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-179 — 2026-09-07 — Static Service-family over-admission corrected, rereview pending

**Input:** Continue the approved Task 6 correction sequence and evaluate the
independent static API-default specification review.

**Interpretation:** Static normalization must not grant the dynamic Service
allocation authority reserved for B.1, even when the intended cluster is IPv4.

**Decision status:** The initial 169 focused tests and 41 inventory/manifest
tests passed independently, but specification review found one concrete scope
violation. The implementer removed the premature IP-family defaults after 14
regression subcases failed. Its updated 171 focused and 41 inventory/manifest
tests pass; independent specification rereview is now pending. This is not
whole Task 6 acceptance.

**Rationale:** `ipFamilies` depends on allocation configuration and
`ipFamilyPolicy` can depend on prior Service state. Both remain exact until
the dynamic validator supplies independent context. Only sessionAffinity and
internalTrafficPolicy are normalized in this static Service slice. Explicit
desired family fields still require exact equality. The plan now states this
bounded implementation boundary explicitly.

**Affected artifacts:** API-default module and tests; corrective plan and its
regenerated reader. Root also reconfirmed Colima's profile-name mapping and
inventory implementation for the pending B.4 roster-completeness work. No live
runtime operation or Git mutation occurred. Main's existing HTML and `Inputs/`
remain untouched.

**Unresolved questions:** Static specification and quality acceptance, then B.4
inventory compatibility/completeness, B.1 relational resource proofs, actual
source/result binding and partial diagnostics remain open.

**Next gate:** Close both static review stages, then continue the approved
bounded corrections. No live phase, V3B-2b or V3C is opened.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-180 — 2026-09-07 — Static API slice accepted; foreign inventory correction dispatched

**Input:** Independent specification rereview and quality review of the corrected
static API-default slice, followed by the next approved Task 6 correction.

**Interpretation:** Accept only the bounded static comparator, not dynamic
ownership/readiness or complete Task 6. Continue with B.4 using isolated fixtures.

**Decision status:** Both reviews accepted the static slice with no remaining
scoped findings. Root freshly passed 171 focused tests in 25.187 seconds; each
reviewer passed the combined 212-test focused/inventory/manifest suite. Quality
review also independently assembled all 38 Calico static response documents.
A fresh B.4 implementer is now active; B.4 is not yet accepted.

**Rationale:** The accepted comparator preserves exact structural paths and
JSON scalar types while leaving allocated Service and actual Pod additions
unproved. B.4 must unify the private inventory schema, bind hidden address drift
with keyed public commitments, and reconcile Colima output against the no-follow
Lima directory roster. Colima's missing final Scanner error check makes command
success alone insufficient for a complete inventory. Stable bracketing is not
an atomic exclusion guarantee against external Colima activity.

**Affected artifacts:** Accepted API-default module/tests and proof wrapper;
forthcoming shared Colima inventory module, controller/proof/evidence adapters
and isolated fixtures. Main HTML and `Inputs/` remain preserved; no live runtime
operation or Git mutation occurred.

**Unresolved questions:** B.4 implementation and both reviews; B.1 resource
relations, producer associations, calibrated diagnostics, realistic archive
fixtures and whole Task 6 verification remain outstanding.

**Next gate:** B.4 focused verification and independent specification/quality
acceptance. Runtime readiness stays fail-closed, with live and later phases gated.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-181 — 2026-09-07 — Foreign inventory implemented; retained-snapshot linkage corrected

**Input:** B.4 implementation report and its self-review concern about separate
controller and registry samples.

**Interpretation:** Inventory compatibility, completeness, private comparison
and published commitments must all refer to the actual retained observation.
A preliminary snapshot cannot supply private evidence for a different proof.

**Decision status:** The implementer reports 278 focused tests passing after
closing the snapshot-linkage concern. Independent specification review and a
root rerun are in progress; B.4 is not yet accepted. Its bounded compatibility
contract is 1024 records, a 32 MiB raw payload, 128-character supported ASCII
names and positive bounded resources; unsupported names/rosters fail closed.

**Rationale:** The shared decoder admits the seven pinned runtime forms and
optional IP literals, while owned profile configuration remains strict. Stable
no-follow directory brackets address incomplete Colima listings without guest
content inspection. Public state HMACs capture hidden address drift without
publishing addresses or a low-entropy unkeyed hash. The retained foreign proof
now derives the after-state, global context, equality and attestation digest;
normal completion, recovery and hydration restore that same validated state.
The journal's narrow observed-foreign completion exception permits derived
results to differ from the preliminary intent without loosening other families.

**Affected artifacts:** New Colima inventory module/tests; focused controller,
proof, journal, profile-state and evidence adapters/fixtures; plan clarification
and regenerated reader. Root read pinned bootstrap source for later B.1 work.
No live runtime operation or Git mutation occurred. Existing main HTML and
`Inputs/` remain untouched.

**Unresolved questions:** Independent B.4 specification/quality acceptance and
whole Task 6 resource/source/fixture corrections remain open. Public verifiers
compare opaque state commitments; they cannot recompute the private HMAC.

**Next gate:** Complete B.4 focused verification and both review stages before
dispatching the next bounded implementation. Runtime readiness and live/later
phase gates remain closed.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-182 — 2026-09-07 — Foreign inventory accepted; bounded Service allocation work begins

**Input:** B.4 independent specification and quality verdicts and continuation
of the approved resource-proof corrections.

**Interpretation:** Accept B.4's inventory and retained-snapshot linkage only.
Split the next dynamic resource work into a focused Service allocation contract
before generated-owner, bootstrap, actual-Pod and readiness integration.

**Decision status:** B.4 passed both reviews without remaining scoped findings.
Root passed 278 tests in 35.179 seconds; specification and quality reviewers
passed 278 in 35.070 and 35.752 seconds respectively. Quality also checked
context-only drift and command-free offline hydration. A fresh Service-binding
implementer is active; this new slice is not yet accepted.

**Rationale:** Nine independently rendered KIL Services require usable, unique
IPv4 addresses inside the approved Service CIDR and persistent UID/address
bindings. Kubernetes API and DNS Service offsets 1 and 10 are reserved by the
pinned bootstrap contract. Static comparison without allocation context remains
strict. New dynamic bindings must be rederived from raw proofs and survive
replay; they do not establish Pod owners, admission or readiness. Source review
also confirmed fresh kubeadm's two CoreDNS replicas and Kind's single-node
post-init taint/label removal. The plan records these bootstrap expectations
subject to confirming no overriding generated kubeadm patch.

**Affected artifacts:** Accepted B.4 module/adapters/tests; planned Service
binding module/tests and focused proof integration; corrective plan and reader.
No live runtime operation or Git mutation occurred. Existing main HTML and
`Inputs/` remain preserved.

**Unresolved questions:** Service allocation implementation and two reviews;
remaining bootstrap/owner/Pod/stage proofs, producer/result associations,
calibrated partial diagnostics and realistic full-controller fixtures.

**Next gate:** Service slice focused verification and specification/quality
acceptance. Whole Task 6 and live/later phases remain gated; runtime completeness
stays false.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-183 — 2026-09-07 — Service allocation implemented; source-capture bounds clarified

**Input:** Service implementer verification and ongoing source review for the
remaining bootstrap/capture corrections.

**Interpretation:** Service allocation and persistent incarnation checks are a
bounded step, not a substitute for generated-owner, admission or readiness
proofs. Later captures must also distinguish bounded reads from complete sources.

**Decision status:** The Service implementer reports 300 focused tests passing
in 36.105 seconds. Specification review and a root rerun are active; acceptance
is pending. No controller, journal or static-default behavior was modified by
this slice. Runtime completeness remains false.

**Rationale:** The new validator derives all nine expected Service configurations
independently and binds unique UID/address pairs. Shared proof replay supplies
prior bindings; readiness cannot fall back to static comparison when those
bindings are missing. ResourceVersion progression remains distinct from object
replacement. The direct static comparator's root-status treatment is unchanged;
full settled Service status is part of later readiness work.

Root also confirmed that Kubernetes log reads currently cap output at the same
1 MiB limit accepted as evidence, while ledger reads already request an overflow
sentinel byte. Plan C.2 now requires the analogous log overflow check, private
truncation diagnostics and idempotent derivation of counts from frozen captures.
These capture changes are planned, not implemented. Read-only source research
confirmed Kind's iptables default and lack of an injected CoreDNS override;
remaining pinned bootstrap details are being checked independently.

**Affected artifacts:** New Service binding module/tests and focused proof
integration; corrective plan and regenerated reader. Main HTML and `Inputs/`
remain untouched. No live runtime operation or Git mutation occurred.

**Unresolved questions:** Both Service reviews, full bootstrap/owner/Pod/stage
contracts, source associations/partial diagnostics and realistic full-controller
fixtures remain open.

**Next gate:** Service specification/quality acceptance, then the next bounded
resource correction. Whole Task 6 and all live/later phase gates remain closed.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-184 — 2026-09-07 — Service specification accepted; quality review underway

**Input:** Independent Service specification verdict, root verification and
completed pinned Kind/kubeadm configuration research.

**Interpretation:** Preserve the Service slice's narrow allocation/incarnation
claim while preparing source-derived bootstrap expectations for a separate
resource validator.

**Decision status:** Service specification review passed with no scoped finding.
The reviewer passed 300 tests in 36.223 seconds and root freshly passed 300 in
36.526 seconds. Independent quality review is active, so the slice is not yet
fully accepted. No live gate has opened.

**Rationale:** Exact rendered Services, distinct UIDs/addresses and replayed
prior bindings were independently confirmed. The readiness guard remains false
first and cannot accept a missing prior allocation binding. Pinned source review
also confirms no Kind-injected CoreDNS patch for this fixed configuration,
fresh kubeadm's two CoreDNS replicas, iptables kube-proxy settings, source-level
CoreDNS/kube-proxy image references and the controller-manager arguments that
enable service-account clients. Rootless-dependent variants remain observations
to bind later, not assumptions.

**Affected artifacts:** Service module/tests and proof integration under review;
bootstrap corrective plan and regenerated reader. No live runtime operation or
Git mutation occurred. Existing main HTML and `Inputs/` remain untouched.

**Unresolved questions:** Service quality acceptance; exact bootstrap/resource
ownership implementation; Pod admission, source associations, calibrated
diagnostics and realistic full-controller fixtures.

**Next gate:** Close Service quality review, then dispatch the next bounded
resource validator. Whole Task 6, runtime readiness and live/later phases remain
closed.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-186 — 2026-09-07 — Service slice accepted; bootstrap identity slice dispatched

**Input:** Service test-oracle correction and independent quality rereview.

**Interpretation:** Close Service allocation only after the independent raw
expected-output assertion passes, then continue with an exact but deliberately
non-semantic bootstrap identity/cardinality slice.

**Decision status:** The Service slice is accepted by both review stages. The
corrected focused suite passed 36 tests for the implementer, 36 for root in
0.698 seconds and 36 for quality rereview in 0.687 seconds; the implementer's
full 300-test run passed in 33.905 seconds. A fresh bootstrap-identity implementer
is active. Its work is not yet accepted.

**Rationale:** The corrected test independently retains all non-allocation
Service fields and compares decoded output exactly. The next slice will replace
broad Namespace/ServiceAccount/ConfigMap allowances with the exact eight,
63 and 26 final identity sets respectively, binding UIDs and namespace Active
state. Platform ConfigMap content remains explicitly unvalidated semantics:
bounded current digests may support later work but cannot authorize readiness
or become immutable identity merely because dynamic content was observed.

**Affected artifacts:** Accepted Service binding/proof tests; planned bootstrap
identity module/tests. No live runtime operation or Git mutation occurred.
Existing main HTML and `Inputs/` remain untouched.

**Unresolved questions:** Bootstrap identity implementation/reviews, semantic
platform ConfigMap and component configuration, generated owner/Pod/endpoint
relations, evidence and full-controller fixture work.

**Next gate:** Bootstrap identity focused verification and both independent
review stages. Runtime completeness and whole Task 6/live/later gates stay closed.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-185 — 2026-09-07 — Service production contract sound; test independence correction pending

**Input:** Independent Service code-quality review after specification acceptance.

**Interpretation:** A scoped-ready production verdict does not justify carrying
forward a known avoidable test oracle dependency. Correct it and rereview before
dispatching another implementation slice.

**Decision status:** Quality review found no Critical or Important issue and
classified the slice scoped-ready. Its 300-test run passed in 34.278 seconds,
and 47 independent malformed/type probes rejected correctly. One Minor test
finding is being corrected; final acceptance remains pending rereview.

**Rationale:** The production validator removes exactly the four independently
validated Service allocation fields. However, the test then used the production
static comparator to assess the sanitized result, which could mask a future
fifth-field removal. The expected sanitized documents will instead be built
directly and compared byte-for-byte, retaining static fields such as
sessionAffinity and internalTrafficPolicy.

**Affected artifacts:** Service binding tests only for the correction; bootstrap
module file routing was added to the plan and readers regenerated. No live
runtime operation or Git mutation occurred. Existing main HTML and `Inputs/`
remain untouched.

**Unresolved questions:** Test correction/rereview, then the bootstrap identity
and configuration slice; later generated ownership, Pod admission, source and
full-controller work remain open.

**Next gate:** Fresh Service verification and quality rereview, then continue
the approved bounded resource sequence. Whole Task 6 and live/later gates remain
closed.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-187 — 2026-09-07 — Bootstrap identities and ConfigMap source contract accepted

**Input:** Completed bootstrap identity implementation, independent specification
and code-quality reviews, root verification, and pinned-source research for all
16 fresh platform ConfigMap producers.

**Interpretation:** Accept the exact bootstrap object identities without letting
current platform configuration bytes become semantic evidence, while recording
the separate source-derived rules needed for the next configuration slice.

**Decision status:** The standalone bootstrap identity/cardinality slice is
accepted after both review stages. Specification review first rejected valid
`binaryData` acceptance; the correction now rejects every such field. Quality
review then identified a raw lone-surrogate encoding exception and a weak digest
oracle; both were corrected and rereview passed with no remaining finding. Root
freshly passed the accepted 313-test suite in 39.229 seconds. The platform
ConfigMap semantic slice and runtime completeness remain unaccepted.

**Rationale:** The accepted slice binds exactly eight Namespaces, 63
ServiceAccounts and 26 ConfigMaps, globally distinct UIDs, canonical positive
resource versions, kube-system cluster incarnation, Namespace Active state and
prior UID/resource-version continuity. It compares only KIL and Calico static
configuration. The 16 platform ConfigMaps remain closed-shape observations with
current-only `unvalidated_configuration_sha256` diagnostics. Pinned producers
establish exact fresh data-key sets, absence of `binaryData`/`immutable` and
component hashes, CA/configuration relationships, the four-key Kind local-path
object, and lifecycle-qualified zero-or-one `cluster-info` JWS signatures; these
rules were added to the implementation plan for a separate validator.

**Affected artifacts:** Worktree bootstrap module/tests; corrected V3B-2a plan
and regenerated reader; this lineage entry. Main lineage HTML and `Inputs/`
remain untouched. No Colima, Docker, Kind or Kubernetes operation and no Git
mutation occurred.

**Unresolved questions:** Platform ConfigMap semantic implementation/reviews;
generated owner, Pod, Node and EndpointSlice relations; staged application,
source associations, calibrated diagnostics, exact Envoy refusal evidence and
the realistic full-controller archive fixture.

**Next gate:** Implement and independently review the source-derived platform
ConfigMap configuration slice. Runtime completeness, whole Task 6 and every
live/later-phase gate remain closed; any future live action is restricted to the
unique `kil-v3-lab` Colima profile and matching Kind cluster.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-188 — 2026-09-07 — Source-rendered platform ConfigMaps accepted

**Input:** Exact pinned CoreDNS/Kind fixture extraction, TDD implementation,
independent specification and code-quality reviews, and root verification.

**Interpretation:** Close only the two platform ConfigMaps whose entire fresh
content is deterministically rendered from pinned public source, leaving private
CA, token and typed component relationships for separate validators.

**Decision status:** The source-rendered ConfigMap slice is accepted by both
review stages. Specification review first rejected forgeable exported proof
digests and indirect duplicate coverage; exact identity-specific digest
revalidation and direct duplicate cases resolved both. Quality review then
rejected non-exact API identity strings that could retain mutable equality
objects; exact built-in-string checks resolved the invariant. Root freshly
passed 328 accepted tests in 34.702 seconds. Runtime completeness stays false.

**Rationale:** The validator admits exactly `kube-system/coredns` and
`local-path-storage/local-path-config`, exact producer metadata, canonical
positive resource versions and bounded UIDs. It compares the 420-byte Corefile
and all four no-final-LF Kind values byte-for-byte, parses last-applied JSON by
closed semantics rather than textual order, and produces immutable
identity-specific canonical source digests. It does not infer readiness,
ownership, CA/JWS validity or any other platform configuration.

**Affected artifacts:** New worktree source-rendered ConfigMap module/tests;
V3B-2a plan routing, fixture hashes and regenerated reader; this lineage entry.
Main lineage HTML and `Inputs/` remain untouched. No live runtime or Git
mutation occurred.

**Unresolved questions:** Root-CA and extension trust relationships, legacy date
and cluster-info lifecycle/JWS proof, typed kubeadm/kubelet/kube-proxy content,
generated ownership/admission, staged application, source/result associations,
calibrated diagnostics, Envoy refusal and realistic full-controller fixtures.

**Next gate:** Implement and independently review a bounded private
CA/date/bootstrap-token relationship slice. Whole Task 6 and every live/later
phase remain closed; any future live action is limited to `kil-v3-lab`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-189 — 2026-09-07 — Platform trust and legacy-date ConfigMaps accepted

**Input:** TDD implementation and independent specification/quality review of
the private trust/date ConfigMap slice, including malformed-certificate and
decoded-tree hardening.

**Interpretation:** Accept only the producer relationships that can be proven
from independent CA material and API creation time; keep bootstrap-token JWS and
typed component documents in separate gates.

**Decision status:** The ten-object trust/date slice is accepted by both review
stages. Specification review required normalization of duplicate X.509
extensions and immutable exports. Quality review required pre-allocation tree
bounds and partial forged-object error normalization. All corrections were
independently rereviewed. Root freshly passed 344 accepted tests in 34.524
seconds. Runtime completeness remains false.

**Rationale:** Eight `kube-root-ca.crt` objects now bind certificate DER to the
independent cluster CA, and extension-apiserver data binds distinct cluster and
front-proxy CA roles plus exact fresh request-header arrays. The legacy tracking
date is a real UTC date related to its API creation day or the immediately
preceding midnight-boundary day, never to the current observation date. Input
traversal is cycle-safe and rejects before unbounded encoding or scheduling;
proof constructors revalidate exact identities and internal digest relations.

**Affected artifacts:** New worktree trust ConfigMap module/tests; V3B-2a plan
routing and regenerated reader; this lineage entry. Main lineage HTML and
`Inputs/` remain untouched. No live infrastructure or Git mutation occurred.

**Unresolved questions:** `cluster-info` internal kubeconfig and token-lifecycle
JWS; typed kubeadm/kubelet/kube-proxy documents; generated ownership/admission;
staged application, source/result associations, partial diagnostics, Envoy
refusal and realistic controller fixtures.

**Next gate:** Implement and independently review the closed `cluster-info`
kubeconfig/JWS lifecycle proof. Whole Task 6 and every live/later phase remain
closed; future live action stays restricted to `kil-v3-lab`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-190 — 2026-09-07 — Cluster-info lifecycle proof accepted

**Input:** TDD implementation and independent specification/quality review of
the `kube-public/cluster-info` internal kubeconfig, detached bootstrap-token JWS
and active-to-expired reconciliation contract.

**Interpretation:** Accept a current active signature only after byte-exact JWS
verification against private token evidence, and accept later signature removal
only after independently revalidating the earlier raw signed ConfigMap. Keep
typed component configuration and runtime readiness in later gates.

**Decision status:** The cluster-info slice is accepted by both review stages.
Specification review closed malformed HTTPS authority, control-character,
backslash and percent-escape cases. Quality review closed wide-tree and
pre-encoding allocation amplification, equal-resourceVersion signature drift,
and a caller-forgeable prior-proof shortcut. The final transition requires the
prior raw document and revalidates its JWS rather than trusting a proof digest.
Root freshly passed 367 accepted tests in 37.137 seconds. Runtime completeness
remains false.

**Rationale:** The validator admits only the closed one-empty-name-cluster
kubeconfig, binds its HTTPS server and single CA certificate DER to independent
evidence, and verifies the exact detached HS256 construction with the
16-character token secret alone. Expiration is `expiration <= captured_at`;
zero signatures require a strictly advanced resourceVersion and the matching
prior active observation. Returned immutable proofs retain bindings and digests
but no token secret, PEM, raw kubeconfig or JWS. Hostile decoded structures and
private strings are rejected within explicit bounds.

**Affected artifacts:** New worktree cluster-info module/tests; V3B-2a plan
clarification and regenerated reader; this lineage entry. Main lineage HTML and
`Inputs/` remain untouched. No live Colima, Docker, Kind or Kubernetes action
occurred.

**Unresolved questions:** Typed kubeadm, kubelet and kube-proxy ConfigMaps;
generated ownership and Pod admission; staged application, source/result
associations, partial diagnostics, exact Envoy refusal evidence and realistic
full-controller fixtures.

**Next gate:** Implement and independently review the typed platform component
ConfigMap contract. Whole Task 6 and every live/later phase remain closed; all
future live actions stay restricted to the unique `kil-v3-lab` Colima profile
and matching Kind cluster.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-191 — 2026-09-07 — Closed component-YAML decoder accepted

**Input:** TDD implementation plus independent specification and quality review
of the dependency-free YAML syntax boundary needed by typed kubeadm, kubelet
and kube-proxy ConfigMap validators.

**Interpretation:** Admit only the deterministic serialization subset required
by the pinned component documents, not general YAML. Syntax decoding remains a
supporting proof layer and cannot establish component semantics or readiness.

**Decision status:** The closed-YAML slice is accepted by both review stages.
Specification review corrected sequence-map indentation, YAML 1.1 boolean and
sexagesimal ambiguity, trailing-colon scalars, key-node accounting,
single-quoted backslash semantics, root empty mappings and trailing-dot
sexagesimal forms. Quality review added bounded integer conversion, escaped BOM
rejection and early single-quoted scalar accounting. Root freshly passed 396
accepted tests in 35.944 seconds. Runtime completeness remains false.

**Rationale:** The decoder returns only exact built-in mapping, sequence,
string, Boolean, integer and null values. It rejects duplicate keys, graph/type
extensions, comments, directives, document markers, block scalars, non-empty
flow collections, ambiguous implicit types, controls, surrogates and subclasses.
It bounds input bytes, lines, depth, semantic nodes, decoded scalar bytes and
decimal-integer digits before expensive construction or conversion.

**Affected artifacts:** New worktree closed-YAML module/tests; V3B-2a plan
routing and regenerated reader; this lineage entry. Main lineage HTML and
`Inputs/` remain untouched. No live infrastructure or Git mutation occurred.

**Unresolved questions:** Typed semantic equality and private relationships for
the three component ConfigMaps, especially kube-proxy kubeconfig credentials;
generated ownership and Pod admission; staged application, source/result
associations, diagnostics, Envoy refusal and realistic controller fixtures.

**Next gate:** Implement and independently review the source-closed typed
kubeadm/kubelet component ConfigMap semantics, keeping live-derived kube-proxy
credential relations closed until their evidence shape is established. Whole
Task 6 and all live/later gates remain closed; future live actions are limited
to `kil-v3-lab`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-192 — 2026-09-07 — Typed kubeadm and kubelet ConfigMaps accepted

**Input:** TDD implementation and independent specification/quality review of
the uploaded kubeadm cluster configuration and generic kubelet configuration
against trusted generated/defaulted semantic inputs.

**Interpretation:** Accept semantic equality independent of YAML ordering while
binding the pinned nominal cluster, version, network, DNS and rootful-provider
relations. Do not conflate the uploaded generic kubelet document with
node-local CRI patching, and keep kube-proxy credentials separate.

**Decision status:** The two-ConfigMap component slice is accepted by both
review stages without requested corrections. Root freshly passed 413 accepted
tests in 35.874 seconds. The proof remains an evidence record rather than an
unforgeable capability, and runtime completeness remains false.

**Rationale:** Exactly `kube-system/kubeadm-config` and
`kube-system/kubelet-config` are admitted with closed core/v1 identity,
metadata and data shapes. Their embedded YAML is decoded through the accepted
closed subset and compared to bounded exact built-in expected trees without
attacker-controlled equality. Kubeadm binds the beta-v4 cluster identity,
control-plane endpoint, subnets, DNS domain and sole Kind hostpath controller
argument; kubelet binds its beta-v1 type, cluster domain and single DNS address.
Proofs retain only API identity, UID/resourceVersion and raw/semantic digests.

**Affected artifacts:** New worktree component-ConfigMap module/tests; V3B-2a
plan routing and regenerated reader; this lineage entry. Main lineage HTML and
`Inputs/` remain untouched. No live Colima, Docker, Kind or Kubernetes action
occurred.

**Unresolved questions:** Kube-proxy configuration and kubeconfig credential
shape/relations; generated ownership and Pod admission; staged application,
source/result associations, partial diagnostics, exact Envoy refusal and
realistic full-controller fixtures.

**Next gate:** Establish and implement the pinned kube-proxy configuration and
private kubeconfig relationship without guessing its credential representation.
Whole Task 6 and all live/later gates remain closed; future live actions stay
limited to the unique `kil-v3-lab` profile and matching Kind cluster.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-193 — 2026-09-07 — Kube-proxy ConfigMap relationship accepted

**Input:** Pinned Kubernetes 1.36.1 kubeadm proxy manifest/generator source,
TDD implementation, independent source/specification review and independent
quality review.

**Interpretation:** Treat kube-proxy credentials as exact service-account file
references, not embedded private material, and bind the source-rendered
kubeconfig separately from the generated/defaulted proxy configuration.

**Decision status:** The kube-proxy ConfigMap slice is accepted by both review
stages. Quality review found no production defect and required one hostile-width
test to instrument the actual traversal hook rather than dead code; the revised
test proves rejection before child visitation. Root freshly passed 425 accepted
tests in 36.462 seconds. Runtime completeness remains false.

**Rationale:** The validator admits only the labeled `kube-system/kube-proxy`
core/v1 ConfigMap with exact `config.conf` and `kubeconfig.conf` data. It binds
the trusted defaulted iptables configuration, pod CIDR, 1-second minimum sync,
zero max-per-core conntrack setting and rootful selection. The kubeconfig is
closed to one `default` cluster/context/user, the fixed internal HTTPS endpoint,
the mounted service-account CA path and token-file path; embedded tokens,
certificates, keys and alternate authentication are rejected. Proofs retain
only identity and raw/semantic digests.

**Affected artifacts:** New worktree kube-proxy ConfigMap module/tests; V3B-2a
plan routing and regenerated reader; this lineage entry. Main lineage HTML and
`Inputs/` remain untouched. No live infrastructure or Git mutation occurred.

**Unresolved questions:** Generated Deployment/DaemonSet/static-Pod/
EndpointSlice ownership and Node incarnation; Pod admission, CNI and image
identity; staged application, source/result associations, partial diagnostics,
exact Envoy refusal and realistic full-controller fixtures.

**Next gate:** Implement and independently review generated platform ownership
and resource relationships before any Pod-readiness claim. Whole Task 6 and all
live/later gates remain closed; future live actions remain restricted to
`kil-v3-lab`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-194 — 2026-09-07 — Deployment ownership chains accepted

**Input:** TDD implementation and independent specification/quality review of
the fresh Deployment to ReplicaSet to Pod ownership projection.

**Interpretation:** Prove generated workload identity through exact controller
UID relations plus revision, template-hash and generated-name joins; name
prefixes alone are insufficient. Keep DaemonSet/static ownership and all Pod
readiness/image claims separate.

**Decision status:** The Deployment ownership slice is accepted by both review
stages. Quality review required exact collection cardinalities to fail before
per-key/per-element traversal; the revised tests observe the real paths for
wide records, Pod tuples and proof bindings. Root freshly passed 448 accepted
tests in 35.481 seconds. Runtime completeness remains false.

**Rationale:** The validator derives exactly 12 pinned deployments and their
replica counts, admits one fresh revision-1 ReplicaSet per Deployment and binds
13 generated Pods through namespace/name/UID owner references. ReplicaSet and
Pod hashes/names must agree, and all 37 UIDs across the three families are
globally unique. The immutable proof retains only identities, resourceVersions,
hashes and canonical Pod triples; no raw projection is retained.

**Affected artifacts:** New worktree deployment-ownership module/tests; V3B-2a
plan routing and regenerated reader; this lineage entry. Main lineage HTML and
`Inputs/` remain untouched. No live infrastructure or Git mutation occurred.

**Unresolved questions:** DaemonSet-to-Pod and static mirror-Pod-to-Node
ownership; EndpointSlice ownership; Pod admission/CNI/images; staged
application, source/result associations, diagnostics, Envoy refusal and
realistic full-controller fixtures.

**Next gate:** Implement and independently review the single-node DaemonSet and
static mirror Pod ownership relations. Whole Task 6 and all live/later gates
remain closed; future live actions stay limited to `kil-v3-lab`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-195 — 2026-09-07 — Node, DaemonSet and mirror ownership accepted

**Input:** TDD implementation and independent specification/quality review of
the single-node DaemonSet Pod and control-plane static mirror Pod ownership
projection.

**Interpretation:** Bind generated DaemonSet Pods through exact controller UIDs
and bind mirror Pods through the exact Node incarnation UID plus component,
file-source and mirror/config hash relations. Keep readiness and image identity
outside this proof.

**Decision status:** The Node ownership slice is accepted by both review stages.
An initially contradictory review instruction about digest retention was
corrected: equal mirror/config digests are required evidence. Quality review
then found that the validated static owner UID was not retained in the proof;
the final binding stores it and the proof constructor requires equality with
the Node UID. Root freshly passed 466 accepted tests in 35.938 seconds. Runtime
completeness remains false.

**Rationale:** Exactly one named Node, two pinned DaemonSets, two generated
DaemonSet Pods and four named control-plane mirror Pods are admitted. All nine
resource UIDs are unique; owner references join exact names and UIDs, and each
mirror binding preserves the repeated Node owner UID without miscounting it as
a resource identity. Static hashes are lowercase SHA-256 values and equal, with
source `file`. The immutable proof retains no raw projection.

**Affected artifacts:** New worktree Node-ownership module/tests; V3B-2a plan
routing and regenerated reader; this lineage entry. Main lineage HTML and
`Inputs/` remain untouched. No live infrastructure or Git mutation occurred.

**Unresolved questions:** EndpointSlice owner/manager/port/address/target joins;
Pod admission, CNI and image identity; staged application, source/result
associations, diagnostics, Envoy refusal and realistic controller fixtures.

**Next gate:** Implement and independently review EndpointSlice ownership and
ready Pod-target relations for platform and KIL Services. Whole Task 6 and all
live/later gates remain closed; future live actions remain limited to
`kil-v3-lab`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-196 — 2026-09-07 — KIL ready EndpointSlice ownership accepted

**Input:** TDD implementation and independent specification/quality review of
the nine KIL Service-to-ready-Pod-to-EndpointSlice relations.

**Interpretation:** Revalidate the accepted Service allocation and Deployment
ownership evidence, then join each fixed KIL Service to its sole ready owned Pod
and controller-produced EndpointSlice through exact incarnation identities,
network addresses and producer fields. Keep platform endpoints, complete Pod
admission/CNI and image identity outside this focused proof.

**Decision status:** The KIL EndpointSlice slice is accepted by both review
stages. Specification review required full preservation of the prior Service
proof's API UID, timestamp and run-ID syntax and corrected EndpointSlice-name
uniqueness to namespace/name. Quality review then closed permissive UID handling
across raw, owner, target, upstream-proof and retained-binding paths. Root
freshly passed 484 accepted tests in 35.649 seconds; all 56 Markdown readers
were regenerated and verified. Runtime completeness remains false.

**Rationale:** Exactly nine authz/envoy/target relations across the three fixed
application namespaces are admitted. Each Pod joins its retained Deployment
proof UID and resourceVersion, uses one unique canonical IPv4 address in the
pinned Pod subnet, is Running, ready, non-deleting and bound to the sole node.
Each discovery/v1 EndpointSlice has the exact Service controller owner UID, two
producer labels, IPv4 type, resolved TCP/8080 port and one endpoint whose three
conditions, address, node and Pod targetRef are exact. Generated names remain
supplemental namespace-scoped evidence. The immutable canonical proof cannot
open the overall runtime contract.

**Affected artifacts:** New worktree KIL EndpointSlice ownership module/tests;
V3B-2a plan routing and regenerated reader; this lineage entry. Main lineage
HTML and `Inputs/` remain untouched. No Colima, Docker, Kind or Kubernetes
runtime was started, stopped or mutated.

**Unresolved questions:** Platform Kubernetes/kube-dns Service and endpoint
ownership; complete Pod admission, Calico CNI and image identity; staged
application, source/result associations, diagnostics, Envoy refusal and
realistic full-controller fixtures.

**Next gate:** Implement and independently review the bounded platform Service
and endpoint relations, then proceed to complete Pod admission/CNI/image
evidence. Whole Task 6 and all live/later gates remain closed; future live
actions remain limited to the unique `kil-v3-lab` Colima profile.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-197 — 2026-09-07 — Platform Service and endpoint relations accepted

**Input:** TDD implementation, pinned Kubernetes v1.36.1 source inspection and
independent specification/quality review of the `kubernetes` and `kube-dns`
Service, legacy Endpoints and EndpointSlice relations.

**Interpretation:** Treat the API-server lease adapter and the selector-driven
DNS controllers as distinct producers. Bind the fixed API endpoint to the
accepted Node incarnation and InternalIP, while binding both DNS endpoints to
the exact two CoreDNS Pods already owned by the CoreDNS Deployment proof.

**Decision status:** The platform endpoint slice is accepted by both review
stages. Specification review corrected the legacy kube-dns Endpoints labels:
they copy the DNS Service labels and add the endpoint-controller manager,
whereas only the API-server Endpoints carries skip-mirror. Quality review then
closed forged address relations, cross-proof UID collisions, constructor
exception leaks and flattened-UID role confusion. Root freshly passed 503
accepted tests in 37.537 seconds; all 56 Markdown readers were regenerated and
verified. Runtime completeness remains false.

**Rationale:** The two Services retain their exact pinned subnet offsets and
producer configurations. The API-server's same-named EndpointSlice has its
source-correct service-name-only metadata and one Node-bound ready target; the
DNS EndpointSlice retains its exact Service owner, manager, three ports and two
ready CoreDNS targets. The proof revalidates and retains the accepted owner
proofs, a collision-free 46-resource UID domain and role-preserving CoreDNS
name/UID/resourceVersion/address records. Node, Service and Pod address spaces
remain distinct, and direct proof reconstruction reasserts every relation.

**Affected artifacts:** New worktree platform-endpoint module/tests; V3B-2a
plan routing and regenerated reader; this lineage entry. Main lineage HTML and
`Inputs/` remain untouched. Read-only pinned upstream source was inspected. No
Colima, Docker, Kind or Kubernetes runtime was started, stopped or mutated.

**Unresolved questions:** Complete admission/default/CNI/image identity for
direct, generated, DaemonSet and static Pods; staged application, completion
registry integration, source/result associations, diagnostics, Envoy refusal
and realistic full-controller fixtures.

**Next gate:** Implement and independently review bounded actual-Pod admission,
Calico network annotations and immutable image/container incarnation evidence.
Whole Task 6 and all live/later gates remain closed; future live actions remain
limited to the unique `kil-v3-lab` Colima profile.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-198 — 2026-09-08 — V3B-2a checkpoint stop and synchronization authorized

**Input:** The user requested that work stop at the accepted checkpoint, that
all accepted work be synchronized and committed locally and remotely, and that
the remaining tasks resume in another session.

**Interpretation:** Interrupt the not-yet-implemented driver-Pod admission
slice, preserve only reviewed work through the platform endpoint gate, commit
the dedicated implementation branch, integrate it into local main and publish
both branch and main. Do not adopt unrelated `Inputs/` content or the separately
modified lineage HTML, and do not touch any Colima runtime.

**Decision status:** Confirmed checkpoint boundary. The interrupted next slice
created no files. The accepted 50-file implementation checkpoint was freshly
verified at 503 tests plus reader/diff checks, committed as `e888a0f`, and
pushed to `origin/codex/v3b2-kind-calico-implementation`. Local-main lineage
and implementation synchronization is authorized as the remaining closeout.

**Rationale:** A reviewed Git checkpoint makes the incomplete phase safe to
resume without presenting Task 6 or V3B-2a as complete. Separating unrelated
working-tree content prevents the synchronization request from silently
capturing user-owned artifacts outside the accepted implementation scope.

**Affected artifacts:** The V3B-2a implementation branch and its 50 accepted
files; this Markdown lineage. `Inputs/` and the modified lineage HTML remain
uncommitted and untouched. No Colima, Docker, Kind or Kubernetes runtime was
started, stopped or mutated.

**Unresolved questions:** The remaining Task 6 corrective work, beginning with
direct-driver Pod admission/CNI/image identity, followed by Tasks 7–10 and the
later V3C repetition/performance phase.

**Next gate:** In a new session, resume from direct-driver Pod admission using
the accepted platform endpoint proof as the Node-network authority. Future live
actions remain limited to the unique `kil-v3-lab` Colima profile.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-199 — 2026-09-08 — V3B-2a checkpoint synchronized and shutdown-safe

**Input:** Completion of the user-authorized checkpoint synchronization and
host-state verification.

**Interpretation:** Confirm the accepted branch and merged main tips on the
remote, reverify the merged test tree, and inspect Colima read-only before
declaring the workstation safe to shut down.

**Decision status:** Confirmed. The accepted checkpoint branch is published at
`e888a0f0695f5fe01a94478f3144a854db161dbb`; the implementation and prior
lineage were merged and published on main at
`b98615e7f114d909eb0201c1089986409012605a`. The merged main tree freshly passed
503 tests in 42.139 seconds. The `kil-v3-lab` Colima profile is absent, so no
project-owned runtime needed stopping. The unrelated running `attackswarm`
profile was not touched.

**Rationale:** Remote-tip readback plus merged-tree verification establishes a
durable resume point. Read-only Colima inventory confirms shutdown safety
without broadening authority to another project's profile.

**Affected artifacts:** Remote and local main, the published implementation
branch, and this Markdown lineage. The unrelated untracked `Inputs/` directory
and modified lineage HTML remain uncommitted and untouched.

**Unresolved questions:** All remaining Task 6 corrective work and Tasks 7–10;
V3C remains a later phase.

**Next gate:** Resume in a new session at direct-driver Pod admission/CNI/image
identity. Any future Colima mutation must target only a newly and uniquely
validated `kil-v3-lab` profile.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-200 — 2026-09-08 — Resume V3B-2a with model switch checkpoints

**Input:** The user selected Astra medium, requested advice at future model
switch points, confirmed readiness to resume the accepted checkpoint, and
explicitly requested as many additional agents as possible.

**Interpretation:** Resume Task 6 at direct-driver Pod admission/CNI/image
identity in the existing implementation worktree, using the approved separate
implementation, specification-review and quality-review workflow.

**Decision status:** Resume confirmed. Astra medium coordinates integration;
Sol low handles this bounded implementation. Later model changes are advisory
checkpoints, not changes already applied. No timing improvement is established
by measurement yet. All four available slots are engaged: the coordinator,
driver-Pod implementer, generated-Pod contract researcher, and a reused agent
mapping controller/evidence integration. Preparation agents are read-only to
avoid overlapping edits.

**Rationale:** Match reasoning effort to the work while retaining independent
review and all existing evidence gates. The static validator must not imply
that complete runtime readiness or Task 6 has been accepted.

**Affected artifacts:** This Markdown lineage; the implementation-worktree
plan; new driver-Pod validator and tests pending implementation and review.

**Unresolved questions:** Review results, generated-Pod admission and image
proofs, controller integration and remaining Task 6 requirements; Tasks 7–10
and V3C remain later work.

**Next gate:** Independently verify the bounded direct-driver proof and then
continue the corrective pass. Any future Colima mutation is restricted to the
uniquely validated `kil-v3-lab` profile.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
### T-201 — 2026-09-08 — Parallel implementation and broader baseline correction

**Input:** The user requested maximum available parallel agents while resuming
the Task 6 corrective pass.

**Interpretation:** Use all four slots for distinct bounded work, reassigning
completed preparation agents to implementation or independent review. Keep
runtime readiness closed throughout this preparation.

**Decision status:** Parallel work is confirmed. Driver-Pod admission has seven
focused tests independently passing and is awaiting independent review. The
Envoy refusal producer is being implemented separately. Image-reference research
identified ordered CRI repoTags/repoDigests as additional required evidence.

**Rationale:** Independent source and producer work can proceed while Pod
validators are reviewed. Runtime image display names and content references
must be bound independently; digest-suffix equality is insufficient.

**Verification correction:** The broad baseline command executed 1,098 tests
in 477.015 seconds with eight failures and 26 errors, largely controller image
identity failures. Earlier references to 503 passing tests must not be read as
a repository-wide passing baseline. An overlapping suite was also attempted;
concurrency has not been established as the cause. One isolated controller
failure is being diagnosed before any corrective implementation.

**Affected artifacts:** Driver-Pod validator/tests; quiescence producer/tests;
implementation-worktree plan; this Markdown lineage. No Colima profile has
been started or stopped.

**Unresolved questions:** Independent reviews, standalone controller failure
cause, CRI reference proof implementation and full runtime proof composition.

**Next gate:** Repair confirmed bounded issues, finish independent reviews,
and verify the corresponding focused gates before broader integration.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
### T-202 — 2026-09-08 — Driver proof accepted; image identity assumptions corrected

**Input:** Independent driver specification/quality reviews and isolated
controller baseline diagnosis during the user-authorized parallel continuation.

**Interpretation:** Accept only the bounded reviewed driver-Pod contract;
repair stale fixture assumptions without weakening runtime completion gates.

**Decision status:** Driver specification and quality gates passed. Root
verification passed 51 driver/platform-endpoint/static-default tests. The
producer/journal/proof group passed 95 tests outside the host sandbox, which
otherwise denies Bash process-substitution `/dev/fd` access. Envoy producer
quality review and the archive fixture correction remain pending.

**Rationale:** Source inspection established that `WorkloadIdentity.kil_image_id`
currently carries the manifest/tag identity, not the Docker config identity.
The driver proof now requires a separate expected config digest from committed
inputs and preserves both identities. Distinct fixture digests prevent silent
conflation. The broader controller failure reproduces in isolation; stale fake
image-inspect IDs and a digest-mocked archive are confirmed causes, not merely
concurrent-test interference.

**Affected artifacts:** New driver-Pod validator and tests; updated plan and
reader; pending Envoy producer/journal/tests; controller fixture correction;
this Markdown lineage.

**Unresolved questions:** Ordered CRI reference-chain proof, generated-Pod
validation, runtime composition, remaining controller/evidence corrective work.
The fixture repair may reveal the next already-closed integration gate.

**Next gate:** Finish independent producer review and self-consistent archive
fixture review. No live readiness or whole-phase acceptance is implied.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
### T-203 — 2026-09-08 — Three parallel corrective slices reviewed

**Input:** Completion of the bounded implementation and independent review
batch initiated by the user's resume and maximum-agent requests.

**Interpretation:** Record accepted local progress while preserving the
unfinished Task 6 runtime/evidence integration boundary.

**Decision status:** Specification and quality reviews passed for driver-Pod
admission, bounded Envoy refusal/control production, and the self-consistent
archive fixture correction. Root verification passed 51 driver/dependency
tests, 95 producer/journal/proof tests, and eight focused archive/controller
tests. Generated readers were refreshed and checked. These scoped passes do
not establish a passing repository-wide controller suite.

**Rationale:** The driver proof distinguishes manifest/tag identity from the
separately accepted config digest and rejects malformed or reconstructed
identities. Envoy control proves only the exact bounded textual refusal
classification and observed admin stats. The fixture now contains an actual
10,240-byte OCI archive and patches fixed acceptance constants rather than
hashing functions. Production archive size derives from already hash-verified
retained bytes, while the production config pin is unchanged.

**Affected artifacts:** The implementation worktree's driver and Envoy modules,
journal, controller, focused tests, plan and generated reader; this Markdown
lineage. All runtime profiles remain untouched.

**Unresolved questions:** The next experimentally reached controller gate is
`image_load_postcondition_unproved`: the legacy fake lacks node-store `ctr`
evidence. Ordered CRI image references, generated Pod admission, composition
of runtime proofs, durable/partial source evidence, and subsequent phase gates
remain unfinished. The actual pinned-image Bash diagnostic is a later live
compatibility check.

**Next gate:** Add source-correct node image-store/reference observations and
continue the existing Task 6 integration plan without opening readiness from
these standalone proofs.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
### T-204 — 2026-09-08 — Continue node image evidence with parallel workers

**Input:** The user requested continuation after the three reviewed corrective
slices, retaining the request to use available parallel agents.

**Interpretation:** Advance the next image-load proof boundary without enabling
live readiness: source-correct controller test observations, a bounded CRI
reference proof, exact read-only command grammar, and source/review preparation.

**Decision status:** Implementation and review in progress. The test-only
controller slice reaches image-load completion and next stops at Calico apply.
New CRI command grammar admits only fixed node-local inspection with the owned
Docker endpoint; no command was run against a container. Exact real-image target
media types are being independently verified before registry expectations are
populated; they must not be inferred from candidate output.

**Rationale:** Configuration IDs, manifest/index targets, ordered CRI aliases,
and Kubernetes image fields are distinct. Proofs must bind each representation
to independently accepted inputs and replayed Node identity rather than accept
a digest suffix or infer completion from command exit.

**Affected artifacts:** Implementation-worktree journal and command tests,
controller fixture, new node-image-reference module/tests, and this Markdown
lineage. Earlier accepted edits are preserved.

**Unresolved questions:** Exact real target media types; independent node proof
review; bracketed registry integration and persisted reference bindings;
Calico apply and remaining runtime/evidence composition.

**Next gate:** Review the bounded node-reference proof and source-correct
image-load fixture, then integrate their observations through shared replay.
All Colima mutations remain restricted to uniquely validated `kil-v3-lab`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-205 — 2026-09-08 — Node-reference proof and Calico observation progress

**Input:** Continue the approved Task 6 corrective work with available parallel
agents, preserving isolation of other Colima profiles.

**Interpretation:** Complete bounded offline image-reference and command
validation, then advance the controller fixture through the next genuine
postcondition without manufacturing later readiness.

**Decision status:** Node-reference specification review passed after strict
LF framing and actual row-cardinality checks; quality review is pending.
Image-load fixture review passed. The narrow Calico Unicode request fix and
source-derived Calico fixture passed specification and quality review. Root
verification passed 108 focused tests; 56 generated readers were refreshed
and checked. These results are not a repository-wide suite or live acceptance.

**Rationale:** The request builder previously ASCII-escaped pinned Unicode
descriptions while the journal required canonical UTF-8. Only command stdin
serialization changed; proof encoding remains unchanged. Regressions cover
bundle/context reconstruction and identical command rebuilding, not full
journal replay. The fake Calico response requires the exact successful scoped
apply, exact read command, and canonical pinned 38-object input. Missing,
extra, changed, and identity-deficient responses fail. The offline lifecycle
now reaches the missing application-observation gate.

**Affected artifacts:** Implementation-worktree node-image module/tests,
journal command tests, shared proof request builder, Unicode regression,
controller fixture, plan/reader, and this Markdown lineage. No runtime
profile was started, stopped, or otherwise changed.

**Unresolved questions:** Node-reference quality review; Envoy target media
type; registry identity bracketing and durable reference composition;
application observation and subsequent Task 6 evidence gates. The accepted
KIL archive was located in the prior central-proof worktree and independently
hash-verified: archive `07c12f338c7d764812ef6271ec8942f0535d05019288f4df1e1b54f6cd75e4b6`,
manifest `45a167d79b92f352af05a3e9cb8a9df8e972e38ab23d04ca692053e2eaf63649`
(1,622 bytes), config `f21285be21c8f691b9b60b7e38bb309564a5cc238512c7455eb7759f4d922ddb`
(7,538 bytes). Index and manifest agree on
`application/vnd.oci.image.manifest.v1+json`. This is source evidence, not a
new runtime dependency on the historical worktree.

**Next gate:** Complete node-reference quality review and diagnose the exact
application response contract; integrate only independently established image
expectations. Task 6, live acceptance, and V3C remain open.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-206 — 2026-09-08 — Close reviewed node-reference slice; retain composition gate

**Input:** Continue the current corrective batch through independent review.

**Interpretation:** Resolve the final scoped quality finding, verify the
combined changes, and identify the next authentic integration boundary.

**Decision status:** Node-reference quality review now passes. The proof
requires all four independently expected config/target identities to be
distinct before candidate parsing or hashing. Regression tests cover both
cross-role config/target collisions and equal targets. Root reran the combined
focused gate: 109 tests passed in 8.201 seconds. Earlier scoped Calico and
command review outcomes remain accepted; complete Task 6 acceptance is open.

**Rationale:** Independent expected descriptors still require internal
consistency. Application observations cannot be advanced honestly with a
static-only success fixture: real direct-driver Pods contain admission/CNI
additions, while the shared application comparison still uses the static
normalizer. Separate driver-Pod admission proofs exist but are not composed
at the relevant controller boundary. Service allocation proof alone does not
establish complete application API compatibility or readiness.

**Affected artifacts:** Implementation-worktree node-reference module/tests,
reviewed image-load/Calico fixtures and Unicode command fix, and this lineage.
No commits, pushes, or runtime mutations were performed during this batch.

**Unresolved questions:** Independently verify Envoy target media type;
compose node-reference evidence through bracketed journal replay; connect
direct-Pod admission and remaining runtime proofs without conflating apply
completion with readiness. Full controller/repository tests still require
subsequent integration work.

**Next gate:** Shared application/Pod proof composition and remaining image
expectation provenance, followed by real-shaped application observations.
Preserve the unique `kil-v3-lab` boundary and leave other profiles untouched.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-207 — 2026-09-08 — Separate apply configuration from readiness; integrate image replay

**Input:** The user approved continuation after selecting Astra Medium for
integration work, retaining parallel-agent authorization.

**Interpretation:** Advance the approved application proof boundary without
requiring a newly applied driver to be running prematurely. Integrate the
independently reviewed node-image reference proof into collection and replay.

**Decision status:** Separate pre-CNI driver configuration proof passed
specification and quality review after rejecting Pod UIDs that collide with
the retained cluster Namespace UID. It retains canonical metadata/spec
projections, immutable inputs, and three UID/resourceVersion bindings; optional
managedFields and bounded last-applied metadata remain validated and retained.
Status and CNI enrichment remain explicit unsupported boundaries, not silently
discarded evidence. This proof is not full application completion or readiness.

**Rationale:** The existing driver admission proof requires running/ready
containers and platform endpoints. Applying it to immediate post-apply
configuration would conflate lifecycle stages. Separately, image-load evidence
now binds the exact pending image intent, two-sided node name/ID/image/label
observations, two CRI reads, the node-store read, namespace incarnation, and
Kind configuration. Reference bindings are established only through successful
proof recalculation and retained for offline replay. Tests reject immutable
binding injection and tampered raw evidence even after bundle hashes are repaired.

**Affected artifacts:** Implementation-worktree configuration module/tests,
shared proofs and image integration tests, controller preflight/fixtures,
legacy image and timeout test fixtures, plan/generated reader, and this lineage.
Controller specification review passed; final controller quality review and
combined verification are in progress. The timeout fixture correction preserves
partial raw bytes and teardown-only behavior rather than relaxing recovery.

**Source evidence:** A scoped approved read-only Docker Hub request returned
the pinned Envoy manifest endpoint's 493-byte body. Its SHA-256 equals
`57e14a549d7bd43c8d3f6d03e8cfa653e037d4b38e133acd9b54f38c524401b4`,
the Docker-Content-Digest agrees, and Content-Type plus body mediaType both
declare `application/vnd.oci.image.index.v1+json`. The bearer token was retained
only in memory, not displayed. KIL's optional canonical repository/digest alias
is derived from its independently accepted manifest; presence is not assumed.
No containers or Colima profiles were changed.

**Unresolved questions:** Calico CNI annotation intermediate-state semantics;
configuration-source byte joins; policy-stage and generated Pod ownership
collection; full application and readiness composition. Standalone proofs must
not open those terminal gates prematurely.

**Next gate:** Verify the combined scoped tests and finish independent review,
then extend application configuration only with source-backed CNI relations
and retained ownership evidence. Other Colima profiles remain out of scope.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-208 — 2026-09-08 — Same-source configuration and historical policy checkpoint

**Input:** Continue the approved Task 6 corrective work with parallel agents.

**Interpretation:** Separate apply-time configuration, historical ordering, and
later readiness rather than treating one final inventory as proof of all three.

**Decision status:** The earlier combined focused gate passed 192 tests; this
was not the repository-wide suite. Controller image-reference integration passed
specification and quality review. Driver configuration now accepts source-backed
Calico ADD annotation pairs, with optional sandbox identity and owned-node
scheduling; it does not require Pod status to have caught up. The policy-stage
pure proof passed re-review after exact argv/environment type checks and actual
preflight profile-schema validation. A sixty-object same-source configuration
composer and durable controller checkpoint are implemented, with integration
and producer-compatibility reviews still in progress.

**Rationale:** Calico v3.32.0 workloadendpoint.go patches the IP annotation pair
together, may include a container ID, and documents that kubelet status can lag.
Its delete path blanks the pair, which this ADD-only configuration relation
rejects. A final policy read cannot establish that policy configuration existed
before workload dispatch; historical evidence must be published first and must
not be recreated during recovery.

**Source evidence:** A read-only lookup of Kubernetes v1.36.1 kubectl get.go
confirmed that printGeneric constructs a composite List and supplies List
metadata with an empty resourceVersion. Review found the new configuration
and policy-stage envelopes too narrow for that producer shape; narrowly scoped
regressions and corrections are underway, without accepting nonempty or unknown
List metadata as authority.

**Affected artifacts:** Implementation-worktree driver configuration, application
configuration, policy-stage and checkpoint modules/tests, controller barrier,
plan, and this lineage. No runtime operations, commits, or pushes in this batch.

**Unresolved questions:** Checkpoint terminal replay and final policy identity
continuity; generated Pod ownership collection; complete application/readiness
composition; full controller and repository verification. Task 6 remains open;
live validation and V3C have not been authorized by a passing gate.

**Next gate:** Finish checkpoint and producer-envelope reviews, then compose
historical and current evidence without weakening the remaining terminal gates.
Only `kil-v3-lab` may be mutated in any later runtime work; other profiles remain
untouched.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-209 — 2026-09-08 — Accept checkpoint barrier after recovery-read race fixes

**Input:** Continue through independent review of the new policy ordering barrier.

**Interpretation:** A successful read must bind both the historical checkpoint
and the currently named private directory, not a detached directory descriptor.

**Decision status:** Checkpoint/controller specification and quality review
passed. Review reproduced permission drift and parent rename/replacement races;
new before/after directory mode, owner, and named-inode checks reject both.
The normal controller now publishes policy-stage evidence before dispatching
workloads, and publication or evidence failure blocks dispatch and latches
teardown. Recovery has no new checkpoint producer. Producer-envelope fixes in
configuration and policy proofs also passed independent review.

**Rationale:** Private file checks alone did not protect the parent directory's
identity across a read. Historical evidence must remain bound to its exact
pending context and fixed private filename. Neither that checkpoint nor the
configuration-only composer establishes generated Pod admission or readiness.

**Verification:** Root ran 192 focused tests successfully in 16.525 seconds,
then 12 checkpoint/controller tests successfully in 19.866 seconds after the
directory fixes. All 56 generated readers were verified before the latest plan
status update; regeneration remains a final documentation step. This is scoped
verification, not a passing repository-wide acceptance run.

**Affected artifacts:** Implementation-worktree checkpoint module/tests,
controller ordering and fixtures, configuration/policy envelope checks, plan,
and this lineage. No runtime mutations, commits, or pushes.

**Unresolved questions:** Shared terminal replay still needs the historical
checkpoint/current policy UID join. Runtime collection currently lacks Node
and ReplicaSet observations required by the existing generated ownership proofs.
Do not require unchanged resourceVersion across distinct observations merely
to establish UID continuity; controller status updates can legitimately advance it.

**Next gate:** Derive ownership projections from one retained runtime List,
then compose configuration and historical policy evidence while keeping the
full application terminal closed until all approved obligations are satisfied.
`kil-v3-lab` remains the only permitted runtime profile.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-210 — 2026-09-08 — Replay boundary and same-source runtime adapters

**Input:** Continue implementation; the user reiterated standing authorization
for KIL work and asked how to avoid repeated manual security approvals.

**Interpretation:** Continue routine approved work without conversational
checkpoints. This does not change the app's enforced permission policy or
permit mutation of other projects or Colima profiles.

**Decision status:** The application registry now retains five observations,
including the original policy checkpoint, and composes eighteen policy UID
continuity relations with the later sixty-object configuration. Fresh cluster
observations are revalidated before reporting even the pending summary; three
poisoned-bracket regressions initially failed and now pass. The application
decision remains unknown until remaining generated admission/container gates.
Runtime ownership and nine generated KIL Pod configuration adapters passed
specification and root quality review. Endpoint adapter review identified
contradictory target-reference fields being discarded; the fix awaits final
re-review.

**Rationale:** One retained runtime List now supplies closed ownership-family
projections rather than caller-supplied fragments. Generated configuration is
derived independently from rendered Deployment templates. Kubernetes v1.36.1
controller_utils.go and replica_set.go confirm the standard ReplicaSet-name
plus dash generateName path. Pinned legacy Endpoints and EndpointSlice producers
both construct four-field Pod references (kind, namespace, name, UID), so extra
API-version, resource-version or field-path claims must be rejected before
projection. Service status remains bounded and uninterpreted, not schema-validated.

**Verification:** Root ran 50 runtime ownership tests successfully, 45 endpoint
tests before the target-reference correction, and 38 generated configuration,
application-boundary and shared-proof tests after the cluster-bracket correction.
The endpoint author reports 46 tests passing after its source-backed correction;
independent re-review is pending. These are scoped gates, not full acceptance.

**Affected artifacts:** Implementation-worktree application boundary, checkpoint
byte reader, shared registry/controller collector, runtime ownership/endpoints,
generated KIL Pod configuration and their tests; plan and this lineage. No
runtime mutations, commits, pushes or permission-setting changes.

**Unresolved questions:** Node/ReplicaSet collection and typed parser integration;
runtime image-reference and ready-container joins; generated platform/Calico Pod
admission; retained pre-driver listener readiness ordering. No completion flags
are promoted by configuration or ownership alone.

**Next gate:** Finish endpoint review and compose the new relations into the
runtime collector without weakening the remaining application/readiness gates.
Standing authorization remains limited to KIL; only `kil-v3-lab` may be mutated.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-211 — 2026-09-08 — Ownership integration and KIL runtime image relations

**Input:** Continue approved KIL implementation without routine confirmation;
retain Astra Medium unless the work warrants a change. The environment now
reports automatic review of eligible sandbox escalation requests.

**Interpretation:** Continue the existing corrective plan. Automatic review
does not grant unrestricted authority or permit operations on other projects
or Colima profiles. No permission configuration was edited by the agent.

**Decision status:** Endpoint target-reference correction passed specification
and quality review. Exact Node/ReplicaSet collection and same-raw proof-backed
parser admission passed independent specification and root review. The new
twelve-KIL-Pod runtime proof passed specification and root review, joining
configuration, endpoints and node image references without completing the
broader runtime contract. Implementation of a separate proof-backed public
image-row projection is in progress; production wiring remains deferred.

**Rationale:** Requested image references, runtime Image and realized ImageRef
are different domains. Legacy DTO suffix equality cannot represent the pinned
runtime faithfully. Preserve those existing rejection checks until replacement
enclosing proofs retain and reconstruct independent authority. ContainerStatus
source-known optional fields remain bounded and retained, not nested-schema
certified. Fresh running restart-zero containers accept only absent/empty
lastState; malformed condition entries cannot be silently discarded.

**Verification:** Root ran 131 focused inventory, ownership, integration,
journal, shared-proof and KIL runtime tests successfully in 11.137 seconds.
An earlier invocation used an incorrect test-module name and failed import;
the corrected invocation is the reported successful run. All 56 generated
Markdown readers verified and worktree diff whitespace checks passed. These
are scoped gates, not a repository-wide or live-cluster acceptance result.

**Affected artifacts:** Implementation-worktree runtime ownership collector,
inventory parser, command grammar, KIL Pod runtime proof and tests; corrective
plan and generated reader; this lineage. No runtime mutations, commits or
pushes were performed in this continuation.

**Unresolved questions:** Proof-aware inventory/evidence reconstruction;
fresh single-Pod image/incarnation checks; platform/Calico admission and image
authority; retained pre-driver readiness ordering and live stability checks.

**Next gate:** Review the twelve-row image projection, then integrate retained
authority into evidence replay before changing production image acceptance.
Task 6 remains open; live validation and V3C remain gated. Only `kil-v3-lab`
may be started, stopped or otherwise mutated.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-212 — 2026-09-08 — Finite public image membership and private replay source

**Input:** Continue approved work; avoid routine manual confirmations.

**Interpretation:** Advance the existing Task 6 corrective integration while
automatic security review handles eligible escalation requests. No change to
the unique `kil-v3-lab` runtime scope or other-project protections.

**Decision status:** The twelve-row image projection, shared full node-image
reconstruction helper, fixed accepted-image descriptors, public image verifier
integration and workload DTO migration passed specification and root review.
Public requested image identities now bind the accepted production pair rather
than arbitrary self-consistent digests. A versioned, lossless private source
propagation implementation is under corrective review, not yet accepted.

**Rationale:** Public finite membership and private observed provenance are
different claims. The accepted manifest commits the requested targets; the
previously verified archive/registry chains bind their config identities. KIL
may report its exact config ID or canonical repository target digest, while
Envoy uses the exact accepted repository/index digest. The public schema does
not need extra fields to express these values. After establishing this fixed
verifier-owned contract, tightening workload DTOs is preferable to duplicating
the complete inventory hierarchy. This supersedes the temporary implementation
constraint to leave workload DTO checks unchanged; it does not introduce broad
digest acceptance, constructor bypasses or a provenance exemption. Calico and
fresh single-Pod lifecycle DTOs remain unchanged.

**Verification:** Root ran 36 projection/runtime/inventory tests, 3 fixed-image
contract tests, 97 public evidence/inventory/shared-proof tests, 45 node-image
reconstruction tests and 107 DTO/evidence/inventory/projection/shared-proof
tests successfully. These overlapping runs are not an aggregate unique-test
count. Root independently rehashed the accepted V3B1 public manifest to
`fa39212f1ffad95a1b5a674021ac5ce4ed9458025ce0dcc80077070355141cd0`.
Source review reproduced a writer/replay size-limit mismatch and acceptance
of null markers and duplicate historical terminals; fixes and expanded
compatibility/boundary tests are required before accepting that replay slice.

**Affected artifacts:** Implementation-worktree accepted image descriptors,
image projection, evidence verifier, workload DTO, shared reconstruction helper,
tests and corrective plan; private replay source code under review; this log.
No runtime operations, commits, pushes or permission-setting edits.

**Unresolved questions:** Lossless source propagation and old-context byte
compatibility; proof-required runtime parser wiring; fresh single-Pod image
observations; platform/Calico admission; pre-driver readiness ordering and
private-to-public provenance comparison.

**Next gate:** Complete independent replay-source re-review, then require its
reconstructed image authority in same-source runtime parsing. Membership-only
DTOs cannot authorize dispatch. Task 6, live validation and V3C remain open.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-213 — 2026-09-08 — Proof-required runtime wiring and distinct pre-driver phase

**Input:** Continue approved Task 6 corrective work without routine approval
pauses; retain unique ownership of the `kil-v3-lab` runtime profile.

**Interpretation:** Complete image provenance wiring and implement the already
approved ordering invariant with retained pre-driver evidence, not a new lab
topology or an expanded runtime experiment.

**Decision status:** The corrected private image-source seam passed independent
specification and root quality review. Production-style inventory parsing now
requires the exact reconstructed KIL runtime proof. Controller and readiness
paths use the shared same-source composition; application/runtime completion
flags remain unchanged. Separate 19-Pod pre-driver ownership passed review;
nine-Pod pre-driver configuration/runtime composition is in progress.

**Rationale:** Source summaries are not authority. New runs explicitly opt into
lossless replay using `node_image_source_version: 1`; absent-marker historical
contexts retain their existing encoding. The successful source cap is enforced
before terminal persistence and during replay, with non-allocating JSON size
preflight and exact typed historical intent/terminal records. Abandoned evidence
retains the larger general proof budget. The controller authenticates image
authority while application intent is pending, avoiding a context lookup after
that intent has closed. Pre-driver ordering needs its own 19-Pod proof, rather
than fabricated drivers or relaxed 22-Pod runtime cardinality.

**Verification:** Root ran 53 source/reconstruction/shared-proof tests, 112
proof-required inventory/evidence/projection tests, 89 shared-glue/source/public
evidence tests, and 60 pre-driver/runtime/generated-ownership tests successfully.
Counts overlap and are not a unique aggregate. Independent review additionally
replayed a 4,203,661-byte abandoned bundle without creating a successful source.
The ready-stage ownership API and original ownership regressions remain intact.

**Affected artifacts:** Implementation-worktree shared replay, controller,
inventory glue, proof-required parser, distinct pre-driver ownership adapter,
tests and corrective plan; this lineage. No runtime operations, commits, pushes
or permission-setting edits were performed.

**Unresolved questions:** Pre-driver ready/configuration checkpoint and durable
ordering; later application identity continuity; fresh single-Pod lifecycle
images; remaining platform/Calico admission; versioned private/public image
projection continuity. None is satisfied merely by a passing image DTO.

**Next gate:** Validate the nine generated workloads in the driver-absent phase,
persist that evidence before driver apply, and retain/revalidate it during
application replay. Full Task 6 and live validation remain gated.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-214 — 2026-09-08 — Durable pre-driver evidence and publication image continuity

**Input:** Continue the approved corrective implementation without routine
approval pauses. Preserve exclusive mutation scope for `kil-v3-lab`.

**Interpretation:** Finish the separate driver-absent proof and durable evidence
barrier, while binding public image rows to the exact private readiness
selection. These are implementation gates within the approved plan, not
authorization to advance into live testing or alter other runtime profiles.

**Decision status:** Nine-Pod pre-driver runtime composition, its canonical
durable checkpoint, and versioned public image provenance passed independent
specification and root quality review. Normal controller checkpoint wiring is
under implementation. Review identified an inherited existing-FIFO blocking
case in the shared private publisher; its narrow nonblocking-open correction
is under separate verification. No application/runtime completion flag was
promoted.

**Rationale:** A successful readiness poll does not retain evidence that the
nine generated workloads were healthy before drivers existed. The checkpoint
preserves the exact five-observation cluster bracket and full 19-Pod source,
reconstructs historical node-image authority, and joins eighteen historical
policy configurations/UIDs without treating resourceVersions as clocks. Its
publisher authenticates the pending journal context and reads the already
durable policy checkpoint itself. Public finite image membership is separately
insufficient: the actual seventeen readiness-selected rows must match exactly,
even when another alias would also pass public semantic validation.

**Verification:** Root ran 93 publication/provenance/evidence/replay/glue tests
and 49 pre-driver checkpoint/policy/runtime/application-boundary tests
successfully, in addition to the previously verified 55-test pre-driver runtime
composition gate. These overlapping suites are not a unique aggregate count.
Checkpoint filesystem tests exercise actual publication and strict reads but
mock journal loaders; provenance fixtures exercise the authenticated-context
boundary, not full readiness lifecycle replay. The broad repository/controller
suite is not claimed green.

**Affected artifacts:** Implementation-worktree pre-driver runtime and durable
checkpoint modules, shared strict checkpoint reader, public provenance guard,
publication call sites, focused tests and corrective plan; this lineage. No
runtime operations, commits, pushes or permission-setting edits were made.

**Unresolved questions:** Controller barrier wiring and later application
identity continuity; fresh single-Pod lifecycle/source-capture image proof;
full platform/Calico admission and image chains; final fixture migration and
complete regression verification. Historical image-load authority alone does
not establish freshness at later lifecycle observations.

**Next gate:** Accept the nonblocking publisher regression, complete the normal
pre-driver dispatch barrier, and retain the historical checkpoint in terminal
application replay. Task 6, live validation and V3C remain open.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-215 — 2026-09-08 — Driver dispatch barrier and cross-phase incarnation joins

**Input:** Continue the approved Task 6 corrections through the next safe
implementation steps without routine confirmation prompts.

**Interpretation:** Enforce the accepted pre-driver evidence barrier in normal
dispatch, then independently prove continuity to the later twelve-KIL-Pod
snapshot before connecting terminal replay.

**Decision status:** The shared FIFO correction, normal controller barrier and
pure application/runtime boundary passed specification and root quality review.
Terminal registry and evidence-budget integration remain pending. No runtime
or full-application completion flag was enabled.

**Rationale:** The shared publisher now opens an existing destination without
blocking and still rejects nonregular, linked, nonprivate or changed evidence.
The controller authenticates local application authority, collects five fresh
observations, and persists them before any driver apply. Later composition
reconstructs sixty configurations from the same retained current runtime List,
preserves eighteen policy identities, and joins the nine generated Pod UIDs,
container/sandbox/IP/image/start identities. ResourceVersions identify each
observation; changes do not imply replacement and equality does not excuse a
changed container. Recovery never regenerates the historical barrier.

**Verification:** Root ran 83 publisher/journal/checkpoint tests, 30 controller/
checkpoint/provenance/glue tests, and 34 application/runtime-boundary tests
successfully. Counts overlap. The FIFO regression uses a bounded child process;
controller tests use real private evidence files with mocked journal and runtime
boundaries. Continuity regressions reconstruct independently valid changed
runtime proofs before rejecting cross-phase substitutions. Fifty-six generated
Markdown readers were verified before the latest plan status update; regeneration
remains part of the next documentation check.

**Affected artifacts:** Implementation-worktree controller, private publisher,
new application runtime boundary, focused tests and corrective plan; this log.
No live runtime operations, commits, pushes or permission-setting changes.

**Unresolved questions:** Terminal replay must retain both historical and current
evidence without violating existing serialization limits. A compact encoding was
proposed during review; operation-local bounds using the unchanged encoding are
being evaluated before selecting the smaller implementation. Fresh lifecycle
image observations, complete platform/Calico admission and broad regression
fixture migration remain separate open gates.

**Next gate:** Resolve and test the application evidence size contract, wire the
historical checkpoint/current snapshot terminal registry, and preserve explicit
incomplete outcomes until the remaining platform and lifecycle proofs close.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-216 — 2026-09-08 — Versioned application terminal replay checkpoint

**Input:** Continue approved work; the maintainer subsequently asked how much
longer the current step would take. Report this bounded step separately from
the remaining Task 6 work.

**Interpretation:** Complete terminal evidence retention and replay under
explicit operation-local budgets without changing the general proof encoding
or prematurely claiming full platform readiness.

**Decision status:** Application evidence budgets and versioned terminal wiring
passed independent specification and root quality review. The current terminal
replay step is complete. Task 6, live validation and V3C are not complete.

**Rationale:** The explicit `application_source_version: 1` selects six sources:
historical pre-driver checkpoint plus the current five-observation runtime
bracket. Absent markers retain the old five-source path. Twenty MiB of historical
checkpoint bytes, eight MiB of current raw outputs, five MiB of context, one MiB
of bindings and one MiB of metadata fit within the unchanged 64 MiB general
envelope after hexadecimal expansion. Writer and encoded replay share the
bounds. Prospective context and command metadata are checked before appending
application intent; bounded failed evidence remains available for abandonment.
Recovery reads history only. The composed result retains nine runtime and
eighteen policy continuity bindings but explicitly reports the outstanding
platform-admission gate.

**Verification:** Root ran 44 budget/source/shared-proof tests and 49 focused
terminal/controller/budget/boundary/provenance tests successfully. Independent
review found an unnormalized filesystem error in preflight; after its TDD fix,
root ran 34 terminal/checkpoint/budget tests successfully. Counts overlap and
are not a unique aggregate. The abandoned application proof test genuinely
replays through `expected_context`; it does not claim a successful complete
application lifecycle. Whitespace validation passed. Broad controller and
repository-wide regression completion remain unclaimed.

**Affected artifacts:** Implementation-worktree application budget and terminal
modules, shared writer/replay registry, controller preflight and collector,
tightenable historical checkpoint reader, focused tests and corrective plan;
this lineage. No live Colima, Docker or Kubernetes commands, commits or pushes.

**Unresolved questions:** Complete admission/runtime/image proofs for ten
platform Pods; fresh single-Pod driver, quiescence and source-capture identity
evidence; broader fixture migration. A parallel read-only audit identified the
vendored Calico controller as the next bounded adapter. Pinned priority-class
defaulting was directly fetched after browser cache misses, but no platform
configuration or image gate was enabled from source inspection alone.

**Next gate:** Implement and review the source-backed Calico-controller admission
adapter, then remaining platform and lifecycle image contracts. The completed
pre-driver/terminal step must not be presented as full Task 6 completion.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-217 — 2026-09-08 — Calico-controller configuration implementation resumed

**Input:** The maintainer asked whether to change models and directed work to
continue if not.

**Interpretation:** Continue the approved next bounded platform configuration
slice on Astra Medium; no demonstrated reasoning blocker warrants a model
change. Model selection does not change the remaining evidence gates.

**Decision status:** Calico-controller configuration implementation is in
progress, not accepted yet. Preserve false runtime/application completion flags
and do not enable live validation from this partial adapter.

**Rationale:** Independently authenticated Calico manifest bytes supply the
Deployment and ServiceAccount configuration. Generated Pod expectations must
follow pinned controller/admission producers rather than observed templates.
Source review confirmed that generated metadata discards template name and
namespace, that the deprecated service-account alias follows the modern field,
and that the two template NoSchedule tolerations retain omitted operators.
Token projection expiry is explicitly 3607 seconds. Matching these expected
outputs is not evidence of actual PriorityClass/plugin configuration, issued
tokens, mounted contents, readiness or realized runtime images.

**Affected artifacts:** Implementation-worktree corrective plan and new
Calico-controller configuration module/tests under development; this lineage.
The existing 54 focused ownership, generated/direct Pod configuration and API
default tests passed before acceptance of the new adapter. No live cluster,
Colima, Docker, commit or push operations were performed.

**Unresolved questions:** Independent specification/quality review of the new
adapter; remaining nine platform Pod configurations and all required platform
runtime/image composition; fresh single-Pod lifecycle evidence and broader
fixture migration. Source serialization closure is distinct from effective
admission-environment authority.

**Next gate:** Finish the Calico-controller adapter's failing-regression,
implementation and independent review cycle, then proceed to the remaining
platform/lifecycle contracts. Task 6 remains open.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-218 — 2026-09-08 — Calico-controller configuration slice accepted

**Input:** Continue the approved implementation without routine approval pauses.

**Interpretation:** Finish the bounded controller configuration adapter and its
review cycle; do not confuse this with full platform or Task 6 completion.

**Decision status:** Accepted after independent specification/quality review
and root inspection. Nine new test methods cover valid serialization and
adversarial subcases. Root freshly ran 63 focused tests successfully; the
specification reviewer independently ran the nine new tests successfully.
The quality reviewer's initial host-Python import failure was environmental
and is not counted as another passing verification run.

**Rationale:** The proof retains exact checksummed manifest/projection bytes
and the full ownership source, compares the same-source Deployment and
ServiceAccount to independently authenticated expectations, and reconstructs
the sole generated Pod's configuration. Token projection/mount correlation,
priority, tolerations, scheduling, CNI annotations and incarnation metadata
are closed within this configuration scope. Status remains uninterpreted;
runtime and application completion flags remain false.

**Affected artifacts:** New implementation-worktree Calico-controller
configuration module and focused tests; corrective plan and generated reader;
this append-only lineage. No live Colima, Docker or Kubernetes commands,
commits, pushes or modifications to other project profiles.

**Unresolved questions:** Cross-Pod network uniqueness, effective admission
environment, remaining platform configurations and realized image identity,
fresh lifecycle proofs and broad fixture migration. The next Calico-node
adapter additionally needs source-backed DaemonSet revision metadata: pinned
history construction derives new labels from template/collision count but
can repair historical missing labels using the ControllerRevision name.
Existing ownership observations do not retain that revision authority.
Pinned toleration matching was fetched directly and confirms exact tuple
matching, not wildcard taint coverage, for DaemonSet additions.

**Next gate:** Resolve the bounded fresh DaemonSet revision/configuration
contract, then implement Calico-node and remaining platform/lifecycle proofs.
No collector expansion or full-readiness claim follows silently from this
accepted configuration-only slice. Astra Medium remains adequate for the
current bounded implementation/review work.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-219 — 2026-09-08 — Calico-node revision relationship contract

**Input:** Continue the approved testing implementation.

**Interpretation:** Resolve revision authority before implementing the next
platform Pod configuration, preserving existing collector and live gates.

**Decision status:** Implement the bounded opaque revision relationship under
the existing configuration plan. Independently authenticated revision template
content supplies configuration authority; DS/revision/Pod UID and label joins
supply identity. The label is not represented as a recomputed Kubernetes hash.
Implementation and review are in progress, not accepted yet.

**Rationale:** Pinned history construction retains a replacement template patch
and copies DS annotations. Its raw data receives no later Pod defaulting, so
candidate patch content must compare exactly to independently derived typed
template output. The pinned Go 1.26/ObjectMeta omitzero combination omits a zero
template timestamp, while container resources retain ordinary struct `{}`
serialization. ControllerRevision creation strategy does not set generation.
Candidate selection includes owner UID/name, identifying label and name prefix
to expose contradictory or orphan Calico histories instead of filtering them
out. Structural content identity is distinct from Go byte encoding and hashing.

**Affected artifacts:** Implementation-worktree corrective plan and new
revision relationship module/tests under development; this lineage. Existing
36 controller/ownership tests passed. Root read pinned Kubernetes/containerd
sources confirming hostNetwork selects NODE networking and skips CNI setup;
Calico's reviewed annotation patch-in path requires CNI mode. No live commands,
collector expansion, commits, pushes or other Colima-profile changes.

**Unresolved questions:** Independent implementation reviews; Calico-node full
configuration composition; fresh observation integration and all remaining
platform/runtime/lifecycle gates. Consistently changing an opaque revision
label/name/Pod-label trio is deliberately not rejected as a content-hash
mismatch when the independently required template remains identical.

**Next gate:** Accept the revision relationship after regression and review,
then compose the Calico-node configuration without claiming full readiness.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-220 — 2026-09-08 — Revision relationship accepted; node configuration begun

**Input:** Continue approved work through bounded review checkpoints.

**Interpretation:** Accept the completed revision relationship and proceed
directly to Calico-node Pod configuration, without a routine approval pause.

**Decision status:** Revision relationship passed independent specification,
independent quality and root quality review. Root's final combined run passed
70 tests; the quality reviewer independently passed eleven focused revision
tests. Full Calico-node configuration implementation is now in progress.

**Rationale:** The revision adapter authenticates template content, retains
raw evidence and reconstructs owner/incarnation/opaque-label joins. TDD exposed
and fixed a candidate selector that mistakenly included Calico-labeled
ServiceAccounts. Candidate data is not normalized. The next adapter separately
checks the complete Pod, including four containers, thirteen volumes, exact
token mounts, host-network configuration and DaemonSet scheduling additions.

**Affected artifacts:** Accepted revision module/tests and corrective plan;
new Calico-node configuration module/tests under development; this lineage.
No collector or terminal integration, live operations, commits or pushes.

**Unresolved questions:** Calico-node configuration reviews; subsequent
platform image/runtime evidence, remaining platform Pods, fresh collection
and lifecycle proofs. Opaque revision identity does not become a recomputed
content hash in the composition, and false completion flags remain required.

**Next gate:** Complete Calico-node configuration TDD and independent reviews,
then remaining platform/runtime/lifecycle contracts. Task 6 remains open.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-221 — 2026-09-08 — Calico-node admitted configuration accepted

**Input:** Continue the approved next platform validation work.

**Interpretation:** Complete the full Calico-node Pod configuration adapter
after accepting its separate revision relationship.

**Decision status:** Accepted after specification, independent quality and
root quality review. Root ran 80 focused tests successfully; both independent
reviewers ran all ten new configuration tests successfully. These overlapping
counts are not a unique aggregate or a repository-wide regression claim.

**Rationale:** The proof reconstructs its exact retained revision dependency,
uses independently pinned template and ServiceAccount expectations, and checks
complete Pod metadata/spec. It enforces the sole DS owner, opaque revision
label, owned-node affinity, ordered tolerations, thirteen volumes and token
mount correlation across all four containers. Source privilege, host paths,
images, grace zero and host networking are preserved. CNI and other Pod
annotations are rejected under the reviewed producer configuration; status,
effective runtime properties and image realization remain uncertified.

**Affected artifacts:** New Calico-node configuration module and tests;
corrective plan and generated reader; this lineage. No live cluster or Colima
operations, collector expansion, terminal integration, commits or pushes.

**Unresolved questions:** CoreDNS parent/two-Pod configuration, local-path,
kube-proxy and four static mirrors; platform image/runtime evidence; fresh
revision collection, lifecycle evidence and broader fixtures. Read-only source
preparation confirmed CoreDNS defaults and the Deployment maxSurge `25%`
addition that is not supplied by the existing generic normalizer. A public
registry HEAD request identified the pinned Calico-node image as a manifest
list; this was not promoted to an image realization proof.

**Next gate:** Source-backed CoreDNS parent configuration, then its generated
Pods and the remaining platform/runtime/lifecycle contracts. Task 6 and V3C
remain incomplete; no full-readiness flag was enabled.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-222 — 2026-09-08 — CoreDNS parents accepted; Pod configuration begun

**Input:** Continue implementation through the remaining platform families.

**Interpretation:** Proceed from accepted Calico-node configuration into the
independent CoreDNS parent and generated-Pod contracts.

**Decision status:** CoreDNS parent configuration passed specification,
independent quality and root quality review. Both reviewers passed eleven
focused tests; root passed 91 combined tests. Two-Pod configuration is now
under implementation and has not yet been accepted.

**Rationale:** Fresh verifier-owned literals define the complete pinned
Deployment/ServiceAccount output, including two replicas, CoreDNS v1.14.2,
resource requests/limit, five ports, probes and maxSurge `25%`. Exact ownership
retains the two-Pod chain; observed templates cannot redefine expectations.
The Pod memory-pressure question was resolved separately: pinned
TaintNodesByCondition handles Nodes only; the non-BestEffort Pod mutation is
in PodTolerationRestriction, which is not default-on in the pinned API server.
The next proof therefore checks the reviewed default-profile output while
leaving effective admission-environment authority outside its claim.

**Affected artifacts:** New CoreDNS parent module/tests, corrective plan and
reader; CoreDNS Pod module/tests under development; this lineage. Read-only
pinned Kubernetes and Kind source inspection also located the later local-path
template. No live operations, collector changes, commits or pushes.

**Unresolved questions:** CoreDNS two-Pod review; local-path, kube-proxy and
static mirrors; platform realized images/status, fresh collectors and lifecycle
evidence. The memory-pressure rule must not be generalized to installations
that enable additional admission plugins.

**Next gate:** Complete the two-Pod configuration and reviews while preserving
false completion flags, then continue remaining platform contracts.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-223 — 2026-09-08 — CoreDNS two-Pod configuration accepted

**Input:** Continue through the current implementation phase.

**Interpretation:** Complete the in-progress CoreDNS review gate, then advance
to the source-prepared local-path family without routine approval pauses.

**Decision status:** CoreDNS two-Pod configuration accepted after specification,
independent quality and root review. Both reviewers passed seven focused tests;
root passed 131 combined platform configuration/revision/ownership/default tests.
These overlapping scoped runs do not establish a repository-wide pass.

**Rationale:** Exact retained parent reconstruction precedes independent Pod
configuration comparison. Generated identities, owner/hash joins, ordered token
projection and mounts, source resources, priority, tolerations and optional
owned-node/CNI annotations are checked. CNI uniqueness is pair-local; token
names may coincide between Pods. Status remains retained but uninterpreted,
and runtime/application completion flags remain false.

**Affected artifacts:** CoreDNS Pod module/tests, corrective plan and reader;
local-path parent implementation checklist; this lineage. No live operations,
collector expansion, commits or pushes. Other Colima profiles were untouched.

**Unresolved questions:** Local-path, kube-proxy and static mirror configuration;
platform runtime/image proofs, effective admission profile, fresh collectors and
lifecycle evidence. Local-path zero priority must be qualified by absence of a
global-default PriorityClass rather than claimed as universal admission.

**Next gate:** Implement and review the independent local-path parent output
contract, then its generated Pod. Task 6 and V3C remain incomplete.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-224 — 2026-09-08 — Local-path parents accepted; generated Pod next

**Input:** Continue the approved remaining platform configuration work.

**Interpretation:** Execute the independently source-audited local-path family
after CoreDNS acceptance without broadening configuration proof into runtime.

**Decision status:** Local-path Deployment/ServiceAccount adapter accepted after
specification, independent quality and root review. Both reviewers passed nine
focused tests; root passed 140 combined platform/ownership/default tests.
Generated-Pod configuration remains the next implementation gate.

**Rationale:** Independent fresh Kind literals preserve absent root labels,
explicit string strategy percentages, command/helper-image argument, ordered
environment/tolerations and writable trailing-slash config mount. Exact retained
ownership is reconstructed; candidate templates cannot redefine expectations.
Status, mounted content, helper execution and image realization remain excluded.

**Affected artifacts:** Local-path parent module/tests, corrective plan/reader,
generated-Pod checklist and this lineage. Read-only kube-proxy source preparation
also confirmed inherited proxy environment additions in its kubeadm producer;
that future contract must not silently assume a universal one-entry environment.
No live operations, collector integration, commits or pushes were performed.

**Unresolved questions:** Local-path Pod configuration; kube-proxy and static
mirrors; effective priority/admission/environment inputs; platform runtime/image
proofs, revision collectors and lifecycle evidence. Focused tests are not a
repository-wide green result.

**Next gate:** Test-first local-path generated-Pod validator and independent
reviews, preserving false completion flags and untouched foreign Colima profiles.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-225 — 2026-09-08 — Local-path Pod accepted; static producer mismatches reproduced

**Input:** Continue the platform verification implementation.

**Interpretation:** Finish local-path configuration review and investigate the
first source-compatibility prerequisite found by the static-mirror audit.

**Decision status:** Local-path Pod adapter passed specification, independent
quality and root review. Both reviewers passed eight focused tests; root passed
148 combined tests. Two pre-existing static ownership incompatibilities are
confirmed by pinned source and isolated reproductions; correction is next.

**Rationale:** The local-path proof independently checks its one generated Pod,
ordered token/config mounts, source fields, priority and CNI metadata without
claiming runtime completion. Separately, Kubernetes v1.36.1 static defaults use
FNV128a and hex32, not SHA-256 hex64. Mirror creation supplies a five-field Node
owner without blockOwnerDeletion, unlike DaemonSet owners. Existing ownership
rejected each producer shape independently. Inspected Pod defaults add no owner
flag, and GC admission validates rather than mutates owner references. Earlier
passing fixtures encoded these incorrect assumptions and do not prove live
compatibility. This entry explicitly corrects that interpretation without
rewriting earlier acceptance records.

**Affected artifacts:** Local-path Pod module/tests, corrective plan/reader;
planned node ownership and static-fixture correction; this lineage. Source reads:
[static defaults](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/config/common.go),
[mirror creation](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/pod/mirror_client.go),
[GC admission](https://github.com/kubernetes/kubernetes/blob/v1.36.1/plugin/pkg/admission/gc/gc_admission.go).
No live operations, collector changes, commits or pushes.

**Unresolved questions:** Static hashes will remain opaque equality bindings,
not authenticated disk-manifest hashes. Independent static configuration,
kube-proxy, platform images/status and lifecycle integration remain open.

**Next gate:** Test-first correction of hash grammar and producer-specific owner
schemas, update the two fixture producers, add raw-List regression, and rerun
platform/ownership suites with independent reviews. Completion flags stay false.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-226 — 2026-09-08 — Static-mirror ownership compatibility corrected

**Input:** Continue; resolve the independently reproduced producer mismatches.

**Interpretation:** Correct only static identifier grammar and owner shape,
preserving the stronger distinct DaemonSet contract and all non-runtime limits.

**Decision status:** Correction accepted after specification, independent
quality and root review. Root passed 171 adjacent tests using corrected fixtures;
specification passed 60 focused tests and quality passed a 50-test subset.
The broader V3B-2 suite is running and is not yet claimed green.

**Rationale:** Exact lowercase hex32 accepts the pinned FNV128a output shape;
static five-field Node owners now match the mirror producer. Extra owner flags
and malformed hashes still fail, including constructor forgeries. DaemonSet
six-field owners and strict true flags are unchanged. Both independent fixture
producers were corrected, and a full-List test confirms raw values survive
reconstruction. Equality does not establish trusted manifest content.

**Affected artifacts:** Node ownership module, its tests, platform endpoint
fixture and runtime ownership regression; corrective plan/reader and this
lineage. No live operations, runtime projection edits, commits or pushes.

**Unresolved questions:** Broader regression results; kube-proxy and static
configuration, independently authenticated disk inputs, actual runtime images/
status, fresh collectors and lifecycle composition. Existing runtime completion
flags remain false.

**Next gate:** Assess broader regression, then continue the source-prepared
platform contracts without treating fixture compatibility as live validation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-227 — 2026-09-08 — Kube-proxy parents accepted

**Input:** Continue source-backed platform verification while broader regression
runs independently.

**Interpretation:** Implement the bounded kube-proxy DaemonSet/ServiceAccount
configuration before its revision and generated Pod.

**Decision status:** Parent adapter accepted after specification, independent
quality and root reviews. Both reviewers passed eleven tests; root passed 182
combined platform/ownership/default/endpoint tests with corrected static fixtures.
The broader suite remains running; no repository-wide pass is asserted.

**Rationale:** Fresh verifier-owned literals preserve the pinned image, literal
NODE_NAME command expression, ordered environment/mounts/volumes, privilege,
host networking and rolling-update defaults. Exact ownership reconstruction
precedes same-source comparison. The no-inherited-proxy output qualification is
explicit because kubeadm can append proxy environment variables; effective
node environment and patch authority remain separate.

**Affected artifacts:** Kube-proxy parent module/tests, corrective plan/reader,
revision checklist and this lineage. No live operations, collector expansion,
commits or pushes. All completion flags remain false.

**Unresolved questions:** Kube-proxy revision and Pod contracts; independent
static disk configurations; platform runtime images/status and lifecycle gates.

**Next gate:** Independently derived kube-proxy ControllerRevision patch and
opaque label/Pod relationship, with reviews before generated-Pod configuration.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-228 — 2026-09-08 — Kube-proxy revision accepted; broad fixture gap isolated

**Input:** Continue sequential platform contracts and assess broader regression.

**Interpretation:** Verify the kube-proxy revision relationship independently;
investigate the prolonged broad test run without weakening production checks.

**Decision status:** Revision adapter accepted after specification, independent
quality and root reviews. Both reviewers passed eleven focused tests; root
passed 193 combined tests. Quality additionally rejected ten malformed patch
values. The broad suite was interrupted by root with exit 130 and did not yield
a final result; it is not a repository-wide pass or completed failure count.

**Rationale:** Independent expected template content, exact parent reconstruction,
closed revision metadata and opaque label/Pod joins prevent candidate patch data
from defining its own authority. Broad-run interruption exposed legacy controller
inventory rejected before static hashes: family counts 10/0/14/0/1 instead of
12/12/19/1/2, with drivers already included. Its 16-boundary recovery matrix was
reconstructing persisted context during fallback. Inspection establishes a stale
fixture gap, not an infinite loop or regression caused by the static correction.

**Affected artifacts:** Kube-proxy revision module/tests, corrective plan/reader,
Pod checklist and fixture-migration note; this lineage. Only the exact local
test process was interrupted. No live cluster or Colima operations, commits,
pushes or collector changes occurred.

**Unresolved questions:** Phase-aware controller fixture migration; kube-proxy
Pod, static mirror configurations and independent effective/disk inputs; actual
platform images/status and final lifecycle composition.

**Next gate:** Kube-proxy generated-Pod configuration and reviews. Keep broader
verification open until realistic phase-aware fixtures and remaining contracts
are integrated; retain strict false completion flags.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-229 — 2026-09-08 — Kube-proxy Pod accepted; scheduler mirror prepared

**Input:** Continue through the remaining platform configuration families.

**Interpretation:** Complete kube-proxy admission-output review, then use the
independently reviewed narrow API-output approach for static mirrors.

**Decision status:** Kube-proxy Pod accepted after specification, independent
quality and root reviews. Both reviewers passed ten tests; root passed 203
combined tests. Quality also rejected 35 malformed spec cases. Six of ten
platform Pod configurations are covered, not six complete runtime proofs.

**Rationale:** Exact revision reconstruction, independent source expectation,
owned-node affinity, ordered DaemonSet tolerations and correlated token volume/
mount are enforced. Static mirrors need distinct rules: service-account admission
bypasses mutation and forbids token references; file-source NoExecute tolerance
suppresses the normal 300-second additions; hostNetwork defaulting sets hostPort.
Source config.seen uses fixed nine-digit fractional RFC3339 time, separate from
API creationTimestamp validation. Scheduler producer inputs and no-override
qualifications were inspected before implementation planning.

**Affected artifacts:** Kube-proxy Pod module/tests, corrective plan/reader,
scheduler mirror checklist and this lineage. No live operations, commits,
pushes or collector changes.

**Unresolved questions:** Four static mirror configuration adapters, effective
node-local inputs/disk-manifest authenticity, platform runtime images/status,
phase-aware controller fixture migration and final lifecycle composition.

**Next gate:** Test-first scheduler mirror API-output proof and independent
reviews, explicitly excluding FNV/disk authentication and preserving false
completion flags. The broad test run remains interrupted, not passed.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-230 — 2026-09-08 — Scheduler mirror accepted; etcd address boundary prepared

**Input:** Continue the approved KIL testing implementation.

**Interpretation:** Finish the pending scheduler review gate and source-prepare
the next control-plane configuration slice without broadening runtime claims.

**Decision status:** Scheduler API-output adapter accepted after specification,
independent quality and root verification. Both reviewers passed nine focused
tests; quality rejected 29 additional malformed cases. Root passed 212 combined
tests in 31.178 seconds. Etcd remains planned, not implemented or accepted.

**Rationale:** Scheduler expectations are independent of candidate configuration;
exact ownership is reconstructed, complete metadata/spec and fixed-nine-digit
producer timestamps are checked, status remains uninterpreted and completion
flags remain false. Source citation corrected from nonexistent timestamp.go to
types/types.go and CRI logs/logs.go. Seven of ten platform Pod configuration
contracts are covered, not seven complete runtime proofs.

**Affected artifacts:** Scheduler module and nine-test suite in the implementation
worktree; corrective plan and generated reader; this append-only lineage. No
live Colima, Docker or Kubernetes operations, commits or pushes were performed.

**Unresolved questions:** Etcd's exact raw Node address-list contract; effective
kubeadm configuration and disk authenticity; conditional CA-volume authority
for controller-manager/apiserver; platform image/status composition and legacy
phase-aware controller fixture migration. The broad suite remains interrupted,
not passed. V3C remains closed.

**Next gate:** Test-first etcd mirror API-output comparison using the retained
owned Node address, followed by specification/quality reviews. Pinned Kind
source maps node.IP to advertiseAddress and kubelet node-ip; kubelet emits both
InternalIP and Hostname. This permits an explicitly limited relational proof,
not independent network/disk authentication. A consistently changed Node and
matching mirror may pass that relation; do not disguise this residual limit.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-231 — 2026-09-08 — Etcd mirror API-output configuration accepted

**Input:** Continue the V3B-2 platform validation work.

**Interpretation:** Implement and independently review the eighth platform Pod
configuration while keeping node-local disk and runtime authority outside the
narrow API-output claim.

**Decision status:** Etcd mirror configuration accepted after test-first
implementation, specification review, quality review and root verification.
Nine absent-adapter tests established RED; a reserved-address regression also
failed before its predicate was added. Both reviewers passed nine focused tests.
Quality rejected 18 additional malformed cases. Root passed 221 combined tests
in 34.776 seconds. Eight of ten platform Pod configurations are now covered.

**Rationale:** Exact runtime ownership is reconstructed before the retained raw
Node supplies a canonical IPv4 InternalIP. The complete etcd mirror metadata and
spec are compared with independent pinned-source expectations, including ordered
arguments, mounts, volumes and probes. A coordinated valid Node/mirror address
change intentionally passes: this is a same-source relational check, not proof
of effective kubeadm input, actual network ownership or disk-manifest content.
Arbitrary Pod status remains uninterpreted and completion flags remain false.

**Affected artifacts:** New etcd configuration module and nine-test suite in the
implementation worktree; updated plan and generated reader; this append-only
lineage. No Colima, Docker, Kubernetes, collector, commit or push operation was
performed.

**Unresolved questions:** Independent filesystem input for the conditional CA
mounts on kube-apiserver and kube-controller-manager; effective kubeadm/disk
authentication; all platform image/status/readiness composition; legacy
phase-aware controller fixture migration. The broad suite remains interrupted,
not passed. V3C remains closed.

**Next gate:** Source-close the smallest independently captured/reconstructed
filesystem authority needed by the two remaining static mirrors. Do not select
conditional volumes from candidate Pod mounts or count either configuration as
covered until that input and its composition are independently reviewed.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-232 — 2026-09-08 — Remaining static-manifest authority options audited

**Input:** Continue after accepting eight of ten platform Pod configurations.

**Interpretation:** Resolve the independent input needed for kube-apiserver and
kube-controller-manager filesystem-conditional CA mounts before implementing
either validator.

**Decision status:** Proposal pending user approval. Two independent read-only
audits agree that existing KIL evidence and Kind/Kubernetes producer source do
not establish the published node image's exact five-path presence vector.
Kubernetes source fixes the candidate paths and rendering algorithm; the Kind
source inherits mutable Debian/package inputs and does not materialize the
published artifact's exact filesystem. No validator was implemented.

**Rationale:** Three approaches remain sound. The recommended approach captures
the two bounded on-disk static manifests from the exact owned node, bracketed by
node identity, and proves their API mirrors agree with those files while fixed
source rules constrain all fields and conditional mounts to the five allowed
path/name pairs. This directly authenticates effective kubeadm output at modest
complexity. A pre-creation OCI index/manifest/layer audit is more independent
but must implement digest, platform, layer-order, whiteout, hardlink and symlink
semantics. Deferral is honest but leaves the platform configuration gate at
eight of ten. Candidate API mounts alone remain forbidden as expected authority.

**Affected artifacts:** Read-only audits of controller/evidence/journal/image
proofs and pinned Kind/Kubernetes/OCI sources; updated etcd plan/reader and the
T-231/T-232 lineage append. No new authority code, live Colima/Docker/Kubernetes
operation, commit or push occurred.

**Unresolved questions:** Whether the project requires pre-creation prediction
of the conditional directory vector or accepts node-identity-bracketed disk
manifest authentication after Kind creation. The answer selects the disk capture
or OCI-layer approach. Runtime/image/readiness composition and fixture migration
remain open; V3C remains closed.

**Next gate:** Obtain explicit design choice. If disk capture is approved, write
the narrow source/identity/bounds/replay design and implementation plan before
test-first work. If pre-creation prediction is required, design the OCI artifact
audit instead. Preserve the unique `kil-v3-lab` mutation scope in either case.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-233 — 2026-09-08 — Disk-manifest authority design documented

**Input:** Approve the recommended approach for the two remaining platform Pod
configuration gates.

**Interpretation:** Formalize node-identity-bracketed on-disk static-manifest
capture as the independent conditional-volume source, without beginning
implementation before written-spec review.

**Decision status:** Recommended approach confirmed and written specification
created. Commit `62c90f4` contains only the Markdown design and generated HTML
reader. The written-spec review gate remains pending; no implementation plan or
production code was started.

**Rationale:** Exact reads of the two literal manifest paths from the bound
owned-node container directly authenticate kubeadm's effective output. Fixed
source expectations constrain all nonconditional fields; the disk source may
select only an exact subset of five pinned CA path/name pairs. Before/after node
inspection, private bounded raw retention, journal commitment and offline replay
prevent an API mirror or later candidate from becoming its own authority. This
is materially smaller than full OCI layer reconstruction while preserving the
claim boundary.

**Affected artifacts:** New control-plane static-manifest source design and HTML
reader on the isolated implementation branch; this append-only lineage. No live
Colima, Docker or Kubernetes operation, implementation edit, push or merge.

**Unresolved questions:** User review of the exact written source, lifecycle,
replay and failure contracts; subsequent implementation plan; platform image,
status/readiness composition and phase-aware controller fixture migration.
V3C remains closed.

**Next gate:** User reviews the committed design. After approval, write the
test-first implementation plan, then execute source proof, API-server proof and
controller-manager proof sequentially with independent reviews. Keep all
completion flags false and all mutations restricted to `kil-v3-lab`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-234 — 2026-09-08 — Static-manifest gate related to incident claim

**Input:** Explain the purpose of the control-plane static-manifest source
relative to testing whether KIL could have thwarted the Hugging Face incident.

**Interpretation:** Distinguish direct enforcement evidence from infrastructure
and evidence-integrity prerequisites, and restate the historical claim boundary.

**Decision status:** Clarification confirmed; no design change. The manifest
gate is an instrumentation-integrity control, not an incident simulation or a
KIL enforcement mechanism. The committed design remains pending written-spec
review.

**Rationale:** V2 maps publicly reported incident facts into an explicitly
modeled counterfactual. V3 tests the same decision contract at real enforcement
boundaries. V3B-2 adds Kubernetes/Calico policy, identity and bypass-resistance.
Authenticating API-server and controller-manager manifests makes that live result
attributable to the reviewed lab rather than unknown control-plane drift or
self-referential API evidence. It therefore strengthens the evidence chain but
cannot by itself show denial, thwarting or historical prevention.

**Affected artifacts:** This append-only lineage clarification only. No design,
implementation, live environment, commit or remote state changed.

**Unresolved questions:** Written-spec approval and implementation of the two
remaining platform configuration gates; V3B-2a nominal proof; V3B-2b negative
and failure campaign; V3C repetition/performance. Private historical telemetry
is unavailable, so even a successful local campaign remains a bounded validated
counterfactual rather than proof of what would have happened historically.

**Next gate:** Review the manifest-source design, then implement it only if the
user wants the stronger publishable evidence chain. The eventual defensible
claim is that KIL reproduced denial under named modeled conditions in the local
cluster, not that it proved prevention of the historical incident.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-235 — 2026-09-09 — Accumulated implementation checkpoint paused

**Input:** Verify the accumulated changes, commit them in logical checkpoints,
integrate the three newer `main` commits, push the implementation branch, then
pause for a later session.

**Interpretation:** Preserve the verified implementation work in dependency-
aligned local commits, stop active verification on request, and leave merge and
push work explicitly unfinished rather than claiming completion.

**Decision status:** Paused by user request. Four new local checkpoints were
committed on `codex/v3b2-kind-calico-implementation`: runtime-admission
prerequisites (`1292e8b`), runtime proof graph (`3244fdb`), platform
configuration validators (`313a37f`), and the updated implementation plan
(`b34d703`). The earlier static-manifest design commit `62c90f4` remains. The
controller integration files are still uncommitted; the three newer `main`
commits are not yet merged and the branch has not been pushed.

**Rationale:** Fresh bounded verification passed 190 proof/evidence tests, 218
ownership/platform tests, and 133 application/runtime tests. The first 190-test
run failed only because the sandbox denied Bash `/dev/fd`; the same batch passed
with that local restriction removed. The focused controller batch remained
CPU-active in exhaustive lifecycle/recovery replay and was interrupted only
after the user requested a pause, so no result is claimed for it. A duplicate
full discovery run was also interrupted to avoid redundant load.

**Affected artifacts:** Five existing feature commits plus the four new local
checkpoints above; this append-only lineage entry. No Colima profile, Docker,
Kind, Kubernetes, or remote Git state was mutated. The main-checkout `Inputs/`
directory and dirty generated lineage reader remain untouched.

**Unresolved questions:** Completion of the controller integration test batch;
the controller checkpoint commit; integration of main commits `2cfce8e`,
`b98615e`, and `f238cd4`; transfer of the full T200–T235 lineage append into the
implementation branch; post-merge verification and remote push.

**Next gate:** Resume with the focused controller tests, commit the remaining
controller integration paths if green, merge local `main`, transfer and render
the chronological lineage append without staging `Inputs/`, rerun bounded
post-merge verification, review the final branch diff, and push only
`codex/v3b2-kind-calico-implementation`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
### T-236 — 2026-09-09 — Proved-runtime checkpoint integrated

**Input:** Finish and commit the paused accumulated work as quickly as possible,
including integration of the three newer `main` commits and publication of the
implementation branch.

**Interpretation:** Complete the bounded proved-runtime checkpoint honestly,
without weakening the deliberate platform-admission terminal gate, then
synchronize the implementation branch. Do not touch any Colima profile.

**Decision status:** Confirmed checkpoint. Commit `af5e7cf` binds the controller
to the finite accepted image contract, policy and pre-driver checkpoints,
proved runtime inventory, and public image provenance. Commit `0c4bac4` updates
the controller assertion to the six-record pre-driver terminal registry. The
three newer `main` commits (`2cfce8e`, `b98615e`, and `f238cd4`) were merged
cleanly, and the chronological T-200 through T-235 append was transferred.

**Rationale:** Fresh post-merge verification passed 133 affected proof,
runtime, endpoint, ownership, public-provenance, and observed-lifecycle tests,
plus two focused controller checkpoint tests. Compilation and whitespace
validation passed. The legacy nominal continuation correctly remains blocked
at `platform_admission_terminal_gate_pending`; treating that deliberate unknown
decision as success would overclaim the current implementation.

**Affected artifacts:** `src/kil/v3b2_controller.py`; its controller and
observed-lifecycle tests; parameterized runtime fixture helpers; new proved-
runtime glue and public-image-provenance tests; merged and appended specialist
lineage Markdown and generated HTML. No Colima, Docker, Kind, or Kubernetes
runtime was invoked, and the main-checkout `Inputs/` directory was untouched.

**Unresolved questions:** The platform configuration validators are present but
are not yet composed into the application terminal, so the full nominal
lifecycle and complete controller suite are intentionally not claimed green.

**Next gate:** Compose the reviewed platform-admission validators into one
terminal proof, rerun the complete controller and repository gates, then open
the live `kil-v3-lab` validation gate only after static acceptance.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-237 — 2026-09-09 — Exact pending platform gate proved

**Input:** Resolve the independent final-review finding before pushing the
implementation branch.

**Interpretation:** Make the controller fixture satisfy every earlier finite-
image, ownership, configuration, endpoint, and continuity validator, then
assert the exact remaining platform-admission pending category.

**Decision status:** Confirmed correction. Commit `db681e4` supplies the full
independently rendered application Deployment specifications in the retained
API fixture and requires
`operation_postcondition_unproved:platform_admission_terminal_gate_pending`.
Both focused controller tests pass and confirm no `application_apply_complete`
event is emitted.

**Rationale:** The reviewer correctly identified that generic fail-closed
coverage could conceal an earlier validator regression. The corrected fixture
now reaches the named terminal gate, preserving the honest incomplete claim
while proving the accumulated runtime chain beneath it.

**Affected artifacts:** `tests/test_v3b2_controller.py`, this append-only
lineage entry, and the generated lineage reader. No live runtime or Colima
profile was touched.

**Unresolved questions:** Composition of the already implemented platform
configuration validators remains the next development slice.

**Next gate:** Push the clean implementation branch, then resume with the
platform-admission terminal composition and full static gate.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-238 — 2026-09-10 — V3B-1 publication boundary approved

**Input:** Fast-forward KIL to publication, mark V3B-1 complete, rename and move
V3B-2 to the post-publication future as **V4 Future**, and preserve V3B-1 detail
as additional validation.

**Interpretation:** Publish from the accepted observed local-Envoy result while
keeping its claim boundary explicit. Preserve all V3B-2 implementation and
history, but remove that work from the current publication dependency chain.

**Decision status:** Confirmed design. The public sequence is V1, V2, V3A,
V3B-1 Complete, Publication, then V4 Future. The accepted V3B-1 run remains
visible with its exact outcome tuple, source, teardown, and verification facts.
The immutable bundle remains `not_promoted`; publication status does not rewrite
experiment evidence.

**Rationale:** V3B-1 already supplies accepted observed evidence at its declared
local Envoy boundary. Deferring cluster validation permits publication now
without claiming Kubernetes behavior, historical prevention, or performance.
Retaining the detailed evidence makes the narrower claim auditable rather than
turning completion into an unsupported label.

**Affected artifacts:** New publication-boundary design specification; carried-
forward T-200 through T-237 lineage history; regenerated lineage reader. No
runtime, evidence bundle, Colima profile, V3B-2 implementation branch, or
external publication target was mutated.

**Unresolved questions:** Implementation of the approved current-facing status,
paper, timeline, and tests; resolution of the screenshot's repository source;
final publication deployment mechanism after repository validation.

**Next gate:** User reviews the written specification. After approval, produce
the implementation plan and update the bounded publication surfaces without
merging V4 Future implementation code.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-239 — 2026-09-10 — V3B-1 publication implementation planned

**Input:** Approve the V3B-1 publication-boundary specification.

**Interpretation:** Convert the approved claim and milestone decision into a
minimal test-first plan covering current status, retained validation detail,
paper language, a durable roadmap visual, verification, review, and push.

**Decision status:** Confirmed plan. Four dependency-ordered tasks define the
publication contract test, canonical status changes, paper/presentation update,
and final reader/lineage/review delivery gate.

**Rationale:** The plan makes claim limitations executable documentation
requirements, preserves the immutable `not_promoted` experiment record, and
keeps V4 Future implementation code out of the publication branch. A new
repository-owned SVG replaces reliance on the supplied screenshot's absent
repository source.

**Affected artifacts:** New implementation plan and generated reader; this
append-only lineage entry and generated lineage reader. No production code,
evidence bundle, runtime, Colima profile, or remote branch was changed.

**Unresolved questions:** Selection of subagent-driven versus inline plan
execution; external publication deployment remains after repository acceptance.

**Next gate:** Execute the approved plan, require the exact V3B-1 boundary tests
to pass, independently review the publication claims, and push the isolated
publication branch.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-240 — 2026-09-10 — V3B-1 publication record finalized

**Input:** Fast-forward publication, mark V3B-1 complete, preserve validation
detail, and rename deferred V3B-2/V3C work as post-publication **V4 Future**.

**Interpretation:** V3B-1 is complete only at its accepted
`local_envoy_boundary`; publication now follows that bounded result. The
immutable evidence bundle remains `not_promoted`. This does not claim
Kubernetes validation, historical prevention, production behavior, or
performance.

**Decision status:** Confirmed. Accepted run
`v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94`
reproduced `permit / permit / deny`, HTTP `200 / 200 / 403`, and target markers
`1 / 1 / 0`, with one attempt per track and no retry. All nine authoritative
sources joined; exact teardown removed 15 owned containers and six networks;
checksums and the offline verifier passed. Current-facing README, V3 progress,
paper, architecture HTML, and durable repository-owned SVG now present the
bounded completion before Publication and **V4 Future**. The five focused
publication tests protect those statements. Responsive review found that the
long status run ID could overflow narrow layouts and that the roadmap claim
panel needed fixed readable wrapping; the architecture status code now wraps
anywhere and the SVG claim is split into durable two-line text, with the focused
layout test covering both corrections.

**Rationale:** The accepted observed local-Envoy result is sufficient for the
declared V3B-1 boundary, while retaining its exact validation facts and
non-promotion state makes publication auditable without extending the claim.
Moving deferred cluster and later work to **V4 Future** preserves its history
without making it a prerequisite for this publication.

**Affected artifacts:** README, V3 progress, paper, architecture HTML, SVG,
focused test, generated readers, and this lineage record. No evidence bytes,
production code, live runtime, Colima, Docker, Kind, Kubernetes, or V4 Future
implementation branch changed.

**Unresolved questions:** External publication deployment or release mechanism
after repository acceptance.

**Next gate:** Final independent review, push `codex/v3b1-publication`, then
external publication or release.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-241 — 2026-09-10 — Whole-branch publication consistency review resolved

**Input:** Final whole-branch review found that the current embedded
`v3-envoy-live-validation.svg` and adapter README still used pending/V3B-2
labels after the V3B-1 publication transition.

**Interpretation:** Resolve the remaining current-facing label drift without
altering the accepted evidence boundary or the depicted topology: V3B-1
Complete leads to Publication, followed by post-publication **V4 Future**.

**Decision status:** Confirmed. Commit `c222a3e` updates the embedded SVG and
adapter README to the V3B-1 Complete → Publication → post-publication **V4
Future** sequence, preserving topology and claim limitations. Spec and quality
re-review approved the resolution with no Critical or Important issues. Six
focused tests pass.

**Rationale:** The final reader surfaces must agree with the accepted
`local_envoy_boundary` completion and reserve Kind/Calico, NetworkPolicy,
cluster transport, and measurement for **V4 Future**. Retaining the topology
and limitations keeps the correction presentational rather than evidentiary.

**Affected artifacts:** Focused test, `v3-envoy-live-validation.svg`, adapter
README, generated adapter and lineage readers, and this append-only lineage
record. No evidence bytes, runtime, production code, Colima state, or V4 Future
implementation changed.

**Unresolved questions:** External publication deployment or release mechanism
after repository acceptance.

**Next gate:** Full publication verification, final whole-branch re-review,
push `codex/v3b1-publication`, then external release.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-242 — 2026-09-10 — V3B-1 publication integration authorized

**Input:** Create the publication pull request and merge the approved V3B-1
publication branch into `main`.

**Interpretation:** Integrate the already reviewed publication-only change set
through GitHub after a fresh local verification and required remote checks. Do
not merge the separate V4 Future implementation branch, alter immutable
evidence, or touch any local runtime or Colima profile.

**Decision status:** Confirmed authorization. Branch
`codex/v3b1-publication` is the sole integration source. Its publication claim
remains bounded to the accepted V3B-1 `local_envoy_boundary`; cluster validation,
repetition, and performance remain post-publication **V4 Future** work.

**Rationale:** A pull request provides a reviewable, check-gated path from the
approved and independently reviewed publication branch to `main`, while keeping
the deferred implementation history and the user's dirty local `main` checkout
isolated.

**Affected artifacts:** This append-only lineage record and its generated
reader; the publication pull request and `main` only after checks and merge. No
evidence bytes, runtime, Colima state, or V4 Future implementation is changed.

**Unresolved questions:** Required GitHub checks and mergeability must be
confirmed before integration completes; external publication deployment remains
a later release action.

**Next gate:** Regenerate readers, rerun the full publication verification,
push this checkpoint, create the pull request, wait for checks, and merge into
`main`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-243 — 2026-09-11 — Narrow V4 publication CI boundary confirmed

**Input:** Authorization to repair the narrow V4 CI/proof blocker before
merging publication pull request 23.

**Interpretation:** Exclude exactly the 16 unfinished V4 controller lifecycle
integration methods from default publication discovery while retaining every
completed controller and proof test. Keep the unfinished lifecycle suite
explicitly runnable through `make v4-future-controller-test`; do not claim that
opt-in suite passes.

**Decision status:** Confirmed. The exact deferred set is locked by an
independent guard test and cannot silently expand. The default gate retains the
remaining controller coverage, while setting `KIL_RUN_V4_FUTURE_TESTS=1`
executes the deferred cases and currently exposes their pending proof failures.

**Rationale:** Both failed GitHub validation runs traced all 34 failures and
subfailures to these 16 lifecycle methods. Completing them requires the larger
post-publication V4 proof graph; importing that work would violate the approved
publication-only boundary. An exact, opt-in quarantine makes the boundary
auditable without hiding or deleting the unfinished work.

**Affected artifacts:** `Makefile`, `tests/test_v3b2_controller.py`,
`tests/test_v4_future_controller_gate.py`, the V4 CI boundary specification and
plan, this append-only lineage record and generated readers, and publication
pull request 23. No accepted evidence bytes, runtime, Colima profile, or V4
production implementation changed.

**Unresolved questions:** The explicit V4 future target remains red at pending
proof stages and must be completed when post-publication V4 work resumes.

**Next gate:** Run full local validation, push the repaired publication branch,
require green GitHub checks, and merge pull request 23 into `main`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-244 — 2026-09-11 — External publication visibility gate selected

**Input:** Proceed to the next action after publication pull request 23 merged
into `main`.

**Interpretation:** Use public GitHub repository visibility as KIL's first
external publication surface. Do not invent a semantic release version or
enable an unconfigured Pages site in the same action. Preserve the accepted
V3B-1 claim boundary and the separate post-publication **V4 Future** branch.

**Decision status:** Confirmed authorization to advance to external
publication. A read-only readiness audit found that the repository is still
private, has no releases or Pages configuration, and has 25 remote branches,
including three tips not merged into `main`. A pattern scan found only the
deliberately synthetic credential strings used by rejection tests, not a
likely live credential. Publication will also disclose two commit-author email
identities, historical absolute-path provenance, and the incomplete V4 Future
branch.

**Rationale:** Changing repository visibility is the narrowest established
mechanism that makes the merged paper, generated readers, code, and accepted
evidence accessible without creating a new unreviewed deployment artifact or
assigning an unsupported version. Recording the complete-repository exposure
before the change keeps the action deliberate and auditable.

**Affected artifacts:** This append-only lineage record and generated reader;
GitHub repository visibility after the audit record is integrated. No source
behavior, evidence bytes, release tag, Pages configuration, runtime, Colima
profile, or V4 Future branch content changes.

**Unresolved questions:** A future release needs an explicitly selected tag and
version. A future hosted paper surface needs an approved Pages or other hosting
design. Historical branch and path provenance remain visible after public
conversion unless separately curated.

**Next gate:** Regenerate and verify readers, integrate this audit record, set
the GitHub repository to public, and verify unauthenticated access to `main`
and the bounded V3B-1 publication surfaces.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-245 — 2026-09-11 — Public visibility declined; repository remains private

**Input:** Keep the KIL GitHub repository private after reviewing the
repository-wide disclosure implications of public conversion.

**Interpretation:** Supersede T-244's proposed public-visibility next gate. The
merged V3B-1 publication boundary remains the authoritative repository state,
but it is not externally published through public repository visibility,
GitHub Pages, or a GitHub release.

**Decision status:** Confirmed. `gatekeeper454/KIL` remains private. No public
visibility change completed, and no workaround publication surface is
authorized.

**Rationale:** Public conversion would expose all remote branches and commit
history, including author identities, historical local-path provenance, and
the incomplete post-publication V4 Future branch. The explicit privacy
decision takes precedence over the earlier proposal to use repository
visibility as the first external surface.

**Affected artifacts:** This append-only lineage record and generated reader.
No GitHub visibility, release, Pages, source behavior, evidence bytes, runtime,
Colima profile, or V4 Future content changed.

**Unresolved questions:** Any later external publication requires a new,
explicitly scoped choice of audience and surface that preserves the private
repository boundary.

**Next gate:** Keep the repository private and await either a separately
approved publication mechanism or resumption of post-publication V4 Future
work.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-246 — 2026-09-14 — Turnkey Blue Zone strategy proposed

**Input:** Use the KTP website and RFC series, the Martherus and Tamed Autonomy
implementation repositories, KIL evidence, and current real-world autonomous-
system activity to develop a complete, evidence-validated plan for rapidly
deployable “Turnkey Blue Zones” and an evolution of Zero Trust.

**Interpretation:** Define a product and deployment procedure that operationalizes
KTP without inventing a competing trust system, connects KIL's reducing-only
infrastructure enforcement and evidence discipline to practical runtime
adapters, supplies multiple adoption options, and distinguishes demonstrated
facts from proposed product targets and historical counterfactuals.

**Decision status:** Strategy proposed for review; no product architecture or
implementation is approved. The recommendation is one architecture with three
promotion profiles: a developer Blue Zone Kit, a Kubernetes-native Blue Zone
Operator as the first product, and later Blue Zone Federation. “Turnkey Blue
Zone — a runtime autonomy control plane” is the recommended product framing;
“Frontier Zero Trust” is retained as the broader thesis rather than the primary
product category.

**Rationale:** KTP 2.1.0 supplies the published protocol and zone model; the Go
and Python libraries supply useful but deliberately incomplete kernels; and KIL
has accepted one bounded local Envoy consequence proof but not Kind/Calico,
production, performance, or historical-prevention evidence. Recent primary
reports from Hugging Face, OpenAI, and Anthropic demonstrate that autonomous
evaluation systems can escape intended boundaries and reach real infrastructure
at machine speed. NIST and OWASP sources independently support dynamic,
action-level, workload-bound authorization, least agency, default-deny egress,
independent enforcement, and tamper-resistant audit. Together they support an
evidence-gated zone factory, not a push-button claim of production security.

**Affected artifacts:** Added the proposed strategy
`docs/design-drafts/2026-09-14-turnkey-blue-zone-strategy.md` and its generated
HTML reader; appended this lineage entry. No KTP, KIL runtime, laboratory,
cluster, remote, or product implementation was changed. Pre-existing `Inputs/`
and earlier dirty lineage state were preserved.

**Unresolved questions:** Approval of the product/category framing; first pilot
selection; Basic versus Standard initial target; product repository boundary;
SPIFFE default versus bring-your-own identity; governance ownership; and review
with KTP maintainers of which proposed profile fields are implementation details
versus candidate protocol extensions. KIL's current checkout is not claimed
green, and its unfinished V3B-2 work must not be presented as accepted evidence.

**Next gate:** Review and approve or revise the six decisions in the strategy.
Only after that review, write a narrow Phase 0 product requirements and
architecture specification fixing the pilot, action scope, conformance target,
governance owners, and extension boundary; do not begin implementation before
that design gate passes.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-247 — 2026-09-14 — Self-contained HTML review contract confirmed

**Input:** Ensure that every file presented for review is a self-contained HTML
file that can be shared easily.

**Interpretation:** Treat Markdown as an authoring source only and make each
review-facing `.htm` artifact independently readable outside the repository,
with inline presentation behavior and no required local-file dependencies.

**Decision status:** Confirmed publication requirement. The Turnkey Blue Zone
strategy now contains a review distribution contract requiring standalone HTML,
internal anchors or canonical HTTPS citations, complete in-file context,
script-disabled readability, print support, and an automated portability check.

**Rationale:** A sibling HTML reader is not truly portable if its conclusions or
evidence depend on repository-relative files, external stylesheets, local
images, or a rendering toolchain. Embedding the review content while retaining
canonical public citations makes the artifact useful to technical, executive,
and external reviewers without weakening provenance.

**Affected artifacts:** Updated
`docs/design-drafts/2026-09-14-turnkey-blue-zone-strategy.md`, regenerated its
standalone HTML reader, and regenerated the lineage HTML reader after this
append. The two KIL evidence references in the strategy now use canonical public
GitHub URLs rather than repository-relative links. No runtime, laboratory,
cluster, remote, or implementation state changed.

**Unresolved questions:** Future review artifacts will need the same portability
gate; embedded raster or vector diagrams, if introduced, will need data-URI or
inline-SVG handling and explicit size limits.

**Next gate:** Review the standalone Turnkey Blue Zone HTML reader. Apply the
same contract to the Phase 0 requirements and architecture reader after the
strategy decisions are approved.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-248 — 2026-09-14 — Frontier Zero Trust thesis created

**Input:** Develop a complete thesis that modern Zero Trust must evolve from
authenticated access to continuously earned, action-specific authority for
human safety against autonomous misalignment, using the potential to thwart the
Hugging Face incident as the central proof case.

**Interpretation:** Produce a rigorous, self-contained doctrine that connects
present Zero Trust standards, KTP, KIL, Blue Zones, current alignment evidence,
frontier-safety frameworks, and real autonomous-system incidents. Make the
Hugging Face campaign central without treating a plausible or demonstrated
mechanism as proof of an unobserved historical counterfactual.

**Decision status:** Thesis proposed for review; no normative protocol,
architecture, implementation, or publication decision is approved. The thesis
defines Frontier Zero Trust as the evolution from identity-to-resource access
to fresh agent-action-environment authority, with independent consequence
enforcement, trajectory, reducing-only local evidence, non-event proof, safe
degradation, and human constitutional governance.

**Rationale:** The 2026 International AI Safety Report separates severe
loss-of-control risk into capability, harmful propensity, and an enabling
deployment environment. Frontier Zero Trust directly constrains the third
factor while alignment and evaluations address the first two. The Hugging Face
incident demonstrates adaptive, machine-speed movement through failed sandboxes,
reachability, credentials, Kubernetes, cloud, network, and supply-chain paths,
while its successful denials show that independently enforced consequences
still matter after compromise. KIL V3B-1 independently demonstrates the narrow
signed-state permit/withhold mechanism at one local Envoy boundary. Together
these facts support named counterfactual severance hypotheses and a matched
replay agenda, not an unconditional historical-prevention claim.

**Affected artifacts:** Added
`docs/design-drafts/2026-09-14-frontier-zero-trust-thesis.md` and its standalone
HTML reader; appended this lineage entry and regenerated the standalone lineage
reader. No KIL runtime, laboratory, cluster, remote, protocol, or implementation
state changed.

**Unresolved questions:** Editorial and stakeholder approval; desired balance
between technical doctrine, public manifesto, policy argument, and academic
paper; whether the thesis should become a KIL white paper or remain a separate
position paper; external peer review; and completion of the KIL V3B-2, V3C, and
scenario-matched Hugging Face validation gates.

**Next gate:** Review the standalone Frontier Zero Trust HTML thesis. Revise its
claims and voice from stakeholder feedback before considering publication or a
separate implementation specification. Preserve the distinction between proof
of need, proof of mechanism, validated counterfactual, and historical causal
proof.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-249 — 2026-09-14 — Frontier Zero Trust pacing thesis proposed

**Input:** Create a version of the Frontier Zero Trust thesis that specifically
addresses the current safety and capability-pacing debate initiated by Dario
Amodei and the subsequent public agreement or endorsement by other frontier AI
leaders, using current internet research and retaining the Hugging Face incident
as the central proof case.

**Interpretation:** Distinguish a fast-moving public convergence from a binding
or operational agreement; assess both the genuine technical signal and the hype
cycle around it; and convert the governance opening into an evidence-backed
proposal joining independent embedded evaluation to independent runtime
consequence enforcement through Frontier Zero Trust, KTP, KIL, and deployable
Blue Zones.

**Decision status:** A new thesis variant is proposed for review. It recommends
that the pace-the-frontier moment be institutionalized as a Frontier Safety
Compact with seven commitments: protected embedded evaluators, embedded
enforcement, linked capability/deployment/evidence gates, comparable public
claim labels, incident replay, open conformance with anti-capture provisions,
and measurable pacing rules. No compact, protocol change, policy position,
implementation, or publication decision is approved.

**Rationale:** Amodei published a detailed three-stage proposal and a unilateral
Anthropic commitment to embedded evaluators. OpenAI publicly committed to match
that evaluator step, while Elon Musk and Demis Hassabis endorsed the direction
without equivalent published operational detail. The available record therefore
supports “public convergence,” not a settled pact. The OpenAI and Hugging Face
primary reports establish real autonomous boundary crossing and adaptive
infrastructure compromise, while successful denials in that same incident show
that independent consequence controls remain useful after containment and
identity fail. This supports action-level deployment controls without treating
Amodei's six-to-twelve-month catastrophic scenario as established fact.

**Affected artifacts:** Added
`docs/design-drafts/2026-09-14-frontier-zero-trust-pacing-thesis.md` and its
standalone HTML reader; appended this lineage entry and regenerated the
standalone lineage reader. No KTP or KIL runtime, laboratory, cluster, remote,
protocol, policy, or implementation state changed. Pre-existing `Inputs/` and
unrelated worktree changes were preserved.

**Unresolved questions:** Whether the thesis should replace or accompany the
broader Frontier Zero Trust paper; stakeholder and external peer review; the
scope and legal form of a Frontier Safety Compact; evaluator funding and
independence; anti-capture governance; which organizations will make matched
operational commitments; and completion of a scenario-matched Hugging Face
Blue Zone replay.

**Next gate:** Review the standalone pacing thesis for factual, strategic, and
editorial approval. Revalidate all time-sensitive public commitments before
publication. If the framing is accepted, convert the compact into a scoped
implementation and assurance specification with named owners, test vectors,
and evidence gates; do not advance historical-prevention claims beyond the
current validated-counterfactual level until matched replay succeeds.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-250 — 2026-09-14 — Deep Blue journey and v3 federation correction scoped

**Input:** Revise the Turnkey Blue Zone strategy so readers understand Blue
Zones as a maturity spectrum and a journey toward Deep Blue, and recognize that
federation belongs on the KTP v3 critical path but is not yet written.

**Interpretation:** Add an explicit adoption ladder using the canonical current
zone gradient—Wild, Green, Cyan, Blue, and Deep Blue—while deciding how to use
“Light Blue” as accessible journey language without presenting it as a current
normative RFC label. Separate zone assurance from rollout state and conformance
level. Treat federation as a reserved future KTP v3 dependency, not a capability
available from the present published baseline or something to implement before
the normative v3 text exists.

**Decision status:** Revision design proposed; editing is awaiting the required
design confirmation. The recommended approach is a compact “Journey to Deep
Blue” section and ladder, plus minimal corrections to existing federation claims
and a Phase 5 critical-path gate. No implementation or protocol decision is
approved.

**Rationale:** The current KTP Zones text explicitly defines a gradient from
Deep Blue to Wild and describes gradual adoption, but its canonical labels are
Deep Blue, Blue, Cyan, Green, and Wild rather than Light Blue. The current
Turnkey strategy mentions the gradient without making it the reader's adoption
journey, and it also describes federation as though it were part of the current
published product baseline. The proposed revision would clarify both concepts
without collapsing environment assurance, operational rollout, conformance,
and product-delivery profiles into one ladder.

**Affected artifacts:** This append-only lineage entry only. The Turnkey Blue
Zone strategy and its standalone HTML reader remain unchanged pending design
confirmation. No KTP or KIL runtime, laboratory, cluster, remote, protocol, or
implementation state changed; pre-existing `Inputs/` and unrelated worktree
changes were preserved.

**Unresolved questions:** Whether to include a small visual ladder in the
standalone reader; whether “Light Blue” should be an explicitly non-normative
umbrella for the Green/Cyan on-ramp or omitted in favor of exact RFC labels; and
the eventual scope, release, and conformance semantics of KTP v3 federation.

**Next gate:** Confirm whether a visual companion is desired, then approve the
recommended ladder and terminology. After approval, revise only the strategy's
foundation, delivery-option, deployment-gate, roadmap, and decision-summary
language; regenerate and verify the standalone HTML reader and record the
completed revision in a new lineage entry.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-251 — 2026-09-14 — Context-shaped Blue Zone journey adopted in strategy

**Input:** After reviewing three visual treatments, select option C: present
zone assurance depth and operational rollout as two independent axes. Emphasize
that each RFC color has a purpose, that Deep Blue is designed for contexts such
as nuclear and medical critical systems, and that organizations should not be
driven toward more assurance than their consequence model requires. Keep
federation on the critical path for the unwritten KTP v3 specification.

**Interpretation:** Use the exact current RFC gradient—Wild, Green, Cyan, Blue,
and Deep Blue—as a context-selected assurance target, while treating “Light
Blue” only as non-normative conversational shorthand for the Green/Cyan on-ramp.
Show inventory, observe, shadow, canary, enforce, and attest as a separate
operational journey that can be followed at any selected assurance depth. Do
not equate a color, rollout state, evidence level, or KTP conformance claim.

**Decision status:** The two-axis option is adopted in the proposed strategy and
is ready for stakeholder review. The document now recommends Kit and Operator
as the present single-zone product path, Deep Blue readiness as a context-driven
single-zone assurance track, and Federation as a future KTP v3 track behind a
published, pinned, and reviewed normative specification. No product build,
protocol change, conformance claim, or publication decision is approved.

**Rationale:** The canonical Zones RFC assigns distinct purposes to the five
colors and expressly reserves Deep Blue for maximum-assurance critical contexts.
The migration RFC independently describes staged activation. A two-axis model
prevents teams from mistaking rollout progress for assurance depth or treating
Deep Blue as a universal maturity destination. Current v2.1 texts contain
federation-related concepts and conformance references, but the governing design
direction places normative federation in not-yet-written KTP v3; therefore the
strategy withholds Standard or Full claims where unresolved federation is a
profile dependency.

**Affected artifacts:** Revised
`docs/design-drafts/2026-09-14-turnkey-blue-zone-strategy.md`; regenerated its
self-contained HTML reader with an embedded two-axis PNG diagram; appended this
lineage entry and regenerated the standalone lineage reader. No KTP or KIL
runtime, laboratory, cluster, remote, protocol, or implementation state changed.
Pre-existing `Inputs/` and unrelated worktree changes were preserved.

**Unresolved questions:** Stakeholder approval of the exact journey vocabulary;
whether a future KTP release will revise the current Standard and Full
conformance labels; the normative content, timing, and compatibility rules of
KTP v3 Federation; and which first pilot contexts should target Cyan, Blue, or
Deep Blue.

**Next gate:** Review the standalone Turnkey Blue Zone HTML reader. If the
two-axis model and claim boundaries are accepted, carry them into the Phase 0
product contract, profile schema, claims registry, and protocol compatibility
matrix. Do not schedule or implement Federation before the KTP v3 entry gate is
satisfied.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-252 — 2026-09-14 — Wide review-reader layout implemented

**Input:** Make the Turnkey Blue Zone strategy page wider because its dense
tables and preformatted material were difficult to read within the existing
right margin. After diagnosis, approve a reusable but document-scoped wide
reader mode: apply it only to the strategy, target an approximately 68-rem
content column, collapse the desktop outline earlier, and make no strategy
content changes.

**Interpretation:** Treat this as a presentation defect in the generated,
self-contained HTML reader rather than a KTP content or protocol revision. Add
an exact leading Markdown directive that selects the wide layout during
generation, remove the directive before article rendering, and preserve the
original source bytes for the reader's SHA-256 identity. Keep ordinary readers
byte-identical unless they explicitly opt in.

**Decision status:** The reusable `reader-layout: wide` mode is implemented and
applied only to the Turnkey Blue Zone strategy. This is a confirmed reader-layout
decision. It does not change the strategy thesis, the Blue Zone journey, KTP
semantics, product scope, conformance claims, or federation status.

**Rationale:** At the original desktop layout, the article column measured 606
pixels while existing preformatted and tabular blocks required as much as 764
pixels. The approved layout expands the article to 809 pixels at a 1280-pixel
viewport and 833 pixels at a 1000-pixel viewport. At both widths, every table and
preformatted block fits its container without horizontal overflow; at 1000
pixels, the desktop outline collapses into the mobile outline so navigation does
not compete with the article. Conditional CSS injection prevents the new mode
from altering readers that do not opt in.

**Affected artifacts:** Updated `tools/render_markdown.py` and
`tests/test_markdown_html.py`; added the wide-reader directive to
`docs/design-drafts/2026-09-14-turnkey-blue-zone-strategy.md`; regenerated its
self-contained HTML reader; recorded and rendered the implementation plan at
`docs/superpowers/plans/2026-09-14-wide-review-reader-layout.md`; and regenerated
this lineage reader. No KTP or KIL runtime, laboratory, cluster,
remote, protocol, or implementation state changed. Pre-existing `Inputs/` and
unrelated worktree changes were preserved.

**Unresolved questions:** Stakeholder visual acceptance on additional physical
devices; whether any other long-form review document should explicitly opt into
the wide layout; and whether the currently untracked design-draft source and
reader pairs should be added to the repository's publication inventory.

**Next gate:** Review the widened standalone Turnkey Blue Zone strategy reader.
If accepted, retain the layout as the document's presentation profile and apply
the directive to other readers only by explicit editorial decision. Separately
decide whether to track the current design-draft source and reader pairs so the
repository publication-contract check no longer reports them as unexpected.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-253 — 2026-09-14 — Dario Amodei Kinetic Zero Trust briefing package designed

**Input:** Create all three consumable formats—a one-page executive brief, a
direct two-page memo, and a technical proposal—for private delivery to Dario
Amodei in response to *We Must Pace the Frontier*. Affirm that all elements of
his pacing plan are relevant while explaining that Kinetic Trust and Ambient
Enforcement allow defenders to act without waiting for a government agreement
with China. Present protection as bidirectional: constrain misaligned AI
originating inside democratic Blue Zones and prevent external or cheating
adversarial AI from exercising authority inside them.

**Interpretation:** Position Kinetic Zero Trust as embedded enforcement that
complements Amodei's embedded evaluators. Distinguish capability pacing from
action authority and organize the argument around three outcomes: global
agreement, no agreement, and adversarial defection. Define government
independence as unilateral deployability rather than government irrelevance;
define immutability and ubiquity as evidence-tested Blue Zone invariants rather
than universal facts; and keep immediate single-zone protection independent of
the unwritten KTP v3 Federation work.

**Decision status:** The integrated three-document package and its shared claim
architecture are approved. A written design specification now defines audience,
terminology, message sequence, evidence tiers, claim boundaries, deliverable
lengths, a private-briefing request, and acceptance criteria. The three outreach
documents have not yet been drafted, and no pilot, external contact, protocol
change, or publication decision is approved.

**Rationale:** Amodei's essay explicitly makes embedded independent evaluation
the verification foundation of pacing and acknowledges that global agreements
face severe compliance and defection problems. Anthropic's incident report
identifies containment, monitoring, evaluation-environment hardening, and
defense in depth as necessary. METR's independent investigation documents
large-scale agent coordination and attempts to manipulate tool-call or
trajectory evidence. These sources support a bounded proposal for independent
consequence enforcement; they do not prove universal prevention.

**Affected artifacts:** Added
`docs/superpowers/specs/2026-09-14-kinetic-zero-trust-dario-briefing-design.md`
and its self-contained HTML review reader; appended this lineage entry and
regenerated the lineage reader. No KTP or KIL runtime, laboratory, cluster,
remote, protocol, enforcement, pilot, or external communication state changed.
Pre-existing `Inputs/` and unrelated worktree changes were preserved.

**Unresolved questions:** Editorial approval of the written package design;
the named recipients who should join Amodei in a private briefing; whether the
eventual technical appendix should expose detailed KIL experiment status or
remain implementation-neutral; and whether an independent evaluator would
accept the proposed pilot scope and evidence interface.

**Next gate:** Review the standalone design specification. After editorial
approval, create a detailed writing and validation plan for the three
self-contained outreach documents. Do not draft or send the package before the
design gate is accepted, and do not advance prevention or geopolitical-defense
claims beyond declared, non-bypassable Blue Zone coverage.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-254 — 2026-09-14 — Kinetic Enforcement adopted as the ultimate fail-safe frame

**Input:** Clarify that Kinetic Enforcement is the ultimate fail-safe and that
Ambient Enforcement, Kinetic Zero Trust, Kinetic Trust, KTP, and Blue Zones are
not separate ideas competing for attention; they are names for layers or
properties of the same substrate.

**Interpretation:** Use Kinetic Enforcement as the operational centerpiece of
the Amodei package. Define Kinetic Trust as the substrate principle, KTP as the
draft protocol framework, Kinetic Zero Trust as the security doctrine, Kinetic
Enforcement as the final independent control before consequence, Ambient
Enforcement as its omnipresent deployment property within declared coverage,
and a Blue Zone as the resulting protected environment.

**Decision status:** The naming hierarchy and “ultimate fail-safe” framing are
adopted in the briefing-package design. The phrase denotes an architectural
role—the last independent boundary after alignment, evaluation, pacing, or
identity assumptions fail—not an assertion that an implementation is
infallible. The outreach documents remain undrafted pending design review.

**Rationale:** A single substrate with a clear naming hierarchy is easier to
understand than several apparently competing brands. The fail-safe formulation
also makes the relationship to Amodei's plan concrete: alignment seeks correct
model choices, evaluation discovers failure, pacing creates time, and Kinetic
Enforcement withholds or attenuates protected consequences when those upstream
measures are wrong or incomplete. Claim discipline requires coverage,
non-bypassability, evidence independence, fail-constrained behavior, and
recovery to be demonstrated rather than assumed.

**Affected artifacts:** Revised
`docs/superpowers/specs/2026-09-14-kinetic-zero-trust-dario-briefing-design.md`;
this lineage entry and the corresponding self-contained review readers. No KTP
or KIL runtime, laboratory, cluster, remote, protocol, enforcement, pilot, or
external communication state changed. Pre-existing `Inputs/` and unrelated
worktree changes were preserved.

**Unresolved questions:** Editorial acceptance of the naming hierarchy and
qualified “ultimate fail-safe” language; whether the public-facing primary
name should eventually be Kinetic Enforcement or Kinetic Zero Trust; and which
implementation evidence should appear in the technical proposal.

**Next gate:** Review the revised standalone design specification. After
approval, write a detailed package-production plan and then draft the three
self-contained outreach documents with identical terminology and claim
boundaries.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-255 — 2026-09-14 — Sendable email added to the private-briefing package

**Input:** Ensure that one package item is an email that can be sent directly
to Dario Amodei.

**Interpretation:** Preserve the already approved executive brief, direct memo,
and technical proposal, and add a concise email as the package's delivery
surface. The email should work without an attachment while optionally pointing
to the brief and proposal. It should request a private technical briefing only,
without seeking public endorsement or implying that a pilot has been agreed.

**Decision status:** The package expands from three to four self-contained
deliverables. The email is specified at 300–450 words with a subject line,
greeting, send-ready body, closing placeholder that does not invent the sender's
identity, no more than two inline links, and an optional attachment note. The
four documents remain undrafted pending the production plan.

**Rationale:** A technically complete package still needs a low-friction entry
point. A short email respects the recipient's attention, states the distinctive
embedded-enforcement proposition, and creates a route to the requested private
briefing without forcing the longer materials into the initial message.

**Affected artifacts:** Revised
`docs/superpowers/specs/2026-09-14-kinetic-zero-trust-dario-briefing-design.md`;
this lineage entry and the corresponding self-contained review readers. No KTP
or KIL runtime, laboratory, cluster, remote, protocol, enforcement, pilot,
email, or other external communication state changed. Pre-existing `Inputs/`
and unrelated worktree changes were preserved.

**Unresolved questions:** The sender's preferred name, title, organization, and
contact details; whether the final email will include attachments or links; and
the best private contact channel for delivery.

**Next gate:** Produce and validate the four documents. Leave sender-specific
fields clearly marked for replacement, and do not send or externally publish
the email or attachments without explicit authorization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-256 — 2026-09-14 — Kinetic Enforcement private-briefing package completed

**Input:** Build the approved package and ensure that it includes an email that
can be sent directly to Dario Amodei. Make Kinetic Enforcement the ultimate
fail-safe, present Ambient Enforcement and Kinetic Zero Trust as the same
substrate, affirm the relevance of Amodei's complete pacing plan, and explain
the unilateral and bidirectional defense available if there is no agreement
with China or if an adversary cheats.

**Interpretation:** Produce four independent outreach surfaces: a sendable
email, a one-page executive brief, a direct private memo, and a technical
proposal. Use the same terminology, agreement/no-agreement/defection argument,
private-briefing request, evidence ladder, and claim boundaries in every file.
Treat “ultimate fail-safe” as the final independently governed consequence
boundary and require non-bypassable coverage rather than claiming
infallibility.

**Decision status:** The four documents are complete as private-review drafts.
Their main narrative lengths are 401, 762, 1,513, and 4,390 words respectively.
The email contains a subject, direct greeting, sender placeholders, two inline
links, and an optional attachment note. The technical proposal defines the
threat model, decision semantics, bidirectional architecture, independent
evaluator interface, incident control map, 90-day pilot, metrics, falsification
conditions, residual risks, and briefing agenda. Nothing has been emailed,
published, endorsed, piloted, or committed to a third party.

**Rationale:** Amodei's three-level pacing program addresses capability speed
and coordination; the package supplies a complementary consequence-control
layer that can be deployed without a prior synchronized government decision.
Primary-source grounding includes Amodei's essay, Anthropic's evaluation
incident analysis, METR's independent OpenAI–Hugging Face investigation, NIST
SP 800-207, the KTP site, and the canonical RFC repository. The China argument
is stated precisely: undisclosed capability can increase attack pressure, but
it is not an authorization credential inside a covered Blue Zone.

**Verification:** Static checks confirmed all four narrative word bands,
terminology, China/defection framing, briefing request, and email-link limit.
Each `.htm` has one H1, a source SHA-256 matching its Markdown bytes, inline
reader and print assets, HTTPS or internal links only, and no remote runtime
asset. The technical proposal alone selects wide-reader mode. Browser checks
measured an 809-pixel article at a 1280-pixel viewport and an 833-pixel article
at a 1000-pixel viewport, with no document or block overflow and the desktop
outline correctly collapsed at the smaller width. Forty-eight renderer,
generation, and tracked-publication tests passed. The full 49-test run retained
one expected publication-inventory failure reporting eight untracked review
readers: the three earlier design drafts, this package's design specification,
and the four new outreach readers.

**Affected artifacts:** Added the Markdown and generated HTML pairs
`docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-email.*`,
`docs/design-drafts/2026-09-14-kinetic-enforcement-executive-brief.*`,
`docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-private-memo.*`,
and `docs/design-drafts/2026-09-14-kinetic-enforcement-technical-proposal.*`;
added the internal production plan
`docs/superpowers/plans/2026-09-14-dario-kinetic-enforcement-package.md`;
revised and regenerated the package design specification; and appended this
lineage entry. No KTP or KIL runtime, laboratory, cluster, remote, protocol,
enforcement, pilot, email, publication, or other external state changed.
Pre-existing `Inputs/` and unrelated worktree changes were preserved.

**Unresolved questions:** Final editorial approval; replacement of the email
sender placeholders; the delivery address or introduction channel; whether to
attach all three longer documents or begin with the executive brief; which
Anthropic and independent-evaluator participants should attend; and whether a
private briefing would justify scoping the proposed pilot.

**Next gate:** Review the four standalone HTML documents. Personalize the email
only after the language is approved. If Dario accepts the private briefing,
use the technical proposal as a discussion instrument and decide whether to
scope—not presume—the independently governed 90-day pilot. Do not send or
publish any material without explicit authorization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-257 — 2026-09-14 — Concise Dario email revision scoped

**Input:** Make the sendable email more concise and avoid repeating material
Dario Amodei already stated in *We Must Pace the Frontier*.

**Interpretation:** Treat Amodei's pacing argument as shared context rather than
summarizing it back to him. Preserve only the novel contribution: embedded
evaluation needs an independently governed consequence-control layer; that
layer reduces dependence on universal agreement; Ambient Enforcement protects
covered Blue Zones in both directions; and the immediate request is a private
technical briefing.

**Decision status:** Revision direction is proposed, not yet implemented. Three
candidate densities were identified: an approximately 170-word recommended
version, an approximately 100-word warm-introduction version, and an
approximately 240-word concise-technical version. The current recommendation is
the 170-word version because it can state the distinctive control thesis and
the briefing request without reproducing the attached materials.

**Rationale:** The recipient already knows the pacing thesis. Repeating its
components consumes attention and makes Kinetic Enforcement appear derivative.
The email should create curiosity and establish the one missing control
category, leaving mechanism, evidence, geopolitical cases, and pilot detail to
the attachments and briefing.

**Affected artifacts:** This lineage entry only. The email Markdown and HTML
remain unchanged pending editorial approval. No email, publication, KTP or KIL
runtime, laboratory, cluster, protocol, enforcement, pilot, or other external
state changed.

**Unresolved questions:** Which target density the user prefers; whether the
China/defection case should remain explicit in the email or be left to the
brief; and which attachments will accompany the first contact.

**Next gate:** Obtain approval of the target density, revise the email source,
regenerate its self-contained HTML reader, and verify source binding, link
count, and rendering before review. Do not send the email without explicit
authorization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-258 — 2026-09-14 — Concise Dario email implemented

**Input:** Proceed with the recommended approximately 170-word email revision.

**Interpretation:** Address Amodei as a peer who already understands his own
pacing argument. Lead directly with the missing control category, define its
relationship to embedded evaluation, compress unilateral and bidirectional
Blue Zone protection into one paragraph, and use the remaining attention for a
specific private-briefing request.

**Decision status:** Confirmed editorial revision. The sendable body is now 187
words including greeting and closing, down from 401 main-narrative words. It
contains one inline HTTPS link and retains the subject, greeting, sender
placeholders, optional attachment note, private 45-minute request, scrutiny-not-
endorsement boundary, and the continuously earned, action-specific authority
thesis. The recap of Amodei's program and the three-scenario geopolitical list
were removed. No email has been sent.

**Rationale:** The shorter version respects the recipient's existing knowledge
and makes the contribution legible in one pass: independent evaluators assess
safety claims, while Kinetic Enforcement decides whether a specific action may
become a consequence. The Blue Zone sentence preserves the strategic advantage
without forcing the first-contact email to carry the full China/defection case.

**Verification:** Static checks measured 187 words from greeting through
closing, one HTTPS link, all required email fields, and no removed recap
phrases. The regenerated HTML embeds the exact Markdown SHA-256, contains one
H1, selects the standard reader rather than wide mode, and contains no remote
runtime asset. Forty-eight focused renderer, generation, and publication-
contract tests passed; `git diff --check` returned no error.

**Affected artifacts:** Revised and regenerated
`docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-email.*` and
`docs/superpowers/specs/2026-09-14-kinetic-zero-trust-dario-briefing-design.*`;
added the internal execution plan
`docs/superpowers/plans/2026-09-14-concise-dario-email.md`; and appended this
lineage entry with its generated reader. No email, publication, KTP or KIL
runtime, laboratory, cluster, protocol, enforcement, briefing, pilot, or other
external state changed.

**Unresolved questions:** Replacement of sender placeholders, the final
delivery channel, and whether the first contact should attach the one-page
executive brief or merely offer it.

**Next gate:** Review the concise standalone email reader. After editorial and
sender-field approval, decide the attachment strategy. Do not send or publish
without explicit authorization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-259 — 2026-09-14 — Existing-infrastructure and mathematical-enforcement claim scoped

**Input:** State in the Dario email that Kinetic Enforcement operates “on your
existing infrastructure”; it is not a product or a policy but physics, math,
and an immutable enforcement mechanism that needs to be enabled.

**Interpretation:** Preserve the requested force while defining its technical
meaning. “Physics” should describe operational inevitability at a non-bypassable
consequence boundary; “math” should identify the authority equation as the
decision rule; and “immutable” should mean that, within declared coverage, the
requesting AI cannot rewrite or overrule the decision. The language must not
imply that uncovered paths, administrators, implementations, or the surrounding
world are universally immutable.

**Decision status:** Three editorial approaches are proposed, not yet
implemented: a technically forceful paragraph defining each term, a maximum-
rhetoric sequence of slogans, and a conservative protocol-pattern description.
The recommended approach is the technically forceful paragraph because it
retains “existing infrastructure,” “not a product,” “not a policy,” “physics,”
“math,” “immutable,” and “enabled” while bounding the claim.

**Rationale:** The direct slogan is memorable but can sound metaphysical or
commercially evasive unless the enforcement invariant is stated. The bounded
version turns the rhetoric into a falsifiable proposition: on every declared,
non-bypassable consequence path, the required authority equation is satisfied
or the consequence does not propagate, and the requesting system cannot alter
that decision.

**Affected artifacts:** This lineage entry only. The concise email Markdown and
HTML remain unchanged pending wording approval. No email, publication, KTP or
KIL runtime, laboratory, cluster, protocol, enforcement, briefing, pilot, or
other external state changed.

**Unresolved questions:** Whether the recommended technically bounded language
is approved verbatim; whether the authority equation should be named in a
first-contact email; and whether “enabled” could be read as claiming a completed
Anthropic deployment rather than a deployable mechanism.

**Next gate:** Obtain wording approval, update the concise email and its design
contract, regenerate the self-contained reader, and verify length, claim
boundaries, source identity, and rendering. Do not send or publish without
explicit authorization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-260 — 2026-09-14 — Infrastructure-level enforcement invariant added to Dario email

**Input:** Approve adding the recommended existing-infrastructure, physics,
math, immutable-enforcement, and enablement paragraph to the sendable email.

**Interpretation:** Replace the earlier generic mechanism description rather
than append a second explanation. Keep the email near one minute and make the
enforcement invariant its center: a declared consequence either satisfies the
authority equation at a non-bypassable boundary or it does not occur.

**Decision status:** Confirmed and implemented editorial revision. The email
now states that Kinetic Enforcement, as the operational layer of Kinetic Zero
Trust, runs on the recipient's existing infrastructure; is not a product to buy
or a policy to interpret; is math expressed as infrastructure and operationally
behaves like physics; is immutable to the requesting AI within declared
coverage; and needs to be enabled. The body is 201 words from greeting through
closing. “Enabled” remains a deployment proposition, not a claim that Kinetic
Enforcement is presently installed or active on Anthropic infrastructure.

**Rationale:** Replacing the paragraph preserves concision while drawing the
most important categorical distinction. Product and policy controls depend on
adoption, interpretation, or voluntary compliance; the proposed enforcement
property resides in the consequence path and is evaluated mechanically. The
declared-coverage qualifier preserves falsifiability and avoids claiming global
or administrator-proof immutability.

**Verification:** Static checks measured 201 words, one HTTPS link, and every
requested concept. The regenerated email reader contains one H1, standard
rather than wide layout, no remote runtime asset, and a source SHA-256 matching
the Markdown bytes. Forty-eight focused renderer, generation, and publication-
contract tests passed; `git diff --check` returned no error.

**Affected artifacts:** Revised and regenerated
`docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-email.*` and
`docs/superpowers/specs/2026-09-14-kinetic-zero-trust-dario-briefing-design.*`;
updated `docs/superpowers/plans/2026-09-14-concise-dario-email.md`; and appended
this lineage entry with its generated reader. No email, publication, KTP or KIL
runtime, laboratory, cluster, protocol, enforcement, briefing, pilot, or other
external state changed.

**Unresolved questions:** Replacement of sender placeholders, delivery channel,
and first-contact attachment strategy.

**Next gate:** Review the amended standalone email reader. After editorial and
sender-field approval, decide the attachment strategy. Do not send or publish
without explicit authorization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-261 — 2026-09-14 — Complete working-tree publication authorized

**Input:** Commit and push all current repository changes.

**Interpretation:** Treat “all” as explicit authorization to include every
tracked modification and every non-ignored untracked file in the normal `main`
working tree: the Turnkey Blue Zone and Frontier Zero Trust materials, Dario
briefing package, generated review readers, transcript exports, OTCS input
record, renderer wide-layout support and test, production plans and design
specification, and accumulated specialist-lineage additions. Preserve ignored
private lab state and do not modify it merely to satisfy an environment-facing
test.

**Decision status:** Publication to `origin/main` is confirmed. The staged set
contains 35 files after generating HTML siblings for all 71 tracked Markdown
sources and adding the canonical KTP citation to six newly tracked documents
that lacked it. No credential-like material was detected by the bounded secret
pattern scan, and no staged file is oversized for this repository.

**Rationale:** The user explicitly authorized the complete working-tree scope.
Generating every expected HTML sibling and satisfying the citation contract
keeps the repository publication model coherent instead of committing known
reader drift. The ignored V3B-1 live board is intentionally excluded because it
is private operational state, not a publication artifact.

**Verification:** `docs-html-check` verified 71 readers; the 49 Markdown reader
tests, four citation tests, four transition-record tests, and staged diff check
passed. The complete test run is not green: the ignored live-board freshness
assertion expects “task 11” while the local private board remains at task 10.
A second run executed 1,098 tests with only that assertion excluded; 1,064
passed and 34 failed in unchanged V3B-2 controller tests, all centered on the
existing `image_import_identity_invalid` path. No `src/kil/v3b2_controller.py`
or `tests/test_v3b2_controller.py` change is staged, so these failures are
recorded as pre-existing baseline/runtime-fixture drift rather than repaired or
concealed in this publication.

**Affected artifacts:** All staged paths reported by Git, including the
strategy, theses, private briefing package, email, transcripts, plans,
specification, input record, reader renderer and tests, generated HTML readers,
and this lineage entry. The ignored private lab board and runtime state remain
unchanged. No email, briefing, pilot, enforcement deployment, or runtime action
was performed.

**Unresolved questions:** The stale private live-board state and V3B-2 image
import fixture/identity failures require a separate diagnosis before the full
repository validation gate can be represented as green.

**Next gate:** Regenerate and verify the lineage reader, commit the entire
staged set as one documentation/publication checkpoint, push `main` to
`origin`, and verify that the remote branch resolves to the local commit. Treat
the recorded V3B test failures as an explicit follow-up rather than silently
changing unrelated runtime state.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-262 — 2026-09-14 — Coordinate-record conversation transcript exported

**Input:** Export the full conversation transcript into a Markdown file in the
KIL project folder.

**Interpretation:** Preserve every user and assistant conversation message in
this task through the export request, including assistant progress updates.
Exclude hidden system/developer instructions, internal reasoning, tool calls,
raw tool output, and app-injected runtime metadata because those are execution
context rather than conversation messages. State the snapshot boundary so the
artifact does not imply that later messages are present.

**Decision status:** Confirmed and implemented as a project-root Markdown
transcript. The export covers the 2026-09-03 KIL OTCS coordinate-record task and
the 2026-09-14 export request through the declared snapshot boundary. No
runtime, protocol, evidence, or publication claim changed.

**Rationale:** A bounded, human-readable transcript preserves the user-visible
provenance of the coordinate-record work without disclosing hidden execution
context or representing raw tool telemetry as dialogue.

**Affected artifacts:**

- `CONVERSATION-TRANSCRIPT-2026-09-14.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** None for the requested export. Later conversation is
outside this snapshot and would require a subsequent append or re-export.

**Next gate:** User review of the exported Markdown transcript.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-263 — 2026-09-14 — KIL architecture task transcript exported

**Input:** Export the full conversation/transcript for the active “KIL
architecture” Codex task into a Markdown file in the KIL project folder.

**Interpretation:** Create a human-readable chronological snapshot of the
user-visible conversation from the task's complete local event log. Include
user-authored messages and visible assistant commentary/final responses;
exclude hidden system/developer instructions, encrypted reasoning, raw tool
payloads, token accounting, and automatically injected environment/browser/app
state. Represent image attachments with textual markers instead of embedding
binary image data.

**Decision status:** Confirmed and implemented. The transcript is saved at
`docs/transcripts/KIL-architecture-full-transcript-2026-09-14.md`. It is a
point-in-time export rather than a continuously updating file.

**Rationale:** The bounded Markdown export preserves the complete visible
lineage of the long-running KIL architecture task while separating human
conversation from hidden execution context and avoiding a very large binary
payload.

**Affected artifacts:**

- `docs/transcripts/KIL-architecture-full-transcript-2026-09-14.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- no KTP/KIL protocol, architecture, model, evidence, presentation, lab, or
  runtime state

**Unresolved questions:** Later task messages are outside this snapshot unless
the transcript is explicitly refreshed or converted into an ongoing archival
workflow.

**Next gate:** User review of the transcript export. Refresh or automate only
if explicitly requested.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-264 — 2026-09-14 — Parallel lineage histories reconciled for non-force publication

**Input:** Integrate the local complete-working-tree publication checkpoint with
19 newer commits already present on `origin/main`, after a non-fast-forward
push was rejected and the append-only specialist lineage conflicted.

**Interpretation:** Use the already published remote lineage as the authoritative
numbering base through T-245. Preserve the complete text and order of all 18
local entries, but reassign only their colliding heading identifiers from their
local T-236–T-252 range to T-246–T-263. Record the reconciliation explicitly
rather than silently dropping, overwriting, or duplicating entries.

**Decision status:** Confirmed merge resolution. Remote V3B-1 publication and
privacy entries remain T-236–T-245. The local Turnkey Blue Zone, Frontier Zero
Trust, Dario briefing, transcript-export, and publication-authorization entries
are preserved as T-246–T-263. No substantive entry body or decision was removed.

**Rationale:** The two branches independently appended valid history after
T-235. Chronological, unique identifiers are required for a legible lineage and
deterministic HTML anchors. Retaining the published remote sequence and
renumbering the later, previously unpublished local sequence is the least
surprising merge rule.

**Affected artifacts:** Reconciled
`docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`; its HTML reader will be
regenerated from this resolved source. All other merge results are the ordinary
content of the 19 remote commits plus local commit `41a9c13`. No email,
repository-visibility change, release, Pages publication, runtime, laboratory,
enforcement, briefing, or pilot action was performed.

**Unresolved questions:** The existing ignored live-board freshness failure and
V3B-2 `image_import_identity_invalid` test cluster remain separate follow-up
work. They are not altered by this merge resolution.

**Next gate:** Regenerate all Markdown readers, validate the merged staged tree,
complete the merge commit, push `main` without force, and verify that
`origin/main` resolves to the local merge commit.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-265 — 2026-09-14 — Repository and transcript context digested for session continuity

**Input:** "Make sure to digest the transcripts so when I ask you to do
something - it makes sense," following confirmation that the repository and
all tracked transcript files were already committed and synchronized with
`origin/main`.

**Interpretation:** Read the tracked conversation-transcript files, `README.md`,
the publishable paper, and this lineage log's structure/legend and latest
entries so that later instructions in this session can be interpreted against
established KIL/KTP terminology, evidence discipline, and current project
state, rather than re-deriving context from scratch. This is a context-loading
action, not a design, implementation, or evidence decision.

**Decision status:** Confirmed as completed for this session. Read in full:
`CONVERSATION-TRANSCRIPT-2026-09-14.md` (OTCS coordinate-record task),
`KIL-CONVERSATION-TRANSCRIPT-2026-09-14.md` (Turnkey Blue Zone / Frontier Zero
Trust / Dario Amodei briefing package), `README.md`, and
`docs/paper/kinetic-infrastructure.md`. Read in substantial part (opening,
multiple internal ranges, and the full ending) `KIL-V3B1-CONVERSATION-TRANSCRIPT-2026-09-14.md`
(V3B-1 live-Envoy testing through the V3B-1 Complete / V4 Future publication
decision and the confirmed remain-private decision) and
`docs/transcripts/KIL-architecture-full-transcript-2026-09-14.md` (project
origin from the Hugging Face incident and KTP through the trust-decay model,
V1–V3A history, and later presentation-asset promotions). Read this lineage
log's purpose/convention section and its most recent entries through T-264.

**Rationale:** The repository's own convention treats the specialist lineage
log and exported transcripts as the durable record of why KIL exists, how its
architecture evolved, and which claims are confirmed versus proposed. Loading
that record before further instructions reduces the risk of contradicting
prior approved decisions (e.g., the non-expansion invariant, the
`observed`/`modeled`/`validated` evidence contract, the `kil-v3-lab`-only
Colima ownership rule, the exactly-once central-request rule, the V3B-1
Complete / V4 Future publication boundary, and the confirmed-private repository
visibility decision).

**Affected artifacts:** None changed; this entry documents context loaded into
the current session. No code, evidence, publication claim, or repository
setting was modified.

**Unresolved questions:** None raised by this review. The V3B-2/V4 Future
`image_import_identity_invalid` deferred test boundary and the ignored
live-board freshness follow-up noted in T-264 remain open, pre-existing items
independent of this digestion.

**Next gate:** None required by this entry; awaiting the user's next
substantive request.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-266 — 2026-09-15 — V3B-1 completion reverified and closed evidence namespace repaired

**Input:** Finish V3B-1 testing from the prior stopping point, use parallel
agents, and minimize additional approval prompts.

**Interpretation:** Resolve the request against the synchronized repository
record before issuing any runtime command. V3B-1 already has one accepted,
exactly-once Task 11 local-Envoy result, so another live request would be
repetition/new evidence reserved for post-publication V4 Future. Complete only
the safe outstanding verification and bookkeeping work: audit runtime absence,
refresh the ignored status board, close the historical Task 10 checklist, and
verify the accepted evidence bundle without changing its declared contents.

**Decision status:** Confirmed V3B-1 remains complete at the bounded
`local_envoy_boundary`. No live lifecycle command or request traffic was
authorized or executed. Three independent read-only audits confirmed that
`main` matched `origin/main` at the start, `kil-v3-lab` was absent, no active
state/journal/readiness-poison/publication-staging marker existed, and the
foreign `default` and `attackswarm` profiles remained outside KIL ownership and
untouched. The private live board now records Task 11 completion, exactly one
attempt per track, no retry, and the V4 Future exclusions. The historical Task
10 public-record step is marked complete together with its contract assertion.

Offline verification exposed one tracked `summary.htm` inside the accepted run
directory that was not named by `SHA256SUMS`, the manifest artifact map, or the
controller's closed authoritative file set. The accepted bundle therefore
failed closed as designed. The undeclared companion was removed; the general
Markdown reader now excludes the exact reserved `artifacts/generated/**`
namespace, and regression coverage proves the exclusion is component-exact,
links to excluded evidence retain `.md`, similarly named directories remain
eligible, and an HTML companion inside generated evidence is rejected as
unexpected. This entry supersedes the blanket reader invariant recorded in
T-143/T-144 only for the exact generated-evidence namespace; historical entries
remain unchanged.

**Rationale:** The accepted run is immutable evidence whose directory shape is
part of its verification contract. A convenience reader not bound by the
manifest or checksums weakens that closed set even if its own content is
benign. Keeping ordinary documentation readers outside generated evidence
preserves both guarantees: repository Markdown remains reviewable through
deterministic siblings, while evidence directories remain exactly
manifest-defined. Avoiding a live rerun preserves the exactly-once record and
the approved V3B-1 Complete / V4 Future publication boundary.

**Verification:** The accepted run
`v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94`
again passes every recorded checksum and the offline `view --bundle` verifier,
which returns its accepted `live.html` presenter. The focused live-board test,
Task 10 publication-contract test, evidence-namespace renderer tests, and
tracked reader-set test pass. A fresh 303-test V3B-1 run found only the stale
Task 10 checkbox expectation before that expectation was corrected; no
controller, request-driver, evidence, publication-status, or live-board defect
remained. Independent specification and quality/security reviews reported no
Critical finding and approved the closed-evidence approach after requiring
current maintainer guidance, boundary tests, reader regeneration, and this
lineage entry.

**Affected artifacts:** Updated `tools/render_markdown.py`,
`tests/test_markdown_html.py`, `tests/test_v3b1_documentation.py`, `README.md`,
`tools/README.md`, and the Task 10 plan/checklist; removed only the undeclared
accepted-bundle `summary.htm`; refreshed the ignored private V3B-1 status board;
and appended this lineage entry plus regenerated documentation readers. The
accepted checksummed files, KIL/KTP protocol, evidence values, Colima profiles,
and V4 Future implementation remain unchanged.

**Unresolved questions:** None inside V3B-1. Kind/Calico, NetworkPolicy,
repetition, and performance remain explicitly deferred to post-publication V4
Future.

**Next gate:** Regenerate all eligible readers, run the complete repository
validation from the Python 3.12 environment, obtain final independent
read-only review, then commit and push this closure checkpoint without running
the live lab.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-267 — 2026-09-15 — V4 Future branch synchronized and static execution resumed

**Input:** Begin V4 work with the same evidence-first, parallel-review,
minimal-prompt, dedicated-profile, verification, commit, and private-push
discipline used for V3B-1. Before starting implementation, synchronize and
publish a recoverable safety checkpoint, then begin execution.

**Interpretation:** Resume the preserved V3B-2a Kind/Calico implementation as
post-publication **V4 Future** work. Integrate current private `main` before new
implementation, retain the branch's expanded proof graph, preserve the exact
16-method opt-in lifecycle boundary from `main`, and treat the present
authorization to begin execution as approval to proceed through the already
approved control-plane static-manifest design without changing its claim
boundary. Static work may proceed; no live lifecycle is authorized by this
checkpoint.

**Decision status:** Confirmed. Current `main` at `0099d37` was merged into
`codex/v3b2-kind-calico-implementation`. The three predicted conflicts were
resolved by preserving the full chronological lineage, regenerating its HTML
reader from the merged Markdown, retaining the expanded V4 controller fixture,
and applying the exact `v4_future` decorator and guard contract. The branch
still stops honestly at
`platform_admission_terminal_gate_pending`; neither that terminal nor any live
result is represented as complete.

**Rationale:** A pushed synchronization checkpoint separates integration risk
from new proof implementation and makes the resumed work recoverable. Keeping
the opt-in boundary visible preserves the public V3B-1 gate while V4 completes
the underlying proof graph. The next missing authority is not the previously
repaired image-import fixture: it is the two-file, identity-bracketed
kube-apiserver and kube-controller-manager static-manifest source required
before all ten platform Pod configurations can compose into the terminal.

**Verification:** The merged V4 boundary guard passed. Forty-three controller
tests passed with exactly 16 intentional V4 Future skips. Twenty-two focused
runtime-authority and dedicated-profile tests passed in an independent
read-only audit. That audit found `kil-v3-lab`, its Colima/Lima state paths, the
V3B-2 private journal root, and V3B-2 public evidence absent. Foreign profiles
remained unchanged: `default` stopped and `attackswarm` running. The required
live input archive `.tools/v3b2-input/kil-image.tar` is absent, so live V4
preflight and lifecycle execution remain fail-closed and were not run.

**Affected artifacts:** The V4 implementation branch receives current `main`,
the merged controller-test opt-in boundary, the complete append-only lineage,
regenerated Markdown readers, and this entry. No Colima, Docker, Kind,
Kubernetes, request, evidence, repository-visibility, or foreign-profile state
changed.

**Unresolved questions:** The opt-in V4 lifecycle suite remains intentionally
red at the platform-admission terminal. The two control-plane static-manifest
proofs, platform image/status/readiness composition, all-ten-Pod terminal,
Task 7 static acceptance, request-free lifecycle, and nominal lifecycle remain
open in that order. V3C repetition and performance remain closed.

**Next gate:** Complete and review the test-first implementation plan for the
approved two-file control-plane manifest source. Execute its closed source and
journal/replay slice first, followed by kube-apiserver and
kube-controller-manager disk/API proofs. Keep completion flags false until the
remaining platform authority composes and do not open the live gate before the
entire static suite passes from synchronized private `main`.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-268 — 2026-09-15 — V4 static-manifest execution plan opened

**Input:** After synchronizing the V4 Future implementation branch, begin
execution with the same evidence-first discipline as V3B-1 and minimize
external approval pauses.

**Interpretation:** Convert the approved control-plane static-manifest source
design into a test-first implementation sequence and begin with the smallest
closed static slice. The work remains confined to repository code and tests;
it does not authorize a live Kind/Calico lifecycle or any Colima mutation.

**Decision status:** Confirmed. The implementation plan is split into a pure
two-command/four-observation source proof, a deterministic private checkpoint
and replay-safe journal family, controller ordering, independent
kube-apiserver and kube-controller-manager disk/API proofs, and a final static
acceptance checkpoint. Each implementation task requires specification review,
quality review, focused tests, and a logical commit.

**Rationale:** The two missing static-mirror configurations depend on evidence
that cannot truthfully be inferred from API Pod fields or a predicted Kind
root filesystem. Capturing only the two literal manifest paths from the exact
identity-bracketed owned node establishes the narrow missing authority while
keeping foreign profiles, arbitrary paths, shell input, live readiness, and
application completion outside the claim.

**Verification:** The synchronization checkpoint `13ccd07` was pushed to the
private `codex/v3b2-kind-calico-implementation` branch and the local and remote
revisions matched. The definitive post-merge validation passed 1,492 tests
with exactly 16 intentional V4 lifecycle skips, verified 75 Markdown readers,
and reported no diff-format errors. Independent review found no Critical,
Important, or Minor issue in the two merge-fixture reconciliations; production
validators were unchanged. Shell-sensitive Envoy tests separately passed all
10 cases under their normal local execution boundary.

**Affected artifacts:** Added
`docs/superpowers/plans/2026-09-15-v4-control-plane-static-manifest-source.md`
and this lineage entry. The approved design status remains implementation-ready.
No Colima, Docker, Kind, Kubernetes, request, evidence, or repository-visibility
state changed.

**Unresolved questions:** The pure manifest source, durable checkpoint,
journal/controller wiring, both component proofs, platform image/status/readiness
composition, all-ten-Pod terminal, request-free lifecycle, and nominal lifecycle
remain to be implemented and accepted. The live input archive remains absent.

**Next gate:** Implement Task 1's exact Docker command grammar and pure
control-plane manifest source proof under TDD, then obtain independent
specification and quality review before starting durable persistence.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-269 — 2026-09-15 — V4 control-plane manifest source proof implemented

**Input:** Execute Task 1 of the approved V4 control-plane static-manifest
source plan: add the exact two-command Docker read surface, a four-observation
owned-node identity bracket, bounded closed-YAML Pod decoding, immutable source
bindings and reconstruction, and focused journal grammar coverage. Keep the
work static-only, preserve foreign profiles, retain strict false completion
flags, and commit a local checkpoint without pushing.

**Interpretation:** This checkpoint authenticates only the transport envelope,
retained raw observations, node-identity bracket, and independent raw and
canonical semantic commitments for the two literal kubeadm manifest paths.
Component-specific producer configuration, conditional CA subsets, disk-to-API
mirror transformation, runtime readiness, and application completion remain
outside Task 1 and belong to later V4 gates.

**Decision status:** Confirmed static implementation checkpoint; no live claim.
The command grammar admits only nonmutating, stdin-free `/bin/cat --` reads for
the kube-apiserver and kube-controller-manager manifest paths through the
journaled isolated Docker endpoint and private Docker configuration. The pure
proof retains exactly four ordered observations and two sorted bindings while
both `runtime_complete` and `application_complete` remain exact `False`.

**Rationale:** Reading the two effective files from the exact owned Kind node
closes the missing source boundary without accepting caller-selected paths,
shell evaluation, current-context discovery, API Pod fields, or foreign Docker
authority. Reconstructing the proof from canonical retained observation bytes
and separately hashing raw and parsed Pod content makes later private
checkpoint replay deterministic while preventing source or identity
substitution.

**Verification:** Test-first development witnessed the missing module and
Docker grammar fail before implementation, then witnessed the proof boundary
fail before validation was added. Independent review identified and the
implementation corrected a coordinated constructor-forgery gap by retaining
and reconstructing the exact expected context and owned identity. The 4 MiB
guard now measures the planned complete `{schema, context, proof}` checkpoint
envelope. Independent re-review then found no remaining Critical, Important,
or Minor issue. The required focused and neighboring suite passed 112 tests
covering command closure, authority drift, transport failure,
the exact 1 MiB boundary, closed-YAML ambiguity, digest independence,
constructor forgery, detached Pod access, the 4 MiB proof bound, and unchanged
existing journal/image-command behavior. No Colima, Docker, Kind, kubectl, or
live runtime command was invoked.

**Affected artifacts:** Added
`src/kil/v3b2_control_plane_manifest_source.py` and
`tests/test_v3b2_control_plane_manifest_source.py`; extended only the Docker
read grammar in `src/kil/v3b2_journal.py` and its focused test; appended this
lineage entry and regenerated its HTML reader. No foreign profile, live
cluster, evidence bundle, publication, or repository-visibility state changed.

**Unresolved questions:** Durable no-follow checkpoint encoding, lifecycle
ordering and replay wiring, controller capture/recovery behavior, both
component-specific disk/API configuration proofs, platform
image/status/readiness composition, the all-ten-Pod terminal, request-free
lifecycle, and nominal lifecycle remain open. This checkpoint does not claim
that either parsed Pod has the final reviewed producer configuration or CA
subset. Task 3 must use a bounded successful-output capture path so an
oversized manifest is marked truncated before unbounded process output can be
retained; Task 1's pure post-capture validator does not claim that controller
transport property.

**Next gate:** Implement Task 2's canonical 4 MiB private source checkpoint and
replay-safe journal family from retained bytes only, followed by Task 3's
bounded capture and recovery wiring. Keep all completion flags false and do not
open any live gate.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-270 — 2026-09-15 — V4 manifest source encoding review corrections

**Input:** Resolve the Task 1 specification-review findings that node-inspect
JSON accepted Python's UTF-16/UTF-32 byte auto-detection and retained
observation hex accepted uppercase or whitespace-separated spellings. Preserve
the static-only scope, use test-first corrections, and publish no live claim.

**Interpretation:** Every observation transport in the manifest source proof
must have one canonical byte interpretation. Node inspection is strict UTF-8
JSON rather than generic Python bytes-to-JSON autodetection, and retained
stdout/stderr commitments use only exact lowercase contiguous hexadecimal.
These are source-envelope corrections; they do not add component configuration,
runtime, readiness, or application authority.

**Decision status:** Confirmed static Task 1 correction; no live claim. The
validator now decodes node-inspect bytes as strict UTF-8 text before closed JSON
parsing, and proof reconstruction requires each retained hex spelling to equal
the exact decoded byte sequence's canonical `.hex()` result. Completion flags
remain exact `False`.

**Rationale:** Python's bytes-oriented JSON loader intentionally recognizes
UTF-16 and UTF-32, which was broader than the approved source contract.
Likewise, `bytes.fromhex` intentionally ignores ASCII whitespace and accepts
uppercase digits. Constraining both boundaries prevents alternate byte and
text representations from reconstructing as the same retained authority.

**Verification:** The new UTF-16, UTF-32, uppercase-hex, and whitespace-hex
tests first failed against checkpoint `8ad7011`, directly reproducing both
findings. After the bounded decoder corrections, the focused and neighboring
suite passed 114 tests. No Colima, Docker, Kind, kubectl, or live runtime
command was invoked.

**Affected artifacts:** Corrected
`src/kil/v3b2_control_plane_manifest_source.py`, extended
`tests/test_v3b2_control_plane_manifest_source.py`, appended this lineage entry,
and regenerated the lineage HTML reader. No journal grammar, foreign profile,
cluster, evidence bundle, publication, or repository-visibility state changed.

**Unresolved questions:** Task 2 persistence, Task 3 bounded successful-output
capture and recovery, both component disk/API proofs, platform composition,
the all-ten-Pod terminal, request-free lifecycle, and nominal lifecycle remain
open. This correction does not authorize live capture.

**Next gate:** Complete correction review, then begin Task 2's canonical private
checkpoint and replay-safe journal family. Preserve strict false completion
flags and carry bounded successful-output capture into Task 3.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
