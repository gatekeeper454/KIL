"""Experimental signed composite-state profile for KIL live validation."""

from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from .domain import CompositeState


Q_STATE_SCHEMA_VERSION = "kil.q-state.v0"
MAX_VALIDITY_SECONDS = 10
_DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
_DECIMAL_FIELDS = frozenset(
    {"charge", "threshold", "decay_rate", "maximum_charge"}
)


def _require_nonblank(name: str, value: object) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")
    return value


def _require_integer(name: str, value: object) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def _require_boolean(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean")
    return value


def _require_decimal(name: str, value: object) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


@dataclass(frozen=True, slots=True)
class QStateClaims:
    """Strict payload claims for the experimental ``kil.q-state.v0`` profile."""

    schema_version: str
    state_id: str
    issuer: str
    subject: str
    audience: str
    authority_class: str
    action_class: str
    issued_at_s: int
    not_before_s: int
    expires_at_s: int
    evidence_horizon_s: int
    trust_proof_id: str
    trust_proof_digest: str
    envelope_result_id: str
    envelope_result_digest: str
    deployment_profile: str
    charge: Decimal
    threshold: Decimal
    history_count: int
    minimum_history: int
    veto_clear: bool
    envelope_allows: bool
    decay_rate: Decimal
    maximum_charge: Decimal
    model_version: str
    parameter_version: str

    def __post_init__(self) -> None:
        if self.schema_version != Q_STATE_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {Q_STATE_SCHEMA_VERSION}"
            )
        for name in (
            "state_id",
            "issuer",
            "subject",
            "audience",
            "authority_class",
            "action_class",
            "trust_proof_id",
            "envelope_result_id",
            "deployment_profile",
            "model_version",
            "parameter_version",
        ):
            _require_nonblank(name, getattr(self, name))
        for name in (
            "issued_at_s",
            "not_before_s",
            "expires_at_s",
            "evidence_horizon_s",
            "history_count",
            "minimum_history",
        ):
            _require_integer(name, getattr(self, name))
        for name in ("veto_clear", "envelope_allows"):
            _require_boolean(name, getattr(self, name))
        for name in _DECIMAL_FIELDS:
            _require_decimal(name, getattr(self, name))
        for name in ("trust_proof_digest", "envelope_result_digest"):
            value = getattr(self, name)
            if type(value) is not str or _DIGEST_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{name} must be a sha256 digest")

        if not self.issued_at_s <= self.not_before_s < self.expires_at_s:
            raise ValueError("invalid state validity window")
        if self.expires_at_s - self.issued_at_s > MAX_VALIDITY_SECONDS:
            raise ValueError("state validity cannot exceed ten seconds")
        if self.evidence_horizon_s > self.issued_at_s:
            raise ValueError("evidence_horizon_s cannot be later than issuance")
        if self.history_count < 0 or self.minimum_history < 0:
            raise ValueError("history counts must be nonnegative")
        if self.charge > self.maximum_charge:
            raise ValueError("charge exceeds maximum_charge")
        if self.threshold > self.maximum_charge:
            raise ValueError("threshold exceeds maximum_charge")

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            payload[item.name] = str(value) if item.name in _DECIMAL_FIELDS else value
        return payload

    @classmethod
    def from_payload(cls, payload: object) -> "QStateClaims":
        if type(payload) is not dict:
            raise ValueError("q-state payload must be an object")
        expected = {item.name for item in fields(cls)}
        actual = set(payload)
        unknown = actual - expected
        missing = expected - actual
        if unknown:
            raise ValueError(f"unknown q-state payload fields: {sorted(unknown)}")
        if missing:
            raise ValueError(f"missing q-state payload fields: {sorted(missing)}")

        values: dict[str, Any] = dict(payload)
        for name in _DECIMAL_FIELDS:
            raw = values[name]
            if type(raw) is not str or not raw:
                raise ValueError(f"{name} must be a decimal string")
            try:
                values[name] = Decimal(raw)
            except InvalidOperation as error:
                raise ValueError(f"{name} must be a decimal string") from error
        return cls(**values)

    def to_composite_state(self) -> CompositeState:
        return CompositeState(
            state_id=self.state_id,
            identity=self.subject,
            authority_class=self.authority_class,
            issued_at_s=self.issued_at_s,
            not_before_s=self.not_before_s,
            expires_at_s=self.expires_at_s,
            charge=self.charge,
            threshold=self.threshold,
            history_count=self.history_count,
            minimum_history=self.minimum_history,
            authentic=True,
            veto_clear=self.veto_clear,
            envelope_allows=self.envelope_allows,
            decay_rate=self.decay_rate,
            maximum_charge=self.maximum_charge,
        )
