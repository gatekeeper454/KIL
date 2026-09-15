# Dario Kinetic Enforcement Briefing Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Produce a sendable email, one-page executive brief, direct private memo, and technical proposal that present Kinetic Enforcement as the ultimate fail-safe complement to Dario Amodei's pace-the-frontier program.

**Architecture:** Four Markdown sources share one terminology and evidence contract but remain independently understandable. The repository renderer generates each as a source-bound, self-contained `.htm`; the technical proposal opts into the scoped wide-reader layout, while the shorter documents retain the standard print-oriented reader.

**Tech Stack:** Markdown, Python 3.12, the repository's deterministic `markdown-it-py` renderer, `unittest`, standard-library HTML parsing, and browser viewport inspection.

---

### Task 1: Lock the evidence and claims contract

**Files:**
- Reference: `docs/superpowers/specs/2026-09-14-kinetic-zero-trust-dario-briefing-design.md`
- Reference: `docs/design-drafts/2026-09-14-frontier-zero-trust-pacing-thesis.md`
- Reference: `docs/design-drafts/2026-09-14-turnkey-blue-zone-strategy.md`

- [x] **Step 1: Confirm the primary-source record**

Use the current text of Amodei's essay, Anthropic's cybersecurity-evaluation incident report, METR's independent OpenAI–Hugging Face investigation, NIST SP 800-207, the KTP site, and the canonical KTP RFC repository. Record only source-supported numbers and distinguish publication dates from incident dates.

- [x] **Step 2: Apply the shared claim ladder**

Every document must distinguish observed incident evidence, independent incident analysis, draft protocol or bounded implementation evidence, and proposed pilot validation. Use “could have constrained named incident transitions” rather than “would have prevented the incident.”

- [x] **Step 3: Apply the terminology contract**

Use the following hierarchy without synonyms drifting across documents: Kinetic Trust is the substrate principle; KTP is the draft protocol framework; Kinetic Zero Trust is the doctrine; Kinetic Enforcement is the fail-safe function; Ambient Enforcement is the deployment property; and a Blue Zone is the protected environment.

- [x] **Step 4: Apply the geopolitical boundary**

State that unilateral Blue Zone deployment does not require a prior treaty or synchronized government decision. Do not claim that government, international coordination, model security, alignment, or threat intelligence become unnecessary, and do not claim protection outside declared non-bypassable coverage.

### Task 2: Create the sendable email

**Files:**
- Create: `docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-email.md`
- Generate: `docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-email.htm`

- [x] **Step 1: Draft a send-ready structure**

Include a subject line, “Dario,” greeting, 300–450 word body, private-briefing request, `[Your name]` closing, and an optional attachment note. Do not invent a sender title, organization, relationship, or contact details.

- [x] **Step 2: Make one argument**

Affirm the relevance of all three pacing levels, then state: embedded evaluators assess whether safety claims are credible; Kinetic Enforcement governs whether an action becomes a consequence. Include the agreement/no-agreement/defection formulation and bidirectional protection in no more than two short paragraphs.

- [x] **Step 3: Bound the ask**

Request a private 45-minute technical briefing with relevant safety, infrastructure, security, and independent-evaluation participants. Do not ask for endorsement, funding, a partnership, or a pilot commitment.

- [x] **Step 4: Verify email usability**

Confirm the email contains no more than two inline HTTPS links, has no footnotes interrupting the body, is understandable without attachments, and renders as a self-contained `.htm`.

### Task 3: Create the one-page executive brief

**Files:**
- Create: `docs/design-drafts/2026-09-14-kinetic-enforcement-executive-brief.md`
- Generate: `docs/design-drafts/2026-09-14-kinetic-enforcement-executive-brief.htm`

- [x] **Step 1: Draft the 650–850 word brief**

Use the title “Kinetic Enforcement: The Ultimate Fail-Safe for the Pace-the-Frontier Era.” Cover the problem, the pacing-versus-authority distinction, the same-substrate terminology stack, the agreement/no-agreement/defection advantage, bidirectional Ambient Enforcement, the five-step control loop, evidence status, and private-briefing request.

- [x] **Step 2: Add a compact conceptual figure**

Use a Markdown table or preformatted text—not a remote image—to show upstream safety measures flowing to the final independent consequence boundary and outbound/inbound requests encountering the same rule.

- [x] **Step 3: Make the brief independently citable**

Include a compact sources section containing Amodei, Anthropic, METR, NIST, and KTP primary or authoritative links. Label KTP as a draft framework and the pilot as proposed.

- [x] **Step 4: Verify one-page discipline**

Confirm the main narrative is 650–850 words excluding sources, contains one call to action, and does not assume the email or technical proposal has been read.

