from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import patch

import kil.v3b2_deployment_ownership as ownership
from kil.v3b2_deployment_ownership import (
    DeploymentBinding,
    DeploymentOwnershipError,
    DeploymentOwnershipProof,
    validate_deployment_ownership,
)


APPLICATION_NAMESPACES = (
    "kil-v3-baseline",
    "kil-v3-local-reduce",
    "kil-v3-signed",
)


class StrSubclass(str):
    pass


class ListSubclass(list):
    pass


class DictSubclass(dict):
    pass


class TupleSubclass(tuple):
    pass


def expected_deployments() -> tuple[tuple[str, str, int], ...]:
    records = [
        ("kube-system", "coredns", 2),
        ("kube-system", "calico-kube-controllers", 1),
        ("local-path-storage", "local-path-provisioner", 1),
    ]
    records.extend(
        (namespace, name, 1)
        for namespace in APPLICATION_NAMESPACES
        for name in ("authz", "envoy", "target")
    )
    return tuple(sorted(records))


def observation() -> tuple[list[dict], list[dict], list[dict]]:
    deployments: list[dict] = []
    replica_sets: list[dict] = []
    pods: list[dict] = []
    for index, (namespace, name, replicas) in enumerate(expected_deployments(), 1):
        deployment_uid = f"deployment-uid-{index}"
        replica_set_uid = f"replicaset-uid-{index}"
        hash_value = f"h{index:09d}"
        replica_set_name = f"{name}-{hash_value}"
        deployments.append({
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "namespace": namespace,
            "name": name,
            "uid": deployment_uid,
            "resourceVersion": str(100 + index),
            "revision": "1",
            "replicas": replicas,
        })
        replica_sets.append({
            "apiVersion": "apps/v1",
            "kind": "ReplicaSet",
            "namespace": namespace,
            "name": replica_set_name,
            "uid": replica_set_uid,
            "resourceVersion": str(200 + index),
            "revision": "1",
            "podTemplateHash": hash_value,
            "ownerReference": {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": name,
                "uid": deployment_uid,
                "controller": True,
                "blockOwnerDeletion": True,
            },
        })
        for pod_index in range(replicas):
            pods.append({
                "apiVersion": "v1",
                "kind": "Pod",
                "namespace": namespace,
                "name": f"{replica_set_name}-p{pod_index:04d}",
                "uid": f"pod-uid-{index}-{pod_index}",
                "resourceVersion": str(300 + index * 2 + pod_index),
                "podTemplateHash": hash_value,
                "ownerReference": {
                    "apiVersion": "apps/v1",
                    "kind": "ReplicaSet",
                    "name": replica_set_name,
                    "uid": replica_set_uid,
                    "controller": True,
                    "blockOwnerDeletion": True,
                },
            })
    return deployments, replica_sets, pods


def validate(
    deployments: list[dict], replica_sets: list[dict], pods: list[dict],
) -> DeploymentOwnershipProof:
    return validate_deployment_ownership(
        deployments=deployments,
        replica_sets=replica_sets,
        pods=pods,
        application_namespaces=APPLICATION_NAMESPACES,
    )


