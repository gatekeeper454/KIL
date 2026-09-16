# V4 Platform Pod Configuration Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce one reconstructable configuration-only proof covering all ten owned platform Pod incarnations in exactly one retained runtime inventory.

**Architecture:** Compose nine existing exact component proof types around an explicit `RuntimeOwnershipProof`. Reconstruct every dependency, require complete ownership and shared-source equality, then compare a canonical ten-binding projection with independently derived ownership coverage. Preserve all component claim limitations and exact-false completion flags.

**Tech Stack:** Python 3.12 standard library, existing frozen/slotted KIL proofs, `unittest`, deterministic Markdown/HTML readers.

---

## Approved inputs, execution environment and boundaries

Approved design: `docs/superpowers/specs/2026-09-16-v4-platform-pod-configuration-composition-design.md` (user approval 2026-09-16).
Planning base: `08bc973` in the existing externally managed detached linked worktree.
Before execution use using-git-worktrees to verify this existing isolation; do not
create another worktree or move user changes unnecessarily.

Use this interpreter in every command below. Run from the repository root:

```bash
export KIL_TEST_PYTHON='/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python'
```

`../../.venv/bin/python` is not valid in this worktree. Quote the interpreter.
Git index writes require the normal escalation because the linked index is
outside the writable root. Full tests require escalation for existing subprocess
and `/dev/fd` checks. Do not interpret sandbox failures as product regressions.

No live Docker, Colima, Kind, kubectl, profile inspection/mutation, collector,
controller, journal, checkpoint, publication or inventory-schema changes.
Do not enable or remove the sixteen deferred lifecycle tests. No platform image
realization, status/readiness, runtime/application completion, V4 completion or
V3C claim. No new skip or relaxed component validation.

## File map

- Create `tests/v3b2_platform_configuration_fixture.py`: test-only merger of independent existing component observations and one shared source; existing-validator dependency builder. No production expected-spec factory calls.
- Create `tests/test_v3b2_platform_pod_configuration.py`: fixture acceptance, aggregate acceptance and adversarial tests.
- Create `src/kil/v3b2_platform_pod_configuration.py`: fixed typed aggregate, bindings, reconstruction, shared-source joins and exact coverage.
- Update this plan's checkboxes at accepted checkpoints only.
- Append dated entries to `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md` for every substantive turn; regenerate its `.htm`. Never rewrite prior entries.
- Regenerate readers for changed/new Markdown, including this plan. No other production files are in scope.

### Task 1: One independently observed inventory accepted by all nine components

**Files:** Create `tests/v3b2_platform_configuration_fixture.py` and `tests/test_v3b2_platform_pod_configuration.py`.

- [ ] **Step 1: Create the test-only combined fixture and dependency builder**

Use the following code. The delta merge compares each component fixture with its
own unchanged ownership baseline, so unrelated sparse rows never overwrite a
previous component's rich observation. Reject conflicting deltas rather than
silently taking last writer. Calico observations come from the checksummed
committed projection plus test-owned serialization; other components use
test-owned literals, not production factories.

