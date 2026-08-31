# Project tools

Repository tools normalize public source material, validate evidence labels,
run deterministic replays, compare counterfactuals, and generate paper tables
and figures from canonical decision records.

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
track the frontend contains `{driver, Envoy}` and the backend contains
`{Envoy, authz, target}`; Envoy is the only dual-homed service. There is no host
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
