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

### T-125 — 2026-08-31 — Demo readiness remains split between showcaseable assets and accepted live enforcement

**Input:** Determine whether the KIL laboratory is ready to demonstrate after
Task 10 publication PR #17 merged and synchronized.

**Interpretation:** “Ready to demo” has two materially different meanings. The
modeled V3A presenter and the live V3B-1 request-free lifecycle can be shown
now. An accepted live KIL enforcement demonstration requires a consequential
central request and therefore must satisfy the stronger evidence boundary
before it runs.

**Decision status:** Confirmed partial readiness. Public and local `main` are
synchronized at merge commit
`ab2667941b9328739c8201d626694770e2387fe9`; the merged 485-test gate passes;
and Task 10 established three-driver readiness, clean cancellation, zero
request activity, evidence freeze, and exact owned-object teardown. The central
`run` has not executed and is not yet authorized. Exact before/after foreign-
resource snapshots, verifier equality, and their publication gate remain
unimplemented.

**Rationale:** Showing the request-free lifecycle as an enforcement result
would collapse lifecycle safety into authorization evidence. The accepted live
demo must retain the no-retry boundary and must not claim exact foreign-state
restoration until that state is durably bound at both observation boundaries.

**Affected artifacts:**

- `docs/lab/V3B1-TASK10-REQUEST-FREE-GATE.md`
- `docs/lab/V3-PROGRESS.md`
- `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The public representation of foreign-profile
snapshots requires founder approval: exact raw records, digest-only records, or
pseudonymous per-profile records. The recommended design retains exact names
privately and publishes pseudonymous resource records.

**Next gate:** Approve the snapshot representation; write and review its narrow
design specification and implementation plan; implement it test-first; pass
independent review and public CI; merge and synchronize; then execute and
publish a fresh request-free snapshot lifecycle. Only after that gate may the
one-shot central live proof execute.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-126 — 2026-08-31 — Current-main V3A modeled presenter regenerated for founder viewing

**Input:** Display the V3A visual demonstration.

**Interpretation:** Provide the existing V3A process-contract demonstration as
a visible, integrity-checked modeled asset without representing it as the live
V3B-1 enforcement proof.

**Decision status:** Confirmed execution of the deterministic V3A presenter on
current public `main` commit
`ab2667941b9328739c8201d626694770e2387fe9`. The three fixed outcomes were
`permit / permit / deny`, with target-marker counts `1 / 1 / 0` and valid
proofs. The generated bundle identifier is `ea57c04913151539`.

**Rationale:** The prior browser artifact lived in a removed development
worktree. Regenerating from synchronized `main` supplies a current, reproducible
presenter while preserving the evidence boundary: V3A remains modeled and
process-contract-only, not a validated Envoy or cluster result.

**Affected artifacts:**

- ignored generated bundle
  `artifacts/generated/v3a-process-contract/ea57c04913151539/`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** None for viewing. The accepted live-enforcement demo
still depends on the approved foreign-resource snapshot contract and its fresh
request-free publication gate.

**Next gate:** Review the V3A presenter as a modeled showcase. Do not promote
its outcomes as live enforcement; continue with snapshot-contract approval
before authorizing the one-shot V3B-1 central proof.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-127 — 2026-08-31 — Founder approves pseudonymous-public/full-private foreign-resource snapshot design

**Input:** Proceed with the next actions and confirm the recommended foreign-
resource snapshot representation.

**Interpretation:** The founder's “correct” confirms the recommended design:
exact named snapshots remain private, complete public resource tuples use
run-scoped pseudonymous profile references, equality is exact, v3 evidence
fails closed on mismatch, and legacy v1/v2 bundles retain their original
verification rules.

**Decision status:** Confirmed architecture approval. The narrow design is
recorded in
`docs/superpowers/specs/2026-08-31-v3b1-foreign-resource-snapshot-design.md`.
No controller behavior or consequential request has been executed. The
isolated branch baseline passes all 485 tests.

**Rationale:** This representation makes the full resource tuple independently
inspectable without publishing local profile names. Exact private journal
records retain recovery and audit authority. Observation never grants KIL
authority to repair or mutate foreign profiles.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-31-v3b1-foreign-resource-snapshot-design.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- isolated branch `codex/v3b1-foreign-snapshot-contract`

**Unresolved questions:** Founder review of the written specification remains
the final design gate. Implementation planning and production-code changes have
not begun.

**Next gate:** Self-review and commit the specification, then obtain founder
approval of the written file. After approval, write the complete test-first
implementation plan. The central `run` remains prohibited.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-128 — 2026-08-31 — Audience walkthrough distinguishes observed lifecycle, modeled outcome, and pending live enforcement

**Input:** Show how the live demonstration works in a form that other people
can understand.

**Interpretation:** Provide a presenter-facing step-through of topology,
readiness, request intent, ambient enforcement, comparative outcomes, evidence
construction, and the current approval gate without implying that the central
live enforcement request has already executed.

**Decision status:** Confirmed explanatory asset. The walkthrough states that
the request-free V3B-1 lifecycle is observed live, the `permit / permit / deny`
comparison is currently reproduced by the modeled V3A process contract, and
the authoritative V3B-1 enforcement result remains locked behind the v3
foreign-resource snapshot gate.

**Rationale:** A credible public demonstration must make the enforcement path
and evidentiary boundary visible at the same time. The audience sees the fixed
path `controller -> one-shot driver -> Envoy -> KIL authorization -> target or
withhold`, the three comparison tracks, and the evidence pipeline without
collapsing modeled, observed, and pending claims.

**Affected artifacts:**

- thread visualization `kil-live-demo-walkthrough.html`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Verification:** The fragment rendered successfully, JavaScript syntax was
validated, all seven controls updated their intended state, and the topology,
outcome, evidence, and gate views were checked at 736-pixel and 360-pixel
viewports with no console warnings, errors, or horizontal overflow.

**Unresolved questions:** The written v3 snapshot specification still requires
founder review. The walkthrough is not itself an evidence bundle and must not
be presented as the accepted live result.

**Next gate:** Obtain founder approval of
`docs/superpowers/specs/2026-08-31-v3b1-foreign-resource-snapshot-design.md`,
then write the test-first implementation plan. The central `run` remains
prohibited until the merged v3 snapshot contract passes a fresh request-free
publication gate.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-129 — 2026-08-31 — Audience walkthrough exported and opened as an interactive browser page

**Input:** Provide the live-demo walkthrough as an interactive page rather
than Markdown.

**Interpretation:** Export the verified audience walkthrough to a standalone
document inside the KIL repository's generated-artifact area and present it in
the in-app browser with all seven stages interactive.

**Decision status:** Confirmed presentation export. The standalone page is
available at `artifacts/generated/kil-live-demo-walkthrough.html` and was opened
through a localhost-only browser session. Stage interaction was rechecked before
handoff. This export does not change the evidence status of the laboratory.

**Rationale:** A presenter needs a directly operable page, while the document
must continue to distinguish the observed request-free lifecycle, the modeled
V3A outcome, and the pending V3B-1 central enforcement result.

**Affected artifacts:**

- ignored generated export `artifacts/generated/kil-live-demo-walkthrough.html`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** The standalone page is a walkthrough, not an accepted
live evidence bundle. The v3 snapshot specification still awaits founder review.

**Next gate:** Approve the written v3 snapshot specification, produce the
test-first implementation plan, and keep the central `run` prohibited until a
fresh merged request-free v3 publication gate passes.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-130 — 2026-08-31 — Stage-linked presenter talk track requested

**Input:** Determine whether each walkthrough click has an associated talk
track and create one if absent.

**Interpretation:** The current page provides a changing diagram and one-line
technical explanation, but it does not provide a rehearsable spoken narrative.
The requested extension should bind one claim-safe script to each of the seven
existing stages without changing laboratory behavior or evidence status.

**Decision status:** Confirmed gap; design pending. No walkthrough source or
standalone export has been modified. The first design choice is speaking depth:
executive-short, balanced presenter, or technical-deep.

**Rationale:** Speaking length determines both content density and page layout.
The talk track must preserve the distinction between observed request-free
behavior, modeled V3A outcomes, and the pending V3B-1 enforcement proof.

**Affected artifacts:**

- proposed update to `kil-live-demo-walkthrough.html`
- proposed regenerated export
  `artifacts/generated/kil-live-demo-walkthrough.html`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Select approximately 15 seconds, 30–45 seconds, or
60–90 seconds of narration per stage. The recommended default is 30–45 seconds
for a mixed executive and technical audience.

**Next gate:** Confirm speaking depth; compare visible embedded notes, a
separate speaker guide, and dual presenter/audience modes; approve the narrow
design before any page modification.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-131 — 2026-08-31 — Balanced 30–45-second stage narration selected

**Input:** Select 30–45 seconds of narration for each of the seven walkthrough
stages.

**Interpretation:** Write approximately 70–90 spoken words per stage for a
mixed executive and technical audience, yielding an approximately five-minute
guided presentation.

**Decision status:** Confirmed narration depth; presentation model proposed.
The recommended model keeps notes synchronized with the existing stage buttons
and adds a presenter-notes visibility control so one page supports rehearsal
and a clean audience view.

**Rationale:** A synchronized presenter mode avoids switching to a separate
document while preventing speaker text from permanently cluttering the public
diagram. Each script can carry its own observed, modeled, or pending claim
boundary at the moment it matters.

**Affected artifacts:**

- proposed walkthrough talk-track design specification
- proposed update to `kil-live-demo-walkthrough.html`
- proposed regenerated export
  `artifacts/generated/kil-live-demo-walkthrough.html`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Founder approval of the recommended synchronized
presenter/audience mode remains required before writing the specification or
modifying the walkthrough.

**Next gate:** Approve the presentation model, then write and commit the narrow
talk-track design specification for final founder review. No laboratory or
enforcement behavior changes are in scope.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-132 — 2026-08-31 — Incident-centered Presenter/Audience storyboard scoped

**Input:** Build synchronized Presenter/Audience mode so the demonstration
tells the story of the disclosed Hugging Face breach, shows how KIL could
potentially have interrupted it, and uses graphics plus a referenced topology
to explain what is happening and why.

**Interpretation:** Expand the seven-step technical walkthrough into one
incident-centered narrative. A persistent topology should trace the disclosed
path from the dataset worker through control-plane, cloud, secret, cross-cluster,
mesh, token, and CI targets; the same view should then map the relevant incident
boundary into the three-track KIL lab. Each selected scene should synchronize
the topology, audience takeaway, evidence label, and a 30–45-second presenter
script. Audience mode hides the script without changing the selected scene.

**Decision status:** Scope confirmed; detailed design proposed and awaiting
founder approval. The recommended cutoff is deliberately two-part: anomalous
local reads are shown as an early trajectory signal, while the first claimed
transport-level intervention is the worker's attempted Kubernetes control-plane
or cloud-metadata egress. Downstream incident branches become conditionally
unreachable rather than being counted as separately prevented. No walkthrough
code or evidence status has changed in this turn.

**Rationale:** The current Envoy laboratory tests an HTTP enforcement boundary,
not application parsing or kernel file access. Locating the decisive public
counterfactual at the first mediated egress keeps the story visually strong
without implying that the current lab has reproduced the complete historical
intrusion or an earlier kernel-level cutoff.

**Affected artifacts:**

- proposed incident-centered Presenter/Audience design specification
- proposed update to the visualization source
  `kil-live-demo-walkthrough.html`
- proposed regenerated export
  `artifacts/generated/kil-live-demo-walkthrough.html`
- canonical scenario `scenarios/hugging-face-july-2026/scenario-v1.json`
  as the scene source of record
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Founder approval is required for the integrated
storyboard and for treating first privileged egress as the principal KIL
counterfactual cutoff. The written v3 foreign-resource snapshot specification
also still requires founder review, and the central live run remains prohibited.

**Next gate:** Approve the incident-centered topology and cutoff boundary;
then write, self-review, and commit the design specification before any page
implementation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-133 — 2026-08-31 — Branching counterfactual visual language selected

**Input:** A founder-supplied reference graphic showed the actual incident as
a branching red timeline, a blue KIL counterfactual terminating at Phase 1,
and downstream phases faded under an `Unreachable` label. The founder stated
that graphics of this kind help tell the story.

**Interpretation:** Use this branching topological-timeline grammar as the
primary incident visual inside synchronized Presenter/Audience mode. Retain a
persistent system-topology map and a separate incident-to-lab mapping, but make
the actual-versus-counterfactual branch graphic the principal explanation of
why one early transport intervention changes downstream reachability.

**Decision status:** Confirmed visual direction; implementation still awaits
approval of the consolidated design. The scenario's `d_t = 0.95` value may be
shown only with an explicit `modeled` label. Replace unconditional phrases such
as `absolute denial` and `prevented` with conditional model language such as
`modeled deny at the mediated boundary` and `downstream actions conditionally
unreachable`. Correct the reference subtitle duplication before publication.

**Rationale:** The supplied graphic communicates causality and leverage more
clearly than a linear component diagram, but its evidence language must remain
consistent with the canonical scenario: the incident sequence is observed from
the disclosure, the divergence value and KIL result are modeled, and only local
laboratory reproduction can be labeled validated.

**Affected artifacts:**

- founder-supplied branching-timeline visual reference
- proposed Presenter/Audience design specification
- proposed walkthrough visualization source and generated export
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Consolidated founder approval remains required for
the incident-centered storyboard, principal Phase 1 transport cutoff, and this
two-lane actual-versus-KIL visual treatment. The v3 snapshot specification also
remains at its separate founder-review gate.

**Next gate:** Approve the consolidated visual design; then write, self-review,
and commit the design specification before implementation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-134 — 2026-08-31 — Incident Presenter/Audience written design completed

**Input:** The founder approved the consolidated incident-centered design,
including synchronized Presenter/Audience modes, the branching
actual-versus-counterfactual visual language, and the first privileged egress
as the principal KIL cutoff.

**Interpretation:** Convert the approved concept into an implementation-ready
written specification while preserving the historical incident, modeled KIL
counterfactual, local lab mapping, and current evidence gate as distinct claim
classes.

**Decision status:** Written design completed, self-reviewed, and pending
founder review. The specification defines eight scenes, a persistent incident
topology, a branching timeline, the incident-to-lab mapping, 30–45-second
scene-linked scripts, a presenter-authoritative same-origin synchronization
contract, responsive and accessible behavior, canonical tracked source, test
requirements, and non-goals. No demo implementation or laboratory behavior was
changed.

**Rationale:** A durable specification prevents the spoken narrative, animated
graphic, and evidence language from drifting independently. Self-review added a
presenter-epoch handshake so an audience view can recover from presenter reload
without treating new state as stale, and it fixed the principal cutoff at the
canonical Phase 1 Kubernetes control-plane request.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-31-kil-incident-presenter-audience-demo-design.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Founder review of the written presentation design is
required before the test-first implementation plan. The V3B-1 foreign-resource
snapshot design remains at a separate founder-review gate, and the central
laboratory request remains prohibited.

**Next gate:** Founder reviews and approves the written incident-demo design;
then create the test-first implementation plan. Do not implement the page or
run the central V3B-1 request before the applicable gates pass.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-135 — 2026-08-31 — KIL/KTP front matter added to demo design

**Input:** Before the approved eight-scene incident story, introduce the
audience to KIL, how and why it works, its relationship to KTP, and its
relevance as ambient enforcement against ambient breach. The founder supplied
fourteen additional graphics as possible visual direction.

**Interpretation:** Restructure the demonstration into two acts: a four-part
KIL primer followed by the eight-scene Hugging Face case study. Use the supplied
graphics for explanatory composition, not as evidence or unmodified production
assets. Recreate useful concepts in responsive HTML/SVG while reconciling every
claim with the unified paper, canonical scenario, and current laboratory state.

**Decision status:** Written design revised and pending renewed founder review.
The primer now covers: ambient breach versus credential/policy checkpoints;
KIL's ambient-enforcement reframe; KIL as a proposed KTP extension consuming
signed, short-lived composite state under a non-expansion invariant; and the
slow-gain, passive-decay, fast-loss, class-bound trust model. The eight-scene
case study remains intact as Act II.

**Rationale:** An audience cannot interpret the counterfactual incident cutoff
without first understanding the authority model and the KTP/KIL boundary. The
graphic audit prevents persuasive imagery from silently promoting modeled or
future behavior into measured fact.

**Claim corrections recorded:**

- describe the comparison as a credential/policy checkpoint pattern rather
  than claiming all zero-trust architectures are one-time or application-only;
- use the weighted diagonal standardized distance from the paper, not a full
  Mahalanobis claim;
- replace microsecond, throughput, fabricated telemetry, hash, and
  pseudo-measurement claims with unmeasured fast-path language;
- preserve KTP veto and environmental authority and allow local evidence only
  to reduce or withhold;
- use modeled Phase 1 divergence `0.95` and Phase 4 divergence `0.90` from the
  canonical scenario;
- replace `bypass`, `irreversible`, `killed`, `for free`, absolute prevention,
  and validated zero-byte claims with bounded, dependency-aware language; and
- distinguish V3A modeled process evidence, pending V3B-1 local Envoy, and
  future V3B-2 Kind/Calico rather than depicting current V3 as validated live
  Kubernetes.

**Affected artifacts:**

- `docs/superpowers/specs/2026-08-31-kil-incident-presenter-audience-demo-design.md`
- fourteen founder-supplied graphic references used for design review
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Founder approval of the revised two-act written
design remains required before the test-first implementation plan. The V3B-1
foreign-resource snapshot design remains a separate approval dependency, and
the central laboratory request remains prohibited.

**Next gate:** Founder reviews and approves the revised primer-plus-case-study
design; then create the test-first implementation plan and implement the
tracked presenter/audience page without altering laboratory evidence status.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-136 — 2026-08-31 — Synchronized two-act KIL showcase implemented

**Input:** The founder approved immediate implementation of the revised
primer-plus-case-study demonstration, requested that it be moved to a
showcase-ready state, and identified Brave as the Chromium browser used for the
presentation.

**Interpretation:** Implement the approved twelve-state narrative as one
tracked, self-contained browser application. Preserve presenter-only talk
tracks, controls-free audience views, presenter-authoritative synchronization,
the KTP/KIL extension boundary, the modeled Hugging Face counterfactual, and
the current laboratory evidence limits. Prefer the installed Brave executable
for automated browser verification, with Playwright Chromium only as a
fallback.

**Decision status:** Confirmed and implemented. Four KIL primer scenes and eight
incident scenes now render responsive, accessible SVG diagrams from the same
closed narrative contract. Same-session audience views follow the presenter;
wrong sessions are isolated; stale state is rejected; and audience views
recover after a presenter reload through a new presenter epoch. The complete
493-test repository suite passes. A Brave-based browser verifier passes all
twelve graphics, synchronization, 1024-, 736-, and 360-pixel layouts, light and
dark color schemes, reduced-motion mode, native controls, SVG titles and
descriptions, and runtime-console checks. The canonical and generated showcase
HTML files have identical SHA-256 digest
`5947d5cd0de40ff0e7aba32ad922fc049f56127c69c564ba6b83fdaa1bf88a6c`.

**Rationale:** A single contract-driven application keeps public graphics,
spoken narration, evidence labels, and synchronization state from drifting.
The diagrams use observed red paths, proposed or modeled blue KIL paths, faded
conditional descendants, and explicit status copy instead of importing
reference imagery containing unsupported measurements. The launch target is a
loopback HTTP origin so BroadcastChannel synchronization works consistently in
Brave without a hosted service.

**Affected artifacts:**

- `docs/demo/kil-presenter-audience-demo.html`
- `tests/test_presenter_audience_demo.py`
- `tools/verify_presenter_audience_demo.mjs`
- `README.md`
- `Makefile`
- ignored showcase export
  `artifacts/generated/kil-presenter-audience-demo.html`
- ignored Brave-rendered visual-QA captures under
  `artifacts/generated/kil-demo-preview/`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** No unresolved issue remains for presenting the
modeled two-act showcase. The V3B-1 live enforcement result remains pending,
V3B-2 Kind/Calico remains future work, and neither status is promoted by this
demonstration. The separate foreign-resource snapshot and central live-request
gates remain governed by their existing approvals.

**Next gate:** Founder performs the live Presenter/Audience walkthrough in
Brave. After acceptance, publish the feature branch through the normal review
and merge workflow without changing the laboratory evidence labels.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-137 — 2026-08-31 — Envoy lab diagram paused at counterfactual-first design gate

**Input:** Create a graphical diagram showing how the Envoy laboratory was set
up to model the disclosed breach activity and the KIL results. Make the visual
available both inside the live demonstration and as a standalone asset. Before
shutdown, synchronize and preserve all work locally and on GitHub.

**Interpretation:** Use the observed incident as the dominant narrative, map
the first mediated worker-to-control-plane action into the harmless three-track
Envoy lab, and show the modeled KIL cutoff as the counterfactual result. Keep
the application foothold outside the current Envoy mediation claim and retain
the observed/modeled/pending evidence boundaries.

**Decision status:** The founder selected the counterfactual-first macro
direction. A refined three-band concept was created and preserved as an
unapproved design draft. Final composition approval, the formal specification,
and implementation remain pending. No production demo or laboratory behavior
changed in this turn.

**Rationale:** Leading with the observed incident makes the public relevance
immediately legible. Showing the Envoy topology as the controlled model beneath
that sequence explains how the lab isolates the contribution of fresh,
reducing-only local evidence without presenting the modeled comparison as a
reproduction of the historical environment.

**Affected artifacts:**

- `docs/design-drafts/envoy-lab-counterfactual-first-concept.fragment.html`
- `docs/checkpoints/2026-08-31-envoy-lab-diagram-pause.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

