from copy import copy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import re
import unittest

from kil.canonical import canonical_json
import kil.v3b2_inventory as inventory
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_manifests import expected_object_keys
from kil.v3b2_inventory import (
    EndpointIdentity,
    ExpectedInventory,
    InventoryError,
    InventorySnapshot,
    ObjectIdentity,
    PodImageIdentity,
    PolicyEdge,
    RuntimePodIdentity,
    parse_runtime_pod_identity,
    parse_ready_endpoint_slice,
    parse_calico_runtime_workload,
    parse_runtime_inventory,
    parse_kubectl_list,
    stable_source,
    validate_inventory,
)


KUBE_SYSTEM_UID = "11111111-1111-4111-8111-111111111111"
NODE_ID = "a" * 64
DOCKER_HOST = "unix:///Users/test/.colima/kil-v3-lab/docker.sock"
ROOT = Path(__file__).resolve().parents[1]
FIXED_PROFILE = V3B2Profile.load(ROOT / "deploy/kind/v3b2-profile.json")
PROFILE_CALICO_IMAGES = dict(FIXED_PROFILE.calico_images)
CALICO_CNI = PROFILE_CALICO_IMAGES["cni"]
CALICO_NODE = PROFILE_CALICO_IMAGES["node"]
CALICO_CONTROLLERS = PROFILE_CALICO_IMAGES["kube_controllers"]
KIL_TARGET = "sha256:45a167d79b92f352af05a3e9cb8a9df8e972e38ab23d04ca692053e2eaf63649"
KIL_CONFIG = "sha256:f21285be21c8f691b9b60b7e38bb309564a5cc238512c7455eb7759f4d922ddb"
KIL_IMAGE = "kil.local/kil-v3b2:sha256-" + KIL_TARGET[7:]
KIL_IMAGE_ID = "kil.local/kil-v3b2@" + KIL_TARGET
ENVOY_IMAGE = "docker.io/envoyproxy/envoy@sha256:57e14a549d7bd43c8d3f6d03e8cfa653e037d4b38e133acd9b54f38c524401b4"
ENVOY_IMAGE_ID = ENVOY_IMAGE


class WorkloadImageMembershipTest(unittest.TestCase):
    def test_config_and_repository_refs_are_finite_members_not_provenance(self):
        for container, image, refs in (('authz', KIL_IMAGE, (KIL_CONFIG, KIL_IMAGE_ID)),
                                       ('envoy', ENVOY_IMAGE, (ENVOY_IMAGE_ID,))):
            for ref in refs:
                row = PodImageIdentity('workload', 'regular', 'kil-v3-baseline', container + '-a',
                                       container, 'uid', '1', image, ref, True)
                self.assertEqual(replace(row), row)

    def test_unknown_targets_and_cross_domain_pairs_reject(self):
        unknown = 'f' * 64
        for container, image, ref in (
            ('authz', 'kil.local/kil-v3b2:sha256-' + unknown, 'docker-pullable://kil.local/kil-v3b2@sha256:' + unknown),
            ('authz', KIL_IMAGE, KIL_TARGET), ('authz', KIL_IMAGE, ENVOY_IMAGE),
            ('authz', KIL_IMAGE, 'foreign/repo@' + KIL_TARGET),
            ('envoy', ENVOY_IMAGE, KIL_CONFIG), ('unknown', KIL_IMAGE, KIL_CONFIG),
            ('authz', KIL_CONFIG, KIL_CONFIG)):
            with self.subTest(container=container, image=image, ref=ref), self.assertRaises(InventoryError):
                PodImageIdentity('workload', 'regular', 'kil-v3-baseline', 'pod', container,
                                 'uid', '1', image, ref, True)


def obj(kind: str, namespace: str, name: str, suffix: str) -> ObjectIdentity:
    api_version = "apps/v1" if kind in {"Deployment", "DaemonSet"} else "v1"
    if kind == "NetworkPolicy":
        api_version = "networking.k8s.io/v1"
    return ObjectIdentity(api_version, kind, namespace, name, f"uid-{suffix}", f"rv-{suffix}")


def policies() -> tuple[PolicyEdge, ...]:
    records = []
    for namespace in ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed"):
        records.extend((
            PolicyEdge(namespace, ("driver",), namespace, ("envoy",), (("TCP", 8080),)),
            PolicyEdge(namespace, ("envoy",), namespace, ("authz",), (("TCP", 8080),)),
            PolicyEdge(namespace, ("envoy",), namespace, ("target",), (("TCP", 8080),)),
            PolicyEdge(namespace, ("driver", "envoy"), "kube-system", ("kube-dns",), (("TCP", 53), ("UDP", 53))),
        ))
    return tuple(sorted(records))


