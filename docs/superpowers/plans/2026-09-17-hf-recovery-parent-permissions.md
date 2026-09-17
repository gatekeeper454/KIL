# Fixed HF recovery parent permission preparation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare a fixture-verified, separately approved one-shot change of the one pinned evidence parent's mode from0755 to0700 without changing receipts or contacting the VM.

**Architecture:** A dedicated tool retains no-follow directory descriptors, opens only the existing cooperating lock, and commits to bounded direct-child metadata. An entry-consumed fchmod slot, stable post-observation and complete owned teardown keep syscall certainty, observed mode and verification separate. Engineering uses real owned temporary fixtures; live permission execution and native recovery remain separate gates.

**Tech Stack:** Existing Python3.12/unittest, POSIX directory descriptors/stat/pread/scandir/fchmod/fsync, nonblocking flock, existing bounded clean-source helper, canonical JSON.

---

## Approval, worktree and file map

The user approved the written
`docs/superpowers/specs/2026-09-17-hf-recovery-parent-permissions-design.md`
at clean checkpoint8b5714377cce4e3dffdf5ce6aaec926a5247099a.
This approves planning and fixture-only preparation, **not live fchmod or VM
recovery**. The spent T430 stop permission remains spent. Preserve the user's
subagent-driven preparation with independent spec and quality reviews.

Use the existing externally managed detached linked worktree:
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL`.
No worktree/branch creation, relocation, dependency installation, merge or push.

Create only these engineering files:

- `tools/hf_recovery_parent_permissions.py`: private, fixed-target one-shot
  procedure and strict CLI; no generic permission/recovery API.
- `tests/test_hf_recovery_parent_permissions.py`: real owned-temp proof,
  mutation, refusal, late-failure, bound, non-action and cleanup tests.

Documentation changes are this plan, appended approval records in its spec,
append-only `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md` and their readers.
The accepted recovery tool/tests, production Native/Runtime/Profile/IO,
strict verifiers/launcher, deploy, accepted artifacts, citation policy and all
historical private evidence are read-only. No actual `.tools` permission change,
lock/receipt creation or native/runtime/guest/disk access during engineering.

All blocks marked `permission-tool` concatenate in task order into the new
tool. Blocks marked `permission-tests` concatenate into the new test file.
Neither implementation file exists at this planning checkpoint. These are
concrete implementation instructions, not claims of tested behavior. Each
task's RED run precedes addition of its corresponding implementation block.
Test fixtures may patch only fixed location/pin constants and unavoidable
account/source selection; faults wrap real syscalls/proof methods and call
their originals unless intentionally raising. Never mock a filesystem guard
into success or treat fixtures as live VM/evidence observations.

## Common commands and baseline

Use the existing interpreter, bytecode disabled, ResourceWarning fatal:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_exploratory_io tests.test_v3b2_profile_state tests.test_hf_compact_residual_recovery
```

Require actual OK; record count/duration, not a predicted count. These are
fixture regressions, not native queries. An unknown failure triggers
systematic-debugging; do not fix protected production code. The known four
immutable historical citation omissions are disclosed, not repaired/exempted.

Each task's commit also includes its factual append-only lineage entry and
regenerated affected readers. Root owns docs and exact-path staging/commit;
implementers own only the two new engineering files. Use a fresh implementer
per task when available; if the host's agent limit prevents this, report it
and obtain direction rather than silently substituting the requested workflow.
Spec review precedes quality review for each completed task; Important findings
receive a genuine failing regression before the minimum fix. Reviewers do not
edit files, acquire actual locks or execute any live permission/native command.

## Task 1: Retained read-only ancestry and exact pins

**Files:** Create the two new paths. Read the approved spec and
`src/kil/v3b2_profile_state.py` for no-follow patterns; edit neither.

- [x] Add this initial test block before creating the tool.

<!-- permission-tests -->
```python
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/hf_recovery_parent_permissions.py'
SOURCE = 'a' * 40
APPROVAL = 'fixture-only permission test'


def load_tool():
    if not TOOL.is_file():
        raise AssertionError('fixed permission tool is missing')
    spec = importlib.util.spec_from_file_location('hf_permission_fixture', TOOL)
    if spec is None or spec.loader is None:
        raise AssertionError('fixed permission tool is not loadable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.temp = tempfile.TemporaryDirectory(prefix='kil-mode-', dir='/private/tmp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.tools = self.root / '.tools'
        self.target = self.tools / 'hf-recovery-private'
        self.lock_parent = self.tools / 'hf-exploratory-private'
        self.tools.mkdir(mode=0o700)
        self.target.mkdir(mode=0o755)
        self.target.chmod(0o755)
        self.lock_parent.mkdir(mode=0o700)
        self.lock = self.lock_parent / 'profile.lock'
        self.lock.write_bytes(b'cooperating fixture lock\n')
        self.lock.chmod(0o600)
        self.receipt = self.target / 'retained'
        self.receipt.mkdir(mode=0o700)
        self.payload = self.receipt / 'outcome.json'
        self.seal = self.receipt / 'SHA256SUMS'
        self.payload.write_bytes(b'{"historical":true}\n')
        self.seal.write_bytes(b'exact historical seal\n')
        self.payload.chmod(0o600)
        self.seal.chmod(0o600)
        self.original_payload = self.payload.read_bytes()
        self.original_seal = self.seal.read_bytes()
        self.original_modes = [stat.S_IMODE(p.stat().st_mode)
                               for p in (self.receipt, self.payload, self.seal)]
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in {
            'REPOSITORY': self.root, 'TARGET': self.target, 'UID': os.geteuid(),
            'TOOLS_PIN': (self.tools.stat().st_dev, self.tools.stat().st_ino),
            'TARGET_PIN': (self.target.stat().st_dev, self.target.stat().st_ino),
        }.items():
            self.stack.enter_context(patch.object(self.tool, name, value))

    def unchanged_receipts(self):
        self.assertEqual(self.payload.read_bytes(), self.original_payload)
        self.assertEqual(self.seal.read_bytes(), self.original_seal)
        self.assertEqual([stat.S_IMODE(p.stat().st_mode)
                          for p in (self.receipt, self.payload, self.seal)],
                         self.original_modes)


class AncestryTests(Fixture):
    def test_real_named_fd_ancestry_and_all_descriptors_close(self):
        dirs = self.tool._Directories()
        self.addCleanup(dirs.close)
        fd = dirs.directory(self.target)
        dirs.guard()
        self.assertEqual(os.fstat(fd).st_ino, self.target.stat().st_ino)
        descriptors = [record[1] for record in dirs.records.values()]
        self.assertEqual(dirs.close(), [])
        self.assertEqual(dirs.close(), [])
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)
        with self.assertRaises(ValueError):
            dirs.guard()

        self.unchanged_receipts()

    def test_after_guard_rejects_unapproved_initial_target_modes(self):
        for initial_mode in (0o705, 0o777, 0o700):
            self.target.chmod(initial_mode)
            dirs = self.tool._Directories()
            try:
                dirs.directory(self.target)
                self.target.chmod(0o700)
                with self.assertRaises(ValueError):
                    dirs.guard(after=True)
            finally:
                dirs.close()

    def test_after_guard_allows_only_captured_755_to_700(self):
        self.target.chmod(0o755)
        dirs = self.tool._Directories()
        try:
            dirs.directory(self.target)
            captured = {path: record[2] for path, record in dirs.records.items()}
            self.target.chmod(0o700)
            dirs.guard(after=True)
            self.assertEqual(captured, {path: record[2] for path, record in dirs.records.items()})
        finally:
            dirs.close()
        self.unchanged_receipts()

    def test_real_ancestor_reanchor_and_symlink_refuse(self):
        dirs = self.tool._Directories()
        self.addCleanup(dirs.close)
        dirs.directory(self.target)
        moved = self.root / 'moved-tools'
        self.tools.rename(moved)
        self.tools.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError):
            dirs.guard()
        fresh = self.tool._Directories()
        self.addCleanup(fresh.close)
        with self.assertRaises(OSError):
            fresh.directory(self.target)

    def test_target_replacement_or_mode_change_is_not_adopted(self):
        dirs = self.tool._Directories()
        self.addCleanup(dirs.close)
        dirs.directory(self.target)
        self.target.chmod(0o700)
        with self.assertRaises(ValueError):
            dirs.guard()
        self.target.chmod(0o755)
        self.target.rename(self.tools / 'original-target')
        self.target.mkdir(mode=0o755)
        with self.assertRaises(ValueError):
            dirs.guard()
```

