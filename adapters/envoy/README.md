# Envoy adapter boundary — Gate V3B

V3B-1 implements three independently configured local Envoy `ext_authz` routes
in front of harmless target workloads. Each authorization service instance
fixes one track at startup. V3B-2 may reuse the same fixed tracks in a future
Kind/Calico topology. The historical driver-era request-free lifecycle gate is
accepted as a lifecycle result, but no central V3B-1 enforcement proof has
been accepted, promoted, or labeled validated:

1. `credential_policy_baseline`
2. `signed_state_only`
3. `signed_plus_local_reduce`

## Corrected local topology

Each track uses two Docker-internal networks with no host TCP publication:

```text
host control: Docker attach/stdin -> one-shot driver

frontend:  driver -> Envoy
backend:             Envoy -> authorization
                     Envoy -> harmless target or withhold
```

The frontend is configured exactly for `{driver, Envoy}`. Physical membership
is state-derived: with Envoy running it is `{Envoy}` while the driver is
`created`, `exited`, or `dead`, and `{driver, Envoy}` only while the driver is
`running`. A stopped Envoy has no physical endpoint. The nominal running
backend is `{Envoy, authz, target}`; each stopped role is absent from its
physical inventory. Envoy is the sole configured dual-homed component. Across
the three tracks the lifecycle owns twelve track containers plus three
transient validators and six networks. Driver-first exact teardown freezes the
nine Envoy, authorization, and target sources before proving all fifteen
containers and all six networks absent.

Attach/stdin does not carry consequential traffic across the enforcement
boundary; it supplies exactly one canonical request instruction to a one-shot
driver. That request driver then opens the track-local connection to Envoy. The
driver is a laboratory transport witness, not KIL enforcement, and the current
claim scope is `local_envoy_boundary`.

Request-free readiness starts all three attached drivers, consumes only their
readiness records, sends no instruction and no HTTP request, and performs three
bounded cancellations. A central run uses fresh drivers, durably records intent
before sending one instruction per track, and never retries after intent.

Historically, the Task 8 implementation checkpoint passed 466 non-runtime
tests, and the fresh Task 9 complete static gate passed 474 tests, including
eight documentation tests.

The current evidence extension emits `kil.v3b1-manifest.v3`. Its private
journal durably binds exact before/after foreign Colima records and requires
exact equality for complete evidence, while its public manifest replaces names
with run-scoped HMAC pseudonyms and retains status, architecture, CPU, memory,
disk, and runtime. A mismatch never authorizes foreign mutation and can
publish only nonpromotable failure evidence. Offline verification keeps the
historical v1 and driver-era v2 schemas closed and independently verifiable.

The fresh request-free v3 lifecycle ran from synchronized public-main source
`5ebf21a88794a9f83a0e6c8ee53e76f6d8e5142d` as
`v3b1-4ac0b6eef70b0483f7883c8a26753d15a007f612953b25e23b8ecb6afd021a8f`.
Its `kil.v3b1-public-manifest.v3` records three readiness completions, three
clean cancellations, zero driver instructions, zero request intents, zero HTTP
requests, exact teardown of 15 containers and six networks, and exact equality
of the pseudonymous foreign-resource arrays. The result is request-free and
nonpromotable, not an enforcement result. After this prerequisite merged and
synchronized, the first central `run` executed exactly once and observed HTTP
`200 / 200 / 403` with target markers `1 / 1 / 0`. Collection rejected Envoy
typed-JSON number/null output, two exact Envoy transport headers in
authorization records, and one not-yet-visible live ledger. Teardown completed,
the evidence stayed private and nonpromotable, and no request was retried. The
producer-side canonical-text and bounded-read correction is locally verified;
another run remains prohibited until that correction is reviewed, merged
through public CI, and exactly synchronized. The previously accepted Task 10
bundle remains historical v2 evidence and does not satisfy the v3 prerequisite
by itself.

The request cannot select or downgrade the active track. KIL state is a signed,
short-lived experimental extension envelope that references KTP Trust Proof and
Kinetic Envelope results; it does not replace either KTP construct. The first
lab profile uses Ed25519 compact JWS, track-bound audiences, exact request
binding, a maximum ten-second lifetime, and fail-closed verification.

## Fixed HTTP contract

Each Envoy HTTP filter chain places `envoy.filters.http.ext_authz` immediately
before `envoy.filters.http.router`. The laboratory profile fixes an authorization
timeout of 250 ms, disables retries, sets `failure_mode_allow: false`, and does
not enable route-cache clearing. An unavailable, timed-out, or malformed
authorization response therefore cannot fall through to the target.

The authorization service consumes exactly five trusted semantic inputs:

- `:method`
- `:path`
- `x-request-id`
- `authorization`
- `x-kil-q-state`

Envoy's raw HTTP `ext_authz` protocol conveys the original method and path as
the authorization request's method and path, and automatically includes Host,
Method, Path, Content-Length, and Authorization. The configured
`allowed_headers` matcher therefore adds only `x-request-id` and
`x-kil-q-state`. Host and Content-Length are transport metadata and must not
enter authorization evaluation. Their presence does not expand the five-input
semantic contract above.

The adapter must not forward client-supplied `x-kil-mode`,
`x-kil-local-evidence`, `x-kil-verified-subject`, `x-kil-issuer`, or any
undeclared header into trusted evaluation. Track, audience, expected subject,
action mapping, and local evidence come from read-only server configuration or
the server-side fixture store. `authorization` is consumed for the baseline
comparison and must be redacted from all logs.

On permit, the service returns an allow response and the
`x-kil-decision-digest` value for Envoy to record and pass to the harmless
target. On policy denial, the client receives a generic HTTP 403 response with
no internal reason; on authorization-service error, it receives the configured
generic HTTP 503 response. Both paths expose the decision digest to the run
collector without exposing the signed state or credential. The digest, track,
run ID, and request ID are the join keys for the authoritative JSONL record.

V3B accepts a denial as pre-execution evidence only when the joined record
contains all three facts: the KIL decision denies, Envoy does not forward the
request, and the target workload has no matching invocation marker. V3A's
in-process `ReferenceGateway` tests this contract but does not validate Envoy,
Kind, networking, or cluster latency.

The approved topology and boundary details are documented in:

- [`docs/architecture/v3-envoy-live-validation.svg`](../../docs/architecture/v3-envoy-live-validation.svg)
- [`docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`](../../docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md)
- [`docs/lab/V3-PROGRESS.md`](../../docs/lab/V3-PROGRESS.md)

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
