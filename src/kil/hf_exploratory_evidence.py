"""Finite immutable observations of one derived runtime; not admission or cleanup."""
from hashlib import sha256
import os

from kil.hf_exploratory_io import PrivateStore
from kil.hf_exploratory_runtime import RuntimeAuthority
from kil.v3b2_profile_state import _read
from kil.v3b2_proofs import canonical


def _binding(store, authority):
    if type(store) is not PrivateStore or type(authority) is not RuntimeAuthority:
        raise ValueError('invalid_runtime_observation_authority')
    authority.guard()
    if authority._store is not store or authority._store.path != store.path:
        raise ValueError('runtime_observation_receipt_mismatch')


def _files(authority):
    return (
        (authority.kind_config, 'runtime-kind-config.yaml'),
        (authority.kubeconfig, 'runtime-kubeconfig'),
        (authority.colima / 'kil-v3-lab' / 'colima.yaml', 'runtime-profile-colima.yaml'),
        (authority.lima / 'colima-kil-v3-lab' / 'colima.yaml', 'runtime-instance-colima.yaml'),
        (authority.lima / 'colima-kil-v3-lab' / 'lima.yaml', 'runtime-lima.yaml'),
        (authority.docker_config / 'config.json', 'runtime-docker-config.json'),
        (authority.docker_config / 'contexts' / 'meta' /
         sha256(b'colima-kil-v3-lab').hexdigest() / 'meta.json', 'runtime-docker-context-meta.json'),
    )


def _capture_files(store, authority):
    _binding(store, authority)
    observations = []
    for path, retained in _files(authority):
        row = _read(path)
        if row is not None and 'hex' not in row:
            raise ValueError('runtime_snapshot_requires_regular_file')
        observations.append((path, retained, row))
    _binding(store, authority)
    return observations


def snapshot_runtime(store, authority):
    """Retain original bytes of seven fixed inputs after stable double capture.

    Failed writes remain visible and consume the store's bounded quota. The caller
    must not proceed to native teardown after any capture or persistence failure.
    """
    _binding(store, authority)
    # Refuse even an earlier partial capture before extending its immutable set.
    for name in ('runtime-observations.json', *(name for _, name in _files(authority))):
        try:
            os.stat(name, dir_fd=store._directory, follow_symlinks=False)
        except FileNotFoundError:
            continue
        raise FileExistsError('runtime_snapshot_already_retained: ' + name)
    observations = _capture_files(store, authority)
    if observations != _capture_files(store, authority):
        raise ValueError('runtime_snapshot_changed_during_capture')
    files = []
    for path, retained, observation in observations:
        row = {'runtime_path': str(path), 'presence': 'absent', 'identity': None,
               'raw_sha256': None, 'byte_count': None, 'retained_file': None}
        if observation is not None:
            payload = bytes.fromhex(observation['hex'])
            _binding(store, authority)
            digest = store.write(retained, payload)
            _binding(store, authority)
            row.update(presence='present',
                       identity={key: observation[key] for key in ('device', 'inode', 'mode')},
                       raw_sha256=digest, byte_count=len(payload), retained_file=retained)
        files.append(row)
    ledger = {'schema': 'kil.hf-exploratory-runtime-observations.v1',
              'observed_only': True, 'runtime_path': str(authority.path),
              'receipt_path': str(store.path), 'files': files}
    _binding(store, authority)
    store.write('runtime-observations.json', canonical(ledger))
    _binding(store, authority)
    return ledger


def _capture_directories(authority):
    if type(authority) is not RuntimeAuthority:
        raise ValueError('invalid_runtime_leftover_authority')
    authority.guard()
    observations = [{'runtime_path': str(path), 'observation': _read(path, directory_only=True)}
                    for path in (authority.path, authority.colima, authority.lima,
                                 authority.docker_config, authority.tmp)]
    authority.guard()
    return observations


def observe_runtime_leftovers(authority):
    """Report five stable, bounded rosters only; never walk or erase children."""
    observations = _capture_directories(authority)
    if observations != _capture_directories(authority):
        raise ValueError('runtime_leftovers_changed_during_observation')
    return {'schema': 'kil.hf-exploratory-runtime-leftovers.v1',
            'observed_only': True, 'partial': True,
            'scope': 'named namespace directories only',
            'runtime_path': str(authority.path), 'directories': observations}
