"""Closed Deployment -> ReplicaSet -> Pod ownership evidence for V3B-2a."""

from __future__ import annotations

from dataclasses import dataclass
import re

_APPLICATION_NAMESPACES = (
    "kil-v3-baseline",
    "kil-v3-local-reduce",
    "kil-v3-signed",
)
_DEPLOYMENT_KEYS = frozenset({
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "revision", "replicas",
})
_REPLICA_SET_KEYS = frozenset({
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "revision", "podTemplateHash", "ownerReference",
})
_POD_KEYS = frozenset({
    "apiVersion", "kind", "namespace", "name", "uid", "resourceVersion",
    "podTemplateHash", "ownerReference",
})
_OWNER_KEYS = frozenset({
    "apiVersion", "kind", "name", "uid", "controller", "blockOwnerDeletion",
})
_DNS_LABEL = re.compile(r"[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?")
# Pinned Kubernetes ComputeHash safely encodes a decimal uint32: 1-10 chars.
# Owner names and every Pod label/reference still bind the exact same value.
_HASH = re.compile(r"[a-z0-9]{1,10}")
_POD_SUFFIX = re.compile(r"[a-z0-9]{5}")
_UINT64_MAX = 18_446_744_073_709_551_615

class DeploymentOwnershipError(ValueError):
    """Raised when the ownership projection is open, ambiguous, or forged."""

def _text(
    label: str,
    value: object,
    *,
    max_chars: int,
    max_bytes: int,
    empty: bool = False,
) -> str:
    if type(value) is not str or (not empty and not value):
        raise DeploymentOwnershipError(f"{label} must be an exact bounded string")
    if len(value) > max_chars:
        raise DeploymentOwnershipError(f"{label} exceeds its character bound")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise DeploymentOwnershipError(f"{label} must contain Unicode scalar values")
    if len(value.encode("utf-8")) > max_bytes:
        raise DeploymentOwnershipError(f"{label} exceeds its byte bound")
    return value

def _name(label: str, value: object) -> str:
    result = _text(label, value, max_chars=63, max_bytes=63)
    if _DNS_LABEL.fullmatch(result) is None:
        raise DeploymentOwnershipError(f"{label} must be a conservative DNS label")
    return result


def _uid(label: str, value: object) -> str:
    return _text(label, value, max_chars=256, max_bytes=1024)

def _uint64(label: str, value: object) -> str:
    result = _text(label, value, max_chars=20, max_bytes=20)
    if not result.isascii() or not result.isdigit() or result.startswith("0"):
        raise DeploymentOwnershipError(f"{label} must be a canonical positive uint64")
    if int(result) > _UINT64_MAX:
        raise DeploymentOwnershipError(f"{label} exceeds uint64")
    return result

def _revision(value: object) -> str:
    result = _uint64("revision", value)
    if result != "1":
        raise DeploymentOwnershipError("fresh Deployment and ReplicaSet revisions must be 1")
    return result


def _closed(record: object, keys: frozenset[str], label: str) -> dict:
    if type(record) is not dict:
        raise DeploymentOwnershipError(f"{label} must be an exact dict")
    if len(record) != len(keys):
        raise DeploymentOwnershipError(f"{label} has an open or incomplete shape")
    if any(type(key) is not str for key in record):
        raise DeploymentOwnershipError(f"{label} keys must be exact strings")
    if set(record) != keys:
        raise DeploymentOwnershipError(f"{label} has an open or incomplete shape")
    return record


def _constant(label: str, value: object, expected: str) -> None:
    if _text(label, value, max_chars=32, max_bytes=32) != expected:
        raise DeploymentOwnershipError(f"{label} must be {expected}")


def _owner(record: object, *, kind: str) -> tuple[str, str]:
    owner = _closed(record, _OWNER_KEYS, "ownerReference")
    _constant("ownerReference.apiVersion", owner["apiVersion"], "apps/v1")
    _constant("ownerReference.kind", owner["kind"], kind)
    name = _name("ownerReference.name", owner["name"])
    uid = _uid("ownerReference.uid", owner["uid"])
    if owner["controller"] is not True or owner["blockOwnerDeletion"] is not True:
        raise DeploymentOwnershipError(
            "ownerReference controller and blockOwnerDeletion must be exact true",
        )
    return name, uid


def _expected() -> dict[tuple[str, str], int]:
    result = {
        ("kube-system", "coredns"): 2,
        ("kube-system", "calico-kube-controllers"): 1,
        ("local-path-storage", "local-path-provisioner"): 1,
    }
    for namespace in _APPLICATION_NAMESPACES:
        for name in ("authz", "envoy", "target"):
            result[(namespace, name)] = 1
    return result


