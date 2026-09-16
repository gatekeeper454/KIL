# Isolated exploratory HF launcher repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the exploratory launcher’s native namespace, exact generated
configuration binding and evidence lifetime without relaxing strict acceptance.

**Architecture:** Derive one fresh fd-anchored runtime sibling per source-bound
receipt. A closed exploratory Colima adapter names that namespace; independent
pure profile binding admits the pinned generated instance form. Only immutable
snapshots enter receipts, while every default-home resource remains foreign.

**Tech Stack:** Python standard library, unittest, existing bounded runner,
PrivateStore and LabLock; pinned Colima 0.10.3 / Lima 2.2.0 contracts.

---

## Approved scope and execution constraints

Design: [approved design](../specs/2026-09-16-hf-exploratory-launcher-repair-design.md).
Engineering only: no native command, VM operation, Kind cluster, HTTP/HF
request, Ollama operation, old receipt modification or platform-image audit.
Tests use temporary files and command-boundary doubles, not native execution.
Keep accepted inputs, strict source/tests, sixteen deferrals and fixed tracks.
The old stopped default-home lab remains foreign; its missing receipt metadata
is not reconstructed. Preserve the existing externally managed detached worktree.

Interpreter for every command below:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest
```

Append one lineage entry per implementer/review phase with exclusive writer
handoff. Preserve the earlier Markdown prefix. Render/check indexed readers
with `tools/render_markdown.py` using the same interpreter. Commit only the
named unit and documentation; no integration, branch movement or push.

## File structure and stable interfaces

- Create `src/kil/hf_exploratory_runtime.py`: `RuntimeAuthority.create(store,
  run_digest)`, `guard()`, `close()`, derived `path`, `colima`, `lima`,
  `docker_config`, `tmp`, `kubeconfig`, `kind_config`; exclusive bounded
  `write_control(name, payload)` for only kind-config.yaml. No configurable
  endpoint/home. `ExploratoryColimaCommand(command, authority)` wraps exactly a
  strict empty-env Colima Command and exposes its argv/timeout/mutating/stdin
  plus the four derived environment entries. Validation occurs at construction
  and fresh dispatch; no subclass or arbitrary environment escape.
- Create `tests/test_hf_exploratory_runtime.py`: real temporary filesystem tests
  of creation/identity/closed grammar, not native subprocesses.
- Create `src/kil/hf_exploratory_profile.py`: `ProfilePaths.bind(authority)` with
  actual passwd home and derived runtime; same collector-facing path properties.
  Exact document `{home, runtime}`. Pure `parse_saved_instance(payload)`,
  `creation_binding(document, observed)`, `unchanged(..., stopped=False)`,
  `absent(document, observed)`. Reuse no-follow capture/schema/disk-probe helpers
  without changing any strict module or treating runtime root as passwd HOME.
- Create `tests/test_hf_exploratory_profile.py`: independent generated-form
  fixture, full raw hashes and protected/replaced/stopped/absence cases.
- Create `src/kil/hf_exploratory_evidence.py` and
  `tests/test_hf_exploratory_evidence.py`: bounded no-follow immutable runtime
  snapshots and explicitly partial leftover observations; never erase runtime.
- Modify `src/kil/hf_exploratory_io.py:BoundedRunner.run`: accept only exact
  strict Command or exact exploratory adapter, with fresh authority guard before
  process dispatch. Strict Command itself stays byte-for-byte unchanged.
- Modify `src/kil/hf_exploratory_native.py:ExploratoryLifecycle`: runtime
  authority ownership, explicit global/private Colima dispatch, two inventory
  domains, moved Kind controls, exact profile binding, snapshot-before-stop,
  runtime reporting and close. Preserve attempt latches and experiment logic.
- Modify `tools/hf_exploratory_kind.py:main`: close lifecycle/runtime descriptors
  in finally before PrivateStore close; no retry/resume/runtime-home CLI flag.
- Modify `tests/test_hf_exploratory_native.py` and
  `tests/test_hf_exploratory_io.py`: migrate fixtures into the derived layout,
  maintain original protection assertions and add composition regressions.

### Task 1: Derived runtime authority and finite Colima adapter

- [x] Write a behavior assertion before implementing the missing module:

```python
def test_runtime_is_a_fresh_receipt_sibling(self):
    self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_runtime'),
                         'isolated runtime authority is missing')
    from kil.hf_exploratory_runtime import RuntimeAuthority
    authority = RuntimeAuthority.create(self.store, 'a' * 64)
    self.addCleanup(authority.close)
    self.assertEqual(authority.path, self.store.path.parent /
                     ('hf-exploratory-runtime-' + 'a' * 64))
    self.assertNotEqual(authority.path, self.store.path)
    for path in (authority.path, authority.colima, authority.lima,
                 authority.docker_config, authority.tmp):
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
    authority.guard()
