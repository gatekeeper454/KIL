"""Two CoreDNS Pods: expected default-profile configuration, never runtime.

Independent kubeadm template authority is in coredns_parent_objects. Kubernetes
v1.36.1 pkg/controller/controller_utils.go, plugin/pkg/admission/serviceaccount/
admission.go, pkg/serviceaccount/claims.go and priority/defaulttolerationseconds
admission supply the reviewed generated metadata, 3607-second projected token,
priority and tolerations. Safe suffix alphabet: apimachinery/pkg/util/rand/rand.go.
The memory-pressure Pod toleration is added by optional PodTolerationRestriction;
nodetaint.Admit handles Nodes only. Kubernetes v1.36.1 defaultOnPlugins does not
enable PodTolerationRestriction, and this Kind profile has no admission override.
This proves expected configuration, not effective admission/PriorityClass state,
token issuance, actual image identity, mounted bytes, status IPs, endpoints or
readiness. CNI uniqueness is only between these two Pods and the owned Node's
sandbox identity. Raw status is retained uninterpreted in the exact parent.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import re

from kil.v3b2_api_defaults import _equal, matches_configuration
from kil.v3b2_coredns_parent_configuration import CoreDNSParentConfigurationProof, coredns_parent_objects
from kil.v3b2_driver_pod_configuration import _uid, _rv, _timestamp, _TOLERATIONS, _cni_annotations

_METADATA = {'name', 'namespace', 'generateName', 'labels', 'ownerReferences', 'uid',
             'resourceVersion', 'generation', 'creationTimestamp'}
_TOKEN_NAME = r'kube-api-access-[bcdfghjklmnpqrstvwxz2456789]{5}'


class CoreDNSPodConfigurationError(ValueError):
    """Evidence differs from the reviewed two-Pod configuration."""


@dataclass(frozen=True, slots=True)
class CoreDNSPodConfigurationBinding:
    namespace: str
    name: str
    uid: str
    resource_version: str
    token_volume_name: str

    def __post_init__(self):
        try:
            if (type(self.namespace) is not str or self.namespace != 'kube-system'
                    or type(self.name) is not str or re.fullmatch(r'coredns-[a-z0-9-]{1,245}', self.name) is None
                    or type(self.token_volume_name) is not str or re.fullmatch(_TOKEN_NAME, self.token_volume_name) is None):
                raise CoreDNSPodConfigurationError('invalid CoreDNS Pod binding')
            _uid(self.uid); _rv(self.resource_version)
        except (ValueError, TypeError) as error:
            if isinstance(error, CoreDNSPodConfigurationError): raise
            raise CoreDNSPodConfigurationError('invalid CoreDNS Pod API identity') from error


def _compute(parent):
    if type(parent) is not CoreDNSParentConfigurationProof:
        raise CoreDNSPodConfigurationError('parent dependency must be exact')
    parent.__post_init__()
    ownership = parent.ownership
    selected = [b for b in ownership.deployment_ownership.bindings
                if (b.namespace, b.deployment_name) == ('kube-system', 'coredns')]
    if len(selected) != 1 or len(selected[0].pods) != 2:
        raise CoreDNSPodConfigurationError('expected sole CoreDNS two-Pod chain')
    binding = selected[0]
    rows = json.loads(ownership.runtime_objects)['items']
    # Fresh factory, never the observed Deployment or ReplicaSet template.
    template = coredns_parent_objects()[0]['spec']['template']
    bindings, ips, sandboxes = [], set(), {ownership.owned_identity.node_container_id}
    for name, uid, rv in binding.pods:
        candidates = [r for r in rows if r['kind'] == 'Pod' and r['metadata'].get('namespace') == 'kube-system'
                      and r['metadata']['name'] == name]
        if len(candidates) != 1:
            raise CoreDNSPodConfigurationError('missing or duplicate CoreDNS Pod')
        pod = candidates[0]
        if set(pod) not in ({'apiVersion', 'kind', 'metadata', 'spec'},
                            {'apiVersion', 'kind', 'metadata', 'spec', 'status'}):
            raise CoreDNSPodConfigurationError('unreviewed Pod root')
        metadata, spec = pod['metadata'], pod['spec']
        if not _METADATA <= metadata.keys() or metadata.keys() - (_METADATA | {'annotations', 'managedFields'}):
            raise CoreDNSPodConfigurationError('incomplete or unreviewed Pod metadata')
        _uid(metadata['uid']); _rv(metadata['resourceVersion']); _timestamp(metadata['creationTimestamp'])
        if (metadata['name'] != name or metadata['namespace'] != 'kube-system' or metadata['uid'] != uid
                or metadata['resourceVersion'] != rv or metadata['generateName'] != binding.replica_set_name + '-'
                or type(metadata['generation']) is not int or metadata['generation'] != 1):
            raise CoreDNSPodConfigurationError('Pod incarnation differs from ownership')
        owner = {'apiVersion': 'apps/v1', 'kind': 'ReplicaSet', 'name': binding.replica_set_name,
                 'uid': binding.replica_set_uid, 'controller': True, 'blockOwnerDeletion': True}
        if not _equal(metadata['ownerReferences'], [owner]):
            raise CoreDNSPodConfigurationError('Pod owner is not exact')
        if type(spec) is not dict or type(spec.get('priority')) is not int or spec['priority'] != 2000000000:
            raise CoreDNSPodConfigurationError('Pod priority is not exact')
        annotations = metadata.get('annotations', {})
        if type(annotations) is not dict:
            raise CoreDNSPodConfigurationError('annotations must be exact dict')
        cni, ip, sandbox = _cni_annotations(annotations, spec, ownership.profile)
        # Do not let the shared normalizer remove last-applied or unknown keys.
        if not _equal(annotations, cni):
            raise CoreDNSPodConfigurationError('only reviewed CNI ADD annotations are admitted')
        if ip is not None:
            if ip in ips: raise CoreDNSPodConfigurationError('CoreDNS CNI IP collision')
            ips.add(ip)
        if sandbox is not None:
            if sandbox in sandboxes: raise CoreDNSPodConfigurationError('CoreDNS CNI sandbox collision')
            sandboxes.add(sandbox)
        volumes = spec.get('volumes')
        if type(volumes) is not list or len(volumes) != 2 or type(volumes[1]) is not dict:
            raise CoreDNSPodConfigurationError('expected config and token volumes')
        token = volumes[1].get('name')
        if type(token) is not str or re.fullmatch(_TOKEN_NAME, token) is None:
            raise CoreDNSPodConfigurationError('invalid projected token name')
        desired = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {
            'name': name, 'namespace': 'kube-system', 'generateName': binding.replica_set_name + '-',
            'labels': {'k8s-app': 'kube-dns', 'pod-template-hash': binding.pod_template_hash},
            'ownerReferences': [owner]}, 'spec': deepcopy(template['spec'])}
        # An explicitly empty map is equivalent locally; no shared helper change.
        if 'annotations' in metadata: desired['metadata']['annotations'] = cni
        admitted = desired['spec']
        admitted.update(priority=2000000000, preemptionPolicy='PreemptLowerPriority',
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
                raise CoreDNSPodConfigurationError('Pod scheduling differs from owned Node')
            admitted['nodeName'] = node
        if not matches_configuration(desired, pod):
            raise CoreDNSPodConfigurationError('Pod differs from independent admitted configuration')
        bindings.append(CoreDNSPodConfigurationBinding('kube-system', name, uid, rv, token))
    return tuple(sorted(bindings, key=lambda b: b.name))


@dataclass(frozen=True, slots=True)
class CoreDNSPodConfigurationProof:
    parent: CoreDNSParentConfigurationProof
    bindings: tuple[CoreDNSPodConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in
                   (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise CoreDNSPodConfigurationError('Pod configuration cannot establish completion')
            if type(self.bindings) is not tuple or len(self.bindings) != 2:
                raise CoreDNSPodConfigurationError('expected exact pair of Pod bindings')
            for binding in self.bindings:
                if type(binding) is not CoreDNSPodConfigurationBinding:
                    raise CoreDNSPodConfigurationError('Pod binding type must be exact')
                binding.__post_init__()
            if self.bindings != _compute(self.parent):
                raise CoreDNSPodConfigurationError('Pod bindings differ from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, CoreDNSPodConfigurationError): raise
            raise CoreDNSPodConfigurationError('invalid CoreDNS Pod proof') from error


def validate_coredns_pod_configuration(*, parent):
    """Validate both full Pods and retain the exact parent source proof."""
    try:
        return CoreDNSPodConfigurationProof(parent, _compute(parent))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, CoreDNSPodConfigurationError): raise
        raise CoreDNSPodConfigurationError('invalid CoreDNS Pod configuration source') from error
