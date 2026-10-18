from __future__ import annotations

import time

from .base import SiteAdapter


class NucleoLeiloesAdapter(SiteAdapter):
    """Public preview listings from Núcleo Leilões, an auction aggregator."""

    max_pages = 1
    CITY_IDS = {
        "Joinville": ("4551", "joinville-sc"),
        "Balneário Camboriú": ("4442", "balneario-camboriu-sc"),
        "Barra Velha": ("4446", "barra-velha-sc"),
        "Rio do Sul": ("4630", "rio-do-sul-sc"),
    }

    def collect(self, page):
        started = time.monotonic()
        original_config = self.config
        configured_cities = list(self.cities)
        all_items = {}
        pages = 0
        errors = []
        by_city = {city: 0 for city in configured_cities}

        for city in configured_cities:
            location = self.CITY_IDS.get(city)
            if location is None:
                errors.append(f"{city}: página pública da cidade ainda não identificada.")
                continue
            city_id, city_slug = location
            self.cities = [city]
            self.config = {
                **original_config,
                "url": original_config["url"].replace("{city_id}", city_id).replace("{city_slug}", city_slug),
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
