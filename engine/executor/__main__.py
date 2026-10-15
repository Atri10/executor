#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""`python -m executor` — the same CLI as `python engine/executor/cli.py`.

Exists so a launch needs no shell, no shebang bit, and no path arithmetic:
PYTHONPATH=engine python3 -m executor next
"""
from __future__ import annotations

import sys

from executor.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
