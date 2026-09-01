"""Canonical company registry for Indian listed companies."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

Company = dict[str, Any]

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "companies.json"


def _norm(value: str | None) -> str:
    return (value or "").strip().casefold()


def _clean_symbol(symbol: str) -> str:
    cleaned = _norm(symbol)
    for suffix in (".ns", ".bo", ".bse"):
        if cleaned.endswith(suffix):
            return cleaned[: -len(suffix)]
    return cleaned


@lru_cache(maxsize=1)
def load_companies() -> list[Company]:
    """Load the canonical company list from disk."""
    with _DATA_PATH.open(encoding="utf-8") as handle:
        companies = json.load(handle)
    if not isinstance(companies, list):
        raise ValueError("companies.json must contain a JSON array")
    return companies


def _matches_name_or_alias(company: Company, query: str) -> bool:
    if _norm(company.get("company_name")) == query:
        return True
    aliases = company.get("aliases") or []
    return any(_norm(alias) == query for alias in aliases)


def _search_haystack(company: Company) -> list[str]:
    fields = [
        company.get("company_name"),
        company.get("nse_symbol"),
        company.get("bse_code"),
        company.get("isin"),
        company.get("sector"),
        company.get("industry"),
    ]
    aliases = company.get("aliases") or []
    return [value for value in [*fields, *aliases] if isinstance(value, str) and value]


def get_company_by_symbol(symbol: str) -> Company | None:
    """Return a company by NSE symbol. Matching is case-insensitive."""
    target = _clean_symbol(symbol)
    if not target:
        return None
    for company in load_companies():
        if _norm(company.get("nse_symbol")) == target:
            return company
    return None


def get_company_by_name(name: str) -> Company | None:
    """Return a company by registered name or alias. Matching is case-insensitive."""
    target = _norm(name)
    if not target:
        return None
    for company in load_companies():
        if _matches_name_or_alias(company, target):
            return company
    return None


def search_companies(query: str) -> list[Company]:
    """Case-insensitive substring search across names, symbols, codes, and aliases."""
    target = _norm(query)
    if not target:
        return []
    matches = []
    for company in load_companies():
        if any(target in _norm(value) for value in _search_haystack(company)):
            matches.append(company)
    return matches


def get_companies_by_sector(sector: str) -> list[Company]:
    """Return companies whose sector matches exactly, ignoring case."""
    target = _norm(sector)
    if not target:
        return []
    return [
        company
        for company in load_companies()
        if _norm(company.get("sector")) == target
    ]


def get_official_x_handle(symbol: str) -> str | None:
    """Return the official X handle for an NSE symbol, if known."""
    company = get_company_by_symbol(symbol)
    if not company:
        return None
    handle = company.get("official_x_handle")
    return handle if handle else None


def get_all_official_x_handles(sector: str | None = None) -> list[str]:
    """Return known official X handles, optionally filtered by sector."""
    companies = load_companies() if sector is None else get_companies_by_sector(sector)
    handles: list[str] = []
    for company in companies:
        handle = company.get("official_x_handle")
        if handle:
            handles.append(handle)
    return handles


def get_official_x_handles_by_sector(sector: str) -> list[dict[str, str]]:
    """Return name, NSE symbol, and verified X handle for a sector.

    Companies whose official X handle is null are excluded.
    """
    matches: list[dict[str, str]] = []
    for company in get_companies_by_sector(sector):
        handle = company.get("official_x_handle")
        if not handle:
            continue
        matches.append(
            {
                "company_name": company["company_name"],
                "nse_symbol": company["nse_symbol"],
                "official_x_handle": handle,
            }
        )
    return matches


def is_defence_aerospace_related(company: Company) -> bool:
    """Return True when the company is tagged for the defence/aerospace universe."""
    return bool(company.get("defence_aerospace_related"))


def get_defence_research_universe() -> dict[str, Any]:
    """Return defence/aerospace companies, including those with no X handle.

    Canonical company objects are unchanged. Companies without a verified
    official X account are listed separately so that absence is explicit.
    """
    companies = [
        company for company in load_companies() if is_defence_aerospace_related(company)
    ]
    without_handle = [
        {
            "company_name": company["company_name"],
            "nse_symbol": company["nse_symbol"],
        }
        for company in companies
        if not company.get("official_x_handle")
    ]
    return {
        "companies": companies,
        "companies_without_verified_official_x_account": without_handle,
    }
