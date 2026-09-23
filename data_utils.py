import pandas as pd
import streamlit as st


@st.cache_data
def load_data():
    """Read reservoirs.csv, rename headers to English, and filter to the
    national total ('NO'), giving one clean row per week. Cached so the
    file is only read/processed once per app session, not on every rerun.
    """
    df = pd.read_csv("reservoirs.csv", parse_dates=["dato_Id"])
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
