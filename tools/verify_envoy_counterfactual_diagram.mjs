import { createServer } from 'node:http';
import { existsSync } from 'node:fs';
import { mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const htmlPath = resolve('docs/demo/envoy-lab-counterfactual-first.html');
const html = await readFile(htmlPath);
const bravePath = '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser';
const useBrave = existsSync(bravePath);
const runtimeFailures = [];
let browser;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function assertVisibleBox(locator, label) {
  assert(await locator.isVisible(), `${label} expected visible`);
  const box = await locator.boundingBox();
  assert(box && box.width > 0 && box.height > 0, `${label} expected a nonzero bounding box`);
}

async function assertViewport(page, width) {
  await page.setViewportSize({ width, height: 1000 });

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
  }));
  assert(
    dimensions.scrollWidth <= dimensions.clientWidth,
    `${width}px viewport overflowed horizontally: ${dimensions.scrollWidth} > ${dimensions.clientWidth}`,
  );

  const bands = page.locator('[data-band]');
  assert(await bands.count() === 3, `${width}px viewport expected exactly three data bands`);
  const bandOrder = await bands.evaluateAll(elements => elements.map(element => element.dataset.band));
  assert(
    JSON.stringify(bandOrder) === JSON.stringify(['observed', 'lab', 'result']),
    `${width}px viewport had unexpected data-band order: ${bandOrder.join(', ')}`,
  );
  for (const band of ['observed', 'lab', 'result']) {
    await assertVisibleBox(page.locator(`[data-band="${band}"]`), `${width}px ${band} band`);
  }

  const titles = page.locator('svg[role="img"] title');
  const descriptions = page.locator('svg[role="img"] desc');
  assert(await titles.count() === 1, `${width}px viewport expected exactly one SVG title`);
  assert(await descriptions.count() === 1, `${width}px viewport expected exactly one SVG description`);
  assert((await titles.textContent())?.trim(), `${width}px viewport SVG title is empty`);
  assert((await descriptions.textContent())?.trim(), `${width}px viewport SVG description is empty`);

  const marker = page.locator('.kil-mapped-action');
  assert(await marker.count() === 1, `${width}px viewport expected one mapped-action marker`);
  await assertVisibleBox(marker, `${width}px mapped-action marker`);
  const markerText = (await marker.textContent())?.trim() ?? '';
  assert(markerText.includes('Cluster API'), `${width}px mapped-action marker expected to identify Cluster API`);

  const svg = page.locator('.kil-result-svg');
  const mobileResult = page.locator('.kil-mobile-result');
  assert(await mobileResult.count() === 1, `${width}px viewport expected one mobile result`);
  if (width === 1440) {
    await assertVisibleBox(svg, `${width}px result SVG`);
    assert(await mobileResult.isHidden(), `${width}px mobile result expected hidden`);
  } else {
    assert(await svg.isHidden(), `${width}px result SVG expected hidden`);
    await assertVisibleBox(mobileResult, `${width}px mobile result`);
  }

  const evidenceText = (await page.locator('.kil-evidence').textContent())?.trim() ?? '';
  for (const label of ['Observed', 'Modeled', 'Pending validation']) {
    assert(evidenceText.includes(label), `${width}px evidence expected to include ${JSON.stringify(label)}`);
  }
  const pageText = (await page.locator('body').innerText()).toLowerCase();
  for (const forbidden of ['validated live', 'microsecond enforcement']) {
    assert(!pageText.includes(forbidden), `${width}px page unexpectedly included ${JSON.stringify(forbidden)}`);
  }
}

const server = createServer((request, response) => {
  const url = new URL(request.url ?? '/', 'http://127.0.0.1');
  if (url.pathname === '/favicon.ico') {
    response.writeHead(204, { 'cache-control': 'no-store' });
    response.end();
    return;
  }
  if (url.pathname !== '/') {
    response.writeHead(404, {
      'content-type': 'text/plain; charset=utf-8',
      'cache-control': 'no-store',
    });
    response.end('not found');
    return;
  }
  response.writeHead(200, {
    'content-type': 'text/html; charset=utf-8',
    'cache-control': 'no-store',
  });
  response.end(html);
});

try {
  await new Promise((resolveListen, rejectListen) => {
    server.once('error', rejectListen);
    server.listen(0, '127.0.0.1', resolveListen);
  });
  const address = server.address();
  assert(address && typeof address === 'object', 'local server did not expose an address');

  browser = await chromium.launch({
    headless: true,
    executablePath: useBrave ? bravePath : chromium.executablePath(),
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', error => runtimeFailures.push(`pageerror: ${error.message}`));
  page.on('console', message => {
    if (['warning', 'error'].includes(message.type())) {
      runtimeFailures.push(`console ${message.type()}: ${message.text()}`);
    }
  });

  await page.goto(`http://127.0.0.1:${address.port}/`);
  for (const width of [1440, 736, 641, 360]) {
    await assertViewport(page, width);
  }

  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await assertVisibleBox(page.locator('[data-band="result"]'), 'dark reduced-motion result band');
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'no-preference' });

  if (process.env.KIL_COUNTERFACTUAL_SCREENSHOTS === '1') {
    const screenshotDirectory = resolve('artifacts/generated/kil-counterfactual-preview');
    await mkdir(screenshotDirectory, { recursive: true });
    for (const width of [1440, 736, 360]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.screenshot({
        path: resolve(screenshotDirectory, `standalone-${width}.png`),
        fullPage: true,
      });
    }
  }

  assert(runtimeFailures.length === 0, runtimeFailures.join('\n'));
  console.log(`envoy counterfactual verifier (${useBrave ? 'Brave' : 'Playwright Chromium'}): PASS`);
} finally {
  try {
    if (browser) await browser.close();
  } finally {
    if (server.listening) await new Promise(resolveClose => server.close(resolveClose));
  }
}
