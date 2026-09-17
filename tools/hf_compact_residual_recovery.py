"""Separately approved, fixed-target manual stop of the compact HF residual VM.

One graceful stop at most; preserve retained evidence and resources. Never
resume a rehearsal, retry, force, delete or issue an HF request.
"""
from contextlib import ExitStack, contextmanager
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys


REPOSITORY = Path(__file__).resolve().parents[1]
for _location in (REPOSITORY, REPOSITORY / 'src'):
    if str(_location) not in sys.path:
        sys.path.insert(0, str(_location))

from kil.hf_exploratory_inputs import read_regular, verify_bytes
from kil.hf_exploratory_inputs import ACCEPTED_RUN, TOOL_VERSION_ARGUMENTS
from kil.hf_exploratory_io import PrivateStore, _dependency_snapshot, capture_process
from kil.hf_exploratory_profile import ProfilePaths, capture, creation_binding, unchanged
from kil import hf_exploratory_runtime as runtime_module
from kil.v3b2_profile_state import ProfilePaths as DefaultProfilePaths
from kil.v3b2_profile_state import _parent, _read, passwd_home
from kil.v3b2_colima_inventory import capture_roster, decode_inventory, require_complete, _roster_names
from kil.v3b2_accepted_images import ACCEPTED_MANIFEST_SHA256
from kil.v3b2_controller import CommandResult
from kil.v3b2_proofs import canonical
from kil.hf_exploratory_native import check_source
from tools.hf_exploratory_kind import LabLock


DIGEST = '254877dc1b1462c4e29c068e51ad7286fe430b075bc5044c8b3076d1887ad25d'
HOME = Path('/Users/mistorm')
UID = 501
RUNTIME = HOME / '.kil-hf' / ('r' + DIGEST[:16])
RECEIPT = REPOSITORY / '.tools/hf-exploratory-private' / ('hf-exploratory-' + DIGEST)
RECOVERY = REPOSITORY / '.tools/hf-recovery-private/2026-09-17' / ('manual-stop-' + DIGEST)
TOOLS = Path('/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.tools/bin')
COLIMA = HOME / '.local/bin/colima'
ACCEPTED_MANIFEST = REPOSITORY / 'artifacts/generated/v3b1-local-envoy' / ACCEPTED_RUN / 'manifest.json'
ROOT_ID = (16777232, 615011851, 16832, 501)
MANIFEST_PIN = ('d128fd99fcc32391db27804da8be86c0e62b238343b71c7f44009785cba38ad0', 3979)
SSH_PIN = ('0788dfecc6e2e6d6301a2eca6d9bebe153de450cac6d4657b053f2676a9564e9', 767)
COLIMA_PIN = ('980ad8bf61a4ca370243f4cb41401a61276dcd2c2502bee7b9b86f9250169f34', 15656320)
SOURCE = '7d5c58372040ecf5b7c1fdd9c9d7ea3ddcd06205'
COLIMA_VERSION = b'colima version v0.10.3\ngit commit: 00f6c297e92a82c04a4ab507db0a61435650d7e8\n'
MAXIMUM = 8 * 1024**2


