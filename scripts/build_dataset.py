"""
Builds the processed datasets the dashboard reads from:
  data/processed/shots.csv        - frozen historical shot-location data
                                     (Peterson + Acuff's first 2 games each,
                                     from the old ESPN-based pipeline - no
                                     new shot data comes in via RealGM)
  data/processed/season_stats.csv - one row per rookie: PPG/RPG/APG/SPG/BPG,
                                     TS%, avg Game Score, games played
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


def load_frozen_shots() -> pd.DataFrame:
    """Historical shot-location data from the old ESPN-based pipeline.
    Frozen - RealGM doesn't provide shot coordinates, so nothing new lands
    here going forward. Kept so the two existing shot charts still render."""
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


def compute_season_stats(boxscores: pd.DataFrame, rookies: list) -> pd.DataFrame:
    rows = []
    for rookie in rookies:
        name = rookie["name"]
        player_box = boxscores[boxscores["player"] == name] if not boxscores.empty else pd.DataFrame()

        games = len(player_box)
        if games == 0:
            rows.append({
                "name": name, "team": rookie["team"], "draft_pick": rookie["draft_pick"],
                "games": 0, "ppg": 0.0, "rpg": 0.0, "apg": 0.0, "spg": 0.0, "bpg": 0.0,
                "ts_pct": 0.0, "avg_game_score": 0.0,
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
        })
    return pd.DataFrame(rows)


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    shots = load_frozen_shots()
    shots_path = os.path.join(PROCESSED_DIR, "shots.csv")
    shots.to_csv(shots_path, index=False)
    print(f"Wrote {len(shots)} frozen historical shot rows -> {shots_path}")

    rookies_path = os.path.join(BASE_DIR, "data", "rookies.json")
    with open(rookies_path) as f:
        rookies = json.load(f)

    boxscores = load_boxscores()
    season_stats = compute_season_stats(boxscores, rookies)
    stats_path = os.path.join(PROCESSED_DIR, "season_stats.csv")
    season_stats.to_csv(stats_path, index=False)
    print(f"Wrote season stats for {len(season_stats)} rookies -> {stats_path}")

    rankings = compute_roy_rankings(season_stats)
    rankings_path = os.path.join(PROCESSED_DIR, "rankings.csv")
    rankings.to_csv(rankings_path, index=False)
    print(f"Wrote ROY rankings -> {rankings_path}")
    print(rankings[["name", "games", "ppg", "avg_game_score", "ts_pct", "roy_score"]].to_string(index=False))


if __name__ == "__main__":
    main()
