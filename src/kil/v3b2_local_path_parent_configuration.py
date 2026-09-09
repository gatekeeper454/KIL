"""Pinned Kind local-path parent output configuration; no runtime completion.

Source authority: Kind v0.32.0 pkg/build/nodeimage/const_storage.go lines 99-152:
https://github.com/kubernetes-sigs/kind/blob/v0.32.0/pkg/build/nodeimage/const_storage.go#L99-L152
Deployment strategy is explicit Kubernetes v1.36.1 apps/v1 API default output:
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/apis/apps/v1/defaults.go
Both maxUnavailable and maxSurge are the strings "25%".

This checks expected platform output, not effective overrides, mounted ConfigMap
contents, helper Pod behavior, actual images, status or readiness. Exact retained
ownership supplies the sole ReplicaSet/Pod relationship; full Pod configuration
and application completion are not certified. Raw status is retained uninterpreted.
"""
from dataclasses import dataclass
import json

from kil.v3b2_api_defaults import matches_configuration
from kil.v3b2_driver_pod_configuration import _uid, _rv, _timestamp
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof


class LocalPathParentConfigurationError(ValueError):
    """Evidence differs from bounded independent local-path parent configuration."""


def local_path_parent_objects():
    """Fresh source-owned literals; observed templates never supply authority."""
    return [
        {'apiVersion': 'apps/v1', 'kind': 'Deployment',
         'metadata': {'name': 'local-path-provisioner', 'namespace': 'local-path-storage'},
         'spec': {
            'replicas': 1,
            'strategy': {'type': 'RollingUpdate', 'rollingUpdate': {'maxUnavailable': '25%', 'maxSurge': '25%'}},
            'selector': {'matchLabels': {'app': 'local-path-provisioner'}},
            'template': {'metadata': {'labels': {'app': 'local-path-provisioner'}}, 'spec': {
                'nodeSelector': {'kubernetes.io/os': 'linux'},
                'tolerations': [
                    {'key': 'node-role.kubernetes.io/control-plane', 'operator': 'Equal', 'effect': 'NoSchedule'},
                    {'key': 'node-role.kubernetes.io/master', 'operator': 'Equal', 'effect': 'NoSchedule'}],
                'serviceAccountName': 'local-path-provisioner-service-account',
                'containers': [{'name': 'local-path-provisioner',
                    'image': 'docker.io/kindest/local-path-provisioner:v20260521-9fb22683',
                    'imagePullPolicy': 'IfNotPresent',
                    'command': ['local-path-provisioner', '--debug', 'start', '--helper-image',
                        'docker.io/kindest/local-path-helper:v20260131-7181c60a', '--config', '/etc/config/config.json'],
                    'volumeMounts': [{'name': 'config-volume', 'mountPath': '/etc/config/'}],
                    'env': [{'name': 'POD_NAMESPACE', 'valueFrom': {'fieldRef': {'fieldPath': 'metadata.namespace'}}},
                        {'name': 'CONFIG_MOUNT_PATH', 'value': '/etc/config/'}]}],
                'volumes': [{'name': 'config-volume', 'configMap': {'name': 'local-path-config'}}]}}}},
        {'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': {
            'name': 'local-path-provisioner-service-account', 'namespace': 'local-path-storage'}},
    ]


@dataclass(frozen=True, slots=True)
class LocalPathParentConfigurationBinding:
    namespace: str
    deployment_name: str
    deployment_uid: str
    deployment_resource_version: str
    service_account_uid: str
    service_account_resource_version: str

    def __post_init__(self):
        try:
            if (type(self.namespace) is not str or self.namespace != 'local-path-storage'
                    or type(self.deployment_name) is not str or self.deployment_name != 'local-path-provisioner'):
                raise LocalPathParentConfigurationError('invalid local-path parent identity')
            _uid(self.deployment_uid); _rv(self.deployment_resource_version)
            _uid(self.service_account_uid); _rv(self.service_account_resource_version)
            if self.deployment_uid == self.service_account_uid:
                raise LocalPathParentConfigurationError('parent incarnations collide')
        except (ValueError, TypeError) as error:
            if isinstance(error, LocalPathParentConfigurationError): raise
            raise LocalPathParentConfigurationError('invalid local-path parent binding') from error


def _compute(ownership):
    if type(ownership) is not RuntimeOwnershipProof:
        raise LocalPathParentConfigurationError('ownership dependency must be exact')
    # Reconstruct bounded source ownership before any raw decoding here.
    ownership.__post_init__()
    rows = json.loads(ownership.runtime_objects)['items']
    selected = []
    for expected in local_path_parent_objects():
        candidates = [r for r in rows if r['kind'] == expected['kind']
            and r['metadata'].get('namespace') == expected['metadata']['namespace']
            and r['metadata']['name'] == expected['metadata']['name']]
        if len(candidates) != 1:
            raise LocalPathParentConfigurationError('missing or duplicate local-path parent')
        candidate = candidates[0]
        required = {'apiVersion', 'kind', 'metadata'}
        if expected['kind'] == 'Deployment': required.add('spec')
        if not required <= candidate.keys() or candidate.keys() - (required | {'status'}):
            raise LocalPathParentConfigurationError('unreviewed local-path parent root')
        metadata = candidate['metadata']
        required_meta = {'name', 'namespace', 'uid', 'resourceVersion', 'creationTimestamp'}
        if expected['kind'] == 'Deployment': required_meta.add('generation')
        if not required_meta <= metadata.keys():
            raise LocalPathParentConfigurationError('incomplete local-path parent metadata')
        _timestamp(metadata['creationTimestamp'])
        if expected['kind'] == 'Deployment' and (type(metadata['generation']) is not int or metadata['generation'] != 1):
            raise LocalPathParentConfigurationError('local-path Deployment generation must be one')
        # Shared metadata/default rules retain unreviewed extras for rejection.
        if not matches_configuration(expected, candidate):
            raise LocalPathParentConfigurationError('parent differs from independent pinned configuration')
        selected.append(metadata)
    deployment, account = selected
    return (LocalPathParentConfigurationBinding('local-path-storage', 'local-path-provisioner',
        deployment['uid'], deployment['resourceVersion'], account['uid'], account['resourceVersion']),)


@dataclass(frozen=True, slots=True)
class LocalPathParentConfigurationProof:
    ownership: RuntimeOwnershipProof
    bindings: tuple[LocalPathParentConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in
                   (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise LocalPathParentConfigurationError('parent configuration cannot establish completion')
            if (type(self.bindings) is not tuple or len(self.bindings) != 1
                    or type(self.bindings[0]) is not LocalPathParentConfigurationBinding):
                raise LocalPathParentConfigurationError('expected one exact parent configuration binding')
            self.bindings[0].__post_init__()
            if self.bindings != _compute(self.ownership):
                raise LocalPathParentConfigurationError('binding differs from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, LocalPathParentConfigurationError): raise
            raise LocalPathParentConfigurationError('invalid local-path parent configuration proof') from error


def validate_local_path_parent_configuration(*, ownership):
    """Check parent output configuration while retaining exact raw ownership."""
    try:
        return LocalPathParentConfigurationProof(ownership, _compute(ownership))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, LocalPathParentConfigurationError): raise
        raise LocalPathParentConfigurationError('invalid local-path parent configuration source') from error