```python
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json

from kil.v3b2_runtime_ownership import validate_runtime_ownership
from kil.v3b2_control_plane_manifest_source import validate_control_plane_manifest_source
from kil.v3b2_calico_node_revision import validate_calico_node_revision
from kil.v3b2_kube_proxy_parent_configuration import validate_kube_proxy_parent_configuration
from kil.v3b2_kube_proxy_revision import validate_kube_proxy_revision
from kil.v3b2_coredns_parent_configuration import validate_coredns_parent_configuration
from kil.v3b2_local_path_parent_configuration import validate_local_path_parent_configuration
from kil.v3b2_calico_node_configuration import validate_calico_node_configuration
from kil.v3b2_calico_controller_configuration import validate_calico_controller_configuration
from kil.v3b2_coredns_pod_configuration import validate_coredns_pod_configuration
from kil.v3b2_local_path_pod_configuration import validate_local_path_pod_configuration
from kil.v3b2_kube_proxy_pod_configuration import validate_kube_proxy_pod_configuration
from kil.v3b2_scheduler_mirror_configuration import validate_scheduler_mirror_configuration
from kil.v3b2_etcd_mirror_configuration import validate_etcd_mirror_configuration
from kil.v3b2_kube_apiserver_mirror_configuration import validate_kube_apiserver_mirror_configuration
from kil.v3b2_kube_controller_manager_mirror_configuration import validate_kube_controller_manager_mirror_configuration
from tests.test_v3b2_runtime_ownership import fixture as owner_fixture, encode
from tests.test_v3b2_calico_node_configuration import fixture as node_fixture
from tests.test_v3b2_calico_controller_configuration import fixture as controller_fixture
from tests.test_v3b2_coredns_pod_configuration import fixture as dns_fixture
from tests.test_v3b2_local_path_pod_configuration import fixture as storage_fixture
from tests.test_v3b2_kube_proxy_pod_configuration import fixture as proxy_fixture
from tests.test_v3b2_scheduler_mirror_configuration import fixture as scheduler_fixture
from tests.test_v3b2_etcd_mirror_configuration import fixture as etcd_fixture
from tests.test_v3b2_kube_apiserver_mirror_configuration import (
    api_document as apiserver_fixture, disk_pod as apiserver_disk,
    yaml_bytes, MATCHED_OWNERSHIP_IDENTITY, MATCHED_WORKLOAD,
)
from tests.test_v3b2_kube_controller_manager_mirror_configuration import (
    api_document as manager_fixture, disk_pod as manager_disk,
)
from tests.test_v3b2_control_plane_manifest_source import context, observations, node

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('calico_node', 'calico_controller', 'coredns', 'local_path',
         'kube_proxy', 'scheduler', 'etcd', 'apiserver', 'controller_manager')

def key(row):
    m = row['metadata']
    return row['apiVersion'], row['kind'], m.get('namespace', ''), m['name']

def fixture():
    args = owner_fixture(owned_identity=MATCHED_OWNERSHIP_IDENTITY,
                         workload=MATCHED_WORKLOAD)
    document = json.loads(args['runtime_objects'])
    merged = {key(r): deepcopy(r) for r in document['items']}
    changes = {}
    for build in (node_fixture, controller_fixture, dns_fixture, storage_fixture,
                  proxy_fixture, scheduler_fixture, etcd_fixture,
                  apiserver_fixture, manager_fixture):
        data = build()
        local_args, observed = data[:2]
        baseline = owner_fixture(profile=local_args['profile'],
            workload=local_args['workload'], owned_identity=local_args['owned_identity'])
        old = {key(r): r for r in json.loads(baseline['runtime_objects'])['items']}
        for row in observed['items']:
            identity = key(row)
            if identity in old and row == old[identity]:
                continue
            if identity in changes and changes[identity] != row:
                raise AssertionError(('conflicting independent observations', identity))
            changes[identity] = deepcopy(row)
    merged.update(changes)
    document['items'] = list(merged.values())
    args['runtime_objects'] = encode(document)
    return args, document, source_for(args)

def source_for(args, *, sequence=5):
    owned = args['owned_identity']
    requested = args['profile'].kind_node_image
    run_id = args['workload'].run_id.removeprefix('v3b2-')
    retained = context(owned, kind_node_image=requested, run_id=run_id)
    retained = replace(retained, run_id=run_id, intent_sequence=sequence)
    bracket = node(node_id=owned.node_container_id, requested_image=requested)
    return validate_control_plane_manifest_source(context=retained,
        owned_identity=owned, observations=observations(owned,
            apiserver=yaml_bytes(apiserver_disk()),
            controller=yaml_bytes(manager_disk()), before=bracket, after=bracket))

def rebase_args(args, document, **changes):
    inputs = {name: args[name] for name in ('profile', 'workload', 'owned_identity')}
    inputs.update(changes)
    alternate = owner_fixture(**inputs)
    base = json.loads(alternate['runtime_objects'])
    rows = {key(r): r for r in base['items']}
    for row in document['items']:
        namespace = row['metadata'].get('namespace', '')
        if row['kind'] != 'Namespace' and not namespace.startswith('kil-'):
            rows[key(row)] = deepcopy(row)
    base['items'] = list(rows.values())
    alternate['runtime_objects'] = encode(base)
    return alternate

def dependencies(args, source, *, calico_source=None, calico_projection=None):
    ownership = validate_runtime_ownership(**args)
    raw = ((ROOT / 'deploy/kind/calico-v3.32.0.yaml').read_bytes()
           if calico_source is None else calico_source)
    projection = ((ROOT / 'deploy/kind/calico-v3.32.0.objects.json').read_bytes()
                  if calico_projection is None else calico_projection)
    revision = validate_calico_node_revision(ownership=ownership,
        calico_source=raw, calico_projection=projection)
    proxy_parent = validate_kube_proxy_parent_configuration(ownership=ownership)
    return dict(ownership=ownership,
        calico_node=validate_calico_node_configuration(revision=revision),
        calico_controller=validate_calico_controller_configuration(
            ownership=ownership, calico_source=raw, calico_projection=projection),
        coredns=validate_coredns_pod_configuration(
            parent=validate_coredns_parent_configuration(ownership=ownership)),
        local_path=validate_local_path_pod_configuration(
            parent=validate_local_path_parent_configuration(ownership=ownership)),
        kube_proxy=validate_kube_proxy_pod_configuration(
            revision=validate_kube_proxy_revision(parent=proxy_parent)),
        scheduler=validate_scheduler_mirror_configuration(ownership=ownership),
        etcd=validate_etcd_mirror_configuration(ownership=ownership),
        apiserver=validate_kube_apiserver_mirror_configuration(ownership=ownership, source=source),
        controller_manager=validate_kube_controller_manager_mirror_configuration(
            ownership=ownership, source=source))
```

