"""
SCRAPER 3 of 3: Profile photos - ESPN headshots for all 60 rookies.

This is one of three independent, single-purpose scrapers:
  1. fetch_realgm.py         <- box-score stats (RealGM)
  2. fetch_espn_shots.py     <- shot chart locations (ESPN)
  3. fetch_espn_headshots.py <- this file: profile photos (ESPN)
Each writes to its own file/field and tracks its own state, so a failure in
one never affects the others.

Unlike the other two, this one doesn't need to run often - a player's ESPN
athlete ID and headshot URL are effectively permanent once assigned, so this
only needs to succeed once per player. It writes directly into
data/rookies.json's espn_id/headshot_url fields (does NOT touch anything in
data/raw/ - no game data, no stats).

How it finds a player: ESPN doesn't have simple person-name search that's
reliable to scrape, so this walks the roster instead - fetch the full list
of NBA teams (to map team name -> team ID), then fetch that specific team's
roster (to find the athlete by name) and read their headshot URL directly
off the roster entry. This means a rookie who hasn't been added to their
team's official roster yet (common right after a draft, before contracts
are finalized) will come back not-found until a later run.

IMPORTANT CAVEAT: this could not be tested against the live ESPN API from
the sandbox that built it (network restricted to package registries only) -
the first real run is the actual test. data/rookies.json already has
manually-verified espn_id/headshot_url for the full draft class as of when this was
written, so this script's main value going forward is future rookies added
to the roster, or catching a case where ESPN's ID for someone changes.

Usage:
    python scripts/fetch_espn_headshots.py
    python scripts/fetch_espn_headshots.py --force   # re-check even already-resolved players
    python scripts/fetch_espn_headshots.py --player "AJ Dybantsa"

Designed to run occasionally (see .github/workflows/update_data.yml) - not
worth running on the same tight schedule as the stats/shot scrapers.
"""
import argparse
import json
import os
import re

import requests

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
ROOKIES_PATH = os.path.join(BASE_DIR, "data", "rookies.json")

session = requests.Session()
session.headers.update({"User-Agent": "rookie-tracker/1.0 (personal project)"})


def load_rookies() -> list:
    with open(ROOKIES_PATH) as f:
        return json.load(f)


def save_rookies(rookies: list) -> None:
    with open(ROOKIES_PATH, "w") as f:
        json.dump(rookies, f, indent=2)


def normalize_name(name: str) -> str:
    """Lowercase, strip suffixes (Jr./II/III) and punctuation for fuzzy matching."""
    name = name.lower()
    name = re.sub(r"\b(jr\.?|sr\.?|ii|iii|iv)\b", "", name)
    name = re.sub(r"[^a-z\s]", "", name)
    return " ".join(name.split())


def get_all_teams() -> list:
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    teams = []
    for sport in data.get("sports", []):
        for league in sport.get("leagues", []):
            for team_entry in league.get("teams", []):
                team = team_entry.get("team", {})
                teams.append({"id": team.get("id"), "displayName": team.get("displayName")})
    return teams


def find_team_id(team_name: str, all_teams: list):
    for t in all_teams:
        if t["displayName"] == team_name:
            return t["id"]
    for t in all_teams:
        if team_name.lower() in t["displayName"].lower() or t["displayName"].lower() in team_name.lower():
            return t["id"]
    return None


def get_team_roster(team_id: str) -> list:
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json().get("athletes", [])


def find_player_in_roster(player_name: str, roster: list):
    target = normalize_name(player_name)
    for athlete in roster:
        candidate = athlete.get("fullName") or athlete.get("displayName", "")
        if normalize_name(candidate) == target:
            return athlete
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                         help="Re-check players that already have a headshot_url")
    parser.add_argument("--player", default=None,
                         help="Only resolve this one rookie (exact name match), for testing")
    args = parser.parse_args()

    rookies = load_rookies()
    targets = rookies
    if args.player:
        targets = [r for r in rookies if r["name"] == args.player]
        if not targets:
            print(f"No rookie named '{args.player}' in data/rookies.json")
            return

    print("Fetching NBA team list...")
    try:
        all_teams = get_all_teams()
    except Exception as e:
        print(f"[error] Could not fetch team list: {e}")
        return
    print(f"  Found {len(all_teams)} teams")

    updated = 0
    for rookie in targets:
        if rookie.get("headshot_url") and not args.force:
            print(f"\n{rookie['name']}: already resolved, skipping (use --force to re-check)")
            continue

        print(f"\n{rookie['name']} ({rookie['team']}):")
        team_id = find_team_id(rookie["team"], all_teams)
        if not team_id:
            print(f"  [warn] Could not find ESPN team ID for '{rookie['team']}'")
            continue

        try:
            roster = get_team_roster(team_id)
        except Exception as e:
            print(f"  [error] Could not fetch roster: {e}")
            continue

        athlete = find_player_in_roster(rookie["name"], roster)
        if not athlete:
            print(f"  [info] Not yet on {rookie['team']}'s official ESPN roster "
                  f"(common right after a draft - try again later)")
            continue

        espn_id = str(athlete.get("id"))
        headshot = athlete.get("headshot", {})
        headshot_url = headshot.get("href") or (
            f"https://a.espncdn.com/i/headshots/nba/players/full/{espn_id}.png"
        )

        rookie["espn_id"] = espn_id
        rookie["headshot_url"] = headshot_url
        updated += 1
        print(f"  Resolved -> espn_id={espn_id}")
        print(f"  headshot_url={headshot_url}")

    if updated:
        save_rookies(rookies)
    print(f"\nDone. Resolved/updated {updated} player(s).")


if __name__ == "__main__":
    main()
