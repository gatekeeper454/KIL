from __future__ import annotations

from pathlib import Path
import unittest

from tests import test_v3b2_controller as controller_tests


DEFERRED_METHODS = frozenset({
    "test_down_resumes_bound_runtime_without_current_context_or_discovery_selected_delete",
    "test_driver_eof_cancel_requires_retained_terminal_exit_zero",
    "test_envoy_quiesce_rejects_container_incarnation_change",
    "test_every_request_free_completion_persistence_boundary_recovers_without_request",
    "test_import_uses_preflight_verified_archive_bytes_not_reopened_path",
    "test_nominal_persists_intent_before_each_single_attach",
    "test_post_intent_failure_cancels_later_drivers_and_never_retries",
    "test_recover_attests_successful_cluster_create_without_replaying_create",
    "test_recover_attests_successful_profile_start_without_replaying_mutation",
    "test_recover_driver_cancel_completion_crash_attests_terminal_without_replaying_eof",
    "test_request_free_rejects_any_application_record_but_still_tears_down",
    "test_request_free_sends_no_attach_stdin_or_application_records",
    "test_request_result_persistence_failure_recovers_by_freezing_never_replay",
    "test_separate_process_can_continue_a_preflight_only_journal_into_request_free",
    "test_uncertain_command_failures_enter_exact_cleanup_without_forward_progress",
    "test_up_uses_only_owned_profile_cluster_and_applies_policy_before_workloads",
})


class V4FutureControllerGateTest(unittest.TestCase):
    def test_default_gate_defers_exact_unfinished_lifecycle_set(self) -> None:
        case = controller_tests.V3B2ControllerTest
        deferred = frozenset(
            name for name in dir(case)
            if name.startswith("test_") and getattr(getattr(case, name), "__unittest_skip__", False)
        )
        self.assertEqual(deferred, DEFERRED_METHODS)
        self.assertFalse(getattr(
            case.test_preflight_rejects_tool_byte_drift_before_any_mutation,
            "__unittest_skip__",
            False,
        ))

    def test_makefile_exposes_the_explicit_v4_future_target(self) -> None:
        makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text()
        self.assertIn("v4-future-controller-test: check-python", makefile)
        self.assertIn("KIL_RUN_V4_FUTURE_TESTS=1", makefile)
        self.assertIn(
            "tests.test_v3b2_controller.V3B2ControllerTest -v",
            makefile,
        )


if __name__ == "__main__":
    unittest.main()
