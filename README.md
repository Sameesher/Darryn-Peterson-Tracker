# Darryn Peterson: The Next Great 
This project consists of an auto-updating dashboard tracking Darryn Peterson's career including statistics from NBA Summer League into his Utah Jazz rookie season.


## Why this project
Darryn Peterson might have been one of the most polarizing prospects in recent history. While many scouts acknowledged his generational talent concerns about his injuries and his motivation arose. It didn't help that the draft class he was apart of was one of the strongest in recent memory. So it wasn't much of a shock when AJ Dybantsa went number one overall and Peterson went number two.
The inspiration behind this project stems from my personal belief that the decision to draft Dybantsa over Peterson was a mistake as I believe Peterson will grow into a Hall of Fame caliber player. I built this dashboard to show how much of an anomly he is as a prospect and why draft experts will be wondering how a player like him didn't go number one overall.

## Project structure
```
data/                  # raw + processed game data (committed, updated by CI)
  raw/                 # one file per data pull, timestamped
  processed/           # cleaned, unioned dataset the app reads from
scripts/
  fetch_nba_games.py   # pulls shot chart + play-by-play once regular season starts
  fetch_summer_league.py  # manual/scraped Summer League ingestion (see notes below)
  build_dataset.py     # merges all sources into data/processed/shots.csv
app/
  dashboard.py         # Streamlit app: shot chart + role-over-time views
.github/workflows/
  update_data.yml      # nightly cron job that runs the fetch + rebuild + commits
requirements.txt
```

## Data source notes (read before you run this)
- **NBA/rookie season**: uses the `nba_api` package (wraps stats.nba.com).
  Once he has a Jazz roster ID, `fetch_nba_games.py` pulls shot chart + play-by-play
  data automatically. Real tracked coordinates.
- **Summer League — now fully automatic**: `fetch_espn_summer_league.py` uses
  ESPN's (unofficial, undocumented) JSON API to discover recently completed
  Jazz Summer League games on its own, pull the play-by-play, and extract
  Darryn Peterson's shot attempts — no manual entry needed. It runs on the
  same nightly GitHub Action as the NBA fetch. See the big comment at the
  top of that script for exactly how it works and what it can't guarantee
  (ESPN's API is unofficial and could change; shot locations may be estimated
  from the play's text description rather than real coordinates if ESPN
  doesn't expose coordinates for these games — check the `location_source`
  column in the data to see which happened for any given shot).
- `fetch_summer_league.py` (manual CSV template) still exists as a fallback
  for any game the automated script misses or gets wrong.

## Running locally
```bash
pip install -r requirements.txt
python scripts/build_dataset.py
streamlit run app/dashboard.py
```

## Auto-updates
`.github/workflows/update_data.yml` runs nightly during the season, re-fetches
new games, rebuilds `data/processed/shots.csv`, and commits the change. If
you deploy the Streamlit app on Streamlit Community Cloud pointed at this repo,
it will reflect new games automatically after each commit.

## Roadmap ideas
- [ ] Add possession-type tagging (iso / spot-up / PnR ball-handler / off-screen)
- [ ] Add a "role score" metric blending usage%, assist%, and touch time
- [ ] Side-by-side shot chart slider: college vs. Summer League vs. NBA
- [ ] Weekly auto-generated summary written to `CHANGELOG.md`
