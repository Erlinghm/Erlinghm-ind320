"""Streamlit-specific helper functions: the area selector shown in the
sidebar, plus cached wrappers around the plain functions in
data_utils.py/weather_utils.py so Streamlit doesn't redo expensive work on
every rerun.

Kept separate from data_utils.py/weather_utils.py/analysis_utils.py on
purpose - those need to work without Streamlit installed too (they're used
directly in the Part 4 notebook). This is the only module that actually
imports streamlit - even just importing it prints warnings when there's no
real app running, which gets annoying in the notebook.

The MongoDB helpers (get_mongo_client, get_crossborder_collection) live
here too, for the same reason. Cross-border data is still read from Mongo;
weather isn't anymore - see get_weather_hourly_avg_live() below.
"""

from pathlib import Path

import certifi
import pandas as pd
import streamlit as st
from pymongo import MongoClient

from modules.data_utils import load_data, filter_area_type
from modules.theme import register_template
from modules.weather_utils import (
    get_weather_hourly_avg,
    sample_points_per_region,
    sample_points_per_vass_zone,
)

# Every page imports something from this module, so registering the
# colour template here means I don't have to call it separately on each
# page. Calling it more than once is harmless.
register_template()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUDOMRADER_SHP = PROJECT_ROOT / "data/shapefiles/budomrader/Budområder.shp"
NVE_REGIONER_SHP = PROJECT_ROOT / "data/shapefiles/nve_regioner/NVE_Region.shp"

AREA_TYPE_HELP = (
    "EL = the 5 electricity price zones (NO1-NO5); "
    "NO = the national total (one area only); "
    "VASS = the 3 watercourse zones (East, West, North)."
)

VASS_LABELS = {1: "East (VASS1)", 2: "West (VASS2)", 3: "North (VASS3)"}


def _seed(widget_key, durable_key, default):
    """Copies durable_key's value into widget_key right before that
    widget gets created (and sets a default for durable_key the first
    time it's used).

    Needed because of a real Streamlit gotcha: a keyed widget counts as a
    brand new widget whenever it's rendered on a different page - which
    page it's on is part of its "identity" - so it just resets to its
    index=/value= default. That's why clicking NO2 on the map used to set
    area_number_el directly, but the very next page's Price zone dropdown
    reset it straight back to NO3.

    Fix (this is what Streamlit's own docs recommend for exactly this):
    keep the real value under a key that's never itself used as a widget's
    key, so it can't get reset, and copy it into the actual widget key
    right before that widget is created, every time.
    """
    if durable_key not in st.session_state:
        st.session_state[durable_key] = default
    st.session_state[widget_key] = st.session_state[durable_key]


def area_selector():
    """Renders the area picker in the sidebar, returns (area_type, area_number).

    One global selector rather than one per page - Reservoir Data,
    Fill-Degree Decomposition and Weather Outliers & Anomalies all read
    from it, so picking EL/NO3 once keeps it picked everywhere else too
    (the assignment wants the area picked here to also decide which
    weather gets downloaded).

    The actual durable value lives in "sel_area_type"/"sel_area_number_el"/
    "sel_area_number_vass" (see _seed() above). The Map page reseeds its
    own area-type widget from "sel_area_type" and writes a click straight
    into the sel_area_number_* keys, and Correlation/Forecasting just read
    those three keys directly since they don't have an area widget of
    their own - so wherever you set it, here or on the map, it carries
    over everywhere.
    """
    st.sidebar.markdown("### Area")
    _seed("area_type", "sel_area_type", "EL")
    area_type = st.sidebar.radio(
        "Area type",
        options=["EL", "NO", "VASS"],
        key="area_type",
        help=AREA_TYPE_HELP,
    )
    st.session_state["sel_area_type"] = area_type

    if area_type == "EL":
        _seed("area_number_el", "sel_area_number_el", 3)  # NO3 - the zone used throughout the Part 3 notebook
        area_number = st.sidebar.selectbox(
            "Price zone",
            options=[1, 2, 3, 4, 5],
            format_func=lambda n: f"NO{n}",
            key="area_number_el",
        )
        st.session_state["sel_area_number_el"] = area_number
    elif area_type == "VASS":
        _seed("area_number_vass", "sel_area_number_vass", 1)
        area_number = st.sidebar.selectbox(
            "Watercourse zone",
            options=[1, 2, 3],
            format_func=lambda n: VASS_LABELS[n],
            key="area_number_vass",
        )
        st.session_state["sel_area_number_vass"] = area_number
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
def get_el_sampled_points(seed=0, n_points=50):
    """Sampled lon/lat points per EL price zone (NO1-NO5), from the
    budomrader shapefile. Cached since sampling (and reading the shapefile)
    is pure CPU/disk work with a fixed seed - only needs to run once a
    session.

    50 points per zone now, not the 1000 from Part 3 - back then it was a
    one-off manual download, now it runs inline every time a page needs
    weather, so it has to stay fast. 50 still fits in one open-meteo
    request, and nearby points are close enough together anyway that the
    extra 950 weren't adding much to the average.
    """
    points = sample_points_per_region(BUDOMRADER_SHP, "budomr", n_points=n_points, seed=seed)
    points["region"] = points["region"].str.replace(" ", "")  # "NO 3" -> "NO3"
    return points


