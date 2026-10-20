"""Helpers for fetching and parsing cross-border physical flow data from the
ENTSO-E Transparency Platform RESTful API.

Verified against a real response on 2026-10-15 (NO2 -> DK1, documentType A11):
the API only sends a <Point> when the value CHANGES (curveType A03, "variable
sized block"). A point's quantity holds from its own position up to - but not
including - the next point's position, or the end of the period for the last
point. parse_crossborder_xml() expands that into one row per resolution step
so every position in the period gets a value.
"""

import os # for os.getenv() to read ENTSOE_API_KEY from .env
import xml.etree.ElementTree as ET # for parsing the XML response from ENTSO-E
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests 
from dotenv import load_dotenv # for reading ENTSOE_API_KEY from .env

load_dotenv()

BASE_URL = "https://web-api.tp.entsoe.eu/api" # Base URL for ENTSO-E Transparency Platform RESTful API
NS = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0"} # XML namespace for parsing the ENTSO-E XML response

# EIC domain codes (from ENTSO-E's own area list)
AREAS = {
    "NO": "10YNO-0--------C",
    "NO_1": "10YNO-1--------2",
    "NO_2": "10YNO-2--------T",
    "NO_3": "10YNO-3--------J",
    "NO_4": "10YNO-4--------9",
    "NO_5": "10Y1001A1001A48H",
    "DK_1": "10YDK-1--------W",
    "DE_LU": "10Y1001A1001A82H",
    "NL": "10YNL----------L",
    "GB": "10YGB----------A",
    "SE_1": "10Y1001A1001A44P",
    "SE_2": "10Y1001A1001A45N",
    "SE_3": "10Y1001A1001A46L",
    "SE_4": "10Y1001A1001A47J",
    "FI": "10YFI-1--------U",
}

_RESOLUTION_TO_TIMEDELTA = {
    "PT15M": timedelta(minutes=15),
    "PT30M": timedelta(minutes=30),
    "PT60M": timedelta(hours=1),
    "P1D": timedelta(days=1),
}


def fetch_crossborder_flow_xml(out_domain_code, in_domain_code, start, end):
    """Raw XML text for cross-border physical flow (documentType A11) from
    out_domain_code to in_domain_code, for the UTC datetime range [start, end).
    """
    # Read the ENTSO-E API key from the environment variable (set in .env)
    api_key = os.getenv("ENTSOE_API_KEY")
    if not api_key:
        raise RuntimeError("ENTSOE_API_KEY not set - check your .env file")

    # Build the query parameters for the ENTSO-E API request
    params = {
        "securityToken": api_key,
        "documentType": "A11",
        "in_Domain": in_domain_code,
        "out_Domain": out_domain_code,
        "periodStart": start.strftime("%Y%m%d%H00"),
        "periodEnd": end.strftime("%Y%m%d%H00"),
    }
    # Make the GET request to the ENTSO-E API and return the raw XML text
    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status() # Raise an error if the request failed (e.g., network issue, invalid API key, etc.)
    return response.text # Return the raw XML response text from the ENTSO-E API


def parse_crossborder_xml(xml_text):
    """Parse a Publication_MarketDocument (documentType A11) into a tidy
    DataFrame with one row per resolution step: timestamp (UTC), out_domain,
    in_domain, quantity_mw. Returns an empty DataFrame if there's no data
    (e.g. ENTSO-E sends a near-empty document when a period has nothing to
    report, rather than an error).
    """
    # Parse the XML text into an ElementTree and initialize an empty list to hold the rows
    root = ET.fromstring(xml_text)
    rows = []

    # Iterate over each TimeSeries element in the XML, extracting the relevant data
    for ts in root.findall("ns:TimeSeries", NS):
        out_domain = ts.findtext("ns:out_Domain.mRID", namespaces=NS) # Extract the out_domain code from the TimeSeries element
        in_domain = ts.findtext("ns:in_Domain.mRID", namespaces=NS) # Extract the in_domain code from the TimeSeries element

        # Iterate over each Period element within the TimeSeries, extracting the start and end times, resolution, and quantity points
        for period in ts.findall("ns:Period", NS):
            period_start = datetime.strptime(
                period.findtext("ns:timeInterval/ns:start", namespaces=NS),
                "%Y-%m-%dT%H:%MZ",
            ).replace(tzinfo=timezone.utc) # Convert the start time string to a UTC datetime object
            period_end = datetime.strptime(
                period.findtext("ns:timeInterval/ns:end", namespaces=NS),
                "%Y-%m-%dT%H:%MZ",
            ).replace(tzinfo=timezone.utc)
            resolution = _RESOLUTION_TO_TIMEDELTA[period.findtext("ns:resolution", namespaces=NS)] # Convert the resolution string to a timedelta object using the predefined mapping

            # Extract the quantity points from the Period element, sort them by position, and expand them into individual rows for each resolution step
            points = [
                (int(p.findtext("ns:position", namespaces=NS)), float(p.findtext("ns:quantity", namespaces=NS)))
                for p in period.findall("ns:Point", NS)
            ]
            points.sort(key=lambda p: p[0]) # Sort the points by position to ensure they are in the correct order for processing

            # Calculate the duration in hours for each resolution step and the total number of positions in the period, then iterate over the points to create rows for each resolution step
            duration_hours = resolution.total_seconds() / 3600
            total_positions = int((period_end - period_start) / resolution)
            for i, (position, quantity) in enumerate(points):
                next_position = points[i + 1][0] if i + 1 < len(points) else total_positions + 1
                for pos in range(position, next_position):
                    rows.append({
                        "timestamp": period_start + (pos - 1) * resolution,
                        "out_domain": out_domain,
                        "in_domain": in_domain,
                        "quantity_mw": quantity,
                        "duration_hours": duration_hours,
                    })

    return pd.DataFrame(rows) # Return a DataFrame containing the parsed data with one row per resolution step, including the timestamp, out_domain, in_domain, quantity in MW, and duration in hours for each step


# Norway's direct international interconnectors used on the cross-border page.
# Each is a (Norwegian side, partner side) pair; "export" = out of Norway,
# "import" = into Norway.
CONNECTIONS = {
    "NO2-DK1": ("NO_2", "DK_1"),
    "NO2-NL": ("NO_2", "NL"),
    "NO2-DE": ("NO_2", "DE_LU"),
    "NO2-GB": ("NO_2", "GB"),
}

# Helper to fetch one connection's full-year data in one direction, for use in the Streamlit app's cross-border page. The ENTSO-E API only allows one
# direction at a time, so we need to call this twice for each connection (once for "export" and once for "import") to get the full picture of Norway's physical electricity exchange with its directly connected neighbours. 
def fetch_connection_year_xml(connection_key, direction, year):
    """Raw XML for one connection, one direction, one full calendar year.
    direction: "export" (Norway -> partner) or "import" (partner -> Norway).
    """
    no_side, partner_side = CONNECTIONS[connection_key]
    no_code, partner_code = AREAS[no_side], AREAS[partner_side]
    out_code, in_code = (no_code, partner_code) if direction == "export" else (partner_code, no_code)

    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    return fetch_crossborder_flow_xml(out_code, in_code, start, end)


CONNECTION_LABELS = {
    "NO2-DK1": "Norway - Denmark (Skagerrak)",
    "NO2-NL": "Norway - Netherlands (NorNed)",
    "NO2-DE": "Norway - Germany (NordLink)",
    "NO2-GB": "Norway - Great Britain (North Sea Link)",
}
