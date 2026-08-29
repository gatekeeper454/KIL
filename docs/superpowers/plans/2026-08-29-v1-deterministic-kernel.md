# V1 Deterministic KIL Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate the dependency-free deterministic decision kernel for KIL's signed-state-only and signed-plus-local-reduction modes.

**Architecture:** The kernel separates evidence labels, deterministic decimal arithmetic, immutable domain records, and decision evaluation. It consumes an already authenticated composite-state result through an algorithm-neutral boundary; cryptographic encoding is a later KTP compatibility gate. The fast loop can reduce but never replenish authority.

**Tech Stack:** Python 3.12 standard library, frozen dataclasses, `Decimal`, `Enum`, canonical JSON, SHA-256, `unittest`.

---

### Task 0: Pin the supported local Python runtime

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Verify the bundled runtime**

Run: `'/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' --version`

Expected: Python 3.12.x. Stop if the reported version is below the project's
Python 3.11 minimum.

- [ ] **Step 2: Parameterize the Makefile**

Add `PYTHON ?= python3` above the targets. Replace both executable occurrences
of `python3` with `$(PYTHON)`:

```make
PYTHON ?= python3

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

validate: test
	$(PYTHON) -c "from pathlib import Path; assert '[project]' in Path('pyproject.toml').read_text()"
	git diff --check
```

- [ ] **Step 3: Verify the existing baseline through Python 3.12**

Run: `make validate PYTHON='/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'`

Expected: the existing 11 tests pass and `git diff --check` reports no errors.

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "Parameterize the KIL Python runtime"
```

### Task 1: Evidence classification contract

**Files:**
- Create: `src/kil/evidence.py`
- Create: `tests/test_evidence.py`

- [ ] **Step 1: Write the failing tests**

```python
from decimal import Decimal
import unittest

from kil.evidence import EvidenceClass, LabeledValue


class EvidenceTest(unittest.TestCase):
    def test_observed_requires_source_reference(self):
        with self.assertRaisesRegex(ValueError, "source_ref"):
            LabeledValue(Decimal("1"), EvidenceClass.OBSERVED)

    def test_modeled_requires_rationale(self):
        with self.assertRaisesRegex(ValueError, "rationale"):
            LabeledValue(Decimal("0.9"), EvidenceClass.MODELED)

    def test_validated_requires_run_id(self):
        with self.assertRaisesRegex(ValueError, "run_id"):
            LabeledValue(Decimal("0"), EvidenceClass.VALIDATED)

    def test_complete_labels_are_immutable(self):
        value = LabeledValue(
            Decimal("0.9"),
            EvidenceClass.MODELED,
            rationale="synthetic origin-distance feature",
        )
        with self.assertRaises(Exception):
            value.value = Decimal("0")
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_evidence -v`

Expected: import failure because `kil.evidence` does not exist.

- [ ] **Step 3: Implement the evidence types**

```python
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar


T = TypeVar("T")


class EvidenceClass(str, Enum):
    OBSERVED = "observed"
    MODELED = "modeled"
    VALIDATED = "validated"


@dataclass(frozen=True, slots=True)
class LabeledValue(Generic[T]):
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
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_evidence -v`

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/kil/evidence.py tests/test_evidence.py
git commit -m "Add KIL evidence classification contract"
```

### Task 2: Deterministic trust-decay arithmetic

**Files:**
- Create: `src/kil/decay.py`
- Create: `tests/test_decay.py`

- [ ] **Step 1: Write the failing arithmetic tests**

