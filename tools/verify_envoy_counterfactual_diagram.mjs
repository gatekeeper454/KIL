import { createServer } from 'node:http';
import { existsSync } from 'node:fs';
import { mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const standaloneHtmlPath = resolve('docs/demo/envoy-lab-counterfactual-first.html');
const presenterHtmlPath = resolve('docs/demo/kil-presenter-audience-demo.html');
const [standaloneHtml, presenterHtml] = await Promise.all([
  readFile(standaloneHtmlPath),
  readFile(presenterHtmlPath),
]);
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

async function assertNoHorizontalOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
  }));
  assert(
    dimensions.scrollWidth <= dimensions.clientWidth,
    `${label} overflowed horizontally: ${dimensions.scrollWidth} > ${dimensions.clientWidth}`,
  );
}

async function assertChildrenContained(locator, label, tolerance = 1) {
  const geometry = await locator.evaluate((container, allowed) => {
    const containerRect = container.getBoundingClientRect();
    const children = [...container.querySelectorAll('*')]
      .filter(child => {
        const style = getComputedStyle(child);
        return style.display !== 'none' && style.visibility !== 'hidden' && child.getClientRects().length > 0;
      })
      .map(child => {
        const rect = child.getBoundingClientRect();
        return {
          tag: child.tagName.toLowerCase(),
          className: child.getAttribute('class') ?? '',
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
        };
      });
    return {
      clientWidth: container.clientWidth,
      clientHeight: container.clientHeight,
      scrollWidth: container.scrollWidth,
      scrollHeight: container.scrollHeight,
      offenders: children.filter(child => (
        child.left < containerRect.left - allowed
        || child.top < containerRect.top - allowed
        || child.right > containerRect.right + allowed
        || child.bottom > containerRect.bottom + allowed
      )),
    };
  }, tolerance);
  assert(
    geometry.scrollWidth <= geometry.clientWidth + tolerance
      && geometry.scrollHeight <= geometry.clientHeight + tolerance,
    `${label} scroll geometry overflowed: ${geometry.scrollWidth}x${geometry.scrollHeight} > ${geometry.clientWidth}x${geometry.clientHeight}; children: ${JSON.stringify(geometry.offenders)}`,
  );
  assert(
    geometry.offenders.length === 0,
    `${label} contained overflowing children: ${JSON.stringify(geometry.offenders)}`,
  );
}

async function assertSvgContentsInViewBox(svg, label, tolerance = 2) {
  const geometry = await svg.evaluate((element, allowed) => {
    const viewBox = element.viewBox.baseVal;
    const bounds = {
      left: viewBox.x,
      top: viewBox.y,
      right: viewBox.x + viewBox.width,
      bottom: viewBox.y + viewBox.height,
    };
    const graphics = [...element.querySelectorAll('*')]
      .filter(child => (
        child instanceof SVGGraphicsElement
        && !child.closest('defs')
        && getComputedStyle(child).display !== 'none'
      ));
    const offenders = [];
    for (const child of graphics) {
      const box = child.getBBox();
      if (
        box.x < bounds.left - allowed
        || box.y < bounds.top - allowed
        || box.x + box.width > bounds.right + allowed
        || box.y + box.height > bounds.bottom + allowed
      ) {
        offenders.push({
          tag: child.tagName.toLowerCase(),
          text: child.textContent?.trim() ?? '',
          x: box.x,
          y: box.y,
          width: box.width,
          height: box.height,
        });
      }
    }
    return { viewBox: bounds, graphicalElementCount: graphics.length, offenders };
  }, tolerance);
  assert(geometry.graphicalElementCount > 0, `${label} expected graphical SVG elements`);
  assert(
    geometry.offenders.length === 0,
    `${label} had elements outside ${JSON.stringify(geometry.viewBox)}: ${JSON.stringify(geometry.offenders)}`,
  );
}

