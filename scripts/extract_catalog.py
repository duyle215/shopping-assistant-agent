"""
Extract Catalog - trang san pham tho (HTML) -> PhoneSpec co kieu.

    trang HTML -> lam sach text -> LLM Structured Outputs (PhoneSpec)
               -> chuan hoa (hang, chip, bo nho) -> kiem tra hop le -> data/catalog.jsonl

Chay (tu thu muc goc project):
    python scripts/extract_catalog.py                       # data/raw_pages -> data/catalog.jsonl
    python scripts/extract_catalog.py --pages data/crawled --out data/catalog_crawled.jsonl
    python scripts/extract_catalog.py --only 6 13           # chi chay lai vai trang

Sau do:  python scripts/eval_extraction.py   (do do chinh xac)
         python scripts/ingest_data.py       (nap vao Postgres + Qdrant)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.catalog import PhoneSpec, clean_html, normalize, validate  # noqa: E402
from app.config import LLM_MODEL, OPENAI_API_KEY, OPENAI_BASE_URL  # noqa: E402

SYSTEM_PROMPT = (
    "Ban la bo trich xuat thong so dien thoai tu trang ban hang tieng Viet.\n"
    "Chi dung thong tin co trong trang, khong dung kien thuc ben ngoai.\n"
    "- price_vnd: gia ban hien tai cua phien ban re nhat duoc rao (sau giam gia). "
    "Bo qua gia niem yet bi gach, tien tra gop, qua tang, tro gia.\n"
    "- Doi don vi: '28,99 trieu' -> 28990000; '5.000 mAh' -> 5000; '6,7 inch' -> 6.7; 1TB -> 1024.\n"
    "- storage_gb: liet ke moi phien ban bo nho trong duoc nhac den.\n"
    "- main_camera_mp: camera sau chinh, khong phai selfie.\n"
    "- Truong nao trang khong ghi va cho phep null thi tra null, khong doan."
)

MAX_PAGE_CHARS = 12_000


def page_id(filename: str, fallback: int) -> int:
    m = re.match(r"(\d+)", filename)
    return int(m.group(1)) if m else fallback


def extract_one(client: OpenAI, model: str, text: str, retries: int = 5) -> PhoneSpec:
    """Goi LLM voi JSON schema strict; thu lai khi bi gioi han toc do / loi tam thoi."""
    delay = 5.0
    for attempt in range(1, retries + 1):
        try:
            resp = client.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text[:MAX_PAGE_CHARS]},
                ],
                response_format=PhoneSpec,
                temperature=0,
            )
            parsed = resp.choices[0].message.parsed
            if parsed is None:
                raise ValueError("Model khong tra ve JSON hop le")
            return parsed
        except (RateLimitError, APIConnectionError) as exc:
            err: Exception = exc
        except APIStatusError as exc:
            if exc.status_code < 500:
                raise
            err = exc
        if attempt == retries:
            raise err
        print(f"    thu lai sau {delay:.0f}s ({type(err).__name__})")
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--pages", default="data/raw_pages", help="Thu muc chua file .html/.txt")
    parser.add_argument("--out", default="data/catalog.jsonl")
    parser.add_argument("--model", default=os.getenv("EXTRACT_MODEL") or LLM_MODEL)
    parser.add_argument("--only", type=int, nargs="*", help="Chi trich xuat cac id nay")
    parser.add_argument("--sleep", type=float, default=0.5, help="Nghi giua 2 lan goi (giay)")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Goi LLM toi da N trang lan nay (giu han muc API cho chatbot)",
    )
    args = parser.parse_args()

    files = sorted(f for f in os.listdir(args.pages) if f.endswith((".html", ".htm", ".txt")))
    if not files:
        sys.exit(f"Khong co trang nao trong {args.pages}")

    # Giu ket qua cu cua cac trang khong chay lai (khi dung --only)
    previous: dict[int, dict] = {}
    if args.only and os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            previous = {r["id"]: r for r in map(json.loads, f)}

    client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
    records: dict[int, dict] = dict(previous)
    ok = invalid = failed = 0
    started = time.time()

    print(f"Trich xuat {len(files)} trang bang {args.model}")
    for idx, fname in enumerate(files, start=1):
        pid = page_id(fname, idx)
        if args.only and pid not in args.only:
            continue
        if args.max_pages is not None and ok + invalid + failed >= args.max_pages:
            print(f"  Dung o --max-pages {args.max_pages}")
            break

        with open(os.path.join(args.pages, fname), encoding="utf-8") as f:
            text = clean_html(f.read())

        record = {
            "id": pid,
            "source": fname,
            "model": args.model,
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "text": text,
        }
        try:
            spec = normalize(extract_one(client, args.model, text))
            problems = validate(spec)
            record.update(spec=spec.model_dump(), problems=problems, valid=not problems)
            if problems:
                invalid += 1
                print(f"  [{pid:>3}] {fname}: KHONG HOP LE -> {problems}")
            else:
                ok += 1
                print(f"  [{pid:>3}] {fname}: {spec.brand} {spec.model}")
        except (ValidationError, ValueError, APIStatusError) as exc:
            failed += 1
            record.update(spec=None, problems=[f"{type(exc).__name__}: {exc}"[:300]], valid=False)
            print(f"  [{pid:>3}] {fname}: LOI -> {record['problems'][0]}")

        records[pid] = record
        time.sleep(args.sleep)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for pid in sorted(records):
            f.write(json.dumps(records[pid], ensure_ascii=False) + "\n")

    print(
        f"\nXong trong {time.time() - started:.0f}s: {ok} hop le, {invalid} khong hop le, "
        f"{failed} loi -> {args.out}"
    )


if __name__ == "__main__":
    main()
