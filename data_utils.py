import pandas as pd
import requests
import streamlit as st

MAGASIN_URL = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligData"


@st.cache_data
def load_data():
    """Fetch the full magasinstatistikk history directly from NVE's API and
    rename headers to English. Keeps all area types (EL, NO, VASS) - pages
    filter down to whichever type the user picks via a radio button. Cached
    so the API is only called once per app session, not on every rerun.
    Note: this endpoint takes no query parameters, so there is no way to ask
    NVE for only a date range - the full history is always fetched once and
    cached, and any "download interval" control in the pages below only
    narrows down what we use from that cached data, not what is requested
    from NVE.
    """
    response = requests.get(MAGASIN_URL, timeout=30)
    response.raise_for_status()
    df = pd.DataFrame(response.json())
    df["dato_Id"] = pd.to_datetime(df["dato_Id"])

    df = df.rename(columns={
        "omrType": "area_type",
        "omrnr": "area_number",
        "iso_aar": "iso_year",
        "iso_uke": "iso_week",
        "fyllingsgrad": "fill_degree",
        "kapasitet_TWh": "capacity_twh",
        "fylling_TWh": "filling_twh",
        "neste_Publiseringsdato": "next_publish_date",
        "fyllingsgrad_forrige_uke": "fill_degree_prev_week",
        "endring_fyllingsgrad": "fill_degree_change",
    })

    return df.sort_values("dato_Id").set_index("dato_Id")


def filter_area_type(df, area_type):
    """Return only the rows for the given area type (EL, NO, or VASS)."""
    return df[df["area_type"] == area_type].copy()
