# Gate V3 implementation progress

## V3A status

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

## V3B-1 current status

Through implementation commit
`14ed92dfb1431fb2e4c3f588ff19ad07122f11fe`, V3B-1 implements the pinned local
Envoy `ext_authz` boundary, the transcript-driven readiness, provenance,
evidence-freeze, exact-inventory teardown and partial-up recovery contracts,
and a deterministic authoritative offline presenter. Subsequent publication-
recovery hardening closes repaired-checksum and post-validation completion
races without changing the live boundary. Fresh static verification at the
current branch checkpoint passed 174 controller tests and 389 repository tests,
plus Python compilation and diff hygiene.

Three exploratory local cycles were rejected and remain private. The first
committed zero-request smoke completed from merged public source
`47c0614d49ec1a7484cdefd04cc5d080adc73ca2` with run ID
`v3b1-1db8b5914ce26e2e6c60e74124bcc1b2c9ed66b7dd68c2d3cf4ea1bc0d18c9b3`.
Its eight request, normalized-decision, Envoy, target, join, and raw-decision
JSONL files were exactly zero bytes. `SHA256SUMS` verified, the manifest was
`run_complete=false`, `promotion_status=not_promoted`, and teardown was
complete and verified before publication. Nine service containers, three
transient validator containers, all three networks, and only the dedicated
profile were removed; lifecycle state, readiness poison, and the active journal
were absent; the foreign `default` profile was restored to Running/containerd/
4 CPU/4 GiB/20 GiB. The smoke manifest SHA-256 is
`24176666cc860cfe0b66a67f8a63d0f63d66b4f91329e06464b1475eb84e55c4`.
The ignored nonpromotable bundle remains private for offline backup.

The run safely exercised teardown and foreign-runtime restoration, but it did
not pass the zero-request evidence-freeze gate. The durable lifecycle journal
records all three requests as `not_attempted`; all nine sources were observed
as zero bytes; and the three Envoy legs were copied and byte-bound. Docker
copy failed for all six authorization and target ledgers, however, so the empty
failure bundle does not independently prove those service sources were absent.
No V3B-1 enforcement run has been accepted, promoted, or labeled validated.

The exact-byte correction is now implemented and statically verified. If the
normal Docker copy fails, the controller executes a fixed, no-shell exporter in
the attested service container; bounds and opens the real ledger without
following symlinks; requires a stable regular inode and size; emits its exact
bytes, count, and digest in a closed canonical envelope; and requires the host
to recheck that envelope against the independent pre-copy observation before
freezing it. It never synthesizes an empty file from metadata. Empty, nonempty,
malformed, mismatched, oversized, and symlink cases are covered, including
direct subprocess execution of the real exporter. Independent review found no
Important or Critical issue. Fresh static verification passed 180 controller
tests and 396 repository tests, plus Python compilation and diff hygiene. The
remaining risk is the real Docker path, which is the purpose of the repeated
zero-request gate.

The first two post-merge launch attempts remained pre-profile and
non-enforcement events. The first could not expose the repo-pinned Docker CLI to
Colima's dependency check; the second used the corrected explicit PATH but
Colima v0.10.3 rejected `--nested-virtualization=false` during actual launch,
despite advertising the boolean option in help mode. Neither attempt created
`kil-v3-lab`, a Docker object, or a request; each journal records all request
states as `not_attempted` and was archived through `down`. The foreign `default`
profile was restored to its exact Running/containerd/arm64/4 CPU/4 GiB/20 GiB
state. The minimal compatibility correction removes only that redundant false
CLI flag. The saved-config attestation still requires
`nestedVirtualization: false` before any service container may deploy. Static
verification remains 180 controller tests and 396 repository tests.

The corrected zero-request lifecycle then passed from synchronized public main
`6706859d265204e0a569ebb6817d187dc1728f9d` as run
`v3b1-0374c771b23adcab64060cd8c854d12b72417ff8e4713d24e6f6a550e20bdbea`.
No `run` command or request intent occurred. All nine Envoy, authorization, and
target source legs terminated `copied`; every source and copied byte count was
zero and every digest was the empty SHA-256. All 11 public `SHA256SUMS` entries
verified. The manifest remains intentionally `run_complete=false`,
`promotion_status=not_promoted`, and
`intermediate_provisional_failure_local_boundary`; it does not claim an
enforcement result. Teardown removed nine services, three transient validators,
three networks, and only `kil-v3-lab` before publication. No active lifecycle
state remains, and the foreign profile was host-verified after restoration as
Running/containerd/arm64/4 CPU/4 GiB/20 GiB.

This result accepts the zero-request lifecycle and evidence-freeze gate. The
offline presenter correctly rejects the smoke because it is not an accepted
local-boundary run; presenter acceptance remains an exit criterion for the one
central proof.

V3B-1 is limited to the local Envoy boundary. Full local-cluster transport
validation remains V3B-2: the isolated Kind/Calico topology, approved failure
matrix, target-side markers, and cluster-level measurements are still
unexecuted.

## Architecture

![Approved V3 Envoy live-validation architecture](../architecture/v3-envoy-live-validation.svg)

The source diagram is
[`docs/architecture/v3-envoy-live-validation.svg`](../architecture/v3-envoy-live-validation.svg),
and the complete approved specification is
[`docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`](../superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md).

## Next gate

Publish and merge the corrected zero-request smoke references. Then execute
exactly one central V3B-1 `preflight` / `up` / `run` / `down` proof from clean
synchronized main, with no retry after request intent. Require
`permit / permit / deny`, HTTP `200 / 200 / 403`, target markers `1 / 1 / 0`,
exact source joins and checksums, verified teardown, restored foreign runtime,
and offline presenter acceptance. V3B-2 and V3C remain separate later gates,
and all V3A output remains explicitly modeled.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