```python
from decimal import Decimal
import unittest

from kil.decay import (
    local_effective_charge,
    logistic_squash,
    passive_decay,
    superlinear_loss,
    weighted_diagonal_distance,
)


class DecayTest(unittest.TestCase):
    def test_identical_feature_vector_has_zero_distance(self):
        result = weighted_diagonal_distance(
            {"origin": Decimal("1")},
            {"origin": Decimal("1")},
            {"origin": Decimal("2")},
            {"origin": Decimal("1")},
        )
        self.assertEqual(result, Decimal("0"))

    def test_zero_scale_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "scale"):
            weighted_diagonal_distance(
                {"origin": Decimal("1")},
                {"origin": Decimal("0")},
                {"origin": Decimal("0")},
                {"origin": Decimal("1")},
            )

    def test_logistic_squash_is_bounded(self):
        self.assertEqual(logistic_squash(Decimal("0"), Decimal("1")), Decimal("0"))
        self.assertLess(logistic_squash(Decimal("10"), Decimal("1")), Decimal("1"))

    def test_passive_decay_never_increases_charge(self):
        result = passive_decay(Decimal("80"), Decimal("0.1"), Decimal("5"))
        self.assertGreaterEqual(result, Decimal("0"))
        self.assertLess(result, Decimal("80"))

    def test_loss_is_zero_inside_normal_band_and_superlinear_outside(self):
        self.assertEqual(
            superlinear_loss(Decimal("0.2"), Decimal("0.25"), Decimal("25"), 3),
            Decimal("0"),
        )
        first = superlinear_loss(Decimal("0.5"), Decimal("0.25"), Decimal("25"), 3)
        second = superlinear_loss(Decimal("1.0"), Decimal("0.25"), Decimal("25"), 3)
        self.assertEqual(second, first * 8)

    def test_local_effective_charge_clamps_and_never_increases(self):
        self.assertEqual(
            local_effective_charge(Decimal("20"), Decimal("50"), Decimal("5"), Decimal("100")),
            Decimal("0"),
        )
        self.assertEqual(
            local_effective_charge(Decimal("20"), Decimal("0"), Decimal("0"), Decimal("100")),
            Decimal("20"),
        )
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_decay -v`

Expected: import failure because `kil.decay` does not exist.

- [ ] **Step 3: Implement the deterministic arithmetic**

```python
from decimal import Decimal, localcontext
from collections.abc import Mapping


ZERO = Decimal("0")
ONE = Decimal("1")


def weighted_diagonal_distance(
    features: Mapping[str, Decimal],
    means: Mapping[str, Decimal],
    scales: Mapping[str, Decimal],
    weights: Mapping[str, Decimal],
) -> Decimal:
    keys = set(features)
    if keys != set(means) or keys != set(scales) or keys != set(weights):
        raise ValueError("feature, mean, scale, and weight keys must match")
    total = ZERO
    for key in sorted(keys):
        if scales[key] <= ZERO:
            raise ValueError("scale must be greater than zero")
        if weights[key] < ZERO:
            raise ValueError("weight must be non-negative")
        standardized = (features[key] - means[key]) / scales[key]
        total += weights[key] * standardized * standardized
    return total.sqrt()


def logistic_squash(raw: Decimal, k: Decimal) -> Decimal:
    if raw < ZERO or k <= ZERO:
        raise ValueError("raw must be non-negative and k must be positive")
    with localcontext() as context:
        context.prec = 28
        return (Decimal("2") / (ONE + (-k * raw).exp())) - ONE


def passive_decay(charge: Decimal, decay_rate: Decimal, elapsed: Decimal) -> Decimal:
    if charge < ZERO or decay_rate < ZERO or elapsed < ZERO:
        raise ValueError("charge, decay_rate, and elapsed must be non-negative")
    with localcontext() as context:
        context.prec = 28
        return charge * (-decay_rate * elapsed).exp()


def superlinear_loss(
    divergence: Decimal,
    threshold: Decimal,
    loss_rate: Decimal,
    exponent: int,
) -> Decimal:
    if not ZERO <= divergence <= ONE:
        raise ValueError("divergence must be in [0,1]")
    if threshold <= ZERO or loss_rate < ZERO or exponent <= 1:
        raise ValueError("threshold and loss profile are invalid")
    if divergence <= threshold:
        return ZERO
    return loss_rate * (divergence / threshold) ** exponent


def local_effective_charge(
    decayed_charge: Decimal,
    loss: Decimal,
    coupled_loss: Decimal,
    maximum: Decimal,
) -> Decimal:
    if min(decayed_charge, loss, coupled_loss, maximum) < ZERO:
        raise ValueError("charge inputs must be non-negative")
    return min(maximum, max(ZERO, decayed_charge - loss - coupled_loss))
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_decay -v`

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/kil/decay.py tests/test_decay.py
git commit -m "Implement deterministic trust-decay arithmetic"
```

### Task 3: Immutable decision-domain records

**Files:**
- Create: `src/kil/domain.py`
- Create: `tests/test_domain.py`

- [ ] **Step 1: Write the failing domain tests**

```python
from decimal import Decimal
import unittest

from kil.domain import (
    ActionRequest,
    CompositeState,
    EnforcementMode,
    LocalEvidence,
)


