from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from playwright.sync_api import Error as PlaywrightError

from ..normalization import canonical_property_type, has_card_details, money, parse_item
from .base import SiteAdapter, SourceUnavailable


class LeiloeiroPublicoAdapter(SiteAdapter):
    """Public calendar and lot-list rows from Leiloeiro Público."""

    def _links(self, page, selector: str) -> list[dict[str, str]]:
        links = page.locator(selector).evaluate_all("""anchors => anchors.map(anchor => ({
          href: anchor.href,
          text: (anchor.innerText || anchor.textContent || '').replace(/\\s+/g, ' ').trim()
        }))""")
        unique: dict[str, dict[str, str]] = {}
        for link in links:
            parsed = urlparse(link["href"])
            if (parsed.hostname or "").casefold().removeprefix("www.") != self.config["host"].casefold().removeprefix("www."):
                continue
            if link["href"].split("#", 1)[0] not in unique:
                unique[link["href"].split("#", 1)[0]] = link
        return list(unique.values())

    def _city_context(self, text: str) -> str:
        found = [city for city in self.cities if re.search(rf"\b{re.escape(city)}\b", text, re.I)]
        # A city label is added only when this individual lot text names exactly
        # one configured city. parse_item then treats that as a declared field.
        if len(found) == 1 and not re.search(r"\bCidade\s*:", text, re.I):
            return f"{found[0]}/SC {text}"
        return text

    def _lot_rows(self, page) -> list[dict[str, Any]]:
        rows = page.locator('a[href*="DetalheLote.aspx"][href*="Leilao="][href*="Lote="]').evaluate_all("""anchors => anchors.map(anchor => {
          let row = anchor.closest('tr');
          if (!row) {
            let node = anchor;
            for (let i = 0; i < 7 && node; i++, node = node.parentElement) {
              const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
              if (text.length >= 40 && text.length <= 2200 && node.querySelectorAll('a[href*="DetalheLote.aspx"]').length <= 1) {
                row = node;
                break;
              }
            }
          }
          const text = (row?.innerText || anchor.innerText || anchor.textContent || '').replace(/\\s+/g, ' ').trim();
          const cells = [...(row?.querySelectorAll(':scope > td, :scope > th') || [])].map(cell => (cell.innerText || '').replace(/\\s+/g, ' ').trim());
          const table = row?.closest('table');
          const headerRow = table?.querySelector('thead tr') || [...(table?.querySelectorAll('tr') || [])].find(candidate => candidate.querySelectorAll('th').length);
          const headers = [...(headerRow?.querySelectorAll('th, td') || [])].map(cell => (cell.innerText || '').replace(/\\s+/g, ' ').trim());
          const documents = [...(row?.querySelectorAll('a[href]') || [])].map(link => ({
            href: link.href, text: (link.innerText || link.textContent || '').trim()
          }));
          const images = [...(row?.querySelectorAll('img') || [])].map(img => img.currentSrc || img.dataset.src || img.dataset.original || img.getAttribute('src')).filter(Boolean);
          return {href: anchor.href, text, headers, cells, documents, images};
        })""")
        unique: dict[str, dict[str, Any]] = {}
        expected_host = self.config["host"].casefold().removeprefix("www.")
        for row in rows:
            parsed = urlparse(row["href"])
            if (parsed.hostname or "").casefold().removeprefix("www.") != expected_host:
                continue
            unique.setdefault(row["href"].split("#", 1)[0], row)
        return list(unique.values())

    @staticmethod
    def _column(lot: dict[str, Any], label: str) -> str | None:
        for header, value in zip(lot.get("headers", []), lot.get("cells", [])):
            if re.search(label, header, re.I) and value:
                return value
        return None

    def collect(self, page) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.monotonic()
        pages_read = 0
        errors: list[str] = []
        properties: dict[str, dict[str, Any]] = {}
        by_city = {city: 0 for city in self.cities}

        try:
            self._open(page, self.config["url"])
            pages_read += 1
            event_links = self._links(page, 'a[href*="ListagemLote.aspx"][href*="Leilao="]')
            if not event_links:
                raise SourceUnavailable("Calendário acessível, mas nenhum link público de leilão foi reconhecido.")
        except (SourceUnavailable, PlaywrightError, ValueError) as exception:
            summary = self._summary(started, pages_read, properties, by_city, str(exception))
            return [], summary

        unrecognized_event_lists = 0
        lot_rows: list[dict[str, Any]] = []
        for event in event_links:
            event_url = event["href"].split("#", 1)[0] + "#Lista"
            try:
                self._open(page, event_url)
                pages_read += 1
                event_text = page.locator("body").inner_text(timeout=5000)
                rows = self._lot_rows(page)
                if not rows:
                    if not re.search(r"nenhum(?:a)?\s+lote|sem\s+lotes|n[aã]o\s+h[aá]\s+lotes", event_text, re.I):
                        unrecognized_event_lists += 1
                    continue
                for row in rows:
                    lot_rows.append(row)
            except (SourceUnavailable, PlaywrightError, ValueError) as exception:
                errors.append(f"Leilão {event['href']}: {exception}")

        # All calendar event pages are read before selecting configured cities
        # and property types. Public listing rows provide the declared lot facts;
        # Detail URLs are preserved as official listing links.
        for lot in lot_rows:
            lot_url = lot["href"].split("#", 1)[0]
            combined = self._city_context(lot.get("text", ""))
            captured_at = datetime.now(ZoneInfo(self.timezone)).isoformat(timespec="seconds")
            item = parse_item(self.config, lot_url, combined, self.cities, captured_at)
            non_property_signal = bool(re.search(
                r"\b(?:autom[oó]vel|ve[ií]culo|carro|motocicleta|moto|caminh[aã]o|trator|embarca[cç][aã]o|sucata|maquin[aá]rio)\b",
                combined[:2500], re.I,
            ))
            if item:
                item["property_type"] = canonical_property_type(item, combined)
            if not item or non_property_signal or not item.get("property_type"):
                continue
            query = parse_qs(urlparse(lot_url).query)
            auction_id = (query.get("Leilao") or [None])[0]
            lot_id = (query.get("Lote") or [None])[0]
            sublot_id = (query.get("Sublote") or [None])[0]
            if auction_id and lot_id:
                item["source_listing_ids"] = [f"{auction_id}:{lot_id}:{sublot_id or '1'}"]
                item["auction_lot"] = lot_id
            appraisal = money(self._column(lot, r"avalia[cç][aã]o"))
            minimum_offer = money(self._column(lot, r"oferta\s+m[ií]nima|lance\s+m[ií]nimo"))
            current_offer = money(self._column(lot, r"oferta\s+atual"))
            if appraisal is not None:
                item["appraisal_value_brl"] = appraisal
                item["field_verification"]["appraisal_value_brl"] = "declared"
            if minimum_offer is not None:
                item["current_minimum_bid_brl"] = minimum_offer
                item["field_verification"]["current_minimum_bid_brl"] = "declared"
            if current_offer is not None:
                item["source_listing_price_brl"] = current_offer
                item["field_verification"]["source_listing_price_brl"] = "declared"
            elif not re.search(r"(?:pre[cç]o|valor|lance|oferta)\s*(?:atual|inicial|m[ií]nimo)?\s*[:=]\s*R\$", combined, re.I):
                item["source_listing_price_brl"] = None
                item["field_verification"]["source_listing_price_brl"] = "unknown"
            if appraisal and minimum_offer is not None and appraisal > 0:
                item["discount_on_appraisal_percent"] = round((1 - minimum_offer / appraisal) * 100, 2)
                item["classification"] = "A" if item.get("status") == "active" and minimum_offer <= self.config.get("priority", {}).get("max_bid_brl", 800000) and item["discount_on_appraisal_percent"] >= self.config.get("priority", {}).get("min_discount_percent", 30) else "B"
            else:
                item["discount_on_appraisal_percent"] = None
                item["classification"] = "B"
            item["field_verification"]["first_minimum_bid_brl"] = "unknown"
            item["field_verification"]["second_minimum_bid_brl"] = "unknown"
            if not re.search(r"\b(?:endere[cç]o|localiza[cç][aã]o)\s*:", combined, re.I):
                item["address"] = None
                item["field_verification"]["address"] = "unknown"
            if not re.search(r"\b(?:cart[oó]rio|registro\s+de\s+im[oó]veis|RI)\s*(?:n[º°.]?\s*)?[:#-]", combined, re.I):
                item["registry_office"] = None
                item["field_verification"]["registry_office"] = "unknown"
            item["image_urls"] = [url for url in lot.get("images", []) if url.startswith("https://") and not re.search(r"logo|icon|avatar|banner|pixel|tracking|placeholder", url, re.I)]
            documents = [link["href"] for link in lot.get("documents", []) if re.search(r"edital|matr[ií]cula|documento|\.pdf(?:\?|$)", link.get("text", "") + " " + link["href"], re.I)]
            item["document_urls"] = list(dict.fromkeys(documents))
            item["edital_url"] = next((url for url in documents if "edital" in url.casefold()), None)
            if item["edital_url"]:
                item["field_verification"]["edital_url"] = "verified"
            if not has_card_details(item):
                continue
            properties[item["id"]] = item
            by_city[item["city"]] += 1

        if unrecognized_event_lists:
            errors.append(f"{unrecognized_event_lists} páginas de leilão não expuseram links de lotes reconhecíveis.")
        summary = self._summary(started, pages_read, properties, by_city, "; ".join(errors) if errors else None)
        return list(properties.values()), summary

    def _summary(self, started, pages_read, properties, by_city, error):
        status = "success" if not error else "partial" if pages_read else "failed"
        summary = {
            "source_id": self.config["id"], "name": self.config["name"], "status": status,
            "pages_read": pages_read, "listings_found": len(properties), "error": error,
            "listings_by_city": by_city, "duration_seconds": round(time.monotonic() - started, 2),
        }
        print(json.dumps({"event": "source_result", **summary}, ensure_ascii=False))
        return summary
