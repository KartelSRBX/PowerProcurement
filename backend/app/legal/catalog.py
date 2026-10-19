"""The list of legal acts the review can cite. Only names and where to get the text live here: the texts
themselves are downloaded by the loader (or uploaded by a person) into the database, never stored in git.

EU entries carry a CELEX number, so the loader can fetch them; the 27 EU numbers were checked against the
text EUR-Lex returned (2026-10-19). CISG, the New York Convention and the UNIDROIT Principles are fetched from
their publishers' PDFs. For Serbia, China and the UAE the names and numbers were written from memory and are
marked `check`: confirm them when the text is imported."""

# ruff: noqa: E501
from typing import Any

EUR = "eurlex"


def _eu(key: str, celex: str, short: str, title: str, kind: str, topics: list[str]) -> dict[str, Any]:
    return {
        "key": key,
        "jurisdiction": "EU",
        "kind": kind,
        "title": title,
        "short": short,
        "ref": celex,
        "topics": topics,
        "fetch": EUR,
        "note": "",
    }


def _other(
    key: str, juris: str, kind: str, title: str, short: str, topics: list[str], url: str | None = None
) -> dict[str, Any]:
    return {
        "key": key,
        "jurisdiction": juris,
        "kind": kind,
        "title": title,
        "short": short,
        "ref": None,
        "topics": topics,
        "fetch": "url" if url else "manual",
        "source_url": url,
        "note": "" if url else "Upload the official or translated text (HTML, PDF or plain text).",
    }


