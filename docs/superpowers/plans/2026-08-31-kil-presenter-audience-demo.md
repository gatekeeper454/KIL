# KIL Presenter/Audience Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a showcase-ready, synchronized Presenter/Audience browser demo with a four-part KIL primer, an eight-scene Hugging Face case study, persistent topology, claim-safe graphics, and 30–45-second talk tracks.

**Architecture:** A tracked, self-contained HTML document owns immutable JSON scene data, responsive SVG renderers, navigation, presenter notes, and a same-origin `BroadcastChannel` synchronization contract. A Python `unittest` validates durable content and evidence language; a Node/Playwright verifier serves the page locally and proves real two-page synchronization, mode separation, reload recovery, and responsive layout.

**Tech Stack:** Semantic HTML, scoped CSS, browser-native JavaScript and SVG, `BroadcastChannel`, Python 3.12 `unittest`, Node.js, Playwright Chromium.

---

## File map

- Create `docs/demo/kil-presenter-audience-demo.html`: canonical self-contained application and twelve immutable narrative states.
- Create `tests/test_presenter_audience_demo.py`: static content, citation, evidence-language, and DOM contract.
- Create `tools/verify_presenter_audience_demo.mjs`: local HTTP server and two-page Playwright verifier.
- Create ignored `artifacts/generated/kil-presenter-audience-demo.html`: verified showcase copy.
- Modify `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`: implementation and verification lineage.

### Task 1: Establish the durable narrative contract

**Files:**
- Create: `tests/test_presenter_audience_demo.py`
- Create: `docs/demo/kil-presenter-audience-demo.html`

- [ ] **Step 1: Write the failing static contract test**

Create a `unittest.TestCase` that loads the HTML, extracts `<script id="kil-demo-scenes" type="application/json">`, and asserts:

```python
EXPECTED_IDS = [
    "primer-ambient-breach", "primer-kinetic-infrastructure",
    "primer-ktp-extension", "primer-trust-physics",
    "case-ambient-breach", "case-foothold", "case-first-divergence",
    "case-cascade", "case-kil-mechanics", "case-lab-mapping",
    "case-three-tracks", "case-evidence",
]
required_keys = {
    "id", "act", "order", "title", "status", "takeaway",
    "script", "source", "visual",
}
self.assertEqual([scene["id"] for scene in scenes], EXPECTED_IDS)
self.assertTrue(all(required_keys == set(scene) for scene in scenes))
self.assertTrue(all(70 <= len(scene["script"].split()) <= 90 for scene in scenes))
self.assertEqual([scene["act"] for scene in scenes[:4]], ["primer"] * 4)
self.assertEqual([scene["act"] for scene in scenes[4:]], ["case-study"] * 8)
```

Also require `data-mode-label`, `data-sync-status`, `data-act-controls`, `data-scene-controls`, `data-visual`, `data-presenter-notes`, `data-prev`, `data-next`, and `data-open-audience`. Require all KTP reference URLs, the canonical `CITATION.cff`, and the Hugging Face timeline URL. Reject public claim strings `absolute denial`, `prevented structurally`, `microsecond enforcement`, `classic zero trust failure`, `perfectly valid credentials`, `killed before`, `for free`, `0 bytes exfiltrated`, and `validated live kubernetes`.

- [ ] **Step 2: Run the new test and verify RED**

```bash
PYTHONPATH=src /Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests/test_presenter_audience_demo.py -v
```

Expected: FAIL because the canonical HTML does not exist.

- [ ] **Step 3: Add the minimal canonical document and scene records**

Create a complete HTML document with this stable body contract:

```html
<main id="kil-demo-app">
  <header>
    <span data-mode-label></span><h1 data-title></h1>
    <span data-status></span><span data-progress></span>
    <span data-sync-status aria-live="polite"></span>
  </header>
  <nav data-act-controls aria-label="Presentation acts"></nav>
  <nav data-scene-controls aria-label="Scenes"></nav>
  <section data-visual aria-live="polite"></section>
  <p data-takeaway></p>
  <aside data-presenter-notes><h2>Say this</h2><p data-script></p><p data-source></p></aside>
  <nav aria-label="Presentation navigation">
    <button type="button" data-prev>Previous</button>
    <button type="button" data-next>Next</button>
    <button type="button" data-open-audience>Open audience view</button>
  </nav>
</main>
```

