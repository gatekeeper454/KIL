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

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
