"""Fixed-target retained-file proof for the manual HF residual stop path.

This module deliberately has no command entry point.  It only retains and
re-authenticates fixed local files before a later, separately approved stage.
"""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


REPOSITORY = Path(__file__).resolve().parents[1]
for _location in (REPOSITORY, REPOSITORY / 'src'):
    if str(_location) not in sys.path:
        sys.path.insert(0, str(_location))

from kil.hf_exploratory_inputs import read_regular, verify_bytes
from kil.hf_exploratory_profile import ProfilePaths, capture, creation_binding, unchanged
from kil import hf_exploratory_runtime as runtime_module
from kil.v3b2_profile_state import _read, passwd_home
from kil.v3b2_proofs import canonical


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


def _receipt(proof):
    """Authenticate the complete, fixed retained receipt without repairing it."""
    if type(proof) is not _Files:
        raise ValueError('recovery_receipt_proof_is_invalid')
    proof.directory(RECEIPT.parent, private=True)
    proof.directory(RECEIPT, private=True)
    manifest = proof.read(RECEIPT / 'SHA256SUMS', 8192, 0o600, UID, MANIFEST_PIN)
    rows = manifest.splitlines(keepends=True)
    if len(rows) != 46:
        raise ValueError('recovery_receipt_manifest_count_is_invalid')
    expected = {}
    expression = re.compile(rb'([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._-]{0,127})\n\Z')
    for row in rows:
        matched = expression.fullmatch(row)
        if matched is None:
            raise ValueError('recovery_receipt_manifest_line_is_invalid')
        digest, raw_name = matched.groups()
        name = raw_name.decode('ascii')
        if name == 'SHA256SUMS' or name in expected:
            raise ValueError('recovery_receipt_manifest_name_is_invalid')
        expected[name] = digest.decode('ascii')
    if len(expected) != 46:
        raise ValueError('recovery_receipt_manifest_names_are_invalid')
    result = {}
    for name, digest in sorted(expected.items()):
        payload = proof.read(RECEIPT / name, MAXIMUM, 0o600, UID)
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError('recovery_receipt_file_digest_is_invalid')
        result[name] = payload
    proof.guard()
    return result


