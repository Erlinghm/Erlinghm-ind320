"""Outlier/anomaly detection, decomposition, spectral and correlation
analysis for the Part 3/4 weather and reservoir time series: a DCT-based
Statistical Process Control check for precipitation, a Local Outlier Factor
check for temperature, an STL decomposition of reservoir fill degree, a
spectrogram of the same fill-degree series, and a sliding-window
lagged-correlation function (Part 4) between any two aligned series.
"""

import numpy as np
import pandas as pd
from scipy.fft import dct, idct
from sklearn.neighbors import LocalOutlierFactor
from scipy.signal import spectrogram
from statsmodels.tsa.seasonal import STL


def _robust_center_scale(values):
    """Median and a normal-consistent scaling of the median absolute
    deviation - robust (outlier-resistant) stand-ins for the mean and
    standard deviation, used so a handful of real outliers don't drag the
    control limits out wide enough to hide themselves.
    """
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    return median, mad * 1.4826


def _seasonal_trend(values, freq_cutoff):
    """Low-pass reconstruction of `values` keeping only the first
    `freq_cutoff` Discrete Cosine Transform coefficients (the slowest-
    varying components) - the smooth seasonal/trend curve that the
    higher-frequency day-to-day variation sits on top of.
    """
    coeffs = dct(values, norm="ortho")
    low_coeffs = np.zeros_like(coeffs)
    low_coeffs[:freq_cutoff] = coeffs[:freq_cutoff]
    return idct(low_coeffs, norm="ortho")


def spc_outliers(series, freq_cutoff=10, n_std=3):
    """Data-only version of plot_precipitation_outliers()'s SPC logic -
    works on ANY univariate series, not just precipitation (used by the
    Weather Outliers page's weather-property selector). Returns (values,
    is_outlier, lower_curve, upper_curve, summary), where summary is a
    DataFrame of the flagged outliers (timestamp, value, satv).
    """
    values = series.to_numpy(dtype=float)
    seasonal = _seasonal_trend(values, freq_cutoff)
    satv = values - seasonal

    center, scale = _robust_center_scale(satv)
    lower_satv, upper_satv = center - n_std * scale, center + n_std * scale
    is_outlier = (satv < lower_satv) | (satv > upper_satv)
    lower_curve, upper_curve = seasonal + lower_satv, seasonal + upper_satv

    index = np.asarray(series.index)
    summary = pd.DataFrame({
        "timestamp": index[is_outlier],
        "value": values[is_outlier],
        "satv": satv[is_outlier],
    })
    return values, is_outlier, lower_curve, upper_curve, summary


def plot_precipitation_outliers(series, freq_cutoff=10, n_std=3, ax=None):
    """Plot a precipitation time series with Statistical Process Control
    boundaries, colouring points outside them as outliers.

    A DCT high-pass filter splits `series` into a smooth seasonal trend
    (the lowest `freq_cutoff` DCT coefficients) and a high-frequency
    residual - the Seasonally Adjusted Temporal Variation (SATV), which is
    the assignment's own term for it. Robust stats (median + a
    normal-consistent MAD) over the SATV give constant control limits in
    residual space; adding the trend back turns that into a boundary curve
    in the original units, which is what's actually plotted - the SATV
    values themselves only get used to find the boundaries and flag
    outliers, never plotted directly (the assignment says so explicitly:
    "Do not plot SATV values; only use them to find boundaries and
    outliers").

    Returns (ax, summary) where summary is a DataFrame of the flagged
    outliers (timestamp, value, satv).
    """
    import matplotlib.pyplot as plt

    values, is_outlier, lower_curve, upper_curve, summary = spc_outliers(series, freq_cutoff=freq_cutoff, n_std=n_std)

    ax = ax or plt.gca()
    index = np.asarray(series.index)
    ax.plot(index, values, color="tab:blue", linewidth=0.8, label="precipitation")
    ax.plot(index, upper_curve, color="gray", linestyle="--", linewidth=0.8, label="SPC bounds")
    ax.plot(index, lower_curve, color="gray", linestyle="--", linewidth=0.8)
    ax.scatter(index[is_outlier], values[is_outlier], color="tab:red", s=10, zorder=3, label="outliers")
    ax.set_xlabel("Time")
    ax.set_ylabel("Precipitation")
    ax.legend()

    return ax, summary


