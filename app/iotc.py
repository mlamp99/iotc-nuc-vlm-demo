"""Avnet /IOTCONNECT integration using the official lite Python SDK.

Auth is X.509 (auth type 3) on the AWS platform; the device identity, platform
and environment all come from the provided iotcDeviceConfig.json.

Design goal: connectivity is OPTIONAL. If the SDK is missing, credentials are
absent, or the cloud is unreachable, this falls back to a local "log only"
publisher so the perception demo always runs. That is what lets us promise the
package "will run" on the target machine even before the cloud side is verified.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

log = logging.getLogger("iotc")

# A command handler turns (command_name, args) into a human-readable result
# string that gets ack'd back to the platform.
CommandHandler = Callable[[str, list[str]], str]


class _NullClient:
    """Stand-in used when IOTCONNECT is disabled or unavailable."""

    def __init__(self, reason: str):
        log.warning("IOTCONNECT running in LOCAL-ONLY mode: %s", reason)

    def send_telemetry(self, data: dict) -> None:
        log.info("[telemetry-local] %s", data)

    def is_connected(self) -> bool:
        return False

    def disconnect(self) -> None:
        pass


class IotcClient:
    def __init__(
        self,
        config_json: str,
        cert_path: str,
        pkey_path: str,
        enabled: bool,
        command_handler: CommandHandler | None = None,
    ):
        self._command_handler = command_handler
        self._lock = threading.Lock()
        self._client = None

        if not enabled:
            self._client = _NullClient("IOTC_ENABLED=0")
            return

        try:
            self._client = self._build_real_client(config_json, cert_path, pkey_path)
        except Exception as e:  # noqa: BLE001 - never let cloud setup kill the demo
            log.exception("IOTCONNECT init failed; falling back to local-only")
            self._client = _NullClient(f"init error: {e}")

    def _build_real_client(self, config_json: str, cert_path: str, pkey_path: str):
        from avnet.iotconnect.sdk.lite import Client, Callbacks, DeviceConfig

        device_config = DeviceConfig.from_iotc_device_config_json_file(
            device_config_json_path=config_json,
            device_cert_path=cert_path,
            device_pkey_path=pkey_path,
        )
        client = Client(
            config=device_config,
            callbacks=Callbacks(
                command_cb=self._on_command,
                disconnected_cb=self._on_disconnect,
            ),
        )
        log.info("Connecting to IOTCONNECT...")
        client.connect()
        if client.is_connected():
            log.info("IOTCONNECT connected.")
        else:
            log.warning("IOTCONNECT connect() returned but not connected yet.")
        return client

    # --- SDK callbacks --------------------------------------------------
    def _on_disconnect(self, *args, **kwargs):
        log.warning("IOTCONNECT disconnected (will auto-reconnect on next send).")

    def _on_command(self, msg):
        """Adapt the SDK command object to our (name, args) handler and ack."""
        name = (
            getattr(msg, "command_name", None)
            or getattr(msg, "command", None)
            or ""
        )
        args = list(getattr(msg, "command_args", None) or getattr(msg, "args", []) or [])
        log.info("C2D command received: name=%r args=%r", name, args)
        result = "ok"
        try:
            if self._command_handler:
                result = self._command_handler(name, args)
        except Exception as e:  # noqa: BLE001
            log.exception("Command handler error")
            result = f"error: {e}"
        self._ack(msg, result)

    def _ack(self, msg, message: str):
        """Best-effort command acknowledgement (SDK ack APIs vary by version)."""
        try:
            from avnet.iotconnect.sdk.sdklib.mqtt import C2dAck

            status = getattr(C2dAck, "CMD_SUCCESS_WITH_ACK", 6)
            self._client.send_command_ack(msg, status, message)
        except Exception as e:  # noqa: BLE001
            log.debug("Command ack skipped (%s)", e)

    # --- Public API -----------------------------------------------------
    def send_telemetry(self, data: dict) -> None:
        with self._lock:
            try:
                self._client.send_telemetry(data)
            except Exception:  # noqa: BLE001
                log.exception("send_telemetry failed")

    def is_connected(self) -> bool:
        try:
            return bool(self._client.is_connected())
        except Exception:  # noqa: BLE001
            return False

    def disconnect(self) -> None:
        try:
            self._client.disconnect()
        except Exception:  # noqa: BLE001
            pass
