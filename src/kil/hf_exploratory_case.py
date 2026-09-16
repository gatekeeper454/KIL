"""Pure exploratory fixtures and evidence joins, not native acceptance proof."""
from decimal import Decimal
from hashlib import sha256
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from kil.q_state import QStateClaims, issue_q_state
from kil.v3b1_driver_protocol import canonical_record, parse_instruction
from kil.v3b2_contracts import TRACKS, TRACK_NAMESPACES
from kil.v3b2_evidence import adapt_producer_sources
from kil.v3b2_proofs import canonical, decode

SOURCE_LIMIT = 1048576
LABEL = 'Exploratory local Kind/Calico result; platform-image provenance unverified; full Kind/Calico acceptance not established.'
EXPECTED = (('permit', 200, 1), ('permit', 200, 1), ('deny', 403, 0))


def instruction(track, run_digest, issued):
    if track not in TRACKS or type(run_digest) is not str or re.fullmatch(r'[0-9a-f]{64}', run_digest) is None or type(issued) is not int or issued <= 0:
        raise ValueError('invalid instruction binding')
    headers = {'authorization': 'Bearer v3b1-lab-credential', 'x-request-id': 'v3b1-central-request',
               'x-kil-run-id': 'v3b1-' + run_digest, 'x-envoy-hedge-on-per-try-timeout': 'false',
               'x-envoy-max-retries': '0', 'x-kil-decision-digest': 'f' * 64,
               'x-kil-issuer': 'https://attacker.invalid', 'x-kil-local-evidence': '{"divergence":"0"}',
               'x-kil-mode': 'credential_policy_baseline', 'x-kil-track': 'client-selected-track',
               'x-kil-verified-subject': 'spiffe://attacker.invalid/workload'}
    if track != TRACKS[0]:
        audience = 'kil-v3-signed' if track == TRACKS[1] else 'kil-v3-local'
        claims = QStateClaims('kil.q-state.v0', f'q-v3b2-{audience}', 'https://lab-issuer.kil.invalid',
            'spiffe://kil.local/workload/demo', audience, 'admin_action', 'consequential_admin',
            issued, issued, issued + 10, issued - 1, 'tp-v3b2-1', 'sha256:' + 'a' * 64,
            'ke-v3b2-1', 'sha256:' + 'b' * 64, 'kil-lab-v3@0', Decimal('80'), Decimal('40'),
            5, 2, True, True, Decimal('0'), Decimal('100'), 'kil-decay-v1', 'kil-v3b2-fixture-v1')
        headers['x-kil-q-state'] = issue_q_state(claims, Ed25519PrivateKey.from_private_bytes(bytes(range(32))))
    payload = canonical_record({'schema_version': 'kil.v3b1-driver-instruction.v1', 'track': track,
        'method': 'POST', 'path': '/consequential/admin', 'headers': headers, 'body_byte_count': 0})
    parse_instruction(payload, expected_track=track)
    return payload


def records(payload):
    if type(payload) is not bytes or len(payload) >= SOURCE_LIMIT or b'\r' in payload or (payload and not payload.endswith(b'\n')):
        raise ValueError('source must be complete bounded JSONL bytes')
    result, seen = [], set()
    for line in payload.split(b'\n')[:-1]:
        if not line:
            raise ValueError('empty source record')
        value = decode(line, maximum=SOURCE_LIMIT)
        if type(value) is not dict:
            raise ValueError('source record must be an object')
        normalized = canonical(value)
        if normalized in seen:
            raise ValueError('duplicate source record')
        seen.add(normalized)
        result.append(value)
    return result


def frozen_source(before, after, payload, second):
    for identity in (before, after):
        if type(identity) is not dict or any(type(identity.get(key)) is not str or not identity[key]
                                            for key in ('uid', 'container_id', 'resource_version')):
            raise ValueError('source identity is incomplete')
    if before != after or type(second) is not bytes or payload != second:
        raise ValueError('source binding or bytes changed')
    parsed = records(payload)
    return {'identity': dict(before), 'byte_count': len(payload), 'sha256': sha256(payload).hexdigest(), 'records': parsed}


