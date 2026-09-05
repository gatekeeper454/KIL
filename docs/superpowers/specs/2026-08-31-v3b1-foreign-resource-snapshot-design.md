# V3B-1 Foreign-Resource Snapshot Contract Design

## 1. Decision and scope

V3B-1 will durably bind the complete Colima state that the controller does not
own at both sides of every lifecycle. Private evidence retains exact profile
names. Public evidence replaces each name with a run-scoped pseudonymous
reference while retaining every other field returned by the controller's
closed Colima parser. Accepted evidence requires exact before/after equality.

This is a laboratory evidence-integrity extension. It does not change KIL
trust decay, the signed composite KTP enforcement state, the authorization
engine, the request driver, Envoy policy, target behavior, or the expected
`permit / permit / deny` result. The central `run` remains prohibited until
this contract is implemented, reviewed, merged, synchronized, and proven by a
fresh request-free lifecycle from public `main`.

The design advances the private and public evidence manifests to v3. Existing
v1 and v2 bundles remain independently verifiable under their original closed
schemas and cannot be reinterpreted as v3 evidence.

## 2. Security claim

For a v3 accepted bundle, the controller and offline verifier may claim:

> Every non-KIL Colima profile visible through the closed `colima list --json`
> boundary had the same name identity, status, architecture, CPU count, memory,
> disk, and runtime immediately before KIL's first Colima mutation intent and
> after the dedicated KIL profile was deleted, before publication intent.

The public claim omits raw profile names and substitutes stable-within-run
pseudonyms. It does not claim that Colima can observe resources outside its own
profile inventory, that an external actor could not change a profile between
the two samples, or that KIL restored a profile it mutated. KIL must never
mutate a foreign profile.

## 3. Closed snapshot model

The existing `parse_colima_profiles` boundary remains authoritative for raw
profile records. A snapshot canonicalizer adds requirements that are necessary
for equality evidence:

- the snapshot is a JSON array of closed records;
- every record has exactly `name`, `status`, `arch`, `cpus`, `memory`, `disk`,
  and `runtime`;
- string fields are nonempty strings;
- `cpus`, `memory`, and `disk` are positive integers;
- profile names are unique;
- the dedicated `kil-v3-lab` profile is excluded from the foreign set;
- private records are sorted by UTF-8 profile name bytes; and
- public records are sorted by pseudonymous profile reference.

No normalization changes status spelling, architecture spelling, byte counts,
or runtime labels. Equality is exact canonical-object equality, not semantic or
case-insensitive equivalence. This contract does not weaken the existing
preflight rule that prohibits a non-dedicated running profile. The snapshot
helper remains total over syntactically valid stopped or running records so it
can preserve and diagnose an observed state, but an accepted lifecycle still
requires the existing preflight policy.

The private snapshot record is:

```json
{
  "schema_version": "kil.v3b1-foreign-profile-snapshot.v1",
  "capture_stage": "before_colima_mutation",
  "profiles": [
    {
      "name": "<exact-private-name>",
      "status": "Stopped",
      "arch": "aarch64",
      "cpus": 2,
      "memory": 4294967296,
      "disk": 107374182400,
      "runtime": "docker"
    }
  ]
}
```

The after record uses `capture_stage: "after_owned_profile_deletion"` and the
same schema. These records are durable lifecycle-journal events, not mutable
side files.

## 4. Pseudonymous public projection

Raw foreign profile names never enter public artifacts. For each private name,
the controller computes:

```text
profile_ref = HMAC-SHA256(
  key = bytes.fromhex(execution_nonce),
  message = "kil.v3b1-foreign-profile-ref.v1\0" || utf8(profile_name)
)
```

The execution nonce is already private lifecycle authority and is never
published. Domain separation prevents the reference from being confused with
another digest. The controller rejects invalid UTF-8 names, duplicate names,
duplicate references, and any reference that is not 64 lowercase hexadecimal
characters. A reference is stable only within one lifecycle, so bundles cannot
be used to correlate local profile names across runs.

The public v3 manifest contains:

