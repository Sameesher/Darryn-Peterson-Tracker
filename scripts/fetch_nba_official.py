"""
SCRAPER 1 of 3 (PRIMARY pipeline): NBA.com's own Summer League stats, via
the stats.nba.com JSON API that nba.com's pages themselves call
client-side (the visible nba.com pages, e.g. nba.com/2026-summer-league-
vegas-player-stats, render "No data available" in raw HTML because the
table loads via JavaScript after page load - this hits the same backend
API directly instead of scraping a page that has nothing in it server-side).

This is one of three NBA.com/nba_api scrapers, now the PRIMARY data
pipeline for this project (previously RealGM/ESPN were primary and this
was a bonus - reversed per direct instruction to make nba_api the main
pipeline for all 60 rookies, not just the couple that had been manually
verified):
  1. fetch_nba_official.py    <- this file: season stats (LeagueDashPlayerStats)
  2. fetch_nba_shotchart.py   <- shot locations (ShotChartDetail)
  3. fetch_nba_headshots.py   <- downloads actual headshot image files (not just URLs)

Uses `nba_api` to call LeagueDashPlayerStats with SeasonType="Summer
League" - one bulk call returns every player across the whole Summer
League at once, which is filtered down to all 60 tracked rookies by name.

This script also captures each matched rookie's NBA.com PLAYER_ID from the
same response and writes it into data/rookies.json's `nba_player_id`
field - fetch_nba_headshots.py and fetch_nba_shotchart.py both need this ID
and should be run after this script.

Writes to data/raw/rookie_nba_official_stats.csv - one row per rookie, as
PER-GAME AVERAGES (games played, PTS/REB/AST/STL/BLK/FGM/FGA/3PM/3PA/FTM/
FTA/TOV/PF per game). Game Score and True Shooting % are both LINEAR
functions of the underlying box score stats, so computing them from
per-game averages gives the exact same result as averaging individual
per-game values would.

IMPORTANT CAVEATS - read before trusting this blindly:
- This could not be tested against the live stats.nba.com API from the
  sandbox that built it (network restricted to package registries only) -
  the first real run is the actual test.
- The exact `season` string stats.nba.com expects for Summer League data is
  a real uncertainty - it's set here to the season that FOLLOWS Summer
  League (e.g. "2026-27" for the summer before the 2026-27 season), which
  matches common nba_api usage, but verify this against the first live
  run's output before trusting it.
- stats.nba.com is known to rate-limit/reject requests without realistic
  browser-like headers, and has been reported to block requests from some
  cloud/datacenter IP ranges. `nba_api` sets reasonable default headers,
  but if every request times out or 403s in GitHub Actions specifically,
  that's the likely cause - there's no clean fix for this from a public
  Action beyond retrying or running from a different network.
- RealGM (fetch_realgm.py) and ESPN (fetch_espn_shots.py,
  fetch_espn_headshots.py) remain in the pipeline as fallbacks for any
  rookie this doesn't cover.

Usage:
    python scripts/fetch_nba_official.py
    python scripts/fetch_nba_official.py --season 2026-27

Designed to run unattended on a schedule (see .github/workflows/update_data.yml).
"""
import argparse
import csv
import json
import os
import re
import time

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
ROOKIES_PATH = os.path.join(BASE_DIR, "data", "rookies.json")
OUTPUT_PATH = os.path.join(RAW_DIR, "rookie_nba_official_stats.csv")

OUTPUT_COLUMNS = [
    "player", "games", "min_pg", "pts_pg", "oreb_pg", "dreb_pg", "reb_pg",
    "ast_pg", "stl_pg", "blk_pg", "fgm_pg", "fga_pg", "tpm_pg", "tpa_pg",
    "ftm_pg", "fta_pg", "tov_pg", "pf_pg",
]


def normalize_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"\b(jr\.?|sr\.?|ii|iii|iv)\b", "", name)
    name = re.sub(r"[^a-z\s]", "", name)
    return " ".join(name.split())


def load_rookies() -> list:
    with open(ROOKIES_PATH) as f:
        return json.load(f)


def save_rookies(rookies: list) -> None:
    with open(ROOKIES_PATH, "w") as f:
        json.dump(rookies, f, indent=2)