_EXPECTED = _expected()


def _pod_tuple(value: object, *, expected_count: int) -> tuple[tuple[str, str, str], ...]:
    if type(value) is not tuple or len(value) != expected_count:
        raise DeploymentOwnershipError("pods must be an exact tuple of the replica count")
    checked: list[tuple[str, str, str]] = []
    for pod in value:
        if type(pod) is not tuple or len(pod) != 3:
            raise DeploymentOwnershipError("each Pod proof must be an exact triple")
        name = _name("pod.name", pod[0])
        uid = _uid("pod.uid", pod[1])
        resource_version = _uint64("pod.resourceVersion", pod[2])
        checked.append((name, uid, resource_version))
    result = tuple(checked)
    if result != value or result != tuple(sorted(result)) or len(set(result)) != len(result):
        raise DeploymentOwnershipError("Pod proofs must be exact, unique, and canonical")
    return result


@dataclass(frozen=True, slots=True, order=True)
class DeploymentBinding:
    namespace: str
    deployment_name: str
    deployment_uid: str
    deployment_resource_version: str
    revision: str
    replicas: int
    replica_set_name: str
    replica_set_uid: str
    replica_set_resource_version: str
    pod_template_hash: str
    pods: tuple[tuple[str, str, str], ...]

    def __post_init__(self) -> None:
        try:
            _name("namespace", self.namespace)
            _name("deployment_name", self.deployment_name)
            _uid("deployment_uid", self.deployment_uid)
            _uint64("deployment_resource_version", self.deployment_resource_version)
            _revision(self.revision)
            if type(self.replicas) is not int or self.replicas <= 0:
                raise DeploymentOwnershipError("replicas must be an exact positive integer")
            if _EXPECTED.get((self.namespace, self.deployment_name)) != self.replicas:
                raise DeploymentOwnershipError("binding identity or replica count is not expected")
            _name("replica_set_name", self.replica_set_name)
            _uid("replica_set_uid", self.replica_set_uid)
            _uint64("replica_set_resource_version", self.replica_set_resource_version)
            hash_value = _text(
                "pod_template_hash", self.pod_template_hash,
                max_chars=10, max_bytes=10,
            )
            if _HASH.fullmatch(hash_value) is None:
                raise DeploymentOwnershipError("pod template hash must be 1-10 lowercase alphanumerics")
            if self.replica_set_name != f"{self.deployment_name}-{hash_value}":
                raise DeploymentOwnershipError("ReplicaSet name is not Deployment-hash bound")
            pods = _pod_tuple(self.pods, expected_count=self.replicas)
            prefix = self.replica_set_name + "-"
            for pod_name, _, _ in pods:
                if not pod_name.startswith(prefix) or _POD_SUFFIX.fullmatch(pod_name[len(prefix):]) is None:
                    raise DeploymentOwnershipError("Pod name is not ReplicaSet-suffix bound")
            identities = [self.deployment_uid, self.replica_set_uid]
            identities.extend(pod[1] for pod in pods)
            if len(set(identities)) != len(identities):
                raise DeploymentOwnershipError("binding UIDs must be globally distinct")
        except DeploymentOwnershipError:
            raise
        except (TypeError, ValueError, UnicodeError, OverflowError, AttributeError) as error:
            raise DeploymentOwnershipError("invalid Deployment ownership binding") from error


@dataclass(frozen=True, slots=True)
class DeploymentOwnershipProof:
    application_namespaces: tuple[str, ...]
    bindings: tuple[DeploymentBinding, ...]
    runtime_contract_complete: bool = False

    def __post_init__(self) -> None:
        try:
            _application_namespaces(self.application_namespaces)
            if type(self.bindings) is not tuple or len(self.bindings) != len(_EXPECTED):
                raise DeploymentOwnershipError("bindings must have the exact expected count")
            if any(
                type(binding) is not DeploymentBinding for binding in self.bindings
            ):
                raise DeploymentOwnershipError("bindings must contain exact DeploymentBinding records")
            for binding in self.bindings:
                binding.__post_init__()
            if self.bindings != tuple(sorted(self.bindings)):
                raise DeploymentOwnershipError("bindings must be in canonical order")
            actual = {
                (binding.namespace, binding.deployment_name): binding.replicas
                for binding in self.bindings
            }
            if len(self.bindings) != len(_EXPECTED) or actual != _EXPECTED:
                raise DeploymentOwnershipError("proof does not contain the exact Deployment inventory")
            identities: list[str] = []
            for binding in self.bindings:
                identities.extend((binding.deployment_uid, binding.replica_set_uid))
                identities.extend(pod[1] for pod in binding.pods)
            if len(identities) != 37 or len(set(identities)) != len(identities):
                raise DeploymentOwnershipError("proof UIDs are incomplete or collide")
            if type(self.runtime_contract_complete) is not bool or self.runtime_contract_complete:
                raise DeploymentOwnershipError("ownership proof cannot complete the runtime contract")
        except DeploymentOwnershipError:
            raise
        except (TypeError, ValueError, UnicodeError, OverflowError, AttributeError) as error:
            raise DeploymentOwnershipError("invalid Deployment ownership proof") from error


