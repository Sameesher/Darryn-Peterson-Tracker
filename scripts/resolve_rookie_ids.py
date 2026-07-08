"""
Fills in missing espn_id / headshot_url fields in data/rookies.json by looking
each rookie up on their NBA team's official ESPN roster.

Why this is a separate script: unlike Summer League game data (which changes
constantly), a player's ESPN ID and headshot URL are essentially permanent
once assigned - so this only needs to successfully run once per player, and
the result is committed straight into rookies.json instead of being
re-fetched every time.

IMPORTANT: this could not be tested against the live ESPN API from the
sandbox that built it (network restricted to package registries only) - the
first real run against espn.com is the actual test. If a rookie doesn't show
up on their team's official NBA roster yet (common right after a draft,
before contracts are finalized/rosters updated), this leaves espn_id as null
and the profile page falls back to a placeholder silhouette instead of a
broken image.

Usage:
    python scripts/resolve_rookie_ids.py
"""
import json
import os
import re

import requests

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
ROOKIES_PATH = os.path.join(BASE_DIR, "data", "rookies.json")

session = requests.Session()
session.headers.update({"User-Agent": "rookie-tracker/1.0 (personal project)"})


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
    data = resp.json()
    return data.get("athletes", [])


def find_player_in_roster(player_name: str, roster: list):
    target = normalize_name(player_name)
    for athlete in roster:
        candidate = athlete.get("fullName") or athlete.get("displayName", "")
        if normalize_name(candidate) == target:
            return athlete
    return None


def main():
    with open(ROOKIES_PATH) as f:
        rookies = json.load(f)

    print("Fetching NBA team list...")
    all_teams = get_all_teams()
    print(f"  Found {len(all_teams)} teams")

    updated = 0
    for rookie in rookies:
        if rookie.get("espn_id"):
            continue

        team_id = find_team_id(rookie["team"], all_teams)
        if not team_id:
            print(f"  [warn] Could not find ESPN team ID for '{rookie['team']}' ({rookie['name']})")
            continue

        try:
            roster = get_team_roster(team_id)
        except Exception as e:
            print(f"  [error] Could not fetch roster for {rookie['team']}: {e}")
            continue

        athlete = find_player_in_roster(rookie["name"], roster)
        if not athlete:
            print(f"  [info] {rookie['name']} not yet on {rookie['team']}'s official roster "
                  f"(common right after a draft - try again later)")
            continue

        rookie["espn_id"] = str(athlete.get("id"))
        headshot = athlete.get("headshot", {})
        rookie["headshot_url"] = headshot.get("href") or (
            f"https://a.espncdn.com/i/headshots/nba/players/full/{athlete.get('id')}.png"
        )
        updated += 1
        print(f"  Resolved {rookie['name']} -> espn_id={rookie['espn_id']}")

    with open(ROOKIES_PATH, "w") as f:
        json.dump(rookies, f, indent=2)

    print(f"\nDone. Resolved {updated} new player(s). "
          f"{sum(1 for r in rookies if not r.get('espn_id'))} still unresolved.")


if __name__ == "__main__":
    main()