Immediately after `main`, add `script#kil-demo-scenes[type="application/json"]`
containing exactly four primer and eight case-study records with the IDs above.
Each script is original 70–90-word prose and ends with an explicit boundary
such as `This is the KIL thesis.`, `This is a proposed KIL extension.`, `These
parameters are modeled.`, `These incident facts are source-cited.`, `This KIL
result is modeled.`, `This is a modeled lab mapping.`, or `The V3B-1 live result
remains pending.` The approved titles, status classes, visual keys, takeaways,
and narrative anchors come directly from the approved design specification.

- [ ] **Step 4: Run the static test and verify GREEN**

Expected: the Task 1 test passes.

- [ ] **Step 5: Run the full Python suite**

```bash
PYTHONPATH=src /Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -q
```

Expected: the 485-test baseline plus all new demo contract tests, OK.

- [ ] **Step 6: Commit the narrative contract**

```bash
git add tests/test_presenter_audience_demo.py docs/demo/kil-presenter-audience-demo.html
git commit -m "Add KIL presenter demo narrative contract"
```

### Task 2: Implement navigation and mode separation

**Files:**
- Modify: `tests/test_presenter_audience_demo.py`
- Modify: `docs/demo/kil-presenter-audience-demo.html`
- Create: `tools/verify_presenter_audience_demo.mjs`

- [ ] **Step 1: Write the failing browser verifier**

Use Node built-ins plus Playwright. Bind a local server to `127.0.0.1` on an ephemeral port, serve only the canonical HTML, launch Chromium, and assert:

```javascript
await presenter.goto(`${base}/?mode=presenter&session=showcase`);
await audience.goto(`${base}/?mode=audience&session=showcase`);
await expectText(presenter, '[data-mode-label]', 'Presenter');
await expectText(audience, '[data-mode-label]', 'Audience');
await assertVisible(presenter, '[data-presenter-notes]');
await assertHidden(audience, '[data-presenter-notes]');
await presenter.click('[data-scene-id="primer-ktp-extension"]');
await expectText(presenter, '[data-title]', 'KIL is a proposed extension of KTP');
await presenter.click('[data-next]');
await expectText(presenter, '[data-title]', 'Why kinetic authority works');
await presenter.click('[data-prev]');
await expectText(presenter, '[data-title]', 'KIL is a proposed extension of KTP');
```

Exit nonzero on console errors, page errors, failed assertions, or requests outside `/` and `/favicon.ico`.

- [ ] **Step 2: Run the browser verifier and verify RED**

```bash
NODE_PATH=/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules /Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node tools/verify_presenter_audience_demo.mjs
```

Expected: FAIL because mode rendering and navigation are absent.

- [ ] **Step 3: Implement deterministic mode and navigation behavior**

```javascript
const validModes = new Set(['presenter', 'audience', 'standalone']);
const params = new URLSearchParams(location.search);
const requestedMode = params.get('mode') || 'standalone';
const mode = validModes.has(requestedMode) ? requestedMode : 'standalone';
const byId = new Map(scenes.map((scene, index) => [scene.id, {scene, index}]));
function selectScene(id, {broadcast = true} = {}) {
  const entry = byId.get(id);
  if (!entry) return false;
  currentIndex = entry.index;
  render(entry.scene);
  if (broadcast && mode === 'presenter') publishState();
  return true;
}
```

Generate two act buttons and scene buttons for the selected act using `aria-pressed`. Previous/next traverse all twelve records and update the act. Presenter shows notes and `Open audience view`; audience hides both; standalone shows notes only with `?notes=1`.

- [ ] **Step 4: Run static and browser tests and verify GREEN**

Expected: both Task 1 and Task 2 commands pass.

- [ ] **Step 5: Commit navigation and modes**

```bash
git add docs/demo/kil-presenter-audience-demo.html tests/test_presenter_audience_demo.py tools/verify_presenter_audience_demo.mjs
git commit -m "Implement KIL demo navigation and modes"
```

### Task 3: Implement presenter-authoritative synchronization

**Files:**
- Modify: `tools/verify_presenter_audience_demo.mjs`
- Modify: `docs/demo/kil-presenter-audience-demo.html`

- [ ] **Step 1: Extend the verifier with failing synchronization cases**

