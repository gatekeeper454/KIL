from dataclasses import replace
import importlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kil.v3b2_proofs import canonical, decode
from tests.test_v3b2_application_policy_stage import fixture

MODULE = "kil.v3b2_policy_stage_checkpoint"


class PolicyStageCheckpointTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "checkpoint module is missing")
        self.module = importlib.import_module(MODULE)
        _, self.context, self.observations = fixture()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name).resolve(); self.private.chmod(0o700)
        self.path = self.private / "journal.json"
        self.journal = {"run_id": self.context.run_id, "teardown_from_sequence": None,
                        "expected_inputs_sha256": "a" * 64, "events": [{
                            "sequence": self.context.intent_sequence, "event": "application_apply_intent",
                            "details": decode(self.context.intent)}]}

    def publish(self):
        with patch(MODULE + ".load_journal", return_value=self.journal), patch(
                MODULE + ".load_expected_context", return_value=self.context):
            return self.module.publish_policy_stage_checkpoint(self.path, self.context, self.observations)

    def test_canonical_checkpoint_recomputes_raw_evidence_and_reuses_exact_private_bytes(self):
        payload = self.module.encode_policy_stage_checkpoint(self.context, self.observations)
        proof = self.module.decode_policy_stage_checkpoint(payload, self.context)
        self.assertEqual(len(proof.bindings), 18)
        self.assertFalse(proof.runtime_contract_complete)
        self.publish(); self.publish()
        target = self.private / "policy-stage-1.json"
        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.module.read_policy_stage_checkpoint_bytes(self.path, self.context), payload)
        self.assertEqual(self.module.read_policy_stage_checkpoint(self.path, self.context), proof)

    def test_missing_corrupt_symlink_hardlink_and_nonprivate_checkpoint_rejected(self):
        with self.assertRaises((OSError, ValueError)):
            self.module.read_policy_stage_checkpoint(self.path, self.context)
        self.publish()
        target = self.private / "policy-stage-1.json"
        target.chmod(0o644)
        with self.assertRaises(ValueError): self.module.read_policy_stage_checkpoint(self.path, self.context)
        target.chmod(0o600)
        os.link(target, self.private / "alias")
        with self.assertRaises(ValueError): self.module.read_policy_stage_checkpoint(self.path, self.context)
        (self.private / "alias").unlink()
        saved = self.private / "saved"; target.rename(saved); target.symlink_to(saved)
        with self.assertRaises((OSError, ValueError)): self.module.read_policy_stage_checkpoint(self.path, self.context)
        target.unlink(); target.write_bytes(b"corrupt"); target.chmod(0o600)
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual(target.read_bytes(), b"corrupt")

    def test_publication_rejects_teardown_pending_intent_and_context_drift(self):
        for changes in ({"teardown_from_sequence": 2}, {"events": []}, {"run_id": "f" * 64},
                        {"expected_inputs_sha256": None}):
            with patch(MODULE + ".load_journal", return_value={**self.journal, **changes}), patch(
                    MODULE + ".load_expected_context", return_value=self.context):
                with self.assertRaises(ValueError):
                    self.module.publish_policy_stage_checkpoint(self.path, self.context, self.observations)
        with patch(MODULE + ".load_journal", return_value=self.journal), patch(
                MODULE + ".load_expected_context", return_value=replace(self.context, intent_sequence=2)):
            with self.assertRaises(ValueError):
                self.module.publish_policy_stage_checkpoint(self.path, self.context, self.observations)
        self.assertFalse((self.private / "policy-stage-1.json").exists())

    def test_repaired_envelope_wrong_context_and_missing_raw_evidence_fail(self):
        payload = self.module.encode_policy_stage_checkpoint(self.context, self.observations)
        for field, value in (("context_commitment", "f" * 64), ("run_id", "f" * 64),
                             ("intent_sequence", 2), ("observations", [])):
            document = decode(payload); document[field] = value
            with self.assertRaises(ValueError): self.module.decode_policy_stage_checkpoint(canonical(document), self.context)
        document = decode(payload); document["observations"][1]["stdout_hex"] = b"{}".hex()
        with self.assertRaises(ValueError): self.module.decode_policy_stage_checkpoint(canonical(document), self.context)

    def test_reader_rejects_parent_permission_drift_before_open_and_during_read(self):
        self.publish()
        real_location = self.module._private_location
        def changed_location(*args, **kwargs):
            result = real_location(*args, **kwargs)
            self.private.chmod(0o755)
            return result
        try:
            with patch(MODULE + "._private_location", side_effect=changed_location):
                with self.assertRaisesRegex(ValueError, "parent"):
                    self.module.read_policy_stage_checkpoint(self.path, self.context)
        finally:
            self.private.chmod(0o700)
        real_read = os.read
        def changed_read(*args):
            data = real_read(*args)
            self.private.chmod(0o755)
            return data
        try:
            with patch(MODULE + ".os.read", side_effect=changed_read):
                with self.assertRaisesRegex(ValueError, "parent"):
                    self.module.read_policy_stage_checkpoint(self.path, self.context)
        finally:
            self.private.chmod(0o700)

    def test_reader_rejects_parent_name_substitution_during_read(self):
        self.publish()
        real_read = os.read
        saved = self.private.parent / (self.private.name + "-moved")
        changed = False
        def swapped_read(*args):
            nonlocal changed
            data = real_read(*args)
            if not changed:
                self.private.rename(saved)
                self.private.mkdir(mode=0o700)
                changed = True
            return data
        try:
            with patch(MODULE + ".os.read", side_effect=swapped_read):
                with self.assertRaisesRegex(ValueError, "parent"):
                    self.module.read_policy_stage_checkpoint(self.path, self.context)
        finally:
            if changed:
                self.private.rmdir()
                saved.rename(self.private)


if __name__ == "__main__": unittest.main()