def _application_namespaces(value: object) -> tuple[str, ...]:
    if type(value) is not tuple or len(value) != len(_APPLICATION_NAMESPACES):
        raise DeploymentOwnershipError("application_namespaces must be the exact pinned tuple")
    for namespace in value:
        _name("application namespace", namespace)
    if value != _APPLICATION_NAMESPACES:
        raise DeploymentOwnershipError("application_namespaces must be exact and sorted")
    return value

def _precheck(records: object, *, count: int, label: str) -> list[dict]:
    if type(records) is not list or len(records) != count:
        raise DeploymentOwnershipError(f"{label} must be an exact list of {count} records")
    return records


def _validate_deployment_ownership(
    deployments: object,
    replica_sets: object,
    pods: object,
    application_namespaces: object,
) -> DeploymentOwnershipProof:
    namespaces = _application_namespaces(application_namespaces)
    deployment_records = _precheck(deployments, count=12, label="deployments")
    replica_set_records = _precheck(replica_sets, count=12, label="replica_sets")
    pod_records = _precheck(pods, count=13, label="pods")

    deployment_by_key: dict[tuple[str, str], dict] = {}
    all_uids: list[str] = []
    for raw in deployment_records:
        record = _closed(raw, _DEPLOYMENT_KEYS, "Deployment")
        _constant("Deployment.apiVersion", record["apiVersion"], "apps/v1")
        _constant("Deployment.kind", record["kind"], "Deployment")
        namespace = _name("Deployment.namespace", record["namespace"])
        name = _name("Deployment.name", record["name"])
        uid = _uid("Deployment.uid", record["uid"])
        _uint64("Deployment.resourceVersion", record["resourceVersion"])
        _revision(record["revision"])
        replicas = record["replicas"]
        if type(replicas) is not int or replicas <= 0:
            raise DeploymentOwnershipError("Deployment.replicas must be an exact positive int")
        key = (namespace, name)
        if key in deployment_by_key:
            raise DeploymentOwnershipError("duplicate Deployment identity")
        deployment_by_key[key] = record
        all_uids.append(uid)
    if {key: record["replicas"] for key, record in deployment_by_key.items()} != _EXPECTED:
        raise DeploymentOwnershipError("Deployment inventory or replica counts differ")

    replica_set_by_deployment: dict[tuple[str, str, str], dict] = {}
    replica_set_identities: set[tuple[str, str]] = set()
    for raw in replica_set_records:
        record = _closed(raw, _REPLICA_SET_KEYS, "ReplicaSet")
        _constant("ReplicaSet.apiVersion", record["apiVersion"], "apps/v1")
        _constant("ReplicaSet.kind", record["kind"], "ReplicaSet")
        namespace = _name("ReplicaSet.namespace", record["namespace"])
        name = _name("ReplicaSet.name", record["name"])
        uid = _uid("ReplicaSet.uid", record["uid"])
        _uint64("ReplicaSet.resourceVersion", record["resourceVersion"])
        _revision(record["revision"])
        hash_value = _text(
            "ReplicaSet.podTemplateHash", record["podTemplateHash"],
            max_chars=10, max_bytes=10,
        )
        if _HASH.fullmatch(hash_value) is None:
            raise DeploymentOwnershipError("ReplicaSet hash is invalid")
        owner_name, owner_uid = _owner(record["ownerReference"], kind="Deployment")
        if name != f"{owner_name}-{hash_value}":
            raise DeploymentOwnershipError("ReplicaSet name is not owner-hash bound")
        identity = (namespace, name)
        owner_key = (namespace, owner_name, owner_uid)
        if identity in replica_set_identities or owner_key in replica_set_by_deployment:
            raise DeploymentOwnershipError("duplicate ReplicaSet or Deployment ownership")
        replica_set_identities.add(identity)
        replica_set_by_deployment[owner_key] = record
        all_uids.append(uid)

    pods_by_replica_set: dict[tuple[str, str, str], list[dict]] = {}
    pod_identities: set[tuple[str, str]] = set()
    for raw in pod_records:
        record = _closed(raw, _POD_KEYS, "Pod")
        _constant("Pod.apiVersion", record["apiVersion"], "v1")
        _constant("Pod.kind", record["kind"], "Pod")
        namespace = _name("Pod.namespace", record["namespace"])
        name = _name("Pod.name", record["name"])
        uid = _uid("Pod.uid", record["uid"])
        _uint64("Pod.resourceVersion", record["resourceVersion"])
        hash_value = _text(
            "Pod.podTemplateHash", record["podTemplateHash"],
            max_chars=10, max_bytes=10,
        )
        if _HASH.fullmatch(hash_value) is None:
            raise DeploymentOwnershipError("Pod hash is invalid")
        owner_name, owner_uid = _owner(record["ownerReference"], kind="ReplicaSet")
        prefix = owner_name + "-"
        if not name.startswith(prefix) or _POD_SUFFIX.fullmatch(name[len(prefix):]) is None:
            raise DeploymentOwnershipError("Pod name is not owner-suffix bound")
        identity = (namespace, name)
        if identity in pod_identities:
            raise DeploymentOwnershipError("duplicate Pod identity")
        pod_identities.add(identity)
        pods_by_replica_set.setdefault((namespace, owner_name, owner_uid), []).append(record)
        all_uids.append(uid)
    if len(set(all_uids)) != len(all_uids):
        raise DeploymentOwnershipError("UIDs must be globally unique across all families")

    bindings: list[DeploymentBinding] = []
    consumed_replica_sets: set[tuple[str, str, str]] = set()
    consumed_pods: set[tuple[str, str, str]] = set()
    for (namespace, deployment_name), deployment in deployment_by_key.items():
        deployment_owner = (namespace, deployment_name, deployment["uid"])
        replica_set = replica_set_by_deployment.get(deployment_owner)
        if replica_set is None:
            raise DeploymentOwnershipError("Deployment lacks one exact owned ReplicaSet")
        consumed_replica_sets.add(deployment_owner)
        replica_set_owner = (namespace, replica_set["name"], replica_set["uid"])
        owned_pods = pods_by_replica_set.get(replica_set_owner, [])
        if len(owned_pods) != deployment["replicas"]:
            raise DeploymentOwnershipError("ReplicaSet does not own the exact replica count")
        consumed_pods.add(replica_set_owner)
        for pod in owned_pods:
            if pod["podTemplateHash"] != replica_set["podTemplateHash"]:
                raise DeploymentOwnershipError("Pod and ReplicaSet hashes differ")
        bindings.append(DeploymentBinding(
            namespace=namespace,
            deployment_name=deployment_name,
            deployment_uid=deployment["uid"],
            deployment_resource_version=deployment["resourceVersion"],
            revision=deployment["revision"],
            replicas=deployment["replicas"],
            replica_set_name=replica_set["name"],
            replica_set_uid=replica_set["uid"],
            replica_set_resource_version=replica_set["resourceVersion"],
            pod_template_hash=replica_set["podTemplateHash"],
            pods=tuple(sorted(
                (pod["name"], pod["uid"], pod["resourceVersion"])
                for pod in owned_pods
            )),
        ))
    if consumed_replica_sets != set(replica_set_by_deployment):
        raise DeploymentOwnershipError("orphan or cross-namespace ReplicaSet")
    if consumed_pods != set(pods_by_replica_set):
        raise DeploymentOwnershipError("orphan or cross-namespace Pod")
    return DeploymentOwnershipProof(namespaces, tuple(sorted(bindings)), False)


def validate_deployment_ownership(
    *,
    deployments: list[dict],
    replica_sets: list[dict],
    pods: list[dict],
    application_namespaces: tuple[str, ...],
) -> DeploymentOwnershipProof:
    """Validate a closed fresh ownership projection without runtime completeness."""
    try:
        return _validate_deployment_ownership(
            deployments, replica_sets, pods, application_namespaces,
        )
    except DeploymentOwnershipError:
        raise
    except (TypeError, ValueError, UnicodeError, OverflowError, AttributeError) as error:
        raise DeploymentOwnershipError("invalid Deployment ownership projection") from error


__all__ = (
    "DeploymentOwnershipError",
    "DeploymentBinding",
    "DeploymentOwnershipProof",
    "validate_deployment_ownership",
)