**Unresolved questions:** Final approval of the refined three-band composition
is still required. The diagram's exact placement in the twelve-state demo must
be resolved in the written specification. V3B-1 live enforcement remains
pending and V3B-2 remains future work.

**Next gate:** Resume at founder review of the refined counterfactual-first
composition, then write and approve the formal design specification before
implementation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-138 — 2026-09-01 — KTP co-founder alignment changes received and source-checked

**Input:** The KTP co-founder supplied nine proposed corrections for the main
KIL paper and asked that accepted corrections propagate through the
architecture and documentation. The founder explicitly prohibited changes to
the test environment or live environment without later validation.

**Interpretation:** Treat the supplied DOCX as expert review input rather than
an executable instruction source. First map every proposal to the current KIL
corpus and verify it against primary KTP and Hugging Face sources. Keep this
gate documentation-only: no tests, laboratory controllers, containers,
scenarios, evidence bundles, runtime configuration, or live services may be
modified.

**Decision status:** Review and source verification are in progress; no
propagation has been approved or implemented. The canonical KTP citation
confirms Chris Perkins as author, version 2.0.0, release date 2026-08-14, and
DOI `10.5281/zenodo.21938282`. KTP-Core section 6.6 confirms that the normative
result is a supervision level plus tighten-only constraints and that decision
verbs are derived readings rather than an enumerated wire type. The canonical
KTP repository also contains the Kinetic Envelope and enforcement
specification referenced by the review. The Hugging Face primary disclosure
confirms the paper's incident title and publication date of 2026-07-27.