class DomainTest(unittest.TestCase):
    def test_composite_state_rejects_invalid_validity_window(self):
        with self.assertRaisesRegex(ValueError, "validity"):
            CompositeState(
                state_id="q-1", identity="worker", authority_class="admin",
                issued_at_s=10, not_before_s=20, expires_at_s=20,
                charge=Decimal("50"), threshold=Decimal("40"),
                history_count=5, minimum_history=2, authentic=True,
                veto_clear=True, envelope_allows=True,
                decay_rate=Decimal("0.1"), maximum_charge=Decimal("100"),
            )

    def test_local_evidence_rejects_unbounded_divergence(self):
        with self.assertRaisesRegex(ValueError, "divergence"):
            LocalEvidence(Decimal("1.1"), Decimal("0"), True)

    def test_request_and_mode_values_are_stable(self):
        request = ActionRequest("r-1", "worker", "admin", 30)
        self.assertEqual(request.request_id, "r-1")
        self.assertEqual(EnforcementMode.SIGNED_STATE_ONLY.value, "signed_state_only")
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_domain -v`

Expected: import failure because `kil.domain` does not exist.

- [ ] **Step 3: Implement the records and enums**

```python
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class EnforcementMode(str, Enum):
    SIGNED_STATE_ONLY = "signed_state_only"
    SIGNED_PLUS_LOCAL_REDUCE = "signed_plus_local_reduce"


class DecisionOutcome(str, Enum):
    PERMIT = "permit"
    CONSTRAIN = "constrain"
    DENY = "deny"
    INDETERMINATE = "indeterminate"


class FailureDisposition(str, Enum):
    CLOSED = "closed"
    CONSTRAINED = "constrained"


class ReasonCode(str, Enum):
    PERMITTED = "permitted"
    IDENTITY_MISMATCH = "identity_mismatch"
    CLASS_MISMATCH = "class_mismatch"
    VETO = "immutable_veto"
    OUTSIDE_ENVELOPE = "outside_environmental_envelope"
    STATE_UNAUTHENTIC = "state_unauthentic"
    STATE_NOT_YET_VALID = "state_not_yet_valid"
    STATE_EXPIRED = "state_expired"
    LOCAL_EVIDENCE_STALE = "local_evidence_stale"
    INSUFFICIENT_CHARGE = "insufficient_charge"
    INSUFFICIENT_HISTORY = "insufficient_history"


@dataclass(frozen=True, slots=True)
class ActionRequest:
    request_id: str
    identity: str
    authority_class: str
    timestamp_s: int


@dataclass(frozen=True, slots=True)
class CompositeState:
    state_id: str
    identity: str
    authority_class: str
    issued_at_s: int
    not_before_s: int
    expires_at_s: int
    charge: Decimal
    threshold: Decimal
    history_count: int
    minimum_history: int
    authentic: bool
    veto_clear: bool
    envelope_allows: bool
    decay_rate: Decimal
    maximum_charge: Decimal

    def __post_init__(self) -> None:
        if not self.issued_at_s <= self.not_before_s < self.expires_at_s:
            raise ValueError("invalid state validity window")
        if min(self.charge, self.threshold, self.decay_rate, self.maximum_charge) < 0:
            raise ValueError("charge profile must be non-negative")
        if self.charge > self.maximum_charge:
            raise ValueError("charge exceeds maximum")
        if self.history_count < 0 or self.minimum_history < 0:
            raise ValueError("history counts must be non-negative")


@dataclass(frozen=True, slots=True)
class LocalEvidence:
    divergence: Decimal
    coupled_loss: Decimal
    fresh: bool

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.divergence <= Decimal("1"):
            raise ValueError("divergence must be in [0,1]")
        if self.coupled_loss < 0:
            raise ValueError("coupled loss must be non-negative")


@dataclass(frozen=True, slots=True)
class ReductionProfile:
    divergence_threshold: Decimal
    loss_rate: Decimal
    exponent: int


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    request_id: str
    state_id: str
    mode: EnforcementMode
    outcome: DecisionOutcome
    reasons: tuple[ReasonCode, ...]
    signed_charge: Decimal
    decayed_charge: Decimal
    effective_charge: Decimal
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_domain -v`

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/kil/domain.py tests/test_domain.py
git commit -m "Define immutable KIL decision records"
```

### Task 4: Deterministic decision engine

