# Exploratory HF case and source evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encode the unchanged harmless three-track case and reject incomplete, replaced or nonjoining producer evidence before reporting a result.

**Architecture:** A pure module supplies the fixed instruction, bounded JSONL decoder, narrow Pod incarnation binding and complete producer join. It runs no command and publishes no acceptance artifact. Native lifecycle supplies authenticated node-image alias bindings and exact rendered Pod specifications, brackets each source read and provides complete frozen bytes.

**Tech Stack:** Python 3.12, existing Q-state fixture, driver protocol and producer adapter, unittest.

---

Approved scope: docs/superpowers/specs/2026-09-16-hf-exploratory-kind-calico-design.md. Dependency: reviewed input unit; no native tool, lab command, download, strict-controller invocation or existing production-file change. Retain this linked worktree.

## Task 1: Pure case and evidence boundary

Files: create src/kil/hf_exploratory_case.py and tests/test_hf_exploratory_case.py.

- [ ] Write these complete tests first. Additional independently specified producer fixtures exercise all three complete joins and an unexpected complete tuple; do not derive expected values with the module being tested.

```python
import importlib
import importlib.util
from hashlib import sha256
import unittest
from kil.v3b1_driver_protocol import parse_instruction, canonical_record
from kil.v3b2_contracts import TRACKS


class ExploratoryCaseTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('kil.hf_exploratory_case'))
        self.module = importlib.import_module('kil.hf_exploratory_case')

    def test_instruction_is_fixed_one_shot_and_fixture_only(self):
        for track in TRACKS:
            value = parse_instruction(self.module.instruction(track, 'a' * 64, 100), expected_track=track)
            self.assertEqual(value['method'], 'POST')
            self.assertEqual(value['path'], '/consequential/admin')
            self.assertEqual(value['body_byte_count'], 0)
            self.assertEqual(value['headers']['authorization'], 'Bearer v3b1-lab-credential')
            self.assertEqual(value['headers']['x-envoy-max-retries'], '0')
            self.assertEqual(value['headers']['x-kil-run-id'], 'v3b1-' + 'a' * 64)
        for track, digest, issued in [('foreign', 'a' * 64, 100), (TRACKS[0], 'A' * 64, 100), (TRACKS[0], 'a' * 64, True)]:
            with self.assertRaises(ValueError):
                self.module.instruction(track, digest, issued)

    def test_jsonl_requires_complete_distinct_bounded_object_records(self):
        self.assertEqual(self.module.records(b''), [])
        payload = canonical_record({'x': 1})
        self.assertEqual(self.module.records(payload), [{'x': 1}])
        for bad in [payload[:-1], payload + payload, b'[]\n', b'{"x":1,"x":2}\n', b'not json\n', b'x' * (1024 * 1024)]:
            with self.subTest(bad=bad[:30]), self.assertRaises(ValueError):
                self.module.records(bad)

    def test_source_requires_exact_incarnation_stable_complete_bytes(self):
        bound = {'uid': 'pod-1', 'container_id': 'containerd://' + 'a' * 64, 'resource_version': '1'}
        payload = canonical_record({'x': 1})
        value = self.module.frozen_source(bound, bound, payload, payload)
        self.assertEqual(value['sha256'], sha256(payload).hexdigest())
        for after, second in [({**bound, 'uid': 'pod-2'}, payload), ({**bound, 'container_id': 'containerd://' + 'b' * 64}, payload), ({**bound, 'resource_version': '2'}, payload), (bound, b'')]:
            with self.assertRaises(ValueError):
                self.module.frozen_source(bound, after, payload, second)


if __name__ == '__main__':
    unittest.main()
```

