from __future__ import annotations

import json
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
from .normalization import identity_keys

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
    changes = []
    tracked = ("current_minimum_bid_brl", "appraisal_value_brl", "discount_on_appraisal_percent", "auction_events", "occupancy", "status", "payment_conditions", "edital_url")
    for field, value in new.items():
        if value is None or value == [] or value == {}:
            continue
        previous = merged.get(field)
        if field in tracked and previous != value:
            changes.append({"field": field, "before": previous, "after": value})
        if field in ("source_ids", "source_listing_ids", "document_urls", "image_urls"):
            merged[field] = list(dict.fromkeys((previous or []) + value))
        elif field == "provenance":
            sources = merged.get(field, {})
            sources.update(value)
            merged[field] = sources
        elif field == "field_verification":
            states = merged.get(field, {})
            for key, state in value.items():
                if state == "verified" or states.get(key) in (None, "unknown", "unverified"):
                    states[key] = state
            merged[field] = states
        else:
            merged[field] = value
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
    changes = []
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
    report = {
        "run_id": run_id, "status": run_status, "started_at": started, "finished_at": finished,
        "duration_seconds": round(time.monotonic() - started_clock, 2), "timezone": timezone,
        "cities": cities, "sources": results,
        "counts": {"new_or_updated": len(set(change["property_id"] for change in changes)), "total_preserved": len({item["id"] for item in by_identity.values()}), "sources_succeeded": source_successes, "sources_partial": source_partials, "sources_failed": source_failures},
        "errors": [{"source_id": result["source_id"], "message": result["error"]} for result in results if result.get("error")],
    }
    if source_successes + source_partials:
        canonical = {item["id"]: item for item in by_identity.values()}
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
