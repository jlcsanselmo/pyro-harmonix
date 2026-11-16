# PyroHarmonix

**A WebGIS calendar for fire activity in any region, using NASA FIRMS MODIS and VIIRS observations.**

PyroHarmonix combines Django, React, and Docker to support reading seasonal patterns and changes in fire activity. Select an area and year, process FIRMS observations already stored in the database or request new data, and explore the map, calendar, and compare the activity with previous years.

[Submission presentation (PDF, 7 slides)](docs/pyroharmonix-spaceapps-demo.pdf) · [Demo harmonized CSV](docs/data/ribeirao-preto-2024-harmonized-snapshot.csv)

> **Scientific prototype:** counts and calibration are exploratory and do not represent burned area, fire prediction, or a validated product for operational decision-making. Results reflect only the data currently in the database; the absence of points does not mean no fire occurred.

## Real-world case: fires in inland São Paulo in 2024

In August and September 2024, fires affected municipalities around Ribeirão Preto. According to BDQueimadas/INPE data published by g1, between August 21 and September 7, six of the ten São Paulo cities with the most fire detections were in the region; Altinópolis and Pitangueiras led the ranking. The ten cities totaled 651 detections in the period.

### Satellite image and thermal hotspots

![NASA VIIRS/Suomi-NPP image from August 24, 2024, cropped to the Ribeirão Preto region, with thermal anomalies highlighted in red](docs/assets/ribeirao-preto-2024-08-24-viirs.jpg)

*NASA Worldview/GIBS, August 24, 2024. True-color VIIRS/Suomi-NPP composite with VIIRS thermal anomalies at 375 m. The crop covers the Ribeirão Preto region; the highlighted areas are thermal anomaly detections, not burn perimeters.*

### Daily evolution observed by satellite

![Animation of VIIRS images and thermal anomalies between August 21 and 31, 2024 in the Ribeirão Preto region](docs/assets/ribeirao-preto-fire-2024-aug.gif)

*Animation assembled by the project from 11 daily NASA Worldview/GIBS images, one per day between August 21 and 31, 2024. Images: VIIRS/Suomi-NPP in true color; VIIRS thermal anomaly layer at 375 m. Clouds can obscure hotspots, and differences in observation between days do not necessarily mean the fire began or ended at that instant.*