- [ ] Run RED:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -m unittest tests.test_hf_exploratory_case -v
```

Expected: three missing-module assertion failures, no native command.

- [ ] Implement the complete pure case/source boundary below. Add Pod-binding tests first before implementing `bind_pod` in the next step.

```python
"""Pure fixed exploratory case and complete frozen source validation."""
from decimal import Decimal
from hashlib import sha256
import re
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from kil.q_state import QStateClaims, issue_q_state
from kil.v3b1_driver_protocol import canonical_record, parse_instruction
from kil.v3b2_contracts import TRACKS, TRACK_NAMESPACES
from kil.v3b2_evidence import adapt_producer_sources
from kil.v3b2_proofs import canonical, decode

SOURCE_LIMIT = 1024 * 1024
LABEL = 'Exploratory local Kind/Calico result; platform-image provenance unverified; full Kind/Calico acceptance not established.'
EXPECTED = (('permit', 200, 1), ('permit', 200, 1), ('deny', 403, 0))


def instruction(track, run_digest, issued):
    if (track not in TRACKS or type(run_digest) is not str
            or re.fullmatch('[0-9a-f]{64}', run_digest) is None
            or type(issued) is not int or issued < 1):
        raise ValueError('invalid_exploratory_case_binding')
    headers = {
        'authorization': 'Bearer v3b1-lab-credential', 'x-request-id': 'v3b1-central-request',
        'x-kil-run-id': 'v3b1-' + run_digest,
        'x-envoy-hedge-on-per-try-timeout': 'false', 'x-envoy-max-retries': '0',
        'x-kil-decision-digest': 'f' * 64, 'x-kil-issuer': 'https://attacker.invalid',
        'x-kil-local-evidence': '{"divergence":"0"}', 'x-kil-mode': 'credential_policy_baseline',
        'x-kil-track': 'client-selected-track', 'x-kil-verified-subject': 'spiffe://attacker.invalid/workload',
    }
    if track != TRACKS[0]:
        audience = 'kil-v3-signed' if track == TRACKS[1] else 'kil-v3-local'
        claims = QStateClaims(
            'kil.q-state.v0', f'q-v3b2-{audience}', 'https://lab-issuer.kil.invalid',
            'spiffe://kil.local/workload/demo', audience, 'admin_action', 'consequential_admin',
            issued, issued, issued + 10, issued - 1, 'tp-v3b2-1', 'sha256:' + 'a' * 64,
            'ke-v3b2-1', 'sha256:' + 'b' * 64, 'kil-lab-v3@0', Decimal('80'), Decimal('40'),
            5, 2, True, True, Decimal('0'), Decimal('100'), 'kil-decay-v1', 'kil-v3b2-fixture-v1',
        )
        headers['x-kil-q-state'] = issue_q_state(claims, Ed25519PrivateKey.from_private_bytes(bytes(range(32))))
    payload = canonical_record({'schema_version': 'kil.v3b1-driver-instruction.v1',
        'track': track, 'method': 'POST', 'path': '/consequential/admin', 'headers': headers,
        'body_byte_count': 0})
    parse_instruction(payload, expected_track=track)
    return payload


def records(payload):
    if type(payload) is not bytes or len(payload) >= SOURCE_LIMIT or payload and not payload.endswith(b'\n'):
        raise ValueError('source_incomplete_or_bounded_prefix')
    result, seen = [], set()
    for line in payload.splitlines():
        if not line:
            raise ValueError('source_blank_record')
        value = decode(line, maximum=SOURCE_LIMIT)
        if type(value) is not dict:
            raise ValueError('source_record_not_object')
        encoded = canonical(value)
        if encoded in seen:
            raise ValueError('source_duplicate_record')
        seen.add(encoded)
        result.append(value)
    return result


def frozen_source(before, after, payload, second):
    if before != after or type(before) is not dict or payload != second:
        raise ValueError('source_incarnation_or_bytes_changed')
    rows = records(payload)
    return {'identity': before, 'byte_count': len(payload), 'sha256': sha256(payload).hexdigest(), 'records': rows}


