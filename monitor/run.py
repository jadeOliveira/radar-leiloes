from __future__ import annotations

import json
import re
import tempfile
import time
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from .collectors import ADAPTERS
from .normalization import canonical_property_type, has_card_details, identity_keys

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "monitor.json"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def now(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def merge_property(old: dict[str, Any] | None, new: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if old is None:
        return new, [{"field": "record", "before": None, "after": "new"}]
    merged = deepcopy(old)
    aggregator_observation = bool(new.get("provenance", {}).get("is_aggregator"))
    aggregator_only = aggregator_observation and set(merged.get("source_ids", [])).issubset({"hasta"})
    changes = []
    tracked = (
        "city", "neighborhood", "address", "property_type", "area_privative_m2", "area_built_m2", "area_total_m2",
        "registry_number", "registry_office", "auction_lot", "auctioneer", "seller", "modality",
        "appraisal_value_brl", "first_minimum_bid_brl", "second_minimum_bid_brl", "current_minimum_bid_brl", "source_listing_price_brl",
        "discount_on_appraisal_percent", "auction_events", "commission_percent", "payment_conditions",
        "occupancy", "status", "official_url", "source_listing_url", "validation_status", "edital_url",
        "document_urls", "image_urls", "classification", "risk_flags",
    )
    for field, value in new.items():
        previous = merged.get(field)
        old_field_is_verified = merged.get("field_verification", {}).get(field) == "verified"
        incoming_field_is_verified = new.get("field_verification", {}).get(field) == "verified"
        if value is None or value == [] or value == {}:
            incoming_state = new.get("field_verification", {}).get(field)
            if (field == "appraisal_value_brl" and aggregator_only and value is None
                    and incoming_state == "unknown" and not old_field_is_verified):
                merged[field] = None
                merged.setdefault("field_verification", {})[field] = "unknown"
                if field in tracked and previous is not None:
                    changes.append({"field": field, "before": previous, "after": None})
            continue
        if aggregator_observation and field not in ("status", "classification") and old_field_is_verified and not incoming_field_is_verified:
            continue
        if field in ("source_ids", "source_listing_ids", "source_listing_urls", "document_urls", "image_urls"):
            merged[field] = list(dict.fromkeys((previous or []) + value))
        elif field == "auction_events":
            events = list(previous or [])
            event_keys = {(event.get("date"), event.get("time"), event.get("stage"), event.get("minimum_bid_brl")) for event in events if isinstance(event, dict)}
            for event in value:
                event_key = (event.get("date"), event.get("time"), event.get("stage"), event.get("minimum_bid_brl"))
                if event_key not in event_keys:
                    events.append(event)
                    event_keys.add(event_key)
            merged[field] = sorted(events, key=lambda event: (event.get("date") or "", event.get("stage") or "", event.get("time") or ""))
        elif field == "provenance":
            sources = merged.get(field, {})
            old_urls = list(sources.get("source_listing_urls", []))
            if sources.get("captured_from"):
                old_urls.append(sources["captured_from"])
            if value.get("captured_from"):
                old_urls.append(value["captured_from"])
            old_urls.extend(value.get("source_listing_urls", []))
            sources.update(value)
            sources["source_listing_urls"] = list(dict.fromkeys(old_urls))
            merged[field] = sources
        elif field == "risk_flags":
            merged[field] = list(dict.fromkeys((previous or []) + value))
        elif field == "validation_status":
            merged[field] = "verified" if value == "verified" or previous == "verified" else value
        elif field == "field_verification":
            states = merged.get(field, {})
            for key, state in value.items():
                if state == "verified" or states.get(key) in (None, "unknown", "unverified"):
                    states[key] = state
            merged[field] = states
        elif field == "status" and aggregator_observation and merged.get("validation_status") == "verified" and previous == "active" and value in ("unknown", "scheduled_unverified"):
            continue
        elif field == "classification" and aggregator_observation and merged.get("validation_status") == "verified" and merged.get("status") == "active":
            continue
        else:
            merged[field] = value
        current = merged.get(field)
        if field in tracked and previous != current:
            changes.append({"field": field, "before": previous, "after": current})
    if merged.get("validation_status") == "verified" and "aggregator_listing_unverified" in merged.get("risk_flags", []):
        merged["risk_flags"].remove("aggregator_listing_unverified")
    if aggregator_only and new.get("validation_status") == "nao_verificado":
        old_address = merged.get("address") or ""
        address_like = re.compile(r"^(?:rua\b|r\.\s|avenida\b|av\.\s|alameda\b|travessa\b|servid[aã]o\b|estrada\b|rodovia\b)", re.I)
        merged["official_url"] = None
        merged["address"] = new.get("address") or (old_address if address_like.search(old_address.strip()) else None)
        merged["auctioneer"] = new.get("auctioneer")
        if new.get("image_urls"):
            merged["image_urls"] = new["image_urls"]
        merged["validation_status"] = "nao_verificado"
        merged.setdefault("field_verification", {}).update({
            "official_url": "unverified",
            "auctioneer": new.get("field_verification", {}).get("auctioneer", "unverified"),
            "address": new.get("field_verification", {}).get("address", "unknown"),
        })
    urls = list(merged.get("source_listing_urls", []))
    urls.extend([merged.get("source_listing_url"), new.get("source_listing_url"), new.get("official_url")])
    merged["source_listing_urls"] = list(dict.fromkeys(url for url in urls if url))
    merged["id"] = old["id"]
    merged["first_seen_at"] = old.get("first_seen_at") or new.get("first_seen_at")
    return merged, changes


def migrate_legacy() -> list[dict[str, Any]]:
    legacy = read_json(ROOT / "public" / "data" / "auctions.json", {}).get("auctions", [])
    migrated = []
    for auction in legacy:
        city = auction.get("city")
        item = {
            "id": auction.get("id"), "source_ids": ["portalzuk"], "source_listing_ids": [auction.get("id")],
            "city": city, "state": auction.get("state", "SC"), "address": auction.get("address"),
            "property_type": auction.get("propertyType"), "auctioneer": auction.get("auctioneer"),
            "official_url": auction.get("url"), "current_minimum_bid_brl": auction.get("price"),
            "appraisal_value_brl": auction.get("appraisalValue"), "discount_on_appraisal_percent": None,
            "auction_events": [], "occupancy": auction.get("occupancy"), "status": "unknown",
            "first_seen_at": auction.get("collectedAt"), "last_checked_at": auction.get("collectedAt"),
            "classification": "B", "risk_flags": ["legacy_record_unverified"],
            "field_verification": {"official_url": "unverified", "city": "unverified"},
            "provenance": {"source_id": "portalzuk", "legacy": True},
        }
        if item["id"] and city:
            migrated.append(item)
    return migrated


def validate(item: dict[str, Any], cities: list[str]) -> None:
    if not item.get("id") or item.get("city") not in cities or item.get("state") != "SC":
        raise ValueError(f"Registro inválido (identidade/localização): {item.get('id')}")
    url = item.get("official_url")
    if url and not url.startswith("https://"):
        raise ValueError(f"URL oficial inválida para {item['id']}")
    if not has_card_details(item):
        raise ValueError(f"Registro sem dados suficientes para exibir um card: {item['id']}")


def main() -> int:
    config = read_json(CONFIG_PATH, {})
    timezone = config.get("timezone", "America/Sao_Paulo")
    run_id = str(uuid.uuid4())
    started_dt = now(timezone)
    started = started_dt.isoformat(timespec="seconds")
    started_clock = time.monotonic()
    cities = config["cities"]
    existing_data = read_json(DATA_DIR / "properties.json", {"properties": []})
    existing = existing_data.get("properties", [])
    if not existing:
        existing = migrate_legacy()
    retained_existing = []
    excluded_existing = []
    for item in existing:
        normalized_type = canonical_property_type(item)
        if normalized_type:
            item["property_type"] = normalized_type
            retained_existing.append(item)
        else:
            excluded_existing.append(item)
    existing = retained_existing
    by_identity: dict[str, dict[str, Any]] = {}
    id_remap: dict[str, str] = {}
    for item in existing:
        if not item.get("id"):
            continue
        keys = identity_keys(item)
        previous = next((by_identity[key] for key in keys if key in by_identity), None)
        if previous:
            merged, _ = merge_property(previous, item)
            timestamps = [value for value in (previous.get("first_seen_at"), item.get("first_seen_at")) if value]
            merged["first_seen_at"] = min(timestamps) if timestamps else None
            if item["id"] != merged["id"]:
                id_remap[item["id"]] = merged["id"]
            keys = list(dict.fromkeys(identity_keys(previous) + keys + identity_keys(merged)))
            for key in keys:
                by_identity[key] = merged
        else:
            for key in keys:
                by_identity[key] = item

    results: list[dict[str, Any]] = []
    collected: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for source in config["sources"]:
            source = {**source, "priority": config.get("priority", {})}
            if not source.get("enabled", True):
                results.append({"source_id": source["id"], "name": source["name"], "status": "disabled", "pages_read": 0, "listings_found": 0, "error": None, "duration_seconds": 0})
                continue
            adapter_type = ADAPTERS.get(source.get("adapter"))
            if adapter_type is None:
                results.append({"source_id": source["id"], "name": source["name"], "status": "failed", "pages_read": 0, "listings_found": 0, "error": "Adaptador não implementado", "duration_seconds": 0})
                continue
            context = browser.new_context(locale="pt-BR", timezone_id=timezone)
            page = context.new_page()
            try:
                items, result = adapter_type(source, cities, timezone).collect(page)
                result["finished_at"] = now(timezone).isoformat(timespec="seconds")
                if result["status"] in ("success", "partial"):
                    result["last_success_at"] = result["finished_at"]
                results.append(result)
                collected.extend(items)
            except Exception as exception:  # isolate all source failures
                results.append({"source_id": source["id"], "name": source["name"], "status": "failed", "pages_read": 0, "listings_found": 0, "listings_by_city": {}, "error": str(exception), "duration_seconds": None, "finished_at": now(timezone).isoformat(timespec="seconds")})
                print(json.dumps({"event": "source_exception", "source_id": source["id"], "error": str(exception)}, ensure_ascii=False))
            finally:
                context.close()
        browser.close()

    checked_at = now(timezone).isoformat(timespec="seconds")
    changes = [{
        "property_id": item["id"],
        "city": item.get("city"),
        "source_ids": item.get("source_ids", []),
        "changes": [{"field": "feed_visibility", "before": "included", "after": "excluded_non_real_estate_or_unconfirmed_type"}],
    } for item in excluded_existing if item.get("id")]
    for item in collected:
        validate(item, cities)
        keys = identity_keys(item)
        previous = next((by_identity[key] for key in keys if key in by_identity), None)
        merged, item_changes = merge_property(previous, item)
        merged["last_checked_at"] = checked_at
        if item_changes and item_changes[0].get("field") == "record":
            item_changes = [{"field": "record", "before": None, "after": "new"}]
        if item_changes:
            changes.append({"property_id": merged["id"], "city": merged.get("city"), "source_ids": merged.get("source_ids", []), "changes": item_changes, "detected_at": checked_at})
        timestamps = [value for value in ((previous or {}).get("first_seen_at"), item.get("first_seen_at")) if value]
        merged["first_seen_at"] = min(timestamps) if timestamps else None
        for key in list(dict.fromkeys(keys + identity_keys(previous or {}) + identity_keys(merged))):
            by_identity[key] = merged

    source_successes = sum(1 for result in results if result["status"] == "success")
    source_partials = sum(1 for result in results if result["status"] == "partial")
    source_failures = sum(1 for result in results if result["status"] == "failed")
    run_status = "success" if source_failures == 0 and source_partials == 0 else "partial" if source_successes + source_partials else "failed"
    finished = now(timezone).isoformat(timespec="seconds")
    new_property_ids = sorted({
        change["property_id"] for change in changes
        if any(entry.get("field") == "record" and entry.get("after") == "new" for entry in change.get("changes", []))
    })
    changed_property_ids = sorted({change["property_id"] for change in changes} - set(new_property_ids))
    sources_available = source_successes + source_partials > 0
    data_status = "updated" if changes else "unchanged" if sources_available else "unavailable"
    data_updated_at = checked_at if data_status == "updated" else existing_data.get("updated_at")
    report = {
        "run_id": run_id, "status": run_status, "started_at": started, "finished_at": finished,
        "duration_seconds": round(time.monotonic() - started_clock, 2), "timezone": timezone,
        "cities": cities, "sources": results,
        "data_status": data_status, "data_updated_at": data_updated_at,
        "counts": {
            "new_listings": len(new_property_ids), "changed_listings": len(changed_property_ids),
            "new_or_updated": len(set(change["property_id"] for change in changes)),
            "total_preserved": len({item["id"] for item in by_identity.values()}),
            "sources_succeeded": source_successes, "sources_partial": source_partials, "sources_failed": source_failures,
        },
        "new_property_ids": new_property_ids, "changed_property_ids": changed_property_ids,
        "errors": [{"source_id": result["source_id"], "message": result["error"]} for result in results if result.get("error")],
    }
    if data_status == "updated":
        canonical = {item["id"]: item for item in by_identity.values()}
        for property_id in new_property_ids:
            if property_id in canonical:
                canonical[property_id]["newly_discovered_at"] = checked_at
        properties = sorted(canonical.values(), key=lambda item: (item.get("city", ""), item.get("id", "")))
        write_json(DATA_DIR / "properties.json", {"updated_at": checked_at, "timezone": timezone, "cities": cities, "priority": config.get("priority", {}), "properties": properties, "sources": results})
        history = read_json(DATA_DIR / "history.json", {"events": []})
        for event in history.get("events", []):
            event["property_id"] = id_remap.get(event.get("property_id"), event.get("property_id"))
        history["events"].extend(changes)
        write_json(DATA_DIR / "history.json", history)
        change_log = read_json(DATA_DIR / "changes.json", {"runs": []})
        for run in change_log.get("runs", []):
            for event in run.get("changes", []):
                event["property_id"] = id_remap.get(event.get("property_id"), event.get("property_id"))
        change_log["runs"].append({"run_id": run_id, "detected_at": checked_at, "changes": changes})
        write_json(DATA_DIR / "changes.json", change_log)
    write_json(DATA_DIR / "last-run.json", report)
    print(json.dumps({"event": "run_finished", **report}, ensure_ascii=False))
    return 1 if run_status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
