# Project-Boundary Reference Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove an unrelated project name from every current KIL-owned file while preserving KIL/KTP meaning and the maintainer's uncommitted OTCS work.

**Architecture:** Markdown remains authoritative, and the repository renderer refreshes every sibling `.htm` reader after source edits. A case-insensitive current-file search verifies the strict project boundary without retaining or reconstructing the removed name in KIL source.

**Tech Stack:** Python `unittest`, Git, Markdown, and `tools/render_markdown.py`.

---

### Task 1: Inventory the current references

**Files:**
- Inspect all current project-owned files.

- [ ] **Step 1: Run a case-insensitive current-file search**

Use the maintainer-supplied name as the literal search term while excluding Git metadata, virtual environments, tool caches, and dependency caches.

Expected: six matches across `PROJECT.md`, `PROJECT.htm`, `README.md`, `README.htm`, and the specialist-consultation Markdown/HTML pair, plus the maintainer's uncommitted OTCS lineage pair after it is restored.

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

- [ ] **Step 3: Verify generated-reader integrity**

Run: `python tools/render_markdown.py --check`

Expected: `verified 49 Markdown readers`.

- [ ] **Step 4: Verify the entire repository**

Run: `make validate` with the repository virtual environment on `PATH`.

Expected: all tests pass, all 49 readers verify, and `git diff --check` exits zero.

### Task 4: Commit and publish the isolated cleanup

**Files:**
- Stage only the plan, three Markdown rewrites, lineage entry, and generated readers.

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
