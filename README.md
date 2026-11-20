# IND320 - Norwegian Reservoir Data

Course project for NMBU's IND320. Explores Norwegian water reservoir
(magasinstatistikk) data together with the weather over the areas it
covers, and Norway's cross-border electricity exchange - built up across
three assignment parts, each in its own Jupyter notebook, with the results
served through a multi-page Streamlit app.

Live app: https://erlinghm-ind320.streamlit.app

## Data sources

- **NVE magasinstatistikk API** (`biapi.nve.no/magasinstatistikk`) - weekly
  reservoir fill-degree history for all of Norway's area types: the 5
  electricity price zones (EL, NO1-NO5), the national total (NO), and the
  watercourse zones (VASS). Fetched live and cached in the app
  (`modules/data_utils.py`).
- **NVE region shapefiles** (`data/shapefiles/`) - polygon geometry used to
  sample random points for weather lookups: `budomrader/Budområder.shp` for
  the 5 EL price zones, and `nve_regioner/NVE_Region.shp` for the 5 raw
  watercourse regions (RS, RØ, RV, RM, RN), which are grouped into VASS's 3
  actual zones - East (RS+RØ), West (RV), North (RM+RN) - per NVE's own
  region descriptions (`modules/weather_utils.py`).
- **Open-Meteo historical weather API** (`archive-api.open-meteo.com`) -
  hourly temperature, precipitation and snowfall for the sampled points in
  a selected zone, disk-cached per chunk (`modules/weather_utils.py`).
- **ENTSO-E Transparency Platform API** - physical cross-border electricity
  flow between Norway and its four directly connected neighbours (Denmark,
  Netherlands, Germany, Great Britain) (`modules/entsoe_utils.py`).
- **Cassandra -> Spark -> MongoDB pipeline** (Part 3 notebook) - raw
  downloaded weather is written to Cassandra, aggregated to hourly
  per-zone averages with Spark, and the result pushed to MongoDB so the
  Streamlit app (which has no persistent local disk once deployed) can
  read it straight away instead of re-downloading and re-aggregating.
  MongoDB also backs the cross-border daily totals shown on the
  Cross-border page. Connection details come from `.streamlit/secrets.toml`
  locally, or Streamlit Community Cloud's own secrets store when deployed -
  never from anything checked into GitHub.

## App structure

```
app.py                    # Landing page, sets page config and the sidebar overview
modules/
  data_utils.py            # NVE magasinstatistikk fetch/filter
  weather_utils.py          # Shapefile point sampling, VASS region grouping, open-meteo download/cache
  entsoe_utils.py            # ENTSO-E API fetch/parse
  mongo_utils.py              # MongoDB connection + collection helpers
  analysis_utils.py            # STL decomposition, spectrogram, DCT/SPC outliers, LOF anomalies
  app_utils.py                   # Shared sidebar area selector + st.cache_data wrappers used across pages
pages/
  1_Table.py                 # Reservoir data as a table, with a sparkline per column
  2_Plot.py                  # Interactive plot with column selector and month-range slider
  3_FillDegree.py             # STL decomposition and spectrogram of fill degree
  4_WeatherDownload.py         # On-demand hourly weather download for the selected zone
  5_WeatherAnalysis.py          # Precipitation outlier / temperature anomaly detection
  6_CrossBorder.py                # Norway's cross-border electricity exchange
  7_Extra.py                        # Placeholder for later work
notebooks/
  Jupyter_part1.ipynb        # Part 1: initial data exploration
  Jupyter_part2.ipynb         # Part 2: cross-border data (ENTSO-E)
  Jupyter_part3.ipynb          # Part 3: weather sampling/download, Cassandra -> Spark -> MongoDB pipeline
data/shapefiles/            # Region polygons (EL price zones, NVE watercourse regions)
```

Every page shares one sidebar area selector (`area_selector()` in
`modules/app_utils.py`) - the EL/NO/VASS area picked there stays picked
while navigating between pages, so e.g. the Weather Download and Weather
Analysis pages always operate on the same zone.