**Files:**
- Create: `src/kil/engine.py`
- Create: `tests/test_engine.py`

- [ ] **Step 1: Write failing decision tests**

```python
from dataclasses import replace
from decimal import Decimal
import unittest

from kil.domain import (
    ActionRequest, CompositeState, DecisionOutcome, EnforcementMode,
    FailureDisposition, LocalEvidence, ReasonCode, ReductionProfile,
)
from kil.engine import decide


def state(**changes):
    value = CompositeState(
        state_id="q-1", identity="worker", authority_class="admin",
        issued_at_s=0, not_before_s=0, expires_at_s=100,
        charge=Decimal("80"), threshold=Decimal("40"),
        history_count=5, minimum_history=2, authentic=True,
        veto_clear=True, envelope_allows=True,
        decay_rate=Decimal("0"), maximum_charge=Decimal("100"),
    )
    return replace(value, **changes)


REQUEST = ActionRequest("r-1", "worker", "admin", 10)
PROFILE = ReductionProfile(Decimal("0.25"), Decimal("25"), 3)


class EngineTest(unittest.TestCase):
    def test_valid_signed_state_permits(self):
        record = decide(REQUEST, state(), EnforcementMode.SIGNED_STATE_ONLY)
        self.assertEqual(record.outcome, DecisionOutcome.PERMIT)
        self.assertEqual(record.reasons, (ReasonCode.PERMITTED,))

    def test_veto_cannot_be_overridden_by_high_charge(self):
        record = decide(REQUEST, state(veto_clear=False), EnforcementMode.SIGNED_STATE_ONLY)
        self.assertEqual(record.outcome, DecisionOutcome.DENY)
        self.assertIn(ReasonCode.VETO, record.reasons)

    def test_invalid_and_expired_state_deny(self):
        unauthentic = decide(
            REQUEST, state(authentic=False), EnforcementMode.SIGNED_STATE_ONLY
        )
        expired = decide(
            replace(REQUEST, timestamp_s=100), state(), EnforcementMode.SIGNED_STATE_ONLY
        )
        self.assertIn(ReasonCode.STATE_UNAUTHENTIC, unauthentic.reasons)
        self.assertIn(ReasonCode.STATE_EXPIRED, expired.reasons)

    def test_binding_envelope_and_history_gates_are_independent(self):
        cases = (
            (replace(REQUEST, identity="other"), state(), ReasonCode.IDENTITY_MISMATCH),
            (replace(REQUEST, authority_class="read"), state(), ReasonCode.CLASS_MISMATCH),
            (REQUEST, state(envelope_allows=False), ReasonCode.OUTSIDE_ENVELOPE),
            (REQUEST, state(history_count=1), ReasonCode.INSUFFICIENT_HISTORY),
            (replace(REQUEST, timestamp_s=-1), state(), ReasonCode.STATE_NOT_YET_VALID),
        )
        for request, composite, expected in cases:
            with self.subTest(expected=expected):
                record = decide(request, composite, EnforcementMode.SIGNED_STATE_ONLY)
                self.assertEqual(record.outcome, DecisionOutcome.DENY)
                self.assertIn(expected, record.reasons)

    def test_local_reduction_can_deny_but_never_increase(self):
        evidence = LocalEvidence(Decimal("0.9"), Decimal("0"), True)
        record = decide(
            REQUEST, state(), EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE,
            evidence, PROFILE,
        )
        self.assertEqual(record.outcome, DecisionOutcome.DENY)
        self.assertLessEqual(record.effective_charge, record.decayed_charge)

    def test_coupled_loss_only_reduces_effective_charge(self):
        plain = decide(
            REQUEST, state(), EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE,
            LocalEvidence(Decimal("0.1"), Decimal("0"), True), PROFILE,
        )
        coupled = decide(
            REQUEST, state(), EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE,
            LocalEvidence(Decimal("0.1"), Decimal("10"), True), PROFILE,
        )
        self.assertEqual(coupled.effective_charge, plain.effective_charge - Decimal("10"))

    def test_stale_local_evidence_fails_closed_by_default(self):
        evidence = LocalEvidence(Decimal("0.1"), Decimal("0"), False)
        record = decide(
            REQUEST, state(), EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE,
            evidence, PROFILE,
        )
        self.assertEqual(record.outcome, DecisionOutcome.DENY)
        self.assertIn(ReasonCode.LOCAL_EVIDENCE_STALE, record.reasons)

    def test_stale_local_evidence_can_fail_constrained_when_explicit(self):
        evidence = LocalEvidence(Decimal("0.1"), Decimal("0"), False)
        record = decide(
            REQUEST, state(), EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE,
            evidence, PROFILE, FailureDisposition.CONSTRAINED,
        )
        self.assertEqual(record.outcome, DecisionOutcome.CONSTRAIN)

    def test_veto_takes_precedence_over_stale_local_evidence(self):
        evidence = LocalEvidence(Decimal("0.1"), Decimal("0"), False)
        record = decide(
            REQUEST, state(veto_clear=False),
            EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE, evidence, PROFILE,
        )
        self.assertEqual(record.outcome, DecisionOutcome.DENY)
        self.assertIn(ReasonCode.VETO, record.reasons)

    def test_action_cannot_authorize_itself(self):
        evidence = LocalEvidence(Decimal("0"), Decimal("0"), True)
        record = decide(
            REQUEST, state(charge=Decimal("39")),
            EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE, evidence, PROFILE,
        )
        self.assertEqual(record.effective_charge, Decimal("39"))
        self.assertEqual(record.outcome, DecisionOutcome.DENY)
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_engine -v`

