"""Reconstructable ten-platform-Pod configuration coverage, not readiness.

Existing component contracts retain their narrower evidence boundaries. This
composition adds exact coverage and same-source authority joins only; status,
effective images, freshness and runtime/application completion remain unclaimed.
"""
from collections import Counter
from dataclasses import dataclass

from kil.v3b2_calico_node_configuration import CalicoNodeConfigurationProof
from kil.v3b2_calico_controller_configuration import CalicoControllerConfigurationProof
from kil.v3b2_coredns_pod_configuration import CoreDNSPodConfigurationProof
from kil.v3b2_local_path_pod_configuration import LocalPathPodConfigurationProof
from kil.v3b2_kube_proxy_pod_configuration import KubeProxyPodConfigurationProof
from kil.v3b2_scheduler_mirror_configuration import SchedulerMirrorConfigurationProof
from kil.v3b2_etcd_mirror_configuration import EtcdMirrorConfigurationProof
from kil.v3b2_kube_apiserver_mirror_configuration import KubeAPIServerMirrorConfigurationProof
from kil.v3b2_kube_controller_manager_mirror_configuration import KubeControllerManagerMirrorConfigurationProof
from kil.v3b2_node_ownership import _text, _uid, _rv
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof, _document

__all__ = (
    'PlatformPodConfigurationError',
    'PlatformPodConfigurationBinding',
    'PlatformPodConfigurationProof',
    'validate_platform_pod_configuration',
)


class PlatformPodConfigurationError(ValueError):
    """Retained component evidence cannot establish this fixed composition."""


# Fixed reviewed composition, not an extensible component registry. The last
# field selects the existing heterogeneous binding API without changing it.
_COMPONENTS = (
    ('calico-node', CalicoNodeConfigurationProof, 1, True),
    ('calico-kube-controllers', CalicoControllerConfigurationProof, 1, False),
    ('coredns', CoreDNSPodConfigurationProof, 2, False),
    ('local-path-provisioner', LocalPathPodConfigurationProof, 1, False),
    ('kube-proxy', KubeProxyPodConfigurationProof, 1, True),
    ('kube-scheduler', SchedulerMirrorConfigurationProof, 1, True),
    ('etcd', EtcdMirrorConfigurationProof, 1, True),
    ('kube-apiserver', KubeAPIServerMirrorConfigurationProof, 1, True),
    ('kube-controller-manager', KubeControllerManagerMirrorConfigurationProof, 1, True),
)
_MULTIPLICITIES = {component: count for component, _, count, _ in _COMPONENTS}
_DEPLOYMENTS = {
    ('kube-system', 'coredns'),
    ('kube-system', 'calico-kube-controllers'),
    ('local-path-storage', 'local-path-provisioner'),
}
_MALFORMED = (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError)


@dataclass(frozen=True, slots=True, order=True)
class PlatformPodConfigurationBinding:
    component: str
    namespace: str
    pod_name: str
    pod_uid: str
    pod_resource_version: str

    def __post_init__(self):
        try:
            if type(self.component) is not str or self.component not in _MULTIPLICITIES:
                raise PlatformPodConfigurationError('component is not a reviewed platform identity')
            namespace = ('local-path-storage' if self.component == 'local-path-provisioner'
                         else 'kube-system')
            if type(self.namespace) is not str or self.namespace != namespace:
                raise PlatformPodConfigurationError('namespace/component pair is not reviewed')
            _text('platform Pod name', self.pod_name)
            _uid(self.pod_uid)
            _rv(self.pod_resource_version)
        except PlatformPodConfigurationError:
            raise
        except _MALFORMED as error:
            raise PlatformPodConfigurationError('invalid platform Pod binding identity') from error


def _coverage(bindings):
    """Require the fixed ten-incarnation identity domain, independently of status."""
    if (len(bindings) != 10
            or Counter(binding.component for binding in bindings) != _MULTIPLICITIES
            or len({(binding.namespace, binding.pod_name) for binding in bindings}) != 10
            or len({binding.pod_uid for binding in bindings}) != 10):
        raise PlatformPodConfigurationError('platform coverage is not the exact ten unique incarnations')
    return tuple(sorted(bindings))


