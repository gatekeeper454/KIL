"""Bind public images to the private readiness selection for opted-in runs.

Callers MUST authenticate ExpectedContext by journal replay. This pure guard
corroborates the historical node image source, then compares the exact rows
selected by readiness replay. It does not authenticate a supplied context,
replace the full public semantic validator, or establish new Calico CRI proof.
"""
import re

from kil.v3b2_proofs import (
    ExpectedContext, ProofError, canonical, decode,
    reconstruct_prior_node_image_references,
)


def validate_public_image_provenance(context: ExpectedContext, manifest_bytes: bytes) -> None:
    if type(context) is not ExpectedContext:
        raise ProofError('public image provenance context is invalid')
    context.__post_init__()
    if context.family != 'publication':
        raise ProofError('public image provenance requires pending publication')
    inputs = decode(context.inputs)
    if 'node_image_source_version' not in inputs:
        # Only this new guard is skipped; no global legacy replay claim.
        return
    version = inputs['node_image_source_version']
    if type(version) is not int or version != 1:
        raise ProofError('public image provenance version is invalid')
    reconstruct_prior_node_image_references(context)
    history = inputs['history']
    readiness = [row for row in history if row['event'] == 'readiness_complete']
    image_load = [row for row in history if row['event'] == 'image_load_complete']
    if len(readiness) != 1 or len(image_load) != 1:
        raise ProofError('public image provenance lacks unique readiness')
    ready, loaded = readiness[0], image_load[0]
    digest = ready['details'].get('observed_proof_sha256')
    if (type(ready['sequence']) is not int
            or not loaded['sequence'] < ready['sequence'] < context.intent_sequence
            or history.index(loaded) >= history.index(ready)
            or type(digest) is not str or re.fullmatch(r'[0-9a-f]{64}', digest) is None):
        raise ProofError('public image provenance readiness is invalid')
    manifest = decode(manifest_bytes)
    if type(manifest) is not dict or type(manifest.get('topology_attestation')) is not dict:
        raise ProofError('public image provenance manifest is invalid')
    topology = manifest['topology_attestation']
    rows = inputs.get('source_images')
    if (type(rows) is not list or len(rows) != 17
            or canonical(rows) != canonical(topology.get('pod_images'))):
        raise ProofError('public images differ from replayed readiness selection')
    identity = inputs['owned_identity']
    if (manifest.get('run_id') != 'v3b2-' + context.run_id
            or any(topology.get(key) != identity[key]
                   for key in ('node_container_id', 'cluster_incarnation_uid'))):
        raise ProofError('public image provenance identity differs')