def snapshot() -> InventorySnapshot:
    profile = V3B2Profile.load(ROOT / "deploy/kind/v3b2-profile.json")
    object_records = [
        ObjectIdentity(api, kind, namespace, name, f"uid-{index}", f"rv-{index}")
        for index, (api, kind, namespace, name) in enumerate(
            expected_object_keys(profile), start=1,
        )
    ]
    object_records.extend((
        ObjectIdentity("v1", "Namespace", "", "kube-system", KUBE_SYSTEM_UID, "system-1"),
        ObjectIdentity("apps/v1", "DaemonSet", "kube-system", "calico-node", "uid-calico-node", "system-2"),
        ObjectIdentity("apps/v1", "Deployment", "kube-system", "calico-kube-controllers", "uid-calico-controller", "system-3"),
    ))
    for index, (kind, name) in enumerate((("ServiceAccount", "calico-node"), ("ServiceAccount", "calico-cni-plugin"),
                                         ("ServiceAccount", "calico-kube-controllers"), ("ConfigMap", "calico-config")), start=4):
        object_records.append(ObjectIdentity("v1", kind, "kube-system", name, "uid-system-" + str(index), "system-" + str(index)))
    objects = tuple(sorted(object_records))
    image_records = [
        PodImageIdentity("calico-cni", "init", "kube-system", "calico-node-a", "upgrade-ipam", "pod-calico", "201", CALICO_CNI, "docker-pullable://quay.io/calico/cni@sha256:" + CALICO_CNI.rsplit(":", 1)[1], True),
        PodImageIdentity("calico-cni", "init", "kube-system", "calico-node-a", "install-cni", "pod-calico", "201", CALICO_CNI, "docker-pullable://quay.io/calico/cni@sha256:" + CALICO_CNI.rsplit(":", 1)[1], True),
        PodImageIdentity("calico-node", "init", "kube-system", "calico-node-a", "ebpf-bootstrap", "pod-calico", "201", CALICO_NODE, "docker-pullable://quay.io/calico/node@sha256:" + CALICO_NODE.rsplit(":", 1)[1], True),
        PodImageIdentity("calico-node", "regular", "kube-system", "calico-node-a", "calico-node", "pod-calico", "201", CALICO_NODE, "docker-pullable://quay.io/calico/node@sha256:" + CALICO_NODE.rsplit(":", 1)[1], True),
        PodImageIdentity("calico-kube-controllers", "regular", "kube-system", "calico-kube-controllers-a", "calico-kube-controllers", "pod-controller", "202", CALICO_CONTROLLERS, "docker-pullable://quay.io/calico/kube-controllers@sha256:" + CALICO_CONTROLLERS.rsplit(":", 1)[1], True),
    ]
    for namespace_index, namespace in enumerate(
        ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed"), start=1,
    ):
        for role_index, role in enumerate(("driver", "envoy", "authz", "target"), start=1):
            pod_name = "driver" if role == "driver" else f"{role}-a"
            image_records.append(PodImageIdentity(
                "workload", "regular", namespace, pod_name, role,
                f"pod-{namespace_index}-{role}", f"rv-pod-{namespace_index}-{role}",
                ENVOY_IMAGE if role == "envoy" else KIL_IMAGE,
                ENVOY_IMAGE_ID if role == "envoy" else KIL_IMAGE_ID,
                True,
            ))
    images = tuple(sorted(
        replace(item, container_id="containerd://" + f"{index:064x}")
        for index, item in enumerate(image_records, start=1)
    ))
    endpoints = tuple(sorted(
        EndpointIdentity(
            "Endpoints", service, namespace, service,
            (f"10.244.{namespace_index}.{service_index + 10}",),
            "http", "TCP", 8080,
        )
        for namespace_index, namespace in enumerate(
            ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed"), start=1,
        )
        for service_index, service in enumerate(("envoy", "authz", "target"), start=1)
    ))
    return InventorySnapshot(
        KUBE_SYSTEM_UID,
        NODE_ID,
        DOCKER_HOST,
        ("default", "kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed", "kube-node-lease", "kube-public", "kube-system", "local-path-storage"),
        objects,
        images,
        endpoints,
        policies(),
        1,
        1,
        1,
        1,
    )


def tampered(record, **changes):
    changed = copy(record)
    for name, value in changes.items():
        object.__setattr__(changed, name, value)
    return changed


def raw_list(items: list[dict]) -> bytes:
    return (canonical_json({
        "apiVersion": "v1", "kind": "List",
        "metadata": {"resourceVersion": ""}, "items": items,
    }) + "\n").encode()


class StrSubclass(str):
    pass


class TupleSubclass(tuple):
    pass


