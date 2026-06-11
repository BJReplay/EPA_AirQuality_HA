"""Constants for the EPA Air Quality integration."""

from datetime import timedelta
from typing import Final

# Integration constants
ATTR_ENTRY_TYPE: Final = "entry_type"
ATTRIBUTION: Final = "Data retrieved from EPA (Victoria)"
COLLECTOR: Final = "collector"
CONF_LEGACY_UNIQUE_IDS: Final = "legacy_unique_ids"
CONF_AQI_SOURCE: Final = "aqi_source"
CONF_SITE_ID: Final = "site_id"
CONF_SITE_NAME: Final = "site_name"
DOMAIN: Final = "epa_victoria_air_quality"
ENTRY_TYPE_SERVICE: Final = "service"
COORDINATOR: Final = "coordinator"
UPDATE_LISTENER: Final = "update_listener"
AQI_SOURCE_OVERALL: Final = "overall"
AQI_SOURCE_PM25: Final = "pm25"
DEFAULT_AQI_SOURCE: Final = AQI_SOURCE_PM25
TIME_FORMAT: Final = "%H:%M:%S"
DATE_FORMAT: Final = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT_UTC: Final = "%Y-%m-%d %H:%M:%S UTC"
INIT_MSG: Final = """This is a custom integration. When troubleshooting a problem, after
reviewing open and closed issues, and the discussions.

Beta versions may also have addressed issues so look at those.

If all else fails, then open an issue and our community will try to
help: https://github.com/BJReplay/EPA_AirQuality_HA/issues"""
MANUFACTURER: Final = "BJReplay"
TITLE: Final = "EPA Air Quality"
ATTR_CONFIDENCE: Final = "confidence"
ATTR_CONFIDENCE_24H: Final = "confidence_24h"
ATTR_DATA_SOURCE: Final = "data_source"
ATTR_TOTAL_SAMPLE: Final = "total_samples"
ATTR_TOTAL_SAMPLE_24H: Final = "total_samples_24h"
NAME_API: Final = "API"
NAME_AQI: Final = "AQI"
NAME_CO: Final = "CO"
NAME_NO2: Final = "NO2"
NAME_O3: Final = "O3"
NAME_PM10: Final = "PM10"
NAME_PM25: Final = "PM2.5"
NAME_SO2: Final = "SO2"
NAME_VISIBILITY: Final = "Visibility"
PARAM_NAME: Final = "name"
TYPE_AQI: Final = "aqi"
TYPE_AQI_24H: Final = "aqi_24h"
TYPE_AQI_OVERALL: Final = "aqi_overall"
TYPE_AQI_OVERALL_24H: Final = "aqi_overall_24h"
TYPE_AQI_PM25: Final = "aqi_pm25"
TYPE_AQI_PM25_24H: Final = "aqi_pm25_24h"
TYPE_PM25_AQI_VALUE: Final = "pm25_aqi_value"
TYPE_PM25_AQI_VALUE_24H: Final = "pm25_aqi_value_24h"
TYPE_PM25: Final = "pm25"
TYPE_PM25_24H: Final = "pm25_24h"
TYPE_PM10: Final = "pm10"
TYPE_PM10_24H: Final = "pm10_24h"
TYPE_PM10_AQI_VALUE: Final = "pm10_aqi_value"
TYPE_PM10_AQI_VALUE_24H: Final = "pm10_aqi_value_24h"
TYPE_PM10_ADVICE: Final = "pm10_advice"
TYPE_PM10_ADVICE_24H: Final = "pm10_advice_24h"
TYPE_NO2: Final = "no2"
TYPE_NO2_24H: Final = "no2_24h"
TYPE_NO2_AQI_VALUE: Final = "no2_aqi_value"
TYPE_NO2_ADVICE: Final = "no2_advice"
TYPE_NO2_ADVICE_24H: Final = "no2_advice_24h"
TYPE_O3: Final = "o3"
TYPE_O3_24H: Final = "o3_24h"
TYPE_O3_AQI_VALUE: Final = "o3_aqi_value"
TYPE_O3_ADVICE: Final = "o3_advice"
TYPE_O3_ADVICE_24H: Final = "o3_advice_24h"
TYPE_SO2: Final = "so2"
TYPE_SO2_24H: Final = "so2_24h"
TYPE_SO2_AQI_VALUE: Final = "so2_aqi_value"
TYPE_SO2_ADVICE: Final = "so2_advice"
TYPE_SO2_ADVICE_24H: Final = "so2_advice_24h"
TYPE_CO: Final = "co"
TYPE_CO_24H: Final = "co_24h"
TYPE_CO_ADVICE: Final = "co_advice"
TYPE_CO_ADVICE_24H: Final = "co_advice_24h"
URL_BASE: Final = "https://gateway.api.epa.vic.gov.au/environmentMonitoring/v1/sites/"
URL_PARAMETERS: Final = "/parameters"
URL_FIND_SITE: Final = "?environmentalSegment=air&location="
URL_LIST_SITE: Final = "?environmentalSegment=air"
GEOMETRY: Final = "geometry"
COORDINATES: Final = "coordinates"
PARAMETERS: Final = "parameters"
DISTANCE: Final = "distance"
HEALTH_PARAMETER: Final = "healthParameter"
TIME_SERIES_NAME: Final = "timeSeriesName"
TIME_SERIES_READINGS: Final = "timeSeriesReadings"
HOURLY: Final = "1HR_AV"
DAILY: Final = "24HR_AV"
READINGS: Final = "readings"
AVERAGE_VALUE: Final = "averageValue"
HEALTH_ADVICE: Final = "healthAdvice"
UNTIL: Final = "until"
CONFIDENCE: Final = "confidence"
TOTAL_SAMPLE: Final = "totalSample"
RECORDS: Final = "records"
SITE_ID: Final = "siteID"
SITE_NAME: Final = "siteName"
SITE_TYPE: Final = "siteType"
SITE_TYPE_SENSOR: Final = "Sensor"
SITE_TYPE_STANDARD: Final = "Standard"
SITE_TYPE_CAMERA: Final = "Camera"
SITE_TYPE_SENSOR_LABEL_SUFFIX: Final = " (sensor/indicative)"
SITE_HEALTH_ADVICES: Final = "siteHealthAdvices"
SCAN_INTERVAL: Final = timedelta(minutes=15)

