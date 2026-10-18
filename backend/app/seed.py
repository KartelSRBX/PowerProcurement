"""Synthetic demo data: invented suppliers and price lists. No real companies, prices or people.
Deterministic: the same call always produces the same rows.

    uv run python -m app.seed
"""

import hashlib
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import CatalogPrice, Supplier, SupplierDiscount

# (name, country, categories, languages, age, vat, deals, framework, pay_days, warranty, sanctioned, flags)
SUPPLIERS = [
    ("Dunav Elektronika d.o.o.", "RS", ["electronics"], ["sr", "en"], 14, True, 40, True, 30, 24, False, []),
    (
        "Beograd IT Distribucija d.o.o.",
        "RS",
        ["it_hardware"],
        ["sr", "en"],
        11,
        True,
        55,
        True,
        45,
        24,
        False,
        [],
    ),
    ("Novi Sad Komponente d.o.o.", "RS", ["electronics"], ["sr"], 5, True, 8, False, 15, 12, False, []),
    (
        "Balkan Office Trade d.o.o.",
        "RS",
        ["other", "it_hardware"],
        ["sr", "en"],
        8,
        True,
        12,
        False,
        30,
        12,
        False,
        [],
    ),
    (
        "Shenzhen Mega Components Ltd",
        "CN",
        ["electronics"],
        ["en"],
        6,
        False,
        3,
        False,
        0,
        6,
        False,
        [{"label": "unverified VAT/tax ID", "criterion": "reliability", "penalty": 10}],
    ),
    (
        "Guangzhou DigiParts Co",
        "CN",
        ["electronics", "it_hardware"],
        ["en"],
        9,
        False,
        6,
        False,
        0,
        12,
        False,
        [],
    ),
    ("Budapest Chip Supply Kft", "HU", ["electronics"], ["en"], 12, True, 18, True, 30, 24, False, []),
    ("Warszawa Hardware Sp. z o.o.", "PL", ["it_hardware"], ["en"], 15, True, 22, True, 30, 24, False, []),
    (
        "Istanbul Teknik Ticaret",
        "TR",
        ["electronics", "it_hardware"],
        ["en"],
        10,
        True,
        9,
        False,
        30,
        12,
        False,
        [{"label": "customs delays reported", "criterion": "external_risk", "penalty": 15}],
    ),
    ("Munich Bauteile GmbH", "DE", ["electronics"], ["en"], 25, True, 30, True, 30, 24, False, []),
    ("Vostok Parts Trading", "RU", ["electronics", "it_hardware"], ["en"], 4, True, 2, False, 0, 6, True, []),
    (
        "Zagreb Tech Grupa d.o.o.",
        "HR",
        ["it_hardware", "other"],
        ["sr", "en"],
        9,
        True,
        14,
        False,
        30,
        24,
        False,
        [],
    ),
]

# keyword (lowercase, matched against item text), description, category, base price in EUR
PRODUCTS = [
    ("stm32f407", "STM32F407VGT6 MCU", "electronics", 11.5),
    ("100nf", "100nF 0603 X7R capacitor", "electronics", 0.012),
    ("lm358dr", "LM358DR dual op-amp", "electronics", 0.28),
    ("esp32", "ESP32-WROOM-32E module", "electronics", 3.1),
    ("srd-05vdc", "Relay module 5V SRD-05VDC-SL-C", "electronics", 0.9),
    ("arduino uno", "Arduino Uno R3", "electronics", 22.0),
    ("kondenzat", "Capacitor 10uF 25V", "electronics", 0.05),
    ("otporni", "Resistor 10k 0805", "electronics", 0.01),
    ("raspberry pi 5", "Raspberry Pi 5 8GB", "electronics", 82.0),
    ("power supply", "Power supply 5V 5A", "electronics", 12.0),
    ("microsd", "microSD 128GB", "electronics", 14.0),
    ("latitude 5450", "Dell Latitude 5450 laptop", "it_hardware", 1150.0),
    ("docking", "Docking station", "it_hardware", 160.0),
    ("p2423d", "Dell P2423D monitor", "it_hardware", 245.0),
    ("hdmi", "HDMI cable 2 m", "it_hardware", 4.5),
    ("m404dn", "HP LaserJet Pro M404dn", "it_hardware", 330.0),
    ("cf259a", "HP CF259A toner", "it_hardware", 95.0),
    ("870 evo", "Samsung 870 EVO 1TB SSD", "it_hardware", 105.0),
    ("sata", "SATA cable", "it_hardware", 3.2),
    ("probook 450", "HP ProBook 450 G10", "it_hardware", 950.0),
    ("smart-ups", "APC Smart-UPS 1500VA", "it_hardware", 520.0),
    ("netzteil", "Power adapter 12V 5A", "electronics", 8.0),
    ("switch", "Cisco-class 24-port switch", "it_hardware", 640.0),
    ("chair", "Ergonomic office chair", "other", 140.0),
]

