"""Pure historical-to-current application runtime continuity, without completion.

The caller authenticates ExpectedContext. No filesystem or current observations
are collected here; all current claims derive from the retained twelve-Pod source.
"""
from dataclasses import asdict, dataclass

from kil.v3b2_application_boundary import ApplicationBoundaryProof, validate_application_boundary
from kil.v3b2_application_configuration import validate_application_configuration
from kil.v3b2_kil_pod_runtime import KilPodRuntimeProof, KilPodRuntimeBinding
from kil.v3b2_manifests import render_objects
from kil.v3b2_pre_driver_checkpoint import decode_pre_driver_checkpoint
from kil.v3b2_proofs import ExpectedContext, canonical, decode


class ApplicationRuntimeBoundaryError(ValueError):
    pass


@dataclass(frozen=True, slots=True, order=True)
class RuntimeContinuityBinding:
    namespace: str
    role: str
    name: str
    uid: str
    pre_driver_resource_version: str
    final_resource_version: str
    pod_ip: str
    cni_sandbox_id: str
    app_container_id: str
    runtime_image: str
    image_ref: str
    started_at: str

    def __post_init__(self):
        if self.role not in {'authz', 'envoy', 'target'}:
            raise ApplicationRuntimeBoundaryError('continuity role is not generated')
        for rv in (self.pre_driver_resource_version, self.final_resource_version):
            KilPodRuntimeBinding(self.namespace, self.role, self.name, self.uid, rv,
                self.pod_ip, self.cni_sandbox_id, self.app_container_id,
                self.runtime_image, self.image_ref, self.started_at)


def _key(row):
    return row['kind'], row['metadata'].get('namespace', ''), row['metadata']['name']


def _compute(context, checkpoint_bytes, runtime):
    if type(context) is not ExpectedContext or type(runtime) is not KilPodRuntimeProof:
        raise ApplicationRuntimeBoundaryError('boundary dependency types must be exact')
    if type(checkpoint_bytes) is not bytes or not checkpoint_bytes:
        raise ApplicationRuntimeBoundaryError('checkpoint must retain exact bytes')
    context.__post_init__()
    pre = decode_pre_driver_checkpoint(checkpoint_bytes, context)
    runtime.__post_init__()
    historical = pre.runtime.ownership
    current = runtime.configuration.ownership
    if any(getattr(historical, name) != getattr(current, name) for name in
           ('profile', 'workload', 'owned_identity', 'rendered_objects')):
        raise ApplicationRuntimeBoundaryError('independent application authority changed')
    if runtime.node_images != pre.runtime.node_images:
        raise ApplicationRuntimeBoundaryError('historical node image authority changed')
    independent = render_objects(current.profile, current.workload)
    keys = {_key(row) for row in decode(independent)['items']}
    document = decode(current.runtime_objects, maximum=8 * 1024 * 1024)
    selected = [row for row in document['items'] if _key(row) in keys]
    configuration = validate_application_configuration(profile=current.profile,
        workload=current.workload, rendered_objects=independent, owned_identity=current.owned_identity,
        applied_objects=canonical({'apiVersion': 'v1', 'kind': 'List', 'items': selected}))
    boundary = validate_application_boundary(context=context,
        checkpoint_bytes=pre.policy_checkpoint_bytes, configuration=configuration)
    before = {(b.namespace, b.role, b.name): b for b in pre.runtime.bindings}
    after = {(b.namespace, b.role, b.name): b for b in runtime.bindings if b.role != 'driver'}
    if len(before) != 9 or set(before) != set(after):
        raise ApplicationRuntimeBoundaryError('continuity identity set differs')
    bindings = []
    fields = ('uid', 'pod_ip', 'cni_sandbox_id', 'app_container_id', 'runtime_image', 'image_ref', 'started_at')
    for key, old in before.items():
        new = after[key]
        if any(getattr(old, field) != getattr(new, field) for field in fields):
            raise ApplicationRuntimeBoundaryError('generated Pod runtime incarnation changed')
        bindings.append(RuntimeContinuityBinding(*key, old.uid, old.resource_version,
            new.resource_version, old.pod_ip, old.cni_sandbox_id, old.app_container_id,
            old.runtime_image, old.image_ref, old.started_at))
    return boundary, tuple(sorted(bindings))


@dataclass(frozen=True, slots=True)
class ApplicationRuntimeBoundaryProof:
    context: ExpectedContext
    pre_driver_checkpoint_bytes: bytes
    runtime: KilPodRuntimeProof
    application_boundary: ApplicationBoundaryProof
    runtime_continuity: tuple[RuntimeContinuityBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if self.runtime_contract_complete is not False or self.full_application_contract_complete is not False:
                raise ApplicationRuntimeBoundaryError('runtime boundary cannot claim completion')
            if (type(self.application_boundary) is not ApplicationBoundaryProof
                    or type(self.runtime_continuity) is not tuple or len(self.runtime_continuity) != 9
                    or any(type(row) is not RuntimeContinuityBinding for row in self.runtime_continuity)):
                raise ApplicationRuntimeBoundaryError('retained boundary fields are not exact')
            self.application_boundary.__post_init__()
            for row in self.runtime_continuity:
                row.__post_init__()
            if _compute(self.context, self.pre_driver_checkpoint_bytes, self.runtime) != (
                    self.application_boundary, self.runtime_continuity):
                raise ApplicationRuntimeBoundaryError('retained boundary differs from reconstruction')
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError) as error:
            if isinstance(error, ApplicationRuntimeBoundaryError):
                raise
            raise ApplicationRuntimeBoundaryError('invalid retained runtime boundary') from error

    def summary(self) -> bytes:
        return canonical({'runtime_continuity': [asdict(row) for row in self.runtime_continuity],
            'policy_continuity': [asdict(row) for row in self.application_boundary.policy_continuity],
            'runtime_contract_complete': False, 'full_application_contract_complete': False})


def validate_application_runtime_boundary(*, context: ExpectedContext,
        pre_driver_checkpoint_bytes: bytes, runtime: KilPodRuntimeProof) -> ApplicationRuntimeBoundaryProof:
    try:
        boundary, bindings = _compute(context, pre_driver_checkpoint_bytes, runtime)
        return ApplicationRuntimeBoundaryProof(context, pre_driver_checkpoint_bytes, runtime, boundary, bindings)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError) as error:
        if isinstance(error, ApplicationRuntimeBoundaryError):
            raise
        raise ApplicationRuntimeBoundaryError('invalid application runtime boundary evidence') from error


__all__ = ('ApplicationRuntimeBoundaryError', 'RuntimeContinuityBinding',
           'ApplicationRuntimeBoundaryProof', 'validate_application_runtime_boundary')
