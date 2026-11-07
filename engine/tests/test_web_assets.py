# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Vendored browser code runs only as pinned, and the palette stays readable.

A changed, missing, or unlisted file must stop the page from being built, never
ship quietly. Every text pair the pages use must clear WCAG AA in both themes."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from executor.web_assets import (MANIFEST_NAME, PAGE_SCRIPTS, VENDOR_ORDER, WEB,
                                 AssetError, page_assets, read_manifest,
                                 vendor_text)

THEMES = (("light", ":root"), ("dark", ':root[data-theme="dark"]'))
TEXT_PAIRS = [
    ("fg", "bg"), ("fg", "surface"), ("fg", "surface-2"), ("fg", "accent-soft"),
    ("fg-2", "bg"), ("fg-2", "surface"), ("fg-2", "surface-2"), ("fg-2", "accent-soft"),
    ("fg-3", "bg"), ("fg-3", "surface"), ("fg-3", "surface-2"), ("fg-3", "accent-soft"),
    ("accent", "bg"), ("accent", "surface"), ("accent", "surface-2"), ("accent", "accent-soft"),
    ("accent-fg", "accent"), ("ok", "surface"), ("ok", "ok-soft"),
    ("warn", "surface"), ("warn", "warn-soft"), ("bad", "surface"), ("bad", "bad-soft"),
]
FOCUS_PAIRS = [("focus", "surface"), ("focus", "bg")]


def _luminance(color: str) -> float:
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class ShippedAssets(unittest.TestCase):
    def test_every_pinned_library_reads_back_unchanged(self):
        vendor = WEB / "vendor"
        manifest = read_manifest(vendor)
        for key in VENDOR_ORDER:
            vendor_text(key, manifest, vendor)

    def test_both_pages_assemble_from_the_shipped_files(self):
        for page in PAGE_SCRIPTS:
            page_assets(page)


class TamperedCopy(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.web = Path(tmp.name) / "web"
        shutil.copytree(WEB, self.web)
        self.vendor = self.web / "vendor"
        self.manifest_path = self.vendor / MANIFEST_NAME

    def _manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _write_manifest(self, data: dict) -> None:
        self.manifest_path.write_text(json.dumps(data), encoding="utf-8")

    def test_a_library_edited_after_pinning_is_refused(self):
        target = self.vendor / "d3" / "d3.min.js"
        target.write_bytes(target.read_bytes() + b";")
        with self.assertRaisesRegex(AssetError, "changed since it was pinned"):
            page_assets("parent", web=self.web)

    def test_a_vendor_file_the_manifest_does_not_list_is_refused(self):
        (self.vendor / "extra.js").write_text("void 0;", encoding="utf-8")
        with self.assertRaisesRegex(AssetError, "not in manifest: extra.js"):
            page_assets("parent", web=self.web)

    def test_a_manifest_with_an_unknown_schema_is_refused(self):
        data = self._manifest()
        data["schema"] = 2
        self._write_manifest(data)
        with self.assertRaisesRegex(AssetError, "schema"):
            read_manifest(self.vendor)

    def test_a_manifest_that_lists_a_key_twice_is_refused(self):
        data = self._manifest()
        data["files"].append(dict(data["files"][0]))
        self._write_manifest(data)
        with self.assertRaisesRegex(AssetError, "more than once"):
            read_manifest(self.vendor)

    def test_a_library_with_no_pin_cannot_be_read(self):
        data = self._manifest()
        data["files"] = [e for e in data["files"] if e["key"] != "htm"]
        self._write_manifest(data)
        with self.assertRaisesRegex(AssetError, "no vendor entry for 'htm'"):
            vendor_text("htm", read_manifest(self.vendor), self.vendor)

    def test_a_library_without_a_pin_blocks_the_page(self):
        data = self._manifest()
        data["files"] = [e for e in data["files"] if e["key"] != "htm"]
        self._write_manifest(data)
        with self.assertRaisesRegex(AssetError, "not in manifest"):
            page_assets("initiative", web=self.web)

    def test_an_unknown_page_is_refused(self):
        with self.assertRaisesRegex(AssetError, "unknown page"):
            page_assets("settings", web=self.web)


class TextContrast(unittest.TestCase):
    """Every text pair the pages use clears WCAG AA in both themes. Read from the
    shipped tokens, so a palette edit that breaks contrast fails here."""

    def _tokens(self, selector: str) -> dict[str, str]:
        css = (WEB / "base.css").read_text(encoding="utf-8")
        match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
        if match is None:
            self.fail(f"no token block for {selector!r}")
        return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", match.group(1)))

    def test_text_pairs_meet_aa_in_both_themes(self):
        for theme, selector in THEMES:
            tokens = self._tokens(selector)
            for fg, bg in TEXT_PAIRS:
                with self.subTest(theme=theme, pair=f"{fg} on {bg}"):
                    self.assertGreaterEqual(_contrast(tokens[fg], tokens[bg]), 4.5)

    def test_focus_ring_meets_non_text_contrast_in_both_themes(self):
        for theme, selector in THEMES:
            tokens = self._tokens(selector)
            for fg, bg in FOCUS_PAIRS:
                with self.subTest(theme=theme, pair=f"{fg} on {bg}"):
                    self.assertGreaterEqual(_contrast(tokens[fg], tokens[bg]), 3.0)


if __name__ == "__main__":
    unittest.main()
