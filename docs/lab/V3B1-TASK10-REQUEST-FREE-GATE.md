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

The `kil.v3b1-manifest.v3` snapshot extension is now implemented and statically
tested on its development branch, but still requires independent review,
merge, and synchronization. A fresh request-free v3 lifecycle must then prove
the exact pseudonymous before/after equality contract from public `main`. The
central `run` remains prohibited until that gate passes. Only afterward may the
project execute exactly one central local-Envoy proof. No retry is permitted
after request intent. Its prospective acceptance criteria remain
three exact terminal driver results, `permit / permit / deny`, HTTP
`200 / 200 / 403`, target markers `1 / 1 / 0`, complete driver/service joins,
verified checksums, exact teardown, restored foreign state, and offline
presenter acceptance.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