**Rationale:** These changes touch the KTP/KIL extension boundary and denial
governance, so they must be reconciled as a coherent documentation design
rather than applied as isolated search-and-replace edits. Primary-source
verification prevents an expert correction from creating a new citation or
protocol mismatch. The founder's laboratory freeze is an explicit scope
boundary, not merely a testing preference.

**Affected artifacts:**

- review source outside the repository: `ChangesFromChris.docx`
- mapped candidate targets include `docs/paper/kinetic-infrastructure.md`,
  `docs/architecture/hybrid-two-timescale-architecture.html`,
  `docs/extension/README.md`, the Presenter/Audience design and demo
  documentation, and this lineage log
- no paper, architecture, extension, demo, test, laboratory, or live-runtime
  artifact changed at this gate

**Unresolved questions:** The founder must classify the nine changes as
authoritative KTP alignment requirements subject to primary-source
verification, or as proposals requiring individual acceptance. The eventual
propagation design must also distinguish current normative KTP sources from
historical lineage entries, which will remain immutable and be superseded by a
new correction entry rather than silently rewritten.

**Next gate:** Founder resolves the authority status of the co-founder review;
then compare two or three documentation-only propagation strategies and obtain
approval for a written design specification before any implementation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-139 — 2026-09-01 — Co-founder corrections confirmed as authoritative

