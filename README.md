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

The deterministic V1 decision kernel and V2 historical replay are locally
executable. V2 normalizes eight source-cited incident cut points, evaluates one
common stream under a modeled credential-policy baseline and two KIL modes, and
emits a reproducible, integrity-checked bundle. Historical counterfactual
results remain **modeled**, not validated. Concrete KTP signature verification
and live-cluster enforcement remain later gates.

## Evidence classes

Every replay input and published result will carry one of three labels:

- `observed`: directly supported by a named primary source;
- `modeled`: an explicit counterfactual assumption or synthetic signal; or
- `validated`: reproduced by the local-cluster reference implementation under
  an approved validation protocol.

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
| `docs/checkpoints/` | Durable pause/resume records for design and consultation |
| `docs/design-drafts/` | Unapproved architecture visuals and working designs |
| `docs/specialist/` | KIL–KTP lineage, decisions, and specialist briefing log |
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

## Historical replay

Use Python 3.11 or newer and provide an immutable implementation identity such
as the full Git commit. `OUTPUT` is the parent directory; the command creates a
content-addressed child directory and prints its path.

```bash
make replay \
  PYTHON=/path/to/python3.12 \
  OUTPUT=/absolute/path/to/replay-runs \
  VERSION=<full-git-commit>
```

The bundle contains `manifest.json`, `scenario.json`, `states.jsonl`,
`decisions.jsonl`, `metrics.json`, `summary.md`, and `SHA256SUMS`. Verify its
six public artifacts from inside the emitted run directory:

```bash
shasum -a 256 -c SHA256SUMS
```

The replay uses source-cited observed incident summaries together with
explicitly synthetic KTP state, local context signals, and credential-policy
assumptions. Its decisions must not be relabeled as validated.

## Primary foundations

- [KTP v2.0.0 RFC series](https://github.com/nmcitra/ktp-rfc/tree/v2.0.0)
- [Hugging Face July 2026 technical timeline](https://huggingface.co/blog/agent-intrusion-technical-timeline)
- [Hugging Face July 2026 incident disclosure](https://huggingface.co/blog/security-incident-july-2026)

Licensing for this new repository remains an explicit project decision. KTP
source material retains its Apache-2.0 license and attribution requirements.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

## Preserved starting artifacts

The two original Markdown drafts supplied by the project founder are preserved
unchanged in `docs/drafts/`. They are inputs to the design process, not approved
specifications or validated findings. Their byte-level checksums are recorded in
`research/source-material/SHA256SUMS`.

The complete 16-message Claude origin conversation is preserved as a
public-safe, provenance-bearing JSON record in `research/source-material/`.
Private account identifiers, hidden reasoning, tool exchanges, and unrelated
conversations are excluded from the tracked record. See
`docs/transition/CLAUDE-ORIGIN.md` for the recovery boundary.
