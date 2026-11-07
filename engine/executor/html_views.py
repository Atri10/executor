# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The explorer's two page shapes: one initiative, and the parent index.

Each page is one file that opens from disk with no network. The script and the
style are inlined, and a Content-Security-Policy admits exactly those two texts
by SHA-256. The model travels as a JSON island that the browser reads and never
executes. One model always renders the same bytes.

Writers must store the returned text as UTF-8 bytes without newline translation:
the policy hashes cover those bytes.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json

from . import __version__
from .web_assets import page_assets

# The island is JSON inside a <script> tag, so these must never appear raw in it.
_ISLAND_ESCAPES = (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                   ("\u2028", "\\u2028"), ("\u2029", "\\u2029"))
# An initiative page embeds no frames. The parent embeds its own initiative pages,
# which are same-origin siblings in the store.
INITIATIVE_FRAMES = "'none'"
PARENT_FRAMES = "'self'"


def island(model: dict) -> str:
    """The model as JSON that cannot close its own tag or open markup."""
    text = json.dumps(model, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    for raw, escaped in _ISLAND_ESCAPES:
        text = text.replace(raw, escaped)
    return text


def _digest(text: str) -> str:
    raw = hashlib.sha256(text.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(raw).decode("ascii") + "'"


def _policy(script: str, style: str, frames: str) -> str:
    return "; ".join([
        "default-src 'none'",
        f"script-src {_digest(script)}",
        f"style-src {_digest(style)}",
        "img-src data:",
        "connect-src 'none'",
        f"frame-src {frames}",
        "base-uri 'none'",
        "form-action 'none'",
    ])


def _page(page: str, title: str, model: dict, frames: str) -> str:
    assets = page_assets(page)
    if "</script" in assets.script.lower() or "</style" in assets.style.lower():
        raise ValueError(f"{page} assets would close their own tag")
    policy = html.escape(_policy(assets.script, assets.style, frames))
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="referrer" content="no-referrer">',
        f'<meta name="generator" content="executor {__version__}">',
        f'<meta http-equiv="Content-Security-Policy" content="{policy}">',
        '<link rel="icon" href="data:,">',
        f"<title>{html.escape(title)}</title>",
        f"<style>{assets.style}</style>",
        "</head>",
        "<body>",
        '<noscript><p class="noscript">This page runs JavaScript. Its data is embedded, '
        "so nothing is fetched.</p></noscript>",
        '<div id="app"></div>',
        f'<script type="application/json" id="executor-model">{island(model)}</script>',
        f"<script>{assets.script}</script>",
        "</body>",
        "</html>",
        "",
    ])


def render_initiative_page(model: dict) -> str:
    init = model["init"]
    return _page("initiative", f"{init['id']} · {init['title'] or 'initiative'}",
                 model, INITIATIVE_FRAMES)


def render_parent_page(model: dict) -> str:
    return _page("parent", "Executor · initiatives", model, PARENT_FRAMES)
