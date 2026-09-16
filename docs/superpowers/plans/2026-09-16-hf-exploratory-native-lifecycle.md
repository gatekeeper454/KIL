# Exploratory HF native lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rehearse one exact owned Kind/Calico lifecycle without requests, then run one fresh three-track harmless action and retain a private explicitly exploratory report.

**Architecture:** The separate lifecycle composes reviewed input, IO and case units, existing closed command factories and native ownership parsers. Ownership is established from an absent profile and empty fresh Docker endpoint, then bound to filesystem/VM, node and kube-system incarnations before subsequent mutations. Request uncertainty never invokes another instruction; cleanup only operates on exact still-bound resources.

**Tech Stack:** Python 3.12, pinned Colima/Lima/Docker/Kind/kubectl, existing manifest renderer, application node-image reference proof, unittest test-owned observations.

---

Approved design: docs/superpowers/specs/2026-09-16-hf-exploratory-kind-calico-design.md. Dependencies: reviewed hf_exploratory_inputs.py, hf_exploratory_io.py and hf_exploratory_case.py. Do not call strict V3B2Controller lifecycle or publication verifier, modify any strict file/completion flag, resume platform provenance or use global contexts for mutation. Existing isolated worktree retained. Root executes native commands only after all code reviews.

## File responsibilities and fixed interfaces

- Create src/kil/hf_exploratory_native.py: exact native ownership and lifecycle, bounded readiness, source capture, report.
- Create tools/hf_exploratory_kind.py: explicit reviewed-source CLI, two fresh ordered runs, no retry/recovery/publication option.
- Create tests/test_hf_exploratory_native.py: test-owned ownership/command and failure gates, no native tools.

Native lifecycle constructor is `ExploratoryLifecycle(repository, inputs, store, runner, source_commit, mode)`; mode exact `rehearsal` or `action`. Runner is the reviewed BoundedRunner in real execution, injectable only for tests. `execute()` returns a private report dict and must attempt conservative scoped cleanup in finally; it never retries mutating operations. `guard_profile(stopped=False)`, `guard_cluster()`, `observe(command, allow_failure=False)`, `capture_all(final=False)`, `cleanup()` have the exact responsibilities below. Separate pure helpers bind node observation and compare live readiness anchors. All exceptions are retained as inconclusive report with actual reached gate; cleanup ambiguity is explicit and never recast as success.

## Task 1: Exact owned authority and durable command receipts

- [ ] Write test-owned node and replacement fixtures first. Initial absent module must fail assertions, not import errors:

```python
import importlib
import importlib.util
import unittest
from copy import deepcopy


def node_fixture():
    return [{'Id': 'a' * 64, 'Name': '/kil-v3-lab-control-plane',
        'Config': {'Labels': {'io.x-k8s.kind.cluster': 'kil-v3-lab', 'io.x-k8s.kind.role': 'control-plane'}},
        'State': {'Running': True}}]


class ExploratoryNativeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_native'))
        self.module = importlib.import_module('kil.hf_exploratory_native')

    def test_exact_node_binding(self):
        self.assertEqual(self.module.bind_node(node_fixture()), 'a' * 64)
        for change in [lambda x: x[0].update(Id='short'), lambda x: x[0].update(Name='/foreign'),
                       lambda x: x[0]['Config']['Labels'].update({'io.x-k8s.kind.cluster': 'foreign'}),
                       lambda x: x[0]['State'].update(Running=False), lambda x: x.append(deepcopy(x[0]))]:
            value = node_fixture()
            change(value)
            with self.assertRaises(ValueError):
                self.module.bind_node(value)

    def test_readiness_anchor_rejects_replacement_not_completion_rv(self):
        original = {'namespace': 'kil-v3-baseline', 'pod': 'driver', 'role': 'driver',
                    'uid': 'pod-1', 'container_id': 'containerd://' + 'a' * 64, 'resource_version': '1',
                    'requested_image': 'fixed', 'runtime_image': 'fixed', 'image_ref': 'config'}
        self.module.same_incarnation(original, {**original, 'resource_version': '2'})
        for field in ('uid', 'container_id', 'requested_image', 'namespace', 'pod', 'image_ref'):
            with self.assertRaises(ValueError):
                self.module.same_incarnation(original, {**original, field: 'replacement'})


if __name__ == '__main__':
    unittest.main()
```

