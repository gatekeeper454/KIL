# Compact private HF runtime implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Prepare a fresh exploratory HF runtime whose native sockets fit the pinned Lima pathname cap, without relocating receipts or weakening full-identity ownership.

**Architecture:** Keep receipt authority and compact native runtime authority as two independently retained no-follow ancestry chains. Authenticate a private registry marker and a durable full-digest receipt binding, then preserve unchanged runner/lifecycle contracts. The tightly coupled authority, pure-path compatibility and consumer fixtures constitute one engineering task; independent reviews and the single conditionally approved rehearsal follow it.

**Tech Stack:** Python 3.12.13 standard library, unittest, POSIX retained directory/file descriptors, existing PrivateStore and canonical JSON, pinned macOS/Colima/Lima tooling only for the later root rehearsal.

---

## Scope and commands

Approved design: docs/superpowers/specs/2026-09-16-hf-compact-runtime-design.md.
Working directory: /Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL.
Interpreter: /Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python.
Existing externally managed detached linked worktree is retained. No install, new
worktree, branch move, merge, push, image audit, old-runtime adoption/cleanup or
Ollama operation is part of this plan. No live HF requests are approved.

Production files:

- src/kil/hf_exploratory_runtime.py: private location selection, namespace creation, retained authority, marker/binding authentication and Kind control FD.
- src/kil/hf_exploratory_profile.py: pure compact-shape validation and existing exact live-authority bind.

Tests allowed to change: tests/test_hf_exploratory_runtime.py,
tests/test_hf_exploratory_profile.py, tests/test_hf_exploratory_io.py,
tests/test_hf_exploratory_evidence.py, tests/test_hf_exploratory_native.py.
IO, evidence, Native and CLI production, strict modules, accepted inputs,
historical receipts, citation policy and .gitattributes remain unchanged.
Lineage and generated readers are updated append-only at each substantive gate.

