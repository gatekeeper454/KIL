from copy import copy
from dataclasses import FrozenInstanceError, replace
import json
import unittest

from kil.canonical import canonical_json
from kil.v3b2_inventory import (
    EndpointIdentity,
    ExpectedInventory,
    InventoryError,
    InventorySnapshot,
    ObjectIdentity,
    PodImageIdentity,
    PolicyEdge,
    parse_kubectl_list,
    stable_source,
    validate_inventory,
)


KUBE_SYSTEM_UID = "11111111-1111-4111-8111-111111111111"
NODE_ID = "a" * 64
DOCKER_HOST = "unix:///Users/test/.colima/kil-v3-lab/docker.sock"
CALICO_NODE = "quay.io/calico/node@sha256:" + "b" * 64
CALICO_CONTROLLERS = "quay.io/calico/kube-controllers@sha256:" + "c" * 64
KIL_IMAGE = "kil.local/kil-v3b2:sha256-" + "d" * 64
KIL_IMAGE_ID = "docker-pullable://kil.local/kil-v3b2@sha256:" + "d" * 64


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
    objects = tuple(sorted((
        ObjectIdentity("v1", "Namespace", "", "kube-system", KUBE_SYSTEM_UID, "100"),
        obj("Deployment", "kil-v3-baseline", "envoy", "envoy"),
        obj("Service", "kil-v3-baseline", "envoy", "service"),
    )))
    images = tuple(sorted((
        PodImageIdentity("kube-system", "calico-node-a", "calico-node", "pod-calico", "201", CALICO_NODE, "docker-pullable://quay.io/calico/node@sha256:" + "b" * 64, True),
        PodImageIdentity("kube-system", "calico-kube-controllers-a", "calico-kube-controllers", "pod-controller", "202", CALICO_CONTROLLERS, "docker-pullable://quay.io/calico/kube-controllers@sha256:" + "c" * 64, True),
        PodImageIdentity("kil-v3-baseline", "envoy-a", "envoy", "pod-envoy", "203", KIL_IMAGE, KIL_IMAGE_ID, True),
    )))
    endpoints = (EndpointIdentity("kil-v3-baseline", "envoy", ("10.244.0.10",), "http", "TCP", 8080),)
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


class StrSubclass(str):
    pass


class TupleSubclass(tuple):
    pass


class V3B2InventoryTest(unittest.TestCase):
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
            EndpointIdentity("n", "s", TupleSubclass(("10.0.0.1",)), "http", "TCP", 80)
        with self.assertRaises(InventoryError):
            EndpointIdentity("n", "s", ("10.0.0.1",), "http", "TCP", True)
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

    def test_rejects_extra_namespace_workload_service_endpoint_or_policy(self) -> None:
        mutations = (
            tampered(self.snapshot, namespaces=tuple(sorted((*self.snapshot.namespaces, "foreign-in-cluster")))),
            replace(self.snapshot, objects=tuple(sorted((*self.snapshot.objects, obj("Deployment", "kil-v3-baseline", "extra", "x"))))),
            replace(self.snapshot, objects=tuple(sorted((*self.snapshot.objects, obj("Service", "kil-v3-signed", "public", "y"))))),
            replace(self.snapshot, endpoints=(*self.snapshot.endpoints, EndpointIdentity("kil-v3-signed", "public", ("10.244.0.20",), "http", "TCP", 8080))),
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

    def test_rejects_uid_resourceversion_or_image_identity_drift(self) -> None:
        after = self.snapshot
        changed_object = replace(after.objects[1], uid="changed")
        changed_rv = replace(after.objects[1], resource_version="changed")
        changed_image = replace(after.pod_images[0], image_id=after.pod_images[0].image_id[:-1] + "a")
        for mutated in (
            replace(after, objects=tuple(sorted((after.objects[0], changed_object, after.objects[2])))),
            replace(after, objects=tuple(sorted((after.objects[0], changed_rv, after.objects[2])))),
            replace(after, pod_images=tuple(sorted((changed_image, *after.pod_images[1:])))),
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
        wrong = replace(self.snapshot.pod_images[0], image=CALICO_NODE[:-1] + "e")
        no_digest_id = tampered(self.snapshot.pod_images[0], image_id="sha256:" + "b" * 64)
        for mutated in (
            replace(self.snapshot, calico_node_desired=2),
            replace(self.snapshot, calico_controller_desired=2, calico_controller_ready=2),
            tampered(self.snapshot, pod_images=tuple(sorted((mutable, *self.snapshot.pod_images[1:])))),
            replace(self.snapshot, pod_images=tuple(sorted((wrong, *self.snapshot.pod_images[1:])))),
            tampered(self.snapshot, pod_images=tuple(sorted((no_digest_id, *self.snapshot.pod_images[1:])))),
        ):
            with self.assertRaises(InventoryError):
                validate_inventory(mutated, self.expected)

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
            PodImageIdentity("n", "p", "c", "u", "r", KIL_IMAGE, KIL_IMAGE_ID, "Unknown")  # type: ignore[arg-type]
        with self.assertRaises(InventoryError):
            EndpointIdentity("n", "s", ("10.0.0.1", "10.0.0.1"), "http", "TCP", 80)
        with self.assertRaises(InventoryError):
            EndpointIdentity("n", "s", ("10.0.0.2", "10.0.0.1"), "http", "TCP", 80)


if __name__ == "__main__":
    unittest.main()
