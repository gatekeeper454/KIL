# Kinetic Infrastructure Layer (KIL)

KIL is a public, testable reference implementation of Kinetic Trust Protocol
(KTP) v2.0.0 concepts at a transport enforcement boundary. The project pairs a
publishable technical paper with two executable demonstrations:

1. a deterministic counterfactual replay of the July 2026 Hugging Face agent
   intrusion; and
2. a staged live proof that first applies the same decision model at a local
   Envoy boundary, with Kind/Calico cluster validation reserved for a later
   gate.

The narrow extension proposal will specify only what KTP v2.0.0 does not yet
make sufficiently concrete for this use case. KIL will not rename existing
KTP-Transport, KTP-Enforce, KTP-Gravity, or Vector Identity constructs.

## Status

The deterministic V1 decision kernel, V2 historical replay, and V3A signed-
state authorization core remain locally executable modeled assets. The
corrected V3B-1 local-Envoy mechanism is implemented and statically approved at
commits `75161f0` and `48bd81a`: three one-shot request drivers communicate with
three fixed Envoy `ext_authz` tracks over six internal networks without a host
TCP publication. The Task 8 implementation checkpoint passed 466 non-runtime
tests. The fresh Task 9 complete static gate passes 474 tests, including eight
documentation tests. The stopped-endpoint recovery correction merged through
PR #16 after its
232-test controller suite, complete 484-test repository gate, and both public
CI jobs passed.

Each track has a frontend configured only for its driver and Envoy, and a
backend containing only Envoy, authorization service, and harmless target.
Physical membership is derived from fresh container state: only a `running`
role contributes an endpoint. With Envoy running, a never-started, exited, or
dead driver yields `{Envoy}` and a running driver yields `{driver, Envoy}`; a
stopped Envoy contributes no endpoint. The nominal running backend is
`{Envoy, authz, target}`, with each stopped role absent. Envoy is the sole
configured dual-homed component. The lifecycle owns twelve track
containers plus three transient validators and proves all fifteen containers
and all six networks absent during exact teardown. Docker attach/stdin is only
the host control channel that gives a driver one canonical instruction; the
consequential path is `driver -> Envoy -> authorization -> target or withhold`.
The driver is a laboratory transport witness, not KIL enforcement. The current
evidence scope is `local_envoy_boundary`.

The driver-era Task 10 request-free live gate passed from source
`a46e8dc98a1af64ceadb5700e91c2f87840564fe` as run
`v3b1-d2b26f6c8136dcd26a6e6727b9bb1381076a1e03b71a5a44df9b2b2ef9db6cf9`.
It produced three exact readiness records and three clean cancellations, with
zero driver instructions and zero HTTP requests. Evidence freeze persisted all
nine zero-byte service legs; teardown removed all 15 exact containers and all
six exact networks. The public manifest binds the foreign context name as
`default` before and after the lifecycle, and a post-run readback observed its
stopped resource tuple; the exact tuple was not durably bound at both ends.
The central `run` was not executed and remains prohibited until the
[Task 10 gate record](docs/lab/V3B1-TASK10-REQUEST-FREE-GATE.md) is reviewed,
merged, and synchronized and a tested, merged evidence extension durably binds
and verifies exact before/after resource snapshots. This is accepted request-
free lifecycle evidence,
not an enforcement result. Kind/Calico validation (V3B-2), repetition, and
performance promotion (V3C) remain future work.

Historical pre-driver records remain available for provenance. The rejected
nine-service/three-network smoke ran from public source
`47c0614d49ec1a7484cdefd04cc5d080adc73ca2` as
`v3b1-1db8b5914ce26e2e6c60e74124bcc1b2c9ed66b7dd68c2d3cf4ea1bc0d18c9b3`.
After intervening pre-profile launch failures, the corrected zero-request
lifecycle ran from public source
`6706859d265204e0a569ebb6817d187dc1728f9d` as
`v3b1-0374c771b23adcab64060cd8c854d12b72417ff8e4713d24e6f6a550e20bdbea`
and accepted that retired topology's lifecycle/evidence-freeze gate without an
enforcement request. Both are pre-driver historical records; neither can
satisfy the current six-network driver-era readiness or acceptance contracts.

## Evidence classes

Every replay input and published result will carry one of three labels:

- `observed`: directly supported by a named primary source;
- `modeled`: an explicit counterfactual assumption or synthetic signal; or
- `validated`: reproduced by the local-cluster reference implementation under
  an approved validation protocol.

Modeled output must never be presented as an observed fact. A local experiment
must never be presented as proof that a counterfactual would have changed the
historical incident.

## Presenter/Audience showcase

Start the self-contained, two-act demonstration from the repository root:

```sh
make kil-showcase
```

Open the presenter at
`http://127.0.0.1:8767/kil-presenter-audience-demo.html?mode=presenter&session=showcase`.
Use **Open audience view** to launch the synchronized, controls-free audience
window. Advancing either act or scene in the presenter updates every audience
window using the same session. The presenter contains the 30–45-second talk
track and evidence label for each scene; the audience sees only the story and
graphics. Brave Chromium is the preferred showcase browser and the automated
browser verifier uses Brave when it is installed.

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

### V3B-1 local-Envoy boundary

The V3B-1 controller has separate lifecycle commands for `preflight`, `up`,
request-free `readiness`, one central `run`, evidence `collect`, `down`, and an
offline `view`. Readiness starts all three attached drivers, reads their
request-free readiness records, and cancels all three without sending an
instruction or HTTP request. A central run starts a fresh three-driver set,
records durable request intent, sends exactly one canonical instruction to each
driver, and never retries after intent.

The v2 public evidence contract publishes the exact canonical result from each
driver under `raw/drivers/`, together with nine authoritative Envoy,
authorization, and target sources. The verifier reconstructs and hashes those
sources before joining the same request, decision, forwarding, and target facts.
The central local-Envoy enforcement gate remains pending. Until it passes,
these contracts are statically verified and must not be described as a
validated enforcement result. V3B-2 Kind/Calico validation remains a later
gate.

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
