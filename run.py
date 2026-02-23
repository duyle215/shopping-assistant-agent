"""
Entry point chinh - Khoi dong Shopping Assistant.

Chay:  python run.py
Truy cap: http://localhost:5000
"""

from app import create_app
from app.config import FLASK_DEBUG, FLASK_HOST, FLASK_PORT

app = create_app()

if __name__ == "__main__":
    print("=" * 50)
    print("  Shopping Assistant  |  Flask Web UI")
    print(f"  http://localhost:{FLASK_PORT}")
    print("=" * 50)
    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=FLASK_DEBUG,
        use_reloader=False,
    )
