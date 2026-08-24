# Kinetic Infrastructure Layer (KIL)

KIL is a public, testable reference implementation of Kinetic Trust Protocol
(KTP) v2.0.0 concepts at a transport enforcement boundary. The project pairs a
publishable technical paper with two executable demonstrations:

1. a deterministic counterfactual replay of the July 2026 Hugging Face agent
   intrusion; and
2. a local Kubernetes proof of concept that applies the same decision model to
   live traffic.

The narrow extension proposal will specify only what KTP v2.0.0 does not yet
make sufficiently concrete for this use case. KIL will not rename existing
KTP-Transport, KTP-Enforce, KTP-Gravity, or Vector Identity constructs.

## Status

Repository scaffold only. No trust-decay equation, cutoff result, or enforcement
claim is implemented or validated yet. Those are design decisions still under
review.

## Evidence classes

Every replay input and published result will carry one of three labels:

- `observed`: directly supported by a named primary source;
- `modeled`: an explicit counterfactual assumption or synthetic signal; or
- `validated`: reproduced by the local reference implementation.

Modeled output must never be presented as an observed fact. A local experiment
must never be presented as proof that a counterfactual would have changed the
historical incident.

## Project boundaries

KIL is an enforcer and experiment harness. ShadowClaw remains a separate,
detector-only project and may supply KTP Risk Factor telemetry through a stable
interface. KIL must not import ShadowClaw internals or move enforcement into the
sensor process.

## Repository map

| Path | Responsibility |
|---|---|
| `docs/paper/` | Publishable argument, model, results, and limitations |
| `docs/drafts/` | Byte-preserved original draft artifacts |
| `docs/extension/` | Narrow KTP extension proposal and compatibility analysis |
| `docs/superpowers/specs/` | Approved design specifications |
| `research/` | Primary-source register and preserved source material |
| `scenarios/` | Replay scenarios and evidence manifests |
| `schemas/` | Versioned wire and fixture schemas |
| `src/kil/` | Deterministic model, replay engine, and decision records |
| `adapters/kubernetes/` | Live transport-enforcement adapter |
| `deploy/kind/` | Reproducible local Kubernetes environment |
| `tests/` | Unit, property, conformance, replay, and live integration tests |
| `tools/` | Source-ingestion, validation, and publication utilities |

## Bootstrap check

```bash
make test
```

No cluster dependency is installed or downloaded by the bootstrap.

## Primary foundations

- [KTP v2.0.0 RFC series](https://github.com/nmcitra/ktp-rfc/tree/v2.0.0)
- [Hugging Face July 2026 technical timeline](https://cdn-avatars.qwak.ai/blog/agent-intrusion-technical-timeline)
- [Hugging Face July 2026 incident disclosure](https://huggingface.co/blog/security-incident-july-2026)

Licensing for this new repository remains an explicit project decision. KTP
source material retains its Apache-2.0 license and attribution requirements.

## Preserved starting artifacts

The two original Markdown drafts supplied by the project founder are preserved
unchanged in `docs/drafts/`. They are inputs to the design process, not approved
specifications or validated findings. Their byte-level checksums are recorded in
`research/source-material/SHA256SUMS`.
