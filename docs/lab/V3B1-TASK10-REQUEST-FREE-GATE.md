# V3B-1 Task 10 request-free live-gate record

## Status

Task 10 passed at the local Envoy boundary on 2026-08-31. This record is a
public-safe projection of the ignored local bundle and its archived lifecycle
journal. It records an observed request-free lifecycle result, not an
enforcement outcome and not a validated Kind/Calico cluster result.
It is historical driver-era v2 evidence: because it lacks durable exact
before/after foreign-resource snapshots, it does not satisfy the v3 evidence
prerequisite for a central proof.

## Public binding

- Source commit: `a46e8dc98a1af64ceadb5700e91c2f87840564fe`
- Run ID: `v3b1-d2b26f6c8136dcd26a6e6727b9bb1381076a1e03b71a5a44df9b2b2ef9db6cf9`
- Content identity: `d2b26f6c8136dcd26a6e6727b9bb1381076a1e03b71a5a44df9b2b2ef9db6cf9`
- Public commitment SHA-256:
  `18bfe97801cfb5f43774c68581da58576147e698f05d56dfac53cc7fa1097da7`
- Public manifest SHA-256:
  `e7dfc3e371a3057152850b196005753b40bafd384fd470b3d501bffa34d0acae`
- Evidence scope: `local_envoy_boundary`
- Bundle class: `intermediate_provisional_failure_local_boundary`
- Promotion status: `not_promoted`
- Lifecycle result: `run_complete=false`

The intentionally incomplete classification is correct. Task 10 never issues a
consequential request, so it cannot produce a complete enforcement bundle.

## Executed sequence

The approved sequence was `preflight -> up -> readiness -> down`. `Preflight`
verified the three fixed ports, pinned tool identities, clean tracked source,
and observed the pre-existing foreign profile. The archived journal binds the
foreign context name, but does not contain a before-resource snapshot. `Up`
created the twelve fixed
service/driver containers, three transient validators, and six internal
networks from the bound source commit. Request-free readiness produced three
exact readiness records and three clean cancellations. Mandatory `down` froze
the nine service evidence sources, removed all owned objects, proved their
absence, deleted the dedicated profile, restored the foreign context, and only
then published the provisional bundle.

## Observed acceptance facts

- Three exact tracks reached readiness:
  `credential_policy_baseline`, `signed_state_only`, and
  `signed_plus_local_reduce`.
- The readiness session ended with three clean cancellations.
- Zero driver instructions, zero request intents, and zero HTTP requests were
  issued. The archived journal contains no request-side event.
- Nine source-collection legs terminated and nine byte-bound evidence legs
  were persisted.
- Requests, normalized decisions, Envoy records, target records, joins, all
  three raw decision files, and all three raw driver files were zero bytes.
- Every zero-byte evidence file is bound to the empty SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- Every entry in `SHA256SUMS` verified.
- All 15 exact containers and all six exact networks were removed. The
  topology-absence attestation recorded no surviving container or network.
- The dedicated `kil-v3-lab` profile deletion was verified.
- Active lifecycle state, the active journal, and readiness poison were absent
  after teardown.
- The public manifest binds the foreign context name as `default` before and
  after the lifecycle. A post-run read-only Colima observation reported
  `Stopped/containerd/aarch64/4 CPU/4 GiB/20 GiB`; the exact resource tuple was
  not durably bound at both the before and after boundaries and is therefore
  not cryptographic restoration proof.

## Implementation and review boundary

The stopped-endpoint recovery correction was merged through PR #16 after both
required public CI jobs passed. The merged result passed all 484 repository
tests through `make validate`. The gate then executed from that exact merged
commit. These facts establish the request-free V3B-1 lifecycle, readiness,
evidence-freeze, teardown, global-context-name preservation, and post-run
foreign-profile observation boundary only.

They do not establish a KIL enforcement result, historical prevention of the
Hugging Face incident, Kind/Calico or NetworkPolicy behavior, repetition,
production performance, or production suitability. Modeled KTP signals remain
modeled. The central `run` was not executed and remains prohibited until this
record passes independent review, public CI, merge, and exact synchronization
and a tested, merged evidence extension durably binds and verifies exact
before/after foreign-resource snapshots.

## Next gate

The historical v2 record remains unchanged. The fresh request-free v3 successor
gate described below now proves the exact pseudonymous before/after equality
contract from public `main`. The central `run` remains prohibited until that
new public-safe checkpoint passes review, merge, and synchronization. Only
afterward may the project execute exactly one central local-Envoy proof. No
retry is permitted after request intent. Its prospective acceptance criteria remain
three exact terminal driver results, `permit / permit / deny`, HTTP
`200 / 200 / 403`, target markers `1 / 1 / 0`, complete driver/service joins,
verified checksums, exact teardown, restored foreign state, and offline
presenter acceptance.

## Fresh v3 successor gate — 2026-09-05

- Source commit: `5ebf21a88794a9f83a0e6c8ee53e76f6d8e5142d`
- Run ID: `v3b1-4ac0b6eef70b0483f7883c8a26753d15a007f612953b25e23b8ecb6afd021a8f`
- Public schema: `kil.v3b1-public-manifest.v3`
- Public commitment SHA-256:
  `10101f8ddb3d11682955444d5b3330ab5b290f2663302afdd5fade23530cf112`
- Public manifest SHA-256:
  `3572ad5b9f7a2da66ce8b5cf13c020179283c5b1635aef8302977e8c562bb475`
- Bundle class: `intermediate_provisional_failure_local_boundary`
- Promotion status: `not_promoted`
- Lifecycle result: `run_complete=false`

The exact sequence was `preflight -> up -> readiness -> down`; neither `run`
nor `collect` was invoked. All three tracks reached readiness and completed
clean pre-instruction cancellation. The journal contains zero driver
instructions, zero request intents, and zero HTTP requests. All nine
Envoy/authorization/target sources were copied and frozen as exact zero-byte
inputs with the empty SHA-256. Every published `SHA256SUMS` entry verified.
Teardown proved all 15 containers and six networks absent, archived the
completed private journal, and cleared the active state, active journal path,
and readiness poison.

The V3 public attestation contains one run-scoped pseudonymous foreign-profile
reference with status, architecture, CPU, memory, disk, and runtime fields.
Its before and after arrays are exactly equal and `unchanged=true`; raw foreign
profile names remain private. The internal failure-bundle verifier accepted the
nonpromotable diagnostic presenter. Public `view --bundle` acceptance remains
reserved for the later complete central proof.

Foreign-resource restoration therefore has exact equality in the bound V3
attestation, without exposing the private profile name.

This record establishes only the request-free V3 lifecycle, evidence-freeze,
exact teardown, and foreign-resource equality gates at the local Envoy
boundary. It is not an enforcement result and does not establish Kind/Calico,
NetworkPolicy, historical prevention, repetition, production performance, or
production suitability. The central `run` remains prohibited until this
checkpoint passes independent review, public CI, merge, and synchronization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
