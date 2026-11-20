"""Tests for the Wikimedia Commons catalog adapter (#75)."""

import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from catalog_commons import (
    API_URL, attribution_text, build_search_url, clean_download_url,
    description_url, parse_search_response, safe_filename, validate_download_url,
)


def page(title, url, size=1024, license_name="CC BY-SA 4.0", **extra):
    meta = {
        "Artist": {"value": '<a href="//commons.wikimedia.org/wiki/User:A">A. Creator</a>'},
        "LicenseShortName": {"value": license_name},
        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
        "AttributionRequired": {"value": "true"},
    }
    meta.update(extra)
    return {
        "title": title,
        "imageinfo": [{
            "url": url,
            "thumburl": url.replace("upload.wikimedia.org", "thumb.wikimedia.org"),
            "size": size,
            "width": 1920,
            "height": 1080,
            "extmetadata": meta,
        }],
    }


class CatalogCommonsTests(unittest.TestCase):
    def test_search_url_uses_public_api_with_limits(self):
        url = build_search_url("mountains", 25)
        parsed = urlparse(url)
        self.assertTrue(url.startswith(API_URL))
        params = parse_qs(parsed.query)
        self.assertEqual(params["action"], ["query"])
        self.assertEqual(params["gsrnamespace"], ["6"])
        self.assertEqual(params["gsrlimit"], ["20"])
        self.assertIn("filetype:bitmap mountains", params["gsrsearch"][0])

    def test_url_validation(self):
        good = "https://upload.wikimedia.org/wikipedia/commons/a/ab/photo.jpg"
        self.assertTrue(validate_download_url(good))
        self.assertFalse(validate_download_url(good.replace("https", "http")))
        self.assertFalse(validate_download_url("https://example.com/photo.jpg"))
        self.assertFalse(validate_download_url("https://user:pass@upload.wikimedia.org/p.jpg"))
        self.assertFalse(validate_download_url(good[:-4] + ".exe"))
        self.assertFalse(validate_download_url(""))

    def test_tracking_parameters_are_stripped(self):
        url = ("https://upload.wikimedia.org/wikipedia/commons/a/ab/photo.jpg"
               "?utm_source=commons.wikimedia.org&utm_campaign=imageinfo")
        cleaned = clean_download_url(url)
        self.assertNotIn("?", cleaned)
        self.assertTrue(validate_download_url(cleaned))

    def test_parse_response_and_drop_unsafe_or_incomplete_items(self):
        good_url = "https://upload.wikimedia.org/wikipedia/commons/a/ab/photo.jpg"
        payload = {"query": {"pages": {
            "1": page("File:Photo one.jpg", good_url),
            "2": page("File:Huge.jpg", good_url, size=100 * 1024 * 1024),
            "3": page("File:Unsafe.jpg", "https://example.com/x.jpg"),
            "4": page("File:No license.jpg", good_url, license_name=""),
        }}}
        items = parse_search_response(payload, max_bytes=40 * 1024 * 1024)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["artist"], "A. Creator")
        self.assertEqual(item["license"], "CC BY-SA 4.0")
        self.assertTrue(item["attribution_required"])
        self.assertTrue(item["description_url"].startswith("https://commons.wikimedia.org/wiki/"))

    def test_parse_rejects_malformed_payload(self):
        for bad in ([], {"query": {"pages": []}}, None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_search_response(bad)

    def test_safe_filename_and_attribution(self):
        self.assertEqual(safe_filename("File:My/Photo?.jpg"), "My_Photo.jpg")
        item = {
            "artist": "Someone", "license": "CC BY 4.0",
            "license_url": "https://example.test/license",
            "description_url": description_url("File:X.jpg"),
        }
        text = attribution_text(item)
        self.assertIn("Creator: Someone", text)
        self.assertIn("License: CC BY 4.0", text)
        self.assertIn("Source:", text)


if __name__ == "__main__":
    unittest.main()
