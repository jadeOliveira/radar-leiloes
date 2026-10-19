from __future__ import annotations

import re
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError

from .base import SiteAdapter


class ZampieriAdapter(SiteAdapter):
    """Public auction lot pages published by Zampieri Leiloeiro."""

    max_pages = 30

    def prepare(self, page) -> None:
        # Use the site's public category filter so vehicles and other movable
        # goods are not mixed into the property search.
        property_filter = page.get_by_text("IMÓVEIS", exact=True).last
        if property_filter.count():
            property_filter.click(timeout=3000)
            page.wait_for_timeout(500)

    def _read_cards(self, page) -> list[dict[str, str]]:
        candidates = page.evaluate(r"""() => {
          const locality = /\bSC\b/i;
          const property = /\b(im[oó]vel|casa|apartamento|terreno|lote)\b/i;
          const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')];
          const found = [];
          headings.forEach((heading, index) => {
            const title = (heading.innerText || '').replace(/\s+/g, ' ').trim();
            if (!property.test(title)) return;
            let node = heading;
            for (let depth = 0; depth < 7 && node; depth++, node = node.parentElement) {
              const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
              if (text.length > 30 && text.length < 2500 && locality.test(text) && /R\$/.test(text)) {
                found.push({title, text, index});
                break;
              }
            }
          });
          return found;
        }""")
        list_url = page.url
        cards: dict[str, dict[str, str]] = {}
        for candidate in candidates:
            try:
                page.locator("h1,h2,h3,h4,h5,h6").nth(candidate["index"]).click(timeout=3000)
                page.wait_for_timeout(350)
                href = page.url
                if href != list_url and self.link_matches(href) and self.host_matches(href):
                    cards.setdefault(href.split("#")[0], {"href": href, "text": candidate["text"]})
            except PlaywrightError:
                pass
            finally:
                if page.url != list_url:
                    try:
                        page.go_back(wait_until="domcontentloaded", timeout=self.timeout_ms)
                        page.wait_for_timeout(500)
                    except PlaywrightError:
                        page.goto(list_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                        page.wait_for_timeout(900)
        return list(cards.values())