Full required engineering command (actual test count must be recorded):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_exploratory_runtime tests.test_hf_exploratory_profile tests.test_hf_exploratory_evidence tests.test_hf_exploratory_case tests.test_hf_exploratory_inputs tests.test_hf_exploratory_io tests.test_hf_exploratory_native tests.test_v3b2_profile_state tests.test_v3b2_journal tests.test_v4_future_controller_gate tests.test_v3b2_inventory tests.test_v3b2_colima_inventory tests.test_v3b2_runtime_inventory_ownership tests.test_v3b2_bootstrap_inventory tests.test_v3b2_runtime_image_inventory
```

Expected: OK, no errors/failures/ResourceWarning. The previous 425-test result is
not a prediction for the changed suite. Pre-change focused runtime/profile/IO
baseline is 110 tests, OK. The earlier broader discovery citation failure for
four immutable ignored historical Markdown files remains a disclosed limitation;
neither receipts nor exemptions will be rewritten to claim all-green discovery.

## Task 1: Compact authority, pure paths and real short fixtures

### Contract to implement

Keep exact RuntimeAuthority.create(store, run_digest), closed frozen/slotted
constructor and exact adapter checks. Derive production registry privately from
actual passwd home, not environment, as home/.kil-hf. Require real UID equals
effective UID at create and every guard; validate actual home canonical route.
Run root is registry/('r'+full_digest[:16]); full digest and v3b2-full-digest remain
identity. Do not expose caller path/home/binary/environment/CLI overrides.

Before any registry/run allocation and every guard require fsencoded lengths of
runtime/.colima/_lima/colima-kil-v3-lab/ssh.sock.1234567890123456 and the derived
Docker socket each <104. No alias, temp fallback, second label or retry.

Retain complete receipt and runtime ancestry independently from /. Validate exact
store object, canonical .tools/hf-exploratory-private receipt name/full digest,
retained store directory and private parent, store lock UID/0600/regular/single
link. Retain explicit verified store/root handles and a complete expected topology,
not a positional store-sibling root assumption. Named and FD directory identities
are dev/inode/mode/UID; ordinary ancestor timestamps are not immutable. Registry,
run and existing four native homes are owner-0700, created exclusively and fsynced.

Absent registry: exclusive mkdir through retained actual-home parent FD, verify
0700/UID, fsync parent, exclusive 0600 single-link bounded regular registry.json,
complete write and file/directory fsync. Existing registry: reuse only canonical
owner-0700 parent with exact marker; never mark/repair an existing unmarked,
partial, foreign or unsafe directory. No scanning/adoption of old child roots.

Marker exact canonical fields: schema='kil.hf-exploratory-runtime-registry.v1',
uid=int(effective UID), runtime_parent=str(canonical registry). Marker is a closed
namespace form, not attestation or exclusion of arbitrary same-UID code.

One exclusive fresh run mkdir and .colima/_lima, docker-config, runtime-tmp mkdirs;
any preexisting label refuses, including same full digest or different full digest
sharing first 16 hex. No adoption, alternate label, repair, truncation or retry.

Persist runtime-binding.json through exclusive PrivateStore.write before usable
authority. Exact canonical fields: schema='kil.hf-exploratory-runtime-binding.v1',
uid=int(UID), run_digest=full64, run_id='v3b2-'+full64, receipt_path=str(store.path),
registry_path=str(registry), runtime_path=str(root), runtime_identity=dict(device,
inode, mode, uid), four integer stat values from retained root FD. Both files <=8192
bytes. Retain expected bytes and read-only no-follow/nonblocking file handles plus
eight-field file identities (dev/inode/mode/UID/nlink/size/mtime_ns/ctime_ns).

Guard: validate exact type, bool-live state, digest, store, derived paths, full
topology and all named/retained identities; read both marker and binding exactly,
before/after identity checks, owner-0600/regular/single link and exact canonical
expected field types/bytes. After BOTH reads recheck BOTH named/retained file
identities and all directory/store/lock identities. Known OS/shape failures become
ValueError before dispatch. Failure and idempotent close release every acquired FD
once, erase no files/native state and retain partial bootstrap/write state.
Kind-control grammar/bound/exclusivity/fsync/before-after guard remain unchanged,
using explicit verified root FD. Existing properties/environment semantics remain.

Pure ProfilePaths accepts compact r[0-9a-f]{16} whose parent equals private
registry selector; caller home does not choose registry. Preserve legacy offline
saved-evidence shape only; no live legacy constructor/adoption. Bind remains exact
live guarded authority and actual passwd home. Existing two-field documents,
capture/binding schemas, seven-file snapshots and five directory rosters unchanged.
No production consumer changes or new IO after final runner consistency block.

- [ ] **Step 1: Add real short fixture selection and first failing behavior assertions.**

Use this fixture setup in the existing runtime tests and equivalent existing
setUp methods for every consumer that creates RuntimeAuthority. Cleanup registration
order must leave the patch active until retained authorities close. Existing
receipt fixture remains independent; pure offline legacy tests may stay legacy.

```python
self.compact_temp = tempfile.TemporaryDirectory(prefix='k', dir='/private/tmp')
self.addCleanup(self.compact_temp.cleanup)
self.registry = Path(self.compact_temp.name).resolve() / 'k'
self.registry_patch = patch.object(self.runtime, '_registry_parent',
                                  return_value=self.registry, create=True)
self.registry_patch.start()
self.addCleanup(self.registry_patch.stop)
```

First assertion, placed in existing RuntimeTests:

```python
def test_compact_locator_has_full_receipt_identity_and_durable_binding(self):
    import json
    authority = self.authority()
    self.assertEqual(authority.path, self.registry / ('r' + self.digest[:16]))
    self.assertLess(len(os.fsencode(authority.lima / 'colima-kil-v3-lab' /
                                    'ssh.sock.1234567890123456')), 104)
    marker = json.loads((self.registry / 'registry.json').read_bytes())
    self.assertEqual(marker, {
        'schema': 'kil.hf-exploratory-runtime-registry.v1',
        'uid': os.geteuid(), 'runtime_parent': str(self.registry)})
    binding = json.loads((self.store.path / 'runtime-binding.json').read_bytes())
    row = authority.path.stat()
    self.assertEqual(binding, {
        'schema': 'kil.hf-exploratory-runtime-binding.v1', 'uid': os.geteuid(),
        'run_digest': self.digest, 'run_id': 'v3b2-' + self.digest,
        'receipt_path': str(self.store.path), 'registry_path': str(self.registry),
        'runtime_path': str(authority.path), 'runtime_identity': {
            'device': row.st_dev, 'inode': row.st_ino,
            'mode': row.st_mode, 'uid': row.st_uid}})
    authority.guard()
