"""Pure version-one terminal composition; platform admission remains pending."""
from kil.v3b2_proofs import (ProofError, ProofDecision, RawObservation, decode, _cluster,
    reconstruct_prior_node_image_references)
from kil.v3b2_application_evidence_budget import validate_application_bundle_budget
from kil.v3b2_pre_driver_checkpoint import pre_driver_observation_specs
from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_manifests import WorkloadIdentity, render_objects
from kil.v3b2_runtime_ownership import validate_runtime_ownership
from kil.v3b2_generated_kil_pod_configuration import validate_generated_kil_pod_configuration
from kil.v3b2_runtime_endpoints import validate_runtime_endpoints
from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
from kil.v3b2_application_runtime_boundary import validate_application_runtime_boundary


def validate_application_terminal(context, observations):
    validate_application_bundle_budget(context, observations, ProofDecision('unknown', 'abandoned'))
    inputs = decode(context.inputs)
    identity = OwnedIdentity(**inputs['owned_identity'])
    specs = (('pre_driver_checkpoint', (), ()), *pre_driver_observation_specs(identity))
    if (type(observations) is not tuple or len(observations) != len(specs)
            or any(type(row) is not RawObservation for row in observations)):
        raise ProofError('application terminal observation types differ')
    for row in observations:
        row.__post_init__()
    if (tuple((r.label, r.argv, r.env) for r in observations) != specs
            or any(r.returncode != 0 or r.stderr for r in observations)):
        raise ProofError('application terminal registry or transport differs')
    if _cluster(context, observations).outcome != 'complete':
        raise ProofError('application cluster bracket differs')
    def projection(row):
        value = decode(row.stdout)
        if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
            raise ProofError('application node bracket is ambiguous')
        node = value[0]
        return node['Name'], node['Id'], node['Image'], node['Config']['Image'], node['Config']['Labels']
    if projection(observations[1]) != projection(observations[3]):
        raise ProofError('application node changed across bracket')
    profile = V3B2Profile.from_mapping(inputs['profile'])
    workload = WorkloadIdentity(**inputs['workload'])
    ownership = validate_runtime_ownership(profile=profile, workload=workload,
        rendered_objects=render_objects(profile, workload), owned_identity=identity,
        runtime_objects=observations[2].stdout)
    runtime = validate_kil_pod_runtime(
        configuration=validate_generated_kil_pod_configuration(ownership=ownership),
        endpoints=validate_runtime_endpoints(ownership=ownership),
        node_images=reconstruct_prior_node_image_references(context))
    boundary = validate_application_runtime_boundary(context=context,
        pre_driver_checkpoint_bytes=observations[0].stdout, runtime=runtime)
    if 'prior_service_bindings' in inputs:
        from kil.v3b2_service_bindings import validate_service_allocations
        configuration = boundary.application_boundary.configuration
        continuity = validate_service_allocations(
            [row for row in decode(configuration.applied_objects)['items'] if row['kind'] == 'Service'],
            profile=profile, workload=workload, prior_bindings=inputs['prior_service_bindings'])
        if configuration.service_bindings != continuity.bindings:
            raise ProofError('application Service bindings differ across validators')
    return ProofDecision('unknown', 'platform_admission_terminal_gate_pending', boundary.summary())
