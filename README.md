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

## Three independent scrapers
| # | Script | Source | Writes to |
|---|---|---|---|
| 1 | `scripts/fetch_realgm.py` | RealGM | `data/raw/rookie_boxscores.csv` |
| 2 | `scripts/fetch_espn_shots.py` | ESPN | `data/raw/rookie_shots.csv` |
| 3 | `scripts/fetch_espn_headshots.py` | ESPN | `data/rookies.json` (`espn_id`/`headshot_url` only) |

Each is fully independent - separate output file, separate dedup state,
separate failure mode. A problem in one (e.g. RealGM's bot detection kicking
in) never blocks the other two. Run all three, then `build_dataset.py` to
merge scrapers 1 and 2's output into the rankings/shot-chart data the app reads.

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
  rookies.json                    # roster config: name, team, draft pick, RealGM IDs, ESPN id/headshot
  raw/
    rookie_boxscores.csv          # full box-score line per game, all 10 rookies (scraper 1: RealGM)
    rookie_shots.csv              # shot-by-shot data, all 10 rookies (scraper 2: ESPN)
  processed/
    shots.csv                     # unified shot data the shot charts read from
    season_stats.csv              # one row per rookie: PPG/RPG/APG/SPG/BPG/TS%/GameScore/games
    rankings.csv                  # season_stats + computed ROY score, sorted
  processed_realgm_games.json     # scraper 1's dedup state (RealGM boxscore URLs already ingested)
  processed_espn_shot_games.json  # scraper 2's dedup state (ESPN games already ingested for shots)
app/
  Home.py                         # hub page: ranked top 10 list (Streamlit entrypoint)
  player_profile.py               # shared rendering logic - every rookie's page calls this
  pages/                          # one thin file per rookie (Streamlit's multipage convention)
  stats.py                        # shot-based helper (used only by the scatter/legacy view)
  roy_score.py                    # the v2 weighting formula + Game Score/TS% computation
scripts/
  fetch_realgm.py                 # scraper 1: box scores + advanced-stat inputs (RealGM)
  fetch_espn_shots.py             # scraper 2: shot locations (ESPN)
  fetch_espn_headshots.py         # scraper 3: profile photos (ESPN)
  fetch_nba_games.py              # nba_api pull for real NBA season (Darryn Peterson only so far)
  fetch_summer_league.py          # manual CSV fallback for shot data (legacy schema)
  build_dataset.py                # merges scrapers 1+2's output, computes rankings
```

## Data source notes (read before you trust this blindly)
- **RealGM has bot detection (CrowdSec)**. While researching this project,
  some RealGM forum pages returned a CrowdSec captcha challenge to automated
  requests ("We have seen a lot of robot like traffic..."). This is a real
  risk for `fetch_realgm.py` running unattended in GitHub Actions - if the
  scheduled run keeps coming back with zero new games for players you know
  have played, this is the likely cause, not a code bug. There's no clean
  fix for this from a public GitHub Action (no way to solve a captcha
  automatically); if it becomes a persistent problem, the realistic options
  are switching back to a source without bot detection, or manually
  refreshing data periodically the way this was bootstrapped for Peterson/
  Acuff/Dybantsa (searched + fetched directly, not via the automated script).
- **RealGM is unofficial/unaffiliated with the NBA**; its page structure
  could change without notice beyond the bot-detection issue above.
- **This could not be tested against the live RealGM site** from the
  sandbox that built it (network restricted to package registries only) -
  it was validated against a synthetic HTML fixture built from the real
  page structure, but the first live run is the actual test.
- **Most rookies still show 0 games** - either because their team's Summer
  League site hasn't started yet (e.g. Wizards/Bulls/Clippers/Mavericks
  play Vegas, which starts ~July 10), or because `fetch_realgm.py` hasn't
  successfully run against the live site yet for the others.
- **Photos come from ESPN**, not RealGM - `data/rookies.json` has each
  rookie's ESPN athlete ID and headshot URL populated directly (found via
  web search), and `fetch_realgm.py` does not touch this field.
- **NBA-season data** (`fetch_nba_games.py`, via `nba_api`) is currently
  Darryn-Peterson-only - extending it to all 10 once the season starts is a
  straightforward copy of the existing pattern, not yet done.

## Running locally
```bash
pip install -r requirements.txt
python scripts/fetch_realgm.py            # scraper 1: stats
python scripts/fetch_espn_shots.py        # scraper 2: shot charts
python scripts/fetch_espn_headshots.py    # scraper 3: photos (only needs to succeed once per player)
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
