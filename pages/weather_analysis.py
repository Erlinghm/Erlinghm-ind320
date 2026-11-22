import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.analysis_utils import lof_anomalies, spc_outliers
from modules.app_utils import (
    area_selector,
    get_weather_hourly_avg_from_mongo,
    get_weather_region_label_and_points,
)
from modules.theme import CATEGORICAL, STATUS
from modules.weather_utils import fetch_weather_for_region, weather_cache_status

st.title("Weather Outliers and Anomalies")

# Shared sidebar area selector (modules/app_utils.py) - same area as the
# Weather Download page, per the assignment's instruction to let the choice
# of downloaded data depend on the magasinstatistikk selector.
area_type, area_number = area_selector()

if area_type == "NO":
    st.info(
        "Weather-based analysis isn't available for the national total - it has no "
        "corresponding region shapefile to sample points from. Pick an EL price zone or a "
        "VASS watercourse zone in the sidebar to use this page."
    )
    st.stop()

region_label, all_points = get_weather_region_label_and_points(area_type, area_number)
year = 2024
start_date, end_date = f"{year}-01-01", f"{year}-12-31"

# Try MongoDB first - the Cassandra -> Spark -> MongoDB pipeline in the Part 3
# notebook pre-aggregates this, so when it's there this is a fast, no-network
# read that works anywhere, including Streamlit Community Cloud (which has no
# persistent local disk for the CSV cache the fallback below relies on).
hourly_avg = get_weather_hourly_avg_from_mongo(region_label, year)
source = "MongoDB"

if hourly_avg is None:
    # Not in MongoDB yet for this zone/year - fall back to the original
    # open-meteo CSV cache + on-the-fly pandas aggregation.
    cached, total = weather_cache_status(region_label, all_points, start_date, end_date)

    if cached < total:
        st.warning(
            f"Weather for {region_label}, {year} isn't available in MongoDB, and isn't "
            f"fully downloaded to disk either ({cached}/{total} chunk(s) cached)."
        )
        st.page_link("pages/weather_download.py", label="Go to the Weather Download page", icon="⬇️")
        st.stop()

    # Fully cached, so this is a disk-only read - no network call, safe to run
    # on every page visit/rerun (unlike the Weather Download page's button,
    # which is the only place that can trigger a new, potentially slow,
    # open-meteo request).
    weather = fetch_weather_for_region(region_label, all_points, start_date, end_date)
    hourly_avg = weather.groupby("timestamp")[["temperature_2m", "precipitation", "snowfall"]].mean()
    hourly_avg.index = pd.to_datetime(hourly_avg.index)
    hourly_avg = hourly_avg.sort_index()
    source = "local disk cache"

st.caption(f"{len(hourly_avg)} hourly readings for **{region_label}**, {year} (from {source}).")

WEATHER_VARS = ["temperature_2m", "precipitation", "snowfall"]

tab_spc, tab_lof = st.tabs(["Outlier / SPC", "Anomaly / LOF"])

