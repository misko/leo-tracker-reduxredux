# Public terrain data narrows the receiver-height question

**The public terrain estimate is about 54.6 m NAVD88, corresponding approximately to 22.1 m NAD83 ellipsoidal ground height using GEOID18.** This is not the antenna's WGS84 ellipsoidal height. Antenna height above ground and the frame/epoch conversion remain unresolved; neither is silently set to zero.

This evidence makes the earlier +100 m and +300 m height cases useful stress tests, not evidence that those are likely antenna heights. The next height comparison should distinguish public terrain evidence from an assumed mounting-height scenario, rather than optimize height from radio/reference agreement.

## Independent public measurements and provenance

The USGS Elevation Point Query Service returned the following at the operator's nominal horizontal coordinate and four points approximately 10 m away. The offsets are a terrain-context check, not a confidence region for horizontal position.

| Point | Reported NAVD88 ground elevation |
|---|---:|
| Nominal coordinate | 54.572 m |
| 10 m east | 54.685 m |
| 10 m west | 55.886 m |
| 10 m north | 56.520 m |
| 10 m south | 53.923 m |

All five responses identify raster 121893 and 1 m resolution. The [USGS raster metadata](https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/121893?f=pjson) identifies `CA_NoCal_Wildfires_B5b_QL1_2018`, explicitly specifies NAVD88, and links the source DEM. The [service metadata](https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer?f=pjson) describes a bare-earth DEM. Thus these values exclude the building/roof as the intended modeled surface; they do not establish antenna mounting elevation.

The point responses report acquisition date `3/2/2018`; raster-level metadata separately records a project interval 2017-12-01 through 2018-04-24 and publication date 2020-01-14. Preserve these differing metadata fields rather than inventing a single exact measurement epoch. They are historical terrain data, not a survey of the present installation.

USGS explains that EPQS interpolates DEM values and that location accuracy depends on the source. Its published aggregate service RMSE is not a site-specific uncertainty bound, and interpolated elevations are not surveyed control measurements. We therefore do not assign that aggregate RMSE to this antenna. [USGS accuracy documentation](https://www.usgs.gov/faqs/how-accurate-are-elevations-generated-elevation-point-query-service-national-map).

## Vertical datum conversion

The [NOAA geoid service](https://geodesy.noaa.gov/web_services/geoid.shtml) returned GEOID18 undulation **−32.477 m** and an `error` field of 0.031 m at the nominal coordinate. The service is designed for NAD83 ellipsoidal height and NAVD88 orthometric height conversion. Its model-error field is not an uncertainty for the DEM, the antenna, or the complete frame conversion.

Using the standard geoid relation `h = H + N` gives:

`54.571628571 + (−32.477) = 22.094628571 m`.

This is an approximate **NAD83-related ellipsoidal ground-height inference**, conditional on the queried location and datum conventions. It is not a completed NAD83-to-WGS84 coordinate transformation. The input nominal coordinate was supplied in EPSG:4326; no independently known NAD83 realization or installation epoch was provided. A precise transformation requires those definitions. Do not substitute 54.6 m NAVD88 directly into the research model's WGS84 ellipsoidal-height parameter.

The usable installation relation remains: ground ellipsoidal height, plus antenna height above local ground, with the required datum/frame transformation. Mounting height and actual WGS84 antenna height are explicitly null in `summary.json`.

## Consequence for localization

Public terrain evidence is independent of Doppler fitting but is queried at the supplied nominal site coordinate. It is a site-calibration input, not a blind method for locating an unknown receiver. The five samples span 53.923–56.520 m NAVD88; that range is sampled terrain variation, not a guaranteed bound or an antenna uncertainty interval.

The earlier height sensitivities show why tens of metres matter, but this report does not interpolate them into a claimed accuracy correction. Obtain the mounting height and datum/epoch information, or run clearly labelled ground-plus-mount sensitivity scenarios while preserving the original baseline. Do not claim that this terrain lookup validates the horizontal reference coordinate or resolves its uncertainty.

## Evidence and reproduction

Eight public HTTPS responses are preserved byte-for-byte: five elevation queries, one geoid query, raster metadata and service metadata. `receipts.json` binds URLs, UTC request times, response headers and SHA-256 hashes. Its `response_error_field` preserves each API's field named `error`; the numeric GEOID18 value is model metadata, not a failed HTTP request. A receipt-label clarification changed no source response bytes.

`summarize.py` verifies all response hashes and HTTP success, matching raster IDs, explicit NAVD88 metadata, reported resolution, model name and units before calculating the height. The script leaves unknown antenna fields null. Query decimals are retained for reproducibility, not claimed physical precision.

```sh
python3 reports/2026_09_29_public_elevation/fetch.py
python3 reports/2026_09_29_public_elevation/summarize.py
```

Use a fresh output context: writers create files exclusively, and public services can change. The numerical summary uses the saved responses. `evidence.sha256` seals the report, code, raw responses, receipts and summary. No RF, private archive mutation, production configuration change or remote publication occurred. Absolute subkm accuracy remains unverified.
