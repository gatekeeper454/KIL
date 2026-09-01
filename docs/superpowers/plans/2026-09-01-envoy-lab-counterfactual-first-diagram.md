# Envoy Laboratory Counterfactual-First Diagram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved standalone counterfactual-first Envoy diagram and
integrate the same observed/modeled/pending story into the synchronized
Presenter/Audience demonstration without changing any laboratory behavior.

**Architecture:** Add one self-contained, passive standalone HTML presentation
under `docs/demo/`, then replace only the existing lab-mapping scene renderer
with an inline SVG that carries the same three-band semantics. A new isolated
documentation contract test protects the diagram without modifying existing
tests, and a new Brave/Playwright verifier checks layout and accessibility
without starting the KIL lab.

**Tech Stack:** Semantic HTML, CSS, inline SVG, existing vanilla JavaScript
Presenter/Audience state machine, Python `unittest`, Node.js, Playwright, Brave
Chromium.

---

## Scope and safety contract

The implementation may change only:

- create `docs/demo/envoy-lab-counterfactual-first.html`;
- modify `docs/demo/kil-presenter-audience-demo.html`;
- create `tests/test_envoy_counterfactual_diagram.py` after explicit execution
  approval;
- create `tools/verify_envoy_counterfactual_diagram.mjs`;
- modify `README.md`;
- modify `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`; and
- update this plan's checkboxes during execution.

It must not modify any existing test file, fixture, scenario, schema, source
module, adapter, Envoy configuration, container definition, laboratory
controller, evidence bundle, generated run, or live service. It must not start
V3B-1 or execute the central `run` command. If an existing test rejects the
authoritative KTP wording, stop at a founder gate rather than changing the test.

The later graphic-intensive Presenter/Audience redesign is explicitly outside
this plan. This plan creates the approved semantic baseline that redesign must
preserve.

## File responsibilities

| File | Responsibility |
|---|---|
| `docs/demo/envoy-lab-counterfactual-first.html` | Self-contained executive introduction plus the approved three-band standalone diagram. |
| `docs/demo/kil-presenter-audience-demo.html` | Existing synchronized app; update only the ambient-breach primer copy, lab-mapping scene record, and lab-mapping renderer. |
| `tests/test_envoy_counterfactual_diagram.py` | New isolated source contract for narrative, KTP semantics, evidence labels, accessibility, passivity, and demo integration. |
| `tools/verify_envoy_counterfactual_diagram.mjs` | New read-only Brave/Playwright visual verifier for the standalone diagram. |
| `README.md` | Discoverability and local opening instructions for the standalone diagram. |
| `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md` | Append-only implementation and verification record. |

### Task 1: Establish the protected path and standalone source contract

**Files:**

- Create: `tests/test_envoy_counterfactual_diagram.py`
- Create: `docs/demo/envoy-lab-counterfactual-first.html`

- [ ] **Step 1: Record explicit execution approval for the new isolated test**

Before editing `tests/`, confirm that the founder's selection of this plan for
execution authorizes creation of
`tests/test_envoy_counterfactual_diagram.py`. This approval does not authorize
modification of any existing test or laboratory artifact.

- [ ] **Step 2: Write the failing standalone existence and source test**

Create `tests/test_envoy_counterfactual_diagram.py` with:

```python
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
STANDALONE = ROOT / "docs" / "demo" / "envoy-lab-counterfactual-first.html"
DEMO = ROOT / "docs" / "demo" / "kil-presenter-audience-demo.html"
README = ROOT / "README.md"

KTP_CITATION = "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff"
KTP_RELEASE = "https://github.com/nmcitra/ktp-rfc/tree/v2.0.0"
HF_TIMELINE = "https://huggingface.co/blog/agent-intrusion-technical-timeline"


class CounterfactualDiagramTest(unittest.TestCase):
    def standalone(self) -> str:
        self.assertTrue(STANDALONE.is_file(), f"missing {STANDALONE}")
        return STANDALONE.read_text(encoding="utf-8")

    def test_standalone_exists_and_cites_controlling_sources(self):
        html = self.standalone()
        self.assertIn("<title>KIL — Counterfactual-First Envoy Laboratory</title>", html)
        for source in (KTP_CITATION, KTP_RELEASE, HF_TIMELINE):
            with self.subTest(source=source):
                self.assertIn(source, html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test and verify the missing-file failure**

Run:

```bash
PYTHONPATH=src "/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python" -m unittest tests.test_envoy_counterfactual_diagram -v
```

Expected: `FAIL` identifying the missing
`docs/demo/envoy-lab-counterfactual-first.html`.

- [ ] **Step 4: Create the minimal passive standalone document**

Create `docs/demo/envoy-lab-counterfactual-first.html` with this complete
document shell:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KIL — Counterfactual-First Envoy Laboratory</title>
</head>
<body>
  <main id="kil-envoy-counterfactual">
    <h1>Kinetic Infrastructure Layer</h1>
    <p>Counterfactual-first Envoy laboratory demonstration</p>
  </main>
  <footer>
    <a href="https://github.com/nmcitra/ktp-rfc/tree/v2.0.0">KTP v2.0.0</a>
    <a href="https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff">KTP citation</a>
    <a href="https://huggingface.co/blog/agent-intrusion-technical-timeline">Hugging Face technical timeline</a>
  </footer>
</body>
</html>
```

- [ ] **Step 5: Run the focused test and verify it passes**

Run the command from Step 3.

Expected: `Ran 1 test` and `OK`.

- [ ] **Step 6: Commit the protected test scaffold**

```bash
git add tests/test_envoy_counterfactual_diagram.py docs/demo/envoy-lab-counterfactual-first.html
git commit -m "test: establish Envoy counterfactual diagram contract"
```

### Task 2: Implement the executive narrative and three-band standalone diagram

**Files:**

- Modify: `tests/test_envoy_counterfactual_diagram.py`
- Modify: `docs/demo/envoy-lab-counterfactual-first.html`

- [ ] **Step 1: Add failing semantic, accessibility, and passivity tests**

Add this parser above `CounterfactualDiagramTest`:

```python
class PassiveDocumentParser(HTMLParser):
    FORBIDDEN_TAGS = {"script", "iframe", "object", "embed", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.violations: list[str] = []

    def handle_starttag(self, tag, attrs):
        lowered = tag.lower()
        if lowered in self.FORBIDDEN_TAGS:
            self.violations.append(f"forbidden tag <{tag}>")
        for name, value in attrs:
            if name.lower().startswith("on"):
                self.violations.append(f"event handler {name}")
            if name.lower() == "href" and value and not (
                value.startswith("https://") or value.startswith("#")
            ):
                self.violations.append(f"non-HTTPS href {value}")

    handle_startendtag = handle_starttag
```

Add these methods to `CounterfactualDiagramTest`:

```python
    def test_executive_narrative_preserves_the_approved_why(self):
        html = " ".join(self.standalone().split())
        for exact in (
            "Cybersecurity is currently at an inflection point",
            "pervasive, continuous ‘ambient breach’",
            "Ambient enforcement represents this critical evolution",
            "does not mean every system is continuously compromised",
        ):
            with self.subTest(exact=exact):
                self.assertIn(exact, html)

    def test_three_bands_preserve_semantics_and_evidence_boundaries(self):
        html = self.standalone()
        self.assertEqual(len(re.findall(r'data-band="(?:observed|lab|result)"', html)), 3)
        for exact in (
            "Observed incident",
            "Envoy lab model",
            "KIL counterfactual result",
            "Signed composite KTP state",
            "supervision plus tighten-only constraints",
            "derived HTTP 403",
            "200 / 200 / 403",
            "1 / 1 / 0",
            "Conditionally unreachable",
            "Pending validation",
        ):
            with self.subTest(exact=exact):
                self.assertIn(exact, html)

    def test_standalone_is_passive_accessible_and_responsive(self):
        html = self.standalone()
        parser = PassiveDocumentParser()
        parser.feed(html)
        self.assertEqual(parser.violations, [])
        self.assertIn('role="img"', html)
        self.assertIn("<title id=", html)
        self.assertIn("<desc id=", html)
        self.assertIn("aria-labelledby=", html)
        self.assertIn("@media (max-width: 640px)", html)
        self.assertIn("@media (prefers-reduced-motion: reduce)", html)
        self.assertNotIn("microsecond enforcement", html.lower())
        self.assertNotIn("validated live", html.lower())
```

