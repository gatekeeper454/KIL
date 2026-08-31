# V3B-1 Transcript-Driven Integration Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local Envoy harness readiness, request provenance, evidence freeze, and exact teardown contracts strong enough for a zero-request smoke cycle and one accepted live boundary proof without changing KIL authorization behavior.

**Architecture:** Add a small pure harness-contract module for closed transcript parsing and provenance records, then integrate it into the existing lifecycle controller. All behavior changes are test-first and limited to host-side orchestration and evidence collection; KIL state, decision, Envoy policy, and target semantics remain frozen.

**Tech Stack:** Python 3.12.13, `unittest`, `http.client`, Docker CLI 29.7.2, Colima 0.10.3, canonical JSON/JSONL, SHA-256, GitHub CLI.

**Execution record:** Tasks 1–5 completed across commits `63a8bf3` through
`14ed92d` and specialist lineage T-074 through T-090. The commit commands below
remain the original planned checkpoints; review-driven corrections required
additional test-first commits without changing KIL, authorization, Envoy, or
target semantics.

---

### Task 1: Lock sanitized transcript and pure harness contracts

**Files:**

- Create: `tools/v3b1_harness_contract.py`
- Create: `tests/fixtures/v3b1-integration-contract.json`
- Modify: `tests/test_v3b1_local_envoy.py`

- [x] **Step 1: Add RED tests for the closed transcript schema**

Add tests that load one canonical fixture object with explicit `observed` or
`reconstructed` provenance, reject unknown fields and secret-bearing values,
and parse full-ID container/network inventory rows. Assertions must require
64-hex IDs, exact names, duplicate rejection, and no stderr interpretation.

- [x] **Step 2: Run the focused tests and verify the expected import failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_v3b1_local_envoy -v
```

Expected: new tests fail because `tools.v3b1_harness_contract` does not exist.

- [x] **Step 3: Implement only the pure closed validators**

Implement frozen records for request-failure provenance, source collection
status, and inventory entries. Implement canonical fixture loading with
duplicate-key rejection and closed field sets. Do not import or change KIL
engine, Q-state, authorization, Envoy, or target modules.

- [x] **Step 4: Verify GREEN and commit**

Run the focused suite, `py_compile` on both harness files, and `git diff --check`.
Commit:

```bash
git add tools/v3b1_harness_contract.py tests/fixtures/v3b1-integration-contract.json tests/test_v3b1_local_envoy.py
git commit -m "Lock the V3B-1 integration transcript contract"
```

### Task 2: Add non-consuming readiness and request-stage provenance

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Modify: `tests/test_v3b1_local_envoy.py`

- [x] **Step 1: Add RED readiness tests**

Use injected connection objects to prove all three `connect()` calls occur
before any `claim_request_attempt`, no `request()` occurs during readiness,
failed readiness leaves all request states `not_attempted`, and every opened
socket closes on failure.

- [x] **Step 2: Add RED stage-provenance tests**

Inject failures separately from `request()`, `getresponse()`, and `read()`.
Require the closed stage, allowlisted exception class, numeric errno/name,
monotonic ordering, bytes-may-have-been-sent flag, attempt count one, no retry,
and absence of raw messages or secrets.

- [x] **Step 3: Verify RED, then implement minimal readiness/provenance behavior**

Run each new test alone to observe the intended failure before changing
production code. Integrate the already-connected sockets into `run()` and
extend journal validation without changing request facts or authorization data.

- [x] **Step 4: Verify GREEN and commit**

Run the full focused controller suite, compilation, and diff hygiene. Commit:

```bash
git add tools/v3b1_local_envoy.py tests/test_v3b1_local_envoy.py
git commit -m "Add non-consuming V3B-1 gateway readiness"
```

### Task 3: Freeze evidence before tmpfs teardown

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Modify: `tools/v3b1_harness_contract.py`
- Modify: `tests/test_v3b1_local_envoy.py`

- [x] **Step 1: Add RED ordering and independent-leg tests**

Prove Envoys stop before collection, authz/target containers remain running
during ledger attestation and copy, source results are persisted before those
containers stop, and one missing/copy-error/malformed leg cannot prevent all
other legs from being preserved or exact cleanup from continuing.

- [x] **Step 2: Add RED zero-byte and malformed-byte tests**

Require positive in-container size/hash observation for a zero-byte `copied`
result. Require missing to remain missing, copy mismatch to become `copy_error`,
and malformed raw bytes to be retained privately with `malformed` status.

- [x] **Step 3: Verify RED, then implement the source-freeze state machine**

Use a closed JSON result from an exact `docker exec` Python ledger probe,
compare the host copy to the observed size/hash, and record all nine source
results independently. Incomplete sources produce no valid joins and a
nonpromotable bundle while teardown continues.

- [x] **Step 4: Verify GREEN and commit**

Run focused tests, compilation, and diff hygiene. Commit:

```bash
git add tools/v3b1_local_envoy.py tools/v3b1_harness_contract.py tests/test_v3b1_local_envoy.py
git commit -m "Freeze V3B-1 evidence before service teardown"
```

### Task 4: Replace error-text absence with exact inventories

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Modify: `tools/v3b1_harness_contract.py`
- Modify: `tests/test_v3b1_local_envoy.py`

- [x] **Step 1: Add RED removal and recovery tests**

Replay successful removal followed by Docker `network <id> not found` and prove
stderr is irrelevant. Require successful closed inventories to establish
absence, expected remaining-object equality after every removal, empty network
membership before network deletion, and no repeated deletion after a crash.

- [x] **Step 2: Add RED ambiguity tests**

Reject inventory command failures, malformed or duplicate JSON, shortened IDs,
wrong names, unexpected remaining objects, and nonempty network membership.

- [x] **Step 3: Verify RED, then integrate inventory-based recovery**

Replace `_docker_object_exists` prose matching with closed container/network
inventories. Preserve exact-ID delete commands, durable intents, and the rule
that no unrecorded object is mutated.

- [x] **Step 4: Verify GREEN and commit**

Run focused tests, full repository validation, compilation, and diff hygiene.
Commit:

```bash
git add tools/v3b1_local_envoy.py tools/v3b1_harness_contract.py tests/test_v3b1_local_envoy.py
git commit -m "Verify V3B-1 teardown through exact inventories"
```

### Task 5: Independently review the complete harness

**Files:**

- Modify if required by review: harness source/tests only

- [x] **Step 1: Run spec-compliance review**

Require line-by-line confirmation against
`docs/superpowers/specs/2026-08-30-v3b1-integration-contract-design.md`, including
the frozen KIL-semantics boundary.

- [x] **Step 2: Resolve every spec issue test-first and re-review**

No Critical or Important issue may remain.

- [x] **Step 3: Run code-quality and security-boundary review**

Review secret exclusion, journal closure, crash recovery, command construction,
unsafe path handling, exact ownership, and claim-language boundaries.

- [x] **Step 4: Run fresh static verification**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python -m py_compile tools/v3b1_local_envoy.py tools/v3b1_harness_contract.py
git diff --check
```

