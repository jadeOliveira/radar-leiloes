"""Publication rule shared by scheduled collection and Pages."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit


def photo_urls(item: dict) -> list[str]:
    return list(dict.fromkeys(url for url in item.get('image_urls', [])
        if isinstance(url, str) and urlsplit(url).scheme == 'https' and urlsplit(url).hostname))


def missing_photos(items: list[dict]) -> list[str]:
    return [item['id'] for item in items if not photo_urls(item)]


def main() -> int:
    data = json.loads((Path(__file__).resolve().parents[1] / 'data/properties.json').read_text())
    missing = missing_photos(data.get('properties', []))
    print(json.dumps({'total': len(data.get('properties', [])), 'missing_image_ids': missing}))
    if missing:
        print('Publicação bloqueada: recuperar fotos dos anúncios indicados; não usar fotos de outro imóvel.')
    return bool(missing)


if __name__ == '__main__':
    raise SystemExit(main())
