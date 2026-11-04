"""
Eval Agent - chay cac kich ban hoi thoai trong evals/scenarios.yaml va cham diem.

Kiem tra bang luat (tool phai goi, tham so, agent, noi dung cau tra loi, thay doi trong DB,
gia trong cau tra loi phai co trong catalog) va, neu bat --judge, them LLM lam giam khao
(cau tra loi co bia thong tin ngoai du lieu tool tra ve khong).

Chay tren database rieng (mac dinh shopping_assistant_eval), nap lai catalog vao Postgres,
dung chung Qdrant voi app (tat run.py truoc neu dung Qdrant local).

    python scripts/eval_agent.py                       # tat ca kich ban
    python scripts/eval_agent.py --category order      # mot nhom
    python scripts/eval_agent.py --only order-confirmed compare-a55-a35
    python scripts/eval_agent.py --judge               # them LLM giam khao (ton them quota)
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
def setup_database(db_name: str) -> None:
    os.environ["POSTGRES_DB"] = db_name
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


def load_catalog_into_db() -> dict[int, dict]:
    from ingest_data import ingest_postgres, load_catalog

    products = load_catalog([os.path.join(ROOT, "data/catalog.jsonl")], os.path.join(ROOT, "data/stock.json"))
    ingest_postgres(products)
    return {p["id"]: p for p in products}


def reset_state(catalog: dict[int, dict]) -> None:
    from sqlalchemy import text

    from app.db import get_engine

    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE orders, support_requests RESTART IDENTITY"))
        for pid, p in catalog.items():
            conn.execute(text("UPDATE products SET stock = :s WHERE id = :id"), {"s": p["stock"], "id": pid})


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
_PRICE_MILLION = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:triệu|trieu)", re.IGNORECASE)


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


def db_snapshot() -> dict:
    from sqlalchemy import text

    from app.db import get_engine

    with get_engine().connect() as conn:
        orders = conn.execute(text("SELECT status FROM orders")).scalars().all()
        support = conn.execute(text("SELECT count(*) FROM support_requests")).scalar_one()
        stock = dict(conn.execute(text("SELECT id, stock FROM products")).fetchall())
    return {"orders": orders, "support_requests": support, "stock": stock}


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
    "You grade a Vietnamese phone-shop chatbot. You get the customer's message, the data the "
    "bot's tools returned, and the bot's answer. Judge ONLY against the tool data.\n"
    "- grounded: false if the answer states any product fact (price, spec, feature, stock, "
    "policy) that is not supported by the tool data. Greetings and questions do not count.\n"
    "- ungrounded_claims: list those facts (empty if grounded).\n"
    "- helpful: 1-5, does it answer what the customer asked.\n"
    "- polite: natural, polite Vietnamese."
)


def judge(question: str, tool_outputs: list[str], answer: str, model: str) -> dict:
    from pydantic import BaseModel

    from app.agent.llm import client

    class Verdict(BaseModel):
        grounded: bool
        ungrounded_claims: list[str]
        helpful: int
        polite: bool

    data = "\n\n".join(tool_outputs)[:8000] or "(no tool was called)"
    from openai import RateLimitError

    from app.agent.llm import _retry_after

    for attempt in range(1, 5):
        try:
            return _judge_once(client, Verdict, question, data, answer, model)
        except RateLimitError as exc:
            if attempt == 4:
                raise
            time.sleep(min(max(_retry_after(exc) or 0, 15.0 * attempt), 90.0))


def _judge_once(client, Verdict, question, data, answer, model) -> dict:
    resp = client().chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": f"CUSTOMER:\n{question}\n\nTOOL DATA:\n{data}\n\nANSWER:\n{answer}"},
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
    parser.add_argument("--db", default="shopping_assistant_eval")
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
    args = parser.parse_args()

    setup_database(args.db)

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

    catalog = load_catalog_into_db()
    create_tables(get_engine())
    allowed = allowed_prices(catalog)
    agent = ShoppingAgent(checkpointer=MemorySaver())
    judge_model = args.judge_model or LLM_MODEL

    commit = current_commit()
    results = []
    consecutive_errors = 0
    started = time.time()
    print(f"Chay {len(scenarios)} kich ban voi {LLM_MODEL} (DB: {args.db})\n")

    for sc in scenarios:
        for attempt in (1, 2):
            reset_state(catalog)
            session = f"eval-{sc['id']}-{uuid.uuid4().hex[:6]}"
            fails: list[str] = []
            answers: list[str] = []
            verdict = None
            try:
                for i, turn in enumerate(sc["turns"], start=1):
                    resp = agent.run(turn["user"], session)
                    had_pending = resp.pending_confirmation is not None
                    if had_pending and turn.get("confirm"):
                        resp = agent.confirm(session, turn["confirm"] == "approve")
                    answers.append(resp.answer_markdown or "")
                    calls, outputs = turn_tool_calls(agent, session)
                    fails += [f"turn {i}: {f}" for f in check_turn(turn, resp, calls, had_pending, allowed)]
                fails += [f"db: {f}" for f in check_db(sc.get("db") or {}, db_snapshot())]
                if args.judge and resp.intent != "blocked" and not resp.pending_confirmation:
                    verdict = judge(sc["turns"][-1]["user"], outputs, resp.answer_markdown, judge_model)
                consecutive_errors = 0
            except Exception as exc:
                transient = any(k in type(exc).__name__ for k in ("RateLimit", "InternalServer", "Quota"))
                if attempt == 1 and transient:
                    print(f"  ...  {sc['id']}: loi tam thoi ({type(exc).__name__}), cho 60s roi chay lai")
                    time.sleep(60)
                    continue
                consecutive_errors += 1
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
        results.append(
            {
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
        )
        mark = "PASS" if passed else "FAIL"
        extra = "" if verdict is None else f"  judge: grounded={verdict['grounded']} helpful={verdict['helpful']}"
        print(f"  {mark}  {sc['id']}{extra}")
        for f in fails:
            print(f"        - {f}")

        if consecutive_errors >= 3:
            print("\nDung som: 3 kich ban lien tiep loi (co the het quota API).")
            break
        time.sleep(args.sleep)

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
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "app"], cwd=ROOT, capture_output=True, text=True
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
        f"Code: `{commit}` · Model: `{model}` · Scenarios: {n} · Turns: {turns} · "
        f"Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        + ("" if rerun else f" ({seconds / 60:.0f} min)"),
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
