from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Who made a change. The plan requires every price change to record one of these.
ACTORS = ("system", "human", "client")


class AuditLog(Base):
    """Append-only record of decisions and changes (approvals, price changes, outcomes)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


REQUEST_STATUSES = ("needs_review", "parsed", "not_request", "confirmed")


class CustomerRequest(Base):
    """One incoming email and what the model made of it (step 1)."""

    __tablename__ = "customer_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    sender: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    parsed: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(128))


# ---- Suppliers, prices, and the rest of the pipeline (synthetic data in the demo) ----


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    languages: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    age_years: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    deals_count: Mapped[int] = mapped_column(Integer, nullable=False)
    framework_contract: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False)
    warranty_months: Mapped[int] = mapped_column(Integer, nullable=False)
    sanctioned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Manual flags set by a person: label, criterion (reliability or external_risk), penalty points
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    # Profile (filled by people or an import; every field is optional)
    brands: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    product_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    # brand -> vendor | distributor | sub_distributor | reseller
    brand_tiers: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    stock_delivery_days: Mapped[int | None] = mapped_column(Integer)
    payment_type: Mapped[str | None] = mapped_column(
        String(32)
    )  # prepayment | on_delivery | deferred | credit
    contract_note: Mapped[str | None] = mapped_column(String(300))
    has_credit_line: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    credit_line_note: Mapped[str | None] = mapped_column(String(300))
    rebates: Mapped[str | None] = mapped_column(String(300))
    partner_status: Mapped[str | None] = mapped_column(String(16))  # new | approved | preferred | on_hold
    website: Mapped[str | None] = mapped_column(String(300))


class CatalogPrice(Base):
    """A supplier's price list line. In the demo it doubles as the price source."""

    __tablename__ = "catalog_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)  # lowercase, matched in item text
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    moq: Mapped[int] = mapped_column(Integer, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="synthetic-catalog")


class RequestItem(Base):
    __tablename__ = "request_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("customer_requests.id"), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    part_number: Mapped[str | None] = mapped_column(String(100))
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32))


class ShortlistEntry(Base):
    __tablename__ = "shortlist"
    __table_args__ = (UniqueConstraint("request_id", "supplier_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("customer_requests.id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    covered_items: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)


class MarketPrice(Base):
    """One price observation for one item. Always carries its source, time, currency, MOQ and validity."""

    __tablename__ = "market_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_item_id: Mapped[int] = mapped_column(ForeignKey("request_items.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    moq: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Rfq(Base):
    """A letter to one supplier. Nothing is sent until a named person approves it."""

    __tablename__ = "rfqs"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("customer_requests.id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    decided_by: Mapped[str | None] = mapped_column(String(128))
    sent_to: Mapped[str | None] = mapped_column(String(32))
    drafted_by: Mapped[str] = mapped_column(
        String(120), nullable=False, default="template", server_default="template"
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Offer(Base):
    """A supplier's answer, entered as structured data (extraction by AI comes later)."""

    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("customer_requests.id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    covers_all_items: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    moq_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # "manual" | "demo-simulator"
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerQuote(Base):
    __tablename__ = "customer_quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("customer_requests.id"), nullable=False)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), nullable=False)
    cost_eur: Mapped[float] = mapped_column(Float, nullable=False)
    markup: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    decided_by: Mapped[str | None] = mapped_column(String(128))
    sent_to: Mapped[str | None] = mapped_column(String(32))
    drafted_by: Mapped[str] = mapped_column(
        String(120), nullable=False, default="template", server_default="template"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceEvent(Base):
    """Every price that appears in a deal, with who set it: system, human or client."""

    __tablename__ = "price_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("customer_requests.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128))


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("customer_quotes.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # accepted|counter|rejected|silence
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(3))
    reason: Mapped[str | None] = mapped_column(String(500))
    confirmed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("customer_requests.id"), nullable=False)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    total_eur: Mapped[float] = mapped_column(Float, nullable=False)
    budget_checks: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="sent")
    approved_by: Mapped[str] = mapped_column(String(128), nullable=False)
    invoice_requested_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InboxEmail(Base):
    """A raw inbound email as it arrived, before (or without) AI parsing. Linked to a request
    by message_id once one exists."""

    __tablename__ = "inbox_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    sender: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # imap | eml | demo


class QuoteHistory(Base):
    """One past customer quote with its outcome, for markup analytics. Rows come from a synthetic
    generator or an import; quotes made in this system are read from customer_quotes/outcomes."""

    __tablename__ = "quote_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer: Mapped[str] = mapped_column(String(320), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    cost_eur: Mapped[float] = mapped_column(Float, nullable=False)
    markup: Mapped[float] = mapped_column(Float, nullable=False)
    price_eur: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)  # accepted|counter|rejected|silence
    counter_price_eur: Mapped[float | None] = mapped_column(Float)
    quoted_at: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # synthetic | import


class AppSetting(Base):
    """A setting saved from the Settings tab. Secret values are stored encrypted."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FxRate(Base):
    """One fetched exchange-rate snapshot (units per 1 EUR), kept so a past quote can be explained."""

    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # nbs
    rsd_per_eur: Mapped[float] = mapped_column(Float, nullable=False)
    usd_per_eur: Mapped[float] = mapped_column(Float, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SupplierDiscount(Base):
    """A discount a supplier gives on one brand, in words (for example "5% from 100 pcs")."""

    __tablename__ = "supplier_discounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)


class SupplierCheck(Base):
    """One due-diligence check of a supplier. The newest one is the supplier's current status."""

    __tablename__ = "supplier_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)  # working | not_working | under_review
    checked_by: Mapped[str] = mapped_column(String(128), nullable=False)
    contact_details: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(String(500))
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VaultEntry(Base):
    """A login for a supplier portal or another resource. Login and password are stored encrypted."""

    __tablename__ = "vault_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    site_url: Mapped[str | None] = mapped_column(String(300))
    login_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    comments: Mapped[str | None] = mapped_column(String(500))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VaultRequest(Base):
    """A request to see one entry's login and password. A second person approves it; it can be used once."""

    __tablename__ = "vault_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("vault_entries.id"), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(128))
    decision_comment: Mapped[str | None] = mapped_column(String(300))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VaultLog(Base):
    """Append-only: who opened the vault, saw a secret, added, changed or removed an entry."""

    __tablename__ = "vault_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[str] = mapped_column(String(24), nullable=False)
    person: Mapped[str] = mapped_column(String(128), nullable=False)
    entry_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(String(300))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SupplierReply(Base):
    """A supplier's answer as text, what was read from it, and the offer a person confirmed from it."""

    __tablename__ = "supplier_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("customer_requests.id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    extracted: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    missing: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    read_by: Mapped[str] = mapped_column(String(120), nullable=False)  # model name or "manual"
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="extracted"
    )  # extracted|confirmed
    entered_by: Mapped[str] = mapped_column(String(128), nullable=False)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Letter(Base):
    """Any other outgoing letter (follow-up or delivery question to a supplier, reminder or order
    confirmation to a customer). Same rule as
    every letter: nothing is sent until a named person approves it."""

    __tablename__ = "letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("customer_requests.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # followup|reminder|confirmation|delivery
    order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    drafted_by: Mapped[str] = mapped_column(String(120), nullable=False, default="template")
    decided_by: Mapped[str | None] = mapped_column(String(128))
    sent_to: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
