from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from kil.v3b2_journal import (
    Command,
    JournalError,
    JournalInputs,
    OwnedIdentity,
    RecoveryObservation,
    append_event,
    create_journal,
    kind_delete_command,
    load_journal,
    owned_commands,
    recovery_plan,
)


HEX64 = "a" * 64
NODE_ID = "b" * 64
CLUSTER_UID = "cluster-incarnation-uid"


def adjacent_pairs(values: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    return tuple(zip(values, values[1:]))


class V3B2JournalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.private = Path(self.temporary.name).resolve() / "private"
        self.path = self.private / "journal.json"
        self.kubeconfig = str(self.private / "kubeconfig")
        self.identity = OwnedIdentity(
            colima_profile="kil-v3-lab",
            docker_host="unix:///Users/test/.colima/kil-v3-lab/docker.sock",
            kind_cluster="kil-v3-lab",
            kubeconfig=self.kubeconfig,
            cluster_incarnation_uid=CLUSTER_UID,
            node_container_id=NODE_ID,
        )
        self.inputs = JournalInputs(
            schema_version="kil.v3b2-journal.v1",
            run_id=HEX64,
            execution_nonce="c" * 64,
            source_commit="d" * 40,
            profile_sha256="e" * 64,
            phase="prepared",
            global_context_before="desktop-linux",
            foreign_profiles_before=(("client-project", "Running"),),
            expected_objects=("kil-v3-baseline/driver",),
            owned_identity=self.identity,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _journal(self) -> dict[str, object]:
        return create_journal(self.path, self.inputs)

    def _append(self, name: str, details: dict[str, object] | None = None) -> dict[str, object]:
        return append_event(self.path, name, details or {})

    def _profile_started(self) -> None:
        self._append("profile_start_intent", {"colima_profile": "kil-v3-lab"})
        self._append("profile_start_complete", {"colima_profile": "kil-v3-lab"})

    def _cluster_created(self) -> None:
        self._profile_started()
        intent = {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig}
        self._append("cluster_create_intent", intent)
        self._append(
            "cluster_create_complete",
            {
                **intent,
                "cluster_incarnation_uid": CLUSTER_UID,
                "node_container_id": NODE_ID,
                "docker_host": self.identity.docker_host,
            },
        )

    def _ready(self) -> None:
        self._cluster_created()
        for family, details in (
            ("calico_apply", {"manifest_sha256": "2" * 64}),
            ("application_apply", {"manifest_sha256": "3" * 64}),
            ("readiness", {"attestation_sha256": "4" * 64}),
        ):
            self._append(f"{family}_intent", details)
            self._append(f"{family}_complete", details)

    def _start_driver(self, namespace: str, uid: str) -> dict[str, object]:
        details = {"namespace": namespace, "pod": "driver", "uid": uid}
        self._append("driver_start_intent", details)
        self._append("driver_start_complete", details)
        return details

    def _freeze(self) -> None:
        details = {"evidence_sha256": "5" * 64}
        self._append("evidence_freeze_intent", details)
        self._append("evidence_freeze_complete", details)

    def _canonical_events(self) -> list[tuple[str, dict[str, object]]]:
        profile = {"colima_profile": "kil-v3-lab"}
        cluster = {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig}
        cluster_complete = {
            **cluster,
            "cluster_incarnation_uid": CLUSTER_UID,
            "node_container_id": NODE_ID,
            "docker_host": self.identity.docker_host,
        }
        driver = {"namespace": "kil-v3-baseline", "pod": "driver", "uid": "driver-uid"}
        request = {"track": "credential_policy_baseline", "request_id": "v3b1-central-request", "case_sha256": "f" * 64}
        return [
            ("profile_start_intent", profile), ("profile_start_complete", profile),
            ("cluster_create_intent", cluster), ("cluster_create_complete", cluster_complete),
            ("calico_apply_intent", {"manifest_sha256": "2" * 64}), ("calico_apply_complete", {"manifest_sha256": "2" * 64}),
            ("application_apply_intent", {"manifest_sha256": "3" * 64}), ("application_apply_complete", {"manifest_sha256": "3" * 64}),
            ("readiness_intent", {"attestation_sha256": "4" * 64}), ("readiness_complete", {"attestation_sha256": "4" * 64}),
            ("driver_start_intent", driver), ("driver_start_complete", driver),
            ("request_intent", request), ("request_result", {**request, "result_sha256": "1" * 64}),
            ("evidence_freeze_intent", {"evidence_sha256": "5" * 64}), ("evidence_freeze_complete", {"evidence_sha256": "5" * 64}),
            ("driver_cancel_intent", driver), ("driver_cancel_complete", driver),
            ("cluster_delete_intent", cluster), ("cluster_delete_complete", cluster),
            ("cluster_absence_proof_intent", {"kind_cluster": "kil-v3-lab", "node_container_id": NODE_ID}), ("cluster_absence_proof_complete", {"kind_cluster": "kil-v3-lab", "node_container_id": NODE_ID}),
            ("profile_stop_intent", profile), ("profile_stop_complete", profile),
            ("profile_delete_intent", profile), ("profile_delete_complete", profile),
            ("profile_absence_proof_intent", profile), ("profile_absence_proof_complete", profile),
            ("foreign_snapshot_comparison_intent", {"unchanged": True, "attestation_sha256": "6" * 64}), ("foreign_snapshot_comparison_complete", {"unchanged": True, "attestation_sha256": "6" * 64}),
            ("publication_intent", {"public_commitment_sha256": "7" * 64}), ("publication_complete", {"public_commitment_sha256": "7" * 64}),
        ]

    def _observation(self, **changes: object) -> RecoveryObservation:
        values = {
            "docker_host": self.identity.docker_host,
            "colima_profile": "kil-v3-lab",
            "kind_cluster": "kil-v3-lab",
            "cluster_incarnation_uid": CLUSTER_UID,
            "node_container_id": NODE_ID,
            "driver_pods": (),
        }
        values.update(changes)
        return RecoveryObservation(**values)  # type: ignore[arg-type]

    def test_journal_exists_before_first_owned_mutation(self) -> None:
        journal = self._journal()
        self.assertTrue(self.path.exists())
        self.assertEqual(journal["events"], [])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.private.stat().st_mode & 0o777, 0o700)

    def test_creation_is_exclusive_canonical_and_durable_shape(self) -> None:
        journal = self._journal()
        expected = json.dumps(journal, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        self.assertEqual(self.path.read_text(encoding="utf-8"), expected)
        with self.assertRaisesRegex(JournalError, "already exists"):
            create_journal(self.path, self.inputs)

    def test_journal_records_are_frozen_and_exactly_typed(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.identity.colima_profile = "foreign"  # type: ignore[misc]
        invalid = [
            {"run_id": True},
            {"foreign_profiles_before": [["client-project", "Running"]]},
            {"expected_objects": ["object"]},
            {"owned_identity": object()},
        ]
        for replacement in invalid:
            values = {field: getattr(self.inputs, field) for field in self.inputs.__dataclass_fields__}
            values.update(replacement)
            with self.subTest(replacement=replacement), self.assertRaises(JournalError):
                JournalInputs(**values)

    def test_every_colima_mutation_names_only_kil_profile(self) -> None:
        for command in owned_commands(self.identity):
            if command.argv[0] == "colima" and command.mutating:
                self.assertIn(("--profile", "kil-v3-lab"), adjacent_pairs(command.argv))
                self.assertNotIn("default", command.argv)

    def test_kind_delete_uses_exact_name_kubeconfig_and_environment(self) -> None:
        command = kind_delete_command(self.identity)
        self.assertEqual(command.argv[0:4], ("kind", "delete", "cluster", "--name"))
        self.assertEqual(command.argv[4], "kil-v3-lab")
        self.assertIn(("--kubeconfig", self.kubeconfig), adjacent_pairs(command.argv))
        self.assertNotIn("current-context", command.argv)
        self.assertEqual(
            command.env,
            (
                ("DOCKER_CONFIG", str(self.private / "docker-config")),
                ("DOCKER_HOST", "unix:///Users/test/.colima/kil-v3-lab/docker.sock"),
            ),
        )

    def test_command_rejects_mutable_or_ambiguous_authority(self) -> None:
        cases = (
            {"argv": ["kind"], "timeout_s": 1},
            {"argv": ("kind",), "timeout_s": True},
            {"argv": ("kind",), "timeout_s": 0},
            {"argv": ("kind",), "timeout_s": 1, "env": (("DOCKER_HOST", "one"), ("DOCKER_HOST", "two"))},
            {"argv": ("kind",), "timeout_s": 1, "env": (("DOCKER_HOST", ""),)},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(JournalError):
                Command(**kwargs)  # type: ignore[arg-type]

    def test_command_payloads_are_bounded(self) -> None:
        cases = (
            {"argv": tuple("x" for _ in range(257)), "timeout_s": 1},
            {"argv": ("tool", "x" * 65537), "timeout_s": 1},
            {"argv": ("tool",), "timeout_s": 1, "stdin": b"x" * (1024 * 1024 + 1)},
            {"argv": ("tool",), "timeout_s": 1, "env": (("KEY", "x" * 65537),)},
        )
        for kwargs in cases:
            with self.subTest(field=tuple(kwargs)), self.assertRaisesRegex(JournalError, "bound"):
                Command(**kwargs)  # type: ignore[arg-type]

    def test_docker_and_kind_commands_fail_closed_without_both_bindings(self) -> None:
        fields = {field: getattr(self.identity, field) for field in self.identity.__dataclass_fields__}
        for field in ("docker_host", "kubeconfig"):
            changed = dict(fields)
            changed[field] = None
            with self.subTest(field=field), self.assertRaises(JournalError):
                owned_commands(OwnedIdentity(**changed))

    def test_command_builders_reject_owned_identity_subclasses(self) -> None:
        class IdentitySubclass(OwnedIdentity):
            pass

        subclass = IdentitySubclass(
            self.identity.colima_profile,
            self.identity.docker_host,
            self.identity.kind_cluster,
            self.identity.kubeconfig,
            self.identity.cluster_incarnation_uid,
            self.identity.node_container_id,
        )
        with self.assertRaisesRegex(JournalError, "exact OwnedIdentity"):
            owned_commands(subclass)

    def test_typed_command_boundary_rejects_unbound_or_foreign_tool_commands(self) -> None:
        cases = (
            (("docker", "ps"), (), False),
            (("kind", "delete", "cluster", "--name", "foreign"), (("DOCKER_CONFIG", "/tmp/config"), ("DOCKER_HOST", "unix:///tmp/kil-v3-lab/docker.sock")), True),
            (("kubectl", "get", "pods"), (), False),
            (("colima", "stop", "--profile", "foreign"), (), True),
        )
        for argv, env, mutating in cases:
            with self.subTest(argv=argv), self.assertRaises(JournalError):
                Command(argv, 30, env=env, mutating=mutating)

    def test_typed_command_boundary_rejects_duplicate_or_alternate_authority_flags(self) -> None:
        env = (("DOCKER_CONFIG", str(self.private / "docker-config")), ("DOCKER_HOST", self.identity.docker_host))
        cases = (
            ("colima", "stop", "--profile", "kil-v3-lab", "--profile", "kil-v3-lab"),
            ("colima", "stop", "--profile=kil-v3-lab"),
            ("kind", "delete", "cluster", "--name", "kil-v3-lab", "--name", "kil-v3-lab", "--kubeconfig", self.kubeconfig),
            ("kind", "delete", "cluster", "--name=kil-v3-lab", "--kubeconfig", self.kubeconfig),
            ("kubectl", "--kubeconfig", self.kubeconfig, "--kubeconfig", self.kubeconfig, "get", "pods"),
            ("kubectl", f"--kubeconfig={self.kubeconfig}", "get", "pods"),
        )
        for argv in cases:
            with self.subTest(argv=argv), self.assertRaises(JournalError):
                Command(argv, 30, env=env if argv[0] == "kind" else (), mutating=argv[0] != "kubectl")

    def test_tool_argv_grammars_reject_short_aliases_and_extra_flags(self) -> None:
        env = (("DOCKER_CONFIG", str(self.private / "docker-config")), ("DOCKER_HOST", self.identity.docker_host))
        cases = (
            (("colima", "stop", "-p", "kil-v3-lab"), (), True),
            (("colima", "status", "--profile", "kil-v3-lab", "--verbose"), (), False),
            (("kind", "delete", "cluster", "-n", "kil-v3-lab", "--kubeconfig", self.kubeconfig), env, True),
            (("kind", "delete", "cluster", "--name", "kil-v3-lab", "--kubeconfig", self.kubeconfig, "--retain"), env, True),
            (("kubectl", "-k", self.kubeconfig, "get", "pods"), (), False),
            (("kubectl", "--kubeconfig", self.kubeconfig, "get", "pods", "--context", "foreign"), (), False),
        )
        for argv, command_env, mutating in cases:
            with self.subTest(argv=argv), self.assertRaises(JournalError):
                Command(argv, 30, env=command_env, mutating=mutating)

    def test_command_rejects_every_unreviewed_executable_spelling(self) -> None:
        for executable in ("rm", "sh", "env", "unknown", "/usr/bin/kubectl", "Kubectl"):
            with self.subTest(executable=executable), self.assertRaises(JournalError):
                Command((executable, "noop"), 30)

    def test_create_rejects_oversized_inputs_before_creating_any_file(self) -> None:
        values = {field: getattr(self.inputs, field) for field in self.inputs.__dataclass_fields__}
        values["expected_objects"] = tuple(f"{index:04d}-" + "x" * 4090 for index in range(300))
        oversized = JournalInputs(**values)
        with self.assertRaisesRegex(JournalError, "byte bound"):
            create_journal(self.path, oversized)
        self.assertFalse(self.path.exists())

    def test_lifecycle_rejects_phase_skips_overlapping_intents_and_publication_first(self) -> None:
        invalid_first = (
            ("cluster_create_intent", {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig}),
            ("publication_intent", {"public_commitment_sha256": "7" * 64}),
        )
        for event, details in invalid_first:
            self.path.unlink(missing_ok=True)
            self._journal()
            with self.subTest(event=event), self.assertRaisesRegex(JournalError, "phase|order"):
                self._append(event, details)
        self.path.unlink(missing_ok=True)
        self._journal()
        self._append("profile_start_intent", {"colima_profile": "kil-v3-lab"})
        with self.assertRaisesRegex(JournalError, "pending|overlap"):
            self._append("profile_stop_intent", {"colima_profile": "kil-v3-lab"})

    def test_request_intent_blocks_forward_work_and_freeze_makes_late_result_terminal(self) -> None:
        self.path.unlink(missing_ok=True)
        self._journal()
        self._ready()
        self._start_driver("kil-v3-baseline", "driver-uid")
        request = {"track": "credential_policy_baseline", "request_id": "v3b1-central-request", "case_sha256": "f" * 64}
        self._append("request_intent", request)
        with self.assertRaisesRegex(JournalError, "pending|terminal|order"):
            self._append("driver_start_intent", {"namespace": "kil-v3-signed", "pod": "driver", "uid": "signed-driver"})
        freeze = {"evidence_sha256": "5" * 64}
        self._append("evidence_freeze_intent", freeze)
        self._append("evidence_freeze_complete", freeze)
        with self.assertRaisesRegex(JournalError, "terminal|order"):
            self._append("request_result", {**request, "result_sha256": "1" * 64})

    def test_create_sets_private_mode_before_first_file_fsync(self) -> None:
        order: list[str] = []
        real_fchmod = os.fchmod
        real_fsync = os.fsync

        def observed_fchmod(descriptor: int, mode: int) -> None:
            order.append("fchmod")
            real_fchmod(descriptor, mode)

        def observed_fsync(descriptor: int) -> None:
            order.append("fsync")
            real_fsync(descriptor)

        with patch("kil.v3b2_journal.os.fchmod", side_effect=observed_fchmod), patch(
            "kil.v3b2_journal.os.fsync", side_effect=observed_fsync
        ):
            self._journal()
        self.assertLess(order.index("fchmod"), order.index("fsync"))

    def test_recovery_requires_journaled_intent_and_external_observation_before_delete(self) -> None:
        fresh = self._journal()
        self.assertFalse(any(command.mutating for command in recovery_plan(fresh).commands))
        self.path.unlink()
        self._journal()
        self._cluster_created()
        without = recovery_plan(load_journal(self.path))
        self.assertTrue(without.commands)
        self.assertFalse(any(command.mutating for command in without.commands))
        self.assertEqual(without.next_intent[0], "cluster_delete_intent")
        matching = recovery_plan(load_journal(self.path), self._observation())
        self.assertFalse(any(command.mutating for command in matching.commands))
        self._append("cluster_delete_intent", dict(matching.next_intent[1]))
        authorized = recovery_plan(load_journal(self.path), self._observation())
        self.assertTrue(any(command.argv[:3] == ("kind", "delete", "cluster") for command in authorized.commands))
        with self.assertRaisesRegex(JournalError, "manual_recovery_required"):
            recovery_plan(load_journal(self.path), self._observation(node_container_id="9" * 64))

    def test_pending_cluster_create_attests_and_never_blindly_recreates(self) -> None:
        self._journal()
        self._profile_started()
        pending = self._append("cluster_create_intent", {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig})
        plan = recovery_plan(pending)
        self.assertEqual(len(plan.commands), 1)
        self.assertFalse(plan.commands[0].mutating)
        self.assertEqual(plan.commands[0].argv[:2], ("docker", "inspect"))

    def test_completed_request_recovery_also_freezes_before_observation_gated_cancel(self) -> None:
        self._journal()
        self._ready()
        driver = self._start_driver("kil-v3-baseline", "driver-uid")
        request = {"track": "credential_policy_baseline", "request_id": "v3b1-central-request", "case_sha256": "f" * 64}
        self._append("request_intent", request)
        self._append("request_result", {**request, "result_sha256": "1" * 64})
        freeze = {"evidence_sha256": "5" * 64}
        pending = self._append("evidence_freeze_intent", freeze)
        pending_plan = recovery_plan(pending)
        text = "\n".join(" ".join(command.argv) for command in pending_plan.commands)
        for source in ("pod/driver", "deployment/authz", "deployment/envoy", "deployment/target", "networkpolicies"):
            self.assertIn(source, text)
        self.assertFalse(any(command.mutating for command in pending_plan.commands))
        self._append("evidence_freeze_complete", freeze)
        ungated = recovery_plan(load_journal(self.path))
        self.assertFalse(any(command.mutating for command in ungated.commands))
        observed = self._observation(
            driver_pods=((str(driver["namespace"]), str(driver["pod"]), str(driver["uid"])),)
        )
        gated = recovery_plan(load_journal(self.path), observed)
        self.assertFalse(any(command.mutating for command in gated.commands))
        self._append("driver_cancel_intent", dict(gated.next_intent[1]))
        authorized = recovery_plan(load_journal(self.path), observed)
        self.assertTrue(any("delete" in command.argv for command in authorized.commands))

    def test_ready_request_free_recovery_freezes_even_when_no_driver_was_started(self) -> None:
        self._journal()
        self._ready()
        plan = recovery_plan(load_journal(self.path), self._observation())
        self.assertFalse(any(command.mutating for command in plan.commands))
        self.assertTrue(any("networkpolicies" in argument for command in plan.commands for argument in command.argv))

    def test_request_result_cannot_complete_across_an_evidence_freeze_intent(self) -> None:
        self._journal()
        self._ready()
        self._start_driver("kil-v3-baseline", "driver-uid")
        request = {"track": "credential_policy_baseline", "request_id": "v3b1-central-request", "case_sha256": "f" * 64}
        self._append("request_intent", request)
        self._append("evidence_freeze_intent", {"evidence_sha256": "5" * 64})
        with self.assertRaisesRegex(JournalError, "overlap|order"):
            self._append("request_result", {**request, "result_sha256": "1" * 64})

    def test_load_rejects_noncanonical_duplicate_oversized_and_unsafe_files(self) -> None:
        self._journal()
        canonical = self.path.read_bytes()
        bad_payloads = (
            canonical.rstrip(b"\n") + b" \n",
            b'{"schema_version":"kil.v3b2-journal.v1","schema_version":"kil.v3b2-journal.v1"}\n',
            b"{" + b"x" * (1024 * 1024) + b"}",
            b"\xff",
        )
        for payload in bad_payloads:
            with self.subTest(size=len(payload)):
                self.path.unlink()
                self.path.write_bytes(payload)
                os.chmod(self.path, 0o600)
                with self.assertRaises(JournalError):
                    load_journal(self.path)
        self.path.unlink()
        target = self.private / "target"
        target.write_bytes(canonical)
        self.path.symlink_to(target)
        with self.assertRaisesRegex(JournalError, "symlink|safe"):
            load_journal(self.path)

    def test_lone_surrogates_are_totalized_at_constructor_load_and_append_boundaries(self) -> None:
        values = {field: getattr(self.inputs, field) for field in self.inputs.__dataclass_fields__}
        values["global_context_before"] = "bad\ud800context"
        with self.assertRaises(JournalError):
            JournalInputs(**values)
        with self.assertRaises(JournalError):
            Command(("unknown\ud800",), 30)

        self._journal()
        payload = self.path.read_bytes().replace(b"desktop-linux", b"\\ud800")
        self.path.write_bytes(payload)
        os.chmod(self.path, 0o600)
        with self.assertRaises(JournalError):
            load_journal(self.path)

        self.path.unlink()
        self._journal()
        self._ready()
        self._start_driver("kil-v3-baseline", "driver-uid")
        with self.assertRaises(JournalError):
            self._append("request_intent", {
                "track": "credential_policy_baseline",
                "request_id": "bad\ud800request",
                "case_sha256": "f" * 64,
            })

    def test_append_event_serializes_conflicting_threads_without_lost_update(self) -> None:
        self._journal()
        first_loaded = threading.Event()
        release_first = threading.Event()
        real_load = load_journal
        load_calls = 0
        call_guard = threading.Lock()

        def controlled_load(path: Path) -> dict[str, object]:
            nonlocal load_calls
            with call_guard:
                load_calls += 1
                position = load_calls
            value = real_load(path)
            if position == 1:
                first_loaded.set()
                self.assertTrue(release_first.wait(5))
            return value

        outcomes: list[str] = []

        def worker(started: threading.Event) -> None:
            started.set()
            try:
                append_event(self.path, "profile_start_intent", {"colima_profile": "kil-v3-lab"})
                outcomes.append("success")
            except JournalError:
                outcomes.append("rejected")

        with patch("kil.v3b2_journal.load_journal", side_effect=controlled_load):
            first_started = threading.Event()
            second_started = threading.Event()
            first = threading.Thread(target=worker, args=(first_started,))
            second = threading.Thread(target=worker, args=(second_started,))
            first.start()
            self.assertTrue(first_started.wait(5))
            self.assertTrue(first_loaded.wait(5))
            second.start()
            self.assertTrue(second_started.wait(5))
            second.join(0.1)
            self.assertTrue(second.is_alive())
            with call_guard:
                self.assertEqual(load_calls, 1)
            release_first.set()
            first.join(5)
            second.join(5)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(sorted(outcomes), ["rejected", "success"])
        loaded = load_journal(self.path)
        self.assertEqual(len(loaded["events"]), 1)

    def test_append_rejects_symlink_lock_without_changing_journal(self) -> None:
        original = self._journal()
        target = self.private / "lock-target"
        target.write_text("do not follow", encoding="utf-8")
        lock = self.private / ".journal.json.lock"
        lock.symlink_to(target)
        with self.assertRaisesRegex(JournalError, "lock|symlink|safe"):
            self._append("profile_start_intent", {"colima_profile": "kil-v3-lab"})
        self.assertEqual(load_journal(self.path), original)

    def test_load_rejects_open_schema_wrong_mode_and_path_escape(self) -> None:
        journal = self._journal()
        journal["surprise"] = True
        self.path.write_text(json.dumps(journal, sort_keys=True, separators=(",", ":")) + "\n")
        os.chmod(self.path, 0o600)
        with self.assertRaisesRegex(JournalError, "fields"):
            load_journal(self.path)
        self.path.unlink()
        create_journal(self.path, self.inputs)
        os.chmod(self.path, 0o644)
        with self.assertRaisesRegex(JournalError, "0600"):
            load_journal(self.path)
        with self.assertRaisesRegex(JournalError, "absolute"):
            create_journal(Path("relative/journal.json"), self.inputs)

    def test_append_is_atomic_sequenced_and_revalidates_history(self) -> None:
        self._journal()
        value = self._append("profile_start_intent", {"colima_profile": "kil-v3-lab"})
        value = self._append("profile_start_complete", {"colima_profile": "kil-v3-lab"})
        self.assertEqual([event["sequence"] for event in value["events"]], [1, 2])
        self.assertEqual(load_journal(self.path), value)
        leftovers = tuple(self.private.glob(".journal.json.*"))
        self.assertEqual(leftovers, (self.private / ".journal.json.lock",))
        self.assertEqual(leftovers[0].stat().st_mode & 0o777, 0o600)

    def test_event_grammar_rejects_unknown_duplicates_completion_without_intent_and_open_details(self) -> None:
        self._journal()
        invalid = (
            ("unknown", {}),
            ("profile_start_complete", {"colima_profile": "kil-v3-lab"}),
            ("profile_start_intent", {"colima_profile": "kil-v3-lab", "extra": True}),
            ("profile_start_intent", {"colima_profile": "foreign"}),
        )
        for name, details in invalid:
            with self.subTest(name=name, details=details), self.assertRaises(JournalError):
                append_event(self.path, name, details)
        self._append("profile_start_intent", {"colima_profile": "kil-v3-lab"})
        with self.assertRaisesRegex(JournalError, "duplicated|pending"):
            self._append("profile_start_intent", {"colima_profile": "kil-v3-lab"})

    def test_complete_event_must_match_its_intent_details(self) -> None:
        self._journal()
        self._ready()
        self._append("driver_start_intent", {"namespace": "kil-v3-baseline", "pod": "driver", "uid": "driver-uid"})
        with self.assertRaisesRegex(JournalError, "match|exact intent"):
            self._append("driver_start_complete", {"namespace": "kil-v3-signed", "pod": "driver", "uid": "driver-uid"})

    def test_request_intent_is_terminal_and_never_replayed(self) -> None:
        self._journal()
        self._ready()
        self._start_driver("kil-v3-baseline", "driver-uid")
        request = {"track": "credential_policy_baseline", "request_id": "v3b1-central-request", "case_sha256": "f" * 64}
        claimed = append_event(self.path, "request_intent", request)
        with self.assertRaisesRegex(JournalError, "already claimed"):
            append_event(self.path, "request_intent", request)
        self.assertEqual(recovery_plan(claimed).requests_to_send, ())

    def test_each_track_may_be_claimed_once_but_distinct_tracks_may_advance(self) -> None:
        self._journal()
        self._ready()
        for index, (track, namespace) in enumerate((
            ("credential_policy_baseline", "kil-v3-baseline"),
            ("signed_state_only", "kil-v3-signed"),
            ("signed_plus_local_reduce", "kil-v3-local-reduce"),
        )):
            self._start_driver(namespace, f"driver-uid-{index}")
            details = {"track": track, "request_id": "v3b1-central-request", "case_sha256": "f" * 64}
            self._append("request_intent", details)
            self._append("request_result", {**details, "result_sha256": "1" * 64})

    def test_next_track_driver_requires_prior_track_request_result(self) -> None:
        self._journal()
        self._ready()
        baseline = self._start_driver("kil-v3-baseline", "baseline-driver")
        signed = {"namespace": "kil-v3-signed", "pod": "driver", "uid": "signed-driver"}
        with self.assertRaisesRegex(JournalError, "track|request|order"):
            self._append("driver_start_intent", signed)
        request = {
            "track": "credential_policy_baseline",
            "request_id": "v3b1-central-request",
            "case_sha256": "f" * 64,
        }
        self._append("request_intent", request)
        with self.assertRaisesRegex(JournalError, "pending|terminal|order"):
            self._append("driver_start_intent", signed)
        self._append("request_result", {**request, "result_sha256": "1" * 64})
        self._append("driver_start_intent", signed)
        self._append("driver_start_complete", signed)
        with self.assertRaisesRegex(JournalError, "duplicated|order"):
            self._append("driver_start_intent", baseline)

    def test_request_free_freeze_accepts_zero_or_waiting_drivers_and_closes_forward_work(self) -> None:
        self._journal()
        self._ready()
        freeze = {"evidence_sha256": "5" * 64}
        self._append("evidence_freeze_intent", freeze)
        self._append("evidence_freeze_complete", freeze)

        self.path.unlink()
        self._journal()
        self._ready()
        self._start_driver("kil-v3-baseline", "driver-uid")
        self._append("evidence_freeze_intent", freeze)
        with self.assertRaisesRegex(JournalError, "pending|overlap|order"):
            self._append("driver_start_intent", {"namespace": "kil-v3-signed", "pod": "driver", "uid": "signed"})

    def test_pre_request_driver_recovery_proposes_freeze_and_never_invents_request(self) -> None:
        self._journal()
        self._ready()
        driver = self._start_driver("kil-v3-baseline", "driver-uid")
        plan = recovery_plan(load_journal(self.path), self._observation(
            driver_pods=(("kil-v3-baseline", "driver", "driver-uid"),)
        ))
        self.assertEqual(plan.requests_to_send, ())
        self.assertFalse(any(command.mutating for command in plan.commands))
        self.assertTrue(any("pod/driver" in command.argv for command in plan.commands))
        self.assertTrue(any("metadata.uid=driver-uid" in command.argv for command in plan.commands))
        self.assertIsNotNone(plan.next_intent)
        self.assertEqual(plan.next_intent[0], "evidence_freeze_intent")
        freeze = dict(plan.next_intent[1])
        self._append(plan.next_intent[0], freeze)
        pending = recovery_plan(load_journal(self.path), self._observation(
            driver_pods=(("kil-v3-baseline", "driver", "driver-uid"),)
        ))
        self.assertEqual(pending.requests_to_send, ())
        self.assertFalse(any(command.mutating for command in pending.commands))
        self._append("evidence_freeze_complete", freeze)
        proposal = recovery_plan(load_journal(self.path), self._observation(
            driver_pods=(("kil-v3-baseline", "driver", "driver-uid"),)
        ))
        self.assertEqual(proposal.next_intent[0], "driver_cancel_intent")
        self.assertEqual(dict(proposal.next_intent[1]), driver)
        self._append(proposal.next_intent[0], dict(proposal.next_intent[1]))
        authorized = recovery_plan(load_journal(self.path), self._observation(
            driver_pods=(("kil-v3-baseline", "driver", "driver-uid"),)
        ))
        self.assertTrue(any(command.mutating for command in authorized.commands))
        self._append("driver_cancel_complete", driver)
        cluster = {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig}
        profile = {"colima_profile": "kil-v3-lab"}
        tail = (
            ("cluster_delete_intent", cluster), ("cluster_delete_complete", cluster),
            ("cluster_absence_proof_intent", {"kind_cluster": "kil-v3-lab", "node_container_id": NODE_ID}),
            ("cluster_absence_proof_complete", {"kind_cluster": "kil-v3-lab", "node_container_id": NODE_ID}),
            ("profile_stop_intent", profile), ("profile_stop_complete", profile),
            ("profile_delete_intent", profile), ("profile_delete_complete", profile),
            ("profile_absence_proof_intent", profile), ("profile_absence_proof_complete", profile),
            ("foreign_snapshot_comparison_intent", {"unchanged": True, "attestation_sha256": "6" * 64}),
            ("foreign_snapshot_comparison_complete", {"unchanged": True, "attestation_sha256": "6" * 64}),
            ("publication_intent", {"public_commitment_sha256": "7" * 64}),
            ("publication_complete", {"public_commitment_sha256": "7" * 64}),
        )
        for name, details in tail:
            self._append(name, details)
        self.assertTrue(recovery_plan(load_journal(self.path)).publication_allowed)

    def test_pre_request_abandonment_freeze_is_available_at_each_track_boundary(self) -> None:
        tracks = (
            ("credential_policy_baseline", "kil-v3-baseline"),
            ("signed_state_only", "kil-v3-signed"),
            ("signed_plus_local_reduce", "kil-v3-local-reduce"),
        )
        for boundary in range(3):
            with self.subTest(boundary=boundary):
                self.path.unlink(missing_ok=True)
                self._journal()
                self._ready()
                observed: list[tuple[str, str, str]] = []
                for index, (track, namespace) in enumerate(tracks[: boundary + 1]):
                    uid = f"driver-uid-{index}"
                    self._start_driver(namespace, uid)
                    observed.append((namespace, "driver", uid))
                    if index < boundary:
                        request = {
                            "track": track,
                            "request_id": "v3b1-central-request",
                            "case_sha256": "f" * 64,
                        }
                        self._append("request_intent", request)
                        self._append("request_result", {**request, "result_sha256": "1" * 64})
                plan = recovery_plan(
                    load_journal(self.path), self._observation(driver_pods=tuple(sorted(observed)))
                )
                self.assertEqual(plan.requests_to_send, ())
                self.assertFalse(any(command.mutating for command in plan.commands))
                self.assertEqual(plan.next_intent[0], "evidence_freeze_intent")
                self._append(plan.next_intent[0], dict(plan.next_intent[1]))
                if boundary < 2:
                    next_namespace = tracks[boundary + 1][1]
                    with self.assertRaisesRegex(JournalError, "pending|overlap|order"):
                        self._append("driver_start_intent", {
                            "namespace": next_namespace,
                            "pod": "driver",
                            "uid": "late-driver",
                        })

    def test_stranded_request_freeze_allows_only_journaled_teardown_to_publication(self) -> None:
        self._journal()
        self._ready()
        driver = self._start_driver("kil-v3-baseline", "driver-uid")
        request = {
            "track": "credential_policy_baseline",
            "request_id": "v3b1-central-request",
            "case_sha256": "f" * 64,
        }
        self._append("request_intent", request)
        self._freeze()

        initial = recovery_plan(load_journal(self.path), self._observation(
            driver_pods=(("kil-v3-baseline", "driver", "driver-uid"),)
        ))
        self.assertFalse(any(command.mutating for command in initial.commands))
        self.assertEqual(initial.next_intent[0], "driver_cancel_intent")
        self.assertEqual(dict(initial.next_intent[1]), driver)

        self._append("driver_cancel_intent", driver)
        pending = recovery_plan(load_journal(self.path), self._observation(
            driver_pods=(("kil-v3-baseline", "driver", "driver-uid"),)
        ))
        deletion = next(command for command in pending.commands if command.mutating)
        self.assertIn("--raw", deletion.argv)
        self.assertIn(b'"uid":"driver-uid"', deletion.stdin or b"")
        self._append("driver_cancel_complete", driver)

        cluster = {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig}
        profile = {"colima_profile": "kil-v3-lab"}
        tail = (
            ("cluster_delete_intent", cluster), ("cluster_delete_complete", cluster),
            ("cluster_absence_proof_intent", {"kind_cluster": "kil-v3-lab", "node_container_id": NODE_ID}),
            ("cluster_absence_proof_complete", {"kind_cluster": "kil-v3-lab", "node_container_id": NODE_ID}),
            ("profile_stop_intent", profile), ("profile_stop_complete", profile),
            ("profile_delete_intent", profile), ("profile_delete_complete", profile),
            ("profile_absence_proof_intent", profile), ("profile_absence_proof_complete", profile),
            ("foreign_snapshot_comparison_intent", {"unchanged": True, "attestation_sha256": "6" * 64}),
            ("foreign_snapshot_comparison_complete", {"unchanged": True, "attestation_sha256": "6" * 64}),
            ("publication_intent", {"public_commitment_sha256": "7" * 64}),
            ("publication_complete", {"public_commitment_sha256": "7" * 64}),
        )
        for name, details in tail:
            self._append(name, details)
        self.assertTrue(recovery_plan(load_journal(self.path)).publication_allowed)

    def test_three_driver_stranded_recovery_preserves_track_order_through_publication(self) -> None:
        self._journal()
        self._ready()
        drivers: list[dict[str, object]] = []
        tracks = (
            ("credential_policy_baseline", "kil-v3-baseline"),
            ("signed_state_only", "kil-v3-signed"),
            ("signed_plus_local_reduce", "kil-v3-local-reduce"),
        )
        for index, (track, namespace) in enumerate(tracks):
            driver = self._start_driver(namespace, f"driver-uid-{index}")
            drivers.append(driver)
            request = {
                "track": track,
                "request_id": "v3b1-central-request",
                "case_sha256": "f" * 64,
            }
            self._append("request_intent", request)
            if index < 2:
                self._append("request_result", {**request, "result_sha256": "1" * 64})
        self._freeze()

        active = [
            (str(driver["namespace"]), str(driver["pod"]), str(driver["uid"]))
            for driver in drivers
        ]
        proposed_cancels: list[str] = []
        while active:
            observation = self._observation(driver_pods=tuple(sorted(active)))
            proposal = recovery_plan(load_journal(self.path), observation)
            self.assertFalse(any(command.mutating for command in proposal.commands))
            self.assertIsNotNone(proposal.next_intent)
            event, detail_pairs = proposal.next_intent
            self.assertEqual(event, "driver_cancel_intent")
            details = dict(detail_pairs)
            proposed_cancels.append(str(details["namespace"]))
            self._append(event, details)
            deletion = recovery_plan(load_journal(self.path), observation)
            command = next(command for command in deletion.commands if command.mutating)
            self.assertIn(str(details["uid"]).encode("utf-8"), command.stdin or b"")
            self._append("driver_cancel_complete", details)
            active.remove((str(details["namespace"]), str(details["pod"]), str(details["uid"])))
        self.assertEqual(
            proposed_cancels,
            ["kil-v3-baseline", "kil-v3-signed", "kil-v3-local-reduce"],
        )

        cluster_observation = self._observation(driver_pods=())
        plan = recovery_plan(load_journal(self.path), cluster_observation)
        self.assertEqual(plan.next_intent[0], "cluster_delete_intent")
        self._append(plan.next_intent[0], dict(plan.next_intent[1]))
        self.assertTrue(any(command.mutating for command in recovery_plan(
            load_journal(self.path), cluster_observation
        ).commands))
        cluster = {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig}
        self._append("cluster_delete_complete", cluster)

        absent_cluster = self._observation(
            kind_cluster=None,
            cluster_incarnation_uid=None,
            node_container_id=None,
            driver_pods=(),
        )
        plan = recovery_plan(load_journal(self.path), absent_cluster)
        self.assertEqual(plan.next_intent[0], "cluster_absence_proof_intent")
        self._append(plan.next_intent[0], dict(plan.next_intent[1]))
        self._append("cluster_absence_proof_complete", dict(plan.next_intent[1]))

        for family in ("profile_stop", "profile_delete"):
            plan = recovery_plan(load_journal(self.path), absent_cluster)
            self.assertEqual(plan.next_intent[0], f"{family}_intent")
            details = dict(plan.next_intent[1])
            self._append(plan.next_intent[0], details)
            self.assertTrue(any(command.mutating for command in recovery_plan(
                load_journal(self.path), absent_cluster
            ).commands))
            self._append(f"{family}_complete", details)

        absent_profile = self._observation(
            colima_profile=None,
            kind_cluster=None,
            cluster_incarnation_uid=None,
            node_container_id=None,
            driver_pods=(),
        )
        plan = recovery_plan(load_journal(self.path), absent_profile)
        self.assertEqual(plan.next_intent[0], "profile_absence_proof_intent")
        self._append(plan.next_intent[0], dict(plan.next_intent[1]))
        self._append("profile_absence_proof_complete", dict(plan.next_intent[1]))
        comparison = {"unchanged": True, "attestation_sha256": "6" * 64}
        publication = {"public_commitment_sha256": "7" * 64}
        for family, details in (("foreign_snapshot_comparison", comparison), ("publication", publication)):
            self._append(f"{family}_intent", details)
            self._append(f"{family}_complete", details)
        self.assertTrue(recovery_plan(load_journal(self.path), absent_profile).publication_allowed)

    def test_all_required_event_families_accept_exact_intent_completion_pairs(self) -> None:
        self._journal()
        for name, details in self._canonical_events():
            self._append(name, details)
        self.assertTrue(recovery_plan(load_journal(self.path)).publication_allowed)

    def test_failed_foreign_comparison_never_authorizes_promotable_publication(self) -> None:
        self._journal()
        events = self._canonical_events()
        for name, details in events:
            if name.startswith("foreign_snapshot_comparison_"):
                details = {**details, "unchanged": False}
            if name == "publication_intent":
                break
            self._append(name, details)
        failed = load_journal(self.path)
        self.assertFalse(recovery_plan(failed).publication_allowed)
        with self.assertRaisesRegex(JournalError, "unchanged|publication|order"):
            self._append("publication_intent", {"public_commitment_sha256": "7" * 64})

        mutated = load_journal(self.path)
        mutated["events"].extend([
            {
                "sequence": len(mutated["events"]) + 1,
                "event": "publication_intent",
                "details": {"public_commitment_sha256": "7" * 64},
            },
            {
                "sequence": len(mutated["events"]) + 2,
                "event": "publication_complete",
                "details": {"public_commitment_sha256": "7" * 64},
            },
        ])
        mutated["phase"] = "publication_complete"
        self.path.write_text(json.dumps(mutated, sort_keys=True, separators=(",", ":")) + "\n")
        os.chmod(self.path, 0o600)
        with self.assertRaisesRegex(JournalError, "unchanged|publication|order"):
            load_journal(self.path)

    def test_every_crash_boundary_recovers_only_the_pending_exact_mutation(self) -> None:
        events = self._canonical_events()
        intent_indices = [index for index, (name, _details) in enumerate(events) if name.endswith("_intent")]
        self.assertEqual(len(intent_indices), 16)
        expected_probe = {
            "profile_start_intent": "status",
            "cluster_create_intent": "inspect",
            "calico_apply_intent": "kube-system",
            "application_apply_intent": "networkpolicies",
            "readiness_intent": "pods",
            "driver_start_intent": "metadata.uid=driver-uid",
            "request_intent": "deployment/authz",
            "evidence_freeze_intent": "deployment/authz",
            "driver_cancel_intent": "metadata.uid=driver-uid",
            "cluster_delete_intent": "inspect",
            "cluster_absence_proof_intent": "inspect",
            "profile_stop_intent": "status",
            "profile_delete_intent": "status",
            "profile_absence_proof_intent": "status",
            "foreign_snapshot_comparison_intent": "list",
        }
        for intent_index in intent_indices:
            name = events[intent_index][0]
            with self.subTest(event=name):
                self.path.unlink(missing_ok=True)
                self._journal()
                for prefix_name, prefix_details in events[: intent_index + 1]:
                    self._append(prefix_name, prefix_details)
                pending = recovery_plan(load_journal(self.path))
                self.assertEqual(pending.requests_to_send, ())
                self.assertFalse(any(command.mutating for command in pending.commands))
                pending_text = " ".join(argument for command in pending.commands for argument in command.argv)
                if name in expected_probe:
                    self.assertIn(expected_probe[name], pending_text)
                else:
                    self.assertEqual(name, "publication_intent")
                    self.assertEqual(pending.commands, ())
                completion_name, completion_details = events[intent_index + 1]
                self._append(completion_name, completion_details)
                completed = recovery_plan(load_journal(self.path))
                self.assertEqual(completed.requests_to_send, ())

    def test_post_request_recovery_cancels_unfinished_driver_and_never_sends(self) -> None:
        self._journal()
        self._ready()
        driver = {"namespace": "kil-v3-baseline", "pod": "driver", "uid": "driver-uid"}
        self._append("driver_start_intent", driver)
        self._append("driver_start_complete", driver)
        request = {"track": "credential_policy_baseline", "request_id": "v3b1-central-request", "case_sha256": "f" * 64}
        value = self._append("request_intent", request)
        plan = recovery_plan(value)
        self.assertEqual(plan.requests_to_send, ())
        self.assertFalse(any("delete" in command.argv for command in plan.commands))
        self.assertTrue(
            any(
                command.argv[:3] == ("kubectl", "--kubeconfig", self.kubeconfig)
                and "get" in command.argv
                and "--all-namespaces" in command.argv
                for command in plan.commands
            )
        )
        self.assertFalse(any(command.stdin is not None for command in plan.commands))
        self.assertFalse(plan.publication_allowed)
        self._freeze()
        frozen = recovery_plan(load_journal(self.path))
        self.assertFalse(any(command.mutating for command in frozen.commands))
        observed = self._observation(driver_pods=(("kil-v3-baseline", "driver", "driver-uid"),))
        gated = recovery_plan(load_journal(self.path), observed)
        self.assertFalse(any(command.mutating for command in gated.commands))
        self._append("driver_cancel_intent", dict(gated.next_intent[1]))
        authorized = recovery_plan(load_journal(self.path), observed)
        deletion = next(command for command in authorized.commands if "delete" in command.argv)
        self.assertIn("--raw", deletion.argv)
        self.assertIn("/api/v1/namespaces/kil-v3-baseline/pods/driver", deletion.argv)
        self.assertEqual(
            deletion.stdin,
            b'{"apiVersion":"v1","kind":"DeleteOptions","preconditions":{"uid":"driver-uid"}}\n',
        )
        self.assertNotIn("metadata.uid=driver-uid", " ".join(deletion.argv))

    def test_foreign_profiles_never_appear_in_mutation_commands(self) -> None:
        journal = self._journal()
        plan = recovery_plan(journal)
        mutation_text = "\n".join(" ".join(command.argv) for command in plan.commands)
        self.assertNotIn("client-project", mutation_text)

    def test_identity_or_endpoint_mismatch_requires_manual_recovery_and_never_deletes(self) -> None:
        self._journal()
        self._cluster_created()
        valid = load_journal(self.path)
        mutations = (
            ("cluster_incarnation_uid", "foreign-uid"),
            ("node_container_id", "9" * 64),
            ("docker_host", "unix:///foreign/docker.sock"),
            ("colima_profile", "foreign"),
        )
        for field, replacement in mutations:
            changes = {field: replacement}
            with self.subTest(field=field), self.assertRaisesRegex(JournalError, "manual_recovery_required"):
                recovery_plan(valid, self._observation(**changes))

    def test_noncreation_event_authority_mismatch_also_requires_manual_recovery(self) -> None:
        self._journal()
        self._cluster_created()
        mismatched = load_journal(self.path)
        with self.assertRaisesRegex(JournalError, "manual_recovery_required"):
            recovery_plan(mismatched, self._observation(docker_host="unix:///foreign/docker.sock"))

    def test_loaded_nested_mutation_cannot_bypass_revalidation(self) -> None:
        journal = self._journal()
        journal["owned_identity"]["colima_profile"] = "foreign"
        with self.assertRaises(JournalError):
            recovery_plan(journal)


if __name__ == "__main__":
    unittest.main()
