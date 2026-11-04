// Playwright script for the README media. The app must run on http://localhost:5000.
//   npm install playwright && npx playwright install chromium
//   node scripts/demo/record.js docs/video
// GIF for the README (palette per video keeps text sharp):
//   ffmpeg -i docs/video/demo.webm -vf "fps=10,scale=960:-1:flags=lanczos,palettegen=stats_mode=diff" pal.png
//   ffmpeg -i docs/video/demo.webm -i pal.png -lavfi "fps=10,scale=960:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" docs/demo.gif
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");
const OUT = process.argv[2];
// Optional local copy of marked.js (only needed where the CDN is blocked)
const MARKED_FILE = path.join(__dirname, "package/marked.min.js");
const MARKED = fs.existsSync(MARKED_FILE) ? fs.readFileSync(MARKED_FILE, "utf8") : null;
const SIZE = { width: 1280, height: 800 };

async function waitAnswer(page, before) {
  await page.waitForFunction((n) => document.querySelectorAll(".msg.bot .meta").length > n, before, { timeout: 240000 });
}

async function ask(page, text) {
  const before = await page.locator(".msg.bot .meta").count();
  await page.click("#userInput");
  await page.keyboard.type(text, { delay: 35 });
  await page.waitForTimeout(400);
  await page.click("#sendBtn");
  await waitAnswer(page, before);
  await page.waitForTimeout(1800); // time to read
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: SIZE, recordVideo: { dir: OUT, size: SIZE } });
  const page = await ctx.newPage();
  if (MARKED) await page.route("**/marked*.js", (r) => r.fulfill({ body: MARKED, contentType: "application/javascript" }));
  await page.goto("http://localhost:5000");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForTimeout(1200);

  await ask(page, "Samsung dưới 10 triệu pin trâu");
  await ask(page, "So sánh giúp mình Galaxy A55 và A35");
  // order -> confirmation card
  const before = await page.locator(".msg.bot .meta").count();
  await page.click("#userInput");
  await page.keyboard.type("Lấy 1 chiếc A55 nhé, tên Minh, số 0901234567", { delay: 35 });
  await page.click("#sendBtn");
  await page.waitForSelector(".confirm-actions .yes", { timeout: 240000 });
  await page.waitForTimeout(1500);
  await page.hover(".confirm-actions .yes");
  await page.waitForTimeout(700);
  await page.click(".confirm-actions .yes");
  await waitAnswer(page, before + 1);
  await page.waitForTimeout(2500);

  // staff view: the new order
  await page.click('.tab-btn:has-text("Quản lý")');
  await page.waitForFunction(() => document.querySelectorAll("#ordersTable tr").length > 1, null, { timeout: 30000 });
  await page.evaluate(() => document.getElementById("ordersTable").scrollIntoView({ behavior: "smooth" }));
  await page.waitForTimeout(3000);

  const video = page.video();
  await ctx.close();
  const file = await video.path();
  fs.renameSync(file, path.join(OUT, "demo.webm"));
  await browser.close();
  console.log("saved", path.join(OUT, "demo.webm"));
})().catch((e) => { console.error(e); process.exit(1); });