class _Once:
    """Consume one slot before durable intent; failure never restores authority."""
    def __init__(self, store):
        if type(store) is not PrivateStore:
            raise ValueError('recovery_once_store_is_invalid')
        self.store, self.used = store, False

    def send(self, intent, check, dispatch):
        if self.used:
            raise ValueError('recovery_stop_slot_already_consumed')
        self.used = True
        self.store._bound(intent, 1024 * 1024)
        self.store.total += len(intent)
        fd = os.open('manual-stop-intent.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.store._directory)
        try:
            view = memoryview(intent)
            while view:
                written = os.write(fd, view)
                if written <= 0: raise OSError('recovery_short_intent_write')
                view = view[written:]
            identity = _fid(os.fstat(fd))
            def bound():
                if (_fid(os.fstat(fd)) != identity or _fid(os.stat(
                        'manual-stop-intent.json', dir_fd=self.store._directory,
                        follow_symlinks=False)) != identity):
                    raise ValueError('recovery_manual_intent_writer_changed')
            os.fsync(fd)
            self.store._sync_parent()
            bound()
            check()
            bound()
            return dispatch()
        finally:
            os.close(fd)


def _new_store(receipt):
    """Reserve only the fixed new receipt beneath retained private parents."""
    if type(receipt) is not _Files:
        raise ValueError('recovery_new_store_proof_is_invalid')
    expected = REPOSITORY / '.tools/hf-recovery-private/2026-09-17' / ('manual-stop-' + DIGEST)
    if RECOVERY != expected:
        raise ValueError('recovery_new_store_path_is_not_fixed')
    parent = receipt.directory(REPOSITORY)
    current = REPOSITORY
    for name in ('.tools', 'hf-recovery-private', '2026-09-17'):
        current = current / name
        receipt.metadata_guard()
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            pass
        else:
            os.fsync(parent)
        parent = receipt.directory(current, private=True)
    receipt.guard()
    store = PrivateStore(RECOVERY)
    try:
        receipt.directory(RECOVERY, private=True)
        receipt.read(RECOVERY / 'lock', 1, 0o600, UID)
        lock = receipt.files[-1]
        receipt.guard()
        if (lock[2][5] != 0 or _fid(os.fstat(store._lock)) != lock[2]
                or _id(os.fstat(store._directory)) != receipt.directories[RECOVERY][1]):
            raise ValueError('recovery_new_store_binding_changed')
        receipt.metadata_guard()
        return store
    except BaseException:
        store.close()
        raise


def _seal(store):
    with _seal_scope(store) as (digest, _):
        return digest


@contextmanager
def _seal_scope(store):
    """Seal only a new bounded evidence directory, never repair or reseal it."""
    if type(store) is not PrivateStore:
        raise ValueError('recovery_seal_store_is_invalid')
    proof = _Files()
    try:
        store._bound(b'', 1)
        directory = proof.directory(store.path, private=True)
        directory_identity = _fid(os.fstat(directory))
        lock_identity = _fid(os.fstat(store._lock))
        if (not stat.S_ISREG(lock_identity[2]) or stat.S_IMODE(lock_identity[2]) != 0o600
                or lock_identity[3] != UID or lock_identity[4:6] != (1, 0)
                or _fid(os.stat('lock', dir_fd=directory, follow_symlinks=False)) != lock_identity
                or _fid(os.fstat(store._directory)) != directory_identity):
            raise ValueError('recovery_seal_store_binding_changed')

        def roster():
            names = []
            with os.scandir(directory) as entries:
                for entry in entries:
                    if len(names) >= 256 or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', entry.name) is None:
                        raise ValueError('recovery_seal_roster_is_invalid')
                    names.append(entry.name)
            return sorted(names)

        names = roster()
        if 'SHA256SUMS' in names:
            raise ValueError('recovery_seal_already_exists')
        total, lines = 0, []
        for name in names:
            row = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (not stat.S_ISREG(row.st_mode) or stat.S_IMODE(row.st_mode) != 0o600
                    or row.st_uid != UID or row.st_nlink != 1 or row.st_size > MAXIMUM
                    or total + row.st_size > 256 * 1024**2):
                raise ValueError('recovery_seal_file_is_invalid')
            payload = proof.read(store.path / name, MAXIMUM, 0o600, UID)
            if proof.files[-1][2] != _fid(row):
                raise ValueError('recovery_seal_file_changed_during_authentication')
            total += len(payload)
            if total > 256 * 1024**2:
                raise ValueError('recovery_seal_total_bound')
            lines.append(hashlib.sha256(payload).hexdigest().encode('ascii') + b'  ' + name.encode('ascii') + b'\n')
        manifest = b''.join(lines)
        if total + len(manifest) > 256 * 1024**2 or len(names) >= 256:
            raise ValueError('recovery_seal_total_bound')
        proof.guard()
        if roster() != names:
            raise ValueError('recovery_seal_roster_changed')
        proof.metadata_guard()
        if (_fid(os.fstat(directory)) != directory_identity
                or _fid(os.fstat(store._directory)) != directory_identity
                or _fid(os.fstat(store._lock)) != lock_identity):
            raise ValueError('recovery_seal_store_binding_changed')
        digest = store.write('SHA256SUMS', manifest)
        sealed_directory_identity = _fid(os.fstat(directory))
        proof.read(store.path / 'SHA256SUMS', MAXIMUM, 0o600, UID, (digest, len(manifest)))
        proof.guard()
        if roster() != sorted([*names, 'SHA256SUMS']):
            raise ValueError('recovery_seal_roster_changed')
        proof.metadata_guard()
        if (_fid(os.fstat(directory)) != sealed_directory_identity
                or _fid(os.fstat(store._directory)) != sealed_directory_identity
                or _fid(os.fstat(store._lock)) != lock_identity):
            raise ValueError('recovery_seal_store_binding_changed')
        def close_metadata():
            proof.metadata_guard()
            if (_fid(os.fstat(directory)) != sealed_directory_identity
                    or _fid(os.fstat(store._directory)) != sealed_directory_identity
                    or _fid(os.fstat(store._lock)) != lock_identity):
                raise ValueError('recovery_seal_store_binding_changed')
        yield digest, close_metadata
    finally:
        proof.close()


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


def _final_files(receipt, runtime, after_stop=False):
    """Close both retained proofs after every later authentication read."""
    if type(receipt) is not _Files or type(runtime) is not _Files or type(after_stop) is not bool:
        raise ValueError('recovery_final_proof_arguments_are_invalid')
    receipt.guard()
    mutable = (RUNTIME / '.colima' / 'ssh_config',) if after_stop else ()
    runtime.guard(mutable)
    # Content authentication above is complete.  The final closure deliberately
    # performs metadata-only checks so one proof cannot be replaced while the
    # other's retained descriptors are reread.
    receipt.metadata_guard()
    runtime.metadata_guard(mutable)


def _result_bytes(result):
    if type(result) is bytes:
        return result, 0, b''
    if type(result) is not CommandResult:
        raise ValueError('recovery_inventory_acquisition_is_invalid')
    return result.stdout_bytes, result.returncode, result.stderr_bytes


def _inventory(paths, acquire):
    """Bracket one Colima list read with a complete no-follow Lima roster."""
    if type(paths) is not ProfilePaths or not callable(acquire):
        raise ValueError('recovery_inventory_arguments_are_invalid')
    before = capture_roster(paths)
    payload, returncode, stderr = _result_bytes(acquire())
    after = capture_roster(paths)
    try:
        rows = require_complete(decode_inventory(payload, returncode=returncode, stderr=stderr), before, after)
    except (ValueError, TypeError) as error:
        raise ValueError('recovery_inventory_is_incomplete') from error
    return rows


def _fingerprint(path):
    """Commit an existing foreign regular file, or a stably absent pathname."""
    if not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts:
        raise ValueError('recovery_foreign_path_is_invalid')
    try:
        with _parent(path) as parent:
            if parent is None:
                return {'path': str(path), 'present': False, 'identity': None,
                        'byte_count': None, 'sha256': None}
            try:
                before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return {'path': str(path), 'present': False, 'identity': None,
                        'byte_count': None, 'sha256': None}
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_size > MAXIMUM):
                raise ValueError('recovery_foreign_file_is_not_bounded_regular')
            payload = read_regular(path, MAXIMUM)
            after = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            full_identity = _fid(before)
            if full_identity != _fid(after):
                raise ValueError('recovery_foreign_file_changed_during_read')
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith('recovery_'):
            raise
        raise ValueError('recovery_foreign_path_is_unavailable') from error
    return {'path': str(path), 'present': True,
            'identity': dict(zip(('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns'),
                                 (before.st_dev, before.st_ino, before.st_mode, before.st_size,
                                  before.st_mtime_ns, before.st_ctime_ns))),
            'byte_count': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}


def _control_paths(paths):
    if type(paths) is not ProfilePaths:
        raise ValueError('recovery_control_paths_are_invalid')
    docker_meta = paths.runtime / 'docker-config' / 'contexts' / 'meta' / hashlib.sha256(
        b'colima-kil-v3-lab').hexdigest() / 'meta.json'
    return (
        ('profile.yaml', paths.profile / 'colima.yaml'),
        ('instance.yaml', paths.instance / 'colima.yaml'),
        ('lima.yaml', paths.instance / 'lima.yaml'),
        ('colima-ssh.config', paths.colima / 'ssh_config'),
        ('instance-ssh.config', paths.instance / 'ssh.config'),
        ('ha.pid', paths.instance / 'ha.pid'), ('vz.pid', paths.instance / 'vz.pid'),
        ('kind.yaml', paths.runtime / 'kind-config.yaml'), ('docker-meta.json', docker_meta),
        ('ha.stdout.log', paths.instance / 'ha.stdout.log'),
        ('ha.stderr.log', paths.instance / 'ha.stderr.log'),
        ('serialv.log', paths.instance / 'serialv.log'),
    )


