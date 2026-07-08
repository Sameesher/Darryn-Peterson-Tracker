"""
Builds data/processed/shots.csv by merging whatever raw sources currently
exist: NBA shot chart pulls, Summer League manual entries, and the college
summary. Safe to re-run any time — later runs just re-merge the latest
raw files, they don't duplicate.

Usage:
    python scripts/build_dataset.py
"""
import glob
import os

import pandas as pd

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

SHOT_SCHEMA = [
    "stage",           # "nba" or "summer_league"
    "game_date",
    "opponent",
    "shot_made",
    "shot_type",
    "shot_zone",
    "shot_x",
    "shot_y",
    "possession_type",
]


def load_nba_shots() -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(RAW_DIR, "nba_shots_*.csv")))
    if not files:
        return pd.DataFrame(columns=SHOT_SCHEMA)
    # use the most recent pull for each season to avoid double counting
    latest = files[-1]
    raw = pd.read_csv(latest)
    if raw.empty:
        return pd.DataFrame(columns=SHOT_SCHEMA)
    out = pd.DataFrame({
        "stage": "nba",
        "game_date": raw.get("GAME_DATE"),
        "opponent": raw.get("HTM").fillna("") + " vs " + raw.get("VTM").fillna(""),
        "shot_made": raw.get("SHOT_MADE_FLAG"),
        "shot_type": raw.get("SHOT_TYPE"),
        "shot_zone": raw.get("SHOT_ZONE_BASIC"),
        "shot_x": raw.get("LOC_X"),
        "shot_y": raw.get("LOC_Y"),
        "possession_type": None,  # nba_api shotchartdetail doesn't tag this directly
    })
    return out


def load_summer_league_shots() -> pd.DataFrame:
    path = os.path.join(RAW_DIR, "summer_league_shots.csv")
    if not os.path.exists(path):
        return pd.DataFrame(columns=SHOT_SCHEMA)
    raw = pd.read_csv(path)
    out = pd.DataFrame({
        "stage": "summer_league",
        "game_date": raw.get("game_date"),
        "opponent": raw.get("opponent"),
        "shot_made": raw.get("shot_made"),
        "shot_type": raw.get("shot_type"),
        "shot_zone": raw.get("shot_zone"),
        "shot_x": raw.get("shot_x"),
        "shot_y": raw.get("shot_y"),
        "possession_type": raw.get("possession_type"),
    })
    return out


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    nba_shots = load_nba_shots()
    sl_shots = load_summer_league_shots()
    combined = pd.concat([nba_shots, sl_shots], ignore_index=True)

    out_path = os.path.join(PROCESSED_DIR, "shots.csv")
    combined.to_csv(out_path, index=False)
    print(f"Wrote {len(combined)} combined shot rows to {out_path}")
    print(f"  - NBA rows: {len(nba_shots)}")
    print(f"  - Summer League rows: {len(sl_shots)}")

    college_path = os.path.join(BASE_DIR, "data", "college_summary.csv")
    if os.path.exists(college_path):
        print(f"College summary stats available at {college_path} (used as-is, no shot coords)")


if __name__ == "__main__":
    main()
