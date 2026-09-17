# Stop-only recovery of the residual compact HF VM

Date: 2026-09-17.

Status: The user approved the isolated stop-only architecture presented after
T421. This is its written specification, pending user review. Writing this
document does not authorize native execution. No recovery has occurred.

## Goal and scope

Gracefully stop only the private VM left by the inconclusive compact-runtime
rehearsal, if it is still running. Preserve its profile, root/data disks and
sealed evidence. Do not reclaim disk space, repair the production harness,
resume the old lifecycle or launch another rehearsal/HF action.

The selected approach is a separate one-shot manual recovery runbook. Repairing
production inventory compatibility first is broader work and does not itself
authorize operation on this existing runtime. Leaving the VM alone avoids
mutation but does not establish stopped status or release its running resources.

The rehearsal started VZ successfully, established an eight-resource creation
binding and observed an empty private Docker endpoint. It then refused generated
`ssh_config` as an unknown private Colima roster entry. Cleanup refused before
any stop/delete instruction. HF request intents and attempts were both zero;
no Kind cluster, Calico or KIL/Envoy application workload was created.

Running is the last retained native observation, not a current-state assertion.
Fresh recovery preflight must establish Running or Stopped without inference.

## Fixed identity and authority boundary

Full digest:
`254877dc1b1462c4e29c068e51ad7286fe430b075bc5044c8b3076d1887ad25d`.
Run ID is `v3b2-` followed by that entire digest. The short label is a locator,
never an ownership proof.

Repository:
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL`.

Immutable receipt:
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL/.tools/hf-exploratory-private/hf-exploratory-254877dc1b1462c4e29c068e51ad7286fe430b075bc5044c8b3076d1887ad25d`.

Runtime: `/Users/mistorm/.kil-hf/r254877dc1b1462c4`.
Registry: `/Users/mistorm/.kil-hf`.
Actual passwd home: `/Users/mistorm`; real and effective UID must both be501.
Retained runtime-root identity is device16777232/inode615011851/mode16832/uid501.

Profile: runtime/`.colima/kil-v3-lab`.
Lima instance: runtime/`.colima/_lima/colima-kil-v3-lab`.
Data disk: runtime/`.colima/_lima/_disks/colima-kil-v3-lab/datadisk`.
Root disk: runtime/`.colima/_lima/colima-kil-v3-lab/disk`.
Docker endpoint: `unix:///Users/mistorm/.kil-hf/r254877dc1b1462c4/.colima/kil-v3-lab/docker.sock`.

Establish separate, stop-only manual authority from authenticated retained
evidence plus fresh matching observations. Never call RuntimeAuthority.create
on this existing root, construct a replacement RuntimeAuthority, call launcher
main, resume ExploratoryLifecycle or relax its private_inventory guard. Pure
ProfilePaths/capture/binding parsing alone does not grant native authority.
The spent historical4bf recovery runbook concerns another target and is not
permission for this stop.

## Evidence authentication and finite filesystem checks

The receipt's SHA256SUMS is exactly3979 bytes with SHA-256
`d128fd99fcc32391db27804da8be86c0e62b238343b71c7f44009785cba38ad0`.
Require precisely its46 unique fixed basename entries, all matching bounded
regular-file reads. Reject alternate manifests, path components, symlinks,
hardlinks, unbounded files or substituted evidence. Fresh verification during
spec preparation passed all46; future execution must verify them again.

Authenticate and strictly decode the retained report, runtime-binding,
profile-created capture and foreign-original baseline. Require the exact full
ID/paths/UID/root identity, rehearsal source
`7d5c58372040ecf5b7c1fdd9c9d7ea3ddcd06205`, inconclusive report, manual_recovery
true, actual_creation_bound true, zero requests and empty joined results.
Recompute the saved eight-resource binding and require equality with the report.

Retain read-only/no-follow descriptor ancestry independently for receipt and
runtime. Each named directory must match its retained device/inode/type/mode/UID
through final dispatch checks. Registry, runtime, `.colima`, `_lima`,
docker-config and runtime-tmp must be canonical UID501-owned0700 directories;
the four runtime-home identities must match runtime-leftovers.json. Ordinary
ancestor timestamps/rosters are not frozen. Do not scan other registry children.

