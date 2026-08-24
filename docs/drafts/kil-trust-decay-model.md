# The Trust-Decay Model

### A formal basis for ambient enforcement in the Kinetic Infrastructure Layer

*This document specifies the mathematical model underlying "trust charge" — the mechanism that lets infrastructure grant or withhold authority to an action in real time, without a policy engine or human decision in the loop. It's built to be defensible, not just evocative: every design choice below is there because of a specific failure mode observed in the July 2026 Hugging Face incident (see the companion timeline document), and the worked example at the end traces the model numerically against that incident's actual phases.*

---

## 1. Design principles, stated up front

Before the equations, four decisions that shape everything downstream — because a "trust as physics" metaphor is only defensible if the physics encodes real security properties, not just a decaying number that looks scientific.

1. **Charge is earned slowly and lost quickly.** Legitimate trust accumulates through repetition; a single wildly anomalous action should cost far more than any one normal action gains. This isn't poetic license — it's the direct fix for the incident's root failure, where a stolen-but-valid credential was treated as equally trustworthy on its first ever cluster-admin action as an identity with months of legitimate cluster-admin history.
2. **Charge is per authority class, not a single number.** An identity that has built deep trust for "read my assigned dataset" has built *none* for "call the Kubernetes API" — those are different classes of action with independent trust histories. A single scalar would let reads-heavy legitimate behavior silently subsidize an escalation attempt.
3. **Charge decays passively, even with no bad behavior.** An idle credential's standing authority should erode over time. This is what makes 24-hour-valid forged tokens and long-lived VPN keys structurally weaker under this model than under a validity-until-expiry model.
4. **The model must have an explicit, honest escape hatch.** Real infrastructure has legitimate rare events — migrations, incident response, a new deploy pattern. A model with no way to pre-register an expected trajectory change will either get bypassed by operators or cause real outages. Section 6 covers this; it is not an afterthought.

---

## 2. Formal definitions

**Identity** `i` — any workload, agent, or credential-holder whose actions are tracked: a pod, a service account, an agent session, a device.

**Authority class** `c ∈ C` — a bucket of action types requiring comparable privilege: e.g. `{read_own_data, read_other_resource, network_egress_internal, network_egress_external, mint_token, admin_action, privilege_escalation}`. Each class has its own independent trust charge for a given identity.

**Action** `a_t` — a single action taken by identity `i` at time `t`, represented as a feature vector `x_t ∈ ℝⁿ` capturing:

| Feature | What it captures | Example from the incident |
|---|---|---|
| target resource novelty | has `i` ever addressed this resource before | worker pod calling `kubernetes.default.svc/api` for the first time |
| network origin distance | how far this request's origin is from `i`'s historical origin set | node-role credential replayed from external hosting-provider IP |
| privilege delta | requested scope vs. `i`'s historical maximum granted scope | reading a 136-key secret object vs. prior single-key reads |
| temporal anomaly | deviation from `i`'s established request cadence | 181 enrollment attempts in under 4 hours from one key |
| volume anomaly | bytes/records touched vs. `i`'s historical distribution | bulk secret-object read vs. routine per-file reads |
| sequence anomaly | likelihood of this action given `i`'s prior action, under `i`'s learned action-bigram model | `read_own_token → call_cluster_api` — a bigram never seen for this workload class |

**Baseline trajectory** `B_i,c` — the learned distribution (mean `μ` and variance `σ²` per feature, or a small sequence model) of identity `i`'s historical actions within class `c`. This is the KTP **Vector Identity** made concrete: not a static role or credential, but a live statistical model of how this identity actually behaves.

---

## 3. Divergence score

For an action `a_t` in class `c`, compute a normalized divergence `d_t ∈ [0, 1]` against the baseline:

```
        ___________________________
       /  n
d_raw = √  Σ  w_j · ((x_t,j − μ_j) / σ_j)²
          j=1

d_t = 2 / (1 + e^(−k · d_raw)) − 1        (logistic squash to [0,1])
```

This is a weighted Mahalanobis distance (standard practice for multivariate anomaly scoring — it naturally down-weights features with high historical variance and up-weights features that are normally very stable for this identity) squashed into a bounded range so the charge dynamics below stay well-behaved regardless of raw feature scale. `w_j` are feature weights, tunable per authority class (e.g., network-origin distance should dominate for `network_egress`, sequence anomaly should dominate for `privilege_escalation`).

