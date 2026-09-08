"""Allocation and incarnation proof for the fixed profile's nine KIL Services.

The allocator-derived fields are admitted only after independent rendering and
relational validation. Static API default comparison remains a separate step.
"""
from copy import deepcopy
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
import json

from kil.canonical import canonical_json
from kil.v3b2_api_defaults import _metadata, matches_configuration, object_key
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_manifests import WorkloadIdentity, _require_plain_json, render_objects


class ServiceBindingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ServiceAllocation:
    """Canonical immutable JSON arrays, sorted by namespace and name."""
    bindings: bytes
    configurations: bytes


def _canonical(value):
    return (canonical_json(value) + '\n').encode('utf-8')


def _address(value, network):
    if type(value) is not str:
        raise ServiceBindingError('Service address must be an exact IPv4 string')
    try:
        address = IPv4Address(value)
    except ValueError as error:
        raise ServiceBindingError('Service address is not canonical IPv4') from error
    # Kubernetes v1.36.1 kubeadm reserves offsets 1 (API) and 10 (DNS).
    if (str(address) != value or address not in network
            or address in {network.network_address, network.broadcast_address, network[1], network[10]}):
        raise ServiceBindingError('Service address is outside usable application allocation space')
    return value


def _bindings(rows, keys, network):
    if type(rows) is not list or len(rows) != 9:
        raise ServiceBindingError('Service bindings must contain exactly nine records')
    _require_plain_json(rows)
    identities, uids, addresses = [], set(), set()
    for row in rows:
        if type(row) is not dict or set(row) != {'namespace', 'name', 'uid', 'cluster_ip'}:
            raise ServiceBindingError('Service binding record is not closed')
        if any(type(row[key]) is not str or not row[key] for key in row):
            raise ServiceBindingError('Service binding fields must be nonempty exact strings')
        identity = ('v1', 'Service', row['namespace'], row['name'])
        _metadata({'uid': row['uid']}, ('v1', 'Service'))
        address = _address(row['cluster_ip'], network)
        if identity not in keys or identity in identities or row['uid'] in uids or address in addresses:
            raise ServiceBindingError('Service binding identities, UIDs and addresses must be distinct and expected')
        identities.append(identity)
        uids.add(row['uid'])
        addresses.add(address)
    if identities != sorted(keys):
        raise ServiceBindingError('Service bindings are not the full canonical identity sequence')
    return _canonical(rows)


def validate_service_allocations(observed, *, profile: V3B2Profile, workload: WorkloadIdentity,
                                 prior_bindings=None) -> ServiceAllocation:
    """Validate the full nine Services; None explicitly establishes initial bindings.

    Callers comparing a later observation must supply the prior complete array
    from verified proof history. resourceVersion is checked as API metadata but
    never retained as incarnation identity.
    """
    # render_objects revalidates exact dataclass types and all pinned values.
    desired = {object_key(row): row for row in json.loads(render_objects(profile, workload))['items']
               if row['kind'] == 'Service'}
    network = IPv4Network(profile.service_subnet)
    if type(observed) is not list or len(observed) != 9:
        raise ServiceBindingError('Service observations must contain exactly nine objects')
    _require_plain_json(observed)
    indexed = {}
    for row in observed:
        try:
            key = object_key(row)
        except (KeyError, TypeError, AttributeError) as error:
            raise ServiceBindingError('Service identity is malformed') from error
        if any(type(part) is not str or not part for part in key):
            raise ServiceBindingError('Service identity fields must be nonempty exact strings')
        if key not in desired or key in indexed:
            raise ServiceBindingError('Service observations are not the exact independently rendered set')
        indexed[key] = row
    bindings, configurations = [], []
    for key in sorted(desired):
        row = indexed[key]
        metadata, spec = row['metadata'], row.get('spec')
        if type(spec) is not dict or not {'uid', 'resourceVersion'} <= metadata.keys():
            raise ServiceBindingError('Service allocation or API incarnation metadata is missing')
        _metadata(deepcopy(metadata), ('v1', 'Service'))
        address = _address(spec.get('clusterIP'), network)
        if (type(spec.get('clusterIPs')) is not list or spec['clusterIPs'] != [address]
                or type(spec.get('ipFamilies')) is not list or spec['ipFamilies'] != ['IPv4']
                or type(spec.get('ipFamilyPolicy')) is not str or spec['ipFamilyPolicy'] != 'SingleStack'):
            raise ServiceBindingError('Service allocation is not the exact single-stack IPv4 contract')
        sanitized = deepcopy(row)
        for field in ('clusterIP', 'clusterIPs', 'ipFamilies', 'ipFamilyPolicy'):
            del sanitized['spec'][field]
        if not matches_configuration(desired[key], sanitized):
            raise ServiceBindingError('Service configuration differs from independently rendered inputs')
        configurations.append(sanitized)
        bindings.append({'namespace': key[2], 'name': key[3], 'uid': metadata['uid'], 'cluster_ip': address})
    encoded = _bindings(bindings, desired.keys(), network)
    if prior_bindings is not None and _bindings(prior_bindings, desired.keys(), network) != encoded:
        raise ServiceBindingError('Service UID or address differs from established allocation bindings')
    return ServiceAllocation(encoded, _canonical(configurations))
