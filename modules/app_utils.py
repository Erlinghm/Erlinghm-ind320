"""Streamlit-specific glue for the app: the shared, sidebar-rendered area
selector used across pages, and thin st.cache_data wrappers around the
plain functions in data_utils.py/weather_utils.py so Streamlit's "rerun the
whole script on every interaction" model doesn't repeat expensive work.

Kept separate from data_utils.py/weather_utils.py/analysis_utils.py on
purpose - those stay importable and testable without Streamlit installed
(as used directly in the Part 3 notebook); this module is the only place
that couples them to Streamlit.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from modules.data_utils import load_data, filter_area_type
from modules.mongo_utils import get_weather_collection
from modules.weather_utils import sample_points_per_region

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUDOMRADER_SHP = PROJECT_ROOT / "data/shapefiles/budomrader/Budområder.shp"

AREA_TYPE_HELP = (
    "EL = the 5 electricity price zones (NO1-NO5); "
    "NO = the national total (one area only); "
    "VASS = the 3 watercourse regions."
)


def area_selector():
    """Render the shared area picker in the sidebar and return
    (area_type, area_number).

    This is deliberately global, not local to each page: it's the one
    selector that every area-dependent page (Table, Plot, and the new Fill
    Degree / Weather Download / Weather Analysis pages) reads from, via
    fixed widget keys - so picking EL/NO3 on one page keeps it picked when
    you switch to another, and the weather pages download/analyse exactly
    the area this selector is set to, per the assignment's "let the choice
    of downloaded data depend on the selector used for the magasinstatistikk"
    instruction. Table and Plot only need the area_type half (they show
    every area of that type at once); the new single-series pages also need
    area_number to narrow down to just one.
    """
    st.sidebar.markdown("### Area")
    area_type = st.sidebar.radio(
        "Area type",
        options=["EL", "NO", "VASS"],
        index=0,
        key="area_type",
        help=AREA_TYPE_HELP,
    )

    if area_type == "EL":
        area_number = st.sidebar.selectbox(
            "Price zone",
            options=[1, 2, 3, 4, 5],
            index=2,  # NO3 - the zone used throughout the Part 3 notebook
            format_func=lambda n: f"NO{n}",
            key="area_number_el",
        )
    elif area_type == "VASS":
        area_number = st.sidebar.selectbox(
            "Watercourse region",
            options=[1, 2, 3],
            key="area_number_vass",
        )
    else:
        area_number = 0
        st.sidebar.caption("National total - one area only.")

    return area_type, area_number


@st.cache_data
def get_fill_degree_series(area_type, area_number):
    """The weekly fill_degree series for one specific area - cached so
    switching back to an already-picked area (or just navigating between
    pages) doesn't refetch/refilter magasinstatistikk's full history.
    """
    data = load_data()
    areas = filter_area_type(data, area_type)
    return areas.loc[areas["area_number"] == area_number, "fill_degree"].sort_index()


@st.cache_data
def get_el_sampled_points(seed=0, n_points=1000):
    """The 1000 sampled lon/lat points per EL price zone (NO1-NO5), from
    the budomrader shapefile - cached because sampling (and reading the
    shapefile) is pure CPU/disk work with a fixed seed, so it only needs to
    run once per session rather than on every rerun.
    """
    points = sample_points_per_region(BUDOMRADER_SHP, "budomr", n_points=n_points, seed=seed)
    points["region"] = points["region"].str.replace(" ", "")  # "NO 3" -> "NO3"
    return points
@st.cache_data(ttl=3600)
def get_weather_hourly_avg_from_mongo(region_label, year):
    """The pre-aggregated hourly weather average for one region/year, read
    straight from MongoDB - this is what the Cassandra -> Spark -> MongoDB
    pipeline in the Part 3 notebook populates (so far just NO3, 2024).

    Returns None if that region/year isn't in MongoDB yet (incomplete or
    missing entirely) - that's not an error, it just means the caller
    should fall back to the open-meteo download + on-the-fly pandas
    aggregation instead. Checking MongoDB first like this is what lets the
    weather pages work on Streamlit Community Cloud, which has no
    persistent local disk for the CSV cache the fallback path relies on -
    whichever region/year has actually been pushed to MongoDB loads
    instantly there with no network call, while anything not yet pushed
    still works via the original download flow.

    Filters by year in pandas rather than with a Mongo-side string range
    query on `timestamp` - the pipeline writes `timestamp.isoformat()`,
    and whether that comes out tz-aware ("...+00:00") or naive depends on
    what Spark's toPandas() handed back, which isn't worth hard-coding
    here. pd.to_datetime parses either form, so filtering client-side
    after fetching is the robust option; this also means a stray
    out-of-year document (e.g. a leading/trailing hour from an
    aggregation edge case) is naturally excluded rather than tripping up
    a brittle string-prefix comparison.
    """
    expected_hours = len(pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h"))
    collection = get_weather_collection()
    docs = list(collection.find({"region": region_label}))
    if not docs:
        return None

    df = pd.DataFrame(docs)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if df["timestamp"].dt.tz is not None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    df = df[df["timestamp"].dt.year == year]
    if len(df) != expected_hours:
        return None

    df = df.set_index("timestamp").rename(columns={
        "temperature_2m_avg": "temperature_2m",
        "precipitation_avg": "precipitation",
        "snowfall_avg": "snowfall",
    })
    return df[["temperature_2m", "precipitation", "snowfall"]].sort_index()
