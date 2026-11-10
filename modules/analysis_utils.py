"""Outlier/anomaly detection, decomposition and spectral analysis for the
Part 3 weather and reservoir time series: a DCT-based Statistical Process
Control check for precipitation, a Local Outlier Factor check for
temperature, an STL decomposition of reservoir fill degree, and a
spectrogram of the same fill-degree series.
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


def plot_precipitation_outliers(series, freq_cutoff=10, n_std=3, ax=None):
    """Plot a precipitation time series with Statistical Process Control
    boundaries, colouring points outside them as outliers.

    A DCT high-pass filter splits `series` into a smooth seasonal trend
    (the lowest `freq_cutoff` DCT coefficients) and a high-frequency
    residual - the Seasonally Adjusted Temporal Variation (SATV), per the
    assignment's own naming. Robust statistics (median and a
    normal-consistent MAD) computed over the SATV give constant control
    limits in residual space; adding the seasonal trend back turns that
    into a boundary CURVE in the original units, which is what actually
    gets plotted - the SATV values themselves are only used to find the
    boundaries and classify outliers, never plotted directly, per the
    assignment ("Do not plot SATV values; only use them to find
    boundaries and outliers").

    Returns (ax, summary) where summary is a DataFrame of the flagged
    outliers (timestamp, value, satv).
    """
    import matplotlib.pyplot as plt

    values = series.to_numpy(dtype=float)
    seasonal = _seasonal_trend(values, freq_cutoff)
    satv = values - seasonal

    center, scale = _robust_center_scale(satv)
    lower_satv, upper_satv = center - n_std * scale, center + n_std * scale
    is_outlier = (satv < lower_satv) | (satv > upper_satv)
    lower_curve, upper_curve = seasonal + lower_satv, seasonal + upper_satv

    ax = ax or plt.gca()
    index = np.asarray(series.index)
    ax.plot(index, values, color="tab:blue", linewidth=0.8, label="precipitation")
    ax.plot(index, upper_curve, color="gray", linestyle="--", linewidth=0.8, label="SPC bounds")
    ax.plot(index, lower_curve, color="gray", linestyle="--", linewidth=0.8)
    ax.scatter(index[is_outlier], values[is_outlier], color="tab:red", s=10, zorder=3, label="outliers")
    ax.set_xlabel("Time")
    ax.set_ylabel("Precipitation")
    ax.legend()

    summary = pd.DataFrame({
        "timestamp": index[is_outlier],
        "value": values[is_outlier],
        "satv": satv[is_outlier],
    })
    return ax, summary


def plot_temperature_anomalies(series, freq_cutoff=10, contamination=0.01, n_neighbors=20, ax=None):
    """Plot a temperature time series, colouring points flagged as
    anomalies by Local Outlier Factor in a contrasting colour.

    LOF runs on the DESEASONALISED residual (the same DCT low-pass trend
    used in plot_precipitation_outliers, subtracted out), not the raw
    values. Otherwise LOF - which only looks at how isolated a value is
    among other values, not when it occurred - systematically misses
    anomalies that are unusual for their SEASON but not extreme relative
    to the whole year (e.g. an unseasonably warm winter day that's still
    cooler than an ordinary summer day): tested explicitly in this
    project's test suite, where a raw-value LOF missed exactly this case
    and the deseasonalised version caught it.

    Returns (ax, summary) where summary is a DataFrame of the flagged
    anomalies (timestamp, value, lof_score), most anomalous first.
    """
    import matplotlib.pyplot as plt

    values = series.to_numpy(dtype=float)
    seasonal = _seasonal_trend(values, freq_cutoff)
    residual = values - seasonal

    lof = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination)
    labels = lof.fit_predict(residual.reshape(-1, 1))
    is_outlier = labels == -1
    scores = -lof.negative_outlier_factor_

    ax = ax or plt.gca()
    index = np.asarray(series.index)
    ax.plot(index, values, color="tab:blue", linewidth=0.8, label="temperature")
    ax.scatter(index[is_outlier], values[is_outlier], color="tab:red", s=10, zorder=3, label="anomalies")
    ax.set_xlabel("Time")
    ax.set_ylabel("Temperature")
    ax.legend()

    summary = pd.DataFrame({
        "timestamp": index[is_outlier],
        "value": values[is_outlier],
        "lof_score": scores[is_outlier],
    }).sort_values("lof_score", ascending=False)
    return ax, summary


def plot_fill_degree_stl(series, period=52, seasonal=53, trend=None, robust=False, axes=None):
    """STL (Seasonal-Trend decomposition using LOESS) of a reservoir
    fill-degree series, plotted as its four components.

    - `seasonal` and `trend` are the LOESS smoothing-window lengths (in
      observations) behind the seasonal and trend components respectively -
      parameters with sensible defaults: `seasonal=53` is just over one full
      52-week annual cycle, long enough that the extracted seasonal shape is
      smooth and stable from year to year rather than chasing noise;
      `trend=None` lets statsmodels fall back to its own formula-based
      default (a function of `period` and `seasonal`), which is itself
      guaranteed sensible - long enough to not quietly re-absorb the
      seasonal pattern, short enough to still track real multi-year drift.
    - `robust` (bool, default False) switches STL to its robust variant,
      which down-weights unusually large residuals so a handful of outlier
      weeks don't distort the trend/seasonal estimates.
    - `period=52` is the length of one seasonal cycle in observations -
      fixed by this being weekly data with an annual cycle, not one of the
      assignment's own tunable parameters, but STL needs it regardless.

    Any gaps in `series` are linearly interpolated first, since STL
    requires a complete, evenly-spaced series.

    Returns (axes, result) where result is the statsmodels DecomposeResult
    (observed/trend/seasonal/resid, each aligned with `series.index`).
    """
    import matplotlib.pyplot as plt

    values = series.astype(float)
    if values.isna().any():
        values = values.interpolate(limit_direction="both")

    result = STL(values, period=period, seasonal=seasonal, trend=trend, robust=robust).fit()

    if axes is None:
        _, axes = plt.subplots(4, 1, figsize=(10, 8), sharex=True)
    components = [result.observed, result.trend, result.seasonal, result.resid]
    labels = ["fill degree", "trend", "seasonal", "residual"]
    for ax, component, label in zip(axes, components, labels):
        ax.plot(series.index, component, linewidth=0.8)
        ax.set_ylabel(label)
    axes[-1].set_xlabel("Time")
    axes[0].set_title("STL decomposition of reservoir fill degree")
    plt.tight_layout()

    return axes, result


def plot_fill_degree_spectrogram(series, window_length=104, window_overlap=52, ax=None):
    """Spectrogram of a reservoir fill-degree series - the same data
    `plot_fill_degree_stl` decomposes - showing how its frequency content
    changes over time, rather than STL's single year-round seasonal shape.

    - `window_length` (observations) is the length of each STFT segment -
      104 (2 years of weekly data) by default, long enough to contain a
      couple of repeats of the ~52-week annual cycle (so that cycle shows
      up as a clear frequency band at all) while still leaving several
      segments across a multi-year series to show change over time.
    - `window_overlap` (observations) is how much consecutive segments
      overlap - half of `window_length` by default, the usual STFT
      convention, which smooths the time axis out at the cost of some
      redundant computation.
    - both are parameters with sensible defaults, per the assignment.

    The series is one sample per week (fs=1 "per week"), so the raw
    frequency axis from scipy is in cycles/week; it's rescaled to
    cycles/year (x52) here since that's the natural unit for describing
    an annual cycle. Any gaps are linearly interpolated first, since the
    STFT needs a complete, evenly-spaced series.

    Returns (ax, result) where result is (frequencies_per_year, times,
    Sxx) as from scipy.signal.spectrogram, frequencies already rescaled.
    """
    import matplotlib.pyplot as plt

    values = series.astype(float)
    if values.isna().any():
        values = values.interpolate(limit_direction="both")
    values = values.to_numpy()

    nperseg = min(window_length, len(values))
    noverlap = min(window_overlap, nperseg - 1)
    freqs, times, Sxx = spectrogram(values, fs=1.0, nperseg=nperseg, noverlap=noverlap)
    freqs_per_year = freqs * 52

    ax = ax or plt.gca()
    mesh = ax.pcolormesh(times, freqs_per_year, 10 * np.log10(Sxx + 1e-12), shading="gouraud")
    ax.set_xlabel("Time (weeks since start)")
    ax.set_ylabel("Frequency (cycles/year)")
    plt.colorbar(mesh, ax=ax, label="Power (dB)")

    return ax, (freqs_per_year, times, Sxx)
