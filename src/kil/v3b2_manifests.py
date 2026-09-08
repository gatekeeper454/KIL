"""Pure, deterministic rendering of the closed V3B-2a Kind object set."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from .canonical import canonical_json
from .live_authz import LiveTrack
from .v3b2_contracts import TRACK_NAMESPACES, V3B2Profile
from .v3b_envoy import render_envoy_json


_RUN_ID = re.compile(r"v3b2-[0-9a-f]{64}")
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
_DIGEST_IMAGE = re.compile(r"[^@\s]+@sha256:[0-9a-f]{64}")
_MANAGED = "v3b2"
_ROLES = ("driver", "envoy", "authz", "target")
_POLICIES = (
    "default-deny",
    "allow-dns",
    "allow-driver-egress-envoy",
    "allow-envoy-ingress-egress",
    "allow-backends-ingress-envoy",
)
_RESOURCES = {
    "requests": {"cpu": "100m", "memory": "64Mi", "ephemeral-storage": "16Mi"},
    "limits": {"cpu": "500m", "memory": "256Mi", "ephemeral-storage": "64Mi"},
}
_PUBLIC_KEY = {
    "key_id": "56475aa75463474c",
    "raw_base64url": "A6EHv_POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg",
}
_FIXTURE = {
    "request_id": "v3b1-central-request",
    "method": "POST",
    "path": "/consequential/admin",
    "identity": "spiffe://kil.local/workload/demo",
    "authority_class": "admin_action",
    "action_class": "consequential_admin",
    "expected_authorization_sha256": (
        "6439999a7bf4ce84849af7b26150003ef0ee42642fe46921805929a0d68dcdb7"
    ),
    "policy_allows_action": True,
    "local_evidence": {"divergence": "0.9", "coupled_loss": "0", "fresh": True},
    "reduction_profile": {
        "divergence_threshold": "0.25",
        "loss_rate": "25",
        "exponent": 3,
    },
}


class ManifestError(ValueError):
    """Raised when a rendered V3B-2a manifest is not the exact closed object set."""


def _exact_string_tuple(name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple or any(type(item) is not str for item in value):
        raise ManifestError(f"{name} must be an exact tuple of exact strings")
    if tuple(sorted(value)) != value or len(set(value)) != len(value):
        raise ManifestError(f"{name} must be unique and lexically canonical")
    return value


@dataclass(frozen=True, slots=True)
class WorkloadIdentity:
    run_id: str
    kil_image_id: str
    envoy_image_digest: str

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or _RUN_ID.fullmatch(self.run_id) is None:
            raise ManifestError("run_id must be v3b2- followed by 64 lowercase hex")
        if (
            type(self.kil_image_id) is not str
            or _IMAGE_ID.fullmatch(self.kil_image_id) is None
        ):
            raise ManifestError("kil_image_id must be a lowercase sha256 image ID")
        if (
            type(self.envoy_image_digest) is not str
            or _DIGEST_IMAGE.fullmatch(self.envoy_image_digest) is None
        ):
            raise ManifestError("envoy_image_digest must be repository@sha256:digest")


@dataclass(frozen=True, slots=True)
class PolicyEdge:
    namespace: str
    source_roles: tuple[str, ...]
    destination_namespace: str
    destination_roles: tuple[str, ...]
    protocol_ports: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if type(self.namespace) is not str or not self.namespace:
            raise ManifestError("namespace must be an exact nonempty string")
        if type(self.destination_namespace) is not str or not self.destination_namespace:
            raise ManifestError("destination_namespace must be an exact nonempty string")
        _exact_string_tuple("source_roles", self.source_roles)
        _exact_string_tuple("destination_roles", self.destination_roles)
        if type(self.protocol_ports) is not tuple or not self.protocol_ports:
            raise ManifestError("protocol_ports must be an exact nonempty tuple")
        for pair in self.protocol_ports:
            if (
                type(pair) is not tuple
                or len(pair) != 2
                or type(pair[0]) is not str
                or type(pair[1]) is not int
                or pair[0] not in {"TCP", "UDP"}
                or not 1 <= pair[1] <= 65535
            ):
                raise ManifestError("protocol_ports entries must be exact protocol/port pairs")
        if tuple(sorted(self.protocol_ports)) != self.protocol_ports or len(set(self.protocol_ports)) != len(self.protocol_ports):
            raise ManifestError("protocol_ports must be unique and lexically canonical")


def _require_profile(profile: object) -> V3B2Profile:
    if type(profile) is not V3B2Profile:
        raise ManifestError("profile must be an exact V3B2Profile")
    try:
        profile.__post_init__()
    except (ValueError, TypeError) as error:
        raise ManifestError(f"invalid V3B2Profile: {error}") from error
    return profile


def _require_workload(workload: object) -> WorkloadIdentity:
    if type(workload) is not WorkloadIdentity:
        raise ManifestError("workload must be an exact WorkloadIdentity")
    try:
        workload.__post_init__()
    except (ValueError, TypeError) as error:
        if isinstance(error, ManifestError):
            raise
        raise ManifestError(f"invalid WorkloadIdentity: {error}") from error
    return workload


def render_kind_config(profile: V3B2Profile) -> bytes:
    fixed = _require_profile(profile)
    value = {
        "apiVersion": "kind.x-k8s.io/v1alpha4",
        "kind": "Cluster",
        "networking": {
            "disableDefaultCNI": True,
            "podSubnet": fixed.pod_subnet,
            "serviceSubnet": fixed.service_subnet,
        },
        "nodes": [{"role": "control-plane"}],
    }
    return (canonical_json(value) + "\n").encode("utf-8")


def _labels(track: str, role: str | None = None) -> dict[str, str]:
    labels = {"kil.dev/managed": _MANAGED, "kil.dev/track": track}
    if role is not None:
        labels["kil.dev/role"] = role
    return labels


def _metadata(name: str, track: str, run_id: str, *, namespace: str | None = None, role: str | None = None) -> dict[str, object]:
    metadata: dict[str, object] = {
        "name": name,
        "labels": _labels(track, role),
        "annotations": {"kil.dev/run-id": run_id},
    }
    if namespace is not None:
        metadata["namespace"] = namespace
    return metadata


def _object(api_version: str, kind: str, metadata: dict[str, object], **body: object) -> dict[str, object]:
    return {"apiVersion": api_version, "kind": kind, "metadata": metadata, **body}


def _same_namespace_peer(track: str, role: str) -> dict[str, object]:
    return {
        "namespaceSelector": {"matchLabels": _labels(track)},
        "podSelector": {"matchLabels": _labels(track, role)},
    }


def _role_selector(track: str, roles: tuple[str, ...]) -> dict[str, object]:
    return {
        "matchLabels": _labels(track),
        "matchExpressions": [
            {"key": "kil.dev/role", "operator": "In", "values": list(roles)}
        ],
    }


def _port(protocol: str, port: int) -> dict[str, object]:
    return {"port": port, "protocol": protocol}


def _network_policies(track: str, namespace: str, run_id: str) -> list[dict[str, object]]:
    meta = lambda name: _metadata(name, track, run_id, namespace=namespace)
    tcp = [_port("TCP", 8080)]
    return [
        _object(
            "networking.k8s.io/v1", "NetworkPolicy", meta("default-deny"),
            spec={"podSelector": {}, "policyTypes": ["Ingress", "Egress"]},
        ),
        _object(
            "networking.k8s.io/v1", "NetworkPolicy", meta("allow-dns"),
            spec={
                "podSelector": _role_selector(track, ("driver", "envoy")),
                "policyTypes": ["Egress"],
                "egress": [{
                    "to": [{
                        "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
                        "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                    }],
                    "ports": [_port("TCP", 53), _port("UDP", 53)],
                }],
            },
        ),
        _object(
            "networking.k8s.io/v1", "NetworkPolicy", meta("allow-driver-egress-envoy"),
            spec={
                "podSelector": {"matchLabels": _labels(track, "driver")},
                "policyTypes": ["Egress"],
                "egress": [{"to": [_same_namespace_peer(track, "envoy")], "ports": tcp}],
            },
        ),
        _object(
            "networking.k8s.io/v1", "NetworkPolicy", meta("allow-envoy-ingress-egress"),
            spec={
                "podSelector": {"matchLabels": _labels(track, "envoy")},
                "policyTypes": ["Ingress", "Egress"],
                "ingress": [{"from": [_same_namespace_peer(track, "driver")], "ports": tcp}],
                "egress": [
                    {"to": [_same_namespace_peer(track, "authz")], "ports": tcp},
                    {"to": [_same_namespace_peer(track, "target")], "ports": tcp},
                ],
            },
        ),
        _object(
            "networking.k8s.io/v1", "NetworkPolicy", meta("allow-backends-ingress-envoy"),
            spec={
                "podSelector": _role_selector(track, ("authz", "target")),
                "policyTypes": ["Ingress"],
                "ingress": [{"from": [_same_namespace_peer(track, "envoy")], "ports": tcp}],
            },
        ),
    ]


def _authz_config(track: str) -> str:
    value = {
        "schema_version": "kil.v3b-authz-http.v1",
        "track": track,
        "bind_host": "0.0.0.0",
        "bind_port": 8080,
        "records_path": "/evidence/decisions.jsonl",
        "public_keys": [] if track == "credential_policy_baseline" else [_PUBLIC_KEY],
        "revoked_state_ids": [],
        "fixtures": [_FIXTURE],
    }
    return canonical_json(value) + "\n"


def _target_config(track: str, run_id: str) -> str:
    return canonical_json({
        "schema_version": "kil.v3b-target-http.v1",
        "run_id": run_id,
        "track": track,
        "bind_host": "0.0.0.0",
        "bind_port": 8080,
        "ledger_path": "/evidence/targets.jsonl",
    }) + "\n"


def _envoy_config(track: str) -> str:
    value = json.loads(render_envoy_json(LiveTrack(track), "authz", "target"))
    value["admin"] = {
        "access_log_path": "/dev/null",
        "address": {"socket_address": {"address": "127.0.0.1", "port_value": 9901}},
    }
    return canonical_json(value) + "\n"


def _pod_spec(role: str, track: str, image: str, command: list[str], config_name: str | None) -> dict[str, object]:
    mounts: list[dict[str, object]] = [
        {"name": "evidence", "mountPath": "/evidence"},
        {"name": "tmp", "mountPath": "/tmp"},
    ]
    volumes: list[dict[str, object]] = [
        {"name": "evidence", "emptyDir": {"sizeLimit": "16Mi"}},
        {"name": "tmp", "emptyDir": {"sizeLimit": "16Mi"}},
    ]
    if config_name is not None:
        mounts.insert(0, {"name": "config", "mountPath": "/config", "readOnly": True})
        volumes.insert(0, {"name": "config", "configMap": {"name": config_name, "defaultMode": 292}})
    container: dict[str, object] = {
        "name": role,
        "image": image,
        "imagePullPolicy": "Never",
        "command": command,
        "resources": _RESOURCES,
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 65532,
            "runAsGroup": 65532,
            "capabilities": {"drop": ["ALL"]},
        },
        "volumeMounts": mounts,
    }
    if role == "driver":
        container.update({"stdin": True, "stdinOnce": True, "tty": False})
    else:
        container["ports"] = [{"containerPort": 8080, "name": "http", "protocol": "TCP"}]
        container["readinessProbe"] = {
            "tcpSocket": {"port": 8080}, "periodSeconds": 1,
            "timeoutSeconds": 1, "failureThreshold": 30, "successThreshold": 1,
        }
    return {
        "serviceAccountName": role,
        "automountServiceAccountToken": False,
        "enableServiceLinks": False,
        "restartPolicy": "Never" if role == "driver" else "Always",
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 65532,
            "runAsGroup": 65532,
            "fsGroup": 65532,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": [container],
        "volumes": volumes,
    }


def _deployment(role: str, track: str, namespace: str, run_id: str, image: str, command: list[str], config_name: str) -> dict[str, object]:
    labels = _labels(track, role)
    return _object(
        "apps/v1", "Deployment", _metadata(role, track, run_id, namespace=namespace, role=role),
        spec={
            "replicas": 1,
            "strategy": {"type": "Recreate"},
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels, "annotations": {"kil.dev/run-id": run_id}},
                "spec": _pod_spec(role, track, image, command, config_name),
            },
        },
    )


def _namespace_objects(track: str, namespace: str, workload: WorkloadIdentity) -> list[dict[str, object]]:
    run_id = workload.run_id
    kil_image = "kil.local/kil-v3b2:sha256-" + workload.kil_image_id.removeprefix("sha256:")
    objects = [_object("v1", "Namespace", _metadata(namespace, track, run_id))]
    objects.extend(
        _object("v1", "ServiceAccount", _metadata(role, track, run_id, namespace=namespace, role=role))
        for role in _ROLES
    )
    config_values = (
        ("authz-config", "authz", "authz.json", _authz_config(track)),
        ("target-config", "target", "target.json", _target_config(track, run_id)),
        ("envoy-config", "envoy", "envoy.json", _envoy_config(track)),
    )
    objects.extend(
        _object("v1", "ConfigMap", _metadata(name, track, run_id, namespace=namespace, role=role), data={filename: value})
        for name, role, filename, value in config_values
    )
    objects.extend(_network_policies(track, namespace, run_id))
    objects.extend(
        _object(
            "v1", "Service", _metadata(role, track, run_id, namespace=namespace, role=role),
            spec={
                "type": "ClusterIP",
                "selector": _labels(track, role),
                "ports": [{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": 8080}],
            },
        )
        for role in ("envoy", "authz", "target")
    )
    commands = {
        "envoy": ["envoy", "-c", "/config/envoy.json", "--log-path", "/tmp/envoy.log"],
        "authz": ["sh", "-ceu", "umask 077; set -C; : > /evidence/decisions.jsonl; exec python -m kil.ext_authz_http --config /config/authz.json"],
        "target": ["sh", "-ceu", "umask 077; set -C; : > /evidence/targets.jsonl; exec python -m kil.target_http --config /config/target.json"],
    }
    for role in ("envoy", "authz", "target"):
        objects.append(_deployment(
            role, track, namespace, run_id,
            workload.envoy_image_digest if role == "envoy" else kil_image,
            commands[role], f"{role}-config",
        ))
    driver_command = [
        "python", "-m", "kil.v3b1_request_driver", "--track", track,
        "--endpoint", "envoy:8080",
    ]
    objects.append(_object(
        "v1", "Pod", _metadata("driver", track, run_id, namespace=namespace, role="driver"),
        spec=_pod_spec("driver", track, kil_image, driver_command, None),
    ))
    return objects


def render_objects(profile: V3B2Profile, workload: WorkloadIdentity) -> bytes:
    _require_profile(profile)
    fixed_workload = _require_workload(workload)
    items: list[dict[str, object]] = []
    for track, namespace in TRACK_NAMESPACES:
        items.extend(_namespace_objects(track, namespace, fixed_workload))
    return (canonical_json({"apiVersion": "v1", "kind": "List", "items": items}) + "\n").encode("utf-8")


def expected_object_keys(profile: V3B2Profile) -> tuple[tuple[str, str, str, str], ...]:
    _require_profile(profile)
    keys: list[tuple[str, str, str, str]] = []
    for _, namespace in TRACK_NAMESPACES:
        keys.append(("v1", "Namespace", "", namespace))
        keys.extend(("v1", "ServiceAccount", namespace, role) for role in _ROLES)
        keys.extend(("v1", "ConfigMap", namespace, name) for name in ("authz-config", "target-config", "envoy-config"))
        keys.extend(("networking.k8s.io/v1", "NetworkPolicy", namespace, name) for name in _POLICIES)
        keys.extend(("v1", "Service", namespace, role) for role in ("envoy", "authz", "target"))
        keys.extend(("apps/v1", "Deployment", namespace, role) for role in ("envoy", "authz", "target"))
        keys.append(("v1", "Pod", namespace, "driver"))
    return tuple(keys)


def expected_policy_graph(profile: V3B2Profile) -> tuple[PolicyEdge, ...]:
    _require_profile(profile)
    edges: list[PolicyEdge] = []
    for _, namespace in TRACK_NAMESPACES:
        edges.extend((
            PolicyEdge(namespace, ("driver",), namespace, ("envoy",), (("TCP", 8080),)),
            PolicyEdge(namespace, ("envoy",), namespace, ("authz",), (("TCP", 8080),)),
            PolicyEdge(namespace, ("envoy",), namespace, ("target",), (("TCP", 8080),)),
            PolicyEdge(namespace, ("driver", "envoy"), "kube-system", ("kube-dns",), (("TCP", 53), ("UDP", 53))),
        ))
    return tuple(edges)


def _require_plain_json(value: object) -> None:
    if value is None or type(value) in {str, int, bool}:
        return
    if type(value) is list:
        for item in value:
            _require_plain_json(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ManifestError("decoded payload keys must be exact strings")
            _require_plain_json(item)
        return
    raise ManifestError("decoded payload must contain only exact JSON value types")


def _path_text(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "payload"


def _selector_context(path: tuple[str, ...]) -> str:
    return "selector mismatch: " if any("Selector" in part for part in path) else ""


def _first_mismatch(
    expected: object,
    actual: object,
    path: tuple[str, ...] = (),
) -> str | None:
    if type(expected) is not type(actual):
        return f"{_selector_context(path)}wrong JSON type at {_path_text(path)}"
    if type(expected) is dict:
        expected_mapping = expected
        actual_mapping = actual
        missing = sorted(set(expected_mapping) - set(actual_mapping))
        if missing:
            return (
                f"{_selector_context(path)}missing field {missing[0]} "
                f"at {_path_text(path)}"
            )
        extra = sorted(set(actual_mapping) - set(expected_mapping))
        if extra:
            return (
                f"{_selector_context(path)}unexpected field {extra[0]} "
                f"at {_path_text(path)}"
            )
        for key in sorted(expected_mapping):
            mismatch = _first_mismatch(
                expected_mapping[key],
                actual_mapping[key],
                (*path, key),
            )
            if mismatch is not None:
                return mismatch
        return None
    if type(expected) is list:
        expected_items = expected
        actual_items = actual
        if len(expected_items) != len(actual_items):
            return f"wrong list length at {_path_text(path)}"
        for index, (expected_item, actual_item) in enumerate(
            zip(expected_items, actual_items, strict=True)
        ):
            mismatch = _first_mismatch(
                expected_item,
                actual_item,
                (*path, str(index)),
            )
            if mismatch is not None:
                return mismatch
        return None
    if expected != actual:
        return (
            f"{_selector_context(path)}expected {expected!r} "
            f"at {_path_text(path)}"
        )
    return None


def validate_rendered_objects(payload: bytes | dict[str, object], profile: V3B2Profile, workload: WorkloadIdentity) -> None:
    """Reject anything other than the exact canonical object structure for the inputs."""
    expected = render_objects(profile, workload)
    expected_value = json.loads(expected)
    if type(payload) is bytes:
        if payload != expected:
            raise ManifestError("payload is not the exact canonical rendered object set")
        return
    if type(payload) is not dict:
        raise ManifestError("payload must be canonical bytes or an exact decoded dictionary")
    _require_plain_json(payload)
    if canonical_json(payload) != canonical_json(expected_value):
        detail = _first_mismatch(expected_value, payload)
        raise ManifestError(
            detail or "decoded payload is not the exact rendered object structure"
        )


__all__ = (
    "ManifestError",
    "PolicyEdge",
    "WorkloadIdentity",
    "expected_object_keys",
    "expected_policy_graph",
    "render_kind_config",
    "render_objects",
    "validate_rendered_objects",
)
