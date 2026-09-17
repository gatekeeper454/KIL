# Compact private runtime for exploratory HF preparation

Date: 2026-09-16.

Status: The user approved the persistent whole-runtime architecture proposed in
T406. This is its concrete written specification, pending written-spec review
before the implementation plan, production edits or another native attempt.

## Purpose and evidence

The verified scoped PATH repair advanced the one authorized request-free rehearsal
v3b2-3e71b5b05810b71567e14ac06c5accf1faebee0126ed4659aceec17da567a3ae beyond
Docker dependency lookup. At 18:59:22 PDT, Lima 2.2.0 refused its projected SSH
socket pathname: 247 characters, where less than UNIX_PATH_MAX=104 is required.
The original refusal is retained in command-0014.stdout of that private receipt.
The report is inconclusive_at_profile_start_attempted, not a successful rehearsal.

Move ONLY fresh exploratory native runtime state to a compact, persistent,
internally derived location. Keep durable receipts in their existing repository
store. Preserve strict contracts, the accepted local-Envoy result, accepted inputs,
the verified PATH repair and all claim exclusions. This does not require a new
platform-image provenance audit or a dependency installation.

The failed runtimes and receipts, including the 3e71b5b0 sparse data disk, are
never moved, adopted, rewritten or deleted by this work. The old disk has 60-GiB
logical size and stat reported zero allocated blocks; it is not teardown authority.

## Approved architecture and alternatives

Use actual passwd home/.kil-hf/r<first-16-lowercase-hex-of-full-run-digest>.
On this pinned host that is /Users/mistorm/.kil-hf/r<16-hex-label>. The complete
known Lima socket projection is 98 UTF-8 bytes, below the exclusive 104-byte bound.
The short label is a locator, NOT a replacement run identity or an ownership proof.
The full 64-hex digest and v3b2-<full-digest> run ID remain authoritative.

Alternatives considered: a whole-runtime /private/tmp location fits but exposes
residual state to temporary-directory cleanup/reboot retention risk; a symlink
alias conflicts with canonical/no-follow authority. Moving only Lima would split
authority and leave other native endpoint paths long. No fallback is selected.

Retain the existing exact RuntimeAuthority.create(store, run_digest) interface,
closed constructor, frozen object and exact-type adapter checks. No caller runtime
path/home/binary argument, environment override, CLI flag or new production module.
Production location selection is private, takes no caller path and derives the
actual passwd home, never ambient HOME or TMPDIR.

All native paths stay together under the fresh short root: .colima, .colima/_lima,
docker-config, runtime-tmp, kubeconfig and kind-config.yaml. Existing property names,
fixed native profile/instance names and command/environment grammar stay unchanged.
HOME remains actual passwd home; the four existing derived Colima namespace keys
retain their exact meanings. Global PATH/default Colima/Docker/kube state is untouched.

## Registry contract

Here UID means the current effective UID; creation and every live guard require
real and effective UIDs to agree. The actual passwd account supplies home, not a
caller-supplied home. Reject a mismatched/elevated-UID route before allocation.

The .kil-hf registry is a canonical, nonsymlink, actual-UID-owned 0700 directory.
Open each ancestor from / with retained read-only directory/no-follow descriptors;
validate named and retained identities and the expected derived topology. Ordinary
ancestor directory timestamps/rosters are not immutable, but device/inode/type/
mode/UID identities are retained and rechecked. Registry and run-home privacy is
mandatory even if ordinary home ancestors have different modes.

If the registry is absent, create it exclusively through the retained parent FD,
retain its FD, verify UID/mode/identity and fsync the parent. Create registry.json
exclusively as a bounded, single-link, UID-owned 0600 regular file; fsync that file
and registry directory. Its exact canonical bytes have precisely these fields:

- schema: kil.hf-exploratory-runtime-registry.v1;
- uid: the actual numeric UID;
- runtime_parent: the exact canonical registry path string.

If the registry exists, reuse ONLY its namespace parent after the same privacy,
canonical/identity checks and exact registry marker authentication. An unmarked,
partial, foreign, symlinked, nonregular, hardlinked or wrong-mode marker refuses.
Do not install a marker into an existing unmarked directory, chmod it, repair it,
search for another registry, scan/adopt old run children or retry bootstrap.
Existing marked registries may contain old run directories; those are not authority
for the new run. A marker establishes the closed namespace form, not exclusion of
arbitrary same-UID host code or a cryptographic attestation of the operating system.

## Fresh run and durable full-identity binding

