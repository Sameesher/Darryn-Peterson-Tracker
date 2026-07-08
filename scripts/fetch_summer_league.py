"""
Summer League data ingestion.

stats.nba.com's Summer League shot/play-by-play data isn't reliably covered
by nba_api. Rather than block the pipeline on scraping something fragile,
this script takes manually-entered per-game data (from box scores, ESPN,
or your own charting while watching) and normalizes it to match the schema
used by the NBA-season data, so the dashboard can treat both consistently.

Workflow:
1. Copy data/templates/summer_league_game_template.csv
2. Fill in one row per shot attempt (or per game summary row, if you don't
   want shot-by-shot detail — see NOTES.md for the two supported formats)
3. Run this script to validate + append to data/raw/summer_league_shots.csv
"""
import glob
import os
import sys

import pandas as pd

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "templates")
OUTPUT_PATH = os.path.join(RAW_DIR, "summer_league_shots.csv")

REQUIRED_COLUMNS = [
    "game_date",
    "opponent",
    "shot_made",       # 1 or 0
    "shot_type",       # "2PT" or "3PT"
    "shot_zone",       # e.g. "Above the Break 3", "Restricted Area" (match NBA schema loosely)
    "shot_x",          # optional, leave blank if unknown
    "shot_y",          # optional, leave blank if unknown
    "assisted",        # 1 or 0 or blank if unknown
    "possession_type",  # "spot_up", "pull_up", "pnr_ball_handler", "off_screen", "iso", "transition", "post_up"
]


def validate(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def main(input_csv: str):
    df = pd.read_csv(input_csv)
    validate(df)

    os.makedirs(RAW_DIR, exist_ok=True)
    if os.path.exists(OUTPUT_PATH):
        existing = pd.read_csv(OUTPUT_PATH)
        # NOTE: no drop_duplicates() here on purpose. Two shots (or two free
        # throws) in the same game can have genuinely identical values in
        # every column - e.g. two made free throws with no location data -
        # and blindly deduping would silently delete one of them. The
        # tradeoff is that re-running this script on the *same* input file
        # twice will double-count it, so don't do that.
        combined = pd.concat([existing, df], ignore_index=True)
    else:
        combined = df

    combined.to_csv(OUTPUT_PATH, index=False)
    print(f"Summer League dataset now has {len(combined)} total shot rows -> {OUTPUT_PATH}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/fetch_summer_league.py <path_to_filled_in_csv>")
        sys.exit(1)
    main(sys.argv[1])
