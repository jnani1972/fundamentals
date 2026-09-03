import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcp_server import mcp  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _payload(result):
    data = result.structured_content
    if data is None and result.content:
        data = json.loads(result.content[0].text)
    if isinstance(data, dict) and set(data) == {"result"}:
        return data["result"]
    return data


@pytest.mark.anyio
async def test_mcp_tools_are_read_only_lookups():
    from mcp import Client

    async with Client(mcp, raise_exceptions=True) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools >= {
            "get_company_by_symbol",
            "search_companies",
            "get_sectors",
            "get_companies_by_sector",
            "get_official_x_handle",
            "get_official_x_handles_by_sector",
            "get_defence_research_universe",
        }

        sectors = _payload(await client.call_tool("get_sectors", {}))
        assert "Aerospace & Defence" in sectors
        assert sectors == sorted(sectors)

        company = _payload(
            await client.call_tool("get_company_by_symbol", {"symbol": "hal"})
        )
        assert company["nse_symbol"] == "HAL"
        assert company["company_name"] == "Hindustan Aeronautics Limited"

        missing = _payload(
            await client.call_tool("get_company_by_symbol", {"symbol": "NOPE"})
        )
        assert missing is None

        matches = _payload(await client.call_tool("search_companies", {"query": "MDL"}))
        assert [row["nse_symbol"] for row in matches] == ["MAZDOCK"]

        shipyards = _payload(
            await client.call_tool("get_companies_by_sector", {"sector": "ship building"})
        )
        assert {row["nse_symbol"] for row in shipyards} == {"MAZDOCK", "GRSE", "COCHINSHIP"}

        handle = _payload(
            await client.call_tool("get_official_x_handle", {"symbol": "BEL"})
        )
        assert handle == "@BEL_CorpCom"

        null_handle = _payload(
            await client.call_tool("get_official_x_handle", {"symbol": "ZENTEC"})
        )
        assert null_handle is None

        sector_handles = _payload(
            await client.call_tool(
                "get_official_x_handles_by_sector",
                {"sector": "Ship Building"},
            )
        )
        assert sector_handles == [
            {
                "company_name": "Cochin Shipyard Limited",
                "nse_symbol": "COCHINSHIP",
                "official_x_handle": "@cslcochin",
            }
        ]

        universe = _payload(await client.call_tool("get_defence_research_universe", {}))
        assert len(universe["companies"]) == 18
        without = universe["companies_without_verified_official_x_account"]
        without_symbols = {row["nse_symbol"] for row in without}
        assert "ZENTEC" in without_symbols
        assert "HAL" not in without_symbols
        assert all(set(row) == {"company_name", "nse_symbol"} for row in without)


def test_health_endpoint():
    from starlette.testclient import TestClient

    from mcp_server import create_http_app

    app = create_http_app()
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        root = client.get("/")
        assert root.status_code == 200
        body = root.json()
        assert body["status"] == "ok"
        assert "get_company_by_symbol" in body["tools"]
        assert body["mcp_url"].endswith("/mcp")


def test_browser_get_does_not_hang_on_mcp():
    from starlette.testclient import TestClient

    from mcp_server import create_http_app

    chrome_accept = (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    )
    app = create_http_app()
    with TestClient(app) as client:
        root = client.get("/", headers={"Accept": chrome_accept})
        assert root.status_code == 200
        assert "text/html" in root.headers["content-type"]
        assert "Server is running" in root.text

        mcp_page = client.get("/mcp", headers={"Accept": chrome_accept})
        assert mcp_page.status_code == 200
        assert "text/html" in mcp_page.headers["content-type"]
        assert "Use this URL in an MCP client" in mcp_page.text

        init = client.post(
            "/mcp",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
        )
        assert init.status_code == 200
        assert init.json()["result"]["serverInfo"]["name"] == "indian-company-registry"


def test_web_ui_serves_search_page():
    from starlette.testclient import TestClient

    from mcp_server import create_http_app

    app = create_http_app()
    with TestClient(app) as client:
        page = client.get("/ui")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assert "search-form" in page.text
        assert "rel=\"icon\"" in page.text
        assert "{ {" not in page.text  # template braces must not leak into HTML

        favicon = client.get("/favicon.ico")
        assert favicon.status_code == 200
        assert "image/svg+xml" in favicon.headers["content-type"]


def test_listen_port_uses_railway_port_or_local_fallback(monkeypatch):
    from mcp_server import DEFAULT_PORT, LISTEN_HOST, listen_port

    assert LISTEN_HOST == "0.0.0.0"
    assert DEFAULT_PORT == 3001

    monkeypatch.delenv("PORT", raising=False)
    assert listen_port() == 3001

    monkeypatch.setenv("PORT", "8080")
    assert listen_port() == 8080
