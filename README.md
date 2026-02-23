# Shopping Assistant AI Agent

Chatbot tu van mua dien thoai thong minh, xay dung theo chuan OpenAI Agents SDK voi:

- **Agent Loop**: LLM tu quyet dinh goi tool, lap lai cho den khi xong
- **Handoffs**: SalesAgent <-> CompareAgent uy quyen cho nhau
- **Sessions**: Nho lich su hoi thoai (hieu "cai do" la gi)
- **Guardrails**: Kiem tra input/output, chan prompt injection
- **MCP Inventory**: Quan ly ton kho, dat hang, restock
- **Human-in-the-Loop**: Chuyen tiep sang nhan vien khi can

## Kien truc he thong

```
Nguoi dung (Browser)
     |
     v
 Flask Web UI  (port 5000)
     |
     v
 ShoppingAgent  (Agent Loop - gpt-4.1-mini function calling)
     |
     +---> Tool: search_products ----> OpenAI Embedding --> Qdrant
     +---> Tool: get_product_details -> PostgreSQL
     +---> Tool: check_inventory -----> PostgreSQL
     +---> Tool: place_order ---------> PostgreSQL
     +---> Tool: request_human_support -> PostgreSQL
     +---> Tool: save_customer_info ---> PostgreSQL
     +---> Handoff: transfer_to_compare_agent / transfer_to_sales_agent
     |
     v
 Tra loi Markdown --> Hien thi tren giao dien
```

## Stack cong nghe

| Thanh phan      | Cong nghe                       | Muc dich                                 |
| --------------- | ------------------------------- | ---------------------------------------- |
| Agent Loop      | OpenAI `gpt-4.1-mini`           | Function calling, tu chon tool, lap vong |
| Embedding       | OpenAI `text-embedding-3-small` | Chuyen van ban thanh vector 1536-dim     |
| Vector Database | Qdrant (local mode)             | Tim kiem san pham bang ngu nghia         |
| Relational DB   | PostgreSQL                      | San pham, don hang, yeu cau ho tro       |
| Backend         | Flask                           | REST API va giao dien web                |
| Frontend        | HTML/CSS/JS + marked.js         | Giao dien chat 4 tab                     |
| Config          | python-dotenv (`.env`)          | Quan ly cau hinh tap trung               |

## Yeu cau he thong

- **Python** >= 3.10
- **PostgreSQL** >= 14
- **OpenAI API Key** (ho tro model `gpt-4.1-mini` va `text-embedding-3-small`)

## Cai dat

### 1. Clone repository

```bash
git clone <repo-url>
cd AI_Agent
```

### 2. Cai dat PostgreSQL

- Tai va cai dat PostgreSQL: https://www.postgresql.org/download/
- Tao database:

```sql
CREATE DATABASE shopping_assistant;
```

### 3. Tao moi truong ao Python (venv)

```bash
python -m venv .venv
```

Kich hoat venv:

- **Windows (PowerShell):**

```powershell
.venv\Scripts\Activate.ps1
```

- **Windows (CMD):**

```cmd
.venv\Scripts\activate.bat
```

- **Linux / macOS:**

```bash
source .venv/bin/activate
```

### 4. Cai dat thu vien Python

```bash
pip install -r requirements.txt
```

### 5. Cau hinh bien moi truong

Copy file mau va dien thong tin:

```bash
cp .env.example .env
```

Mo file `.env` va cap nhat:

```dotenv
# Bat buoc thay doi
POSTGRES_PASSWORD=mat_khau_postgres_cua_ban
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxx

# Cac gia tri khac giu nguyen hoac tuy chinh theo nhu cau
```

Xem file `.env.example` de biet day du cac bien can thiet.

### 6. Kiem tra ket noi

```bash
python scripts/check_health.py
```

Ket qua mong doi:

```
Postgres: OK
Qdrant:   OK
```

### 7. Nap du lieu san pham

```bash
python scripts/ingest_data.py
```

Lenh nay se:

- Tao bang `products`, `orders`, `support_requests` trong PostgreSQL
- Nap 5 san pham mau (co stock)
- Tao embedding vector va luu vao Qdrant (thu muc `qdrant_data/`)

## Chay ung dung

```bash
python run.py
```

Truy cap: **http://localhost:5000**

Giao dien gom 4 tab:

- **Chat AI** -- Hoi dap voi chatbot tu van dien thoai
- **San pham** -- Xem danh sach san pham trong kho
- **Quan ly** -- Xem don hang, yeu cau ho tro (cho nhan vien)
- **He thong** -- Kiem tra trang thai PostgreSQL, Qdrant

## Cau truc thu muc

```
AI_Agent/
├── .env                  # Bien moi truong (KHONG push len git)
├── .env.example          # Mau file .env
├── .gitignore
├── requirements.txt
├── README.md
├── run.py                # Entry point: python run.py
│
├── app/                  # Package chinh
│   ├── __init__.py       # Flask factory create_app()
│   ├── config.py         # Cau hinh tap trung (doc .env)
│   ├── routes.py         # Flask routes (API endpoints)
│   ├── sessions.py       # Session store (lich su hoi thoai)
│   ├── guardrails.py     # Input/Output validation
│   │
│   ├── agent/            # Agent package
│   │   ├── __init__.py   # Export ShoppingAgent
│   │   ├── core.py       # Agent Loop (LLM + tool calling)
│   │   ├── tools.py      # Tool definitions + dispatch
│   │   ├── prompts.py    # System prompts + agent configs
│   │   └── schemas.py    # Pydantic models
│   │
│   └── services/         # Business logic
│       ├── __init__.py
│       ├── search.py     # Qdrant semantic search
│       ├── product.py    # Product details (Postgres)
│       ├── inventory.py  # Ton kho + dat hang (MCP)
│       └── support.py    # Human-in-the-Loop
│
├── scripts/              # Utility scripts
│   ├── check_health.py   # Kiem tra ket noi
│   └── ingest_data.py    # Nap du lieu san pham
│
├── templates/
│   └── index.html        # SPA frontend (4 tab)
│
├── qdrant_data/          # Du lieu vector Qdrant (auto-generated)
└── .venv/                # Moi truong ao Python
```

## API Endpoints

| Method | Endpoint                | Mo ta                        |
| ------ | ----------------------- | ---------------------------- |
| GET    | `/`                     | Trang chu (giao dien chat)   |
| POST   | `/api/chat`             | Gui tin nhan cho chatbot     |
| GET    | `/api/products`         | Lay danh sach san pham       |
| GET    | `/api/stock`            | Xem ton kho toan bo          |
| GET    | `/api/orders`           | Xem danh sach don hang       |
| GET    | `/api/support-requests` | Xem yeu cau ho tro           |
| POST   | `/api/session/clear`    | Xoa session hoi thoai        |
| GET    | `/api/health`           | Kiem tra trang thai he thong |

### Vi du goi API chat

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Co thong tin gi ve OPPO khong?"}'
```

## Luu y

- File `.env` chua API key va mat khau -- **KHONG BAO GIO** push len GitHub.
- Thu muc `qdrant_data/` se duoc tao tu dong khi chay `scripts/ingest_data.py`.
- Neu doi `EMBED_MODEL` hoac `EMBED_DIM`, can xoa `qdrant_data/` va chay lai `scripts/ingest_data.py`.
- Entry point duy nhat: `python run.py`. Cac script tien ich chay tu `scripts/`.
