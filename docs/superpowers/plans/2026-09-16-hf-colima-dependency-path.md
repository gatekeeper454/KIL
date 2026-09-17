# Scoped Colima dependency PATH Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make private Colima mutations find only the already accepted tools
without changing global PATH, strict grammar or other command dispatch.

**Architecture:** One exploratory runner unit snapshots a bounded exact tools
directory and authenticates its three executables before PATH priority is granted.
Resolve Colima from the original sanitized PATH and preserve its absolute selection.
Repeat dependency authentication across existing IO before final dispatch guards.

**Tech Stack:** Python standard library, unittest, existing accepted manifest,
RuntimeAuthority and BoundedRunner.

---

Approved design: ../specs/2026-09-16-hf-colima-dependency-path-design.md.
Existing externally managed detached worktree is preserved; no dependency install,
new worktree, branch move, merge or push. Code changes ONLY
src/kil/hf_exploratory_io.py and tests/test_hf_exploratory_io.py. No strict,
Native/CLI, accepted artifact, old receipt or failed-runtime edits. Root alone
may later execute one conditionally authorized fresh rehearsal; no worker may
run native tools, HTTP/HF, Ollama or a platform-image audit.

Interpreter: /Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python.
Every test: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src and -W error::ResourceWarning.
Baseline: 77 IO/runtime tests passed in 2.554s. Prior full discovery has exactly
four preserved historical citation omissions (one failure) and 16 intentional
skips; neither receipts nor exemptions may be changed to hide that limitation.

### Task 1: One bounded runner dependency-authority unit

Files: modify src/kil/hf_exploratory_io.py and its existing test module only.
No new production module or public interface. Add imports shutil/stat and private
helpers in the same IO unit; the reference implementation below may be simplified
only while preserving the approved behavior and every rejection.

- [ ] Write real temporary fixtures and the missing behavior assertion first:

```python
def test_private_start_uses_verified_dependency_path_and_original_colima(self):
    from kil.hf_exploratory_runtime import ExploratoryColimaCommand
    from kil.v3b2_journal import colima_start_command
    authority = self.runtime_authority()
    tools = Path(self.temp.name).resolve() / 'accepted-bin'
    tools.mkdir()
    payloads = {}
    for name in ('docker', 'kind', 'kubectl'):
        payloads[name] = (name + ' inert fixture, never executed').encode()
        (tools / name).write_bytes(payloads[name])
        (tools / name).chmod(0o755)
    original = tools.parent / 'original-bin'
    original.mkdir()
    colima = original / 'colima'
    colima.write_bytes(b'inert original Colima fixture, never executed')
    colima.chmod(0o755)
    inputs = self.accepted_inputs(tools)
    real_verify = self.io.verify_bytes
    rows = inputs.tool_records
    def fixture_verify(payload, digest, size):
        if digest == ACCEPTED_MANIFEST_SHA256:
            return real_verify(payload, digest, size)
        for name, row in rows.items():
            if digest == row['executable_sha256'] and payload == payloads[name]:
                self.assertEqual(size, row['byte_size'])
                return digest
        return real_verify(payload, digest, size)
    runner = self.io.BoundedRunner(Path.cwd(), inputs)
    adapter = ExploratoryColimaCommand(colima_start_command(), authority)
    with patch.dict(os.environ, {'PATH': str(original)}), \
            patch.object(self.io, 'verify_bytes', side_effect=fixture_verify), \
            patch.object(self.io, 'capture_process') as capture:
        runner.run(adapter)
        argv, environment = capture.call_args.args[:2]
        self.assertEqual(argv[0], str(colima))
        self.assertEqual(environment['PATH'], str(tools) + os.pathsep + str(original))
        self.assertEqual(dict(adapter.env), {key: environment[key] for key in dict(adapter.env)})
        self.assertEqual(os.environ['PATH'], str(original))
```

Only executable digest fixtures and capture are mocked. Actual full manifest
authentication, file bytes/permissions, executable search, directory roster,
RuntimeAuthority and metadata shape/type checks stay real. Refactor the test-only
fixture for subsequent cases without adding any test-only production API.

- [ ] Run this exact test -v; expected behavioral assertion FAIL (original
  capture argv is bare colima and no authenticated PATH prefix), not an import
  or fixture error. Record RED before any production edit.
- [ ] Add failing start/stop/delete assertions and negative tests for missing/
  substituted Docker/Kind/kubectl, symlink/relative/noncanonical/separator tools
  paths, extra entries and nonexecutable files. Each requires ValueError and
  capture.assert_not_called(). Existing rejection cases are regressions; do not
  weaken guards to manufacture RED. Add missing/nonregular/nonexecutable Colima
  and original PATH tail/environment preservation cases.
- [ ] Implement private identity/roster/snapshot helpers, closing every fd on
  all outcomes, with this complete reference algorithm:

