from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import unittest
from unittest.mock import patch

from kil import v3b2_proofs as proofs
from tests import test_v3b2_node_image_integration as integration


class NodeImageSourceTest(unittest.TestCase):
    def setUp(self):
        fixture = integration.NodeImageIntegrationTest(); fixture.setUp()
        self.base = deepcopy(fixture.base)
        self.base["node_image_source_version"] = 1
        payload = proofs.canonical(self.base)
        self.journal = {"run_id": fixture.context.run_id, "owned_identity": self.base["owned_identity"],
                        "expected_inputs_sha256": sha256(payload).hexdigest(),
                        "profile_start_refused_sequence": None, "teardown_from_sequence": None,
                        "events": [{"sequence": 1, "event": "image_load_intent", "details": fixture.intent}]}
        context = proofs.expected_context(payload, self.journal, lambda *_: self.fail())
        observations = fixture.observations(context)
        decision = proofs.decide(context, observations)
        self.bundle = proofs.observation_bundle(context, observations, decision)
        self.journal["events"] += [proofs.terminal_event(context, decision, sha256(self.bundle).hexdigest()),
                                   {"sequence": 3, "event": "calico_apply_intent",
                                    "details": {"manifest_sha256": "6" * 64}}]
        self.payload = payload

    def test_opted_in_replay_retains_lossless_source_and_reconstructs(self):
        current = proofs.expected_context(self.payload, self.journal, lambda *_: self.bundle)
        source = proofs.decode(current.inputs)["prior_node_image_source"]
        self.assertEqual(proofs.canonical(source), self.bundle)
        proof = proofs.reconstruct_prior_node_image_references(current)
        self.assertEqual(proof.inspections[0].stdout,
                         proofs.reconstruct_node_image_references(
                             proofs.ExpectedContext(source["run_id"], source["intent_sequence"], source["family"],
                                                    proofs.canonical(source["intent"]), proofs.canonical(source["expected_inputs"])),
                             tuple(proofs.RawObservation(r["label"], tuple(r["argv"]), tuple(map(tuple, r["env"])),
                                                         r["returncode"], bytes.fromhex(r["stdout_hex"]),
                                                         bytes.fromhex(r["stderr_hex"])) for r in source["observations"])).inspections[0].stdout)

    def test_legacy_context_is_byte_compatible_and_source_injection_is_rejected(self):
        legacy = deepcopy(self.base); legacy.pop("node_image_source_version")
        payload = proofs.canonical(legacy)
        journal = deepcopy(self.journal); journal["expected_inputs_sha256"] = sha256(payload).hexdigest(); journal["owned_identity"] = legacy["owned_identity"]
        initial = {**journal, "events": journal["events"][:1]}
        context = proofs.expected_context(payload, initial, lambda *_: self.fail())
        expected = {**legacy, "expected_inputs_sha256": sha256(payload).hexdigest(), "history": [],
                    "profile_start_refused_sequence": None, "teardown_only": False,
                    "prior_service_bindings": None, "prior_node_image_references": None,
                    "source_images": []}
        self.assertEqual(context.inputs, proofs.canonical(expected))
        for value in (None, True, 2):
            bad = deepcopy(legacy); bad["node_image_source_version"] = value
            raw = proofs.canonical(bad); badjournal = {**initial, "expected_inputs_sha256": sha256(raw).hexdigest()}
            with self.subTest(value=value), self.assertRaises(proofs.ProofError):
                proofs.expected_context(raw, badjournal, lambda *_: self.fail())
        bad = deepcopy(self.base); bad["prior_node_image_source"] = {}
        raw = proofs.canonical(bad); badjournal = {**self.journal, "expected_inputs_sha256": sha256(raw).hexdigest()}
        with self.assertRaises(proofs.ProofError): proofs.expected_context(raw, badjournal, lambda *_: self.bundle)

    def test_source_tampering_is_rejected(self):
        current = proofs.expected_context(self.payload, self.journal, lambda *_: self.bundle)
        inputs = proofs.decode(current.inputs)
        variants = []
        changed = deepcopy(inputs); changed["prior_node_image_source"]["run_id"] = "0" * 64; variants.append(changed)
        changed = deepcopy(inputs); changed["history"][1]["details"]["observed_proof_sha256"] = "0" * 64; variants.append(changed)
        changed = deepcopy(inputs); changed["prior_node_image_source"]["expected_inputs"]["kind_node_image"] = "foreign"; variants.append(changed)
        changed = deepcopy(inputs); changed["history"].pop(0); variants.append(changed)
        changed = deepcopy(inputs); changed["history"].insert(2, deepcopy(changed["history"][0])); variants.append(changed)
        changed = deepcopy(inputs); changed["prior_node_image_source"]["expected_inputs"]["node_image_source_version"] = 2; variants.append(changed)
        changed = deepcopy(inputs); changed["history"][0]["sequence"] = True; variants.append(changed)
        changed = deepcopy(inputs); changed["history"][1]["sequence"] = 2.0; variants.append(changed)
        for changed in variants:
            with self.subTest(), self.assertRaises(proofs.ProofError):
                proofs.reconstruct_prior_node_image_references(replace(current, inputs=proofs.canonical(changed)))

    def test_successful_opted_source_uses_same_two_megabyte_writer_bound(self):
        initial = {**self.journal, "events": self.journal["events"][:1]}
        context = proofs.expected_context(self.payload, initial, lambda *_: self.fail())
        fixture = integration.NodeImageIntegrationTest(); fixture.setUp()
        observations = list(fixture.observations(context))
        observations[1] = replace(observations[1], stderr=b"x" * (proofs.MAX_NODE_IMAGE_SOURCE_BYTES // 2))
        decision = proofs.ProofDecision("complete", "bound_node_image_references_complete", b"{}\n")
        with self.assertRaises(proofs.ProofError):
            proofs.observation_bundle(context, tuple(observations), decision)

    def test_incremental_canonical_bounds_accept_exact_limit_and_reject_next_byte(self):
        value = {"value": "x\"\\\b\u001f\u007f\u0080\U0001f642" + "x" * 32}
        encoded = proofs.canonical(value)
        self.assertEqual(proofs._canonical_bounded(value, len(encoded)), encoded)
        with self.assertRaises(proofs.ProofError):
            proofs._canonical_bounded(value, len(encoded) - 1)
        with patch.object(proofs.json.JSONEncoder, "iterencode", side_effect=AssertionError("encoder called")):
            with self.assertRaises(proofs.ProofError):
                proofs._canonical_bounded({"value": "x" * 1_000_002}, 64)
            with self.assertRaises(proofs.ProofError):
                proofs._canonical_bounded([{}] * 1_000_002, 64)

    def test_actual_complete_bundle_has_identical_writer_and_replay_threshold(self):
        initial = {**self.journal, "events": self.journal["events"][:1]}
        context = proofs.expected_context(self.payload, initial, lambda *_: self.fail())
        fixture = integration.NodeImageIntegrationTest(); fixture.setUp()
        observations = fixture.observations(context)
        decision = proofs.decide(context, observations)
        bundle = proofs.observation_bundle(context, observations, decision)
        for cap, accepted in ((len(bundle), True), (len(bundle) - 1, False)):
            with self.subTest(cap=cap), patch.object(proofs, "MAX_NODE_IMAGE_SOURCE_BYTES", cap):
                if accepted:
                    self.assertEqual(proofs.observation_bundle(context, observations, decision), bundle)
                    journal = deepcopy(initial); digest = sha256(bundle).hexdigest()
                    journal["events"] += [proofs.terminal_event(context, decision, digest),
                                          {"sequence": 3, "event": "calico_apply_intent",
                                           "details": {"manifest_sha256": "6" * 64}}]
                    replayed = proofs.expected_context(self.payload, journal, lambda *_: bundle)
                    self.assertIn("prior_node_image_source", proofs.decode(replayed.inputs))
                else:
                    with self.assertRaises(proofs.ProofError):
                        proofs.observation_bundle(context, observations, decision)

    def test_teardown_only_image_evidence_keeps_general_bundle_budget(self):
        initial = {**self.journal, "teardown_from_sequence": 1, "events": self.journal["events"][:1]}
        context = proofs.expected_context(self.payload, initial, lambda *_: self.fail())
        fixture = integration.NodeImageIntegrationTest(); fixture.setUp()
        observations = list(fixture.observations(context))
        observations[1] = replace(observations[1], returncode=1,
                                  stderr=b"x" * (proofs.MAX_NODE_IMAGE_SOURCE_BYTES + 1))
        decision = proofs.decide(context, tuple(observations))
        self.assertEqual(decision.outcome, "teardown_only")
        bundle = proofs.observation_bundle(context, tuple(observations), decision)
        self.assertGreater(len(bundle), proofs.MAX_NODE_IMAGE_SOURCE_BYTES)
        self.assertEqual(proofs.decode_proof_bundle(bundle)["outcome"], "teardown_only")

    @staticmethod
    def _absence_observations(context):
        rows = []
        for request in proofs.OPERATIONS[context.family].requests(context):
            command = request.command
            rows.append(proofs.RawObservation(request.label,
                () if command is None else command.argv,
                () if command is None else command.env,
                0 if request.label == "cluster_inventory" else 1,
                b"", b"" if request.label == "cluster_inventory" else b"not found"))
        return tuple(rows)

    def test_lossless_source_survives_two_later_completed_replays(self):
        bundles = {(1, sha256(self.bundle).hexdigest()): self.bundle}
        journal = deepcopy(self.journal)
        journal["teardown_from_sequence"] = 3
        journal["events"][-1] = {"sequence": 3, "event": "cluster_delete_intent", "details": {}}
        first = proofs.expected_context(self.payload, journal, lambda sequence, digest: bundles[(sequence, digest)])
        source = proofs.canonical(proofs.decode(first.inputs)["prior_node_image_source"])
        original = proofs.reconstruct_prior_node_image_references(first)

        for sequence, family in ((3, "cluster_delete"), (5, "cluster_absence_proof")):
            context = proofs.expected_context(self.payload, journal,
                                              lambda prior_sequence, digest: bundles[(prior_sequence, digest)])
            observations = self._absence_observations(context)
            decision = proofs.decide(context, observations)
            self.assertEqual(decision.outcome, "complete")
            bundle = proofs.observation_bundle(context, observations, decision)
            digest = sha256(bundle).hexdigest(); bundles[(sequence, digest)] = bundle
            journal["events"].append(proofs.terminal_event(context, decision, digest))
            journal["events"].append({"sequence": sequence + 2,
                "event": ("cluster_absence_proof_intent" if sequence == 3 else "profile_stop_intent"),
                "details": {}})
            later = proofs.expected_context(self.payload, journal,
                                            lambda prior_sequence, prior_digest: bundles[(prior_sequence, prior_digest)])
            self.assertEqual(proofs.canonical(proofs.decode(later.inputs)["prior_node_image_source"]), source)
            self.assertEqual(proofs.reconstruct_prior_node_image_references(later), original)


if __name__ == "__main__": unittest.main()
