from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
import unittest
from unittest.mock import patch

from kil.v3b2_node_ownership import (
    DaemonPodBinding,
    NodeOwnershipError,
    NodeOwnershipProof,
    StaticPodBinding,
    validate_node_ownership,
)


CLUSTER = "kil-v3-lab"
NODE = f"{CLUSTER}-control-plane"
COMPONENTS = ("etcd", "kube-apiserver", "kube-controller-manager", "kube-scheduler")


def fixtures():
    node = {"apiVersion": "v1", "kind": "Node", "name": NODE,
            "uid": "uid-node", "resourceVersion": "1"}
    daemon_sets, daemon_pods = [], []
    for index, name in enumerate(("calico-node", "kube-proxy"), 2):
        ds_uid = f"uid-ds-{index}"
        daemon_sets.append({
            "apiVersion": "apps/v1", "kind": "DaemonSet", "namespace": "kube-system",
            "name": name, "uid": ds_uid, "resourceVersion": str(index),
            "desiredNumberScheduled": 1,
        })
        daemon_pods.append({
            "apiVersion": "v1", "kind": "Pod", "namespace": "kube-system",
            "name": f"{name}-a1b2{index}", "uid": f"uid-pod-{index}",
            "resourceVersion": str(index + 2), "nodeName": NODE,
            "ownerReference": {"apiVersion": "apps/v1", "kind": "DaemonSet",
                               "name": name, "uid": ds_uid, "controller": True,
                               "blockOwnerDeletion": True},
        })
    static_pods = []
    for index, component in enumerate(COMPONENTS, 6):
        digest = format(index, "064x")
        static_pods.append({
            "apiVersion": "v1", "kind": "Pod", "namespace": "kube-system",
            "name": f"{component}-{NODE}", "uid": f"uid-static-{index}",
            "resourceVersion": str(index), "nodeName": NODE, "component": component,
            "configSource": "file", "configHash": digest, "mirrorHash": digest,
            "ownerReference": {"apiVersion": "v1", "kind": "Node", "name": NODE,
                               "uid": "uid-node", "controller": True,
                               "blockOwnerDeletion": True},
        })
    return node, daemon_sets, daemon_pods, static_pods


def validate(values=None, **changes):
    node, daemon_sets, daemon_pods, static_pods = fixtures() if values is None else values
    arguments = {"node": node, "daemon_sets": daemon_sets, "daemon_pods": daemon_pods,
                 "static_pods": static_pods, "cluster_name": CLUSTER}
    arguments.update(changes)
    return validate_node_ownership(**arguments)


