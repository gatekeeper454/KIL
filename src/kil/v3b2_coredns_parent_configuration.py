"""Pinned kubeadm CoreDNS parent output configuration; no runtime completion.

Authority is Kubernetes v1.36.1 cmd/kubeadm/app/phases/addons/dns/manifests.go
and dns.go (two replicas), cmd/kubeadm/app/constants/constants.go (v1.14.2),
cmd/kubeadm/app/images/images.go (default registry/subpath), and
pkg/apis/apps/v1/defaults.go (Deployment maxSurge 25%). All paths are under
https://github.com/kubernetes/kubernetes/blob/v1.36.1/ .

This checks expected output configuration, not effective kubeadm image
overrides or patch files. The exact retained ownership proof supplies the sole
ReplicaSet/two-Pod chain; full Pod configuration, actual images, status,
readiness and application completion are not certified. Raw status is retained
uninterpreted. Omitted toleration operator remains omitted: it has no API setter.
"""
from dataclasses import dataclass
import json

from kil.v3b2_api_defaults import matches_configuration
from kil.v3b2_driver_pod_configuration import _uid, _rv, _timestamp
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof


class CoreDNSParentConfigurationError(ValueError):
    """Evidence differs from bounded independent CoreDNS parent configuration."""


def coredns_parent_objects():
    """Fresh verifier-owned literals; observed template never supplies authority."""
    return [
        {'apiVersion': 'apps/v1', 'kind': 'Deployment',
         'metadata': {'name': 'coredns', 'namespace': 'kube-system', 'labels': {'k8s-app': 'kube-dns'}},
         'spec': {
            'replicas': 2,
            'strategy': {'type': 'RollingUpdate', 'rollingUpdate': {'maxUnavailable': 1, 'maxSurge': '25%'}},
            'selector': {'matchLabels': {'k8s-app': 'kube-dns'}},
            'template': {'metadata': {'labels': {'k8s-app': 'kube-dns'}}, 'spec': {
                'priorityClassName': 'system-cluster-critical', 'serviceAccountName': 'coredns',
                'affinity': {'podAntiAffinity': {'preferredDuringSchedulingIgnoredDuringExecution': [{
                    'weight': 100, 'podAffinityTerm': {'labelSelector': {'matchExpressions': [{
                        'key': 'k8s-app', 'operator': 'In', 'values': ['kube-dns']}]},
                        'topologyKey': 'kubernetes.io/hostname'}}]}},
                'tolerations': [{'key': 'CriticalAddonsOnly', 'operator': 'Exists'},
                    {'key': 'node-role.kubernetes.io/control-plane', 'effect': 'NoSchedule'}],
                'nodeSelector': {'kubernetes.io/os': 'linux'}, 'dnsPolicy': 'Default',
                'containers': [{'name': 'coredns', 'image': 'registry.k8s.io/coredns/coredns:v1.14.2',
                    'imagePullPolicy': 'IfNotPresent',
                    'resources': {'limits': {'memory': '170Mi'}, 'requests': {'cpu': '100m', 'memory': '70Mi'}},
                    'args': ['-conf', '/etc/coredns/Corefile'],
                    'volumeMounts': [{'name': 'config-volume', 'mountPath': '/etc/coredns', 'readOnly': True}],
                    'ports': [{'containerPort': 53, 'name': 'dns', 'protocol': 'UDP'},
                        {'containerPort': 53, 'name': 'dns-tcp', 'protocol': 'TCP'},
                        {'containerPort': 9153, 'name': 'metrics', 'protocol': 'TCP'},
                        {'containerPort': 8080, 'name': 'liveness-probe', 'protocol': 'TCP'},
                        {'containerPort': 8181, 'name': 'readiness-probe', 'protocol': 'TCP'}],
                    'livenessProbe': {'httpGet': {'path': '/health', 'port': 'liveness-probe', 'scheme': 'HTTP'},
                        'initialDelaySeconds': 60, 'timeoutSeconds': 5, 'successThreshold': 1, 'failureThreshold': 5},
                    'readinessProbe': {'httpGet': {'path': '/ready', 'port': 'readiness-probe', 'scheme': 'HTTP'}},
                    'securityContext': {'allowPrivilegeEscalation': False,
                        'capabilities': {'add': ['NET_BIND_SERVICE'], 'drop': ['ALL']}, 'readOnlyRootFilesystem': True}}],
                'volumes': [{'name': 'config-volume', 'configMap': {'name': 'coredns',
                    'items': [{'key': 'Corefile', 'path': 'Corefile'}]}}]}}}},
        {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {'name': 'coredns', 'namespace': 'kube-system'}},
    ]


