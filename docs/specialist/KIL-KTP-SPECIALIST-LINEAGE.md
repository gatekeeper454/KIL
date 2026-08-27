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

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
