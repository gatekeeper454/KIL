# Envoy adapter boundary — Gate V3B

Gate V3B will place three independently configured Envoy `ext_authz` routes in
front of harmless target workloads. Each authorization service instance fixes
one track at startup:

1. `credential_policy_baseline`
2. `signed_state_only`
3. `signed_plus_local_reduce`

The request cannot select or downgrade the active track. KIL state is a signed,
short-lived experimental extension envelope that references KTP Trust Proof and
Kinetic Envelope results; it does not replace either KTP construct. The first
lab profile uses Ed25519 compact JWS, track-bound audiences, exact request
binding, a maximum ten-second lifetime, and fail-closed verification.

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