def _compute(ownership, calico_node, calico_controller, coredns, local_path,
             kube_proxy, scheduler, etcd, apiserver, controller_manager):
    proofs = (calico_node, calico_controller, coredns, local_path, kube_proxy,
              scheduler, etcd, apiserver, controller_manager)
    # All top-level types and tuple cardinalities precede any reconstruction,
    # binding iteration or retained raw decoding.
    if type(ownership) is not RuntimeOwnershipProof:
        raise PlatformPodConfigurationError('ownership dependency must be exact RuntimeOwnershipProof')
    for proof, (component, cls, _, _) in zip(proofs, _COMPONENTS):
        if type(proof) is not cls:
            raise PlatformPodConfigurationError(f'{component} dependency type must be exact')
    for proof, (component, _, count, _) in zip(proofs, _COMPONENTS):
        if type(proof.bindings) is not tuple or len(proof.bindings) != count:
            raise PlatformPodConfigurationError(f'{component} binding tuple cardinality is not exact')

    ownership.__post_init__()
    for proof in proofs:
        proof.__post_init__()
    retained_ownership = (
        calico_node.revision.ownership,
        calico_controller.ownership,
        coredns.parent.ownership,
        local_path.parent.ownership,
        kube_proxy.revision.parent.ownership,
        scheduler.ownership,
        etcd.ownership,
        apiserver.ownership,
        controller_manager.ownership,
    )
    if any(value != ownership for value in retained_ownership):
        raise PlatformPodConfigurationError('component ownership differs from complete retained authority')
    if any(type(raw) is not bytes for raw in (
            calico_node.revision.calico_source, calico_node.revision.calico_projection,
            calico_controller.calico_source, calico_controller.calico_projection)):
        raise PlatformPodConfigurationError('Calico authority must be exact bytes')
    if (calico_node.revision.calico_source != calico_controller.calico_source
            or calico_node.revision.calico_projection != calico_controller.calico_projection):
        raise PlatformPodConfigurationError('Calico source/projection authorities differ')
    if apiserver.source != controller_manager.source:
        raise PlatformPodConfigurationError('complete manifest source authorities differ')

    projected = []
    for proof, (component, _, _, prefixed) in zip(proofs, _COMPONENTS):
        for binding in proof.bindings:
            name, uid, rv = ((binding.pod_name, binding.pod_uid, binding.pod_resource_version)
                             if prefixed else (binding.name, binding.uid, binding.resource_version))
            projected.append(PlatformPodConfigurationBinding(
                component, binding.namespace, name, uid, rv))
    projected = _coverage(projected)

    # Coverage expectations come only from reconstructed ownership, never from
    # candidate configuration, Pod command/image/annotation or status fields.
    expected = []
    for binding in ownership.deployment_ownership.bindings:
        if (binding.namespace, binding.deployment_name) in _DEPLOYMENTS:
            for name, uid, rv in binding.pods:
                expected.append(PlatformPodConfigurationBinding(
                    binding.deployment_name, binding.namespace, name, uid, rv))
    for binding in ownership.node_ownership.daemon_pods:
        expected.append(PlatformPodConfigurationBinding(
            binding.daemon_set_name, binding.namespace, binding.pod_name,
            binding.pod_uid, binding.pod_resource_version))
    for binding in ownership.node_ownership.static_pods:
        expected.append(PlatformPodConfigurationBinding(
            binding.component, 'kube-system', binding.pod_name,
            binding.pod_uid, binding.pod_resource_version))
    expected = _coverage(expected)
    if projected != expected:
        raise PlatformPodConfigurationError('component projection differs from owned platform Pod coverage')

    # Reuse the ownership decoder's established byte and structural bounds,
    # after ownership reconstruction; unrelated/application objects are not
    # projected into coverage and cannot compensate for a missing incarnation.
    rows = _document(ownership.runtime_objects)
    for binding in expected:
        matching = [row for row in rows if row['apiVersion'] == 'v1' and row['kind'] == 'Pod'
                    and row['metadata'].get('namespace') == binding.namespace
                    and row['metadata']['name'] == binding.pod_name
                    and row['metadata']['uid'] == binding.pod_uid
                    and row['metadata']['resourceVersion'] == binding.pod_resource_version]
        if len(matching) != 1:
            raise PlatformPodConfigurationError('expected one matching retained raw platform Pod incarnation')
    return projected


@dataclass(frozen=True, slots=True)
class PlatformPodConfigurationProof:
    ownership: RuntimeOwnershipProof
    calico_node: CalicoNodeConfigurationProof
    calico_controller: CalicoControllerConfigurationProof
    coredns: CoreDNSPodConfigurationProof
    local_path: LocalPathPodConfigurationProof
    kube_proxy: KubeProxyPodConfigurationProof
    scheduler: SchedulerMirrorConfigurationProof
    etcd: EtcdMirrorConfigurationProof
    apiserver: KubeAPIServerMirrorConfigurationProof
    controller_manager: KubeControllerManagerMirrorConfigurationProof
    bindings: tuple[PlatformPodConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if (self.runtime_contract_complete is not False
                    or self.full_application_contract_complete is not False):
                raise PlatformPodConfigurationError('platform configuration cannot establish completion')
            if type(self.bindings) is not tuple or len(self.bindings) != 10:
                raise PlatformPodConfigurationError('expected exact tuple of ten platform bindings')
            if any(type(binding) is not PlatformPodConfigurationBinding for binding in self.bindings):
                raise PlatformPodConfigurationError('platform binding types must be exact')
            for binding in self.bindings:
                binding.__post_init__()
            bindings = _compute(self.ownership, self.calico_node, self.calico_controller,
                self.coredns, self.local_path, self.kube_proxy, self.scheduler,
                self.etcd, self.apiserver, self.controller_manager)
            if self.bindings != bindings:
                raise PlatformPodConfigurationError('bindings differ from complete same-source reconstruction')
        except PlatformPodConfigurationError:
            raise
        except _MALFORMED as error:
            raise PlatformPodConfigurationError('invalid platform Pod configuration proof') from error


def validate_platform_pod_configuration(
        *, ownership: RuntimeOwnershipProof,
        calico_node: CalicoNodeConfigurationProof,
        calico_controller: CalicoControllerConfigurationProof,
        coredns: CoreDNSPodConfigurationProof,
        local_path: LocalPathPodConfigurationProof,
        kube_proxy: KubeProxyPodConfigurationProof,
        scheduler: SchedulerMirrorConfigurationProof,
        etcd: EtcdMirrorConfigurationProof,
        apiserver: KubeAPIServerMirrorConfigurationProof,
        controller_manager: KubeControllerManagerMirrorConfigurationProof,
        ) -> PlatformPodConfigurationProof:
    """Compose existing configuration contracts without strengthening their claims."""
    try:
        inputs = (ownership, calico_node, calico_controller, coredns, local_path,
                  kube_proxy, scheduler, etcd, apiserver, controller_manager)
        return PlatformPodConfigurationProof(*inputs, _compute(*inputs))
    except PlatformPodConfigurationError:
        raise
    except _MALFORMED as error:
        raise PlatformPodConfigurationError('invalid platform Pod configuration inputs') from error
