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


if __name__ == '__main__':
    unittest.main()