# keyword -> (brand, product type); only for the demo profiles
BRANDS = {
    "stm32f407": ("STMicroelectronics", "Microcontrollers"),
    "100nf": ("Murata", "Passive components"),
    "lm358dr": ("Texas Instruments", "Integrated circuits"),
    "esp32": ("Espressif", "Modules and boards"),
    "srd-05vdc": ("Songle", "Relays"),
    "arduino uno": ("Arduino", "Modules and boards"),
    "kondenzat": ("Panasonic", "Passive components"),
    "otporni": ("Yageo", "Passive components"),
    "raspberry pi 5": ("Raspberry Pi", "Modules and boards"),
    "power supply": ("Mean Well", "Power supplies"),
    "microsd": ("SanDisk", "Memory cards"),
    "latitude 5450": ("Dell", "Laptops"),
    "docking": ("Dell", "Accessories"),
    "p2423d": ("Dell", "Monitors"),
    "hdmi": ("Generic", "Cables"),
    "m404dn": ("HP", "Printers"),
    "cf259a": ("HP", "Printing supplies"),
    "870 evo": ("Samsung", "Storage"),
    "sata": ("Generic", "Cables"),
    "probook 450": ("HP", "Laptops"),
    "smart-ups": ("APC", "UPS"),
    "netzteil": ("Mean Well", "Power supplies"),
    "switch": ("Cisco", "Networking"),
    "chair": ("Ergo", "Furniture"),
}
TIER_ORDER = ("vendor", "distributor", "sub_distributor", "reseller")
PAYMENT_TYPES = ("prepayment", "on_delivery", "deferred", "credit")

LEAD_DAYS = {
    "RS": (3, 7),
    "HR": (4, 8),
    "DE": (6, 10),
    "PL": (6, 10),
    "HU": (6, 10),
    "TR": (10, 16),
    "CN": (18, 30),
    "RU": (14, 25),
}
CURRENCY = {"RS": "RSD", "CN": "USD"}


def _h(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)


def fill_profiles(session: Session) -> int:
    """Give demo suppliers a profile (brands, tiers, discounts) derived from their price lists.
    Only touches suppliers whose profile is still empty, so it is safe to run on every start."""
    done = 0
    for sup in session.scalars(select(Supplier).where(Supplier.partner_status.is_(None))):
        lines = list(session.scalars(select(CatalogPrice).where(CatalogPrice.supplier_id == sup.id)))
        if not lines or sup.brands:
            continue
        brands: list[str] = []
        types: list[str] = []
        for line in lines:
            brand, ptype = BRANDS.get(line.keyword, ("Other", "Other"))
            if brand not in brands:
                brands.append(brand)
            if ptype not in types:
                types.append(ptype)
        sup.brands = sorted(brands)
        sup.product_types = sorted(types)
        sup.brand_tiers = {b: TIER_ORDER[_h(sup.name, b, "tier") % 4] for b in sup.brands}
        sup.stock_delivery_days = min(line.lead_time_days for line in lines)
        sup.payment_type = PAYMENT_TYPES[_h(sup.name, "pay") % 4]
        sup.has_credit_line = sup.framework_contract and _h(sup.name, "credit") % 2 == 0
        sup.credit_line_note = "limit agreed in the framework contract" if sup.has_credit_line else None
        sup.contract_note = "framework contract signed" if sup.framework_contract else None
        sup.partner_status = (
            "preferred" if sup.deals_count >= 20 else "new" if sup.age_years < 3 else "approved"
        )
        sup.website = f"https://www.{sup.name.lower().split()[0]}.example"
        for b in sup.brands:
            if _h(sup.name, b, "disc") % 2 == 0:
                pct = 3 + _h(sup.name, b, "pct") % 8
                session.add(SupplierDiscount(supplier_id=sup.id, brand=b, description=f"{pct}% from 100 pcs"))
        done += 1
    session.commit()
    return done


def seed(session: Session, settings: Settings, today: date | None = None) -> int:
    """Insert suppliers and price lists once. Returns the number of suppliers inserted."""
    if session.scalar(select(Supplier.id).limit(1)) is not None:
        fill_profiles(session)
        return 0
    today = today or date.today()
    for name, country, cats, langs, age, vat, deals, fw, pay, war, sanc, flags in SUPPLIERS:
        slug = name.lower().split()[0]
        sup = Supplier(
            name=name,
            country=country,
            email=f"sales@{slug}.example",
            categories=cats,
            languages=langs,
            age_years=age,
            vat_verified=vat,
            deals_count=deals,
            framework_contract=fw,
            payment_terms_days=pay,
            warranty_months=war,
            sanctioned=sanc,
            flags=flags,
        )
        session.add(sup)
        session.flush()
        currency = CURRENCY.get(country, "EUR")
        rate = {"EUR": 1.0, "RSD": settings.fx_rsd_per_eur, "USD": settings.fx_usd_per_eur}[currency]
        for keyword, desc, cat, base in PRODUCTS:
            if cat not in cats or _h(name, keyword) % 10 >= 8:
                continue
            factor = 0.90 + (_h(name, keyword, "price") % 26) / 100  # 0.90 .. 1.15
            lo, hi = LEAD_DAYS[country]
            session.add(
                CatalogPrice(
                    supplier_id=sup.id,
                    keyword=keyword,
                    description=desc,
                    unit_price=round(base * factor * rate, 4),
                    currency=currency,
                    moq=1 if base > 20 else 100 if country == "CN" else 10,
                    lead_time_days=lo + _h(name, keyword, "lead") % (hi - lo + 1),
                    valid_until=today + timedelta(days=90),
                )
            )
    session.commit()
    fill_profiles(session)
    return len(SUPPLIERS)


def main() -> int:
    from app.config import get_settings
    from app.db import get_session

    n = seed(next(get_session()), get_settings())
    print(f"seeded {n} suppliers" if n else "already seeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