**Case sources:** [g1 Ribeirão Preto — six of the ten cities with the most hotspots were in the region](https://g1.globo.com/sp/ribeirao-preto-franca/noticia/2024/09/09/incendios-em-sp-6-das-10-cidades-com-mais-focos-sao-da-regiao-de-ribeirao-preto.ghtml) · [NASA Earthdata — smoke from fires in Brazil and Bolivia, observed on August 28, 2024](https://www.earthdata.nasa.gov/news/worldview-image-archive/thick-smoke-from-fires-brazil-bolivia) · [Open NASA Worldview](https://worldview.earthdata.nasa.gov/).

**Image attribution:** We acknowledge the use of images provided by the NASA Global Imagery Browse Services (GIBS), part of the NASA Earth Science Data and Information System (ESDIS). The images above are examples for context and are **not yet an integrated image layer in the interactive PyroHarmonix map**.

## What the WebGIS offers

- Interactive map of hotspots aggregated by H3 cell/day.
- Filters for period and area by coordinates.
- Monthly calendar and seasonality chart.
- Comparison of the selected month’s activity with the historical median.
- CSV export for filtered results.
- Processing, without external calls, of raw FIRMS data already stored for a given region and year.
- On-demand requests for new FIRMS data for a region and year, including estimated number of calls and collection time.
- Upload of external harmonized CSV data.

The interactive map uses OpenStreetMap as the basemap and shows the detected activity cells. It **currently does not display satellite imagery like the composition above or calculate scars/burned areas**.

### Data snapshot for reproduction

The repository includes a [harmonized CSV for Ribeirão Preto in 2024](docs/data/ribeirao-preto-2024-harmonized-snapshot.csv), exported from the local database. It contains 7,747 records by H3 cell/day, totaling 12,535 equivalent detections. Dates with records fall between January 1 and February 19 and between August 21 and August 31, 2024; this does not mean continuous coverage in those intervals. Annual collection was interrupted before completion. Dates without records in the CSV do not imply absence of fires. All records are marked as uncalibrated. Use it to reproduce the map and calendar, not as a complete time series or as an operational product.

### How the project addresses the challenge

| Need | Current implementation and limitation |
| --- | --- |
| MODIS historical series and VIIRS continuity | Queries the FIRMS Standard Processing products `MODIS_SP` and `VIIRS_SNPP_SP`, respecting each product’s start date. |
| User-selected region and period | Rectangular area by coordinates, one year per request, and a maximum area of 20° × 20°. It can be used anywhere in the world. |
| Fire activity calendar | Aggregates detections by H3 cell and day; shows monthly totals, seasonality, and comparison with the median of available years. |
| Explore patterns/anomalies | Compares with the historical median of the same window when there are at least two previous years with records; it is not an alert, forecast, or statistical test. |
| Download the search data | Exports the displayed hotspots to CSV. |
| Harmonize sensors | Computes an empirical monthly calibration when enough samples are present. While no calibration is available, results are marked as uncalibrated and should be interpreted cautiously. |

### Example of the WebGIS with real data: Ribeirão Preto, August 2024

![PyroHarmonix dashboard filtered for Ribeirão Preto in 2024, with map, seasonality, and calendar](docs/assets/pyroharmonix-ribeirao-preto-2024-current.png)

*Actual application capture filtered for 2024 in the area `-50,-23,-46,-20`. The local database contains **12,535 equivalent detections** in records from January–February and August 21–31; the map displays up to 5,000 cells. The annual collection was cancelled before finishing. Months without records in the dashboard should not be interpreted as months without fire.*

![PyroHarmonix calendar for the window of August 21–31, 2024 in Ribeirão Preto, with 12,476 equivalent detections](docs/assets/pyroharmonix-ribeirao-preto-2024-08-calendario.png)

*The August value corresponds to the completed request for August 21–31, 2024, not the entire month. The demo CSV [`docs/data/ribeirao-preto-2024-harmonized-snapshot.csv`](docs/data/ribeirao-preto-2024-harmonized-snapshot.csv) contains 7,747 H3/day records, all marked as **uncalibrated**. It is a sample of the data actually stored, not a complete annual coverage.*

## Run with Docker

Requirements: Docker Desktop and Docker Compose v2. The NASA FIRMS key is free; keep it only in the local `.env` file, never in `.env.example` or in Git.

In PowerShell, in the project folder:

```powershell
Copy-Item .env.example .env
notepad .env
```

Edit `FIRMS_MAP_KEY` in `.env` with your key from <https://firms.modaps.eosdis.nasa.gov/api/area/>. Then start the services:

```powershell
docker compose up -d --build
```

- WebGIS: <http://localhost:8081> (or the port defined by `WEB_PORT`).
- API health: <http://localhost:8081/api/health/>.
- Collection status and progress: <http://localhost:8081/api/ingestion-status/>.
- Worker logs: `docker compose logs -f firms-sync`.

PostgreSQL and the worker run in containers. Data and checkpoints stay in the Docker volume; restarting the services does not delete the collection. **Do not use `docker compose down -v`** if you want to preserve the data.

Without a configured key, the interface remains available and the worker reports that it is waiting for the key. After changing `.env`, recreate the worker to update the variable:

```powershell
docker compose up -d --build --force-recreate firms-sync
```

## Process existing data or search another region

In the dashboard, choose a year and provide the area rectangle. There are two actions:

1. **Process existing data** re-aggregates only FIRMS detections already present in the database for the selected area and year. It does not query NASA and does not consume API transactions. This is the option for analyzing data that was downloaded previously.
2. **Download + analyze** requests the available products for that region and year, then aggregates and harmonizes them. The queue is persistent and the worker resumes progress after restarts.

The map, calendar, medians, and CSV all consult the harmonized results stored in the database. A region/year with no local data may appear empty in the first mode; use **Download + analyze** to fetch the records. The initial installation may start without data; the screenshots in this README document a real query made during development.

Current limits:

- Up to 20° in width and 20° in height per area; for larger regions, split the search into rectangles.
- One year per request. Years from 2000 to the current year are accepted; MODIS starts on November 1, 2000.
- Up to five pending or processing requests.
- FIRMS is queried in intervals of up to five days, with pauses between calls and checkpoints.
- The **Download + analyze** button shows a heuristic duration range. It estimates 60–180 seconds per call, adjusted by the square root of the area in degrees² relative to 12°². Fire density, network, FIRMS response, and disk performance can increase the time. The estimate does not include local processing and does not predict the final database size.

The continuous national backfill for Brazil is **disabled by default** (`FIRMS_BRAZIL_BACKFILL_ENABLED=false`) to avoid unsolicited downloads and disk usage. On-demand collection works for other areas and countries. To opt into Brazil backfill, set `FIRMS_BRAZIL_BACKFILL_ENABLED=true` in `.env` and recreate the `firms-sync` service; this can consume substantial storage and time. Existing data and checkpoints are preserved. Monitor available disk space. To pause without deleting data, use `docker compose stop firms-sync`; resume with `docker compose start firms-sync`. **Do not use `docker compose down -v`** if you want to keep the PostgreSQL volume.

## Data and harmonization

NASA FIRMS Standard Processing products:

- `MODIS_SP` (Terra/Aqua; coverage from November 1, 2000).
- `VIIRS_SNPP_SP` (Suomi-NPP; coverage from January 20, 2012).

The pipeline:

1. Stores raw fire detections and FIRMS attributes in PostgreSQL.
2. Groups detections by H3 cell of resolution 8 (approximately 1 km², varying geographically) and UTC day.
3. When a calibration is available, it adjusts the VIIRS count for each month of the year; each product must have at least 500 detections in that calibration month.
4. When both sensors have records in the same cell/day, it calculates the average between the MODIS count and the adjusted VIIRS count. If only one sensor has records, it uses the available count, adjusted when applicable. Without a valid calibration, it keeps the neutral factor and marks results as uncalibrated.

### How MODIS and VIIRS are harmonized

The goal is to transform counts from the two sensors into a single H3/day series that can feed the same map and calendar:

1. The original FIRMS detections are stored with the product identifier (`MODIS_SP` or `VIIRS_SNPP_SP`), timestamp, coordinates, and attributes. This source is not deleted: raw records remain available for auditing and reprocessing.
2. Each detection is assigned to an H3 cell of resolution 8 and to a UTC day. The system counts MODIS and VIIRS records separately for each cell/day.
3. When a monthly calibration exists, it computes `factor = total MODIS / total VIIRS` for that month and applies the factor to the VIIRS count. The implemented calibration uses the Brazil study area and the configured historical window; it is only considered calibrated when both products have at least 500 records in the month.
4. If both sensors have counts in the same cell/day, the combined value is the average between the MODIS count and the adjusted VIIRS count. If only one sensor has records, the available count is used, with VIIRS adjustment when a calibrated factor exists.
5. The result is written as a harmonized observation (`MODIS+VIIRS-SNPP`) per cell/day. The map and analyses use this combined series instead of presenting two independent sensor series.

**Important limitations:** this is an empirical exploratory method, not a validated scientific harmonization. The factor is aggregated for Brazil and is not recalculated by region, biome, or requested area; applying it elsewhere in the world may not compensate for local sensor differences. On-demand collection does not compute calibration from a partial sample. Since national backfill is disabled by default, data may remain with a neutral factor and a **uncalibrated** status. Therefore, the source is no longer separated in the visualization, but it should not be considered irrelevant to scientific interpretation. Thermal anomaly detection also does not by itself identify the cause of the fire or measure burned area. This version does not include VIIRS NOAA-20/21, NRT products, cloud masking, biome stratification, or independent validation.

### Why the historical median may appear as “—”

The median and anomaly are calculated only when there are harmonized data for the current period and records in at least **two historical years** in the same month/day window. Periods without records are no longer automatically converted to zeros because they may indicate that data has not yet been collected or processed. Therefore, “—” means insufficient history, not an absence of fire.

In the example region, the demonstration database contains the request for **August 21–31, 2024**; that is not enough to calculate a multi-year median. To obtain a comparison, process existing data or download and analyze for the same area other years that include the desired month/period. The anomaly is `(observed − median) / median × 100` and remains unavailable when no reliable median exists. In the calendar, `—` and in the chart, an absence of recorded hotspots indicates missing stored records, not proof that no fire occurred, and may reflect incomplete coverage.

The FIRMS service limits queries to five days and documents up to 5,000 transactions per ten-minute interval; longer queries consume additional calls. The call estimate is not a guarantee of limits or duration. The worker maintains pauses and checkpoints, but the key is shared with any other use of the same MAP_KEY.

## Import harmonized data by CSV

Manual upload remains available for external harmonized datasets. The template can be downloaded via the **Download CSV Template** button in the application or via the `/api/template.csv` endpoint of the local installation.

| Column | Required | Description |
| --- | --- | --- |
| `latitude` | Yes | Decimal latitude from -90 to 90 |
| `longitude` | Yes | Decimal longitude from -180 to 180 |
| `acq_datetime` | Yes* | ISO 8601 date/time, for example `2024-08-12T03:00:00Z` |
| `acq_date` | Yes* | Date `YYYY-MM-DD`, alternative to `acq_datetime` |
| `acq_time` | No | Time `HH:MM` when using `acq_date` |
| `sensor` | No | Sensor or source |
| `confidence` | No | Confidence provided by the product |
| `frp` | No | Fire radiative power, non-negative value |

Each row represents one detection with weight 1. Imports are additive; duplicates are ignored. UTF-8 files have a 10 MB limit and 200,000 rows.

## API

- `GET /api/health/` — service health.
- `GET /api/ingestion-status/` — worker status and checkpoints per product.
- `GET /api/area-requests/` — recent area requests and their states.
- `GET /api/area-requests/estimate/?year=2024&south=-23&north=-20&west=-50&east=-46` — estimate calls and collection duration.
- `POST /api/area-requests/create/` — process stored data or request collection. Send `year`, `south`, `north`, `west`, `east`, and `download_sources` (`false` for local data only, `true` for download and analyze).
- `GET /api/analytics/` — totals, monthly calendar, and historical comparison.
- `GET /api/hotspots/` — cells for the map; up to 10,000 markers.
- `GET /api/hotspots.csv` — streaming CSV export.
- `GET /api/template.csv` — template for upload.
- `POST /api/upload/` — import multipart CSV using the `file` field.

Analytical endpoints accept `start`, `end`, `south`, `north`, `west`, and `east`. The comparison uses previous years with records in the same window as the final month and requires at least two historical years. Periods without records are not assumed to be zero because coverage may be incomplete.

## Local development

Backend (Python 3.12+):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py test
python manage.py runserver
```

Frontend (Node.js 22+), in another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

## References and credits

- [NASA FIRMS — Area API](https://firms.modaps.eosdis.nasa.gov/api/area/).
- [NASA FIRMS — active fire data](https://firms.modaps.eosdis.nasa.gov/).
- [NASA Earthdata — NASA Worldview](https://www.earthdata.nasa.gov/data/tools/worldview).
- [NASA Earthdata — Global Imagery Browse Services (GIBS)](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api).
- [NASA Worldview Snapshots](https://wvs.earthdata.nasa.gov/).
- [INPE — BDQueimadas](https://data.inpe.br/queimadas/bdqueimadas/).
- [g1 — fires in SP and municipalities around Ribeirão Preto, 2024](https://g1.globo.com/sp/ribeirao-preto-franca/noticia/2024/09/09/incendios-em-sp-6-das-10-cidades-com-mais-focos-sao-da-regiao-de-ribeirao-preto.ghtml).
- [OpenStreetMap — copyright and attribution](https://www.openstreetmap.org/copyright), used as the basemap.
- Technologies: [Django](https://www.djangoproject.com/), [React](https://react.dev/), [PostgreSQL](https://www.postgresql.org/), [Docker](https://www.docker.com/), [H3](https://h3geo.org/), and [Leaflet](https://leafletjs.com/).

## Use of AI tools

An AI assistant was used to support implementation and debugging, documentation review, and preparation of presentation text. The code and text were reviewed by the team. The satellite images and thermal hotspots are NASA Worldview/GIBS data/images, with attribution provided above; they were not generated by AI. No AI-generated audio or video was included.

## Scope and limitations

Calendars and medians are summaries of counts, not predictions. MODIS and VIIRS data are not directly equivalent; the result should only be treated as harmonized when calibration is available and validated. Stored coverage depends on the requests made and may be incomplete, even within the selected year. The application depends on internet access for the OpenStreetMap basemap and for new FIRMS downloads. For public deployment, configure `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `DJANGO_DEBUG=false`, allowed hosts, upload authentication, and a production application server.
