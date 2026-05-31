"""Locate the IOTCONNECT device credentials in the credentials folder.

Makes the package device-agnostic: drop ANY device's downloaded files
(iotcDeviceConfig.json + the device .crt and private-key .pem) into the
credentials directory and they're found automatically — no need to edit config
to match a specific device name. Explicit env overrides still win if set.
"""
from __future__ import annotations

import glob
import os


def _pick(explicit: str, creds_dir: str, patterns: list[str]) -> str:
    if explicit and os.path.isfile(explicit):
        return explicit
    for pat in patterns:
        hits = sorted(glob.glob(os.path.join(creds_dir, pat)))
        if hits:
            return hits[0]
    return explicit  # may be "" or a missing path; caller reports the error


def resolve(creds_dir: str, config_json: str = "", cert: str = "", pkey: str = "") -> tuple[str, str, str]:
    """Return (config_json, cert, pkey), discovering any not explicitly given.

    Conventions (matching IOTCONNECT's device download):
      * config : iotcDeviceConfig.json (or any *.json)
      * cert   : a *.crt (or cert*.pem)
      * key    : pk_*.pem / *key*.pem / *.key (a *.pem that isn't the cert)
    """
    config_json = _pick(config_json, creds_dir, ["iotcDeviceConfig.json", "*.json"])
    cert = _pick(cert, creds_dir, ["*.crt", "cert*.pem"])
    # Avoid re-selecting the cert file when it is a .pem.
    cert_base = os.path.basename(cert) if cert else ""
    key_patterns = ["pk_*.pem", "*private*.pem", "*key*.pem", "*.key"]
    pkey = _pick(pkey, creds_dir, key_patterns)
    if not (pkey and os.path.isfile(pkey)):
        # last resort: any *.pem that isn't the cert
        for hit in sorted(glob.glob(os.path.join(creds_dir, "*.pem"))):
            if os.path.basename(hit) != cert_base:
                pkey = hit
                break
    return config_json, cert, pkey
