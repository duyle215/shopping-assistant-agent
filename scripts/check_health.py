"""
Health Check - Kiem tra ket noi toi cac thanh phan: PostgreSQL, Qdrant.

Chay:  python scripts/check_health.py  (tu thu muc goc project)
"""

import os
import sys

# Them project root vao sys.path de import app.config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD, QDRANT_PATH, QDRANT_URL


# ------------------------------------------------------------------
# 1. POSTGRES
# ------------------------------------------------------------------
def check_postgres():
    try:
        import psycopg2
    except ImportError:
        print("Postgres: FAIL  ->  Chua cai psycopg2  (pip install psycopg2-binary)")
        return False

    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=int(PG_PORT),
            dbname=PG_DB,
            user=PG_USER,
            password=PG_PASSWORD,
            connect_timeout=5,
        )
        conn.close()
        print("Postgres: OK")
        return True
    except Exception as e:
        err = str(e).strip()
        print(f"Postgres: FAIL  ->  {err}")
        if "does not exist" in err or "database" in err.lower():
            print()
            print("  Database 'shopping_assistant' chua ton tai.")
            print("  Chay lenh SQL sau de tao (dung psql hoac pgAdmin):")
            print()
            print("      CREATE DATABASE shopping_assistant;")
        return False


# ------------------------------------------------------------------
# 2. QDRANT LOCAL
# ------------------------------------------------------------------
def check_qdrant():
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        print("Qdrant:   FAIL  ->  Chua cai qdrant-client  (pip install qdrant-client)")
        return False

    try:
        existed_before = os.path.isdir(QDRANT_PATH)
        client = QdrantClient(url=QDRANT_URL) if QDRANT_URL else QdrantClient(path=QDRANT_PATH)
        collections = client.get_collections().collections

        if QDRANT_URL:
            print(f"Qdrant:   OK  (Server: {QDRANT_URL})")
        elif not existed_before:
            print(f"Qdrant:   OK  (Da tao thu muc moi: '{QDRANT_PATH}')")
        else:
            print(f"Qdrant:   OK  (Su dung thu muc hien co: '{QDRANT_PATH}')")

        if collections:
            names = [c.name for c in collections]
            print(f"  Collections hien co: {', '.join(names)}")
        else:
            print("  Chua co collection nao.")

        return True
    except Exception as e:
        print(f"Qdrant:   FAIL  ->  {e}")
        return False


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():
    print("=" * 50)
    print("  Shopping Assistant  |  Health Check")
    print("=" * 50)

    results = {
        "Postgres": check_postgres(),
        "Qdrant": check_qdrant(),
    }

    print()
    print("-" * 50)
    print("Tom tat:")
    all_ok = True
    for name, ok in results.items():
        status = "OK" if ok else "FAIL"
        print(f"  {name:<10} {status}")
        if not ok:
            all_ok = False

    print("-" * 50)
    if all_ok:
        print("  Tat ca thanh phan san sang!")
    else:
        print("  Mot so thanh phan chua san sang. Vui long kiem tra lai.")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
