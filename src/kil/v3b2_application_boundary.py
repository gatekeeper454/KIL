"""Historical policy barrier joined to the later full application configuration.

This proof deliberately stops before generated ownership and container admission.
"""
from dataclasses import asdict, dataclass
import json

from kil.v3b2_api_defaults import _equal
from kil.v3b2_application_configuration import (
    ApplicationConfigurationProof, ApplicationConfigurationError,
)
from kil.v3b2_policy_stage_checkpoint import decode_policy_stage_checkpoint
from kil.v3b2_proofs import ExpectedContext, canonical, decode


class ApplicationBoundaryError(ValueError):
    pass


@dataclass(frozen=True, slots=True, order=True)
class PolicyContinuityBinding:
    kind: str
    namespace: str
    name: str
    uid: str
    policy_resource_version: str
    final_resource_version: str

    def __post_init__(self):
        from kil.v3b2_driver_pod_admission import _uid, _rv
        if (type(self.kind) is not str or self.kind not in {"Namespace", "NetworkPolicy"}
                or type(self.namespace) is not str or type(self.name) is not str or not self.name):
            raise ApplicationBoundaryError("policy continuity identity is invalid")
        _uid(self.uid); _rv(self.policy_resource_version); _rv(self.final_resource_version)


def _compute(context, checkpoint_bytes, configuration):
    if type(context) is not ExpectedContext or type(configuration) is not ApplicationConfigurationProof:
        raise ApplicationBoundaryError("boundary dependencies must have exact types")
    if type(checkpoint_bytes) is not bytes or not checkpoint_bytes:
        raise ApplicationBoundaryError("checkpoint must be exact retained bytes")
    context.__post_init__(); configuration.__post_init__()
    policy = decode_policy_stage_checkpoint(checkpoint_bytes, context)
    inputs = decode(context.inputs)
    if (policy.profile != configuration.profile or policy.workload != configuration.workload
            or policy.rendered_objects != configuration.rendered_objects
            or policy.owned_identity != configuration.owned_identity
            or not _equal(inputs.get("application_objects"),
                          json.loads(configuration.rendered_objects)["items"])
            or not _equal(inputs.get("applied_objects"),
                          json.loads(configuration.rendered_objects)["items"])):
        raise ApplicationBoundaryError("policy and configuration inputs are not the same application context")
    document = decode(configuration.applied_objects)
    final = {}
    for row in document["items"]:
        if row["kind"] in {"Namespace", "NetworkPolicy"}:
            metadata = row["metadata"]
            key = (row["kind"], metadata.get("namespace", ""), metadata["name"])
            if key in final:
                raise ApplicationBoundaryError("final policy identity is duplicated")
            final[key] = metadata
    bindings = []
    for historical in policy.bindings:
        key = (historical.kind, historical.namespace, historical.name)
        metadata = final.get(key)
        if metadata is None or metadata.get("uid") != historical.uid:
            raise ApplicationBoundaryError("policy UID continuity changed")
        bindings.append(PolicyContinuityBinding(
            historical.kind, historical.namespace, historical.name, historical.uid,
            historical.resource_version, metadata.get("resourceVersion"),
        ))
    result = tuple(sorted(bindings))
    if len(result) != 18 or set(final) != {
            (row.kind, row.namespace, row.name) for row in policy.bindings}:
        raise ApplicationBoundaryError("policy continuity set is not exact")
    return policy, result


@dataclass(frozen=True, slots=True)
class ApplicationBoundaryProof:
    context: ExpectedContext
    checkpoint_bytes: bytes
    configuration: ApplicationConfigurationProof
    policy_continuity: tuple[PolicyContinuityBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if (type(self.runtime_contract_complete) is not bool or self.runtime_contract_complete
                    or type(self.full_application_contract_complete) is not bool
                    or self.full_application_contract_complete):
                raise ApplicationBoundaryError("application boundary cannot claim completion")
            if (type(self.policy_continuity) is not tuple or len(self.policy_continuity) != 18
                    or any(type(row) is not PolicyContinuityBinding for row in self.policy_continuity)):
                raise ApplicationBoundaryError("policy continuity bindings are not exact")
            for row in self.policy_continuity: row.__post_init__()
            _, expected = _compute(self.context, self.checkpoint_bytes, self.configuration)
            if expected != self.policy_continuity:
                raise ApplicationBoundaryError("retained policy continuity differs")
        except ApplicationBoundaryError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError) as error:
            raise ApplicationBoundaryError("invalid application boundary proof") from error

    def summary(self) -> bytes:
        return canonical({
            "policy_continuity": [asdict(row) for row in self.policy_continuity],
            "service_bindings": decode(self.configuration.service_bindings),
            "driver_configuration_bindings": [asdict(row) for row in self.configuration.driver_bindings],
            "runtime_contract_complete": False,
            "full_application_contract_complete": False,
        })


def validate_application_boundary(*, context, checkpoint_bytes, configuration):
    try:
        _, bindings = _compute(context, checkpoint_bytes, configuration)
        return ApplicationBoundaryProof(context, checkpoint_bytes, configuration, bindings)
    except ApplicationBoundaryError:
        raise
    except (ApplicationConfigurationError, ValueError, TypeError, KeyError, AttributeError,
            IndexError, RecursionError) as error:
        raise ApplicationBoundaryError("invalid application boundary evidence") from error


__all__ = ("ApplicationBoundaryError", "PolicyContinuityBinding",
           "ApplicationBoundaryProof", "validate_application_boundary")
