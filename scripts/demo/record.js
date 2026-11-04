// Playwright demo video for the README: the chat inside the Odoo website, then the new sales order
// in the Odoo backend. Odoo on http://localhost:8069 (shop database only), the app on :5000.
//   node scripts/demo/record.js docs/video [vi|en]
// GIF for the README (palette per video keeps text sharp):
//   ffmpeg -i docs/video/demo-en.webm -vf "fps=10,scale=960:-1:flags=lanczos,palettegen=stats_mode=diff" pal.png
//   ffmpeg -i docs/video/demo-en.webm -i pal.png -lavfi "fps=10,scale=960:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" docs/demo.gif
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");
const OUT = process.argv[2];
const LANG = process.argv[3] === "en" ? "en" : "vi";
const ODOO = "http://localhost:8069";
const PASSWORD = process.env.ODOO_ADMIN_PASSWORD || "admin";
const Q = {
  vi: ["Samsung dưới 10 triệu pin trâu", "So sánh giúp mình Galaxy A55 và A35", "Lấy 1 chiếc A55 nhé, tên Minh, số 0901234567"],
  en: ["Samsung under 10 million with a big battery", "Compare the Galaxy A55 and A35 for me", "I'll take one A55, name Minh, phone 0901234567"],
}[LANG];
// Optional local copy of marked.js (only needed where the CDN is blocked)
const MARKED_FILE = path.join(__dirname, "package/marked.min.js");
const MARKED = fs.existsSync(MARKED_FILE) ? fs.readFileSync(MARKED_FILE, "utf8") : null;
const SIZE = { width: 1280, height: 800 };

async function adminCookies(browser) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${ODOO}/web/login`);
  await page.fill("input[name=login]", "admin");
  await page.fill("input[name=password]", PASSWORD);
  await page.click("button[type=submit]");
  await page.waitForURL(/\/odoo/);
  const cookies = await ctx.cookies();
  await ctx.close();
  return cookies;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const staff = await adminCookies(browser);

  const ctx = await browser.newContext({ viewport: SIZE, recordVideo: { dir: OUT, size: SIZE } });
  if (MARKED) await ctx.route("**/marked*.js", (r) => r.fulfill({ body: MARKED, contentType: "application/javascript" }));
  const page = await ctx.newPage();
  await page.goto(`${ODOO}${LANG === "vi" ? "/vi" : ""}/shop`);
  await page.waitForTimeout(1500);
  await page.hover("#sa_chat_toggle");
  await page.waitForTimeout(500);
  await page.click("#sa_chat_toggle");
  const chat = page.frameLocator("#sa_chat_panel iframe");
  await chat.locator("#userInput").waitFor();
  await page.waitForTimeout(1000);

  const answers = chat.locator(".msg.bot .meta");
  async function ask(text) {
    const before = await answers.count();
    await chat.locator("#userInput").pressSequentially(text, { delay: 35 });
    await page.waitForTimeout(400);
    await chat.locator("#sendBtn").click();
    await answers.nth(before).waitFor({ timeout: 240000 });
    await page.waitForTimeout(2200); // time to read
    return before;
  }

  await ask(Q[0]);
  await ask(Q[1]);
  // order -> confirmation card -> confirm
  const before = await answers.count();
  await chat.locator("#userInput").pressSequentially(Q[2], { delay: 35 });
  await chat.locator("#sendBtn").click();
  await chat.locator(".confirm-actions .yes").waitFor({ timeout: 240000 });
  await page.waitForTimeout(1500);
  await chat.locator(".confirm-actions .yes").hover();
  await page.waitForTimeout(700);
  await chat.locator(".confirm-actions .yes").click();
  await answers.nth(before + 1).waitFor({ timeout: 240000 });
  await page.waitForTimeout(2500);

  // staff side: the order is a confirmed sales order in Odoo
  await ctx.addCookies(staff);
  await page.goto(`${ODOO}/odoo/sales`);
  await page.locator(".o_data_row").first().waitFor();
  await page.waitForTimeout(1500);
  await page.locator(".o_data_row").first().click();
  await page.locator(".o_form_view").waitFor();
  await page.waitForTimeout(3500);

  const video = page.video();
  await ctx.close();
  const file = await video.path();
  fs.renameSync(file, path.join(OUT, `demo-${LANG}.webm`));
  await browser.close();
  console.log("saved", path.join(OUT, `demo-${LANG}.webm`));
})().catch((e) => { console.error(e); process.exit(1); });
