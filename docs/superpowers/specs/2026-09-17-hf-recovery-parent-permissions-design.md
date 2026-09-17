# Mode-only remediation of the fixed HF recovery evidence parent

Date: 2026-09-17.

Status: The user answered "approved" to the minimal descriptor-anchored design
presented after T431. Design approval is CONFIRMED. This written specification
awaits user review before writing-plans. No implementation, chmod or new recovery
attempt is authorized by this document.

## Goal and boundaries

Remove only the evidence-parent mode blocker from the refused compact residual
VM recovery attempt. Authenticate the existing directory, make at most one
0755→0700 permission operation through its retained descriptor, and verify the
directory identity, ownership and observed children without editing any receipt.

This is not VM recovery, resource release, receipt repair, directory adoption or
an extension of the spent stop permission. The attempt recorded by T430 returned
preflight_refused/Stop0 before new evidence creation or native VM commands.
Current VM status remains unobserved. Fixing this mode condition does not promise
that all later recovery preflight conditions will pass.

The alternative is leaving the parent unchanged and retaining the blocker.
Replacing/moving the parent, selecting another evidence root or relaxing the
accepted recovery guard are outside the approved design.

## Fixed target and expected identity

Repository:
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL`.

Sole permission target:
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL/.tools/hf-recovery-private`.

Expected device16777232/inode612764151, directory type, real/effective UID501 and
owner UID501. Expected initial permission bits0755; intended final bits0700.
Any different inode/device/type/owner or initial mode refuses; including an
already0700 directory, which may be reported as observed but receives no mutation.
Never normalize another mode or substitute a newly created directory.

Actual passwd home must be `/Users/mistorm`. Real/effective identity and passwd
home are rechecked before mutation and final acceptance. The existing `.tools`
parent is expected device16777232/inode612669178, UID501-owned0700 directory;
it must not be chmodded. Other directory ancestors retain their independently
observed device/inode/type/mode/UID identities, not frozen timestamps/rosters.

These pins derive from T430/T431, not an upstream attestation. Their observation
is historical; future execution must freshly authenticate them without repinning.

## One-shot architecture and engineering file scope

The future plan may implement a dedicated fixed-target one-shot procedure in
`tools/hf_recovery_parent_permissions.py`, tested by
`tests/test_hf_recovery_parent_permissions.py`. It is separate from the accepted
stop-only tool and introduces no reusable recovery API or caller-selected target.
No source implementation is part of this specification checkpoint.

Read-only dependencies may supply clean-source/account/canonical-output helpers
and no-follow proof patterns. Do not edit production Native/Runtime/IO/Profile,
the accepted recovery tool/tests, strict verifiers or launcher. Do not invoke
launcher main, RuntimeAuthority creation, a lifecycle, _Native or native tools.
Import and CLI argument rejection must not open the real target or mutate state.

The execution entry must require --reviewed-source with an exact40-hex source,
--execution-approval with the actual nonblank valid-UTF-8 approval text (at most
4096 bytes), and --execute-approved-mode-change as a required true flag. Reject
flag abbreviations and target/path/home/mode/tool/receipt/retry/rollback overrides.
Argument errors exit2 before real access; confirmed change alone exits0, handled
refusal/uncertainty exits1. The plan must show the actual command after fixture
verification without inventing approval or accepting an observed mode as success.

## Proof, existing lock and preflight

Require the exact clean reviewed Git HEAD before acquiring the lock or making
any filesystem mutation. Preserve source warnings and exceptions; never filter
them to manufacture clean status. Use the existing managed detached worktree:
no new branch/worktree, relocation, install, merge or push.

Walk read-only/no-follow directory descriptors from `/` to the repository,
`.tools`, existing lock ancestry and fixed target. Recheck each named directory
against its held descriptor before/after all observation IO. Never follow a
target or ancestor symlink, tolerate a partial ancestry or create missing state.

