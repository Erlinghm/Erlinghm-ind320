"""Streamlit-specific glue for the app: the shared, sidebar-rendered area
selector used across pages, and thin st.cache_data wrappers around the
plain functions in data_utils.py/weather_utils.py so Streamlit's "rerun the
whole script on every interaction" model doesn't repeat expensive work.

Kept separate from data_utils.py/weather_utils.py/analysis_utils.py on
purpose - those stay importable and testable without Streamlit installed
(as used directly in the Part 3 notebook); this module is the only place
that couples them to Streamlit. For the same reason, the Streamlit-cached
MongoClient/collection helpers (get_mongo_client, get_crossborder_collection)
live here too, not in modules/mongo_utils.py - that module is meant to be
importable from the notebook with NO streamlit dependency at all, and even
just `import streamlit` (not calling anything st.cache_*-decorated) is
enough to print its "No runtime found"/"missing ScriptRunContext" warnings
outside a real app.
"""

from pathlib import Path

import certifi
import pandas as pd
import streamlit as st
from pymongo import MongoClient

from modules.data_utils import load_data, filter_area_type
from modules.mongo_utils import get_weather_hourly_avg
from modules.theme import register_template
from modules.weather_utils import sample_points_per_region, sample_points_per_vass_zone

# Registers the shared Plotly template as a side effect of importing this
# module - every page already imports something from here (area_selector,
# at least), so this is what makes every st.plotly_chart(...) in the app
# pick up the same colours/theme without each page having to call it
# itself. Registering more than once (e.g. Streamlit re-importing modules
# across pages) is harmless - it just re-sets the same template.
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
            "Watercourse zone",
            options=[1, 2, 3],
            format_func=lambda n: VASS_LABELS[n],
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


@st.cache_data
def get_vass_sampled_points(seed=0, n_points=1000):
    """The sampled lon/lat points per VASS watercourse zone (East=RS+RØ,
    West=RV, North=RM+RN - see modules/weather_utils.py), labeled
    VASS1/VASS2/VASS3 to match magasinstatistikk's own omrnr - cached for
    the same reason as get_el_sampled_points.
    """
    return sample_points_per_vass_zone(NVE_REGIONER_SHP, n_points=n_points, seed=seed)


def get_weather_region_label_and_points(area_type, area_number):
    """Resolve the shared area selector's (area_type, area_number) to the
    region_label/all_points pair the weather pages need - EL maps straight
    onto a budomrader price zone ("NO3"), VASS maps onto one of the 3
    grouped NVE_Region zones ("VASS1"/"VASS2"/"VASS3"). NO (the national
    total) has no corresponding region shapefile at all, so weather
    sampling doesn't support it - callers are expected to gate on
    area_type == "NO" before calling this.
    """
    if area_type == "EL":
        return f"NO{area_number}", get_el_sampled_points()
    return f"VASS{area_number}", get_vass_sampled_points()


@st.cache_data(ttl=3600)
def get_weather_hourly_avg_from_mongo(region_label, year):
    """Thin st.cache_data wrapper around mongo_utils.get_weather_hourly_avg()
    - see there for the actual Mongo read/validation logic. Kept as a
    separate, Streamlit-cached entry point here (rather than just calling
    the plain function directly from the pages) so repeated page
    reruns/navigations don't re-hit MongoDB for a region/year that's
    already been read once this session - this is what lets the weather
    pages work on Streamlit Community Cloud, which has no persistent local
    disk for the CSV cache the fallback path relies on.
    """
    return get_weather_hourly_avg(region_label, year)


@st.cache_resource  # Cache the MongoClient across reruns - it isn't serializable, so this
# needs st.cache_resource rather than st.cache_data. Lives here, not
# modules/mongo_utils.py, for the same reason the function below does -
# see this module's own docstring and mongo_utils.py's.
def get_mongo_client():
    return MongoClient(st.secrets["MONGODB_URI"], tlsCAFile=certifi.where())


def get_crossborder_collection():
    """The MongoDB collection for cross-border data (daily totals, not
    monthly - renamed from crossborder_monthly once the aggregation moved
    to daily granularity). Kept here rather than in modules/mongo_utils.py
    - which is meant to stay import-safe from the notebook with no
    Streamlit dependency at all - since this goes through the
    Streamlit-cached get_mongo_client() above.
    """
    return get_mongo_client()["ind320"]["crossborder_daily"]


@st.cache_data(ttl=3600)
def get_crossborder_docs(connection, year):
    """All cross-border flow documents for one connection/year, as a
    DataFrame - cached so the Cross-border Exchange page's year/direction
    totals and daily-by-month chart don't each re-query MongoDB on every
    rerun (e.g. every time the month pills selection changes), since both
    read from the exact same (connection, year) document set and only
    differ in how it's aggregated/filtered afterwards, in pandas.
    """
    docs = list(get_crossborder_collection().find({"connection": connection, "year": year}))
    return pd.DataFrame(docs)
