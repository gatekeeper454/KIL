"""Policy-before-workload observation proof; no cluster or CNI runtime access."""
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import unittest

from kil.v3b2_contracts import V3B2Profile, TRACK_NAMESPACES
from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_manifests import WorkloadIdentity, render_kind_config, render_objects
from kil.v3b2_proofs import ExpectedContext, RawObservation, canonical
from kil.v3b2_application_policy_stage import (
    ApplicationPolicyStageError, application_policy_observation_specs,
    policy_request_bytes, validate_application_policy_stage,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE = V3B2Profile.load(ROOT / "deploy/kind/v3b2-profile.json")
WORKLOAD = WorkloadIdentity("v3b2-" + "1" * 64, "sha256:" + "2" * 64,
                            "docker.io/envoyproxy/envoy@sha256:" + "3" * 64)
IDENTITY = OwnedIdentity("kil-v3-lab", "unix:///tmp/owned/kil-v3-lab/docker.sock",
                         "kil-v3-lab", "/tmp/owned/kubeconfig",
                         "11111111-1111-4111-8111-111111111111", "a" * 64)
KIND_IMAGE = PROFILE.kind_node_image
KIND_BYTES = render_kind_config(PROFILE)


def fixture():
    rendered = render_objects(PROFILE, WORKLOAD)
    objects = json.loads(rendered)["items"]
    desired = [row for row in objects if row["kind"] in {"Namespace", "NetworkPolicy"}]
    observed = deepcopy(desired)
    for index, row in enumerate(observed, 1):
        row["metadata"].update(uid=f"policy-{index}", resourceVersion=str(index),
                               creationTimestamp="2026-09-08T00:00:00Z")
    inputs = {"run_id": "1" * 64,
              "profile": json.loads((ROOT / "deploy/kind/v3b2-profile.json").read_bytes()),
              "workload": asdict(WORKLOAD),
              "owned_identity": asdict(IDENTITY), "application_objects": objects,
              "kind_node_image": KIND_IMAGE, "kind_config_path": "/tmp/owned/kind-config.yaml",
              "kind_config_sha256": sha256(KIND_BYTES).hexdigest(),
              "runtime_contract_complete": False}
    intent = {"manifest_sha256": sha256(rendered).hexdigest()}
    context = ExpectedContext("1" * 64, 1, "application_apply", canonical(intent), canonical(inputs))
    specs = application_policy_observation_specs(IDENTITY)
    node = canonical([{"Id": IDENTITY.node_container_id, "Name": "/kil-v3-lab-control-plane",
        "Image": "sha256:" + "6" * 64, "Config": {"Image": KIND_IMAGE, "Labels": {
            "io.x-k8s.kind.cluster": "kil-v3-lab", "io.x-k8s.kind.role": "control-plane"}}}])
    payloads = {"node_before": node, "policy_objects": canonical({"apiVersion": "v1", "kind": "List",
                "metadata": {"resourceVersion": ""}, "items": observed}),
                "node": node, "cluster_namespace": canonical({"apiVersion": "v1", "kind": "Namespace",
                    "metadata": {"name": "kube-system", "uid": IDENTITY.cluster_incarnation_uid}}),
                "kind_configuration": KIND_BYTES}
    for _, namespace in TRACK_NAMESPACES:
        payloads[namespace + ":workload_absence"] = canonical(
            {"apiVersion": "v1", "kind": "List", "metadata": {"resourceVersion": ""}, "items": []})
    observations = tuple(RawObservation(label, argv, env, 0, payloads[label], b"")
                         for label, argv, env in specs)
    return rendered, context, observations


class ApplicationPolicyStageTest(unittest.TestCase):
    def validate(self, context=None, observations=None, commitment=None):
        rendered, default_context, default_observations = fixture()
        context = default_context if context is None else context
        return validate_application_policy_stage(
            context=context, expected_context_commitment=context.commitment if commitment is None else commitment,
            profile=PROFILE, workload=WORKLOAD, rendered_objects=rendered, owned_identity=IDENTITY,
            observations=default_observations if observations is None else observations)

    def test_exact_eight_observations_prove_only_policy_before_workload(self):
        rendered, context, observations = fixture()
        self.assertEqual([row.label for row in observations], ["node_before", "policy_objects",
            *[namespace + ":workload_absence" for _, namespace in TRACK_NAMESPACES],
            "node", "cluster_namespace", "kind_configuration"])
        proof = self.validate(context, observations)
        self.assertEqual(len(proof.bindings), 18)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertEqual(proof.expected_context_commitment, context.commitment)
        self.assertEqual(proof.policy_request, policy_request_bytes(PROFILE, WORKLOAD))

    def test_intent_context_and_dependencies_are_independently_bound(self):
        rendered, context, observations = fixture()
        for changed_context, commitment in (
            (replace(context, intent=canonical({})), context.commitment),
            (context, "0" * 64),
            (replace(context, inputs=canonical({**json.loads(context.inputs), "workload": {}})), context.commitment),
            (replace(context, inputs=canonical({**json.loads(context.inputs),
                                                "runtime_contract_complete": True})), context.commitment),
        ):
            with self.subTest(), self.assertRaises(ApplicationPolicyStageError):
                self.validate(changed_context, observations, commitment)
        with self.assertRaises(ApplicationPolicyStageError):
            validate_application_policy_stage(context=context, expected_context_commitment=context.commitment,
                profile=PROFILE, workload=WORKLOAD, rendered_objects=rendered + b" ",
                owned_identity=IDENTITY, observations=observations)
        pseudo = json.loads(context.inputs); pseudo["profile"] = asdict(PROFILE)
        pseudo_context = replace(context, inputs=canonical(pseudo))
        with self.assertRaises(ApplicationPolicyStageError):
            self.validate(pseudo_context, observations, pseudo_context.commitment)

    def test_registry_transport_cluster_bracket_and_absence_fail_closed(self):
        _, context, observations = fixture()
        cases = [observations[:-1], observations + (observations[-1],),
                 (observations[1], observations[0], *observations[2:]),
                 (replace(observations[0], env=()), *observations[1:]),
                 (replace(observations[0], stderr=b"warning"), *observations[1:])]
        foreign = json.loads(observations[0].stdout); foreign[0]["Name"] = "/foreign"
        cases.append((replace(observations[0], stdout=canonical(foreign)), *observations[1:]))
        for index in range(3):
            position = 2 + index
            cases.append((*observations[:position], replace(observations[position], stdout=canonical(
                {"apiVersion": "v1", "kind": "List", "items": [{"kind": "Pod"}]})), *observations[position + 1:]))
        for rows in cases:
            with self.subTest(), self.assertRaises(ApplicationPolicyStageError): self.validate(context, tuple(rows))

    def test_policy_configuration_identity_and_uid_collisions_fail_closed(self):
        _, context, observations = fixture()
        document = json.loads(observations[1].stdout)
        mutations = []
        changed = deepcopy(document); changed["items"].pop(); mutations.append(changed)
        changed = deepcopy(document); changed["items"][0]["metadata"]["labels"] = {"foreign": "yes"}; mutations.append(changed)
        changed = deepcopy(document); changed["items"][0]["metadata"]["uid"] = changed["items"][1]["metadata"]["uid"]; mutations.append(changed)
        changed = deepcopy(document); changed["items"][0]["metadata"]["uid"] = IDENTITY.cluster_incarnation_uid; mutations.append(changed)
        changed = deepcopy(document); changed["metadata"] = {"continue": "evil"}; mutations.append(changed)
        changed = deepcopy(document); changed["metadata"] = {"resourceVersion": "1"}; mutations.append(changed)
        changed = deepcopy(document); changed["metadata"] = None; mutations.append(changed)
        for document in mutations:
            rows = (*observations[:1], replace(observations[1], stdout=canonical(document)), *observations[2:])
            with self.subTest(), self.assertRaises(ApplicationPolicyStageError): self.validate(context, rows)

    def test_list_envelopes_allow_only_three_source_backed_metadata_forms(self):
        _, context, observations = fixture()
        for metadata in (None, {}, {"resourceVersion": ""}):
            changed = list(observations)
            for position in (1, 2, 3, 4):
                document = json.loads(changed[position].stdout)
                if metadata is None: document.pop("metadata", None)
                else: document["metadata"] = metadata
                changed[position] = replace(changed[position], stdout=canonical(document))
            with self.subTest(metadata=metadata): self.validate(context, tuple(changed))
        for metadata in ({"resourceVersion": "1"}, {"resourceVersion": "", "continue": ""}, None):
            changed = list(observations)
            document = json.loads(changed[2].stdout); document["metadata"] = metadata
            changed[2] = replace(changed[2], stdout=canonical(document))
            with self.subTest(rejected=metadata), self.assertRaises(ApplicationPolicyStageError):
                self.validate(context, tuple(changed))

    def test_profile_binds_kind_image_configuration_bytes_hash_and_private_path(self):
        _, context, observations = fixture()
        inputs = json.loads(context.inputs)
        inputs.update(kind_node_image="kindest/node@sha256:" + "9" * 64,
                      kind_config_sha256=sha256(b"kind: Foreign\n").hexdigest())
        changed_context = replace(context, inputs=canonical(inputs))
        before = json.loads(observations[0].stdout)
        before[0]["Config"]["Image"] = inputs["kind_node_image"]
        changed = list(observations)
        changed[0] = replace(changed[0], stdout=canonical(before))
        changed[5] = replace(changed[5], stdout=canonical(before))
        changed[7] = replace(changed[7], stdout=b"kind: Foreign\n")
        with self.assertRaises(ApplicationPolicyStageError):
            self.validate(changed_context, tuple(changed), changed_context.commitment)
        inputs = json.loads(context.inputs); inputs["kind_config_path"] = "/tmp/foreign/kind-config.yaml"
        changed_context = replace(context, inputs=canonical(inputs))
        with self.assertRaises(ApplicationPolicyStageError):
            self.validate(changed_context, observations, changed_context.commitment)

    def test_command_metadata_is_bounded_before_serialization(self):
        _, context, observations = fixture()
        changed = (replace(observations[0], argv=("x" * (2 * 1024 * 1024),)), *observations[1:])
        with self.assertRaises(ApplicationPolicyStageError): self.validate(context, changed)
        class StringSubclass(str): pass
        changed = (replace(observations[0], argv=(StringSubclass(observations[0].argv[0]),
                                                  *observations[0].argv[1:])), *observations[1:])
        with self.assertRaises(ApplicationPolicyStageError): self.validate(context, changed)
        changed_env = ((StringSubclass("DOCKER_CONFIG"), observations[0].env[0][1]),
                       observations[0].env[1])
        changed = (replace(observations[0], env=changed_env), *observations[1:])
        with self.assertRaises(ApplicationPolicyStageError): self.validate(context, changed)

    def test_constructor_revalidates_canonical_raw_evidence(self):
        proof = self.validate()
        self.assertEqual(replace(proof), proof)
        for changes in ({"runtime_contract_complete": True}, {"bindings": ()},
                        {"raw_observations": proof.raw_observations + b" "},
                        {"policy_request": bytearray(proof.policy_request)},
                        {"expected_context_commitment": "0" * 64}):
            with self.subTest(changes=changes), self.assertRaises(ApplicationPolicyStageError):
                replace(proof, **changes)


if __name__ == "__main__": unittest.main()
