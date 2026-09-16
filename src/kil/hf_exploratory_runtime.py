"""Derived, no-follow local runtime namespace; no native dispatch or recovery."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
from typing import TYPE_CHECKING

from kil.v3b2_profile_state import _parent
from kil.v3b2_journal import Command

if TYPE_CHECKING:
    from kil.hf_exploratory_io import PrivateStore


def _identity(row):
    return row.st_dev, row.st_ino, row.st_mode, row.st_uid


@dataclass(frozen=True, slots=True, init=False)
class RuntimeAuthority:
    path: Path
    _store: PrivateStore
    _digest: str
    _anchors: tuple
    _lock_identity: tuple
    _closed: bool

    def __init__(self):
        raise ValueError('runtime_authority_requires_create')

    @classmethod
    def create(cls, store, run_digest):
        from kil.hf_exploratory_io import PrivateStore
        if (cls is not RuntimeAuthority or type(store) is not PrivateStore
                or type(run_digest) is not str
                or re.fullmatch(r'[0-9a-f]{64}', run_digest) is None
                or not isinstance(store.path, Path) or not store.path.is_absolute()
                or store.path.resolve(strict=True) != store.path
                or store.path.name != 'hf-exploratory-' + run_digest
                or store.path.parent.parts[-2:] != ('.tools', 'hf-exploratory-private')
                or store._directory is None or store._lock is None):
            raise ValueError('invalid_runtime_store_authority')
        anchors = []
        def retain(parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                identity = _identity(os.fstat(fd))
            except BaseException:
                os.close(fd)
                raise
            anchors.append((parent, name, fd, identity))
            return fd
        try:
            with _parent(store.path) as observed_parent:
                if observed_parent is None:
                    raise ValueError('runtime_store_parent_missing')
                fd = retain(None, '/')
                for part in store.path.parent.parts[1:]:
                    fd = retain(fd, part)
                parent_fd = fd
                row = os.fstat(parent_fd)
                if (_identity(row) != _identity(os.fstat(observed_parent))
                        or stat.S_IMODE(row.st_mode) != 0o700 or row.st_uid != os.geteuid()):
                    raise ValueError('runtime_parent_not_private')
                store_fd = retain(parent_fd, store.path.name)
                if _identity(os.fstat(store_fd)) != _identity(os.fstat(store._directory)):
                    raise ValueError('runtime_store_reanchored')
                lock_identity = _identity(os.fstat(store._lock))
                if _identity(os.stat('lock', dir_fd=store_fd, follow_symlinks=False)) != lock_identity:
                    raise ValueError('runtime_store_lock_reanchored')
                path = store.path.parent / ('hf-exploratory-runtime-' + run_digest)
                def fresh(parent, name):
                    os.mkdir(name, mode=0o700, dir_fd=parent)
                    os.fsync(parent)
                    child = retain(parent, name)
                    row = os.fstat(child)
                    if stat.S_IMODE(row.st_mode) != 0o700 or row.st_uid != os.geteuid():
                        raise ValueError('runtime_directory_not_private')
                    return child
                root = fresh(parent_fd, path.name)
                colima = fresh(root, '.colima')
                fresh(colima, '_lima')
                fresh(root, 'docker-config')
                fresh(root, 'runtime-tmp')
                authority = object.__new__(cls)
                for name, value in (('path', path), ('_store', store), ('_digest', run_digest),
                                    ('_anchors', tuple(anchors)),
                                    ('_lock_identity', lock_identity),
                                    ('_closed', False)):
                    object.__setattr__(authority, name, value)
                authority.guard()
                return authority
        except BaseException:
            for _, _, fd, _ in reversed(anchors):
                os.close(fd)
            raise

    @property
    def colima(self):
        return self.path / '.colima'

    @property
    def lima(self):
        return self.colima / '_lima'

    @property
    def docker_config(self):
        return self.path / 'docker-config'

    @property
    def tmp(self):
        return self.path / 'runtime-tmp'

    @property
    def kubeconfig(self):
        return self.path / 'kubeconfig'

    @property
    def kind_config(self):
        return self.path / 'kind-config.yaml'

    def guard(self):
        from kil.hf_exploratory_io import PrivateStore
        try:
            store = self._store
            if (type(self) is not RuntimeAuthority or self._closed is not False
                    or type(store) is not PrivateStore or type(self._digest) is not str
                    or re.fullmatch(r'[0-9a-f]{64}', self._digest) is None
                    or not isinstance(store.path, Path) or not store.path.is_absolute()
                    or '..' in store.path.parts
                    or store.path.parent.parts[-2:] != ('.tools', 'hf-exploratory-private')
                    or store.path.name != 'hf-exploratory-' + self._digest
                    or self.path != store.path.parent / ('hf-exploratory-runtime-' + self._digest)
                    or store._directory is None or store._lock is None
                    or _identity(os.fstat(store._lock)) != self._lock_identity
                    or _identity(os.stat('lock', dir_fd=store._directory,
                                         follow_symlinks=False)) != self._lock_identity):
                raise ValueError('invalid_or_closed_runtime_authority')
            # Validate the retained layout as well as its filesystem identities.
            n = len(store.path.parent.parts)
            names = ('/', *store.path.parent.parts[1:], store.path.name, self.path.name,
                     '.colima', '_lima', 'docker-config', 'runtime-tmp')
            parents = (None, *range(n - 1), n - 1, n - 1, n + 1, n + 2, n + 1, n + 1)
            if type(self._anchors) is not tuple or len(self._anchors) != len(names):
                raise ValueError('substituted_runtime_anchors')
            for index, (parent, name, fd, identity) in enumerate(self._anchors):
                expected_parent = None if parents[index] is None else self._anchors[parents[index]][2]
                if (name != names[index] or parent != expected_parent
                        or _identity(os.fstat(fd)) != identity
                        or _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity
                        or not stat.S_ISDIR(identity[2])):
                    raise ValueError('runtime_namespace_changed')
                if index >= n - 1 and (stat.S_IMODE(identity[2]) != 0o700
                                      or identity[3] != os.geteuid()):
                    raise ValueError('runtime_namespace_not_private')
            if _identity(os.fstat(store._directory)) != self._anchors[n][3]:
                raise ValueError('runtime_store_reanchored')
        except (OSError, AttributeError, TypeError, IndexError) as error:
            raise ValueError('runtime_authority_unavailable') from error

    def close(self):
        if not self._closed:
            object.__setattr__(self, '_closed', True)
            for _, _, fd, _ in reversed(self._anchors):
                os.close(fd)

    def write_control(self, name, payload):
        if (type(name) is not str or name != 'kind-config.yaml'
                or type(payload) is not bytes or len(payload) > 65536):
            raise ValueError('invalid_runtime_control')
        self.guard()
        root = self._anchors[len(self._store.path.parent.parts) + 1][2]
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=root)
        try:
            view = memoryview(payload)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    raise OSError('short_runtime_control_write')
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(root)
        self.guard()


@dataclass(frozen=True, slots=True)
class ExploratoryColimaCommand:
    """The unchanged finite Colima grammar with derived runtime bindings only."""
    command: Command
    authority: RuntimeAuthority

    def __post_init__(self):
        if (type(self) is not ExploratoryColimaCommand or type(getattr(self, 'command', None)) is not Command
                or type(getattr(self, 'authority', None)) is not RuntimeAuthority):
            raise ValueError('invalid_exploratory_colima_command')
        self.command.__post_init__()
        if self.command.argv[0] != 'colima' or self.command.env:
            raise ValueError('exploratory_colima_requires_empty_strict_environment')
        self.authority.guard()

    @property
    def argv(self):
        return self.command.argv

    @property
    def timeout_s(self):
        return self.command.timeout_s

    @property
    def mutating(self):
        return self.command.mutating

    @property
    def stdin(self):
        return self.command.stdin

    @property
    def env(self):
        self.__post_init__()
        return (('COLIMA_HOME', str(self.authority.colima)),
                ('LIMA_HOME', str(self.authority.lima)),
                ('DOCKER_CONFIG', str(self.authority.docker_config)),
                ('TMPDIR', str(self.authority.tmp)))