@dataclass(frozen=True, slots=True)
class CoreDNSParentConfigurationBinding:
    namespace: str
    deployment_name: str
    deployment_uid: str
    deployment_resource_version: str
    service_account_uid: str
    service_account_resource_version: str

    def __post_init__(self):
        try:
            if (type(self.namespace) is not str or self.namespace != 'kube-system'
                    or type(self.deployment_name) is not str or self.deployment_name != 'coredns'):
                raise CoreDNSParentConfigurationError('invalid CoreDNS parent identity')
            _uid(self.deployment_uid); _rv(self.deployment_resource_version)
            _uid(self.service_account_uid); _rv(self.service_account_resource_version)
            if self.deployment_uid == self.service_account_uid:
                raise CoreDNSParentConfigurationError('parent incarnations collide')
        except (ValueError, TypeError) as error:
            if isinstance(error, CoreDNSParentConfigurationError): raise
            raise CoreDNSParentConfigurationError('invalid CoreDNS parent binding') from error


def _compute(ownership):
    if type(ownership) is not RuntimeOwnershipProof:
        raise CoreDNSParentConfigurationError('ownership dependency must be exact')
    # Validate bounds and reconstruct the full source ownership before decoding.
    ownership.__post_init__()
    rows = json.loads(ownership.runtime_objects)['items']
    selected = []
    for expected in coredns_parent_objects():
        candidates = [r for r in rows if r['kind'] == expected['kind']
            and r['metadata'].get('namespace') == 'kube-system' and r['metadata']['name'] == 'coredns']
        if len(candidates) != 1:
            raise CoreDNSParentConfigurationError('missing or duplicate CoreDNS parent')
        candidate = candidates[0]
        required = {'apiVersion', 'kind', 'metadata'}
        if expected['kind'] == 'Deployment': required.add('spec')
        if not required <= candidate.keys() or candidate.keys() - (required | {'status'}):
            raise CoreDNSParentConfigurationError('unreviewed CoreDNS parent root')
        metadata = candidate['metadata']
        required_meta = {'name', 'namespace', 'uid', 'resourceVersion', 'creationTimestamp'}
        if expected['kind'] == 'Deployment': required_meta |= {'generation', 'labels'}
        if not required_meta <= metadata.keys():
            raise CoreDNSParentConfigurationError('incomplete CoreDNS parent metadata')
        _timestamp(metadata['creationTimestamp'])
        if expected['kind'] == 'Deployment' and (type(metadata['generation']) is not int or metadata['generation'] != 1):
            raise CoreDNSParentConfigurationError('CoreDNS Deployment generation must be one')
        # Shared metadata validation admits only reviewed runtime annotations and
        # managedFields; remaining owners, labels, finalizers and extras differ.
        if not matches_configuration(expected, candidate):
            raise CoreDNSParentConfigurationError('parent differs from independent pinned configuration')
        selected.append(metadata)
    deployment, account = selected
    # The retained exact dependency already joins this same source identity to
    # its sole ReplicaSet and two Pods. Do not duplicate that chain projection.
    return (CoreDNSParentConfigurationBinding('kube-system', 'coredns', deployment['uid'],
        deployment['resourceVersion'], account['uid'], account['resourceVersion']),)


@dataclass(frozen=True, slots=True)
class CoreDNSParentConfigurationProof:
    ownership: RuntimeOwnershipProof
    bindings: tuple[CoreDNSParentConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in
                   (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise CoreDNSParentConfigurationError('parent configuration cannot establish completion')
            if (type(self.bindings) is not tuple or len(self.bindings) != 1
                    or type(self.bindings[0]) is not CoreDNSParentConfigurationBinding):
                raise CoreDNSParentConfigurationError('expected one exact parent configuration binding')
            self.bindings[0].__post_init__()
            if self.bindings != _compute(self.ownership):
                raise CoreDNSParentConfigurationError('binding differs from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, CoreDNSParentConfigurationError): raise
            raise CoreDNSParentConfigurationError('invalid CoreDNS parent configuration proof') from error


def validate_coredns_parent_configuration(*, ownership):
    """Check full parent output configuration while retaining exact raw ownership."""
    try:
        return CoreDNSParentConfigurationProof(ownership, _compute(ownership))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, CoreDNSParentConfigurationError): raise
        raise CoreDNSParentConfigurationError('invalid CoreDNS parent configuration source') from error
