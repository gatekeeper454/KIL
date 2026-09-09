from copy import deepcopy
from dataclasses import replace
import json
import unittest

from kil.v3b2_proofs import canonical
from kil.v3b2_policy_stage_checkpoint import encode_policy_stage_checkpoint
from tests.test_v3b2_application_configuration import fixture as configuration_fixture
from tests.test_v3b2_application_policy_stage import fixture as policy_fixture


def fixture(*, advance_rv=True):
    from kil.v3b2_application_configuration import validate_application_configuration
    from kil.v3b2_application_boundary import validate_application_boundary
    rendered, context, observations = policy_fixture()
    inputs = json.loads(context.inputs)
    inputs["applied_objects"] = inputs["application_objects"]
    context = replace(context, inputs=canonical(inputs))
    checkpoint = encode_policy_stage_checkpoint(context, observations)
    config = configuration_fixture()
    config["owned_identity"] = json.loads(context.inputs)["owned_identity"]
    from kil.v3b2_journal import OwnedIdentity
    config["owned_identity"] = OwnedIdentity(**config["owned_identity"])
    document = json.loads(config["applied_objects"])
    historical = json.loads(observations[1].stdout)["items"]
    by_key = {(row["kind"], row["metadata"].get("namespace", ""), row["metadata"]["name"]): row
              for row in historical}
    for row in document["items"]:
        key = (row["kind"], row["metadata"].get("namespace", ""), row["metadata"]["name"])
        if key in by_key:
            row["metadata"]["uid"] = by_key[key]["metadata"]["uid"]
            row["metadata"]["resourceVersion"] = (str(1000 + int(by_key[key]["metadata"]["resourceVersion"]))
                                                       if advance_rv else by_key[key]["metadata"]["resourceVersion"])
    config["applied_objects"] = (json.dumps(document, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":")) + "\n").encode()
    configuration = validate_application_configuration(**config)
    proof = validate_application_boundary(context=context, checkpoint_bytes=checkpoint,
                                            configuration=configuration)
    return context, checkpoint, configuration, proof


def decision_fixture():
    from kil.v3b2_proofs import RawObservation
    context, checkpoint, configuration, _ = fixture()
    inputs = json.loads(context.inputs); inputs["prior_service_bindings"] = None
    context = replace(context, inputs=canonical(inputs))
    # The checkpoint is necessarily committed to the final expected context.
    _, _, historical = policy_fixture()
    checkpoint = encode_policy_stage_checkpoint(context, historical)
    by_label = {row.label: row for row in historical}
    requests = __import__("kil.v3b2_proofs", fromlist=["OPERATIONS"]).OPERATIONS["application_apply"].requests(context)
    payload = {"policy_stage_checkpoint": checkpoint,
               "applied_objects": configuration.applied_objects,
               "node": by_label["node"].stdout,
               "cluster_namespace": by_label["cluster_namespace"].stdout,
               "kind_configuration": by_label["kind_configuration"].stdout}
    observations = tuple(RawObservation(request.label,
        () if request.command is None else request.command.argv,
        () if request.command is None else request.command.env,
        0, payload[request.label], b"") for request in requests)
    return context, observations


