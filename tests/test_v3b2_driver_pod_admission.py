from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_driver_pod_admission import (
    DriverPodAdmissionError,
    validate_driver_pod_admission,
)
from kil.v3b2_manifests import WorkloadIdentity, render_objects
from tests.test_v3b2_platform_endpoints import fixture as platform_fixture
from kil.v3b2_platform_endpoints import validate_platform_endpoints


ROOT = Path(__file__).resolve().parents[1]
PROFILE = V3B2Profile.load(ROOT / "deploy/kind/v3b2-profile.json")
WORKLOAD = WorkloadIdentity(
    "v3b2-" + "1" * 64,
    "sha256:" + "2" * 64,
    "docker.io/envoyproxy/envoy@sha256:" + "3" * 64,
)
STAMP = "2026-09-08T01:02:03Z"
NODE = "kil-v3-lab-control-plane"
KIL_CONFIG_DIGEST = "sha256:" + "4" * 64


class StringSubclass(str):
    pass


def desired_document():
    return json.loads(render_objects(PROFILE, WORKLOAD))


def platform_proof():
    return validate_platform_endpoints(**platform_fixture())


def observed_pods():
    desired = [item for item in desired_document()["items"] if item["kind"] == "Pod"]
    result = []
    for index, item in enumerate(sorted(desired, key=lambda row: row["metadata"]["namespace"]), 1):
        row = deepcopy(item)
        row["metadata"].update({
            "uid": f"driver-uid-{index}", "resourceVersion": str(800 + index),
            "generation": 1, "creationTimestamp": STAMP,
        })
        row["metadata"]["annotations"].update({
            "cni.projectcalico.org/containerID": f"{index:064x}",
            "cni.projectcalico.org/podIP": f"10.244.1.{index}/32",
            "cni.projectcalico.org/podIPs": f"10.244.1.{index}/32",
        })
        row["spec"].update({
            "nodeName": NODE, "priority": 0,
            "preemptionPolicy": "PreemptLowerPriority",
            "tolerations": [
                {"key": "node.kubernetes.io/not-ready", "operator": "Exists",
                 "effect": "NoExecute", "tolerationSeconds": 300},
                {"key": "node.kubernetes.io/unreachable", "operator": "Exists",
                 "effect": "NoExecute", "tolerationSeconds": 300},
            ],
        })
        # Independently spell the pinned API's defaults, rather than using the
        # production normalizer to manufacture the fixture.
        row["spec"].update({"dnsPolicy": "ClusterFirst", "schedulerName": "default-scheduler",
                            "terminationGracePeriodSeconds": 30})
        row["spec"].setdefault("securityContext", {})
        row["spec"]["serviceAccount"] = "driver"
        container = row["spec"]["containers"][0]
        container.update({"terminationMessagePath": "/dev/termination-log",
                          "terminationMessagePolicy": "File"})
        ip = f"10.244.1.{index}"
        container_id = f"containerd://{index + 10:064x}"
        row["status"] = {
            "phase": "Running", "hostIP": "192.168.5.2", "podIP": ip,
            "podIPs": [{"ip": ip}],
            "conditions": [{"type": "Ready", "status": "True"}],
            "containerStatuses": [{
                "name": "driver", "image": container["image"],
                "imageID": KIL_CONFIG_DIGEST, "containerID": container_id,
                "ready": True, "started": True, "restartCount": 0,
                "state": {"running": {"startedAt": STAMP}},
            }],
        }
        result.append(row)
    return result


_MISSING = object()


def validate(pods=_MISSING, proof=None, rendered=None):
    return validate_driver_pod_admission(
        profile=PROFILE, workload=WORKLOAD,
        expected_kil_config_digest=KIL_CONFIG_DIGEST,
        rendered_objects=desired_document() if rendered is None else rendered,
        platform_endpoints=platform_proof() if proof is None else proof,
        pods=observed_pods() if pods is _MISSING else pods,
    )


