"""Historical policy continuity and healthy generated KIL Pods before drivers.

Pure replay callers must authenticate the supplied context themselves. Durable
publication authenticates that context against the pending journal under its lock.
No reader collects or regenerates missing evidence.
"""
from dataclasses import dataclass
import os
from pathlib import Path

from kil.v3b2_application_boundary import PolicyContinuityBinding
from kil.v3b2_application_policy_stage import application_policy_observation_specs, _observation_shape
from kil.v3b2_policy_stage_checkpoint import (decode_policy_stage_checkpoint, _context,
    read_policy_stage_checkpoint_bytes, _read_checkpoint_bytes)
from kil.v3b2_journal import (_journal_append_lock, _private_location, _publish_observed_proof,
    load_journal, load_expected_context)
from kil.v3b2_pre_driver_ownership import validate_pre_driver_ownership
from kil.v3b2_pre_driver_runtime import PreDriverRuntimeProof, validate_pre_driver_runtime
from kil.v3b2_proofs import (ExpectedContext, RawObservation, RUNTIME_RESOURCES,
    canonical, decode, _canonical_bounded, _cluster, reconstruct_prior_node_image_references,
    validate_applied_objects)

_MAX_RAW = 8 * 1024 * 1024
_MAX_BYTES = 24 * 1024 * 1024
_SCHEMA = 'kil.v3b2-pre-driver-stage-checkpoint.v1'


class PreDriverCheckpointError(ValueError):
    pass


def pre_driver_observation_specs(identity):
    policy = application_policy_observation_specs(identity)
    runtime = ('runtime_inventory', ('kubectl', '--kubeconfig', identity.kubeconfig,
        'get', RUNTIME_RESOURCES, '--all-namespaces', '--output', 'json'), ())
    return (policy[0], runtime, *policy[-3:])


def _raw_bytes(observations):
    if type(observations) is not tuple or len(observations) != 5:
        raise PreDriverCheckpointError('observations must be an exact tuple of five')
    for row in observations:
        if type(row) is not RawObservation:
            raise PreDriverCheckpointError('observation type is not exact')
        row.__post_init__(); _observation_shape(row)
    if sum(len(row.stdout) + len(row.stderr) for row in observations) > _MAX_RAW:
        raise PreDriverCheckpointError('observations exceed pre-serialization bound')
    return _canonical_bounded([{'label': row.label, 'argv': list(row.argv),
        'env': [list(pair) for pair in row.env], 'returncode': row.returncode,
        'stdout_hex': row.stdout.hex(), 'stderr_hex': row.stderr.hex()} for row in observations],
        2 * _MAX_RAW + 65536)


def _decode_raw(raw):
    rows = decode(raw, maximum=2 * _MAX_RAW + 65536)
    if type(rows) is not list or len(rows) != 5:
        raise PreDriverCheckpointError('retained observation cardinality differs')
    fields = {'label', 'argv', 'env', 'returncode', 'stdout_hex', 'stderr_hex'}
    for row in rows:
        if (type(row) is not dict or set(row) != fields or type(row['argv']) is not list
                or type(row['env']) is not list or any(type(pair) is not list for pair in row['env'])
                or type(row['stdout_hex']) is not str or type(row['stderr_hex']) is not str):
            raise PreDriverCheckpointError('retained observation shape differs')
    observations = tuple(RawObservation(row['label'], tuple(row['argv']), tuple(map(tuple, row['env'])),
        row['returncode'], bytes.fromhex(row['stdout_hex']), bytes.fromhex(row['stderr_hex'])) for row in rows)
    if _raw_bytes(observations) != raw:
        raise PreDriverCheckpointError('retained observations are not canonical')
    return observations


def _compute(context, policy_checkpoint_bytes, observations):
    _context(context)
    policy = decode_policy_stage_checkpoint(policy_checkpoint_bytes, context)
    raw = _raw_bytes(observations)
    if (tuple((r.label, r.argv, r.env) for r in observations) != pre_driver_observation_specs(policy.owned_identity)
            or any(r.returncode != 0 or r.stderr for r in observations)):
        raise PreDriverCheckpointError('pre-driver observation registry or transport differs')
    if _cluster(context, observations).outcome != 'complete':
        raise PreDriverCheckpointError('cluster identity did not revalidate')
    def projection(row):
        document = decode(row.stdout)
        if type(document) is not list or len(document) != 1 or type(document[0]) is not dict:
            raise PreDriverCheckpointError('node bracket is ambiguous')
        node = document[0]
        return (node['Name'], node['Id'], node['Image'], node['Config']['Image'], node['Config']['Labels'])
    if projection(observations[0]) != projection(observations[2]):
        raise PreDriverCheckpointError('node changed across pre-driver stage')
    ownership = validate_pre_driver_ownership(profile=policy.profile, workload=policy.workload,
        rendered_objects=policy.rendered_objects, owned_identity=policy.owned_identity,
        runtime_objects=observations[1].stdout)
    runtime = validate_pre_driver_runtime(ownership=ownership,
        node_images=reconstruct_prior_node_image_references(context))
    desired = decode(policy.policy_request)['items']
    keys = {(r.kind, r.namespace, r.name) for r in policy.bindings}
    selected = [row for row in decode(observations[1].stdout, maximum=_MAX_RAW)['items']
        if (row['kind'], row['metadata'].get('namespace', ''), row['metadata']['name']) in keys]
    validate_applied_objects(desired, canonical({'apiVersion': 'v1', 'kind': 'List', 'items': selected}))
    final = {(row['kind'], row['metadata'].get('namespace', ''), row['metadata']['name']): row['metadata']
             for row in selected}
    if len(selected) != 18 or len(final) != 18:
        raise PreDriverCheckpointError('current policy set is not exact')
    continuity = []
    for row in policy.bindings:
        metadata = final[(row.kind, row.namespace, row.name)]
        if metadata.get('uid') != row.uid:
            raise PreDriverCheckpointError('policy UID continuity changed')
        continuity.append(PolicyContinuityBinding(row.kind, row.namespace, row.name, row.uid,
            row.resource_version, metadata.get('resourceVersion')))
    return raw, runtime, tuple(sorted(continuity))