- [ ] Run RED:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -m unittest tests.test_hf_exploratory_native -v
```

Expected two missing-module assertion failures; no native tool.

- [ ] Implement complete ownership helpers:

```python
import re


def bind_node(value):
    if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
        raise ValueError('owned_node_cardinality')
    row = value[0]
    if (type(row.get('Id')) is not str or re.fullmatch('[0-9a-f]{64}', row['Id']) is None
            or row.get('Name') != '/kil-v3-lab-control-plane'
            or row.get('Config', {}).get('Labels', {}).get('io.x-k8s.kind.cluster') != 'kil-v3-lab'
            or row.get('Config', {}).get('Labels', {}).get('io.x-k8s.kind.role') != 'control-plane'
            or row.get('State', {}).get('Running') is not True):
        raise ValueError('owned_node_identity')
    return row['Id']


def same_incarnation(original, observed):
    fields = ('namespace', 'pod', 'role', 'uid', 'container_id', 'requested_image', 'runtime_image', 'image_ref')
    if any(original.get(key) != observed.get(key) for key in fields):
        raise ValueError('application_incarnation_changed')
```

- [ ] Add the receipt dispatcher below, then failing-first test-owned runner tests asserting intent is present before dispatch, stdout/stderr retained on nonzero status, no dispatch after failed intent fsync, no command retry and no arbitrary grammar bypass. The production class uses this body; `sequence` starts at zero. Read-only receipts also retained. Private filenames are fixed counter-derived names, never native names.

```python
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tempfile
from kil.hf_exploratory_io import PrivateStore
from kil.v3b2_journal import Command, OwnedIdentity, kind_delete_command
from kil.v3b2_controller import CommandResult


class ExploratoryReceiptTests(ExploratoryNativeTests):
    def test_durable_receipt_precedes_dispatch_and_retains_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PrivateStore(Path(directory).resolve() / 'run')
            self.addCleanup(store.close)
            calls = []
            def run(command):
                self.assertIn(b'command_intent', store.journal.read_bytes())
                calls.append(command)
                return CommandResult(7, 'prefix', 'error', b'prefix', b'error')
            lifecycle = self.module.ExploratoryLifecycle.__new__(self.module.ExploratoryLifecycle)
            lifecycle.sequence, lifecycle.store = 0, store
            lifecycle.runner = SimpleNamespace(run=run)
            lifecycle.authorize_mutation = Mock()
            with self.assertRaises(ValueError):
                lifecycle.observe(Command(('colima', 'version'), 1))
            self.assertEqual(len(calls), 1)
            self.assertEqual((store.path / 'command-0001.stdout').read_bytes(), b'prefix')
            self.assertEqual((store.path / 'command-0001.stderr').read_bytes(), b'error')

    def test_failed_intent_never_dispatches(self):
        lifecycle = self.module.ExploratoryLifecycle.__new__(self.module.ExploratoryLifecycle)
        lifecycle.sequence = 0
        lifecycle.store = SimpleNamespace(record=Mock(side_effect=OSError('durability')))
        lifecycle.runner = SimpleNamespace(run=Mock())
        with self.assertRaises(OSError):
            lifecycle.observe(Command(('colima', 'version'), 1))
        lifecycle.runner.run.assert_not_called()

    def test_unknown_cluster_identity_never_authorizes_deletion(self):
        lifecycle = self.module.ExploratoryLifecycle.__new__(self.module.ExploratoryLifecycle)
        lifecycle.cluster_removed, lifecycle.cluster_delete_attempted = False, False
        lifecycle.guard_cluster = Mock(side_effect=ValueError('replacement'))
        identity = OwnedIdentity('kil-v3-lab', 'unix:///tmp/kil-v3-lab/docker.sock', 'kil-v3-lab',
            '/tmp/kil-v3-lab/kubeconfig', 'cluster-1', 'a' * 64)
        with self.assertRaises(ValueError):
            lifecycle.authorize_mutation(kind_delete_command(identity))
        self.assertIs(lifecycle.cluster_delete_attempted, False)