- [x] Run RED:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_recovery_parent_permissions.AncestryTests
```

Expected nonzero, with `fixed permission tool is missing`; inspect actual output
to distinguish this intentional absence from an unrelated import failure.

- [x] Create the tool with this complete ancestry block. It contains no mutation.

<!-- permission-tool -->
```python
"""Fixed, separately approved one-directory mode change; never VM recovery."""
import argparse
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys

REPOSITORY = Path('/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL')
TARGET = REPOSITORY / '.tools/hf-recovery-private'
UID = 501
HOME = Path('/Users/mistorm')
TOOLS_PIN = (16777232, 612669178)
TARGET_PIN = (16777232, 612764151)
MAXIMUM = 1024 * 1024


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf-8')


def _id(row):
    return row.st_dev, row.st_ino, row.st_mode, row.st_uid


def _full(row):
    return (row.st_dev, row.st_ino, row.st_mode, row.st_uid, row.st_gid,
            row.st_nlink, row.st_size, row.st_mtime_ns, row.st_ctime_ns)


def _close_fd(fd):
    os.close(fd)


class _Directories:
    def __init__(self):
        self.records = {}
        self.closed = False

    def directory(self, path):
        if self.closed or not path.is_absolute() or '..' in path.parts:
            raise ValueError('permission_ancestry_invalid')
        current, parent = Path('/'), None
        for name in ('/', *path.parts[1:]):
            if name != '/':
                current = current / name
            if current not in self.records:
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=parent)
                # Retain before any stat can raise: close must own this FD.
                self.records[current] = (current, fd, None, parent, name)
                row = os.fstat(fd)
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISDIR(row.st_mode) or _id(row) != _id(named):
                    raise ValueError('permission_directory_unbound')
                self.records[current] = (current, fd, _id(row), parent, name)
            parent = self.records[current][1]
        self.guard()
        return parent

    def guard(self, *, after=False):
        if self.closed:
            raise ValueError('permission_ancestry_closed')
        for path, fd, original, parent, name in self.records.values():
            expected = original
            if after and path == TARGET and original is not None:
                if stat.S_IMODE(original[2]) != 0o755:
                    raise ValueError('permission_initial_transition_not_755')
                expected = (*original[:2],
                            (original[2] & ~0o7777) | 0o700, original[3])
            if (expected is None or _id(os.fstat(fd)) != expected
                    or _id(os.stat(name, dir_fd=parent, follow_symlinks=False)) != expected):
                raise ValueError('permission_directory_changed')

    def close(self):
        if self.closed:
            return []
        self.closed = True
        records, self.records = list(self.records.values()), {}
        errors = []
        for _, fd, _, _, _ in reversed(records):
            try:
                _close_fd(fd)
            except BaseException as error:
                errors.append(error)
        return errors
