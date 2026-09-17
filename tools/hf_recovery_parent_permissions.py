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

class _Attempt:
    def __init__(self):
        self.attempts = 0
        self.returned = False
    def enter(self, fd):
        if self.attempts:
            raise ValueError('permission_slot_already_consumed')
        self.attempts = 1
        os.fchmod(fd, 0o700)
        self.returned = True

class _Errors:
    def __init__(self):
        self.rows = []
        self.overflow = False
    def add(self, error):
        if len(self.rows) >= 16:
            self.overflow = True
            return
        def bound(value, maximum):
            data = value.encode('utf-8', errors='backslashreplace')
            if len(data) > maximum:
                self.overflow = True
            return data[:maximum].decode('utf-8', errors='ignore')
        try:
            message = str(error)
        except BaseException:
            message = 'exception message conversion failed'
            self.overflow = True
        self.rows.append({'type': bound(type(error).__name__, 128),
                          'message': bound(message, 4096)})

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

class _Proof:
    def __init__(self):
        self.dirs = _Directories()
        self.target = self.lock = self.lock_parent = None
        self.before = self.post = self.lock_identity = None
        self.lock_payload = self.children = None
        self.closed = False
    def bind(self):
        tools = self.dirs.directory(REPOSITORY / '.tools')
        row = os.fstat(tools)
        if ((row.st_dev, row.st_ino) != TOOLS_PIN or row.st_uid != UID or stat.S_IMODE(row.st_mode) != 0o700):
            raise ValueError('permission_tools_pin_or_privacy')
        self.target = self.dirs.directory(TARGET)
        row = os.fstat(self.target)
        if ((row.st_dev, row.st_ino) != TARGET_PIN or row.st_uid != UID or stat.S_IMODE(row.st_mode) != 0o755):
            raise ValueError('permission_target_pin_or_initial_mode')
        self.before = _full(row)
        self.lock_parent = self.dirs.directory(REPOSITORY / '.tools/hf-exploratory-private')
        parent = os.fstat(self.lock_parent)
        if parent.st_uid != UID or stat.S_IMODE(parent.st_mode) != 0o700:
            raise ValueError('permission_lock_parent_not_private')
        self.lock = os.open('profile.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.lock_parent)
        row = os.fstat(self.lock)
        if (not stat.S_ISREG(row.st_mode) or stat.S_IMODE(row.st_mode) != 0o600 or row.st_uid != UID or row.st_nlink != 1 or row.st_size > MAXIMUM):
            raise ValueError('permission_existing_lock_invalid')
        self.lock_identity = _full(row)
        self.metadata()
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.lock_payload = self._read_lock()
        first, second = self._children(), self._children()
        if first != second: raise ValueError('permission_initial_children_unstable')
        self.children = first
        self.metadata()
    def metadata(self, *, after=False):
        if self.closed: raise ValueError('permission_proof_closed')
        if after and self.post is None: raise ValueError('permission_post_baseline_unavailable')
        self.dirs.guard(after=after)
        expected = self.post if after else self.before
        if self.target is not None and expected is not None:
            if _full(os.fstat(self.target)) != expected: raise ValueError('permission_target_metadata_changed')
            parent = self.dirs.records[TARGET.parent][1]
            if _full(os.stat(TARGET.name, dir_fd=parent, follow_symlinks=False)) != expected:
                raise ValueError('permission_target_named_changed')
        if self.lock is not None and self.lock_identity is not None:
            if (_full(os.fstat(self.lock)) != self.lock_identity or _full(os.stat('profile.lock', dir_fd=self.lock_parent, follow_symlinks=False)) != self.lock_identity):
                raise ValueError('permission_existing_lock_changed')
        if self.children is not None:
            for name, original in self.children:
                if _full(os.stat(name, dir_fd=self.target, follow_symlinks=False)) != original:
                    raise ValueError('permission_known_child_metadata_changed')
    def _read_lock(self, *, after=False):
        self.metadata(after=after)
        payload = os.pread(self.lock, MAXIMUM + 1, 0)
        if len(payload) > MAXIMUM or len(payload) != self.lock_identity[6]:
            raise ValueError('permission_lock_read_bound_or_length')
        self.metadata(after=after)
        return payload
    def _children(self):
        rows = []
        with os.scandir(self.target) as entries:
            for entry in entries:
                name = entry.name
                if (len(rows) >= 256 or not name or len(name.encode('utf-8')) > 128 or name in ('.', '..') or '/' in name or '\x00' in name):
                    raise ValueError('permission_children_bound_or_name')
                rows.append((name, _full(os.stat(name, dir_fd=self.target, follow_symlinks=False))))
        return sorted(rows)
    def observe(self, *, after=False):
        self.metadata(after=after)
        if self._read_lock(after=after) != self.lock_payload: raise ValueError('permission_lock_bytes_changed')
        first, second = self._children(), self._children()
        if first != second or first != self.children: raise ValueError('permission_children_changed')
        self.metadata(after=after)
    def bind_post(self):
        self.dirs.guard(after=True)
        row = _full(os.fstat(self.target))
        expected_mode = (self.before[2] & ~0o7777) | 0o700
        if row[:8] != (*self.before[:2], expected_mode, *self.before[3:8]):
            raise ValueError('permission_post_target_not_expected')
        self.post = row
        self.metadata(after=True)
    def close(self):
        if self.closed: return []
        self.closed = True
        errors = []
        if self.lock is not None:
            fd, self.lock = self.lock, None
            try: fcntl.flock(fd, fcntl.LOCK_UN)
            except BaseException as error: errors.append(error)
            try: _close_fd(fd)
            except BaseException as error: errors.append(error)
        errors.extend(self.dirs.close())
        return errors

def _source(reviewed_source):
    location = str(REPOSITORY / 'src')
    if location not in sys.path:
        sys.path.insert(0, location)
    from kil.hf_exploratory_native import check_source
    check_source(REPOSITORY, reviewed_source)

def _account():
    if os.getuid() != UID or os.geteuid() != UID or Path(pwd.getpwuid(os.getuid()).pw_dir) != HOME:
        raise ValueError('permission_actual_account_changed')

def _run(reviewed_source, execution_approval):
    proof, attempt, errors = _Proof(), _Attempt(), _Errors()
    observed_post = None
    checks = {key: False for key in ('target', 'ancestors', 'children', 'lock', 'source', 'account', 'teardown')}
    try:
        _source(reviewed_source)
        _account()
        proof.bind()
        _source(reviewed_source)
        _account()
        proof.observe()
        _source(reviewed_source)
        _account()
        proof.metadata()
        attempt.enter(proof.target)
        observed_post = _full(os.fstat(proof.target))
        os.fsync(proof.target)
        proof.bind_post()
        proof.observe(after=True)
        _source(reviewed_source)
        _account()
        proof.metadata(after=True)
        for key in checks:
            if key != 'teardown':
                checks[key] = True
    except BaseException as error:
        errors.add(error)
        if attempt.attempts and proof.target is not None:
            try:
                observed_post = _full(os.fstat(proof.target))
            except BaseException as observation_error:
                errors.add(observation_error)
    finally:
        for error in proof.close():
            errors.add(error)
    checks['teardown'] = not errors.rows and not errors.overflow
    if not attempt.attempts:
        outcome = 'preflight_refused'
    elif not attempt.returned:
        outcome = 'mutation_uncertain'
    elif errors.rows or errors.overflow or not all(checks.values()):
        outcome = 'postverification_inconclusive'
    else:
        outcome = 'mode_change_confirmed'
    def mode(row):
        return None if row is None else format(stat.S_IMODE(row[2]), '04o')
    return {
        'outcome': outcome,
        'reviewed_source': reviewed_source,
        'execution_approval': execution_approval,
        'target': str(TARGET),
        'target_pin': TARGET_PIN,
        'tools_pin': TOOLS_PIN,
        'fchmod_attempts': attempt.attempts,
        'syscall_certainty': ('not_entered' if not attempt.attempts else 'returned' if attempt.returned else 'uncertain'),
        'observed_pre_mode': mode(proof.before),
        'observed_post_mode': mode(observed_post),
        'target_pre_stat9': proof.before,
        'target_post_observed_stat9': observed_post,
        'target_post_verified_stat9': proof.post,
        'direct_children_count': None if proof.children is None else len(proof.children),
        'direct_children_sha256': None if proof.children is None else sha256(_canonical(proof.children)).hexdigest(),
        'lock_stat9': proof.lock_identity,
        'lock_sha256': None if proof.lock_payload is None else sha256(proof.lock_payload).hexdigest(),
        'preservation': outcome == 'mode_change_confirmed',
        'preservation_checks': checks,
        'errors': errors.rows,
        'error_overflow': errors.overflow,
        'preservation_scope': 'own_no_receipt_writes_and_direct_child_metadata_not_descendant_content',
    }

def _source_argument(value):
    if re.fullmatch(r'[0-9a-f]{40}', value) is None:
        raise argparse.ArgumentTypeError('reviewed source must be exact40-hex')
    return value

def _approval_argument(value):
    try:
        valid = bool(value.strip()) and len(value.encode('utf-8')) <= 4096
    except UnicodeError:
        valid = False
    if not valid:
        raise argparse.ArgumentTypeError('actual approval must be nonblank validUTF-8 <=4096 bytes')
    return value

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--reviewed-source', required=True, type=_source_argument)
    parser.add_argument('--execution-approval', required=True, type=_approval_argument)
    parser.add_argument('--execute-approved-mode-change', required=True, action='store_true')
    args = parser.parse_args(argv)
    result = _run(args.reviewed_source, args.execution_approval)
    raw = _canonical(result)
    if len(raw) > MAXIMUM:
        raise ValueError('permission_result_exceeds_bound_after_attempt')
    print(raw.decode('utf-8'), end='')
    return 0 if result['outcome'] == 'mode_change_confirmed' else 1

if __name__ == '__main__':
    raise SystemExit(main())
