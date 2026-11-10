import matplotlib.pyplot as plt
import streamlit as st

from modules.analysis_utils import plot_fill_degree_spectrogram, plot_fill_degree_stl
from modules.app_utils import area_selector, get_fill_degree_series

st.title("Fill-Degree Decomposition")

# Shared sidebar area selector (modules/app_utils.py) - this page works for
# any area_type (EL/NO/VASS), unlike the weather pages below, since it only
# needs magasinstatistikk's own fill_degree series, not a weather download.
area_type, area_number = area_selector()
series = get_fill_degree_series(area_type, area_number)

if series.empty:
    st.warning(f"No fill-degree data for {area_type} area {area_number}.")
    st.stop()

label = f"{area_type}{area_number}" if area_type != "NO" else "national total"
st.caption(
    f"{len(series)} weekly readings for the **{label}** area, "
    f"{series.index.min():%Y-%m-%d} to {series.index.max():%Y-%m-%d}."
)

tab_stl, tab_spectrogram = st.tabs(["STL decomposition", "Spectrogram"])

with tab_stl:
    st.write(
        "Seasonal-Trend decomposition using LOESS (STL), splitting the series into "
        "trend, seasonal and residual components."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        seasonal = st.slider(
            "Seasonal smoother", min_value=7, max_value=105, value=53, step=2,
            help="LOESS window for the seasonal component (must be odd). "
                 "53 is just over one 52-week annual cycle.",
        )
    with col2:
        auto_trend = st.checkbox("Auto trend smoother", value=True)
        trend = None
        if not auto_trend:
            trend = st.slider(
                "Trend smoother", min_value=53, max_value=261, value=81, step=2,
                help="LOESS window for the trend component (must be odd and longer "
                     "than the seasonal window). Left on auto, statsmodels picks a "
                     "sensible value from the seasonal window and period itself.",
            )
    with col3:
        robust = st.checkbox(
            "Robust", value=False,
            help="Down-weight unusually large residuals so a handful of outlier "
                 "weeks don't distort the trend/seasonal estimates.",
        )

    axes, result = plot_fill_degree_stl(series, seasonal=seasonal, trend=trend, robust=robust)
    fig = axes[0].figure
    fig.suptitle(f"STL decomposition - {label}")
    st.pyplot(fig)
    plt.close(fig)

with tab_spectrogram:
    st.write(
        "Spectrogram of the same fill-degree series, showing how its frequency "
        "content (e.g. the strength of the annual cycle) changes over time."
    )

    col1, col2 = st.columns(2)
    with col1:
        window_length = st.slider(
            "Window length (weeks)", min_value=26, max_value=260, value=104, step=26,
            help="Length of each STFT segment. 104 (2 years) comfortably contains "
                 "the ~52-week annual cycle while still leaving several segments "
                 "across a multi-year series.",
        )
    with col2:
        window_overlap = st.slider(
            "Window overlap (weeks)", min_value=0, max_value=window_length - 1,
            value=min(52, window_length - 1), step=13,
            help="How much consecutive segments overlap. Half the window length "
                 "is the usual STFT convention.",
        )

    ax, (freqs, times, Sxx) = plot_fill_degree_spectrogram(
        series, window_length=window_length, window_overlap=window_overlap
    )
    ax.set_title(f"Spectrogram - {label}")
    st.pyplot(ax.figure)
    plt.close(ax.figure)
