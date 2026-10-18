#!/usr/bin/env python3
"""Best-effort public listing collector for Portal Zuk, scoped to Rio do Sul/SC."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "public" / "data" / "auctions.json"
SOURCE = "https://www.portalzuk.com.br/leilao-de-imoveis"
CITY = "Rio do Sul"


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def price_from(text: str) -> float | None:
    match = re.search(r"R\$\s*([\d.]+,\d{2})", text)
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


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

    raw = page.evaluate("""() => Array.from(document.querySelectorAll('a[href]'))
      .map(a => ({href:a.href, text:(a.innerText || a.textContent || '').replace(/\\s+/g,' ').trim(), parent:a.parentElement?.parentElement?.innerText || ''}))
      .filter(x => /\\/(imovel|lote|leilao|detalhe)[^/]*\\//i.test(new URL(x.href).pathname))""")
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
        # Use only the first published minimum bid; auction-stage prices are
        # not appraisal values and must not be used to invent a discount.
        current = price_from(block)
        explicit_discount = re.search(r"desconto\s*(?:de)?\s*(\d{1,2})\s*%", block, re.I)
        discount = int(explicit_discount.group(1)) if explicit_discount else None
        area_match = re.search(r"([\d.,]+)\s*m²", block, re.I)
        area = float(area_match.group(1).replace(".", "").replace(",", ".")) if area_match else None
        date_match = re.search(r"(\d{2}/\d{2}/\d{4})", block)
        date_iso = datetime.strptime(date_match.group(1), "%d/%m/%Y").date().isoformat() if date_match else None
        title = text if len(text) > 4 else (block[:100] or "Imóvel em leilão")
        results.append({
            "id": href.rstrip("/").split("/")[-1], "title": title,
            "city": CITY, "state": "SC", "address": None,
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
