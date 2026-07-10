"""Cross-device hazard actions via the local /IOTCONNECT MCP server.

When the scene turns hazardous, send a C2D command to ANOTHER device on the
same /IOTCONNECT account (e.g. `board-user-led on` to an NXP FRDM i.MX95 acting
as a warning light); send the matching "off" once the scene has stayed clear
for a debounce period.

Deliberately deterministic — no LLM decides anything here. The only side effect
this module can ever produce is the single configured command to the single
configured device (same allowlist discipline as the genai-flow-demo agent).

Requires the `iotconnect-mcp-server` package running on the HOST (the MCP
server wraps the /IOTCONNECT REST API, which is what allows one device to
command another — the lite device SDK alone cannot):

    pipx install iotconnect-mcp-server
    iotconnect-cli configure          # one-time auth
    IOTC_MCP_TRANSPORT=streamable-http IOTC_MCP_PORT=8000 iotc-mcp-server

Disabled unless HAZARD_ACTIONS_ENABLED=1 and HAZARD_LIGHT_DUID are set.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("hazard")

_RETRY_BACKOFF_S = 60.0  # after a failed send, don't hammer an absent server


class HazardActions:
    def __init__(self, state, *, mcp_url: str, duid: str, command: str,
                 source: str = "any", off_delay_s: float = 10.0,
                 on_args: str = "on", off_args: str = "off"):
        self._state = state
        self._mcp_url = mcp_url
        self._duid = duid
        self._command = command
        self._source = source.strip().lower()
        self._off_delay_s = off_delay_s
        # Command args for danger/clear. "on"/"off" suits board-user-led;
        # RGB triples like "255 0 0" / "0 0 0" suit set-user-led.
        self._on_args = on_args
        self._off_args = off_args
        self._thread = threading.Thread(target=self._run, daemon=True, name="hazard-actions")

    def start(self):
        log.info(
            "Hazard actions armed: %s -> '%s on/off' to %r (source=%s, off-delay=%.0fs)",
            self._mcp_url, self._command, self._duid, self._source, self._off_delay_s,
        )
        self._thread.start()

    # --- decision ---------------------------------------------------------
    def _danger(self, snap: dict) -> bool:
        detector = snap["safety_alert"] != "clear" or snap["person_in_danger_zone"]
        vlm = bool(snap["hazard_detected"])
        if self._source == "detector":
            return detector
        if self._source == "vlm":
            return vlm
        return detector or vlm  # "any"

    def _run(self):
        stop = self._state.stop
        applied: bool | None = None  # last state we successfully sent (None = never)
        clear_since: float | None = None
        blocked_until = 0.0
        while not stop.is_set():
            snap = self._state.snapshot()
            now = time.monotonic()
            if self._danger(snap):
                clear_since = None
                desired = True
            else:
                if clear_since is None:
                    clear_since = now
                # Hold the light on until the scene has stayed clear a while,
                # so a looping demo video doesn't strobe it.
                desired = False if (now - clear_since) >= self._off_delay_s else applied
            if desired is not None and desired != applied and now >= blocked_until:
                if self._send(self._on_args if desired else self._off_args):
                    applied = desired
                else:
                    blocked_until = now + _RETRY_BACKOFF_S
            stop.wait(0.5)

    # --- MCP plumbing -----------------------------------------------------
    def _send(self, arg: str) -> bool:
        try:
            self._mcp_call("command_send", {
                "duid": self._duid, "command_name": self._command, "args": arg,
            })
            log.info("Sent '%s %s' to %s via /IOTCONNECT", self._command, arg, self._duid)
            return True
        except Exception as e:  # noqa: BLE001 - actions must never kill the demo
            log.warning("Hazard action failed (%s); retrying in %.0fs", e, _RETRY_BACKOFF_S)
            return False

    def _mcp_call(self, tool: str, args: dict, timeout_s: float = 30.0):
        import asyncio
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async def run():
            async with streamablehttp_client(self._mcp_url) as (r, w, _):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    res = await asyncio.wait_for(s.call_tool(tool, args), timeout=timeout_s)
                    text = res.content[0].text if res.content else ""
                    if "Not logged in" in text:
                        raise RuntimeError("MCP server not authenticated - run: iotconnect-cli configure")
                    return text

        return asyncio.run(asyncio.wait_for(run(), timeout=timeout_s + 15))