def lof_anomalies(series, freq_cutoff=10, contamination=0.01, n_neighbors=20):
    """Data-only version of plot_temperature_anomalies()'s LOF logic -
    works on ANY univariate series, not just temperature (used by the
    Weather Outliers page's weather-property selector). Returns (values,
    is_outlier, summary), where summary is a DataFrame of the flagged
    anomalies (timestamp, value, lof_score), most anomalous first.
    """
    values = series.to_numpy(dtype=float)
    seasonal = _seasonal_trend(values, freq_cutoff)
    residual = values - seasonal

    lof = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
    labels = lof.fit_predict(residual.reshape(-1, 1))
    is_outlier = labels == -1
    scores = -lof.negative_outlier_factor_

    index = np.asarray(series.index)
    summary = pd.DataFrame({
        "timestamp": index[is_outlier],
        "value": values[is_outlier],
        "lof_score": scores[is_outlier],
    }).sort_values("lof_score", ascending=False)
    return values, is_outlier, summary


def plot_temperature_anomalies(series, freq_cutoff=10, contamination=0.01, n_neighbors=20, ax=None):
    """Plot a temperature time series, colouring points flagged as
    anomalies by Local Outlier Factor in a contrasting colour.

    LOF runs on the deseasonalised residual (same DCT low-pass trend as in
    plot_precipitation_outliers, subtracted out), not the raw values.
    Otherwise LOF - which only looks at how isolated a value is among
    other values, not when it happened - misses anomalies that are
    unusual for their SEASON but not extreme for the whole year (an
    unseasonably warm winter day that's still cooler than an ordinary
    summer day, say). Hit this in testing: a raw-value LOF missed exactly
    that case, the deseasonalised version caught it.

    Returns (ax, summary) where summary is a DataFrame of the flagged
    anomalies (timestamp, value, lof_score), most anomalous first.
    """
    import matplotlib.pyplot as plt

    values, is_outlier, summary = lof_anomalies(
        series, freq_cutoff=freq_cutoff, contamination=contamination, n_neighbors=n_neighbors
    )

    ax = ax or plt.gca()
    index = np.asarray(series.index)
    ax.plot(index, values, color="tab:blue", linewidth=0.8, label="temperature")
    ax.scatter(index[is_outlier], values[is_outlier], color="tab:red", s=10, zorder=3, label="anomalies")
    ax.set_xlabel("Time")
    ax.set_ylabel("Temperature")
    ax.legend()

    return ax, summary


def fill_degree_stl(series, period=52, seasonal=53, trend=None, robust=False):
    """Data-only version of plot_fill_degree_stl() - same preprocessing
    (linear interpolation of any gaps) and STL call, but returns the
    statsmodels DecomposeResult without plotting, for callers (e.g. the
    Plotly-based Streamlit page) that build their own figure.
    """
    values = series.astype(float)
    if values.isna().any():
        values = values.interpolate(limit_direction="both")
    return STL(values, period=period, seasonal=seasonal, trend=trend, robust=robust).fit()


def plot_fill_degree_stl(series, period=52, seasonal=53, trend=None, robust=False, axes=None,
                          title="STL decomposition of reservoir fill degree"):
    """STL (Seasonal-Trend decomposition using LOESS) of a reservoir
    fill-degree series, plotted as its four components.

    - `seasonal`/`trend` are the LOESS window lengths (in observations)
      for the seasonal/trend components. `seasonal=53` is just over one
      52-week annual cycle - long enough that the extracted seasonal shape
      stays stable year to year instead of chasing noise. `trend=None`
      lets statsmodels pick its own default from `period`/`seasonal`,
      which is already sensible (long enough not to reabsorb the seasonal
      pattern, short enough to still track real multi-year drift).
    - `robust` (default False) switches to STL's robust variant, which
      down-weights unusually large residuals so a few outlier weeks don't
      distort the trend/seasonal estimates.
    - `period=52` is one seasonal cycle in observations - fixed by this
      being weekly data with an annual cycle rather than something to
      tune, but STL still needs it passed in.

    Any gaps in `series` get linearly interpolated first, since STL needs
    a complete, evenly-spaced series.

    Returns (axes, result) where result is the statsmodels DecomposeResult
    (observed/trend/seasonal/resid, aligned with `series.index`).
    """
    import matplotlib.pyplot as plt

    result = fill_degree_stl(series, period=period, seasonal=seasonal, trend=trend, robust=robust)

    if axes is None:
        _, axes = plt.subplots(4, 1, figsize=(10, 8), sharex=True)
    components = [result.observed, result.trend, result.seasonal, result.resid]
    labels = ["fill degree", "trend", "seasonal", "residual"]
    for ax, component, label in zip(axes, components, labels):
        ax.plot(series.index, component, linewidth=0.8)
        ax.set_ylabel(label)
    axes[-1].set_xlabel("Time")
    axes[0].set_title(title)
    plt.tight_layout()

    return axes, result