def join(sources, *, track, run_id, request_free):
    reduced = adapt_producer_sources(sources, track=track, run_id=run_id)
    if type(request_free) is not bool:
        raise ValueError('invalid_result_mode')
    if request_free:
        if any(reduced.values()):
            raise ValueError('rehearsal_contains_request')
        return {'track': track, 'request_free': True}
    if len(reduced['driver']) != 1:
        raise ValueError('missing_consequential_result')
    row = reduced['driver'][0]
    actual = (row['decision'], row['http_status'], len(reduced['target']))
    return {'track': track, 'observed': list(actual), 'expected': list(EXPECTED[TRACKS.index(track)]),
            'classification': 'expected' if actual == EXPECTED[TRACKS.index(track)] else 'unexpected',
            'decision_digest': row['decision_digest'], 'semantic_join': reduced,
            'adapter_reasons': sources['decision'][0]['adapter_reasons'],
            'engine_reasons': sources['decision'][0]['engine_reasons'],
            'untrusted_header_names': sources['decision'][0]['untrusted_header_names']}
```

- [ ] Add the following literal Pod fixtures and failing tests before `bind_pod`. Wrong requested/runtime images, config-vs-target ImageRef distinction, restarting/extra containers, deleting/foreign/run-mismatched Pods and missing readiness are independent negatives. UID/CID replacement is covered by the earlier frozen-source test. This asserts selected safety controls and incarnation only; it is not full static/admission/no-bypass acceptance.

```python
from copy import deepcopy


def pod_fixture():
    return {'apiVersion': 'v1', 'kind': 'Pod',
        'metadata': {'name': 'driver', 'namespace': 'kil-v3-baseline', 'uid': 'pod-1', 'resourceVersion': '1',
            'annotations': {'kil.dev/run-id': 'v3b2-' + 'a' * 64},
            'labels': {'kil.dev/track': TRACKS[0], 'kil.dev/role': 'driver', 'kil.dev/managed': 'v3b2'}},
        'spec': {'automountServiceAccountToken': False, 'containers': [{'name': 'driver',
            'image': 'kil.local/kil-v3b2:sha256-' + 'b' * 64, 'imagePullPolicy': 'Never',
            'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
                'runAsNonRoot': True, 'runAsUser': 65532, 'capabilities': {'drop': ['ALL']}}}]},
        'status': {'phase': 'Running', 'containerStatuses': [{'name': 'driver',
            'image': 'kil.local/kil-v3b2:sha256-' + 'b' * 64, 'imageID': 'sha256:' + 'c' * 64,
            'containerID': 'containerd://' + 'd' * 64, 'restartCount': 0, 'ready': True, 'state': {'running': {}}}]}}


def bind_arguments():
    return dict(track=TRACKS[0], role='driver', run_id='v3b2-' + 'a' * 64,
        requested_image='kil.local/kil-v3b2:sha256-' + 'b' * 64,
        runtime_image='kil.local/kil-v3b2:sha256-' + 'b' * 64, image_ref='sha256:' + 'c' * 64)


