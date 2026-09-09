"""Bounded etcd mirror API-output configuration, Kubernetes v1.36.1.

Verifier-owned expectations cover one reviewed Kind v0.32.0 IPv4 default-local-
etcd branch with no extra arguments, environment, volumes, patches, rootless
mode, or overrides. The retained Node InternalIP is the sole authority for the
IP repeated in kubeadm's mirror annotation and etcd command. A coordinated,
valid change therefore passes this relational slice: this does not authenticate
disk manifests, prove actual network ownership, establish effective kubeadm
inputs or patch absence, prove image realization/readiness, or complete either
the runtime or application contract. Pod status is retained uninterpreted, and
config.seen is syntax-checked without a freshness claim.

Pinned Kind sources for Node IP derivation and kubeadm input:
https://github.com/kubernetes-sigs/kind/blob/v0.32.0/pkg/cluster/internal/create/actions/config/config.go
https://github.com/kubernetes-sigs/kind/blob/v0.32.0/pkg/cluster/internal/kubeadm/config.go
Pinned Kubernetes sources for local etcd construction and defaults:
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/etcd/local.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/util/staticpod/utils.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/util/arguments.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/images/images.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/constants/constants.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/apis/kubeadm/v1beta4/defaults.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/nodestatus/setters.go
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
import ipaddress
import json
import re

from kil.v3b2_api_defaults import _equal, _managed_fields, _timestamp, matches_configuration
from kil.v3b2_driver_pod_configuration import _uid, _rv
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof

_NODE = 'kil-v3-lab-control-plane'
_NAME = 'etcd-' + _NODE
_NAMESPACE = 'kube-system'
_METADATA = {'name', 'namespace', 'uid', 'resourceVersion', 'generation',
             'creationTimestamp', 'labels', 'annotations', 'ownerReferences'}


class EtcdMirrorConfigurationError(ValueError):
    """Retained evidence differs from independent etcd mirror expectations."""


def _ipv4(value):
    if type(value) is not str:
        raise EtcdMirrorConfigurationError('Node InternalIP must be an exact IPv4 string')
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise EtcdMirrorConfigurationError('Node InternalIP is invalid') from error
    if (type(address) is not ipaddress.IPv4Address or str(address) != value
            or address.is_loopback or address.is_multicast or address.is_unspecified
            or address.is_link_local or address.is_reserved):
        raise EtcdMirrorConfigurationError('Node InternalIP is outside the reviewed IPv4 boundary')
    return value


def _seen_timestamp(value):
    if type(value) is not str or re.fullmatch(
            r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{9}(?:Z|[+-][0-9]{2}:[0-9]{2})', value) is None:
        raise EtcdMirrorConfigurationError('invalid kubelet config.seen timestamp')
    if value[-1] != 'Z' and (value[-6:] in {'+00:00', '-00:00'}
            or int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise EtcdMirrorConfigurationError('invalid kubelet config.seen zone')
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise EtcdMirrorConfigurationError('invalid kubelet config.seen calendar time') from error


def etcd_mirror_api_spec(node_internal_ip):
    """Return a fresh expected spec for the reviewed relational IPv4 branch."""
    ip = _ipv4(node_internal_ip)
    return {
        'hostNetwork': True, 'nodeName': _NODE, 'priority': 2000001000,
        'priorityClassName': 'system-node-critical', 'preemptionPolicy': 'PreemptLowerPriority',
        'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}},
        'tolerations': [{'operator': 'Exists', 'effect': 'NoExecute'}],
        'containers': [{'name': 'etcd', 'image': 'registry.k8s.io/etcd:3.6.8-0',
            'imagePullPolicy': 'IfNotPresent',
            'command': ['etcd', f'--advertise-client-urls=https://{ip}:2379',
                '--cert-file=/etc/kubernetes/pki/etcd/server.crt', '--client-cert-auth=true',
                '--data-dir=/var/lib/etcd', '--feature-gates=InitialCorruptCheck=true',
                f'--initial-advertise-peer-urls=https://{ip}:2380',
                f'--initial-cluster={_NODE}=https://{ip}:2380',
                '--key-file=/etc/kubernetes/pki/etcd/server.key',
                f'--listen-client-urls=https://127.0.0.1:2379,https://{ip}:2379',
                '--listen-metrics-urls=http://127.0.0.1:2381',
                f'--listen-peer-urls=https://{ip}:2380', f'--name={_NODE}',
                '--peer-cert-file=/etc/kubernetes/pki/etcd/peer.crt',
                '--peer-client-cert-auth=true', '--peer-key-file=/etc/kubernetes/pki/etcd/peer.key',
                '--peer-trusted-ca-file=/etc/kubernetes/pki/etcd/ca.crt', '--snapshot-count=10000',
                '--trusted-ca-file=/etc/kubernetes/pki/etcd/ca.crt', '--watch-progress-notify-interval=5s'],
            'resources': {'requests': {'cpu': '100m', 'memory': '100Mi'}},
            'ports': [{'name': 'probe-port', 'containerPort': 2381, 'hostPort': 2381, 'protocol': 'TCP'}],
            'volumeMounts': [
                {'name': 'etcd-data', 'mountPath': '/var/lib/etcd', 'readOnly': False},
                {'name': 'etcd-certs', 'mountPath': '/etc/kubernetes/pki/etcd', 'readOnly': False}],
            'livenessProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/livez', 'port': 'probe-port', 'scheme': 'HTTP'},
                'initialDelaySeconds': 10, 'timeoutSeconds': 15, 'failureThreshold': 8, 'periodSeconds': 10},
            'readinessProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/readyz', 'port': 'probe-port', 'scheme': 'HTTP'},
                'timeoutSeconds': 15, 'failureThreshold': 3, 'periodSeconds': 1},
            'startupProbe': {'httpGet': {'host': '127.0.0.1', 'path': '/readyz', 'port': 'probe-port', 'scheme': 'HTTP'},
                'initialDelaySeconds': 10, 'timeoutSeconds': 15, 'failureThreshold': 24, 'periodSeconds': 10}}],
        'volumes': [
            {'name': 'etcd-certs', 'hostPath': {'path': '/etc/kubernetes/pki/etcd', 'type': 'DirectoryOrCreate'}},
            {'name': 'etcd-data', 'hostPath': {'path': '/var/lib/etcd', 'type': 'DirectoryOrCreate'}}]}


@dataclass(frozen=True, slots=True)
class EtcdMirrorConfigurationBinding:
    namespace: str
    pod_name: str
    pod_uid: str
    pod_resource_version: str
    config_hash: str
    node_internal_ip: str

    def __post_init__(self):
        try:
            if (type(self.namespace) is not str or self.namespace != _NAMESPACE
                    or type(self.pod_name) is not str or self.pod_name != _NAME
                    or type(self.config_hash) is not str
                    or re.fullmatch(r'[0-9a-f]{32}', self.config_hash) is None):
                raise EtcdMirrorConfigurationError('invalid etcd binding')
            _uid(self.pod_uid); _rv(self.pod_resource_version); _ipv4(self.node_internal_ip)
        except (ValueError, TypeError) as error:
            if isinstance(error, EtcdMirrorConfigurationError): raise
            raise EtcdMirrorConfigurationError('invalid etcd binding identity') from error


def _node_ip(rows, ownership):
    matches = [row for row in rows if row.get('apiVersion') == 'v1' and row.get('kind') == 'Node'
        and type(row.get('metadata')) is dict
        and row['metadata'].get('name') == ownership.node_ownership.node_name
        and row['metadata'].get('uid') == ownership.node_ownership.node_uid
        and row['metadata'].get('resourceVersion') == ownership.node_ownership.node_resource_version]
    if len(matches) != 1:
        raise EtcdMirrorConfigurationError('expected sole same-source owned Node')
    status = matches[0].get('status')
    if type(status) is not dict:
        raise EtcdMirrorConfigurationError('owned Node status is absent or invalid')
    addresses = status.get('addresses')
    if (type(addresses) is not list or len(addresses) != 2
            or not _equal(addresses[0], {'type': 'InternalIP', 'address': addresses[0].get('address')}
                if type(addresses[0]) is dict else {})
            or not _equal(addresses[1], {'type': 'Hostname', 'address': _NODE})):
        raise EtcdMirrorConfigurationError('owned Node addresses differ from reviewed ordered shape')
    return _ipv4(addresses[0]['address'])


def _compute(ownership):
    if type(ownership) is not RuntimeOwnershipProof:
        raise EtcdMirrorConfigurationError('ownership dependency must be exact')
    ownership.__post_init__()
    relations = [item for item in ownership.node_ownership.static_pods if item.component == 'etcd']
    if len(relations) != 1:
        raise EtcdMirrorConfigurationError('expected sole etcd ownership binding')
    relation = relations[0]
    rows = json.loads(ownership.runtime_objects)['items']
    ip = _node_ip(rows, ownership)
    pods = [row for row in rows if row.get('apiVersion') == 'v1' and row.get('kind') == 'Pod'
            and type(row.get('metadata')) is dict and row['metadata'].get('namespace') == _NAMESPACE
            and row['metadata'].get('name') == _NAME]
    if len(pods) != 1:
        raise EtcdMirrorConfigurationError('expected sole owned etcd Pod')
    pod = pods[0]
    if (not {'apiVersion', 'kind', 'metadata', 'spec'} <= pod.keys()
            or pod.keys() - {'apiVersion', 'kind', 'metadata', 'spec', 'status'}):
        raise EtcdMirrorConfigurationError('unreviewed Pod root')
    metadata = pod['metadata']
    if type(metadata) is not dict or not _METADATA <= metadata.keys() or metadata.keys() - (_METADATA | {'managedFields'}):
        raise EtcdMirrorConfigurationError('unreviewed complete Pod metadata')
    _uid(metadata['uid']); _rv(metadata['resourceVersion']); _timestamp(metadata['creationTimestamp'])
    if 'managedFields' in metadata: _managed_fields(metadata['managedFields'])
    if (type(metadata['generation']) is not int or metadata['generation'] != 1
            or not _equal([metadata['namespace'], metadata['name'], metadata['uid'], metadata['resourceVersion']],
                [_NAMESPACE, relation.pod_name, relation.pod_uid, relation.pod_resource_version])):
        raise EtcdMirrorConfigurationError('Pod incarnation metadata differs')
    annotations = metadata['annotations']
    if type(annotations) is not dict or 'kubernetes.io/config.seen' not in annotations:
        raise EtcdMirrorConfigurationError('invalid mirror annotations')
    seen = annotations['kubernetes.io/config.seen']; _seen_timestamp(seen)
    desired_meta = {'name': _NAME, 'namespace': _NAMESPACE,
        'labels': {'component': 'etcd', 'tier': 'control-plane'},
        'ownerReferences': [{'apiVersion': 'v1', 'kind': 'Node',
            'name': ownership.node_ownership.node_name, 'uid': ownership.node_ownership.node_uid,
            'controller': True}],
        'annotations': {'kubernetes.io/config.source': 'file',
            'kubernetes.io/config.hash': relation.config_hash,
            'kubernetes.io/config.mirror': relation.mirror_hash,
            'kubernetes.io/config.seen': seen,
            'kubeadm.kubernetes.io/etcd.advertise-client-urls': f'https://{ip}:2379'}}
    if not all(_equal(metadata[key], desired_meta[key])
               for key in ('annotations', 'labels', 'ownerReferences')):
        raise EtcdMirrorConfigurationError('mirror labels, annotations or owner differ')
    desired = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': desired_meta,
               'spec': etcd_mirror_api_spec(ip)}
    if type(pod['spec']) is not dict or not matches_configuration(desired, pod):
        raise EtcdMirrorConfigurationError('Pod differs from independent etcd mirror API configuration')
    return (EtcdMirrorConfigurationBinding(_NAMESPACE, relation.pod_name, relation.pod_uid,
        relation.pod_resource_version, relation.config_hash, ip),)


@dataclass(frozen=True, slots=True)
class EtcdMirrorConfigurationProof:
    ownership: RuntimeOwnershipProof
    bindings: tuple[EtcdMirrorConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in
                   (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise EtcdMirrorConfigurationError('configuration cannot establish completion')
            if (type(self.bindings) is not tuple or len(self.bindings) != 1
                    or type(self.bindings[0]) is not EtcdMirrorConfigurationBinding):
                raise EtcdMirrorConfigurationError('expected one exact etcd binding')
            self.bindings[0].__post_init__()
            if self.bindings != _compute(self.ownership):
                raise EtcdMirrorConfigurationError('binding differs from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, EtcdMirrorConfigurationError): raise
            raise EtcdMirrorConfigurationError('invalid etcd mirror configuration proof') from error


def validate_etcd_mirror_configuration(*, ownership):
    """Compare etcd mirror metadata/spec; retain Pod status uninterpreted."""
    try:
        return EtcdMirrorConfigurationProof(ownership, _compute(ownership))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, EtcdMirrorConfigurationError): raise
        raise EtcdMirrorConfigurationError('invalid etcd mirror configuration source') from error
