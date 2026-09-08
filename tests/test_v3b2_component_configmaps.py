"""Independent contract tests for uploaded kubeadm and kubelet ConfigMaps."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import builtins
import json
import unittest
from unittest.mock import patch

from kil import v3b2_component_configmaps as component_module
from kil.canonical import canonical_digest
from kil.v3b2_component_configmaps import (
    ComponentConfigMapError,
    ComponentConfigMapProof,
    validate_component_configmaps,
)


KUBEADM = {
    "apiVersion": "kubeadm.k8s.io/v1beta4",
    "kind": "ClusterConfiguration",
    "clusterName": "kil-v3-lab",
    "kubernetesVersion": "v1.36.1",
    "controlPlaneEndpoint": "kil-v3-lab-control-plane:6443",
    "networking": {
        "dnsDomain": "cluster.local",
        "podSubnet": "10.244.0.0/16",
        "serviceSubnet": "10.96.0.0/16",
    },
    "controllerManager": {
        "extraArgs": [
            {"name": "enable-hostpath-provisioner", "value": "true"},
        ],
    },
    "apiServer": {
        "certSANs": ["kil-v3-lab-control-plane", "127.0.0.1"],
        "extraArgs": [{"name": "profiling", "value": "false"}],
    },
    "dns": {},
    "featureGates": {"SomePinnedGate": False},
    "certificateValidityPeriod": -1,
    "imageRepository": None,
}

KUBELET = {
    "apiVersion": "kubelet.config.k8s.io/v1beta1",
    "kind": "KubeletConfiguration",
    "clusterDomain": "cluster.local",
    "clusterDNS": ["10.96.0.10"],
    "authentication": {
        "anonymous": {"enabled": False},
        "webhook": {"enabled": True, "cacheTTL": "2m0s"},
    },
    "authorization": {"mode": "Webhook"},
    "evictionHard": {"memory.available": "100Mi"},
    "shutdownGracePeriod": "0s",
    "serializeImagePulls": True,
    "maxPods": 110,
    "oomScoreAdj": -999,
    "reservedSystemCPUs": None,
    "staticPodPath": "",
}

PINNED = dict(
    cluster_name="kil-v3-lab",
    kubernetes_version="v1.36.1",
    pod_subnet="10.244.0.0/16",
    service_subnet="10.96.0.0/16",
    dns_domain="cluster.local",
    cluster_dns="10.96.0.10",
    provider_rootless=False,
)


def _scalar(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def yaml_document(value, *, reverse=False):
    lines = []

    def emit(node, indent):
        if type(node) is dict:
            items = list(node.items())
            if reverse:
                items.reverse()
            for key, child in items:
                prefix = " " * indent + key + ":"
                if type(child) is dict:
                    if child:
                        lines.append(prefix)
                        emit(child, indent + 2)
                    else:
                        lines.append(prefix + " {}")
                elif type(child) is list:
                    if child:
                        lines.append(prefix)
                        emit(child, indent + 2)
                    else:
                        lines.append(prefix + " []")
                else:
                    lines.append(prefix + " " + _scalar(child))
        else:
            for child in node:
                prefix = " " * indent + "-"
                if type(child) in (dict, list) and child:
                    lines.append(prefix)
                    emit(child, indent + 2)
                elif type(child) is dict:
                    lines.append(prefix + " {}")
                elif type(child) is list:
                    lines.append(prefix + " []")
                else:
                    lines.append(prefix + " " + _scalar(child))

    emit(value, 0)
    return "\n".join(lines) + "\n"


def metadata(name, *, uid=None, rv=None):
    suffix = "ka" if name == "kubeadm-config" else "kl"
    return {
        "name": name,
        "namespace": "kube-system",
        "uid": uid or f"uid-{suffix}",
        "resourceVersion": rv or ("51" if suffix == "ka" else "52"),
        "creationTimestamp": "2026-09-06T00:00:00Z",
        "managedFields": [{
            "manager": "kubeadm", "operation": "Update", "apiVersion": "v1",
            "fieldsType": "FieldsV1", "fieldsV1": {"f:data": {}},
        }],
    }


def documents(*, reverse=False):
    return [
        {"apiVersion": "v1", "kind": "ConfigMap",
         "metadata": metadata("kubelet-config"),
         "data": {"kubelet": yaml_document(KUBELET, reverse=reverse)}},
        {"apiVersion": "v1", "kind": "ConfigMap",
         "metadata": metadata("kubeadm-config"),
         "data": {"ClusterConfiguration": yaml_document(KUBEADM, reverse=reverse)}},
    ]


def validate(value=None, *, kubeadm=None, kubelet=None, **changes):
    arguments = dict(
        expected_kubeadm_configuration=deepcopy(KUBEADM) if kubeadm is None else kubeadm,
        expected_kubelet_configuration=deepcopy(KUBELET) if kubelet is None else kubelet,
        **PINNED,
    )
    arguments.update(changes)
    return validate_component_configmaps(documents=documents() if value is None else value,
                                         **arguments)


class DictSubclass(dict):
    pass


class ListSubclass(list):
    pass


class StringSubclass(str):
    pass


class IntSubclass(int):
    pass


class EqualityTrap:
    def __eq__(self, _other):
        raise AssertionError("attacker equality was invoked")


class ComponentConfigMapsTest(unittest.TestCase):
    def assertInvalid(self, value=None, **changes):
        with self.assertRaises(ComponentConfigMapError):
            validate(value, **changes)

    def test_success_is_sorted_frozen_minimal_and_nonmutating(self):
        observed = documents()
        original = deepcopy(observed)
        proofs = validate(observed)
        self.assertEqual(observed, original)
        self.assertIs(type(proofs), tuple)
        self.assertEqual([proof.name for proof in proofs],
                         ["kubeadm-config", "kubelet-config"])
        self.assertEqual(proofs, validate(observed))
        for proof in proofs:
            self.assertEqual(proof.api_version, "v1")
            self.assertEqual(proof.kind, "ConfigMap")
            self.assertEqual(proof.namespace, "kube-system")
            self.assertIs(proof.provider_rootless, False)
            self.assertIs(proof.runtime_contract_complete, False)
            self.assertEqual(proof.semantic_sha256, proof.expected_sha256)
            self.assertNotIn("apiServer", repr(proof))
            with self.assertRaises(FrozenInstanceError):
                proof.uid = "changed"

    def test_public_validator_is_keyword_only(self):
        arguments = dict(
            expected_kubeadm_configuration=deepcopy(KUBEADM),
            expected_kubelet_configuration=deepcopy(KUBELET),
            **PINNED,
        )
        with self.assertRaises(TypeError):
            validate_component_configmaps(documents(), **arguments)

    def test_reordered_yaml_changes_raw_digest_only(self):
        normal = validate()
        reordered = validate(documents(reverse=True))
        self.assertNotEqual([p.raw_content_sha256 for p in normal],
                            [p.raw_content_sha256 for p in reordered])
        self.assertEqual([p.semantic_sha256 for p in normal],
                         [p.semantic_sha256 for p in reordered])
        self.assertEqual([p.expected_sha256 for p in normal],
                         [p.expected_sha256 for p in reordered])

    def test_digests_use_independent_oracles(self):
        proofs = validate()
        expected = {"kubeadm-config": KUBEADM, "kubelet-config": KUBELET}
        raw = {"kubeadm-config": yaml_document(KUBEADM),
               "kubelet-config": yaml_document(KUBELET)}
        for proof in proofs:
            self.assertEqual(proof.raw_content_sha256,
                             sha256(raw[proof.name].encode()).hexdigest())
            self.assertEqual(proof.semantic_sha256,
                             canonical_digest(expected[proof.name]))

    def test_nested_semantic_drift_is_rejected(self):
        mutations = [
            lambda x: x[0]["data"].update(kubelet=x[0]["data"]["kubelet"].replace("enabled: true", "enabled: false", 1)),
            lambda x: x[1]["data"].update(ClusterConfiguration=x[1]["data"]["ClusterConfiguration"].replace('"127.0.0.1"', '"127.0.0.2"')),
            lambda x: x[0]["data"].update(kubelet=x[0]["data"]["kubelet"].replace("oomScoreAdj: -999", "oomScoreAdj: -998")),
            lambda x: x[1]["data"].update(ClusterConfiguration=x[1]["data"]["ClusterConfiguration"].replace("imageRepository: null", 'imageRepository: "registry"')),
        ]
        for mutate in mutations:
            value = documents()
            mutate(value)
            self.assertInvalid(value)

    def test_every_pinned_independent_input_is_exact(self):
        cases = {
            "cluster_name": "other", "kubernetes_version": "v1.36.0",
            "pod_subnet": "10.245.0.0/16", "service_subnet": "10.97.0.0/16",
            "dns_domain": "example.local", "cluster_dns": "10.96.0.11",
            "provider_rootless": True,
        }
        for field, replacement in cases.items():
            with self.subTest(field=field):
                self.assertInvalid(**{field: replacement})
        for field in cases:
            if field != "provider_rootless":
                with self.subTest(subclass=field):
                    self.assertInvalid(**{field: StringSubclass(PINNED[field])})
        self.assertInvalid(provider_rootless=0)

    def test_expected_configuration_relations_are_independent(self):
        changes = [
            ("kubeadm", lambda d: d.update(clusterName="other")),
            ("kubeadm", lambda d: d.update(kubernetesVersion="v1.36.0")),
            ("kubeadm", lambda d: d.update(controlPlaneEndpoint="other:6443")),
            ("kubeadm", lambda d: d["networking"].update(dnsDomain="other")),
            ("kubeadm", lambda d: d["networking"].update(podSubnet="other")),
            ("kubeadm", lambda d: d["networking"].update(serviceSubnet="other")),
            ("kubelet", lambda d: d.update(clusterDomain="other")),
            ("kubelet", lambda d: d.update(clusterDNS=["10.96.0.11"])),
        ]
        for target, mutate in changes:
            expected = deepcopy(KUBEADM if target == "kubeadm" else KUBELET)
            mutate(expected)
            with self.subTest(target=target, expected=expected):
                self.assertInvalid(**{target: expected})

    def test_controller_extra_args_are_exact_and_unique(self):
        variants = []
        wrong = deepcopy(KUBEADM)
        wrong["controllerManager"]["extraArgs"][0]["value"] = "false"
        variants.append(wrong)
        missing = deepcopy(KUBEADM)
        missing["controllerManager"]["extraArgs"] = []
        variants.append(missing)
        duplicate = deepcopy(KUBEADM)
        duplicate["controllerManager"]["extraArgs"].append(
            {"name": "enable-hostpath-provisioner", "value": "true"})
        variants.append(duplicate)
        duplicate_name = deepcopy(KUBEADM)
        duplicate_name["controllerManager"]["extraArgs"] += [
            {"name": "other", "value": "x"}, {"name": "other", "value": "y"}]
        variants.append(duplicate_name)
        malformed = deepcopy(KUBEADM)
        malformed["controllerManager"]["extraArgs"].append(
            {"name": "other", "value": "x", "extra": None})
        variants.append(malformed)
        for expected in variants:
            self.assertInvalid(kubeadm=expected)

    def test_cluster_dns_shape_is_one_exact_string(self):
        for cluster_dns in ([], ["10.96.0.10", "10.96.0.11"], "10.96.0.10",
                            [StringSubclass("10.96.0.10")]):
            expected = deepcopy(KUBELET)
            expected["clusterDNS"] = cluster_dns
            self.assertInvalid(kubelet=expected)

    def test_cardinality_identity_root_metadata_and_data_are_closed(self):
        self.assertInvalid(documents()[:1])
        self.assertInvalid(tuple(documents()))
        duplicate = documents()
        duplicate[1] = deepcopy(duplicate[0])
        self.assertInvalid(duplicate)
        for mutation in (
            lambda d: d[0].update(extra=None),
            lambda d: d[0].update(apiVersion="v2"),
            lambda d: d[0].update(kind="Secret"),
            lambda d: d[0].update(binaryData={}),
            lambda d: d[0].update(immutable=False),
            lambda d: d[0]["metadata"].update(namespace="default"),
            lambda d: d[0]["metadata"].update(labels={}),
            lambda d: d[0]["metadata"].update(annotations={}),
            lambda d: d[0]["metadata"].update(ownerReferences=[]),
            lambda d: d[0]["metadata"].update(finalizers=[]),
            lambda d: d[0]["metadata"].update(uid=""),
            lambda d: d[0]["metadata"].update(resourceVersion="01"),
            lambda d: d[0]["metadata"].update(creationTimestamp="bad"),
            lambda d: d[0]["data"].update(extra="x"),
            lambda d: d[0].update(data={"kubelet": 1}),
        ):
            value = documents()
            mutation(value)
            self.assertInvalid(value)

    def test_kube_proxy_and_other_identities_are_rejected(self):
        for name in ("kube-proxy", "coredns"):
            value = documents()
            value[0]["metadata"]["name"] = name
            self.assertInvalid(value)

    def test_duplicate_and_ambiguous_yaml_are_normalized(self):
        bad_values = [
            yaml_document(KUBELET) + "kind: KubeletConfiguration\n",
            yaml_document(KUBELET).replace("kind:", "kind: &alias", 1),
            yaml_document(KUBELET).replace("maxPods: 110", "maxPods: 0110"),
            yaml_document(KUBELET).replace("clusterDomain:", "clusterDomain:\t", 1),
            "---\n" + yaml_document(KUBELET),
        ]
        for raw in bad_values:
            value = documents()
            value[0]["data"]["kubelet"] = raw
            with self.subTest(raw=raw[-40:]), self.assertRaises(ComponentConfigMapError):
                validate(value)

    def test_expected_trees_reject_subclasses_and_equality_traps(self):
        cases = [
            DictSubclass(KUBEADM),
            {**deepcopy(KUBEADM), "networking": DictSubclass(KUBEADM["networking"])},
            {**deepcopy(KUBEADM), "apiServer": {"certSANs": ListSubclass([])}},
            {**deepcopy(KUBEADM), "clusterName": StringSubclass("kil-v3-lab")},
            {**deepcopy(KUBEADM), "certificateValidityPeriod": IntSubclass(-1)},
            {**deepcopy(KUBEADM), "trap": EqualityTrap()},
        ]
        for expected in cases:
            with self.subTest(type=type(expected).__name__):
                self.assertInvalid(kubeadm=expected)

    def test_expected_trees_are_bounded_cycle_safe_and_reserve_width(self):
        cycle = deepcopy(KUBEADM)
        cycle["cycle"] = cycle
        self.assertInvalid(kubeadm=cycle)
        deep = deepcopy(KUBEADM)
        node = {}
        deep["deep"] = node
        for _ in range(65):
            child = {}
            node["x"] = child
            node = child
        self.assertInvalid(kubeadm=deep)
        for wide in ([None] * 32768, {str(index): None for index in range(32768)}):
            expected = deepcopy(KUBEADM)
            expected["wide"] = wide
            original_reversed = builtins.reversed
            def guarded(candidate):
                if candidate is wide:
                    raise AssertionError("oversized children were scheduled")
                return original_reversed(candidate)
            with self.subTest(kind=type(wide).__name__), patch(
                    "builtins.reversed", side_effect=guarded):
                self.assertInvalid(kubeadm=expected)

    def test_observed_tree_subclasses_cycles_and_bounds_are_rejected(self):
        value = documents()
        value[0] = DictSubclass(value[0])
        self.assertInvalid(value)
        value = documents()
        value[0]["metadata"] = DictSubclass(value[0]["metadata"])
        self.assertInvalid(value)
        value = documents()
        value[0]["cycle"] = value[0]
        self.assertInvalid(value)
        value = documents()
        value[0]["huge"] = "x" * (1024 * 1024 + 1)
        self.assertInvalid(value)

    def test_proof_constructor_and_bypass_invariants(self):
        proof = validate()[0]
        values = {field: getattr(proof, field) for field in proof.__slots__}
        changes = (
            ("api_version", StringSubclass("v1")), ("kind", "Secret"),
            ("namespace", "default"), ("name", "kube-proxy"),
            ("uid", ""), ("resource_version", "0"),
            ("raw_content_sha256", "A" * 64),
            ("semantic_sha256", "0" * 64),
            ("expected_sha256", "1" * 64),
            ("provider_rootless", 0), ("runtime_contract_complete", True),
        )
        for field, replacement in changes:
            changed = dict(values)
            changed[field] = replacement
            with self.subTest(field=field), self.assertRaises(ComponentConfigMapError):
                ComponentConfigMapProof(**changed)
        partial = object.__new__(ComponentConfigMapProof)
        with self.assertRaises(ComponentConfigMapError):
            partial.__post_init__()
        forged = object.__new__(ComponentConfigMapProof)
        for field, value in values.items():
            object.__setattr__(forged, field, value)
        object.__setattr__(forged, "runtime_contract_complete", True)
        with self.assertRaises(ComponentConfigMapError):
            forged.__post_init__()

    def test_exports_are_the_exact_immutable_tuple(self):
        self.assertIs(type(component_module.__all__), tuple)
        self.assertEqual(component_module.__all__, (
            "ComponentConfigMapError", "ComponentConfigMapProof",
            "validate_component_configmaps",
        ))


if __name__ == "__main__":
    unittest.main()
