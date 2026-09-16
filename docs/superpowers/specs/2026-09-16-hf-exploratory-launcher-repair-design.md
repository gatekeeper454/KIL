# Exploratory HF launcher repair: isolated native state and frozen evidence

Date: 2026-09-16.

Status: **PROPOSED concrete design; implementation not started.** User approved
the focused repair phase, then requested a stopping point to reload the app.
Isolating the native state changes the prior launch-placement contract and
requires review of this design before implementation. No deletion, restart,
rehearsal or HF request is authorized by this document.

## Goal and confirmed boundary

Make the existing separate exploratory launcher compatible with pinned Colima
0.10.3 while keeping foreign-state protection and immutable receipts. Preserve
the accepted local-Envoy result, strict launcher/parser/command grammar, sixteen
strict deferrals, application-image requirements and all experiment exclusions.
Platform-image provenance remains explicitly unverified; no new provenance
audit is required. The experiment remains one harmless modeled cut point and
the existing fixed three tracks, not a historical exploit or full incident replay.

The residual default-home kil-v3-lab is Stopped. Profile and both disks remain;
original receipt's missing context metadata is an established exception, not
something this repair may fabricate or silently restore.

## Evidence-backed causes

1. The existing strict saved parser expects an empty DNS-host mapping for both
   profile and instance. Native `newConf` inserts the Docker-to-Lima host alias
   into the mapping, and instance persistence retains that generated form.
   [Pinned DNS/config generation](https://github.com/abiosoft/colima/blob/v0.10.3/environment/vm/lima/yaml.go),
   [pinned instance persistence](https://github.com/abiosoft/colima/blob/v0.10.3/environment/vm/lima/lima.go).
2. `writeNetworkFile` removes network assets when its running-instance scan is
   empty. `NetworkAssetsDirectory` is the selected Lima home's `_networks`.
   This code is consistent with the observed default-home inode replacement;
   no internal deletion trace independently proves that particular execution.
   [Pinned network reset](https://github.com/abiosoft/colima/blob/v0.10.3/environment/vm/lima/network.go),
   [pinned network paths](https://github.com/abiosoft/colima/blob/v0.10.3/environment/vm/lima/limautil/files.go).
3. Docker-runtime Stop invokes context teardown, which issues a scoped Docker
   context removal. Native runtime configuration was placed inside the receipt;
   the observed file loss exposes that lifetime mismatch.
   [Pinned Stop](https://github.com/abiosoft/colima/blob/v0.10.3/environment/container/docker/docker.go),
   [pinned context teardown](https://github.com/abiosoft/colima/blob/v0.10.3/environment/container/docker/context.go).

These sources were read through GitHub's API at the pinned tag, not executed.
No shell/environment dump, sudo, guest provisioning or native mutation was
performed in this investigation. Hook pattern findings during source reads
do not authorize running any upstream code snippet.

## Approaches and recommendation

- **Recommended: per-run isolated native state.** Colima may reset its own
  network assets and remove its own runtime context without changing user
  state or frozen evidence. Requires a separate exploratory path/command
  adapter and explicit source review, rather than a one-line bypass.
- Keep default-home state and permit the known shared-directory churn. Smaller
  code delta, but changes the original foreign-identity contract and does not
  keep native network-file writes away from stopped foreign profiles. Rejected.
- Change/update the native tool or substitute local Envoy. Changes the pinned
  substrate or experiment question; neither is part of this repair.

## Native namespace and command authority

Derive a fresh runtime sibling from the same source-bound run digest under the
existing fd-anchored LabLock parent:

```text
.tools/hf-exploratory-private/
  hf-exploratory-<digest>/          immutable receipt / PrivateStore
  hf-exploratory-runtime-<digest>/ owned native state
    .colima/                      COLIMA_HOME
      _lima/                      LIMA_HOME
      kil-v3-lab/                  private profile and Docker socket
    docker-config/                native-managed Docker context
    runtime-tmp/                  TMPDIR
    kubeconfig                    private Kind control file
    kind-config.yaml              exact retained configuration copy
```

No caller-selectable runtime directory/home/endpoint. The runtime sibling,
Colima home and Lima home must be newly created, empty, mode 700, nonsymlink,
fd-anchored and identity checked before native dispatch. Colima's pinned path
selection only honors COLIMA_HOME if the directory already exists; otherwise
it can fall back to user state. Therefore missing/replaced private homes refuse
dispatch, rather than letting the tool choose a fallback.
[Pinned path selection](https://github.com/abiosoft/colima/blob/v0.10.3/config/files.go).

All scoped Colima commands carry exact derived COLIMA_HOME, LIMA_HOME,
DOCKER_CONFIG and TMPDIR; inherited home/profile/XDG overrides remain excluded.
Docker/Kind commands retain their exact private configuration and Unix endpoint;
kubectl retains the explicit private kubeconfig. Their runtime paths move
together because existing Kind factories derive docker-config/kind-config from
the kubeconfig's parent. Persist immutable copies and commitments for generated
control inputs and observed native configuration in the receipt.

The existing strict `Command` rejects extra Colima environment keys. Do not
widen it. Add a separate exploratory-only closed Colima command adapter with
the same finite argv, mutating flags, stdin restrictions and time/byte bounds,
plus exact derived namespace authority. Only the exploratory dispatcher may
accept it. All other command families retain the existing strict type and
grammar. Attempt latches, durable intent and no-replay rules remain unchanged.

## Configuration binding and foreign-state protection

Add exploratory-only profile authority/binding logic using the existing
no-follow collectors and raw-capture validation. Do not modify the strict
saved parser or pretend passwd HOME has moved. The document must explicitly
name actual user HOME and the separate derived native namespace.

Require the known original profile form and exact generated instance form:
the only admitted DNS-host entry is host.docker.internal mapped to
host.lima.internal. Keep all other scalar/resource/mount/activation values
exact. Reject extra hosts, values, keys, nested structures, duplicates, tags,
anchors and ambiguous syntax. Hash and retain the full native bytes, not a
normalized replacement. Bind concrete directory/config/disk identities, sizes,
raw format and lock target under the derived namespace; recheck before every
mutation. Changed or unbound targets still refuse cleanup.

Keep two distinct inventories. The default-home snapshot treats **every** user
profile and Lima child as foreign, including the old stopped kil-v3-lab;
do not exclude a row merely because its name matches the private lab. Preserve
its complete roster identities, rows, global Docker/kubeconfig state, and the
bounded native network-config file snapshot. The private inventory must contain
only the creation-bound lab and expected private reserved state. Private
network churn is within the owned namespace; any default-home churn still
fails. The old stopped VM can remain untouched rather than requiring deletion
solely to make this newly isolated launch pristine.

This is a placement change, not permission to relax foreign identity checks.
If isolation cannot be enforced without changing a strict unit, stop and
revise this design rather than widening shared grammar.

## Evidence and cleanup

Only receipt files enter the frozen retained-file manifest. Before native
shutdown, snapshot bounded relevant runtime configuration/context bytes into
new immutable receipt files with identities, full byte hashes and provenance
labels distinguishing observation from verification. Never use those snapshots
as live control files; never checksum mutable runtime paths as retained receipts.
All future receipt hashes must remain valid after simulated context removal.

Existing exact-owned Kind/Colima teardown remains restricted to the private
namespace and verified incarnations. Do not recursively erase the runtime
sibling: native deletion may leave reserved network/cache files. Retain and
report leftovers; broader filesystem removal needs a separately reviewed exact
footprint contract. Unknown/unbound cleanup still means manual recovery. No
default-home residual deletion or recreation of lost metadata is included.

## Tests and implementation boundaries

Proposed new exploratory units: `src/kil/hf_exploratory_profile.py` for exact
saved-form/resource binding and `src/kil/hf_exploratory_runtime.py` for derived
namespace and closed Colima authority. Integrate only in exploratory native/IO/
CLI units and their tests. No strict, accepted/publication or deployment edits.

Use retained failure data to create independent regression fixtures. First
observe failing tests for exact generated instance parsing, protected/changed
resources, missing/symlink/replaced private home, environment substitution,
same-name cross-home confusion, private-network reset versus forbidden foreign
reset, and native context removal without receipt invalidation. Keep existing
fixed-track/no-replay/incarnation/join/owned-cleanup guards passing. Unit/SPEC/
QUALITY/final composition review and clean source precede any native permission.

Implementation planning must explicitly resolve integration of the new
Colima type, runtime Kind control-file paths, pure stopped/absence checks and
immutable snapshots; these are not permission to use a generic subprocess or
caller-selected environment. Fresh private state is never adopted on resume.

## Checkpoint and next gate

All source lookups finished; no native command, held runtime lock or repair
worker remains active. No implementation/tests were edited and no repair was
claimed. The brainstorming design-review gate pauses implementation because
native-home placement and command authority are material decisions.

After app reload: review this recommended isolated-state design, approve or
revise it, then write the concrete test-first implementation plan and execute
it with independent reviews. No deletion/start/rehearsal/request is authorized
by design approval alone. Once repaired, a separately gated request-free
private setup/capture/teardown rehearsal still precedes the fresh three-track
action under the approved exploratory experiment scope.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

## Design approval — 2026-09-16

The user instructed: “go design approval under the brainstorming skill, then
test-first implementation.” This approves the recommended isolated-runtime
design above for engineering implementation. The original PROPOSED status and
checkpoint remain historical records. Approval does not authorize any native
start/stop/delete, rehearsal or HF request. Platform-image provenance remains
unverified. Next gate: written implementation plan, test-first repair and
independent spec/quality/composition review before separate native permission.
