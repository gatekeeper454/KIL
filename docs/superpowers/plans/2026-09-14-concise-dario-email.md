# Concise Dario Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the sendable Dario Amodei email to a one-minute introduction that states only Kinetic Enforcement's novel contribution and requests a private briefing.

**Architecture:** The Markdown file remains the editorial source of truth and its sibling `.htm` remains the self-contained review artifact. The repository renderer regenerates the reader and embeds the source SHA-256 so the two forms can be verified as an exact pair.

**Tech Stack:** Markdown, the repository's Python HTML renderer, `unittest`, and static shell checks.

---

### Task 1: Replace the email body

**Files:**
- Modify: `docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-email.md`

- [x] **Step 1: Replace the 401-word draft with the approved concise version**

Use the subject `Embedded evaluators need embedded enforcement`. Treat the pacing essay as shared context. Preserve the action-specific authority definition, evaluator-versus-enforcer distinction, one-sentence unilateral/bidirectional advantage, private 45-minute request, sender fields, and optional attachment note.

- [x] **Step 2: Check the editorial contract**

Run a static content check. Expected: 150–190 main-body words, no recap list of Amodei's pacing program, no geopolitical scenario bullet list, no more than two HTTPS links, and all required email fields present.

### Task 2: Regenerate and verify the reader

**Files:**
- Modify: `docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-email.htm`
- Modify: `docs/superpowers/specs/2026-09-14-kinetic-zero-trust-dario-briefing-design.htm`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm`

- [x] **Step 1: Regenerate the self-contained readers**

Run the repository renderer over the tracked sources and the eight review-draft sources. Expected: 64 readers generated with no reported problem.

- [x] **Step 2: Verify rendering and source identity**

Confirm that the email HTML has one H1, no remote runtime assets, a source SHA-256 matching the Markdown bytes, and no wide-reader class.

- [x] **Step 3: Run focused publication tests**

Run the renderer, generation, byte-preservation, tracked-sibling, and Makefile-wiring tests. Expected: 48 tests pass.

- [x] **Step 4: Record the completed editorial decision**

Append a dated specialist-lineage entry distinguishing the approved email edit from any unperformed delivery, publication, endorsement, briefing, or pilot action. Regenerate the lineage reader and repeat the source-identity check.

- [x] **Step 5: Check the working diff**

Run `git diff --check`. Expected: exit status 0 and no output.

### Task 3: Center the infrastructure-level enforcement invariant

**Files:**
- Modify: `docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-email.md`
- Modify: `docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-email.htm`
- Modify: `docs/superpowers/specs/2026-09-14-kinetic-zero-trust-dario-briefing-design.md`
- Modify: `docs/superpowers/specs/2026-09-14-kinetic-zero-trust-dario-briefing-design.htm`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm`

- [x] **Step 1: Replace the mechanism paragraph**

State that Kinetic Enforcement runs on the recipient's existing infrastructure,
is neither a product to buy nor a policy to interpret, expresses mathematics as
infrastructure and therefore behaves operationally like physics, is immutable
to the requesting AI within declared coverage, and needs to be enabled. Replace
the existing paragraph so the email remains approximately one minute long.

- [x] **Step 2: Regenerate all self-contained readers**

Run the repository renderer over the tracked sources and eight review-draft
sources. Expected: 64 readers generated with no problem.

- [x] **Step 3: Verify the amended editorial and publication contracts**

Confirm a 180–210-word body from greeting through closing, all six requested
concepts, no more than two HTTPS links, one H1, a matching source SHA-256, no
remote runtime assets, standard rather than wide layout, 48 passing focused
tests, and clean `git diff --check` output.

- [x] **Step 4: Record completion without implying deployment**

Append a specialist-lineage entry making clear that “needs to be enabled” is a
deployment proposition, not evidence that Kinetic Enforcement is already
installed or active on Anthropic infrastructure. Regenerate and verify the
lineage reader.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
