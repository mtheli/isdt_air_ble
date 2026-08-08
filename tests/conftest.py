"""Pytest setup for ISDT Air BLE unit tests.

The parser module lives under ``custom_components/isdt_air_ble`` and uses
relative imports (``from .const import ...``).  Putting that directory's
parent on ``sys.path`` lets the tests do ``from isdt_air_ble.parser
import ...`` without standing up a full Home Assistant test harness.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CUSTOM_COMPONENTS = REPO_ROOT / "custom_components"
if str(CUSTOM_COMPONENTS) not in sys.path:
    sys.path.insert(0, str(CUSTOM_COMPONENTS))

# ``isdt_air_ble/__init__.py`` is the integration's setup entry point and
# imports Home Assistant at module level, which would drag the whole HA
# runtime into a plain ``import isdt_air_ble.parser``. Register the package
# by hand with only its ``__path__`` set, so submodules like ``const`` and
# ``parser`` resolve and their relative imports work, while ``__init__.py``
# is never executed. Modules under test must stay free of HA imports.
if "isdt_air_ble" not in sys.modules:
    package = types.ModuleType("isdt_air_ble")
    package.__path__ = [str(CUSTOM_COMPONENTS / "isdt_air_ble")]
    sys.modules["isdt_air_ble"] = package
