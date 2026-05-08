# HA EPA Air Quality Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![GitHub Release](https://img.shields.io/github/v/release/BJReplay/EPA_AirQuality_HA?style=for-the-badge)
[![hacs_downloads](https://img.shields.io/github/downloads/BJReplay/EPA_AirQuality_HA/latest/total?style=for-the-badge)](https://github.com/BJReplay/EPA_AirQuality_HA/releases/latest)
![GitHub License](https://img.shields.io/github/license/BJReplay/EPA_AirQuality_HA?style=for-the-badge)
![GitHub commit activity](https://img.shields.io/github/commit-activity/y/BJReplay/EPA_AirQuality_HA?style=for-the-badge)
![Maintenance](https://img.shields.io/maintenance/yes/2026?style=for-the-badge)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BJReplay&repository=EPA_AirQuality_HA&category=integration)

A Home Assistant custom component for reading air quality data from the EPA Victoria (Australia) Environment Monitoring API

In order to use this integration, you will need to sign up to the [EPA Developer portal](https://portal.api.epa.vic.gov.au/).

Once you have signed up and have a log in, go to the [Environment Monitoring](https://portal.api.epa.vic.gov.au/product#product=environment-monitoring) page, select a name (such as home-assistant) for your new subscription, and hit `subscribe`.

This will create a new subscription, with a Primary and Secondary key.  You only need one key for the API, and you can return to your [profile page](https://portal.api.epa.vic.gov.au/profile) at any time to review the keys, so there is no need to record them in your password manager (provided, of course, that you have recorded your login to to the EPA Developer portal in your password manager).

Once you have subscribed, you can set up this integration.

First it will prompt you for your API Key:

[<img src="https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/API_Key.png">](https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/API_Key.png)

Then, after a few moments, while it is finding all EPA monitoring stations, and listing them with the closest stations to you listed first, it will prompt you to choose a station.  The closest station to you should be listed at the top of the list, but you may prefer to choose another station, especially if you know that is where the prevailing wind blows from.

[<img src="https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/Choose_Location.png">](https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/Choose_Location.png)

[<img src="https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/Location_List.png">](https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/Location_List.png)

If you drop the images (`good-aqi.png`, `fair-aqi.png`, `poor-aqi.png`, `verypoor-aql.png`, and `extremelypoor-aqi.png`) into your `www` directory (or create it, if required), the `sample-card.yaml` will create the sample below.

[<img src="https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/sample_card.png">](https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/sample_card.png)

Sometimes sensors go off line: example of Melbourne CBD Sensor when it goes offline - integration switches to 24 Hour sensor, and shows the Data source as 24HR_AV

[<img src="https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/1HR_AV_Unavailable.png">](https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/1HR_AV_Unavailable.png)

Inspired by [@loryanstrant](https://github.com/loryanstrant) who published [this article](https://www.loryanstrant.com/2023/07/23/track-air-quality-with-home-assistant-and-epa-data/) that helped me track air quality in HA, and created the first repo for this project.

Thanks to @autoSteve who provided much of the python knowledge and assistance over at [HA Solcast PV Solar Forecast Integration](https://github.com/BJReplay/ha-solcast-solar) and to @bremor and @Makin-Things who provided inspiration (and a model to steal for a cloud polling integration) with their fantastic [BoM integration](https://github.com/bremor/bureau_of_meteorology).

@autoSteve has just dropped a major release that now supports multiple locations, so you can monitor more than one location.  It currently prompts for the API key for each location (but you can easily copy and paste from your first location by clicking on the configure gear for your already configured location, copying the API key, and using it to configure subsequent locations).

This allows for templates such as the following simple example that uses the base (first sensor defined) and casts it to a float with a default value of the Brighton sensor - which, if it doesn't have a value, uses the Spotswood sensor

``` yaml
  states('sensor.epa_air_quality_hourly_aqi') 
         | float ( states('sensor.epa_air_quality_brighton_epa_air_quality_hourly_aqi') 
                 | float ( states('sensor.epa_air_quality_spotswood_epa_air_quality_hourly_aqi') 
                 )
            )
```

Another example is shown in discussion https://github.com/BJReplay/EPA_AirQuality_HA/discussions/15
