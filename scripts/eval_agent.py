"""
Eval Agent - chay cac kich ban hoi thoai trong evals/scenarios.yaml va cham diem.

Kiem tra bang luat (tool phai goi, tham so, agent, noi dung cau tra loi, thay doi trong DB,
gia trong cau tra loi phai co trong catalog) va, neu bat --judge, them LLM lam giam khao
(cau tra loi co bia thong tin ngoai du lieu tool tra ve khong).

Backend la Odoo: chay tren database Odoo rieng (mac dinh odoo_eval, tao bang
`docker compose run --rm odoo-setup odoo_eval`, Odoo chay voi ODOO_DB_FILTER=^odoo).
Truoc moi kich ban: huy don cua chatbot va dat lai ton kho theo data/stock.json, qua API Odoo.
Kiem tra DB: don ban (sale.order), yeu cau ho tro (crm.lead) cua phien chat do, ton kho con ban.
Vector nam o collection Qdrant rieng (product_knowledge_eval). Traces o Postgres shopping_assistant_eval.

    python scripts/eval_agent.py                       # tat ca kich ban
    python scripts/eval_agent.py --category order      # mot nhom
    python scripts/eval_agent.py --only order-confirmed compare-a55-a35
    python scripts/eval_agent.py --judge               # them LLM giam khao (ton them quota)
    python scripts/eval_agent.py --judge --resume      # chay tiep lan truoc bi ngat (cung commit, model)
    python scripts/eval_agent.py --workers 6           # so luong song song (mac dinh 4)

Moi kich ban xong duoc ghi ngay vao .cache/agent_eval_progress.jsonl. Het quota thi dung lai,
khong ghi kich ban dang do; --resume bo qua cac kich ban da xong cua cung commit + model + giam khao.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))


# ------------------------------------------------------------------
# SETUP DATABASE RIENG CHO EVAL
# ------------------------------------------------------------------
def setup_database(db_name: str, odoo_db: str) -> None:
    os.environ["POSTGRES_DB"] = db_name
    os.environ["ODOO_DB"] = odoo_db
    os.environ.setdefault("QDRANT_COLLECTION_EVAL", "product_knowledge_eval")
    os.environ["QDRANT_COLLECTION"] = os.environ["QDRANT_COLLECTION_EVAL"]
    # Key trong .env la cua database demo; key cua odoo_eval doc tu odoo/secrets/odoo_eval.json
    os.environ.pop("ODOO_API_KEY", None)
    os.environ.pop("ODOO_ADMIN_API_KEY", None)
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        dbname="postgres",
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{db_name}"')
    conn.close()


def load_catalog_into_odoo(reindex: bool) -> dict[int, dict]:
    """Dong bo catalog vao Odoo eval (+ Qdrant neu chua co). Tra ve {catalog_id: san pham + odoo_id}."""
    from sync_odoo import ingest_qdrant, load_catalog, sync_products

    from app.config import QDRANT_COLLECTION
    from app.db import get_qdrant
    from app.odoo import get_odoo

    products = load_catalog([os.path.join(ROOT, "data/catalog.jsonl")], os.path.join(ROOT, "data/stock.json"))
    ids = sync_products(get_odoo(admin=True), products)
    if reindex or not get_qdrant().collection_exists(QDRANT_COLLECTION):
        print(f"  Qdrant: {ingest_qdrant(products, ids)} vector -> {QDRANT_COLLECTION}")
    return {p["catalog_id"]: {**p, "odoo_id": ids[p["catalog_id"]]} for p in products}


def reset_state(catalog: dict[int, dict]) -> None:
    """Huy don cua chatbot (tra lai hang da giu) roi dat lai ton kho nhung may bi lech."""
    from app.odoo import get_odoo

    odoo = get_odoo(admin=True)
    orders = odoo.search("sale.order", [("chat_session_id", "!=", False), ("state", "!=", "cancel")])
    if orders:
        odoo.call("sale.order", "action_cancel", ids=orders)
    current = {
        r["id"]: r["chat_free_qty"]
        for r in odoo.search_read(
            "product.template", [("id", "in", [p["odoo_id"] for p in catalog.values()])], ["chat_free_qty"]
        )
    }
    levels = {p["odoo_id"]: p["stock"] for p in catalog.values() if current.get(p["odoo_id"]) != p["stock"]}
    if levels:
        from sync_odoo import set_stock

        set_stock(odoo, levels, quiet=True)


def translate_ids(scenarios: list[dict], catalog: dict[int, dict]) -> None:
    """Kich ban ghi product_id theo catalog (1..30); doi sang id product.template trong Odoo."""
    to_odoo = {cid: p["odoo_id"] for cid, p in catalog.items()}

    def conv(rule):
        if isinstance(rule, int):
            return to_odoo.get(rule, rule)
        if isinstance(rule, list):
            return [conv(r) for r in rule]
        if isinstance(rule, dict):
            return {k: conv(v) for k, v in rule.items()}
        return rule

    for sc in scenarios:
        for turn in sc["turns"]:
            for rules in (turn.get("args") or {}).values():
                for key in ("product_id", "product_ids"):
                    if key in rules:
                        rules[key] = conv(rules[key])


# ------------------------------------------------------------------
# CHECKPOINT
# ------------------------------------------------------------------
PROGRESS = os.path.join(ROOT, ".cache/agent_eval_progress.jsonl")


class OutOfQuota(Exception):
    """Model het quota (agent tra cau 'he thong ban'): dung, khong tinh kich ban dang do."""


def load_progress(key: dict) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec["key"] == key:
                    done[rec["result"]["id"]] = rec["result"]
    return done


def save_progress(key: dict, result: dict) -> None:
    os.makedirs(os.path.dirname(PROGRESS), exist_ok=True)
    with open(PROGRESS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "result": result}, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------
# KIEM TRA
# ------------------------------------------------------------------
def _norm(value):
    """So sanh khong phan biet hoa thuong; '15' va 15 la mot (model hay truyen so dang chuoi)."""
    if isinstance(value, str):
        v = value.strip().lower()
        return int(v) if v.isdigit() else v
    return value


def rule_ok(actual, rule) -> bool:
    if isinstance(rule, dict):
        if actual is None:
            return False
        if "lte" in rule:
            return float(actual) <= rule["lte"]
        if "gte" in rule:
            return float(actual) >= rule["gte"]
        if "in" in rule:
            return _norm(actual) in [_norm(v) for v in rule["in"]]
        if "contains" in rule:
            return isinstance(actual, list) and all(_norm(v) in [_norm(a) for a in actual] for v in rule["contains"])
        raise ValueError(f"Rule la: {rule}")
    return _norm(actual) == _norm(rule)


_PRICE_DOTTED = re.compile(r"(?<![\d.,])\d{1,3}(?:[.,]\d{3}){2,}(?![\d])")
_PRICE_MILLION = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:triệu|trieu|million)", re.IGNORECASE)


def prices_in(answer: str) -> set[int]:
    found = {int(re.sub(r"[.,]", "", m.group())) for m in _PRICE_DOTTED.finditer(answer)}
    for m in _PRICE_MILLION.finditer(answer):
        found.add(int(round(float(m.group(1).replace(",", ".")) * 1_000_000)))
    return {p for p in found if p >= 1_000_000}


def allowed_prices(catalog: dict[int, dict]) -> set[int]:
    prices = [p["price_vnd"] for p in catalog.values()]
    allowed = {p * q for p in prices for q in range(1, 21)}
    allowed |= {abs(a - b) for a in prices for b in prices}
    return allowed


def db_snapshot(session_id: str, catalog: dict[int, dict]) -> dict:
    """Trang thai Odoo sau kich ban: don va yeu cau ho tro cua phien nay, ton kho theo id catalog."""
    from app.odoo import get_odoo

    odoo = get_odoo(admin=True)
    orders = odoo.search_read("sale.order", [("chat_session_id", "=", session_id)], ["state", "chat_shortage"])
    status = {"sale": "confirmed", "draft": "pending_restock"}
    support = len(odoo.search("crm.lead", [("chat_session_id", "=", session_id)]))
    by_odoo = {p["odoo_id"]: cid for cid, p in catalog.items()}
    stock = {
        by_odoo[r["id"]]: r["chat_free_qty"]
        for r in odoo.search_read("product.template", [("id", "in", list(by_odoo))], ["chat_free_qty"])
    }
    return {
        "orders": [status.get(o["state"], o["state"]) for o in orders],
        "support_requests": support,
        "stock": stock,
    }


def turn_tool_calls(agent, session_id: str) -> tuple[list[tuple[str, dict]], list[str]]:
    values = agent.graph.get_state({"configurable": {"thread_id": session_id}}).values
    calls, outputs = [], []
    for m in values.get("turn", []):
        for tc in m.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append((tc["function"]["name"], args))
        if m.get("role") == "tool":
            outputs.append(m["content"])
    return calls, outputs


def check_turn(turn: dict, resp, calls, had_pending: bool, allowed: set[int]) -> list[str]:
    fails: list[str] = []
    answer = resp.answer_markdown or ""
    # So noi dung tren chu thuan: "còn **7** chiếc" -> "còn 7 chiếc"
    low = re.sub(r"[*_`]+", "", answer).lower()
    names = [n for n, _ in calls]

    if not answer.strip():
        fails.append("empty answer")
    if resp.warning and not turn.get("allow_warning") and resp.intent != "blocked":
        fails.append(f"warning: {resp.warning}")
    for tool in turn.get("tools", []):
        if tool not in names:
            fails.append(f"tool not called: {tool}")
    for tool in turn.get("not_tools", []):
        if tool in names:
            fails.append(f"tool should not be called: {tool}")
    for tool, rules in (turn.get("args") or {}).items():
        candidates = [a for n, a in calls if n == tool]
        if candidates and not any(all(rule_ok(a.get(k), r) for k, r in rules.items()) for a in candidates):
            fails.append(f"args of {tool} {candidates} do not match {rules}")
    if turn.get("agent") and resp.intent != turn["agent"]:
        fails.append(f"agent {resp.intent} != {turn['agent']}")
    if turn.get("contains_any") and not any(s.lower() in low for s in turn["contains_any"]):
        fails.append(f"answer has none of {turn['contains_any']}")
    for s in turn.get("contains_all", []):
        if s.lower() not in low:
            fails.append(f"answer missing '{s}'")
    for s in turn.get("not_contains", []):
        if s.lower() in low:
            fails.append(f"answer contains '{s}'")
    if turn.get("pending_confirmation") and not had_pending:
        fails.append("no order confirmation shown")
    if turn.get("english"):
        # Chu co dau tieng Viet (khong tinh ten san pham): qua 5 ky tu -> dang tra loi tieng Viet
        vietnamese = re.findall(r"[ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ]", low)
        if len(vietnamese) > 5:
            fails.append(f"answer is not in English ({len(vietnamese)} Vietnamese characters)")
    bad_prices = sorted(prices_in(answer) - allowed)
    if bad_prices:
        fails.append(f"prices not in catalog: {bad_prices}")
    return fails


def check_db(expect: dict, snap: dict) -> list[str]:
    fails = []
    if "orders" in expect and len(snap["orders"]) != expect["orders"]:
        fails.append(f"orders {len(snap['orders'])} != {expect['orders']}")
    if "order_status" in expect and expect["order_status"] not in snap["orders"]:
        fails.append(f"no order with status {expect['order_status']} (got {snap['orders']})")
    if "support_requests" in expect and snap["support_requests"] < expect["support_requests"]:
        fails.append(f"support_requests {snap['support_requests']} < {expect['support_requests']}")
    for pid, stock in (expect.get("stock") or {}).items():
        if snap["stock"].get(int(pid)) != stock:
            fails.append(f"stock of #{pid} = {snap['stock'].get(int(pid))} != {stock}")
    return fails


# ------------------------------------------------------------------
# LLM GIAM KHAO (tuy chon)
# ------------------------------------------------------------------
JUDGE_PROMPT = (
    "You grade a Vietnamese phone-shop chatbot. You get the conversation so far, the data the "
    "bot's tools returned in any turn of it, and the bot's LAST answer, which is the one you grade. "
    "Judge facts ONLY against the tool data; earlier messages are context (what the customer asked "
    "or said, e.g. their budget), and the bot's earlier answers are not evidence.\n"
    "- grounded: false if the last answer states any product fact (price, spec, feature, stock, "
    "policy) that is not supported by the tool data. Greetings and questions do not count.\n"
    "- ungrounded_claims: list those facts (empty if grounded).\n"
    "- helpful: 1-5, does it answer what the customer asked.\n"
    "- polite: natural, polite Vietnamese."
)


def judge(conversation: str, tool_outputs: list[str], answer: str, model: str) -> dict:
    from pydantic import BaseModel

    from app.agent.llm import client

    class Verdict(BaseModel):
        grounded: bool
        ungrounded_claims: list[str]
        helpful: int
        polite: bool

    data = "\n\n".join(tool_outputs)[:16000] or "(no tool was called)"
    from openai import RateLimitError

    from app.agent.llm import _retry_after

    for attempt in range(1, 5):
        try:
            return _judge_once(client, Verdict, conversation, data, answer, model)
        except RateLimitError as exc:
            if attempt == 4:
                raise
            time.sleep(min(max(_retry_after(exc) or 0, 15.0 * attempt), 90.0))


def _judge_once(client, Verdict, conversation, data, answer, model) -> dict:
    resp = client().chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": f"CONVERSATION:\n{conversation}\n\nTOOL DATA (all turns):\n{data}\n\nLAST ANSWER:\n{answer}"},
        ],
        response_format=Verdict,
        temperature=0,
    )
    return resp.choices[0].message.parsed.model_dump()


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default=os.path.join(ROOT, "evals/scenarios.yaml"))
    parser.add_argument("--report", default=os.path.join(ROOT, "docs/agent_eval.md"))
    parser.add_argument("--db", default="shopping_assistant_eval", help="Postgres cua agent (traces)")
    parser.add_argument("--odoo-db", default="odoo_eval", help="Database Odoo cho eval")
    parser.add_argument("--reindex", action="store_true", help="Tao lai vector Qdrant cho eval")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--category")
    parser.add_argument("--judge", action="store_true", help="LLM giam khao cho luot cuoi moi kich ban")
    parser.add_argument("--judge-model", default=None)
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Ghi de ket qua cac kich ban vua chay vao lan chay day du truoc (.cache) roi viet lai bao cao",
    )
    parser.add_argument("--sleep", type=float, default=4.0, help="Nghi giua cac kich ban (giay)")
    parser.add_argument("--workers", type=int, default=4, help="So luong chay song song (kich ban khong dung Odoo)")
    parser.add_argument("--retry-wait", type=float, default=20.0, help="Cho truoc khi chay lai sau loi tam thoi")
    parser.add_argument(
        "--resume", action="store_true", help="Bo qua kich ban da xong o lan chay truoc (cung commit, model, giam khao)"
    )
    args = parser.parse_args()

    setup_database(args.db, args.odoo_db)

    import yaml
    from langgraph.checkpoint.memory import MemorySaver
    from sqlalchemy import text

    from app.agent.core import ShoppingAgent
    from app.config import LLM_MODEL
    from app.db import get_engine
    from app.models import create_tables

    with open(args.scenarios, encoding="utf-8") as f:
        scenarios = yaml.safe_load(f)
    if args.only:
        scenarios = [s for s in scenarios if s["id"] in args.only]
    if args.category:
        scenarios = [s for s in scenarios if s["category"] == args.category]

    catalog = load_catalog_into_odoo(args.reindex)
    translate_ids(scenarios, catalog)
    create_tables(get_engine())
    allowed = allowed_prices(catalog)
    judge_model = args.judge_model or LLM_MODEL

    commit = current_commit()
    key = {"commit": commit, "model": LLM_MODEL, "judge": judge_model if args.judge else None}
    done = load_progress(key) if args.resume else {}
    if not args.resume and os.path.exists(PROGRESS):
        os.remove(PROGRESS)
    results = [done[s["id"]] for s in scenarios if s["id"] in done]
    consecutive_errors = 0
    started = time.time()
    todo = [s for s in scenarios if s["id"] not in done]
    print(
        f"Chay {len(todo)} kich ban voi {LLM_MODEL} (Odoo: {args.odoo_db}, traces: {args.db})"
        + (f"; {len(done)} kich ban da xong o lan truoc" if done else "")
        + "\n"
    )

    import threading
    from concurrent.futures import ThreadPoolExecutor

    lock = threading.Lock()
    stop = threading.Event()
    errors = {"consecutive": 0}
    local = threading.local()

    def worker_agent():
        # Moi luong mot agent (graph + checkpointer rieng)
        if not hasattr(local, "agent"):
            local.agent = ShoppingAgent(checkpointer=MemorySaver())
        return local.agent

    def run_scenario(sc: dict, reset: bool) -> None:
        if stop.is_set():
            return
        agent = worker_agent()
        for attempt in (1, 2):
            if reset:
                reset_state(catalog)
            session = f"eval-{sc['id']}-{uuid.uuid4().hex[:6]}"
            fails: list[str] = []
            answers: list[str] = []
            all_outputs: list[str] = []  # du lieu tool cua moi luot, cho giam khao
            verdict = None
            try:
                for i, turn in enumerate(sc["turns"], start=1):
                    resp = agent.run(turn["user"], session, lang=sc.get("lang", "vi"))
                    had_pending = resp.pending_confirmation is not None
                    if had_pending and turn.get("confirm"):
                        resp = agent.confirm(session, turn["confirm"] == "approve")
                    if resp.intent == "error" and "han muc" in (resp.warning or ""):  # QuotaExhausted
                        raise OutOfQuota(resp.warning)
                    answers.append(resp.answer_markdown or "")
                    calls, outputs = turn_tool_calls(agent, session)
                    all_outputs += outputs
                    fails += [f"turn {i}: {f}" for f in check_turn(turn, resp, calls, had_pending, allowed)]
                fails += [f"db: {f}" for f in check_db(sc.get("db") or {}, db_snapshot(session, catalog))]
                if args.judge and resp.intent != "blocked" and not resp.pending_confirmation:
                    # Giam khao xem ca hoi thoai: khach co the noi ngan sach o luot truoc,
                    # bot co the tra loi bang du lieu tool cua luot truoc ("pin cua no?")
                    convo = "\n".join(
                        f"Customer: {t['user']}\nBot: {a}" for t, a in zip(sc["turns"][:-1], answers[:-1])
                    )
                    convo += f"\nCustomer: {sc['turns'][-1]['user']}"
                    verdict = judge(convo, all_outputs, resp.answer_markdown, judge_model)
                with lock:
                    errors["consecutive"] = 0
            except OutOfQuota as exc:
                print(f"  ...  {sc['id']}: het quota ({str(exc)[:120]}). Dung; chay lai voi --resume.")
                stop.set()
                return
            except Exception as exc:
                transient = any(k in type(exc).__name__ for k in ("RateLimit", "InternalServer", "Quota"))
                if attempt == 1 and transient:
                    print(f"  ...  {sc['id']}: loi tam thoi ({type(exc).__name__}), cho {args.retry_wait:.0f}s roi chay lai")
                    time.sleep(args.retry_wait)
                    continue
                with lock:
                    errors["consecutive"] += 1
                fails.append(f"error: {type(exc).__name__}: {str(exc)[:200]}")
            break

        with get_engine().connect() as conn:
            usage = conn.execute(
                text(
                    "SELECT coalesce(sum(prompt_tokens),0) AS pt, coalesce(sum(completion_tokens),0) AS ct, "
                    "count(*) FILTER (WHERE kind='llm') AS calls, "
                    "coalesce(sum(latency_ms) FILTER (WHERE kind='turn'),0) AS turn_ms "
                    "FROM traces WHERE session_id = :sid"
                ),
                {"sid": session},
            ).one()

        passed = not fails
        result = {
            "id": sc["id"],
            "category": sc["category"],
            "passed": passed,
            "fails": fails,
            "judge": verdict,
            "answers": answers,
            "commit": commit,
            "turns": len(sc["turns"]),
            "llm_calls": usage.calls,
            "prompt_tokens": int(usage.pt),
            "completion_tokens": int(usage.ct),
            "latency_ms": int(usage.turn_ms),
        }
        mark = "PASS" if passed else "FAIL"
        extra = "" if verdict is None else f"  judge: grounded={verdict['grounded']} helpful={verdict['helpful']}"
        with lock:
            results.append(result)
            # Loi tam thoi cua API (khong phai loi cua agent): khong luu, --resume se chay lai
            if not any(f.startswith("error:") for f in fails):
                save_progress(key, result)
            print(f"  {mark}  {sc['id']}{extra}")
            for f in fails:
                print(f"        - {f}")
            if errors["consecutive"] >= 3:
                print("\nDung som: 3 kich ban lien tiep loi (co the het quota API).")
                stop.set()
        time.sleep(args.sleep)

    # Kich ban khong dat hang va khong kiem tra Odoo chay song song. Kich ban co kiem tra Odoo
    # (don, ton kho, yeu cau ho tro) chay tuan tu: moi kich ban reset don va ton kho dung chung.
    def touches_shop(sc: dict) -> bool:
        return bool(sc.get("db")) or any(
            "place_order" in (t.get("tools") or []) or t.get("confirm") or t.get("pending_confirmation")
            for t in sc["turns"]
        )

    parallel = [sc for sc in todo if not touches_shop(sc)]
    serial = [sc for sc in todo if touches_shop(sc)]
    if parallel:
        reset_state(catalog)
        print(f"Song song ({args.workers} luong): {len(parallel)} kich ban")
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(lambda sc: run_scenario(sc, reset=False), parallel))
    if serial:
        print(f"Tuan tu (dat hang / kiem tra Odoo): {len(serial)} kich ban")
        for sc in serial:
            run_scenario(sc, reset=True)

    if len(results) < len(scenarios):
        print(
            f"\nChua du: {len(results)}/{len(scenarios)} kich ban. Khong viet bao cao; "
            "chay lai voi --resume de tiep tuc."
        )
        sys.exit(2)
    order = {s["id"]: i for i, s in enumerate(scenarios)}
    results.sort(key=lambda r: order[r["id"]])
    args.resumed = len(done)

    rerun: list[str] = []
    cache = os.path.join(ROOT, ".cache/agent_eval_results.json")
    if args.merge and os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            previous = json.load(f)
        fresh = {r["id"]: r for r in results}
        rerun = list(fresh)
        order = [s["id"] for s in yaml.safe_load(open(args.scenarios, encoding="utf-8"))]
        merged = {r["id"]: r for r in previous}
        merged.update(fresh)
        results = [merged[i] for i in order if i in merged]
    write_report(results, args, LLM_MODEL, time.time() - started, rerun)


def current_commit() -> str:
    import subprocess

    try:
        # Commit cuoi cung sua code duoc danh gia (agent + addon), khong phai HEAD:
        # sua script danh gia khong lam doi ket qua nen khong can chay lai
        commit = subprocess.run(
            ["git", "log", "-1", "--format=%h", "--", "app", "odoo/addons"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "app", "odoo/addons"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        return commit + ("+dirty" if dirty else "")
    except Exception:
        return "unknown"


def write_report(results: list[dict], args, model: str, seconds: float, rerun: list[str] | None = None) -> None:
    n = len(results)
    if not n:
        return
    passed = sum(r["passed"] for r in results)
    cats: dict[str, list[dict]] = {}
    for r in results:
        cats.setdefault(r["category"], []).append(r)
    turns = sum(r["turns"] for r in results) or 1
    judged = [r["judge"] for r in results if r["judge"]]

    commits: dict[str, int] = {}
    for r in results:
        commits[r.get("commit", "unknown")] = commits.get(r.get("commit", "unknown"), 0) + 1
    commit = ", ".join(f"{c} ({k} scenarios)" if len(commits) > 1 else c for c, k in commits.items())

    lines = [
        "# Agent evaluation",
        "",
        f"Code: `{commit}` · Backend: Odoo 19 · Model: `{model}` · Scenarios: {n} · Turns: {turns} · "
        f"Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        + ("" if rerun else f" ({seconds / 60:.0f} min)")
        + (
            f" · resumed: {args.resumed} scenarios came from an interrupted session on the same commit"
            if getattr(args, "resumed", 0)
            else ""
        ),
        "",
        f"**Task success: {passed}/{n} = {passed / n:.0%}** (a scenario passes only if every check in every turn passes)",
        *(
            [
                "",
                f"Merged report: {len(rerun)} scenarios were re-run after fixes and replace their results "
                f"from the previous full run ({', '.join(rerun)}).",
            ]
            if rerun
            else []
        ),
        "",
        "| Category | Passed | Rate |",
        "| --- | ---: | ---: |",
    ]
    for cat, rs in cats.items():
        p = sum(r["passed"] for r in rs)
        lines.append(f"| {cat} | {p}/{len(rs)} | {p / len(rs):.0%} |")

    lines += [
        "",
        "| Per turn (average) | Value |",
        "| --- | ---: |",
        f"| LLM calls | {sum(r['llm_calls'] for r in results) / turns:.1f} |",
        f"| Prompt tokens | {sum(r['prompt_tokens'] for r in results) / turns:,.0f} |",
        f"| Completion tokens | {sum(r['completion_tokens'] for r in results) / turns:,.0f} |",
        f"| Latency | {sum(r['latency_ms'] for r in results) / turns / 1000:.1f} s |",
    ]
    if judged:
        g = sum(j["grounded"] for j in judged)
        lines += [
            "",
            f"LLM judge on the last turn of {len(judged)} scenarios: grounded {g}/{len(judged)} = {g / len(judged):.0%}, "
            f"average helpfulness {sum(j['helpful'] for j in judged) / len(judged):.1f}/5, "
            f"polite {sum(j['polite'] for j in judged)}/{len(judged)}.",
        ]
        ungrounded = [(r["id"], r["judge"]["ungrounded_claims"]) for r in results if r["judge"] and not r["judge"]["grounded"]]
        if ungrounded:
            lines += ["", "| Scenario | Claims not supported by tool data |", "| --- | --- |"]
            lines += [f"| {sid} | {'; '.join(c)[:300]} |" for sid, c in ungrounded]

    failed = [r for r in results if not r["passed"]]
    lines += ["", "## Failures", ""]
    if failed:
        lines += ["| Scenario | Checks that failed |", "| --- | --- |"]
        lines += [f"| {r['id']} | {'<br>'.join(f.replace('|', '/') for f in r['fails'])[:600]} |" for r in failed]
    else:
        lines.append("None.")

    report = "\n".join(lines) + "\n"
    print("\n" + report)
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(report)
    cache = os.path.join(ROOT, ".cache/agent_eval_results.json")
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"-> {args.report}")


if __name__ == "__main__":
    main()
