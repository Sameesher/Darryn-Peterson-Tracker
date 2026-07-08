"""
Shot-location data ingestion via ESPN's (unofficial) JSON API - a SEPARATE
pipeline from RealGM's, which handles the season-stats/ROY-ranking side.

Why two pipelines instead of one: RealGM's box scores are more complete and
accurate for stats (full box score, real photos), but RealGM does not
expose shot x/y coordinates anywhere. ESPN's play-by-play sometimes does
(and always has distance/type text to fall back on), so shot charts stay on
ESPN while everything else - points, rebounds, assists, rankings - comes
from RealGM via fetch_realgm.py. The two pipelines are independent and
intentionally don't overlap: this script writes ONLY to
data/raw/rookie_shots.csv and never touches rookie_boxscores.csv.

Each rookie needs an "espn_team_name_matches" and "summer_league_slugs"
entry in data/rookies.json for this to find their games (see that file).

IMPORTANT CAVEATS (same as before - read before trusting this blindly):
- ESPN does not publish an official API; this could change/break without notice.
- Different rookies play in different Summer League "sites" (Salt Lake City,
  Las Vegas, California Classic) - `summer_league_slugs` in rookies.json is
  a list per player to cover teams playing at more than one site.
- Shot locations fall back to distance/type text-parsing when ESPN doesn't
  expose real coordinates for a play - see `location_source` column.
- Free throws are captured too (shot_type="FT", no location) purely so this
  pipeline's data stays self-consistent, but FT%/points-from-FT are actually
  computed from RealGM's box scores now, not from this file.

Usage:
    python scripts/fetch_espn_shots.py
    python scripts/fetch_espn_shots.py --days-back 5

Designed to run unattended on a schedule (see .github/workflows/update_data.yml),
alongside (not instead of) fetch_realgm.py.
"""
import argparse
import csv
import datetime as dt
import json
import math
import os
import re

import requests

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
ROOKIES_PATH = os.path.join(BASE_DIR, "data", "rookies.json")
STATE_PATH = os.path.join(BASE_DIR, "data", "processed_espn_shot_games.json")
SHOTS_OUTPUT_PATH = os.path.join(RAW_DIR, "rookie_shots.csv")

SHOT_CSV_COLUMNS = [
    "player", "game_date", "opponent", "shot_made", "shot_type", "shot_zone",
    "shot_x", "shot_y", "assisted", "possession_type", "location_source",
]

HOOP_X, HOOP_Y = 0.0, 5.25

session = requests.Session()
session.headers.update({"User-Agent": "rookie-tracker/1.0 (personal project)"})


def load_rookies() -> list:
    with open(ROOKIES_PATH) as f:
        return json.load(f)


def load_state() -> set:
    if not os.path.exists(STATE_PATH):
        return set()
    with open(STATE_PATH) as f:
        return set(json.load(f).get("processed_keys", []))


def save_state(processed_keys: set) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump({"processed_keys": sorted(processed_keys)}, f, indent=2)


def find_recent_team_games(league: str, team_name_matches: list, days_back: int) -> list:
    found = []
    today = dt.date.today()
    for delta in range(days_back + 1):
        date_str = (today - dt.timedelta(days=delta)).strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard"
        try:
            resp = session.get(url, params={"dates": date_str}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"    [warn] scoreboard fetch failed for {league} {date_str}: {e}")
            continue

        for event in data.get("events", []):
            status = event.get("status", {}).get("type", {}).get("name", "")
            if status != "STATUS_FINAL":
                continue
            competitors = event.get("competitions", [{}])[0].get("competitors", [])
            names = [c.get("team", {}).get("displayName", "") for c in competitors]
            if any(t in team_name_matches for t in names):
                opponent = next((t for t in names if t not in team_name_matches), "Unknown")
                found.append({"event_id": event.get("id"), "date": event.get("date", "")[:10],
                              "opponent": opponent})
    seen = {}
    for g in found:
        seen[g["event_id"]] = g
    return list(seen.values())


def estimate_location_from_text(text: str):
    is_three = "three point" in text.lower()
    dist_match = re.search(r"(\d+)-foot", text)
    if dist_match:
        distance = float(dist_match.group(1))
    elif is_three:
        distance = 25.0
    elif re.search(r"layup|dunk|hook", text, re.IGNORECASE):
        distance = 2.0
    else:
        distance = 10.0
    if "heave" in text.lower():
        distance = 45.0

    angle_options = [90, 60, 120, 45, 135, 20, 160]
    angle = angle_options[hash(text) % len(angle_options)]
    theta = math.radians(angle)
    x = round(HOOP_X + distance * math.cos(theta), 1)
    y = round(HOOP_Y + distance * math.sin(theta), 1)

    if distance <= 4:
        zone = "Restricted Area"
    elif distance <= 19:
        zone = "Mid-Range"
    elif is_three:
        zone = "Above the Break 3"
    else:
        zone = "Mid-Range"

    shot_type = "3PT" if is_three else "2PT"
    return shot_type, zone, x, y


