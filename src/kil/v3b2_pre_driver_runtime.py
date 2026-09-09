"""Nine generated KIL Pod runtime joins before any direct driver exists.

All projections are rederived from the exact retained 19-Pod ownership List.
Optional source-known status fields retain the existing bounded, uninterpreted
semantics. This proof establishes neither full platform nor application completion.
"""
from dataclasses import dataclass

from kil.v3b2_pre_driver_ownership import PreDriverOwnershipProof
from kil.v3b2_node_image_references import NodeImageReferenceProof
from kil.v3b2_generated_kil_pod_configuration import GeneratedKilPodConfigurationBinding, _extract_configuration
from kil.v3b2_runtime_endpoints import _extract_endpoints
from kil.v3b2_service_bindings import ServiceAllocation
from kil.v3b2_platform_endpoints import PlatformEndpointProof
from kil.v3b2_kil_endpoint_ownership import KilEndpointOwnershipProof
from kil.v3b2_kil_pod_runtime import KilPodRuntimeBinding, _extract_runtime_bindings


class PreDriverRuntimeError(ValueError):
    pass


def _compute(ownership, node_images):
    if type(ownership) is not PreDriverOwnershipProof or type(node_images) is not NodeImageReferenceProof:
        raise PreDriverRuntimeError("pre-driver dependency types must be exact")
    ownership.__post_init__(); node_images.__post_init__()
    # Only this exact zero-driver ownership proof permits no driver reservation.
    configuration = _extract_configuration(ownership, driver_namespaces=())
    allocation, platform, endpoints = _extract_endpoints(ownership)
    expected = {(b.namespace, b.name): (b.deployment_name, b.uid, b.resource_version)
                for b in configuration}
    bindings = _extract_runtime_bindings(ownership, node_images, platform, endpoints, expected)
    return configuration, allocation, platform, endpoints, bindings


@dataclass(frozen=True, slots=True)
class PreDriverRuntimeProof:
    ownership: PreDriverOwnershipProof
    node_images: NodeImageReferenceProof
    configuration_bindings: tuple[GeneratedKilPodConfigurationBinding, ...]
    service_allocation: ServiceAllocation
    platform_endpoints: PlatformEndpointProof
    kil_endpoints: KilEndpointOwnershipProof
    bindings: tuple[KilPodRuntimeBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if self.runtime_contract_complete is not False or self.full_application_contract_complete is not False:
                raise PreDriverRuntimeError("pre-driver proof cannot establish completion")
            for rows, cls in ((self.configuration_bindings, GeneratedKilPodConfigurationBinding),
                              (self.bindings, KilPodRuntimeBinding)):
                if type(rows) is not tuple or len(rows) != 9 or any(type(row) is not cls for row in rows):
                    raise PreDriverRuntimeError("retained bindings must be an exact tuple of nine")
                for row in rows: row.__post_init__()
            if (type(self.service_allocation) is not ServiceAllocation
                    or type(self.platform_endpoints) is not PlatformEndpointProof
                    or type(self.kil_endpoints) is not KilEndpointOwnershipProof):
                raise PreDriverRuntimeError("retained endpoint proof types must be exact")
            if any(type(raw) is not bytes or len(raw) > 8 * 1024 * 1024 for raw in
                   (self.service_allocation.bindings, self.service_allocation.configurations)):
                raise PreDriverRuntimeError("retained allocation fields must be bounded bytes")
            self.platform_endpoints.__post_init__(); self.kil_endpoints.__post_init__()
            if (self.configuration_bindings, self.service_allocation, self.platform_endpoints,
                    self.kil_endpoints, self.bindings) != _compute(self.ownership, self.node_images):
                raise PreDriverRuntimeError("retained projections differ from same-source reconstruction")
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
            if isinstance(error, PreDriverRuntimeError): raise
            raise PreDriverRuntimeError("invalid pre-driver runtime proof") from error


def validate_pre_driver_runtime(*, ownership, node_images):
    """Validate the nine generated KIL Pods using independent node image evidence."""
    try:
        return PreDriverRuntimeProof(ownership, node_images, *_compute(ownership, node_images))
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        if isinstance(error, PreDriverRuntimeError): raise
        raise PreDriverRuntimeError("invalid pre-driver runtime evidence") from error


__all__ = ("PreDriverRuntimeError", "PreDriverRuntimeProof", "validate_pre_driver_runtime")
