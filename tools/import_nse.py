"""Bulk-import the NSE equity universe into data/companies.json.

Downloads the official NSE list of listed equity securities
(EQUITY_L.csv from archives.nseindia.com), maps each row onto the
canonical registry schema, and merges with the existing curated records:

- Existing entries win. The 18 curated defence/aerospace records keep
  their verified identifiers, sectors, handles, and aliases.
- New entries are created with unknown fields as null and
  source_verified=false; they are candidates for later verification,
  not verified data.

Usage (from the repo root):

    python tools/import_nse.py

Requires network access to archives.nseindia.com.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "companies.json"

NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
# NSE rejects generic HTTP clients; present as a browser.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,text/plain,*/*",
}

# Only the EQ series: one row per active equity listing. Other series
# (BE, BZ, SM, ...) are trade-to-trade or SME lines of the same companies.
SERIES = "EQ"


# Each company may appear under several series (EQ, BE, BZ, ...). Dedupe
# by ISIN and prefer the EQ line; companies that trade only in another
# series (e.g. MTARTECH in BE) are still included.
def fetch_nse_equity_rows() -> list[dict[str, str]]:
    request = urllib.request.Request(NSE_EQUITY_URL, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read().decode("utf-8-sig", errors="replace")
    by_isin: dict[str, dict[str, str]] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        # Header names vary in case and carry stray spaces (" SERIES");
        # normalize them before filtering and mapping.
        row = {(k or "").strip().casefold(): v for k, v in row.items()}
        isin = (row.get("isin number") or "").strip()
        if not isin:
            continue
        current = by_isin.get(isin)
        if current is None or (
            (current.get("series") or "").strip() != SERIES
            and (row.get("series") or "").strip() == SERIES
        ):
            by_isin[isin] = row
    return list(by_isin.values())


def blank_record(symbol: str, name: str, isin: str) -> dict:
    """A registry entry for an unverified bulk-imported company."""
    return {
        "company_name": name.strip(),
        "nse_symbol": symbol.strip(),
        "bse_code": None,
        "isin": isin.strip(),
        "sector": None,
        "industry": None,
        "official_x_handle": None,
        "official_website": None,
        "investor_relations_url": None,
        "aliases": [],
        "source_verified": False,
        "last_verified_at": None,
        "defence_aerospace_related": False,
    }


def main() -> int:
    existing = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    by_isin = {c["isin"]: c for c in existing if c.get("isin")}
    by_symbol = {c["nse_symbol"]: c for c in existing if c.get("nse_symbol")}

    rows = fetch_nse_equity_rows()
    kept, added = 0, 0
    records: dict[str, dict] = {}

    for row in rows:
        symbol = (row.get("symbol") or "").strip()
        name = (row.get("name of company") or "").strip()
        isin = (row.get("isin number") or "").strip()
        if not symbol or not isin:
            continue
        if isin in records:
            continue  # duplicate ISIN within the file
        current = by_isin.get(isin) or by_symbol.get(symbol)
        if current is not None:
            records[isin] = current
            kept += 1
        else:
            records[isin] = blank_record(symbol, name, isin)
            added += 1

    # Preserve curated records that are absent from the NSE file (e.g. a
    # company trading only on BSE). The import must never drop data.
    for company in existing:
        isin = company.get("isin")
        if isin and isin not in records:
            records[isin] = company
            kept += 1

    merged = sorted(records.values(), key=lambda c: c["nse_symbol"])
    DATA_PATH.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"NSE companies: {len(rows)}")
    print(f"total companies: {len(merged)} (kept existing: {kept}, added: {added})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
