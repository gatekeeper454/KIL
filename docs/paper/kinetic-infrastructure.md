# Kinetic Infrastructure

## Ambient Enforcement for Agent-Speed Cybersecurity

**Status:** Official KIL white-paper manuscript, prevalidation edition

**Protocol baseline:** Kinetic Trust Protocol v2.0.0

**Evidence state:** Architecture and model proposed; historical example modeled;
local validation in progress

## Executive summary

AI changes cybersecurity in two ways at once. It increases the speed, scale, and
adaptability available to defenders, while giving adversaries and compromised
agents the same advantages. Controls that depend on a request reaching a
checkpoint, a policy being evaluated, an alert being correlated, and a person or
automation reacting afterward inherit a timing disadvantage. The credential may
be authentic and the policy evaluation correct while the action around that
credential has become operationally impossible for the legitimate identity.

The Kinetic Infrastructure Layer (KIL) proposes **ambient enforcement**:
authorization continuously expressed and consumed as a property of
infrastructure-mediated action. KIL builds on the [Kinetic Trust Protocol (KTP)
v2.0.0][ktp-rfc-v2]. It introduces a narrowly scoped, signed, short-lived
composite KTP enforcement state, `Q_i,c`, bound to identity `i`, authority class
`c`, freshness, trajectory evidence, and the KTP environmental envelope. KIL
may reduce or withhold authority. It may never clear a KTP veto, expand the KTP
environmental envelope, or manufacture authority absent from KTP.

The architecture is hybrid and two-timescale. A slower authoritative loop
derives, signs, expires, and refreshes `Q_i,c`. A faster enforcement loop
evaluates each action at an infrastructure boundary. Two experimental modes
compare consumption of signed state alone with signed state plus local
reduction. Offline historical replay and live local-cluster validation are two
execution rails for this architecture; they are not the two timescales.

This paper applies the proposed model to Hugging Face's public account of the
July 2026 agent intrusion. The incident provides an unusually detailed example
of valid or forgeable credentials being used across novel origins, resources,
privilege levels, and action sequences. The analysis is a counterfactual, not a
claim of historical prevention. Reported incident facts are **observed**;
synthetic KTP context and predicted KIL decisions are **modeled**; only behavior
reproduced in the versioned local lab may be called **validated**.

## 1. Introduction

Cybersecurity is currently at an inflection point where reliance on static or
AI-assisted SOCs (Security Operations Centers) and traditional AI-augmented
controls is no longer sufficient to counter modern, adversarial AI.

To remain effective, the practice must transcend the legacy detect-and-prevent
paradigm and evolve into a state of ambient enforcement. We are transitioning
from a landscape of “ambient risk” and “ambient threat” into an era of
pervasive, continuous “ambient breach,” necessitating a shift toward autonomous,
real-time mitigation that functions at speed and scale independent of human
intervention.

Ambient enforcement represents this critical evolution by decoupling defense
from static, procedural constraints and utilizing kinetic infrastructure to
match the velocity of AI adversaries in real time. By leveraging the same
transport mechanisms as the threat itself and instantiating immutable controls
that enforce security through physics, we move toward a future where
cybersecurity functions not as a reactive overlay, but as an autonomous,
omnipresent force capable of neutralizing AI-driven threats with the same speed
and adaptability as the intelligence it seeks to contain.

> **Evidence note:** This founder-approved opening states the paper's thesis.
> Its empirical implications are hypotheses to be tested by the KIL lab. It is
> not itself a validated result.

### 1.1 The checkpoint problem

A simplified checkpoint architecture asks whether a credential is authentic
and whether policy allows the requested operation. That question remains
necessary, but it is no longer sufficient for autonomous systems. A stolen key,
replayed session, forged token, or overbroad service identity may pass the same
binary checks as its legitimate holder. The difference lies in the action's
trajectory: origin, sequence, resource novelty, privilege delta, cadence,
volume, and relation to the identity's established behavior.

KIL does not argue that every modern zero-trust implementation is merely a
static token gate. The lab uses an explicitly limited
`credential_policy_baseline` so that comparisons are falsifiable rather than
straw-man claims about an entire security discipline. KIL asks a narrower
question: what additional behavior becomes enforceable when current,
trajectory-derived KTP state is cryptographically bound to action execution at
the infrastructure boundary?

