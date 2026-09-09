"""One full applied List; literal API additions, not normalizer-made fixtures."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import unittest

from tests.test_v3b2_driver_pod_configuration import PROFILE, WORKLOAD, IDENTITY, fixture as drivers
from kil.v3b2_manifests import render_objects

MODULE = "kil.v3b2_application_configuration"


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def fixture():
    rendered = render_objects(PROFILE, WORKLOAD)
    document = json.loads(rendered)
    driver_rows = {row["metadata"]["namespace"]: row for row in drivers()["pods"]}
    service_index = 0
    for index, row in enumerate(document["items"]):
        row["metadata"].update(uid=f"object-{index}", resourceVersion=str(index + 1),
                               creationTimestamp="2026-09-08T01:02:03Z")
        if row["kind"] == "Service":
            address = f"10.96.1.{service_index + 1}"; service_index += 1
            row["spec"].update(clusterIP=address, clusterIPs=[address], ipFamilyPolicy="SingleStack",
                               ipFamilies=["IPv4"], sessionAffinity="None", internalTrafficPolicy="Cluster")
        if row["kind"] == "Pod":
            replacement = deepcopy(driver_rows[row["metadata"]["namespace"]])
            replacement["metadata"]["uid"] = row["metadata"]["uid"]
            replacement["spec"]["nodeName"] = "kil-v3-lab-control-plane"
            replacement["metadata"]["annotations"].update({
                "cni.projectcalico.org/podIP": f"10.244.1.{index + 1}/32",
                "cni.projectcalico.org/podIPs": f"10.244.1.{index + 1}/32",
                "cni.projectcalico.org/containerID": f"{index + 1:064x}",
            })
            # Status may lag annotations. It is retained but not validated.
            replacement["status"] = {"phase": "Pending", "conditions": [{"type": "Ready", "status": "False"}]}
            document["items"][index] = replacement
    return dict(profile=PROFILE, workload=WORKLOAD, rendered_objects=rendered,
                owned_identity=IDENTITY, applied_objects=encode(document))


class ApplicationConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "application configuration module is missing")
        self.module = importlib.import_module(MODULE)

    def validate(self, document=None, **changes):
        args = fixture()
        if document is not None: args["applied_objects"] = encode(document)
        args.update(changes)
        return self.module.validate_application_configuration(**args)

    def test_same_full_list_produces_initial_service_and_driver_bindings_not_completion(self):
        proof = self.validate()
        self.assertEqual(proof.applied_objects, fixture()["applied_objects"])
        self.assertEqual(len(json.loads(proof.service_bindings)), 9)
        self.assertEqual(len(proof.driver_bindings), 3)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)
        document = json.loads(proof.applied_objects)
        expected_uids = {row["metadata"]["uid"] for row in document["items"] if row["kind"] == "Pod"}
        self.assertEqual({binding.uid for binding in proof.driver_bindings}, expected_uids)
        self.assertTrue(all("status" in row for row in document["items"] if row["kind"] == "Pod"))

    def test_exact_list_roots_cardinality_and_identity_keys(self):
        original = json.loads(fixture()["applied_objects"])
        variants = [dict(original, kind="Other"), dict(original, extra={}),
                    dict(original, items=original["items"][:-1]),
                    dict(original, items=original["items"] + [original["items"][0]])]
        duplicated = deepcopy(original); duplicated["items"][-1] = deepcopy(duplicated["items"][-2]); variants.append(duplicated)
        for value in variants:
            with self.assertRaises(self.module.ApplicationConfigurationError): self.validate(value)
        document = deepcopy(original)
        pod = next(row for row in document["items"] if row["kind"] == "Pod")
        pod["unreviewed"] = {"status": "not a permitted projection"}
        with self.assertRaises(self.module.ApplicationConfigurationError): self.validate(document)

    def test_composite_list_empty_resource_version_is_retained_and_replayed(self):
        document = json.loads(fixture()["applied_objects"])
        # kubectl v1.36.1 printGeneric emits this composite List metadata.
        document["metadata"] = {"resourceVersion": ""}
        raw = encode(document)
        try:
            proof = self.validate(applied_objects=raw)
        except self.module.ApplicationConfigurationError as error:
            self.fail(f"reviewed kubectl composite List was rejected: {error}")
        self.assertEqual(proof.applied_objects, raw)
        self.assertEqual(replace(proof), proof)
        self.assertFalse(proof.full_application_contract_complete)

    def test_composite_list_metadata_rejects_nonempty_or_unreviewed_claims(self):
        for metadata in ({"resourceVersion": "1"}, {"resourceVersion": None},
                         {"resourceVersion": False}, {"resourceVersion": 0},
                         {"resourceVersion": "", "continue": ""},
                         {"continue": ""}, {}, None, []):
            document = json.loads(fixture()["applied_objects"])
            document["metadata"] = metadata
            with self.subTest(metadata=metadata), self.assertRaises(self.module.ApplicationConfigurationError):
                self.validate(document)

    def test_all_sixty_uids_unique_including_retained_namespace(self):
        for replacement in (IDENTITY.cluster_incarnation_uid, "object-0", ""):
            document = json.loads(fixture()["applied_objects"])
            document["items"][-1]["metadata"]["uid"] = replacement
            with self.assertRaises(self.module.ApplicationConfigurationError): self.validate(document)
        document = json.loads(fixture()["applied_objects"])
        document["items"][0]["metadata"]["resourceVersion"] = True
        with self.assertRaises(self.module.ApplicationConfigurationError): self.validate(document)

    def test_service_driver_and_static_configuration_fail_independently(self):
        for kind in ("Service", "Pod", "Deployment", "NetworkPolicy", "ConfigMap"):
            document = json.loads(fixture()["applied_objects"])
            row = next(row for row in document["items"] if row["kind"] == kind)
            if kind == "Service": row["spec"]["clusterIPs"] = ["10.96.1.99"]
            elif kind == "Pod": row["spec"]["priority"] = True
            else: row["metadata"]["labels"]["foreign"] = "changed"
            with self.subTest(kind=kind), self.assertRaises(self.module.ApplicationConfigurationError): self.validate(document)

    def test_constructor_replays_same_sources_and_rejects_binding_substitution(self):
        proof = self.validate()
        for changes in ({"runtime_contract_complete": True}, {"full_application_contract_complete": True},
                        {"service_bindings": b"[]\n"}, {"driver_bindings": ()},
                        {"rendered_objects": b"{}"}, {"applied_objects": b"{}"},
                        {"workload": replace(WORKLOAD, kil_image_id="sha256:" + "8" * 64)}):
            with self.assertRaises(self.module.ApplicationConfigurationError): replace(proof, **changes)
        changed = json.loads(proof.applied_objects)
        next(row for row in changed["items"] if row["kind"] == "Pod")["metadata"]["uid"] = "replacement"
        with self.assertRaises(self.module.ApplicationConfigurationError): replace(proof, applied_objects=encode(changed))
        forged = deepcopy(proof.driver_bindings[0]); object.__setattr__(forged, "uid", "forged")
        with self.assertRaises(self.module.ApplicationConfigurationError):
            replace(proof, driver_bindings=(forged, *proof.driver_bindings[1:]))

    def test_raw_bytes_bounds_duplicate_keys_and_non_json_values_fail_closed(self):
        for raw in (b"x" * (2 * 1024 * 1024 + 1), b'{"kind":"List","kind":"List","items":[]}',
                    b'{"kind":"List","items":NaN}', b"\xff"):
            with self.assertRaises(self.module.ApplicationConfigurationError): self.validate(applied_objects=raw)

    def test_cross_family_uid_collisions_and_unknown_roots_are_rejected(self):
        for left, right in (("Service", "Pod"), ("Deployment", "ConfigMap"),
                            ("Namespace", "ServiceAccount"), ("NetworkPolicy", "Service")):
            document = json.loads(fixture()["applied_objects"])
            one = next(row for row in document["items"] if row["kind"] == left)
            two = next(row for row in document["items"] if row["kind"] == right)
            two["metadata"]["uid"] = one["metadata"]["uid"]
            with self.subTest(left=left, right=right), self.assertRaises(self.module.ApplicationConfigurationError):
                self.validate(document)
        for kind in ("Namespace", "ServiceAccount", "ConfigMap", "NetworkPolicy", "Service", "Deployment", "Pod"):
            document = json.loads(fixture()["applied_objects"])
            next(row for row in document["items"] if row["kind"] == kind)["unknown"] = {}
            with self.subTest(kind=kind), self.assertRaises(self.module.ApplicationConfigurationError): self.validate(document)

    def test_uninterpreted_status_and_original_byte_framing_are_preserved(self):
        document = json.loads(fixture()["applied_objects"])
        for row in document["items"]:
            row["status"] = {"uninterpreted": "not a readiness assertion"}
        raw = json.dumps(document, ensure_ascii=False, indent=2).encode()
        proof = self.validate(applied_objects=raw)
        self.assertEqual(proof.applied_objects, raw)
        self.assertFalse(proof.full_application_contract_complete)

    def test_forged_expected_dependency_and_deep_raw_status_fail(self):
        proof = self.validate()
        owner = deepcopy(IDENTITY); object.__setattr__(owner, "kind_cluster", "foreign")
        with self.assertRaises(self.module.ApplicationConfigurationError): replace(proof, owned_identity=owner)
        with self.assertRaises(self.module.ApplicationConfigurationError): replace(proof, driver_bindings=list(proof.driver_bindings))
        document = json.loads(proof.applied_objects)
        value = {}
        for _ in range(30): value = {"nested": value}
        document["items"][0]["status"] = value
        with self.assertRaises(self.module.ApplicationConfigurationError): self.validate(document)


if __name__ == "__main__": unittest.main()
