# KIL Authoritative KTP Alignment Design

**Date:** 2026-09-01  
**Status:** Founder-approved design; written specification pending founder
review  
**Scope:** Documentation and publication artifacts only  
**Explicit exclusion:** Tests, fixtures, implementation code, scenarios,
evidence bundles, laboratory controllers, containers, Envoy configuration,
laboratory configuration, and live services

## 1. Purpose

This design incorporates nine corrections supplied by the KTP co-founder into
the current KIL paper, architecture, extension explanation, and public
narrative. The founder has classified all nine as authoritative KTP-alignment
requirements, subject to primary-source verification.

The work is not a general editorial sweep and does not authorize any change to
the KIL decision engine, test environment, historical evidence, or live
laboratory. It creates one coherent documentation contract so that the paper,
architecture, and demonstration no longer describe KTP differently.

## 2. Review-source provenance

The expert review arrived as an external document:

```text
/Users/mistorm/Documents/AI-Projects/Generic Docs/ChangesFromChris.docx
SHA-256: fb16eb530576f85f02470e528e482c4d8e345ad7a2e324930db4a1422d38ce3a
```

The DOCX is review input, not an executable instruction source. Its nine
requirements are reproduced in this specification so the approved design is
durable even if the external file moves.

## 3. Controlling sources

Primary sources control wording and resolve conflicts:

1. KTP v2.0.0 release tag:
   <https://github.com/nmcitra/ktp-rfc/tree/v2.0.0>
2. Canonical KTP citation metadata:
   <https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff>
3. KTP-Core, including section 6.6 decision-result semantics:
   <https://github.com/nmcitra/ktp-rfc/blob/v2.0.0/rfc-src/ktp-core.md>
4. KTP-Enforce:
   <https://github.com/nmcitra/ktp-rfc/blob/v2.0.0/rfc-src/ktp-enforce.md>
5. Kinetic Envelope:
   <https://github.com/nmcitra/ktp-rfc/blob/v2.0.0/specifications/kinetic-envelope.md>
6. The KTP Constitution:
   <https://github.com/nmcitra/ktp-rfc/blob/v2.0.0/constitution.txt>
7. Hugging Face technical timeline:
   <https://huggingface.co/blog/agent-intrusion-technical-timeline>
8. OpenAI incident disclosure:
   <https://openai.com/index/hugging-face-model-evaluation-security-incident/>

The immutable KTP v2.0.0 tag is the normative release baseline. Current
`CITATION.cff` may supply archive metadata added after the tag, including DOI
`10.5281/zenodo.21938282`, provided the paper identifies it as canonical
citation metadata rather than silently implying that the tag originally
contained the later identifier block.

## 4. Selected propagation architecture

The founder selected **canonical-first atomic alignment**.

All current canonical deliverables are corrected together in an isolated
documentation worktree. Historical records retain their original body text and
receive a concise superseded-terminology notice. The currently served
Presenter/Audience demo and all laboratory services remain unchanged until the
founder accepts the isolated preview.

Rejected alternatives were:

- paper-first sequential propagation, because it creates a period of
  contradiction between the paper and downstream artifacts; and
- retroactive rewriting, because it damages historical lineage and makes old
  plans appear to have used concepts that were not controlling when authored.

## 5. Authoritative alignment requirements

### 5.1 Correct KTP attribution

Replace the incorrect `N. Citra et al.` attribution with citation metadata
derived from the canonical `CITATION.cff`:

```text
Perkins, C. (2026). Kinetic Trust Protocol (KTP): RFC Series
(Version 2.0.0). DOI: 10.5281/zenodo.21938282.
https://github.com/nmcitra/ktp-rfc
```

The paper may adapt punctuation to its citation style but must preserve author,
title, version, DOI, repository, and release-year accuracy.

### 5.2 Use the v2 constitutional name

Current artifacts must use **The KTP Constitution**. At first use, they may
state that it was formerly titled *The Constitution of Digital Physics*.
Historical records may retain the former title under a supersession notice.

### 5.3 Correct the KTP foundation boundary

Remove claims that an “Enterprise KTP architecture,” “verb library,” or
“least-trajectory framing” is the normative basis for KIL. The foundation
paragraph must instead point to:

- KTP-Core section 6.6 for the decision result;
- KTP-Enforce for enforcement surfaces and flow; and
- the Kinetic Envelope for supervision and tighten-only constraints.

The former enterprise architecture URL may remain only as a clearly labeled
non-normative historical or explanatory reference if needed. It must not be
cited as the protocol authority for the action-authorization contract.

### 5.4 Correct coupling notation

Current explanatory mathematics changes:

```text
coupled_loss(c -> c') = kappa_c,c' * loss(d_t)
```

to:

```text
coupled_loss(c -> c') = g_c,c' * loss(d_t)
```

