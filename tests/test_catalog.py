"""Lam sach HTML, chuan hoa va kiem tra hop le PhoneSpec."""

from __future__ import annotations

from app.catalog import PhoneSpec, clean_html, display_name, normalize, validate


def _spec(**overrides) -> PhoneSpec:
    base = dict(
        brand="samsung",
        model="Samsung Galaxy S24 Ultra",
        price_vnd=31_990_000,
        chipset="Qualcomm Snapdragon 8 Gen 3 for Galaxy",
        ram_gb=12,
        storage_gb=[512, 256, 1000],
        screen_inch=6.8,
        refresh_rate_hz=120,
        battery_mah=5000,
        charging_w=45,
        main_camera_mp=200,
        weight_g=232,
        os="Android",
        release_year=2024,
    )
    return PhoneSpec(**{**base, **overrides})


def test_clean_html_keeps_table_cells_and_drops_scripts():
    raw = (
        "<html><script>var x = 1;</script><h1>Galaxy &amp; S24</h1>"
        "<table><tr><td>RAM</td><td>12 GB</td></tr></table></html>"
    )
    text = clean_html(raw)
    assert "var x" not in text
    assert "Galaxy & S24" in text
    assert "RAM | 12 GB" in text


def test_normalize_brand_model_chip_and_storage():
    spec = normalize(_spec())
    assert spec.brand == "Samsung"
    assert spec.model == "Galaxy S24 Ultra"
    assert spec.chipset == "Snapdragon 8 Gen 3"
    assert spec.storage_gb == [256, 512, 1024]


def test_validate_accepts_normal_phone():
    assert validate(normalize(_spec())) == []


def test_validate_flags_out_of_range_values():
    problems = validate(_spec(price_vnd=31_990, battery_mah=50_000, storage_gb=[100]))
    assert any("price_vnd" in p for p in problems)
    assert any("battery_mah" in p for p in problems)
    assert any("storage_gb" in p for p in problems)


def test_validate_flags_apple_with_android():
    assert validate(_spec(brand="Apple", model="iPhone 15", os="Android"))


def test_display_name():
    assert display_name("Apple", "iPhone 15") == "iPhone 15"
    assert display_name("Samsung", "Galaxy S24") == "Samsung Galaxy S24"
