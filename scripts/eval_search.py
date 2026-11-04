"""
Eval Search - so sanh tim theo nghia (dense), tu khoa (keyword) va hybrid (RRF).

Doc evals/search_queries.yaml (truy van + product_id dung), moi truy van embed mot lan,
roi do Hit@1, Hit@3 va MRR cho tung che do. Ghi docs/search_eval.md.

Chay:  python scripts/eval_search.py   (can da chay ingest_data.py)
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import yaml  # noqa: E402

from app.config import EMBED_MODEL  # noqa: E402
from app.services.search import _embed, dense_ids, keyword_ids, rrf  # noqa: E402

CACHE = ".cache/query_embeddings.json"


def embed_cached(query: str, cache: dict) -> list[float]:
    """Luu embedding truy van de chay lai khong ton quota API."""
    key = f"{EMBED_MODEL}|{query}"
    if key not in cache:
        cache[key] = _embed(query)
    return cache[key]

MODES = ("dense", "keyword", "hybrid")


def rank_of(ranking: list[int], expected: list[int]) -> int | None:
    for i, pid in enumerate(ranking, start=1):
        if pid in expected:
            return i
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", default="evals/search_queries.yaml")
    parser.add_argument("--report", default="docs/search_eval.md")
    args = parser.parse_args()

    with open(args.queries, encoding="utf-8") as f:
        groups = yaml.safe_load(f)

    import json

    cache: dict = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)

    results: dict[str, dict[str, list[int | None]]] = {}
    misses: list[str] = []
    for group, items in groups.items():
        results[group] = {m: [] for m in MODES}
        for item in items:
            q, expected = item["query"], item["expected"]
            dense = dense_ids(embed_cached(q, cache), 10)
            keyword = keyword_ids(q, 10)
            hybrid = [pid for pid, _ in rrf([dense, keyword])]
            for mode, ranking in zip(MODES, (dense, keyword, hybrid)):
                r = rank_of(ranking, expected)
                results[group][mode].append(r)
                if mode == "hybrid" and r != 1:
                    misses.append(f"| {group} | {q} | {expected} | {ranking[:3]} |")

    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)

    def metrics(ranks: list[int | None]) -> tuple[float, float, float]:
        n = len(ranks)
        hit1 = sum(1 for r in ranks if r == 1) / n
        hit3 = sum(1 for r in ranks if r and r <= 3) / n
        mrr = sum(1 / r for r in ranks if r) / n
        return hit1, hit3, mrr

    lines = [
        "# Search evaluation",
        "",
        f"Embedding model: `{EMBED_MODEL}` · Catalog: 30 phones · Queries: "
        + ", ".join(f"{len(v)} {k}" for k, v in groups.items()),
        "",
        "- **name**: the user types a model name, often shortened or lowercase (`ip 16`, `A55`, `redmi 13c`).",
        "- **need**: the user describes a feature mentioned in the product page (`camera Leica`, `màn hình gập`).",
        "",
        "| Queries | Mode | Hit@1 | Hit@3 | MRR |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for group in results:
        for mode in MODES:
            h1, h3, mrr = metrics(results[group][mode])
            lines.append(f"| {group} | {mode} | {h1:.0%} | {h3:.0%} | {mrr:.2f} |")
    lines += ["", "## Hybrid misses (expected product not ranked first)", ""]
    if misses:
        lines += ["| Queries | Query | Expected | Hybrid top 3 |", "| --- | --- | --- | --- |", *misses]
    else:
        lines.append("None.")
    report = "\n".join(lines) + "\n"
    print(report)
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"-> {args.report}")


if __name__ == "__main__":
    main()