```javascript
await presenter.click('[data-scene-id="case-first-divergence"]');
await expectText(audience, '[data-title]', 'The first mediated divergence');
await expectText(presenter, '[data-sync-status]', 'Audience synchronized');
const wrongAudience = await context.newPage();
await wrongAudience.goto(`${base}/?mode=audience&session=other-session`);
await assertNotText(wrongAudience, '[data-title]', 'The first mediated divergence');
await presenter.reload();
await presenter.click('[data-scene-id="case-evidence"]');
await expectText(audience, '[data-title]', 'What is evidence today?');
```

- [ ] **Step 2: Run the verifier and verify RED**

Expected: FAIL because cross-page state does not propagate.

- [ ] **Step 3: Implement the closed BroadcastChannel contract**

Use channel `kil-demo:<session>`. Messages contain schema version, message type (`state`, `request_state`, or `ack`), session ID, presenter epoch, sequence, scene ID, and audience ID where applicable. Presenter alone emits state. Audience rejects wrong sessions, unknown types, invalid scenes, and stale sequences within an epoch. A new valid presenter epoch resets comparison. Audience requests state on load and acknowledges applied state. Presenter reports synchronized only for an acknowledgement matching its current epoch and sequence. If the API is unavailable, report `Not synchronized` and retain local navigation.

- [ ] **Step 4: Run the browser verifier and verify GREEN**

Expected: same-session propagation, wrong-session isolation, acknowledgement, and reload recovery pass.

- [ ] **Step 5: Commit synchronization**

```bash
git add docs/demo/kil-presenter-audience-demo.html tools/verify_presenter_audience_demo.mjs
git commit -m "Synchronize KIL presenter and audience views"
```

### Task 4: Build the four KIL primer graphics

**Files:**
- Modify: `tests/test_presenter_audience_demo.py`
- Modify: `docs/demo/kil-presenter-audience-demo.html`

- [ ] **Step 1: Add failing primer visual assertions**

Assert the visual keys are `ambient-breach`, `kil-comparison`, `hybrid-architecture`, and `trust-physics`. Require renderer functions `renderAmbientBreach`, `renderKILComparison`, `renderHybridArchitecture`, and `renderTrustPhysics`. Require visible copy `KIL_effective_authority ≤ KTP_authorized_authority`, `signed, short-lived composite KTP state`, `Earn slowly`, `Decay passively`, `Lose quickly`, and `Class-bound`.

- [ ] **Step 2: Run the static test and verify RED**

Expected: FAIL because the primer renderers do not exist.

- [ ] **Step 3: Implement four responsive SVG renderers**

- P1: an authentic credential crosses a credential/policy checkpoint and branches into labeled novel actions; KIL asks whether fresh trajectory carries class-bound authority.
- P2: a four-row checkpoint-pattern versus ambient-enforcement comparison.
- P3: an authoritative KTP-derived signed-state loop feeds a fast, reducing-only boundary and displays the non-expansion invariant.
- P4: normalized charge rises in small steps, decays during silence, and drops after a modeled high-divergence event, directly labeled `Earn slowly`, `Decay passively`, `Lose quickly`, and `Class-bound`.

Each SVG contains nonempty `<title>` and `<desc>`, sizes responsively, pairs color with labels and line styles, and contains no fabricated latency, throughput, telemetry, hash, or universal parameter claim.

- [ ] **Step 4: Run static and browser verifiers and verify GREEN**

Expected: both pass.

- [ ] **Step 5: Commit the primer graphics**

```bash
git add docs/demo/kil-presenter-audience-demo.html tests/test_presenter_audience_demo.py
git commit -m "Add KIL ambient enforcement primer graphics"
```

### Task 5: Build the eight-scene incident topology and lab mapping

**Files:**
- Modify: `tests/test_presenter_audience_demo.py`
- Modify: `docs/demo/kil-presenter-audience-demo.html`

- [ ] **Step 1: Add failing case-study assertions**

Require visual keys `incident-overview`, `foothold`, `branching-cutoff`, `incident-topology`, `hybrid-applied`, `lab-mapping`, `three-tracks`, and `evidence-ladder`. Require public copy with modeled Phase 1 `0.95`, modeled Phase 4 `0.90`, `Conditionally unreachable`, `permit / permit / deny`, `200 / 200 / 403`, `V3A modeled`, `V3B-1 pending`, and `V3B-2 future`.

