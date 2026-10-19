from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


def fold(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold().split())


def identity_keys(item: dict[str, Any]) -> list[str]:
    """Return all stable identity aliases so new document data cannot split a record."""
    keys = []
    registry = fold(str(item.get("registry_number") or ""))
    address = fold(item.get("address") or "")
    if registry:
        keys.append(f"registry:{registry}")
    if address:
        keys.append(f"address:{fold(item.get('city') or '')}:{address}")
    if item.get("provenance", {}).get("is_aggregator") or "hasta" in (item.get("source_ids") or []):
        listing_url = item.get("source_listing_url") or item.get("provenance", {}).get("captured_from") or ""
        listing_id = re.search(r"/imovel/(\d+)(?:-|/|$)", listing_url)
        if listing_id:
            keys.append(f"source-listing:{item.get('provenance', {}).get('source_id')}:{listing_id.group(1)}")
    if not keys and item.get("id"):
        source = (item.get("source_ids") or ["unknown"])[0]
        keys.append(f"source-id:{source}:{item['id']}")
    return keys


def money(value: str | None) -> float | None:
    if not value:
        return None
    normalized = re.sub(r"[^\d,.-]", "", value).replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


CURRENCY_AMOUNT = r"R\$\s*(?:(?:\d{1,3}(?:\.\d{3})+)|\d+)(?:,\d{2})?"


def first(pattern: str, text: str, flags: int = re.I) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def extract_neighborhood(text: str) -> str | None:
    """Extract a neighborhood only when the listing labels it explicitly."""
    value = first(r"\bbairro(?:\s+de)?\s*[:\-]?\s*([^,;|]{2,60})", text)
    if not value:
        return None
    value = re.split(r"\s+(?:-|–|—)\s+", value, maxsplit=1)[0]
    value = re.split(r"\s+(?:cep|cidade|matr[ií]cula|localiza[cç][aã]o|endere[cç]o|comarca|lote)\b", value, maxsplit=1, flags=re.I)[0]
    value = value.strip(" .:-–—")
    if len(value) < 2 or len(value) > 50:
        return None
    return value


def has_card_details(item: dict[str, Any]) -> bool:
    """Require at least one listing fact beyond city/status before publishing a card."""
    return any((
        item.get("property_type"), item.get("address"), item.get("source_listing_price_brl"),
        item.get("current_minimum_bid_brl"), item.get("appraisal_value_brl"),
        item.get("auction_events"), item.get("image_urls"),
    ))


STATE_CODES = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()


