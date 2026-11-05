# ruff: noqa: E501
"""Draft checklists for two regulations that touch EU-Serbia trade: the EU carbon border adjustment
mechanism (CBAM) and Serbian electronic invoicing (SEF).

Every line is DRAFT. Each one names the page it came from, whether that page is a primary source (the law, a
government or EU page) or a secondary one (a law firm, a consultancy, a news site), a short passage copied from
it, and the day the page was read. A date that does not come from a primary source says so on the line. Where
the pages read do not say something, the line says "not found" and asks a person to check; nothing is filled in
from memory. This is a reading aid for a buyer, not legal advice: the sources in the lines are what to check
against before relying on a date.

Pages read on CHECKED_ON. The EUR-Lex pages of the regulations gave only their metadata, not the articles, so
CBAM statements rest on two law-firm and consultancy pages. The Serbian law and rulebook texts are PDF
attachments that were not opened; their gazette numbers and titles come from efaktura.gov.rs."""

CHECKED_ON = "2026-11-05"

PWC = "https://www.pwc.com/mt/en/publications/tax-legal/regulation-eu-2025-2083-simplifying-the-carbon-border-adjustment-mechanism-cbam.html"
REED = "https://www.reedsmith.com/our-insights/blogs/viewpoints/102lr9t/what-you-need-to-know-as-cbam-simplification-comes-into-effect/"
EURLEX = "https://eur-lex.europa.eu/eli/reg/2025/2083/oj"
LAW_2025 = "https://www.efaktura.gov.rs/tekst/9490/zakon-o-elektronskom-fakturisanju-04122025.php"
LAW_2026 = "https://www.efaktura.gov.rs/tekst/11017/zakon-o-izmenama-i-dopunama-zakona-o-elektronskom-fakturisanju-31082026.php"
RULE_MAR = "https://www.efaktura.gov.rs/tekst/10123/pravilnik-o-izmenama-i-dopunama-pef-27032026.php"
RULE_AUG = "https://www.efaktura.gov.rs/tekst/10837/pravilnik-o-izmenama-i-dopunama-pef-01082026.php"
KPMG_LAW = "https://kpmg.com/us/en/taxnewsflash/news/2025/12/serbia-amendments-e-invoicing-law.html"
KPMG_APR = "https://kpmg.com/us/en/taxnewsflash/news/2026/04/serbia-rulebook-e-invoicing-amended.html"
KPMG_AUG = "https://kpmg.com/us/en/taxnewsflash/news/2026/08/serbia-amendments-e-invoicing-rulebook.html"
FISCAL = "https://www.fiscal-requirements.com/news/4560-serbia-has-postponed-the-sef-b2b-e-invoicing-reforms-until-the-end-of-2026"
EFAKTURA = "https://www.efaktura.gov.rs/"


def _i(key, area, title, detail, source, kind, quote, date=None, date_basis="none", ask=None):
    """date_basis: primary (the date is in a primary source) | secondary (only in a secondary source) |
    inferred (worked out from a rule, not stated) | none (no date on this line)."""
    return {
        "key": key, "area": area, "title": title, "detail": detail, "date": date, "date_basis": date_basis,
        "source_url": source, "source_kind": kind, "quote": quote, "checked_on": CHECKED_ON,
        "status": "draft", "ask": ask,
    }  # fmt: skip