```

Additional first-cycle assertions use actual filesystem state:

```python
def test_existing_unmarked_registry_is_not_repaired(self):
    self.registry.mkdir(mode=0o700)
    with self.assertRaises(ValueError):
        self.runtime.RuntimeAuthority.create(self.store, self.digest)
    self.assertEqual(list(self.registry.iterdir()), [])

def test_marker_drift_refuses_before_adapter(self):
    authority = self.authority()
    marker = self.registry / 'registry.json'
    marker.write_bytes(marker.read_bytes().replace(b'"uid":', b'"foreign_uid":'))
    with self.assertRaises(ValueError):
        self.runtime.ExploratoryColimaCommand(
            Command(('colima', 'version'), 1), authority)
```

- [ ] **Step 2: Run and observe RED before editing production.**

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -W error::ResourceWarning -m unittest tests.test_hf_exploratory_runtime.RuntimeTests.test_compact_locator_has_full_receipt_identity_and_durable_binding tests.test_hf_exploratory_runtime.RuntimeTests.test_existing_unmarked_registry_is_not_repaired
```

Expected actual assertion failures: old sibling path differs from short locator;
existing unmarked fixture is silently ignored by old implementation instead of
refused. Import/setup/typo errors are not accepted RED. Record exact observations.

- [ ] **Step 3: Implement private derivation and retained file authentication.**

The following complete helper code defines the private selector, byte budget and
bounded retained authentication. Integrate these with the existing authority in
the next step; do not weaken filesystem checks to accommodate fixture paths.

```python
from kil.v3b2_profile_state import passwd_home
from kil.v3b2_proofs import canonical

def _registry_parent():
    home = passwd_home()
    if home.resolve(strict=True) != home:
        raise ValueError('runtime_home_not_canonical')
    return home / '.kil-hf'

def _path_budget(path):
    for endpoint in (
            path / '.colima/_lima/colima-kil-v3-lab/ssh.sock.1234567890123456',
            path / '.colima/kil-v3-lab/docker.sock'):
        if len(os.fsencode(endpoint)) >= 104:
            raise ValueError('runtime_socket_path_too_long')

def _file_identity(row):
    return (row.st_dev, row.st_ino, row.st_mode, row.st_uid, row.st_nlink,
            row.st_size, row.st_mtime_ns, row.st_ctime_ns)

def _file_check(parent, name, fd, identity, expected):
    row = os.fstat(fd)
    named = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (not stat.S_ISREG(row.st_mode) or row.st_uid != os.geteuid()
            or stat.S_IMODE(row.st_mode) != 0o600 or row.st_nlink != 1
            or not 0 <= row.st_size <= 8192
            or _file_identity(row) != identity
            or _file_identity(named) != identity
            or type(expected) is not bytes or len(expected) > 8192):
        raise ValueError('runtime_file_identity_changed')

def _file_auth(parent, name, fd, identity, expected):
    _file_check(parent, name, fd, identity, expected)
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    remaining = 8193
    while remaining:
        chunk = os.read(fd, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    if b''.join(chunks) != expected:
        raise ValueError('runtime_file_bytes_changed')
    _file_check(parent, name, fd, identity, expected)
```

- [ ] **Step 4: Implement complete two-chain creation and guard integration.**

Use the complete integration below as the planned authority implementation. Keep
the existing property getters and exact ExploratoryColimaCommand adapter unchanged.
Keep write_control unchanged except replacing its root lookup with self._root_fd.
Tests, not this proposed code, decide whether further minimal corrections are
needed. Any important correction must have observed failing behavior first.

