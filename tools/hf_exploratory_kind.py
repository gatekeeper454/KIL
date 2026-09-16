#!/usr/bin/env python3
"""One separate HF request-free rehearsal, then one fresh exploratory action."""
import argparse
from contextlib import ExitStack
import fcntl
from hashlib import sha256
import os
from pathlib import Path
import secrets
import stat
import sys

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / 'src'))

from kil.hf_exploratory_inputs import verify_inputs
from kil.hf_exploratory_io import BoundedRunner, PrivateStore
from kil.hf_exploratory_native import ExploratoryLifecycle, check_source
from kil.v3b2_profile_state import _parent
from kil.v3b2_proofs import canonical


class LabLock:
    """Durable fd-anchored private ancestry; flock is not external exclusion."""
    def __init__(self, repository):
        self.repository = repository
        self.path = repository / '.tools/hf-exploratory-private'
        self.stack = ExitStack()
        self.anchors = []
        self.lock = None

    def __enter__(self):
        try:
            if not self.repository.is_absolute() or self.repository.resolve(strict=True) != self.repository:
                raise ValueError('unsafe_repository_ancestry')
            repository_fd = self.stack.enter_context(_parent(self.repository / '.hf-lock-observation'))
            if repository_fd is None:
                raise ValueError('repository_unavailable')
            self.anchors.append((self.repository, repository_fd))
            parent = repository_fd
            for name, path, private in [('.tools', self.repository/'.tools', False),
                                        ('hf-exploratory-private', self.path, True)]:
                try:
                    os.mkdir(name, mode=0o700, dir_fd=parent)
                except FileExistsError:
                    pass
                else:
                    os.fsync(parent)
                descriptor = os.open(name, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW, dir_fd=parent)
                self.stack.callback(os.close, descriptor)
                row = os.fstat(descriptor)
                if (not stat.S_ISDIR(row.st_mode) or (private and
                        (stat.S_IMODE(row.st_mode)!=0o700 or row.st_uid!=os.geteuid()))):
                    raise ValueError('unsafe_private_parent_permissions')
                self.anchors.append((path, descriptor))
                parent = descriptor
            try:
                self.lock = os.open('profile.lock', os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                                    0o600, dir_fd=parent)
            except FileExistsError:
                self.lock = os.open('profile.lock', os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=parent)
            self.stack.callback(os.close, self.lock)
            row = os.fstat(self.lock)
            if not stat.S_ISREG(row.st_mode) or stat.S_IMODE(row.st_mode)!=0o600 or row.st_uid!=os.geteuid() or row.st_nlink!=1:
                raise ValueError('unsafe_profile_lock')
            os.fsync(self.lock)
            os.fsync(parent)
            fcntl.flock(self.lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.guard()
            return self
        except BaseException:
            self.stack.close()
            raise

    def guard(self):
        for path, descriptor in self.anchors:
            current = os.stat(path, follow_symlinks=False)
            retained = os.fstat(descriptor)
            if (not stat.S_ISDIR(current.st_mode) or path.resolve(strict=True)!=path
                    or (current.st_dev,current.st_ino)!=(retained.st_dev,retained.st_ino)):
                raise ValueError('private_parent_replaced')
        named = os.stat('profile.lock',dir_fd=self.anchors[-1][1],follow_symlinks=False)
        retained = os.fstat(self.lock)
        if (named.st_dev,named.st_ino,named.st_mode)!=(retained.st_dev,retained.st_ino,retained.st_mode):
            raise ValueError('profile_lock_replaced')

    def __exit__(self, *exception):
        self.stack.close()


def main(argv=None, *, repository=REPOSITORY):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--reviewed-source',required=True)
    parser.add_argument('--tools',required=True,type=Path)
    parser.add_argument('--kil-archive',required=True,type=Path)
    arguments = parser.parse_args(argv)
    for path in (arguments.tools,arguments.kil_archive):
        if not path.is_absolute() or '..' in path.parts or path.resolve()!=path:
            raise ValueError('inputs_must_be_absolute_canonical_paths')
    # This gate precedes .tools, private parents, locks, and profile mutation.
    check_source(repository,arguments.reviewed_source)
    with LabLock(repository) as lock:
        for mode in ('rehearsal','action'):
            lock.guard()
            check_source(repository,arguments.reviewed_source)
            nonce = secrets.token_hex(32)
            digest = sha256(canonical({'source_commit':arguments.reviewed_source,
                                      'mode':mode,'nonce':nonce})).hexdigest()
            inputs = verify_inputs(repository,arguments.tools,arguments.kil_archive,digest)
            lock.guard()
            store = PrivateStore(lock.path/('hf-exploratory-'+digest))
            try:
                runner = BoundedRunner(repository,inputs)
                lifecycle = ExploratoryLifecycle(repository,inputs,store,runner,arguments.reviewed_source,mode)
                report = lifecycle.execute()
                lock.guard()
                print(canonical({'mode':mode,'private_path':str(store.path),'status':report['status']}).decode().strip())
            finally:
                store.close()
            if report['status']!='complete' or report['owned_teardown'] is not True:
                raise SystemExit(1)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
