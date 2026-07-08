"""
Darryn Peterson: Shot Chart & Role Evolution Dashboard

Run with:
    streamlit run app/dashboard.py
"""
import os

import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, LogNorm
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
SHOTS_PATH = os.path.join(BASE_DIR, "data", "processed", "shots.csv")

STAGE_COLORS = {"nba": "#1D428A", "summer_league": "#F58426"}  # Jazz-ish colors
STAGE_LABELS = {"nba": "NBA", "summer_league": "Summer League"}


DARK_BG = "#0d1b2a"
COURT_LINE_COLOR = "#4a6178"
FREQ_CMAP = LinearSegmentedColormap.from_list(
    "pts_freq", ["#16232f", "#5a4632", "#c97a2e", "#ff9a2e", "#ffb238"]
)
EFF_CMAP = LinearSegmentedColormap.from_list(
    "pts_eff", ["#2b6cb0", "#16232f", "#e8823a"]
)


def draw_court(fig):
    """Add a basic NBA half-court outline to a plotly figure (in feet, x0-50 y0-47)."""
    shapes = [
        dict(type="rect", x0=-25, y0=0, x1=25, y1=47, line=dict(color="black", width=1)),
        dict(type="rect", x0=-8, y0=0, x1=8, y1=19, line=dict(color="black", width=1)),
        dict(type="circle", x0=-6, y0=13, x1=6, y1=25, line=dict(color="black", width=1)),
        dict(type="path",
             path="M -22,0 L -22,14 Q -22,33 0,33 Q 22,33 22,14 L 22,0",
             line=dict(color="black", width=1)),
    ]
    for s in shapes:
        fig.add_shape(**s)
    fig.update_xaxes(range=[-27, 27], showgrid=False, zeroline=False, visible=False)
    fig.update_yaxes(range=[0, 47], showgrid=False, zeroline=False, visible=False,
                      scaleanchor="x", scaleratio=1)
    return fig


def draw_court_mpl(ax, color=COURT_LINE_COLOR, lw=1.1):
    """Draw an NBA half-court outline on a matplotlib axis, dark-theme style (feet, hoop at y=0)."""
    ax.add_patch(mpatches.Rectangle((-25, 0), 50, 47, fill=False, edgecolor=color, lw=lw))
    ax.add_patch(mpatches.Rectangle((-8, 0), 16, 19, fill=False, edgecolor=color, lw=lw))
    ax.add_patch(mpatches.Circle((0, 19), 6, fill=False, edgecolor=color, lw=lw))
    ax.add_patch(mpatches.Arc((0, 5.25), 8, 8, theta1=0, theta2=180, edgecolor=color, lw=lw))
    ax.add_patch(mpatches.Circle((0, 5.25), 0.75, fill=False, edgecolor=color, lw=lw))
    ax.plot([-3, 3], [4, 4], color=color, lw=lw)
    ax.plot([-22, -22], [0, 14], color=color, lw=lw)
    ax.plot([22, 22], [0, 14], color=color, lw=lw)
    three_arc = mpatches.Arc((0, 5.25), 47.5, 47.5, theta1=22, theta2=158,
                              edgecolor=color, lw=lw)
    ax.add_patch(three_arc)
    ax.set_xlim(-27, 27)
    ax.set_ylim(0, 40)
    ax.set_aspect("equal")
    ax.axis("off")


def _style_dark_figure(fig, ax, title):
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARK_BG)
    ax.set_title(title, fontsize=13, fontweight="bold", color="white", pad=10)


def plot_hexbin_chart(df: pd.DataFrame, title: str, mode: str = "frequency"):
    """
    PerThirtySix-style hexbin shot chart on a dark court, with per-zone value
    labels so exact numbers are visible, not just color.
    mode="frequency" -> hexagons colored by shot volume, labeled with shot count.
    mode="efficiency" -> hexagons colored by FG%, labeled with FG% per zone.
    """
    fig, ax = plt.subplots(figsize=(6.8, 6.9))
    df = df.dropna(subset=["shot_x", "shot_y", "shot_made"])

    if len(df) >= 5:
        if mode == "frequency":
            hb = ax.hexbin(
                df["shot_x"], df["shot_y"],
                gridsize=20, extent=(-25, 25, 0, 35),
                cmap=FREQ_CMAP, mincnt=1,
                edgecolors=DARK_BG, linewidths=0.6,
                norm=LogNorm(),  # color scale is log, but labels below show real counts
            )
            values = hb.get_array()
            def label_fmt(v):
                return f"{int(round(v))}"
        else:
            hb = ax.hexbin(
                df["shot_x"], df["shot_y"],
                C=df["shot_made"], reduce_C_function=np.mean,
                gridsize=20, extent=(-25, 25, 0, 35),
                cmap=EFF_CMAP, mincnt=1, vmin=0, vmax=1,
                edgecolors=DARK_BG, linewidths=0.6,
            )
            values = hb.get_array()
            def label_fmt(v):
                return f"{v * 100:.0f}%"

        # Label every hexagon with its actual value (count or FG%) so the
        # number is readable at a glance, not just inferred from color.
        for (hx, hy), v in zip(hb.get_offsets(), values):
            ax.text(
                hx, hy, label_fmt(v), ha="center", va="center",
                fontsize=7.5, fontweight="bold", color="white",
                path_effects=[pe.withStroke(linewidth=2, foreground=DARK_BG)],
            )

        cbar = fig.colorbar(hb, ax=ax, shrink=0.6, pad=0.02)
        cbar.set_label("Shots taken" if mode == "frequency" else "FG%",
                        fontsize=9, color="white")
        cbar.ax.tick_params(labelsize=8, colors="white")
        cbar.outline.set_edgecolor(DARK_BG)

        # On-chart legend explaining what the colors mean, so it doesn't
        # rely on a caption above the chart that could get missed.
        legend_text = (
            "darker/blue = fewer shots, brighter orange = more shots"
            if mode == "frequency"
            else "blue = below-average FG%, orange = above-average FG%"
        )
        ax.text(
            0, -3.2, legend_text, ha="center", va="top",
            fontsize=8, color="#8a99a8", style="italic",
        )
        ax.text(
            0, 36.5, f"n = {len(df)} shots", ha="center", va="bottom",
            fontsize=9, color="#8a99a8",
        )
    else:
        ax.text(0, 20, "Not enough shots yet", ha="center", fontsize=11, color="#8a99a8")

    draw_court_mpl(ax)
    ax.set_ylim(-5, 38)  # extra room for the legend/count text below and above the court
    _style_dark_figure(fig, ax, title)
    fig.tight_layout()
    return fig


