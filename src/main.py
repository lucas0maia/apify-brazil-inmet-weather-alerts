"""Apify Actor & Standby MCP Server for Brazil INMET Severe Weather Alerts."""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable

try:
    from aiohttp import web
    from apify import Actor
except ImportError:
    web = None  # type: ignore[assignment]
    Actor = None  # type: ignore[assignment]

EVENT_NAME = "record-delivered"
INMET_ACTIVE_URL = "https://apiprevmet3.inmet.gov.br/avisos/ativos"
MUNICIPALITY_RE = re.compile(r"([^,]+?)\s*-\s*([A-Z]{2})\s*\((\d{7})\)")

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "query_brazil_inmet_alerts",
        "description": (
            "Query real-time severe weather alerts across Brazil from INMET (hoje and futuro), "
            "filtered by UF state, municipality name, 7-digit IBGE code, or severity level, with GeoJSON polygons."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["active_alerts", "alerts_by_state", "alerts_by_municipality"],
                },
                "uf": {"type": "string", "default": ""},
                "query": {"type": "string", "default": ""},
                "ibgeCode": {"type": "string", "default": ""},
                "severityFilter": {
                    "type": "string",
                    "enum": ["all", "Perigo Potencial", "Perigo", "Grande Perigo"],
                    "default": "all",
                },
                "includePolygons": {"type": "boolean", "default": True},
                "includeAllMunicipalities": {"type": "boolean", "default": False},
                "maxResults": {"type": "integer", "default": 50},
                "timeoutSecs": {"type": "integer", "default": 30},
            },
            "required": ["mode"],
        },
    }
]


