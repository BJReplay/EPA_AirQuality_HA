"""EPA API."""

# pylint: disable=C0103, C0301, C0302, C0304, C0321, E0401, R0902, R0914, W0105, W0702, W0706, W0718, W0719

from __future__ import annotations

import asyncio
import copy
import json
import logging
import sys
import time
import traceback
import random
import re
from dataclasses import dataclass
from datetime import datetime as dt
from datetime import timedelta, timezone
from operator import itemgetter
from os.path import exists as file_exists
from os.path import dirname
from typing import Optional, Any, cast

import async_timeout # type: ignore
import aiofiles # type: ignore
from aiohttp import ClientConnectionError, ClientSession # type: ignore
from aiohttp.client_reqrep import ClientResponse # type: ignore
from isodate import parse_datetime # type: ignore


from .const import (
    CONF_SITE_ID,
)

"""Return the function name at a specified caller depth.

* For current function name, specify 0 or no argument
* For name of caller of current function, specify 1
* For name of caller of caller of current function, specify 2, etc.
"""
currentFuncName = lambda n=0: sys._getframe(n + 1).f_code.co_name # pylint: disable=C3001, W0212

JSON_VERSION = 1

# HTTP status code translation.
# A 418 error is included here for fun. This was introduced in RFC2324#section-2.3.2 as an April Fools joke in 1998.
STATUS_TRANSLATE = {
    200: 'Success',
    401: 'Unauthorized',
    403: 'Forbidden',
    404: 'Not found',
    418: 'I\'m a teapot',
    429: 'Try again later',
    500: 'Internal web server error',
    501: 'Not implemented',
    502: 'Bad gateway',
    503: 'Service unavailable',
    504: 'Gateway timeout',
}

_LOGGER = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    """Helper to convert datetime dict values to ISO format."""
    def default(self, o) -> Optional[str]:
        if isinstance(o, dt):
            return o.isoformat()
        else:
            return None

class DateKeyEncoder(json.JSONEncoder):
    """Helper to convert datetime dict keys and values to ISO format."""
    def _preprocess_date(self, o):
        if isinstance(o, dt):
            return str(o)
        elif isinstance(o, dict):
            return {self._preprocess_date(k): self._preprocess_date(v) for k,v in o.items()}
        elif isinstance(o, list):
            return [self._preprocess_date(i) for i in o]
        return o

    def default(self, o):
        if isinstance(o, dt):
            return str(o)
        return super().default(o)

    def iterencode(self, o, _one_shot=False):
        return super().iterencode(self._preprocess_date(o))

class NoIndentEncoder(json.JSONEncoder):
    """Helper to output semi-indented json."""
    def iterencode(self, o, _one_shot=False):
        list_lvl = 0
        for s in super(NoIndentEncoder, self).iterencode(o, _one_shot=_one_shot):
            if s.startswith('['):
                list_lvl += 1
                s = s.replace(' ','').replace('\n', '').rstrip()
            elif list_lvl > 0:
                s = s.replace(' ','').replace('\n', '').rstrip()
                if s and s[-1] == ',':
                    s = s[:-1] + self.item_separator
                elif s and s[-1] == ':':
                    s = s[:-1] + self.key_separator
            if s.endswith(']'):
                list_lvl -= 1
            yield s

class JSONDecoder(json.JSONDecoder):
    """Helper to convert ISO format dict values to datetime."""
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(
            self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, obj) -> dict: # pylint: disable=E0202
        """Required hook."""
        ret = {}
        for key, value in obj.items():
            try:
                if re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value):
                    ret[key] = dt.fromisoformat(value)
                else:
                    ret[key] = value
            except:
                ret[key] = value
        return ret

@dataclass
class ConnectionOptions:
    """EPA options for the integration."""

    api_key: str
    site_id: str
    host: str
    file_path: str
    tz: timezone

