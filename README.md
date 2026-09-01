# Indian Market Intelligence

Shared data components for an Indian equity market intelligence system.

This slice is a canonical company registry plus a read-only MCP server over Streamable HTTP. There is no FastAPI app, database, live market feed, or authentication yet.

## Layout

- `data/companies.json` — one object per listed company
- `src/company_registry.py` — read-only lookups over that file
- `src/mcp_server.py` — MCP tools over the same registry
- `tests/` — registry and MCP tool tests

## Company fields

| Field | Meaning |
| --- | --- |
| `company_name` | Registered / listed name |
| `nse_symbol` | NSE equity symbol |
| `bse_code` | BSE scrip code |
| `isin` | ISIN of the currently listed equity |
| `sector` | Broad sector label from public listing pages |
| `industry` | Finer industry label where available |
| `official_x_handle` | Official X account, or `null` if not verified |
| `official_website` | Company website |
| `investor_relations_url` | Investor / disclosures page, or `null` |
| `aliases` | Common names and tickers used in search |
| `source_verified` | Whether listing identifiers were checked against public sources |
| `last_verified_at` | Date those identifiers were last checked (`YYYY-MM-DD`) |
| `defence_aerospace_related` | Whether the company is in the defence/aerospace research universe |

Unknown values are stored as `null`. Do not invent identifiers, websites, or social handles.

The seed set is Indian defence / aerospace names (plus L&T, which has a large defence business). ISINs reflect post-split equity where listing pages show a newer code.

## Python usage

```python
from company_registry import (
    get_all_official_x_handles,
    get_companies_by_sector,
    get_company_by_name,
    get_company_by_symbol,
    get_defence_research_universe,
    get_official_x_handle,
    get_official_x_handles_by_sector,
    search_companies,
)

get_company_by_symbol("hal")
get_company_by_name("MDL")
search_companies("ship")
get_companies_by_sector("Aerospace & Defence")
get_official_x_handle("BEL")
get_all_official_x_handles(sector="Ship Building")
get_official_x_handles_by_sector("Ship Building")
get_defence_research_universe()
```

Lookups are case-insensitive. `get_company_by_name` and `search_companies` both honour `aliases`.

## MCP server

The server uses the official Python MCP SDK (`mcp`) and Streamable HTTP (not the legacy SSE transport). Tools are read-only wrappers around `company_registry.py`.

It binds to `0.0.0.0` and listens on `PORT` when that environment variable is set (Railway sets this automatically). If `PORT` is unset, it uses `3001` for local development.

### Endpoints

| Path | Purpose |
| --- | --- |
| `/health` | Health check. Returns `{"status":"ok"}`. |
| `/mcp` | Streamable HTTP MCP endpoint. MCP clients POST JSON-RPC here. |
| `/` | Status page (HTML in a browser, JSON otherwise). |

A browser can open `/` or `/mcp` to confirm the server is up. `/mcp` is still the MCP endpoint; Chrome just gets a status page instead of hanging on the event stream.

### Local start

This machine has `python3`, not `python`:

```bash
python3 -m pip install -r requirements.txt
python3 src/mcp_server.py
```

That listens on:

- Health: `http://127.0.0.1:3001/health`
- MCP: `http://127.0.0.1:3001/mcp`

Cursor is configured in `.cursor/mcp.json` to use `http://127.0.0.1:3001/mcp`. Start this server first, then reload MCP in Cursor.

To mimic Railway locally:

```bash
PORT=8080 python3 src/mcp_server.py
```

### Railway deployment

1. Create a new Railway project from this repo (GitHub, or `railway up`).
2. Railway installs `requirements.txt` and starts the web process from `Procfile` / `railway.toml`.
3. Generate a public domain in Railway (Settings → Networking).

Start command (also in `Procfile`):

```bash
python src/mcp_server.py
```

After deploy:

- Health: `https://<your-railway-domain>/health`
- MCP: `https://<your-railway-domain>/mcp`

Set Railway’s health check path to `/health` if you want deploy probes against that endpoint.

### Environment variables

| Variable | Required | Meaning |
| --- | --- | --- |
| `PORT` | No locally; set automatically on Railway | Listen port. Falls back to `3001` when unset. |

No other environment variables are required. There is no database, API key, or auth config.

Tools:

| Tool | Input | Returns |
| --- | --- | --- |
| `get_company_by_symbol` | `symbol` | Canonical company object, or `null` |
| `search_companies` | `query` | Matching company objects |
| `get_companies_by_sector` | `sector` | Matching company objects |
| `get_official_x_handle` | `symbol` | Verified X handle, or `null` |
| `get_official_x_handles_by_sector` | `sector` | `{company_name, nse_symbol, official_x_handle}` for companies with a verified handle |
| `get_defence_research_universe` | none | All defence/aerospace companies, plus `companies_without_verified_official_x_account` |

## Tests

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=src python3 -m pytest tests
```
