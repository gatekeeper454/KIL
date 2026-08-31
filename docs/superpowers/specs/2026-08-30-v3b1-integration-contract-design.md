# V3B-1 Transcript-Driven Integration Contract Design

## 1. Decision and scope

V3B-1 will harden only the local laboratory harness around the already-reviewed
KIL authorization implementation. The trust-decay model, `kil.q-state.v0`
claims, signature verification, authorization outcomes, Envoy policy semantics,
and harmless target semantics are frozen for this phase.

The phase closes four installed-runtime ambiguities discovered during the first
three local Envoy attempts:

1. host port readiness was first tested by the irreversible demonstration
   request;
2. request failures lacked stage and errno provenance;
3. tmpfs evidence was copied only after its containers had stopped; and
4. object absence depended on Docker's version-specific error prose.

The three private failed-run directories remain immutable, ignored inputs. New
tracked fixtures contain only closed, sanitized transcripts needed to reproduce
the contract gaps; they may not contain credentials, signed states, keys,
account identifiers, absolute private paths, or raw exception messages.

## 2. Non-consuming readiness contract

After all nine containers and three networks pass immutable attestation, the
controller creates one `HTTPConnection` per fixed localhost gateway port and
calls `connect()` under a single bounded deadline. A successful TCP handshake
sends no HTTP request bytes and therefore must not create a request intent,
Envoy access record, authorization decision, or target marker.

All three connections must be ready before the first request intent is
persisted. The controller keeps the successful sockets open. For each track it
then issues any required short-lived signed state, persists exactly one request
intent, and sends the sole HTTP request on the already-connected socket. A
readiness failure closes every socket, journals only closed readiness metadata,
and enters nonpromotable teardown without changing any request state from
`not_attempted`.

No failure after request intent may retry, reconnect, or promote the run.

## 3. Closed request-failure provenance

Request failure evidence is a closed object containing only:

- `stage`: `request_send`, `response_headers`, or `response_body`;
- `exception_class`: one allowlisted built-in transport exception name;
- `errno`: an integer or null;
- `errno_name`: the corresponding fixed `errno.errorcode` value or null;
- `connect_monotonic_ns`, `send_monotonic_ns`, and `failure_monotonic_ns`;
- `request_bytes_may_have_been_sent`;
- `attempt_count`, fixed at `1`; and
- `retry_performed`, fixed at `false`.

Readiness failures use a separate `readiness_connect_failed` event and never
enter request-failure state. Raw exception text, request headers, credentials,
compact JWS values, private keys, and environment data are forbidden from both
the journal and public bundles.

## 4. Evidence freeze and independent source status

Teardown freezes the request boundary before destroying evidence:

1. stop and attest the three Envoy containers;
2. capture each stopped Envoy log independently;
3. while authorization and target containers remain running, attest the exact
   ledger path inside each container and record its byte count and SHA-256;
4. copy each present ledger, then verify the copied byte count and SHA-256;
5. parse each copied source without discarding its raw bytes;
6. persist the nine per-track source results durably; and only then
7. stop and remove authorization and target containers.

Each source result is one of `copied`, `missing`, `copy_error`, or `malformed`.
A zero-byte source is `copied` only after positive in-container observation and
matching host copy. `missing` is never synthesized into an empty ledger.
Malformed copied bytes are retained privately and recorded as `malformed`.
Any source not `copied`, or any required copied source with invalid cardinality,
makes the bundle incomplete and nonpromotable but cannot interrupt exact owned
cleanup.

## 5. Inventory-based exact absence

Container and network removal always addresses the recorded full object ID.
After each removal command, the controller obtains command-local, no-truncation
Docker inventories containing only closed JSON projections of full IDs and
names. Successful inventory—not stderr wording—is the authority for absence.

The removed ID and fixed name must be absent, and all expected remaining owned
objects must still be present. Inventory command failure, malformed JSON,
duplicate IDs or names, shortened IDs, or an unexpected owned-name mapping is
ambiguous and stops automatic deletion. Before network removal, the existing
single closed network inspection must prove exact empty membership.

Recovery replays a persisted removal intent by inventory first. If the exact
object is already absent it records completion without a second delete. If it
is present and still matches the recorded immutable identity, it issues one
exact delete. No wildcard, prefix discovery, global Docker context mutation, or
unrecorded object deletion is permitted.

Ownership is never inferred from a fixed name alone. The object kind, fixed
name, and full ID must be durably paired before recovery can adopt or mutate a
present object. The transient image validators run without Docker `--rm`; each
validator has an explicit persisted full ID, exit and immutable-configuration
attestation, stop transition, removal intent, and survivor-inventory proof.