def _json_exact(payload, maximum):
    """Decode only the repository's canonical JSON bytes, rejecting duplicates."""
    if type(payload) is not bytes or len(payload) > maximum:
        raise ValueError('recovery_json_exceeds_bound')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('recovery_json_has_duplicate_key')
            result[key] = value
        return result
    try:
        value = json.loads(payload, object_pairs_hook=unique)
    except (UnicodeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError('recovery_json_is_invalid') from error
    if canonical(value) != payload:
        raise ValueError('recovery_json_is_not_canonical')
    return value


def _owned(path, *, directory=False, disk=False):
    row = _read(path, directory_only=directory, disk=disk)
    if row is None or os.lstat(path).st_uid != UID:
        raise ValueError('recovery_saved_resource_is_not_owned')
    return row


def _expect(value, expected, error):
    if value != expected:
        raise ValueError(error)


def _leftovers(paths):
    locations = (paths.runtime, paths.colima, paths.lima, paths.runtime / 'docker-config', paths.tmp)
    result = []
    for path in locations:
        row = _owned(path, directory=True)
        result.append({'runtime_path': str(path), 'observation': row})
    return {'schema': 'kil.hf-exploratory-runtime-leftovers.v1', 'observed_only': True,
            'partial': True, 'scope': 'named namespace directories only',
            'runtime_path': str(paths.runtime), 'directories': result}


def _same_leftover_identities(saved, actual):
    if (type(saved) is not dict or set(saved) != {'schema', 'observed_only', 'partial', 'scope',
                                                   'runtime_path', 'directories'}
            or saved['schema'] != 'kil.hf-exploratory-runtime-leftovers.v1'
            or saved['observed_only'] is not True or saved['partial'] is not True
            or saved['scope'] != 'named namespace directories only'
            or saved['runtime_path'] != actual['runtime_path']
            or type(saved['directories']) is not list or len(saved['directories']) != 5):
        return False
    for old, new in zip(saved['directories'], actual['directories']):
        if (type(old) is not dict or set(old) != {'runtime_path', 'observation'}
                or old['runtime_path'] != new['runtime_path'] or type(old['observation']) is not dict
                or set(old['observation']) != {'device', 'inode', 'mode', 'entries'}
                or any(type(old['observation'][key]) is not int or old['observation'][key] < 0
                       for key in ('device', 'inode', 'mode'))
                or type(old['observation']['entries']) is not list):
            return False
        if {key: old['observation'].get(key) for key in ('device', 'inode', 'mode')} != {
                key: new['observation'][key] for key in ('device', 'inode', 'mode')}:
            return False
    return True


def _footprint_metadata(paths):
    """Bounded no-content metadata for the complete retained footprint."""
    targets = (
        ('profile', paths.profile, False), ('instance', paths.instance, False),
        ('disk_directory', paths.disk, False), ('profile_config', paths.profile / 'colima.yaml', False),
        ('instance_config', paths.instance / 'colima.yaml', False),
        ('lima_config', paths.instance / 'lima.yaml', False), ('data_disk', paths.disk / 'datadisk', True),
        ('root_disk', paths.instance / 'disk', True), ('store', paths.store, False),
        ('startup', paths.startup, False), ('protected', paths.instance / 'protected', False),
        ('lock', paths.disk / 'in_use_by', False), ('runtime', paths.runtime, False),
        ('colima', paths.colima, False), ('lima', paths.lima, False),
        ('docker_config', paths.runtime / 'docker-config', False), ('runtime_tmp', paths.tmp, False),
    )
    result = []
    for name, path, disk in targets:
        try:
            row = os.lstat(path)
        except FileNotFoundError:
            result.append((name, None))
            continue
        if row.st_uid != UID:
            raise ValueError('recovery_footprint_metadata_not_owned')
        identity = (row.st_dev, row.st_ino, row.st_mode, row.st_uid, row.st_nlink, row.st_size)
        result.append((name, identity if disk else identity + (row.st_mtime_ns, row.st_ctime_ns)))
    return tuple(result)


def _retained(proof):
    """Bind the receipt, derived private runtime, and exact saved native state."""
    if type(proof) is not _Files:
        raise ValueError('recovery_retained_proof_is_invalid')
    runtime = _Files()
    try:
        if os.getuid() != UID or os.geteuid() != UID or passwd_home() != HOME:
            raise ValueError('recovery_identity_or_home_changed')
        if runtime_module._registry_parent() != RUNTIME.parent:
            raise ValueError('recovery_runtime_registry_changed')
        proof.directory(RECEIPT.parent, private=True)
        proof.directory(RECEIPT, private=True)
        files = _receipt(proof)
        root = os.lstat(RUNTIME)
        if not stat.S_ISDIR(root.st_mode) or _id(root) != ROOT_ID:
            raise ValueError('recovery_runtime_root_identity_changed')
        for path in (RUNTIME.parent, RUNTIME, RUNTIME / '.colima', RUNTIME / '.colima/_lima',
                     RUNTIME / 'docker-config', RUNTIME / 'runtime-tmp'):
            runtime.directory(path, private=True)
        marker = runtime.read(RUNTIME.parent / 'registry.json', 8192, 0o600, UID)
        expected_marker = canonical({'schema': 'kil.hf-exploratory-runtime-registry.v1',
                                     'uid': UID, 'runtime_parent': str(RUNTIME.parent)})
        _expect(marker, expected_marker, 'recovery_runtime_marker_changed')
        binding = _json_exact(files['runtime-binding.json'], 8192)
        expected_binding = {'schema': 'kil.hf-exploratory-runtime-binding.v1', 'uid': UID,
            'run_digest': DIGEST, 'run_id': 'v3b2-' + DIGEST, 'receipt_path': str(RECEIPT),
            'registry_path': str(RUNTIME.parent), 'runtime_path': str(RUNTIME),
            'runtime_identity': dict(zip(('device', 'inode', 'mode', 'uid'), ROOT_ID))}
        if files['runtime-binding.json'] != canonical(expected_binding):
            raise ValueError('recovery_runtime_binding_changed')
        paths = ProfilePaths(HOME, RUNTIME)
        for path, directory in ((paths.profile, True), (paths.instance, True), (paths.disk, True),
                                (paths.profile / 'colima.yaml', False), (paths.instance / 'colima.yaml', False),
                                (paths.instance / 'lima.yaml', False), (paths.disk / 'datadisk', False),
                                (paths.instance / 'disk', False)):
            _owned(path, directory=directory, disk=path in {paths.disk / 'datadisk', paths.instance / 'disk'})
        original = _json_exact(files['profile-created.json'], 1024 * 1024)
        profile_binding = creation_binding(paths.document(), original)
        leftovers = _json_exact(files['runtime-leftovers.json'], 1024 * 1024)
        if not _same_leftover_identities(leftovers, _leftovers(paths)):
            raise ValueError('recovery_runtime_leftovers_changed')
        report = _json_exact(files['report.json'], 1024 * 1024)
        expected_report = {
            'schema_version': 'kil.hf-exploratory-report.v1', 'run_id': 'v3b2-' + DIGEST,
            'source_commit': SOURCE, 'mode': 'rehearsal', 'status': 'inconclusive',
            'manual_recovery': True, 'request_intent_count': 0, 'request_attempt_count': 0,
            'joined_results': [], 'paths': {'actual_default_home': str(HOME), 'receipt': str(RECEIPT),
                                             'runtime': str(RUNTIME)},
        }
        for key, value in expected_report.items():
            if report.get(key) != value or type(report.get(key)) is not type(value):
                raise ValueError('recovery_report_premise_changed')
        if (type(report.get('profile_resources')) is not dict
                or report['profile_resources'].get('actual_creation_bound') is not True
                or report.get('profile_binding') != profile_binding
                or report.get('runtime_leftovers') != leftovers):
            raise ValueError('recovery_report_binding_changed')
        proof.guard()
        runtime.guard()
        return runtime, files, paths, report, original
    except BaseException:
        runtime.close()
        raise


def _footprint(paths, report, original, status):
    """Re-observe exactly the saved local footprint; this grants no lifecycle power."""
    if type(paths) is not ProfilePaths or type(report) is not dict or status not in {'Running', 'Stopped'}:
        raise ValueError('recovery_footprint_arguments_are_invalid')
    metadata = _footprint_metadata(paths)
    resources = ((paths.profile, True), (paths.instance, True), (paths.disk, True),
                 (paths.profile / 'colima.yaml', False), (paths.instance / 'colima.yaml', False),
                 (paths.instance / 'lima.yaml', False), (paths.disk / 'datadisk', False),
                 (paths.instance / 'disk', False))
    for path, directory in resources:
        _owned(path, directory=directory, disk=path in {paths.disk / 'datadisk', paths.instance / 'disk'})
    first, observed = capture(paths), capture(paths)
    if first != observed:
        raise ValueError('recovery_footprint_changed_during_capture')
    for path, directory in resources:
        _owned(path, directory=directory, disk=path in {paths.disk / 'datadisk', paths.instance / 'disk'})
    binding = report.get('profile_binding')
    if (binding != creation_binding(paths.document(), original)
            or unchanged(paths.document(), observed, binding, stopped=(status == 'Stopped')) is not True):
        raise ValueError('recovery_saved_profile_binding_changed')
    if status == 'Running':
        for key in ('profile', 'instance', 'disk', 'store', 'lock'):
            _expect(observed[key], original[key], 'recovery_running_footprint_changed')
    else:
        allowed = {'profile': {'docker.sock', 'containerd.sock'},
                   'instance': {'ha.pid', 'ha.sock', 'ssh.sock', 'vz.pid'},
                   'disk': {'in_use_by'}}
        for key, removable in allowed.items():
            before, after = set(original[key]['entries']), set(observed[key]['entries'])
            if not after <= before or before - after - removable:
                raise ValueError('recovery_stopped_footprint_changed')
        _expect(observed['store'], original['store'], 'recovery_store_changed')
    rosters = ((paths.runtime, {'.colima', 'docker-config', 'kind-config.yaml', 'runtime-tmp'}, set()),
               (paths.colima, {'_lima', '_store', 'kil-v3-lab', 'ssh_config'},
                {'ssh_config'} if status == 'Stopped' else set()),
               (paths.lima, {'_config', '_disks', '_networks', 'colima-kil-v3-lab'}, set()),
               (paths.runtime / 'docker-config', {'contexts'}, set()), (paths.tmp, set(), set()))
    def namespace_snapshot():
        result = []
        for path, expected, missing in rosters:
            row = _owned(path, directory=True)
            entries = set(row['entries'])
            if entries - expected or expected - entries - missing:
                raise ValueError('recovery_runtime_namespace_roster_changed')
            result.append(row)
        return tuple(result)
    namespace_snapshot()
    # A complete bounded final observation brackets every resource and each
    # named namespace directory. It never becomes a new saved baseline.
    for path, directory in resources:
        _owned(path, directory=directory, disk=path in {paths.disk / 'datadisk', paths.instance / 'disk'})
    final = capture(paths)
    if final != observed:
        raise ValueError('recovery_footprint_changed_after_final_authentication')
    namespaces = namespace_snapshot()
    for path, directory in resources:
        _owned(path, directory=directory, disk=path in {paths.disk / 'datadisk', paths.instance / 'disk'})
    if (capture(paths) != final or namespace_snapshot() != namespaces
            or _footprint_metadata(paths) != metadata):
        raise ValueError('recovery_footprint_changed_after_final_authentication')
    return observed


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
