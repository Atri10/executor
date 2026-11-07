# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Assets for the explorer pages, read from disk and checked before use.

Vendored browser libraries are pinned by SHA-256 in `web/vendor/manifest.json`.
A library file that differs from its pin, or a file in `vendor/` that the
manifest does not list, is refused. A page therefore runs only the code that
was reviewed and pinned.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"
MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA = 1

# Each library reads globals that the ones before it set, so this is load order.
VENDOR_ORDER = ("preact", "preact-hooks", "htm", "d3", "minisearch")
PAGE_SCRIPTS = {"initiative": ("ui.js", "initiative.js"), "parent": ("ui.js", "parent.js")}
PAGE_STYLES = {"initiative": ("base.css", "initiative.css"), "parent": ("base.css", "parent.css")}


class AssetError(RuntimeError):
    """A pinned library changed, a vendor file is unlisted, or the page is unknown."""


@dataclass(frozen=True)
class PageAssets:
    """The exact text the renderer inlines. Its hashes go into the CSP."""

    script: str
    style: str


def read_manifest(vendor: Path) -> dict[str, dict]:
    data = json.loads((vendor / MANIFEST_NAME).read_text(encoding="utf-8"))
    if data.get("schema") != MANIFEST_SCHEMA:
        raise AssetError(f"vendor manifest schema {data.get('schema')!r} is not {MANIFEST_SCHEMA}")
    entries = {entry["key"]: entry for entry in data["files"]}
    if len(entries) != len(data["files"]):
        raise AssetError("vendor manifest lists a key more than once")
    return entries


def vendor_text(key: str, manifest: dict[str, dict], vendor: Path) -> str:
    entry = manifest.get(key)
    if entry is None:
        raise AssetError(f"no vendor entry for {key!r}")
    data = (vendor / entry["path"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise AssetError(f"vendor file changed since it was pinned: {entry['path']}")
    return data.decode("utf-8")


def unlisted_vendor_files(manifest: dict[str, dict], vendor: Path) -> list[str]:
    pinned = {entry["path"] for entry in manifest.values()}
    licenses = {entry["license_file"] for entry in manifest.values() if entry.get("license_file")}
    present = {p.relative_to(vendor).as_posix() for p in vendor.rglob("*")
               if p.is_file() and p.name != MANIFEST_NAME}
    return sorted(present - pinned - licenses)


def assets_present(*, web: Path | None = None) -> bool:
    """True when every file the explorer needs is on disk. This checks presence
    only: pins are verified when a page is built, so a tampered file still fails
    loudly instead of hiding the explorer."""
    tree = WEB if web is None else web
    files = {f for group in (*PAGE_SCRIPTS.values(), *PAGE_STYLES.values()) for f in group}
    return all((tree / name).is_file() for name in [f"vendor/{MANIFEST_NAME}", *sorted(files)])


def page_assets(page: str, *, web: Path | None = None) -> PageAssets:
    """The text a page inlines. `web` defaults to the shipped tree, looked up at
    call time so an install or a test can point the loader elsewhere."""
    web = WEB if web is None else web
    if page not in PAGE_SCRIPTS:
        raise AssetError(f"unknown page {page!r}")
    vendor = web / "vendor"
    manifest = read_manifest(vendor)
    extra = unlisted_vendor_files(manifest, vendor)
    if extra:
        raise AssetError("vendor files not in manifest: " + ", ".join(extra))
    libraries = [vendor_text(key, manifest, vendor) for key in VENDOR_ORDER]
    scripts = [(web / name).read_text(encoding="utf-8") for name in PAGE_SCRIPTS[page]]
    styles = [(web / name).read_text(encoding="utf-8") for name in PAGE_STYLES[page]]
    return PageAssets(script="\n".join(libraries + scripts), style="\n".join(styles))