Validate the existing exact PrivateStore instance, full lowercase 64-hex digest,
receipt name hf-exploratory-<full-digest>, canonical repository ancestry, private
receipt directory and retained/named single-link 0600 store lock before allocation.
The receipt namespace remains .tools/hf-exploratory-private. Retain its complete
descriptor ancestry independently from the compact runtime ancestry.

Compute the label r+run_digest[:16] internally. Require one exclusive fresh mkdir
for that run root, then exclusive fresh 0700 .colima/_lima, docker-config and
runtime-tmp homes with parent fsyncs. A preexisting label of ANY kind refuses,
including an identical full digest or a different digest sharing the first 16 hex.
Never adopt, inspect for reuse, truncate further, choose a second label or retry.
Exclusive creation handles collision safely; collision-free naming is not claimed.

Before returning a usable authority, persist runtime-binding.json through the
existing exclusive bounded PrivateStore write. Its canonical document has exactly:

- schema: kil.hf-exploratory-runtime-binding.v1;
- uid: actual numeric UID;
- run_digest: full 64-hex digest;
- run_id: v3b2- plus that complete digest;
- receipt_path: exact canonical store path string;
- registry_path: exact canonical registry path string;
- runtime_path: exact canonical fresh short-root path string;
- runtime_identity: device/inode/mode/uid integer fields from the retained root FD.

Retain the expected bytes and stable file identity of both marker and binding.
Both are at most 8192 bytes, UID-owned single-link 0600 regular files, opened
read-only/no-follow/nonblocking for stable bounded authentication. Compare named
and retained file identities (device/inode/mode/UID/link-count/size/nanosecond
mtime/ctime) before and after the exact full-byte read; require exact canonical
expected bytes and field types. Neither a caller-owned mutable map nor a short
prefix alone can authorize runtime use. Marker/binding persistence failure closes
all acquired descriptors and leaves observable partial state; no native dispatch
or automatic filesystem cleanup follows.

## Authority guard and path budget

RuntimeAuthority.guard validates its exact class, closed/live state, full digest,
store object/path/lock, derived registry/label/root and the complete expected
topology of BOTH retained ancestry chains. Keep explicit verified store/root handles
rather than indexing a presumed store-sibling runtime root. Every directory's named
and FD identity must match; private registry/root/native homes remain UID-owned 0700.
write_control retains its existing sole Kind-control grammar, exclusive 0600 file
creation, bound, fsyncs and before/after guards, using the verified short-root FD.

Authenticate marker/binding through their retained directories as above. After
both reads, recheck BOTH named/retained file identities and directory/store/lock
identities, so later authentication cannot leave an earlier file substituted. Refuse any
known name/topology/content/link/mode/UID drift or source-object substitution before
native acquisition. Preserve existing final adapter/runtime/fingerprint checks and
final exact manifest/tool-metadata consistency AFTER all authentication/guard IO.
No new authentication IO is inserted after that final runner consistency block.
Normalize known authority filesystem/shape failures to ValueError before dispatch.
All directory/file descriptors close exactly once on failure and idempotent close;
close releases handles only, never native resources or disk files.

Before any registry/run allocation AND in every guard, compute the byte length
of the full derived Lima projection:
runtime/.colima/_lima/colima-kil-v3-lab/ssh.sock.1234567890123456.
Require os.fsencode(projected_path) length <104, also checking the known derived
Docker socket path. A longer/noncanonical actual home refuses before native start;
there is no temporary-directory, alias, shortened-second-label or environment
fallback. The bound addresses the recorded pinned-native failure, not an unlimited
promise about future serializers. No transaction, external exclusion, zero-TOCTOU
or hostile arbitrary in-process code-execution guarantee is claimed.

## Pure paths, evidence and unchanged consumers

ProfilePaths.bind still requires exact live RuntimeAuthority and its guard.
Pure ProfilePaths/saved-form validation accepts the internally derived compact
shape: parent equals the private registry selector's expected location and leaf
matches r[0-9a-f]{16}; a provided home field cannot choose a production registry.
It may retain the existing legacy sibling shape for OFFLINE saved-evidence
analysis only; no legacy RuntimeAuthority creation/adoption path is added. Existing
two-field home/runtime path documents and strict capture/binding schemas stay
unchanged. Pure document parsing or a registry marker never grants live authority.

Existing seven-file runtime snapshots and five-directory leftover observations
consume derived properties without broader traversal. The binding file is durable
receipt evidence and automatically participates in the retained SHA-256 set; do
not add another full runtime/disk scan. Native/CLI behavior, durable intent/latches,
Kind-control consumer checks, foreign/default commitments, snapshot-before-teardown
and refusal of unbound cleanup remain unchanged. Successful owned native teardown
does NOT erase the registry/run controls or imply filesystem_fully_removed.

