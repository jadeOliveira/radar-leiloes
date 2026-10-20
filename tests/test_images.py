import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from monitor.images import extract_property_images


class GalleryTests(unittest.TestCase):
    def test_hasta_keeps_unloaded_gallery_and_excludes_other_listings(self):
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            page = browser.new_page()
            page.route('**/*', lambda route: route.fulfill(content_type='text/html', body='''
                <img id="galMain" src="/foto/123/0.jpg">
                <div class="thumbs"><img loading="lazy" data-src="/foto/123/1.jpg" src="data:image/gif;base64,R0lGODlhAQABAIAAAAUEBA=="><img src="/foto/123/0.jpg"></div>
                <section><h2>Imóveis semelhantes</h2><img src="/foto/999/0.jpg"></section>
            ''') if route.request.resource_type == 'document' else route.abort())
            page.goto('https://hasta.com.br/imovel/123-test')
            self.assertEqual(extract_property_images(page, 'hasta'), [
                'https://hasta.com.br/foto/123/0.jpg',
                'https://hasta.com.br/foto/123/1.jpg',
            ])
            browser.close()


if __name__ == '__main__':
    unittest.main()