def _foreign_metadata(roster):
    """Close only the known default namespace and files, without content reads."""
    _roster_names(roster)
    defaults = DefaultProfilePaths(HOME, RUNTIME)
    targets = (defaults.colima, defaults.lima, defaults.lima / '_config',
               defaults.lima / '_config/networks.yaml', HOME / '.docker',
               HOME / '.docker/config.json', HOME / '.kube', HOME / '.kube/config')
    # Child names come from an earlier bounded complete roster; final closure
    # must not reopen scandir/_read after another scope's metadata check.
    if roster is not None:
        targets += tuple(defaults.lima / child['name'] for child in roster['children'])
    rows = []
    for path in targets:
        with _parent(path) as parent:
            if parent is None:
                rows.append(None)
                continue
            try:
                rows.append(_fid(os.stat(path.name, dir_fd=parent, follow_symlinks=False)))
            except FileNotFoundError:
                rows.append(None)
    return tuple(rows)


def _foreign(native):
    """Re-observe only the inherited default Colima/Docker state, never adopt it."""
    if os.environ.get('KUBECONFIG') is not None:
        raise ValueError('recovery_inherited_kubeconfig_is_not_default')
    if not hasattr(native, 'observe'):
        raise ValueError('recovery_foreign_native_is_invalid')
    defaults = DefaultProfilePaths(HOME, RUNTIME)
    def files():
        networks = _read(defaults.lima / '_config' / 'networks.yaml')
        if networks is not None and 'hex' not in networks:
            raise ValueError('recovery_default_networks_is_not_regular')
        docker = HOME / '.docker'
        return {'default_networks': networks, 'global_docker_config': str(docker),
                'global_docker_directory': _read(docker, directory_only=True),
                'global_docker_file': _fingerprint(docker / 'config.json'),
                'kubeconfig': {'inherited': None, 'files': [_fingerprint(HOME / '.kube' / 'config')]}}
    before = capture_roster(defaults)
    metadata = _foreign_metadata(before)
    first_files = files()
    first = native.observe(('colima', 'list', '--json'), 'global')
    after = capture_roster(defaults)
    try:
        rows = require_complete(decode_inventory(first.stdout_bytes, returncode=first.returncode,
                                                  stderr=first.stderr_bytes), before, after)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError('recovery_foreign_inventory_is_incomplete') from error
    context = native.observe(('docker', 'context', 'show'), 'global').stdout_bytes
    if (not context or len(context) > 4096 or b'\r' in context or not context.endswith(b'\n')
            or context.count(b'\n') != 1):
        raise ValueError('recovery_global_docker_context_is_invalid')
    context_name = context.decode('utf-8', 'strict').strip()
    if not context_name:
        raise ValueError('recovery_global_docker_context_is_invalid')
    final = native.observe(('colima', 'list', '--json'), 'global')
    end = capture_roster(defaults)
    try:
        final_rows = require_complete(decode_inventory(final.stdout_bytes, returncode=final.returncode,
                                                        stderr=final.stderr_bytes), after, end)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError('recovery_foreign_inventory_is_incomplete') from error
    final_files = files()
    if (before != end or rows != final_rows or first_files != final_files
            or _foreign_metadata(before) != metadata):
        raise ValueError('recovery_foreign_state_changed_during_observation')
    return {'foreign_profiles': rows, 'foreign_lima_roster': before,
            'global_docker_context': context_name, **first_files}


def _controls(paths, proof):
    """Retain the finite local controls without treating absence as creation authority."""
    if type(paths) is not ProfilePaths or type(proof) is not _Files:
        raise ValueError('recovery_controls_arguments_are_invalid')
    observed, payloads = {}, {}
    absent = []
    for label, path in _control_paths(paths):
        fingerprint = _fingerprint(path)
        if not fingerprint['present']:
            observed[label], payloads[label] = fingerprint, None
            absent.append((label, path, fingerprint))
            continue
        try:
            row = os.lstat(path)
            if row.st_uid != UID or row.st_size > MAXIMUM:
                raise ValueError('recovery_control_is_not_private_bounded_file')
            if any(getattr(row, key) != value for key, value in fingerprint['identity'].items()):
                raise ValueError('recovery_control_changed_during_authentication')
            payload = proof.read(path, MAXIMUM, stat.S_IMODE(row.st_mode), UID)
            if _fid(os.lstat(path)) != _fid(row) or proof.files[-1][2] != _fid(row):
                raise ValueError('recovery_control_changed_during_authentication')
        except (OSError, RuntimeError, ValueError) as error:
            if isinstance(error, ValueError) and str(error).startswith('recovery_'):
                raise
            raise ValueError('recovery_control_is_unavailable') from error
        if (len(payload) != fingerprint['byte_count']
                or hashlib.sha256(payload).hexdigest() != fingerprint['sha256']):
            raise ValueError('recovery_control_changed_during_authentication')
        observed[label], payloads[label] = fingerprint, bytes(payload)
    proof.guard()
    # Recheck every retained absence after all later control content reads.
    for label, path, original in absent:
        if _fingerprint(path) != original:
            raise ValueError('recovery_absent_control_changed_during_authentication')
    _controls_metadata(paths, observed, proof)
    return observed, payloads


def _controls_metadata(paths, observed, proof):
    """Final no-content closure for transient controls after unrelated reads."""
    proof.metadata_guard()
    for label, path in _control_paths(paths):
        row = observed[label]
        try:
            with _parent(path) as parent:
                current = None
                if parent is not None:
                    try:
                        current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                if row['present']:
                    if current is None or any(getattr(current, key) != value
                                              for key, value in row['identity'].items()):
                        raise ValueError('recovery_control_changed_during_authentication')
                elif current is not None:
                    raise ValueError('recovery_absent_control_changed_during_authentication')
        except (OSError, RuntimeError) as error:
            raise ValueError('recovery_control_parent_changed_during_authentication') from error


