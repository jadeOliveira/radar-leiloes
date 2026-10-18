from __future__ import annotations

import re
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError

from .base import SiteAdapter


class SampaioAdapter(SiteAdapter):
    """Public property listings rendered as clickable cards in Sampaio's Angular app."""

    max_pages = 30

    def _read_cards(self, page) -> list[dict[str, str]]:
        candidates = page.evaluate(r"""({cities}) => {
          const cityPattern = new RegExp('(?:' + cities.join('|') + ')\\s*(?:/|-|,)\\s*SC\\b', 'i');
          const propertyPattern = /\b(casa|apartamento|terreno|lote)\b/i;
          const found = [];
          for (const heading of document.querySelectorAll('h1,h2,h3,h4,h5,h6')) {
            const title = (heading.innerText || '').replace(/\s+/g, ' ').trim();
            if (!propertyPattern.test(title)) continue;
            let node = heading;
            for (let depth = 0; depth < 8 && node; depth++, node = node.parentElement) {
              const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
              if (text.length > 30 && text.length < 2500 && cityPattern.test(text) && /R\$/.test(text)) {
                found.push({title, text});
                break;
              }
            }
          }
          return found;
        }""", {"cities": self.cities})
        list_url = page.url
        cards: dict[str, dict[str, str]] = {}
        for candidate in candidates:
            try:
                heading = page.get_by_role("heading", name=candidate["title"], exact=True).last
                heading.click(timeout=3000)
                page.wait_for_timeout(500)
                href = page.url
                if href != list_url and urlparse(href).hostname and self.link_matches(href) and self.host_matches(href):
                    cards.setdefault(href.split("#")[0], {"href": href, "text": candidate["text"]})
            except PlaywrightError:
                pass
            finally:
                if page.url != list_url:
                    page.goto(list_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                    page.wait_for_timeout(500)
        return list(cards.values())
