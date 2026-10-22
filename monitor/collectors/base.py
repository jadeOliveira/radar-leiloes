from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from ..images import extract_property_images
from ..normalization import canonical_property_type, fold, has_card_details, parse_item


class SourceUnavailable(RuntimeError):
    pass


class SiteAdapter:
    """Independent adapter base. A source failure never aborts other adapters."""

    pagination_parameter = "page"
    timeout_ms = 25000

    def __init__(self, config: dict[str, Any], cities: list[str], timezone: str) -> None:
        self.config = config
        self.cities = cities
        self.timezone = timezone

    def page_url(self, number: int) -> str:
        template = self.config["url"]
        return template.format(page=number) if "{page}" in template else template

    def prepare(self, page) -> None:
        """Optional public search form setup. Implementations must not log in or bypass challenges."""

    def link_matches(self, href: str) -> bool:
        return bool(re.search(self.config["path_pattern"], urlparse(href).path, re.I))

    def host_matches(self, href: str) -> bool:
        actual = (urlparse(href).hostname or "").casefold().removeprefix("www.")
        expected = self.config["host"].casefold().removeprefix("www.")
        return actual == expected

    def _open(self, page, url: str) -> None:
        last_error = None
        for attempt in range(2):
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                if response and response.status in (401, 403, 429):
                    raise SourceUnavailable(f"Fonte limitada (HTTP {response.status}); acesso não contornado.")
                page.wait_for_timeout(900)
                title = page.title().casefold()
                body = page.locator("body").inner_text(timeout=5000)
                if any(marker in title for marker in ("attention required", "access denied", "captcha", "cloudflare")) or any(marker in body[:2500].casefold() for marker in ("verify you are human", "captcha challenge", "access denied", "cloudflare")):
                    raise SourceUnavailable("Bloqueio/CAPTCHA detectado; a fonte não foi contornada.")
                self.prepare(page)
                return
            except SourceUnavailable:
                raise
            except (PlaywrightTimeoutError, PlaywrightError) as error:
                last_error = error
                if attempt == 0:
                    time.sleep(1)
        raise SourceUnavailable(f"Falha ao abrir a fonte: {last_error}")

    def _read_cards(self, page) -> list[dict[str, str]]:
        pattern = self.config["path_pattern"]
        cards = page.evaluate("""({pattern}) => {
          const matcher = new RegExp(pattern, 'i');
          const result = [];
          for (const a of document.querySelectorAll('a[href]')) {
            if (!matcher.test(new URL(a.href).pathname)) continue;
            let node = a, text = '', image = null;
            for (let i = 0; i < 9 && node; i++, node = node.parentElement) {
              const candidate = (node.innerText || '').replace(/\\s+/g, ' ').trim();
              if (candidate.length > 40 && candidate.length < 2500) {
                text = candidate;
              const picture = [...node.querySelectorAll('img')].map(img => {
                const srcset = img.getAttribute('srcset') || img.dataset.srcset || '';
                const source = img.currentSrc || img.dataset.src || img.dataset.lazySrc || img.dataset.original || img.getAttribute('data-original-src') || srcset.split(',')[0]?.trim().split(/\\s+/)[0] || img.getAttribute('src');
                if (!source || /^(?:data:|blob:)/i.test(source)) return null;
                if (img.complete && img.naturalWidth > 0 && (img.naturalWidth < 120 || img.naturalHeight < 90)) return null;
                if (/logo|icon|avatar|banner|pixel|tracking|placeholder/i.test(`${source} ${img.alt || ''}`)) return null;
                return source;
              }).find(Boolean);
                image = picture || null;
                break;
              }
            }
            result.push({href:a.href, text:text || (a.innerText || a.textContent || '').trim(), image});
          }
          return result;
        }""", {"pattern": pattern})
        unique: dict[str, dict[str, str]] = {}
        for card in cards:
            if self.link_matches(card["href"]) and self.host_matches(card["href"]):
                unique.setdefault(card["href"].split("#")[0], card)
        return list(unique.values())

    def _load_more(self, page) -> None:
        previous_count = -1
        while True:
            button = page.get_by_role("button", name=re.compile(r"carregar mais|ver mais|mostrar mais", re.I))
            if not button.count() or not button.first.is_visible():
                return
            try:
                current_count = page.locator("a[href]").count()
                if current_count <= previous_count:
                    return
                previous_count = current_count
                button.first.click(timeout=2000)
                page.wait_for_timeout(500)
                if page.locator("a[href]").count() <= current_count:
                    return
            except PlaywrightError:
                return

    def _next_page_url(self, page) -> str | None:
        links = page.locator('a[rel="next"], a[aria-label*="Próxima" i], a[aria-label*="Next" i], a[title*="Próxima" i], a[title*="Next" i]')
        if links.count():
            href = links.first.get_attribute("href")
            if href:
                return page.evaluate("href => new URL(href, location.href).href", href)
        pagination = page.locator("nav[aria-label*='pag' i] a[href], .pagination a[href], [class*='pagination'] a[href]")
        for index in range(pagination.count()):
            link = pagination.nth(index)
            label = f"{link.inner_text(timeout=1000)} {link.get_attribute('aria-label') or ''} {link.get_attribute('title') or ''}".casefold()
            if any(token in label for token in ("próxima", "proxima", "next", "›", "»", "→")):
                href = link.get_attribute("href")
                if href:
                    return page.evaluate("href => new URL(href, location.href).href", href)
        return None

    def collect(self, page) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.monotonic()
        seen_urls: set[str] = set()
        properties: dict[str, dict[str, Any]] = {}
        pages_ok = 0
        error = None
        detail_error = None
        discarded_empty_cards = 0
        dynamic_next_url = None
        page_number = 0
        visited_pages: set[str] = set()
        paginated_template = "{page}" in self.config["url"]
        last_page_signature: tuple[str, ...] | None = None
        consecutive_duplicate_pages = 0
        while True:
            page_number += 1
            url = self.page_url(page_number) if paginated_template else (dynamic_next_url or self.page_url(1))
            if not url or url in visited_pages:
                break
            visited_pages.add(url)
            try:
                self._open(page, url)
                self._load_more(page)
                cards = self._read_cards(page)
                next_url = self._next_page_url(page)
                dynamic_next_url = next_url
                body = page.locator("body").inner_text(timeout=5000)
                if not cards:
                    if re.search(r"nenhum(?:a)?\s+(?:im[oó]vel|resultado|an[uú]ncio)|n[aã]o encontramos|sem oportunidades", body, re.I):
                        pages_ok += 1
                        break
                    if next_url and next_url not in visited_pages:
                        pages_ok += 1
                        error = error or "Página de resultados sem cartões reconhecidos; a paginação continuou."
                        continue
                    if page_number == 1:
                        raise SourceUnavailable("Página carregada, mas o formato dos resultados ainda não foi reconhecido.")
                    break
                new_urls = [item for item in cards if item["href"] not in seen_urls]
                page_signature = tuple(sorted(item["href"] for item in cards))
                if not new_urls and page_number > 1:
                    consecutive_duplicate_pages = consecutive_duplicate_pages + 1 if page_signature == last_page_signature else 1
                    if consecutive_duplicate_pages >= 2:
                        error = error or "A paginação repetiu a mesma página; a fonte não avançou para novos resultados."
                        break
                else:
                    consecutive_duplicate_pages = 0
                last_page_signature = page_signature
                seen_urls.update(item["href"] for item in new_urls)
                pages_ok += 1
                for card in new_urls:
                    combined = card["text"]
                    # Search pagination already captured every card on this page.
                    # Avoid expensive detail requests for cards that explicitly
                    # identify a different city; cards with unknown city still
                    # get a detail lookup in case it supplies the location.
                    has_explicit_state = bool(re.search(r"(?:/|,|-)\s*(?:AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b", combined, re.I))
                    matches_city = any(fold(city) in fold(combined) for city in self.cities)
                    if has_explicit_state and not matches_city:
                        continue
                    captured_at = datetime.now(ZoneInfo(self.timezone)).isoformat(timespec="seconds")
                    detail_links = []
                    detail_images = []
                    if self.config.get("skip_detail") and self.config.get("enrich_images"):
                        try:
                            self._open(page, card["href"])
                            detail_images = extract_property_images(page, self.config["id"])
                        except (SourceUnavailable, PlaywrightError) as exception:
                            detail_error = detail_error or str(exception)
                        if not detail_images and card.get("image"):
                            detail_images = [page.evaluate("url => new URL(url, location.href).href", card["image"])]
                    elif self.config.get("skip_detail"):
                        if card.get("image"):
                            detail_images = [page.evaluate("url => new URL(url, location.href).href", card["image"])]
                    else:
                        try:
                            self._open(page, card["href"])
                            detail_text = page.locator("body").inner_text(timeout=5000)
                            combined = f"{combined} {detail_text}"
                            detail_links = page.locator("a[href]").evaluate_all("""links => links.map(a => ({url:a.href, text:(a.innerText || a.textContent || '').trim()})).filter(x => /edital|matr[ií]cula|documento|\\.pdf(\\?|$)/i.test(x.text + ' ' + x.url))""")
                            detail_images = extract_property_images(page, self.config["id"])
                        except (SourceUnavailable, PlaywrightError) as exception:
                            detail_error = detail_error or str(exception)
                    item = parse_item(self.config, card["href"], combined, self.cities, captured_at)
                    # Mixed auction portals also list cars, machines and other movable goods.
                    # Keep discovery broad, then publish only explicitly recognized real estate.
                    non_property_signal = bool(re.search(
                        r"\b(?:autom[oó]vel|ve[ií]culo|carro|motocicleta|moto|caminh[aã]o|trator|embarca[cç][aã]o|sucata|maquin[aá]rio)\b",
                        combined[:2000], re.I,
                    ))
                    if item:
                        item["property_type"] = canonical_property_type(item, combined)
                    if item and (non_property_signal or not item.get("property_type")):
                        item = None
                    if item:
                        item["image_urls"] = detail_images
                        if not has_card_details(item):
                            discarded_empty_cards += 1
                            continue
                        item["document_urls"] = list(dict.fromkeys(link["url"] for link in detail_links))
                        item["image_urls"] = detail_images
                        item["edital_url"] = next((link["url"] for link in detail_links if "edital" in link["text"].casefold()), None)
                        if item["edital_url"]:
                            item["field_verification"]["edital_url"] = "verified"
                        properties[item["id"]] = item
                dynamic_next_url = next_url
            except SourceUnavailable as exception:
                error = str(exception)
                break
            except (PlaywrightError, ValueError) as exception:
                error = str(exception)
                break
            if not paginated_template and not dynamic_next_url:
                break
            if not paginated_template and dynamic_next_url in visited_pages:
                break
        if pages_ok == 0 and not error:
            error = "Nenhuma página de resultados acessível."
        if detail_error and not error:
            error = f"Alguns anúncios não puderam ser abertos: {detail_error}"
        if discarded_empty_cards:
            message = f"{discarded_empty_cards} anúncios descartados por não conterem dados suficientes para um card."
            error = f"{error}; {message}" if error else message
        status = "success" if not error else ("partial" if pages_ok else "failed")
        summary = {
            "source_id": self.config["id"], "name": self.config["name"], "status": status,
            "pages_read": pages_ok, "listings_found": len(properties), "error": error,
            "listings_by_city": {city: sum(1 for item in properties.values() if item["city"] == city) for city in self.cities},
            "duration_seconds": round(time.monotonic() - started, 2),
        }
        print(json.dumps({"event": "source_result", **summary}, ensure_ascii=False))
        return list(properties.values()), summary