```

```python
def observe(self, command, allow_failure=False):
    command.__post_init__()
    if command.mutating:
        self.authorize_mutation(command)
    self.sequence += 1
    name = f'command-{self.sequence:04d}'
    self.store.record('command_intent', {'sequence': self.sequence, 'argv': list(command.argv),
        'env': [list(pair) for pair in command.env], 'mutating': command.mutating,
        'stdin_sha256': None if command.stdin is None else sha256(command.stdin).hexdigest()})
    result = self.runner.run(command)
    out = self.store.write(name + '.stdout', result.stdout_bytes)
    err = self.store.write(name + '.stderr', result.stderr_bytes)
    self.store.record('command_terminal', {'sequence': self.sequence, 'returncode': result.returncode,
        'stdout_sha256': out, 'stderr_sha256': err})
    if result.returncode != 0 and not allow_failure:
        raise ValueError('command_failed_' + str(self.sequence))
    return result
```

Mutation dispatch must enforce state centrally, not rely on each caller remembering
a guard. Start/profile/cluster attempt flags are latched before intent, never reset
for replay. The initial state has no bindings, no attempts, no removed/stopped flags.
Bindings are set only after authenticated native observations, not command status.

```python
def authorize_mutation(self, command):
    if command.argv == colima_start_command().argv:
        if self.profile_attempted:
            raise ValueError('profile_start_never_repeats')
        require_pristine(self.paths)
        self.require_original_foreign_state()
        self.profile_attempted = True
    elif command.argv[:3] == ('kind', 'create', 'cluster'):
        if self.cluster_attempted:
            raise ValueError('cluster_create_never_repeats')
        self.guard_profile()
        self.require_empty_owned_endpoint()
        self.cluster_attempted = True
    elif command.argv[:3] == ('kind', 'delete', 'cluster'):
        if self.cluster_removed or self.cluster_delete_attempted:
            raise ValueError('cluster_delete_never_repeats')
        self.guard_cluster()
        self.cluster_delete_attempted = True
    elif command.argv[:2] == ('colima', 'stop'):
        if self.profile_stop_attempted or self.cluster_attempted and not self.cluster_removed:
            raise ValueError('profile_stop_without_bound_cluster_absence')
        self.guard_profile()
        self.profile_stop_attempted = True
    elif command.argv[:2] == ('colima', 'delete'):
        if self.profile_delete_attempted or not self.profile_stopped:
            raise ValueError('profile_delete_without_stopped_binding')
        self.guard_profile(stopped=True)
        self.profile_delete_attempted = True
    else:
        self.guard_cluster()
