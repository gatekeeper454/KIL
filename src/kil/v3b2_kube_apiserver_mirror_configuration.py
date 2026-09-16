"""Authenticated kube-apiserver disk manifest and mirror configuration proof.

The disk expectation is the reviewed Kind v0.32.0 / kubeadm v1.36.1 IPv4
profile.  Only the five kubeadm host-CA mounts are conditional, and their
selection comes from the authenticated disk manifest.  The API expectation is
then independently transformed with the reviewed kubelet and API defaults and
joined to the sole retained owned mirror Pod and owned Node InternalIP.

This proof does not establish readiness, effective image realization, runtime
completion, application completion, or freshness of ``config.seen``.

Pinned Kubernetes sources:
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/controlplane/manifests.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/controlplane/volumes.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/util/staticpod/utils.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/config/common.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/pod/mirror_client.go
https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/apis/core/v1/defaults.go
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import ipaddress
import json
import re

from kil.v3b2_api_defaults import _equal, _managed_fields, _timestamp, matches_configuration
from kil.v3b2_control_plane_manifest_source import (
    ControlPlaneManifestSourceProof,
    control_plane_manifest_pod,
)
from kil.v3b2_driver_pod_configuration import _rv, _uid
from kil.v3b2_runtime_ownership import RuntimeOwnershipProof


__all__ = (
    "KubeAPIServerMirrorConfigurationBinding",
    "KubeAPIServerMirrorConfigurationError",
    "KubeAPIServerMirrorConfigurationProof",
    "kube_apiserver_mirror_api_spec",
    "validate_kube_apiserver_mirror_configuration",
)

_NODE = "kil-v3-lab-control-plane"
_NAME = "kube-apiserver-" + _NODE
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


class KubeAPIServerMirrorConfigurationError(ValueError):
    """Retained disk or API evidence differs from the reviewed profile."""


def _ipv4(value):
    if type(value) is not str:
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver Node InternalIP must be an exact IPv4 string")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver Node InternalIP is invalid") from error
    if (type(address) is not ipaddress.IPv4Address or str(address) != value
            or address.is_loopback or address.is_multicast or address.is_unspecified
            or address.is_link_local or address.is_reserved):
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver Node InternalIP is outside the reviewed IPv4 boundary")
    return value


def _seen_timestamp(value):
    if type(value) is not str or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{9}(?:Z|[+-][0-9]{2}:[0-9]{2})",
            value) is None:
        raise KubeAPIServerMirrorConfigurationError(
            "invalid kube-apiserver config.seen timestamp")
    if value[-1] != "Z" and (value[-6:] in {"+00:00", "-00:00"}
            or int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise KubeAPIServerMirrorConfigurationError(
            "invalid kube-apiserver config.seen zone")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise KubeAPIServerMirrorConfigurationError(
            "invalid kube-apiserver config.seen calendar time") from error


def _command(ip):
    return [
        "kube-apiserver",
        f"--advertise-address={ip}",
        "--allow-privileged=true",
        "--authorization-mode=Node,RBAC",
        "--client-ca-file=/etc/kubernetes/pki/ca.crt",
        "--enable-admission-plugins=NodeRestriction",
        "--enable-bootstrap-token-auth=true",
        "--etcd-cafile=/etc/kubernetes/pki/etcd/ca.crt",
        "--etcd-certfile=/etc/kubernetes/pki/apiserver-etcd-client.crt",
        "--etcd-keyfile=/etc/kubernetes/pki/apiserver-etcd-client.key",
        "--etcd-servers=https://127.0.0.1:2379",
        "--kubelet-client-certificate=/etc/kubernetes/pki/apiserver-kubelet-client.crt",
        "--kubelet-client-key=/etc/kubernetes/pki/apiserver-kubelet-client.key",
        "--kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname",
        "--proxy-client-cert-file=/etc/kubernetes/pki/front-proxy-client.crt",
        "--proxy-client-key-file=/etc/kubernetes/pki/front-proxy-client.key",
        "--requestheader-allowed-names=front-proxy-client",
        "--requestheader-client-ca-file=/etc/kubernetes/pki/front-proxy-ca.crt",
        "--requestheader-extra-headers-prefix=X-Remote-Extra-",
        "--requestheader-group-headers=X-Remote-Group",
        "--requestheader-username-headers=X-Remote-User",
        "--secure-port=6443",
        "--service-account-issuer=https://kubernetes.default.svc.cluster.local",
        "--service-account-key-file=/etc/kubernetes/pki/sa.pub",
        "--service-account-signing-key-file=/etc/kubernetes/pki/sa.key",
        "--service-cluster-ip-range=10.96.0.0/16",
        "--tls-cert-file=/etc/kubernetes/pki/apiserver.crt",
        "--tls-private-key-file=/etc/kubernetes/pki/apiserver.key",
    ]


def _pairs(selected):
    return tuple(sorted((
        ("ca-certs", "/etc/ssl/certs"),
        *selected,
        ("k8s-certs", "/etc/kubernetes/pki"),
    )))


def _mounts(selected):
    return [{"mountPath": path, "name": name, "readOnly": True}
            for name, path in _pairs(selected)]


def _volumes(selected):
    return [{"hostPath": {"path": path, "type": "DirectoryOrCreate"},
             "name": name} for name, path in _pairs(selected)]


def _probes(ip):
    return {
        "livenessProbe": {"failureThreshold": 8,
            "httpGet": {"host": ip, "path": "/livez", "port": "probe-port",
                        "scheme": "HTTPS"},
            "initialDelaySeconds": 10, "periodSeconds": 10, "timeoutSeconds": 15},
        "readinessProbe": {"failureThreshold": 3,
            "httpGet": {"host": ip, "path": "/readyz", "port": "probe-port",
                        "scheme": "HTTPS"},
            "periodSeconds": 1, "timeoutSeconds": 15},
        "startupProbe": {"failureThreshold": 24,
            "httpGet": {"host": ip, "path": "/livez", "port": "probe-port",
                        "scheme": "HTTPS"},
            "initialDelaySeconds": 10, "periodSeconds": 10, "timeoutSeconds": 15},
    }


def _disk_container(selected, ip):
    return {
        "command": _command(ip),
        "image": "registry.k8s.io/kube-apiserver:v1.36.1",
        "imagePullPolicy": "IfNotPresent",
        **_probes(ip),
        "name": "kube-apiserver",
        "ports": [{"containerPort": 6443, "name": "probe-port", "protocol": "TCP"}],
        "resources": {"requests": {"cpu": "250m"}},
        "volumeMounts": _mounts(selected),
    }


def _expected_disk_pod(selected, ip):
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "annotations": {
                "kubeadm.kubernetes.io/kube-apiserver.advertise-address.endpoint":
                    f"{ip}:6443",
            },
            "labels": {"component": "kube-apiserver", "tier": "control-plane"},
            "name": "kube-apiserver",
            "namespace": _NAMESPACE,
        },
        "spec": {
            "containers": [_disk_container(selected, ip)],
            "hostNetwork": True,
            "priority": 2000001000,
            "priorityClassName": "system-node-critical",
            "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
            "volumes": _volumes(selected),
        },
    }


def _conditional_subset(pod):
    try:
        volumes = pod["spec"]["volumes"]
        mounts = pod["spec"]["containers"][0]["volumeMounts"]
    except (KeyError, TypeError, IndexError) as error:
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver disk volume structure is absent") from error
    if type(volumes) is not list or type(mounts) is not list:
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver disk volumes and mounts must be lists")
    if (any(type(row) is not dict or type(row.get("name")) is not str
            for row in (*volumes, *mounts))
            or len({row["name"] for row in volumes}) != len(volumes)
            or len({row["name"] for row in mounts}) != len(mounts)):
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver disk volumes or mounts are duplicated or malformed")
    volume_names = {row["name"] for row in volumes}
    mount_names = {row["name"] for row in mounts}
    selected = []
    for name, path in _CA_CANDIDATES:
        in_volume = name in volume_names
        in_mount = name in mount_names
        if in_volume != in_mount:
            raise KubeAPIServerMirrorConfigurationError(
                "kube-apiserver conditional CA pair is incomplete")
        if in_volume:
            volume = next(row for row in volumes if row["name"] == name)
            mount = next(row for row in mounts if row["name"] == name)
            if (not _equal(volume, {"hostPath": {"path": path,
                                                  "type": "DirectoryOrCreate"},
                                    "name": name})
                    or not _equal(mount, {"mountPath": path, "name": name,
                                          "readOnly": True})):
                raise KubeAPIServerMirrorConfigurationError(
                    "kube-apiserver conditional CA pair differs")
            selected.append((name, path))
    return tuple(selected)


def _authenticated_disk(source, ip):
    if type(source) is not ControlPlaneManifestSourceProof:
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver source dependency must be exact")
    source.__post_init__()
    pod = control_plane_manifest_pod(source=source, component="kube-apiserver")
    selected = _conditional_subset(pod)
    if not _equal(pod, _expected_disk_pod(selected, ip)):
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver disk manifest differs from reviewed configuration")
    return pod, selected


def _expected_api_pod(*, disk_pod, node_internal_ip):
    ip = _ipv4(node_internal_ip)
    selected = _conditional_subset(disk_pod)
    if not _equal(disk_pod, _expected_disk_pod(selected, ip)):
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver disk/API address or configuration differs")
    spec = deepcopy(_expected_disk_pod(selected, ip)["spec"])
    spec["nodeName"] = _NODE
    spec["preemptionPolicy"] = "PreemptLowerPriority"
    spec["tolerations"] = [{"operator": "Exists", "effect": "NoExecute"}]
    spec["containers"][0]["ports"][0]["hostPort"] = 6443
    return spec


def kube_apiserver_mirror_api_spec(*, source: ControlPlaneManifestSourceProof,
                                    node_internal_ip: str) -> dict:
    """Return a fresh API spec derived from an authenticated reviewed disk Pod."""
    try:
        ip = _ipv4(node_internal_ip)
        disk_pod, _selected = _authenticated_disk(source, ip)
        return _expected_api_pod(disk_pod=disk_pod, node_internal_ip=ip)
    except KubeAPIServerMirrorConfigurationError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError,
            RecursionError) as error:
        raise KubeAPIServerMirrorConfigurationError(
            "invalid kube-apiserver disk source") from error


def _node_ip(rows, ownership):
    matches = [row for row in rows
        if row.get("apiVersion") == "v1" and row.get("kind") == "Node"
        and type(row.get("metadata")) is dict
        and row["metadata"].get("name") == ownership.node_ownership.node_name
        and row["metadata"].get("uid") == ownership.node_ownership.node_uid
        and row["metadata"].get("resourceVersion") ==
            ownership.node_ownership.node_resource_version]
    if len(matches) != 1:
        raise KubeAPIServerMirrorConfigurationError(
            "expected sole same-source owned Node for kube-apiserver")
    status = matches[0].get("status")
    if type(status) is not dict:
        raise KubeAPIServerMirrorConfigurationError(
            "owned Node status for kube-apiserver is absent or invalid")
    addresses = status.get("addresses")
    if (type(addresses) is not list or len(addresses) != 2
            or not _equal(addresses[0], {
                "type": "InternalIP",
                "address": addresses[0].get("address")
            } if type(addresses[0]) is dict else {})
            or not _equal(addresses[1], {"type": "Hostname", "address": _NODE})):
        raise KubeAPIServerMirrorConfigurationError(
            "owned Node addresses differ from kube-apiserver reviewed shape")
    return _ipv4(addresses[0]["address"])


@dataclass(frozen=True, slots=True)
class KubeAPIServerMirrorConfigurationBinding:
    namespace: str
    pod_name: str
    pod_uid: str
    pod_resource_version: str
    config_hash: str
    node_internal_ip: str
    conditional_volume_names: tuple[str, ...]

    def __post_init__(self):
        try:
            if (type(self.namespace) is not str or self.namespace != _NAMESPACE
                    or type(self.pod_name) is not str or self.pod_name != _NAME
                    or type(self.config_hash) is not str
                    or re.fullmatch(r"[0-9a-f]{32}", self.config_hash) is None
                    or type(self.conditional_volume_names) is not tuple
                    or any(type(name) is not str for name in self.conditional_volume_names)
                    or self.conditional_volume_names not in tuple(
                        tuple(name for bit, (name, _path) in enumerate(_CA_CANDIDATES)
                              if mask & (1 << bit)) for mask in range(32))):
                raise KubeAPIServerMirrorConfigurationError(
                    "invalid kube-apiserver configuration binding")
            _uid(self.pod_uid)
            _rv(self.pod_resource_version)
            _ipv4(self.node_internal_ip)
        except KubeAPIServerMirrorConfigurationError:
            raise
        except (ValueError, TypeError) as error:
            raise KubeAPIServerMirrorConfigurationError(
                "invalid kube-apiserver binding identity") from error


def _compute(*, ownership, source):
    if type(ownership) is not RuntimeOwnershipProof:
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver ownership dependency must be exact")
    ownership.__post_init__()
    if type(source) is not ControlPlaneManifestSourceProof:
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver source dependency must be exact")
    source.__post_init__()
    if source.cluster_uid != ownership.owned_identity.cluster_incarnation_uid:
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver source cluster incarnation differs from ownership")
    if source.node_container_id != ownership.owned_identity.node_container_id:
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver source node container differs from ownership")
    relations = [row for row in ownership.node_ownership.static_pods
                 if row.component == "kube-apiserver"]
    if len(relations) != 1:
        raise KubeAPIServerMirrorConfigurationError(
            "expected sole kube-apiserver ownership binding")
    relation = relations[0]
    rows = json.loads(ownership.runtime_objects)["items"]
    ip = _node_ip(rows, ownership)
    disk_pod, selected = _authenticated_disk(source, ip)
    pods = [row for row in rows
            if row.get("apiVersion") == "v1" and row.get("kind") == "Pod"
            and type(row.get("metadata")) is dict
            and row["metadata"].get("namespace") == _NAMESPACE
            and row["metadata"].get("name") == _NAME]
    if len(pods) != 1:
        raise KubeAPIServerMirrorConfigurationError(
            "expected sole owned kube-apiserver Pod")
    pod = pods[0]
    if (not {"apiVersion", "kind", "metadata", "spec"} <= pod.keys()
            or pod.keys() - {"apiVersion", "kind", "metadata", "spec", "status"}):
        raise KubeAPIServerMirrorConfigurationError(
            "unreviewed kube-apiserver Pod root")
    metadata = pod["metadata"]
    if (type(metadata) is not dict or not _METADATA <= metadata.keys()
            or metadata.keys() - (_METADATA | {"managedFields"})):
        raise KubeAPIServerMirrorConfigurationError(
            "unreviewed complete kube-apiserver Pod metadata")
    _uid(metadata["uid"])
    _rv(metadata["resourceVersion"])
    _timestamp(metadata["creationTimestamp"])
    if "managedFields" in metadata:
        _managed_fields(metadata["managedFields"])
    if (type(metadata["generation"]) is not int or metadata["generation"] != 1
            or not _equal(
                [metadata["namespace"], metadata["name"], metadata["uid"],
                 metadata["resourceVersion"]],
                [_NAMESPACE, relation.pod_name, relation.pod_uid,
                 relation.pod_resource_version])):
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver Pod incarnation metadata differs")
    annotations = metadata["annotations"]
    if type(annotations) is not dict or "kubernetes.io/config.seen" not in annotations:
        raise KubeAPIServerMirrorConfigurationError(
            "invalid kube-apiserver mirror annotations")
    seen = annotations["kubernetes.io/config.seen"]
    _seen_timestamp(seen)
    desired_meta = {
        "name": _NAME,
        "namespace": _NAMESPACE,
        "labels": {"component": "kube-apiserver", "tier": "control-plane"},
        "ownerReferences": [{"apiVersion": "v1", "kind": "Node",
            "name": ownership.node_ownership.node_name,
            "uid": ownership.node_ownership.node_uid, "controller": True}],
        "annotations": {
            "kubeadm.kubernetes.io/kube-apiserver.advertise-address.endpoint":
                f"{ip}:6443",
            "kubernetes.io/config.source": "file",
            "kubernetes.io/config.hash": relation.config_hash,
            "kubernetes.io/config.mirror": relation.mirror_hash,
            "kubernetes.io/config.seen": seen,
        },
    }
    if not all(_equal(metadata[key], desired_meta[key])
               for key in ("annotations", "labels", "ownerReferences")):
        raise KubeAPIServerMirrorConfigurationError(
            "kube-apiserver mirror labels, annotations or owner differ")
    desired = {"apiVersion": "v1", "kind": "Pod", "metadata": desired_meta,
               "spec": _expected_api_pod(
                   disk_pod=disk_pod, node_internal_ip=ip)}
    if type(pod["spec"]) is not dict or not matches_configuration(desired, pod):
        raise KubeAPIServerMirrorConfigurationError(
            "Pod differs from independent kube-apiserver mirror API configuration")
    return KubeAPIServerMirrorConfigurationBinding(
        _NAMESPACE, relation.pod_name, relation.pod_uid,
        relation.pod_resource_version, relation.config_hash, ip,
        tuple(name for name, _path in selected))


@dataclass(frozen=True, slots=True)
class KubeAPIServerMirrorConfigurationProof:
    ownership: RuntimeOwnershipProof
    source: ControlPlaneManifestSourceProof
    bindings: tuple[KubeAPIServerMirrorConfigurationBinding, ...]
    runtime_contract_complete: bool = False
    full_application_contract_complete: bool = False

    def __post_init__(self):
        try:
            if any(type(flag) is not bool or flag for flag in (
                    self.runtime_contract_complete,
                    self.full_application_contract_complete)):
                raise KubeAPIServerMirrorConfigurationError(
                    "kube-apiserver configuration cannot establish completion")
            if (type(self.bindings) is not tuple or len(self.bindings) != 1
                    or type(self.bindings[0]) is not
                        KubeAPIServerMirrorConfigurationBinding):
                raise KubeAPIServerMirrorConfigurationError(
                    "expected one exact kube-apiserver binding")
            self.bindings[0].__post_init__()
            if self.bindings != (_compute(ownership=self.ownership,
                                          source=self.source),):
                raise KubeAPIServerMirrorConfigurationError(
                    "kube-apiserver binding differs from same-source reconstruction")
        except KubeAPIServerMirrorConfigurationError:
            raise
        except (ValueError, TypeError, KeyError, IndexError, AttributeError,
                RecursionError, json.JSONDecodeError) as error:
            raise KubeAPIServerMirrorConfigurationError(
                "invalid kube-apiserver mirror configuration proof") from error


def validate_kube_apiserver_mirror_configuration(
        *, ownership: RuntimeOwnershipProof,
        source: ControlPlaneManifestSourceProof,
        ) -> KubeAPIServerMirrorConfigurationProof:
    """Validate authenticated disk configuration against the owned API mirror."""
    try:
        binding = _compute(ownership=ownership, source=source)
        return KubeAPIServerMirrorConfigurationProof(
            ownership=ownership, source=source, bindings=(binding,))
    except KubeAPIServerMirrorConfigurationError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError,
            RecursionError, json.JSONDecodeError) as error:
        raise KubeAPIServerMirrorConfigurationError(
            "invalid kube-apiserver mirror configuration source") from error
