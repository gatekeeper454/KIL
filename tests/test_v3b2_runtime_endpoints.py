"""Actual API source paths assembled from independent literal endpoint fixtures."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import unittest

from kil.v3b2_runtime_ownership import validate_runtime_ownership
from tests.test_v3b2_runtime_ownership import fixture as ownership_fixture, encode
from tests.test_v3b2_platform_endpoints import fixture as platform_fixture
from tests.test_v3b2_kil_endpoint_ownership import fixture as kil_fixture
from tests.test_v3b2_service_bindings import fixture as service_fixture

MODULE = "kil.v3b2_runtime_endpoints"


def fixture(*, profile=None, workload=None, owned_identity=None):
    options = {}
    if profile is not None: options["profile"] = profile
    if workload is not None: options["workload"] = workload
    if owned_identity is not None: options["owned_identity"] = owned_identity
    arguments = ownership_fixture(**options)
    document = json.loads(arguments["runtime_objects"])
    rows = document["items"]
    by_key = {(row["kind"], row["metadata"].get("namespace", ""), row["metadata"]["name"]): row for row in rows}
    platform = platform_fixture()
    uid_map = {}
    for projection in platform["coredns_pods"]:
        actual = by_key[("Pod", projection["namespace"], projection["name"])]
        uid_map[projection["uid"]] = actual["metadata"]["uid"]
    def remap(value):
        if type(value) is list: return [remap(item) for item in value]
        if type(value) is dict: return {key: remap(item) for key, item in value.items()}
        return uid_map.get(value, value) if type(value) is str else value
    platform = {key: remap(value) if type(value) in (dict, list) else value for key, value in platform.items()}
    _, _, _, kil_pods, kil_slices = kil_fixture(
        profile=arguments["profile"], workload=arguments["workload"])
    for projection in [*platform["coredns_pods"], *kil_pods]:
        actual = by_key[("Pod", projection["namespace"], projection["name"])]
        actual["metadata"]["creationTimestamp"] = "2026-09-07T01:02:03Z"
        actual.setdefault("spec", {})["nodeName"] = projection["nodeName"]
        actual["status"] = {key: deepcopy(projection[key]) for key in ("phase", "podIP", "podIPs", "conditions")}
        actual["status"]["conditions"].append({"type": "Initialized", "status": "True"})
    node = next(row for row in rows if row["kind"] == "Node")
    node["metadata"]["creationTimestamp"] = "2026-09-07T01:02:03Z"
    node["status"] = {"addresses": [{"type": "InternalIP", "address": "192.168.5.2"},
                                    {"type": "Hostname", "address": node["metadata"]["name"]}]}
    rows.extend(service_fixture(
        profile=arguments["profile"], workload=arguments["workload"])[3])
    for projection in platform["services"]:
        metadata = {key: deepcopy(projection[key]) for key in
                    ("namespace", "name", "uid", "resourceVersion", "creationTimestamp", "labels", "annotations")}
        spec = {key: deepcopy(value) for key, value in projection.items()
                if key not in {*metadata, "apiVersion", "kind"}}
        if spec["selector"] is None: del spec["selector"]
        rows.append({"apiVersion": "v1", "kind": "Service", "metadata": metadata, "spec": spec})
    for projection in platform["endpoints"]:
        metadata = {key: deepcopy(projection[key]) for key in
                    ("namespace", "name", "uid", "resourceVersion", "creationTimestamp", "labels")}
        rows.append({"apiVersion": "v1", "kind": "Endpoints", "metadata": metadata,
                     "subsets": deepcopy(projection["subsets"])})
    for projection in [*platform["endpoint_slices"], *kil_slices]:
        metadata = {key: deepcopy(projection[key]) for key in
                    ("namespace", "name", "uid", "resourceVersion", "labels")}
        metadata["creationTimestamp"] = projection.get("creationTimestamp", "2026-09-07T01:02:03Z")
        if projection["ownerReference"] is not None:
            metadata["ownerReferences"] = [deepcopy(projection["ownerReference"])]
        endpoints = deepcopy(projection["endpoints"])
        for endpoint in endpoints:
            for key in ("targetRef", "nodeName"):
                if endpoint[key] is None: del endpoint[key]
        rows.append({"apiVersion": "discovery.k8s.io/v1", "kind": "EndpointSlice", "metadata": metadata,
                     "addressType": projection["addressType"], "ports": deepcopy(projection["ports"]), "endpoints": endpoints})
    arguments["runtime_objects"] = encode(document)
    return arguments


class RuntimeEndpointsTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "runtime endpoints adapter is missing")
        self.module = importlib.import_module(MODULE)

    def validate(self, document=None):
        arguments = fixture()
        if document is not None: arguments["runtime_objects"] = encode(document)
        return self.module.validate_runtime_endpoints(ownership=validate_runtime_ownership(**arguments))

    def test_same_runtime_source_produces_platform_and_kil_endpoint_proofs(self):
        proof = self.validate()
        self.assertEqual(len(proof.platform_endpoints.bindings), 2)
        self.assertEqual(len(proof.kil_endpoints.bindings), 9)
        self.assertEqual(len(json.loads(proof.service_allocation.bindings)), 9)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        self.assertEqual(replace(proof), proof)

    def test_closed_services_and_slices_reject_extra_missing_and_wrong_identity(self):
        for kind in ("Service", "EndpointSlice"):
            for mode in ("missing", "extra"):
                document = json.loads(fixture()["runtime_objects"])
                index = next(i for i, row in enumerate(document["items"]) if row["kind"] == kind)
                if mode == "missing": document["items"].pop(index)
                else:
                    extra = deepcopy(document["items"][index]); extra["metadata"].update(name="foreign", uid="foreign")
                    document["items"].append(extra)
                with self.subTest(kind=kind, mode=mode), self.assertRaises(self.module.RuntimeEndpointsError): self.validate(document)

    def test_owner_ambiguity_wrong_target_and_poisoned_source_ip_fail(self):
        for mutation in ("owners", "target", "ip", "ready", "node"):
            document = json.loads(fixture()["runtime_objects"])
            row = next(row for row in document["items"] if row["kind"] == "EndpointSlice" and "ownerReferences" in row["metadata"])
            if mutation == "owners": row["metadata"]["ownerReferences"] *= 2
            elif mutation == "target": row["endpoints"][0]["targetRef"]["uid"] = "foreign"
            elif mutation == "ip": row["endpoints"][0]["addresses"] = ["10.244.99.99"]
            elif mutation == "ready": row["endpoints"][0]["conditions"]["ready"] = False
            else:
                node = next(item for item in document["items"] if item["kind"] == "Node")
                node["status"]["addresses"][0]["address"] = "192.168.5.9"
                node["addresses"] = [{"type": "InternalIP", "address": "192.168.5.2"}]
            with self.subTest(mutation=mutation), self.assertRaises(self.module.RuntimeEndpointsError): self.validate(document)

    def test_duplicate_ready_internal_ip_and_missing_platform_endpoint_rejected(self):
        for kind in ("Node", "Pod", "Endpoints"):
            document = json.loads(fixture()["runtime_objects"])
            if kind == "Node":
                row = next(row for row in document["items"] if row["kind"] == kind)
                row["status"]["addresses"].append(deepcopy(row["status"]["addresses"][0]))
            elif kind == "Pod":
                row = next(row for row in document["items"] if row["kind"] == kind and "conditions" in row.get("status", {}))
                row["status"]["conditions"].append(deepcopy(row["status"]["conditions"][0]))
            else: document["items"] = [row for row in document["items"] if row["kind"] != kind]
            with self.assertRaises(self.module.RuntimeEndpointsError): self.validate(document)

    def test_constructor_revalidates_ownership_source_and_all_subproofs(self):
        proof = self.validate()
        for changes in ({"ownership": None}, {"platform_endpoints": None}, {"kil_endpoints": None},
                        {"service_allocation": None}, {"runtime_contract_complete": True},
                        {"full_application_contract_complete": True}):
            with self.assertRaises(self.module.RuntimeEndpointsError): replace(proof, **changes)
        forged = deepcopy(proof.ownership); object.__setattr__(forged, "runtime_objects", b"{}")
        with self.assertRaises(self.module.RuntimeEndpointsError): replace(proof, ownership=forged)

    def test_full_service_api_additions_survive_internal_compatibility_projection(self):
        document = json.loads(fixture()["runtime_objects"])
        services = [row for row in document["items"] if row["kind"] == "Service"
                    and row["metadata"]["namespace"].startswith("kil-")]
        for row in services:
            row["status"] = {"loadBalancer": {}}
            row["metadata"].update(generation=1, managedFields=[{
                "manager": "kubectl-client-side-apply", "operation": "Update", "apiVersion": "v1",
                "fieldsType": "FieldsV1", "fieldsV1": {"f:spec": {}}}])
            row["metadata"]["annotations"]["kubectl.kubernetes.io/last-applied-configuration"] = "{}"
        proof = self.validate(document)
        retained = json.loads(proof.service_allocation.configurations)
        self.assertTrue(all("status" in row and "managedFields" in row["metadata"] for row in retained))
        self.assertTrue(all("kubectl.kubernetes.io/last-applied-configuration" in row["metadata"]["annotations"] for row in retained))
        self.assertEqual(replace(proof), proof)
        services[0]["metadata"]["unreviewed"] = "must not be stripped"
        with self.assertRaises(self.module.RuntimeEndpointsError): self.validate(document)

    def test_legacy_kil_endpoints_retained_but_unknown_identity_rejected(self):
        document = json.loads(fixture()["runtime_objects"])
        document["items"].append({"apiVersion": "v1", "kind": "Endpoints", "metadata": {
            "namespace": "kil-v3-baseline", "name": "authz", "uid": "legacy-kil-authz", "resourceVersion": "800"},
            "subsets": []})
        proof = self.validate(document)
        self.assertEqual(json.loads(proof.ownership.runtime_objects)["items"][-1]["subsets"], [])
        document["items"][-1]["metadata"]["name"] = "foreign"
        with self.assertRaises(self.module.RuntimeEndpointsError): self.validate(document)

    def test_endpoint_raw_tamper_and_replaced_allocation_cannot_reconstruct(self):
        proof = self.validate()
        allocation = deepcopy(proof.service_allocation)
        object.__setattr__(allocation, "bindings", b"[]\n")
        with self.assertRaises(self.module.RuntimeEndpointsError): replace(proof, service_allocation=allocation)
        document = json.loads(proof.ownership.runtime_objects)
        row = next(row for row in document["items"] if row["kind"] == "Service" and row["metadata"]["namespace"].startswith("kil-"))
        row["spec"].update(clusterIP="10.96.2.22", clusterIPs=["10.96.2.22"])
        replaced_ownership = replace(proof.ownership, runtime_objects=encode(document))
        with self.assertRaises(self.module.RuntimeEndpointsError): replace(proof, ownership=replaced_ownership)

    def test_contradictory_target_api_version_is_not_discarded(self):
        for kind in ("EndpointSlice", "Endpoints"):
            for field, value in (("apiVersion", "foreign/v9"), ("apiVersion", "v1"),
                                 ("resourceVersion", "42"), ("fieldPath", "spec.containers{envoy}")):
                with self.subTest(kind=kind, field=field, value=value):
                    document = json.loads(fixture()["runtime_objects"])
                    row = next(row for row in document["items"] if row["kind"] == kind
                               and row["metadata"]["namespace"] == "kube-system")
                    target = (row["endpoints"][0]["targetRef"] if kind == "EndpointSlice"
                              else row["subsets"][0]["addresses"][0]["targetRef"])
                    target[field] = value
                    with self.assertRaises(self.module.RuntimeEndpointsError): self.validate(document)


if __name__ == "__main__": unittest.main()