ITEMS = [
    # ---- CBAM ----
    _i(
        "cbam-law",
        "cbam",
        "The rules in force are Regulation (EU) 2023/956 as amended by Regulation (EU) 2025/2083",
        "Check that your adviser works from the amended text; the articles themselves were not readable on EUR-Lex when this list was drafted.",
        EURLEX,
        "primary",
        "meta-eli:date_document 2025-10-08; meta-eli:first_date_entry_in_force 2025-10-20 (page metadata)",
        "2025-10-20",
        "primary",
    ),
    _i(
        "cbam-scope",
        "cbam",
        "Do you buy or import goods in CBAM scope?",
        "Cement, fertilisers, iron and steel, aluminium; electricity and hydrogen are also covered but are not helped by the 50 tonne threshold. Match your articles and tariff codes against Annex I of the Regulation.",
        PWC,
        "secondary",
        "Importers whose total annual imports of CBAM goods (iron and steel, aluminium, fertilisers, and cement) do not exceed 50 tonnes are exempt",
        ask="The full goods list in Annex I (the primary text) was not read: check your tariff codes against it.",
    ),
    _i(
        "cbam-definitive",
        "cbam",
        "The definitive period (certificates and surrender) started on 1 January 2026",
        "From that date importers must buy and surrender CBAM certificates for goods imported.",
        REED,
        "secondary",
        "The definitive regime, under which importers must purchase and surrender CBAM certificates, will start on January 1, 2026.",
        "2026-01-01",
        "secondary",
    ),
    _i(
        "cbam-threshold",
        "cbam",
        "The 50 tonne yearly threshold per importer",
        "Under 50 tonnes of CBAM goods a year (not electricity or hydrogen) there are no CBAM obligations. If the importer goes over 50 tonnes at any point in the year, all imports of that year are covered.",
        REED,
        "secondary",
        "If an importer exceeds the 50-tonne threshold at any point during the year, all imports for that year become subject to CBAM obligations.",
        ask="Who is the importer of record: you, your EU customer, or a customs agent? The threshold is per importer.",
    ),
    _i(
        "cbam-declarant",
        "cbam",
        "Authorised CBAM declarant status",
        "An importer established in a Member State has to apply for the status before importing; an application filed by 31 March 2026 allows imports to continue while the decision is pending.",
        PWC,
        "secondary",
        "Importers and indirect customs representatives who submit an application for authorisation by 31 March 2026 may continue importing goods in 2026",
        "2026-03-31",
        "secondary",
        ask="Whether this applies to you depends on who imports into the EU. Ask your EU importer or customs agent.",
    ),
    _i(
        "cbam-emissions",
        "cbam",
        "Emissions data from the supplier",
        "The importer needs the embedded emissions of each product. The drafting source named it as a requirement; the pages read for this list do not give the rule.",
        "https://www.coolset.com/academy/cbam-timeline-deadlines-phases-what-to-expect-2026",
        "secondary",
        "(cited in the 30-day plan document; this page was not fetched when the list was drafted)",
        ask="Not found in the pages read: ask what emissions data the supplier can give and in what format.",
    ),
    _i(
        "cbam-declaration",
        "cbam",
        "Annual CBAM declaration and surrender of certificates",
        "Both sources read say the annual declaration and the surrender are due by 30 September of the following year, which for goods imported in 2026 would be 30 September 2027. That date is worked out from the rule, no page states it for 2026, and earlier sources gave 31 May 2027 (the old deadline).",
        PWC,
        "secondary",
        "Authorised CBAM declarants must submit annual declarations by 30 September for the previous year.",
        "2027-09-30",
        "inferred",
        ask="Confirm the first deadline against Regulation (EU) 2025/2083 or the Commission's CBAM page.",
    ),
    _i(
        "cbam-sales",
        "cbam",
        "Certificate sales start in February 2027",
        "Certificates are bought through a central platform; those bought in 2027 are priced on the average 2026 EU ETS allowance price. Authorised declarants must hold at least 50% of the embedded emissions of goods imported since the start of the year (from 2027).",
        REED,
        "secondary",
        "Sales of CBAM certificates through the EU's central platform will now begin in February 2027",
        "2027-02",
        "secondary",
    ),
    # ---- Serbia: e-invoicing (SEF) ----
    _i(
        "sef-b2b",
        "rs_sef",
        "B2B invoices between VAT payers go through the SEF system",
        "Serbia has required B2B e-invoicing in the SEF system since 1 January 2023 (B2G earlier, in 2022).",
        FISCAL,
        "secondary",
        "Serbia has required B2B e-invoicing through the Sistem E-Faktura (SEF) since 1 January 2023",
        "2023-01-01",
        "secondary",
        ask="The Ministry of Finance page with the original date was not found: check it on efaktura.gov.rs.",
    ),
    _i(
        "sef-law-2025",
        "rs_sef",
        "Law amendments of December 2025 (Službeni glasnik RS 109/2025)",
        "Published on 4 December 2025 (efaktura.gov.rs). A consultancy reports they took effect on 12 December 2025 and apply to tax periods starting after 31 March 2026, with the preliminary VAT return provisions applying from entry into force. They concern e-invoices for retail supply, the system, and preliminary VAT returns.",
        LAW_2025,
        "primary",
        "...109 од 4. децембра 2025.",
        "2025-12-04",
        "primary",
        ask="The in-force and application dates (12 Dec 2025; periods after 31 Mar 2026) are from KPMG, not from the law text.",
    ),
    _i(
        "sef-law-2026",
        "rs_sef",
        "A further amending law (Službeni glasnik RS 80/2026)",
        "efaktura.gov.rs lists it under 31 August 2026. Its content, adoption and entry into force were not in the page text (the law is a PDF).",
        LAW_2026,
        "primary",
        'Закон о изменама и допунама Закона о електронском фактурисању ("Службени гласник РС", број 80/2026)',
        "2026-08-31",
        "primary",
        ask="Not read: open the PDF and note what changed.",
    ),
    _i(
        "sef-rulebook-mar",
        "rs_sef",
        "Rulebook amendment of 27 March 2026 (Službeni glasnik RS 30/2026-23)",
        "A consultancy reports it applies to tax periods from 1 April 2026: an e-invoice is needed when an advance payment is received on the day of supply; tax category N (annulment) shows negative amounts; electronic recording of VAT is mandatory when no e-invoice was issued for retail supply.",
        RULE_MAR,
        "primary",
        'Правилник о изменама и допунама Правилника о електронском фактурисању ("Службени гласник РС", бр. 30/2026-23)',
        "2026-03-27",
        "primary",
        ask="The content and the 1 April 2026 date are from KPMG ("
        + KPMG_APR
        + "), not from the rulebook text.",
    ),
    _i(
        "sef-rulebook-aug",
        "rs_sef",
        "Rulebook amendment of 1 August 2026 (Službeni glasnik RS 71/2026)",
        "A consultancy reports it took effect on 1 August 2026, except the preliminary VAT return in SEF, which applies to tax periods beginning after 31 December 2026.",
        RULE_AUG,
        "primary",
        'Правилник о изменама и допунама Правилника о електронском фактурисању ("Службени гласник РС", бр. 71/2026)',
        "2026-08-01",
        "primary",
        ask="The effective dates are from KPMG ("
        + KPMG_AUG
        + "), not from the rulebook text. The preliminary VAT return date (after 31 Dec 2026) is secondary.",
    ),
    _i(
        "sef-format",
        "rs_sef",
        "Invoice format: UBL 2.1 with the Serbian customisation of EN 16931-1",
        "efaktura.gov.rs publishes the customised specification, XML examples in UBL 2.1 and the VAT categories for e-invoices. Your accounting software or intermediary must produce that format.",
        EFAKTURA,
        "primary",
        "Ажурирана спецификација прилагођене примене стандарда EN 16931-1 за електронске фактуре у унутрашњем промету у Републици Србији",
        ask="The mandatory fields and VAT category codes were not read: take them from the published specification.",
    ),
    _i(
        "sef-foreign",
        "rs_sef",
        "Foreign suppliers and imports",
        "Whether invoices from foreign suppliers, or imports, go through SEF was not found in the pages read. Do not assume either way.",
        FISCAL,
        "secondary",
        "(no statement found; a news item mentions new import VAT reporting obligations added in 2025)",
        ask="Ask your accountant how invoices from EU suppliers and import VAT are handled.",
    ),
    _i(
        "sef-deadlines",
        "rs_sef",
        "Deadlines to approve or reject an incoming invoice in SEF",
        "No number of days was found in the pages read. One news item says the input VAT declaration deadline was extended from 10 to 12 days after the invoice date; this was not confirmed in a primary source.",
        FISCAL,
        "secondary",
        "Input VAT declaration deadline extended from 10 to 12 days after the invoice date.",
        ask="Not confirmed: check the law and rulebook for the approval and rejection periods.",
    ),
]

AREAS = {
    "cbam": "EU carbon border adjustment mechanism (CBAM)",
    "rs_sef": "Serbian electronic invoicing (SEF)",
}
STATES = ("todo", "done", "not_applicable")
BASES = ("primary", "secondary", "inferred", "none")