CATALOG: list[dict[str, Any]] = [
    # --- EU: sale of goods, payment, contract law ---
    _eu(
        "eu-2011-7",
        "32011L0007",
        "Late Payment Directive",
        "Directive 2011/7/EU on combating late payment in commercial transactions",
        "directive",
        ["payment", "interest", "b2b"],
    ),
    _eu(
        "eu-2019-771",
        "32019L0771",
        "Sale of Goods Directive",
        "Directive (EU) 2019/771 on certain aspects concerning contracts for the sale of goods",
        "directive",
        ["sale", "warranty", "b2c"],
    ),
    _eu(
        "eu-2019-770",
        "32019L0770",
        "Digital Content Directive",
        "Directive (EU) 2019/770 on contracts for the supply of digital content and digital services",
        "directive",
        ["software", "subscription", "b2c"],
    ),
    _eu(
        "eu-2011-83",
        "32011L0083",
        "Consumer Rights Directive",
        "Directive 2011/83/EU on consumer rights",
        "directive",
        ["consumer", "distance", "b2c"],
    ),
    _eu(
        "eu-93-13",
        "31993L0013",
        "Unfair Terms Directive",
        "Council Directive 93/13/EEC on unfair terms in consumer contracts",
        "directive",
        ["unfair-terms", "b2c"],
    ),
    _eu(
        "eu-2000-31",
        "32000L0031",
        "E-commerce Directive",
        "Directive 2000/31/EC on electronic commerce",
        "directive",
        ["online", "services"],
    ),
    _eu(
        "eu-2009-24",
        "32009L0024",
        "Computer Programs Directive",
        "Directive 2009/24/EC on the legal protection of computer programs",
        "directive",
        ["software", "licence"],
    ),
    # --- EU: applicable law and courts ---
    _eu(
        "eu-593-2008",
        "32008R0593",
        "Rome I",
        "Regulation (EC) No 593/2008 on the law applicable to contractual obligations (Rome I)",
        "regulation",
        ["governing-law"],
    ),
    _eu(
        "eu-1215-2012",
        "32012R1215",
        "Brussels I (recast)",
        "Regulation (EU) No 1215/2012 on jurisdiction and the recognition and enforcement of judgments",
        "regulation",
        ["jurisdiction"],
    ),
    # --- EU: data, security, digital ---
    _eu(
        "eu-2016-679",
        "32016R0679",
        "GDPR",
        "Regulation (EU) 2016/679 (General Data Protection Regulation)",
        "regulation",
        ["data", "processor", "transfers"],
    ),
    _eu(
        "eu-2023-2854",
        "32023R2854",
        "Data Act",
        "Regulation (EU) 2023/2854 on harmonised rules on fair access to and use of data (Data Act)",
        "regulation",
        ["data", "cloud", "switching"],
    ),
    _eu(
        "eu-2022-2555",
        "32022L2555",
        "NIS2",
        "Directive (EU) 2022/2555 on measures for a high common level of cybersecurity (NIS2)",
        "directive",
        ["security"],
    ),
    _eu(
        "eu-2024-1689",
        "32024R1689",
        "AI Act",
        "Regulation (EU) 2024/1689 laying down harmonised rules on artificial intelligence (AI Act)",
        "regulation",
        ["ai"],
    ),
    _eu(
        "eu-2024-2847",
        "32024R2847",
        "Cyber Resilience Act",
        "Regulation (EU) 2024/2847 on horizontal cybersecurity requirements for products with digital elements",
        "regulation",
        ["security", "product"],
    ),
    # --- EU: products, electronics ---
    _eu(
        "eu-2023-988",
        "32023R0988",
        "GPSR",
        "Regulation (EU) 2023/988 on general product safety",
        "regulation",
        ["product", "safety"],
    ),
    _eu(
        "eu-2014-53",
        "32014L0053",
        "RED",
        "Directive 2014/53/EU on radio equipment",
        "directive",
        ["electronics", "conformity"],
    ),
    _eu(
        "eu-2014-35",
        "32014L0035",
        "Low Voltage Directive",
        "Directive 2014/35/EU on electrical equipment designed for use within certain voltage limits",
        "directive",
        ["electronics", "conformity"],
    ),
    _eu(
        "eu-2014-30",
        "32014L0030",
        "EMC Directive",
        "Directive 2014/30/EU on electromagnetic compatibility",
        "directive",
        ["electronics", "conformity"],
    ),
    _eu(
        "eu-2011-65",
        "32011L0065",
        "RoHS",
        "Directive 2011/65/EU on the restriction of hazardous substances in electrical and electronic equipment",
        "directive",
        ["electronics", "environment"],
    ),
    _eu(
        "eu-2012-19",
        "32012L0019",
        "WEEE",
        "Directive 2012/19/EU on waste electrical and electronic equipment",
        "directive",
        ["electronics", "environment"],
    ),
    _eu(
        "eu-2023-1542",
        "32023R1542",
        "Batteries Regulation",
        "Regulation (EU) 2023/1542 concerning batteries and waste batteries",
        "regulation",
        ["electronics", "environment"],
    ),
    _eu(
        "eu-2024-2853",
        "32024L2853",
        "Product Liability Directive (new)",
        "Directive (EU) 2024/2853 on liability for defective products",
        "directive",
        ["liability", "product"],
    ),
    _eu(
        "eu-85-374",
        "31985L0374",
        "Product Liability Directive (old)",
        "Council Directive 85/374/EEC on liability for defective products",
        "directive",
        ["liability", "product"],
    ),
    # --- EU: trade compliance ---
    _eu(
        "eu-833-2014",
        "32014R0833",
        "Sanctions: Russia (sectoral)",
        "Council Regulation (EU) No 833/2014 concerning restrictive measures in view of Russia's actions destabilising the situation in Ukraine",
        "regulation",
        ["sanctions", "export"],
    ),
    _eu(
        "eu-269-2014",
        "32014R0269",
        "Sanctions: Russia (listings)",
        "Council Regulation (EU) No 269/2014 concerning restrictive measures in respect of actions undermining Ukraine's territorial integrity",
        "regulation",
        ["sanctions"],
    ),
    _eu(
        "eu-2021-821",
        "32021R0821",
        "Dual-use Regulation",
        "Regulation (EU) 2021/821 setting up a Union regime for the control of exports of dual-use items",
        "regulation",
        ["export", "compliance"],
    ),
    _eu(
        "eu-952-2013",
        "32013R0952",
        "Union Customs Code",
        "Regulation (EU) No 952/2013 laying down the Union Customs Code",
        "regulation",
        ["customs"],
    ),
    # --- International ---
    {
        **_other(
            "cisg",
            "INT",
            "convention",
            "United Nations Convention on Contracts for the International Sale of Goods (Vienna, 1980)",
            "CISG",
            ["sale", "warranty", "damages", "exclusion"],
            "https://uncitral.un.org/sites/uncitral.un.org/files/media-documents/uncitral/en/19-09951_e_ebook.pdf",
        ),
        "ref": "UN Treaty Series vol. 1489",
    },
    _other(
        "ny-1958",
        "INT",
        "convention",
        "Convention on the Recognition and Enforcement of Foreign Arbitral Awards (New York, 1958)",
        "New York Convention",
        ["arbitration"],
        "https://uncitral.un.org/sites/uncitral.un.org/files/media-documents/uncitral/en/new-york-convention-e.pdf",
    ),
    _other(
        "unidroit-2016",
        "INT",
        "principles",
        "UNIDROIT Principles of International Commercial Contracts (2016)",
        "UNIDROIT Principles",
        ["general", "soft-law"],
        "https://www.unidroit.org/wp-content/uploads/2021/06/Unidroit-Principles-2016-English-i.pdf",
    ),
    # --- Serbia (check numbers and titles on import) ---
    _other(
        "rs-zoo",
        "RS",
        "law",
        "Law on Obligations (Zakon o obligacionim odnosima)",
        "Law on Obligations (RS)",
        ["contract", "penalty", "damages", "liability"],
    ),
    _other(
        "rs-payment-terms",
        "RS",
        "law",
        "Law on Payment Terms in Commercial Transactions (Zakon o rokovima izmirenja novčanih obaveza u komercijalnim transakcijama)",
        "Payment Terms Law (RS)",
        ["payment", "interest"],
    ),
    _other(
        "rs-trade", "RS", "law", "Law on Trade (Zakon o trgovini)", "Law on Trade (RS)", ["sale", "trade"]
    ),
    _other(
        "rs-foreign-trade",
        "RS",
        "law",
        "Law on Foreign Trade Operations (Zakon o spoljnotrgovinskom poslovanju)",
        "Foreign Trade Law (RS)",
        ["export", "import"],
    ),
    _other(
        "rs-consumer",
        "RS",
        "law",
        "Law on Consumer Protection (Zakon o zaštiti potrošača)",
        "Consumer Law (RS)",
        ["consumer", "b2c"],
    ),
    _other(
        "rs-pdp",
        "RS",
        "law",
        "Law on Personal Data Protection (Zakon o zaštiti podataka o ličnosti)",
        "Data Protection Law (RS)",
        ["data"],
    ),
    _other(
        "rs-ecommerce",
        "RS",
        "law",
        "Law on Electronic Commerce (Zakon o elektronskoj trgovini)",
        "E-commerce Law (RS)",
        ["online"],
    ),
    _other(
        "rs-arbitration",
        "RS",
        "law",
        "Law on Arbitration (Zakon o arbitraži)",
        "Arbitration Law (RS)",
        ["arbitration"],
    ),
    _other("rs-customs", "RS", "law", "Customs Law (Carinski zakon)", "Customs Law (RS)", ["customs"]),
    # --- China (check numbers and titles on import) ---
    _other(
        "cn-civil-code",
        "CN",
        "code",
        "Civil Code of the People's Republic of China (2020), Book III Contracts",
        "Civil Code (CN)",
        ["contract", "penalty", "damages", "standard-terms"],
    ),
    _other(
        "cn-foreign-trade",
        "CN",
        "law",
        "Foreign Trade Law of the People's Republic of China",
        "Foreign Trade Law (CN)",
        ["export", "import"],
    ),
    _other(
        "cn-export-control",
        "CN",
        "law",
        "Export Control Law of the People's Republic of China (2020)",
        "Export Control Law (CN)",
        ["export", "compliance"],
    ),
    _other(
        "cn-pipl",
        "CN",
        "law",
        "Personal Information Protection Law of the People's Republic of China (2021)",
        "PIPL (CN)",
        ["data", "transfers"],
    ),
    _other(
        "cn-data-security",
        "CN",
        "law",
        "Data Security Law of the People's Republic of China (2021)",
        "Data Security Law (CN)",
        ["data"],
    ),
    _other(
        "cn-cybersecurity",
        "CN",
        "law",
        "Cybersecurity Law of the People's Republic of China",
        "Cybersecurity Law (CN)",
        ["security"],
    ),
    _other(
        "cn-anti-sanctions",
        "CN",
        "law",
        "Anti-Foreign Sanctions Law of the People's Republic of China (2021)",
        "Anti-Foreign Sanctions Law (CN)",
        ["sanctions"],
    ),
    _other(
        "cn-arbitration",
        "CN",
        "law",
        "Arbitration Law of the People's Republic of China",
        "Arbitration Law (CN)",
        ["arbitration"],
    ),
    # --- UAE (check numbers and titles on import) ---
    _other(
        "ae-civil",
        "AE",
        "law",
        "Federal Decree-Law No. 5 of 1985 on Civil Transactions (Civil Transactions Law)",
        "Civil Transactions Law (AE)",
        ["contract", "penalty", "damages"],
    ),
    _other(
        "ae-commercial",
        "AE",
        "law",
        "Federal Decree-Law No. 50 of 2022 on Commercial Transactions",
        "Commercial Transactions Law (AE)",
        ["sale", "trade"],
    ),
    _other(
        "ae-pdpl",
        "AE",
        "law",
        "Federal Decree-Law No. 45 of 2021 on the Protection of Personal Data",
        "PDPL (AE)",
        ["data", "transfers"],
    ),
    _other(
        "ae-arbitration",
        "AE",
        "law",
        "Federal Law No. 6 of 2018 on Arbitration",
        "Arbitration Law (AE)",
        ["arbitration"],
    ),
    _other(
        "ae-consumer",
        "AE",
        "law",
        "Federal Law No. 15 of 2020 on Consumer Protection",
        "Consumer Law (AE)",
        ["consumer", "b2c"],
    ),
    _other(
        "ae-etransactions",
        "AE",
        "law",
        "Federal Decree-Law No. 46 of 2021 on Electronic Transactions and Trust Services",
        "E-transactions Law (AE)",
        ["online"],
    ),
]

JURISDICTIONS = {
    "EU": "European Union",
    "INT": "International",
    "RS": "Serbia",
    "CN": "China",
    "AE": "United Arab Emirates",
}


def eurlex_urls(celex: str) -> list[str]:
    """Where the English text of an EU act can be fetched, most robust first (see loader for why)."""
    return [
        f"https://publications.europa.eu/resource/celex/{celex}",
        f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}",
    ]
