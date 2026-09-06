from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import tempfile
import unittest

from kil.v3b2_journal import (
    Command,
    JournalError,
    JournalInputs,
    OwnedIdentity,
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
        self.assertEqual(leftovers, ())

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
        self._append("driver_start_intent", {"namespace": "kil-v3-baseline", "pod": "driver", "uid": "driver-uid"})
        with self.assertRaisesRegex(JournalError, "match|exact intent"):
            self._append("driver_start_complete", {"namespace": "kil-v3-signed", "pod": "driver", "uid": "driver-uid"})

    def test_request_intent_is_terminal_and_never_replayed(self) -> None:
        self._journal()
        request = {"track": "credential_policy_baseline", "request_id": "v3b1-central-request", "case_sha256": "f" * 64}
        claimed = append_event(self.path, "request_intent", request)
        with self.assertRaisesRegex(JournalError, "already claimed"):
            append_event(self.path, "request_intent", request)
        self.assertEqual(recovery_plan(claimed).requests_to_send, ())

    def test_each_track_may_be_claimed_once_but_distinct_tracks_may_advance(self) -> None:
        self._journal()
        for track in ("credential_policy_baseline", "signed_state_only", "signed_plus_local_reduce"):
            details = {"track": track, "request_id": "v3b1-central-request", "case_sha256": "f" * 64}
            self._append("request_intent", details)
            self._append("request_result", {**details, "result_sha256": "1" * 64})

    def test_all_required_event_families_accept_exact_intent_completion_pairs(self) -> None:
        details_by_family: dict[str, tuple[dict[str, object], dict[str, object]]] = {
            "profile_start": {"colima_profile": "kil-v3-lab"},
            "profile_stop": {"colima_profile": "kil-v3-lab"},
            "profile_delete": {"colima_profile": "kil-v3-lab"},
            "cluster_create": (
                {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig},
                {
                    "kind_cluster": "kil-v3-lab",
                    "kubeconfig": self.kubeconfig,
                    "cluster_incarnation_uid": CLUSTER_UID,
                    "node_container_id": NODE_ID,
                    "docker_host": self.identity.docker_host,
                },
            ),
            "cluster_delete": {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig},
            "calico_apply": {"manifest_sha256": "2" * 64},
            "application_apply": {"manifest_sha256": "3" * 64},
            "readiness": {"attestation_sha256": "4" * 64},
            "driver_start": {"namespace": "kil-v3-baseline", "pod": "driver", "uid": "driver-uid"},
            "driver_cancel": {"namespace": "kil-v3-baseline", "pod": "driver", "uid": "driver-uid"},
            "evidence_freeze": {"evidence_sha256": "5" * 64},
            "cluster_absence_proof": {"kind_cluster": "kil-v3-lab", "node_container_id": NODE_ID},
            "profile_absence_proof": {"colima_profile": "kil-v3-lab"},
            "foreign_snapshot_comparison": {"unchanged": True, "attestation_sha256": "6" * 64},
            "publication": {"public_commitment_sha256": "7" * 64},
        }
        for family, value in details_by_family.items():
            with self.subTest(family=family):
                self.path.unlink(missing_ok=True)
                self._journal()
                intent, complete = value if isinstance(value, tuple) else (value, value)
                self._append(f"{family}_intent", intent)
                self._append(f"{family}_complete", complete)

    def test_every_crash_boundary_recovers_only_the_pending_exact_mutation(self) -> None:
        cases = (
            ("profile_start", {"colima_profile": "kil-v3-lab"}, None, "start"),
            ("profile_stop", {"colima_profile": "kil-v3-lab"}, None, "stop"),
            ("profile_delete", {"colima_profile": "kil-v3-lab"}, None, "delete"),
            (
                "cluster_create",
                {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig},
                {
                    "kind_cluster": "kil-v3-lab",
                    "kubeconfig": self.kubeconfig,
                    "cluster_incarnation_uid": CLUSTER_UID,
                    "node_container_id": NODE_ID,
                    "docker_host": self.identity.docker_host,
                },
                "create",
            ),
            ("cluster_delete", {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig}, None, "delete"),
            ("calico_apply", {"manifest_sha256": "2" * 64}, None, "get"),
            ("application_apply", {"manifest_sha256": "3" * 64}, None, "get"),
            ("driver_start", {"namespace": "kil-v3-baseline", "pod": "driver", "uid": "driver-uid"}, None, "get"),
            ("driver_cancel", {"namespace": "kil-v3-baseline", "pod": "driver", "uid": "driver-uid"}, None, "delete"),
        )
        for family, details, completion, operation in cases:
            with self.subTest(family=family):
                self.path.unlink(missing_ok=True)
                self._journal()
                before = recovery_plan(load_journal(self.path))
                self.assertEqual(before.commands[0].argv[:2], ("colima", "start"))
                pending = self._append(f"{family}_intent", details)
                plan = recovery_plan(pending)
                self.assertEqual(len(plan.commands), 1)
                self.assertEqual(plan.commands[0].argv[0], "colima" if family.startswith("profile_") else ("kind" if family.startswith("cluster_") else "kubectl"))
                self.assertIn(operation, plan.commands[0].argv)
                complete = self._append(f"{family}_complete", completion or details)
                completed_plan = recovery_plan(complete)
                self.assertNotEqual(completed_plan.commands, plan.commands)

    def test_post_request_recovery_cancels_unfinished_driver_and_never_sends(self) -> None:
        self._journal()
        driver = {"namespace": "kil-v3-baseline", "pod": "driver", "uid": "driver-uid"}
        self._append("driver_start_intent", driver)
        self._append("driver_start_complete", driver)
        request = {"track": "credential_policy_baseline", "request_id": "v3b1-central-request", "case_sha256": "f" * 64}
        value = self._append("request_intent", request)
        plan = recovery_plan(value)
        self.assertEqual(plan.requests_to_send, ())
        self.assertTrue(any(command.argv[:3] == ("kubectl", "--kubeconfig", self.kubeconfig) and "delete" in command.argv for command in plan.commands))
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

    def test_foreign_profiles_never_appear_in_mutation_commands(self) -> None:
        journal = self._journal()
        plan = recovery_plan(journal)
        mutation_text = "\n".join(" ".join(command.argv) for command in plan.commands)
        self.assertNotIn("client-project", mutation_text)

    def test_identity_or_endpoint_mismatch_requires_manual_recovery_and_never_deletes(self) -> None:
        self._journal()
        self._append("cluster_create_intent", {"kind_cluster": "kil-v3-lab", "kubeconfig": self.kubeconfig})
        valid = self._append(
            "cluster_create_complete",
            {
                "kind_cluster": "kil-v3-lab",
                "kubeconfig": self.kubeconfig,
                "cluster_incarnation_uid": CLUSTER_UID,
                "node_container_id": NODE_ID,
                "docker_host": self.identity.docker_host,
            },
        )
        mutations = (
            ("cluster_incarnation_uid", "foreign-uid"),
            ("node_container_id", "9" * 64),
            ("docker_host", "unix:///foreign/docker.sock"),
            ("kubeconfig", "/tmp/foreign-kubeconfig"),
        )
        event = valid["events"][1]
        assert isinstance(event, dict)
        details = event["details"]
        assert isinstance(details, dict)
        for field, replacement in mutations:
            changed = json.loads(json.dumps(valid))
            changed["events"][1]["details"][field] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(JournalError, "manual_recovery_required"):
                recovery_plan(changed)

    def test_noncreation_event_authority_mismatch_also_requires_manual_recovery(self) -> None:
        self._journal()
        mismatched = self._append(
            "cluster_delete_intent",
            {"kind_cluster": "kil-v3-lab", "kubeconfig": "/tmp/foreign-kubeconfig"},
        )
        with self.assertRaisesRegex(JournalError, "manual_recovery_required"):
            recovery_plan(mismatched)

    def test_loaded_nested_mutation_cannot_bypass_revalidation(self) -> None:
        journal = self._journal()
        journal["owned_identity"]["colima_profile"] = "foreign"
        with self.assertRaises(JournalError):
            recovery_plan(journal)


if __name__ == "__main__":
    unittest.main()