@st.cache_data
def load_shots():
    if not os.path.exists(SHOTS_PATH):
        return pd.DataFrame()
    df = pd.read_csv(SHOTS_PATH)
    # nba_api coordinates are in units of 1/10 foot; convert to feet
    if "shot_x" in df.columns:
        df.loc[df["stage"] == "nba", "shot_x"] = df.loc[df["stage"] == "nba", "shot_x"] / 10
        df.loc[df["stage"] == "nba", "shot_y"] = df.loc[df["stage"] == "nba", "shot_y"] / 10
    return df


st.set_page_config(page_title="Darryn Peterson Tracker", layout="wide")
st.title("🏀 Darryn Peterson: Shot Chart & Role Evolution")
st.caption(
    "Tracking his shot profile and on-court role from Summer League into his "
    "NBA rookie season. Data updates automatically as new games are added."
)

shots = load_shots()

st.divider()

if shots.empty:
    st.info(
        "No Summer League or NBA shot data yet. Run `scripts/fetch_nba_games.py` "
        "and/or fill in a Summer League template (see data/templates/) and "
        "`scripts/build_dataset.py`, then refresh."
    )
else:
    stages_available = shots["stage"].dropna().unique().tolist()
    selected_stages = st.multiselect(
        "Stage(s) to show", options=stages_available, default=stages_available
    )
    filtered = shots[shots["stage"].isin(selected_stages)]

    tab1, tab2 = st.tabs(["Shot Chart", "Role Over Time"])

    with tab1:
        chart_style = st.radio(
            "Chart style", ["Favorite Spots (frequency)", "Make/Miss (efficiency)", "Scatter (raw)"],
            horizontal=True,
        )

        if chart_style == "Favorite Spots (frequency)":
            st.caption(
                "Hexagons colored/sized by how often he shoots from that zone — "
                "brighter orange = higher volume. Matches PerThirtySix's 'Favorite Spots' view."
            )
            cols = st.columns(len(selected_stages)) if selected_stages else [st]
            for col, stage in zip(cols, selected_stages):
                stage_df = filtered[filtered["stage"] == stage]
                with col:
                    fig = plot_hexbin_chart(stage_df, STAGE_LABELS.get(stage, stage), mode="frequency")
                    st.pyplot(fig, use_container_width=True)
        elif chart_style == "Make/Miss (efficiency)":
            st.caption(
                "Hexagons colored by field-goal % in that zone — blue = cold, "
                "orange = hot. Needs a handful of shots per zone to look meaningful."
            )
            cols = st.columns(len(selected_stages)) if selected_stages else [st]
            for col, stage in zip(cols, selected_stages):
                stage_df = filtered[filtered["stage"] == stage]
                with col:
                    fig = plot_hexbin_chart(stage_df, STAGE_LABELS.get(stage, stage), mode="efficiency")
                    st.pyplot(fig, use_container_width=True)
        else:
            fig = go.Figure()
            for stage in selected_stages:
                stage_df = filtered[filtered["stage"] == stage].dropna(subset=["shot_x", "shot_y"])
                if stage_df.empty:
                    continue
                made = stage_df[stage_df["shot_made"] == 1]
                missed = stage_df[stage_df["shot_made"] == 0]
                fig.add_trace(go.Scatter(
                    x=made["shot_x"], y=made["shot_y"], mode="markers",
                    name=f"{stage} - made",
                    marker=dict(symbol="circle", size=8, color=STAGE_COLORS.get(stage, "green")),
                ))
                fig.add_trace(go.Scatter(
                    x=missed["shot_x"], y=missed["shot_y"], mode="markers",
                    name=f"{stage} - missed",
                    marker=dict(symbol="x", size=8, color=STAGE_COLORS.get(stage, "red")),
                ))
            fig = draw_court(fig)
            fig.update_layout(height=650, legend=dict(orientation="h"))
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        if "possession_type" in filtered.columns and filtered["possession_type"].notna().any():
            role_counts = (
                filtered.dropna(subset=["possession_type"])
                .groupby(["stage", "possession_type"])
                .size()
                .reset_index(name="count")
            )
            fig2 = go.Figure()
            for stage in selected_stages:
                stage_role = role_counts[role_counts["stage"] == stage]
                fig2.add_trace(go.Bar(
                    x=stage_role["possession_type"], y=stage_role["count"], name=stage
                ))
            fig2.update_layout(
                barmode="group", height=450,
                xaxis_title="Possession type", yaxis_title="Shot attempts",
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info(
                "No possession-type data yet. NBA shot chart data alone doesn't "
                "include this — it needs to be tagged manually or pulled from "
                "play-by-play (see scripts/fetch_nba_games.py's game log fetch "
                "as a starting point for a fuller pipeline)."
            )

st.divider()
st.caption(
    "Data sources: nba_api (NBA regular season), manual charting (Summer League). "
    "See README for update workflow."
)
