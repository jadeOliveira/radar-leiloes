from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime
from typing import Any


def fold(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold().split())


def money(value: str | None) -> float | None:
    if not value:
        return None
    normalized = re.sub(r"[^\d,.-]", "", value).replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def first(pattern: str, text: str, flags: int = re.I) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def parse_item(source: dict[str, Any], href: str, text: str, cities: list[str], seen_at: str) -> dict[str, Any] | None:
    text = re.sub(r"\s+", " ", text).strip()
    normalized = fold(text)
    city = next((city for city in cities if fold(city) in normalized), None)
    if not city:
        return None

    type_match = re.search(r"\b(casa|apartamento|terreno|lote(?:\s+urbano)?|sala\s+comercial|im[oó]vel\s+comercial)\b", text, re.I)
    property_type = type_match.group(1).title() if type_match else None
    # Parse only labels that state what the value means; never infer appraisal from a bid.
    appraisal = money(first(r"(?:avalia[cç][aã]o|valor\s+de\s+avalia[cç][aã]o)\D{0,24}(R\$\s*[\d.]+,\d{2})", text) or "")
    labeled_bids = [(label, money(value)) for label, value in re.findall(r"(1[ºo]\s*(?:leil[aã]o|pra[cç]a)|2[ºo]\s*(?:leil[aã]o|pra[cç]a)|lance\s+m[ií]nimo|lance\s+inicial|valor\s+de\s+lance\s+inicial)\D{0,35}(R\$\s*[\d.]+,\d{2})", text, re.I)]
    bids = {"first": None, "second": None, "current": None}
    for label, amount in labeled_bids:
        if amount is None:
            continue
        key = "second" if label.casefold().startswith("2") else "first" if label.casefold().startswith("1") else "current"
        if bids[key] is None:
            bids[key] = amount
    current = bids["second"] or bids["first"] or bids["current"]
    discount = round((1 - current / appraisal) * 100, 2) if current is not None and appraisal and appraisal > 0 else None
    date_matches = re.findall(r"(\d{2}/\d{2}/\d{4})(?:\s*(?:às|as)?\s*(\d{1,2}:\d{2}))?", text, re.I)
    events = []
    for i, (date, time) in enumerate(date_matches):
        stage = "second" if i == 1 else "first" if i == 0 else "unknown"
        events.append({"date": datetime.strptime(date, "%d/%m/%Y").date().isoformat(), "time": time or None, "minimum_bid_brl": bids[stage] if stage in bids else None, "stage": stage})
    street = first(r"(?:Endere[cç]o|Localiza[cç][aã]o)\s*:?\s*(.{4,180}?)(?:\s+(?:CEP|Lance|Matr[ií]cula|\d{5}-\d{3})\b|$)", text)
    if not street:
        # Some catalogs print a compact "City/SC - neighborhood street" line
        # instead of labeling the address. Anchor on the state marker so names
        # with accents or compound cities do not make the identity source-based.
        street = first(r"\bSC\s*[-–:]\s*(.{5,180}?)(?=\s+(?:1[ºo]\s*(?:leil[aã]o|pra[cç]a)|2[ºo]\s*(?:leil[aã]o|pra[cç]a)|lance|valor|R\$|aberto para)|$)", text)
    registry = first(r"Matr[ií]cula(?:\s+(?:n[º°.]?\s*)?)\s*([\d.]+)", text)
    area = first(r"([\d.,]+)\s*m(?:²|2)\b", text)
    occupied = "ocupad" if re.search(r"\bocupad[oa]s?\b", normalized) else "desocupado" if re.search(r"\bdesocupad[oa]s?\b", normalized) else None
    has_open_signal = bool(re.search(r"aberto para lance|aberto para proposta|dispon[ií]vel|em breve|aberto\b", normalized))
    today = datetime.fromisoformat(seen_at).date()
    future_events = [event for event in events if datetime.fromisoformat(event["date"]).date() >= today]
    status = "closed" if events and not future_events else "active" if has_open_signal and (not events or future_events) else "unknown"
    modality = "judicial" if "judicial" in normalized else "extrajudicial" if "extrajudicial" in normalized or "fiduciaria" in normalized else None
    id_match = first(r"(?:c[oó]d(?:igo)?\.?\s*(?:do im[oó]vel)?|lote|item|n[º°])\s*[:#]?\s*([a-z0-9-]{3,})", text)
    normalized_address = fold(street or "")
    identity_basis = f"matricula:{registry}" if registry else f"address:{fold(city)}:{normalized_address}" if normalized_address else f"source:{source['id']}:{id_match or href}"
    stable_id = hashlib.sha256(identity_basis.encode()).hexdigest()[:20]
    official = href.startswith("https://") and source["host"] in href
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
        "neighborhood": first(r"\b(?:bairro|bairro\s+de)\s+([\wÀ-ÿ -]{2,50})", text),
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
        "discount_on_appraisal_percent": discount,
        "auction_events": events,
        "commission_percent": float(first(r"comiss[aã]o\D{0,12}(\d{1,2}(?:[,\.]\d+)?)\s*%", text).replace(",", ".")) if first(r"comiss[aã]o\D{0,12}(\d{1,2}(?:[,\.]\d+)?)\s*%", text) else None,
        "payment_conditions": first(r"(?:condi[cç][oõ]es?\s+de\s+pagamento|forma\s+de\s+pagamento)\s*:?\s*(.{5,180}?)(?:\s+(?:comiss[aã]o|edital|matr[ií]cula)\b|$)", text),
        "occupancy": occupied,
        "status": status,
        "official_url": href if official else None,
        "edital_url": None,
        "document_urls": [],
        "first_seen_at": seen_at,
        "last_checked_at": seen_at,
        "classification": "A" if status == "active" and current is not None and current <= max_bid and discount is not None and discount >= min_discount else "B",
        "risk_flags": ["occupancy_unknown"] if occupied is None else (["occupied"] if occupied == "ocupad" else []),
        "field_verification": {**populated, "official_url": "verified" if official else "unverified", **{field: populated.get(field, "unknown") for field in fields if field not in populated}},
        "provenance": {"source_id": source["id"], "captured_from": href, "raw_text": text[:3000]},
    }
