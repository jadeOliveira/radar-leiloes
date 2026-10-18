from __future__ import annotations

import re
import time
import unicodedata

from .base import SiteAdapter


class HastaAdapter(SiteAdapter):
    """Public results from Hasta, an aggregator that links to auctioneer pages."""

    max_pages = 1

    @staticmethod
    def city_slug(city: str) -> str:
        slug = unicodedata.normalize("NFKD", city).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "-", slug).strip("-")

    def collect(self, page):
        started = time.monotonic()
        original_config = self.config
        configured_cities = list(self.cities)
        all_items = {}
        pages = 0
        errors = []
        by_city = {city: 0 for city in configured_cities}

        for city in configured_cities:
            self.cities = [city]
            self.config = {
                **original_config,
                "url": original_config["url"].replace("{city_slug}", self.city_slug(city)),
            }
            items, result = super().collect(page)
            pages += result["pages_read"]
            if result["status"] == "failed":
                errors.append(f"{city}: {result['error']}")
            for item in items:
                item["source_listing_url"] = item.get("provenance", {}).get("captured_from")
                item["validation_status"] = "nao_verificado"
                item["auctioneer"] = None
                item["risk_flags"] = list(dict.fromkeys([*(item.get("risk_flags") or []), "aggregator_listing_unverified"]))
                all_items[item["id"]] = item
                by_city[city] += 1

        self.config = original_config
        self.cities = configured_cities
        status = "success" if not errors else "partial" if pages else "failed"
        summary = {
            "source_id": original_config["id"], "name": original_config["name"], "status": status,
            "pages_read": pages, "listings_found": len(all_items),
            "error": "; ".join(errors) if errors else None,
            "listings_by_city": by_city, "duration_seconds": round(time.monotonic() - started, 2),
        }
        return list(all_items.values()), summary