def _locator_snapshot(locator):
    """Commit PATH's locator spelling separately from its resolved executable."""
    if not isinstance(locator, Path) or not locator.is_absolute() or '..' in locator.parts:
        raise ValueError('recovery_original_lima_locator_is_invalid')
    try:
        before = locator.lstat()
        resolved = locator.resolve(strict=True)
        row = resolved.lstat()
        if (not stat.S_ISREG(row.st_mode) or row.st_uid != UID or row.st_nlink != 1
                or not row.st_mode & stat.S_IXUSR or row.st_size > 128 * 1024**2):
            raise ValueError('recovery_original_lima_is_not_owner_executable')
        payload = read_regular(resolved, 128 * 1024**2)
        if _fid(locator.lstat()) != _fid(before) or _fid(resolved.lstat()) != _fid(row):
            raise ValueError('recovery_original_lima_changed_during_read')
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith('recovery_'):
            raise
        raise ValueError('recovery_original_lima_locator_is_unavailable') from error
    return {'locator': str(locator), 'locator_identity': _fid(before),
            'resolved': str(resolved), 'resolved_identity': _fid(row),
            'sha256': hashlib.sha256(payload).hexdigest(), 'byte_count': len(payload)}


class _Native:
    """Closed observations and one durable-intent-bound private Colima stop."""
    def __init__(self, receipt, runtime, paths, store):
        if (type(receipt) is not _Files or type(runtime) is not _Files
                or type(paths) is not ProfilePaths or type(store) is not PrivateStore):
            raise ValueError('recovery_native_arguments_are_invalid')
        self.receipt, self.runtime, self.paths, self.store = receipt, runtime, paths, store
        self.after_stop = False
        self.stop_used = False
        self.stop_dispatches = 0
        self.stop_returncode = None
        self.stop_certainty = 'not_dispatched'
        self.observed_status = None
        self.stop_intent = None
        self.stop_proof = None
        self.stop_check = None
        self._account()
        original = os.environ.get('PATH')
        if type(original) is not str or not original:
            raise ValueError('recovery_original_path_is_invalid')
        self.original_path = original
        self._path_components = tuple(original.split(os.pathsep))
        if (not self._path_components or any(not part or not Path(part).is_absolute() or '..' in Path(part).parts
                                            for part in self._path_components)):
            raise ValueError('recovery_original_path_is_invalid')
        self.original_path_sha256 = hashlib.sha256(original.encode('utf-8')).hexdigest()
        manifest = receipt.read(ACCEPTED_MANIFEST, 1024 * 1024, 0o644, UID)
        self._manifest_record = receipt.files[-1]
        verify_bytes(manifest, ACCEPTED_MANIFEST_SHA256, len(manifest))
        try:
            accepted = _json_exact(manifest, 1024 * 1024)['verified_tool_identities']
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('recovery_accepted_manifest_is_invalid') from error
        if type(accepted) is not dict or set(accepted) != set(TOOL_VERSION_ARGUMENTS):
            raise ValueError('recovery_accepted_manifest_tools_are_invalid')
        self.accepted_manifest = manifest
        self.accepted = accepted
        self.dependencies = _dependency_snapshot(TOOLS, accepted)
        self.accepted_files = []
        for name in sorted(TOOL_VERSION_ARGUMENTS):
            payload = runtime.read(TOOLS / name, 128 * 1024**2, 0o755, UID)
            row = accepted[name]
            verify_bytes(payload, row['executable_sha256'], row['byte_size'])
            self.accepted_files.append((name, hashlib.sha256(payload).hexdigest(), len(payload)))
        self.accepted_files = tuple(self.accepted_files)
        self.colima = runtime.read(COLIMA, 128 * 1024**2, 0o755, UID, COLIMA_PIN)
        locator = shutil.which('limactl', path=original)
        if locator is None:
            raise ValueError('recovery_original_lima_is_unavailable')
        self.lima = _locator_snapshot(Path(locator))
        runtime.read(Path(self.lima['resolved']), 128 * 1024**2,
                     stat.S_IMODE(self.lima['resolved_identity'][2]), UID,
                     (self.lima['sha256'], self.lima['byte_count']))
        self._store = self._store_snapshot()
        self._final_guard()
        self._locator_metadata()
        self._dependency_metadata()
        self._account()
        self.receipt.metadata_guard(); self.runtime.metadata_guard(); self._check_store()
        self.sequence = 0

    def _account(self):
        if os.getuid() != UID or os.geteuid() != UID or passwd_home() != HOME:
            raise ValueError('recovery_identity_or_home_changed')

    def _store_snapshot(self):
        self.store._bound(b'', 1)
        if self.store._directory is None or self.store._lock is None:
            raise ValueError('recovery_private_store_is_closed')
        directory, lock = os.fstat(self.store._directory), os.fstat(self.store._lock)
        named_directory = os.lstat(self.store.path)
        named_lock = os.stat('lock', dir_fd=self.store._directory, follow_symlinks=False)
        if (not stat.S_ISDIR(directory.st_mode) or stat.S_IMODE(directory.st_mode) != 0o700
                or directory.st_uid != UID or _id(directory) != _id(named_directory)
                or not stat.S_ISREG(lock.st_mode) or stat.S_IMODE(lock.st_mode) != 0o600
                or lock.st_uid != UID or lock.st_nlink != 1 or lock.st_size != 0
                or _fid(lock) != _fid(named_lock)):
            raise ValueError('recovery_private_store_changed')
        # Retain the path ancestry/name as well as PrivateStore's own descriptor.
        self.runtime.directory(self.store.path, private=True)
        return (_id(directory), _fid(lock))

    def _check_store(self):
        if self._store_snapshot() != self._store:
            raise ValueError('recovery_private_store_changed')

    def _manifest(self):
        payload = self.receipt._retained_bytes(self._manifest_record)
        verify_bytes(payload, ACCEPTED_MANIFEST_SHA256, len(payload))
        if payload != self.accepted_manifest:
            raise ValueError('recovery_accepted_manifest_changed')
        return payload

    def _refresh_lima(self):
        locator = shutil.which('limactl', path=self.original_path)
        if locator is None or _locator_snapshot(Path(locator)) != self.lima:
            raise ValueError('recovery_original_lima_changed')

    def _locator_metadata(self):
        locator = Path(self.lima['locator'])
        resolved = Path(self.lima['resolved'])
        try:
            if (shutil.which('limactl', path=self.original_path) != str(locator)
                    or locator.resolve(strict=True) != resolved
                    or _fid(locator.lstat()) != self.lima['locator_identity']
                    or _fid(resolved.lstat()) != self.lima['resolved_identity']):
                raise ValueError('recovery_original_lima_changed')
        except OSError as error:
            raise ValueError('recovery_original_lima_changed') from error

    def _dependency_metadata(self):
        """Close the exact accepted PATH directory after every content read."""
        try:
            descriptor, _ = self.runtime.directories[TOOLS]
            if (_fid(os.fstat(descriptor)) != self.dependencies[0]
                    or _fid(os.lstat(TOOLS)) != self.dependencies[0]):
                raise ValueError('recovery_accepted_dependency_directory_changed')
        except (OSError, KeyError) as error:
            raise ValueError('recovery_accepted_dependency_directory_changed') from error

    def _final_guard(self, after_stop=False):
        _final_files(self.receipt, self.runtime, after_stop)
        self._check_store()

    def guard(self):
        if type(self.after_stop) is not bool:
            raise ValueError('recovery_native_after_stop_is_invalid')
        after_stop = self.after_stop
        self._account()
        self._check_store()
        self._manifest()
        if _dependency_snapshot(TOOLS, self.accepted) != self.dependencies:
            raise ValueError('recovery_accepted_dependencies_changed')
        # Close all proof content before the final locator content read; the
        # subsequent checks are metadata-only and cannot move that boundary.
        self._final_guard(after_stop)
        self._refresh_lima()
        self._account()
        self.receipt.metadata_guard()
        self.runtime.metadata_guard((RUNTIME / '.colima' / 'ssh_config',) if after_stop else ())
        self._locator_metadata()
        self._check_store()
        self._dependency_metadata()

    @property
    def endpoint(self):
        return 'unix://' + str(self.paths.profile / 'docker.sock')

    def environment_for(self, namespace):
        if namespace not in {'private', 'docker', 'global'}:
            raise ValueError('recovery_native_namespace_is_invalid')
        result = {'HOME': str(HOME), 'PATH': str(TOOLS) + os.pathsep + self.original_path}
        for name in ('LANG', 'LC_ALL'):
            value = os.environ.get(name)
            if value is not None:
                result[name] = value
        if namespace == 'private':
            result.update(COLIMA_HOME=str(self.paths.colima), LIMA_HOME=str(self.paths.lima),
                          DOCKER_CONFIG=str(self.paths.runtime / 'docker-config'), TMPDIR=str(self.paths.tmp))
        elif namespace == 'docker':
            result.update(DOCKER_CONFIG=str(self.paths.runtime / 'docker-config'), TMPDIR=str(self.paths.tmp))
        else:
            result['DOCKER_CONFIG'] = str(HOME / '.docker')
        return result

    def allowed(self, argv, namespace):
        if type(argv) is not tuple or any(type(part) is not str for part in argv):
            return False
        allowed = {
            ('colima', 'version'): {'private', 'global'},
            ('colima', 'list', '--json'): {'private', 'global'},
            ('limactl', '--version'): {'global'},
            ('docker', 'context', 'show'): {'global'},
            ('docker', '--host', self.endpoint, 'ps', '--all', '--quiet', '--no-trunc'): {'docker'},
        }
        return namespace in allowed.get(argv, set())

    def _dispatch(self, argv):
        if argv[0] == 'colima':
            return (str(COLIMA), *argv[1:])
        if argv[0] == 'limactl':
            return (self.lima['resolved'], *argv[1:])
        if argv[0] == 'docker':
            return (str(TOOLS / 'docker'), *argv[1:])
        raise ValueError('recovery_native_argv_is_invalid')

    def acquire(self, argv, namespace, timeout=10):
        stopping = argv == (str(COLIMA), 'stop', '--profile', 'kil-v3-lab') and type(argv) is tuple
        if stopping:
            if self.stop_used:
                raise ValueError('recovery_stop_slot_already_consumed')
            self.stop_used = True
        if not (stopping and namespace == 'private') and not self.allowed(argv, namespace):
            raise ValueError('recovery_native_argv_is_not_allowed')
        if type(timeout) is not int or timeout != (300 if stopping else 10):
            raise ValueError('recovery_native_timeout_is_not_allowed')
        self.guard()
        if stopping:
            self._stop_authentication()
        effective = argv if stopping else self._dispatch(argv)
        environment = self.environment_for(namespace)
        self.sequence += 1
        sequence = self.sequence
        self.store.record('command_intent', {'sequence': sequence, 'argv': list(effective),
                           'logical_argv': list(argv), 'namespace': namespace, 'environment': environment,
                           'timeout_s': timeout, 'stdin_sha256': None, 'maximum': 8 * 1024**2,
                           'cwd': str(REPOSITORY)})
        # record() fsyncs both the journal descriptor and private store directory.
        self.guard()
        if stopping:
            self._stop_authentication()
            commitment = _json_exact(self.stop_intent, 1024 * 1024)
            if environment != commitment['environment']:
                raise ValueError('recovery_manual_stop_environment_changed')
            check_source(REPOSITORY, commitment['reviewed_source'])
            if environment != self.environment_for(namespace):
                raise ValueError('recovery_manual_stop_environment_changed')
            self.stop_check()
        result, out, err = None, None, None
        try:
            if stopping:
                self.stop_dispatches = None
                self.stop_certainty = 'uncertain'
                self.observed_status = None
                try:
                    result = capture_process(effective, environment, None, timeout, 8 * 1024**2, REPOSITORY)
                finally:
                    self.after_stop = True
                self.stop_returncode = result.returncode
                self.stop_dispatches = 1 if result.returncode >= 0 else None
            else:
                result = capture_process(effective, environment, None, timeout, 8 * 1024**2, REPOSITORY)
            out = self.store.write('command-%04d.stdout' % sequence, result.stdout_bytes)
            err = self.store.write('command-%04d.stderr' % sequence, result.stderr_bytes)
            self.store.record('command_terminal', {'sequence': sequence, 'returncode': result.returncode,
                              'stdout_sha256': out, 'stderr_sha256': err,
                              'certainty': 'returned' if result.returncode >= 0 else 'uncertain'})
            if stopping:
                self.stop_certainty = 'returned' if result.returncode == 0 else 'uncertain'
        except BaseException as error:
            try:
                self.store.record('command_terminal', {'sequence': sequence,
                                  'returncode': None if result is None else result.returncode,
                                  'stdout_sha256': out, 'stderr_sha256': err,
                                  'certainty': 'uncertain', 'error_type': type(error).__name__[:128]})
            except BaseException:
                pass  # A failed journal cannot promise durability or replace the first error.
            raise
        return result

    def _stop_authentication(self):
        if (type(self.stop_intent) is not bytes or type(self.stop_proof) is not _Files
                or not callable(self.stop_check)):
            raise ValueError('recovery_manual_stop_authority_is_missing')
        record = self.stop_proof.files[-1]
        if (record[0] != RECOVERY / 'manual-stop-intent.json'
                or self.stop_proof._retained_bytes(record) != self.stop_intent):
            raise ValueError('recovery_manual_stop_intent_changed')
        self.stop_proof.guard()
        commitment = _json_exact(self.stop_intent, 1024 * 1024)
        if (commitment.get('argv') != [str(COLIMA), 'stop', '--profile', 'kil-v3-lab']
                or commitment.get('environment') != self.environment_for('private')
                or commitment.get('max_native_mutations') != 1
                or commitment.get('timeout_s') != 300 or commitment.get('namespace') != 'private'
                or commitment.get('stdin_sha256') is not None or commitment.get('maximum') != MAXIMUM
                or commitment.get('cwd') != str(REPOSITORY)):
            raise ValueError('recovery_manual_stop_commitment_changed')

    def observe(self, argv, namespace):
        result = self.acquire(argv, namespace)
        if result.returncode != 0 or result.stderr_bytes:
            raise ValueError('recovery_native_observation_failed')
        return result


