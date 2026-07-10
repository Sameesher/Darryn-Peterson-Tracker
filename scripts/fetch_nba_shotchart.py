"""
SCRAPER (official source): NBA.com's own shot chart data, via the same
stats.nba.com API that powers the shot plot on pages like
nba.com/game/{game-slug}/game-charts - the page in the screenshot that
inspired this script shows exactly this: a court with circles (made) and
X's (missed) per player, filterable by player checkbox. That chart is
rendered from the ShotChartDetail endpoint, which `nba_api` (already a
dependency) wraps directly.

This REPLACES fetch_espn_shots.py as the shot-location pipeline for any
rookie this covers - nba.com is now the single source for stats (see
fetch_nba_official.py), shot locations (this file), AND headshots (also
fetch_nba_official.py, which captures the NBA.com player ID this script
also needs). ESPN remains available as a fallback only for rookies without
an nba_player_id yet.

How it works, per rookie:
1. Needs `nba_player_id` in data/rookies.json (populated by
   fetch_nba_official.py - run that first).
2. Calls PlayerGameLogs (bulk-capable, but used per-player here for
   simplicity) with SeasonType="Summer League" to find which games that
   player has played - returns real stats.nba.com GAME_IDs.
3. For each game not already processed, calls ShotChartDetail with that
   player_id + game_id to get every shot attempt with real X/Y court
   coordinates, shot zone, made/missed, and distance - genuine tracked
   locations, not the distance/text-based estimates the ESPN pipeline
   sometimes had to fall back on.

Writes to data/raw/rookie_shots.csv, same schema fetch_espn_shots.py used
(player, game_date, opponent, shot_made, shot_type, shot_zone, shot_x,
shot_y, possession_type, location_source) so build_dataset.py needs no
changes - location_source is set to "nba_official" here.

IMPORTANT CAVEATS - read before trusting this blindly:
- Could not be tested against the live stats.nba.com API from the sandbox
  that built it (network restricted to package registries only) - the
  first real run is the actual test.
- ShotChartDetail's coordinate system is in the same 1/10-foot units the
  existing NBA-season pipeline (fetch_nba_games.py) already handles - the
  dashboard's load_shots() already divides by 10 for stage="nba", but this
  writes stage="summer_league" shots, so this script converts to feet
  itself (divides by 10) before writing, to keep the output schema
  consistent regardless of which pipeline produced it.
- possession_type isn't available from ShotChartDetail directly (no
  play-type tagging) - left blank here, same as it would be for any
  shot the ESPN pipeline couldn't classify either.
- `season` string uncertainty is the same as fetch_nba_official.py - see
  that script's docstring.

Usage:
    python scripts/fetch_nba_shotchart.py
    python scripts/fetch_nba_shotchart.py --player "Darryn Peterson"   # single player, for testing
    python scripts/fetch_nba_shotchart.py --season 2026-27

Designed to run unattended on a schedule (see .github/workflows/update_data.yml),
after fetch_nba_official.py (which supplies nba_player_id).
"""
import argparse
import csv
import json
import os
import time

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
ROOKIES_PATH = os.path.join(BASE_DIR, "data", "rookies.json")
STATE_PATH = os.path.join(BASE_DIR, "data", "processed_nba_shot_games.json")
SHOTS_OUTPUT_PATH = os.path.join(RAW_DIR, "rookie_shots.csv")

SHOT_CSV_COLUMNS = [
    "player", "game_date", "opponent", "shot_made", "shot_type", "shot_zone",
    "shot_x", "shot_y", "assisted", "possession_type", "location_source",
]


def load_rookies() -> list:
    with open(ROOKIES_PATH) as f:
        return json.load(f)


def load_state() -> set:
    if not os.path.exists(STATE_PATH):
        return set()
    with open(STATE_PATH) as f:
        return set(json.load(f).get("processed_game_ids", []))


def save_state(processed: set) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump({"processed_game_ids": sorted(processed)}, f, indent=2)


def get_player_games(player_id: str, season: str):
    """Returns a DataFrame of this player's Summer League games (one row
    per game, includes GAME_ID, GAME_DATE, MATCHUP), or None on failure."""
    try:
        from nba_api.stats.endpoints import playergamelog
    except ImportError:
        print("[error] nba_api not installed.")
        return None
    try:
        resp = playergamelog.PlayerGameLog(
            player_id=player_id, season=season, season_type_all_star="Summer League",
        )
        return resp.get_data_frames()[0]
    except Exception as e:
        print(f"    [error] PlayerGameLog call failed: {e}")
        return None


