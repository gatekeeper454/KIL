"""Apply-time configuration projections, independent of runtime-ready fixtures."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
from pathlib import Path
import unittest

from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_manifests import WorkloadIdentity, render_objects

PROFILE = V3B2Profile.load(Path(__file__).resolve().parents[1] / "deploy/kind/v3b2-profile.json")
WORKLOAD = WorkloadIdentity("v3b2-" + "1" * 64, "sha256:" + "2" * 64,
                            "docker.io/envoyproxy/envoy@sha256:" + "3" * 64)
IDENTITY = OwnedIdentity("kil-v3-lab", "unix:///tmp/owned/kil-v3-lab/docker.sock",
                         "kil-v3-lab", "/tmp/owned/kubeconfig", "cluster-uid", "a" * 64)
MODULE = "kil.v3b2_driver_pod_configuration"


def fixture():
    rendered = render_objects(PROFILE, WORKLOAD)
    pods = [row for row in json.loads(rendered)["items"] if row["kind"] == "Pod"]
    for index, row in enumerate(pods):
        row["metadata"].update(uid=f"driver-{index}", resourceVersion=str(100 + index),
                               generation=1, creationTimestamp="2026-09-08T01:02:03Z")
        row["spec"].update(priority=0, preemptionPolicy="PreemptLowerPriority", tolerations=[
            {"key": "node.kubernetes.io/not-ready", "operator": "Exists", "effect": "NoExecute", "tolerationSeconds": 300},
            {"key": "node.kubernetes.io/unreachable", "operator": "Exists", "effect": "NoExecute", "tolerationSeconds": 300},
        ], dnsPolicy="ClusterFirst", schedulerName="default-scheduler",
            terminationGracePeriodSeconds=30, serviceAccount="driver")
        row["spec"]["containers"][0].update(terminationMessagePath="/dev/termination-log",
                                             terminationMessagePolicy="File")
    return dict(profile=PROFILE, workload=WORKLOAD, rendered_objects=rendered,
                owned_identity=IDENTITY, pods=pods)


class DriverPodConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "configuration proof module is missing")
        self.module = importlib.import_module(MODULE)

    def validate(self, **changes):
        args = fixture()
        args.update(changes)
        return self.module.validate_driver_pod_configuration(**args)

    def test_unscheduled_configuration_retains_exact_inputs_without_runtime_claim(self):
        proof = self.validate()
        self.assertFalse(proof.runtime_contract_complete)
        self.assertEqual(proof.rendered_objects, fixture()["rendered_objects"])
        self.assertEqual(json.loads(proof.pods), fixture()["pods"])
        self.assertEqual(len(proof.bindings), 3)
        self.assertEqual({binding.uid for binding in proof.bindings}, {"driver-0", "driver-1", "driver-2"})
        self.assertEqual(replace(proof), proof)

    def test_scheduled_pre_cni_configuration_uses_owned_fixed_node(self):
        rows = fixture()["pods"]
        for row in rows: row["spec"]["nodeName"] = "kil-v3-lab-control-plane"
        self.validate(pods=rows)
        rows[0]["spec"]["nodeName"] = "foreign"
        with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)

    def test_optional_managed_fields_are_validated_and_retained(self):
        rows = fixture()["pods"]
        managed = [{"manager": "kubectl-client-side-apply", "operation": "Update",
                    "apiVersion": "v1", "fieldsType": "FieldsV1",
                    "fieldsV1": {"f:spec": {"f:containers": {}}},
                    "time": "2026-09-08T01:02:03Z"}]
        rows[0]["metadata"]["managedFields"] = managed
        proof = self.validate(pods=rows)
        self.assertEqual(json.loads(proof.pods)[0]["metadata"]["managedFields"], managed)
        for value in (None, [{}], [dict(managed[0], operation="Forged")],
                      [dict(managed[0], fieldsV1={"arbitrary": {}})]):
            rows[0]["metadata"]["managedFields"] = value
            with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)

    def test_last_applied_is_bounded_retained_and_never_desired_authority(self):
        rows = fixture()["pods"]
        key = "kubectl.kubernetes.io/last-applied-configuration"
        annotation = json.dumps(rows[0], ensure_ascii=False)
        rows[0]["metadata"]["annotations"][key] = annotation
        proof = self.validate(pods=rows)
        self.assertEqual(json.loads(proof.pods)[0]["metadata"]["annotations"][key], annotation)
        # This projection's global 4096-character string cap is deliberately
        # stricter than the shared annotation-specific 262144-byte ceiling.
        rows[0]["metadata"]["annotations"][key] = "x" * 4096
        self.validate(pods=rows)
        for value in ("x" * 4097, {}, None):
            rows[0]["metadata"]["annotations"][key] = value
            with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)
        rows[0]["metadata"]["annotations"][key] = annotation
        rows[0]["spec"]["containers"][0]["image"] = "foreign:latest"
        with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)

    def test_each_admission_value_and_type_is_exact(self):
        for key, value in (("priority", False), ("priority", 1), ("preemptionPolicy", "Never"),
                           ("tolerations", []), ("imagePullSecrets", []), ("nodeName", "")):
            with self.subTest(key=key, value=value):
                rows = fixture()["pods"]; rows[0]["spec"][key] = value
                with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)
        for key in ("priority", "preemptionPolicy", "tolerations"):
            rows = fixture()["pods"]; del rows[0]["spec"][key]
            with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)

    def test_incomplete_cni_additions_are_unsupported_evidence(self):
        for key, value in (("containerID", "1" * 64), ("podIP", "10.244.1.2/32"), ("podIPs", "")):
            rows = fixture()["pods"]
            rows[0]["metadata"]["annotations"]["cni.projectcalico.org/" + key] = value
            with self.assertRaisesRegex(self.module.DriverPodConfigurationError, "CNI"):
                self.validate(pods=rows)

    def cni_rows(self, sandbox=True):
        rows = fixture()["pods"]
        for index, row in enumerate(rows):
            row["spec"]["nodeName"] = "kil-v3-lab-control-plane"
            annotations = row["metadata"]["annotations"]
            annotations["cni.projectcalico.org/podIP"] = f"10.244.1.{index + 1}/32"
            annotations["cni.projectcalico.org/podIPs"] = f"10.244.1.{index + 1}/32"
            if sandbox: annotations["cni.projectcalico.org/containerID"] = f"{index + 1:064x}"
        return rows

    def test_atomic_cni_pair_with_optional_sandbox_precedes_status(self):
        for sandbox in (False, True):
            rows = self.cni_rows(sandbox)
            proof = self.validate(pods=rows)
            self.assertEqual(json.loads(proof.pods), rows)
            self.assertFalse(proof.runtime_contract_complete)
            self.assertEqual(replace(proof), proof)
        rows = self.cni_rows()
        rows[1] = fixture()["pods"][1]
        del rows[2]["metadata"]["annotations"]["cni.projectcalico.org/containerID"]
        self.validate(pods=rows)

    def test_cni_rejects_teardown_noncanonical_outside_network_and_unknown_fields(self):
        for value in ("", "10.244.1.1", "10.244.1.1/24", "10.244.01.1/32",
                      "10.9.1.1/32", "10.244.0.0/32", "10.244.255.255/32",
                      "10.244.1.1/32,10.244.1.2/32", "::1/128", None):
            rows = self.cni_rows()
            for key in ("podIP", "podIPs"):
                rows[0]["metadata"]["annotations"]["cni.projectcalico.org/" + key] = value
            with self.subTest(value=value), self.assertRaises(self.module.DriverPodConfigurationError):
                self.validate(pods=rows)
        for key, value in (("containerID", ""), ("containerID", "A" * 64),
                           ("containerID", "containerd://" + "1" * 64),
                           ("unknown", "value"), ("podIPs", "10.244.1.9/32")):
            rows = self.cni_rows(); rows[0]["metadata"]["annotations"]["cni.projectcalico.org/" + key] = value
            with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)
        rows = self.cni_rows(); del rows[0]["spec"]["nodeName"]
        with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)

    def test_cni_ip_and_sandbox_collisions_fail_even_with_repaired_retained_bytes(self):
        proof = self.validate(pods=self.cni_rows())
        for mode in ("ip", "sandbox", "node_sandbox"):
            rows = self.cni_rows()
            annotations = rows[0]["metadata"]["annotations"]
            if mode == "ip":
                annotations["cni.projectcalico.org/podIP"] = "10.244.1.2/32"
                annotations["cni.projectcalico.org/podIPs"] = "10.244.1.2/32"
            else:
                annotations["cni.projectcalico.org/containerID"] = (
                    IDENTITY.node_container_id if mode == "node_sandbox" else f"{2:064x}")
            with self.subTest(mode=mode), self.assertRaises(self.module.DriverPodConfigurationError):
                self.validate(pods=rows)
            raw = (json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
            with self.assertRaises(self.module.DriverPodConfigurationError): replace(proof, pods=raw)

    def test_spec_and_metadata_cannot_redefine_expected_inputs(self):
        mutations = [
            lambda row: row["spec"]["containers"][0].update(image="foreign:latest"),
            lambda row: row["spec"].update(volumes=[{"name": "token", "projected": {}}]),
            lambda row: row["spec"].update(automountServiceAccountToken=True),
            lambda row: row["metadata"]["labels"].update(extra="unreviewed"),
            lambda row: row["metadata"].update(ownerReferences=[]),
            lambda row: row.update(status={"phase": "Pending"}),
        ]
        for mutate in mutations:
            rows = fixture()["pods"]; mutate(rows[0])
            with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)
        changed = json.loads(fixture()["rendered_objects"])
        changed["items"][-1]["metadata"]["labels"]["extra"] = "unreviewed"
        with self.assertRaises(self.module.DriverPodConfigurationError):
            self.validate(rendered_objects=json.dumps(changed).encode())

    def test_exact_cardinality_uid_uniqueness_and_identity_types(self):
        for rows in ([], fixture()["pods"] * 2, tuple(fixture()["pods"])):
            with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)
        for key, value in (("uid", "driver-1"), ("uid", ""), ("resourceVersion", "01"),
                           ("resourceVersion", 100), ("generation", True)):
            rows = fixture()["pods"]; rows[0]["metadata"][key] = value
            with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)
        rows = fixture()["pods"]; rows[0] = deepcopy(rows[1])
        with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)
        with self.assertRaises(self.module.DriverPodConfigurationError):
            self.validate(owned_identity=replace(IDENTITY, node_container_id=None))

    def test_driver_uids_cannot_alias_retained_cluster_namespace_uid(self):
        proof = self.validate()
        for index in range(3):
            rows = fixture()["pods"]
            rows[index]["metadata"]["uid"] = IDENTITY.cluster_incarnation_uid
            with self.assertRaisesRegex(self.module.DriverPodConfigurationError, "cluster.*UID"):
                self.validate(pods=rows)
        # Repairing both candidate bytes and retained bindings cannot bypass
        # the constructor's independent cluster-namespace identity relation.
        rows = json.loads(proof.pods)
        rows[0]["metadata"]["uid"] = IDENTITY.cluster_incarnation_uid
        bindings = tuple(replace(binding, uid=IDENTITY.cluster_incarnation_uid)
                         if binding.namespace == rows[0]["metadata"]["namespace"] else binding
                         for binding in proof.bindings)
        raw = (json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        with self.assertRaisesRegex(self.module.DriverPodConfigurationError, "cluster.*UID"):
            replace(proof, pods=raw, bindings=bindings)

    def test_retained_evidence_and_bindings_revalidate_on_constructor(self):
        proof = self.validate()
        for changes in ({"runtime_contract_complete": True}, {"pods": b"[]"},
                        {"bindings": ()}, {"rendered_objects": b"{}"},
                        {"workload": replace(WORKLOAD, kil_image_id="sha256:" + "8" * 64)}):
            with self.subTest(changes=changes):
                with self.assertRaises(self.module.DriverPodConfigurationError): replace(proof, **changes)
        forged = deepcopy(proof.bindings[0]); object.__setattr__(forged, "uid", "wrong")
        with self.assertRaises(self.module.DriverPodConfigurationError):
            replace(proof, bindings=(forged, *proof.bindings[1:]))

    def test_status_including_ready_false_is_not_part_of_configuration_projection(self):
        for ready in ("False", "True"):
            rows = fixture()["pods"]
            rows[0]["status"] = {"conditions": [{"type": "Ready", "status": ready}]}
            with self.assertRaisesRegex(self.module.DriverPodConfigurationError, "status is outside scope"):
                self.validate(pods=rows)
        # No readiness bit is needed when the documented projection is supplied.
        self.assertFalse(self.validate().runtime_contract_complete)

    def test_constructor_rejects_forged_dependencies_and_noncanonical_raw_bytes(self):
        proof = self.validate()
        owner = deepcopy(IDENTITY)
        object.__setattr__(owner, "kind_cluster", "foreign")
        profile = deepcopy(PROFILE)
        object.__setattr__(profile, "pod_subnet", "10.9.0.0/16")
        for changes in ({"owned_identity": owner}, {"profile": profile},
                        {"pods": proof.pods + b" "},
                        {"pods": proof.pods.replace(b'"kind":"Pod"', b'"kind":"Pod","kind":"Pod"', 1)},
                        {"pods": b"x" * 196609}):
            with self.assertRaises(self.module.DriverPodConfigurationError): replace(proof, **changes)
        rows = json.loads(proof.pods)
        rows[0]["metadata"]["uid"] = "replaced-uid"
        repaired_bytes = (json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        with self.assertRaises(self.module.DriverPodConfigurationError): replace(proof, pods=repaired_bytes)

    def test_bounded_json_projection_rejects_deep_large_and_non_json_data(self):
        for value in ("x" * 65537, float("nan"), {"x": set()}):
            rows = fixture()["pods"]; rows[0]["spec"]["unreviewed"] = value
            with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)
        value = {}
        for _ in range(30): value = {"nested": value}
        rows = fixture()["pods"]; rows[0]["spec"]["unreviewed"] = value
        with self.assertRaises(self.module.DriverPodConfigurationError): self.validate(pods=rows)


if __name__ == "__main__": unittest.main()