```

The fixture creates `.tools/hf-exploratory-private` under TemporaryDirectory,
mode 700, and PrivateStore `hf-exploratory-` plus 64 a’s. Register cleanup before
each failing assertion to ensure no descriptor leak. Run
`tests.test_hf_exploratory_runtime -v`; expected assertion failure stating the
authority is missing, not an import error.

- [x] Implement creation only after RED. Validate lowercase 64-hex digest and
  exact matching receipt basename, receipt live fd identity, canonical absolute
  parent with the expected `.tools/hf-exploratory-private` suffix, effective-uid
  ownership/private mode. Open each ancestor with `_parent`; retain parent fd.
  Create the sibling and four directories exclusively via mkdirat, openat
  O_DIRECTORY|O_NOFOLLOW; fsync parent at every creation. Any existing directory
  refuses adoption. Record initial device/inode/type/mode/uid and retain fds.
  Release all descriptors on construction failure without deleting anything.
  Guard named entries against retained fd identities and no-follow ancestry;
  root/Colima/Lima/Docker/tmp deletion, symlink, inode/mode/owner substitution
  refuses. Guard does not freeze mutable native directory contents.

- [x] Add failing adapter tests for exact four namespace variables, foreign
  env, non-Colima argv, subclass/wrong authority, grammar substitution and a
  deleted/replaced private Colima home. Implement the finite wrapper:

```python
@dataclass(frozen=True)
class ExploratoryColimaCommand:
    command: Command
    authority: RuntimeAuthority

    def __post_init__(self):
        if type(self.command) is not Command or type(self.authority) is not RuntimeAuthority:
            raise ValueError('invalid_exploratory_colima_authority')
        self.command.__post_init__()
        if self.command.argv[0] != 'colima' or self.command.env:
            raise ValueError('exploratory_colima_requires_closed_empty_env_command')
        self.authority.guard()

    @property
    def argv(self): return self.command.argv
    @property
    def timeout_s(self): return self.command.timeout_s
    @property
    def mutating(self): return self.command.mutating
    @property
    def stdin(self): return self.command.stdin
    @property
    def env(self):
        return (('COLIMA_HOME', str(self.authority.colima)),
                ('LIMA_HOME', str(self.authority.lima)),
                ('DOCKER_CONFIG', str(self.authority.docker_config)),
                ('TMPDIR', str(self.authority.tmp)))
```

- [x] Add failing exclusive-control tests: only kind-config.yaml, bytes <=64K,
  no overwrite, no symlink adoption, stale authority refuses. Implement write
  with guarded root fd, O_EXCL|O_NOFOLLOW mode600, full write loop/fsync and root
  fsync. Derived kubeconfig is a native output, not written by this helper.
- [x] Run runtime tests and existing IO/native tests; expect all pass with
  runtime not yet integrated. Self-review; append lineage, render/check readers,
  diff-check, commit `feat: bind exploratory Colima to isolated runtime state`.
- [x] Independent SPEC review followed by QUALITY review; correct/re-review
  any important issue with test-first corrections before Task 2.

### Task 2: Exact exploratory saved forms and resource binding

- [x] Write independent full generated-instance bytes from the retained failure
  (not from the parser under test). The saved profile retains empty dnsHosts;
  instance has exactly this two-line block within the network section:

```yaml
  dnsHosts:
    host.docker.internal: host.lima.internal
```

```python
def test_exact_generated_instance_is_bound_with_original_bytes(self):
    self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_profile'),
                         'exploratory native configuration binding is missing')
    from kil.hf_exploratory_profile import creation_binding
    binding = creation_binding(self.paths.document(), self.observed)
    self.assertEqual(binding['config_sha256']['instance'],
                     sha256(INSTANCE_SAVED).hexdigest())
    self.assertNotEqual(binding['config_sha256']['instance'],
                        binding['config_sha256']['profile'])