Production changes are limited to src/kil/hf_exploratory_runtime.py and
src/kil/hf_exploratory_profile.py. Update existing runtime/profile/IO/evidence/Native
tests only as needed for the approved locator/fixture contract. Do not edit IO,
evidence, Native or CLI production modules, strict modules, accepted artifacts,
gitattributes, historical receipts or citation policy. No unrelated refactor.

## Test-first engineering readiness

After written-spec approval, write failing behavior assertions before implementation:
compact derivation and actual byte cap, whole-root consumer paths, exclusive prefix
collision, registry first creation/safe reuse/unsafe refusal, exact durable full-ID
binding, changed marker/binding bytes/types/links/modes, both ancestry replacement,
substituted digest/path/store/handles, close/failure descriptor lifecycle, unchanged
strict/global/read-only command behavior and finite snapshot/teardown semantics.

Use real short temporary filesystem fixtures. Tests may narrowly replace the
private registry-location selector with an owned canonical short fixture registry
under /private/tmp; this is not a public API or production caller override. All
file bytes, markers, metadata types, permissions, no-follow and retained FD guards
remain real. Retain the IO module's already narrow executable-digest fixtures and
mock only unavoidable process acquisition. Reject known drift with zero capture.

Use the designated interpreter, bytecode off, PYTHONPATH=src and
-W error::ResourceWarning. Run focused affected modules and all existing required
15-module exploratory/strict regressions, recording actual counts rather than
assuming the prior 425-test count. Independent SPEC, QUALITY and final composed
review must pass; fix important findings test-first and independently re-review.
Verify complete predecessor lineage bytes, generated readers, diff checks,
unchanged protected production/artifact paths and clean committed exact HEAD.
Keep the existing externally managed detached worktree; no branch move, merge,
push, new worktree or cleanup. Prior broader discovery's one failure for four
immutable historical citation omissions and sixteen intentional skips remains
visible; do not rewrite old receipts or exemptions to claim all-green discovery.

## HF preparation and bounded native approval terms

The latest user messages confirm design approval and intent to proceed through
test-first implementation/HF preparation. Review of THIS written spec is the next
gate. Approval of it also approves ONE new, fresh, request-free private rehearsal
conditionally on all engineering/review/clean-source/input gates above passing.
No native attempt occurs while this written review is pending.

Root alone uses reviewed LabLock/verify_inputs/PrivateStore/BoundedRunner/
ExploratoryLifecycle APIs with constant mode='rehearsal', fresh nonce and exact
clean reviewed HEAD. Never call the unchanged CLI main, whose successful rehearsal
automatically continues into action. Source/input/native execution may use the
existing outside-sandbox route because sandboxed macOS Git stderr warnings trip
the unchanged fail-closed source gate; do not filter warnings or bypass guards.

The one preparation attempt may create only its fresh compact private namespace,
private Colima VZ/Kind setup and retained request-free evidence, then exact guarded
owned teardown. It must record zero request intents AND zero request attempts.
Verify every retained receipt checksum, bracketed protected foreign/default state,
observed runtime controls/leftovers and actual report. Preserve all old/new failed
bytes. Inconclusive result, missing ownership binding or unknown/drifting state
ends the attempt without a second automatic launch, adoption or unbound stop/delete.

HF-test readiness requires a complete retained request-free rehearsal AND verified
owned teardown, not merely successful VM startup or unit tests. Even that does
not authorize action mode/live HF requests: fresh three-track action requires
separate explicit user approval. Platform-image provenance remains unverified,
full Kind/Calico acceptance remains false and accepted local Envoy is unaffected.
No original exploit, full-HF prevention, all-eight-phase, NetworkPolicy/no-bypass,
performance, V3B2 acceptance, V4 or V3C claim is established by this preparation.

## Spec self-review and next gate

The selected location, locator/full-identity distinction, marker/bootstrap/reuse,
collision refusal, complete binding fields, fd/byte bounds, consumer compatibility,
file scope, test fixtures and single native attempt terms are explicit. There are
no placeholder requirements, dynamic fallback or unrelated image/installation
tasks. Offline legacy parsing is distinguished from forbidden live adoption;
performed preparation is distinguished from successful readiness/acceptance.

Request written-spec approval before invoking writing-plans. Production code and
native runtimes are unchanged at this document checkpoint.

KTP citation: [canonical CITATION.cff](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
