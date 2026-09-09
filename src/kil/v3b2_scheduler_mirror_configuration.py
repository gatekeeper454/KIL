"""Bounded scheduler mirror API-output configuration, Kubernetes v1.36.1.

Verifier-owned expectations describe the default non-rootless kubeadm profile
with no extra arguments, environment, volumes, proxies or patches. This does
not authenticate disk manifests, recompute the opaque kubelet hash, establish
effective override absence, or prove running images, privileges or readiness.
The config.seen producer timestamp is syntax-checked, with no freshness claim.
Raw status remains retained by ownership and is uninterpreted here.

Pinned source for command ordering, mounts, probes and static Pod construction:
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/controlplane/manifests.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/controlplane/volumes.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/util/staticpod/utils.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/util/arguments.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/constants/constants.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/features/features.go
Mirror identity, file defaults, seen timestamp and API/admission additions:
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/config/common.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/config/config.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/types/types.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/staging/src/k8s.io/cri-client/pkg/logs/logs.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/pod/mirror_client.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/apis/core/v1/defaults.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/plugin/pkg/admission/serviceaccount/admission.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/plugin/pkg/admission/defaulttolerationseconds/admission.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/plugin/pkg/admission/priority/admission.go
"""
from dataclasses import dataclass
from datetime import datetime
import json
import re

from kil.v3b2_api_defaults import _equal, _managed_fields, _timestamp, matches_configuration
from kil.v3b2_driver_pod_configuration import _uid, _rv
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof

_NODE = 'kil-v3-lab-control-plane'
_NAME = 'kube-scheduler-' + _NODE
_NAMESPACE = 'kube-system'
_METADATA = {'name', 'namespace', 'uid', 'resourceVersion', 'generation',
             'creationTimestamp', 'labels', 'annotations', 'ownerReferences'}


class SchedulerMirrorConfigurationError(ValueError):
    """Retained evidence differs from independent mirror API expectations."""


def _seen_timestamp(value):
    # kubelet types.Timestamp.GetString uses logs.RFC3339NanoFixed, including
    # nine fractional digits and a local numeric zone (UTC is serialized as Z).
    if type(value) is not str or re.fullmatch(
            r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{9}(?:Z|[+-][0-9]{2}:[0-9]{2})', value) is None:
        raise SchedulerMirrorConfigurationError('invalid kubelet config.seen timestamp')
    if value[-1] != 'Z' and (value[-6:] in {'+00:00', '-00:00'}
            or int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise SchedulerMirrorConfigurationError('invalid kubelet config.seen zone')
    datetime.fromisoformat(value.replace('Z', '+00:00'))


def scheduler_mirror_api_spec():
    """Fresh expected mirror spec, including reviewed API/admission additions."""
    return {
        'hostNetwork': True, 'nodeName': _NODE, 'priority': 2000001000,
        'priorityClassName': 'system-node-critical', 'preemptionPolicy': 'PreemptLowerPriority',
        'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}},
        'tolerations': [{'operator': 'Exists', 'effect': 'NoExecute'}],
        'containers': [{'name': 'kube-scheduler', 'image': 'registry.k8s.io/kube-scheduler:v1.36.1',
            'imagePullPolicy': 'IfNotPresent',
            'command': ['kube-scheduler', '--authentication-kubeconfig=/etc/kubernetes/scheduler.conf',
                '--authorization-kubeconfig=/etc/kubernetes/scheduler.conf', '--bind-address=127.0.0.1',
                '--kubeconfig=/etc/kubernetes/scheduler.conf', '--leader-elect=true'],
            'resources': {'requests': {'cpu': '100m'}},
            'volumeMounts': [{'name': 'kubeconfig', 'mountPath': '/etc/kubernetes/scheduler.conf', 'readOnly': True}],
            # HostNetwork SetDefaults_Pod explicitly sets hostPort; the shared
            # comparator does not synthesize it, so candidate omission fails.
            'ports': [{'name': 'probe-port', 'containerPort': 10259, 'hostPort': 10259, 'protocol': 'TCP'}],
            'livenessProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/livez', 'port': 'probe-port', 'scheme': 'HTTPS'},
                'initialDelaySeconds': 10, 'timeoutSeconds': 15, 'failureThreshold': 8, 'periodSeconds': 10},
            'readinessProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/readyz', 'port': 'probe-port', 'scheme': 'HTTPS'},
                'timeoutSeconds': 15, 'failureThreshold': 3, 'periodSeconds': 1},
            'startupProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/livez', 'port': 'probe-port', 'scheme': 'HTTPS'},
                'initialDelaySeconds': 10, 'timeoutSeconds': 15, 'failureThreshold': 24, 'periodSeconds': 10}}],
        'volumes': [{'name': 'kubeconfig', 'hostPath': {'path': '/etc/kubernetes/scheduler.conf', 'type': 'FileOrCreate'}}]}


