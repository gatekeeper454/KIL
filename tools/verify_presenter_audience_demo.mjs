import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
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
  const value = (await locator.textContent())?.trim() ?? '';
  assert(value.includes(expected), `${selector} expected to include ${JSON.stringify(expected)}, received ${JSON.stringify(value)}`);
}

async function assertVisible(page, selector) {
  assert(await page.locator(selector).isVisible(), `${selector} expected visible`);
}

async function assertHidden(page, selector) {
  assert(await page.locator(selector).isHidden(), `${selector} expected hidden`);
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
const browser = await chromium.launch({
  headless: true,
  executablePath: chromium.executablePath(),
});
const context = await browser.newContext({ viewport: { width: 1024, height: 900 } });
const presenter = await context.newPage();
const audience = await context.newPage();
const runtimeErrors = [];

for (const page of [presenter, audience]) {
  page.on('pageerror', error => runtimeErrors.push(`pageerror: ${error.message}`));
  page.on('console', message => {
    if (message.type() === 'error') runtimeErrors.push(`console: ${message.text()}`);
  });
}

try {
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

  assert(runtimeErrors.length === 0, runtimeErrors.join('\n'));
  console.log('presenter-audience browser verifier: PASS');
} finally {
  await browser.close();
  await new Promise(resolveClose => server.close(resolveClose));
}