```

- [x] Repeat the exact Task1 command; require actual OK, closed FD assertions and
  no receipt changes. Review then commit with exact paths:

```sh
git add -- tools/hf_recovery_parent_permissions.py tests/test_hf_recovery_parent_permissions.py docs/superpowers/plans/2026-09-17-hf-recovery-parent-permissions.md docs/superpowers/plans/2026-09-17-hf-recovery-parent-permissions.htm docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm
git commit -m 'feat: retain fixed permission ancestry without mutation'
```

## Task 2: Existing lock and bounded direct-child commitment

**Files:** Append the new tool/test files only. Read
`tools/hf_exploratory_kind.py:23` and its flock protocol without calling
create-capable LabLock.__enter__ or changing it.

- [x] Append these tests before adding `_Proof`.

<!-- permission-tests -->
```python
class ProofTests(Fixture):
    def proof(self):
        proof = self.tool._Proof()
        self.addCleanup(proof.close)
        proof.bind()
        return proof

    def test_existing_lock_and_equal_observations_without_child_reads(self):
        original_pread = os.pread
        reads = []
        def read(fd, maximum, offset):
            reads.append(os.fstat(fd).st_ino)
            return original_pread(fd, maximum, offset)
        with patch.object(self.tool.os, 'pread', side_effect=read):
            proof = self.proof()
            proof.observe()
            proof.metadata()
        self.assertTrue(reads)
        self.assertEqual(set(reads), {self.lock.stat().st_ino})
        self.assertEqual(len(proof.children), 1)
        self.unchanged_receipts()

    def test_missing_lock_refuses_and_does_not_create_it(self):
        self.lock.unlink()
        proof = self.tool._Proof()
        self.addCleanup(proof.close)
        with self.assertRaises(FileNotFoundError):
            proof.bind()
        self.assertFalse(self.lock.exists())

    def test_busy_lock_refuses_using_real_flock(self):
        import fcntl
        fd = os.open(self.lock, os.O_RDONLY | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proof = self.tool._Proof()
        self.addCleanup(proof.close)
        with self.assertRaises(BlockingIOError):
            proof.bind()

    def test_wrong_pins_owner_and_initial_modes_refuse(self):
        cases = [dict(TARGET_PIN=(0, 0)), dict(TOOLS_PIN=(0, 0)),
                 dict(UID=os.geteuid() + 1)]
        for changes in cases:
            with self.subTest(changes=changes), ExitStack() as stack:
                for name, value in changes.items():
                    stack.enter_context(patch.object(self.tool, name, value))
                proof = self.tool._Proof()
                try:
                    with self.assertRaises(ValueError):
                        proof.bind()
                finally:
                    proof.close()
        for mode in (0o700, 0o750, 0o777, 0o1755):
            with self.subTest(mode=mode):
                self.target.chmod(mode)
                proof = self.tool._Proof()
                try:
                    with self.assertRaises(ValueError):
                        proof.bind()
                finally:
                    proof.close()

    def test_lock_metadata_bytes_and_replacement_are_not_adopted(self):
        proof = self.proof()
        self.lock.write_bytes(b'changed cooperating lock\n')
        with self.assertRaises(ValueError):
            proof.observe()
        self.lock.rename(self.lock_parent / 'old-lock')
        self.lock.write_bytes(b'cooperating fixture lock\n')
        self.lock.chmod(0o600)
        with self.assertRaises(ValueError):
            proof.metadata()

    def test_children_drift_refuses_without_descendant_interpretation(self):
        proof = self.proof()
        self.receipt.chmod(0o755)
        with self.assertRaises(ValueError):
            proof.observe()
        # A direct symlink is metadata, not permission to follow it.
        other = self.tools / 'outside'
        other.write_bytes(b'never opened by proof')
        (self.target / 'pointer').symlink_to(other)
        with self.assertRaises(ValueError):
            proof.observe()

    def test_256_names_pass_and_257_or_oversized_name_refuse(self):
        for index in range(255):
            (self.target / ('n' + str(index))).mkdir(mode=0o700)
        proof = self.proof()
        self.assertEqual(len(proof.children), 256)
        proof.close()
        (self.target / 'n255').mkdir(mode=0o700)
        fresh = self.tool._Proof()
        try:
            with self.assertRaisesRegex(ValueError, 'permission_children_bound_or_name'):
                fresh.bind()
        finally:
            fresh.close()
        (self.target / 'n255').rmdir()
        for index in range(255):
            (self.target / ('n' + str(index))).rmdir()
        (self.target / ('x' * 129)).mkdir(mode=0o700)
        fresh = self.tool._Proof()
        try:
            with self.assertRaisesRegex(ValueError, 'permission_children_bound_or_name'):
                fresh.bind()
        finally:
            fresh.close()

    def test_post_metadata_requires_validated_baseline(self):
        proof = self.proof()
        os.fchmod(proof.target, 0o700)
        os.utime(self.target, ns=(self.target.stat().st_atime_ns,
                                 proof.before[7] + 1000000000))
        for method in ('metadata', 'observe'):
            with self.subTest(method=method):
                with self.assertRaisesRegex(ValueError, 'permission_post_baseline_unavailable'):
                    getattr(proof, method)(after=True)

    def test_validated_post_baseline_preserves_other_commitments(self):
        proof = self.proof()
        ancestors = {path: record[2] for path, record in proof.dirs.records.items()}
        children = list(proof.children)
        os.fchmod(proof.target, 0o700)
        proof.bind_post()
        proof.metadata(after=True)
        proof.observe(after=True)
        self.assertEqual(ancestors, {path: record[2] for path, record in proof.dirs.records.items()})
        self.assertEqual(children, proof.children)
        self.unchanged_receipts()
```

- [x] Run RED (expected `_Proof` missing, nonzero):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_recovery_parent_permissions.ProofTests
```

- [x] Append the complete existing-only lock/metadata implementation.

<!-- permission-tool -->
```python
class _Proof:
    def __init__(self):
        self.dirs = _Directories()
        self.target = self.lock = self.lock_parent = None
        self.before = self.post = self.lock_identity = None
        self.lock_payload = self.children = None
        self.closed = False

    def bind(self):
        tools = self.dirs.directory(REPOSITORY / '.tools')
        row = os.fstat(tools)
        if ((row.st_dev, row.st_ino) != TOOLS_PIN or row.st_uid != UID
                or stat.S_IMODE(row.st_mode) != 0o700):
            raise ValueError('permission_tools_pin_or_privacy')
        self.target = self.dirs.directory(TARGET)
        row = os.fstat(self.target)
        if ((row.st_dev, row.st_ino) != TARGET_PIN or row.st_uid != UID
                or stat.S_IMODE(row.st_mode) != 0o755):
            raise ValueError('permission_target_pin_or_initial_mode')
        self.before = _full(row)
        self.lock_parent = self.dirs.directory(REPOSITORY / '.tools/hf-exploratory-private')
        parent = os.fstat(self.lock_parent)
        if parent.st_uid != UID or stat.S_IMODE(parent.st_mode) != 0o700:
            raise ValueError('permission_lock_parent_not_private')
        self.lock = os.open('profile.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                            dir_fd=self.lock_parent)
        row = os.fstat(self.lock)
        if (not stat.S_ISREG(row.st_mode) or stat.S_IMODE(row.st_mode) != 0o600
                or row.st_uid != UID or row.st_nlink != 1 or row.st_size > MAXIMUM):
            raise ValueError('permission_existing_lock_invalid')
        self.lock_identity = _full(row)
        self.metadata()
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.lock_payload = self._read_lock()
        first, second = self._children(), self._children()
        if first != second:
            raise ValueError('permission_initial_children_unstable')
        self.children = first
        self.metadata()

    def metadata(self, *, after=False):
        if self.closed:
            raise ValueError('permission_proof_closed')
        if after and self.post is None:
            raise ValueError('permission_post_baseline_unavailable')
        self.dirs.guard(after=after)
        expected = self.post if after else self.before
        if self.target is not None and expected is not None:
            if _full(os.fstat(self.target)) != expected:
                raise ValueError('permission_target_metadata_changed')
            parent = self.dirs.records[TARGET.parent][1]
            if _full(os.stat(TARGET.name, dir_fd=parent, follow_symlinks=False)) != expected:
                raise ValueError('permission_target_named_changed')
        if self.lock is not None and self.lock_identity is not None:
            if (_full(os.fstat(self.lock)) != self.lock_identity
                    or _full(os.stat('profile.lock', dir_fd=self.lock_parent,
                                     follow_symlinks=False)) != self.lock_identity):
                raise ValueError('permission_existing_lock_changed')
        if self.children is not None:
            for name, original in self.children:
                if _full(os.stat(name, dir_fd=self.target, follow_symlinks=False)) != original:
                    raise ValueError('permission_known_child_metadata_changed')

    def _read_lock(self, *, after=False):
        self.metadata(after=after)
        payload = os.pread(self.lock, MAXIMUM + 1, 0)
        if len(payload) > MAXIMUM or len(payload) != self.lock_identity[6]:
            raise ValueError('permission_lock_read_bound_or_length')
        self.metadata(after=after)
        return payload

    def _children(self):
        rows = []
        with os.scandir(self.target) as entries:
            for entry in entries:
                name = entry.name
                if (len(rows) >= 256 or not name or len(name.encode('utf-8')) > 128
                        or name in ('.', '..') or '/' in name or '\x00' in name):
                    raise ValueError('permission_children_bound_or_name')
                rows.append((name, _full(os.stat(name, dir_fd=self.target,
                                                follow_symlinks=False))))
        return sorted(rows)

    def observe(self, *, after=False):
        self.metadata(after=after)
        if self._read_lock(after=after) != self.lock_payload:
            raise ValueError('permission_lock_bytes_changed')
        first, second = self._children(), self._children()
        if first != second or first != self.children:
            raise ValueError('permission_children_changed')
        self.metadata(after=after)

    def bind_post(self):
        self.dirs.guard(after=True)
        row = _full(os.fstat(self.target))
        expected_mode = (self.before[2] & ~0o7777) | 0o700
        if row[:8] != (*self.before[:2], expected_mode, *self.before[3:8]):
            raise ValueError('permission_post_target_not_expected')
        self.post = row  # Only validated target mode/ctime; never new ancestry/child baseline.
        self.metadata(after=True)

    def close(self):
        if self.closed:
            return []
        self.closed = True
        errors = []
        if self.lock is not None:
            fd, self.lock = self.lock, None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BaseException as error:
                errors.append(error)
            try:
                _close_fd(fd)
            except BaseException as error:
                errors.append(error)
        errors.extend(self.dirs.close())
        return errors
```

- [x] Repeat Task2 command and whole new module; require actual OK. Independently
  review no-create lock, full stat9 including GID, held/named closure, finite
  enumeration and no child open/traversal. Record actual results; commit exact
  engineering/doc paths using Task1's staging command and message
  `feat: authenticate existing permission lock and child metadata`.

## Task 3: Entry-consumed syscall slot and bounded honest errors

**Files:** Append only the new tool/tests. No actual target syscall.

- [x] Append this real-fixture slot/error test block first.

<!-- permission-tests -->
```python
class AttemptTests(Fixture):
    def test_one_real_fchmod_then_reentry_refuses_without_rollback(self):
        fd = os.open(self.target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        original = os.fchmod
        calls = []
        def change(descriptor, mode):
            calls.append((descriptor, mode))
            return original(descriptor, mode)
        attempt = self.tool._Attempt()
        with patch.object(self.tool.os, 'fchmod', side_effect=change):
            attempt.enter(fd)
            with self.assertRaises(ValueError):
                attempt.enter(fd)
        self.assertEqual(calls, [(fd, 0o700)])
        self.assertEqual(attempt.attempts, 1)
        self.assertTrue(attempt.returned)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)
        self.unchanged_receipts()

    def test_raised_result_after_real_change_stays_consumed_uncertain(self):
        fd = os.open(self.target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        original = os.fchmod
        def lost(descriptor, mode):
            original(descriptor, mode)
            raise OSError('lost syscall result')
        attempt = self.tool._Attempt()
        with patch.object(self.tool.os, 'fchmod', side_effect=lost) as change:
            with self.assertRaises(OSError):
                attempt.enter(fd)
            with self.assertRaises(ValueError):
                attempt.enter(fd)
        self.assertEqual(change.call_count, 1)
        self.assertEqual(attempt.attempts, 1)
        self.assertFalse(attempt.returned)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)

    def test_error_count_and_utf8_bounds_never_discard_failure_into_success(self):
        errors = self.tool._Errors()
        for index in range(17):
            errors.add(OSError('failure ' + str(index)))
        self.assertEqual(len(errors.rows), 16)
        self.assertTrue(errors.overflow)
        long = self.tool._Errors()
        long.add(ValueError('é' * 4097))
        self.assertTrue(long.overflow)
        self.assertLessEqual(len(long.rows[0]['message'].encode('utf-8')), 4096)
        long.add(ValueError('\udcff'))
        self.assertTrue(long.rows)
```

- [x] Run RED, expected missing `_Attempt`/`_Errors`, nonzero:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_recovery_parent_permissions.AttemptTests
```

- [x] Append this complete single-entry implementation.

<!-- permission-tool -->
```python
class _Attempt:
    def __init__(self):
        self.attempts = 0
        self.returned = False

    def enter(self, fd):
        if self.attempts:
            raise ValueError('permission_slot_already_consumed')
        self.attempts = 1
        os.fchmod(fd, 0o700)
        self.returned = True


class _Errors:
    def __init__(self):
        self.rows = []
        self.overflow = False

    def add(self, error):
        if len(self.rows) >= 16:
            self.overflow = True
            return
        def bound(value, maximum):
            data = value.encode('utf-8', errors='backslashreplace')
            if len(data) > maximum:
                self.overflow = True
            return data[:maximum].decode('utf-8', errors='ignore')
        try:
            message = str(error)
        except BaseException:
            message = 'exception message conversion failed'
            self.overflow = True
        self.rows.append({'type': bound(type(error).__name__, 128),
                          'message': bound(message, 4096)})
```

- [x] Repeat Task3 command and whole module; require actual OK and one syscall
  only on fixtures. Spec/quality review, record results, exact-path commit:
  `feat: consume permission syscall slot before entry`.

## Task 4: Complete closure, truthful outcomes and strict non-action CLI

**Files:** Append new tool/tests only. Read existing bounded
`src/kil/hf_exploratory_native.py:125` check_source; do not edit protected code.

- [x] Append these orchestration/fault/argument tests before `_run`/`main`.

<!-- permission-tests -->
```python
class ProcedureTests(Fixture):
    def run_fixture(self, *, source=None, account=None):
        with patch.object(self.tool, '_source', side_effect=source), \
             patch.object(self.tool, '_account', side_effect=account):
            return self.tool._run(SOURCE, APPROVAL)

    def assert_refused(self, result):
        self.assertEqual(result['outcome'], 'preflight_refused')
        self.assertEqual(result['fchmod_attempts'], 0)
        self.assertFalse(result['preservation'])
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o755)

    def test_confirmed_only_after_real_change_observation_and_teardown(self):
        inode = self.target.stat().st_ino
        original_close = self.tool._close_fd
        closed = []
        def close(fd):
            original_close(fd)
            closed.append(fd)
        with patch.object(self.tool, '_close_fd', side_effect=close):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'mode_change_confirmed')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'returned')
        self.assertEqual(result['observed_pre_mode'], '0755')
        self.assertEqual(result['observed_post_mode'], '0700')
        self.assertTrue(result['preservation'])
        self.assertTrue(all(result['preservation_checks'].values()))
        self.assertEqual(self.target.stat().st_ino, inode)
        self.assertEqual(result['execution_approval'], APPROVAL)
        self.assertEqual(result['reviewed_source'], SOURCE)
        self.assertTrue(closed)
        for fd in closed:
            with self.assertRaises(OSError):
                os.fstat(fd)
        self.unchanged_receipts()

    def test_source_and_account_refusals_and_late_source_drift_make_zero_calls(self):
        for category, fail_at in (('source', 1), ('account', 1), ('source', 3), ('account', 3)):
            with self.subTest(category=category, fail_at=fail_at):
                calls = 0
                def reject(*args):
                    nonlocal calls
                    calls += 1
                    if calls == fail_at:
                        raise ValueError(category + ' changed')
                with patch.object(self.tool.os, 'fchmod', wraps=os.fchmod) as change:
                    result = self.run_fixture(**{category: reject})
                self.assert_refused(result)
                self.assertEqual(change.call_count, 0)

    def test_final_metadata_after_source_io_refuses_replacement_before_syscall(self):
        count = 0
        def source(*args):
            nonlocal count
            count += 1
            if count == 3:
                self.target.rename(self.tools / 'old-target')
                self.target.mkdir(mode=0o755)
                self.target.chmod(0o755)
        with patch.object(self.tool.os, 'fchmod', wraps=os.fchmod) as change:
            result = self.run_fixture(source=source)
        self.assert_refused(result)
        self.assertEqual(change.call_count, 0)

    def test_raised_fchmod_is_uncertain_with_actual_observed_mode_and_no_retry(self):
        original = os.fchmod
        def lost(fd, mode):
            original(fd, mode)
            raise OSError('fchmod result unavailable')
        with patch.object(self.tool.os, 'fchmod', side_effect=lost) as change:
            result = self.run_fixture()
        self.assertEqual(change.call_count, 1)
        self.assertEqual(result['outcome'], 'mutation_uncertain')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'uncertain')
        self.assertEqual(result['observed_post_mode'], '0700')
        self.assertFalse(result['preservation'])
        self.unchanged_receipts()

    def test_returned_call_then_fsync_failure_is_inconclusive_not_zero(self):
        with patch.object(self.tool.os, 'fsync', side_effect=OSError('fsync failed')):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'postverification_inconclusive')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'returned')
        self.assertEqual(result['observed_post_mode'], '0700')
        self.assertFalse(result['preservation'])

    def test_post_observation_and_final_closure_failures_keep_one_attempt(self):
        for method in ('observe', 'metadata'):
            with self.subTest(method=method):
                self.target.chmod(0o755)  # Fixture reset between distinct test attempts only.
                original = getattr(self.tool._Proof, method)
                def fail(proof, *, after=False):
                    original(proof, after=after)
                    if after:
                        raise ValueError('post ' + method + ' failed')
                with patch.object(self.tool._Proof, method, fail):
                    result = self.run_fixture()
                self.assertEqual(result['outcome'], 'postverification_inconclusive')
                self.assertEqual(result['fchmod_attempts'], 1)
                self.assertEqual(result['observed_post_mode'], '0700')
                self.assertFalse(result['preservation'])

    def test_late_teardown_errors_preserve_original_error_and_close_every_fd(self):
        original_close = self.tool._close_fd
        closed = []
        def close(fd):
            original_close(fd)
            closed.append(fd)
            raise OSError('late close after actual release')
        # Keep original callable outside the patched os module, not a production attribute.
        original_change = os.fchmod
        def change(fd, mode):
            original_change(fd, mode)
            raise ValueError('original lost result')
        with patch.object(self.tool, '_close_fd', side_effect=close), \
             patch.object(self.tool.os, 'fchmod', side_effect=change):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'mutation_uncertain')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['observed_post_mode'], '0700')
        self.assertEqual(result['errors'][0]['message'], 'original lost result')
        self.assertTrue(any('late close' in row['message'] for row in result['errors']))
        for fd in closed:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_post_source_drift_keeps_returned_attempt_and_mode(self):
        count = 0
        def source(*args):
            nonlocal count
            count += 1
            if count == 4:
                raise ValueError('post source changed')
        result = self.run_fixture(source=source)
        self.assertEqual(result['outcome'], 'postverification_inconclusive')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'returned')
        self.assertEqual(result['observed_post_mode'], '0700')

    def test_syscall_to_postcheck_child_drift_refuses_confirmation(self):
        original_change = os.fchmod
        def change(fd, mode):
            original_change(fd, mode)
            self.receipt.chmod(0o755)
        with patch.object(self.tool.os, 'fchmod', side_effect=change):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'postverification_inconclusive')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertFalse(result['preservation'])

    def test_procedure_does_not_create_write_delete_rename_or_run_native(self):
        import subprocess
        def forbidden(*args, **kwargs):
            raise AssertionError('out-of-scope operation')
        with ExitStack() as stack:
            for name in ('mkdir', 'write', 'unlink', 'rename', 'chmod', 'chown'):
                stack.enter_context(patch.object(self.tool.os, name, side_effect=forbidden))
            stack.enter_context(patch.object(subprocess, 'Popen', side_effect=forbidden))
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'mode_change_confirmed')
        self.unchanged_receipts()