Container and custom-network inventories are one joint recovery observation.
Pending-and-absent removals, including validators, are collected first; the
journal records completion only after both command-local snapshots validate
the exact survivor sets. Any ambiguity in either snapshot causes no journal
mutation and no deletion.

## 6. Partial-up failure recovery

When `up_complete` is absent, teardown cannot claim source evidence and must not
enter the nine-source freeze. It immutably records the exact survivors first
observed in `partial_up_evidence_rejected`, stops and attests any recovered
containers as applicable, and rejoins the full-ID inventory removal path. On a
retry, that initial survivor attestation remains unchanged while the durable
creation and removal transitions authorize the legitimately shrinking current
set. Replacement IDs and names remain fail-closed and untouched.

The fixed post-teardown failure-bundle replacement intent is persisted before
any container, network, or dedicated-profile mutation. Once both inventories
are empty and profile absence is verified, recovery may materialize only the
deterministic incomplete, nonpromotable failure bundle authorized by the
durable partial-up rejection and replacement intent. Profile-absent recovery
does not require a provisional attestation that could not have existed before
profile deletion, and it never invents source evidence.

## 7. Authoritative offline presenter

An accepted completed bundle contains deterministic `live.html` bytes derived
only from the closed public manifest, normalized decisions, joined outcomes,
and fixed causal reasons. The page has a deny-by-default content-security
policy, inline CSS only, no scripts or external assets, escaped projected
values, and explicit `local`, `intermediate`, and `not promoted` limitations.
It is checksummed and part of the authoritative bundle, but it neither decides
acceptance nor contributes to the content-addressed run ID.

The public manifest publishes the safe `kil.v3b1-content-identity.v2` preimage:
the raw Docker socket is represented by the fixed logical Colima-profile
endpoint and the execution nonce by its SHA-256. An offline verifier recomputes
the content identity, run ID, cross-field pins, all canonical public records,
source-byte bindings, joins, presenter bytes, and the non-circular public
commitment. It retains no-follow directory descriptors and file identities
through semantic verification, rejects sensitive strings recursively, and
accepts only the exact completed `permit / permit / deny`, `200 / 200 / 403`,
and `1 / 1 / 0` local-boundary proof. The `view --bundle PATH` command performs
no writes, browser action, Docker action, or Colima action and prints only the
verified presenter path.

Publication uses descriptor-relative, no-follow atomic rename plus directory
fsync and post-rename reattestation. A failed final check moves the exact entry
to a collision-safe private quarantine rather than exposing or deleting it.
The public commitment proves internal bundle consistency, not publisher
authenticity; a trusted Git revision, release signature, or separately conveyed
checksum remains an external distribution requirement.

## 8. Transcript and smoke validation

Tracked tests replay the sanitized installed-runtime shapes from the three
failed cycles: immutable image-label merge, one-object network JSON, a staged
socket failure, independent missing/copy-error evidence legs, and successful
post-removal inventories. A reconstructed fixture must say so and cannot be
described as an exact historical transcript.

Before another central proof, a live contract-only cycle runs `preflight`,
`up`, and `down` without `run`. Acceptance requires:

- no request intent or request bytes;
- no authorization decision or target marker;
- exact lifecycle ownership and source-status records;
- exactly one nonpromotable smoke/failure bundle with valid checksums;
- all recorded containers and networks absent;
- `kil-v3-lab` absent;
- the pre-existing global Docker context unchanged; and
- any temporarily paused foreign Colima profile restored exactly.

Only after that smoke passes may one new central proof attempt execute. The
proof is accepted only for `local_envoy_boundary` when the joined outcomes are
`permit / permit / deny`, target markers are `1 / 1 / 0`, every source is
complete, all checksums pass, and exact teardown passes.

## 9. Publication and backup boundary

The accepted implementation, tracked fixtures, tests, design, plan, progress,
lineage, and public evidence references are committed on the feature branch.
Private failed runs, downloaded tools, private journals, credentials, keys, and
unredacted runtime material remain ignored and are never pushed.

The generated artifact root remains broadly ignored. Only after `view` accepts
one exact completed run and a closed checksum and secret review passes may that
single directory be staged with:

```bash
git add -f artifacts/generated/v3b1-local-envoy/<accepted-run-id>/
```

Never force-add `artifacts/generated/`, its V3B-1 parent, a wildcard, a failed
run, or `live.html` by itself. The presenter travels only with its exact public
JSONL, manifest, raw decision sources, summary, and `SHA256SUMS` bundle.

After review and CI, the feature branch is pushed, merged through GitHub, and
local `main` is fast-forwarded to the exact public `origin/main`. Final readback
must show equal commit IDs, clean tracked trees, passing tests, and valid public
artifact checksums. The feature worktree is retained until private failed-run
evidence has been intentionally included or excluded from the user's separate
offline-backup procedure.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