```python
def _layout(store_path, registry, digest):
    result = [(None, '/', False)]
    for part in store_path.parts[1:]:
        result.append((len(result) - 1, part, False))
    store_index = len(result) - 1
    result[store_index - 1] = (*result[store_index - 1][:2], True)
    result[store_index] = (*result[store_index][:2], True)
    result.append((None, '/', False))
    for part in registry.parts[1:]:
        result.append((len(result) - 1, part, False))
    registry_index = len(result) - 1
    result[registry_index] = (*result[registry_index][:2], True)
    result.extend(((registry_index, 'r' + digest[:16], True),
                   (registry_index + 1, '.colima', True),
                   (registry_index + 2, '_lima', True),
                   (registry_index + 1, 'docker-config', True),
                   (registry_index + 1, 'runtime-tmp', True)))
    return tuple(result), store_index, registry_index, registry_index + 1

@dataclass(frozen=True, slots=True, init=False)
class RuntimeAuthority:
    path: Path
    _store: PrivateStore
    _digest: str
    _registry: Path
    _anchors: tuple
    _store_fd: int
    _root_fd: int
    _lock_identity: tuple
    _files: tuple
    _closed: bool

    def __init__(self):
        raise ValueError('runtime_authority_requires_create')

    @classmethod
    def create(cls, store, run_digest):
        from kil.hf_exploratory_io import PrivateStore
        anchors, files = [], []
        def retain(parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=parent)
            try:
                identity = _identity(os.fstat(fd))
            except BaseException:
                os.close(fd)
                raise
            anchors.append((parent, name, fd, identity))
            return fd
        def fresh(parent, name):
            os.mkdir(name, mode=0o700, dir_fd=parent)
            os.fsync(parent)
            fd = retain(parent, name)
            row = os.fstat(fd)
            if row.st_uid != os.geteuid() or stat.S_IMODE(row.st_mode) != 0o700:
                raise ValueError('runtime_directory_not_private')
            return fd
        def retain_file(parent, name, expected):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=parent)
            try:
                identity = _file_identity(os.fstat(fd))
            except BaseException:
                os.close(fd)
                raise
            files.append((parent, name, fd, identity, expected))
            _file_auth(*files[-1])
        try:
            if (cls is not RuntimeAuthority or os.getuid() != os.geteuid()
                    or type(store) is not PrivateStore or type(run_digest) is not str
                    or re.fullmatch(r'[0-9a-f]{64}', run_digest) is None
                    or not isinstance(store.path, Path) or not store.path.is_absolute()
                    or '..' in store.path.parts
                    or store.path.resolve(strict=True) != store.path
                    or store.path.name != 'hf-exploratory-' + run_digest
                    or store.path.parent.parts[-2:] != ('.tools', 'hf-exploratory-private')
                    or store._directory is None or store._lock is None):
                raise ValueError('invalid_runtime_store_authority')
            home = passwd_home()
            if home.resolve(strict=True) != home:
                raise ValueError('runtime_home_not_canonical')
            registry = _registry_parent()
            if (not isinstance(registry, Path) or not registry.is_absolute()
                    or '..' in registry.parts or registry == Path('/')
                    or registry.parent.resolve(strict=True) != registry.parent):
                raise ValueError('invalid_runtime_registry')
            path = registry / ('r' + run_digest[:16])
            _path_budget(path)
            layout, store_index, registry_index, root_index = _layout(
                store.path, registry, run_digest)
            for parent_index, name, private in layout[:store_index + 1]:
                parent = None if parent_index is None else anchors[parent_index][2]
                fd = retain(parent, name)
                row = os.fstat(fd)
                if private and (row.st_uid != os.geteuid()
                                or stat.S_IMODE(row.st_mode) != 0o700):
                    raise ValueError('runtime_store_not_private')
            store_fd = anchors[store_index][2]
            if _identity(os.fstat(store._directory)) != anchors[store_index][3]:
                raise ValueError('runtime_store_reanchored')
            lock_identity = _identity(os.fstat(store._lock))
            for row in (os.fstat(store._lock),
                        os.stat('lock', dir_fd=store_fd, follow_symlinks=False)):
                if (_identity(row) != lock_identity or not stat.S_ISREG(row.st_mode)
                        or row.st_uid != os.geteuid() or row.st_nlink != 1
                        or stat.S_IMODE(row.st_mode) != 0o600):
                    raise ValueError('runtime_store_lock_reanchored')
            for parent_index, name, private in layout[store_index + 1:registry_index]:
                parent = None if parent_index is None else anchors[parent_index][2]
                retain(parent, name)
            parent_fd = anchors[registry_index - 1][2]
            try:
                os.stat(registry.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                registry_fd = fresh(parent_fd, registry.name)
                marker = canonical({'schema': 'kil.hf-exploratory-runtime-registry.v1',
                                    'uid': os.geteuid(), 'runtime_parent': str(registry)})
                fd = os.open('registry.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW, 0o600, dir_fd=registry_fd)
                try:
                    row = os.fstat(fd)
                    if (not stat.S_ISREG(row.st_mode) or row.st_uid != os.geteuid()
                            or row.st_nlink != 1 or stat.S_IMODE(row.st_mode) != 0o600):
                        raise ValueError('runtime_marker_not_private')
                    view = memoryview(marker)
                    while view:
                        count = os.write(fd, view)
                        if count <= 0:
                            raise OSError('short_runtime_marker_write')
                        view = view[count:]
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.fsync(registry_fd)
            else:
                registry_fd = retain(parent_fd, registry.name)
                row = os.fstat(registry_fd)
                if row.st_uid != os.geteuid() or stat.S_IMODE(row.st_mode) != 0o700:
                    raise ValueError('runtime_registry_not_private')
                marker = canonical({'schema': 'kil.hf-exploratory-runtime-registry.v1',
                                    'uid': os.geteuid(), 'runtime_parent': str(registry)})
            retain_file(registry_fd, 'registry.json', marker)
            for parent_index, name, private in layout[root_index:]:
                fresh(anchors[parent_index][2], name)
            root_fd = anchors[root_index][2]
            row = os.fstat(root_fd)
            binding = canonical({
                'schema': 'kil.hf-exploratory-runtime-binding.v1',
                'uid': os.geteuid(), 'run_digest': run_digest,
                'run_id': 'v3b2-' + run_digest, 'receipt_path': str(store.path),
                'registry_path': str(registry), 'runtime_path': str(path),
                'runtime_identity': {'device': row.st_dev, 'inode': row.st_ino,
                                     'mode': row.st_mode, 'uid': row.st_uid}})
            store.write('runtime-binding.json', binding)
            retain_file(store_fd, 'runtime-binding.json', binding)
            authority = object.__new__(cls)
            for name, value in (
                    ('path', path), ('_store', store), ('_digest', run_digest),
                    ('_registry', registry), ('_anchors', tuple(anchors)),
                    ('_store_fd', store_fd), ('_root_fd', root_fd),
                    ('_lock_identity', lock_identity), ('_files', tuple(files)),
                    ('_closed', False)):
                object.__setattr__(authority, name, value)
            authority.guard()
            return authority
        except BaseException as error:
            for parent, name, fd, identity, expected in reversed(files):
                os.close(fd)
            for parent, name, fd, identity in reversed(anchors):
                os.close(fd)
            if isinstance(error, (OSError, AttributeError, KeyError, TypeError, IndexError)):
                raise ValueError('runtime_authority_unavailable') from error
            raise

    def _guard_directories(self):
        from kil.hf_exploratory_io import PrivateStore
        store = self._store
        if (type(self) is not RuntimeAuthority or self._closed is not False
                or os.getuid() != os.geteuid() or type(store) is not PrivateStore
                or type(self._digest) is not str
                or re.fullmatch(r'[0-9a-f]{64}', self._digest) is None
                or not isinstance(store.path, Path) or not store.path.is_absolute()
                or '..' in store.path.parts
                or store.path.name != 'hf-exploratory-' + self._digest
                or store.path.parent.parts[-2:] != ('.tools', 'hf-exploratory-private')
                or self._registry != _registry_parent()
                or self.path != self._registry / ('r' + self._digest[:16])
                or store._directory is None or store._lock is None):
            raise ValueError('invalid_or_closed_runtime_authority')
        home = passwd_home()
        if home.resolve(strict=True) != home:
            raise ValueError('runtime_home_not_canonical')
        _path_budget(self.path)
        layout, store_index, registry_index, root_index = _layout(
            store.path, self._registry, self._digest)
        if (type(self._anchors) is not tuple or len(self._anchors) != len(layout)
                or self._store_fd != self._anchors[store_index][2]
                or self._root_fd != self._anchors[root_index][2]):
            raise ValueError('substituted_runtime_anchors')
        for anchor, (parent_index, name, private) in zip(self._anchors, layout):
            parent, actual_name, fd, identity = anchor
            expected_parent = None if parent_index is None else self._anchors[parent_index][2]
            if (actual_name != name or parent != expected_parent
                    or _identity(os.fstat(fd)) != identity
                    or _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity
                    or not stat.S_ISDIR(identity[2])
                    or (private and (identity[3] != os.geteuid()
                                     or stat.S_IMODE(identity[2]) != 0o700))):
                raise ValueError('runtime_namespace_changed')
        if _identity(os.fstat(store._directory)) != self._anchors[store_index][3]:
            raise ValueError('runtime_store_reanchored')
        for row in (os.fstat(store._lock),
                    os.stat('lock', dir_fd=self._store_fd, follow_symlinks=False)):
            if (_identity(row) != self._lock_identity or not stat.S_ISREG(row.st_mode)
                    or row.st_uid != os.geteuid() or row.st_nlink != 1
                    or stat.S_IMODE(row.st_mode) != 0o600):
                raise ValueError('runtime_store_lock_reanchored')
        return registry_index, root_index

    def guard(self):
        try:
            registry_index, root_index = self._guard_directories()
            identity = self._anchors[root_index][3]
            expected = (
                (self._anchors[registry_index][2], 'registry.json', canonical({
                    'schema': 'kil.hf-exploratory-runtime-registry.v1',
                    'uid': os.geteuid(), 'runtime_parent': str(self._registry)})),
                (self._store_fd, 'runtime-binding.json', canonical({
                    'schema': 'kil.hf-exploratory-runtime-binding.v1',
                    'uid': os.geteuid(), 'run_digest': self._digest,
                    'run_id': 'v3b2-' + self._digest, 'receipt_path': str(self._store.path),
                    'registry_path': str(self._registry), 'runtime_path': str(self.path),
                    'runtime_identity': dict(zip(('device', 'inode', 'mode', 'uid'), identity))})))
            if type(self._files) is not tuple or len(self._files) != 2:
                raise ValueError('substituted_runtime_files')
            for record, (parent, name, payload) in zip(self._files, expected):
                if (type(record) is not tuple or len(record) != 5
                        or record[0] != parent or record[1] != name or record[4] != payload):
                    raise ValueError('substituted_runtime_files')
                _file_auth(*record)
            for record in self._files:
                _file_check(*record)
            self._guard_directories()
        except (OSError, AttributeError, KeyError, TypeError, IndexError) as error:
            raise ValueError('runtime_authority_unavailable') from error

    def close(self):
        if not self._closed:
            object.__setattr__(self, '_closed', True)
            for parent, name, fd, identity, expected in reversed(self._files):
                os.close(fd)
            for parent, name, fd, identity in reversed(self._anchors):
                os.close(fd)
```