**Input:** The founder confirmed that all nine co-founder changes are
authoritative KTP-alignment requirements, subject to primary-source
verification.

**Interpretation:** The corrections are no longer optional editorial
suggestions. The documentation design must incorporate every verified change
across the current KIL paper, architecture, extension explanation, and public
demo narrative while maintaining an explicit prohibition on changes to tests,
laboratory controllers, scenario fixtures, evidence bundles, containers,
runtime configuration, and live services.

**Decision status:** Confirmed. Primary-source verification remains a
precondition for each propagated statement. Verified conflicts in current
published documentation must be corrected; historical lineage entries remain
immutable and will be superseded by later entries. Whether historical design
specifications and implementation plans should remain untouched, receive a
non-destructive supersession notice, or be edited is the remaining scope
question.

**Rationale:** Treating the review as authoritative makes KTP semantic
alignment the controlling requirement. Preserving runtime and evidentiary
state separately prevents a documentation correction from silently changing
what the lab proves. Preserving historical lineage protects the project's
decision history while allowing current deliverables to become canonical.

**Affected artifacts:**

- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- candidate current-deliverable scope: main paper, canonical hybrid
  architecture, extension overview, Presenter/Audience demo and its design
  documentation, and current project navigation
- explicitly excluded from implementation scope pending separate founder
  validation: all test and live/laboratory artifacts

