"""Plotly figures for the report.

Figures are built with the light-mode palette. The page swaps in the dark
steps and theme chrome at render time (see `report.py`), so every color used
here must come from the constants below.
"""
import numpy as np
import plotly.graph_objects as go

# Categorical slots, in fixed order (validated light/dark pairs).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
DEEMPH, DEEMPH_DARK = "#c3c2b7", "#4a4a46"
ACCENT = SERIES[0]
# Sequential blue: near-surface → strong, per mode.
SEQ_LIGHT = ["#f3f7fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ_DARK = ["#1d2129", "#132c4f", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"]

COLOR_MAP_DARK = dict(zip(SERIES + [DEEMPH], SERIES_DARK + [DEEMPH_DARK]))


def _scale(colors):
    n = len(colors) - 1
    return [[i / n, c] for i, c in enumerate(colors)]


def _fig(height=320, **layout):
    fig = go.Figure()
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=8), showlegend=False,
                      bargap=0.35, barcornerradius=4, hovermode="closest")
    fig.update_xaxes(showgrid=False, automargin=True, fixedrange=True)
    fig.update_yaxes(showgrid=True, zeroline=False, automargin=True, fixedrange=True, rangemode="tozero")
    fig.update_layout(**layout)
    return fig


def _legend_top():
    return dict(showlegend=True, legend=dict(orientation="h", x=0, xanchor="left", y=1.02, yanchor="bottom",
                                             traceorder="normal"))


def bars(x, y, *, horizontal=False, color=ACCENT, height=320, hover="%{y:,.0f}", text=None,
         ytitle=None, xtitle=None, colors=None, tickformat=None):
    """Single-series bar chart. `colors` (per-bar) is only used for emphasis vs de-emphasis."""
    fig = _fig(height)
    marker = dict(color=colors if colors is not None else color)
    if horizontal:
        fig.add_bar(x=y, y=x, orientation="h", marker=marker, hovertemplate=f"%{{y}}<br>{hover.replace('%{y', '%{x')}<extra></extra>",
                    text=text, textposition="outside" if text is not None else None, cliponaxis=False)
        fig.update_yaxes(autorange="reversed", showgrid=False, rangemode="normal", ticksuffix="  ")
        fig.update_xaxes(showgrid=True, tickformat=tickformat, title=xtitle)
        fig.update_layout(bargap=0.3)
        if text is not None and len(y):
            fig.update_xaxes(range=[0, max(y) * 1.18])  # room for the value labels
    else:
        fig.add_bar(x=x, y=y, marker=marker, hovertemplate=f"%{{x}}<br>{hover}<extra></extra>",
                    text=text, textposition="outside" if text is not None else None, cliponaxis=False)
        fig.update_yaxes(title=ytitle, tickformat=tickformat)
        fig.update_xaxes(title=xtitle)
        if len(x) and isinstance(list(x)[0], str):
            fig.update_xaxes(type="category")
    return fig


def monthly_hours(monthly):
    fig = bars(monthly.index, monthly.values.round(1), hover="%{y:,.1f} h", ytitle="Hours per month")
    fig.update_traces(hovertemplate="%{x|%B %Y}<br>%{y:,.1f} h<extra></extra>")
    fig.update_layout(bargap=0.15)
    return fig


def yearly_hours(yearly):
    fig = bars(yearly["label"], yearly["hours"].round(0), hover="%{y:,.0f} h",
               text=[f"{h:,.0f} h" for h in yearly["hours"]], ytitle="Hours")
    fig.update_traces(customdata=yearly[["per_day", "streams"]].values,
                      hovertemplate="%{x}<br>%{y:,.0f} h · %{customdata[1]:,} streams"
                                    "<br>%{customdata[0]:.0f} min per listening day<extra></extra>")
    fig.update_layout(margin=dict(t=24))
    return fig


def cumulative(cum, milestones):
    fig = _fig(280)
    fig.add_scatter(x=cum.index, y=cum.values.round(1), mode="lines", line=dict(color=ACCENT, width=2),
                    fill="tozeroy", fillcolor="rgba(42,120,214,0.10)",
                    hovertemplate="%{x|%-d %b %Y}<br>%{y:,.0f} h total<extra></extra>")
    for target, when in milestones.items():
        fig.add_scatter(x=[when], y=[target], mode="markers+text", text=[f"{target:,} h"],
                        textposition="top left", marker=dict(size=9, color=ACCENT, line=dict(width=2, color="#fcfcfb")),
                        hovertemplate=f"{target:,} h reached<br>%{{x|%-d %b %Y}}<extra></extra>")
    fig.update_yaxes(title="Cumulative hours")
    return fig


def bump(years, bump_data, max_rank):
    fig = _fig(380, **_legend_top())
    for i, (artist, ranks) in enumerate(bump_data.items()):
        fig.add_scatter(x=[str(y) for y in years], y=ranks, name=artist, mode="lines+markers",
                        line=dict(color=SERIES[i % 8], width=2),
                        marker=dict(size=9, color=SERIES[i % 8], line=dict(width=2, color="#fcfcfb")),
                        connectgaps=False, hovertemplate=f"<b>{artist}</b><br>%{{x}}: #%{{y}}<extra></extra>")
    fig.update_yaxes(autorange=False, range=[max_rank + 1, 0.3], title="Rank by hours that year",
                     tickvals=[1, 5, 10, 20, 30, 40], rangemode="normal")
    fig.update_xaxes(type="category")
    fig.update_layout(margin=dict(t=40))
    return fig


