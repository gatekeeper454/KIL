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

- [ ] Write a behavior assertion before implementing the missing module:

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

- [ ] Implement creation only after RED. Validate lowercase 64-hex digest and
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

- [ ] Add failing adapter tests for exact four namespace variables, foreign
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

- [ ] Add failing exclusive-control tests: only kind-config.yaml, bytes <=64K,
  no overwrite, no symlink adoption, stale authority refuses. Implement write
  with guarded root fd, O_EXCL|O_NOFOLLOW mode600, full write loop/fsync and root
  fsync. Derived kubeconfig is a native output, not written by this helper.
- [ ] Run runtime tests and existing IO/native tests; expect all pass with
  runtime not yet integrated. Self-review; append lineage, render/check readers,
  diff-check, commit `feat: bind exploratory Colima to isolated runtime state`.
- [ ] Independent SPEC review followed by QUALITY review; correct/re-review
  any important issue with test-first corrections before Task 2.

### Task 2: Exact exploratory saved forms and resource binding

- [ ] Write independent full generated-instance bytes from the retained failure
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

- [ ] Implement derived ProfilePaths with actual home + runtime (not fake HOME).
  Require exact lowercase digest runtime basename and private parent shape.
  Pure document decoding accepts exactly two string fields. Collector paths
  are runtime/.colima, its _lima, kil-v3-lab, colima-kil-v3-lab disk/instance,
  _store/name.json and runtime/runtime-tmp/name.yaml. Re-export collectors only
  where useful; never edit strict code.
- [ ] Implement exact instance syntax recognition, followed by strict scalar
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

- [ ] Add failing negative tests for wrong alias/value, extra/duplicate hosts,
  duplicate dnsHosts, tags/anchors, extra keys/mounts, profile generated mapping,
  instance empty mapping, ambiguous indentation and byte overflow. Verify RED
  individually before adding corresponding rejection where not already strict.
- [ ] Implement creation binding with `validate_capture`, protected/startup
  absence, eight concrete directory/file identities, strict profile parse,
  generated instance parse, raw byte hashes, raw60GiB data/raw20GiB root, full
  Lima bytes/hash, exact lock target equal to the derived private instance.
  Return existing six-field binding schema; validate_binding remains strict.
  No capture normalization enters the binding or receipt.
- [ ] Write failing changed-resource/stopped/absence tests. Recompute the same
  binding before mutation; stopped missing lock is admitted only as an internal
  pure validation probe with corresponding directory entry. Protected or
  substituted config/disk/id/lock remains rejected. Absence requires no profile,
  instance, disk or startup and absent/exact zero native store. No orphan cleanup.
- [ ] Run runtime/profile tests plus strict profile tests; all pass and strict
  source/tests unchanged. Append lineage, render/check, diff-check; commit
  `fix: bind exact exploratory Colima generated configuration`.
- [ ] Independent SPEC then QUALITY review, test-first corrections and re-review.

### Task 3: Integrate two inventory domains and frozen evidence lifetime

- [ ] Migrate native fixtures to the exact source-bound receipt basename and
  private runtime layout, patch only passwd-home lookup to temporary user home.
  Preserve original fixed-track/no-replay/incarnation assertions. Fake Colima
  dispatch differentiates default read-only list from private adapter env and
  writes the independent exact generated config form under private paths.
  Do not mock guards or binding in composition regressions.
- [ ] Write failing runtime dispatch tests in existing IO tests: scoped commands
  use four derived variables with true passwd HOME, inherited overrides absent,
  strict extra-env Command still rejects, replaced home refuses before Popen.
  Implement exact-type adapter recognition and guard both at entry and after
  tool verification, immediately before bounded capture. Keep bounds unchanged.
- [ ] Write failing native composition assertions before wiring the lifecycle:

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

- [ ] Lifecycle creates RuntimeAuthority from live Store + workload digest and
  owns descriptors. `close()` releases descriptors only. Move identity kubeconfig
  to runtime.kubeconfig and derive Docker/Kind env from runtime. Keep a separate
  strict default ProfilePaths(actual_home, receipt). Wrap scoped empty-env Colima
  commands; default inventory uses only exact plain read-only list through an
  explicit global dispatch path. No arbitrary global Colima mutation.
- [ ] Guard runtime on every dispatch and exact commands before durable intent.
  Preserve start/create/stop/delete one-attempt latches and intent-before-action.
  Private preflight bracket is complete/empty. Private live bracket allows only
  creation-bound kil-v3-lab and known reserved Lima entries, exact running/stopped
  resources. Recheck private inventory and concrete binding before each mutation.
  Default bracket includes EVERY row/child with no same-name filter. Snapshot
  `_config/networks.yaml` no-follow raw identity/bytes <=64K and compare before/
  after; any default roster/file/config change fails. Preserve default Docker
  context/config identity and inherited/default kubeconfig commitments unchanged.
- [ ] Prepare canonical one-node kind config in both immutable Store and runtime
  exclusive control helper; Kind reads only runtime copy and use requires fresh
  exact retained-byte verification. Do not mkdir runtime dirs inside receipt.
  Keep Calico/object manifests immutable in Store and all workload joins unchanged.
- [ ] Evidence helper snapshots a finite set: runtime kind-config.yaml/kubeconfig,
  private profile+instance colima.yaml/lima.yaml, runtime Docker config.json and
  exact contexts/meta/SHA256(colima-kil-v3-lab)/meta.json. No generic directory
  walker. Use `_read`/no-follow helpers (64KiB per file, stable identity/full
  bytes); retain absence as observation, never fabricate. Write raw bytes and
  canonical observed-only path/identity/size/hash ledger exclusively into Store.
  Guard before/after capture. Snapshot once before stop, also before reporting
  partial setup failures when safely observable. Snapshot failure refuses native
  cleanup rather than erasing evidence under uncertainty.
- [ ] Write RED tests for context removal, symlink/oversize/replaced snapshot
  targets, private network reset permitted, default network reset rejected,
  extra private profile rejected and stale controls refusing Kind. Implement
  immutable snapshots, default/private guard differentiation and commitment
  checks. Report explicit runtime vs receipt vs default paths and bounded,
  explicitly partial leftover directory observations after cleanup. Never
  recursively remove runtime siblings; native exact-owned deletion only.
- [ ] CLI finally closes lifecycle (if constructed) then Store. Construction
  errors close authority fds. No new command-line options, retry or auto resume.
- [ ] Run runtime/profile/evidence/all four exploratory test modules plus strict
  profile/inventory/journal tests and driver boundary guards; expect all pass.
  Append lineage, readers/check, diff-check, commit
  `fix: isolate exploratory native lifecycle and freeze runtime evidence`.
- [ ] Independent SPEC then QUALITY review; correct and re-review all important
  gaps. Final reviewer inspects the entire repair against the approved design.

## Final verification and next gate

- [ ] Fresh full unittest discovery with ResourceWarning fatal; distinguish
  intentional opt-in skips from failures. No native opt-in variables enabled.
- [ ] Verify strict source/test diff empty relative to 89a641a, immutable earlier
  lineage prefix, reader check, diff check, clean local source checkpoint.
- [ ] Record actual test counts/reviews/limitations, not native compatibility
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