@dataclass(frozen=True, slots=True)
class SchedulerMirrorConfigurationBinding:
    namespace: str
    pod_name: str
    pod_uid: str
    pod_resource_version: str
    config_hash: str

    def __post_init__(self):
        try:
            if (type(self.namespace) is not str or self.namespace != _NAMESPACE
                    or type(self.pod_name) is not str or self.pod_name != _NAME
                    or type(self.config_hash) is not str
                    or re.fullmatch(r'[0-9a-f]{32}', self.config_hash) is None):
                raise SchedulerMirrorConfigurationError('invalid scheduler binding')
            _uid(self.pod_uid); _rv(self.pod_resource_version)
        except (ValueError, TypeError) as error:
            if isinstance(error, SchedulerMirrorConfigurationError): raise
            raise SchedulerMirrorConfigurationError('invalid scheduler binding identity') from error


def _compute(ownership):
    if type(ownership) is not RuntimeOwnershipProof:
        raise SchedulerMirrorConfigurationError('ownership dependency must be exact')
    ownership.__post_init__()
    relations = [row for row in ownership.node_ownership.static_pods if row.component == 'kube-scheduler']
    if len(relations) != 1:
        raise SchedulerMirrorConfigurationError('expected sole scheduler ownership binding')
    relation = relations[0]
    rows = json.loads(ownership.runtime_objects)['items']
    pods = [row for row in rows if row['kind'] == 'Pod'
            and row['metadata'].get('namespace') == _NAMESPACE and row['metadata']['name'] == _NAME]
    if len(pods) != 1:
        raise SchedulerMirrorConfigurationError('expected sole owned scheduler Pod')
    pod = pods[0]
    if (not {'apiVersion', 'kind', 'metadata', 'spec'} <= pod.keys()
            or pod.keys() - {'apiVersion', 'kind', 'metadata', 'spec', 'status'}
            or pod['apiVersion'] != 'v1' or pod['kind'] != 'Pod'):
        raise SchedulerMirrorConfigurationError('unreviewed Pod root')
    metadata = pod['metadata']
    if not _METADATA <= metadata.keys() or metadata.keys() - (_METADATA | {'managedFields'}):
        raise SchedulerMirrorConfigurationError('unreviewed complete Pod metadata')
    _uid(metadata['uid']); _rv(metadata['resourceVersion']); _timestamp(metadata['creationTimestamp'])
    if 'managedFields' in metadata: _managed_fields(metadata['managedFields'])
    if (type(metadata['generation']) is not int or metadata['generation'] != 1
            or not _equal([metadata['namespace'], metadata['name'], metadata['uid'], metadata['resourceVersion']],
                [_NAMESPACE, relation.pod_name, relation.pod_uid, relation.pod_resource_version])):
        raise SchedulerMirrorConfigurationError('Pod incarnation metadata differs')
    annotations = metadata['annotations']
    if type(annotations) is not dict:
        raise SchedulerMirrorConfigurationError('invalid mirror annotations')
    seen = annotations['kubernetes.io/config.seen']
    _seen_timestamp(seen)
    desired_meta = {'name': _NAME, 'namespace': _NAMESPACE,
        'labels': {'component': 'kube-scheduler', 'tier': 'control-plane'},
        'ownerReferences': [{'apiVersion': 'v1', 'kind': 'Node', 'name': ownership.node_ownership.node_name,
            'uid': ownership.node_ownership.node_uid, 'controller': True}],
        'annotations': {'kubernetes.io/config.source': 'file', 'kubernetes.io/config.hash': relation.config_hash,
            'kubernetes.io/config.mirror': relation.mirror_hash, 'kubernetes.io/config.seen': seen}}
    # Check annotations before normalization, which otherwise strips last-applied.
    if not all(_equal(metadata[key], desired_meta[key]) for key in ('annotations', 'labels', 'ownerReferences')):
        raise SchedulerMirrorConfigurationError('mirror labels, annotations or owner differ')
    desired = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': desired_meta, 'spec': scheduler_mirror_api_spec()}
    if type(pod['spec']) is not dict or not matches_configuration(desired, pod):
        raise SchedulerMirrorConfigurationError('Pod differs from independent mirror API configuration')
    return (SchedulerMirrorConfigurationBinding(_NAMESPACE, relation.pod_name, relation.pod_uid,
        relation.pod_resource_version, relation.config_hash),)


@dataclass(frozen=True, slots=True)
class SchedulerMirrorConfigurationProof:
    ownership: RuntimeOwnershipProof
    bindings: tuple[SchedulerMirrorConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise SchedulerMirrorConfigurationError('configuration cannot establish completion')
            if type(self.bindings) is not tuple or len(self.bindings) != 1 or type(self.bindings[0]) is not SchedulerMirrorConfigurationBinding:
                raise SchedulerMirrorConfigurationError('expected one exact scheduler binding')
            self.bindings[0].__post_init__()
            if self.bindings != _compute(self.ownership):
                raise SchedulerMirrorConfigurationError('binding differs from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, SchedulerMirrorConfigurationError): raise
            raise SchedulerMirrorConfigurationError('invalid scheduler mirror configuration proof') from error


def validate_scheduler_mirror_configuration(*, ownership):
    """Compare full mirror metadata/spec; retain status without interpreting it."""
    try:
        return SchedulerMirrorConfigurationProof(ownership, _compute(ownership))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, SchedulerMirrorConfigurationError): raise
        raise SchedulerMirrorConfigurationError('invalid scheduler mirror configuration source') from error
