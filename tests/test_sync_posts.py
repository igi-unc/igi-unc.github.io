import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sync_posts  # noqa: E402


class SyncPostsTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "ignore_image_substrings": ["8b44083d-390f-45ac-af2a-916e47031033"],
            "match_patterns": [r"\bIGI\b", "Initiative for Generative Immunotherapy"],
            "include_urls": ["https://pirlblog.substack.com/p/pinned-post"],
            "exclude_urls": ["https://pirlblog.substack.com/p/skip-me"],
        }

    def test_matches_igi_subtitle_and_skips_unrelated(self):
        igi_post = {
            "title": "New tumor pMHC dataset",
            "subtitle": "First release from IGI at UNC",
            "url": "https://pirlblog.substack.com/p/new-tumor-pmhc",
        }
        other_post = {
            "title": "Shaking the Rust Off Python",
            "subtitle": "Origin stories of k-mer counting",  # contains 'origin', not word IGI
            "url": "https://pirlblog.substack.com/p/rust",
        }
        self.assertTrue(sync_posts.is_igi_post(igi_post, self.cfg, set()))
        self.assertFalse(sync_posts.is_igi_post(other_post, self.cfg, set()))

    def test_include_exclude_and_tag_urls(self):
        pinned = {"title": "General title", "url": "https://pirlblog.substack.com/p/pinned-post/"}
        tagged = {"title": "Tagged on Substack", "url": "https://pirlblog.substack.com/p/tagged-one"}
        skipped = {"title": "IGI internal draft", "url": "https://pirlblog.substack.com/p/skip-me"}
        self.assertTrue(sync_posts.is_igi_post(pinned, self.cfg, set()))
        self.assertTrue(sync_posts.is_igi_post(tagged, self.cfg, {"https://pirlblog.substack.com/p/tagged-one"}))
        self.assertFalse(sync_posts.is_igi_post(skipped, self.cfg, set()))

    def test_filters_generic_avatar_cover(self):
        avatar_post = {
            "image": "https://substackcdn.com/image/fetch/8b44083d-390f-45ac-af2a-916e47031033_1280x1280.png"
        }
        real_post = {
            "image": "https://substackcdn.com/image/fetch/figure1_1200x800.png"
        }
        self.assertFalse(sync_posts.usable_cover(avatar_post, self.cfg))
        self.assertTrue(sync_posts.usable_cover(real_post, self.cfg))

    def test_inject_into_index_preserves_surrounding_markup(self):
        sample = "<html><body><!-- BLOG-POSTS:START -->old<!-- BLOG-POSTS:END --></body></html>"
        out = sync_posts.inject_into_index(sample, "      <p>new</p>")
        self.assertIn("<!-- BLOG-POSTS:START -->\n      <p>new</p>\n      <!-- BLOG-POSTS:END -->", out)


if __name__ == "__main__":
    unittest.main()
