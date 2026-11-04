"""
Eval Extraction - do do chinh xac trich xuat theo tung field.

So data/catalog.jsonl (ket qua LLM) voi data/gold_specs.json (dap an gan tay).
Mot field dung khi:
  - so nguyen / chuoi: bang nhau sau khi chuan hoa (chu thuong, bo dau cach va ky tu dac biet)
  - so thuc: lech khong qua 0.01
  - danh sach (storage_gb): cung tap gia tri
  - null: ca hai cung null

Chay:  python scripts/eval_extraction.py [--catalog data/catalog.jsonl] [--report docs/extraction_eval.md]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

FIELDS = [
    "brand",
    "model",
    "price_vnd",
    "chipset",
    "ram_gb",
    "storage_gb",
    "screen_inch",
    "refresh_rate_hz",
    "battery_mah",
    "charging_w",
    "main_camera_mp",
    "weight_g",
    "os",
    "release_year",
]


def _key(value: str) -> str:
    return re.sub(r"[^0-9a-z]", "", value.lower())


def field_matches(pred, gold) -> bool:
    if pred is None or gold is None:
        return pred is None and gold is None
    if isinstance(gold, list):
        return set(pred) == set(gold)
    if isinstance(gold, float) or isinstance(pred, float):
        return abs(float(pred) - float(gold)) <= 0.01
    if isinstance(gold, str):
        return _key(str(pred)) == _key(gold)
    return pred == gold


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--gold", default="data/gold_specs.json")
    parser.add_argument("--report", default="docs/extraction_eval.md")
    args = parser.parse_args()

    from app.catalog import PhoneSpec, normalize

    with open(args.gold, encoding="utf-8") as f:
        gold = {g["id"]: g for g in json.load(f)}
    with open(args.catalog, encoding="utf-8") as f:
        preds = {r["id"]: r for r in map(json.loads, f)}

    correct = {f: 0 for f in FIELDS}
    errors: list[tuple[int, str, object, object]] = []
    perfect = 0
    model_name = None

    for pid, g in sorted(gold.items()):
        rec = preds.get(pid)
        spec = (rec or {}).get("spec")
        model_name = model_name or (rec or {}).get("model")
        gold_spec = normalize(PhoneSpec(**{k: g[k] for k in FIELDS})).model_dump()
        all_ok = True
        for field in FIELDS:
            pred_value = spec.get(field) if spec else None
            if spec and field_matches(pred_value, gold_spec[field]):
                correct[field] += 1
            else:
                all_ok = False
                errors.append((pid, field, pred_value, gold_spec[field]))
        perfect += all_ok

    n = len(gold)
    total_fields = n * len(FIELDS)
    total_correct = sum(correct.values())

    lines = [
        "# Extraction accuracy",
        "",
        f"Model: `{model_name}` · Pages: {n} · Fields per page: {len(FIELDS)}",
        "",
        f"- **Field accuracy: {total_correct}/{total_fields} = {total_correct / total_fields:.1%}**",
        f"- Pages with every field correct: {perfect}/{n} = {perfect / n:.1%}",
        "",
        "| Field | Correct | Accuracy |",
        "| --- | ---: | ---: |",
    ]
    lines += [f"| `{f}` | {correct[f]}/{n} | {correct[f] / n:.0%} |" for f in FIELDS]
    lines += ["", "## Errors", ""]
    if errors:
        lines += ["| Page | Field | Extracted | Expected |", "| ---: | --- | --- | --- |"]
        lines += [f"| {pid} | `{f}` | {p} | {g} |" for pid, f, p, g in errors]
    else:
        lines.append("None.")
    report = "\n".join(lines) + "\n"

    print(report)
    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"-> {args.report}")


if __name__ == "__main__":
    main()