**Unresolved questions:** Determine the treatment of historical design specs,
implementation plans, and checkpoints that contain superseded KTP language.

**Next gate:** Founder selects the historical-document treatment; then review
two or three propagation approaches and approve the documentation-only design.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-140 — 2026-09-01 — Historical documents retain text with supersession notices

**Input:** The founder approved use of superseded-terminology notices for
historical KIL specifications, plans, and checkpoints.

**Interpretation:** Correct current canonical deliverables directly. Preserve
the body text of historical records and add a concise notice pointing readers
to the new KTP-alignment design and current canonical artifacts. Do not rewrite
earlier specialist-lineage entries; record supersession only through new
entries.

**Decision status:** Confirmed. Historical records remain evidence of what was
known and decided at the time. Their notices will prevent obsolete KTP terms
from being mistaken for current protocol guidance.

**Rationale:** Non-destructive notices balance accuracy with lineage. A global
rewrite would make past plans appear to have used concepts that were not
actually controlling when those plans were authored, while leaving them
unmarked would allow stale terminology to compete with current documentation.

**Affected artifacts:**

- current canonical paper, architecture, extension, demo, and navigation
  artifacts will be candidates for direct correction after design approval
- affected historical specs, plans, and checkpoints will be candidates for a
  supersession notice only
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- all tests and live/laboratory artifacts remain excluded

**Unresolved questions:** Founder approval of the recommended propagation
architecture and its precise current-versus-historical artifact inventory.

**Next gate:** Present two or three propagation approaches and obtain approval
for the recommended canonical-first, history-preserving design.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-141 — 2026-09-01 — Canonical-first isolated propagation selected

**Input:** The founder selected propagation approach 1.

**Interpretation:** Apply the nine verified KTP-alignment corrections as one
coherent documentation change in an isolated workspace. Correct current
canonical artifacts directly, mark historical records non-destructively, and
hold the currently served Presenter/Audience demo unchanged until the founder
reviews a separate documentation preview.

**Decision status:** Confirmed design direction. The implementation boundary
excludes tests, fixtures, scenarios, evidence bundles, controllers, containers,
Envoy configuration, laboratory configuration, and live services. Existing
validation may later be run read-only; any test that encodes superseded wording
creates a new approval gate rather than authority to change the test.

**Rationale:** Atomic correction prevents the paper, architecture, extension,
and public narrative from contradicting one another. Isolation prevents
documentation work from altering the current demonstration or laboratory
state, and preserves a clean founder comparison before publication.

**Affected artifacts:**

- planned direct-correction scope: canonical paper, hybrid architecture and
  editable source, extension overview, Presenter/Audience source and design,
  current project navigation, and any other current artifact with a verified
  semantic conflict
- planned notice-only scope: historical designs, implementation plans, and
  checkpoints containing superseded KTP language
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- no runtime, test, or laboratory artifact

**Unresolved questions:** Approval of the exact nine-change propagation model,
review flow, and failure handling before the written design specification.

**Next gate:** Founder reviews and approves the per-requirement propagation
model; then complete the design's verification and preview section.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-142 — 2026-09-01 — Ambient breach retained as the urgency-defining phase change

**Input:** The founder rejected a minimized definition of ambient breach as
only an action without verified trust or an epistemic `A > E` condition.
Ambient breach is also the current state of cybersecurity evolution: the
inability to distinguish service from attack. Ambient threat marked the prior
threshold, crossed when frontier models demonstrated autonomous vulnerability
discovery and exploitation at machine rates.

**Interpretation:** Define ambient breach at two inseparable scales. At the
action scale, it includes acting without verified trust and specific
unsupported-authority conditions. At the systemic scale, it names the security
epoch in which authentic-looking service activity and adversarial activity use
the same credentials, interfaces, transports, and automation patterns quickly
enough that their operational distinction cannot be assumed before execution.
The action-scale expression illustrates the broader condition; it does not
exhaust or narrow it.

**Decision status:** Founder correction confirmed. Primary-source support is
available from the July 2026 OpenAI disclosure, which reports autonomous
discovery and exploitation of a previously unknown vulnerability, chained
real-world attack paths, and sustained multistep cyber operations, and from the
Hugging Face technical timeline, which reconstructs approximately 17,600
machine-speed attacker actions across a multiday campaign. These sources
support the ambient-threat threshold and urgency while the term `ambient
breach` remains the KIL paper's explicit analytical thesis.

**Rationale:** KIL's urgency rests on a changed operating condition, not merely
on a new decision predicate. Reducing ambient breach to one formula would erase
the central reason ambient enforcement is needed: defenders can no longer rely
on service appearance, valid credentials, or human-speed retrospective
classification to distinguish benign execution from autonomous attack before
consequence.

**Affected artifacts:**

- planned main-paper introduction and section 1.2
- planned Presenter/Audience primer and incident transition language
- planned extension and architecture explanatory labels where the urgency
  thesis is summarized
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- no test, laboratory, evidence, or live-runtime artifact