- [ ] **Step 2: Add the fixture acceptance test and execute it**

```python
import unittest
from tests.v3b2_platform_configuration_fixture import (
    fixture, dependencies, NAMES, source_for, rebase_args,
)

class PlatformFixtureTest(unittest.TestCase):
    def test_all_components_accept_one_inventory_without_readiness(self):
        args, _, source = fixture()
        values = dependencies(args, source)
        self.assertEqual(sum(len(values[n].bindings) for n in NAMES), 10)
        self.assertEqual(len(values['coredns'].bindings), 2)
        for n in NAMES:
            values[n].__post_init__()
            self.assertIs(values[n].runtime_contract_complete, False)
```

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$KIL_TEST_PYTHON" -m unittest tests.test_v3b2_platform_pod_configuration.PlatformFixtureTest -v`

Expected: one passing test; all existing validators accept the merged inventory.
If a dependency fails, use systematic-debugging. Correct test-owned observations
only after identifying the conflicting literal/relationship; do not change or
weaken production contracts. Any substantive specification incompatibility
requires coordinator review before continuing.

- [ ] **Step 3: Review fixture independence, append lineage and commit**

Confirm none of the fixture imports calls a production expected-spec factory to
create observed configurations. Run specification then quality review of fixture
and dependency builder; record exact outcomes and any corrections. Append lineage,
regenerate/check readers, run `git diff --check`, then commit the two test files
and lineage/readers as `test: compose independent platform configuration fixture`.

### Task 2: Typed ten-Pod aggregate with complete reconstruction

**Files:** Create `src/kil/v3b2_platform_pod_configuration.py`; modify `tests/test_v3b2_platform_pod_configuration.py`.

- [ ] **Step 1: Add acceptance tests before the module exists**

Use importlib in test setup so Task 1 still runs independently:

```python
from dataclasses import replace
import importlib
import importlib.util

class PlatformCompositionTest(unittest.TestCase):
    def setUp(self):
        module = 'kil.v3b2_platform_pod_configuration'
        self.assertIsNotNone(importlib.util.find_spec(module), 'aggregate missing')
        self.m = importlib.import_module(module)
        self.args, self.document, self.source = fixture()
        self.values = dependencies(self.args, self.source)

    def test_ten_bindings_retention_replay_and_false_flags(self):
        proof = self.m.validate_platform_pod_configuration(**self.values)
        self.assertEqual(len(proof.bindings), 10)
        self.assertEqual(proof.bindings, tuple(sorted(proof.bindings)))
        self.assertEqual(sum(b.component == 'coredns' for b in proof.bindings), 2)
        self.assertEqual(len({(b.namespace, b.pod_name) for b in proof.bindings}), 10)
        self.assertEqual(len({b.pod_uid for b in proof.bindings}), 10)
        for name, value in self.values.items():
            self.assertIs(getattr(proof, name), value)
        self.assertEqual(replace(proof), proof)
        self.assertIs(proof.runtime_contract_complete, False)
        self.assertIs(proof.full_application_contract_complete, False)
```

Run the focused module. Expected RED: `aggregate missing`, not fixture failure.

- [ ] **Step 2: Implement the full fixed aggregate module**

The following is the complete implementation shape. Fixed descriptors describe
the nine explicit proof inputs; they are not an extensible registry.

