from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import unittest

from kil.v3b2_runtime_ownership import validate_runtime_ownership
from tests.test_v3b2_runtime_ownership import fixture as ownership_fixture, encode

MODULE = "kil.v3b2_generated_kil_pod_configuration"


def fixture(*, profile=None, workload=None, owned_identity=None):
    options = {}
    if profile is not None: options["profile"] = profile
    if workload is not None: options["workload"] = workload
    if owned_identity is not None: options["owned_identity"] = owned_identity
    args = ownership_fixture(**options)
    document = json.loads(args["runtime_objects"])
    templates = {(row["metadata"]["namespace"], row["metadata"]["name"]): row["spec"]["template"]
                 for row in json.loads(args["rendered_objects"])["items"] if row["kind"] == "Deployment"}
    original = validate_runtime_ownership(**args)
    by_key = {(row["kind"], row["metadata"].get("namespace", ""), row["metadata"]["name"]): row for row in document["items"]}
    for index, binding in enumerate(original.deployment_ownership.bindings):
        key = (binding.namespace, binding.deployment_name)
        if key not in templates: continue
        template = deepcopy(templates[key])
        name, _, _ = binding.pods[0]
        row = by_key[("Pod", binding.namespace, name)]
        row["metadata"].update(generateName=binding.replica_set_name + "-", generation=1,
                               creationTimestamp="2026-09-08T01:02:03Z")
        row["metadata"]["labels"].update(template["metadata"]["labels"])
        row["metadata"]["annotations"] = deepcopy(template["metadata"]["annotations"])
        row["spec"] = template["spec"]
        row["spec"].update(priority=0, preemptionPolicy="PreemptLowerPriority", tolerations=[
            {"key": "node.kubernetes.io/not-ready", "operator": "Exists", "effect": "NoExecute", "tolerationSeconds": 300},
            {"key": "node.kubernetes.io/unreachable", "operator": "Exists", "effect": "NoExecute", "tolerationSeconds": 300},
        ], dnsPolicy="ClusterFirst", schedulerName="default-scheduler", serviceAccount=row["spec"]["serviceAccountName"],
            terminationGracePeriodSeconds=30)
        for container in row["spec"]["containers"]:
            container.update(terminationMessagePath="/dev/termination-log", terminationMessagePolicy="File")
        row["status"] = {"phase": "Pending", "conditions": [{"type": "Ready", "status": "False"}]}
    args["runtime_objects"] = encode(document)
    return args


def generated(document):
    return [row for row in document["items"] if row["kind"] == "Pod"
            and row["metadata"].get("namespace", "").startswith("kil-") and row["metadata"]["name"] != "driver"]


class GeneratedKilPodConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "generated configuration module missing")
        self.module = importlib.import_module(MODULE)

    def validate(self, document=None):
        args = fixture()
        if document is not None: args["runtime_objects"] = encode(document)
        return self.module.validate_generated_kil_pod_configuration(ownership=validate_runtime_ownership(**args))

    def test_exact_templates_owner_generated_metadata_without_readiness(self):
        proof = self.validate()
        self.assertEqual(len(proof.bindings), 9)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)

    def test_generate_name_run_hash_owner_uid_and_unknown_metadata_fail(self):
        mutations = [
            lambda row: row["metadata"].update(generateName="foreign-"),
            lambda row: row["metadata"]["annotations"].update({"kil.dev/run-id": "v3b2-" + "f" * 64}),
            lambda row: row["metadata"]["labels"].update({"pod-template-hash": "foreign"}),
            lambda row: row["metadata"]["ownerReferences"][0].update(uid="foreign"),
            lambda row: row["metadata"].update(unknown="unreviewed"),
            lambda row: row["metadata"].pop("generateName"),
        ]
        for mutate in mutations:
            document = json.loads(fixture()["runtime_objects"]); mutate(generated(document)[0])
            with self.assertRaises(ValueError): self.validate(document)

    def test_template_command_probe_security_resource_container_and_volume_changes_fail(self):
        mutations = [
            lambda row: row["spec"]["containers"][0].update(command=["foreign"]),
            lambda row: row["spec"]["containers"][0].update(readinessProbe={"exec": {"command": ["true"]}}),
            lambda row: row["spec"]["containers"][0].update(securityContext={"privileged": True}),
            lambda row: row["spec"]["containers"][0].update(resources={"limits": {"cpu": "99"}}),
            lambda row: row["spec"]["containers"].append(deepcopy(row["spec"]["containers"][0])),
            lambda row: row["spec"].update(volumes=[{"name": "token", "projected": {}}]),
            lambda row: row["spec"].update(imagePullSecrets=[]),
            lambda row: row["spec"].update(priority=False),
            lambda row: row.update(unreviewed={}),
        ]
        for mutate in mutations:
            document = json.loads(fixture()["runtime_objects"]); mutate(generated(document)[0])
            with self.assertRaises(ValueError): self.validate(document)

    def cni_document(self):
        document = json.loads(fixture()["runtime_objects"])
        for index, row in enumerate(generated(document)):
            row["spec"]["nodeName"] = "kil-v3-lab-control-plane"
            row["metadata"]["annotations"].update({"cni.projectcalico.org/podIP": f"10.244.1.{index + 1}/32",
                "cni.projectcalico.org/podIPs": f"10.244.1.{index + 1}/32", "cni.projectcalico.org/containerID": f"{index + 1:064x}"})
        return document

    def test_cni_addition_retained_and_cross_generated_driver_node_id_collisions_fail(self):
        document = self.cni_document()
        proof = self.validate(document)
        self.assertEqual(json.loads(proof.ownership.runtime_objects), document)
        for mode in ("ip", "sandbox", "driver", "driver_sandbox", "node", "unknown"):
            changed = deepcopy(document); rows = generated(changed)
            if mode == "ip":
                for field in ("podIP", "podIPs"):
                    rows[0]["metadata"]["annotations"]["cni.projectcalico.org/" + field] = "10.244.1.2/32"
            elif mode == "sandbox": rows[0]["metadata"]["annotations"]["cni.projectcalico.org/containerID"] = f"{2:064x}"
            elif mode == "node": rows[0]["metadata"]["annotations"]["cni.projectcalico.org/containerID"] = fixture()["owned_identity"].node_container_id
            elif mode == "unknown": rows[0]["metadata"]["annotations"]["cni.projectcalico.org/foreign"] = "x"
            else:
                driver = next(row for row in changed["items"] if row["kind"] == "Pod" and row["metadata"]["name"] == "driver")
                driver["spec"]["nodeName"] = "kil-v3-lab-control-plane"
                driver["metadata"]["annotations"].update({"cni.projectcalico.org/podIP": "10.244.1.1/32",
                                                          "cni.projectcalico.org/podIPs": "10.244.1.1/32"})
                if mode == "driver_sandbox":
                    driver["metadata"]["annotations"].update({"cni.projectcalico.org/podIP": "10.244.2.1/32",
                        "cni.projectcalico.org/podIPs": "10.244.2.1/32", "cni.projectcalico.org/containerID": f"{1:064x}"})
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.validate(changed)

    def test_constructor_rejects_binding_dependency_raw_and_completeness_tampering(self):
        proof = self.validate()
        for changes in ({"bindings": ()}, {"ownership": None}, {"runtime_contract_complete": True},
                        {"full_application_contract_complete": True}):
            with self.assertRaises(self.module.GeneratedKilPodConfigurationError): replace(proof, **changes)
        forged = deepcopy(proof.ownership); object.__setattr__(forged, "runtime_objects", b"{}")
        with self.assertRaises(self.module.GeneratedKilPodConfigurationError): replace(proof, ownership=forged)
        document = json.loads(proof.ownership.runtime_objects)
        generated(document)[0]["spec"]["containers"][0]["command"] = ["foreign"]
        repaired = replace(proof.ownership, runtime_objects=encode(document))
        with self.assertRaises(self.module.GeneratedKilPodConfigurationError): replace(proof, ownership=repaired)

    def test_retained_generated_uid_and_binding_repair_cannot_override_source(self):
        proof = self.validate()
        forged = deepcopy(proof.bindings[0]); object.__setattr__(forged, "uid", "forged")
        with self.assertRaises(self.module.GeneratedKilPodConfigurationError):
            replace(proof, bindings=(forged, *proof.bindings[1:]))
        document = json.loads(proof.ownership.runtime_objects)
        generated(document)[0]["metadata"]["uid"] = "new-generation"
        args = fixture(); args["runtime_objects"] = encode(document)
        replacement = validate_runtime_ownership(**args)
        with self.assertRaises(self.module.GeneratedKilPodConfigurationError): replace(proof, ownership=replacement)


if __name__ == "__main__": unittest.main()
