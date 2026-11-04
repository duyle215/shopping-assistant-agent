// Playwright script for the README media. The app must run on http://localhost:5000.
//   npm install playwright && npx playwright install chromium
//   node scripts/demo/screenshots.js docs/screenshots [compare|search|confirm|order|tabs]
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const OUT = process.argv[2];
const BASE = "http://localhost:5000";
// Optional local copy of marked.js (only needed where the CDN is blocked)
const MARKED_FILE = path.join(__dirname, "package/marked.min.js");
const MARKED = fs.existsSync(MARKED_FILE) ? fs.readFileSync(MARKED_FILE, "utf8") : null;

// A finished bot answer gets a .meta row (intent + tools)
async function waitAnswer(page, before) {
  await page.waitForFunction((n) => document.querySelectorAll(".msg.bot .meta").length > n, before, { timeout: 240000 });
  await page.waitForTimeout(500);
}

async function ask(page, text) {
  const before = await page.locator(".msg.bot .meta").count();
  await page.fill("#userInput", text);
  await page.click("#sendBtn");
  await waitAnswer(page, before);
}

async function confirmOrder(page) {
  const before = await page.locator(".msg.bot .meta").count();
  await page.click(".confirm-actions .yes");
  await waitAnswer(page, before);
}

async function shootChat(browser, file, questions, height) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  if (MARKED) await page.route("**/marked*.js", (r) => r.fulfill({ body: MARKED, contentType: "application/javascript" }));
  await page.goto(BASE);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  for (const q of questions) {
    if (q === "__confirm__") await confirmOrder(page);
    else await ask(page, q);
  }
  // scroll the chat so the latest answer is in view
  await page.evaluate(() => {
    const el = document.getElementById("chatMessages");
    el.scrollTop = el.scrollHeight;
  });
  await page.screenshot({ path: path.join(OUT, file) });
  await ctx.close();
}

async function shootTab(browser, file, tabLabel, height, waitFor) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  if (MARKED) await page.route("**/marked*.js", (r) => r.fulfill({ body: MARKED, contentType: "application/javascript" }));
  await page.goto(BASE);
  await page.click(`.tab-btn:has-text("${tabLabel}")`);
  if (waitFor) await page.waitForFunction(waitFor, null, { timeout: 30000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, file) });
  await ctx.close();
}

// Orders + support requests (the stock table above them is long)
async function shootAdmin(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 700 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(BASE);
  await page.click('.tab-btn:has-text("Quản lý")');
  await page.waitForFunction(
    () => document.querySelectorAll("#ordersTable tr").length > 1 && document.querySelectorAll("#supportTable tr").length > 1,
    null,
    { timeout: 30000 },
  );
  // The 30-row stock table pushes orders and support requests out of view; hide it for this shot
  await page.evaluate(() => {
    document.querySelectorAll(".admin-section")[0].style.display = "none";
  });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(OUT, "admin.png") });
  await ctx.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const only = process.argv[3];

  if (!only || only === "compare")
    await shootChat(browser, "chat-compare.png", [
      "So sánh iPhone 16 Pro với Galaxy S24 Ultra và Xiaomi 14 Ultra, mình hay chụp ảnh và cần pin trâu",
    ], 1180);

  if (!only || only === "search")
    await shootChat(browser, "chat-search.png", [
      "Tìm giúp mình điện thoại Samsung dưới 10 triệu, pin trâu",
    ], 900);

  if (!only || only === "confirm")
    await shootChat(browser, "chat-confirm.png", [
      "Cho mình đặt 2 chiếc Redmi Note 13, tên Hùng, số 0987654321",
    ], 800);

  if (!only || only === "order")
    await shootChat(browser, "chat-order.png", [
      "Mình muốn mua 1 chiếc Galaxy A55, tên Minh, số điện thoại 0901234567",
      "__confirm__",
      "Máy này bảo hành bao lâu vậy?",
    ], 1200);

  if (!only || only === "tabs") {
    await shootTab(browser, "products.png", "Sản phẩm", 900,
      () => document.querySelectorAll(".product-card").length > 0);
    await shootAdmin(browser);
    await shootTab(browser, "health.png", "Hệ thống", 860,
      () => document.querySelectorAll("#traceSummary .stat").length > 0);
  }

  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
