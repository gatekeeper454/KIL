# Compact residual HF VM recovery preparation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare and verify one fixed-target, stop-only manual recovery tool without contacting or changing the live VM during engineering.

**Architecture:** Keep recovery separate from the exploratory lifecycle. Authenticate the one retained receipt and its exact private runtime, prove fresh inventory/ownership, persist one exclusive stop intent, and permit one bounded graceful stop only after separate execution approval. An already-stopped VM receives no stop; uncertainty never retries.

**Tech Stack:** Python3.12/unittest, existing no-follow capture and complete-inventory parsers, LabLock/PrivateStore/capture_process, pinned Colima and accepted Docker tools.

---

## Approval, workspace and file boundary

The user approved the written
`docs/superpowers/specs/2026-09-17-hf-compact-residual-vm-recovery-design.md`.
This confirms planning and test-first engineering only. **No live preflight or
stop is approved.** Current document checkpoint is
77ce6ecaa8dba2191d7a280ad9ff7d9b726c3726.

The repository is already an externally managed detached linked worktree at
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL`.
Keep it: no branch/worktree creation, relocation, installation, merge or push.

Create ONLY `tools/hf_compact_residual_recovery.py` and
`tests/test_hf_compact_residual_recovery.py`. The tool implements this one manual
runbook, not a reusable recovery API. Production Native/Runtime/Profile/IO/CLI,
strict modules, accepted artifacts, citation policy and historical evidence are
read-only. Documentation updates are this plan, the approved spec's appended
approval record, append-only specialist lineage and their generated readers.

Private helpers beginning with `_` below are internal to this fixed tool. There
are no runtime/tool/home/receipt CLI overrides. Tests may replace the private
location/pin constants with real owned temporary fixtures; process acquisition
is the only native seam. Never patch a filesystem guard or treat mocked native
results as evidence about the real VM.

All implementation code blocks below concatenate, in order, into the one tool.
Test blocks concatenate into the one test file. Do not create the implementation
until the corresponding failing behavior tests have run against its absence or
previous behavior. Complete final-file code is divided by responsibility rather
than creating unrelated modules.

## Common test command and baseline

Use the existing interpreter; do not install dependencies:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_exploratory_runtime tests.test_hf_exploratory_profile tests.test_hf_exploratory_io tests.test_hf_exploratory_evidence tests.test_hf_exploratory_native tests.test_v3b2_profile_state tests.test_v3b2_colima_inventory
```

Require actual OK/no errors/failures before changes; record the observed count.
These are fixture tests, not live inventory. If a previously unknown failure
appears, use systematic-debugging and stop the affected task rather than editing
protected production modules. The broader historical citation failure remains
disclosed: exactly four immutable ignored documents lack canonical citations.

## Task 1: Real file/ancestry proof with a fixed target

**Files:** Create the tool/test paths above. Read, do not edit,
`src/kil/hf_exploratory_runtime.py`, `src/kil/hf_exploratory_inputs.py`,
`src/kil/v3b2_profile_state.py` and the approved spec.

- [ ] Add the following initial real-filesystem tests before the tool exists.

```python
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_tool():
    path = ROOT / 'tools/hf_compact_residual_recovery.py'
    if not path.is_file():
        raise AssertionError('fixed-target recovery tool is missing')
    spec = importlib.util.spec_from_file_location('hf_compact_recovery_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FileProofTests(unittest.TestCase):
    def setUp(self):
        self.module = load_tool()
        temporary = tempfile.TemporaryDirectory(prefix='kil-r-', dir='/private/tmp')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root / 'control'
        self.path.write_bytes(b'exact original control\n')
        self.path.chmod(0o600)

    def test_exact_file_can_be_guarded_and_closed_twice(self):
        proof = self.module._Files()
        self.addCleanup(proof.close)
        payload = proof.read(self.path, 64, 0o600, os.geteuid())
        self.assertEqual(payload, b'exact original control\n')
        proof.guard()
        proof.close()
        proof.close()
        with self.assertRaises(ValueError):
            proof.guard()

    def test_changed_bytes_mode_or_links_refuse(self):
        for alteration in ('bytes', 'mode', 'link', 'replacement'):
            with self.subTest(alteration=alteration):
                self.path.unlink(missing_ok=True)
                self.path.write_bytes(b'exact original control\n')
                self.path.chmod(0o600)
                proof = self.module._Files()
                try:
                    proof.read(self.path, 64, 0o600, os.geteuid())
                    if alteration == 'bytes':
                        self.path.write_bytes(b'changed control\n')
                    elif alteration == 'mode':
                        self.path.chmod(0o644)
                    elif alteration == 'link':
                        os.link(self.path, self.root / 'alias')
                    else:
                        self.path.rename(self.root / 'original')
                        self.path.write_bytes(b'exact original control\n')
                        self.path.chmod(0o600)
                    with self.assertRaises(ValueError):
                        proof.guard()
                finally:
                    proof.close()

    def test_symlink_loop_and_wrong_uid_refuse(self):
        proof = self.module._Files()
        try:
            with self.assertRaises(ValueError):
                proof.read(self.path, 64, 0o600, os.geteuid() + 1)
            loop = self.root / 'loop'
            loop.symlink_to(loop)
            with self.assertRaises(ValueError):
                proof.read(loop, 64, 0o600, os.geteuid())
        finally:
            proof.close()

    def test_ancestor_replacement_refuses(self):
        directory = self.root / 'parent'
        directory.mkdir(mode=0o700)
        child = directory / 'control'
        child.write_bytes(b'original')
        child.chmod(0o600)
        proof = self.module._Files()
        try:
            proof.read(child, 64, 0o600, os.geteuid())
            directory.rename(self.root / 'old-parent')
            directory.mkdir(mode=0o700)
            child.write_bytes(b'original')
            child.chmod(0o600)
            with self.assertRaises(ValueError):
                proof.guard()
        finally:
            proof.close()
```

- [ ] Run `tests.test_hf_compact_residual_recovery.FileProofTests` with the common
  interpreter flags. Require the explicit missing-tool assertions, not fixture
  setup/import mistakes. Retain RED count/output in lineage.
- [ ] Create the tool with this complete first section.

```python
"""One fixed-target manual stop; import never contacts a native runtime."""
import argparse
from contextlib import ExitStack
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
import stat
import sys

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(REPOSITORY / 'src'))

from kil.hf_exploratory_inputs import ACCEPTED_RUN, read_regular, verify_bytes
from kil.hf_exploratory_io import PrivateStore, capture_process, _dependency_snapshot
from kil.hf_exploratory_native import check_source
from kil.hf_exploratory_profile import ProfilePaths, creation_binding, unchanged
from kil.v3b2_accepted_images import ACCEPTED_MANIFEST_SHA256
from kil.v3b2_colima_inventory import capture_roster, decode_inventory, require_complete
from kil.v3b2_profile_state import ProfilePaths as DefaultPaths, capture, _read, passwd_home
from kil.v3b2_proofs import canonical, decode
from tools.hf_exploratory_kind import LabLock

DIGEST = '254877dc1b1462c4e29c068e51ad7286fe430b075bc5044c8b3076d1887ad25d'
HOME = Path('/Users/mistorm')
UID = 501
RUNTIME = HOME / '.kil-hf' / ('r' + DIGEST[:16])
RECEIPT = REPOSITORY / '.tools/hf-exploratory-private' / ('hf-exploratory-' + DIGEST)
RECOVERY = REPOSITORY / '.tools/hf-recovery-private/2026-09-17' / ('manual-stop-' + DIGEST)
TOOLS = Path('/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.tools/bin')
COLIMA = HOME / '.local/bin/colima'
ROOT_ID = (16777232, 615011851, 16832, 501)
MANIFEST_PIN = ('d128fd99fcc32391db27804da8be86c0e62b238343b71c7f44009785cba38ad0', 3979)
SSH_PIN = ('0788dfecc6e2e6d6301a2eca6d9bebe153de450cac6d4657b053f2676a9564e9', 767)
COLIMA_PIN = ('980ad8bf61a4ca370243f4cb41401a61276dcd2c2502bee7b9b86f9250169f34', 15656320)
SOURCE = '7d5c58372040ecf5b7c1fdd9c9d7ea3ddcd06205'
COLIMA_VERSION = b'colima version v0.10.3\ngit commit: 00f6c297e92a82c04a4ab507db0a61435650d7e8\n'
MAXIMUM = 8 * 1024**2


def _id(row):
    return row.st_dev, row.st_ino, row.st_mode, row.st_uid


def _fid(row):
    return (*_id(row), row.st_nlink, row.st_size, row.st_mtime_ns, row.st_ctime_ns)


class _Files:
    """Read-only retained directories/files; never creates or adopts a runtime."""
    def __init__(self):
        self.stack = ExitStack()
        self.directories = {}
        self.files = []
        self.closed = False

    def directory(self, path, private=False):
        try:
            if self.closed or not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts:
                raise ValueError('unsafe_recovery_directory')
            if path not in self.directories:
                parent = None if path == Path('/') else self.directory(path.parent)
                fd = os.open('/' if parent is None else path.name,
                             os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.stack.callback(os.close, fd)
                identity = _id(os.fstat(fd))
                if _id(os.stat(path, follow_symlinks=False)) != identity:
                    raise ValueError('recovery_directory_replaced')
                self.directories[path] = (fd, identity)
            fd, identity = self.directories[path]
            if private and (stat.S_IMODE(identity[2]) != 0o700 or identity[3] != UID):
                raise ValueError('recovery_directory_not_private')
            return fd
        except (OSError, RuntimeError) as error:
            raise ValueError('unsafe_recovery_directory') from error

    def read(self, path, maximum, mode, uid, pin=None):
        try:
            parent = self.directory(path.parent)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            self.stack.callback(os.close, fd)
            row = os.fstat(fd)
            if (not stat.S_ISREG(row.st_mode) or row.st_nlink != 1 or row.st_uid != uid
                    or stat.S_IMODE(row.st_mode) != mode or row.st_size > maximum):
                raise ValueError('unsafe_recovery_file')
            payload = read_regular(path, maximum)
            if pin is not None:
                verify_bytes(payload, *pin)
            record = (path, fd, _fid(row), sha256(payload).hexdigest(), maximum)
            self.files.append(record)
            self.guard()
            return payload
        except (OSError, RuntimeError) as error:
            raise ValueError('unsafe_recovery_file') from error

    def guard(self, mutable=()):
        try:
            if self.closed:
                raise ValueError('recovery_proof_closed')
            for path, (fd, identity) in self.directories.items():
                if _id(os.fstat(fd)) != identity or _id(os.stat(path, follow_symlinks=False)) != identity:
                    raise ValueError('recovery_ancestry_changed')
            for path, fd, identity, digest, maximum in self.files:
                if path in mutable:
                    continue
                if _fid(os.fstat(fd)) != identity or _fid(path.lstat()) != identity:
                    raise ValueError('recovery_file_changed')
                if sha256(read_regular(path, maximum)).hexdigest() != digest:
                    raise ValueError('recovery_file_bytes_changed')
            for path, fd, identity, digest, maximum in self.files:
                if path in mutable:
                    continue
                if _fid(os.fstat(fd)) != identity or _fid(path.lstat()) != identity:
                    raise ValueError('recovery_file_changed_after_authentication')
            for path, (fd, identity) in self.directories.items():
                if _id(os.fstat(fd)) != identity or _id(path.lstat()) != identity:
                    raise ValueError('recovery_ancestry_changed_after_authentication')
        except (OSError, RuntimeError) as error:
            raise ValueError('recovery_proof_unavailable') from error

    def close(self):
        if not self.closed:
            self.closed = True
            self.stack.close()
```

