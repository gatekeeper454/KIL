from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import shutil
import tempfile
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
from kil.v3b2_journal import Command, load_journal
from kil.v3b2_contracts import TRACKS
from kil.v3b2_evidence import verify_bundle
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_manifests import WorkloadIdentity, render_objects


HEX64 = "a" * 64
SOURCE_COMMIT = "d" * 40
NOMINAL_REQUEST_ID = "v3b1-central-request"


def raw_runtime_inventory() -> str:
    from tests.test_v3b2_inventory import snapshot

    root = Path(__file__).resolve().parents[1]
    profile = V3B2Profile.load(root / "deploy/kind/v3b2-profile.json")
    kil_digest = "45a167d79b92f352af05a3e9cb8a9df8e972e38ab23d04ca692053e2eaf63649"
    envoy_digest = "57e14a549d7bd43c8d3f6d03e8cfa653e037d4b38e133acd9b54f38c524401b4"
    workload = WorkloadIdentity(
        "v3b2-" + "1" * 64, "sha256:" + kil_digest,
        "docker.io/envoyproxy/envoy@sha256:" + envoy_digest,
    )
    snap = snapshot()
    identities = {(item.api_version, item.kind, item.namespace, item.name): item for item in snap.objects}
    rendered = json.loads(render_objects(profile, workload))["items"]
    items: list[dict[str, object]] = []
    for item in rendered:
        key = (item["apiVersion"], item["kind"], item["metadata"].get("namespace", ""), item["metadata"]["name"])
        identity = identities[key]
        item["metadata"]["uid"] = identity.uid
        item["metadata"]["resourceVersion"] = identity.resource_version
        if item["kind"] == "Pod":
            image = "kil.local/kil-v3b2:sha256-" + kil_digest
            item["status"] = {"conditions": [{"type": "Ready", "status": "True"}], "containerStatuses": [{"name": "driver", "image": image, "imageID": "docker-pullable://fixture@sha256:" + kil_digest, "containerID": "containerd://" + "1" * 64}]}
        items.append(item)
    for key in (("v1", "Namespace", "", "kube-system"), ("apps/v1", "DaemonSet", "kube-system", "calico-node"), ("apps/v1", "Deployment", "kube-system", "calico-kube-controllers")):
        identity = identities[key]
        status = ({"desiredNumberScheduled": 1, "numberReady": 1} if key[1] == "DaemonSet" else {"replicas": 1, "readyReplicas": 1}) if key[1] != "Namespace" else None
        value = {"apiVersion": key[0], "kind": key[1], "metadata": {"namespace": key[2], "name": key[3], "uid": identity.uid, "resourceVersion": identity.resource_version}}
        if status is not None:
            value["status"] = status
        items.append(value)
    for name in ("default", "kube-node-lease", "kube-public", "local-path-storage"):
        items.append({"apiVersion": "v1", "kind": "Namespace", "metadata": {"namespace": "", "name": name, "uid": "uid-" + name, "resourceVersion": "1"}})
    calico = json.loads((root / "deploy/kind/calico-v3.32.0.objects.json").read_bytes())
    for item in calico["items"]:
        if item["kind"] not in {"ServiceAccount", "ConfigMap"}:
            continue
        key = (item["apiVersion"], item["kind"], item["metadata"].get("namespace", ""), item["metadata"]["name"])
        identity = identities[key]
        item["metadata"].update(uid=identity.uid, resourceVersion=identity.resource_version)
        items.append(item)
    grouped: dict[tuple[str, str], list[object]] = {}
    for image in snap.pod_images:
        if image.container == "driver":
            continue
        digest = envoy_digest if image.container == "envoy" else kil_digest if image.image_role == "workload" else image.image.rsplit(":", 1)[1]
        requested = "docker.io/envoyproxy/envoy@sha256:" + digest if image.container == "envoy" else "kil.local/kil-v3b2:sha256-" + digest if image.image_role == "workload" else image.image
        row = {"name": image.container, "image": requested, "imageID": "docker-pullable://fixture@sha256:" + digest, "containerID": "containerd://" + __import__("hashlib").sha256((image.namespace + image.pod + image.container).encode()).hexdigest()}
        grouped.setdefault((image.namespace, image.pod), []).append((image.container_type, row, image.uid, image.resource_version))
    for (namespace, pod), rows in grouped.items():
        items.append({"apiVersion": "v1", "kind": "Pod", "metadata": {"namespace": namespace, "name": pod, "uid": rows[0][2], "resourceVersion": rows[0][3]}, "status": {"conditions": [{"type": "Ready", "status": "True"}], "initContainerStatuses": [row for placement, row, _uid, _rv in rows if placement == "init"], "containerStatuses": [row for placement, row, _uid, _rv in rows if placement == "regular"]}})
    for endpoint in snap.endpoints:
        items.append({"apiVersion": "v1", "kind": "Endpoints", "metadata": {"namespace": endpoint.namespace, "name": endpoint.service, "uid": "uid-endpoint-" + endpoint.namespace + endpoint.service, "resourceVersion": "30"}, "subsets": [{"addresses": [{"ip": address} for address in endpoint.addresses], "ports": [{"name": endpoint.port_name, "protocol": endpoint.protocol, "port": endpoint.port}]}]})
        pod = next(item for item in items if item["kind"] == "Pod" and item["metadata"].get("namespace") == endpoint.namespace and item["metadata"]["name"].startswith(endpoint.service + "-"))
        items.append({
            "apiVersion": "discovery.k8s.io/v1", "kind": "EndpointSlice",
            "metadata": {"namespace": endpoint.namespace, "name": endpoint.service + "-abcde",
                         "uid": "uid-slice-" + endpoint.namespace + endpoint.service,
                         "resourceVersion": "31", "labels": {"kubernetes.io/service-name": endpoint.service}},
            "addressType": "IPv4", "ports": [{"name": endpoint.port_name, "protocol": endpoint.protocol, "port": endpoint.port}],
            "endpoints": [{"addresses": list(endpoint.addresses), "conditions": {"ready": True},
                           "targetRef": {"kind": "Pod", "name": pod["metadata"]["name"],
                                         "namespace": endpoint.namespace, "uid": pod["metadata"]["uid"]}}],
        })
    uid_map: dict[str, str] = {}
    rv_map: dict[str, str] = {}
    for item in items:
        metadata = item["metadata"]
        old_uid, old_rv = str(metadata["uid"]), str(metadata["resourceVersion"])
        if old_uid not in uid_map:
            uid_map[old_uid] = old_uid if old_uid == "11111111-1111-4111-8111-111111111111" else f"00000000-0000-4000-8000-{len(uid_map) + 1:012x}"
        if old_rv not in rv_map:
            rv_map[old_rv] = str(len(rv_map) + 1)
        metadata["uid"], metadata["resourceVersion"] = uid_map[old_uid], rv_map[old_rv]
    for item in items:
        if item["kind"] == "EndpointSlice":
            for endpoint in item["endpoints"]:
                endpoint["targetRef"]["uid"] = uid_map[endpoint["targetRef"]["uid"]]
    return json.dumps({"apiVersion": "v1", "kind": "List", "items": items}, sort_keys=True, separators=(",", ":")) + "\n"