class CLITests(unittest.TestCase):
    def test_import_has_no_target_or_source_access(self):
        # Loader reads the code normally; module execution must not touch actual target.
        module = load_tool()
        with patch.object(module.os, 'open', side_effect=AssertionError('real access')), \
             patch.object(module.os, 'stat', side_effect=AssertionError('real access')):
            spec = importlib.util.spec_from_file_location('hf_permission_import_only', TOOL)
            fresh = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fresh)

    def test_invalid_cli_rejects_before_any_source_account_or_target_access(self):
        tool = load_tool()
        valid = ['--reviewed-source', SOURCE, '--execution-approval', APPROVAL,
                 '--execute-approved-mode-change']
        cases = [[], valid[:-1], ['--reviewed', SOURCE],
                 [*valid, '--target', '/private/tmp/other'],
                 ['--reviewed-source', 'HEAD', *valid[2:]],
                 ['--reviewed-source', SOURCE, '--execution-approval', ' ', valid[-1]],
                 ['--reviewed-source', SOURCE, '--execution-approval', 'x' * 4097, valid[-1]],
                 ['--reviewed-source', SOURCE, '--execution-approval', '\udcff', valid[-1]]]
        for argv in cases:
            with self.subTest(argv=repr(argv)), redirect_stderr(io.StringIO()), \
                 patch.object(tool, '_source', side_effect=AssertionError('source access')), \
                 patch.object(tool, '_account', side_effect=AssertionError('account access')), \
                 patch.object(tool.os, 'open', side_effect=AssertionError('target access')):
                with self.assertRaises(SystemExit) as raised:
                    tool.main(argv)
                self.assertEqual(raised.exception.code, 2)

    def test_cli_exit_codes_canonical_bound_and_attempt_history(self):
        tool = load_tool()
        argv = ['--reviewed-source', SOURCE, '--execution-approval', APPROVAL,
                '--execute-approved-mode-change']
        for outcome, expected in [('mode_change_confirmed', 0), ('preflight_refused', 1),
                                  ('mutation_uncertain', 1), ('postverification_inconclusive', 1)]:
            document = {'outcome': outcome, 'fchmod_attempts': 0 if expected and outcome == 'preflight_refused' else 1}
            output = io.StringIO()
            with patch.object(tool, '_run', return_value=document), redirect_stdout(output):
                code = tool.main(argv)
            self.assertEqual(code, expected)
            raw = output.getvalue().encode('utf-8')
            self.assertEqual(raw, tool._canonical(document))
            self.assertLessEqual(len(raw), tool.MAXIMUM)
            self.assertEqual(json.loads(raw)['fchmod_attempts'], document['fchmod_attempts'])
