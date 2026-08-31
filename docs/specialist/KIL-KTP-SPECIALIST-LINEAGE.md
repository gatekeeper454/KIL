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