class ApplicationBoundaryTest(unittest.TestCase):
    def test_application_registry_is_exact_five_and_decision_stays_unknown(self):
        from kil.v3b2_proofs import OPERATIONS, decide
        context, observations = decision_fixture()
        requests = OPERATIONS["application_apply"].requests(context)
        self.assertEqual([row.label for row in requests], ["policy_stage_checkpoint",
                         "applied_objects", "node", "cluster_namespace", "kind_configuration"])
        self.assertEqual(requests[0].source, "policy_stage_checkpoint")
        decision = decide(context, observations)
        self.assertEqual((decision.outcome, decision.category),
                         ("unknown", "generated_ownership_terminal_gate_pending"))
        self.assertEqual(len(json.loads(decision.bindings)["policy_continuity"]), 18)

    def test_missing_or_changed_checkpoint_never_completes_application(self):
        from kil.v3b2_proofs import decide
        context, observations = decision_fixture()
        variants = (observations[1:],
                    (replace(observations[0], stdout=b"{}\n"), *observations[1:]))
        for rows in variants:
            with self.subTest():
                decision = decide(context, tuple(rows))
                self.assertEqual(decision.outcome, "unknown")
                self.assertNotEqual(decision.category, "exact_applied_configuration")

    def test_current_cluster_bracket_must_validate_before_pending_boundary_summary(self):
        from kil.v3b2_proofs import decide
        context, observations = decision_fixture()
        for position in (2, 3, 4):
            changed = list(observations)
            changed[position] = replace(changed[position], stdout=b"{}\n")
            decision = decide(context, tuple(changed))
            with self.subTest(label=observations[position].label):
                self.assertEqual((decision.outcome, decision.category),
                                 ("unknown", "invalid_or_missing_observation"))
                self.assertEqual(decision.bindings, b"{}\n")

    def test_offline_decision_uses_retained_checkpoint_without_filesystem_reader(self):
        from unittest.mock import patch
        from kil.v3b2_proofs import decide
        context, observations = decision_fixture()
        with patch("kil.v3b2_policy_stage_checkpoint.read_policy_stage_checkpoint_bytes",
                   side_effect=AssertionError("offline replay read filesystem")):
            self.assertEqual(decide(context, observations).category,
                             "generated_ownership_terminal_gate_pending")

    def test_repaired_bundle_with_changed_checkpoint_raw_does_not_revalidate(self):
        from kil.v3b2_proofs import RawObservation, decode, decide, observation_bundle
        context, observations = decision_fixture()
        decision = decide(context, observations)
        document = decode(observation_bundle(context, observations, decision))
        document["observations"][0]["stdout_hex"] = b"{}\n".hex()
        replay = tuple(RawObservation(row["label"], tuple(row["argv"]),
            tuple(tuple(pair) for pair in row["env"]), row["returncode"],
            bytes.fromhex(row["stdout_hex"]), bytes.fromhex(row["stderr_hex"]))
            for row in decode(canonical(document))["observations"])
        repaired = decide(context, replay)
        self.assertEqual(repaired.outcome, "unknown")
        self.assertEqual(repaired.category, "invalid_or_missing_observation")

    def test_historical_policy_and_final_configuration_join_by_uid_not_resource_version(self):
        _, _, _, proof = fixture(advance_rv=True)
        self.assertEqual(len(proof.policy_continuity), 18)
        self.assertTrue(all(row.policy_resource_version != row.final_resource_version
                            for row in proof.policy_continuity))
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)

    def test_equal_resource_versions_are_also_legitimate(self):
        _, _, _, proof = fixture(advance_rv=False)
        self.assertTrue(all(row.policy_resource_version == row.final_resource_version
                            for row in proof.policy_continuity))

    def test_uid_drift_and_reconstructed_raw_checkpoint_are_rejected(self):
        context, checkpoint, configuration, proof = fixture()
        document = json.loads(configuration.applied_objects)
        row = next(row for row in document["items"] if row["kind"] == "NetworkPolicy")
        row["metadata"]["uid"] = "replacement-policy-uid"
        changed = replace(configuration, applied_objects=(json.dumps(document, sort_keys=True,
                           separators=(",", ":")) + "\n").encode())
        from kil.v3b2_application_boundary import ApplicationBoundaryError, validate_application_boundary
        with self.assertRaises(ApplicationBoundaryError):
            validate_application_boundary(context=context, checkpoint_bytes=checkpoint,
                                            configuration=changed)
        payload = json.loads(checkpoint); payload["observations"][1]["stdout_hex"] = b"{}".hex()
        with self.assertRaises(ApplicationBoundaryError):
            replace(proof, checkpoint_bytes=canonical(payload))

    def test_same_context_and_full_raw_configuration_are_constructor_bound(self):
        context, checkpoint, configuration, proof = fixture()
        with self.assertRaises(ValueError): replace(proof, context=replace(context, intent_sequence=2))
        with self.assertRaises(ValueError): replace(proof, checkpoint_bytes=b"{}\n")
        with self.assertRaises(ValueError): replace(proof, configuration=replace(
            configuration, applied_objects=b"{}\n"))


if __name__ == "__main__": unittest.main()
