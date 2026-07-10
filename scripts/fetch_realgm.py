"""
SCRAPER 1 of 3: Stats pipeline - RealGM box scores for all 60 rookies.

This is one of three independent, single-purpose scrapers:
  1. fetch_realgm.py         <- this file: box-score stats (RealGM)
  2. fetch_espn_shots.py     <- shot chart locations (ESPN)
  3. fetch_espn_headshots.py <- profile photos (ESPN)
Each writes to its own file and tracks its own dedup state, so a failure in
one never affects the others. Run all three, then build_dataset.py to merge.

Writes to data/raw/rookie_boxscores.csv: one row per game per rookie, full
box score (minutes, both rebound types, steals, blocks, turnovers, fouls -
not just points/rebounds/assists), which is what makes the advanced ROY
formula (Game Score, True Shooting %) in app/roy_score.py possible at all.

IMPORTANT CAVEATS - read before trusting this blindly:
- RealGM has bot detection (CrowdSec). A captcha challenge page looks
  nothing like a game-log table, so this script explicitly checks for it
  and skips that player with a clear warning rather than silently parsing
  garbage. If every player comes back "blocked by bot detection" on a run,
  that's RealGM rate-limiting the request pattern, not a parsing bug -
  there is no clean automated fix for a captcha from a script or GitHub
  Action; consider spacing out requests further or running less often.
- RealGM is unofficial/unaffiliated with the NBA; its page layout could
  change without notice. The table-finder matches header text ("PTS",
  "FGM", etc.) rather than a hardcoded position, which should survive minor
  layout tweaks but not a full redesign.
- This could not be tested against the live RealGM site from the sandbox
  that built it (network restricted to package registries only) - it was
  validated against a synthetic HTML fixture built from the real page
  structure, but the first live run is the actual test.
- Game dates before a team's Summer League site has started will correctly
  yield zero rows - that's accurate, not a bug.

Usage:
    python scripts/fetch_realgm.py
    python scripts/fetch_realgm.py --player "Darryn Peterson"   # single player, for testing
    python scripts/fetch_realgm.py --delay 3                     # seconds between requests (default 2)

Designed to run unattended on a schedule (see .github/workflows/update_data.yml).
"""
import argparse
import csv
import json
import os
import time

import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
ROOKIES_PATH = os.path.join(BASE_DIR, "data", "rookies.json")
STATE_PATH = os.path.join(BASE_DIR, "data", "processed_realgm_games.json")
BOXSCORE_OUTPUT_PATH = os.path.join(RAW_DIR, "rookie_boxscores.csv")

BOXSCORE_CSV_COLUMNS = [
    "player", "game_date", "opponent", "boxscore_url", "min", "pts",
    "fgm", "fga", "tpm", "tpa", "ftm", "fta",
    "orb", "drb", "reb", "ast", "stl", "blk", "tov", "pf",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; rookie-tracker/1.0; +personal project)"
})

# Maps RealGM's game-log table headers to our column names.
HEADER_MAP = {
    "Date": "date", "Team": "team", "Opponent": "opponent",
    "MIN": "min", "PTS": "pts", "FGM": "fgm", "FGA": "fga",
    "3PM": "tpm", "3PA": "tpa", "FTM": "ftm", "FTA": "fta",
    "ORB": "orb", "DRB": "drb", "REB": "reb", "AST": "ast",
    "STL": "stl", "BLK": "blk", "TOV": "tov", "PF": "pf",
}

# Telltale strings on RealGM's bot-detection challenge page - if any of these
# appear, treat the response as blocked rather than trying to parse it.
CAPTCHA_MARKERS = ["CrowdSec", "robot like traffic", "captcha", "Captcha"]


def load_rookies() -> list:
    with open(ROOKIES_PATH) as f:
        return json.load(f)


def load_state() -> set:
    if not os.path.exists(STATE_PATH):
        return set()
    with open(STATE_PATH) as f:
        return set(json.load(f).get("processed_boxscore_urls", []))


def save_state(processed: set) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump({"processed_boxscore_urls": sorted(processed)}, f, indent=2)


def is_blocked(html_text: str) -> bool:
    return any(marker in html_text for marker in CAPTCHA_MARKERS)