Authenticate registry.json as the existing canonical schema
`kil.hf-exploratory-runtime-registry.v1`, uid501 and exact runtime_parent.
Marker and receipt runtime-binding must be single-link UID501-owned0600 regular
files, at most8192 bytes. Compare named/retained device/inode/mode/UID/link-count/
size/nanosecond mtime/ctime before and after full reads, and recheck both after
all subsequent guard IO. Missing, partial or changed state refuses; never repair,
chmod, mark or adopt a directory.

While Running, require these exact direct rosters, with no additional children:

- runtime: `.colima`, `docker-config`, `kind-config.yaml`, `runtime-tmp`;
- private Colima: `_lima`, `_store`, `kil-v3-lab`, `ssh_config`;
- private Lima: `_config`, `_disks`, `_networks`, `colima-kil-v3-lab`;
- docker-config: `contexts`; runtime-tmp: empty.

Use the existing bounded no-follow capture for profile/instance/disk/config/
store/protected/startup/lock records. Require two equal fresh captures. The eight
resource identities and three saved config hashes must match the retained
binding; compare profile/instance/disk direct rosters and store bytes against
profile-created.json while Running. Protected/startup must remain absent. The
disk lock must name this exact instance and retain its original identity.
Require raw data60GiB/root20GiB sizes and existing512-byte format probes, not
disk-content immutability or a full disk hash. Ongoing guest writes and orderly
shutdown flushes are not measured as unchanged disk contents.

For a Running candidate, the sole new Colima roster control admitted to this
proof is runtime/`.colima/ssh_config`: canonical single-link UID501-owned0644 regular
file, exactly767 bytes, SHA-256
`0788dfecc6e2e6d6301a2eca6d9bebe153de450cac6d4657b053f2676a9564e9`.
This pin comes from T419's bounded diagnostic, not an invented sealed-receipt
entry. Retain its exact bytes in the new recovery evidence and stable named/FD
identity through dispatch. Do not interpret arbitrary SSH configuration, execute
its contents, allow a filename alone or broaden production allowlists.

## Complete inventories and protected state

Hold the existing LabLock continuously across preflight, durable intent, stop
and post-observation. A busy/unsafe/replaced lock refuses. It excludes cooperating
local runs, not arbitrary same-UID/external processes; require no concurrent
Colima/Lima/Docker activity. No atomic transaction or zero-TOCTOU claim is made.

Private `colima list --json` must succeed with empty stderr, closed records and
equal complete no-follow Lima roster brackets using existing decode_inventory /
require_complete. Require exactly one private row: kil-v3-lab, aarch64, docker,
4CPUs,8GiB memory,60GiB disk, and Running or Stopped as observed. A missing,
additional, partial, inconsistent or unknown-status row refuses.

If Running, query only the explicit private Docker endpoint using the accepted
Docker executable with `ps --all --quiet --no-trunc`. Require returncode0,
empty stderr and exactly empty stdout. Any container, timeout, malformed or
uncertain response refuses. Do not contact a default daemon or switch contexts.

Collect protected default/global observations with the existing finite collectors:
complete default-home Colima inventory and Lima roster, networks.yaml bytes,
global Docker directory/config/context and kubeconfig fingerprints. Bracket
stable inventory/file observations as foreign_snapshot does, without constructing
or resuming a lifecycle. Require exact equality with retained foreign-original.json
before action; no new baseline excuses drift. Include the global stopped
kil-v3-lab profile: it has the same name but is NOT this private target.

If the private row is already Stopped, issue zero stop instructions. Require
the same saved resource/config identities and sizes via existing stopped-form
validation. Disk-lock absence and removal of shutdown control entries described
below may be observed, not fabricated. Use the same finite direct rosters,
allowing only those shutdown-control absences, with no added names. Any present
pinned SSH/config control must still authenticate. Skip Docker endpoint querying;
never start the VM to observe it. Report already_stopped_observed separately from
a stop performed by this workflow. Other mismatches remain inconclusive.