```

- [x] Run RED (expected missing `_run`/`main`, nonzero):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_recovery_parent_permissions.ProcedureTests tests.test_hf_recovery_parent_permissions.CLITests
```

- [x] Append complete orchestration and CLI. This is the last tool block.

<!-- permission-tool -->
```python
def _source(reviewed_source):
    location = str(REPOSITORY / 'src')
    if location not in sys.path:
        sys.path.insert(0, location)
    from kil.hf_exploratory_native import check_source
    check_source(REPOSITORY, reviewed_source)


def _account():
    if (os.getuid() != UID or os.geteuid() != UID
            or Path(pwd.getpwuid(os.getuid()).pw_dir) != HOME):
        raise ValueError('permission_actual_account_changed')


def _run(reviewed_source, execution_approval):
    proof, attempt, errors = _Proof(), _Attempt(), _Errors()
    observed_post = None
    checks = {key: False for key in ('target', 'ancestors', 'children', 'lock',
                                    'source', 'account', 'teardown')}
    try:
        _source(reviewed_source)
        _account()
        proof.bind()
        _source(reviewed_source)
        _account()
        proof.observe()
        # The last Git/account IO precedes metadata-only closure and fchmod.
        _source(reviewed_source)
        _account()
        proof.metadata()
        attempt.enter(proof.target)
        observed_post = _full(os.fstat(proof.target))
        os.fsync(proof.target)
        proof.bind_post()
        proof.observe(after=True)
        _source(reviewed_source)
        _account()
        proof.metadata(after=True)
        for key in checks:
            if key != 'teardown':
                checks[key] = True
    except BaseException as error:
        errors.add(error)
        if attempt.attempts and proof.target is not None:
            try:
                observed_post = _full(os.fstat(proof.target))
            except BaseException as observation_error:
                errors.add(observation_error)
    finally:
        for error in proof.close():
            errors.add(error)
    checks['teardown'] = not errors.rows and not errors.overflow
    if not attempt.attempts:
        outcome = 'preflight_refused'
    elif not attempt.returned:
        outcome = 'mutation_uncertain'
    elif errors.rows or errors.overflow or not all(checks.values()):
        outcome = 'postverification_inconclusive'
    else:
        outcome = 'mode_change_confirmed'
    def mode(row):
        return None if row is None else format(stat.S_IMODE(row[2]), '04o')
    return {
        'outcome': outcome, 'reviewed_source': reviewed_source,
        'execution_approval': execution_approval,
        'target': str(TARGET), 'target_pin': TARGET_PIN, 'tools_pin': TOOLS_PIN,
        'fchmod_attempts': attempt.attempts,
        'syscall_certainty': ('not_entered' if not attempt.attempts
                              else 'returned' if attempt.returned else 'uncertain'),
        'observed_pre_mode': mode(proof.before), 'observed_post_mode': mode(observed_post),
        'target_pre_stat9': proof.before, 'target_post_observed_stat9': observed_post,
        'target_post_verified_stat9': proof.post,
        'direct_children_count': None if proof.children is None else len(proof.children),
        'direct_children_sha256': None if proof.children is None else sha256(_canonical(proof.children)).hexdigest(),
        'lock_stat9': proof.lock_identity,
        'lock_sha256': None if proof.lock_payload is None else sha256(proof.lock_payload).hexdigest(),
        'preservation': outcome == 'mode_change_confirmed', 'preservation_checks': checks,
        'errors': errors.rows, 'error_overflow': errors.overflow,
        'preservation_scope': 'own_no_receipt_writes_and_direct_child_metadata_not_descendant_content',
    }


def _source_argument(value):
    if re.fullmatch(r'[0-9a-f]{40}', value) is None:
        raise argparse.ArgumentTypeError('reviewed source must be exact40-hex')
    return value


def _approval_argument(value):
    try:
        valid = bool(value.strip()) and len(value.encode('utf-8')) <= 4096
    except UnicodeError:
        valid = False
    if not valid:
        raise argparse.ArgumentTypeError('actual approval must be nonblank validUTF-8 <=4096 bytes')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--reviewed-source', required=True, type=_source_argument)
    parser.add_argument('--execution-approval', required=True, type=_approval_argument)
    parser.add_argument('--execute-approved-mode-change', required=True, action='store_true')
    args = parser.parse_args(argv)
    result = _run(args.reviewed_source, args.execution_approval)
    raw = _canonical(result)
    if len(raw) > MAXIMUM:
        # This cannot fit with the fixed schema/bounds; never fabricate a startup result.
        raise ValueError('permission_result_exceeds_bound_after_attempt')
    print(raw.decode('utf-8'), end='')
    return 0 if result['outcome'] == 'mode_change_confirmed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
```

- [x] Repeat Task4 command and whole module; require actual OK. Use
  systematic-debugging for any unexpected failure, not a speculative change.
  Independent reviews must check the outer finally preserves prior errors/count,
  every owned close is attempted, no child receipt bytes are touched, and final
  content/enumeration IO is followed by source/account and metadata-only closure.
  Record actual RED/GREEN evidence and exact-path commit:
  `feat: report one-shot permission outcomes after complete closure`.

