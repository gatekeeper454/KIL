from dataclasses import FrozenInstanceError
from decimal import Decimal
import unittest

from kil.evidence import EvidenceClass, LabeledValue


class EvidenceContractTest(unittest.TestCase):
    def test_observed_requires_source_reference(self):
        with self.assertRaisesRegex(ValueError, "source_ref"):
            LabeledValue(Decimal("1"), EvidenceClass.OBSERVED)

    def test_modeled_requires_rationale(self):
        with self.assertRaisesRegex(ValueError, "rationale"):
            LabeledValue(Decimal("0.9"), EvidenceClass.MODELED)

    def test_validated_requires_run_id(self):
        with self.assertRaisesRegex(ValueError, "run_id"):
            LabeledValue(Decimal("0"), EvidenceClass.VALIDATED)

    def test_labeled_values_are_immutable(self):
        value = LabeledValue(
            Decimal("0.9"),
            EvidenceClass.MODELED,
            rationale="synthetic origin-distance feature",
        )

        with self.assertRaises(FrozenInstanceError):
            value.value = Decimal("1")


if __name__ == "__main__":
    unittest.main()
