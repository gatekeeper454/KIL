"""Closed ownership evidence for the nine KIL EndpointSlices."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import unittest
from unittest.mock import patch

import kil.v3b2_kil_endpoint_ownership as endpoint_ownership
from kil.v3b2_kil_endpoint_ownership import (
    KilEndpointBinding,
    KilEndpointOwnershipError,
    KilEndpointOwnershipProof,
    validate_kil_endpoint_ownership,
)
from kil.v3b2_deployment_ownership import validate_deployment_ownership
from kil.v3b2_service_bindings import validate_service_allocations
from tests.test_v3b2_deployment_ownership import (
    APPLICATION_NAMESPACES,
    observation as deployment_observation,
)
from tests.test_v3b2_service_bindings import fixture as service_fixture


class ListSubclass(list):
    pass


class DictSubclass(dict):
    pass


class StrSubclass(str):
    pass


def fixture():
    profile, workload, _, services = service_fixture()
    deployments, replica_sets, owned_pods = deployment_observation()
    deployment_proof = validate_deployment_ownership(
        deployments=deployments,
        replica_sets=replica_sets,
        pods=owned_pods,
        application_namespaces=APPLICATION_NAMESPACES,
    )
    service_allocation = validate_service_allocations(
        services, profile=profile, workload=workload,
    )
    service_bindings = {
        (row["namespace"], row["name"]): row
        for row in json.loads(service_allocation.bindings)
    }
    deployment_bindings = {
        (binding.namespace, binding.deployment_name): binding
        for binding in deployment_proof.bindings
    }
    pods, slices = [], []
    for index, key in enumerate(sorted(service_bindings), 11):
        namespace, service_name = key
        service = service_bindings[key]
        pod_name, pod_uid, pod_rv = deployment_bindings[key].pods[0]
        pod_ip = f"10.244.0.{index}"
        pods.append({
            "apiVersion": "v1",
            "kind": "Pod",
            "namespace": namespace,
            "name": pod_name,
            "uid": pod_uid,
            "resourceVersion": pod_rv,
            "nodeName": "kil-v3-lab-control-plane",
            "phase": "Running",
            "deletionTimestamp": None,
            "podIP": pod_ip,
            "podIPs": [{"ip": pod_ip}],
            "conditions": [{"type": "Ready", "status": "True"}],
        })
        slices.append({
            "apiVersion": "discovery.k8s.io/v1",
            "kind": "EndpointSlice",
            "namespace": namespace,
            "name": f"{service_name}-s{index:04d}",
            "uid": f"endpointslice-uid-{index}",
            "resourceVersion": str(600 + index),
            "labels": {
                "kubernetes.io/service-name": service_name,
                "endpointslice.kubernetes.io/managed-by":
                    "endpointslice-controller.k8s.io",
            },
            "ownerReference": {
                "apiVersion": "v1",
                "kind": "Service",
                "name": service_name,
                "uid": service["uid"],
                "controller": True,
                "blockOwnerDeletion": True,
            },
            "addressType": "IPv4",
            "ports": [{"name": "http", "protocol": "TCP", "port": 8080}],
            "endpoints": [{
                "addresses": [pod_ip],
                "conditions": {
                    "ready": True,
                    "serving": True,
                    "terminating": False,
                },
                "targetRef": {
                    "kind": "Pod",
                    "namespace": namespace,
                    "name": pod_name,
                    "uid": pod_uid,
                },
                "nodeName": "kil-v3-lab-control-plane",
            }],
        })
    return profile, deployment_proof, service_allocation, pods, slices


class KilEndpointOwnershipTest(unittest.TestCase):
    def setUp(self):
        (self.profile, self.deployment_proof, self.service_allocation,
         self.pods, self.slices) = fixture()

    def validate(self, *, pods=None, slices=None, profile=None,
                 deployment_proof=None, service_allocation=None):
        return validate_kil_endpoint_ownership(
            pods=self.pods if pods is None else pods,
            endpoint_slices=self.slices if slices is None else slices,
            profile=self.profile if profile is None else profile,
            deployment_proof=(self.deployment_proof if deployment_proof is None
                              else deployment_proof),
            service_allocation=(self.service_allocation if service_allocation is None
                                else service_allocation),
        )

    def assert_invalid(self, **kwargs):
        with self.assertRaises(KilEndpointOwnershipError):
            self.validate(**kwargs)

    def test_nominal_result_is_closed_immutable_and_canonical(self):
        before_pods, before_slices = deepcopy(self.pods), deepcopy(self.slices)
        proof = self.validate(
            pods=list(reversed(self.pods)), slices=list(reversed(self.slices)),
        )
        self.assertEqual(len(proof.bindings), 9)
        self.assertEqual(proof.bindings, tuple(sorted(proof.bindings)))
        self.assertEqual(
            {(row.namespace, row.service_name) for row in proof.bindings},
            {(namespace, role) for namespace in APPLICATION_NAMESPACES
             for role in ("authz", "envoy", "target")},
        )
        self.assertEqual(proof.node_name, "kil-v3-lab-control-plane")
        self.assertFalse(proof.runtime_contract_complete)
        self.assertEqual(self.pods, before_pods)
        self.assertEqual(self.slices, before_slices)
        with self.assertRaises(FrozenInstanceError):
            proof.runtime_contract_complete = True

    def test_pods_are_exactly_the_nine_owned_application_pods(self):
        self.assert_invalid(pods=self.pods[:-1])
        self.assert_invalid(pods=self.pods + [deepcopy(self.pods[0])])
        changed = deepcopy(self.pods)
        changed[0]["uid"] = changed[1]["uid"]
        self.assert_invalid(pods=changed)
        for field, value in (
            ("name", "foreign-pod"), ("uid", "foreign-uid"),
            ("resourceVersion", "999"), ("namespace", "default"),
        ):
            with self.subTest(field=field):
                changed = deepcopy(self.pods)
                changed[0][field] = value
                self.assert_invalid(pods=changed)

    def test_pod_network_identity_is_exact_single_stack_ipv4(self):
        values = (None, True, 1, "", "10.244.0.011", "10.244.0.11 ", "::1",
                  "10.243.255.254", "10.245.0.1", "10.244.0.0")
        for value in values:
            with self.subTest(value=value):
                changed = deepcopy(self.pods)
                changed[0]["podIP"] = value
                changed[0]["podIPs"] = [{"ip": value}]
                self.assert_invalid(pods=changed)
        for value in (None, True, "10.244.0.11", [], [{"ip": "10.244.0.12"}],
                      [{"ip": "10.244.0.11"}, {"ip": "10.244.0.12"}],
                      [{"ip": "10.244.0.11", "extra": True}]):
            with self.subTest(pod_ips=value):
                changed = deepcopy(self.pods)
                changed[0]["podIPs"] = value
                self.assert_invalid(pods=changed)
        changed = deepcopy(self.pods)
        changed[0]["podIP"] = changed[1]["podIP"]
        changed[0]["podIPs"] = deepcopy(changed[1]["podIPs"])
        self.assert_invalid(pods=changed)

    def test_pod_liveness_and_readiness_are_exact(self):
        changes = (
            ("nodeName", "other-node"), ("phase", "Pending"),
            ("deletionTimestamp", "2026-09-07T00:00:00Z"),
            ("conditions", []),
            ("conditions", [{"type": "ContainersReady", "status": "True"}]),
            ("conditions", [{"type": "Ready", "status": "False"}]),
            ("conditions", [{"type": "Ready", "status": "Unknown"}]),
            ("conditions", [{"type": "Ready", "status": "True", "reason": "x"}]),
            ("conditions", [{"type": "Ready", "status": "True"},
                            {"type": "Ready", "status": "True"}]),
        )
        for field, value in changes:
            with self.subTest(field=field, value=value):
                changed = deepcopy(self.pods)
                changed[0][field] = value
                self.assert_invalid(pods=changed)

    def test_endpoint_slice_service_ownership_and_labels_are_exact(self):
        mutations = (
            ("ownerReference", "apiVersion", "apps/v1"),
            ("ownerReference", "kind", "Deployment"),
            ("ownerReference", "name", "target"),
            ("ownerReference", "uid", "forged-service-uid"),
            ("ownerReference", "controller", False),
            ("ownerReference", "blockOwnerDeletion", False),
            ("labels", "kubernetes.io/service-name", "target"),
            ("labels", "endpointslice.kubernetes.io/managed-by", "foreign"),
        )
        for parent, field, value in mutations:
            with self.subTest(parent=parent, field=field):
                changed = deepcopy(self.slices)
                changed[0][parent][field] = value
                self.assert_invalid(slices=changed)
        for parent, field in (("ownerReference", "uid"),
                              ("labels", "endpointslice.kubernetes.io/managed-by")):
            changed = deepcopy(self.slices)
            del changed[0][parent][field]
            self.assert_invalid(slices=changed)

    def test_endpoint_slice_shape_cardinality_and_identity_are_exact(self):
        self.assert_invalid(slices=self.slices[:-1])
        self.assert_invalid(slices=self.slices + [deepcopy(self.slices[0])])
        for field, value in (
            ("apiVersion", "v1"), ("kind", "Endpoints"),
            ("namespace", "default"), ("name", "foreign-s0001"),
            ("addressType", "IPv6"), ("ports", []),
            ("ports", [deepcopy(self.slices[0]["ports"][0])] * 2),
            ("endpoints", []),
            ("endpoints", [deepcopy(self.slices[0]["endpoints"][0])] * 2),
        ):
            with self.subTest(field=field):
                changed = deepcopy(self.slices)
                changed[0][field] = value
                self.assert_invalid(slices=changed)
        for collection in (self.pods, self.slices):
            changed = deepcopy(collection)
            changed[0]["extra"] = None
            self.assert_invalid(**({"pods": changed} if collection is self.pods
                                   else {"slices": changed}))

    def test_endpoint_slice_name_identity_is_namespaced(self):
        changed = deepcopy(self.slices)
        for row in changed:
            if row["labels"]["kubernetes.io/service-name"] == "authz":
                row["name"] = "authz-same1"
        proof = self.validate(slices=changed)
        authz_names = [binding.endpoint_slice_name for binding in proof.bindings
                       if binding.service_name == "authz"]
        self.assertEqual(authz_names, ["authz-same1"] * 3)

    def test_endpoint_port_is_exactly_resolved_from_service_configuration(self):
        for field, value in (("name", "other"), ("protocol", "UDP"),
                             ("port", 80), ("port", True), ("appProtocol", "http")):
            with self.subTest(field=field):
                changed = deepcopy(self.slices)
                changed[0]["ports"][0][field] = value
                self.assert_invalid(slices=changed)

    def test_endpoint_exactly_targets_the_ready_owned_pod(self):
        mutations = (
            ("targetRef", "kind", "Service"),
            ("targetRef", "namespace", "default"),
            ("targetRef", "name", "foreign"),
            ("targetRef", "uid", "foreign-uid"),
            ("conditions", "ready", False),
            ("conditions", "serving", False),
            ("conditions", "terminating", True),
        )
        for parent, field, value in mutations:
            with self.subTest(parent=parent, field=field):
                changed = deepcopy(self.slices)
                changed[0]["endpoints"][0][parent][field] = value
                self.assert_invalid(slices=changed)
        for field, value in (
            ("addresses", ["10.244.0.99"]),
            ("addresses", [self.pods[0]["podIP"], "10.244.0.99"]),
            ("nodeName", "other-node"),
        ):
            changed = deepcopy(self.slices)
            changed[0]["endpoints"][0][field] = value
            self.assert_invalid(slices=changed)

    def test_endpoint_rejects_fields_not_emitted_by_pinned_controller(self):
        for field, value in (("hostname", "host"), ("hints", {}),
                             ("zone", "zone-a"), ("deprecatedTopology", {})):
            with self.subTest(field=field):
                changed = deepcopy(self.slices)
                changed[0]["endpoints"][0][field] = value
                self.assert_invalid(slices=changed)
        changed = deepcopy(self.slices)
        changed[0]["endpoints"][0]["targetRef"]["apiVersion"] = "v1"
        self.assert_invalid(slices=changed)

    def test_uid_generated_names_and_resource_versions_are_exact(self):
        source = deepcopy(self.pods)
        source[0]["resourceVersion"] = source[1]["resourceVersion"]
        self.assert_invalid(pods=source)  # differs from retained Deployment proof
        source = deepcopy(self.slices)
        source[0]["resourceVersion"] = source[1]["resourceVersion"]
        self.validate(slices=source)  # RV is not a cross-object identity invariant
        changed = deepcopy(self.slices)
        changed[0]["uid"] = changed[1]["uid"]
        self.assert_invalid(slices=changed)
        for field, value in (("resourceVersion", "0"), ("resourceVersion", "01"),
                             ("resourceVersion", str(2**64)), ("uid", ""),
                             ("uid", "u" * 257), ("name", "authz-too-long" + "x" * 64)):
            with self.subTest(field=field):
                changed = deepcopy(self.slices)
                changed[0][field] = value
                self.assert_invalid(slices=changed)

    def test_all_resource_uid_sites_require_exact_api_uid_syntax(self):
        for invalid_uid in (" uid", "uid with space", "uid/with/slash", "u" * 129):
            with self.subTest(site="Pod", uid=invalid_uid):
                pods = deepcopy(self.pods)
                pods[0]["uid"] = invalid_uid
                self.assert_invalid(pods=pods)
            with self.subTest(site="targetRef", uid=invalid_uid):
                slices = deepcopy(self.slices)
                slices[0]["endpoints"][0]["targetRef"]["uid"] = invalid_uid
                self.assert_invalid(slices=slices)
            with self.subTest(site="EndpointSlice", uid=invalid_uid):
                slices = deepcopy(self.slices)
                slices[0]["uid"] = invalid_uid
                self.assert_invalid(slices=slices)
            with self.subTest(site="Service owner", uid=invalid_uid):
                slices = deepcopy(self.slices)
                slices[0]["ownerReference"]["uid"] = invalid_uid
                self.assert_invalid(slices=slices)

        invalid_uid = "pod uid smuggled"
        old_uid = self.pods[0]["uid"]
        bindings = []
        for binding in self.deployment_proof.bindings:
            changed_pods = tuple(
                (name, invalid_uid if uid == old_uid else uid, resource_version)
                for name, uid, resource_version in binding.pods
            )
            bindings.append(replace(binding, pods=changed_pods))
        forged_deployment_proof = replace(
            self.deployment_proof, bindings=tuple(sorted(bindings)),
        )
        pods = deepcopy(self.pods)
        next(row for row in pods if row["uid"] == old_uid)["uid"] = invalid_uid
        slices = deepcopy(self.slices)
        for row in slices:
            if row["endpoints"][0]["targetRef"]["uid"] == old_uid:
                row["endpoints"][0]["targetRef"]["uid"] = invalid_uid
        self.assert_invalid(
            pods=pods, slices=slices,
            deployment_proof=forged_deployment_proof,
        )

    def test_exact_builtin_container_types_are_required(self):
        for field, value in (("name", StrSubclass(self.pods[0]["name"])),
                             ("resourceVersion", True), ("podIP", StrSubclass(self.pods[0]["podIP"]))):
            changed = deepcopy(self.pods)
            changed[0][field] = value
            self.assert_invalid(pods=changed)
        self.assert_invalid(pods=ListSubclass(self.pods))
        self.assert_invalid(slices=ListSubclass(self.slices))
        changed = deepcopy(self.slices)
        changed[0] = DictSubclass(changed[0])
        self.assert_invalid(slices=changed)

    def test_cardinality_and_shallow_bounds_precede_semantic_traversal(self):
        with patch.object(endpoint_ownership, "_closed", side_effect=AssertionError("traversed")):
            with self.assertRaises(KilEndpointOwnershipError):
                self.validate(pods=self.pods[:-1])
            changed = deepcopy(self.slices)
            changed[0]["uid"] = "x" * 1025
            with self.assertRaises(KilEndpointOwnershipError):
                self.validate(slices=changed)

    def test_revalidates_profile_and_accepted_proofs(self):
        object.__setattr__(self.profile, "pod_subnet", "10.245.0.0/16")
        self.assert_invalid()
        self.profile, self.deployment_proof, self.service_allocation, self.pods, self.slices = fixture()
        object.__setattr__(self.deployment_proof, "runtime_contract_complete", True)
        self.assert_invalid()
        self.profile, self.deployment_proof, self.service_allocation, self.pods, self.slices = fixture()
        object.__setattr__(self.service_allocation, "bindings", b"[]\n")
        self.assert_invalid()
        self.assert_invalid(profile={})
        self.assert_invalid(deployment_proof={})
        self.assert_invalid(service_allocation={})

    def test_service_proof_bytes_must_be_canonical_closed_and_port_pinned(self):
        for field in ("bindings", "configurations"):
            changed = replace(self.service_allocation)
            object.__setattr__(changed, field, getattr(changed, field).replace(b"\n", b" \n"))
            self.assert_invalid(service_allocation=changed)
        configurations = json.loads(self.service_allocation.configurations)
        reordered = replace(self.service_allocation)
        object.__setattr__(reordered, "configurations",
                           endpoint_ownership._canonical(list(reversed(configurations))))
        self.assert_invalid(service_allocation=reordered)
        configurations[0]["spec"]["ports"][0]["targetPort"] = 80
        changed = replace(self.service_allocation)
        object.__setattr__(changed, "configurations", endpoint_ownership._canonical(configurations))
        self.assert_invalid(service_allocation=changed)

    def test_service_proof_cannot_smuggle_invalid_api_uid_timestamp_or_run_id(self):
        for invalid_uid in (" uid", "uid with space", "uid/with/slash", "u" * 129):
            with self.subTest(uid=invalid_uid):
                bindings = json.loads(self.service_allocation.bindings)
                configurations = json.loads(self.service_allocation.configurations)
                old_uid = bindings[0]["uid"]
                bindings[0]["uid"] = invalid_uid
                matching_key = (bindings[0]["namespace"], bindings[0]["name"])
                for row in configurations:
                    if (row["metadata"]["namespace"], row["metadata"]["name"]) == matching_key:
                        row["metadata"]["uid"] = invalid_uid
                slices = deepcopy(self.slices)
                for row in slices:
                    if row["ownerReference"]["uid"] == old_uid:
                        row["ownerReference"]["uid"] = invalid_uid
                allocation = replace(self.service_allocation)
                object.__setattr__(allocation, "bindings", endpoint_ownership._canonical(bindings))
                object.__setattr__(allocation, "configurations",
                                   endpoint_ownership._canonical(configurations))
                self.assert_invalid(service_allocation=allocation, slices=slices)

        for invalid_timestamp in ("not-a-date", "2026-99-99T00:00:00Z",
                                  "2026-09-07 00:00:00Z", None):
            with self.subTest(timestamp=invalid_timestamp):
                configurations = json.loads(self.service_allocation.configurations)
                configurations[0]["metadata"]["creationTimestamp"] = invalid_timestamp
                allocation = replace(self.service_allocation)
                object.__setattr__(allocation, "configurations",
                                   endpoint_ownership._canonical(configurations))
                self.assert_invalid(service_allocation=allocation)

        for invalid_run_id in ("not-v3b2", "v3b2-" + "A" * 64,
                               "v3b2-" + "1" * 63, " v3b2-" + "1" * 64):
            with self.subTest(run_id=invalid_run_id):
                configurations = json.loads(self.service_allocation.configurations)
                for row in configurations:
                    row["metadata"]["annotations"]["kil.dev/run-id"] = invalid_run_id
                allocation = replace(self.service_allocation)
                object.__setattr__(allocation, "configurations",
                                   endpoint_ownership._canonical(configurations))
                self.assert_invalid(service_allocation=allocation)

    def test_proof_and_binding_constructors_reject_forgery(self):
        proof = self.validate()
        with self.assertRaises(KilEndpointOwnershipError):
            KilEndpointOwnershipProof(
                proof.application_namespaces, proof.node_name,
                proof.bindings[:-1], False,
            )
        with self.assertRaises(KilEndpointOwnershipError):
            KilEndpointOwnershipProof(
                proof.application_namespaces, proof.node_name,
                tuple(reversed(proof.bindings)), False,
            )
        with self.assertRaises(KilEndpointOwnershipError):
            replace(proof.bindings[0], pod_ip="10.245.0.1")
        with self.assertRaises(KilEndpointOwnershipError):
            replace(proof.bindings[0], pod_name="foreign-pod")
        with self.assertRaises(KilEndpointOwnershipError):
            replace(proof.bindings[0], pod_uid="pod uid")
        with self.assertRaises(KilEndpointOwnershipError):
            replace(proof.bindings[0], service_uid="service uid")
        with self.assertRaises(KilEndpointOwnershipError):
            replace(proof.bindings[0], endpoint_slice_uid="slice/uid")
        with self.assertRaises(KilEndpointOwnershipError):
            KilEndpointOwnershipProof(
                proof.application_namespaces, proof.node_name,
                proof.bindings, True,
            )


if __name__ == "__main__":
    unittest.main()
