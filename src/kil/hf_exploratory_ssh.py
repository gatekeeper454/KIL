"""Authenticate fresh pinned-producer SSH controls; never execute or repair them."""
from dataclasses import dataclass
from hashlib import sha256
import os
import sys
import re
import stat

from kil.hf_exploratory_runtime import RuntimeAuthority

MAX_CONTROL = 16 * 1024
KEYS = ('device', 'inode', 'mode', 'uid', 'nlink', 'size', 'mtime_ns', 'ctime_ns')


def _identity(row):
    return (row.st_dev, row.st_ino, row.st_mode, row.st_uid,
            row.st_nlink, row.st_size, row.st_mtime_ns, row.st_ctime_ns)


def _directory(row):
    return row.st_dev, row.st_ino, row.st_mode, row.st_uid


def _absent(parent, name):
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ValueError('ssh_control_expected_absence')


@dataclass(frozen=True)
class _Control:
    parent: int
    name: str
    fd: int | None
    identity: tuple | None
    data: bytes | None

    def proof(self):
        return {'present': self.fd is not None,
                'identity': None if self.identity is None else dict(zip(KEYS, self.identity)),
                'byte_count': None if self.data is None else len(self.data),
                'hex': None if self.data is None else self.data.hex(),
                'sha256': None if self.data is None else sha256(self.data).hexdigest()}


