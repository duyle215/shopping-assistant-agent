"""
Dependencies dung chung toan app (Singleton pattern).
Import vao bat ky router nao can.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def get_agent():
    """Khoi tao ShoppingAgent mot lan duy nhat, tai su dung cho moi request."""
    from agent_core import ShoppingAgent

    return ShoppingAgent()


def get_pg_url() -> str:
    def _r(k: str) -> str:
        v = os.getenv(k)
        if not v:
            raise EnvironmentError(f"Thieu bien '{k}' trong .env")
        return v

    return (
        f"postgresql+psycopg2://{_r('POSTGRES_USER')}:{_r('POSTGRES_PASSWORD')}"
        f"@{_r('POSTGRES_HOST')}:{_r('POSTGRES_PORT')}/{_r('POSTGRES_DB')}"
    )
