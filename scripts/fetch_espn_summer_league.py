"""
Fully automated Summer League shot data ingestion via ESPN's (unofficial) JSON API.

Unlike fetch_summer_league.py (manual CSV entry), this script needs no human
input: it discovers recently completed Jazz Summer League games on its own,
pulls the play-by-play for each, extracts Darryn Peterson's shot attempts,
and appends them to data/raw/summer_league_shots.csv — skipping any game
already processed (tracked in data/processed_games.json).

IMPORTANT CAVEATS (read before trusting this blindly):
- ESPN does not publish an official API. This uses the same undocumented
  JSON endpoints their website calls client-side. It could change or break
  without notice — if a scheduled run starts silently producing 0 new shots
  for several days in a row while games are happening, that's the likely cause.
- Summer League box scores are less richly tracked than regular-season NBA.
  If ESPN's play-by-play includes real shot coordinates for these games, this
  script uses them. If it doesn't, it falls back to estimating court position
  from the shot's distance + type (e.g. "17-foot pullup jump shot"), the same
  approximation used for the first manually-entered game. Either way, the
  `location_source` column in the output tells you which happened.
- Free throws are excluded (no meaningful court location).
- possession_type is inferred from keywords in ESPN's play text (e.g.
  "pullup" -> pull_up, assisted layup/dunk -> transition). It's a reasonable
  guess, not official tracking data.

Usage:
    python scripts/fetch_espn_summer_league.py
    python scripts/fetch_espn_summer_league.py --days-back 5 --league nba-summer-utah

This is designed to run unattended on a schedule (see .github/workflows/
update_data.yml) - no arguments are required for normal nightly use.
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys

import requests

PLAYER_NAME = "Darryn Peterson"
TEAM_NAME_MATCHES = ["Utah Jazz", "Jazz"]  # how the team shows up in ESPN's JSON

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
STATE_PATH = os.path.join(BASE_DIR, "data", "processed_games.json")
OUTPUT_PATH = os.path.join(RAW_DIR, "summer_league_shots.csv")

CSV_COLUMNS = [
    "game_date", "opponent", "shot_made", "shot_type", "shot_zone",
    "shot_x", "shot_y", "assisted", "possession_type", "location_source",
]

HOOP_X, HOOP_Y = 0.0, 5.25  # feet, standard half-court hoop position

session = requests.Session()
session.headers.update({"User-Agent": "darryn-peterson-tracker/1.0 (personal project)"})


def load_state() -> set:
    if not os.path.exists(STATE_PATH):
        return set()
    with open(STATE_PATH) as f:
        return set(json.load(f).get("processed_event_ids", []))


def save_state(processed_ids: set) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump({"processed_event_ids": sorted(processed_ids)}, f, indent=2)


def find_recent_jazz_games(league: str, days_back: int) -> list:
    """Scan the last `days_back` days of the scoreboard for completed Jazz games."""
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
            print(f"  [warn] scoreboard fetch failed for {date_str}: {e}")
            continue

        for event in data.get("events", []):
            status = event.get("status", {}).get("type", {}).get("name", "")
            if status != "STATUS_FINAL":
                continue
            competitors = event.get("competitions", [{}])[0].get("competitors", [])
            team_names = [c.get("team", {}).get("displayName", "") for c in competitors]
            if any(t in TEAM_NAME_MATCHES for t in team_names):
                opponent = next(
                    (t for t in team_names if t not in TEAM_NAME_MATCHES), "Unknown"
                )
                found.append({
                    "event_id": event.get("id"),
                    "date": event.get("date", "")[:10],
                    "opponent": opponent,
                })
    # de-dupe by event_id
    seen = {}
    for g in found:
        seen[g["event_id"]] = g
    return list(seen.values())


def estimate_location_from_text(text: str):
    """Fallback: guess court position from a play's text description."""
    is_three = "three point" in text.lower()
    dist_match = re.search(r"(\d+)-foot", text)
    if dist_match:
        distance = float(dist_match.group(1))
    elif is_three:
        distance = 25.0
    elif re.search(r"layup|dunk|hook", text, re.IGNORECASE):
        distance = 2.0  # driving layups/dunks/hooks are near-rim even without a footage tag
    else:
        distance = 10.0
    if "heave" in text.lower():
        distance = 45.0

    # crude alternating angle so shots don't all stack on one line
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


def extract_player_shots(game_summary: dict, game_date: str, opponent: str) -> list:
    plays = game_summary.get("plays", [])
    rows = []
    for play in plays:
        text = play.get("text", "")
        if not text.startswith(PLAYER_NAME):
            continue
        if "free throw" in text.lower():
            continue  # no court location for free throws
        if "makes" not in text.lower() and "misses" not in text.lower():
            continue  # rebounds, steals, blocks, turnovers, etc.

        shot_made = 1 if "makes" in text.lower() else 0
        assisted = "assist" in text.lower()

        # Prefer real coordinates if ESPN provides them for this play
        coord = play.get("coordinate")
        if coord and "x" in coord and "y" in coord:
            # ESPN's raw coordinate system varies by sport/feed; this assumes
            # a 0-50 (width) x 0-94 (length) full-court grid halved to one end.
            # Verify against a known play before trusting this at scale.
            x = round(coord["x"] - 25, 1)
            y = round(coord["y"], 1)
            is_three = "three point" in text.lower()
            shot_type = "3PT" if is_three else "2PT"
            zone = "Above the Break 3" if is_three else "Mid-Range"
            source = "espn_coordinate"
        else:
            shot_type, zone, x, y = estimate_location_from_text(text)
            source = "estimated_from_text"

        rows.append({
            "game_date": game_date,
            "opponent": opponent,
            "shot_made": shot_made,
            "shot_type": shot_type,
            "shot_zone": zone,
            "shot_x": x,
            "shot_y": y,
            "assisted": int(assisted),
            "possession_type": infer_possession_type(text, assisted),
            "location_source": source,
        })
    return rows


def fetch_game_summary(league: str, event_id: str) -> dict:
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/summary"
    resp = session.get(url, params={"event": event_id}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def append_rows_to_csv(rows: list) -> None:
    import csv

    os.makedirs(RAW_DIR, exist_ok=True)
    file_exists = os.path.exists(OUTPUT_PATH)
    with open(OUTPUT_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", default="nba-summer-utah",
                         help="ESPN league slug, e.g. nba-summer-utah, nba-summer-las-vegas")
    parser.add_argument("--days-back", type=int, default=3,
                         help="How many days of scoreboard history to scan each run")
    args = parser.parse_args()

    processed = load_state()
    games = find_recent_jazz_games(args.league, args.days_back)
    print(f"Found {len(games)} completed Jazz game(s) in the last {args.days_back} day(s)")

    new_rows_total = 0
    for game in games:
        event_id = game["event_id"]
        if event_id in processed:
            continue
        print(f"  Processing new game {event_id} ({game['date']} vs {game['opponent']})...")
        try:
            summary = fetch_game_summary(args.league, event_id)
        except Exception as e:
            print(f"    [error] Could not fetch summary for {event_id}: {e}")
            continue

        rows = extract_player_shots(summary, game["date"], game["opponent"])
        if not rows:
            print(f"    No {PLAYER_NAME} shot attempts found (maybe he didn't play, "
                  f"or ESPN's play text format differs from what this script expects).")
        else:
            append_rows_to_csv(rows)
            print(f"    Added {len(rows)} shot(s).")
            new_rows_total += len(rows)

        processed.add(event_id)

    save_state(processed)
    print(f"Done. {new_rows_total} new shot rows added this run.")


if __name__ == "__main__":
    main()
