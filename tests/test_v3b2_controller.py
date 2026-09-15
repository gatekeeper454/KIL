from __future__ import annotations

from dataclasses import FrozenInstanceError
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import tempfile
import tarfile
import unittest
import importlib.util
from unittest.mock import patch
from types import SimpleNamespace

from kil.v3b2_controller import (
    CommandResult,
    ControllerError,
    ControllerPaths,
    V3B2Controller,
    SubprocessCommandRunner,
)
from kil.v3b2_journal import Command, OwnedIdentity, load_journal
from kil.v3b2_contracts import TRACKS
from kil.v3b2_evidence import verify_bundle
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_manifests import WorkloadIdentity, render_objects


HEX64 = "a" * 64
SOURCE_COMMIT = "d" * 40
NOMINAL_REQUEST_ID = "v3b1-central-request"
KIL_MANIFEST_DIGEST = "45a167d79b92f352af05a3e9cb8a9df8e972e38ab23d04ca692053e2eaf63649"
KIL_CONFIG_ID = "sha256:f21285be21c8f691b9b60b7e38bb309564a5cc238512c7455eb7759f4d922ddb"
ENVOY_MANIFEST_DIGEST = "57e14a549d7bd43c8d3f6d03e8cfa653e037d4b38e133acd9b54f38c524401b4"
ENVOY_CONFIG_ID = "sha256:ef846ec85aabf01a2ff7176a185260e476ca43d20478f57281d88f7a66d5671f"


def control_plane_node(*, node_id: str = "a" * 64,
                       running: bool = True) -> str:
    return json.dumps([{
        "Id": node_id,
        "Name": "/kil-v3-lab-control-plane",
        "Image": "sha256:" + "9" * 64,
        "Config": {
            "Image": ("kindest/node:v1.36.1@sha256:"
                      "3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5"),
            "Labels": {
                "io.x-k8s.kind.cluster": "kil-v3-lab",
                "io.x-k8s.kind.role": "control-plane",
            },
        },
        "State": {"Running": running},
    }], sort_keys=True, separators=(",", ":")) + "\n"


def control_plane_manifest(component: str) -> str:
    return (
        "apiVersion: v1\n"
        "kind: Pod\n"
        "metadata:\n"
        f"  name: {component}\n"
        "  namespace: kube-system\n"
        "spec:\n"
        "  containers:\n"
        f"  - name: {component}\n"
        f"    image: registry.k8s.io/{component}:v1.36.1\n"
    )


def synthetic_kil_archive():
    """A deterministic OCI archive whose descriptors hash its actual bytes."""
    encode = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    config = encode({"architecture": "arm64", "os": "linux", "config": {"User": "65532"},
                     "rootfs": {"type": "layers", "diff_ids": []}})
    config_hash = sha256(config).hexdigest()
    manifest = encode({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                       "config": {"mediaType": "application/vnd.oci.image.config.v1+json",
                                  "digest": "sha256:" + config_hash, "size": len(config)}, "layers": []})
    manifest_hash = sha256(manifest).hexdigest()
    index = encode({"schemaVersion": 2, "manifests": [{
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "digest": "sha256:" + manifest_hash, "size": len(manifest),
        "annotations": {"org.opencontainers.image.ref.name": "kil.local/kil-v3b2:sha256-" + manifest_hash},
        "platform": {"architecture": "arm64", "os": "linux"},
    }]})
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in (("oci-layout", encode({"imageLayoutVersion": "1.0.0"})),
                           ("index.json", index), ("blobs/sha256/" + manifest_hash, manifest),
                           ("blobs/sha256/" + config_hash, config)):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, BytesIO(data))
    return output.getvalue(), manifest_hash, "sha256:" + config_hash


SYNTHETIC_ARCHIVE, SYNTHETIC_MANIFEST_DIGEST, SYNTHETIC_CONFIG_ID = synthetic_kil_archive()


@lru_cache(maxsize=1)
def production_runtime_snapshot():
    from tests.test_v3b2_inventory import snapshot

    return snapshot()


@lru_cache(maxsize=16)
def raw_runtime_inventory(
    run_id: str = "v3b2-" + "1" * 64,
    kil_digest: str = KIL_MANIFEST_DIGEST,
    kil_config_digest: str = KIL_CONFIG_ID,
    *,
    include_drivers: bool = True,
) -> str:
    from tests.test_v3b2_kil_pod_runtime import fixture as runtime_fixture

    root = Path(__file__).resolve().parents[1]
    profile = V3B2Profile.load(root / "deploy/kind/v3b2-profile.json")
    envoy_digest = ENVOY_MANIFEST_DIGEST
    workload = WorkloadIdentity(
        run_id, "sha256:" + kil_digest,
        "docker.io/envoyproxy/envoy@sha256:" + envoy_digest,
    )
    owned = OwnedIdentity(
        "kil-v3-lab", "unix:///tmp/owned/kil-v3-lab/docker.sock",
        "kil-v3-lab", "/tmp/owned/kubeconfig",
        "11111111-1111-4111-8111-111111111111", "a" * 64,
    )
    _configuration, _endpoints, _images, arguments = runtime_fixture(
        profile=profile, workload=workload, owned_identity=owned,
        kil_config_digest=kil_config_digest, envoy_config_digest=ENVOY_CONFIG_ID,
    )
    items = json.loads(arguments["runtime_objects"])["items"]
    snap = production_runtime_snapshot()
    identities = {(item.api_version, item.kind, item.namespace, item.name): item for item in snap.objects}
    rendered = json.loads(render_objects(profile, workload))["items"]
    policy_identities = {
        (item["apiVersion"], item["kind"], item["metadata"].get("namespace", ""),
         item["metadata"]["name"]): (f"policy-{index}", str(index + 1))
        for index, item in enumerate(
            row for row in rendered if row["kind"] in {"Namespace", "NetworkPolicy"}
        )
    }
    for item in rendered:
        key = (item["apiVersion"], item["kind"], item["metadata"].get("namespace", ""), item["metadata"]["name"])
        existing = next((row for row in items if
            (row["apiVersion"], row["kind"], row["metadata"].get("namespace", ""), row["metadata"]["name"]) == key
        ), None)
        if existing is not None:
            if item["kind"] == "Deployment" and item["metadata"].get("namespace", "").startswith("kil-"):
                existing["metadata"]["labels"] = item["metadata"]["labels"]
                existing["metadata"]["annotations"].update(item["metadata"]["annotations"])
                existing["spec"] = item["spec"]
            continue
        if key in policy_identities:
            item["metadata"]["uid"], item["metadata"]["resourceVersion"] = policy_identities[key]
        else:
            identity = identities[key]
            item["metadata"]["uid"] = identity.uid
            item["metadata"]["resourceVersion"] = identity.resource_version
        items.append(item)
    for name in ("default", "kube-node-lease", "kube-public", "local-path-storage"):
        if not any(row["kind"] == "Namespace" and row["metadata"]["name"] == name for row in items):
            items.append({"apiVersion": "v1", "kind": "Namespace", "metadata": {
                "namespace": "", "name": name, "uid": "uid-" + name, "resourceVersion": "1"}})
    calico = json.loads((root / "deploy/kind/calico-v3.32.0.objects.json").read_bytes())
    for item in calico["items"]:
        if item["kind"] not in {"ServiceAccount", "ConfigMap"}:
            continue
        key = (item["apiVersion"], item["kind"], item["metadata"].get("namespace", ""), item["metadata"]["name"])
        if any(
            (row["apiVersion"], row["kind"], row["metadata"].get("namespace", ""), row["metadata"]["name"]) == key
            for row in items
        ):
            continue
        identity = identities[key]
        item["metadata"].update(uid=identity.uid, resourceVersion=identity.resource_version)
        items.append(item)
    grouped: dict[tuple[str, str], list[object]] = {}
    for image in snap.pod_images:
        if image.image_role == "workload":
            continue
        digest = envoy_digest if image.container == "envoy" else kil_digest if image.image_role == "workload" else image.image.rsplit(":", 1)[1]
        requested = "docker.io/envoyproxy/envoy@sha256:" + digest if image.container == "envoy" else "kil.local/kil-v3b2:sha256-" + digest if image.image_role == "workload" else image.image
        row = {"name": image.container, "image": requested, "imageID": "docker-pullable://fixture@sha256:" + digest, "containerID": "containerd://" + __import__("hashlib").sha256((image.namespace + image.pod + image.container).encode()).hexdigest()}
        grouped.setdefault((image.namespace, image.pod), []).append((image.container_type, row, image.uid, image.resource_version))
    for (_namespace, pod), rows in grouped.items():
        prefix = "calico-node-" if pod.startswith("calico-node-") else "calico-kube-controllers-"
        actual = next(item for item in items if item["kind"] == "Pod"
                      and item["metadata"].get("namespace") == "kube-system"
                      and item["metadata"]["name"].startswith(prefix))
        actual["status"] = {
            "conditions": [{"type": "Ready", "status": "True"}],
            "initContainerStatuses": [row for placement, row, _uid, _rv in rows if placement == "init"],
            "containerStatuses": [row for placement, row, _uid, _rv in rows if placement == "regular"],
        }
    for endpoint in snap.endpoints:
        if any(item["kind"] == "Endpoints"
               and item["metadata"].get("namespace") == endpoint.namespace
               and item["metadata"]["name"] == endpoint.service for item in items):
            continue
        items.append({
            "apiVersion": "v1", "kind": "Endpoints",
            "metadata": {
                "namespace": endpoint.namespace, "name": endpoint.service,
                "uid": "uid-endpoint-" + endpoint.namespace + endpoint.service,
                "resourceVersion": "30",
            },
            "subsets": [{
                "addresses": [{"ip": address} for address in endpoint.addresses],
                "ports": [{"name": endpoint.port_name, "protocol": endpoint.protocol,
                           "port": endpoint.port}],
            }],
        })
    uid_map: dict[str, str] = {}
    rv_map: dict[str, str] = {}
    for item in items:
        metadata = item["metadata"]
        old_uid, old_rv = str(metadata["uid"]), str(metadata["resourceVersion"])
        if old_uid not in uid_map:
            uid_map[old_uid] = (
                old_uid
                if old_uid == "11111111-1111-4111-8111-111111111111"
                or old_uid.startswith("policy-")
                else f"00000000-0000-4000-8000-{len(uid_map) + 1:012x}"
            )
        if old_rv not in rv_map:
            rv_map[old_rv] = str(len(rv_map) + 1)
        metadata["uid"], metadata["resourceVersion"] = uid_map[old_uid], rv_map[old_rv]
    for item in items:
        metadata = item["metadata"]
        for owner in metadata.get("ownerReferences", []):
            owner["uid"] = uid_map[owner["uid"]]
        if item["kind"] == "EndpointSlice":
            for endpoint in item["endpoints"]:
                if "targetRef" in endpoint:
                    endpoint["targetRef"]["uid"] = uid_map[endpoint["targetRef"]["uid"]]
        if item["kind"] == "Endpoints":
            for subset in item.get("subsets", []):
                for address in subset.get("addresses", []):
                    if "targetRef" in address:
                        address["targetRef"]["uid"] = uid_map[address["targetRef"]["uid"]]
    if not include_drivers:
        items = [item for item in items if not (
            item["kind"] == "Pod"
            and item["metadata"].get("namespace", "").startswith("kil-v3-")
            and item["metadata"]["name"] == "driver"
        )]
    return json.dumps({"apiVersion": "v1", "kind": "List", "items": items}, sort_keys=True, separators=(",", ":")) + "\n"


