# Exploratory HF Generated SSH Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Tasks1–5 form one coupled bounded implementation unit; use test-first development and ordered independent SPEC, QUALITY and final composed reviews. Root coordinates local checkpoints and all native gates.

**Goal:** Permit exactly the pinned producer's fresh run-owned SSH controls without opening the exploratory lifecycle's closed roster or mutation authority.

**Architecture:** Add a focused descriptor-owning SSH-control proof helper, used only by `hf_exploratory_native.py`. Bind the producer pair after successful native start, profile creation binding, and exact Running inventory; authenticate both names, retained descriptors, metadata, and bytes at every private inventory and dispatch closure. Treat native stop/delete as explicit one-shot transition brackets, with exact post-state proof before adopting any stopped/removed binding.

**Tech Stack:** Existing Python standard library, unittest, real test-owned files, current PrivateStore/RuntimeAuthority APIs. No additional dependencies.

---

## Execution context and authorized scope

- Exact existing detached worktree: `/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL`. Preserve it and all retained prior runs.
- Read source at preparation HEAD `8736eeb46d7d7dc60d4f512324f74a35721e40b1`; parent performs clean source/input gates before any later native lifecycle.
- Interpreter: `/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python`, always `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src`, with `-W error::ResourceWarning`.
- User instruction `fix the ssh issue so we can get past it. do what is necessary to make it work` authorizes this necessary bounded compatibility fix and preparation. No extra fix approval pause. Complete engineering/reviews before parent performs its separately controlled one fresh request-free rehearsal; only a complete accepted rehearsal can unlock the retained single conditional HF action authorization.
- Never edit strict launchers/controllers, accepted recovery/permission helpers, provenance materials, recovered runtime resources, or predecessor receipts. Root owns local scoped checkpoints. Implementer may edit only authorized helper/native/tests; no native execution.

## Files and responsibilities

Create `/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL/src/kil/hf_exploratory_ssh.py`: producer grammar plus paired generated-control proof, with no commands, writes to producer files, recovery, or external path selector.

Create `/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL/tests/test_hf_exploratory_ssh.py`: real files/descriptors and exact adversarial grammar/identity/transition coverage.

Modify `/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL/src/kil/hf_exploratory_native.py`: initialization/close, start binding, private roster/inventory closure, final intent-to-dispatch closure, native stop/delete transition proof, and new-run SSH evidence.

Modify `/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL/tests/test_hf_exploratory_native.py`: native producer fixtures/doubles and lifecycle/intent/cleanup regressions. Existing `create_native_profile` fixture should create producer SSH pair; double stop truncates Colima control and leaves instance unchanged; double delete removes instance as already modeled and leaves exact stopped Colima control or removes it in dedicated variants.

No production runtime/profile modules need alteration. Reuse retained RuntimeAuthority root directory descriptor and `runtime.guard()`; helper creates/owns all additional directory/file descriptors it retains.

## Exact producer grammar (implementation contract)

The account observed in the pinned producer is literal `mistorm`. Use that exact fixed account for this selected environment; do not accept an environment variable, caller account, whitespace, or other user syntax. The only dynamic values are derived runtime paths and a producer-observed canonical decimal Port in 1..65535. Encode derived paths using UTF-8, and refuse ambiguous newline, CR, quote, backslash, NUL, noncanonical path, or control-character bytes rather than adding SSH escaping syntax.

Expected Colima bytes are exactly this template including two final LF bytes:

```text
# This SSH config file can be passed to 'ssh -F'.
# This file is created by Lima, but not used by Lima itself currently.
# Modifications to this file will be lost on restarting the Lima instance.
Host colima-kil-v3-lab
  IdentityFile "{runtime}/.colima/_lima/_config/user"
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  NoHostAuthenticationForLocalhost yes
  PreferredAuthentications publickey
  Compression no
  BatchMode yes
  IdentitiesOnly yes
  GSSAPIAuthentication no
  Ciphers "^aes128-gcm@openssh.com,aes256-gcm@openssh.com"
  User mistorm
  ControlMaster auto
  ControlPath "{runtime}/.colima/_lima/colima-kil-v3-lab/ssh.sock"
  ControlPersist yes
  Hostname 127.0.0.1
  Port {port}

```

Expected instance bytes are the exact same template with `Host lima-colima-kil-v3-lab` and exactly one final LF. Validate the full byte sequences, never a general SSH parser, split-token dictionary, unordered directive set, substring match, or broad whitespace normalization. Extract Port with a fixed-position anchored decimal expression; reject `0`, `65536`, leading zeros, signs, floats, trailing whitespace/bytes, and more than five digits. Construct exact expected sequences from derived paths plus the observed port, require both complete sequences to match, then compare the pair while normalizing only the single exact Host line and single exact extra trailing LF. Preserve raw producer bytes and hashes in evidence.

