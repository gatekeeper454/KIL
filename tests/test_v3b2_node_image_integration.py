"""Shared image-load registry, node bracketing, and durable replay tests."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
import unittest

from kil import v3b2_proofs as proofs
from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_node_image_references import validate_node_image_references
from tests.test_v3b2_node_image_references import fixture as reference_fixture


KIND_IMAGE = "kindest/node@sha256:" + "9" * 64
NODE_RUNTIME_IMAGE = "sha256:" + "8" * 64
UID = "11111111-1111-4111-8111-111111111111"
CONFIGURATION = b"kind: Cluster\n"


class NodeImageIntegrationTest(unittest.TestCase):
    def setUp(self):
        source = reference_fixture()
        self.identity: OwnedIdentity = source["identity"]
        self.expected = source["expected_images"]
        self.base = {
            "run_id": "7" * 64,
            "owned_identity": asdict(replace(self.identity, cluster_incarnation_uid=UID)),
            "kind_node_image": KIND_IMAGE,
            "kind_config_path": "/tmp/owned/kind.json",
            "kind_config_sha256": sha256(CONFIGURATION).hexdigest(),
            "images": [
                {"reference": image.query_reference,
                 "manifest_digest": image.target_digest,
                 "config_digest": image.config_digest,
                 "target_media_type": image.target_media_type,
                 "allowed_repo_tags": list(image.allowed_repo_tags),
                 "allowed_repo_digests": list(image.allowed_repo_digests)}
                for image in self.expected
            ],
            "calico_objects": [],
            "runtime_contract_complete": False,
        }
        self.intent = {"image": self.base["images"][0]["reference"],
                       "envoy_image": self.base["images"][1]["reference"]}
        self.context = proofs.ExpectedContext("7" * 64, 1, "image_load", proofs.canonical(self.intent),
                                              proofs.canonical(self.base))
        self.source = source

    def node_payload(self, *, node=None, image=None, name=None):
        return proofs.canonical([{
            "Id": node or self.identity.node_container_id,
            "Name": name or "/kil-v3-lab-control-plane",
            "Image": image or NODE_RUNTIME_IMAGE,
            "Config": {"Image": KIND_IMAGE, "Labels": {
                "io.x-k8s.kind.cluster": "kil-v3-lab",
                "io.x-k8s.kind.role": "control-plane",
            }},
            "Created": "unrelated-but-retained-outside-the-bracket-projection",
        }])

    def observations(self, context=None):
        context = self.context if context is None else context
        requests = proofs.OPERATIONS["image_load"].requests(context)
        source_rows = {row.label: row for row in (*self.source["inspections"], self.source["node_images"])}
        payloads = {
            "node_before": self.node_payload(),
            "cri_image_0": source_rows["cri_image_0"].stdout,
            "cri_image_1": source_rows["cri_image_1"].stdout,
            "node_images": source_rows["node_images"].stdout,
            "node": self.node_payload(),
            "cluster_namespace": proofs.canonical({"apiVersion": "v1", "kind": "Namespace",
                "metadata": {"name": "kube-system", "uid": UID}}),
            "kind_configuration": CONFIGURATION,
        }
        return tuple(proofs.RawObservation(request.label,
                     () if request.command is None else request.command.argv,
                     () if request.command is None else request.command.env,
                     0, payloads[request.label], b"") for request in requests)

    def test_registry_exactly_brackets_bound_node_around_cri_and_ctr_reads(self):
        requests = proofs.OPERATIONS["image_load"].requests(self.context)
        self.assertEqual([row.label for row in requests], [
            "node_before", "cri_image_0", "cri_image_1", "node_images",
            "node", "cluster_namespace", "kind_configuration",
        ])
        expected_env = (("DOCKER_CONFIG", "/tmp/owned/docker-config"),
                        ("DOCKER_HOST", self.identity.docker_host))
        for request in requests[:5]:
            self.assertEqual(request.command.env, expected_env)
        self.assertEqual(requests[1].command.argv, self.source["inspections"][0].argv)
        self.assertEqual(requests[2].command.argv, self.source["inspections"][1].argv)
        self.assertEqual(requests[3].command.argv, self.source["node_images"].argv)

    def test_registry_rejects_unbounded_or_non_list_image_expectations_before_iteration(self):
        for images in (self.base["images"][:1], self.base["images"] * 2, "not-a-list"):
            inputs = {**self.base, "images": images}
            context = proofs.ExpectedContext("7" * 64, 1, "image_load", proofs.canonical(self.intent),
                                             proofs.canonical(inputs))
            with self.subTest(images=images), self.assertRaises(proofs.ProofError):
                proofs.OPERATIONS["image_load"].requests(context)

    def test_direct_validator_fails_closed_and_returns_durable_reference_bindings(self):
        observations = self.observations()
        decision = proofs._image_load(self.context, observations)
        self.assertEqual(decision.outcome, "complete")
        bindings = proofs.decode(decision.bindings)
        expected_bindings = [asdict(row) for row in validate_node_image_references(
                             identity=replace(self.identity, cluster_incarnation_uid=UID),
                             docker_config="/tmp/owned/docker-config",
                             expected_images=self.expected,
                             inspections=self.source["inspections"],
                             node_images=self.source["node_images"]).bindings]
        self.assertEqual(bindings["node_image_references"],
                         proofs.decode(proofs.canonical(expected_bindings)))
        self.assertIs(bindings["runtime_contract_complete"], False)

        cases = {
            "missing": observations[:-1],
            "extra": observations + (observations[-1],),
            "reordered": (observations[1], observations[0], *observations[2:]),
            "bad_env": (replace(observations[0], env=(("DOCKER_HOST", "unix:///tmp/foreign.sock"),)),
                        *observations[1:]),
            "before_node": (replace(observations[0], stdout=self.node_payload(node="f" * 64)), *observations[1:]),
            "before_image": (replace(observations[0], stdout=self.node_payload(image="sha256:" + "f" * 64)), *observations[1:]),
            "before_name": (replace(observations[0], stdout=self.node_payload(name="/foreign")), *observations[1:]),
            "after_node": (*observations[:4], replace(observations[4], stdout=self.node_payload(node="f" * 64)), *observations[5:]),
            "uid": (*observations[:5], replace(observations[5], stdout=proofs.canonical({
                "apiVersion": "v1", "kind": "Namespace", "metadata": {
                    "name": "kube-system", "uid": "22222222-2222-4222-8222-222222222222"}})), observations[6]),
            "cri": (*observations[:1], replace(observations[1], stdout=observations[1].stdout.replace(b'"pinned": false', b'"pinned": 0')),
                    *observations[2:]),
            "ctr": (*observations[:3], replace(observations[3], stdout=observations[3].stdout.replace(b" complete ", b" incomplete ", 1)),
                    *observations[4:]),
            "stderr": (replace(observations[0], stderr=b"warning"), *observations[1:]),
        }
        for name, poisoned in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                proofs._image_load(self.context, tuple(poisoned))
            with self.subTest(name=name, boundary="decide"):
                self.assertEqual(proofs.decide(self.context, tuple(poisoned)).outcome, "unknown")

        for intent in ({}, {"image": self.intent["envoy_image"],
                            "envoy_image": self.intent["image"]},
                       {**self.intent, "extra": "foreign"}):
            context = replace(self.context, intent=proofs.canonical(intent))
            with self.subTest(intent=intent), self.assertRaises(proofs.ProofError):
                proofs._image_load(context, observations)
            self.assertEqual(proofs.decide(context, observations).outcome, "unknown")

    def test_bindings_survive_offline_replay_and_cannot_be_injected_or_repaired(self):
        base = proofs.canonical(self.base)
        journal = {"run_id": self.context.run_id, "owned_identity": self.base["owned_identity"],
                   "expected_inputs_sha256": sha256(base).hexdigest(),
                   "profile_start_refused_sequence": None, "teardown_from_sequence": None,
                   "events": [{"sequence": 1, "event": "image_load_intent", "details": self.intent}]}
        context = proofs.expected_context(base, journal, lambda *_: self.fail("initial replay read"))
        observations = self.observations(context)
        decision = proofs.decide(context, observations)
        self.assertEqual(decision.outcome, "complete")
        bundle = proofs.observation_bundle(context, observations, decision)
        terminal = proofs.terminal_event(context, decision, sha256(bundle).hexdigest())
        journal["events"].extend([terminal, {"sequence": 3, "event": "calico_apply_intent",
                                             "details": {"manifest_sha256": "6" * 64}}])
        replayed = proofs.expected_context(base, journal, lambda *_: bundle)
        replayed_inputs = proofs.decode(replayed.inputs)
        self.assertEqual(replayed_inputs["prior_node_image_references"],
                         proofs.decode(decision.bindings)["node_image_references"])
        self.assertIs(replayed_inputs["runtime_contract_complete"], False)

        for key in ("node_image_references", "prior_node_image_references"):
            poisoned = deepcopy(self.base); poisoned[key] = []
            poisoned_base = proofs.canonical(poisoned)
            poisoned_journal = {**journal, "expected_inputs_sha256": sha256(poisoned_base).hexdigest(),
                                "owned_identity": poisoned["owned_identity"]}
            with self.subTest(key=key), self.assertRaises(proofs.ProofError):
                proofs.expected_context(poisoned_base, poisoned_journal, lambda *_: bundle)
        document = proofs.decode(bundle)
        document["bindings"]["node_image_references"][0]["image_ref"] = "sha256:" + "0" * 64
        repaired = proofs.canonical(document)
        repaired_digest = sha256(repaired).hexdigest()
        repaired_journal = deepcopy(journal)
        repaired_journal["events"][1]["details"]["observed_proof_sha256"] = repaired_digest
        with self.assertRaises(proofs.ProofError):
            proofs.expected_context(base, repaired_journal, lambda *_: repaired)

        raw_document = proofs.decode(bundle)
        cri = next(row for row in raw_document["observations"] if row["label"] == "cri_image_0")
        cri_payload = json.loads(bytes.fromhex(cri["stdout_hex"]))
        cri_payload["status"]["id"] = "sha256:" + "0" * 64
        cri["stdout_hex"] = json.dumps(cri_payload, separators=(",", ":")).encode().hex()
        repaired_raw = proofs.canonical(raw_document)
        repaired_raw_digest = sha256(repaired_raw).hexdigest()
        repaired_raw_journal = deepcopy(journal)
        repaired_raw_journal["events"][1]["details"]["observed_proof_sha256"] = repaired_raw_digest
        with self.assertRaises(proofs.ProofError):
            proofs.expected_context(base, repaired_raw_journal, lambda *_: repaired_raw)


if __name__ == "__main__":
    unittest.main()
