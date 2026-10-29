import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from pymongo.errors import PyMongoError

from modules.entsoe_utils import CONNECTION_LABELS, CONNECTIONS
from modules.mongo_utils import get_crossborder_collection

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

    # Default to the year with the most stored data rather than just the
    # highest year number - a stray or incomplete year (e.g. a leftover test
    # document) should never silently become the default view.
    try:
        year_counts = list(collection.aggregate([
            {"$match": {"connection": connection}},
            {"$group": {"_id": "$year", "count": {"$sum": 1}}},
        ]))
    except PyMongoError as e:
        st.error(f"Could not reach the MongoDB database: {e}")
        st.stop()

    years = sorted(doc["_id"] for doc in year_counts)
    if years:
        best_year = max(year_counts, key=lambda d: d["count"])["_id"]
        year = st.selectbox("Year", years, index=years.index(best_year))

        try:
            docs = list(collection.find({"connection": connection, "year": year}))
        except PyMongoError as e:
            st.error(f"Could not reach the MongoDB database: {e}")
            st.stop()

        if not docs:
            # Shouldn't normally happen (year was only offered because it had
            # documents above), but guard anyway rather than crash on an
            # empty DataFrame.
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
        try:
            docs = list(
                collection.find({"connection": connection, "year": year, "month": {"$in": selected_months}})
            )
        except PyMongoError as e:
            st.error(f"Could not reach the MongoDB database: {e}")
            st.stop()

        if not docs:
            # A connection/year can have gaps for a particular month (ENTSO-E
            # data isn't always complete), so an empty result here is a real
            # possibility, not just a bug - this used to crash with a
            # KeyError on an empty DataFrame instead of showing this message.
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
