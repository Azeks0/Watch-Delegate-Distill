#!/usr/bin/env python3
"""Entry point for the SAM 3.1 "Watch, Delegate, Distill" pipeline.

The implementation lives in the `sam_pipeline` package next to this file; run
`python sam_ego4d.py --help` for the full description of both modes and the budget rules.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sam_pipeline.cli import main

if __name__ == "__main__":
    main()
