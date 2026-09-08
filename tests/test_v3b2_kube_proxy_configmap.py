"""Independent contract tests for the uploaded kube-proxy ConfigMap."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from kil import v3b2_kube_proxy_configmap as proxy_module
from kil.canonical import canonical_digest
from kil.v3b2_kube_proxy_configmap import (
    KubeProxyConfigMapError,
    KubeProxyConfigMapProof,
    validate_kube_proxy_configmap,
)


ENDPOINT = "https://kil-v3-lab-control-plane:6443"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CONFIG_PATH = "/var/lib/kube-proxy/kubeconfig.conf"
EXPECTED = {
    "apiVersion": "kubeproxy.config.k8s.io/v1alpha1",
    "kind": "KubeProxyConfiguration",
    "bindAddress": "0.0.0.0",
    "bindAddressHardFail": False,
    "clientConnection": {
        "acceptContentTypes": "",
        "burst": 10,
        "contentType": "application/vnd.kubernetes.protobuf",
        "kubeconfig": CONFIG_PATH,
        "qps": 5,
    },
    "clusterCIDR": "10.244.0.0/16",
    "configSyncPeriod": "15m0s",
    "conntrack": {
        "maxPerCore": 0,
        "min": 0,
        "tcpBeLiberal": False,
        "tcpCloseWaitTimeout": "1h0m0s",
        "tcpEstablishedTimeout": "24h0m0s",
        "udpStreamTimeout": "5m0s",
        "udpTimeout": "250ms",
    },
    "detectLocalMode": "ClusterCIDR",
    "iptables": {
        "localhostNodePorts": None,
        "masqueradeAll": False,
        "masqueradeBit": None,
        "minSyncPeriod": "1s",
        "syncPeriod": "30s",
    },
    "metricsBindAddress": "127.0.0.1:10249",
    "mode": "iptables",
    "nodePortAddresses": [],
}
KUBECONFIG = {
    "apiVersion": "v1",
    "kind": "Config",
    "clusters": [{
        "cluster": {"certificate-authority": CA_PATH, "server": ENDPOINT},
        "name": "default",
    }],
    "contexts": [{
        "context": {"cluster": "default", "namespace": "default", "user": "default"},
        "name": "default",
    }],
    "current-context": "default",
    "users": [{"name": "default", "user": {"tokenFile": TOKEN_PATH}}],
}
PINNED = dict(
    cluster_name="kil-v3-lab",
    pod_subnet="10.244.0.0/16",
    control_plane_endpoint=ENDPOINT,
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


def document(*, reverse=False):
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "kube-proxy",
            "namespace": "kube-system",
            "labels": {"app": "kube-proxy"},
            "uid": "uid-kp",
            "resourceVersion": "61",
            "creationTimestamp": "2026-09-06T00:00:00Z",
            "managedFields": [{
                "manager": "kubeadm", "operation": "Update", "apiVersion": "v1",
                "fieldsType": "FieldsV1", "fieldsV1": {"f:data": {}},
            }],
        },
        "data": {
            "config.conf": yaml_document(EXPECTED, reverse=reverse),
            "kubeconfig.conf": yaml_document(KUBECONFIG, reverse=reverse),
        },
    }


def validate(value=None, *, expected=None, **changes):
    arguments = dict(
        document=document() if value is None else value,
        expected_proxy_configuration=(deepcopy(EXPECTED) if expected is None else expected),
        **PINNED,
    )
    arguments.update(changes)
    return validate_kube_proxy_configmap(**arguments)


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


class KubeProxyConfigMapTest(unittest.TestCase):
    def assertInvalid(self, value=None, **changes):
        with self.assertRaises(KubeProxyConfigMapError):
            validate(value, **changes)

    def test_success_is_frozen_minimal_nonmutating_and_keyword_only(self):
        observed = document()
        expected = deepcopy(EXPECTED)
        original_observed, original_expected = deepcopy(observed), deepcopy(expected)
        proof = validate(observed, expected=expected)
        self.assertEqual((observed, expected), (original_observed, original_expected))
        self.assertEqual((proof.api_version, proof.kind, proof.namespace, proof.name),
                         ("v1", "ConfigMap", "kube-system", "kube-proxy"))
        self.assertEqual((proof.uid, proof.resource_version), ("uid-kp", "61"))
        self.assertEqual(proof.control_plane_endpoint, ENDPOINT)
        self.assertIs(proof.provider_rootless, False)
        self.assertIs(proof.runtime_contract_complete, False)
        self.assertEqual(proof.config_semantic_sha256, proof.expected_config_sha256)
        self.assertNotIn("tokenFile", repr(proof))
        with self.assertRaises(FrozenInstanceError):
            proof.uid = "changed"
        with self.assertRaises(TypeError):
            validate_kube_proxy_configmap(document(), deepcopy(EXPECTED), **PINNED)

    def test_raw_and_semantic_digests_have_independent_oracles(self):
        proof = validate()
        self.assertEqual(proof.config_raw_sha256,
                         sha256(yaml_document(EXPECTED).encode()).hexdigest())
        self.assertEqual(proof.kubeconfig_raw_sha256,
                         sha256(yaml_document(KUBECONFIG).encode()).hexdigest())
        self.assertEqual(proof.config_semantic_sha256, canonical_digest(EXPECTED))
        self.assertEqual(proof.kubeconfig_semantic_sha256, canonical_digest(KUBECONFIG))
        reordered = validate(document(reverse=True))
        self.assertNotEqual((proof.config_raw_sha256, proof.kubeconfig_raw_sha256),
                            (reordered.config_raw_sha256, reordered.kubeconfig_raw_sha256))
        self.assertEqual((proof.config_semantic_sha256, proof.kubeconfig_semantic_sha256),
                         (reordered.config_semantic_sha256,
                          reordered.kubeconfig_semantic_sha256))

    def test_every_pinned_input_and_expected_relation_is_exact(self):
        for field, replacement in {
            "cluster_name": "other", "pod_subnet": "10.245.0.0/16",
            "control_plane_endpoint": "https://other:6443", "provider_rootless": True,
        }.items():
            with self.subTest(field=field):
                self.assertInvalid(**{field: replacement})
        for field in ("cluster_name", "pod_subnet", "control_plane_endpoint"):
            self.assertInvalid(**{field: StringSubclass(PINNED[field])})
        self.assertInvalid(provider_rootless=0)
        mutations = [
            lambda e: e.update(apiVersion="other"),
            lambda e: e.update(kind="Other"),
            lambda e: e.update(mode="ipvs"),
            lambda e: e.update(clusterCIDR="10.245.0.0/16"),
            lambda e: e["clientConnection"].update(kubeconfig="/tmp/config"),
            lambda e: e["iptables"].update(minSyncPeriod="0s"),
            lambda e: e.update(iptables={"minSyncPeriod": "1s", "extra": False}),
            lambda e: e["conntrack"].update(maxPerCore=1),
            lambda e: e.update(conntrack={"maxPerCore": 0, "extra": False}),
        ]
        for mutate in mutations:
            expected = deepcopy(EXPECTED)
            mutate(expected)
            self.assertInvalid(expected=expected)

    def test_observed_configuration_drift_is_rejected(self):
        for old, new in (('mode: "iptables"', 'mode: "ipvs"'),
                         ("burst: 10", "burst: 11"),
                         ('tcpEstablishedTimeout: "24h0m0s"',
                          'tcpEstablishedTimeout: "23h0m0s"')):
            value = document()
            value["data"]["config.conf"] = value["data"]["config.conf"].replace(old, new)
            with self.subTest(field=old):
                self.assertInvalid(value)

    def test_root_metadata_labels_and_data_are_closed(self):
        mutations = (
            lambda d: d.update(extra=None), lambda d: d.update(apiVersion="v2"),
            lambda d: d.update(kind="Secret"), lambda d: d.update(binaryData={}),
            lambda d: d.update(immutable=False),
            lambda d: d["metadata"].update(name="other"),
            lambda d: d["metadata"].update(namespace="default"),
            lambda d: d["metadata"].update(labels={}),
            lambda d: d["metadata"].update(labels={"app": "kube-proxy", "x": "y"}),
            lambda d: d["metadata"].update(annotations={}),
            lambda d: d["metadata"].update(annotations={"kubernetes.io/config.hash": "x"}),
            lambda d: d["metadata"].update(ownerReferences=[]),
            lambda d: d["metadata"].update(finalizers=[]),
            lambda d: d["metadata"].update(uid=""),
            lambda d: d["metadata"].update(resourceVersion="01"),
            lambda d: d["metadata"].update(creationTimestamp="bad"),
            lambda d: d["data"].update(extra="x"),
            lambda d: d.update(data={"config.conf": "x"}),
            lambda d: d["data"].update(**{"config.conf": 1}),
        )
        for mutate in mutations:
            value = document()
            mutate(value)
            self.assertInvalid(value)

    def test_kubeconfig_root_cardinality_and_exact_relations_are_closed(self):
        variants = []
        for key in KUBECONFIG:
            changed = deepcopy(KUBECONFIG)
            changed.pop(key)
            variants.append(changed)
        for key, value in (("preferences", {}), ("extra", None)):
            variants.append({**deepcopy(KUBECONFIG), key: value})
        changes = [
            ("apiVersion", "v2"), ("kind", "Other"),
            ("current-context", "other"),
        ]
        for key, value in changes:
            changed = deepcopy(KUBECONFIG); changed[key] = value; variants.append(changed)
        for collection in ("clusters", "contexts", "users"):
            for replacement in ([], deepcopy(KUBECONFIG[collection]) * 2):
                changed = deepcopy(KUBECONFIG); changed[collection] = replacement
                variants.append(changed)
        for changed in variants:
            value = document(); value["data"]["kubeconfig.conf"] = yaml_document(changed)
            self.assertInvalid(value)

    def test_kubeconfig_rejects_all_field_path_and_secret_drift(self):
        mutations = (
            lambda k: k["clusters"][0].update(name="other"),
            lambda k: k["clusters"][0].update(extra=None),
            lambda k: k["clusters"][0]["cluster"].update(server="https://other:6443"),
            lambda k: k["clusters"][0]["cluster"].update(**{"certificate-authority": "/tmp/ca"}),
            lambda k: k["clusters"][0]["cluster"].update(**{"certificate-authority-data": "CA"}),
            lambda k: k["contexts"][0].update(name="other"),
            lambda k: k["contexts"][0]["context"].update(cluster="other"),
            lambda k: k["contexts"][0]["context"].update(namespace="other"),
            lambda k: k["contexts"][0]["context"].update(user="other"),
            lambda k: k["users"][0].update(name="other"),
            lambda k: k["users"][0]["user"].update(tokenFile="/tmp/token"),
            lambda k: k["users"][0]["user"].update(token="secret"),
            lambda k: k["users"][0]["user"].update(exec={}),
            lambda k: k["users"][0]["user"].update(**{"auth-provider": {}}),
            lambda k: k["users"][0]["user"].update(username="admin"),
            lambda k: k["users"][0]["user"].update(password="secret"),
            lambda k: k["users"][0]["user"].update(**{"client-certificate": "/tmp/cert"}),
            lambda k: k["users"][0]["user"].update(**{"client-certificate-data": "CERT"}),
            lambda k: k["users"][0]["user"].update(**{"client-key": "/tmp/key"}),
            lambda k: k["users"][0]["user"].update(**{"client-key-data": "KEY"}),
        )
        for mutate in mutations:
            changed = deepcopy(KUBECONFIG); mutate(changed)
            value = document(); value["data"]["kubeconfig.conf"] = yaml_document(changed)
            self.assertInvalid(value)

    def test_malformed_duplicate_and_ambiguous_yaml_are_normalized(self):
        good = yaml_document(EXPECTED)
        bad = [good + "kind: KubeProxyConfiguration\n",
               good.replace("kind:", "kind: &alias", 1),
               good.replace("burst: 10", "burst: 010"),
               good.replace("mode:", "mode:\t", 1), "---\n" + good]
        for key in ("config.conf", "kubeconfig.conf"):
            for raw in bad:
                value = document(); value["data"][key] = raw
                with self.subTest(key=key, raw=raw[-30:]):
                    self.assertInvalid(value)

    def test_exact_builtin_types_and_equality_traps_are_rejected(self):
        cases = [DictSubclass(EXPECTED),
                 {**deepcopy(EXPECTED), "clientConnection": DictSubclass(EXPECTED["clientConnection"])},
                 {**deepcopy(EXPECTED), "nodePortAddresses": ListSubclass([])},
                 {**deepcopy(EXPECTED), "mode": StringSubclass("iptables")},
                 {**deepcopy(EXPECTED), "conntrack": {"maxPerCore": IntSubclass(0)}},
                 {**deepcopy(EXPECTED), "trap": EqualityTrap()}]
        for expected in cases:
            self.assertInvalid(expected=expected)
        value = DictSubclass(document()); self.assertInvalid(value)
        value = document(); value["metadata"] = DictSubclass(value["metadata"]); self.assertInvalid(value)

    def test_expected_tree_is_bounded_cycle_safe_and_reserves_width(self):
        cycle = deepcopy(EXPECTED); cycle["cycle"] = cycle; self.assertInvalid(expected=cycle)
        deep = deepcopy(EXPECTED); node = {}; deep["deep"] = node
        for _ in range(65):
            child = {}; node["x"] = child; node = child
        self.assertInvalid(expected=deep)
        sentinel = "".join(("wide", "-", "child"))
        for wide in ([sentinel] * 32768,
                     {str(index): sentinel for index in range(32768)}):
            expected = deepcopy(EXPECTED); expected["wide"] = wide
            original_string_size = proxy_module._string_size
            def guarded(candidate, remaining, *, key=False):
                if candidate is sentinel:
                    raise AssertionError("oversized children were scheduled")
                return original_string_size(candidate, remaining, key=key)
            with patch.object(proxy_module, "_string_size", side_effect=guarded):
                self.assertInvalid(expected=expected)

    def test_proof_constructor_revalidates_partial_and_forged_instances(self):
        proof = validate()
        values = {field: getattr(proof, field) for field in proof.__slots__}
        changes = (
            ("api_version", StringSubclass("v1")), ("kind", "Secret"),
            ("namespace", "default"), ("name", "other"), ("uid", ""),
            ("resource_version", "0"), ("config_raw_sha256", "A" * 64),
            ("kubeconfig_raw_sha256", "A" * 64),
            ("config_semantic_sha256", "0" * 64),
            ("kubeconfig_semantic_sha256", "A" * 64),
            ("expected_config_sha256", "1" * 64),
            ("control_plane_endpoint", "https://other:6443"),
            ("provider_rootless", 0), ("runtime_contract_complete", True),
        )
        for field, replacement in changes:
            changed = dict(values); changed[field] = replacement
            with self.subTest(field=field), self.assertRaises(KubeProxyConfigMapError):
                KubeProxyConfigMapProof(**changed)
        partial = object.__new__(KubeProxyConfigMapProof)
        with self.assertRaises(KubeProxyConfigMapError):
            partial.__post_init__()
        forged = object.__new__(KubeProxyConfigMapProof)
        for field, value in values.items():
            object.__setattr__(forged, field, value)
        object.__setattr__(forged, "provider_rootless", True)
        with self.assertRaises(KubeProxyConfigMapError):
            forged.__post_init__()

    def test_exports_are_exact_immutable_tuple(self):
        self.assertIs(type(proxy_module.__all__), tuple)
        self.assertEqual(proxy_module.__all__, (
            "KubeProxyConfigMapError", "KubeProxyConfigMapProof",
            "validate_kube_proxy_configmap",
        ))


if __name__ == "__main__":
    unittest.main()
