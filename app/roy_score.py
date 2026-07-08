"""
Custom Rookie of the Year scoring formula.

Weights reflect this priority order (set by the user):
  1. Scoring        (highest weight)
  2. Efficiency
  3. Playmaking
  4. Rebounding      (lowest weight)

The formula normalizes each raw stat to a 0-100 scale *relative to the other
tracked rookies* (not to the whole league) before applying weights, since
comparing this specific group of 10 is the whole point of the hub. That means
scores will shift slightly whenever a rookie's stats update - a "72" today
might become a "68" next week if someone else in the group goes off, even if
this rookie's own numbers didn't change. This is a relative ranking tool, not
an absolute grade.

Edit WEIGHTS below to change what matters most to you.
"""
import pandas as pd

WEIGHTS = {
    "scoring": 0.40,      # PPG
    "efficiency": 0.30,   # blend of FG% and 3PT%
    "playmaking": 0.20,   # APG
    "rebounding": 0.10,   # RPG
}


def _normalize(series: pd.Series) -> pd.Series:
    """Scale a stat to 0-100 relative to the min/max within this group of rookies."""
    if series.max() == series.min():
        return pd.Series([50.0] * len(series), index=series.index)  # all tied -> neutral midpoint
    return (series - series.min()) / (series.max() - series.min()) * 100


def compute_roy_rankings(rookie_stats: pd.DataFrame) -> pd.DataFrame:
    """
    rookie_stats must have one row per rookie with columns:
    name, ppg, fg_pct, fg3_pct, apg, rpg, games

    Returns the same dataframe with added columns: efficiency_raw, scoring_score,
    efficiency_score, playmaking_score, rebounding_score, roy_score (0-100),
    sorted descending by roy_score.
    """
    df = rookie_stats.copy()

    # Efficiency blends FG% and 3PT% (equal parts) into one raw number before normalizing
    df["efficiency_raw"] = (df["fg_pct"].fillna(0) + df["fg3_pct"].fillna(0)) / 2

    df["scoring_score"] = _normalize(df["ppg"].fillna(0))
    df["efficiency_score"] = _normalize(df["efficiency_raw"])
    df["playmaking_score"] = _normalize(df["apg"].fillna(0))
    df["rebounding_score"] = _normalize(df["rpg"].fillna(0))

    df["roy_score"] = (
        df["scoring_score"] * WEIGHTS["scoring"]
        + df["efficiency_score"] * WEIGHTS["efficiency"]
        + df["playmaking_score"] * WEIGHTS["playmaking"]
        + df["rebounding_score"] * WEIGHTS["rebounding"]
    ).round(1)

    return df.sort_values("roy_score", ascending=False).reset_index(drop=True)
