from pathlib import Path
import unittest

from kil.v3b2_journal import Command, JournalError, _canonical_bytes
from kil.v3b2_proofs import (
    ExpectedContext,
    OPERATIONS,
    ProofDecision,
    calico_objects,
    canonical,
    decode_proof_bundle,
    observation_bundle,
)


ROOT = Path(__file__).resolve().parents[1]


class AppliedRequestUnicodeTest(unittest.TestCase):
    def context_and_document(self):
        source = ROOT / "deploy/kind/calico-v3.32.0.yaml"
        items = calico_objects(
            source.read_bytes(), source.with_suffix(".objects.json").read_bytes(),
        )
        document = {"apiVersion": "v1", "kind": "List", "items": items}
        self.assertIn("–", str(document))
        return ExpectedContext(
            "a" * 64, 1, "calico_apply", b"{}\n",
            canonical({
                "owned_identity": {
                    "kubeconfig": "/tmp/kil-v3-lab/kubeconfig",
                    "docker_host": "unix:///tmp/kil-v3-lab/docker.sock",
                },
                "kind_config_path": "/tmp/kil-v3-lab/kind-config.yaml",
                "applied_objects": items,
            }),
        ), document

    def test_calico_request_uses_the_journal_canonical_utf8_manifest(self):
        context, document = self.context_and_document()

        request = OPERATIONS["calico_apply"].requests(context)[0].command

        self.assertEqual(request.stdin, _canonical_bytes(document))
        self.assertIn("–".encode(), request.stdin)
        self.assertNotIn(b"\\u2013", request.stdin)

    def test_proof_replay_preserves_ascii_encoding_and_rebuilds_identical_request(self):
        context, document = self.context_and_document()
        original = OPERATIONS["calico_apply"].requests(context)[0].command
        self.assertIn(b"\\u2013", context.inputs)
        bundle = observation_bundle(
            context, (), ProofDecision("unknown", "fixture_replay"),
        )
        decoded = decode_proof_bundle(bundle)
        self.assertIn(b"\\u2013", bundle)
        replayed = ExpectedContext(
            decoded["run_id"], decoded["intent_sequence"], decoded["family"],
            canonical(decoded["intent"]), canonical(decoded["expected_inputs"]),
        )
        rebuilt = OPERATIONS["calico_apply"].requests(replayed)[0].command
        self.assertEqual(replayed, context)
        self.assertEqual(rebuilt, original)
        old_ascii_stdin = canonical(document)
        self.assertNotEqual(old_ascii_stdin, original.stdin)
        with self.assertRaisesRegex(JournalError, "canonical List"):
            Command(original.argv, original.timeout_s, stdin=old_ascii_stdin,
                    env=original.env, mutating=original.mutating)


if __name__ == "__main__":
    unittest.main()
