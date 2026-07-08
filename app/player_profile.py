"""
Shared rendering logic for a single rookie's profile page. Every rookie's
page (app/pages/*.py) is a thin wrapper that just calls render_profile(name) -
this is the ONE place the actual layout/chart code lives, so every rookie's
page looks identical in style, just with their own data.
"""
import json
import math
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from stats import compute_season_stats

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
SHOTS_PATH = os.path.join(BASE_DIR, "data", "processed", "shots.csv")
ROOKIES_PATH = os.path.join(BASE_DIR, "data", "rookies.json")

DARK_BG = "#0d1b2a"
COURT_LINE_COLOR = "#4a6178"
STAGE_COLORS = {"nba": "#1D428A", "summer_league": "#F58426"}
STAGE_LABELS = {"nba": "NBA", "summer_league": "Summer League"}

FREQ_COLORSCALE = [
    [0.0, "#16232f"], [0.25, "#5a4632"], [0.5, "#c97a2e"],
    [0.75, "#ff9a2e"], [1.0, "#ffb238"],
]
EFF_COLORSCALE = [[0.0, "#2b6cb0"], [0.5, "#16232f"], [1.0, "#e8823a"]]

HOOP_X, HOOP_Y = 0.0, 5.25

# ESPN team logo URLs keyed by team display name (hotlinked from ESPN's public CDN)
TEAM_LOGO_SLUGS = {
    "Washington Wizards": "wsh", "Utah Jazz": "utah", "Memphis Grizzlies": "mem",
    "Chicago Bulls": "chi", "LA Clippers": "lac", "Brooklyn Nets": "bkn",
    "Sacramento Kings": "sac", "Atlanta Hawks": "atl", "Dallas Mavericks": "dal",
    "Milwaukee Bucks": "mil",
}


@st.cache_data
def load_shots():
    if not os.path.exists(SHOTS_PATH):
        return pd.DataFrame()
    df = pd.read_csv(SHOTS_PATH)
    if "shot_x" in df.columns:
        nba_mask = df["stage"] == "nba"
        df.loc[nba_mask, "shot_x"] = df.loc[nba_mask, "shot_x"] / 10
        df.loc[nba_mask, "shot_y"] = df.loc[nba_mask, "shot_y"] / 10
    return df


@st.cache_data
def load_rookies():
    with open(ROOKIES_PATH) as f:
        return json.load(f)


def get_rookie_config(player_name: str):
    for r in load_rookies():
        if r["name"] == player_name:
            return r
    return None


def draw_court_plotly(fig):
    shapes = [
        dict(type="rect", x0=-25, y0=0, x1=25, y1=35, line=dict(color=COURT_LINE_COLOR, width=1.2)),
        dict(type="rect", x0=-8, y0=0, x1=8, y1=19, line=dict(color=COURT_LINE_COLOR, width=1.2)),
        dict(type="circle", x0=-6, y0=13, x1=6, y1=25, line=dict(color=COURT_LINE_COLOR, width=1.2)),
        dict(type="path", path="M -22,0 L -22,14 Q -22,33 0,33 Q 22,33 22,14 L 22,0",
             line=dict(color=COURT_LINE_COLOR, width=1.2)),
        dict(type="circle", x0=-0.75, y0=4.5, x1=0.75, y1=6, line=dict(color=COURT_LINE_COLOR, width=1.2)),
        dict(type="path", path="M -4,5.25 Q 0,9.25 4,5.25", line=dict(color=COURT_LINE_COLOR, width=1.2)),
    ]
    for s in shapes:
        fig.add_shape(**s)
    fig.update_xaxes(range=[-27, 27], showgrid=False, zeroline=False, visible=False)
    fig.update_yaxes(range=[-4, 38], showgrid=False, zeroline=False, visible=False,
                      scaleanchor="x", scaleratio=1)
    return fig


def compute_hex_bins(df: pd.DataFrame, gridsize: int = 16):
    x, y, made = df["shot_x"].values, df["shot_y"].values, df["shot_made"].values
    dist = np.sqrt((x - HOOP_X) ** 2 + (y - HOOP_Y) ** 2)

    fig_tmp, ax_tmp = plt.subplots()
    hb_count = ax_tmp.hexbin(x, y, gridsize=gridsize, extent=(-25, 25, 0, 35), mincnt=1)
    hb_makes = ax_tmp.hexbin(x, y, C=made, reduce_C_function=np.sum,
                              gridsize=gridsize, extent=(-25, 25, 0, 35), mincnt=1)
    hb_dist = ax_tmp.hexbin(x, y, C=dist, reduce_C_function=np.mean,
                             gridsize=gridsize, extent=(-25, 25, 0, 35), mincnt=1)
    offsets = hb_count.get_offsets()
    counts = hb_count.get_array()
    makes = hb_makes.get_array()
    dists = hb_dist.get_array()
    plt.close(fig_tmp)

    return pd.DataFrame({
        "x": offsets[:, 0], "y": offsets[:, 1],
        "attempts": counts, "makes": makes, "avg_dist": dists,
        "pct": np.where(counts > 0, makes / counts * 100, 0),
    })


