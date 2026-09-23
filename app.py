import streamlit as st

st.set_page_config(page_title="IND320 - Reservoirs", page_icon="\U0001F4A7", layout="wide")

st.title("IND320 - Norwegian Reservoir Data")

st.markdown(
    """
Welcome! This app explores Norwegian hydropower reservoir data (NVE's
*magasinstatistikk*), filtered to the national total.

Use the sidebar on the left to navigate between pages:

- **Table** - the data shown as a table, with a small sparkline of the
  first month for each column
- **Plot** - an interactive plot of the reservoir data over time, with a
  column selector and a month-range slider
- **Extra** - placeholder page for future work
"""
)
