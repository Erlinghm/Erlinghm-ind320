"""Helpers for sampling random weather-query locations from a region shapefile,
and downloading historical weather for those locations from open-meteo.
"""

import hashlib
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely

# Where successfully-downloaded chunks are cached (see fetch_weather_for_region).
# Lives under the project root regardless of the notebook's own working
# directory, since this module is always at <project root>/modules/.
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "weather"


def sample_points_per_region(shapefile_path, region_col, n_points=1000, seed=None):
    """Returns a DataFrame with n_points random (lat, lon) locations inside
    each region's polygon, reprojected to WGS84 regardless of the
    shapefile's own CRS (both of mine are EPSG:25833, UTM zone 33N).

    Rejection sampling: draw random points inside each region's bounding
    box, keep the ones that land inside the actual polygon, and top up
    with another batch if not enough landed inside. Simpler than sampling
    the polygon directly, and fine at this scale.
    """
    gdf = gpd.read_file(shapefile_path, encoding="utf-8").to_crs(epsg=4326)
    rng = np.random.default_rng(seed)

    rows = []
    for _, region in gdf.iterrows():
        polygon = region.geometry
        min_x, min_y, max_x, max_y = polygon.bounds

        accepted = []
        while len(accepted) < n_points:
            # Oversample each round since only the points inside the polygon
            # (not just its bounding box) are kept.
            batch_size = (n_points - len(accepted)) * 2
            xs = rng.uniform(min_x, max_x, batch_size)
            ys = rng.uniform(min_y, max_y, batch_size)
            points = gpd.points_from_xy(xs, ys)
            inside = points[shapely.contains(polygon, points)]
            accepted.extend(inside[: n_points - len(accepted)])

        for point in accepted:
            rows.append({"region": region[region_col], "lat": point.y, "lon": point.x})

    return pd.DataFrame(rows)


# NVE_Region.shp has 5 regions: RS, RØ, RV, RM, RN. magasinstatistikk's VASS
# area type reports 3 combined zones instead - checked this against NVE's
# own region descriptions (biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/
# HentOmråder): omrnr 1 is "Sørøst-Norge...Østlandet, Agder og deler av
# Rogaland" (= RS+RØ), omrnr 2 is "Vest-Norge" (= RV alone), omrnr 3 is
# "Midt-Norge...og sørlige Nordland" (= RM+RN). Named East/West/North per
# the teacher's feedback. (NVE's endpoint also lists a 4th VASS region,
# "Nord-Norge", but it never actually has data in the historical feed, so
# it's left out here rather than guessed at.)
VASS_REGION_GROUPS = {
    1: ("East", ["RS", "RØ"]),
    2: ("West", ["RV"]),
    3: ("North", ["RM", "RN"]),
}


def sample_points_per_vass_zone(shapefile_path, region_col="REGION", n_points=1000, seed=None):
    """Like sample_points_per_region, but for the 3 combined VASS zones
    instead of the 5 raw shapefile regions: samples n_points per raw
    region, then relabels each point from its raw code (RS, RØ, RV, RM, RN)
    to its VASS zone ("VASS1"/"VASS2"/"VASS3", matching magasinstatistikk's
    own numbering so the rest of the pipeline doesn't need to know about
    the grouping at all). East and North each combine 2 raw regions, so
    they end up with 2x n_points; West (1 raw region) just gets n_points.
    """
    points = sample_points_per_region(shapefile_path, region_col, n_points=n_points, seed=seed)
    code_to_zone = {
        code: f"VASS{area_number}"
        for area_number, (_name, codes) in VASS_REGION_GROUPS.items()
        for code in codes
    }
    points["region"] = points["region"].map(code_to_zone)
    return points


ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Precipitation and temperature are what the assignment asks for; snowfall
# is my own addition - for a hydropower catchment, snowmelt affects
# reservoir inflow just as much as rain does. Kept to just these 3 rather
# than grabbing everything open-meteo has, since at 1000 points per region
# and a full year hourly, extra variables add up fast (100 points x 1 year
# x 6 variables was already ~42 MB for one chunk, tested live).
HOURLY_VARIABLES = ["temperature_2m", "precipitation", "snowfall"]

# The 429s turned out to be open-meteo's DAILY quota, not a short burst
# limit - the API says so directly ("Daily API request limit exceeded.
# Please try again tomorrow."). That matters: the quota is per *request*,
# not per data point, so fewer/bigger chunks burn through it slower than
# lots of small ones - hence the fairly large chunk size, to keep 1000
# points down to about 10 requests instead of 100.
CHUNK_SIZE = 100
PAUSE_SECONDS = 2.0


def _points_hash(region_points):
    """Short hash of a region's actual sampled (lon, lat) points, used in
    cache filenames so two different samplings of "the same" region (a
    different seed, or a different n_points - e.g. a quick 10-point test
    run vs. the real 1000-point one) never collide on the same cache file.
    Rounded to 6 decimal places first so floating-point noise doesn't make
    two runs of the *same* sampling hash differently.
    """
    coords = region_points[["lon", "lat"]].to_numpy().round(6)
    return hashlib.md5(coords.tobytes()).hexdigest()[:8]


