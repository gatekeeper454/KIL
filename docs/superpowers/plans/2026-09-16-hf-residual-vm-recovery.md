# HF Residual VM Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This is a manual recovery runbook, not permission to implement a recovery feature or change the strict lifecycle.

**Goal:** After explicit execution approval and fresh continuity checks, gracefully stop only the residual `kil-v3-lab` VM, preserving its disks and all evidence.

**Architecture:** Establish a separate, narrowly scoped manual-stop authority from the retained creation footprint plus fresh unchanged filesystem observations, complete inventory and an empty lab-container roster. Do not pretend the failed strict creation binding succeeded. Perform at most one graceful stop, then observe and report; uncertainty stops the workflow without force, deletion, restoration or replay.

**Tech Stack:** Existing Colima v0.10.3, Lima 2.2.0, accepted Docker client, existing no-follow profile/inventory observers and bounded process capture; local private evidence and Markdown readers.

---

## Status and authority

Prepared at the user's request on 2026-09-16. **PROPOSED; NOT EXECUTED.**
The user requested saving the transcript and preparing this plan, not stopping
or deleting the VM. A subsequent explicit approval is required for the one
manual stop. Sandbox approval for that instruction is also required.

This manual-stop exception does not change the approved exploratory acceptance
contract, repair or retroactively establish ownership binding, admit another
setup attempt, or authorize any HF request. Approval covers no deletion.

## Exact targets and files

Repository:
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL`.

Retained failed run, here called **receipt**:
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL/.tools/hf-exploratory-private/hf-exploratory-4bf272a01cfdb5c96ab08a70def03ecbd7a29ef375bbe957ae0be6b991409bfe`.

Manual recovery evidence, separate from that immutable receipt:
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL/.tools/hf-recovery-private/2026-09-16`.

Only permitted native mutation after approval:

```text
/Users/mistorm/.local/bin/colima stop --profile kil-v3-lab
```

Profile: `/Users/mistorm/.colima/kil-v3-lab`.
Lima instance: `/Users/mistorm/.colima/_lima/colima-kil-v3-lab`.
Data-disk directory: `/Users/mistorm/.colima/_lima/_disks/colima-kil-v3-lab`.
Lab Docker endpoint: `unix:///Users/mistorm/.colima/kil-v3-lab/docker.sock`.

**Files created/updated during execution:** Separate private recovery observations,
stop-intent/result, outcome and checksums; append-only specialist lineage and
its generated reader. Never overwrite transcript exports or failed receipts.
No implementation, test, deployment, accepted/publication artifact, global
Docker configuration or kubeconfig is edited.

**Existing units used, not modified:**
`src/kil/v3b2_profile_state.py` (`ProfilePaths`, `capture`, `validate_capture`),
`src/kil/v3b2_colima_inventory.py` (`capture_roster`, `decode_inventory`,
`require_complete`), `src/kil/hf_exploratory_inputs.py` (`read_regular`),
`src/kil/hf_exploratory_io.py` (`capture_process`, `PrivateStore`) and
`tools/hf_exploratory_kind.py` (`LabLock`, without calling its launcher).

## Confirmed failure and last observed environment

Reviewed launch source: `a7c18c55b899158f9e5f6bb1c445b1569eb19da0`.
Last complete post-failure inventory: residual profile Running, aarch64,
Docker runtime, 4 CPUs, 8 GiB RAM and 60 GiB data disk. Retained raw capture:
20 GiB root disk and VZ configuration. These are observations, not a successful
creation binding. Fresh state must be re-established before any stop.

The profile configuration passes the saved parser. The instance configuration
adds `network.dnsHosts` / `host.docker.internal: host.lima.internal`; the
closed parser cannot parse this nested mapping and rejects creation binding.
The successful Colima start includes an internal restart, but the launcher
issued just one start instruction. It stopped with zero request intents and
attempts, before Kind, Calico, Envoy/KIL workloads or driver attachment.

Separately, shared `_networks` directory inode changed from 596062288 to
612747935 on device 16777232, mode 16877 unchanged. Other captured foreign child
identities, foreign inventory rows and global Docker context still matched.
The cause of the directory replacement is not established. This plan does not
relabel that change as acceptable strict preservation or restore shared state.

