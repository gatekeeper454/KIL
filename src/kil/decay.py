"""Deterministic arithmetic for the KIL trust-decay reference kernel."""

from decimal import Decimal, localcontext
from typing import Mapping


ZERO = Decimal("0")
ONE = Decimal("1")


def weighted_diagonal_distance(
    features: Mapping[str, Decimal],
    means: Mapping[str, Decimal],
    scales: Mapping[str, Decimal],
    weights: Mapping[str, Decimal],
) -> Decimal:
    """Return a weighted standardized distance over matching feature keys."""
    keys = set(features)
    if set(means) != keys or set(scales) != keys or set(weights) != keys:
        raise ValueError("feature, mean, scale, and weight key sets must match")

    with localcontext() as context:
        context.prec = 28
        squared_distance = ZERO
        for key in sorted(keys):
            scale = scales[key]
            weight = weights[key]
            if scale <= ZERO:
                raise ValueError(f"scale for {key!r} must be greater than zero")
            if weight < ZERO:
                raise ValueError(f"weight for {key!r} must be nonnegative")
            standardized = (features[key] - means[key]) / scale
            squared_distance += weight * standardized * standardized
        return squared_distance.sqrt()


def logistic_squash(raw: Decimal, k: Decimal) -> Decimal:
    """Map a nonnegative raw distance into the half-open interval [0, 1)."""
    if raw < ZERO:
        raise ValueError("raw must be nonnegative")
    if k <= ZERO:
        raise ValueError("k must be greater than zero")

    with localcontext() as context:
        context.prec = 28
        return Decimal("2") / (ONE + (-k * raw).exp()) - ONE


def passive_decay(
    charge: Decimal, decay_rate: Decimal, elapsed: Decimal
) -> Decimal:
    """Apply exponential passive decay to a nonnegative charge."""
    if charge < ZERO:
        raise ValueError("charge must be nonnegative")
    if decay_rate < ZERO:
        raise ValueError("decay_rate must be nonnegative")
    if elapsed < ZERO:
        raise ValueError("elapsed must be nonnegative")

    with localcontext() as context:
        context.prec = 28
        return charge * (-decay_rate * elapsed).exp()


def superlinear_loss(
    divergence: Decimal,
    threshold: Decimal,
    loss_rate: Decimal,
    exponent: Decimal,
) -> Decimal:
    """Return zero in-band and a superlinear penalty above the threshold."""
    if divergence < ZERO or divergence > ONE:
        raise ValueError("divergence must be between zero and one")
    if threshold <= ZERO:
        raise ValueError("threshold must be greater than zero")
    if loss_rate < ZERO:
        raise ValueError("loss_rate must be nonnegative")
    if exponent <= ONE:
        raise ValueError("exponent must be greater than one")
    if divergence <= threshold:
        return ZERO

    with localcontext() as context:
        context.prec = 28
        return loss_rate * (divergence / threshold) ** exponent


def local_effective_charge(
    decayed_charge: Decimal,
    loss: Decimal,
    coupled_loss: Decimal,
    maximum: Decimal,
) -> Decimal:
    """Apply reducing-only local losses and clamp the result to its bounds."""
    values = {
        "decayed_charge": decayed_charge,
        "loss": loss,
        "coupled_loss": coupled_loss,
        "maximum": maximum,
    }
    for name, value in values.items():
        if value < ZERO:
            raise ValueError(f"{name} must be nonnegative")

    reduced = max(ZERO, decayed_charge - loss - coupled_loss)
    return min(maximum, reduced)
