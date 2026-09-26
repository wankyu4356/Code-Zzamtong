#!/opt/node22/bin/node
// Render the graphics layer of a timeline to transparent PNGs (overlay/%05d.png)
// with headless Chromium. Each frame is a pure function of its index (see overlay.html),
// so frames whose state key equals the previous frame's are file copies, not screenshots.
//
// usage: node render_overlay.mjs --timeline t.json --out build/overlay [--from A --to B] [--only-shot s03]
//        (--from/--to are inclusive global frame indices)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "/opt/node22/lib/node_modules/playwright/index.mjs";

const CHROME = process.env.CHROME_BIN || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
const HERE = path.dirname(fileURLToPath(import.meta.url));

function parseArgs(argv) {
  const a = { from: null, to: null, onlyShot: null };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i], v = argv[i + 1];
    if (k === "--timeline") a.timeline = v, i++;
    else if (k === "--out") a.out = v, i++;
    else if (k === "--from") a.from = parseInt(v, 10), i++;
    else if (k === "--to") a.to = parseInt(v, 10), i++;
    else if (k === "--only-shot") a.onlyShot = v, i++;
    else throw new Error(`unknown argument ${k}`);
  }
  if (!a.timeline || !a.out) throw new Error("usage: render_overlay.mjs --timeline t.json --out dir [--from A --to B] [--only-shot id]");
  return a;
}

const toFrame = (sec, fps) => Math.floor(sec * fps + 0.5);

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const tl = JSON.parse(fs.readFileSync(args.timeline, "utf8"));
  const total = toFrame(tl.duration, tl.fps);
  let from = 0, to = total - 1;
  if (args.onlyShot !== null) {
    const shot = tl.shots.find((s) => s.id === args.onlyShot);
    if (!shot) throw new Error(`shot ${args.onlyShot} not found`);
    from = toFrame(shot.start, tl.fps);
    to = toFrame(shot.end, tl.fps) - 1;
  }
  if (args.from !== null) from = Math.max(from, args.from);
  if (args.to !== null) to = Math.min(to, args.to);
  if (from > to) throw new Error(`empty frame range ${from}..${to}`);
  fs.mkdirSync(args.out, { recursive: true });

  const t0 = Date.now();
  const browser = await chromium.launch({
    executablePath: CHROME,
    args: ["--no-sandbox", "--force-color-profile=srgb", "--hide-scrollbars"],
  });
  const page = await browser.newPage({ viewport: { width: tl.width, height: tl.height }, deviceScaleFactor: 1 });
  page.on("pageerror", (e) => { console.error("page error:", e); process.exitCode = 1; });
  await page.goto("file://" + path.join(HERE, "overlay.html"));
  const n = await page.evaluate((t) => window.setTimeline(t), tl);
  await page.evaluate(() => document.fonts.ready.then(() => true));
  console.log(`overlay: ${n} elements, frames ${from}..${to} (${to - from + 1}) -> ${args.out}`);

  let lastKey = null, lastFile = null, shots = 0, copies = 0;
  const clip = { x: 0, y: 0, width: tl.width, height: tl.height };
  for (let f = from; f <= to; f++) {
    const key = await page.evaluate((i) => window.render(i), f);
    const file = path.join(args.out, String(f).padStart(5, "0") + ".png");
    if (key === lastKey) { fs.copyFileSync(lastFile, file); copies++; }
    else { await page.screenshot({ path: file, omitBackground: true, type: "png", clip }); shots++; }
    lastKey = key; lastFile = file;
    const done = f - from + 1;
    if (done % 100 === 0 || f === to) {
      console.log(`  ${done}/${to - from + 1} frames  ${((Date.now() - t0) / 1000).toFixed(1)}s  (${shots} screenshots, ${copies} copies)`);
    }
  }
  await browser.close();
  console.log(`overlay done in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
}

main().catch((e) => { console.error("error:", e.message || e); process.exit(1); });
