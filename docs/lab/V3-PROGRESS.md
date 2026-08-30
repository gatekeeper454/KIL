# Gate V3 implementation progress

## Current status

V3A implements the signed-state and authorization core behind the approved
three-track architecture. The implementation now includes:

- the closed `kil.q-state.v0` claims schema;
- Ed25519 compact-JWS issuance and fail-closed verification;
- a maximum ten-second lifetime plus revocation, time, subject, audience,
  authority-class, and action-class binding;
- infrastructure-fixed credential-policy, signed-only, and signed-plus-local-
  reduction tracks;
- resistance to an untrusted `x-kil-mode` downgrade header;
- a harmless target marker and a joined forward-or-withhold proof; and
- an atomic, content-addressed JSONL/HTML evidence bundle.

The demonstration uses the same request facts in all three tracks. With the
fixed V3A fixture, the expected result is `permit / permit / deny`, with target
marker counts `1 / 1 / 0` and valid joins for all three outcomes.

The first pre-review process run was `52c90309d00439e7` at implementation
commit `ad3db6aa7686781761bd8622a435c279f534df05` with 121 passing tests. The
intermediate review run `b0cdc26b471c9539` at implementation commit
`700b307a573e3668024d51e3b156d7044b03fca3` passed 125 tests but preceded the
final zero-exponent allocation fix. Both are retained only as development
history. The canonical review-complete run is `ca26ff63c09cd78b` at
implementation commit `4e02ed3727096174456de0b6edcb33403d7870df` with 126
passing tests. Its eight published artifacts pass `SHA256SUMS` verification.

The review-complete bundle records the full Ed25519 public-key thumbprint,
public JWK, explicit deterministic Level 1 laboratory-fixture provenance, and
the two audience-bound compact JWS states. No private or production key is
claimed. The bundle is generated under
`artifacts/generated/v3a-process-contract/ca26ff63c09cd78b/` and remains
reproducible from the recorded implementation commit.

## Evidence boundary

V3A is a **modeled process-contract demonstration**. It proves the local
software contracts for signature verification, fixed-mode authorization,
forwarding, target invocation, and evidence joining. It does not run Envoy or
Kubernetes and therefore does not establish a `validated` cluster result.
Synthetic charge, threshold, and local-divergence values remain modeled.

The full transport validation is Gate V3B. That gate must deploy Envoy
`ext_authz` and harmless targets in an isolated Kind cluster, pin runtime and
image identities, exercise the approved failure matrix, collect target-side
markers, and measure cluster-level latency before any result is labeled
validated.

## Architecture

![Approved V3 Envoy live-validation architecture](../architecture/v3-envoy-live-validation.svg)

The source diagram is
[`docs/architecture/v3-envoy-live-validation.svg`](../architecture/v3-envoy-live-validation.svg),
and the complete approved specification is
[`docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`](../superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md).

## Next gate

Gate V3B must resolve the local container runtime and client tooling, pin the
Envoy and workload image digests, implement the HTTP `ext_authz` mapping,
verify Kind network isolation and failure behavior, and execute the cluster
validation protocol. Until then, all V3A output remains explicitly modeled.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
