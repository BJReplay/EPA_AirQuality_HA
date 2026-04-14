#!/usr/bin/env python3
"""EPA Victoria Air Quality API simulator.

A WSGI-based (Flask) simulator for the EPA Victoria environment monitoring API.

Install:

* This script runs in a Home Assistant DevContainer.
* Script start: ``python3 wsgi_sim.py``, or make the file executable and run ``./wsgi_sim.py``

Getting started (quick):

1. Run: ``sudo python3 wsgi_sim.py --setup-hosts``   (adds /etc/hosts entry, needs sudo)
2. Run: ``python3 wsgi_sim.py``
3. The collector must use ``ssl=False`` on its aiohttp requests to accept the self-signed cert.
   Add to each ``session.get()`` call: ``response = await session.get(url, ssl=False)``
4. Configure the integration with API key ``test-key-1`` or ``test-key-2``.

Optional run arguments:

* --setup-hosts      Add /etc/hosts entry to redirect EPA API domain to localhost, then exit.
* --port PORT        Port to listen on (default: 443).
* --no-ssl           Run without SSL (HTTP only). Requires collector URL_BASE change to http://.
* --limit LIMIT      Set an API call limit per key (default: unlimited).
* --bomb429 w-x,y,z  Minute(s) of the hour to return 429 too busy, comma separated.
* --debug            Enable Flask debug mode.

Theory of operation:

* API keys ``test-key-1`` and ``test-key-2`` are valid. Any other key returns 403.
* ``test-key-1`` has access to sites 10001, 10002, 10003.
* ``test-key-2`` has access to site 10001 only.
* PM2.5 readings follow a deterministic diurnal pattern (higher morning/evening).
* The simulator serves the three endpoints used by the integration:
    - GET /environmentMonitoring/v1/sites/?environmentalSegment=air                         → list all sites
    - GET /environmentMonitoring/v1/sites/?environmentalSegment=air&location=[lat,lon]       → find nearest site
    - GET /environmentMonitoring/v1/sites/{siteID}/parameters                                → site observations
* Optional 429 responses are returned at specified bomb429 minutes of each hour.
* The time zone defaults to Australia/Melbourne but can be read from HA config.

Connecting the integration to the simulator:

* The integration's ``collector.py`` uses URL_BASE = ``https://gateway.api.epa.vic.gov.au/...``
* To redirect requests to the simulator:
  1. Add ``127.0.0.1 gateway.api.epa.vic.gov.au`` to ``/etc/hosts`` (use ``--setup-hosts``).
  2. The simulator listens on port 443 with a self-signed SSL certificate by default.
  3. The collector's ``aiohttp.ClientSession`` will reject the self-signed cert.
     Fix: add ``ssl=False`` to each ``session.get()`` call in ``collector.py``.

SSL certificate:

* A self-signed certificate is auto-generated on first run (cert.pem / key.pem).
* Delete *.pem files and restart to regenerate.
* With ``--no-ssl``, no certificate is needed (but collector must use ``http://`` URL_BASE).

Integration issues raised regarding the simulator will be closed without response.
Raise a pull request instead, suggesting a fix.
"""

import argparse
import datetime
from datetime import datetime as dt
import json
from logging.config import dictConfig
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from zoneinfo import ZoneInfo

from simulator.simulate import API_KEY_SITES, SimulatedEPA

simulate = SimulatedEPA()


def restart() -> None:
    """Restart the simulator process."""
    python = sys.executable
    os.execl(python, python, *sys.argv)
    sys.exit()


EPA_DOMAIN = "gateway.api.epa.vic.gov.au"
HOSTS_ENTRY = f"127.0.0.1 {EPA_DOMAIN}"

need_restart = False

try:
    from flask import Flask, jsonify, request
    from flask.json.provider import DefaultJSONProvider
except (ModuleNotFoundError, ImportError):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
    need_restart = True

if need_restart:
    restart()


def _ensure_ssl_cert() -> None:
    """Generate a self-signed certificate if not present."""
    if not (Path("cert.pem").exists() and Path("key.pem").exists()):
        subprocess.check_call(
            [
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:4096",
                "-nodes",
                "-out",
                "cert.pem",
                "-keyout",
                "key.pem",
                "-days",
                "3650",
                "-subj",
                f"/C=AU/ST=Victoria/L=Melbourne/O=EPA Victoria/OU=AirQuality/CN={EPA_DOMAIN}",
            ]
        )


def setup_hosts() -> None:
    """Add /etc/hosts entry to redirect the EPA API domain to localhost."""
    hosts_path = Path("/etc/hosts")
    hosts_content = hosts_path.read_text(encoding="utf-8")
    if EPA_DOMAIN in hosts_content:
        _LOGGER.info("/etc/hosts already contains an entry for %s", EPA_DOMAIN)
        return
    _LOGGER.info("Adding '%s' to /etc/hosts (requires sudo, may not work for your environment)", HOSTS_ENTRY)
    subprocess.check_call(["sudo", "sh", "-c", f"echo '{HOSTS_ENTRY}' >> /etc/hosts"])
    _LOGGER.info("Done. Verify with: cat /etc/hosts")
    _LOGGER.info("")
    _LOGGER.info("To remove later, edit /etc/hosts and delete the line:")
    _LOGGER.info("  %s", HOSTS_ENTRY)


