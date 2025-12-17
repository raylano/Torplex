import unittest
from src.logic.quality import QualityManager

class TestQualityManager(unittest.TestCase):
    def setUp(self):
        self.qm = QualityManager()
        self.qm.profile = "1080p"
        self.qm.allow_4k = False # Explicitly forbid 4K

    def test_filter_no_4k(self):
        items = [
            {'title': 'Movie.Title.2023.1080p.BluRay.x264', 'magnetUrl': 'magnet:?xt=urn:btih:ABC'},
            {'title': 'Movie.Title.2023.2160p.WEB-DL.x265.HDR', 'magnetUrl': 'magnet:?xt=urn:btih:DEF'},
            {'title': 'Movie.Title.2023.720p.HDTV', 'magnetUrl': 'magnet:?xt=urn:btih:GHI'}
        ]

        filtered = self.qm.filter_items(items)
        # Should NOT contain the 2160p item
        self.assertEqual(len(filtered), 2)
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
