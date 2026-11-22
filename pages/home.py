import streamlit as st

st.title("IND320 - Norwegian Reservoir Data")

st.markdown(
    """
This project explores Norwegian water reservoir (magasinstatistikk) data, together with
weather, electricity cross-border flow and currency exchange data for the areas and
periods it covers, and forecasts reservoir filling a few months ahead.

Most pages share one area selector in the sidebar (electricity price zone NO1-NO5,
the national total, or a watercourse zone) - pick an area there and it stays picked
as you move between pages.

See `README.md` on GitHub for the full project description, data sources and app
structure.

### 📊 Data Overview
- **Reservoir & Price Data** - the raw/aggregated reservoir data as an interactive
  plot and a table, with a small sparkline per area
- **Interactive Area Map** - a GeoJSON map of the EL price zones and VASS
  watercourse zones (the national total has no region shapefile to map), coloured
  by fill degree or a weather property for a chosen week; click an area to select
  it for the other pages
- **Cross-border Exchange** - Norway's physical electricity exchange with its four
  directly connected neighbours
- **Currency Rates** - EUR/USD exchange rates from Norges Bank
- **Weather Download** - downloads hourly ERA5 weather (open-meteo) for the
  selected zone; its own page since this hits a rate-limited external API, so it
  only runs on an explicit button press

### 🔍 Patterns & Anomalies
- **Fill-Degree Decomposition** - STL decomposition and a spectrogram of the
  selected area's reservoir fill degree
- **Weather Outliers & Anomalies** - outlier detection (DCT + Statistical Process
  Control) and anomaly detection (Local Outlier Factor) on a selected weather
  property for whatever weather has already been downloaded
- **Weather ↔ Reservoir Correlation** - sliding-window correlation between a
  selected weather property and reservoir fill degree, with adjustable lag and
  window length

### 🔮 Forecasting
- **Water Magazine Filling Forecast** - River SNARIMAX forecast of reservoir
  filling a few months ahead, with selectable model/data settings and confidence
  intervals
"""
)