Foreign profiles last observed: `default` Stopped (4 CPU/4 GiB/20 GiB) and
`attackswarm` Stopped (4 CPU/6 GiB/30 GiB), both aarch64/containerd. Global Docker
context `default`; no inherited/default kubeconfig. Do not use these historical
observations as fresh stop authority.

## Task 1: Verify preserved evidence and acquire exclusive local execution

- [ ] Obtain explicit approval for this plan's one graceful stop, with no deletion or retry.
- [ ] From the receipt directory run `shasum -a 256 -c SHA256SUMS`. Require all 29 listed files to verify; retain this output separately.
- [ ] Verify the transcript export's five-file `SHA256SUMS` separately. The transcript is the current task's recorded visible messages and tool activity through the user's latest request, not other tasks or hidden reasoning.
- [ ] Confirm `report.json` is inconclusive, with null profile binding, `manual_recovery: true`, zero request intents/attempts and empty joined results. Otherwise stop: the proposed recovery premise no longer matches.
- [ ] Hold the existing `LabLock` continuously across preflight, intent, stop and post-observation. Do not call `main()` or `ExploratoryLifecycle.execute()`. If busy or ancestry/permissions fail, stop without operating on the profile. The lock does not exclude outside actors; request no concurrent Colima/Lima/Docker operations from the user.

## Task 2: Establish a fresh, narrowly scoped manual-stop candidate

- [ ] Authenticate the Docker executable against the retained accepted SHA-256 `a078469d8b77683b81e1604ee35af488ef143a8a0230897f05f0839b2f42d1dd`. Observe Colima version again; require the exact v0.10.3/commit `00f6c297e92a82c04a4ab507db0a61435650d7e8` output. No tool replacement/download is authorized.
- [ ] Run Colima `list --json` bracketed by `capture_roster`; require `require_complete` and equality of the bracketing roster. Require exactly the three expected profiles: only `kil-v3-lab` Running with its captured resources, and both foreign rows unchanged and Stopped. If the lab is already Stopped with otherwise matching rows, issue no stop, skip the running-container query and Task 3, and proceed to read-only Task 4 reporting an already-stopped condition. Any additional profile, missing row, changed foreign status/resource or transport/schema failure stops this plan.
- [ ] Read `profile-created.json` using `read_regular` with a 1 MiB maximum; validate its capture schema. Collect two equal fresh `capture(ProfilePaths.bind(receipt))` observations. Compare the retained/fresh records for `profile`, `instance`, `disk`, `profile_config`, `instance_config`, `lima_config`, `data_disk`, `root_disk` and `lock` byte-for-byte. Require `protected` and `startup` absent in both. A changed inode, directory entry list, saved configuration, disk size/format/probe or lock target refuses this plan. Do not normalize the generated DNS entry or call a weakened `creation_binding`.
- [ ] Capture the present complete foreign roster, Docker context and kubeconfig fingerprints as a **manual-recovery pre-stop baseline**. Record the known `_networks` mismatch against the original separately; do not overwrite `foreign-original.json` or claim the new baseline repairs it. Require other original captured identities and global state still match. Unknown new differences stop this plan.
- [ ] Query only the explicit lab endpoint for containers, using the accepted Docker client and the receipt's private Docker configuration. Require a successful, empty result from this exact command; any container or uncertain result refuses the stop because the VM may have acquired another workload:

```text
/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.tools/bin/docker --host unix:///Users/mistorm/.colima/kil-v3-lab/docker.sock ps --all --quiet --no-trunc
```

Use an explicit sanitized child environment: HOME from passwd; accepted tool
PATH; `DOCKER_CONFIG` set to the receipt's `docker-config`; no inherited
DOCKER_CONTEXT, DOCKER_HOST, TLS, certificate, KUBECONFIG or Colima/Lima override.
Use existing `capture_process` for every native instruction: 10-second read
timeouts, 8 MiB aggregate stdout/stderr bound, and the repository as cwd. Retain
complete bounded results. Timeout, overflow, nonzero status or malformed output
is refusal, not permission to retry or substitute a direct socket/process action.