```

Fixture collector uses real temporary profile/disk files with sparse 60/20GiB
capacities and 512 zero header bytes; no VM disk contents or native tools.
Run `tests.test_hf_exploratory_profile -v`; expect the named missing-feature
assertion before production code.

- [x] Implement derived ProfilePaths with actual home + runtime (not fake HOME).
  Require exact lowercase digest runtime basename and private parent shape.
  Pure document decoding accepts exactly two string fields. Collector paths
  are runtime/.colima, its _lima, kil-v3-lab, colima-kil-v3-lab disk/instance,
  _store/name.json and runtime/runtime-tmp/name.yaml. Re-export collectors only
  where useful; never edit strict code.
- [x] Implement exact instance syntax recognition, followed by strict scalar
  validation on an internal validation-only copy; raw observations stay intact:

```python
def parse_saved_instance(payload):
    if type(payload) is not bytes or len(payload) > MAX_CONFIG:
        raise ProfileStateError('saved instance exceeds bound')
    block = b'  dnsHosts:\n    host.docker.internal: host.lima.internal\n'
    if payload.count(block) != 1:
        raise ProfileStateError('generated DNS mapping is not exact')
    result = parse_saved(payload.replace(block, b'  dnsHosts: {}\n', 1))
    result['network']['dnsHosts'] = {'host.docker.internal': 'host.lima.internal'}
    return result
```

- [x] Add failing negative tests for wrong alias/value, extra/duplicate hosts,
  duplicate dnsHosts, tags/anchors, extra keys/mounts, profile generated mapping,
  instance empty mapping, ambiguous indentation and byte overflow. Verify RED
  individually before adding corresponding rejection where not already strict.
- [x] Implement creation binding with `validate_capture`, protected/startup
  absence, eight concrete directory/file identities, strict profile parse,
  generated instance parse, raw byte hashes, raw60GiB data/raw20GiB root, full
  Lima bytes/hash, exact lock target equal to the derived private instance.
  Return existing six-field binding schema; validate_binding remains strict.
  No capture normalization enters the binding or receipt.
- [x] Write failing changed-resource/stopped/absence tests. Recompute the same
  binding before mutation; stopped missing lock is admitted only as an internal
  pure validation probe with corresponding directory entry. Protected or
  substituted config/disk/id/lock remains rejected. Absence requires no profile,
  instance, disk or startup and absent/exact zero native store. No orphan cleanup.
- [x] Run runtime/profile tests plus strict profile tests; all pass and strict
  source/tests unchanged. Append lineage, render/check, diff-check; commit
  `fix: bind exact exploratory Colima generated configuration`.
- [x] Independent SPEC then QUALITY review, test-first corrections and re-review.

### Task 3: Integrate two inventory domains and frozen evidence lifetime

- [x] Migrate native fixtures to the exact source-bound receipt basename and
  private runtime layout, patch only passwd-home lookup to temporary user home.
  Preserve original fixed-track/no-replay/incarnation assertions. Fake Colima
  dispatch differentiates default read-only list from private adapter env and
  writes the independent exact generated config form under private paths.
  Do not mock guards or binding in composition regressions.
- [x] Write failing runtime dispatch tests in existing IO tests: scoped commands
  use four derived variables with true passwd HOME, inherited overrides absent,
  strict extra-env Command still rejects, replaced home refuses before Popen.
  Implement exact-type adapter recognition and guard both at entry and after
  tool verification, immediately before bounded capture. Keep bounds unchanged.
- [x] Write failing native composition assertions before wiring the lifecycle:

```python
def test_same_name_default_profile_remains_foreign(self):
    from tests.test_v3b2_profile_state import create_profile
    create_profile(self.life.default_paths)
    (self.life.default_paths.disk / 'in_use_by').unlink()
    self.full_fake_runner()
    before = capture(self.life.default_paths)
    report = self.execute_fake()
    self.assertEqual(report['status'], 'complete')
    self.assertEqual(capture(self.life.default_paths), before)
    self.assertNotEqual(self.life.paths.profile, self.life.default_paths.profile)

