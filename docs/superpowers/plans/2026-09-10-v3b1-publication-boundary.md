# V3B-1 Publication Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make V3B-1 complete at its accepted local-Envoy boundary, place publication immediately after it, and present the deferred V3B-2 work as post-publication **V4 Future** while retaining detailed V3B-1 validation evidence.

**Architecture:** Documentation tests define one current-facing milestone and claim contract. Canonical Markdown status and paper sources plus the hand-authored architecture presentation implement that contract; a repository-owned SVG replaces the untracked screenshot as the durable milestone visual. Historical evidence, plans, schemas, implementation branches, and bundle bytes remain unchanged.

**Tech Stack:** Python `unittest`, Markdown, self-contained generated HTML readers, HTML/CSS, SVG, Git.

---

### Task 1: Lock the publication contract with failing tests

**Files:**
- Create: `tests/test_v3b1_publication_status.py`

- [ ] **Step 1: Add the current-facing source and milestone assertions**

```python
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94"


class V3B1PublicationStatusTest(unittest.TestCase):
    def source(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_current_status_declares_the_bounded_completion(self):
        for relative in ("README.md", "docs/lab/V3-PROGRESS.md",
                         "docs/paper/kinetic-infrastructure.md"):
            with self.subTest(relative=relative):
                text = self.source(relative)
                self.assertIn("V3B-1 Complete", text)
                self.assertIn("local_envoy_boundary", text)
                self.assertIn(RUN_ID, text)
                self.assertIn("not proof that KIL would have prevented", text)

    def test_milestone_visual_places_publication_before_v4_future(self):
        text = self.source("docs/architecture/v3-publication-roadmap.svg")
        labels = [text.index(label) for label in
                  ("V1", "V2", "V3A", "V3B-1 Complete", "Publication", "V4 Future")]
        self.assertEqual(labels, sorted(labels))
        self.assertNotIn("V3B-2", text)

    def test_additional_validation_retains_exact_accepted_facts(self):
        text = self.source("docs/lab/V3-PROGRESS.md")
        for fact in (RUN_ID, "permit / permit / deny", "200 / 200 / 403",
                     "1 / 1 / 0", "all nine authoritative", "15 owned containers",
                     "six networks", "not_promoted"):
            with self.subTest(fact=fact):
                self.assertIn(fact, text)

    def test_current_architecture_calls_cluster_work_v4_future(self):
        text = self.source("docs/architecture/hybrid-two-timescale-architecture.html")
        self.assertIn("Current · V3B-1 Complete", text)
        self.assertIn("Post-publication · V4 Future", text)
        self.assertNotIn("Future · V3B-2 Kind/Calico", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_v3b1_publication_status -v
```

Expected: FAIL because the new SVG is absent and current sources do not yet use
the approved exact milestone language.

- [ ] **Step 3: Commit the failing contract test**

```bash
git add tests/test_v3b1_publication_status.py
git commit -m "test: define V3B-1 publication status"
```

### Task 2: Update canonical repository and validation status

**Files:**
- Modify: `README.md:15-90`
- Modify: `README.md:191-215`
- Modify: `docs/lab/V3-PROGRESS.md:46-55`
- Modify: `docs/lab/V3-PROGRESS.md:219-247`
- Modify: `docs/lab/V3-PROGRESS.md:332-344`

- [ ] **Step 1: Replace the repository status lead**

Use this bounded status language in `README.md`:

```markdown
## Status — V3B-1 Complete

KIL has accepted observed evidence at the `local_envoy_boundary`. The accepted
run is `v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94`.
It reproduced `permit / permit / deny`, HTTP `200 / 200 / 403`, and target
markers `1 / 1 / 0`, with one attempt per track and no retry.

This is not proof that KIL would have prevented the historical Hugging Face
incident. Publication follows this bounded completion. Kind/Calico,
NetworkPolicy, cluster transport, repetition, and performance are
post-publication **V4 Future** work.
```