```python
from dataclasses import dataclass
import json
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof
from kil.v3b2_driver_pod_configuration import _uid, _rv
from kil.v3b2_calico_node_configuration import CalicoNodeConfigurationProof
from kil.v3b2_calico_controller_configuration import CalicoControllerConfigurationProof
from kil.v3b2_coredns_pod_configuration import CoreDNSPodConfigurationProof
from kil.v3b2_local_path_pod_configuration import LocalPathPodConfigurationProof
from kil.v3b2_kube_proxy_pod_configuration import KubeProxyPodConfigurationProof
from kil.v3b2_scheduler_mirror_configuration import SchedulerMirrorConfigurationProof
from kil.v3b2_etcd_mirror_configuration import EtcdMirrorConfigurationProof
from kil.v3b2_kube_apiserver_mirror_configuration import KubeAPIServerMirrorConfigurationProof
from kil.v3b2_kube_controller_manager_mirror_configuration import KubeControllerManagerMirrorConfigurationProof

__all__ = ('PlatformPodConfigurationError', 'PlatformPodConfigurationBinding',
           'PlatformPodConfigurationProof', 'validate_platform_pod_configuration')
_DESCRIPTORS = (
    ('calico_node', CalicoNodeConfigurationProof, 'calico-node', 1, 'revision.ownership', True),
    ('calico_controller', CalicoControllerConfigurationProof, 'calico-kube-controllers', 1, 'ownership', False),
    ('coredns', CoreDNSPodConfigurationProof, 'coredns', 2, 'parent.ownership', False),
    ('local_path', LocalPathPodConfigurationProof, 'local-path-provisioner', 1, 'parent.ownership', False),
    ('kube_proxy', KubeProxyPodConfigurationProof, 'kube-proxy', 1, 'revision.parent.ownership', True),
    ('scheduler', SchedulerMirrorConfigurationProof, 'kube-scheduler', 1, 'ownership', True),
    ('etcd', EtcdMirrorConfigurationProof, 'etcd', 1, 'ownership', True),
    ('apiserver', KubeAPIServerMirrorConfigurationProof, 'kube-apiserver', 1, 'ownership', True),
    ('controller_manager', KubeControllerManagerMirrorConfigurationProof, 'kube-controller-manager', 1, 'ownership', True),
)
_PAIRS = {component: ('local-path-storage' if component == 'local-path-provisioner'
                      else 'kube-system') for _, _, component, _, _, _ in _DESCRIPTORS}

class PlatformPodConfigurationError(ValueError):
    pass

@dataclass(frozen=True, slots=True, order=True)
class PlatformPodConfigurationBinding:
    component: str
    namespace: str
    pod_name: str
    pod_uid: str
    pod_resource_version: str

    def __post_init__(self):
        try:
            if (type(self.component) is not str or self.component not in _PAIRS
                    or type(self.namespace) is not str
                    or self.namespace != _PAIRS[self.component]
                    or type(self.pod_name) is not str or not self.pod_name
                    or len(self.pod_name) > 253):
                raise PlatformPodConfigurationError('binding identity is invalid')
            _uid(self.pod_uid); _rv(self.pod_resource_version)
        except (ValueError, TypeError) as error:
            if isinstance(error, PlatformPodConfigurationError): raise
            raise PlatformPodConfigurationError('invalid binding') from error

def _path(value, path):
    for field in path.split('.'):
        value = getattr(value, field)
    return value

def _compute(ownership, values):
    if type(ownership) is not RuntimeOwnershipProof:
        raise PlatformPodConfigurationError('ownership must be exact')
    for name, cls, _, count, _, _ in _DESCRIPTORS:
        proof = values[name]
        if (type(proof) is not cls or type(proof.bindings) is not tuple
                or len(proof.bindings) != count):
            raise PlatformPodConfigurationError('component type/cardinality differs')
    ownership.__post_init__()
    projected = []
    for name, _, component, _, path, pod_fields in _DESCRIPTORS:
        proof = values[name]
        proof.__post_init__()
        if _path(proof, path) != ownership:
            raise PlatformPodConfigurationError('complete retained ownership differs')
        for b in proof.bindings:
            identity = ((b.pod_name, b.pod_uid, b.pod_resource_version)
                        if pod_fields else (b.name, b.uid, b.resource_version))
            projected.append(PlatformPodConfigurationBinding(component, b.namespace, *identity))
    revision = values['calico_node'].revision
    controller = values['calico_controller']
    if (revision.calico_source != controller.calico_source
            or revision.calico_projection != controller.calico_projection):
        raise PlatformPodConfigurationError('shared Calico authority differs')
    if values['apiserver'].source != values['controller_manager'].source:
        raise PlatformPodConfigurationError('complete manifest source differs')
    expected = []
    deployments = {'coredns', 'calico-kube-controllers', 'local-path-provisioner'}
    for b in ownership.deployment_ownership.bindings:
        if b.deployment_name in deployments:
            expected.extend(PlatformPodConfigurationBinding(b.deployment_name, b.namespace, *p)
                            for p in b.pods)
    for b in ownership.node_ownership.daemon_pods:
        expected.append(PlatformPodConfigurationBinding(b.daemon_set_name, b.namespace,
            b.pod_name, b.pod_uid, b.pod_resource_version))
    for b in ownership.node_ownership.static_pods:
        expected.append(PlatformPodConfigurationBinding(b.component, 'kube-system',
            b.pod_name, b.pod_uid, b.pod_resource_version))
    result, wanted = tuple(sorted(projected)), tuple(sorted(expected))
    counts = {component: sum(b.component == component for b in wanted) for component in _PAIRS}
    if (len(wanted) != 10 or len({(b.namespace, b.pod_name) for b in wanted}) != 10
            or len({b.pod_uid for b in wanted}) != 10
            or any(counts[c] != count for _, _, c, count, _, _ in _DESCRIPTORS)
            or result != wanted):
        raise PlatformPodConfigurationError('exact platform coverage differs')
    pods = [r for r in json.loads(ownership.runtime_objects)['items'] if r['kind'] == 'Pod']
    for b in wanted:
        matches = [r for r in pods if (r['metadata'].get('namespace'), r['metadata']['name'],
            r['metadata']['uid'], r['metadata']['resourceVersion']) ==
            (b.namespace, b.pod_name, b.pod_uid, b.pod_resource_version)]
        if len(matches) != 1:
            raise PlatformPodConfigurationError('raw Pod incarnation differs')
    return result

@dataclass(frozen=True, slots=True)
class PlatformPodConfigurationProof:
    ownership: RuntimeOwnershipProof
    calico_node: CalicoNodeConfigurationProof
    calico_controller: CalicoControllerConfigurationProof
    coredns: CoreDNSPodConfigurationProof
    local_path: LocalPathPodConfigurationProof
    kube_proxy: KubeProxyPodConfigurationProof
    scheduler: SchedulerMirrorConfigurationProof
    etcd: EtcdMirrorConfigurationProof
    apiserver: KubeAPIServerMirrorConfigurationProof
    controller_manager: KubeControllerManagerMirrorConfigurationProof
    bindings: tuple[PlatformPodConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if (self.runtime_contract_complete is not False
                    or self.full_application_contract_complete is not False):
                raise PlatformPodConfigurationError('configuration cannot complete runtime/application')
            if (type(self.bindings) is not tuple or len(self.bindings) != 10
                    or any(type(b) is not PlatformPodConfigurationBinding for b in self.bindings)):
                raise PlatformPodConfigurationError('retained bindings are not exact')
            for b in self.bindings: b.__post_init__()
            values = {name: getattr(self, name) for name, *_ in _DESCRIPTORS}
            if self.bindings != _compute(self.ownership, values):
                raise PlatformPodConfigurationError('reconstructed binding tuple differs')
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
            if isinstance(error, PlatformPodConfigurationError): raise
            raise PlatformPodConfigurationError('invalid retained platform configuration') from error

def validate_platform_pod_configuration(*, ownership, calico_node, calico_controller,
        coredns, local_path, kube_proxy, scheduler, etcd, apiserver, controller_manager):
    values = dict(calico_node=calico_node, calico_controller=calico_controller,
        coredns=coredns, local_path=local_path, kube_proxy=kube_proxy,
        scheduler=scheduler, etcd=etcd, apiserver=apiserver, controller_manager=controller_manager)
    try:
        return PlatformPodConfigurationProof(ownership=ownership, **values,
            bindings=_compute(ownership, values))
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        if isinstance(error, PlatformPodConfigurationError): raise
        raise PlatformPodConfigurationError('invalid platform configuration evidence') from error
```