Hold the existing cooperating LabLock's lock location/protocol throughout:
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL/.tools/hf-exploratory-private/profile.lock`.
Its parent must already be UID501-owned0700. Open only this already-existing
UID501-owned0600 regular single-link file, bounded to1MiB, with no-follow and
without O_CREAT. Acquire the same nonblocking exclusive flock as LabLock.
Retain the named/held device/inode/mode/UID/link-count/size/mtime_ns/ctime_ns and
authenticated bounded bytes until final closure; refuse busy or substituted lock.

Do not call the ordinary LabLock create-capable __enter__ path: it can create
missing parents/lock, violating this mode-only scope. Reusing the existing lock
protocol is not a new authority, general lock API or arbitrary external exclusion.
All acquired descriptors must close on every path, and late teardown errors must
retain actual mutation history instead of becoming a zero-attempt startup claim.

Record the target's named/held device/inode/type/mode/UID/GID/link-count/size and
nanosecond mtime/ctime. Collect two equal bounded direct-child observations using
the held target descriptor and no-follow metadata only. At most256 direct names;
each must be a nonempty basename of at most128 UTF-8 bytes, with no slash, NUL,
`.` or `..`. Stop enumeration/refuse at the257th name. Do not interpret, follow,
open or traverse children; record their type and full stat fields above.
Directory enumeration/stat errors or unequal complete observations refuse.

Immediately repeat source/account/lock/ancestry/target/child authentication.
After all content/enumeration IO, perform a final metadata-only named/FD closure
before mutation, with no later directory listing, file read or native acquisition.
Require the same preflight target and child commitments, not a replacement baseline.

## Sole mutation and postconditions

Consume the procedure's slot before entering exactly one
`os.fchmod(held_target_directory_fd, 0o700)`. Count entry attempts separately from
syscall certainty and observed mode: a raised/lost result never authorizes a
second call. No path-based or recursive chmod, chown, ACL/flag repair, file write,
rename, mkdir, unlink or directory replacement. Do not chmod ancestors/children.

If the call returns normally, fsync the retained target directory and obtain
fresh stable bounded read-only post-observations. Confirmation requires the same
named/held target device/inode/type/UID/GID/link-count/size/mtime and mode0700;
its ctime is expected to change and is captured, not compared with initial ctime.
Close final named/FD continuity against the fresh post identity. Ancestor and
lock identities/bytes and the exact direct-child roster/stat commitments must
remain unchanged. Recheck source and account after observation IO, then final
metadata-only proof closure and all owned teardown before accepting success.

0700 intentionally removes group/other mode-based access through this parent;
it does not change children's own modes or promise a broader access-control
assessment. Direct-child stat equality is not a descendant-content attestation.
The procedure itself must write no receipt bytes and perform no recursive
traversal/hash; it cannot promise absence of arbitrary external descendant writes
or an atomic filesystem snapshot. Do not overstate preservation from metadata.

## Honest result and evidence

Keep outcomes separate: preflight_refused, mode_change_confirmed,
mutation_uncertain and postverification_inconclusive. Record reviewed source,
actual execution approval, fixed target/pins, entry-attempt count, syscall
certainty, observed pre/post mode and identity/child/lock preservation status.
Record earlier and late teardown exceptions, at most16 records, each with a
type of at most128 UTF-8 bytes and message of at most4096 UTF-8 bytes; overflow
must refuse confirmation, not discard failures to claim success.

Known precheck refusal has0 fchmod attempts. Entered-call failure has1 attempt
and uncertain syscall result even if later mode is0700. A normally returned call
with failed fsync/post/source/closure/teardown is postverification_inconclusive,
not confirmed and not an invented zero attempt. Observed mode and syscall success
remain distinct from complete preservation verification.

Use bounded canonical stdout (at most1MiB) for the result, captured by root and
recorded verbatim as appropriate in factual plan/lineage. Do not create a new
private receipt, date directory, alternate suffix or overwrite earlier exports.
No seal is claimed for an uncreated evidence directory. Root records only actual
observations and regenerates readers after the procedure ends.

Any refused/uncertain/postcheck-failed attempt ends its permission. Do not retry,
automatically restore0755, roll back metadata, adopt changed state or launch the
recovery tool. If observed mode changed but proof failed, preserve that fact and
request direction. Never hide a partial result by repair/rebaseline/reseal.

## Test-first verification and approval gates

After user review of this written specification, use writing-plans to detail
fixture-only implementation and exact checks. Before adding mutation behavior,
run genuine failing real-owned-temp tests. Mock only unavoidable source/account
selection or inject narrowly controlled syscall failures; use real descriptor
ancestry, existing flock, stat/enumeration, files, fchmod/fsync and cleanup.

Required tests: preserved fixture receipt payloads/seals/child modes; exact one
0755→0700 change with same inode/owner; wrong UID/type/mode/device/inode refusal;
target/ancestor symlink or replacement; missing/busy/substituted lock with no
creation; child roster/metadata drift and256/257 bounds; precheck source/account/
late-IO drift yields0 calls; fchmod/fsync/post/final-closure/teardown failures retain
actual attempt/observed-mode history; no retry/rollback/recovery/native call;
all descriptors released, import/invalid CLI no real access. Important review
findings receive a failing regression before the minimum scoped fix.

Use the existing Python3.12 interpreter at
`/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python`,
bytecode disabled, PYTHONPATH=src and ResourceWarning fatal. Run the new tests
and relevant retained-proof/IO/recovery regressions. Require independent spec
and quality review plus root verification before permission execution. Fixture
GREEN is not a live permission change or a recovered VM.

Verify exact protected paths, append-only predecessor lineage, canonical new
citations, generated readers, scoped local commit and clean exact HEAD. Do not
repair or exempt the four known immutable historical citation omissions or claim
full discovery green from scoped checks.

Written-spec approval authorizes writing-plans and fixture-only preparation,
not actual fchmod. After verified preparation, ask explicit approval for one
fixed mode-change attempt and use the scoped outside-sandbox route if required.
After that attempt ends, any VM recovery needs NEW separate one-stop approval;
T430's spent permission is not revived by absent intent or corrected permissions.

No runtime/guest/disk access, Colima/Lima/Docker/Kind/kubectl operation, HF request,
Ollama, image audit, SSH compatibility change, rehearsal, force/delete/restart or
implicit continuation. Platform-image provenance stays unverified, full Kind/
Calico acceptance false and accepted local Envoy unchanged. HF readiness retains
its separate compatibility, request-free rehearsal and live-action gates.

## Spec self-review

The sole pinned directory/0755→0700 operation, unchanged descendants, no-follow
held-FD proof, open-existing-only cooperating lock, finite child observations,
separate attempt/certainty/mode/preservation outcomes, no rollback/retry and
design/spec/engineering/execution/recovery approval boundaries are explicit.
This document contains requirements, not unverified implementation or a claim
that its future engineering/execution has passed. User review is required next.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

## Written-spec approval record — 2026-09-17

The user answered "approved" to review of this written spec at clean checkpoint
8b5714377cce4e3dffdf5ce6aaec926a5247099a. Written-spec approval is CONFIRMED;
writing-plans and fixture-only test-first preparation may proceed. The historical
pending status above records the document's earlier checkpoint, not the current
gate. Actual fixed-target fchmod and a subsequent native recovery attempt each
remain separately unapproved. Retain the user's subagent-driven preparation and
independent-review preference; do not revive the spent T430 stop permission.
