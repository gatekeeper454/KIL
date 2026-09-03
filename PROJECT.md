# Project charter

## Objective

Demonstrate that AI-era authorization can be enforced as a continuously
recomputed property of an action trajectory at the infrastructure boundary,
instead of relying only on the validity of a credential at a checkpoint.

## Agreed direction

- Audience: public thought leadership that withstands review by security
  architects and researchers.
- Deliverable: a paired technical paper and executable reference implementation.
- Protocol posture: a KTP v2.0.0 reference implementation plus a narrowly scoped
  extension proposal.
- Execution: both deterministic incident replay and live local Kubernetes
  enforcement.
- Repository boundary: KIL owns detection and enforcement behavior while
  preserving provenance.

## Evidence contract

The public replay may combine disclosed Hugging Face actions with synthetic KTP
context signals only when every value is labeled by provenance. `Observed`
means supported by a primary source, `modeled` means an explicit counterfactual
assumption, and `validated` is reserved for behavior reproduced locally.

## Non-goals for the bootstrap

- Selecting trust-decay constants or thresholds.
- Claiming that KIL would have prevented the historical incident.
- Installing or changing a Kubernetes environment.
- Modifying KTP upstream specifications.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