- [ ] **Step 2: Run the tests and verify the semantic failures**

Run:

```bash
PYTHONPATH=src "/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python" -m unittest tests.test_envoy_counterfactual_diagram -v
```

Expected: three new tests fail because the narrative, bands, accessibility
metadata, and responsive rules are absent.

- [ ] **Step 3: Replace the standalone shell with the approved document**

Keep the source URLs from Task 1. Add theme-aware CSS with these exact layout
contracts:

```css
:root {
  color-scheme: light dark;
  --kil-bg: light-dark(#f4f7fa, #0d141c);
  --kil-panel: light-dark(#ffffff, #17222e);
  --kil-text: light-dark(#14202b, #edf4fa);
  --kil-muted: light-dark(#516575, #aebdca);
  --kil-line: light-dark(#c6d1da, #435564);
  --kil-observed: light-dark(#a8332a, #ff786e);
  --kil-model: light-dark(#155fae, #69aef5);
  --kil-pending: light-dark(#6b7280, #9ca3af);
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--kil-bg); color: var(--kil-text); }
main, footer { width: min(1180px, 100%); margin: 0 auto; padding: 24px; }
.kil-narrative { display: grid; gap: 16px; max-width: 78ch; }
.kil-diagram { display: grid; gap: 18px; margin-top: 32px; }
.kil-band { padding-top: 16px; border-top: 1px solid var(--kil-line); }
.kil-rail { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 10px; }
.kil-tracks { display: grid; gap: 10px; }
.kil-track { display: grid; grid-template-columns: 150px repeat(4, minmax(0, 1fr)) 80px; gap: 8px; }
.kil-node { min-height: 64px; display: grid; place-items: center; padding: 8px; text-align: center; border: 1px solid var(--kil-line); }
.kil-unreachable { opacity: .68; border-style: dashed; }
.kil-evidence { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.kil-mobile-result { display: none; }
svg { display: block; width: 100%; height: auto; }
@media (max-width: 640px) {
  main, footer { padding: 14px; }
  .kil-rail, .kil-track, .kil-evidence { grid-template-columns: 1fr; }
  .kil-result-svg { display: none; }
  .kil-mobile-result { display: grid; gap: 8px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
```

Use this exact semantic body order and copy:

```html
<main id="kil-envoy-counterfactual">
  <header class="kil-narrative">
    <p>Kinetic Infrastructure Layer · Executive counterfactual</p>
    <h1>Why ambient breach requires ambient enforcement</h1>
    <p>Cybersecurity is currently at an inflection point where reliance on static or AI-Assisted SOC (Security Operations Centers) and traditional AI-augmented controls is no longer sufficient to counter modern, adversarial AI.</p>
    <p>To remain effective, the practice must transcend the legacy detect-and-prevent paradigm and evolve into a state of ambient enforcement. We are transitioning from a landscape of ‘ambient risk’ and ‘ambient threat’ into an era of pervasive, continuous ‘ambient breach’, necessitating a shift toward autonomous, real-time mitigation that functions at speed and scale independent of human intervention.</p>
    <p>Ambient enforcement represents this critical evolution by decoupling defenses from static, procedural constraints and utilizing kinetic infrastructure to match the velocity of AI adversaries in real time. By leveraging the same transport mechanisms as the threat itself and instantiating immutable controls that enforce security through physics, we move toward a future where cybersecurity functions not as a reactive overlay, but as an autonomous, omnipresent force capable of neutralizing AI-driven threats with the same speed and adaptability as the intelligence it seeks to contain.</p>
    <p><strong>Interpretive boundary:</strong> pervasive, continuous ambient breach names the operating condition in which service and attack cannot reliably be distinguished before consequence; it does not mean every system is continuously compromised.</p>
  </header>

  <section class="kil-diagram" id="diagram" aria-label="Counterfactual-first Envoy laboratory composition">
    <section class="kil-band" data-band="observed">
      <h2>01 · Observed incident</h2>
      <p>Authenticated, service-like activity carried attack through ordinary interfaces before consequence.</p>
      <div class="kil-rail" aria-label="Published incident dependency sequence">
        <div class="kil-node">Worker foothold</div>
        <div class="kil-node">Cluster API request</div>
        <div class="kil-node">Cloud and node privilege</div>
        <div class="kil-node">136-key secret read</div>
        <div class="kil-node">Cross-cluster access</div>
        <div class="kil-node">Mesh enrollment</div>
        <div class="kil-node">Token and CI pivot</div>
      </div>
      <p>First mediated action normalized into a harmless request.</p>
    </section>

    <section class="kil-band" data-band="lab">
      <h2>02 · Envoy lab model</h2>
      <p>KTP supplies supervision plus tighten-only constraints; the Envoy adapter derives the transport effect.</p>
      <div class="kil-tracks" aria-label="Three isolated Envoy laboratory tracks">
        <div class="kil-track"><strong>A · Credential policy</strong><span class="kil-node">Driver</span><span class="kil-node">Envoy</span><span class="kil-node">Policy authz</span><span class="kil-node">Target marker 1</span><strong>HTTP 200</strong></div>
        <div class="kil-track"><strong>B · Signed composite KTP state</strong><span class="kil-node">Driver</span><span class="kil-node">Envoy</span><span class="kil-node">Signature + freshness</span><span class="kil-node">Target marker 1</span><strong>HTTP 200</strong></div>
        <div class="kil-track"><strong>C · State + local reduction</strong><span class="kil-node">Driver</span><span class="kil-node">Envoy</span><span class="kil-node">0.95 modeled divergence</span><span class="kil-node kil-unreachable">Target marker 0</span><strong>derived HTTP 403</strong></div>
      </div>
      <p>Modeled process contract: 200 / 200 / 403 · target markers 1 / 1 / 0.</p>
    </section>

    <section class="kil-band" data-band="result">
      <h2>03 · KIL counterfactual result</h2>
      <svg class="kil-result-svg" viewBox="0 0 1000 250" role="img" aria-labelledby="kil-result-title kil-result-desc">
        <title id="kil-result-title">Modeled KIL cutoff at the Envoy boundary</title>
        <desc id="kil-result-desc">Signed composite KTP state plus modeled local reduction reaches the Envoy boundary, where an HTTP 403 is derived and dependent downstream phases become conditionally unreachable.</desc>
        <rect x="40" y="75" width="250" height="100" rx="10" fill="none" stroke="currentColor"/>
        <text x="165" y="120" text-anchor="middle" fill="currentColor">Signed state + local reduction</text>
        <text x="165" y="148" text-anchor="middle" fill="currentColor">action-scale authority check</text>
        <path d="M290 125H430" stroke="currentColor" stroke-width="4"/>
        <rect x="430" y="35" width="26" height="180" rx="4" fill="currentColor"/>
        <text x="443" y="236" text-anchor="middle" fill="currentColor">derived HTTP 403</text>
        <path d="M456 125H940" stroke="currentColor" stroke-width="3" stroke-dasharray="10 8" opacity=".55"/>
        <text x="700" y="105" text-anchor="middle" fill="currentColor">Conditionally unreachable</text>
        <text x="700" y="145" text-anchor="middle" fill="currentColor">cloud privilege · secrets · cross-cluster · mesh · CI</text>
      </svg>
      <div class="kil-mobile-result" aria-label="Modeled KIL cutoff at the Envoy boundary">
        <strong>Signed state + modeled local reduction → derived HTTP 403</strong>
        <span>Conditionally unreachable: cloud privilege, secrets, cross-cluster access, mesh enrollment, and CI pivot.</span>
      </div>
      <div class="kil-evidence">
        <p><strong>Observed</strong><br>Published incident sequence</p>
        <p><strong>Modeled</strong><br>0.95 reduction and derived transport outcomes</p>
        <p><strong>Pending validation</strong><br>Accepted V3B-1 live enforcement result</p>
      </div>
    </section>
  </section>
</main>
```

