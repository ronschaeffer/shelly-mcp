"""Gen1 settings write — the Gen1 counterpart of ``*.SetConfig``.

Gen1 devices change configuration with ``GET /settings[/<path>]?key=value`` (e.g.
``/settings/relay/0?default_state=off``, ``/settings?name=...``). The generic engine can
only read Gen1 ``/settings``; this tool closes that gap behind the same safety model as
the other mutating tools: ``confirm:true``, audit logging with secrets masked, and an
extra ``i_understand_disconnect`` gate for Wi-Fi sub-paths. Login/auth is not writable.
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import backend_errors, get_audit, get_registry, mcp
from shelly_mcp.audit import redact_config
from shelly_mcp.backends.base import BackendError
from shelly_mcp.methods import GEN1_SET_SETTINGS, gen1_settings_request
from shelly_mcp.models import Generation


@mcp.tool(annotations={"destructiveHint": True})
@backend_errors
async def shelly_gen1_settings_set(
    device: str,
    values: dict[str, Any],
    path: str = "",
    confirm: bool = False,
    i_understand_disconnect: bool = False,
) -> dict[str, Any]:
    """Change settings on a **Gen1** device (``GET /settings[/<path>]?key=value``).

    ``path`` is the sub-path under ``/settings``: ``""`` for device-level settings
    (``name``, ``led_status_disable``, ``sntp_server``, ``tzautodetect``, ...),
    ``relay/0``, ``light/0``, ``color/0``, ``white/0``, ``roller/0``, ``mqtt``, ``coiot``,
    ``cloud``, ``actions`` (list values become repeated keys, e.g. ``urls[]``).
    ``values`` maps setting names to str/int/float/bool (or lists of them).
    Read the current values first with ``shelly_get_config``. Requires ``confirm:true``;
    Wi-Fi paths (``sta``, ``sta1``, ``ap``) also need ``i_understand_disconnect:true``.
    Gen2+ devices: use ``shelly_rpc_write`` with ``<Component>.SetConfig`` instead.
    Returns the device's updated settings section (credentials masked). Audit-logged.
    """
    ident = await get_registry().require_identity(device)
    if ident.gen is not Generation.GEN1:
        return {
            "error": f"'{device}' is Gen{int(ident.gen)}; use shelly_rpc_write with "
            "<Component>.SetConfig for Gen2+ devices"
        }
    if ident.backend == "cloud":
        return {"error": f"'{device}' is reached via Shelly Cloud; Gen1 settings need LAN access"}
    try:
        url_path, _ = gen1_settings_request(path, values, allow_wifi_change=i_understand_disconnect)
    except ValueError as exc:
        return {"error": str(exc)}
    safe = {"path": url_path, "values": redact_config(values)}
    if not confirm:
        return {
            "confirmed": False,
            "would_call": {"device": device, "method": GEN1_SET_SETTINGS, "params": safe},
            "message": (
                f"This changes settings on '{device}'. Re-call with confirm=true to proceed."
            ),
        }
    params = {"path": path, "values": values, "allow_wifi_change": i_understand_disconnect}
    backend = await get_registry().get_backend(device)
    try:
        result = await backend.call(GEN1_SET_SETTINGS, params)
    except BackendError as exc:
        get_audit().record(
            device=device, method=GEN1_SET_SETTINGS, params=safe, ok=False, error=str(exc)
        )
        raise
    masked = redact_config(result)
    get_audit().record(device=device, method=GEN1_SET_SETTINGS, params=safe, ok=True, result=masked)
    return {"device": device, "path": url_path, "confirmed": True, "result": masked}
