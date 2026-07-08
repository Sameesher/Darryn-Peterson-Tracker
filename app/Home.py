"""
Rookie of the Year Tracker - Home hub.

Shows the top 10 tracked rookies ranked by a custom-weighted ROY score.
Click into the sidebar pages for each rookie's full profile (shot chart,
role breakdown - identical layout for every player, just their own data).

Run with:
    streamlit run app/Home.py
"""
import os

import pandas as pd
import streamlit as st

from player_profile import TEAM_LOGO_SLUGS, load_rookies

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
RANKINGS_PATH = os.path.join(BASE_DIR, "data", "processed", "rankings.csv")

DARK_BG = "#0d1b2a"

st.set_page_config(page_title="2026 Rookie of the Year Tracker", layout="wide")

st.title("🏆 2026 Rookie of the Year Tracker")
st.caption(
    "Tracking the top 10 picks of the 2026 NBA Draft, ranked by a custom-weighted "
    "score: Production (35%) → Game Score (30%) → Availability (20%) → Efficiency (15%). "
    "Click a rookie in the sidebar for their full shot chart and role breakdown."
)
st.divider()

if not os.path.exists(RANKINGS_PATH):
    st.info(
        "No rankings yet - run `scripts/build_dataset.py` after the data fetchers "
        "have pulled at least one game."
    )
else:
    rankings = pd.read_csv(RANKINGS_PATH)

    for i, row in rankings.iterrows():
        rank = i + 1
        logo_slug = TEAM_LOGO_SLUGS.get(row["team"])
        logo_url = f"https://a.espncdn.com/i/teamlogos/nba/500/{logo_slug}.png" if logo_slug else ""

        rookie_config = next((r for r in load_rookies() if r["name"] == row["name"]), {})
        headshot_url = rookie_config.get("headshot_url")
        headshot_html = (
            f'<img src="{headshot_url}" style="width:56px; height:56px; border-radius:50%; '
            f'background:white; object-fit:cover;" />'
            if headshot_url else
            '<div style="width:56px; height:56px; border-radius:50%; background:#2a3a4a; '
            'display:flex; align-items:center; justify-content:center; color:#8a99a8; '
            'font-size:22px;">?</div>'
        )
        logo_html = f'<img src="{logo_url}" style="width:32px; height:32px;" />' if logo_url else ""

        games_note = "" if row["games"] > 0 else (
            '<span style="color:#8a99a8; font-size:12px;"> (no games yet)</span>'
        )

        st.markdown(
            f"""
            <div style="display:flex; align-items:center; gap:18px; background:{DARK_BG};
                        border:1px solid #2a3a4a; border-radius:10px; padding:14px 20px;
                        margin-bottom:10px;">
              <div style="font-size:26px; font-weight:800; color:#8a99a8; width:36px;">
                #{rank}
              </div>
              {headshot_html}
              <div style="flex:1;">
                <div style="color:white; font-size:17px; font-weight:700;">
                  {row['name']} {logo_html}
                </div>
                <div style="color:#8a99a8; font-size:13px;">
                  {row['team']} - Pick #{int(row['draft_pick'])}{games_note}
                </div>
              </div>
              <div style="text-align:center; padding:0 14px;">
                <div style="color:white; font-size:20px; font-weight:800;">{row['ppg']}</div>
                <div style="color:#8a99a8; font-size:11px;">PPG</div>
              </div>
              <div style="text-align:center; padding:0 14px;">
                <div style="color:white; font-size:20px; font-weight:800;">{row['ts_pct']}%</div>
                <div style="color:#8a99a8; font-size:11px;">TS%</div>
              </div>
              <div style="text-align:center; padding:0 14px;">
                <div style="color:white; font-size:20px; font-weight:800;">{row['rpg']}</div>
                <div style="color:#8a99a8; font-size:11px;">RPG</div>
              </div>
              <div style="text-align:center; padding:0 14px;">
                <div style="color:white; font-size:20px; font-weight:800;">{row['apg']}</div>
                <div style="color:#8a99a8; font-size:11px;">APG</div>
              </div>
              <div style="text-align:center; padding:0 14px;">
                <div style="color:white; font-size:20px; font-weight:800;">{row['avg_game_score']}</div>
                <div style="color:#8a99a8; font-size:11px;">Game Score</div>
              </div>
              <div style="text-align:center; padding:0 14px; background:#F58426;
                          border-radius:8px; min-width:70px;">
                <div style="color:white; font-size:22px; font-weight:800;">{row['roy_score']}</div>
                <div style="color:white; font-size:11px;">ROY score</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()
    st.caption(
        "ROY score is normalized *within this group of 10* (not vs. the whole league), "
        "so scores shift slightly as data updates for everyone. Formula: Production "
        "(PPG+RPG+APG+SPG+BPG) 35% + Game Score 30% + Availability (games played) 20% "
        "+ True Shooting % 15%. See app/roy_score.py to change the weighting yourself."
    )