```

Add separate one-shot set for every remaining mutating argv+stdin commitment so
failed apply/load/drain/attach cannot be dispatched again during cleanup or polling.
The empty rehearsal EOF and each exact one-shot attach are distinct track commands;
action instructions still have the stricter PrivateStore TRACKS/uncertainty latch.

## Task 2: Exact fresh setup and readiness, no requests

- [ ] Add lifecycle setup through failing-first fixture tests. The command table below is exhaustive; construct every command with existing `kil.v3b2_journal` factories/Command grammar, not arbitrary argv. Before each mutation after start call guard_profile; after cluster UID binding guard_cluster before every application/image-load/driver/drain mutation. `guard_profile` calls profile_state.unchanged(document,capture(paths),binding,stopped=...). `guard_cluster` additionally inspects exact named node ID/labels, requires endpoint's entire container roster consists only of that exact node ID, and reads kube-system UID equal to bound value. Node replacement, unknown extra container or UID drift means no mutation/deletion.

| Order | Exact command/input | Gate and retained authority |
|---|---|---|
| 1 | `git rev-parse HEAD`; `git status --porcelain` | Equal explicit reviewed-source 40 lower hex, clean; no origin/main requirement |
| 2 | absolute accepted Docker/Kind/kubectl version argv; `colima version`; `limactl --version` | Exact accepted version outputs and pinned Colima/Lima; sanitize execution env |
| 3 | `docker context show`; `colima list --json` bracketed by capture_roster | Save global context, complete foreign rows; profile_state.require_pristine before intent |
| 4 | colima_start_command exact fixed argv | Add only private DOCKER_CONFIG/TMPDIR; never activate default or host mounts |
| 5 | profile_state.creation_binding and complete roster | Bind concrete dirs/config bytes/disks/lock; if unbound start failure stop manual recovery |
| 6 | private Docker `container ls --all --no-trunc --format {{json .}}` | Entire fresh endpoint empty before cluster creation |
| 7 | kind_create_command | Private kind-config/kubeconfig, disableDefaultCNI true, exact node pin inserted into sole control-plane node |
| 8 | private Docker inspect exact kil-v3-lab-control-plane and entire container roster; private kubectl get namespace kube-system JSON | Bind node ID and kube-system UID; failed create may be inspected for exact bound cleanup but never blindly deleted |
| 9 | docker_image_import_commands with retained archive/config, fixed content tag and Envoy root digest | Both inspect Ids equal ACCEPTED_IMAGES configs, expected RepoTags/RepoDigests membership |
| 10 | kind_load_command twice exact accepted refs | Accepted KIL and Envoy content only |
| 11 | authenticated node image CRI inspect commands and node-store images check | Existing validate_node_image_references proves two application alias branches; no platform-image proof |
| 12 | kubectl_apply_calico_command exact private vendored bytes | Retained profile checksum verified before start and rechecked before apply; no upstream download/substitution |
| 13 | two kubectl_calico_workload_command reads | Canonicalize duplicate-safe decoded native response before existing parse_calico_runtime_workload; desired/ready 1/1 |
| 14 | kubectl_apply_command canonical Lists: namespaces, policies, then non-Pod workloads | Default-deny applied and read back BEFORE workloads/drivers; no manifest alteration |
| 15 | nine kubectl_workload_ready_command reads and nine kubectl_ready_endpoint_command reads | Each service EndpointSlice ready one, exact Pod UID/IP, retained responses |
| 16 | read applied exact rendered non-Pod objects via `get --filename - --output json` | Existing validate_applied_objects with profile/workload proves source config/service allocations; save returned allocation bindings |
| 17 | kubectl_apply_command List of three standalone driver Pods | Never add published endpoint, production credential or host driver |
| 18 | wide runtime inventory exact existing resource string | Twelve exact track/role Pods and fresh Deployment/ReplicaSet ownership chains; bind_pod ready with source-derived image aliases |
| 19 | bounded double source reads bracketed by Pod identities | Driver readiness record only; no decision/Envoy/target records across all three tracks |

Pure preparation snippets:

```python
config = decode(render_kind_config(inputs.profile))
config['nodes'][0]['image'] = inputs.profile.kind_node_image
store.write('kind-config.yaml', canonical(config))
calico = read_regular(repository / inputs.profile.calico_manifest_path, 8 * 1024 * 1024)
verify_bytes(calico, inputs.profile.calico_manifest_sha256, len(calico))
store.write('calico-v3.32.0.yaml', calico)
rendered = decode(render_objects(inputs.profile, inputs.workload))['items']
groups = [[item for item in rendered if item['kind'] == kind] for kind in ('Namespace', 'NetworkPolicy')]
groups += [[item for item in rendered if item['kind'] not in {'Namespace', 'NetworkPolicy', 'Pod'}],
           [item for item in rendered if item['kind'] == 'Pod']]
payloads = [canonical({'apiVersion': 'v1', 'kind': 'List', 'items': group}) for group in groups]
```

Node image proof expected inputs are constructed only from ACCEPTED_IMAGES: KIL root media type application/vnd.oci.image.manifest.v1+json, allowed tag exactly its requested_image, allowed digest kil.local/kil-v3b2@target; Envoy root media application/vnd.oci.image.index.v1+json, no tag, allowed digest exactly its requested_image; saved_container_image is config_digest, not root. Two `RawObservation` labels cri_image_0/cri_image_1 (stdout <=16KiB) and node_images (<=256KiB); exact command env/argv and bound OwnedIdentity feed validate_node_image_references. Save canonical proof bindings, not strict completion flags.

Readiness loops retry READS ONLY: monotonic global setup-readiness deadline 300s, per-read/wait command timeout at most10s (wait itself1s), sleep0.5s max between read sets, <=60 complete attempts. No request/mutation retries. Native errors stop setup rather than weakening a parser. Every command receipt is retained within 256MiB aggregate. Native wide inventory remains an observation of platform software, not a comprehensive platform acceptance proof.

Application ownership selection: select exactly one Pod per track+role, no deleting/restarted Pod or extra application-namespace Pod. App Pod ownerReferences exactly one controlling ReplicaSet; ReplicaSet owner exactly one controlling Deployment with expected role, namespace/run annotation and sole reviewed Pod template; join exact UIDs, confirm Deployment/ReplicaSet desired/ready1 and observedGeneration current. Driver Pod has no owner and exact run annotation. Fixed rendered commands, resources, volumes and safety flags are checked against native Pods, allowing only independently documented API/scheduling/CNI defaults; do not silently strip arbitrary fields. Bind requested/spec image separately from CRI-derived runtime image and ImageRef. A source is read only using the selected exact Pod from the readiness anchor.

Reuse the existing pure partial ownership and application configuration validators
instead of reimplementing their API defaults. These validators do not depend on
admitting independently expected platform image identities and keep their strict
completion flags false. They may check structural platform ownership as a safety
gate; that is not a resumed image-provenance audit or full acceptance claim.

```python
ownership = validate_runtime_ownership(profile=inputs.profile, workload=inputs.workload,
    rendered_objects=render_objects(inputs.profile, inputs.workload), owned_identity=self.identity,
    runtime_objects=inventory.stdout_bytes)
