from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import importlib.util
from unittest.mock import patch

from kil.v3b2_controller import (
    CommandResult,
    ControllerError,
    ControllerPaths,
    V3B2Controller,
)
from kil.v3b2_contracts import TRACKS
from kil.v3b2_evidence import verify_bundle


HEX64 = "a" * 64
SOURCE_COMMIT = "d" * 40
NOMINAL_REQUEST_ID = "v3b1-central-request"


class FakeRunner:
    def __init__(self, profiles: list[dict[str, object]] | None = None) -> None:
        self.profiles = [] if profiles is None else profiles
        self.commands = []
        self.attach_count = 0
        self.fail_track: str | None = None
        self.inject_application_record = False

    def run(self, command):
        self.commands.append(command)
        argv = command.argv
        if argv == ("git", "rev-parse", "HEAD") or argv == ("git", "rev-parse", "origin/main"):
            return CommandResult(0, SOURCE_COMMIT + "\n", "")
        if argv == ("git", "status", "--porcelain"):
            return CommandResult(0, "", "")
        if argv == ("colima", "list", "--json"):
            return CommandResult(0, json.dumps(self.profiles, separators=(",", ":")) + "\n", "")
        if argv == ("docker", "context", "show"):
            return CommandResult(0, "desktop-linux\n", "")
        if Path(argv[0]).name == "docker" and argv[1:] == ("--version",):
            return CommandResult(0, "Docker version 29.7.2\n", "")
        if Path(argv[0]).name == "kind" and argv[1:] == ("version",):
            return CommandResult(0, "kind v0.32.0\n", "")
        if Path(argv[0]).name == "kubectl" and argv[1:] == ("version", "--client", "-o", "json"):
            return CommandResult(0, '{"clientVersion":{"gitVersion":"v1.36.3"}}\n', "")
        if argv == ("colima", "version"):
            return CommandResult(0, "colima version 0.10.3\n", "")
        if argv == ("limactl", "--version"):
            return CommandResult(0, "limactl version 2.2.0\n", "")
        if argv[:2] == ("docker", "inspect"):
            return CommandResult(0, json.dumps([{
                "Id": "a" * 64,
                "Image": "sha256:" + "9" * 64,
                "Config": {"Image": "kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5"},
            }]) + "\n", "")
        if "namespace" in argv and "kube-system" in argv:
            return CommandResult(0, json.dumps({"metadata": {"uid": "11111111-1111-4111-8111-111111111111", "resourceVersion": "1"}}) + "\n", "")
        if any(item.startswith("namespaces,pods,services") for item in argv):
            from tests.test_v3b2_evidence import private_evidence
            runtime = private_evidence(request_free=True)["runtime_identities"]
            projection = {
                "topology_attestation": runtime["topology_attestation"],
                "policy_attestation": runtime["policy_attestation"],
            }
            accepted_kil = "45a167d79b92f352af05a3e9cb8a9df8e972e38ab23d04ca692053e2eaf63649"
            accepted_envoy = "57e14a549d7bd43c8d3f6d03e8cfa653e037d4b38e133acd9b54f38c524401b4"
            for item in projection["topology_attestation"]["pod_images"]:
                if item["image_role"] != "workload":
                    continue
                digest = accepted_envoy if item["container"] == "envoy" else accepted_kil
                item["image"] = (
                    "docker.io/envoyproxy/envoy@sha256:" + digest
                    if item["container"] == "envoy"
                    else "kil.local/kil-v3b2:sha256-" + digest
                )
                item["image_id"] = "docker-pullable://fixture@sha256:" + digest
            return CommandResult(0, json.dumps(projection, sort_keys=True, separators=(",", ":")) + "\n", "")
        if "attach" in argv:
            self.attach_count += 1
            track = json.loads(command.stdin)["track"]
            if self.fail_track == track:
                return CommandResult(9, "", "injected")
            outcome = "deny" if track == TRACKS[2] else "permit"
            status = 403 if outcome == "deny" else 200
            marker = 0 if outcome == "deny" else 1
            return CommandResult(0, json.dumps({"outcome": outcome, "http_status": status, "target_marker_count": marker}) + "\n", "")
        if "logs" in argv:
            if self.inject_application_record and "deployment/authz" in argv:
                return CommandResult(0, '{"unexpected":"record"}\n', "")
            if self.attach_count:
                namespace = argv[argv.index("--namespace") + 1]
                track = dict((namespace, track) for track, namespace in __import__("kil.v3b2_contracts", fromlist=["TRACK_NAMESPACES"]).TRACK_NAMESPACES)[namespace]
                deny = track == TRACKS[2]
                decision = "deny" if deny else "permit"
                status = 403 if deny else 200
                digest = __import__("hashlib").sha256(f"{track}:{decision}".encode()).hexdigest()
                common = {"track": track, "request_id": NOMINAL_REQUEST_ID}
                if "pod/driver" in argv:
                    record = {**common, "attempt": 1, "decision": decision, "http_status": status, "decision_digest": digest}
                elif "deployment/authz" in argv:
                    record = {**common, "decision": decision, "decision_digest": digest}
                elif "deployment/envoy" in argv:
                    record = {**common, "decision_digest": digest, "upstream_attempted": not deny, "upstream_status": None if deny else status}
                elif deny:
                    return CommandResult(0, "", "")
                else:
                    record = {**common, "marker": 1}
                return CommandResult(0, json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", "")
            return CommandResult(0, "", "")
        return CommandResult(0, "{}\n", "")


def foreign(name: str, status: str) -> dict[str, object]:
    return {
        "name": name, "status": status, "arch": "aarch64", "cpus": 2,
        "memory": 4, "disk": 20, "runtime": "docker",
    }


class V3B2ControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name).resolve()
        (root / "deploy/kind").mkdir(parents=True)
        source = Path(__file__).resolve().parents[1] / "deploy/kind/v3b2-profile.json"
        (root / "deploy/kind/v3b2-profile.json").write_bytes(source.read_bytes())
        calico = Path(__file__).resolve().parents[1] / "deploy/kind/calico-v3.32.0.yaml"
        (root / "deploy/kind/calico-v3.32.0.yaml").write_bytes(calico.read_bytes())
        (root / ".tools/bin").mkdir(parents=True)
        tool_rows = {}
        for name in ("docker", "kind", "kubectl"):
            payload = ("tool-" + name).encode()
            binary = root / ".tools/bin" / name
            binary.write_bytes(payload)
            binary.chmod(0o755)
            tool_rows[name] = {
                "archive_sha256": "a" * 64,
                "byte_size": len(payload),
                "checksum_attestation": "test",
                "executable_sha256": __import__("hashlib").sha256(payload).hexdigest(),
                "source_url": "https://example.invalid/" + name,
                "version_output": {"docker": "Docker version 29.7.2", "kind": "kind v0.32.0", "kubectl": '{"clientVersion":{"gitVersion":"v1.36.3"}}'}[name],
            }
        (root / ".tools/locks").mkdir()
        v3b_profile = Path(__file__).resolve().parents[1] / "deploy/kind/v3b-profile.json"
        (root / "deploy/kind/v3b-profile.json").write_bytes(v3b_profile.read_bytes())
        accepted = Path(__file__).resolve().parents[1] / "artifacts/generated/v3b1-local-envoy"
        shutil.copytree(accepted, root / "artifacts/generated/v3b1-local-envoy")
        lock = {
            "schema_version": "kil.v3b-tools-lock.v1",
            "profile_sha256": __import__("hashlib").sha256(v3b_profile.read_bytes()).hexdigest(),
            "tools": tool_rows,
        }
        (root / ".tools/locks/v3b-tools.json").write_text(json.dumps(lock, sort_keys=True, separators=(",", ":")) + "\n")
        self.paths = ControllerPaths(
            repository=root,
            profile=root / "deploy/kind/v3b2-profile.json",
            tools=root / ".tools/bin",
            private=root / ".tools/v3b2-private",
            public=root / "artifacts/generated/v3b2-kind-calico",
        )
        self.runner = FakeRunner()
        self.controller = V3B2Controller(self.paths, self.runner)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_controller_paths_are_frozen_slotted_absolute_and_contained(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.paths.repository = Path("/")  # type: ignore[misc]
        with self.assertRaises(ControllerError):
            ControllerPaths(Path("."), *([Path("/tmp/x")] * 4))

    def test_preflight_precedes_every_mutation_and_allows_foreign_profiles(self) -> None:
        self.runner.profiles = [foreign("client-a", "Running"), foreign("client-b", "Stopped")]
        result = self.controller.preflight()
        self.assertEqual(result["owned_profile"], "absent")
        self.assertEqual([command for command in self.runner.commands if command.mutating], [])
        self.assertTrue(self.controller.journal_path.exists())

    def test_preflight_rejects_owned_presence_and_ambiguous_inventory(self) -> None:
        for profiles in (
            [foreign("kil-v3-lab", "Running")],
            [foreign("client-a", "Running"), foreign("client-a", "Stopped")],
        ):
            with self.subTest(profiles=profiles):
                runner = FakeRunner(profiles)
                with self.assertRaises(ControllerError):
                    V3B2Controller(self.paths, runner).preflight()

    def test_preflight_rejects_tool_byte_drift_before_any_mutation(self) -> None:
        (self.paths.tools / "kind").write_bytes(b"tampered")
        with self.assertRaisesRegex(ControllerError, "tool_identity_mismatch"):
            self.controller.preflight()
        self.assertFalse(any(command.mutating for command in self.runner.commands))

    def test_global_docker_context_is_read_only(self) -> None:
        self.controller.preflight()
        contexts = [command for command in self.runner.commands if command.argv[:2] == ("docker", "context")]
        self.assertEqual(len(contexts), 1)
        self.assertFalse(contexts[0].mutating)

    def test_up_uses_only_owned_profile_cluster_and_applies_policy_before_workloads(self) -> None:
        self.controller.up()
        mutations = [command for command in self.runner.commands if command.mutating]
        for command in mutations:
            if command.argv[0] == "colima":
                self.assertIn(("--profile", "kil-v3-lab"), tuple(zip(command.argv, command.argv[1:])))
            if command.argv[0] == "kind":
                self.assertIn(("--name", "kil-v3-lab"), tuple(zip(command.argv, command.argv[1:])))
                self.assertIn(("--kubeconfig", str(self.controller.kubeconfig)), tuple(zip(command.argv, command.argv[1:])))
        applied = [json.loads(command.stdin) for command in mutations if command.argv[-3:] == ("apply", "-f", "-")]
        kinds = [{item["kind"] for item in payload["items"]} for payload in applied]
        self.assertEqual(kinds[0], {"Namespace"})
        self.assertEqual(kinds[1], {"NetworkPolicy"})
        self.assertNotIn("NetworkPolicy", kinds[2])
        self.assertEqual(self.controller.kind_config.read_bytes(), __import__("kil.v3b2_manifests", fromlist=["render_kind_config"]).render_kind_config(self.controller.profile))

    def test_request_free_sends_no_attach_stdin_or_application_records(self) -> None:
        result = self.controller.request_free()
        self.assertEqual(result["instructions_sent"], 0)
        self.assertFalse(any("attach" in command.argv for command in self.runner.commands))
        self.assertFalse(any(command.stdin is not None and "attach" in command.argv for command in self.runner.commands))
        self.assertEqual(result["application_records"], 0)
        self.assertTrue(self.controller.owned_absence_proven)
        started = [event for event in self.controller.events if event[0] == "driver_start_complete"]
        self.assertEqual(len(started), 3)
        names = [command.argv[-3] for command in self.runner.commands if "scale" in command.argv]
        self.assertEqual(names, ["--namespace", "--namespace", "--namespace"])
        event_names = [name for name, _details in self.controller.events]
        self.assertLess(event_names.index("driver_cancel_complete"), event_names.index("envoy_quiesce_intent"))
        self.assertLess(event_names.index("envoy_quiesce_complete"), event_names.index("evidence_freeze_intent"))
        self.assertLess(event_names.index("foreign_snapshot_comparison_complete"), event_names.index("publication_intent"))
        verified = verify_bundle(Path(result["bundle"]))
        self.assertEqual(verified.result_class, "diagnostic_request_free_kind_calico_readiness")
        self.assertEqual(len(self.controller._captured_sources), 12)
        self.assertTrue(all(source.identity.object_uid != "uid-0" for source in self.controller._captured_sources))

    def test_separate_process_can_continue_a_preflight_only_journal_into_request_free(self) -> None:
        self.controller.preflight()
        resumed = V3B2Controller(self.paths, self.runner)
        result = resumed.request_free()
        self.assertEqual(result["instructions_sent"], 0)
        self.assertTrue(resumed.owned_absence_proven)

    def test_request_free_rejects_any_application_record_but_still_tears_down(self) -> None:
        self.runner.inject_application_record = True
        with self.assertRaisesRegex(ControllerError, "request_free_records_present"):
            self.controller.request_free()
        self.assertTrue(self.controller.owned_absence_proven)

    def test_down_resumes_bound_runtime_without_current_context_or_discovery_selected_delete(self) -> None:
        self.controller.up()
        resumed = V3B2Controller(self.paths, self.runner)
        result = resumed.down()
        self.assertTrue(result["owned_teardown"])
        self.assertTrue(resumed.owned_absence_proven)
        for command in self.runner.commands:
            if command.mutating and command.argv[0] == "kind":
                self.assertIn("kil-v3-lab", command.argv)
                self.assertIn(str(resumed.kubeconfig), command.argv)
            self.assertNotIn("current-context", command.argv)

    def test_nominal_persists_intent_before_each_single_attach(self) -> None:
        bundle = self.controller.nominal()
        self.assertEqual(self.runner.attach_count, 3)
        events = self.controller.events
        for track in TRACKS:
            intent = next(index for index, event in enumerate(events) if event[0] == "request_intent" and event[1]["track"] == track)
            attach = next(index for index, event in enumerate(events) if event[0] == "kubectl_attach" and event[1]["track"] == track)
            self.assertLess(intent, attach)
        self.assertEqual(bundle.result_tuple, (("permit", 200, 1), ("permit", 200, 1), ("deny", 403, 0)))
        self.assertTrue(self.controller.owned_absence_proven)
        self.assertIsNotNone(self.controller.published_path)
        verified = verify_bundle(self.controller.published_path)
        self.assertEqual(verified.result_class, "intermediate_provisional_kind_calico_nominal")

    def test_recover_attests_successful_profile_start_without_replaying_mutation(self) -> None:
        import kil.v3b2_controller as module

        original = module.append_event
        failed = False

        def fail_completion(path, event, details):
            nonlocal failed
            if event == "profile_start_complete" and not failed:
                failed = True
                raise OSError("injected persistence failure")
            return original(path, event, details)

        with patch.object(module, "append_event", side_effect=fail_completion):
            with self.assertRaises(OSError):
                self.controller.up()
        resumed = V3B2Controller(self.paths, self.runner)
        result = resumed.recover()
        starts = [command for command in self.runner.commands if command.argv[:2] == ("colima", "start")]
        self.assertEqual(len(starts), 1)
        self.assertEqual(result["completed"], "profile_start")
        self.assertFalse(any("attach" in command.argv for command in self.runner.commands))

    def test_recover_attests_successful_cluster_create_without_replaying_create(self) -> None:
        import kil.v3b2_controller as module

        original = module.append_event
        failed = False

        def fail_completion(path, event, details):
            nonlocal failed
            if event == "cluster_create_complete" and not failed:
                failed = True
                raise OSError("injected persistence failure")
            return original(path, event, details)

        with patch.object(module, "append_event", side_effect=fail_completion):
            with self.assertRaises(OSError):
                self.controller.up()
        resumed = V3B2Controller(self.paths, self.runner)
        result = resumed.recover()
        creates = [command for command in self.runner.commands if command.argv[:3] == ("kind", "create", "cluster")]
        self.assertEqual(len(creates), 1)
        self.assertEqual(result["completed"], "cluster_create")
        self.assertFalse(any("attach" in command.argv for command in self.runner.commands))

    def test_every_request_free_completion_persistence_boundary_recovers_without_request(self) -> None:
        import kil.v3b2_controller as module

        families = (
            "calico_apply", "application_apply", "readiness", "driver_start",
            "driver_cancel", "envoy_quiesce", "evidence_freeze", "cluster_delete",
            "cluster_absence_proof", "profile_stop", "profile_delete",
            "profile_absence_proof", "foreign_snapshot_comparison", "publication",
        )
        for index, family in enumerate(families):
            with self.subTest(family=family):
                if index:
                    self.tearDown()
                    self.setUp()
                original = module.append_event
                failed = False

                def fail_completion(path, event, details):
                    nonlocal failed
                    if event == family + "_complete" and not failed:
                        failed = True
                        raise OSError("injected persistence failure")
                    return original(path, event, details)

                with patch.object(module, "append_event", side_effect=fail_completion):
                    with self.assertRaises(OSError):
                        self.controller.request_free()
                resumed = V3B2Controller(self.paths, self.runner)
                result = resumed.recover()
                self.assertEqual(result["completed"], family)
                self.assertFalse(any("attach" in command.argv for command in self.runner.commands))
                for command in self.runner.commands:
                    if command.mutating and command.argv[0] in {"kind", "colima"}:
                        self.assertIn("kil-v3-lab", command.argv)

    def test_request_result_persistence_failure_recovers_by_freezing_never_replay(self) -> None:
        import kil.v3b2_controller as module

        original = module.append_event
        failed = False

        def fail_result(path, event, details):
            nonlocal failed
            if event == "request_result" and not failed:
                failed = True
                raise OSError("injected persistence failure")
            return original(path, event, details)

        with patch.object(module, "append_event", side_effect=fail_result):
            with self.assertRaises(OSError):
                self.controller.nominal()
        self.assertEqual(self.runner.attach_count, 1)
        resumed = V3B2Controller(self.paths, self.runner)
        result = resumed.recover()
        self.assertEqual(result["completed"], "evidence_freeze")
        self.assertEqual(self.runner.attach_count, 1)

    def test_post_intent_failure_cancels_later_drivers_and_never_retries(self) -> None:
        self.runner.fail_track = TRACKS[0]
        with self.assertRaises(ControllerError):
            self.controller.nominal()
        self.assertEqual(self.runner.attach_count, 1)
        self.assertTrue(self.controller.owned_absence_proven)
        attached = [event[1]["track"] for event in self.controller.events if event[0] == "kubectl_attach"]
        self.assertEqual(attached, [TRACKS[0]])

    def test_cli_exposes_only_fixed_commands_and_view_bundle(self) -> None:
        cli_path = Path(__file__).resolve().parents[1] / "tools/v3b2_kind_calico.py"
        spec = importlib.util.spec_from_file_location("v3b2_kind_calico_cli", cli_path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        parser = module.make_parser()
        for name in ("preflight", "up", "request-free", "nominal", "down", "recover"):
            self.assertEqual(parser.parse_args([name]).command, name)
        viewed = parser.parse_args(["view", "--bundle", "/tmp/public-bundle"])
        self.assertEqual(viewed.bundle, Path("/tmp/public-bundle"))
        with self.assertRaises(SystemExit):
            parser.parse_args(["up", "--profile", "foreign"])


if __name__ == "__main__":
    unittest.main()
