"""Pinned kubeadm kube-proxy parent output for the no-inherited-proxy profile.

Authority is Kubernetes v1.36.1 cmd/kubeadm/app/phases/addons/proxy/manifests.go
and proxy.go, cmd/kubeadm/app/constants/constants.go (ConfigMap/key), and
cmd/kubeadm/app/images/images.go (configured Kubernetes image repository and
version). The expected profile pins registry.k8s.io/kube-proxy:v1.36.1.
pkg/apis/apps/v1/defaults.go supplies the explicit rollingUpdate scalar values.
All paths are under https://github.com/kubernetes/kubernetes/blob/v1.36.1/ .

proxy.go appends inherited proxy environment variables from the kubeadm process;
this expected output is restricted to the no-inherited-proxy profile, not every
kubeadm invocation. It does not independently certify node environments, image
overrides or patches. The exact ownership dependency joins the DaemonSet, sole
Pod and owned Node. Full Pod configuration, ControllerRevision, ConfigMap
contents, actual images, readiness and runtime completion remain outside this
proof. Raw status is retained; only the ownership dependency interprets its
required desiredNumberScheduled count.
"""
from dataclasses import dataclass
import json

from kil.v3b2_api_defaults import matches_configuration
from kil.v3b2_driver_pod_configuration import _uid, _rv, _timestamp
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof


class KubeProxyParentConfigurationError(ValueError):
    """Evidence differs from bounded independent kube-proxy parent output."""


def kube_proxy_parent_objects():
    """Fresh verifier-owned literals; candidate configuration is not authority."""
    return [
        {'apiVersion': 'apps/v1', 'kind': 'DaemonSet',
         'metadata': {'name': 'kube-proxy', 'namespace': 'kube-system', 'labels': {'k8s-app': 'kube-proxy'}},
         'spec': {
            'selector': {'matchLabels': {'k8s-app': 'kube-proxy'}},
            'updateStrategy': {'type': 'RollingUpdate', 'rollingUpdate': {'maxUnavailable': 1, 'maxSurge': 0}},
            'template': {'metadata': {'labels': {'k8s-app': 'kube-proxy'}}, 'spec': {
                'priorityClassName': 'system-node-critical',
                'containers': [{'name': 'kube-proxy', 'image': 'registry.k8s.io/kube-proxy:v1.36.1',
                    'imagePullPolicy': 'IfNotPresent',
                    'command': ['/usr/local/bin/kube-proxy', '--config=/var/lib/kube-proxy/config.conf',
                        '--hostname-override=$(NODE_NAME)'],
                    'securityContext': {'privileged': True},
                    'volumeMounts': [{'mountPath': '/var/lib/kube-proxy', 'name': 'kube-proxy'},
                        {'mountPath': '/run/xtables.lock', 'name': 'xtables-lock', 'readOnly': False},
                        {'mountPath': '/lib/modules', 'name': 'lib-modules', 'readOnly': True}],
                    'env': [{'name': 'NODE_NAME', 'valueFrom': {'fieldRef': {'fieldPath': 'spec.nodeName'}}}]}],
                'hostNetwork': True, 'serviceAccountName': 'kube-proxy',
                'volumes': [{'name': 'kube-proxy', 'configMap': {'name': 'kube-proxy'}},
                    {'name': 'xtables-lock', 'hostPath': {'path': '/run/xtables.lock', 'type': 'FileOrCreate'}},
                    {'name': 'lib-modules', 'hostPath': {'path': '/lib/modules'}}],
                'tolerations': [{'operator': 'Exists'}], 'nodeSelector': {'kubernetes.io/os': 'linux'}}}}},
        {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {'name': 'kube-proxy', 'namespace': 'kube-system'}},
    ]