**Cold-start identities** (no history yet) get `d_t` computed against the *class prior* — the population-level baseline for that workload type — rather than an individual baseline that doesn't exist yet. This is what puts new identities into a probationary tier automatically (Section 6) rather than either blocking them entirely or trusting them by default.

---

## 4. Charge dynamics

Each identity `i` holds a charge vector `E_i,c(t)` for each authority class `c`, bounded in `[0, E_max]`. Between actions, charge decays passively; at each action, charge is updated based on divergence.

**Passive decay** (elapsed time `Δt` since the identity's last action in class `c`):

```
E'_i,c = E_i,c(t_prev) · e^(−λ_c · Δt)
```

This is a direct RC-discharge analogy — charge leaks exponentially toward zero absent activity, at rate `λ_c`. Higher-privilege classes get a larger `λ_c` (leak faster) — cluster-admin authority earned last week should not still be "charged" today; read-only authority can persist longer, because passive decay is a strong response to exactly the pattern of a 24-hour-valid forged token: even a technically-unexpired credential arrives at a near-empty charge if it hasn't been actively re-earning trust.

**Event update** at the action itself:

```
Δ(d_t) =  +ρ_gain,c · (1 − d_t/θ_c)              if d_t ≤ θ_c   (replenishment)
          −ρ_loss,c · (d_t/θ_c)^p                 if d_t > θ_c   (penalty)

E_i,c(t) = clamp( E'_i,c + Δ(d_t),  0,  E_max )
```

`θ_c` is the acceptable-divergence threshold for class `c` (the "normal noise" band — even legitimate behavior isn't perfectly identical action to action). `p > 1` (recommend `p = 3`) makes the penalty superlinear: an action twice over threshold costs roughly 8× the penalty of an action barely over threshold. This single exponent is what encodes "a small deviation is fine, a wild one is catastrophic and immediate" — directly modeling the difference between, say, a slightly unusual read pattern versus a worker pod suddenly enumerating the cloud control plane.

**The core asymmetry**, and the most important tunable in the whole model:

```
ρ_loss,c ≫ ρ_gain,c        (recommended ratio: 10× to 50×, tightening with class privilege)
```

Trust arrives on foot and leaves on horseback. This is not a stylistic choice — it's the direct fix for the incident's central defect, where possession of a valid credential conferred full authority instantly and losing that authority required a human to notice and manually rotate the credential.

---

## 5. Authorization gate and cross-class coupling

An action requesting authority class `c` is permitted only if:

```
E_i,c(t) ≥ τ_c        AND        history_count_i,c ≥ h_c
```

`τ_c` is the minimum charge threshold for class `c`; `h_c` is a minimum number of prior *low-divergence* actions in that specific class — this second condition is what stops an identity from grinding charge quickly through many trivial, easy, low-divergence actions in one class and then attempting to "spend" that accumulated charge on an unrelated escalation. Charge earned reading files does not transfer to charge for calling the Kubernetes API, because `h_c` for `admin_action` requires a real history *of admin-adjacent actions specifically* — history that a freshly-compromised worker pod cannot possibly have.

**Cross-class coupling.** Authority classes are hierarchically related — trust in a low-privilege class is a soft precondition for trust in a higher one, but not vice versa. When a divergence event in a low class exceeds a severity threshold, it also applies a fractional penalty to related higher classes:

```
E_i,c'(t) -= κ_c,c' · penalty_magnitude(d_t)     for each c' downstream of c
```

This is what makes a single bad event cascade appropriately: the Phase 4 moment in the Hugging Face incident — reading a 136-key secret object — wasn't just a divergence in `read_other_resource`; under coupling, it also depletes charge for `mint_token`, `network_egress_external`, and `admin_action`, because those classes' legitimacy was resting on the same identity whose baseline just broke.

---

## 6. The escape hatch: declared trajectory changes

A model with no way to represent legitimate change either gets disabled by frustrated operators or causes real outages during migrations, incident response, or planned architecture changes. The fix is an explicit, auditable pre-registration mechanism, not a blanket exception:

- An operator or automated change-management system can submit a **trajectory grant**: `(identity, class, expected_feature_range, valid_window, issued_by)`.
- During the valid window, actions matching the declared range compute divergence against the *grant's* declared range in addition to the historical baseline — effectively widening `θ_c` temporarily and locally, not globally.
- Every grant is itself an auditable, provenance-bearing object — logged with who issued it and why — so "we widened the trust window for the migration" is a reviewable decision, not a silent bypass.
- Grants never apply retroactively and never apply to classes outside what was declared — a grant for `network_egress_internal` during a maintenance window does not quietly cover `admin_action`.

New identities enter at a **probationary tier**: `E_i,c(0)` initialized low, `τ_c` for anything beyond `read_own_data` effectively unreachable until `h_c` (real history) accumulates through ordinary operation. This maps directly onto **Blue Zones** — the probationary tier is the innermost, most-restricted zone, and identities graduate outward only by building real trajectory, never by a one-time grant of standing privilege.

---

## 7. Worked example: tracing charge through the incident

Take the compromised dataset-processing worker pod as identity `i`, and trace `E_i,c(t)` across four authority classes as the actual incident phases occur. Illustrative parameter values: `E_max = 100`, `θ_c ≈ 0.25`, `p = 3`, `ρ_gain = 1`, `ρ_loss = 25`, `λ` small for `read_own_data`, larger for `admin_action`.

| Phase | Class touched | Divergence `d_t` | Charge before | Charge after | Gate result |
|---|---|---|---|---|---|
| Baseline operation (weeks of normal conversion jobs) | `read_own_data` | ~0.05–0.15 (normal noise) | — | stabilizes around 60–75 | reads permitted, as expected |
| Phase 1 — SA token read + cluster API call | `network_egress` (new class for this identity) | ~0.95 (never touched before) | ~5 (cold-start prior, no history) | **≈ 0** (penalty ≈ 25 · (0.95/0.25)³ ≈ 1,368, clamped) | **denied** — call never reaches the API |
| Phase 2 — metadata replay from external origin | `network_egress` | ~0.98 (origin never seen) | 0 (already floored) | 0 | **denied** |
| Phase 4 — bulk 136-key secret read | `read_other_resource`, with coupling into `admin_action`, `mint_token` | ~0.9 | `read_other_resource` starts moderate (~40, some legitimate cross-resource reads exist); `admin_action`/`mint_token` start near 0 (no history) | `read_other_resource` collapses toward 0; coupled classes stay at 0 | **denied** — bulk read blocked, and nothing downstream ever gets minted |
| Phase 6 — 181 mesh enrollment attempts | `network_egress_external` / `mint_token`-adjacent | ~0.95, and cadence anomaly compounds it (181 attempts in <4h vs. a legitimate key's historical rate of near-zero) | 0 (already floored from Phase 1/2/4 coupling) | 0 | **denied from attempt 1**; even without upstream coupling, attempt 2 alone would floor it |

The pattern that falls out of the math, not asserted separately: **the actual incident's escalation only works because every step after Phase 1 assumes the previous step's authority was legitimately obtained.** Once Phase 1 is denied under this model, everything downstream is denied not because each subsequent action was separately caught, but because the coupling terms mean there was never any charge to spend in the first place. That's the property worth stating plainly in the demo: this isn't seven separate detections — it's one structural cutoff whose effects cascade for free.

---

## 8. What would make this genuinely defensible (not just internally consistent)

Being honest about what's still owed before this is a production claim rather than a model:

- **Calibration requires real telemetry.** `θ_c`, `ρ_gain`, `ρ_loss`, `p`, and the feature weights `w_j` are currently reasoned from first principles and from this one incident. They need to be fit against a large corpus of *legitimate* action sequences across many workload classes to know the real false-positive rate — the model needs to not flag Tuesday's ordinary batch job as an intrusion.
- **The Mahalanobis/logistic formulation is a reasonable default, not the only valid one.** A learned sequence model (small transformer or HMM over action n-grams) may outperform a hand-specified feature+distance approach once there's enough data — worth prototyping both.
- **Coupling coefficients `κ_c,c'` are the least-justified numbers in the model right now.** They encode a hierarchy of authority classes that should probably be derived empirically (which classes actually predict compromise of which other classes) rather than assigned by intuition.
- **Latency is a real constraint.** Computing `d_t` has to happen fast enough to gate the action inline at the transport/substrate layer — this pushes toward lightweight per-action scoring (the Mahalanobis form is cheap) rather than a heavyweight model in the hot path, with any heavier sequence modeling done asynchronously to update the baseline, not to gate the live action.

---

*Companion to "What Ambient Enforcement Would Have Done" (the annotated Hugging Face incident timeline). Together these two documents form the technical basis for the Kinetic Infrastructure Layer demo: this document supplies the model, the timeline document supplies the case it's tested against.*
