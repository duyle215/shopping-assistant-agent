# Shopping Assistant Agent

A phone-shopping chatbot built directly on **OpenAI function calling** (no agent framework). The model decides which tools to call and loops until it can answer. Two specialised agents hand off to each other, conversations are remembered per session, and guardrails check every input and output. Product questions are answered with **semantic search over a vector database**, while stock, orders, and support requests live in **PostgreSQL**.

The chatbot answers in Vietnamese.

## Features

- **Agent loop:** `gpt-4.1-mini` picks tools, reads their results, and repeats (up to 10 rounds) until it returns a final answer.
- **Handoffs:** a `SalesAgent` (search, stock, orders) and a `CompareAgent` (side-by-side comparisons) transfer the conversation to each other through dedicated handoff tools. Each agent has its own system prompt and tool set.
- **RAG product search:** product descriptions are embedded with `text-embedding-3-small` and stored in Qdrant. Search supports an optional brand filter.
- **Transactional tools:** check stock, place orders (stock is deducted if available, otherwise a pending order and a restock request are created), and save customer details on an order.
- **Human-in-the-loop:** the agent can open a support request for staff when it cannot help.
- **Sessions:** the last 20 turns of each conversation are kept for one hour, so follow-ups like "how much is that one?" resolve correctly.
- **Guardrails:** inputs are checked for length and common prompt-injection patterns. Outputs are checked for leaked internals (system prompt, vector-store details, API keys).
- **Web UI:** Flask app with four tabs (chat, products, staff view of orders and support requests, system health) and a REST API.

## Architecture

```
Browser ──► Flask (routes.py) ──► ShoppingAgent.run()
                                     │
                    input guardrail ─┤
                                     ▼
                     ┌──────── agent loop (gpt-4.1-mini) ◄────────┐
                     │   tool calls                               │ tool results
                     ▼                                            │
   SalesAgent ◄─ handoff ─► CompareAgent                           │
     ├─ search_products ─────────► OpenAI embeddings ─► Qdrant ───┤
     ├─ get_product_details ─────► PostgreSQL ────────────────────┤
     ├─ check_inventory / place_order ─► PostgreSQL ──────────────┤
     ├─ save_customer_info ──────► PostgreSQL ────────────────────┤
     └─ request_human_support ───► PostgreSQL ────────────────────┘
                                     │
                   output guardrail ─┤
                                     ▼
                         Markdown answer + session update
```

| Tool | SalesAgent | CompareAgent |
| --- | :---: | :---: |
| `search_products` | ✓ | ✓ |
| `get_product_details` | ✓ | ✓ |
| `check_inventory` | ✓ | |
| `place_order` | ✓ | |
| `save_customer_info` | ✓ | ✓ |
| `request_human_support` | ✓ | ✓ |
| `transfer_to_compare_agent` | ✓ | |
| `transfer_to_sales_agent` | | ✓ |

## Tech stack

| Component | Technology |
| --- | --- |
| LLM and tool calling | OpenAI `gpt-4.1-mini` (Chat Completions API) |
| Embeddings | OpenAI `text-embedding-3-small` (1536-d) |
| Vector database | Qdrant (local mode) |
| Relational database | PostgreSQL, SQLAlchemy |
| Backend | Flask |
| Frontend | HTML, CSS, JavaScript, marked.js |
| Validation | Pydantic |

## Getting started

Requirements: Python 3.10+, PostgreSQL 14+, and an OpenAI API key.

```bash
git clone https://github.com/duyle215/shopping-assistant-agent.git
cd shopping-assistant-agent
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux / macOS
pip install -r requirements.txt
```

Create the database and the config file:

```sql
CREATE DATABASE shopping_assistant;
```

```bash
cp .env.example .env              # then set POSTGRES_PASSWORD and OPENAI_API_KEY
```

Check connections, load sample products (creates the tables, inserts 5 products, and builds the Qdrant index), and start the app:

```bash
python scripts/check_health.py    # expects: Postgres OK, Qdrant OK
python scripts/ingest_data.py
python run.py                     # http://localhost:5000
```

If you change `EMBED_MODEL` or `EMBED_DIM`, delete `qdrant_data/` and run `scripts/ingest_data.py` again.

## API

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/` | Chat UI |
| POST | `/api/chat` | Send a message: `{"message": "...", "session_id": "..."}` |
| GET | `/api/products` | List products |
| GET | `/api/stock` | Stock levels |
| GET | `/api/orders` | Orders |
| GET | `/api/support-requests` | Human support requests |
| POST | `/api/session/clear` | Clear a conversation |
| GET | `/api/health` | PostgreSQL and Qdrant status |

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Co thong tin gi ve OPPO khong?"}'
```

## Project structure

```
.
├── run.py                  # Entry point
├── app/
│   ├── __init__.py         # Flask app factory
│   ├── config.py           # Settings loaded from .env
│   ├── routes.py           # REST endpoints and UI
│   ├── sessions.py         # In-memory session store (20 turns, 1 h TTL)
│   ├── guardrails.py       # Input and output checks
│   ├── agent/
│   │   ├── core.py         # Agent loop and handoffs
│   │   ├── tools.py        # Tool schemas and dispatch
│   │   ├── prompts.py      # System prompts and per-agent tool sets
│   │   └── schemas.py      # Pydantic response models
│   └── services/
│       ├── search.py       # Qdrant semantic search
│       ├── product.py      # Product details
│       ├── inventory.py    # Stock and orders
│       └── support.py      # Human support requests
├── scripts/
│   ├── check_health.py
│   └── ingest_data.py
└── templates/index.html    # Single-page UI
```

## Notes

- `.env` holds API keys and passwords and is git-ignored. Never commit it.
- Sessions are kept in memory, so they reset when the server restarts.
