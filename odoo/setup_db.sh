#!/bin/bash
# Create or update one Odoo database for the chatbot:
#   install the addon and its dependencies, then run setup_odoo.py in an Odoo shell
#   (company in VND, Vietnamese website language, API users and keys).
# Usage (from the repo root):  docker compose run --rm odoo-setup [db_name]   (default: odoo)
set -e
DB="${1:-odoo}"
ARGS=(-c /etc/odoo/odoo.conf --db_host "$HOST" --db_user "$USER" --db_password "$PASSWORD" -d "$DB")
wait-for-psql.py --db_host "$HOST" --db_port 5432 --db_user "$USER" --db_password "$PASSWORD" --timeout=60
echo "[setup] Installing shopping_assistant_chat in '$DB'..."
odoo "${ARGS[@]}" -i shopping_assistant_chat -u shopping_assistant_chat --load-language vi_VN --stop-after-init --no-http
echo "[setup] Configuring '$DB'..."
SETUP_DB="$DB" odoo shell "${ARGS[@]}" --no-http < /setup/setup_odoo.py
