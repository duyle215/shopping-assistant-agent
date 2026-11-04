// Playwright: README screenshots of the Odoo side. Odoo on http://localhost:8069 (shop database only,
// default ODOO_DB_FILTER), the app on http://localhost:5000.
//   node scripts/demo/odoo.js docs/screenshots [vi|en] [website|backend]
// website: the Odoo shop with the chat window open after a question.
// backend: staff view in Odoo (logs in as admin, password from ODOO_ADMIN_PASSWORD or "admin"):
//   the chatbot's sales order, the CRM pipeline with its support requests, a product's spec tab.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const OUT = process.argv[2];
const LANG = process.argv[3] === "en" ? "en" : "vi";
const ODOO = "http://localhost:8069";
const PASSWORD = process.env.ODOO_ADMIN_PASSWORD || "admin";
const Q = {
  vi: "Tìm giúp mình điện thoại Samsung dưới 10 triệu, pin trâu",
  en: "Find me a Samsung phone under 10 million with a big battery",
}[LANG];
const MARKED_FILE = path.join(__dirname, "package/marked.min.js");
const MARKED = fs.existsSync(MARKED_FILE) ? fs.readFileSync(MARKED_FILE, "utf8") : null;

async function newPage(browser, height = 800) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height }, deviceScaleFactor: 2 });
  if (MARKED) await ctx.route("**/marked*.js", (r) => r.fulfill({ body: MARKED, contentType: "application/javascript" }));
  return [ctx, await ctx.newPage()];
}

async function shootWebsite(browser) {
  const [ctx, page] = await newPage(browser, 860);
  await page.goto(`${ODOO}${LANG === "vi" ? "/vi" : ""}/shop`);
  await page.click("#sa_chat_toggle");
  const chat = page.frameLocator("#sa_chat_panel iframe");
  await chat.locator("#userInput").fill(Q);
  await chat.locator("#sendBtn").click();
  await chat.locator(".msg.bot .meta").first().waitFor({ timeout: 240000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "odoo-website.png") });
  await ctx.close();
}

async function login(page) {
  await page.goto(`${ODOO}/web/login`);
  await page.fill("input[name=login]", "admin");
  await page.fill("input[name=password]", PASSWORD);
  await page.click("button[type=submit]");
  await page.waitForURL(/\/odoo/);
}

async function shootBackend(browser) {
  const [ctx, page] = await newPage(browser, 760);
  await login(page);

  // Latest sales order created by the chatbot
  await page.goto(`${ODOO}/odoo/sales`);
  await page.locator(".o_data_row").first().waitFor();
  await page.locator(".o_data_row").first().click();
  await page.locator(".o_form_view").waitFor();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(OUT, "odoo-order.png") });

  // CRM pipeline: support requests from the chat
  await page.goto(`${ODOO}/odoo/crm`);
  await page.locator(".o_kanban_record").first().waitFor();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(OUT, "odoo-crm.png") });

  // Product form, phone spec tab added by the addon
  await page.goto(`${ODOO}/odoo/action-sale.product_template_action`);
  await page.locator(".o_kanban_record").first().waitFor();
  await page.locator(".o_kanban_record").first().click();
  await page.locator("a[name=phone_specs], .nav-link:has-text('Phone specs')").first().click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(OUT, "odoo-product.png") });
  await ctx.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const only = process.argv[4];
  if (!only || only === "website") await shootWebsite(browser);
  if (!only || only === "backend") await shootBackend(browser);
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