configuration = validate_generated_kil_pod_configuration(ownership=ownership)
driver_configuration = validate_driver_pod_configuration(profile=inputs.profile,
    workload=inputs.workload, rendered_objects=render_objects(inputs.profile, inputs.workload),
    owned_identity=self.identity, pods=[{key: value for key, value in row.items() if key != 'status'}
        for row in decode(inventory.stdout_bytes)['items']
        if row['kind'] == 'Pod' and row['metadata'].get('namespace') in inputs.profile.application_namespaces
        and row['metadata']['name'] == 'driver'])
```

Only the documented status exclusion is used for direct Pod configuration;
retain the complete raw inventory and check its runtime state separately via
bind_pod. No object spec/metadata is flattened or removed to force a match.

## Task 3: Nonreplayable action, frozen capture, conservative cleanup

- [ ] Add failing-first fake runner/source tests for rehearsal sends only empty EOF, action intent before each attach, uncertain first outcome stops tracks two/three, source UID/CID replacement stops later instruction, missing/truncated target prevents denial, quiescence failures inconclusive, foreign/context changes never success, cleanup node/profile replacement never delete. Fake observations belong only to tests and must never be emitted as native run evidence.

Request mode body:

```python
for track, namespace in TRACK_NAMESPACES:
    self.guard_cluster()
    self.require_current_driver(track)
    if self.mode == 'rehearsal':
        self.observe(kubectl_attach_command(self.identity, namespace, b''))
    else:
        payload = instruction(track, self.run_digest, int(time.time()))
        command = kubectl_attach_command(self.identity, namespace, payload)
        self.store.send_once(track, payload, lambda command=command: self.observe(command).stdout_bytes)
        self.require_complete_driver(track)
        self.freeze_track(track)
        self.capture_track(track, final=True)