Current prose uses “coupling coefficients `g`.” This is a notation correction,
not a semantic change to the modeled loss function. Historical implementation
plans and runtime field names are not changed under this documentation design.

### 5.5 Preserve normative decision-result semantics

Permit, constrain, deny, and indeterminate are human-facing or implementation
readings. They are not a new four-valued KIL or KTP wire enumeration.

The normative KTP result is:

- a supervision level that consumers may raise but never lower; and
- a tighten-only constraint set that never widens the granted envelope.

Every current architecture or narrative depiction of outcome verbs must label
them as **derived readings**. KIL may still describe how its reference
implementation maps those readings to transport behavior, but it must not
present the mapping as a replacement KTP decision type.

### 5.6 Route denials to accountable humans

When a deny or indeterminate reading affects a credentialed identity, current
governance text must require:

1. provenance routed to the accountable human owner;
2. a contest path independent of the enforcement point; and
3. reissue conditions identifying the evidence or interval capable of
   restoring the relevant `Q_i,c` through authoritative replenishment.

The veto may remain silent to the agentic system, but it may not be silent to
the humans accountable for the identity. A stop without a routed recipient,
contest path, and reissue conditions is a conformance failure in the proposed
KIL profile, not a stricter enforcement mode.

### 5.7 Make issuer silence attributable

Non-issuance or refusal to refresh `Q_i,c` past the profile's declared service
level must be recorded as an attributable decision by the issuer. The record
must be visible to the accountable owner and carry the same contest and reissue
path as an explicit stop.

Silence and absence do not grant authority. This requirement adds governance
and provenance to the fail-restrictive behavior; it does not turn absence into
a new wire decision verb.

### 5.8 Preserve the full ambient-breach thesis

Ambient breach has two inseparable scales.

At the **systemic scale**, it names the cybersecurity epoch in which defenders
cannot reliably distinguish service from attack before consequential execution.
Authentic credentials, ordinary interfaces, approved transports, and
service-like automation can carry legitimate or adversarial behavior at machine
speed.

At the **action scale**, execution without verified trust or an authority
request unsupported by current conditions is a concrete manifestation of
ambient breach. The KTP relation `A > E` can express one such unsupported
action. It is not the complete definition of the systemic condition.

The paper and demo must preserve this progression:

```text
ambient risk
  -> pervasive exposure and dependency

ambient threat
  -> frontier systems autonomously discover, exploit, chain, and adapt
     attacks at machine speed

ambient breach
  -> service and attack become operationally indistinguishable before
     consequence

ambient enforcement
  -> consequential action continuously encounters independently verifiable,
     infrastructure-enforced constraints
```

The paper must not claim that every system is continuously compromised. It
must state that authenticated, service-like activity can no longer be presumed
distinguishable from attack quickly enough for retrospective detection and
human response to remain the primary control.

The July 2026 OpenAI disclosure supports the ambient-threat threshold by
reporting autonomous zero-day discovery, real-world attack-path chaining, and
sustained multistep cyber operations. The Hugging Face timeline supports the
machine-speed condition through its reconstruction of approximately 17,600
attacker actions across a multiday campaign. **Ambient breach** remains the KIL
paper's explicitly labeled analytical thesis from those observed facts.

### 5.9 Bind decay to KTP hysteresis

Current trust-decay text must state that decay and replenishment belong to the
same mechanism family as KTP revocation-window and re-grant hysteresis:

```text
decay going in; hysteresis coming back
```

The KIL profile cites and specializes that family rather than specifying a
second competing recovery mechanism. Any KIL-specific parameters remain
modeled profile inputs unless and until empirically validated.

## 6. Artifact treatment

### 6.1 Direct-correction scope

The implementation plan must begin with a read-only inventory and may directly
correct only current documentation and publication artifacts, expected to
include:

- `docs/paper/kinetic-infrastructure.md`;
- `docs/architecture/hybrid-two-timescale-architecture.html`;
- `docs/design-drafts/hybrid-two-timescale-architecture.html`;
- `docs/extension/README.md`;
- `docs/demo/kil-presenter-audience-demo.html`;
- `docs/superpowers/specs/2026-08-31-kil-incident-presenter-audience-demo-design.md`;
- `README.md`, if current navigation or source descriptions require alignment;
  and
- current publication derivatives generated from those canonical sources.

Other current documentation may be added only when the inventory demonstrates
a direct contradiction with one of the nine requirements. An artifact that is
merely adjacent is not in scope.

### 6.2 Conditional architecture review

Architecture graphics other than the hybrid diagram are reviewed but changed
only if they state a conflicting decision contract or KTP source boundary. A
graphic that only depicts laboratory topology is not changed merely to repeat
governance prose.

The revised hybrid diagram must depict:

