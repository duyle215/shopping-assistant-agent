"""
Odoo client - goi Odoo qua JSON-2 API (Odoo 19): POST /json/2/<model>/<method>,
xac thuc bang API key cua mot user rieng (header Authorization: bearer).

Odoo la backend that: san pham, ton kho, don hang, yeu cau ho tro deu doc/ghi o day.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from functools import lru_cache
from typing import Any, Optional

import requests

from app.config import ODOO_ADMIN_API_KEY, ODOO_API_KEY, ODOO_DB, ODOO_SECRETS_DIR, ODOO_TIMEOUT, ODOO_URL

logger = logging.getLogger("odoo")

# Loi tranh chap transaction (Odoo da tu thu lai 5 lan); thu them vai lan nua o phia client
RETRYABLE = ("SerializationFailure", "concurrent update", "could not serialize")


class OdooError(Exception):
    def __init__(self, message: str, name: str = "", status: int = 0):
        super().__init__(message)
        self.name = name
        self.status = status


class OdooClient:
    def __init__(self, url: str, db: str, api_key: str, timeout: float = 30, retries: int = 3):
        if not api_key:
            raise OdooError(
                f"Thieu API key cho database Odoo '{db}': dat ODOO_API_KEY hoac chay "
                "`docker compose run --rm odoo-setup` de tao odoo/secrets/<db>.json"
            )
        self.url = url.rstrip("/")
        self.db = db
        self.timeout = timeout
        self.retries = retries
        self._headers = {
            "Authorization": f"bearer {api_key}",
            "X-Odoo-Database": db,
            "Content-Type": "application/json",
            "User-Agent": "shopping-assistant",
        }
        self._local = threading.local()

    def _session(self) -> requests.Session:
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
        return self._local.session

    def call(self, model: str, method: str, ids: Optional[list[int]] = None, **kwargs) -> Any:
        body = {**kwargs}
        if ids is not None:
            body["ids"] = list(ids)
        for attempt in range(1, self.retries + 1):
            try:
                resp = self._session().post(
                    f"{self.url}/json/2/{model}/{method}",
                    data=json.dumps(body),
                    headers=self._headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise OdooError(f"Khong ket noi duoc Odoo ({self.url}): {exc}") from exc
            if resp.ok:
                return resp.json()
            err = _error(resp)
            if attempt < self.retries and any(r in f"{err.name} {err}" for r in RETRYABLE):
                logger.warning(f"[Odoo] {model}.{method}: tranh chap, thu lai ({attempt})")
                time.sleep(0.2 * attempt)
                continue
            raise err

    # Tien ich cho cac method hay dung
    def search_read(
        self,
        model: str,
        domain: list,
        fields: list[str],
        order: Optional[str] = None,
        limit: Optional[int] = None,
        context: Optional[dict] = None,
    ) -> list[dict]:
        kwargs: dict = {"domain": domain, "fields": fields}
        if order:
            kwargs["order"] = order
        if limit:
            kwargs["limit"] = limit
        if context:
            kwargs["context"] = context
        return self.call(model, "search_read", **kwargs)

    def search(self, model: str, domain: list, order: Optional[str] = None, limit: Optional[int] = None) -> list[int]:
        kwargs: dict = {"domain": domain}
        if order:
            kwargs["order"] = order
        if limit:
            kwargs["limit"] = limit
        return self.call(model, "search", **kwargs)

    def create(self, model: str, vals: dict, context: Optional[dict] = None) -> int:
        kwargs: dict = {"vals_list": [vals]}
        if context:
            kwargs["context"] = context
        return self.call(model, "create", **kwargs)[0]

    def write(self, model: str, ids: list[int], vals: dict) -> bool:
        return self.call(model, "write", ids=ids, vals=vals)


def _error(resp: requests.Response) -> OdooError:
    try:
        data = resp.json()
        return OdooError(data.get("message") or resp.text, data.get("name", ""), resp.status_code)
    except ValueError:
        return OdooError(f"HTTP {resp.status_code}: {resp.text[:300]}", status=resp.status_code)


def _secret(db: str, key: str) -> str:
    path = os.path.join(ODOO_SECRETS_DIR, f"{db}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get(key) or ""
    except FileNotFoundError:
        return ""


@lru_cache(maxsize=4)
def get_odoo(admin: bool = False, db: Optional[str] = None) -> OdooClient:
    """Client dung chung. admin=True: user dong bo catalog (sua san pham, ton kho) cho scripts."""
    db = db or ODOO_DB
    if admin:
        key = (ODOO_ADMIN_API_KEY if db == ODOO_DB else "") or _secret(db, "admin_api_key")
    else:
        key = (ODOO_API_KEY if db == ODOO_DB else "") or _secret(db, "api_key")
    return OdooClient(ODOO_URL, db, key, timeout=ODOO_TIMEOUT)
