#!/usr/bin/env python3
"""Read-only MCP server for the canonical Indian company registry."""

from __future__ import annotations

import html
import os
import socket
import sys
from pathlib import Path
from typing import Any, TypedDict

try:
    from mcp.server import MCPServer
except ImportError:  # mcp 2.x layout variation
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover - install hint only
        raise SystemExit(
            "The official MCP Python SDK is required. Install with:\n"
            "  python3 -m pip install -r requirements.txt"
        ) from exc

from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from company_registry import (  # noqa: E402
    get_companies_by_sector as registry_get_companies_by_sector,
    get_company_by_symbol as registry_get_company_by_symbol,
    get_defence_research_universe as registry_get_defence_research_universe,
    get_official_x_handle as registry_get_official_x_handle,
    get_official_x_handles_by_sector as registry_get_official_x_handles_by_sector,
    get_sectors as registry_get_sectors,
    search_companies as registry_search_companies,
)

LISTEN_HOST = "0.0.0.0"
DEFAULT_PORT = 3001
MCP_PATH = "/mcp"
TOOL_NAMES = [
    "get_company_by_symbol",
    "search_companies",
    "get_sectors",
    "get_companies_by_sector",
    "get_official_x_handle",
    "get_official_x_handles_by_sector",
    "get_defence_research_universe",
]