class DeploymentOwnershipTest(unittest.TestCase):
    def setUp(self) -> None:
        self.deployments, self.replica_sets, self.pods = observation()

    def assert_invalid(self, deployments=None, replica_sets=None, pods=None, namespaces=None):
        with self.assertRaises(DeploymentOwnershipError):
            validate_deployment_ownership(
                deployments=self.deployments if deployments is None else deployments,
                replica_sets=self.replica_sets if replica_sets is None else replica_sets,
                pods=self.pods if pods is None else pods,
                application_namespaces=(
                    APPLICATION_NAMESPACES if namespaces is None else namespaces
                ),
            )

    def test_nominal_projection_returns_closed_immutable_proof(self) -> None:
        proof = validate(self.deployments, self.replica_sets, self.pods)
        self.assertEqual(len(proof.bindings), 12)
        self.assertEqual(sum(len(binding.pods) for binding in proof.bindings), 13)
        coredns = next(
            binding for binding in proof.bindings
            if (binding.namespace, binding.deployment_name) == ("kube-system", "coredns")
        )
        self.assertEqual(coredns.replicas, 2)
        self.assertEqual(len(coredns.pods), 2)
        self.assertEqual(coredns.revision, "1")
        self.assertFalse(proof.runtime_contract_complete)
        with self.assertRaises(FrozenInstanceError):
            proof.runtime_contract_complete = True

    def test_input_order_does_not_change_canonical_proof(self) -> None:
        expected = validate(self.deployments, self.replica_sets, self.pods)
        actual = validate(
            list(reversed(self.deployments)),
            list(reversed(self.replica_sets)),
            list(reversed(self.pods)),
        )
        self.assertEqual(actual, expected)
        self.assertEqual(actual.bindings, tuple(sorted(actual.bindings)))
        self.assertTrue(all(binding.pods == tuple(sorted(binding.pods)) for binding in actual.bindings))

    def test_missing_extra_and_duplicate_deployments_are_rejected(self) -> None:
        self.assert_invalid(deployments=self.deployments[:-1])
        extra = deepcopy(self.deployments)
        extra[-1] = {**extra[-1], "name": "unexpected"}
        self.assert_invalid(deployments=extra)
        duplicate = deepcopy(self.deployments)
        duplicate[-1] = deepcopy(duplicate[0])
        self.assert_invalid(deployments=duplicate)

    def test_missing_extra_and_duplicate_replica_sets_are_rejected(self) -> None:
        self.assert_invalid(replica_sets=self.replica_sets[:-1])
        extra = deepcopy(self.replica_sets)
        extra[-1]["ownerReference"]["name"] = "unexpected"
        self.assert_invalid(replica_sets=extra)
        duplicate = deepcopy(self.replica_sets)
        duplicate[-1] = deepcopy(duplicate[0])
        self.assert_invalid(replica_sets=duplicate)

    def test_missing_extra_and_duplicate_pods_are_rejected(self) -> None:
        self.assert_invalid(pods=self.pods[:-1])
        extra = deepcopy(self.pods)
        extra[-1]["ownerReference"]["name"] = "unexpected"
        self.assert_invalid(pods=extra)
        duplicate = deepcopy(self.pods)
        duplicate[-1] = deepcopy(duplicate[0])
        self.assert_invalid(pods=duplicate)

    def test_replica_count_is_derived_and_exact(self) -> None:
        changed = deepcopy(self.deployments)
        changed[0]["replicas"] = 1 if changed[0]["replicas"] == 2 else 2
        self.assert_invalid(deployments=changed)
        changed = deepcopy(self.pods)
        changed[0]["ownerReference"] = deepcopy(changed[1]["ownerReference"])
        changed[0]["namespace"] = changed[1]["namespace"]
        changed[0]["podTemplateHash"] = changed[1]["podTemplateHash"]
        changed[0]["name"] = changed[1]["name"][:-5] + "z9999"
        self.assert_invalid(pods=changed)

    def test_replica_set_owner_reference_is_closed_and_uid_bound(self) -> None:
        for key, value in (
            ("name", "envoy"), ("uid", "wrong-uid"),
            ("apiVersion", "v1"), ("kind", "ReplicaSet"),
            ("controller", False), ("blockOwnerDeletion", False),
        ):
            changed = deepcopy(self.replica_sets)
            changed[0]["ownerReference"][key] = value
            self.assert_invalid(replica_sets=changed)
        changed = deepcopy(self.replica_sets)
        changed[0]["ownerReference"]["extra"] = "open"
        self.assert_invalid(replica_sets=changed)

    def test_pod_owner_reference_is_closed_and_uid_bound(self) -> None:
        for key, value in (
            ("name", "coredns-h000000001"), ("uid", "wrong-uid"),
            ("apiVersion", "v1"), ("kind", "Deployment"),
            ("controller", False), ("blockOwnerDeletion", False),
        ):
            changed = deepcopy(self.pods)
            changed[0]["ownerReference"][key] = value
            self.assert_invalid(pods=changed)
        changed = deepcopy(self.pods)
        changed[0]["ownerReference"]["extra"] = "open"
        self.assert_invalid(pods=changed)

    def test_name_prefix_never_substitutes_for_owner_uid(self) -> None:
        changed = deepcopy(self.pods)
        changed[0]["ownerReference"]["uid"] = self.replica_sets[1]["uid"]
        self.assertTrue(changed[0]["name"].startswith(changed[0]["ownerReference"]["name"]))
        self.assert_invalid(pods=changed)

    def test_cross_namespace_owner_joins_are_rejected(self) -> None:
        changed = deepcopy(self.replica_sets)
        changed[0]["namespace"] = self.replica_sets[-1]["namespace"]
        self.assert_invalid(replica_sets=changed)
        changed = deepcopy(self.pods)
        changed[0]["namespace"] = self.pods[-1]["namespace"]
        self.assert_invalid(pods=changed)

    def test_native_variable_length_hash_keeps_complete_owner_name_graph(self) -> None:
        for hash_value in ('d8cb8bc6b', '5', '5c9bdbff57'):
            replicas = deepcopy(self.replica_sets)
            pods = deepcopy(self.pods)
            old_name = replicas[0]['name']
            name = replicas[0]['ownerReference']['name'] + '-' + hash_value
            replicas[0].update(name=name, podTemplateHash=hash_value)
            for pod in pods:
                if pod['ownerReference']['name'] == old_name:
                    pod['name'] = name + '-' + pod['name'].rsplit('-', 1)[1]
                    pod['podTemplateHash'] = hash_value
                    pod['ownerReference']['name'] = name
            proof = validate(self.deployments, replicas, pods)
            self.assertEqual(len(proof.bindings), 12)
            self.assert_invalid(replica_sets=replicas)  # old Pods cannot join
        for hash_value in ('', 'd8cb8bc6b99', 'D8CB8BC6B', 'd8cb8bc6_'):
            replicas = deepcopy(self.replica_sets)
            replicas[0]['podTemplateHash'] = hash_value
            self.assert_invalid(replica_sets=replicas)

    def test_hash_replica_set_name_and_pod_suffix_are_exact(self) -> None:
        for field, value in (
            ("podTemplateHash", "SHORT"),
            ("podTemplateHash", "h00000000_"),
            ("name", self.replica_sets[0]["name"] + "x"),
        ):
            changed = deepcopy(self.replica_sets)
            changed[0][field] = value
            self.assert_invalid(replica_sets=changed)
        changed = deepcopy(self.pods)
        changed[0]["podTemplateHash"] = "h999999999"
        self.assert_invalid(pods=changed)
        for name in (self.pods[0]["name"][:-1], self.pods[0]["name"][:-1] + "_"):
            changed = deepcopy(self.pods)
            changed[0]["name"] = name
            self.assert_invalid(pods=changed)

    def test_deployment_and_replica_set_revisions_are_fresh_and_equal(self) -> None:
        changed = deepcopy(self.deployments)
        changed[0]["revision"] = "2"
        self.assert_invalid(deployments=changed)
        changed = deepcopy(self.replica_sets)
        changed[0]["revision"] = "2"
        self.assert_invalid(replica_sets=changed)

    def test_uid_collisions_across_all_record_families_are_rejected(self) -> None:
        changed = deepcopy(self.replica_sets)
        changed[0]["uid"] = self.deployments[0]["uid"]
        changed[0]["ownerReference"]["uid"] = self.deployments[0]["uid"]
        self.assert_invalid(replica_sets=changed)
        changed = deepcopy(self.pods)
        changed[0]["uid"] = self.replica_sets[0]["uid"]
        self.assert_invalid(pods=changed)

    def test_closed_records_reject_missing_extra_and_wrong_identity(self) -> None:
        for family, records in (
            ("deployment", self.deployments),
            ("replica_set", self.replica_sets),
            ("pod", self.pods),
        ):
            for operation in ("missing", "extra"):
                changed = deepcopy(records)
                if operation == "missing":
                    changed[0].pop("resourceVersion")
                else:
                    changed[0]["extra"] = "open"
                kwargs = {"deployments": changed} if family == "deployment" else (
                    {"replica_sets": changed} if family == "replica_set" else {"pods": changed}
                )
                self.assert_invalid(**kwargs)
        for family, records in (("deployments", self.deployments), ("replica_sets", self.replica_sets), ("pods", self.pods)):
            changed = deepcopy(records)
            changed[0]["apiVersion"] = "v2"
            self.assert_invalid(**{family: changed})
            changed = deepcopy(records)
            changed[0]["kind"] = "Service"
            self.assert_invalid(**{family: changed})

    def test_resource_versions_uids_names_and_exact_types_are_strict(self) -> None:
        for value in ("0", "01", "18446744073709551616", 1, True):
            changed = deepcopy(self.deployments)
            changed[0]["resourceVersion"] = value
            self.assert_invalid(deployments=changed)
        for field, value in (("uid", ""), ("name", "Bad_Name"), ("namespace", "Bad_NS")):
            changed = deepcopy(self.deployments)
            changed[0][field] = value
            self.assert_invalid(deployments=changed)
        changed = deepcopy(self.deployments)
        changed[0]["replicas"] = True
        self.assert_invalid(deployments=changed)
        changed = deepcopy(self.deployments)
        changed[0]["name"] = StrSubclass(changed[0]["name"])
        self.assert_invalid(deployments=changed)
        self.assert_invalid(deployments=ListSubclass(self.deployments))
        changed = deepcopy(self.deployments)
        changed[0] = DictSubclass(changed[0])
        self.assert_invalid(deployments=changed)

    def test_oversized_and_surrogate_strings_are_normalized(self) -> None:
        for value in ("x" * 10_000_000, "uid-\ud800"):
            changed = deepcopy(self.deployments)
            changed[0]["uid"] = value
            self.assert_invalid(deployments=changed)

    def test_wide_dict_is_rejected_before_key_visitation_or_set_allocation(self) -> None:
        wide = {f"key-{index}": index for index in range(100_000)}
        with patch.object(ownership, "any", side_effect=AssertionError("visited"), create=True), \
             patch.object(ownership, "set", side_effect=AssertionError("allocated"), create=True):
            with self.assertRaises(DeploymentOwnershipError):
                ownership._closed(wide, frozenset({"only"}), "wide")

    def test_wide_pod_tuple_is_rejected_before_element_visitation(self) -> None:
        wide = tuple(("pod", "uid", "1") for _ in range(100_000))
        with patch.object(ownership, "_name", side_effect=AssertionError("visited")):
            with self.assertRaises(DeploymentOwnershipError):
                ownership._pod_tuple(wide, expected_count=1)

    def test_wide_proof_tuple_is_rejected_before_binding_visitation(self) -> None:
        proof = validate(self.deployments, self.replica_sets, self.pods)
        wide = proof.bindings * 10_000
        with patch.object(
            DeploymentBinding, "__post_init__", side_effect=AssertionError("visited"),
        ):
            with self.assertRaises(DeploymentOwnershipError):
                DeploymentOwnershipProof(APPLICATION_NAMESPACES, wide, False)

    def test_application_namespaces_are_exact_pinned_and_sorted(self) -> None:
        self.assert_invalid(namespaces=tuple(reversed(APPLICATION_NAMESPACES)))
        self.assert_invalid(namespaces=APPLICATION_NAMESPACES[:-1])
        self.assert_invalid(namespaces=TupleSubclass(APPLICATION_NAMESPACES))
        changed = list(APPLICATION_NAMESPACES)
        changed[0] = StrSubclass(changed[0])
        self.assert_invalid(namespaces=tuple(changed))

    def test_binding_constructor_revalidates_all_internal_invariants(self) -> None:
        proof = validate(self.deployments, self.replica_sets, self.pods)
        binding = next(item for item in proof.bindings if item.replicas == 2)
        for changes in (
            {"revision": "2"},
            {"replicas": True},
            {"replicas": binding.replicas + 1},
            {"deployment_name": "unexpected"},
            {"replica_set_name": binding.replica_set_name + "x"},
            {"pod_template_hash": "BAD"},
            {"pods": tuple(reversed(binding.pods))},
            {"pods": TupleSubclass(binding.pods)},
            {"deployment_uid": binding.replica_set_uid},
        ):
            with self.assertRaises(DeploymentOwnershipError):
                replace(binding, **changes)
        pod = binding.pods[0]
        forged_pods = ((StrSubclass(pod[0]), pod[1], pod[2]),) + binding.pods[1:]
        with self.assertRaises(DeploymentOwnershipError):
            replace(binding, pods=forged_pods)

    def test_proof_constructor_rejects_partial_forged_and_mutated_evidence(self) -> None:
        proof = validate(self.deployments, self.replica_sets, self.pods)
        with self.assertRaises(DeploymentOwnershipError):
            replace(proof, bindings=proof.bindings[:-1])
        with self.assertRaises(DeploymentOwnershipError):
            replace(proof, bindings=tuple(reversed(proof.bindings)))
        with self.assertRaises(DeploymentOwnershipError):
            replace(proof, bindings=TupleSubclass(proof.bindings))
        with self.assertRaises(DeploymentOwnershipError):
            replace(proof, runtime_contract_complete=True)
        forged = deepcopy(proof)
        duplicate = replace(forged.bindings[1], deployment_uid=forged.bindings[0].deployment_uid)
        bindings = (forged.bindings[0], duplicate) + forged.bindings[2:]
        with self.assertRaises(DeploymentOwnershipError):
            DeploymentOwnershipProof(APPLICATION_NAMESPACES, bindings, False)
        object.__setattr__(forged.bindings[0], "revision", "2")
        with self.assertRaises(DeploymentOwnershipError):
            replace(forged)

    def test_exports_are_an_immutable_closed_tuple(self) -> None:
        import kil.v3b2_deployment_ownership as module

        self.assertIs(type(module.__all__), tuple)
        self.assertEqual(module.__all__, (
            "DeploymentOwnershipError",
            "DeploymentBinding",
            "DeploymentOwnershipProof",
            "validate_deployment_ownership",
        ))


if __name__ == "__main__":
    unittest.main()
