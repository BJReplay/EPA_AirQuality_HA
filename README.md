# EPA_AirQuality_HA

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BJReplay&repository=EPA_AirQuality_HA&category=integration)

A Home Assistant custom component for reading air quality data from the EPA Victoria (Australia) Environment Monitoring API

Example of Melbourne CBD Sensor when it goes offline - integration switches to 24 Hour sensor, and shows the Data source as 24HR_AV

[<img src="https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/1HR_AV_Unavailable.png">](https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/1HR_AV_Unavailable.png)

Inspired by [@loryanstrant](https://github.com/loryanstrant) who published [this article](https://www.loryanstrant.com/2023/07/23/track-air-quality-with-home-assistant-and-epa-data/) that helped me track air quality in HA, and created the first repo for this project.

Future releases will support multiple installs so you can monitor multiple locations: currently the integration doesn't prevent multiple installs, but errors out on second and subsequent installs.

Current release v0.4.0 allows selecting Air Quality monitoring station from a list sorted by distance from your Home Assistant location.

If you change the location, subsequent list updates might be sorted based on distance from the currently selected location 🤣
