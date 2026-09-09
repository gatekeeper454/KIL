"""One local-path Pod's expected Kind default-profile configuration, not runtime.

Template authority is the independent Kind v0.32.0 local_path_parent_objects
factory. Kubernetes v1.36.1 controller, serviceaccount, priority and
defaulttolerationseconds admission supply generated metadata, the 3607-second
projected token and ordered tolerations. Safe suffix alphabet comes from
apimachinery/pkg/util/rand/rand.go. Priority zero assumes the fixed profile has
no global-default PriorityClass; this comparison does not independently certify
the cluster's effective PriorityClasses or admission state. The BestEffort
source receives no memory-pressure toleration in the reviewed default profile.

No mounted bytes, helper behavior, actual image identity, token issuance,
readiness, status IPs, endpoints or cross-family CNI uniqueness are established.
Raw status remains uninterpreted in the exact retained parent proof.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import re

from kil.v3b2_api_defaults import _equal, matches_configuration
from kil.v3b2_local_path_parent_configuration import LocalPathParentConfigurationProof, local_path_parent_objects
from kil.v3b2_driver_pod_configuration import _uid, _rv, _timestamp, _TOLERATIONS, _cni_annotations

_NAMESPACE = 'local-path-storage'
_NAME = 'local-path-provisioner'
_METADATA = {'name', 'namespace', 'generateName', 'labels', 'ownerReferences', 'uid',
             'resourceVersion', 'generation', 'creationTimestamp'}
_TOKEN_NAME = r'kube-api-access-[bcdfghjklmnpqrstvwxz2456789]{5}'


class LocalPathPodConfigurationError(ValueError):
    """Evidence differs from the reviewed generated local-path Pod."""


@dataclass(frozen=True, slots=True)
class LocalPathPodConfigurationBinding:
    namespace: str
    name: str
    uid: str
    resource_version: str
    token_volume_name: str

    def __post_init__(self):
        try:
            if (type(self.namespace) is not str or self.namespace != _NAMESPACE
                    or type(self.name) is not str
                    or re.fullmatch(r'local-path-provisioner-[a-z0-9-]{1,231}', self.name) is None
                    or type(self.token_volume_name) is not str
                    or re.fullmatch(_TOKEN_NAME, self.token_volume_name) is None):
                raise LocalPathPodConfigurationError('invalid local-path Pod binding')
            _uid(self.uid); _rv(self.resource_version)
        except (ValueError, TypeError) as error:
            if isinstance(error, LocalPathPodConfigurationError): raise
            raise LocalPathPodConfigurationError('invalid local-path Pod API identity') from error


def _compute(parent):
    if type(parent) is not LocalPathParentConfigurationProof:
        raise LocalPathPodConfigurationError('parent dependency must be exact')
    # Reconstruct all retained authority before decoding raw evidence here.
    parent.__post_init__()
    ownership = parent.ownership
    selected = [b for b in ownership.deployment_ownership.bindings
                if (b.namespace, b.deployment_name) == (_NAMESPACE, _NAME)]
    if len(selected) != 1 or len(selected[0].pods) != 1:
        raise LocalPathPodConfigurationError('expected sole local-path one-Pod chain')
    binding = selected[0]
    name, uid, rv = binding.pods[0]
    rows = json.loads(ownership.runtime_objects)['items']
    candidates = [r for r in rows if r['kind'] == 'Pod' and r['metadata'].get('namespace') == _NAMESPACE
                  and r['metadata']['name'] == name]
    if len(candidates) != 1:
        raise LocalPathPodConfigurationError('missing or duplicate local-path Pod')
    pod = candidates[0]
    if set(pod) not in ({'apiVersion', 'kind', 'metadata', 'spec'},
                        {'apiVersion', 'kind', 'metadata', 'spec', 'status'}):
        raise LocalPathPodConfigurationError('unreviewed Pod root')
    metadata, spec = pod['metadata'], pod['spec']
    if not _METADATA <= metadata.keys() or metadata.keys() - (_METADATA | {'annotations', 'managedFields'}):
        raise LocalPathPodConfigurationError('incomplete or unreviewed Pod metadata')
    _uid(metadata['uid']); _rv(metadata['resourceVersion']); _timestamp(metadata['creationTimestamp'])
    if (metadata['name'] != name or metadata['namespace'] != _NAMESPACE or metadata['uid'] != uid
            or metadata['resourceVersion'] != rv or metadata['generateName'] != binding.replica_set_name + '-'
            or type(metadata['generation']) is not int or metadata['generation'] != 1):
        raise LocalPathPodConfigurationError('Pod incarnation differs from ownership')
    owner = {'apiVersion': 'apps/v1', 'kind': 'ReplicaSet', 'name': binding.replica_set_name,
             'uid': binding.replica_set_uid, 'controller': True, 'blockOwnerDeletion': True}
    if not _equal(metadata['ownerReferences'], [owner]):
        raise LocalPathPodConfigurationError('Pod owner is not exact')
    if type(spec) is not dict or type(spec.get('priority')) is not int or spec['priority'] != 0:
        raise LocalPathPodConfigurationError('Pod priority is not exact')
    annotations = metadata.get('annotations', {})
    if type(annotations) is not dict:
        raise LocalPathPodConfigurationError('annotations must be exact dict')
    cni, _, sandbox = _cni_annotations(annotations, spec, ownership.profile)
    if not _equal(annotations, cni):
        raise LocalPathPodConfigurationError('only reviewed CNI ADD annotations are admitted')
    if sandbox is not None and sandbox == ownership.owned_identity.node_container_id:
        raise LocalPathPodConfigurationError('Pod CNI sandbox collides with owned Node')
    volumes = spec.get('volumes')
    if type(volumes) is not list or len(volumes) != 2 or type(volumes[1]) is not dict:
        raise LocalPathPodConfigurationError('expected config and token volumes')
    token = volumes[1].get('name')
    if type(token) is not str or re.fullmatch(_TOKEN_NAME, token) is None:
        raise LocalPathPodConfigurationError('invalid projected token name')
    # Only the fresh independent source template supplies expected configuration.
    template = local_path_parent_objects()[0]['spec']['template']
    desired = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {
        'name': name, 'namespace': _NAMESPACE, 'generateName': binding.replica_set_name + '-',
        'labels': {'app': _NAME, 'pod-template-hash': binding.pod_template_hash},
        'ownerReferences': [owner]}, 'spec': deepcopy(template['spec'])}
    # Locally admit an explicitly empty map without changing shared normalization.
    if 'annotations' in metadata: desired['metadata']['annotations'] = cni
    admitted = desired['spec']
    admitted.update(priority=0, preemptionPolicy='PreemptLowerPriority',
        tolerations=deepcopy(template['spec']['tolerations']) + deepcopy(_TOLERATIONS))
    admitted['volumes'].append({'name': token, 'projected': {'defaultMode': 420, 'sources': [
        {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 3607}},
        {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}},
        {'downwardAPI': {'items': [{'path': 'namespace', 'fieldRef': {
            'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}]}}]}})
    admitted['containers'][0]['volumeMounts'].append({'name': token, 'readOnly': True,
        'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount'})
    if 'nodeName' in spec:
        node = ownership.owned_identity.kind_cluster + '-control-plane'
        if type(spec['nodeName']) is not str or spec['nodeName'] != node:
            raise LocalPathPodConfigurationError('Pod scheduling differs from owned Node')
        admitted['nodeName'] = node
    if not matches_configuration(desired, pod):
        raise LocalPathPodConfigurationError('Pod differs from independent admitted configuration')
    return (LocalPathPodConfigurationBinding(_NAMESPACE, name, uid, rv, token),)


@dataclass(frozen=True, slots=True)
class LocalPathPodConfigurationProof:
    parent: LocalPathParentConfigurationProof
    bindings: tuple[LocalPathPodConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in
                   (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise LocalPathPodConfigurationError('Pod configuration cannot establish completion')
            if (type(self.bindings) is not tuple or len(self.bindings) != 1
                    or type(self.bindings[0]) is not LocalPathPodConfigurationBinding):
                raise LocalPathPodConfigurationError('expected one exact Pod binding')
            self.bindings[0].__post_init__()
            if self.bindings != _compute(self.parent):
                raise LocalPathPodConfigurationError('Pod binding differs from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, LocalPathPodConfigurationError): raise
            raise LocalPathPodConfigurationError('invalid local-path Pod proof') from error


def validate_local_path_pod_configuration(*, parent):
    """Validate the full expected Pod configuration and retain the exact parent."""
    try:
        return LocalPathPodConfigurationProof(parent, _compute(parent))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, LocalPathPodConfigurationError): raise
        raise LocalPathPodConfigurationError('invalid local-path Pod configuration source') from error
