"""Bang so sanh dung bang code va kiem tra so lieu trong cau tra loi."""

from __future__ import annotations

from app.agent.schemas import ProductMetadata
from app.services.compare import build_comparison, unsupported_numbers


def _phone(pid: int, name: str, **overrides) -> ProductMetadata:
    base = dict(
        id=pid,
        name=name,
        brand="Brand",
        model=name,
        price=20_000_000,
        stock=5,
        chipset="Chip",
        ram_gb=8,
        storage_gb=[128, 256],
        screen_inch=6.5,
        refresh_rate_hz=120,
        battery_mah=5000,
        charging_w=45,
        main_camera_mp=50,
        weight_g=200,
        os="Android",
        release_year=2024,
    )
    return ProductMetadata(**{**base, **overrides})


def test_marks_winner_per_aspect():
    a = _phone(1, "Phone A", price=10_000_000, battery_mah=6000, weight_g=210)
    b = _phone(2, "Phone B", price=15_000_000, battery_mah=4000, weight_g=180, ram_gb=12)

    result = build_comparison([a, b])

    assert "Giá" in result["wins"]["Phone A"]
    assert "Pin" in result["wins"]["Phone A"]
    assert "Trọng lượng" in result["wins"]["Phone B"]
    assert "RAM" in result["wins"]["Phone B"]
    assert "| Pin | **6000 mAh** ✓ | 4000 mAh |" in result["table_markdown"]
    assert "10.000.000 ₫" in result["table_markdown"]


def test_ties_and_unscored_aspects_have_no_winner():
    a = _phone(1, "Phone A", main_camera_mp=200)
    b = _phone(2, "Phone B", main_camera_mp=48)

    result = build_comparison([a, b])

    for aspects in result["wins"].values():
        assert "Camera chính" not in aspects  # camera khong cham diem
        assert "Tần số quét" not in aspects  # bang nhau


def test_missing_value_shows_dash_and_is_skipped():
    a = _phone(1, "Phone A", charging_w=None)
    b = _phone(2, "Phone B", charging_w=25)

    result = build_comparison([a, b])

    assert "| Sạc nhanh | — | 25 W |" in result["table_markdown"]
    assert result["wins"]["Phone B"] == []


def test_aspect_filter_keeps_price():
    result = build_comparison([_phone(1, "A"), _phone(2, "B")], aspects=["battery"])
    lines = result["table_markdown"].splitlines()
    assert [ln.split("|")[1].strip() for ln in lines[2:]] == ["Giá", "Pin"]


def test_unsupported_numbers_accepts_numbers_from_table():
    table = "| Giá | 31.990.000 ₫ | 22.990.000 ₫ |\n| Pin | 5000 mAh | 4610 mAh |"
    answer = "S24 Ultra giá 31.990.000 ₫, pin 5000 mAh; máy kia 22,99 triệu và 4610 mAh."
    assert unsupported_numbers(answer, [table]) == []


def test_unsupported_numbers_flags_invented_numbers():
    table = "| Pin | 5000 mAh | 4610 mAh |"
    answer = "Pin 5000 mAh, hơn máy kia 390 mAh, sạc 120W."
    assert unsupported_numbers(answer, [table]) == ["120", "390"]


def test_english_table_labels():
    result = build_comparison([_phone(1, "A", battery_mah=6000), _phone(2, "B")], lang="en")
    assert result["table_markdown"].startswith("| Spec | A | B |")
    assert "| Battery | **6000 mAh** ✓ | 5000 mAh |" in result["table_markdown"]
    assert "Battery" in result["wins"]["A"]


def test_million_written_in_english_counts_as_the_price():
    table = "| Price | 22.990.000 ₫ |"
    assert unsupported_numbers("It costs 22.99 million VND.", [table]) == []