async function assertAccessibleSvg(page, label) {
  const titles = page.locator('svg[role="img"] title');
  const descriptions = page.locator('svg[role="img"] desc');
  assert(await titles.count() === 1, `${label} expected exactly one SVG title`);
  assert(await descriptions.count() === 1, `${label} expected exactly one SVG description`);
  assert((await titles.textContent())?.trim(), `${label} SVG title is empty`);
  assert((await descriptions.textContent())?.trim(), `${label} SVG description is empty`);
}

async function assertStandaloneViewport(page, width) {
  const label = `standalone ${width}px`;
  await page.setViewportSize({ width, height: 1000 });
  await assertNoHorizontalOverflow(page, label);

  const bands = page.locator('[data-band]');
  assert(await bands.count() === 3, `${label} expected exactly three data bands`);
  const bandOrder = await bands.evaluateAll(elements => elements.map(element => element.dataset.band));
  assert(
    JSON.stringify(bandOrder) === JSON.stringify(['observed', 'lab', 'result']),
    `${label} had unexpected data-band order: ${bandOrder.join(', ')}`,
  );
  for (const band of ['observed', 'lab', 'result']) {
    await assertVisibleBox(page.locator(`[data-band="${band}"]`), `${label} ${band} band`);
  }

  await assertAccessibleSvg(page, label);
  const marker = page.locator('.kil-mapped-action');
  assert(await marker.count() === 1, `${label} expected one mapped-action marker`);
  await assertVisibleBox(marker, `${label} mapped-action marker`);
  const markerText = (await marker.textContent())?.trim() ?? '';
  assert(markerText.includes('Cluster API'), `${label} mapped-action marker expected to identify Cluster API`);

  const rail = page.locator('.kil-rail');
  await assertChildrenContained(rail, `${label} incident rail`);
  const tracks = page.locator('.kil-track');
  assert(await tracks.count() === 3, `${label} expected three lab tracks`);
  for (let index = 0; index < await tracks.count(); index += 1) {
    await assertChildrenContained(tracks.nth(index), `${label} lab track ${index + 1}`);
  }

  const evidence = page.locator('.kil-evidence');
  await assertVisibleBox(evidence, `${label} evidence`);
  await assertChildrenContained(evidence, `${label} evidence`);
  const evidenceItems = evidence.locator('.kil-evidence-item');
  const expectedEvidenceLabels = ['Observed', 'Modeled', 'Pending validation'];
  assert(await evidenceItems.count() === 3, `${label} expected three evidence items`);
  for (let index = 0; index < expectedEvidenceLabels.length; index += 1) {
    const item = evidenceItems.nth(index);
    await assertVisibleBox(item, `${label} evidence item ${index + 1}`);
    const itemLabel = (await item.locator('.kil-evidence-label').textContent())?.trim() ?? '';
    assert(
      itemLabel === expectedEvidenceLabels[index],
      `${label} evidence item ${index + 1} expected ${JSON.stringify(expectedEvidenceLabels[index])}, received ${JSON.stringify(itemLabel)}`,
    );
  }

  const resultSvg = page.locator('.kil-result-svg');
  const mobileResult = page.locator('.kil-mobile-result');
  assert(await resultSvg.count() === 1, `${label} expected one result SVG`);
  assert(await mobileResult.count() === 1, `${label} expected one mobile result`);
  if (width > 760) {
    await assertVisibleBox(resultSvg, `${label} result SVG`);
    assert(await mobileResult.isHidden(), `${label} mobile result expected hidden`);
    await assertSvgContentsInViewBox(resultSvg, `${label} result SVG`);
  } else {
    assert(await resultSvg.isHidden(), `${label} result SVG expected hidden`);
    await assertVisibleBox(mobileResult, `${label} mobile result`);
    await assertChildrenContained(mobileResult, `${label} mobile result`);
  }

  const pageText = (await page.locator('body').innerText()).toLowerCase();
  for (const forbidden of ['validated live', 'microsecond enforcement']) {
    assert(!pageText.includes(forbidden), `${label} unexpectedly included ${JSON.stringify(forbidden)}`);
  }
}