with tab_spc:
    st.write(
        "High-pass filters the chosen weather property with a Discrete Cosine Transform to "
        "get its Seasonally Adjusted Temporal Variation (SATV), then flags outliers using "
        "robust Statistical Process Control boundaries estimated from the SATV."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        spc_var = st.selectbox("Weather property", WEATHER_VARS, key="spc_var")
    with col2:
        freq_cutoff_p = st.slider(
            "DCT frequency cutoff", 2, 200, 10, key="spc_freq",
            help="How many of the slowest-varying DCT coefficients make up the seasonal "
                 "trend that's subtracted out before looking for outliers - fewer "
                 "coefficients means a smoother trend and more residual variation.",
        )
    with col3:
        n_std = st.slider(
            "Number of standard deviations", 1.0, 6.0, 3.0, step=0.5, key="spc_std",
            help="Width of the SPC control limits, in robust standard deviations either "
                 "side of the SATV's centre - wider means fewer points flagged as outliers.",
        )

    values, is_outlier, lower_curve, upper_curve, precip_outliers = spc_outliers(
        hourly_avg[spc_var], freq_cutoff=freq_cutoff_p, n_std=n_std
    )
    index = hourly_avg.index

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=index, y=upper_curve, mode="lines", line=dict(color=CATEGORICAL[2], width=1, dash="dash"), name="SPC bounds", showlegend=True))
    fig.add_trace(go.Scatter(x=index, y=lower_curve, mode="lines", line=dict(color=CATEGORICAL[2], width=1, dash="dash"), name="SPC bounds", showlegend=False))
    fig.add_trace(go.Scatter(x=index, y=values, mode="lines", line=dict(color=CATEGORICAL[0], width=1), name=spc_var))
    fig.add_trace(go.Scatter(
        x=index[is_outlier], y=values[is_outlier], mode="markers",
        marker=dict(color=STATUS["critical"], size=6), name="outliers",
    ))
    fig.update_layout(
        title=f"{spc_var} outliers - {region_label}, {year}",
        xaxis_title="Time", yaxis_title=spc_var, hovermode="x unified", height=450,
    )
    st.plotly_chart(fig, use_container_width=True)

    m1, m2, m3 = st.columns(3)
    m1.metric("Outlier hours", len(precip_outliers))
    m2.metric("Share of hours", f"{len(precip_outliers) / len(hourly_avg):.2%}")
    m3.metric(
        "Max |SATV|",
        f"{precip_outliers['satv'].abs().max():.2f}" if len(precip_outliers) else "-",
    )
    st.dataframe(
        precip_outliers.sort_values("satv", key=abs, ascending=False),
        hide_index=True,
    )

with tab_lof:
    st.write(
        "Runs Local Outlier Factor on the DCT-deseasonalised residual of the chosen weather "
        "property (not the raw values), so anomalies that are unusual for their season but "
        "not extreme for the whole year still get caught - see the Part 3 notebook."
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        lof_var = st.selectbox("Weather property", WEATHER_VARS, index=0, key="lof_var")
    with col2:
        freq_cutoff_t = st.slider(
            "DCT frequency cutoff", 2, 200, 10, key="lof_freq",
            help="Same role as on the SPC tab - how smooth the seasonal trend removed "
                 "before LOF looks for anomalies is.",
        )
    with col3:
        contamination = st.slider(
            "Proportion of outliers", 0.001, 0.10, 0.01, step=0.001, format="%.3f", key="lof_contam",
            help="LOF's expected fraction of anomalous points - roughly how many hours end "
                 "up flagged, not an exact count.",
        )
    with col4:
        n_neighbors = st.slider(
            "LOF neighbors", 5, 100, 20, key="lof_neighbors",
            help="How many nearby residual values each point is compared against to judge "
                 "how isolated it is - more neighbors gives a smoother, less noisy notion "
                 "of 'isolated'.",
        )

    values2, is_outlier2, temp_anomalies = lof_anomalies(
        hourly_avg[lof_var], freq_cutoff=freq_cutoff_t, contamination=contamination, n_neighbors=n_neighbors
    )
    index2 = hourly_avg.index

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=index2, y=values2, mode="lines", line=dict(color=CATEGORICAL[0], width=1), name=lof_var))
    fig2.add_trace(go.Scatter(
        x=index2[is_outlier2], y=values2[is_outlier2], mode="markers",
        marker=dict(color=STATUS["critical"], size=6), name="anomalies",
    ))
    fig2.update_layout(
        title=f"{lof_var} anomalies - {region_label}, {year}",
        xaxis_title="Time", yaxis_title=lof_var, hovermode="x unified", height=450,
    )
    st.plotly_chart(fig2, use_container_width=True)

    m1, m2, m3 = st.columns(3)
    m1.metric("Anomalous hours", len(temp_anomalies))
    m2.metric("Share of hours", f"{len(temp_anomalies) / len(hourly_avg):.2%}")
    m3.metric(
        "Max LOF score",
        f"{temp_anomalies['lof_score'].max():.2f}" if len(temp_anomalies) else "-",
    )
    st.dataframe(temp_anomalies, hide_index=True)
