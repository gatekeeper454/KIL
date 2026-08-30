# KIL Lab and Demo Validation Design

**Status:** Approved direction; design baseline for founder review  
**Date:** 2026-08-29  
**Scope:** Deterministic replay first, followed by live local-cluster validation

## 1. Purpose

The KIL lab is the evidence-producing counterpart to the official white paper.
It must determine what the proposed Kinetic Infrastructure Layer actually does
under controlled conditions, not merely illustrate what the architecture is
intended to do.

The lab has two ordered rails:

1. a deterministic, offline replay that makes the model, provenance, decisions,
   and counterfactual assumptions reviewable; and
2. a live local-cluster rail that exercises the same decision contract against
   real workload actions and measures enforcement behavior.

The offline rail can validate implementation behavior and replay
reproducibility. It cannot validate that KIL would have prevented the historical
Hugging Face incident. The live rail can validate locally reproduced behavior;
it likewise cannot convert a historical counterfactual into an observed fact.

## 2. Goals

- Implement one deterministic decision contract shared by replay and live
  enforcement.
- Test the proposed `Q_i,c` signed, short-lived composite KTP enforcement state
  without treating it as a competing trust system.
- Compare an explicitly defined credential-and-policy control with KIL under the
  same action sequence.
- Test both signed-state-only consumption and a bounded local reducing-only
  overlay without prematurely standardizing the overlay.
- Produce self-contained, integrity-verifiable run bundles from which the paper
  can generate tables, figures, and claims.
- Measure security behavior, safety behavior, reproducibility, and enforcement
  cost.
- Make negative, ambiguous, and falsifying results publishable rather than
  suppressing them.

## 3. Non-goals

- Reconstructing Hugging Face private telemetry or claiming knowledge beyond its
  public disclosure.
- Reproducing the original exploit payloads, compromising a real service, or
  connecting the lab to production systems.
- Treating anomaly detection alone as authorization.
- Allowing KIL to expand a KTP environmental envelope or override an immutable
  KTP veto.
- Selecting final production thresholds from one incident.
- Claiming eBPF, SmartNIC, SDN, or service-mesh enforcement until that substrate
  is actually implemented and measured.

## 4. Evidence and claim contract

Every input field, event, decision, metric, and paper claim has one evidence
class:

- `observed`: directly supported by an identified primary source;
- `modeled`: synthetic context, a counterfactual assumption, an illustrative
  parameter, or output derived from those inputs; or
- `validated`: reproduced locally by a named lab run whose bundle passes schema,
  integrity, and provenance checks.

Evidence classes do not automatically propagate upward. A decision computed
correctly from modeled input remains a modeled historical counterfactual even
when the implementation that computed it is locally validated.

The following language rules apply to the paper and demo:

| Evidence | Permitted formulation | Prohibited formulation |
|---|---|---|
| Observed | “Hugging Face reports…” | “KIL observed…” |
| Modeled | “Under profile P, the replay predicts denial…” | “KIL prevented the incident…” |
| Validated | “Run R reproduced denial in the local cluster…” | “This proves the historical incident would have been prevented…” |

## 5. System under test

### 5.1 Authoritative, slower loop

The authoritative loop consumes KTP-derived identity, trajectory, standing,
environment, constraint, and freshness inputs. It emits a signed, short-lived,
identity- and authority-class-bound composite state `Q_i,c` plus provenance:

- subject identity and workload class;
- authority class;
- composite charge and threshold profile identifier;
- KTP environmental-envelope reference;
- immutable constraint or veto references;
- evidence horizon and issuer time;
- not-before and expiry times;
- issuer, key identifier, signature profile, and state identifier;
- model, parameter, and schema versions.

Only the authoritative loop may increase composite authority. A later extension
profile will select a concrete signature encoding after confirming compatibility
with KTP v2.0.0; the deterministic interface remains algorithm-neutral.

### 5.2 Fast enforcement loop

For every action request, the fast loop evaluates:

```text
permit = veto_clear
      ∧ action_within_environment
      ∧ composite_state_authentic
      ∧ composite_state_fresh
      ∧ Q_effective(i,c) ≥ tau_c
      ∧ history_count(i,c) ≥ h_c
```

The result is one of:

- `permit`: short-lived, action-bound execution may proceed;
- `constrain`: execution may proceed only inside a strictly smaller authority
  set already permitted by KTP;
- `deny`: the requested action does not proceed; or
- `indeterminate`: required evidence or verification is unavailable and the
  configured fail-safe profile determines the constrained outcome.

Every result emits a deterministic decision record. A decision record contains
the evaluated inputs, evidence labels, state and request identifiers, reason
codes, effective authority, timestamps, implementation version, and integrity
digest.

### 5.3 Experimental enforcement modes

The lab compares two KIL modes:

1. `signed_state_only`: the fast loop consumes the latest valid signed state and
   cannot derive a new trajectory penalty between refreshes.
2. `signed_plus_local_reduce`: fresh local evidence may immediately clamp
   `Q_effective` downward or withhold authority until the next signed refresh.

The local overlay has four invariants:

- it cannot increase `Q_i,c`;
- it cannot clear a KTP veto;
- it cannot expand the environmental envelope; and
- it expires or reconciles against the next authentic signed state while its
  provenance remains auditable.

Comparing these modes tests the value and safety cost of fast local reduction.
It does not decide the overlay's final normative status in KTP 2.1 or 3.0.

## 6. Trust-decay validation profile

The first profile uses a weighted diagonal standardized distance. It is not
described as a full Mahalanobis distance because it does not initially model
feature covariance.

For feature vector `x_t`, class baseline mean `mu_c`, scale `sigma_c`, and
non-negative weights `w_c`:

```text
d_raw = sqrt(sum_j(w_c,j * ((x_t,j - mu_c,j) / sigma_c,j)^2))
d_t   = 2 / (1 + exp(-k_c * d_raw)) - 1
```

The authoritative pre-action charge passively decays over elapsed time:

```text
Q_decay = Q_previous * exp(-lambda_c * delta_t)
```

An over-threshold event yields a superlinear reducing penalty:

```text
loss(d_t) = rho_loss,c * (d_t / theta_c)^p     when d_t > theta_c
```

In `signed_plus_local_reduce` mode:

```text
Q_effective = clamp(Q_decay - loss(d_t) - coupled_loss, 0, Q_max)
```

A request cannot earn the authority needed to authorize itself. Positive
replenishment is credited only by the authoritative loop after successful,
low-divergence behavior is confirmed. Local observations can reduce authority;
they cannot replenish it.

The profile tests independent charge by authority class, minimum low-divergence
history, higher-class passive decay, downstream coupling, cold-start class
priors, and declared trajectory changes. All initial weights, thresholds,
decay constants, coupling coefficients, and priors are versioned modeled inputs.

## 7. Control and comparisons

The control is named `credential_policy_baseline`. It is not presented as every
possible zero-trust architecture. For each action it evaluates only the
credential validity and explicit policy facts encoded in the scenario:

```text
permit_baseline = credential_valid ∧ policy_allows_action
```

Each replay event is evaluated by the baseline, `signed_state_only`, and
`signed_plus_local_reduce` modes. All modes receive the same observed action and
credential facts. KIL-only context features are separately labeled modeled.

The comparison reports:

- first denied or constrained event;
- downstream actions rendered unreachable by the scenario dependency graph;
- false denials on benign controls;
- decisions changed by the local overlay;
- stale-state and refresh-window exposure;
- reason-code and provenance completeness; and
- computational and live enforcement latency.

## 8. Scenario model

The historical scenario is a normalized, source-cited action graph rather than
a prose transcript. Each event includes:

- stable event identifier and phase;
- logical and disclosed wall-clock time, when available;
- actor, credential, authority class, action, resource, and dependency IDs;
- observed source citation and location note;
- credential-validity and policy-control facts;
- modeled KTP context features with explicit rationale;
- expected control result and expected KIL result under a named profile; and
- confidence, ambiguity, and omission notes.

The initial representative cut points are:

1. worker identity addressing the Kubernetes API;
2. credential use from a novel external origin;
3. privileged workload admission;
4. high-scope secret-object access;
5. cross-cluster administrative use;
6. repeated mesh-enrollment behavior;
7. newly minted signed identity use; and
8. source-control and CI-directed action.

Only facts present in the Hugging Face technical timeline are observed. Paths,
feature values, baselines, thresholds, and KTP signals absent from the disclosure
are modeled and must not be silently reconstructed.

## 9. Deterministic replay rail

The replay rail is a pure, offline pipeline:

```text
scenario manifest
  -> normalized events
  -> versioned state/profile inputs
  -> baseline and KIL decision engines
  -> JSONL decision records
  -> summary metrics and claim-evidence matrix
  -> integrity manifest
```

Determinism requires canonical event ordering, explicit clocks, decimal or
rational handling where floating-point ambiguity affects thresholds, stable
serialization, fixed profile versions, and no network or wall-clock dependency.
Two executions of the same inputs and implementation commit must produce the
same semantic output and integrity digest.

## 10. Live local-cluster rail

The live rail reuses the same request, state, decision, reason-code, and record
schemas. It contains:

- benign workload generators that establish permitted trajectories;
- adversarial workload generators that request representative escalation
  actions without using destructive payloads;
- an authoritative state issuer or deterministic issuer fixture;
- an enforcement adapter at the selected Kubernetes boundary;
- an append-only decision collector; and
- a run controller that captures environment and timing metadata.