class V3B2InventoryTest(unittest.TestCase):
    def test_fixed_inventory_requires_all_calico_accounts_and_configuration(self):
        required = {("v1", "ServiceAccount", "kube-system", name) for name in ("calico-node", "calico-cni-plugin", "calico-kube-controllers")}
        required.add(("v1", "ConfigMap", "kube-system", "calico-config"))
        self.assertTrue(required.issubset(inventory._EXPECTED_OBJECT_KEYS), "pinned Calico objects are missing from expectations")

    def test_ready_endpoint_slice_binds_one_ready_pod_uid_and_exact_port(self) -> None:
        value = {
            "apiVersion": "discovery.k8s.io/v1", "kind": "EndpointSlice",
            "metadata": {"name": "envoy-abcde", "namespace": "kil-v3-baseline",
                         "labels": {"kubernetes.io/service-name": "envoy"}},
            "addressType": "IPv4",
            "ports": [{"name": "http", "port": 8080, "protocol": "TCP"}],
            "endpoints": [{"addresses": ["10.244.0.10"], "conditions": {"ready": True},
                           "targetRef": {"kind": "Pod", "name": "envoy-abc", "namespace": "kil-v3-baseline", "uid": "pod-uid"}}],
        }
        endpoint, uid = parse_ready_endpoint_slice(
            json.dumps(value, indent=2).encode(),
            expected_namespace="kil-v3-baseline", expected_service="envoy",
        )
        self.assertEqual((endpoint.source_kind, endpoint.port, uid), ("EndpointSlice", 8080, "pod-uid"))
        value["endpoints"][0]["conditions"]["ready"] = False
        with self.assertRaises(InventoryError):
            parse_ready_endpoint_slice(
                json.dumps(value).encode(), expected_namespace="kil-v3-baseline",
                expected_service="envoy",
            )

    def test_runtime_driver_pod_identity_is_strict_and_image_bound(self) -> None:
        legacy_image_id = 'docker-pullable://' + KIL_IMAGE_ID
        value = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "driver", "namespace": "kil-v3-baseline",
                "resourceVersion": "17", "uid": "driver-uid",
            },
            "status": {
                "conditions": [{"status": "True", "type": "Ready"}],
                "containerStatuses": [{
                    "image": KIL_IMAGE, "imageID": legacy_image_id,
                    "containerID": "containerd://" + "1" * 64,
                    "name": "driver", "ready": True,
                }],
            },
        }
        payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        parsed = parse_runtime_pod_identity(
            payload,
            expected_namespace="kil-v3-baseline",
            expected_pod="driver",
            expected_container="driver",
            expected_image=KIL_IMAGE,
        )
        self.assertEqual(parsed, RuntimePodIdentity(
            "kil-v3-baseline", "driver", "driver-uid", "17", "driver",
            KIL_IMAGE, legacy_image_id, True, "containerd://" + "1" * 64,
        ))
        value["metadata"]["managedFields"] = [{"manager": "kubelet"}]
        value["spec"] = {"nodeName": "kil-v3-lab-control-plane"}
        value["status"]["containerStatuses"][0]["state"] = {
            "terminated": {"exitCode": 0, "finishedAt": "2026-09-07T00:00:00Z"},
        }
        value["status"]["containerStatuses"][0]["ready"] = False
        value["status"]["conditions"][0]["status"] = "False"
        terminal = parse_runtime_pod_identity(
            json.dumps(value, indent=2).encode(),
            expected_namespace="kil-v3-baseline", expected_pod="driver",
            expected_container="driver", expected_image=KIL_IMAGE,
            require_ready=False,
        )
        self.assertEqual(terminal.terminated_exit_code, 0)
        value["status"]["containerStatuses"][0]["image"] = "kil.local/kil-v3b2:latest"
        bad = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        with self.assertRaises(InventoryError):
            parse_runtime_pod_identity(
                bad, expected_namespace="kil-v3-baseline", expected_pod="driver",
                expected_container="driver", expected_image=KIL_IMAGE,
            )

    def test_calico_runtime_workload_requires_exact_ready_pinned_projection(self) -> None:
        item = {
            "apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"name": "calico-kube-controllers", "namespace": "kube-system", "resourceVersion": "2", "uid": "uid-controller"},
            "spec": {"containers": [{"image": CALICO_CONTROLLERS, "name": "calico-kube-controllers"}], "initContainers": []},
            "status": {"readyReplicas": 1, "replicas": 1},
        }
        payload = (json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n").encode()
        desired, ready, images = parse_calico_runtime_workload(payload, "Deployment")
        self.assertEqual((desired, ready), (1, 1))
        self.assertEqual(images[0][2], CALICO_CONTROLLERS)
        item["status"]["readyReplicas"] = 0
        bad = (json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n").encode()
        with self.assertRaises(InventoryError):
            parse_calico_runtime_workload(bad, "Deployment")

    def test_composite_runtime_parser_closes_the_entire_raw_object_set(self) -> None:
        from kil.v3b2_manifests import WorkloadIdentity
        from tests.test_v3b2_controller import raw_runtime_inventory

        kil = "45a167d79b92f352af05a3e9cb8a9df8e972e38ab23d04ca692053e2eaf63649"
        envoy = "57e14a549d7bd43c8d3f6d03e8cfa653e037d4b38e133acd9b54f38c524401b4"
        workload = WorkloadIdentity(
            "v3b2-" + "1" * 64, "sha256:" + kil,
            "docker.io/envoyproxy/envoy@sha256:" + envoy,
        )
        payload = raw_runtime_inventory().encode()
        raw_value = json.loads(payload)
        platform = (
            ("v1", "Pod", "kube-system", "kube-apiserver-kil-v3-lab-control-plane"),
            ("v1", "Pod", "kube-system", "coredns-7db6d8ff4d-abcde"),
            ("v1", "Pod", "local-path-storage", "local-path-provisioner-abcde"),
            ("v1", "Service", "default", "kubernetes"),
            ("v1", "Service", "kube-system", "kube-dns"),
            ("v1", "Endpoints", "default", "kubernetes"),
            ("discovery.k8s.io/v1", "EndpointSlice", "kube-system", "kube-dns-abcde"),
            ("v1", "ServiceAccount", "default", "default"),
            ("v1", "ConfigMap", "kil-v3-baseline", "kube-root-ca.crt"),
            ("apps/v1", "Deployment", "kube-system", "coredns"),
            ("apps/v1", "DaemonSet", "kube-system", "kube-proxy"),
        )
        for index, (api_version, kind, namespace, name) in enumerate(platform):
            raw_value["items"].append({
                "apiVersion": api_version, "kind": kind,
                "metadata": {"name": name, "namespace": namespace,
                             "resourceVersion": str(900 + index),
                             "uid": f"33333333-3333-4333-8333-{index:012x}"},
                "spec": {}, "status": {},
            })
        # Legacy pure parser fixture: fixed public members, not production
        # source-backed containerd status/provenance authority.
        for item in raw_value['items']:
            if item['kind'] == 'Pod' and item['metadata'].get('namespace', '').startswith('kil-'):
                for row in item.get('status', {}).get('containerStatuses', []):
                    row['imageID'] = ENVOY_IMAGE_ID if row['name'] == 'envoy' else KIL_IMAGE_ID
        payload = json.dumps(raw_value, indent=2).encode()
        parsed = parse_runtime_inventory(
            payload, profile=FIXED_PROFILE, workload=workload,
            node_container_id=NODE_ID, docker_host=DOCKER_HOST,
        )
        self.assertEqual((len(parsed.objects), len(parsed.pod_images), len(parsed.endpoints)), (67, 17, 9))
        value = json.loads(payload)
        value["items"].append({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "extra", "namespace": "default", "resourceVersion": "1", "uid": "22222222-2222-4222-8222-222222222222"}})
        extra = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        with self.assertRaisesRegex(InventoryError, "extra"):
            parse_runtime_inventory(
                extra, profile=FIXED_PROFILE, workload=workload,
                node_container_id=NODE_ID, docker_host=DOCKER_HOST,
            )
    def setUp(self) -> None:
        self.snapshot = snapshot()
        self.expected = ExpectedInventory(
            self.snapshot.cluster_incarnation_uid,
            self.snapshot.node_container_id,
            self.snapshot.docker_host,
            self.snapshot.namespaces,
            self.snapshot.objects,
            self.snapshot.pod_images,
            self.snapshot.endpoints,
            self.snapshot.policy_graph,
            self.snapshot.calico_node_desired,
            self.snapshot.calico_node_ready,
            self.snapshot.calico_controller_desired,
            self.snapshot.calico_controller_ready,
        )

    def test_accepts_exact_ready_inventory_and_cluster_binding(self) -> None:
        result = validate_inventory(self.snapshot, self.expected)
        self.assertEqual(result.cluster_incarnation_uid, KUBE_SYSTEM_UID)
        self.assertEqual(result.node_container_id, NODE_ID)
        self.assertEqual(result.policy_graph, self.expected.policy_graph)
        self.assertTrue(result.calico_ready)

    def test_records_are_frozen_slotted_exact_and_nested_immutable(self) -> None:
        records = (
            self.snapshot.objects[0], self.snapshot.pod_images[0],
            self.snapshot.endpoints[0], self.snapshot.policy_graph[0], self.snapshot,
        )
        for record in records:
            with self.subTest(record=type(record).__name__):
                with self.assertRaises((FrozenInstanceError, AttributeError, TypeError)):
                    record.extra = "no"  # type: ignore[attr-defined]
        with self.assertRaises(InventoryError):
            EndpointIdentity("Endpoints", "source", "n", "s", TupleSubclass(("10.0.0.1",)), "http", "TCP", 80)
        with self.assertRaises(InventoryError):
            EndpointIdentity("Endpoints", "source", "n", "s", ("10.0.0.1",), "http", "TCP", True)
        with self.assertRaises(InventoryError):
            ObjectIdentity(StrSubclass("v1"), "Pod", "n", "p", "u", "r")

    def test_parse_kubectl_list_accepts_only_bounded_canonical_duplicate_free_closed_json(self) -> None:
        value = {
            "apiVersion": "v1", "kind": "List", "metadata": {"resourceVersion": ""},
            "items": [
                {"apiVersion": "v1", "kind": "Pod", "metadata": {"namespace": "z", "name": "b", "uid": "u2", "resourceVersion": "2"}},
                {"apiVersion": "v1", "kind": "Pod", "metadata": {"namespace": "a", "name": "a", "uid": "u1", "resourceVersion": "1"}},
            ],
        }
        payload = (canonical_json(value) + "\n").encode()
        parsed = parse_kubectl_list(payload, "Pod")
        self.assertEqual(tuple(record.name for record in parsed), ("a", "b"))
        for broken in (
            json.dumps(value).encode(),
            payload.replace(b'"kind":"List"', b'"kind":"PodList"'),
            payload.replace(b'"metadata":{"resourceVersion":""}', b'"metadata":{"extra":1,"resourceVersion":""}'),
            payload.replace(b'"uid":"u1"', b'"uid":"u1","uid":"duplicate"'),
            payload.replace(b'"name":"a"', b'"extra":1,"name":"a"'),
            payload.replace(b'"name":"a","namespace":"a"', b'"name":"b","namespace":"z"'),
            b"[]\n",
            b"x" * (8 * 1024 * 1024 + 1),
        ):
            with self.subTest(broken=broken[:50]):
                with self.assertRaises(InventoryError):
                    parse_kubectl_list(broken, "Pod")
        with self.assertRaises(InventoryError):
            parse_kubectl_list(payload, StrSubclass("Pod"))

    def test_raw_decoder_totalizes_types_integer_depth_and_eight_mib_bound(self) -> None:
        value = {
            "apiVersion": "v1", "kind": "List", "metadata": {"resourceVersion": ""},
            "items": [{
                "apiVersion": "v1", "kind": "Pod",
                "metadata": {"namespace": "n", "name": "p", "uid": "u", "resourceVersion": "r"},
                "status": {
                    "conditions": [{"type": "Ready", "status": []}],
                    "containerStatuses": [], "initContainerStatuses": [],
                },
            }],
        }
        encoded = lambda item: (json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        with self.assertRaises(InventoryError):
            inventory._parse_pod_image_list(encoded(value))
        huge_integer = encoded({
            "apiVersion": "v1", "kind": "List", "metadata": {"resourceVersion": 0}, "items": [],
        }).replace(b'"resourceVersion":0', b'"resourceVersion":' + b"9" * 5000)
        with self.assertRaises(InventoryError):
            parse_kubectl_list(huge_integer, "Pod")
        deep = []
        cursor = deep
        for _ in range(80):
            child = []
            cursor.append(child)
            cursor = child
        deep_value = {
            "apiVersion": "v1", "kind": "List", "metadata": {"resourceVersion": ""},
            "items": [{"apiVersion": "v1", "kind": "Pod", "metadata": {"namespace": "n", "name": "p", "uid": "u", "resourceVersion": "r"}, "extra": deep}],
        }
        with self.assertRaises(InventoryError):
            parse_kubectl_list(encoded(deep_value), "Pod")
        large_uid = "u" * (1_100_000)
        large_value = {
            "apiVersion": "v1", "kind": "List", "metadata": {"resourceVersion": ""},
            "items": [{"apiVersion": "v1", "kind": "Pod", "metadata": {"namespace": "n", "name": "p", "uid": large_uid, "resourceVersion": "r"}}],
        }
        large_payload = encoded(large_value)
        self.assertGreater(len(large_payload), 1_000_000)
        self.assertEqual(parse_kubectl_list(large_payload, "Pod")[0].uid, large_uid)
        with self.assertRaises(InventoryError):
            parse_kubectl_list(b" " * (8 * 1024 * 1024 + 1), "Pod")

    def test_rejects_extra_namespace_workload_service_endpoint_or_policy(self) -> None:
        mutations = (
            tampered(self.snapshot, namespaces=tuple(sorted((*self.snapshot.namespaces, "foreign-in-cluster")))),
            tampered(self.snapshot, objects=tuple(sorted((*self.snapshot.objects, obj("Deployment", "kil-v3-baseline", "extra", "x"))))),
            tampered(self.snapshot, objects=tuple(sorted((*self.snapshot.objects, obj("Service", "kil-v3-signed", "public", "y"))))),
            tampered(self.snapshot, endpoints=tuple(sorted((*self.snapshot.endpoints, EndpointIdentity("Endpoints", "public", "kil-v3-signed", "public", ("10.244.0.20",), "http", "TCP", 8080))))),
            tampered(
                self.snapshot,
                policy_graph=tuple(sorted((
                    *self.snapshot.policy_graph,
                    PolicyEdge(
                        "kil-v3-local-reduce", ("driver",),
                        "kil-v3-local-reduce", ("target",), (("TCP", 8080),),
                    ),
                ))),
            ),
        )
        for mutated in mutations:
            with self.subTest(field=next(f for f in mutated.__dataclass_fields__ if getattr(mutated, f) != getattr(self.snapshot, f))):
                with self.assertRaises(InventoryError):
                    validate_inventory(mutated, self.expected)

    def test_mirrored_expected_cannot_authorize_extra_fixed_topology_or_workload(self) -> None:
        extra_object = obj("Deployment", "kil-v3-baseline", "extra", "mirrored")
        extra_service = obj("Service", "kil-v3-signed", "public", "mirrored-service")
        extra_workload = PodImageIdentity(
            "workload", "regular", "kil-v3-baseline", "authz-extra", "authz",
            "pod-extra", "rv-extra", KIL_IMAGE, KIL_IMAGE_ID, True,
        )
        for label, field, value in (
            ("deployment", "objects", tuple(sorted((*self.snapshot.objects, extra_object)))),
            ("service", "objects", tuple(sorted((*self.snapshot.objects, extra_service)))),
            ("container", "pod_images", tuple(sorted((*self.snapshot.pod_images, extra_workload)))),
        ):
            current = tampered(self.snapshot, **{field: value})
            expected = tampered(self.expected, **{field: value})
            with self.subTest(label=label):
                with self.assertRaises(InventoryError):
                    validate_inventory(current, expected)

    def test_mirrored_endpoint_service_port_and_address_cannot_expand_topology(self) -> None:
        original = self.snapshot.endpoints[0]
        mutations = (
            replace(original, service="public", source_name="public"),
            replace(original, port_name="metrics", port=9090),
            replace(original, addresses=("not-an-ip",)),
            replace(original, addresses=("192.0.2.10",)),
        )
        for changed in mutations:
            endpoints = tuple(sorted((changed, *self.snapshot.endpoints[1:])))
            current = tampered(self.snapshot, endpoints=endpoints)
            expected = tampered(self.expected, endpoints=endpoints)
            with self.subTest(changed=changed):
                with self.assertRaises(InventoryError):
                    validate_inventory(current, expected)

    def test_rejects_uid_resourceversion_or_image_identity_drift(self) -> None:
        after = self.snapshot
        changed_object = replace(after.objects[1], uid="changed")
        changed_rv = replace(after.objects[1], resource_version="changed")
        changed_image = tampered(
            after.pod_images[0], image_id=after.pod_images[0].image_id[:-1] + "a",
        )
        for mutated in (
            tampered(after, objects=tuple(sorted(changed_object if item == after.objects[1] else item for item in after.objects))),
            tampered(after, objects=tuple(sorted(changed_rv if item == after.objects[1] else item for item in after.objects))),
            tampered(after, pod_images=tuple(sorted((changed_image, *after.pod_images[1:])))),
        ):
            with self.assertRaises(InventoryError):
                stable_source(self.snapshot, mutated)

    def test_rejects_unready_calico_unknown_system_namespace_or_cluster_binding(self) -> None:
        for mutated, message in (
            (replace(self.snapshot, calico_node_ready=0), "Calico"),
            (replace(self.snapshot, calico_controller_ready=0), "Calico"),
            (tampered(self.snapshot, namespaces=tuple(sorted((*self.snapshot.namespaces, "mystery-system")))), "namespace"),
            (tampered(self.snapshot, cluster_incarnation_uid="other"), "cluster_incarnation_uid|kube-system"),
            (tampered(self.snapshot, node_container_id="e" * 63), "node"),
            (tampered(self.snapshot, docker_host="unix:///Users/test/.colima/default/docker.sock"), "kil-v3-lab"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(InventoryError, message):
                    validate_inventory(mutated, self.expected)

    def test_rejects_calico_count_or_pinned_image_drift_and_mutable_image_ids(self) -> None:
        mutable = tampered(self.snapshot.pod_images[0], image="quay.io/calico/node:v3.32.0")
        wrong = tampered(self.snapshot.pod_images[0], image=CALICO_NODE[:-1] + "e")
        no_digest_id = tampered(self.snapshot.pod_images[0], image_id="sha256:" + "b" * 64)
        for mutated in (
            replace(self.snapshot, calico_node_desired=2),
            replace(self.snapshot, calico_controller_desired=2, calico_controller_ready=2),
            tampered(self.snapshot, pod_images=tuple(sorted((mutable, *self.snapshot.pod_images[1:])))),
            tampered(self.snapshot, pod_images=tuple(sorted((wrong, *self.snapshot.pod_images[1:])))),
            tampered(self.snapshot, pod_images=tuple(sorted((no_digest_id, *self.snapshot.pod_images[1:])))),
        ):
            with self.assertRaises(InventoryError):
                validate_inventory(mutated, self.expected)
        two_nodes = replace(self.snapshot, calico_node_desired=2, calico_node_ready=2)
        mirrored = replace(self.expected, calico_node_desired=2, calico_node_ready=2)
        with self.assertRaisesRegex(InventoryError, "Calico"):
            validate_inventory(two_nodes, mirrored)

    def test_policy_graph_is_exact_twelve_edges_including_three_dns_edges(self) -> None:
        graph = self.snapshot.policy_graph
        self.assertEqual(len(graph), 12)
        self.assertEqual(sum(edge.destination_namespace == "kube-system" for edge in graph), 3)
        original = graph[0]
        mutations = (
            replace(original, namespace="kil-v3-signed"),
            replace(original, source_roles=("target",)),
            replace(original, destination_namespace="kil-v3-signed"),
            replace(original, destination_roles=("target",)),
            replace(original, protocol_ports=(("UDP", 8080),)),
            replace(original, protocol_ports=(("TCP", 8081),)),
        )
        for edge in mutations:
            mutated = tampered(self.snapshot, policy_graph=tuple(sorted((edge, *graph[1:]))))
            with self.assertRaises(InventoryError):
                validate_inventory(mutated, self.expected)

    def test_rejects_duplicate_unsorted_unknown_conditions_and_ambiguous_endpoints(self) -> None:
        with self.assertRaises(InventoryError):
            replace(
                self.snapshot,
                objects=self.snapshot.objects + (self.snapshot.objects[0],),
            )
        with self.assertRaises(InventoryError):
            replace(self.snapshot, objects=tuple(reversed(self.snapshot.objects)))
        with self.assertRaises(InventoryError):
            PodImageIdentity("workload", "regular", "n", "p", "c", "u", "r", KIL_IMAGE, KIL_IMAGE_ID, "Unknown")  # type: ignore[arg-type]
        with self.assertRaises(InventoryError):
            EndpointIdentity("Endpoints", "source", "n", "s", ("10.0.0.1", "10.0.0.1"), "http", "TCP", 80)
        with self.assertRaises(InventoryError):
            EndpointIdentity("Endpoints", "source", "n", "s", ("10.0.0.2", "10.0.0.1"), "http", "TCP", 80)

    def test_raw_pod_projection_closes_conditions_and_container_image_identity(self) -> None:
        item = {
            "apiVersion": "v1", "kind": "Pod",
            "metadata": {"namespace": "kube-system", "name": "calico-node-a", "uid": "pod-calico", "resourceVersion": "201"},
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "containerStatuses": [{"name": "calico-node", "image": CALICO_NODE, "imageID": "docker-pullable://quay.io/calico/node@sha256:" + CALICO_NODE.rsplit(":", 1)[1], "containerID": "containerd://" + "1" * 64}],
                "initContainerStatuses": [
                    {"name": "upgrade-ipam", "image": CALICO_CNI, "imageID": "docker-pullable://quay.io/calico/cni@sha256:" + CALICO_CNI.rsplit(":", 1)[1], "containerID": "containerd://" + "2" * 64},
                    {"name": "install-cni", "image": CALICO_CNI, "imageID": "docker-pullable://quay.io/calico/cni@sha256:" + CALICO_CNI.rsplit(":", 1)[1], "containerID": "containerd://" + "3" * 64},
                    {"name": "ebpf-bootstrap", "image": CALICO_NODE, "imageID": "docker-pullable://quay.io/calico/node@sha256:" + CALICO_NODE.rsplit(":", 1)[1], "containerID": "containerd://" + "4" * 64},
                ],
            },
        }
        controller = {
            "apiVersion": "v1", "kind": "Pod",
            "metadata": {"namespace": "kube-system", "name": "calico-kube-controllers-a", "uid": "pod-controller", "resourceVersion": "202"},
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "containerStatuses": [{"name": "calico-kube-controllers", "image": CALICO_CONTROLLERS, "imageID": "docker-pullable://quay.io/calico/kube-controllers@sha256:" + CALICO_CONTROLLERS.rsplit(":", 1)[1], "containerID": "containerd://" + "5" * 64}],
                "initContainerStatuses": [],
            },
        }
        parsed = inventory._parse_pod_image_list(raw_list([item, controller]))
        self.assertEqual(
            {(record.container_type, record.container, record.image_role) for record in parsed},
            {
                ("init", "upgrade-ipam", "calico-cni"),
                ("init", "install-cni", "calico-cni"),
                ("init", "ebpf-bootstrap", "calico-node"),
                ("regular", "calico-node", "calico-node"),
                ("regular", "calico-kube-controllers", "calico-kube-controllers"),
            },
        )
        for mutation in (
            {**item, "status": {**item["status"], "conditions": [{"type": "Initialized", "status": "True"}]}},
            {**item, "status": {**item["status"], "conditions": [{"type": "Ready", "status": "Unknown"}]}},
            {**item, "status": {**item["status"], "extra": 1}},
            {**item, "status": {**item["status"], "containerStatuses": item["status"]["containerStatuses"] * 2}},
            {**item, "status": {**item["status"], "containerStatuses": [{"name": "mystery", "image": CALICO_NODE, "imageID": "docker-pullable://quay.io/calico/node@sha256:" + CALICO_NODE.rsplit(":", 1)[1]}]}},
            {**item, "status": {**item["status"], "initContainerStatuses": item["status"]["initContainerStatuses"][1:]}},
            {**item, "status": {**item["status"], "containerStatuses": [], "initContainerStatuses": [*item["status"]["initContainerStatuses"], item["status"]["containerStatuses"][0]]}},
        ):
            with self.assertRaises(InventoryError):
                inventory._parse_pod_image_list(raw_list([mutation]))

    def test_raw_endpoints_and_slices_reject_unknown_conditions_and_ambiguity(self) -> None:
        endpoints = {
            "apiVersion": "v1", "kind": "Endpoints",
            "metadata": {"namespace": "kil-v3-baseline", "name": "envoy", "uid": "ep-1", "resourceVersion": "3"},
            "subsets": [{"addresses": [{"ip": "10.244.0.10"}], "ports": [{"name": "http", "protocol": "TCP", "port": 8080}]}],
        }
        slices = {
            "apiVersion": "discovery.k8s.io/v1", "kind": "EndpointSlice",
            "metadata": {"namespace": "kil-v3-baseline", "name": "envoy-a", "uid": "slice-1", "resourceVersion": "4", "labels": {"kubernetes.io/service-name": "envoy"}},
            "addressType": "IPv4",
            "endpoints": [{"addresses": ["10.244.0.10"], "conditions": {"ready": True}}],
            "ports": [{"name": "http", "protocol": "TCP", "port": 8080}],
        }
        first = inventory._parse_endpoint_list(raw_list([endpoints]), "Endpoints")
        second = inventory._parse_endpoint_list(raw_list([slices]), "EndpointSlice")
        self.assertEqual(first[0].addresses, second[0].addresses)
        multi_port = {
            **endpoints,
            "subsets": [{
                **endpoints["subsets"][0],
                "ports": [
                    {"name": "http", "protocol": "TCP", "port": 8080},
                    {"name": "metrics", "protocol": "TCP", "port": 9090},
                ],
            }],
        }
        same_source = inventory._parse_endpoint_list(
            raw_list([multi_port]), "Endpoints",
        )
        self.assertEqual(len(same_source), 2)
        ambiguous = tampered(self.snapshot, endpoints=tuple(sorted((*first, *second))))
        mirrored = ExpectedInventory(
            self.expected.cluster_incarnation_uid, self.expected.node_container_id,
            self.expected.docker_host, self.expected.namespaces, self.expected.objects,
            self.expected.pod_images, self.expected.endpoints, self.expected.policy_graph,
            1, 1, 1, 1,
        )
        object.__setattr__(mirrored, "endpoints", ambiguous.endpoints)
        with self.assertRaisesRegex(InventoryError, "ambiguous"):
            validate_inventory(ambiguous, mirrored)
        bad_slice = {**slices, "endpoints": [{"addresses": ["10.244.0.10"], "conditions": {"ready": True, "serving": True}}]}
        with self.assertRaises(InventoryError):
            inventory._parse_endpoint_list(raw_list([bad_slice]), "EndpointSlice")
        different_port_slice = {
            **slices,
            "ports": [{"name": "metrics", "protocol": "TCP", "port": 9090}],
        }
        different_source = inventory._parse_endpoint_list(
            raw_list([different_port_slice]), "EndpointSlice",
        )
        mixed = tampered(
            self.snapshot, endpoints=tuple(sorted((*first, *different_source))),
        )
        mixed_expected = tampered(self.expected, endpoints=mixed.endpoints)
        with self.assertRaisesRegex(InventoryError, "ambiguous"):
            validate_inventory(mixed, mixed_expected)

    def test_raw_policy_projection_rejects_selector_direction_peer_and_port_ambiguity(self) -> None:
        item = {
            "apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
            "metadata": {"namespace": "kil-v3-baseline", "name": "driver-envoy", "uid": "np-1", "resourceVersion": "5"},
            "spec": {
                "sourceRoles": ["driver"], "direction": "Egress",
                "peers": [{"namespace": "kil-v3-baseline", "roles": ["envoy"]}],
                "ports": [{"protocol": "TCP", "port": 8080}],
            },
        }
        self.assertEqual(len(inventory._parse_policy_list(raw_list([item]))), 1)
        mutations = (
            {**item, "spec": {**item["spec"], "sourceRoles": []}},
            {**item, "spec": {**item["spec"], "direction": "Ingress"}},
            {**item, "spec": {**item["spec"], "peers": item["spec"]["peers"] * 2}},
            {**item, "spec": {**item["spec"], "ports": [{"protocol": "SCTP", "port": 8080}]}},
            {**item, "spec": {**item["spec"], "ports": [{"protocol": "TCP", "port": True}]}},
        )
        for mutation in mutations:
            with self.assertRaises(InventoryError):
                inventory._parse_policy_list(raw_list([mutation]))

    def test_raw_calico_workloads_close_status_and_bind_all_three_pins(self) -> None:
        daemonset = {
            "apiVersion": "apps/v1", "kind": "DaemonSet",
            "metadata": {"namespace": "kube-system", "name": "calico-node", "uid": "ds-1", "resourceVersion": "6"},
            "spec": {
                "containers": [{"name": "calico-node", "image": CALICO_NODE}],
                "initContainers": [
                    {"name": "upgrade-ipam", "image": CALICO_CNI},
                    {"name": "install-cni", "image": CALICO_CNI},
                    {"name": "ebpf-bootstrap", "image": CALICO_NODE},
                ],
            },
            "status": {"desiredNumberScheduled": 1, "numberReady": 1},
        }
        deployment = {
            "apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"namespace": "kube-system", "name": "calico-kube-controllers", "uid": "dep-1", "resourceVersion": "7"},
            "spec": {"containers": [{"name": "calico-kube-controllers", "image": CALICO_CONTROLLERS}], "initContainers": []},
            "status": {"replicas": 1, "readyReplicas": 1},
        }
        daemonset_result = inventory._parse_calico_workload_list(
            raw_list([daemonset]), "DaemonSet",
        )
        controller_result = inventory._parse_calico_workload_list(
            raw_list([deployment]), "Deployment",
        )
        self.assertEqual(daemonset_result[:2], (1, 1))
        self.assertEqual(
            set(daemonset_result[2]),
            {
                ("init", "upgrade-ipam", CALICO_CNI),
                ("init", "install-cni", CALICO_CNI),
                ("init", "ebpf-bootstrap", CALICO_NODE),
                ("regular", "calico-node", CALICO_NODE),
            },
        )
        self.assertEqual(
            controller_result,
            (1, 1, (("regular", "calico-kube-controllers", CALICO_CONTROLLERS),)),
        )
        for mutation in (
            {**daemonset, "status": {"desiredNumberScheduled": True, "numberReady": 1}},
            {**daemonset, "spec": {**daemonset["spec"], "containers": [{"name": "calico-node", "image": "quay.io/calico/node@sha256:" + "e" * 64}]}},
            {**daemonset, "spec": {**daemonset["spec"], "initContainers": daemonset["spec"]["initContainers"][1:]}},
            {**daemonset, "spec": {**daemonset["spec"], "initContainers": [*daemonset["spec"]["initContainers"], daemonset["spec"]["initContainers"][0]]}},
            {**daemonset, "spec": {**daemonset["spec"], "initContainers": [{"name": "mystery", "image": CALICO_CNI}, *daemonset["spec"]["initContainers"][1:]]}},
            {**daemonset, "spec": {**daemonset["spec"], "initContainers": [{"name": "install-cni", "image": CALICO_NODE}, daemonset["spec"]["initContainers"][0], daemonset["spec"]["initContainers"][2]]}},
            {**daemonset, "spec": {**daemonset["spec"], "containers": [], "initContainers": [*daemonset["spec"]["initContainers"], daemonset["spec"]["containers"][0]]}},
            {**deployment, "status": {**deployment["status"], "extra": 1}},
        ):
            kind = mutation["kind"]
            with self.assertRaises(InventoryError):
                inventory._parse_calico_workload_list(raw_list([mutation]), kind)

    def test_calico_pin_roles_and_docker_host_cannot_be_mirrored_or_suffix_spoofed(self) -> None:
        arbitrary = tampered(self.snapshot.pod_images[0], image=CALICO_CNI[:-1] + "e")
        unexpected_placement = tampered(
            next(item for item in self.snapshot.pod_images if item.container == "calico-node"),
            container_type="init",
        )
        wrong_pod = tampered(
            next(
                item for item in self.snapshot.pod_images
                if item.container == "calico-kube-controllers"
            ),
            pod="calico-node-a",
        )
        for images in (
            tuple(sorted((arbitrary, *self.snapshot.pod_images[1:]))),
            self.snapshot.pod_images[1:],
            tuple(sorted(
                unexpected_placement if item.container == "calico-node" else item
                for item in self.snapshot.pod_images
            )),
            tuple(sorted(
                wrong_pod if item.container == "calico-kube-controllers" else item
                for item in self.snapshot.pod_images
            )),
        ):
            current = tampered(self.snapshot, pod_images=images)
            expected = tampered(self.expected, pod_images=images)
            with self.assertRaises(InventoryError):
                validate_inventory(current, expected)
        for spoofed in (
            "unix:///Users/test/project/.colima/kil-v3-lab/docker.sock",
            "unix:///Users/../.colima/kil-v3-lab/docker.sock",
            "unix:///Users/./.colima/kil-v3-lab/docker.sock",
            "unix:///Users/%2e%2e/.colima/kil-v3-lab/docker.sock",
            "unix:///Users/test//.colima/kil-v3-lab/docker.sock",
            "unix:////Users/test/.colima/kil-v3-lab/docker.sock",
            "unix:///Users/-/.colima/kil-v3-lab/docker.sock",
        ):
            current = tampered(self.snapshot, docker_host=spoofed)
            expected = tampered(self.expected, docker_host=spoofed)
            with self.subTest(spoofed=spoofed):
                with self.assertRaisesRegex(InventoryError, "kil-v3-lab"):
                    validate_inventory(current, expected)

    def test_profile_and_vendored_manifest_prove_calico_container_oracle(self) -> None:
        profile = V3B2Profile.load(ROOT / "deploy/kind/v3b2-profile.json")
        pins = dict(profile.calico_images)
        text = (ROOT / profile.calico_manifest_path).read_text(encoding="utf-8")
        daemonset = text[text.index("kind: DaemonSet"):text.index("kind: Deployment", text.index("kind: DaemonSet"))]
        init_text, regular_text = daemonset.split("      containers:", 1)
        pair_pattern = re.compile(r'- name: "?([^"\n]+)"?\n\s+image: (quay\.io/calico/[^\s]+)')
        self.assertEqual(
            pair_pattern.findall(init_text),
            [("upgrade-ipam", pins["cni"]), ("install-cni", pins["cni"]), ("ebpf-bootstrap", pins["node"])],
        )
        self.assertEqual(pair_pattern.findall(regular_text)[:1], [("calico-node", pins["node"])])
        deployment = text[text.index("kind: Deployment", text.index("kind: DaemonSet")):]
        self.assertIn(
            f"- name: calico-kube-controllers\n          image: {pins['kube_controllers']}",
            deployment,
        )


if __name__ == "__main__":
    unittest.main()