## Task 5: Adversarial coverage, independent whole review and root verification

**Files:** Append these concrete tests to the new test file only; existing
implementation is exercised without adding another mutation/recovery feature.
If one fails, preserve RED and implement the minimum scoped regression fix before
repeating GREEN. Read all approved spec requirements and final actual tool.

- [ ] Append the missing-state/type/bounds/late-IO and teardown regressions.

<!-- permission-tests -->
```python
class AdversarialTests(Fixture):
    def run_fixture(self):
        with patch.object(self.tool, '_source'), patch.object(self.tool, '_account'):
            return self.tool._run(SOURCE, APPROVAL)

    def test_missing_target_and_regular_file_or_symlink_are_not_created_or_followed(self):
        self.target.rename(self.tools / 'retained-original')
        for kind in ('missing', 'file', 'symlink'):
            with self.subTest(kind=kind):
                if kind == 'file':
                    self.target.write_bytes(b'not a directory')
                elif kind == 'symlink':
                    self.target.symlink_to(self.tools / 'retained-original', target_is_directory=True)
                result = self.run_fixture()
                self.assertEqual(result['outcome'], 'preflight_refused')
                self.assertEqual(result['fchmod_attempts'], 0)
                if kind == 'missing':
                    self.assertFalse(self.target.exists())
                else:
                    self.target.unlink()

    def test_missing_lock_parent_is_not_created(self):
        self.lock.unlink()
        self.lock_parent.rmdir()
        result = self.run_fixture()
        self.assertEqual(result['fchmod_attempts'], 0)
        self.assertFalse(self.lock_parent.exists())

    def test_lock_symlink_hardlink_wrong_mode_and_size_refuse(self):
        for kind in ('symlink', 'hardlink', 'mode', 'size'):
            with self.subTest(kind=kind):
                self.lock.unlink(missing_ok=True)
                self.lock.write_bytes(b'cooperating fixture lock\n')
                self.lock.chmod(0o600)
                other = self.lock_parent / 'other'
                other.unlink(missing_ok=True)
                if kind == 'symlink':
                    self.lock.rename(other)
                    self.lock.symlink_to(other)
                elif kind == 'hardlink':
                    os.link(self.lock, other)
                elif kind == 'mode':
                    self.lock.chmod(0o644)
                else:
                    self.lock.write_bytes(b'x' * (self.tool.MAXIMUM + 1))
                result = self.run_fixture()
                self.assertEqual(result['outcome'], 'preflight_refused')
                self.assertEqual(result['fchmod_attempts'], 0)

    def test_final_metadata_detects_lock_replacement_after_last_content_read(self):
        original = self.tool._Proof._read_lock
        reads = 0
        def read(proof, *, after=False):
            nonlocal reads
            value = original(proof, after=after)
            reads += 1
            if reads == 2:
                self.lock.rename(self.lock_parent / 'old')
                self.lock.write_bytes(b'cooperating fixture lock\n')
                self.lock.chmod(0o600)
            return value
        with patch.object(self.tool._Proof, '_read_lock', read):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'preflight_refused')
        self.assertEqual(result['fchmod_attempts'], 0)

    def test_initial_roster_instability_and_enumeration_exception_refuse(self):
        original = self.tool._Proof._children
        calls = 0
        def unstable(proof):
            nonlocal calls
            value = original(proof)
            calls += 1
            if calls == 1:
                (self.target / 'new-child').mkdir(mode=0o700)
            return value
        with patch.object(self.tool._Proof, '_children', unstable):
            result = self.run_fixture()
        self.assertEqual(result['fchmod_attempts'], 0)
        with patch.object(self.tool.os, 'scandir', side_effect=OSError('enumeration failed')):
            result = self.run_fixture()
        self.assertEqual(result['fchmod_attempts'], 0)

    def test_final_post_source_io_cannot_replace_target_and_claim_confirmation(self):
        calls = 0
        def source(*args):
            nonlocal calls
            calls += 1
            if calls == 4:
                self.target.rename(self.tools / 'changed-after-post')
                self.target.mkdir(mode=0o700)
        with patch.object(self.tool, '_source', side_effect=source), \
             patch.object(self.tool, '_account'):
            result = self.tool._run(SOURCE, APPROVAL)
        self.assertEqual(result['outcome'], 'postverification_inconclusive')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'returned')
        self.assertEqual(result['observed_post_mode'], '0700')

    def test_teardown_only_failure_after_otherwise_complete_postcheck_is_not_confirmed(self):
        original = self.tool._close_fd
        descriptors = []
        def close(fd):
            original(fd)
            descriptors.append(fd)
            raise ValueError('late release proof error')
        with patch.object(self.tool, '_close_fd', side_effect=close):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'postverification_inconclusive')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'returned')
        self.assertEqual(result['observed_post_mode'], '0700')
        self.assertFalse(result['preservation'])
        self.assertFalse(result['preservation_checks']['teardown'])
        for fd in descriptors:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_syscall_exception_before_change_reports_one_uncertain_0755(self):
        with patch.object(self.tool.os, 'fchmod', side_effect=OSError('syscall refused')) as change:
            result = self.run_fixture()
        self.assertEqual(change.call_count, 1)
        self.assertEqual(result['outcome'], 'mutation_uncertain')
        self.assertEqual(result['fchmod_attempts'], 1)
        self.assertEqual(result['syscall_certainty'], 'uncertain')
        self.assertEqual(result['observed_post_mode'], '0755')
        self.unchanged_receipts()

    def test_known_child_drift_during_last_source_io_refuses_pre_and_post_acceptance(self):
        for fail_at in (3, 4):
            with self.subTest(fail_at=fail_at):
                self.target.chmod(0o755)
                self.receipt.chmod(0o700)
                calls = 0
                def source(*args):
                    nonlocal calls
                    calls += 1
                    if calls == fail_at:
                        self.receipt.chmod(0o755)
                with patch.object(self.tool, '_source', side_effect=source), \
                     patch.object(self.tool, '_account'):
                    result = self.tool._run(SOURCE, APPROVAL)
                self.assertEqual(result['outcome'], 'preflight_refused' if fail_at == 3
                                 else 'postverification_inconclusive')
                self.assertEqual(result['fchmod_attempts'], 0 if fail_at == 3 else 1)
                self.assertFalse(result['preservation'])

    def test_equal_roster_allows_symlink_metadata_without_reading_its_target(self):
        outside = self.root / 'outside-payload'
        outside.write_bytes(b'not a receipt and must not be read')
        (self.target / 'pointer').symlink_to(outside)
        original_open = os.open
        opened = []
        def open_only_owned_anchors(path, flags, *args, **kwargs):
            opened.append(os.fspath(path))
            self.assertFalse(flags & (os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_RDWR))
            self.assertNotIn(os.fspath(path), ('pointer', str(outside)))
            return original_open(path, flags, *args, **kwargs)
        with patch.object(self.tool.os, 'open', side_effect=open_only_owned_anchors):
            result = self.run_fixture()
        self.assertEqual(result['outcome'], 'mode_change_confirmed')
        self.assertTrue(opened)
        self.assertEqual(outside.read_bytes(), b'not a receipt and must not be read')

    def test_multibyte_child_name_byte_bound_and_lock_maximum(self):
        (self.target / ('é' * 65)).mkdir(mode=0o700)
        result = self.run_fixture()
        self.assertEqual(result['fchmod_attempts'], 0)
        (self.target / ('é' * 65)).rmdir()
        self.lock.write_bytes(b'x' * self.tool.MAXIMUM)
        result = self.run_fixture()
        self.assertEqual(result['outcome'], 'mode_change_confirmed')

    def test_account_helper_rejects_real_effective_and_passwd_home_mismatch(self):
        from types import SimpleNamespace
        for real, effective, home in [(self.tool.UID + 1, self.tool.UID, '/Users/mistorm'),
                                      (self.tool.UID, self.tool.UID + 1, '/Users/mistorm'),
                                      (self.tool.UID, self.tool.UID, '/private/tmp/not-home')]:
            with self.subTest(real=real, effective=effective, home=home), \
                 patch.object(self.tool.os, 'getuid', return_value=real), \
                 patch.object(self.tool.os, 'geteuid', return_value=effective), \
                 patch.object(self.tool.pwd, 'getpwuid', return_value=SimpleNamespace(pw_dir=home)):
                with self.assertRaises(ValueError):
                    self.tool._account()

    def test_no_content_or_enumeration_between_final_metadata_and_fchmod(self):
        original_metadata = self.tool._Proof.metadata
        original_change = os.fchmod
        original_pread, original_scandir = os.pread, os.scandir
        source_calls, events = 0, []
        def source(*args):
            nonlocal source_calls
            source_calls += 1
            events.append('source')
        def metadata(proof, *, after=False):
            original_metadata(proof, after=after)
            events.append('metadata_after' if after else 'metadata_before')
        def pread(*args):
            events.append('content')
            return original_pread(*args)
        def scandir(*args):
            events.append('enumeration')
            return original_scandir(*args)
        def change(fd, mode):
            self.assertEqual(source_calls, 3)
            self.assertEqual(events[-1], 'metadata_before')
            events.append('syscall')
            return original_change(fd, mode)
        with patch.object(self.tool, '_source', side_effect=source), \
             patch.object(self.tool, '_account'), \
             patch.object(self.tool._Proof, 'metadata', metadata), \
             patch.object(self.tool.os, 'pread', side_effect=pread), \
             patch.object(self.tool.os, 'scandir', side_effect=scandir), \
             patch.object(self.tool.os, 'fchmod', side_effect=change):
            result = self.tool._run(SOURCE, APPROVAL)
        self.assertEqual(result['outcome'], 'mode_change_confirmed')
        self.assertEqual(source_calls, 4)
        self.assertEqual(events[-2:], ['source', 'metadata_after'])
```

