import streamlit as st

from modules.app_utils import area_selector, get_el_sampled_points
from modules.weather_utils import CHUNK_SIZE, fetch_weather_for_region, weather_cache_status

st.title("Meteorological Data")

st.caption(
    "Downloads hourly ERA5 weather (temperature, precipitation, snowfall, ...) for 1000 "
    "randomly sampled points in the selected price zone, via open-meteo - see the Part 3 "
    "notebook. This is its own page, separate from the pages that use the result, because "
    "open-meteo has a hard **daily** request quota that's easy to exhaust and a 1000-point "
    "download can take several minutes - so it only runs on an explicit button press here, "
    "never automatically just from loading a page or changing the area selector."
)

# Shared sidebar area selector (modules/app_utils.py) - the same one used by
# Table/Plot/Fill Degree, so the area picked here is the exact area the
# Weather Analysis page's outlier/anomaly checks run on too.
area_type, area_number = area_selector()

if area_type != "EL":
    st.info(
        "Weather download only covers EL (electricity price zones, NO1-NO5) so far - pick "
        "an EL zone in the sidebar to use this page.\n\n"
        "magasinstatistikk's VASS zones don't map 1:1 onto the 5-region NVE shapefile used "
        "for weather sampling (2 of its 3 zones are each a combination of 2 shapefile "
        "regions - see the Part 3 notebook), so wiring that up correctly needs more than "
        "guessing which `omrnr` is which. NO (the national total) has no corresponding "
        "region shapefile at all."
    )
    st.stop()

region_label = f"NO{area_number}"
st.subheader(f"Selected zone: {region_label}")

year = st.selectbox(
    "Year", options=[2024],
    help="Only 2024 has been downloaded/validated so far - see the Part 3 notebook.",
)
start_date, end_date = f"{year}-01-01", f"{year}-12-31"

all_points = get_el_sampled_points()
cached, total = weather_cache_status(region_label, all_points, start_date, end_date)

if total == 0:
    st.error(f"No sampled points found for {region_label} - this shouldn't happen.")
    st.stop()
elif cached == total:
    st.success(
        f"{region_label}, {year} is fully cached on disk ({total} chunk(s), "
        f"~{total * CHUNK_SIZE} points) - loading it below makes no network calls."
    )
else:
    st.warning(f"{cached} of {total} chunk(s) already cached for {region_label}, {year}.")

button_label = (
    f"Load cached weather for {region_label}, {year}"
    if cached == total
    else f"Download weather for {region_label}, {year} ({total - cached} chunk(s) remaining)"
)

if st.button(button_label):
    spinner_text = (
        "Loading from disk cache..."
        if cached == total
        else f"Downloading from open-meteo ({total - cached} chunk(s) remaining, may take a few minutes)..."
    )
    with st.spinner(spinner_text):
        try:
            weather = fetch_weather_for_region(region_label, all_points, start_date, end_date)
        except RuntimeError as e:
            st.error(str(e))
            # fetch_weather_for_region raises with `from <underlying error>` -
            # that chained cause (the actual timeout/connection/HTTP error) is
            # what explains WHY it failed, but st.error(str(e)) alone drops it,
            # leaving only the generic "see the chained exception below" message
            # on screen and forcing a dig through the terminal for the real
            # reason. Surface it here instead.
            if e.__cause__ is not None:
                st.caption(f"Underlying cause: {e.__cause__!r}")
        else:
            st.success(f"{len(weather)} hourly readings ready for {region_label}, {year}.")
            st.dataframe(weather.head())
