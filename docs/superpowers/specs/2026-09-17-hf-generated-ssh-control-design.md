# Exploratory HF generated SSH-control compatibility

Date: 2026-09-17

Status: APPROVED for the new bounded repair by the user on2026-09-17: "fix the ssh issue so we can get past it. do what is necessary to make it work.". User "I need you to execute the HF now"
authorizes the previously selected single exploratory HF action when its retained
readiness requirements pass. The subsequent instruction approves the necessary new repair and conditional
request-free preparation. Neither instruction establishes successful readiness. No VM/HF execution occurred while preparing it.

## Problem and selected approach

The T419 request-free rehearsal started its compact private Colima VM, then
failed both setup and cleanup at `private_colima_profile_roster_unknown`.
`ExploratoryLifecycle.private_inventory` still permits only `_lima`, `_store`,
`_templates`, and `kil-v3-lab` beneath the run's private Colima home. The pinned
native producer also generated `ssh_config` despite `--ssh-config=false`.
Recovery T443 stopped that residual VM and retained its resources; it did not
change the HF lifecycle or complete the failed rehearsal.

Recommended: recognize only the validated run-owned generated SSH control in
the exploratory lifecycle. Keep the closed roster and all other ownership gates.
This is a new bounded compatibility repair, not repetition of accepted compact
runtime/recovery engineering or a platform-image provenance audit.

Alternative: leave the guard unchanged. This preserves its current refusal but
cannot reach the HF action; another launch would reproduce a known unresolved
failure. Alternative: allow the extra name without content/identity checks.
Reject this because a pathname alone does not establish run ownership.

## Contract

- Only the fresh run's exact private `.colima/ssh_config` may be recognized;
  never default/global homes or a retained failed/stopped runtime.
- A fresh pre-start private namespace must still be pristine. Presence before
  the native start is a refusal, not a file to adopt or delete.
- Initial acceptance is after successful start and established profile creation
  binding. Read through anchored no-follow descriptors, bounded to16KiB. Require
  regular file, effective UID ownership,0644 for Colima and0600 for the paired
  instance control, one link, stable named/descriptor
  identity and bytes across authentication and closure.
- Validate the complete observed pinned-producer grammar: exactly one
  `Host colima-kil-v3-lab`, exact generated comments/options/order, loopback
  `Hostname 127.0.0.1`, integer Port1..65535, fixed account user, and exactly the
  current run's Lima `_config/user` IdentityFile and instance `ssh.sock`
  ControlPath. No wildcard hosts, Include, ProxyCommand/ProxyJump, extra directives,
  additional host blocks, alternate paths or arbitrary bytes. The port is a
  native observation, not selected by a caller.
- Cross-check against the run's bounded generated instance SSH configuration;
  the instance uses exactly `Host lima-colima-kil-v3-lab`, whereas the Colima
  copy uses exactly `Host colima-kil-v3-lab` and adds one trailing blank line.
  Normalize only those two documented differences; require all other validated
  definition bytes and private endpoint to agree. Retain their bytes, identities and SHA256 in the new run evidence.
  Do not pin the historical767-byte file hash as a future run's expected hash:
  private paths and native port belong to the fresh runtime.
- Reauthenticate accepted controls at relevant private inventory and mutation
  boundaries, including final intent-to-dispatch checks. Running-state drift,
  replacement, unexpected disappearance, or uncertain observations refuse
  further setup/request/teardown authority.
- The sealed recovery records native stop rewriting the Colima control to exactly
  zero bytes (regular UID501/0644/single-link), while the paired instance control
  stays unchanged. Native stop/delete may also remove generated transient controls.
  Permit only absent, unchanged-valid or exactly empty Colima post-stop forms,
  bracketed by successfully returned exact owned stop and complete Stopped inventory/
  profile proof; paired instance bytes remain bound until native delete. Native
  replacement during that bracket is recorded with its new identity; no replacement
  is permitted while Running. No other stopped syntax is accepted. These are
  explicit stopped/removed transitions authorized by exact owned lifecycle commands; no caller-operated unlink/chmod/rewrite, repair or arbitrary stopped
  content substitution. Keep absent-state checks anchored and closed.
- Unknown extra roster entries still refuse. Inventory completeness, exact owned
  profile/resource binding, foreign-state preservation and request/evidence guards
  remain required. Recognition of SSH controls grants no new command grammar.

## Engineering and evidence

Scope: exploratory lifecycle and a focused SSH-control helper if needed, plus
tests and new plan/spec/lineage readers. Preserve strict launchers/controllers,
accepted artifacts, recovered/failed runtimes, original receipts, and accepted
recovery/permission-helper bytes. Do not refactor unrelated lifecycle behavior.

Use the user's test-first/subagent preparation and ordered independent SPEC,
QUALITY and final composed reviews for this new change. Real test-owned filesystem
fixtures must exercise valid generated controls, wrong grammar/paths/endpoint,
foreign UID/mode/linkcount/type, symlink/FIFO, pre-start presence, late replacement/
same-size edits, unexpected absence, unknown roster names and allowed exact native
stopped/removed transitions. Include dispatch-boundary and cleanup integration
checks without real native commands. Run meaningful scoped regressions with
bytecode disabled and ResourceWarning fatal; do not revive the known broader
citation omissions as an all-green claim or rewrite them.

The implementation plan must specify complete producer grammar and paired-file
comparison before code is changed. Any additional incompatible producer behavior
is a separate blocker, not a fallback or automatic scope expansion.

## Ordered execution and approval boundaries

1. The user has authorized this necessary compatibility repair and ONE conditional
   request-free rehearsal after engineering/review gates. No live launch before
   engineering/review gates and a fresh clean source/input check.
2. Implement/review/checkpoint only the new repair in the exact existing detached
   worktree. No installation, main-checkout switch, merge, push or worktree cleanup.
3. Root runs one fresh private request-free lifecycle using the accepted core APIs
   with constant rehearsal mode, fresh full run digest and exact clean HEAD. Preserve
   all predecessors. Do not invoke the CLI's automatic rehearsal/action loop.
4. Verify complete rehearsal, zero HF intents/attempts, exact owned teardown,
   retained checksums and foreign preservation. Any failure or uncertainty stops;
   no retry or implicit residual recovery.
5. Only if readiness passes, use the user's current HF authorization for ONE fresh
   three-track action lifecycle: at most one instruction per fixed track, three
   total, equivalent inputs, durable intent before instructions, no retry. Do not
   resume the failed rehearsal or reuse the recovered runtime as action ownership.
6. Retain final joined driver/Envoy/authorization/target evidence and perform exact
   owned teardown under the accepted experimental contract. Report actual result,
   uncertainty and leftovers, append lineage and stop.

The modeled cut point expects permit/permit/deny, HTTP200/200/403, target1/1/0.
These are hypotheses. Platform-image provenance stays unverified and full
Kind/Calico acceptance remains false; accepted local-Envoy evidence unchanged.
No original-exploit reproduction, full incident, no-bypass, complete NetworkPolicy,
performance, repeated reliability or publication acceptance claim.

Self-review: one bounded blocker, alternatives explicit, fresh ownership and
native transitions distinguished, historical evidence preserved, no placeholders
or readiness promise. Detailed implementation planning follows approval.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