class DriverPodAdmissionTest(unittest.TestCase):
    def test_accepts_exact_three_direct_driver_pods_and_returns_closed_proof(self):
        proof = validate()
        self.assertEqual(tuple(field.name for field in fields(proof)),
                         ("node_name", "node_uid", "node_resource_version",
                          "node_internal_ip", "workload", "expected_kil_config_digest",
                          "platform_endpoints",
                          "bindings", "runtime_contract_complete"))
        self.assertNotEqual(proof.workload.kil_image_id,
                            proof.expected_kil_config_digest)
        self.assertEqual(len(proof.bindings), 3)
        self.assertEqual(tuple(binding.namespace for binding in proof.bindings),
                         ("kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed"))
        self.assertFalse(proof.runtime_contract_complete)
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            proof.node_name = "changed"
        with self.assertRaises(DriverPodAdmissionError):
            replace(proof, runtime_contract_complete=True)
        other = WorkloadIdentity("v3b2-" + "9" * 64, WORKLOAD.kil_image_id,
                                 WORKLOAD.envoy_image_digest)
        with self.assertRaises(DriverPodAdmissionError):
            replace(proof, workload=other)
        with self.assertRaises(DriverPodAdmissionError):
            replace(proof, expected_kil_config_digest="sha256:" + "8" * 64)
        bindings = list(proof.bindings)
        bindings[0] = replace(bindings[0], uid=proof.platform_endpoints.dependency_uids[0])
        with self.assertRaises(DriverPodAdmissionError):
            replace(proof, bindings=tuple(bindings))
        with self.assertRaises(DriverPodAdmissionError):
            replace(proof, node_name=StringSubclass(proof.node_name))
        with self.assertRaises(DriverPodAdmissionError):
            replace(proof.bindings[0],
                    namespace=StringSubclass(proof.bindings[0].namespace))
        with self.assertRaises(DriverPodAdmissionError):
            replace(proof.bindings[0], name=StringSubclass("driver"))
        bindings = list(proof.bindings)
        bindings[0] = replace(bindings[0], uid=proof.platform_endpoints.bindings[0].service_uid)
        with self.assertRaises(DriverPodAdmissionError):
            replace(proof, bindings=tuple(bindings))
        bindings = list(proof.bindings)
        bindings[0] = replace(bindings[0], pod_ip=proof.platform_endpoints.coredns_pods[0].address)
        with self.assertRaises(DriverPodAdmissionError):
            replace(proof, bindings=tuple(bindings))
        bindings = list(proof.bindings)
        bindings[0] = replace(
            bindings[0],
            cni_sandbox_id=bindings[1].app_container_id.removeprefix("containerd://"),
        )
        with self.assertRaises(DriverPodAdmissionError):
            replace(proof, bindings=tuple(bindings))

    def test_requires_exact_desired_manifest_and_direct_pod_admission_fields(self):
        mutations = [
            ("priority", 1), ("preemptionPolicy", "Never"), ("nodeName", "other"),
            ("restartPolicy", "Always"), ("automountServiceAccountToken", True),
            ("enableServiceLinks", True), ("serviceAccountName", "default"),
            ("serviceAccount", "default"), ("imagePullSecrets", [{"name": "foreign"}]),
        ]
        for key, value in mutations:
            pods = observed_pods(); pods[0]["spec"][key] = value
            with self.subTest(key=key), self.assertRaises(DriverPodAdmissionError): validate(pods)
        pods = observed_pods(); pods[0]["spec"]["tolerations"][0]["tolerationSeconds"] = 301
        with self.assertRaises(DriverPodAdmissionError): validate(pods)
        pods = observed_pods()
        first_sandbox = pods[0]["metadata"]["annotations"]["cni.projectcalico.org/containerID"]
        pods[1]["status"]["containerStatuses"][0]["containerID"] = "containerd://" + first_sandbox
        with self.assertRaises(DriverPodAdmissionError): validate(pods)
        pods = observed_pods(); pods[0]["spec"]["containers"][0]["volumeMounts"] = [{"name": "token", "mountPath": "/var/run/secrets/kubernetes.io/serviceaccount"}]
        with self.assertRaises(DriverPodAdmissionError): validate(pods)

    def test_rejects_metadata_ownership_deletion_and_unexpected_mutations(self):
        cases = (("uid", ""), ("resourceVersion", "01"), ("generation", 2),
                 ("creationTimestamp", "not-time"), ("labels", {}),
                 ("ownerReferences", []), ("deletionTimestamp", None))
        for key, value in cases:
            pods = observed_pods(); pods[0]["metadata"][key] = value
            with self.subTest(key=key), self.assertRaises(DriverPodAdmissionError): validate(pods)

    def test_binds_distinct_cni_sandbox_runtime_container_and_status_network(self):
        paths = [
            ("annotation-container", "A" * 64),
            ("annotation-podIP", "10.244.1.9/32"),
            ("annotation-podIPs", "10.244.1.9/32"),
            ("status-podIP", "10.244.1.9"),
            ("status-podIPs", [{"ip": "10.244.1.9"}]),
            ("hostIP", "192.168.5.3"),
            ("containerID", "docker://" + "b" * 64),
            ("imageID", "sha256:" + "9" * 64),
            ("ready", False), ("started", False), ("restartCount", 1),
        ]
        for path, value in paths:
            pods = observed_pods(); row = pods[0]
            if path.startswith("annotation-"):
                suffix = {"annotation-container": "containerID"}.get(path, path[11:])
                row["metadata"]["annotations"]["cni.projectcalico.org/" + suffix] = value
            elif path in {"status-podIP", "status-podIPs"}:
                row["status"][path[7:]] = value
            elif path == "hostIP": row["status"][path] = value
            else: row["status"]["containerStatuses"][0][path] = value
            with self.subTest(path=path), self.assertRaises(DriverPodAdmissionError): validate(pods)
        pods = observed_pods()
        pods[0]["status"]["containerStatuses"][0]["containerID"] = "containerd://" + pods[0]["metadata"]["annotations"]["cni.projectcalico.org/containerID"]
        with self.assertRaises(DriverPodAdmissionError): validate(pods)

    def test_rejects_waiting_terminated_or_open_container_state(self):
        for state in ({"waiting": {"reason": "Starting"}},
                      {"terminated": {"exitCode": 0}},
                      {"running": {"startedAt": STAMP}, "waiting": {}}):
            pods = observed_pods()
            pods[0]["status"]["containerStatuses"][0]["state"] = state
            with self.subTest(state=state), self.assertRaises(DriverPodAdmissionError):
                validate(pods)

    def test_revalidates_forged_platform_proof_and_rejects_cross_domain_collisions(self):
        proof = platform_proof(); object.__setattr__(proof, "node_internal_ip", "192.168.5.3")
        with self.assertRaises(DriverPodAdmissionError): validate(proof=proof)
        pods = observed_pods(); pods[0]["metadata"]["uid"] = platform_proof().dependency_uids[0]
        with self.assertRaises(DriverPodAdmissionError): validate(pods)
        pods = observed_pods(); pods[0]["metadata"]["uid"] = platform_proof().bindings[0].service_uid
        with self.assertRaises(DriverPodAdmissionError): validate(pods)
        pods = observed_pods(); pods[0]["status"]["podIP"] = "10.244.0.20"; pods[0]["status"]["podIPs"] = [{"ip": "10.244.0.20"}]
        pods[0]["metadata"]["annotations"]["cni.projectcalico.org/podIP"] = "10.244.0.20/32"
        pods[0]["metadata"]["annotations"]["cni.projectcalico.org/podIPs"] = "10.244.0.20/32"
        with self.assertRaises(DriverPodAdmissionError): validate(pods)

    def test_rejects_wrong_cardinality_types_and_duplicate_incarnations(self):
        for value in (None, tuple(observed_pods()), observed_pods()[:2], observed_pods() + [observed_pods()[0]]):
            with self.subTest(value=type(value).__name__), self.assertRaises(DriverPodAdmissionError): validate(value)
        pods = observed_pods(); pods[1]["metadata"]["uid"] = pods[0]["metadata"]["uid"]
        with self.assertRaises(DriverPodAdmissionError): validate(pods)
        pods = observed_pods(); duplicate_ip = pods[0]["status"]["podIP"]
        pods[1]["status"]["podIP"] = duplicate_ip
        pods[1]["status"]["podIPs"] = [{"ip": duplicate_ip}]
        pods[1]["metadata"]["annotations"]["cni.projectcalico.org/podIP"] = duplicate_ip + "/32"
        pods[1]["metadata"]["annotations"]["cni.projectcalico.org/podIPs"] = duplicate_ip + "/32"
        with self.assertRaises(DriverPodAdmissionError): validate(pods)

    def test_malformed_pod_cardinality_fails_before_dependency_or_render_traversal(self):
        class PoisonDict(dict):
            def __deepcopy__(self, memo):
                raise AssertionError("rendered input was traversed")

        proof = platform_proof()
        with patch.object(type(proof), "__post_init__",
                          side_effect=AssertionError("dependency was traversed")):
            with self.assertRaises(DriverPodAdmissionError):
                validate_driver_pod_admission(
                    profile=PROFILE, workload=WORKLOAD,
                    expected_kil_config_digest=KIL_CONFIG_DIGEST,
                    rendered_objects=PoisonDict(), platform_endpoints=proof,
                    pods=[{}] * 4,
                )

    def test_rendered_bytes_accept_only_the_exact_canonical_bounded_output(self):
        canonical = render_objects(PROFILE, WORKLOAD)
        self.assertEqual(validate(rendered=canonical).workload, WORKLOAD)
        duplicate_root_key = canonical.replace(
            b'{"apiVersion":', b'{"apiVersion":"evil","apiVersion":', 1,
        )
        deep = b"[" * 20_000 + b"0" + b"]" * 20_000
        oversized = b"x" * (2 * 1024 * 1024 + 1)
        for payload in (duplicate_root_key, deep, oversized):
            with self.subTest(size=len(payload)), self.assertRaises(DriverPodAdmissionError):
                validate(rendered=payload)


if __name__ == "__main__":
    unittest.main()
