"""Pure exploratory saved-form binding in a derived native namespace.

The strict no-follow collector and capture/binding schemas remain shared and
unchanged. Only the instance serializer's single generated DNS alias differs.
No commands, recovery, or retained-byte normalization occur here.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import stat

from kil.hf_exploratory_runtime import RuntimeAuthority
from kil import hf_exploratory_runtime as runtime_module
from kil.v3b2_profile_state import (
    MAX_CONFIG, NAME, SIZE, ProfileStateError, _record_identity, _zero_store,
    capture, parse_saved, passwd_home as actual_passwd_home, validate_binding,
    validate_capture,
)


@dataclass(frozen=True)
class ProfilePaths:
    home: Path
    runtime: Path

    def __post_init__(self):
        for path in (self.home, self.runtime):
            if (not isinstance(path, Path) or not path.is_absolute()
                    or '..' in path.parts or path == Path('/')
                    or path.anchor != '/'):
                raise ProfileStateError('exploratory profile authority is invalid')
        compact = (re.fullmatch(r'r[0-9a-f]{16}', self.runtime.name) is not None
                   and self.runtime.parent == runtime_module._registry_parent())
        # Legacy saved evidence remains pure parsing, never live creation/adoption.
        legacy = (re.fullmatch(r'hf-exploratory-runtime-[0-9a-f]{64}', self.runtime.name) is not None
                  and self.runtime.parent.parts[-2:] == ('.tools', 'hf-exploratory-private'))
        if not compact and not legacy:
            raise ProfileStateError('exploratory runtime namespace is invalid')

    @classmethod
    def bind(cls, authority):
        if type(authority) is not RuntimeAuthority:
            raise ProfileStateError('exploratory profile requires exact runtime authority')
        authority.guard()
        return cls(actual_passwd_home(), authority.path)

    @property
    def colima(self):
        return self.runtime / '.colima'

    @property
    def lima(self):
        return self.colima / '_lima'

    @property
    def profile(self):
        return self.colima / 'kil-v3-lab'

    @property
    def instance(self):
        return self.lima / NAME

    @property
    def disk(self):
        return self.lima / '_disks' / NAME

    @property
    def store(self):
        return self.colima / '_store' / (NAME + '.json')

    @property
    def private(self):
        return self.runtime

    @property
    def tmp(self):
        return self.runtime / 'runtime-tmp'

    @property
    def startup(self):
        return self.tmp / (NAME + '.yaml')

    def document(self):
        return {'home': str(self.home), 'runtime': str(self.runtime)}


def _paths(document):
    if (type(document) is not dict or set(document) != {'home', 'runtime'}
            or any(type(v) is not str for v in document.values())):
        raise ProfileStateError('exploratory profile authority document is invalid')
    paths = ProfilePaths(Path(document['home']), Path(document['runtime']))
    if paths.document() != document:
        raise ProfileStateError('exploratory profile authority document is noncanonical')
    return paths


def parse_saved_instance(payload):
    """Validate the exact generated alias without normalizing proof bytes."""
    alias = b'  dnsHosts:\n    host.docker.internal: host.lima.internal\n'
    if type(payload) is not bytes or len(payload) > MAX_CONFIG:
        raise ProfileStateError('saved instance configuration exceeds bound')
    if payload.count(alias) != 1:
        raise ProfileStateError('saved instance requires exact generated DNS alias')
    # This copy is validation-only; hashes and retained captures use the input.
    result = parse_saved(payload.replace(alias, b'  dnsHosts: {}\n', 1))
    result['network']['dnsHosts'] = {'host.docker.internal': 'host.lima.internal'}
    return result


def creation_binding(document, observed):
    paths = _paths(document)
    validate_capture(observed)
    if observed['protected'] is not None:
        raise ProfileStateError('protected VM requires manual recovery')
    if observed['startup'] is not None:
        raise ProfileStateError('startup artifact remains')
    identities = {key: _record_identity(observed[key], 'dir')
                  for key in ('profile', 'instance', 'disk')}
    hashes = {}
    for key, parser in (('profile', parse_saved), ('instance', parse_saved_instance)):
        row = observed[key + '_config']
        identities[key + '_config'] = _record_identity(row, 'file')
        payload = bytes.fromhex(row['hex'])
        parser(payload)
        hashes[key] = sha256(payload).hexdigest()
    disk = observed['data_disk']
    identities['data_disk'] = _record_identity(disk, 'file')
    if disk['size'] != SIZE or disk['format'] != 'raw':
        raise ProfileStateError('data disk differs from pinned capacity')
    root = observed['root_disk']
    identities['root_disk'] = _record_identity(root, 'file')
    if root['size'] != 20 * 1024**3 or root['format'] != 'raw':
        raise ProfileStateError('root disk differs from pinned capacity')
    _record_identity(observed['lock'], 'link')
    if observed['lock']['target'] != str(paths.instance):
        raise ProfileStateError('disk lock names foreign instance')
    identities['lima_config'] = _record_identity(observed['lima_config'], 'file')
    return {'resources': identities, 'config_sha256': hashes,
            'lima_config_sha256': sha256(bytes.fromhex(observed['lima_config']['hex'])).hexdigest(),
            'data_disk_size': SIZE, 'data_disk_format': 'raw', 'lock_target': str(paths.instance)}


def unchanged(document, observed, binding, *, stopped=False):
    paths = _paths(document)
    validate_capture(observed)
    validate_binding(binding)
    candidate = dict(observed)
    if stopped and candidate['lock'] is None:
        # A stopped VM legitimately unlocks its disk. This internal validation
        # probe is not a retained observation or new filesystem authority.
        candidate['lock'] = {'device': 0, 'inode': 0, 'mode': stat.S_IFLNK,
                             'target': str(paths.instance)}
        if candidate['disk'] is not None:
            candidate['disk'] = {**candidate['disk'],
                                 'entries': sorted([*candidate['disk']['entries'], 'in_use_by'])}
    return creation_binding(document, candidate) == binding


def absent(document, observed):
    _paths(document)
    validate_capture(observed)
    return (all(observed[key] is None for key in ('profile', 'instance', 'disk', 'startup'))
            and _zero_store(observed['store']))
