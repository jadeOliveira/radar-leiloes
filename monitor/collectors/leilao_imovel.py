from __future__ import annotations

from urllib.parse import quote

from .base import SiteAdapter


class LeilaoImovelAdapter(SiteAdapter):
    """City-specific public result pages from the Leilão Imóvel aggregator."""

    max_pages = 30

    def page_url(self, number: int) -> str:
        template = self.config["url"].replace("{city_slug}", self._city_slug)
        return template.format(page=number)

    @staticmethod
    def city_slug(city: str) -> str:
        return {
            "Joinville": "joinville-sc",
            "Balneário Camboriú": "balneario-camboriu-sc",
            "Balneário Piçarras": "balneario-picarras-sc",
            "Barra Velha": "barra-velha-sc",
            "Rio do Sul": "rio-do-sul-sc",
        }.get(city, f"{quote(city.lower().replace(' ', '-'))}-sc")

    def collect(self, page):
        configured_cities = list(self.cities)
        original_config = self.config
        all_items = {}
        summaries = []
        for city in configured_cities:
            self.cities = [city]
            self._city_slug = self.city_slug(city)
            self.config = {**original_config, "url": original_config["url"].replace("{city_slug}", self._city_slug)}
            items, summary = super().collect(page)
            summaries.append(summary)
            for item in items:
                item["source_listing_url"] = item.get("provenance", {}).get("captured_from")
                item["validation_status"] = "nao_verificado"
                item["auctioneer"] = None
                item["risk_flags"] = list(dict.fromkeys([*(item.get("risk_flags") or []), "aggregator_listing_unverified"]))
                all_items[item["id"]] = item
        self.config = original_config
        self.cities = configured_cities
        failed = [summary for summary in summaries if summary["status"] == "failed"]
        pages = sum(summary["pages_read"] for summary in summaries)
        errors = [f'{summary["name"]}: {summary["error"]}' for summary in failed if summary.get("error")]
        status = "success" if not errors else "partial" if pages else "failed"
        by_city = {city: sum(1 for item in all_items.values() if item["city"] == city) for city in configured_cities}
        error = "; ".join(errors) if errors else None
        summary = {
            "source_id": original_config["id"], "name": original_config["name"], "status": status,
            "pages_read": pages, "listings_found": len(all_items), "error": error,
            "listings_by_city": by_city,
            "duration_seconds": round(sum(summary["duration_seconds"] for summary in summaries), 2),
        }
        return list(all_items.values()), summary

