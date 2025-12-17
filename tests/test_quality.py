import unittest
from src.logic.quality import QualityManager

class TestQualityManager(unittest.TestCase):
    def setUp(self):
        self.qm = QualityManager()
        # Mock profile
        self.qm.profile = "1080p"

    def test_filter_items(self):
        items = [
            {'title': 'Movie.Title.2023.1080p.BluRay.x264', 'magnetUrl': 'magnet:?xt=urn:btih:ABC'},
            {'title': 'Movie.Title.2023.2160p.WEB-DL.x265.HDR', 'magnetUrl': 'magnet:?xt=urn:btih:DEF'},
            {'title': 'Movie.Title.2023.720p.HDTV', 'magnetUrl': 'magnet:?xt=urn:btih:GHI'}
        ]

        filtered = self.qm.filter_items(items)
        # Expect 1080p first (score 100+), then 2160p (score 10), then 720p
        self.assertEqual(filtered[0]['title'], 'Movie.Title.2023.1080p.BluRay.x264')

    def test_filter_anime(self):
        items = [
            {'title': 'Anime.Show.S01E01.1080p.Jap.Sub', 'magnetUrl': '...'},
            {'title': 'Anime.Show.S01E01.1080p.Dual-Audio', 'magnetUrl': '...'},
            {'title': 'Anime.Show.S01E01.720p.Dubbed', 'magnetUrl': '...'}
        ]

        # Should prefer Dual-Audio (score 200+) > Dubbed (150+) > Sub (0+)
        filtered = self.qm.filter_items(items, is_anime=True)
        self.assertIn('Dual-Audio', filtered[0]['title'])
        self.assertIn('Dubbed', filtered[1]['title'])

    def test_extract_hash(self):
        magnet = "magnet:?xt=urn:btih:ABC123DEF456&dn=Movie"
        h = self.qm.extract_hash(magnet)
        self.assertEqual(h, "abc123def456")

if __name__ == '__main__':
    unittest.main()
