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

The deterministic V1 decision kernel, V2 historical replay, and V3A signed-
state authorization core remain locally executable modeled assets. V3B-1 now
implements the pinned local Envoy `ext_authz` boundary, a hardened transcript-
driven lifecycle and evidence harness, and an authoritative offline presenter.
Three exploratory local cycles were rejected and remain private. The first
committed zero-request V3B-1 smoke from public source commit `47c0614d49ec`
completed exact teardown and restored the foreign runtime, but it did not pass
the evidence-freeze gate: three Envoy legs were copied while six authorization
and target ledger copies failed after zero-byte in-container observations. Its
empty failure bundle is nonpromotable and does not independently prove service-
source absence.

The harness now contains a bounded exact-byte service-ledger export correction.
Two subsequent launch attempts stopped before profile creation because of host
tool discovery and a Colima false-flag compatibility mismatch; both were
durably archived without a request or KIL runtime. The minimal launch correction
retains post-start attestation that nested virtualization is disabled. The next
execution gate is a fresh zero-request `preflight` / `up` / `down` smoke from a
clean public commit containing both corrections. A central request remains
prohibited until all nine source legs are copied and byte-bound. Kind/Calico
validation (V3B-2) and repetition and performance promotion (V3C) remain
unexecuted.

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
| `adapters/envoy/` | Frozen V3B Envoy external-authorization boundary |
| `adapters/kubernetes/` | Earlier Kubernetes adapter scaffold |
| `deploy/kind/` | Reproducible local Kubernetes environment |
| `tests/` | Unit, property, conformance, replay, and live integration tests |
| `tools/` | Source-ingestion, validation, and publication utilities |

## Bootstrap check

Install the optional laboratory dependency set, then run the complete unit
suite:

```bash
python -m pip install -e ".[lab]"
make test
```

This installs the pinned V3A cryptography library. No cluster dependency is
installed or downloaded by the bootstrap.

The V3B-1 tool bootstrap and preflight are separate, opt-in commands:

```bash
make v3b-tools PYTHON=.venv/bin/python
make v3b-preflight PYTHON=.venv/bin/python
```

The tool command downloads only the resolved laboratory clients into ignored
`.tools/`; neither command installs a system-wide dependency. The fixed bearer
string and deterministic Ed25519 seeds used by V3B-1 are public, non-secret
laboratory fixtures. They must never be reused as production credentials or
keys.

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

## V3A process-contract demonstration

V3A runs the same normalized action facts through three fixed tracks and emits
an integrity-checked JSONL/HTML bundle. The expected outcome is
`permit / permit / deny`; only permitted tracks receive a target marker.

```bash
make v3a-demo \
  PYTHON=/path/to/python3.12 \
  OUTPUT=/absolute/path/to/v3a-runs \
  VERSION=<full-git-commit>
```

V3A does not exercise Envoy or Kubernetes and must not be described as a
validated cluster result. See the
[V3 architecture diagram](docs/architecture/v3-envoy-live-validation.svg) and
[V3 progress record](docs/lab/V3-PROGRESS.md).

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