- [ ] Run the FileProofTests again; require GREEN/no ResourceWarning. Add final
  authentication-IO substitution and retained-FD replacement tests before
  changing guard ordering. Add a real hardlink/loop/UID/mode/parent replacement
  assertion for each failure, always with zero native acquisition.
- [ ] Append lineage and commit only tool/test plus lineage/readers after verified
  GREEN. Keep the production file boundary exact.

## Task 2: Authenticated receipt and exact saved footprint

**Files:** Append to the same tool and test file. No production edits.

- [ ] Add tests that build46 real0600 evidence files and their manifest under an
  owned temporary receipt. Replace only MANIFEST_PIN with that fixture digest/size.
  For each malformed manifest below, pin the malformed fixture bytes deliberately,
  then require structural refusal, proving the digest check is not the only guard.

```python
from hashlib import sha256
from unittest.mock import patch


class ReceiptTests(FileProofTests):
    def make_receipt(self):
        receipt = self.root / 'receipt'
        receipt.mkdir(mode=0o700)
        rows = []
        for number in range(46):
            name = 'file-%04d.json' % number
            payload = b'{}\n'
            path = receipt / name
            path.write_bytes(payload)
            path.chmod(0o600)
            rows.append('%s  %s\n' % (sha256(payload).hexdigest(), name))
        manifest = ''.join(rows).encode()
        (receipt / 'SHA256SUMS').write_bytes(manifest)
        (receipt / 'SHA256SUMS').chmod(0o600)
        return receipt, manifest

    def test_complete_manifest_verifies_without_native_process(self):
        receipt, payload = self.make_receipt()
        proof = self.module._Files()
        try:
            with patch.object(self.module, 'RECEIPT', receipt), patch.object(
                    self.module, 'MANIFEST_PIN', (sha256(payload).hexdigest(), len(payload))), patch.object(
                    self.module, 'UID', os.geteuid()):
                self.assertEqual(len(self.module._receipt(proof)), 46)
        finally:
            proof.close()

    def test_manifest_count_duplicate_and_traversal_refuse(self):
        receipt, payload = self.make_receipt()
        lines = payload.splitlines(keepends=True)
        cases = (b''.join(lines[:-1]), b''.join(lines[:-1] + [lines[0]]),
                 payload.replace(b'file-0000.json', b'../outside.json', 1))
        for malformed in cases:
            (receipt / 'SHA256SUMS').write_bytes(malformed)
            proof = self.module._Files()
            try:
                with patch.object(self.module, 'RECEIPT', receipt), patch.object(
                        self.module, 'MANIFEST_PIN', (sha256(malformed).hexdigest(), len(malformed))), patch.object(
                        self.module, 'UID', os.geteuid()), self.assertRaises(ValueError):
                    self.module._receipt(proof)
            finally:
                proof.close()
```

- [ ] Run ReceiptTests RED against Task1, requiring missing `_receipt`, then
  append this implementation. Observe the remaining report/footprint tests fail
  before adding their corresponding functions.

```python
def _receipt(proof):
    manifest = proof.read(RECEIPT / 'SHA256SUMS', 8192, 0o600, UID, MANIFEST_PIN)
    rows = manifest.splitlines(keepends=True)
    if len(rows) != 46:
        raise ValueError('recovery_receipt_count')
    files = {}
    for line in rows:
        match = re.fullmatch(rb'([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._-]{0,127})\n', line)
        if match is None:
            raise ValueError('recovery_receipt_manifest_shape')
        digest, name = match[1].decode(), match[2].decode()
        if name in files or name == 'SHA256SUMS':
            raise ValueError('recovery_receipt_duplicate')
        payload = proof.read(RECEIPT / name, MAXIMUM, 0o600, UID)
        if sha256(payload).hexdigest() != digest:
            raise ValueError('recovery_receipt_checksum')
        files[name] = payload
    return files


def _retained(proof):
    if os.getuid() != UID or os.geteuid() != UID or passwd_home() != HOME:
        raise ValueError('recovery_account_mismatch')
    runtime = _Files()
    try:
        for path in (RUNTIME.parent, RUNTIME, RUNTIME / '.colima', RUNTIME / '.colima/_lima',
                     RUNTIME / 'docker-config', RUNTIME / 'runtime-tmp'):
            runtime.directory(path, private=True)
        if _id(os.fstat(runtime.directory(RUNTIME))) != ROOT_ID:
            raise ValueError('recovery_root_identity')
        proof.directory(RECEIPT.parent, private=True)
        proof.directory(RECEIPT, private=True)
        files = _receipt(proof)
        binding = decode(files['runtime-binding.json'], maximum=8192)
        expected = {'schema': 'kil.hf-exploratory-runtime-binding.v1', 'uid': UID,
                    'run_digest': DIGEST, 'run_id': 'v3b2-' + DIGEST,
                    'receipt_path': str(RECEIPT), 'registry_path': str(RUNTIME.parent),
                    'runtime_path': str(RUNTIME), 'runtime_identity': dict(zip(
                        ('device', 'inode', 'mode', 'uid'), ROOT_ID))}
        if canonical(binding) != canonical(expected) or files['runtime-binding.json'] != canonical(expected):
            raise ValueError('recovery_full_binding_mismatch')
        marker = canonical({'schema': 'kil.hf-exploratory-runtime-registry.v1',
                            'uid': UID, 'runtime_parent': str(RUNTIME.parent)})
        if runtime.read(RUNTIME.parent / 'registry.json', 8192, 0o600, UID) != marker:
            raise ValueError('recovery_registry_marker')
        report = decode(files['report.json'], maximum=1024**2)
        expected_fields = {'schema_version': 'kil.hf-exploratory-report.v1',
                           'run_id': 'v3b2-' + DIGEST, 'source_commit': SOURCE,
                           'mode': 'rehearsal', 'status': 'inconclusive',
                           'manual_recovery': True, 'request_intent_count': 0,
                           'request_attempt_count': 0, 'joined_results': []}
        if any(type(report.get(key)) is not type(value) or report.get(key) != value
               for key, value in expected_fields.items()):
            raise ValueError('recovery_report_premise')
        if report['paths'] != {'actual_default_home': str(HOME), 'receipt': str(RECEIPT), 'runtime': str(RUNTIME)}:
            raise ValueError('recovery_report_paths')
        if report['profile_resources']['actual_creation_bound'] is not True:
            raise ValueError('recovery_creation_unbound')
        paths = ProfilePaths(HOME, RUNTIME)
        for path in (paths.profile, paths.instance, paths.disk):
            runtime.directory(path)
            if path.lstat().st_uid != UID:
                raise ValueError('recovery_owned_directory_uid')
        original = decode(files['profile-created.json'], maximum=1024**2)
        if creation_binding(paths.document(), original) != report['profile_binding']:
            raise ValueError('recovery_saved_binding_mismatch')
        leftovers = decode(files['runtime-leftovers.json'], maximum=1024**2)
        for row in leftovers['directories']:
            path = Path(row['runtime_path'])
            if path not in (RUNTIME, paths.colima, paths.lima, RUNTIME / 'docker-config', paths.tmp):
                raise ValueError('recovery_leftover_path')
            actual = _id(os.fstat(runtime.directory(path, private=True)))[:3]
            wanted = tuple(row['observation'][key] for key in ('device', 'inode', 'mode'))
            if actual != wanted:
                raise ValueError('recovery_native_home_changed')
        proof.guard()
        runtime.guard()
        return runtime, files, paths, report, original
    except BaseException:
        runtime.close()
        raise


REMOVABLE = {
    'profile': {'docker.sock', 'containerd.sock'},
    'instance': {'ha.pid', 'ha.sock', 'ssh.sock', 'vz.pid'},
    'disk': {'in_use_by'},
}


def _footprint(paths, report, original, status):
    owned = (paths.profile, paths.instance, paths.disk, paths.profile / 'colima.yaml',
             paths.instance / 'colima.yaml', paths.instance / 'lima.yaml',
             paths.disk / 'datadisk', paths.instance / 'disk')
    if any(path.lstat().st_uid != UID for path in owned):
        raise ValueError('recovery_owned_resource_uid')
    observed = capture(paths)
    if observed != capture(paths):
        raise ValueError('recovery_capture_unstable')
    if unchanged(paths.document(), observed, report['profile_binding'], stopped=status == 'Stopped') is not True:
        raise ValueError('recovery_owned_binding_changed')
    for key in ('profile', 'instance', 'disk'):
        actual, prior = set(observed[key]['entries']), set(original[key]['entries'])
        if status == 'Running' and actual != prior:
            raise ValueError('recovery_owned_roster_changed')
        if status == 'Stopped' and (actual - prior or prior - actual - REMOVABLE[key]):
            raise ValueError('recovery_stopped_roster_unknown')
    if observed['store'] != original['store']:
        raise ValueError('recovery_store_changed')
    if status == 'Running' and observed['lock'] != original['lock']:
        raise ValueError('recovery_disk_lock_changed')
    tables = ((RUNTIME, {'.colima', 'docker-config', 'kind-config.yaml', 'runtime-tmp'}),
              (paths.colima, {'_lima', '_store', 'kil-v3-lab', 'ssh_config'}),
              (paths.lima, {'_config', '_disks', '_networks', 'colima-kil-v3-lab'}),
              (RUNTIME / 'docker-config', {'contexts'}), (paths.tmp, set()))
    for path, names in tables:
        entries = set(_read(path, directory_only=True)['entries'])
        optional = {'ssh_config'} if status == 'Stopped' and path == paths.colima else set()
        if entries - names or names - entries - optional:
            raise ValueError('recovery_namespace_roster_unknown')
    if any(path.lstat().st_uid != UID for path in owned):
        raise ValueError('recovery_owned_resource_uid_changed')
    return observed
```

