"""The app's single colour/theme definition - every Plotly chart in the app
imports CATEGORICAL/SEQUENTIAL/DIVERGING/STATUS from here rather than letting
Plotly pick its own defaults, so the whole app reads as one consistent
system rather than a different palette per page.

Palette validated with the data-viz skill's CVD/contrast checker before use
(8-colour categorical: worst adjacent CVD Delta E 9.1, worst adjacent
normal-vision Delta E 19.6 - both clear the pass floors; 3 of the 8 slots
sit below 3:1 contrast against the chart surface, so those are never relied
on without a visible legend/direct label, per the skill's "relief rule").
Matches .streamlit/config.toml's [theme] section - same primary blue, same
light surface - so Streamlit's own chrome (buttons, sliders, sidebar) and
the Plotly charts inside it look like one app.
"""

import plotly.graph_objects as go
import plotly.io as pio

# Fixed-order categorical palette - never cycle or reassign these per chart;
# a series keeps the same colour across pages/reruns because it keeps the
# same *slot*, not because it keeps the same position in whatever list
# happened to be plotted.
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

# Single-hue blue ramp for continuous magnitude (map choropleth fill,
# correlation-strength heatmap) - lightest = near zero, darkest = highest.
SEQUENTIAL = [
    [0.00, "#cde2fb"], [0.15, "#9ec5f4"], [0.30, "#6da7ec"], [0.45, "#3987e5"],
    [0.60, "#2a78d6"], [0.75, "#1c5cab"], [0.90, "#104281"], [1.00, "#0d366b"],
]

# blue <-> red, gray midpoint - for correlation sign (sliding-window
# correlation page) or any other +/- around zero.
DIVERGING = [
    [0.0, "#0d366b"], [0.25, "#2a78d6"], [0.5, "#f0efec"], [0.75, "#e34948"], [1.0, "#8a1f1f"],
]

# Reserved for state, never reused as a plain series colour (outlier/anomaly
# flags on the SPC/LOF plots use these, not a categorical slot).
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
    """Register (and make default) a Plotly template using this module's
    colours, so every st.plotly_chart(...) in the app picks these up
    automatically without each page having to set colours itself. Safe to
    call more than once (e.g. once per page import) - re-registering just
    overwrites the same template with itself.
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
