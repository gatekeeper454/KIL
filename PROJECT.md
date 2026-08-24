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
- Repository boundary: separate from ShadowClaw so detection and enforcement
  remain independent processes.

## Current open decision

Whether the public replay may combine disclosed Hugging Face actions with
clearly labeled synthetic KTP context signals when the primary disclosure does
not provide raw telemetry, while reserving `validated` for results reproduced
in the local cluster.

## Non-goals for the bootstrap

- Selecting trust-decay constants or thresholds.
- Claiming that KIL would have prevented the historical incident.
- Installing or changing a Kubernetes environment.
- Modifying ShadowClaw or KTP upstream specifications.