- [ ] Add real saved-profile fixtures using the two existing independently
  hashed HF YAML files and create_profile's sparse disk recipe. Require RED
  before each guard change for all of these cases: full digest/UID/path/root
  mismatch; wrong marker schema/bytes/mode/hardlink; missing/changed home;
  substituted YAML/config/disk identity or raw capacity; protected/startup present;
  wrong disk-lock target; additional profile/instance/root/Lima entry; already-
  stopped lock/control release; changed store bytes. Do not use the real runtime.
- [ ] Run all new tests GREEN plus runtime/profile/strict-profile regressions.
  Append lineage and commit the exact tool/test/document paths only.

## Task 3: Closed native observations, original foreign baseline and control copies

**Files:** Append to the same tool/test. Read the existing complete-inventory
parser and foreign_snapshot/foreign_file behavior; do not construct a lifecycle.

- [ ] Add these component tests first. The native-output callback is synthetic;
  all roster directories and before/after captures remain real.

```python
from types import SimpleNamespace
from kil.v3b2_controller import CommandResult
from kil.v3b2_proofs import canonical


class InventoryTests(FileProofTests):
    def paths(self):
        lima = self.root / 'lima'
        lima.mkdir(mode=0o700)
        for name in ('_config', '_disks', '_networks', 'colima-kil-v3-lab'):
            (lima / name).mkdir(mode=0o700)
        return SimpleNamespace(lima=lima)

    def row(self):
        return {'name': 'kil-v3-lab', 'status': 'Running', 'arch': 'aarch64',
                'runtime': 'docker', 'cpus': 4, 'memory': 8 * 1024**3, 'disk': 60 * 1024**3}

    def test_successful_empty_or_partial_inventory_refuses(self):
        paths = self.paths()
        for payload in (b'', b'[]\n'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.module._inventory(paths, lambda: payload)

    def test_complete_inventory_is_not_stop_permission(self):
        paths = self.paths()
        payload = canonical(self.row())
        self.assertEqual(self.module._inventory(paths, lambda: payload), [self.row()])

    def test_roster_replacement_or_unknown_child_refuses(self):
        paths = self.paths()
        def changed():
            (paths.lima / 'colima-kil-v3-lab').rename(paths.lima / 'moved')
            return canonical(self.row())
        with self.assertRaises(ValueError):
            self.module._inventory(paths, changed)
```

- [ ] Run InventoryTests RED before appending `_inventory`; then append this
  complete section. _Native never acquires a mutating instruction here.

