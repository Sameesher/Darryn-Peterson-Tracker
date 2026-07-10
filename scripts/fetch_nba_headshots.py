"""
SCRAPER 3 of 3 (PRIMARY pipeline): downloads actual NBA.com headshot image
files for every rookie with a known nba_player_id (see
fetch_nba_official.py, which must run first to populate that field).

Unlike a simple hotlinked <img src="remote-url">, this ACTUALLY DOWNLOADS
the image bytes and saves them to disk under data/headshots/{player_id}.png.
This is more robust than hotlinking for a few reasons: it doesn't depend on
cdn.nba.com being reachable/fast at the moment someone views the dashboard,
it can't be broken by hotlink protection, and the downloaded file becomes
a stable local asset that gets committed to the repo like any other data
file. The app embeds these local files as base64 data URIs at render time
(see player_profile.py/Home.py) rather than linking to a URL.

nba.com serves headshots from a predictable CDN pattern once you have the
numeric NBA.com person ID:
    https://cdn.nba.com/headshots/nba/latest/1040x760/{PLAYER_ID}.png

Writes:
- data/headshots/{player_id}.png - the actual downloaded image file
- data/rookies.json's `headshot_local_path` field - relative path to that file

IMPORTANT CAVEATS - read before trusting this blindly:
- Could not be tested against the live cdn.nba.com endpoint from the
  sandbox that built it (network restricted to package registries only) -
  the first live run is the actual test.
- The CDN URL pattern above is a well-known, widely-used convention but
  wasn't verified against a real request here - if downloads come back as
  0-byte files or non-image content, double check this pattern against a
  player you can confirm has a real nba.com photo.
- A rookie who hasn't been matched to an nba_player_id yet (see
  fetch_nba_official.py) is skipped - re-run this after that script finds
  more IDs.
- Only re-downloads a player's image if the local file doesn't already
  exist, to avoid needlessly re-fetching unchanged headshots on every run.
  Use --force to re-download everyone anyway.

Usage:
    python scripts/fetch_nba_headshots.py
    python scripts/fetch_nba_headshots.py --force
    python scripts/fetch_nba_headshots.py --player "Darryn Peterson"

Designed to run occasionally (see .github/workflows/update_data.yml) -
photos rarely change, so this doesn't need the same frequent schedule as
the stats/shot-chart scrapers.
"""
import argparse
import json
import os

import requests

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
ROOKIES_PATH = os.path.join(BASE_DIR, "data", "rookies.json")
HEADSHOTS_DIR = os.path.join(BASE_DIR, "data", "headshots")

CDN_URL_TEMPLATE = "https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; rookie-tracker/1.0)"})


def load_rookies() -> list:
    with open(ROOKIES_PATH) as f:
        return json.load(f)


def save_rookies(rookies: list) -> None:
    with open(ROOKIES_PATH, "w") as f:
        json.dump(rookies, f, indent=2)


def download_headshot(player_id: str, force: bool = False):
    """Downloads and saves one player's headshot. Returns the relative
    local path on success, None on failure or if skipped (already exists)."""
    os.makedirs(HEADSHOTS_DIR, exist_ok=True)
    filename = f"{player_id}.png"
    local_path = os.path.join(HEADSHOTS_DIR, filename)
    relative_path = os.path.join("data", "headshots", filename)

    if os.path.exists(local_path) and not force:
        return relative_path  # already have it, nothing to do

    url = CDN_URL_TEMPLATE.format(player_id=player_id)
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"    [error] Could not download {url}: {e}")
        return None

    content_type = resp.headers.get("Content-Type", "")
    if "image" not in content_type or len(resp.content) < 500:
        print(f"    [warn] Response doesn't look like a real image "
              f"(content-type={content_type}, size={len(resp.content)} bytes) - skipping save.")
        return None

    with open(local_path, "wb") as f:
        f.write(resp.content)
    return relative_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                         help="Re-download even if a local file already exists")
    parser.add_argument("--player", default=None,
                         help="Only download this one rookie (exact name match), for testing")
    args = parser.parse_args()

    rookies = load_rookies()
    targets = rookies
    if args.player:
        targets = [r for r in rookies if r["name"] == args.player]
        if not targets:
            print(f"No rookie named '{args.player}' in data/rookies.json")
            return

    downloaded = 0
    skipped_no_id = 0
    rookies_updated = False

    for rookie in targets:
        player_id = rookie.get("nba_player_id")
        if not player_id:
            skipped_no_id += 1
            continue

        print(f"{rookie['name']} (nba_player_id={player_id}):")
        path = download_headshot(player_id, force=args.force)
        if path:
            if rookie.get("headshot_local_path") != path:
                rookie["headshot_local_path"] = path
                rookies_updated = True
            downloaded += 1
            print(f"  Saved -> {path}")
        else:
            print("  Failed or skipped (see above).")

    if rookies_updated:
        save_rookies(rookies)

    print(f"\nDone. {downloaded} headshot(s) downloaded/confirmed, "
          f"{skipped_no_id} skipped (no nba_player_id yet - run fetch_nba_official.py first).")


if __name__ == "__main__":
    main()