def _sealed_json(files, name):
    if type(files) is not dict or type(files.get(name)) is not bytes:
        raise ValueError('recovery_sealed_receipt_input_is_invalid')
    return _json_exact(files[name], 1024 * 1024)


def _control_exact(observed, label, mode, *, required=True):
    row = observed.get(label)
    if type(row) is not dict or type(row.get('present')) is not bool:
        raise ValueError('recovery_control_observation_is_invalid')
    if not row['present']:
        if required:
            raise ValueError('recovery_required_control_is_missing')
        return
    identity = row.get('identity')
    if (type(identity) is not dict or identity.get('st_mode') != (stat.S_IFREG | mode)):
        raise ValueError('recovery_control_mode_is_invalid')


def _preflight(native, paths, report, original, files, authenticate=True):
    with _preflight_scope(native, paths, report, original, files, authenticate) as (observed, payloads, _):
        return observed, payloads


@contextmanager
def _preflight_scope(native, paths, report, original, files, authenticate=True):
    """Read-only fixed-profile validation; it creates and stops nothing."""
    if type(authenticate) is not bool:
        raise ValueError('recovery_preflight_authentication_is_invalid')
    colima = native.observe(('colima', 'version'), 'private').stdout_bytes
    if colima != COLIMA_VERSION:
        raise ValueError('recovery_colima_version_is_invalid')
    lima = native.observe(('limactl', '--version'), 'global').stdout_bytes
    if lima != b'limactl version 2.2.0\n':
        raise ValueError('recovery_lima_version_is_invalid')
    if type(paths) is not ProfilePaths or type(report) is not dict or type(original) is not dict:
        raise ValueError('recovery_preflight_arguments_are_invalid')
    inventory = _inventory(paths, lambda: native.observe(('colima', 'list', '--json'), 'private'))
    if len(inventory) != 1:
        raise ValueError('recovery_private_inventory_is_not_singleton')
    private = inventory[0]
    if (private.get('name') != 'kil-v3-lab' or private.get('status') not in {'Running', 'Stopped'}
            or private.get('arch') != 'aarch64' or private.get('runtime') != 'docker'
            or private.get('cpus') != 4 or private.get('memory') != 8 * 1024**3
            or private.get('disk') != 60 * 1024**3):
        raise ValueError('recovery_private_inventory_is_not_pinned')
    status = private['status']
    native.observed_status = status
    footprint = _footprint(paths, report, original, status)
    footprint_metadata = _footprint_metadata(paths)
    foreign_original = _sealed_json(files, 'foreign-original.json')
    foreign_metadata = _foreign_metadata(foreign_original['foreign_lima_roster'])
    foreign = _foreign(native)
    if foreign != foreign_original:
        raise ValueError('recovery_foreign_state_changed')
    # These copies are deliberately transient: PID/log controls may disappear
    # during the separately approved stop stage and never become stop authority.
    control_proof = _Files()
    controls, payloads = {}, {}
    try:
        controls, payloads = _controls(paths, control_proof)
        for label in ('profile.yaml', 'instance.yaml', 'lima.yaml'):
            _control_exact(controls, label, 0o644)
        _control_exact(controls, 'kind.yaml', 0o600)
        if payloads['kind.yaml'] != files.get('runtime-kind-config.yaml'):
            raise ValueError('recovery_kind_control_changed')
        _control_exact(controls, 'colima-ssh.config', 0o644, required=status == 'Running')
        if controls['colima-ssh.config']['present'] and not native.after_stop:
            verify_bytes(payloads['colima-ssh.config'], *SSH_PIN)
        if authenticate:
            # These long-lived proof records are the exact immutable controls
            # that remain relevant through a later stopped-state revalidation.
            for label, mode in (('profile.yaml', 0o644), ('instance.yaml', 0o644),
                                ('lima.yaml', 0o644), ('kind.yaml', 0o600)):
                native.runtime.read(dict(_control_paths(paths))[label], MAXIMUM, mode, UID)
            if payloads['kind.yaml'] != files['runtime-kind-config.yaml']:
                raise ValueError('recovery_kind_control_changed')
            ssh = dict(_control_paths(paths))['colima-ssh.config']
            if status == 'Running':
                native.runtime.read(ssh, MAXIMUM, 0o644, UID, SSH_PIN)
            elif controls['colima-ssh.config']['present']:
                native.runtime.read(ssh, MAXIMUM, 0o644, UID, SSH_PIN)
        if status == 'Running':
            endpoint = 'unix://' + str(paths.profile / 'docker.sock')
            docker = native.observe(('docker', '--host', endpoint, 'ps', '--all', '--quiet', '--no-trunc'), 'docker')
            if docker.stdout_bytes != b'':
                raise ValueError('recovery_private_docker_is_not_empty')
        # _footprint itself ends with metadata-only closure of the full saved scope;
        # its second capture never becomes a baseline or lifecycle authority.
        # Every native proof content read follows the footprint/control captures.
        # Close it, then use metadata-only scope checks to avoid reopening a
        # guest/disk-content authentication window.
        native.guard()
        if _footprint_metadata(paths) != footprint_metadata:
            raise ValueError('recovery_footprint_changed_during_preflight')
        _controls_metadata(paths, controls, control_proof)
        if _foreign_metadata(foreign_original['foreign_lima_roster']) != foreign_metadata:
            raise ValueError('recovery_foreign_state_changed_during_preflight')
        native.runtime.metadata_guard((RUNTIME / '.colima' / 'ssh_config',) if native.after_stop else ())
        def close_metadata():
            if _footprint_metadata(paths) != footprint_metadata:
                raise ValueError('recovery_footprint_changed_during_preflight')
            _controls_metadata(paths, controls, control_proof)
            if _foreign_metadata(foreign_original['foreign_lima_roster']) != foreign_metadata:
                raise ValueError('recovery_foreign_state_changed_during_preflight')
        yield ({'status': status, 'private_inventory': inventory, 'footprint': footprint,
                'foreign': foreign, 'controls': controls}, payloads, close_metadata)
    finally:
        control_proof.close()