class FakeRunner:
    def __init__(self, profiles: list[dict[str, object]] | None = None) -> None:
        self.profiles = [] if profiles is None else profiles
        self.commands = []
        self.attach_count = 0
        self.cancel_attach_count = 0
        self.attached_tracks: set[str] = set()
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
        self.canceled_drivers: set[str] = set()
        self.cancel_exit_code = 0
        self.swap_envoy_container_after_drain = False
        self.run_id = "v3b2-" + "1" * 64

    def run(self, command):
        self.commands.append(command)
        argv = command.argv
        if command.stdin and argv[-3:] == ("apply", "-f", "-"):
            self.run_id = json.loads(command.stdin)["items"][0]["metadata"]["annotations"]["kil.dev/run-id"]
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
            return CommandResult(0, json.dumps([{
                "Id": "a" * 64,
                "Name": "/kil-v3-lab-control-plane",
                "Image": "sha256:" + "9" * 64,
                "Config": {"Image": "kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5",
                           "Labels": {"io.x-k8s.kind.cluster": "kil-v3-lab", "io.x-k8s.kind.role": "control-plane"}},
            }]) + "\n", "")
        if argv[:3] == ("docker", "container", "ls"):
            payload = json.dumps({"ID": "a" * 64, "Names": "kil-v3-lab-control-plane",
                "Image": "kindest/node:v1.36.1", "Labels": "io.x-k8s.kind.cluster=kil-v3-lab,io.x-k8s.kind.role=control-plane"}) + "\n" if self.cluster_exists else ""
            return CommandResult(0, payload, "")
        if argv[:3] == ("docker", "image", "inspect"):
            image = argv[3]
            digest = image.rsplit(":", 1)[1].removeprefix("sha256-")
            if self.wrong_image_id:
                digest = "0" * 64
            return CommandResult(0, json.dumps([{"Id": "sha256:" + digest, "RepoTags": [image], "RepoDigests": [image]}]) + "\n", "")
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
            pod = next(item for item in json.loads(raw_runtime_inventory())["items"] if item["kind"] == "Pod" and item["metadata"].get("namespace") == namespace and item["metadata"]["name"] == pod_name)
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
            inventory = json.loads(raw_runtime_inventory())["items"]
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
        if any(item.startswith("namespaces,pods,services") for item in argv):
            return CommandResult(0, raw_runtime_inventory(), "")
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
        archive = b"verified-test-oci-archive"
        (root / ".tools/v3b2-input").mkdir()
        (root / ".tools/v3b2-input/kil-image.tar").write_bytes(archive)
        import kil.v3b2_controller as controller_module
        archive_patch = patch.object(
            controller_module, "_archive_digest",
            return_value="07c12f338c7d764812ef6271ec8942f0535d05019288f4df1e1b54f6cd75e4b6",
        )
        archive_patch.start()
        self.addCleanup(archive_patch.stop)
        self.paths = ControllerPaths(
            repository=root,
            profile=root / "deploy/kind/v3b2-profile.json",
            tools=root / ".tools/bin",
            private=root / ".tools/v3b2-private",
            public=root / "artifacts/generated/v3b2-kind-calico",
        )
        self.runner = FakeRunner()
        self.controller = V3B2Controller(self.paths, self.runner)
        self.runner.profile_paths = self.controller.profile_paths

    def tearDown(self) -> None:
        self.temporary.cleanup()

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

    def test_import_uses_preflight_verified_archive_bytes_not_reopened_path(self) -> None:
        archive_path = self.paths.tools.parent / "v3b2-input/kil-image.tar"
        verified = archive_path.read_bytes()
        self.controller.preflight()
        archive_path.write_bytes(b"replacement")
        self.controller.up()
        load = next(command for command in self.runner.commands if command.argv == ("docker", "load"))
        self.assertEqual(load.stdin, verified)

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

    def test_envoy_quiesce_rejects_container_incarnation_change(self) -> None:
        self.runner.swap_envoy_container_after_drain = True
        with self.assertRaisesRegex(ControllerError, "envoy_quiesce_identity_invalid"):
            self.controller.request_free()
        self.assertTrue(self.controller.owned_absence_proven)

    def test_separate_process_can_continue_a_preflight_only_journal_into_request_free(self) -> None:
        self.controller.preflight()
        resumed = V3B2Controller(self.paths, self.runner)
        result = resumed.request_free()
        self.assertEqual(result["instructions_sent"], 0)
        self.assertTrue(resumed.owned_absence_proven)

    def test_request_free_rejects_any_application_record_but_still_tears_down(self) -> None:
        self.runner.inject_application_record = True
        with self.assertRaisesRegex(ControllerError, "source_producer_invalid"):
            self.controller.request_free()
        self.assertTrue(self.controller.owned_absence_proven)

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