@st.cache_data
def get_vass_sampled_points(seed=0, n_points=50):
    """Sampled lon/lat points per VASS watercourse zone (East=RS+RØ,
    West=RV, North=RM+RN - see weather_utils.py), labeled VASS1/2/3 to
    match magasinstatistikk's own numbering. Cached for the same reason as
    get_el_sampled_points, same smaller n_points too.
    """
    return sample_points_per_vass_zone(NVE_REGIONER_SHP, n_points=n_points, seed=seed)


def get_weather_region_label_and_points(area_type, area_number):
    """Turns the selector's (area_type, area_number) into the
    region_label/points pair the weather functions need. EL maps onto a
    budomrader price zone ("NO3"), VASS onto one of the 3 grouped
    NVE_Region zones ("VASS1" etc). NO has no region shapefile at all, so
    this doesn't support it - callers need to check for area_type == "NO"
    themselves first.
    """
    if area_type == "EL":
        return f"NO{area_number}", get_el_sampled_points()
    return f"VASS{area_number}", get_vass_sampled_points()


@st.cache_data(ttl=3600)
def get_weather_hourly_avg_live(area_type, area_number, year):
    """Hourly weather (temperature/precipitation/snowfall) averaged across
    a small sample of points in the given EL/VASS area, fetched live from
    open-meteo. Every weather page (Map, Weather Outliers & Anomalies,
    Correlation, Forecasting) calls this now.

    Replaces the old Part 3 pipeline (Cassandra -> Spark -> MongoDB,
    pre-aggregated). That meant everyone had to already have their own
    MongoDB seeded before the weather pages showed anything, and comparing
    notes with classmates it turned out people hadn't all set that up the
    same way. Cross-border data (get_crossborder_docs below) is still
    genuinely shared/pre-aggregated like that - just not weather anymore,
    that's fetched straight from open-meteo on demand instead.

    The ttl=3600 cache here is what keeps repeat visits/reruns fast -
    fetch_weather_for_region() underneath also disk-caches each chunk, so
    even a fresh session reuses what's already been downloaded, but
    caching here too skips even that disk read on every rerun.

    Raises RuntimeError if open-meteo's quota is used up or the request
    keeps failing - wrap this in try/except and show st.error. Doesn't
    work for area_type == "NO" (no region shapefile for the national
    total) - callers need to check for that themselves first.
    """
    region_label, points = get_weather_region_label_and_points(area_type, area_number)
    return get_weather_hourly_avg(region_label, points, year)


@st.cache_resource  # cache_resource, not cache_data - a MongoClient isn't
# serializable. Lives here rather than weather_utils.py for the same
# reason as this module's own docstring.
def get_mongo_client():
    return MongoClient(st.secrets["MONGODB_URI"], tlsCAFile=certifi.where())


def get_crossborder_collection():
    """The MongoDB collection for cross-border data (daily now, not
    monthly - renamed from crossborder_monthly once I switched the
    aggregation to daily). Lives here since it goes through the cached
    get_mongo_client() above.
    """
    return get_mongo_client()["ind320"]["crossborder_daily"]


@st.cache_data(ttl=3600)
def get_crossborder_docs(connection, year):
    """All cross-border documents for one connection/year, as a
    DataFrame. Cached so the page's totals and its daily chart don't both
    re-query MongoDB on every rerun - they read the exact same
    (connection, year) documents, just aggregate them differently
    afterwards in pandas.
    """
    docs = list(get_crossborder_collection().find({"connection": connection, "year": year}))
    return pd.DataFrame(docs)