def _canonical(path):
    if not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts:
        raise ValueError('recovery_path_is_not_absolute_canonical')
    try:
        if path.resolve(strict=True) != path:
            raise ValueError('recovery_path_is_not_absolute_canonical')
    except (OSError, RuntimeError) as error:
        raise ValueError('recovery_path_is_not_absolute_canonical') from error
    return path


def _authority(reviewed_source, execution_approval):
    if type(reviewed_source) is not str or re.fullmatch(r'[0-9a-f]{40}', reviewed_source) is None:
        raise ValueError('recovery_reviewed_source_is_invalid')
    try:
        valid = (type(execution_approval) is str and bool(execution_approval.strip())
                 and len(execution_approval.encode('utf-8', 'strict')) <= 4096)
    except UnicodeError:
        valid = False
    if not valid:
        raise ValueError('recovery_execution_approval_is_invalid')


def _proof_bytes(value):
    payload = canonical(value)
    if len(payload) > 1024 * 1024:
        raise ValueError('recovery_proof_exceeds_bound')
    return payload


def _tool_commitments(native):
    tool_records = {str(record[0]): {'identity': record[2], 'sha256': record[3]}
                    for record in native.runtime.files
                    if record[0] in {COLIMA, Path(native.lima['resolved']),
                                     *(TOOLS / name for name in TOOL_VERSION_ARGUMENTS)}}
    return {'original_path': native.original_path, 'original_path_sha256': native.original_path_sha256,
            'accepted_manifest_pin': (ACCEPTED_MANIFEST_SHA256, len(native.accepted_manifest)),
            'accepted_manifest_identity': native._manifest_record[2],
            'accepted_tools': native.accepted, 'accepted_dependency_snapshot': native.dependencies,
            'tool_proofs': tool_records, 'colima_pin': COLIMA_PIN, 'lima': native.lima}


