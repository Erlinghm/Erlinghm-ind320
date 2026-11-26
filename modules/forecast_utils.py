"""River-based forecasting of one region's weekly Magasinstatistikk
fill_degree a few months ahead, with selectable exogenous data sources and
quantile-regression confidence bands.

Defaults (p=1, d=1, q=1, m=52, sd=1, sp=0, sq=0, history=104) come from the
walk-forward sweep in the Part 4 notebook - by far the biggest factor there
was seasonal differencing (sd): turning it off multiplied the mean MAE by
about 6x, since fill_degree is seasonal enough that SNARIMAX can't track it
without differencing out the annual cycle first.

Tried this on a synthetic seasonal series before trusting it on the real
data: River's SNARIMAX (the plain, non-pipeline version) takes exogenous
features as a dict (learn_one(y, x=...), forecast(horizon, xs=...)), and
plugging river.optim.losses.Quantile into the regressor gives quantile
forecasts. One catch: each quantile is trained as a completely separate
online model, so they can "cross" (the lower bound ends up above the upper
one at some step) - not a bug, just a known issue with doing quantile
regression this way, fixed below by sorting the three forecasts at each
step instead of trusting which model is which.
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

    y: weekly fill_degree for a single region, indexed by date, sorted
       ascending (e.g. filter_area_type(data, "EL") narrowed to one
       area_number).
    history: only train on the last `history` points of y (None = use all
       of it) - lets the caller trade training length off against speed
       and how relevant the older data still is, which is the "length of
       history" input the assignment asks for. 104 (2 years) is the
       walk-forward sweep's winner - see the notebook's "Testing various
       settings" section.
    exogenous: optional dict[name -> pd.Series] of extra weekly-aligned
       regressors (e.g. a region's mean weekly temperature, or EUR/USD
       resampled to weekly) - this is what lets the caller choose which
       data sources feed the model. Pass None/{} for a plain univariate
       forecast.
    future_exogenous: same keys as `exogenous`, but covering the `horizon`
       forecast dates (e.g. a weather forecast, or just the last known
       value carried forward). Left out, the model forecasts without any
       exogenous input (xs=None) - that's fine, it just can't react to
       assumed future weather/rates.
    quantiles: the 3 quantiles to fit (lower, median, upper) - defaults to
       an 80% interval around the median.

    Returns a DataFrame indexed by forecast date with "lower"/"median"/
    "upper" columns, sorted per step so lower <= median <= upper always
    holds (see the module docstring for why that's not automatic).
    """
    y = y.sort_index()
    if history is not None:
        y = y.iloc[-history:]

    exogenous = exogenous or {}
    future_exogenous = future_exogenous or {}

    # One x-dict per training timestamp, pulling that date from every
    # exogenous series - a missing/NaN value just means that key is left
    # out for that step, which SNARIMAX's regressor is fine with.
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