class FakeRunner:
    def __init__(self, profiles: list[dict[str, object]] | None = None) -> None:
        self.profiles = [] if profiles is None else profiles
        self.commands = []
        self.attach_count = 0
        self.cancel_attach_count = 0
        self.attached_tracks: set[str] = set()
        self.drivers_applied = False
        self.fail_track: str | None = None
        self.inject_application_record = False
        self.profile_exists = False
        self.profile_status = "Running"
        self.cluster_exists = False
        self.fail_profile_start = False
        self.fail_stage: str | None = None
        self.failed_stage = False
        self.quiesce_seen = False
        self.wrong_image_id = False
        self.kil_manifest_digest = KIL_MANIFEST_DIGEST
        self.kil_config_id = KIL_CONFIG_ID
        self.calico_applied = False
        self.calico_expected = None
        self.policy_expected = None
        self.policy_observation_invalid = False
        self.workload_dispatch_check = None
        self.runtime_inventory_payload = None
        self.bound_kubeconfig = None
        self.bound_calico_path = None
        self.bound_docker_environment = None
        self.canceled_drivers: set[str] = set()
        self.cancel_exit_code = 0
        self.swap_envoy_container_after_drain = False
        self.run_id = "v3b2-" + "1" * 64
        self.node_inspect_count = 0
        self.control_plane_node_before: CommandResult | None = None
        self.control_plane_node_after: CommandResult | None = None
        self.control_plane_manifest_results = {
            component: CommandResult(0, control_plane_manifest(component), "")
            for component in ("kube-apiserver", "kube-controller-manager")
        }

    def node_image_check(self):
        return (
            "REF TYPE DIGEST STATUS SIZE UNPACKED\n"
            f"kil.local/kil-v3b2:sha256-{self.kil_manifest_digest} "
            f"application/vnd.oci.image.manifest.v1+json sha256:{self.kil_manifest_digest} "
            "complete (2/2) 1.0 KiB true\n"
            f"docker.io/envoyproxy/envoy@sha256:{ENVOY_MANIFEST_DIGEST} "
            f"application/vnd.oci.image.index.v1+json sha256:{ENVOY_MANIFEST_DIGEST} "
            "complete (18/18) 64.0 MiB true\n"
        )

    def calico_observed(self):
        items = json.loads(json.dumps(self.calico_expected))
        for index, item in enumerate(items, 1):
            item["metadata"].update(
                uid=f"00000000-0000-4000-8000-{index:012x}",
                resourceVersion=str(1000 + index),
            )
        return {"apiVersion": "v1", "kind": "List", "items": items}

    def run(self, command):
        self.commands.append(command)
        argv = command.argv
        if command.stdin and argv[-3:] == ("apply", "-f", "-"):
            applied = json.loads(command.stdin)["items"]
            self.run_id = applied[0]["metadata"]["annotations"]["kil.dev/run-id"]
            if any(row["kind"] == "Pod" for row in applied):
                self.drivers_applied = True
            if any(row["kind"] not in {"Namespace", "NetworkPolicy"} for row in applied):
                if self.workload_dispatch_check is not None: self.workload_dispatch_check()
        stage_matches = {
            "image_import": argv[:2] == ("docker", "load"),
            "image_load": argv[:3] == ("kind", "load", "docker-image"),
            "calico_apply": argv[-3:-1] == ("apply", "-f") and argv[-1].endswith("calico-v3.32.0.yaml"),
            "application_apply": argv[-3:] == ("apply", "-f", "-") and command.stdin is not None,
            "calico_readiness": argv[3:5] == ("get", "daemonset"),
            "driver_readiness": "logs" in argv and "pod/driver" in argv and not self.quiesce_seen,
            "quiesce": "exec" in argv and "drain_listeners" in argv[-1],
            "freeze": "logs" in argv and self.quiesce_seen,
            "cluster_delete": argv[:3] == ("kind", "delete", "cluster"),
            "profile_stop": argv[:2] == ("colima", "stop"),
            "profile_delete": argv[:2] == ("colima", "delete"),
        }
        if self.fail_stage is not None and stage_matches[self.fail_stage] and not self.failed_stage:
            self.failed_stage = True
            return CommandResult(9, "", "injected")
        exact_calico_apply = (
            "kubectl", "--kubeconfig", self.bound_kubeconfig or "", "apply", "-f",
            self.bound_calico_path or "",
        )
        if (argv == exact_calico_apply and command.mutating is True
                and command.stdin is None):
            self.calico_applied = True
            return CommandResult(0, "", "")
        if argv[:2] == ("colima", "start"):
            if self.fail_profile_start:
                return CommandResult(9, "", "injected")
            self.profile_exists = True
            self.profile_status = "Running"
            if hasattr(self, 'profile_paths'):
                from tests.test_v3b2_profile_state import create_profile
                create_profile(self.profile_paths)
            return CommandResult(0, "", "")
        if argv[:2] == ("colima", "stop"):
            self.profile_status = "Stopped"
            return CommandResult(0, "", "")
        if argv[:2] == ("colima", "delete"):
            self.profile_exists = False
            if hasattr(self, 'profile_paths'):
                import shutil
                for path in (self.profile_paths.profile, self.profile_paths.instance, self.profile_paths.disk):
                    if path.exists():
                        shutil.rmtree(path)
            return CommandResult(0, "", "")
        if argv[:2] == ("colima", "status"):
            return CommandResult(0, "running\n", "") if self.profile_exists else CommandResult(1, "", "profile does not exist")
        if argv[:3] == ("kind", "create", "cluster"):
            self.cluster_exists = True
            return CommandResult(0, "", "")
        if argv[:3] == ("kind", "delete", "cluster"):
            self.cluster_exists = False
            return CommandResult(0, "", "")
        if argv == ("git", "rev-parse", "HEAD") or argv == ("git", "rev-parse", "origin/main"):
            return CommandResult(0, SOURCE_COMMIT + "\n", "")
        if argv == ("git", "status", "--porcelain"):
            return CommandResult(0, "", "")
        if argv == ("colima", "list", "--json"):
            rows = list(self.profiles)
            if self.profile_exists:
                rows.append({"name": "kil-v3-lab", "status": self.profile_status, "arch": "aarch64",
                             "cpus": 4, "memory": 8589934592, "disk": 64424509440, "runtime": "docker"})
            return CommandResult(0, json.dumps(rows, separators=(",", ":")) + "\n", "")
        if argv == ("docker", "context", "show"):
            return CommandResult(0, "desktop-linux\n", "")
        if Path(argv[0]).name == "docker" and argv[1:] == ("--version",):
            return CommandResult(0, "Docker version 29.7.2\n", "")
        if Path(argv[0]).name == "kind" and argv[1:] == ("version",):
            return CommandResult(0, "kind v0.32.0\n", "")
        if Path(argv[0]).name == "kubectl" and argv[1:] == ("version", "--client", "-o", "json"):
            return CommandResult(0, '{"clientVersion":{"gitVersion":"v1.36.3"}}\n', "")
        if argv == ("colima", "version"):
            return CommandResult(0, "colima version 0.10.3\n", "")
        if argv == ("limactl", "--version"):
            return CommandResult(0, "limactl version 2.2.0\n", "")
        if argv[:2] == ("docker", "inspect"):
            if not self.cluster_exists:
                return CommandResult(1, "", "no such object")
            self.node_inspect_count += 1
            if self.node_inspect_count == 2 and self.control_plane_node_before is not None:
                return self.control_plane_node_before
            if self.node_inspect_count == 3 and self.control_plane_node_after is not None:
                return self.control_plane_node_after
            return CommandResult(0, control_plane_node(), "")
        if argv[:3] == ("docker", "container", "ls"):
            payload = json.dumps({"ID": "a" * 64, "Names": "kil-v3-lab-control-plane",
                "Image": "kindest/node:v1.36.1", "Labels": "io.x-k8s.kind.cluster=kil-v3-lab,io.x-k8s.kind.role=control-plane"}) + "\n" if self.cluster_exists else ""
            return CommandResult(0, payload, "")
        if argv[:3] == ("docker", "image", "inspect"):
            image = argv[3]
            config_ids = {
                "kil.local/kil-v3b2:sha256-" + self.kil_manifest_digest: self.kil_config_id,
                "docker.io/envoyproxy/envoy@sha256:" + ENVOY_MANIFEST_DIGEST: ENVOY_CONFIG_ID,
            }
            image_id = config_ids.get(image, "sha256:" + image.rsplit(":", 1)[1].removeprefix("sha256-"))
            if self.wrong_image_id:
                image_id = "sha256:" + "0" * 64
            return CommandResult(0, json.dumps([{"Id": image_id, "RepoTags": [image], "RepoDigests": [image]}]) + "\n", "")
        node_image_argv = (
            "docker", "exec", "a" * 64, "/usr/local/bin/ctr", "--address",
            "/run/containerd/containerd.sock", "--namespace", "k8s.io",
            "images", "check", "--snapshotter", "overlayfs",
        )
        expected_node_host = (f"unix://{self.profile_paths.profile}/docker.sock"
                              if hasattr(self, "profile_paths") else None)
        if (argv == node_image_argv
                and dict(command.env).get("DOCKER_HOST") == expected_node_host):
            return CommandResult(0, self.node_image_check(), "")
        if (len(argv) == 6 and argv[:4] == ("docker", "exec", "a" * 64, "/bin/cat")
                and argv[4] == "--"):
            component = Path(argv[5]).stem
            if component in self.control_plane_manifest_results:
                return self.control_plane_manifest_results[component]
        cri_prefix = ("docker", "exec", "a" * 64, "/usr/local/bin/crictl",
                      "--runtime-endpoint", "unix:///run/containerd/containerd.sock",
                      "--image-endpoint", "unix:///run/containerd/containerd.sock",
                      "--timeout", "10s", "inspecti", "--quiet", "--output", "json")
        if (len(argv) == 15 and argv[:14] == cri_prefix
                and command.env == self.bound_docker_environment):
            kil_reference = "kil.local/kil-v3b2:sha256-" + self.kil_manifest_digest
            envoy_reference = "docker.io/envoyproxy/envoy@sha256:" + ENVOY_MANIFEST_DIGEST
            if argv[-1] in (kil_reference, envoy_reference):
                is_kil = argv[-1] == kil_reference
                status = {"id": self.kil_config_id if is_kil else ENVOY_CONFIG_ID,
                          "repoTags": [kil_reference] if is_kil else [],
                          "repoDigests": [] if is_kil else [envoy_reference],
                          "size": "1024", "username": "", "pinned": False}
                if is_kil:
                    status["uid"] = {"value": "65532"}
                return CommandResult(0, json.dumps({"status": status}) + "\n", "")
        calico_get = ("kubectl", "--kubeconfig", self.bound_kubeconfig or "",
                      "get", "--filename", "-", "--output", "json")
        if self.policy_expected is not None:
            policy = self.policy_expected()
            from kil.v3b2_journal import _canonical_bytes
            if argv == calico_get and command.stdin == _canonical_bytes(policy) and command.env == ():
                if self.policy_observation_invalid: return CommandResult(0, "{}", "")
                observed = json.loads(json.dumps(policy))
                observed["metadata"] = {"resourceVersion": ""}
                for index, row in enumerate(observed["items"]):
                    row["metadata"].update(uid=f"policy-{index}", resourceVersion=str(index + 1))
                return CommandResult(0, _canonical_bytes(observed).decode(), "")
            from kil.v3b2_contracts import TRACK_NAMESPACES
            for _, namespace in TRACK_NAMESPACES:
                if argv == ("kubectl", "--kubeconfig", self.bound_kubeconfig,
                            "get", "pods,deployments,replicasets", "--namespace", namespace, "--output", "json") and command.env == ():
                    return CommandResult(0, '{"apiVersion":"v1","kind":"List","metadata":{"resourceVersion":""},"items":[]}', "")
        if self.calico_applied and argv == calico_get and self.calico_expected is not None:
            from kil.v3b2_journal import _canonical_bytes
            expected = _canonical_bytes({"apiVersion": "v1", "kind": "List",
                                         "items": self.calico_expected})
            if command.stdin == expected:
                return CommandResult(0, _canonical_bytes(self.calico_observed()).decode(), "")
        if argv[:2] in {("docker", "load"), ("docker", "tag"), ("docker", "pull")}:
            return CommandResult(0, "", "")
        if argv[3:5] == ("get", "daemonset") or argv[3:5] == ("get", "deployment"):
            deployment = argv[4] == "deployment"
            if deployment:
                kind, name = "Deployment", "calico-kube-controllers"
                containers = [{"name": name, "image": "quay.io/calico/kube-controllers@sha256:adf0ac895796d21bca5383bc81c4cd2614be3a4308085b47857d7999f4cc2b1f"}]
                init_containers = []
                status = {"readyReplicas": 1, "replicas": 1}
            else:
                kind, name = "DaemonSet", "calico-node"
                node = "quay.io/calico/node@sha256:f4fafd8ba641d96c5a91b01e5a519117d77d55dee789a3562ba3ad4aa125b36a"
                cni = "quay.io/calico/cni@sha256:1cfc6aa9c4dad3575fdf36b78185fd7d68bcd4acc95778f8342be4fb6a851a14"
                containers = [{"name": "calico-node", "image": node}]
                init_containers = [{"name": "upgrade-ipam", "image": cni}, {"name": "install-cni", "image": cni}, {"name": "ebpf-bootstrap", "image": node}]
                status = {"desiredNumberScheduled": 1, "numberReady": 1}
            value = {"apiVersion": "apps/v1", "kind": kind, "metadata": {"name": name, "namespace": "kube-system", "resourceVersion": "2", "uid": "uid-" + name}, "spec": {"containers": containers, "initContainers": init_containers}, "status": status}
            return CommandResult(0, json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", "")
        if "namespace" in argv and "kube-system" in argv:
            return CommandResult(0, json.dumps({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "kube-system", "uid": "11111111-1111-4111-8111-111111111111", "resourceVersion": "1"}}) + "\n", "")
        if argv[3:5] == ("get", "pod") and argv[-2:] == ("--output", "json"):
            pod_name = argv[5]
            namespace = argv[argv.index("--namespace") + 1]
            pod = next(item for item in json.loads(raw_runtime_inventory(
                self.run_id, self.kil_manifest_digest, self.kil_config_id))["items"]
                if item["kind"] == "Pod" and item["metadata"].get("namespace") == namespace
                and item["metadata"]["name"] == pod_name)
            role = "driver" if pod_name == "driver" else pod_name.split("-", 1)[0]
            status = next(row for row in pod["status"]["containerStatuses"] if row["name"] == role)
            track_by_namespace = dict((namespace, track) for track, namespace in __import__("kil.v3b2_contracts", fromlist=["TRACK_NAMESPACES"]).TRACK_NAMESPACES)
            completed = role == "driver" and track_by_namespace[namespace] in self.attached_tracks
            canceled = role == "driver" and namespace in self.canceled_drivers
            if role == "envoy" and self.quiesce_seen and self.swap_envoy_container_after_drain:
                status["containerID"] = "containerd://" + "f" * 64
                self.swap_envoy_container_after_drain = False
            terminal = canceled or completed
            runtime_status = {**status, "ready": not terminal}
            if terminal:
                runtime_status["state"] = {"terminated": {"exitCode": self.cancel_exit_code if canceled else 0}}
            pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {name: pod["metadata"][name] for name in ("name", "namespace", "resourceVersion", "uid")}, "status": {"conditions": [{"type": "Ready", "status": "False" if terminal else "True"}], "containerStatuses": [runtime_status]}}
            return CommandResult(0, json.dumps(pod, sort_keys=True, separators=(",", ":")) + "\n", "")
        if argv[3:5] == ("get", "endpointslices"):
            namespace = argv[argv.index("--namespace") + 1]
            role = argv[argv.index("--selector") + 1].split("=", 1)[1]
            inventory = json.loads(raw_runtime_inventory(
                self.run_id, self.kil_manifest_digest, self.kil_config_id))["items"]
            pod = next(item for item in inventory if item["kind"] == "Pod" and item["metadata"].get("namespace") == namespace and item["metadata"]["name"].startswith(role + "-"))
            endpoint = next(item for item in inventory if item["kind"] == "Endpoints" and item["metadata"].get("namespace") == namespace and item["metadata"]["name"] == role)
            item = {
                "apiVersion": "discovery.k8s.io/v1", "kind": "EndpointSlice",
                "metadata": {"name": role + "-abcde", "namespace": namespace,
                             "labels": {"kubernetes.io/service-name": role}},
                "addressType": "IPv4", "ports": endpoint["subsets"][0]["ports"],
                "endpoints": [{"addresses": [entry["ip"] for entry in endpoint["subsets"][0]["addresses"]],
                               "conditions": {"ready": True},
                               "targetRef": {"kind": "Pod", "name": pod["metadata"]["name"],
                                             "namespace": namespace, "uid": pod["metadata"]["uid"]}}],
            }
            return CommandResult(0, json.dumps({"apiVersion": "v1", "kind": "List", "items": [item]}, indent=2) + "\n", "")
        if (argv == ("kubectl", "--kubeconfig", self.bound_kubeconfig, "get",
                     "namespaces,pods,services,endpoints,endpointslices,serviceaccounts,configmaps,deployments,daemonsets,networkpolicies,nodes,replicasets",
                     "--all-namespaces", "--output", "json") and command.env == ()
                and command.stdin is None and command.mutating is False):
            return CommandResult(
                0,
                self.runtime_inventory_payload or raw_runtime_inventory(
                    self.run_id, self.kil_manifest_digest, self.kil_config_id,
                    include_drivers=self.drivers_applied),
                "",
            )
        if "attach" in argv:
            if command.stdin == b"":
                self.cancel_attach_count += 1
                self.canceled_drivers.add(argv[argv.index("--namespace") + 1])
                return CommandResult(0, "", "")
            self.attach_count += 1
            track = json.loads(command.stdin)["track"]
            if self.fail_track == track:
                return CommandResult(9, "", "injected")
            self.attached_tracks.add(track)
            status = 403 if track == TRACKS[2] else 200
            record = {
                "attempt_count": 1, "connect_monotonic_ns": 1,
                "decision_digest": __import__("hashlib").sha256(f"{track}:{status}".encode()).hexdigest(),
                "receive_monotonic_ns": 3, "response_status": status,
                "retry_performed": False, "schema_version": "kil.v3b1-driver-result.v1",
                "send_monotonic_ns": 2, "status": "complete", "track": track,
            }
            ready = {"connect_monotonic_ns": 1, "ready_monotonic_ns": 2, "schema_version": "kil.v3b1-driver-readiness.v1", "status": "ready", "track": track}
            stream = "".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in (ready, record))
            return CommandResult(0, stream, "")
        if "exec" in argv and "drain_listeners" in argv[-1]:
            self.quiesce_seen = True
            return CommandResult(0, '{"drain_requested":true}\n', "")
        if "exec" in argv and "/stats?format=json" in argv[-1]:
            names = (
                "http.kil_v3b_ingress.downstream_cx_active",
                "http.kil_v3b_ingress.downstream_rq_active",
                "cluster.kil-v3b-authz.upstream_rq_active",
                "cluster.kil-v3b-target.upstream_rq_active",
            )
            return CommandResult(0, json.dumps({"stats": [{"name": name, "value": 0} for name in names]}) + "\n", "")
        if "logs" in argv or "exec" in argv:
            operation = "logs" if "logs" in argv else "exec"
            resource = argv[argv.index(operation) + 1]
            role = "driver" if resource == "pod/driver" else resource.removeprefix("pod/").split("-", 1)[0]
            if self.inject_application_record and role == "authz":
                return CommandResult(0, '{"unexpected":"record"}\n', "")
            if role == "driver":
                namespace = argv[argv.index("--namespace") + 1]
                track = dict((namespace, track) for track, namespace in __import__("kil.v3b2_contracts", fromlist=["TRACK_NAMESPACES"]).TRACK_NAMESPACES)[namespace]
                if track not in self.attached_tracks:
                    record = {"connect_monotonic_ns": 1, "ready_monotonic_ns": 2, "schema_version": "kil.v3b1-driver-readiness.v1", "status": "ready", "track": track}
                    return CommandResult(0, json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", "")
            if self.attach_count:
                namespace = argv[argv.index("--namespace") + 1]
                track = dict((namespace, track) for track, namespace in __import__("kil.v3b2_contracts", fromlist=["TRACK_NAMESPACES"]).TRACK_NAMESPACES)[namespace]
                from tests.test_v3b2_evidence import producer_records, canonical
                kind = "decision" if role == "authz" else role
                rows = producer_records(track, self.run_id, request_free=track not in self.attached_tracks)[kind]
                return CommandResult(0, b"".join(canonical(row) for row in rows).decode(), "")
            return CommandResult(0, "", "")
        if "scale" in argv:
            self.quiesce_seen = True
            return CommandResult(0, "", "")
        return CommandResult(0, "{}\n", "")


def foreign(name: str, status: str) -> dict[str, object]:
    return {
        "name": name, "status": status, "arch": "aarch64", "cpus": 2,
        "memory": 4, "disk": 20, "runtime": "docker",
    }


class AcceptedArchiveConstantsTest(unittest.TestCase):
    def test_real_production_acceptance_constants_are_not_fixture_values(self):
        import kil.v3b2_controller as module
        self.assertEqual(module._ACCEPTED_KIL_ARCHIVE_SHA256,
                         "07c12f338c7d764812ef6271ec8942f0535d05019288f4df1e1b54f6cd75e4b6")
        self.assertEqual(module._ACCEPTED_V3B1_MANIFEST_SHA256,
                         "fa39212f1ffad95a1b5a674021ac5ce4ed9458025ce0dcc80077070355141cd0")
        self.assertEqual(module._ACCEPTED_V3B1_COMMITMENT,
                         "8d5ea5e8e12913945006af636bd674c39681a96b6d09a045e1b071ca77429ec2")
        self.assertEqual(module._ACCEPTED_KIL_CONFIG_DIGEST, KIL_CONFIG_ID)
        accepted = Path(__file__).resolve().parents[1] / "artifacts/generated/v3b1-local-envoy" / module._ACCEPTED_V3B1_RUN / "manifest.json"
        self.assertEqual(sha256(accepted.read_bytes()).hexdigest(), module._ACCEPTED_V3B1_MANIFEST_SHA256)
        self.assertEqual(json.loads(accepted.read_bytes())["immutable_images"]["kil_image_id"], "sha256:" + KIL_MANIFEST_DIGEST)
        self.assertEqual(module._archive_digest(SYNTHETIC_ARCHIVE), sha256(SYNTHETIC_ARCHIVE).hexdigest())
        self.assertEqual(module._digest(SYNTHETIC_ARCHIVE), sha256(SYNTHETIC_ARCHIVE).hexdigest())

    def test_synthetic_oci_archive_descriptors_match_actual_blob_bytes(self):
        with tarfile.open(fileobj=BytesIO(SYNTHETIC_ARCHIVE)) as archive:
            index = json.load(archive.extractfile("index.json"))
            descriptor = index["manifests"][0]
            manifest_bytes = archive.extractfile("blobs/sha256/" + SYNTHETIC_MANIFEST_DIGEST).read()
            self.assertEqual(descriptor["digest"], "sha256:" + sha256(manifest_bytes).hexdigest())
            self.assertEqual(descriptor["size"], len(manifest_bytes))
            config_descriptor = json.loads(manifest_bytes)["config"]
            config_bytes = archive.extractfile("blobs/sha256/" + SYNTHETIC_CONFIG_ID.removeprefix("sha256:")).read()
            self.assertEqual(config_descriptor["digest"], "sha256:" + sha256(config_bytes).hexdigest())
            self.assertEqual(config_descriptor["size"], len(config_bytes))
            self.assertEqual(json.loads(config_bytes)["architecture"], "arm64")
            self.assertNotEqual(descriptor["digest"], config_descriptor["digest"])


def v4_future(test):
    return unittest.skipUnless(
        os.environ.get("KIL_RUN_V4_FUTURE_TESTS") == "1",
        "V4 Future controller proof graph pending; run make v4-future-controller-test",
    )(test)


class V3B2ControllerTest(unittest.TestCase):
    def test_private_capture_write_fsyncs_file_and_parent_directory(self):
        from kil.v3b2_controller import _write_exclusive
        import os
        import stat
        modes = []
        original = os.fsync
        def observe(descriptor):
            modes.append(os.fstat(descriptor).st_mode)
            return original(descriptor)
        with patch("kil.v3b2_controller.os.fsync", side_effect=observe):
            _write_exclusive(self.paths.repository / "capture.json", b"{}\n")
        self.assertTrue(any(stat.S_ISREG(mode) for mode in modes))
        self.assertTrue(any(stat.S_ISDIR(mode) for mode in modes))

    def test_failure_cleanup_never_registers_missing_driver_starts(self):
        self.runner.fail_stage = "driver_readiness"
        with self.assertRaises(ControllerError):
            self.controller.request_free()
        events = load_journal(self.controller.journal_path)["events"]
        self.assertFalse(any(row["event"] == "driver_start_complete" for row in events))
        self.assertTrue(self.controller.owned_absence_proven)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name).resolve()
        self.isolated_home = root / 'home'
        self.isolated_home.mkdir()
        home_patch = patch('kil.v3b2_profile_state.passwd_home', return_value=self.isolated_home)
        home_patch.start()
        self.addCleanup(home_patch.stop)
        (root / "deploy/kind").mkdir(parents=True)
        source = Path(__file__).resolve().parents[1] / "deploy/kind/v3b2-profile.json"
        (root / "deploy/kind/v3b2-profile.json").write_bytes(source.read_bytes())
        calico = Path(__file__).resolve().parents[1] / "deploy/kind/calico-v3.32.0.yaml"
        (root / "deploy/kind/calico-v3.32.0.yaml").write_bytes(calico.read_bytes())
        projection = calico.with_suffix(".objects.json")
        (root / "deploy/kind/calico-v3.32.0.objects.json").write_bytes(projection.read_bytes())
        (root / ".tools/bin").mkdir(parents=True)
        tool_rows = {}
        for name in ("docker", "kind", "kubectl"):
            payload = ("tool-" + name).encode()
            binary = root / ".tools/bin" / name
            binary.write_bytes(payload)
            binary.chmod(0o755)
            tool_rows[name] = {
                "archive_sha256": "a" * 64,
                "byte_size": len(payload),
                "checksum_attestation": "test",
                "executable_sha256": __import__("hashlib").sha256(payload).hexdigest(),
                "source_url": "https://example.invalid/" + name,
                "version_output": {"docker": "Docker version 29.7.2", "kind": "kind v0.32.0", "kubectl": '{"clientVersion":{"gitVersion":"v1.36.3"}}'}[name],
            }
        (root / ".tools/locks").mkdir()
        v3b_profile = Path(__file__).resolve().parents[1] / "deploy/kind/v3b-profile.json"
        (root / "deploy/kind/v3b-profile.json").write_bytes(v3b_profile.read_bytes())
        accepted = Path(__file__).resolve().parents[1] / "artifacts/generated/v3b1-local-envoy"
        shutil.copytree(accepted, root / "artifacts/generated/v3b1-local-envoy")
        lock = {
            "schema_version": "kil.v3b-tools-lock.v1",
            "profile_sha256": __import__("hashlib").sha256(v3b_profile.read_bytes()).hexdigest(),
            "tools": tool_rows,
        }
        (root / ".tools/locks/v3b-tools.json").write_text(json.dumps(lock, sort_keys=True, separators=(",", ":")) + "\n")
        archive = SYNTHETIC_ARCHIVE
        (root / ".tools/v3b2-input").mkdir()
        (root / ".tools/v3b2-input/kil-image.tar").write_bytes(archive)
        import kil.v3b2_controller as controller_module
        self.accepted_manifest_path = (root / "artifacts/generated/v3b1-local-envoy" /
                                      controller_module._ACCEPTED_V3B1_RUN / "manifest.json")
        manifest = json.loads(self.accepted_manifest_path.read_bytes())
        manifest["immutable_images"]["kil_archive_sha256"] = sha256(archive).hexdigest()
        manifest["immutable_images"]["kil_image_id"] = "sha256:" + SYNTHETIC_MANIFEST_DIGEST
        # This fixture exercises the controller's accepted-input boundary, not
        # publication of a replacement historical experiment bundle.
        from tools.v3b1_local_envoy import _public_commitment_from_output
        manifest["public_commitment_sha256"] = _public_commitment_from_output(
            self.accepted_manifest_path.parent, manifest)
        self.accepted_manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
        self.accepted_constants = {
            "_ACCEPTED_KIL_ARCHIVE_SHA256": sha256(archive).hexdigest(),
            "_ACCEPTED_KIL_CONFIG_DIGEST": SYNTHETIC_CONFIG_ID,
            "_ACCEPTED_V3B1_MANIFEST_SHA256": sha256(self.accepted_manifest_path.read_bytes()).hexdigest(),
            "_ACCEPTED_V3B1_COMMITMENT": manifest["public_commitment_sha256"],
        }
        for name, value in self.accepted_constants.items():
            constant_patch = patch.object(controller_module, name, value)
            constant_patch.start()
            self.addCleanup(constant_patch.stop)
        # Keep the synthetic archive test boundary coherent with the finite
        # production membership module that runtime inventory now consults.
        import kil.v3b2_accepted_images as accepted_module
        import kil.v3b2_evidence as evidence_module
        production_runtime_snapshot()
        synthetic_request = "kil.local/kil-v3b2:sha256-" + SYNTHETIC_MANIFEST_DIGEST
        synthetic_contract = (
            (
                "kil", synthetic_request, "sha256:" + SYNTHETIC_MANIFEST_DIGEST,
                SYNTHETIC_CONFIG_ID,
                (SYNTHETIC_CONFIG_ID,
                 "kil.local/kil-v3b2@sha256:" + SYNTHETIC_MANIFEST_DIGEST),
            ),
            accepted_module._CONTRACT[1],
        )
        contract_patch = patch.object(accepted_module, "_CONTRACT", synthetic_contract)
        contract_patch.start()
        self.addCleanup(contract_patch.stop)
        synthetic_images = tuple(
            accepted_module.AcceptedImage(*row) for row in synthetic_contract
        )
        for module, name in (
            (accepted_module, "ACCEPTED_IMAGES"),
            (evidence_module, "ACCEPTED_IMAGES"),
        ):
            image_patch = patch.object(module, name, synthetic_images)
            image_patch.start()
            self.addCleanup(image_patch.stop)
        self.paths = ControllerPaths(
            repository=root,
            profile=root / "deploy/kind/v3b2-profile.json",
            tools=root / ".tools/bin",
            private=root / ".tools/v3b2-private",
            public=root / "artifacts/generated/v3b2-kind-calico",
        )
        self.runner = FakeRunner()
        self.runner.kil_manifest_digest = SYNTHETIC_MANIFEST_DIGEST
        self.runner.kil_config_id = SYNTHETIC_CONFIG_ID
        self.controller = V3B2Controller(self.paths, self.runner)
        self.runner.profile_paths = self.controller.profile_paths
        self.runner.bound_kubeconfig = str(self.controller.kubeconfig)
        self.runner.bound_calico_path = str(self.paths.private / "calico-v3.32.0.yaml")
        self.runner.bound_docker_environment = (("DOCKER_CONFIG", str(self.controller.docker_config)),
                                                ("DOCKER_HOST", self.controller.docker_host))
        from kil.v3b2_proofs import calico_objects
        calico_source = root / "deploy/kind/calico-v3.32.0.yaml"
        self.runner.calico_expected = calico_objects(
            calico_source.read_bytes(),
            calico_source.with_suffix(".objects.json").read_bytes(),
        )
        self.runner.policy_expected = lambda: {"apiVersion": "v1", "kind": "List", "items": [
            row for row in json.loads(render_objects(self.controller.profile, WorkloadIdentity(
                self.controller.run_id, "sha256:" + SYNTHETIC_MANIFEST_DIGEST,
                "docker.io/envoyproxy/envoy@sha256:" + ENVOY_MANIFEST_DIGEST)))["items"]
            if row["kind"] in {"Namespace", "NetworkPolicy"}]}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def assert_no_post_manifest_dispatch(self) -> None:
        image = [command for command in self.runner.commands if
                 command.argv[:2] in {("docker", "load"), ("docker", "pull"),
                                      ("docker", "tag")}
                 or command.argv[:3] == ("kind", "load", "docker-image")]
        calico = [command for command in self.runner.commands if
                  command.argv[-3:-1] == ("apply", "-f")
                  and command.argv[-1].endswith("calico-v3.32.0.yaml")]
        application = [command for command in self.runner.commands if
                       command.argv[-3:] == ("apply", "-f", "-")
                       and command.stdin is not None]
        self.assertEqual(image, [])
        self.assertEqual(calico, [])
        self.assertEqual(application, [])

    def manifest_cat_commands(self):
        return [command for command in self.runner.commands if
                len(command.argv) == 6
                and command.argv[:2] == ("docker", "exec")
                and command.argv[3:5] == ("/bin/cat", "--")]

    def leave_persisted_manifest_source_without_terminal(self) -> Path:
        import kil.v3b2_controller as module

        original = module.append_observed_terminal

        def crash_before_terminal(path, context, observations):
            if context.family == "control_plane_manifest_source":
                raise OSError("injected terminal persistence failure")
            return original(path, context, observations)

        with patch.object(module, "append_observed_terminal",
                          side_effect=crash_before_terminal):
            with self.assertRaisesRegex(OSError, "terminal persistence"):
                self.controller._up_lifecycle()
        checkpoints = list(self.paths.private.glob(
            "control-plane-manifest-source-*.json"))
        self.assertEqual(len(checkpoints), 1)
        return checkpoints[0]

    def test_controller_paths_are_frozen_slotted_absolute_and_contained(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.paths.repository = Path("/")  # type: ignore[misc]
        with self.assertRaises(ControllerError):
            ControllerPaths(Path("."), *([Path("/tmp/x")] * 4))

    def test_preflight_precedes_every_mutation_and_allows_foreign_profiles(self) -> None:
        self.runner.profiles = [foreign("client-a", "Running"), foreign("client-b", "Stopped")]
        for row in self.runner.profiles:
            (self.controller.profile_paths.lima / ('colima-' + row['name'])).mkdir(parents=True)
        result = self.controller.preflight()
        self.assertEqual(result["owned_profile"], "absent")
        self.assertEqual([command for command in self.runner.commands if command.mutating], [])
        self.assertTrue(self.controller.journal_path.exists())

    def test_preflight_rejects_owned_presence_and_ambiguous_inventory(self) -> None:
        for profiles in (
            [foreign("kil-v3-lab", "Running")],
            [foreign("client-a", "Running"), foreign("client-a", "Stopped")],
        ):
            with self.subTest(profiles=profiles):
                runner = FakeRunner(profiles)
                with self.assertRaises(ControllerError):
                    V3B2Controller(self.paths, runner).preflight()

    def test_preflight_rejects_tool_byte_drift_before_any_mutation(self) -> None:
        (self.paths.tools / "kind").write_bytes(b"tampered")
        with self.assertRaisesRegex(ControllerError, "tool_identity_mismatch"):
            self.controller.preflight()
        self.assertFalse(any(command.mutating for command in self.runner.commands))

    def test_preflight_rejects_missing_accepted_image_archive_before_mutation(self) -> None:
        (self.paths.tools.parent / "v3b2-input/kil-image.tar").unlink()
        with self.assertRaisesRegex(ControllerError, "kil_image_archive_unavailable"):
            self.controller.preflight()
        self.assertFalse(any(command.mutating for command in self.runner.commands))

    def test_preflight_binds_actual_synthetic_archive_size_hash_and_image_descriptors(self):
        self.controller.preflight()
        inputs = json.loads(self.controller.expected_inputs_path.read_bytes())
        self.assertEqual(inputs["archive_byte_count"], len(SYNTHETIC_ARCHIVE))
        self.assertEqual(inputs["archive_sha256"], sha256(SYNTHETIC_ARCHIVE).hexdigest())
        self.assertEqual(inputs["images"][0]["manifest_digest"], "sha256:" + SYNTHETIC_MANIFEST_DIGEST)
        self.assertEqual(inputs["images"][0]["config_digest"], SYNTHETIC_CONFIG_ID)
        self.assertEqual(inputs["images"][0].get("target_media_type"),
                         "application/vnd.oci.image.manifest.v1+json")
        self.assertEqual(inputs["images"][0]["allowed_repo_tags"],
                         ["kil.local/kil-v3b2:sha256-" + SYNTHETIC_MANIFEST_DIGEST])
        self.assertEqual(inputs["images"][0]["allowed_repo_digests"],
                         ["kil.local/kil-v3b2@sha256:" + SYNTHETIC_MANIFEST_DIGEST])
        self.assertEqual(inputs["images"][1]["allowed_repo_tags"], [])
        self.assertEqual(inputs["images"][1].get("target_media_type"),
                         "application/vnd.oci.image.index.v1+json")
        self.assertEqual(inputs["images"][1]["allowed_repo_digests"],
                         ["docker.io/envoyproxy/envoy@sha256:" + ENVOY_MANIFEST_DIGEST])

    def test_preflight_rejects_changed_archive_bytes_without_digest_mock(self):
        archive_path = self.paths.tools.parent / "v3b2-input/kil-image.tar"
        archive_path.write_bytes(SYNTHETIC_ARCHIVE[:-1] + b"x")
        with self.assertRaisesRegex(ControllerError, "kil_image_archive_unavailable"):
            self.controller.preflight()
        self.assertFalse(any(command.mutating for command in self.runner.commands))

    def test_preflight_rejects_repaired_manifest_claims(self):
        replacement = SYNTHETIC_ARCHIVE + b"changed"
        (self.paths.tools.parent / "v3b2-input/kil-image.tar").write_bytes(replacement)
        manifest = json.loads(self.accepted_manifest_path.read_bytes())
        manifest["immutable_images"]["kil_archive_sha256"] = sha256(replacement).hexdigest()
        from tools.v3b1_local_envoy import _public_commitment_from_output
        manifest["public_commitment_sha256"] = _public_commitment_from_output(
            self.accepted_manifest_path.parent, manifest)
        self.accepted_manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ControllerError, "content_identity_failed"):
            self.controller.preflight()
        self.assertFalse(any(command.mutating for command in self.runner.commands))

    def test_import_proof_rejects_wrong_archive_size_with_correct_hash(self):
        from dataclasses import asdict
        from kil.v3b2_proofs import ExpectedContext, RawObservation, canonical, decide
        self.controller.preflight()
        inputs = json.loads(self.controller.expected_inputs_path.read_bytes())
        inputs["owned_identity"] = asdict(self.controller._identity)
        observations = [RawObservation("image_archive", (), (), 0, canonical({
            "path": inputs["archive_path"], "sha256": inputs["archive_sha256"],
            "byte_count": len(SYNTHETIC_ARCHIVE)}), b"")]
        for index, expected in enumerate(inputs["images"]):
            observations.append(RawObservation("image_" + str(index),
                ("docker", "image", "inspect", expected["reference"]),
                (("DOCKER_HOST", inputs["owned_identity"]["docker_host"]),), 0,
                canonical([{"Id": expected["config_digest"],
                            "RepoTags": [expected["reference"]], "RepoDigests": []}]), b""))
        context = ExpectedContext(self.controller.run_digest, 1, "image_import", b"{}\n", canonical(inputs))
        self.assertEqual(decide(context, tuple(observations)).outcome, "complete")
        measured = json.loads(observations[0].stdout)
        measured["byte_count"] += 1
        observations[0] = RawObservation("image_archive", (), (), 0, canonical(measured), b"")
        self.assertEqual(decide(context, tuple(observations)).outcome, "unknown")

    def test_image_load_fixture_completes_only_exact_bound_node_store_proof(self):
        from kil import v3b2_proofs as proofs
        from kil.v3b2_controller import render_kind_config
        self.controller.preflight()
        inputs = json.loads(self.controller.expected_inputs_path.read_bytes())
        docker_host = self.controller.docker_host
        node_id = "a" * 64
        inputs["owned_identity"].update(node_container_id=node_id,
                                        cluster_incarnation_uid="11111111-1111-4111-8111-111111111111")
        self.controller.kind_config.write_bytes(render_kind_config(self.controller.profile))
        self.runner.cluster_exists = True
        intent = {"image": inputs["images"][0]["reference"],
                  "envoy_image": inputs["images"][1]["reference"]}
        context = proofs.ExpectedContext(self.controller.run_digest, 1, "image_load", proofs.canonical(intent),
                                         proofs.canonical(inputs))
        observations = self.controller._collect_observations(context)
        self.assertEqual([row.label for row in observations],
                         ["node_before", "cri_image_0", "cri_image_1", "node_images",
                          "node", "cluster_namespace", "kind_configuration"])
        self.assertEqual(proofs.decide(context, observations).outcome, "complete")
        argv = proofs.node_images_argv(node_id)
        env = (("DOCKER_CONFIG", str(self.controller.docker_config)),
               ("DOCKER_HOST", docker_host))
        result = self.runner.run(Command(argv, 60, env=env))
        poisons = (
            (proofs.node_images_argv("b" * 64), env, result.stdout),
            (argv, (("DOCKER_CONFIG", str(self.controller.docker_config)),
                    ("DOCKER_HOST", "unix:///tmp/foreign/docker.sock")), result.stdout),
            (argv, env, result.stdout.replace("sha256:" + SYNTHETIC_MANIFEST_DIGEST,
                                              SYNTHETIC_CONFIG_ID, 1)),
            (argv, env, result.stdout.replace("complete (2/2)", "incomplete (1/2)", 1)),
            (argv, env, "\n".join(result.stdout.splitlines()[:2]) + "\n"),
        )
        for poisoned_argv, poisoned_env, stdout in poisons:
            with self.subTest(argv=poisoned_argv[2], host=dict(poisoned_env)["DOCKER_HOST"]):
                poisoned = proofs.RawObservation("node_images", poisoned_argv,
                                                 poisoned_env, 0, stdout.encode(), b"")
                altered = (*observations[:3], poisoned, *observations[4:])
                self.assertNotEqual(proofs.decide(context, altered).outcome,
                                    "complete")

    def test_image_load_and_calico_apply_complete_before_application_gate(self):
        from kil.v3b2_journal import load_expected_context
        with self.assertRaisesRegex(
                ControllerError,
                "operation_postcondition_unproved:platform_admission_terminal_gate_pending"):
            self.controller._up_lifecycle()
        events = load_journal(self.controller.journal_path)["events"]
        labels = [row["event"] for row in events]
        self.assertLess(labels.index("cluster_create_complete"),
                        labels.index("control_plane_manifest_source_complete"))
        self.assertLess(labels.index("control_plane_manifest_source_complete"),
                        labels.index("image_import_intent"))
        self.assertTrue(any(row["event"] == "image_load_complete" for row in events))
        self.assertTrue(any(row["event"] == "calico_apply_complete" for row in events))
        self.assertFalse(any(row["event"] == "application_apply_complete" for row in events))
        command_count = len(self.runner.commands)
        replayed = json.loads(load_expected_context(self.controller.journal_path).inputs)
        self.assertEqual(len(self.runner.commands), command_count)
        references = replayed["prior_node_image_references"]
        self.assertEqual([row["expected"]["config_digest"] for row in references],
                         [SYNTHETIC_CONFIG_ID, ENVOY_CONFIG_ID])
        self.assertEqual([row["image_ref"] for row in references],
                         [SYNTHETIC_CONFIG_ID, "docker.io/envoyproxy/envoy@sha256:" + ENVOY_MANIFEST_DIGEST])
        self.assertIs(replayed["runtime_contract_complete"], False)

    def test_manifest_source_rejects_changed_before_node_identity_before_downstream_dispatch(self):
        from kil.v3b2_control_plane_manifest_source import ControlPlaneManifestSourceError
        self.runner.control_plane_node_before = CommandResult(
            0, control_plane_node(node_id="b" * 64), "")
        with self.assertRaises(ControlPlaneManifestSourceError):
            self.controller._up_lifecycle()
        self.assertEqual(len(self.manifest_cat_commands()), 2)
        self.assert_no_post_manifest_dispatch()

    def test_manifest_source_rejects_changed_after_node_identity_before_downstream_dispatch(self):
        from kil.v3b2_control_plane_manifest_source import ControlPlaneManifestSourceError
        self.runner.control_plane_node_after = CommandResult(
            0, control_plane_node(node_id="b" * 64), "")
        with self.assertRaises(ControlPlaneManifestSourceError):
            self.controller._up_lifecycle()
        self.assertEqual(len(self.manifest_cat_commands()), 2)
        self.assert_no_post_manifest_dispatch()

    def test_manifest_source_rejects_stopped_node_before_downstream_dispatch(self):
        from kil.v3b2_control_plane_manifest_source import ControlPlaneManifestSourceError
        self.runner.control_plane_node_before = CommandResult(
            0, control_plane_node(running=False), "")
        with self.assertRaises(ControlPlaneManifestSourceError):
            self.controller._up_lifecycle()
        self.assertEqual(len(self.manifest_cat_commands()), 2)
        self.assert_no_post_manifest_dispatch()

    def test_manifest_source_rejects_nonzero_read_before_downstream_dispatch(self):
        from kil.v3b2_control_plane_manifest_source import ControlPlaneManifestSourceError
        self.runner.control_plane_manifest_results["kube-apiserver"] = CommandResult(
            9, "", "injected read failure")
        with self.assertRaises(ControlPlaneManifestSourceError):
            self.controller._up_lifecycle()
        self.assertEqual(len(self.manifest_cat_commands()), 2)
        self.assert_no_post_manifest_dispatch()

    def test_manifest_source_rejects_truncated_read_before_downstream_dispatch(self):
        from kil.v3b2_control_plane_manifest_source import ControlPlaneManifestSourceError
        self.runner.control_plane_manifest_results["kube-controller-manager"] = CommandResult(
            -1001, control_plane_manifest("kube-controller-manager")[:64],
            "output truncated")
        with self.assertRaises(ControlPlaneManifestSourceError):
            self.controller._up_lifecycle()
        self.assertEqual(len(self.manifest_cat_commands()), 2)
        self.assert_no_post_manifest_dispatch()

    def test_manifest_source_publication_failure_prevents_downstream_dispatch(self):
        from kil.v3b2_control_plane_manifest_source import (
            validate_control_plane_manifest_source,
        )
        with patch(
                "kil.v3b2_control_plane_manifest_source."
                "validate_control_plane_manifest_source",
                wraps=validate_control_plane_manifest_source) as validator:
            with patch(
                    "kil.v3b2_control_plane_manifest_source_record."
                    "publish_control_plane_manifest_source_record",
                    side_effect=OSError("injected publication failure")):
                with self.assertRaisesRegex(OSError, "publication failure"):
                    self.controller._up_lifecycle()
        authority = validator.call_args.kwargs
        self.assertEqual(authority["owned_identity"], self.controller._identity)
        self.assertEqual(json.loads(authority["context"].inputs)["owned_identity"],
                         {field: getattr(authority["owned_identity"], field)
                          for field in (
                              "colima_profile", "docker_host", "kind_cluster",
                              "kubeconfig", "cluster_incarnation_uid",
                              "node_container_id",
                          )})
        self.assert_no_post_manifest_dispatch()

    def test_manifest_source_recovery_revalidates_persisted_checkpoint_without_live_reads(self):
        self.leave_persisted_manifest_source_without_terminal()
        before = len(self.manifest_cat_commands())
        from kil.v3b2_control_plane_manifest_source_record import (
            read_control_plane_manifest_source_record,
        )
        with patch(
                "kil.v3b2_control_plane_manifest_source_record."
                "read_control_plane_manifest_source_record",
                wraps=read_control_plane_manifest_source_record) as reader:
            result = V3B2Controller(self.paths, self.runner).recover()
        self.assertEqual(result["completed"], "control_plane_manifest_source")
        self.assertEqual(result["proof_outcome"], "complete")
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(len(self.manifest_cat_commands()), before)
        self.assert_no_post_manifest_dispatch()

    def test_manifest_source_recovery_rejects_missing_checkpoint_without_live_reads(self):
        with patch(
                "kil.v3b2_control_plane_manifest_source_record."
                "publish_control_plane_manifest_source_record",
                side_effect=OSError("injected publication failure")):
            with self.assertRaisesRegex(OSError, "publication failure"):
                self.controller._up_lifecycle()
        self.assertEqual(list(self.paths.private.glob(
            "control-plane-manifest-source-*.json")), [])
        before = len(self.manifest_cat_commands())
        result = V3B2Controller(self.paths, self.runner).recover()
        self.assertEqual(result["proof_outcome"], "teardown_only")
        self.assertIsNone(result["completed"])
        self.assertEqual(len(self.manifest_cat_commands()), before)
        self.assert_no_post_manifest_dispatch()

    def test_manifest_source_recovery_rejects_corrupt_checkpoint_without_live_reads(self):
        checkpoint = self.leave_persisted_manifest_source_without_terminal()
        checkpoint.write_bytes(b'{"corrupt":true}\n')
        before = len(self.manifest_cat_commands())
        result = V3B2Controller(self.paths, self.runner).recover()
        self.assertEqual(result["proof_outcome"], "teardown_only")
        self.assertIsNone(result["completed"])
        self.assertEqual(len(self.manifest_cat_commands()), before)
        self.assert_no_post_manifest_dispatch()

    def test_policy_checkpoint_is_durable_before_any_workload_dispatch(self):
        checked = []
        def check():
            from kil.v3b2_journal import load_expected_context
            from kil.v3b2_policy_stage_checkpoint import read_policy_stage_checkpoint
            context = load_expected_context(self.controller.journal_path)
            proof = read_policy_stage_checkpoint(self.controller.journal_path, context)
            self.assertEqual(len(proof.bindings), 18)
            checked.append(context.intent_sequence)
        self.runner.workload_dispatch_check = check
        with self.assertRaisesRegex(ControllerError, "operation_postcondition_unproved"):
            self.controller._up_lifecycle()
        self.assertEqual(len(checked), 2)

    def test_application_terminal_collector_reads_strict_pre_driver_checkpoint_registry(self):
        from kil.v3b2_pre_driver_checkpoint import read_pre_driver_checkpoint_bytes
        from kil.v3b2_proofs import OPERATIONS
        captured = []
        def read(path, context, *, maximum):
            payload = read_pre_driver_checkpoint_bytes(path, context, maximum=maximum)
            captured.append((context, payload))
            return payload
        with patch("kil.v3b2_pre_driver_checkpoint.read_pre_driver_checkpoint_bytes",
                   side_effect=read) as reader:
            with self.assertRaisesRegex(
                    ControllerError,
                    "operation_postcondition_unproved:platform_admission_terminal_gate_pending"):
                self.controller._up_lifecycle()
        self.assertEqual(reader.call_count, 1)
        context, expected = captured[0]
        requests = OPERATIONS["application_apply"].requests(context)
        self.assertEqual([row.label for row in requests], ["pre_driver_checkpoint",
                         "node_before", "runtime_inventory", "node",
                         "cluster_namespace", "kind_configuration"])
        self.assertTrue(expected.startswith(b'{"context_commitment":'))

    def test_invalid_policy_observation_prevents_workloads_and_latches_teardown(self):
        self.runner.policy_observation_invalid = True
        self.runner.workload_dispatch_check = lambda: self.fail("workload dispatched before checkpoint")
        with self.assertRaisesRegex(ControllerError, "policy_stage_checkpoint_failed"):
            self.controller._up_lifecycle()
        journal = load_journal(self.controller.journal_path)
        self.assertIsNotNone(journal["teardown_from_sequence"])
        self.assertFalse(list(self.paths.private.glob("policy-stage-*.json")))

    def test_policy_checkpoint_publication_failure_prevents_workload_dispatch(self):
        self.runner.workload_dispatch_check = lambda: self.fail("workload dispatched after publication failure")
        with patch("kil.v3b2_policy_stage_checkpoint._publish_observed_proof", side_effect=OSError("fsync failed")):
            with self.assertRaisesRegex(ControllerError, "policy_stage_checkpoint_failed"):
                self.controller._up_lifecycle()
        journal = load_journal(self.controller.journal_path)
        self.assertIsNotNone(journal["teardown_from_sequence"])
        self.assertFalse(list(self.paths.private.glob("policy-stage-*.json")))

    def test_calico_apply_fixture_uses_pinned_set_and_shared_proof_fails_closed(self):
        from kil import v3b2_proofs as proofs
        expected = self.runner.calico_expected
        inputs = {"owned_identity": {
                      "kubeconfig": str(self.controller.kubeconfig),
                      "docker_host": self.controller.docker_host,
                  },
                  "kind_config_path": str(self.controller.kind_config),
                  "applied_objects": expected}
        context = proofs.ExpectedContext("a" * 64, 1, "calico_apply", b"{}\n",
                                         proofs.canonical(inputs))
        request = proofs.OPERATIONS["calico_apply"].requests(context)[0].command
        before = self.runner.run(request)
        self.assertEqual(before.stdout, "{}\n")
        from kil.v3b2_journal import kubectl_apply_calico_command
        apply = kubectl_apply_calico_command(
            self.controller._identity, self.paths.private / "calico-v3.32.0.yaml")
        self.assertEqual(self.runner.run(apply).returncode, 0)
        result = self.runner.run(request)
        observed = proofs.RawObservation("applied_objects", request.argv, request.env,
                                         0, result.stdout_bytes, b"")
        self.assertEqual(proofs._applied(context, (observed,)).outcome, "complete")
        poisons = []
        missing = self.runner.calico_observed(); missing["items"].pop(); poisons.append(missing)
        extra = self.runner.calico_observed()
        foreign = json.loads(json.dumps(extra["items"][0]))
        foreign["metadata"].update(name="foreign-calico-object",
                                   uid="00000000-0000-4000-8000-ffffffffffff",
                                   resourceVersion="9999")
        extra["items"].append(foreign); poisons.append(extra)
        changed = self.runner.calico_observed()
        next(item for item in changed["items"] if item["kind"] == "ConfigMap")["data"]["foreign"] = "x"
        poisons.append(changed)
        no_uid = self.runner.calico_observed(); no_uid["items"][0]["metadata"].pop("uid"); poisons.append(no_uid)
        bad_rv = self.runner.calico_observed(); bad_rv["items"][0]["metadata"]["resourceVersion"] = ""; poisons.append(bad_rv)
        for document in poisons:
            poison = proofs.RawObservation("applied_objects", request.argv, request.env,
                                           0, proofs.canonical(document), b"")
            with self.assertRaises(proofs.ProofError):
                proofs._applied(context, (poison,))
        wrong_get = Command(
            ("kubectl", "--kubeconfig", "/tmp/foreign-kubeconfig", "get",
             "--filename", "-", "--output", "json"), 60,
            stdin=request.stdin,
        )
        self.assertEqual(self.runner.run(wrong_get).stdout, "{}\n")
        foreign_apply = Command(
            ("kubectl", "--kubeconfig", str(self.controller.kubeconfig), "apply",
             "-f", "/tmp/foreign/calico-v3.32.0.yaml"), 60, mutating=True,
        )
        self.runner.calico_applied = False
        self.runner.run(foreign_apply)
        self.assertFalse(self.runner.calico_applied)
        noncanonical = SimpleNamespace(
            argv=request.argv, env=request.env, stdin=b'{ "apiVersion": "v1" }\n',
            mutating=False,
        )
        self.runner.calico_applied = True
        self.assertEqual(self.runner.run(noncanonical).stdout, "{}\n")

    @v4_future
    def test_import_uses_preflight_verified_archive_bytes_not_reopened_path(self) -> None:
        archive_path = self.paths.tools.parent / "v3b2-input/kil-image.tar"
        verified = archive_path.read_bytes()
        self.controller.preflight()
        archive_path.write_bytes(b"replacement")
        with self.assertRaisesRegex(ControllerError, "operation_postcondition_unproved:invalid_or_missing_observation"):
            self.controller._up_lifecycle()
        load = next(command for command in self.runner.commands if command.argv == ("docker", "load"))
        self.assertEqual(load.stdin, verified)
        events = load_journal(self.controller.journal_path)["events"]
        self.assertTrue(any(row["event"] == "image_import_complete" for row in events))
        self.assertTrue(any(row["event"] == "image_load_complete" for row in events))
        self.assertTrue(any(row["event"] == "calico_apply_complete" for row in events))
        self.assertFalse(any(row["event"] == "application_apply_complete" for row in events))
        self.assertTrue(any(command.argv[-3:] == ("apply", "-f", "-")
                            and command.stdin is not None
                            for command in self.runner.commands))

    def test_fake_import_inspection_preserves_distinct_manifest_and_config_identities(self) -> None:
        references = (
            "kil.local/kil-v3b2:sha256-" + SYNTHETIC_MANIFEST_DIGEST,
            "docker.io/envoyproxy/envoy@sha256:" + ENVOY_MANIFEST_DIGEST,
        )
        expected_ids = (SYNTHETIC_CONFIG_ID, ENVOY_CONFIG_ID)
        for reference, expected_id in zip(references, expected_ids):
            result = self.runner.run(Command(
                ("docker", "image", "inspect", reference), 60,
                env=(("DOCKER_CONFIG", str(self.controller.docker_config)),
                     ("DOCKER_HOST", self.controller.docker_host)),
            ))
            row = json.loads(result.stdout)[0]
            self.assertEqual(row["Id"], expected_id)
            self.assertNotEqual(row["Id"].removeprefix("sha256:"), reference.rsplit(":", 1)[1].removeprefix("sha256-"))

    def test_fake_cri_image_inspection_is_exact_node_local_and_preserves_reference_domains(self):
        references = ("kil.local/kil-v3b2:sha256-" + SYNTHETIC_MANIFEST_DIGEST,
                      "docker.io/envoyproxy/envoy@sha256:" + ENVOY_MANIFEST_DIGEST)
        environment = (("DOCKER_CONFIG", str(self.controller.docker_config)),
                       ("DOCKER_HOST", self.controller.docker_host))
        for index, reference in enumerate(references):
            argv = ("docker", "exec", "a" * 64, "/usr/local/bin/crictl",
                    "--runtime-endpoint", "unix:///run/containerd/containerd.sock",
                    "--image-endpoint", "unix:///run/containerd/containerd.sock",
                    "--timeout", "10s", "inspecti", "--quiet", "--output", "json", reference)
            result = self.runner.run(Command(argv, 30, env=environment))
            self.assertTrue(result.stdout.startswith("{"), "missing CRI JSON response")
            document = json.loads(result.stdout)
            self.assertIn("status", document)
            self.assertEqual(document["status"]["id"], (SYNTHETIC_CONFIG_ID, ENVOY_CONFIG_ID)[index])
            self.assertEqual(document["status"]["repoTags"], [reference] if index == 0 else [])
            self.assertEqual(document["status"]["repoDigests"], [] if index == 0 else [reference])
            wrong_node = (*argv[:2], "b" * 64, *argv[3:])
            self.assertNotIn('"status"', self.runner.run(Command(wrong_node, 30, env=environment)).stdout)
            wrong_config = (("DOCKER_CONFIG", "/tmp/foreign/docker-config"), environment[1])
            self.assertNotIn('"status"', self.runner.run(Command(argv, 30, env=wrong_config)).stdout)

    def test_import_rejects_right_tag_with_wrong_realized_image_id_and_cleans_up(self) -> None:
        self.runner.wrong_image_id = True
        with self.assertRaisesRegex(ControllerError, "image_import_identity_invalid"):
            self.controller.up()
        self.assertTrue(self.controller.owned_absence_proven)

    def test_failed_profile_start_is_proven_absent_and_closes_to_safe_teardown(self) -> None:
        self.runner.fail_profile_start = True
        with self.assertRaisesRegex(ControllerError, "profile_start_failed"):
            self.controller.up()
        resumed = V3B2Controller(self.paths, self.runner)
        self.assertTrue(resumed.owned_absence_proven)
        self.assertIn("profile_start_failed", [name for name, _details in resumed.events])
        self.assertFalse(any("attach" in command.argv and command.stdin for command in self.runner.commands))

    @v4_future
    def test_uncertain_command_failures_enter_exact_cleanup_without_forward_progress(self) -> None:
        abandoned = {"image_import", "image_load", "calico_apply", "application_apply", "quiesce"}
        for index, stage in enumerate((
            "image_import", "image_load", "calico_apply", "application_apply",
            "calico_readiness", "driver_readiness", "quiesce", "freeze",
            "cluster_delete", "profile_stop", "profile_delete",
        )):
            with self.subTest(stage=stage):
                if index:
                    self.tearDown()
                    self.setUp()
                self.runner.fail_stage = stage
                with self.assertRaises(ControllerError):
                    self.controller.request_free()
                self.assertTrue(self.controller.owned_absence_proven)
                events = [name for name, _details in V3B2Controller(self.paths, self.runner).events]
                if stage in abandoned:
                    family = "envoy_quiesce" if stage == "quiesce" else stage
                    self.assertIn(family + "_abandoned_for_teardown", events)
                self.assertNotIn("publication_complete", events)
                self.assertFalse(any("attach" in command.argv and command.stdin for command in self.runner.commands))

    def test_global_docker_context_is_read_only(self) -> None:
        self.controller.preflight()
        contexts = [command for command in self.runner.commands if command.argv[:2] == ("docker", "context")]
        self.assertEqual(len(contexts), 1)
        self.assertFalse(contexts[0].mutating)

    @v4_future
    def test_up_uses_only_owned_profile_cluster_and_applies_policy_before_workloads(self) -> None:
        self.controller.up()
        mutations = [command for command in self.runner.commands if command.mutating]
        for command in mutations:
            if command.argv[0] == "colima":
                self.assertIn(("--profile", "kil-v3-lab"), tuple(zip(command.argv, command.argv[1:])))
            if command.argv[0] == "kind":
                self.assertIn(("--name", "kil-v3-lab"), tuple(zip(command.argv, command.argv[1:])))
                if command.argv[1:3] == ("load", "docker-image"):
                    self.assertRegex(command.argv[3], r"^(?:kil\.local/kil-v3b2:sha256-|docker\.io/envoyproxy/envoy@sha256:)[0-9a-f]{64}$")
                else:
                    self.assertIn(("--kubeconfig", str(self.controller.kubeconfig)), tuple(zip(command.argv, command.argv[1:])))
        applied = [json.loads(command.stdin) for command in mutations if command.argv[-3:] == ("apply", "-f", "-")]
        kinds = [{item["kind"] for item in payload["items"]} for payload in applied]
        self.assertEqual(kinds[0], {"Namespace"})
        self.assertEqual(kinds[1], {"NetworkPolicy"})
        self.assertNotIn("NetworkPolicy", kinds[2])
        driver_apply = next(index for index, command in enumerate(self.runner.commands) if command.stdin is not None and b'"kind":"Pod"' in command.stdin)
        endpoint_reads = [index for index, command in enumerate(self.runner.commands) if command.argv[3:5] == ("get", "endpointslices")]
        self.assertEqual(len(endpoint_reads), 9)
        self.assertLess(max(endpoint_reads), driver_apply)
        first_app = next(index for index, command in enumerate(self.runner.commands) if command.stdin is not None and command.argv[-3:] == ("apply", "-f", "-"))
        calico_reads = [index for index, command in enumerate(self.runner.commands) if "calico-node" in command.argv or "calico-kube-controllers" in command.argv]
        self.assertTrue(calico_reads and max(calico_reads) < first_app)
        self.assertEqual(self.controller.kind_config.read_bytes(), __import__("kil.v3b2_manifests", fromlist=["render_kind_config"]).render_kind_config(self.controller.profile))

    @v4_future
    def test_request_free_sends_no_attach_stdin_or_application_records(self) -> None:
        result = self.controller.request_free()
        self.assertEqual(result["instructions_sent"], 0)
        self.assertFalse(any("attach" in command.argv and command.stdin for command in self.runner.commands))
        self.assertFalse(any(bool(command.stdin) and "attach" in command.argv for command in self.runner.commands))
        self.assertEqual(result["application_records"], 0)
        self.assertTrue(self.controller.owned_absence_proven)
        started = [event for event in self.controller.events if event[0] == "driver_start_complete"]
        self.assertEqual(len(started), 3)
        drains = [command for command in self.runner.commands if "exec" in command.argv and "drain_listeners" in command.argv[-1]]
        self.assertEqual(len(drains), 3)
        self.assertEqual(self.runner.canceled_drivers, {namespace for _track, namespace in __import__("kil.v3b2_contracts", fromlist=["TRACK_NAMESPACES"]).TRACK_NAMESPACES})
        event_names = [name for name, _details in self.controller.events]
        self.assertLess(event_names.index("driver_cancel_complete"), event_names.index("envoy_quiesce_intent"))
        self.assertLess(event_names.index("envoy_quiesce_complete"), event_names.index("evidence_freeze_intent"))
        self.assertLess(event_names.index("foreign_snapshot_comparison_complete"), event_names.index("publication_intent"))
        verified = verify_bundle(Path(result["bundle"]))
        self.assertEqual(verified.result_class, "diagnostic_request_free_kind_calico_readiness")
        self.assertEqual(len(self.controller._captured_sources), 12)
        self.assertTrue(all(source.identity.object_uid != "uid-0" for source in self.controller._captured_sources))
        source_logs = [command for command in self.runner.commands if "logs" in command.argv]
        self.assertTrue(all(command.argv[command.argv.index("logs") + 1].startswith("pod/") for command in source_logs))
        for capture in self.controller._captured_sources:
            kind = capture.identity.logical_name.split(":", 1)[1]
            if kind == "driver":
                continue
            # capture_source performs expected, before, and after identity reads;
            # the Fake returns the inventory-bound Pod projection for each.
            role = {"decision": "authz", "envoy": "envoy", "target": "target"}[kind]
            self.assertGreaterEqual(sum(
                1 for command in self.runner.commands
                if command.argv[3:5] == ("get", "pod") and command.argv[5].startswith(role + "-")
            ), 3)

    @v4_future
    def test_driver_eof_cancel_requires_retained_terminal_exit_zero(self) -> None:
        self.runner.cancel_exit_code = 7
        with self.assertRaisesRegex(ControllerError, "driver_cancel_postcondition_invalid"):
            self.controller.request_free()
        self.assertTrue(self.controller.owned_absence_proven)
        self.assertFalse(any(command.stdin for command in self.runner.commands if "attach" in command.argv))
        events = load_journal(self.controller.journal_path)["events"]
        self.assertTrue(any(row["event"] == "driver_cancel_abandoned_for_teardown" for row in events))
        self.assertFalse(any(row["event"] == "driver_cancel_failed" for row in events))

    def test_process_boundary_drops_inherited_authority_overrides(self) -> None:
        poison = {key: "synthetic-foreign" for key in (
            "DOCKER_CONTEXT", "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH", "KUBECONFIG", "COLIMA_HOME", "LIMA_HOME",
            "COLIMA_PROFILE", "KIND_EXPERIMENTAL_PROVIDER", "HTTP_PROXY",
        )}
        command = Command(("colima", "list", "--json"), 60)
        with patch.dict("os.environ", poison), patch(
            "kil.v3b2_controller.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=b"[]\n", stderr=b""),
        ) as boundary:
            SubprocessCommandRunner().run(command)
        child = boundary.call_args.kwargs["env"]
        self.assertEqual(set(child) & set(poison), set())

    @v4_future
    def test_envoy_quiesce_rejects_container_incarnation_change(self) -> None:
        self.runner.swap_envoy_container_after_drain = True
        with self.assertRaisesRegex(ControllerError, "envoy_quiesce_identity_invalid"):
            self.controller.request_free()
        self.assertTrue(self.controller.owned_absence_proven)

    @v4_future
    def test_separate_process_can_continue_a_preflight_only_journal_into_request_free(self) -> None:
        self.controller.preflight()
        resumed = V3B2Controller(self.paths, self.runner)
        result = resumed.request_free()
        self.assertEqual(result["instructions_sent"], 0)
        self.assertTrue(resumed.owned_absence_proven)

    @v4_future
    def test_request_free_rejects_any_application_record_but_still_tears_down(self) -> None:
        self.runner.inject_application_record = True
        with self.assertRaisesRegex(ControllerError, "source_producer_invalid"):
            self.controller.request_free()
        self.assertTrue(self.controller.owned_absence_proven)

    @v4_future
    def test_down_resumes_bound_runtime_without_current_context_or_discovery_selected_delete(self) -> None:
        self.controller.up()
        resumed = V3B2Controller(self.paths, self.runner)
        result = resumed.down()
        self.assertTrue(result["owned_teardown"])
        self.assertTrue(resumed.owned_absence_proven)
        for command in self.runner.commands:
            if command.mutating and command.argv[0] == "kind":
                self.assertIn("kil-v3-lab", command.argv)
                if command.argv[1:3] != ("load", "docker-image"):
                    self.assertIn(str(resumed.kubeconfig), command.argv)
            self.assertNotIn("current-context", command.argv)

    @v4_future
    def test_nominal_persists_intent_before_each_single_attach(self) -> None:
        bundle = self.controller.nominal()
        self.assertEqual(self.runner.attach_count, 3)
        self.assertEqual(self.runner.cancel_attach_count, 0)
        events = self.controller.events
        for track in TRACKS:
            intent = next(index for index, event in enumerate(events) if event[0] == "request_intent" and event[1]["track"] == track)
            attach = next(index for index, event in enumerate(events) if event[0] == "kubectl_attach" and event[1]["track"] == track)
            self.assertLess(intent, attach)
        self.assertEqual(bundle.result_tuple, (("permit", 200, 1), ("permit", 200, 1), ("deny", 403, 0)))
        self.assertTrue(self.controller.owned_absence_proven)
        self.assertIsNotNone(self.controller.published_path)
        verified = verify_bundle(self.controller.published_path)
        self.assertEqual(verified.result_class, "intermediate_provisional_kind_calico_nominal")

    @v4_future
    def test_recover_attests_successful_profile_start_without_replaying_mutation(self) -> None:
        import kil.v3b2_controller as module

        original = module.append_event
        failed = False

        def fail_completion(path, event, details):
            nonlocal failed
            if event == "profile_start_complete" and not failed:
                failed = True
                raise OSError("injected persistence failure")
            return original(path, event, details)

        with patch.object(module, "append_event", side_effect=fail_completion):
            with self.assertRaises(OSError):
                self.controller.up()
        resumed = V3B2Controller(self.paths, self.runner)
        self.assertTrue(resumed.owned_absence_proven)
        result = resumed.recover()
        starts = [command for command in self.runner.commands if command.argv[:2] == ("colima", "start")]
        self.assertEqual(len(starts), 1)
        self.assertIsNone(result["completed"])
        self.assertFalse(any("attach" in command.argv and command.stdin for command in self.runner.commands))

    @v4_future
    def test_recover_attests_successful_cluster_create_without_replaying_create(self) -> None:
        import kil.v3b2_controller as module

        original = module.append_event
        failed = False

        def fail_completion(path, event, details):
            nonlocal failed
            if event == "cluster_create_complete" and not failed:
                failed = True
                raise OSError("injected persistence failure")
            return original(path, event, details)

        with patch.object(module, "append_event", side_effect=fail_completion):
            with self.assertRaises(OSError):
                self.controller.up()
        resumed = V3B2Controller(self.paths, self.runner)
        self.assertTrue(resumed.owned_absence_proven)
        result = resumed.recover()
        creates = [command for command in self.runner.commands if command.argv[:3] == ("kind", "create", "cluster")]
        self.assertEqual(len(creates), 1)
        self.assertIsNone(result["completed"])
        self.assertFalse(any("attach" in command.argv and command.stdin for command in self.runner.commands))

    @v4_future
    def test_recover_driver_cancel_completion_crash_attests_terminal_without_replaying_eof(self) -> None:
        import kil.v3b2_controller as module

        self.controller._used_mode = "request-free"
        self.controller.preflight()
        self.controller._select_mode("request-free")
        self.controller.up()
        self.controller._start_driver(TRACKS[0])
        original = module.append_event
        failed = False

        def fail_completion(path, event, details):
            nonlocal failed
            if event == "driver_cancel_complete" and not failed:
                failed = True
                raise OSError("injected persistence failure")
            return original(path, event, details)

        with patch.object(module, "append_event", side_effect=fail_completion):
            with self.assertRaises(OSError):
                self.controller._cancel_drivers()
        self.assertEqual(self.runner.cancel_attach_count, 1)
        resumed = V3B2Controller(self.paths, self.runner)
        result = resumed.recover()
        self.assertEqual(result["completed"], "driver_cancel")
        self.assertEqual(self.runner.cancel_attach_count, 1)

    @v4_future
    def test_every_request_free_completion_persistence_boundary_recovers_without_request(self) -> None:
        import kil.v3b2_controller as module

        families = (
            "image_import", "image_load", "calico_apply", "application_apply", "readiness", "driver_start",
            "driver_cancel", "envoy_quiesce", "evidence_freeze", "cluster_delete",
            "cluster_absence_proof", "profile_stop", "profile_delete",
            "profile_absence_proof", "foreign_snapshot_comparison", "publication",
        )
        for index, family in enumerate(families):
            with self.subTest(family=family):
                if index:
                    self.tearDown()
                    self.setUp()
                original = module.append_event
                failed = False

                def fail_completion(path, event, details):
                    nonlocal failed
                    if event == family + "_complete" and not failed:
                        failed = True
                        raise OSError("injected persistence failure")
                    return original(path, event, details)

                with patch.object(module, "append_event", side_effect=fail_completion):
                    with self.assertRaises(OSError):
                        self.controller.request_free()
                resumed = V3B2Controller(self.paths, self.runner)
                self.assertTrue(resumed.owned_absence_proven)
                result = resumed.recover()
                if family == "publication":
                    self.assertEqual(result["completed"], "publication")
                self.assertFalse(any("attach" in command.argv and command.stdin for command in self.runner.commands))
                for command in self.runner.commands:
                    if command.mutating and command.argv[0] in {"kind", "colima"}:
                        self.assertIn("kil-v3-lab", command.argv)

    @v4_future
    def test_request_result_persistence_failure_recovers_by_freezing_never_replay(self) -> None:
        import kil.v3b2_controller as module

        original = module.append_event
        failed = False

        def fail_result(path, event, details):
            nonlocal failed
            if event == "request_result" and not failed:
                failed = True
                raise OSError("injected persistence failure")
            return original(path, event, details)

        with patch.object(module, "append_event", side_effect=fail_result):
            with self.assertRaises(OSError):
                self.controller.nominal()
        self.assertEqual(self.runner.attach_count, 1)
        resumed = V3B2Controller(self.paths, self.runner)
        self.assertTrue(resumed.owned_absence_proven)
        result = resumed.recover()
        self.assertIsNone(result["completed"])
        self.assertEqual(self.runner.attach_count, 1)

    @v4_future
    def test_post_intent_failure_cancels_later_drivers_and_never_retries(self) -> None:
        self.runner.fail_track = TRACKS[0]
        with self.assertRaises(ControllerError):
            self.controller.nominal()
        self.assertEqual(self.runner.attach_count, 1)
        self.assertTrue(self.controller.owned_absence_proven)
        attached = [event[1]["track"] for event in self.controller.events if event[0] == "kubectl_attach"]
        self.assertEqual(attached, [TRACKS[0]])

    def test_cli_exposes_only_fixed_commands_and_view_bundle(self) -> None:
        cli_path = Path(__file__).resolve().parents[1] / "tools/v3b2_kind_calico.py"
        spec = importlib.util.spec_from_file_location("v3b2_kind_calico_cli", cli_path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        parser = module.make_parser()
        for name in ("preflight", "up", "request-free", "nominal", "down", "recover"):
            self.assertEqual(parser.parse_args([name]).command, name)
        viewed = parser.parse_args(["view", "--bundle", "/tmp/public-bundle"])
        self.assertEqual(viewed.bundle, Path("/tmp/public-bundle"))
        with self.assertRaises(SystemExit):
            parser.parse_args(["up", "--profile", "foreign"])


if __name__ == "__main__":
    unittest.main()
