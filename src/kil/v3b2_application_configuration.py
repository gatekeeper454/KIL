"""Same-observation configuration composition; neither application nor runtime completion.

The exact rendered sixty-object set supplies all desired configuration. Initial
Service allocations and direct driver configuration are derived from one retained
raw API List. Status is retained as bounded JSON, but never validated or used as
identity/configuration authority. Policy checkpoints, generated Pod ownership,
fresh observation transport, later allocation continuity and readiness are separate.
The pinned kubectl v1.36.1 printGeneric composite List carries metadata with an
empty resourceVersion; it is retained without claiming a shared snapshot version.
An omitted metadata member remains supported for existing direct-List fixtures.
Source: https://github.com/kubernetes/kubernetes/blob/v1.36.1/staging/src/k8s.io/kubectl/pkg/cmd/get/get.go
"""
from dataclasses import dataclass
import json

from kil.v3b2_api_defaults import _equal, object_key, matches_configuration
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_driver_pod_admission import _uid, _rv
from kil.v3b2_driver_pod_configuration import (
    DriverPodConfigurationBinding, validate_driver_pod_configuration,
)
from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_manifests import WorkloadIdentity, render_objects
from kil.v3b2_service_bindings import validate_service_allocations

_MAX_BYTES = 2 * 1024 * 1024