- [ ] **Step 3: Run focused GREEN and review before committing**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$KIL_TEST_PYTHON" -m unittest tests.test_v3b2_platform_pod_configuration -v`
Expected: fixture and aggregate acceptance pass with zero skips. Run specification
then quality review, correct findings regression-first, append lineage and verify
readers/diff. Commit as `feat: compose ten platform Pod configurations`.

### Task 3: Adversarial same-source, replay and claim-boundary tests

**Files:** Modify `tests/test_v3b2_platform_pod_configuration.py`; production aggregate only if a regression demonstrates a defect.

- [ ] **Step 1: Add exact-type, constructor and binding mutation tests**

Add these methods to `PlatformCompositionTest`:

```python
    def test_wrong_types_and_subclasses_reject(self):
        for name, value in self.values.items():
            for bad in (None, object(), type('Lookalike', (), {})()):
                with self.subTest(name=name, bad=type(bad).__name__):
                    with self.assertRaises(self.m.PlatformPodConfigurationError):
                        self.m.validate_platform_pod_configuration(**dict(self.values, **{name: bad}))
            subclass = type('Derived', (type(value),), {})
            # Construct the subclass with the original retained fields.
            from dataclasses import fields
            bad = subclass(**{f.name: getattr(value, f.name) for f in fields(value)})
            with self.assertRaises(self.m.PlatformPodConfigurationError):
                self.m.validate_platform_pod_configuration(**dict(self.values, **{name: bad}))

    def test_constructor_forgery_and_flags_reject(self):
        proof = self.m.validate_platform_pod_configuration(**self.values)
        for rows in ((), list(proof.bindings), proof.bindings[:-1],
                     tuple(reversed(proof.bindings)),
                     proof.bindings[:-1] + (proof.bindings[0],),
                     proof.bindings[:-1] + (object(),)):
            with self.assertRaises(self.m.PlatformPodConfigurationError):
                replace(proof, bindings=rows)
        for flag in ('runtime_contract_complete', 'full_application_contract_complete'):
            for bad in (True, 0, None, 'false'):
                with self.assertRaises(self.m.PlatformPodConfigurationError):
                    replace(proof, **{flag: bad})
        for name in NAMES:
            bad = deepcopy(self.values[name])
            field = 'pod_uid' if hasattr(bad.bindings[0], 'pod_uid') else 'uid'
            object.__setattr__(bad.bindings[0], field, 'forged-incarnation')
            with self.assertRaises(self.m.PlatformPodConfigurationError):
                self.m.validate_platform_pod_configuration(**dict(self.values, **{name: bad}))
            with self.assertRaises(self.m.PlatformPodConfigurationError):
                replace(proof, **{name: bad})

    def test_missing_keywords_are_call_errors(self):
        for name in self.values:
            incomplete = dict(self.values)
            del incomplete[name]
            with self.assertRaises(TypeError):
                self.m.validate_platform_pod_configuration(**incomplete)

    def test_projection_identity_drift_rejects_constructor_replay(self):
        proof = self.m.validate_platform_pod_configuration(**self.values)
        for changes in (dict(pod_name='different-pod'), dict(pod_uid='different-uid'),
                        dict(pod_resource_version='987654')):
            altered = replace(proof.bindings[0], **changes)
            with self.assertRaises(self.m.PlatformPodConfigurationError):
                replace(proof, bindings=(altered,) + proof.bindings[1:])
```

