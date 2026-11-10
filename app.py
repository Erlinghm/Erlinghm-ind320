import streamlit as st

st.set_page_config(page_title="IND320 - Norwegian Reservoirs", layout="wide")

st.title("IND320 - Norwegian Reservoir Data")

st.markdown(
    """
This project explores Norwegian water reservoir (magasinstatistikk) data, together with
weather data for the areas it covers.

Most pages share one area selector in the sidebar (electricity price zone NO1-NO5, the
national total, or a watercourse region) - pick an area there and it stays picked as you
move between pages.

The sidebar on the left contains the following pages:

- **Table** - the data shown as a table, with a small sparkline of the
  first month for each column
- **Plot** - an interactive plot of the reservoir data over time, with a
  column selector and a month-range slider
- **Fill Degree** - STL decomposition and a spectrogram of the selected
  area's reservoir fill degree
- **Weather Download** - downloads hourly ERA5 weather (open-meteo) for the
  selected price zone; its own page since this hits a rate-limited external
  API, so it only runs on an explicit button press
- **Weather Analysis** - outlier detection (DCT + Statistical Process
  Control) on precipitation and anomaly detection (Local Outlier Factor) on
  temperature, for whatever weather has already been downloaded
- **Cross-border** - Norway's physical electricity exchange with its four
  directly connected neighbours (Denmark, Netherlands, Germany, Great
  Britain) over the last two years, shown as a yearly export/import pie
  chart and a daily line plot, built on ENTSO-E data via Cassandra, Spark
  and MongoDB
- **Extra** - placeholder page for future work
"""
)