def fetch_gamelog_table(soup: BeautifulSoup):
    """Find the game log table by matching its header row against HEADER_MAP keys."""
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if not header_row:
            continue
        headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
        matches = sum(1 for h in headers if h in HEADER_MAP)
        if matches >= 8:  # enough overlap with expected columns to be confident
            return table, headers
    return None, None


def parse_games(table, headers) -> list:
    col_map = {}
    for i, h in enumerate(headers):
        if h in HEADER_MAP:
            col_map[HEADER_MAP[h]] = i

    games = []
    rows = table.find_all("tr")[1:]  # skip header
    for row in rows:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        cell_texts = [c.get_text(strip=True) for c in cells]
        if not cell_texts or cell_texts[0] in ("Averages", "Totals", ""):
            continue
        if len(cell_texts) < len(headers):
            continue  # malformed/short row, skip defensively

        def get(col, default=""):
            idx = col_map.get(col)
            if idx is None or idx >= len(cell_texts):
                return default
            return cell_texts[idx]

        link = None
        date_cell_idx = col_map.get("date")
        if date_cell_idx is not None and date_cell_idx < len(cells):
            a_tag = cells[date_cell_idx].find("a")
            if a_tag and a_tag.get("href"):
                link = a_tag["href"]
                if link.startswith("/"):
                    link = "https://basketball.realgm.com" + link

        if not link:
            continue  # can't dedupe safely without a unique game URL, skip

        def to_int(s):
            try:
                return int(s)
            except (ValueError, TypeError):
                return 0

        games.append({
            "boxscore_url": link,
            "game_date": get("date"),
            "opponent": get("opponent"),
            "min": get("min"),
            "pts": to_int(get("pts")),
            "fgm": to_int(get("fgm")), "fga": to_int(get("fga")),
            "tpm": to_int(get("tpm")), "tpa": to_int(get("tpa")),
            "ftm": to_int(get("ftm")), "fta": to_int(get("fta")),
            "orb": to_int(get("orb")), "drb": to_int(get("drb")),
            "reb": to_int(get("reb")), "ast": to_int(get("ast")),
            "stl": to_int(get("stl")), "blk": to_int(get("blk")),
            "tov": to_int(get("tov")), "pf": to_int(get("pf")),
        })
    return games


def append_rows(rows: list) -> None:
    if not rows:
        return
    os.makedirs(RAW_DIR, exist_ok=True)
    file_exists = os.path.exists(BOXSCORE_OUTPUT_PATH)
    with open(BOXSCORE_OUTPUT_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BOXSCORE_CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fetch_one_rookie(rookie: dict, processed: set, delay: float) -> int:
    name = rookie["name"]
    slug = rookie["realgm_slug"]
    rid = rookie["realgm_id"]
    url = f"https://basketball.realgm.com/player/{slug}/GameLogs/{rid}"
    print(f"\n{name}: fetching {url}")

    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [error] Could not fetch page: {e}")
        return 0

    if is_blocked(resp.text):
        print("  [blocked] RealGM's bot detection (CrowdSec) served a challenge "
              "page instead of real content. Skipping this player - this is not "
              "a parsing bug, see this script's docstring.")
        return 0

    soup = BeautifulSoup(resp.text, "html.parser")
    table, headers = fetch_gamelog_table(soup)
    if table is None:
        print("  [warn] Could not find a game log table on this page "
              "(rookie may have zero games yet, or RealGM's layout changed).")
        return 0

    games = parse_games(table, headers)
    new_rows = []
    for g in games:
        if g["boxscore_url"] in processed:
            continue
        new_rows.append({"player": name, **g})
        processed.add(g["boxscore_url"])

    if new_rows:
        append_rows(new_rows)
        print(f"  Added {len(new_rows)} new game(s).")
    else:
        print("  No new games.")

    time.sleep(delay)  # be polite between requests, reduces bot-detection risk
    return len(new_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--player", default=None,
                         help="Only fetch this one rookie (exact name match), for testing")
    parser.add_argument("--delay", type=float, default=2.0,
                         help="Seconds to wait between requests (default 2.0)")
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
        total_new += fetch_one_rookie(rookie, processed, args.delay)

    save_state(processed)
    print(f"\nDone. {total_new} new box score rows this run.")


if __name__ == "__main__":
    main()