Add `from copy import deepcopy` at module top.
Check missing keyword arguments with Python `TypeError` separately
from explicitly supplied `None`, which must raise the local evidence error.

- [ ] **Step 2: Add independently valid inventory/status mix regressions**

```python
    def test_valid_byte_and_status_variants_cannot_be_mixed(self):
        variants = [dict(self.args, runtime_objects=self.args['runtime_objects'] + b'\n')]
        document = deepcopy(self.document)
        for row in document['items']:
            if row['kind'] == 'Pod':
                row['status'] = {'arbitrary': ['not-ready', False]}
        from tests.test_v3b2_runtime_ownership import encode
        variants.append(dict(self.args, runtime_objects=encode(document)))
        for args in variants:
            alternate = dependencies(args, self.source)
            self.m.validate_platform_pod_configuration(**alternate)
            for name in self.values:
                mixed = dict(self.values, **{name: alternate[name]})
                with self.assertRaises(self.m.PlatformPodConfigurationError):
                    self.m.validate_platform_pod_configuration(**mixed)

    def test_distinct_valid_source_records_cannot_be_mixed(self):
        alternate_source = source_for(self.args, sequence=6)
        alternate = dependencies(self.args, alternate_source)
        self.m.validate_platform_pod_configuration(**alternate)
        for name in ('apiserver', 'controller_manager'):
            with self.assertRaises(self.m.PlatformPodConfigurationError):
                self.m.validate_platform_pod_configuration(
                    **dict(self.values, **{name: alternate[name]}))
```

