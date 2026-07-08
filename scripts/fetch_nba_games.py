"""
Fetch Darryn Peterson's NBA shot chart + play-by-play data via nba_api.

This only works once he has played real NBA regular-season minutes with a
resolvable player_id (Summer League is NOT covered by this endpoint —
see fetch_summer_league.py for that stage).

Usage:
    python scripts/fetch_nba_games.py --season 2026-27

Output:
    data/raw/nba_shots_<season>_<timestamp>.csv
    data/raw/nba_pbp_<season>_<timestamp>.csv
"""
import argparse
import datetime as dt
import os
import sys
import time

import pandas as pd

try:
    from nba_api.stats.static import players
    from nba_api.stats.endpoints import shotchartdetail, playergamelog
except ImportError:
    print("nba_api not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

PLAYER_NAME = "Darryn Peterson"
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def get_player_id(name: str) -> int:
    matches = players.find_players_by_full_name(name)
    if not matches:
        raise ValueError(
            f"No player found for '{name}'. He may not be in the nba_api "
            "static player list yet if he's a brand-new rookie — check "
            "nba_api's player list has refreshed for the current season."
        )
    return matches[0]["id"]


def fetch_shot_chart(player_id: int, season: str) -> pd.DataFrame:
    resp = shotchartdetail.ShotChartDetail(
        team_id=0,
        player_id=player_id,
        season_nullable=season,
        season_type_all_star="Regular Season",
        context_measure_simple="FGA",
    )
    df = resp.get_data_frames()[0]
    df["pulled_at"] = dt.datetime.utcnow().isoformat()
    return df


def fetch_game_log(player_id: int, season: str) -> pd.DataFrame:
    resp = playergamelog.PlayerGameLog(player_id=player_id, season=season)
    df = resp.get_data_frames()[0]
    df["pulled_at"] = dt.datetime.utcnow().isoformat()
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--season",
        default="2026-27",
        help="NBA season string, e.g. 2026-27",
    )
    args = parser.parse_args()

    os.makedirs(RAW_DIR, exist_ok=True)
    player_id = get_player_id(PLAYER_NAME)
    print(f"Found player_id={player_id} for {PLAYER_NAME}")

    timestamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S")

    shots = fetch_shot_chart(player_id, args.season)
    shots_path = os.path.join(RAW_DIR, f"nba_shots_{args.season}_{timestamp}.csv")
    shots.to_csv(shots_path, index=False)
    print(f"Wrote {len(shots)} shot rows to {shots_path}")

    time.sleep(1)  # be polite to the API between calls

    log = fetch_game_log(player_id, args.season)
    log_path = os.path.join(RAW_DIR, f"nba_gamelog_{args.season}_{timestamp}.csv")
    log.to_csv(log_path, index=False)
    print(f"Wrote {len(log)} game log rows to {log_path}")


if __name__ == "__main__":
    main()