@dataclass(frozen=True, slots=True)
class PreDriverCheckpointProof:
    context: ExpectedContext
    policy_checkpoint_bytes: bytes
    raw_observations: bytes
    runtime: PreDriverRuntimeProof
    policy_continuity: tuple[PolicyContinuityBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if self.runtime_contract_complete is not False or self.full_application_contract_complete is not False:
                raise PreDriverCheckpointError('pre-driver checkpoint cannot claim completion')
            if (type(self.runtime) is not PreDriverRuntimeProof or type(self.policy_continuity) is not tuple
                    or len(self.policy_continuity) != 18
                    or any(type(row) is not PolicyContinuityBinding for row in self.policy_continuity)):
                raise PreDriverCheckpointError('retained derived proof types differ')
            self.runtime.__post_init__()
            for row in self.policy_continuity: row.__post_init__()
            expected = _compute(self.context, self.policy_checkpoint_bytes, _decode_raw(self.raw_observations))
            if expected != (self.raw_observations, self.runtime, self.policy_continuity):
                raise PreDriverCheckpointError('retained proof differs from raw reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError) as error:
            if isinstance(error, PreDriverCheckpointError): raise
            raise PreDriverCheckpointError('invalid retained pre-driver checkpoint') from error


def validate_pre_driver_checkpoint(*, context, policy_checkpoint_bytes, observations):
    try:
        raw, runtime, continuity = _compute(context, policy_checkpoint_bytes, observations)
        return PreDriverCheckpointProof(context, policy_checkpoint_bytes, raw, runtime, continuity)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError) as error:
        if isinstance(error, PreDriverCheckpointError): raise
        raise PreDriverCheckpointError('invalid pre-driver checkpoint evidence') from error


def encode_pre_driver_checkpoint(context, policy_checkpoint_bytes, observations):
    proof = validate_pre_driver_checkpoint(context=context, policy_checkpoint_bytes=policy_checkpoint_bytes,
                                          observations=observations)
    return _canonical_bounded({'schema': _SCHEMA, 'run_id': context.run_id,
        'intent_sequence': context.intent_sequence, 'context_commitment': context.commitment,
        'policy_checkpoint': decode(proof.policy_checkpoint_bytes, maximum=3 * 1024 * 1024),
        'observations': decode(proof.raw_observations, maximum=2 * _MAX_RAW + 65536)}, _MAX_BYTES)


def decode_pre_driver_checkpoint(payload, context):
    _context(context)
    document = decode(payload, maximum=_MAX_BYTES)
    if (type(document) is not dict or set(document) != {'schema', 'run_id', 'intent_sequence',
            'context_commitment', 'policy_checkpoint', 'observations'}
            or _canonical_bounded(document, _MAX_BYTES) != payload or document['schema'] != _SCHEMA
            or type(document['intent_sequence']) is not int
            or document['intent_sequence'] != context.intent_sequence or document['run_id'] != context.run_id
            or document['context_commitment'] != context.commitment):
        raise PreDriverCheckpointError('checkpoint does not bind exact historical context')
    return validate_pre_driver_checkpoint(context=context,
        policy_checkpoint_bytes=_canonical_bounded(document['policy_checkpoint'], 3 * 1024 * 1024),
        observations=_decode_raw(_canonical_bounded(document['observations'], 2 * _MAX_RAW + 65536)))


def publish_pre_driver_checkpoint(path: Path, context, observations):
    """Publish once while the authenticated application intent remains pending."""
    _context(context)
    with _journal_append_lock(path):
        value = load_journal(path)
        events = value['events']
        if (value['teardown_from_sequence'] is not None or value['expected_inputs_sha256'] is None
                or value['run_id'] != context.run_id or not events
                or events[-1]['sequence'] != context.intent_sequence
                or events[-1]['event'] != 'application_apply_intent'
                or events[-1]['details'] != decode(context.intent)
                or load_expected_context(path, value) != context):
            raise PreDriverCheckpointError('checkpoint context is stale, unbound, or teardown-only')
        policy = read_policy_stage_checkpoint_bytes(path, context)
        payload = encode_pre_driver_checkpoint(context, policy, observations)
        proof = decode_pre_driver_checkpoint(payload, context)
        _, private = _private_location(path, create_parent=False)
        _publish_observed_proof(private, f'pre-driver-stage-{context.intent_sequence}.json', payload)
        return proof


def read_pre_driver_checkpoint_bytes(path: Path, context, *, maximum=_MAX_BYTES):
    """Read historical bytes; no collection or recovery fallback is available."""
    _context(context)
    if type(maximum) is not int or not 1 <= maximum <= _MAX_BYTES:
        raise PreDriverCheckpointError('checkpoint reader bound is invalid')
    _, private = _private_location(path, create_parent=False)
    payload = _read_checkpoint_bytes(private, f'pre-driver-stage-{context.intent_sequence}.json',
                                     maximum, PreDriverCheckpointError)
    decode_pre_driver_checkpoint(payload, context)
    return payload


def read_pre_driver_checkpoint(path: Path, context):
    return decode_pre_driver_checkpoint(read_pre_driver_checkpoint_bytes(path, context), context)