### 1.2 From ambient breach to ambient enforcement

“Ambient breach” describes an operating assumption, not a declaration that
every system is continuously compromised. In an AI-mediated environment,
attempted boundary crossing, credential abuse, capability discovery, and novel
action generation can occur continuously and at machine speed. Ambient
enforcement is the corresponding defensive posture: consequential actions
continuously encounter independently verifiable, action-bound constraints.

```text
detect anomalous activity -> investigate -> revoke or contain

                         becomes

verify current authority at execution -> permit, constrain, or deny -> record
```

Detection and the SOC remain important. KIL changes their relationship to
execution: they become sources of evidence, governance, recovery, and learning,
rather than the only mechanisms capable of stopping a consequential action.

## 2. KTP foundation and KIL extension boundary

KIL is grounded in the versioned [KTP RFC v2.0.0 release][ktp-rfc-v2]. The
official [Enterprise KTP architecture][ktp-architecture] provides the reference
for KTP's action-authorization plane, enforcement surfaces, “should” gate, verb
library, and least-trajectory framing. The [Constitution of Digital
Physics][ktp-constitution] supplies the principles against which KIL evaluates
graceful degradation, algorithmic accountability, environmental context, Blue
Zones, and immutable constraints.

KIL is not a replacement trust system. It is a proposed KTP extension profile
that makes one infrastructure-consumption contract explicit: a signed,
short-lived composite KTP enforcement state for identity `i` and authority
class `c`, written `Q_i,c`. Existing KTP constructs remain authoritative for
identity, trajectory, standing, context, environmental bounds, enforcement,
transport, audit, emergency behavior, and conformance. KIL adds the normative
composition, binding, freshness, reducing-only consumption, and decision-record
requirements needed by infrastructure enforcement points.

The initial reference profile targets KTP v2.0.0 through an explicit namespace.
A backward-compatible standards expression may fit KTP 2.1. A change to KTP
core invariants, mandatory processing, or wire semantics may instead require
KTP 3.0. The reference implementation cannot decide that governance question.

### 2.1 Non-expansion invariant

Let `A(action)` be requested action authority and `E(environment)` be the KTP
environmental envelope. KIL's central governance rule is:

```text
KIL_effective_authority <= KTP_authorized_authority
```

Consequently:

- `Q_i,c` cannot make `A(action) <= E(environment)` true when KTP says it is
  false;
- a KTP veto cannot be overridden by a high KIL score;
- local evidence may reduce or withhold authority but cannot replenish it; and
- missing, stale, or unverifiable state can never fail into greater authority.

## 3. Hybrid two-timescale architecture

The architecture contains two temporal loops and two execution rails. Keeping
these concepts separate is essential.

### 3.1 Authoritative signed-state loop

The slower loop combines KTP-derived inputs into `Q_i,c`, signs the state, and
sets its validity interval. A state binds at least identity, workload and
authority class, charge and threshold profile, KTP envelope and constraints,
evidence horizon, validity period, issuer, key, signature profile, unique state
identifier, and schema, model, and parameter versions.

This loop is the only component allowed to increase composite authority.
Positive replenishment follows confirmed low-divergence behavior and becomes
available only in a later authentic signed state. Silence does not preserve
standing privilege indefinitely: charge decays with time and state expires.

### 3.2 Fast enforcement loop

The faster loop evaluates every action request at the infrastructure boundary:

```text
permit = veto_clear
      AND action_within_environment
      AND composite_state_authentic
      AND composite_state_fresh
      AND Q_effective(i,c) >= tau_c
      AND history_count(i,c) >= h_c
```

The loop emits `permit`, `constrain`, `deny`, or `indeterminate`, together with a
deterministic provenance record. The implementation tests two modes:

1. **signed-state-only** consumes the latest authentic state and applies no new
   local trajectory penalty between refreshes;
2. **signed state plus local reduction** allows fresh local evidence to clamp
   `Q_effective` downward until reconciliation with the next signed state.

