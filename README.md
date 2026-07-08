# 2026 Rookie of the Year Tracker

An auto-updating hub tracking the top 10 picks of the 2026 NBA Draft, ranked
by a custom-weighted "Rookie of the Year" score, with a full shot-chart
profile page for each player.

**Live question this project answers:** based on early performance (Summer
League now, real NBA minutes once the season starts), who's actually
building the best ROY case among this draft class?

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

## The ROY scoring formula
Set in `app/roy_score.py`, weighted by priority order:
1. **Scoring (40%)** - PPG
2. **Efficiency (30%)** - blend of FG% and 3PT%
3. **Playmaking (20%)** - APG
4. **Rebounding (10%)** - RPG

Each stat is normalized 0-100 **relative to the other 9 tracked rookies**
(not the whole league) before weighting - this is a relative ranking tool
for comparing this specific group, not an absolute grade. Edit the `WEIGHTS`
dict in `app/roy_score.py` to change what matters most to you.

**Known quirk**: when every rookie in a stat category is tied (e.g. everyone
currently has 0 recorded rebounds), that category contributes a neutral
50/100 to everyone rather than 0 - otherwise a rookie with zero *tracked*
games would look artificially worse than one who just hasn't played yet.
This resolves naturally as real box scores come in.

## Project structure
```
data/
  rookies.json              # roster config: name, team, draft pick, ESPN IDs
  raw/                      # raw pulls, appended to by the fetchers
    rookie_shots.csv        # shot-by-shot data, all 10 rookies, one file
    rookie_boxscores.csv    # per-game points/rebounds/assists tallies
  processed/
    shots.csv               # unified shot data the shot charts read from
    season_stats.csv        # one row per rookie: PPG/RPG/APG/FG%/3PT%/games
    rankings.csv            # season_stats + computed ROY score, sorted
app/
  Home.py                   # hub page: ranked top 10 list (Streamlit entrypoint)
  player_profile.py         # shared rendering logic - every rookie's page calls this
  pages/                    # one thin file per rookie (Streamlit's multipage convention)
  stats.py                  # season stat calculator (PPG/FG%/3FG%/FT%)
  roy_score.py              # the weighting formula
scripts/
  fetch_espn_rookies.py     # fully automated: discovers games + extracts shots/box scores for all 10
  resolve_rookie_ids.py     # one-time-per-player: fills in ESPN photo/ID via team rosters
  fetch_nba_games.py        # nba_api pull for real NBA season (Darryn Peterson only so far)
  fetch_summer_league.py    # manual CSV fallback for any game the automation misses
  build_dataset.py          # merges everything, computes rankings
```

## Data source notes (read before you trust this blindly)
- **Summer League sites differ per team.** Salt Lake City Summer League
  (Jazz, Hawks, Grizzlies - already played) is confirmed via
  `nba-summer-utah`. The other 7 rookies' teams are guessed as either
  `nba-summer-las-vegas` or `nba-summer-california` in `rookies.json`
  **before those events had started** - double check and correct these
  slugs once real schedules are confirmed.
- **Most rookies currently show 0 games.** That's accurate, not a bug - Vegas
  Summer League hadn't started as of when this was built.
- **Free throws, rebounds, and assists** are extracted via text-pattern
  matching on ESPN's play-by-play descriptions (e.g. "assists" in
  parentheses, "defensive rebound" as a line), not official structured box
  score fields. Spot-check against a real box score periodically.
- **Player photos**: hotlinked from ESPN's CDN once `resolve_rookie_ids.py`
  finds each rookie on their team's official roster - which may lag right
  after a draft. Missing photos fall back to a placeholder.
- **NBA-season data** (`fetch_nba_games.py`, via `nba_api`) is currently
  Darryn-Peterson-only - extending it to all 10 rookies once the season
  starts is a straightforward copy of the existing pattern, not yet done.
- ESPN's API is unofficial and undocumented; it could change without notice.

## Running locally
```bash
pip install -r requirements.txt
python scripts/resolve_rookie_ids.py
python scripts/fetch_espn_rookies.py
python scripts/build_dataset.py
streamlit run app/Home.py
```

## Auto-updates
`.github/workflows/update_data.yml` runs every 6 hours: resolves any missing
player IDs, fetches new games for all 10 rookies, rebuilds rankings, and
commits. Deploy on Streamlit Community Cloud pointed at `app/Home.py` and it
picks up new commits automatically.

## Roadmap ideas
- [ ] Extend `fetch_nba_games.py` to all 10 rookies once the regular season starts
- [ ] Verify/correct the Vegas & California Classic summer_league_slug guesses
- [ ] Add a "shot mix breakdown" (paint/mid/three %) as an honest substitute
      for "similar shooters" comps, which would need a league-wide database
      this project doesn't have
