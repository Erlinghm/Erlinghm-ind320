import pandas as pd
import streamlit as st

from data_utils import load_data

st.title("Data Table")

national = load_data()

# Only use the numeric measurement columns - text/date columns (area_type,
# next_publish_date) don't make sense as line-chart sparklines
numeric_cols = national.select_dtypes(include="number").columns.tolist()

# Grab just the first calendar month of data, since that's what the
# assignment asks the sparkline to show
first_month_end = national.index.min() + pd.DateOffset(months=1)
first_month = national.loc[national.index < first_month_end, numeric_cols]

st.write("Full data:")
st.dataframe(national)

st.write("One row per column, with a sparkline of its first month:")

# Build a small table: one row per original column, with a list of that
# column's first-month values in a second column (for the sparkline)
table_data = pd.DataFrame({
    "column": numeric_cols,
    "first_month_trend": [first_month[col].tolist() for col in numeric_cols],
})

st.dataframe(
    table_data,
    column_config={
        "column": st.column_config.TextColumn("Column"),
        "first_month_trend": st.column_config.LineChartColumn(
            "First month trend",
            width="medium",
        ),
    },
    hide_index=True,
)
