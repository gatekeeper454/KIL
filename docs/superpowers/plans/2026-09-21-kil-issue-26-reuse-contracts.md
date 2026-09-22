# KIL Issue #26 Reuse-Contract Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a source-pinned KIL R1–R9 reuse/contract matrix that lets downstream projects assess reuse without treating KIL interfaces, laboratory evidence, or ownership as open-ended guarantees.

**Architecture:** The matrix is a KIL-owned Markdown record under `docs/transition/`. Each row connects an assessed KIL module to a canonical KTP v2.1.0 contract, marks the actual reuse disposition and non-guarantees, and names the only remaining compatibility gate. It explicitly separates protocol behavior from Envoy transport and deployment adapters, and makes the two-clock/evidence limits normative for this coordination record.

**Tech Stack:** Markdown, generated self-contained HTML reader, the repository Markdown-renderer and validation targets, GitHub issue comment.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

---

### Task 1: Write the source-pinned R1–R9 matrix

**Files:**
- Create: `docs/transition/KIL-R1-R9-REUSE-CONTRACTS.md`

- [ ] **Step 1: Define scope and non-commitment boundaries**

State the assessed KIL source pin, canonical KTP `v2.1.0` basis, authorship/Apache-2.0 attribution boundary, and that a reuse decision is neither a stable public-API promise nor a production-readiness claim.

- [ ] **Step 2: Record R1–R9 against actual KIL source**

Use the following row anchors and source surfaces:

| ID | Assessed KIL surface |
| --- | --- |
| R1 | `src/kil/ext_authz_http.py`, `src/kil/live_authz.py` |
| R2 | `src/kil/q_state.py` |
| R3 | `src/kil/engine.py`, `src/kil/decay.py`, `src/kil/domain.py` |
| R4 | signed-state claims and modeled scenario/history inputs |
| R5 | `src/kil/reference_gateway.py`, `src/kil/target_http.py` |
| R6 | `src/kil/evidence.py`, recorder/witness code and V3 verifier |
| R7 | relevant unit/integration fixtures |
| R8 | Envoy adapter and isolated lab topology |
| R9 | provider/deployment connectors |

For each row, include a disposition, supported reuse scope, excluded scope, evidence class and one concrete acceptance gate. Never assert a live provider, production durability, target atomicity, measured latency or historical prevention when the assessed source does not establish it.

- [ ] **Step 3: Add cross-cutting contract limits**

Document the signed-state refresh versus per-action evaluation distinction; restrict local evidence to reducing/withholding authority; require deployed latency measurement; and distinguish modeled replay, observed local Envoy boundary evidence and future live deployment evidence.

### Task 2: Render and verify documentation

**Files:**
- Create: `docs/transition/KIL-R1-R9-REUSE-CONTRACTS.htm`
- Create: `docs/superpowers/plans/2026-09-21-kil-issue-26-reuse-contracts.htm`

- [ ] **Step 1: Generate readers**

Run: `make readers PYTHON=.venv/bin/python`

Expected: generated `.htm` siblings for the new Markdown documents with no manual HTML edits.

- [ ] **Step 2: Verify reader synchronization and focused documentation tests**

Run: `make check-readers PYTHON=.venv/bin/python && .venv/bin/python -m unittest tests.test_markdown_html tests.test_transition_record -v`

Expected: no stale/missing readers and passing focused tests.

### Task 3: Record and publish the reconciliation

**Files:**
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- GitHub update: `gatekeeper454/KIL#26`

- [ ] **Step 1: Append the source and decision record**

Record the R1–R9 dispositions, non-runtime scope, evidence limits, remaining unresolved interfaces and next deployment gate in the append-only specialist lineage log.

- [ ] **Step 2: Commit the scoped documentation change**

Run: `git add docs/transition/KIL-R1-R9-REUSE-CONTRACTS.md docs/transition/KIL-R1-R9-REUSE-CONTRACTS.htm docs/superpowers/plans/2026-09-21-kil-issue-26-reuse-contracts.md docs/superpowers/plans/2026-09-21-kil-issue-26-reuse-contracts.htm docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md && git commit -m "docs: record KIL reuse contracts"`

Expected: one commit containing only the matrix, readers, plan and lineage entries; exclude the pre-existing untracked HTML artifact.

- [ ] **Step 3: Publish a concise issue update**

After the branch is pushed, comment on #26 with the commit link, the nine dispositions, the two-clock/evidence limits, and the still-open deployment-readiness gate. Do not close #26 unless its acceptance evidence is fully demonstrated.

## Self-review

- Every R1–R9 row maps to an actual KIL surface and an explicit KTP basis.
- The matrix does not promise source stability, protocol adoption, deployment readiness, or production/historical-prevention evidence.
- The matrix identifies only demonstrated missing interfaces, not speculative Component Dev backlog items.
- Every created Markdown file has a generated reader, and the untracked incident HTML artifact is excluded from the commit.
