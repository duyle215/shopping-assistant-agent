"""
Ingest Data - Nap du lieu san pham vao PostgreSQL va Qdrant.

Chay:  python scripts/ingest_data.py  (tu thu muc goc project)
"""

import json
import sys
import os

# Them project root vao sys.path de import app.config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import (
    PG_USER,
    PG_PASSWORD,
    PG_HOST,
    PG_PORT,
    PG_DB,
    QDRANT_PATH,
    OPENAI_BASE_URL,
    OPENAI_API_KEY,
    EMBED_MODEL,
    EMBED_DIM,
    QDRANT_COLLECTION,
)


# ------------------------------------------------------------------
# DU LIEU MAU - 5 san pham dien thoai
# ------------------------------------------------------------------
PRODUCTS = [
    {
        "id": 1,
        "name": "iPhone 15 Pro Max",
        "brand": "Apple",
        "price": 34_990_000,
        "stock": 15,
        "specs": {
            "ram": "8GB",
            "storage": "256GB",
            "screen": "6.7 inch Super Retina XDR",
            "battery": "4422 mAh",
            "chip": "Apple A17 Pro",
            "camera": "48MP + 12MP + 12MP",
        },
        "description": (
            "iPhone 15 Pro Max la flagship cao cap nhat cua Apple nam 2023, "
            "duoc trang bi chip A17 Pro 3nm manh me, khung titan sieu ben va "
            "he thong camera ProRes cho phep quay video 4K 60fps. "
            "Man hinh Dynamic Island va Always-On Display mang lai trai nghiem hoan toan moi."
        ),
        "reviews": [
            "May cuc ky muot, camera chup dem tot hon han doi truoc.",
            "Pin dung duoc ca ngay dai ca ngay ma khong lo het pin.",
            "Gia cao nhung xung dang, build quality titan rat sang.",
        ],
    },
    {
        "id": 2,
        "name": "Samsung Galaxy S24 Ultra",
        "brand": "Samsung",
        "price": 31_990_000,
        "stock": 25,
        "specs": {
            "ram": "12GB",
            "storage": "256GB",
            "screen": "6.8 inch QHD+ Dynamic AMOLED 2X",
            "battery": "5000 mAh",
            "chip": "Snapdragon 8 Gen 3",
            "camera": "200MP + 12MP + 50MP + 10MP",
        },
        "description": (
            "Galaxy S24 Ultra tich hop but S Pen, chip Snapdragon 8 Gen 3 cuc manh "
            "va camera 200MP hang dau phan khuc. Galaxy AI mang lai nhieu tinh nang "
            "thong minh nhu phien dich thoi gian thuc, Circle to Search va Generative Edit."
        ),
        "reviews": [
            "S Pen rat tien dung cho viec ghi chu va ky hop dong dien tu.",
            "Camera 200MP chup chi tiet den tung soi toc, zoom 100x cung kha dung duoc.",
            "May hoi to va nang nhung doi lai pin rat trau.",
        ],
    },
    {
        "id": 3,
        "name": "Xiaomi 14 Ultra",
        "brand": "Xiaomi",
        "price": 22_990_000,
        "stock": 20,
        "specs": {
            "ram": "16GB",
            "storage": "512GB",
            "screen": "6.73 inch LTPO AMOLED",
            "battery": "5000 mAh",
            "chip": "Snapdragon 8 Gen 3",
            "camera": "50MP Leica Summilux + 50MP + 50MP + 50MP",
        },
        "description": (
            "Xiaomi 14 Ultra hop tac voi Leica cho he thong camera 4 ong kinh "
            "toan 50MP, ong kinh bien tieu tu 12mm den 120mm. "
            "Sac nhanh 90W va sac khong day 80W giup day pin trong chua day 40 phut."
        ),
        "reviews": [
            "Camera Leica cho mau sac cuc ky tu nhien, dac biet chup chan dung.",
            "Sac 90W qua nhanh, 30 phut da duoc 80%, rat tien.",
            "Gia tot hon iPhone hay Samsung nhieu ma hieu nang khong thua kem.",
        ],
    },
    {
        "id": 4,
        "name": "OPPO Find X7 Pro",
        "brand": "OPPO",
        "price": 18_990_000,
        "stock": 30,
        "specs": {
            "ram": "12GB",
            "storage": "256GB",
            "screen": "6.82 inch LTPO AMOLED",
            "battery": "5000 mAh",
            "chip": "Snapdragon 8 Gen 3",
            "camera": "50MP Hasselblad + 50MP + 50MP",
        },
        "description": (
            "OPPO Find X7 Pro hop tac voi Hasselblad mang den he thong camera "
            "chuyen nghiep voi kha nang chup RAW 12-bit. "
            "Man hinh cong 2K 120Hz LTPO va vien pin 5000 mAh voi sac SuperVOOC 100W "
            "la diem nhan dang gia cua may."
        ),
        "reviews": [
            "Camera Hasselblad cho anh RAW rat dep, dai mau rong.",
            "Man hinh cong nhin rat sang, xem phim cuc da mat.",
            "OPPO ColorOS muot va nhieu tinh nang thuc dung.",
        ],
    },
    {
        "id": 5,
        "name": "Google Pixel 8 Pro",
        "brand": "Google",
        "price": 23_990_000,
        "stock": 10,
        "specs": {
            "ram": "12GB",
            "storage": "128GB",
            "screen": "6.7 inch LTPO OLED",
            "battery": "5050 mAh",
            "chip": "Google Tensor G3",
            "camera": "50MP + 48MP + 48MP",
        },
        "description": (
            "Pixel 8 Pro so huu chip Tensor G3 duoc toi uu cho AI, "
            "mang lai cac tinh nang doc quyen nhu Magic Eraser, Best Take, "
            "Audio Magic Eraser va Video Boost. "
            "Day la dien thoai nhan update phan mem va bao mat dai nhat - 7 nam."
        ),
        "reviews": [
            "Tinh nang AI chinh anh Magic Eraser xoa vat the thua cuc ky chinh xac.",
            "Android thuan Google, update nhanh va khong bloatware.",
            "Nhiet do may hoi cao khi choi game nang, nhung dung hang ngay thi on.",
        ],
    },
]


