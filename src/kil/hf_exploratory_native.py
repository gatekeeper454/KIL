"""Separate, conservative HF rehearsal/action integration; not V3B2 acceptance.

Only closed commands are dispatched. Every mutation is a durable one-shot
attempt, and deletion requires freshly rebound exact owned resources. Raw
private observations are retained; no publication or strict controller is used.
"""
from contextlib import ExitStack
from dataclasses import asdict, replace
from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path
import platform
import re
import stat
import time

from kil import hf_exploratory_case as case
from kil.hf_exploratory_inputs import read_regular, verify_bytes, TOOL_VERSION_ARGUMENTS
from kil.hf_exploratory_io import capture_process
from kil.hf_exploratory_runtime import RuntimeAuthority, ExploratoryColimaCommand, ExploratoryEnvoyPlatformCommand, ExploratoryNodeAliasCommand
from kil.hf_exploratory_ssh import SSHControls
from kil.hf_exploratory_profile import ProfilePaths, creation_binding, unchanged, absent
from kil.hf_exploratory_evidence import snapshot_runtime, observe_runtime_leftovers
from kil.v3b2_accepted_images import ACCEPTED_IMAGES
from kil.v3b2_colima_inventory import capture_roster, decode_inventory, require_complete
from kil.v3b2_contracts import TRACKS, TRACK_NAMESPACES
from kil.v3b2_journal import (
    Command, OwnedIdentity, colima_start_command, docker_context_command,
    kind_create_command, kind_delete_command, kind_load_command,
    docker_image_import_commands, kubectl_apply_command, kubectl_apply_calico_command,
    kubectl_attach_command, kubectl_driver_pod_command, kubectl_source_pod_command,
    kubectl_source_read_command, kubectl_ready_endpoint_command,
    kubectl_calico_workload_command, kubectl_workload_ready_command,
    kubectl_envoy_quiesce_commands,
)
from kil.v3b2_profile_state import (
    ProfilePaths as StrictProfilePaths, require_pristine, capture,
    passwd_home, _parent, _read,
)
from kil.v3b2_proofs import canonical, decode, CLUSTER_INVENTORY_ARGV, ACTIVE_GAUGES
from kil.v3b2_manifests import render_kind_config, render_objects

ROLES = ('driver', 'authz', 'envoy', 'target')
NAMESPACES = dict(TRACK_NAMESPACES)
INCARNATION_KEYS = ('namespace', 'pod', 'role', 'uid', 'container_id',
                    'requested_image', 'runtime_image', 'image_ref')


class ReadPending(ValueError):
    """An authenticated, valid known not-ready observation; retry only this."""


class SetupReadinessBudget:
    """One elapsed-time and read-attempt budget for all setup readiness phases."""
    def __init__(self):
        self.deadline = time.monotonic()+300
        self.attempts = 0


def bind_node(rows):
    try:
        if (type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict
                or type(rows[0]['Id']) is not str or re.fullmatch(r'[0-9a-f]{64}', rows[0]['Id']) is None
                or rows[0]['Name'] != '/kil-v3-lab-control-plane'
                or rows[0]['Config']['Labels']['io.x-k8s.kind.cluster'] != 'kil-v3-lab'
                or rows[0]['Config']['Labels']['io.x-k8s.kind.role'] != 'control-plane'
                or rows[0]['State']['Running'] is not True):
            raise ValueError('unbound_owned_node')
        return rows[0]['Id']
    except (KeyError, TypeError, IndexError):
        raise ValueError('unbound_owned_node') from None


def same_incarnation(before, after):
    if not (type(before) is dict and type(after) is dict
            and all(type(before.get(key)) is str and before[key]
                    and before[key] == after.get(key) for key in INCARNATION_KEYS)):
        raise ValueError('application_incarnation_changed_or_unbound')


def calico_readiness_projection(payload, kind):
    """Native nested workload -> configuration/readiness projection only.

    The full native response remains a command receipt. Omitted fields are not
    audited and this projection establishes no platform content provenance.
    """
    from kil.v3b2_inventory import parse_calico_runtime_workload
    row = decode(payload)
    if kind not in ('DaemonSet','Deployment') or type(row) is not dict:
        raise ValueError('native_calico_kind_invalid')
    if row.get('apiVersion')!='apps/v1' or row.get('kind')!=kind:
        raise ValueError('native_calico_type_invalid')
    metadata = row['metadata']
    template = row['spec']['template']['spec']
    if type(metadata) is not dict or type(template) is not dict or type(row['status']) is not dict:
        raise ValueError('native_calico_structure_invalid')
    projected = {'apiVersion':'apps/v1','kind':kind,
        'metadata':{key:metadata[key] for key in ('namespace','name','uid','resourceVersion')},
        'spec':{},'status':{}}
    for field in ('containers','initContainers'):
        containers = template[field] if field=='containers' else template.get(field,[])
        if type(containers) is not list or any(type(container) is not dict for container in containers):
            raise ValueError('native_calico_container_array_invalid')
        projected['spec'][field] = [{key:container[key] for key in ('name','image')} for container in containers]
    fields = ('desiredNumberScheduled','numberReady') if kind=='DaemonSet' else ('replicas','readyReplicas')
    for field in fields:
        # DeploymentStatus documents these counts as omitempty. Preserve their
        # omission, not a repaired zero count; the caller can only mark pending.
        if kind=='Deployment' and field not in row['status']:
            continue
        value = row['status'][field]
        if type(value) is not int or value<0:
            raise ValueError('native_calico_counts_invalid')
        projected['status'][field] = value
    if projected['status'].get(fields[1],0)>projected['status'].get(fields[0],0):
        raise ValueError('native_calico_counts_inconsistent')
    # The existing closed parser checks identities and exact pinned inventory
    # independently of readiness; its validation-only count probe is never an
    # observed readiness record. Persist only the actual native counts below.
    eligibility = deepcopy(projected)
    eligibility['status'] = {field:1 for field in fields}
    parse_calico_runtime_workload(canonical(eligibility),kind)
    return canonical(projected)


def check_source(repository, reviewed_source):
    """Bounded exact local Git reads; no origin/main or synchronization claim."""
    if type(reviewed_source) is not str or re.fullmatch(r'[0-9a-f]{40}', reviewed_source) is None:
        raise ValueError('reviewed_source_must_be_exact_commit')
    environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL') if key in os.environ}
    environment['HOME'] = str(passwd_home())
    for argv, expected in [(('git', 'rev-parse', 'HEAD'), reviewed_source.encode()),
                           (('git', 'status', '--porcelain'), b'')]:
        result = capture_process(argv, environment, None, 10, 65536, repository)
        if result.returncode != 0 or result.stdout_bytes.strip() != expected or result.stderr_bytes:
            raise ValueError('reviewed_local_source_not_clean_head')