```python
def _final_files(receipt, runtime, after_stop=False):
    mutable = (RUNTIME / '.colima/ssh_config',) if after_stop else ()
    receipt.guard()
    runtime.guard(mutable)
    for proof in (receipt, runtime):
        for path, fd, identity, digest, maximum in proof.files:
            if proof is runtime and path in mutable:
                continue
            if _fid(os.fstat(fd)) != identity or _fid(path.lstat()) != identity:
                raise ValueError('recovery_final_file_changed')
        for path, (fd, identity) in proof.directories.items():
            if _id(os.fstat(fd)) != identity or _id(path.lstat()) != identity:
                raise ValueError('recovery_final_directory_changed')


def _inventory(paths, acquire):
    before = capture_roster(paths)
    payload = acquire()
    after = capture_roster(paths)
    return require_complete(decode_inventory(payload), before, after)


def _fingerprint(path):
    try:
        before = path.lstat()
    except FileNotFoundError:
        return {'path': str(path), 'present': False, 'identity': None,
                'byte_count': None, 'sha256': None}
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError('recovery_foreign_file_not_regular')
    payload = read_regular(path, MAXIMUM)
    after = path.lstat()
    if _fid(before) != _fid(after):
        raise ValueError('recovery_foreign_file_changed')
    keys = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    return {'path': str(path), 'present': True,
            'identity': {key: getattr(before, key) for key in keys},
            'byte_count': len(payload), 'sha256': sha256(payload).hexdigest()}


def _foreign(native):
    if os.environ.get('KUBECONFIG') is not None:
        raise ValueError('recovery_inherited_kubeconfig_changed')
    paths = DefaultPaths(HOME, RECOVERY)
    def files():
        return {'default_networks': _read(paths.lima / '_config/networks.yaml'),
                'global_docker_config': str(HOME / '.docker'),
                'global_docker_directory': _read(HOME / '.docker', directory_only=True),
                'global_docker_file': _fingerprint(HOME / '.docker/config.json'),
                'kubeconfig': {'inherited': None, 'files': [_fingerprint(HOME / '.kube/config')]}}
    before = capture_roster(paths)
    original = files()
    rows = _inventory(paths, lambda: native.observe((str(COLIMA), 'list', '--json'), 'global'))
    context = native.observe((str(TOOLS / 'docker'), 'context', 'show'), 'global')
    final = _inventory(paths, lambda: native.observe((str(COLIMA), 'list', '--json'), 'global'))
    end = capture_roster(paths)
    if (before != end or rows != final or original != files() or not context
            or len(context) > 4096 or b'\r' in context or context.count(b'\n') != 1
            or not context.endswith(b'\n')):
        raise ValueError('recovery_foreign_snapshot_unstable')
    return {'foreign_profiles': rows, 'foreign_lima_roster': before,
            'global_docker_context': context.decode('utf-8').strip(), **original}


def _control_paths(paths):
    context = sha256(b'colima-kil-v3-lab').hexdigest()
    return (
        ('profile.yaml', paths.profile / 'colima.yaml'),
        ('instance.yaml', paths.instance / 'colima.yaml'),
        ('lima.yaml', paths.instance / 'lima.yaml'),
        ('colima-ssh.config', paths.colima / 'ssh_config'),
        ('instance-ssh.config', paths.instance / 'ssh.config'),
        ('ha.pid', paths.instance / 'ha.pid'), ('vz.pid', paths.instance / 'vz.pid'),
        ('kind.yaml', RUNTIME / 'kind-config.yaml'),
        ('docker-meta.json', RUNTIME / 'docker-config/contexts/meta' / context / 'meta.json'),
        ('ha.stdout.log', paths.instance / 'ha.stdout.log'),
        ('ha.stderr.log', paths.instance / 'ha.stderr.log'),
        ('serialv.log', paths.instance / 'serialv.log'),
    )


def _controls(paths):
    rows, payloads = [], {}
    for name, path in _control_paths(paths):
        row = _fingerprint(path)
        if row['present']:
            metadata = path.lstat()
            if metadata.st_uid != UID:
                raise ValueError('recovery_control_owner')
            if {key: getattr(metadata, key) for key in row['identity']} != row['identity']:
                raise ValueError('recovery_control_identity_changed')
            payload = read_regular(path, MAXIMUM)
            if len(payload) != row['byte_count'] or sha256(payload).hexdigest() != row['sha256']:
                raise ValueError('recovery_control_capture_changed')
            if _fid(metadata) != _fid(path.lstat()):
                raise ValueError('recovery_control_capture_changed')
            payloads[name] = payload
        rows.append({'name': name, **row})
    return rows, payloads


class _Native:
    def __init__(self, receipt, runtime, paths, store):
        self.receipt, self.runtime, self.paths, self.store = receipt, runtime, paths, store
        self.sequence = 0
        self.after_stop = False
        self.stop_intent = None
        self.stop_used = False
        original_path = os.environ.get('PATH')
        if (type(original_path) is not str or not original_path
                or any(not part or not Path(part).is_absolute() for part in original_path.split(os.pathsep))):
            raise ValueError('recovery_dependency_path_invalid')
        self.environment = {key: os.environ[key] for key in ('LANG', 'LC_ALL') if key in os.environ}
        self.environment.update(HOME=str(HOME), PATH=str(TOOLS) + os.pathsep + original_path)
        manifest_path = REPOSITORY / 'artifacts/generated/v3b1-local-envoy' / ACCEPTED_RUN / 'manifest.json'
        self.manifest = receipt.read(manifest_path, 1024**2,
                                     stat.S_IMODE(manifest_path.lstat().st_mode), UID)
        verify_bytes(self.manifest, ACCEPTED_MANIFEST_SHA256, len(self.manifest))
        self.accepted = decode(self.manifest, maximum=1024**2)['verified_tool_identities']
        self.dependencies = _dependency_snapshot(TOOLS, self.accepted)
        runtime.read(COLIMA, 128 * 1024**2, 0o755, UID, COLIMA_PIN)
        found = shutil.which('limactl', path=original_path)
        if not found:
            raise ValueError('recovery_lima_unavailable')
        self.original_path, self.lima_locator = original_path, found
        self.lima_locator_identity = _fid(Path(found).lstat())
        self.lima = Path(found).resolve(strict=True)
        runtime.read(self.lima, 128 * 1024**2, stat.S_IMODE(self.lima.lstat().st_mode), UID)
        if not self.lima.lstat().st_mode & stat.S_IXUSR:
            raise ValueError('recovery_lima_not_owner_executable')

    def guard(self):
        if os.getuid() != UID or os.geteuid() != UID or passwd_home() != HOME:
            raise ValueError('recovery_account_changed')
        self.store._bound(b'', 1)
        if _dependency_snapshot(TOOLS, self.accepted) != self.dependencies:
            raise ValueError('recovery_accepted_dependencies_changed')
        verify_bytes(self.manifest, ACCEPTED_MANIFEST_SHA256, len(self.manifest))
        _final_files(self.receipt, self.runtime, self.after_stop)
        current = shutil.which('limactl', path=self.original_path)
        if (current != self.lima_locator or _fid(Path(current).lstat()) != self.lima_locator_identity
                or Path(current).resolve(strict=True) != self.lima):
            raise ValueError('recovery_lima_locator_changed')
        if os.getuid() != UID or os.geteuid() != UID or passwd_home() != HOME:
            raise ValueError('recovery_account_changed_after_authentication')

    def endpoint(self):
        return 'unix://' + str(self.paths.profile / 'docker.sock')

    def environment_for(self, namespace):
        environment = dict(self.environment)
        if namespace == 'private':
            environment.update(COLIMA_HOME=str(self.paths.colima), LIMA_HOME=str(self.paths.lima),
                               DOCKER_CONFIG=str(RUNTIME / 'docker-config'), TMPDIR=str(self.paths.tmp))
        elif namespace == 'docker':
            environment.update(DOCKER_CONFIG=str(RUNTIME / 'docker-config'), TMPDIR=str(self.paths.tmp))
        elif namespace == 'global':
            environment['DOCKER_CONFIG'] = str(HOME / '.docker')
        else:
            raise ValueError('recovery_namespace_unknown')
        return environment

    def allowed(self, argv, namespace):
        return (
            (argv in ((str(COLIMA), 'version'), (str(COLIMA), 'list', '--json'))
             and namespace in ('private', 'global'))
            or (argv == (str(self.lima), '--version') and namespace == 'global')
            or (argv == (str(TOOLS / 'docker'), 'context', 'show') and namespace == 'global')
            or (argv == (str(TOOLS / 'docker'), '--host', self.endpoint(), 'ps', '--all', '--quiet', '--no-trunc')
                and namespace == 'docker')
        )

    def acquire(self, argv, namespace, timeout):
        stopping = argv == (str(COLIMA), 'stop', '--profile', 'kil-v3-lab')
        if stopping:
            if namespace != 'private' or timeout != 300 or self.stop_used or self.stop_intent is None:
                raise ValueError('recovery_stop_not_armed')
            self.stop_used = True
            path = self.store.path / 'manual-stop-intent.json'
            metadata = path.lstat()
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_uid != UID or stat.S_IMODE(metadata.st_mode) != 0o600
                    or read_regular(path, 1024**2) != self.stop_intent):
                raise ValueError('recovery_stop_intent_changed')
            self.receipt.read(path, 1024**2, 0o600, UID,
                              (sha256(self.stop_intent).hexdigest(), len(self.stop_intent)))
        elif timeout != 10 or not self.allowed(argv, namespace):
            raise ValueError('recovery_acquisition_outside_closed_grammar')
        self.guard()
        self.sequence += 1
        prefix = 'command-%04d' % self.sequence
        environment = self.environment_for(namespace)
        self.store.record('command_intent', {'argv': argv, 'environment': environment, 'timeout': timeout})
        self.guard()
        try:
            result = capture_process(argv, environment, None, timeout, MAXIMUM, REPOSITORY)
        finally:
            if stopping:
                self.after_stop = True
        self.store.write(prefix + '.stdout', result.stdout_bytes)
        self.store.write(prefix + '.stderr', result.stderr_bytes)
        self.store.record('command_terminal', {'prefix': prefix, 'returncode': result.returncode})
        return result

    def observe(self, argv, namespace):
        if type(argv) is not tuple or not self.allowed(argv, namespace):
            raise ValueError('recovery_read_outside_closed_grammar')
        result = self.acquire(argv, namespace, 10)
        if result.returncode != 0 or result.stderr_bytes:
            raise ValueError('recovery_read_transport_uncertain')
        return result.stdout_bytes


def _preflight(native, paths, report, original, files, authenticate=True):
    if native.observe((str(COLIMA), 'version'), 'private') != COLIMA_VERSION:
        raise ValueError('recovery_colima_version_changed')
    if native.observe((str(native.lima), '--version'), 'global') != b'limactl version 2.2.0\n':
        raise ValueError('recovery_lima_version_changed')
    rows = _inventory(paths, lambda: native.observe((str(COLIMA), 'list', '--json'), 'private'))
    fixed = {'name': 'kil-v3-lab', 'arch': 'aarch64', 'runtime': 'docker', 'cpus': 4,
             'memory': 8 * 1024**3, 'disk': 60 * 1024**3}
    if len(rows) != 1 or any(rows[0].get(key) != value for key, value in fixed.items()):
        raise ValueError('recovery_private_inventory_not_exact')
    status = rows[0]['status']
    observed = _footprint(paths, report, original, status)
    if authenticate:
        for key, directory in (('profile', paths.profile), ('instance', paths.instance)):
            name = directory / 'colima.yaml'
            native.runtime.read(name, 65536, 0o644, UID)
        native.runtime.read(paths.instance / 'lima.yaml', 65536, 0o644, UID)
        native.runtime.read(RUNTIME / 'kind-config.yaml', 65536, 0o600, UID,
                            (sha256(files['runtime-kind-config.yaml']).hexdigest(), len(files['runtime-kind-config.yaml'])))
        ssh = paths.colima / 'ssh_config'
        if status == 'Running' or ssh.exists():
            native.runtime.read(ssh, 8192, 0o644, UID, SSH_PIN)
    if status == 'Running':
        payload = native.observe((str(TOOLS / 'docker'), '--host', native.endpoint(),
                                  'ps', '--all', '--quiet', '--no-trunc'), 'docker')
        if payload != b'':
            raise ValueError('recovery_endpoint_not_empty')
    foreign = _foreign(native)
    if foreign != decode(files['foreign-original.json'], maximum=1024**2):
        raise ValueError('recovery_original_foreign_state_changed')
    controls, payloads = _controls(paths)
    native.guard()
    return {'status': status, 'private_inventory': rows, 'footprint': observed,
            'foreign': foreign, 'controls': controls}, payloads
```

