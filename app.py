import streamlit as st

st.set_page_config(page_title="IND320 - Norwegian Reservoirs", layout="wide")

st.title("IND320 - Norwegian Reservoir Data")

st.markdown(
    """
This project explores Norwegian water reservoir data, filtered to the national total.

The sidebar on the left contains following pages:

- **Table** - the data shown as a table, with a small sparkline of the
  first month for each column
- **Plot** - an interactive plot of the reservoir data over time, with a
  column selector and a month-range slider
- **Cross-border** - Norway's physical electricity exchange with its four
  directly connected neighbours (Denmark, Netherlands, Germany, Great
  Britain) over the last two years, shown as a yearly export/import pie
  chart and a daily line plot, built on ENTSO-E data via Cassandra, Spark
  and MongoDB
- **Extra** - placeholder page for future work
"""
)
