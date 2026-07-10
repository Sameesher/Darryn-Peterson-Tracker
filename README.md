# 2026 Rookie of the Year Tracker

An auto-updating hub tracking the full 2026 NBA Draft class (all 60 picks), ranked
by a custom-weighted "Rookie of the Year" score grounded in how ROY voting
actually behaves historically, with a full profile page for each player.

## Roster tracked: the full 2026 NBA Draft class (all 60 picks)
Verified against RealGM's official 2026 draft results page (which lists
every pick with post-trade final destinations). The complete list of all
60 - name, team, college/pre-draft team, RealGM/ESPN IDs - lives in
`data/rookies.json`, not duplicated here since it's 60 rows. Top 10 for reference:

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

Picks 11-60 include the rest of Round 1 (Yaxel Lendeborg, Aday Mara, Nate
Ament, etc.) and all of Round 2, with final team destinations resolved for
every post-draft trade RealGM had recorded as of when this was built.

## NBA.com is now the primary source for everything - stats, shot charts, and headshots
| # | Script | Source | Writes to |
|---|---|---|---|
| ★1 | `scripts/fetch_nba_official.py` | **NBA.com / stats.nba.com** | `rookie_nba_official_stats.csv` + `rookies.json` (player ID + headshot) |
| ★2 | `scripts/fetch_nba_shotchart.py` | **NBA.com / stats.nba.com** | `data/raw/rookie_shots.csv` - real tracked shot coordinates |
| 3 | `scripts/fetch_realgm.py` | RealGM | `data/raw/rookie_boxscores.csv` - **fallback stats** only |
| 4 | `scripts/fetch_espn_shots.py` | ESPN | `data/raw/rookie_shots.csv` - **fallback shots** only |
| 5 | `scripts/fetch_espn_headshots.py` | ESPN | `rookies.json` - **fallback headshots** only |

`build_dataset.py` prefers NBA.com's own numbers everywhere they're
available, and only falls back to RealGM/ESPN for rookies/games the
official source doesn't cover yet (e.g. a player who hasn't been matched to
an `nba_player_id` yet). Each scraper is fully independent - separate
output file, separate dedup state, separate failure mode - so a problem in
one never blocks the others.

**Why nba.com needed its own scraper instead of just visiting the site**:
the visible pages (e.g. `nba.com/2026-summer-league-vegas-player-stats`,
or the shot-chart page at `nba.com/game/{slug}/game-charts`) render "No
data available" in their raw HTML - the real tables/shot plots load via a
client-side JavaScript call to `stats.nba.com`'s JSON API. `nba_api`
(already a dependency) talks to that same backend directly:
- `fetch_nba_official.py` uses `LeagueDashPlayerStats` (`SeasonType="Summer
  League"`) - one bulk call returns every player in the whole Summer
  League, filtered down to the 60 tracked rookies. It also captures each
  matched rookie's NBA.com `PLAYER_ID` from that same response and builds
  their headshot URL from nba.com's predictable CDN pattern
  (`cdn.nba.com/headshots/nba/latest/1040x760/{id}.png`) - no separate
  headshot lookup needed.
- `fetch_nba_shotchart.py` uses `PlayerGameLogs` to find each rookie's
  individual games, then `ShotChartDetail` per game for **real tracked X/Y
  shot coordinates** - genuinely measured locations, not the distance/type
  text-estimates the ESPN fallback pipeline sometimes had to use.

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

Each component is normalized 0-100 **relative to the other 59 tracked
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
    rookie_boxscores.csv          # full box-score line per game, all 60 rookies (scraper 1: RealGM)
    rookie_shots.csv              # shot-by-shot data, all 60 rookies (scraper 2: ESPN)
  processed/
    shots.csv                     # unified shot data the shot charts read from
    season_stats.csv              # one row per rookie: PPG/RPG/APG/SPG/BPG/TS%/GameScore/games
    rankings.csv                  # season_stats + computed ROY score, sorted
  processed_realgm_games.json     # scraper 1's dedup state (RealGM boxscore URLs already ingested)
  processed_espn_shot_games.json  # scraper 2's dedup state (ESPN games already ingested for shots)