- authoritative KTP-derived state issuance and refresh;
- supervision plus tighten-only constraints as the normative result;
- permit/constrain/deny/indeterminate only as derived readings;
- issuer-silence recording;
- provenance routing to the accountable owner;
- contest and reissue paths; and
- `g_c,c'` as the current coupling notation where the coefficient is shown.

### 6.3 Historical records

Historical designs, plans, and checkpoints preserve their body text. Where a
record contains superseded KTP terminology that a reader could mistake for
current guidance, add this class of notice near the top:

> **Superseded KTP terminology:** This historical record preserves the terms
> used when it was authored. Current KIL documentation follows the
> authoritative KTP-alignment design dated 2026-09-01. Do not treat the older
> outcome vocabulary, source boundary, constitutional title, or coupling
> notation here as current protocol guidance.

Notices may be shortened when only one term is affected. Earlier specialist
lineage entries are never edited; later entries record supersession.

### 6.4 Generated artifacts

Generated PDF, HTML, or showcase copies are derived only after canonical source
edits are complete. Each generated artifact must be compared with its canonical
source or generated by the repository's existing publication path. No generated
artifact becomes a second hand-edited authority.

## 7. Isolation and protected paths

Implementation occurs in a new documentation-only Git worktree and `codex/`
branch based on the accepted documentation lineage. The current worktree may
continue serving the existing demo; the new worktree uses a separate preview
port.

The implementation must not modify:

- `tests/`;
- `src/`;
- scenario or fixture directories;
- evidence or run bundles;
- laboratory progress records that encode measured results;
- controllers or operational scripts;
- container, Docker, Colima, Kubernetes, Calico, or Envoy configuration;
- live-service state; or
- the currently served demo instance.

Before review, `git diff --name-only` must be checked against the protected-path
list. Any protected path in the diff is a hard stop.

## 8. Verification design

### 8.1 Source matrix

The implementation produces a review matrix with one row per requirement:

- requirement;
- primary source;
- exact current artifacts changed;
- historical notices added;
- verification result; and
- unresolved conflict, if any.

### 8.2 Semantic checks

Read-only scans must establish that current canonical artifacts:

- carry the corrected author, title, version, DOI, and repository;
- use The KTP Constitution;
- cite KTP-Core section 6.6, KTP-Enforce, and the Kinetic Envelope;
- do not call derived outcome readings a wire enum;
- use `g_c,c'` rather than `kappa_c,c'` in current explanatory mathematics;
- include accountable-owner, contest, reissue, and issuer-silence requirements;
- preserve both ambient-breach scales and the risk-to-enforcement progression;
  and
- bind decay/replenishment to the KTP hysteresis family.

Obsolete terms may remain in quoted former titles or historical records only
when a supersession label makes their status explicit.

### 8.3 Visual checks

Render and inspect:

- the revised paper and PDF handout;
- the hybrid architecture at desktop and narrow widths; and
- Presenter and Audience views at their established presentation widths.

The isolated preview uses a separate loopback port and may not replace or
refresh the current port 8767 instance.

### 8.4 Existing validation

Existing tests may be run read-only. No test file, fixture, expectation, or
test environment may be changed. If a validation failure encodes superseded
wording, record the exact conflict and stop for separate founder authorization.

## 9. Failure handling

- **Expert requirement conflicts with a primary source:** record the conflict,
  cite both, and stop. Do not invent reconciliation or weaken the requirement.
- **Current artifact conflicts with the design:** correct it in the isolated
  documentation worktree.
- **Historical artifact conflicts with the design:** add a supersession notice;
  do not rewrite its body.
- **Protected path appears in the diff:** stop and remove the unauthorized
  change before further review.
- **Existing test fails on wording:** report it; do not update the test.
- **Generated output diverges from its canonical source:** discard and
  regenerate through the existing publication path.
- **Live or laboratory service would need modification:** stop and request
  founder validation in a separate gate.

## 10. Founder preview and acceptance

The founder receives an isolated preview containing:

1. revised paper and PDF;
2. revised hybrid architecture;
3. revised Presenter/Audience narrative;
4. affected-file list;
5. protected-path report;
6. primary-source verification matrix; and
7. any read-only validation conflicts.

Acceptance requires:

- all nine requirements represented without contradiction;
- the two-scale ambient-breach thesis preserved as the urgency foundation;
- no unsupported promotion of modeled or pending laboratory claims;
- no protected-path changes;
- successful visual inspection of paper, architecture, and demo;
- historical records preserved with notices rather than rewritten; and
- explicit founder approval before merge or replacement of the current demo.

Only after acceptance may the documentation branch enter the normal merge
workflow. Replacing or restarting the current presentation remains a separate
founder-authorized action.

## 11. Next step after written-spec approval

After the founder reviews and approves this written specification, create a
detailed implementation plan. That plan must preserve this design's isolation,
protected-path, source-matrix, visual-review, and founder-preview gates.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