class NodeOwnershipTest(unittest.TestCase):
    def test_nominal_is_frozen_canonical_and_does_not_retain_input(self):
        values = fixtures()
        original = deepcopy(values)
        values[1].reverse(); values[2].reverse(); values[3].reverse()
        proof = validate(values)
        self.assertEqual(proof.node_name, NODE)
        self.assertEqual(proof.node_uid, "uid-node")
        self.assertEqual(proof.node_resource_version, "1")
        self.assertEqual(tuple(item.daemon_set_name for item in proof.daemon_pods),
                         ("calico-node", "kube-proxy"))
        self.assertEqual(tuple(item.component for item in proof.static_pods), COMPONENTS)
        self.assertEqual({item.owner_node_uid for item in proof.static_pods}, {"uid-node"})
        self.assertFalse(proof.runtime_complete)
        self.assertFalse(any(value is part for value in values for part in (
            proof.daemon_pods, proof.static_pods)))
        self.assertEqual(tuple(sorted(original[1], key=lambda item: item["name"])),
                         tuple(sorted(values[1], key=lambda item: item["name"])))
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            proof.node_uid = "replacement"

    def test_exports_are_an_exact_tuple(self):
        import kil.v3b2_node_ownership as module
        self.assertEqual(module.__all__, (
            "NodeOwnershipError", "DaemonPodBinding", "StaticPodBinding",
            "NodeOwnershipProof", "validate_node_ownership",
        ))

    def test_missing_extra_and_duplicate_families_are_rejected(self):
        for position in range(3):
            with self.subTest(position=position, case="missing"):
                values = list(fixtures()); values[position + 1] = values[position + 1][:-1]
                with self.assertRaises(NodeOwnershipError): validate(tuple(values))
            with self.subTest(position=position, case="extra"):
                values = list(fixtures()); values[position + 1].append(deepcopy(values[position + 1][0]))
                with self.assertRaises(NodeOwnershipError): validate(tuple(values))
        for position in range(3):
            with self.subTest(position=position, case="duplicate"):
                values = list(fixtures()); values[position + 1][1] = deepcopy(values[position + 1][0])
                with self.assertRaises(NodeOwnershipError): validate(tuple(values))

    def test_record_missing_and_extra_keys_are_rejected_before_text_work(self):
        families = ((0, None), (1, 0), (2, 0), (3, 0))
        for family, record_index in families:
            for mutation in ("missing", "extra"):
                values = list(fixtures())
                record = values[family] if record_index is None else values[family][record_index]
                if mutation == "missing": record.pop(next(iter(record)))
                else: record["extra"] = "value"
                with self.subTest(family=family, mutation=mutation):
                    with patch("kil.v3b2_node_ownership._text") as text:
                        with self.assertRaises(NodeOwnershipError): validate(tuple(values))
                        text.assert_not_called()

    def test_owner_key_count_is_checked_before_any_key_set_work(self):
        values = fixtures(); values[2][0]["ownerReference"]["extra"] = "value"
        with patch("kil.v3b2_node_ownership._keys") as keys:
            with self.assertRaises(NodeOwnershipError): validate(values)
            keys.assert_not_called()

    def test_daemon_set_identity_desired_count_and_pod_name_are_exact(self):
        mutations = (
            (1, 0, "apiVersion", "v1"), (1, 0, "kind", "Deployment"),
            (1, 0, "namespace", "default"), (1, 0, "name", "other"),
            (1, 0, "desiredNumberScheduled", 0), (1, 0, "desiredNumberScheduled", True),
            (2, 0, "namespace", "default"), (2, 0, "nodeName", "other-node"),
            (2, 0, "name", "calico-node-a1b2_"), (2, 0, "name", "calico-node-A1b22"),
            (2, 0, "name", "calico-node-a1b222"),
        )
        for family, index, key, value in mutations:
            values = list(fixtures()); values[family][index][key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(NodeOwnershipError): validate(tuple(values))

    def test_daemon_owner_reference_is_exact_and_uid_joined(self):
        for key, value in (
            ("apiVersion", "v1"), ("kind", "Node"), ("name", "kube-proxy"),
            ("uid", "uid-ds-999"), ("controller", False),
            ("blockOwnerDeletion", False), ("controller", 1),
        ):
            values = fixtures(); values[2][0]["ownerReference"][key] = value
            with self.subTest(key=key):
                with self.assertRaises(NodeOwnershipError): validate(values)
        for mutation in ("missing", "extra"):
            values = fixtures(); owner = values[2][0]["ownerReference"]
            owner.pop("kind") if mutation == "missing" else owner.update(extra="x")
            with self.assertRaises(NodeOwnershipError): validate(values)

    def test_same_prefix_with_wrong_daemon_uid_is_rejected(self):
        values = fixtures()
        values[1][0]["uid"] = "uid-ds-same-prefix"
        with self.assertRaises(NodeOwnershipError): validate(values)

    def test_static_component_name_source_and_hashes_are_exact(self):
        cases = (
            ("component", "other"), ("name", f"etcd-other"),
            ("namespace", "default"), ("nodeName", "other"),
            ("configSource", "api"), ("configHash", "A" * 64),
            ("configHash", "0" * 63), ("mirrorHash", "1" * 64),
        )
        for key, value in cases:
            values = fixtures(); values[3][0][key] = value
            with self.subTest(key=key):
                with self.assertRaises(NodeOwnershipError): validate(values)
        values = fixtures(); values[3][1]["component"] = "etcd"
        with self.assertRaises(NodeOwnershipError): validate(values)

    def test_static_node_owner_reference_is_exact_and_uid_joined(self):
        for key, value in (
            ("apiVersion", "apps/v1"), ("kind", "DaemonSet"), ("name", "other"),
            ("uid", "uid-node-other"), ("controller", False),
            ("blockOwnerDeletion", False), ("blockOwnerDeletion", 1),
        ):
            values = fixtures(); values[3][0]["ownerReference"][key] = value
            with self.subTest(key=key):
                with self.assertRaises(NodeOwnershipError): validate(values)

    def test_global_uid_collisions_are_rejected(self):
        locations = ((1, 0), (2, 0), (3, 0))
        for family, index in locations:
            values = fixtures(); values[family][index]["uid"] = "uid-node"
            if family == 1:
                values[2][index]["ownerReference"]["uid"] = "uid-node"
            with self.subTest(family=family):
                with self.assertRaises(NodeOwnershipError): validate(values)

    def test_node_cluster_and_all_scalar_types_are_exact(self):
        mutations = (
            (0, None, "apiVersion", "apps/v1"), (0, None, "kind", "Pod"),
            (0, None, "name", "kil-v3-other-control-plane"),
            (0, None, "uid", "bad uid"), (0, None, "resourceVersion", "01"),
            (0, None, "resourceVersion", str(2**64)), (1, 0, "uid", 3),
            (2, 0, "resourceVersion", True), (3, 0, "name", ["bad"]),
        )
        for family, index, key, value in mutations:
            values = list(fixtures()); record = values[family] if index is None else values[family][index]
            record[key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(NodeOwnershipError): validate(tuple(values))
        for cluster in ("other", "kil-v3-lab ", 3, str("x") * 254):
            with self.assertRaises(NodeOwnershipError): validate(cluster_name=cluster)
        class String(str): pass
        with self.assertRaises(NodeOwnershipError): validate(cluster_name=String(CLUSTER))
        class Dict(dict): pass
        values = fixtures(); values = (Dict(values[0]), *values[1:])
        with self.assertRaises(NodeOwnershipError): validate(values)
        values = list(fixtures()); values[1] = tuple(values[1])
        with self.assertRaises(NodeOwnershipError): validate(tuple(values))

    def test_oversized_and_surrogate_strings_are_normalized_and_prechecked(self):
        import kil.v3b2_node_ownership as module
        values = fixtures(); values[0]["uid"] = "x" * 129
        with patch("kil.v3b2_node_ownership._utf8", wraps=module._utf8) as encode:
            with self.assertRaises(NodeOwnershipError): validate(values)
            self.assertNotIn(unittest.mock.call("x" * 129), encode.call_args_list)
        for value in ("bad\ud800", "\udfff"):
            values = fixtures(); values[0]["uid"] = value
            with self.assertRaises(NodeOwnershipError): validate(values)

    def test_family_cardinality_is_checked_before_record_work(self):
        values = list(fixtures()); values[1] = values[1][:-1]
        with patch("kil.v3b2_node_ownership._text") as text:
            with self.assertRaises(NodeOwnershipError): validate(tuple(values))
            text.assert_not_called()

    def test_binding_constructors_revalidate_fields(self):
        proof = validate()
        daemon = proof.daemon_pods[0]
        static = proof.static_pods[0]
        for cls, arguments in (
            (DaemonPodBinding, {field.name: getattr(daemon, field.name) for field in fields(daemon)}),
            (StaticPodBinding, {field.name: getattr(static, field.name) for field in fields(static)}),
        ):
            for key in arguments:
                bad = dict(arguments)
                value = bad[key]
                if key.endswith("resource_version"): bad[key] = "0"
                elif key.endswith("hash"): bad[key] = "A" * 64
                elif key == "namespace": bad[key] = "default"
                elif key == "node_name": bad[key] = "other"
                elif key == "component": bad[key] = "other"
                elif key == "daemon_set_name": bad[key] = "other"
                elif key == "pod_name": bad[key] = "other"
                else: bad[key] = 3 if type(value) is str else "bad"
                with self.subTest(cls=cls.__name__, key=key):
                    with self.assertRaises(NodeOwnershipError): cls(**bad)

    def test_proof_rejects_reordering_counts_collisions_and_runtime_true(self):
        proof = validate()
        base = {field.name: getattr(proof, field.name) for field in fields(proof)}
        changes = (
            {"daemon_pods": tuple(reversed(proof.daemon_pods))},
            {"daemon_pods": proof.daemon_pods[:1]},
            {"static_pods": tuple(reversed(proof.static_pods))},
            {"static_pods": proof.static_pods[:3]},
            {"runtime_complete": True}, {"runtime_complete": 0},
            {"node_name": "other"}, {"node_uid": proof.daemon_pods[0].pod_uid},
            {"node_uid": "uid-distinct-node"},
        )
        for change in changes:
            arguments = dict(base); arguments.update(change)
            with self.subTest(change=change):
                with self.assertRaises(NodeOwnershipError): NodeOwnershipProof(**arguments)

    def test_proof_rejects_static_owner_uid_drift_and_partial_binding(self):
        proof = validate()
        original = proof.static_pods[0]
        arguments = {field.name: getattr(original, field.name) for field in fields(original)}
        arguments["owner_node_uid"] = "uid-other-node"
        drifted = StaticPodBinding(**arguments)
        with self.assertRaises(NodeOwnershipError): NodeOwnershipProof(
            proof.node_name, proof.node_uid, proof.node_resource_version,
            proof.daemon_pods, (drifted, *proof.static_pods[1:]), False)

        partial = object.__new__(StaticPodBinding)
        for field in fields(original):
            if field.name != "owner_node_uid":
                object.__setattr__(partial, field.name, getattr(original, field.name))
        with self.assertRaises(NodeOwnershipError): NodeOwnershipProof(
            proof.node_name, proof.node_uid, proof.node_resource_version,
            proof.daemon_pods, (partial, *proof.static_pods[1:]), False)

    def test_proof_rejects_partial_and_forged_bindings(self):
        proof = validate()
        forged = object.__new__(DaemonPodBinding)
        for field in fields(proof.daemon_pods[0]):
            object.__setattr__(forged, field.name, getattr(proof.daemon_pods[0], field.name))
        object.__setattr__(forged, "pod_uid", "bad uid")
        with self.assertRaises(NodeOwnershipError): NodeOwnershipProof(
            proof.node_name, proof.node_uid, proof.node_resource_version,
            (forged, proof.daemon_pods[1]), proof.static_pods, False)
        with self.assertRaises(NodeOwnershipError): NodeOwnershipProof(
            proof.node_name, proof.node_uid, proof.node_resource_version,
            [*proof.daemon_pods], proof.static_pods, False)


if __name__ == "__main__":
    unittest.main()
