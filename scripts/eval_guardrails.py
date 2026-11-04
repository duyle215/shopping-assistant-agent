"""
Eval Guardrails - do lop chan input tren evals/injection.yaml.

  attack: cau tan cong (phai bi chan) · benign: cau binh thuong, ke ca cau "trong dang ngo"
  (khong duoc chan). Do regex (khong ton API) va, voi --llm, LLM guard + ca hai lop.

Chay:  python scripts/eval_guardrails.py [--llm] [--model gemini-3.5-flash-lite]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import yaml  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="evals/injection.yaml")
    parser.add_argument("--report", default="docs/guardrail_eval.md")
    parser.add_argument("--llm", action="store_true", help="Do them LLM guard (1 lan goi API moi cau)")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    from app.guardrails import check_input

    with open(args.data, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    items = [(t, "attack") for t in data["attack"]] + [(t, "benign") for t in data["benign"]]

    layers: dict[str, dict[str, bool]] = {"regex": {t: not check_input(t).passed for t, _ in items}}
    if args.llm:
        from app.config import GUARD_MODEL, LLM_MODEL
        from app.guardrails import classify_with_llm

        model = args.model or GUARD_MODEL or LLM_MODEL
        layers["llm"] = {}
        for t, _ in items:
            layers["llm"][t] = classify_with_llm(t, model).injection
            time.sleep(0.5)
        layers["regex + llm"] = {t: layers["regex"][t] or layers["llm"][t] for t, _ in items}

    n_attack = len(data["attack"])
    n_benign = len(data["benign"])
    lines = [
        "# Input guardrail evaluation",
        "",
        f"Data: [`evals/injection.yaml`](../evals/injection.yaml), {n_attack} attacks and {n_benign} "
        "benign messages (several look suspicious on purpose, e.g. \"bỏ qua cái máy vừa rồi\", "
        "\"system update\", \"developer mode\").",
        "",
        "| Layer | Attacks blocked | Benign blocked (false positives) |",
        "| --- | ---: | ---: |",
    ]
    for name, blocked in layers.items():
        a = sum(blocked[t] for t, k in items if k == "attack")
        b = sum(blocked[t] for t, k in items if k == "benign")
        lines.append(f"| {name} | {a}/{n_attack} = {a / n_attack:.0%} | {b}/{n_benign} |")
    lines += ["", "## Misses and false positives", "", "| Layer | Kind | Message |", "| --- | --- | --- |"]
    for name, blocked in layers.items():
        for t, kind in items:
            if (kind == "attack" and not blocked[t]) or (kind == "benign" and blocked[t]):
                lines.append(f"| {name} | {'missed attack' if kind == 'attack' else 'false positive'} | {t} |")

    report = "\n".join(lines) + "\n"
    print(report)
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(report)


if __name__ == "__main__":
    main()
