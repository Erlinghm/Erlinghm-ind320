import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.app_utils import get_weather_hourly_avg_live
from modules.data_utils import filter_area_type, load_data
from modules.forecast_utils import forecast_fill_degree
from modules.norgesbank_utils import fetch_exchange_rates
from modules.theme import CATEGORICAL

st.title("Water Magazine Filling Forecast")
st.caption(
    "SNARIMAX forecast (River, online learning) of weekly reservoir fill "
    "degree for one region, with selectable history length, model order, "
    "exogenous data sources, and quantile confidence bands (bonus). Area "
    "defaults to the app's one shared area selection; as-of date defaults to "
    "whatever week is selected on the Interactive Area Map, so the two pages "
    "stay in sync."
)

# No area widget on this page, so just read the durable, cross-page
# selection directly (see area_selector()'s _seed() docstring for why it's
# "sel_area_type" etc. and not "area_type" etc.).
area_type = st.session_state.get("sel_area_type", "EL")
if area_type == "EL":
    area_number = st.session_state.get("sel_area_number_el", 3)
elif area_type == "VASS":
    area_number = st.session_state.get("sel_area_number_vass", 1)
else:
    area_number = 0
st.caption(
    f"Area: **{area_type} {area_number}** - change it in the sidebar (Reservoir Data, "
    f"Fill-Degree Decomposition, Weather Outliers) or by clicking a zone on the "
    f"Interactive Area Map; either one updates it here too."
)

if area_type != "EL":
    st.warning(
        "Only EL price zones can be forecast right now - VASS watercourse zones and "
        "the NO national total aren't wired up here yet. Switch the Map page's area "
        "type to EL to forecast a price zone."
    )
    st.stop()

data = load_data()
areas = filter_area_type(data, "EL")
y_full = areas.loc[areas["area_number"] == area_number, "fill_degree"].sort_index()
y_full = y_full[~y_full.index.duplicated()]
region_label = f"NO{area_number}"

st.divider()
st.subheader("Model settings")

col1, col2, col3 = st.columns(3)
with col1:
    horizon_months = st.slider("Forecast horizon (months)", 1, 12, 3)
with col2:
    history_weeks = st.select_slider(
        "Training history length", options=["All", 52, 104, 156, 260], value=104,
        help="How many of the most recent weeks to train on - shorter history "
             "reacts faster to recent conditions, longer history captures more "
             "full seasonal cycles. 104 (2 years) is the walk-forward sweep's "
             "winner in the Part 4 notebook.",
    )
with col3:
    as_of_options = y_full.index.tolist()
    default_as_of = st.session_state.get("map_selected_week", as_of_options[-1])
    if default_as_of not in as_of_options:
        default_as_of = as_of_options[-1]
    as_of = st.select_slider(
        "Forecast as of", options=as_of_options, value=default_as_of,
        format_func=lambda d: d.strftime("%Y-%m-%d"),
    )

st.caption("SNARIMAX order - defaults are the best setting found by the walk-forward sweep in the Part 4 notebook.")
col1, col2, col3, col4 = st.columns(4)
with col1:
    p = st.number_input("AR order (p)", 0, 5, 1)
with col2:
    q = st.number_input("MA order (q)", 0, 5, 1)
with col3:
    sp = st.number_input("Seasonal AR (sp)", 0, 3, 0)
with col4:
    sq = st.number_input("Seasonal MA (sq)", 0, 3, 0)

col1, col2, col3 = st.columns(3)
with col1:
    d = st.number_input("Differencing (d)", 0, 2, 1)
with col2:
    sd = st.number_input("Seasonal differencing (sd)", 0, 2, 1)
with col3:
    m = st.number_input(
        "Seasonal period (m, weeks)", 0, 52, 52,
        help="52 = yearly seasonality on weekly data.",
    )

exogenous_sources = st.multiselect(
    "Exogenous data sources",
    options=["Temperature", "Precipitation", "Snowfall", "EUR/USD rate"],
    help="Future values for these are persisted forward from the last known "
         "reading/rate (there's no real forecast for the exogenous variables "
         "themselves), so treat their contribution as a what-if rather than a "
         "true forward forecast.",
)

quantile_width = st.select_slider(
    "Confidence interval width (bonus)", options=["None", "60%", "80%", "95%"], value="80%",
)

run = st.button("Run forecast", type="primary")

if not run:
    st.info("Set the parameters above and click **Run forecast**.")
    st.stop()

y = y_full.loc[:as_of]
history = None if history_weeks == "All" else int(history_weeks)
horizon_weeks = max(1, round(horizon_months * 52 / 12))