```json
{
  "foreign_profile_attestation": {
    "schema_version": "kil.v3b1-foreign-profile-attestation.v1",
    "before": [
      {
        "profile_ref": "<64-lowercase-hex>",
        "status": "Stopped",
        "arch": "aarch64",
        "cpus": 2,
        "memory": 4294967296,
        "disk": 107374182400,
        "runtime": "docker"
      }
    ],
    "after": [
      {
        "profile_ref": "<same-reference>",
        "status": "Stopped",
        "arch": "aarch64",
        "cpus": 2,
        "memory": 4294967296,
        "disk": 107374182400,
        "runtime": "docker"
      }
    ],
    "unchanged": true
  }
}
```

The public verifier does not need the private name or nonce. It validates the
closed projection, uniqueness, ordering, field types and bounds, then requires
`unchanged == (before == after)`. Complete accepted evidence additionally
requires `before == after` and `unchanged is true`; a structurally valid
nonpromotable failure bundle may retain unequal arrays with `unchanged: false`.
The controller separately regenerates the projection from both private journal
snapshots during publication recovery and requires byte-equivalent agreement
with the public manifest.

## 5. Capture and lifecycle ordering

The before capture occurs only after the private lifecycle journal is created,
so it can be made durable, and before `colima_start_intent`, the first Colima
mutation intent. The required order is:

```text
preflight observation
  -> create lifecycle journal
  -> foreign_profile_snapshot_before
  -> preflight_complete
  -> colima_start_intent
```

The controller obtains a fresh `colima list --json` result for the snapshot. It
does not reuse the earlier preflight value. Failure to parse or durably append
the before record aborts before any Colima mutation.

The after capture occurs after the dedicated KIL profile deletion is complete
and its absence is freshly verified, but before `publication_intent`:

```text
owned-object absence proof
  -> dedicated profile delete complete
  -> dedicated profile absence verification
  -> foreign_profile_snapshot_after
  -> compare exact private snapshots
  -> publication_intent
```

Recovery may resume an interrupted owned-resource teardown, but it must never
synthesize either snapshot. If the before snapshot is missing after a Colima
mutation intent, the lifecycle is nonpromotable. If the after snapshot is
missing, malformed, duplicated, or cannot be freshly captured, publication is
nonpromotable. Recovery must not start, stop, delete, resize, rename, or
otherwise repair any foreign profile.

## 6. Mismatch and failure behavior

Foreign-state mismatch is fail-closed evidence, not a repair instruction.
When exact private snapshots differ, the controller:

1. completes exact teardown of KIL-owned containers, networks, and profile;
2. records a closed `foreign_profile_mismatch` journal event containing only
   the private before and after snapshot digests plus fixed mismatch categories;
3. does not mutate any foreign profile;
4. prohibits accepted publication and any later central request; and
5. may publish only a nonpromotable failure bundle whose public v3 attestation
   has `unchanged: false` and contains both pseudonymous projections.

Mismatch categories are closed: `profile_set`, `status`, `arch`, `cpus`,
`memory`, `disk`, or `runtime`. Raw profile names and execution nonces remain
private. A failure bundle with unequal foreign profiles is diagnostic evidence
and cannot satisfy the fresh request-free gate.

If pseudonym construction or public projection would be ambiguous, the
controller records no public snapshot and the lifecycle remains private and
nonpromotable. Privacy failure cannot be traded for public completeness.

## 7. Schema generation and verifier behavior

The new generation uses:

- private manifest `kil.v3b1-manifest.v3`;
- public manifest `kil.v3b1-public-manifest.v3`;
- authoritative bundle `kil.v3b1-authoritative-bundle.v3`; and
- public commitment `kil.v3b1-public-commitment.v3`.

V3 adds `foreign_profile_attestation` to the public manifest and binds it
through the existing canonical public commitment, `manifest.json`, and
`SHA256SUMS`. No new unbound sidecar is introduced. The private manifest remains
free of raw foreign profile names; exact names stay in the private journal.

Generation dispatch is explicit:

