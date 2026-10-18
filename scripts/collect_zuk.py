#!/usr/bin/env python3
"""Best-effort public listing collector for Portal Zuk, scoped to Rio do Sul/SC."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "public" / "data" / "auctions.json"
SOURCE = "https://www.portalzuk.com.br/leilao-de-imoveis/c/todos-imoveis/sc/regiao/rio-do-sul"
CITY = "Rio do Sul"


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract(page) -> list[dict]:
    # Portal Zuk renders auction cards client-side; the text and links are read
    # from rendered DOM, while all displayed properties remain linked to source.
    page.goto(SOURCE, wait_until="domcontentloaded", timeout=90000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(1500)
    for _ in range(12):
        button = page.get_by_role("button", name=re.compile("carregar mais", re.I))
        if not button.count() or not button.first.is_visible():
            break
        try:
            button.first.click(timeout=2500)
            page.wait_for_timeout(900)
        except PlaywrightTimeoutError:
            break

    raw = page.evaluate(r"""() => Array.from(document.querySelectorAll('a[href]'))
      .map(a => {
        let text = '';
        let node = a;
        for (let i = 0; i < 7 && node; i++, node = node.parentElement) {
          const candidate = (node.innerText || '').replace(/\s+/g, ' ').trim();
          if (/Rio do Sul\s*\/\s*SC/i.test(candidate) && /R\$\s*[\d.]+,\d{2}/.test(candidate)) { text = candidate; break; }
        }
        return {href:a.href, text:(a.innerText || a.textContent || a.getAttribute('aria-label') || a.title || '').replace(/\s+/g,' ').trim(), parent:text};
      })
      .filter(x => /\/(imovel|lote|leilao|detalhe)[^/]*\//i.test(new URL(x.href).pathname))""")
    seen: set[str] = set()
    results = []
    for link in raw:
        block = clean(link["parent"])
        text = clean(link["text"])
        combined = f"{text} {block}"
        if CITY.casefold() not in combined.casefold() or "SC" not in combined:
            continue
        href = urljoin(SOURCE, link["href"])
        if href in seen or not text:
            continue
        seen.add(href)
        # Select the next scheduled bid; only use discount values displayed
        # between the bid and date by the source page.
        today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        bids = []
        for price_match in re.finditer(r"R\$\s*([\d.]+,\d{2})", block):
            segment = block[price_match.end():price_match.end() + 100]
            date_match = re.search(r"(\d{2}/\d{2}/\d{4})", segment)
            if not date_match:
                continue
            auction_day = datetime.strptime(date_match.group(1), "%d/%m/%Y").date()
            before_date = segment[:date_match.start()]
            percent_match = re.search(r"\b(100|[1-9]?\d)\s*$", before_date)
            bids.append((auction_day, float(price_match.group(1).replace(".", "").replace(",", ".")), int(percent_match.group(1)) if percent_match else None))
        upcoming = sorted((bid for bid in bids if bid[0] >= today), key=lambda bid: bid[0])
        chosen = upcoming[0] if upcoming else (bids[0] if bids else None)
        current = chosen[1] if chosen else None
        discount = chosen[2] if chosen else None
        auction_day = chosen[0] if chosen else None
        area_match = re.search(r"([\d.,]+)\s*m²", block, re.I)
        area = float(area_match.group(1).replace(".", "").replace(",", ".")) if area_match else None
        date_iso = auction_day.isoformat() if auction_day else None
        address_match = re.search(r"Rio do Sul\s*/\s*SC\s*[-–]\s*(.*?)(?=\s+(?:1º|2º)\s*leilão|\s+Valor|\s+R\$)", block, re.I)
        address = address_match.group(1).strip() if address_match else None
        title = text if len(text) > 4 else (block[:100] or "Imóvel em leilão")
        results.append({
            "id": href.rstrip("/").split("/")[-1], "title": title,
            "city": CITY, "state": "SC", "address": address,
            "propertyType": next((t for t in ("Apartamento", "Casa", "Terreno", "Comercial", "Rural") if t.casefold() in combined.casefold()), None),
            "auctioneer": "Portal Zuk", "url": href, "price": current,
            "appraisalValue": None, "discountPercent": discount,
            "areaM2": area, "auctionDate": date_iso,
            "occupancy": None,
        })
    return results


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="pt-BR", timezone_id="America/Sao_Paulo")
        auctions = extract(page)
        browser.close()
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"source": SOURCE, "updatedAt": timestamp, "auctions": auctions}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Coleta concluída: {len(auctions)} anúncio(s) de {CITY}/SC.")


if __name__ == "__main__":
    main()