def get_shot_chart(player_id: str, game_id: str, season: str):
    """Returns a DataFrame of every shot attempt for this player in this
    specific game, with real X/Y coordinates, or None on failure."""
    try:
        from nba_api.stats.endpoints import shotchartdetail
    except ImportError:
        print("[error] nba_api not installed.")
        return None
    try:
        resp = shotchartdetail.ShotChartDetail(
            team_id=0, player_id=player_id, game_id_nullable=game_id,
            season_nullable=season, season_type_all_star="Summer League",
            context_measure_simple="FGA",
        )
        return resp.get_data_frames()[0]
    except Exception as e:
        print(f"    [error] ShotChartDetail call failed for game {game_id}: {e}")
        return None


def parse_matchup(matchup: str, player_team_in_matchup_first: bool = True) -> str:
    """MATCHUP looks like 'UTA vs. ATL' or 'UTA @ ATL' - returns the opponent abbreviation."""
    for sep in [" vs. ", " @ "]:
        if sep in matchup:
            parts = matchup.split(sep)
            if len(parts) == 2:
                return parts[1].strip()
    return matchup


def rows_from_shot_chart(df, player_name: str, game_date: str, opponent: str) -> list:
    rows = []
    for _, shot in df.iterrows():
        shot_type = "3PT" if shot.get("SHOT_TYPE", "").startswith("3PT") else "2PT"
        rows.append({
            "player": player_name,
            "game_date": game_date,
            "opponent": opponent,
            "shot_made": int(shot.get("SHOT_MADE_FLAG", 0)),
            "shot_type": shot_type,
            "shot_zone": shot.get("SHOT_ZONE_BASIC", ""),
            "shot_x": round(float(shot.get("LOC_X", 0)) / 10, 1),
            "shot_y": round(float(shot.get("LOC_Y", 0)) / 10, 1),
            "assisted": "",  # ShotChartDetail doesn't tag this directly
            "possession_type": "",  # no play-type tagging available from this endpoint
            "location_source": "nba_official",
        })
    return rows


def append_rows(rows: list) -> None:
    if not rows:
        return
    os.makedirs(RAW_DIR, exist_ok=True)
    file_exists = os.path.exists(SHOTS_OUTPUT_PATH)
    with open(SHOTS_OUTPUT_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SHOT_CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fetch_one_rookie(rookie: dict, season: str, processed: set, delay: float) -> int:
    name = rookie["name"]
    player_id = rookie.get("nba_player_id")
    if not player_id:
        print(f"\n{name}: no nba_player_id yet - run fetch_nba_official.py first. Skipping.")
        return 0

    print(f"\n{name} (nba_player_id={player_id}):")
    games_df = get_player_games(player_id, season)
    if games_df is None or games_df.empty:
        print("  No Summer League games found for this player yet.")
        return 0

    new_total = 0
    for _, game in games_df.iterrows():
        game_id = str(game.get("Game_ID") or game.get("GAME_ID"))
        key = f"{name}|{game_id}"
        if key in processed:
            continue

        game_date = str(game.get("GAME_DATE", ""))
        opponent = parse_matchup(str(game.get("MATCHUP", "")))

        print(f"  Processing new game {game_id} ({game_date} vs {opponent})...")
        shot_df = get_shot_chart(player_id, game_id, season)
        if shot_df is None or shot_df.empty:
            print("    No shots returned for this game.")
            processed.add(key)
            continue

        rows = rows_from_shot_chart(shot_df, name, game_date, opponent)
        append_rows(rows)
        new_total += len(rows)
        print(f"    Added {len(rows)} shot(s).")
        processed.add(key)
        time.sleep(delay)

    return new_total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2026-27",
                         help="Season string stats.nba.com expects (default 2026-27 - "
                              "same uncertainty as fetch_nba_official.py, verify on first live run)")
    parser.add_argument("--player", default=None,
                         help="Only fetch this one rookie (exact name match), for testing")
    parser.add_argument("--delay", type=float, default=1.0,
                         help="Seconds to wait between ShotChartDetail calls (default 1.0)")
    args = parser.parse_args()

    rookies = load_rookies()
    if args.player:
        rookies = [r for r in rookies if r["name"] == args.player]
        if not rookies:
            print(f"No rookie named '{args.player}' in data/rookies.json")
            return

    processed = load_state()
    total_new = 0

    for rookie in rookies:
        total_new += fetch_one_rookie(rookie, args.season, processed, args.delay)

    save_state(processed)
    print(f"\nDone. {total_new} new shot rows this run.")


if __name__ == "__main__":
    main()
