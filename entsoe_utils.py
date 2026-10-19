"""Helpers for fetching and parsing cross-border physical flow data from the
ENTSO-E Transparency Platform RESTful API.

Verified against a real response on 2026-10-15 (NO2 -> DK1, documentType A11):
the API only sends a <Point> when the value CHANGES (curveType A03, "variable
sized block"). A point's quantity holds from its own position up to - but not
including - the next point's position, or the end of the period for the last
point. parse_crossborder_xml() expands that into one row per resolution step
so every position in the period gets a value.
"""

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://web-api.tp.entsoe.eu/api"
NS = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0"}

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
    api_key = os.getenv("ENTSOE_API_KEY")
    if not api_key:
        raise RuntimeError("ENTSOE_API_KEY not set - check your .env file")

    params = {
        "securityToken": api_key,
        "documentType": "A11",
        "in_Domain": in_domain_code,
        "out_Domain": out_domain_code,
        "periodStart": start.strftime("%Y%m%d%H00"),
        "periodEnd": end.strftime("%Y%m%d%H00"),
    }
    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.text


def parse_crossborder_xml(xml_text):
    """Parse a Publication_MarketDocument (documentType A11) into a tidy
    DataFrame with one row per resolution step: timestamp (UTC), out_domain,
    in_domain, quantity_mw. Returns an empty DataFrame if there's no data
    (e.g. ENTSO-E sends a near-empty document when a period has nothing to
    report, rather than an error).
    """
    root = ET.fromstring(xml_text)
    rows = []

    for ts in root.findall("ns:TimeSeries", NS):
        out_domain = ts.findtext("ns:out_Domain.mRID", namespaces=NS)
        in_domain = ts.findtext("ns:in_Domain.mRID", namespaces=NS)

        for period in ts.findall("ns:Period", NS):
            period_start = datetime.strptime(
                period.findtext("ns:timeInterval/ns:start", namespaces=NS),
                "%Y-%m-%dT%H:%MZ",
            ).replace(tzinfo=timezone.utc)
            period_end = datetime.strptime(
                period.findtext("ns:timeInterval/ns:end", namespaces=NS),
                "%Y-%m-%dT%H:%MZ",
            ).replace(tzinfo=timezone.utc)
            resolution = _RESOLUTION_TO_TIMEDELTA[period.findtext("ns:resolution", namespaces=NS)]

            points = [
                (int(p.findtext("ns:position", namespaces=NS)), float(p.findtext("ns:quantity", namespaces=NS)))
                for p in period.findall("ns:Point", NS)
            ]
            points.sort(key=lambda p: p[0])

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

    return pd.DataFrame(rows)


# Norway's direct international interconnectors used on the cross-border page.
# Each is a (Norwegian side, partner side) pair; "export" = out of Norway,
# "import" = into Norway.
CONNECTIONS = {
    "NO2-DK1": ("NO_2", "DK_1"),
    "NO2-NL": ("NO_2", "NL"),
    "NO2-DE": ("NO_2", "DE_LU"),
    "NO2-GB": ("NO_2", "GB"),
}


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
