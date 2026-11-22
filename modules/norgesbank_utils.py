"""Helpers for downloading currency exchange rates from Norges Bank's (the
Norwegian central bank) open data API.

Verified against a real response on 2026-11-20 (EUR+USD vs NOK, Jan 2024):
Norges Bank's SDMX-JSON uses the series key "<FREQ idx>:<BASE_CUR idx>:
<QUOTE_CUR idx>:<TENOR idx>", with the index order given by
data.structure.dimensions.series (not fixed - read it rather than assume a
position), and observations keyed by a time INDEX (not the date itself),
with the actual dates in data.structure.dimensions.observation[0].values.
The "+" syntax (B.EUR+USD.NOK.SP) fetches several base currencies in one
request. See the timezone investigation in the Part 4 notebook for a note
on the "ECB concertation time 14:15 CET" collection attribute this response
also carries - the quoted date itself has no time-of-day component.
"""

import pandas as pd
import requests

BASE_URL = "https://data.norges-bank.no/api/data/EXR"


def fetch_exchange_rates(currencies=("EUR", "USD"), start_date="2024-01-01", end_date="2024-12-31", quote_currency="NOK"):
    """Business-daily exchange rates for one or more base currencies against
    quote_currency (NOK by default), as a tidy DataFrame with columns
    date/currency/rate - one row per currency per business day.

    Dates are plain calendar dates (no time-of-day, no timezone) - Norges
    Bank publishes one rate per business day, fixed daily via the ECB
    concertation procedure (see module docstring), so there's no hour to
    place a timezone on in the first place.
    """
    series_key = f"B.{'+'.join(currencies)}.{quote_currency}.SP"
    response = requests.get(
        f"{BASE_URL}/{series_key}",
        params={"format": "sdmx-json", "startPeriod": start_date, "endPeriod": end_date, "locale": "en"},
        timeout=30,
    )
    response.raise_for_status()
    return _parse_exchange_rate_response(response.json())


def _parse_exchange_rate_response(payload):
    """Pulled out of fetch_exchange_rates() so the parsing logic can be
    tested against a saved sample response without a network call.
    """
    payload = payload["data"]

    # The observation dates are a separate lookup table, shared by every
    # series in the response - indexed by position, not by date.
    dates = [v["id"] for v in payload["structure"]["dimensions"]["observation"][0]["values"]]

    # Map each series dimension's position in the ":"-joined series key to
    # its list of value ids (e.g. BASE_CUR -> ["USD", "EUR"]) - read from the
    # response rather than assumed, since Norges Bank doesn't document a
    # fixed dimension order for the key.
    series_dims = payload["structure"]["dimensions"]["series"]
    base_cur_dim_index = next(i for i, d in enumerate(series_dims) if d["id"] == "BASE_CUR")

    rows = []
    for series_key_str, series in payload["dataSets"][0]["series"].items():
        dim_indices = [int(i) for i in series_key_str.split(":")]
        currency = series_dims[base_cur_dim_index]["values"][dim_indices[base_cur_dim_index]]["id"]
        for time_index, obs in series["observations"].items():
            rows.append({"date": dates[int(time_index)], "currency": currency, "rate": float(obs[0])})

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["currency", "date"]).reset_index(drop=True)