class ExploratoryPodTests(ExploratoryCaseTests):
    def test_source_config_ref_is_not_assumed_target(self):
        value = self.module.bind_pod(pod_fixture(), **bind_arguments())
        self.assertEqual(value['image_ref'], 'sha256:' + 'c' * 64)
        with self.assertRaises(ValueError):
            self.module.bind_pod(pod_fixture(), **{**bind_arguments(), 'image_ref': 'sha256:' + 'b' * 64})

    def test_container_and_pod_negative_controls(self):
        mutations = [
            lambda x: x['metadata'].update(namespace='foreign'),
            lambda x: x['metadata'].update(deletionTimestamp='now'),
            lambda x: x['metadata']['annotations'].update({'kil.dev/run-id': 'foreign'}),
            lambda x: x['spec']['containers'][0].update(image='foreign'),
            lambda x: x['spec']['containers'].append(deepcopy(x['spec']['containers'][0])),
            lambda x: x['spec'].update(hostNetwork=True),
            lambda x: x['spec']['containers'][0]['securityContext'].update(privileged=True),
            lambda x: x['status']['containerStatuses'][0].update(image='foreign'),
            lambda x: x['status']['containerStatuses'][0].update(imageID='sha256:' + 'b' * 64),
            lambda x: x['status']['containerStatuses'][0].update(restartCount=1),
            lambda x: x['status']['containerStatuses'][0].update(ready=False),
        ]
        for mutation in mutations:
            value = pod_fixture()
            mutation(value)
            with self.assertRaises(ValueError):
                self.module.bind_pod(value, **bind_arguments())

    def test_completed_driver_requires_exact_zero(self):
        value = pod_fixture()
        value['status']['phase'] = 'Succeeded'
        state = value['status']['containerStatuses'][0]
        state.update(ready=False, state={'terminated': {'exitCode': 0}})
        self.module.bind_pod(value, **bind_arguments(), completed=True)
        for bad in (False, 1, '0'):
            state['state']['terminated']['exitCode'] = bad
            with self.assertRaises(ValueError):
                self.module.bind_pod(value, **bind_arguments(), completed=True)
```

Add this binding after the new tests fail for the absent function:

```python
def bind_pod(value, *, track, role, run_id, requested_image, runtime_image, image_ref, completed=False, require_ready=True):
    if (track not in TRACKS or role not in {'driver', 'authz', 'envoy', 'target'}
            or type(completed) is not bool or type(require_ready) is not bool):
        raise ValueError('invalid_exploratory_pod_binding')
    namespace = dict(TRACK_NAMESPACES)[track]
    metadata, spec, status = value['metadata'], value['spec'], value['status']
    name = metadata['name']
    if (value['apiVersion'] != 'v1' or value['kind'] != 'Pod'
            or metadata['namespace'] != namespace or 'deletionTimestamp' in metadata
            or metadata.get('annotations', {}).get('kil.dev/run-id') != run_id
            or metadata.get('labels', {}).get('kil.dev/track') != track
            or metadata.get('labels', {}).get('kil.dev/role') != role
            or metadata.get('labels', {}).get('kil.dev/managed') != 'v3b2'
            or not (name == 'driver' if role == 'driver' else name.startswith(role + '-'))
            or len(spec['containers']) != 1 or len(status['containerStatuses']) != 1
            or spec.get('initContainers') or spec.get('ephemeralContainers')
            or any(spec.get(key, False) is not False for key in ('hostNetwork', 'hostPID', 'hostIPC'))
            or spec.get('automountServiceAccountToken') is not False):
        raise ValueError('exploratory_pod_not_bound')
    container, state = spec['containers'][0], status['containerStatuses'][0]
    security = container.get('securityContext', {})
    if (container['name'] != role or container['image'] != requested_image
            or container.get('imagePullPolicy') != 'Never'
            or security.get('allowPrivilegeEscalation') is not False
            or security.get('readOnlyRootFilesystem') is not True
            or security.get('runAsNonRoot') is not True
            or security.get('runAsUser') != 65532 or security.get('capabilities') != {'drop': ['ALL']}
            or security.get('privileged', False) is not False
            or any('hostPath' in volume for volume in spec.get('volumes', []))
            or state['name'] != role or state['image'] != runtime_image or state['imageID'] != image_ref
            or type(state['restartCount']) is not int or state['restartCount'] != 0
            or re.fullmatch('containerd://[0-9a-f]{64}', state['containerID']) is None):
        raise ValueError('exploratory_container_not_bound')
    if completed:
        exit_code = state.get('state', {}).get('terminated', {}).get('exitCode')
        if role != 'driver' or status.get('phase') != 'Succeeded' or type(exit_code) is not int or exit_code != 0:
            raise ValueError('driver_not_completed_zero')
    elif (status.get('phase') != 'Running' or require_ready and state.get('ready') is not True
            or set(state.get('state', {})) != {'running'}):
        raise ValueError('exploratory_container_not_ready')
    for key in ('uid', 'resourceVersion'):
        if type(metadata.get(key)) is not str or not metadata[key] or len(metadata[key]) > 128:
            raise ValueError('exploratory_pod_identity_invalid')
    return {'namespace': namespace, 'pod': name, 'role': role, 'uid': metadata['uid'],
            'resource_version': metadata['resourceVersion'], 'container_id': state['containerID'],
            'requested_image': requested_image, 'runtime_image': runtime_image, 'image_ref': image_ref}
