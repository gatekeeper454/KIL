import hashlib
import importlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ExploratoryInputTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_inputs'))
        self.inputs = importlib.import_module('kil.hf_exploratory_inputs')

    def test_regular_blob_is_retained_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'blob'
            path.write_bytes(b'abc')
            self.assertEqual(self.inputs.read_regular(path, 3), b'abc')
            with self.assertRaises(ValueError):
                self.inputs.read_regular(path, 2)

    def test_symlink_and_relative_path_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'blob'
            path.write_bytes(b'abc')
            link = path.with_name('link')
            link.symlink_to(path)
            for unsafe in (link, Path('relative')):
                with self.subTest(path=unsafe), self.assertRaises(ValueError):
                    self.inputs.read_regular(unsafe, 3)

    def test_substitution_and_wrong_size_are_rejected(self):
        digest = hashlib.sha256(b'abc').hexdigest()
        self.assertEqual(self.inputs.verify_bytes(b'abc', digest, 3), digest)
        for payload, size in ((b'abd', 3), (b'abc', 2)):
            with self.subTest(payload=payload, size=size), self.assertRaises(ValueError):
                self.inputs.verify_bytes(payload, digest, size)

    def test_invalid_sizes_and_uppercase_digest_are_rejected(self):
        digest = hashlib.sha256(b'abc').hexdigest()
        for size in (True, 3.0, '3', -1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                self.inputs.verify_bytes(b'abc', digest, size)
        with self.assertRaises(ValueError):
            self.inputs.verify_bytes(b'abc', digest.upper(), 3)

    def test_missing_inputs_are_unavailable_without_commands(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory).resolve() / 'missing'
            with self.assertRaisesRegex(ValueError, 'exploratory_inputs_unavailable_or_invalid'):
                self.inputs.verify_inputs(repository, missing, missing, 'a' * 64)

    def test_fifo_without_writer_is_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory).resolve() / 'fifo'
            os.mkfifo(fifo)
            child = (
                'from pathlib import Path\n'
                'import sys\n'
                'from kil.hf_exploratory_inputs import read_regular\n'
                'try:\n'
                '    read_regular(Path(sys.argv[1]), 3)\n'
                'except ValueError as error:\n'
                '    assert str(error) == "exploratory_input_not_bounded_regular_file"\n'
                'else:\n'
                '    raise AssertionError("FIFO was accepted")\n'
            )
            try:
                result = subprocess.run(
                    [sys.executable, '-c', child, str(fifo)],
                    capture_output=True, text=True, timeout=2,
                )
            except subprocess.TimeoutExpired:
                self.fail('read_regular blocked on a FIFO without a writer for 2 seconds')
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
