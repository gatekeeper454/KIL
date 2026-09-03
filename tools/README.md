# Project tools

Repository tools normalize public source material, validate evidence labels,
run deterministic replays, compare counterfactuals, and generate paper tables
and figures from canonical decision records.

## Markdown reader publication

`render_markdown.py` maps every Git-tracked file whose final suffix is
lowercase `.md` to exactly one same-directory `.htm` reader. Markdown is the
source of record; generated readers carry their source path and SHA-256 digest
and must not be edited directly.

```bash
make docs-html
make docs-html-check
```

Generation uses the exact Git-index source set, renders all documents before
replacing any output, and reserves visible nonignored `.htm` paths for the
generated corpus. The output embeds the rendered article, CSS, and bounded
JavaScript controls, so no hosted runtime or network fetch is required to read
it directly from disk. Raw HTML is escaped. Only links to tracked relative
Markdown documents are changed to `.htm`; external, missing, fragment-only,
image, and non-Markdown destinations retain their source destination. The
content security policy blocks remote content and network APIs. Local relative
image references remain file references rather than embedded binary data and
therefore require the referenced local files to remain available.

`make docs-html-check` runs the renderer with `--check`. It performs no repairs
or removals and returns failure after reporting every missing, stale, or
unexpected visible reader. `make validate` includes this check, so any future
tracked lowercase-`.md` addition or removal changes the exact required `.htm`
set automatically. Regeneration and checking require the pinned `docs`
dependency set.

`v3a_demo.py` runs the three infrastructure-fixed authorization tracks against
one normalized request, joins each decision to its forwarding outcome and
harmless target marker, and emits an atomic, content-addressed evidence bundle.
The bundle is labeled `modeled` with scope `process_contract_only`; it is not an
Envoy or Kubernetes validation. It contains decisions, joins, target records,
the two signed Q-state fixtures, the public verification JWK and provenance,
the visible HTML view, a Markdown summary, a manifest, and checksums.

```bash
PYTHONPATH=src python3 tools/v3a_demo.py \
  --output /absolute/path/to/v3a-runs \
  --implementation-version <full-git-commit>
```

## V3B-1 local-Envoy controller

`v3b1_local_envoy.py` orchestrates the corrected in-network request-driver
boundary. It creates three isolated tracks over six internal networks. In each
track the frontend is configured for `{driver, Envoy}` and the backend contains
`{Envoy, authz, target}`. Docker's physical inventory is derived from fresh
container state: only `running` roles contribute endpoints. With Envoy running,
the frontend is `{Envoy}` for a `created`, `exited`, or `dead` driver and
`{driver, Envoy}` for a running driver; stopped services are likewise absent
from the backend. Envoy is the only configured dual-homed service. There is no host
TCP publication. Docker attach/stdin is a host control channel only. The
consequential request path is:

```text
driver -> Envoy -> authorization -> target or withhold
```

Each request driver is a one-shot laboratory transport witness; it is not an
authorization decision point.

The twelve lifecycle-owned track containers comprise three one-shot drivers,
three Envoys, three authorization services, and three harmless targets. Three
additional validators are transient. `down` finalizes drivers before Envoys,
freezes the nine Envoy/authz/target authority sources, and proves all fifteen
containers and six networks absent through exact full-ID inventory.

The request-free `readiness` command starts all three drivers before reading
their readiness records, sends no stdin instruction and no HTTP request, then
cancels all three under one bounded lifecycle. The central `run` uses a fresh
set, persists intent before sending exactly one canonical instruction per
driver, and performs no retry after intent. If intent is ambiguous, evidence is
nonpromotable while exact cleanup still proceeds.

The v2 bundle adds three exact canonical driver results:

```text
raw/drivers/credential_policy_baseline.json
raw/drivers/signed_state_only.json
raw/drivers/signed_plus_local_reduce.json
```

Those result bytes are bound to the corresponding request, manifest identity,
checksums, and nine authoritative service sources. The offline presenter states
`No host publication`, identifies the driver as a laboratory transport witness
rather than KIL enforcement, and limits claims to `local_envoy_boundary`.

The mechanism is implemented and statically approved at commits `75161f0` and
`48bd81a`. The Task 8 implementation checkpoint passed 466 non-runtime tests.
The fresh Task 9 complete static gate passes 474 tests, including eight
documentation tests. Request-free live readiness and the conditional central
proof remain pending. Do not infer a live acceptance, historical prevention,
Kind/Calico result, or performance claim from the static result.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