class ApplicationConfigurationError(ValueError):
    """The retained applied List cannot establish the bounded configuration relation."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ApplicationConfigurationError("duplicate JSON member")
        result[key] = value
    return result


def _precheck(value, depth=0, budget=None):
    if budget is None: budget = [0]
    budget[0] += 1
    if depth > 24 or budget[0] > 65536:
        raise ApplicationConfigurationError("application projection exceeds structural bounds")
    if value is None or type(value) is bool: return
    if type(value) is int:
        if value.bit_length() > 64: raise ApplicationConfigurationError("unbounded integer")
        return
    if type(value) is str:
        if len(value) > 262144 or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ApplicationConfigurationError("unbounded or invalid string")
        return
    if type(value) is dict:
        if len(value) > 256 or any(type(key) is not str or not key or len(key) > 4096 for key in value):
            raise ApplicationConfigurationError("invalid object keys")
        for key, item in value.items():
            _precheck(key, depth + 1, budget); _precheck(item, depth + 1, budget)
        return
    if type(value) is list:
        if len(value) > 256: raise ApplicationConfigurationError("unbounded array")
        for item in value: _precheck(item, depth + 1, budget)
        return
    raise ApplicationConfigurationError("non-JSON projection value")


def _document(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_BYTES:
        raise ApplicationConfigurationError("applied List must be bounded exact bytes")
    document = json.loads(raw, object_pairs_hook=_pairs)
    if (type(document) is not dict or set(document) not in (
            {"apiVersion", "kind", "items"}, {"apiVersion", "kind", "metadata", "items"})
            or document["apiVersion"] != "v1" or document["kind"] != "List"
            or type(document["items"]) is not list or len(document["items"]) != 60):
        raise ApplicationConfigurationError("applied root is not the exact sixty-object List")
    if "metadata" in document and not _equal(document["metadata"], {"resourceVersion": ""}):
        raise ApplicationConfigurationError("composite List metadata is not the reviewed empty resourceVersion")
    _precheck(document)
    return document


def _compute(profile, workload, rendered_objects, owned_identity, applied_objects):
    observed = _document(applied_objects)
    if (type(profile) is not V3B2Profile or type(workload) is not WorkloadIdentity
            or type(owned_identity) is not OwnedIdentity):
        raise ApplicationConfigurationError("dependency types must be exact")
    profile.__post_init__(); workload.__post_init__(); owned_identity.__post_init__()
    if any(getattr(owned_identity, field) is None for field in
           ("docker_host", "kind_cluster", "kubeconfig", "cluster_incarnation_uid", "node_container_id")):
        raise ApplicationConfigurationError("owned Kind identity is incomplete")
    if type(rendered_objects) is not bytes or len(rendered_objects) > _MAX_BYTES:
        raise ApplicationConfigurationError("rendered expectations must be bounded exact bytes")
    independent = render_objects(profile, workload)
    if independent != rendered_objects:
        raise ApplicationConfigurationError("rendered expectations differ from independent inputs")
    desired = {object_key(row): row for row in json.loads(independent)["items"]}
    indexed, uids = {}, {owned_identity.cluster_incarnation_uid}
    for row in observed["items"]:
        if type(row) is not dict:
            raise ApplicationConfigurationError("applied objects must be exact dicts")
        key = object_key(row)
        if key not in desired or key in indexed:
            raise ApplicationConfigurationError("object identity is unexpected or duplicated")
        metadata = row["metadata"]
        uid, _ = _uid(metadata.get("uid")), _rv(metadata.get("resourceVersion"))
        if uid in uids:
            raise ApplicationConfigurationError("applied UID collides in the retained Kubernetes identity domain")
        uids.add(uid); indexed[key] = row
    if len(desired) != 60 or set(indexed) != set(desired):
        raise ApplicationConfigurationError("applied identity set differs from exact rendered sixty")
    services = [row for key, row in indexed.items() if key[1] == "Service"]
    allocation = validate_service_allocations(services, profile=profile, workload=workload)
    pods = []
    for key, row in indexed.items():
        if key[1] == "Pod":
            if set(row) not in ({"apiVersion", "kind", "metadata", "spec"},
                                {"apiVersion", "kind", "metadata", "spec", "status"}):
                raise ApplicationConfigurationError("driver root contains unreviewed projection fields")
            # Only status is excluded from the configuration-only subproof;
            # every metadata/spec member remains present and raw bytes retained.
            pods.append({name: value for name, value in row.items() if name != "status"})
        elif key[1] != "Service" and not matches_configuration(desired[key], row):
            raise ApplicationConfigurationError("static applied configuration differs from expected inputs")
    drivers = validate_driver_pod_configuration(profile=profile, workload=workload,
        rendered_objects=rendered_objects, owned_identity=owned_identity, pods=pods)
    return allocation.bindings, drivers.bindings


@dataclass(frozen=True, slots=True)
class ApplicationConfigurationProof:
    profile: V3B2Profile
    workload: WorkloadIdentity
    rendered_objects: bytes
    owned_identity: OwnedIdentity
    applied_objects: bytes
    service_bindings: bytes
    driver_bindings: tuple[DriverPodConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            for flag in (self.runtime_contract_complete, self.full_application_contract_complete):
                if type(flag) is not bool or flag:
                    raise ApplicationConfigurationError("configuration composition cannot claim completion")
            if type(self.service_bindings) is not bytes or len(self.service_bindings) > 16384:
                raise ApplicationConfigurationError("Service binding bytes are invalid")
            if type(self.driver_bindings) is not tuple or len(self.driver_bindings) != 3:
                raise ApplicationConfigurationError("driver bindings must be an exact tuple of three")
            for binding in self.driver_bindings:
                if type(binding) is not DriverPodConfigurationBinding:
                    raise ApplicationConfigurationError("driver binding type is invalid")
                binding.__post_init__()
            service, drivers = _compute(self.profile, self.workload, self.rendered_objects,
                                        self.owned_identity, self.applied_objects)
            if service != self.service_bindings or drivers != self.driver_bindings:
                raise ApplicationConfigurationError("retained bindings differ from same-source reconstruction")
        except (ValueError, TypeError, AttributeError, KeyError, RecursionError) as error:
            if isinstance(error, ApplicationConfigurationError): raise
            raise ApplicationConfigurationError("invalid application configuration proof") from error


def validate_application_configuration(*, profile: V3B2Profile, workload: WorkloadIdentity,
                                       rendered_objects: bytes, owned_identity: OwnedIdentity,
                                       applied_objects: bytes) -> ApplicationConfigurationProof:
    """Prove configuration and initial allocation over one full retained API List."""
    try:
        services, drivers = _compute(profile, workload, rendered_objects, owned_identity, applied_objects)
        return ApplicationConfigurationProof(profile, workload, rendered_objects, owned_identity,
                                              applied_objects, services, drivers)
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError) as error:
        if isinstance(error, ApplicationConfigurationError): raise
        raise ApplicationConfigurationError("invalid application configuration observation") from error
