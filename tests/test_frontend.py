"""Tests for the bundled-card registration (frontend.py).

The card must end up in the Lovelace resource registry in storage mode and
fall back to ``add_extra_js_url`` when the registry is read-only (YAML mode)
or unavailable. A leftover standalone install raises a repair issue.
"""

from __future__ import annotations

import asyncio
import functools
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("homeassistant")

from isdt_air_ble.frontend import (  # noqa: E402
    CARD_URL,
    ISSUE_STANDALONE_CARD,
    async_ensure_card_resource,
    async_register_card,
    async_remove_card_resource,
)

VERSION = json.loads(
    (
        Path(__file__).parents[1]
        / "custom_components"
        / "isdt_air_ble"
        / "manifest.json"
    ).read_text(encoding="utf-8")
)["version"]
VERSIONED_URL = f"{CARD_URL}?v={VERSION}"


class FakeStorageResources:
    """Writable resource collection mimicking ResourceStorageCollection."""

    def __init__(self, items: list[dict] | None = None) -> None:
        self.items = items or []
        self.loaded = False
        self._next_id = 1000

    async def async_load(self) -> None:
        pass

    def async_items(self) -> list[dict]:
        return self.items

    async def async_create_item(self, data: dict) -> dict:
        item = {"id": str(self._next_id), "type": data["res_type"], "url": data["url"]}
        self._next_id += 1
        self.items.append(item)
        return item

    async def async_update_item(self, item_id: str, data: dict) -> dict:
        for item in self.items:
            if item["id"] == item_id:
                item.update({"url": data["url"]})
                return item
        raise KeyError(item_id)

    async def async_delete_item(self, item_id: str) -> None:
        self.items[:] = [item for item in self.items if item["id"] != item_id]


class FakeYamlResources:
    """Read-only resource collection mimicking ResourceYAMLCollection."""

    loaded = True

    def __init__(self, items: list[dict] | None = None) -> None:
        self.items = items or []

    def async_items(self) -> list[dict]:
        return self.items


@pytest.fixture
def hass():
    """A hass stand-in with the parts frontend.py touches."""
    http = MagicMock()
    http.async_register_static_paths = AsyncMock()
    return SimpleNamespace(data={}, http=http)


@pytest.fixture(autouse=True)
def mock_integration_version():
    with patch(
        "isdt_air_ble.frontend.async_get_integration",
        AsyncMock(return_value=SimpleNamespace(version=VERSION)),
    ):
        yield


@pytest.fixture
def mock_extra_js():
    with patch("isdt_air_ble.frontend.add_extra_js_url") as mock:
        yield mock


@pytest.fixture
def mock_issues():
    with patch("isdt_air_ble.frontend.ir") as mock:
        yield mock


def run_async(test):
    """Run an async test without an asyncio pytest plugin."""

    @functools.wraps(test)
    def wrapper(*args, **kwargs):
        asyncio.run(test(*args, **kwargs))

    return wrapper


def _set_resources(hass, resources) -> None:
    hass.data["lovelace"] = SimpleNamespace(resources=resources)


@run_async
async def test_resource_created(hass, mock_extra_js, mock_issues) -> None:
    resources = FakeStorageResources()
    _set_resources(hass, resources)

    await async_register_card(hass)

    assert [item["url"] for item in resources.items] == [VERSIONED_URL]
    assert resources.items[0]["type"] == "module"
    mock_extra_js.assert_not_called()


@run_async
async def test_resource_updated_in_place_and_deduped(hass, mock_extra_js, mock_issues) -> None:
    resources = FakeStorageResources(
        [
            {"id": "1", "type": "module", "url": f"{CARD_URL}?v=0.0.1"},
            {"id": "2", "type": "module", "url": CARD_URL},
        ]
    )
    _set_resources(hass, resources)

    await async_register_card(hass)

    assert resources.items == [{"id": "1", "type": "module", "url": VERSIONED_URL}]


@run_async
async def test_resource_already_current(hass, mock_extra_js, mock_issues) -> None:
    resources = FakeStorageResources(
        [{"id": "1", "type": "module", "url": VERSIONED_URL}]
    )
    resources.async_create_item = AsyncMock()
    resources.async_update_item = AsyncMock()
    _set_resources(hass, resources)

    await async_register_card(hass)

    resources.async_create_item.assert_not_called()
    resources.async_update_item.assert_not_called()


