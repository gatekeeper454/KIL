"""Durable replay-safe record for the V4 control-plane manifest source."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from kil.v3b2_control_plane_manifest_source import (
    MAX_SOURCE_RECORD_BYTES,
    ControlPlaneManifestSourceProof,
    validate_control_plane_manifest_source,
)
from kil.v3b2_control_plane_manifest_source_record import (
    ControlPlaneManifestSourceRecordError,
    encode_control_plane_manifest_source_record,
    publish_control_plane_manifest_source_record,
    read_control_plane_manifest_source_record,
)
from kil.v3b2_proofs import ExpectedContext, canonical
from tests.test_v3b2_control_plane_manifest_source import context, identity, observations


class ControlPlaneManifestSourceRecordTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.private = Path(self.temporary.name).resolve() / "private"
        self.private.mkdir(mode=0o700)
        os.chmod(self.private, 0o700)
        self.path = self.private / "control-plane-manifest-source-5.json"
        self.context = context(
            private_path=str(self.private),
            control_plane_manifest_source_version=1,
        )
        self.proof = validate_control_plane_manifest_source(
            context=self.context, owned_identity=identity(), observations=observations())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def encoded_document(self) -> tuple[bytes, dict[str, object]]:
        encoded = encode_control_plane_manifest_source_record(
            proof=self.proof, context=self.context)
        return encoded, json.loads(encoded)

    def write(self, payload: bytes, *, mode: int = 0o600) -> None:
        self.path.write_bytes(payload)
        os.chmod(self.path, mode)

    def test_encoding_is_one_exact_canonical_closed_envelope(self) -> None:
        encoded, document = self.encoded_document()
        self.assertEqual(encoded, canonical(document))
        self.assertEqual(set(document), {"schema", "context", "proof"})
        self.assertEqual(document["schema"],
                         "kil.v4.control-plane-manifest-source.v1")
        self.assertEqual(document["context"], {
            "run_id": self.context.run_id,
            "intent_sequence": self.context.intent_sequence,
            "family": self.context.family,
            "intent": json.loads(self.context.intent),
            "inputs": json.loads(self.context.inputs),
        })
        expected = {
            "run_id": self.proof.run_id,
            "cluster_uid": self.proof.cluster_uid,
            "node_container_id": self.proof.node_container_id,
            "node_config_id": self.proof.node_config_id,
            "raw_observations": [json.loads(row) for row in self.proof.raw_observations],
            "bindings": [asdict(binding) for binding in self.proof.bindings],
            "runtime_complete": False,
            "application_complete": False,
        }
        self.assertEqual(document["proof"], expected)

    def test_publish_is_write_once_idempotent_and_read_reconstructs_exact_proof(self) -> None:
        encoded = encode_control_plane_manifest_source_record(
            proof=self.proof, context=self.context)
        self.assertEqual(publish_control_plane_manifest_source_record(
            path=self.path, proof=self.proof, context=self.context), encoded)
        self.assertEqual(publish_control_plane_manifest_source_record(
            path=self.path, proof=self.proof, context=self.context), encoded)
        self.assertEqual(self.path.read_bytes(), encoded)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(self.path.stat().st_nlink, 1)
        reconstructed = read_control_plane_manifest_source_record(
            path=self.path, context=self.context)
        self.assertEqual(reconstructed, self.proof)
        self.assertIsNot(reconstructed, self.proof)
        self.assertTrue(all(left is not right for left, right in
                            zip(reconstructed.bindings, self.proof.bindings, strict=True)))

    def test_context_must_be_reconstructed_exactly_not_just_commitment_equivalent(self) -> None:
        self.write(encode_control_plane_manifest_source_record(
            proof=self.proof, context=self.context))
        changed = replace(self.context, intent_sequence=self.context.intent_sequence + 1)
        with self.assertRaises(ControlPlaneManifestSourceRecordError):
            read_control_plane_manifest_source_record(path=self.path, context=changed)
        with self.assertRaises(ControlPlaneManifestSourceRecordError):
            encode_control_plane_manifest_source_record(
                proof=self.proof, context=changed)

    def test_checkpoint_path_is_bound_to_versioned_immutable_private_parent(self) -> None:
        unrelated = self.private.with_name("unrelated-private")
        unrelated.mkdir(mode=0o700)
        os.chmod(unrelated, 0o700)
        substituted = unrelated / self.path.name
        substituted.write_bytes(encode_control_plane_manifest_source_record(
            proof=self.proof, context=self.context))
        os.chmod(substituted, 0o600)
        for action in (
            lambda: read_control_plane_manifest_source_record(
                path=substituted, context=self.context),
            lambda: publish_control_plane_manifest_source_record(
                path=substituted, proof=self.proof, context=self.context),
        ):
            with self.subTest(action=action), self.assertRaisesRegex(
                    ControlPlaneManifestSourceRecordError, "private|parent|version"):
                action()

        version_two = context(
            private_path=str(self.private),
            control_plane_manifest_source_version=2,
        )
        version_two_proof = validate_control_plane_manifest_source(
            context=version_two, owned_identity=identity(), observations=observations())
        encoded = encode_control_plane_manifest_source_record(
            proof=version_two_proof, context=version_two)
        self.write(encoded)
        for action in (
            lambda: read_control_plane_manifest_source_record(
                path=self.path, context=version_two),
            lambda: publish_control_plane_manifest_source_record(
                path=self.path, proof=version_two_proof, context=version_two),
        ):
            with self.subTest(action=action), self.assertRaisesRegex(
                    ControlPlaneManifestSourceRecordError, "version"):
                action()

    def test_reader_validates_exact_context_before_path_or_filesystem_access(self) -> None:
        from kil import v3b2_control_plane_manifest_source_record as record

        class ForgedExpectedContext(ExpectedContext):
            pass

        forged = ForgedExpectedContext(
            self.context.run_id,
            self.context.intent_sequence,
            self.context.family,
            self.context.intent,
            self.context.inputs,
        )
        with patch.object(
                record, "_open_parent",
                side_effect=AssertionError("filesystem reached before context validation"),
        ) as open_parent:
            for malformed in (object(), forged):
                with self.subTest(context=type(malformed).__name__):
                    try:
                        read_control_plane_manifest_source_record(
                            path=self.path, context=malformed)
                    except ControlPlaneManifestSourceRecordError:
                        pass
                    except Exception as error:
                        self.fail(f"reader leaked {type(error).__name__}: {error}")
                    else:
                        self.fail("reader accepted a malformed context")
        open_parent.assert_not_called()

    def test_exact_four_mib_budget_is_shared_by_encode_and_read(self) -> None:
        from kil import v3b2_control_plane_manifest_source_record as record
        encoded = encode_control_plane_manifest_source_record(
            proof=self.proof, context=self.context)
        with patch.object(record, "MAX_SOURCE_RECORD_BYTES", len(encoded)):
            self.assertEqual(encode_control_plane_manifest_source_record(
                proof=self.proof, context=self.context), encoded)
            self.write(encoded)
            self.assertEqual(read_control_plane_manifest_source_record(
                path=self.path, context=self.context), self.proof)
        with patch.object(record, "MAX_SOURCE_RECORD_BYTES", len(encoded) - 1):
            with self.assertRaisesRegex(ControlPlaneManifestSourceRecordError,
                                        "four MiB|byte bound|bounded"):
                encode_control_plane_manifest_source_record(
                    proof=self.proof, context=self.context)
            with self.assertRaisesRegex(ControlPlaneManifestSourceRecordError,
                                        "four MiB|byte bound|bounded"):
                read_control_plane_manifest_source_record(
                    path=self.path, context=self.context)
        self.assertLessEqual(len(encoded), MAX_SOURCE_RECORD_BYTES)

    def test_complete_envelope_uses_bounded_canonical_before_materialization(self) -> None:
        from kil import v3b2_control_plane_manifest_source_record as record
        unbounded = record.canonical

        def reject_complete_envelope(value: object) -> bytes:
            if type(value) is dict and set(value) == {"schema", "context", "proof"}:
                raise AssertionError("complete envelope reached unbounded canonical")
            return unbounded(value)

        with patch.object(record, "canonical", side_effect=reject_complete_envelope):
            try:
                encoded = encode_control_plane_manifest_source_record(
                    proof=self.proof, context=self.context)
            except AssertionError as error:
                self.fail(str(error))
        self.assertLessEqual(len(encoded), MAX_SOURCE_RECORD_BYTES)

    def test_existing_altered_bytes_are_never_replaced(self) -> None:
        expected = encode_control_plane_manifest_source_record(
            proof=self.proof, context=self.context)
        altered = expected[:-2] + b" \n"
        self.write(altered)
        before = self.path.stat()
        with self.assertRaises(ControlPlaneManifestSourceRecordError):
            publish_control_plane_manifest_source_record(
                path=self.path, proof=self.proof, context=self.context)
        after = self.path.stat()
        self.assertEqual(self.path.read_bytes(), altered)
        self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))

    def test_symlink_hardlink_fifo_and_non_private_existing_targets_are_rejected(self) -> None:
        encoded = encode_control_plane_manifest_source_record(
            proof=self.proof, context=self.context)
        cases = ("symlink", "hardlink", "fifo", "mode")
        for case in cases:
            with self.subTest(case=case):
                self.path.unlink(missing_ok=True)
                backing = self.private / "backing"
                backing.unlink(missing_ok=True)
                if case == "symlink":
                    backing.write_bytes(encoded)
                    os.chmod(backing, 0o600)
                    self.path.symlink_to(backing)
                elif case == "hardlink":
                    backing.write_bytes(encoded)
                    os.chmod(backing, 0o600)
                    os.link(backing, self.path)
                elif case == "fifo":
                    os.mkfifo(self.path, 0o600)
                else:
                    self.write(encoded, mode=0o640)
                for action in (
                    lambda: read_control_plane_manifest_source_record(
                        path=self.path, context=self.context),
                    lambda: publish_control_plane_manifest_source_record(
                        path=self.path, proof=self.proof, context=self.context),
                ):
                    with self.assertRaises((ControlPlaneManifestSourceRecordError,
                                            OSError)):
                        action()

    def test_parent_must_be_owned_private_and_stable_during_publication(self) -> None:
        os.chmod(self.private, 0o755)
        with self.assertRaises(ControlPlaneManifestSourceRecordError):
            publish_control_plane_manifest_source_record(
                path=self.path, proof=self.proof, context=self.context)
        os.chmod(self.private, 0o700)
        moved = self.private.with_name("private-moved")
        real_fsync = os.fsync
        replaced = False

        def replace_parent(descriptor: int) -> None:
            nonlocal replaced
            mode = os.fstat(descriptor).st_mode
            if not replaced and stat.S_ISREG(mode):
                self.private.rename(moved)
                self.private.mkdir(mode=0o700)
                replaced = True
            real_fsync(descriptor)

        with patch("kil.v3b2_control_plane_manifest_source_record.os.fsync",
                   side_effect=replace_parent):
            with self.assertRaisesRegex(ControlPlaneManifestSourceRecordError,
                                        "parent|identity"):
                publish_control_plane_manifest_source_record(
                    path=self.path, proof=self.proof, context=self.context)
        self.assertTrue(replaced)
        self.assertFalse(self.path.exists())

    def test_parent_descriptor_is_closed_when_open_validation_raises(self) -> None:
        from kil import v3b2_control_plane_manifest_source_record as record

        with (
            patch.object(record.os, "open", return_value=91),
            patch.object(record.os, "fstat", side_effect=OSError("fstat failed")),
            patch.object(record.os, "close") as close,
        ):
            with self.assertRaises(ControlPlaneManifestSourceRecordError):
                read_control_plane_manifest_source_record(
                    path=self.path, context=self.context)
        close.assert_called_once_with(91)

    def test_corruption_unknown_fields_and_forged_nested_proof_fail_closed(self) -> None:
        encoded, document = self.encoded_document()
        mutations = []
        mutations.append(encoded[:-1])
        for location in ("envelope", "context", "proof", "binding", "raw"):
            changed = json.loads(encoded)
            if location == "envelope":
                changed["unknown"] = True
            elif location == "context":
                changed["context"]["unknown"] = True
            elif location == "proof":
                changed["proof"]["unknown"] = True
            elif location == "binding":
                changed["proof"]["bindings"][0]["unknown"] = True
            else:
                changed["proof"]["raw_observations"][0]["unknown"] = True
            mutations.append(canonical(changed))
        forged = json.loads(encoded)
        forged["proof"]["bindings"][0]["sha256"] = "0" * 64
        mutations.append(canonical(forged))
        forged = json.loads(encoded)
        forged["proof"]["runtime_complete"] = True
        mutations.append(canonical(forged))
        for index, payload in enumerate(mutations):
            with self.subTest(index=index):
                self.path.unlink(missing_ok=True)
                self.write(payload)
                with self.assertRaises(ControlPlaneManifestSourceRecordError):
                    read_control_plane_manifest_source_record(
                        path=self.path, context=self.context)

    def test_file_and_parent_are_fsynced_before_publish_returns(self) -> None:
        real_fsync = os.fsync
        kinds: list[str] = []

        def observed(descriptor: int) -> None:
            mode = os.fstat(descriptor).st_mode
            kinds.append("directory" if stat.S_ISDIR(mode) else "file")
            real_fsync(descriptor)

        with patch("kil.v3b2_control_plane_manifest_source_record.os.fsync",
                   side_effect=observed):
            publish_control_plane_manifest_source_record(
                path=self.path, proof=self.proof, context=self.context)
        self.assertIn("file", kinds)
        self.assertIn("directory", kinds)
        self.assertLess(kinds.index("file"), kinds.index("directory"))

    def test_forged_public_record_types_are_rejected(self) -> None:
        with self.assertRaises(ControlPlaneManifestSourceRecordError):
            encode_control_plane_manifest_source_record(
                proof=object(), context=self.context)
        forged = object.__new__(ControlPlaneManifestSourceProof)
        with self.assertRaises(ControlPlaneManifestSourceRecordError):
            encode_control_plane_manifest_source_record(
                proof=forged, context=self.context)


if __name__ == "__main__":
    unittest.main()
