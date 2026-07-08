"""
Builds the processed datasets the dashboard reads from:
  data/processed/shots.csv      - per-shot rows across all rookies (for hex charts)
  data/processed/season_stats.csv - one row per rookie: PPG/RPG/APG/FG%/3PT%/games
  data/processed/rankings.csv   - season_stats + computed ROY score, ranked

Safe to re-run any time.

Usage:
    python scripts/build_dataset.py
"""
import glob
import os
import sys

import pandas as pd

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

sys.path.insert(0, os.path.join(BASE_DIR, "app"))
from roy_score import compute_roy_rankings  # noqa: E402

SHOT_SCHEMA = [
    "player", "stage", "game_date", "opponent", "shot_made", "shot_type",
    "shot_zone", "shot_x", "shot_y", "possession_type", "location_source",
]


def load_nba_shots() -> pd.DataFrame:
    """nba_api pulls (fetch_nba_games.py) are currently Darryn-Peterson-only
    and don't yet have a 'player' column - tagged here for now."""
    files = sorted(glob.glob(os.path.join(RAW_DIR, "nba_shots_*.csv")))
    if not files:
        return pd.DataFrame(columns=SHOT_SCHEMA)
    latest = files[-1]
    raw = pd.read_csv(latest)
    if raw.empty:
        return pd.DataFrame(columns=SHOT_SCHEMA)
    return pd.DataFrame({
        "player": "Darryn Peterson",
        "stage": "nba",
        "game_date": raw.get("GAME_DATE"),
        "opponent": raw.get("HTM").fillna("") + " vs " + raw.get("VTM").fillna(""),
        "shot_made": raw.get("SHOT_MADE_FLAG"),
        "shot_type": raw.get("SHOT_TYPE"),
        "shot_zone": raw.get("SHOT_ZONE_BASIC"),
        "shot_x": raw.get("LOC_X"),
        "shot_y": raw.get("LOC_Y"),
        "possession_type": None,
        "location_source": "nba_api",
    })


def load_rookie_shots() -> pd.DataFrame:
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
    return pd.read_csv(path)


def compute_season_stats(boxscores: pd.DataFrame, rookies: list) -> pd.DataFrame:
    rows = []
    for rookie in rookies:
        name = rookie["name"]
        player_box = boxscores[boxscores["player"] == name] if not boxscores.empty else pd.DataFrame()

        games = len(player_box)
        if games == 0:
            rows.append({
                "name": name, "team": rookie["team"], "draft_pick": rookie["draft_pick"],
                "games": 0, "ppg": 0.0, "rpg": 0.0, "apg": 0.0,
                "fg_pct": 0.0, "fg3_pct": 0.0,
            })
            continue

        fg_made = player_box["fg_made"].sum()
        fg_att = player_box["fg_attempts"].sum()
        three_made = player_box["three_made"].sum()
        three_att = player_box["three_attempts"].sum()

        rows.append({
            "name": name, "team": rookie["team"], "draft_pick": rookie["draft_pick"],
            "games": games,
            "ppg": round(player_box["points"].sum() / games, 1),
            "rpg": round(player_box["rebounds"].fillna(0).sum() / games, 1),
            "apg": round(player_box["assists"].fillna(0).sum() / games, 1),
            "fg_pct": round(fg_made / fg_att * 100, 1) if fg_att else 0.0,
            "fg3_pct": round(three_made / three_att * 100, 1) if three_att else 0.0,
        })
    return pd.DataFrame(rows)


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    nba_shots = load_nba_shots()
    rookie_shots = load_rookie_shots()
    combined_shots = pd.concat([nba_shots, rookie_shots], ignore_index=True)
    shots_path = os.path.join(PROCESSED_DIR, "shots.csv")
    combined_shots.to_csv(shots_path, index=False)
    print(f"Wrote {len(combined_shots)} shot rows -> {shots_path}")
    print(f"  - NBA rows: {len(nba_shots)}")
    print(f"  - Summer League rows: {len(rookie_shots)}")

    rookies_path = os.path.join(BASE_DIR, "data", "rookies.json")
    import json
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
    print(rankings[["name", "games", "ppg", "roy_score"]].to_string(index=False))


if __name__ == "__main__":
    main()
