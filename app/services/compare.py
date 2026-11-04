"""
Compare service - so sanh san pham bang du lieu co cau truc, khong qua LLM.

Code lay thong so tu Postgres, dung bang so sanh va chi ra may hon o tung tieu chi.
LLM chi viet nhan xet dua tren bang, nen khong the doc sai hay bia thong so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from app.agent.schemas import ProductMetadata


def _vnd(v: int, lang: str = "vi") -> str:
    """9.490.000 ₫ (vi) / 9,490,000 ₫ (en)."""
    text = f"{v:,}"
    return (text if lang == "en" else text.replace(",", ".")) + " ₫"


def _storage(v: list[int]) -> str:
    return " / ".join(f"{s // 1024}TB" if s >= 1024 else f"{s}GB" for s in v)


@dataclass(frozen=True)
class Aspect:
    key: str
    label: str
    get: Callable[[ProductMetadata], object]
    fmt: Callable[[object], str]
    # "higher" / "lower": gia tri nao tot hon; None: khong cham diem (vd chip, camera MP)
    better: Optional[str] = None
    label_en: str = ""

    def name(self, lang: str) -> str:
        return self.label_en if lang == "en" and self.label_en else self.label


ASPECTS: list[Aspect] = [
    Aspect("price", "Giá", lambda p: p.price, _vnd, "lower", label_en="Price"),
    Aspect("chipset", "Chip", lambda p: p.chipset, str, label_en="Chip"),
    Aspect("ram", "RAM", lambda p: p.ram_gb, lambda v: f"{v} GB", "higher", label_en="RAM"),
    Aspect("storage", "Bộ nhớ", lambda p: p.storage_gb, _storage, "higher", label_en="Storage"),
    Aspect("screen", "Màn hình", lambda p: p.screen_inch, lambda v: f'{v}"', label_en="Screen"),
    Aspect("refresh_rate", "Tần số quét", lambda p: p.refresh_rate_hz, lambda v: f"{v} Hz", "higher", label_en="Refresh rate"),
    Aspect("battery", "Pin", lambda p: p.battery_mah, lambda v: f"{v} mAh", "higher", label_en="Battery"),
    Aspect("charging", "Sạc nhanh", lambda p: p.charging_w, lambda v: f"{v} W", "higher", label_en="Fast charging"),
    # Do phan giai cao khong dong nghia anh dep hon, nen khong cham diem camera
    Aspect("camera", "Camera chính", lambda p: p.main_camera_mp, lambda v: f"{v} MP", label_en="Main camera"),
    Aspect("weight", "Trọng lượng", lambda p: p.weight_g, lambda v: f"{v} g", "lower", label_en="Weight"),
    Aspect("os", "Hệ điều hành", lambda p: p.os, str, label_en="OS"),
    Aspect("release_year", "Năm ra mắt", lambda p: p.release_year, str, "higher", label_en="Release year"),
]
ASPECT_KEYS = [a.key for a in ASPECTS]


def _score(aspect: Aspect, value) -> float:
    """Gia tri de so: bo nho lay phien ban lon nhat."""
    return max(value) if isinstance(value, list) else float(value)


NOTES = {
    "vi": "✓ = tốt hơn ở tiêu chí đó. Chip, màn hình, camera và hệ điều hành không chấm điểm.",
    "en": "✓ = better on that spec. Chip, screen size, camera and OS are not scored.",
}


def build_comparison(
    products: list[ProductMetadata], aspects: Optional[list[str]] = None, lang: str = "vi"
) -> dict:
    """Dung bang so sanh Markdown va danh sach tieu chi moi may thang."""
    chosen = [a for a in ASPECTS if not aspects or a.key in aspects or a.key == "price"]
    wins: dict[str, list[str]] = {p.name: [] for p in products}

    first = "Spec" if lang == "en" else "Tiêu chí"
    header = f"| {first} | " + " | ".join(p.name for p in products) + " |"
    sep = "| --- |" + " --- |" * len(products)
    rows = [header, sep]

    for aspect in chosen:
        values = [aspect.get(p) for p in products]
        best_idx: set[int] = set()
        known = (
            [(i, _score(aspect, v)) for i, v in enumerate(values) if v is not None]
            if aspect.better
            else []
        )
        if len(known) >= 2:
            pick = max if aspect.better == "higher" else min
            best = pick(score for _, score in known)
            winners = {i for i, score in known if score == best}
            # Ca hai bang nhau thi khong ai thang
            if len(winners) < len(known):
                best_idx = winners
                for i in winners:
                    wins[products[i].name].append(aspect.name(lang))

        cells = []
        for i, v in enumerate(values):
            if v is None:
                cell = "—"
            elif aspect.key == "price":
                cell = _vnd(v, lang)
            else:
                cell = aspect.fmt(v)
            cells.append(f"**{cell}** ✓" if i in best_idx else cell)
        rows.append(f"| {aspect.name(lang)} | " + " | ".join(cells) + " |")

    return {
        "products": [p.name for p in products],
        "table_markdown": "\n".join(rows),
        "wins": wins,
        "note": NOTES.get(lang, NOTES["vi"]),
    }


def compare_products(product_ids: list[int], aspects: Optional[list[str]] = None, lang: str = "vi") -> dict:
    from app.services.product import get_products

    ids = list(dict.fromkeys(product_ids))
    if not 2 <= len(ids) <= 4:
        return {"error": "Can tu 2 den 4 product_id khac nhau de so sanh."}

    products = get_products(ids)
    missing = sorted(set(ids) - {p.id for p in products})
    if missing:
        return {"error": f"Khong tim thay san pham co ID: {missing}"}
    return build_comparison(products, aspects, lang)


# ------------------------------------------------------------------
# KIEM TRA SO LIEU TRONG CAU TRA LOI
# ------------------------------------------------------------------
# So dung rieng, khong dinh voi chu cai phia truoc (bo qua ten may nhu "S24", "A55")
_NUMBER = re.compile(r"(?<![A-Za-z\d])\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    """Tach so trong text, chuan hoa '31.990.000' -> '31990000', '6,8' -> '6.8',
    '31,99 trieu' -> '31990000'."""
    out: set[str] = set()
    for m in _NUMBER.finditer(text):
        raw = m.group()
        tail = text[m.end() : m.end() + 10].strip().lower()
        decimal = raw.replace(",", ".")
        if tail.startswith(("triệu", "trieu", "tr ", "million", "mil ")) and decimal.count(".") <= 1:
            out.add(str(int(round(float(decimal) * 1_000_000))))
        elif re.fullmatch(r"\d{1,3}([.,]\d{3})+", raw):
            out.add(re.sub(r"[.,]", "", raw))
        else:
            out.add(decimal)
    return out


def unsupported_numbers(answer: str, sources: list[str], min_value: float = 10) -> list[str]:
    """So trong cau tra loi (>= min_value) ma khong co trong du lieu tool tra ve."""
    known: set[str] = set()
    for s in sources:
        known |= _numbers(s)
    bad = []
    for n in sorted(_numbers(answer)):
        try:
            if float(n) < min_value:
                continue
        except ValueError:
            continue
        if n not in known:
            bad.append(n)
    return bad
