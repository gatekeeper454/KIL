"""Pinned Calico-node admitted configuration, with complete source retention.

Kubernetes v1.36.1 DaemonSet CreatePodTemplate adds ordered node tolerations and
node affinity; priority and serviceaccount admission supply the reviewed additions
below. The pinned template has no annotations. Host-network Pods take containerd
2.3.1's NODE namespace path, which skips CNI setup; Calico v3.32 annotation patches
require CNI patch mode. Absence here describes expected configuration, not proof
that external actors cannot write annotations.

This pure proof does not certify runtime images, status, network namespaces,
effective privileges, token issuance, PriorityClass or admission configuration,
readiness, freshness, ComputeHash, or application completion. The inherited
revision label remains an opaque relationship. Full raw status remains retained
through the exact revision dependency and is deliberately uninterpreted.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import re

from kil.v3b2_api_defaults import _equal, _managed_fields, matches_configuration
from kil.v3b2_calico_node_revision import CalicoNodeRevisionProof
from kil.v3b2_driver_pod_configuration import _uid, _rv, _timestamp
from kil.v3b2_proofs import calico_objects

_NAME = 'calico-node'
_NAMESPACE = 'kube-system'
_TOKEN = r'kube-api-access-[bcdfghjklmnpqrstvwxz2456789]{5}'
_METADATA = {'name', 'namespace', 'uid', 'resourceVersion', 'generation',
             'creationTimestamp', 'generateName', 'labels', 'ownerReferences'}


class CalicoNodeConfigurationError(ValueError):
    """Evidence does not establish the bounded admitted configuration."""


@dataclass(frozen=True, slots=True)
class CalicoNodeConfigurationBinding:
    namespace: str
    pod_name: str
    pod_uid: str
    pod_resource_version: str
    service_account_uid: str
    service_account_resource_version: str
    token_volume_name: str

    def __post_init__(self):
        try:
            if (type(self.namespace) is not str or self.namespace != _NAMESPACE
                    or type(self.pod_name) is not str
                    or re.fullmatch(r'calico-node-[a-z0-9]{5}', self.pod_name) is None
                    or type(self.token_volume_name) is not str
                    or re.fullmatch(_TOKEN, self.token_volume_name) is None):
                raise CalicoNodeConfigurationError('invalid configuration binding')
            _uid(self.pod_uid); _rv(self.pod_resource_version)
            _uid(self.service_account_uid); _rv(self.service_account_resource_version)
            if self.pod_uid == self.service_account_uid:
                raise CalicoNodeConfigurationError('configuration incarnations collide')
        except (ValueError, TypeError) as error:
            if isinstance(error, CalicoNodeConfigurationError): raise
            raise CalicoNodeConfigurationError('invalid configuration identity') from error


def _compute(revision):
    if type(revision) is not CalicoNodeRevisionProof:
        raise CalicoNodeConfigurationError('revision dependency must be exact')
    # Revalidates bounded raw input, structural limits and every earlier
    # ownership/revision relationship before decoding or copying candidate data.
    revision.__post_init__()
    relation = revision.bindings[0]
    rows = json.loads(revision.ownership.runtime_objects)['items']
    expected = calico_objects(revision.calico_source, revision.calico_projection)

    def one(objects, kind, name):
        selected = [r for r in objects if r['kind'] == kind and
            r['metadata'].get('namespace') == _NAMESPACE and r['metadata']['name'] == name]
        if len(selected) != 1:
            raise CalicoNodeConfigurationError('missing or duplicate configuration object')
        return selected[0]

    account = one(rows, 'ServiceAccount', _NAME)
    if not matches_configuration(one(expected, 'ServiceAccount', _NAME), account):
        raise CalicoNodeConfigurationError('ServiceAccount differs from independent pinned configuration')
    pod = one(rows, 'Pod', relation.pod_name)
    if (not {'apiVersion', 'kind', 'metadata', 'spec'} <= pod.keys()
            or pod.keys() - {'apiVersion', 'kind', 'metadata', 'spec', 'status'}
            or pod['apiVersion'] != 'v1' or pod['kind'] != 'Pod'):
        raise CalicoNodeConfigurationError('unreviewed Pod root')
    metadata = pod['metadata']
    if not _METADATA <= metadata.keys() or metadata.keys() - (_METADATA | {'managedFields'}):
        raise CalicoNodeConfigurationError('unreviewed complete Pod metadata')
    _uid(metadata['uid']); _rv(metadata['resourceVersion']); _timestamp(metadata['creationTimestamp'])
    if 'managedFields' in metadata: _managed_fields(metadata['managedFields'])
    if (type(metadata['generation']) is not int or metadata['generation'] != 1
            or not _equal([metadata['name'], metadata['namespace'], metadata['uid'], metadata['resourceVersion']],
                [relation.pod_name, _NAMESPACE, relation.pod_uid, relation.pod_resource_version])
            or metadata['generateName'] != _NAME + '-'):
        raise CalicoNodeConfigurationError('Pod incarnation metadata differs')
    template = one(expected, 'DaemonSet', _NAME)['spec']['template']
    desired_meta = deepcopy(template['metadata'])
    desired_meta.update(name=relation.pod_name, namespace=_NAMESPACE, generateName=_NAME + '-',
        ownerReferences=[{'apiVersion': 'apps/v1', 'kind': 'DaemonSet', 'name': _NAME,
            'uid': relation.daemon_set_uid, 'controller': True, 'blockOwnerDeletion': True}])
    desired_meta['labels']['controller-revision-hash'] = relation.revision_label
    if not _equal(metadata['labels'], desired_meta['labels']) or not _equal(metadata['ownerReferences'], desired_meta['ownerReferences']):
        raise CalicoNodeConfigurationError('Pod labels or sole owner differ')
    candidate_spec = pod['spec']
    if type(candidate_spec) is not dict:
        raise CalicoNodeConfigurationError('Pod spec must be exact dict')
    volumes = candidate_spec.get('volumes')
    if type(volumes) is not list or len(volumes) != 13 or type(volumes[-1]) is not dict:
        raise CalicoNodeConfigurationError('expected twelve source volumes and one token volume')
    token = volumes[-1].get('name')
    if type(token) is not str or re.fullmatch(_TOKEN, token) is None:
        raise CalicoNodeConfigurationError('invalid token volume suffix')
    # Only a grammar-checked random name comes from candidate spec. All shapes
    # and values below come from pinned source and reviewed producer rules.
    spec = deepcopy(template['spec'])
    node = revision.ownership.node_ownership.node_name
    spec.update(nodeName=node, priority=2000001000, preemptionPolicy='PreemptLowerPriority',
        affinity={'nodeAffinity': {'requiredDuringSchedulingIgnoredDuringExecution': {
            'nodeSelectorTerms': [{'matchFields': [{'key': 'metadata.name', 'operator': 'In', 'values': [node]}]}]}}})
    for suffix, effect in [('not-ready', 'NoExecute'), ('unreachable', 'NoExecute'),
            ('disk-pressure', 'NoSchedule'), ('memory-pressure', 'NoSchedule'), ('pid-pressure', 'NoSchedule'),
            ('unschedulable', 'NoSchedule'), ('network-unavailable', 'NoSchedule')]:
        spec['tolerations'].append({'key': 'node.kubernetes.io/' + suffix, 'operator': 'Exists', 'effect': effect})
    spec['volumes'].append({'name': token, 'projected': {'defaultMode': 420, 'sources': [
        {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 3607}},
        {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}},
        {'downwardAPI': {'items': [{'path': 'namespace', 'fieldRef': {'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}]}}]}})
    for container in spec['initContainers'] + spec['containers']:
        container['volumeMounts'].append({'name': token, 'readOnly': True,
            'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount'})
    desired = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': desired_meta, 'spec': spec}
    if not matches_configuration(desired, pod):
        raise CalicoNodeConfigurationError('Pod differs from independent admitted configuration')
    return (CalicoNodeConfigurationBinding(_NAMESPACE, relation.pod_name, relation.pod_uid,
        relation.pod_resource_version, account['metadata']['uid'], account['metadata']['resourceVersion'], token),)


@dataclass(frozen=True, slots=True)
class CalicoNodeConfigurationProof:
    revision: CalicoNodeRevisionProof
    bindings: tuple[CalicoNodeConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise CalicoNodeConfigurationError('configuration cannot establish completion')
            if type(self.bindings) is not tuple or len(self.bindings) != 1 or type(self.bindings[0]) is not CalicoNodeConfigurationBinding:
                raise CalicoNodeConfigurationError('expected one exact configuration binding')
            self.bindings[0].__post_init__()
            if self.bindings != _compute(self.revision):
                raise CalicoNodeConfigurationError('binding differs from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, CalicoNodeConfigurationError): raise
            raise CalicoNodeConfigurationError('invalid Calico configuration proof') from error


def validate_calico_node_configuration(*, revision):
    """Validate full admitted metadata/spec; retain status without certifying it."""
    try:
        return CalicoNodeConfigurationProof(revision, _compute(revision))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, CalicoNodeConfigurationError): raise
        raise CalicoNodeConfigurationError('invalid Calico configuration source') from error
