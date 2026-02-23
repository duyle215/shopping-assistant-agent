"""
Phase 2 - Ingest Data
Nap du lieu san pham vao:
  - PostgreSQL  (metadata)  --- qua SQLAlchemy
  - Qdrant      (vectors)   --- qua QdrantClient local
Embedding goi qua OpenAI API (text-embedding-3-small).
De chay local voi Ollama: doi OPENAI_BASE_URL va OPENAI_API_KEY trong .env.
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────────────────────
# 0. CONFIG (đọc thuần từ .env)
# ─────────────────────────────────────────────────────────────
def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        sys.exit(f"[ERROR] Thiếu biến '{key}' trong file .env")
    return val


PG_HOST = _require("POSTGRES_HOST")
PG_PORT = _require("POSTGRES_PORT")
PG_DB = _require("POSTGRES_DB")
PG_USER = _require("POSTGRES_USER")
PG_PASSWORD = _require("POSTGRES_PASSWORD")

QDRANT_PATH = _require("QDRANT_PATH")

OPENAI_BASE_URL = _require("OPENAI_BASE_URL")
OPENAI_API_KEY = _require("OPENAI_API_KEY")
EMBED_MODEL = _require("EMBED_MODEL")
EMBED_DIM = int(_require("EMBED_DIM"))
COLLECTION_NAME = _require("QDRANT_COLLECTION")

# ─────────────────────────────────────────────────────────────
# 1. DỮ LIỆU MẪU – 5 sản phẩm điện thoại
# ─────────────────────────────────────────────────────────────
PRODUCTS = [
    {
        "id": 1,
        "name": "iPhone 15 Pro Max",
        "brand": "Apple",
        "price": 34_990_000,
        "specs": {
            "ram": "8GB",
            "storage": "256GB",
            "screen": "6.7 inch Super Retina XDR",
            "battery": "4422 mAh",
            "chip": "Apple A17 Pro",
            "camera": "48MP + 12MP + 12MP",
        },
        "description": (
            "iPhone 15 Pro Max là flagship cao cấp nhất của Apple năm 2023, "
            "được trang bị chip A17 Pro 3nm mạnh mẽ, khung titan siêu bền và "
            "hệ thống camera ProRes cho phép quay video 4K 60fps. "
            "Màn hình Dynamic Island và Always-On Display mang lại trải nghiệm hoàn toàn mới."
        ),
        "reviews": [
            "Máy cực kỳ mượt, camera chụp đêm tốt hơn hẳn đời trước.",
            "Pin dùng được cả ngày dài cả ngày mà không lo hết pin.",
            "Giá cao nhưng xứng đáng, build quality titan rất sang.",
        ],
    },
    {
        "id": 2,
        "name": "Samsung Galaxy S24 Ultra",
        "brand": "Samsung",
        "price": 31_990_000,
        "specs": {
            "ram": "12GB",
            "storage": "256GB",
            "screen": "6.8 inch QHD+ Dynamic AMOLED 2X",
            "battery": "5000 mAh",
            "chip": "Snapdragon 8 Gen 3",
            "camera": "200MP + 12MP + 50MP + 10MP",
        },
        "description": (
            "Galaxy S24 Ultra tích hợp bút S Pen, chip Snapdragon 8 Gen 3 cực mạnh "
            "và camera 200MP hàng đầu phân khúc. Galaxy AI mang lại nhiều tính năng "
            "thông minh như phiên dịch thời gian thực, Circle to Search và Generative Edit."
        ),
        "reviews": [
            "S Pen rất tiện dụng cho việc ghi chú và ký hợp đồng điện tử.",
            "Camera 200MP chụp chi tiết đến từng sợi tóc, zoom 100x cũng khá dùng được.",
            "Máy hơi to và nặng nhưng đổi lại pin rất trâu.",
        ],
    },
    {
        "id": 3,
        "name": "Xiaomi 14 Ultra",
        "brand": "Xiaomi",
        "price": 22_990_000,
        "specs": {
            "ram": "16GB",
            "storage": "512GB",
            "screen": "6.73 inch LTPO AMOLED",
            "battery": "5000 mAh",
            "chip": "Snapdragon 8 Gen 3",
            "camera": "50MP Leica Summilux + 50MP + 50MP + 50MP",
        },
        "description": (
            "Xiaomi 14 Ultra hợp tác với Leica cho hệ thống camera 4 ống kính "
            "toàn 50MP, ống kính biến tiêu từ 12mm đến 120mm. "
            "Sạc nhanh 90W và sạc không dây 80W giúp đầy pin trong chưa đầy 40 phút."
        ),
        "reviews": [
            "Camera Leica cho màu sắc cực kỳ tự nhiên, đặc biệt chụp chân dung.",
            "Sạc 90W quá nhanh, 30 phút đã được 80%, rất tiện.",
            "Giá tốt hơn iPhone hay Samsung nhiều mà hiệu năng không thua kém.",
        ],
    },
    {
        "id": 4,
        "name": "OPPO Find X7 Pro",
        "brand": "OPPO",
        "price": 18_990_000,
        "specs": {
            "ram": "12GB",
            "storage": "256GB",
            "screen": "6.82 inch LTPO AMOLED",
            "battery": "5000 mAh",
            "chip": "Snapdragon 8 Gen 3",
            "camera": "50MP Hasselblad + 50MP + 50MP",
        },
        "description": (
            "OPPO Find X7 Pro hợp tác với Hasselblad mang đến hệ thống camera "
            "chuyên nghiệp với khả năng chụp RAW 12-bit. "
            "Màn hình cong 2K 120Hz LTPO và viên pin 5000 mAh với sạc SuperVOOC 100W "
            "là điểm nhấn đáng giá của máy."
        ),
        "reviews": [
            "Camera Hasselblad cho ảnh RAW rất đẹp, dải màu rộng.",
            "Màn hình cong nhìn rất sang, xem phim cực đã mắt.",
            "OPPO ColorOS mượt và nhiều tính năng thực dụng.",
        ],
    },
    {
        "id": 5,
        "name": "Google Pixel 8 Pro",
        "brand": "Google",
        "price": 23_990_000,
        "specs": {
            "ram": "12GB",
            "storage": "128GB",
            "screen": "6.7 inch LTPO OLED",
            "battery": "5050 mAh",
            "chip": "Google Tensor G3",
            "camera": "50MP + 48MP + 48MP",
        },
        "description": (
            "Pixel 8 Pro sở hữu chip Tensor G3 được tối ưu cho AI, "
            "mang lại các tính năng độc quyền như Magic Eraser, Best Take, "
            "Audio Magic Eraser và Video Boost. "
            "Đây là điện thoại nhận update phần mềm và bảo mật dài nhất – 7 năm."
        ),
        "reviews": [
            "Tính năng AI chỉnh ảnh Magic Eraser xóa vật thể thừa cực kỳ chính xác.",
            "Android thuần Google, update nhanh và không bloatware.",
            "Nhiệt độ máy hơi cao khi chơi game nặng, nhưng dùng hàng ngày thì ổn.",
        ],
    },
]


# ─────────────────────────────────────────────────────────────
# 2. HÀM TIỆN ÍCH
# ─────────────────────────────────────────────────────────────
def build_text(product: dict) -> str:
    """Kết hợp name, description và reviews thành đoạn text cho embedding."""
    reviews_text = " | ".join(product["reviews"])
    return (
        f"Tên sản phẩm: {product['name']}. "
        f"Thương hiệu: {product['brand']}. "
        f"Mô tả: {product['description']} "
        f"Đánh giá người dùng: {reviews_text}"
    )


# ─────────────────────────────────────────────────────────────
# 3. POSTGRES – tạo bảng & nạp dữ liệu
# ─────────────────────────────────────────────────────────────
def ingest_postgres() -> int:
    try:
        from sqlalchemy import (
            Column,
            Integer,
            Numeric,
            String,
            Text,
            create_engine,
            text,
        )
        from sqlalchemy.orm import declarative_base, Session
    except ImportError:
        sys.exit("[ERROR] Chưa cài SQLAlchemy: pip install sqlalchemy")

    DB_URL = (
        f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}" f"@{PG_HOST}:{PG_PORT}/{PG_DB}"
    )

    engine = create_engine(DB_URL, echo=False)
    Base = declarative_base()

    class Product(Base):
        __tablename__ = "products"
        id = Column(Integer, primary_key=True)
        name = Column(String(255), nullable=False)
        brand = Column(String(100), nullable=False)
        price = Column(Numeric(15, 0), nullable=False)
        specs = Column(Text, nullable=True)  # JSON string
        description = Column(Text, nullable=True)

    # Tạo bảng nếu chưa có
    Base.metadata.create_all(engine)

    inserted = 0
    with Session(engine) as session:
        # Xoá dữ liệu cũ (idempotent)
        session.execute(text("DELETE FROM products"))
        for p in PRODUCTS:
            row = Product(
                id=p["id"],
                name=p["name"],
                brand=p["brand"],
                price=p["price"],
                specs=json.dumps(p["specs"], ensure_ascii=False),
                description=p["description"],
            )
            session.add(row)
            inserted += 1
        session.commit()

    return inserted


# ─────────────────────────────────────────────────────────────
# 4. QDRANT + EMBEDDING – tạo collection & nạp vector
# ─────────────────────────────────────────────────────────────
def ingest_qdrant() -> int:
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("[ERROR] Chưa cài openai: pip install openai")

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams
    except ImportError:
        sys.exit("[ERROR] Chưa cài qdrant-client: pip install qdrant-client")

    # OpenAI client
    oai = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)

    # Qdrant local
    qdrant = QdrantClient(path=QDRANT_PATH)

    # Tạo hoặc recreate collection
    existing = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION_NAME in existing:
        qdrant.delete_collection(COLLECTION_NAME)

    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )

    points = []
    for p in PRODUCTS:
        text_chunk = build_text(p)

        # Gọi embedding qua chuẩn API OpenAI
        response = oai.embeddings.create(
            model=EMBED_MODEL,
            input=text_chunk,
        )
        vector = response.data[0].embedding

        points.append(
            PointStruct(
                id=p["id"],
                vector=vector,
                payload={
                    "product_id": p["id"],
                    "name": p["name"],
                    "brand": p["brand"],
                    "price": p["price"],
                    "description": p["description"],
                },
            )
        )

    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    return len(points)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Shopping Assistant  |  Phase 2 – Ingest Data")
    print("=" * 55)

    # --- PostgreSQL ---
    print("\n[1/2] Nạp dữ liệu vào PostgreSQL...")
    try:
        pg_count = ingest_postgres()
        print(f"  PostgreSQL: da luu {pg_count} san pham vao bang 'products'")
    except Exception as e:
        print(f"  PostgreSQL FAIL: {e}")
        sys.exit(1)

    # --- Qdrant ---
    print("\n[2/2] Tạo embedding và nạp vector vào Qdrant...")
    print(f"  Dang goi OpenAI API ({EMBED_MODEL}) de tao vector...")
    try:
        qd_count = ingest_qdrant()
        print(
            f"  Qdrant: da upsert {qd_count} vector vao collection '{COLLECTION_NAME}'"
        )
    except Exception as e:
        print(f"  Qdrant FAIL: {e}")
        sys.exit(1)

    # --- Tóm tắt ---
    print()
    print("─" * 55)
    print("  Kết quả nạp dữ liệu:")
    print(f"    PostgreSQL  →  {pg_count} bản ghi  (bảng: products)")
    print(f"    Qdrant      →  {qd_count} vector   (collection: {COLLECTION_NAME})")
    print("─" * 55)
    print("  Phase 2 hoàn tất. Sẵn sàng cho Phase 3 (RAG Agent)!")


if __name__ == "__main__":
    main()
