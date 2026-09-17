"""Fixed-target retained-file proof for the manual HF residual stop path.

This module deliberately has no command entry point.  It only retains and
re-authenticates fixed local files before a later, separately approved stage.
"""
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import stat
import sys


REPOSITORY = Path(__file__).resolve().parents[1]
for _location in (REPOSITORY, REPOSITORY / 'src'):
    if str(_location) not in sys.path:
        sys.path.insert(0, str(_location))

from kil.hf_exploratory_inputs import read_regular, verify_bytes


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


def _canonical(path):
    if not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts:
        raise ValueError('recovery_path_is_not_absolute_canonical')
    try:
        if path.resolve(strict=True) != path:
            raise ValueError('recovery_path_is_not_absolute_canonical')
    except (OSError, RuntimeError) as error:
        raise ValueError('recovery_path_is_not_absolute_canonical') from error
    return path


class _Files:
    def __init__(self):
        self._stack = ExitStack()
        self.directories = {}
        self.files = []
        self.closed = False

    def _retain(self, fd):
        self._stack.callback(os.close, fd)
        return fd

    def _check_directories(self):
        for path in sorted(self.directories, key=lambda item: len(item.parts)):
            fd, identity = self.directories[path]
            if _id(os.fstat(fd)) != identity or not stat.S_ISDIR(identity[2]):
                raise ValueError('recovery_directory_descriptor_changed')
            if path != Path('/'):
                parent_fd, _ = self.directories[path.parent]
                named = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
                if _id(named) != identity:
                    raise ValueError('recovery_directory_name_changed')

    def directory(self, path, private=False):
        try:
            if self.closed:
                raise ValueError('recovery_file_proof_is_closed')
            path = _canonical(path)
            if type(private) is not bool:
                raise ValueError('recovery_directory_privacy_is_invalid')
            if path not in self.directories:
                root_fd = self._retain(os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
                root_identity = _id(os.fstat(root_fd))
                if _id(os.stat('/', follow_symlinks=False)) != root_identity:
                    raise ValueError('recovery_root_reanchored')
                self.directories[Path('/')] = (root_fd, root_identity)
                current = Path('/')
                for part in path.parts[1:]:
                    current = current / part
                    if current in self.directories:
                        continue
                    parent_fd, _ = self.directories[current.parent]
                    fd = self._retain(os.open(
                        part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd,
                    ))
                    identity = _id(os.fstat(fd))
                    named = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
                    if not stat.S_ISDIR(identity[2]) or _id(named) != identity:
                        raise ValueError('recovery_directory_reanchored')
                    self.directories[current] = (fd, identity)
            self._check_directories()
            fd, identity = self.directories[path]
            if private and (stat.S_IMODE(identity[2]) != 0o700 or identity[3] != UID):
                raise ValueError('recovery_directory_not_private')
            return fd
        except (OSError, RuntimeError) as error:
            raise ValueError('recovery_directory_unavailable') from error

    def _check_file(self, record):
        path, fd, identity, _, _ = record
        parent_fd, _ = self.directories[path.parent]
        named = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if _fid(os.fstat(fd)) != identity or _fid(named) != identity:
            raise ValueError('recovery_file_changed')

    def _retained_bytes(self, record):
        path, fd, identity, _, maximum = record
        self._check_file(record)
        os.lseek(fd, 0, os.SEEK_SET)
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b''.join(chunks)
        if len(payload) != identity[5] or len(payload) > maximum:
            raise ValueError('recovery_file_read_is_not_bounded')
        self._check_file(record)
        return payload

    def read(self, path, maximum, mode, uid, pin=None):
        try:
            if self.closed:
                raise ValueError('recovery_file_proof_is_closed')
            path = _canonical(path)
            if (type(maximum) is not int or maximum <= 0 or type(mode) is not int
                    or type(uid) is not int or uid != os.geteuid()):
                raise ValueError('recovery_file_expectation_is_invalid')
            parent_fd = self.directory(path.parent)
            fd = self._retain(os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd,
            ))
            row = os.fstat(fd)
            named = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            identity = _fid(row)
            if (not stat.S_ISREG(row.st_mode) or stat.S_IMODE(row.st_mode) != mode
                    or row.st_uid != uid or row.st_nlink != 1 or row.st_size > maximum
                    or _fid(named) != identity):
                raise ValueError('recovery_file_is_not_exact_private_regular')
            payload = read_regular(path, maximum)
            if pin is not None:
                verify_bytes(payload, *pin)
            record = (path, fd, identity, hashlib.sha256(payload).hexdigest(), maximum)
            self._check_file(record)
            if hashlib.sha256(self._retained_bytes(record)).hexdigest() != record[3]:
                raise ValueError('recovery_file_bytes_changed')
            self.files.append(record)
            self.guard()
            return payload
        except (OSError, RuntimeError) as error:
            raise ValueError('recovery_file_unavailable') from error

    def guard(self, mutable=()):
        try:
            if self.closed:
                raise ValueError('recovery_file_proof_is_closed')
            mutable_paths = frozenset(mutable)
            self._check_directories()
            retained = []
            for record in self.files:
                if record[0] not in mutable_paths:
                    self._check_file(record)
                    payload = self._retained_bytes(record)
                    if hashlib.sha256(payload).hexdigest() != record[3]:
                        raise ValueError('recovery_file_bytes_changed')
                    retained.append(record)
            for record in retained:
                self._check_file(record)
            self._check_directories()
        except (OSError, RuntimeError) as error:
            raise ValueError('recovery_file_proof_unavailable') from error

    def close(self):
        if not self.closed:
            self.closed = True
            self._stack.close()