Retain the existing detailed topology, evidence, and historical paragraphs
below the lead; replace only contradictory pending/current-future sentences.

- [ ] **Step 2: Mark the validation record complete without changing evidence**

Change the V3 progress heading to `## V3B-1 Complete` and insert:

```markdown
### Additional validation detail

The accepted run remains an observed intermediate result under immutable
`promotion_status=not_promoted` evidence. Phase completion does not rewrite that
record. It preserves all nine authoritative service sources, one attempt per
track with no retry, exact absence of all 15 owned containers and six networks
before publication, equal pseudonymous foreign-resource snapshots, passing
checksums, and offline-presenter acceptance.
```

Replace the current-facing closing roadmap with:

```markdown
Publication proceeds from this accepted local-Envoy boundary. The isolated
Kind/Calico, NetworkPolicy, cluster failure-matrix, repetition, and performance
work previously planned as V3B-2/V3C is now post-publication **V4 Future**.
Historical records retain their original phase names.
```

- [ ] **Step 3: Run the focused content assertions**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_v3b1_publication_status.V3B1PublicationStatusTest.test_current_status_declares_the_bounded_completion \
  tests.test_v3b1_publication_status.V3B1PublicationStatusTest.test_additional_validation_retains_exact_accepted_facts -v
```

Expected: the additional-validation assertion passes; the full current-status
assertion remains RED until the paper changes in Task 3.

- [ ] **Step 4: Commit repository and validation status**

```bash
git add README.md docs/lab/V3-PROGRESS.md
git commit -m "docs: mark V3B-1 boundary complete"
```

### Task 3: Update the paper and durable milestone visual

**Files:**
- Modify: `docs/paper/kinetic-infrastructure.md:1-60`
- Modify: `docs/paper/kinetic-infrastructure.md:400-465`
- Modify: `docs/architecture/hybrid-two-timescale-architecture.html:270-410`
- Create: `docs/architecture/v3-publication-roadmap.svg`
- Modify: `README.md:15-45`

- [ ] **Step 1: Update the paper status and gate table**

Set the paper status to `V3B-1 Complete — accepted observed local-Envoy
boundary`. In the current-results section include the accepted run ID,
`local_envoy_boundary`, and the sentence:

```markdown
This result is not proof that KIL would have prevented the historical incident;
cluster validation and performance remain post-publication V4 Future work.
```

Replace the gate-table tail with:

```markdown
| V3B-1 Complete — local Envoy boundary | Accepted observed evidence joins exact driver, decision, Envoy, and target records and satisfies exact teardown. |
| Publication | Publish the bounded V1–V3B-1 argument, artifacts, validation detail, and limitations. |
| V4 Future — Kind/Calico and measurement | NetworkPolicy isolation, cluster transport, failure cases, repetition, and performance require future execution. |
```

- [ ] **Step 2: Update the existing architecture presentation**

Replace stale pending text with the accepted run outcome and change the two rail
cards to:

```html
<strong>Current · V3B-1 Complete</strong>
<span>Accepted observed local-Envoy evidence; publication boundary reached.</span>
<strong>Post-publication · V4 Future</strong>
<span>Kind/Calico, NetworkPolicy, cluster failures, repetition, and performance.</span>
```

Keep `V3B-2` only where the HTML explicitly labels historical plan provenance;
the current-facing future card must use `V4 Future`.

- [ ] **Step 3: Create the durable roadmap SVG**

Create a self-contained SVG with six ordered nodes and accessible text:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1400 720" role="img"
     aria-labelledby="title description">
  <title id="title">KIL evidence and publication roadmap</title>
  <desc id="description">V1, V2, V3A, V3B-1 Complete, Publication, then V4 Future.</desc>
  <style>
    .background { fill: #0f151d; }
    .path { fill: none; stroke: #63adf2; stroke-width: 6; }
    .complete { fill: #63adf2; stroke: #8ec7ff; stroke-width: 3; }
    .future { fill: #0f151d; stroke: #526273; stroke-width: 3; }
    .label { fill: #f2f6fa; font: 700 22px system-ui, sans-serif; text-anchor: middle; }
    .caption { fill: #b8c5d1; font: 16px system-ui, sans-serif; text-anchor: middle; }
  </style>
  <rect class="background" width="1400" height="720"/>
  <path class="path" d="M150 570 L370 470 L590 370 L810 270 L1030 170 L1250 90"/>
  <g><circle class="complete" cx="150" cy="570" r="48"/><text class="label" x="150" y="578">V1</text><text class="caption" x="150" y="642">model invariants</text></g>
  <g><circle class="complete" cx="370" cy="470" r="48"/><text class="label" x="370" y="478">V2</text><text class="caption" x="370" y="542">historical replay</text></g>
  <g><circle class="complete" cx="590" cy="370" r="48"/><text class="label" x="590" y="378">V3A</text><text class="caption" x="590" y="442">modeled authorization</text></g>
  <g><circle class="complete" cx="810" cy="270" r="58"/><text class="label" x="810" y="264">V3B-1 Complete</text><text class="caption" x="810" y="286">local Envoy</text></g>
  <g><circle class="complete" cx="1030" cy="170" r="58"/><text class="label" x="1030" y="178">Publication</text><text class="caption" x="1030" y="244">current boundary</text></g>
  <g><circle class="future" cx="1250" cy="90" r="58"/><text class="label" x="1250" y="98">V4 Future</text><text class="caption" x="1250" y="164">cluster + measurement</text></g>
</svg>
```