def heatmap(heat, weekdays):
    fig = _fig(300)
    fig.add_heatmap(z=heat.values.round(1), x=[f"{h:02d}" for h in heat.columns], y=weekdays,
                    colorscale=_scale(SEQ_LIGHT), xgap=2, ygap=2,
                    colorbar=dict(title=dict(text="min / week", side="right"), thickness=10, outlinewidth=0),
                    hovertemplate="%{y} %{x}:00<br>%{z:.1f} min per week on average<extra></extra>")
    fig.update_yaxes(autorange="reversed", showgrid=False, rangemode="normal")
    fig.update_xaxes(title="Hour of day (local time)", dtick=2)
    return fig


def multi_lines(df, *, pct=False, height=300, ytitle=None):
    fig = _fig(height, **_legend_top())
    fmt = ".0%" if pct else ",.0f"
    for i, col in enumerate(df.columns):
        fig.add_scatter(x=[str(x) for x in df.index], y=df[col], name=col, mode="lines+markers",
                        line=dict(color=SERIES[i], width=2), marker=dict(size=8, color=SERIES[i], line=dict(width=2, color="#fcfcfb")),
                        hovertemplate=f"{col}: %{{y:{fmt}}}<extra></extra>")
    fig.update_layout(hovermode="x unified", margin=dict(t=40))
    fig.update_yaxes(tickformat=".0%" if pct else None, title=ytitle)
    fig.update_xaxes(type="category")
    return fig


def stacked(df, *, pct=False, height=320, ytitle=None, hover_fmt=",.1f", suffix=""):
    fig = _fig(height, barmode="stack", **_legend_top())
    for i, col in enumerate(df.columns):
        fig.add_bar(x=df.index, y=df[col], name=col, marker=dict(color=SERIES[i], line=dict(width=1, color="#fcfcfb")),
                    hovertemplate=f"{col}: %{{y:{hover_fmt}}}{suffix}<extra></extra>")
    fig.update_layout(hovermode="x unified", margin=dict(t=40), barcornerradius=0)
    fig.update_yaxes(tickformat=".0%" if pct else None, title=ytitle)
    return fig


def grouped(df, *, height=300, pct=True):
    fig = _fig(height, barmode="group", **_legend_top())
    for i, col in enumerate(df.columns):
        fig.add_bar(x=df.index.astype(str), y=df[col], name=col, marker=dict(color=SERIES[i]),
                    hovertemplate=f"{col}: %{{y:{'.0%' if pct else ',.0f'}}}<extra></extra>")
    fig.update_layout(hovermode="x unified", margin=dict(t=40), bargap=0.3, bargroupgap=0.08)
    fig.update_yaxes(tickformat=".0%" if pct else None)
    return fig


SYMBOLS = ["circle", "square", "diamond", "triangle-up", "triangle-down", "pentagon", "hexagon", "circle-open"]


def network(nodes, edges, names, label_per_scene=3, height=640):
    """Artist co-listening map: one trace per scene (color + symbol), edges as hairlines."""
    fig = _fig(height, **_legend_top())
    ex, ey = [], []
    for x0, y0, x1, y1 in edges:
        ex += [x0, x1, None]
        ey += [y0, y1, None]
    fig.add_scatter(x=ex, y=ey, mode="lines", line=dict(color=DEEMPH, width=0.6), hoverinfo="skip",
                    showlegend=False, name="links")
    labelled = set(nodes.sort_values("hours", ascending=False).groupby("group").head(label_per_scene)["artist"])
    size_ref = nodes["hours"].max()
    for gid in sorted(nodes["group"].unique()):
        g = nodes[nodes["group"] == gid]
        other = gid not in names or names[gid] == "Other scenes"
        color = DEEMPH if other else SERIES[int(gid) % 8]
        fig.add_scatter(
            x=g["x"], y=g["y"], name=names.get(gid, "Other scenes"),
            mode="markers+text", text=[a if a in labelled else "" for a in g["artist"]],
            textposition="top center", customdata=g[["artist", "hours"]].values,
            marker=dict(size=(8 + 30 * (g["hours"] / size_ref) ** 0.5), color=color,
                        symbol=SYMBOLS[int(gid) % 8] if not other else "circle",
                        line=dict(width=2, color="#fcfcfb")),
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]:.0f} h<extra>%{fullData.name}</extra>")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, rangemode="normal")
    fig.update_layout(margin=dict(t=60, l=4, r=4, b=4))
    return fig


def matrix_heatmap(mat, *, xtitle=None, colorbar="", hover="%{z:.0%}", pct=True, height=320, zmax=None):
    fig = _fig(height)
    z = mat.values.astype(float)
    fig.add_heatmap(z=np.round(z, 3), x=[str(c) for c in mat.columns], y=[str(i) for i in mat.index],
                    colorscale=_scale(SEQ_LIGHT), xgap=2, ygap=2, zmin=0, zmax=zmax,
                    colorbar=dict(title=dict(text=colorbar, side="right"), thickness=10, outlinewidth=0,
                                  tickformat=".0%" if pct else None),
                    hovertemplate=f"%{{y}} · %{{x}}<br>{hover}<extra></extra>", hoverongaps=False)
    fig.update_yaxes(autorange="reversed", showgrid=False, rangemode="normal", type="category")
    fig.update_xaxes(title=xtitle, type="category")
    return fig


def survival(curves, height=320):
    fig = _fig(height, **_legend_top())
    for i, (name, s) in enumerate(curves.items()):
        fig.add_scatter(x=(s.index / 30.44).round(2), y=s.values.round(4), name=name, mode="lines",
                        line=dict(color=SERIES[i], width=2, shape="hv"),
                        hovertemplate=f"{name}<br>after %{{x:.0f}} months: %{{y:.0%}} still around<extra></extra>")
    fig.update_yaxes(tickformat=".0%", range=[0, 1.02], title="Artists still in rotation")
    fig.update_xaxes(title="Months since you discovered the artist")
    fig.update_layout(margin=dict(t=40))
    return fig
