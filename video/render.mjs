// Drives the player's offline page in headless Chrome.
//   node render.mjs simulate <shot.json> <meta.json>
//   node render.mjs render   <shot.json> <crops.json> <outDir> [--map]
// Needs the built player served at $PLAYER_URL (default http://localhost:4173).
// Chrome: $CHROME_PATH, else @sparticuz/chromium (bundled, works without a system browser).
import fs from 'node:fs/promises';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

const [mode, specPath, a, b, flag] = process.argv.slice(2);
const url = (process.env.PLAYER_URL ?? 'http://localhost:4173') + '/offline.html';

async function browser() {
  let executablePath = process.env.CHROME_PATH;
  let args = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];
  if (!executablePath) {
    const chromium = (await import('@sparticuz/chromium')).default;
    executablePath = await chromium.executablePath();
    args = [...chromium.args, ...args];
  }
  return puppeteer.launch({ executablePath, args, headless: true, protocolTimeout: 600000 });
}

const spec = JSON.parse(await fs.readFile(specPath, 'utf8'));
const b0 = await browser();
const page = await b0.newPage();
page.on('console', (m) => m.type() === 'error' && console.error('[page]', m.text()));
page.on('pageerror', (e) => console.error('[page]', e.message));
await page.goto(url);
await page.waitForFunction(() => document.title === 'ready', { timeout: 120000 });

const meta = await page.evaluate((s) => window.deskBuddyOffline.simulate(s), spec);
if (mode === 'simulate') {
  await fs.writeFile(a, JSON.stringify(meta));
} else if (mode === 'render') {
  const crops = JSON.parse(await fs.readFile(a, 'utf8'));
  const outDir = b;
  await fs.mkdir(outDir, { recursive: true });
  const t0 = Date.now();
  for (let i = 0; i < crops.length; i++) {
    const file = path.join(outDir, `${String(i).padStart(5, '0')}.png`);
    try {
      await fs.access(file);
      continue; // resume
    } catch {}
    const data = await page.evaluate(
      (i, c, map, t) => (map ? window.deskBuddyOffline.renderMap(t, c) : window.deskBuddyOffline.render(i, c)),
      i, crops[i], flag === '--map', spec.plateTimes[i],
    );
    await fs.writeFile(file, Buffer.from(data.split(',')[1], 'base64'));
    if (i % 30 === 0) console.log(`${path.basename(outDir)} ${i}/${crops.length} ${((Date.now() - t0) / (i + 1) / 1000).toFixed(2)}s/frame`);
  }
}
await b0.close();
