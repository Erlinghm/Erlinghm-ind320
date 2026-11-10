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
    """Return a DataFrame with n_points random (lat, lon) locations inside
    each region's polygon, reprojected to WGS84 regardless of the
    shapefile's own CRS (both of ours are EPSG:25833, UTM zone 33N).

    Sampling is by rejection: draw random points inside each region's
    bounding box and keep the ones that actually fall inside the polygon,
    topping up with another batch whenever not enough land inside - simpler
    than a direct polygon-sampling method and fine at this scale (1000
    points, a handful of regions).
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


ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Precipitation and temperature are what the assignment explicitly asks for;
# snowfall is included as an "other relevant property" - for a hydropower
# catchment, snowmelt affects reservoir inflow alongside rain, so it's
# directly relevant here even though the assignment doesn't name it. Kept
# short rather than grabbing every available variable: at 1000 points per
# region and a full year hourly, each extra variable adds real time and
# data volume (tested live: 100 points x 1 year hourly x 6 variables was
# already ~42 MB for one chunk).
HOURLY_VARIABLES = ["temperature_2m", "precipitation", "snowfall"]

# The 429s turned out to be open-meteo's DAILY request quota, not a
# short-lived burst limit - confirmed by the API's own error message
# ("Daily API request limit exceeded. Please try again tomorrow."). That
# changes the trade-off completely: since the quota is per *request* (not
# per data point), fewer, larger chunks use it up more slowly than many
# small ones. So this uses a large-ish chunk size to keep the total number
# of requests for 1000 points down to about 10, rather than optimising for
# request size.
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


def weather_cache_status(region_id, points_df, start_date, end_date, region_col="region", cache_dir=CACHE_DIR):
    """How many of fetch_weather_for_region's chunks for these exact
    arguments are already cached on disk, without making any network calls -
    lets a UI show "already downloaded" (or how much of it is) before
    committing to a real fetch, which can be slow and is subject to
    open-meteo's daily quota.

    Returns (cached_chunks, total_chunks). (0, 0) if the region has no
    sampled points at all (shouldn't happen for a real shapefile region).
    """
    region_points = points_df.loc[points_df[region_col] == region_id]
    if region_points.empty:
        return 0, 0

    cache_dir = Path(cache_dir)
    points_hash = _points_hash(region_points)
    chunk_starts = range(0, len(region_points), CHUNK_SIZE)
    total_chunks = len(chunk_starts)
    cached_chunks = sum(
        1 for chunk_start in chunk_starts
        if (cache_dir / f"{region_id}_{points_hash}_{start_date}_{end_date}_{chunk_start:05d}.csv").exists()
    )
    return cached_chunks, total_chunks


def fetch_weather_for_region(region_id, points_df, start_date, end_date, region_col="region", timeout=90, cache_dir=CACHE_DIR):
    """Hourly ERA5 historical weather (via open-meteo) for every point
    sampled for one region.

    points_df: the output of sample_points_per_region() - optionally the
    concatenation of several shapefiles' results - with columns
    [region_col, "lat", "lon"]. Rather than taking a list of points
    directly, this looks region_id up in that table itself, matching the
    assignment's required function signature: a region identifier plus a
    time interval.

    Each chunk of points is downloaded once and then cached to disk (under
    cache_dir, keyed by region/date range/chunk position AND a hash of the
    actual sampled (lon, lat) points in that chunk - see _points_hash) -
    open-meteo's daily request quota is easy to exhaust and the connection
    can be flaky for a request this size, so a later call (even a fresh
    one, e.g. after restarting the kernel) reuses whatever was already
    fetched rather than re-downloading it and burning more quota. The
    points hash means a differently-sampled points_df for "the same"
    region (a different seed, a different n_points - e.g. a quick 10-point
    test run vs. a real 1000-point one) automatically gets its own cache
    entries rather than colliding with an old, mismatched one.

    Returns one tidy DataFrame with a row per (point, hour), tagged with
    the region, a point_id (that point's position within the region's
    sampled list) and its own lon/lat, so the raw readings can be
    aggregated (e.g. averaged across points per timestamp) afterwards.
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

        # Two different kinds of failure to recover from here: a network-level
        # problem (timeout/connection error - the request never even got a
        # response), and a 429, which itself can mean a short burst limit
        # (worth retrying after a short wait) or a longer-lived quota being
        # exhausted - seen in practice as both "daily" and "hourly" request
        # limits, worded differently ("try again tomorrow" / "try again in
        # the next hour") but both pointless to retry within this call: no
        # amount of backoff clears either before the stated window passes,
        # and burning more retries against an already-exhausted quota just
        # risks extending the throttle further. open-meteo's error body says
        # which kind of 429 it is, so that's checked explicitly.
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
