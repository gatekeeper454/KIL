# KIL specialist-consultation checkpoint

Status: **Paused for specialist consultation**

This checkpoint freezes the project's accepted decisions, unresolved design
questions, evidence boundary, and exact resume point. It does not approve the
architecture draft or convert modeled counterfactuals into validated results.

## Decisions already accepted

- KIL will be a paired package: a publishable technical paper plus an executable
  reference implementation.
- The implementation will provide a deterministic, offline replay of the July
  2026 Hugging Face agent-intrusion disclosure and a live local Kubernetes
  validation rail.
- KIL is a KTP v2 reference implementation with a narrowly scoped extension
  proposal. It will not rename or duplicate existing KTP constructs.
- Public evidence is classified as `observed`, `modeled`, or `validated`.
  Synthetic KTP context signals are permitted only when explicitly labeled
  `modeled`; `validated` is reserved for behavior reproduced locally.
- KIL is an enforcement and experiment harness. ShadowClaw may provide risk
  telemetry across a stable interface but remains a separate detector project.
- Every authored project document cites the canonical KTP citation record.

## Design awaiting approval

**Architecture Section 1 is a draft, not an accepted specification.** The
current candidate is a hybrid, two-timescale enforcement model shared by the
offline replay and live transport adapter:

```text
permit = veto_clear ∧ A(action) ≤ E(environment) ∧ Q_i,c ≥ τ_c ∧ evidence_fresh
```

Here `Q_i,c` is a new KIL extension to KTP: an ephemeral, composite,
trajectory-derived enforcement state for identity `i` and authority class `c`.
It is derived from and constrained by existing KTP constructs rather than
forming a parallel trust system. Its proposed governance boundary is
reducing-only: it may constrain or withhold authority, but it may never override
a KTP veto or make an action fit the KTP envelope when
`A(action) ≤ E(environment)` is false.

The first implementation will express this as an extension profile for KTP
v2.0.0. Its future normative home may be KTP 2.1 if backward-compatible, or KTP
3.0 if adoption requires changes to core or wire semantics.

The saved visual companion is
[`../design-drafts/hybrid-two-timescale-architecture.html`](../design-drafts/hybrid-two-timescale-architecture.html).

## Questions for the specialist

1. **KTP alignment and terminology — resolved 2026-08-29:** `Q_i,c` is a new
   KIL extension derived from existing KTP constructs. The remaining work is to
   define the smallest extension boundary and determine whether its eventual
   normative expression belongs in KTP 2.1 or 3.0.
2. **Enforcement substrate:** Which first adapter best proves transport-native
   ambient enforcement without overstating what the prototype demonstrates:
   eBPF, Envoy/Istio, Kubernetes admission/network policy, SmartNIC, or SDN?
3. **Trust-decay mathematics:** Should the first implementation use a full
   covariance-aware Mahalanobis distance or a diagonal standardized distance?
   How should cold start, passive decay, replenishment, authority-class coupling,
   false positives, and adversarial slow drift be calibrated?
4. **Safety and recovery:** What behavior is appropriate for stale or missing
   evidence, control-plane partition, model failure, rare legitimate actions,
   emergency access, human override, and graceful degradation? Which paths must
   fail closed, fail constrained, or fail operational?
5. **Experimental validity:** What synthetic telemetry is acceptable in the
   historical replay, and what local experiments, controls, baselines, and
   sensitivity tests are needed before making latency or prevention claims?
6. **Governance and publication:** What authorship, licensing, conformance,
   compatibility, and adoption process should govern the reference
   implementation and extension proposal?

## Evidence and source-integrity record

- The two founder-supplied Markdown drafts remain byte-preserved in
  `docs/drafts/`; their hashes are pinned in
  `research/source-material/SHA256SUMS`.
- The complete visible 16-message Claude origin conversation is preserved in a
  public-safe JSON record. Hidden reasoning, tool exchanges, private account
  data, export URLs, and unrelated conversations are excluded from tracked Git.
- The original Claude export is retained under the gitignored
  `research/private/` tree.
- No historical counterfactual has been labeled `validated`.

## Exact resume point

Resume by reviewing **Architecture Section 1** and choosing one of three
outcomes: approve it, revise it using the specialist's findings, or replace it.
Only after that checkpoint should work continue through model/data flow, safety
and error handling, test design, specification writing, self-review, user
review, and the implementation plan.

Re-establish the saved baseline with:

```bash
make validate
shasum -a 256 -c research/source-material/SHA256SUMS
```

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