# --- Configuration ---

API_LIMIT: int = 0  # 0 = unlimited
BOMB_429: list[int] = [0]
GENERATE_429: bool = True

ERROR_KEY_REQUIRED = "KeyRequired"
ERROR_INVALID_KEY = "InvalidKey"
ERROR_TOO_MANY_REQUESTS = "TooManyRequests"
ERROR_SITE_NOT_FOUND = "SiteNotFound"

ERROR_MESSAGE: dict[str, Any] = {
    ERROR_KEY_REQUIRED: {"message": "An API key must be specified.", "status": 400},
    ERROR_INVALID_KEY: {"message": "Invalid API key.", "status": 403},
    ERROR_TOO_MANY_REQUESTS: {"message": "You have exceeded your daily API limit.", "status": 429},
    ERROR_SITE_NOT_FOUND: {"message": "The specified site cannot be found.", "status": 404},
}

# --- Logging ---

dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            }
        },
        "root": {"level": "DEBUG", "handlers": ["wsgi"]},
    }
)


# --- Custom JSON serialiser ---


class DtJSONProvider(DefaultJSONProvider):
    """Custom JSON provider converting datetime to ISO format."""

    def default(self, o: Any) -> Any:
        """Convert datetime to ISO format."""
        if isinstance(o, dt):
            return o.isoformat()
        return super().default(o)


# --- Flask app ---

