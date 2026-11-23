import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from modules.analysis_utils import sliding_window_correlation
from modules.app_utils import get_weather_hourly_avg_live
from modules.data_utils import filter_area_type, load_data
from modules.theme import CATEGORICAL, CHROME

st.title("Weather ↔ Reservoir Correlation")
st.caption(
    "Sliding-window correlation between a chosen weather property and reservoir "
    "fill degree, with adjustable lag and window length. Uses the area selected "
    "on the Interactive Area Map page (defaults to EL NO3 if none picked yet)."
)

area_type = st.session_state.get("map_selected_area_type", "EL")
area_number = st.session_state.get("map_selected_area", 3 if area_type == "EL" else 1)
st.caption(f"Area: **{area_type} {area_number}** - pick a different one on the Interactive Area Map page.")

if area_type == "NO":
    st.info(
        "Weather-based correlation isn't available for the national total - it has no "
        "region shapefile to sample weather from. Pick an EL price zone or a VASS "
        "watercourse zone on the Interactive Area Map page."
    )
    st.stop()

region_label = f"{'NO' if area_type == 'EL' else 'VASS'}{area_number}"

col1, col2 = st.columns(2)
with col1:
    weather_var = st.selectbox("Weather property", ["temperature_2m", "precipitation", "snowfall"])
with col2:
    year = st.selectbox("Year", options=[2024], help="Weather is fetched live from open-meteo for this one calendar year.")

st.caption(
    f"Weather is only fetched for **{year}** (one live open-meteo request) - the top panel below "
    f"shows {region_label}'s full fill-degree history for context, but the weather and correlation "
    f"panels only have real values inside {year}; everything outside that one year is blank."
)

with st.spinner(f"Fetching live weather for {region_label}, {year} from open-meteo (cached after the first visit)..."):
    try:
        hourly = get_weather_hourly_avg_live(area_type, area_number, year)
    except RuntimeError as e:
        st.error(str(e))
        if e.__cause__ is not None:
            st.caption(f"Underlying cause: {e.__cause__!r}")
        st.stop()

weekly_weather = hourly[weather_var].resample("W").mean()

data = load_data()
areas = filter_area_type(data, area_type)
fill_degree = areas.loc[areas["area_number"] == area_number, "fill_degree"].resample("W").mean()

col1, col2 = st.columns(2)
with col1:
    window = st.slider("Window length (weeks)", min_value=4, max_value=26, value=8)
with col2:
    lag = st.slider(
        "Lag (weeks)", min_value=-12, max_value=12, value=0,
        help="Positive: weather leads fill degree by this many weeks (compares this "
             "week's fill degree against weather from `lag` weeks ago).",
    )

rolling_corr = sliding_window_correlation(fill_degree, weekly_weather, window=window, lag=lag)

fig = make_subplots(
    rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.32, 0.32, 0.36],
    subplot_titles=(f"{region_label} fill degree", weather_var, f"Rolling correlation (window={window}, lag={lag})"),
)
fig.add_trace(go.Scatter(x=fill_degree.index, y=fill_degree, line=dict(color=CATEGORICAL[0])), row=1, col=1)
fig.add_trace(go.Scatter(x=weekly_weather.index, y=weekly_weather, line=dict(color=CATEGORICAL[1])), row=2, col=1)
fig.add_trace(go.Scatter(x=rolling_corr.index, y=rolling_corr, line=dict(color=CATEGORICAL[6])), row=3, col=1)
fig.add_hline(y=0, line_dash="dot", line_color=CHROME["baseline"], row=3, col=1)
fig.update_yaxes(range=[-1, 1], row=3, col=1)
fig.update_layout(height=750, showlegend=False)
st.plotly_chart(fig, use_container_width=True)

valid_corr = rolling_corr.dropna()
if len(valid_corr):
    st.metric("Latest rolling correlation", f"{valid_corr.iloc[-1]:.3f}")
    st.caption(
        f"Strongest correlation in this window/lag setting: {valid_corr.abs().idxmax():%Y-%m-%d} "
        f"({valid_corr.loc[valid_corr.abs().idxmax()]:.3f})."
    )
else:
    st.info("Not enough overlapping data for this window/lag combination to compute a correlation yet.")
