# HA EPA Air Quality Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![GitHub Release](https://img.shields.io/github/v/release/BJReplay/EPA_AirQuality_HA?style=for-the-badge)
[![hacs_downloads](https://img.shields.io/github/downloads/BJReplay/EPA_AirQuality_HA/latest/total?style=for-the-badge)](https://github.com/BJReplay/EPA_AirQuality_HA/releases/latest)
![GitHub License](https://img.shields.io/github/license/BJReplay/EPA_AirQuality_HA?style=for-the-badge)
![GitHub commit activity](https://img.shields.io/github/commit-activity/y/BJReplay/EPA_AirQuality_HA?style=for-the-badge)
![Maintenance](https://img.shields.io/maintenance/yes/2026?style=for-the-badge)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BJReplay&repository=EPA_AirQuality_HA&category=integration)

A Home Assistant custom component for reading air quality data from the EPA Victoria (Australia) Environment Monitoring API.

In order to use this integration, you will need to sign up to the [EPA Developer portal](https://portal.api.epa.vic.gov.au/).

Once you have signed up and have a log in, go to the [Environment Monitoring](https://portal.api.epa.vic.gov.au/product#product=environment-monitoring) page, select a name (such as home-assistant) for your new subscription, and hit `subscribe`.

This will create a new subscription, with a Primary and Secondary key.  You can use either API key, and you can return to your [profile page](https://portal.api.epa.vic.gov.au/profile) at any time to review the keys, so there is no need to record them in your password manager (provided, of course, that you have recorded your login to to the EPA Developer portal in your password manager).

Once you have subscribed, you can set up this integration.

First it will prompt you for your API Key:

[<img src="https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/API_Key.png">](https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/API_Key.png)

Then, after a few moments, while it is finding all EPA monitoring stations, and listing them with the closest stations to you listed first, it will prompt you to choose a station.  The closest station to you should be listed at the top of the list, but you may prefer to choose another station, especially if you know that is where the prevailing wind blows from.

[<img src="https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/Choose_Location.png">](https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/Choose_Location.png)

[<img src="https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/Location_List.png">](https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/Location_List.png)

Sometimes sensors go off line: example of Melbourne CBD Sensor when it goes offline - integration switches to 24 Hour sensor, and shows the Data source as 24HR_AV

[<img src="https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/1HR_AV_Unavailable.png">](https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/1HR_AV_Unavailable.png)

## Multiple locations

This integration supports multiple locations, so you can monitor more than one EPA station in Home Assistant.

Go to the integration at `Settings` | `Devices & services` and add another service. The new location instance will be set up with its own entities. During set up the API key will default to that of existing service(s), making this process straightforward.

> [!NOTE]
>
> If you're a user from pre-v0.4.6 then the entities from your first set up are not going to be named after the location they represent. To make these consistent with the new multi-location naming, remove that integration service and re-add it. This will change entity names, so dashboards and any automation will need updating to match.

## Location differences

There are (at time of writing) 19 "standard" locations providing accurate PM2.5 pollutant data, and in many cases even more data. There are also a lot more "sensor" locations, and these provide an indicative air particle content. These locations are differentiated by the label `(sensor/indicative)`, and provide a generally lower quality guidance.

The list of stations can be viewed at the [EPA Air and Water Quality](https://www.epa.vic.gov.au/check-air-and-water-quality?tab=list) site in list view.  The standard locations are listed at the top of the list, with the pollutants recorded by each station shown if you click on the Pollutants tab, and the sensor monitoring sites are listed at the bottom of the list.

## Changing API key

If the API key is regenerated in the EPA developer portal and not updated in the integration then a reconfiguration issue will be raised within fifteen minutes. This allows for entry of the new key.

You are also able to update to the new key immediately by using the reconfigure function. In `Settings` | `Devices & services` | `Integrations` | `EPA Victoria Air Quality` select a service menu (three dots) and choose `Reconfigure`. If there are more than one service using the same API key then the key will be changed for all services using the old key. This can be optionally overridden if desired, setting a new key for a single service only.

> [!NOTE]
>
> If you are using a different key for differing integration services then you are going to need to select the correct one! The currant API key in use is displayed when the reconfigure flow is opened, so noting the prior key and its replacement might be handy in this circumstance.

## Changing locations

Once an integration service has been set up it cannot be changed to a different location. This is because entity naming is distinct for each location.

To switch locations, set up a new service for the different location and then delete the old service. Update dashboards and other entity references to suit the new location.

## Entities Exposed By This Integration

The integration defines a broad entity set, but availability and default visibility depend on what the selected EPA site actually returns.

- Enabled by default: PM2.5 family, primary AQI (`Hourly AQI`, `Daily AQI`), and `Overall AQI`.
- Disabled-ish by default: PM10/NO2/O3/SO2/CO families.
- If EPA does not provide a pollutant for a location at that time, those entities stay unavailable.

The expression "disabled-ish" refers to integration behaviour that automatically enables entities when a value has been obtained for the location on either first configuration of that location, or at a later date should the capability be added to an EPA location. When a value can be obtained then both hourly and daily entities are enabled for that pollutant reading.

### AQI and AQI-derived entities

| Entity | Meaning |
| --- | --- |
| `Hourly AQI` | Primary hourly AQI shown by the integration. Source is configurable (`PM2.5` or `Overall`). |
| `Daily AQI` | Primary daily AQI shown by the integration. Source is configurable (`PM2.5` or `Overall`). |
| `Hourly Overall AQI` | Highest hourly AQI sub-index across available pollutants. |
| `Daily Overall AQI` | Highest daily AQI sub-index across available pollutants. |
| `Hourly PM2.5 AQI` / `Daily PM2.5 AQI` | PM2.5 AQI sub-index values. |
| `Hourly PM10 AQI` / `Daily PM10 AQI` | PM10 AQI sub-index values. |
| `Hourly NO2 AQI` | NO2 AQI sub-index (hourly only). |
| `Hourly O3 AQI` | O3 AQI sub-index (hourly only). |
| `Hourly SO2 AQI` | SO2 AQI sub-index (hourly only). |

CO AQI is not currently provided because the available EPA time series in this integration does not map to a CO AQI sub-index calculation.

### Pollutant concentration entities

| Entity family | Hourly | Daily | Unit |
| --- | --- | --- | --- |
| PM2.5 | Yes | Yes | ug/m3 |
| PM10 | Yes | Yes | ug/m3 |
| NO2 | Yes | Yes | ppb |
| O3 | Yes | Yes | ppb |
| SO2 | Yes | Yes | ppb |
| CO | Yes | Yes | ppm |

### Health advice entities

| Entity family | Hourly advice | Daily advice | Note |
| --- | --- | --- | --- |
| PM2.5 | Yes | Yes | |
| PM10 | Yes | Yes | |
| NO2 | Yes | Yes | |
| O3 | Yes | Yes | |
| SO2 | Yes | Yes | |
| CO | Yes | Yes | |
| Overall health advice | Yes | Yes | Based on PM2.5 or 'worst overall' |

## Sensor Attributes

Most sensors include:

- `confidence`: EPA confidence value for the reading.
- `total_samples`: Number of samples used in that average.
- `until`: Timestamp indicating validity/end of reading interval.
- `monitoring_site_type`: Whether the site is a 'standard' or 'sensor' location.
- `measurement_quality`: Either 'standard' for a standard location, or 'indicative' for a sensor location.

Hourly sensors also include:

- `data_source`: `1HR_AV` or `24HR_AV` (fallback when hourly data is unavailable or unreliable).

Primary AQI sensors (`Hourly AQI`, `Daily AQI`) include:

- `configured_source`: The strategy configured in options (`PM2.5` or `Overall`).
- `aqi_source`: Which sub-index actually produced the current AQI value.

## Examples

If you drop the images (`good-aqi.png`, `fair-aqi.png`, `poor-aqi.png`, `verypoor-aql.png`, and `extremelypoor-aqi.png`) into your `www` directory (or create it, if required), the `sample-card.yaml` will create the sample below.

Add the yaml to a dashboard: you can do this by adding a card to a dashboard, choosing `custom card`, and pasting in the all of contents of `sample-card.yaml` replacing the `type: ""` sample, and before you save the card, hit `Ctrl+F`, find `~location~`, and replace with the location of your sensor - e.g. `melbourne_cbd`.

[<img src="https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/sample_card.png">](https://github.com/BJReplay/EPA_AirQuality_HA/blob/main/.github/SCREENSHOTS/sample_card.png)

## Acknowledgements

Inspired by [@loryanstrant](https://github.com/loryanstrant) who published [this article](https://www.loryanstrant.com/2023/07/23/track-air-quality-with-home-assistant-and-epa-data/) that helped me track air quality in HA, and created the first repo for this project.

Thanks to @autoSteve who provided much of the python knowledge and assistance over at [HA Solcast PV Solar Forecast Integration](https://github.com/BJReplay/ha-solcast-solar) and to @bremor and @Makin-Things who provided inspiration (and a model to steal for a cloud polling integration) with their fantastic [BoM integration](https://github.com/bremor/bureau_of_meteorology).