def parse_item(source: dict[str, Any], href: str, text: str, cities: list[str], seen_at: str) -> dict[str, Any] | None:
    text = re.sub(r"\s+", " ", text).strip()
    # Use the first explicit state marker and require a configured city directly
    # before it. A page can mention target cities in navigation or other lots.
    state_marker = re.search(r"(?:/|,|-)\s*(" + "|".join(STATE_CODES) + r")\b", text)
    city_match = None
    city = None
    if state_marker and state_marker.group(1) == "SC":
        for candidate in cities:
            candidate_match = re.search(rf"\b{re.escape(candidate)}\s*(?:/|,|-)\s*SC\b", text, re.I)
            if candidate_match and candidate_match.end() == state_marker.end():
                city_match, city = candidate_match, candidate
                break
    elif not state_marker:
        raw_city = first(r"\bCidade\s*:\s*([A-ZÀ-ÿ][A-Za-zÀ-ÿ .'-]{1,50})", text)
        city = next((candidate for candidate in cities if raw_city and fold(candidate) == fold(raw_city)), None)
    if not city:
        return None
    normalized = fold(text)
    # Detail pages may append a long edital/catalog PDF after the listing
    # summary. Keep market amounts and dates tied to the listing header.
    market_text = text[:2000]

    type_match = re.search(r"\b(casa|apartamento|terreno|lote\s+(?:urbano|rural|de\s+terreno|de\s+terras)|galp[aã]o(?:\s+industrial)?)\b", market_text, re.I)
    property_type = type_match.group(1).title() if type_match else None
    if property_type and fold(property_type).startswith("galpao"):
        property_type = "Galpão"
    # Parse only labels that state what the value means; never infer appraisal from a bid.
    # Require the currency value immediately after the appraisal label. A broad
    # search can cross unrelated card text and mistake a later price for appraisal.
    appraisal = money(first(r"(?:valor\s+de\s+)?avalia[cç][aã]o\s*(?:do\s+im[oó]vel\s*)?[:\-]?\s*(" + CURRENCY_AMOUNT + r")", text[:8000]) or "")
    bid_labels = r"(1[ºo]\s*(?:leil[aã]o|pra[cç]a)|2[ºo]\s*(?:leil[aã]o|pra[cç]a)|lance\s+m[ií]nimo|lance\s+inicial|valor\s+(?:de\s+lance\s+)?inicial)"
    labeled_bids = [(label, money(value)) for label, value in re.findall(bid_labels + r"\D{0,35}(" + CURRENCY_AMOUNT + r")", market_text, re.I)]
    labeled_bids += [(label, money(value)) for value, label in re.findall(r"(" + CURRENCY_AMOUNT + r")\D{0,35}" + bid_labels, market_text, re.I)]
    bids = {"first": None, "second": None, "current": None}
    for label, amount in labeled_bids:
        if amount is None:
            continue
        key = "second" if label.casefold().startswith("2") else "first" if label.casefold().startswith("1") else "current"
        if bids[key] is None:
            bids[key] = amount
    current = bids["second"] or bids["first"] or bids["current"]
    declared_discount = first(r"(\d{1,2}(?:[,.]\d{1,2})?)\s*%\s*(?:de\s+desconto\s*)?(?:sobre|abaixo|da)\s*(?:[ao]\s*)?(?:valor\s+)?(?:de\s+)?avalia[cç][aã]o", market_text)
    discount = (float(declared_discount.replace(",", ".")) if declared_discount else
                round((1 - current / appraisal) * 100, 2) if current is not None and appraisal and appraisal > 0 else None)
    # Preserve an unlabelled amount as a source-display price only. It is not
    # promoted to an auction bid or appraisal without an explicit source label.
    source_listing_price = money(first("(" + CURRENCY_AMOUNT + r")", market_text) or "")
    date_matches = re.findall(r"(\d{2}/\d{2}/\d{4})(?:\s*(?:às|as)?\s*(\d{1,2}:\d{2}))?", market_text, re.I)
    events = []
    for i, (date, time) in enumerate(date_matches):
        stage = "second" if i == 1 else "first" if i == 0 else "unknown"
        events.append({"date": datetime.strptime(date, "%d/%m/%Y").date().isoformat(), "time": time or None, "minimum_bid_brl": bids[stage] if stage in ("first", "second") else bids["current"], "stage": stage})
    street = None
    if city_match:
        location_tail = text[city_match.end():].lstrip(" -–:,. ")
        street = re.split(r"\s+(?:1[ºo]\s*(?:leil[aã]o|pra[cç]a)|2[ºo]\s*(?:leil[aã]o|pra[cç]a)|lance|valor|avalia[cç][aã]o|R\$|aberto para)", location_tail, maxsplit=1, flags=re.I)[0].strip(" .,-")[:180] or None
    labeled_address = first(r"(?:Endere[cç]o|Localiza[cç][aã]o)\s*:?\s*(.{4,180}?)(?:\s+(?:CEP|Comitente|Leiloeiro|Descri[cç][aã]o|Edital|Lance|Matr[ií]cula|\d{5}-\d{3})\b|$)", text[:5000])
    if labeled_address:
        street = labeled_address
    registry = first(r"Matr[ií]cula(?:\(s\))?\s*(?:n[º°.]?\s*)?[:#]?\s*([\d.]+)", text)
    registry = registry.rstrip(".") if registry else None
    area = first(r"([\d.,]+)\s*m(?:²|2)\b", market_text)
    occupied = "ocupado" if re.search(r"\bocupad[oa]s?\b", normalized) else "desocupado" if re.search(r"\bdesocupad[oa]s?\b", normalized) else None
    today = datetime.fromisoformat(seen_at).date()
    future_events = [event for event in events if datetime.fromisoformat(event["date"]).date() >= today]
    cancelled_signal = bool(re.search(r"\b(?:leilao|lote|anuncio)\s+(?:cancelad[oa]s?|suspens[oa]s?|retirad[oa]s?)\b|\bcancelad[oa]s?\b", normalized))
    sold_signal = bool(re.search(r"\b(?:imovel|lote|bem)\s+(?:vendid[oa]s?|arrematad[oa]s?)\b|\bleilao\s+(?:vendid[oa]|arrematad[oa])\b", normalized))
    closed_signal = bool(re.search(r"\b(?:leilao|lote)\s+(?:encerrad[oa]s?|finalizad[oa]s?)\b|\b(?:encerrad[oa]s?|finalizad[oa]s?)\b", normalized))
    has_open_signal = bool(re.search(r"\baberto\s+para\s+(?:lances?|propostas?)\b|\b(?:lances?|propostas?)\s+abertos?\b|\bdisponivel\s+para\s+(?:lances?|propostas?)\b|\bstatus\s+do\s+lote\s*[:\-]?\s*aberto\b", normalized))
    if cancelled_signal:
        status = "cancelled"
    elif sold_signal:
        status = "sold"
    elif closed_signal:
        status = "closed"
    elif has_open_signal:
        status = "active" if not events or future_events else "ended_unverified"
    elif future_events:
        status = "scheduled_unverified"
    elif events:
        status = "ended_unverified"
    else:
        status = "unknown"
    modality = "judicial" if "judicial" in normalized else "extrajudicial" if "extrajudicial" in normalized or "fiduciaria" in normalized else None
    id_match = first(r"(?:c[oó]d(?:igo)?\.?\s*(?:do im[oó]vel)?|lote|item|n[º°])\s*[:#]?\s*([a-z0-9-]{3,})", text)
    normalized_address = fold(street or "")
    identity_basis = f"matricula:{registry}" if registry else f"address:{fold(city)}:{normalized_address}" if normalized_address else f"source:{source['id']}:{id_match or href}"
    stable_id = hashlib.sha256(identity_basis.encode()).hexdigest()[:20]
    actual_host = (urlparse(href).hostname or "").casefold().removeprefix("www.")
    expected_host = source["host"].casefold().removeprefix("www.")
    official = not source.get("is_aggregator", False) and href.startswith("https://") and actual_host == expected_host
    if source.get("is_aggregator", False):
        address_like = re.compile(r"^(?:rua\b|r\.\s|avenida\b|av\.\s|alameda\b|travessa\b|servid[aã]o\b|estrada\b|rodovia\b)", re.I)
        if street and not address_like.search(street.strip()):
            street = None
    fields = ["city", "property_type", "appraisal_value_brl", "first_minimum_bid_brl", "second_minimum_bid_brl", "current_minimum_bid_brl", "occupancy", "registry_number", "auction_events"]
    populated = {"city": "declared"}
    for field, value in (("property_type", property_type), ("appraisal_value_brl", appraisal), ("first_minimum_bid_brl", bids["first"]), ("second_minimum_bid_brl", bids["second"]), ("current_minimum_bid_brl", current), ("occupancy", occupied), ("registry_number", registry), ("auction_events", events)):
        populated[field] = "declared" if value not in (None, [], {}) else "unknown"
    thresholds = source.get("priority", {})
    max_bid = thresholds.get("max_bid_brl", 800000)
    min_discount = thresholds.get("min_discount_percent", 30)
    return {
        "id": stable_id,
        "source_ids": [source["id"]],
        "source_listing_ids": [id_match] if id_match else [],
        "city": city,
        "state": "SC",
        "neighborhood": extract_neighborhood(market_text),
        "address": street,
        "property_type": property_type,
        "area_privative_m2": float(area.replace(".", "").replace(",", ".")) if area else None,
        "area_built_m2": None,
        "area_total_m2": None,
        "registry_number": registry,
        "registry_office": first(r"(?:cart[oó]rio|registro\s+de\s+im[oó]veis|RI)\s*(?:n[º°.]?\s*)?([^,.]{3,90})", text),
        "auction_lot": first(r"(?:lote|item)\s*[:#]?\s*(\d+[A-Z]?)", text),
        "auctioneer": source["name"],
        "seller": first(r"(?:comitente|vendedor|institui[cç][aã]o\s+vendedora)\s*:?\s*([^,.]{3,100})", text),
        "modality": modality,
        "appraisal_value_brl": appraisal,
        "first_minimum_bid_brl": bids["first"],
        "second_minimum_bid_brl": bids["second"],
        "current_minimum_bid_brl": current,
        "source_listing_price_brl": source_listing_price,
        "discount_on_appraisal_percent": discount,
        "auction_events": events,
        "commission_percent": float(first(r"comiss[aã]o\D{0,12}(\d{1,2}(?:[,\.]\d+)?)\s*%", text).replace(",", ".")) if first(r"comiss[aã]o\D{0,12}(\d{1,2}(?:[,\.]\d+)?)\s*%", text) else None,
        "payment_conditions": first(r"(?:condi[cç][oõ]es?\s+de\s+pagamento|forma\s+de\s+pagamento)\s*:?\s*(.{5,180}?)(?:\s+(?:comiss[aã]o|edital|matr[ií]cula)\b|$)", text),
        "occupancy": occupied,
        "status": status,
        "official_url": href if official else None,
        "source_listing_url": href,
        "validation_status": "verified" if official else "nao_verificado",
        "edital_url": None,
        "document_urls": [],
        "image_urls": [],
        "first_seen_at": seen_at,
        "last_checked_at": seen_at,
        "classification": "A" if status == "active" and current is not None and current <= max_bid and discount is not None and discount >= min_discount else "B",
        "risk_flags": ["occupancy_unknown"] if occupied is None else (["occupied"] if occupied == "ocupado" else []),
        "field_verification": {**populated, "source_listing_price_brl": "declared" if source_listing_price is not None else "unknown", "official_url": "verified" if official else "unverified", **{field: populated.get(field, "unknown") for field in fields if field not in populated}},
        "provenance": {"source_id": source["id"], "captured_from": href, "is_aggregator": bool(source.get("is_aggregator")), "raw_text": text[:3000]},
    }