The founder selected an Envoy HTTP `ext_authz` gateway as the first live
adapter. It optimizes for observability, reproducibility, and clear
pre-execution denial rather than claiming the deepest possible transport
placement. The three comparison modes run as separately configured tracks so a
client cannot select or downgrade enforcement. Kubernetes admission, network,
and eBPF enforcement remain later gates. The complete approved topology,
evidence join, safe workload, signed-state fixture, measurement protocol, and
graphical diagram are specified in
[the Gate V3 Envoy design](2026-08-29-v3-envoy-live-validation-design.md).

## 11. Failure and safety experiments

The lab must exercise, not merely describe:

- absent, malformed, expired, not-yet-valid, revoked, and incorrectly signed
  composite state;
- state replay and identity, class, action, or environment binding mismatch;
- evidence staleness and control-plane partition;
- cold start and insufficient history;
- slow drift and single high-divergence events;
- a legitimate rare action with and without a declared trajectory change;
- local overlay false reduction and recovery at signed refresh;
- an immutable veto and environmental-envelope violation;
- attempted local authority increase; and
- decision-record loss or integrity failure.

Fail-safe behavior is defined by authority class. Administrative,
privilege-escalation, token-minting, and secret-bulk-read classes fail closed.
Lower-risk operational classes may fail constrained only inside a predeclared
safe envelope. No failure mode fails into greater authority.

## 12. Metrics

### Security behavior

- first cutoff event and phase;
- permitted, constrained, denied, and indeterminate counts;
- prevented dependency descendants;
- stale-state exposure window;
- overlay incremental cutoff value; and
- invariant violations, which must remain zero.

### Operational behavior

- benign permit rate and false-denial rate;
- declared-change success and recovery time;
- decision latency at p50, p95, and p99;
- signed-state refresh latency and age at decision;
- decision throughput; and
- record completeness and integrity-verification rate.

Latency is reported only for the measured hardware, runtime, adapter, profile,
sample size, and run identifier. It is not generalized to SmartNIC, eBPF, SDN,
or production-scale performance.

## 13. Run bundle and publication linkage

Each run produces an immutable directory containing:

- `manifest.json`: run ID, timestamps, commit, environment, profile, modes, and
  artifact hashes;
- `scenario.json`: normalized action graph and provenance;
- `state.jsonl`: issued composite states and refresh events;
- `decisions.jsonl`: baseline and KIL decisions;
- `metrics.json`: machine-readable measurements;
- `summary.md`: human-readable findings and limitations; and
- `SHA256SUMS`: integrity hashes for every published artifact.

Every paper table, chart, and validated sentence cites a run ID and artifact
path. Modeled historical figures cite both the source scenario version and model
profile. Generated PDF content must never be the sole repository of a result.

## 14. Acceptance gates

### Gate V1 — Deterministic kernel

- arithmetic boundary, decay, monotonicity, class isolation, coupling, and
  reducing-only tests pass;
- the local overlay cannot increase authority under generated test inputs;
- invalid or stale signed states cannot produce greater authority; and
- repeated runs yield identical semantic output and hashes.

### Gate V2 — Historical replay

- every observed event has a primary-source citation;
- every synthetic feature and parameter is labeled modeled;
- baseline and KIL modes consume the same normalized action facts;
- the replay emits complete decision provenance; and
- paper-ready results retain the historical-counterfactual caveat.

### Gate V3 — Live local validation

- benign and adversarial trajectories execute in an isolated local cluster;
- enforcement occurs before the representative consequential action completes;
- decision records correspond to observable workload outcomes;
- failure and safety cases are reproduced; and
- published results include environment, repetitions, distributions, and run
  identifiers.

### Gate V4 — Publication promotion

- a claim-evidence review confirms every `validated` statement points to a
  passing run bundle;
- source and artifact integrity checks pass;
- negative and ambiguous outcomes are retained; and
- the white paper, demo, and repository use consistent terminology and figures.

## 15. Implementation sequencing

The deterministic rail is one independently testable subsystem and is
implemented first. The live-cluster rail is a second subsystem built only after
the decision interface and replay schemas are stable. Test-first development is
mandatory: each behavior begins with a focused failing test, is implemented
minimally, and is verified against the full suite before the next behavior.

## 16. Authoritative sources

- [KTP RFC series, version 2.0.0](https://github.com/nmcitra/ktp-rfc/tree/v2.0.0)
- [Enterprise KTP architecture](https://kinetic-trust-protocol.net/enterprise/architecture)
- [The Constitution of Digital Physics](https://kinetic-trust-protocol.net/learn/constitution)
- [Hugging Face technical incident timeline](https://huggingface.co/blog/agent-intrusion-technical-timeline)

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
