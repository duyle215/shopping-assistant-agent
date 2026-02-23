# Shopping Assistant AI Agent

Chatbot tu van mua dien thoai thong minh, su dung ky thuat RAG (Retrieval-Augmented Generation) ket hop vector search va co so du lieu quan he.

## Kien truc he thong

```
Nguoi dung (Browser)
     |
     v
 Flask Web UI  (port 5000)
     |
     v
 ShoppingAgent (agent_core.py)
     |
     +---> Buoc 1: Intent Parsing -----> Ollama (qwen2.5:3b, local)
     |
     +---> Buoc 2: Tool Execution
     |         +---> search_products ---> OpenAI Embedding --> Qdrant (vector search)
     |         +---> get_product_details --> PostgreSQL (thong so ky thuat)
     |
     +---> Buoc 3: Synthesis ----------> OpenAI (gpt-4.1-mini)
     |
     v
 Tra loi Markdown --> Hien thi tren giao dien
```

## Stack cong nghe

| Thanh phan      | Cong nghe                       | Muc dich                                   |
| --------------- | ------------------------------- | ------------------------------------------ |
| LLM (Synthesis) | OpenAI `gpt-4.1-mini`           | Tong hop cau tra loi chat luong cao        |
| LLM (Intent)    | Ollama `qwen2.5:3b`             | Phan tich y dinh nguoi dung (local, nhanh) |
| Embedding       | OpenAI `text-embedding-3-small` | Chuyen van ban thanh vector 1536-dim       |
| Vector Database | Qdrant (local mode)             | Tim kiem san pham bang ngu nghia           |
| Relational DB   | PostgreSQL                      | Luu thong tin, thong so ky thuat san pham  |
| Backend         | Flask + FastAPI                 | REST API va giao dien web                  |
| Frontend        | HTML/CSS/JS + marked.js         | Giao dien chat, danh sach san pham         |
| Config          | python-dotenv (`.env`)          | Quan ly cau hinh va bi mat                 |

## Yeu cau he thong

- **Python** >= 3.10
- **PostgreSQL** >= 14
- **Ollama** >= 0.3 (chay local)
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

### 3. Cai dat Ollama

- Tai va cai dat Ollama: https://ollama.com/download
- Pull model can thiet:

```bash
ollama pull qwen2.5:3b
```

- Dam bao Ollama dang chay (mac dinh tai `http://localhost:11434`)

### 4. Tao moi truong ao Python (venv)

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

### 5. Cai dat thu vien Python

```bash
pip install -r requirements.txt
```

### 6. Cau hinh bien moi truong

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

### 7. Kiem tra ket noi

```bash
python check_health.py
```

Ket qua mong doi:

```
[OK] PostgreSQL -- ket noi thanh cong
[OK] Ollama    -- dang chay, co 1 model
[OK] Qdrant    -- san sang
```

### 8. Nap du lieu san pham

```bash
python ingest_data.py
```

Lenh nay se:

- Tao bang `products` trong PostgreSQL va nap 5 san pham mau
- Tao embedding vector va luu vao Qdrant (thu muc `qdrant_data/`)

## Chay ung dung

### Flask Web UI (khuyen dung)

```bash
python app.py
```

Truy cap: **http://localhost:5000**

Giao dien gom 3 tab:

- **Chat AI** -- Hoi dap voi chatbot tu van dien thoai
- **San pham** -- Xem danh sach san pham trong kho
- **He thong** -- Kiem tra trang thai PostgreSQL, Qdrant, Ollama

### FastAPI (REST API thuan)

```bash
uvicorn main:app --reload --port 8000
```

Truy cap Swagger docs: **http://localhost:8000/docs**

## Cau truc thu muc

```
AI_Agent/
├── .env                  # Bien moi truong (KHONG push len git)
├── .env.example          # Mau file .env
├── .gitignore
├── requirements.txt      # Danh sach thu vien Python
├── README.md
│
├── check_health.py       # Kiem tra ket noi PostgreSQL, Ollama, Qdrant
├── ingest_data.py        # Nap du lieu san pham vao PostgreSQL + Qdrant
├── agent_core.py         # AI Agent chinh (Intent -> Search -> Synthesis)
├── app.py                # Flask Web UI (chay bang: python app.py)
├── main.py               # FastAPI REST API
│
├── api/                  # FastAPI routes va schemas
│   ├── schemas.py
│   ├── dependencies.py
│   └── routes/
│       ├── chat.py
│       └── products.py
│
├── templates/
│   └── index.html        # Giao dien web (Chat, San pham, He thong)
│
├── qdrant_data/          # Du lieu vector Qdrant (auto-generated)
└── .venv/                # Moi truong ao Python (KHONG push len git)
```

## API Endpoints

| Method | Endpoint        | Mo ta                        |
| ------ | --------------- | ---------------------------- |
| GET    | `/`             | Trang chu (giao dien chat)   |
| POST   | `/api/chat`     | Gui tin nhan cho chatbot     |
| GET    | `/api/products` | Lay danh sach san pham       |
| GET    | `/api/health`   | Kiem tra trang thai he thong |

### Vi du goi API chat

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Co thong tin gi ve OPPO khong?"}'
```

## Luu y

- File `.env` chua API key va mat khau -- **KHONG BAO GIO** push len GitHub.
- Thu muc `qdrant_data/` se duoc tao tu dong khi chay `ingest_data.py`.
- Neu doi `EMBED_MODEL` hoac `EMBED_DIM`, can xoa thu muc `qdrant_data/` va chay lai `ingest_data.py`.
- Ollama phai dang chay truoc khi start ung dung (dung cho intent parsing).