def plot_hexbin_interactive(df: pd.DataFrame, title: str, mode: str = "frequency"):
    df = df.dropna(subset=["shot_x", "shot_y", "shot_made"])
    fig = go.Figure()

    if len(df) >= 5:
        bins = compute_hex_bins(df)
        if mode == "frequency":
            color_vals, colorscale, colorbar_title = bins["attempts"], FREQ_COLORSCALE, "Shots"
        else:
            color_vals, colorscale, colorbar_title = bins["pct"], EFF_COLORSCALE, "FG%"

        sizes = 16 + np.sqrt(bins["attempts"]) * 9
        customdata = np.stack([bins["makes"], bins["attempts"], bins["pct"], bins["avg_dist"]], axis=-1)

        fig.add_trace(go.Scatter(
            x=bins["x"], y=bins["y"], mode="markers",
            marker=dict(
                symbol="hexagon", size=sizes, sizemode="diameter",
                color=color_vals, colorscale=colorscale,
                line=dict(color=DARK_BG, width=1.5),
                colorbar=dict(title=colorbar_title, tickfont=dict(color="white"),
                               title_font=dict(color="white"), outlinecolor=DARK_BG),
                cmin=0, cmax=(bins["attempts"].max() if mode == "frequency" else 100),
            ),
            customdata=customdata,
            hovertemplate=(
                "Shots: %{customdata[0]:.0f}/%{customdata[1]:.0f} (%{customdata[2]:.1f}%)<br>"
                "Distance: %{customdata[3]:.1f} ft<extra></extra>"
            ),
        ))

        legend_text = (
            "darker/blue = fewer shots, brighter orange = more shots"
            if mode == "frequency"
            else "blue = below-average FG%, orange = above-average FG%"
        )
        fig.add_annotation(x=0, y=-3, text=legend_text, showarrow=False,
                            font=dict(size=11, color="#8a99a8"))
        fig.add_annotation(x=0, y=36.5, text=f"n = {len(df)} shots", showarrow=False,
                            font=dict(size=12, color="#8a99a8"))
    else:
        fig.add_annotation(x=0, y=20, text="Not enough shots yet", showarrow=False,
                            font=dict(size=13, color="#8a99a8"))

    fig = draw_court_plotly(fig)
    fig.update_layout(
        title=dict(text=title, font=dict(size=18, color="white", family="Arial Black")),
        paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG,
        height=560, margin=dict(l=10, r=10, t=50, b=10), showlegend=False,
    )
    return fig