Retain the Task 1 footer after `</main>`.

- [ ] **Step 4: Run the focused contract and verify all tests pass**

Run the command from Step 2.

Expected: four tests run and `OK`.

- [ ] **Step 5: Commit the standalone diagram**

```bash
git add docs/demo/envoy-lab-counterfactual-first.html tests/test_envoy_counterfactual_diagram.py
git commit -m "feat: add counterfactual-first Envoy diagram"
```

### Task 3: Integrate the approved semantics into Presenter/Audience mode

**Files:**

- Modify: `tests/test_envoy_counterfactual_diagram.py`
- Modify: `docs/demo/kil-presenter-audience-demo.html:104-220`
- Modify: `docs/demo/kil-presenter-audience-demo.html:500-558`

- [ ] **Step 1: Add the failing integration contract**

Add to `CounterfactualDiagramTest`:

```python
    def test_presenter_audience_uses_the_counterfactual_renderer_and_copy(self):
        html = DEMO.read_text(encoding="utf-8")
        for exact in (
            '"visual": "lab-mapping"',
            "function renderLabMapping(",
            "KTP result: supervision + tighten-only constraints",
            "Envoy-derived effect: HTTP 403",
            "Observed · modeled · pending validation",
            "not a KTP wire decision",
        ):
            with self.subTest(exact=exact):
                self.assertIn(exact, html)

    def test_standalone_is_linked_from_the_showcase_documentation(self):
        readme = README.read_text(encoding="utf-8")
        self.assertIn("docs/demo/envoy-lab-counterfactual-first.html", readme)
```

- [ ] **Step 2: Run the focused test and verify both integration tests fail**

Run:

```bash
PYTHONPATH=src "/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python" -m unittest tests.test_envoy_counterfactual_diagram -v
```

Expected: the new renderer/copy test and README link test fail.

- [ ] **Step 3: Update the ambient-breach primer copy**

Keep the scene ID, order, evidence status, and visual ID unchanged. Replace the
`primer-ambient-breach` takeaway and script with:

```json
"takeaway": "When service and attack become indistinguishable before consequence, enforcement must operate continuously at the consequential boundary.",
"script": "Cybersecurity is at an inflection point. Frontier systems can discover, chain, and execute attacks at machine speed while using authentic credentials and ordinary service interfaces. That moved us from ambient risk through ambient threat into ambient breach: the operating condition in which service and attack cannot reliably be distinguished before consequence. It does not mean every system is continuously compromised. It means retrospective detection and human response can no longer remain the primary control. Ambient enforcement is the required evolution.",
```

The script is 75 words and remains inside the existing 70–90-word contract.

- [ ] **Step 4: Update only the lab-mapping scene record**

Keep its scene ID and order. Replace its title, takeaway, script, source, and
visual with:

