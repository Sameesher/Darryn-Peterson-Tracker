"""
Fully automated data ingestion for ALL tracked rookies (see data/rookies.json),
via ESPN's (unofficial) JSON API. Replaces the single-player
fetch_espn_summer_league.py now that the project tracks 10 rookies instead of one.

For each rookie, this script:
1. Scans their NBA team's recent Summer League scoreboard for finished games
2. Pulls the play-by-play for any game not already processed
3. Extracts BOTH:
   a. Shot-by-shot data (for the hex shot chart) -> data/raw/rookie_shots.csv
   b. A per-game box score tally: points, rebounds, assists -> data/raw/rookie_boxscores.csv
      (rebounds/assists aren't visible in shot-chart data alone, but the ROY
      ranking formula needs them)

IMPORTANT CAVEATS (same as the original single-player version, now doubled
across 10 players - read before trusting this blindly):
- ESPN does not publish an official API; this could change/break without notice.
- Different rookies play in different Summer League "sites" (Salt Lake City,
  Las Vegas, California Classic). See data/rookies.json's summer_league_slug
  field per player - the Las Vegas/California Classic assignments are
  reasonable guesses made before those events started and may need
  correcting once real schedules are confirmed.
- Shot locations fall back to distance/type text-parsing when ESPN doesn't
  expose real coordinates for a play - see `location_source` column.
- Assists are credited to a tracked rookie whenever a play's text contains
  "(<rookie name> assists)", regardless of who took the shot. Rebounds are
  counted from lines like "<rookie name> defensive/offensive rebound".
  Both are simple text-pattern matches against ESPN's play descriptions, not
  official box score fields - double check against a real box score early on.

Usage:
    python scripts/fetch_espn_rookies.py
    python scripts/fetch_espn_rookies.py --days-back 5

Designed to run unattended on a schedule (see .github/workflows/update_data.yml).
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
STATE_PATH = os.path.join(BASE_DIR, "data", "processed_games.json")
SHOTS_OUTPUT_PATH = os.path.join(RAW_DIR, "rookie_shots.csv")
BOXSCORE_OUTPUT_PATH = os.path.join(RAW_DIR, "rookie_boxscores.csv")

SHOT_CSV_COLUMNS = [
    "player", "game_date", "opponent", "shot_made", "shot_type", "shot_zone",
    "shot_x", "shot_y", "assisted", "possession_type", "location_source",
]
BOXSCORE_CSV_COLUMNS = [
    "player", "game_date", "opponent", "points", "rebounds", "assists",
    "fg_made", "fg_attempts", "three_made", "three_attempts", "ft_made", "ft_attempts",
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
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
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


def extract_shots_and_boxscore(plays: list, player_name: str, game_date: str, opponent: str):
    shot_rows = []
    rebounds = 0
    assists = 0
    points = 0
    fg_made = fg_attempts = 0
    three_made = three_attempts = 0
    ft_made = ft_attempts = 0

    for play in plays:
        text = play.get("text", "")
        if not text:
            continue

        # Assist credit can appear on ANY play, not just ones the rookie shot
        if f"({player_name} assists)" in text:
            assists += 1

        if not text.startswith(player_name):
            continue

        if "rebound" in text.lower():
            rebounds += 1
            continue

        if "makes" not in text.lower() and "misses" not in text.lower():
            continue  # steals, blocks, turnovers, etc.

        shot_made = 1 if "makes" in text.lower() else 0
        assisted = "assist" in text.lower()
        is_three = "three point" in text.lower()

        if "free throw" in text.lower():
            ft_attempts += 1
            if shot_made:
                ft_made += 1
                points += 1
            shot_rows.append({
                "player": player_name, "game_date": game_date, "opponent": opponent,
                "shot_made": shot_made, "shot_type": "FT", "shot_zone": "",
                "shot_x": "", "shot_y": "", "assisted": 0, "possession_type": "",
                "location_source": "espn_text",
            })
            continue

        fg_attempts += 1
        if is_three:
            three_attempts += 1
        if shot_made:
            fg_made += 1
            points += 3 if is_three else 2
            if is_three:
                three_made += 1

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

    boxscore_row = {
        "player": player_name, "game_date": game_date, "opponent": opponent,
        "points": points, "rebounds": rebounds, "assists": assists,
        "fg_made": fg_made, "fg_attempts": fg_attempts,
        "three_made": three_made, "three_attempts": three_attempts,
        "ft_made": ft_made, "ft_attempts": ft_attempts,
    }
    return shot_rows, boxscore_row


def fetch_game_summary(league: str, event_id: str) -> dict:
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/summary"
    resp = session.get(url, params={"event": event_id}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def append_rows(path: str, columns: list, rows: list) -> None:
    if not rows:
        return
    os.makedirs(RAW_DIR, exist_ok=True)
    file_exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
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

    total_new_shots = 0
    total_new_boxscores = 0

    for rookie in rookies:
        name = rookie["name"]
        league = rookie["summer_league_slug"]
        print(f"\n{name} ({rookie['team']}, {league}):")

        games = find_recent_team_games(league, rookie["team_name_matches"], args.days_back)
        print(f"  Found {len(games)} completed game(s) in the last {args.days_back} day(s)")

        for game in games:
            key = f"{name}|{game['event_id']}"
            if key in processed:
                continue
            print(f"  Processing new game {game['event_id']} ({game['date']} vs {game['opponent']})...")
            try:
                summary = fetch_game_summary(league, game["event_id"])
            except Exception as e:
                print(f"    [error] Could not fetch summary: {e}")
                continue

            plays = summary.get("plays", [])
            shot_rows, boxscore_row = extract_shots_and_boxscore(
                plays, name, game["date"], game["opponent"]
            )

            if shot_rows:
                append_rows(SHOTS_OUTPUT_PATH, SHOT_CSV_COLUMNS, shot_rows)
                total_new_shots += len(shot_rows)
            append_rows(BOXSCORE_OUTPUT_PATH, BOXSCORE_CSV_COLUMNS, [boxscore_row])
            total_new_boxscores += 1
            print(f"    Added {len(shot_rows)} shot row(s), "
                  f"{boxscore_row['points']} pts / {boxscore_row['rebounds']} reb / "
                  f"{boxscore_row['assists']} ast")

            processed.add(key)

    save_state(processed)
    print(f"\nDone. {total_new_shots} new shot rows, {total_new_boxscores} new box score rows this run.")


if __name__ == "__main__":
    main()
