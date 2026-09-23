import matplotlib.pyplot as plt
import streamlit as st

from data_utils import load_data

st.title("Reservoir Data Plot")

national = load_data()
numeric_cols = national.select_dtypes(include="number").columns.tolist()

# Dropdown: pick one column, or all columns together
selected = st.selectbox("Choose a column to plot", options=["All columns"] + numeric_cols)

# Build a list of available months (as "YYYY-MM" strings) for the slider
months = sorted(national.index.to_period("M").astype(str).unique())

# Selection slider to pick a start and end month - default to just the
# first month, as required
start_month, end_month = st.select_slider(
    "Select a range of months",
    options=months,
    value=(months[0], months[0]),
)

month_period = national.index.to_period("M").astype(str)
mask = (month_period >= start_month) & (month_period <= end_month)
filtered = national.loc[mask]

fig, ax = plt.subplots(figsize=(10, 5))
if selected == "All columns":
    for col in numeric_cols:
        ax.plot(filtered.index, filtered[col], label=col)
else:
    ax.plot(filtered.index, filtered[selected], label=selected)

ax.set_title(f"Reservoir data ({start_month} to {end_month})")
ax.set_xlabel("Date")
ax.set_ylabel("Value")
ax.legend()
fig.autofmt_xdate()

st.pyplot(fig)
