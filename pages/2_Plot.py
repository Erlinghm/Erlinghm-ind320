import matplotlib.pyplot as plt
import streamlit as st

from modules.data_utils import load_data, filter_area_type

st.title("Reservoir Data Plot")

data = load_data()

# Same area-type radio as the Table page - this decides how many lines end
# up on the plot (one per area number within the chosen type).
area_type = st.radio("Area type", options=["EL", "NO", "VASS"], index=1)
areas = filter_area_type(data, area_type)

numeric_cols = ["fill_degree", "capacity_twh", "filling_twh",
                 "fill_degree_prev_week", "fill_degree_change"]
selected_col = st.selectbox("Choose a column to plot", options=numeric_cols)

# Build a list of available months (as "YYYY-MM" strings) for the slider.
# This slider is the "download interval" control - see the note in
# data_utils.load_data() about why it can only narrow the already-cached
# data rather than changing what is requested from NVE.
months = sorted(areas.index.to_period("M").astype(str).unique())

start_month, end_month = st.select_slider(
    "Select a range of months (controls which data is used)",
    options=months,
    value=(months[0], months[0]),
)

month_period = areas.index.to_period("M").astype(str)
mask = (month_period >= start_month) & (month_period <= end_month)
filtered = areas.loc[mask]

# Plot one line per area number within the selected area type
fig, ax = plt.subplots(figsize=(10, 5))
for area_number in sorted(filtered["area_number"].unique()):
    series = filtered[filtered["area_number"] == area_number]
    ax.plot(series.index, series[selected_col], label=f"{area_type} {area_number}")

ax.set_title(f"{selected_col} by {area_type} area ({start_month} to {end_month})")
ax.set_xlabel("Date")
ax.set_ylabel(selected_col)
ax.legend()
fig.autofmt_xdate()

st.pyplot(fig)
