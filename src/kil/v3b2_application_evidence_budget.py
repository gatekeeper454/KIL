"""Pure operation-local budgets for application-source v1 evidence.

Callers authenticate ExpectedContext independently. Strict helpers require the
immutable opt-in marker; dispatch discovery alone preserves marker-absent
legacy behavior. These checks permit bounded missing, failed and corrupt
sources so an unknown/abandoned terminal proof remains serializable. Registry
and source semantics belong to subsequent proof validation.
"""
from __future__ import annotations

MAX_APPLICATION_CHECKPOINT_BYTES = 20 * 1024 * 1024
MAX_APPLICATION_OBSERVATION_BYTES = 8 * 1024 * 1024
MAX_APPLICATION_INPUT_BYTES = 5 * 1024 * 1024
MAX_APPLICATION_BINDING_BYTES = 1024 * 1024
MAX_APPLICATION_METADATA_BYTES = 1024 * 1024


def application_source_enabled(inputs: dict) -> bool:
    from kil.v3b2_proofs import ProofError
    if type(inputs) is not dict:
        raise ProofError('application source inputs are not an exact object')
    if 'application_source_version' not in inputs:
        return False
    version = inputs['application_source_version']
    if type(version) is not int or version != 1:
        raise ProofError('application source version is invalid')
    return True


def validate_application_context_budget(context) -> None:
    """Strict opt-in context check; byte caps precede any context decoding."""
    from kil.v3b2_proofs import ExpectedContext, ProofError, decode
    if type(context) is not ExpectedContext or context.family != 'application_apply':
        raise ProofError('application budget requires an application context')
    if (type(context.inputs) is not bytes or len(context.inputs) > MAX_APPLICATION_INPUT_BYTES
            or type(context.intent) is not bytes or len(context.intent) > MAX_APPLICATION_METADATA_BYTES):
        raise ProofError('application context exceeds its byte bound')
    context.__post_init__()
    if not application_source_enabled(decode(context.inputs)):
        raise ProofError('application budget requires the immutable source opt-in')


def validate_application_dispatch_budget(context, observations=()) -> bool:
    """Discover opt-in under the existing global input bound; preflight requests.

    Pass prospective RawObservations with empty output bytes before dispatch.
    Marker discovery must decode inputs; callers already selecting the new path
    should call the strict context helper first for its smaller predecode cap.
    """
    from kil.v3b2_proofs import ExpectedContext, ProofDecision, ProofError, decode
    if type(context) is not ExpectedContext:
        raise ProofError('application dispatch context is invalid')
    if context.family != 'application_apply':
        return False
    if not application_source_enabled(decode(context.inputs)):
        return False
    validate_application_bundle_budget(context, observations, ProofDecision('unknown', 'abandoned'))
    return True


def _metadata(context, rows, outcome, category):
    from kil.v3b2_proofs import decode
    # The commitment has a fixed width. Computing it here would allocate the
    # full expected-input representation before the metadata preflight.
    return _bounded({
        'schema_version': 'kil.v3b2-observed-proof.v1', 'run_id': context.run_id,
        'intent_sequence': context.intent_sequence, 'family': context.family,
        'expected_sha256': '0' * 64, 'outcome': outcome,
        'expected_inputs': {}, 'intent': decode(context.intent), 'category': category,
        'bindings': {}, 'observations': rows,
    }, MAX_APPLICATION_METADATA_BYTES)


def _bounded(value, maximum):
    from kil.v3b2_proofs import ProofError, _canonical_bounded
    try:
        return _canonical_bounded(value, maximum)
    except (ValueError, RecursionError, OverflowError) as error:
        raise ProofError('application evidence cannot fit its canonical byte bound') from error


def _row_metadata(label, argv, env, returncode):
    from kil.v3b2_proofs import ProofError
    if (type(label) is not str or not label or type(returncode) is not int
            or type(argv) not in (list, tuple) or any(type(arg) is not str for arg in argv)
            or type(env) not in (list, tuple)
            or any(type(pair) not in (list, tuple) or len(pair) != 2
                   or any(type(value) is not str for value in pair) for pair in env)):
        raise ProofError('application observation metadata types are invalid')
    return {'label': label, 'argv': list(argv), 'env': [list(pair) for pair in env],
            'returncode': returncode, 'stdout_hex': '', 'stderr_hex': ''}