app = Flask(__name__)
app.json = DtJSONProvider(app)
_LOGGER = app.logger
counter_last_reset = dt.now(datetime.UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def validate_call(api_key: str | None, counter: bool = True) -> tuple[int, Any]:
    """Validate an API call and return (status_code, error_body_or_None).

    Returns:
        tuple: (200, None) on success, or (error_code, error_dict) on failure.
    """
    global counter_last_reset  # noqa: PLW0603

    # Reset counters at UTC midnight
    if counter_last_reset.day != dt.now(datetime.UTC).day:
        _LOGGER.info("Resetting API usage counters")
        for v in API_KEY_SITES.values():
            v["counter"] = 0
        counter_last_reset = dt.now(datetime.UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    def error(code: str) -> tuple[int, dict[str, Any]]:
        return (
            ERROR_MESSAGE[code]["status"],
            {"error_code": code, "message": ERROR_MESSAGE[code]["message"]},
        )

    if not api_key:
        return error(ERROR_KEY_REQUIRED)
    if api_key not in API_KEY_SITES:
        return error(ERROR_INVALID_KEY)
    if GENERATE_429 and dt.now(datetime.UTC).minute in BOMB_429:
        return 429, {"error_code": ERROR_TOO_MANY_REQUESTS, "message": "API too busy, try again later."}
    if counter and API_LIMIT > 0:
        current = API_KEY_SITES.get(api_key, {}).get("counter", 0)
        if current >= API_LIMIT:
            return error(ERROR_TOO_MANY_REQUESTS)
        API_KEY_SITES[api_key]["counter"] = current + 1
        _LOGGER.info("API key %s used %s times", api_key, API_KEY_SITES[api_key]["counter"])

    return 200, None


def _extract_api_key() -> str | None:
    """Extract the X-API-Key header from the request."""
    return request.headers.get("X-API-Key")


# --- Endpoints ---


@app.route("/environmentMonitoring/v1/sites/", methods=["GET"])
@app.route("/environmentMonitoring/v1/sites", methods=["GET"])
def get_sites() -> tuple[Any, int]:
    """Return site list or nearest site by location.

    Query parameters:
        environmentalSegment: must be "air"
        location: optional, format "[lat,lon]" — returns nearest site(s)
    """
    api_key = _extract_api_key()
    response_code, issue = validate_call(api_key, counter=False)
    if response_code != 200:
        return jsonify(issue) if issue else "", response_code

    location = request.args.get("location")
    if location:
        # Parse "[lat,lon]" format
        try:
            clean = location.strip("[]")
            parts = clean.split(",")
            lat = float(parts[0])
            lon = float(parts[1])
        except (ValueError, IndexError):
            return jsonify({"error": "Invalid location format. Use [lat,lon]"}), 400
        result = simulate.get_sites_by_location(lat, lon)
    else:
        result = simulate.get_sites_list()

    return jsonify(result), 200


@app.route("/environmentMonitoring/v1/sites/<site_id>/parameters", methods=["GET"])
def get_site_parameters(site_id: str) -> tuple[Any, int]:
    """Return observation parameters for a specific monitoring site.

    Path parameters:
        site_id: The EPA site identifier.
    """
    api_key = _extract_api_key()
    response_code, issue = validate_call(api_key)
    if response_code != 200:
        return jsonify(issue) if issue else "", response_code

    if not simulate.site_exists(site_id):
        return jsonify(ERROR_MESSAGE[ERROR_SITE_NOT_FOUND]), 404

    parameters = simulate.get_site_parameters(site_id)
    if parameters is None:
        return jsonify({"error": "No data available for site"}), 500

    return jsonify(parameters), 200


# --- Health / info endpoints ---


@app.route("/", methods=["GET"])
def index() -> tuple[Any, int]:
    """Return simulator status."""
    return jsonify(
        {
            "simulator": "EPA Victoria Air Quality API Simulator",
            "version": "1.0.0",
            "endpoints": [
                "GET /environmentMonitoring/v1/sites/?environmentalSegment=air",
                "GET /environmentMonitoring/v1/sites/?environmentalSegment=air&location=[lat,lon]",
                "GET /environmentMonitoring/v1/sites/{siteID}/parameters",
            ],
            "valid_api_keys": ["test-key-1", "test-key-2"],
        }
    ), 200


# --- Time zone reader ---


def get_time_zone() -> None:
    """Attempt to read time zone from Home Assistant config."""
    try:
        with Path.open(Path(Path.cwd(), "../../../.storage/core.config")) as f:
            config = json.loads(f.read())
            simulate.set_time_zone(ZoneInfo(config["data"]["time_zone"]))
            _LOGGER.info("Time zone: %s", config["data"]["time_zone"])
    except Exception:  # noqa: BLE001
        _LOGGER.info("Using default time zone: Australia/Melbourne")


# --- CLI entry point ---


def _parse_bomb_minutes(spec: str) -> list[int]:
    """Parse a comma-separated minute specification with optional ranges.

    Example: "0-5,15,30-35,45" → [0, 1, 2, 3, 4, 5, 15, 30, 31, 32, 33, 34, 35, 45]
    """
    minutes: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            start, end = part.split("-", 1)
            minutes.extend(range(int(start), int(end) + 1))
        else:
            minutes.append(int(part))
    return sorted(minutes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EPA Victoria Air Quality API Simulator")
    parser.add_argument(
        "--setup-hosts", help="Add /etc/hosts entry to redirect EPA API to localhost, then exit", action="store_true", required=False
    )
    parser.add_argument("--port", help="Port to listen on (default: 443)", type=int, required=False, default=443)
    parser.add_argument("--no-ssl", help="Run without SSL (HTTP only)", action="store_true", required=False)
    parser.add_argument("--limit", help="Set the API call limit per key (0 = unlimited)", type=int, required=False)
    parser.add_argument(
        "--bomb429",
        help="Minute(s) of the hour to return 429, comma separated with optional ranges (e.g. 0-5,15,30)",
        type=str,
        required=False,
    )
    parser.add_argument("--debug", help="Enable Flask debug mode", action="store_true", required=False, default=False)
    args = parser.parse_args()

    if args.setup_hosts:
        setup_hosts()
        sys.exit(0)

    _LOGGER.info("Starting EPA Victoria Air Quality API simulator")
    _LOGGER.info("Originally modelled after the Solcast Solar API simulator by @autoSteve")
    get_time_zone()

    if args.limit is not None:
        API_LIMIT = args.limit
        _LOGGER.info("API limit set to %s", API_LIMIT)
    if args.bomb429:
        GENERATE_429 = True
        BOMB_429 = _parse_bomb_minutes(args.bomb429)
        _LOGGER.info("429 responses will be returned at minute(s) %s", BOMB_429)
    else:
        GENERATE_429 = False

    if API_LIMIT == 0:
        _LOGGER.info("API limit is unlimited")

    use_ssl = not args.no_ssl
    port = args.port
    ssl_context = None

    if use_ssl:
        _ensure_ssl_cert()
        ssl_context = ("cert.pem", "key.pem")
        _LOGGER.info("Listening on https://127.0.0.1:%s (SSL)", port)
        _LOGGER.info("Reminder: collector.py must use ssl=False on session.get() calls")
    else:
        _LOGGER.info("Listening on http://127.0.0.1:%s (no SSL)", port)
        _LOGGER.info("Reminder: collector.py URL_BASE must use http:// instead of https://")

    # Check /etc/hosts
    try:
        if EPA_DOMAIN not in Path("/etc/hosts").read_text(encoding="utf-8"):
            _LOGGER.warning(
                "/etc/hosts does not redirect %s to localhost. Run with --setup-hosts using sudo first, or manually add: %s",
                EPA_DOMAIN,
                HOSTS_ENTRY,
            )
    except OSError:
        pass

    app.run(debug=args.debug, host="127.0.0.1", port=port, ssl_context=ssl_context)