The second mode is experimental. Its local overlay cannot increase `Q_i,c`,
clear a veto, expand `E(environment)`, or outlive its reconciliation rules.
Testing its security value and operational cost does not grant it final
normative status.

### 3.3 Execution rails

The offline replay rail feeds versioned historical actions and modeled context
into the deterministic decision engine. The live rail feeds locally observed
workload actions into the same interface and connects the result to an actual
enforcement adapter. These are execution rails—not timescales.

The canonical architecture graphic is maintained as
[hybrid-two-timescale-architecture.html](../design-drafts/hybrid-two-timescale-architecture.html).

Gate V3 instantiates the live rail through three separately configured Envoy
external-authorization tracks. The graphical deployment view below distinguishes
the credential-policy control, signed-state consumption, and signed state plus
local reducing-only overlay. A validated denial requires a joined decision,
Envoy non-forwarding record, and absence of the target invocation marker.

![Gate V3 Envoy live-validation architecture](../architecture/v3-envoy-live-validation.svg)

## 4. Formal trust-decay profile

### 4.1 Identity, authority, action, and trajectory

An identity `i` is a workload, agent, service identity, device, or other
credential holder. An authority class `c` groups actions of comparable
consequence, such as assigned-data reads, other-resource reads, internal or
external egress, token minting, administration, and privilege escalation.

An action at time `t` is represented by feature vector `x_t`. The first profile
uses resource novelty, network-origin distance, privilege delta, temporal
anomaly, volume anomaly, and sequence anomaly. Baseline `B_i,c` is the versioned
distribution of confirmed behavior for identity `i` in class `c`. A cold-start
identity uses a workload-class prior and begins in a constrained probationary
state.

### 4.2 Divergence

The first reference profile uses a **weighted diagonal standardized distance**.
It is not a full Mahalanobis distance because feature covariance is not included
in this initial profile:

```text
d_raw = sqrt(sum_j(w_c,j * ((x_t,j - mu_i,c,j) / sigma_i,c,j)^2))
d_t   = 2 / (1 + exp(-k_c * d_raw)) - 1
```

`d_t` lies in `[0,1]`. Feature weights are non-negative and versioned by
authority class. Floors on `sigma` prevent undefined arithmetic. Missing
features follow an explicit profile and are never silently imputed as normal.

### 4.3 Passive decay and asymmetric loss

Between authoritative updates, charge decays exponentially:

```text
Q_decay(i,c) = Q_previous(i,c) * exp(-lambda_c * delta_t)
```

Higher-consequence classes may use shorter half-lives. When divergence exceeds
class threshold `theta_c`, the proposed loss is superlinear:

```text
loss(d_t) = rho_loss,c * (d_t / theta_c)^p    when d_t > theta_c
```

Under the local-reduction experiment:

```text
Q_effective(i,c) = clamp(
    Q_decay(i,c) - loss(d_t) - coupled_loss,
    0,
    Q_max
)
```

Replenishment is deliberately asymmetric. A legitimate action cannot earn the
authority needed to authorize itself. Confirmed low-divergence behavior may
contribute a small positive update in the authoritative loop, but only a later
signed state exposes that increase. Authority therefore arrives slowly and can
be lost quickly.

### 4.4 Class isolation, coupling, and declared change

Charge is maintained per authority class. A history of reading assigned data
cannot subsidize a first request to mint a token or administer a cluster. The
gate also requires a minimum count `h_c` of confirmed low-divergence history in
the requested class.

A severe divergence may reduce related higher-consequence classes through a
versioned, directed coupling graph:

```text
coupled_loss(c -> c') = kappa_c,c' * loss(d_t)
```

Real systems also change. An auditable trajectory-change declaration is bound
to identity, authority class, expected range, validity window, issuer, and
purpose. It widens only the declared range and never applies retroactively or to
an undeclared authority class.

### 4.5 Parameter status

Initial weights, squash factors, decay constants, thresholds, loss rates,
exponents, coupling coefficients, minimum histories, and class priors are
modeled inputs. The lab will publish sensitivity rather than presenting
illustrative constants as universal physical laws.

## 5. Worked counterfactual: the Hugging Face incident

