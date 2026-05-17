"""Simulated data for EPA Victoria Air Quality integration.

Provides deterministic, realistic EPA air monitoring site and observation data
for use by the WSGI simulator and tests.

Theory of operation:

* Simulated sites represent real EPA Victoria monitoring station types (Standard and Sensor).
* PM2.5 readings vary by time of day using a simple diurnal pattern (higher morning/evening, lower midday).
* Health advice strings are derived from PM2.5 concentration ranges per EPA Victoria guidelines.
* API keys "test-key-1" and "test-key-2" are valid; any other key returns an error.
* Site "10001" has both 1HR_AV and 24HR_AV readings, site "10002" is a sensor with reduced data.
"""

import datetime
from datetime import datetime as dt
import math
import random
from typing import Any
from zoneinfo import ZoneInfo

# Valid API keys mapped to their associated sites
API_KEY_SITES: dict[str, dict[str, Any]] = {
    "test-key-1": {
        "sites": ["10001", "10002", "10003"],
    },
    "test-key-2": {
        "sites": ["10001"],
    },
}

# Simulated EPA Victoria monitoring sites
SITES: dict[str, dict[str, Any]] = {
    "10001": {
        "siteID": "10001",
        "siteName": "Melbourne CBD",
        "siteType": "Standard",
        "geometry": {
            "coordinates": [-37.8136, 144.9631],
        },
        "siteHealthAdvices": [
            {
                "healthParameter": "PM2.5",
                "averageValue": 8.5,
                "healthAdvice": "Good",
                "healthAdviceColor": "#00FF00",
            }
        ],
    },
    "10002": {
        "siteID": "10002",
        "siteName": "Geelong South",
        "siteType": "Sensor",
        "geometry": {
            "coordinates": [-38.1499, 144.3617],
        },
        "siteHealthAdvices": [
            {
                "healthParameter": "PM2.5",
                "averageValue": 12.3,
                "healthAdvice": "Fair",
                "healthAdviceColor": "#FFFF00",
            }
        ],
    },
    "10003": {
        "siteID": "10003",
        "siteName": "Traralgon",
        "siteType": "Standard",
        "geometry": {
            "coordinates": [-38.1953, 146.5353],
        },
        "siteHealthAdvices": [
            {
                "healthParameter": "PM2.5",
                "averageValue": 5.2,
                "healthAdvice": "Good",
                "healthAdviceColor": "#00FF00",
            }
        ],
    },
    "10004": {
        "siteID": "10004",
        "siteName": "Viewbank Camera",
        "siteType": "Camera",
        "geometry": {
            "coordinates": [-37.7408, 145.0965],
        },
        "siteHealthAdvices": [{}],
    },
}

# PM2.5 diurnal pattern factors (index 0 = midnight, each step = 1 hour)
# Higher in morning rush (7-9) and evening (18-21), lower midday
_DIURNAL_FACTORS: list[float] = [
    0.6,
    0.5,
    0.4,
    0.4,
    0.4,
    0.5,
    0.7,
    1.0,  # 00:00 - 07:00
    1.2,
    1.1,
    0.9,
    0.7,
    0.6,
    0.5,
    0.5,
    0.6,  # 08:00 - 15:00
    0.7,
    0.9,
    1.1,
    1.3,
    1.2,
    1.0,
    0.8,
    0.7,  # 16:00 - 23:00
]

# Base PM2.5 concentrations per site (µg/m³)
_BASE_PM25: dict[str, float] = {
    "10001": 8.0,
    "10002": 12.0,
    "10003": 5.0,
    "10004": 0.0,
}


def _pm25_health_advice(pm25: float) -> str:
    """Return EPA Victoria health advice string for a PM2.5 value.

    Based on EPA Victoria AQI categories for PM2.5.
    """
    if pm25 <= 25.0:
        return "Good"
    if pm25 <= 50.0:
        return "Fair"
    if pm25 <= 100.0:
        return "Poor"
    if pm25 <= 300.0:
        return "Very poor"
    return "Extremely poor"