## Closed native grammar and child environment

The only native mutation, after separate execution approval, is:

```text
/Users/mistorm/.local/bin/colima stop --profile kil-v3-lab
```

Require this canonical UID501-owned0755 single-link regular executable,
15656320 bytes and SHA-256
`980ad8bf61a4ca370243f4cb41401a61276dcd2c2502bee7b9b86f9250169f34`.
The executable metadata/hash were freshly observed while writing this spec;
this is a local pin, not an upstream signature or platform-image attestation.
Require version0.10.3/commit00f6c297e92a82c04a4ab507db0a61435650d7e8.
Authenticate the accepted Docker executable/manifest as existing input checks do,
and require the recorded Lima2.2.0 version. No downloads or replacement tools.

Construct each child environment explicitly, without inherited native overrides:
HOME is actual passwd home; PATH uses the verified accepted tool directory prefix
followed by the original dependency PATH; LANG/LC_ALL may be retained. That original
PATH must contain only nonempty absolute directory components; refuse invalid
form instead of silently removing/reordering components. Retain its value/hash
in the private recovery evidence, not an environment dump. Resolve/authenticate
Colima and Lima dependencies before use and recheck their retained identities;
the accepted prefix may contain only the authenticated three tool files.
For private Colima, set COLIMA_HOME=runtime/`.colima`, LIMA_HOME=runtime/`.colima/_lima`,
DOCKER_CONFIG=runtime/`docker-config`, TMPDIR=runtime/`runtime-tmp`.
For private Docker, set its explicit endpoint and private config/temp only.
Global read-only observations use actual default namespaces, not these overrides.
Do not change host environment, contexts, kubeconfig or global configuration.

Allow only bounded read-only version, private/default inventory, global Docker
context-show and explicit private empty-container instructions needed above.
No arbitrary argv/environment or caller-selected target is permitted. Use existing
capture_process, repository cwd, stdin=None,10-second read timeout,300-second
stop timeout and8MiB combined stdout/stderr bound per instruction. The wrapper
may terminate its own newly launched command process group on timeout; it may
not kill discovered host-agent, VZ or SSH processes. No force/direct limactl stop.

## Once-only evidence and execution flow