Expected: import failure because `kil.engine` does not exist.

- [ ] **Step 3: Implement the minimal decision engine**

```python
from decimal import Decimal

from .decay import local_effective_charge, passive_decay, superlinear_loss
from .domain import (
    ActionRequest, CompositeState, DecisionOutcome, DecisionRecord,
    EnforcementMode, FailureDisposition, LocalEvidence, ReasonCode,
    ReductionProfile,
)


def decide(
    request: ActionRequest,
    state: CompositeState,
    mode: EnforcementMode,
    local_evidence: LocalEvidence | None = None,
    reduction_profile: ReductionProfile | None = None,
    failure_disposition: FailureDisposition = FailureDisposition.CLOSED,
) -> DecisionRecord:
    reasons: list[ReasonCode] = []
    if request.identity != state.identity:
        reasons.append(ReasonCode.IDENTITY_MISMATCH)
    if request.authority_class != state.authority_class:
        reasons.append(ReasonCode.CLASS_MISMATCH)
    if not state.veto_clear:
        reasons.append(ReasonCode.VETO)
    if not state.envelope_allows:
        reasons.append(ReasonCode.OUTSIDE_ENVELOPE)
    if not state.authentic:
        reasons.append(ReasonCode.STATE_UNAUTHENTIC)
    if request.timestamp_s < state.not_before_s:
        reasons.append(ReasonCode.STATE_NOT_YET_VALID)
    if request.timestamp_s >= state.expires_at_s:
        reasons.append(ReasonCode.STATE_EXPIRED)

    elapsed = Decimal(max(0, request.timestamp_s - state.issued_at_s))
    decayed = passive_decay(state.charge, state.decay_rate, elapsed)
    effective = decayed

    if mode is EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE:
        if local_evidence is None or reduction_profile is None or not local_evidence.fresh:
            reasons.append(ReasonCode.LOCAL_EVIDENCE_STALE)
        else:
            loss = superlinear_loss(
                local_evidence.divergence,
                reduction_profile.divergence_threshold,
                reduction_profile.loss_rate,
                reduction_profile.exponent,
            )
            effective = local_effective_charge(
                decayed, loss, local_evidence.coupled_loss, state.maximum_charge
            )

    if effective < state.threshold:
        reasons.append(ReasonCode.INSUFFICIENT_CHARGE)
    if state.history_count < state.minimum_history:
        reasons.append(ReasonCode.INSUFFICIENT_HISTORY)

    decisive_reasons = [
        reason for reason in reasons if reason is not ReasonCode.LOCAL_EVIDENCE_STALE
    ]
    if decisive_reasons:
        outcome = DecisionOutcome.DENY
    elif ReasonCode.LOCAL_EVIDENCE_STALE in reasons:
        outcome = (
            DecisionOutcome.CONSTRAIN
            if failure_disposition is FailureDisposition.CONSTRAINED
            else DecisionOutcome.DENY
        )
    else:
        outcome = DecisionOutcome.PERMIT
        reasons.append(ReasonCode.PERMITTED)

    return DecisionRecord(
        request.request_id, state.state_id, mode, outcome, tuple(reasons),
        state.charge, decayed, effective,
    )
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_engine -v`