Sealed recovery source used read-only: `.../.tools/hf-recovery-private/2026-09-17/manual-stop-254877dc1b1462c4e29c068e51ad7286fe430b075bc5044c8b3076d1887ad25d/{pre-colima-ssh.config,pre-instance-ssh.config,pre-observations.json,post-observations.json}`. Historical Colima length 767, instance length 771; hashes are observations, never future expected pins. Colima mode is exactly 0644; instance mode exactly 0600. Post-stop Colima remains present with same inode, 0644 and exact zero bytes; instance retains its identity and all bytes unchanged. Parent explicitly accepted zero-byte Colima as necessary pinned native stop compatibility, alongside absent or unchanged bound control; arbitrary stopped syntax remains forbidden.

## Helper interface and proof state

Keep this a small proof helper, not a new authority subsystem. Use `GeneratedSSHControls.capture(runtime)` requiring `type(runtime) is RuntimeAuthority`, derive all names internally, and expose only `guard()`, bounded transition snapshot checking, `document()`, and idempotent `close()`. Reuse RuntimeAuthority's established anchors/guard; retain only additional instance/file descriptors and proof bytes. Lifecycle holds `ssh_controls` and a narrow phase (`pristine`, `binding`, `running`, `stop_pending`, `stopped`, `delete_pending`, `removed`), plus `profile_start_succeeded`, `profile_stop_succeeded`, and `profile_delete_succeeded` flags. Set success only after exact runner command returned zero and observe has retained terminal output/receipt; attempted flags and profile_binding alone never grant transition. A transition snapshot is local captured data tied to this proof/runtime; the lifecycle adopts it only after its own successful command and exact state proofs. No caller flag or snapshot grants native authority.

`capture` opens `.colima`, `_lima`, and exact `colima-kil-v3-lab` directory components relative to RuntimeAuthority's retained root fd, with `O_DIRECTORY|O_NOFOLLOW`; retains their fd/identity plus parent/name edges. Require owner effective UID and exact private directory modes already proved by native profile/runtime contracts rather than inventing a mode incompatible with generated instance state. Cross-check instance directory device/inode/mode against existing creation binding. Bind two files relative to retained parent fds, `ssh_config` and `ssh.config`, with `O_RDONLY|O_NOFOLLOW|O_NONBLOCK`.

Every file read is bounded to 16384 bytes, regular, owner effective UID, exact per-file mode, one link; read at most bound+1, and compare stat tuples `(dev,ino,mode,uid,nlink,size,mtime_ns,ctime_ns)` before/after read and against no-follow named stat. Require exact count and stable full bytes, then close the read with both earlier/later file identities and all directory edges rechecked. Keep retained descriptors, raw bytes, full metadata, endpoint port, and SHA256. Failure closes every partially opened owned fd, leaves no adopted proof, and never changes producer files.

`guard` authenticates runtime first and last, every retained directory edge, both current no-follow file names and retained file fds, all metadata, and full bytes; reread both and close both file proofs after the paired read. This detects same-size edits, replace-then-restore metadata, renames, owner/mode/link drift, ancestor replacement, missing files, fd substitution, and late replacement during second-file reading. Treat OSError/uncertain reads as refusal, not absence. Only FileNotFoundError on the exact anchored name is absence; absence is allowed solely in explicit native transition state.

Stop observation permits Colima (a) unchanged original binding, (b) anchored absence, or (c) exactly zero-byte owned regular 0644 one-link file after the successful exact native stop return. For (c), permit original inode truncation or securely captured replacement only inside that native bracket, retain its new descriptor/metadata/bytes and close the observation across both controls. Instance must remain exact original identity/metadata/bytes. Stopped adoption occurs only after existing unchanged profile proof and exact complete Stopped inventory pass and candidate is freshly reauthenticated. Thereafter stopped closure is immutable; a second truncate/replacement/new disappearance is refused.

Delete observation permits removal of exact owned instance directory/file after successful exact delete return and confirmed profile/resource absence; any surviving instance or unknown/replaced directory fails. Colima must be unchanged stopped binding or anchored absent; do not adopt new content or another empty inode at delete. Retained instance descriptors may have `nlink=0` due to native removal; do not mistake that expected transition for live owned control or dereference deleted paths. Close retained fds after evidence and removal proof. Original runtime `.colima`/`_lima` anchors must remain authenticated throughout.

Evidence uses new-run top-level names `ssh-control-colima.running.config`, `ssh-control-instance.running.config`, `ssh-controls.running.json`; stopped/removal records use `ssh-controls.stopped.json` / `ssh-controls.removed.json` plus stopped Colima bytes only when present. Record present=false distinctly from present=true empty; schema `kil.hf-generated-ssh-controls.v1`, runtime binding digest, phase, exact paths, raw byte counts/hashes/full stat identities, and observed port. Evidence writes do not overwrite predecessor receipts. After writing evidence, reauthenticate control proof and read back new retained files via `private_read` before adopting/dispatching.