async function selectPresenterMapping(page, base) {
  await page.goto(`${base}/presenter?mode=presenter&session=counterfactual-verifier`);
  await page.click('[data-act="case-study"]');
  await page.click('[data-scene-id="case-lab-mapping"]');
  await page.locator('[data-title]').filter({ hasText: 'Observed breach, controlled lab, bounded result' }).waitFor();
}

async function assertPresenterViewport(page, width) {
  const label = `presenter mapping ${width}px`;
  await page.setViewportSize({ width, height: 1000 });
  await assertNoHorizontalOverflow(page, label);
  await assertAccessibleSvg(page, label);

  const desktop = page.locator('.lab-mapping-desktop');
  const mobile = page.locator('.lab-mapping-mobile');
  assert(await desktop.count() === 1, `${label} expected one desktop mapping`);
  assert(await mobile.count() === 1, `${label} expected one mobile mapping`);
  const activeRepresentation = width > 640 ? desktop : mobile;
  if (width > 640) {
    await assertVisibleBox(desktop, `${label} desktop representation`);
    assert(await mobile.isHidden(), `${label} mobile representation expected hidden`);
    await assertSvgContentsInViewBox(desktop.locator('svg[role="img"]'), `${label} desktop SVG`);
  } else {
    assert(await desktop.isHidden(), `${label} desktop representation expected hidden`);
    await assertVisibleBox(mobile, `${label} mobile representation`);
    await assertChildrenContained(mobile, `${label} mobile representation`);

    const mobileBands = mobile.locator('.lab-mapping-band');
    assert(await mobileBands.count() === 3, `${label} expected three semantic mobile bands`);
    const expectedHeadings = [
      'Observed incident, controlled Envoy lab, and bounded KIL counterfactual',
      '01 · Observed incident',
      '02 · Envoy lab model',
      '03 · KIL counterfactual result',
    ];
    const headings = mobile.locator('h2, h3');
    assert(await headings.count() === expectedHeadings.length, `${label} expected four semantic headings`);
    for (let index = 0; index < expectedHeadings.length; index += 1) {
      const heading = headings.nth(index);
      await assertVisibleBox(heading, `${label} heading ${index + 1}`);
      const headingText = (await heading.textContent())?.trim() ?? '';
      assert(
        headingText === expectedHeadings[index],
        `${label} heading ${index + 1} expected ${JSON.stringify(expectedHeadings[index])}, received ${JSON.stringify(headingText)}`,
      );
    }
    for (let index = 0; index < await mobileBands.count(); index += 1) {
      await assertVisibleBox(mobileBands.nth(index), `${label} semantic band ${index + 1}`);
    }
    const mobileContent = mobile.locator('p, .lab-mapping-track');
    assert(await mobileContent.count() > 0, `${label} expected semantic mobile content`);
    for (let index = 0; index < await mobileContent.count(); index += 1) {
      await assertVisibleBox(mobileContent.nth(index), `${label} semantic content ${index + 1}`);
    }
  }

  const renderedTextNodes = width > 640
    ? activeRepresentation.locator('svg[role="img"] text')
    : activeRepresentation.locator('h2, h3, p, .lab-mapping-track span');
  const renderedTextCount = await renderedTextNodes.count();
  assert(renderedTextCount > 0, `${label} expected rendered semantic text nodes`);
  const renderedText = [];
  for (let index = 0; index < renderedTextCount; index += 1) {
    const textNode = renderedTextNodes.nth(index);
    await assertVisibleBox(textNode, `${label} rendered semantic text ${index + 1}`);
    const text = (await textNode.textContent())?.trim() ?? '';
    assert(text, `${label} rendered semantic text ${index + 1} expected nonempty content`);
    renderedText.push(text);
  }
  const activeText = renderedText.join(' ').toLowerCase();
  for (const requiredText of [
    'KTP result',
    'supervision',
    'Envoy-derived effect: HTTP 403',
    'Observed',
    'modeled',
    'pending validation',
    'not a KTP wire decision',
  ]) {
    assert(
      activeText.includes(requiredText.toLowerCase()),
      `${label} active representation expected ${JSON.stringify(requiredText)}`,
    );
  }
}