## Task 3: Record intent and issue at most one graceful stop

- [ ] Warn before dispatch: the stop frees VM memory/CPU but preserves the 60 GiB data disk, 20 GiB root disk and profile. It may also change Lima-managed shared networking; exact post-state will be reported, not promised unchanged.
- [ ] In a fresh exclusive `PrivateStore` under the separate recovery directory, retain the pre-stop observations and an immutable `manual_stop_intent.json`. Record exact target paths/record hashes, user approval, Colima version, empty container observation, command argv, 300-second timeout and `max_instructions: 1`. Fsync before native dispatch. An existing/pending/completed intent refuses a second dispatch; it is not a resume mechanism.
- [ ] Immediately recheck the held lock, complete roster, all candidate footprint records and empty container roster against Task 2. Any replacement or change stops before the instruction. This is not atomic exclusion of outside actors; unexpected concurrent activity is a blocker.
- [ ] Invoke exactly the displayed Colima graceful-stop command once through `capture_process`, with 300-second timeout and 8 MiB aggregate output maximum. Keep the same sanitized environment and private Docker configuration. Retain the raw result separately from the old receipt. No `--force`, process kill, `limactl stop`, delete, shared-network edit or fallback is permitted.
- [ ] If the command fails, times out, overflows or returns ambiguously, mark recovery inconclusive. Read-only post-observation is allowed, but no second stop is authorized. The bounded wrapper can terminate its own newly launched command process group on timeout; that is not permission to kill discovered host-agent/VM processes.

## Task 4: Observe post-state, preserve disks and hand off

- [ ] Run one bounded complete post-stop inventory with stable roster bracketing. Success requires `kil-v3-lab` Stopped and both foreign rows matching their fresh pre-stop baseline. If already Stopped before Task 3, issue no stop and report an observed already-stopped condition instead of claiming this workflow stopped it.
- [ ] Capture profile/disk state read-only. Require original profile, instance, config, root/data-disk identities and sizes retained. Report the expected stopped disk-lock release; do not synthesize a creation binding or use these observations as deletion authority.
- [ ] Compare foreign Lima roster, global Docker context and kubeconfig fingerprints with the separate pre-stop baseline and original baseline. Report every difference, especially `_networks`; even a stopped VM does not establish full strict foreign-preservation acceptance. Do not restore/recreate directories or switch contexts.
- [ ] Retain an outcome distinguishing `graceful_stop_confirmed` from inconclusive observations, command uncertainty and foreign-state differences. Checksum the new recovery evidence. Keep both failed receipts and transcript exports unchanged; append specialist lineage and regenerate/check its reader.
- [ ] End at this stopping place. VM startup, profile/data deletion, parser work and another request-free rehearsal or HF action require separate scope/approval. A fresh exploratory launcher will still refuse the preserved existing profile.

## Stop conditions and explicit exclusions

Never identify a cleanup target merely by name. Changed footprint, nonempty lab,
busy local lock, concurrent native operation, new foreign/global difference,
unreadable/partial inventory or command uncertainty means report and stop.
No recursive deletion, force shutdown, disk deletion, orphan/disk fallback,
Lima/shared-network restoration, strict-verifier bypass, guest-image audit,
parser change or HF request is part of this plan. Deletion is materially
different and would require a new exact-target recovery design and authorization.

The DNS parser mismatch and shared-network inode behavior must be independently
understood and reviewed before proposing future lab setup. Merely accepting the
DNS entry would not repair the second gate. No such implementation is specified
or authorized here.

## Verification and handoff criteria

Plan preparation: prior lineage preserved as an exact prefix; only this plan,
its generated reader and appended lineage/reader are tracked changes; transcript
is ignored/private and checksummed; no VM mutation during this preparation.
Execution: all Task 1–2 preconditions plus durable once-only intent before the
single instruction; fresh complete post-state before claiming graceful-stop
success. No mocked/unit success can substitute for those observations.

Accepted local-Envoy evidence remains unchanged. Platform-image provenance is
unverified; full Kind/Calico acceptance remains not established. This recovery
does not measure KIL behavior or historical HF incident prevention.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
