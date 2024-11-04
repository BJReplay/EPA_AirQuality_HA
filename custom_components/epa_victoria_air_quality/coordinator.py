"""The EPA Vic coordinator."""

# pylint: disable=C0301, C0302, C0304, C0321, E0401, R0902, R0914, W0105, W0613, W0702, W0706, W0719

from __future__ import annotations
from datetime import datetime as dt
from datetime import timedelta

from typing import Optional, Any, Dict

import logging
import traceback

import asyncio

from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.helpers.event import async_track_utc_time_change # type: ignore

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator # type: ignore

from .const import (
    DATE_FORMAT,
    DOMAIN,
    TIME_FORMAT,
)

from .epaapi import EPAApi

_LOGGER = logging.getLogger(__name__)

class EPAVicUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data."""

    def __init__(self, hass: HomeAssistant, epa: EPAApi, version: str):
        """Initialisation.

        Public variables at the top, protected variables (those prepended with _ after).

        Arguments:
            hass (HomeAssistant): The Home Assistant instance.
            epa (epaApi): The EPA API instance.
            version (str): The integration version from manifest.json.
        """
        self.epa = epa
        self.tasks = {}

        self._hass: HomeAssistant = hass
        self._version: str = version
        self._last_day: dt = None
        self._date_changed: bool = False
        self._data_updated: bool = False
        self._sunrise: dt = None
        self._sunset: dt = None
        self._sunrise_tomorrow: dt = None
        self._sunset_tomorrow: dt = None
        self._intervals: list[dt] = []
        self.interval_just_passed = None

        super().__init__(hass, _LOGGER, name=DOMAIN)

    async def _async_update_data(self):
        """Update data via library.

        Returns:
            list: Current air quality detail list.
        """
        return self.epa.get_data()

    async def setup(self) -> bool:
        """Set up time change tracking."""
        self._last_day = dt.now(self.epa.options.tz).day
        try:
            self.__auto_update_setup(init=True)
            await self.__check_quality_fetch()

            self.tasks['listeners'] = async_track_utc_time_change(self._hass, self.update_integration_listeners, minute=range(0, 60, 5), second=0)
            self.tasks['check_fetch'] = async_track_utc_time_change(self._hass, self.__check_quality_fetch, minute=range(0, 60, 5), second=0)
            for timer, _ in self.tasks.items():
                _LOGGER.debug("Started task %s", timer)
            return True
        except:
            _LOGGER.error("Exception in setup: %s", traceback.format_exc())
            return False

    async def update_integration_listeners(self, *args):
        """Get updated sensor values."""
        try:
            await self.async_update_listeners()
        except:
            _LOGGER.error("Exception in update_integration_listeners(): %s", traceback.format_exc())

    async def __check_quality_fetch(self, *args):
        """Check for an auto quality update event."""
        try:
            if len(self._intervals) > 0:
                _now = self.epa.get_real_now_utc().replace(microsecond=0)
                _from = _now.replace(minute=int(_now.minute/5)*5, second=0)
                if _from <= self._intervals[0] <= _from + timedelta(seconds=299):
                    update_in = (self._intervals[0] - _now).total_seconds()
                    if self.tasks.get('pending_update') is not None:
                        # An update is already tasked
                        _LOGGER.debug("Update already tasked and updating in %d seconds", update_in)
                        return
                    _LOGGER.debug("Air quality will update in %d seconds", update_in)
                    async def wait_for_fetch():
                        try:
                            await asyncio.sleep(update_in)
                            # Proceed with quality update if not cancelled
                            _LOGGER.info("Auto update: Fetching air quality")
                            self._intervals = self._intervals[1:]
                            await self.__quality_update()
                        except asyncio.CancelledError:
                            _LOGGER.info("Auto update: Cancelled next scheduled update")
                        finally:
                            if self.tasks.get('pending_update') is not None:
                                self.tasks.pop('pending_update')
                    self.tasks['pending_update'] = asyncio.create_task(wait_for_fetch())
        except:
            _LOGGER.error("Exception in __check_quality_fetch(): %s", traceback.format_exc())

    def __auto_update_setup(self, init: bool=False):
        """Daily set up of auto-updates."""
        try:
            self._sunrise = self.epa.get_day_start_utc()
            self._sunset = self._sunrise + timedelta(hours=24)
            self._sunrise_tomorrow = self._sunset
            self._sunset_tomorrow = self._sunrise_tomorrow + timedelta(hours=24)
            self.__calculate_quality_updates(init=init)
        except:
            _LOGGER.error("Exception in __auto_update_setup(): %s", traceback.format_exc())

    def __calculate_quality_updates(self, init: bool=False):
        """Calculate all automated quality update events for the day.

        This is an even spread between every half hour.
        """
        try:
            divisions = int(48)

            def get_intervals(sunrise: dt, sunset: dt, log=True):
                seconds = int((sunset - sunrise).total_seconds())
                interval = int(seconds / divisions)
                intervals = [(sunrise + timedelta(seconds=interval) * i) for i in range(0, divisions)]
                _now = self.epa.get_real_now_utc()
                for i in intervals:
                    if i < _now:
                        self.interval_just_passed = i
                    else:
                        break
                intervals = [i for i in intervals if i > _now]
                if len(intervals) < divisions:
                    _LOGGER.debug("Previous auto update was at: %s (if auto-update was enabled at the time)", self.interval_just_passed.astimezone(self.epa.options.tz).strftime(DATE_FORMAT))
                if log:
                    _LOGGER.debug("Auto update total seconds: %d, divisions: %d, interval: %d seconds", seconds, divisions, interval)
                    if init:
                        _LOGGER.debug("Auto update will update air quality %d times over 24 hours", divisions)
                return intervals

            def format_intervals(intervals):
                return [i.astimezone(self.epa.options.tz).strftime('%H:%M') if len(intervals) > 10 else i.astimezone(self.epa.options.tz).strftime('%H:%M:%S') for i in intervals]

            intervals_today = get_intervals(self._sunrise, self._sunset)
            intervals_tomorrow = get_intervals(self._sunrise_tomorrow, self._sunset_tomorrow, log=False)
            self._intervals = intervals_today + intervals_tomorrow

            if len(intervals_today) > 0:
                _LOGGER.info("Auto update: quality update%s for today at %s", 's' if len(intervals_today) > 1 else '', ', '.join(format_intervals(intervals_today)))
            if len(intervals_today) < divisions: # Only log tomorrow if part-way though today, or today has no more updates
                _LOGGER.info("Auto update: quality update%s for tomorrow at %s", 's' if len(intervals_tomorrow) > 1 else '', ', '.join(format_intervals(intervals_tomorrow)))
        except:
            _LOGGER.error("Exception in __calculate_quality_updates(): %s", traceback.format_exc())

    async def __quality_update(self, force: bool=False):
        """Get updated quality data."""

        if len(self._intervals) > 0:
            next_update = self._intervals[0].astimezone(self.epa.options.tz)
            next_update = next_update.strftime(TIME_FORMAT) if next_update.date() == dt.now().date() else next_update.strftime(DATE_FORMAT)
        else:
            next_update = None

        await self.epa.get_quality_update(do_past=False, force=force, next_update=next_update)
        self._data_updated = True
        await self.update_integration_listeners()
        self._data_updated = False

    async def service_event_update(self):
        """Get updated quality data when requested by a service call.        """
        self.tasks['quality_update'] = asyncio.create_task(self.__quality_update())

    def get_epa_sites(self) -> dict[str, Any]:
        """Return the active epa sites.

        Returns:
            dict[str, Any]: The presently known epa.com sites
        """
        return self.epa.sites

    def get_data(self) -> dict[str, Any]:
        """Return the data dictionary.

        Returns:
            list: Dampened forecast detail list of the sum of all site forecasts.
        """
        return self._data

    def get_last_updated(self) -> dt:
        """Return when the data was last updated.

        Returns:
            datetime: The last successful forecast fetch.
        """
        return self._data["last_updated"]

    def get_aqi_pm25(self) -> str:
        """Returns C

        Returns:
            str: Air Quality Description
        """

        return self._data["aqi_pm25"]

    def get_aqi_pm25_24h(self) -> str:
        """Returns the 24 Hour Air Quality based on PM2.5

        Returns:
            str: Air Quality Description
        """
        return self._data["aqi_pm25_24h"]

    def get_pm25(self) -> float:
        """Return the PM2.5 air quality in µg/m3

        Returns:
            float: The PM2.5 air quality in µg/m3
        """
        return self._data["pm25"]

    def get_pm25_24h(self) -> dt:
        """Return the 24 Hour PM2.5 air quality in µg/m3

        Returns:
            float: The PM2.5 air quality in µg/m3
        """
        return self._data["pm25_24h"]

    def get_data_updated(self) -> bool:
        """Returns True if data has been updated, which will trigger all sensor values to update.

        Returns:
            bool: Whether the quality data has been updated.
        """
        return self._data_updated

    def set_data_updated(self, updated: bool):
        """Set the state of the data updated flag.

        Arguments:
            updated (bool): The state to set the _data_updated quality updated flag to.
        """
        self._data_updated = updated

    def get_date_changed(self) -> bool:
        """Returns True if a roll-over to tomorrow has occurred, which will trigger all sensor values to update.

        Returns:
            bool: Whether a date roll-over has occurred.
        """
        return self._date_changed

    def get_sensor_value(self, key: str="") -> Optional[int | dt | float | str | bool]:
        """Return the value of a sensor."""
        match key:
            case "aqi_pm25":
                return self.get_aqi_pm25()
            case "aqi_pm25_24h":
                return self.get_aqi_pm25_24h()
            case "pm25":
                return self.get_pm25()
            case "pm25_24h":
                return self.get_pm25_24h()
            case "lastupdated":
                return self.get_last_updated()
            case _:
                return None

    def get_sensor_extra_attributes(self, key="") -> Optional[Dict[str, Any]]:
        """Return the attributes for a sensor."""
        match key:
            case _:
                return None