```python
def _dependency_identity(row):
    return tuple(getattr(row, key) for key in (
        'st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_nlink',
        'st_size', 'st_mtime_ns', 'st_ctime_ns'))

def _dependency_names(fd):
    names = set()
    with os.scandir(fd) as entries:
        for entry in entries:
            names.add(entry.name)
            if len(names) > 3:
                raise ValueError('unexpected_dependency_directory_entry')
    if names != set(TOOL_VERSION_ARGUMENTS):
        raise ValueError('incomplete_dependency_directory')
    return names

def _dependency_snapshot(tools, accepted):
    if (not isinstance(tools, Path) or not tools.is_absolute()
            or '..' in tools.parts or os.pathsep in str(tools)
            or tools.resolve(strict=True) != tools):
        raise ValueError('unsafe_dependency_tools_path')
    fd = os.open(tools, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        directory = _dependency_identity(os.fstat(fd))
        if directory != _dependency_identity(tools.lstat()):
            raise ValueError('dependency_directory_reanchored')
        _dependency_names(fd)
        files = []
        for name in sorted(TOOL_VERSION_ARGUMENTS):
            before = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or not before.st_mode & stat.S_IXUSR):
                raise ValueError('dependency_not_regular_executable')
            payload = read_regular(tools / name, 128 * 1024 * 1024)
            row = accepted[name]
            digest = verify_bytes(payload, row['executable_sha256'], row['byte_size'])
            after = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if _dependency_identity(before) != _dependency_identity(after):
                raise ValueError('dependency_changed_during_read')
            files.append((name, _dependency_identity(after), digest))
        _dependency_names(fd)
        if (directory != _dependency_identity(os.fstat(fd))
                or directory != _dependency_identity(tools.lstat())
                or tools.resolve(strict=True) != tools):
            raise ValueError('dependency_directory_changed')
        return directory, tuple(files)
    finally:
        os.close(fd)

def _colima_dependency_executable(path):
    found = shutil.which('colima', path=os.defpath if path is None else path)
    if found is None:
        raise ValueError('original_colima_unavailable')
    executable = Path(found)
    if (not executable.is_absolute() or '..' in executable.parts
            or executable.resolve(strict=True) != executable):
        raise ValueError('unsafe_original_colima')
    row = executable.lstat()
    if not stat.S_ISREG(row.st_mode) or not row.st_mode & stat.S_IXUSR:
        raise ValueError('original_colima_not_regular_executable')
    return executable, _dependency_identity(row)
```

- [ ] In run(), define the finite route only after exact type/grammar validation:

```python
scoped_mutation = type(command) is ExploratoryColimaCommand and command.mutating
```

For that route, preserve original environment.get('PATH'), resolve Colima before
prefixing, snapshot inputs.tools against fresh authenticated accepted rows and
dispatch argv=(str(colima_executable), *command.argv[1:]). Set only the copied
environment's PATH to str(tools)+(os.pathsep+original_path if original_path else '').
Do not mutate command.env or os.environ. Normalize OSError/Attribute/Key/Type/
Value dependency failures into ValueError before capture.

- [ ] Extend existing tools-path comparisons to this route. After second manifest
  authentication, re-run the full dependency snapshot and require exact equality;
  recheck original Colima canonical spelling and recorded identity. Keep these
  checks before the existing final adapter validation/fingerprint guard and final
  no-IO manifest/metadata exact consistency block. Preserve existing direct-tool
  executable reauthentication and no further authentication IO before capture.
- [ ] Write failing drift regressions: directory identity replacement, executable
  bytes or executable permission drift, tools-path replacement during manifest/
  dependency verification, and unexpected entries. Spy wrappers call real guards
  and real manifest verification, mutate only the intended temporary fixture,
  and require zero capture. GREEN each correction before adding the next behavior.
- [ ] Confirm scoped readonly/global Colima and direct tool families retain
  their original PATH/environment/dispatch. Run focused IO/runtime tests and the
  combined 15 modules below. Self-review scoped diff, append actual-EOF lineage
  with exact prior prefix, render/check readers and diff-check. Commit exact
  source/test + lineage pair only. Release exclusive writer.
- [ ] Independent SPEC then QUALITY review. Correct important findings test-first
  and re-review. Final independent whole-change review before root native gate.

### Root verification and conditional fresh rehearsal

- [ ] Fresh designated-interpreter run of these exact modules:

```text
tests.test_hf_exploratory_runtime tests.test_hf_exploratory_profile
tests.test_hf_exploratory_evidence tests.test_hf_exploratory_case
tests.test_hf_exploratory_inputs tests.test_hf_exploratory_io
tests.test_hf_exploratory_native tests.test_v3b2_profile_state
tests.test_v3b2_journal tests.test_v4_future_controller_gate
tests.test_v3b2_inventory tests.test_v3b2_colima_inventory
tests.test_v3b2_runtime_inventory_ownership tests.test_v3b2_bootstrap_inventory
tests.test_v3b2_runtime_image_inventory
```

- [ ] Verify unchanged strict/Native/CLI/accepted artifacts, exact earlier lineage
  prefix, reader check, diff check and clean committed source. Record actual counts
  and prior broad-suite limitation, with no merge/PR/all-green assertion.
- [ ] Use the already granted conditional permission only if all repair readiness
  gates succeed. Invoke reviewed LabLock/verify_inputs/PrivateStore/BoundedRunner/
  ExploratoryLifecycle APIs once with mode='rehearsal', fresh nonce and exact clean
  reviewed HEAD. Never invoke the looping CLI main, which automatically continues
  into action. Source/input preflight and native command session run outside the
  sandbox because sandboxed macOS Git produces confstr stderr warnings; do not
  suppress warnings or bypass the fail-closed gate.
- [ ] Capture, verify every retained receipt checksum, report foreign-state checks,
  observed leftovers and zero request intents. Stop on inconclusive outcome;
  no retry/adoption/delete beyond exact guarded owned teardown. Preserve all
  failed-run bytes. Append final root lineage, render/check and clean checkpoint.

## Plan self-review

Every approved route, file/roster/authentication constraint, original executable
selection, freshness check and unchanged consumer maps to Task 1. Root gates
cover conditional single native attempt, unchanged strict artifacts and honest
evidence/reporting. Names match existing APIs; no unrelated refactor or omitted
authority boundary is planned. No native worker or image audit is authorized.

KTP citation: [canonical CITATION.cff](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
