"""Streamlit-free MongoDB read for the project - deliberately the ONLY
thing in here. modules/app_utils.py is the project's one designated
Streamlit-coupled module (see its own docstring); the Streamlit-cached
MongoClient/collection helpers used to live here too, which meant just
IMPORTING this module (even without calling any of the cached functions)
pulled in `streamlit` and printed its "No runtime found"/"missing
ScriptRunContext" warnings in the notebook - importing streamlit at all is
enough to trigger that, not just calling an st.cache_* function. Moved
those into app_utils.py instead so this module has no streamlit import at
all, and is genuinely safe to import from the notebook with no warnings.
"""

import os

import certifi
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()


def get_weather_hourly_avg(region_label, year):
    """The pre-aggregated hourly weather average for one region/year, read
    straight from MongoDB via a plain (non-Streamlit-cached) client - see
    modules/app_utils.py's get_weather_hourly_avg_from_mongo() for the
    st.cache_data-wrapped version the Streamlit app actually uses; this is
    the Streamlit-free version of the same read, for the notebook.

    Returns None if that region/year isn't in MongoDB yet (incomplete or
    missing entirely) - not an error, just means the caller should fall
    back to the open-meteo download + on-the-fly aggregation instead.

    Filters by year in pandas rather than with a Mongo-side string range
    query on `timestamp` - see the long version of this comment in
    app_utils.py; the short version is that the pipeline's timestamp
    strings aren't reliably tz-aware or naive, so a client-side filter
    after fetching is the robust option.
    """
    expected_hours = len(pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="h"))
    client = MongoClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())
    docs = list(client["ind320"]["weather_hourly_avg"].find({"region": region_label}))
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
