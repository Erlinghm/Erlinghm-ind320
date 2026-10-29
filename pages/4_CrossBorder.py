import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from modules.entsoe_utils import CONNECTION_LABELS, CONNECTIONS
from modules.mongo_utils import get_crossborder_collection

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

# Get the MongoDB collection for cross-border data
collection = get_crossborder_collection()

col_left, col_right = st.columns(2)

with col_left:
    connection = st.radio(
        "Connection",
        list(CONNECTIONS.keys()),
        format_func=lambda c: CONNECTION_LABELS.get(c, c),
    )

    year = st.selectbox("Year", YEARS)

    docs = list(collection.find({"connection": connection, "year": year}))
    if not docs:
        st.info(f"No data stored for {year}.")
    else:
        totals = pd.DataFrame(docs).groupby("direction")["total_gwh"].sum()

        fig, ax = plt.subplots()
        ax.pie(
            totals.values,
            labels=[f"{d} ({v:.0f} GWh)" for d, v in totals.items()],
            autopct="%1.1f%%",
            startangle=90,
        )
        ax.set_title(f"{CONNECTION_LABELS.get(connection, connection)} - {year}")
        st.pyplot(fig)

with col_right:
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    selected_names = st.pills("Months", month_names, selection_mode="multi", default=month_names)
    selected_months = sorted(month_names.index(m) + 1 for m in selected_names)

    if not selected_months:
        st.info("Pick at least one month.")
    else:
        docs = list(
            collection.find({"connection": connection, "year": year, "month": {"$in": selected_months}})
        )
        if not docs:
            # A connection/year can have gaps for a particular month (ENTSO-E data
            # isn't always complete) - this used to crash with a KeyError on an
            # empty DataFrame instead of showing this message.
            st.info("No data for the selected months.")
        else:
            df = pd.DataFrame(docs)
            df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=df["day"]))
            df = df.sort_values("date")

            fig2, ax2 = plt.subplots()
            for direction, group in df.groupby("direction"):
                ax2.plot(group["date"], group["total_gwh"], marker="o", markersize=3, label=direction)
            ax2.set_xlabel("Date")
            ax2.set_ylabel("Energy (GWh/day)")
            ax2.set_title(f"{CONNECTION_LABELS.get(connection, connection)} - {year}")
            ax2.legend()
            fig2.autofmt_xdate(rotation=45)
            st.pyplot(fig2)

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
