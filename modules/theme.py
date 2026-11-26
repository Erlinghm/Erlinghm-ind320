"""One shared colour/theme file for the whole app - every chart imports
CATEGORICAL/SEQUENTIAL/DIVERGING/STATUS from here instead of just using
Plotly's defaults, so pages don't end up with a different palette each.

Ran the categorical colours through a colourblindness checker before
settling on these 8.

Also matches the colours in .streamlit/config.toml, so the sidebar/buttons
and the charts don't end up looking like two different apps stuck together.
"""

import plotly.graph_objects as go
import plotly.io as pio

# Fixed order, never cycled - area/zone 1 is always colour 1 etc, regardless
# of what else happens to be plotted on the same chart.
CATEGORICAL = [
    "#2a78d6",  # 1 blue      - primary series / "selected" emphasis
    "#eb6834",  # 2 orange    - secondary series / forecast median
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#6250d6",  # 7 violet
    "#e34948",  # 8 red
]

# Blue ramp for magnitude (map colouring, correlation heatmap) - light = low,
# dark = high.
SEQUENTIAL = [
    [0.00, "#cde2fb"], [0.15, "#9ec5f4"], [0.30, "#6da7ec"], [0.45, "#3987e5"],
    [0.60, "#2a78d6"], [0.75, "#1c5cab"], [0.90, "#104281"], [1.00, "#0d366b"],
]

# Blue <-> red with a gray midpoint, for anything that can be +/- (the
# correlation page mainly).
DIVERGING = [
    [0.0, "#0d366b"], [0.25, "#2a78d6"], [0.5, "#f0efec"], [0.75, "#e34948"], [1.0, "#8a1f1f"],
]

# Only used for outlier/anomaly markers on the SPC/LOF plots, not as a
# regular series colour.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

CHROME = {
    "surface": "#fcfcfb",
    "page": "#f9f9f7",
    "ink": "#0b0b0b",
    "ink_secondary": "#52514e",
    "ink_muted": "#898781",
    "gridline": "#e1e0d9",
    "baseline": "#c3c2b7",
}


def register_template(name="ind320"):
    """Register this module's colours as a Plotly template and make it the
    default, so every st.plotly_chart() picks them up without each page
    setting colours itself. Fine to call this more than once.
    """
    template = go.layout.Template(
        layout=go.Layout(
            colorway=CATEGORICAL,
            paper_bgcolor=CHROME["surface"],
            plot_bgcolor=CHROME["surface"],
            font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", color=CHROME["ink"]),
            title=dict(font=dict(color=CHROME["ink"])),
            xaxis=dict(gridcolor=CHROME["gridline"], linecolor=CHROME["baseline"], zerolinecolor=CHROME["baseline"]),
            yaxis=dict(gridcolor=CHROME["gridline"], linecolor=CHROME["baseline"], zerolinecolor=CHROME["baseline"]),
            legend=dict(bgcolor=CHROME["surface"]),
            colorscale=dict(sequential=SEQUENTIAL, diverging=DIVERGING),
        )
    )
    pio.templates[name] = template
    pio.templates.default = name
    return name