The alternate source uses freshly constructed `RawObservation` objects.
`source.raw_observations` contains context-bound encoded bytes, not validator
input objects, so it must not be passed back as `observations`.

- [ ] **Step 3: Cover valid run/full-identity/profile differences and Calico source equality**

Add these methods. `rebase_args` preserves independent platform observations but
re-renders the new application expectations; `source_for` joins the changed run,
endpoint/kubeconfig and requested Kind image. A full alternate must validate
before any mixed evidence is claimed independently valid.

```python
    def test_independently_valid_authority_changes_cannot_be_mixed(self):
        owned = self.args['owned_identity']
        profile = self.args['profile']
        workload = self.args['workload']
        variants = (
            dict(owned_identity=replace(owned, docker_host='unix:///tmp/alternate/docker.sock')),
            dict(owned_identity=replace(owned, kubeconfig='/tmp/alternate/kubeconfig')),
            dict(workload=replace(workload, run_id='v3b2-' + 'd' * 64)),
            dict(profile=replace(profile, kind_node_image='kindest/node:v1.36.1@sha256:' + 'e' * 64)),
        )
        proof = self.m.validate_platform_pod_configuration(**self.values)
        for changes in variants:
            args = rebase_args(self.args, self.document, **changes)
            alternate = dependencies(args, source_for(args))
            self.m.validate_platform_pod_configuration(**alternate)
            for name in self.values:
                with self.subTest(changes=tuple(changes), name=name):
                    with self.assertRaises(self.m.PlatformPodConfigurationError):
                        self.m.validate_platform_pod_configuration(
                            **dict(self.values, **{name: alternate[name]}))
                    with self.assertRaises(self.m.PlatformPodConfigurationError):
                        replace(proof, **{name: alternate[name]})

    def test_calico_byte_variants_reject_at_existing_content_lock(self):
        revision = self.values['calico_node'].revision
        for changes in (
            dict(calico_source=revision.calico_source + b'\n# alternate\n'),
            dict(calico_projection=revision.calico_projection + b'\n'),
        ):
            with self.assertRaises(ValueError):
                dependencies(self.args, self.source, **changes)

    def test_forged_calico_authority_and_configuration_do_not_bypass_replay(self):
        bad = deepcopy(self.values['calico_node'])
        object.__setattr__(bad.revision, 'calico_source', b'not Calico')
        with self.assertRaises(self.m.PlatformPodConfigurationError):
            self.m.validate_platform_pod_configuration(**dict(self.values, calico_node=bad))
        proof = self.m.validate_platform_pod_configuration(**self.values)
        with self.assertRaises(self.m.PlatformPodConfigurationError):
                replace(proof, calico_node=bad)
```

The existing Calico pair has exact SHA-256 content locks; unequal byte pairs
cannot both be independently valid under this contract. Record this earlier
rejection accurately. The aggregate still compares the retained pairs explicitly.
Do not loosen the source lock to manufacture an aggregate-only test.

Add a component configuration mutation test that preserves ownership validity
but must fail component reconstruction through the aggregate:

```python
    def test_every_component_configuration_is_reconstructed(self):
        import json
        from tests.test_v3b2_runtime_ownership import encode
        from kil.v3b2_runtime_ownership import validate_runtime_ownership
        paths = dict(calico_node='revision.ownership', calico_controller='ownership',
            coredns='parent.ownership', local_path='parent.ownership',
            kube_proxy='revision.parent.ownership', scheduler='ownership',
            etcd='ownership', apiserver='ownership', controller_manager='ownership')
        proof = self.m.validate_platform_pod_configuration(**self.values)
        for name, path in paths.items():
            bad = deepcopy(self.values[name])
            owned = bad
            for field in path.split('.'):
                owned = getattr(owned, field)
            binding = bad.bindings[0]
            pod_name = binding.pod_name if hasattr(binding, 'pod_name') else binding.name
            doc = json.loads(owned.runtime_objects)
            candidate = next(r for r in doc['items'] if r['kind'] == 'Pod'
                and r['metadata'].get('namespace') == binding.namespace
                and r['metadata']['name'] == pod_name)
            candidate['spec']['containers'][0]['image'] = 'invalid.example/config-drift:v1'
            changed = encode(doc)
            validate_runtime_ownership(**dict(self.args, runtime_objects=changed))
            object.__setattr__(owned, 'runtime_objects', changed)
            with self.assertRaises(self.m.PlatformPodConfigurationError):
                self.m.validate_platform_pod_configuration(**dict(self.values, **{name: bad}))
            with self.assertRaises(self.m.PlatformPodConfigurationError):
                replace(proof, **{name: bad})
```

