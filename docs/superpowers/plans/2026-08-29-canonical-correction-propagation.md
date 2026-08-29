# Canonical KIL Correction Propagation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propagate approved KIL terminology, evidence rules, two-timescale semantics, and corrected mathematics into every mutable canonical paper and architecture artifact while preserving the original source drafts byte-for-byte.

**Architecture:** A repository invariant test defines the canonical semantic contract. The main paper becomes the unified narrative, mathematical, incident, and lab companion asset. The HTML visual is revised to show the slower signed-state loop and faster action-enforcement loop separately from the offline and live execution rails.

**Tech Stack:** Python 3.12 standard library, `unittest`, Markdown, semantic HTML/CSS, repository `make validate` checks.

---

### Task 1: Encode canonical semantic invariants

**Files:**
- Create: `tests/test_canonical_semantics.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "docs/paper/kinetic-infrastructure.md"
ARCHITECTURE = ROOT / "docs/design-drafts/hybrid-two-timescale-architecture.html"


class CanonicalSemanticsTest(unittest.TestCase):
    def test_paper_uses_corrected_model_and_evidence_contract(self):
        text = PAPER.read_text(encoding="utf-8")
        for marker in (
            "signed, short-lived composite KTP enforcement state",
            "weighted diagonal standardized distance",
            "signed-state-only",
            "signed state plus local reduction",
            "observed",
            "modeled",
            "validated",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("E_i,c", text)
        self.assertNotIn("weighted Mahalanobis distance", text)

    def test_architecture_separates_timescales_from_execution_rails(self):
        text = ARCHITECTURE.read_text(encoding="utf-8")
        for marker in (
            "Authoritative signed-state loop",
            "Fast enforcement loop",
            "Execution rails—not timescales",
            "Signed Qᵢ,c",
            "Local reducing-only overlay",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("Ephemeral charge Qᵢ,c", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify the tests fail for missing corrected content**

Run: `PYTHONPATH=src python3 -m unittest tests.test_canonical_semantics -v`

Expected: both tests fail because the canonical paper and visual do not yet
contain the required corrected markers.

- [ ] **Step 3: Commit the red tests with the completed propagation work**

The red tests remain uncommitted until Tasks 2 and 3 make them pass, so the
repository branch is never published in a knowingly failing state.

### Task 2: Consolidate the corrected canonical paper

**Files:**
- Modify: `docs/paper/kinetic-infrastructure.md`

- [ ] **Step 1: Add the unified argument and architecture**

Add sections covering the ambient-enforcement thesis, the KTP/KIL extension
boundary, the authoritative signed-state loop, the fast enforcement loop, and
the offline/live execution rails. State that local evidence is reducing-only
and that testing the overlay does not yet standardize it.

- [ ] **Step 2: Add the corrected trust-decay model**

Use `Q_i,c` for the KIL composite state, reserve `E(environment)` for the KTP
envelope, call the first profile a weighted diagonal standardized distance, and
state that positive replenishment occurs only through the authoritative loop
after confirmed behavior.

- [ ] **Step 3: Add the source-cited Hugging Face worked example**

Integrate the phase sequence as a modeled counterfactual. Distinguish observed
incident facts from synthetic KTP signals and phrase decisions conditionally on
the declared sensor, placement, freshness, state, and threshold assumptions.

- [ ] **Step 4: Add lab linkage, limitations, and references**

Describe the baseline and two KIL modes, acceptance gates, run IDs, and the
restriction that only locally reproduced outcomes may be labeled validated.
Retain all official KTP and Hugging Face citations.

- [ ] **Step 5: Run the paper invariant test**

Run: `PYTHONPATH=src python3 -m unittest tests.test_canonical_semantics.CanonicalSemanticsTest.test_paper_uses_corrected_model_and_evidence_contract -v`

Expected: PASS.

### Task 3: Correct the hybrid two-timescale visual

**Files:**
- Modify: `docs/design-drafts/hybrid-two-timescale-architecture.html`
- Modify: `tests/test_consultation_checkpoint.py`

- [ ] **Step 1: Revise the semantic structure**

Show the authoritative signed-state loop and fast enforcement loop as distinct
horizontal layers. Show offline replay and live validation below them with the
explicit label “Execution rails—not timescales.” Replace “Ephemeral charge”
with “Signed Qᵢ,c” and display the local reducing-only overlay as optional and
incapable of increasing authority.

- [ ] **Step 2: Strengthen the existing architecture test**

Add these assertions to
`test_architecture_visual_is_saved_with_its_governance_boundary`:

```python
self.assertIn("Authoritative signed-state loop", text)
self.assertIn("Fast enforcement loop", text)
self.assertIn("Execution rails—not timescales", text)
self.assertIn("Local reducing-only overlay", text)
```

- [ ] **Step 3: Run the visual invariant tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_canonical_semantics.CanonicalSemanticsTest.test_architecture_separates_timescales_from_execution_rails tests.test_consultation_checkpoint.ConsultationCheckpointTest.test_architecture_visual_is_saved_with_its_governance_boundary -v`

Expected: PASS.

### Task 4: Verify provenance and repository integrity

**Files:**
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

- [ ] **Step 1: Append the completed propagation decision**

Record the founder authorization, mutable artifacts changed, preserved drafts
left untouched, invariant tests added, remaining questions, and the next gate.

- [ ] **Step 2: Run the complete verification suite**

Run: `make validate`

Expected: all unit tests pass and `git diff --check` reports no errors.

Run: `shasum -a 256 -c research/source-material/SHA256SUMS`

Expected: every preserved source reports `OK`.

- [ ] **Step 3: Inspect the final diff**

Run: `git diff --check && git status --short && git diff --stat`

Expected: only the plan, canonical paper, architecture visual, semantic tests,
consultation test, and specialist lineage are changed.

- [ ] **Step 4: Commit and push**

```bash
git add docs/superpowers/plans/2026-08-29-canonical-correction-propagation.md \
  docs/paper/kinetic-infrastructure.md \
  docs/design-drafts/hybrid-two-timescale-architecture.html \
  docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md \
  tests/test_canonical_semantics.py \
  tests/test_consultation_checkpoint.py
git commit -m "Propagate canonical KIL corrections"
git push origin main
```

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
