import unittest

from monitor.normalization import fold, money, parse_item


SOURCE = {
    "id": "example", "name": "Fonte oficial", "host": "leiloes.example.br"
}
CITIES = ["Joinville", "Balneário Camboriú", "Balneário Piçarras", "Barra Velha", "Rio do Sul"]


class NormalizationTests(unittest.TestCase):
    def test_normalizes_city_accents_and_currency(self):
        self.assertEqual(fold("Balneário Piçarras"), "balneario picarras")
        self.assertEqual(money("R$ 1.234.567,89"), 1234567.89)

    def test_does_not_infer_appraisal_or_discount_from_two_auction_bids(self):
        text = "Casa em Joinville/SC. 1º leilão R$ 500.000,00 02/12/2026 às 10:00. 2º leilão R$ 350.000,00 09/12/2026 às 10:00. Aberto para lances."
        item = parse_item(SOURCE, "https://leiloes.example.br/imovel/abc", text, CITIES, "2026-10-17T08:00:00-03:00")
        self.assertIsNotNone(item)
        self.assertEqual(item["first_minimum_bid_brl"], 500000.0)
        self.assertEqual(item["second_minimum_bid_brl"], 350000.0)
        self.assertIsNone(item["appraisal_value_brl"])
        self.assertIsNone(item["discount_on_appraisal_percent"])
        self.assertEqual(item["classification"], "B")

    def test_only_accepts_configured_target_cities(self):
        text = "Apartamento em Itajaí/SC. Lance inicial R$ 300.000,00."
        self.assertIsNone(parse_item(SOURCE, "https://leiloes.example.br/imovel/abc", text, CITIES, "2026-10-17T08:00:00-03:00"))

    def test_same_address_from_two_sources_uses_same_identity(self):
        text = "Casa Joinville/SC - Itinga Rua José Machado Pereira, 121. Lance inicial R$ 520.000,00."
        first = parse_item(SOURCE, "https://leiloes.example.br/imovel/abc", text, CITIES, "2026-10-17T08:00:00-03:00")
        second_source = {**SOURCE, "id": "another-source"}
        second = parse_item(second_source, "https://leiloes.example.br/imovel/different", text, CITIES, "2026-10-17T08:00:00-03:00")
        self.assertEqual(first["id"], second["id"])

    def test_computes_discount_only_from_labeled_appraisal(self):
        text = "Terreno em Rio do Sul/SC. Avaliação: R$ 1.000.000,00. Lance mínimo 2º leilão: R$ 600.000,00. 20/11/2026. Aberto para lances."
        item = parse_item(SOURCE, "https://leiloes.example.br/imovel/xyz", text, CITIES, "2026-10-17T08:00:00-03:00")
        self.assertEqual(item["appraisal_value_brl"], 1000000.0)
        self.assertEqual(item["current_minimum_bid_brl"], 600000.0)
        self.assertEqual(item["discount_on_appraisal_percent"], 40.0)
        self.assertEqual(item["classification"], "A")


if __name__ == "__main__":
    unittest.main()