@dataclass(frozen=True, slots=True)
class KubeProxyParentConfigurationBinding:
    namespace: str
    daemon_set_name: str
    daemon_set_uid: str
    daemon_set_resource_version: str
    service_account_uid: str
    service_account_resource_version: str

    def __post_init__(self):
        try:
            if (type(self.namespace) is not str or self.namespace != 'kube-system'
                    or type(self.daemon_set_name) is not str or self.daemon_set_name != 'kube-proxy'):
                raise KubeProxyParentConfigurationError('invalid kube-proxy parent identity')
            _uid(self.daemon_set_uid); _rv(self.daemon_set_resource_version)
            _uid(self.service_account_uid); _rv(self.service_account_resource_version)
            if self.daemon_set_uid == self.service_account_uid:
                raise KubeProxyParentConfigurationError('parent incarnations collide')
        except (ValueError, TypeError) as error:
            if isinstance(error, KubeProxyParentConfigurationError): raise
            raise KubeProxyParentConfigurationError('invalid kube-proxy parent binding') from error


def _compute(ownership):
    if type(ownership) is not RuntimeOwnershipProof:
        raise KubeProxyParentConfigurationError('ownership dependency must be exact')
    # Bound and reconstruct all retained dependency evidence before decoding it.
    ownership.__post_init__()
    rows = json.loads(ownership.runtime_objects)['items']
    selected = []
    for expected in kube_proxy_parent_objects():
        candidates = [r for r in rows if r['kind'] == expected['kind']
            and r['metadata'].get('namespace') == 'kube-system' and r['metadata']['name'] == 'kube-proxy']
        if len(candidates) != 1:
            raise KubeProxyParentConfigurationError('missing or duplicate kube-proxy parent')
        candidate = candidates[0]
        required = {'apiVersion', 'kind', 'metadata'}
        if expected['kind'] == 'DaemonSet': required.add('spec')
        if not required <= candidate.keys() or candidate.keys() - (required | {'status'}):
            raise KubeProxyParentConfigurationError('unreviewed kube-proxy parent root')
        metadata = candidate['metadata']
        required_meta = {'name', 'namespace', 'uid', 'resourceVersion', 'creationTimestamp'}
        if expected['kind'] == 'DaemonSet': required_meta |= {'generation', 'labels'}
        if not required_meta <= metadata.keys():
            raise KubeProxyParentConfigurationError('incomplete kube-proxy parent metadata')
        _timestamp(metadata['creationTimestamp'])
        if expected['kind'] == 'DaemonSet' and (type(metadata['generation']) is not int or metadata['generation'] != 1):
            raise KubeProxyParentConfigurationError('kube-proxy DaemonSet generation must be one')
        # Shared metadata validation admits reviewed runtime annotations and
        # managedFields; owners, finalizers, extra labels and fields differ.
        if not matches_configuration(expected, candidate):
            raise KubeProxyParentConfigurationError('parent differs from independent pinned configuration')
        selected.append(metadata)
    daemon, account = selected
    # The exact retained dependency already joins this source incarnation to
    # its sole Pod and owned Node; do not create a second chain projection.
    return (KubeProxyParentConfigurationBinding('kube-system', 'kube-proxy', daemon['uid'],
        daemon['resourceVersion'], account['uid'], account['resourceVersion']),)


@dataclass(frozen=True, slots=True)
class KubeProxyParentConfigurationProof:
    ownership: RuntimeOwnershipProof
    bindings: tuple[KubeProxyParentConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in
                   (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise KubeProxyParentConfigurationError('parent configuration cannot establish completion')
            if (type(self.bindings) is not tuple or len(self.bindings) != 1
                    or type(self.bindings[0]) is not KubeProxyParentConfigurationBinding):
                raise KubeProxyParentConfigurationError('expected one exact parent configuration binding')
            self.bindings[0].__post_init__()
            if self.bindings != _compute(self.ownership):
                raise KubeProxyParentConfigurationError('binding differs from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, KubeProxyParentConfigurationError): raise
            raise KubeProxyParentConfigurationError('invalid kube-proxy parent configuration proof') from error


def validate_kube_proxy_parent_configuration(*, ownership):
    """Check bounded parent output configuration and retain exact raw ownership."""
    try:
        return KubeProxyParentConfigurationProof(ownership, _compute(ownership))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, KubeProxyParentConfigurationError): raise
        raise KubeProxyParentConfigurationError('invalid kube-proxy parent configuration source') from error