class SimulatedEPA:
    """Simulated EPA Victoria air quality data provider."""

    def __init__(self) -> None:
        """Initialise the simulator."""
        self._time_zone: ZoneInfo = ZoneInfo("Australia/Melbourne")
        self._seed: int = 42
        self._rng: random.Random = random.Random(self._seed)

    def set_time_zone(self, tz: ZoneInfo) -> None:
        """Set the time zone used for diurnal calculations."""
        self._time_zone = tz

    def _now_local(self) -> dt:
        """Return the current time in the configured time zone."""
        return dt.now(self._time_zone)

    def _generate_pm25(self, site_id: str, hour: int | None = None) -> float:
        """Generate a deterministic PM2.5 value for a site and hour.

        Uses the diurnal pattern with a small pseudo-random jitter.
        """
        if hour is None:
            hour = self._now_local().hour
        base = _BASE_PM25.get(site_id, 8.0)
        factor = _DIURNAL_FACTORS[hour % 24]
        # Add small deterministic jitter based on site_id hash and hour
        jitter = math.sin(hash(site_id) + hour) * 1.5
        return round(max(0.1, base * factor + jitter), 1)

    def _generate_pm25_24h(self, site_id: str) -> float:
        """Generate a 24-hour average PM2.5 for a site.

        Averages across all 24 hours of diurnal pattern.
        """
        values = [self._generate_pm25(site_id, h) for h in range(24)]
        return round(sum(values) / len(values), 1)

    def _make_reading(
        self,
        pm25: float,
        confidence: float = 0.95,
        total_sample: float = 12.0,
    ) -> dict[str, Any]:
        """Build a single reading dict matching EPA API structure."""
        until = (self._now_local() + datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        return {
            "averageValue": pm25,
            "healthAdvice": _pm25_health_advice(pm25),
            "until": until,
            "confidence": confidence,
            "totalSample": total_sample,
        }

    def _make_parameters(self, site_id: str) -> dict[str, Any]:
        """Build the full parameters response for a site."""
        pm25_1h = self._generate_pm25(site_id)
        pm25_24h = self._generate_pm25_24h(site_id)

        time_series: list[dict[str, Any]] = [
            {
                "timeSeriesName": "1HR_AV",
                "readings": [self._make_reading(pm25_1h)],
            },
            {
                "timeSeriesName": "24HR_AV",
                "readings": [self._make_reading(pm25_24h, confidence=0.98, total_sample=288.0)],
            },
        ]

        return {
            "parameters": [
                {
                    "timeSeriesReadings": time_series,
                }
            ],
        }

    # --- Public API methods matching EPA Victoria endpoints ---

    def get_sites_list(self) -> dict[str, Any]:
        """Return all sites (environmentalSegment=air).

        Corresponds to: GET /sites/?environmentalSegment=air
        """
        records = list(SITES.values())
        return {"records": records}

    def get_sites_by_location(self, lat: float, lon: float) -> dict[str, Any]:
        """Return sites nearest to given coordinates.

        Corresponds to: GET /sites/?environmentalSegment=air&location=[lat,lon]
        """

        # Sort sites by distance to requested coordinates (simple Euclidean for sim)
        def _dist(site: dict[str, Any]) -> float:
            coords = site["geometry"]["coordinates"]
            return math.sqrt((coords[0] - lat) ** 2 + (coords[1] - lon) ** 2)

        # Filter out cameras and sites without health parameters
        valid = [
            s
            for s in SITES.values()
            if s["siteType"] in ("Standard", "Sensor") and s.get("siteHealthAdvices", [{}])[0].get("healthParameter")
        ]
        sorted_sites = sorted(valid, key=_dist)
        return {"records": sorted_sites}

    def get_site_parameters(self, site_id: str) -> dict[str, Any] | None:
        """Return observation parameters for a specific site.

        Corresponds to: GET /sites/{siteID}/parameters
        """
        if site_id not in SITES:
            return None
        return self._make_parameters(site_id)

    def valid_api_keys(self) -> list[str]:
        """Return all valid API keys."""
        return list(API_KEY_SITES.keys())

    def validate_api_key(self, api_key: str) -> bool:
        """Check whether an API key is valid."""
        return api_key in API_KEY_SITES

    def site_exists(self, site_id: str) -> bool:
        """Check whether a site ID exists."""
        return site_id in SITES
