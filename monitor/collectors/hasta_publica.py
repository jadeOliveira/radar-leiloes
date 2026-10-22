from __future__ import annotations

import re

from .base import SiteAdapter


class HastaPublicaAdapter(SiteAdapter):
    """Public property lots from Hasta Pública Leilões."""

    def page_url(self, number: int) -> str:
        base_url = self.config["url"]
        if number == 1:
            return base_url
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}page_a={number}"

    def collect(self, page):
        items, summary = super().collect(page)
        for item in items:
            raw_text = item.get("provenance", {}).get("raw_text", "")
            if not re.search(r"\b(?:endere[cç]o|localiza[cç][aã]o)\s*:", raw_text, re.I):
                item["address"] = None
                item["field_verification"]["address"] = "unknown"
            if not re.search(r"\b(?:cart[oó]rio|registro\s+de\s+im[oó]veis|RI)\s*(?:n[º°.]?\s*)?[:#-]", raw_text, re.I):
                item["registry_office"] = None
                item["field_verification"]["registry_office"] = "unknown"
        return items, summary
