from dataclasses import replace
from decimal import Decimal
import unittest

from kil.q_state import QStateClaims


def claims(**changes):
    value = QStateClaims(
        schema_version="kil.q-state.v0",
        state_id="q-v3a-1",
        issuer="https://lab-issuer.kil.invalid",
        subject="spiffe://kil.local/workload/demo",
        audience="kil-v3-signed",
        authority_class="admin_action",
        action_class="consequential_admin",
        issued_at_s=100,
        not_before_s=100,
        expires_at_s=110,
        evidence_horizon_s=99,
        trust_proof_id="tp-v3a-1",
        trust_proof_digest="sha256:" + "a" * 64,
        envelope_result_id="ke-v3a-1",
        envelope_result_digest="sha256:" + "b" * 64,
        deployment_profile="kil-lab-v3@0",
        charge=Decimal("80"),
        threshold=Decimal("40"),
        history_count=5,
        minimum_history=2,
        veto_clear=True,
        envelope_allows=True,
        decay_rate=Decimal("0"),
        maximum_charge=Decimal("100"),
        model_version="kil-decay-v1",
        parameter_version="kil-v3a-fixture-v1",
    )
    return replace(value, **changes)


class QStateClaimsTest(unittest.TestCase):
    def test_round_trips_the_exact_payload(self):
        original = claims()
        self.assertEqual(QStateClaims.from_payload(original.to_payload()), original)

    def test_rejects_more_than_ten_seconds_of_validity(self):
        with self.assertRaisesRegex(ValueError, "ten seconds"):
            claims(expires_at_s=111)

    def test_rejects_unknown_payload_fields(self):
        payload = claims().to_payload()
        payload["mode"] = "signed_state_only"
        with self.assertRaisesRegex(ValueError, "unknown"):
            QStateClaims.from_payload(payload)

    def test_converts_only_claimed_authority_to_v1_state(self):
        state = claims().to_composite_state()
        self.assertEqual(state.identity, "spiffe://kil.local/workload/demo")
        self.assertEqual(state.authority_class, "admin_action")
        self.assertTrue(state.authentic)


if __name__ == "__main__":
    unittest.main()