def _manual_intent(native, files, pre, reviewed_source, execution_approval):
    return _proof_bytes({
        'schema': 'kil.hf-compact-residual-manual-stop-intent.v1',
        'execution_approval': execution_approval, 'reviewed_source': reviewed_source,
        'source_commit': SOURCE, 'run_digest': DIGEST, 'run_id': 'v3b2-' + DIGEST,
        'runtime_root_identity': ROOT_ID,
        'runtime_binding': _sealed_json(files, 'runtime-binding.json'),
        'paths': {**native.paths.document(), 'repository': str(REPOSITORY),
                  'receipt': str(RECEIPT), 'recovery': str(RECOVERY)},
        'receipt_manifest_pin': MANIFEST_PIN,
        'receipt_files': {name: hashlib.sha256(payload).hexdigest() for name, payload in sorted(files.items())},
        'preflight_sha256': hashlib.sha256(_proof_bytes(pre)).hexdigest(),
        'controls': pre['controls'], 'argv': [str(COLIMA), 'stop', '--profile', 'kil-v3-lab'],
        'environment': native.environment_for('private'), 'namespace': 'private',
        'timeout_s': 300, 'stdin_sha256': None, 'maximum': MAXIMUM, 'cwd': str(REPOSITORY),
        'account': {'uid': UID, 'effective_uid': UID, 'home': str(HOME)},
        **_tool_commitments(native),
        'max_native_mutations': 1,
    })


def _save_observation(store, prefix, observed, payloads):
    store.write(prefix + '-observations.json', _proof_bytes(observed))
    for label, payload in payloads.items():
        if payload is not None:
            store.write(prefix + '-' + label, payload)


