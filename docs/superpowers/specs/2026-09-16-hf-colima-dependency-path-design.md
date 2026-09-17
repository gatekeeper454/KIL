# Exploratory Colima dependency PATH repair

Date: 2026-09-16.

Status: **Repair scope approved; concrete authority design proposed for written
review. No implementation or new native attempt has started.**

## Input, cause and scope

The user approved the narrow test-first PATH repair after rehearsal
v3b2-ee8373d6150ffa19ed3ec8b0457b0a2b3791cbd3dc66ba658373e042dcf4c31f
failed at private Colima startup. Its command-0014.stderr says Docker was not
found. The accepted Docker executable verified and its explicit version dispatch
succeeded; the inherited PATH does not locate it. Colima performs a separate
transitive dependency lookup. No installation or platform-image audit is needed.

Repair only the exploratory BoundedRunner's private Colima mutation dispatch.
Preserve strict grammar, namespace authority, durable intent/latches, byte/time
bounds, default-home protection, accepted inputs and all sixteen deferrals.
The failed receipt and partial runtime remain untouched. No native retry,
rehearsal or action-mode request was authorized by the initial engineering
approval. During design preparation the user additionally instructed “rerun also
approved if you get everything to work.” This conditionally authorizes one new,
request-free private rehearsal after the repair's tests/reviews and clean-source
gates succeed. It does not authorize resuming the failed run or any action-mode
request. No further rehearsal permission is needed once those conditions are met.

## Alternatives and recommendation

1. **Recommended: scoped, freshly authenticated dependency PATH.** Prepend the
   existing accepted tools directory only when dispatching an exact private
   ExploratoryColimaCommand marked mutating. This covers the closed start/stop/
   delete grammar and native Docker context teardown, without a global change.
2. Export the directory into the parent process or user PATH. Smaller operational
   workaround, but it does not bind transitive lookup to runner verification and
   affects unrelated commands. Rejected.
3. Install another Docker or create a runtime shim/copy. Adds alternate executable
   identity or another mutable control-file contract. Unnecessary; rejected.

## Exact authority boundary

Use only inputs.tools, already tied to the checksum-authenticated accepted
manifest. No caller PATH/home/binary parameter, new environment key or new CLI
option. The tools directory must be absolute, canonical, nonsymlink and contain
no PATH separator; refuse ambiguous spelling. Its complete bounded direct-child
roster must be exactly docker, kind and kubectl, all regular executable files.
Freshly authenticate all three full files against the accepted rows before
granting this directory PATH priority. Extra entries refuse rather than shadow
Colima, Lima or system helpers. This is an executable-input check, not an image
provenance audit or installation.

Resolve the top-level Colima executable from the original sanitized PATH before
prepending the tools directory; dispatch that existing executable by absolute
path. Missing, nonregular, nonexecutable or noncanonical resolution refuses.
The existing pinned Colima/Lima version checks remain unchanged. Preserve the
original PATH tail byte-for-byte; when absent or empty, use the authenticated
directory alone without introducing an empty current-directory search entry.
Do not mutate os.environ or the command's derived four-variable env tuple.

Recheck the dependency directory identity/roster, authenticated executable bytes
and inputs.tools across existing authentication IO. Retain the final runtime/
command guard and exact manifest/metadata-map consistency checks after all new
authentication/guard IO, immediately before capture. Refuse known drift with
zero process capture. No transaction, external exclusion or zero-TOCTOU guarantee
is claimed; do not introduce a generic executable search/dispatch facility.

## Unchanged consumers and failure handling

Direct Docker/Kind/kubectl commands still use their existing absolute authenticated
executable dispatch. Plain global Colima version/list and scoped read-only Colima
commands keep their existing sanitized environment and behavior. HOME remains
the actual passwd home; COLIMA_HOME/LIMA_HOME/DOCKER_CONFIG/TMPDIR remain exactly
derived from the fresh private RuntimeAuthority. No grammar or foreign-state
exception is introduced. Any authority or dependency failure propagates before
process acquisition; no fallback, retry, adoption or partial-state cleanup.

## Test-first implementation and verification

The implementation unit is src/kil/hf_exploratory_io.py and its existing test
module only, plus required design/plan/lineage readers. First demonstrate failure
for private start/stop/delete dependency PATH wiring and original Colima selection.
Use real temporary authority/filesystem fixtures; mock only the unavoidable
process acquisition boundary and narrowly identified executable digest fixtures.
Keep real accepted manifest authentication, metadata shape/type checks and guards.

Cover unchanged readonly/global/other-family behavior; missing or substituted
Docker and other accepted binaries; ambiguous or symlink tools paths; unexpected
directory entries; dependency-directory/bytes/tools-path drift during IO; missing
Colima; and preservation of sanitized inherited variables and PATH tail. Watch
each new behavioral assertion fail for the intended reason before code changes.
Re-run focused IO/runtime and the required 15-module exploratory/strict regression
suite with ResourceWarning fatal and bytecode off. Independent SPEC then QUALITY
review, reader/prefix/diff checks and a clean engineering checkpoint are required
before using the conditional permission for one fresh native rehearsal. If an
engineering gate fails or the rehearsal is inconclusive, stop without another
automatic attempt or action-mode continuation.

The prior full suite's four immutable historical citation omissions remain
unchanged; neither old documents nor exemptions are edited to hide the failure.
Full Kind/Calico acceptance remains false and platform-image provenance unverified.
The accepted local-Envoy result is unaffected. The conditional rerun covers only
the request-free rehearsal. Successful retained rehearsal and separate explicit
action permission still gate any fresh three-track action.

## Spec self-review and next gate

One runner unit, finite mutation-only routing, exact tool authority and explicit
unchanged consumers are specified; no placeholder or unrelated refactor remains.
This document records the approved repair scope without treating new authority
details as silently confirmed decisions. User review of this written design is
the brainstorming gate before the concrete implementation plan and TDD.

KTP citation: [canonical CITATION.cff](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
