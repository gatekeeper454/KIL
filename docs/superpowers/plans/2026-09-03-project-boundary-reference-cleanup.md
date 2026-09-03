# Project-Boundary Reference Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove an unrelated project name from every current KIL-owned file while preserving KIL/KTP meaning and the maintainer's uncommitted OTCS work.

**Architecture:** Markdown remains authoritative, and the repository renderer refreshes every sibling `.htm` reader after source edits. A small tracked-file boundary test prevents the removed name from returning without storing it contiguously in the test itself.

**Tech Stack:** Python `unittest`, Git, Markdown, and `tools/render_markdown.py`.

---

### Task 1: Add the project-boundary regression test

**Files:**
- Create: `tests/test_project_boundaries.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProjectBoundaryTests(unittest.TestCase):
    def test_unrelated_project_name_is_absent_from_tracked_files(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout.split(b"\0")
        needle = ("shadow" + "claw").casefold()
        offenders: list[str] = []
        for encoded_path in tracked:
            if not encoded_path:
                continue
            relative = encoded_path.decode("utf-8")
            try:
                contents = (ROOT / relative).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if needle in contents.casefold():
                offenders.append(relative)
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify the test fails for the existing tracked sources and readers**

Run: `python -m unittest tests.test_project_boundaries -v`

Expected: FAIL listing `PROJECT.md`, `PROJECT.htm`, `README.md`, `README.htm`, and the specialist-consultation Markdown/HTML pair.

### Task 2: Rewrite the three authoritative Markdown sources

**Files:**
- Modify: `PROJECT.md`
- Modify: `README.md`
- Modify: `docs/checkpoints/2026-08-24-specialist-consultation.md`

- [ ] **Step 1: Replace the two charter references with KIL-only wording**

Use `Repository boundary: KIL owns detection and enforcement behavior while preserving provenance.` and retain `Modifying KTP upstream specifications.` as the upstream-specification non-goal.

- [ ] **Step 2: Replace the README boundary paragraph**

Use: `KIL is an enforcer and experiment harness. It accepts KTP Risk Factor telemetry through stable, documented interfaces and keeps enforcement within KIL-controlled infrastructure.`

- [ ] **Step 3: Replace the checkpoint decision**

Use: `KIL is an enforcement and experiment harness. It accepts KTP Risk Factor telemetry through stable, documented interfaces and owns enforcement behavior.`

### Task 3: Regenerate and verify self-contained readers

**Files:**
- Modify: `PROJECT.htm`
- Modify: `README.htm`
- Modify: `docs/checkpoints/2026-08-24-specialist-consultation.htm`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm`
- Modify: `docs/superpowers/plans/2026-09-03-project-boundary-reference-cleanup.htm`

- [ ] **Step 1: Append the implementation result to the specialist lineage**

Record the maintainer direction, exact KIL-only interpretation, validation evidence, changed artifacts, current-file-only scope, and synchronization gate without spelling the removed name.

- [ ] **Step 2: Regenerate all readers**

Run: `python tools/render_markdown.py`

Expected: `generated 49 Markdown readers`.

- [ ] **Step 3: Verify the regression test passes**

Run: `python -m unittest tests.test_project_boundaries -v`

Expected: PASS.

- [ ] **Step 4: Verify generated-reader integrity**

Run: `python tools/render_markdown.py --check`

Expected: `verified 49 Markdown readers`.

- [ ] **Step 5: Verify the entire repository**

Run: `make validate` with the repository virtual environment on `PATH`.

Expected: all tests pass, all 49 readers verify, and `git diff --check` exits zero.

### Task 4: Commit and publish the isolated cleanup

**Files:**
- Stage only the plan, regression test, three Markdown rewrites, lineage entry, and generated readers.

- [ ] **Step 1: Confirm no current tracked file contains the removed name**

Run a case-insensitive `git grep` using the name supplied by the maintainer.

Expected: no output and exit status 1.

- [ ] **Step 2: Commit and push the cleanup branch**

Run: `git commit -m "docs: remove unrelated project references"` followed by `git push -u origin codex/remove-unrelated-project-references`.

Expected: the remote feature branch resolves to the local cleanup commit.

### Task 5: Integrate without committing OTCS work

**Files:**
- Preserve as uncommitted: `Inputs/coordinate-record-template.yaml`
- Narrowly modify as uncommitted: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Regenerate as uncommitted: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm`

- [ ] **Step 1: Stash the normal checkout's OTCS changes, fast-forward `main`, and restore them**

Use a uniquely named stash including untracked files. Resolve only the append-only lineage overlap, retaining the cleanup entries and the OTCS entry.

- [ ] **Step 2: Rewrite the OTCS entry's one unrelated-project clause**

End the sentence after `with KTP`, leaving all other OTCS content byte-preserved, then regenerate its `.htm` partner.

- [ ] **Step 3: Push and verify synchronization**

Push `main`, fetch `origin/main`, and verify local `main`, `origin/main`, and the remote head are the same cleanup commit. Confirm the normal checkout still has only the intended uncommitted OTCS files and that a project-owned-file search finds zero occurrences.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
