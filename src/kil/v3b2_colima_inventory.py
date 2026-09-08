"""Closed Colima 0.10.3 inventory and read-only Lima roster completeness.

Colima emits one InstanceInfo JSON object per line, and its pinned Instances
scanner omits Scanner.Err. Successful empty/partial output therefore requires a
stable directory roster bracket. This is an observation, not external exclusion
or permission to operate on any discovered name. No guest contents are read.
"""
import ipaddress
import json
import os
import re
import stat

MAX_RECORDS = 1024
MAX_PAYLOAD_BYTES = 32 * 1024 * 1024
MAX_NAME_BYTES = 128
RESOURCE_LIMITS = {'cpus': 2**31 - 1, 'memory': 2**63 - 1, 'disk': 2**63 - 1}
RUNTIMES = frozenset({'docker', 'containerd', 'incus', 'docker+k3s', 'containerd+k3s', 'incus+k3s', 'none'})
ARCHES = frozenset({'aarch64', 'x86_64'})
FIELDS = frozenset({'name', 'status', 'arch', 'cpus', 'memory', 'disk', 'runtime'})
RESERVED = frozenset({'_config', '_networks', '_disks', '_templates', '_cache'})
_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')


class ColimaInventoryError(ValueError):
    pass


def _name(value):
    if type(value) is not str or _NAME.fullmatch(value) is None:
        raise ColimaInventoryError('profile name is outside the supported bounded vocabulary')
    return value


def validate_resources(record):
    if (type(record.get('status')) is not str or record['status'] not in {'Running', 'Stopped'}
            or type(record.get('arch')) is not str or record['arch'] not in ARCHES
            or type(record.get('runtime')) is not str or record['runtime'] not in RUNTIMES
            or any(type(record.get(key)) is not int or not 0 < record[key] <= limit
                   for key, limit in RESOURCE_LIMITS.items())):
        raise ColimaInventoryError('profile resources are invalid')


def validate_records(value):
    """Normalize the supported compatibility aliases, retaining optional address."""
    if type(value) is not list or len(value) > MAX_RECORDS:
        raise ColimaInventoryError('profile inventory must be a bounded array')
    names, result = set(), []
    for raw in value:
        if type(raw) is not dict or set(raw) not in (FIELDS, FIELDS | {'address'}):
            raise ColimaInventoryError('profile fields are not closed')
        row = dict(raw)
        name = _name(row['name'])
        if name in names:
            raise ColimaInventoryError('profile name is duplicated')
        names.add(name)
        # Only these legacy fixture spellings are accepted and normalized.
        if type(row['arch']) is str:
            row['arch'] = {'arm64': 'aarch64', 'amd64': 'x86_64'}.get(row['arch'], row['arch'])
        if type(row['status']) is str:
            row['status'] = {'running': 'Running', 'stopped': 'Stopped'}.get(row['status'], row['status'])
        validate_resources(row)
        if 'address' in row:
            address = row['address']
            if type(address) is not str or len(address) > 45 or '%' in address:
                raise ColimaInventoryError('profile address is not an IP literal')
            try:
                ipaddress.ip_address(address)
            except ValueError:
                raise ColimaInventoryError('profile address is not an IP literal') from None
        result.append(row)
    return sorted(result, key=lambda row: row['name'])


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ColimaInventoryError('duplicate profile JSON field')
        result[key] = value
    return result


def decode_inventory(payload, *, returncode=0, stderr=b''):
    if (type(payload) is not bytes or len(payload) > MAX_PAYLOAD_BYTES
            or type(returncode) is not int or returncode != 0 or type(stderr) is not bytes or stderr):
        raise ColimaInventoryError('profile inventory transport or byte bound is invalid')
    try:
        text = payload.decode('utf-8').strip()
        if not text:
            return []
        def read(text):
            return json.loads(text, object_pairs_hook=_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ColimaInventoryError('nonfinite profile JSON')))
        if text.startswith('['):
            rows = read(text)
        else:
            lines = [line for line in text.splitlines() if line.strip()]
            if len(lines) > MAX_RECORDS:
                raise ColimaInventoryError('profile record count exceeds bound')
            rows = [read(line) for line in lines]
        return validate_records(rows)
    except (UnicodeError, ValueError, RecursionError):
        raise ColimaInventoryError('invalid closed profile inventory') from None


def _directory(row, fields):
    if (type(row) is not dict or set(row) != fields
            or any(type(row.get(key)) is not int or row[key] < 0 for key in ('device', 'inode', 'mode'))
            or not stat.S_ISDIR(row['mode'])):
        raise ColimaInventoryError('roster entry is not an exact directory identity')


def _roster_names(observed):
    if observed is None:
        return []
    if type(observed) is not dict or set(observed) != {'directory', 'children'}:
        raise ColimaInventoryError('roster observation fields are invalid')
    directory, children = observed['directory'], observed['children']
    _directory(directory, {'device', 'inode', 'mode', 'entries'})
    entries = directory['entries']
    if (type(entries) is not list or len(entries) > MAX_RECORDS + len(RESERVED)
            or any(type(name) is not str for name in entries) or entries != sorted(set(entries))
            or type(children) is not list or len(children) != len(entries)):
        raise ColimaInventoryError('roster cardinality or directory entries are invalid')
    names = []
    for entry, child in zip(entries, children):
        _directory(child, {'name', 'device', 'inode', 'mode'})
        if child['name'] != entry:
            raise ColimaInventoryError('roster child identity differs from directory listing')
        if entry in RESERVED:
            continue
        if entry == 'colima':
            name = 'default'
        elif entry.startswith('colima-'):
            name = _name(entry[len('colima-'):])
            # Fail closed for ambiguous aliases and unsupported prefix lookalikes.
            if name in {'colima', 'default'} or name.startswith('colima-'):
                raise ColimaInventoryError('ambiguous Colima profile mapping')
        else:
            raise ColimaInventoryError('unsupported Lima roster entry')
        names.append(name)
    if len(names) != len(set(names)) or len(names) > MAX_RECORDS:
        raise ColimaInventoryError('ambiguous or oversized Colima roster')
    return sorted(names)


def require_complete(records, before, after):
    rows = validate_records(records)
    left, right = _roster_names(before), _roster_names(after)
    if before != after or left != right or [row['name'] for row in rows] != left:
        raise ColimaInventoryError('profile inventory is incomplete or roster changed')
    return rows


def capture_roster(paths):
    """Observe only the Lima directory and child lstat identities, without follow."""
    from kil.v3b2_profile_state import _read, _parent, _identity
    directory = _read(paths.lima, directory_only=True)
    if directory is None:
        if _read(paths.lima, directory_only=True) is not None:
            raise ColimaInventoryError('missing roster changed during capture')
        return None
    _directory(directory, {'device', 'inode', 'mode', 'entries'})
    with _parent(paths.lima / '.roster-observation') as descriptor:
        if descriptor is None or _identity(os.fstat(descriptor)) != {key: directory[key] for key in ('device', 'inode', 'mode')}:
            raise ColimaInventoryError('roster directory changed during capture')
        children = [{'name': name, **_identity(os.stat(name, dir_fd=descriptor, follow_symlinks=False))}
                    for name in directory['entries']]
        observed = {'directory': directory, 'children': children}
        _roster_names(observed)
        if any(_identity(os.stat(row['name'], dir_fd=descriptor, follow_symlinks=False)) !=
               {key: row[key] for key in ('device', 'inode', 'mode')} for row in children):
            raise ColimaInventoryError('roster children changed during capture')
    if _read(paths.lima, directory_only=True) != directory:
        raise ColimaInventoryError('roster directory changed during capture')
    return observed
