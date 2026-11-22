import datetime as dt

import plotly.graph_objects as go
import streamlit as st

from modules.norgesbank_utils import fetch_exchange_rates
from modules.theme import CATEGORICAL

st.title("Currency Rates")
st.caption(
    "Business-daily EUR and USD exchange rates against NOK, downloaded live from "
    "Norges Bank's open data API - see the Part 4 notebook for the timezone/date "
    "notes on this source."
)

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start date", value=dt.date.today() - dt.timedelta(days=365))
with col2:
    end_date = st.date_input("End date", value=dt.date.today())

if start_date >= end_date:
    st.error("Start date must be before end date.")
    st.stop()


@st.cache_data(ttl=3600)
def _cached_rates(start, end):
    return fetch_exchange_rates(currencies=["EUR", "USD"], start_date=str(start), end_date=str(end))


try:
    rates = _cached_rates(start_date, end_date)
except Exception as e:
    st.error(f"Couldn't reach Norges Bank's API: {e}")
    st.stop()

if rates.empty:
    st.warning("No rates for that range - check the dates (weekends/holidays have no business-daily rate).")
    st.stop()

fig = go.Figure()
for i, currency in enumerate(sorted(rates["currency"].unique())):
    series = rates[rates["currency"] == currency]
    fig.add_trace(go.Scatter(
        x=series["date"], y=series["rate"], mode="lines", name=currency,
        line=dict(color=CATEGORICAL[i % len(CATEGORICAL)]),
    ))
fig.update_layout(
    title=f"NOK per unit of foreign currency ({start_date} to {end_date})",
    xaxis_title="Date", yaxis_title="NOK", hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)

st.dataframe(rates, hide_index=True)
