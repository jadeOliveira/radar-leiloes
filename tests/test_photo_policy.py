import copy
import unittest

from monitor.ensure_images import recover
from monitor.photo_policy import missing_photos


class ScheduledPhotoTests(unittest.TestCase):
    def test_requires_photo_for_every_city_and_historical_listing(self):
        items = [
            {'id': 'bc', 'city': 'Balneário Camboriú', 'image_urls': ['https://images.example/bc.jpg']},
            {'id': 'joinville', 'city': 'Joinville', 'image_urls': []},
            {'id': 'history', 'city': 'Rio do Sul', 'status': 'ended_unverified'},
        ]
        self.assertEqual(missing_photos(items), ['joinville', 'history'])

    def test_recovers_missing_history_preserves_prices_and_existing_photo(self):
        items = [
            {'id': 'existing', 'image_urls': ['https://images.example/existing.jpg'], 'price': 100},
            {'id': 'history', 'city': 'Rio do Sul', 'status': 'ended_unverified', 'price': 200,
             'source_listing_url': 'https://source.example/history', 'image_urls': []},
        ]
        original = copy.deepcopy(items)
        visited = []
        def load(url):
            visited.append(url)
            return ['https://images.example/history.jpg']
        recovered, errors = recover(items, load)
        self.assertEqual(visited, ['https://source.example/history'])
        self.assertEqual(recovered, ['history'])
        self.assertEqual(errors, [])
        self.assertEqual(items[0], original[0])
        self.assertEqual(items[1]['price'], original[1]['price'])
        self.assertEqual(items[1]['status'], original[1]['status'])
        self.assertEqual(missing_photos(items), [])

    def test_failure_is_reported_and_does_not_invent_photo(self):
        item = {'id': 'blocked', 'source_listing_url': 'https://source.example/blocked', 'image_urls': []}
        def blocked(url):
            raise RuntimeError('HTTP 429')
        recovered, errors = recover([item], blocked)
        self.assertEqual(recovered, [])
        self.assertEqual(len(errors), 1)
        self.assertEqual(missing_photos([item]), ['blocked'])

    def test_rejects_non_https_and_empty_photo_values(self):
        self.assertEqual(missing_photos([{'id': 'bad', 'image_urls': ['', 'data:image/png;base64,x', 'http://images.example/a.jpg']}]), ['bad'])


if __name__ == '__main__':
    unittest.main()