### Task 6: Execute the zero-request live smoke gate

**Files:**

- Modify: `docs/lab/V3-PROGRESS.md`
- Modify: `artifacts/generated/v3b1-task6-live-status.md` (ignored live board)
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

- [x] **Step 1: Record and, if necessary, temporarily pause foreign runtime state**

Capture the exact pre-run `default` Colima state. Do not alter it unless needed
for the dedicated profile; if paused, restore the exact configuration and
status after the KIL cycle.

- [x] **Step 2: Run `preflight`, `up`, then `down` without `run`**

Use the exact committed implementation identity. Confirm no request intent,
request send, authz decision, or target marker occurred.

- [ ] **Step 3: Verify smoke evidence and exact absence**

Verify public checksums, nonpromotable classification, one bundle/archive,
recorded object absence, dedicated profile absence, restored foreign profile,
and unchanged global Docker context.

- [x] **Step 4: Record the blocked smoke result**

Commit only public-safe evidence references and documentation. Preserve raw
runtime journals and failed runs under ignored private paths.

Attempted on 2026-08-30 from public source
`47c0614d49ec1a7484cdefd04cc5d080adc73ca2`. The nonpromotable smoke run was
`v3b1-1db8b5914ce26e2e6c60e74124bcc1b2c9ed66b7dd68c2d3cf4ea1bc0d18c9b3`;
all public evidence JSONLs were empty, checksums and exact teardown passed, and
the foreign profile was restored. Three Envoy sources were copied, but six
authorization and target ledger copies failed after zero-byte in-container
observations. The failure bundle is nonpromotable and does not independently
prove service-source absence. Correct the exact-byte export and repeat Task 6;
Task 7 remains prohibited.

### Task 7: Execute one accepted local Envoy proof and presenter bundle

**Files:**

- Modify: `docs/lab/V3-PROGRESS.md`
- Modify: `README.md`
- Modify: `docs/paper/kinetic-infrastructure.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Generate: `artifacts/generated/v3b1-local-envoy/<run-id>/`

- [ ] **Step 1: Run a fresh clean preflight and one `up`/`run`/`down` cycle**

Never retry after request intent. Any ambiguity remains nonpromotable and is
preserved privately.

- [ ] **Step 2: Verify the accepted proof**

Require `permit / permit / deny`, markers `1 / 1 / 0`, valid joins, complete
sources, checksums, exact teardown, restored foreign runtime state, and the
`local_envoy_boundary` claim only.

- [ ] **Step 3: Generate and inspect the presenter-facing `live.html`**

The visualization must derive only from accepted JSONL records and remain an
observation surface rather than evidence authority. Run the read-only offline
`view --bundle` verifier and accept only the exact presenter path it returns.

- [ ] **Step 4: Commit the result references and public bundle**

After `view` succeeds and a closed checksum and secret review passes, stage only
the exact accepted directory:

```bash
git add -f artifacts/generated/v3b1-local-envoy/<accepted-run-id>/
```

Never force-add `artifacts/generated/`, the V3B-1 parent, a wildcard, a failed
run, or `live.html` alone. Commit the presenter only with its exact JSONL,
manifest, raw sources, summary, and `SHA256SUMS`, and record the run ID and
implementation commit in the progress record.

### Task 8: Publish, merge, synchronize, and verify backup readiness

**Files:**

- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

- [ ] **Step 1: Run final full verification and independent review**

Require all tests, compilation, diff hygiene, public checksums, and clean secret
scan of the pending Git diff.

- [ ] **Step 2: Push the feature branch and create/update the GitHub PR**

Wait for required checks and resolve failures before merge.

- [ ] **Step 3: Merge without force-push and fast-forward local `main`**

Read back `origin/main`, GitHub's merged commit, and local `main`; all must be
the same commit.

- [ ] **Step 4: Verify public/local cleanliness for offline backup**

Run fresh tests on local `main`, verify every tracked public checksum, confirm
the tracked tree is clean, and report ignored private paths separately so the
user can decide whether to include them in the offline backup.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
