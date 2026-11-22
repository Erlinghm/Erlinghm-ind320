import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.app_utils import area_selector
from modules.data_utils import filter_area_type, load_data
from modules.theme import CATEGORICAL

st.title("Reservoir & Price Data")

data = load_data()

# Shared sidebar area selector (modules/app_utils.py) - only area_type is
# used here (every area of that type is shown at once), but it's the same
# global selector the other pages read from, so picking EL/VASS here keeps
# that choice when you navigate elsewhere.
area_type, _ = area_selector()
areas = filter_area_type(data, area_type)

if area_type == "EL":
    st.caption(
        "This page shows every EL price zone at once - the price-zone picker in "
        "the sidebar only narrows things down on the single-zone pages (Fill "
        "Degree, Weather, Forecast)."
    )

# One shared "download interval" slider for both tabs below, instead of the
# same slider being duplicated on two separate pages as it was pre-refactor.
months = sorted(areas.index.to_period("M").astype(str).unique())
start_month, end_month = st.select_slider(
    "Select a range of months",
    options=months,
    value=(months[max(0, len(months) - 12)], months[-1]),  # last 12 months by default
)
month_period = areas.index.to_period("M").astype(str)
mask = (month_period >= start_month) & (month_period <= end_month)
filtered = areas.loc[mask]

tab_plot, tab_table = st.tabs(["Interactive plot", "Table overview"])

with tab_plot:
    numeric_cols = ["fill_degree", "capacity_twh", "filling_twh",
                     "fill_degree_prev_week", "fill_degree_change"]
    selected_col = st.selectbox("Choose a column to plot", options=numeric_cols)

    fig = go.Figure()
    for i, area_number in enumerate(sorted(filtered["area_number"].unique())):
        series = filtered[filtered["area_number"] == area_number]
        fig.add_trace(go.Scatter(
            x=series.index, y=series[selected_col], mode="lines",
            name=f"{area_type}{area_number}",
            line=dict(color=CATEGORICAL[i % len(CATEGORICAL)]),
        ))
    fig.update_layout(
        title=f"{selected_col} by {area_type} area ({start_month} to {end_month})",
        xaxis_title="Date", yaxis_title=selected_col,
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

with tab_table:
    st.write(f"Full data ({area_type}), {start_month} to {end_month}:")
    st.dataframe(filtered)

    st.write("One row per area number, with a sparkline of fill degree for its first month:")
    # Grab just the first calendar month of data, built per area number.
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
