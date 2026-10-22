import unittest

from monitor.collectors.base import SiteAdapter


class FakePage:
    url = ""

    class Body:
        @staticmethod
        def inner_text(timeout=None):
            return "Resultados públicos de imóveis"

    def locator(self, selector):
        return self.Body()


class CollectorPaginationTests(unittest.TestCase):
    def test_city_filter_does_not_stop_pagination_before_target_city_is_found(self):
        adapter = SiteAdapter(
            {
                "id": "example",
                "name": "Example",
                "url": "https://example.test/imoveis?page={page}",
                "host": "example.test",
                "path_pattern": "/imovel/",
                "priority": {"max_bid_brl": 800000, "min_discount_percent": 30},
                "skip_detail": True,
            },
            ["Joinville"],
            "America/Sao_Paulo",
        )
        page = FakePage()
        cards_by_page = {
            1: [{"href": "https://example.test/imovel/outside", "text": "Casa em Itajaí/SC R$ 100.000"}],
            2: [{"href": "https://example.test/imovel/outside", "text": "Casa em Itajaí/SC R$ 100.000"}],
            3: [{"href": "https://example.test/imovel/target", "text": "Casa em Joinville/SC R$ 100.000"}],
            4: [],
        }

        adapter._open = lambda current_page, url: setattr(current_page, "url", url)
        adapter._load_more = lambda current_page: None
        adapter._read_cards = lambda current_page: cards_by_page[int(current_page.url.rsplit("=", 1)[1])]
        adapter._next_page_url = lambda current_page: None

        properties, result = adapter.collect(page)

        self.assertEqual(result["pages_read"], 3)
        self.assertEqual([item["city"] for item in properties], ["Joinville"])


if __name__ == "__main__":
    unittest.main()
