import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.app_utils import get_weather_hourly_avg_live
from modules.data_utils import filter_area_type, load_data
from modules.theme import SEQUENTIAL

st.title("Interactive Area Map")
st.caption(
    "Click an area to select it - the selection is stored and reused as the "
    "default area on the Correlation and Forecasting pages. GeoJSON converted "
    "from the project's shapefiles - see the Part 4 notebook. NO is the national "
    "total, drawn as all 5 EL zones dissolved into one outline (it has no region "
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
    area_type = st.selectbox(
        "Area type (shapefile)", options=["EL", "VASS", "NO"], format_func=lambda t: AREA_TYPE_LABELS[t],
    )
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

# A lot of weekly options to choose from (magasinstatistikk goes back to the
# late 1990s) - default to the most recent week rather than the oldest.
selected_week = st.select_slider(
    "Week", options=weeks, value=weeks[-1], format_func=lambda d: d.strftime("%Y-%m-%d"),
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
            f"{selected_week:%Y-%m-%d} (open-meteo's historical archive only goes up "
            f"to a few days ago) - try an earlier week, or switch back to "
            f"\"Reservoir fill degree\"."
        )
        st.stop()

locations = [int(loc) for loc in values.index]
z = list(values.to_numpy())
selected_area = st.session_state.get("map_selected_area")
selected_area_type = st.session_state.get("map_selected_area_type")
marker_line_width = [
    4 if (area_type == selected_area_type and loc == selected_area) else 1
    for loc in locations
]

# go.Choroplethmap (not the older go.Choroplethmapbox) - the newer trace
# built on MapLibre GL instead of Mapbox GL, so "carto-positron" is
# actually token-free here. The Mapbox-based version shows an "API key
# required" watermark on current Mapbox/Plotly versions even for styles
# that are documented as not needing a token - a Mapbox-side licensing
# change, not something fixable by just picking a different style name.
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
    if clicked_location != selected_area or area_type != selected_area_type:
        st.session_state["map_selected_area"] = clicked_location
        st.session_state["map_selected_area_type"] = area_type
        st.rerun()

if selected_area is not None and selected_area_type is not None:
    _, selected_labels = load_geojson(selected_area_type)
    st.success(
        f"Selected for other pages: {selected_area_type} area {selected_area} "
        f"({selected_labels.get(selected_area, '?')})"
    )
else:
    st.caption("No area selected yet - click one on the map above.")
