"""Full API source-path fixtures; no production extraction helper builds them."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import unittest

from kil.v3b2_manifests import render_objects
from tests.test_v3b2_driver_pod_configuration import PROFILE, WORKLOAD, IDENTITY
from tests.test_v3b2_deployment_ownership import observation
from tests.test_v3b2_node_ownership import fixtures

MODULE = "kil.v3b2_runtime_ownership"


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def fixture():
    # The existing independent literal owner records are placed into actual API
    # paths here. They are candidate data, never supplied as expected authority.
    deployments, replicas, generated = observation()
    node, daemons, daemon_pods, static_pods = fixtures()
    rows = []
    for record in [*deployments, *replicas, *generated, node, *daemons, *daemon_pods, *static_pods]:
        metadata = {key: record[key] for key in ("name", "uid", "resourceVersion")}
        if "namespace" in record: metadata["namespace"] = record["namespace"]
        row = {"apiVersion": record["apiVersion"], "kind": record["kind"], "metadata": metadata}
        if "revision" in record: metadata["annotations"] = {"deployment.kubernetes.io/revision": record["revision"]}
        if "podTemplateHash" in record: metadata["labels"] = {"pod-template-hash": record["podTemplateHash"]}
        if "ownerReference" in record: metadata["ownerReferences"] = [deepcopy(record["ownerReference"])]
        if record["kind"] == "Deployment":
            row["spec"] = {"replicas": record["replicas"]}
            row["status"] = {"readyReplicas": 0, "replicas": 0}
        if record["kind"] == "ReplicaSet": row["spec"] = {"replicas": 1}
        if record["kind"] == "DaemonSet": row["status"] = {"desiredNumberScheduled": record["desiredNumberScheduled"]}
        if "nodeName" in record: row["spec"] = {"nodeName": record["nodeName"]}
        if "component" in record:
            metadata["labels"] = {"component": record["component"]}
            metadata["annotations"] = {"kubernetes.io/config.source": record["configSource"],
                "kubernetes.io/config.hash": record["configHash"], "kubernetes.io/config.mirror": record["mirrorHash"]}
        rows.append(row)
    for index, row in enumerate(json.loads(render_objects(PROFILE, WORKLOAD))["items"]):
        if row["kind"] == "Pod":
            row["metadata"].update(uid=f"direct-{index}", resourceVersion="10")
            rows.append(row)
    rows.append({"apiVersion": "v1", "kind": "Namespace", "metadata": {
        "name": "kube-system", "uid": IDENTITY.cluster_incarnation_uid, "resourceVersion": "99"}})
    return dict(profile=PROFILE, workload=WORKLOAD, rendered_objects=render_objects(PROFILE, WORKLOAD),
                owned_identity=IDENTITY, runtime_objects=encode({"apiVersion": "v1", "kind": "List",
                    "metadata": {"resourceVersion": ""}, "items": rows}))


class RuntimeOwnershipTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "runtime ownership adapter is missing")
        self.module = importlib.import_module(MODULE)

    def validate(self, document=None, **changes):
        args = fixture()
        if document is not None: args["runtime_objects"] = encode(document)
        args.update(changes)
        return self.module.validate_runtime_ownership(**args)

    def test_source_paths_produce_exact_ownership_without_readiness(self):
        proof = self.validate()
        self.assertEqual(len(proof.deployment_ownership.bindings), 12)
        self.assertEqual(sum(len(row.pods) for row in proof.deployment_ownership.bindings), 13)
        self.assertEqual(len(proof.node_ownership.daemon_pods), 2)
        self.assertEqual(len(proof.node_ownership.static_pods), 4)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(proof.runtime_objects, fixture()["runtime_objects"])
        self.assertEqual(replace(proof), proof)

    def test_full_list_preserves_kubelet_static_mirror_producer_records(self):
        args = fixture()
        document = json.loads(args["runtime_objects"])
        statics = [row for row in document["items"] if
                   "kubernetes.io/config.mirror" in row["metadata"].get("annotations", {})]
        self.assertEqual(len(statics), 4)
        for row in statics:
            annotations = row["metadata"]["annotations"]
            self.assertRegex(annotations["kubernetes.io/config.hash"], r"^[0-9a-f]{32}$")
            self.assertEqual(annotations["kubernetes.io/config.hash"],
                             annotations["kubernetes.io/config.mirror"])
            owners = row["metadata"]["ownerReferences"]
            self.assertEqual(len(owners), 1)
            self.assertEqual(set(owners[0]), {"apiVersion", "kind", "name", "uid", "controller"})
            self.assertIs(owners[0]["controller"], True)
        proof = self.module.validate_runtime_ownership(**args)
        self.assertEqual(proof.runtime_objects, args["runtime_objects"])
        self.assertEqual(len(proof.node_ownership.static_pods), 4)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)

    def test_replica_count_comes_from_spec_not_poisoned_top_level_or_status(self):
        document = json.loads(fixture()["runtime_objects"])
        row = next(row for row in document["items"] if row["kind"] == "Deployment")
        row["spec"]["replicas"] = 0
        row["replicas"] = 1; row["status"] = {"replicas": 1, "readyReplicas": 1}
        with self.assertRaises(self.module.RuntimeOwnershipError): self.validate(document)

    def test_owner_reference_list_must_be_exactly_one_at_real_metadata_path(self):
        for owners in ([], None, {}, [{}, {}]):
            document = json.loads(fixture()["runtime_objects"])
            row = next(row for row in document["items"] if row["kind"] == "ReplicaSet")
            row["ownerReference"] = row["metadata"]["ownerReferences"][0]
            row["metadata"]["ownerReferences"] = owners
            with self.assertRaises(self.module.RuntimeOwnershipError): self.validate(document)

    def test_extra_missing_ownership_objects_and_direct_driver_owner_fail(self):
        for kind in ("Deployment", "ReplicaSet", "DaemonSet", "Node", "Pod"):
            for mode in ("missing", "extra"):
                document = json.loads(fixture()["runtime_objects"])
                index = next(i for i, row in enumerate(document["items"]) if row["kind"] == kind)
                if mode == "missing": document["items"].pop(index)
                else:
                    extra = deepcopy(document["items"][index]); extra["metadata"].update(name="foreign", uid="foreign")
                    document["items"].append(extra)
                with self.subTest(kind=kind, mode=mode), self.assertRaises(self.module.RuntimeOwnershipError): self.validate(document)
        document = json.loads(fixture()["runtime_objects"])
        row = next(row for row in document["items"] if row["kind"] == "Pod" and row["metadata"]["name"] == "driver")
        row["metadata"]["ownerReferences"] = []
        with self.assertRaises(self.module.RuntimeOwnershipError): self.validate(document)

    def test_source_annotation_label_node_and_daemon_count_poison_fails(self):
        for kind, path, field, value in (("ReplicaSet", "labels", "pod-template-hash", "wrong"),
                                       ("Deployment", "annotations", "deployment.kubernetes.io/revision", "2")):
            document = json.loads(fixture()["runtime_objects"])
            row = next(row for row in document["items"] if row["kind"] == kind)
            row["metadata"][path][field] = value
            with self.assertRaises(self.module.RuntimeOwnershipError): self.validate(document)
        document = json.loads(fixture()["runtime_objects"])
        next(row for row in document["items"] if row["kind"] == "DaemonSet")["status"]["desiredNumberScheduled"] = True
        with self.assertRaises(self.module.RuntimeOwnershipError): self.validate(document)
        document = json.loads(fixture()["runtime_objects"])
        next(row for row in document["items"] if row["kind"] == "Node")["metadata"]["name"] = "foreign"
        with self.assertRaises(self.module.RuntimeOwnershipError): self.validate(document)

    def test_global_identity_and_uid_collisions_include_uninterpreted_families(self):
        document = json.loads(fixture()["runtime_objects"])
        document["items"][-1]["metadata"]["uid"] = document["items"][0]["metadata"]["uid"]
        with self.assertRaises(self.module.RuntimeOwnershipError): self.validate(document)

    def test_direct_driver_exception_requires_exact_api_identity(self):
        document = json.loads(fixture()["runtime_objects"])
        row = next(row for row in document["items"] if row["kind"] == "Pod" and row["metadata"]["name"] == "driver")
        row["apiVersion"] = "apps/v1"
        with self.assertRaises(self.module.RuntimeOwnershipError): self.validate(document)

    def test_raw_duplicate_keys_bounds_and_non_json_values_are_rejected(self):
        for raw in (b"x" * (8 * 1024 * 1024 + 1), b'{"kind":"List","kind":"List"}', b"\xff"):
            with self.assertRaises(self.module.RuntimeOwnershipError): self.validate(runtime_objects=raw)
        document = json.loads(fixture()["runtime_objects"])
        document["items"][-1]["status"] = {"value": float("nan")}
        with self.assertRaises(self.module.RuntimeOwnershipError): self.validate(document)
        document = json.loads(fixture()["runtime_objects"]); document["items"].append(deepcopy(document["items"][-1]))
        with self.assertRaises(self.module.RuntimeOwnershipError): self.validate(document)

    def test_reconstruction_rejects_replaced_subproof_raw_and_expected_inputs(self):
        proof = self.validate()
        for changes in ({"runtime_contract_complete": True}, {"full_application_contract_complete": True},
                        {"runtime_objects": b"{}"}, {"rendered_objects": b"{}"},
                        {"node_ownership": None}, {"deployment_ownership": None},
                        {"workload": replace(WORKLOAD, kil_image_id="sha256:" + "8" * 64)}):
            with self.assertRaises(self.module.RuntimeOwnershipError): replace(proof, **changes)
        forged = deepcopy(proof.node_ownership); object.__setattr__(forged, "node_uid", "foreign")
        with self.assertRaises(self.module.RuntimeOwnershipError): replace(proof, node_ownership=forged)


if __name__ == "__main__": unittest.main()
