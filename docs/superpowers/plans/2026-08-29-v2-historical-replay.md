# V2 Historical KIL Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize the source-cited Hugging Face incident sequence, execute the credential-policy control and both KIL modes, and produce deterministic modeled run bundles suitable for white-paper figures.

**Architecture:** V2 is an adapter over the V1 kernel. A strict scenario loader converts versioned JSON into immutable V1 requests, states, and local evidence. The replay engine evaluates one common event stream under three modes and writes canonical, hashed artifacts; it never promotes historical counterfactual output to validated.

**Tech Stack:** Python 3.12 standard library, V1 KIL kernel, JSON/JSONL, SHA-256, `argparse`, `tempfile`, `unittest`.

---

### Task 1: Versioned scenario schema and loader

**Files:**
- Create: `schemas/scenario-v1.schema.json`
- Create: `src/kil/scenario.py`
- Create: `tests/fixtures/scenario-minimal-v1.json`
- Create: `tests/test_scenario.py`

- [ ] **Step 1: Write the failing loader tests**

```python
import json
from pathlib import Path
import unittest

from kil.evidence import EvidenceClass
from kil.scenario import load_scenario


FIXTURE = Path(__file__).parent / "fixtures/scenario-minimal-v1.json"


class ScenarioTest(unittest.TestCase):
    def test_loads_source_cited_observed_event_and_modeled_context(self):
        scenario = load_scenario(FIXTURE)
        event = scenario.events[0]
        self.assertEqual(scenario.schema_version, "kil.scenario.v1")
        self.assertEqual(event.observed_summary.evidence_class, EvidenceClass.OBSERVED)
        self.assertEqual(event.control_assumption.evidence_class, EvidenceClass.MODELED)
        self.assertEqual(event.state_assumption.evidence_class, EvidenceClass.MODELED)
        self.assertEqual(event.local_evidence_assumption.evidence_class, EvidenceClass.MODELED)

    def test_rejects_observed_event_without_source(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        del raw["events"][0]["source_ref"]
        with self.assertRaisesRegex(ValueError, "source_ref"):
            load_scenario(raw)

    def test_rejects_modeled_context_without_rationale(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        del raw["events"][0]["modeled_context"]["rationale"]
        with self.assertRaisesRegex(ValueError, "rationale"):
            load_scenario(raw)

    def test_rejects_control_assumption_without_rationale(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        del raw["events"][0]["control_rationale"]
        with self.assertRaisesRegex(ValueError, "control_rationale"):
            load_scenario(raw)

    def test_rejects_composite_state_without_modeled_rationale(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        del raw["events"][0]["state_rationale"]
        with self.assertRaisesRegex(ValueError, "state_rationale"):
            load_scenario(raw)

    def test_rejects_unknown_fields(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        raw["events"][0]["silent_override"] = True
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_scenario(raw)
```

- [ ] **Step 2: Add the exact minimal fixture**

```json
{
  "schema_version": "kil.scenario.v1",
  "scenario_id": "hf-july-2026-minimal",
  "primary_source": "https://huggingface.co/blog/agent-intrusion-technical-timeline",
  "events": [
    {
      "event_id": "hf-p1-cluster-api",
      "phase": 1,
      "timestamp_s": 10,
      "identity": "dataset-worker",
      "authority_class": "admin_action",
      "summary": "Worker identity addressed the Kubernetes control plane.",
      "source_ref": "technical timeline: Day-by-day / cluster API transition",
      "credential_valid": true,
      "policy_allows_action": true,
      "control_rationale": "Modeled credential-policy baseline for this cut point; the public timeline does not specify a complete policy evaluation record.",
      "state_rationale": "Synthetic Q_i,c state for counterfactual evaluation; the public timeline contains no KTP enforcement state.",
      "depends_on": [],
      "state": {
        "state_id": "q-hf-p1", "issued_at_s": 0, "not_before_s": 0,
        "expires_at_s": 60, "charge": "5", "threshold": "40",
        "history_count": 0, "minimum_history": 2, "authentic": true,
        "veto_clear": true, "envelope_allows": true,
        "decay_rate": "0.05", "maximum_charge": "100"
      },
      "modeled_context": {
        "divergence": "0.95", "coupled_loss": "0", "fresh": true,
        "rationale": "Synthetic class-history and control-plane novelty signal; raw telemetry was not disclosed."
      }
    }
  ]
}
```

