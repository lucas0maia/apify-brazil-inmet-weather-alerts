# Brazil INMET Severe Weather Alerts & Agro/Insurance Risk (`apify-brazil-inmet-weather-alerts`)

Monitor real-time severe weather advisories across Brazil directly from **INMET (Instituto Nacional de Meteorologia)** (`apiprevmet3.inmet.gov.br/avisos/ativos`), including official GeoJSON warning polygons, 7-digit IBGE municipality codes, risk summaries, and Civil Defense instructions.

## Use Cases

- **Agribusiness & Precision Farming:** Trigger automated Telegram/Webhook/ERP alerts when `Tempestade`, `Geada`, `Onda de Calor`, or `Chuvas Intensas` enter target IBGE municipalities.
- **Parametric Insurance & Energy Utilities:** Cross-check substation, crop, or fleet coordinates against live GeoJSON polygons (`Perigo Potencial`, `Perigo`, `Grande Perigo`).
- **Logistics & Supply Chain Routing:** Filter active and upcoming (`hoje` + `futuro`) severe weather corridors by state (`uf`) or municipality.

## Example Input

```json
{
  "mode": "alerts_by_state",
  "uf": "SP",
  "severityFilter": "all",
  "includePolygons": true
}
```

## MCP & Standby Ready

Runs as an Apify batch Actor, Standby HTTP endpoint (`GET /`, `GET /health`, `POST /`), or **MCP Server** (`POST /mcp`, tool `query_brazil_inmet_alerts`).