**Unresolved questions:** Founder approval of the exact two-scale definition
and the risk-to-threat-to-breach-to-enforcement progression before the written
design specification.

**Next gate:** Present the revised ambient-breach language for approval, then
complete the verification and preview portion of the documentation design.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-143 — 2026-09-01 — Two-scale ambient-breach definition approved

**Input:** The founder approved the revised ambient-breach definition and its
progression from ambient risk through ambient threat and ambient breach to
ambient enforcement.

**Interpretation:** The authoritative KIL definition now combines the systemic
condition—the inability to distinguish service from attack before consequence
at machine speed—with action-level manifestations such as execution without
verified trust or authority unsupported by current conditions. Neither scale
may be presented as the complete concept without the other.

**Decision status:** Confirmed. The systemic phase change is the foundation of
KIL's urgency. The action-level KTP expression supplies enforceable mechanics
without shrinking the broader cybersecurity thesis. Primary 2026 OpenAI and
Hugging Face disclosures support the transition into ambient threat; ambient
breach remains the KIL paper's named analytical conclusion from that changed
operating condition.

**Rationale:** The approved framing preserves both meaning and rigor. It avoids
claiming universal continuous compromise while rejecting the weaker assumption
that authenticated service appearance can establish benign intent before
machine-speed consequence.

**Affected artifacts:**

- planned main-paper introduction and section 1.2
- planned Presenter/Audience primer and incident transition
- planned architecture and extension explanatory language
- future supersession notices where earlier text narrows the definition
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- no test, laboratory, evidence, or live-runtime artifact

**Unresolved questions:** Approval of the isolated documentation preview,
verification, protected-path, and failure-handling gates.

**Next gate:** Founder reviews the final design section. On approval, write,
commit, and self-review the formal design specification for founder review.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-144 — 2026-09-01 — Authoritative KTP alignment specification written

**Input:** The founder approved the canonical-first propagation architecture,
the nine-change alignment contract including the two-scale ambient-breach
definition, and the isolated verification and preview design.

**Interpretation:** Persist the complete approved design before implementation.
The specification must reproduce the expert requirements, identify controlling
primary sources, distinguish direct correction from historical supersession,
and make test/laboratory/live-service exclusions enforceable through a
protected-path gate.

**Decision status:** Written design complete and self-reviewed. No placeholders
remain; the current-versus-historical boundary is explicit; the immutable KTP
v2.0.0 tag is distinguished from later canonical citation metadata; failure
handling stops on source conflict, protected-path changes, test wording
conflicts, or required live-service modification. Only the new specification
and append-only lineage entries changed.

**Rationale:** A committed design makes the expert review durable and prevents
implementation from becoming a sequence of context-dependent wording edits.
It also preserves the founder's explicit prohibition on modifying the test or
live environments while allowing current documentation to be corrected and
previewed in isolation.

**Affected artifacts:**

- `docs/superpowers/specs/2026-09-01-kil-ktp-authoritative-alignment-design.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- no paper, architecture, demo, test, laboratory, evidence, or live-runtime
  artifact

**Unresolved questions:** Founder review of the written specification is
required before an implementation plan may be created.

**Next gate:** Commit the specification and lineage, ask the founder to review
the written file, and wait. On approval, invoke the planning workflow; do not
begin implementation directly.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-145 — 2026-09-01 — Counterfactual-first Envoy composition resumed under authoritative KTP semantics

**Input:** The founder resumed from the 2026-08-31 shutdown checkpoint at the
final approval gate for the refined counterfactual-first Envoy laboratory
composition.

**Interpretation:** Preserve the approved three-band narrative—observed
incident, controlled Envoy model, bounded KIL counterfactual—but reconcile its
labels with the subsequently confirmed KTP-alignment contract before requesting
final composition approval. In particular, the preview must preserve ambient
breach as both the systemic inability to distinguish service from attack before
consequence and an action-level unsupported-authority manifestation; describe
the KTP result as supervision plus tighten-only constraints; identify HTTP 403
as a derived Envoy transport effect rather than a KTP wire decision; and retain
the evidence boundary between observed, modeled, and pending validation.

**Decision status:** Refined composition prepared for founder review; final
composition approval remains pending. The preview is an untracked,
conversation-scoped design artifact with SHA-256
`9cf1bb01b4febc11b164f52b32eef4b2e4c3a1426fcd3ea9e6f44d9cb2d0b8e6`.
No canonical paper, Presenter/Audience page, test, laboratory configuration, or
live service was changed.

**Rationale:** The macro composition was already selected, but the checkpoint
predated the authoritative KTP corrections. Reconciliation at the design gate
prevents the eventual diagram from reintroducing superseded decision semantics
or narrowing the ambient-breach thesis while preserving the founder's explicit
restriction against changing the current demo or laboratory before approval.

**Affected artifacts:**

- conversation-scoped preview
  `kil-counterfactual-first-envoy-composition.html`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- no canonical diagram, demo, paper, test, evidence, laboratory, or live-runtime
  artifact

**Unresolved questions:** Founder approval or revision of the reconciled
three-band composition, including its KTP-result language and evidence labels.

**Next gate:** On founder approval, write and commit the formal Envoy-lab
diagram design specification, self-review it, and request founder review before
creating an implementation plan.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-146 — 2026-09-01 — Reconciled counterfactual-first composition approved and specified

**Input:** The founder approved the displayed counterfactual-first Envoy
laboratory composition reconciled with the authoritative KTP-alignment design.

**Interpretation:** Convert the approved visual review into a durable design
specification before implementation. The specification controls both the
standalone diagram and synchronized Presenter/Audience scene, preserves the
observed/modeled/pending evidence boundary, treats HTTP results as derived
Envoy effects, keeps KTP supervision and tighten-only constraints normative,
and retains the two-scale ambient-breach thesis.

**Decision status:** Composition confirmed and written specification complete.
Implementation remains unapproved pending founder review of the committed
written specification. No Presenter/Audience source, canonical paper, test,
laboratory configuration, evidence bundle, or live service changed.

**Rationale:** The visual approval resolves the final composition gate from the
shutdown checkpoint. A written specification now makes the exact narrative,
topology mapping, evidence language, KTP semantics, accessibility requirements,
and protected-path constraints independently reviewable before an
implementation plan exists.

**Affected artifacts:**

- `docs/superpowers/specs/2026-09-01-envoy-lab-counterfactual-first-diagram-design.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- no canonical diagram, demo, paper, test, evidence, laboratory, or live-runtime
  artifact

