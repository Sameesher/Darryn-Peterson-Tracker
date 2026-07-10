"""
Builds the processed datasets the dashboard reads from:
  data/processed/shots.csv        - shot-location data (from fetch_espn_shots.py,
                                     a separate pipeline from the stats below -
                                     see that script's docstring for why)
  data/processed/season_stats.csv - one row per rookie: PPG/RPG/APG/SPG/BPG,
                                     TS%, avg Game Score, games played, and
                                     which source was used (nba_official is
                                     preferred when available, RealGM is the
                                     fallback - see fetch_nba_official.py)
  data/processed/rankings.csv     - season_stats + computed ROY score, ranked

Safe to re-run any time.

Usage:
    python scripts/build_dataset.py
"""
import glob
import json
import os
import sys

import pandas as pd

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

sys.path.insert(0, os.path.join(BASE_DIR, "app"))
from roy_score import compute_roy_rankings, compute_advanced_stats  # noqa: E402

SHOT_SCHEMA = [
    "player", "stage", "game_date", "opponent", "shot_made", "shot_type",
    "shot_zone", "shot_x", "shot_y", "possession_type", "location_source",
]


def load_shots() -> pd.DataFrame:
    """Shot-location data from the ESPN-based pipeline (fetch_espn_shots.py) -
    intentionally separate from RealGM's stats pipeline, since RealGM has no
    shot coordinates."""
    path = os.path.join(RAW_DIR, "rookie_shots.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=SHOT_SCHEMA)
    raw = pd.read_csv(path)
    raw["stage"] = "summer_league"
    for col in SHOT_SCHEMA:
        if col not in raw.columns:
            raw[col] = None
    return raw[SHOT_SCHEMA]


def load_boxscores() -> pd.DataFrame:
    path = os.path.join(RAW_DIR, "rookie_boxscores.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    return compute_advanced_stats(df)


def load_official_stats() -> pd.DataFrame:
    """Official NBA.com/stats.nba.com Summer League averages (fetch_nba_official.py) -
    preferred over RealGM per-player when available, since it's the most
    authoritative source. Already per-game averages (one row per player),
    not per-game rows, so advanced stats are computed directly from the
    averages rather than via compute_advanced_stats (mathematically
    identical for these linear formulas - see that script's docstring)."""
    path = os.path.join(RAW_DIR, "rookie_nba_official_stats.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df

    denom = 2 * (df["fga_pg"] + 0.44 * df["fta_pg"])
    df["ts_pct"] = (df["pts_pg"] / denom.replace(0, pd.NA) * 100).fillna(0)
    df["avg_game_score"] = (
        df["pts_pg"] + 0.4 * df["fgm_pg"] - 0.7 * df["fga_pg"]
        - 0.4 * (df["fta_pg"] - df["ftm_pg"])
        + 0.7 * df["oreb_pg"] + 0.3 * df["dreb_pg"]
        + df["stl_pg"] + 0.7 * df["ast_pg"] + 0.7 * df["blk_pg"]
        - 0.4 * df["pf_pg"] - df["tov_pg"]
    )
    return df


def compute_season_stats(boxscores: pd.DataFrame, official: pd.DataFrame, rookies: list) -> pd.DataFrame:
    rows = []
    for rookie in rookies:
        name = rookie["name"]

        official_row = official[official["player"] == name] if not official.empty else pd.DataFrame()
        if not official_row.empty:
            r = official_row.iloc[0]
            rows.append({
                "name": name, "team": rookie["team"], "draft_pick": rookie["draft_pick"],
                "games": int(r["games"]),
                "ppg": round(r["pts_pg"], 1), "rpg": round(r["reb_pg"], 1),
                "apg": round(r["ast_pg"], 1), "spg": round(r["stl_pg"], 1),
                "bpg": round(r["blk_pg"], 1),
                "ts_pct": round(r["ts_pct"], 1), "avg_game_score": round(r["avg_game_score"], 1),
                "source": "nba_official",
            })
            continue

        player_box = boxscores[boxscores["player"] == name] if not boxscores.empty else pd.DataFrame()
        games = len(player_box)
        if games == 0:
            rows.append({
                "name": name, "team": rookie["team"], "draft_pick": rookie["draft_pick"],
                "games": 0, "ppg": 0.0, "rpg": 0.0, "apg": 0.0, "spg": 0.0, "bpg": 0.0,
                "ts_pct": 0.0, "avg_game_score": 0.0, "source": "none",
            })
            continue

        rows.append({
            "name": name, "team": rookie["team"], "draft_pick": rookie["draft_pick"],
            "games": games,
            "ppg": round(player_box["pts"].mean(), 1),
            "rpg": round(player_box["reb"].mean(), 1),
            "apg": round(player_box["ast"].mean(), 1),
            "spg": round(player_box["stl"].mean(), 1),
            "bpg": round(player_box["blk"].mean(), 1),
            "ts_pct": round(player_box["ts_pct"].mean(), 1),
            "avg_game_score": round(player_box["game_score"].mean(), 1),
            "source": "realgm",
        })
    return pd.DataFrame(rows)


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    shots = load_shots()
    shots_path = os.path.join(PROCESSED_DIR, "shots.csv")
    shots.to_csv(shots_path, index=False)
    print(f"Wrote {len(shots)} shot rows -> {shots_path}")

    rookies_path = os.path.join(BASE_DIR, "data", "rookies.json")
    with open(rookies_path) as f:
        rookies = json.load(f)

    boxscores = load_boxscores()
    official = load_official_stats()
    season_stats = compute_season_stats(boxscores, official, rookies)
    stats_path = os.path.join(PROCESSED_DIR, "season_stats.csv")
    season_stats.to_csv(stats_path, index=False)
    print(f"Wrote season stats for {len(season_stats)} rookies -> {stats_path}")
    print(season_stats[["name", "games", "ppg", "source"]].to_string(index=False))

    rankings = compute_roy_rankings(season_stats)
    rankings_path = os.path.join(PROCESSED_DIR, "rankings.csv")
    rankings.to_csv(rankings_path, index=False)
    print(f"Wrote ROY rankings -> {rankings_path}")
    print(rankings[["name", "games", "ppg", "avg_game_score", "ts_pct", "roy_score"]].to_string(index=False))


if __name__ == "__main__":
    main()