- [ ] **Step 3: Run the tests and verify RED**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_scenario -v`

Expected: import failure because `kil.scenario` does not exist.

- [ ] **Step 4: Add the machine-readable schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/gatekeeper454/KIL/schemas/scenario-v1.schema.json",
  "title": "KIL historical replay scenario v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "scenario_id", "primary_source", "events"],
  "properties": {
    "schema_version": {"const": "kil.scenario.v1"},
    "scenario_id": {"type": "string", "minLength": 1},
    "primary_source": {"type": "string", "format": "uri"},
    "events": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["event_id", "phase", "timestamp_s", "identity",
          "authority_class", "summary", "source_ref", "credential_valid",
          "policy_allows_action", "control_rationale", "state_rationale", "depends_on", "state",
          "modeled_context"],
        "properties": {
          "event_id": {"type": "string", "minLength": 1},
          "phase": {"type": "integer", "minimum": 1},
          "timestamp_s": {"type": "integer", "minimum": 0},
          "identity": {"type": "string", "minLength": 1},
          "authority_class": {"type": "string", "minLength": 1},
          "summary": {"type": "string", "minLength": 1},
          "source_ref": {"type": "string", "minLength": 1},
          "credential_valid": {"type": "boolean"},
          "policy_allows_action": {"type": "boolean"},
          "control_rationale": {"type": "string", "minLength": 1},
          "state_rationale": {"type": "string", "minLength": 1},
          "depends_on": {"type": "array", "items": {"type": "string"}, "uniqueItems": true},
          "state": {
            "type": "object", "additionalProperties": false,
            "required": ["state_id", "issued_at_s", "not_before_s", "expires_at_s",
              "charge", "threshold", "history_count", "minimum_history",
              "authentic", "veto_clear", "envelope_allows", "decay_rate",
              "maximum_charge"],
            "properties": {
              "state_id": {"type": "string", "minLength": 1},
              "issued_at_s": {"type": "integer", "minimum": 0},
              "not_before_s": {"type": "integer", "minimum": 0},
              "expires_at_s": {"type": "integer", "minimum": 1},
              "charge": {"type": "string", "pattern": "^-?[0-9]+(\\.[0-9]+)?$"},
              "threshold": {"type": "string", "pattern": "^-?[0-9]+(\\.[0-9]+)?$"},
              "history_count": {"type": "integer", "minimum": 0},
              "minimum_history": {"type": "integer", "minimum": 0},
              "authentic": {"type": "boolean"},
              "veto_clear": {"type": "boolean"},
              "envelope_allows": {"type": "boolean"},
              "decay_rate": {"type": "string", "pattern": "^-?[0-9]+(\\.[0-9]+)?$"},
              "maximum_charge": {"type": "string", "pattern": "^-?[0-9]+(\\.[0-9]+)?$"}
            }
          },
          "modeled_context": {
            "type": "object", "additionalProperties": false,
            "required": ["divergence", "coupled_loss", "fresh", "rationale"],
            "properties": {
              "divergence": {"type": "string", "pattern": "^-?[0-9]+(\\.[0-9]+)?$"},
              "coupled_loss": {"type": "string", "pattern": "^-?[0-9]+(\\.[0-9]+)?$"},
              "fresh": {"type": "boolean"},
              "rationale": {"type": "string", "minLength": 1}
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 5: Implement the strict loader**

```python
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from .domain import ActionRequest, CompositeState, LocalEvidence
from .evidence import EvidenceClass, LabeledValue


@dataclass(frozen=True, slots=True)
class ScenarioEvent:
    event_id: str
    phase: int
    request: ActionRequest
    observed_summary: LabeledValue[str]
    control_assumption: LabeledValue[tuple[bool, bool]]
    depends_on: tuple[str, ...]
    state_assumption: LabeledValue[CompositeState]
    local_evidence_assumption: LabeledValue[LocalEvidence]