**Unresolved questions:** Founder review of the written specification and any
requested corrections before implementation planning.

**Next gate:** Commit the specification and lineage. After founder approval of
the written file, create the implementation plan; do not implement directly.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-147 — 2026-09-01 — Presenter/Audience graphic overhaul queued after current diagram gate

**Input:** The founder stated that the current Presenter/Audience graphics need
to be redone in a more vivid, graphic-intensive format and directed that the
visual redesign be iterated after the current counterfactual-first diagram step
completes.

**Interpretation:** Preserve the visual-overhaul requirement as the next
separate design phase. Do not expand the current diagram-specification commit
into a production demo rewrite, and do not modify the currently served demo,
tests, or laboratory while closing the present written-specification gate.

**Decision status:** Future design objective confirmed; visual direction and
scene-by-scene implementation remain unselected. The current step remains
limited to the approved Envoy diagram specification and specialist lineage.

**Rationale:** Separating the work prevents an unreviewed aesthetic overhaul
from obscuring the already approved evidence and KTP-semantic contract. The
next visual phase can pursue a substantially more vivid style while treating
the current specification's claim boundaries as non-negotiable content
constraints.

**Affected artifacts:**

- future design scope: `docs/demo/kil-presenter-audience-demo.html` and its
  standalone or synchronized visual derivatives
- current turn: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md` only
- no current demo, test, evidence, laboratory, or live-runtime artifact

**Unresolved questions:** The graphic-intensive visual language, degree of
animation, scene composition, asset strategy, and approval sequence for the
Presenter/Audience overhaul.

**Next gate:** Finish and obtain founder review of the counterfactual-first
diagram specification. Then begin a separate visual-design iteration before
changing the Presenter/Audience implementation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-148 — 2026-09-01 — Executive narrative added to the counterfactual specification

**Input:** The founder approved the written counterfactual-first specification
and supplied a controlling narrative introduction explaining why the Envoy
breach comparison is being demonstrated.

**Interpretation:** Place the full founder-supplied narrative before the
technical composition and make its three transitions explicit for the
standalone and synchronized forms: detection is insufficient at adversarial-AI
speed; ambient breach establishes the operating urgency; and ambient
enforcement moves mitigation into kinetic infrastructure. Preserve the phrase
`pervasive, continuous ambient breach` while binding it to the already approved
systemic definition rather than an assertion of universal continuous
compromise.

**Decision status:** Narrative content confirmed and incorporated into the
written design. The diagram composition, evidence contract, KTP semantics, and
no-lab-change boundary remain unchanged. Implementation planning remains gated
on founder review of the revised written specification.

**Rationale:** An executive audience needs the changed cybersecurity condition
before it can understand why a transport-layer counterfactual matters. The
introduction supplies that urgency while the adjacent interpretive boundary
prevents the phrase `continuous ambient breach` from being misconstrued as an
unsupported claim that every system is always compromised.

**Affected artifacts:**

- `docs/superpowers/specs/2026-09-01-envoy-lab-counterfactual-first-diagram-design.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- no demo, test, paper, evidence, laboratory, or live-runtime artifact

**Unresolved questions:** Founder review of the revised written specification
before implementation planning and the subsequent separate design iteration
for the vivid Presenter/Audience graphic overhaul.

**Next gate:** Commit and verify the revised specification. After founder
approval, create the implementation plan; do not modify the Presenter/Audience
demo or laboratory directly.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-149 — 2026-09-01 — Counterfactual-first diagram implementation plan written

**Input:** The founder confirmed the revised counterfactual-first specification,
including its executive narrative introduction, and authorized progression to
implementation planning.

**Interpretation:** Convert the confirmed design into a test-first,
protected-path implementation plan without changing the current demo, any
existing test, or the laboratory. Keep the graphic-intensive Presenter/Audience
overhaul outside this plan; first implement the approved semantic baseline as a
standalone executive diagram and one synchronized lab-mapping scene.

**Decision status:** Implementation plan written and self-reviewed; execution
approach remains pending founder selection. The plan creates a new isolated
documentation contract only after explicit execution approval, preserves all
existing tests, uses read-only Brave/Playwright verification, and prohibits any
V3B-1 start or central run.

**Rationale:** Bite-sized tasks and frequent commits make the evidence and KTP
boundaries reviewable independently of the later aesthetic redesign. A strict
path allowlist prevents a presentation change from mutating scenarios,
adapters, laboratory controls, evidence, or live services.

**Affected artifacts:**

