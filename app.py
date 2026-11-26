import streamlit as st

st.set_page_config(page_title="IND320 - Norwegian Reservoirs", layout="wide")

# Grouped navigation (the Part 4 restructure) - replaces the old flat,
# numbered pages/N_Name.py files with a front page plus 3 sections, each
# listing its own pages (see the sketch in the Part 4 notebook). Once
# st.navigation() is called it owns page discovery, so files under pages/
# don't need numeric prefixes anymore - this list sets the order instead.
pg = st.navigation({
    "": [
        st.Page("pages/home.py", title="Home", default=True),
    ],
    "Data Overview": [
        st.Page("pages/reservoir_price.py", title="Reservoir Data"),
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
