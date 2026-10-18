import unittest

from monitor.run import merge_property


class MergePropertyTests(unittest.TestCase):
    def test_verified_active_listing_survives_unverified_aggregator_refresh(self):
        official_url = "https://www.portalzuk.com.br/imovel/sc/rio-do-sul/centro/avenida-oscar-barcelos-1977/37735-236051"
        old = {
            "id": "e2e0be6a8b341369956c",
            "source_ids": ["hasta", "portalzuk"],
            "status": "active",
            "validation_status": "verified",
            "official_url": official_url,
            "first_minimum_bid_brl": 1157300.0,
            "second_minimum_bid_brl": 578650.0,
            "current_minimum_bid_brl": 578650.0,
            "classification": "A",
            "field_verification": {
                "status": "verified", "official_url": "verified",
                "first_minimum_bid_brl": "verified",
                "second_minimum_bid_brl": "verified",
                "current_minimum_bid_brl": "verified",
            },
        }
        aggregator = {
            "id": old["id"], "source_ids": ["hasta"],
            "status": "scheduled_unverified",
            "validation_status": "nao_verificado",
            "official_url": None,
            "first_minimum_bid_brl": None,
            "second_minimum_bid_brl": None,
            "current_minimum_bid_brl": 1157300.0,
            "classification": "B",
            "field_verification": {
                "status": "declared", "official_url": "unverified",
                "first_minimum_bid_brl": "unknown",
                "second_minimum_bid_brl": "unknown",
                "current_minimum_bid_brl": "declared",
            },
            "provenance": {"source_id": "hasta", "is_aggregator": True},
        }

        merged, _ = merge_property(old, aggregator)

        self.assertEqual(merged["status"], "active")
        self.assertEqual(merged["validation_status"], "verified")
        self.assertEqual(merged["official_url"], official_url)
        self.assertEqual(merged["first_minimum_bid_brl"], 1157300.0)
        self.assertEqual(merged["second_minimum_bid_brl"], 578650.0)
        self.assertEqual(merged["current_minimum_bid_brl"], 578650.0)
        self.assertEqual(merged["classification"], "A")

    def test_verified_active_listing_can_be_marked_ended_by_aggregator_after_auction(self):
        old = {
            "id": "item", "source_ids": ["hasta", "portalzuk"],
            "status": "active", "validation_status": "verified",
            "classification": "A",
        }
        aggregator = {
            "id": "item", "source_ids": ["hasta"],
            "status": "ended_unverified", "validation_status": "nao_verificado",
            "classification": "B",
            "provenance": {"source_id": "hasta", "is_aggregator": True},
        }

        merged, _ = merge_property(old, aggregator)

        self.assertEqual(merged["status"], "ended_unverified")
        self.assertEqual(merged["classification"], "B")


if __name__ == "__main__":
    unittest.main()