```json
"title": "Observed breach, controlled lab, bounded result",
"takeaway": "The lab isolates one mediated action and shows where reducing-only KIL evidence changes the derived transport effect.",
"script": "Start with the observed incident rail: a worker foothold expanded into control-plane access and dependent escalation. The lab maps only the first mediated cluster API request into three harmless, isolated Envoy tracks. KTP supplies supervision plus tighten-only constraints; HTTP status is an Envoy-derived effect, not a KTP wire decision. Tracks A and B reach their targets. Track C applies the modeled local reduction, derives HTTP four hundred three, and leaves dependent phases conditionally unreachable. Live V3B-1 enforcement remains pending.",
"source": "Hugging Face technical timeline; KTP v2.0.0; KIL V3A process contract and V3B-1 gate status.",
"visual": "lab-mapping"
```

The script is 79 words.

- [ ] **Step 5: Replace the lab-mapping renderer with the approved inline SVG**

Replace only the body of `renderLabMapping()`. Keep its function name and the
existing `lab-mapping` renderer-map key so the current closed scene contract
remains intact. Use `svgShell()` so the existing browser verifier still finds
exactly one accessible SVG. The replacement must include these exact labels
and a three-band layout:

```javascript
function renderLabMapping() {
  return svgShell(
    'Observed incident, controlled Envoy lab, and bounded KIL counterfactual',
    'The source-cited incident maps one mediated cluster API request into three isolated harmless Envoy tracks. The modeled local-reduction track derives HTTP 403 and makes dependent descendants conditionally unreachable; live V3B-1 enforcement remains pending.',
    `<text x="45" y="38" class="diagram-label">01 · OBSERVED INCIDENT</text>
     <text x="45" y="70" class="diagram-small">worker foothold → cluster API → cloud and node privilege → 136-key secret read → cross-cluster, mesh, token and CI pivot</text>
     <path d="M45 94H955" class="diagram-red" marker-end="url(#arrow-red)"/>
     <text x="45" y="140" class="diagram-label">02 · ENVOY LAB MODEL</text>
     <text x="45" y="168" class="diagram-small">Same harmless normalized request · KTP result: supervision + tighten-only constraints</text>
     <rect x="45" y="190" width="910" height="62" rx="9" class="diagram-panel"/>
     <text x="65" y="228" class="diagram-text">A · credential policy</text><text x="735" y="228" class="diagram-small">HTTP 200 · target 1</text>
     <rect x="45" y="266" width="910" height="62" rx="9" class="diagram-panel"/>
     <text x="65" y="304" class="diagram-text">B · signed composite KTP state</text><text x="735" y="304" class="diagram-small">HTTP 200 · target 1</text>
     <rect x="45" y="342" width="910" height="62" rx="9" class="diagram-panel"/>
     <text x="65" y="380" class="diagram-text">C · state + 0.95 modeled local reduction</text><text x="680" y="380" class="diagram-small">Envoy-derived effect: HTTP 403 · target 0</text>
     <text x="45" y="450" class="diagram-label">03 · KIL COUNTERFACTUAL RESULT</text>
     <path d="M45 482H360" class="diagram-blue" marker-end="url(#arrow-blue)"/>
     <rect x="370" y="455" width="24" height="64" class="diagram-blue-fill"/>
     <path d="M394 482H955" class="diagram-line" stroke-dasharray="10 8"/>
     <text x="670" y="475" text-anchor="middle" class="diagram-small">Conditionally unreachable · not separately detected</text>
     <text x="670" y="508" text-anchor="middle" class="diagram-small">Observed · modeled · pending validation · not a KTP wire decision</text>`
  );
}
```

Leave the existing renderer map entry unchanged:

```javascript
'lab-mapping': renderLabMapping,
```

- [ ] **Step 6: Add the standalone link to README**

After the Presenter/Audience opening instructions, add:

```markdown
The approved counterfactual-first Envoy laboratory diagram is also available as
a standalone executive presentation at
[`docs/demo/envoy-lab-counterfactual-first.html`](docs/demo/envoy-lab-counterfactual-first.html).
It separates the observed incident, modeled process-contract result, and pending
V3B-1 live validation.
```