def infer_possession_type(text: str, assisted: bool) -> str:
    t = text.lower()
    if "pullup" in t or "pull-up" in t or "step back" in t or "stepback" in t:
        return "pull_up"
    if "post" in t or "hook" in t or "turnaround" in t:
        return "post_up"
    if ("layup" in t or "dunk" in t) and assisted:
        return "transition"
    if "layup" in t or "dunk" in t or "floating" in t:
        return "iso"
    if assisted:
        return "spot_up"
    return "iso"


def extract_shots(plays: list, player_name: str, game_date: str, opponent: str) -> list:
    shot_rows = []
    for play in plays:
        text = play.get("text", "")
        if not text.startswith(player_name):
            continue
        if "makes" not in text.lower() and "misses" not in text.lower():
            continue

        shot_made = 1 if "makes" in text.lower() else 0
        assisted = "assist" in text.lower()

        if "free throw" in text.lower():
            shot_rows.append({
                "player": player_name, "game_date": game_date, "opponent": opponent,
                "shot_made": shot_made, "shot_type": "FT", "shot_zone": "",
                "shot_x": "", "shot_y": "", "assisted": 0, "possession_type": "",
                "location_source": "espn_text",
            })
            continue

        is_three = "three point" in text.lower()
        coord = play.get("coordinate")
        if coord and "x" in coord and "y" in coord:
            x = round(coord["x"] - 25, 1)
            y = round(coord["y"], 1)
            shot_type = "3PT" if is_three else "2PT"
            zone = "Above the Break 3" if is_three else "Mid-Range"
            source = "espn_coordinate"
        else:
            shot_type, zone, x, y = estimate_location_from_text(text)
            source = "estimated_from_text"

        shot_rows.append({
            "player": player_name, "game_date": game_date, "opponent": opponent,
            "shot_made": shot_made, "shot_type": shot_type, "shot_zone": zone,
            "shot_x": x, "shot_y": y, "assisted": int(assisted),
            "possession_type": infer_possession_type(text, assisted),
            "location_source": source,
        })
    return shot_rows


def fetch_game_summary(league: str, event_id: str) -> dict:
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/summary"
    resp = session.get(url, params={"event": event_id}, timeout=20)
    resp.raise_for_status()
    return resp.json()


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-back", type=int, default=3)
    args = parser.parse_args()

    rookies = load_rookies()
    processed = load_state()
    total_new = 0

    for rookie in rookies:
        name = rookie["name"]
        leagues = rookie.get("summer_league_slugs")
        team_matches = rookie.get("espn_team_name_matches")
        if not leagues or not team_matches:
            print(f"\n{name}: skipped (no summer_league_slugs/espn_team_name_matches "
                  f"configured in rookies.json for the ESPN shot pipeline)")
            continue

        print(f"\n{name} ({rookie['team']}):")
        games = []
        for league in leagues:
            league_games = find_recent_team_games(league, team_matches, args.days_back)
            for g in league_games:
                g["league"] = league
            games.extend(league_games)
            print(f"  [{league}] found {len(league_games)} completed game(s)")

        seen_ids = set()
        deduped = []
        for g in games:
            if g["event_id"] not in seen_ids:
                seen_ids.add(g["event_id"])
                deduped.append(g)

        for game in deduped:
            key = f"{name}|{game['event_id']}"
            if key in processed:
                continue
            print(f"  Processing new game {game['event_id']} ({game['date']} vs {game['opponent']})...")
            try:
                summary = fetch_game_summary(game["league"], game["event_id"])
            except Exception as e:
                print(f"    [error] Could not fetch summary: {e}")
                continue

            rows = extract_shots(summary.get("plays", []), name, game["date"], game["opponent"])
            if rows:
                append_rows(rows)
                total_new += len(rows)
                print(f"    Added {len(rows)} shot row(s).")
            else:
                print("    No shot rows found for this player in this game.")

            processed.add(key)

    save_state(processed)
    print(f"\nDone. {total_new} new shot rows this run.")


if __name__ == "__main__":
    main()
