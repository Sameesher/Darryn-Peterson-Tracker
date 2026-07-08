"""
Custom Rookie of the Year scoring formula - v2, grounded in how ROY voting
actually behaves historically rather than a purely intuitive weighting.

Research basis (see conversation/README for sources): NBA media analysis of
real ROY races consistently finds that voters reward raw production volume
and "stat-stuffing" (points + rebounds + assists + stocks) over shooting
efficiency, and value durability/games-played consistency - while team
success matters comparatively little for this specific award (unlike MVP).
Recent winners (e.g. Cooper Flagg, Stephon Castle) were high-usage,
high-counting-stat rookies on so-so teams, not necessarily the most
efficient scorers in the class.

This version replaces the original 4-stat (PPG/FG%/APG/RPG) formula with:

1. Production (35%) - a "stat-stuffing" composite: PPG + RPG + APG + STL + BLK.
   This is what voters seem to reward most: broad, visible box-score impact.
2. Game Score (30%) - John Hollinger's single-number per-game impact metric,
   which blends scoring, efficiency, rebounding, playmaking, and mistakes
   into one number. Used here as a holistic "how good was this game" measure
   that a pure counting-stat total can miss.
3. Availability (20%) - games played, since voters explicitly value
   durability/consistency and a player who misses time hurts their own case
   even if their per-game numbers are excellent.
4. Efficiency (15%) - True Shooting %, kept as the smallest factor on
   purpose, since research suggests voters historically weight this less
   than raw production.

All four are normalized 0-100 *within this specific group of 10 rookies*
(not against the whole league), same as before - this is a relative
comparison tool for this draft class, not an absolute grade.
"""
import pandas as pd

WEIGHTS = {
    "production": 0.35,
    "game_score": 0.30,
    "availability": 0.20,
    "efficiency": 0.15,
}


def _normalize(series: pd.Series) -> pd.Series:
    if series.max() == series.min():
        return pd.Series([50.0] * len(series), index=series.index)
    return (series - series.min()) / (series.max() - series.min()) * 100


def compute_advanced_stats(boxscores: pd.DataFrame) -> pd.DataFrame:
    """
    Computes per-game True Shooting % and Hollinger Game Score from a
    dataframe of individual games (one row per game, full box score columns:
    pts, fgm, fga, ftm, fta, orb, drb, ast, stl, blk, tov, pf).
    Returns the same dataframe with ts_pct and game_score columns added.
    """
    df = boxscores.copy()
    denom = 2 * (df["fga"] + 0.44 * df["fta"])
    df["ts_pct"] = (df["pts"] / denom.replace(0, pd.NA) * 100).fillna(0)

    df["game_score"] = (
        df["pts"]
        + 0.4 * df["fgm"]
        - 0.7 * df["fga"]
        - 0.4 * (df["fta"] - df["ftm"])
        + 0.7 * df["orb"]
        + 0.3 * df["drb"]
        + df["stl"]
        + 0.7 * df["ast"]
        + 0.7 * df["blk"]
        - 0.4 * df["pf"]
        - df["tov"]
    )
    return df


def compute_roy_rankings(rookie_stats: pd.DataFrame) -> pd.DataFrame:
    """
    rookie_stats must have one row per rookie with columns:
    name, team, draft_pick, games, ppg, rpg, apg, spg, bpg, ts_pct, avg_game_score

    Returns the same dataframe with added score columns, sorted descending
    by roy_score (0-100).
    """
    df = rookie_stats.copy()

    df["production_raw"] = (
        df["ppg"].fillna(0) + df["rpg"].fillna(0) + df["apg"].fillna(0)
        + df["spg"].fillna(0) + df["bpg"].fillna(0)
    )

    df["production_score"] = _normalize(df["production_raw"])
    df["game_score_score"] = _normalize(df["avg_game_score"].fillna(0))
    df["availability_score"] = _normalize(df["games"].fillna(0))
    df["efficiency_score"] = _normalize(df["ts_pct"].fillna(0))

    df["roy_score"] = (
        df["production_score"] * WEIGHTS["production"]
        + df["game_score_score"] * WEIGHTS["game_score"]
        + df["availability_score"] * WEIGHTS["availability"]
        + df["efficiency_score"] * WEIGHTS["efficiency"]
    ).round(1)

    return df.sort_values("roy_score", ascending=False).reset_index(drop=True)
