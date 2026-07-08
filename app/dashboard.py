"""
Darryn Peterson: Shot Chart & Role Evolution Dashboard

Run with:
    streamlit run app/dashboard.py
"""
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
SHOTS_PATH = os.path.join(BASE_DIR, "data", "processed", "shots.csv")

STAGE_COLORS = {"nba": "#1D428A", "summer_league": "#F58426"}  # Jazz-ish colors


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
