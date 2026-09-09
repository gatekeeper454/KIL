"""Fresh Calico controller configuration only, from authenticated source bytes.

Reviewed Kubernetes v1.36.1 GetPodFromTemplate copies labels, annotations and
finalizers only (pkg/controller/controller_utils.go). ServiceAccount admission
adds the correlated projected token volume (plugin/pkg/admission/serviceaccount/
admission.go); pkg/serviceaccount/claims.go defines the 3607-second request.
Names use apimachinery/pkg/util/rand/rand.go's safe random alphabet. Priority
and preemption expectations follow pkg/apis/scheduling/v1/defaults.go and
helpers.go. These comparisons do NOT establish actual PriorityClass or admission
plugin configuration, token issuance, mounted bytes, readiness or runtime image
identity. Raw status is retained uninterpreted. No filesystem or live access.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import re

from kil.v3b2_api_defaults import _equal, matches_configuration
from kil.v3b2_driver_pod_configuration import _precheck, _uid, _rv, _timestamp, _TOLERATIONS, _cni_annotations
from kil.v3b2_proofs import calico_objects
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof

_NAME = 'calico-kube-controllers'
_NAMESPACE = 'kube-system'
_METADATA = {'name', 'namespace', 'generateName', 'labels', 'ownerReferences', 'uid',
             'resourceVersion', 'generation', 'creationTimestamp'}
_TOKEN_NAME = r'kube-api-access-[bcdfghjklmnpqrstvwxz2456789]{5}'


class CalicoControllerConfigurationError(ValueError):
    """Evidence differs from the reviewed configuration contract."""


@dataclass(frozen=True, slots=True)
class CalicoControllerConfigurationBinding:
    namespace: str
    deployment_name: str
    replica_set_name: str
    name: str
    uid: str
    resource_version: str

    def __post_init__(self):
        if (type(self.namespace) is not str or self.namespace != _NAMESPACE
                or type(self.deployment_name) is not str or self.deployment_name != _NAME):
            raise CalicoControllerConfigurationError('unexpected controller binding')
        for name in (self.replica_set_name, self.name):
            if type(name) is not str or re.fullmatch(r'[a-z0-9][a-z0-9-]{0,252}', name) is None:
                raise CalicoControllerConfigurationError('invalid generated name')
        try:
            _uid(self.uid); _rv(self.resource_version)
        except ValueError as error:
            raise CalicoControllerConfigurationError('invalid binding API identity') from error


def _compute(ownership, source, projection):
    for raw in (source, projection):
        if type(raw) is not bytes or not 1 <= len(raw) <= 2 * 1024 * 1024:
            raise CalicoControllerConfigurationError('authority must be bounded exact bytes')
    expected = calico_objects(source, projection)
    if type(ownership) is not RuntimeOwnershipProof:
        raise CalicoControllerConfigurationError('ownership dependency must be exact')
    ownership.__post_init__()
    selected = [b for b in ownership.deployment_ownership.bindings
                if (b.namespace, b.deployment_name) == (_NAMESPACE, _NAME)]
    if len(selected) != 1 or len(selected[0].pods) != 1:
        raise CalicoControllerConfigurationError('expected one controller owner chain')
    binding = selected[0]
    rows = json.loads(ownership.runtime_objects)['items']

    def one(objects, kind, name):
        found = [r for r in objects if r['kind'] == kind and r['metadata'].get('namespace') == _NAMESPACE
                 and r['metadata']['name'] == name]
        if len(found) != 1: raise CalicoControllerConfigurationError('missing or duplicate configuration object')
        return found[0]

    deployment = one(expected, 'Deployment', _NAME)
    account = one(expected, 'ServiceAccount', _NAME)
    for desired in (deployment, account):
        observed = one(rows, desired['kind'], _NAME)
        if not matches_configuration(desired, observed):
            raise CalicoControllerConfigurationError('runtime controller or account differs from pinned configuration')
    template = deployment['spec']['template']
    name, uid, rv = binding.pods[0]
    pod = one(rows, 'Pod', name)
    _precheck(pod, 0, [0])
    if set(pod) not in ({'apiVersion', 'kind', 'metadata', 'spec'},
                         {'apiVersion', 'kind', 'metadata', 'spec', 'status'}):
        raise CalicoControllerConfigurationError('unreviewed Pod root fields')
    metadata, spec = pod['metadata'], pod['spec']
    allowed = _METADATA | {'annotations', 'managedFields'}
    if 'finalizers' in template['metadata']: allowed.add('finalizers')
    if not _METADATA <= metadata.keys() or metadata.keys() - allowed:
        raise CalicoControllerConfigurationError('unreviewed generated metadata')
    _uid(metadata['uid']); _rv(metadata['resourceVersion']); _timestamp(metadata['creationTimestamp'])
    if (metadata['name'] != name or metadata['namespace'] != _NAMESPACE or metadata['uid'] != uid
            or metadata['resourceVersion'] != rv or metadata['generateName'] != binding.replica_set_name + '-'
            or type(metadata['generation']) is not int or metadata['generation'] != 1):
        raise CalicoControllerConfigurationError('generated incarnation differs')
    owner = {'apiVersion': 'apps/v1', 'kind': 'ReplicaSet', 'name': binding.replica_set_name,
             'uid': binding.replica_set_uid, 'controller': True, 'blockOwnerDeletion': True}
    if not _equal(metadata['ownerReferences'], [owner]):
        raise CalicoControllerConfigurationError('generated owner differs')
    if type(spec) is not dict or type(spec.get('priority')) is not int or spec['priority'] != 2000000000:
        raise CalicoControllerConfigurationError('controller priority differs')
    annotations = metadata.get('annotations', {})
    if type(annotations) is not dict: raise CalicoControllerConfigurationError('invalid annotations')
    cni, _, sandbox = _cni_annotations(annotations, spec, ownership.profile)
    if sandbox is not None and sandbox == ownership.owned_identity.node_container_id:
        raise CalicoControllerConfigurationError('CNI sandbox collides with owned Node')
    volumes = spec.get('volumes')
    if type(volumes) is not list or len(volumes) != 1 or type(volumes[0]) is not dict:
        raise CalicoControllerConfigurationError('expected one projected token volume')
    token_name = volumes[0].get('name')
    if type(token_name) is not str or re.fullmatch(_TOKEN_NAME, token_name) is None:
        raise CalicoControllerConfigurationError('token volume name differs from producer grammar')
    desired = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {
        key: deepcopy(value) for key, value in template['metadata'].items()
        if key in {'labels', 'annotations', 'finalizers'}}, 'spec': deepcopy(template['spec'])}
    desired['metadata'].update(name=name, namespace=_NAMESPACE, generateName=binding.replica_set_name + '-',
                               ownerReferences=[owner])
    desired['metadata']['labels']['pod-template-hash'] = binding.pod_template_hash
    if cni: desired['metadata'].setdefault('annotations', {}).update(cni)
    desired['spec'].update(priority=2000000000, preemptionPolicy='PreemptLowerPriority',
        tolerations=deepcopy(template['spec']['tolerations']) + deepcopy(_TOLERATIONS),
        volumes=[{'name': token_name, 'projected': {'defaultMode': 420, 'sources': [
            {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 3607}},
            {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}},
            {'downwardAPI': {'items': [{'path': 'namespace', 'fieldRef': {
                'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}]}}]}}])
    desired['spec']['containers'][0]['volumeMounts'] = [{'name': token_name, 'readOnly': True,
        'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount'}]
    if 'nodeName' in spec:
        node = ownership.owned_identity.kind_cluster + '-control-plane'
        if type(spec['nodeName']) is not str or spec['nodeName'] != node:
            raise CalicoControllerConfigurationError('scheduling differs from owned Node')
        desired['spec']['nodeName'] = node
    if not matches_configuration(desired, pod):
        raise CalicoControllerConfigurationError('generated configuration differs from independent admitted template')
    return (CalicoControllerConfigurationBinding(_NAMESPACE, _NAME, binding.replica_set_name, name, uid, rv),)


@dataclass(frozen=True, slots=True)
class CalicoControllerConfigurationProof:
    ownership: RuntimeOwnershipProof
    calico_source: bytes
    calico_projection: bytes
    bindings: tuple[CalicoControllerConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise CalicoControllerConfigurationError('configuration cannot establish completion')
            if type(self.bindings) is not tuple or len(self.bindings) != 1:
                raise CalicoControllerConfigurationError('expected one exact binding')
            if type(self.bindings[0]) is not CalicoControllerConfigurationBinding:
                raise CalicoControllerConfigurationError('binding type must be exact')
            self.bindings[0].__post_init__()
            if self.bindings != _compute(self.ownership, self.calico_source, self.calico_projection):
                raise CalicoControllerConfigurationError('binding differs from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, CalicoControllerConfigurationError): raise
            raise CalicoControllerConfigurationError('invalid controller configuration proof') from error


def validate_calico_controller_configuration(*, ownership, calico_source, calico_projection):
    """Compare complete retained configuration; never certify status or tokens."""
    try:
        bindings = _compute(ownership, calico_source, calico_projection)
        return CalicoControllerConfigurationProof(ownership, calico_source, calico_projection, bindings)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, CalicoControllerConfigurationError): raise
        raise CalicoControllerConfigurationError('invalid controller configuration source') from error