# ------------------------------------------------------------------
# HAM TIEN ICH
# ------------------------------------------------------------------
def build_text(product: dict) -> str:
    """Ket hop name, description va reviews thanh doan text cho embedding."""
    reviews_text = " | ".join(product["reviews"])
    return (
        f"Ten san pham: {product['name']}. "
        f"Thuong hieu: {product['brand']}. "
        f"Mo ta: {product['description']} "
        f"Danh gia nguoi dung: {reviews_text}"
    )


# ------------------------------------------------------------------
# POSTGRES
# ------------------------------------------------------------------
def ingest_postgres() -> int:
    from sqlalchemy import Column, Integer, Numeric, String, Text, create_engine
    from sqlalchemy.orm import Session, declarative_base

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
        stock = Column(Integer, nullable=False, default=0)
        specs = Column(Text, nullable=True)
        description = Column(Text, nullable=True)

    class Order(Base):
        __tablename__ = "orders"
        id = Column(Integer, primary_key=True, autoincrement=True)
        product_id = Column(Integer, nullable=False)
        product_name = Column(String(255), nullable=False)
        quantity = Column(Integer, nullable=False)
        customer_name = Column(String(255), nullable=True)
        customer_phone = Column(String(50), nullable=True)
        status = Column(String(50), nullable=False, default="pending")
        note = Column(Text, nullable=True)
        created_at = Column(String(50), nullable=False)

    class SupportRequest(Base):
        __tablename__ = "support_requests"
        id = Column(Integer, primary_key=True, autoincrement=True)
        session_id = Column(String(100), nullable=True)
        reason = Column(Text, nullable=False)
        customer_name = Column(String(255), nullable=True)
        customer_phone = Column(String(50), nullable=True)
        status = Column(String(50), nullable=False, default="pending")
        created_at = Column(String(50), nullable=False)

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    inserted = 0
    with Session(engine) as session:
        for p in PRODUCTS:
            row = Product(
                id=p["id"],
                name=p["name"],
                brand=p["brand"],
                price=p["price"],
                stock=p["stock"],
                specs=json.dumps(p["specs"], ensure_ascii=False),
                description=p["description"],
            )
            session.add(row)
            inserted += 1
        session.commit()

    return inserted


# ------------------------------------------------------------------
# QDRANT + EMBEDDING
# ------------------------------------------------------------------
def ingest_qdrant() -> int:
    from openai import OpenAI
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    oai = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
    qdrant = QdrantClient(path=QDRANT_PATH)

    existing = [c.name for c in qdrant.get_collections().collections]
    if QDRANT_COLLECTION in existing:
        qdrant.delete_collection(QDRANT_COLLECTION)

    qdrant.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )

    points = []
    for p in PRODUCTS:
        text_chunk = build_text(p)
        response = oai.embeddings.create(model=EMBED_MODEL, input=text_chunk)
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

    qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)
    return len(points)


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():
    print("=" * 55)
    print("  Shopping Assistant  |  Ingest Data")
    print("=" * 55)

    print("\n[1/2] Nap du lieu vao PostgreSQL...")
    try:
        pg_count = ingest_postgres()
        print(f"  PostgreSQL: da luu {pg_count} san pham vao bang 'products'")
    except Exception as e:
        print(f"  PostgreSQL FAIL: {e}")
        sys.exit(1)

    print("\n[2/2] Tao embedding va nap vector vao Qdrant...")
    print(f"  Dang goi OpenAI API ({EMBED_MODEL}) de tao vector...")
    try:
        qd_count = ingest_qdrant()
        print(
            f"  Qdrant: da upsert {qd_count} vector vao collection '{QDRANT_COLLECTION}'"
        )
    except Exception as e:
        print(f"  Qdrant FAIL: {e}")
        sys.exit(1)

    print()
    print("-" * 55)
    print("  Ket qua nap du lieu:")
    print(f"    PostgreSQL  ->  {pg_count} ban ghi  (bang: products)")
    print(f"    Qdrant      ->  {qd_count} vector   (collection: {QDRANT_COLLECTION})")
    print("-" * 55)
    print("  Hoan tat! San sang chay:  python run.py")


if __name__ == "__main__":
    main()
