import pandas as pd
import streamlit as st

from data_utils import load_data

st.title("Data Table")

national = load_data()

# Only use the numeric measurement columns
numeric_cols = national.select_dtypes(include="number").columns.tolist()

# Use just the first calendar month of data
first_month_end = national.index.min() + pd.DateOffset(months=1)
first_month = national.loc[national.index < first_month_end, numeric_cols]

# Display the full national data
st.write("Full data:")
st.dataframe(national)

st.write("One row per column, with a sparkline of its first month:")

# Build a small table, dispalying the first month of each column as a sparkline.
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
