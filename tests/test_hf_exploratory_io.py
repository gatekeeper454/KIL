import importlib
import importlib.util
import json
from hashlib import sha256
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from kil.v3b1_driver_protocol import canonical_record
from kil.v3b2_contracts import TRACKS
from kil.v3b2_journal import Command, COLIMA_START_ARGV
from kil.hf_exploratory_inputs import ACCEPTED_RUN, ACCEPTED_MANIFEST_SHA256, ExploratoryInputs, verify_bytes


def terminal(track):
    return canonical_record(dict(schema_version='kil.v3b1-driver-result.v1',
        track=track, status='complete', attempt_count=1, retry_performed=False,
        connect_monotonic_ns=1, send_monotonic_ns=2, receive_monotonic_ns=3,
        response_status=200, decision_digest='a' * 64))


class IOTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_io'))
        self.io = importlib.import_module('kil.hf_exploratory_io')
        from kil import hf_exploratory_runtime as runtime_module
        compact = tempfile.TemporaryDirectory(prefix='k', dir='/private/tmp')
        self.addCleanup(compact.cleanup)
        self.registry = Path(compact.name).resolve() / 'k'
        selector = patch.object(runtime_module, '_registry_parent', return_value=self.registry, create=True)
        selector.start()
        self.addCleanup(selector.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def store(self):
        store = self.io.PrivateStore(Path(self.temp.name).resolve() / 'run')
        self.addCleanup(store.close)
        return store

    def accepted_inputs(self, tools=None):
        manifest = (Path.cwd() / 'artifacts/generated/v3b1-local-envoy' / ACCEPTED_RUN / 'manifest.json').read_bytes()
        verify_bytes(manifest, ACCEPTED_MANIFEST_SHA256, len(manifest))
        # Real frozen container; unused readiness fields are inert test placeholders.
        return ExploratoryInputs(None, b'', None, b'', tools or Path(self.temp.name).resolve(),
            json.loads(manifest)['verified_tool_identities'], manifest)

    def runtime_authority(self):
        from kil.hf_exploratory_runtime import RuntimeAuthority
        parent = Path(self.temp.name).resolve() / '.tools' / 'hf-exploratory-private'
        parent.mkdir(parents=True, mode=0o700)
        store = self.io.PrivateStore(parent / ('hf-exploratory-' + 'a' * 64))
        self.addCleanup(store.close)
        authority = RuntimeAuthority.create(store, 'a' * 64)
        self.addCleanup(authority.close)
        return authority

    def test_node_alias_routes_use_pinned_docker_and_current_private_environment(self):
        from kil.hf_exploratory_runtime import ExploratoryNodeAliasCommand
        from kil.v3b2_journal import OwnedIdentity
        authority = self.runtime_authority()
        identity = OwnedIdentity('kil-v3-lab','unix://'+str(authority.colima/'kil-v3-lab/docker.sock'),
                                 'kil-v3-lab',str(authority.kubeconfig),'cluster-uid','b'*64)
        inputs, colima, verify = self.dependency_fixture()
        for operation, reference in [('inspect',None),('tag',None),('remove','import-2026-09-18@sha256:'+'a'*64)]:
            command = ExploratoryNodeAliasCommand(authority,identity,'kil',operation,reference)
            with self.subTest(operation=operation), patch.dict(os.environ,{'PATH':str(colima.parent)}), \
                    patch.object(self.io,'verify_bytes',side_effect=verify), patch.object(self.io,'capture_process') as capture:
                self.io.BoundedRunner(Path.cwd(),inputs).run(command)
                argv, env, stdin, timeout, _, _ = capture.call_args.args
                self.assertEqual(argv,(str(inputs.tools/'docker'),*command.argv[1:]))
                self.assertEqual({key:env[key] for key,_ in command.env},dict(command.env))
                self.assertEqual(env['PATH'],str(colima.parent)); self.assertIsNone(stdin); self.assertEqual(timeout,10)

    def test_node_alias_route_refuses_late_runtime_or_node_substitution(self):
        from kil.hf_exploratory_runtime import ExploratoryNodeAliasCommand
        from kil.v3b2_journal import OwnedIdentity
        authority = self.runtime_authority()
        for changed in ('runtime','node'):
            identity = OwnedIdentity('kil-v3-lab','unix://'+str(authority.colima/'kil-v3-lab/docker.sock'),
                                     'kil-v3-lab',str(authority.kubeconfig),'cluster-uid','b'*64)
            command = ExploratoryNodeAliasCommand(authority,identity,'kil','tag')
            inputs, _, verify = self.dependency_fixture()
            def changing(data,digest,size):
                value = verify(data,digest,size)
                if data == b'inert fixture: docker':
                    if changed == 'runtime': object.__setattr__(authority,'_digest','b'*64)
                    else: object.__setattr__(identity,'node_container_id','f'*64)
                return value
            with self.subTest(changed=changed), patch.object(self.io,'verify_bytes',side_effect=changing), \
                    patch.object(self.io,'capture_process') as capture:
                with self.assertRaises(ValueError): self.io.BoundedRunner(Path.cwd(),inputs).run(command)
            capture.assert_not_called()
            object.__setattr__(authority,'_digest','a'*64)

    def test_envoy_platform_command_uses_authenticated_docker_and_owned_environment(self):
        from kil import hf_exploratory_runtime as runtime
        command_type = getattr(runtime,'ExploratoryEnvoyPlatformCommand',None)
        self.assertIsNotNone(command_type,'finite platform pull type is missing')
        authority = self.runtime_authority(); command = command_type(authority)
        inputs, colima, verify = self.dependency_fixture()
        with patch.dict(os.environ,{'PATH':str(colima.parent)}), patch.object(self.io,'verify_bytes',side_effect=verify), \
                patch.object(self.io,'capture_process') as capture:
            self.io.BoundedRunner(Path.cwd(),inputs).run(command)
        argv,env,stdin,timeout,_,_ = capture.call_args.args
        self.assertEqual(argv,(str(inputs.tools/'docker'),*command.argv[1:]))
        self.assertEqual({key:env[key] for key,_ in command.env},dict(command.env))
        self.assertEqual(env['PATH'],str(colima.parent)); self.assertIsNone(stdin); self.assertEqual(timeout,300)

    def test_envoy_platform_command_recloses_runtime_after_docker_authentication(self):
        from kil.hf_exploratory_runtime import ExploratoryEnvoyPlatformCommand
        authority = self.runtime_authority(); command = ExploratoryEnvoyPlatformCommand(authority)
        inputs, _, verify = self.dependency_fixture()
        def changing(data,digest,size):
            result = verify(data,digest,size)
            if data == b'inert fixture: docker': object.__setattr__(authority,'_digest','b'*64)
            return result
        with patch.object(self.io,'verify_bytes',side_effect=changing), patch.object(self.io,'capture_process') as capture:
            with self.assertRaises(ValueError): self.io.BoundedRunner(Path.cwd(),inputs).run(command)
        capture.assert_not_called()

    def test_scoped_start_uses_accepted_dependency_path_and_original_colima(self):
        authority = self.runtime_authority()
        inputs, colima, verify = self.dependency_fixture()
        command = self.scoped_mutation(authority)
        namespace = command.env
        with patch.dict(os.environ, {'PATH': str(colima.parent)}), \
                patch.object(self.io, 'verify_bytes', side_effect=verify), \
                patch.object(self.io, 'capture_process') as capture:
            self.io.BoundedRunner(Path.cwd(), inputs).run(command)
            argv, env, _, _, _, _ = capture.call_args.args
            self.assertEqual(argv, (str(colima), *COLIMA_START_ARGV[1:]))
            self.assertEqual(env['PATH'], str(inputs.tools) + os.pathsep + str(colima.parent))
            self.assertEqual({key: env[key] for key, _ in namespace}, dict(namespace))
            self.assertEqual(command.env, namespace)
            self.assertEqual(os.environ['PATH'], str(colima.parent))

    def dependency_fixture(self):
        root = Path(tempfile.mkdtemp(dir=self.temp.name)).resolve()
        tools = root / '.tools' / 'bin'
        original = root / 'original-bin'
        tools.mkdir(parents=True)
        original.mkdir()
        payloads = {name: ('inert fixture: ' + name).encode() for name in ('docker', 'kind', 'kubectl')}
        for name, payload in payloads.items():
            (tools / name).write_bytes(payload)
            (tools / name).chmod(0o755)
        colima = original / 'colima'
        colima.write_bytes(b'inert original colima fixture')
        colima.chmod(0o755)
        inputs = self.accepted_inputs(tools)
        rows = json.loads(inputs.manifest_bytes)['verified_tool_identities']
        real_verify = self.io.verify_bytes
        def verify(data, digest, size):
            if digest == ACCEPTED_MANIFEST_SHA256:
                return real_verify(data, digest, size)
            for name, row in rows.items():
                if digest == row['executable_sha256']:
                    self.assertEqual((digest, size), (row['executable_sha256'], row['byte_size']))
                    if data == payloads[name]:
                        return digest
            return real_verify(data, digest, size)
        return inputs, colima, verify

    def scoped_mutation(self, authority, argv=COLIMA_START_ARGV):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        return ExploratoryColimaCommand(Command(argv, 1, mutating=True), authority)

    def kind_mutations(self):
        from kil.v3b2_journal import OwnedIdentity, kind_create_command, kind_delete_command, kind_load_command
        from kil.v3b2_accepted_images import ACCEPTED_IMAGES
        root = Path(self.temp.name).resolve()/'owned'
        identity = OwnedIdentity('kil-v3-lab','unix://'+str(root/'.colima/kil-v3-lab/docker.sock'),
                                 'kil-v3-lab',str(root/'kubeconfig'),None,None)
        return (kind_create_command(identity),kind_delete_command(identity),
                kind_load_command(identity,ACCEPTED_IMAGES[0].requested_image))

    def test_mutating_kind_prioritizes_complete_accepted_tools_without_empty_path_entries(self):
        for command in self.kind_mutations():
            for tail in [None,'','/inert/bin',''+os.pathsep+'/inert/bin'+os.pathsep+os.pathsep]:
                with self.subTest(argv=command.argv,tail=tail):
                    inputs, _, verify = self.dependency_fixture()
                    with patch.dict(os.environ,{},clear=True), patch.object(self.io,'verify_bytes',side_effect=verify), \
                            patch.object(self.io.shutil,'which') as locator, patch.object(self.io,'capture_process') as capture:
                        if tail is not None: os.environ['PATH'] = tail
                        self.io.BoundedRunner(Path.cwd(),inputs).run(command)
                        argv,env,*_ = capture.call_args.args
                        expected = [str(inputs.tools)] + ([part for part in tail.split(os.pathsep) if part] if tail else [])
                        self.assertIn('PATH',env,'accepted child dependency PATH is missing')
                        self.assertEqual(env['PATH'].split(os.pathsep),expected)
                        self.assertEqual(argv,(str(inputs.tools/'kind'),*command.argv[1:]))
                        self.assertEqual({key:env[key] for key,_ in command.env},dict(command.env))
                        locator.assert_not_called()
                        self.assertEqual(os.environ.get('PATH'),tail)

    def test_mutating_kind_rejects_missing_child_docker_and_unaccepted_roster(self):
        for command in self.kind_mutations():
            for fault in ['missing-docker','extra-entry']:
                with self.subTest(argv=command.argv,fault=fault):
                    fixture = self.dependency_fixture()
                    if fault == 'missing-docker': (fixture[0].tools/'docker').unlink()
                    else: (fixture[0].tools/'extra').write_bytes(b'unknown')
                    self.assert_dependency_rejected(fixture,command)

    def test_mutating_kind_recloses_dependencies_and_caller_authority_before_dispatch(self):
        for command in self.kind_mutations():
            for fault in ['docker-replacement','directory-replacement','tools-path','metadata','late-docker']:
                with self.subTest(argv=command.argv,fault=fault):
                    fixture = self.dependency_fixture(); inputs,_,fixture_verify = fixture
                    manifests = executable_checks = 0
                    def verify(data,digest,size):
                        nonlocal manifests, executable_checks
                        result = fixture_verify(data,digest,size)
                        if digest == ACCEPTED_MANIFEST_SHA256: manifests += 1
                        else: executable_checks += 1
                        mutate = ((digest == ACCEPTED_MANIFEST_SHA256 and manifests == 2 and fault != 'late-docker')
                                  or (fault == 'late-docker' and executable_checks == 8))
                        if mutate:
                            if fault in ['docker-replacement','late-docker']:
                                path = inputs.tools/'docker'; payload = path.read_bytes()
                                path.rename(path.parent.parent/'old-docker'); path.write_bytes(payload); path.chmod(0o755)
                            elif fault == 'directory-replacement':
                                old = inputs.tools.with_name('old-bin'); inputs.tools.rename(old); inputs.tools.mkdir()
                                for name in ['docker','kind','kubectl']:
                                    (inputs.tools/name).write_bytes((old/name).read_bytes()); (inputs.tools/name).chmod(0o755)
                            elif fault == 'tools-path': object.__setattr__(inputs,'tools',inputs.tools.with_name('changed'))
                            else: inputs.tool_records['docker']['byte_size'] += 1
                        return result
                    # The late case counts the two Kind reads plus six dependency reads.
                    self.assert_dependency_rejected(fixture,command,verify)

    def test_real_harmless_kind_standin_resolves_only_fixture_child_docker(self):
        for command in self.kind_mutations():
            with self.subTest(argv=command.argv):
                inputs, colima, fixture_verify = self.dependency_fixture()
                payloads = {'kind':b'#!/bin/sh\nexec docker\n',
                            'docker':b'#!/bin/sh\nprintf "test-owned-child-docker\\n"\n'}
                for name,payload in payloads.items():
                    (inputs.tools/name).write_bytes(payload); (inputs.tools/name).chmod(0o755)
                rows = inputs.tool_records
                def verify(data,digest,size):
                    for name,payload in payloads.items():
                        if digest == rows[name]['executable_sha256'] and data == payload:
                            self.assertEqual(size,rows[name]['byte_size']); return digest
                    return fixture_verify(data,digest,size)
                with patch.dict(os.environ,{'PATH':str(colima.parent)}), patch.object(self.io,'verify_bytes',side_effect=verify):
                    result = self.io.BoundedRunner(Path.cwd(),inputs).run(command)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout_bytes,b'test-owned-child-docker\n')

    def test_marker_and_binding_drift_refuse_before_process_capture(self):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        for target in ('marker', 'binding'):
            with self.subTest(target=target):
                # One fresh run per authority; reuse only the authenticated registry.
                from kil.hf_exploratory_runtime import RuntimeAuthority
                digest = ('a' if target == 'marker' else 'b') * 64
                parent = Path(self.temp.name).resolve() / '.tools' / 'hf-exploratory-private'
                parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                store = self.io.PrivateStore(parent / ('hf-exploratory-' + digest))
                self.addCleanup(store.close)
                authority = RuntimeAuthority.create(store, digest)
                self.addCleanup(authority.close)
                adapter = ExploratoryColimaCommand(Command(('colima', 'version'), 1), authority)
                inputs, colima, verify = self.dependency_fixture()
                path = self.registry / 'registry.json' if target == 'marker' else store.path / 'runtime-binding.json'
                document = json.loads(path.read_bytes())
                document['uid'] += 1
                original = path.read_bytes()
                path.write_bytes(canonical_record(document))
                with patch.dict(os.environ, {'PATH': str(colima.parent)}), \
                        patch.object(self.io, 'verify_bytes', side_effect=verify), \
                        patch.object(self.io, 'capture_process') as capture:
                    with self.assertRaises(ValueError):
                        self.io.BoundedRunner(Path.cwd(), inputs).run(adapter)
                    capture.assert_not_called()
                path.write_bytes(original)

    def assert_dependency_rejected(self, fixture, command, verify=None):
        inputs, colima, fixture_verify = fixture
        with patch.dict(os.environ, {'PATH': str(colima.parent)}), \
                patch.object(self.io, 'verify_bytes', side_effect=verify or fixture_verify), \
                patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                self.io.BoundedRunner(Path.cwd(), inputs).run(command)
            capture.assert_not_called()

    def test_scoped_start_stop_delete_prefix_only_authenticated_tools(self):
        authority = self.runtime_authority()
        inputs, colima, verify = self.dependency_fixture()
        tail = str(colima.parent) + os.pathsep + '/inert path//tail' + os.pathsep
        for argv in (COLIMA_START_ARGV, ('colima', 'stop', '--profile', 'kil-v3-lab'),
                     ('colima', 'delete', '--profile', 'kil-v3-lab', '--force', '--data')):
            command = self.scoped_mutation(authority, argv)
            namespace = command.env
            with self.subTest(argv=argv), patch.dict(os.environ, {'PATH': tail, 'HOME': '/untrusted',
                    'EXTRA_AUTHORITY': 'no'}), patch.object(self.io, 'verify_bytes', side_effect=verify), \
                    patch.object(self.io, 'capture_process') as capture:
                parent = dict(os.environ)
                self.io.BoundedRunner(Path.cwd(), inputs).run(command)
                actual, env, _, _, _, _ = capture.call_args.args
                self.assertEqual(actual, (str(colima), *argv[1:]))
                self.assertEqual(env['PATH'], str(inputs.tools) + os.pathsep + tail)
                self.assertEqual(env['HOME'], str(self.io.passwd_home()))
                self.assertEqual(set(env) - {'PATH', 'LANG', 'LC_ALL', 'HOME'}, set(dict(namespace)))
                self.assertEqual({key: env[key] for key, _ in namespace}, dict(namespace))
                self.assertEqual(command.env, namespace)
                self.assertEqual(command.argv, argv)
                self.assertEqual(dict(os.environ), parent)

    def test_scoped_mutation_refuses_each_missing_or_substituted_dependency(self):
        authority = self.runtime_authority()
        command = self.scoped_mutation(authority)
        for name in ('docker', 'kind', 'kubectl'):
            for state in ('missing', 'substituted', 'nonexecutable', 'symlink', 'directory', 'hardlink'):
                with self.subTest(name=name, state=state):
                    fixture = self.dependency_fixture()
                    path = fixture[0].tools / name
                    if state == 'missing':
                        path.unlink()
                    elif state == 'substituted':
                        path.write_bytes(b'unaccepted executable bytes')
                    elif state == 'nonexecutable':
                        path.chmod(0o644)
                    elif state == 'symlink':
                        moved = path.parent.parent / name
                        path.rename(moved)
                        path.symlink_to(moved)
                    elif state == 'directory':
                        path.unlink()
                        path.mkdir()
                    else:
                        os.link(path, path.parent.parent / name)
                    self.assert_dependency_rejected(fixture, command)

    def test_scoped_mutation_refuses_ambiguous_tools_path(self):
        authority = self.runtime_authority()
        command = self.scoped_mutation(authority)
        for state in ('relative', 'noncanonical', 'symlink', 'separator', 'not-path'):
            with self.subTest(state=state):
                fixture = self.dependency_fixture()
                tools = fixture[0].tools
                if state == 'relative':
                    replacement = Path('relative/tools')
                elif state == 'noncanonical':
                    replacement = tools / '..' / tools.name
                elif state == 'symlink':
                    replacement = tools.parent / 'linked-bin'
                    replacement.symlink_to(tools, target_is_directory=True)
                elif state == 'separator':
                    replacement = tools.parent / ('bin' + os.pathsep + 'untrusted')
                    tools.rename(replacement)
                else:
                    replacement = str(tools)
                object.__setattr__(fixture[0], 'tools', replacement)
                self.assert_dependency_rejected(fixture, command)

    def test_scoped_mutation_refuses_extra_dependency_directory_entries(self):
        authority = self.runtime_authority()
        for name in ('colima', 'limactl', 'extra', '.hidden'):
            with self.subTest(name=name):
                fixture = self.dependency_fixture()
                (fixture[0].tools / name).write_bytes(b'never granted search priority')
                self.assert_dependency_rejected(fixture, self.scoped_mutation(authority))

    def test_scoped_mutation_refuses_unusable_original_colima(self):
        authority = self.runtime_authority()
        for state in ('missing', 'directory', 'nonexecutable', 'symlink'):
            with self.subTest(state=state):
                fixture = self.dependency_fixture()
                colima = fixture[1]
                if state == 'missing':
                    colima.unlink()
                elif state == 'directory':
                    colima.unlink()
                    colima.mkdir(mode=0o755)
                elif state == 'nonexecutable':
                    colima.chmod(0o644)
                else:
                    moved = colima.with_name('original-colima')
                    colima.rename(moved)
                    colima.symlink_to(moved)
                self.assert_dependency_rejected(fixture, self.scoped_mutation(authority))

    def test_scoped_mutation_refuses_noncanonical_original_search_path(self):
        authority = self.runtime_authority()
        inputs, colima, verify = self.dependency_fixture()
        for tail in (str(colima.parent / '..' / colima.parent.name),
                     str(colima.parent) + '//',
                     os.path.relpath(colima.parent, Path.cwd())):
            with self.subTest(tail=tail), patch.dict(os.environ, {'PATH': tail}), \
                    patch.object(self.io, 'verify_bytes', side_effect=verify), \
                    patch.object(self.io, 'capture_process') as capture:
                with self.assertRaises(ValueError):
                    self.io.BoundedRunner(Path.cwd(), inputs).run(self.scoped_mutation(authority))
                capture.assert_not_called()

    def test_scoped_dependency_drift_during_manifest_reauthentication_refuses(self):
        authority = self.runtime_authority()
        for state in ('directory', 'bytes', 'permission', 'tools-path', 'extra', 'colima-identity', 'colima-mode'):
            with self.subTest(state=state):
                fixture = self.dependency_fixture()
                inputs, colima, fixture_verify = fixture
                manifests = 0
                def verify(data, digest, size):
                    nonlocal manifests
                    result = fixture_verify(data, digest, size)
                    if digest == ACCEPTED_MANIFEST_SHA256:
                        manifests += 1
                        if manifests == 2:
                            if state == 'directory':
                                moved = inputs.tools.with_name('old-bin')
                                inputs.tools.rename(moved)
                                inputs.tools.mkdir()
                                for name in ('docker', 'kind', 'kubectl'):
                                    (inputs.tools / name).write_bytes((moved / name).read_bytes())
                                    (inputs.tools / name).chmod(0o755)
                            elif state == 'bytes':
                                (inputs.tools / 'kind').write_bytes(b'changed after authentication')
                            elif state == 'permission':
                                (inputs.tools / 'kubectl').chmod(0o744)
                            elif state == 'tools-path':
                                object.__setattr__(inputs, 'tools', inputs.tools.with_name('replacement'))
                            elif state == 'extra':
                                (inputs.tools / 'limactl').write_bytes(b'extra')
                            elif state == 'colima-identity':
                                payload = colima.read_bytes()
                                colima.rename(colima.with_name('old-colima'))
                                colima.write_bytes(payload)
                                colima.chmod(0o755)
                            else:
                                colima.chmod(0o744)
                    return result
                self.assert_dependency_rejected(fixture, self.scoped_mutation(authority), verify)
                self.assertEqual(manifests, 2)

    def test_scoped_dependency_drift_during_full_byte_verification_refuses(self):
        authority = self.runtime_authority()
        for state in ('permission', 'tools-path', 'extra', 'manifest', 'metadata'):
            with self.subTest(state=state):
                fixture = self.dependency_fixture()
                inputs, _, fixture_verify = fixture
                executable_checks = 0
                def verify(data, digest, size):
                    nonlocal executable_checks
                    result = fixture_verify(data, digest, size)
                    if digest != ACCEPTED_MANIFEST_SHA256:
                        executable_checks += 1
                        if executable_checks == 6:
                            if state == 'permission':
                                (inputs.tools / 'kubectl').chmod(0o744)
                            elif state == 'tools-path':
                                object.__setattr__(inputs, 'tools', inputs.tools.with_name('replacement'))
                            elif state == 'extra':
                                (inputs.tools / 'colima').write_bytes(b'extra')
                            elif state == 'manifest':
                                object.__setattr__(inputs, 'manifest_bytes', b'{}\n')
                            else:
                                inputs.tool_records['kind']['byte_size'] += 1
                    return result
                self.assert_dependency_rejected(fixture, self.scoped_mutation(authority), verify)
                self.assertEqual(executable_checks, 6)

    def test_readonly_and_direct_family_dispatch_do_not_gain_dependency_path(self):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        authority = self.runtime_authority()
        inputs, colima, verify = self.dependency_fixture()
        commands = [Command(('colima', 'version'), 1), Command(('colima', 'list', '--json'), 1)]
        commands += [ExploratoryColimaCommand(Command(argv, 1), authority) for argv in
            (('colima', 'version'), ('colima', 'list', '--json'), ('colima', 'status', '--profile', 'kil-v3-lab'))]
        commands += [Command((str(inputs.tools / name), *args), 1) for name, args in
            (('docker', ('--version',)), ('kind', ('version',)), ('kubectl', ('version', '--client', '-o', 'json')))]
        tail = str(colima.parent) + os.pathsep
        for command in commands:
            with self.subTest(argv=command.argv), patch.dict(os.environ, {'PATH': tail}), \
                    patch.object(self.io, 'verify_bytes', side_effect=verify), \
                    patch.object(self.io, 'capture_process') as capture:
                self.io.BoundedRunner(Path.cwd(), inputs).run(command)
                argv, env, _, _, _, _ = capture.call_args.args
                self.assertEqual(argv, command.argv)
                self.assertEqual(env['PATH'], tail)

    def test_scoped_mutation_absent_or_empty_path_has_no_empty_search_entry(self):
        authority = self.runtime_authority()
        inputs, colima, verify = self.dependency_fixture()
        for tail in (None, ''):
            with self.subTest(tail=tail), patch.dict(os.environ, {}, clear=True), \
                    patch.object(shutil, 'which', return_value=str(colima)) as finder, \
                    patch.object(self.io, 'verify_bytes', side_effect=verify), \
                    patch.object(self.io, 'capture_process') as capture:
                if tail is not None:
                    os.environ['PATH'] = tail
                parent = dict(os.environ)
                self.io.BoundedRunner(Path.cwd(), inputs).run(self.scoped_mutation(authority))
                finder.assert_called_once_with('colima', path=os.defpath if tail is None else tail)
                self.assertEqual(capture.call_args.args[0][0], str(colima))
                self.assertEqual(capture.call_args.args[1]['PATH'], str(inputs.tools))
                self.assertEqual(dict(os.environ), parent)

    def test_dependency_authentication_closes_all_opened_descriptors(self):
        authority = self.runtime_authority()
        for state in ('accepted', 'missing', 'permission', 'extra'):
            with self.subTest(state=state):
                fixture = self.dependency_fixture()
                inputs, colima, verify = fixture
                if state == 'missing':
                    (inputs.tools / 'kind').unlink()
                elif state == 'permission':
                    (inputs.tools / 'kind').chmod(0o644)
                elif state == 'extra':
                    (inputs.tools / 'colima').write_bytes(b'extra')
                descriptors = []
                real_open = os.open
                def opened(*args, **kwargs):
                    fd = real_open(*args, **kwargs)
                    descriptors.append(fd)
                    return fd
                with patch.object(self.io.os, 'open', side_effect=opened):
                    if state == 'accepted':
                        with patch.dict(os.environ, {'PATH': str(colima.parent)}), \
                                patch.object(self.io, 'verify_bytes', side_effect=verify), \
                                patch.object(self.io, 'capture_process'):
                            self.io.BoundedRunner(Path.cwd(), inputs).run(self.scoped_mutation(authority))
                    else:
                        self.assert_dependency_rejected(fixture, self.scoped_mutation(authority))
                self.assertTrue(descriptors)
                for fd in descriptors:
                    with self.assertRaises(OSError):
                        os.fstat(fd)

    def test_scoped_mutation_command_substitution_during_final_dependency_authentication_refuses(self):
        authority = self.runtime_authority()
        fixture = self.dependency_fixture()
        _, _, fixture_verify = fixture
        command = self.scoped_mutation(authority)
        checks = 0
        def verify(data, digest, size):
            nonlocal checks
            result = fixture_verify(data, digest, size)
            if digest != ACCEPTED_MANIFEST_SHA256:
                checks += 1
                if checks == 6:
                    object.__setattr__(command.command, 'argv', ('colima', 'stop', '--profile', 'kil-v3-lab'))
            return result
        self.assert_dependency_rejected(fixture, command, verify)
        self.assertEqual(checks, 6)

    def test_scoped_dependency_drift_during_first_snapshot_refuses(self):
        authority = self.runtime_authority()
        for state in ('directory', 'permission', 'tools-path', 'extra'):
            with self.subTest(state=state):
                fixture = self.dependency_fixture()
                inputs, _, fixture_verify = fixture
                checks = 0
                def verify(data, digest, size):
                    nonlocal checks
                    result = fixture_verify(data, digest, size)
                    if digest != ACCEPTED_MANIFEST_SHA256:
                        checks += 1
                        if checks == 1:
                            if state == 'directory':
                                inputs.tools.rename(inputs.tools.with_name('old-bin'))
                                inputs.tools.mkdir()
                            elif state == 'permission':
                                (inputs.tools / 'docker').chmod(0o744)
                            elif state == 'tools-path':
                                object.__setattr__(inputs, 'tools', inputs.tools.with_name('replacement'))
                            else:
                                (inputs.tools / 'limactl').write_bytes(b'extra')
                    return result
                self.assert_dependency_rejected(fixture, self.scoped_mutation(authority), verify)
                self.assertGreater(checks, 0)

    def test_scoped_mutation_rechecks_tools_path_after_last_real_runtime_guard(self):
        from kil.hf_exploratory_runtime import RuntimeAuthority
        authority = self.runtime_authority()
        fixture = self.dependency_fixture()
        inputs, _, fixture_verify = fixture
        real_guard = RuntimeAuthority.guard
        manifest_checks = 0
        final_guards = 0
        def verify(data, digest, size):
            nonlocal manifest_checks
            result = fixture_verify(data, digest, size)
            if digest == ACCEPTED_MANIFEST_SHA256:
                manifest_checks += 1
            return result
        def guard(actual):
            nonlocal final_guards
            real_guard(actual)
            if manifest_checks == 2:
                final_guards += 1
                if final_guards == 2:
                    object.__setattr__(inputs, 'tools', inputs.tools.with_name('replacement'))
        with patch.object(RuntimeAuthority, 'guard', guard):
            self.assert_dependency_rejected(fixture, self.scoped_mutation(authority), verify)
        self.assertEqual((manifest_checks, final_guards), (2, 2))

    def test_runner_accepts_scoped_colima_and_derived_environment(self):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        authority = self.runtime_authority()
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs())
        command = ExploratoryColimaCommand(Command(('colima', 'version'), 1), authority)
        with patch.object(self.io, 'capture_process') as capture:
            runner.run(command)
            env = capture.call_args.args[1]
            self.assertEqual({key: env[key] for key in dict(command.env)}, dict(command.env))
            self.assertEqual(env['HOME'], str(self.io.passwd_home()))

    def test_runner_rejects_manifest_replacement_during_authentication(self):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        authority = self.runtime_authority()
        inputs = self.accepted_inputs()
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        real_verify = self.io.verify_bytes
        def verify(data, digest, size):
            result = real_verify(data, digest, size)
            object.__setattr__(inputs, 'manifest_bytes', b'{}\n')
            return result
        with patch.object(self.io, 'verify_bytes', side_effect=verify), patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(ExploratoryColimaCommand(Command(('colima', 'version'), 1), authority))
            capture.assert_not_called()

    def test_runner_rejects_valid_command_substitution_during_authentication(self):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        authority = self.runtime_authority()
        command = Command(('colima', 'version'), 1)
        adapter = ExploratoryColimaCommand(command, authority)
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs())
        real_verify = self.io.verify_bytes
        def verify(data, digest, size):
            result = real_verify(data, digest, size)
            object.__setattr__(command, 'argv', ('colima', 'list', '--json'))
            return result
        with patch.object(self.io, 'verify_bytes', side_effect=verify), patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(adapter)
            capture.assert_not_called()

    def test_runner_rejects_metadata_change_after_executable_verification(self):
        tools = Path(self.temp.name).resolve() / '.tools' / 'bin'
        tools.mkdir(parents=True)
        payload = b'temporary executable identity fixture only'
        (tools / 'docker').write_bytes(payload)
        inputs = self.accepted_inputs(tools)
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        expected = dict(inputs.tool_records['docker'])
        real_verify = self.io.verify_bytes
        def verify(data, digest, size):
            if digest == ACCEPTED_MANIFEST_SHA256:
                return real_verify(data, digest, size)
            self.assertEqual((data, digest, size),
                             (payload, expected['executable_sha256'], expected['byte_size']))
            inputs.tool_records['kind']['byte_size'] += 1
            return digest
        with patch.object(self.io, 'verify_bytes', side_effect=verify), patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command((str(tools / 'docker'), '--version'), 1))
            capture.assert_not_called()

    def assert_final_adapter_guard_metadata_rejected(self, authority, mutate):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand, RuntimeAuthority
        inputs = self.accepted_inputs()
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        command = ExploratoryColimaCommand(Command(('colima', 'version'), 1), authority)
        real_verify = self.io.verify_bytes
        real_guard = RuntimeAuthority.guard
        manifest_checks = 0
        final_guards = 0
        changed = False

        def verify(data, digest, size):
            nonlocal manifest_checks
            result = real_verify(data, digest, size)
            if digest == ACCEPTED_MANIFEST_SHA256:
                manifest_checks += 1
            return result

        def guard(actual):
            nonlocal final_guards, changed
            real_guard(actual)
            if manifest_checks == 2:
                final_guards += 1
                # After reauthentication, the adapter validation guards first;
                # the dispatch fingerprint's env property performs the last guard.
                if final_guards == 2:
                    mutate(inputs)
                    changed = True

        with patch.object(self.io, 'verify_bytes', side_effect=verify), \
                patch.object(RuntimeAuthority, 'guard', guard), \
                patch.object(self.io, 'capture_process') as capture:
            with self.assertRaisesRegex(ValueError, 'unavailable_or_substituted_accepted_tool_authority'):
                runner.run(command)
            capture.assert_not_called()
        self.assertTrue(changed)
        self.assertEqual((manifest_checks, final_guards), (2, 2))

    def test_runner_rejects_row_drift_during_last_adapter_guard(self):
        authority = self.runtime_authority()
        def mutate(inputs):
            inputs.tool_records['kind']['version_output'] = 'substituted-after-metadata-check'
        self.assert_final_adapter_guard_metadata_rejected(authority, mutate)

    def test_runner_rejects_metadata_map_replacement_during_last_adapter_guard(self):
        authority = self.runtime_authority()
        class MetadataSubclass(dict):
            pass
        for replacement in (None, {}, {'docker': {}}, MetadataSubclass):
            with self.subTest(replacement=replacement):
                def mutate(inputs):
                    value = (MetadataSubclass(inputs.tool_records)
                             if replacement is MetadataSubclass else replacement)
                    object.__setattr__(inputs, 'tool_records', value)
                self.assert_final_adapter_guard_metadata_rejected(authority, mutate)

    def test_runner_rejects_row_shape_and_exact_type_drift_during_last_adapter_guard(self):
        authority = self.runtime_authority()
        class RowSubclass(dict):
            pass
        for drift in ('extra-key', 'missing-key', 'row-subclass', 'equal-float'):
            with self.subTest(drift=drift):
                def mutate(inputs):
                    row = inputs.tool_records['kind']
                    if drift == 'extra-key':
                        row['extra'] = 'unaccepted'
                    elif drift == 'missing-key':
                        row.pop('version_output')
                    elif drift == 'row-subclass':
                        inputs.tool_records['kind'] = RowSubclass(row)
                    else:
                        row['byte_size'] = float(row['byte_size'])
                self.assert_final_adapter_guard_metadata_rejected(authority, mutate)

    def test_runner_rechecks_executable_after_manifest_reauthentication(self):
        tools = Path(self.temp.name).resolve() / '.tools' / 'bin'
        tools.mkdir(parents=True)
        executable = tools / 'docker'
        payload = b'temporary executable identity fixture only'
        executable.write_bytes(payload)
        inputs = self.accepted_inputs(tools)
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        expected = dict(inputs.tool_records['docker'])
        real_verify = self.io.verify_bytes
        manifests = []
        def verify(data, digest, size):
            if digest == ACCEPTED_MANIFEST_SHA256:
                result = real_verify(data, digest, size)
                manifests.append(1)
                if len(manifests) == 2:
                    executable.write_bytes(b'drift after manifest reauthentication')
                return result
            self.assertEqual((digest, size), (expected['executable_sha256'], expected['byte_size']))
            if data == payload:
                return digest
            return real_verify(data, digest, size)
        with patch.object(self.io, 'verify_bytes', side_effect=verify), patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command((str(executable), '--version'), 1))
            capture.assert_not_called()

    def test_runner_rejects_manifest_substitution_during_final_executable_authentication(self):
        tools = Path(self.temp.name).resolve() / '.tools' / 'bin'
        tools.mkdir(parents=True)
        payload = b'temporary executable identity fixture only'
        (tools / 'docker').write_bytes(payload)
        inputs = self.accepted_inputs(tools)
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        expected = dict(inputs.tool_records['docker'])
        real_verify = self.io.verify_bytes
        executable_checks = []
        def verify(data, digest, size):
            if digest == ACCEPTED_MANIFEST_SHA256:
                return real_verify(data, digest, size)
            self.assertEqual((data, digest, size),
                             (payload, expected['executable_sha256'], expected['byte_size']))
            executable_checks.append(1)
            if len(executable_checks) == 2:
                object.__setattr__(inputs, 'manifest_bytes', b'{}\n')
            return digest
        with patch.object(self.io, 'verify_bytes', side_effect=verify), patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command((str(tools / 'docker'), '--version'), 1))
            capture.assert_not_called()
        self.assertEqual(len(executable_checks), 2)

    def test_runner_rejects_tools_path_substitution_during_final_executable_authentication(self):
        tools = Path(self.temp.name).resolve() / '.tools' / 'bin'
        tools.mkdir(parents=True)
        payload = b'temporary executable identity fixture only'
        (tools / 'docker').write_bytes(payload)
        replacement = tools.parent / 'replacement-bin'
        replacement.mkdir()
        (replacement / 'docker').write_bytes(payload)
        inputs = self.accepted_inputs(tools)
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        expected = dict(inputs.tool_records['docker'])
        real_verify = self.io.verify_bytes
        executable_checks = []
        def verify(data, digest, size):
            if digest == ACCEPTED_MANIFEST_SHA256:
                return real_verify(data, digest, size)
            self.assertEqual((data, digest, size),
                             (payload, expected['executable_sha256'], expected['byte_size']))
            executable_checks.append(1)
            if len(executable_checks) == 2:
                object.__setattr__(inputs, 'tools', replacement)
            return digest
        with patch.object(self.io, 'verify_bytes', side_effect=verify), patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command((str(tools / 'docker'), '--version'), 1))
            capture.assert_not_called()
        self.assertEqual(len(executable_checks), 2)

    def test_runner_rechecks_runtime_after_manifest_authentication(self):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        authority = self.runtime_authority()
        command = ExploratoryColimaCommand(Command(('colima', 'version'), 1), authority)
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs())
        real_verify = self.io.verify_bytes
        def verify(data, digest, size):
            result = real_verify(data, digest, size)
            authority.tmp.rename(authority.path / 'old-tmp')
            authority.tmp.mkdir(mode=0o700)
            return result
        with patch.object(self.io, 'verify_bytes', side_effect=verify), patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(command)
            capture.assert_not_called()

    def test_runner_scoped_homes_missing_replaced_and_symlink_refuse(self):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        authority = self.runtime_authority()
        command = ExploratoryColimaCommand(Command(('colima', 'version'), 1), authority)
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs())
        for path in (authority.path, authority.colima, authority.lima,
                     authority.docker_config, authority.tmp):
            moved = path.with_name(path.name + '-moved')
            path.rename(moved)
            try:
                for state in ('missing', 'replacement', 'symlink'):
                    with self.subTest(path=path, state=state), patch.object(self.io, 'capture_process') as capture:
                        if state == 'replacement':
                            path.mkdir(mode=0o700)
                        elif state == 'symlink':
                            path.symlink_to(moved, target_is_directory=True)
                        with self.assertRaises(ValueError):
                            runner.run(command)
                        capture.assert_not_called()
                        if state == 'replacement':
                            path.rmdir()
                        elif state == 'symlink':
                            path.unlink()
            finally:
                moved.rename(path)

    def test_runner_scoped_rejects_subclasses_and_forged_nested_commands(self):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        authority = self.runtime_authority()
        class SubCommand(Command):
            pass
        class SubAdapter(ExploratoryColimaCommand):
            pass
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs())
        with patch.object(self.io, 'capture_process') as capture:
            for bad in (SubCommand(('colima', 'version'), 1), object.__new__(SubAdapter)):
                with self.assertRaises(ValueError):
                    runner.run(bad)
            command = Command(('colima', 'version'), 1)
            adapter = ExploratoryColimaCommand(command, authority)
            for field, bad in [('argv', ('colima', 'start', '--profile', 'foreign')),
                               ('timeout_s', True), ('mutating', True), ('stdin', b'bad'),
                               ('env', (('COLIMA_HOME', '/foreign'),))]:
                original = getattr(command, field)
                object.__setattr__(command, field, bad)
                try:
                    with self.assertRaises(ValueError):
                        runner.run(adapter)
                finally:
                    object.__setattr__(command, field, original)
            object.__setattr__(adapter, 'command', SubCommand(('colima', 'version'), 1))
            with self.assertRaises(ValueError):
                runner.run(adapter)
            capture.assert_not_called()

    def test_runner_plain_colima_is_global_version_list_only_without_environment(self):
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs())
        private_env = (('DOCKER_CONFIG', '/private/tmp/test/docker-config'),
                       ('TMPDIR', '/private/tmp/test/runtime-tmp'))
        with patch.object(self.io, 'capture_process') as capture:
            for argv, mutating, env in [(('colima', 'status', '--profile', 'kil-v3-lab'), False, ()),
                                        (('colima', 'version'), False, private_env),
                                        (('colima', 'stop', '--profile', 'kil-v3-lab'), True, private_env)]:
                with self.subTest(argv=argv, env=env), self.assertRaises(ValueError):
                    runner.run(Command(argv, 1, env=env, mutating=mutating))
            capture.assert_not_called()
            for argv in (('colima', 'version'), ('colima', 'list', '--json')):
                runner.run(Command(argv, 1))
                env = capture.call_args.args[1]
                for key in ('COLIMA_HOME', 'LIMA_HOME', 'DOCKER_CONFIG', 'DOCKER_HOST', 'TMPDIR'):
                    self.assertNotIn(key, env)

    def test_runner_scoped_sanitizes_inherited_overrides_and_other_families_stay_closed(self):
        from kil.hf_exploratory_runtime import ExploratoryColimaCommand
        authority = self.runtime_authority()
        adapter = ExploratoryColimaCommand(Command(('colima', 'version'), 1), authority)
        overrides = {key: '/untrusted' for key in ('HOME', 'COLIMA_HOME', 'LIMA_HOME', 'DOCKER_HOST',
                     'DOCKER_CONFIG', 'TMPDIR', 'XDG_CONFIG_HOME', 'COLIMA_PROFILE', 'LIMA_INSTANCE')}
        with patch.dict(os.environ, overrides), patch.object(self.io, 'capture_process') as capture:
            self.io.BoundedRunner(Path.cwd(), self.accepted_inputs()).run(adapter)
            env = capture.call_args.args[1]
            self.assertEqual(set(env) - {'PATH', 'LANG', 'LC_ALL', 'HOME'}, set(dict(adapter.env)))
            self.assertEqual(env['HOME'], str(self.io.passwd_home()))
            self.assertEqual({key: env[key] for key in dict(adapter.env)}, dict(adapter.env))
        with self.assertRaises(ValueError):
            ExploratoryColimaCommand(Command(('docker', 'context', 'show'), 1), authority)
        with self.assertRaises(ValueError):
            Command(('colima', 'version'), 1, env=tuple(sorted(adapter.env)))

    def test_intent_precedes_action_and_no_repeat(self):
        store = self.store()
        calls = []
        def action():
            self.assertIn(b'request_intent', store.journal.read_bytes())
            calls.append(1)
            return terminal(TRACKS[0])
        self.assertEqual(store.send_once(TRACKS[0], b'instruction\n', action)['status'], 'complete')
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[0], b'instruction\n', action)
        self.assertEqual(calls, [1])

    def test_callback_failure_blocks_next_track(self):
        store = self.store()
        def fail():
            raise RuntimeError('uncertain')
        with self.assertRaises(RuntimeError):
            store.send_once(TRACKS[0], b'instruction\n', fail)
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[1], b'instruction\n', lambda: self.fail('called'))

    def test_private_path_and_exclusive_creation(self):
        store = self.store()
        with self.assertRaises(ValueError):
            store.write('../escape', b'x')
        with self.assertRaises(FileExistsError):
            self.io.PrivateStore(store.path)

    def test_capture_limits_and_timeout(self):
        result = self.io.capture_process((sys.executable, '-c', 'import sys;sys.stdout.write("x"*10000)'),
            {'PATH': os.environ['PATH']}, None, 5, 64, Path.cwd())
        self.assertEqual(result.returncode, -1001)
        self.assertLessEqual(len(result.stdout_bytes) + len(result.stderr_bytes), 64)
        result = self.io.capture_process((sys.executable, '-c', 'import time;time.sleep(5)'),
            {'PATH': os.environ['PATH']}, None, 1, 64, Path.cwd())
        self.assertEqual(result.returncode, -1000)

    def test_closed_store_rejects_writes(self):
        store = self.store()
        store.close()
        with self.assertRaises(ValueError):
            store.write('late', b'x')
        with self.assertRaises(ValueError):
            store.record('late', {})

    def test_capture_rejects_invalid_bounds(self):
        with self.assertRaises(ValueError):
            self.io.capture_process((sys.executable,), {}, None, 0, -1, Path.cwd())

    def test_runner_validates_before_capture(self):
        self.assertTrue(hasattr(self.io, 'BoundedRunner'))
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs())
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(object())
            command = Command(('docker', 'context', 'show'), 1)
            object.__setattr__(command, 'argv', ('sh', '-c', 'bad'))
            with self.assertRaises(ValueError):
                runner.run(command)
            capture.assert_not_called()

    def test_runner_rejects_executable_drift(self):
        self.assertTrue(hasattr(self.io, 'BoundedRunner'))
        tools = Path(self.temp.name).resolve() / '.tools' / 'bin'
        tools.mkdir(parents=True)
        executable = tools / 'docker'
        executable.write_bytes(b'drift')
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs(tools))
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command((str(executable), '--version'), 1))
            capture.assert_not_called()

    def test_store_rejects_parent_reanchor(self):
        store = self.store()
        moved = store.path.with_name('moved')
        store.path.rename(moved)
        store.path.symlink_to(moved, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            store.write('reanchor', b'x')
        self.assertFalse((moved / 'reanchor').exists())

    def test_malformed_terminal_keeps_uncertainty(self):
        store = self.store()
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[0], b'instruction\n', lambda: b'not-json\n')
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[1], b'instruction\n', lambda: self.fail('called'))

    def test_missing_lf_terminal_latches_uncertainty(self):
        store = self.store()
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[0], b'instruction\n', lambda: terminal(TRACKS[0])[:-1])
        self.assertTrue(store.uncertain)
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[1], b'instruction\n', lambda: self.fail('called'))

    def test_crlf_terminal_latches_uncertainty(self):
        store = self.store()
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[0], b'instruction\n', lambda: terminal(TRACKS[0])[:-1] + b'\r\n')
        self.assertTrue(store.uncertain)
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[1], b'instruction\n', lambda: self.fail('called'))

    def test_runner_rejects_mutable_matching_digest_override(self):
        inputs = self.accepted_inputs()
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        payload = b'test-owned replacement, never executed'
        (inputs.tools / 'docker').write_bytes(payload)
        inputs.tool_records['docker']['executable_sha256'] = sha256(payload).hexdigest()
        inputs.tool_records['docker']['byte_size'] = len(payload)
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command(('docker', 'context', 'show'), 1))
            capture.assert_not_called()

    def test_runner_rejects_missing_records_before_path_fallback(self):
        inputs = self.accepted_inputs()
        inputs.tool_records.clear()
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command(('docker', 'context', 'show'), 1))
            capture.assert_not_called()

    def test_runner_rejects_substituted_manifest(self):
        inputs = self.accepted_inputs()
        object.__setattr__(inputs, 'manifest_bytes', b'{}\n')
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command(('colima', 'version'), 1))
            capture.assert_not_called()

    def test_runner_rejects_missing_or_malformed_authority(self):
        for metadata in (None, [], {'docker': {}}, {'docker': 'malformed'}):
            with self.subTest(metadata=metadata):
                inputs = self.accepted_inputs()
                object.__setattr__(inputs, 'tool_records', metadata)
                runner = self.io.BoundedRunner(Path.cwd(), inputs)
                with patch.object(self.io, 'capture_process') as capture:
                    with self.assertRaises(ValueError):
                        runner.run(Command(('docker', 'context', 'show'), 1))
                    capture.assert_not_called()

    def test_runner_reauthenticates_manifest_after_construction(self):
        inputs = self.accepted_inputs()
        runner = self.io.BoundedRunner(Path.cwd(), inputs)
        object.__setattr__(inputs, 'manifest_bytes', inputs.manifest_bytes + b' ')
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command(('docker', 'context', 'show'), 1))
            capture.assert_not_called()

    def test_intent_fsync_failure_prevents_action(self):
        store = self.store()
        with patch.object(self.io.os, 'fsync', side_effect=[None, None, OSError('intent disk')]):
            with self.assertRaises(OSError):
                store.send_once(TRACKS[0], b'instruction\n', lambda: self.fail('called'))
        self.assertTrue(store.uncertain)

    def test_streaming_stdin_and_empty_eof(self):
        for payload in (b'', b'payload' * 20000):
            result = self.io.capture_process((sys.executable, '-c', 'import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())'),
                {'PATH': os.environ['PATH']}, payload, 5, 200000, Path.cwd())
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout_bytes, payload)

    def test_three_tracks_and_no_fourth(self):
        store = self.store()
        for track in TRACKS:
            store.send_once(track, b'instruction\n', lambda track=track: terminal(track))
        with self.assertRaises(ValueError):
            store.send_once(TRACKS[0], b'instruction\n', lambda: self.fail('called'))

    def test_constructor_failure_closes_lock(self):
        descriptors = []
        real_open = self.io.os.open
        def opened(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            descriptors.append(fd)
            return fd
        with patch.object(self.io.os, 'open', side_effect=opened), patch.object(self.io.os, 'fsync', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                self.io.PrivateStore(Path(self.temp.name).resolve() / 'run')
        for fd in descriptors:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_runner_sanitizes_environment_and_version_read(self):
        tools = Path(self.temp.name).resolve() / '.tools' / 'bin'
        tools.mkdir(parents=True)
        payload = b'test-owned identity only'
        (tools / 'docker').write_bytes(payload)
        inputs = self.accepted_inputs(tools)
        real_verify = self.io.verify_bytes
        def dispatch_only_verify(data, digest, size):
            # Manifest authority uses the real check; only dummy binary IO is isolated.
            if digest == ACCEPTED_MANIFEST_SHA256:
                return real_verify(data, digest, size)
            self.assertEqual(data, payload)
            self.assertEqual(digest, inputs.tool_records['docker']['executable_sha256'])
            self.assertEqual(size, inputs.tool_records['docker']['byte_size'])
            return digest
        with patch.dict(os.environ, {'DOCKER_CONFIG': '/global-config', 'HOME': '/untrusted', 'EXTRA_AUTHORITY': 'no'}):
            runner = self.io.BoundedRunner(Path.cwd(), inputs)
            with patch.object(self.io, 'verify_bytes', side_effect=dispatch_only_verify), patch.object(self.io, 'capture_process') as capture:
                runner.run(Command((str(tools / 'docker'), '--version'), 1))
                argv, env, _, _, _, _ = capture.call_args.args
                self.assertEqual(argv[0], str(tools / 'docker'))
                self.assertNotIn('DOCKER_CONFIG', env)
                self.assertNotIn('TMPDIR', env)
                self.assertNotIn('EXTRA_AUTHORITY', env)
                self.assertEqual(env['HOME'], str(self.io.passwd_home()))
                runner.run(Command(('docker', 'context', 'show'), 1))
                self.assertEqual(capture.call_args.args[1]['DOCKER_CONFIG'], '/global-config')

    def test_runner_requires_colima_private_environment(self):
        runner = self.io.BoundedRunner(Path.cwd(), self.accepted_inputs())
        with patch.object(self.io, 'capture_process') as capture:
            with self.assertRaises(ValueError):
                runner.run(Command(('colima', 'stop', '--profile', 'kil-v3-lab'), 1, mutating=True))
            capture.assert_not_called()

    def test_capture_aggregate_output_and_nonzero_exit(self):
        result = self.io.capture_process((sys.executable, '-c', 'import sys;sys.stdout.write("x"*40);sys.stdout.flush();sys.stderr.write("y"*40)'),
            {}, None, 5, 64, Path.cwd())
        self.assertEqual(result.returncode, -1001)
        self.assertEqual(len(result.stdout_bytes) + len(result.stderr_bytes), 64)
        result = self.io.capture_process((sys.executable, '-c', 'import sys;sys.exit(7)'),
            {}, b'x' * 200000, 5, 64, Path.cwd())
        self.assertEqual(result.returncode, 7)

    def test_capture_wait_is_bounded_after_output_eof(self):
        result = self.io.capture_process((sys.executable, '-c', 'import os,time;os.close(1);os.close(2);time.sleep(5)'),
            {}, None, 1, 64, Path.cwd())
        self.assertEqual(result.returncode, -1000)

    def test_private_permissions_symlinks_and_quotas(self):
        store = self.store()
        self.assertEqual(store.path.stat().st_mode & 0o777, 0o700)
        store.write('small', b'x')
        self.assertEqual((store.path / 'small').stat().st_mode & 0o777, 0o600)
        (store.path / 'linked').symlink_to(store.path / 'small')
        with self.assertRaises(FileExistsError):
            store.write('linked', b'bad')
        self.assertEqual((store.path / 'small').read_bytes(), b'x')
        with self.assertRaises(ValueError):
            store.write('large', b'x' * (self.io.MAX_OUTPUT_BYTES + 1))
        store.total = self.io.MAX_PRIVATE_TOTAL_BYTES
        with self.assertRaises(ValueError):
            store.write('quota', b'x')
        with self.assertRaises(ValueError):
            store.record('quota', {})

    def test_containing_parent_is_synced_before_action(self):
        parent = Path(self.temp.name).resolve()
        identity = lambda row: (row.st_dev, row.st_ino)
        expected = identity(parent.stat())
        synced = []
        real_sync = os.fsync
        def sync(fd):
            synced.append(identity(os.fstat(fd)))
            real_sync(fd)
        with patch.object(self.io.os, 'fsync', side_effect=sync):
            store = self.store()
            def action():
                self.assertIn(expected, synced)
                return terminal(TRACKS[0])
            store.send_once(TRACKS[0], b'instruction\n', action)

    def test_parent_sync_failure_closes_constructor_resources(self):
        parent = Path(self.temp.name).resolve()
        expected = (parent.stat().st_dev, parent.stat().st_ino)
        descriptors = []
        real_open, real_sync = os.open, os.fsync
        def opened(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            descriptors.append(fd)
            return fd
        def sync(fd):
            row = os.fstat(fd)
            if (row.st_dev, row.st_ino) == expected:
                raise OSError('parent persistence')
            real_sync(fd)
        with patch.object(self.io.os, 'open', side_effect=opened), patch.object(self.io.os, 'fsync', side_effect=sync):
            with self.assertRaises(OSError):
                store = self.io.PrivateStore(parent / 'run')
                self.addCleanup(store.close)
        for fd in descriptors:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_failed_file_persistence_reserves_quota(self):
        store = self.store()
        base = store.total
        with patch.object(self.io, 'MAX_PRIVATE_TOTAL_BYTES', base + 8):
            with patch.object(self.io.os, 'fsync', side_effect=OSError('disk')):
                with self.assertRaises(OSError):
                    store.write('failed', b'12345')
            self.assertEqual((store.path / 'failed').read_bytes(), b'12345')
            with self.assertRaises(ValueError):
                store.write('later', b'12345')
            self.assertEqual(store.total, base + 5)

    def test_failed_journal_persistence_reserves_quota(self):
        store = self.store()
        base = store.total
        payload = self.io.canonical({'event': 'failed', 'details': {}})
        with patch.object(self.io, 'MAX_PRIVATE_TOTAL_BYTES', base + len(payload) + 1):
            with patch.object(self.io.os, 'fsync', side_effect=OSError('disk')):
                with self.assertRaises(OSError):
                    store.record('failed', {})
            self.assertTrue(store.journal.read_bytes().endswith(payload))
            with self.assertRaises(ValueError):
                store.record('later', {})
            self.assertEqual(store.total, base + len(payload))

    def test_selector_failure_prevents_process_acquisition(self):
        with patch.object(self.io.selectors, 'DefaultSelector', side_effect=OSError('selector')), patch.object(self.io.subprocess, 'Popen') as spawn:
            with self.assertRaises(OSError):
                self.io.capture_process((sys.executable, '-c', 'pass'), {}, None, 1, 64, Path.cwd())
            spawn.assert_not_called()

    def test_spawn_failure_closes_selector(self):
        selector = self.io.selectors.DefaultSelector()
        self.addCleanup(selector.close)
        with patch.object(self.io.selectors, 'DefaultSelector', return_value=selector), patch.object(self.io.subprocess, 'Popen', side_effect=OSError('spawn')):
            with self.assertRaises(OSError):
                self.io.capture_process((sys.executable, '-c', 'pass'), {}, None, 1, 64, Path.cwd())
        self.assertIsNone(selector.get_map())

    def test_partial_journal_failure_reserves_full_payload(self):
        store = self.store()
        base = store.total
        before = store.journal.read_bytes()
        payload = self.io.canonical({'event': 'partial', 'details': {}})
        real_write = os.write
        calls = []
        def partial(fd, view):
            if calls:
                raise OSError('partial append')
            calls.append(1)
            return real_write(fd, view[:5])
        with patch.object(self.io, 'MAX_PRIVATE_TOTAL_BYTES', base + len(payload)):
            with patch.object(self.io.os, 'write', side_effect=partial):
                with self.assertRaises(OSError):
                    store.record('partial', {})
            self.assertEqual(store.journal.read_bytes(), before + payload[:5])
            self.assertEqual(store.total, base + len(payload))
            with self.assertRaises(ValueError):
                store.write('later', b'x')

    def test_successful_totals_equal_persisted_bytes(self):
        store = self.store()
        store.send_once(TRACKS[0], b'instruction\n', lambda: terminal(TRACKS[0]))
        self.assertEqual(store.total, sum(path.stat().st_size for path in store.path.iterdir()))