def test_native_context_removal_does_not_invalidate_receipts(self):
    self.full_fake_runner()
    original = self.runner.run.side_effect
    context = self.life.runtime.docker_config / 'contexts/meta' / sha256(
        b'colima-kil-v3-lab').hexdigest() / 'meta.json'
    def remove_on_stop(command):
        result = original(command)
        if command.argv == ('colima', 'start', *colima_start_command().argv[2:]):
            context.parent.mkdir(parents=True, exist_ok=True)
            context.write_bytes(b'{"Name":"colima-kil-v3-lab"}\n')
        if command.argv == ('colima', 'stop', '--profile', 'kil-v3-lab'):
            context.unlink()
        return result
    self.runner.run.side_effect = remove_on_stop
    report = self.execute_fake()
    self.assertEqual(report['status'], 'complete')
    for name, expected in self.life.retained_checksums().items():
        self.assertEqual(sha256((self.store.path / name).read_bytes()).hexdigest(), expected)
    self.assertFalse(context.exists())
    self.assertTrue((self.store.path / 'runtime-docker-context-meta.json').exists())
```

Use the existing full lifecycle double as the starting point; retain real
binding/receipt validation. Tests observe production behavior, not just calls.

- [x] Lifecycle creates RuntimeAuthority from live Store + workload digest and
  owns descriptors. `close()` releases descriptors only. Move identity kubeconfig
  to runtime.kubeconfig and derive Docker/Kind env from runtime. Keep a separate
  strict default ProfilePaths(actual_home, receipt). Wrap scoped empty-env Colima
  commands; default inventory uses only exact plain read-only list through an
  explicit global dispatch path. No arbitrary global Colima mutation.
- [x] Guard runtime on every dispatch and exact commands before durable intent.
  Preserve start/create/stop/delete one-attempt latches and intent-before-action.
  Private preflight bracket is complete/empty. Private live bracket allows only
  creation-bound kil-v3-lab and known reserved Lima entries, exact running/stopped
  resources. Recheck private inventory and concrete binding before each mutation.
  Default bracket includes EVERY row/child with no same-name filter. Snapshot
  `_config/networks.yaml` no-follow raw identity/bytes <=64K and compare before/
  after; any default roster/file/config change fails. Preserve default Docker
  context/config identity and inherited/default kubeconfig commitments unchanged.
- [x] Prepare canonical one-node kind config in both immutable Store and runtime
  exclusive control helper; Kind reads only runtime copy and use requires fresh
  exact retained-byte verification. Do not mkdir runtime dirs inside receipt.
  Keep Calico/object manifests immutable in Store and all workload joins unchanged.
- [x] Evidence helper snapshots a finite set: runtime kind-config.yaml/kubeconfig,
  private profile+instance colima.yaml/lima.yaml, runtime Docker config.json and
  exact contexts/meta/SHA256(colima-kil-v3-lab)/meta.json. No generic directory
  walker. Use `_read`/no-follow helpers (64KiB per file, stable identity/full
  bytes); retain absence as observation, never fabricate. Write raw bytes and
  canonical observed-only path/identity/size/hash ledger exclusively into Store.
  Guard before/after capture. Snapshot once before stop, also before reporting
  partial setup failures when safely observable. Snapshot failure refuses native
  cleanup rather than erasing evidence under uncertainty.
- [x] Write RED tests for context removal, symlink/oversize/replaced snapshot
  targets, private network reset permitted, default network reset rejected,
  extra private profile rejected and stale controls refusing Kind. Implement
  immutable snapshots, default/private guard differentiation and commitment
  checks. Report explicit runtime vs receipt vs default paths and bounded,
  explicitly partial leftover directory observations after cleanup. Never
  recursively remove runtime siblings; native exact-owned deletion only.
- [x] CLI finally closes lifecycle (if constructed) then Store. Construction
  errors close authority fds. No new command-line options, retry or auto resume.
- [x] Run runtime/profile/evidence/all four exploratory test modules plus strict
  profile/inventory/journal tests and driver boundary guards; expect all pass.
  Append lineage, readers/check, diff-check, commit
  `fix: isolate exploratory native lifecycle and freeze runtime evidence`.
- [x] Independent SPEC then QUALITY review; correct and re-review all important
  gaps. Final reviewer inspects the entire repair against the approved design.

## Final verification and next gate

- [x] Fresh full unittest discovery with ResourceWarning fatal; distinguish
  intentional opt-in skips from failures. No native opt-in variables enabled.
- [x] Verify strict source/test diff empty relative to 89a641a, immutable earlier
  lineage prefix, reader check, diff check, clean local source checkpoint.
- [x] Record actual test counts/reviews/limitations, not native compatibility
  claims. Append root lineage and checkpoint. No merge, push or native test.
- [ ] Next user gate is permission for a fresh request-free PRIVATE native
  setup/capture/teardown rehearsal. Only a successful fully retained rehearsal
  can permit the separate fresh fixed-three-track action; no historic replay
  or full Kind/Calico acceptance is inferred.

## Plan self-review — 2026-09-16

Coverage: runtime/home/fallback/closed-command authority is Task 1; exact raw
native configuration and pure stopped/absence binding is Task 2; dispatch,
Kind controls, two inventory domains, network protection, evidence lifetime,
CLI fd lifecycle and leftovers are Task 3. Existing experiment guards are
regressions, not redesign. Interface names above are shared across units.
Negative cases receive RED verification before rejection changes; already
rejected cases remain regression tests. No native operation is a plan step.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

## Execution outcome — 2026-09-16

The approved engineering design is implemented and independently reviewed.
Task checkboxes record performed engineering steps; they do not assert a green
full repository suite or authorize native execution. The last permission gate
above remains unchecked.

- Task 1: derived RuntimeAuthority and closed Colima adapter; 28 runtime tests.
- Task 2: exact exploratory saved-form/resource binding; 18 profile tests.
  Two independent full saved YAML fixtures preserve their original bytes.
  The .gitattributes exception is limited to those two fixture paths, solely
  to retain native trailing-space blank lines.
- Task 3 was split into IO/evidence (3A) and Native/CLI composition (3B), with
  49 IO, 12 evidence and 116 Native tests. Real temporary filesystem authority,
  collectors and retained-byte binding remain active in composition tests;
  native process capture/command boundaries are doubled.
- Review corrections were test-first: fd/lock authority edges; late manifest,
  executable-path and exact metadata-map drift; durable-intent namespace and
  Kind consumer freshness; valid-command substitution and handoff latches.
  Final metadata regressions produced nine expected pre-fix failures.
- Final source checkpoint is 06e6c35. Runtime/profile/IO SPEC and QUALITY,
  Native SPEC/QUALITY and final composed review are approved. Final correction
  review receipts: bcef18a (SPEC), 1f0bb62 (QUALITY), 30376e2 (Native QUALITY),
  094c12f (final composed review). The composed reviewer independently passed
  73 targeted tests in 9.505s; Native QUALITY passed 116 in 37.735s.

Root's fresh required 15-module suite passed **410 tests in 93.542s**, with
ResourceWarning fatal and bytecode generation disabled. Fresh full repository
discovery, with future-controller opt-in disabled and the preverified local
AF_UNIX/bash descriptor fixtures allowed outside the sandbox, ran **1,849 tests
in 907.006s: one failure, 16 intentional skips, no errors**. The failure is
test_every_kil_authored_markdown_document_cites_ktp, identifying exactly four
existing ignored immutable historical documents:

- .tools/hf-exploratory-private/hf-exploratory-4bf272a01cfdb5c96ab08a70def03ecbd7a29ef375bbe957ae0be6b991409bfe/synopsis.md
- .tools/hf-exploratory-private/hf-exploratory-5507a11d6dd49a2ddca0d2588e7ad484b2bcf808ec3744d05b1aa966a746d7e2/synopsis.md
- .tools/hf-recovery-private/2026-09-16/README.md
- .tools/hf-recovery-private/2026-09-16/manual-stop-4bf272a0-post-verification.md

Those files and citation-test exemptions were not changed. The new plan's own
citation omission was corrected in 5fb0b53; tracked nonexempt Markdown has no
citation omission. The broader suite is **not green**, so no merge/PR is offered.

Strict V3/V4 source/tests/tools, accepted inputs/local-Envoy artifacts and all
sixteen deferrals remain unchanged relative to 89a641a. Its 1,140,588-byte
lineage prefix is preserved exactly. Final reader/prefix/diff checks and root
lineage checkpoint accompany this progress update.

No actual Colima/Lima/Docker/Kind/kubectl, VM operation, HTTP/HF request, Ollama
operation, platform-image audit, old receipt/export edit, metadata reconstruction,
branch move, merge or push occurred. The externally managed detached worktree
is retained. Platform-image provenance remains unverified and full Kind/Calico
acceptance remains false; the accepted local-Envoy result is unaffected.

Next action requires separate permission for a fresh request-free PRIVATE
setup/capture/teardown rehearsal from the clean reviewed local checkpoint.
Only successful fully retained rehearsal evidence can gate the separate fresh
fixed-three-track action. No historic replay, native compatibility or complete
filesystem-removal claim follows from these engineering tests.
