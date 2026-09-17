import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY = Path(__file__).resolve().parents[1]
TOOL_PATH = REPOSITORY / 'tools' / 'hf_compact_residual_recovery.py'


def load_tool():
    if not TOOL_PATH.is_file():
        raise AssertionError('fixed-target recovery tool is missing')
    for location in (str(REPOSITORY), str(REPOSITORY / 'src')):
        if location not in sys.path:
            sys.path.insert(0, location)
    spec = importlib.util.spec_from_file_location('hf_compact_residual_recovery', TOOL_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError('fixed-target recovery tool is not loadable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FileProofTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.temporary = tempfile.TemporaryDirectory(prefix='kil-r-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.payload = b'exact original control\n'
        self.control = self.root / 'control'
        self.control.write_bytes(self.payload)
        self.control.chmod(0o600)
        self.assertEqual(stat.S_IMODE(self.control.stat().st_mode), 0o600)
        self.assertEqual(self.control.stat().st_uid, os.geteuid())

    def files(self):
        result = self.tool._Files()
        self.addCleanup(result.close)
        return result

    def test_exact_bounded_read_guard_and_close_lifecycle(self):
        files = self.files()
        self.assertEqual(files.read(self.control, len(self.payload), 0o600, os.geteuid()),
                         self.payload)
        files.guard()
        descriptors = [fd for fd, _ in files.directories.values()]
        descriptors.extend(record[1] for record in files.files)
        files.close()
        files.close()
        with self.assertRaises(ValueError):
            files.guard()
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_file_content_metadata_link_and_name_substitutions_refuse(self):
        cases = []
        for kind in ('changed', 'mode', 'hardlink', 'replacement'):
            with self.subTest(kind=kind):
                for stale in (self.root / 'additional-link', self.root / 'original'):
                    stale.unlink(missing_ok=True)
                self.control.unlink(missing_ok=True)
                self.control.write_bytes(self.payload)
                self.control.chmod(0o600)
                files = self.files()
                files.read(self.control, len(self.payload), 0o600, os.geteuid())
                if kind == 'changed':
                    self.control.write_bytes(b'changed original data\n')
                elif kind == 'mode':
                    self.control.chmod(0o644)
                elif kind == 'hardlink':
                    os.link(self.control, self.root / 'additional-link')
                else:
                    moved = self.root / 'original'
                    self.control.rename(moved)
                    self.control.write_bytes(self.payload)
                    self.control.chmod(0o600)
                with self.assertRaises(ValueError):
                    files.guard()
                cases.append(files)
        self.assertEqual(len(cases), 4)

    def test_symlink_loop_and_wrong_uid_refuse_read(self):
        loop = self.root / 'loop'
        loop.symlink_to(loop)
        with self.assertRaises(ValueError):
            self.files().read(loop, len(self.payload), 0o600, os.geteuid())
        with self.assertRaises(ValueError):
            self.files().read(self.control, len(self.payload), 0o600, os.geteuid() + 1)

    def test_closed_proof_refuses_read_and_directory_before_opening_descriptors(self):
        files = self.files()
        files.close()
        opened = []
        real_open = os.open

        def tracked_open(*args, **kwargs):
            opened.append(args[0])
            return real_open(*args, **kwargs)

        with patch.object(self.tool.os, 'open', side_effect=tracked_open):
            with self.assertRaises(ValueError):
                files.directory(self.root)
            with self.assertRaises(ValueError):
                files.read(self.control, len(self.payload), 0o600, os.geteuid())
        self.assertEqual(opened, [])

    def test_private_directory_binds_fixed_tool_uid_and_private_mode(self):
        private = self.root / 'private'
        private.mkdir(mode=0o700)
        files = self.files()
        with patch.object(self.tool, 'UID', os.geteuid()):
            self.assertIsInstance(files.directory(private, private=True), int)
        with patch.object(self.tool, 'UID', os.geteuid() + 1):
            with self.assertRaises(ValueError):
                files.directory(private, private=True)
        private.chmod(0o755)
        with patch.object(self.tool, 'UID', os.geteuid()):
            with self.assertRaises(ValueError):
                files.directory(private, private=True)

    def test_parent_rename_and_replacement_refuses(self):
        parent = self.root / 'parent'
        parent.mkdir(mode=0o700)
        child = parent / 'control'
        child.write_bytes(self.payload)
        child.chmod(0o600)
        files = self.files()
        files.read(child, len(self.payload), 0o600, os.geteuid())
        moved = self.root / 'moved-parent'
        parent.rename(moved)
        parent.mkdir(mode=0o700)
        replacement = parent / 'control'
        replacement.write_bytes(self.payload)
        replacement.chmod(0o600)
        with self.assertRaises(ValueError):
            files.guard()

    def test_read_refuses_substitution_after_bounded_authentication_io(self):
        files = self.files()
        real_read_regular = self.tool.read_regular
        moved = self.root / 'authenticated-original'

        def read_then_substitute(path, maximum):
            payload = real_read_regular(path, maximum)
            path.rename(moved)
            path.write_bytes(payload)
            path.chmod(0o600)
            return payload

        with patch.object(self.tool, 'read_regular', side_effect=read_then_substitute):
            with self.assertRaises(ValueError):
                files.read(self.control, len(self.payload), 0o600, os.geteuid())

    def test_guard_rechecks_first_file_after_later_retained_fd_io(self):
        first = self.root / 'first'
        second = self.root / 'second'
        first.write_bytes(b'first control\n')
        second.write_bytes(b'second control\n')
        first.chmod(0o600)
        second.chmod(0o600)
        files = self.files()
        files.read(first, 64, 0o600, os.geteuid())
        files.read(second, 64, 0o600, os.geteuid())
        first_fd = files.files[0][1]
        second_fd = files.files[1][1]
        real_read = os.read
        replacement_done = False

        def read_then_replace_first(fd, count):
            nonlocal replacement_done
            payload = real_read(fd, count)
            if fd == second_fd and payload == b'' and not replacement_done:
                replacement_done = True
                first.rename(self.root / 'first-original')
                first.write_bytes(b'first control\n')
                first.chmod(0o600)
            return payload

        with patch.object(self.tool.os, 'read', side_effect=read_then_replace_first):
            with self.assertRaises(ValueError):
                files.guard()
        self.assertTrue(replacement_done)
        self.assertEqual(os.fstat(first_fd).st_nlink, 1)

    def test_guard_refuses_replaced_retained_file_descriptor(self):
        first = self.root / 'first'
        replacement = self.root / 'replacement'
        first.write_bytes(b'first control\n')
        replacement.write_bytes(b'replacement control\n')
        first.chmod(0o600)
        replacement.chmod(0o600)
        files = self.files()
        files.read(first, 64, 0o600, os.geteuid())
        retained_fd = files.files[0][1]
        replacement_fd = os.open(replacement, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        self.addCleanup(os.close, replacement_fd)
        os.dup2(replacement_fd, retained_fd)
        with self.assertRaises(ValueError):
            files.guard()


if __name__ == '__main__':
    unittest.main()