def recover(reviewed_source, execution_approval):
    """One fixed approved graceful stop; no retries, discovery or cleanup."""
    _authority(reviewed_source, execution_approval)
    check_source(REPOSITORY, reviewed_source)
    with ExitStack() as lifetime:
        lab = lifetime.enter_context(LabLock(REPOSITORY))
        receipt = _Files(); lifetime.callback(receipt.close)
        receipt.read(lab.path / 'profile.lock', 1024 * 1024, 0o600, UID)
        lab_record = receipt.files[-1]
        if _fid(os.fstat(lab.lock)) != lab_record[2]:
            raise ValueError('recovery_lab_lock_descriptor_changed')
        runtime, files, paths, report, original = _retained(receipt)
        lifetime.callback(runtime.close)
        store = _new_store(receipt); lifetime.callback(store.close)
        native = None
        outcome = {'schema': 'kil.hf-compact-residual-recovery-outcome.v1',
                   'reviewed_source': reviewed_source, 'execution_approval': execution_approval,
                   'run_id': 'v3b2-' + DIGEST, 'run_digest': DIGEST, 'source_commit': SOURCE,
                   'receipt_path': str(RECEIPT), 'recovery_path': str(RECOVERY),
                   'runtime_root_identity': ROOT_ID,
                   'runtime_binding': _sealed_json(files, 'runtime-binding.json'),
                   'receipt_manifest_pin': MANIFEST_PIN,
                   'receipt_files': {name: hashlib.sha256(payload).hexdigest() for name, payload in sorted(files.items())},
                   'outcome': 'preflight_refused', 'stop_dispatches': 0, 'returncode': None,
                   'command_certainty': 'not_dispatched', 'observed_status': None,
                   'preservation': False, 'hf_request_intents': 0, 'hf_request_attempts': 0,
                   'exceptions': []}

        def status():
            if native is not None:
                outcome.update(stop_dispatches=native.stop_dispatches,
                               returncode=native.stop_returncode,
                               command_certainty=native.stop_certainty,
                               observed_status=native.observed_status)

        def exception(error):
            outcome['exceptions'].append({'type': type(error).__name__[:128], 'message': str(error)[:4096]})

        def close_metadata(observation_close):
            # No directory listings or content reads after this boundary.
            if os.environ.get('KUBECONFIG') is not None:
                raise ValueError('recovery_inherited_kubeconfig_is_not_default')
            native._account()
            native._locator_metadata()
            native._dependency_metadata()
            native._check_store()
            lab.guard()
            if _fid(os.fstat(lab.lock)) != lab_record[2]:
                raise ValueError('recovery_lab_lock_descriptor_changed')
            observation_close()
            receipt.metadata_guard()
            runtime.metadata_guard((RUNTIME / '.colima/ssh_config',) if native.after_stop else ())
            if native.stop_proof is not None: native.stop_proof.metadata_guard()

        def authenticate(observation_close):
            native.guard()
            if native.stop_proof is not None: native._stop_authentication()
            check_source(REPOSITORY, reviewed_source)
            close_metadata(observation_close)

        def finish(observation_close=None):
            status()
            if observation_close is not None: authenticate(observation_close)
            # The sealed record is provisional until its seal and all retained
            # scopes close below. A returned failure never promotes this record.
            store.write('outcome.json', _proof_bytes({**outcome, 'final_closure_pending': True}))
            with _seal_scope(store) as (digest, seal_close):
                if observation_close is not None: authenticate(observation_close)
                seal_close()
                if observation_close is not None: close_metadata(observation_close)
                outcome.update(seal_sha256=digest, seal_verified=True)
            return outcome

        try:
            native = _Native(receipt, runtime, paths, store)
            store.write('native-proof.json', _proof_bytes(_tool_commitments(native)))
            pre, pre_payloads = _preflight(native, paths, report, original, files)
            outcome['observed_status'] = pre['status']
            _save_observation(store, 'pre', pre, pre_payloads)
            if pre['status'] == 'Stopped':
                with _preflight_scope(native, paths, report, original, files, False) as (again, payloads, close):
                    if (again, payloads) != (pre, pre_payloads):
                        raise ValueError('recovery_preflight_commitment_changed')
                    outcome.update(outcome='already_stopped_observed', preservation=True)
                    return finish(close)

            native.stop_intent = _manual_intent(native, files, pre, reviewed_source, execution_approval)
            with ExitStack() as handoff:
                def recheck():
                    native.stop_proof = _Files(); lifetime.callback(native.stop_proof.close)
                    native.stop_proof.read(RECOVERY / 'manual-stop-intent.json', 1024 * 1024, 0o600, UID,
                                          (hashlib.sha256(native.stop_intent).hexdigest(), len(native.stop_intent)))
                    again, payloads, close = handoff.enter_context(
                        _preflight_scope(native, paths, report, original, files, False))
                    if (again, payloads) != (pre, pre_payloads):
                        raise ValueError('recovery_preflight_commitment_changed')
                    native.stop_check = lambda: close_metadata(close)
                    authenticate(close)
                try:
                    _Once(store).send(native.stop_intent, recheck,
                                      lambda: native.acquire((str(COLIMA), 'stop', '--profile', 'kil-v3-lab'),
                                                             'private', 300))
                except Exception as error:
                    exception(error)
                    if not native.after_stop: raise
            status()
            outcome['outcome'] = ('postverification_inconclusive' if native.stop_certainty == 'returned'
                                  else 'command_uncertain')
            with _preflight_scope(native, paths, report, original, files, False) as (post, payloads, close):
                outcome['observed_status'] = post['status']
                _save_observation(store, 'post', post, payloads)
                if post['status'] != 'Stopped':
                    raise ValueError('recovery_post_status_is_not_stopped')
                outcome['preservation'] = True
                if native.stop_certainty == 'returned': outcome['outcome'] = 'graceful_stop_confirmed'
                return finish(close)
        except Exception as error:
            exception(error)
            status()
            outcome['preservation'] = False
            outcome['outcome'] = ('preflight_refused' if native is None or not native.after_stop else
                                  'command_uncertain' if native.stop_certainty != 'returned' else
                                  'postverification_inconclusive')
            if (RECOVERY / 'SHA256SUMS').exists():
                outcome['seal_verified'] = False
                return outcome
            try:
                return finish()
            except Exception as sealing_error:
                exception(sealing_error)
                outcome['seal_verified'] = False
                return outcome


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

    def metadata_guard(self, mutable=()):
        """Close names/descriptors after all retained content reads."""
        try:
            if self.closed:
                raise ValueError('recovery_file_proof_is_closed')
            mutable_paths = frozenset(mutable)
            self._check_directories()
            for record in self.files:
                if record[0] not in mutable_paths:
                    self._check_file(record)
            self._check_directories()
        except (OSError, RuntimeError) as error:
            raise ValueError('recovery_file_proof_unavailable') from error

    def close(self):
        if not self.closed:
            self.closed = True
            self._stack.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--reviewed-source', required=True)
    parser.add_argument('--execution-approval', required=True)
    parser.add_argument('--execute-approved-stop', action='store_true', required=True)
    arguments = parser.parse_args(argv)
    try:
        outcome = recover(arguments.reviewed_source, arguments.execution_approval)
    except Exception as error:
        outcome = {'outcome': 'preflight_refused', 'stop_dispatches': 0, 'preservation': False,
                   'seal_verified': False, 'error_type': type(error).__name__[:128], 'error': str(error)[:4096]}
    print(canonical(outcome).decode('utf-8'), end='')
    return 0 if outcome['outcome'] in {'already_stopped_observed', 'graceful_stop_confirmed'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