```

`require_current_driver` rebinds ready Pod and same_incarnation against readiness anchor. `require_complete_driver` bounded read polling requires same UID/CID and exact zero termination, never restarts. `freeze_track` drains the exact track Envoy once, checks native refusal/zero gauges and records frozen track in memory; later final freeze skips those already frozen rather than repeating a mutation. After each action capture_track validates full producer join BEFORE later instruction; ambiguity or missing ledger stops progression. Action terminal freshness uses fixture issued just before durable instruction; no resending expired fixture. Unexpected complete join is reported, not retried.

After all drivers complete/canceled, drain each exact Envoy with kubectl_envoy_quiesce_commands, require raw drain JSON exactly drain_requested true, native listener refusal true and the exact four ACTIVE_GAUGES with integer zero values. Bracket drain by same UID/CID and running state; readiness may turn false due to intended refusal. Read stats up to bounded10s/20read attempts, never repeat drain mutation. Then capture all four source kinds per track: exact authz/target ledger head max1048577 and driver/Envoy logs limit1048576. Reject length>=1MiB, nonzero/overflow/timeout, nonnewline, duplicate/unknown JSON record, or changed bytes/Pod resourceVersion over double-read bracket. Use frozen_source and join; driver completion UID/CID must equal readiness anchor. Store raw source files, source metadata and joined results BEFORE cleanup. No host consequential HTTP.

Cleanup order: validate unchanged profile and guard_cluster; kind_delete_command once; require empty owned endpoint and kube-system unreachable/no named node (absence is not success on an unknown transport); validate profile unchanged; colima stop exact once with private env; validate stopped filesystem binding; colima delete exact --force --data once; require profile_state.absent, complete roster equals original foreign rows, Docker global context equals original and original global Kubernetes config fingerprints unchanged. Do not use Lima disk fallback, broad filesystem deletion or resource discovery-selected targets. If cluster creation was attempted but exact node/UID not bound, refuse Kind deletion and profile deletion as ambiguous/manual recovery. If no cluster attempt occurred and exact profile binding is still valid, scoped profile cleanup is safe. Profile start failure without binding is manual recovery, never a blind delete. Private artifacts remain retained.

Global Kubernetes fingerprint: retain inherited KUBECONFIG value and each canonical nonsymlink file's bounded bytes SHA/size plus absence; default passwd-home/.kube/config if variable absent. Do not create missing .kube, read contexts using global mutation, or rewrite kubeconfigs. Private Kind kubeconfig remains isolated. Preserve global Docker config path via BoundedRunner global context read.

## Task 4: Reviewed source CLI and private result

- [ ] Add failing-first CLI tests: wrong/dirty reviewed revision refuses BEFORE any private path/profile mutation; profile lock conflict refuses; unready rehearsal causes no action instance; action mode not user-selectable alone, no retry/resume option. Parser has three required arguments --reviewed-source, --tools, --kil-archive, absolute paths accepted only through fixed input factory. Script inserts repository/src into import path, exports no mutable acceptance map.

CLI orchestration core:

```python
for mode in ('rehearsal', 'action'):
    nonce = secrets.token_hex(32)
    run_digest = sha256(canonical({'source_commit': source_commit, 'mode': mode, 'nonce': nonce})).hexdigest()
    inputs = verify_inputs(repository, tools, archive_path, run_digest)
    store = PrivateStore(private_parent / ('hf-exploratory-' + run_digest))
    try:
        report = ExploratoryLifecycle(repository, inputs, store, BoundedRunner(repository, inputs), source_commit, mode).execute()
        print(canonical({'mode': mode, 'private_path': str(store.path), 'status': report['status']}).decode(), end='')
    finally:
        store.close()
    if report['status'] != 'complete' or report['owned_teardown'] is not True:
        raise SystemExit(1)
```

Create private_parent exactly repository/.tools/hf-exploratory-private with nofollow canonical ancestry, mode700, existing only regular actual directories. Hold exclusive nonblocking flock on profile.lock (nofollow600) across BOTH runs; release on all exits. This lock excludes this path's launcher, not all external processes; absence/rebinding gates remain mandatory. Source revision/cleanliness checks run again immediately before each native lifecycle start and instruction phase. No edits/staging/commits during native action.

Report exact schema kil.hf-exploratory-report.v1, LABEL text, mode, run_id, source_commit, profile_sha256, input/tool commitments, command/source checksums, reached_gate, status complete/inconclusive, error text bounded4096, actual application incarnations and observed platform image references/IDs, request_intent_count (0 rehearsal; <=3 action), joined observed results, owned_teardown bool, manual_recovery bool, foreign/global-state-preservation observations, platform_image_provenance_verified false, full_kind_calico_acceptance false. Never mark static strict flags true. Generate private report.json, synopsis.md and SHA256SUMS over retained regular run files excluding lock and SHA256SUMS; checksum list itself is written exclusively. Private aggregate256MiB, singlefile8MiB, source1MiB. Explicit exclusions historicalHFprevention/fullincident, all8phases/exploits, NetworkPolicy enforcement/no-bypass, repeats/performance, strictV3b2/V4/V3C. No artifacts/generated/public writer.

- [ ] Run focused GREEN and original strict boundary guards. Independently spec-review then quality-review the entire native unit and source/private report interfaces; original implementer fixes findings through observed RED/GREEN. Commit exact new module/script/test/lineage/readers only after verification.

## Root-owned execution gate

- [ ] Fresh focused combined exploratory suites and strict boundary tests, reader --check and diff checks. Review full exploratory change set independently. Retain a clean reviewed local commit. No publication/merge implied.
- [ ] Run exact CLI with reviewed HEAD and retained accepted paths, escalating owned native filesystem/network execution through command approval. CLI itself runs request-free rehearsal THEN one fresh action; any real readiness mismatch stops, saves inconclusive report and attempts exact scoped teardown. No automatic correction/substitution/retry.
- [ ] Inspect retained report/source checksums and native post-roster. Synopsis states exactly actual environment and KIL decisions, incomplete/failed gates and remaining provenance gap. Append dated final lineage entry. Never claim live result unless complete joined native evidence exists.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
