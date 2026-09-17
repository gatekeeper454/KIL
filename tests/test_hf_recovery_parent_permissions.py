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
        self.original_modes = [stat.S_IMODE(p.stat().st_mode) for p in (self.receipt, self.payload, self.seal)]
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in {'REPOSITORY': self.root, 'TARGET': self.target, 'UID': os.geteuid(), 'TOOLS_PIN': (self.tools.stat().st_dev, self.tools.stat().st_ino), 'TARGET_PIN': (self.target.stat().st_dev, self.target.stat().st_ino)}.items():
            self.stack.enter_context(patch.object(self.tool, name, value))
    def unchanged_receipts(self):
        self.assertEqual(self.payload.read_bytes(), self.original_payload)
        self.assertEqual(self.seal.read_bytes(), self.original_seal)
        self.assertEqual([stat.S_IMODE(p.stat().st_mode) for p in (self.receipt, self.payload, self.seal)], self.original_modes)

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
            with self.assertRaises(OSError): os.fstat(descriptor)
        with self.assertRaises(ValueError): dirs.guard()
        self.unchanged_receipts()
    def test_real_ancestor_reanchor_and_symlink_refuse(self):
        dirs = self.tool._Directories()
        self.addCleanup(dirs.close)
        dirs.directory(self.target)
        moved = self.root / 'moved-tools'
        self.tools.rename(moved)
        self.tools.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError): dirs.guard()
        fresh = self.tool._Directories()
        self.addCleanup(fresh.close)
        with self.assertRaises(OSError): fresh.directory(self.target)
    def test_target_replacement_or_mode_change_is_not_adopted(self):
        dirs = self.tool._Directories()
        self.addCleanup(dirs.close)
        dirs.directory(self.target)
        self.target.chmod(0o700)
        with self.assertRaises(ValueError): dirs.guard()
        self.target.chmod(0o755)
        self.target.rename(self.tools / 'original-target')
        self.target.mkdir(mode=0o755)
        with self.assertRaises(ValueError): dirs.guard()
    def test_after_guard_rejects_unapproved_initial_target_modes(self):
        for initial_mode in (0o705, 0o777, 0o700):
            self.target.chmod(initial_mode)
            dirs = self.tool._Directories()
            try:
                dirs.directory(self.target)
                self.target.chmod(0o700)
                with self.assertRaises(ValueError): dirs.guard(after=True)
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
