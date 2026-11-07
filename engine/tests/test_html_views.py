# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The explorer pages are offline, pinned, and inert. These tests check what the
browser enforces: the policy admits exactly the shipped code, the model is
embedded without a way out of its tag, nothing is fetched over the network, and
one model always gives one page."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _live import Live
from executor import __version__
from executor.html_views import island, render_initiative_page, render_parent_page
from executor.paths import view_file
from executor.view_model import initiative_model, initiative_row, root_model
from executor.views import render_plan, render_root_plan, store_info
from executor.web_assets import WEB as WEB_TREE
from executor.web_assets import PageAssets


def _folded(title: str = "Demo") -> dict:
    return {
        "phase": "execution", "phase_state": {"execution": "in_progress"}, "done": False,
        "seq": 2, "last_ts": "2026-01-01T00:00:02Z",
        "tasks": {"INIT-1-P01-T01": {"title": title, "state": "complete",
                                     "plan": "INIT-1-P01", "depends_on": []}},
        "dispatches": {}, "answered": {}, "evidence": {}, "critiques": {},
        "entities": {"INIT-1": {"type": "initiative"},
                     "INIT-1-P01-T01": {"type": "task"}},
        "edges": [], "artifacts": {}, "changes": {}, "rulings": [],
        "needs_ruling": [], "policy": {},
    }


def _model(title: str = "Demo") -> dict:
    return initiative_model(
        init_id="INIT-1", title="Demo", folded=_folded(title), events=[], criteria=[],
        store=store_info({"engine_version": __version__, "store_version": "v2"}),
        home="", parent_href="../../views/index.html")


