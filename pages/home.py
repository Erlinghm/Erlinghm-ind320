import streamlit as st

st.title("IND320 - Norwegian Reservoir Data")

st.markdown(
    """
This project explores Norwegian water reservoir (magasinstatistikk) data, together with
weather, electricity cross-border flow and currency exchange data for the areas and
periods it covers, and forecasts reservoir filling a few months ahead.

There are two ways to pick an area, depending on the page: the older pages
(Reservoir & Price Data, Fill-Degree Decomposition, Weather Outliers & Anomalies)
share one area selector in the sidebar (electricity price zone NO1-NO5, the
national total, or a watercourse zone) - pick an area there and it stays picked
across those pages. The newer pages (Correlation, Forecasting) instead default
to whatever area you last clicked on the Interactive Area Map, so pick one
there first if you want to drive those two from a specific area.

See `README.md` on GitHub for the full project description, data sources and app
structure.

### Data Overview
- **Reservoir & Price Data** - the raw/aggregated reservoir data as an interactive
  plot and a table, with a small sparkline per area
- **Interactive Area Map** - a GeoJSON map covering all 3 area types (EL price
  zones, VASS watercourse zones, and NO - the national total, drawn as all 5 EL
  zones dissolved into one outline), coloured by fill degree or (for EL/VASS) a
  weather property for a chosen week; click an area to select it for the other
  pages
- **Cross-border Exchange** - Norway's physical electricity exchange with its four
  directly connected neighbours
- **Currency Rates** - EUR/USD exchange rates from Norges Bank

### Patterns & Anomalies
- **Fill-Degree Decomposition** - STL decomposition and a spectrogram of the
  selected area's reservoir fill degree
- **Weather Outliers & Anomalies** - outlier detection (DCT + Statistical Process
  Control) and anomaly detection (Local Outlier Factor) on a selected weather
  property, fetched live from open-meteo for the selected zone
- **Weather ↔ Reservoir Correlation** - sliding-window correlation between a
  selected weather property and reservoir fill degree, with adjustable lag and
  window length

### Forecasting
- **Water Magazine Filling Forecast** - River SNARIMAX forecast of reservoir
  filling a few months ahead, with selectable model/data settings and confidence
  intervals
"""
)