- [ ] **Step 5: Add failing pure compact-path compatibility assertion, then implement that predicate.**

Existing profile test with private selector patched to self.registry:

```python
def test_compact_paths_round_trip_without_live_authority(self):
    runtime = self.registry / ('r' + 'a' * 16)
    paths = self.module.ProfilePaths(strict.passwd_home(), runtime)
    self.assertEqual(self.module._paths(paths.document()), paths)
    with self.assertRaises(ValueError):
        self.module.ProfilePaths(self.root, self.root / runtime.name)
```

Observe RED: existing legacy-only predicate refuses compact shape. Then import
the runtime module as runtime_namespace and replace only the legacy-only
namespace predicate with:

```python
compact = (re.fullmatch(r'r[0-9a-f]{16}', self.runtime.name) is not None
           and self.runtime.parent == runtime_namespace._registry_parent())
legacy = (re.fullmatch(r'hf-exploratory-runtime-[0-9a-f]{64}', self.runtime.name)
          is not None and self.runtime.parent.parts[-2:] ==
          ('.tools', 'hf-exploratory-private'))
if not (compact or legacy):
    raise ProfileStateError('exploratory runtime namespace is invalid')
```

- [ ] **Step 6: Extend real regression coverage in small observed RED/GREEN cycles.**

Concrete collision/safe-registry-reuse tests in RuntimeTests:

```python
def test_safe_registry_reuse_does_not_adopt_previous_run(self):
    first = self.authority()
    marker = (self.registry / 'registry.json').read_bytes()
    digest = 'b' * 64
    store = PrivateStore(self.parent / ('hf-exploratory-' + digest))
    self.addCleanup(store.close)
    second = self.runtime.RuntimeAuthority.create(store, digest)
    self.addCleanup(second.close)
    self.assertNotEqual(first.path, second.path)
    self.assertEqual((self.registry / 'registry.json').read_bytes(), marker)
    first.guard()
    second.guard()

def test_different_full_digest_prefix_collision_refuses_without_second_label(self):
    first = self.authority()
    digest = self.digest[:16] + 'b' * 48
    store = PrivateStore(self.parent / ('hf-exploratory-' + digest))
    self.addCleanup(store.close)
    before = sorted(path.name for path in self.registry.iterdir())
    with self.assertRaises(ValueError):
        self.runtime.RuntimeAuthority.create(store, digest)
    self.assertEqual(sorted(path.name for path in self.registry.iterdir()), before)
    self.assertFalse((store.path / 'runtime-binding.json').exists())
    first.guard()
```

Add finite table-driven variants, with real files/metadata, to existing tests:
unsafe registry directory/marker type, symlink/hardlink/mode/bytes/canonical field
types; binding exact fields/types/bytes/replacement/link/mode; both ancestry
replacement; digest/store/root/retained-handle substitution; UID mismatch and
103/104-byte budget boundaries; failed bootstrap/binding/close descriptor counts;
Kind control explicit-root placement; IO known marker/binding drift produces
ValueError with zero capture; real compact snapshots/full-roster consumers.
Use the existing guard-drift/control/adaptor tests as the concrete table pattern,
not production-only test hooks. Every new fix must be preceded by its failing
assertion. Do not bypass guard/authentication or allocate the real home registry.