_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📈</text></svg>">
  <title>Indian company registry — search</title>
  <style>
    body { font: 16px/1.45 ui-sans-serif, system-ui, sans-serif; margin: 2rem; color: #1a1a1a; max-width: 60rem; }
    h1 { margin-bottom: 0.25rem; }
    .muted { color: #666; font-size: 0.9rem; }
    form { display: flex; gap: 0.5rem; margin: 1rem 0 1.5rem; flex-wrap: wrap; }
    input[type=search] { flex: 1; min-width: 16rem; padding: 0.55rem 0.7rem; font-size: 1rem; border: 1px solid #bbb; border-radius: 6px; }
    button { padding: 0.55rem 0.9rem; font-size: 0.95rem; border: 1px solid #2f6fdd; background: #2f6fdd; color: #fff; border-radius: 6px; cursor: pointer; }
    button.ghost { background: #fff; color: #2f6fdd; }
    #status { margin: 0.5rem 0; color: #666; }
    .card { border: 1px solid #ddd; border-radius: 8px; padding: 0.9rem 1.1rem; margin-bottom: 0.9rem; background: #fbfbf9; }
    .card h2 { margin: 0 0 0.5rem; font-size: 1.1rem; }
    table { border-collapse: collapse; width: 100%; font-size: 0.92rem; }
    td { padding: 0.15rem 0.6rem 0.15rem 0; vertical-align: top; }
    td.k { color: #666; white-space: nowrap; }
    a { color: #2f6fdd; }
    pre { background: #f3f3f0; padding: 0.8rem; border-radius: 6px; overflow-x: auto; }
  </style>
</head>
<body>
  <h1>Indian company registry</h1>
  <p class="muted">Search the canonical registry. Try a name, symbol, alias, ISIN, or BSE code (e.g. <em>HAL</em>, <em>MDL</em>, <em>ship</em>).</p>
  <form id="search-form">
    <input id="q" type="search" placeholder="Search companies…" autofocus>
    <button type="submit">Search</button>
    <select id="sector-sel" title="Browse by sector">
      <option value="" selected disabled>Choose a sector…</option>
      <option value="__defence__">Defence / aerospace universe</option>
    </select>
  </form>
  <div id="status"></div>
  <div id="results"></div>
<script>
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');

async function callTool(name, args) {
  const resp = await fetch('/mcp', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'},
    body: JSON.stringify({jsonrpc: '2.0', id: 1, method: 'tools/call',
                          params: {name: name, arguments: args}})
  });
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
  const data = await resp.json();
  if (data.error) throw new Error(data.error.message || 'MCP error');
  const sc = data.result && data.result.structuredContent;
  if (sc && 'result' in sc) return sc.result;
  if (data.result && data.result.content && data.result.content[0]) {
    try { return JSON.parse(data.result.content[0].text); } catch (e) { return data.result.content[0].text; }
  }
  return null;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function linkify(value) {
  if (typeof value === 'string' && /^https?:\/\//.test(value))
    return '<a href="' + esc(value) + '" target="_blank" rel="noopener">' + esc(value) + '</a>';
  return esc(value);
}

function renderCard(obj) {
  if (obj === null || typeof obj !== 'object') return '<div class="card"><pre>' + esc(String(obj)) + '</pre></div>';
  const title = obj.company_name || obj.nse_symbol || 'Result';
  let rows = '';
  for (const [k, v] of Object.entries(obj)) {
    if (v === null || v === undefined) {
      if (k === 'official_x_handle')
        rows += '<tr><td class="k">official_x_handle</td><td class="muted">no verified account</td></tr>';
      continue;
    }
    const shown = Array.isArray(v) ? v.join(', ') : (typeof v === 'object' ? JSON.stringify(v) : v);
    rows += '<tr><td class="k">' + esc(k) + '</td><td>' + linkify(shown) + '</td></tr>';
  }
  return '<div class="card"><h2>' + esc(title) + '</h2><table>' + rows + '</table></div>';
}

function render(data) {
  if (data === null || data === undefined) {
    resultsEl.innerHTML = '<p>No match.</p>';
  } else if (Array.isArray(data)) {
    resultsEl.innerHTML = data.length ? data.map(renderCard).join('') : '<p>No match.</p>';
  } else if (typeof data === 'object' && Array.isArray(data.companies)) {
    // Every company gets a full card; missing handles are noted inside the card.
    resultsEl.innerHTML = data.companies.map(renderCard).join('');
  } else if (typeof data === 'object') {
    resultsEl.innerHTML = renderCard(data);
  } else {
    resultsEl.innerHTML = '<div class="card"><pre>' + esc(data) + '</pre></div>';
  }
}

async function run(label, promise) {
  statusEl.textContent = 'Loading ' + label + '…';
  resultsEl.innerHTML = '';
  try {
    render(await promise);
    statusEl.textContent = '';
  } catch (err) {
    statusEl.textContent = '';
    resultsEl.innerHTML = '<p>Error: ' + esc(err.message) + '</p>';
  }
}

async function loadSectors() {
  const sectors = await callTool('get_sectors', {});
  const sel = document.getElementById('sector-sel');
  for (const s of sectors) {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = s;
    sel.appendChild(opt);
  }
}

document.getElementById('search-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  run('“' + q + '”', callTool('search_companies', {query: q}));
});

document.getElementById('sector-sel').addEventListener('change', (e) => {
  const v = e.target.value;
  if (!v) return;
  if (v === '__defence__')
    run('defence universe', callTool('get_defence_research_universe', {}));
  else
    run(v, callTool('get_companies_by_sector', {sector: v}));
});

// Populate the sector dropdown from the registry, then load the default view.
loadSectors().catch((err) => { statusEl.textContent = 'Could not load sectors: ' + err.message; });
run('defence universe', callTool('get_defence_research_universe', {}));
</script>
</body>
</html>"""


class OfficialXHandleRow(TypedDict):
    company_name: str
    nse_symbol: str
    official_x_handle: str


class MissingOfficialXHandleRow(TypedDict):
    company_name: str
    nse_symbol: str


class DefenceResearchUniverse(TypedDict):
    companies: list[dict[str, Any]]
    companies_without_verified_official_x_account: list[MissingOfficialXHandleRow]


mcp = MCPServer(
    "indian-company-registry",
    instructions=(
        "Read-only canonical registry of Indian listed companies. "
        "Unknown values are null; do not invent missing fields."
    ),
)


@mcp.tool()
def get_company_by_symbol(symbol: str) -> dict | None:
    """Return the complete canonical company object for an NSE symbol, or null."""
    return registry_get_company_by_symbol(symbol)


@mcp.tool()
def search_companies(query: str) -> list[dict]:
    """Return companies matching a case-insensitive name, symbol, code, or alias query."""
    return registry_search_companies(query)


@mcp.tool()
def get_sectors() -> list[str]:
    """Return the sorted list of distinct sectors in the registry."""
    return registry_get_sectors()


@mcp.tool()
def get_companies_by_sector(sector: str) -> list[dict]:
    """Return canonical company objects whose sector matches, ignoring case."""
    return registry_get_companies_by_sector(sector)


@mcp.tool()
def get_official_x_handle(symbol: str) -> str | None:
    """Return the verified official X handle for an NSE symbol, or null."""
    return registry_get_official_x_handle(symbol)


@mcp.tool()
def get_official_x_handles_by_sector(sector: str) -> list[OfficialXHandleRow]:
    """Return company name, NSE symbol, and verified X handle for a sector.

    Entries whose official X handle is null are excluded.
    """
    return registry_get_official_x_handles_by_sector(sector)


@mcp.tool()
def get_defence_research_universe() -> DefenceResearchUniverse:
    """Return defence/aerospace companies, including those with no verified X account."""
    return registry_get_defence_research_universe()


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    first = accept.split(",")[0].strip().lower()
    return first.startswith("text/html")


def listen_port() -> int:
    """Use Railway's PORT when set; otherwise the local development port."""
    raw = os.environ.get("PORT")
    if raw is None or not str(raw).strip():
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError as exc:
        raise SystemExit(f"PORT must be an integer, got {raw!r}") from exc
    if not 1 <= port <= 65535:
        raise SystemExit(f"PORT out of range: {port}")
    return port


def _public_base(request: Request) -> str:
    host = request.headers.get("host") or f"127.0.0.1:{listen_port()}"
    forwarded = request.headers.get("x-forwarded-proto")
    proto = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.url.scheme or "http")
    )
    return f"{proto}://{host}"


def _status_payload(request: Request) -> dict[str, Any]:
    base = _public_base(request)
    return {
        "status": "ok",
        "name": "indian-company-registry",
        "transport": "streamable-http",
        "mcp_url": f"{base}{MCP_PATH}",
        "health_url": f"{base}/health",
        "tools": list(TOOL_NAMES),
        "note": (
            "/mcp is a Streamable HTTP MCP endpoint for MCP clients. "
            "Open / or /health in a browser to confirm the server is up."
        ),
    }


def _status_html(request: Request) -> HTMLResponse:
    data = _status_payload(request)
    tools = "".join(
        f"<li><code>{html.escape(name)}</code></li>" for name in data["tools"]
    )
    mcp_url = html.escape(data["mcp_url"])
    health_url = html.escape(data["health_url"])
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📈</text></svg>">
  <title>Indian company registry</title>
  <style>
    body {{ font: 16px/1.45 ui-sans-serif, system-ui, sans-serif; margin: 2rem; color: #1a1a1a; max-width: 42rem; }}
    code {{ background: #f3f3f0; padding: 0.1em 0.35em; }}
    .ok {{ color: #0a7a2f; font-weight: 600; }}
  </style>
</head>
<body>
  <p class="ok">Server is running</p>
  <h1>Indian company registry</h1>
  <p>This is a read-only MCP server, not a website. Use this URL in an MCP client:</p>
  <p><code>{mcp_url}</code></p>
  <p>Health: <a href="{health_url}">{health_url}</a></p>
  <p>Search UI: <a href="/ui">/ui</a></p>
  <h2>Tools</h2>
  <ul>{tools}</ul>
</body>
</html>"""
    )


class BrowserGetMcpMiddleware(BaseHTTPMiddleware):
    """Chrome GET /mcp includes */* and would otherwise hang on an SSE stream."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"
        if path == MCP_PATH and request.method == "GET" and _wants_html(request):
            return _status_html(request)
        return await call_next(request)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> Response:
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> Response:
    if _wants_html(request):
        return _status_html(request)
    return JSONResponse(_status_payload(request))


@mcp.custom_route("/ui", methods=["GET"])
async def web_ui(_request: Request) -> Response:
    """Browser search UI over the registry tools."""
    return HTMLResponse(_UI_HTML)


FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
    "<text y='.9em' font-size='90'>📈</text></svg>"
)


@mcp.custom_route("/favicon.ico", methods=["GET"])
async def favicon(_request: Request) -> Response:
    return Response(FAVICON_SVG, media_type="image/svg+xml")


def create_http_app():
    app = mcp.streamable_http_app(
        streamable_http_path=MCP_PATH,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
        host=LISTEN_HOST,
    )
    app.add_middleware(BrowserGetMcpMiddleware)
    return app


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def main() -> None:
    host = LISTEN_HOST
    port = listen_port()
    # Skip the local occupancy check in production; Railway assigns PORT and
    # a false positive here would exit before uvicorn could bind.
    if os.environ.get("PORT") is None and _port_in_use("127.0.0.1", port):
        raise SystemExit(
            f"Port {port} is already in use. "
            "Stop the other process, then start again with:\n"
            "  python3 src/mcp_server.py"
        )
    import uvicorn

    print(
        f"Company registry MCP listening on http://{host}:{port}{MCP_PATH}",
        file=sys.stderr,
    )
    print(f"Health check: http://{host}:{port}/health", file=sys.stderr)
    # DNS rebinding is off so Railway / tunnel Host headers are accepted.
    # proxy_headers lets / and status URLs see https behind Railway's proxy.
    uvicorn.run(
        create_http_app(),
        host=host,
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
