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
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
def _id(row):
    return row.st_dev, row.st_ino, row.st_mode, row.st_uid
def _full(row):
    return (row.st_dev, row.st_ino, row.st_mode, row.st_uid, row.st_gid, row.st_nlink, row.st_size, row.st_mtime_ns, row.st_ctime_ns)
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
            if name != '/': current = current / name
            if current not in self.records:
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
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
        if self.closed: raise ValueError('permission_ancestry_closed')
        for path, fd, original, parent, name in self.records.values():
            expected = original
            if after and path == TARGET and original is not None:
                if stat.S_IMODE(original[2]) != 0o755:
                    raise ValueError('permission_initial_transition_not_755')
                expected = (*original[:2], (original[2] & ~0o7777) | 0o700, original[3])
            if (expected is None or _id(os.fstat(fd)) != expected or _id(os.stat(name, dir_fd=parent, follow_symlinks=False)) != expected):
                raise ValueError('permission_directory_changed')
    def close(self):
        if self.closed: return []
        self.closed = True
        records, self.records = list(self.records.values()), {}
        errors = []
        for _, fd, _, _, _ in reversed(records):
            try: _close_fd(fd)
            except BaseException as error: errors.append(error)
        return errors
