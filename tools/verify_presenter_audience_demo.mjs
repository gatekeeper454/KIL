import { createServer } from 'node:http';
import { existsSync } from 'node:fs';
import { mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';


const require = createRequire(import.meta.url);
const { chromium } = require('playwright');


const demoPath = resolve('docs/demo/kil-presenter-audience-demo.html');
const html = await readFile(demoPath);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function expectText(page, selector, expected) {
  const locator = page.locator(selector);
  await locator.waitFor({ state: 'attached' });
  const deadline = Date.now() + 3000;
  let value = '';
  while (Date.now() < deadline) {
    value = (await locator.textContent())?.trim() ?? '';
    if (value.includes(expected)) return;
    await page.waitForTimeout(25);
  }
  throw new Error(`${selector} expected to include ${JSON.stringify(expected)}, received ${JSON.stringify(value)}`);
}

async function assertNotText(page, selector, unexpected) {
  const value = (await page.locator(selector).textContent())?.trim() ?? '';
  assert(!value.includes(unexpected), `${selector} unexpectedly included ${JSON.stringify(unexpected)}`);
}

async function assertVisible(page, selector) {
  assert(await page.locator(selector).isVisible(), `${selector} expected visible`);
}

async function assertHidden(page, selector) {
  assert(await page.locator(selector).isHidden(), `${selector} expected hidden`);
}

async function assertNoHorizontalOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(
    dimensions.scrollWidth <= dimensions.clientWidth,
    `${label} overflowed horizontally: ${dimensions.scrollWidth} > ${dimensions.clientWidth}`,
  );
}

async function assertAccessibleSvg(page, label) {
  const svg = page.locator('[data-visual] svg');
  assert(await svg.count() === 1, `${label} expected exactly one SVG`);
  assert((await svg.locator('title').textContent())?.trim(), `${label} SVG title is empty`);
  assert((await svg.locator('desc').textContent())?.trim(), `${label} SVG description is empty`);
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
assert(address && typeof address === 'object', 'local server did not expose an address');
const base = `http://127.0.0.1:${address.port}`;
const bravePath = '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser';
const browserName = existsSync(bravePath) ? 'Brave' : 'Playwright Chromium';
const browser = await chromium.launch({
  headless: true,
  executablePath: existsSync(bravePath) ? bravePath : chromium.executablePath(),
});
const context = await browser.newContext({ viewport: { width: 1024, height: 900 } });
const presenter = await context.newPage();
const audience = await context.newPage();
const wrongAudience = await context.newPage();
const runtimeErrors = [];

for (const page of [presenter, audience, wrongAudience]) {
  page.on('pageerror', error => runtimeErrors.push(`pageerror: ${error.message}`));
  page.on('console', message => {
    if (['error', 'warning'].includes(message.type())) runtimeErrors.push(`console: ${message.text()}`);
  });
}

try {
  await presenter.goto(`${base}/?mode=presenter&session=showcase`);
  await audience.goto(`${base}/?mode=audience&session=showcase`);
  await wrongAudience.goto(`${base}/?mode=audience&session=other-session`);

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

  await presenter.click('[data-act="case-study"]');
  await presenter.click('[data-scene-id="case-first-divergence"]');
  await expectText(audience, '[data-title]', 'The first mediated divergence');
  await expectText(presenter, '[data-sync-status]', 'Audience synchronized');
  await assertNotText(wrongAudience, '[data-title]', 'The first mediated divergence');

  await presenter.reload();
  await presenter.click('[data-act="case-study"]');
  await presenter.click('[data-scene-id="case-evidence"]');
  await expectText(audience, '[data-title]', 'What is evidence today?');

  for (const act of ['primer', 'case-study']) {
    await presenter.click(`[data-act="${act}"]`);
    const sceneIds = await presenter.locator('[data-scene-id]').evaluateAll(buttons => buttons.map(button => button.dataset.sceneId));
    for (const sceneId of sceneIds) {
      await presenter.click(`[data-scene-id="${sceneId}"]`);
      await assertAccessibleSvg(presenter, sceneId);
    }
  }

  for (const width of [1024, 736, 360]) {
    await presenter.setViewportSize({ width, height: 900 });
    await audience.setViewportSize({ width, height: 900 });
    await assertNoHorizontalOverflow(presenter, `presenter ${width}px`);
    await assertNoHorizontalOverflow(audience, `audience ${width}px`);
  }

  await presenter.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await assertAccessibleSvg(presenter, 'dark reduced-motion view');
  await presenter.emulateMedia({ colorScheme: 'light', reducedMotion: 'no-preference' });
  const buttonTags = await presenter.locator('button').evaluateAll(buttons => buttons.map(button => button.tagName));
  assert(buttonTags.length > 0 && buttonTags.every(tag => tag === 'BUTTON'), 'controls must use native buttons');

  if (process.env.KIL_DEMO_SCREENSHOTS === '1') {
    const screenshotDirectory = resolve('artifacts/generated/kil-demo-preview');
    await mkdir(screenshotDirectory, { recursive: true });
    await presenter.setViewportSize({ width: 1440, height: 1000 });
    await presenter.click('[data-act="primer"]');
    await presenter.click('[data-scene-id="primer-ktp-extension"]');
    await presenter.screenshot({ path: resolve(screenshotDirectory, 'primer-ktp-extension.png'), fullPage: true });
    await presenter.click('[data-act="case-study"]');
    await presenter.click('[data-scene-id="case-first-divergence"]');
    await presenter.screenshot({ path: resolve(screenshotDirectory, 'case-first-divergence.png'), fullPage: true });
    await presenter.click('[data-scene-id="case-three-tracks"]');
    await presenter.screenshot({ path: resolve(screenshotDirectory, 'case-three-tracks.png'), fullPage: true });
  }

  assert(runtimeErrors.length === 0, runtimeErrors.join('\n'));
  console.log(`presenter-audience browser verifier (${browserName}): PASS`);
} finally {
  await browser.close();
  await new Promise(resolveClose => server.close(resolveClose));
}
