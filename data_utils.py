import pandas as pd
import requests
import streamlit as st

MAGASIN_URL = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligData"


@st.cache_data
def load_data():
    """Fetch magasinstatistikk directly from NVE's API, rename headers to
    English, and filter to the national total ('NO'), giving one clean row
    per week. Cached so the API is only called once per app session, not on
    every rerun.
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

    national = df[df["area_type"] == "NO"].copy()
    national = national.sort_values("dato_Id").set_index("dato_Id")
    return national