Hugging Face's [technical timeline][hf-timeline] describes a July 2026 intrusion
that progressed from a production worker foothold into cloud and cluster
discovery, privilege escalation, secret access, cross-cluster administration,
mesh enrollment, token creation, and a source-control/CI pivot. The disclosure
is the primary source for observed incident facts in this paper.

The KIL analysis is conditional. It assumes the stated action is visible at the
enforcement boundary, the required bindings are available, signed state is
fresh, and modeled features and thresholds have the declared values. Until a
representative action is reproduced locally, the predicted decision is modeled.

### 5.1 Phase map

| Phase | Observed incident fact | Modeled trajectory evidence | Conditional KIL result |
|---|---|---|---|
| 0 — foothold | Renderer-related injection paths reached a production dataset-processing worker. | Configuration resolution to process or application internals is novel for the workload. | An application-aware point could deny the resolution; a transport-only adapter is not assumed to see it. |
| 1 — cluster API | The compromised worker used its service-account context and addressed Kubernetes control-plane endpoints. | The worker has no confirmed history in a control-plane or administrative class. | The modeled profile lowers effective authority below threshold; interception before transmission denies the request. |
| 2 — external replay | Cloud-derived credentials were used from external infrastructure for estate enumeration. | Origin distance, service novelty, request breadth, and sequence divergence are high. | Enumeration is denied or constrained under the declared origin and class profile. |
| 3 — node privilege | A privileged, host-mounted workload enabled node-level control and persistence. | Privilege delta is far outside a dataset worker trajectory. | Admission is denied if KIL mediates the privileged creation request. |
| 4 — secret access | Cluster secret objects, including a high-value multi-key object, were accessed. | Scope, volume, novelty, and sequence divergence exceed the modeled threshold; coupling reduces token and admin classes. | The bulk read is denied under the model; descendants are marked unreachable rather than counted as separate prevention. |
| 5 — cross-cluster administration | A shared connector credential enabled broad administrative use across clusters. | Credential possession provides no class-bound administrative history for the requesting identity. | The modeled state lacks sufficient `Q_i,c`, so the administrative action is denied. |
| 6 — mesh enrollment | A stolen mesh credential was used for repeated device enrollment. | Origin, workload-class mismatch, and cadence are anomalous. | The first high-divergence attempt reduces authority; later results depend on refresh and local-reduction mode. |
| 7 — forged identity tokens | Stolen signing capability enabled correctly signed identity tokens. | A new authentic token has no confirmed trajectory for the requested authority class. | Signature validity is necessary but insufficient; class history, state binding, and charge govern the action. |
| 8 — source control and CI | An installation token supported a source-control and CI-directed pivot attempt. | First-use write behavior and rapid targeting of build infrastructure diverge from baseline. | The modeled profile denies the action independently of earlier cutoffs. |

All incident facts in the second column summarize the public disclosure, not new
forensic findings by the KIL project. Synthetic values live in the versioned
scenario manifest rather than only in prose.

### 5.2 Structural cutoffs and dependency effects

The cluster-API transition and later high-scope secret read are candidate cut
points. The lab will encode event dependencies and report the first denied event
for each mode, the evidence that changed it, descendants made unreachable, and
exposure caused by refresh cadence. If an upstream modeled denial makes a
downstream action unreachable, KIL may show the reduced branch but may not claim
separate detection or validation of every descendant.

The incident motivates class-bound, trajectory-derived, fresh enforcement
state. It cannot establish the correct features, thresholds, decay constants,
coupling, false-positive rate, or inline latency. Those are lab questions.

## 6. Validation lab and demo

The lab follows the approved
[deterministic-first validation design](../superpowers/specs/2026-08-29-kil-lab-validation-design.md).

### 6.1 Control and modes

```text
permit_baseline = credential_valid AND policy_allows_action
```

The baseline is compared with `signed-state-only` and signed state plus local
reduction, implemented as `signed_plus_local_reduce`. All modes consume the same
normalized observed action and credential facts. KIL-specific context remains
separately labeled modeled.

### 6.2 Deterministic and live rails

The replay converts the disclosed action sequence into a source-cited graph,
applies versioned model inputs, and emits canonical decision records. Repeating
a run with the same commit, scenario, clock, model, and parameters must produce
the same semantic output and integrity digest.

