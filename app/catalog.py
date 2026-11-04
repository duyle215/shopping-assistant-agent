"""
Catalog schema - PhoneSpec la "hop dong" giua LLM trich xuat va database.

LLM chi dien PhoneSpec (Structured Outputs, JSON schema strict). Sau do code
chuan hoa va kiem tra hop le truoc khi luu, nen du lieu trong DB luon co kieu ro rang.
"""

from __future__ import annotations

import html
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PhoneSpec(BaseModel):
    """Thong so mot dien thoai, trich tu trang san pham."""

    brand: str = Field(description="Hang san xuat, vd Apple, Samsung, Xiaomi, OPPO")
    model: str = Field(
        description="Ten model, khong lap lai ten hang, khong ghi dung luong/mau. "
        "Vd 'iPhone 15 Pro Max', 'Galaxy S24 Ultra', 'Redmi Note 13'"
    )
    price_vnd: int = Field(
        description="Gia ban hien tai bang VND (gia sau giam neu co, khong phai gia "
        "niem yet hay tien tra gop/qua tang). Vd '28,99 trieu' -> 28990000"
    )
    chipset: str = Field(description="Ten chip, vd 'Snapdragon 8 Gen 3', 'A17 Pro'")
    ram_gb: int = Field(description="RAM that (GB), khong tinh RAM ao/mo rong")
    storage_gb: list[int] = Field(
        description="Tat ca phien ban bo nho trong (GB), 1TB = 1024. Khong tinh the nho"
    )
    screen_inch: float = Field(description="Kich thuoc man hinh chinh (inch)")
    refresh_rate_hz: int = Field(description="Tan so quet toi da cua man hinh chinh (Hz)")
    battery_mah: int = Field(description="Dung luong pin (mAh)")
    charging_w: Optional[int] = Field(
        description="Cong suat sac co day toi da (W); null neu trang khong ghi"
    )
    main_camera_mp: int = Field(description="Do phan giai camera sau chinh (MP)")
    weight_g: Optional[int] = Field(description="Trong luong (gram); null neu khong ghi")
    os: Literal["iOS", "Android"]
    release_year: Optional[int] = Field(description="Nam ra mat; null neu khong ghi")


# ------------------------------------------------------------------
# LAM SACH TEXT
# ------------------------------------------------------------------
def clean_html(raw: str) -> str:
    """HTML -> text: bo script/style, giu xuong dong theo block, gop khoang trang."""
    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d|dt|dd|table|ul|dl)>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", " | ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip(" |") for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


# ------------------------------------------------------------------
# CHUAN HOA
# ------------------------------------------------------------------
BRAND_CANONICAL: dict[str, str] = {
    "apple": "Apple",
    "samsung": "Samsung",
    "xiaomi": "Xiaomi",
    "redmi": "Xiaomi",
    "poco": "Xiaomi",
    "oppo": "OPPO",
    "vivo": "vivo",
    "google": "Google",
    "realme": "realme",
    "honor": "Honor",
    "nothing": "Nothing",
    "asus": "ASUS",
}

_CHIP_VENDORS = ("qualcomm", "mediatek", "apple", "google", "samsung", "hisilicon", "unisoc")
_CHIP_SUFFIXES = (" for galaxy",)


def normalize_brand(raw: str) -> str:
    key = raw.strip().lower()
    return BRAND_CANONICAL.get(key, raw.strip())


def normalize_chipset(raw: str) -> str:
    chip = re.sub(r"\(.*?\)", "", raw).strip()
    lower = chip.lower()
    for vendor in _CHIP_VENDORS:
        if lower.startswith(vendor + " "):
            chip = chip[len(vendor) + 1 :]
            lower = chip.lower()
    for suffix in _CHIP_SUFFIXES:
        if lower.endswith(suffix):
            chip = chip[: -len(suffix)]
    return re.sub(r"\s+", " ", chip).strip()


def normalize_model(brand: str, model: str) -> str:
    """Bo ten hang o dau model ('Samsung Galaxy S24' -> 'Galaxy S24')."""
    m = re.sub(r"\s+", " ", model).strip()
    if m.lower().startswith(brand.lower() + " "):
        m = m[len(brand) + 1 :]
    return m


def normalize(spec: PhoneSpec) -> PhoneSpec:
    brand = normalize_brand(spec.brand)
    # Mot so model ghi 1TB thanh 1000GB
    storage = sorted({1024 if s == 1000 else s for s in spec.storage_gb})
    return spec.model_copy(
        update={
            "brand": brand,
            "model": normalize_model(brand, spec.model),
            "chipset": normalize_chipset(spec.chipset),
            "storage_gb": storage,
            "screen_inch": round(spec.screen_inch, 2),
        }
    )


# ------------------------------------------------------------------
# KIEM TRA HOP LE
# ------------------------------------------------------------------
_RANGES: dict[str, tuple[float, float]] = {
    "price_vnd": (500_000, 100_000_000),
    "ram_gb": (1, 24),
    "screen_inch": (4.0, 8.5),
    "refresh_rate_hz": (60, 240),
    "battery_mah": (1500, 8000),
    "charging_w": (5, 250),
    "main_camera_mp": (2, 250),
    "weight_g": (100, 350),
    "release_year": (2015, 2030),
}
_STORAGE_OPTIONS = {16, 32, 64, 128, 256, 512, 1024, 2048}


def validate(spec: PhoneSpec) -> list[str]:
    """Tra ve danh sach loi; rong = hop le."""
    problems: list[str] = []
    for field, (lo, hi) in _RANGES.items():
        value = getattr(spec, field)
        if value is not None and not lo <= value <= hi:
            problems.append(f"{field}={value} ngoai khoang [{lo}, {hi}]")
    if not spec.storage_gb:
        problems.append("storage_gb rong")
    bad = [s for s in spec.storage_gb if s not in _STORAGE_OPTIONS]
    if bad:
        problems.append(f"storage_gb co gia tri la: {bad}")
    if not spec.model.strip():
        problems.append("model rong")
    if spec.brand == "Apple" and spec.os != "iOS":
        problems.append("Apple nhung os khac iOS")
    return problems


def display_name(brand: str, model: str) -> str:
    """Ten hien thi: 'Apple iPhone 15' -> 'iPhone 15', con lai 'Samsung Galaxy S24'."""
    if brand == "Apple":
        return model
    return f"{brand} {model}"
