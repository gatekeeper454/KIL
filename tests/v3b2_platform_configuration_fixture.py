"""Compose independent observations for existing configuration contracts only."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json

from kil.v3b2_runtime_ownership import validate_runtime_ownership
from kil.v3b2_control_plane_manifest_source import validate_control_plane_manifest_source
from kil.v3b2_calico_node_revision import validate_calico_node_revision
from kil.v3b2_kube_proxy_parent_configuration import validate_kube_proxy_parent_configuration
from kil.v3b2_kube_proxy_revision import validate_kube_proxy_revision
from kil.v3b2_coredns_parent_configuration import validate_coredns_parent_configuration
from kil.v3b2_local_path_parent_configuration import validate_local_path_parent_configuration
from kil.v3b2_calico_node_configuration import validate_calico_node_configuration
from kil.v3b2_calico_controller_configuration import validate_calico_controller_configuration
from kil.v3b2_coredns_pod_configuration import validate_coredns_pod_configuration
from kil.v3b2_local_path_pod_configuration import validate_local_path_pod_configuration
from kil.v3b2_kube_proxy_pod_configuration import validate_kube_proxy_pod_configuration
from kil.v3b2_scheduler_mirror_configuration import validate_scheduler_mirror_configuration
from kil.v3b2_etcd_mirror_configuration import validate_etcd_mirror_configuration
from kil.v3b2_kube_apiserver_mirror_configuration import validate_kube_apiserver_mirror_configuration
from kil.v3b2_kube_controller_manager_mirror_configuration import validate_kube_controller_manager_mirror_configuration
from tests.test_v3b2_runtime_ownership import fixture as owner_fixture, encode
from tests.test_v3b2_calico_node_configuration import fixture as node_fixture
from tests.test_v3b2_calico_controller_configuration import fixture as controller_fixture
from tests.test_v3b2_coredns_pod_configuration import fixture as dns_fixture
from tests.test_v3b2_local_path_pod_configuration import fixture as storage_fixture
from tests.test_v3b2_kube_proxy_pod_configuration import fixture as proxy_fixture
from tests.test_v3b2_scheduler_mirror_configuration import fixture as scheduler_fixture
from tests.test_v3b2_etcd_mirror_configuration import fixture as etcd_fixture
from tests.test_v3b2_kube_apiserver_mirror_configuration import (
    api_document as apiserver_fixture, disk_pod as apiserver_disk,
    yaml_bytes as apiserver_yaml_bytes, MATCHED_OWNERSHIP_IDENTITY, MATCHED_WORKLOAD,
)
from tests.test_v3b2_kube_controller_manager_mirror_configuration import (
    api_document as manager_fixture, disk_pod as manager_disk,
    yaml_bytes as manager_yaml_bytes,
)
from tests.test_v3b2_control_plane_manifest_source import context, observations, node


ROOT = Path(__file__).resolve().parents[1]
NAMES = ('calico_node', 'calico_controller', 'coredns', 'local_path',
         'kube_proxy', 'scheduler', 'etcd', 'apiserver', 'controller_manager')


def key(row):
    metadata = row['metadata']
    return row['apiVersion'], row['kind'], metadata.get('namespace', ''), metadata['name']


def fixture():
    args = owner_fixture(owned_identity=MATCHED_OWNERSHIP_IDENTITY,
                         workload=MATCHED_WORKLOAD)
    document = json.loads(args['runtime_objects'])
    merged = {key(row): deepcopy(row) for row in document['items']}
    changes = {}
    for build in (node_fixture, controller_fixture, dns_fixture, storage_fixture,
                  proxy_fixture, scheduler_fixture, etcd_fixture,
                  apiserver_fixture, manager_fixture):
        local_args, observed = build()[:2]
        baseline = owner_fixture(profile=local_args['profile'],
            workload=local_args['workload'], owned_identity=local_args['owned_identity'])
        old = {key(row): row for row in json.loads(baseline['runtime_objects'])['items']}
        for row in observed['items']:
            identity = key(row)
            if identity in old and row == old[identity]:
                continue
            if identity in changes and changes[identity] != row:
                raise AssertionError('conflicting independent observations', identity)
            changes[identity] = deepcopy(row)
    merged.update(changes)
    document['items'] = list(merged.values())
    args['runtime_objects'] = encode(document)
    return args, document, source_for(args)


def source_for(args, *, sequence=5):
    owned = args['owned_identity']
    requested = args['profile'].kind_node_image
    run = args['workload'].run_id.removeprefix('v3b2-')
    retained = context(owned, kind_node_image=requested, run_id=run)
    retained = replace(retained, run_id=run, intent_sequence=sequence)
    bracket = node(node_id=owned.node_container_id, requested_image=requested)
    return validate_control_plane_manifest_source(context=retained,
        owned_identity=owned, observations=observations(owned,
            apiserver=apiserver_yaml_bytes(apiserver_disk()),
            controller=manager_yaml_bytes(manager_disk()), before=bracket, after=bracket))


def rebase_args(args, document, **changes):
    inputs = {name: args[name] for name in ('profile', 'workload', 'owned_identity')}
    inputs.update(changes)
    alternate = owner_fixture(**inputs)
    base = json.loads(alternate['runtime_objects'])
    rows = {key(row): row for row in base['items']}
    for row in document['items']:
        namespace = row['metadata'].get('namespace', '')
        if row['kind'] != 'Namespace' and not namespace.startswith('kil-'):
            rows[key(row)] = deepcopy(row)
    base['items'] = list(rows.values())
    alternate['runtime_objects'] = encode(base)
    return alternate


def dependencies(args, source, *, calico_source=None, calico_projection=None):
    ownership = validate_runtime_ownership(**args)
    raw = ((ROOT / 'deploy/kind/calico-v3.32.0.yaml').read_bytes()
           if calico_source is None else calico_source)
    projection = ((ROOT / 'deploy/kind/calico-v3.32.0.objects.json').read_bytes()
                  if calico_projection is None else calico_projection)
    revision = validate_calico_node_revision(ownership=ownership,
        calico_source=raw, calico_projection=projection)
    proxy_parent = validate_kube_proxy_parent_configuration(ownership=ownership)
    return dict(ownership=ownership,
        calico_node=validate_calico_node_configuration(revision=revision),
        calico_controller=validate_calico_controller_configuration(
            ownership=ownership, calico_source=raw, calico_projection=projection),
        coredns=validate_coredns_pod_configuration(
            parent=validate_coredns_parent_configuration(ownership=ownership)),
        local_path=validate_local_path_pod_configuration(
            parent=validate_local_path_parent_configuration(ownership=ownership)),
        kube_proxy=validate_kube_proxy_pod_configuration(
            revision=validate_kube_proxy_revision(parent=proxy_parent)),
        scheduler=validate_scheduler_mirror_configuration(ownership=ownership),
        etcd=validate_etcd_mirror_configuration(ownership=ownership),
        apiserver=validate_kube_apiserver_mirror_configuration(ownership=ownership, source=source),
        controller_manager=validate_kube_controller_manager_mirror_configuration(
            ownership=ownership, source=source))
