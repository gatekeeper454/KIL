"""Derived, no-follow local runtime namespace; no native dispatch or recovery."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
from typing import TYPE_CHECKING

from kil.v3b2_journal import Command
from kil.v3b2_profile_state import passwd_home
from kil.v3b2_proofs import canonical

if TYPE_CHECKING:
    from kil.hf_exploratory_io import PrivateStore


def _identity(row):
    return row.st_dev, row.st_ino, row.st_mode, row.st_uid


def _file_identity(row):
    return (*_identity(row), row.st_nlink, row.st_size, row.st_mtime_ns, row.st_ctime_ns)


def _registry_parent():
    """Production selection is actual passwd home, never a caller/environment path."""
    home = passwd_home()
    try:
        if (not isinstance(home, Path) or not home.is_absolute() or '..' in home.parts
                or home == Path('/') or home.resolve(strict=True) != home):
            raise ValueError('runtime_passwd_home_noncanonical')
    except RuntimeError as error:
        # Python 3.12 Path.resolve reports a real symlink loop as RuntimeError.
        raise ValueError('runtime_passwd_home_noncanonical') from error
    return home / '.kil-hf'


def _location(digest):
    registry = _registry_parent()
    if (not isinstance(registry, Path) or not registry.is_absolute()
            or '..' in registry.parts or registry == Path('/')
            or registry.parent.resolve(strict=True) != registry.parent):
        raise ValueError('runtime_registry_noncanonical')
    root = registry / ('r' + digest[:16])
    for suffix in ('.colima/_lima/colima-kil-v3-lab/ssh.sock.1234567890123456',
                   '.colima/kil-v3-lab/docker.sock'):
        if len(os.fsencode(root / suffix)) >= 104:
            raise ValueError('runtime_socket_path_exceeds_bound')
    return registry, root


def _topology(receipt, registry, root):
    """Expected names/parent indexes, independently reconstructed for both walks."""
    layout = []
    def walk(path):
        parent = None
        for name in ('/', *path.parts[1:]):
            layout.append((parent, name, False))
            parent = len(layout) - 1
        return parent
    store_index = walk(receipt)
    layout[store_index - 1] = (*layout[store_index - 1][:2], True)
    layout[store_index] = (*layout[store_index][:2], True)
    registry_index = walk(registry)
    layout[registry_index] = (*layout[registry_index][:2], True)
    layout.append((registry_index, root.name, True))
    root_index = len(layout) - 1
    layout.append((root_index, '.colima', True))
    colima_index = len(layout) - 1
    layout.extend(((colima_index, '_lima', True), (root_index, 'docker-config', True),
                   (root_index, 'runtime-tmp', True)))
    return tuple(layout), store_index, registry_index, root_index


def _marker_bytes(uid, registry):
    return canonical({'schema': 'kil.hf-exploratory-runtime-registry.v1',
                      'uid': uid, 'runtime_parent': str(registry)})


def _binding_bytes(uid, digest, receipt, registry, root, identity):
    return canonical({'schema': 'kil.hf-exploratory-runtime-binding.v1', 'uid': uid,
                      'run_digest': digest, 'run_id': 'v3b2-' + digest,
                      'receipt_path': str(receipt), 'registry_path': str(registry),
                      'runtime_path': str(root), 'runtime_identity': dict(zip(
                          ('device', 'inode', 'mode', 'uid'), identity))})


def _file_check(parent, name, fd, identity, expected, uid):
    retained = os.fstat(fd)
    named = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (type(identity) is not tuple or len(identity) != 8
            or any(type(value) is not int for value in identity)
            or type(expected) is not bytes or len(expected) > 8192
            or _file_identity(retained) != identity or _file_identity(named) != identity
            or not stat.S_ISREG(retained.st_mode) or stat.S_IMODE(retained.st_mode) != 0o600
            or retained.st_uid != uid or retained.st_nlink != 1
            or retained.st_size != len(expected)):
        raise ValueError('runtime_auth_file_changed')


def _file_auth(parent, name, fd, identity, expected, uid):
    _file_check(parent, name, fd, identity, expected, uid)
    os.lseek(fd, 0, os.SEEK_SET)
    chunks, size = [], 0
    while size <= 8192:
        chunk = os.read(fd, 8193 - size)
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    if b''.join(chunks) != expected:
        raise ValueError('runtime_auth_file_bytes_changed')
    _file_check(parent, name, fd, identity, expected, uid)


@dataclass(frozen=True, slots=True, init=False)
class RuntimeAuthority:
    path: Path
    _store: PrivateStore
    _digest: str
    _anchors: tuple
    _lock_identity: tuple
    _store_ref: PrivateStore
    _receipt_path: Path
    _registry: Path
    _uid: int
    _store_fd: int
    _root_fd: int
    _lock_fd: int
    _marker: tuple
    _binding: tuple
    _descriptors: tuple
    _closed: bool

    def __init__(self):
        raise ValueError('runtime_authority_requires_create')

    @classmethod
    def create(cls, store, run_digest):
        from kil.hf_exploratory_io import PrivateStore
        anchors, owned = [], []
        def retain(parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            owned.append(fd)
            identity = _identity(os.fstat(fd))
            if (not stat.S_ISDIR(identity[2])
                    or _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity):
                raise ValueError('runtime_directory_reanchored_during_walk')
            anchors.append((parent, name, fd, identity))
            return fd
        def fresh(parent, name):
            os.mkdir(name, mode=0o700, dir_fd=parent)
            child = retain(parent, name)
            row = os.fstat(child)
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (_identity(row) != _identity(named) or stat.S_IMODE(row.st_mode) != 0o700
                    or row.st_uid != uid):
                raise ValueError('runtime_directory_not_private')
            os.fsync(parent)
            return child
        def auth_file(parent, name, expected):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            owned.append(fd)
            identity = _file_identity(os.fstat(fd))
            record = (parent, name, fd, identity, expected)
            _file_auth(*record, uid)
            return record
        def recheck_walks():
            for parent, name, fd, identity in anchors:
                if (_identity(os.fstat(fd)) != identity
                        or _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity):
                    raise ValueError('runtime_directory_reanchored_before_allocation')
            if (_identity(os.fstat(store._directory)) != _identity(os.fstat(store_fd))
                    or _identity(os.fstat(store._lock)) != lock_identity
                    or _identity(os.stat('lock', dir_fd=store_fd, follow_symlinks=False)) != lock_identity
                    or os.fstat(store._lock).st_nlink != 1
                    or os.stat('lock', dir_fd=store_fd, follow_symlinks=False).st_nlink != 1):
                raise ValueError('runtime_store_reanchored_before_allocation')
        try:
            uid = os.geteuid()
            if (os.getuid() != uid or cls is not RuntimeAuthority
                    or type(store) is not PrivateStore or type(run_digest) is not str
                    or re.fullmatch(r'[0-9a-f]{64}', run_digest) is None
                    or not isinstance(store.path, Path) or not store.path.is_absolute()
                    or store.path.resolve(strict=True) != store.path
                    or store.path.name != 'hf-exploratory-' + run_digest
                    or store.path.parent.parts[-2:] != ('.tools', 'hf-exploratory-private')
                    or store._directory is None or store._lock is None):
                raise ValueError('invalid_runtime_store_authority')
            registry, path = _location(run_digest)
            # Validate and retain the entire receipt chain before any allocation.
            fd = retain(None, '/')
            for part in store.path.parent.parts[1:]:
                fd = retain(fd, part)
            parent_fd = fd
            row = os.fstat(parent_fd)
            if stat.S_IMODE(row.st_mode) != 0o700 or row.st_uid != uid:
                raise ValueError('runtime_parent_not_private')
            store_fd = retain(parent_fd, store.path.name)
            store_row = os.fstat(store_fd)
            if (_identity(store_row) != _identity(os.fstat(store._directory))
                    or stat.S_IMODE(store_row.st_mode) != 0o700
                    or store_row.st_uid != uid):
                raise ValueError('runtime_store_reanchored')
            lock_row = os.fstat(store._lock)
            lock_identity = _identity(lock_row)
            named_lock = os.stat('lock', dir_fd=store_fd, follow_symlinks=False)
            if (_identity(named_lock) != lock_identity or not stat.S_ISREG(lock_row.st_mode)
                    or stat.S_IMODE(lock_row.st_mode) != 0o600
                    or lock_row.st_uid != uid or lock_row.st_nlink != 1
                    or named_lock.st_nlink != 1):
                raise ValueError('runtime_store_lock_reanchored')
            fd = retain(None, '/')
            for part in registry.parent.parts[1:]:
                fd = retain(fd, part)
            recheck_walks()
            try:
                os.stat(registry.name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                registry_fd = fresh(fd, registry.name)
                expected = _marker_bytes(uid, registry)
                writer = os.open('registry.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | os.O_NOFOLLOW, 0o600, dir_fd=registry_fd)
                try:
                    row = os.fstat(writer)
                    if (not stat.S_ISREG(row.st_mode) or stat.S_IMODE(row.st_mode) != 0o600
                            or row.st_uid != uid or row.st_nlink != 1 or len(expected) > 8192):
                        raise ValueError('runtime_registry_marker_not_private')
                    view = memoryview(expected)
                    while view:
                        count = os.write(writer, view)
                        if count <= 0:
                            raise OSError('short_runtime_registry_write')
                        view = view[count:]
                    os.fsync(writer)
                finally:
                    os.close(writer)
                os.fsync(registry_fd)
            else:
                registry_fd = retain(fd, registry.name)
            row = os.fstat(registry_fd)
            if (stat.S_IMODE(row.st_mode) != 0o700 or row.st_uid != uid
                    or registry.resolve(strict=True) != registry):
                raise ValueError('runtime_registry_not_private')
            marker = auth_file(registry_fd, 'registry.json', _marker_bytes(uid, registry))
            recheck_walks()
            _file_check(*marker, uid)
            root = fresh(registry_fd, path.name)
            colima = fresh(root, '.colima')
            fresh(colima, '_lima')
            fresh(root, 'docker-config')
            fresh(root, 'runtime-tmp')
            expected = _binding_bytes(uid, run_digest, store.path, registry, path,
                                      _identity(os.fstat(root)))
            if len(expected) > 8192:
                raise ValueError('runtime_binding_exceeds_bound')
            store.write('runtime-binding.json', expected)
            binding = auth_file(store_fd, 'runtime-binding.json', expected)
            authority = object.__new__(cls)
            for name, value in (('path', path), ('_store', store), ('_digest', run_digest),
                                ('_anchors', tuple(anchors)),
                                ('_lock_identity', lock_identity),
                                ('_store_ref', store), ('_receipt_path', store.path),
                                ('_registry', registry), ('_uid', uid),
                                ('_store_fd', store_fd), ('_root_fd', root),
                                ('_lock_fd', store._lock), ('_marker', marker), ('_binding', binding),
                                ('_descriptors', tuple(owned)),
                                ('_closed', False)):
                object.__setattr__(authority, name, value)
            authority.guard()
            return authority
        except BaseException as error:
            for fd in reversed(owned):
                os.close(fd)
            if isinstance(error, (OSError, AttributeError, KeyError, TypeError, ValueError, IndexError, RuntimeError)):
                raise ValueError('runtime_authority_creation_refused') from error
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
                    or type(self._uid) is not int or os.getuid() != os.geteuid()
                    or any(type(fd) is not int for fd in (self._store_fd, self._root_fd, self._lock_fd))
                    or type(self._lock_identity) is not tuple or len(self._lock_identity) != 4
                    or any(type(value) is not int for value in self._lock_identity)
                    or os.geteuid() != self._uid or store is not self._store_ref
                    or type(store) is not PrivateStore or type(self._digest) is not str
                    or re.fullmatch(r'[0-9a-f]{64}', self._digest) is None
                    or not isinstance(store.path, Path) or not store.path.is_absolute()
                    or '..' in store.path.parts
                    or store.path.parent.parts[-2:] != ('.tools', 'hf-exploratory-private')
                    or store.path.name != 'hf-exploratory-' + self._digest
                    or store.path != self._receipt_path or store.path.resolve(strict=True) != store.path
                    or store._directory is None or store._lock is None
                    or store._lock != self._lock_fd
                    or _identity(os.fstat(store._lock)) != self._lock_identity
                    or _identity(os.stat('lock', dir_fd=store._directory,
                                         follow_symlinks=False)) != self._lock_identity):
                raise ValueError('invalid_or_closed_runtime_authority')
            if (os.fstat(store._lock).st_nlink != 1
                    or os.stat('lock', dir_fd=store._directory, follow_symlinks=False).st_nlink != 1):
                raise ValueError('runtime_store_lock_hardlinked')
            registry, root = _location(self._digest)
            if registry != self._registry or self.path != root:
                raise ValueError('runtime_derived_location_changed')
            layout, store_index, registry_index, root_index = _topology(store.path, registry, root)
            if (type(self._anchors) is not tuple or len(self._anchors) != len(layout)
                    or self._store_fd != self._anchors[store_index][2]
                    or self._root_fd != self._anchors[root_index][2]
                    or len({anchor[2] for anchor in self._anchors}) != len(layout)):
                raise ValueError('substituted_runtime_anchors')
            descriptors = (*[anchor[2] for anchor in self._anchors[:registry_index + 1]],
                           self._marker[2],
                           *[anchor[2] for anchor in self._anchors[registry_index + 1:]],
                           self._binding[2])
            if (type(self._descriptors) is not tuple or len(self._descriptors) != len(descriptors)
                    or any(type(fd) is not int for fd in self._descriptors)
                    or len(set(self._descriptors)) != len(descriptors)
                    or self._descriptors != descriptors):
                raise ValueError('substituted_runtime_descriptors')
            def directories_and_lock():
                for anchor, (parent_index, expected_name, private) in zip(self._anchors, layout):
                    parent, name, fd, identity = anchor
                    expected_parent = None if parent_index is None else self._anchors[parent_index][2]
                    if (type(anchor) is not tuple or type(fd) is not int
                            or type(identity) is not tuple or len(identity) != 4
                            or any(type(value) is not int for value in identity)
                            or name != expected_name or parent != expected_parent
                            or _identity(os.fstat(fd)) != identity
                            or _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity
                            or not stat.S_ISDIR(identity[2])):
                        raise ValueError('runtime_namespace_changed')
                    if private and (stat.S_IMODE(identity[2]) != 0o700 or identity[3] != self._uid):
                        raise ValueError('runtime_namespace_not_private')
                if (_identity(os.fstat(store._directory)) != self._anchors[store_index][3]
                        or _identity(os.fstat(store._lock)) != self._lock_identity
                        or _identity(os.stat('lock', dir_fd=self._store_fd,
                                             follow_symlinks=False)) != self._lock_identity
                        or not stat.S_ISREG(self._lock_identity[2])
                        or stat.S_IMODE(self._lock_identity[2]) != 0o600
                        or self._lock_identity[3] != self._uid
                        or os.fstat(store._lock).st_nlink != 1
                        or os.stat('lock', dir_fd=self._store_fd, follow_symlinks=False).st_nlink != 1):
                    raise ValueError('runtime_store_reanchored')
            directories_and_lock()
            expected_marker = _marker_bytes(self._uid, registry)
            expected_binding = _binding_bytes(self._uid, self._digest, store.path, registry, root,
                                               self._anchors[root_index][3])
            for record, parent, name, expected in (
                    (self._marker, self._anchors[registry_index][2], 'registry.json', expected_marker),
                    (self._binding, self._store_fd, 'runtime-binding.json', expected_binding)):
                if (type(record) is not tuple or len(record) != 5 or record[0] != parent
                        or record[1] != name or type(record[2]) is not int or record[4] != expected):
                    raise ValueError('substituted_runtime_auth_file')
                _file_auth(*record, self._uid)
            # A later bounded read cannot leave an earlier authenticated name substituted.
            _file_check(*self._marker, self._uid)
            _file_check(*self._binding, self._uid)
            directories_and_lock()
        except (OSError, AttributeError, KeyError, TypeError, ValueError, IndexError, RuntimeError) as error:
            raise ValueError('runtime_authority_unavailable') from error

    def close(self):
        if not self._closed:
            object.__setattr__(self, '_closed', True)
            for fd in reversed(self._descriptors):
                os.close(fd)

    def write_control(self, name, payload):
        if (type(name) is not str or name != 'kind-config.yaml'
                or type(payload) is not bytes or len(payload) > 65536):
            raise ValueError('invalid_runtime_control')
        self.guard()
        root = self._root_fd
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=root)
        try:
            row = os.fstat(fd)
            if (not stat.S_ISREG(row.st_mode) or row.st_uid != os.geteuid()
                    or row.st_nlink != 1):
                raise ValueError('runtime_control_not_owned_regular_file')
            os.fchmod(fd, 0o600)
            row = os.fstat(fd)
            named = os.stat(name, dir_fd=root, follow_symlinks=False)
            if (stat.S_IMODE(row.st_mode) != 0o600
                    or _identity(row) != _identity(named) or row.st_nlink != 1
                    or named.st_nlink != 1):
                raise ValueError('runtime_control_not_private')
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


@dataclass(frozen=True, slots=True)
class ExploratoryEnvoyPlatformCommand:
    """Fetch the missing AMD64 child of the unchanged accepted Envoy index."""
    authority: RuntimeAuthority

    def __post_init__(self):
        if type(self) is not ExploratoryEnvoyPlatformCommand or type(self.authority) is not RuntimeAuthority:
            raise ValueError('invalid_exploratory_envoy_platform_command')
        self.authority.guard()

    @property
    def argv(self):
        from kil.v3b2_accepted_images import ACCEPTED_IMAGES
        image = next(row for row in ACCEPTED_IMAGES if row.role == 'envoy')
        return ('docker','pull','--platform','linux/amd64',image.requested_image)

    @property
    def timeout_s(self): return 300

    @property
    def mutating(self): return True

    @property
    def stdin(self): return None

    @property
    def env(self):
        return (('DOCKER_CONFIG',str(self.authority.docker_config)),
                ('DOCKER_HOST','unix://'+str(self.authority.colima/'kil-v3-lab/docker.sock')))


@dataclass(frozen=True, slots=True)
class ExploratoryNodeAliasCommand:
    """Finite accepted-config reads and canonical aliases in the owned node."""
    authority: RuntimeAuthority
    identity: object
    role: str
    operation: str
    import_ref: str | None = None

    def __post_init__(self):
        from kil.v3b2_journal import OwnedIdentity
        from kil.hf_exploratory_node_aliases import accepted_image, validate_import_ref
        if (type(self) is not ExploratoryNodeAliasCommand or type(self.authority) is not RuntimeAuthority
                or type(self.identity) is not OwnedIdentity):
            raise ValueError('invalid_exploratory_node_alias_command')
        self.identity.__post_init__(); accepted_image(self.role)
        if (self.identity.node_container_id is None or self.identity.cluster_incarnation_uid is None
                or self.identity.colima_profile != 'kil-v3-lab' or self.identity.kind_cluster != 'kil-v3-lab'
                or self.identity.kubeconfig != str(self.authority.kubeconfig)
                or self.identity.docker_host != 'unix://'+str(self.authority.colima/'kil-v3-lab/docker.sock')
                or type(self.operation) is not str or self.operation not in ('inspect','tag','remove')):
            raise ValueError('node_alias_command_not_current_owned_node')
        if self.operation == 'remove': validate_import_ref(self.import_ref)
        elif self.import_ref is not None: raise ValueError('node_alias_command_has_unexpected_reference')
        self.authority.guard()

    @property
    def argv(self):
        from kil.hf_exploratory_node_aliases import accepted_image, canonical_alias
        image = accepted_image(self.role)
        base = ('docker','exec',self.identity.node_container_id)
        if self.operation == 'inspect':
            return (*base,'/usr/local/bin/crictl','--runtime-endpoint','unix:///run/containerd/containerd.sock',
                    '--image-endpoint','unix:///run/containerd/containerd.sock','--timeout','10s',
                    'inspecti','--quiet','--output','json',image.config_digest)
        ctr = (*base,'/usr/local/bin/ctr','--address','/run/containerd/containerd.sock','--namespace','k8s.io','images')
        return (*ctr,'tag',image.config_digest,canonical_alias(image)) if self.operation == 'tag' else (*ctr,'rm',self.import_ref)

    @property
    def timeout_s(self): return 10

    @property
    def mutating(self): return self.operation != 'inspect'

    @property
    def stdin(self): return None

    @property
    def env(self):
        return (('DOCKER_CONFIG',str(self.authority.docker_config)),('DOCKER_HOST',self.identity.docker_host))