def join(sources, *, track, run_id, request_free):
    """Report observed tuples; equality is not a causal or acceptance proof."""
    if type(request_free) is not bool:
        raise ValueError('request_free must be a boolean')
    reduced = adapt_producer_sources(sources, track=track, run_id=run_id)
    if request_free:
        if any(reduced.values()):
            raise ValueError('rehearsal contains application records')
        return {'track': track, 'request_free': True}
    if len(reduced['driver']) != 1:
        raise ValueError('action lacks a complete driver result')
    row = reduced['driver'][0]
    observed = (row['decision'], row['http_status'], len(reduced['target']))
    expected = EXPECTED[TRACKS.index(track)]
    return {'track': track, 'observed': list(observed), 'expected': list(expected),
            'classification': 'expected' if observed == expected else 'unexpected',
            'decision_digest': row['decision_digest'], 'semantic_join': reduced,
            **{key: list(sources['decision'][0][key]) for key in
               ('adapter_reasons', 'engine_reasons', 'untrusted_header_names')}}


def bind_pod(value, *, track, role, run_id, requested_image, runtime_image, image_ref,
             completed=False, require_ready=True):
    """Bind observations to supplied image aliases, without proving provenance.

    This partial Pod check is not a full static, admission, or no-bypass check.
    Runtime image and imageID aliases must come from the caller's node proof.
    """
    try:
        if track not in TRACKS or role not in {'driver', 'authz', 'envoy', 'target'} or type(completed) is not bool or type(require_ready) is not bool:
            raise ValueError('invalid Pod binding arguments')
        namespace = dict(TRACK_NAMESPACES)[track]
        if type(value) is not dict or value['apiVersion'] != 'v1' or value['kind'] != 'Pod':
            raise ValueError('not a v1 Pod')
        metadata, spec, status = value['metadata'], value['spec'], value['status']
        name = metadata['name']
        if (metadata['namespace'] != namespace or 'deletionTimestamp' in metadata
                or metadata['annotations']['kil.dev/run-id'] != run_id
                or metadata['labels']['kil.dev/track'] != track
                or metadata['labels']['kil.dev/role'] != role
                or metadata['labels']['kil.dev/managed'] != 'v3b2'
                or type(name) is not str or (name != 'driver' if role == 'driver' else not name.startswith(role + '-'))):
            raise ValueError('Pod metadata does not bind')
        for key in ('uid', 'resourceVersion'):
            if type(metadata[key]) is not str or not metadata[key] or len(metadata[key]) > 128:
                raise ValueError('invalid Pod identity')
        if (type(spec['containers']) is not list or len(spec['containers']) != 1
                or type(status['containerStatuses']) is not list or len(status['containerStatuses']) != 1
                or spec.get('initContainers') or spec.get('ephemeralContainers')
                or any(spec.get(key, False) is not False for key in ('hostNetwork', 'hostPID', 'hostIPC'))
                or spec['automountServiceAccountToken'] is not False
                or any('hostPath' in volume for volume in spec.get('volumes', []))):
            raise ValueError('unsafe or ambiguous Pod structure')
        container, observed = spec['containers'][0], status['containerStatuses'][0]
        security = container['securityContext']
        if (container['name'] != role or container['image'] != requested_image or container['imagePullPolicy'] != 'Never'
                or security['allowPrivilegeEscalation'] is not False or security['readOnlyRootFilesystem'] is not True
                or security['runAsNonRoot'] is not True or type(security['runAsUser']) is not int
                or security['runAsUser'] != 65532 or security['capabilities'] != {'drop': ['ALL']}
                or security.get('privileged', False) is not False
                or observed['name'] != role or observed['image'] != runtime_image or observed['imageID'] != image_ref
                or type(observed['restartCount']) is not int or observed['restartCount'] != 0
                or type(observed['containerID']) is not str or re.fullmatch(r'containerd://[0-9a-f]{64}', observed['containerID']) is None):
            raise ValueError('container observation does not bind')
        state = observed['state']
        if completed:
            if (role != 'driver' or status['phase'] != 'Succeeded' or set(state) != {'terminated'}
                    or type(state['terminated']['exitCode']) is not int or state['terminated']['exitCode'] != 0):
                raise ValueError('driver completion is invalid')
        elif (status['phase'] != 'Running' or set(state) != {'running'}
              or type(state['running']) is not dict or type(observed['ready']) is not bool
              or (require_ready and observed['ready'] is not True)):
            raise ValueError('Pod is not an eligible running observation')
        return {'namespace': namespace, 'pod': name, 'role': role, 'uid': metadata['uid'],
                'resource_version': metadata['resourceVersion'], 'container_id': observed['containerID'],
                'requested_image': requested_image, 'runtime_image': runtime_image, 'image_ref': image_ref}
    except (KeyError, TypeError, AttributeError, IndexError):
        raise ValueError('invalid Pod structure') from None