Use only inline SVG shapes and text; do not embed scripts, remote content, fonts,
or raster data. Link the visual from the README status section.

- [ ] **Step 4: Run the complete publication-status test**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_v3b1_publication_status -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit paper and presentation changes**

```bash
git add README.md docs/paper/kinetic-infrastructure.md \
  docs/architecture/hybrid-two-timescale-architecture.html \
  docs/architecture/v3-publication-roadmap.svg
git commit -m "docs: move cluster validation to V4 Future"
```

### Task 4: Regenerate readers, record lineage, verify, review, and push

**Files:**
- Modify: generated `.htm` readers corresponding to changed tracked Markdown
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm`

- [ ] **Step 1: Append the implementation decision to specialist lineage**

Add a dated append-only entry recording the input, bounded interpretation,
confirmed status, claim rationale, exact affected artifacts, unresolved external
deployment mechanism, and the next publication gate. State that no live runtime
or evidence bundle was changed.

- [ ] **Step 2: Regenerate all required readers**

Run:

```bash
../../.venv/bin/python tools/render_markdown.py
../../.venv/bin/python tools/render_markdown.py --check
```

Expected: all tracked Markdown files have current generated `.htm` siblings.

- [ ] **Step 3: Run the bounded publication gate**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_v3b1_publication_status tests.test_v3b1_documentation \
  tests.test_markdown_html tests.test_document_citation -v
git diff --check
git status --short
```

Expected: all tests pass; diff hygiene is clean; only reviewed publication,
generated-reader, test, plan, and lineage files are present.

- [ ] **Step 4: Commit generated readers and lineage**

```bash
git add README.htm docs/lab/V3-PROGRESS.htm \
  docs/paper/kinetic-infrastructure.htm \
  docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md \
  docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm
git commit -m "docs: finalize V3B-1 publication record"
```

- [ ] **Step 5: Request independent review**

Review `main..HEAD` for claim overreach, contradictory current-facing phase
labels, missing V3B-1 detail, accidental evidence changes, and any V4 Future
work merged into the publication branch. Resolve every Critical or Important
finding and rerun Step 3.

- [ ] **Step 6: Push the publication branch and verify synchronization**

```bash
git push -u origin codex/v3b1-publication
git rev-parse HEAD
git rev-parse origin/codex/v3b1-publication
git status --short
```

Expected: local and remote hashes match and the publication worktree is clean.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
