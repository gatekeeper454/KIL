"""Real observation-bound controller tests, independent of happy-path projections."""
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from kil.v3b2_controller import CommandResult, ControllerError, V3B2Controller
from kil.v3b2_journal import append_event, load_journal, latch_teardown, colima_start_command, kind_create_command
from tests import test_v3b2_controller as controller_fixtures


class ObservedLifecycleTest(unittest.TestCase):
    setUp = controller_fixtures.V3B2ControllerTest.setUp
    tearDown = controller_fixtures.V3B2ControllerTest.tearDown

    def test_process_observation_retains_invalid_utf8_bytes_exactly(self):
        from kil.v3b2_controller import SubprocessCommandRunner
        from kil.v3b2_journal import Command
        import subprocess
        raw = b'[{"name":"bad\xff"}]\n'
        with patch("kil.v3b2_controller.subprocess.run", return_value=subprocess.CompletedProcess([], 0, raw, b"\xfe")):
            result = SubprocessCommandRunner().run(Command(("colima", "list", "--json"), 60))
        self.assertTrue(hasattr(result, "stdout_bytes"), "process byte boundary is lossy")
        self.assertEqual(result.stdout_bytes, raw)
        self.assertEqual(result.stderr_bytes, b"\xfe")

    def test_large_committed_proof_replays_with_the_same_bundle_budget(self):
        from kil.v3b2_proofs import MAX_OBSERVATION_BYTES
        controller = self._prepared()
        append_event(controller.journal_path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
        raw = json.dumps([self._owned_profile()]).encode() + b" " * (17 * 1024 * 1024)
        result = CommandResult(0, raw.decode(), "", raw, b"")
        with patch.object(self.runner, "run", return_value=result):
            try:
                decision = controller._observe_terminal()
            except ValueError as error:
                self.fail("accepted proof became unreplayable after terminal commit: " + str(error))
        self.assertEqual(decision.outcome, "complete")
        proof = next(self.paths.private.glob("proof-1-*.json"))
        self.assertGreater(proof.stat().st_size, MAX_OBSERVATION_BYTES)
        self.assertEqual(V3B2Controller(self.paths, self.runner).events[-1][0], "profile_start_complete")

    def test_hex_expansion_over_bundle_budget_cannot_commit_a_terminal(self):
        from kil.v3b2_proofs import MAX_OBSERVATION_BYTES, ProofError
        controller = self._prepared()
        append_event(controller.journal_path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
        row = json.dumps([self._owned_profile()]).encode()
        raw = row + b" " * (MAX_OBSERVATION_BYTES - len(row))
        with patch.object(self.runner, "run", return_value=CommandResult(0, raw.decode(), "", raw, b"")):
            with self.assertRaisesRegex(ProofError, "bundle.*bound"):
                controller._observe_terminal()
        self.assertEqual(load_journal(controller.journal_path)["phase"], "profile_start_intent")
        self.assertEqual(list(self.paths.private.glob("proof-1-*.json")), [])

    def test_interrupted_proof_write_never_publishes_partial_final_bytes(self):
        from kil import v3b2_journal as journal_module
        import os
        controller = self._prepared()
        self.runner.profiles = [self._owned_profile()]
        append_event(controller.journal_path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
        real_fdopen = os.fdopen
        class InterruptedStream:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                self.stream.__enter__()
                return self
            def __exit__(self, *args):
                return self.stream.__exit__(*args)
            def write(self, payload):
                if b'"schema_version":"kil.v3b2-observed-proof.v1"' in payload:
                    self.stream.write(payload[:100])
                    self.stream.flush()
                    raise RuntimeError("interrupted after 100 proof bytes")
                return self.stream.write(payload)
            def __getattr__(self, name):
                return getattr(self.stream, name)
        with patch.object(journal_module.os, "fdopen", side_effect=lambda *args, **kwargs: InterruptedStream(real_fdopen(*args, **kwargs))):
            with self.assertRaisesRegex(RuntimeError, "100 proof bytes"):
                controller._observe_terminal()
        self.assertEqual(load_journal(controller.journal_path)["phase"], "profile_start_intent")
        self.assertEqual(list(self.paths.private.glob("proof-1-*.json")), [], "a partial final proof poisoned retry")
        self.assertEqual(V3B2Controller(self.paths, self.runner).recover()["proof_outcome"], "complete")
        proof = next(self.paths.private.glob("proof-1-*.json"))
        self.assertEqual(proof.stat().st_nlink, 1)

    def test_proof_publication_never_overwrites_a_raced_regular_file(self):
        from kil import v3b2_journal as journal_module
        from kil.v3b2_proofs import decide, observation_bundle
        from kil.v3b2_journal import load_expected_context, JournalError
        import os
        controller = self._prepared()
        self.runner.profiles = [self._owned_profile()]
        append_event(controller.journal_path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
        context = load_expected_context(controller.journal_path)
        observations = controller._collect_observations(context)
        payload = observation_bundle(context, observations, decide(context, observations))
        proof = self.paths.private / ("proof-1-" + sha256(payload).hexdigest() + ".json")
        real_fdopen = os.fdopen
        raced = False
        class RacingStream:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                self.stream.__enter__()
                return self
            def __exit__(self, *args):
                return self.stream.__exit__(*args)
            def write(self, data):
                nonlocal raced
                if not raced and b'"schema_version":"kil.v3b2-observed-proof.v1"' in data:
                    raced = True
                    proof.write_bytes(b"raced foreign proof")
                    proof.chmod(0o600)
                return self.stream.write(data)
            def __getattr__(self, name):
                return getattr(self.stream, name)
        with patch.object(journal_module.os, "fdopen", side_effect=lambda *args, **kwargs: RacingStream(real_fdopen(*args, **kwargs))):
            with self.assertRaises((JournalError, OSError)):
                controller._observe_terminal()
        self.assertTrue(raced)
        self.assertEqual(proof.read_bytes(), b"raced foreign proof")
        self.assertEqual(load_journal(controller.journal_path)["phase"], "profile_start_intent")

    def test_proof_publication_rejects_existing_symlink_without_touching_target(self):
        from kil.v3b2_proofs import decide, observation_bundle
        from kil.v3b2_journal import load_expected_context, JournalError
        controller = self._prepared()
        self.runner.profiles = [self._owned_profile()]
        append_event(controller.journal_path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
        context = load_expected_context(controller.journal_path)
        observations = controller._collect_observations(context)
        payload = observation_bundle(context, observations, decide(context, observations))
        proof = self.paths.private / ("proof-1-" + sha256(payload).hexdigest() + ".json")
        target = self.paths.repository / "unrelated-evidence.json"
        target.write_bytes(b"unrelated evidence remains intact")
        proof.symlink_to(target)
        with self.assertRaises((JournalError, OSError)):
            controller._observe_terminal()
        self.assertTrue(proof.is_symlink())
        self.assertEqual(target.read_bytes(), b"unrelated evidence remains intact")
        self.assertEqual(load_journal(controller.journal_path)["phase"], "profile_start_intent")

    def test_timeout_runner_preserves_partial_bytes_with_reserved_unsuccessful_status(self):
        from kil.v3b2_controller import SubprocessCommandRunner
        from kil.v3b2_journal import Command
        import subprocess
        command = Command(("colima", "list", "--json"), 60)
        for stdout, stderr in ((b"partial raw stdout\xff", b"partial raw stderr\xfe"), (None, None)):
            with self.subTest(stdout=stdout):
                timeout = subprocess.TimeoutExpired(command.argv, 60, output=stdout, stderr=stderr)
                with patch("kil.v3b2_controller.subprocess.run", side_effect=timeout):
                    try:
                        result = SubprocessCommandRunner().run(command)
                    except ControllerError:
                        self.fail("TimeoutExpired partial buffers were discarded at the runner boundary")
                self.assertEqual(result.returncode, -1000)
                self.assertEqual(result.stdout_bytes, stdout or b"")
                self.assertEqual(result.stderr_bytes, stderr or b"")

    def test_oversized_timeout_capture_has_distinct_truncated_status_and_bounded_prefixes(self):
        from kil.v3b2_controller import SubprocessCommandRunner
        from kil.v3b2_journal import Command
        from kil.v3b2_proofs import MAX_OBSERVATION_BYTES
        import subprocess
        command = Command(("colima", "list", "--json"), 60)
        stdout, stderr = b"x" * (MAX_OBSERVATION_BYTES + 1), b"partial error\xfe"
        timeout = subprocess.TimeoutExpired(command.argv, 60, output=stdout, stderr=stderr)
        with patch("kil.v3b2_controller.subprocess.run", side_effect=timeout):
            try:
                result = SubprocessCommandRunner().run(command)
            except ControllerError:
                self.fail("Oversized timeout capture lost its explicit truncated transport status")
        self.assertEqual(result.returncode, -1001)
        self.assertLessEqual(len(result.stdout_bytes) + len(result.stderr_bytes), MAX_OBSERVATION_BYTES // 4)
        self.assertTrue(stdout.startswith(result.stdout_bytes))
        self.assertNotEqual(result.stdout_bytes, stdout)
        self.assertEqual(result.stderr_bytes, stderr)

    def test_timed_out_valid_profile_json_is_retained_but_cannot_complete(self):
        from kil.v3b2_controller import SubprocessCommandRunner
        import subprocess
        controller = self._prepared()
        append_event(controller.journal_path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
        raw = json.dumps([self._owned_profile()]).encode() + b"\n"
        controller.runner = SubprocessCommandRunner()
        with patch("kil.v3b2_controller.subprocess.run", side_effect=subprocess.TimeoutExpired(
                ("colima", "list", "--json"), 60, output=raw, stderr=b"")):
            decision = controller._observe_terminal()
        self.assertEqual(decision.outcome, "unknown")
        self.assertEqual(load_journal(controller.journal_path)["phase"], "profile_start_intent")
        proof = json.loads(next(self.paths.private.glob("proof-1-*.json")).read_bytes())
        observation = next(row for row in proof['observations'] if row['label'] == 'profile_inventory')
        self.assertEqual(bytes.fromhex(observation["stdout_hex"]), raw)
        self.assertEqual(observation["returncode"], -1000)

    def test_image_load_timeout_proof_retains_partial_bytes_before_owned_teardown(self):
        from dataclasses import asdict, replace
        from kil.v3b2_controller import SubprocessCommandRunner
        from kil.v3b2_journal import Command, JournalInputs, create_journal, append_observed_terminal
        from kil.v3b2_manifests import render_kind_config
        from kil.v3b2_proofs import ExpectedContext, canonical, node_images_argv
        import subprocess
        controller = self.controller
        controller.paths.private.mkdir(mode=0o700)
        config = render_kind_config(controller.profile)
        controller.kind_config.write_bytes(config)
        identity = replace(controller._identity, node_container_id="a" * 64,
                           cluster_incarnation_uid="11111111-1111-4111-8111-111111111111")
        # Seed only the preceding lifecycle state; the transport, registry,
        # observation validator and durable terminal writer under test are real.
        create_journal(controller.journal_path, JournalInputs("kil.v3b2-journal.v1", controller.run_digest,
            "c" * 64, "d" * 40, "e" * 64, "prepared", "desktop-linux", (), (), identity))
        cluster = {"kind_cluster": "kil-v3-lab", "kubeconfig": str(controller.kubeconfig)}
        images = {"image": "kil.local/kil-v3b2:sha256-" + "d" * 64,
                  "envoy_image": "docker.io/envoyproxy/envoy@sha256:" + "e" * 64}
        for family, intent, complete in (
            ("profile_start", {"colima_profile": "kil-v3-lab"}, {"colima_profile": "kil-v3-lab"}),
            ("cluster_create", cluster, {**cluster, "node_container_id": identity.node_container_id,
                "cluster_incarnation_uid": identity.cluster_incarnation_uid, "docker_host": identity.docker_host}),
            ("image_import", {**images, "archive_sha256": "f" * 64}, {**images, "archive_sha256": "f" * 64}),
        ):
            append_event(controller.journal_path, family + "_intent", intent)
            append_event(controller.journal_path, family + "_complete", complete)
        append_event(controller.journal_path, "image_load_intent", images)
        latch_teardown(controller.journal_path)
        expected_images = [
            {"reference": images["image"], "manifest_digest": "sha256:" + "d" * 64,
             "config_digest": "sha256:" + "b" * 64,
             "target_media_type": "application/vnd.oci.image.manifest.v1+json",
             "allowed_repo_tags": [images["image"]], "allowed_repo_digests": []},
            {"reference": images["envoy_image"], "manifest_digest": "sha256:" + "e" * 64,
             "config_digest": "sha256:" + "c" * 64,
             "target_media_type": "application/vnd.oci.image.index.v1+json",
             "allowed_repo_tags": [], "allowed_repo_digests": [images["envoy_image"]]},
        ]
        context = ExpectedContext(controller.run_digest, 7, "image_load", canonical(images), canonical({
            "owned_identity": asdict(identity), "teardown_only": True,
            "kind_config_path": str(controller.kind_config), "kind_config_sha256": sha256(config).hexdigest(),
            "kind_node_image": controller.profile.kind_node_image, "images": expected_images,
        }))
        stdout, stderr = b"partial raw stdout\xff", b"partial raw stderr\xfe"
        self.runner.cluster_exists = True
        def process(argv, **kwargs):
            if argv == node_images_argv(identity.node_container_id):
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=stdout, stderr=stderr)
            env = tuple((key, kwargs["env"][key]) for key in ("DOCKER_CONFIG", "DOCKER_HOST") if key in kwargs["env"])
            result = self.runner.run(Command(argv, 60, env=env))
            return subprocess.CompletedProcess(argv, result.returncode, result.stdout_bytes, result.stderr_bytes)
        controller.runner = SubprocessCommandRunner()
        with patch("kil.v3b2_controller.subprocess.run", side_effect=process):
            observations = controller._collect_observations(context)
        decision = append_observed_terminal(controller.journal_path, context, observations)
        self.assertEqual(decision.outcome, "teardown_only")
        journal = load_journal(controller.journal_path)
        self.assertEqual(journal["phase"], "image_load_abandoned_for_teardown")
        commitment = journal["events"][-1]["details"]["observed_proof_sha256"]
        proof = json.loads((self.paths.private / ("proof-7-" + commitment + ".json")).read_bytes())
        observed = next(row for row in proof["observations"] if row["label"] == "node_images")
        self.assertEqual(bytes.fromhex(observed["stdout_hex"]), stdout)
        self.assertEqual(bytes.fromhex(observed["stderr_hex"]), stderr)
        self.assertEqual(observed["returncode"], -1000)

    def _prepared(self):
        self.controller.preflight()
        return self.controller

    def _owned_profile(self):
        from tests.test_v3b2_profile_state import create_profile
        if not self.controller.profile_paths.profile.exists():
            create_profile(self.controller.profile_paths)
        return {"name": "kil-v3-lab", "status": "Running", "arch": "aarch64", "cpus": 4,
                "memory": 8589934592, "disk": 64424509440, "runtime": "docker"}

    def test_expected_inputs_are_committed_before_any_mutation_and_never_rebased(self):
        controller = self._prepared()
        journal = load_journal(controller.journal_path)
        path = controller.paths.private / "expected-inputs.json"
        self.assertTrue(path.exists(), "immutable reviewed expectations are not persisted")
        payload = path.read_bytes()
        self.assertEqual(journal["expected_inputs_sha256"], sha256(payload).hexdigest())
        expected = json.loads(payload)
        self.assertEqual(expected["profile_configuration"], {key: value for key, value in self._owned_profile().items() if key != "status"})
        self.assertFalse(any(command.mutating for command in self.runner.commands))
        path.write_bytes(payload.replace(b'"cpus":4', b'"cpus":9'))
        with self.assertRaisesRegex(ControllerError, "expected_inputs"):
            V3B2Controller(self.paths, self.runner)

    def test_rc_zero_is_not_a_terminal_postcondition(self):
        controller = self._prepared()
        self.runner.profiles = []
        with self.assertRaises(ControllerError):
            controller._journal_pair("profile_start", {"colima_profile": "kil-v3-lab"}, lambda: CommandResult(0, "", ""))
        journal = load_journal(controller.journal_path)
        self.assertNotIn("profile_start_complete", [row["event"] for row in journal["events"]])
        self.assertEqual(journal["events"][-1]["event"], "profile_start_failed")
        self.assertTrue(list(self.paths.private.glob("proof-1-*.json")))

    def test_normal_and_recovery_use_identical_registry_observations(self):
        controller = self._prepared()
        self.runner.profiles = [self._owned_profile()]
        append_event(controller.journal_path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
        before = len(self.runner.commands)
        from kil import v3b2_journal as journal_module
        with patch.object(journal_module, "_replace_journal", side_effect=RuntimeError("crash after proof")):
            with self.assertRaises(RuntimeError):
                controller._observe_terminal()
        first_commands = self.runner.commands[before:]
        self.assertEqual(load_journal(controller.journal_path)["phase"], "profile_start_intent")
        proof_paths = list(self.paths.private.glob("proof-1-*.json"))
        self.assertEqual(len(proof_paths), 1)
        published_identity = (proof_paths[0].stat().st_dev, proof_paths[0].stat().st_ino)
        before = len(self.runner.commands)
        resumed = V3B2Controller(self.paths, self.runner)
        resumed.recover()
        self.assertEqual(self.runner.commands[before:], first_commands)
        terminal = load_journal(controller.journal_path)["events"][-1]
        self.assertEqual(terminal["details"]["observed_proof_sha256"], proof_paths[0].stem.split("-")[-1])
        self.assertEqual((proof_paths[0].stat().st_dev, proof_paths[0].stat().st_ino), published_identity)
        self.assertEqual(proof_paths[0].stat().st_nlink, 1)
        self.assertFalse(any(command.mutating for command in first_commands))

    def test_nonzero_inventory_transport_remains_pending_without_cleanup_guess(self):
        controller = self._prepared()
        append_event(controller.journal_path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
        with patch.object(self.runner, "run", return_value=CommandResult(1, "", "permission denied")):
            result = controller.recover()
        self.assertEqual(result["proof_outcome"], "unknown")
        self.assertEqual(load_journal(controller.journal_path)["phase"], "profile_start_intent")
        self.assertTrue(list(self.paths.private.glob("proof-1-*.json")))

    def test_direct_terminal_append_cannot_bypass_committed_expected_inputs(self):
        controller = self._prepared()
        append_event(controller.journal_path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
        from kil.v3b2_journal import JournalError
        with self.assertRaisesRegex(JournalError, "observed"):
            append_event(controller.journal_path, "profile_start_complete", {"colima_profile": "kil-v3-lab"})

    def test_profile_only_failure_recovers_without_fabricating_cluster_identity(self):
        controller = self._prepared()
        controller._journal_pair("profile_start", {"colima_profile": "kil-v3-lab"}, lambda: self.runner.run(colima_start_command()))
        latch_teardown(controller.journal_path)
        controller._recover_to_owned_absence()
        self.assertTrue(controller.owned_absence_proven)
        self.assertFalse(any(command.argv[0] == "kind" for command in self.runner.commands))
        state = load_journal(controller.journal_path)
        self.assertIsNone(state["owned_identity"]["node_container_id"])
        self.assertEqual(state["events"][-1]["event"], "foreign_snapshot_comparison_complete")

    def test_pending_creation_after_failure_retains_only_proved_cleanup_identity(self):
        from kil.v3b2_manifests import render_kind_config
        controller = self._prepared()
        controller.kind_config.write_bytes(render_kind_config(controller.profile))
        controller._journal_pair("profile_start", {"colima_profile": "kil-v3-lab"}, lambda: self.runner.run(colima_start_command()))
        append_event(controller.journal_path, "cluster_create_intent", {"kind_cluster": "kil-v3-lab", "kubeconfig": str(controller.kubeconfig)})
        self.runner.run(kind_create_command(controller._identity))
        latch_teardown(controller.journal_path)
        result = controller.recover()
        self.assertEqual(result["proof_outcome"], "teardown_only")
        names = [row["event"] for row in load_journal(controller.journal_path)["events"]]
        self.assertNotIn("cluster_create_complete", names)
        self.assertIn("cluster_create_abandoned_for_teardown", names)
        resumed = V3B2Controller(self.paths, self.runner)
        self.assertEqual(resumed._identity.node_container_id, "a" * 64)
        resumed._recover_to_owned_absence()
        self.assertTrue(resumed.owned_absence_proven)
        self.assertEqual(sum(command.argv[:3] == ("kind", "delete", "cluster") for command in self.runner.commands), 1)

    def test_crash_before_proof_write_retains_exact_pending_intent(self):
        controller = self._prepared()
        self.runner.profiles = [self._owned_profile()]
        append_event(controller.journal_path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
        from kil import v3b2_proofs as proofs
        with patch.object(proofs, "observation_bundle", side_effect=RuntimeError("crash before proof")):
            with self.assertRaisesRegex(RuntimeError, "before proof"):
                controller._observe_terminal()
        self.assertEqual(load_journal(controller.journal_path)["phase"], "profile_start_intent")
        self.assertEqual(list(self.paths.private.glob("proof-1-*.json")), [])
        self.assertEqual(V3B2Controller(self.paths, self.runner).recover()["proof_outcome"], "complete")

    def test_registry_rejects_foreign_command_authority_even_with_owned_output(self):
        from kil.v3b2_journal import load_expected_context, append_observed_terminal
        from kil.v3b2_proofs import RawObservation
        controller = self._prepared()
        self.runner.profiles = [self._owned_profile()]
        append_event(controller.journal_path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
        context = load_expected_context(controller.journal_path)
        original = next(row for row in controller._collect_observations(context) if row.label == 'profile_inventory')
        changed = RawObservation(original.label, ("colima", "status", "--profile", "foreign"), original.env,
                                 original.returncode, original.stdout, original.stderr)
        self.assertEqual(append_observed_terminal(controller.journal_path, context, (changed,)).outcome, "unknown")
        self.assertEqual(load_journal(controller.journal_path)["phase"], "profile_start_intent")

    def test_replay_rejects_terminal_relabeling_with_unchanged_valid_raw_proof(self):
        from kil.v3b2_proofs import canonical
        controller = self._prepared()
        with self.assertRaises(ControllerError):
            controller._journal_pair("profile_start", {"colima_profile": "kil-v3-lab"}, lambda: CommandResult(0, "", ""))
        journal = load_journal(controller.journal_path)
        terminal = journal["events"][-1]
        self.assertEqual(terminal["event"], "profile_start_failed")
        terminal["event"] = journal["phase"] = "profile_start_complete"
        terminal["details"] = {key: value for key, value in terminal["details"].items()
                               if key in {"colima_profile", "observed_proof_sha256"}}
        controller.journal_path.write_bytes(canonical(journal))
        with self.assertRaisesRegex(ControllerError, "prior_proof_invalid"):
            V3B2Controller(self.paths, self.runner)


if __name__ == "__main__":
    unittest.main()
