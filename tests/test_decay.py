from decimal import Decimal
import unittest

from kil.decay import (
    local_effective_charge,
    logistic_squash,
    passive_decay,
    superlinear_loss,
    weighted_diagonal_distance,
)


class TrustDecayArithmeticTest(unittest.TestCase):
    def test_identical_feature_vectors_have_zero_distance(self):
        distance = weighted_diagonal_distance(
            features={"velocity": Decimal("2"), "volume": Decimal("10")},
            means={"velocity": Decimal("2"), "volume": Decimal("10")},
            scales={"velocity": Decimal("1"), "volume": Decimal("2")},
            weights={"velocity": Decimal("0.75"), "volume": Decimal("0.25")},
        )

        self.assertEqual(distance, Decimal("0"))

    def test_weighted_distance_rejects_zero_scale(self):
        with self.assertRaisesRegex(ValueError, "scale"):
            weighted_diagonal_distance(
                features={"velocity": Decimal("2")},
                means={"velocity": Decimal("1")},
                scales={"velocity": Decimal("0")},
                weights={"velocity": Decimal("1")},
            )

    def test_logistic_squash_maps_zero_to_zero_and_positive_below_one(self):
        self.assertEqual(logistic_squash(Decimal("0"), Decimal("1")), Decimal("0"))
        positive = logistic_squash(Decimal("2"), Decimal("1"))
        self.assertGreater(positive, Decimal("0"))
        self.assertLess(positive, Decimal("1"))

    def test_passive_decay_lowers_positive_charge_without_going_negative(self):
        decayed = passive_decay(
            charge=Decimal("80"),
            decay_rate=Decimal("0.1"),
            elapsed=Decimal("5"),
        )

        self.assertGreaterEqual(decayed, Decimal("0"))
        self.assertLess(decayed, Decimal("80"))

    def test_superlinear_loss_is_zero_in_band_and_cubic_outside(self):
        threshold = Decimal("0.25")
        loss_rate = Decimal("25")
        exponent = Decimal("3")

        self.assertEqual(
            superlinear_loss(threshold, threshold, loss_rate, exponent),
            Decimal("0"),
        )
        half_divergence_loss = superlinear_loss(
            Decimal("0.5"), threshold, loss_rate, exponent
        )
        full_divergence_loss = superlinear_loss(
            Decimal("1.0"), threshold, loss_rate, exponent
        )
        self.assertEqual(full_divergence_loss, Decimal("8") * half_divergence_loss)

    def test_local_effective_charge_clamps_to_zero_and_never_increases(self):
        depleted = local_effective_charge(
            decayed_charge=Decimal("10"),
            loss=Decimal("7"),
            coupled_loss=Decimal("5"),
            maximum=Decimal("100"),
        )
        capped = local_effective_charge(
            decayed_charge=Decimal("120"),
            loss=Decimal("0"),
            coupled_loss=Decimal("0"),
            maximum=Decimal("100"),
        )

        self.assertEqual(depleted, Decimal("0"))
        self.assertEqual(capped, Decimal("100"))
        self.assertLessEqual(capped, Decimal("120"))


if __name__ == "__main__":
    unittest.main()
