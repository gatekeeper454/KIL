"""Pre-driver evidence removes only the three real direct-driver fixture Pods."""
from copy import deepcopy
from dataclasses import fields, replace
import importlib
import importlib.util
import json
import unittest

from kil.v3b2_runtime_ownership import RuntimeOwnershipError, RuntimeOwnershipProof, validate_runtime_ownership
from tests.test_v3b2_runtime_ownership import fixture as ready_fixture, encode

MODULE = "kil.v3b2_pre_driver_ownership"


def fixture():
    args = ready_fixture()
    document = json.loads(args["runtime_objects"])
    drivers = [row for row in document["items"]
               if row["kind"] == "Pod" and row["metadata"]["name"] == "driver"]
    assert len(drivers) == 3 and all("ownerReferences" not in row["metadata"] for row in drivers)
    document["items"] = [row for row in document["items"] if row not in drivers]
    args["runtime_objects"] = encode(document)
    return args


class PreDriverOwnershipTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "pre-driver ownership adapter is missing")
        self.module = importlib.import_module(MODULE)

    def validate(self, document=None, **changes):
        args = fixture()
        if document is not None: args["runtime_objects"] = encode(document)
        args.update(changes)
        return self.module.validate_pre_driver_ownership(**args)

    def test_retains_exact_nineteen_pod_source_and_derived_ownership(self):
        proof = self.validate()
        self.assertIs(type(proof), self.module.PreDriverOwnershipProof)
        self.assertNotIsInstance(proof, RuntimeOwnershipProof)
        for key, value in fixture().items(): self.assertEqual(getattr(proof, key), value)
        rows = json.loads(proof.runtime_objects)["items"]
        self.assertEqual(sum(row["kind"] == "Pod" for row in rows), 19)
        self.assertEqual(len(proof.deployment_ownership.bindings), 12)
        self.assertEqual(sum(len(row.pods) for row in proof.deployment_ownership.bindings), 13)
        self.assertEqual(len(proof.node_ownership.daemon_pods), 2)
        self.assertEqual(len(proof.node_ownership.static_pods), 4)
        self.assertIs(proof.runtime_contract_complete, False)
        self.assertIs(proof.full_application_contract_complete, False)
        self.assertEqual(replace(proof), proof)

    def test_ready_phase_still_rejects_nineteen_and_pre_driver_rejects_twenty_two(self):
        with self.assertRaises(RuntimeOwnershipError): validate_runtime_ownership(**fixture())
        with self.assertRaises(self.module.PreDriverOwnershipError):
            self.module.validate_pre_driver_ownership(**ready_fixture())

    def test_each_early_driver_is_rejected_even_if_pod_count_is_preserved(self):
        drivers = [row for row in json.loads(ready_fixture()["runtime_objects"])["items"]
                   if row["kind"] == "Pod" and row["metadata"]["name"] == "driver"]
        for driver in drivers:
            for preserve_count in (False, True):
                document = json.loads(fixture()["runtime_objects"])
                if preserve_count:
                    index = next(i for i, row in enumerate(document["items"]) if row["kind"] == "Pod")
                    document["items"].pop(index)
                document["items"].append(driver)
                with self.subTest(driver=driver["metadata"]["namespace"], preserve_count=preserve_count):
                    with self.assertRaises(self.module.PreDriverOwnershipError): self.validate(document)

    def test_missing_and_extra_family_objects_fail(self):
        for kind in ("Deployment", "ReplicaSet", "Pod", "Node", "DaemonSet"):
            for extra in (False, True):
                document = json.loads(fixture()["runtime_objects"])
                index = next(i for i, row in enumerate(document["items"]) if row["kind"] == kind)
                if extra:
                    row = deepcopy(document["items"][index])
                    row["metadata"].update(name="foreign", uid="foreign")
                    document["items"].append(row)
                else: document["items"].pop(index)
                with self.subTest(kind=kind, extra=extra), self.assertRaises(self.module.PreDriverOwnershipError):
                    self.validate(document)

    def test_owner_and_node_uid_tampering_fail(self):
        for kind in ("ReplicaSet", "Pod", "Node"):
            document = json.loads(fixture()["runtime_objects"])
            row = next(row for row in document["items"] if row["kind"] == kind)
            if kind == "Node": row["metadata"]["uid"] = "foreign-node"
            else: row["metadata"]["ownerReferences"][0]["uid"] = "foreign-owner"
            with self.subTest(kind=kind), self.assertRaises(self.module.PreDriverOwnershipError): self.validate(document)

    def test_global_uid_and_resource_identity_collisions_fail(self):
        for duplicate_uid in (False, True):
            document = json.loads(fixture()["runtime_objects"])
            row = deepcopy(document["items"][0])
            if duplicate_uid: row.update(apiVersion="v1", kind="ConfigMap")
            else: row["metadata"]["uid"] = "other-uid"
            document["items"].append(row)
            with self.assertRaises(self.module.PreDriverOwnershipError): self.validate(document)

    def test_raw_bounds_and_list_shape_are_shared(self):
        for raw in (b"{}", b'{"kind":"List","kind":"List"}', b"\xff", b"x" * (8 * 1024 * 1024 + 1)):
            with self.assertRaises(self.module.PreDriverOwnershipError): self.validate(runtime_objects=raw)
        document = json.loads(fixture()["runtime_objects"])
        document["items"][-1]["status"] = {"value": float("nan")}
        with self.assertRaises(self.module.PreDriverOwnershipError): self.validate(document)

    def test_context_and_raw_reconstruction_reject_tampering(self):
        proof = self.validate()
        for changes in ({"runtime_objects": b"{}"}, {"rendered_objects": b"{}"},
                        {"profile": None}, {"workload": replace(proof.workload, kil_image_id="sha256:" + "8" * 64)},
                        {"owned_identity": replace(proof.owned_identity, cluster_incarnation_uid="foreign")},
                        {"node_ownership": None}, {"deployment_ownership": None}):
            with self.subTest(changes=changes), self.assertRaises(self.module.PreDriverOwnershipError): replace(proof, **changes)
        forged = deepcopy(proof.node_ownership)
        object.__setattr__(forged, "node_uid", "foreign")
        with self.assertRaises(self.module.PreDriverOwnershipError): replace(proof, node_ownership=forged)

    def test_completion_flags_require_exact_false_on_reconstruction(self):
        proof = self.validate()
        for field in ("runtime_contract_complete", "full_application_contract_complete"):
            for value in (True, 0, None):
                with self.subTest(field=field, value=value), self.assertRaises(self.module.PreDriverOwnershipError):
                    replace(proof, **{field: value})

    def test_cross_phase_constructor_forging_fails(self):
        pre = self.validate()
        ready = validate_runtime_ownership(**ready_fixture())
        for cls, source, error in ((RuntimeOwnershipProof, pre, RuntimeOwnershipError),
                                  (self.module.PreDriverOwnershipProof, ready, self.module.PreDriverOwnershipError)):
            with self.assertRaises(error): cls(**{field.name: getattr(source, field.name) for field in fields(source)})


if __name__ == "__main__": unittest.main()