def _digest(text: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


def _search(pattern: str, text: str, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    assert match is not None, f"no match for {pattern!r}"
    return match.group(1)


def _policy(page: str) -> dict[str, str]:
    content = _search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', page)
    directives = {}
    for part in html.unescape(content).split(";"):
        name, _, value = part.strip().partition(" ")
        directives[name] = value
    return directives


def _inline(page: str, tag: str) -> str:
    return _search(rf"<{tag}>(.*?)</{tag}>", page, re.DOTALL)


def _embedded(page: str) -> dict:
    return json.loads(_search(r'<script type="application/json" id="executor-model">(.*?)</script>',
                              page, re.DOTALL))


class Policy(unittest.TestCase):
    def test_the_policy_admits_exactly_the_inline_script_and_style(self):
        page = render_initiative_page(_model())
        policy = _policy(page)
        self.assertEqual(policy["script-src"], _digest(_inline(page, "script")))
        self.assertEqual(policy["style-src"], _digest(_inline(page, "style")))

    def test_the_policy_refuses_the_network_and_any_default_source(self):
        policy = _policy(render_initiative_page(_model()))
        self.assertEqual(policy["default-src"], "'none'")
        self.assertEqual(policy["connect-src"], "'none'")

    def test_the_initiative_page_frames_nothing_and_the_parent_frames_its_pages(self):
        self.assertEqual(_policy(render_initiative_page(_model()))["frame-src"], "'none'")
        self.assertEqual(_policy(render_parent_page(_root([]))) ["frame-src"], "'self'")

    def test_the_policy_is_the_same_text_the_page_inlines_even_for_the_parent(self):
        page = render_parent_page(_root([]))
        self.assertEqual(_policy(page)["script-src"], _digest(_inline(page, "script")))


class Offline(unittest.TestCase):
    def test_no_element_or_stylesheet_loads_a_remote_resource(self):
        page = render_initiative_page(_model())
        self.assertIsNone(re.search(r"""(src|href)\s*=\s*["']?https?:""", page))
        self.assertIsNone(re.search(r"url\(\s*[\"']?https?:", page))
        self.assertNotIn("@import", page)


class Island(unittest.TestCase):
    def test_a_hostile_title_cannot_close_the_data_tag_or_add_markup(self):
        hostile = "</script><img src=x onerror=alert(1)>"
        page = render_initiative_page(_model(title=hostile))
        self.assertEqual(page.count("</script>"), 2)
        self.assertNotIn("<img src=x", page)

    def test_the_embedded_model_reads_back_equal_to_the_model(self):
        model = _model(title="a & b <c> \u2028 é")
        self.assertEqual(_embedded(render_initiative_page(model)), model)

    def test_line_separators_are_escaped_so_the_text_stays_on_one_line(self):
        text = island({"t": "x\u2028y\u2029z"})
        self.assertNotIn("\u2028", text)
        self.assertNotIn("\u2029", text)

    def test_a_script_that_would_close_its_own_tag_is_never_built(self):
        leaky = PageAssets(script="var x = '</script>';", style="")
        with mock.patch("executor.html_views.page_assets", return_value=leaky):
            with self.assertRaisesRegex(ValueError, "close their own tag"):
                render_initiative_page(_model())


class Determinism(unittest.TestCase):
    def test_one_model_always_gives_one_page(self):
        self.assertEqual(render_initiative_page(_model()), render_initiative_page(_model()))

    def test_the_parent_lists_its_initiatives_in_the_order_the_model_gives(self):
        rows = [_row("INIT-2", "2026-01-02T00:00:00Z"), _row("INIT-1", "2026-01-01T00:00:00Z")]
        page = render_parent_page(_root(rows))
        self.assertEqual([r["id"] for r in _embedded(page)["initiatives"]], ["INIT-2", "INIT-1"])


class StoreVerdict(unittest.TestCase):
    def test_a_store_written_by_this_engine_is_current(self):
        verdict = store_info({"engine_version": __version__, "store_version": "v2"})["verdict"]
        self.assertEqual(verdict, "current")

    def test_a_store_from_an_older_engine_major_asks_for_a_migration(self):
        verdict = store_info({"engine_version": "0.0.1", "store_version": "v2"})["verdict"]
        self.assertEqual(verdict, "store_outdated")

    def test_a_store_from_a_newer_engine_major_asks_for_an_upgrade(self):
        verdict = store_info({"engine_version": "99.0.0", "store_version": "v2"})["verdict"]
        self.assertEqual(verdict, "engine_too_old")

    def test_an_old_layout_is_flagged_even_when_the_engine_matches(self):
        verdict = store_info({"engine_version": __version__, "store_version": "v1"})["verdict"]
        self.assertEqual(verdict, "store_outdated")


class RenderedFromAJournal(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def test_the_initiative_page_is_written_for_its_initiative_and_links_back(self):
        page = render_plan(self.init)[view_file(self.init.idir, "index.html")]
        model = _embedded(page)
        self.assertEqual(model["init"]["id"], self.init.id)
        self.assertEqual(model["init"]["parent_href"], "../../views/index.html")

    def test_the_parent_page_lists_each_initiative_with_a_link_to_its_page(self):
        from executor.paths import root_views_file
        page = render_root_plan(self.live.root)[root_views_file(self.live.root)]
        rows = _embedded(page)["initiatives"]
        self.assertEqual([r["id"] for r in rows], [self.init.id])
        self.assertEqual(rows[0]["href"], f"../{self.init.id}/views/index.html")
        self.assertNotIn(str(Path.home()), page)


def _row(init_id: str, last_ts: str) -> dict:
    model = initiative_model(init_id=init_id, title=init_id, folded=_folded(),
                             events=[], criteria=[], store=store_info({"engine_version": __version__,
                                                                        "store_version": "v2"}))
    model["init"]["last_ts"] = last_ts
    return initiative_row(model, href=f"../{init_id}/views/index.html")


def _root(rows: list[dict]) -> dict:
    return root_model(rows, store_info({"engine_version": __version__, "store_version": "v2"}))


class ExplorerAvailability(unittest.TestCase):
    """The skill bundle ships Python only. With no browser assets, the explorer
    must skip cleanly and the markdown views must still be complete."""

    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)

    def test_an_install_without_browser_assets_reports_the_explorer_unavailable(self):
        from executor import views as V
        with tempfile.TemporaryDirectory() as empty:
            with mock.patch("executor.web_assets.WEB", Path(empty)):
                self.assertFalse(V.explorer_available())

    def test_without_assets_the_view_set_is_the_markdown_projections_alone(self):
        from executor import views as V
        with tempfile.TemporaryDirectory() as empty, \
             mock.patch("executor.web_assets.WEB", Path(empty)):
            files = V.render_plan(self.live.init)
        self.assertFalse(any(p.name == "index.html" for p in files))
        self.assertTrue(any(p.name == "index.md" for p in files))

    def test_without_assets_the_parent_index_is_empty_not_an_error(self):
        from executor import views as V
        with tempfile.TemporaryDirectory() as empty, \
             mock.patch("executor.web_assets.WEB", Path(empty)):
            self.assertEqual(V.render_root_plan(self.live.root), {})

    def test_a_stray_file_named_like_an_initiative_is_not_treated_as_a_store(self):
        from executor import views as V
        (self.live.root / ".executor" / "INIT-9999").write_text("not a store", encoding="utf-8")
        page = next(iter(V.render_root_plan(self.live.root).values()))
        ids = [r["id"] for r in _embedded(page)["initiatives"]]
        self.assertNotIn("INIT-9999", ids)

    def test_a_tampered_vendor_file_fails_the_build_instead_of_hiding_the_explorer(self):
        from executor import views as V
        with tempfile.TemporaryDirectory() as copy:
            web = Path(copy) / "web"
            import shutil
            shutil.copytree(WEB_TREE, web)
            target = web / "vendor" / "d3" / "d3.min.js"
            target.write_bytes(target.read_bytes() + b";")
            with mock.patch("executor.web_assets.WEB", web):
                self.assertTrue(V.explorer_available())
                from executor.web_assets import AssetError
                with self.assertRaisesRegex(AssetError, "changed since it was pinned"):
                    V.render_initiative_page_text(self.live.init)


if __name__ == "__main__":
    unittest.main()