def fetch_league_stats(season: str):
    """Returns nba_api's LeagueDashPlayerStats result as a pandas DataFrame,
    or None if the call fails (network issue, rate limit, etc)."""
    try:
        from nba_api.stats.endpoints import leaguedashplayerstats
    except ImportError:
        print("[error] nba_api not installed. Run: pip install -r requirements.txt")
        return None

    try:
        resp = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            season_type_all_star="Summer League",
            per_mode_detailed="PerGame",
        )
        return resp.get_data_frames()[0]
    except Exception as e:
        print(f"[error] LeagueDashPlayerStats call failed: {e}")
        return None


def extract_rookie_rows(df, rookies: list) -> list:
    rows = []
    name_col = "PLAYER_NAME" if "PLAYER_NAME" in df.columns else None
    if name_col is None:
        print("[error] Unexpected response shape - no PLAYER_NAME column found.")
        return rows

    df["_norm_name"] = df[name_col].apply(normalize_name)
    nba_ids_by_name = {}

    for rookie in rookies:
        target = normalize_name(rookie["name"])
        match = df[df["_norm_name"] == target]
        if match.empty:
            print(f"  {rookie['name']}: not found in this response")
            continue

        r = match.iloc[0]
        nba_player_id = r.get("PLAYER_ID")
        if nba_player_id is not None:
            nba_ids_by_name[rookie["name"]] = str(int(nba_player_id))

        rows.append({
            "player": rookie["name"],
            "games": int(r.get("GP", 0)),
            "min_pg": round(float(r.get("MIN", 0)), 1),
            "pts_pg": round(float(r.get("PTS", 0)), 1),
            "oreb_pg": round(float(r.get("OREB", 0)), 1),
            "dreb_pg": round(float(r.get("DREB", 0)), 1),
            "reb_pg": round(float(r.get("REB", 0)), 1),
            "ast_pg": round(float(r.get("AST", 0)), 1),
            "stl_pg": round(float(r.get("STL", 0)), 1),
            "blk_pg": round(float(r.get("BLK", 0)), 1),
            "fgm_pg": round(float(r.get("FGM", 0)), 1),
            "fga_pg": round(float(r.get("FGA", 0)), 1),
            "tpm_pg": round(float(r.get("FG3M", 0)), 1),
            "tpa_pg": round(float(r.get("FG3A", 0)), 1),
            "ftm_pg": round(float(r.get("FTM", 0)), 1),
            "fta_pg": round(float(r.get("FTA", 0)), 1),
            "tov_pg": round(float(r.get("TOV", 0)), 1),
            "pf_pg": round(float(r.get("PF", 0)), 1),
        })
        print(f"  {rookie['name']}: {rows[-1]['games']} GP, {rows[-1]['pts_pg']} PPG")
    return rows, nba_ids_by_name


def update_rookies_with_nba_ids(rookies: list, nba_ids_by_name: dict) -> bool:
    """Writes nba_player_id back into rookies.json for any rookie this run
    found an ID for - fetch_nba_headshots.py and fetch_nba_shotchart.py both
    read this field. Returns True if anything changed."""
    changed = False
    for rookie in rookies:
        nba_id = nba_ids_by_name.get(rookie["name"])
        if not nba_id:
            continue
        if rookie.get("nba_player_id") != nba_id:
            rookie["nba_player_id"] = nba_id
            changed = True
    return changed


def write_rows(rows: list) -> None:
    if not rows:
        return
    os.makedirs(RAW_DIR, exist_ok=True)
    # Overwrite each run (this is a season-to-date snapshot, not append-only
    # game log data, so re-fetching just replaces old totals with new ones).
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2026-27",
                         help="Season string stats.nba.com expects for this "
                              "Summer League (default 2026-27 - VERIFY on first live run)")
    args = parser.parse_args()

    rookies = load_rookies()

    print(f"Fetching official NBA Summer League stats (season={args.season})...")
    df = fetch_league_stats(args.season)
    if df is None or df.empty:
        print("No data returned - either the season string is wrong, "
              "stats.nba.com rejected the request, or Summer League "
              "hasn't started/isn't tagged as expected. See this script's "
              "docstring for troubleshooting.")
        return

    print(f"Got {len(df)} total player rows from the league-wide response. Matching to our 60 rookies...")
    rows, nba_ids_by_name = extract_rookie_rows(df, rookies)
    write_rows(rows)

    if update_rookies_with_nba_ids(rookies, nba_ids_by_name):
        save_rookies(rookies)
        print(f"Updated rookies.json with {len(nba_ids_by_name)} nba.com player ID(s).")

    print(f"\nDone. Wrote {len(rows)} rookie row(s) -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
