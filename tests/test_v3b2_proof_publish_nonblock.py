from __future__ import annotations

import errno
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from kil.v3b2_journal import JournalError, _publish_observed_proof


class ProofPublishNonblockTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.private = Path(temporary.name)
        self.private.chmod(0o700)
        self.name = "observed-proof.json"
        self.path = self.private / self.name
        self.payload = b'{"proof":"complete"}'

    def existing_file(self, payload):
        self.path.write_bytes(payload)
        self.path.chmod(0o600)

    def test_existing_fifo_is_rejected_without_waiting_for_writer(self):
        os.mkfifo(self.path, 0o600)
        source = str(Path(__file__).resolve().parents[1] / "src")
        script = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from kil.v3b2_journal import JournalError, _publish_observed_proof
try:
    _publish_observed_proof(Path(sys.argv[2]), sys.argv[3], b'{"proof":"complete"}')
except JournalError as error:
    assert str(error) == "durable proof is not an exact owned private file"
else:
    raise AssertionError("FIFO was accepted as proof")
"""
        try:
            result = subprocess.run(
                [sys.executable, "-c", script, source, str(self.private), self.name],
                capture_output=True, text=True, timeout=3,
            )
        except subprocess.TimeoutExpired:
            self.fail("proof verification blocked on a FIFO without a writer")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(stat.S_ISFIFO(self.path.lstat().st_mode))
        self.assertEqual(list(self.private.iterdir()), [self.path])

    def test_regular_proof_publication_is_idempotent_without_replacement(self):
        _publish_observed_proof(self.private, self.name, self.payload)
        original = self.path.stat()
        _publish_observed_proof(self.private, self.name, self.payload)
        current = self.path.stat()
        self.assertEqual((current.st_dev, current.st_ino), (original.st_dev, original.st_ino))
        self.assertEqual(self.path.read_bytes(), self.payload)
        self.assertEqual(stat.S_IMODE(current.st_mode), 0o600)
        self.assertEqual(current.st_nlink, 1)
        self.assertEqual(current.st_uid, os.geteuid())
        self.assertEqual(list(self.private.iterdir()), [self.path])

    def test_existing_symlink_is_rejected_without_following_or_replacing(self):
        target = self.private / "target"
        target.write_bytes(self.payload)
        target.chmod(0o600)
        self.path.symlink_to(target)
        with self.assertRaises(OSError) as caught:
            _publish_observed_proof(self.private, self.name, self.payload)
        self.assertEqual(caught.exception.errno, errno.ELOOP)
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(target.read_bytes(), self.payload)

    def test_existing_hardlink_is_rejected_without_replacement(self):
        self.existing_file(self.payload)
        alias = self.private / "alias"
        os.link(self.path, alias)
        with self.assertRaisesRegex(JournalError, "exact owned private file"):
            _publish_observed_proof(self.private, self.name, self.payload)
        self.assertEqual(self.path.stat().st_ino, alias.stat().st_ino)
        self.assertEqual(self.path.stat().st_nlink, 2)
        self.assertEqual(self.path.read_bytes(), self.payload)

    def test_existing_altered_bytes_are_rejected_without_replacement(self):
        altered = self.payload.replace(b"complete", b"tampered")
        self.existing_file(altered)
        original = self.path.stat()
        with self.assertRaisesRegex(JournalError, "differs from its commitment"):
            _publish_observed_proof(self.private, self.name, self.payload)
        self.assertEqual(self.path.stat().st_ino, original.st_ino)
        self.assertEqual(self.path.read_bytes(), altered)

    def test_existing_nonprivate_file_is_rejected_without_replacement(self):
        self.existing_file(self.payload)
        self.path.chmod(0o644)
        with self.assertRaisesRegex(JournalError, "exact owned private file"):
            _publish_observed_proof(self.private, self.name, self.payload)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o644)
        self.assertEqual(self.path.read_bytes(), self.payload)
