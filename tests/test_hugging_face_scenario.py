from decimal import Decimal
from pathlib import Path
import unittest

from kil.evidence import EvidenceClass
from kil.scenario import load_scenario


SCENARIO = (
    Path(__file__).resolve().parents[1]
    / "scenarios/hugging-face-july-2026/scenario-v1.json"
)
SOURCE = "https://huggingface.co/blog/agent-intrusion-technical-timeline"
CONTROL_RATIONALE = (
    "Modeled credential-policy baseline for the consequential action; the public "
    "timeline reports that the action occurred but does not provide a complete "
    "policy-engine decision record."
)
STATE_RATIONALE = (
    "Synthetic `Q_i,c` state for counterfactual evaluation; the public timeline "
    "contains no KTP enforcement state."
)
EXPECTED_EVENTS = (
    ("hf-p1-cluster-api", 1, "admin_action", ()),
    ("hf-p2-external-replay", 2, "network_egress_external", ("hf-p1-cluster-api",)),
    ("hf-p3-privileged-workload", 3, "privilege_escalation", ("hf-p1-cluster-api",)),
    ("hf-p4-secret-read", 4, "read_other_resource", ("hf-p3-privileged-workload",)),
    ("hf-p5-cross-cluster-admin", 5, "admin_action", ("hf-p4-secret-read",)),
    ("hf-p6-mesh-enrollment", 6, "network_egress_external", ("hf-p4-secret-read",)),
    ("hf-p7-forged-token", 7, "mint_token", ("hf-p4-secret-read",)),
    (
        "hf-p8-ci-pivot",
        8,
        "admin_action",
        ("hf-p6-mesh-enrollment", "hf-p7-forged-token"),
    ),
)
EXPECTED_SUMMARIES = (
    "The compromised worker used its service-account context and addressed Kubernetes control-plane endpoints.",
    "Cloud-derived credentials were used from external infrastructure for estate enumeration.",
    "A privileged, host-mounted workload enabled node-level control and persistence.",
    "Cluster secret objects, including a high-value multi-key object, were accessed.",
    "A shared connector credential enabled broad administrative use across clusters.",
    "A stolen mesh credential was used for repeated device enrollment.",
    "Stolen signing capability enabled correctly signed identity tokens.",
    "An installation token supported a source-control and CI-directed pivot attempt.",
)
EXPECTED_PROFILE = (
    (10, "5", "40", 0, 2, "0.95", "0"),
    (20, "10", "35", 0, 2, "0.98", "0"),
    (30, "0", "70", 0, 5, "1.0", "0"),
    (40, "40", "50", 1, 3, "0.90", "20"),
    (50, "0", "80", 0, 5, "1.0", "0"),
    (60, "15", "40", 0, 2, "0.95", "0"),
    (70, "0", "60", 0, 3, "1.0", "0"),
    (80, "10", "60", 0, 3, "0.90", "0"),
)


class HuggingFaceScenarioTest(unittest.TestCase):
    def test_scenario_covers_the_eight_counterfactual_cut_points(self):
        scenario = load_scenario(SCENARIO)
        observed = tuple(
            (event.event_id, event.phase, event.request.authority_class, event.depends_on)
            for event in scenario.events
        )
        self.assertEqual(observed, EXPECTED_EVENTS)

    def test_observed_and_modeled_fields_remain_distinct(self):
        scenario = load_scenario(SCENARIO)
        for event in scenario.events:
            self.assertEqual(
                event.observed_summary.evidence_class, EvidenceClass.OBSERVED
            )
            self.assertTrue(event.observed_summary.source_ref.startswith(SOURCE))
            self.assertEqual(
                event.control_assumption.evidence_class, EvidenceClass.MODELED
            )
            self.assertEqual(
                event.state_assumption.evidence_class, EvidenceClass.MODELED
            )
            self.assertEqual(
                event.local_evidence_assumption.evidence_class,
                EvidenceClass.MODELED,
            )
            self.assertEqual(event.control_assumption.rationale, CONTROL_RATIONALE)
            self.assertEqual(event.state_assumption.rationale, STATE_RATIONALE)
            self.assertTrue(event.local_evidence_assumption.rationale)

    def test_observed_summaries_match_the_paper_phase_map(self):
        scenario = load_scenario(SCENARIO)
        self.assertEqual(
            tuple(event.observed_summary.value for event in scenario.events),
            EXPECTED_SUMMARIES,
        )

    def test_first_modeled_profile_matches_the_declared_tables(self):
        scenario = load_scenario(SCENARIO)
        actual = []
        for event in scenario.events:
            state = event.state_assumption.value
            local = event.local_evidence_assumption.value
            actual.append(
                (
                    event.request.timestamp_s,
                    str(state.charge),
                    str(state.threshold),
                    state.history_count,
                    state.minimum_history,
                    str(local.divergence),
                    str(local.coupled_loss),
                )
            )
            self.assertEqual((state.issued_at_s, state.not_before_s), (0, 0))
            self.assertEqual(state.expires_at_s, 600)
            self.assertTrue(state.authentic and state.veto_clear and state.envelope_allows)
            self.assertEqual(state.decay_rate, Decimal("0.01"))
            self.assertEqual(state.maximum_charge, Decimal("100"))
            self.assertEqual(event.control_assumption.value, (True, True))
        self.assertEqual(tuple(actual), EXPECTED_PROFILE)


if __name__ == "__main__":
    unittest.main()
