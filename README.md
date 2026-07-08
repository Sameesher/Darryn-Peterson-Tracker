# 2026 Rookie of the Year Tracker

An auto-updating hub tracking the top 10 picks of the 2026 NBA Draft, ranked
by a custom-weighted "Rookie of the Year" score grounded in how ROY voting
actually behaves historically, with a full profile page for each player.

## Roster tracked (verified against NBA.com's official 2026 draft results)
| Pick | Player | Team |
|---|---|---|
| 1 | AJ Dybantsa | Washington Wizards |
| 2 | Darryn Peterson | Utah Jazz |
| 3 | Cameron Boozer | Memphis Grizzlies |
| 4 | Caleb Wilson | Chicago Bulls |
| 5 | Keaton Wagler | LA Clippers |
| 6 | Mikel Brown Jr. | Brooklyn Nets |
| 7 | Darius Acuff Jr. | Sacramento Kings |
| 8 | Kingston Flemings | Atlanta Hawks |
| 9 | Morez Johnson Jr. | Dallas Mavericks |
| 10 | Brayden Burries | Milwaukee Bucks |

## Data source: RealGM
All stats now come from **basketball.realgm.com**'s structured game-log
tables, not ESPN. Why the switch:
- RealGM's tables include a *complete* box score (minutes, both rebound
  types, steals, blocks, turnovers, personal fouls) - not just points/
  rebounds/assists, which is what makes the advanced-stat formula below
  possible at all.
- ESPN's headshot hotlinking wasn't rendering reliably in the deployed app;
  RealGM's own player photos (scraped directly from their game log pages)
  replace them.
- RealGM's numbers checked out more accurate in spot-checks than this
  project's earlier ESPN play-by-play text-parsing approach.

**Tradeoff, stated plainly**: RealGM's game logs are box scores only - no
shot x/y coordinates. Switching the *stats* pipeline to RealGM means the
interactive hex shot chart has no new data source going forward. The shot
data already collected via the old ESPN-based approach (Peterson's and
Acuff's first two games each) is kept as a **frozen historical snapshot** in
`data/processed/shots.csv` so those two charts still render - but nothing
new will be added there. If shot-chart data matters more than ROY-ranking
accuracy, that's a separate, parallel pipeline to build back in.

## The ROY scoring formula (v2 - research-informed)
Set in `app/roy_score.py`. The original version weighted PPG/FG%/APG/RPG
somewhat arbitrarily. This version is grounded in how ROY voting actually
behaves: media analysis of recent races found voters reward raw production
volume and "stat-stuffing" over shooting efficiency, and value durability -
while team success matters comparatively little for this specific award.

| Component | Weight | What it measures |
|---|---|---|
| **Production** | 35% | PPG + RPG + APG + SPG + BPG - the "stat-stuffing" composite voters reward most |
| **Game Score** | 30% | Hollinger's per-game impact metric - a holistic single number blending scoring, efficiency, rebounding, playmaking, and mistakes |
| **Availability** | 20% | Games played - durability/consistency, which voters explicitly value |
| **Efficiency** | 15% | True Shooting % - kept as the *smallest* weight on purpose, since voters seem to reward volume over pure efficiency |

Each component is normalized 0-100 **relative to the other 9 tracked
rookies** (not the whole league) before weighting - a relative comparison
tool for this group, not an absolute grade. Edit `WEIGHTS` in
`app/roy_score.py` to change the emphasis yourself.

**Game Score formula** (Hollinger):
```
GmSc = PTS + 0.4*FGM - 0.7*FGA - 0.4*(FTA-FTM) + 0.7*ORB + 0.3*DRB
       + STL + 0.7*AST + 0.7*BLK - 0.4*PF - TOV
```
**True Shooting %**: `PTS / (2 * (FGA + 0.44*FTA))`

## Project structure
```
data/
  rookies.json                    # roster config: name, team, draft pick, RealGM IDs, photo URL
  raw/
    rookie_boxscores.csv          # full box-score line per game, all 10 rookies, scraped from RealGM
    rookie_shots.csv              # FROZEN historical shot data (Peterson + Acuff only, ESPN-era)
  processed/
    shots.csv                     # frozen shot data passthrough (for the 2 existing shot charts)
    season_stats.csv              # one row per rookie: PPG/RPG/APG/SPG/BPG/TS%/GameScore/games
    rankings.csv                  # season_stats + computed ROY score, sorted
  processed_realgm_games.json     # dedup state: which RealGM boxscore URLs have already been ingested
app/
  Home.py                         # hub page: ranked top 10 list (Streamlit entrypoint)
  player_profile.py               # shared rendering logic - every rookie's page calls this
  pages/                          # one thin file per rookie (Streamlit's multipage convention)
  stats.py                        # legacy shot-based stat calculator (still used by the 2 frozen shot charts)
  roy_score.py                    # the v2 weighting formula + Game Score/TS% computation
scripts/
  fetch_realgm.py                 # fully automated: scrapes box scores + photos for all 10 from RealGM
  fetch_nba_games.py               # nba_api pull for real NBA season (Darryn Peterson only so far)
  fetch_summer_league.py           # manual CSV fallback (legacy, shot-based schema)
  build_dataset.py                 # merges everything, computes rankings
```

## Data source notes (read before you trust this blindly)
- **RealGM is unofficial/unaffiliated with the NBA**; its page structure
  could change without notice. `fetch_realgm.py`'s table-finder matches
  on header text ("PTS", "FGM", etc.) rather than a hardcoded position,
  which should survive minor layout tweaks but not a full redesign.
- **This could not be tested against the live RealGM site** from the
  sandbox that built it (network restricted to package registries only) -
  it was validated against a synthetic HTML fixture built from the real
  page structure, but the first live run is the actual test.
- **Most rookies still show 0 games** until `fetch_realgm.py` actually runs
  against the live site (via the scheduled GitHub Action, or run locally).
- **Photos**: captured automatically from RealGM's player photo `<img>` tag
  the first time `fetch_realgm.py` successfully fetches a rookie's page, and
  written back into `rookies.json` so it's a one-time cost per player.
- **NBA-season data** (`fetch_nba_games.py`, via `nba_api`) is currently
  Darryn-Peterson-only - extending it to all 10 once the season starts is a
  straightforward copy of the existing pattern, not yet done.

## Running locally
```bash
pip install -r requirements.txt
python scripts/fetch_realgm.py
python scripts/build_dataset.py
streamlit run app/Home.py
```

## Auto-updates
`.github/workflows/update_data.yml` runs every 6 hours: scrapes RealGM for
new games across all 10 rookies, rebuilds rankings, and commits. Deploy on
Streamlit Community Cloud pointed at `app/Home.py` and it picks up new
commits automatically.

## Roadmap ideas
- [ ] Wire a shot-location source back in if the hex chart matters going
      forward (RealGM doesn't have one; would need ESPN or another source
      run in parallel to the RealGM stats pipeline)
- [ ] Extend `fetch_nba_games.py` to all 10 rookies once the regular season starts
- [ ] Add a real live test of `fetch_realgm.py` against the actual site and
      fix any table-parsing surprises