@dataclass(frozen=True, slots=True)
class Scenario:
    schema_version: str
    scenario_id: str
    primary_source: str
    events: tuple[ScenarioEvent, ...]


def _required(mapping: dict[str, Any], key: str) -> Any:
    if key not in mapping:
        raise ValueError(f"missing required field: {key}")
    return mapping[key]


def _expect_keys(mapping: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(mapping) - allowed
    if unknown:
        raise ValueError(f"unknown fields in {where}: {sorted(unknown)}")


def load_scenario(source: Path | dict[str, Any]) -> Scenario:
    raw = json.loads(source.read_text(encoding="utf-8")) if isinstance(source, Path) else source
    _expect_keys(raw, {"schema_version", "scenario_id", "primary_source", "events"}, "scenario")
    if _required(raw, "schema_version") != "kil.scenario.v1":
        raise ValueError("unsupported schema_version")
    primary = _required(raw, "primary_source")
    events = []
    seen: set[str] = set()
    for item in _required(raw, "events"):
        _expect_keys(item, {
            "event_id", "phase", "timestamp_s", "identity", "authority_class",
            "summary", "source_ref", "credential_valid", "policy_allows_action",
            "control_rationale", "state_rationale", "depends_on", "state", "modeled_context",
        }, "event")
        event_id = _required(item, "event_id")
        if event_id in seen:
            raise ValueError(f"duplicate event_id: {event_id}")
        dependencies = tuple(item.get("depends_on", []))
        if any(parent not in seen for parent in dependencies):
            raise ValueError(f"event dependencies must reference earlier events: {event_id}")
        state_raw = _required(item, "state")
        modeled = _required(item, "modeled_context")
        _expect_keys(state_raw, {
            "state_id", "issued_at_s", "not_before_s", "expires_at_s", "charge",
            "threshold", "history_count", "minimum_history", "authentic",
            "veto_clear", "envelope_allows", "decay_rate", "maximum_charge",
        }, "state")
        _expect_keys(modeled, {"divergence", "coupled_loss", "fresh", "rationale"}, "modeled_context")
        source_ref = _required(item, "source_ref")
        rationale = _required(modeled, "rationale")
        control_rationale = _required(item, "control_rationale")
        state_rationale = _required(item, "state_rationale")
        identity = _required(item, "identity")
        authority_class = _required(item, "authority_class")
        timestamp = int(_required(item, "timestamp_s"))
        state = CompositeState(
            state_id=_required(state_raw, "state_id"), identity=identity,
            authority_class=authority_class,
            issued_at_s=int(_required(state_raw, "issued_at_s")),
            not_before_s=int(_required(state_raw, "not_before_s")),
            expires_at_s=int(_required(state_raw, "expires_at_s")),
            charge=Decimal(_required(state_raw, "charge")),
            threshold=Decimal(_required(state_raw, "threshold")),
            history_count=int(_required(state_raw, "history_count")),
            minimum_history=int(_required(state_raw, "minimum_history")),
            authentic=bool(_required(state_raw, "authentic")),
            veto_clear=bool(_required(state_raw, "veto_clear")),
            envelope_allows=bool(_required(state_raw, "envelope_allows")),
            decay_rate=Decimal(_required(state_raw, "decay_rate")),
            maximum_charge=Decimal(_required(state_raw, "maximum_charge")),
        )
        divergence = Decimal(_required(modeled, "divergence"))
        events.append(ScenarioEvent(
            event_id=event_id, phase=int(_required(item, "phase")),
            request=ActionRequest(event_id, identity, authority_class, timestamp),
            observed_summary=LabeledValue(
                _required(item, "summary"), EvidenceClass.OBSERVED,
                source_ref=f"{primary}#{source_ref}",
            ),
            control_assumption=LabeledValue(
                (bool(_required(item, "credential_valid")),
                 bool(_required(item, "policy_allows_action"))),
                EvidenceClass.MODELED, rationale=control_rationale,
            ),
            depends_on=dependencies,
            state_assumption=LabeledValue(
                state, EvidenceClass.MODELED, rationale=state_rationale,
            ),
            local_evidence_assumption=LabeledValue(
                LocalEvidence(
                    divergence, Decimal(_required(modeled, "coupled_loss")),
                    bool(_required(modeled, "fresh")),
                ),
                EvidenceClass.MODELED, rationale=rationale,
            ),
        ))
        seen.add(event_id)
    return Scenario(raw["schema_version"], _required(raw, "scenario_id"), primary, tuple(events))
```

- [ ] **Step 6: Run the focused tests and verify GREEN**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_scenario -v`

Expected: 6 tests pass.

- [ ] **Step 7: Commit**

```bash
git add schemas/scenario-v1.schema.json src/kil/scenario.py \
  tests/fixtures/scenario-minimal-v1.json tests/test_scenario.py
git commit -m "Define versioned KIL replay scenario"
```

### Task 2: Common-stream control and KIL replay

**Files:**
- Create: `src/kil/replay.py`
- Create: `tests/test_replay.py`

- [ ] **Step 1: Write failing paired-replay tests**

```python
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import unittest

from kil.domain import DecisionOutcome, ReductionProfile
from kil.replay import replay
from kil.scenario import load_scenario


FIXTURE = Path(__file__).parent / "fixtures/scenario-minimal-v1.json"


class ReplayTest(unittest.TestCase):
    def test_all_modes_consume_the_same_event(self):
        report = replay(
            load_scenario(FIXTURE),
            ReductionProfile(Decimal("0.25"), Decimal("25"), 3),
        )
        decision = report.decisions[0]
        self.assertTrue(decision.baseline_permit)
        self.assertEqual(decision.signed_state_only.outcome, DecisionOutcome.DENY)
        self.assertEqual(decision.signed_plus_local_reduce.outcome, DecisionOutcome.DENY)
        self.assertEqual(decision.evidence_class, "modeled")

    def test_historical_output_cannot_be_promoted_to_validated(self):
        report = replay(
            load_scenario(FIXTURE),
            ReductionProfile(Decimal("0.25"), Decimal("25"), 3),
        )
        self.assertEqual(report.evidence_class, "modeled")

    def test_denied_parent_marks_kil_descendant_unreachable_without_hiding_decision(self):
        scenario = load_scenario(FIXTURE)
        parent = scenario.events[0]
        child = replace(
            parent,
            event_id="child",
            request=replace(parent.request, request_id="child", timestamp_s=20),
            state_assumption=replace(
                parent.state_assumption,
                value=replace(parent.state_assumption.value, state_id="q-child",
                              charge=Decimal("80"), history_count=5),
            ),
            depends_on=(parent.event_id,),
        )
        report = replay(
            replace(scenario, events=(parent, child)),
            ReductionProfile(Decimal("0.25"), Decimal("25"), 3),
        )
        descendant = report.decisions[1]
        self.assertTrue(descendant.baseline_reachable)
        self.assertFalse(descendant.signed_state_only_reachable)
        self.assertFalse(descendant.signed_plus_local_reduce_reachable)
        self.assertIsNotNone(descendant.signed_state_only)
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_replay -v`

Expected: import failure because `kil.replay` does not exist.

- [ ] **Step 3: Implement paired replay**

```python
from dataclasses import dataclass

from .domain import DecisionOutcome, DecisionRecord, EnforcementMode, ReductionProfile
from .engine import decide
from .scenario import Scenario


@dataclass(frozen=True, slots=True)
class PairedDecision:
    event_id: str
    baseline_permit: bool
    baseline_reachable: bool
    signed_state_only: DecisionRecord
    signed_state_only_reachable: bool
    signed_plus_local_reduce: DecisionRecord
    signed_plus_local_reduce_reachable: bool
    evidence_class: str = "modeled"


@dataclass(frozen=True, slots=True)
class ReplayReport:
    scenario_id: str
    decisions: tuple[PairedDecision, ...]
    evidence_class: str = "modeled"


def replay(scenario: Scenario, profile: ReductionProfile) -> ReplayReport:
    decisions = []
    baseline_success: set[str] = set()
    signed_success: set[str] = set()
    local_success: set[str] = set()
    for event in scenario.events:
        baseline_reachable = all(parent in baseline_success for parent in event.depends_on)
        signed_reachable = all(parent in signed_success for parent in event.depends_on)
        local_reachable = all(parent in local_success for parent in event.depends_on)
        credential_valid, policy_allows_action = event.control_assumption.value
        baseline_permit = credential_valid and policy_allows_action
        signed = decide(
            event.request, event.state_assumption.value,
            EnforcementMode.SIGNED_STATE_ONLY,
        )
        local = decide(
            event.request, event.state_assumption.value,
            EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE,
            event.local_evidence_assumption.value, profile,
        )
        decisions.append(PairedDecision(
            event_id=event.event_id,
            baseline_permit=baseline_permit,
            baseline_reachable=baseline_reachable,
            signed_state_only=signed,
            signed_state_only_reachable=signed_reachable,
            signed_plus_local_reduce=local,
            signed_plus_local_reduce_reachable=local_reachable,
        ))
        if baseline_reachable and baseline_permit:
            baseline_success.add(event.event_id)
        if signed_reachable and signed.outcome is DecisionOutcome.PERMIT:
            signed_success.add(event.event_id)
        if local_reachable and local.outcome is DecisionOutcome.PERMIT:
            local_success.add(event.event_id)
    return ReplayReport(scenario.scenario_id, tuple(decisions))
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_replay -v`

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/kil/replay.py tests/test_replay.py
git commit -m "Add paired KIL historical replay"
```

### Task 3: Deterministic run bundles

**Files:**
- Create: `src/kil/run_bundle.py`
- Create: `tests/test_run_bundle.py`

- [ ] **Step 1: Write failing bundle tests**

```python
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kil.domain import ReductionProfile
from kil.replay import replay
from kil.run_bundle import write_run_bundle
from kil.scenario import load_scenario


FIXTURE = Path(__file__).parent / "fixtures/scenario-minimal-v1.json"


class RunBundleTest(unittest.TestCase):
    def test_same_inputs_produce_same_run_id_and_artifacts(self):
        scenario = load_scenario(FIXTURE)
        report = replay(scenario, ReductionProfile(Decimal("0.25"), Decimal("25"), 3))
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            one = write_run_bundle(report, scenario, Path(first), "test-commit", "profile-v0")
            two = write_run_bundle(report, scenario, Path(second), "test-commit", "profile-v0")
            self.assertEqual(one.name, two.name)
            self.assertEqual(
                (one / "SHA256SUMS").read_text(encoding="utf-8"),
                (two / "SHA256SUMS").read_text(encoding="utf-8"),
            )

    def test_bundle_never_labels_historical_report_validated(self):
        scenario = load_scenario(FIXTURE)
        report = replay(scenario, ReductionProfile(Decimal("0.25"), Decimal("25"), 3))
        with TemporaryDirectory() as directory:
            bundle = write_run_bundle(report, scenario, Path(directory), "test-commit", "profile-v0")
            manifest = (bundle / "manifest.json").read_text(encoding="utf-8")
            self.assertIn('"evidence_class":"modeled"', manifest)
            self.assertNotIn('"evidence_class":"validated"', manifest)

    def test_bundle_contains_the_complete_publication_contract(self):
        scenario = load_scenario(FIXTURE)
        report = replay(scenario, ReductionProfile(Decimal("0.25"), Decimal("25"), 3))
        with TemporaryDirectory() as directory:
            bundle = write_run_bundle(report, scenario, Path(directory), "test-commit", "profile-v0")
            self.assertEqual(
                {path.name for path in bundle.iterdir()},
                {"manifest.json", "scenario.json", "states.jsonl", "decisions.jsonl",
                 "metrics.json", "summary.md", "SHA256SUMS"},
            )
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_run_bundle -v`

Expected: import failure because `kil.run_bundle` does not exist.

- [ ] **Step 3: Implement canonical bundle output**

```python
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from .canonical import canonical_digest, canonical_json
from .replay import ReplayReport
from .scenario import Scenario


def write_run_bundle(
    report: ReplayReport,
    scenario: Scenario,
    output_root: Path,
    implementation_version: str,
    profile_id: str,
) -> Path:
    identity = {
        "scenario_id": report.scenario_id,
        "implementation_version": implementation_version,
        "profile_id": profile_id,
        "scenario": scenario,
        "report": report,
    }
    run_id = canonical_digest(identity)[:16]
    bundle = output_root / run_id
    bundle.mkdir(parents=True, exist_ok=False)
    baseline_permits = sum(item.baseline_permit for item in report.decisions)
    baseline_reachable_permits = sum(
        item.baseline_reachable and item.baseline_permit for item in report.decisions
    )
    signed_denies = sum(item.signed_state_only.outcome.value == "deny" for item in report.decisions)
    local_denies = sum(item.signed_plus_local_reduce.outcome.value == "deny" for item in report.decisions)
    signed_unreachable = sum(not item.signed_state_only_reachable for item in report.decisions)
    local_unreachable = sum(not item.signed_plus_local_reduce_reachable for item in report.decisions)
    artifacts = {
        "manifest.json": canonical_json({
            "run_id": run_id,
            "scenario_id": report.scenario_id,
            "implementation_version": implementation_version,
            "profile_id": profile_id,
            "evidence_class": "modeled",
        }) + "\n",
        "scenario.json": canonical_json(scenario) + "\n",
        "states.jsonl": "".join(canonical_json(event.state_assumption) + "\n" for event in scenario.events),
        "decisions.jsonl": "".join(canonical_json(item) + "\n" for item in report.decisions),
        "metrics.json": canonical_json({
            "event_count": len(report.decisions),
            "baseline_permits": baseline_permits,
            "baseline_reachable_permits": baseline_reachable_permits,
            "signed_state_only_denies": signed_denies,
            "signed_plus_local_reduce_denies": local_denies,
            "signed_state_only_unreachable": signed_unreachable,
            "signed_plus_local_reduce_unreachable": local_unreachable,
            "evidence_class": "modeled",
        }) + "\n",
        "summary.md": (
            f"# KIL modeled replay {run_id}\n\n"
            f"Scenario: `{report.scenario_id}`  \n"
            f"Events: {len(report.decisions)}  \n"
            f"Baseline permits: {baseline_permits}  \n"
            f"Signed-state-only denials: {signed_denies}  \n"
            f"Signed-plus-local-reduction denials: {local_denies}\n\n"
            "These historical counterfactual decisions are modeled, not validated.\n\n"
            "KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).\n"
        ),
    }
    for name, content in artifacts.items():
        (bundle / name).write_text(content, encoding="utf-8")
    checksums = []
    for name in sorted(artifacts):
        digest = sha256((bundle / name).read_bytes()).hexdigest()
        checksums.append(f"{digest}  {name}")
    (bundle / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    return bundle
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_run_bundle -v`

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/kil/run_bundle.py tests/test_run_bundle.py
git commit -m "Emit deterministic KIL replay bundles"
```

### Task 4: Canonical eight-phase Hugging Face scenario

**Files:**
- Create: `scenarios/hugging-face-july-2026/scenario-v1.json`
- Create: `tests/test_hugging_face_scenario.py`
- Modify: `scenarios/hugging-face-july-2026/README.md`

- [ ] **Step 1: Write the failing provenance and coverage tests**

```python
from pathlib import Path
import unittest

from kil.evidence import EvidenceClass
from kil.scenario import load_scenario


SCENARIO = Path(__file__).resolve().parents[1] / "scenarios/hugging-face-july-2026/scenario-v1.json"
SOURCE = "https://huggingface.co/blog/agent-intrusion-technical-timeline"


class HuggingFaceScenarioTest(unittest.TestCase):
    def test_scenario_covers_the_eight_counterfactual_cut_points(self):
        scenario = load_scenario(SCENARIO)
        self.assertEqual([event.phase for event in scenario.events], list(range(1, 9)))
        self.assertEqual(len({event.event_id for event in scenario.events}), 8)

    def test_observed_and_modeled_fields_remain_distinct(self):
        scenario = load_scenario(SCENARIO)
        for event in scenario.events:
            self.assertEqual(event.observed_summary.evidence_class, EvidenceClass.OBSERVED)
            self.assertTrue(event.observed_summary.source_ref.startswith(SOURCE))
            self.assertEqual(event.control_assumption.evidence_class, EvidenceClass.MODELED)
            self.assertEqual(event.state_assumption.evidence_class, EvidenceClass.MODELED)
            self.assertEqual(event.local_evidence_assumption.evidence_class, EvidenceClass.MODELED)
            self.assertTrue(event.control_assumption.rationale)
            self.assertTrue(event.state_assumption.rationale)
            self.assertTrue(event.local_evidence_assumption.rationale)
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_hugging_face_scenario -v`

Expected: file-not-found failure because `scenario-v1.json` does not exist.

- [ ] **Step 3: Populate the exact eight-event scenario**

Use these stable IDs, phases, source-section labels, authority classes, and
dependencies. Every numerical KTP signal is a string and carries a modeled
rationale stating that raw KTP telemetry was not disclosed:

| Event ID | Phase | Source section | Authority class | Depends on |
|---|---:|---|---|---|
| `hf-p1-cluster-api` | 1 | `Day-by-day / cluster API transition` | `admin_action` | none |
| `hf-p2-external-replay` | 2 | `Three lateral-movement techniques / cloud credentials` | `network_egress_external` | phase 1 |
| `hf-p3-privileged-workload` | 3 | `Day-by-day / node privilege` | `privilege_escalation` | phase 1 |
| `hf-p4-secret-read` | 4 | `Three lateral-movement techniques / secret access` | `read_other_resource` | phase 3 |
| `hf-p5-cross-cluster-admin` | 5 | `Three lateral-movement techniques / connector credential` | `admin_action` | phase 4 |
| `hf-p6-mesh-enrollment` | 6 | `Command-and-control and exfiltration / mesh enrollment` | `network_egress_external` | phase 4 |
| `hf-p7-forged-token` | 7 | `Three lateral-movement techniques / signing capability` | `mint_token` | phase 4 |
| `hf-p8-ci-pivot` | 8 | `Day-by-day / source-control and CI pivot` | `admin_action` | phases 6 and 7 |

Use this exact modeled profile for the first replay. All states use
`issued_at_s=0`, `not_before_s=0`, `expires_at_s=600`, `authentic=true`,
`veto_clear=true`, `envelope_allows=true`, `decay_rate="0.01"`, and
`maximum_charge="100"`:

| Phase | `timestamp_s` | charge / threshold | history / minimum | divergence | coupled loss |
|---:|---:|---|---|---|---|
| 1 | 10 | `5` / `40` | 0 / 2 | `0.95` | `0` |
| 2 | 20 | `10` / `35` | 0 / 2 | `0.98` | `0` |
| 3 | 30 | `0` / `70` | 0 / 5 | `1.0` | `0` |
| 4 | 40 | `40` / `50` | 1 / 3 | `0.90` | `20` |
| 5 | 50 | `0` / `80` | 0 / 5 | `1.0` | `0` |
| 6 | 60 | `15` / `40` | 0 / 2 | `0.95` | `0` |
| 7 | 70 | `0` / `60` | 0 / 3 | `1.0` | `0` |
| 8 | 80 | `10` / `60` | 0 / 3 | `0.90` | `0` |

For the first paired control, set `credential_valid=true` and
`policy_allows_action=true` for the consequential action selected from each
successful incident phase. Set `control_rationale` to: “Modeled
credential-policy baseline for the consequential action; the public timeline
reports that the action occurred but does not provide a complete policy-engine
decision record.” This keeps the control assumption modeled rather than
misclassifying it as an observed policy trace. Use the paper's phase-map
summaries verbatim to prevent narrative drift.

Set every event's `state_rationale` to: “Synthetic `Q_i,c` state for
counterfactual evaluation; the public timeline contains no KTP enforcement
state.” This explicitly keeps charge, threshold, history, authenticity,
freshness, envelope, and decay inputs modeled.

- [ ] **Step 4: Update the scenario README**

Document the primary source, schema version, event IDs, evidence distinction,
and statement that expected KIL decisions are counterfactual and modeled.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_hugging_face_scenario -v`

Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add scenarios/hugging-face-july-2026/scenario-v1.json \
  scenarios/hugging-face-july-2026/README.md tests/test_hugging_face_scenario.py
git commit -m "Normalize Hugging Face replay scenario"
```

### Task 5: Replay CLI and first modeled report

**Files:**
- Create: `tools/replay.py`
- Create: `tests/test_replay_cli.py`
- Modify: `Makefile`
- Modify: `README.md`

- [ ] **Step 1: Write the failing CLI test**

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReplayCliTest(unittest.TestCase):
    def test_cli_emits_a_modeled_integrity_checked_bundle(self):
        with TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, "tools/replay.py", "--output", directory,
                 "--implementation-version", "test-commit"],
                cwd=ROOT, env={**os.environ, "PYTHONPATH": "src"}, text=True,
                capture_output=True, check=True,
            )
            bundle = Path(completed.stdout.strip())
            self.assertTrue((bundle / "manifest.json").is_file())
            self.assertTrue((bundle / "SHA256SUMS").is_file())
            self.assertIn('"evidence_class":"modeled"',
                          (bundle / "manifest.json").read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run the test and verify RED**

Run: `PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest tests.test_replay_cli -v`

Expected: subprocess failure because `tools/replay.py` does not exist.

- [ ] **Step 3: Implement the CLI**

```python
#!/usr/bin/env python3
from argparse import ArgumentParser
from decimal import Decimal
from pathlib import Path

from kil.domain import ReductionProfile
from kil.replay import replay
from kil.run_bundle import write_run_bundle
from kil.scenario import load_scenario


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--scenario", type=Path,
        default=Path("scenarios/hugging-face-july-2026/scenario-v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--implementation-version", required=True)
    args = parser.parse_args()
    profile = ReductionProfile(Decimal("0.25"), Decimal("25"), 3)
    scenario = load_scenario(args.scenario)
    report = replay(scenario, profile)
    bundle = write_run_bundle(
        report, scenario, args.output, args.implementation_version,
        "weighted-diagonal-v0-modeled",
    )
    print(bundle)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add Make targets and usage documentation**

Add `replay` to `.PHONY`, document `make replay OUTPUT=/absolute/path
VERSION=<commit>`, and invoke the CLI with those required variables. Update the
root README status to say V2 replay is locally executable but its historical
decisions remain modeled.

- [ ] **Step 5: Run focused and complete verification**

Run:

```bash
PYTHONPATH=src '/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3' -m unittest \
  tests.test_scenario tests.test_replay tests.test_run_bundle \
  tests.test_hugging_face_scenario tests.test_replay_cli -v
make validate PYTHON='/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
shasum -a 256 -c research/source-material/SHA256SUMS
```

Expected: all V2 and repository tests pass; all preserved sources report `OK`.

- [ ] **Step 6: Commit**

```bash
git add tools/replay.py tests/test_replay_cli.py Makefile README.md
git commit -m "Add reproducible KIL replay command"
```

## V2 exit criteria

- All eight phase cut points are normalized with primary-source references.
- Every synthetic KTP value has modeled provenance and rationale.
- The baseline and both KIL modes consume one common event stream.
- Historical output is always labeled modeled, never validated.
- Same inputs and implementation version produce identical run IDs and hashes.
- The CLI emits an integrity-verifiable run bundle suitable for paper figures.
- Full repository validation and preserved-source checks pass.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
