"""Proof-backed KIL image rows with the legacy wire fields, not legacy DTOs.

Only the enclosing proof certifies these rows. Requested images are extracted
from independently rendered configuration; image_id is containerd's verified
ImageRef and need not equal the requested manifest digest. The actual runtime
Image remains in the retained KilPodRuntimeProof. No standalone row claims an
image chain, and this module does not certify platform images, full inventory,
full application completion, or the complete runtime contract.
"""
from dataclasses import dataclass
import json
import re

from kil.v3b2_kil_pod_runtime import KilPodRuntimeProof
from kil.v3b2_driver_pod_configuration import _uid, _rv


class KilImageProjectionError(ValueError):
    pass


@dataclass(frozen=True, slots=True, order=True)
class KilImageRow:
    image_role: str
    container_type: str
    namespace: str
    pod: str
    container: str
    uid: str
    resource_version: str
    image: str
    image_id: str
    ready: bool
    container_id: str

    def __post_init__(self):
        # Structural checks only; the enclosing retained proof supplies authority.
        for field in ('image_role', 'container_type', 'namespace', 'pod', 'container',
                      'uid', 'resource_version', 'image', 'image_id', 'container_id'):
            value = getattr(self, field)
            if type(value) is not str or not value or len(value) > 1024:
                raise KilImageProjectionError('image row strings must be exact and bounded')
        if (self.image_role != 'workload' or self.container_type != 'regular'
                or self.container not in {'authz', 'target', 'envoy', 'driver'} or self.ready is not True):
            raise KilImageProjectionError('image row role/readiness is not exact')
        _uid(self.uid)
        _rv(self.resource_version)
        if re.fullmatch(r'containerd://[0-9a-f]{64}', self.container_id) is None:
            raise KilImageProjectionError('image row container incarnation is invalid')


def _compute(runtime):
    if type(runtime) is not KilPodRuntimeProof:
        raise KilImageProjectionError('runtime proof type must be exact')
    runtime.__post_init__()
    ownership = runtime.configuration.ownership
    rendered = json.loads(ownership.rendered_objects)['items']
    templates = {(row['metadata']['namespace'], row['metadata']['name']): row['spec']['template']['spec']
                 for row in rendered if row['kind'] == 'Deployment'}
    direct = {(row['metadata']['namespace'], row['metadata']['name']): row['spec']
              for row in rendered if row['kind'] == 'Pod'}
    expected = {}
    for binding in runtime.configuration.bindings:
        expected[(binding.namespace, binding.name)] = (
            binding.deployment_name, binding.uid, binding.resource_version,
            templates[(binding.namespace, binding.deployment_name)])
    for binding in runtime.driver_configuration.bindings:
        expected[(binding.namespace, binding.name)] = (
            'driver', binding.uid, binding.resource_version, direct[(binding.namespace, binding.name)])
    if len(expected) != 12 or len(runtime.bindings) != 12:
        raise KilImageProjectionError('image projection must have exactly twelve Pods')
    rows = []
    seen = set()
    for binding in runtime.bindings:
        key = (binding.namespace, binding.name)
        if key in seen or key not in expected:
            raise KilImageProjectionError('image projection Pod identity is not exact')
        seen.add(key)
        role, uid, rv, spec = expected[key]
        if (binding.role, binding.uid, binding.resource_version) != (role, uid, rv):
            raise KilImageProjectionError('image projection configuration join differs')
        containers = spec['containers']
        if len(containers) != 1 or containers[0]['name'] != role:
            raise KilImageProjectionError('requested container identity is not exact')
        rows.append(KilImageRow('workload', 'regular', binding.namespace, binding.name,
                               role, uid, rv, containers[0]['image'], binding.image_ref,
                               True, binding.app_container_id))
    if seen != set(expected):
        raise KilImageProjectionError('image projection Pod set is incomplete')
    return tuple(sorted(rows))


@dataclass(frozen=True, slots=True)
class KilImageProjectionProof:
    runtime: KilPodRuntimeProof
    rows: tuple[KilImageRow, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        if self.runtime_contract_complete is not False or self.full_application_contract_complete is not False:
            raise KilImageProjectionError('image projection cannot complete a runtime or application contract')
        if type(self.rows) is not tuple or len(self.rows) != 12 or any(type(row) is not KilImageRow for row in self.rows):
            raise KilImageProjectionError('image projection rows must be exact bounded records')
        for row in self.rows:
            row.__post_init__()
        if self.rows != _compute(self.runtime):
            raise KilImageProjectionError('image projection differs from retained runtime authority')


def validate_kil_image_projection(*, runtime):
    try:
        return KilImageProjectionProof(runtime, _compute(runtime))
    except KilImageProjectionError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError) as error:
        raise KilImageProjectionError('invalid KIL image projection evidence') from error


__all__ = ('KilImageProjectionError', 'KilImageRow', 'KilImageProjectionProof', 'validate_kil_image_projection')