def render_player_card(rookie_config: dict, stats: dict):
    name = rookie_config["name"]
    team = rookie_config["team"]
    headshot_url = rookie_config.get("headshot_url")
    logo_slug = TEAM_LOGO_SLUGS.get(team)
    logo_url = f"https://a.espncdn.com/i/teamlogos/nba/500/{logo_slug}.png" if logo_slug else ""

    headshot_html = (
        f'<img src="{headshot_url}" style="width:64px; height:64px; border-radius:50%; '
        f'background:white; object-fit:cover;" />'
        if headshot_url else
        '<div style="width:64px; height:64px; border-radius:50%; background:#2a3a4a; '
        'display:flex; align-items:center; justify-content:center; color:#8a99a8; '
        'font-size:24px;">?</div>'
    )
    logo_html = f'<img src="{logo_url}" style="width:48px; height:48px;" />' if logo_url else ""

    st.markdown(
        f"""
        <div style="border-radius:12px; overflow:hidden; border:1px solid #2a3a4a;">
          <div style="background:#002B5C; padding:16px 20px; display:flex;
                      align-items:center; justify-content:space-between;">
            <div style="display:flex; align-items:center; gap:14px;">
              {headshot_html}
              <div style="color:white; font-size:22px; font-weight:800; line-height:1.1;">
                {name}
              </div>
            </div>
            {logo_html}
          </div>
          <div style="background:{DARK_BG}; padding:18px 20px 20px 20px;">
            <div style="font-size:40px; font-weight:800; color:white; line-height:1;">
              {stats['ppg']}
            </div>
            <div style="color:#8a99a8; font-size:13px; margin-bottom:14px;">
              points per game ({stats['games']} game{'s' if stats['games'] != 1 else ''})
            </div>
            <div style="display:flex; gap:22px;">
              <div><span style="color:white; font-size:18px; font-weight:800;">{stats['fg_pct']}%</span>
                <span style="color:#8a99a8; font-size:12px;"> fg</span></div>
              <div><span style="color:white; font-size:18px; font-weight:800;">{stats['fg3_pct']}%</span>
                <span style="color:#8a99a8; font-size:12px;"> 3fg</span></div>
              <div><span style="color:white; font-size:18px; font-weight:800;">{stats['ft_pct']}%</span>
                <span style="color:#8a99a8; font-size:12px;"> ft</span></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_profile(player_name: str):
    """The full profile page for one rookie - call this from a pages/*.py file."""
    st.set_page_config(page_title=f"{player_name} | Rookie Tracker", layout="wide")

    rookie_config = get_rookie_config(player_name)
    if rookie_config is None:
        st.error(f"'{player_name}' isn't in data/rookies.json.")
        return

    shots = load_shots()
    player_shots = shots[shots["player"] == player_name] if not shots.empty else shots

    header_col, card_col = st.columns([2, 1])
    with header_col:
        st.title(f"🏀 {player_name}: Shot Chart & Role Evolution")
        st.caption(
            f"Draft pick #{rookie_config['draft_pick']} ({rookie_config['college']}) - "
            f"{rookie_config['team']}. Tracking shot profile and on-court role from "
            "Summer League into the NBA rookie season."
        )
    with card_col:
        season_stats = compute_season_stats(shots, player=player_name)
        render_player_card(rookie_config, season_stats)

    st.divider()

    if player_shots.empty:
        st.info(
            f"No shot data yet for {player_name}. This is expected if their team "
            "hasn't played Summer League games yet, or the automated fetcher "
            "hasn't run since their last game."
        )
        return

    stages_available = player_shots["stage"].dropna().unique().tolist()
    selected_stages = st.multiselect(
        "Stage(s) to show", options=stages_available, default=stages_available,
        key=f"stages_{player_name}",
    )
    filtered = player_shots[player_shots["stage"].isin(selected_stages)]

    tab1, tab2 = st.tabs(["Shot Chart", "Role Over Time"])

    with tab1:
        chart_style = st.radio(
            "Chart style", ["Favorite Spots (frequency)", "Make/Miss (efficiency)", "Scatter (raw)"],
            horizontal=True, key=f"style_{player_name}",
        )
        if chart_style in ("Favorite Spots (frequency)", "Make/Miss (efficiency)"):
            mode = "frequency" if chart_style.startswith("Favorite") else "efficiency"
            st.caption("Hover over any hexagon for the exact shot count, FG%, and distance.")
            cols = st.columns(len(selected_stages)) if selected_stages else [st]
            for col, stage in zip(cols, selected_stages):
                stage_df = filtered[filtered["stage"] == stage]
                with col:
                    fig = plot_hexbin_interactive(stage_df, STAGE_LABELS.get(stage, stage), mode=mode)
                    st.plotly_chart(fig, width='stretch')
        else:
            fig = go.Figure()
            for stage in selected_stages:
                stage_df = filtered[filtered["stage"] == stage].dropna(subset=["shot_x", "shot_y"])
                if stage_df.empty:
                    continue
                made = stage_df[stage_df["shot_made"] == 1]
                missed = stage_df[stage_df["shot_made"] == 0]
                fig.add_trace(go.Scatter(
                    x=made["shot_x"], y=made["shot_y"], mode="markers", name=f"{stage} - made",
                    marker=dict(symbol="circle", size=8, color=STAGE_COLORS.get(stage, "green")),
                ))
                fig.add_trace(go.Scatter(
                    x=missed["shot_x"], y=missed["shot_y"], mode="markers", name=f"{stage} - missed",
                    marker=dict(symbol="x", size=8, color=STAGE_COLORS.get(stage, "red")),
                ))
            fig = draw_court_plotly(fig)
            fig.update_layout(height=650, legend=dict(orientation="h"),
                               paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG)
            st.plotly_chart(fig, width='stretch')

    with tab2:
        if "possession_type" in filtered.columns and filtered["possession_type"].notna().any():
            role_counts = (
                filtered.dropna(subset=["possession_type"])
                .groupby(["stage", "possession_type"]).size().reset_index(name="count")
            )
            fig2 = go.Figure()
            for stage in selected_stages:
                stage_role = role_counts[role_counts["stage"] == stage]
                fig2.add_trace(go.Bar(x=stage_role["possession_type"], y=stage_role["count"], name=stage))
            fig2.update_layout(barmode="group", height=450,
                               xaxis_title="Possession type", yaxis_title="Shot attempts")
            st.plotly_chart(fig2, width='stretch')
        else:
            st.info("No possession-type data yet for this stage.")

    st.divider()
    st.caption(
        "Data sources: RealGM (Summer League box scores + photos), nba_api (NBA regular season, once it starts)."
    )
