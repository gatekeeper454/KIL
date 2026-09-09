"""Bounded kube-proxy admitted Pod configuration for the no-inherited-proxy profile.

Independent kubeadm source supplies the template. Kubernetes v1.36.1 DaemonSet
CreatePodTemplate, priority and serviceaccount admission supply the additions.
The host-network containerd NODE namespace path skips CNI setup, so this pinned
path has no Pod annotations. This describes expected configuration, not proof
of effective admission settings or inability of external actors to add fields.

The revision label remains opaque. Runtime images, mounted ConfigMap bytes,
token issuance, effective privileges, readiness and full application completion
are not established. Raw status is retained through the revision, uninterpreted.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import re

from kil.v3b2_api_defaults import _equal, _managed_fields, matches_configuration
from kil.v3b2_driver_pod_configuration import _uid, _rv, _timestamp
from kil.v3b2_kube_proxy_parent_configuration import kube_proxy_parent_objects
from kil.v3b2_kube_proxy_revision import KubeProxyRevisionProof

_NAME = 'kube-proxy'
_NAMESPACE = 'kube-system'
_TOKEN = r'kube-api-access-[bcdfghjklmnpqrstvwxz2456789]{5}'
_METADATA = {'name', 'namespace', 'uid', 'resourceVersion', 'generation',
             'creationTimestamp', 'generateName', 'labels', 'ownerReferences'}


class KubeProxyPodConfigurationError(ValueError):
    """Evidence differs from independent bounded admitted configuration."""


@dataclass(frozen=True, slots=True)
class KubeProxyPodConfigurationBinding:
    namespace: str
    pod_name: str
    pod_uid: str
    pod_resource_version: str
    token_volume_name: str

    def __post_init__(self):
        try:
            if (type(self.namespace) is not str or self.namespace != _NAMESPACE
                    or type(self.pod_name) is not str
                    or re.fullmatch(r'kube-proxy-[a-z0-9]{5}', self.pod_name) is None
                    or type(self.token_volume_name) is not str
                    or re.fullmatch(_TOKEN, self.token_volume_name) is None):
                raise KubeProxyPodConfigurationError('invalid Pod configuration binding')
            _uid(self.pod_uid); _rv(self.pod_resource_version)
        except (ValueError, TypeError) as error:
            if isinstance(error, KubeProxyPodConfigurationError): raise
            raise KubeProxyPodConfigurationError('invalid Pod configuration identity') from error


def _compute(revision):
    if type(revision) is not KubeProxyRevisionProof:
        raise KubeProxyPodConfigurationError('revision dependency must be exact')
    # Reconstruct all bounded retained evidence before decoding candidate rows.
    revision.__post_init__()
    relation = revision.bindings[0]
    rows = json.loads(revision.parent.ownership.runtime_objects)['items']
    pods = [r for r in rows if r['kind'] == 'Pod'
        and r['metadata'].get('namespace') == _NAMESPACE and r['metadata']['name'] == relation.pod_name]
    if len(pods) != 1:
        raise KubeProxyPodConfigurationError('expected sole owned Pod')
    pod = pods[0]
    if (not {'apiVersion', 'kind', 'metadata', 'spec'} <= pod.keys()
            or pod.keys() - {'apiVersion', 'kind', 'metadata', 'spec', 'status'}
            or pod['apiVersion'] != 'v1' or pod['kind'] != 'Pod'):
        raise KubeProxyPodConfigurationError('unreviewed Pod root')
    metadata = pod['metadata']
    if not _METADATA <= metadata.keys() or metadata.keys() - (_METADATA | {'managedFields'}):
        raise KubeProxyPodConfigurationError('unreviewed complete Pod metadata')
    _uid(metadata['uid']); _rv(metadata['resourceVersion']); _timestamp(metadata['creationTimestamp'])
    if 'managedFields' in metadata: _managed_fields(metadata['managedFields'])
    if (type(metadata['generation']) is not int or metadata['generation'] != 1
            or not _equal([metadata['name'], metadata['namespace'], metadata['uid'], metadata['resourceVersion']],
                [relation.pod_name, _NAMESPACE, relation.pod_uid, relation.pod_resource_version])
            or metadata['generateName'] != _NAME + '-'):
        raise KubeProxyPodConfigurationError('Pod incarnation metadata differs')
    # Fresh verifier-owned source, never candidate DaemonSet or revision data.
    template = kube_proxy_parent_objects()[0]['spec']['template']
    desired_meta = deepcopy(template['metadata'])
    desired_meta.update(name=relation.pod_name, namespace=_NAMESPACE, generateName=_NAME + '-',
        ownerReferences=[{'apiVersion': 'apps/v1', 'kind': 'DaemonSet', 'name': _NAME,
            'uid': relation.daemon_set_uid, 'controller': True, 'blockOwnerDeletion': True}])
    desired_meta['labels']['controller-revision-hash'] = relation.revision_label
    if not _equal(metadata['labels'], desired_meta['labels']) or not _equal(metadata['ownerReferences'], desired_meta['ownerReferences']):
        raise KubeProxyPodConfigurationError('Pod labels or sole owner differ')
    candidate_spec = pod['spec']
    if type(candidate_spec) is not dict:
        raise KubeProxyPodConfigurationError('Pod spec must be exact dict')
    volumes = candidate_spec.get('volumes')
    if type(volumes) is not list or len(volumes) != 4 or type(volumes[-1]) is not dict:
        raise KubeProxyPodConfigurationError('expected three source volumes and token volume')
    token = volumes[-1].get('name')
    if type(token) is not str or re.fullmatch(_TOKEN, token) is None:
        raise KubeProxyPodConfigurationError('invalid token volume suffix')
    # Only the grammar-checked random token-volume name is candidate-derived.
    spec = deepcopy(template['spec'])
    node = revision.parent.ownership.node_ownership.node_name
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
    spec['containers'][0]['volumeMounts'].append({'name': token, 'readOnly': True,
        'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount'})
    desired = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': desired_meta, 'spec': spec}
    if not matches_configuration(desired, pod):
        raise KubeProxyPodConfigurationError('Pod differs from independent admitted configuration')
    return (KubeProxyPodConfigurationBinding(_NAMESPACE, relation.pod_name, relation.pod_uid,
        relation.pod_resource_version, token),)


@dataclass(frozen=True, slots=True)
class KubeProxyPodConfigurationProof:
    revision: KubeProxyRevisionProof
    bindings: tuple[KubeProxyPodConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise KubeProxyPodConfigurationError('configuration cannot establish completion')
            if type(self.bindings) is not tuple or len(self.bindings) != 1 or type(self.bindings[0]) is not KubeProxyPodConfigurationBinding:
                raise KubeProxyPodConfigurationError('expected one exact configuration binding')
            self.bindings[0].__post_init__()
            if self.bindings != _compute(self.revision):
                raise KubeProxyPodConfigurationError('binding differs from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, KubeProxyPodConfigurationError): raise
            raise KubeProxyPodConfigurationError('invalid kube-proxy Pod configuration proof') from error


def validate_kube_proxy_pod_configuration(*, revision):
    """Validate complete admitted metadata/spec; retain uninterpreted status."""
    try:
        return KubeProxyPodConfigurationProof(revision, _compute(revision))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, KubeProxyPodConfigurationError): raise
        raise KubeProxyPodConfigurationError('invalid kube-proxy Pod configuration source') from error