app/
  Home.py                         # hub page: ranked list of the full draft class (Streamlit entrypoint)
  player_profile.py               # shared rendering logic - every rookie's page calls this
  pages/                          # one thin file per rookie (Streamlit's multipage convention)
  stats.py                        # shot-based helper (used only by the scatter/legacy view)
  roy_score.py                    # the v2 weighting formula + Game Score/TS% computation
scripts/
  fetch_nba_official.py           # PREFERRED: official NBA.com stats via nba_api (SeasonType="Summer League")
  fetch_realgm.py                 # scraper 1: box scores + advanced-stat inputs (RealGM, fallback)
  fetch_espn_shots.py             # scraper 2: shot locations (ESPN)
  fetch_espn_headshots.py         # scraper 3: profile photos (ESPN)
  fetch_nba_games.py              # nba_api pull for real NBA season (Darryn Peterson only so far)
  fetch_summer_league.py          # manual CSV fallback for shot data (legacy schema)
  build_dataset.py                # merges all sources (official > RealGM), computes rankings
```

## Data source notes (read before you trust this blindly)
- **nba.com's headshot CDN pattern is unverified.** `cdn.nba.com/headshots/
  nba/latest/1040x760/{id}.png` is a widely-used, well-known pattern, but
  wasn't checked against a live request from this sandbox. If photos come
  back broken after the first live run, check this pattern against a
  player you can confirm has a real nba.com photo.
- **Shot chart coordinate units**: `ShotChartDetail` returns coordinates in
  1/10-foot units (same as the existing NBA-season pipeline already
  handled) - `fetch_nba_shotchart.py` converts to feet before writing, so
  no changes were needed in the dashboard's chart-rendering code.
- **50 of the 60 rookies are new additions** and haven't had the same manual
  verification as the original top 10 (Peterson, Acuff, etc.). Specifically:
  their `espn_id`/`headshot_url` are `null` until `fetch_espn_headshots.py`
  successfully resolves them (automatic, but depends on each player being on
  their team's official ESPN roster already), and their `summer_league_slugs`
  default to `["nba-summer-las-vegas"]` as a generic guess - correct for most
  teams, but the 6 teams already confirmed playing Salt Lake City or
  California Classic first were set accordingly (Jazz, Grizzlies, Hawks,
  Nets, Kings, Bucks); double check the rest as real schedules confirm them.
- **The official NBA source's exact `season` string is unverified.** It
  defaults to `"2026-27"` (the season Summer League precedes) - this is a
  reasonable guess based on common `nba_api` usage, but the first live run
  is the real test. If it comes back empty, try `--season 2025-26` or check
  the Actions log for what stats.nba.com actually returned.
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
python scripts/fetch_nba_official.py      # 1. NBA.com stats + player IDs + headshots
python scripts/fetch_nba_shotchart.py     # 2. NBA.com shot charts (needs player IDs from step 1)
python scripts/fetch_realgm.py            # 3. fallback stats
python scripts/fetch_espn_shots.py        # 4. fallback shot data
python scripts/fetch_espn_headshots.py    # 5. fallback headshots
python scripts/build_dataset.py
streamlit run app/Home.py
```

## Auto-updates
`.github/workflows/update_data.yml` runs every 6 hours: scrapes RealGM for
new games across all 60 rookies, rebuilds rankings, and commits. Deploy on
Streamlit Community Cloud pointed at `app/Home.py` and it picks up new
commits automatically.

## Roadmap ideas
- [ ] Wire a shot-location source back in if the hex chart matters going
      forward (RealGM doesn't have one; would need ESPN or another source
      run in parallel to the RealGM stats pipeline)
- [ ] Extend `fetch_nba_games.py` to all 60 rookies once the regular season starts
- [ ] Add a real live test of `fetch_realgm.py` against the actual site and
      fix any table-parsing surprises
