"""Fresh test-owned generated controls; no SSH or native dispatch."""
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from kil.hf_exploratory_io import PrivateStore
from kil.hf_exploratory_runtime import RuntimeAuthority


def generated_pair(runtime, port=54321):
    body = ('# This SSH config file can be passed to \'ssh -F\'.\n'
            '# This file is created by Lima, but not used by Lima itself currently.\n'
            '# Modifications to this file will be lost on restarting the Lima instance.\n'
            'Host lima-colima-kil-v3-lab\n'
            f'  IdentityFile "{runtime.lima / "_config/user"}"\n'
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
            f'  ControlPath "{runtime.lima / "colima-kil-v3-lab/ssh.sock"}"\n'
            '  ControlPersist yes\n'
            '  Hostname 127.0.0.1\n'
            f'  Port {port}\n').encode()
    return body.replace(b'Host lima-colima-', b'Host colima-') + b'\n', body


def write_pair(runtime, port=54321):
    colima, instance = generated_pair(runtime, port)
    target = runtime.lima / 'colima-kil-v3-lab'
    target.mkdir(exist_ok=True)
    (runtime.colima/'ssh_config').write_bytes(colima)
    (runtime.colima/'ssh_config').chmod(0o644)
    (target/'ssh.config').write_bytes(instance)
    (target/'ssh.config').chmod(0o600)


class SSHTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='k', dir='/private/tmp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        private = self.root/'.tools/hf-exploratory-private'
        private.mkdir(parents=True, mode=0o700)
        self.store = PrivateStore(private/('hf-exploratory-'+'1'*64))
        self.addCleanup(self.store.close)
        selector = patch('kil.hf_exploratory_runtime._registry_parent', return_value=self.root/'k')
        selector.start(); self.addCleanup(selector.stop)
        self.runtime = RuntimeAuthority.create(self.store, '1'*64)
        self.addCleanup(self.runtime.close)

    def controls(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_ssh'), 'generated SSH control validator is missing')
        result = importlib.import_module('kil.hf_exploratory_ssh').SSHControls(self.runtime)
        self.addCleanup(result.close)
        return result

    @property
    def colima(self): return self.runtime.colima/'ssh_config'
    @property
    def instance(self): return self.runtime.lima/'colima-kil-v3-lab/ssh.config'

    def bound(self):
        controls = self.controls(); controls.require_absent(); write_pair(self.runtime)
        controls.bind_running(); return controls

    def test_valid_pair_retains_raw_bytes_full_metadata_and_port(self):
        controls = self.bound(); controls.guard()
        proof = controls.proof()
        self.assertEqual(proof['state'], 'running')
        self.assertEqual(proof['port'], 54321)
        for key, path in [('colima', self.colima), ('instance', self.instance)]:
            self.assertTrue(proof[key]['present'])
            self.assertEqual(bytes.fromhex(proof[key]['hex']), path.read_bytes())
            self.assertEqual(set(proof[key]['identity']), {'device','inode','mode','uid','nlink','size','mtime_ns','ctime_ns'})

    def test_prestart_presence_is_never_adopted(self):
        controls = self.controls(); write_pair(self.runtime)
        with self.assertRaises(ValueError): controls.require_absent()

    def test_entire_grammar_pair_and_current_runtime_paths_are_required(self):
        write_pair(self.runtime)
        original = self.colima.read_bytes()
        mutations = [original+b'Include other\n', original.replace(b'Host colima-',b'Host * #'),
            original.replace(b'127.0.0.1',b'127.0.0.2'), original.replace(b'User mistorm', b'User another'),
            original.replace(b'Port 54321',b'Port 054321'), original.replace(b'Port 54321',b'Port 0'),
            original.replace(b'Port 54321',b'Port 65536'), original.replace(b'Port 54321',b'Port 54322'),
            original.replace(str(self.runtime.path).encode(), b'/other/runtime'),
            original.replace(b'  BatchMode yes\n',b''), original.replace(b'  Compression no',b' Compression no'),
            original.replace(b'# This SSH',b'# Other SSH'), original[:-1], original+b'\n']
        for payload in mutations:
            with self.subTest(payload=payload):
                self.colima.write_bytes(payload)
                controls = self.controls()
                with self.assertRaises(ValueError): controls.bind_running()
                controls.close()
        self.colima.write_bytes(original); controls = self.controls(); controls.bind_running(); controls.guard()

    def test_bad_file_mode_link_type_size_and_uid_refuse(self):
        for fault in ['mode','instance_mode','hardlink','symlink','fifo','directory','size','uid']:
            with self.subTest(fault=fault):
                write_pair(self.runtime); controls = self.controls()
                if fault == 'mode': self.colima.chmod(0o600)
                elif fault == 'instance_mode': self.instance.chmod(0o644)
                elif fault == 'hardlink': os.link(self.colima,self.root/'link')
                elif fault in ('symlink','fifo','directory'):
                    self.colima.unlink()
                    if fault == 'symlink': self.colima.symlink_to(self.instance)
                    elif fault == 'fifo': os.mkfifo(self.colima)
                    else: self.colima.mkdir()
                elif fault == 'size': self.colima.write_bytes(b'x'*16385)
                context = patch('kil.hf_exploratory_ssh.os.geteuid', return_value=os.geteuid()+1) if fault == 'uid' else patch('builtins.id', wraps=id)
                with context, self.assertRaises(ValueError): controls.bind_running()
                controls.close()
                if self.colima.is_dir(): self.colima.rmdir()
                else: self.colima.unlink()
                if (self.root/'link').exists(): (self.root/'link').unlink()

    def test_foreign_file_owner_refuses_both_controls_with_effective_uid_unchanged(self):
        effective_uid = os.geteuid()
        for target in ['colima','instance']:
            with self.subTest(target=target):
                controls = self.controls(); write_pair(self.runtime)
                expected = getattr(self,target).stat()
                original = os.fstat; hits = []
                def foreign_owner(fd):
                    row = original(fd)
                    if (row.st_dev,row.st_ino) != (expected.st_dev,expected.st_ino):
                        return row
                    hits.append(fd)
                    class ForeignOwnerRow:
                        def __getattr__(self,key):
                            return row.st_uid + 1 if key == 'st_uid' else getattr(row,key)
                    return ForeignOwnerRow()
                with patch('kil.hf_exploratory_ssh.os.fstat',side_effect=foreign_owner):
                    self.assertEqual(os.geteuid(),effective_uid)
                    with self.assertRaises(ValueError): controls.bind_running()
                self.assertTrue(hits,'must authenticate the actual generated file owner')
                self.assertEqual(os.geteuid(),effective_uid)
                self.assertEqual(controls.state,'refused')
                self.assertEqual(controls._owned,[])
                controls.close()

    def test_running_same_size_edit_replacement_absence_and_ancestor_refuse(self):
        controls = self.bound(); original = self.colima.read_bytes()
        self.colima.write_bytes(original.replace(b'54321',b'54322'))
        with self.assertRaises(ValueError): controls.guard()
        controls.close(); write_pair(self.runtime); controls = self.controls(); controls.bind_running()
        self.colima.unlink(); self.colima.write_bytes(original); self.colima.chmod(0o644)
        with self.assertRaises(ValueError): controls.guard()
        controls.close(); write_pair(self.runtime); controls = self.controls(); controls.bind_running()
        self.instance.parent.rename(self.instance.parent.with_name('old'))
        self.instance.parent.mkdir()
        with self.assertRaises(ValueError): controls.guard()

    def test_late_first_file_edit_during_pair_read_is_refused(self):
        controls = self.bound(); original = controls._check
        def checking(control):
            original(control)
            if control is controls.instance:
                self.colima.write_bytes(self.colima.read_bytes().replace(b'54321',b'54322'))
        with patch.object(controls,'_check',side_effect=checking), self.assertRaises(ValueError): controls.guard()

    def test_close_attempts_all_descriptors_after_one_close_error(self):
        controls = self.bound(); descriptors = list(controls._owned); real_close = os.close
        def closing(fd):
            real_close(fd)
            if fd == descriptors[-1]: raise OSError('late close failure')
        with patch('kil.hf_exploratory_ssh.os.close',side_effect=closing) as calls:
            with self.assertRaises(OSError): controls.close()
        self.assertEqual(set(descriptors), {call.args[0] for call in calls.call_args_list})
        self.assertEqual(controls._owned,[])

    def test_deleted_held_instance_hardlink_is_not_absence(self):
        controls = self.bound(); self.colima.write_bytes(b''); controls.begin_stopped(); controls.finish_stopped()
        os.link(self.instance,self.root/'surviving-instance')
        self.instance.unlink(); self.instance.parent.rmdir()
        with self.assertRaises(ValueError): controls.begin_deleted()

    def test_ambiguous_derived_paths_are_never_accepted(self):
        from kil.hf_exploratory_ssh import SSHControls
        for char in ['"', '\\', '\n', '\r', '\x01']:
            with self.subTest(char=char):
                digest = str(ord(char)).zfill(64)
                store = PrivateStore(self.store.path.parent/('hf-exploratory-'+digest))
                self.addCleanup(store.close)
                with patch('kil.hf_exploratory_runtime._registry_parent',return_value=self.root/('k'+char)):
                    authority = RuntimeAuthority.create(store,digest)
                    self.addCleanup(authority.close)
                    with self.assertRaises(ValueError): SSHControls(authority)

    def test_failed_stop_candidate_closure_closes_candidate_and_poisoned_state(self):
        controls = self.bound(); self.colima.write_bytes(b''); count = len(controls._owned)
        original = controls._check; calls = []
        def checking(control):
            calls.append(control)
            if len(calls) == 2: raise OSError('late candidate closure failure')
            return original(control)
        with patch.object(controls,'_check',side_effect=checking), self.assertRaises(ValueError): controls.begin_stopped()
        self.assertEqual(len(controls._owned),count)
        with self.assertRaises(ValueError): controls.guard()
        with self.assertRaises(ValueError): controls.begin_stopped()

    def test_deleted_renamed_empty_instance_directory_is_not_absence(self):
        controls = self.bound(); self.colima.write_bytes(b''); controls.begin_stopped(); controls.finish_stopped()
        self.instance.unlink(); self.instance.parent.rename(self.root/'surviving-directory')
        with self.assertRaises(ValueError): controls.begin_deleted()

    def test_partial_bind_close_failure_attempts_all_and_permanently_refuses(self):
        controls = self.controls(); write_pair(self.runtime); self.instance.unlink()
        import kil.hf_exploratory_ssh as module
        opened, attempted = [], []; real_open, real_close = os.open, os.close
        def opening(*args, **kwargs):
            fd = real_open(*args, **kwargs); opened.append(fd); return fd
        def closing(fd):
            attempted.append(fd); real_close(fd)
            if len(attempted) == 1: raise OSError('test-owned partial-bind close failure')
        try:
            with patch.object(module.os,'open',side_effect=opening), patch.object(module.os,'close',side_effect=closing):
                with self.assertRaises((ValueError,OSError)): controls.begin_running()
            observed_state = controls.state; retained = list(controls._owned)
        finally:
            for fd in list(controls._owned):
                try: real_close(fd)
                except OSError: pass
            controls._owned.clear()
        self.assertEqual(set(opened),set(attempted))
        self.assertEqual(retained,[])
        self.assertEqual(observed_state,'refused')

    def test_deleted_directory_drift_during_final_anchor_read_is_refused(self):
        controls = self.bound(); self.colima.write_bytes(b''); controls.begin_stopped(); controls.finish_stopped()
        self.instance.unlink(); self.instance.parent.rmdir(); controls.begin_deleted(); controls.finish_deleted()
        original = controls._anchors; calls = []
        def anchoring(**kwargs):
            original(**kwargs); calls.append(True)
            if len(calls) == 2: os.fchmod(controls.instance_anchor[0],0o711)
        with patch.object(controls,'_anchors',side_effect=anchoring), self.assertRaises(ValueError): controls.guard()

    def test_partial_open_failure_closes_retained_descriptors(self):
        controls = self.controls(); write_pair(self.runtime); self.instance.unlink()
        import kil.hf_exploratory_ssh as module
        opened = []; real_open = os.open; real_close = os.close
        def opening(*args, **kwargs):
            fd = real_open(*args, **kwargs); opened.append(fd); return fd
        with patch.object(module.os,'open',side_effect=opening), patch.object(module.os,'close',wraps=real_close) as closing:
            with self.assertRaises(ValueError): controls.bind_running()
        self.assertEqual(set(opened), {call.args[0] for call in closing.call_args_list})

    def test_stop_transition_empty_absent_unchanged_and_immutable_proof(self):
        for form in ['empty','absent','unchanged','replacement']:
            with self.subTest(form=form):
                controls = self.controls(); write_pair(self.runtime); controls.bind_running()
                if form == 'empty': self.colima.write_bytes(b'')
                elif form == 'absent': self.colima.unlink()
                elif form == 'replacement':
                    self.colima.unlink(); self.colima.write_bytes(b''); self.colima.chmod(0o644)
                controls.begin_stopped(); controls.guard(); controls.finish_stopped(); controls.guard()
                proof = controls.proof()['colima']
                self.assertEqual(proof['present'], form != 'absent')
                if form in ('empty','replacement'): self.assertEqual(proof['hex'],'')
                if form != 'absent':
                    payload = self.colima.read_bytes(); self.colima.unlink(); self.colima.write_bytes(payload); self.colima.chmod(0o644)
                else: self.colima.write_bytes(b''); self.colima.chmod(0o644)
                with self.assertRaises(ValueError): controls.guard()
                controls.close()

    def test_stopped_arbitrary_content_or_instance_changes_refuse(self):
        controls = self.bound(); self.colima.write_bytes(b'other')
        with self.assertRaises(ValueError): controls.begin_stopped()
        controls.close(); write_pair(self.runtime); controls = self.controls(); controls.bind_running()
        self.colima.write_bytes(b''); self.instance.write_bytes(self.instance.read_bytes().replace(b'54321',b'54322'))
        with self.assertRaises(ValueError): controls.begin_stopped()

    def test_deleted_native_colima_removal_requires_unchanged_unlinked_descriptor(self):
        controls = self.bound(); self.colima.write_bytes(b''); controls.begin_stopped(); controls.finish_stopped()
        self.instance.unlink(); self.instance.parent.rmdir(); self.colima.unlink()
        controls.begin_deleted(); controls.finish_deleted(); controls.guard()
        self.assertFalse(controls.proof()['colima']['present'])
        self.assertFalse(controls.proof()['instance']['present'])

    def test_deleted_requires_instance_absence_and_no_colima_replacement(self):
        controls = self.bound(); self.colima.write_bytes(b''); controls.begin_stopped(); controls.finish_stopped()
        self.instance.unlink(); self.instance.parent.rmdir()
        controls.begin_deleted(); controls.guard(); controls.finish_deleted(); controls.guard()
        self.assertFalse(controls.proof()['instance']['present'])
        self.colima.unlink(); self.colima.write_bytes(b''); self.colima.chmod(0o644)
        with self.assertRaises(ValueError): controls.guard()