class EPAApi: # pylint: disable=R0904
    """The EPA API.

    Public functions:
        get_air_quality_update: Request air quality data for the sites.
        get_site_list: Return the list of sites.

        get_real_now_utc: Get the complete time now, including seconds and microseconds

        get_last_updated: Return when the data was last updated.
        is_stale_data: Return whether the air quality was last updated some time ago (i.e. is stale).
        get_api_limit: Return API polling limit for this UTC 24hr period (minimum of all API keys).
        get_api_used_count: Return API polling count for this UTC 24hr period (minimum of all API keys).

        get_site_extra_data: Return information about a site.
    """

    def __init__(
        self,
        aiohttp_session: ClientSession,
        options: ConnectionOptions,
        api_cache_enabled: bool=False
    ):
        """Initialisation.

        Public variables at the top, protected variables following.

        Arguments:
            aiohttp_session (ClientSession): The aiohttp client session provided by Home Assistant
            options (ConnectionOptions): The integration stored configuration options.
            api_cache_enabled (bool): Utilise cached data instead of getting updates from EPA (default: {False}).
        """

        self.entry = None
        self.entry_options = {}
        self.hass = None
        self.headers = {}
        self.options = options
        self.previously_loaded = False
        self.tasks = {}

        self._aiohttp_session = aiohttp_session
        self._api_cache_enabled = api_cache_enabled # For offline development.
        self._data = {
            'site': {},
            'last_updated': dt.fromtimestamp(0, timezone.utc),
            'last_attempt': dt.fromtimestamp(0, timezone.utc),
            'auto_updated': False,
            'version': JSON_VERSION
        }
        self._filename = options.file_path
        self._loaded_data = False
        self._serialise_lock = asyncio.Lock()
        self._tally = {}
        self._tz = options.tz
        self._data_quality = []

        self._config_dir = dirname(self._filename)
        _LOGGER.debug("Configuration directory is %s", self._config_dir)

    def get_real_now_utc(self) -> dt:
        """Datetime helper.

        Returns:
            datetime: The UTC date and time representing now including seconds/microseconds.
        """
        return dt.now(self._tz).astimezone(timezone.utc)

    def get_day_start_utc(self, future: int=0) -> dt:
        """Datetime helper.

        Returns:
            datetime: The UTC date and time representing midnight local time.

        Arguments:
            future(int): An optional number of days into the future
        """
        for_when = (dt.now(self._tz) + timedelta(days=future)).astimezone(self._tz)
        return for_when.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    def __translate(self, status) -> str | Any:
        """Translate HTTP status code to a human-readable translation.

        Arguments:
            status (int): A HTTP status code.

        Returns:
            str: Human readable HTTP status.
        """
        return (f"{str(status)}/{STATUS_TRANSLATE[status]}") if STATUS_TRANSLATE.get(status) else status

    async def __serialise_data(self, data, filename) -> bool:
        """Serialize data to file.

        Arguments:
            data (dict): The data to serialise.
            filename (str): The name of the file

        Returns:
            bool: Success or failure.
        """
        serialise = True
        # The twin try/except blocks here are significant. If the two were combined with
        # `await f.write(json.dumps(self._data, ensure_ascii=False, cls=DateTimeEncoder))`
        # then should an exception occur during conversion from dict to JSON string it
        # would result in an empty file.
        try:
            if not self._loaded_data:
                _LOGGER.debug("Not saving air quality cache in __serialise_data() as no data has been loaded yet")
                return False
            """
            If the _loaded_data flag is True, yet last_updated is 1/1/1970 then data has not been loaded
            properly for some reason, or no air quality has been received since startup so abort the save.
            """
            if data['last_updated'] == dt.fromtimestamp(0, timezone.utc):
                _LOGGER.error("Internal error: air quality cache %s last updated date has not been set, not saving data", filename)
                return False
            payload = json.dumps(data, ensure_ascii=False, cls=DateTimeEncoder)
        except Exception as e:
            _LOGGER.error("Exception in __serialise_data(): %s: %s", e, traceback.format_exc())
            serialise = False
        if serialise:
            try:
                async with self._serialise_lock:
                    async with aiofiles.open(filename, 'w') as f:
                        await f.write(payload)
                _LOGGER.debug("Saved %s air quality cache", "dampened" if filename == self._filename else "undampened")
                return True
            except Exception as e:
                _LOGGER.error("Exception writing air quality data: %s", e)
        return False

    async def set_options(self):
        """Set the class option variables (used by __init__ to avoid an integration reload).

        Arguments:
            options (dict): The data field to use for sensor values
        """
        self.options = ConnectionOptions(
            # All these options require a reload, and can not be dynamically set, hence retrieval from self.options...
            self.options.api_key,
            self.options.site_id,
            self.options.host,
            self.options.file_path,
            self.options.tz,
        )

    async def get_quality_update(self) -> str:
        """Request air quality data.

        Returns:
            str: An error message, or an empty string for no error.
        """
        try:
            last_attempt = dt.now(timezone.utc).isoformat()
            status = ''

            failure = False
            _LOGGER.info("Getting air quality update for site %s", CONF_SITE_ID)
            result = await self.__http_data_call(CONF_SITE_ID)
            if not result:
                failure = True

            if not failure:
                self._data["last_updated"] = dt.now(timezone.utc).replace(microsecond=0)
                self._data["last_attempt"] = last_attempt
                self._data["auto_updated"] = self.options.auto_update > 0

                self._data["version"] = JSON_VERSION
                self._loaded_data = True

                s_status = await self.__serialise_data(self._data, self._filename)
                if s_status:
                    _LOGGER.info("Air Quality update completed successfully")
            else:
                _LOGGER.error("Air Quality failed to fetch")
                status = 'Air Quality failed to fetch'
        except Exception as e:
            status = f"Exception in get_quality_update(): {e} - Air Quality failed to fetch"
            _LOGGER.error(status)
            _LOGGER.error(traceback.format_exc())
        return status

    async def __http_data_call(self, site: str=None) -> bool:
        """Request EPA Air Quality data via the EPA API.

        Arguments:
            site (str): A EPA site ID

        Returns:
            bool: A flag indicating success or failure
        """
        try:
            _LOGGER.debug("Polling API for site %s", site)

            new_data = []


            """
            Fetch latest data.
            """
            self.tasks['fetch'] = asyncio.create_task(self.__fetch_data(site))
            await self.tasks['fetch']
            resp_dict = self.tasks['fetch'].result()
            if self.tasks.get('fetch') is not None:
                self.tasks.pop('fetch')
            if resp_dict is None:
                return False

            if not isinstance(resp_dict, dict):
                raise TypeError(f"API did not return a json object. Returned {resp_dict}")

            aqi_results = resp_dict.get("parameters", None)
            if not isinstance(aqi_results, list):
                raise TypeError(f"parameters must be a list, not {type(aqi_results)}")

            _LOGGER.debug("%d records returned", len(aqi_results))

            st_time = time.time()
            for timeSeriesReadings in aqi_results:
                z1Hr = ""
                healthAdvice1Hr = ""
                averageValue1Hr = float(0)
                healthAdvice24Hr = ""
                averageValue24Hr = float(0)
                if timeSeriesReadings["timeSeriesName"] == "1HR_AV":
                    z1Hr = parse_datetime(timeSeriesReadings["readings"]["until"]).astimezone(timezone.utc)
                    healthAdvice1Hr = timeSeriesReadings["readings"]["healthAdvice"]
                    averageValue1Hr  = float(timeSeriesReadings["readings"]["averageValue"])
                elif timeSeriesReadings["timeSeriesName"] == "24HR_AV":
                    healthAdvice24Hr = timeSeriesReadings["readings"]["healthAdvice"]
                    averageValue24Hr  = float(timeSeriesReadings["readings"]["averageValue"])

            new_data.append(
                {
                    "until": z1Hr,
                    "healthAdvice1Hr": healthAdvice1Hr,
                    "averageValue1Hr": averageValue1Hr,
                    "healthAdvice24Hr": healthAdvice24Hr,
                    "averageValue24Hr": averageValue24Hr,
                    "updated": st_time,
                }
            )

            """
            Add or update AQI History with the latest data.
            """
            # Load the AQI History history.
            try:
                AQIs = {aqi["until"]: aqi for aqi in self._data['site'][site]['aqi']}
            except:
                AQIs = {}


            # Air Quality contains up to 730 days of period history data for each site. Convert dictionary to list, retain the past two years, sort by period start.
            pastdays = self.get_day_start_utc(future=-730)
            AQIs = sorted(list(filter(lambda aqi: aqi["until"] >= pastdays, AQIs.values())), key=itemgetter("until"))
            self._data['site'].update({site:{'aqi': copy.deepcopy(AQIs)}})

            _LOGGER.debug("AQI dictionary length %s", len(AQIs))
            _LOGGER.debug("HTTP data call processing took %.3f seconds", round(time.time() - st_time, 4))
            return True
        except Exception as e:
            _LOGGER.error("Exception in __http_data_call(): %s: %s", e, traceback.format_exc())
        return False

    async def __fetch_data(self, site_id: str="") -> Optional[dict[str, Any]]:
        """Fetch Air Quality data.

        Arguments:
            site_id (str): The EPA Site ID

        Returns:
            dict: Raw Air Quality data points, or None if unsuccessful.
        """

        try:
            """
            One site is fetched, and retries ensure that the site is actually fetched.
            Occasionally the EPA API is busy, and returns a 429 status, which is a
            request to try again later. (It could also indicate that the API limit for
            the day has been exceeded, and this is catered for by examining additional
            status.)

            The retry mechanism is a "back-off", where the interval between attempted
            fetches is increased each time. All attempts possible span a maximum of
            fifteen minutes, and this is also the timeout limit set for the entire
            async operation.
            """
            async with async_timeout.timeout(900):
                if self._api_cache_enabled:
                    api_cache_filename = self._config_dir + '/' + site_id + ".json"
                    if file_exists(api_cache_filename):
                        status = 404
                        async with aiofiles.open(api_cache_filename) as f:
                            resp_json = json.loads(await f.read())
                            status = 200
                            _LOGGER.debug("Offline cached mode enabled, loaded data for site %s", site_id)
                else:               
                    url = f"{self.options.host}/{site_id}/parameters"
                    _LOGGER.debug("Fetch data url: %s", url)
                    tries = 10
                    counter = 0
                    backoff = 15 # On every retry the back-off increases by (at least) fifteen seconds more than the previous back-off.
                    while True:
                        _LOGGER.debug("Fetching Air Quality")
                        counter += 1
                        resp: ClientResponse = await self._aiohttp_session.get(url=url, headers=self.headers, ssl=False)
                        status = resp.status
                        if status == 200:
                            break
                        if status == 429:
                            if counter >= tries:
                                status = 999 # All retries have been exhausted.
                                break
                            # EPA is busy, so delay (15 seconds * counter), plus a random number of seconds between zero and 15.
                            delay = (counter * backoff) + random.randrange(0,15)
                            _LOGGER.warning("API returned 'try later' (status 429), pausing %d seconds before retry", delay)
                            await asyncio.sleep(delay)
                        else:
                            break

                    if status == 200:
                        _LOGGER.debug("Fetch successful")
                        resp_json = await resp.json(content_type=None)
                        if self._api_cache_enabled:
                            async with self._serialise_lock:
                                async with aiofiles.open(api_cache_filename, 'w') as f:
                                    await f.write(json.dumps(resp_json, ensure_ascii=False))
                    else:
                        _LOGGER.error("API returned status %s", self.__translate(status))
                        return None

                _LOGGER.debug("HTTP session returned data type %s", type(resp_json))
                _LOGGER.debug("HTTP session status %s", self.__translate(status))

            if status == 429:
                _LOGGER.warning("API is too busy, try again later")
            elif status == 404:
                _LOGGER.error("The site cannot be found, status %s returned", self.__translate(status))
            elif status == 200:
                d = cast(dict, resp_json)
                return d
        except asyncio.exceptions.CancelledError:
            _LOGGER.debug('Fetch cancelled')
        except ConnectionRefusedError as e:
            _LOGGER.error("Connection error in __fetch_data(), connection refused: %s", e)
        except ClientConnectionError as e:
            _LOGGER.error("Connection error in __fetch_data(): %s", e)
        except asyncio.TimeoutError:
            _LOGGER.error("Connection error in __fetch_data(): Timed out connecting to server")
        except:
            _LOGGER.error("Exception in __fetch_data(): %s", traceback.format_exc())

        return None