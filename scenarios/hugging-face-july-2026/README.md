# Hugging Face July 2026 scenario

This directory contains the canonical eight-phase historical scenario for the
first KIL replay. It is normalized from Hugging Face's public
[technical timeline](https://huggingface.co/blog/agent-intrusion-technical-timeline)
and encoded as schema `kil.scenario.v1` with scenario ID
`hf-july-2026-eight-phase`.

| Phase | Event | Consequential action class | Depends on |
|---:|---|---|---|
| 1 | `hf-p1-cluster-api` | `admin_action` | — |
| 2 | `hf-p2-external-replay` | `network_egress_external` | phase 1 |
| 3 | `hf-p3-privileged-workload` | `privilege_escalation` | phase 1 |
| 4 | `hf-p4-secret-read` | `read_other_resource` | phase 3 |
| 5 | `hf-p5-cross-cluster-admin` | `admin_action` | phase 4 |
| 6 | `hf-p6-mesh-enrollment` | `network_egress_external` | phase 4 |
| 7 | `hf-p7-forged-token` | `mint_token` | phase 4 |
| 8 | `hf-p8-ci-pivot` | `admin_action` | phases 6 and 7 |

## Evidence boundary

Each event summary is labeled **observed** and carries a section-level anchor to
the primary disclosure. Those labels are human-auditable source locators, not
claims that Hugging Face published raw event telemetry.

The legacy credential/policy outcome, composite KTP state (`Q_i,c`), and local
context signals are synthetic counterfactual inputs labeled **modeled** with
their rationales. All replay decisions derived from them remain **modeled**.
Nothing in this scenario is labeled **validated**; that term is reserved for
results reproduced under an approved local-cluster validation protocol.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
