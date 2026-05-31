"""Device location for /IOTCONNECT, formatted as a LATLONG attribute value
("latitude,longitude" string — what IOTCONNECT/AWS map widgets expect).

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
            self._value = f"{lat},{lon}"
            log.info("Device location (configured): %s", self._value)
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
                return f"{d['lat']},{d['lon']}"
            log.warning("IP geolocation returned no fix")
        except Exception as e:  # noqa: BLE001
            log.warning("IP geolocation failed: %s", e)
        return None

    @property
    def value(self):
        """LATLONG string 'lat,lon', or None if no location is available."""
        return self._value