- [ ] **Step 4: Execute adversarial tests and correct only evidenced defects**

Run the focused module with `-v`. New tests may already pass because Task 2
implemented their strict contract; do not claim such tests established RED.
For any demonstrated defect capture failing output, make the smallest aggregate
correction, rerun the reproducer and focused module, then specification and
quality review. Include each component's image/config mutation rejection through
reconstruction and local error normalization. Append exact lineage results,
regenerate/check readers, diff-check, commit as
`test: enforce platform configuration authority continuity`.

### Task 4: Combined regression and bounded static acceptance

**Files:** Plan checkboxes, lineage Markdown and generated readers only, unless regression proves an in-scope defect.

- [ ] **Step 1: Run adjacent component, revision, ownership and source tests**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$KIL_TEST_PYTHON" -m unittest \
  tests.test_v3b2_platform_pod_configuration \
  tests.test_v3b2_calico_node_configuration tests.test_v3b2_calico_controller_configuration \
  tests.test_v3b2_coredns_pod_configuration tests.test_v3b2_local_path_pod_configuration \
  tests.test_v3b2_kube_proxy_pod_configuration tests.test_v3b2_scheduler_mirror_configuration \
  tests.test_v3b2_etcd_mirror_configuration tests.test_v3b2_kube_apiserver_mirror_configuration \
  tests.test_v3b2_kube_controller_manager_mirror_configuration \
  tests.test_v3b2_calico_node_revision tests.test_v3b2_kube_proxy_revision \
  tests.test_v3b2_coredns_parent_configuration tests.test_v3b2_local_path_parent_configuration \
  tests.test_v3b2_kube_proxy_parent_configuration tests.test_v3b2_runtime_ownership \
  tests.test_v3b2_node_ownership tests.test_v3b2_control_plane_manifest_source -v
```

Expected: zero failures/errors/skips. Capture actual method count and elapsed
time; no estimated count is an acceptance result.

- [ ] **Step 2: Run full discovery and reader verification**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$KIL_TEST_PYTHON" -m unittest discover -s tests -v
"$KIL_TEST_PYTHON" tools/render_markdown.py --check
git diff --check
```

Expected: zero failures/errors; exactly the existing sixteen lifecycle skips.
Compute actual passes as total methods minus skips; `Ran N` includes skips.
An interrupted process is not a passing run. Full discovery is equivalent to
the test part of `make validate` while avoiding its unquoted interpreter path.

- [ ] **Step 3: Obtain final specification then quality review**

Review exact accepted scope, full dependency reconstruction, authority and
incarnation joins, test independence, false flags and unchanged deferrals.
Resolve review findings regression-first; rerun affected gates. Do not dispatch
an expensive duplicate full suite merely to recount coordinator evidence.

- [ ] **Step 4: Record acceptance and commit**

Append a new numbered lineage entry with approved design/plan as input,
“Confirmed static platform configuration composition; no live or readiness
claim” as decision status, exact results and revision, ten-Pod coverage as the
accepted boundary, shared-source equality, unchanged false flags and sixteen
deferrals. State platform image authority and status/readiness design as the
next gate. Update task checkboxes, regenerate/check readers and diff, then
commit as `docs: accept static platform configuration composition`.

## Plan self-review and execution handoff

Spec coverage: Task 1 provides independent same-inventory inputs; Task 2 defines
all public records, exact types, joins, projections and replay; Task 3 exercises
forgery, independently valid mixes and claim boundaries; Task 4 records reviewed
regression evidence without live or completion claims. All component names and
ownership paths match existing records. Task 3 alternate source handling must
use reconstructed observations, not retained context-bound bytes.

Planning verification: all eight planned Python blocks parsed successfully with
`ast.parse`; placeholder scan found no unresolved implementation placeholders.
This checks syntax and specification coverage, not execution or passing tests.

Choose subagent-driven execution (fresh task implementer followed by specification
and quality review) or inline executing-plans with the same review checkpoints.
Neither option broadens this plan's static-only authorization.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
