"""Evidence labels that keep claims inside their evidentiary boundary."""

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar


class EvidenceClass(str, Enum):
    """The provenance class attached to a value used by KIL."""

    OBSERVED = "observed"
    MODELED = "modeled"
    VALIDATED = "validated"


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class LabeledValue(Generic[T]):
    """A value whose evidence class carries the required provenance metadata."""

    value: T
    evidence_class: EvidenceClass
    source_ref: str | None = None
    rationale: str | None = None
    run_id: str | None = None

    def __post_init__(self) -> None:
        if self.evidence_class is EvidenceClass.OBSERVED and not self.source_ref:
            raise ValueError("observed evidence requires source_ref")
        if self.evidence_class is EvidenceClass.MODELED and not self.rationale:
            raise ValueError("modeled evidence requires rationale")
        if self.evidence_class is EvidenceClass.VALIDATED and not self.run_id:
            raise ValueError("validated evidence requires run_id")
