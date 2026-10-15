# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Load `scripts/*.py` as modules for testing.

The scripts are command-line tools, not a package, and one has a hyphen in its
name, so they cannot be imported normally. Loading goes through importlib and
registers the module in `sys.modules` (a `@dataclass` resolves its annotations
through it). A script already loaded from the same file is reused, so every
test module patches and observes one module object.
"""
from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path
from types import ModuleType
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"


def load(filename: str) -> ModuleType:
    path = SCRIPTS / filename
    name = path.stem.replace("-", "_")
    known = sys.modules.get(name)
    if known is not None and getattr(known, "__file__", None) == str(path):
        return known
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_as_main(filename: str, *argv: str) -> int:
    """Execute a script as `__main__` in this process, so its entry-point guard
    counts toward coverage. Returns the exit code the script asked for."""
    with mock.patch.object(sys, "argv", [filename, *argv]):
        try:
            runpy.run_path(str(SCRIPTS / filename), run_name="__main__")
        except SystemExit as e:
            if e.code is None:
                return 0
            return e.code if isinstance(e.code, int) else 1
    raise AssertionError(f"{filename} returned instead of exiting")