KNOWN_SITES: Final = {
    "c69ed768-34d2-4d72-86f3-088c250758a8": "Alphington",
    "4c4e8933-a66b-4e76-b2c2-ad9bb56d8809": "Altona North",
    "39ae637d-9102-49f0-b741-6b280055b033": "Ararat (sensor/indicative)",
    "1619e162-e4a5-4f96-b6a4-540ecd1a471c": "Bacchus Marsh (sensor/indicative)",
    "b860d407-5227-4b15-a0d9-eb5773b9d083": "Bairnsdale (sensor/indicative)",
    "e47fa291-45de-4b06-b6ac-6bb8bf6421f8": "Ballarat (sensor/indicative)",
    "0ad5e111-20d2-44d8-ad03-efa0736f65fc": "Beechworth (sensor/indicative)",
    "ab1a6394-e44b-4ff1-a1c0-cb8a4b48408e": "Benalla (sensor/indicative)",
    "82e215ca-e0e5-4a00-9357-98d53b04311b": "Bendigo",
    "1adaf80a-f20f-4fd3-8fa1-60d87acfce61": "Boolarra (sensor/indicative)",
    "dd8279c0-018d-469b-92c7-49eeeecd27de": "Boolarra South (sensor/indicative)",
    "77062cb7-3e3b-4984-b6d0-03dda76177f2": "Box Hill",
    "ed97e7b3-1ce6-4c6c-bb45-7f42ef305620": "Bright",
    "d56ede8c-637a-41e9-a055-f53198e9456a": "Brighton",
    "a50f4750-b17a-47cd-954b-dc694bd441c2": "Broadford (sensor/indicative)",
    "78dbc892-d9e9-490b-94a6-baf1ca72c36c": "Brooklyn",
    "b17f9b91-fdcf-43e6-9837-0ae6a775711d": "Camperdown (sensor/indicative)",
    "cda783ad-39fb-4ace-a8cd-15324fdb6147": "Castlemaine (sensor/indicative)",
    "ee780b50-0240-4c7e-99f8-0df759caf3a3": "Churchill",
    "883b5df6-8125-4e63-a2b6-1200faac4324": "Cobden (sensor/indicative)",
    "36a0e96c-7527-4a78-811c-230205a1640e": "Colac (sensor/indicative)",
    "69088979-01eb-4b48-9535-22b6d69421ec": "Dandenong",
    "2108694e-5804-4164-a1c6-7a97d6c82ddb": "Daylesford (sensor/indicative)",
    "8f03fc05-84f0-4aef-befb-37725c9c5d69": "Drysdale (sensor/indicative)",
    "1ddbf1d8-eb8b-43cd-acca-9c23c29ff338": "Echuca (sensor/indicative)",
    "86a49d71-03f4-4589-af5a-cc63b730faaf": "Flynn (sensor/indicative)",
    "7e56abba-a570-4139-ad68-f45033862599": "Flynns Creek (sensor/indicative)",
    "031354b3-b6a2-403b-aae3-79e18f69c957": "Footscray",
    "5fa9b7aa-651d-4c9d-96b1-8f6813b2d933": "Geelong South",
    "3420cbd3-a860-455b-813d-38656d72ef11": "Gisborne (sensor/indicative)",
    "3d1a81e7-ef78-4800-80c6-cc7e6ea01cf4": "Glengarry (sensor/indicative)",
    "262abeb7-7cd3-44ea-abb5-14f80a355bfa": "Hamilton (sensor/indicative)",
    "a2a029b2-5c5d-4d96-b9ca-943827256229": "Hastings",
    "22b21e76-76f2-4b0d-b133-3fc852c721b5": "Healesville (sensor/indicative)",
    "f9a9a4b6-7067-41d4-93e2-3cc39fb0784b": "Heathcote (sensor/indicative)",
    "51bff557-dea8-44b3-8ae3-10897be6df61": "Heywood (sensor/indicative)",
    "5e9e5f47-e85b-493e-9b39-e6b5f282bc61": "Horsham (sensor/indicative)",
    "f3aaef44-43be-4557-b572-5de293dd1d85": "Kerang (sensor/indicative)",
    "13be38f2-816d-4c99-8d0b-ec59fdcc952f": "Kinglake (sensor/indicative)",
    "cc5367e5-58b2-4e08-b9ec-920d9afe72ca": "Kyneton (sensor/indicative)",
    "9888bb86-6422-44e6-9f7c-92fc38f2736d": "Lakes Entrance (sensor/indicative)",
    "6bfdd604-0c03-4ea3-8783-782a3673441f": "Lancefield (sensor/indicative)",
    "3aacf39f-dda4-4716-8db4-58b7ea2767b1": "Leongatha (sensor/indicative)",
    "bafb0050-7888-4477-bff7-733f1608c8c6": "Lorne (sensor/indicative)",
    "8ed3a265-73dc-4458-8977-13cb6f533ef5": "Macedon (sensor/indicative)",
    "fd9971b2-130e-4163-b56c-a37beadc7846": "Macleod",
    "57f7b166-7696-4238-8a9b-8a1505e7de8f": "Maffra (sensor/indicative)",
    "58da8231-682a-44ce-97ee-17de937c3782": "Mallacoota (sensor/indicative)",
    "6f12e44a-29d7-4ca9-9756-bcb444962af4": "Mansfield (sensor/indicative)",
    "4afe6adc-cbac-4bf1-afbe-ff98d59564f9": "Melbourne CBD",
    "ea40fbea-46ce-4acf-8f3e-eb76c26c712b": "Melton",
    "4246f120-80ff-44e5-9c94-ec5a16a7276e": "Mildura",
    "48b39f0a-0ea6-4016-b8f2-23adbc72897a": "Mildura (sensor/indicative)",
    "f5c385fd-c136-4398-99b0-35696b711b7b": "Moe",
    "9348c1f5-60c5-4c35-b4f1-1f0931ab1415": "Mooroolbark",
    "032edf91-3cb9-42be-8ff3-70d3f56dba68": "Morwell East",
    "33f48fb3-f771-49e8-b554-0fcec8eb70bb": "Morwell South",
    "fd3acb94-4a2f-40da-bfe0-09245cd39ff6": "Mount Clear",
    "703c0c30-adc6-4e69-94cc-78b8aaa23255": "Myrtleford (sensor/indicative)",
    "eb624ae2-42e4-49eb-a8e0-025121c9d629": "Orbost (sensor/indicative)",
    "63f9b336-cf04-41a4-a08b-cbdb2d20a351": "Ouyen (sensor/indicative)",
    "15b90658-97fe-42a4-8bb8-cfc5cc90cdc9": "Point Cook",
    "0f58d8a5-4856-4de8-8ce8-5a741e27522c": "Portland (sensor/indicative)",
    "63a73778-4244-481b-82d9-3a7c416832eb": "Rosedale",
    "f2190dd1-176f-439f-856d-b7ca1a7b00cd": "Rosedale (sensor/indicative)",
    "c2d7348a-918e-444f-9cf1-3f67055cd90a": "Rutherglen (sensor/indicative)",
    "cfe63589-fcb8-4a85-b500-4920b37f92e7": "Sale (sensor/indicative)",
    "6e1cb2da-1537-40b4-b011-9519095d7e06": "Shepparton (sensor/indicative)",
    "b2972c05-c6c6-4d50-94ad-7fa53722e9d0": "Spotswood",
    "2fcbe861-b685-4088-b042-31b8f53ac118": "Stawell",
    "07967f24-444c-4fd8-901c-9c0c67144053": "Sunbury (sensor/indicative)",
    "f70a1ce9-691e-4dff-83e4-792065d77779": "Swan Hill",
    "0968ba97-5cdf-464a-a8be-8ae789b83f37": "Swan Hill (sensor/indicative)",
    "cc0b9034-7758-4c8e-9680-7fc2915fdcb8": "Torquay (sensor/indicative)",
    "70584bae-a7e7-4ae9-adf5-1e8e92b15386": "Traralgon",
    "33fd2638-98ff-4b6c-8b75-5feecae706df": "Traralgon East (sensor/indicative)",
    "cddf953a-b932-4918-97ea-1d19583d507a": "Traralgon South (sensor/indicative)",
    "69fa2d5e-557c-457a-9103-21bc2609f5eb": "Tyers North (sensor/indicative)",
    "d9c23fd4-2ed0-4627-87a7-4199bffad9b4": "Wallan (sensor/indicative)",
    "8413d21d-5440-4f2b-81f9-2e5cfb8620d0": "Wangaratta",
    "27088121-4310-48ce-8d3f-b1ec5c1608c6": "Warburton (sensor/indicative)",
    "c7d0c270-8c0e-4f5d-8d3b-cd15e786cbbc": "Warragul (sensor/indicative)",
    "3a5e1716-5612-4f3e-a3d6-a924c0899804": "Warrnambool (sensor/indicative)",
    "3a0e909b-a278-4c5b-8786-975c5ef4c4c9": "Willow Grove (sensor/indicative)",
    "7c3c27ba-2255-4c0a-b604-94ae63959a51": "Wodonga (sensor/indicative)",
    "6006c323-1709-4b4f-a048-040f51cc801e": "Wonthaggi (sensor/indicative)",
    "a4f9fa11-1e9b-45eb-9473-9a8418a1c6bf": "Yallourn North (sensor/indicative)",
    "fc15d85f-4141-4949-b2ef-e93c5c825205": "Yarra Glen (sensor/indicative)",
    "ea05039d-28a1-4cd4-838a-648a7843059a": "Yarrawonga (sensor/indicative)",
    "932e8220-8d30-4e51-9200-e5b1ec8f87fb": "Yinnar",
    "aa39a036-4514-4b51-aaf4-6276e98b036c": "Yinnar (sensor/indicative)",
}
