"""Bounded kube-proxy DaemonSet / ControllerRevision / owned Pod relationship.

Inherits the exact parent's pinned Kubernetes v1.36.1 no-inherited-proxy profile.
daemon/update.go getPatch serializes the typed template and adds $patch:replace;
snapshot copies source labels and annotations. With pinned Go 1.26, the zero
ObjectMeta creationTimestamp is omitted; ordinary Resources serializes as {}.
Only independent expected data receives reviewed template API defaults and
typed false-field omissions. Candidate RawExtension data is never normalized.

Opaque revision labels are related, not recomputed as ComputeHash. This does not
certify Go JSON bytes, freshness, Pod admission/full configuration, actual images,
status, or completion. Unrelated objects remain retained and uncertified. Pure
validator only; live collector integration remains outside this slice.
"""
from dataclasses import dataclass
import json
import re

from kil.v3b2_api_defaults import _equal, _managed_fields, configuration
from kil.v3b2_driver_pod_configuration import _uid, _rv, _timestamp
from kil.v3b2_kube_proxy_parent_configuration import (
    KubeProxyParentConfigurationProof, kube_proxy_parent_objects,
)

_NAME = 'kube-proxy'
_NAMESPACE = 'kube-system'
_HASH = 'controller-revision-hash'
_IDENTITY = {'name', 'namespace', 'uid', 'resourceVersion', 'creationTimestamp', 'labels'}


class KubeProxyRevisionError(ValueError):
    """Evidence differs from the bounded revision relationship contract."""


@dataclass(frozen=True, slots=True)
class KubeProxyRevisionBinding:
    namespace: str
    daemon_set_name: str
    daemon_set_uid: str
    daemon_set_resource_version: str
    revision_name: str
    revision_uid: str
    revision_resource_version: str
    pod_name: str
    pod_uid: str
    pod_resource_version: str
    revision_label: str

    def __post_init__(self):
        try:
            if (type(self.namespace) is not str or self.namespace != _NAMESPACE
                    or type(self.daemon_set_name) is not str or self.daemon_set_name != _NAME):
                raise KubeProxyRevisionError('unexpected DaemonSet binding')
            if (type(self.revision_label) is not str
                    or re.fullmatch(r'[a-z0-9]{1,10}', self.revision_label) is None
                    or type(self.revision_name) is not str
                    or self.revision_name != _NAME + '-' + self.revision_label):
                raise KubeProxyRevisionError('invalid opaque revision label relationship')
            if type(self.pod_name) is not str or re.fullmatch(r'kube-proxy-[a-z0-9]{5}', self.pod_name) is None:
                raise KubeProxyRevisionError('invalid bound Pod name')
            for uid in (self.daemon_set_uid, self.revision_uid, self.pod_uid): _uid(uid)
            for rv in (self.daemon_set_resource_version, self.revision_resource_version, self.pod_resource_version): _rv(rv)
            if len({self.daemon_set_uid, self.revision_uid, self.pod_uid}) != 3:
                raise KubeProxyRevisionError('binding incarnations collide')
        except (ValueError, TypeError) as error:
            if isinstance(error, KubeProxyRevisionError): raise
            raise KubeProxyRevisionError('invalid revision binding') from error


def _candidate(row, daemon_uid):
    if row['kind'] != 'ControllerRevision': return False
    metadata = row['metadata']
    labels = metadata.get('labels', {})
    owners = metadata.get('ownerReferences', [])
    return (metadata['name'].startswith(_NAME + '-')
        or (type(labels) is dict and labels.get('k8s-app') == _NAME)
        or (type(owners) is list and any(type(owner) is dict and
            (owner.get('uid') == daemon_uid or owner.get('name') == _NAME) for owner in owners)))


