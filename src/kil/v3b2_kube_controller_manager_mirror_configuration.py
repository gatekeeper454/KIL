"""Authenticated controller-manager disk and owned mirror configuration proof.

The fixed IPv4 producer is Kind v0.32.0 / kubeadm v1.36.1. Only the five
conditional host-CA pairs are selected from authenticated disk evidence; all
other expectations and disk-to-API decisions are local verifier-owned literals.
Status, readiness, image realization, freshness and completion are not proved.

Pinned sources:
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/controlplane/manifests.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/controlplane/volumes.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/util/staticpod/utils.go
https://github.com/kubernetes-sigs/kind/blob/v0.32.0/pkg/cluster/internal/kubeadm/config.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/config/common.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/pod/mirror_client.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/apis/core/v1/defaults.go
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import json
import re

from kil.v3b2_api_defaults import _equal, _managed_fields, _timestamp, matches_configuration
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_control_plane_manifest_source import (
    ControlPlaneManifestSourceProof, _retained_authority, control_plane_manifest_pod,
)
from kil.v3b2_driver_pod_configuration import _rv, _uid
from kil.v3b2_proofs import decode
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof


__all__ = (
    "KubeControllerManagerMirrorConfigurationBinding",
    "KubeControllerManagerMirrorConfigurationError",
    "KubeControllerManagerMirrorConfigurationProof",
    "kube_controller_manager_mirror_api_spec",
    "validate_kube_controller_manager_mirror_configuration",
)

_COMPONENT = "kube-controller-manager"
_NODE = "kil-v3-lab-control-plane"
_NAME = _COMPONENT + "-" + _NODE
_NAMESPACE = "kube-system"
_METADATA = {"name", "namespace", "uid", "resourceVersion", "generation",
             "creationTimestamp", "labels", "annotations", "ownerReferences"}
_CA_CANDIDATES = (
    ("etc-ca-certificates", "/etc/ca-certificates"),
    ("etc-pki-ca-trust", "/etc/pki/ca-trust"),
    ("etc-pki-tls-certs", "/etc/pki/tls/certs"),
    ("usr-local-share-ca-certificates", "/usr/local/share/ca-certificates"),
    ("usr-share-ca-certificates", "/usr/share/ca-certificates"),
)


class KubeControllerManagerMirrorConfigurationError(ValueError):
    """Retained controller-manager evidence differs from the reviewed profile."""


def _seen_timestamp(value):
    if type(value) is not str or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{9}(?:Z|[+-][0-9]{2}:[0-9]{2})",
            value) is None:
        raise KubeControllerManagerMirrorConfigurationError("invalid controller-manager config.seen")
    if value[-1] != "Z" and (value[-6:] in {"+00:00", "-00:00"}
            or int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise KubeControllerManagerMirrorConfigurationError("invalid controller-manager config.seen zone")
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def _command():
    return [
        "kube-controller-manager",
        "--allocate-node-cidrs=true",
        "--authentication-kubeconfig=/etc/kubernetes/controller-manager.conf",
        "--authorization-kubeconfig=/etc/kubernetes/controller-manager.conf",
        "--bind-address=127.0.0.1",
        "--client-ca-file=/etc/kubernetes/pki/ca.crt",
        "--cluster-cidr=10.244.0.0/16",
        "--cluster-name=kil-v3-lab",
        "--cluster-signing-cert-file=/etc/kubernetes/pki/ca.crt",
        "--cluster-signing-key-file=/etc/kubernetes/pki/ca.key",
        "--controllers=*,bootstrapsigner,tokencleaner",
        "--enable-hostpath-provisioner=true",
        "--kubeconfig=/etc/kubernetes/controller-manager.conf",
        "--leader-elect=true",
        "--requestheader-client-ca-file=/etc/kubernetes/pki/front-proxy-ca.crt",
        "--root-ca-file=/etc/kubernetes/pki/ca.crt",
        "--service-account-private-key-file=/etc/kubernetes/pki/sa.key",
        "--service-cluster-ip-range=10.96.0.0/16",
        "--use-service-account-credentials=true",
    ]


def _expected_disk_pod(selected):
    pairs = tuple(sorted((("ca-certs", "/etc/ssl/certs"), *selected,
                          ("k8s-certs", "/etc/kubernetes/pki"),
                          ("kubeconfig", "/etc/kubernetes/controller-manager.conf"))))
    return {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"labels": {"component": _COMPONENT, "tier": "control-plane"},
                     "name": _COMPONENT, "namespace": _NAMESPACE},
        "spec": {
            "hostNetwork": True, "priority": 2000001000,
            "priorityClassName": "system-node-critical",
            "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
            "volumes": [{"hostPath": {"path": path,
                "type": "FileOrCreate" if name == "kubeconfig" else "DirectoryOrCreate"},
                "name": name} for name, path in pairs],
            "containers": [{
                "name": _COMPONENT,
                "image": "registry.k8s.io/kube-controller-manager:v1.36.1",
                "imagePullPolicy": "IfNotPresent", "command": _command(),
                "resources": {"requests": {"cpu": "200m"}},
                "ports": [{"name": "probe-port", "containerPort": 10257, "protocol": "TCP"}],
                "volumeMounts": [{"mountPath": path, "name": name, "readOnly": True}
                                 for name, path in pairs],
                "livenessProbe": {"failureThreshold": 8,
                    "httpGet": {"host": "127.0.0.1", "path": "/healthz",
                                "port": "probe-port", "scheme": "HTTPS"},
                    "initialDelaySeconds": 10, "periodSeconds": 10, "timeoutSeconds": 15},
                "startupProbe": {"failureThreshold": 24,
                    "httpGet": {"host": "127.0.0.1", "path": "/healthz",
                                "port": "probe-port", "scheme": "HTTPS"},
                    "initialDelaySeconds": 10, "periodSeconds": 10, "timeoutSeconds": 15},
            }],
        },
    }


def _conditional_subset(pod):
    volumes = pod["spec"]["volumes"]
    mounts = pod["spec"]["containers"][0]["volumeMounts"]
    if type(volumes) is not list or type(mounts) is not list:
        raise KubeControllerManagerMirrorConfigurationError("controller-manager pairs must be lists")
    if (any(type(row) is not dict or type(row.get("name")) is not str
            for row in (*volumes, *mounts))
            or len({row["name"] for row in volumes}) != len(volumes)
            or len({row["name"] for row in mounts}) != len(mounts)):
        raise KubeControllerManagerMirrorConfigurationError("controller-manager pairs malformed or duplicated")
    volume_names = {row["name"] for row in volumes}
    mount_names = {row["name"] for row in mounts}
    selected = []
    for name, path in _CA_CANDIDATES:
        if (name in volume_names) != (name in mount_names):
            raise KubeControllerManagerMirrorConfigurationError("controller-manager CA pair incomplete")
        if name in volume_names:
            volume = next(row for row in volumes if row["name"] == name)
            mount = next(row for row in mounts if row["name"] == name)
            if (not _equal(volume, {"hostPath": {"path": path, "type": "DirectoryOrCreate"}, "name": name})
                    or not _equal(mount, {"mountPath": path, "name": name, "readOnly": True})):
                raise KubeControllerManagerMirrorConfigurationError("controller-manager CA pair differs")
            selected.append((name, path))
    return tuple(selected)


def _authenticated_subset(source):
    if type(source) is not ControlPlaneManifestSourceProof:
        raise KubeControllerManagerMirrorConfigurationError("controller-manager source dependency must be exact")
    source.__post_init__()
    pod = control_plane_manifest_pod(source=source, component=_COMPONENT)
    selected = _conditional_subset(pod)
    if not _equal(pod, _expected_disk_pod(selected)):
        raise KubeControllerManagerMirrorConfigurationError("controller-manager fixed disk configuration differs")
    return selected


def _expected_api_spec(selected):
    # The only disk-derived decision is selected. Never copy candidate fields.
    spec = deepcopy(_expected_disk_pod(selected)["spec"])
    spec["nodeName"] = _NODE
    spec["preemptionPolicy"] = "PreemptLowerPriority"
    spec["tolerations"] = [{"operator": "Exists", "effect": "NoExecute"}]
    spec["containers"][0]["ports"][0]["hostPort"] = 10257
    return spec


def kube_controller_manager_mirror_api_spec(*, source: ControlPlaneManifestSourceProof) -> dict:
    """Return fresh reviewed API spec after reconstructing the disk source."""
    try:
        return _expected_api_spec(_authenticated_subset(source))
    except KubeControllerManagerMirrorConfigurationError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        raise KubeControllerManagerMirrorConfigurationError("invalid controller-manager disk source") from error


@dataclass(frozen=True, slots=True)
class KubeControllerManagerMirrorConfigurationBinding:
    namespace: str
    pod_name: str
    pod_uid: str
    pod_resource_version: str
    config_hash: str
    conditional_volume_names: tuple[str, ...]
    component: str = _COMPONENT

    def __post_init__(self):
        try:
            if (type(self.component) is not str or self.component != _COMPONENT
                    or type(self.namespace) is not str or self.namespace != _NAMESPACE
                    or type(self.pod_name) is not str or self.pod_name != _NAME
                    or type(self.config_hash) is not str
                    or re.fullmatch(r"[0-9a-f]{32}", self.config_hash) is None
                    or type(self.conditional_volume_names) is not tuple
                    or any(type(name) is not str for name in self.conditional_volume_names)
                    or self.conditional_volume_names not in tuple(
                        tuple(name for bit, (name, _path) in enumerate(_CA_CANDIDATES)
                              if mask & (1 << bit)) for mask in range(32))):
                raise KubeControllerManagerMirrorConfigurationError("invalid controller-manager configuration binding")
            _uid(self.pod_uid)
            _rv(self.pod_resource_version)
        except KubeControllerManagerMirrorConfigurationError:
            raise
        except (ValueError, TypeError) as error:
            raise KubeControllerManagerMirrorConfigurationError("invalid controller-manager binding identity") from error


def _compute(*, ownership, source):
    if type(ownership) is not RuntimeOwnershipProof:
        raise KubeControllerManagerMirrorConfigurationError("controller-manager ownership dependency must be exact")
    ownership.__post_init__()
    selected = _authenticated_subset(source)
    if source.cluster_uid != ownership.owned_identity.cluster_incarnation_uid:
        raise KubeControllerManagerMirrorConfigurationError("controller-manager source cluster incarnation differs")
    if source.node_container_id != ownership.owned_identity.node_container_id:
        raise KubeControllerManagerMirrorConfigurationError("controller-manager source node container differs")
    if source.run_id != ownership.workload.run_id.removeprefix("v3b2-"):
        raise KubeControllerManagerMirrorConfigurationError("controller-manager source run differs")
    # Dependencies are reconstructed above; recover complete retained authority,
    # including isolated endpoint and private kubeconfig/Docker-config scope.
    source_context, source_identity = _retained_authority(source.raw_observations)
    if source_identity != ownership.owned_identity:
        raise KubeControllerManagerMirrorConfigurationError("controller-manager complete source owned authority differs")
    # Join requested producer authority, without asserting image realization.
    inputs = decode(source_context.inputs)
    if inputs["kind_node_image"] != ownership.profile.kind_node_image:
        raise KubeControllerManagerMirrorConfigurationError("controller-manager source requested Kind image differs from ownership profile")
    if ("profile" in inputs
            and V3B2Profile.from_mapping(inputs["profile"]) != ownership.profile):
        raise KubeControllerManagerMirrorConfigurationError("controller-manager source profile differs from ownership profile")
    relations = [row for row in ownership.node_ownership.static_pods if row.component == _COMPONENT]
    if len(relations) != 1:
        raise KubeControllerManagerMirrorConfigurationError("expected sole controller-manager ownership binding")
    relation = relations[0]
    rows = json.loads(ownership.runtime_objects)["items"]
    pods = [row for row in rows if row.get("apiVersion") == "v1" and row.get("kind") == "Pod"
            and type(row.get("metadata")) is dict
            and row["metadata"].get("namespace") == _NAMESPACE and row["metadata"].get("name") == _NAME]
    if len(pods) != 1:
        raise KubeControllerManagerMirrorConfigurationError("expected sole owned controller-manager Pod")
    pod = pods[0]
    if (not {"apiVersion", "kind", "metadata", "spec"} <= pod.keys()
            or pod.keys() - {"apiVersion", "kind", "metadata", "spec", "status"}):
        raise KubeControllerManagerMirrorConfigurationError("unreviewed controller-manager Pod root")
    metadata = pod["metadata"]
    if (not _METADATA <= metadata.keys() or metadata.keys() - (_METADATA | {"managedFields"})):
        raise KubeControllerManagerMirrorConfigurationError("unreviewed complete controller-manager metadata")
    _uid(metadata["uid"])
    _rv(metadata["resourceVersion"])
    _timestamp(metadata["creationTimestamp"])
    if "managedFields" in metadata:
        _managed_fields(metadata["managedFields"])
    if (type(metadata["generation"]) is not int or metadata["generation"] != 1
            or not _equal([metadata["namespace"], metadata["name"], metadata["uid"], metadata["resourceVersion"]],
                          [_NAMESPACE, relation.pod_name, relation.pod_uid, relation.pod_resource_version])):
        raise KubeControllerManagerMirrorConfigurationError("controller-manager incarnation metadata differs")
    annotations = metadata["annotations"]
    if type(annotations) is not dict:
        raise KubeControllerManagerMirrorConfigurationError("invalid controller-manager annotations")
    seen = annotations["kubernetes.io/config.seen"]
    _seen_timestamp(seen)
    desired_meta = {
        "name": _NAME, "namespace": _NAMESPACE,
        "labels": {"component": _COMPONENT, "tier": "control-plane"},
        "ownerReferences": [{"apiVersion": "v1", "kind": "Node", "name": ownership.node_ownership.node_name,
                             "uid": ownership.node_ownership.node_uid, "controller": True}],
        "annotations": {"kubernetes.io/config.source": "file", "kubernetes.io/config.hash": relation.config_hash,
                        "kubernetes.io/config.mirror": relation.mirror_hash, "kubernetes.io/config.seen": seen},
    }
    if not all(_equal(metadata[key], desired_meta[key]) for key in ("labels", "annotations", "ownerReferences")):
        raise KubeControllerManagerMirrorConfigurationError("controller-manager mirror metadata differs")
    desired = {"apiVersion": "v1", "kind": "Pod", "metadata": desired_meta, "spec": _expected_api_spec(selected)}
    if type(pod["spec"]) is not dict or not matches_configuration(desired, pod):
        raise KubeControllerManagerMirrorConfigurationError("controller-manager independent API configuration differs")
    return KubeControllerManagerMirrorConfigurationBinding(
        _NAMESPACE, relation.pod_name, relation.pod_uid, relation.pod_resource_version,
        relation.config_hash, tuple(name for name, _path in selected))


@dataclass(frozen=True, slots=True)
class KubeControllerManagerMirrorConfigurationProof:
    ownership: RuntimeOwnershipProof
    source: ControlPlaneManifestSourceProof
    bindings: tuple[KubeControllerManagerMirrorConfigurationBinding, ...]
    runtime_complete: bool = False
    application_complete: bool = False
    # Preserve established proof vocabulary without expanding either claim.
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in (
                    self.runtime_complete, self.application_complete,
                    self.runtime_contract_complete, self.full_application_contract_complete)):
                raise KubeControllerManagerMirrorConfigurationError("controller-manager configuration cannot establish completion")
            if (type(self.bindings) is not tuple or len(self.bindings) != 1
                    or type(self.bindings[0]) is not KubeControllerManagerMirrorConfigurationBinding):
                raise KubeControllerManagerMirrorConfigurationError("expected one exact controller-manager binding")
            self.bindings[0].__post_init__()
            if self.bindings != (_compute(ownership=self.ownership, source=self.source),):
                raise KubeControllerManagerMirrorConfigurationError("controller-manager binding differs from reconstruction")
        except KubeControllerManagerMirrorConfigurationError:
            raise
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
            raise KubeControllerManagerMirrorConfigurationError("invalid controller-manager configuration proof") from error


def validate_kube_controller_manager_mirror_configuration(
        *, ownership: RuntimeOwnershipProof, source: ControlPlaneManifestSourceProof,
        ) -> KubeControllerManagerMirrorConfigurationProof:
    """Compare authenticated fixed disk configuration with its owned API mirror."""
    try:
        return KubeControllerManagerMirrorConfigurationProof(
            ownership=ownership, source=source, bindings=(_compute(ownership=ownership, source=source),))
    except KubeControllerManagerMirrorConfigurationError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        raise KubeControllerManagerMirrorConfigurationError("invalid controller-manager configuration source") from error
