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


def invalid_photo_ids(items: list[dict]) -> list[str]:
    return [item['id'] for item in items if any(
        isinstance(url, str) and url and url not in photo_urls(item)
        for url in item.get('image_urls', [])
    )]


def main() -> int:
    data = json.loads((Path(__file__).resolve().parents[1] / 'data/properties.json').read_text())
    items = data.get('properties', [])
    missing = missing_photos(items)
    invalid = invalid_photo_ids(items)
    print(json.dumps({'total': len(items), 'missing_image_ids': missing, 'invalid_image_ids': invalid}))
    if invalid:
        print('Publicação bloqueada: URLs de imagem devem ser HTTPS válidas.')
        return 1
    if missing:
        print('Alguns anúncios não têm foto verificável; o dashboard exibirá o placeholder, sem usar imagens de outros imóveis.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
