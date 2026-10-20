"""Read the current listing's public gallery, including unloaded lazy images."""
from __future__ import annotations


def extract_property_images(page, source_id: str) -> list[str]:
    return page.evaluate(r"""(sourceId) => {
      // Hasta's recommendations are separate listings: never collect their photos.
      const images = sourceId === 'hasta'
        ? [...document.querySelectorAll('#galMain, .thumbs img')]
        : [...document.images].filter(image => !image.closest('header, footer, nav'));
      const urls = images.flatMap(image => {
        const srcset = image.getAttribute('srcset') || image.dataset.srcset || '';
        const candidates = [image.dataset.src, image.dataset.lazySrc, image.dataset.original,
          image.getAttribute('data-original-src'),
          ...srcset.split(',').map(part => part.trim().split(/\s+/)[0]),
          image.currentSrc, image.getAttribute('src')];
        if (sourceId !== 'hasta' && image.complete && image.naturalWidth > 0
            && (image.naturalWidth < 240 || image.naturalHeight < 150)) return [];
        return candidates.flatMap(source => {
          if (!source || /^(data:|blob:)/i.test(source)) return [];
          try {
            const url = new URL(source, location.href);
            if (!['http:', 'https:'].includes(url.protocol)) return [];
            if (/\.(svg|gif)(?:$|\?)/i.test(url.pathname)) return [];
            if (/logo|icon|avatar|banner|pixel|tracking|placeholder/i.test(url.pathname)) return [];
            return [url.href];
          } catch { return []; }
        });
      });
      return [...new Set(urls)].slice(0, 12);
    }""", source_id)