```

- [ ] Add the following complete join tests before adding `join`. `producer_records` is an existing test-owned producer-wire fixture, not the new module or production expectation factory. The expected tuple is independently literal. Never emit fixture output as native evidence.

```python
from tests.test_v3b2_evidence import producer_records


class ExploratoryJoinTests(ExploratoryCaseTests):
    def test_complete_join_and_empty_rehearsal(self):
        run_id = 'v3b2-' + 'a' * 64
        for track, expected in zip(TRACKS, [('permit', 200, 1), ('permit', 200, 1), ('deny', 403, 0)]):
            value = self.module.join(producer_records(track, run_id), track=track, run_id=run_id, request_free=False)
            self.assertEqual(value['observed'], list(expected))
            self.assertEqual(value['classification'], 'expected')
            value = self.module.join(producer_records(track, run_id, request_free=True), track=track, run_id=run_id, request_free=True)
            self.assertIs(value['request_free'], True)

    def test_missing_denial_source_is_not_success(self):
        run_id, track = 'v3b2-' + 'a' * 64, TRACKS[2]
        for kind in ('driver', 'decision', 'envoy'):
            sources = producer_records(track, run_id)
            sources[kind] = []
            with self.assertRaises(ValueError):
                self.module.join(sources, track=track, run_id=run_id, request_free=False)

    def test_unexpected_complete_denial_is_reported_without_retry(self):
        run_id, track = 'v3b2-' + 'a' * 64, TRACKS[0]
        sources = producer_records(track, run_id)
        sources['driver'][1]['response_status'] = 403
        sources['decision'][0].update(outcome='deny', http_status=403)
        sources['envoy'][0].update(response_code='403', upstream_host='-', upstream_service_time='-')
        sources['target'] = []
        value = self.module.join(sources, track=track, run_id=run_id, request_free=False)
        self.assertEqual(value['observed'], ['deny', 403, 0])
        self.assertEqual(value['classification'], 'unexpected')
```

- [ ] Run GREEN with the same command, including added failing-first fixtures. Expected all tests pass, malformed/missing evidence raises rather than being a denial. Preserve original strict files byte-for-byte.
- [ ] Complete independent specification then quality review. Regenerate lineage reader and commit only new module/test plus required lineage. Suggested commit: feat: add pure exploratory HF case and evidence boundary.

## Native consumer contract

The next unit must prove two accepted application image alias branches from authenticated CRI/node-store observations, never substitute target digest for config digest. It selects twelve exact ready role Pods from the fresh bound cluster and captures applied rendered objects/policies and Calico readiness before instructions. Capture each source between two `bind_pod` observations and two identical complete reads; retain raw commands, bytes and checksum. Envoy listener refusal and all four zero active gauges, plus zero-exit one-shot drivers, precede final capture. After listener drain `require_ready=False` permits a running Envoy whose TCP readiness probe has correctly failed; it does not permit termination, restart or replacement. Driver resourceVersion can change on completion but UID/CID must equal the readiness anchor; the frozen before/after observation must itself be identical. Any source cap, parse failure, replacement or incomplete join is inconclusive. No diagnostic plaintext is silently removed; fixed Envoy configuration routes diagnostics to /tmp/envoy.log while stdout carries access JSONL. Matching the expected tuple alone does not establish the cause of denial: report the actual adapter/engine reasons, and never call an expired/unverified Q-state denial a demonstrated local-reduction denial. No public bundle writer/verifier is called.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