class SSHControls:
    """Retained descriptors plus provisional lifecycle-transition closures.

    The lifecycle supplies successful native command and complete profile/inventory
    gates. Provisional forms are immutable during those gates and are not evidence
    of successful binding until their finish method completes.
    """
    def __init__(self, authority):
        if type(authority) is not RuntimeAuthority:
            raise ValueError('ssh_controls_require_runtime_authority')
        authority.guard()
        if any(byte < 32 or byte == 127 or byte in (34, 92) for byte in os.fsencode(authority.path)):
            raise ValueError('ssh_control_derived_path_ambiguous')
        self.authority = authority
        self.colima_fd = next(fd for parent,name,fd,_ in authority._anchors
                              if parent == authority._root_fd and name == '.colima')
        self.lima_fd = next(fd for parent,name,fd,_ in authority._anchors
                            if parent == self.colima_fd and name == '_lima')
        self.instance_anchor = None
        self.colima = self.instance = None
        self.state = 'unbound'
        self.port = None
        self._owned = []
        self._removed_instance = None
        self._removed_colima = None

    def close(self):
        descriptors = tuple(reversed(self._owned))
        self._owned.clear()
        self.state = 'closed'
        first_error = None
        for fd in descriptors:
            try:
                os.close(fd)
            except OSError as error:
                if first_error is None: first_error = error
        if first_error is not None: raise first_error

    def refuse(self):
        self.state = 'refused'

    def _anchors(self, *, removed=False):
        self.authority.guard()
        if os.geteuid() != self.authority._uid:
            raise ValueError('ssh_controls_uid_changed')
        if self.instance_anchor is not None:
            fd, identity = self.instance_anchor
            if removed:
                _absent(self.lima_fd, 'colima-kil-v3-lab')
            elif (_directory(os.fstat(fd)) != identity
                  or _directory(os.stat('colima-kil-v3-lab', dir_fd=self.lima_fd,
                                        follow_symlinks=False)) != identity):
                raise ValueError('ssh_instance_ancestor_changed')

    def require_absent(self):
        try:
            self._anchors()
            if self.state != 'unbound':
                raise ValueError('ssh_controls_already_bound')
            _absent(self.colima_fd, 'ssh_config')
            _absent(self.lima_fd, 'colima-kil-v3-lab')
            self._anchors()
        except OSError as error:
            raise ValueError('ssh_prestart_absence_refused') from error

    def _read(self, parent, name, mode, *, absent=False):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            if not absent:
                raise
            _absent(parent, name)
            return _Control(parent, name, None, None, None)
        self._owned.append(fd)
        try:
            row = os.fstat(fd)
            identity = _identity(row)
            if (not stat.S_ISREG(row.st_mode) or stat.S_IMODE(row.st_mode) != mode
                    or row.st_uid != os.geteuid() or row.st_nlink != 1
                    or not 0 <= row.st_size <= MAX_CONTROL):
                raise ValueError('ssh_control_not_owned_bounded_regular')
            data = self._bytes(fd, row.st_size)
            if (_identity(os.fstat(fd)) != identity
                    or _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity
                    or len(data) != row.st_size):
                raise ValueError('ssh_control_changed_during_read')
            return _Control(parent, name, fd, identity, data)
        except BaseException:
            self._owned.remove(fd); os.close(fd)
            raise

    @staticmethod
    def _bytes(fd, size):
        os.lseek(fd, 0, os.SEEK_SET)
        chunks, count = [], 0
        while count <= size:
            chunk = os.read(fd, min(4096, size + 1 - count))
            if not chunk:
                break
            chunks.append(chunk); count += len(chunk)
        return b''.join(chunks)

    def _metadata(self, control):
        if control.fd is None:
            _absent(control.parent, control.name)
        elif (_identity(os.fstat(control.fd)) != control.identity
              or _identity(os.stat(control.name, dir_fd=control.parent,
                                   follow_symlinks=False)) != control.identity):
            raise ValueError('ssh_control_identity_or_bytes_changed')

    def _check(self, control):
        self._metadata(control)
        if control.fd is not None:
            if self._bytes(control.fd, control.identity[5]) != control.data:
                raise ValueError('ssh_control_identity_or_bytes_changed')
            self._metadata(control)

    def _removed_directory(self):
        fd, identity = self.instance_anchor
        row = os.fstat(fd)
        if _directory(row) != identity or os.listdir(fd):
            raise ValueError('ssh_deleted_instance_directory_changed')
        if sys.platform == 'darwin':
            # APFS retains nlink=2 for an open, rmdir'd empty directory. F_GETPATH
            # retains its original path, whereas a renamed surviving directory
            # reports its new path. Named absence is separately anchored.
            import fcntl
            retained = fcntl.fcntl(fd, 50, bytes(1024)).split(b'\0',1)[0]
            expected = os.fsencode(self.authority.lima/'colima-kil-v3-lab')
            if row.st_nlink != 2 or retained != expected:
                raise ValueError('ssh_deleted_instance_directory_survives')
        elif row.st_nlink != 0:
            raise ValueError('ssh_deleted_instance_directory_survives')

    def _unlink_proof(self, control):
        identity = _identity(os.fstat(control.fd))
        expected = control.identity
        if (identity[:4] != expected[:4] or identity[4] != 0
                or identity[5:7] != expected[5:7]
                or self._bytes(control.fd, identity[5]) != control.data
                or _identity(os.fstat(control.fd)) != identity):
            raise ValueError('ssh_control_not_authentically_unlinked')
        return control, identity

    def _check_unlinked(self, proof):
        control, identity = proof
        if (_identity(os.fstat(control.fd)) != identity
                or self._bytes(control.fd, identity[5]) != control.data
                or _identity(os.fstat(control.fd)) != identity):
            raise ValueError('ssh_deleted_control_descriptor_changed')

    def _check_removed_instance(self):
        self._check_unlinked(self._removed_instance)
        self._removed_directory()

    def _grammar(self, colima, instance):
        match = re.search(rb'  Port ([1-9][0-9]{0,4})\n\n$', colima)
        if match is None or not 1 <= int(match[1]) <= 65535:
            raise ValueError('ssh_control_port_invalid')
        port = int(match[1])
        expected = ('# This SSH config file can be passed to \'ssh -F\'.\n'
            '# This file is created by Lima, but not used by Lima itself currently.\n'
            '# Modifications to this file will be lost on restarting the Lima instance.\n'
            'Host lima-colima-kil-v3-lab\n'
            f'  IdentityFile "{self.authority.lima / "_config/user"}"\n'
            '  StrictHostKeyChecking no\n'
            '  UserKnownHostsFile /dev/null\n'
            '  NoHostAuthenticationForLocalhost yes\n'
            '  PreferredAuthentications publickey\n'
            '  Compression no\n'
            '  BatchMode yes\n'
            '  IdentitiesOnly yes\n'
            '  GSSAPIAuthentication no\n'
            '  Ciphers "^aes128-gcm@openssh.com,aes256-gcm@openssh.com"\n'
            '  User mistorm\n'
            '  ControlMaster auto\n'
            f'  ControlPath "{self.authority.lima / "colima-kil-v3-lab/ssh.sock"}"\n'
            '  ControlPersist yes\n'
            '  Hostname 127.0.0.1\n'
            f'  Port {port}\n').encode()
        if (instance != expected
                or colima != expected.replace(b'Host lima-colima-', b'Host colima-') + b'\n'):
            raise ValueError('ssh_controls_not_exact_pinned_generated_pair')
        return port

    def begin_running(self):
        if self.state != 'unbound':
            raise ValueError('ssh_running_bind_not_fresh')
        start = len(self._owned)
        try:
            self._anchors()
            fd = os.open('colima-kil-v3-lab', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=self.lima_fd)
            self._owned.append(fd)
            identity = _directory(os.fstat(fd))
            if not stat.S_ISDIR(identity[2]) or identity[3] != os.geteuid():
                raise ValueError('ssh_instance_not_owned_directory')
            self.instance_anchor = fd, identity
            self._anchors()
            colima = self._read(self.colima_fd, 'ssh_config', 0o644)
            instance = self._read(fd, 'ssh.config', 0o600)
            port = self._grammar(colima.data, instance.data)
            self.colima, self.instance, self.port = colima, instance, port
            self.state = 'binding'
            self.guard()
        except BaseException as error:
            descriptors = tuple(reversed(self._owned[start:]))
            del self._owned[start:]
            self.refuse()
            first_close_error = None
            for fd in descriptors:
                try:
                    os.close(fd)
                except OSError as close_error:
                    if first_close_error is None: first_close_error = close_error
            self.instance_anchor = None
            self.colima = self.instance = self.port = None
            self.refuse()
            if first_close_error is not None:
                raise ValueError('ssh_running_binding_cleanup_refused') from first_close_error
            if isinstance(error, OSError):
                raise ValueError('ssh_running_binding_refused') from error
            raise

    def finish_running(self):
        if self.state != 'binding': raise ValueError('ssh_running_binding_unavailable')
        self.guard(); self.state = 'running'

    def bind_running(self):
        self.begin_running(); self.finish_running()

    def guard(self):
        if self.state not in ('binding','running','stopping','stopped','deleting','deleted'):
            raise ValueError('ssh_controls_binding_unavailable')
        try:
            removed = self.state in ('deleting','deleted')
            self._anchors(removed=removed)
            self._check(self.colima)
            if removed and self._removed_colima is not None:
                self._check_unlinked(self._removed_colima)
            if removed: self._check_removed_instance()
            else: self._check(self.instance)
            self._anchors(removed=removed)
            if removed: self._removed_directory()
            # Close earlier file observations after all pair/authority reads.
            self._metadata(self.colima)
            if removed and self._removed_colima is not None:
                if _identity(os.fstat(self._removed_colima[0].fd)) != self._removed_colima[1]:
                    raise ValueError('ssh_deleted_control_descriptor_changed')
            if removed:
                if _identity(os.fstat(self._removed_instance[0].fd)) != self._removed_instance[1]:
                    raise ValueError('ssh_deleted_instance_descriptor_changed')
            else: self._metadata(self.instance)
        except (OSError, ValueError) as error:
            self.refuse()
            raise ValueError('ssh_controls_fresh_closure_refused') from error

    def begin_stopped(self):
        if self.state != 'running': raise ValueError('ssh_stop_transition_not_running')
        candidate = None
        try:
            self._anchors(); self._check(self.instance)
            candidate = self._read(self.colima_fd, 'ssh_config', 0o644, absent=True)
            if candidate.data not in (None, b''):
                if candidate.identity != self.colima.identity or candidate.data != self.colima.data:
                    raise ValueError('ssh_stop_transition_content_changed')
                self._check(self.colima)
            self._anchors(); self._check(self.instance); self._check(candidate)
            self.colima = candidate
            self.state = 'stopping'
            self.guard()
        except BaseException as error:
            self.refuse()
            if candidate is not None and candidate.fd is not None:
                self._owned.remove(candidate.fd); os.close(candidate.fd)
            if isinstance(error, OSError):
                raise ValueError('ssh_stop_transition_refused') from error
            raise

    def finish_stopped(self):
        if self.state != 'stopping': raise ValueError('ssh_stop_transition_unavailable')
        self.guard(); self.state = 'stopped'

    def begin_deleted(self):
        if self.state != 'stopped': raise ValueError('ssh_delete_transition_not_stopped')
        candidate = None
        try:
            self._anchors(removed=True)
            self._removed_instance = self._unlink_proof(self.instance)
            self._removed_directory()
            try:
                os.stat('ssh_config',dir_fd=self.colima_fd,follow_symlinks=False)
            except FileNotFoundError:
                if self.colima.fd is not None:
                    self._removed_colima = self._unlink_proof(self.colima)
                _absent(self.colima_fd, 'ssh_config')
                self.colima = _Control(self.colima_fd,'ssh_config',None,None,None)
            else:
                if self.colima.fd is not None and self.colima.data == b'':
                    candidate = self._read(self.colima_fd,'ssh_config',0o644)
                    if (candidate.data != b'' or candidate.identity[:6] != self.colima.identity[:6]
                            or _identity(os.fstat(self.colima.fd)) != candidate.identity):
                        raise ValueError('ssh_delete_empty_control_not_same_owned_inode')
                    self._check(candidate)
                    self.colima = candidate
                else:
                    self._check(self.colima)
            self.instance = _Control(self.lima_fd,'colima-kil-v3-lab',None,None,None)
            self.state = 'deleting'
            self.guard()
        except (OSError, ValueError) as error:
            self.refuse()
            if candidate is not None and candidate.fd is not None:
                self._owned.remove(candidate.fd); os.close(candidate.fd)
            raise ValueError('ssh_delete_transition_refused') from error

    def finish_deleted(self):
        if self.state != 'deleting': raise ValueError('ssh_delete_transition_unavailable')
        self.guard(); self.state = 'deleted'

    def proof(self):
        if self.state in ('unbound','binding','closed','refused'): return None
        return {'state': self.state, 'port': self.port,
                'colima': self.colima.proof(), 'instance': self.instance.proof()}
