"""
Flask Application Factory.

Tao Flask app voi:
  - Template folder tro ve thu muc templates/ o goc project
  - Dang ky Blueprint routes
  - Khoi tao ShoppingAgent
"""

from __future__ import annotations

import os

from flask import Flask


def create_app() -> Flask:
    """Tao va cau hinh Flask app."""
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    app = Flask(
        __name__,
        template_folder=os.path.join(basedir, "templates"),
    )

    # Giu thu tu key nhu trong code (vd thu tu thong so tren the san pham)
    app.json.sort_keys = False

    # Tao bang con thieu (vd traces) - khong xoa du lieu
    from app.db import get_engine
    from app.models import create_tables

    create_tables(get_engine())

    # Khoi tao agent mot lan duy nhat
    from app.agent import ShoppingAgent

    app.config["AGENT"] = ShoppingAgent()

    # Dang ky routes
    from app.routes import api as api_blueprint

    app.register_blueprint(api_blueprint)

    return app
