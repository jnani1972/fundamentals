import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from company_registry import (  # noqa: E402
    get_all_official_x_handles,
    get_companies_by_sector,
    get_company_by_name,
    get_company_by_symbol,
    get_defence_research_universe,
    get_official_x_handle,
    get_official_x_handles_by_sector,
    get_sectors,
    load_companies,
    search_companies,
)

REQUIRED_FIELDS = {
    "company_name",
    "nse_symbol",
    "bse_code",
    "isin",
    "sector",
    "industry",
    "official_x_handle",
    "official_website",
    "investor_relations_url",
    "aliases",
    "source_verified",
    "last_verified_at",
    "defence_aerospace_related",
}

SEEDED_SYMBOLS = {
    "HAL",
    "BEL",
    "BDL",
    "BEML",
    "MAZDOCK",
    "GRSE",
    "COCHINSHIP",
    "DATAPATTNS",
    "PARAS",
    "ZENTEC",
    "ASTRAMICRO",
    "DCXINDIA",
    "APOLLO",
    "IDEAFORGE",
    "MTARTECH",
    "MIDHANI",
    "CYIENTDLM",
    "LT",
}


def test_seed_file_has_expected_companies_and_fields():
    companies = load_companies()
    # Bulk NSE import: the full mainboard universe plus curated records.
    assert len(companies) > 2000
    symbols = {company["nse_symbol"] for company in companies}
    assert SEEDED_SYMBOLS <= symbols
    for company in companies:
        assert REQUIRED_FIELDS <= set(company)
        assert isinstance(company["aliases"], list)
        assert company["nse_symbol"]
        assert company["company_name"]
        # INE... is equity; IN9... appears for DVR securities (FELDVR, JISLDVREQS).
        assert company["isin"].startswith("IN")
    # The curated defence records keep their verified data.
    seeded = [c for c in companies if c["nse_symbol"] in SEEDED_SYMBOLS]
    assert all(c["source_verified"] for c in seeded)
    assert all(c["defence_aerospace_related"] for c in seeded)


def test_get_company_by_symbol_is_case_insensitive():
    company = get_company_by_symbol("hal")
    assert company is not None
    assert company["company_name"] == "Hindustan Aeronautics Limited"
    assert get_company_by_symbol("HAL.NS")["nse_symbol"] == "HAL"
    assert get_company_by_symbol("unknown") is None
    assert get_company_by_symbol("") is None


def test_get_company_by_name_uses_aliases():
    by_name = get_company_by_name("hindustan aeronautics")
    by_alias = get_company_by_name("MDL")
    by_lt = get_company_by_name("l&t")
    assert by_name["nse_symbol"] == "HAL"
    assert by_alias["nse_symbol"] == "MAZDOCK"
    assert by_lt["nse_symbol"] == "LT"
    assert get_company_by_name("not a listed company") is None


def test_search_companies_matches_name_symbol_and_alias():
    by_partial_name = search_companies("Aeronautics")
    by_symbol = search_companies("mazdock")
    by_alias = search_companies("csl")
    assert [company["nse_symbol"] for company in by_partial_name] == ["HAL"]
    assert [company["nse_symbol"] for company in by_symbol] == ["MAZDOCK"]
    # "CSL" is an alias of Cochin Shipyard; the wider universe also
    # legitimately matches CSL Finance and GCSL as substrings.
    assert [company["nse_symbol"] for company in by_alias] == [
        "COCHINSHIP",
        "CSLFINANCE",
        "GCSL",
    ]
    assert search_companies("") == []


def test_get_sectors_returns_sorted_distinct_labels():
    sectors = get_sectors()
    assert sectors == sorted(set(sectors))
    assert "Aerospace & Defence" in sectors
    assert "Ship Building" in sectors


def test_get_companies_by_sector_is_case_insensitive():
    shipyards = get_companies_by_sector("ship building")
    symbols = {company["nse_symbol"] for company in shipyards}
    assert symbols == {"MAZDOCK", "GRSE", "COCHINSHIP"}
    assert get_companies_by_sector("not-a-sector") == []


def test_official_x_handles():
    assert get_official_x_handle("BEL") == "@BEL_CorpCom"
    assert get_official_x_handle("hal") == "@HALHQBLR"
    assert get_official_x_handle("ZENTEC") is None
    assert get_official_x_handle("missing") is None

    all_handles = get_all_official_x_handles()
    assert "@HALHQBLR" in all_handles
    assert "@cslcochin" in all_handles
    assert None not in all_handles

    shipyard_handles = get_all_official_x_handles("Ship Building")
    assert shipyard_handles == ["@cslcochin"]


def test_official_x_handles_by_sector_excludes_nulls():
    shipyards = get_official_x_handles_by_sector("Ship Building")
    assert shipyards == [
        {
            "company_name": "Cochin Shipyard Limited",
            "nse_symbol": "COCHINSHIP",
            "official_x_handle": "@cslcochin",
        }
    ]
    assert get_official_x_handles_by_sector("not-a-sector") == []


def test_defence_research_universe_includes_companies_without_x_handles():
    universe = get_defence_research_universe()
    companies = universe["companies"]
    without = universe["companies_without_verified_official_x_account"]
    symbols = {company["nse_symbol"] for company in companies}
    assert symbols == SEEDED_SYMBOLS
    assert all(company["defence_aerospace_related"] is True for company in companies)

    without_symbols = {row["nse_symbol"] for row in without}
    assert "ZENTEC" in without_symbols
    assert "HAL" not in without_symbols
    assert {company["nse_symbol"] for company in companies if not company["official_x_handle"]} == without_symbols