def http_get_json(url: str, timeout: int = 30) -> Any:
    """Fetch JSON from INMET with Mozilla User-Agent and a single retry on peer reset."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; apify-brazil-inmet/1.0)",
            "Accept": "application/json",
            "Connection": "close",
        },
    )
    last_err: Exception | None = None
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (ConnectionResetError, urllib.error.URLError) as exc:
            last_err = exc
    if last_err is not None:
        raise last_err
    return {}


def _parse_municipalities(raw_text: str) -> tuple[list[dict[str, str]], list[str]]:
    parsed: list[dict[str, str]] = []
    ufs: set[str] = set()
    for match in MUNICIPALITY_RE.finditer(raw_text or ""):
        name, uf, ibge_code = match.group(1).strip(), match.group(2).strip(), match.group(3).strip()
        ufs.add(uf)
        parsed.append({"name": name, "uf": uf, "ibgeCode": ibge_code})
    return parsed, sorted(ufs)


def _parse_polygon(raw_polygon: Any) -> Any:
    if isinstance(raw_polygon, dict):
        return raw_polygon
    if isinstance(raw_polygon, str) and raw_polygon.strip().startswith("{"):
        try:
            return json.loads(raw_polygon)
        except json.JSONDecodeError:
            return None
    return None


def fetch_inmet_alerts(
    mode: str = "active_alerts",
    uf: str = "",
    query: str = "",
    ibge_code: str = "",
    severity_filter: str = "all",
    include_polygons: bool = True,
    include_all_municipalities: bool = False,
    max_results: int = 50,
    timeout: int = 30,
    fetcher: Callable[[str, int], Any] = http_get_json,
) -> list[dict[str, Any]]:
    """Fetch and filter INMET active weather alerts across hoje and futuro windows."""
    cap = max(1, min(int(max_results), 500))
    payload = fetcher(INMET_ACTIVE_URL, timeout)
    if not isinstance(payload, dict):
        return []

    uf_clean = (uf or "").strip().upper()
    needle = (query or "").strip().lower()
    ibge_clean = "".join(ch for ch in (ibge_code or "") if ch.isdigit())
    sev_clean = (severity_filter or "all").strip().lower()

    results: list[dict[str, Any]] = []
    for horizon in ("hoje", "futuro"):
        raw_list = payload.get(horizon) or []
        if not isinstance(raw_list, list):
            continue
        for item in raw_list:
            severity = str(item.get("severidade") or "").strip()
            if sev_clean != "all" and severity.lower() != sev_clean:
                continue

            muni_raw = str(item.get("municipios") or "")
            parsed_cities, parsed_ufs = _parse_municipalities(muni_raw)
            geocodes_raw = str(item.get("geocodes") or "")
            geocode_list = [g.strip() for g in geocodes_raw.split(",") if g.strip()]

            if uf_clean and uf_clean not in parsed_ufs:
                continue
            if ibge_clean and ibge_clean not in geocode_list:
                continue

            desc = str(item.get("descricao") or "")
            states_str = str(item.get("estados") or "")
            if needle:
                in_cities = [c for c in parsed_cities if needle in c["name"].lower()]
                if not in_cities and needle not in desc.lower() and needle not in states_str.lower():
                    continue
            else:
                in_cities = [c for c in parsed_cities if (not uf_clean or c["uf"] == uf_clean) and (not ibge_clean or c["ibgeCode"] == ibge_clean)]

            record: dict[str, Any] = {
                "recordType": mode,
                "horizon": horizon,
                "alertId": item.get("id"),
                "avisoId": item.get("id_aviso"),
                "alertCode": str(item.get("codigo") or ""),
                "description": desc,
                "severity": severity,
                "severityId": item.get("id_severidade"),
                "colorHex": str(item.get("aviso_cor") or ""),
                "startsAt": str(item.get("inicio") or item.get("data_inicio") or ""),
                "endsAt": str(item.get("fim") or item.get("data_fim") or ""),
                "affectedUfs": parsed_ufs,
                "statesSummary": states_str,
                "regionsSummary": str(item.get("regioes") or ""),
                "affectedMunicipalitiesCount": len(parsed_cities) or len(geocode_list),
                "matchedMunicipalities": (in_cities[:50] if not include_all_municipalities else in_cities),
                "sampleMunicipalities": parsed_cities[:10],
                "risks": item.get("riscos") or [],
                "instructions": item.get("instrucoes") or [],
                "sourceUrl": INMET_ACTIVE_URL,
            }
            if include_all_municipalities:
                record["allMunicipalities"] = parsed_cities
            if include_polygons:
                record["polygonGeoJson"] = _parse_polygon(item.get("poligono"))

            results.append(record)
            if len(results) >= cap:
                return results
    return results


def run_query(
    params: dict[str, Any],
    fetcher: Callable[[str, int], Any] = http_get_json,
) -> list[dict[str, Any]]:
    """Route Actor input or MCP tool calls cleanly to INMET alerts fetcher."""
    mode = str(params.get("mode") or "active_alerts").strip().lower()
    if mode not in {"active_alerts", "alerts_by_state", "alerts_by_municipality"}:
        raise ValueError(f"Unsupported mode: {mode}")
    return fetch_inmet_alerts(
        mode=mode,
        uf=str(params.get("uf") or ""),
        query=str(params.get("query") or ""),
        ibge_code=str(params.get("ibgeCode") or ""),
        severity_filter=str(params.get("severityFilter") or "all"),
        include_polygons=bool(params.get("includePolygons", True)),
        include_all_municipalities=bool(params.get("includeAllMunicipalities", False)),
        max_results=int(params.get("maxResults") or 50),
        timeout=max(5, min(int(params.get("timeoutSecs") or 30), 60)),
        fetcher=fetcher,
    )


async def _charge_records(count: int) -> int:
    if count <= 0:
        return 0
    max_items_env = os.environ.get("ACTOR_MAX_PAID_DATASET_ITEMS")
    allowed = min(count, int(max_items_env)) if max_items_env and max_items_env.isdigit() else count
    if allowed <= 0:
        return 0
    try:
        res = await Actor.charge(event_name=EVENT_NAME, count=allowed)
        if hasattr(res, "event_charge_limit_reached") and res.event_charge_limit_reached:
            Actor.log.warning("Pay-per-event limit reached on %s.", EVENT_NAME)
    except Exception as exc:
        Actor.log.warning("Charge skipped in local/non-monetized mode: %s", exc)
    return allowed


async def _handle_mcp_rpc(payload: dict[str, Any]) -> dict[str, Any]:
    rpc_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "apify-brazil-inmet-weather-alerts", "version": "0.0.1"},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": MCP_TOOLS}}
    if method == "tools/call":
        if params.get("name") != "query_brazil_inmet_alerts":
            return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": "Unknown tool"}}
        rows = await asyncio.to_thread(run_query, params.get("arguments") or {})
        await _charge_records(len(rows))
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"content": [{"type": "text", "text": json.dumps(rows, ensure_ascii=False)}]},
        }
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Unsupported method: {method}"}}


async def _run_standby_server() -> None:
    port = int(os.environ.get("ACTOR_STANDBY_PORT", "8080"))

    async def handle_health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "actor": "apify-brazil-inmet-weather-alerts"})

    async def handle_root(request: web.Request) -> web.Response:
        if request.headers.get("x-apify-container-server-readiness-probe"):
            return web.Response(text="OK", status=200)
        args = {
            "mode": request.query.get("mode", "active_alerts"),
            "uf": request.query.get("uf", ""),
            "query": request.query.get("query", ""),
            "ibgeCode": request.query.get("ibgeCode", ""),
            "severityFilter": request.query.get("severityFilter", "all"),
            "includePolygons": request.query.get("includePolygons", "true").lower() != "false",
            "maxResults": int(request.query.get("maxResults", "50")),
        }
        rows = await asyncio.to_thread(run_query, args)
        await _charge_records(len(rows))
        return web.json_response({"count": len(rows), "items": rows})

    async def handle_post(request: web.Request) -> web.Response:
        payload = await request.json()
        if isinstance(payload, dict) and payload.get("jsonrpc") == "2.0":
            return web.json_response(await _handle_mcp_rpc(payload))
        rows = await asyncio.to_thread(run_query, payload if isinstance(payload, dict) else {})
        await _charge_records(len(rows))
        return web.json_response({"count": len(rows), "items": rows})

    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_root)
    app.router.add_post("/", handle_post)
    app.router.add_post("/mcp", handle_post)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    Actor.log.info("Brazil INMET Weather Alerts Standby HTTP/MCP server listening on port %s", port)
    await asyncio.Event().wait()


async def main() -> None:
    if Actor is None:
        raise RuntimeError("apify package is required to run Actor.main()")
    async with Actor:
        if os.environ.get("APIFY_META_ORIGIN") == "STANDBY":
            await _run_standby_server()
            return
        actor_input = await Actor.get_input() or {}
        rows = await asyncio.to_thread(run_query, actor_input)
        allowed = await _charge_records(len(rows))
        to_push = rows[:allowed] if allowed else []
        if to_push:
            await Actor.push_data(to_push)
        Actor.log.info("Delivered %d INMET weather alert records.", len(to_push))


if __name__ == "__main__":
    asyncio.run(main())