def _compute(parent):
    if type(parent) is not KubeProxyParentConfigurationProof:
        raise KubeProxyRevisionError('parent dependency must be exact')
    # Reconstruct parent configuration and its entire ownership chain before
    # decoding retained evidence; observed DaemonSet data is never authority.
    parent.__post_init__()
    ownership = parent.ownership
    selected = [b for b in ownership.node_ownership.daemon_pods
                if (b.namespace, b.daemon_set_name) == (_NAMESPACE, _NAME)]
    if len(selected) != 1: raise KubeProxyRevisionError('expected sole kube-proxy daemon binding')
    binding = selected[0]
    rows = json.loads(ownership.runtime_objects)['items']

    def one(kind, name):
        found = [r for r in rows if r['kind'] == kind and r['metadata'].get('namespace') == _NAMESPACE
                 and r['metadata']['name'] == name]
        if len(found) != 1: raise KubeProxyRevisionError('missing or duplicate relationship object')
        return found[0]

    daemon = one('DaemonSet', _NAME)
    candidates = [r for r in rows if _candidate(r, binding.daemon_set_uid)]
    if len(candidates) != 1: raise KubeProxyRevisionError('expected exactly one kube-proxy revision candidate')
    revision = candidates[0]
    if (set(revision) != {'apiVersion', 'kind', 'metadata', 'data', 'revision'}
            or revision['apiVersion'] != 'apps/v1' or revision['kind'] != 'ControllerRevision'
            or type(revision['revision']) is not int or revision['revision'] != 1):
        raise KubeProxyRevisionError('invalid revision type or fresh revision number')
    meta = revision['metadata']
    required = _IDENTITY | {'ownerReferences'}
    if not required <= meta.keys() or meta.keys() - (required | {'annotations', 'managedFields'}):
        raise KubeProxyRevisionError('unreviewed revision metadata')
    _uid(meta['uid']); _rv(meta['resourceVersion']); _timestamp(meta['creationTimestamp'])
    if 'managedFields' in meta: _managed_fields(meta['managedFields'])
    if meta['namespace'] != _NAMESPACE: raise KubeProxyRevisionError('revision namespace differs')
    owner = {'apiVersion': 'apps/v1', 'kind': 'DaemonSet', 'name': _NAME, 'uid': binding.daemon_set_uid,
             'controller': True, 'blockOwnerDeletion': True}
    if not _equal(meta['ownerReferences'], [owner]): raise KubeProxyRevisionError('revision owner differs')
    labels = meta['labels']
    if type(labels) is not dict: raise KubeProxyRevisionError('invalid revision labels')
    label = labels.get(_HASH)
    if not _equal(labels, {'k8s-app': _NAME, _HASH: label}):
        raise KubeProxyRevisionError('revision source labels differ')
    if not _equal(meta.get('annotations', {}), daemon['metadata'].get('annotations', {})):
        raise KubeProxyRevisionError('revision annotations differ from configuration-checked DaemonSet')
    pod = one('Pod', binding.pod_name)
    if type(pod['metadata'].get('labels')) is not dict or not _equal(pod['metadata']['labels'].get(_HASH), label):
        raise KubeProxyRevisionError('owned Pod revision label differs')
    template = configuration(kube_proxy_parent_objects()[0])['spec']['template']
    template['$patch'] = 'replace'
    if not _equal(revision['data'], {'spec': {'template': template}}):
        raise KubeProxyRevisionError('raw revision data differs from independent serialized template')
    return (KubeProxyRevisionBinding(_NAMESPACE, _NAME, binding.daemon_set_uid,
        binding.daemon_set_resource_version, meta['name'], meta['uid'], meta['resourceVersion'],
        binding.pod_name, binding.pod_uid, binding.pod_resource_version, label),)


@dataclass(frozen=True, slots=True)
class KubeProxyRevisionProof:
    parent: KubeProxyParentConfigurationProof
    bindings: tuple[KubeProxyRevisionBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise KubeProxyRevisionError('revision relationship cannot establish completion')
            if type(self.bindings) is not tuple or len(self.bindings) != 1 or type(self.bindings[0]) is not KubeProxyRevisionBinding:
                raise KubeProxyRevisionError('expected one exact revision binding')
            self.bindings[0].__post_init__()
            if self.bindings != _compute(self.parent):
                raise KubeProxyRevisionError('binding differs from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, KubeProxyRevisionError): raise
            raise KubeProxyRevisionError('invalid kube-proxy revision proof') from error


def validate_kube_proxy_revision(*, parent):
    """Bind one exact revision relation, retaining the exact accepted parent."""
    try:
        return KubeProxyRevisionProof(parent, _compute(parent))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, KubeProxyRevisionError): raise
        raise KubeProxyRevisionError('invalid kube-proxy revision source') from error