@run_async
async def test_dict_shaped_lovelace_data(hass, mock_extra_js, mock_issues) -> None:
    """Cores before 2025.2 keep the Lovelace data in a plain dict."""
    resources = FakeStorageResources()
    hass.data["lovelace"] = {"resources": resources}

    await async_register_card(hass)

    assert [item["url"] for item in resources.items] == [VERSIONED_URL]


@run_async
async def test_yaml_mode_falls_back_to_extra_js(hass, mock_extra_js, mock_issues) -> None:
    _set_resources(hass, FakeYamlResources())

    await async_register_card(hass)

    mock_extra_js.assert_called_once_with(hass, VERSIONED_URL)


@run_async
async def test_no_lovelace_falls_back_to_extra_js(hass, mock_extra_js, mock_issues) -> None:
    await async_register_card(hass)

    mock_extra_js.assert_called_once_with(hass, VERSIONED_URL)


@run_async
async def test_registry_error_falls_back_to_extra_js(hass, mock_extra_js, mock_issues) -> None:
    resources = FakeStorageResources()
    resources.async_create_item = AsyncMock(side_effect=RuntimeError("boom"))
    _set_resources(hass, resources)

    await async_register_card(hass)

    mock_extra_js.assert_called_once_with(hass, VERSIONED_URL)


@run_async
async def test_yaml_fallback_registered_once_per_run(hass, mock_extra_js, mock_issues) -> None:
    _set_resources(hass, FakeYamlResources())

    await async_register_card(hass)
    await async_ensure_card_resource(hass)
    await async_ensure_card_resource(hass)

    mock_extra_js.assert_called_once()


@pytest.mark.parametrize(
    "standalone",
    [
        "/hacsfiles/isdt_air_card/isdt-charger-card.js",
        # A manual install, with the cache-buster typo seen in the wild
        "/local/isdt_air_card/dist/isdt-charger-card.js?v0.5",
    ],
)
@run_async
async def test_standalone_leftover_creates_repair_issue(
    hass, mock_extra_js, mock_issues, standalone
) -> None:
    resources = FakeStorageResources([{"id": "1", "type": "module", "url": standalone}])
    _set_resources(hass, resources)

    await async_register_card(hass)

    mock_issues.async_create_issue.assert_called_once()
    args, kwargs = mock_issues.async_create_issue.call_args
    assert args[2] == ISSUE_STANDALONE_CARD
    assert kwargs["translation_placeholders"] == {"url": standalone}
    # The leftover is reported, not deleted; ours is registered next to it.
    assert [item["url"] for item in resources.items] == [standalone, VERSIONED_URL]


@run_async
async def test_own_resource_does_not_trigger_repair_issue(hass, mock_extra_js, mock_issues) -> None:
    _set_resources(
        hass, FakeStorageResources([{"id": "1", "type": "module", "url": CARD_URL}])
    )

    await async_register_card(hass)

    mock_issues.async_create_issue.assert_not_called()
    mock_issues.async_delete_issue.assert_called_once()


@run_async
async def test_remove_card_resource(hass) -> None:
    other = "/hacsfiles/some-other-card/card.js"
    resources = FakeStorageResources(
        [
            {"id": "1", "type": "module", "url": VERSIONED_URL},
            {"id": "2", "type": "module", "url": CARD_URL},
            {"id": "3", "type": "module", "url": other},
        ]
    )
    _set_resources(hass, resources)

    await async_remove_card_resource(hass)

    assert [item["url"] for item in resources.items] == [other]


@run_async
async def test_remove_card_resource_yaml_mode_is_noop(hass) -> None:
    _set_resources(hass, FakeYamlResources([{"id": "1", "url": VERSIONED_URL}]))

    await async_remove_card_resource(hass)


@run_async
async def test_resource_restored_after_remove_and_readd(hass, mock_extra_js, mock_issues) -> None:
    """Remove the last entry, add one again: the resource comes back.

    ``async_setup`` runs only once per run, so the entry setup has to
    restore the resource.
    """
    resources = FakeStorageResources()
    _set_resources(hass, resources)

    await async_register_card(hass)
    await async_remove_card_resource(hass)
    assert resources.items == []

    await async_ensure_card_resource(hass)

    assert [item["url"] for item in resources.items] == [VERSIONED_URL]
    mock_extra_js.assert_not_called()