Expected: 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/kil/engine.py tests/test_engine.py
git commit -m "Implement deterministic KIL decision engine"
```

### Task 5: Canonical decision serialization and invariant sweep

**Files:**
- Create: `src/kil/canonical.py`
- Create: `tests/test_kernel_invariants.py`
- Modify: `src/kil/__init__.py`

- [ ] **Step 1: Write failing canonicalization and property-loop tests**

```python
from dataclasses import asdict, replace
from decimal import Decimal
import unittest

from kil.canonical import canonical_digest, canonical_json
from kil.domain import (
    ActionRequest, CompositeState, EnforcementMode, LocalEvidence,
    ReductionProfile,
)
from kil.engine import decide


class KernelInvariantTest(unittest.TestCase):
    def test_canonical_serialization_is_stable(self):
        left = {"b": Decimal("1.0"), "a": "value"}
        right = {"a": "value", "b": Decimal("1.0")}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(canonical_digest(left), canonical_digest(right))

    def test_local_mode_never_exceeds_signed_mode(self):
        request = ActionRequest("r", "i", "admin", 10)
        base = CompositeState(
            "q", "i", "admin", 0, 0, 100,
            Decimal("80"), Decimal("40"), 5, 2, True, True, True,
            Decimal("0.01"), Decimal("100"),
        )
        profile = ReductionProfile(Decimal("0.25"), Decimal("25"), 3)
        signed = decide(request, base, EnforcementMode.SIGNED_STATE_ONLY)
        for step in range(0, 11):
            evidence = LocalEvidence(Decimal(step) / Decimal("10"), Decimal("0"), True)
            local = decide(
                request, base, EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE,
                evidence, profile,
            )
            self.assertLessEqual(local.effective_charge, signed.effective_charge)

    def test_more_loss_never_produces_more_authority(self):
        request = ActionRequest("r", "i", "admin", 10)
        state = CompositeState(
            "q", "i", "admin", 0, 0, 100,
            Decimal("80"), Decimal("40"), 5, 2, True, True, True,
            Decimal("0"), Decimal("100"),
        )
        profile = ReductionProfile(Decimal("0.25"), Decimal("25"), 3)
        charges = []
        for step in range(3, 11):
            evidence = LocalEvidence(Decimal(step) / Decimal("10"), Decimal("0"), True)
            charges.append(decide(
                request, state, EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE,
                evidence, profile,
            ).effective_charge)
        self.assertEqual(charges, sorted(charges, reverse=True))
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_kernel_invariants -v`

Expected: import failure because `kil.canonical` does not exist.

- [ ] **Step 3: Implement canonical JSON and digest**

```python
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from typing import Any


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def canonical_digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Update the existing package test first, then run it RED**

Change `tests/test_package.py` to expect `"0.1.0-dev1"`, run
`PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_package -v`, and confirm it fails
before editing `src/kil/__init__.py`.

- [ ] **Step 5: Update the package version**

Update `src/kil/__init__.py` to set `__version__ = "0.1.0-dev1"` and revise its
module docstring to state that V1 deterministic behavior is implemented while
cryptographic and live adapters remain outside this gate.

- [ ] **Step 6: Run all V1 tests and verify GREEN**

Run:

```bash
PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest \
  tests.test_evidence tests.test_decay tests.test_domain \
  tests.test_engine tests.test_kernel_invariants tests.test_package -v
```

Expected: all V1 tests pass.

- [ ] **Step 7: Run the repository gate and source-integrity check**

Run: `make validate PYTHON='/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' && shasum -a 256 -c research/source-material/SHA256SUMS`

Expected: all tests pass and all preserved sources report `OK`.

- [ ] **Step 8: Commit**

```bash
git add src/kil/canonical.py src/kil/__init__.py \
  tests/test_kernel_invariants.py tests/test_package.py
git commit -m "Complete V1 deterministic KIL kernel"
```

## V1 exit criteria

- Every new behavior has a recorded red-to-green test cycle.
- Local reduction is monotonic and cannot exceed signed-state-only authority.
- Veto, envelope, authenticity, validity, charge, and history gates are
  independently testable.
- Canonical decision serialization and digest are deterministic.
- No claim is made that the kernel verifies a concrete KTP signature encoding.
- Full repository validation and preserved-source checks pass.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
