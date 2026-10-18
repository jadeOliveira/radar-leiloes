import unittest

from monitor.normalization import fold, identity_keys, money, parse_item


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

    def test_normalizes_occupancy_values_for_dashboard_filters(self):
        occupied = parse_item(SOURCE, "https://leiloes.example.br/imovel/occ", "Apartamento Joinville/SC. Imóvel ocupado.", CITIES, "2026-10-17T08:00:00-03:00")
        vacant = parse_item(SOURCE, "https://leiloes.example.br/imovel/vac", "Terreno Joinville/SC. Imóvel desocupado.", CITIES, "2026-10-17T08:00:00-03:00")
        self.assertEqual(occupied["occupancy"], "ocupado")
        self.assertEqual(vacant["occupancy"], "desocupado")

    def test_only_accepts_configured_target_cities(self):
        text = "Apartamento em Itajaí/SC. Lance inicial R$ 300.000,00."
        self.assertIsNone(parse_item(SOURCE, "https://leiloes.example.br/imovel/abc", text, CITIES, "2026-10-17T08:00:00-03:00"))

    def test_same_address_from_two_sources_uses_same_identity(self):
        text = "Casa Joinville/SC - Itinga Rua José Machado Pereira, 121. Lance inicial R$ 520.000,00."
        first = parse_item(SOURCE, "https://leiloes.example.br/imovel/abc", text, CITIES, "2026-10-17T08:00:00-03:00")
        second_source = {**SOURCE, "id": "another-source"}
        second = parse_item(second_source, "https://leiloes.example.br/imovel/different", text, CITIES, "2026-10-17T08:00:00-03:00")
        self.assertEqual(first["id"], second["id"])

    def test_identity_aliases_match_before_and_after_registry_is_discovered(self):
        without_registry = {"id": "old", "source_ids": ["one"], "city": "Joinville", "address": "Rua Mozart, 358, Floresta, Joinville, SC"}
        with_registry = {**without_registry, "id": "new", "registry_number": "64.044"}
        self.assertTrue(set(identity_keys(without_registry)) & set(identity_keys(with_registry)))

    def test_rejects_page_text_when_first_listing_is_outside_target_cities(self):
        text = "Rio de Janeiro-RJ. Bairro Inhoaíba. Rua das Flores, 10. Outros anúncios: Joinville/SC - Rua A, 1."
        item = parse_item(SOURCE, "https://leiloes.example.br/imovel/abc", text, CITIES, "2026-10-17T08:00:00-03:00")
        self.assertIsNone(item)

    def test_reads_city_from_explicit_state_marker(self):
        text = "Apartamento 67 m² Joinville/SC - Santo Antônio Rua João Vogelsanger, 325. Lance inicial R$ 369.381,91."
        item = parse_item(SOURCE, "https://leiloes.example.br/imovel/abc", text, CITIES, "2026-10-17T08:00:00-03:00")
        self.assertEqual(item["city"], "Joinville")
        self.assertIn("Rua João Vogelsanger", item["address"])

    def test_parses_labeled_address_and_value_initial_from_details(self):
        text = "Terreno 391 m² - Floresta - Joinville - SC. X130445 Joinville, SC. ABERTO PARA LANCES. Data: 20/10/2026 às 13:05 R$ 260.000,00. Valor inicial R$ 260.000,00. Valor de Avaliação R$ 342.000,00. Localização: Rua Mozart, 358, Floresta, Joinville, SC. Matrícula(s): 64.044. Edital anexado."
        item = parse_item(SOURCE, "https://leiloes.example.br/imoveis/terrenos/x", text, CITIES, "2026-10-17T08:00:00-03:00")
        self.assertEqual(item["address"], "Rua Mozart, 358, Floresta, Joinville, SC.")
        self.assertEqual(item["current_minimum_bid_brl"], 260000.0)
        self.assertEqual(item["appraisal_value_brl"], 342000.0)
        self.assertEqual(item["registry_number"], "64.044")

    def test_computes_discount_only_from_labeled_appraisal(self):
        text = "Terreno em Rio do Sul/SC. Avaliação: R$ 1.000.000,00. Lance mínimo 2º leilão: R$ 600.000,00. 20/11/2026. Aberto para lances."
        item = parse_item(SOURCE, "https://leiloes.example.br/imovel/xyz", text, CITIES, "2026-10-17T08:00:00-03:00")
        self.assertEqual(item["appraisal_value_brl"], 1000000.0)
        self.assertEqual(item["current_minimum_bid_brl"], 600000.0)
        self.assertEqual(item["discount_on_appraisal_percent"], 40.0)
        self.assertEqual(item["classification"], "A")


if __name__ == "__main__":
    unittest.main()
