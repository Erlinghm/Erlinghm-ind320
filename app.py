import streamlit as st

st.set_page_config(page_title="IND320 - Norwegian Reservoirs", layout="wide")

# Grouped multi-page navigation (Part 4 restructure) - replaces the old
# pages/ folder auto-discovery (flat, numbered N_Name.py files) with an
# explicit, grouped structure: a front page, then 3 main sections, each
# listing its own pages - see notebooks/Jupyter_part4.ipynb for the sketch
# this follows. st.navigation() takes over page discovery entirely once
# called here, so file names/locations under pages/ no longer need numeric
# prefixes to control order - this list does that instead.
pg = st.navigation({
    "": [
        st.Page("pages/home.py", title="Home", default=True),
    ],
    "Data Overview": [
        st.Page("pages/reservoir_price.py", title="Reservoir & Price Data"),
        st.Page("pages/map.py", title="Interactive Area Map"),
        st.Page("pages/crossborder.py", title="Cross-border Exchange"),
        st.Page("pages/currency.py", title="Currency Rates"),
    ],
    "Patterns & Anomalies": [
        st.Page("pages/fill_degree.py", title="Fill-Degree Decomposition"),
        st.Page("pages/weather_analysis.py", title="Weather Outliers & Anomalies"),
        st.Page("pages/correlation.py", title="Weather ↔ Reservoir Correlation"),
    ],
    "Forecasting": [
        st.Page("pages/forecast.py", title="Water Magazine Filling Forecast"),
    ],
})
pg.run()
