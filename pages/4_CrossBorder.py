import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from entsoe_utils import CONNECTION_LABELS, CONNECTIONS
from mongo_utils import get_crossborder_collection

# Title and caption
st.title("Cross-border flows")
st.caption(
    "Norway's physical electricity exchange with its directly connected neighbours, "
    "via the ENTSO-E Transparency Platform."
)

# Get the MongoDB collection for cross-border data
collection = get_crossborder_collection()

col_left, col_right = st.columns(2)

with col_left:
    connection = st.radio(
        "Connection",
        list(CONNECTIONS.keys()),
        format_func=lambda c: CONNECTION_LABELS.get(c, c),
    )

    years = sorted({doc["year"] for doc in collection.find({"connection": connection}, {"year": 1})})
    if years:
        year = st.selectbox("Year", years, index=len(years) - 1)

        docs = list(collection.find({"connection": connection, "year": year}))
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
    else:
        year = None
        st.info("No data stored yet for this connection.")

with col_right:
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    selected_names = st.pills("Months", month_names, selection_mode="multi", default=month_names)
    selected_months = sorted(month_names.index(m) + 1 for m in selected_names)

    if year is None:
        st.info("No data to plot.")
    elif not selected_months:
        st.info("Pick at least one month.")
    else:
        docs = list(
            collection.find({"connection": connection, "year": year, "month": {"$in": selected_months}})
        )
        df = pd.DataFrame(docs).sort_values("month")

        fig2, ax2 = plt.subplots()
        for direction, group in df.groupby("direction"):
            ax2.plot(group["month"], group["total_gwh"], marker="o", label=direction)
        ax2.set_xticks(selected_months)
        ax2.set_xticklabels([month_names[m - 1] for m in selected_months])
        ax2.set_xlabel("Month")
        ax2.set_ylabel("Energy (GWh)")
        ax2.set_title(f"{CONNECTION_LABELS.get(connection, connection)} - {year}")
        ax2.legend()
        st.pyplot(fig2)

with st.expander("About this data"):
    st.markdown(
        "Cross-border physical flow data (`documentType=A11`) from the "
        "[ENTSO-E Transparency Platform](https://transparency.entsoe.eu/), covering Norway's "
        "four direct international interconnectors: NO2-DK1 (Skagerrak), NO2-NL (NorNed), "
        "NO2-DE (NordLink) and NO2-GB (North Sea Link). Raw 15-minute/hourly readings were "
        "pulled from the RESTful API, written into Cassandra via Spark, aggregated to monthly "
        "totals via Spark, and the monthly aggregates stored in MongoDB - which is what this "
        "page reads from directly."
    )