- `docs/superpowers/plans/2026-09-01-envoy-lab-counterfactual-first-diagram.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- no demo, test, paper, evidence, laboratory, or live-runtime artifact

**Unresolved questions:** Founder selection of subagent-driven or inline plan
execution and explicit authorization to create the new isolated documentation
contract test during Task 1.

**Next gate:** Commit the plan and lineage, then obtain the founder's execution
choice. Execution must stop before any existing test or protected laboratory
path would change.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-150 — 2026-09-01 — Counterfactual-first Envoy semantic baseline implemented and verified

**Input:** The founder selected option 1 for execution of the approved
counterfactual-first Envoy plan. That selection was explicit execution
approval to create the new isolated documentation contract test while
preserving the prohibition on modifying any existing test, laboratory,
evidence, source, adapter, controller, container, scenario, schema, or live
service. The final gate also clarified that the authoritative-alignment and
counterfactual-design specifications in commits `aa9961c`, `1f3b9da`, and
`fc14c03` are approved pre-implementation design history; implementation-only
path protection therefore begins at plan commit `081ea32`.

**Interpretation:** Implement the confirmed semantic baseline in two forms: a
passive standalone executive presentation and the synchronized
Presenter/Audience lab-mapping scene. Both deliverables separate the published
incident sequence as **observed**, the isolated Envoy process contract and
`0.95` local reduction as **modeled**, and an accepted V3B-1 live enforcement
result as **pending validation**. The KTP result is supervision plus
tighten-only constraints. The `200 / 200 / 403` HTTP outcomes are derived by
the Envoy adapter and are not a KTP wire decision.

**Decision status:** Implementation and repository verification are complete;
founder acceptance of the semantic baseline remains pending. The standalone
and synchronized deliverables are present, responsive, passive, accessible,
and protected by the new isolated source contract and read-only browser
verification. No live/current laboratory or V3B-1 service was started,
modified, or exercised, and no central `run` command was invoked. This entry
does not claim that the historical breach was prevented or that pending V3B-1
validation has occurred.

**Rationale:** The implementation preserves the approved claim boundary while
making the same counterfactual legible in standalone and synchronized modes.
The first responsive review found the Envoy tracks did not stack correctly at
the `641px` tablet boundary; commit `6d4631a` corrected that layout. Mobile
review also found that the inline mapping lost essential semantic and evidence
content; commits `dea594f` and `b22a99b` added and contract-protected the
dedicated mobile mapping. Review-only screenshots were generated at:

- `artifacts/generated/kil-counterfactual-preview/standalone-1440.png`;
- `artifacts/generated/kil-counterfactual-preview/standalone-736.png`;
- `artifacts/generated/kil-counterfactual-preview/standalone-360.png`;
- `artifacts/generated/kil-demo-preview/case-first-divergence.png`;
- `artifacts/generated/kil-demo-preview/case-three-tracks.png`;
- `artifacts/generated/kil-demo-preview/case-lab-mapping.png`; and
- `artifacts/generated/kil-demo-preview/case-lab-mapping-mobile.png`.

The review disposition after those fixes was acceptable for the semantic
baseline: the three evidence classes remained visible, the mapped action and
derived cutoff remained unambiguous, and pending validation did not appear
validated. The screenshots remain ignored, untracked review artifacts.

Fresh verification from the final gate was:

- focused contracts:
  `PYTHONPATH=src "/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python" -m unittest tests.test_envoy_counterfactual_diagram tests.test_presenter_audience_demo -v`
  returned `Ran 19 tests in 0.010s` and `OK`;
- complete repository suite:
  `PYTHONPATH=src "/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python" -m unittest discover -s tests -v`
  returned `Ran 504 tests in 27.868s` and `OK`;
- standalone browser verification:
  `env NODE_PATH=/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules /Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node tools/verify_envoy_counterfactual_diagram.mjs`
  returned `envoy counterfactual verifier (Brave): PASS`;
- synchronized browser verification:
  `env NODE_PATH=/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules /Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node tools/verify_presenter_audience_demo.mjs`
  returned `presenter-audience browser verifier (Brave): PASS`; and
- `git diff --check` returned no errors. The full branch audit
  `git diff --name-only b49fe10..HEAD` contained the seven implementation
  allowlist paths plus the two approved pre-plan specification artifacts
  `docs/superpowers/specs/2026-09-01-envoy-lab-counterfactual-first-diagram-design.md`
  and
  `docs/superpowers/specs/2026-09-01-kil-ktp-authoritative-alignment-design.md`.
  The protected implementation-only audit from `081ea32` contained exactly the
  seven allowed paths: `README.md`,
  `docs/demo/envoy-lab-counterfactual-first.html`,
  `docs/demo/kil-presenter-audience-demo.html`,
  `tests/test_envoy_counterfactual_diagram.py`,
  `tools/verify_envoy_counterfactual_diagram.mjs`, this lineage, and the
  implementation plan.

**Affected artifacts:**

- `README.md`
- `docs/demo/envoy-lab-counterfactual-first.html`
- `docs/demo/kil-presenter-audience-demo.html`
- `tests/test_envoy_counterfactual_diagram.py`
- `tools/verify_envoy_counterfactual_diagram.mjs`
- `docs/superpowers/plans/2026-09-01-envoy-lab-counterfactual-first-diagram.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored review screenshots under `artifacts/generated/`

**Unresolved questions:** Founder acceptance or revision of the implemented
semantic baseline. The requested vivid, graphic-intensive redesign of the
broader Presenter/Audience experience remains unresolved and outside this
implementation scope; its visual language, animation, scene composition, and
asset strategy have not been selected.

**Next gate:** Present the standalone diagram and synchronized scene for founder
acceptance. Do not push, merge, start V3B-1, replace the public showcase, or
begin the vivid Presenter/Audience redesign until the founder accepts the
semantic baseline and chooses the next action.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

### T-151 — 2026-09-01 — Semantic baseline cleared for synchronized shutdown handoff

**Input:** After Tasks 1–5 and the final independent review completed, the
founder directed that all remaining work be committed, the local feature branch
be synchronized with GitHub, the repository be prepared for shutdown, and the
best next-session starting point be identified.

**Interpretation:** Preserve the completed semantic baseline on its named
feature branch and push that branch for durable backup without merging it into
`main`, replacing the public showcase, or exercising the laboratory. Write a
shutdown checkpoint that makes the founder-review gate and the subsequent
graphic-intensive redesign boundary explicit.

**Decision status:** Final independent review returned `READY FOR FOUNDER
REVIEW` with no blocking findings. The founder's new synchronization direction
supersedes T-150's temporary no-push gate only for publishing the named feature
branch as a backup. Founder acceptance of the semantic baseline, merge, public
showcase replacement, V3B-1 execution, and the visual redesign remain pending.

**Rationale:** A remotely synchronized feature branch and a self-contained
checkpoint make shutdown recoverable without weakening the evidence boundary
or implying that modeled results have become live validation. Keeping the
worktree and branch intact preserves a reviewable surface for founder feedback.

**Affected artifacts:**

- `docs/checkpoints/2026-09-01-counterfactual-semantic-baseline-shutdown.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- feature branch `codex/v3b1-foreign-snapshot-contract`
- no laboratory, evidence bundle, source module, adapter, deployment, or live
  service

**Unresolved questions:** Founder acceptance or revision of the standalone and
synchronized semantic baseline. After acceptance, the visual language,
animation policy, scene composition, and asset strategy for the vivid
Presenter/Audience redesign remain to be designed.

**Next gate:** Resume with founder review of the standalone three-band artifact
and the synchronized `case-lab-mapping` scene. If accepted, begin a separate
visual-design specification that treats the current semantic and evidentiary
contracts as fixed inputs. Do not start the laboratory or merge into `main`
without a separate founder direction.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
