import unittest
from src.logic.quality import QualityManager

class TestQualityManager(unittest.TestCase):
    def setUp(self):
        self.qm = QualityManager()
        # Mock profile
        self.qm.profile = "4k"

    def test_filter_items(self):
        items = [
            {'title': 'Movie.Title.2023.1080p.BluRay.x264', 'magnetUrl': 'magnet:?xt=urn:btih:ABC'},
            {'title': 'Movie.Title.2023.2160p.WEB-DL.x265.HDR', 'magnetUrl': 'magnet:?xt=urn:btih:DEF'},
            {'title': 'Movie.Title.2023.720p.HDTV', 'magnetUrl': 'magnet:?xt=urn:btih:GHI'}
        ]

        filtered = self.qm.filter_items(items)
        # Expect 2160p first (score 100+), then 1080p (score 10), then 720p
        self.assertEqual(filtered[0]['title'], 'Movie.Title.2023.2160p.WEB-DL.x265.HDR')
        self.assertEqual(filtered[1]['title'], 'Movie.Title.2023.1080p.BluRay.x264')

    def test_extract_hash(self):
        magnet = "magnet:?xt=urn:btih:ABC123DEF456&dn=Movie"
        h = self.qm.extract_hash(magnet)
        self.assertEqual(h, "abc123def456")

if __name__ == '__main__':
    unittest.main()
