"""River-based forecasting of a single region's weekly Magasinstatistikk
fill_degree, a few months ahead, with selectable exogenous data sources and
quantile-regression confidence bands.

Defaults (p=1, d=1, q=1, m=52, sd=1, sp=0, sq=0, history=104) are the
winning setting from the walk-forward sweep in the Part 4 notebook - by far
the biggest factor there was seasonal differencing (sd): turning it off
sent the mean MAE up roughly 6x, since fill_degree is so strongly seasonal
that SNARIMAX can't track it without explicitly differencing the annual
cycle out first.

Verified with a synthetic seasonal series before relying on it against the
real data: river.time_series.SNARIMAX's bare (non-pipeline) learn_one/
forecast API takes exogenous features directly as a dict (learn_one(y,
x=...), forecast(horizon, xs=...)), and plugging river.optim.losses.Quantile
into the regressor gives quantile forecasts - but each quantile is an
independently trained online model, so the three can "cross" (lower ending
up above upper at some horizon step). This is a known limitation of
pointwise quantile regression, not a bug - fixed here by sorting the three
forecasts at each step rather than trusting the model ordering.
"""

import pandas as pd
from river import linear_model, optim, preprocessing, time_series


def _make_quantile_model(alpha, p, d, q, m, sd, sp, sq, optimizer_lr):
    """One SNARIMAX instance targeting a single quantile (alpha=0.5 is the
    median) - StandardScaler keeps exogenous features on comparable scales
    for the linear regressor regardless of their original units.
    """
    regressor = preprocessing.StandardScaler() | linear_model.LinearRegression(
        optimizer=optim.SGD(optimizer_lr),
        loss=optim.losses.Quantile(alpha=alpha),
    )
    return time_series.SNARIMAX(p=p, d=d, q=q, m=m, sp=sp, sd=sd, sq=sq, regressor=regressor)


def forecast_fill_degree(
    y,
    horizon=12,
    history=104,
    exogenous=None,
    future_exogenous=None,
    p=1,
    d=1,
    q=1,
    m=52,
    sd=1,
    sp=0,
    sq=0,
    quantiles=(0.1, 0.5, 0.9),
    optimizer_lr=0.01,
):
    """Forecast `horizon` steps ahead for one region's weekly fill_degree
    series using River's SNARIMAX, with optional exogenous regressors and
    quantile confidence bands.

    y: pd.Series of weekly fill_degree, indexed by date, sorted ascending,
       for a single region (e.g. filter_area_type(data, "EL") narrowed to
       one area_number).
    history: use only the last `history` points of y for training (None =
       all of it) - lets the caller trade off training length vs. speed/
       relevance of older data, per the assignment's "length of history"
       input. Default 104 (2 years) is the walk-forward sweep's winner -
       see the Part 4 notebook's "Testing various settings" section.
    exogenous: optional dict[name -> pd.Series] of extra weekly-aligned
       regressors (e.g. a region's mean weekly temperature/precipitation,
       or EUR/USD rates resampled to weekly) - this is what lets the
       caller pick which data sources feed the model; pass None/{} for a
       plain univariate forecast.
    future_exogenous: optional dict with the SAME keys as `exogenous`,
       covering the `horizon` forecast dates (e.g. a weather forecast, or
       simply the last known value persisted forward) - if omitted, the
       model forecasts without exogenous input at all (xs=None), which
       SNARIMAX supports fine, it just can't react to e.g. assumed future
       weather.
    quantiles: the 3 quantiles to fit (lower, median, upper) - default is
       an 80% interval around the median.

    Returns a DataFrame indexed by forecast date with columns "lower",
    "median", "upper" (sorted per-step so lower <= median <= upper always
    holds, even though the 3 underlying models are trained independently
    and can otherwise disagree on order - see module docstring).
    """
    y = y.sort_index()
    if history is not None:
        y = y.iloc[-history:]

    exogenous = exogenous or {}
    future_exogenous = future_exogenous or {}

    # Build one x-dict per training timestamp, pulling the same date from
    # every exogenous series (missing/NaN exogenous values just become a
    # missing key for that step - SNARIMAX's regressor only needs the keys
    # that are actually present).
    def x_at(date, sources):
        return {name: series.loc[date] for name, series in sources.items() if date in series.index and pd.notna(series.loc[date])}

    models = {
        alpha: _make_quantile_model(alpha, p, d, q, m, sd, sp, sq, optimizer_lr)
        for alpha in quantiles
    }
    for model in models.values():
        for date, value in y.items():
            model.learn_one(value, x=x_at(date, exogenous))

    future_dates = pd.date_range(y.index[-1], periods=horizon + 1, freq="7D")[1:]
    xs = [x_at(date, future_exogenous) for date in future_dates] if future_exogenous else None

    forecasts = {alpha: models[alpha].forecast(horizon=horizon, xs=xs) for alpha in quantiles}
    sorted_alphas = sorted(quantiles)
    lower_a, median_a, upper_a = sorted_alphas[0], sorted_alphas[len(sorted_alphas) // 2], sorted_alphas[-1]

    # Sort the 3 forecasts at every step (see module docstring on crossing)
    # rather than just reading off lower_a/median_a/upper_a directly.
    per_step = list(zip(forecasts[lower_a], forecasts[median_a], forecasts[upper_a]))
    sorted_steps = [sorted(step) for step in per_step]

    return pd.DataFrame(
        sorted_steps, columns=["lower", "median", "upper"], index=future_dates
    )