def fetch_weather_for_region(region_id, points_df, start_date, end_date, region_col="region", timeout=90, cache_dir=CACHE_DIR):
    """Hourly ERA5 historical weather (via open-meteo) for every point
    sampled for one region.

    points_df: output of sample_points_per_region() (or several
    shapefiles' results concatenated), with columns [region_col, "lat",
    "lon"]. Looks region_id up in that table rather than taking a plain
    list of points, to match the function signature the assignment asks
    for - a region identifier plus a time interval.

    Each chunk gets cached to disk under cache_dir (see _points_hash for
    why the cache key includes a hash of the actual points, not just
    region/date range) - open-meteo's daily quota is easy to burn through
    and the connection can be flaky for requests this size, so re-running
    this later reuses whatever's already fetched instead of re-downloading
    and spending more quota.

    Returns one row per (point, hour), tagged with the region, a point_id,
    and its own lon/lat, so it can be aggregated afterwards (e.g. averaged
    across points per timestamp).
    """
    region_points = (
        points_df.loc[points_df[region_col] == region_id, ["lon", "lat"]]
        .reset_index(drop=True)
    )
    if region_points.empty:
        raise ValueError(f"no sampled points found for region {region_id!r}")

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    points_hash = _points_hash(region_points)

    chunk_frames = []
    for chunk_start in range(0, len(region_points), CHUNK_SIZE):
        chunk = region_points.iloc[chunk_start:chunk_start + CHUNK_SIZE]
        cache_file = cache_dir / f"{region_id}_{points_hash}_{start_date}_{end_date}_{chunk_start:05d}.csv"

        if cache_file.exists():
            chunk_frames.append(pd.read_csv(cache_file))
            continue

        lons = chunk["lon"].tolist()
        lats = chunk["lat"].tolist()
        point_ids = list(range(chunk_start, chunk_start + len(chunk)))

        params = {
            "latitude": ",".join(str(lat) for lat in lats),
            "longitude": ",".join(str(lon) for lon in lons),
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(HOURLY_VARIABLES),
            "models": "era5",
            "timezone": "UTC",
        }

        # Two kinds of failure here: a plain network error (never got a
        # response at all), and a 429 - which can mean either a short burst
        # limit (worth retrying) or the daily/hourly quota actually being
        # used up (pointless to retry, no backoff clears that before the
        # stated window passes). open-meteo's error body says which one it
        # is, so that's checked explicitly rather than just retrying blind.
        response = None
        last_error = None
        backoff_seconds = [10, 20, 40, 80]
        for attempt in range(len(backoff_seconds) + 1):
            try:
                response = requests.get(ARCHIVE_URL, params=params, timeout=timeout)
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < len(backoff_seconds):
                    time.sleep(backoff_seconds[attempt])
                continue

            if response.status_code == 429:
                try:
                    reason = response.json().get("reason", "")
                except ValueError:
                    reason = response.text[:300]
                if any(window in reason.lower() for window in ("daily", "hourly")):
                    raise RuntimeError(
                        f"open-meteo's request quota is exhausted for now - retrying "
                        f"won't help until it resets: {reason!r}. {len(chunk_frames)} "
                        f"chunk(s) already fetched this call are cached in {cache_dir} "
                        f"and will be reused next time, so re-running won't lose that "
                        f"progress."
                    )
                last_error = RuntimeError(f"open-meteo rate limited this request (429): {reason!r}")
                if attempt < len(backoff_seconds):
                    time.sleep(backoff_seconds[attempt])
                continue

            response.raise_for_status()
            last_error = None
            break
        if last_error:
            raise RuntimeError(
                f"failed to fetch chunk {chunk_start}-{chunk_start + len(chunk)} of "
                f"region {region_id!r} after retries; {len(chunk_frames)} earlier "
                f"chunk(s) already fetched this call are cached in {cache_dir} and "
                f"will be reused next time - see the chained exception below for "
                f"the underlying cause"
            ) from last_error

        results = response.json()
        # A single location comes back as one object rather than a list.
        if isinstance(results, dict):
            results = [results]

        chunk_rows = []
        for point_id, lon, lat, result in zip(point_ids, lons, lats, results):
            hourly = result["hourly"]
            for i, timestamp in enumerate(hourly["time"]):
                row = {
                    "region": region_id,
                    "point_id": point_id,
                    "lon": lon,
                    "lat": lat,
                    "timestamp": timestamp,
                }
                for var in HOURLY_VARIABLES:
                    row[var] = hourly[var][i]
                chunk_rows.append(row)

        chunk_df = pd.DataFrame(chunk_rows)
        chunk_df.to_csv(cache_file, index=False)
        chunk_frames.append(chunk_df)

        time.sleep(PAUSE_SECONDS)  # stay well clear of the rate limit

    return pd.concat(chunk_frames, ignore_index=True)


def get_weather_hourly_avg(region_label, points_df, year, region_col="region"):
    """Streamlit-free hourly weather average (temperature/precipitation/
    snowfall) for one region/year - calls (or reuses the disk cache from)
    fetch_weather_for_region() above and averages across all its sampled
    points per timestamp.

    This is where the actual "average weather across a region" computation
    lives. app_utils.py's get_weather_hourly_avg_live() is just a thin
    cached wrapper around this - kept Streamlit-free here so it still
    works directly from the notebook (see app_utils.py's own docstring for
    why that matters).

    Replaces the old MongoDB-backed version from before Part 4 (pre-
    download once via Cassandra -> Spark -> MongoDB, read from Mongo if
    present). This always fetches instead (hitting the disk cache for
    chunks already downloaded) and can raise RuntimeError on a real
    network/quota failure - callers should catch that and show it to the
    user.
    """
    weather = fetch_weather_for_region(region_label, points_df, f"{year}-01-01", f"{year}-12-31", region_col=region_col)
    hourly_avg = weather.groupby("timestamp")[HOURLY_VARIABLES].mean()
    hourly_avg.index = pd.to_datetime(hourly_avg.index)
    return hourly_avg.sort_index()
