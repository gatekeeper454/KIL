"""Exact, no-follow Colima 0.10.3 / Lima 2.2.0 private profile state.

This module does not execute commands. Filesystem observations are retained as
raw proof inputs; pure validators bind identities before subsequent mutations.
See Colima cmd/start.go, util/yamlutil/yaml.go, config/profile.go and Lima
pkg/store/disk.go at the pinned tags for paths, saved values and disk format.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import re
import stat

NAME = 'colima-kil-v3-lab'
SIZE = 60 * 1024**3
MAX_CONFIG = 64 * 1024


class ProfileStateError(ValueError):
    pass


def passwd_home() -> Path:
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    if not home.is_absolute() or '..' in home.parts or home == Path('/'):
        raise ProfileStateError('passwd home is invalid')
    return home


@dataclass(frozen=True)
class ProfilePaths:
    home: Path
    private: Path

    def __post_init__(self):
        for path in (self.home, self.private):
            if not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts or path == Path('/'):
                raise ProfileStateError('profile authority is invalid')

    @classmethod
    def bind(cls, private):
        return cls(passwd_home(), private)

    @property
    def colima(self):
        return self.home / '.colima'

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
    def tmp(self):
        return self.private / 'runtime-tmp'

    @property
    def startup(self):
        return self.tmp / (NAME + '.yaml')

    def document(self):
        return {'home': str(self.home), 'private': str(self.private)}


def _paths(document):
    if type(document) is not dict or set(document) != {'home', 'private'} or any(type(v) is not str for v in document.values()):
        raise ProfileStateError('profile authority document is invalid')
    return ProfilePaths(Path(document['home']), Path(document['private']))


@contextmanager
def _parent(path):
    """Walk each ancestor with openat/O_NOFOLLOW; never resolve a symlink."""
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    opened, anchors = [fd], []
    missing = None
    try:
        for part in path.parts[1:-1]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                missing = (fd, part)
                break
            anchors.append((fd, part, _identity(os.fstat(child))))
            opened.append(child)
            fd = child
        yield None if missing else fd
        for parent_fd, part, identity in anchors:
            if _identity(os.stat(part, dir_fd=parent_fd, follow_symlinks=False)) != identity:
                raise ProfileStateError('profile ancestor changed during observation')
        if missing:
            try:
                os.stat(missing[1], dir_fd=missing[0], follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ProfileStateError('missing profile ancestor appeared during observation')
    except OSError as error:
        raise ProfileStateError('unsafe or unreadable profile parent') from error
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)


def _identity(row):
    return {'device': row.st_dev, 'inode': row.st_ino, 'mode': row.st_mode}


def _require_raw_disk_probe(sector):
    """Reject pinned go-qcow2reader v0.7.1 container signatures before raw.

    qcow2reader.go tries QCOW2, VMDK, VHDX, VDI, Parallels, VPC and ASIF
    before falling back to raw. image/stub/stub.go probes the first 512 bytes;
    none of these pinned probes inspect a footer. Matching signatures remain
    unsupported even when their subsequent metadata would be malformed.
    This classifies the container only, not the guest filesystem's integrity.
    """
    if type(sector) is not bytes or len(sector) != 512:
        raise ProfileStateError('disk format probe is truncated or unavailable')
    prefixes = (b'QFI\xfb', b'# Disk DescriptorFile', b'KDMV', b'COWD',
                b'vhdxfile', b'WithoutFreeSpace', b'WithouFreSpacExt', b'conectix', b'shdw')
    if sector.startswith(prefixes) or int.from_bytes(sector[64:68], 'little') == 0xBEDA107F:
        raise ProfileStateError('unsupported non-raw disk format requires manual recovery')


def _read(path, *, disk=False, lock=False, directory_only=False):
    with _parent(path) as parent:
        if parent is None:
            return None
        try:
            row = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return None
        result = _identity(row)
        if directory_only and not stat.S_ISDIR(row.st_mode):
            raise ProfileStateError('roster must be a directory')
        if stat.S_ISLNK(row.st_mode):
            if not lock:
                raise ProfileStateError('profile symlink is forbidden')
            result['target'] = os.readlink(path.name, dir_fd=parent)
            if _identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) != _identity(row):
                raise ProfileStateError('profile lock changed during observation')
            return result
        if lock:
            raise ProfileStateError('disk lock is not a symbolic link')
        if stat.S_ISDIR(row.st_mode):
            fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                if _identity(os.fstat(fd)) != result:
                    raise ProfileStateError('profile directory changed')
                entries = os.listdir(fd)
                if len(entries) > 4096:
                    raise ProfileStateError('profile directory exceeds bound')
                result['entries'] = sorted(entries)
                if _identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) != _identity(row):
                    raise ProfileStateError('profile directory entry changed')
            finally:
                os.close(fd)
            return result
        if not stat.S_ISREG(row.st_mode) or row.st_nlink != 1:
            raise ProfileStateError('profile file must be a singly linked regular file')
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if _identity(before) != result:
                raise ProfileStateError('profile file changed')
            if disk:
                header = os.read(fd, 512)
                _require_raw_disk_probe(header)
                result['format_probe_hex'] = header.hex()
                result['format'] = 'raw'
                result['size'] = before.st_size
            else:
                if before.st_size > MAX_CONFIG:
                    raise ProfileStateError('profile file exceeds bound')
                payload = os.read(fd, MAX_CONFIG + 1)
                if len(payload) != before.st_size:
                    raise ProfileStateError('profile file size changed')
                result['hex'] = payload.hex()
            after = os.fstat(fd)
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ProfileStateError('profile file changed during observation')
            if _identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) != _identity(row):
                raise ProfileStateError('profile file entry changed during observation')
        finally:
            os.close(fd)
        return result


def require_pristine(paths):
    for path in (paths.profile, paths.instance, paths.disk, paths.store, paths.startup):
        if _read(path) is not None:
            raise ProfileStateError('owned profile remnant prevents preflight')


def capture(paths):
    targets = {key: getattr(paths, key) for key in ('profile', 'instance', 'disk', 'store', 'startup', 'lima')}
    targets.update(profile_config=paths.profile / 'colima.yaml', instance_config=paths.instance / 'colima.yaml',
                   data_disk=paths.disk / 'datadisk', root_disk=paths.instance / 'disk',
                   lima_config=paths.instance / 'lima.yaml', protected=paths.instance / 'protected',
                   lock=paths.disk / 'in_use_by')
    def read(key, path):
        return _read(path, disk=key in {'data_disk', 'root_disk'}, lock=key == 'lock')
    result = {key: read(key, path) for key, path in targets.items()}
    # A later child read must not bind a replacement beneath an earlier parent
    # observation. Recheck the closed footprint before publishing the capture.
    if any(read(key, path) != result[key] for key, path in targets.items()):
        raise ProfileStateError('profile footprint changed during observation')
    return result


def validate_capture(observed):
    kinds = {'profile': 'dir', 'instance': 'dir', 'disk': 'dir', 'lima': 'dir',
             'store': 'file', 'startup': 'file', 'profile_config': 'file', 'instance_config': 'file',
             'lima_config': 'file', 'protected': 'file', 'data_disk': 'disk', 'root_disk': 'disk', 'lock': 'link'}
    if type(observed) is not dict or set(observed) != set(kinds):
        raise ProfileStateError('profile capture schema is invalid')
    for key, kind in kinds.items():
        row = observed[key]
        if row is None:
            continue
        _record_identity(row, 'file' if kind == 'disk' else kind)
        extra = {'dir': {'entries'}, 'file': {'hex'}, 'disk': {'size', 'format', 'format_probe_hex'}, 'link': {'target'}}[kind]
        if set(row) != {'device', 'inode', 'mode'} | extra:
            raise ProfileStateError('profile capture record fields are invalid')
        if kind == 'file':
            payload = row['hex']
            if type(payload) is not str or len(payload) > 2 * MAX_CONFIG or re.fullmatch('(?:[0-9a-f]{2})*', payload) is None:
                raise ProfileStateError('profile file capture exceeds closed byte bound')
        if kind == 'dir':
            entries = row['entries']
            if type(entries) is not list or len(entries) > 4096 or any(type(v) is not str or not v or '/' in v or v in {'.', '..'} for v in entries) or entries != sorted(set(entries)):
                raise ProfileStateError('profile directory capture is invalid')
        if kind == 'disk' and (type(row['size']) is not int or row['size'] < 0 or row['format'] != 'raw'):
            raise ProfileStateError('profile disk capture is invalid')
        if kind == 'disk':
            probe = row['format_probe_hex']
            if type(probe) is not str or re.fullmatch('[0-9a-f]{1024}', probe) is None:
                raise ProfileStateError('disk format probe capture is invalid')
            _require_raw_disk_probe(bytes.fromhex(probe))
        if kind == 'link' and (type(row['target']) is not str or len(row['target']) > 4096):
            raise ProfileStateError('profile lock capture is invalid')
    # Retained observations must describe one possible tree, independently of
    # the collector's no-follow checks. Absence cannot coexist with descendants
    # or a directory entry claiming that a separately observed child exists.
    relationships = (
        ('profile', 'profile_config', 'colima.yaml'),
        ('instance', 'instance_config', 'colima.yaml'),
        ('instance', 'lima_config', 'lima.yaml'),
        ('instance', 'root_disk', 'disk'),
        ('instance', 'protected', 'protected'),
        ('disk', 'data_disk', 'datadisk'), ('disk', 'lock', 'in_use_by'),
        ('lima', 'instance', NAME),
    )
    for parent_key, child_key, entry in relationships:
        parent, child = observed[parent_key], observed[child_key]
        listed = parent is not None and entry in parent['entries']
        if listed != (child is not None):
            raise ProfileStateError('profile parent/child capture is inconsistent')
    if observed['disk'] is not None and (observed['lima'] is None or '_disks' not in observed['lima']['entries']):
        raise ProfileStateError('profile disk lacks its Lima parent directory')


def _scalar(raw):
    if raw in ('null', 'true', 'false', '[]', '{}'):
        return json.loads(raw)
    if re.fullmatch(r'0|[1-9][0-9]*', raw):
        return int(raw)
    if raw.startswith('"'):
        value = json.loads(raw)
        if type(value) is str:
            return value
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.+\-=]*|--disable=traefik|192\.168\.5\.2', raw):
        if raw.lower() not in {'yes', 'no', 'on', 'off', 'null', 'true', 'false'}:
            return raw
    raise ProfileStateError('ambiguous or unsupported saved YAML scalar')


def parse_saved(payload):
    """Closed inert YAML subset matching the pinned 2-space serializer.

    No YAML interpreter, tags, anchors, merge keys or general collections. Only
    the reviewed one-element Kubernetes argument sequence is admitted.
    """
    if type(payload) is not bytes or len(payload) > MAX_CONFIG:
        raise ProfileStateError('saved configuration exceeds bound')
    try:
        lines = payload.decode('utf-8').splitlines()
        result, current = {}, None
        for line in lines:
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            if line == '    - --disable=traefik' and current == 'kubernetes' and result[current].get('k3sArgs') == []:
                result[current]['k3sArgs'] = ['--disable=traefik']
                continue
            match = re.fullmatch(r'(  )?([A-Za-z][A-Za-z0-9]*):(?: (.*))?', line)
            if match is None:
                raise ProfileStateError('unsupported saved YAML syntax')
            indent, key, raw = match.groups()
            if indent is None:
                if key in result:
                    raise ProfileStateError('duplicate saved configuration key')
                current = key if raw is None else None
                result[key] = {} if raw is None else _scalar(raw)
            else:
                if current not in {'network', 'kubernetes'} or key in result[current]:
                    raise ProfileStateError('duplicate or unexpected nested configuration')
                result[current][key] = [] if key == 'k3sArgs' and raw is None else _scalar(raw)
        expected = {
            'cpu': 4, 'disk': 60, 'memory': 8, 'arch': 'aarch64', 'runtime': 'docker',
            'modelRunner': 'docker', 'hostname': '',
            'kubernetes': {'enabled': False, 'version': 'v1.35.0+k3s1', 'k3sArgs': ['--disable=traefik'], 'port': 0},
            'autoActivate': False,
            'network': {'address': False, 'mode': 'shared', 'interface': 'en0', 'preferredRoute': False,
                        'dns': None, 'dnsHosts': {}, 'hostAddresses': False, 'gatewayAddress': '192.168.5.2'},
            'forwardAgent': False, 'docker': {}, 'vmType': 'vz', 'portForwarder': 'ssh',
            'rosetta': False, 'binfmt': False, 'nestedVirtualization': False, 'mountType': 'virtiofs',
            'mountInotify': False, 'cpuType': '', 'provision': None, 'sshConfig': False, 'sshPort': 0,
            'mounts': None, 'diskImage': '', 'forceDiskImage': False, 'rootDisk': 20, 'env': {},
        }
        if json.dumps(result, sort_keys=True) != json.dumps(expected, sort_keys=True):
            raise ProfileStateError('saved configuration differs from pinned CLI configuration')
        return result
    except (UnicodeError, TypeError, json.JSONDecodeError) as error:
        raise ProfileStateError('invalid saved configuration') from error


def _record_identity(record, kind):
    if type(record) is not dict or any(type(record.get(key)) is not int or record[key] < 0 for key in ('device', 'inode', 'mode')):
        raise ProfileStateError('resource identity is invalid')
    mode = record['mode']
    if not {'dir': stat.S_ISDIR, 'file': stat.S_ISREG, 'link': stat.S_ISLNK}[kind](mode):
        raise ProfileStateError('resource type is invalid')
    return {key: record[key] for key in ('device', 'inode', 'mode')}


def validate_binding(binding):
    if type(binding) is not dict or set(binding) != {'resources', 'config_sha256', 'lima_config_sha256', 'data_disk_size', 'data_disk_format', 'lock_target'}:
        raise ProfileStateError('profile binding fields are invalid')
    resources = binding['resources']
    if type(resources) is not dict or set(resources) != {'profile', 'instance', 'disk', 'profile_config', 'instance_config', 'data_disk', 'root_disk', 'lima_config'}:
        raise ProfileStateError('profile resource binding fields are invalid')
    for key, value in resources.items():
        if set(value) != {'device', 'inode', 'mode'}:
            raise ProfileStateError('profile identity binding fields are invalid')
        _record_identity(value, 'dir' if key in {'profile', 'instance', 'disk'} else 'file')
    hashes = binding['config_sha256']
    if type(hashes) is not dict or set(hashes) != {'profile', 'instance'} or any(type(v) is not str or re.fullmatch('[0-9a-f]{64}', v) is None for v in hashes.values()):
        raise ProfileStateError('profile saved hash bindings are invalid')
    if type(binding['lima_config_sha256']) is not str or re.fullmatch('[0-9a-f]{64}', binding['lima_config_sha256']) is None:
        raise ProfileStateError('Lima config hash binding is invalid')
    if type(binding['data_disk_size']) is not int or binding['data_disk_size'] != SIZE or binding['data_disk_format'] != 'raw':
        raise ProfileStateError('profile disk binding is invalid')
    target = binding['lock_target']
    if type(target) is not str or not Path(target).is_absolute() or '..' in Path(target).parts or Path(target).parts[-3:] != ('.colima', '_lima', NAME):
        raise ProfileStateError('profile disk lock binding is invalid')


def creation_binding(document, observed):
    paths = _paths(document)
    validate_capture(observed)
    if observed['protected'] is not None:
        raise ProfileStateError('protected VM requires manual recovery')
    identities = {key: _record_identity(observed[key], 'dir') for key in ('profile', 'instance', 'disk')}
    hashes = {}
    for key in ('profile', 'instance'):
        row = observed[key + '_config']
        identities[key + '_config'] = _record_identity(row, 'file')
        payload = bytes.fromhex(row['hex'])
        parse_saved(payload)
        hashes[key] = sha256(payload).hexdigest()
    disk = observed['data_disk']
    identities['data_disk'] = _record_identity(disk, 'file')
    if type(disk['size']) is not int or disk['size'] != SIZE or disk['format'] != 'raw':
        raise ProfileStateError('data disk differs from pinned capacity')
    _record_identity(observed['lock'], 'link')
    if observed['lock']['target'] != str(paths.instance):
        raise ProfileStateError('disk lock names foreign instance')
    if observed['startup'] is not None:
        raise ProfileStateError('startup artifact remains')
    identities['root_disk'] = _record_identity(observed['root_disk'], 'file')
    if observed['root_disk']['size'] != 20 * 1024**3:
        raise ProfileStateError('root disk differs from pinned capacity')
    identities['lima_config'] = _record_identity(observed['lima_config'], 'file')
    return {'resources': identities, 'config_sha256': hashes, 'data_disk_size': SIZE,
            'lima_config_sha256': sha256(bytes.fromhex(observed['lima_config']['hex'])).hexdigest(),
            'data_disk_format': disk['format'], 'lock_target': str(paths.instance)}


def unchanged(document, observed, binding, *, stopped=False):
    # A stopped instance legitimately unlocks its disk.
    validate_capture(observed)
    candidate = dict(observed)
    if stopped and candidate['lock'] is None:
        candidate['lock'] = {'device': 0, 'inode': 0, 'mode': stat.S_IFLNK, 'target': str(_paths(document).instance)}
        if candidate['disk'] is not None:
            candidate['disk'] = {**candidate['disk'], 'entries': sorted([*candidate['disk']['entries'], 'in_use_by'])}
    return creation_binding(document, candidate) == binding


def _zero_store(row):
    if row is None:
        return True
    _record_identity(row, 'file')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProfileStateError('duplicate store key')
            result[key] = value
        return result
    value = json.loads(bytes.fromhex(row['hex']), object_pairs_hook=unique)
    return json.dumps(value, sort_keys=True) == json.dumps(
        {'disk_formatted': False, 'disk_runtime': '', 'ramalama_provisioned': False}, sort_keys=True)


def absent(document, observed):
    _paths(document)
    validate_capture(observed)
    return all(observed[key] is None for key in ('profile', 'instance', 'disk', 'startup')) and _zero_store(observed['store'])


def orphan_authorized(document, observed, binding):
    """Fail closed unless the creation-bound disk is isolated and unlocked.

    Any additional Lima instance requires manual recovery: this conservative
    gate avoids trusting list commands that skip malformed instance files.
    """
    paths = _paths(document)
    try:
        validate_capture(observed)
        validate_binding(binding)
        if binding is None or any(observed[key] is not None for key in ('profile', 'instance', 'startup', 'lock')):
            return False
        if not _zero_store(observed['store']):
            return False
        if set(observed['lima']['entries']) - {'_config', '_networks', '_disks', '_templates', '_cache'}:
            return False
        if observed['disk']['entries'] != ['datadisk']:
            return False
        for key, kind in (('disk', 'dir'), ('data_disk', 'file')):
            if _record_identity(observed[key], kind) != binding['resources'][key]:
                return False
        return (observed['data_disk']['size'] == binding['data_disk_size'] == SIZE
                and observed['data_disk']['format'] == binding['data_disk_format']
                and binding['lock_target'] == str(paths.instance))
    except (ValueError, KeyError, TypeError):
        return False


def clear_private_docker(paths):
    """Remove only a closed, validated private Docker context footprint."""
    root = paths.private / 'docker-config'
    context_hash = sha256(NAME.encode()).hexdigest()
    allowed = {
        '': {'config.json', 'contexts'},
        'contexts': {'meta', 'tls'},
        'contexts/meta': {context_hash},
        'contexts/meta/' + context_hash: {'meta.json'},
        'contexts/tls': {context_hash},
        'contexts/tls/' + context_hash: set(),
    }
    observed = {}
    def visit(relative):
        path = root / relative
        row = _read(path)
        if row is None:
            return
        if relative in allowed:
            _record_identity(row, 'dir')
            if set(row['entries']) - allowed[relative]:
                raise ProfileStateError('private Docker directory contains unreviewed entries')
            observed[path] = row
            for name in row['entries']:
                visit(str(Path(relative) / name))
            return
        _record_identity(row, 'file')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ProfileStateError('duplicate Docker context key')
                result[key] = value
            return result
        value = json.loads(bytes.fromhex(row['hex']), object_pairs_hook=unique)
        if relative == 'config.json':
            if type(value) is not dict or set(value) - {'auths', 'currentContext'} or value.get('auths', {}) != {} or value.get('currentContext', '') != '':
                raise ProfileStateError('private Docker configuration contains unreviewed values')
        elif relative == 'contexts/meta/' + context_hash + '/meta.json':
            expected = {'Name': NAME, 'Metadata': {'Description': 'colima [profile=kil-v3-lab]'},
                        'Endpoints': {'docker': {'Host': 'unix://' + str(paths.profile / 'docker.sock'), 'SkipTLSVerify': False}}}
            if json.dumps(value, sort_keys=True) != json.dumps(expected, sort_keys=True):
                raise ProfileStateError('private Docker context identity changed')
        else:
            raise ProfileStateError('unreviewed private Docker file')
        observed[path] = row
    visit('')
    for path, row in observed.items():
        if _read(path) != row:
            raise ProfileStateError('private Docker state changed before cleanup')
    for path, row in sorted(observed.items(), key=lambda item: len(item[0].parts), reverse=True):
        with _parent(path) as parent:
            if parent is None or _identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) != _identity_from_record(row):
                raise ProfileStateError('private Docker entry changed before cleanup')
            if stat.S_ISDIR(row['mode']):
                os.rmdir(path.name, dir_fd=parent)
            else:
                if _read(path) != row:
                    raise ProfileStateError('private Docker file changed before cleanup')
                os.unlink(path.name, dir_fd=parent)


def _identity_from_record(row):
    return {key: row[key] for key in ('device', 'inode', 'mode')}
