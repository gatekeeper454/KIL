"""Calico-node DaemonSet / ControllerRevision / owned Pod label relationship.

The pinned Kubernetes v1.36.1 daemon/update.go getPatch serializes the typed
DaemonSet template and adds $patch:replace. snapshot copies DaemonSet annotations
and template labels. ControllerRevision PrepareForCreate does not set generation.
The zero template creationTimestamp is omitted by metav1's omitempty,omitzero
tag with Go 1.26; Resources remains an ordinary struct encoded as {}.

Only independent expected data receives reviewed API template defaults. Candidate
RawExtension data is compared structurally with exact scalar types and list order,
never normalized. This does not claim identical Go JSON byte encoding, ComputeHash,
full Pod configuration, admission, readiness, observation freshness or completion.
Unrelated revisions and statuses remain retained and uncertified. Pure validator;
the current collector does not yet request ControllerRevision objects.
"""
from dataclasses import dataclass
import json
import re

from kil.v3b2_api_defaults import _equal, _managed_fields, configuration, matches_configuration
from kil.v3b2_driver_pod_configuration import _uid, _rv, _timestamp
from kil.v3b2_proofs import calico_objects
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof

_NAME = 'calico-node'
_NAMESPACE = 'kube-system'
_HASH = 'controller-revision-hash'
_IDENTITY = {'name', 'namespace', 'uid', 'resourceVersion', 'creationTimestamp', 'labels'}


class CalicoNodeRevisionError(ValueError):
    """Evidence differs from the bounded revision relationship contract."""


@dataclass(frozen=True, slots=True)
class CalicoNodeRevisionBinding:
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
                raise CalicoNodeRevisionError('unexpected DaemonSet binding')
            if (type(self.revision_label) is not str
                    or re.fullmatch(r'[a-z0-9]{1,10}', self.revision_label) is None
                    or type(self.revision_name) is not str
                    or self.revision_name != _NAME + '-' + self.revision_label):
                raise CalicoNodeRevisionError('invalid opaque revision label relationship')
            if type(self.pod_name) is not str or re.fullmatch(r'calico-node-[a-z0-9]{5}', self.pod_name) is None:
                raise CalicoNodeRevisionError('invalid bound Pod name')
            for uid in (self.daemon_set_uid, self.revision_uid, self.pod_uid): _uid(uid)
            for rv in (self.daemon_set_resource_version, self.revision_resource_version, self.pod_resource_version): _rv(rv)
            if len({self.daemon_set_uid, self.revision_uid, self.pod_uid}) != 3:
                raise CalicoNodeRevisionError('binding incarnations collide')
        except (ValueError, TypeError) as error:
            if isinstance(error, CalicoNodeRevisionError): raise
            raise CalicoNodeRevisionError('invalid revision binding') from error


def _candidate(row, daemon_uid):
    if row['kind'] != 'ControllerRevision': return False
    metadata = row['metadata']
    labels = metadata.get('labels', {})
    owners = metadata.get('ownerReferences', [])
    related = (metadata['name'].startswith(_NAME + '-')
               or (type(labels) is dict and labels.get('k8s-app') == _NAME)
               or (type(owners) is list and any(type(owner) is dict and
                   (owner.get('uid') == daemon_uid or owner.get('name') == _NAME) for owner in owners)))
    return related


