import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.app_utils import _seed, get_weather_hourly_avg_live
from modules.data_utils import filter_area_type, load_data
from modules.theme import SEQUENTIAL

st.title("Interactive Area Map")
st.caption(
    "Click an area to select it - this is the same, single area selection used "
    "everywhere in the app (the sidebar picker on Reservoir Data, Fill-Degree "
    "Decomposition and Weather Outliers, plus Correlation and Forecasting - "
    "picking one here or there updates all of them). GeoJSON converted from the "
    "project's shapefiles - see the Part 4 notebook. NO is the national total, "
    "drawn as all 5 EL zones dissolved into one outline (it has no region "
    "shapefile of its own); EL and VASS cover the \"Price area\"/\"Water area\" "
    "cases from the assignment, and either one can also be coloured by a weather "
    "property instead."
)

GEOJSON_PATHS = {
    "EL": "data/geojson/budomrader.geojson",
    "VASS": "data/geojson/vass_regioner.geojson",
    "NO": "data/geojson/national.geojson",  # all 5 EL zones dissolved into one outline
}
AREA_TYPE_LABELS = {"EL": "EL - price zones", "VASS": "VASS - watercourse zones", "NO": "NO - national total"}


@st.cache_data
def load_geojson(area_type):
    with open(GEOJSON_PATHS[area_type], encoding="utf-8") as f:
        geojson = json.load(f)
    labels = {feature["properties"]["area_number"]: feature["properties"]["label"] for feature in geojson["features"]}
    return geojson, labels


col1, col2 = st.columns(2)
with col1:
    # Reseed from "sel_area_type" before creating this widget - a keyed
    # widget resets to its default whenever it's rendered on a different
    # page (see _seed()'s docstring), so without this, coming here from the
    # sidebar's own area-type radio would just snap back to EL.
    _seed("area_type", "sel_area_type", "EL")
    area_type = st.selectbox(
        "Area type (shapefile)", options=["EL", "VASS", "NO"], format_func=lambda t: AREA_TYPE_LABELS[t],
        key="area_type",
    )
    st.session_state["sel_area_type"] = area_type
with col2:
    if area_type == "NO":
        # The national total has no region shapefile of its own to sample weather
        # from (it's just all 5 EL zones dissolved into one outline), so only
        # fill degree makes sense to colour by here - same limitation as the
        # Weather Download/Outliers pages already have for NO.
        st.caption("Only fill degree is available for the national total - no region shapefile to sample weather from.")
        color_by = "Reservoir fill degree"
    else:
        color_by = st.radio("Colour by", ["Reservoir fill degree", "Weather property"], horizontal=True)

geojson, labels = load_geojson(area_type)

data = load_data()
areas = filter_area_type(data, area_type)
weeks = sorted(areas.index.unique())

# Default to the most recent week, except in weather mode - open-meteo's
# archive lags well behind today (saw it miss a week 11 days old), so
# weeks[-1] there just lands on "no weather data yet" every time. ~10
# weeks back works out of the box; the slider can still go all the way to
# the latest week, it'll just show that same message.
default_week = weeks[-1] if color_by == "Reservoir fill degree" else weeks[max(0, len(weeks) - 11)]
selected_week = st.select_slider(
    "Week", options=weeks, value=default_week, format_func=lambda d: d.strftime("%Y-%m-%d"),
)
# Stored so the Forecasting page can default its "forecast as of" date to
# whatever week is selected here, keeping the two pages' timeframes in sync.
st.session_state["map_selected_week"] = selected_week

if color_by == "Reservoir fill degree":
    week_data = areas.loc[areas.index == selected_week, ["area_number", "fill_degree"]]
    values = week_data.set_index("area_number")["fill_degree"]
    colorbar_title = "Fill degree"
else:
    weather_var = st.selectbox("Weather property", ["temperature_2m", "precipitation", "snowfall"])
    week_start, week_end = selected_week, selected_week + pd.Timedelta(days=6)
    rows = {}
    with st.spinner("Fetching live weather for each zone from open-meteo (cached after the first visit)..."):
        for area_number in sorted(areas["area_number"].unique()):
            try:
                hourly = get_weather_hourly_avg_live(area_type, area_number, selected_week.year)
            except RuntimeError as e:
                st.warning(f"Couldn't fetch weather for {area_type}{area_number}: {e}")
                continue
            week_hourly = hourly.loc[week_start:week_end]
            if len(week_hourly):
                rows[area_number] = week_hourly[weather_var].mean()
    values = pd.Series(rows, name=weather_var)
    colorbar_title = weather_var
    if values.empty:
        st.info(
            f"No weather data available for any {area_type} zone in the week of "
            f"{selected_week:%Y-%m-%d} - open-meteo's historical archive can lag "
            f"several weeks behind today, not just a few days. Try an earlier week, "
            f"or switch back to \"Reservoir fill degree\"."
        )
        st.stop()

locations = [int(loc) for loc in values.index]
z = list(values.to_numpy())
# Read the durable, cross-page selection (see _seed()'s docstring) instead
# of a map-only key - that's what makes a sidebar pick show up here too.
if area_type == "EL":
    selected_area = st.session_state.get("sel_area_number_el")
elif area_type == "VASS":
    selected_area = st.session_state.get("sel_area_number_vass")
else:
    selected_area = None
marker_line_width = [
    4 if loc == selected_area else 1
    for loc in locations
]

# go.Choroplethmap (not the older go.Choroplethmapbox) - the newer trace
# runs on MapLibre instead of Mapbox, so "carto-positron" is actually
# token-free here. The Mapbox version kept showing an "API key required"
# watermark even on styles documented as token-free - a Mapbox licensing
# change, not something fixable by just picking a different style.
fig = go.Figure(go.Choroplethmap(
    geojson=geojson,
    locations=locations,
    z=z,
    featureidkey="properties.area_number",
    colorscale=SEQUENTIAL,
    marker_opacity=0.7,
    marker_line_width=marker_line_width,
    marker_line_color="#0b0b0b",
    colorbar_title=colorbar_title,
    customdata=[labels.get(loc, str(loc)) for loc in locations],
    hovertemplate="%{customdata}<br>" + colorbar_title + ": %{z:.3f}<extra></extra>",
))
fig.update_layout(
    map_style="carto-positron",
    map_zoom=3.3,
    map_center={"lat": 64.5, "lon": 13},
    margin=dict(l=0, r=0, t=0, b=0),
    height=600,
)

event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="area_map_chart")
if event and event.get("selection", {}).get("points"):
    clicked_location = event["selection"]["points"][0]["location"]
    if clicked_location != selected_area:
        # Only sel_area_number_* needs writing - area_type's already
        # correct (it's this widget's own value), and its widget was
        # already created above this run so it can't be re-set here.
        if area_type == "EL":
            st.session_state["sel_area_number_el"] = clicked_location
        elif area_type == "VASS":
            st.session_state["sel_area_number_vass"] = clicked_location
        st.rerun()

if area_type == "NO":
    st.caption("NO is the national total - no sub-area to select, it already covers every zone.")
elif selected_area is not None:
    st.success(
        f"Selected everywhere in the app: {area_type} area {selected_area} "
        f"({labels.get(selected_area, '?')})"
    )
else:
    st.caption("No area selected yet - click one on the map above.")
