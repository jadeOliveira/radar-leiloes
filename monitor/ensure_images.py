"""Recover missing photos across the whole published dataset, including history."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright
from .collectors.base import SiteAdapter, SourceUnavailable
from .images import extract_property_images
from .photo_policy import missing_photos, photo_urls
from .run import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


def recover(items, load_gallery):
    recovered, errors = [], []
    for item in items:
        if photo_urls(item):
            continue
        urls = list(dict.fromkeys(url for url in [item.get('image_source_url'), item.get('official_url'),
            item.get('source_listing_url'), item.get('provenance', {}).get('captured_from')]
            if isinstance(url, str) and urlsplit(url).scheme == 'https' and urlsplit(url).hostname))
        for url in urls:
            try:
                images = photo_urls({'image_urls': load_gallery(url)})
                if images:
                    item['image_urls'] = images
                    item['image_source_url'] = url
                    recovered.append(item['id'])
                    break
            except Exception as error:
                errors.append({'id': item['id'], 'source_url': url, 'error': str(error)[:300]})
    return recovered, errors


def main() -> int:
    path = ROOT / 'data/properties.json'
    data = read_json(path, {})
    items = data.get('properties', [])
    blocked_hosts = set()
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        def load_gallery(url):
            host = urlsplit(url).hostname
            if host in blocked_hosts:
                raise SourceUnavailable('Fonte bloqueada nesta execução; sem novas tentativas.')
            adapter = SiteAdapter({'id': 'images'}, [], 'America/Sao_Paulo')
            try:
                adapter._open(page, url)
            except SourceUnavailable:
                blocked_hosts.add(host)
                raise
            return extract_property_images(page, 'hasta' if host in ('hasta.com.br', 'www.hasta.com.br') else 'detail')
        recovered, errors = recover(items, load_gallery)
        browser.close()
    stamp = datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(timespec='seconds')
    if recovered:
        data['updated_at'] = stamp
        write_json(path, data)
    report = {'checked_at': stamp, 'total_listings': len(items),
        'listings_with_images': len(items) - len(missing_photos(items)),
        'recovered_ids': recovered, 'missing_image_ids': missing_photos(items), 'errors': errors}
    write_json(ROOT / 'data/image-report.json', report)
    print(json.dumps(report, ensure_ascii=False))
    return bool(report['missing_image_ids'])


if __name__ == '__main__':
    raise SystemExit(main())