- [ ] **Step 7: Verify focused and all 15 required modules, self-review, log and commit exact paths.**

Run the full command above, then renderer/check and git diff --check. Compare the
entire predecessor lineage byte prefix before staging. Record actual RED/GREEN
counts, failures/corrections and limitations in the next dated actual-EOF entry.
The implementer has exclusive source/test/lineage/render/commit writer authority
only until explicitly reporting RELEASED. Stage only actually changed allowed
source/test paths and lineage Markdown/reader; commit and report exact HEAD,
clean status, tests, self-review and concerns. Do not touch plan/spec or native state.

## Review and root engineering gates

- [ ] Fresh SPEC reviewer independently inspects code against the complete approved contract, with no production edits and a separate append-only review log.
- [ ] Only after SPEC PASS, fresh QUALITY reviewer checks bounded FD lifecycle, maintainability, real tests and consumer integration. Important findings return to implementer for observed RED/GREEN correction and re-review.
- [ ] Fresh final reviewer checks the composed whole change and unchanged protected paths.
- [ ] Root runs fresh 15-module regression, reader check, predecessor-prefix proof, protected source hashes and strict diff check. Checkpoint all engineering and plan/log documents, then require exact clean HEAD before native preparation.

## One conditional root-only request-free rehearsal

- [ ] With all engineering gates PASS, root checks reviewed source and accepted inputs using unchanged APIs and outside-sandbox source gate. No filtered Git warnings, runtime gate bypass or new image audit.
- [ ] Root uses LabLock, verify_inputs, PrivateStore, BoundedRunner and ExploratoryLifecycle with constant mode='rehearsal', fresh nonce and exact clean HEAD. Never call CLI main, whose successful rehearsal falls through into action.
- [ ] Allocate only one fresh derived compact private runtime. Preserve every failed earlier receipt/runtime/disk. No retry, adoption or unbound stop/delete if inconclusive.
- [ ] Verify actual report, zero HF intents AND attempts, all receipt checksums, bracketed protected default/global state and bounded runtime leftovers. Successful readiness requires complete retained rehearsal AND verified owned teardown; persistent registry/control leftovers are not filesystem_fully_removed.
- [ ] Append actual outcome and remaining gate, render/check readers, checkpoint clean source and report result. Live HF three-track action requires separate explicit approval even if rehearsal completes. Platform provenance/full Kind-Calico acceptance remain unverified/false and accepted local Envoy unchanged.

## Plan self-review and execution selection

Root checked every spec section against Task 1, reviews and native gates: selected
location/full identity, bootstrap/reuse/collision, exact marker/binding, two-chain
FD and byte auth, path cap, compatibility, limited file scope, real fixture safety,
single rehearsal and claim exclusions are mapped. Helper/type names match their
uses; complete proposed integration retains existing unchanged property/control/
adapter code. No unresolved implementation placeholders or dynamic fallbacks.
Same-session subagent-driven execution is selected for the already requested
test-first workflow; no additional design approval is required by this plan.

KTP citation: [canonical CITATION.cff](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
