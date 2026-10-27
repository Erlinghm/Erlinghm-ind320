import pandas as pd
import streamlit as st

from data_utils import load_data, filter_area_type

st.title("Data Table")

data = load_data()

# Radio button to pick which type of area to look at. NO has only the
# national total (1 area), EL has 5 price zones, VASS has 4 watercourse
# regions - so switching this changes how many rows show up below.
area_type = st.radio("Area type", options=["EL", "NO", "VASS"], index=1)
areas = filter_area_type(data, area_type)

st.write(f"Full data ({area_type}):")

# Same "download interval" slider pattern as the Plot page - lets you narrow
# down which period of the already-cached data to look at, instead of always
# showing every single timestamp.
months = sorted(areas.index.to_period("M").astype(str).unique())
start_month, end_month = st.select_slider(
    "Select a range of months to show",
    options=months,
    value=(months[0], months[0]),
)
month_period = areas.index.to_period("M").astype(str)
mask = (month_period >= start_month) & (month_period <= end_month)
st.dataframe(areas.loc[mask])

st.write("One row per area number, with a sparkline of fill degree for its first month:")

# Grab just the first calendar month of data, same idea as before, but now
# built per area number instead of per measurement column
first_month_end = areas.index.min() + pd.DateOffset(months=1)
area_numbers = sorted(areas["area_number"].unique())

table_data = pd.DataFrame({
    "area_number": area_numbers,
    "fill_degree_first_month": [
        areas.loc[
            (areas["area_number"] == number) & (areas.index < first_month_end),
            "fill_degree",
        ].tolist()
        for number in area_numbers
    ],
})

st.dataframe(
    table_data,
    column_config={
        "area_number": st.column_config.NumberColumn("Area number"),
        "fill_degree_first_month": st.column_config.LineChartColumn(
            "Fill degree - first month trend",
            width="medium",
        ),
    },
    hide_index=True,
)
