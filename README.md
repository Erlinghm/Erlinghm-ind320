# IND320 - Norwegian Reservoir Data

Course project for NMBU's IND320. Explores Norwegian water reservoir
(magasinstatistikk) data together with the weather over the areas it
covers, Norway's cross-border electricity exchange, EUR/USD exchange
rates, and a short-term forecast of reservoir filling - built up across
four assignment parts, each in its own Jupyter notebook, with the results
served through a multi-page Streamlit app.

Live app: https://erlinghm-ind320.streamlit.app

## Data sources

- **NVE magasinstatistikk API** (`biapi.nve.no/magasinstatistikk`) - weekly
  reservoir fill-degree history for all of Norway's area types: the 5
  electricity price zones (EL, NO1-NO5), the national total (NO), and the
  watercourse zones (VASS). Fetched live and cached in the app
  (`modules/data_utils.py`).
- **NVE region shapefiles** (`data/shapefiles/`) - polygon geometry used
  both for the Interactive Area Map's GeoJSON and to sample random points
  for weather lookups: `budomrader/Budområder.shp` for the 5 EL price
  zones, and `nve_regioner/NVE_Region.shp` for the 5 raw watercourse
  regions (RS, RØ, RV, RM, RN), which are grouped into VASS's 3 actual
  zones - East (RS+RØ), West (RV), North (RM+RN) - per NVE's own region
  descriptions (`modules/weather_utils.py`).
- **Open-Meteo historical weather API** (`archive-api.open-meteo.com`) -
  hourly temperature, precipitation and snowfall, averaged across a small
  sample of points per zone. Fetched live, on demand, every time a page
  needs it - there's no separate "download" step or database behind it,
  just a `st.cache_data`-wrapped fetch (`get_weather_hourly_avg_live()` in
  `modules/app_utils.py`, built on the point-sampling/disk-chunk-caching in
  `modules/weather_utils.py`). An earlier version of the app pre-aggregated
  this through a Cassandra -> Spark -> MongoDB pipeline instead, but that
  turned out to be a one-off local database rather than something every
  student's deployment shared, so Part 4 dropped it in favour of fetching
  straight from the API wherever it's needed.
- **ENTSO-E Transparency Platform API** - physical cross-border electricity
  flow between Norway and its four directly connected neighbours (Denmark,
  Netherlands, Germany, Great Britain) (`modules/entsoe_utils.py`).
- **Norges Bank's open data API** - EUR/USD exchange rates, also used as an
  optional exogenous input to the forecast (`modules/norgesbank_utils.py`).
- **MongoDB** - pre-aggregated daily cross-border totals only (from the
  ENTSO-E data above); weather is no longer stored here (see Open-Meteo
  above). Connection details come from `.streamlit/secrets.toml` locally,
  or Streamlit Community Cloud's own secrets store when deployed - never
  from anything checked into GitHub.

## App structure

```
app.py                       # Sets page config and the grouped navigation (st.navigation)
modules/
  data_utils.py               # NVE magasinstatistikk fetch/filter
  weather_utils.py             # Shapefile point sampling, VASS region grouping, open-meteo fetch/disk-cache
  entsoe_utils.py               # ENTSO-E API fetch/parse
  norgesbank_utils.py            # Norges Bank currency API fetch/parse
  analysis_utils.py               # STL decomposition, spectrogram, DCT/SPC outliers, LOF anomalies, sliding correlation
  forecast_utils.py                # River SNARIMAX forecasting with exogenous inputs + quantile confidence bands
  theme.py                          # Shared Plotly colour palette/template
  app_utils.py                       # Shared sidebar area selector + st.cache_data wrappers used across pages
pages/
  home.py                      # Landing page - project overview and page-by-page guide
  reservoir_price.py            # Reservoir data as a table + interactive plot, with a sparkline per area
  map.py                         # Interactive GeoJSON map (EL/VASS/NO), click to select an area for other pages
  crossborder.py                   # Norway's cross-border electricity exchange
  currency.py                       # EUR/USD exchange rates from Norges Bank
  fill_degree.py                      # STL decomposition and spectrogram of fill degree
  weather_analysis.py                  # Weather outlier (SPC) / anomaly (LOF) detection
  correlation.py                        # Sliding-window weather <-> fill-degree correlation
  forecast.py                            # River SNARIMAX forecast with confidence intervals
notebooks/
  Jupyter_part1.ipynb           # Part 1: initial data exploration
  Jupyter_part2.ipynb            # Part 2: cross-border data (ENTSO-E)
  Jupyter_part3.ipynb             # Part 3: weather sampling/download, STL/spectrogram/outlier analysis
  Jupyter_part4.ipynb              # Part 4: Norges Bank currency, River SNARIMAX forecasting, GeoJSON map, full Plotly restructure
data/shapefiles/              # Region polygons (EL price zones, NVE watercourse regions)
data/geojson/                 # GeoJSON converted from the shapefiles for the Interactive Area Map
```

Two ways to pick an area, depending on the page: the older pages
(Reservoir Data, Fill-Degree Decomposition, Weather Outliers &
Anomalies) share one sidebar selector (`area_selector()` in
`modules/app_utils.py`) - pick an area there and it stays picked across
those pages. The newer pages (Correlation, Forecasting) instead default to
whatever area was last clicked on the Interactive Area Map.

## Running locally

```
uv sync
uv run streamlit run app.py
```

Needs `MONGODB_URI` (for the cross-border data) in `.streamlit/secrets.toml`,
and `ENTSOE_API_KEY` (for the ENTSO-E fetch) in a `.env` file at the repo
root - neither is committed (see `.gitignore`).
