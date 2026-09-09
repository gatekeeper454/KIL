from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import unittest
from unittest.mock import patch

from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_deployment_ownership import validate_deployment_ownership
from kil.v3b2_node_ownership import validate_node_ownership
from kil.v3b2_platform_endpoints import (
    CoreDNSPodEndpoint,
    PlatformEndpointBinding,
    PlatformEndpointError,
    PlatformEndpointProof,
    validate_platform_endpoints,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE = V3B2Profile.load(ROOT / "deploy/kind/v3b2-profile.json")
NODE = "kil-v3-lab-control-plane"
STAMP = "2026-09-07T01:02:03Z"
NAMESPACES = ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed")


def deployment_proof():
    expected = [("kube-system", "coredns", 2),
                ("kube-system", "calico-kube-controllers", 1),
                ("local-path-storage", "local-path-provisioner", 1)]
    expected += [(namespace, name, 1) for namespace in NAMESPACES
                 for name in ("authz", "envoy", "target")]
    deployments, replica_sets, pods = [], [], []
    for index, (namespace, name, replicas) in enumerate(sorted(expected), 1):
        deployment_uid, rs_uid, hash_value = f"duid-{index}", f"rsuid-{index}", f"h{index:09d}"
        rs_name = f"{name}-{hash_value}"
        deployments.append({"apiVersion": "apps/v1", "kind": "Deployment",
                            "namespace": namespace, "name": name, "uid": deployment_uid,
                            "resourceVersion": str(100 + index), "revision": "1", "replicas": replicas})
        replica_sets.append({"apiVersion": "apps/v1", "kind": "ReplicaSet",
                            "namespace": namespace, "name": rs_name, "uid": rs_uid,
                            "resourceVersion": str(200 + index), "revision": "1",
                            "podTemplateHash": hash_value,
                            "ownerReference": {"apiVersion": "apps/v1", "kind": "Deployment",
                                               "name": name, "uid": deployment_uid,
                                               "controller": True, "blockOwnerDeletion": True}})
        for pod_index in range(replicas):
            pods.append({"apiVersion": "v1", "kind": "Pod", "namespace": namespace,
                         "name": f"{rs_name}-p{pod_index:04d}",
                         "uid": f"puid-{index}-{pod_index}",
                         "resourceVersion": str(300 + index * 2 + pod_index),
                         "podTemplateHash": hash_value,
                         "ownerReference": {"apiVersion": "apps/v1", "kind": "ReplicaSet",
                                            "name": rs_name, "uid": rs_uid,
                                            "controller": True, "blockOwnerDeletion": True}})
    return validate_deployment_ownership(
        deployments=deployments, replica_sets=replica_sets, pods=pods,
        application_namespaces=NAMESPACES,
    )


def node_proof():
    node = {"apiVersion": "v1", "kind": "Node", "name": NODE,
            "uid": "node-uid", "resourceVersion": "11"}
    daemon_sets, daemon_pods = [], []
    for index, name in enumerate(("calico-node", "kube-proxy"), 1):
        uid = f"ds-uid-{index}"
        daemon_sets.append({"apiVersion": "apps/v1", "kind": "DaemonSet",
                            "namespace": "kube-system", "name": name, "uid": uid,
                            "resourceVersion": str(20 + index), "desiredNumberScheduled": 1})
        daemon_pods.append({"apiVersion": "v1", "kind": "Pod", "namespace": "kube-system",
                            "name": f"{name}-a1b2{index}", "uid": f"daemon-pod-{index}",
                            "resourceVersion": str(30 + index), "nodeName": NODE,
                            "ownerReference": {"apiVersion": "apps/v1", "kind": "DaemonSet",
                                               "name": name, "uid": uid, "controller": True,
                                               "blockOwnerDeletion": True}})
    static_pods = []
    for index, component in enumerate(("etcd", "kube-apiserver", "kube-controller-manager", "kube-scheduler"), 1):
        digest = f"{index:032x}"
        static_pods.append({"apiVersion": "v1", "kind": "Pod", "namespace": "kube-system",
                            "name": f"{component}-{NODE}", "uid": f"static-{index}",
                            "resourceVersion": str(40 + index), "nodeName": NODE,
                            "component": component, "configSource": "file",
                            "configHash": digest, "mirrorHash": digest,
                            "ownerReference": {"apiVersion": "v1", "kind": "Node",
                                               "name": NODE, "uid": "node-uid", "controller": True}})
    return validate_node_ownership(node=node, daemon_sets=daemon_sets,
                                   daemon_pods=daemon_pods, static_pods=static_pods,
                                   cluster_name="kil-v3-lab")


def fixture():
    deployments, node = deployment_proof(), node_proof()
    coredns = next(item for item in deployments.bindings
                   if (item.namespace, item.deployment_name) == ("kube-system", "coredns"))
    pod_values = []
    for index, (name, uid, rv) in enumerate(coredns.pods, 20):
        ip = f"10.244.0.{index}"
        pod_values.append({"apiVersion": "v1", "kind": "Pod", "namespace": "kube-system",
                           "name": name, "uid": uid, "resourceVersion": rv,
                           "creationTimestamp": STAMP, "nodeName": NODE, "phase": "Running",
                           "deletionTimestamp": None, "podIP": ip, "podIPs": [{"ip": ip}],
                           "conditions": [{"type": "Ready", "status": "True"}]})
    services = [
        {"apiVersion": "v1", "kind": "Service", "namespace": "default", "name": "kubernetes",
         "uid": "service-kubernetes", "resourceVersion": "51", "creationTimestamp": STAMP,
         "labels": {"component": "apiserver", "provider": "kubernetes"}, "annotations": {},
         "selector": None, "clusterIP": "10.96.0.1", "clusterIPs": ["10.96.0.1"],
         "ipFamilies": ["IPv4"], "ipFamilyPolicy": "SingleStack", "type": "ClusterIP",
         "sessionAffinity": "None", "internalTrafficPolicy": "Cluster",
         "ports": [{"name": "https", "protocol": "TCP", "port": 443, "targetPort": 6443}]},
        {"apiVersion": "v1", "kind": "Service", "namespace": "kube-system", "name": "kube-dns",
         "uid": "service-dns", "resourceVersion": "52", "creationTimestamp": STAMP,
         "labels": {"k8s-app": "kube-dns", "kubernetes.io/cluster-service": "true",
                    "kubernetes.io/name": "CoreDNS"},
         "annotations": {"prometheus.io/port": "9153", "prometheus.io/scrape": "true"},
         "selector": {"k8s-app": "kube-dns"}, "clusterIP": "10.96.0.10",
         "clusterIPs": ["10.96.0.10"], "ipFamilies": ["IPv4"],
         "ipFamilyPolicy": "SingleStack", "type": "ClusterIP", "sessionAffinity": "None",
         "internalTrafficPolicy": "Cluster",
         "ports": [{"name": "dns", "protocol": "UDP", "port": 53, "targetPort": 53},
                   {"name": "dns-tcp", "protocol": "TCP", "port": 53, "targetPort": 53},
                   {"name": "metrics", "protocol": "TCP", "port": 9153, "targetPort": 9153}]},
    ]
    target_addresses = [{"ip": pod["podIP"], "nodeName": NODE,
                         "targetRef": {"kind": "Pod", "namespace": "kube-system",
                                       "name": pod["name"], "uid": pod["uid"]}}
                        for pod in pod_values]
    endpoint_ports = {
        "api": [{"name": "https", "protocol": "TCP", "port": 6443}],
        "dns": [{"name": "dns", "protocol": "UDP", "port": 53},
                {"name": "dns-tcp", "protocol": "TCP", "port": 53},
                {"name": "metrics", "protocol": "TCP", "port": 9153}],
    }
    endpoints = [
        {"apiVersion": "v1", "kind": "Endpoints", "namespace": "default", "name": "kubernetes",
         "uid": "endpoints-kubernetes", "resourceVersion": "61", "creationTimestamp": STAMP,
         "labels": {"endpointslice.kubernetes.io/skip-mirror": "true"},
         "subsets": [{"addresses": [{"ip": "192.168.5.2"}], "ports": endpoint_ports["api"]}]},
        {"apiVersion": "v1", "kind": "Endpoints", "namespace": "kube-system", "name": "kube-dns",
         "uid": "endpoints-dns", "resourceVersion": "62", "creationTimestamp": STAMP,
         "labels": {"k8s-app": "kube-dns", "kubernetes.io/cluster-service": "true",
                    "kubernetes.io/name": "CoreDNS",
                    "endpoints.kubernetes.io/managed-by": "endpoint-controller"},
         "subsets": [{"addresses": target_addresses, "ports": endpoint_ports["dns"]}]},
    ]
    dns_slice_endpoints = [
        {"addresses": [pod["podIP"]],
         "conditions": {"ready": True, "serving": True, "terminating": False},
         "targetRef": {"kind": "Pod", "namespace": "kube-system", "name": pod["name"],
                       "uid": pod["uid"]}, "nodeName": NODE}
        for pod in pod_values
    ]
    slices = [
        {"apiVersion": "discovery.k8s.io/v1", "kind": "EndpointSlice", "namespace": "default",
         "name": "kubernetes", "uid": "slice-kubernetes", "resourceVersion": "71",
         "creationTimestamp": STAMP, "labels": {"kubernetes.io/service-name": "kubernetes"},
         "ownerReference": None, "addressType": "IPv4", "ports": endpoint_ports["api"],
         "endpoints": [{"addresses": ["192.168.5.2"], "conditions": {"ready": True},
                        "targetRef": None, "nodeName": None}]},
        {"apiVersion": "discovery.k8s.io/v1", "kind": "EndpointSlice", "namespace": "kube-system",
         "name": "kube-dns-a1b2c", "uid": "slice-dns", "resourceVersion": "72",
         "creationTimestamp": STAMP,
         "labels": {"kubernetes.io/service-name": "kube-dns",
                    "endpointslice.kubernetes.io/managed-by": "endpointslice-controller.k8s.io"},
         "ownerReference": {"apiVersion": "v1", "kind": "Service", "name": "kube-dns",
                            "uid": "service-dns", "controller": True, "blockOwnerDeletion": True},
         "addressType": "IPv4", "ports": endpoint_ports["dns"], "endpoints": dns_slice_endpoints},
    ]
    node_network = {"apiVersion": "v1", "kind": "Node", "name": NODE, "uid": "node-uid",
                    "resourceVersion": "11", "creationTimestamp": STAMP,
                    "addresses": [{"type": "InternalIP", "address": "192.168.5.2"}]}
    return {"profile": PROFILE, "deployment_ownership": deployments, "node_ownership": node,
            "node_network": node_network, "services": services, "coredns_pods": pod_values,
            "endpoints": endpoints, "endpoint_slices": slices}


def validate(values=None):
    return validate_platform_endpoints(**(fixture() if values is None else values))


class PlatformEndpointsTest(unittest.TestCase):
    def test_nominal_proof_is_exact_frozen_canonical_and_detached(self):
        values = fixture(); original = deepcopy(values["endpoint_slices"])
        values["services"].reverse(); values["coredns_pods"].reverse()
        values["endpoints"].reverse(); values["endpoint_slices"].reverse()
        proof = validate(values)
        self.assertEqual(proof.node_internal_ip, "192.168.5.2")
        self.assertEqual(tuple((item.namespace, item.service_name) for item in proof.bindings),
                         (("default", "kubernetes"), ("kube-system", "kube-dns")))
        self.assertEqual(proof.bindings[0].endpoint_slice_name, "kubernetes")
        self.assertEqual(proof.bindings[0].target_uids, ())
        self.assertEqual(len(proof.bindings[1].target_uids), 2)
        self.assertEqual(len(proof.coredns_pods), 2)
        self.assertEqual(
            tuple(sorted((item.address, item.uid) for item in proof.coredns_pods)),
            proof.bindings[1].targets,
        )
        self.assertFalse(proof.runtime_contract_complete)
        values["endpoint_slices"][0]["uid"] = "changed"
        self.assertNotEqual(values["endpoint_slices"], original)
        self.assertEqual(proof.bindings[1].endpoint_slice_uid, "slice-dns")
        with self.assertRaises(FrozenInstanceError):
            proof.node_uid = "changed"

    def test_exports_are_closed(self):
        import kil.v3b2_platform_endpoints as module
        self.assertEqual(module.__all__, (
            "PlatformEndpointError", "CoreDNSPodEndpoint", "PlatformEndpointBinding", "PlatformEndpointProof",
            "validate_platform_endpoints",
        ))

    def test_top_level_cardinality_and_shapes_precede_semantic_traversal(self):
        for family in ("services", "coredns_pods", "endpoints", "endpoint_slices"):
            values = fixture(); values[family] = values[family][:-1]
            with self.subTest(family=family), patch("kil.v3b2_platform_endpoints._text") as text:
                with self.assertRaises(PlatformEndpointError): validate(values)
                text.assert_not_called()
        values = fixture(); values["node_network"] = []
        with patch("kil.v3b2_platform_endpoints._text") as text:
            with self.assertRaises(PlatformEndpointError): validate(values)
            text.assert_not_called()

    def test_all_root_records_are_closed(self):
        locations = (("node_network", None), ("services", 0), ("coredns_pods", 0),
                     ("endpoints", 0), ("endpoint_slices", 0))
        for family, index in locations:
            for mutation in ("missing", "extra"):
                values = fixture(); row = values[family] if index is None else values[family][index]
                row.pop(next(iter(row))) if mutation == "missing" else row.update(extra="x")
                with self.subTest(family=family, mutation=mutation):
                    with self.assertRaises(PlatformEndpointError): validate(values)

    def test_profile_and_accepted_proofs_are_revalidated(self):
        for key in ("profile", "deployment_ownership", "node_ownership"):
            values = fixture(); values[key] = object()
            with self.subTest(key=key), self.assertRaises(PlatformEndpointError): validate(values)
        values = fixture(); object.__setattr__(values["node_ownership"], "node_uid", "bad uid")
        with self.assertRaises(PlatformEndpointError): validate(values)
        values = fixture(); object.__setattr__(values["deployment_ownership"], "runtime_contract_complete", True)
        with self.assertRaises(PlatformEndpointError): validate(values)

    def test_node_projection_is_exact_joined_and_has_one_internal_ip(self):
        cases = (("uid", "other"), ("resourceVersion", "12"),
                 ("creationTimestamp", "2026-09-07 01:02:03Z"))
        for key, value in cases:
            values = fixture(); values["node_network"][key] = value
            with self.subTest(key=key), self.assertRaises(PlatformEndpointError): validate(values)
        for addresses in ([], [{"type": "ExternalIP", "address": "192.168.5.2"}],
                          [{"type": "InternalIP", "address": "192.168.005.2"}],
                          [{"type": "InternalIP", "address": "192.168.5.2"},
                           {"type": "InternalIP", "address": "192.168.5.3"}]):
            values = fixture(); values["node_network"]["addresses"] = addresses
            with self.assertRaises(PlatformEndpointError): validate(values)

    def test_kubernetes_service_configuration_and_numeric_target_are_exact(self):
        cases = (("labels", {"component": "apiserver"}), ("selector", {}),
                 ("clusterIP", "10.96.0.2"), ("sessionAffinity", "ClientIP"),
                 ("internalTrafficPolicy", "Local"))
        for key, value in cases:
            values = fixture(); values["services"][0][key] = value
            with self.subTest(key=key), self.assertRaises(PlatformEndpointError): validate(values)
        for target in ("6443", "https", 443, True):
            values = fixture(); values["services"][0]["ports"][0]["targetPort"] = target
            with self.subTest(target=target), self.assertRaises(PlatformEndpointError): validate(values)

    def test_kube_dns_service_source_rendered_fields_and_defaults_are_exact(self):
        for key, value in (("annotations", {}), ("selector", {"app": "dns"}),
                           ("clusterIP", "10.96.0.11"), ("ipFamilies", ["IPv6"]),
                           ("ipFamilyPolicy", "PreferDualStack"), ("type", "NodePort")):
            values = fixture(); values["services"][1][key] = value
            with self.subTest(key=key), self.assertRaises(PlatformEndpointError): validate(values)
        values = fixture(); values["services"][1]["ports"].reverse()
        with self.assertRaises(PlatformEndpointError): validate(values)

    def test_coredns_pods_join_deployment_and_are_unique_ready_nondeleting(self):
        cases = (("uid", "other"), ("resourceVersion", "999"), ("nodeName", "other"),
                 ("phase", "Pending"), ("deletionTimestamp", STAMP),
                 ("conditions", [{"type": "Ready", "status": "False"}]),
                 ("podIPs", [{"ip": "10.244.0.99"}]))
        for key, value in cases:
            values = fixture(); values["coredns_pods"][0][key] = value
            with self.subTest(key=key), self.assertRaises(PlatformEndpointError): validate(values)
        values = fixture(); values["coredns_pods"][1]["podIP"] = values["coredns_pods"][0]["podIP"]
        values["coredns_pods"][1]["podIPs"] = deepcopy(values["coredns_pods"][0]["podIPs"])
        with self.assertRaises(PlatformEndpointError): validate(values)

    def test_kubernetes_endpoints_and_slice_keep_lease_producer_contract(self):
        mutations = [
            ("endpoints", (0, "labels"), {}),
            ("endpoints", (0, "subsets", 0, "addresses", 0, "ip"), "192.168.5.3"),
            ("endpoint_slices", (0, "name"), "kubernetes-abcde"),
            ("endpoint_slices", (0, "labels"), {"kubernetes.io/service-name": "kubernetes",
                                                  "endpointslice.kubernetes.io/managed-by": "x"}),
            ("endpoint_slices", (0, "ownerReference"), {"x": "y"}),
            ("endpoint_slices", (0, "endpoints", 0, "targetRef"),
             {"kind": "Node", "namespace": "", "name": NODE, "uid": "node-uid"}),
            ("endpoint_slices", (0, "endpoints", 0, "nodeName"), NODE),
            ("endpoint_slices", (0, "endpoints", 0, "conditions"),
             {"ready": True, "serving": True, "terminating": False}),
        ]
        for family, path, value in mutations:
            values = fixture(); target = values[family]
            for part in path[:-1]: target = target[part]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(PlatformEndpointError): validate(values)

    def test_dns_endpoints_and_slice_join_service_and_both_pods(self):
        mutations = [
            ("endpoints", (1, "subsets", 0, "addresses", 0, "targetRef", "uid"), "other"),
            ("endpoints", (1, "subsets", 0, "addresses", 0, "nodeName"), "other"),
            ("endpoint_slices", (1, "name"), "kube-dns-longer"),
            ("endpoint_slices", (1, "ownerReference", "uid"), "other"),
            ("endpoint_slices", (1, "labels", "endpointslice.kubernetes.io/managed-by"), "other"),
            ("endpoint_slices", (1, "endpoints", 0, "conditions", "serving"), False),
            ("endpoint_slices", (1, "endpoints", 0, "conditions", "terminating"), True),
            ("endpoint_slices", (1, "endpoints", 0, "addresses", 0), "10.244.0.99"),
            ("endpoint_slices", (1, "endpoints", 0, "targetRef", "uid"), "other"),
        ]
        for family, path, value in mutations:
            values = fixture(); target = values[family]
            for part in path[:-1]: target = target[part]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(PlatformEndpointError): validate(values)

    def test_legacy_endpoints_labels_are_source_specific_and_not_interchangeable(self):
        values = fixture()
        self.assertEqual(values["endpoints"][0]["labels"], {
            "endpointslice.kubernetes.io/skip-mirror": "true",
        })
        self.assertEqual(values["endpoints"][1]["labels"], {
            "k8s-app": "kube-dns",
            "kubernetes.io/cluster-service": "true",
            "kubernetes.io/name": "CoreDNS",
            "endpoints.kubernetes.io/managed-by": "endpoint-controller",
        })
        for index, labels in (
            (0, deepcopy(values["endpoints"][1]["labels"])),
            (1, deepcopy(values["endpoints"][0]["labels"])),
            (1, {"k8s-app": "kube-dns",
                 "kubernetes.io/cluster-service": "true",
                 "kubernetes.io/name": "CoreDNS",
                 "endpoints.kubernetes.io/managed-by": "other-controller"}),
            (1, {"k8s-app": "kube-dns",
                 "kubernetes.io/cluster-service": "true",
                 "endpoints.kubernetes.io/managed-by": "endpoint-controller"}),
        ):
            candidate = fixture(); candidate["endpoints"][index]["labels"] = labels
            with self.subTest(index=index, labels=labels):
                with self.assertRaises(PlatformEndpointError): validate(candidate)

    def test_endpoint_ports_and_cross_resource_addresses_must_agree(self):
        values = fixture(); values["endpoints"][0]["subsets"][0]["ports"][0]["port"] = 443
        with self.assertRaises(PlatformEndpointError): validate(values)
        values = fixture(); values["endpoint_slices"][1]["ports"][2]["port"] = 9154
        with self.assertRaises(PlatformEndpointError): validate(values)
        values = fixture(); values["endpoint_slices"][1]["endpoints"].reverse()
        self.assertEqual(len(validate(values).bindings[1].addresses), 2)

    def test_api_uid_rv_timestamp_and_plain_types_are_strict(self):
        locations = (("services", 0), ("coredns_pods", 0), ("endpoints", 0),
                     ("endpoint_slices", 0))
        for family, index in locations:
            for key, value in (("uid", "bad uid"), ("resourceVersion", "01"),
                               ("resourceVersion", str(2**64)),
                               ("creationTimestamp", "2026-02-30T01:02:03Z")):
                values = fixture(); values[family][index][key] = value
                with self.subTest(family=family, key=key), self.assertRaises(PlatformEndpointError):
                    validate(values)
        class Dict(dict): pass
        values = fixture(); values["services"][0] = Dict(values["services"][0])
        with self.assertRaises(PlatformEndpointError): validate(values)

    def test_nested_bounds_apply_before_deep_traversal(self):
        values = fixture(); nested = []
        for _ in range(20): nested = [nested]
        values["services"][0]["labels"] = nested
        with patch("kil.v3b2_platform_endpoints._metadata") as metadata:
            with self.assertRaises(PlatformEndpointError): validate(values)
            metadata.assert_not_called()
        values = fixture(); values["services"][0]["labels"] = {"x": "z" * 1025}
        with self.assertRaises(PlatformEndpointError): validate(values)

    def test_binding_and_proof_constructors_revalidate(self):
        proof = validate(); binding = proof.bindings[0]
        with self.assertRaises(PlatformEndpointError): replace(binding, targets=(("192.168.5.2", "pod"),))
        with self.assertRaises(PlatformEndpointError): replace(binding, endpoint_slice_name="kubernetes-x")
        with self.assertRaises(PlatformEndpointError): replace(binding, endpoint_slice_name=3)
        with self.assertRaises(PlatformEndpointError): replace(binding, namespace=[])
        with self.assertRaises(PlatformEndpointError): replace(binding, cluster_ip="10.96.0.2")
        with self.assertRaises(PlatformEndpointError): replace(binding, targets=(([], ""),))
        with self.assertRaises(PlatformEndpointError): replace(proof, bindings=proof.bindings[:1])
        with self.assertRaises(PlatformEndpointError): replace(proof, runtime_contract_complete=True)
        with self.assertRaises(PlatformEndpointError): replace(proof, node_internal_ip="10.244.0.9")
        with self.assertRaises(PlatformEndpointError): replace(proof, node_internal_ip="10.96.0.20")
        changed = replace(proof.bindings[0], targets=(("192.168.5.3", ""),))
        with self.assertRaises(PlatformEndpointError): replace(proof, bindings=(changed, proof.bindings[1]))
        dns = proof.bindings[1]
        with self.assertRaises(PlatformEndpointError): replace(
            dns, targets=(("10.244.0.0", dns.target_uids[0]), dns.targets[1]))
        with self.assertRaises(PlatformEndpointError): replace(
            dns, targets=(dns.targets[0], dns.targets[0]))
        with self.assertRaises(PlatformEndpointError): replace(proof, dependency_uids=[])
        colliding = replace(binding, service_uid=proof.dependency_uids[0])
        with self.assertRaises(PlatformEndpointError): replace(
            proof, bindings=(colliding, proof.bindings[1]))

    def test_pod_network_and_broadcast_addresses_are_rejected(self):
        for address in ("10.244.0.0", "10.244.255.255"):
            values = fixture()
            pod = values["coredns_pods"][0]
            pod["podIP"] = address; pod["podIPs"] = [{"ip": address}]
            with self.subTest(address=address), self.assertRaises(PlatformEndpointError): validate(values)

    def test_dependency_uid_domains_and_new_resource_uids_cannot_collide(self):
        cases = ("deployment", "replicaset", "daemonset", "daemonpod", "staticpod")
        for case in cases:
            values = fixture()
            deployment = values["deployment_ownership"].bindings[0]
            node = values["node_ownership"]
            if case == "deployment": object.__setattr__(deployment, "deployment_uid", node.node_uid)
            elif case == "replicaset": object.__setattr__(deployment, "replica_set_uid", node.node_uid)
            elif case == "daemonset": object.__setattr__(node.daemon_pods[0], "daemon_set_uid", deployment.deployment_uid)
            elif case == "daemonpod": object.__setattr__(node.daemon_pods[0], "pod_uid", deployment.deployment_uid)
            else: object.__setattr__(node.static_pods[0], "pod_uid", deployment.deployment_uid)
            with self.subTest(case=case), self.assertRaises(PlatformEndpointError): validate(values)
        values = fixture()
        values["services"][0]["uid"] = values["deployment_ownership"].bindings[0].deployment_uid
        with self.assertRaises(PlatformEndpointError): validate(values)
        values = fixture(); values["endpoint_slices"][0]["uid"] = values["endpoints"][0]["uid"]
        with self.assertRaises(PlatformEndpointError): validate(values)

    def test_proof_constructor_preserves_coredns_role_not_just_uid_membership(self):
        proof = validate()
        unrelated = next(
            binding for binding in proof.deployment_ownership.bindings
            if binding.deployment_name != "coredns"
        ).pods[0]
        substitutes = (
            proof.node_ownership.daemon_pods[0].pod_uid,
            proof.node_ownership.static_pods[0].pod_uid,
            unrelated[1],
        )
        for uid in substitutes:
            records = list(proof.coredns_pods)
            records[0] = replace(records[0], uid=uid)
            records.sort()
            self.assertIn(uid, proof.dependency_uids)
            with self.subTest(uid=uid), self.assertRaises(PlatformEndpointError):
                replace(proof, coredns_pods=tuple(records))
        records = list(proof.coredns_pods)
        records[0] = replace(records[0], resource_version=unrelated[2])
        with self.assertRaises(PlatformEndpointError):
            replace(proof, coredns_pods=tuple(sorted(records)))
        records = list(proof.coredns_pods)
        records[0] = replace(records[0], name="coredns-aaaaaaaaaa-zzzzz")
        with self.assertRaises(PlatformEndpointError):
            replace(proof, coredns_pods=tuple(sorted(records)))
        with self.assertRaises(PlatformEndpointError):
            CoreDNSPodEndpoint([], proof.coredns_pods[0].uid, "1", "10.244.0.9")


if __name__ == "__main__":
    unittest.main()