The live rail generates benign and representative adversarial trajectories in
an isolated local Kubernetes environment. It reuses the replay request,
signed-state, decision, reason-code, and record schemas. The first adapter is
selected for observable pre-execution enforcement and reproducibility. The
project will not imply eBPF, SmartNIC, SDN, or production performance unless
that substrate is built and measured.

### 6.3 Validation gates

| Gate | Required evidence |
|---|---|
| V1 — deterministic kernel | Arithmetic boundaries, decay, class isolation, monotonic reduction, coupling, freshness, and non-expansion invariants pass automated tests. |
| V2 — historical replay | Observed events are cited, synthetic inputs are modeled, modes share action facts, and decision provenance is complete. |
| V3 — live local validation | Benign and adversarial trajectories produce observable outcomes matching decision records; safety cases include latency distributions. |
| V4 — publication promotion | Every `validated` statement points to a passing immutable run bundle; negative and ambiguous results remain visible. |

Run bundles contain the manifest, normalized scenario, signed states, decisions,
metrics, summary, and SHA-256 integrity record. Paper tables, figures, and
validated statements cite immutable run IDs.

## 7. Safety, failure, and governance

Incorrect automated reduction can block a legitimate action, so safety behavior
is part of the security claim. Administrative, privilege-escalation,
token-minting, and high-scope secret classes fail closed when required state is
invalid or unavailable. Lower-risk operations may fail constrained only inside
a predeclared KTP-safe envelope. No failure mode fails into greater authority.

Every decision is attributable to versioned inputs and reason codes. Emergency
and declared-change mechanisms are auditable, bounded, non-retroactive, and
unable to clear immutable constraints. Human governance remains necessary for
profile approval, recovery, contested decisions, calibration, and protocol
evolution even when enforcement itself is autonomous.

## 8. Limitations and research agenda

- The initial distance profile ignores feature covariance.
- Baselines and cold-start priors require representative legitimate telemetry.
- Authority-class coupling is not empirically calibrated.
- Attackers may attempt slow drift, baseline poisoning, sensor evasion, or
  compromised-state issuance.
- Local reduction can improve response time while increasing false-reduction
  risk.
- Enforcement placement determines which actions are visible and stoppable.
- One public incident cannot establish general efficacy.

The validation program will publish sensitivity analyses, benign controls,
negative results, placement limitations, and recovery behavior alongside
successful denial examples.

## 9. Conclusion

KIL reframes authorization as continuously refreshed, infrastructure-consumed
state rather than a one-time checkpoint. Its proposed contribution is not a
second trust model beside KTP, but an extension contract that makes KTP-derived
authority short-lived, class-bound, action-relevant, reducing-only, and
measurable at execution time.

The Hugging Face incident illustrates why this question matters: credential
validity alone cannot describe whether an action belongs to the operational
trajectory of the identity using it. The counterfactual remains a model. The KIL
lab exists to expose where that model works, where it fails, what it costs, and
which claims deserve promotion from proposal to locally validated evidence.

## References

1. N. Citra et al., *Kinetic Trust Protocol (KTP)—RFC Series*, version 2.0.0,
   [versioned specification][ktp-rfc-v2]. Canonical project citation metadata:
   [`CITATION.cff`][ktp-citation].
2. Kinetic Trust Protocol, *Architecture—Enterprise KTP*,
   [official architecture reference][ktp-architecture].
3. Kinetic Trust Protocol, *The Constitution of Digital Physics*,
   [official constitutional principles][ktp-constitution].
4. Hugging Face, *Anatomy of a Frontier Lab Agent Intrusion: A Technical
   Timeline of the July 2026 Incident*, [technical incident disclosure][hf-timeline].

[ktp-rfc-v2]: https://github.com/nmcitra/ktp-rfc/tree/v2.0.0
[ktp-architecture]: https://kinetic-trust-protocol.net/enterprise/architecture
[ktp-constitution]: https://kinetic-trust-protocol.net/learn/constitution
[ktp-citation]: https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff
[hf-timeline]: https://huggingface.co/blog/agent-intrusion-technical-timeline

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