- [ ] **Step 2: Run the static test and verify RED**

Expected: FAIL because the incident renderers and topology states are absent.

- [ ] **Step 3: Implement the persistent topology and scene renderers**

Use this canonical graph:

```text
external agent -> renderer -> worker -> mediated egress
  -> Kubernetes API -> node privilege -> secret store
  -> shared connector -> other clusters
  -> mesh credential -> corporate mesh
  -> signing capability -> forged tokens
  -> source-control token -> CI/source control
```

Scene 3 renders aligned `Disclosed incident` and `KIL counterfactual · modeled` lanes; the second stops at Phase 1 and dims Phases 2–8 as `Conditionally unreachable`. Scene 4 branches from the secret store and uses modeled Phase 4 divergence `0.90`. Scene 6 maps incident roles to driver, Envoy, authorization, local reduction, harmless target, and evidence bundle. Scene 7 renders the three tracks and labels the result modeled. Scene 8 renders V1, V2, V3A, pending V3B-1, future V3B-2, and V4 without depicting current V3B-1 as live Kubernetes.

- [ ] **Step 4: Run static and browser verifiers and verify GREEN**

Expected: both pass.

- [ ] **Step 5: Commit the incident story**

```bash
git add docs/demo/kil-presenter-audience-demo.html tests/test_presenter_audience_demo.py
git commit -m "Add KIL incident topology and lab story"
```

### Task 6: Verify accessibility, responsive presentation, and showcase export

**Files:**
- Modify: `tools/verify_presenter_audience_demo.mjs`
- Modify: `docs/demo/kil-presenter-audience-demo.html`
- Create: `artifacts/generated/kil-presenter-audience-demo.html` (ignored)
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

- [ ] **Step 1: Add failing responsive and accessibility checks**

At 736×900 and 360×900 for presenter and audience, plus 1024×900 for presenter, assert no horizontal overflow:

```javascript
const overflow = await page.evaluate(() =>
  document.documentElement.scrollWidth > document.documentElement.clientWidth
);
if (overflow) throw new Error('horizontal overflow');
```

Also require every rendered SVG to have a nonempty title and description, all scene controls to be native focusable buttons, reduced-motion rendering without animation, dark and light scheme rendering, and no console warning/error or page error.

- [ ] **Step 2: Run the browser verifier and verify RED**

Expected: at least one layout or accessibility requirement fails before final correction.

- [ ] **Step 3: Finish responsive and accessible presentation behavior**

Use scoped CSS custom properties, a restrained engineering grid without fake rulers, minimum 44-pixel touch targets, responsive SVG view boxes, stacked narrow layouts, visible focus, reduced motion, and label/line-style redundancy. Presenter notes remain secondary; Audience mode gives the visual dominant space.

- [ ] **Step 4: Run complete verification**

```bash
PYTHONPATH=src /Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -q
NODE_PATH=/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules /Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node tools/verify_presenter_audience_demo.mjs
git diff --check
```

Expected: the baseline plus new demo tests OK, browser verifier PASS, no diff
errors.

- [ ] **Step 5: Generate and compare the showcase copy**

```bash
mkdir -p artifacts/generated
cp docs/demo/kil-presenter-audience-demo.html artifacts/generated/kil-presenter-audience-demo.html
cmp docs/demo/kil-presenter-audience-demo.html artifacts/generated/kil-presenter-audience-demo.html
```

Expected: `cmp` exits 0.

- [ ] **Step 6: Append specialist lineage**

Record the approved two-act input, implementation interpretation, confirmed presentation behavior, verification evidence, affected artifacts, remaining V3B-1 evidence limitation, and next showcase/publication gate. Include the canonical KTP citation.

- [ ] **Step 7: Commit the completed demo**

```bash
git add docs/demo/kil-presenter-audience-demo.html tests/test_presenter_audience_demo.py tools/verify_presenter_audience_demo.mjs docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md
git commit -m "Complete KIL presenter audience showcase"
```

- [ ] **Step 8: Open local presenter and audience views**

Serve `docs/demo` on localhost and open:

```text
http://127.0.0.1:<port>/?mode=presenter&session=showcase
http://127.0.0.1:<port>/?mode=audience&session=showcase
```

Keep the server local-only and do not execute the V3B-1 central laboratory run.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