class ExploratoryLifecycle:
    def __init__(self, repository, inputs, store, runner, source_commit, mode):
        self.runtime = None
        try:
            self._initialize(repository, inputs, store, runner, source_commit, mode)
        except BaseException:
            self.close()
            raise

    def close(self):
        """Release retained descriptors only, never native resources."""
        try:
            if getattr(self, 'ssh', None) is not None:
                self.ssh.close()
        finally:
            if self.runtime is not None:
                self.runtime.close()

    def _initialize(self, repository, inputs, store, runner, source_commit, mode):
        if (mode not in ('rehearsal', 'action') or type(mode) is not str
                or type(source_commit) is not str or re.fullmatch(r'[0-9a-f]{40}', source_commit) is None
                or re.fullmatch(r'v3b2-[0-9a-f]{64}', inputs.workload.run_id) is None):
            raise ValueError('invalid_exploratory_lifecycle_binding')
        self.repository, self.inputs, self.store, self.runner = repository, inputs, store, runner
        self.source_commit, self.mode = source_commit, mode
        self.run_digest = inputs.workload.run_id[5:]
        self.runtime = RuntimeAuthority.create(store, self.run_digest)
        self.ssh = SSHControls(self.runtime)
        self._ssh_inventory_active = False
        self.ssh_evidence = {}
        self.profile_start_succeeded = self.profile_stop_succeeded = self.profile_delete_succeeded = False
        self.paths = ProfilePaths.bind(self.runtime)
        self.default_paths = StrictProfilePaths(self.paths.home, store.path)
        self.identity = OwnedIdentity('kil-v3-lab', 'unix://' + str(self.paths.profile / 'docker.sock'),
                                     'kil-v3-lab', str(self.runtime.kubeconfig), None, None)
        self.docker_env = (('DOCKER_CONFIG', str(self.runtime.docker_config)),
                           ('DOCKER_HOST', self.identity.docker_host))
        self.colima_env = ExploratoryColimaCommand(colima_start_command(), self.runtime).env
        self.profile_binding = None
        self.original_foreign = None
        self.started_pristine = False
        self.profile_attempted = self.cluster_attempted = False
        self.cluster_delete_attempted = self.cluster_removed = False
        self.profile_stop_attempted = self.profile_stopped = False
        self.profile_delete_attempted = self.profile_delete_completed = False
        self.manual_recovery = self.owned_teardown = False
        self.sequence = 0
        self.mutation_commitments = set()
        self.attach_attempted = set()
        self.anchors, self.endpoints, self.results, self.source_metadata = {}, {}, {}, {}
        self.selected_pods, self.endpoint_bindings = {}, {}
        self.deployment_bindings = {}
        self.calico_bindings = {}
        self.command_checksums, self.aliases, self.environment = {}, {}, {}
        self.foreign_observations, self.placements, self.platform_images = [], [], []
        self.rendered = None
        self.groups = None
        self.frozen = set()
        self.freeze_attempted = set()
        self.reached_gate = 'initial'
        self.error = None
        self._read_deadline = None
        self.runtime_snapshot_attempted = False
        self.runtime_observations = None
        self.runtime_leftovers = None
        self.runtime_leftovers_error = None
        self.kind_config_bytes = None
        self.kind_config_identity = None
        self.loaded_kil_source = self.loaded_kil_stdout = self.loaded_kil_stdout_name = None
        self.envoy_platform_pull_ready = False
        self.node_alias_states = None
        self.node_alias_removals = ()

    def observe(self, command, allow_failure=False, *, _global_inventory=False):
        if type(command) not in (Command, ExploratoryColimaCommand, ExploratoryEnvoyPlatformCommand, ExploratoryNodeAliasCommand):
            raise ValueError('closed_command_required')
        command.__post_init__()
        self.runtime.guard()
        if type(command) in (ExploratoryColimaCommand,ExploratoryEnvoyPlatformCommand,ExploratoryNodeAliasCommand) and command.authority is not self.runtime:
            raise ValueError('foreign_colima_runtime_authority')
        if type(command) is ExploratoryNodeAliasCommand and command.identity is not self.identity:
            raise ValueError('node_alias_command_identity_not_current_owned_node')
        if _global_inventory:
            if (type(command) is not Command or command.argv != ('colima','list','--json')
                    or command.env or command.mutating):
                raise ValueError('global_inventory_route_not_read_only')
        elif type(command) is Command and command.argv[0] == 'colima':
            command = ExploratoryColimaCommand(command, self.runtime)
        if self._read_deadline is not None:
            remaining = self._read_deadline-time.monotonic()
            if command.mutating or remaining<1:
                raise ValueError('readiness_deadline_or_read_only_boundary')
            strict = command.command if type(command) is ExploratoryColimaCommand else command
            strict = replace(strict,timeout_s=min(command.timeout_s,10,int(remaining)))
            command = (ExploratoryColimaCommand(strict,self.runtime)
                       if type(command) is ExploratoryColimaCommand else strict)
        dispatch = (command.argv,command.env,command.stdin,command.timeout_s,command.mutating)
        if command.mutating:
            self.authorize_mutation(command)
        self.require_dispatch_unchanged(command,dispatch)
        self.sequence += 1
        sequence = self.sequence
        name = 'command-%04d' % sequence
        self.store.record('command_intent', {'sequence': sequence, 'argv': list(command.argv),
            'env': dict(command.env), 'mutating': command.mutating, 'timeout_s':command.timeout_s,
            'stdin_sha256': None if command.stdin is None else sha256(command.stdin).hexdigest()})
        if command.mutating and command.argv[:2] == ('kind','create'):
            self.require_kind_control()
        self.require_dispatch_unchanged(command,dispatch)
        if command.mutating:
            self.commit_mutation(command)
        result = self.runner.run(command)
        out_hash = self.store.write(name + '.stdout', result.stdout_bytes)
        err_hash = self.store.write(name + '.stderr', result.stderr_bytes)
        self.command_checksums[name] = {'stdout': out_hash, 'stderr': err_hash}
        self.store.record('command_terminal', {'sequence': sequence, 'returncode': result.returncode,
                                               'stdout_sha256': out_hash, 'stderr_sha256': err_hash})
        if (result.returncode == 0 and type(command) is ExploratoryNodeAliasCommand
                and command.operation == 'remove'):
            row = next(row for row in self.node_alias_states[command.role].import_rows if row[0] == command.import_ref)
            self.node_alias_removals += ((command.role,row,sequence,dispatch,result.stdout_bytes,result.stderr_bytes),)
        if result.returncode == 0 and command.mutating:
            if command.argv == colima_start_command().argv: self.profile_start_succeeded = True
            elif command.argv == ('colima','stop','--profile','kil-v3-lab'): self.profile_stop_succeeded = True
            elif command.argv == ('colima','delete','--profile','kil-v3-lab','--force','--data'): self.profile_delete_succeeded = True
        if result.returncode != 0 and not allow_failure:
            raise ValueError('native_command_failed_%s' % result.returncode)
        return result

    def require_dispatch_unchanged(self, command, dispatch):
        """Join fresh grammar/authority to the authorized durable intent bytes."""
        if type(command) not in (Command,ExploratoryColimaCommand,ExploratoryEnvoyPlatformCommand,ExploratoryNodeAliasCommand):
            raise ValueError('closed_command_required')
        command.__post_init__()
        if type(command) in (ExploratoryColimaCommand,ExploratoryEnvoyPlatformCommand,ExploratoryNodeAliasCommand) and command.authority is not self.runtime:
            raise ValueError('foreign_colima_runtime_authority')
        self.runtime.guard()
        if self.ssh.state in ('binding','stopping','deleting') and (
                not self._ssh_inventory_active or command.mutating
                or command.argv != ('colima','list','--json') or command.env != self.colima_env):
            raise ValueError('ssh_provisional_state_only_private_inventory')
        if self.ssh.state != 'unbound':
            self.ssh.guard()
            self.require_retained_ssh_controls()
        elif not self.profile_attempted:
            self.ssh.require_absent()
        if dispatch != (command.argv,command.env,command.stdin,command.timeout_s,command.mutating):
            raise ValueError('command_changed_during_native_authorization_or_intent')
        if type(command) is ExploratoryEnvoyPlatformCommand:
            command.__post_init__()
        if type(command) is ExploratoryNodeAliasCommand:
            if command.identity is not self.identity:
                raise ValueError('node_alias_command_identity_not_current_owned_node')
            if command.mutating:
                self.require_node_alias_unchanged(command)
                command.__post_init__()
                self.runtime.guard()
                self.ssh.guard()
                self.require_retained_ssh_controls()
        if command.argv[:2] == ('docker','tag'):
            if command.argv[2] != self.require_loaded_kil_source():
                raise ValueError('docker_tag_not_exact_loaded_accepted_source')
        if dispatch != (command.argv,command.env,command.stdin,command.timeout_s,command.mutating):
            raise ValueError('command_changed_during_final_native_checks')

    def authorize_mutation(self, command):
        """Validate dispatch eligibility without claiming a runner handoff."""
        argv = command.argv
        if (argv[0] == 'limactl' or (argv[0] == 'colima' and command.env != self.colima_env)
                or (argv[0] in ('docker','kind') and command.env != self.docker_env)
                or (argv[0] == 'kubectl' and (argv[1:3] != ('--kubeconfig',self.identity.kubeconfig) or command.env))):
            raise ValueError('mutation_authority_not_exact_owned_binding')
        if argv == colima_start_command().argv:
            if self.profile_attempted:
                raise ValueError('profile_start_already_attempted')
            check_source(self.repository, self.source_commit)
            require_pristine(self.paths)
            self.private_inventory(empty=True)
            self.require_foreign_preserved()
        elif argv == kind_create_command(self.identity).argv:
            if self.cluster_attempted:
                raise ValueError('cluster_create_already_attempted')
            self.guard_profile()
            self.require_kind_control()
            if self.endpoint_rows():
                raise ValueError('fresh_owned_endpoint_not_empty')
            self.require_foreign_preserved()
        elif argv == kind_delete_command(self.identity).argv:
            if self.cluster_delete_attempted or self.cluster_removed:
                raise ValueError('cluster_delete_already_attempted')
            self.guard_cluster()
            self.ensure_runtime_snapshot()
            self.require_foreign_preserved()
        elif argv == ('colima', 'stop', '--profile', 'kil-v3-lab'):
            if self.profile_stop_attempted or (self.cluster_attempted and not self.cluster_removed):
                raise ValueError('profile_stop_not_authorized')
            self.guard_profile()
            self.ensure_runtime_snapshot()
            self.require_foreign_preserved()
        elif argv == ('colima', 'delete', '--profile', 'kil-v3-lab', '--force', '--data'):
            if self.profile_delete_attempted or not self.profile_stopped:
                raise ValueError('profile_delete_not_authorized')
            self.guard_profile(stopped=True)
            self.require_foreign_preserved()
        else:
            self.require_allowed_other_mutation(command)
            self.guard_cluster()
            commitment = (argv, command.env, None if command.stdin is None else sha256(command.stdin).hexdigest())
            if commitment in self.mutation_commitments:
                raise ValueError('mutation_already_attempted')
            self.require_foreign_preserved()

    def commit_mutation(self, command):
        """Commit one-shot state immediately before handoff; never roll it back.

        Authorization, durable intent and fresh consumer/runtime checks have
        completed. No native handoff is claimed for a known earlier refusal;
        an opaque runner exception after this point remains an uncertain attempt.
        """
        argv = command.argv
        if argv[:2] == ('colima','start'):
            self.started_pristine = True
            self.profile_attempted = True
            self.reached_gate = 'profile_start_attempted'
        elif argv[:2] == ('kind','create'):
            self.cluster_attempted = True
            self.reached_gate = 'cluster_create_attempted'
        elif argv[:2] == ('kind','delete'):
            self.cluster_delete_attempted = True
        elif argv[:2] == ('colima','stop'):
            self.profile_stop_attempted = True
        elif argv[:2] == ('colima','delete'):
            self.profile_delete_attempted = True
        else:
            self.mutation_commitments.add((argv,command.env,
                None if command.stdin is None else sha256(command.stdin).hexdigest()))
            if argv[0]=='kubectl' and argv[3]=='attach':
                track = next(track for track,namespace in TRACK_NAMESPACES if namespace==argv[6])
                self.attach_attempted.add(track)

    def require_allowed_other_mutation(self, command):
        """The exploratory table is narrower than the reusable strict grammar."""
        argv = command.argv
        accepted = {row.role:row for row in ACCEPTED_IMAGES}
        if type(command) is ExploratoryNodeAliasCommand:
            command.__post_init__()
            if (command.authority is not self.runtime or command.identity is not self.identity
                    or self.node_alias_states is None or not command.mutating):
                raise ValueError('node_alias_mutation_requires_initial_owned_config_proof')
            if command.operation == 'restart' and not self.node_alias_removals:
                raise ValueError('node_alias_restart_without_successful_removals')
            if command.operation == 'remove' and command.import_ref not in {
                    row[0] for row in self.node_alias_states[command.role].import_rows}:
                raise ValueError('node_alias_remove_not_initially_associated')
        elif type(command) is ExploratoryEnvoyPlatformCommand:
            command.__post_init__()
            if command.authority is not self.runtime or not self.envoy_platform_pull_ready:
                raise ValueError('envoy_platform_pull_requires_initial_accepted_host_proof')
        elif argv[0]=='docker':
            source = self.require_loaded_kil_source() if argv[:2] == ('docker','tag') else accepted['kil'].config_digest
            allowed = docker_image_import_commands(self.identity,self.inputs.archive,source,
                accepted['kil'].requested_image,accepted['envoy'].requested_image)[:3]
            if not any((command.argv,command.env,command.stdin)==(row.argv,row.env,row.stdin) for row in allowed):
                raise ValueError('docker_mutation_outside_exploratory_table')
        elif argv[0]=='kind':
            if not any(argv==kind_load_command(self.identity,row.requested_image).argv for row in ACCEPTED_IMAGES):
                raise ValueError('kind_mutation_outside_exploratory_table')
        elif argv[0]=='kubectl':
            arguments = argv[3:]
            if arguments==('apply','-f','-'):
                items = decode(render_objects(self.inputs.profile,self.inputs.workload))['items']
                groups = ([row for row in items if row['kind']=='Namespace'],
                          [row for row in items if row['kind']=='NetworkPolicy'],
                          [row for row in items if row['kind'] not in {'Namespace','NetworkPolicy','Pod'}],
                          [row for row in items if row['kind']=='Pod'])
                if command.stdin not in tuple(self.object_list(group) for group in groups):
                    raise ValueError('apply_payload_outside_exploratory_table')
            elif arguments==('apply','-f',str(self.store.path/'calico-v3.32.0.yaml')):
                payload=read_regular(self.store.path/'calico-v3.32.0.yaml',8*1024*1024)
                verify_bytes(payload,self.inputs.profile.calico_manifest_sha256,len(payload))
            elif arguments[:2]==('attach','pod/driver'):
                track=next(track for track,namespace in TRACK_NAMESPACES if namespace==arguments[3])
                if track in self.attach_attempted:
                    raise ValueError('track_attach_already_attempted')
                if self.mode=='rehearsal':
                    if command.stdin!=b'': raise ValueError('rehearsal_must_be_empty_eof')
                else:
                    from kil.v3b1_driver_protocol import parse_instruction
                    if not self.store.uncertain or not self.store.attempts or self.store.attempts[-1]!=track:
                        raise ValueError('action_attach_requires_durable_one_shot')
                    retained=self.private_read(track+'.instruction.json')
                    journal=[decode(line) for line in self.private_read('journal.jsonl').split(b'\n')[:-1]]
                    intents=[row['details'] for row in journal if row['event']=='request_intent' and row['details']['track']==track]
                    if (retained!=command.stdin or len(intents)!=1
                            or intents[0]['instruction_sha256']!=sha256(retained).hexdigest()):
                        raise ValueError('action_attach_requires_exact_durable_intent')
                    instruction=parse_instruction(retained,expected_track=track)
                    if (instruction['method']!='POST' or instruction['path']!='/consequential/admin'
                            or instruction['body_byte_count']!=0
                            or instruction['headers']['authorization']!='Bearer v3b1-lab-credential'):
                        raise ValueError('action_outside_harmless_admin_boundary')
            elif not any(argv==kubectl_envoy_quiesce_commands(self.identity,NAMESPACES[track],self.anchors[(track,'envoy')]['pod'])[0].argv
                         for track in TRACKS if (track,'envoy') in self.anchors):
                raise ValueError('kubectl_mutation_outside_exploratory_table')
        else:
            raise ValueError('mutation_outside_exploratory_table')

    def guard_profile(self, stopped=False):
        if self.profile_binding is None:
            raise ValueError('profile_binding_unavailable')
        observed = capture(self.paths)
        if unchanged(self.paths.document(), observed, self.profile_binding, stopped=stopped) is not True:
            raise ValueError('owned_profile_changed')
        if stopped and self.ssh.state == 'running':
            if not self.profile_stop_succeeded:
                raise ValueError('ssh_stop_transition_without_successful_native_stop')
            self.ssh.begin_stopped()
        self.private_inventory(stopped=stopped)
        if stopped and self.ssh.state == 'stopping':
            self.retain_ssh_controls('stopped')
            self.ssh.finish_stopped()
        return observed

    def private_inventory(self, *, empty=False, stopped=False):
        if self.ssh.state == 'binding':
            raise ValueError('ssh_running_binding_previous_closure_failed')
        self._ssh_inventory_active = True
        try:
            return self._private_inventory(empty=empty, stopped=stopped)
        except BaseException:
            if self.ssh.state in ('binding','stopping','deleting'):
                self.ssh.refuse()
            raise
        finally:
            self._ssh_inventory_active = False

    def _private_inventory(self, *, empty=False, stopped=False):
        self.runtime.guard()
        colima = _read(self.paths.colima,directory_only=True)
        if empty:
            self.ssh.require_absent()
        binding = not empty and self.ssh.state == 'unbound'
        if binding:
            if stopped or not self.profile_start_succeeded or self.profile_binding is None:
                raise ValueError('ssh_running_binding_without_successful_bound_start')
            observed = capture(self.paths)
            if unchanged(self.paths.document(), observed, self.profile_binding) is not True:
                raise ValueError('owned_profile_changed')
            self.ssh.begin_running()
        if not empty:
            self.ssh.guard()
        allowed = {'_lima','_store','_templates','kil-v3-lab'}
        if not empty: allowed.add('ssh_config')
        if colima is None or not set(colima['entries']) <= allowed:
            raise ValueError('private_colima_profile_roster_unknown')
        before = capture_roster(self.paths)
        result = self.observe(Command(('colima','list','--json'),10))
        after = capture_roster(self.paths)
        colima = _read(self.paths.colima,directory_only=True)
        if colima is None or not set(colima['entries']) <= allowed:
            raise ValueError('private_colima_profile_roster_unknown')
        rows = require_complete(decode_inventory(result.stdout_bytes,
            returncode=result.returncode,stderr=result.stderr_bytes),before,after)
        if before is None:
            raise ValueError('private_lima_roster_unavailable')
        if empty:
            if rows:
                raise ValueError('private_lima_roster_not_empty')
        else:
            expected = {'name':'kil-v3-lab','status':'Stopped' if stopped else 'Running',
                        'arch':'aarch64','runtime':'docker','cpus':4,
                        'memory':8*1024**3,'disk':60*1024**3}
            if len(rows)!=1 or any(rows[0].get(key)!=value for key,value in expected.items()):
                raise ValueError('private_profile_inventory_not_exact_owned')
        self.runtime.guard()
        if empty:
            self.ssh.require_absent()
        else:
            self.ssh.guard()
            if unchanged(self.paths.document(), capture(self.paths), self.profile_binding, stopped=stopped) is not True:
                raise ValueError('owned_profile_changed')
            if binding:
                self.retain_ssh_controls('running')
                self.ssh.finish_running()
        return rows

    def retain_ssh_controls(self, state):
        """Retain and read back the provisional proof before state adoption."""
        try:
            self.ssh.guard()
            phase = 'removed' if state == 'deleted' else state
            proof = {'schema':'kil.hf-generated-ssh-controls.v1',
                     'run_digest':self.run_digest,
                     'runtime_binding_sha256':sha256(self.runtime._binding[4]).hexdigest(),
                     'phase':phase, 'port':self.ssh.port,
                     'colima':dict(self.ssh.colima.proof(), path=str(self.paths.colima/'ssh_config')),
                     'instance':dict(self.ssh.instance.proof(), path=str(self.paths.instance/'ssh.config'))}
            evidence = {'ssh-controls.'+phase+'.json': canonical(proof)}
            for label, control in [('colima',self.ssh.colima),('instance',self.ssh.instance)]:
                if control.data is not None and (phase == 'running' or (phase == 'stopped' and label == 'colima')):
                    evidence['ssh-control-'+label+'.'+phase+'.config'] = control.data
            for name, payload in evidence.items():
                self.store.write(name, payload)
            for name, payload in evidence.items():
                if self.private_read(name) != payload:
                    raise ValueError('ssh_retained_evidence_changed')
            self.ssh.guard()
            colima = _read(self.paths.colima,directory_only=True)
            allowed = {'_lima','_store','_templates','ssh_config'}
            if state != 'deleted': allowed.add('kil-v3-lab')
            if colima is None or not set(colima['entries']) <= allowed:
                raise ValueError('private_colima_profile_roster_unknown')
            self.ssh_evidence.update(evidence)
        except BaseException:
            self.ssh.refuse()
            raise

    def require_retained_ssh_controls(self):
        for name, payload in self.ssh_evidence.items():
            if self.private_read(name) != payload:
                self.ssh.refuse()
                raise ValueError('ssh_retained_evidence_changed')
        self.ssh.guard()

    def require_kind_control(self):
        self.runtime.guard()
        current = _read(self.runtime.kind_config)
        if (self.kind_config_bytes is None or current is None or 'hex' not in current
                or {key:current[key] for key in ('device','inode','mode')} != self.kind_config_identity
                or read_regular(self.runtime.kind_config,65536) != self.kind_config_bytes
                or self.private_read('kind-config.yaml') != self.kind_config_bytes):
            raise ValueError('kind_runtime_control_changed_or_unprepared')
        self.runtime.guard()

    def endpoint_rows(self):
        result = self.observe(Command(CLUSTER_INVENTORY_ARGV, 10, env=self.docker_env))
        payload = result.stdout_bytes
        if b'\r' in payload or (payload and not payload.endswith(b'\n')):
            raise ValueError('incomplete_docker_roster')
        rows, identifiers, names = [], set(), set()
        for line in payload.split(b'\n')[:-1]:
            row = decode(line, maximum=1048576)
            if (type(row) is not dict or type(row.get('ID')) is not str
                    or re.fullmatch(r'[0-9a-f]{64}', row['ID']) is None
                    or type(row.get('Names')) is not str or not row['Names']
                    or row['ID'] in identifiers or row['Names'] in names):
                raise ValueError('invalid_docker_roster')
            rows.append(row); identifiers.add(row['ID']); names.add(row['Names'])
        return rows

    def cluster_uid(self):
        command = Command(('kubectl', '--kubeconfig', self.identity.kubeconfig,
                           'get', 'namespace', 'kube-system', '--output', 'json'), 10)
        value = decode(self.observe(command).stdout_bytes)
        if (type(value) is not dict or value.get('kind') != 'Namespace'
                or value.get('apiVersion') != 'v1' or value['metadata'].get('name') != 'kube-system'
                or type(value['metadata'].get('uid')) is not str or not value['metadata']['uid']):
            raise ValueError('invalid_cluster_uid')
        return value['metadata']['uid']

    def guard_cluster(self):
        self.guard_profile()
        if self.identity.node_container_id is None or self.identity.cluster_incarnation_uid is None:
            raise ValueError('cluster_binding_unavailable')
        observed_id = bind_node(decode(self.observe(Command(('docker', 'inspect', 'kil-v3-lab-control-plane'),
                                                           10, env=self.docker_env)).stdout_bytes))
        rows = self.endpoint_rows()
        if (observed_id != self.identity.node_container_id or len(rows) != 1
                or rows[0]['ID'] != observed_id or rows[0]['Names'] != 'kil-v3-lab-control-plane'
                or self.cluster_uid() != self.identity.cluster_incarnation_uid):
            raise ValueError('owned_cluster_changed_or_extra_container')

    def verify_versions(self):
        if platform.system() != 'Darwin' or platform.machine() != 'arm64':
            raise ValueError('host_not_pinned_darwin_arm64')
        self.environment.update(host_os=platform.system(), host_arch=platform.machine(),
            host_os_version=platform.mac_ver()[0], host_kernel=platform.release(),
            docker_daemon_version='UNOBSERVED')
        versions = {}
        for name, arguments in TOOL_VERSION_ARGUMENTS.items():
            command = Command((str(self.inputs.tools / name), *arguments), 10)
            payload = self.observe(command).stdout_bytes
            if len(payload) > 65536 or payload.strip() != self.inputs.tool_records[name]['version_output'].encode():
                raise ValueError('accepted_tool_version_changed')
            versions[name] = payload.decode('utf-8', 'strict').strip()
        colima = self.observe(Command(('colima','version'), 10)).stdout_bytes
        lima = self.observe(Command(('limactl','--version'), 10)).stdout_bytes
        if (len(colima) > 1024 or re.fullmatch(rb'colima version v0\.10\.3\n(?:git commit: [0-9a-f]{7,40}\n)?', colima) is None
                or lima.strip() != b'limactl version 2.2.0' or len(lima) > 1024):
            raise ValueError('colima_lima_versions_not_pinned')
        versions.update(colima=colima.decode().strip(), lima=lima.decode().strip())
        self.environment['observed_tool_versions'] = versions

    def kubeconfig_fingerprint(self):
        inherited = os.environ.get('KUBECONFIG')
        paths = ([self.paths.home / '.kube/config'] if not inherited
                 else [Path(value) for value in inherited.split(':')])
        if len(paths) > 32 or any(not path.is_absolute() or '..' in path.parts or path.resolve() != path
                                  or path.is_symlink() for path in paths):
            raise ValueError('unsafe_inherited_kubeconfig')
        result, total = [], 0
        for path in paths:
            observed = self.foreign_file(path,8*1024*1024)
            total += observed['byte_count'] or 0
            if total > 8 * 1024 * 1024:
                raise ValueError('inherited_kubeconfig_byte_bound')
            result.append(observed)
        return {'inherited': inherited, 'files':result}

    def foreign_file(self, path, maximum):
        """Stable no-follow full-byte commitment; no foreign file is created."""
        if (not isinstance(path,Path) or not path.is_absolute() or '..' in path.parts
                or path.resolve()!=path):
            raise ValueError('unsafe_foreign_configuration_path')
        identity = None
        payload = None
        with _parent(path) as parent:
            if parent is not None:
                try:
                    before = os.stat(path.name,dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    payload = read_regular(path,maximum)
                    after = os.stat(path.name,dir_fd=parent,follow_symlinks=False)
                    keys = ('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')
                    if any(getattr(before,key)!=getattr(after,key) for key in keys):
                        raise ValueError('foreign_configuration_changed_during_read')
                    identity = {key:getattr(before,key) for key in keys}
        return {'path':str(path),'present':payload is not None,'identity':identity,
                'byte_count':None if payload is None else len(payload),
                'sha256':None if payload is None else sha256(payload).hexdigest()}

    def foreign_files(self):
        docker = self.runner.global_docker_config
        if type(docker) is not str:
            raise ValueError('unsafe_global_docker_config_path')
        path = Path(docker)
        if not path.is_absolute() or '..' in path.parts or path.resolve()!=path:
            raise ValueError('unsafe_global_docker_config_path')
        networks = _read(self.default_paths.lima / '_config/networks.yaml')
        if networks is not None and 'hex' not in networks:
            raise ValueError('default_networks_not_regular_file')
        return {'default_networks':networks,
                'global_docker_config':docker,
                'global_docker_directory':_read(path,directory_only=True),
                'global_docker_file':self.foreign_file(path/'config.json',8*1024*1024),
                'kubeconfig':self.kubeconfig_fingerprint()}

    def foreign_snapshot(self):
        before = capture_roster(self.default_paths)
        files = self.foreign_files()
        inventory = self.observe(Command(('colima','list','--json'), 10), _global_inventory=True)
        after = capture_roster(self.default_paths)
        rows = require_complete(decode_inventory(inventory.stdout_bytes,
            returncode=inventory.returncode, stderr=inventory.stderr_bytes), before, after)
        context = self.observe(replace(docker_context_command(), timeout_s=10)).stdout_bytes
        if not context or len(context) > 4096 or b'\r' in context or not context.endswith(b'\n') or context.count(b'\n') != 1:
            raise ValueError('invalid_global_docker_context')
        final = self.observe(Command(('colima','list','--json'),10),_global_inventory=True)
        end = capture_roster(self.default_paths)
        final_rows = require_complete(decode_inventory(final.stdout_bytes,
            returncode=final.returncode,stderr=final.stderr_bytes),after,end)
        if before!=end or rows!=final_rows or files!=self.foreign_files():
            raise ValueError('foreign_global_state_changed_during_observation')
        return {'foreign_profiles':rows, 'foreign_lima_roster':before,
                'global_docker_context':context.decode('utf-8', 'strict').strip(),
                **files}

    def require_foreign_preserved(self):
        if self.original_foreign is None:
            raise ValueError('original_foreign_binding_unavailable')
        observed = self.foreign_snapshot()
        self.foreign_observations.append(observed)
        if observed != self.original_foreign:
            raise ValueError('foreign_global_state_changed')

    def prepare(self):
        config = decode(render_kind_config(self.inputs.profile), maximum=65536)
        if config['nodes'] != [{'role':'control-plane'}]:
            raise ValueError('unexpected_kind_config')
        config['nodes'][0]['image'] = self.inputs.profile.kind_node_image
        self.kind_config_bytes = canonical(config)
        self.store.write('kind-config.yaml', self.kind_config_bytes)
        self.runtime.write_control('kind-config.yaml',self.kind_config_bytes)
        row = _read(self.runtime.kind_config)
        self.kind_config_identity = {key:row[key]
                                     for key in ('device','inode','mode')}
        calico = read_regular(self.repository / self.inputs.profile.calico_manifest_path, 8 * 1024 * 1024)
        verify_bytes(calico, self.inputs.profile.calico_manifest_sha256, len(calico))
        self.store.write('calico-v3.32.0.yaml', calico)
        self.rendered = render_objects(self.inputs.profile, self.inputs.workload)
        items = decode(self.rendered)['items']
        self.groups = ([row for row in items if row['kind']=='Namespace'],
                       [row for row in items if row['kind']=='NetworkPolicy'],
                       [row for row in items if row['kind'] not in {'Namespace','NetworkPolicy','Pod'}],
                       [row for row in items if row['kind']=='Pod'])
        self.store.write('rendered-objects.json', self.rendered)

    def setup(self):
        from kil.v3b2_proofs import validate_applied_objects
        from kil.v3b2_inventory import parse_calico_runtime_workload
        check_source(self.repository, self.source_commit)
        self.reached_gate = 'reviewed_clean_local_source'
        self.verify_versions()
        self.reached_gate = 'host_and_tool_versions_verified'
        self.original_foreign = self.foreign_snapshot()
        self.store.write('foreign-original.json', canonical(self.original_foreign))
        require_pristine(self.paths)
        self.private_inventory(empty=True)
        self.reached_gate = 'foreign_and_pristine_preflight'
        self.prepare()
        self.reached_gate = 'private_prepared'
        start = colima_start_command()
        result = self.observe(start, allow_failure=True)
        self.reached_gate = 'profile_start_attempted'
        try:
            observed = capture(self.paths)
            self.store.write('profile-created.json', canonical(observed))
            self.profile_binding = creation_binding(self.paths.document(), observed)
            self.reached_gate = 'profile_bound'
        except Exception:
            self.manual_recovery = True
            raise ValueError('profile_start_unbound') from None
        if result.returncode != 0:
            raise ValueError('profile_start_failed')
        self.guard_profile()
        if self.endpoint_rows():
            raise ValueError('fresh_private_docker_endpoint_not_empty')
        self.reached_gate = 'private_endpoint_empty'
        result = self.observe(kind_create_command(self.identity), allow_failure=True)
        self.reached_gate = 'cluster_create_attempted'
        try:
            node_id = bind_node(decode(self.observe(Command(('docker','inspect','kil-v3-lab-control-plane'),
                                                           10, env=self.docker_env)).stdout_bytes))
            rows = self.endpoint_rows()
            if len(rows) != 1 or rows[0]['ID'] != node_id or rows[0]['Names'] != 'kil-v3-lab-control-plane':
                raise ValueError('cluster_create_endpoint_not_exact')
            uid = self.cluster_uid()
            self.identity = replace(self.identity, node_container_id=node_id, cluster_incarnation_uid=uid)
            self.reached_gate = 'cluster_bound'
        except Exception:
            self.manual_recovery = True
            raise ValueError('cluster_create_unbound') from None
        if result.returncode != 0:
            raise ValueError('cluster_create_failed')
        self.import_application_images()
        self.reached_gate = 'application_images_imported'
        self.prove_node_application_aliases()
        self.reached_gate = 'application_node_aliases_bound'
        calico_path = self.store.path / 'calico-v3.32.0.yaml'
        calico = read_regular(calico_path, 8 * 1024 * 1024)
        verify_bytes(calico, self.inputs.profile.calico_manifest_sha256, len(calico))
        self.observe(kubectl_apply_calico_command(self.identity, calico_path))
        self.reached_gate = 'calico_apply_attempted'
        readiness_budget = SetupReadinessBudget()
        def calico_ready(deadline):
            for kind in ('DaemonSet','Deployment'):
                if time.monotonic() >= deadline:
                    raise ValueError('readiness_deadline_exceeded')
                raw = self.observe(replace(kubectl_calico_workload_command(self.identity, kind), timeout_s=10)).stdout_bytes
                projection = calico_readiness_projection(raw,kind)
                digest = self.store.write('calico-readiness-projection-%04d.json'%self.sequence,projection)
                self.store.record('calico_readiness_configuration_projection',{
                    'command_sequence':self.sequence,'native_sha256':sha256(raw).hexdigest(),
                    'projection_sha256':digest,'full_configuration_verified':False,
                    'platform_image_provenance_verified':False})
                projected = decode(projection)
                uid = projected['metadata']['uid']
                if kind in self.calico_bindings and self.calico_bindings[kind]!=uid:
                    raise ValueError('selected_calico_workload_replaced')
                self.calico_bindings.setdefault(kind,uid)
                counts = projected['status']
                if len(counts)!=2 or any(value!=1 for value in counts.values()):
                    raise ReadPending('validated_calico_counts_not_ready')
                parse_calico_runtime_workload(projection, kind)
        self.read_until(calico_ready,budget=readiness_budget)
        self.reached_gate = 'calico_ready'
        for group in self.groups[:2]:
            self.observe(kubectl_apply_command(self.identity, self.object_list(group)))
        policy_payload = self.applied_read(self.groups[1])
        validate_applied_objects(self.groups[1], policy_payload)
        self.store.write('applied-policy.json', policy_payload)
        self.reached_gate = 'application_policy_configuration_verified'
        self.observe(kubectl_apply_command(self.identity, self.object_list(self.groups[2])))
        self.reached_gate = 'application_workload_apply_attempted'
        def application_ready(deadline):
            endpoints = {}
            for track in TRACKS:
                for role in ('authz','envoy','target'):
                    if time.monotonic() >= deadline:
                        raise ValueError('readiness_deadline_exceeded')
                    self.require_deployment_available(track,role)
                    self.observe(replace(kubectl_workload_ready_command(self.identity, NAMESPACES[track], role), timeout_s=10))
                    if time.monotonic() >= deadline:
                        raise ValueError('readiness_deadline_exceeded')
                    endpoints[(track, role)] = self.read_endpoint(track, role)
            return endpoints
        self.endpoints = self.read_until(application_ready,budget=readiness_budget)
        self.reached_gate = 'application_endpoints_ready'
        nonpods = [*self.groups[0], *self.groups[1], *self.groups[2]]
        applied = self.applied_read(nonpods)
        bindings = validate_applied_objects(nonpods, applied, profile=self.inputs.profile, workload=self.inputs.workload)
        self.require_deployment_continuity(applied)
        self.store.write('applied-objects.json', applied)
        self.store.write('service-allocations.json', bindings)
        self.reached_gate = 'application_configuration_and_allocations_verified'
        self.observe(kubectl_apply_command(self.identity, self.object_list(self.groups[3])))
        self.reached_gate = 'driver_apply_attempted'
        self.read_until(lambda deadline: self.bind_runtime_inventory(deadline),budget=readiness_budget)
        self.reached_gate = 'all_application_incarnations_ready'
        self.capture_all(final=False)
        self.reached_gate = 'request_free_ready'

    @staticmethod
    def object_list(items):
        return canonical({'apiVersion':'v1','kind':'List','items':items})

    def applied_read(self, items):
        return self.observe(Command(('kubectl','--kubeconfig',self.identity.kubeconfig,
            'get','--filename','-','--output','json'), 10, stdin=self.object_list(items))).stdout_bytes

    def require_deployment_available(self, track, role):
        """Authenticate native owned readiness before the fixed one-second wait."""
        from kil.v3b2_proofs import validate_applied_objects
        desired = [row for row in self.groups[2] if row['kind']=='Deployment'
                   and row['metadata']['namespace']==NAMESPACES[track] and row['metadata']['name']==role]
        if len(desired)!=1:
            raise ValueError('deployment_desired_not_exact')
        raw = self.applied_read(desired)
        validate_applied_objects(desired,raw)
        document = decode(raw)
        row = document['items'][0] if document.get('kind')=='List' else document
        metadata,status = row['metadata'],row['status']
        uid,rv,generation = metadata['uid'],metadata['resourceVersion'],metadata['generation']
        if (type(uid) is not str or not uid or type(rv) is not str or not rv
                or type(generation) is not int or generation<1 or 'deletionTimestamp' in metadata
                or type(status) is not dict):
            raise ValueError('deployment_readiness_identity_invalid')
        identity = (uid,generation)
        key = (track,role)
        if key in self.deployment_bindings and self.deployment_bindings[key]!=identity:
            raise ValueError('deployment_readiness_incarnation_changed')
        self.deployment_bindings.setdefault(key,identity)
        fields = ('observedGeneration','replicas','readyReplicas','availableReplicas')
        present = {field:status[field] for field in fields if field in status}
        if any(type(value) is not int or value<0 for value in present.values()):
            raise ValueError('deployment_readiness_counts_invalid')
        # These native status fields are documented omitempty. Local zero
        # comparisons classify only pending/invalid state; no projected count
        # or observed readiness proof is created from an omitted field.
        observed,replicas,ready,available = (present.get(field,0) for field in fields)
        conditions = status.get('conditions',[])
        if (type(conditions) is not list or any(type(condition) is not dict
                or type(condition.get('type')) is not str or condition.get('status') not in ('True','False','Unknown')
                for condition in conditions)
                or len({condition['type'] for condition in conditions})!=len(conditions)):
            raise ValueError('deployment_readiness_conditions_invalid')
        available_rows = [condition for condition in conditions if condition['type']=='Available']
        if len(available_rows)>1 or observed>generation or ready>replicas or available>ready or replicas>1:
            raise ValueError('deployment_readiness_state_invalid')
        if (len(present)!=4 or len(available_rows)!=1 or observed!=generation
                or (replicas,ready,available)!=(1,1,1) or available_rows[0]['status']!='True'):
            raise ReadPending('authenticated_owned_deployment_not_available')

    def require_deployment_continuity(self, payload):
        """Join all nine native application Deployments to readiness identities.

        A newly coherent Deployment/ReplicaSet chain is not authority to replace
        an already selected UID or generation. This helper never adopts rows.
        """
        expected = {(track,role) for track in TRACKS for role in ('authz','envoy','target')}
        if set(self.deployment_bindings)!=expected:
            raise ValueError('readiness_deployment_bindings_not_complete')
        try:
            document = decode(payload)
            if (type(document) is not dict or document.get('apiVersion')!='v1'
                    or document.get('kind')!='List' or type(document.get('items')) is not list):
                raise ValueError('deployment_continuity_source_not_native_list')
            selected = {}
            namespaces = {namespace:track for track,namespace in NAMESPACES.items()}
            for row in document['items']:
                if row['kind']!='Deployment' or row['metadata'].get('namespace') not in namespaces:
                    continue
                metadata = row['metadata']
                key = (namespaces[metadata['namespace']],metadata['name'])
                uid,generation = metadata['uid'],metadata['generation']
                if (row['apiVersion']!='apps/v1' or key not in expected or key in selected
                        or type(uid) is not str or not uid or type(generation) is not int or generation<1
                        or 'deletionTimestamp' in metadata or (uid,generation)!=self.deployment_bindings[key]):
                    raise ValueError('readiness_deployment_identity_changed_or_unbound')
                selected[key] = (uid,generation)
            if set(selected)!=expected:
                raise ValueError('deployment_continuity_inventory_not_exact')
        except (KeyError,TypeError,AttributeError,IndexError):
            raise ValueError('deployment_continuity_identity_malformed') from None

    @staticmethod
    def accepted_loaded_kil_source(raw):
        kil = next(row for row in ACCEPTED_IMAGES if row.role == 'kil')
        match = re.fullmatch(rb'Loaded image ID: (sha256:[0-9a-f]{64})\n',raw)
        if match is None or match[1].decode() not in (kil.config_digest,kil.target_digest):
            raise ValueError('native_loaded_kil_identity_not_exact_accepted')
        return match[1].decode()

    def require_loaded_kil_source(self):
        if self.loaded_kil_stdout is None or self.loaded_kil_stdout_name is None:
            raise ValueError('native_loaded_kil_binding_changed_or_unavailable')
        name = self.loaded_kil_stdout_name.removesuffix('.stdout')
        match = re.fullmatch(r'command-([0-9]{4,})',name)
        if match is None:
            raise ValueError('native_loaded_kil_receipt_name_invalid')
        keys = ('st_dev','st_ino','st_mode','st_uid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        def identity(row):
            if (row.st_mode != stat.S_IFREG|0o600 or row.st_uid != os.geteuid()
                    or row.st_nlink != 1 or not 0 <= row.st_size <= 8*1024*1024):
                raise ValueError('native_loaded_kil_receipt_not_owned_private_regular')
            return tuple(getattr(row,key) for key in keys)
        with ExitStack() as owned:
            receipts = []
            self.store._bound(b'',1)
            for suffix in ('.stdout','.stderr'):
                receipt_name = name+suffix
                fd = os.open(receipt_name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.store._directory)
                owned.callback(os.close,fd)
                before = identity(os.fstat(fd))
                raw = self.private_read(receipt_name)
                receipts.append((receipt_name,fd,before,raw))
            if (receipts[0][3] != self.loaded_kil_stdout
                    or self.accepted_loaded_kil_source(receipts[0][3]) != self.loaded_kil_source):
                raise ValueError('native_loaded_kil_binding_changed_or_unavailable')
            sequence = int(match[1])
            stdout_hash = sha256(self.loaded_kil_stdout).hexdigest()
            stderr_hash = sha256(receipts[1][3]).hexdigest()
            if self.command_checksums.get(name) != {'stdout':stdout_hash,'stderr':stderr_hash}:
                raise ValueError('native_loaded_kil_receipt_checksum_changed')
            journal_fd = os.open('journal.jsonl',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.store._directory)
            owned.callback(os.close,journal_fd)
            journal_identity = identity(os.fstat(journal_fd))
            journal_raw = self.private_read('journal.jsonl')
            receipts.append(('journal.jsonl',journal_fd,journal_identity,journal_raw))
            journal = [decode(line) for line in journal_raw.split(b'\n')[:-1]]
            intents = [row['details'] for row in journal if row['event']=='command_intent'
                       and row['details'].get('sequence') == sequence]
            terminals = [row['details'] for row in journal if row['event']=='command_terminal'
                         and row['details'].get('sequence') == sequence]
            expected_intent = {'sequence':sequence,'argv':['docker','load'],'env':dict(self.docker_env),
                               'mutating':True,'timeout_s':300,'stdin_sha256':sha256(self.inputs.archive).hexdigest()}
            expected_terminal = {'sequence':sequence,'returncode':0,
                                 'stdout_sha256':stdout_hash,'stderr_sha256':stderr_hash}
            if (intents != [expected_intent] or terminals != [expected_terminal]
                    or type(intents[0]['sequence']) is not int or type(intents[0]['mutating']) is not bool
                    or type(terminals[0]['sequence']) is not int or type(terminals[0]['returncode']) is not int):
                raise ValueError('native_loaded_kil_requires_exact_successful_receipt')
            self.store._bound(b'',1)
            for receipt_name,fd,before,raw in receipts:
                if os.pread(fd,len(raw)+1,0) != raw:
                    raise ValueError('native_loaded_kil_receipt_bytes_changed')
            for receipt_name,fd,before,raw in receipts:
                if (identity(os.fstat(fd)) != before
                        or identity(os.stat(receipt_name,dir_fd=self.store._directory,follow_symlinks=False)) != before):
                    raise ValueError('native_loaded_kil_receipt_identity_changed')
            return self.loaded_kil_source

    def import_application_images(self):
        accepted = {row.role:row for row in ACCEPTED_IMAGES}
        commands = docker_image_import_commands(self.identity, self.inputs.archive,
            accepted['kil'].config_digest, accepted['kil'].requested_image, accepted['envoy'].requested_image)
        loaded = self.observe(commands[0])
        source = self.accepted_loaded_kil_source(loaded.stdout_bytes)
        name = 'command-%04d.stdout'%self.sequence
        if self.private_read(name) != loaded.stdout_bytes:
            raise ValueError('native_loaded_kil_receipt_changed')
        self.loaded_kil_source, self.loaded_kil_stdout, self.loaded_kil_stdout_name = source, loaded.stdout_bytes, name
        commands = docker_image_import_commands(self.identity, self.inputs.archive,
            source, accepted['kil'].requested_image, accepted['envoy'].requested_image)
        for command in commands[1:3]: self.observe(command)
        envoy_modern = False
        for command, image in zip(commands[3:], ACCEPTED_IMAGES, strict=True):
            modern = self.require_host_application_image(self.observe(command).stdout_bytes,image)
            if image.role == 'envoy': envoy_modern = modern
        if envoy_modern:
            self.envoy_platform_pull_ready = True
            self.observe(ExploratoryEnvoyPlatformCommand(self.runtime))
            if not self.require_host_application_image(self.observe(commands[4]).stdout_bytes,accepted['envoy']):
                raise ValueError('envoy_platform_pull_changed_modern_index_identity')
        for image in ACCEPTED_IMAGES:
            self.observe(kind_load_command(self.identity, image.requested_image))

    def require_host_application_image(self, raw, image):
        rows = decode(raw, maximum=1048576)
        if type(rows) is not list or len(rows)!=1 or type(rows[0]) is not dict:
            raise ValueError('native_application_image_identity_not_accepted')
        value = rows[0]
        identifier = value.get('Id')
        modern = identifier == image.target_digest
        descriptor = value.get('Descriptor')
        expected_types = (('application/vnd.oci.image.manifest.v1+json',) if image.role == 'kil'
                          else ('application/vnd.oci.image.index.v1+json',
                                'application/vnd.docker.distribution.manifest.list.v2+json'))
        if ((modern or descriptor is not None) and (type(descriptor) is not dict
                or descriptor.get('digest') != image.target_digest
                or descriptor.get('mediaType') not in expected_types
                or type(descriptor.get('size')) is not int or not 0 < descriptor['size'] <= 8*1024*1024)):
            raise ValueError('native_application_image_descriptor_not_accepted')
        if (identifier not in (image.config_digest,image.target_digest)
                or (image.role == 'kil' and identifier != self.require_loaded_kil_source())):
            raise ValueError('native_application_image_identity_not_accepted')
        tags, digests = value.get('RepoTags'), value.get('RepoDigests')
        expected_digests = ({'kil.local/kil-v3b2@'+image.target_digest} if image.role == 'kil'
                            else {image.requested_image,image.requested_image.removeprefix('docker.io/')})
        if (type(tags) is not list or type(digests) is not list
                or any(type(row) is not str for row in tags+digests)
                or len(set(digests)) != len(digests) or not set(digests) <= expected_digests
                or (tags != [image.requested_image] if image.role == 'kil' else
                    tags not in ([],[image.requested_image],[image.requested_image.removeprefix('docker.io/')]) or not digests)):
            raise ValueError('native_application_image_references_not_accepted')
        return modern

    def require_node_alias_removal_receipts(self):
        """Authenticate exact durable zero terminals before explaining cache copies."""
        if not self.node_alias_removals: return ()
        keys = ('st_dev','st_ino','st_mode','st_uid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        def identity(row):
            if (row.st_mode != stat.S_IFREG|0o600 or row.st_uid != os.geteuid()
                    or row.st_nlink != 1 or not 0 <= row.st_size <= 8*1024*1024):
                raise ValueError('node_alias_removal_receipt_not_private_regular')
            return tuple(getattr(row,key) for key in keys)
        proofs = self.node_alias_removals
        with ExitStack() as owned:
            receipts = []
            self.store._bound(b'',1)
            def read(name):
                fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.store._directory)
                owned.callback(os.close,fd)
                before = identity(os.fstat(fd)); raw = self.private_read(name)
                receipts.append((name,fd,before,raw)); return raw
            for role,row,sequence,dispatch,stdout,stderr in proofs:
                if row not in self.node_alias_states[role].import_rows:
                    raise ValueError('node_alias_removal_not_original_association')
                expected = ExploratoryNodeAliasCommand(self.runtime,self.identity,role,'remove',row[0])
                if dispatch != (expected.argv,expected.env,None,10,True):
                    raise ValueError('node_alias_removal_dispatch_changed')
                name = 'command-%04d'%sequence
                if read(name+'.stdout') != stdout or read(name+'.stderr') != stderr:
                    raise ValueError('node_alias_removal_receipt_bytes_changed')
            journal = [decode(line) for line in read('journal.jsonl').split(b'\n')[:-1]]
            for role,row,sequence,dispatch,stdout,stderr in proofs:
                expected_intent = {'sequence':sequence,'argv':list(dispatch[0]),'env':dict(dispatch[1]),
                                   'mutating':True,'timeout_s':10,'stdin_sha256':None}
                expected_terminal = {'sequence':sequence,'returncode':0,
                                     'stdout_sha256':sha256(stdout).hexdigest(),'stderr_sha256':sha256(stderr).hexdigest()}
                intents = [entry['details'] for entry in journal if entry['event']=='command_intent' and entry['details'].get('sequence')==sequence]
                terminals = [entry['details'] for entry in journal if entry['event']=='command_terminal' and entry['details'].get('sequence')==sequence]
                if (intents != [expected_intent] or terminals != [expected_terminal]
                        or type(terminals[0]['returncode']) is not int):
                    raise ValueError('node_alias_removal_requires_durable_zero_terminal')
            self.store._bound(b'',1)
            for name,fd,before,raw in receipts:
                if os.pread(fd,len(raw)+1,0) != raw: raise ValueError('node_alias_removal_receipt_drift')
            for name,fd,before,raw in receipts:
                if (identity(os.fstat(fd)) != before or identity(os.stat(name,dir_fd=self.store._directory,follow_symlinks=False)) != before):
                    raise ValueError('node_alias_removal_receipt_identity_drift')
            if self.node_alias_removals != proofs: raise ValueError('node_alias_removal_binding_changed')
            return tuple((role,row) for role,row,*rest in proofs)

    def capture_node_alias_state(self, role, table=None):
        from kil.hf_exploratory_node_aliases import analyse_aliases
        from kil.v3b2_proofs import node_images_argv
        def capture(supplied):
            inspection = self.observe(ExploratoryNodeAliasCommand(self.runtime,self.identity,role,'inspect'))
            if len(inspection.stdout_bytes)+len(inspection.stderr_bytes)>16384 or inspection.stderr_bytes:
                raise ValueError('node_alias_config_inspection_bound_or_stderr')
            if supplied is None:
                result = self.observe(Command(node_images_argv(self.identity.node_container_id),10,env=self.docker_env))
                if len(result.stdout_bytes)+len(result.stderr_bytes)>262144 or result.stderr_bytes:
                    raise ValueError('node_alias_table_bound_or_stderr')
                supplied = result.stdout_bytes
            removed = self.require_node_alias_removal_receipts()
            return analyse_aliases(supplied,inspection.stdout_bytes,role,removed=tuple(row for owner,row in removed if owner == role))
        first = capture(table)
        second = capture(None)
        if first != second:
            raise ValueError('node_alias_config_table_changed_during_capture')
        return second

    def repair_node_application_aliases(self, table):
        states = {role:self.capture_node_alias_state(role,table) for role in ('kil','envoy')}
        names = [row[0] for state in states.values() for row in state.import_rows]
        if len(names) != len(set(names)):
            raise ValueError('node_alias_import_association_ambiguous')
        self.node_alias_states = states
        self.store.write('node-alias-repair.initial.json',canonical({
            'schema':'kil.hf-node-alias-repair.v1','run_digest':self.run_digest,
            'node_container_id':self.identity.node_container_id,
            'cluster_incarnation_uid':self.identity.cluster_incarnation_uid,
            'initial_table_sha256':sha256(table).hexdigest(),
            'states':{role:asdict(state) for role,state in states.items()}}))
        for role,state in states.items():
            if not state.canonical_present:
                self.observe(ExploratoryNodeAliasCommand(self.runtime,self.identity,role,'tag'))
        for role,state in states.items():
            for row in state.import_rows:
                self.observe(ExploratoryNodeAliasCommand(self.runtime,self.identity,role,'remove',row[0]))
        if self.node_alias_removals:
            self.observe(ExploratoryNodeAliasCommand(self.runtime,self.identity,'envoy','restart'))

    def require_node_alias_unchanged(self, command):
        if self.node_alias_states is None:
            raise ValueError('node_alias_initial_config_proof_unavailable')
        self.guard_cluster()
        if command.operation == 'restart':
            expected = {(role,row) for role,initial in self.node_alias_states.items() for row in initial.import_rows}
            if set(self.require_node_alias_removal_receipts()) != expected or not expected:
                raise ValueError('node_alias_restart_requires_all_successful_owned_removals')
            captures = []
            for _ in range(2):
                states = {role:self.capture_node_alias_state(role) for role in self.node_alias_states}
                for role,state in states.items():
                    if (state.config_row != self.node_alias_states[role].config_row or state.import_rows
                            or not state.canonical_present or not state.canonical_reported):
                        raise ValueError('node_alias_restart_owned_targets_not_closed')
                captures.append(states)
            if captures[0] != captures[1]:
                raise ValueError('node_alias_restart_targets_changed_during_capture')
            self.require_node_alias_removal_receipts()
            return
        state = self.capture_node_alias_state(command.role)
        initial = self.node_alias_states[command.role]
        if state.config_row != initial.config_row:
            raise ValueError('node_alias_config_target_changed')
        if command.operation == 'tag':
            if state.canonical_present:
                raise ValueError('node_alias_tag_destination_already_present')
        else:
            expected = next(row for row in initial.import_rows if row[0] == command.import_ref)
            if (expected not in state.import_rows or not state.canonical_present
                    or not state.canonical_reported):
                raise ValueError('node_alias_import_association_changed_or_canonical_unproved')

    def prove_node_application_aliases(self):
        from kil.v3b2_node_image_references import ExpectedNodeImage, node_image_inspect_argv, validate_node_image_references
        from kil.v3b2_proofs import RawObservation, node_images_argv
        expected = tuple(ExpectedNodeImage(row.role, row.requested_image, row.config_digest, row.target_digest,
            'application/vnd.oci.image.' + ('manifest' if row.role=='kil' else 'index') + '.v1+json',
            (row.requested_image,) if row.role=='kil' else (),
            ('kil.local/kil-v3b2@'+row.target_digest,) if row.role=='kil' else (row.requested_image,),
            row.config_digest) for row in ACCEPTED_IMAGES)
        command = Command(node_images_argv(self.identity.node_container_id), 10, env=self.docker_env)
        result = self.observe(command)
        if len(result.stdout_bytes)+len(result.stderr_bytes)>262144 or result.stderr_bytes:
            raise ValueError('node_images_bound_or_stderr')
        self.repair_node_application_aliases(result.stdout_bytes)
        command = Command(node_images_argv(self.identity.node_container_id),10,env=self.docker_env)
        result = self.observe(command)
        if len(result.stdout_bytes)+len(result.stderr_bytes)>262144 or result.stderr_bytes:
            raise ValueError('node_images_bound_or_stderr')
        observation = RawObservation('node_images',command.argv,command.env,result.returncode,
                                     result.stdout_bytes,result.stderr_bytes)
        inspections = []
        for index, image in enumerate(expected):
            command = Command(node_image_inspect_argv(self.identity.node_container_id, image.query_reference),
                              10, env=self.docker_env)
            result = self.observe(command)
            if len(result.stdout_bytes)+len(result.stderr_bytes)>16384:
                raise ValueError('node_image_inspect_bound')
            inspections.append(RawObservation('cri_image_'+str(index), command.argv, command.env,
                                             result.returncode, result.stdout_bytes, result.stderr_bytes))
        proof = validate_node_image_references(identity=self.identity, docker_config=dict(self.docker_env)['DOCKER_CONFIG'],
            expected_images=expected, inspections=tuple(inspections), node_images=observation)
        self.aliases = {binding.expected.role:binding for binding in proof.bindings}
        self.store.write('node-application-image-proof.json', canonical({'bindings':[asdict(row) for row in proof.bindings],
            'observation_sha256':list(proof.observation_sha256), 'runtime_contract_complete':False,
            'platform_image_provenance_verified':False}))

    def bind_runtime_inventory(self, deadline):
        from kil.v3b2_proofs import RUNTIME_RESOURCES
        from kil.v3b2_runtime_ownership import validate_runtime_ownership
        from kil.v3b2_generated_kil_pod_configuration import validate_generated_kil_pod_configuration
        from kil.v3b2_driver_pod_configuration import validate_driver_pod_configuration
        if time.monotonic() >= deadline:
            raise ValueError('readiness_deadline_exceeded')
        raw = self.observe(Command(('kubectl','--kubeconfig',self.identity.kubeconfig,'get',RUNTIME_RESOURCES,
                                   '--all-namespaces','--output','json'), 10)).stdout_bytes
        self.require_deployment_continuity(raw)
        ownership = validate_runtime_ownership(profile=self.inputs.profile, workload=self.inputs.workload,
            rendered_objects=self.rendered, owned_identity=self.identity, runtime_objects=raw)
        validate_generated_kil_pod_configuration(ownership=ownership)
        document = decode(raw)
        app_pods = [row for row in document['items'] if row['kind']=='Pod'
                    and row['metadata'].get('namespace') in NAMESPACES.values()]
        drivers = [{key:value for key,value in row.items() if key!='status'} for row in app_pods
                   if row['metadata']['name']=='driver']
        validate_driver_pod_configuration(profile=self.inputs.profile, workload=self.inputs.workload,
            rendered_objects=self.rendered, owned_identity=self.identity, pods=drivers)
        anchors, placements, pending = {}, [], False
        if len(app_pods)!=12:
            raise ValueError('application_pod_cardinality_not_exact')
        # Latch every selected identity before any pending observation can end
        # this attempt. A later read may complete it, never replace it.
        for track in TRACKS:
            for role in ROLES:
                rows = [row for row in app_pods if row['metadata']['namespace']==NAMESPACES[track]
                        and row['metadata']['labels'].get('kil.dev/role')==role]
                if len(rows)!=1:
                    raise ValueError('application_pod_selection_not_exact')
                metadata = rows[0]['metadata']
                selected = tuple(metadata[key] for key in ('namespace','name','uid'))
                if any(type(value) is not str or not value for value in selected):
                    raise ValueError('application_selection_unbound')
                key = (track,role)
                if key in self.selected_pods and self.selected_pods[key]!=selected:
                    raise ValueError('selected_application_pod_replaced')
                self.selected_pods.setdefault(key,selected)
        for track in TRACKS:
            for role in ROLES:
                rows = [row for row in app_pods if row['metadata']['namespace']==NAMESPACES[track]
                        and row['metadata']['labels'].get('kil.dev/role')==role]
                if len(rows)!=1:
                    raise ValueError('application_pod_selection_not_exact')
                pod = rows[0]
                try:
                    bound = self.bind_ready_pod(pod, track, role)
                except ReadPending:
                    # Validate/latch the other initial native incarnations too;
                    # one starting driver must not hide an already-running CID.
                    pending = True
                    continue
                if (track,role) in self.anchors:
                    same_incarnation(self.anchors[(track,role)],bound)
                else:
                    self.anchors[(track,role)] = bound
                if pod['spec'].get('nodeName')!='kil-v3-lab-control-plane':
                    raise ValueError('application_node_placement_not_exact')
                if role!='driver':
                    endpoint = self.read_endpoint(track, role)
                    if (endpoint!=self.endpoints[(track,role)] or endpoint['target_uid']!=bound['uid']
                            or endpoint['addresses']!=[pod['status'].get('podIP')]):
                        raise ValueError('readiness_pod_endpoint_binding_changed')
                anchors[(track,role)] = bound
                placements.append({'track':track,'role':role,**bound,'node':pod['spec']['nodeName'],
                                   'pod_ip':pod['status'].get('podIP')})
        if pending:
            raise ReadPending('authenticated_application_inventory_not_ready')
        nodes = [row for row in document['items'] if row['kind']=='Node']
        if len(nodes)!=1 or nodes[0]['metadata']['name']!='kil-v3-lab-control-plane':
            raise ValueError('observed_node_not_exact')
        self.environment['observed_node_info'] = nodes[0]['status']['nodeInfo']
        self.platform_images = [{'namespace':row['metadata']['namespace'], 'pod':row['metadata']['name'],
            'spec_images':[container.get('image') for field in ('containers','initContainers') for container in row['spec'].get(field,[])],
            'status_images':[{'name':container.get('name'),'image':container.get('image'),'imageID':container.get('imageID'),
                              'containerID':container.get('containerID')}
                             for field in ('containerStatuses','initContainerStatuses') for container in row.get('status',{}).get(field,[])],
            'verified':False} for row in document['items'] if row['kind']=='Pod' and row not in app_pods]
        self.placements = placements
        # Bracket readiness against fresh same-role Pod and EndpointSlice reads,
        # not merely the wide source's earlier Ready state.
        for track in TRACKS:
            self.require_current_track(track)
        self.store.write('runtime-ready-source.json', raw)
        return anchors

    def bind_ready_pod(self, pod, track, role):
        status = pod['status']
        if status['phase']=='Pending':
            rows = status['containerStatuses']
            if type(rows) is not list or len(rows)!=1 or type(rows[0]) is not dict:
                raise ValueError('pending_container_inventory_invalid')
            observed = rows[0]
            requested = pod['spec']['containers'][0]['image']
            waiting = observed.get('state',{}).get('waiting')
            if (observed.get('name')!=role or observed.get('ready') is not False
                    or type(observed.get('restartCount')) is not int or observed['restartCount']!=0
                    or observed.get('containerID')!='' or observed.get('imageID')!=''
                    or observed.get('image')!=requested or set(observed['state'])!={'waiting'}
                    or type(waiting) is not dict or waiting.get('reason')!='ContainerCreating'
                    or set(waiting)-{'reason','message'}
                    or ('message' in waiting and type(waiting['message']) is not str)
                    or pod['spec'].get('nodeName')!='kil-v3-lab-control-plane'
                    or (track,role) in self.anchors):
                raise ValueError('pending_container_not_known_startup')
            # Validate the unchanged metadata/spec with the existing partial
            # safety binder. This internal eligibility probe is never retained
            # or used as a runtime identity/provenance observation.
            probe = deepcopy(pod)
            alias = self.aliases['envoy' if role=='envoy' else 'kil']
            probe['status']['phase']='Running'
            probe['status']['containerStatuses'][0].update(
                image=alias.runtime_image,imageID=alias.image_ref,
                containerID='containerd://'+'0'*64,state={'running':{}},ready=False)
            self.bind_application_pod(probe,track,role,require_ready=False)
            raise ReadPending('authenticated_container_creating')
        bound = self.bind_application_pod(pod,track,role,require_ready=False)
        if (track,role) in self.anchors:
            same_incarnation(self.anchors[(track,role)],bound)
        else:
            self.anchors[(track,role)] = bound
        if status['containerStatuses'][0]['ready'] is not True:
            raise ReadPending('bound_running_container_not_ready')
        return bound

    def bind_application_pod(self, pod, track, role, *, completed=False, require_ready=True):
        image_role = 'envoy' if role == 'envoy' else 'kil'
        alias = self.aliases[image_role]
        requested = (self.inputs.workload.envoy_image_digest if role == 'envoy'
                     else 'kil.local/kil-v3b2:sha256-' + self.inputs.workload.kil_image_id[7:])
        return case.bind_pod(pod, track=track, role=role, run_id=self.inputs.workload.run_id,
                             requested_image=requested, runtime_image=alias.runtime_image,
                             image_ref=alias.image_ref, completed=completed, require_ready=require_ready)

    def read_pod(self, track, role, **kwargs):
        anchor = self.anchors[(track, role)]
        command = (kubectl_driver_pod_command(self.identity, NAMESPACES[track]) if role == 'driver'
                   else kubectl_source_pod_command(self.identity, NAMESPACES[track], anchor['pod']))
        return decode(self.observe(replace(command, timeout_s=10)).stdout_bytes)

    def current_pod(self, track, role, *, completed=False, require_ready=True):
        raw = self.read_pod(track, role)
        bound = self.bind_application_pod(raw, track, role, completed=completed, require_ready=require_ready)
        same_incarnation(self.anchors[(track, role)], bound)
        return bound

    def read_endpoint(self, track, role):
        from kil.v3b2_inventory import parse_ready_endpoint_slice
        result = self.observe(replace(kubectl_ready_endpoint_command(self.identity, NAMESPACES[track], role), timeout_s=10))
        endpoint, uid = parse_ready_endpoint_slice(result.stdout_bytes,
                                expected_namespace=NAMESPACES[track], expected_service=role)
        if len(endpoint.addresses) != 1:
            raise ValueError('endpoint_not_exactly_one')
        bound = {'addresses': list(endpoint.addresses), 'target_uid': uid}
        key = (track,role)
        if key in self.endpoint_bindings and self.endpoint_bindings[key]!=bound:
            raise ValueError('selected_endpoint_binding_changed')
        self.endpoint_bindings.setdefault(key,bound)
        return bound

    def require_current_track(self, track):
        for role in ROLES:
            raw = self.read_pod(track, role)
            bound = self.bind_application_pod(raw, track, role)
            same_incarnation(self.anchors[(track, role)], bound)
            if role != 'driver':
                endpoint = self.read_endpoint(track, role)
                if (endpoint != self.endpoints[(track, role)] or endpoint['target_uid'] != bound['uid']
                        or endpoint['addresses'] != [raw['status'].get('podIP')]):
                    raise ValueError('endpoint_or_pod_placement_changed')

    def require_current_driver(self, track):
        return self.current_pod(track, 'driver')

    def read_until(self, operation, *, seconds=300, attempts=60, retry_errors=(ReadPending,), budget=None):
        """Retry only bounded read observations, never mutation commands."""
        if retry_errors!=(ReadPending,):
            raise ValueError('only_explicit_read_pending_may_retry')
        deadline = time.monotonic() + seconds if budget is None else budget.deadline
        last_error = None
        interval = 5 if budget is not None else .5
        previous_deadline = self._read_deadline
        self._read_deadline = deadline if previous_deadline is None else min(deadline,previous_deadline)
        try:
            for index in range(attempts):
                if time.monotonic() >= deadline or (budget is not None and budget.attempts>=60):
                    break
                if budget is not None:
                    budget.attempts+=1
                try:
                    value = operation(deadline)
                    if time.monotonic() >= deadline:
                        raise ValueError('readiness_deadline_exceeded')
                    return value
                except retry_errors as error:
                    last_error = error
                if index + 1 < attempts and time.monotonic() + interval < deadline:
                    time.sleep(interval)
            raise ValueError('bounded_readiness_inconclusive: %s' % last_error)
        finally:
            self._read_deadline = previous_deadline

    def require_complete_driver(self, track):
        def read(deadline):
            raw = self.read_pod(track, 'driver')
            completed = raw['status']['phase'] == 'Succeeded'
            bound = self.bind_application_pod(raw, track, 'driver', completed=completed, require_ready=False)
            same_incarnation(self.anchors[(track, 'driver')], bound)
            if not completed:
                raise ReadPending('bound_driver_still_running')
            return bound
        return self.read_until(read, seconds=10, attempts=20, retry_errors=(ReadPending,))

    def instruction_phase(self):
        check_source(self.repository, self.source_commit)
        for track in TRACKS:
            self.reached_gate = track + '_preinstruction'
            self.guard_cluster()
            self.require_current_track(track)
            self.require_current_driver(track)
            if self.mode == 'rehearsal':
                self.observe(kubectl_attach_command(self.identity, NAMESPACES[track], b''))
                self.reached_gate = track + '_empty_eof_attached'
            else:
                payload = case.instruction(track, self.run_digest, int(time.time()))
                self.reached_gate = track + '_request_attempt'
                self.ssh.guard()
                self.require_retained_ssh_controls()
                self.store.send_once(track, payload,
                    lambda: self.observe(kubectl_attach_command(self.identity, NAMESPACES[track], payload)).stdout_bytes)
                self.require_complete_driver(track)
                self.reached_gate = track + '_driver_complete'
                self.freeze_track(track)
                self.capture_track(track, final=True)
                self.reached_gate = track + '_complete_join'
        if self.mode == 'rehearsal':
            for track in TRACKS:
                self.require_complete_driver(track)
            self.freeze_all()
            self.capture_all(final=True)
        self.reached_gate = 'complete_capture'

    def freeze_track(self, track):
        if track in self.frozen:
            return
        if track in self.freeze_attempted:
            raise ValueError('drain_already_attempted')
        before = self.current_pod(track, 'envoy')
        drain, stats = kubectl_envoy_quiesce_commands(self.identity, NAMESPACES[track], before['pod'])
        self.freeze_attempted.add(track)
        drain_raw = decode(self.observe(drain).stdout_bytes)
        if type(drain_raw) is not dict or set(drain_raw) != {'drain_requested'} or drain_raw['drain_requested'] is not True:
            raise ValueError('drain_not_confirmed')
        def quiescent(deadline):
            self.current_pod(track,'envoy',require_ready=False)
            raw = decode(self.observe(replace(stats, timeout_s=10)).stdout_bytes)
            if type(raw) is not dict or set(raw) != {'listener_refused', 'stats'} or raw['listener_refused'] is not True or type(raw['stats']) is not list:
                raise ValueError('quiescence_not_confirmed')
            active = {}
            for row in raw['stats']:
                if type(row) is not dict or type(row.get('name')) is not str:
                    raise ValueError('invalid_stats_record')
                if row['name'] in ACTIVE_GAUGES:
                    if set(row) != {'name','value'} or row['name'] in active or type(row.get('value')) is not int or row['value'] < 0:
                        raise ValueError('active_or_duplicate_gauge')
                    active[row['name']] = row['value']
            if set(active) != ACTIVE_GAUGES:
                raise ValueError('missing_active_gauge')
            if any(value!=0 for value in active.values()):
                raise ReadPending('bound_envoy_active_gauges_not_zero')
            return raw
        self.read_until(quiescent, seconds=10, attempts=20)
        after = self.current_pod(track, 'envoy', require_ready=False)
        same_incarnation(before, after)
        self.frozen.add(track)

    def freeze_all(self):
        for track in TRACKS:
            self.freeze_track(track)

    def read_source(self, track, role):
        namespace, pod = NAMESPACES[track], self.anchors[(track, role)]['pod']
        if role in ('driver', 'envoy'):
            command = Command(('kubectl', '--kubeconfig', self.identity.kubeconfig,
                               'logs', 'pod/' + pod, '--namespace', namespace, '--limit-bytes=1048576'), 10)
        else:
            command = replace(kubectl_source_read_command(self.identity, namespace, pod, role), timeout_s=10)
        return self.observe(command).stdout_bytes

    def capture_track(self, track, final=False):
        sources, metadata = {}, {}
        for role in ROLES:
            options = {'completed': final and role == 'driver',
                       'require_ready': not (role == 'envoy' and track in self.frozen)}
            before = self.bind_application_pod(self.read_pod(track, role), track, role, **options)
            same_incarnation(self.anchors[(track, role)], before)
            payload = self.read_source(track, role)
            second = self.read_source(track, role)
            after = self.bind_application_pod(self.read_pod(track, role), track, role, **options)
            same_incarnation(self.anchors[(track, role)], after)
            bound = case.frozen_source(before, after, payload, second)
            source_role = 'decision' if role == 'authz' else role
            sources[source_role] = bound.pop('records')
            stage = 'final' if final else 'ready'
            filename = '%s-%s-%s.jsonl' % (track, role, stage)
            self.store.write(filename, payload)
            metadata[source_role] = {**bound, 'file': filename}
            self.store.record('source_capture', {'track':track, 'role':source_role, **metadata[source_role]})
        joined = case.join(sources, track=track, run_id=self.inputs.workload.run_id,
                           request_free=self.mode == 'rehearsal' or not final)
        if final and self.mode == 'action' and joined['observed'][0] == 'permit':
            expected_upstream = self.endpoints[(track, 'target')]['addresses'][0] + ':8080'
            if len(sources['envoy']) != 1 or sources['envoy'][0]['upstream_host'] != expected_upstream:
                raise ValueError('permit_upstream_not_exact_ready_target')
        self.source_metadata[track + ('-final' if final else '-ready')] = metadata
        if final:
            self.results[track] = joined
        return joined

    def capture_all(self, final=False):
        return [self.capture_track(track, final=final) for track in TRACKS]

    def clear_owned_reset_store(self, observed):
        if (not self.started_pristine or self.profile_binding is None or not self.profile_delete_completed
                or absent(self.paths.document(), observed) is not True):
            raise ValueError('owned_reset_store_cleanup_not_authorized')
        row = observed['store']
        if row is None:
            require_pristine(self.paths)
            return
        if _read(self.paths.store) != row:
            raise ValueError('owned_reset_store_changed')
        self.store.write('owned-reset-store.json', canonical(observed))
        self.store.record('reset_store_remove_intent', {'path': str(self.paths.store), 'identity': row,
            'sha256':sha256(bytes.fromhex(row['hex'])).hexdigest()})
        with _parent(self.paths.store) as parent:
            if parent is None or _read(self.paths.store) != row:
                raise ValueError('owned_reset_store_changed')
            actual = os.stat(self.paths.store.name, dir_fd=parent, follow_symlinks=False)
            if {key:getattr(actual, {'device':'st_dev','inode':'st_ino','mode':'st_mode'}[key])
                    for key in ('device','inode','mode')} != {key:row[key] for key in ('device','inode','mode')}:
                raise ValueError('owned_reset_store_identity_changed')
            os.unlink(self.paths.store.name, dir_fd=parent)
            os.fsync(parent)
        self.store.record('reset_store_remove_complete', {'path':str(self.paths.store)})
        require_pristine(self.paths)

    def ensure_runtime_snapshot(self):
        if self.runtime_snapshot_attempted:
            if self.runtime_observations is None:
                raise ValueError('runtime_snapshot_failed_no_retry')
            return
        self.runtime_snapshot_attempted = True
        self.runtime_observations = snapshot_runtime(self.store,self.runtime)

    def cleanup(self):
        """Capture once before native teardown, including safely observable failures."""
        try:
            try:
                self.ensure_runtime_snapshot()
            except Exception as error:
                self.manual_recovery = self.profile_attempted
                self.error = ('%s; runtime snapshot: %s' % (self.error or '',error))[:4096]
            else:
                self._cleanup_native()
        finally:
            try:
                self.runtime_leftovers = observe_runtime_leftovers(self.runtime)
                self.store.write('runtime-leftovers.json',canonical(self.runtime_leftovers))
            except Exception as error:
                self.runtime_leftovers = None
                self.runtime_leftovers_error = str(error)[:4096]
                self.error = ('%s; runtime leftovers unknown: %s' % (self.error or '',error))[:4096]

    def _cleanup_native(self):
        """No resource discovery is deletion authority; refuse on any drift."""
        if not self.profile_attempted:
            return
        if self.profile_binding is None or (self.cluster_attempted and
                (self.identity.node_container_id is None or self.identity.cluster_incarnation_uid is None)):
            self.manual_recovery = True
            return
        try:
            if self.cluster_attempted and not self.cluster_removed:
                self.observe(kind_delete_command(self.identity))
                self.guard_profile()
                if self.endpoint_rows():
                    raise ValueError('owned_endpoint_not_empty_after_delete')
                # Empty exact private endpoint plus unchanged VM is authority;
                # neither a Kind return code nor an unknown API error is absence.
                unavailable = self.observe(Command(('kubectl', '--kubeconfig', self.identity.kubeconfig,
                    'get','namespace','kube-system','--output','json'), 10), allow_failure=True)
                if unavailable.returncode == 0:
                    raise ValueError('cluster_api_still_reachable')
                self.cluster_removed = True
            self.observe(Command(('colima','stop','--profile','kil-v3-lab'), 300,
                                 mutating=True))
            self.guard_profile(stopped=True)
            self.profile_stopped = True
            self.observe(Command(('colima','delete','--profile','kil-v3-lab','--force','--data'),
                                 300, mutating=True))
            post_delete = capture(self.paths)
            if absent(self.paths.document(), post_delete) is not True:
                raise ValueError('profile_absence_not_confirmed')
            if not self.profile_delete_succeeded:
                raise ValueError('ssh_delete_transition_without_successful_native_delete')
            self.ssh.begin_deleted()
            self.private_inventory_absent()
            if absent(self.paths.document(), post_delete) is not True:
                raise ValueError('profile_absence_not_confirmed')
            self.retain_ssh_controls('deleted')
            if absent(self.paths.document(), capture(self.paths)) is not True:
                self.ssh.refuse()
                raise ValueError('profile_absence_not_confirmed')
            self.ssh.finish_deleted()
            self.profile_delete_completed = True
            self.clear_owned_reset_store(post_delete)
            self.require_foreign_preserved()
            self.owned_teardown = True
        except Exception as error:
            self.manual_recovery = not self.profile_delete_completed
            self.error = ('%s; cleanup: %s' % (self.error or '', error))[:4096]
            try:
                chain = self.retain_cleanup_refusal(error)
                self.error = (self.error+'; causes: '+' -> '.join(row['message'] for row in chain))[:4096]
            except Exception as diagnostic_error:
                self.error = (self.error+'; cleanup diagnostics: '+str(diagnostic_error))[:4096]

    def retain_cleanup_refusal(self, error):
        """Diagnostic observations grant no adoption or deletion authority."""
        keys = ('device','inode','mode','uid','nlink','size','mtime_ns','ctime_ns')
        def identity(row):
            return dict(zip(keys,(row.st_dev,row.st_ino,row.st_mode,row.st_uid,row.st_nlink,
                                  row.st_size,row.st_mtime_ns,row.st_ctime_ns)))
        chain, current, seen = [], error, set()
        while current is not None and len(chain)<8 and id(current) not in seen:
            seen.add(id(current)); chain.append({'type':type(current).__name__,'message':str(current)[:1024]})
            current = current.__cause__ if current.__cause__ is not None else current.__context__
        result = {'schema':'kil.hf-cleanup-refusal.v1','run_digest':self.run_digest,
                  'exception_chain':chain,'profile_stop_succeeded':self.profile_stop_succeeded,
                  'profile_delete_succeeded':self.profile_delete_succeeded,
                  'ssh_state':self.ssh.state,'instance_directory':{},'instance_file':{}}
        try:
            if self.ssh.instance_anchor is not None:
                fd, expected = self.ssh.instance_anchor
                result['instance_directory'] = {'identity':identity(os.fstat(fd)),
                                               'bound_identity':list(expected),'entries':os.listdir(fd)}
                if platform.system() == 'Darwin':
                    import fcntl
                    result['instance_directory']['retained_path'] = os.fsdecode(fcntl.fcntl(fd,50,bytes(1024)).split(b'\0',1)[0])
        except Exception as observation_error:
            result['instance_directory']['error'] = str(observation_error)[:1024]
        try:
            control = self.ssh.instance
            if control is None or control.fd is None:
                control = None if self.ssh._removed_instance is None else self.ssh._removed_instance[0]
            if control is not None and control.fd in self.ssh._owned:
                before = os.fstat(control.fd)
                value = {'identity':identity(before),'bound_identity':dict(zip(keys,control.identity))}
                result['instance_file'] = value
                if stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= 16*1024:
                    raw = self.ssh._bytes(control.fd,before.st_size)
                    value.update({'sha256':sha256(raw).hexdigest(),'byte_count':len(raw),
                                  'identity_after':identity(os.fstat(control.fd))})
        except Exception as observation_error:
            result['instance_file']['error'] = str(observation_error)[:1024]
        self.store.write('cleanup-refusal.json',canonical(result))
        return chain

    def private_inventory_absent(self):
        self._ssh_inventory_active = True
        try:
            self._private_inventory_absent()
        except BaseException:
            self.ssh.refuse()
            raise
        finally:
            self._ssh_inventory_active = False

    def _private_inventory_absent(self):
        self.runtime.guard()
        self.ssh.guard()
        colima = _read(self.paths.colima,directory_only=True)
        if colima is None or not set(colima['entries']) <= {'_lima','_store','_templates','ssh_config'}:
            raise ValueError('private_colima_profile_roster_unknown')
        before = capture_roster(self.paths)
        result = self.observe(Command(('colima','list','--json'),10))
        after = capture_roster(self.paths)
        if require_complete(decode_inventory(result.stdout_bytes,
                returncode=result.returncode,stderr=result.stderr_bytes),before,after):
            raise ValueError('private_profile_absence_not_confirmed')
        colima = _read(self.paths.colima,directory_only=True)
        if colima is None or not set(colima['entries']) <= {'_lima','_store','_templates','ssh_config'}:
            raise ValueError('private_colima_profile_roster_unknown')
        self.ssh.guard()

    def private_read(self, name):
        """Read an unchanged bounded regular top-level run file by retained fd."""
        self.store._bound(b'', 1)
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=self.store._directory)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > 8 * 1024 * 1024 or before.st_nlink != 1:
                raise ValueError('private_sum_not_regular_bounded_file')
            chunks, count = [], 0
            while count <= before.st_size:
                chunk = os.read(descriptor, min(65536, before.st_size + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk); count += len(chunk)
            after = os.fstat(descriptor)
            current = os.stat(name, dir_fd=self.store._directory, follow_symlinks=False)
            keys = ('st_dev','st_ino','st_size','st_mode','st_mtime_ns','st_ctime_ns')
            if count != before.st_size or any(getattr(before,key)!=getattr(after,key)
                                             or getattr(before,key)!=getattr(current,key) for key in keys):
                raise ValueError('private_sum_source_changed')
            return b''.join(chunks)
        finally:
            os.close(descriptor)

    def retained_checksums(self):
        """Bound retained regular files, including tool-created private scratch.

        This checks retained evidence, not transient native filesystem capacity.
        PrivateStore accounting covers managed writes only. No scratch is erased.
        """
        self.store._bound(b'', 1)
        result, total = {}, 0
        def scan(parent, prefix):
            nonlocal total
            initial = sorted(os.listdir(parent))
            for name in initial:
                if name in ('lock','profile.lock','SHA256SUMS'):
                    continue
                relative = prefix+name
                before = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if stat.S_ISDIR(before.st_mode):
                    descriptor = os.open(name, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW, dir_fd=parent)
                    try:
                        retained = os.fstat(descriptor)
                        if (retained.st_dev,retained.st_ino)!=(before.st_dev,before.st_ino):
                            raise ValueError('retained_directory_changed')
                        scan(descriptor, relative+'/')
                        after = os.stat(name, dir_fd=parent, follow_symlinks=False)
                        if (before.st_dev,before.st_ino,before.st_mode)!=(after.st_dev,after.st_ino,after.st_mode):
                            raise ValueError('retained_directory_changed')
                    finally:
                        os.close(descriptor)
                    continue
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_uid!=os.geteuid()
                        or before.st_size>8*1024*1024):
                    raise ValueError('retained_file_not_regular_owned_or_bounded: '+relative)
                total += before.st_size
                if total>256*1024*1024:
                    raise ValueError('retained_aggregate_bound')
                descriptor = os.open(name, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=parent)
                try:
                    actual = os.fstat(descriptor)
                    keys = ('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')
                    if any(getattr(actual,key)!=getattr(before,key) for key in keys):
                        raise ValueError('retained_file_changed')
                    digest, count = sha256(), 0
                    while count<=before.st_size:
                        chunk = os.read(descriptor,min(65536,before.st_size+1-count))
                        if not chunk: break
                        digest.update(chunk); count+=len(chunk)
                    after = os.fstat(descriptor)
                    current = os.stat(name,dir_fd=parent,follow_symlinks=False)
                    if count!=before.st_size or any(getattr(before,key)!=getattr(after,key)
                            or getattr(before,key)!=getattr(current,key) for key in keys):
                        raise ValueError('retained_file_changed')
                    result[relative]=digest.hexdigest()
                finally:
                    os.close(descriptor)
            if initial!=sorted(os.listdir(parent)):
                raise ValueError('retained_directory_entries_changed')
        scan(self.store._directory, '')
        self.store._bound(b'', 1)
        return result

    def execute(self):
        try:
            self.setup()
            self.instruction_phase()
        except Exception as error:
            self.error = ('%s: %s' % (type(error).__name__, error))[:4096]
            self.reached_gate = 'inconclusive_at_' + self.reached_gate
        finally:
            self.cleanup()
        journal = [decode(line) for line in self.private_read('journal.jsonl').split(b'\n')[:-1]]
        request_count = sum(row['event']=='request_intent' for row in journal)
        if request_count > (0 if self.mode=='rehearsal' else 3):
            raise ValueError('request_intent_bound_exceeded')
        retained_error = None
        try:
            self.retained_checksums()
        except (ValueError, OSError) as error:
            retained_error = str(error)[:4096]
            self.error = ('%s; retained files: %s' % (self.error or '',retained_error))[:4096]
        complete = self.error is None and self.reached_gate=='complete_capture' and self.owned_teardown is True
        report = {'schema_version':'kil.hf-exploratory-report.v1', 'label':case.LABEL,
            'mode':self.mode, 'run_id':self.inputs.workload.run_id, 'source_commit':self.source_commit,
            'profile_sha256':sha256(self.inputs.profile_bytes).hexdigest(),
            'input_manifest_sha256':sha256(self.inputs.manifest_bytes).hexdigest(),
            'archive_sha256':sha256(self.inputs.archive).hexdigest(), 'tool_commitments':self.inputs.tool_records,
            'command_checksums':self.command_checksums, 'source_checksums':self.source_metadata,
            'reached_gate':self.reached_gate, 'status':'complete' if complete else 'inconclusive',
            'error':self.error, 'request_intent_count':request_count, 'request_attempt_count':len(self.store.attempts),
            'joined_results':[self.results[track] for track in TRACKS if track in self.results],
            'observed_environment':self.environment, 'pod_placement_and_images':self.placements,
            'unverified_platform_images':self.platform_images,
            'profile_resources':{'requested':{'cpus':4,'memory_gib':8,'data_disk_gib':60,'root_disk_gib':20,
                                 'vm_type':'VZ','host_mounts':[],'application_published_ports':[]},
                                 'actual_capture_file':'profile-created.json' if self.profile_binding is not None else None,
                                 'actual_creation_bound':self.profile_binding is not None},
            'profile_binding':self.profile_binding, 'profile_delete_completed':self.profile_delete_completed,
            'cluster_removed':self.cluster_removed, 'owned_teardown':self.owned_teardown,
            'paths':{'runtime':str(self.runtime.path),'receipt':str(self.store.path),
                     'actual_default_home':str(self.paths.home)},
            'runtime_observations':self.runtime_observations,
            'runtime_observations_file':'runtime-observations.json' if self.runtime_observations is not None else None,
            'runtime_snapshot_attempted':self.runtime_snapshot_attempted,
            'runtime_leftovers':self.runtime_leftovers,'runtime_leftovers_error':self.runtime_leftovers_error,
            'filesystem_fully_removed':False,
            'manual_recovery':self.manual_recovery, 'foreign_global_original':self.original_foreign,
            'foreign_global_observations':self.foreign_observations,
            'retained_files_error':retained_error,
            'retained_evidence_limits':{'per_regular_file_bytes':8*1024*1024,'aggregate_regular_bytes':256*1024*1024,
                                      'transient_native_capacity_controlled':False},
            'platform_image_provenance_verified':False, 'full_kind_calico_acceptance':False,
            'claim_exclusions':['full HF prevention','all eight HF phases','original HF exploit',
                'performance','NetworkPolicy enforcement','no bypass','V3B2 acceptance','V4','V3C']}
        self.store.write('report.json', canonical(report))
        synopsis = '\n'.join([case.LABEL, '', 'Mode: '+self.mode+'. Status: '+report['status']+'.',
            'Reviewed LOCAL source: '+self.source_commit+'. No origin/main synchronization claim.',
            'Observed environment: '+canonical(self.environment).decode().strip(),
            'Observed Pod placement, IP, requested/runtime image and imageRef: '+canonical(self.placements).decode().strip(),
            'Requested profile resources (not invented runtime observation): '+canonical(report['profile_resources']['requested']).decode().strip(),
            'Actual creation-bound profile: '+canonical({'binding':self.profile_binding,'capture_file':report['profile_resources']['actual_capture_file']}).decode().strip(),
            'Input commitments: '+canonical({key:report[key] for key in ('profile_sha256','input_manifest_sha256','archive_sha256','tool_commitments')}).decode().strip(),
            'Source commitments: '+canonical(self.source_metadata).decode().strip(),
            'Observed joined results and actual reasons: '+canonical(report['joined_results']).decode().strip(),
            'Docker daemon version is UNOBSERVED; Docker CLI output is recorded separately.',
            'Owned teardown (native-owned-teardown, not filesystem-fully-removed): '+str(self.owned_teardown)+'. Manual recovery: '+str(self.manual_recovery)+'.',
            'Runtime namespace, immutable receipt, actual default home: '+canonical(report['paths']).decode().strip(),
            'Finite runtime observations: '+str(report['runtime_observations_file'])+'.',
            'Partial runtime leftovers (not absence or acceptance): '+canonical({'observation':self.runtime_leftovers,'unknown_error':self.runtime_leftovers_error}).decode().strip(),
            'Canonical KTP citation: https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff',
            'No platform-image provenance, full Kind/Calico acceptance, causal HF prevention,',
            'NetworkPolicy enforcement, no-bypass, exploit, or performance claim is established.', ''])
        self.store.write('synopsis.md', synopsis.encode())
        if retained_error is None:
            checksums = self.retained_checksums()
            self.store.write('SHA256SUMS', ''.join(digest+'  '+name+'\n'
                              for name,digest in sorted(checksums.items())).encode())
        return report