## Task 1: Failing pure grammar and owned-file tests

- [ ] Create test class using real TemporaryDirectory under `/private/tmp`, current NativeTests-style patched `_registry_parent`, genuine PrivateStore/RuntimeAuthority, derived paths, and minimal profile fixture. Each test cleans up helper before runtime before store; no native subprocesses.
- [ ] Add valid running pair fixture using the exact template above and modes 0644/0600. Assert capture retains raw bytes, matching port, distinct aliases, exact hashes/identities, and `guard()` succeeds.
- [ ] Add table rejection tests for wildcard/second Host, Include, ProxyCommand, ProxyJump, directives reordered/duplicated/removed/added, changed comments/options, User/root/other, nonloopback Hostname, all invalid port formats, mismatched paired port, another run's IdentityFile/ControlPath, extra blank line, CR/NUL/tab/invalid UTF-8, quote/backslash path injection. Assert no general normalization accepts them.
- [ ] Add pre-start presence tests for exact and malformed Colima file and symlink/directory/FIFO. Assert start refusal before durable command intent/runner.
- [ ] Run new grammar test module before production helper exists: expect ImportError/missing-helper FAIL; retain red test result as test-first evidence.
- [ ] Implement exact template validation and capture/guard/close only. Run new module: expect all grammar tests PASS.

## Task 2: Failing descriptor and stable closure tests

- [ ] Add real files for Colima bad mode 0600/0664/0444, instance bad mode0644, hardlinks, directory, symlink, FIFO, oversized file, and file replacement. Check helper rejects quickly without blocking on FIFO.
- [ ] Add wrong UID tests using narrowly scoped mocked fstat/stat rows around real descriptor reads; do not chown, escalate, or claim mocks as native evidence. Add same-size byte mutation, mtime-restoration with changed ctime, parent replacement, retained descriptor closed/substituted, named fd mismatch, second-file-read mutation of first file, and capture exception after first file opens. Assert no leaked fds using patched close/open tracking or validated fd count where stable.
- [ ] Run each new test red before hardening implementation; expect specific ValueError/refusal and no native effects.
- [ ] Implement full metadata/byte/directory closure and partial-failure cleanup described above. Rerun helper module with ResourceWarning fatal: expect PASS.

## Task 3: Failing fresh-start and roster integration tests

- [ ] Upgrade `create_native_profile` to create paired controls, account/paths/port from test-owned exact fixture; update lifecycle doubles to emit exact native grammar, never historical private bytes. Existing profile-only fixtures used for strict assertions remain untouched.
- [ ] Add full request-free double lifecycle test that completes with valid generated controls and exact closed roster. Assert running pair evidence retained before Kind create; no HF request intent/attempt; preserved foreign files; final stopped/removal evidence.
- [ ] Add start unsuccessful return with valid controls: no running binding/Kind dispatch; unbound start: no running adoption. Add start successful but stopped/extra/wrong inventory rows: no running adoption. Add another roster name alongside ssh_config: refusal. Add SSH missing/malformed pair after successful start: no Kind/HF dispatch, manual recovery retained.
- [ ] Run tests red against existing `private_inventory` allowed roster. Implement lifecycle initialization and helper close, explicit `profile_start_succeeded` after retained zero-return terminal receipt, post-success-start binding bracket, and roster recognition only when complete generated proof is available. In `setup`, after successful creation binding and successful start return, require authenticated pair and exact Running private inventory before endpoint/Kind checks. Existing setup deliberately captures profile_binding before testing nonzero start; that binding alone must never authorize SSH adoption. Avoid accepting generated controls in a retained failed runtime.
- [ ] In `private_inventory`, require pre-read and post-read local roster checks, keep all existing roster names closed plus conditionally authenticated ssh_config, maintain require_complete before/after Lima roster, close SSH pair proof after native inventory read, and refuse before-start presence. Avoid recursive inventory: generated proof checks are local fd authentication only.
- [ ] Rerun native and helper modules; expect PASS or only explicitly diagnosed new integration failures. Do not weaken old ownership tests to silence failures.

## Task 4: Failing intent-to-dispatch and request closure tests

