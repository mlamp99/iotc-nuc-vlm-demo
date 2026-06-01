"""Device location for /IOTCONNECT, emitted as a LATLONG attribute value.

IOTCONNECT's LATLONG type needs a numeric value, NOT a quoted string — a quoted
"lat,lon" is treated as a plain string and won't map. So this returns a two-number
array [latitude, longitude] (serializes to JSON as [33.0173, -96.612], no quotes).

Resolution order:
  1. Explicit DEVICE_LAT + DEVICE_LON (best for a fixed install — exact & private).
  2. Optional GEO_AUTODETECT: approximate city-level location from the public IP
     (one lookup at startup, cached). Off by default.

A NUC has no GPS, so there is no live-moving location; this is a fixed/approximate
position. Resolved once and cached.
"""
from __future__ import annotations

import json
import logging
import urllib.request

log = logging.getLogger("location")


class Location:
    def __init__(self, lat: str, lon: str, autodetect: bool):
        self._value = None
        if lat and lon:
            try:
                self._value = [float(lat), float(lon)]
                log.info("Device location (configured): %s", self._value)
            except ValueError:
                log.warning("Invalid DEVICE_LAT/DEVICE_LON: %r, %r", lat, lon)
        elif autodetect:
            self._value = self._ip_lookup()
            if self._value:
                log.info("Device location (IP-estimated): %s", self._value)

    @staticmethod
    def _ip_lookup():
        try:
            with urllib.request.urlopen("http://ip-api.com/json/", timeout=5) as r:
                d = json.loads(r.read().decode())
            if d.get("status") == "success" and "lat" in d and "lon" in d:
                return [float(d["lat"]), float(d["lon"])]
            log.warning("IP geolocation returned no fix")
        except Exception as e:  # noqa: BLE001
            log.warning("IP geolocation failed: %s", e)
        return None

    @property
    def value(self):
        """LATLONG value [lat, lon] (numbers), or None if no location available."""
        return self._value
