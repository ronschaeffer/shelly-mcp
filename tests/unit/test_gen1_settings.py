"""Gen1 settings write: validation, gates, Gen1-only, secrets masked, REST mapping."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from shelly_mcp.methods import gen1_request_for, gen1_settings_request
from shelly_mcp.models import Generation
from shelly_mcp.tools.gen1 import shelly_gen1_settings_set


@pytest.fixture
def gen1(wire: Any) -> Any:
    wire.gen = Generation.GEN1
    from shelly_mcp.app import get_registry

    get_registry()._ident = get_registry()._ident.model_copy(  # type: ignore[attr-defined]
        update={"gen": Generation.GEN1, "backend": "local_rest"}
    )
    return wire


def test_request_builds_path_and_pairs() -> None:
    path, q = gen1_settings_request("relay/0", {"default_state": "off", "auto_off": 0})
    assert path == "/settings/relay/0"
    assert q == [("default_state", "off"), ("auto_off", "0")]


def test_request_top_level_bool_and_list() -> None:
    path, q = gen1_settings_request("", {"led_status_disable": True, "urls[]": ["a", "b"]})
    assert path == "/settings"
    assert q == [("led_status_disable", "true"), ("urls[]", "a"), ("urls[]", "b")]


@pytest.mark.parametrize("bad", ["../reset", "relay/0/x", "Relay", "a?b=c", "x" * 40])
def test_request_rejects_bad_paths(bad: str) -> None:
    with pytest.raises(ValueError):
        gen1_settings_request(bad, {"x": 1})


def test_request_blocks_login_and_gates_wifi() -> None:
    with pytest.raises(ValueError):
        gen1_settings_request("login", {"enabled": True})
    with pytest.raises(ValueError):
        gen1_settings_request("sta", {"ssid": "x"})
    assert gen1_settings_request("sta", {"ssid": "x"}, allow_wifi_change=True)[0] == "/settings/sta"


def test_request_rejects_bad_keys_and_values() -> None:
    with pytest.raises(ValueError):
        gen1_settings_request("", {"a&b": 1})
    with pytest.raises(ValueError):
        gen1_settings_request("", {"a": {"nested": 1}})
    with pytest.raises(ValueError):
        gen1_settings_request("", {})


def test_rest_mapping_routes_through_validation() -> None:
    assert gen1_request_for("Gen1.SetSettings", {"path": "relay/0", "values": {"x": 1}}) == (
        "/settings/relay/0",
        [("x", "1")],
    )
    with pytest.raises(ValueError):
        gen1_request_for("Gen1.SetSettings", {"path": "ap", "values": {"enabled": False}})


async def test_tool_refuses_gen2(wire: Any) -> None:
    out = await shelly_gen1_settings_set(device="dev", values={"name": "x"}, confirm=True)
    assert "error" in out and "SetConfig" in out["error"]
    assert wire.calls == []


async def test_tool_preview_without_confirm(gen1: Any) -> None:
    out = await shelly_gen1_settings_set(device="dev", path="mqtt", values={"mqtt_pass": "s3cret"})
    assert out["confirmed"] is False
    assert "s3cret" not in str(out)
    assert gen1.calls == []


async def test_tool_executes_and_masks_audit(gen1: Any, tmp_path: Path) -> None:
    out = await shelly_gen1_settings_set(
        device="dev", path="mqtt", values={"enable": True, "mqtt_pass": "s3cret"}, confirm=True
    )
    assert out["confirmed"] is True and out["path"] == "/settings/mqtt"
    method, params = gen1.calls[-1]
    assert method == "Gen1.SetSettings" and params["values"]["mqtt_pass"] == "s3cret"
    assert "s3cret" not in (tmp_path / "audit.jsonl").read_text()


async def test_tool_wifi_needs_ack(gen1: Any) -> None:
    out = await shelly_gen1_settings_set(
        device="dev", path="sta", values={"ssid": "x"}, confirm=True
    )
    assert "error" in out and gen1.calls == []


async def test_list_devices_local_only_without_cloud() -> None:
    """With no cloud configured, configured LAN devices are probed (not an error)."""
    from shelly_mcp.app import set_registry
    from shelly_mcp.client import DeviceRegistry
    from shelly_mcp.config import Config
    from shelly_mcp.models import DeviceIdentity
    from shelly_mcp.tools.read import shelly_list_devices

    cfg = Config.model_validate(
        {"devices": {"lamp": {"ip": "10.0.0.2", "location": "study"}, "gone": {"ip": "10.0.0.3"}}}
    )
    reg = DeviceRegistry(cfg)

    async def fake_identify(device: str) -> DeviceIdentity:
        if device == "gone":
            from shelly_mcp.backends.base import DeviceUnreachable

            raise DeviceUnreachable("timeout")
        return DeviceIdentity(id="abc", name=device, location="study", gen=Generation.GEN1)

    reg.identify = fake_identify  # type: ignore[method-assign]
    set_registry(reg)
    try:
        out = await shelly_list_devices()
    finally:
        set_registry(None)
    assert out["count"] == 1 and out["devices"][0]["name"] == "lamp"
    assert out["unreachable"] == {"gone": "timeout"}
