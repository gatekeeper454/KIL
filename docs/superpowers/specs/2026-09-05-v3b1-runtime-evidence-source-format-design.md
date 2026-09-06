# V3B-1 runtime evidence source-format correction

**Date:** 2026-09-05

**Status:** Implemented and locally verified; publication pending

**Scope:** V3B-1 local-Envoy evidence production and collection only

## Purpose

Correct the real-runtime evidence incompatibilities exposed by the first Task
11 exactly-once attempt without weakening the closed evidence schema, changing
the expected authorization result, or retrying a consequential request.

The failed run observed the intended enforcement tuple: the credential-policy
baseline and signed-state tracks returned HTTP 200 and reached their targets,
while the signed-plus-local-reduce track returned HTTP 403 and did not reach its
target. The run was correctly nonpromotable because its authoritative
authorization and Envoy records did not satisfy the existing closed source
format.

## Observed incompatibilities

The preserved stopped-container sources establish three distinct problems:

1. Envoy forwarded the fixed transport-generated headers
   `x-envoy-expected-rq-timeout-ms` and `x-envoy-internal` to the HTTP
   authorization service. The service recorded them as untrusted even though
   the configured client-supplied adversarial headers were correctly excluded.
2. Envoy's JSON formatter emitted response codes as JSON numbers and missing
   denial upstream values as JSON `null`. The evidence contract requires string
   response codes and the explicit `"-"` sentinel.
3. The immediate live evidence copy observed one authorization ledger path as
   absent. Teardown later recovered all three durable decision records, so
   immutable evidence reads need a bounded availability check that does not
   replay or otherwise affect the request.

## Design constraints

- Preserve the existing `kil.v3b1-manifest.v3` and
  `kil.v3b1-public-manifest.v3` schemas.
- Preserve byte-exact source attestation: do not rewrite an observed source
  after collection and claim the rewritten bytes were emitted by a container.
- Preserve v1, v2, and existing v3 offline verification behavior.
- Keep the expected central outcome exactly `permit / permit / deny`, HTTP
  `200 / 200 / 403`, and target markers `1 / 1 / 0`.
- Never retry a request after durable intent. Evidence-read retries must not
  start a driver, write an instruction, or send HTTP.
- Reject arbitrary or client-controlled headers at the authorization boundary.
- Keep raw credentials, signed state, host paths, profile names, and execution
  nonces outside public evidence.

## Source-format correction

### Authorization transport metadata

The authorization HTTP adapter will classify exactly
`x-envoy-expected-rq-timeout-ms` and `x-envoy-internal` as ignored transport
headers, alongside `host` and `content-length`. They will not appear in
`untrusted_header_names` and will not influence authorization. No prefix or
wildcard is permitted. Any other non-trusted, non-transport header remains
untrusted and is recorded under the existing bounded, redacted contract.

The Envoy configuration's explicit `allowed_headers` set remains limited to
`x-request-id` and `x-kil-q-state`. Client-supplied adversarial headers must
remain absent from authorization input, and the central joined decision must
continue to require an empty `untrusted_header_names` list.

### Canonical Envoy access log at the producer

The Envoy stdout access logger will use a text-format source containing one
canonical JSON object followed by one newline. Every substitution is enclosed
as a JSON string. This forces the emitted record to retain the existing closed
shape:

- `response_code` is a three-digit string;
- a permitted request has a nonempty `upstream_host` and canonical decimal
  `upstream_service_time` string; and
- a denied request uses the literal string `"-"` for both upstream fields.

All keys and literal JSON syntax are fixed by repository code. The only dynamic
values are already bounded identifiers, digests, response facts, and Envoy
format substitutions. The configuration validator and tests must prove that
the exact inline format is a single JSON line, includes no authorization or
signed-state material, and preserves the existing access-log field set.

Producer-side canonicalization means the bytes frozen from Envoy are the same
bytes parsed, joined, published, hashed, and verified. No post-collection
normalization is introduced.

## Bounded evidence availability

Live collection will replace each immediate ledger copy with a bounded
read-only availability sequence:

1. Probe the exact journal-bound container ID and literal ledger path using the
   existing closed ledger probe.
2. Accept only a regular file with bounded byte count and SHA-256 metadata.
3. Copy the file using the exact container ID and literal destination.
4. Recompute the copied byte count and digest and require equality with the
   probe.
5. If the path is not yet present, repeat only this probe/copy sequence until
   one shared five-second monotonic deadline expires. Each subprocess timeout
   is clipped to the remaining budget, and polls use an injected 50-millisecond
   wait. Do not retry malformed, oversized,
   nonregular, digest-mismatched, or ambiguous results.

The retry loop has no request-driver handle and cannot invoke the request path.
It is an evidence-read stabilization step only. Exhaustion is terminal and
requires `down`; it never authorizes another central request.

Envoy stdout collection remains an exact `docker logs` read. Its single record
must pass canonical JSON and the unchanged closed Envoy validator before a
complete bundle can be created.

## Failure handling and recovery

Any producer-format, ledger-probe, copy, canonicality, cardinality, join, or
checksum failure leaves the run nonpromotable. The operator must execute
`down`, which freezes all nine authoritative sources before service removal,
proves exact 15-container and 6-network absence, compares foreign-resource
snapshots, and publishes only the permitted failure class.

The prior failed run remains immutable and nonpromotable. The correction must
not reinterpret, rewrite, or promote its bundle or private frozen sources.

## Test strategy

Implementation will follow test-driven development with these red gates:

1. Authorization-adapter tests reproduce the two fixed Envoy transport headers
   and require an empty untrusted-header list while proving an arbitrary header
   is still recorded.
2. Envoy configuration tests require the exact canonical JSON text format and
   reject the typed JSON formatter that produced numeric and `null` values.
3. Evidence tests retain closed rejection of the exact numeric/`null` shapes
   from the failed run, then prove the corrected producer's string/sentinel
   records pass unchanged through parsing and the complete join.
4. Collection tests simulate a missing-then-present ledger, require bounded
   probe/copy success, and prove no driver or request operation occurs.
5. Timeout and integrity tests prove missing, malformed, nonregular,
   oversized, digest-mismatched, and ambiguous sources fail closed without an
   unbounded retry.
6. The full repository suite, generated-reader check, `git diff --check`,
   bundle verifier tests, and secret scan must pass.

## Publication and rerun gate

The correction must pass specification review, quality/security review, local
validation, public CI, merge, and exact local/remote synchronization before a
new lifecycle begins. The newly authorized live attempt must start from that
new public commit in a separate clean worktree and execute:

`preflight` → `up` → exactly one `run` → `collect` if still required by the
controller state → exactly one `down` → checksum, join, teardown, privacy, and
offline `view --bundle` verification.

If `run` already performs and returns the complete collection, the separate
`collect` command must not duplicate it. The operator will inspect durable
journal state and the returned path before deciding whether `collect` remains
required. No request command may be repeated.

Only the exact bundle accepted by public `view --bundle` may be force-added.
Documentation may claim one observed accepted local-Envoy result but must still
exclude Kind/Calico enforcement, NetworkPolicy validation, historical
prevention, production readiness, and performance conclusions.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
