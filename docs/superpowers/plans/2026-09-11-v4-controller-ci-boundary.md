# V4 Controller CI Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a truthful green publication gate by deferring exactly the unfinished V4 controller lifecycle methods while keeping them explicitly runnable.

**Architecture:** Add one opt-in test decorator at the V4 integration-test boundary, lock its exact application with an independent guard test, and expose a dedicated Make target. Production code, evidence, runtime state, and completed tests remain unchanged.

**Tech Stack:** Python `unittest`, GNU Make, existing Markdown reader generator.

---

### Task 1: Lock the exact deferred test boundary

**Files:**
- Create: `tests/test_v4_future_controller_gate.py`
- Modify: `tests/test_v3b2_controller.py`

- [ ] **Step 1: Write the failing boundary test**

Create a test that imports `tests.test_v3b2_controller`, compares the methods
carrying `__unittest_skip__` with the exact 16-method CI failure set, and checks
that at least one completed controller safety test is not skipped.

- [ ] **Step 2: Verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v4_future_controller_gate -v
```

Expected: FAIL because no methods yet carry the V4 Future deferral marker.

- [ ] **Step 3: Add the minimal opt-in decorator**

Add an environment-exact `v4_future` decorator and apply it only to the 16
methods named in the regression test. The skip reason must identify the pending
V4 proof graph and the opt-in variable.

- [ ] **Step 4: Verify GREEN and retained coverage**

Run the boundary test, then run default discovery for
`tests.test_v3b2_controller`. Expected: the boundary test passes; the 16 methods
are skipped; all other methods pass.

- [ ] **Step 5: Commit**

Commit the boundary test and exact decorators as one logical checkpoint.

### Task 2: Expose the deferred suite and restore the release gate

**Files:**
- Modify: `Makefile`
- Modify: `tests/test_v4_future_controller_gate.py`

- [ ] **Step 1: Extend the boundary test for the Make target**

Assert that `Makefile` declares `v4-future-controller-test`, sets
`KIL_RUN_V4_FUTURE_TESTS=1`, and directly names the controller test class.

- [ ] **Step 2: Verify RED**

Run the boundary test. Expected: FAIL because the dedicated target is absent.

- [ ] **Step 3: Add the Make target**

Add the target to `.PHONY` and help, depend on `check-python`, and run:

```bash
KIL_RUN_V4_FUTURE_TESTS=1 PYTHONPATH=src $(PYTHON) -m unittest tests.test_v3b2_controller.V3B2ControllerTest -v
```

- [ ] **Step 4: Verify the boundary and deferred signal**

Run the boundary test and a single deferred method once with the opt-in variable.
Expected: the guard passes; the deferred method runs rather than reporting a
skip and reproduces its pending proof failure.

- [ ] **Step 5: Commit**

Commit the Make target and guard extension.

### Task 3: Record, verify, publish, and merge

**Files:**
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Regenerate: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm`
- Generate: readers for this specification and plan

- [ ] **Step 1: Append the CI-boundary decision**

Record the failed CI evidence, selected quarantine, exact scope, and V4 resume
gate in the append-only specialist lineage.

- [ ] **Step 2: Generate and check readers**

Run `../../.venv/bin/python tools/render_markdown.py` followed by its `--check`
mode. Expected: all tracked Markdown readers are current.

- [ ] **Step 3: Run full local validation**

Run `make validate`, the 70-test publication gate, and `git diff --check`.
Expected: all default tests pass, 58 plus the new readers verify, and the
worktree is clean after the final commit.

- [ ] **Step 4: Commit and push**

Commit the lineage/readers, push `codex/v3b1-publication`, and verify the remote
hash matches local HEAD.

- [ ] **Step 5: Merge PR #23**

Wait for GitHub checks, merge only after they pass, and verify `origin/main`
contains the PR merge commit. Preserve the local dirty `main` checkout and the
publication worktree.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
