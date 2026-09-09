"""Retain source-path ownership before any of the three direct drivers exist.

The exact 19-Pod phase shares extraction rules with runtime ownership, but is a
distinct proof. It establishes no readiness, image or configuration claims.
"""
from dataclasses import dataclass

from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_deployment_ownership import DeploymentOwnershipProof
from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_manifests import WorkloadIdentity
from kil.v3b2_node_ownership import NodeOwnershipProof
from kil.v3b2_runtime_ownership import _extract_ownership


class PreDriverOwnershipError(ValueError):
    pass


def _compute(profile, workload, rendered_objects, owned_identity, runtime_objects):
    return _extract_ownership(profile, workload, rendered_objects, owned_identity, runtime_objects,
                              expected_direct_drivers=0)


@dataclass(frozen=True, slots=True)
class PreDriverOwnershipProof:
    profile: V3B2Profile
    workload: WorkloadIdentity
    rendered_objects: bytes
    owned_identity: OwnedIdentity
    runtime_objects: bytes
    deployment_ownership: DeploymentOwnershipProof
    node_ownership: NodeOwnershipProof
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in
                   (self.runtime_contract_complete, self.full_application_contract_complete)):
                raise PreDriverOwnershipError("ownership cannot establish full completion")
            if type(self.deployment_ownership) is not DeploymentOwnershipProof or type(self.node_ownership) is not NodeOwnershipProof:
                raise PreDriverOwnershipError("retained ownership proof types must be exact")
            self.deployment_ownership.__post_init__(); self.node_ownership.__post_init__()
            deployment, node = _compute(self.profile, self.workload, self.rendered_objects,
                                        self.owned_identity, self.runtime_objects)
            if deployment != self.deployment_ownership or node != self.node_ownership:
                raise PreDriverOwnershipError("ownership differs from same-source reconstruction")
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            if isinstance(error, PreDriverOwnershipError): raise
            raise PreDriverOwnershipError("invalid pre-driver ownership proof") from error


def validate_pre_driver_ownership(*, profile, workload, rendered_objects, owned_identity, runtime_objects):
    """Validate ownership from a full retained API List with no direct drivers."""
    try:
        deployment, node = _compute(profile, workload, rendered_objects, owned_identity, runtime_objects)
        return PreDriverOwnershipProof(profile, workload, rendered_objects, owned_identity,
                                       runtime_objects, deployment, node)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        if isinstance(error, PreDriverOwnershipError): raise
        raise PreDriverOwnershipError("invalid pre-driver ownership observation") from error