def fill_degree_spectrogram(series, window_length=104, window_overlap=52):
    """Data-only version of plot_fill_degree_spectrogram() - same
    preprocessing (linear interpolation of any gaps) and STFT call, but
    returns (frequencies_per_year, times, Sxx) without plotting, for
    callers that build their own figure (e.g. the Plotly-based page).
    """
    values = series.astype(float)
    if values.isna().any():
        values = values.interpolate(limit_direction="both")
    values = values.to_numpy()

    nperseg = min(window_length, len(values))
    noverlap = min(window_overlap, nperseg - 1)
    freqs, times, Sxx = spectrogram(values, fs=1.0, nperseg=nperseg, noverlap=noverlap)
    return freqs * 52, times, Sxx


def plot_fill_degree_spectrogram(series, window_length=104, window_overlap=52, ax=None):
    """Spectrogram of a reservoir fill-degree series - same data as
    `plot_fill_degree_stl` decomposes - showing how its frequency content
    changes over time, instead of STL's one fixed seasonal shape.

    - `window_length` is each STFT segment's length in observations - 104
      (2 years of weekly data) by default, long enough to contain a
      couple of repeats of the ~52-week annual cycle so it actually shows
      up as a frequency band, while still leaving several segments across
      a multi-year series.
    - `window_overlap` is how much consecutive segments overlap - half of
      `window_length` by default, the usual STFT convention.
    - both have sensible defaults, as the assignment asks for.

    The series is one sample per week, so scipy's raw frequency axis comes
    out in cycles/week - rescaled to cycles/year here (x52) since that's
    the more natural unit for an annual cycle. Gaps get linearly
    interpolated first, since STFT needs a complete, evenly-spaced series.

    Returns (ax, result) where result is (frequencies_per_year, times,
    Sxx), frequencies already rescaled.
    """
    import matplotlib.pyplot as plt

    freqs_per_year, times, Sxx = fill_degree_spectrogram(series, window_length=window_length, window_overlap=window_overlap)

    ax = ax or plt.gca()
    mesh = ax.pcolormesh(times, freqs_per_year, 10 * np.log10(Sxx + 1e-12), shading="gouraud")
    ax.set_xlabel("Time (weeks since start)")
    ax.set_ylabel("Frequency (cycles/year)")
    plt.colorbar(mesh, ax=ax, label="Power (dB)")

    return ax, (freqs_per_year, times, Sxx)


def sliding_window_correlation(series_a, series_b, window, lag=0):
    """Rolling Pearson correlation between series_a and series_b, with
    series_b shifted by `lag` steps first (a positive lag compares
    series_a's current value against series_b's value `lag` steps in the
    past - e.g. "does this week's fill degree correlate with temperature
    from 3 weeks ago", i.e. does weather lead reservoir filling by 3
    weeks).

    Tried this on a synthetic series built the other way around
    (fill_degree = weather.shift(3) + noise) to check it actually works:
    the rolling correlation peaks at lag=+3, as expected. The two series
    get aligned on their shared index first (inner join), so they don't
    need to already share an identical index/length - just a compatible
    one (e.g. both resampled to weekly before calling this).

    Returns a Series (indexed like the aligned/lagged input) of rolling
    correlation over a window of `window` points - like any rolling stat,
    the first `window - 1` points are NaN.
    """
    aligned_a, aligned_b = series_a.align(series_b.shift(lag), join="inner")
    return aligned_a.rolling(window).corr(aligned_b)
