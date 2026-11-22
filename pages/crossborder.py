import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.app_utils import get_crossborder_docs
from modules.entsoe_utils import CONNECTION_LABELS, CONNECTIONS
from modules.theme import CATEGORICAL

# Title and caption
st.title("Cross-border flows")
st.caption(
    "Norway's physical electricity exchange with its directly connected neighbours, "
    "via the ENTSO-E Transparency Platform."
)

# The two full years fetched for this assignment - see the Part 2 notebook. Hardcoded
# rather than discovered from MongoDB, so a stray document for some other year could
# never end up as a selectable option.
YEARS = [2024, 2025]

col_left, col_right = st.columns(2)

with col_left:
    connection = st.radio(
        "Connection",
        list(CONNECTIONS.keys()),
        format_func=lambda c: CONNECTION_LABELS.get(c, c),
    )

    year = st.selectbox("Year", YEARS)

    year_df = get_crossborder_docs(connection, year)
    if year_df.empty:
        st.info(f"No data stored for {year}.")
    else:
        totals = year_df.groupby("direction")["total_gwh"].sum()

        fig = go.Figure(go.Pie(
            labels=list(totals.index),
            values=totals.values,
            text=[f"{d} ({v:.0f} GWh)" for d, v in totals.items()],
            textinfo="percent+text",
            marker=dict(colors=CATEGORICAL[: len(totals)]),
        ))
        fig.update_layout(title=f"{CONNECTION_LABELS.get(connection, connection)} - {year}", height=420)
        st.plotly_chart(fig, use_container_width=True)

with col_right:
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    selected_names = st.pills("Months", month_names, selection_mode="multi", default=month_names)
    selected_months = sorted(month_names.index(m) + 1 for m in selected_names)

    if not selected_months:
        st.info("Pick at least one month.")
    elif year_df.empty:
        st.info("No data for the selected months.")
    else:
        df = year_df[year_df["month"].isin(selected_months)]
        if df.empty:
            # A connection/year can have gaps for a particular month (ENTSO-E data
            # isn't always complete) - this used to crash with a KeyError on an
            # empty DataFrame instead of showing this message.
            st.info("No data for the selected months.")
        else:
            df = df.copy()
            df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=df["day"]))
            df = df.sort_values("date")

            fig2 = go.Figure()
            for i, (direction, group) in enumerate(df.groupby("direction")):
                fig2.add_trace(go.Scatter(
                    x=group["date"], y=group["total_gwh"], mode="lines+markers",
                    marker=dict(size=5), line=dict(color=CATEGORICAL[i % len(CATEGORICAL)]),
                    name=direction,
                ))
            fig2.update_layout(
                title=f"{CONNECTION_LABELS.get(connection, connection)} - {year}",
                xaxis_title="Date", yaxis_title="Energy (GWh/day)", hovermode="x unified", height=420,
            )
            st.plotly_chart(fig2, use_container_width=True)

with st.expander("About this data"):
    st.markdown(
        "Cross-border physical flow data (`documentType=A11`) from the "
        "[ENTSO-E Transparency Platform](https://transparency.entsoe.eu/), covering Norway's "
        "four direct international interconnectors: NO2-DK1 (Skagerrak), NO2-NL (NorNed), "
        "NO2-DE (NordLink) and NO2-GB (North Sea Link), for the last two full years (2024-2025). "
        "Raw 15-minute/hourly readings were pulled from the RESTful API, written into Cassandra "
        "via Spark, aggregated to daily totals via Spark, and the daily totals stored in "
        "MongoDB - which is what this page reads from directly."
    )