- [ ] Run the whole new module (require actual OK, record count/duration):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_recovery_parent_permissions
```

- [ ] Freeze actual tool/test bytes and independently review the complete scope:
  spec reviewer maps each requirement below to actual code/tests; quality reviewer
  examines full FD lifecycle, late failures, once history, guards, bounds and
  negative authority. Root independently runs the new module plus baseline:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_recovery_parent_permissions tests.test_hf_exploratory_io tests.test_v3b2_profile_state tests.test_hf_compact_residual_recovery tests.test_hf_exploratory_native
```

- [ ] Check exact protected source scope against8b57143 (must produce no paths):

```sh
git diff --name-only 8b5714377cce4e3dffdf5ce6aaec926a5247099a -- src deploy artifacts tools/hf_compact_residual_recovery.py tests/test_hf_compact_residual_recovery.py tools/hf_exploratory_kind.py .gitattributes
```

- [ ] Verify the full8b57143 lineage prefix is preserved, then each subsequent
  task's complete predecessor prefix. The planning predecessor is1,416,871B:

```sh
git show 8b5714377cce4e3dffdf5ce6aaec926a5247099a:docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md | cmp -n 1416871 - docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md
```

- [ ] Regenerate/check tracked readers; a newly created Markdown source must be
  staged by exact path first, because discovery is tracked-source-only:

```sh
PYTHONDONTWRITEBYTECODE=1 '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' tools/render_markdown.py
PYTHONDONTWRITEBYTECODE=1 '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' tools/render_markdown.py --check
git diff --check
git diff --cached --check
```

Record actual reader count; verify new/changed docs contain the canonical
`https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff` citation. Do not
change renderer/citation selectors or audit/repair old receipts.

- [ ] Finish exact-path scoped local commit and verify clean HEAD/status:

```sh
git add -- tools/hf_recovery_parent_permissions.py tests/test_hf_recovery_parent_permissions.py docs/superpowers/plans/2026-09-17-hf-recovery-parent-permissions.md docs/superpowers/plans/2026-09-17-hf-recovery-parent-permissions.htm docs/superpowers/specs/2026-09-17-hf-recovery-parent-permissions-design.md docs/superpowers/specs/2026-09-17-hf-recovery-parent-permissions-design.htm docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm
git commit -m 'test: verify fixed permission preparation and approval boundaries'
git status --porcelain=v1
git log -1 --format='%H %s'
```

No claim of full discovery green; no HF/VM readiness inference from fixtures.

## Spec coverage and plan self-review

- Fixed sole target/pins,0700 .tools/private lock parent, UID/type/mode refusal:
  Tasks1/2/5; no directory creation on missing state.
- No-follow root-to-name held ancestry and target stat9/GID/nanoseconds:
  Tasks1/2; final target mode-only expectation never rebaselines other anchors.
- Existing regular single-link0600 lock, no O_CREAT, bounded bytes and real
  nonblocking cooperating flock: Tasks2/5; no LabLock create-capable entry.
- Equal bounded direct child observations,256/257,128UTF-8 bytes, no children
  opened/followed/traversed: Tasks2/5. Direct metadata, not content attestation.
- Clean exact reviewed HEAD/account before lock and repeated after final
  observation IO; metadata-only closure before syscall and after post IO:
  Task4/5; source helper rejects warnings/stderr/nonzero, not filtered.
- One entered fchmod, fsync, expected mode/ctime versus stable other fields,
  no retry/rollback and original history through late cleanup: Tasks3/4/5.
- Four distinct outcomes, entry count/certainty/observed modes/pins/approval,
  preservation statuses, bounded16 errors/128-byte type/4096-byte message and
  canonical≤1MiB stdout: Tasks3/4; no private receipt/seal/file writes.
- Strict required CLI/invalid UTF-8/import non-action, exit2/1/0: Task4.
- Payload/seal/childmode preservation, owned FD cleanup and no native call:
  Tasks1–5. Fixtures are not arbitrary external write exclusion/atomicity.
- Independent task/whole spec+quality review, actual root regression results,
  exact protected scope/append-only lineage/readers/clean commit: Tasks1–5.
- Fresh permission and separate recovery approvals: next section. No Ollama,
  rehearsal, HF, image provenance/compatibility audit or lifecycle operation.

Self-review must additionally compile the concatenated tool/test examples
without executing them, scan for incomplete instructions and cross-check every
private method/property/type against these definitions. This is planning
verification, not a substitute for later genuine RED/GREEN runs/reviews.

## Execution handoff and live gates — do not execute now

The user previously chose subagent-driven preparation with independent reviews;
carry that preference forward. Writing-plans offers subagent-driven or inline
execution; no need to ask the same choice again. Hand off this plan for the
requested task-by-task workflow. No new permission/recovery authority follows.

After fixture engineering, independent reviews, root verification and a clean
exact committed HEAD, root presents actual evidence and asks **one explicit
fixed-parent0755→0700 mode-change attempt** approval. This planning approval and
fixture APPROVAL text cannot supply that execution approval. Only root may
execute the live procedure; never dispatch it to a reviewer/implementer.

Build and display the exact argv from the actual reviewed clean HEAD and actual
new user approval with this defined runbook function (not added to the tool):

```python
import re
import shlex


def approved_permission_command(verified_clean_head, actual_user_approval):
    if re.fullmatch(r'[0-9a-f]{40}', verified_clean_head) is None:
        raise ValueError('actual verified exact HEAD required')
    if not actual_user_approval.strip() or len(actual_user_approval.encode('utf-8')) > 4096:
        raise ValueError('actual new execution approval required')
    argv = ['/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python',
            '-W', 'error::ResourceWarning', 'tools/hf_recovery_parent_permissions.py',
            '--reviewed-source', verified_clean_head,
            '--execution-approval', actual_user_approval,
            '--execute-approved-mode-change']
    return 'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ' + shlex.join(argv)
```