def _aggregate(checkpoint, current, label, size):
    from kil.v3b2_proofs import ProofError
    if label == 'pre_driver_checkpoint':
        checkpoint += size
    else:
        current += size
    if checkpoint > MAX_APPLICATION_CHECKPOINT_BYTES or current > MAX_APPLICATION_OBSERVATION_BYTES:
        raise ProofError('application raw evidence exceeds its aggregate byte bound')
    return checkpoint, current


def validate_application_bundle_budget(context, observations, decision) -> None:
    """Strict writer/preflight guard. Never allocates hexadecimal output bytes."""
    from kil.v3b2_proofs import ProofDecision, ProofError, RawObservation
    if (type(decision) is not ProofDecision or type(decision.bindings) is not bytes
            or len(decision.bindings) > MAX_APPLICATION_BINDING_BYTES):
        raise ProofError('application bindings exceed their byte bound')
    validate_application_context_budget(context)
    decision.__post_init__()
    if type(decision.outcome) is not str or type(decision.category) is not str:
        raise ProofError('application decision types are invalid')
    if type(observations) is not tuple:
        raise ProofError('application observations must be an exact tuple')
    checkpoint = current = 0
    rows = []
    for row in observations:
        if type(row) is not RawObservation:
            raise ProofError('application observation type is invalid')
        row.__post_init__()
        checkpoint, current = _aggregate(checkpoint, current, row.label, len(row.stdout) + len(row.stderr))
        rows.append(_row_metadata(row.label, row.argv, row.env, row.returncode))
    _metadata(context, rows, decision.outcome, decision.category)


def validate_application_encoded_budget(context, document) -> None:
    """Strict replay guard before bytes.fromhex or historical-source decoding.

    document must have been decoded under the global 64MiB proof bound. The
    caller independently authenticates context, and subsequently validates the
    complete proof schema/commitment and hexadecimal character contents.
    """
    from kil.v3b2_proofs import ProofError
    validate_application_context_budget(context)
    fields = {'schema_version', 'run_id', 'intent_sequence', 'family',
              'expected_sha256', 'outcome', 'expected_inputs', 'intent',
              'category', 'bindings', 'observations'}
    if type(document) is not dict or set(document) != fields:
        raise ProofError('application encoded envelope fields are invalid')
    if type(document['bindings']) is not dict or type(document['expected_inputs']) is not dict:
        raise ProofError('application encoded inputs or bindings are invalid')
    _bounded(document['bindings'], MAX_APPLICATION_BINDING_BYTES)
    _bounded(document['expected_inputs'], MAX_APPLICATION_INPUT_BYTES)
    if type(document['observations']) is not list:
        raise ProofError('application encoded observations are invalid')
    rows = []
    checkpoint = current = 0
    for row in document['observations']:
        if (type(row) is not dict
                or set(row) != {'label', 'argv', 'env', 'returncode', 'stdout_hex', 'stderr_hex'}
                or type(row['argv']) is not list or type(row['env']) is not list):
            raise ProofError('application encoded observation fields are invalid')
        size = 0
        for key in ('stdout_hex', 'stderr_hex'):
            value = row[key]
            if type(value) is not str or len(value) % 2:
                raise ProofError('application encoded raw evidence has invalid width')
            size += len(value) // 2
        checkpoint, current = _aggregate(checkpoint, current, row['label'], size)
        rows.append(_row_metadata(row['label'], row['argv'], row['env'], row['returncode']))
    # Preserve every actual envelope field to account for hostile metadata;
    # substitutes omit only the independently budgeted components.
    skeleton = {**document, 'expected_inputs': {}, 'bindings': {}, 'observations': rows}
    _bounded(skeleton, MAX_APPLICATION_METADATA_BYTES)
