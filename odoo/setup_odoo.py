# Runs inside `odoo shell` (the `env` variable is provided). Idempotent.
import json
import os

db = os.environ["SETUP_DB"]
secrets_dir = os.environ.get("SECRETS_DIR", "/secrets")
app_url = os.environ.get("CHAT_APP_URL", "http://localhost:5000")

# --- Company: Vietnamese shop, prices in VND ---
vnd = env.ref("base.VND")
vnd.active = True
company = env.ref("base.main_company")
if company.currency_id != vnd:
    company.currency_id = vnd
company.write({"name": "Phone Shop", "country_id": env.ref("base.vn").id})
env["product.pricelist"].search([]).write({"currency_id": vnd.id})

# --- Website: Vietnamese and English, chat widget URL ---
vi = env["res.lang"]._activate_lang("vi_VN")
for website in env["website"].search([]):
    website.write({"language_ids": [(4, vi.id)], "name": "Phone Shop"})
env["ir.config_parameter"].set_param("shopping_assistant_chat.app_url", app_url)


def api_user(login, name, groups):
    Users = env["res.users"].with_context(no_reset_password=True)
    user = Users.search([("login", "=", login)])
    if not user:
        user = Users.create({"login": login, "name": name})
    # English error messages in the app logs, whatever the website language
    user.write({"group_ids": [(6, 0, [env.ref(g).id for g in groups])], "lang": "en_US"})
    # One live key per user: drop old keys so rerunning the setup rotates them
    env["res.users.apikeys"].sudo().search([("user_id", "=", user.id)]).unlink()
    return env["res.users.apikeys"].with_user(user).sudo()._generate(None, f"{login} ({db})", None)


secrets = {
    "db": db,
    # The chatbot: sells, reserves stock, creates leads. Cannot edit products or stock levels.
    "api_key": api_user(
        "chatbot-api",
        "Chatbot",
        ["base.group_user", "sales_team.group_sale_salesman_all_leads", "stock.group_stock_user"],
    ),
    # Catalog sync and evaluation reset: product and stock administration.
    "admin_api_key": api_user(
        "catalog-sync",
        "Catalog sync",
        [
            "base.group_user",
            "product.group_product_manager",
            "sales_team.group_sale_manager",
            "stock.group_stock_manager",
        ],
    ),
}
env.cr.commit()

os.makedirs(secrets_dir, exist_ok=True)
path = os.path.join(secrets_dir, f"{db}.json")
with open(path, "w") as f:
    json.dump(secrets, f, indent=2)
os.chmod(path, 0o644)
print(f"[setup] API keys written to {path}")
