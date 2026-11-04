#!/bin/sh
# Runs once, when the Postgres volume is created: a separate role for Odoo
# (Odoo refuses to connect as the superuser). The agent keeps using POSTGRES_USER.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE odoo WITH LOGIN CREATEDB PASSWORD '${ODOO_DB_PASSWORD}';
SQL