const server = createServer((request, response) => {
  const url = new URL(request.url ?? '/', 'http://127.0.0.1');
  if (url.pathname === '/favicon.ico') {
    response.writeHead(204, { 'cache-control': 'no-store' });
    response.end();
    return;
  }
  const routeHtml = new Map([
    ['/', standaloneHtml],
    ['/presenter', presenterHtml],
  ]).get(url.pathname);
  if (!routeHtml) {
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
  response.end(routeHtml);
});

try {
  await new Promise((resolveListen, rejectListen) => {
    server.once('error', rejectListen);
    server.listen(0, '127.0.0.1', resolveListen);
  });
  const address = server.address();
  assert(address && typeof address === 'object', 'local server did not expose an address');
  const base = `http://127.0.0.1:${address.port}`;

  browser = await chromium.launch({
    headless: true,
    executablePath: useBrave ? bravePath : chromium.executablePath(),
  });
  const standalonePage = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const presenterPage = await browser.newPage({ viewport: { width: 1024, height: 1000 } });
  for (const page of [standalonePage, presenterPage]) {
    page.on('pageerror', error => runtimeFailures.push(`pageerror: ${error.message}`));
    page.on('console', message => {
      if (['warning', 'error'].includes(message.type())) {
        runtimeFailures.push(`console ${message.type()}: ${message.text()}`);
      }
    });
  }

  await standalonePage.goto(`${base}/`);
  for (const width of [1440, 761, 760, 736, 641, 640, 360]) {
    await assertStandaloneViewport(standalonePage, width);
  }
  await standalonePage.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await assertVisibleBox(standalonePage.locator('[data-band="result"]'), 'dark reduced-motion result band');
  await standalonePage.emulateMedia({ colorScheme: 'light', reducedMotion: 'no-preference' });

  await selectPresenterMapping(presenterPage, base);
  for (const width of [1024, 736, 641, 640, 360]) {
    await assertPresenterViewport(presenterPage, width);
  }

  if (process.env.KIL_COUNTERFACTUAL_SCREENSHOTS === '1') {
    const standaloneDirectory = resolve('artifacts/generated/kil-counterfactual-preview');
    const presenterDirectory = resolve('artifacts/generated/kil-demo-preview');
    await Promise.all([
      mkdir(standaloneDirectory, { recursive: true }),
      mkdir(presenterDirectory, { recursive: true }),
    ]);
    await standalonePage.setViewportSize({ width: 1440, height: 1000 });
    await standalonePage.screenshot({
      path: resolve(standaloneDirectory, 'standalone-1440.png'),
      fullPage: true,
    });
    await standalonePage.screenshot({
      path: resolve(standaloneDirectory, 'standalone.png'),
      fullPage: true,
    });
    for (const width of [736, 360]) {
      await standalonePage.setViewportSize({ width, height: 1000 });
      await standalonePage.screenshot({
        path: resolve(standaloneDirectory, `standalone-${width}.png`),
        fullPage: true,
      });
    }

    await presenterPage.setViewportSize({ width: 1024, height: 1000 });
    await presenterPage.screenshot({
      path: resolve(presenterDirectory, 'case-lab-mapping.png'),
      fullPage: true,
    });
    await presenterPage.setViewportSize({ width: 360, height: 1000 });
    await presenterPage.screenshot({
      path: resolve(presenterDirectory, 'case-lab-mapping-mobile.png'),
      fullPage: true,
    });
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