def _compute(ownership, source, projection):
    for raw in (source, projection):
        if type(raw) is not bytes or not 1 <= len(raw) <= 2 * 1024 * 1024:
            raise CalicoNodeRevisionError('authority must be bounded exact bytes')
    expected = calico_objects(source, projection)
    if type(ownership) is not RuntimeOwnershipProof:
        raise CalicoNodeRevisionError('ownership dependency must be exact')
    ownership.__post_init__()
    selected = [b for b in ownership.node_ownership.daemon_pods
                if (b.namespace, b.daemon_set_name) == (_NAMESPACE, _NAME)]
    if len(selected) != 1: raise CalicoNodeRevisionError('expected sole Calico daemon binding')
    binding = selected[0]
    rows = json.loads(ownership.runtime_objects)['items']

    def one(objects, kind, name):
        found = [r for r in objects if r['kind'] == kind and r['metadata'].get('namespace') == _NAMESPACE
                 and r['metadata']['name'] == name]
        if len(found) != 1: raise CalicoNodeRevisionError('missing or duplicate relationship object')
        return found[0]

    pinned = one(expected, 'DaemonSet', _NAME)
    daemon = one(rows, 'DaemonSet', _NAME)
    metadata = daemon['metadata']
    if (not (_IDENTITY | {'generation'}) <= metadata.keys()
            or metadata.keys() - (_IDENTITY | {'generation', 'annotations', 'managedFields'})
            or type(metadata['generation']) is not int or metadata['generation'] != 1
            or not matches_configuration(pinned, daemon)):
        raise CalicoNodeRevisionError('DaemonSet differs from pinned full configuration or fresh metadata')
    candidates = [r for r in rows if _candidate(r, binding.daemon_set_uid)]
    if len(candidates) != 1: raise CalicoNodeRevisionError('expected exactly one Calico revision candidate')
    revision = candidates[0]
    if (set(revision) != {'apiVersion', 'kind', 'metadata', 'data', 'revision'}
            or revision['apiVersion'] != 'apps/v1' or revision['kind'] != 'ControllerRevision'
            or type(revision['revision']) is not int or revision['revision'] != 1):
        raise CalicoNodeRevisionError('invalid revision type or fresh revision number')
    meta = revision['metadata']
    required = _IDENTITY | {'ownerReferences'}
    if not required <= meta.keys() or meta.keys() - (required | {'annotations', 'managedFields'}):
        raise CalicoNodeRevisionError('unreviewed revision metadata')
    _uid(meta['uid']); _rv(meta['resourceVersion']); _timestamp(meta['creationTimestamp'])
    if 'managedFields' in meta: _managed_fields(meta['managedFields'])
    if meta['namespace'] != _NAMESPACE: raise CalicoNodeRevisionError('revision namespace differs')
    owner = {'apiVersion': 'apps/v1', 'kind': 'DaemonSet', 'name': _NAME, 'uid': binding.daemon_set_uid,
             'controller': True, 'blockOwnerDeletion': True}
    if not _equal(meta['ownerReferences'], [owner]): raise CalicoNodeRevisionError('revision owner differs')
    labels = meta['labels']
    if type(labels) is not dict: raise CalicoNodeRevisionError('invalid revision labels')
    label = labels.get(_HASH)
    desired_labels = dict(pinned['spec']['template']['metadata']['labels'], **{_HASH: label})
    if not _equal(labels, desired_labels): raise CalicoNodeRevisionError('revision template labels differ')
    if not _equal(meta.get('annotations', {}), metadata.get('annotations', {})):
        raise CalicoNodeRevisionError('revision annotations differ from observed DaemonSet')
    pod = one(rows, 'Pod', binding.pod_name)
    if type(pod['metadata'].get('labels')) is not dict or not _equal(pod['metadata']['labels'].get(_HASH), label):
        raise CalicoNodeRevisionError('owned Pod revision label differs')
    template = configuration(pinned)['spec']['template']
    template['$patch'] = 'replace'
    if not _equal(revision['data'], {'spec': {'template': template}}):
        raise CalicoNodeRevisionError('raw revision data differs from independent serialized template')
    return (CalicoNodeRevisionBinding(_NAMESPACE, _NAME, binding.daemon_set_uid,
        binding.daemon_set_resource_version, meta['name'], meta['uid'], meta['resourceVersion'],
        binding.pod_name, binding.pod_uid, binding.pod_resource_version, label),)


@dataclass(frozen=True, slots=True)
class CalicoNodeRevisionProof:
    ownership: RuntimeOwnershipProof
    calico_source: bytes
    calico_projection: bytes
    bindings: tuple[CalicoNodeRevisionBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise CalicoNodeRevisionError('revision relationship cannot establish completion')
            if type(self.bindings) is not tuple or len(self.bindings) != 1 or type(self.bindings[0]) is not CalicoNodeRevisionBinding:
                raise CalicoNodeRevisionError('expected one exact revision binding')
            self.bindings[0].__post_init__()
            if self.bindings != _compute(self.ownership, self.calico_source, self.calico_projection):
                raise CalicoNodeRevisionError('binding differs from same-source reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, CalicoNodeRevisionError): raise
            raise CalicoNodeRevisionError('invalid Calico revision proof') from error


def validate_calico_node_revision(*, ownership, calico_source, calico_projection):
    """Bind one exact revision relation, without full Calico Pod certification."""
    try:
        bindings = _compute(ownership, calico_source, calico_projection)
        return CalicoNodeRevisionProof(ownership, calico_source, calico_projection, bindings)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, CalicoNodeRevisionError): raise
        raise CalicoNodeRevisionError('invalid Calico revision source') from error