with st.spinner("Training the online model and forecasting..."):
    exogenous, future_exogenous = {}, {}
    future_dates = pd.date_range(as_of, periods=horizon_weeks + 1, freq="7D")[1:]

    if any(s in exogenous_sources for s in ("Temperature", "Precipitation", "Snowfall")):
        try:
            hourly = get_weather_hourly_avg_live("EL", area_number, as_of.year)
        except RuntimeError as e:
            st.warning(f"Couldn't fetch weather for {region_label}, {as_of.year} ({e}) - weather exogenous sources skipped.")
        else:
            weekly = hourly.resample("W").mean()
            name_map = {"Temperature": "temperature_2m", "Precipitation": "precipitation", "Snowfall": "snowfall"}
            for source in exogenous_sources:
                if source in name_map:
                    series = weekly[name_map[source]]
                    exogenous[source] = series
                    future_exogenous[source] = pd.Series(series.iloc[-1], index=future_dates)

    if "EUR/USD rate" in exogenous_sources:
        try:
            lookback_weeks = history if history is not None else 260
            rates = fetch_exchange_rates(
                currencies=("EUR",),
                start_date=(as_of - pd.Timedelta(weeks=lookback_weeks)).strftime("%Y-%m-%d"),
                end_date=as_of.strftime("%Y-%m-%d"),
            )
            weekly_rate = rates.set_index("date")["rate"].resample("W").mean()
            exogenous["EUR/USD rate"] = weekly_rate
            future_exogenous["EUR/USD rate"] = pd.Series(weekly_rate.iloc[-1], index=future_dates)
        except Exception as exc:
            st.warning(f"Could not fetch EUR/USD rates ({exc}) - skipping that exogenous source.")

    quantile_map = {
        "60%": (0.2, 0.5, 0.8), "80%": (0.1, 0.5, 0.9),
        "95%": (0.025, 0.5, 0.975), "None": (0.5,),
    }
    quantiles = quantile_map[quantile_width]

    forecast = forecast_fill_degree(
        y, horizon=horizon_weeks, history=history, exogenous=exogenous or None,
        future_exogenous=future_exogenous or None, p=p, d=d, q=q, m=m, sd=sd, sp=sp, sq=sq,
        quantiles=quantiles,
    )

st.success(f"Forecast complete - {horizon_weeks} weeks ahead from {as_of:%Y-%m-%d}.")

recent_history = y.iloc[-52:]
fig = go.Figure(
    data=[
        go.Scatter(x=recent_history.index, y=recent_history, mode="lines", name="Observed", line=dict(color=CATEGORICAL[0])),
        go.Scatter(x=forecast.index, y=forecast["median"], mode="lines", name="Forecast (median)", line=dict(color=CATEGORICAL[1])),
    ]
)
if quantile_width != "None":
    fig.add_trace(go.Scatter(
        x=list(forecast.index) + list(forecast.index[::-1]),
        y=list(forecast["upper"]) + list(forecast["lower"][::-1]),
        fill="toself", fillcolor="rgba(235,104,52,0.18)", line=dict(color="rgba(0,0,0,0)"),
        name=f"{quantile_width} interval", hoverinfo="skip",
    ))

# Frame-by-frame reveal of the forecast (one point further per frame), per
# the assignment's "plot the results using Plotly animation" ask - the
# observed history is static, only the forecast + band grow frame to frame.
frames = []
for i in range(1, len(forecast) + 1):
    partial = forecast.iloc[:i]
    frame_data = [
        go.Scatter(x=recent_history.index, y=recent_history, line=dict(color=CATEGORICAL[0])),
        go.Scatter(x=partial.index, y=partial["median"], line=dict(color=CATEGORICAL[1])),
    ]
    if quantile_width != "None":
        frame_data.append(go.Scatter(
            x=list(partial.index) + list(partial.index[::-1]),
            y=list(partial["upper"]) + list(partial["lower"][::-1]),
            fill="toself", fillcolor="rgba(235,104,52,0.18)", line=dict(color="rgba(0,0,0,0)"),
        ))
    frames.append(go.Frame(data=frame_data, name=str(i)))
fig.frames = frames

fig.update_layout(
    title=f"{region_label} fill degree - observed + forecast",
    xaxis_title="Date", yaxis_title="Fill degree", hovermode="x unified",
    updatemenus=[{
        "type": "buttons", "showactive": False, "x": 0.0, "y": 1.12,
        "buttons": [{
            "label": "▶ Animate forecast", "method": "animate",
            "args": [None, {"frame": {"duration": 250, "redraw": True}, "fromcurrent": True, "transition": {"duration": 0}}],
        }],
    }],
)

st.plotly_chart(fig, use_container_width=True)
st.dataframe(forecast)
