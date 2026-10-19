"""MongoDB connection helper for the Streamlit app.

Uses st.secrets rather than python-dotenv/.env (which the notebook and the
test_*.py scripts use) since this is the app's own runtime config - locally
from .streamlit/secrets.toml, and from Streamlit Community Cloud's own
secrets store once deployed (never from a value checked into GitHub).
"""

import certifi
import streamlit as st
from pymongo import MongoClient


@st.cache_resource
def get_mongo_client():
    """Cached across reruns - a MongoClient is not serializable, so this
    needs st.cache_resource rather than st.cache_data.
    """
    return MongoClient(st.secrets["MONGODB_URI"], tlsCAFile=certifi.where())


def get_crossborder_collection():
    return get_mongo_client()["ind320"]["crossborder_monthly"]