- [ ] Add durable command_intent hook tests mutating/replacing/removing Colima and instance control between authorization and final dispatch; target Kind create, ordinary setup apply, Kind delete, Colima stop/delete, read command, and action attach. Assert runner not handed off, one-shot attempt flags remain false where not committed, intent remains truthful, cleanup refuses drift.
- [ ] Add mutation immediately before `store.send_once` request-intent write; assert no request intent on known pre-intent drift. Add drift during request intent writing; assert retained uncertain/request intent truthfully preserved, zero runner dispatch/target execution and no retry.
- [ ] Run newly added tests red. Implement local generated-control authentication in `require_dispatch_unchanged` before/after durable intent, without native observation or recursion. Apply pristine absence closure to exact fresh start. Only explicitly in-flight native stopped/delete inventory proof reads can inspect transition candidates; no mutation/attach dispatch while provisional phase exists.
- [ ] Add fresh proof recheck immediately before action `store.send_once`, after current track/driver checks. `observe` final closure remains the consuming attach authority after request-intent persistence.
- [ ] Rerun helper/native modules: expect PASS; preserve existing command-bytes substitution and no-premature-latch regressions.

## Task 5: Failing stopped/removed transition tests

- [ ] Model successful exact stop truncating original Colima fd to empty while retaining exact instance pair. Assert successful Stopped proof adopts exact empty bytes/identity once; stop absent and stop unchanged valid Colima variants also accepted. Distinguish empty and absent evidence.
- [ ] Reject empty Colima before start, while Running, before exact stop dispatch, during stop command-intent, after failed stop return, after runner exception, wrong Stopped inventory/profile, nonempty modified stopped grammar, mode/link/type/UID drift, changed instance bytes, and a late zero-byte inode substitution after adopted stopped proof. Native stop returning success alone never establishes stopped adoption.
- [ ] Model successful delete removing exact instance/profile/disk and unchanged stopped Colima or absent Colima. Reject unknown roster extras after delete, new empty replacement at delete, surviving instance control, foreign instance replacement, failed/uncertain delete, and late ancestor drift. Assert owned_teardown only after profile/resource absence, complete private inventory absence, local roster closure, stopped/removed SSH closure, reset store authorization, and foreign preservation.
- [ ] Run new transition tests red. Implement exact command success flags after `observe` returns (not merely attempted flags), provisional stop/delete candidate observation, accepted state adoption only after exact existing profile/inventory proof and fresh candidate closure. In `_cleanup_native`, establish stop proof before setting profile_stopped, and delete removal proof before profile_delete_completed/owned_teardown. Expand `private_inventory_absent` to close local roster plus SSH removed state before and after native list, preserving require_complete.
- [ ] Run full helper/native modules: expect PASS, including inconclusive/manual recovery behavior on any drift.

## Task 6: Scoped regressions and ordered reviews

From the exact worktree run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_exploratory_ssh tests.test_hf_exploratory_native tests.test_hf_exploratory_runtime tests.test_hf_exploratory_profile tests.test_hf_exploratory_io tests.test_hf_exploratory_evidence tests.test_hf_compact_residual_recovery tests.test_hf_recovery_parent_permissions tests.test_v3b2_profile_state tests.test_v3b2_inventory tests.test_v3b2_journal tests.test_v3b2_controller
```

- [ ] Expect exit0 and OK; if existing failures appear, diagnose and report precisely before next gate. Do not claim broader repository all-green or alter known citation omissions.
- [ ] Independent SPEC review compares patch/tests against exact grammar, owner/descriptor proof, lifecycle transition contracts, closed roster, and conditional execution scope. Address findings test first.
- [ ] Independent QUALITY review examines fd ownership/cleanup, race/recursion/dispatch closure, evidence ordering, mock realism, and minimal scope. Address findings test first.
- [ ] Final composed review joins implementation and ordered review resolution with scoped test evidence and retained source/artifact constraints. Parent records lineage and any authorized checkpoint; this preparation agent edits no repository lineage.
- [ ] Parent proceeds only after all engineering gates pass to the fresh request-free rehearsal, verifies full lifecycle, zero HF intents/attempts, exact owned teardown, retained checksums and foreign preservation. Failure/uncertainty stops with no automatic retry/recovery. Conditional action remains one instruction per fixed track, three total, fresh lifecycle, durable intent and final joined evidence, subject to retained authorization.

## Self-review

Coverage: Tasks1/2 cover exact grammar, paired aliases/LF, distinct modes, bounded no-follow descriptors, stable closure, partial-failure cleanup and pristine presence; Task3 covers successful fresh ownership and closed native inventory; Task4 covers known pre-intent and late intent/dispatch/request drift; Task5 covers exact successful native stop empty/absent/unchanged and delete removal, no arbitrary content adoption; Task6 covers scope, regressions and ordered independent reviews. Keep helper minimal using existing RuntimeAuthority, with successful native start/stop/delete flags explicit after retained terminal receipts. No production implementation or native command has been performed during planning. The native stopped-empty behavior is explicitly incorporated with parent acceptance; additional producer differences remain refusal/blockers rather than fallback scope.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