Record the actual displayed command before dispatch; do not invent a future
commit or approval now. Use repository cwd and scoped outside-sandbox approval
route only if needed for the sole authorized fchmod. Capture actual exit/stdout
boundedly, append factual lineage/plan and regenerate readers **after** the
procedure ends. No new receipt/date directory/alternate suffix/export overwrite.
Any refusal/uncertainty/postcheck failure ends that one permission; no retry,
rollback to0755, directory substitution, repair/rebaseline or recovery call.

Even confirmed mode-only change does not update VM status or prove recovery/HF
readiness. A later VM recovery needs a **NEW separately approved one-stop
attempt**, with its own accepted preflight and live gate. The original T430
preflight refusal spent its permission despite Stop0 and absent intent.
HF testing retains separate compatibility, request-free rehearsal and live
action gates. Accepted local Envoy stays unchanged; platform-image provenance
unverified, full Kind/Calico acceptance false. No broad provenance audit is
required or authorized by this mode-only preparation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

## Engineering execution record — 2026-09-17

At clean committed plan checkpoint817c47fba7bfb16751e34311fe788bf51d50f497,
root's prescribed baseline completed:309 tests/134.159s, exit0/OK, bytecode
disabled and ResourceWarning fatal. Scope: new preparation baseline's existing
IO, profile-state and accepted compact-recovery fixture modules. Accepted
recovery tool SHA2562b58ab2392543611f64044f5d2624f07edfa03ed4c988e1bff2c03d137ccf864
and tests SHA256a4ee14ce13dd569bc1a1202ffab3be450fed8bbae954be96b98600caeccaf64f
unchanged. Root sent BASELINE GO to fresh Task1 implementer only afterward.
No actual private-target/lock/receipt/runtime observation or native action.
Task1 implementation/review/verification results are pending at this record.

Task1 subsequently completed by fresh permission_task1_impl with genuine initial
RED3 missing-tool failures, then GREEN3. Independent permission_task1_spec found
the proposed after=True guard admitted unapproved initial modes; root reproduced
RED1/0.020s. Minimal captured0755 requirement plus negative0705/0777/0700 and
positive0755→0700 tests produced GREEN5. Root whole5/0.033s and independent SPEC
rereview5/0.034s passed. Independent permission_task1_quality passed5/0.055s and
real-owned-temp close-error/partial-walk/reused-ancestor/canonical-output probes,
no Critical/Important issues. Final root run and exact doc checkpoint follow.
Proposed plan examples updated with the faithful guard/test correction and
compile without execution: tool360 lines, tests722 lines/41 methods.
Only read-only ancestry is implemented; existing lock/proof/syscall/CLI tasks
remain pending. No live target/VM state change or permission attempt consumed.

Quality's minor test-hygiene note is addressed by registering first-test
dirs.close before assertions as well as its explicit release checks. Root's
fresh post-review whole module5/0.055s passed before this test-only adjustment;
repeat verification/review of that adjustment precedes the actual checkpoint.

Final Task1 root verification5/0.032s OK; quality exact-delta rereview5/0.053s
PASS, minor closed. ToolSHA256b2911e161a5d501d94c2a4191d5a4e1e766fde9d1785f013babe646aa3096594;
testSHA256fedf1e824e0fea7cd49efc0705217ff004eb9d4d34e1bf910b581d9beb9967aa.
Updated plan examples syntax-check only: tool360 lines/tests723 lines/41 methods.
Task1 engineering acceptance confirmed; fresh Task2 follows the scoped checkpoint.

Task2 fresh permission_task2_impl reported genuine missing_Proof RED7 before
adding its read-only lock/child proof; focused7/whole12 GREEN. Root whole12/0.200s
OK. Independent SPEC12/0.178s plus4 owned-temp probes/0.255s found masked bound
tests, not a code defect: late target metadata drift prevented enumeration.
Root tightened exact bound-error expectations and reproduced RED1/0.114s.
Minimal TEST-ONLY correction uses independent initial binds for257 and129B
rosters after the256-positive proof is closed. Root12/0.189s and SPEC12/0.357s
PASS. Target/lock/child commitments remain original, no receipt traversal.

Independent QUALITY found missing-post-baseline state accepted by metadata/
observe(after=True). Root corrected an unrelated selector typo, then reproduced
genuine RED1test/2subfailures/0.009s. Minimal implementation guard refuses after
checks until a validated post baseline exists. Added negative premature-post
and positive real-owned-FD0755→0700 binding coverage. Root14/0.190s, SPEC14/0.161s
and QUALITY14/0.170s PASS; original altered-mtime reproducer now refuses without
capturing a baseline. No remaining Critical/Important review findings.
Current toolSHA25643e1e0490f2f4cbd7a1f0797a97e5176cad09b6f43e0b6c4054dbdecb2a5ac76;
testsSHA25631da0753d31d6737757bc3aaa3937dba198aec7ea66666d845a5a415ea62542d.
Plan examples compile only:362 tool lines/756 test lines/43 methods. Final root
verification and scoped checkpoint follow. Syscall/orchestration/CLI tasks remain
pending; no actual private-target/VM observation or permission attempt consumed.

Final Task2 root whole14/0.196s OK and actual tool/test hashes match the reviewed
values above; Task2 engineering acceptance confirmed. Scoped checkpoint/readers
precede fresh Task3. Live permission and recovery remain separately unapproved.

Task3 fresh permission_task3_impl completed intended missing_Attempt/_Errors
RED3/0.022s before code, focusedGREEN3/0.024s and whole17/0.208s. Root read actual
diff and ran17/0.237s OK. Independent SPEC17/0.330s plus3 error-boundary probes/
0.005s PASS; QUALITY17/0.245s plus realfailedsyscall/refusedretry, UTF8/surrogate/
failedexceptionconversion/exact16-boundary probes PASS. No review findings.
Actual toolSHA2564066b3694062c1fef8ba9427e56e47f6037e760a1b9f1da571e9227546dc4a4b;
testsSHA256c807d84b718522a3c3c884ec83d18a62812b0980aa3b02c1cc84d63984b0fc32.
Slot consumed before fixed700 fchmod, known returned versus uncertain result
remain distinct from observed mode; no reentry/rollback. Error bounds retain
failure/overflow rather than claiming clean. Prior proof guards untouched.
Final root whole17/0.397s OK, ResourceWarning fatal. Only owned temporary fixtures
received syscalls; actual target/VM unobserved. Readers/scoped checkpoint precede
Task4 orchestration; no actual permission/recovery authority granted.

Task4 fresh permission_task4_impl completed genuine focused absence RED13/0.213s,
24 errors/exit1 before source/account/run/main implementation. Root caught an
in-progress test expectation that classified check4 as preflight; test injection
was restricted to approved prechecks1/3 before implementation, without changing
the four-check ordering. Invalid HEAD and uppercase source cases are both covered.
FocusedGREEN13/0.139s and whole30/0.283s; root read actual diff/code and ran
30/0.304s OK. Source delegates to the existing bounded exact-local-clean-HEAD
validator; no remote synchronization or provenance assertion.

Independent SPEC30/0.348s plus2 owned-fixture probes/0.023s PASS; QUALITY30/0.317s
and final-account/late-close/final-child-drift probes PASS. No review findings.
Final root30/0.453s OK, ResourceWarning fatal. Actual toolSHA256
8ba9dd1d4cb277878d4f778c36232e2d96863643187a13b6ae29962c7cfb2489;
testsSHA25649b97cc883eb8571bf48b1319c18996e88bea00548e1877b124870e4e18c26c2.
All source/account/content/enumeration IO precedes final metadata-only closure;
one-entry uncertainty and returned-call/postcheck failure remain distinct.
Confirmed outcome is produced only after all owned teardown; canonical bounded
stdout reports actual attempt/observed-mode/proof scope, never new private evidence.
Complete8f91b5a predecessor lineage prefix1,435,193B and protected scope verified.
Readers/scoped checkpoint precede Task5 adversarial tests and whole verification.
Actual target/lock/receipt/runtime/VM status unobserved, no live permission or
native recovery approval consumed. Task5 engineering remains pending.