- [ ] Add integration tests with real short fixed-location fixtures before using
  _Native: exactly46 pinned receipt files, exact canonical marker/full binding,
  the two saved HF YAML fixtures, real sparse raw disks, accepted three-file
  dependency directory and pinned fixture manifest. Patch only private constants /
  passwd-home selector and capture_process (including check_source's process seam).
  Exercise both private/global environments and prove closed grammar refuses
  stop/delete/force/limactl mutations and arbitrary argv without acquisition.
- [ ] Run new tests and relevant IO/native/inventory regressions GREEN. Actual
  native activity count during these tests must remain zero; record mock dispatch
  counts separately. Append lineage/reader and commit exact scoped paths.

## Task 4: Durable one-stop transaction and honest post-observation

**Files:** Append to the same tool/test. No live instructions during this task.

- [ ] Add and run these RED tests before `_Once` exists. They exercise the real
  exclusive store and its fsync/write behavior; callbacks do not invoke native tools.

```python
from kil.hf_exploratory_io import PrivateStore


class OnceTests(FileProofTests):
    def test_one_slot_is_consumed_before_dispatch(self):
        store = PrivateStore(self.root / 'new-evidence')
        try:
            once = self.module._Once(store)
            events = []
            result = once.send(b'{"fixed":"intent"}\n', lambda: events.append('checked'),
                               lambda: events.append('sent'))
            self.assertIsNone(result)
            self.assertEqual(events, ['checked', 'sent'])
            self.assertEqual((store.path / 'manual-stop-intent.json').read_bytes(), b'{"fixed":"intent"}\n')
            with self.assertRaises(ValueError):
                once.send(b'{}\n', lambda: None, lambda: events.append('again'))
            self.assertEqual(events, ['checked', 'sent'])
        finally:
            store.close()

    def test_final_refusal_or_uncertain_dispatch_never_retries(self):
        for phase in ('check', 'dispatch'):
            with self.subTest(phase=phase):
                store = PrivateStore(self.root / ('evidence-' + phase))
                try:
                    once = self.module._Once(store)
                    events = []
                    def refused():
                        raise ValueError('actual uncertainty')
                    check = refused if phase == 'check' else lambda: None
                    dispatch = refused if phase == 'dispatch' else lambda: events.append('sent')
                    with self.assertRaises(ValueError):
                        once.send(b'{}\n', check, dispatch)
                    with self.assertRaises(ValueError):
                        once.send(b'{}\n', lambda: None, lambda: events.append('retry'))
                    self.assertEqual(events, [])
                finally:
                    store.close()
```

- [ ] Run OnceTests RED, then append this complete orchestration and CLI section.

```python
class _Once:
    def __init__(self, store):
        self.store = store
        self.used = False

    def send(self, intent, check, dispatch):
        if self.used:
            raise ValueError('recovery_stop_slot_consumed')
        self.used = True
        self.store.write('manual-stop-intent.json', intent)
        check()
        return dispatch()


def _new_store(receipt):
    parent = REPOSITORY / '.tools'
    descriptor = receipt.directory(parent)
    for name in ('hf-recovery-private', '2026-09-17'):
        try:
            os.mkdir(name, mode=0o700, dir_fd=descriptor)
            os.fsync(descriptor)
        except FileExistsError:
            pass
        parent = parent / name
        descriptor = receipt.directory(parent, private=True)
    if parent != RECOVERY.parent:
        raise ValueError('recovery_evidence_parent_mismatch')
    receipt.guard()
    store = PrivateStore(RECOVERY)
    try:
        receipt.directory(store.path, private=True)
        receipt.read(store.path / 'lock', 64, 0o600, UID)
        if _id(os.fstat(store._lock)) != _id((store.path / 'lock').lstat()):
            raise ValueError('recovery_store_lock_mismatch')
        return store
    except BaseException:
        store.close()
        raise


def _seal(store):
    names = sorted(os.listdir(store._directory))
    if len(names) > 256:
        raise ValueError('recovery_receipt_roster_unbounded')
    rows = []
    total = 0
    for name in names:
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', name) is None:
            raise ValueError('recovery_receipt_filename_unsafe')
        if name == 'SHA256SUMS':
            raise ValueError('recovery_receipt_already_sealed')
        metadata = os.stat(name, dir_fd=store._directory, follow_symlinks=False)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or metadata.st_uid != UID or stat.S_IMODE(metadata.st_mode) != 0o600):
            raise ValueError('recovery_receipt_file_unsafe')
        payload = read_regular(store.path / name, MAXIMUM)
        total += len(payload)
        if total > 256 * 1024**2:
            raise ValueError('recovery_receipt_aggregate_unbounded')
        rows.append('%s  %s\n' % (sha256(payload).hexdigest(), name))
    store.write('SHA256SUMS', ''.join(rows).encode())


def recover(reviewed_source, execution_approval):
    if (type(reviewed_source) is not str or re.fullmatch(r'[0-9a-f]{40}', reviewed_source) is None
            or type(execution_approval) is not str or not execution_approval.strip()
            or len(execution_approval.encode()) > 4096):
        raise ValueError('recovery_requires_exact_review_and_execution_approval_record')
    check_source(REPOSITORY, reviewed_source)
    with LabLock(REPOSITORY) as lock, ExitStack() as stack:
        receipt = _Files()
        stack.callback(receipt.close)
        receipt.read(lock.path / 'profile.lock', 8192, 0o600, UID)
        if _id(os.fstat(lock.lock)) != _id((lock.path / 'profile.lock').lstat()):
            raise ValueError('recovery_lab_lock_mismatch')
        runtime, files, paths, report, original = _retained(receipt)
        stack.callback(runtime.close)
        store = _new_store(receipt)
        stack.callback(store.close)
        native = None
        outcome = {'schema': 'kil.hf-compact-manual-recovery.v1', 'run_id': 'v3b2-' + DIGEST,
                   'reviewed_source': reviewed_source, 'stop_dispatches': 0,
                   'command_returncode': None, 'observed_private_status': None,
                   'preservation_verified': False, 'status': 'preflight_refused',
                   'hf_request_intents': 0, 'hf_request_attempts': 0}
        try:
            native = _Native(receipt, runtime, paths, store)
            pre, payloads = _preflight(native, paths, report, original, files)
            lock.guard()
            store.write('pre-observations.json', canonical(pre))
            for name, payload in payloads.items():
                store.write('pre-' + name, payload)
            if pre['status'] == 'Stopped':
                fresh, ignored = _preflight(native, paths, report, original, files, authenticate=False)
                if fresh != pre:
                    raise ValueError('recovery_already_stopped_postflight_changed')
                lock.guard()
                native.guard()
                outcome.update(status='already_stopped_observed', observed_private_status='Stopped',
                               preservation_verified=True)
            else:
                argv = (str(COLIMA), 'stop', '--profile', 'kil-v3-lab')
                intent = canonical({'schema': 'kil.hf-compact-manual-stop-intent.v1',
                                    'execution_approval': execution_approval,
                                    'reviewed_source': reviewed_source, 'run_id': 'v3b2-' + DIGEST,
                                    'runtime': str(RUNTIME), 'receipt': str(RECEIPT),
                                    'pre_sha256': sha256(canonical(pre)).hexdigest(),
                                    'argv': argv, 'environment': native.environment_for('private'),
                                    'timeout_seconds': 300, 'maximum_output_bytes': MAXIMUM,
                                    'max_native_mutations': 1})
                def recheck():
                    fresh, ignored = _preflight(native, paths, report, original, files, authenticate=False)
                    if fresh != pre:
                        raise ValueError('recovery_final_preflight_changed')
                    check_source(REPOSITORY, reviewed_source)
                    lock.guard()
                    native.guard()
                def dispatch():
                    native.stop_intent = intent
                    outcome['status'] = 'command_uncertain'
                    result = native.acquire(argv, 'private', 300)
                    outcome['stop_dispatches'] = 1 if result.returncode >= 0 else None
                    return result
                result = _Once(store).send(intent, recheck, dispatch)
                outcome['command_returncode'] = result.returncode
                outcome['status'] = 'postverification_inconclusive'
                rows = _inventory(paths, lambda: native.observe((str(COLIMA), 'list', '--json'), 'private'))
                if len(rows) == 1:
                    outcome['observed_private_status'] = rows[0]['status']
                expected = {key: value for key, value in pre['private_inventory'][0].items() if key != 'address'}
                expected['status'] = 'Stopped'
                if len(rows) != 1 or any(rows[0].get(key) != value for key, value in expected.items()):
                    raise ValueError('recovery_post_inventory_not_exact_stopped')
                post_footprint = _footprint(paths, report, original, 'Stopped')
                foreign = _foreign(native)
                if foreign != pre['foreign']:
                    raise ValueError('recovery_post_foreign_state_changed')
                controls, post_payloads = _controls(paths)
                store.write('post-observations.json', canonical({'private_inventory': rows,
                            'footprint': post_footprint, 'foreign': foreign, 'controls': controls}))
                for name, payload in post_payloads.items():
                    store.write('post-' + name, payload)
                lock.guard()
                native.guard()
                outcome['preservation_verified'] = True
                outcome['status'] = 'graceful_stop_confirmed' if result.returncode == 0 else 'command_uncertain'
        except (ValueError, OSError, RuntimeError, KeyError, TypeError, UnicodeError) as error:
            outcome['error'] = ('%s: %s' % (type(error).__name__, error))[:4096]
            if native is not None and native.stop_used:
                outcome['status'] = ('postverification_inconclusive' if
                    outcome['command_returncode'] is not None and outcome['command_returncode'] >= 0
                    else 'command_uncertain')
                # A spent slot is not proof that native acquisition happened.
                if outcome['command_returncode'] is None:
                    outcome['stop_dispatches'] = None if native.after_stop else 0
                try:
                    rows = _inventory(paths, lambda: native.observe((str(COLIMA), 'list', '--json'), 'private'))
                    outcome['observed_private_status'] = rows[0]['status'] if len(rows) == 1 else None
                except (ValueError, OSError, RuntimeError, KeyError, TypeError) as post_error:
                    outcome['post_error'] = str(post_error)[:4096]
        store.write('outcome.json', canonical(outcome))
        _seal(store)
        return outcome


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--reviewed-source', required=True)
    parser.add_argument('--execution-approval', required=True)
    parser.add_argument('--execute-approved-stop', action='store_true', required=True)
    args = parser.parse_args(argv)
    outcome = recover(args.reviewed_source, args.execution_approval)
    sys.stdout.buffer.write(canonical(outcome))
    return 0 if outcome['status'] in ('already_stopped_observed', 'graceful_stop_confirmed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
```

- [ ] Before GREEN, add real tests for preexisting evidence, pending intent,
  fsync failure, a changed intent between recheck and acquisition, final authority
  IO replacement, already-stopped zero dispatch, and stop timeout/overflow/lost
  result. Include assertions below in the end-to-end fixture tests; the only
  patched native function is capture_process in this tool and check_source's
  owning module. Return CommandResult for synthetic Git, version, inventories,
  context and Docker observations. Simulated stop modifies real temporary lock/
  SSH controls; it must never signal a process.

```python
def assert_stop_boundary(test, events, outcome, expected_count):
    stops = [event for event in events if event['argv'][1:2] == ('stop',)]
    test.assertEqual(len(stops), expected_count)
    test.assertEqual(outcome['hf_request_intents'], 0)
    test.assertEqual(outcome['hf_request_attempts'], 0)
    for event in stops:
        test.assertEqual(event['argv'][2:], ('--profile', 'kil-v3-lab'))
        test.assertEqual(event['stdin'], None)
        test.assertEqual(event['timeout'], 300)
        test.assertEqual(event['environment']['COLIMA_HOME'], str(test.module.RUNTIME / '.colima'))
        test.assertEqual(event['environment']['LIMA_HOME'], str(test.module.RUNTIME / '.colima/_lima'))
        test.assertEqual(event['environment']['DOCKER_CONFIG'], str(test.module.RUNTIME / 'docker-config'))
    test.assertFalse(any('delete' in event['argv'] or '--force' in event['argv'] for event in events))
```

- [ ] Run complete new tests GREEN with ResourceWarning fatal. Check both46-entry
  fixture receipt verification and the new recovery receipt seal after simulated
  SSH control changes. Confirm old bytes remain exact; do not silently regenerate
  old manifests. Append lineage and commit exact tool/test/document paths only.

## Task 5: Independent engineering review and preparation handoff

**Files:** Tool/test plus factual plan and lineage/readers only.

- [ ] Add this complete fixture/composed test section before the final engineering
  GREEN. Its simulated native stop changes only real temporary fixture files.
  Extend the mutation table with each important composed-review finding before
  changing the implementation recipe; do not weaken protected production code.

```python
from contextlib import ExitStack
from kil import hf_exploratory_runtime as runtime_module
from kil import hf_exploratory_native as native_module
from tests.test_hf_exploratory_native import create_native_profile
from kil.hf_exploratory_profile import ProfilePaths, creation_binding
from kil.v3b2_profile_state import capture, _read


class ComposedTests(FileProofTests):
    def fixture(self, case):
        m = self.module
        base = self.root / case
        base.mkdir(mode=0o700)
        home = base / 'home'
        home.mkdir(mode=0o700)
        registry = home / '.kil-hf'
        registry.mkdir(mode=0o700)
        runtime = registry / ('r' + m.DIGEST[:16])
        runtime.mkdir(mode=0o700)
        receipt = base / '.tools/hf-exploratory-private' / ('hf-exploratory-' + m.DIGEST)
        receipt.mkdir(parents=True, mode=0o700)
        receipt.parent.chmod(0o700)
        tools = base / 'bin'
        tools.mkdir(mode=0o700)
        local = home / '.local/bin'
        local.mkdir(parents=True, mode=0o700)
        colima, lima = local / 'colima', local / 'limactl'
        payload = b'fixture executable; never executed\n'
        for path in (colima, lima, *(tools / name for name in ('docker', 'kind', 'kubectl'))):
            path.write_bytes(payload)
            path.chmod(0o755)
        accepted = {'verified_tool_identities': {name: {
            'executable_sha256': sha256(payload).hexdigest(), 'byte_size': len(payload)}
            for name in ('docker', 'kind', 'kubectl')}}
        manifest = canonical(accepted)
        manifest_path = base / 'artifacts/generated/v3b1-local-envoy' / m.ACCEPTED_RUN / 'manifest.json'
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_bytes(manifest)
        manifest_path.chmod(0o644)
        stack = ExitStack()
        self.addCleanup(stack.close)
        replacements = {'REPOSITORY': base, 'HOME': home, 'UID': os.geteuid(),
                        'RUNTIME': runtime, 'RECEIPT': receipt, 'TOOLS': tools,
                        'COLIMA': colima, 'COLIMA_PIN': (sha256(payload).hexdigest(), len(payload)),
                        'RECOVERY': base / '.tools/hf-recovery-private/2026-09-17' / ('manual-stop-' + m.DIGEST),
                        'ACCEPTED_MANIFEST_SHA256': sha256(manifest).hexdigest(),
                        'ROOT_ID': m._id(runtime.lstat())}
        for name, value in replacements.items():
            stack.enter_context(patch.object(m, name, value))
        stack.enter_context(patch.object(m, 'passwd_home', return_value=home))
        stack.enter_context(patch.object(runtime_module, '_registry_parent', return_value=registry))
        stack.enter_context(patch.dict(os.environ, {'PATH': str(local)}, clear=True))
        paths = ProfilePaths(home, runtime)
        for directory in (paths.colima, paths.lima, runtime / 'docker-config', paths.tmp):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        (runtime / 'docker-config/contexts').mkdir(mode=0o700)
        for name in ('_config', '_disks', '_networks'):
            (paths.lima / name).mkdir(mode=0o700, exist_ok=True)
        (paths.colima / '_store').mkdir(mode=0o700)
        create_native_profile(paths)
        for path in (paths.profile / 'colima.yaml', paths.instance / 'colima.yaml', paths.instance / 'lima.yaml'):
            path.chmod(0o644)
        for directory in (paths.profile, paths.instance, paths.disk):
            directory.chmod(0o755 if directory == paths.profile else 0o700)
        (paths.colima / 'ssh_config').write_bytes(b'pinned fixture SSH control\n')
        (paths.colima / 'ssh_config').chmod(0o644)
        ssh_payload = (paths.colima / 'ssh_config').read_bytes()
        stack.enter_context(patch.object(m, 'SSH_PIN', (sha256(ssh_payload).hexdigest(), len(ssh_payload))))
        kind = b'fixture Kind control; not applied\n'
        (runtime / 'kind-config.yaml').write_bytes(kind)
        (runtime / 'kind-config.yaml').chmod(0o600)
        original = capture(paths)
        binding = creation_binding(paths.document(), original)
        def absent(path):
            return {'path': str(path), 'present': False, 'identity': None, 'byte_count': None, 'sha256': None}
        foreign = {'foreign_profiles': [], 'foreign_lima_roster': None,
                   'global_docker_context': 'default', 'default_networks': None,
                   'global_docker_config': str(home / '.docker'), 'global_docker_directory': None,
                   'global_docker_file': absent(home / '.docker/config.json'),
                   'kubeconfig': {'inherited': None, 'files': [absent(home / '.kube/config')]}}
        report = {'schema_version': 'kil.hf-exploratory-report.v1', 'run_id': 'v3b2-' + m.DIGEST,
                  'source_commit': m.SOURCE, 'mode': 'rehearsal', 'status': 'inconclusive',
                  'manual_recovery': True, 'request_intent_count': 0, 'request_attempt_count': 0,
                  'joined_results': [], 'profile_binding': binding,
                  'profile_resources': {'actual_creation_bound': True},
                  'paths': {'actual_default_home': str(home), 'runtime': str(runtime), 'receipt': str(receipt)}}
        full_binding = {'schema': 'kil.hf-exploratory-runtime-binding.v1', 'uid': os.geteuid(),
                        'run_digest': m.DIGEST, 'run_id': 'v3b2-' + m.DIGEST, 'receipt_path': str(receipt),
                        'registry_path': str(registry), 'runtime_path': str(runtime),
                        'runtime_identity': dict(zip(('device', 'inode', 'mode', 'uid'), replacements['ROOT_ID']))}
        documents = {'report.json': canonical(report), 'profile-created.json': canonical(original),
                     'runtime-binding.json': canonical(full_binding), 'foreign-original.json': canonical(foreign),
                     'runtime-kind-config.yaml': kind, 'runtime-leftovers.json': canonical({'directories': [
                         {'runtime_path': str(path), 'observation': _read(path, directory_only=True)}
                         for path in (runtime, paths.colima, paths.lima, runtime / 'docker-config', paths.tmp)]})}
        for number in range(46 - len(documents)):
            documents['fixture-%04d.json' % number] = b'{}\n'
        rows = []
        for name, value in sorted(documents.items()):
            (receipt / name).write_bytes(value)
            (receipt / name).chmod(0o600)
            rows.append('%s  %s\n' % (sha256(value).hexdigest(), name))
        receipt_manifest = ''.join(rows).encode()
        (receipt / 'SHA256SUMS').write_bytes(receipt_manifest)
        (receipt / 'SHA256SUMS').chmod(0o600)
        stack.enter_context(patch.object(m, 'MANIFEST_PIN', (sha256(receipt_manifest).hexdigest(), len(receipt_manifest))))
        (registry / 'registry.json').write_bytes(canonical({'schema': 'kil.hf-exploratory-runtime-registry.v1',
                                                           'uid': os.geteuid(), 'runtime_parent': str(registry)}))
        (registry / 'registry.json').chmod(0o600)
        return stack, paths, documents

    def test_composed_stop_noop_refusals_and_uncertainty(self):
        for case in ('stop', 'stopped', 'unknown', 'nonempty', 'foreign', 'timeout', 'overflow'):
            with self.subTest(case=case):
                stack, paths, old = self.fixture(case)
                m = self.module
                events = []
                status = ['Stopped' if case == 'stopped' else 'Running']
                if case == 'stopped':
                    (paths.disk / 'in_use_by').unlink()
                if case == 'unknown':
                    (m.RUNTIME / 'unknown').write_bytes(b'unrecognized')
                def acquire(argv, environment, stdin, timeout, maximum, cwd):
                    events.append({'argv': argv, 'environment': environment, 'stdin': stdin, 'timeout': timeout})
                    output, returncode = b'', 0
                    if argv[:2] == ('git', 'rev-parse'):
                        output = b'a' * 40 + b'\n'
                    elif argv[1:] == ('version',):
                        output = m.COLIMA_VERSION
                    elif argv[1:] == ('--version',):
                        output = b'limactl version 2.2.0\n'
                    elif argv[1:] == ('list', '--json'):
                        output = b'' if 'COLIMA_HOME' not in environment else canonical({
                            'name': 'kil-v3-lab', 'status': status[0], 'arch': 'aarch64', 'runtime': 'docker',
                            'cpus': 4, 'memory': 8 * 1024**3, 'disk': 60 * 1024**3})
                    elif argv[1:] == ('context', 'show'):
                        output = b'changed\n' if case == 'foreign' else b'default\n'
                    elif 'ps' in argv:
                        output = b'container\n' if case == 'nonempty' else b''
                    elif argv[1:2] == ('stop',):
                        status[0] = 'Stopped'
                        (paths.disk / 'in_use_by').unlink()
                        (paths.colima / 'ssh_config').write_bytes(b'changed stopped SSH control\n')
                        returncode = -1000 if case == 'timeout' else -1001 if case == 'overflow' else 0
                    return CommandResult(returncode, output.decode(), '', output, b'')
                try:
                    with patch.object(m, 'capture_process', side_effect=acquire), patch.object(
                            native_module, 'capture_process', side_effect=acquire):
                        outcome = m.recover('a' * 40, 'fixture approval; not native authority')
                        count = 1 if case in ('stop', 'timeout', 'overflow') else 0
                        assert_stop_boundary(self, events, outcome, count)
                        expected = {'stop': 'graceful_stop_confirmed', 'stopped': 'already_stopped_observed',
                                    'timeout': 'command_uncertain', 'overflow': 'command_uncertain'}
                        self.assertEqual(outcome['status'], expected.get(case, 'preflight_refused'))
                        before = len(events)
                        with self.assertRaises((OSError, ValueError)):
                            m.recover('a' * 40, 'no second permission')
                        self.assertFalse(any(event['argv'][1:2] == ('stop',) for event in events[before:]))
                    for name, value in old.items():
                        self.assertEqual((m.RECEIPT / name).read_bytes(), value)
                finally:
                    stack.close()
```

- [ ] Review composed source against every approved-spec section. This plan's
  code is an implementation recipe, not evidence that it passes; important
  findings require new failing tests, minimum scoped fixes and re-verification.
  Check final cross-chain/file ordering, durable intent authentication before
  acquisition, command certainty versus observed stopped status, mutable SSH
  postconditions, evidence sealing/bounds, exception/FD paths and no implicit
  live action. Do not widen a failing guard to make a mock pass.
- [ ] Run this full regression command after new tests pass:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_compact_residual_recovery tests.test_hf_exploratory_runtime tests.test_hf_exploratory_profile tests.test_hf_exploratory_evidence tests.test_hf_exploratory_case tests.test_hf_exploratory_inputs tests.test_hf_exploratory_io tests.test_hf_exploratory_native tests.test_v3b2_profile_state tests.test_v3b2_journal tests.test_v4_future_controller_gate tests.test_v3b2_inventory tests.test_v3b2_colima_inventory tests.test_v3b2_runtime_inventory_ownership tests.test_v3b2_bootstrap_inventory tests.test_v3b2_runtime_image_inventory
```

Expected: actual OK/no failures/errors/ResourceWarning. Record actual count/time,
not a guessed460 plus estimated new count. Unit success is not VM recovery.

- [ ] Verify unchanged protected paths and all46 real sealed receipt checksums
  read-only. Regenerate/check readers, check canonical citations and preserve
  complete predecessor lineage as an exact prefix. Never rewrite the four known
  immutable citation omissions or claim full discovery green.
- [ ] Mark actual engineering tasks, retain RED/GREEN/review outcomes, commit
  exact scoped paths and verify clean exact HEAD. No branch move/push/merge.
- [ ] Report readiness for **one separate approved recovery attempt**, not HF
  test readiness. Ask explicit execution approval before live preflight, evidence
  directory reservation, or stop. Engineering tests must not create the real
  RECOVERY directory or open the real runtime.

## Task 6: Later native attempt — blocked until explicit execution approval

This task is documented, not approved or performed by written-spec approval.

- [ ] Confirm user's explicit one-stop approval and no concurrent native activity.
  Root alone dispatches the prepared fixed tool at the exact clean reviewed HEAD
  through the scoped outside-sandbox route if required. Pass that verified40-hex
  commit and the actual approval text, never substitute a test source or invent
  approval. The sole executable entry is `main`, whose required flags were
  defined above; do not call the exploratory launcher main.
- [ ] Warn that CPU/RAM may be released, disks remain, and native controls may
  change. Run once; any preflight refusal, timeout, overflow, ambiguous result or
  partial evidence ends this permission. Do not select another evidence suffix.
- [ ] Independently verify original46 checksums and new recovery SHA256SUMS,
  private stopped observation, profile/disk/config retention and protected state
  using the fixed bounded observers. Preserve exceptions rather than restoring
  missing controls. Append actual lineage/outcome and end at that stopping place.

No restart, deletion, force, discovered-process kill, cleanup, second rehearsal,
image-provenance audit, Ollama operation or HF request. Recovery alone does not
repair the production SSH-control refusal. Accepted local Envoy remains unchanged;
platform-image provenance is unverified/full Kind-Calico acceptance false.

## Plan self-review and coverage

Identity/evidence/ancestry/SSH pins map to Tasks1–2; complete inventories,
protected baseline, private command grammar and bounded copies to Task3; durable
once-only intent/stopped no-op/uncertainty/postconditions/sealing to Task4;
test-first checks/composed review/regressions/clean handoff to Task5. Task6 is
separately gated native execution. No native path is touched by preparing this
document. All internal functions used in the implementation recipe are defined
above or explicitly imported from unchanged existing modules.

Self-review also pins/rechecks the original Lima PATH locator separately from
its resolved executable, and rechecks actual account identity after guard IO.
Recipe syntax checks do not establish behavior or native readiness. Each new
important engineering finding gets a real failing test before the minimum fix.

Writing-plans requires an execution-method choice next: subagent-driven with
two-stage review, or inline executing-plans with batch checkpoints. Neither
method selection authorizes Task6.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

## Engineering execution record — 2026-09-17

The user selected subagent-driven preparation with independent reviews.
CONFIRMED fixture-only Tasks1–5; Task6 remains separately unapproved. Keep the
historical method-choice text above as the planning checkpoint, not current status.
The seven-module scoped baseline passed325 tests in221.476s with bytecode disabled
and ResourceWarning fatal. No installation or workspace/branch change.

Task1 is VERIFIED: initial missing-tool RED4 explicit assertion failures;
closed-proof RED1/5 followed by GREEN; final root FileProofTests9/0.068s OK.
Independent spec review PASS; quality review PASS after adding its minor real
retained-descriptor substitution regression, independently9/0.092s OK. The tool
has only internal fixed-target file/ancestry proof; no process/CLI/orchestration.
No live runtime observation or recovery receipt reservation. Next is Task2 under
the same preparation approval; subsequent engineering tasks are not yet complete.

Task2 is VERIFIED at the subsequent engineering checkpoint. The receipt proof
authenticates all46 pinned files and the exact canonical saved binding/report;
fresh footprint checks preserve eight resource identities, three YAMLs, raw disk
capacities/headers, finite Running/Stopped roster rules and five private homes.
Independent reviews exposed typed-JSON equality and late authentication-IO gaps;
each implementation defect received genuine failing real-filesystem regressions
before its minimum fix. Final metadata-only checks follow all content/roster IO
across17 named targets; guest disk timestamps/content and unrelated registry
siblings are deliberately not frozen. No atomic-snapshot claim.
Final independent spec PASS47/12.583s; quality PASS47/11.255s plus eight independent
supplemental real-IO cases/2.466s. Root scoped regression157/52.561s OK, bytecode
disabled/ResourceWarning fatal. Prior intermediate passes did not override the
supplemental defects. Only the fixed tool/test and append-only plan/lineage readers
changed; no native command, actual runtime/receipt access or recovery reservation.
Next is Task3 under the same preparation approval. Tasks3–5 are not yet complete;
Task6 and the live HF test remain unapproved.

Task3 is VERIFIED at the subsequent engineering checkpoint. Component work was
split from remaining composed coverage after the first implementer's explicit
DONE_WITH_CONCERNS/NEEDS_CONTEXT handoff; a fresh-context continuation completed
the same approved scope. Full fixtures authenticate all46 sealed files through
_retained, then real _Native/_preflight, rather than bypassing receipt proof.
The closed read grammar records exact effective executable argv/environment,
bounds/cwd, raw stdout/stderr and returned-versus-uncertain terminal evidence.
Cross-proof, locator/PATH-choice, original foreign-state, control-copy identity
and accepted-prefix late-addition defects received genuine RED tests/minimum
fixes. Final metadata helpers do not reopen directory/content reads. SSH
relaxation depends only on internal after-stop state, never skip-rebinding.
Final implementer125/45.228s, independent spec PASS125/45.101s, independent quality
PASS125/41.377s; root fresh four-module regression328/220.432s OK with bytecode
disabled/ResourceWarning fatal. Quality found no Critical/Important issue; its
nonblocking repeated-manifest descriptor observation is recorded for bounded
Task4 review, not concealed. Running/Stopped fixture preflights used seven/six
simulated reads; actual Colima/Lima/Docker acquisitions zero. Generic IO fixture
child Python processes are not represented as live native VM activity.
No actual runtime/receipt access, recovery reservation or native stop. Next is
Task4 under the same preparation approval; Tasks4–5 are not yet complete and
Task6 remains separately unapproved. Accepted local Envoy is unchanged; platform
image provenance stays unverified and full Kind/Calico acceptance false.

Task4a is VERIFIED as a bounded evidence-primitives checkpoint, not completion
of Task4. The implementer explicitly handed off DONE_WITH_CONCERNS because the
remaining transaction requires fresh context; root retained the same approved
scope and ordered independent reviews. _Once consumes the slot before durable
exclusive intent persistence; _new_store anchors private ancestry and exclusively
reserves the fixed evidence path with bound empty lock/cleanup; _seal covers all
bounded new evidence, including lock/journal, without repairing or resealing.
The retained accepted-manifest descriptor is now reused without weakening its
current-byte, pin or full named/FD metadata authentication.

Missing-feature and descriptor-leak REDs preceded their fixes. Spec review then
reproduced an aggregate-budget gap: growth after the first size-stat was accepted
by a later authenticated read while the total retained the old size. Genuine
growth and same-size-change REDs preceded full eight-field stat-to-retained
continuity and authenticated-byte accounting. Additional boundary/cleanup tests
were coverage additions, not claimed missing-feature REDs. Final implementer
154/39.366s OK; spec re-review PASS154/34.123s and independent original-growth
refusal before manifest creation/0.091s; fresh quality PASS154/39.123s, no
Critical/Important findings, plus four independent real-file probes/0.064s.
Root fresh five-module regression427/218.144s OK, bytecode disabled and
ResourceWarning fatal; unchanged candidate hashes confirmed after completion.
Earlier425/214.386s is a superseded pre-fix observation, not final acceptance.

Quality's module-description Minor is deferred to the final CLI implementation.
Its nonblocking observation is disclosed: identical-byte manifest replacement
during initial fsync is authenticated as the current digest/full identity; this
contract does not separately pin the original manifest-writer inode. No original
evidence commitment was relaxed. Next is fresh-context Task4b: exact stop grammar,
durable authenticated commitments, honest handoff/uncertainty/postconditions,
recover/CLI and composed fault tests, carrying proofs through final evidence and
seal IO. Tasks4–5 remain incomplete. Task6 remains unapproved; actual native VM
activity, recovery reservation and HF requests remain zero/current VM unobserved.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

Task4b and therefore Task4 are VERIFIED engineering checkpoints. Fresh-context
implementation completes real clean-source-before-mutation gating, held LabLock,
protected constructor refusal, exclusive original-writer intent and fixed private
one-stop grammar, fresh no-op/stop/post observations, independent command/status/
preservation outcomes, evidence sealing and required non-abbreviated CLI flags.
No production SSH guard, launcher, accepted contract or native target was changed.
All outcomes retain full review/run/runtime/old-receipt commitments, and successful
native authentication produces bounded native-proof.json even for zero-stop paths.

Genuine RED→GREEN fixes include absent recover/CLI, same-byte intent replacement
during writer fsync, locale drift during both journal and final source auth,
separately observed Stopped lost on later proof refusal, CLI startup exceptions,
and missing reviewed-source identity in no-op/constructor-refusal evidence.
Independent spec then reproduced missing final inherited-KUBECONFIG closure:
source-time drift reached one mocked stop; seal-time drift returned verified
preservation in both stop/no-op fixtures. Genuine RED3/3.387s preceded the minimal
two-line metadata-only absence check; GREEN3/2.602s. Independent original probes
now require zero stop at source time and refuse verified preservation/seal at
seal time, without new content/roster reads. Final spec PASS206/82.973s; fresh
quality PASS206/76.730s plus seven independent real-file probes/6.895s and import
safety/descriptor cleanup. Final implementer local206/83.551s and related273/
202.888s OK; root fresh five-module regression479/268.318s OK, bytecode disabled
and ResourceWarning fatal. Candidate hashes preserved through root verification.
Pre-fix476 runs and the duplicate-inherited228 intermediate run are superseded.

The new fixed-adapter outcome schema uses outcome/returncode/observed_status/
preservation labels; no preexisting consumer/protocol is altered. Reviewed
semantic adaptation: sealed outcome.json explicitly final_closure_pending=True
is a provisional observation, not final acceptance. Only the returned result
after seal and all retained proof metadata closure can confirm verification;
late closure failure returns refusal/inconclusive without overwrite/reseal.
Spec and quality judged this coherent. The prior stale module-description Minor
is fixed with the guarded CLI. Task5 final composed acceptance/full regression/
whole-implementation review remain pending; Task6 stays separately unapproved.
Actual VM activity/reservation/HF requests remain zero; current VM unobserved.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

Task5 is VERIFIED at the final engineering checkpoint, superseding the pending
status above without rewriting the planning recipe or earlier observations.
The coverage-only extension uses the existing real composed fixture: sealed
original same-name global Stopped inventory is never the private stop target;
optional post-stop guest address is retained but nonbinding; returned results
omit final_closure_pending while sealed observations retain it across success,
no-op, constructor refusal and uncertainty. No missing-feature RED is claimed
for these additions. Spec re-review required the final constructor-refusal flag
assertion; focused1/0.494s OK, then fresh quality PASS208/82.405s on all38 added
lines, bytecode disabled and ResourceWarning fatal.

Fresh whole-implementation review then found Important/P1 outcome dishonesty:
the outer ExitStack exited beyond recover's inner handler, so a real final
LabLock ancestor failure could escape to main's startup fallback and report
zero stops after one entered stop. Its independent real temporary repository
replacement before ORIGINAL LabLock exit reproduced this; existing208/93.029s
OK did not establish coverage of that edge. Same Task4b implementer added six
real-ancestry regressions, genuine RED6/5.674s, then minimum GREEN6/5.827s.
The retained native/outcome state and outer handler now enclose all owned
teardown. Late exceptions retain actual dispatch/returncode/certainty/status and
source/run/receipt identity, downgrade preservation/seal, and never reopen,
overwrite or reseal evidence. Successful command becomes postverification_inconclusive;
nonzero/timeout/lost command remains command_uncertain; no-op and
prehand paths stay zero-stop refusal. The inner transaction is otherwise unchanged.

Final implementer214/92.483s OK; ordered independent spec PASS214/94.073s plus
the original real ancestry probe; independent quality PASS214/86.141s plus two
real temporary constructor/lost-capture late-exit probes, confirming earlier
exceptions retained and tracked proof/store/lock descriptors closed. Original
whole reviewer re-review PASS: focused6/5.599s plus independent original
reproducer/0.994s, no remaining Critical/Important finding. Root focused6/5.001s
and final full16-module regression674/312.194s OK, bytecode disabled and
ResourceWarning fatal. Final regression ran alongside read-only review on the
frozen post-fix candidate; source/test hashes stayed2b58ab23…7ccf864/
a4ee14ce…ccaf64f. The earlier668/318.381s run began before the last coverage
assertion and teardown fix: superseded, not final candidate acceptance.

Task5's explicit read-only retained-evidence check authenticated the actual
3979-byte SHA256SUMS pin d128fd99…ba38ad0 (UID501/0600/single-link), then all46
listed checksums passed. The fixed RECOVERY directory was absent at that check;
no engineering test reserved it. This is retained receipt verification, not
platform-image provenance or a live VM inventory. No actual runtime opening,
Colima/Lima/Docker acquisition, live preflight/stop, HF request, Ollama operation,
new rehearsal or production SSH compatibility change. Accepted local Envoy is
unchanged; current VM status remains unobserved, platform provenance unverified
and full Kind/Calico acceptance false. Four historical immutable citation
omissions remain disclosed; scoped success is not full discovery success.

Tasks1–5 engineering are verified. Final records/readers, complete predecessor
lineage prefix, exact scoped local commit and clean HEAD checks complete this
handoff. Task6 remains UNAPPROVED: ask separate explicit approval for one fixed
stop-only recovery attempt including live preflight and exclusive evidence
creation. Recovery readiness is not HF readiness; no restart, force, deletion,
retry, alternate receipt suffix or inferred live continuation.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
