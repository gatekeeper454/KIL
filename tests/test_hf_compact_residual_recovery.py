import importlib.util
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from kil.v3b2_proofs import canonical
from kil.v3b2_profile_state import _read
from kil.v3b2_controller import CommandResult


REPOSITORY = Path(__file__).resolve().parents[1]
TOOL_PATH = REPOSITORY / 'tools' / 'hf_compact_residual_recovery.py'


def load_tool():
    if not TOOL_PATH.is_file():
        raise AssertionError('fixed-target recovery tool is missing')
    for location in (str(REPOSITORY), str(REPOSITORY / 'src')):
        if location not in sys.path:
            sys.path.insert(0, location)
    spec = importlib.util.spec_from_file_location('hf_compact_residual_recovery', TOOL_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError('fixed-target recovery tool is not loadable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FileProofTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.temporary = tempfile.TemporaryDirectory(prefix='kil-r-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.payload = b'exact original control\n'
        self.control = self.root / 'control'
        self.control.write_bytes(self.payload)
        self.control.chmod(0o600)
        self.assertEqual(stat.S_IMODE(self.control.stat().st_mode), 0o600)
        self.assertEqual(self.control.stat().st_uid, os.geteuid())

    def files(self):
        result = self.tool._Files()
        self.addCleanup(result.close)
        return result

    def test_exact_bounded_read_guard_and_close_lifecycle(self):
        files = self.files()
        self.assertEqual(files.read(self.control, len(self.payload), 0o600, os.geteuid()),
                         self.payload)
        files.guard()
        descriptors = [fd for fd, _ in files.directories.values()]
        descriptors.extend(record[1] for record in files.files)
        files.close()
        files.close()
        with self.assertRaises(ValueError):
            files.guard()
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_file_content_metadata_link_and_name_substitutions_refuse(self):
        cases = []
        for kind in ('changed', 'mode', 'hardlink', 'replacement'):
            with self.subTest(kind=kind):
                for stale in (self.root / 'additional-link', self.root / 'original'):
                    stale.unlink(missing_ok=True)
                self.control.unlink(missing_ok=True)
                self.control.write_bytes(self.payload)
                self.control.chmod(0o600)
                files = self.files()
                files.read(self.control, len(self.payload), 0o600, os.geteuid())
                if kind == 'changed':
                    self.control.write_bytes(b'changed original data\n')
                elif kind == 'mode':
                    self.control.chmod(0o644)
                elif kind == 'hardlink':
                    os.link(self.control, self.root / 'additional-link')
                else:
                    moved = self.root / 'original'
                    self.control.rename(moved)
                    self.control.write_bytes(self.payload)
                    self.control.chmod(0o600)
                with self.assertRaises(ValueError):
                    files.guard()
                cases.append(files)
        self.assertEqual(len(cases), 4)

    def test_symlink_loop_and_wrong_uid_refuse_read(self):
        loop = self.root / 'loop'
        loop.symlink_to(loop)
        with self.assertRaises(ValueError):
            self.files().read(loop, len(self.payload), 0o600, os.geteuid())
        with self.assertRaises(ValueError):
            self.files().read(self.control, len(self.payload), 0o600, os.geteuid() + 1)

    def test_closed_proof_refuses_read_and_directory_before_opening_descriptors(self):
        files = self.files()
        files.close()
        opened = []
        real_open = os.open

        def tracked_open(*args, **kwargs):
            opened.append(args[0])
            return real_open(*args, **kwargs)

        with patch.object(self.tool.os, 'open', side_effect=tracked_open):
            with self.assertRaises(ValueError):
                files.directory(self.root)
            with self.assertRaises(ValueError):
                files.read(self.control, len(self.payload), 0o600, os.geteuid())
        self.assertEqual(opened, [])

    def test_private_directory_binds_fixed_tool_uid_and_private_mode(self):
        private = self.root / 'private'
        private.mkdir(mode=0o700)
        files = self.files()
        with patch.object(self.tool, 'UID', os.geteuid()):
            self.assertIsInstance(files.directory(private, private=True), int)
        with patch.object(self.tool, 'UID', os.geteuid() + 1):
            with self.assertRaises(ValueError):
                files.directory(private, private=True)
        private.chmod(0o755)
        with patch.object(self.tool, 'UID', os.geteuid()):
            with self.assertRaises(ValueError):
                files.directory(private, private=True)

    def test_parent_rename_and_replacement_refuses(self):
        parent = self.root / 'parent'
        parent.mkdir(mode=0o700)
        child = parent / 'control'
        child.write_bytes(self.payload)
        child.chmod(0o600)
        files = self.files()
        files.read(child, len(self.payload), 0o600, os.geteuid())
        moved = self.root / 'moved-parent'
        parent.rename(moved)
        parent.mkdir(mode=0o700)
        replacement = parent / 'control'
        replacement.write_bytes(self.payload)
        replacement.chmod(0o600)
        with self.assertRaises(ValueError):
            files.guard()

    def test_read_refuses_substitution_after_bounded_authentication_io(self):
        files = self.files()
        real_read_regular = self.tool.read_regular
        moved = self.root / 'authenticated-original'

        def read_then_substitute(path, maximum):
            payload = real_read_regular(path, maximum)
            path.rename(moved)
            path.write_bytes(payload)
            path.chmod(0o600)
            return payload

        with patch.object(self.tool, 'read_regular', side_effect=read_then_substitute):
            with self.assertRaises(ValueError):
                files.read(self.control, len(self.payload), 0o600, os.geteuid())

    def test_guard_rechecks_first_file_after_later_retained_fd_io(self):
        first = self.root / 'first'
        second = self.root / 'second'
        first.write_bytes(b'first control\n')
        second.write_bytes(b'second control\n')
        first.chmod(0o600)
        second.chmod(0o600)
        files = self.files()
        files.read(first, 64, 0o600, os.geteuid())
        files.read(second, 64, 0o600, os.geteuid())
        first_fd = files.files[0][1]
        second_fd = files.files[1][1]
        real_read = os.read
        replacement_done = False

        def read_then_replace_first(fd, count):
            nonlocal replacement_done
            payload = real_read(fd, count)
            if fd == second_fd and payload == b'' and not replacement_done:
                replacement_done = True
                first.rename(self.root / 'first-original')
                first.write_bytes(b'first control\n')
                first.chmod(0o600)
            return payload

        with patch.object(self.tool.os, 'read', side_effect=read_then_replace_first):
            with self.assertRaises(ValueError):
                files.guard()
        self.assertTrue(replacement_done)
        self.assertEqual(os.fstat(first_fd).st_nlink, 1)

    def test_guard_refuses_replaced_retained_file_descriptor(self):
        first = self.root / 'first'
        replacement = self.root / 'replacement'
        first.write_bytes(b'first control\n')
        replacement.write_bytes(b'replacement control\n')
        first.chmod(0o600)
        replacement.chmod(0o600)
        files = self.files()
        files.read(first, 64, 0o600, os.geteuid())
        retained_fd = files.files[0][1]
        replacement_fd = os.open(replacement, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        self.addCleanup(os.close, replacement_fd)
        os.dup2(replacement_fd, retained_fd)
        with self.assertRaises(ValueError):
            files.guard()


class ReceiptFixture:
    """A real, owned immutable-receipt shape; no production authority is mocked."""
    def receipt_fixture(self):
        root = Path(self.temporary.name).resolve()
        receipt = root / 'receipt'
        receipt.mkdir(mode=0o700)
        payloads = {}
        for index in range(46):
            name = 'file-%04d.json' % index
            payload = b'{}\n'
            path = receipt / name
            path.write_bytes(payload)
            path.chmod(0o600)
            payloads[name] = payload
        manifest = b''.join(
            hashlib.sha256(payload).hexdigest().encode() + b'  ' + name.encode() + b'\n'
            for name, payload in sorted(payloads.items())
        )
        (receipt / 'SHA256SUMS').write_bytes(manifest)
        (receipt / 'SHA256SUMS').chmod(0o600)
        return receipt, payloads, manifest


class ReceiptTests(unittest.TestCase, ReceiptFixture):
    def setUp(self):
        self.tool = load_tool()
        self.temporary = tempfile.TemporaryDirectory(prefix='kil-receipt-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.receipt, self.payloads, self.manifest = self.receipt_fixture()

    def proof(self):
        proof = self.tool._Files()
        self.addCleanup(proof.close)
        return proof

    def authenticated(self):
        # This assertion intentionally fails on Task 1 because the API is absent.
        self.assertTrue(hasattr(self.tool, '_receipt'), 'Task 2 receipt API is required')
        with patch.multiple(self.tool, RECEIPT=self.receipt, UID=os.geteuid(),
                            MANIFEST_PIN=(hashlib.sha256(self.manifest).hexdigest(), len(self.manifest))):
            return self.tool._receipt(self.proof())

    def test_receipt_authenticates_exact_owned_manifest_and_files(self):
        self.assertEqual(self.authenticated(), self.payloads)

    def test_receipt_refuses_count_duplicate_traversal_and_malformed_manifest(self):
        self.assertTrue(hasattr(self.tool, '_receipt'), 'Task 2 receipt API is required')
        cases = {
            'count': self.manifest.rsplit(b'\n', 2)[0] + b'\n',
            'duplicate': b'\n'.join([*self.manifest.splitlines()[:-1], self.manifest.splitlines()[0]]) + b'\n',
            'traversal': self.manifest.replace(b'file-0000.json', b'../outside', 1),
            'malformed': self.manifest.replace(b'  file-0000.json\n', b' file-0000.json\n', 1),
            'self': self.manifest.replace(b'file-0000.json', b'SHA256SUMS', 1),
            'bad-name': self.manifest.replace(b'file-0000.json', b'.hidden', 1),
        }
        for name, fixture in cases.items():
            with self.subTest(name=name):
                manifest = self.receipt / 'SHA256SUMS'
                manifest.write_bytes(fixture); manifest.chmod(0o600)
                with patch.multiple(self.tool, RECEIPT=self.receipt, UID=os.geteuid(),
                                    MANIFEST_PIN=(hashlib.sha256(fixture).hexdigest(), len(fixture))):
                    with self.assertRaises(ValueError): self.tool._receipt(self.proof())
                manifest.write_bytes(self.manifest); manifest.chmod(0o600)

    def test_receipt_refuses_changed_file_metadata_links_and_missing_entries(self):
        path = self.receipt / 'file-0000.json'
        for kind in ('changed', 'mode', 'hardlink', 'symlink', 'missing'):
            with self.subTest(kind=kind):
                path.unlink(missing_ok=True)
                path.write_bytes(b'{}\n'); path.chmod(0o600)
                extra = self.receipt / 'extra'
                extra.unlink(missing_ok=True)
                if kind == 'changed': path.write_bytes(b'{ }\n')
                elif kind == 'mode': path.chmod(0o644)
                elif kind == 'hardlink': os.link(path, extra)
                elif kind == 'symlink': path.unlink(); path.symlink_to('file-0001.json')
                elif kind == 'missing': path.unlink()
                with self.assertRaises(ValueError): self.authenticated()

    def test_receipt_refuses_unbounded_sparse_regular_file(self):
        path = self.receipt / 'file-0000.json'
        with path.open('wb') as stream: stream.truncate(self.tool.MAXIMUM + 1)
        path.chmod(0o600)
        rows = self.manifest.splitlines()
        rows[0] = hashlib.sha256(path.read_bytes()).hexdigest().encode() + b'  file-0000.json'
        self.manifest = b'\n'.join(rows) + b'\n'
        (self.receipt / 'SHA256SUMS').write_bytes(self.manifest)
        (self.receipt / 'SHA256SUMS').chmod(0o600)
        with self.assertRaises(ValueError): self.authenticated()

    def test_receipt_refuses_wrong_expected_private_uid(self):
        with patch.multiple(self.tool, RECEIPT=self.receipt, UID=os.geteuid() + 1,
                            MANIFEST_PIN=(hashlib.sha256(self.manifest).hexdigest(), len(self.manifest))):
            with self.assertRaisesRegex(ValueError, 'recovery_directory_not_private'):
                self.tool._receipt(self.proof())


class RetainedFixture:
    """Private, no-follow fixture namespace with a real sparse saved profile."""
    def retained_fixture(self):
        from kil import hf_exploratory_profile as profile
        from tests.test_hf_exploratory_native import create_native_profile
        root = Path(self.temporary.name).resolve()
        home = root / 'home'; home.mkdir(mode=0o700)
        registry = root / 'registry'; registry.mkdir(mode=0o700)
        digest = 'a' * 64
        runtime = registry / ('r' + digest[:16]); runtime.mkdir(mode=0o700)
        selector = patch.object(profile.runtime_module, '_registry_parent', return_value=registry)
        selector.start(); self.addCleanup(selector.stop)
        for directory in (runtime / '.colima', runtime / '.colima/_lima',
                          runtime / 'docker-config', runtime / 'runtime-tmp'):
            directory.mkdir(mode=0o700)
        paths = profile.ProfilePaths(home, runtime)
        create_native_profile(paths)
        (paths.colima / '_store').mkdir(mode=0o700)
        paths.store.write_bytes(b'{}\n'); paths.store.chmod(0o600)
        (paths.colima / 'ssh_config').write_bytes(b'Host *\n'); (paths.colima / 'ssh_config').chmod(0o600)
        for directory in (paths.lima / '_config', paths.lima / '_networks'):
            directory.mkdir(mode=0o700)
        (runtime / 'docker-config/contexts').mkdir(mode=0o700)
        (runtime / 'kind-config.yaml').write_bytes(b'apiVersion: kind.x-k8s.io/v1alpha4\n')
        (runtime / 'kind-config.yaml').chmod(0o600)
        for directory in (paths.profile, paths.instance, paths.disk): directory.chmod(0o700)
        for file in (paths.profile / 'colima.yaml', paths.instance / 'colima.yaml',
                     paths.instance / 'lima.yaml'):
            file.chmod(0o644)
        for parent, names in ((paths.profile, ('docker.sock', 'containerd.sock')),
                              (paths.instance, ('ha.pid', 'ha.sock', 'ssh.sock', 'vz.pid'))):
            for name in names:
                (parent / name).write_bytes(b'fixture control\n')
                (parent / name).chmod(0o600)
        (paths.profile / 'ordinary-control').write_bytes(b'fixture ordinary control\n')
        (paths.profile / 'ordinary-control').chmod(0o600)
        if getattr(self, 'include_native_logs', False):
            for name in ('ha.stdout.log', 'ha.stderr.log', 'serialv.log'):
                (paths.instance / name).write_bytes(b'original log\n')
                (paths.instance / name).chmod(0o600)
        original = profile.capture(paths)
        binding = profile.creation_binding(paths.document(), original)
        receipt_parent = root / 'receipts'; receipt_parent.mkdir(mode=0o700)
        receipt = receipt_parent / ('hf-exploratory-' + digest); receipt.mkdir(mode=0o700)
        root_id = (runtime.stat().st_dev, runtime.stat().st_ino, runtime.stat().st_mode, os.geteuid())
        marker = canonical({'schema': 'kil.hf-exploratory-runtime-registry.v1', 'uid': os.geteuid(),
                            'runtime_parent': str(registry)})
        (registry / 'registry.json').write_bytes(marker); (registry / 'registry.json').chmod(0o600)
        leftovers = {'schema': 'kil.hf-exploratory-runtime-leftovers.v1', 'observed_only': True,
                     'partial': True, 'scope': 'named namespace directories only',
                     'runtime_path': str(runtime), 'directories': [
                         {'runtime_path': str(path), 'observation': _read(path, directory_only=True)}
                         for path in (runtime, paths.colima, paths.lima, runtime / 'docker-config', paths.tmp)]}
        report = {'schema_version': 'kil.hf-exploratory-report.v1', 'run_id': 'v3b2-' + digest,
                  'source_commit': self.tool.SOURCE, 'mode': 'rehearsal', 'status': 'inconclusive',
                  'manual_recovery': True, 'request_intent_count': 0, 'request_attempt_count': 0,
                  'joined_results': [], 'paths': {'actual_default_home': str(home), 'receipt': str(receipt),
                                                    'runtime': str(runtime)},
                  'profile_resources': {'actual_creation_bound': True}, 'profile_binding': binding,
                  'runtime_leftovers': leftovers}
        records = {
            'runtime-binding.json': canonical({'schema': 'kil.hf-exploratory-runtime-binding.v1',
                'uid': os.geteuid(), 'run_digest': digest, 'run_id': 'v3b2-' + digest,
                'receipt_path': str(receipt), 'registry_path': str(registry), 'runtime_path': str(runtime),
                'runtime_identity': dict(zip(('device', 'inode', 'mode', 'uid'), root_id))}),
            'profile-created.json': canonical(original), 'runtime-leftovers.json': canonical(leftovers),
            'report.json': canonical(report),
        }
        for index in range(42): records['file-%04d.json' % index] = b'{}\n'
        for name, payload in records.items():
            (receipt / name).write_bytes(payload); (receipt / name).chmod(0o600)
        manifest = b''.join(hashlib.sha256(payload).hexdigest().encode() + b'  ' + name.encode() + b'\n'
                            for name, payload in sorted(records.items()))
        (receipt / 'SHA256SUMS').write_bytes(manifest); (receipt / 'SHA256SUMS').chmod(0o600)
        return home, registry, runtime, receipt, paths, original, binding, manifest


class RetainedAndFootprintTests(unittest.TestCase, RetainedFixture):
    def setUp(self):
        self.tool = load_tool()
        self.temporary = tempfile.TemporaryDirectory(prefix='kil-retained-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        (self.home, self.registry, self.runtime, self.receipt, self.paths,
         self.original, self.binding, self.manifest) = self.retained_fixture()
        self.root_id = (self.runtime.stat().st_dev, self.runtime.stat().st_ino,
                        self.runtime.stat().st_mode, os.geteuid())

    def repin_manifest(self):
        records = {path.name: path.read_bytes() for path in self.receipt.iterdir()
                   if path.name != 'SHA256SUMS'}
        self.manifest = b''.join(hashlib.sha256(payload).hexdigest().encode() + b'  ' + name.encode() + b'\n'
                                 for name, payload in sorted(records.items()))
        (self.receipt / 'SHA256SUMS').write_bytes(self.manifest)
        (self.receipt / 'SHA256SUMS').chmod(0o600)

    def retained(self, *, observed_home=None):
        self.assertTrue(hasattr(self.tool, '_retained'), 'Task 2 retained API is required')
        from kil import hf_exploratory_profile as profile
        from kil import hf_exploratory_runtime as runtime_module
        proof = self.tool._Files(); self.addCleanup(proof.close)
        selectors = (patch.object(self.tool, 'HOME', self.home), patch.object(self.tool, 'RUNTIME', self.runtime),
                     patch.object(self.tool, 'RECEIPT', self.receipt), patch.object(self.tool, 'UID', os.geteuid()),
                     patch.object(self.tool, 'DIGEST', self.receipt.name.removeprefix('hf-exploratory-')),
                     patch.object(self.tool, 'ROOT_ID', self.root_id),
                     patch.object(self.tool, 'MANIFEST_PIN', (hashlib.sha256(self.manifest).hexdigest(), len(self.manifest))),
                     patch.object(self.tool, 'passwd_home', return_value=self.home if observed_home is None else observed_home),
                     patch.object(runtime_module, '_registry_parent', return_value=self.registry),
                     patch.object(profile.runtime_module, '_registry_parent', return_value=self.registry))
        for selector in selectors: selector.start(); self.addCleanup(selector.stop)
        return self.tool._retained(proof)

    def test_retained_authenticates_receipt_runtime_binding_and_original_profile(self):
        result = self.retained()
        runtime, files, paths, report, original = result
        self.addCleanup(runtime.close)
        self.assertEqual(files['report.json'], canonical(report))
        self.assertEqual(paths.document(), self.paths.document())
        self.assertEqual(original, self.original)

    def test_retained_refuses_semantically_bad_but_repinned_binding(self):
        (self.receipt / 'runtime-binding.json').write_bytes(canonical({}))
        (self.receipt / 'runtime-binding.json').chmod(0o600)
        self.repin_manifest()
        with self.assertRaises(ValueError): self.retained()

    def test_retained_refuses_repinned_marker_drift(self):
        (self.registry / 'registry.json').write_bytes(canonical({}))
        (self.registry / 'registry.json').chmod(0o600)
        with self.assertRaises(ValueError): self.retained()

    def test_retained_refuses_changed_passwd_home(self):
        with self.assertRaisesRegex(ValueError, 'recovery_identity_or_home_changed'):
            self.retained(observed_home=self.home.with_name('wrong-home'))

    def test_retained_refuses_runtime_root_identity_drift(self):
        self.runtime.chmod(0o755)
        with self.assertRaises(ValueError): self.retained()

    def test_retained_refuses_each_repinned_binding_field_drift(self):
        path = self.receipt / 'runtime-binding.json'
        original = path.read_bytes()
        for field, replacement in (('uid', os.geteuid() + 1), ('run_digest', 'b' * 64),
                                   ('receipt_path', '/tmp/other'), ('registry_path', '/tmp/other'),
                                   ('runtime_path', '/tmp/other'), ('runtime_identity', {'device': 0, 'inode': 0,
                                                                                'mode': 0, 'uid': 0})):
            with self.subTest(field=field):
                value = json.loads(original); value[field] = replacement
                path.write_bytes(canonical(value)); path.chmod(0o600); self.repin_manifest()
                with self.assertRaises(ValueError): self.retained()
                path.write_bytes(original); path.chmod(0o600); self.repin_manifest()

    def test_retained_refuses_repinned_float_binding_numbers(self):
        path = self.receipt / 'runtime-binding.json'
        value = json.loads(path.read_bytes())
        value['uid'] = float(value['uid'])
        for key in ('device', 'inode', 'mode', 'uid'):
            value['runtime_identity'][key] = float(value['runtime_identity'][key])
        path.write_bytes(canonical(value)); path.chmod(0o600); self.repin_manifest()
        with self.assertRaises(ValueError): self.retained()

    def test_retained_refuses_marker_mode_and_hardlink(self):
        marker = self.registry / 'registry.json'
        marker.chmod(0o644)
        with self.assertRaises(ValueError): self.retained()
        marker.chmod(0o600)
        link = self.registry / 'marker-link'; os.link(marker, link)
        self.addCleanup(link.unlink, missing_ok=True)
        with self.assertRaises(ValueError): self.retained()

    def test_retained_refuses_repinned_leftover_shape_and_identity_drift(self):
        leftovers_path = self.receipt / 'runtime-leftovers.json'
        report_path = self.receipt / 'report.json'
        original_leftovers, original_report = leftovers_path.read_bytes(), report_path.read_bytes()
        for kind in ('missing', 'duplicate', 'unknown', 'identity'):
            with self.subTest(kind=kind):
                leftovers, report = json.loads(original_leftovers), json.loads(original_report)
                if kind == 'missing': leftovers['directories'].pop()
                elif kind == 'duplicate': leftovers['directories'][1] = dict(leftovers['directories'][0])
                elif kind == 'unknown':
                    leftovers['directories'].append({'runtime_path': '/tmp/unknown', 'observation': {}})
                else: leftovers['directories'][0]['observation']['inode'] = 0
                report['runtime_leftovers'] = leftovers
                leftovers_path.write_bytes(canonical(leftovers)); report_path.write_bytes(canonical(report))
                leftovers_path.chmod(0o600); report_path.chmod(0o600); self.repin_manifest()
                with self.assertRaises(ValueError): self.retained()
                leftovers_path.write_bytes(original_leftovers); report_path.write_bytes(original_report)
                leftovers_path.chmod(0o600); report_path.chmod(0o600); self.repin_manifest()

    def test_retained_allows_saved_stopped_lock_release_for_later_footprint_validation(self):
        (self.paths.disk / 'in_use_by').unlink()
        runtime, _, _, _, _ = self.retained()
        self.addCleanup(runtime.close)

    def test_footprint_accepts_exact_running_and_stopped_lock_release(self):
        self.assertTrue(hasattr(self.tool, '_footprint'), 'Task 2 footprint API is required')
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        self.tool._footprint(paths, report, original, 'Running')
        (paths.disk / 'in_use_by').unlink()
        self.tool._footprint(paths, report, original, 'Stopped')

    def test_footprint_accepts_all_finite_stopped_removals(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        for parent, names in ((paths.profile, ('docker.sock', 'containerd.sock')),
                              (paths.instance, ('ha.pid', 'ha.sock', 'ssh.sock', 'vz.pid'))):
            for name in names: (parent / name).unlink()
        (paths.disk / 'in_use_by').unlink()
        (paths.colima / 'ssh_config').unlink()
        self.tool._footprint(paths, report, original, 'Stopped')

    def test_footprint_refuses_ordinary_stopped_profile_removal(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        (paths.profile / 'ordinary-control').unlink()
        (paths.disk / 'in_use_by').unlink()
        with self.assertRaisesRegex(ValueError, 'recovery_stopped_footprint_changed'):
            self.tool._footprint(paths, report, original, 'Stopped')

    def test_footprint_refuses_unknown_stopped_namespace_addition(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        (paths.disk / 'in_use_by').unlink()
        (paths.runtime / 'foreign-stopped').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'recovery_runtime_namespace_roster_changed'):
            self.tool._footprint(paths, report, original, 'Stopped')

    def test_footprint_refuses_disk_reanchored_after_last_owned_read(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        data = paths.disk / 'datadisk'; root = paths.instance / 'disk'
        reads, actual = 0, self.tool._read
        def delegated(path, **kwargs):
            nonlocal reads
            result = actual(path, **kwargs)
            if path == root:
                reads += 1
                if reads == 2:
                    size, mode = data.stat().st_size, stat.S_IMODE(data.stat().st_mode)
                    data.rename(self.registry.parent / 'reanchored-datadisk')
                    with data.open('wb') as stream: stream.truncate(size)
                    data.chmod(mode)
                    with data.open('rb') as stream: self.assertEqual(stream.read(512), b'\0' * 512)
            return result
        with patch.object(self.tool, '_read', side_effect=delegated):
            with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')
        self.assertEqual(reads, 3)

    def test_footprint_refuses_disk_reanchored_during_final_owned_read(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        data, root, reads, actual = paths.disk / 'datadisk', paths.instance / 'disk', 0, self.tool._read
        def delegated(path, **kwargs):
            nonlocal reads
            result = actual(path, **kwargs)
            if path == root:
                reads += 1
                if reads == 3:
                    size, mode = data.stat().st_size, stat.S_IMODE(data.stat().st_mode)
                    data.rename(self.registry.parent / 'late-reanchored-datadisk')
                    with data.open('wb') as stream: stream.truncate(size)
                    data.chmod(mode)
            return result
        with patch.object(self.tool, '_read', side_effect=delegated):
            with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')
        self.assertEqual(reads, 3)

    def test_footprint_refuses_namespace_added_during_final_owned_read(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        root, reads, actual = paths.instance / 'disk', 0, self.tool._read
        def delegated(path, **kwargs):
            nonlocal reads
            result = actual(path, **kwargs)
            if path == root:
                reads += 1
                if reads == 3: (paths.runtime / 'late-foreign').write_bytes(b'x')
            return result
        with patch.object(self.tool, '_read', side_effect=delegated):
            with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')
        self.assertEqual(reads, 3)

    def test_footprint_refuses_disk_reanchored_after_last_tmp_content_read(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        data, reads, actual = paths.disk / 'datadisk', 0, self.tool._read
        def delegated(path, **kwargs):
            nonlocal reads
            result = actual(path, **kwargs)
            if path == paths.tmp:
                reads += 1
                if reads == 3:
                    size, mode = data.stat().st_size, stat.S_IMODE(data.stat().st_mode)
                    data.rename(self.registry.parent / 'tmp-reanchored-datadisk')
                    with data.open('wb') as stream: stream.truncate(size)
                    data.chmod(mode)
            return result
        with patch.object(self.tool, '_read', side_effect=delegated):
            with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')
        self.assertEqual(reads, 3)

    def test_footprint_refuses_namespace_added_after_last_tmp_content_read(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        reads, actual = 0, self.tool._read
        def delegated(path, **kwargs):
            nonlocal reads
            result = actual(path, **kwargs)
            if path == paths.tmp:
                reads += 1
                if reads == 3: (paths.runtime / 'tmp-late-foreign').write_bytes(b'x')
            return result
        with patch.object(self.tool, '_read', side_effect=delegated):
            with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')
        self.assertEqual(reads, 3)

    def test_footprint_refuses_profile_config_and_namespace_drift(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        (paths.profile / 'colima.yaml').write_bytes(b'bad\n')
        with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_each_saved_yaml_substitution(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        yaml_paths = (paths.profile / 'colima.yaml', paths.instance / 'colima.yaml', paths.instance / 'lima.yaml')
        for path in yaml_paths:
            with self.subTest(path=path.name):
                payload = path.read_bytes(); path.write_bytes(b'bad\n')
                with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')
                path.write_bytes(payload); path.chmod(0o644)

    def test_footprint_refuses_valid_raw_data_disk_capacity_change(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        disk = paths.disk / 'datadisk'
        with disk.open('r+b') as stream: stream.truncate(disk.stat().st_size - 4096)
        with disk.open('rb') as stream: self.assertEqual(stream.read(512), b'\0' * 512)
        with self.assertRaisesRegex(ValueError, 'data disk differs from pinned capacity'):
            self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_raw_disk_format_substitution(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        disk = paths.disk / 'datadisk'
        with disk.open('r+b') as stream: stream.write(b'QFI\xfb')
        with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_sparse_data_disk_inode_substitution(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        disk = paths.disk / 'datadisk'; mode = stat.S_IMODE(disk.stat().st_mode); size = disk.stat().st_size
        roster = _read(paths.disk, directory_only=True)['entries']
        disk.rename(self.registry.parent / 'saved-datadisk')
        with disk.open('wb') as stream: stream.truncate(size)
        disk.chmod(mode)
        self.assertEqual(disk.stat().st_size, size)
        with disk.open('rb') as stream: self.assertEqual(stream.read(512), b'\0' * 512)
        self.assertEqual(_read(paths.disk, directory_only=True)['entries'], roster)
        with self.assertRaisesRegex(ValueError, 'recovery_saved_profile_binding_changed'):
            self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_sparse_root_disk_inode_substitution(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        disk = paths.instance / 'disk'; mode = stat.S_IMODE(disk.stat().st_mode); size = disk.stat().st_size
        roster = _read(paths.instance, directory_only=True)['entries']
        disk.rename(self.registry.parent / 'saved-root-disk')
        with disk.open('wb') as stream: stream.truncate(size)
        disk.chmod(mode)
        self.assertEqual(disk.stat().st_size, size)
        with disk.open('rb') as stream: self.assertEqual(stream.read(512), b'\0' * 512)
        self.assertEqual(_read(paths.instance, directory_only=True)['entries'], roster)
        with self.assertRaisesRegex(ValueError, 'recovery_saved_profile_binding_changed'):
            self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_profile_instance_and_lima_roster_entries(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        (paths.profile / 'foreign').write_bytes(b'x')
        with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_unknown_instance_roster_entry(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        (paths.instance / 'foreign').write_bytes(b'x')
        with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_unknown_lima_roster_entry(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        (paths.lima / 'foreign').write_bytes(b'x')
        with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_protected_startup_foreign_lock_store_and_namespace_entries(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        (paths.instance / 'protected').write_bytes(b'x')
        with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_foreign_lock_target(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        lock = paths.disk / 'in_use_by'; lock.unlink(); lock.symlink_to('/tmp/foreign')
        with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_startup_store_and_runtime_roster_drift(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        paths.startup.write_bytes(b'x')
        with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_changed_store_bytes(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        paths.store.write_bytes(b'{"changed":true}\n'); paths.store.chmod(0o600)
        with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')

    def test_footprint_refuses_unknown_runtime_roster_entry(self):
        runtime, _, paths, report, original = self.retained(); self.addCleanup(runtime.close)
        (paths.runtime / 'foreign').write_bytes(b'x')
        with self.assertRaises(ValueError): self.tool._footprint(paths, report, original, 'Running')


class Task3FinalProofTests(unittest.TestCase):
    def test_default_accepted_manifest_uses_canonical_accepted_run(self):
        from kil.hf_exploratory_inputs import ACCEPTED_RUN
        tool = load_tool()
        self.assertEqual(tool.ACCEPTED_MANIFEST,
                         REPOSITORY / 'artifacts/generated/v3b1-local-envoy' / ACCEPTED_RUN / 'manifest.json')

    def test_default_fixed_authority_constants_match_approved_target_without_reading_it(self):
        tool = load_tool()
        digest = '254877dc1b1462c4e29c068e51ad7286fe430b075bc5044c8b3076d1887ad25d'
        self.assertEqual((tool.DIGEST, tool.UID, tool.HOME), (digest, 501, Path('/Users/mistorm')))
        self.assertEqual(tool.RUNTIME, tool.HOME / '.kil-hf' / ('r' + digest[:16]))
        self.assertEqual(tool.RECEIPT, REPOSITORY / '.tools/hf-exploratory-private' / ('hf-exploratory-' + digest))
        self.assertEqual(tool.ROOT_ID, (16777232, 615011851, 16832, 501))
        self.assertEqual(tool.SOURCE, '7d5c58372040ecf5b7c1fdd9c9d7ea3ddcd06205')
        self.assertEqual(tool.MANIFEST_PIN,
                         ('d128fd99fcc32391db27804da8be86c0e62b238343b71c7f44009785cba38ad0', 3979))
        self.assertEqual(tool.SSH_PIN,
                         ('0788dfecc6e2e6d6301a2eca6d9bebe153de450cac6d4657b053f2676a9564e9', 767))
        self.assertEqual(tool.COLIMA_PIN,
                         ('980ad8bf61a4ca370243f4cb41401a61276dcd2c2502bee7b9b86f9250169f34', 15656320))

    def test_final_files_rechecks_receipt_after_later_runtime_authentication_io(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory(prefix='kil-final-', dir='/private/tmp') as temporary:
            root = Path(temporary).resolve()
            receipt_path, runtime_path = root / 'receipt', root / 'runtime'
            receipt_path.mkdir(mode=0o700); runtime_path.mkdir(mode=0o700)
            receipt_file, runtime_file = receipt_path / 'saved', runtime_path / 'saved'
            for path in (receipt_file, runtime_file):
                path.write_bytes(b'original\n'); path.chmod(0o600)
            receipt, runtime = tool._Files(), tool._Files()
            try:
                receipt.read(receipt_file, 64, 0o600, os.geteuid())
                runtime.read(runtime_file, 64, 0o600, os.geteuid())
                original = runtime._retained_bytes
                def late_runtime_read(record):
                    payload = original(record)
                    receipt_file.write_bytes(b'late replacement\n')
                    receipt_file.chmod(0o600)
                    return payload
                runtime._retained_bytes = late_runtime_read
                with self.assertRaises(ValueError):
                    tool._final_files(receipt, runtime)
            finally:
                receipt.close(); runtime.close()


class Task3ObservationTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.temporary = tempfile.TemporaryDirectory(prefix='kil-task3-observe-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / 'home'; self.home.mkdir(mode=0o700)
        self.runtime = (self.root / '.tools' / 'hf-exploratory-private' /
                        ('hf-exploratory-runtime-' + 'a' * 64))
        self.runtime.parent.mkdir(parents=True, mode=0o700); self.runtime.mkdir(mode=0o700)
        self.paths = self.tool.ProfilePaths(self.home, self.runtime)
        self.paths.lima.mkdir(parents=True, mode=0o700)
        (self.paths.lima / 'colima-kil-v3-lab').mkdir(mode=0o700)

    def test_inventory_refuses_successful_empty_and_accepts_complete_singleton(self):
        row = {'name': 'kil-v3-lab', 'status': 'Running', 'arch': 'aarch64',
               'cpus': 4, 'memory': 8 * 1024**3, 'disk': 60 * 1024**3, 'runtime': 'docker'}
        with self.assertRaises(ValueError): self.tool._inventory(self.paths, lambda: b'')
        self.assertEqual(self.tool._inventory(self.paths, lambda: canonical([row])), [row])

    def test_fingerprint_records_absence_only_after_nofollow_parent_walk(self):
        missing = self.paths.lima / 'missing.yaml'
        observed = self.tool._fingerprint(missing)
        self.assertEqual(observed, {'path': str(missing), 'present': False, 'identity': None,
                                    'byte_count': None, 'sha256': None})
        link_parent = self.root / 'linked'; link_parent.symlink_to(self.paths.lima, target_is_directory=True)
        with self.assertRaises(ValueError): self.tool._fingerprint(link_parent / 'missing.yaml')

    def test_control_paths_are_the_exact_twelve_fixed_locations(self):
        pairs = self.tool._control_paths(self.paths)
        self.assertEqual([label for label, _ in pairs], [
            'profile.yaml', 'instance.yaml', 'lima.yaml', 'colima-ssh.config',
            'instance-ssh.config', 'ha.pid', 'vz.pid', 'kind.yaml', 'docker-meta.json',
            'ha.stdout.log', 'ha.stderr.log', 'serialv.log'])
        self.assertEqual(dict(pairs)['kind.yaml'], self.runtime / 'kind-config.yaml')

    def test_controls_return_honest_absence_and_copy_present_private_bytes(self):
        control = self.paths.profile / 'colima.yaml'
        self.paths.profile.mkdir(mode=0o700); control.write_bytes(b'profile: fixture\n'); control.chmod(0o600)
        proof = self.tool._Files(); self.addCleanup(proof.close)
        observed, payloads = self.tool._controls(self.paths, proof)
        self.assertEqual(payloads['profile.yaml'], b'profile: fixture\n')
        self.assertFalse(observed['instance.yaml']['present'])

    def test_inventory_rejects_malformed_partial_unknown_and_replaced_roster(self):
        row = {'name': 'kil-v3-lab', 'status': 'Running', 'arch': 'aarch64',
               'cpus': 4, 'memory': 8 * 1024**3, 'disk': 60 * 1024**3, 'runtime': 'docker'}
        for payload in (b'{', b'[]\n', canonical([{**row, 'unknown': True}]),
                        canonical([{**row, 'name': 'other'}])):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.tool._inventory(self.paths, lambda: payload)
        (self.paths.lima / 'unrecognized').mkdir(mode=0o700)
        with self.assertRaises(ValueError): self.tool._inventory(self.paths, lambda: canonical([row]))
        (self.paths.lima / 'unrecognized').rmdir()
        def replace_child():
            (self.paths.lima / 'colima-kil-v3-lab').rename(self.root / 'old-instance')
            (self.paths.lima / 'colima-kil-v3-lab').mkdir(mode=0o700)
            return canonical([row])
        with self.assertRaises(ValueError): self.tool._inventory(self.paths, replace_child)

    def test_fingerprint_rejects_linked_oversized_or_changed_regular_files(self):
        path = self.root / 'foreign'; path.write_bytes(b'original\n'); path.chmod(0o600)
        os.link(path, self.root / 'hardlink')
        with self.assertRaises(ValueError): self.tool._fingerprint(path)
        (self.root / 'hardlink').unlink()
        with path.open('wb') as stream: stream.truncate(self.tool.MAXIMUM + 1)
        with self.assertRaises(ValueError): self.tool._fingerprint(path)
        path.write_bytes(b'original\n')
        real_read = self.tool.read_regular
        def late_change(target, maximum):
            payload = real_read(target, maximum)
            target.write_bytes(b'changed\n')
            return payload
        with patch.object(self.tool, 'read_regular', side_effect=late_change):
            with self.assertRaises(ValueError): self.tool._fingerprint(path)

    def test_controls_recheck_earlier_present_file_after_last_control_content_read(self):
        control = self.paths.profile / 'colima.yaml'
        self.paths.profile.mkdir(mode=0o700); control.write_bytes(b'profile\n'); control.chmod(0o600)
        last = self.paths.instance / 'serialv.log'
        last.parent.mkdir(mode=0o700, exist_ok=True)
        proof = self.tool._Files(); self.addCleanup(proof.close)
        real_read = self.tool.read_regular
        def late_change(path, maximum):
            payload = real_read(path, maximum)
            if path == last: control.write_bytes(b'changed earlier control\n')
            return payload
        last.write_bytes(b'log\n'); last.chmod(0o600)
        with patch.object(self.tool, 'read_regular', side_effect=late_change):
            with self.assertRaises(ValueError): self.tool._controls(self.paths, proof)

    def test_controls_refuse_replacement_between_fingerprint_and_retained_copy(self):
        control = self.paths.profile / 'colima.yaml'
        self.paths.profile.mkdir(mode=0o700); control.write_bytes(b'profile\n'); control.chmod(0o644)
        proof = self.tool._Files(); self.addCleanup(proof.close)
        actual = self.tool._fingerprint
        changed = False
        def fingerprint_then_replace(path):
            nonlocal changed
            result = actual(path)
            if path == control and not changed:
                changed = True
                path.rename(self.root / 'original-control')
                path.write_bytes(b'profile\n'); path.chmod(0o644)
            return result
        with patch.object(self.tool, '_fingerprint', side_effect=fingerprint_then_replace):
            with self.assertRaises(ValueError): self.tool._controls(self.paths, proof)
        self.assertTrue(changed)

    def test_controls_refuse_replacement_during_real_copy_parent_authentication(self):
        control = self.paths.profile / 'colima.yaml'
        self.paths.profile.mkdir(mode=0o700); control.write_bytes(b'profile\n'); control.chmod(0o644)
        proof = self.tool._Files(); self.addCleanup(proof.close)
        actual_directory = proof.directory
        changed = False
        def directory_then_replace(path, private=False):
            nonlocal changed
            descriptor = actual_directory(path, private)
            if path == control.parent and not changed:
                changed = True
                control.rename(self.root / 'original-copy-control')
                control.write_bytes(b'profile\n'); control.chmod(0o644)
            return descriptor
        with patch.object(proof, 'directory', side_effect=directory_then_replace):
            with self.assertRaises(ValueError): self.tool._controls(self.paths, proof)
        self.assertTrue(changed)


class Task3NativeGrammarTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.temporary = tempfile.TemporaryDirectory(prefix='kil-task3-native-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / 'home'; self.home.mkdir(mode=0o700)
        self.runtime = (self.root / '.tools' / 'hf-exploratory-private' /
                        ('hf-exploratory-runtime-' + 'a' * 64))
        self.runtime.parent.mkdir(parents=True, mode=0o700); self.runtime.mkdir(mode=0o700)
        self.paths = self.tool.ProfilePaths(self.home, self.runtime)
        for directory in (self.paths.colima, self.paths.lima, self.runtime / 'docker-config', self.paths.tmp):
            directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.receipt = self.tool._Files(); self.runtime_proof = self.tool._Files()
        self.addCleanup(self.receipt.close); self.addCleanup(self.runtime_proof.close)
        self.tools = self.root / 'tools'; self.tools.mkdir(mode=0o700)
        records = {}
        for name in ('docker', 'kind', 'kubectl'):
            payload = ('fixture ' + name + '\n').encode()
            executable = self.tools / name; executable.write_bytes(payload); executable.chmod(0o755)
            records[name] = {'executable_sha256': hashlib.sha256(payload).hexdigest(), 'byte_size': len(payload)}
        self.manifest = self.root / 'manifest.json'
        payload = canonical({'verified_tool_identities': records})
        self.manifest.write_bytes(payload); self.manifest.chmod(0o644)
        self.colima = self.home / 'colima'; self.colima.write_bytes(b'colima fixture\n'); self.colima.chmod(0o755)
        self.lima_dir = self.root / 'original-bin'; self.lima_dir.mkdir(mode=0o700)
        self.lima = self.lima_dir / 'limactl'; self.lima.write_bytes(b'lima fixture\n'); self.lima.chmod(0o755)
        self.store = self.tool.PrivateStore(self.runtime / 'store')
        self.addCleanup(self.store.close)

    def native(self, original_path=None):
        selectors = (patch.multiple(self.tool, HOME=self.home, UID=os.geteuid(), TOOLS=self.tools,
                                    COLIMA=self.colima, ACCEPTED_MANIFEST=self.manifest,
                                    ACCEPTED_MANIFEST_SHA256=hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
                                    COLIMA_PIN=(hashlib.sha256(self.colima.read_bytes()).hexdigest(), self.colima.stat().st_size),
                                    passwd_home=lambda: self.home),
                     patch.dict(os.environ, {'PATH': str(self.lima_dir) if original_path is None else original_path}, clear=True))
        for selector in selectors: selector.start(); self.addCleanup(selector.stop)
        return self.tool._Native(self.receipt, self.runtime_proof, self.paths, self.store)

    def test_native_exposes_minimal_namespace_environments_and_closed_read_grammar(self):
        native = self.native()
        private = native.environment_for('private')
        self.assertEqual(private['HOME'], str(self.home))
        self.assertEqual(private['PATH'], str(self.tools) + os.pathsep + str(self.lima_dir))
        self.assertEqual(private['COLIMA_HOME'], str(self.paths.colima))
        self.assertNotIn('COLIMA_HOME', native.environment_for('global'))
        endpoint = 'unix://' + str(self.paths.profile / 'docker.sock')
        self.assertTrue(native.allowed(('docker', '--host', endpoint, 'ps', '--all', '--quiet', '--no-trunc'), 'docker'))
        for argv in (('colima', 'stop'), ('docker', 'context', 'use', 'default'), ('docker', '--host', endpoint, 'ps')):
            with self.subTest(argv=argv): self.assertFalse(native.allowed(argv, 'private'))

    def test_native_rejects_empty_or_relative_original_path_before_process_acquisition(self):
        for path in ('', 'relative:/bin', '/bin:', ':/bin', '/bin::/usr/bin', '/bin/../usr/bin'):
            with self.subTest(path=path), patch.object(self.tool, 'capture_process') as capture:
                with self.assertRaisesRegex(ValueError, 'recovery_original_path_is_invalid'):
                    self.native(original_path=path)
                capture.assert_not_called()

    def test_acquire_journals_effective_pinned_dispatch_and_raw_terminal_copies(self):
        native = self.native()
        expected = CommandResult(0, 'fixture\n', '', b'fixture\n', b'')
        with patch.object(self.tool, 'capture_process', return_value=expected) as capture:
            result = native.acquire(('docker', 'context', 'show'), 'global')
        self.assertIs(result, expected)
        argv, environment, stdin, timeout, maximum, cwd = capture.call_args.args
        self.assertEqual(argv, (str(self.tools / 'docker'), 'context', 'show'))
        self.assertEqual(environment['DOCKER_CONFIG'], str(self.home / '.docker'))
        self.assertEqual((stdin, timeout, maximum, cwd), (None, 10, 8 * 1024**2, self.tool.REPOSITORY))
        journal = self.store.journal.read_bytes()
        intent = next(json.loads(line)['details'] for line in journal.splitlines()
                      if json.loads(line)['event'] == 'command_intent')
        self.assertEqual(intent.get('cwd'), str(self.tool.REPOSITORY))
        self.assertEqual(intent['argv'], list(argv))
        self.assertEqual(intent['environment'], environment)
        self.assertIn(b'command_terminal', journal)
        self.assertTrue(any(path.name.endswith('.stdout') for path in self.store.path.iterdir()))

    def test_guard_rejects_accepted_tool_replaced_during_later_lima_authentication(self):
        native = self.native()
        original = self.tool._locator_snapshot
        def mutate_after_lima(path):
            value = original(path)
            docker = self.tools / 'docker'
            docker.write_bytes(b'replaced docker\n'); docker.chmod(0o755)
            return value
        with patch.object(self.tool, '_locator_snapshot', side_effect=mutate_after_lima):
            with self.assertRaises(ValueError): native.guard()

    def test_constructor_retains_resolved_lima_descriptor_and_bytes(self):
        native = self.native()
        retained = [record for record in native.runtime.files if record[0] == self.lima]
        self.assertEqual(len(retained), 1)
        self.assertEqual(os.fstat(retained[0][1]).st_ino, self.lima.stat().st_ino)
        self.assertEqual(retained[0][3], hashlib.sha256(self.lima.read_bytes()).hexdigest())

    def test_repeated_guards_reuse_one_retained_manifest_descriptor(self):
        native = self.native()
        def records():
            return [row for row in native.receipt.files if row[0] == self.manifest]
        self.assertEqual(len(records()), 1)
        descriptor = records()[0][1]
        for _ in range(3): native.guard()
        self.assertEqual(len(records()), 1)
        self.assertEqual(records()[0][1], descriptor)

    def test_reused_manifest_refuses_mutation_during_later_real_lima_read(self):
        native = self.native()
        real_read, changed = self.tool.read_regular, False
        def read_then_mutate(path, maximum):
            nonlocal changed
            payload = real_read(path, maximum)
            if path == self.lima and not changed:
                changed = True
                self.manifest.write_bytes(b'changed manifest\n')
            return payload
        with patch.object(self.tool, 'read_regular', side_effect=read_then_mutate):
            with self.assertRaises(ValueError): native.guard()
        self.assertTrue(changed)

    def test_guard_rejects_new_higher_priority_locator_during_last_lima_read(self):
        earlier = self.root / 'earlier-bin'; earlier.mkdir(mode=0o700)
        native = self.native(original_path=str(earlier) + os.pathsep + str(self.lima_dir))
        real_read = self.tool.read_regular
        changed = False
        def read_then_add(path, maximum):
            nonlocal changed
            payload = real_read(path, maximum)
            if path == self.lima and not changed:
                changed = True
                replacement = earlier / 'limactl'
                replacement.write_bytes(b'higher priority executable\n'); replacement.chmod(0o755)
            return payload
        with patch.object(self.tool, 'read_regular', side_effect=read_then_add):
            with self.assertRaises(ValueError): native.guard()
        self.assertTrue(changed)

    def test_acquisition_terminal_distinguishes_returned_and_uncertain_process_results(self):
        native = self.native()
        for returncode in (0, 1, -9):
            with patch.object(self.tool, 'capture_process', return_value=CommandResult(
                    returncode, 'out', 'err', b'out', b'err')):
                native.acquire(('docker', 'context', 'show'), 'global')
        terminals = [json.loads(line)['details'] for line in self.store.journal.read_bytes().splitlines()
                     if json.loads(line)['event'] == 'command_terminal']
        self.assertEqual([row.get('certainty') for row in terminals], ['returned', 'returned', 'uncertain'])

    def test_capture_exception_has_uncertain_terminal_and_preserves_original_error(self):
        native = self.native()
        failure = OSError('fixture capture failed')
        with patch.object(self.tool, 'capture_process', side_effect=failure):
            with self.assertRaises(OSError) as raised:
                native.acquire(('docker', 'context', 'show'), 'global')
        self.assertIs(raised.exception, failure)
        terminal = json.loads(self.store.journal.read_bytes().splitlines()[-1])
        self.assertEqual(terminal['event'], 'command_terminal')
        self.assertEqual(terminal['details']['certainty'], 'uncertain')
        self.assertIsNone(terminal['details']['returncode'])
        self.assertEqual(terminal['details']['error_type'], 'OSError')

    def test_native_environment_excludes_inherited_overrides_and_separates_namespaces(self):
        native = self.native()
        with patch.dict(os.environ, {'HOME': '/wrong', 'PATH': '/different', 'DOCKER_HOST': 'tcp://wrong',
                                     'COLIMA_HOME': '/wrong', 'LIMA_HOME': '/wrong', 'TMPDIR': '/wrong',
                                     'KUBECONFIG': '/wrong', 'HTTPS_PROXY': 'secret', 'TOKEN': 'secret',
                                     'LANG': 'C', 'LC_ALL': 'C'}):
            common = {'HOME': str(self.home), 'PATH': str(self.tools) + os.pathsep + str(self.lima_dir),
                      'LANG': 'C', 'LC_ALL': 'C'}
            self.assertEqual(native.environment_for('global'), {**common, 'DOCKER_CONFIG': str(self.home / '.docker')})
            docker = {**common, 'DOCKER_CONFIG': str(self.runtime / 'docker-config'), 'TMPDIR': str(self.paths.tmp)}
            self.assertEqual(native.environment_for('docker'), docker)
            self.assertEqual(native.environment_for('private'),
                             {**docker, 'COLIMA_HOME': str(self.paths.colima), 'LIMA_HOME': str(self.paths.lima)})

    def test_closed_native_argv_and_timeout_refusals_produce_zero_acquisitions(self):
        native = self.native()
        before = self.store.journal.read_bytes()
        with patch.object(self.tool, 'capture_process') as capture:
            for argv, namespace in (
                    (('colima', 'stop', '--force', 'kil-v3-lab'), 'private'),
                    (('colima', 'delete', 'kil-v3-lab'), 'private'),
                    (('limactl', 'stop', 'colima-kil-v3-lab'), 'global'),
                    ((str(self.lima), '--version'), 'global'),
                    (('docker', 'ps'), 'global'), (('docker', 'context', 'use', 'default'), 'global'),
                    (('docker', '--host', 'unix:///wrong', 'ps', '--all', '--quiet', '--no-trunc'), 'docker'),
                    (('colima', '--home', '/wrong', 'list', '--json'), 'private'),
                    (('env', 'COLIMA_HOME=/wrong', 'colima', 'list'), 'private'),
                    (('colima', 'list', '--json'), 'docker')):
                with self.subTest(argv=argv), self.assertRaises(ValueError): native.acquire(argv, namespace)
            for timeout in (True, 10.0, 9, 11, '10'):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    native.acquire(('colima', 'version'), 'private', timeout)
            capture.assert_not_called()
        self.assertEqual(self.store.journal.read_bytes(), before)
        self.assertEqual(native.sequence, 0)

    def test_guard_after_durable_intent_refuses_late_tool_change_before_capture(self):
        native = self.native()
        real_record = self.store.record
        def record_then_change(event, details):
            real_record(event, details)
            if event == 'command_intent': (self.tools / 'docker').write_bytes(b'changed after fsync\n')
        with patch.object(self.store, 'record', side_effect=record_then_change), patch.object(self.tool, 'capture_process') as capture:
            with self.assertRaises(ValueError): native.acquire(('docker', 'context', 'show'), 'global')
            capture.assert_not_called()
        self.assertEqual(json.loads(self.store.journal.read_bytes().splitlines()[-1])['event'], 'command_intent')

    def test_late_accepted_tools_directory_addition_refuses_after_intent_before_capture(self):
        native = self.native()
        real_read, reads = self.tool.read_regular, 0
        def read_then_add(path, maximum):
            nonlocal reads
            payload = real_read(path, maximum)
            if path == self.lima:
                reads += 1
                if reads == 2:
                    extra = self.tools / 'limactl'
                    extra.write_bytes(b'unaccepted PATH prefix executable\n'); extra.chmod(0o755)
            return payload
        expected = CommandResult(0, '[]\n', '', b'[]\n', b'')
        with patch.object(self.tool, 'read_regular', side_effect=read_then_add), \
             patch.object(self.tool, 'capture_process', return_value=expected) as capture:
            with self.assertRaises(ValueError): native.acquire(('colima', 'list', '--json'), 'private')
            capture.assert_not_called()
        self.assertEqual(reads, 2)
        self.assertTrue((self.tools / 'limactl').exists())
        self.assertEqual(json.loads(self.store.journal.read_bytes().splitlines()[-1])['event'], 'command_intent')

    def test_store_lock_named_replacement_refuses_before_capture(self):
        native = self.native()
        lock = self.store.path / 'lock'; lock.rename(self.root / 'old-lock')
        lock.touch(mode=0o600)
        with patch.object(self.tool, 'capture_process') as capture:
            with self.assertRaises(ValueError): native.acquire(('docker', 'context', 'show'), 'global')
            capture.assert_not_called()

    def test_store_lock_descriptor_substitution_refuses(self):
        native = self.native()
        replacement = self.root / 'replacement-lock'; replacement.touch(mode=0o600)
        fd = os.open(replacement, os.O_RDWR | os.O_NOFOLLOW)
        try: os.dup2(fd, self.store._lock)
        finally: os.close(fd)
        with self.assertRaises(ValueError): native.guard()

    def test_store_directory_named_replacement_refuses(self):
        native = self.native()
        self.store.path.rename(self.root / 'moved-store')
        self.store.path.mkdir(mode=0o700)
        with self.assertRaises(ValueError): native.guard()

    def test_store_directory_descriptor_substitution_refuses(self):
        native = self.native()
        replacement = self.root / 'replacement-store'; replacement.mkdir(mode=0o700)
        fd = os.open(replacement, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.dup2(fd, self.store._directory)
        finally: os.close(fd)
        with self.assertRaises(ValueError): native.guard()

    def test_store_mode_and_zero_lock_requirements_are_checked(self):
        native = self.native()
        self.store.path.chmod(0o755)
        with self.assertRaises(ValueError): native.guard()
        self.store.path.chmod(0o700)
        (self.store.path / 'lock').write_bytes(b'not zero')
        with self.assertRaises(ValueError): native.guard()

    def test_constructor_rejects_resolved_lima_changed_during_later_retained_receipt_read(self):
        real_read = self.tool._Files._retained_bytes
        changed = False
        def read_then_change(proof, record):
            nonlocal changed
            payload = real_read(proof, record)
            if (proof is self.receipt and not changed
                    and any(item[0] == self.lima for item in self.runtime_proof.files)):
                changed = True
                self.lima.write_bytes(b'changed retained lima\n')
            return payload
        with patch.object(self.tool._Files, '_retained_bytes', new=read_then_change), patch.object(self.tool, 'capture_process') as capture:
            with self.assertRaises(ValueError): self.native()
            capture.assert_not_called()
        self.assertTrue(changed)

    def test_constructor_rejects_accepted_docker_changed_during_real_lima_read(self):
        real_read = self.tool.read_regular
        changed = False
        def read_then_change(path, maximum):
            nonlocal changed
            payload = real_read(path, maximum)
            if path == self.lima and not changed:
                changed = True
                (self.tools / 'docker').write_bytes(b'changed accepted docker\n')
            return payload
        with patch.object(self.tool, 'read_regular', side_effect=read_then_change), patch.object(self.tool, 'capture_process') as capture:
            with self.assertRaises(ValueError): self.native()
            capture.assert_not_called()
        self.assertTrue(changed)

    def test_symlink_original_locator_is_recorded_separately_from_resolved_file(self):
        resolved = self.root / 'resolved-lima'
        self.lima.rename(resolved); self.lima.symlink_to(resolved)
        native = self.native()
        self.assertEqual(native.lima['locator'], str(self.lima))
        self.assertEqual(native.lima['resolved'], str(resolved))
        native.guard()
        self.lima.unlink(); self.lima.symlink_to(self.colima)
        with self.assertRaises(ValueError): native.guard()

    def test_observe_requires_zero_exit_and_empty_stderr(self):
        native = self.native()
        for result in (CommandResult(1, '', '', b'', b''), CommandResult(0, '', 'warn', b'', b'warn')):
            with patch.object(self.tool, 'capture_process', return_value=result):
                with self.assertRaisesRegex(ValueError, 'recovery_native_observation_failed'):
                    native.observe(('docker', 'context', 'show'), 'global')

    def test_output_persistence_failure_records_uncertainty_and_original_error(self):
        native = self.native()
        failure = OSError('fixture stderr persistence failed')
        real_write = self.store.write
        def write(name, payload):
            if name.endswith('.stderr'): raise failure
            return real_write(name, payload)
        result = CommandResult(0, 'out', 'err', b'out', b'err')
        with patch.object(self.tool, 'capture_process', return_value=result), patch.object(self.store, 'write', side_effect=write):
            with self.assertRaises(OSError) as raised: native.acquire(('docker', 'context', 'show'), 'global')
        self.assertIs(raised.exception, failure)
        terminal = json.loads(self.store.journal.read_bytes().splitlines()[-1])['details']
        self.assertEqual(terminal['certainty'], 'uncertain')
        self.assertEqual(terminal['stdout_sha256'], hashlib.sha256(b'out').hexdigest())
        self.assertIsNone(terminal['stderr_sha256'])

    def test_capture_exception_survives_terminal_record_failure(self):
        native = self.native()
        failure = OSError('fixture capture failed')
        real_record = self.store.record
        def record(event, details):
            if event == 'command_terminal': raise RuntimeError('fixture journal failed')
            return real_record(event, details)
        with patch.object(self.tool, 'capture_process', side_effect=failure), patch.object(self.store, 'record', side_effect=record):
            with self.assertRaises(OSError) as raised: native.acquire(('docker', 'context', 'show'), 'global')
        self.assertIs(raised.exception, failure)


class Task3ForeignTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.temporary = tempfile.TemporaryDirectory(prefix='kil-task3-foreign-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve() / 'home'; self.home.mkdir(mode=0o700)
        lima = self.home / '.colima/_lima'; (lima / 'colima-kil-v3-lab').mkdir(parents=True, mode=0o700)
        (lima / '_config').mkdir(mode=0o700); (lima / '_config/networks.yaml').write_bytes(b'networks: {}\n')
        (lima / '_config/networks.yaml').chmod(0o600)
        (self.home / '.docker').mkdir(mode=0o700); (self.home / '.docker/config.json').write_bytes(b'{}\n')
        (self.home / '.docker/config.json').chmod(0o600)
        (self.home / '.kube').mkdir(mode=0o700)
        self.row = {'name': 'kil-v3-lab', 'status': 'Stopped', 'arch': 'aarch64',
                    'cpus': 4, 'memory': 8 * 1024**3, 'disk': 60 * 1024**3, 'runtime': 'docker'}
        class Native:
            def __init__(inner, row): inner.row, inner.calls = row, []
            def observe(inner, argv, namespace):
                inner.calls.append((argv, namespace))
                if argv == ('colima', 'list', '--json'):
                    payload = canonical([inner.row])
                elif argv == ('docker', 'context', 'show'):
                    payload = b'default\n'
                else: raise AssertionError(argv)
                return CommandResult(0, payload.decode(), '', payload, b'')
        self.native = Native(self.row)

    def test_foreign_is_stable_and_keeps_default_kubeconfig_inherited_none(self):
        with patch.multiple(self.tool, HOME=self.home, UID=os.geteuid()), patch.dict(os.environ, {}, clear=True):
            observed = self.tool._foreign(self.native)
        self.assertEqual(observed['kubeconfig']['inherited'], None)
        self.assertEqual(observed['foreign_profiles'], [self.row])
        self.assertEqual(self.native.calls.count((('colima', 'list', '--json'), 'global')), 2)

    def test_foreign_rejects_inherited_kubeconfig_and_changed_inventory(self):
        with patch.multiple(self.tool, HOME=self.home, UID=os.geteuid()), patch.dict(os.environ, {'KUBECONFIG': '/tmp/no'}, clear=True):
            with self.assertRaises(ValueError): self.tool._foreign(self.native)
        class Changing(type(self.native)):
            def observe(inner, argv, namespace):
                result = super().observe(argv, namespace)
                if argv == ('colima', 'list', '--json') and len(inner.calls) == 1:
                    inner.row = {**inner.row, 'status': 'Running'}
                return result
        with patch.multiple(self.tool, HOME=self.home, UID=os.geteuid()), patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError): self.tool._foreign(Changing(self.row))


class Task3PreflightTests(unittest.TestCase):
    def test_preflight_refuses_wrong_pinned_colima_version_before_lifecycle(self):
        tool = load_tool()
        class Native:
            def observe(self, argv, namespace):
                payload = b'wrong\n'
                return CommandResult(0, 'wrong\n', '', payload, b'')
        paths = object()
        with self.assertRaises(ValueError):
            tool._preflight(Native(), paths, {}, {}, {}, authenticate=True)


class Task3IntegratedPreflightTests(unittest.TestCase, RetainedFixture):
    """Composed Task 3 proof with only process acquisition replaced."""
    include_native_logs = True
    def setUp(self):
        self.tool = load_tool()
        self.temporary = tempfile.TemporaryDirectory(prefix='kil-task3-integrated-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        (self.home, self.registry, self.runtime, self.receipt_path, self.paths,
         self.original, self.binding, self.manifest) = self.retained_fixture()
        (self.paths.colima / 'ssh_config').chmod(0o644)
        self.tools = self.home / 'tools'; self.tools.mkdir(mode=0o700)
        records = {}
        for name in ('docker', 'kind', 'kubectl'):
            payload = ('tool ' + name + '\n').encode(); path = self.tools / name
            path.write_bytes(payload); path.chmod(0o755)
            records[name] = {'executable_sha256': hashlib.sha256(payload).hexdigest(), 'byte_size': len(payload)}
        self.accepted_manifest = self.home / 'manifest.json'
        manifest = canonical({'verified_tool_identities': records})
        self.accepted_manifest.write_bytes(manifest); self.accepted_manifest.chmod(0o644)
        self.colima = self.home / 'colima'; self.colima.write_bytes(b'colima fixture\n'); self.colima.chmod(0o755)
        self.bin = self.home / 'bin'; self.bin.mkdir(mode=0o700)
        (self.bin / 'limactl').write_bytes(b'lima fixture\n'); (self.bin / 'limactl').chmod(0o755)
        global_lima = self.home / '.colima/_lima'
        (global_lima / 'colima-kil-v3-lab').mkdir(parents=True, mode=0o700)
        (global_lima / '_config').mkdir(mode=0o700)
        (global_lima / '_config/networks.yaml').write_bytes(b'networks: {}\n')
        (global_lima / '_config/networks.yaml').chmod(0o600)
        (self.home / '.docker').mkdir(mode=0o700); (self.home / '.docker/config.json').write_bytes(b'{}\n')
        (self.home / '.docker/config.json').chmod(0o600)
        (self.home / '.kube').mkdir(mode=0o700)
        self.store = self.tool.PrivateStore(self.home / 'recovery-store'); self.addCleanup(self.store.close)
        self.receipt = self.tool._Files()
        self.addCleanup(self.receipt.close)
        self.private_row = {'name': 'kil-v3-lab', 'status': 'Running', 'arch': 'aarch64', 'cpus': 4,
                            'memory': 8 * 1024**3, 'disk': 60 * 1024**3, 'runtime': 'docker'}
        self.foreign_row = {**self.private_row, 'status': 'Stopped'}
        self.root_id = self.tool._id(self.runtime.lstat())
        self.ssh_bytes = (self.paths.colima / 'ssh_config').read_bytes()
        self.ssh_pin = (hashlib.sha256(self.ssh_bytes).hexdigest(), len(self.ssh_bytes))
        self.accepted_pin = hashlib.sha256(manifest).hexdigest()
        self.colima_pin = (hashlib.sha256(self.colima.read_bytes()).hexdigest(), self.colima.stat().st_size)
        self.observed_home = self.home
        self.dispatches = []
        self.private_payload = None
        self.foreign_payload = None
        self.ps_payload = b''
        self.context_payload = b'default\n'
        self.saved_files = self.sealed_files(self.original_foreign(global_lima))
        self.saved_manifest = (self.receipt_path / 'SHA256SUMS').read_bytes()

    def original_foreign(self, lima):
        # Build the original sealed document before authentication, independently
        # of _foreign and its native observations. Never refresh this baseline.
        def fingerprint(path):
            if not path.exists():
                return {'path': str(path), 'present': False, 'identity': None,
                        'byte_count': None, 'sha256': None}
            row, payload = path.lstat(), path.read_bytes()
            return {'path': str(path), 'present': True,
                    'identity': {key: getattr(row, key) for key in
                                 ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')},
                    'byte_count': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
        def identity(path):
            row = path.lstat()
            return {'device': row.st_dev, 'inode': row.st_ino, 'mode': row.st_mode}
        names = sorted(path.name for path in lima.iterdir())
        return {'foreign_profiles': [dict(self.foreign_row)],
                'foreign_lima_roster': {'directory': {**identity(lima), 'entries': names},
                                       'children': [{'name': name, **identity(lima / name)} for name in names]},
                'global_docker_context': 'default',
                'default_networks': _read(lima / '_config/networks.yaml'),
                'global_docker_config': str(self.home / '.docker'),
                'global_docker_directory': {**identity(self.home / '.docker'), 'entries': ['config.json']},
                'global_docker_file': fingerprint(self.home / '.docker/config.json'),
                'kubeconfig': {'inherited': None, 'files': [fingerprint(self.home / '.kube/config')]}}

    def selectors(self):
        return (patch.multiple(self.tool, HOME=self.home, RUNTIME=self.runtime, UID=os.geteuid(), TOOLS=self.tools,
                               RECEIPT=self.receipt_path, ROOT_ID=self.root_id,
                               DIGEST=self.receipt_path.name.removeprefix('hf-exploratory-'),
                               MANIFEST_PIN=(hashlib.sha256(self.saved_manifest).hexdigest(), len(self.saved_manifest)),
                               COLIMA=self.colima, ACCEPTED_MANIFEST=self.accepted_manifest,
                               ACCEPTED_MANIFEST_SHA256=self.accepted_pin,
                               COLIMA_PIN=self.colima_pin, SSH_PIN=self.ssh_pin,
                               passwd_home=lambda: self.observed_home),
                patch.dict(os.environ, {'PATH': str(self.bin)}, clear=True))

    def native(self):
        for selector in self.selectors():
            selector.start(); self.addCleanup(selector.stop)
        selector = patch.object(self.tool, 'capture_process', side_effect=self.capture)
        selector.start(); self.addCleanup(selector.stop)
        (self.runtime_proof, self.files, self.authenticated_paths,
         self.report, self.authenticated_original) = self.tool._retained(self.receipt)
        self.addCleanup(self.runtime_proof.close)
        self.assertEqual(self.files, self.saved_files)
        self.assertEqual(self.authenticated_original, self.original)
        return self.tool._Native(self.receipt, self.runtime_proof, self.authenticated_paths, self.store)

    def preflight(self, native, authenticate=True):
        return self.tool._preflight(native, self.authenticated_paths, self.report,
                                    self.authenticated_original, self.files, authenticate)

    def assert_receipt_unchanged(self):
        self.assertEqual({path.name: path.read_bytes() for path in self.receipt_path.iterdir()},
                         {**self.saved_files, 'SHA256SUMS': self.saved_manifest})

    def last_auth_mutation(self, native, mutate, *, refuse=True, authenticate=True):
        real_read = self.tool.read_regular
        dispatch_count = len(self.dispatches) + (7 if self.private_row['status'] == 'Running' else 6)
        changed = False
        def read_then_change(path, maximum):
            nonlocal changed
            payload = real_read(path, maximum)
            if path == self.bin / 'limactl' and len(self.dispatches) == dispatch_count and not changed:
                changed = True
                mutate()
            return payload
        with patch.object(self.tool, 'read_regular', side_effect=read_then_change):
            if refuse:
                with self.assertRaises(ValueError): self.preflight(native, authenticate)
            else:
                self.preflight(native, authenticate)
        self.assertTrue(changed)

    def result(self, argv):
        tail = argv[1:]
        if argv[0] == str(self.colima) and tail == ('version',): payload = self.tool.COLIMA_VERSION
        elif argv[0] == str(self.bin / 'limactl'): payload = b'limactl version 2.2.0\n'
        elif argv[0] == str(self.colima) and tail == ('list', '--json'):
            private = 'COLIMA_HOME' in self.last_environment
            override = self.private_payload if private else self.foreign_payload
            payload = override if override is not None else canonical([self.private_row if private else self.foreign_row])
        elif argv[0] == str(self.tools / 'docker') and tail == ('context', 'show'): payload = self.context_payload
        elif argv[0] == str(self.tools / 'docker') and tail[0] == '--host' and tail[2:] == ('ps', '--all', '--quiet', '--no-trunc'): payload = self.ps_payload
        else: raise AssertionError(argv)
        return CommandResult(0, payload.decode('utf-8', 'replace'), '', payload, b'')

    def capture(self, argv, environment, stdin, timeout, maximum, cwd):
        self.dispatches.append((argv, environment, stdin, timeout, maximum, cwd))
        self.last_environment = environment
        return self.result(argv)

    def sealed_files(self, foreign):
        records = {path.name: path.read_bytes() for path in self.receipt_path.iterdir()
                   if path.name != 'SHA256SUMS'}
        self.assertEqual(len(records), 46)
        for name in ('file-0000.json', 'file-0001.json'):
            (self.receipt_path / name).unlink(); records.pop(name)
        records['foreign-original.json'] = canonical(foreign)
        records['runtime-kind-config.yaml'] = (self.runtime / 'kind-config.yaml').read_bytes()
        for name in ('foreign-original.json', 'runtime-kind-config.yaml'):
            (self.receipt_path / name).write_bytes(records[name]); (self.receipt_path / name).chmod(0o600)
        manifest = b''.join(hashlib.sha256(payload).hexdigest().encode() + b'  ' + name.encode() + b'\n'
                            for name, payload in sorted(records.items()))
        (self.receipt_path / 'SHA256SUMS').write_bytes(manifest); (self.receipt_path / 'SHA256SUMS').chmod(0o600)
        self.assertEqual(len(records), 46)
        return records

    def test_real_native_and_preflight_accept_exact_running_fixture(self):
        native = self.native()
        self.assertEqual(self.dispatches, [])
        preflight, payloads = self.preflight(native)
        self.assertEqual(preflight['private_inventory'], [self.private_row])
        self.assertEqual(preflight['foreign']['foreign_profiles'], [self.foreign_row])
        self.assertEqual(payloads['kind.yaml'], self.files['runtime-kind-config.yaml'])
        self.assertEqual(len(self.dispatches), 7)
        self.assert_receipt_unchanged()

    def test_real_native_preflight_rejects_nonempty_private_docker(self):
        native = self.native()
        self.ps_payload = b'id\n'
        with self.assertRaisesRegex(ValueError, 'recovery_private_docker_is_not_empty'):
            self.preflight(native)
        self.assert_receipt_unchanged()

    def test_authenticate_false_never_skips_original_ssh_pin(self):
        (self.paths.colima / 'ssh_config').write_bytes(b'wrong original SSH\n')
        native = self.native()
        with self.assertRaises(ValueError):
            self.preflight(native, authenticate=False)

    def test_preflight_refuses_foreign_file_changed_during_final_native_authentication(self):
        native = self.native()
        self.last_auth_mutation(native, lambda: (self.home / '.docker/config.json').write_bytes(b'{"late":true}\n'))

    def test_true_and_false_preflights_return_identical_fresh_observations(self):
        native = self.native()
        first = self.preflight(native)
        second = self.preflight(native, authenticate=False)
        self.assertEqual(first, second)
        self.assertFalse(native.after_stop)
        self.assertEqual(len(self.dispatches), 14)
        self.assertEqual(len(first[1]), 12)
        self.assertIsNone(first[1]['instance-ssh.config'])
        self.assertEqual(first[1]['ha.stdout.log'], b'original log\n')
        retained = {record[0] for record in native.runtime.files}
        self.assertNotIn(self.paths.instance / 'ha.pid', retained)
        self.assertNotIn(self.paths.instance / 'ha.stdout.log', retained)
        self.assert_receipt_unchanged()

    def test_stopped_lock_release_keeps_original_running_capture_and_skips_ps(self):
        (self.paths.disk / 'in_use_by').unlink()
        self.private_row['status'] = 'Stopped'
        native = self.native()
        preflight, _ = self.preflight(native)
        self.assertEqual(preflight['status'], 'Stopped')
        self.assertIsNotNone(self.authenticated_original['lock'])
        self.assertIsNone(preflight['footprint']['lock'])
        self.assertEqual(len(self.dispatches), 6)
        self.assertFalse(any('--host' in call[0] for call in self.dispatches))
        self.assertFalse(native.after_stop)
        self.assert_receipt_unchanged()

    def test_wrong_ssh_before_initial_authentication_is_not_resealed(self):
        (self.paths.colima / 'ssh_config').write_bytes(b'wrong SSH\n')
        native = self.native()
        with self.assertRaises(ValueError): self.preflight(native)
        self.assertEqual(self.tool.SSH_PIN, self.ssh_pin)
        self.assert_receipt_unchanged()

    def test_ssh_change_during_false_preflight_still_refuses_before_stop(self):
        native = self.native()
        self.preflight(native)
        self.last_auth_mutation(native, lambda: (self.paths.colima / 'ssh_config').write_bytes(b'late SSH\n'),
                                authenticate=False)
        self.assertFalse(native.after_stop)

    def test_kind_mode_and_sealed_bytes_are_required_even_without_rebinding(self):
        native = self.native()
        kind = self.runtime / 'kind-config.yaml'
        kind.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'recovery_control_mode_is_invalid'):
            self.preflight(native, authenticate=False)
        kind.chmod(0o600); kind.write_bytes(b'changed kind\n')
        with self.assertRaisesRegex(ValueError, 'recovery_kind_control_changed'):
            self.preflight(native, authenticate=False)

    def test_yaml_mode_is_checked_in_composed_preflight(self):
        native = self.native()
        (self.paths.instance / 'lima.yaml').chmod(0o600)
        with self.assertRaises(ValueError): self.preflight(native)

    def test_changed_original_foreign_config_is_not_adopted(self):
        (self.home / '.docker/config.json').write_bytes(b'{"changed":true}\n')
        native = self.native()
        with self.assertRaisesRegex(ValueError, 'recovery_foreign_state_changed'): self.preflight(native)
        self.assert_receipt_unchanged()

    def test_changed_global_context_is_not_adopted(self):
        native = self.native()
        self.context_payload = b'other\n'
        with self.assertRaisesRegex(ValueError, 'recovery_foreign_state_changed'): self.preflight(native)

    def test_changed_global_roster_is_not_adopted(self):
        native = self.native()
        (self.home / '.colima/_lima/colima-unknown').mkdir(mode=0o700)
        with self.assertRaises(ValueError): self.preflight(native)

    def test_composed_inventory_rejects_empty_partial_malformed_and_unknown_rows(self):
        native = self.native()
        for payload in (b'', b'[]\n', b'{', canonical([{**self.private_row, 'unknown': True}]),
                        canonical([{**self.private_row, 'cpus': 2}])):
            self.private_payload = payload
            with self.subTest(payload=payload), self.assertRaises(ValueError): self.preflight(native)

    def test_private_ps_whitespace_is_not_empty(self):
        native = self.native()
        self.ps_payload = b'\n'
        with self.assertRaisesRegex(ValueError, 'recovery_private_docker_is_not_empty'): self.preflight(native)

    def test_final_native_read_cannot_change_earlier_receipt(self):
        native = self.native()
        self.last_auth_mutation(native, lambda: (self.receipt_path / 'file-0002.json').write_bytes(b'{"late":true}\n'))

    def test_final_native_read_cannot_replace_accepted_docker(self):
        native = self.native()
        self.last_auth_mutation(native, lambda: (self.tools / 'docker').write_bytes(b'late docker\n'))

    def test_final_native_read_cannot_change_passwd_home(self):
        native = self.native()
        self.last_auth_mutation(native, lambda: setattr(self, 'observed_home', self.home / 'other'))

    def test_final_native_read_cannot_change_effective_uid(self):
        native = self.native()
        uid, changed = os.geteuid(), False
        def change():
            nonlocal changed
            changed = True
        with patch.object(self.tool.os, 'geteuid', side_effect=lambda: uid + 1 if changed else uid):
            self.last_auth_mutation(native, change)

    def test_final_native_read_cannot_change_earlier_yaml(self):
        native = self.native()
        self.last_auth_mutation(native, lambda: (self.paths.profile / 'colima.yaml').write_bytes(b'late YAML\n'))

    def test_final_native_read_cannot_replace_earlier_disk(self):
        native = self.native()
        data = self.paths.disk / 'datadisk'
        def replace():
            size, mode = data.stat().st_size, stat.S_IMODE(data.stat().st_mode)
            data.rename(self.registry / 'saved-datadisk')
            with data.open('wb') as stream: stream.truncate(size)
            data.chmod(mode)
        self.last_auth_mutation(native, replace)

    def test_final_native_read_cannot_add_private_namespace_entry(self):
        native = self.native()
        self.last_auth_mutation(native, lambda: (self.runtime / 'unexpected').write_bytes(b'late\n'))

    def test_final_native_read_cannot_change_transient_present_control(self):
        native = self.native()
        self.last_auth_mutation(native, lambda: (self.paths.instance / 'ha.stdout.log').write_bytes(b'late log\n'))

    def test_final_native_read_cannot_create_transient_absent_control(self):
        native = self.native()
        self.last_auth_mutation(native, lambda: (self.paths.instance / 'ssh.config').write_bytes(b'late ssh\n'))

    def test_guest_disk_write_beyond_header_is_not_a_whole_disk_fingerprint(self):
        native = self.native()
        def write_guest():
            with (self.paths.disk / 'datadisk').open('r+b') as stream:
                stream.seek(1024); stream.write(b'ordinary guest write')
        self.last_auth_mutation(native, write_guest, refuse=False)
        self.assert_receipt_unchanged()

    def test_unrelated_registry_sibling_is_not_part_of_final_scope(self):
        native = self.native()
        self.last_auth_mutation(native, lambda: (self.registry / 'unrelated-runtime').mkdir(mode=0o700), refuse=False)
        self.assert_receipt_unchanged()

    def test_last_foreign_roster_read_cannot_reanchor_private_disk(self):
        from kil import v3b2_profile_state as profile_state
        native = self.native()
        actual_read, reads, changed = profile_state._read, 0, False
        def read_then_change(path, **kwargs):
            nonlocal reads, changed
            value = actual_read(path, **kwargs)
            if path == self.home / '.colima/_lima' and len(self.dispatches) == 7:
                reads += 1
                if reads == 2:
                    changed = True
                    data = self.paths.disk / 'datadisk'
                    size, mode = data.stat().st_size, stat.S_IMODE(data.stat().st_mode)
                    data.rename(self.registry / 'late-saved-disk')
                    with data.open('wb') as stream: stream.truncate(size)
                    data.chmod(mode)
            return value
        with patch.object(profile_state, '_read', side_effect=read_then_change):
            try:
                self.preflight(native)
            except ValueError:
                self.assertTrue(changed)
            else:
                self.assertEqual(reads, 0, 'successful closure must not reopen a foreign roster content read')

    def test_final_foreign_metadata_performs_no_directory_or_file_content_reads(self):
        self.native()
        roster = json.loads(self.saved_files['foreign-original.json'])['foreign_lima_roster']
        with patch.object(self.tool, 'capture_roster', wraps=self.tool.capture_roster) as roster_reads, \
             patch.object(self.tool, '_read', wraps=self.tool._read) as content_reads, \
             patch.object(self.tool, 'read_regular', wraps=self.tool.read_regular) as file_reads, \
             patch.object(os, 'scandir', wraps=os.scandir) as listings, \
             patch.object(os, 'listdir', wraps=os.listdir) as names:
            self.tool._foreign_metadata(roster)
        for call in (roster_reads, content_reads, file_reads, listings, names): call.assert_not_called()

    def last_foreign_roster_mutation(self, mutate):
        from kil import v3b2_profile_state as profile_state
        native = self.native()
        actual_read, reads, changed = profile_state._read, 0, False
        def read_then_change(path, **kwargs):
            nonlocal reads, changed
            value = actual_read(path, **kwargs)
            # The second _read closes the final roster after the second global
            # list command. Mutation is real and precedes only later checks.
            if path == self.home / '.colima/_lima' and len(self.dispatches) == 6:
                reads += 1
                if reads == 2:
                    changed = True
                    mutate()
            return value
        with patch.object(profile_state, '_read', side_effect=read_then_change):
            with self.assertRaises(ValueError): self.preflight(native)
        self.assertTrue(changed)

    def test_last_remaining_foreign_roster_content_read_cannot_replace_private_disk(self):
        def replace():
            data = self.paths.disk / 'datadisk'
            size, mode = data.stat().st_size, stat.S_IMODE(data.stat().st_mode)
            data.rename(self.registry / 'late-roster-disk')
            with data.open('wb') as stream: stream.truncate(size)
            data.chmod(mode)
        self.last_foreign_roster_mutation(replace)

    def test_last_remaining_foreign_roster_content_read_cannot_add_private_namespace_entry(self):
        self.last_foreign_roster_mutation(lambda: (self.runtime / 'late-namespace').write_bytes(b'changed\n'))

    def test_last_native_read_cannot_create_previously_absent_global_kubeconfig(self):
        native = self.native()
        self.last_auth_mutation(native, lambda: (self.home / '.kube/config').write_bytes(b'late config\n'))

    def test_last_native_read_cannot_replace_known_global_roster_child(self):
        native = self.native()
        child = self.home / '.colima/_lima/colima-kil-v3-lab'
        def replace():
            child.rename(self.home / 'old-global-child'); child.mkdir(mode=0o700)
        self.last_auth_mutation(native, replace)

    def test_last_native_read_cannot_add_unknown_global_roster_child(self):
        native = self.native()
        self.last_auth_mutation(native, lambda: (self.home / '.colima/_lima/colima-unknown').mkdir(mode=0o700))

    def test_foreign_context_parser_rejects_empty_decoded_line(self):
        native = self.native()
        for payload in (b'\n', b' \n', b'\t\n'):
            self.context_payload = payload
            with self.subTest(payload=payload), self.assertRaises(ValueError): self.tool._foreign(native)

    def test_final_foreign_metadata_requires_bounded_valid_original_roster(self):
        self.native()
        roster = json.loads(self.saved_files['foreign-original.json'])['foreign_lima_roster']
        roster['directory']['entries'][1] = 'unrecognized'
        roster['children'][1]['name'] = 'unrecognized'
        with self.assertRaises(ValueError): self.tool._foreign_metadata(roster)

    def test_global_empty_inventory_is_valid_only_when_actual_roster_is_empty(self):
        native = self.native()
        self.foreign_payload = b''
        with self.assertRaises(ValueError): self.tool._foreign(native)
        (self.home / '.colima/_lima/colima-kil-v3-lab').rmdir()
        observed = self.tool._foreign(native)
        self.assertEqual(observed['foreign_profiles'], [])
        self.assertEqual(observed['foreign_lima_roster']['directory']['entries'], ['_config'])
        with self.assertRaisesRegex(ValueError, 'recovery_foreign_state_changed'): self.preflight(native)
        self.assert_receipt_unchanged()

    def test_global_empty_inventory_is_valid_when_actual_roster_is_absent(self):
        native = self.native()
        self.foreign_payload = b'[]\n'
        lima = self.home / '.colima/_lima'
        (lima / 'colima-kil-v3-lab').rmdir()
        (lima / '_config/networks.yaml').unlink()
        (lima / '_config').rmdir(); lima.rmdir()
        observed = self.tool._foreign(native)
        self.assertEqual(observed['foreign_profiles'], [])
        self.assertIsNone(observed['foreign_lima_roster'])
        self.assertFalse(lima.exists())
        self.assert_receipt_unchanged()

    def test_foreign_context_requires_bounded_utf8_single_lf_without_cr(self):
        native = self.native()
        for payload in (b'', b'default', b'default\r\n', b'default\nother\n', b'\xff\n', b'x' * 4096 + b'\n'):
            self.context_payload = payload
            with self.subTest(payload=payload[:32]), self.assertRaises(ValueError): self.tool._foreign(native)

    def test_stopped_preflight_accepts_all_permitted_control_removals_without_ps(self):
        for parent, names in ((self.paths.profile, ('docker.sock', 'containerd.sock')),
                              (self.paths.instance, ('ha.pid', 'ha.sock', 'ssh.sock', 'vz.pid'))):
            for name in names: (parent / name).unlink()
        (self.paths.disk / 'in_use_by').unlink(); (self.paths.colima / 'ssh_config').unlink()
        self.private_row['status'] = 'Stopped'
        native = self.native()
        preflight, payloads = self.preflight(native)
        self.assertEqual(preflight['status'], 'Stopped')
        for label in ('colima-ssh.config', 'ha.pid', 'vz.pid'): self.assertIsNone(payloads[label])
        self.assertEqual(len(self.dispatches), 6)
        self.assert_receipt_unchanged()

    def test_final_native_read_cannot_change_real_uid(self):
        native = self.native()
        uid, changed = os.getuid(), False
        def change():
            nonlocal changed
            changed = True
        with patch.object(self.tool.os, 'getuid', side_effect=lambda: uid + 1 if changed else uid):
            self.last_auth_mutation(native, change)


class Task4OnceTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.temporary = tempfile.TemporaryDirectory(prefix='kil-task4-once-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.store = self.tool.PrivateStore(self.root / 'recovery')
        self.addCleanup(self.store.close)

    def test_once_persists_exact_intent_before_check_and_only_dispatch(self):
        self.assertTrue(hasattr(self.tool, '_Once'), 'durable one-stop gate is missing')
        once = self.tool._Once(self.store)
        payload, events = canonical({'max_native_mutations': 1}), []
        def check():
            self.assertTrue(once.used)
            self.assertEqual((self.store.path / 'manual-stop-intent.json').read_bytes(), payload)
            events.append('check')
        def dispatch():
            events.append('dispatch')
            return 'returned'
        self.assertEqual(once.send(payload, check, dispatch), 'returned')
        with self.assertRaises(ValueError): once.send(payload, check, dispatch)
        self.assertEqual(events, ['check', 'dispatch'])

    def test_once_fsync_failure_consumes_slot_before_check_or_dispatch(self):
        self.assertTrue(hasattr(self.tool, '_Once'), 'durable one-stop gate is missing')
        once = self.tool._Once(self.store)
        events, failure = [], OSError('fixture fsync failure')
        with patch.object(self.tool.os, 'fsync', side_effect=failure):
            with self.assertRaises(OSError) as raised:
                once.send(b'{}\n', lambda: events.append('check'), lambda: events.append('dispatch'))
        self.assertIs(raised.exception, failure)
        self.assertTrue(once.used)
        with self.assertRaises(ValueError): once.send(b'{}\n', lambda: None, lambda: None)
        self.assertEqual(events, [])

    def test_once_check_failure_and_dispatch_uncertainty_never_retry(self):
        self.assertTrue(hasattr(self.tool, '_Once'), 'durable one-stop gate is missing')
        for stage in ('check', 'dispatch'):
            with self.subTest(stage=stage):
                store = self.tool.PrivateStore(self.root / stage)
                self.addCleanup(store.close)
                once, events = self.tool._Once(store), []
                failure = OSError('fixture ' + stage)
                def check():
                    events.append('check')
                    if stage == 'check': raise failure
                def dispatch():
                    events.append('dispatch')
                    raise failure
                with self.assertRaises(OSError) as raised: once.send(b'{}\n', check, dispatch)
                self.assertIs(raised.exception, failure)
                with self.assertRaises(ValueError): once.send(b'{}\n', check, dispatch)
                self.assertEqual(events, ['check'] if stage == 'check' else ['check', 'dispatch'])

    def test_once_preexisting_intent_is_never_adopted_or_overwritten(self):
        self.store.write('manual-stop-intent.json', b'pending old intent\n')
        once, events = self.tool._Once(self.store), []
        with self.assertRaises(FileExistsError):
            once.send(b'new intent\n', lambda: events.append('check'), lambda: events.append('dispatch'))
        self.assertTrue(once.used)
        with self.assertRaises(ValueError): once.send(b'new intent\n', lambda: None, lambda: None)
        self.assertEqual(events, [])
        self.assertEqual((self.store.path / 'manual-stop-intent.json').read_bytes(), b'pending old intent\n')

    def test_once_directory_fsync_failure_is_not_durable_authority(self):
        once, events = self.tool._Once(self.store), []
        real_fsync, calls = os.fsync, []
        failure = OSError('fixture directory fsync failure')
        def sync(fd):
            calls.append(fd)
            if fd == self.store._directory: raise failure
            return real_fsync(fd)
        with patch.object(self.tool.os, 'fsync', side_effect=sync):
            with self.assertRaises(OSError) as raised:
                once.send(b'{}\n', lambda: events.append('check'), lambda: events.append('dispatch'))
        self.assertIs(raised.exception, failure)
        self.assertEqual(len(calls), 2)
        self.assertTrue(once.used)
        self.assertEqual(events, [])


class Task4StoreTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.temporary = tempfile.TemporaryDirectory(prefix='kil-task4-store-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.recovery = self.root / '.tools/hf-recovery-private/2026-09-17' / ('manual-stop-' + self.tool.DIGEST)
        selector = patch.multiple(self.tool, REPOSITORY=self.root, RECOVERY=self.recovery, UID=os.geteuid())
        selector.start(); self.addCleanup(selector.stop)
        self.proof = self.tool._Files(); self.addCleanup(self.proof.close)

    def new_store(self):
        self.assertTrue(hasattr(self.tool, '_new_store'), 'anchored exclusive recovery store is missing')
        store = self.tool._new_store(self.proof)
        self.addCleanup(store.close)
        return store

    def test_new_store_creates_only_fixed_private_parents_and_exclusive_receipt(self):
        store = self.new_store()
        for path in (self.root / '.tools', self.recovery.parent.parent, self.recovery.parent, self.recovery):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
            self.assertEqual(path.stat().st_uid, os.geteuid())
            self.assertIn(path, self.proof.directories)
        self.assertEqual(store.path, self.recovery)
        lock = [record for record in self.proof.files if record[0] == self.recovery / 'lock']
        self.assertEqual(len(lock), 1)
        self.assertEqual(lock[0][2], self.tool._fid(os.fstat(store._lock)))
        self.assertEqual(lock[0][2][5], 0)
        with self.assertRaises((ValueError, FileExistsError)): self.new_store()
        self.assertEqual([p.name for p in self.recovery.parent.iterdir()], [self.recovery.name])

    def test_new_store_refuses_unsafe_existing_parent_without_repair(self):
        parent = self.root / '.tools'; parent.mkdir(mode=0o755)
        with self.assertRaises(ValueError): self.new_store()
        self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o755)
        self.assertFalse(self.recovery.parent.parent.exists())

    def test_new_store_refuses_symlink_parent_without_following(self):
        target = self.root / 'target'; target.mkdir(mode=0o700)
        (self.root / '.tools').symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError): self.new_store()
        self.assertEqual(list(target.iterdir()), [])

    def test_new_store_refuses_parent_reanchored_during_real_constructor(self):
        self.assertTrue(hasattr(self.tool, '_new_store'), 'anchored exclusive recovery store is missing')
        real_fsync, changed = os.fsync, False
        def sync_then_replace(fd):
            nonlocal changed
            result = real_fsync(fd)
            if not changed and self.recovery.exists():
                changed = True
                self.recovery.parent.rename(self.recovery.parent.with_name('old-date'))
                self.recovery.parent.mkdir(mode=0o700)
            return result
        with patch.object(self.tool.os, 'fsync', side_effect=sync_then_replace):
            with self.assertRaises((OSError, ValueError)): self.new_store()
        self.assertTrue(changed)
        self.assertFalse(self.recovery.exists())

    def test_new_store_closes_constructor_descriptors_after_real_fsync_failure(self):
        opened, real_open, real_fsync = [], os.open, os.fsync
        def tracked_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd
        def sync(fd):
            if self.recovery.exists(): raise OSError('fixture constructor fsync failure')
            return real_fsync(fd)
        with patch.object(self.tool.os, 'open', side_effect=tracked_open), \
             patch.object(self.tool.os, 'fsync', side_effect=sync):
            with self.assertRaises(OSError): self.new_store()
        self.proof.close()
        for fd in set(opened):
            with self.assertRaises(OSError): os.fstat(fd)

    def test_new_store_closes_store_and_owned_proof_descriptors_after_binding_failure(self):
        opened, real_open, real_read = [], os.open, self.tool.read_regular
        changed = False
        def tracked_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd
        def read_then_change(path, maximum):
            nonlocal changed
            payload = real_read(path, maximum)
            if path == self.recovery / 'lock' and not changed:
                changed = True
                path.write_bytes(b'not empty\n')
            return payload
        with patch.object(self.tool.os, 'open', side_effect=tracked_open), \
             patch.object(self.tool, 'read_regular', side_effect=read_then_change):
            with self.assertRaises(ValueError): self.new_store()
        self.assertTrue(changed)
        self.proof.close()
        for fd in set(opened):
            with self.assertRaises(OSError): os.fstat(fd)

    def test_new_store_refuses_wrong_expected_owner_before_creating_private_ancestry(self):
        parent = self.root / '.tools'; parent.mkdir(mode=0o700)
        with patch.object(self.tool, 'UID', os.geteuid() + 1):
            with self.assertRaises(ValueError): self.new_store()
        self.assertEqual(list(parent.iterdir()), [])

    def test_new_store_refuses_changed_fixed_target_without_creating_ancestry(self):
        with patch.object(self.tool, 'RECOVERY', self.recovery.with_name('alternate')):
            with self.assertRaises(ValueError): self.new_store()
        self.assertFalse((self.root / '.tools').exists())


class Task4SealTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.temporary = tempfile.TemporaryDirectory(prefix='kil-task4-seal-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        selector = patch.object(self.tool, 'UID', os.geteuid())
        selector.start(); self.addCleanup(selector.stop)
        self.store = self.tool.PrivateStore(self.root / 'recovery')
        self.addCleanup(self.store.close)

    def seal(self):
        self.assertTrue(hasattr(self.tool, '_seal'), 'new-receipt-only sealing is missing')
        return self.tool._seal(self.store)

    def test_seal_hashes_every_actual_evidence_file_including_lock_and_journal(self):
        self.store.write('outcome.json', canonical({'status': 'preflight_refused'}))
        self.store.record('observation', {'value': 1})
        before = {path.name: path.read_bytes() for path in self.store.path.iterdir()}
        self.seal()
        expected = b''.join(hashlib.sha256(payload).hexdigest().encode() + b'  ' + name.encode() + b'\n'
                            for name, payload in sorted(before.items()))
        self.assertEqual((self.store.path / 'SHA256SUMS').read_bytes(), expected)
        self.assertEqual({p.name: p.read_bytes() for p in self.store.path.iterdir() if p.name != 'SHA256SUMS'}, before)
        with self.assertRaises(ValueError): self.seal()

    def test_seal_refuses_bad_filename_and_metadata_without_repairs(self):
        for name, kind in (('space name', 'regular'), ('unicode-é', 'regular'), ('.hidden', 'regular'),
                           ('a' * 129, 'regular'), ('directory', 'directory'), ('symlink', 'symlink'),
                           ('hardlink', 'hardlink'), ('wrongmode', 'mode'), ('oversized', 'size')):
            with self.subTest(name=name):
                path = self.store.path / name
                if kind == 'directory': path.mkdir(mode=0o700)
                elif kind == 'symlink': path.symlink_to(self.store.path / 'lock')
                elif kind == 'hardlink': os.link(self.store.path / 'journal.jsonl', path)
                else:
                    path.write_bytes(b'x'); path.chmod(0o644 if kind == 'mode' else 0o600)
                    if kind == 'size':
                        with path.open('r+b') as stream: stream.truncate(self.tool.MAXIMUM + 1)
                try:
                    with self.assertRaises(ValueError): self.seal()
                    self.assertFalse((self.store.path / 'SHA256SUMS').exists())
                finally:
                    if kind == 'directory': path.rmdir()
                    else: path.unlink()

    def test_seal_refuses_roster_above_256(self):
        for index in range(255): self.store.write('file-%03d' % index, b'')
        self.assertEqual(len(list(self.store.path.iterdir())), 257)
        with self.assertRaises(ValueError): self.seal()
        self.assertFalse((self.store.path / 'SHA256SUMS').exists())

    def test_seal_refuses_earlier_file_changed_during_later_authentication_io(self):
        self.store.write('aaa', b'original\n'); self.store.write('zzz', b'later\n')
        real_read, changed = self.tool.read_regular, False
        def read_then_mutate(path, maximum):
            nonlocal changed
            value = real_read(path, maximum)
            if path.name == 'zzz' and not changed:
                changed = True
                (self.store.path / 'aaa').write_bytes(b'changed!\n')
            return value
        with patch.object(self.tool, 'read_regular', side_effect=read_then_mutate):
            with self.assertRaises(ValueError): self.seal()
        self.assertTrue(changed)
        self.assertFalse((self.store.path / 'SHA256SUMS').exists())

    def test_seal_refuses_unknown_roster_added_during_later_authentication_io(self):
        self.store.write('zzz', b'later\n')
        real_read, changed = self.tool.read_regular, False
        def read_then_mutate(path, maximum):
            nonlocal changed
            value = real_read(path, maximum)
            if path.name == 'zzz' and not changed:
                changed = True
                (self.store.path / 'unknown').write_bytes(b'late\n')
                (self.store.path / 'unknown').chmod(0o600)
            return value
        with patch.object(self.tool, 'read_regular', side_effect=read_then_mutate):
            with self.assertRaises(ValueError): self.seal()
        self.assertTrue(changed)
        self.assertFalse((self.store.path / 'SHA256SUMS').exists())

    def test_seal_accepts_final_256_names_with_exact_128_character_basename(self):
        for index in range(252): self.store.write('file-%03d' % index, b'')
        self.store.write('a' * 128, b'')
        self.seal()
        self.assertEqual(len(list(self.store.path.iterdir())), 256)

    def test_seal_reserves_manifest_name_within_final_roster_bound(self):
        for index in range(254): self.store.write('file-%03d' % index, b'')
        with self.assertRaises(ValueError): self.seal()
        self.assertFalse((self.store.path / 'SHA256SUMS').exists())

    def test_seal_aggregate_limit_uses_actual_files_independently_of_store_counter(self):
        for index in range(32):
            path = self.store.path / ('sparse-%03d' % index)
            with path.open('wb') as stream: stream.truncate(8 * 1024**2)
            path.chmod(0o600)
        self.assertLess(self.store.total, 1024)
        with self.assertRaises(ValueError): self.seal()
        self.assertFalse((self.store.path / 'SHA256SUMS').exists())

    def test_seal_refuses_size_growth_between_roster_stat_and_retained_authentication(self):
        for index in range(32):
            path = self.store.path / ('sparse-%03d' % index)
            size = self.tool.MAXIMUM - 8192 if index == 0 else self.tool.MAXIMUM
            with path.open('wb') as stream: stream.truncate(size)
            path.chmod(0o600)
        real_stat, changed = os.stat, False
        def stat_then_grow(path, *args, **kwargs):
            nonlocal changed
            row = real_stat(path, *args, **kwargs)
            directory = kwargs.get('dir_fd')
            if (path == 'sparse-000' and directory is not None and not changed
                    and self.tool._id(os.fstat(directory)) == self.tool._id(os.fstat(self.store._directory))):
                changed = True
                with (self.store.path / path).open('r+b') as stream: stream.truncate(self.tool.MAXIMUM)
            return row
        with patch.object(self.tool.os, 'stat', side_effect=stat_then_grow):
            try:
                self.seal()
            except ValueError:
                pass
            else:
                actual = sum(path.stat().st_size for path in self.store.path.iterdir())
                self.fail('seal accepted actual %d bytes above bound %d' % (actual, 256 * 1024**2))
        self.assertTrue(changed)
        self.assertFalse((self.store.path / 'SHA256SUMS').exists())

    def test_seal_refuses_same_size_change_between_roster_stat_and_retained_authentication(self):
        self.store.write('evidence', b'original\n')
        real_stat, changed = os.stat, False
        def stat_then_change(path, *args, **kwargs):
            nonlocal changed
            row = real_stat(path, *args, **kwargs)
            if path == 'evidence' and kwargs.get('dir_fd') is not None and not changed:
                changed = True
                (self.store.path / 'evidence').write_bytes(b'changed!\n')
            return row
        with patch.object(self.tool.os, 'stat', side_effect=stat_then_change):
            with self.assertRaises(ValueError): self.seal()
        self.assertTrue(changed)
        self.assertFalse((self.store.path / 'SHA256SUMS').exists())

    def test_seal_store_total_limit_includes_exclusive_manifest_bytes(self):
        self.store.total = 256 * 1024**2
        with self.assertRaisesRegex(ValueError, 'private_store_byte_bound'): self.seal()
        self.assertFalse((self.store.path / 'SHA256SUMS').exists())

    def test_store_total_limit_applies_independently_to_journal_append(self):
        self.store.total = 256 * 1024**2
        before = self.store.journal.read_bytes()
        with self.assertRaisesRegex(ValueError, 'private_store_byte_bound'):
            self.store.record('not_persisted', {})
        self.assertEqual(self.store.journal.read_bytes(), before)

    def test_seal_refuses_wrong_expected_owner_and_replaced_lock_descriptor(self):
        with patch.object(self.tool, 'UID', os.geteuid() + 1):
            with self.assertRaises(ValueError): self.seal()
        replacement = self.root / 'replacement'; replacement.touch(mode=0o600)
        fd = os.open(replacement, os.O_RDWR | os.O_NOFOLLOW)
        try: os.dup2(fd, self.store._lock)
        finally: os.close(fd)
        with self.assertRaises(ValueError): self.seal()
        self.assertFalse((self.store.path / 'SHA256SUMS').exists())

    def test_seal_refuses_late_evidence_mutation_during_manifest_fsync(self):
        self.store.write('aaa', b'original\n')
        real_fsync, changed = os.fsync, False
        def sync_then_mutate(fd):
            nonlocal changed
            result = real_fsync(fd)
            if not changed and (self.store.path / 'SHA256SUMS').exists():
                changed = True
                (self.store.path / 'aaa').write_bytes(b'changed!\n')
            return result
        with patch.object(self.tool.os, 'fsync', side_effect=sync_then_mutate):
            with self.assertRaises(ValueError): self.seal()
        self.assertTrue(changed)
        manifest = (self.store.path / 'SHA256SUMS').read_bytes()
        with self.assertRaises(ValueError): self.seal()
        self.assertEqual((self.store.path / 'SHA256SUMS').read_bytes(), manifest)


if __name__ == '__main__':
    unittest.main()
