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