- [ ] **Step 7: Run focused and existing demo contracts**

Run:

```bash
PYTHONPATH=src "/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python" -m unittest tests.test_envoy_counterfactual_diagram tests.test_presenter_audience_demo -v
```

Expected: all tests pass. If the existing demo contract fails solely because
it requires superseded KTP outcome language, stop and present the exact failure
without editing that test.

- [ ] **Step 8: Commit the synchronized integration**

```bash
git add docs/demo/kil-presenter-audience-demo.html README.md tests/test_envoy_counterfactual_diagram.py
git commit -m "feat: integrate Envoy counterfactual diagram"
```

### Task 4: Add standalone Brave visual verification

**Files:**

- Create: `tools/verify_envoy_counterfactual_diagram.mjs`

- [ ] **Step 1: Create the read-only visual verifier**

Create `tools/verify_envoy_counterfactual_diagram.mjs`:

```javascript
import { createServer } from 'node:http';
import { existsSync } from 'node:fs';
import { mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const documentPath = resolve('docs/demo/envoy-lab-counterfactual-first.html');
const html = await readFile(documentPath);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const server = createServer((request, response) => {
  const url = new URL(request.url ?? '/', 'http://127.0.0.1');
  if (url.pathname === '/favicon.ico') {
    response.writeHead(204);
    response.end();
    return;
  }
  if (url.pathname !== '/') {
    response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
    response.end('not found');
    return;
  }
  response.writeHead(200, {
    'content-type': 'text/html; charset=utf-8',
    'cache-control': 'no-store',
  });
  response.end(html);
});

await new Promise((resolveListen, rejectListen) => {
  server.once('error', rejectListen);
  server.listen(0, '127.0.0.1', resolveListen);
});

const address = server.address();
assert(address && typeof address === 'object', 'server did not expose an address');
const bravePath = '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser';
const browserName = existsSync(bravePath) ? 'Brave' : 'Playwright Chromium';
const browser = await chromium.launch({
  headless: true,
  executablePath: existsSync(bravePath) ? bravePath : chromium.executablePath(),
});
const page = await browser.newPage();
const failures = [];
page.on('pageerror', error => failures.push(`pageerror: ${error.message}`));
page.on('console', message => {
  if (['error', 'warning'].includes(message.type())) failures.push(`console: ${message.text()}`);
});

try {
  await page.goto(`http://127.0.0.1:${address.port}/`);
  for (const width of [1440, 736, 360]) {
    await page.setViewportSize({ width, height: 1000 });
    const dimensions = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    assert(dimensions.scrollWidth <= dimensions.clientWidth, `${width}px horizontal overflow`);
    assert(await page.locator('[data-band]').count() === 3, `${width}px missing bands`);
    assert(await page.locator('svg[role="img"] title').count() === 1, `${width}px missing SVG title`);
    assert(await page.locator('svg[role="img"] desc').count() === 1, `${width}px missing SVG description`);
    if (width === 360) assert(await page.locator('.kil-mobile-result').isVisible(), 'mobile result hidden');
  }
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  assert(await page.locator('[data-band="result"]').isVisible(), 'dark result band hidden');
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'no-preference' });
  assert(failures.length === 0, failures.join('\n'));

  if (process.env.KIL_COUNTERFACTUAL_SCREENSHOTS === '1') {
    const output = resolve('artifacts/generated/kil-counterfactual-preview');
    await mkdir(output, { recursive: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({ path: resolve(output, 'standalone.png'), fullPage: true });
  }
  console.log(`envoy counterfactual verifier (${browserName}): PASS`);
} finally {
  await browser.close();
  await new Promise(resolveClose => server.close(resolveClose));
}
```

- [ ] **Step 2: Run the standalone verifier in Brave**

Run:

```bash
node tools/verify_envoy_counterfactual_diagram.mjs
```

Expected: `envoy counterfactual verifier (Brave): PASS` when Brave is
installed, otherwise the Playwright Chromium pass message.

- [ ] **Step 3: Run the existing Presenter/Audience verifier**

Run:

```bash
node tools/verify_presenter_audience_demo.mjs
```

Expected: `presenter-audience browser verifier (Brave): PASS` and no console,
runtime, accessibility, or overflow errors.

- [ ] **Step 4: Generate review-only screenshots**

Run:

```bash
KIL_COUNTERFACTUAL_SCREENSHOTS=1 node tools/verify_envoy_counterfactual_diagram.mjs
KIL_DEMO_SCREENSHOTS=1 node tools/verify_presenter_audience_demo.mjs
```

Inspect:

- `artifacts/generated/kil-counterfactual-preview/standalone.png`;
- `artifacts/generated/kil-demo-preview/case-first-divergence.png`; and
- `artifacts/generated/kil-demo-preview/case-three-tracks.png`.

Screenshots are review outputs and must remain untracked. Confirm that the
three bands are legible, the mapped action is unambiguous, evidence labels are
visible, and no pending result looks validated.

- [ ] **Step 5: Commit the verifier**

```bash
git add tools/verify_envoy_counterfactual_diagram.mjs
git commit -m "test: verify Envoy counterfactual presentation"
```

### Task 5: Record lineage and run the final protected gate

**Files:**

- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Modify: `docs/superpowers/plans/2026-09-01-envoy-lab-counterfactual-first-diagram.md`

- [ ] **Step 1: Append the implementation lineage entry**

Append a dated entry recording:

- founder execution approval;
- standalone and synchronized deliverables;
- exact observed/modelled/pending evidence treatment;
- KTP supervision plus tighten-only semantics and derived HTTP effects;
- focused and full verification commands and results;
- confirmation that no current lab or live service started;
- screenshot locations and review disposition;
- unresolved graphic-intensive Presenter/Audience redesign; and
- the next approval gate.

End the entry with:

```markdown
KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
```

- [ ] **Step 2: Mark completed plan steps**

Change only completed checkbox markers in this plan from `[ ]` to `[x]`. Do
not rewrite planned commands or expected results.

- [ ] **Step 3: Run the complete repository test gate**

Run:

```bash
PYTHONPATH=src "/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python" -m unittest discover -s tests -v
```

Expected: all tests pass. Record the exact test count in lineage. Do not claim
the historical breach was prevented and do not promote V3B-1 from pending.

- [ ] **Step 4: Run both browser verifiers again**

```bash
node tools/verify_envoy_counterfactual_diagram.mjs
node tools/verify_presenter_audience_demo.mjs
```

Expected: both pass in Brave when installed.

- [ ] **Step 5: Enforce the protected-path diff**

Run from the feature worktree:

```bash
git diff --check
git status --short
git diff --name-only b49fe10..HEAD
```

For this implementation phase, every changed path must be in the allowlist at
the top of this plan. Stop if the diff contains any existing test other than
the newly created isolated contract, or any fixture, scenario, schema, source,
adapter, deployment, controller, evidence, artifact, container, or laboratory
path.

- [ ] **Step 6: Commit the lineage and completed plan**

```bash
git add docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md docs/superpowers/plans/2026-09-01-envoy-lab-counterfactual-first-diagram.md
git commit -m "docs: record Envoy counterfactual implementation"
```

- [ ] **Step 7: Verify the final commit state**

Run:

```bash
git status --short
git log -5 --oneline --decorate
```

Expected: empty status and the implementation-lineage commit at `HEAD`.

## Final founder gate

Present the standalone diagram and synchronized scene for founder review. Do
not merge, push, replace the existing public showcase, start V3B-1, or begin the
graphic-intensive Presenter/Audience redesign until the founder accepts the
implemented semantic baseline and chooses the next action.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