- v1 verifies only the frozen host-published legacy contract;
- v2 verifies only the in-network driver contract without resource snapshots;
- v3 verifies the driver contract plus foreign-resource equality; and
- fields from one generation are rejected in every other generation.

The offline v3 verifier requires the attestation even for an empty foreign
profile set. Empty `before` and `after` arrays are valid only when both are
empty and `unchanged` is true. Complete evidence requires equality; incomplete
failure evidence requires `unchanged` to describe the comparison truthfully
and remains nonpromotable.

## 8. Controller interfaces

Implementation will keep the feature bounded behind focused helpers:

- `canonical_foreign_profile_snapshot(records, capture_stage)` validates,
  filters, orders, and returns one private closed record;
- `project_foreign_profile_snapshot(snapshot, execution_nonce)` returns one
  pseudonymous public array;
- `compare_foreign_profile_snapshots(before, after)` returns exact equality and
  closed mismatch categories without mutating either input; and
- journal-recovery helpers require exactly one durable before event and one
  durable after event at the permitted phases.

The controller's lifecycle methods call these helpers but do not absorb their
schema logic. Publication and offline verification share one closed public
attestation validator.

## 9. Test strategy

Implementation follows RED -> GREEN -> REFACTOR. Static tests must prove:

- closed parsing rejects duplicate names, duplicate keys, unknown fields,
  booleans-as-integers, invalid UTF-8, nonpositive resources, and unordered or
  ambiguous projections;
- the dedicated KIL profile is excluded and every foreign resource field is
  retained exactly;
- private ordering is deterministic and independent of Colima output order;
- pseudonyms are deterministic within one execution nonce, differ across
  nonces, are domain-separated, and never expose raw names;
- before capture is durable before `colima_start_intent` and failure prevents
  all Colima mutation;
- after capture follows verified dedicated-profile absence and precedes
  `publication_intent`;
- exact equality accepts unchanged stopped or running foreign profiles and an
  empty foreign set;
- every field and profile-set mismatch fails closed without a foreign mutation;
- crash recovery rejects missing, duplicate, reordered, synthesized, or
  phase-invalid snapshot events;
- v3 public publication is regenerated from private journal authority;
- the offline verifier rejects changed tuples, repaired checksums, inconsistent
  `unchanged`, duplicate references, and cross-generation fields; and
- existing v1/v2 fixtures remain byte-verifiable under their original schemas.

No static test or implementation task may start Colima or Docker. The later
live request-free gate uses only `preflight -> up -> readiness -> down` and
sends no instruction, persists no request intent, and emits no HTTP request.

## 10. Publication and live gates

The implementation branch must pass the complete repository suite, independent
review, public CI, merge, and exact local/remote synchronization. From that
merged public `main`, one new request-free lifecycle must publish a v3 bundle
showing:

- all three in-network drivers ready;
- three clean pre-instruction cancellations;
- zero instructions and zero HTTP requests;
- exact owned-object teardown;
- a v3 foreign-profile attestation with exact equality; and
- offline failure-bundle verifier acceptance of the nonpromotable diagnostic
  presenter.

The public `view --bundle` path remains reserved for completed central evidence
and must continue to reject request-free nonpromotable bundles. This request-free
gate uses the same immutable snapshot and semantic checks in explicit failure-
bundle mode; it does not relabel diagnostic evidence as an accepted enforcement
result.

Only after that public-safe v3 gate is reviewed, merged, and synchronized may
the founder authorize one central `run`. No consequential request is authorized
by this design or its implementation alone.

## 11. Rejected alternatives

**Digest-only public snapshots** were rejected because an outside reviewer
could confirm digest equality but could not inspect the complete resource tuple
being claimed.

**Raw public profile names** were rejected because local names can reveal user,
project, customer, or operational context unrelated to KIL.

**Restoring foreign profiles on mismatch** was rejected because observation
does not confer ownership. Automated repair would expand KIL's authority and
could destroy legitimate external changes.

**Reusing preflight output as the before snapshot** was rejected because it is
not durably bound to the lifecycle at the first mutation boundary.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
