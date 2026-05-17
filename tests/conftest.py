"""Pytest setup for ISDT Air BLE unit tests.

The parser module lives under ``custom_components/isdt_air_ble`` and uses
relative imports (``from .const import ...``).  Putting that directory's
parent on ``sys.path`` lets the tests do ``from isdt_air_ble.parser
import ...`` without standing up a full Home Assistant test harness.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CUSTOM_COMPONENTS = REPO_ROOT / "custom_components"
if str(CUSTOM_COMPONENTS) not in sys.path:
    sys.path.insert(0, str(CUSTOM_COMPONENTS))
