"""
Fully automated data ingestion from RealGM (basketball.realgm.com) for all
10 tracked rookies. This is the STATS pipeline only - box scores, points,
rebounds, assists, etc. Player headshots come from ESPN (better image
quality), configured directly in data/rookies.json - this script does not
touch headshot_url at all.

IMPORTANT TRADEOFF - read this before wondering where the shot chart went:
RealGM's game logs are box scores only - no shot x/y coordinates. Switching
the *stats* pipeline to RealGM means the interactive hex shot chart has no
new data source going forward. The shot data already collected via the old
ESPN-based approach (Peterson and Acuff's first two games each) is left
in data/raw/rookie_shots.csv as a frozen historical snapshot so those two
charts still render, but nothing new will be added there unless a
shot-location source gets wired back in separately.

IMPORTANT CAVEAT: this could not be tested against the live RealGM site
from the sandbox that built it (network restricted to package registries
only) - the first real run is the actual test. If RealGM changes their
page layout, the table-parsing logic below may need updating - look for
the game log table by matching header text ("PTS", "FGM", "FGA", etc.)
rather than a hardcoded position, which should be reasonably resilient to
minor layout changes but not a full redesign.

Usage:
    python scripts/fetch_realgm.py

Designed to run unattended on a schedule (see .github/workflows/update_data.yml).
"""
import csv
import json
import os
import re

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
session.headers.update({"User-Agent": "rookie-tracker/1.0 (personal project)"})

# Maps RealGM's game-log table headers to our column names. RealGM's header
# row text is matched case-sensitively against these keys.
HEADER_MAP = {
    "Date": "date", "Team": "team", "Opponent": "opponent",
    "MIN": "min", "PTS": "pts", "FGM": "fgm", "FGA": "fga",
    "3PM": "tpm", "3PA": "tpa", "FTM": "ftm", "FTA": "fta",
    "ORB": "orb", "DRB": "drb", "REB": "reb", "AST": "ast",
    "STL": "stl", "BLK": "blk", "TOV": "tov", "PF": "pf",
}


def load_rookies() -> list:
    with open(ROOKIES_PATH) as f:
        return json.load(f)


def save_rookies(rookies: list) -> None:
    with open(ROOKIES_PATH, "w") as f:
        json.dump(rookies, f, indent=2)


def load_state() -> set:
    if not os.path.exists(STATE_PATH):
        return set()
    with open(STATE_PATH) as f:
        return set(json.load(f).get("processed_boxscore_urls", []))


def save_state(processed: set) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump({"processed_boxscore_urls": sorted(processed)}, f, indent=2)


def fetch_photo_url(soup: BeautifulSoup) -> str:
    """RealGM's player photo is an <img> whose src contains '/profiles/photos/'."""
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "/profiles/photos/" in src:
            return src
    return None


def fetch_gamelog_table(soup: BeautifulSoup):
    """Find the game log table by matching its header row against HEADER_MAP keys."""
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if not header_row:
            continue
        headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
        # A real game-log table should contain most of these column headers
        matches = sum(1 for h in headers if h in HEADER_MAP)
        if matches >= 8:  # arbitrary threshold - enough overlap to be confident
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

        # boxscore URL, used as the unique dedup key for this game
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


def main():
    rookies = load_rookies()
    processed = load_state()
    total_new = 0
    rookies_updated = False

    for rookie in rookies:
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
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        table, headers = fetch_gamelog_table(soup)
        if table is None:
            print("  [warn] Could not find a game log table on this page.")
            continue

        games = parse_games(table, headers)
        new_rows = []
        for g in games:
            if g["boxscore_url"] in processed:
                continue
            row = {"player": name, **g}
            new_rows.append(row)
            processed.add(g["boxscore_url"])

        if new_rows:
            append_rows(new_rows)
            total_new += len(new_rows)
            print(f"  Added {len(new_rows)} new game(s).")
        else:
            print("  No new games.")

    if rookies_updated:
        save_rookies(rookies)
    save_state(processed)
    print(f"\nDone. {total_new} new box score rows this run.")


if __name__ == "__main__":
    main()
