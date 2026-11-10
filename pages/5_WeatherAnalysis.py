import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from modules.analysis_utils import plot_precipitation_outliers, plot_temperature_anomalies
from modules.app_utils import area_selector, get_el_sampled_points
from modules.weather_utils import fetch_weather_for_region, weather_cache_status

st.title("Weather Outliers and Anomalies")

# Shared sidebar area selector (modules/app_utils.py) - same area as the
# Weather Download page, per the assignment's instruction to let the choice
# of downloaded data depend on the magasinstatistikk selector.
area_type, area_number = area_selector()

if area_type != "EL":
    st.info(
        "Weather-based analysis only covers EL (electricity price zones, NO1-NO5) so far - "
        "pick an EL zone in the sidebar to use this page."
    )
    st.stop()

region_label = f"NO{area_number}"
year = 2024
start_date, end_date = f"{year}-01-01", f"{year}-12-31"

all_points = get_el_sampled_points()
cached, total = weather_cache_status(region_label, all_points, start_date, end_date)

if cached < total:
    st.warning(
        f"Weather for {region_label}, {year} isn't fully downloaded yet "
        f"({cached}/{total} chunk(s) cached)."
    )
    st.page_link("pages/4_WeatherDownload.py", label="Go to the Weather Download page", icon="⬇️")
    st.stop()

# Fully cached, so this is a disk-only read - no network call, safe to run on
# every page visit/rerun (unlike the Weather Download page's button, which is
# the only place that can actually trigger a new, potentially slow, open-meteo
# request).
weather = fetch_weather_for_region(region_label, all_points, start_date, end_date)
hourly_avg = weather.groupby("timestamp")[["temperature_2m", "precipitation", "snowfall"]].mean()
hourly_avg.index = pd.to_datetime(hourly_avg.index)
hourly_avg = hourly_avg.sort_index()

st.caption(f"{len(hourly_avg)} hourly readings for **{region_label}**, {year}.")

tab_spc, tab_lof = st.tabs(["Outlier / SPC (precipitation)", "Anomaly / LOF (temperature)"])

with tab_spc:
    st.write(
        "High-pass filters precipitation with a Discrete Cosine Transform to get the "
        "Seasonally Adjusted Temporal Variation (SATV), then flags outliers using robust "
        "Statistical Process Control boundaries estimated from the SATV."
    )

    col1, col2 = st.columns(2)
    with col1:
        freq_cutoff_p = st.slider("DCT frequency cutoff", 2, 200, 10, key="spc_freq")
    with col2:
        n_std = st.slider("Number of standard deviations", 1.0, 6.0, 3.0, step=0.5, key="spc_std")

    ax, precip_outliers = plot_precipitation_outliers(
        hourly_avg["precipitation"], freq_cutoff=freq_cutoff_p, n_std=n_std
    )
    ax.set_title(f"Precipitation outliers - {region_label}, {year}")
    st.pyplot(ax.figure)
    plt.close(ax.figure)

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
        "Runs Local Outlier Factor on the DCT-deseasonalised temperature residual (not the "
        "raw values), so anomalies that are unusual for their season but not extreme for the "
        "whole year still get caught - see the Part 3 notebook."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        freq_cutoff_t = st.slider("DCT frequency cutoff", 2, 200, 10, key="lof_freq")
    with col2:
        contamination = st.slider(
            "Proportion of outliers", 0.001, 0.10, 0.01, step=0.001, format="%.3f", key="lof_contam"
        )
    with col3:
        n_neighbors = st.slider("LOF neighbors", 5, 100, 20, key="lof_neighbors")

    ax2, temp_anomalies = plot_temperature_anomalies(
        hourly_avg["temperature_2m"],
        freq_cutoff=freq_cutoff_t,
        contamination=contamination,
        n_neighbors=n_neighbors,
    )
    ax2.set_title(f"Temperature anomalies - {region_label}, {year}")
    st.pyplot(ax2.figure)
    plt.close(ax2.figure)

    m1, m2, m3 = st.columns(3)
    m1.metric("Anomalous hours", len(temp_anomalies))
    m2.metric("Share of hours", f"{len(temp_anomalies) / len(hourly_avg):.2%}")
    m3.metric(
        "Max LOF score",
        f"{temp_anomalies['lof_score'].max():.2f}" if len(temp_anomalies) else "-",
    )
    st.dataframe(temp_anomalies, hide_index=True)
