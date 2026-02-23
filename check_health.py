"""
Phase 1 - Health Check Script
Kiểm tra kết nối tới các thành phần: PostgreSQL, Ollama, Qdrant
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()  # Nạp biến từ file .env


def _require(key: str) -> str:
    """Đọc biến từ .env, báo lỗi rõ ràng nếu thiếu."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Thiếu biến '{key}' trong file .env")
    return val


# ─────────────────────────────────────────────
# 1. POSTGRES
# ─────────────────────────────────────────────
def check_postgres():
    try:
        import psycopg2
    except ImportError:
        print("Postgres: FAIL  →  Chưa cài psycopg2  (pip install psycopg2-binary)")
        return False

    try:
        db_config = {
            "host": _require("POSTGRES_HOST"),
            "port": int(_require("POSTGRES_PORT")),
            "dbname": _require("POSTGRES_DB"),
            "user": _require("POSTGRES_USER"),
            "password": _require("POSTGRES_PASSWORD"),
            "connect_timeout": 5,
        }
    except EnvironmentError as e:
        print(f"Postgres: FAIL  →  {e}")
        return False

    try:
        conn = psycopg2.connect(**db_config)
        conn.close()
        print("Postgres: OK")
        return True
    except psycopg2.OperationalError as e:
        err = str(e).strip()
        print(f"Postgres: FAIL  →  {err}")

        # Gợi ý nếu database chưa tồn tại
        if "does not exist" in err or "database" in err.lower():
            print()
            print("  ▶ Database 'shopping_assistant' chưa tồn tại.")
            print("  ▶ Chạy lệnh SQL sau để tạo (dùng psql hoặc pgAdmin):")
            print()
            print("      CREATE DATABASE shopping_assistant")
            print("          WITH ENCODING = 'UTF8'")
            print("               LC_COLLATE = 'en_US.UTF-8'")
            print("               LC_CTYPE   = 'en_US.UTF-8'")
            print("               TEMPLATE   = template0;")
            print()
            print("  ▶ Hoặc dùng lệnh shell:")
            print("      createdb -U postgres shopping_assistant")
        return False
    except Exception as e:
        print(f"Postgres: FAIL  →  {e}")
        return False


# ─────────────────────────────────────────────
# 2. OLLAMA API
# ─────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL") or "http://localhost:11434"
# Models cần cho project (≤4B, hỗ trợ tiếng Việt)
WANTED_MODELS = {"qwen2.5", "nomic-embed-text"}


def check_ollama():
    try:
        import requests
    except ImportError:
        print("Ollama:   FAIL  →  Chưa cài requests  (pip install requests)")
        return False

    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()

        # Lấy danh sách model name (bỏ phần ":tag")
        loaded = {m["name"].split(":")[0].lower() for m in data.get("models", [])}
        all_names = [m["name"] for m in data.get("models", [])]

        print("Ollama:   OK")
        if all_names:
            print(f"  ▶ Models đã tải ({len(all_names)}): {', '.join(all_names)}")
        else:
            print("  ▶ Chưa có model nào được tải.")

        # Kiểm tra từng model quan trọng
        missing = [m for m in WANTED_MODELS if m not in loaded]
        if missing:
            print(f"  ⚠  Model chưa tải: {', '.join(sorted(missing))}")
            print("     Chạy:  ollama pull <model_name>")

        return True

    except requests.exceptions.ConnectionError:
        print(f"Ollama:   FAIL  →  Không kết nối được tới {OLLAMA_URL}")
        print("  ▶ Hãy khởi động Ollama:  ollama serve")
        return False
    except Exception as e:
        print(f"Ollama:   FAIL  →  {e}")
        return False


# ─────────────────────────────────────────────
# 3. QDRANT LOCAL
# ─────────────────────────────────────────────
QDRANT_PATH = os.getenv("QDRANT_PATH") or "./qdrant_data"


def check_qdrant():
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        print("Qdrant:   FAIL  →  Chưa cài qdrant-client  (pip install qdrant-client)")
        return False

    try:
        existed_before = os.path.isdir(QDRANT_PATH)
        client = QdrantClient(path=QDRANT_PATH)

        # Thử đọc danh sách collections để xác nhận client hoạt động
        collections = client.get_collections().collections

        if not existed_before:
            print(f"Qdrant:   OK  (Đã tạo thư mục mới: '{QDRANT_PATH}')")
        else:
            print(f"Qdrant:   OK  (Sử dụng thư mục hiện có: '{QDRANT_PATH}')")

        if collections:
            names = [c.name for c in collections]
            print(f"  ▶ Collections hiện có: {', '.join(names)}")
        else:
            print("  ▶ Chưa có collection nào.")

        return True
    except Exception as e:
        print(f"Qdrant:   FAIL  →  {e}")
        return False


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print("=" * 50)
    print("  AI Agent - Phone Store  |  Phase 1 Health Check")
    print("=" * 50)

    results = {
        "Postgres": check_postgres(),
        "Ollama": check_ollama(),
        "Qdrant": check_qdrant(),
    }

    print()
    print("─" * 50)
    print("Tóm tắt:")
    all_ok = True
    for name, ok in results.items():
        status = "OK" if ok else "FAIL"
        print(f"  {name:<10} {status}")
        if not ok:
            all_ok = False

    print("─" * 50)
    if all_ok:
        print("  Tất cả thành phần sẵn sàng. Có thể bắt đầu Phase 2!")
    else:
        print("  Một số thành phần chưa sẵn sàng. Vui lòng kiểm tra lại.")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
