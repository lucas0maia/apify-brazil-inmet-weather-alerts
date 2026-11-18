"""Unit tests for Brazil INMET Severe Weather Alerts Actor."""

import json
import unittest

from src.main import fetch_inmet_alerts, run_query

SAMPLE_INMET_PAYLOAD = {
    "hoje": [
        {
            "id": 56443,
            "id_aviso": 28724,
            "codigo": "urn:oid:2.49.0.0.76.0.2026.28724.1",
            "inicio": "2026-11-18 09:00",
            "fim": "2026-11-18 23:59",
            "descricao": "Tempestade",
            "aviso_cor": "#FFFE00",
            "id_severidade": 6,
            "severidade": "Perigo Potencial",
            "estados": "São Paulo,Minas Gerais",
            "regioes": "Sudeste",
            "municipios": "São Paulo - SP (3550308),Campinas - SP (3509502),Uberaba - MG (3170107)",
            "geocodes": "3550308,3509502,3170107",
            "poligono": json.dumps({"type": "Polygon", "coordinates": [[[-46.6, -23.5], [-47.0, -22.9]]]}),
            "icone": "data:image/png;base64,AAA...",
            "riscos": ["Chuva entre 20 e 30 mm/h"],
            "instrucoes": ["Evite usar aparelhos eletrônicos"],
        }
    ],
    "futuro": [
        {
            "id": 56449,
            "id_aviso": 28730,
            "codigo": "urn:oid:2.49.0.0.76.0.2026.28730.1",
            "inicio": "2026-11-19 06:00",
            "fim": "2026-11-19 20:00",
            "descricao": "Chuvas Intensas",
            "aviso_cor": "#FFA500",
            "id_severidade": 7,
            "severidade": "Perigo",
            "estados": "Alagoas,Pernambuco",
            "regioes": "Nordeste",
            "municipios": "Maceió - AL (2704302),Recife - PE (2611606)",
            "geocodes": "2704302,2611606",
            "poligono": json.dumps({"type": "Polygon", "coordinates": [[[-35.7, -9.6], [-34.8, -8.0]]]}),
            "riscos": ["Risco de alagamentos"],
            "instrucoes": ["Acione a Defesa Civil"],
        }
    ],
}


class TestInmetActor(unittest.TestCase):
    def test_normalization_across_hoje_and_futuro(self) -> None:
        rows = fetch_inmet_alerts(fetcher=lambda _u, _t: SAMPLE_INMET_PAYLOAD)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["horizon"], "hoje")
        self.assertEqual(rows[1]["horizon"], "futuro")
        self.assertNotIn("icone", rows[0])
        self.assertEqual(rows[0]["polygonGeoJson"]["type"], "Polygon")

    def test_filter_by_state_uf(self) -> None:
        rows = run_query(
            {"mode": "alerts_by_state", "uf": "AL"},
            fetcher=lambda _u, _t: SAMPLE_INMET_PAYLOAD,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Chuvas Intensas")
        self.assertEqual(rows[0]["affectedUfs"], ["AL", "PE"])

    def test_filter_by_municipality_and_ibge_code(self) -> None:
        rows = run_query(
            {"mode": "alerts_by_municipality", "ibgeCode": "2704302", "query": "maceió"},
            fetcher=lambda _u, _t: SAMPLE_INMET_PAYLOAD,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["matchedMunicipalities"][0]["name"], "Maceió")
        self.assertEqual(rows[0]["matchedMunicipalities"][0]["ibgeCode"], "2704302")

    def test_filter_by_severity(self) -> None:
        rows = fetch_inmet_alerts(
            severity_filter="Perigo",
            include_polygons=False,
            fetcher=lambda _u, _t: SAMPLE_INMET_PAYLOAD,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "Perigo")
        self.assertNotIn("polygonGeoJson", rows[0])


if __name__ == "__main__":
    unittest.main()