### Task 4: Create the direct private memo

**Files:**
- Create: `docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-private-memo.md`
- Generate: `docs/design-drafts/2026-09-14-dario-amodei-kinetic-enforcement-private-memo.htm`

- [x] **Step 1: Draft the 1,200–1,600 word memo**

Address Dario directly. Affirm operational excellence, alignment, interpretability, evaluation, embedded evaluators, democratic coordination, and global coordination. Identify the dependency on coordinated compliance without characterizing his plan as naïve or unnecessary.

- [x] **Step 2: Introduce the fail-safe proposition**

Explain that Kinetic Enforcement remains useful after upstream controls fail and at every pace outcome. State the bidirectional model and the precise sense in which a cheating foreign model gains capability but not authority inside a covered Blue Zone.

- [x] **Step 3: Use the incident as evidence, not spectacle**

Use the OpenAI–Hugging Face and Anthropic incidents to show that environment configuration, agent coordination, transcript integrity, and consequence boundaries matter. Separate observed facts from the proposed Blue Zone counterfactual.

- [x] **Step 4: End with the private briefing**

Offer a 45-minute agenda and request technical scrutiny. Keep pilot discussion conditional on the briefing outcome.

### Task 5: Create the technical proposal

**Files:**
- Create: `docs/design-drafts/2026-09-14-kinetic-enforcement-technical-proposal.md`
- Generate: `docs/design-drafts/2026-09-14-kinetic-enforcement-technical-proposal.htm`

- [x] **Step 1: Select the wide reader**

Begin the Markdown source with the exact directive `<!-- reader-layout: wide -->` so tables, incident maps, and verification matrices receive the scoped 68-rem content layout without changing standard readers.

- [x] **Step 2: Draft the 3,500–5,000 word proposal**

Cover the threat model, relationship to NIST Zero Trust, KTP decision semantics, Blue Zone components, the observe–decide–attenuate–enforce–record loop, inbound/outbound paths, evaluator evidence interface, incident-to-control map, pilot stages, metrics, falsification, limitations, governance, and briefing agenda.

- [x] **Step 3: Specify the 90-day validation pilot**

Use a cyber-evaluation Blue Zone with three control families: undeclared egress, privileged infrastructure mutation, and credential or repository mutation. Stage inventory, observe, shadow, canary, enforce, and attest. Require an independent evaluator to reproduce permit, attenuation, denial, bypass, stale-evidence, and recovery outcomes.

- [x] **Step 4: Define failure and falsification**

State that the pilot fails if a declared consequential path bypasses enforcement, the agent can alter governing evidence or policy, stale evidence opens authority, enforcement failure defaults to unsafe continuation, the recorded decision cannot be reproduced, or false denials prevent the stated mission beyond the accepted threshold.

- [x] **Step 5: Keep current boundaries explicit**

Do not depend on KTP v3 Federation. Label KTP as draft, distinguish KIL's bounded evidence from production readiness, and list model compromise, control-plane compromise, unknown paths, physical bypass, sensor collusion, and availability as residual risks.

### Task 6: Generate and validate the review package

**Files:**
- Generate: the four `.htm` siblings listed in Tasks 2–5
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Generate: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm`

- [x] **Step 1: Render all sources in one deterministic snapshot**

Use `tools.render_markdown._render_repository_from_snapshot` with the four new untracked design sources supplied as explicit extras. Regenerate the tracked lineage reader in the same run.

- [x] **Step 2: Verify the HTML contract**

For every review file, require a source SHA-256 matching its Markdown bytes, no remote script or stylesheet, no non-data media source, HTTPS or internal-fragment hyperlinks only, a single H1, inline print rules, and readable article content with scripts disabled.

- [x] **Step 3: Verify content constraints**

Check email and narrative word bands, consistent terminology, the exact private-briefing request, the agreement/no-agreement/defection argument, bidirectional coverage, “ultimate fail-safe” qualification, KTP draft status, and v3 Federation exclusion.

- [x] **Step 4: Run repository tests**

Run `.venv/bin/python -m unittest tests.test_markdown_html -v`. Expect all renderer and generation tests to pass; the publication-contract test may report only the known untracked design readers, now including these four new review outputs.

- [x] **Step 5: Inspect responsive layouts**

At desktop and 1000-pixel viewports, require no document-level horizontal overflow. For the technical proposal, confirm the desktop outline collapses at 1120 pixels and all tables and preformatted blocks fit their containers.

- [x] **Step 6: Record the completed package**

Append the evidence used, confirmed editorial decisions, affected artifacts, residual limitations, verification results, and next gate to `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`; regenerate its `.htm`; run `git diff --check`; and report only the four self-contained `.htm` outreach files for review.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
