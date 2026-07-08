# Darryn Peterson: Shot Chart & Role Evolution Tracker

An auto-updating dashboard tracking Darryn Peterson's shooting profile and
on-court role from NBA Summer League into his Utah Jazz rookie season.

**Live question this project answers:** Is he staying an off-ball spot-up scorer,
or is he growing into more of a lead-guard/playmaking role?

## Why this project
Scouts flagged him as a knockdown shooter who mostly played off the ball in
college despite running point in high school. That's a testable hypothesis —
if his role expands, we should see it in usage rate, assist rate, and shot
selection (more pull-up/PnR shots vs. catch-and-shoot) over time.

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
  data automatically.
- **Summer League**: stats.nba.com's Summer League data is NOT covered by
  `nba_api` reliably. `fetch_summer_league.py` is set up as a manual entry point —
  you fill in a small CSV per game from box scores until/unless a better source
  is found. This keeps the pipeline consistent without blocking on a bad API.

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
