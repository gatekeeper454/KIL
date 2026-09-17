# KIL HF Test — Residual VM Recovery

Date: 2026-09-17. Condensed handoff, not a complete transcript export.

Read this file first. Resume at the **pending stop-only approval gate**, not
design, implementation or a platform-image audit. Preparing this handoff does
not approve a stop, create a new task or authorize HF traffic.

## Exact workspace

Working directory:
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL`

Existing externally managed, detached linked worktree; preserve it. Do not
silently switch to the saved project's main checkout, create another worktree,
install dependencies, merge, push or clean up.

Python:
`/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python`

Use `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src` and `-W error::ResourceWarning`.
Snapshot before this documentation handoff: clean commit
`27b882984437be17a16709dd1dcbb44b2bb56452`.
The handoff commit advances HEAD: freshly verify current exact HEAD and clean
status for any later approved execution. Do not pass historical27b8829/88e37c5
as a new execution source binding.

## Confirmed state and remaining uncertainty

- Goal: the previously selected narrower exploratory live HF incident test,
  explicitly leaving platform-image provenance unverified. Accepted local-Envoy
  evidence remains unchanged; full Kind/Calico acceptance is false. Recovery is
  a prerequisite/housekeeping step, not the HF test itself.
- T430: one separately approved stop-only attempt refused preflight with
  `recovery_directory_not_private`, exit1, stop_dispatches0. Existing recovery
  parent was0755; no native acquisition, stop intent or final recovery receipt
  was created. That stop permission ended despite zero dispatches.
- T439: user "Do next" approved ONE pinned-parent mode attempt. At clean
  `88e37c5f1da777cc4da307fd948157a1c9c84a05`, the dedicated helper ran once;
  exit0/`mode_change_confirmed`, fchmod_attempts1, certainty returned,0755→0700.
  Target dev16777232/inode612764151, UID501/GID20, identity/linkcount/size/mtime,
  ancestors, existing lock and one direct child's metadata passed preservation;
  all owned teardown passed, errors empty. Completion observed by20:45:42 UTC.
  The tool wrote no receipt bytes or new private evidence. This is NOT a
  descendant-content attestation or atomic snapshot. Mode permission is spent;
  do not rerun the helper merely to observe an already0700 directory.
- Current VM status is **UNOBSERVED**, not refreshed by mode remediation or this
  handoff. Historical T419 private VM Running is stale. The same-name global/
  default Stopped profile is foreign and NEVER the private stop target. No VM
  stop, HF request, Ollama, new rehearsal or image/SSH audit followed T439.
- Fixing the mode blocker does not guarantee all recovery preconditions pass
  or resolve the earlier production SSH-control compatibility refusal.

## Fixed recovery identity and accepted engineering

Accepted entry: `tools/hf_compact_residual_recovery.py` (guarded main only).
Private profile: `kil-v3-lab`, under
`/Users/mistorm/.kil-hf/r254877dc1b1462c4`.
Run digest:
`254877dc1b1462c4e29c068e51ad7286fe430b075bc5044c8b3076d1887ad25d`.
Runtime root ID4: `(16777232,615011851,16832,501)`.
The tool fixes the retained receipt and new2026-09-17/manual-stop evidence path;
do not repin, substitute another namespace/date or choose another suffix.

Freshly matched source/test SHA256 at handoff capture:

- Recovery tool: `2b58ab2392543611f64044f5d2624f07edfa03ed4c988e1bff2c03d137ccf864`.
- Recovery tests: `a4ee14ce13dd569bc1a1202ffab3be450fed8bbae954be96b98600caeccaf64f`.

Recorded completed verification: recovery214 tests, ordered independent reviews
and final674-test/312.194s scoped regression; permission helper43 tests, complete
SPEC/QUALITY/fresh final review,468-test/306.343s combined regression, then fresh
post-mode43/0.460s. Engineering bytes remain unchanged. Do not restart those
engineering tasks or a broad provenance audit. Fresh source/identity checks and
the accepted live preflight still apply. No full-discovery-green claim: four
known immutable historical citation omissions remain untouched/unexempted.

## Next action — approval first

Ask NEW explicit approval for ONE accepted stop-only recovery attempt of this
fixed private residual VM, including its live preflight and exclusive evidence
creation. CPU/RAM may be released; disks/profile/config remain; native controls
may change. The handoff request is NOT that approval.

After approval, follow Task6 in the recovery plan and the actual unchanged tool.
Only root dispatches once. Display actual argv using fresh verified clean40-hex
HEAD and actual new approval; main requires `--reviewed-source`,
`--execution-approval` and `--execute-approved-stop`. Use scoped outside-sandbox
approval where needed. Do not invoke the exploratory launcher or construct
_Native/RuntimeAuthority to bypass the gate.

Any refusal, timeout, overflow, lost result or partial evidence ends permission:
no retry, force, deletion, restart, discovered-process kill, alternate receipt,
repair/rebaseline/reseal or rollback. Preserve actual dispatch count/certainty
through all teardown. If already stopped, accepted preflight determines the
no-stop outcome; do not force a dispatch. Record the final returned result after
all closure; a sealed observation with `final_closure_pending=True` is provisional.
Stop at that result. HF compatibility, request-free rehearsal and live action
remain separate gates; original rehearsal/spent approvals do not revive.

## Evidence routing; keep initial context small

Paths below are relative to the exact workspace. Read only relevant sections
on demand, not the entire large lineage/transcript at startup:

- `docs/superpowers/plans/2026-09-17-hf-compact-residual-vm-recovery.md`:
  final engineering record, Task6 and T430 native-attempt record.
- `docs/superpowers/specs/2026-09-17-hf-compact-residual-vm-recovery-design.md`:
  approved fixed stop-only requirements.
- `docs/superpowers/plans/2026-09-17-hf-recovery-parent-permissions.md`:
  final preparation and actual mode-only record with verbatim canonical stdout.
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`: T430, T438, T439; append-only
  specialist history. Follow root `AGENTS.md`; append dated substantive entries.
- `docs/transcripts/KIL-architecture-full-transcript-2026-09-14.md`:
  older architecture-task export, exported2026-09-15,1298 visible messages;
  NOT a complete export of this current HF task. Keep the original HF task as
  historical conversation archive. This handoff does not update either export.

User preference: any genuinely new engineering uses approved design/spec,
test-first implementation, subagent-driven preparation and independent reviews.
Live operations stay root-only. This preference does not require repeating
accepted preparation. Do not modify protected recovery/production/deploy/
artifacts or historical private evidence just to resume.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