New evidence, never the sealed exploratory receipt:
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL/.tools/hf-recovery-private/2026-09-17/manual-stop-254877dc1b1462c4e29c068e51ad7286fe430b075bc5044c8b3076d1887ad25d`.

Anchor owned private ancestry; create that final0700 directory exclusively using
PrivateStore. Preexisting final state refuses, even if incomplete or already
completed; no suffix/fallback, resume or alternate evidence directory. Do not
overwrite earlier transcript exports or recovery receipts.

Retain bounded pre-observations, exact authenticated evidence/tool commitments,
raw command stdout/stderr and finite control-file byte copies. Fixed copies are
the three saved YAML configs, Colima ssh_config, instance ssh.config, ha.pid,
vz.pid, runtime Kind config and the single known Docker-context meta.json named
by runtime-observations.json. Fixed log copies, if present, are instance
ha.stdout.log, ha.stderr.log and serialv.log. Each copy is at most8MiB;
metadata/proof files are at most1MiB; total retained output respects existing256MiB
store budget. Never
traverse guest files, hash entire disks or export private key material.

Before the stop, exclusively write and fsync manual-stop-intent.json plus its
directory. Include user execution approval, reviewed clean source, complete full
identity, preflight/control/tool commitments, exact argv/environment, bounds and
max_native_mutations=1. Pending/completed/uncertain intent consumes the slot;
refuse all second dispatches even if the first result is unavailable. Immediately
repeat lock/ancestry/control/binding/inventory/empty-endpoint/protected-state
checks against the preflight commitments. Failure means zero stop dispatches.

After one dispatch, retain raw terminal result and perform bounded read-only
post-observation only. Nonzero return, timeout, overflow or lost result is
inconclusive even if later inventory says Stopped; never retry or force.

## Postconditions and honest outcome

Graceful-stop confirmation requires successful bounded command completion,
complete stable private inventory showing Stopped, unchanged profile/instance/
disk identities, saved config bytes and raw disk capacities/formats, all46 old
receipt checksums plus its pinned manifest, and protected default/global state
equal to preflight and retained original. No stop command means no performed-
stop claim. Disk-lock release is expected; do not invent retained lock records.

Observe rather than promise native control preservation. Profile docker.sock /
containerd.sock, instance ha.pid / ha.sock / ssh.sock / vz.pid and disk in_use_by
may disappear. Native SSH controls, known context metadata and finite existing
logs listed above may change; retain pre-copies and report each observed bounded
difference.
Persistent directories/configs/disks may not be deleted or replaced. New unknown
entries or protected-state differences make preservation verification inconclusive,
even if stopped status is separately established. Never repair/restore state or
rewrite the original report/checksums to hide a difference.

Keep outcomes separate: already_stopped_observed, graceful_stop_confirmed,
preflight_refused, command_uncertain and postverification_inconclusive. Record
command certainty, observed VM status and preservation status separately; a
Stopped observation alone must not conceal command or preservation uncertainty.
Retain evidence/checksums and every preservation exception; append specialist lineage
and regenerate its reader. End after observation. Recovery does not retroactively
make the rehearsal successful or establish owned teardown/full filesystem removal.

## Test-first preparation and approval gates

The next step after written-spec approval is writing-plans, not native execution.
Any necessary one-shot adapter stays in a dedicated recovery tool/test, never
production Native/Runtime/IO/CLI or strict-verifier changes. No reusable recovery
API, arbitrary path override or launch feature is introduced. Before writing that
adapter, add failing tests for real no-follow/UID/mode/link/bytes/ancestry drift,
full-ID mismatch, substituted receipt/marker/control/tool, unknown roster, partial
inventory, nonempty endpoint, foreign drift, already-stopped zero dispatch,
preexisting/pending intent, fsync failure, final recheck drift and second-stop
refusal. Use real short owned fixtures; mock only unavoidable native acquisition.
Require timeout/overflow/uncertain results never retry and never authorize delete.

Run relevant exploratory runtime/profile/IO/evidence/native and strict profile /
inventory regression suites with the designated Python interpreter, bytecode off,
PYTHONPATH=src and ResourceWarning treated as an error. Native pre/post evidence,
not unit success, establishes recovery outcome. Verify clean exact reviewed HEAD,
append-only lineage prefix, generated readers, document citation and protected
source/evidence commitments. Known historical citation omissions remain reported,
not modified or exempted to manufacture all-green discovery.

After preparation, ask separate explicit approval for this one stop. Approval
of this written spec authorizes planning/test-first preparation only. Execution
also needs the scoped outside-sandbox approval where required; do not bypass
source guards or filter Git warnings. No new branch/worktree, merge, push, cleanup,
Ollama operation, platform-image audit, installation or HF request.

Platform-image provenance remains unverified, full Kind/Calico acceptance false,
and accepted local Envoy unchanged. HF readiness still needs native compatibility
work and a separately approved complete fresh request-free rehearsal with owned
teardown. Live HF action has a separate approval gate. No original exploit,
full-HF prevention, no-bypass, NetworkPolicy, performance, V3B2/V4/V3C claim.

## Spec self-review

Full identity, fixed targets, manifest/SSH/executable pins, finite proof/roster
checks, private versus global namespaces, once-only intent, stopped no-op,
command uncertainty, native-control exceptions and approval boundaries are
explicit. Evidence immutability is not confused with mutable runtime controls
or disk-content immutability. The architecture is isolated to one recovery;
no placeholder, alternate target or implicit HF continuation is specified.

Request user review of this written specification before writing-plans.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

## Written-spec approval — 2026-09-17

The user answered "approved" to review of this written specification for planning
and test-first preparation. That gate is CONFIRMED, superseding the historical
pending status above without rewriting it. Proceed through writing-plans and
fixture-only engineering; no live preflight or stop is authorized. Explicit
native execution approval remains required after verified preparation.
