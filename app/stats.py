"""
Computes season summary stats (PPG, FG%, 3FG%, FT%) from the unified shots
dataset. Used by the player card at the top of the dashboard.

IMPORTANT LIMITATION: for NBA-season rows (once fetch_nba_games.py starts
producing them), nba_api's shotchartdetail endpoint only returns *field goal*
attempts - it does not include free throws. So once NBA data exists alongside
Summer League data, FT% and PPG computed across both stages combined will
undercount NBA free throws specifically (Summer League FT tracking is
complete via the ESPN fetcher; NBA FT tracking would need a separate
endpoint - e.g. nba_api's playergamelog already pulled by fetch_nba_games.py
has the real FT numbers, just not merged into this calculation yet).
"""
import pandas as pd


def compute_season_stats(df: pd.DataFrame) -> dict:
    """Returns PPG, FG%, 3FG%, FT%, and games played from a shots dataframe."""
    if df.empty:
        return {"ppg": 0.0, "fg_pct": 0.0, "fg3_pct": 0.0, "ft_pct": 0.0, "games": 0}

    fg_rows = df[df["shot_type"].isin(["2PT", "3PT"])]
    three_rows = df[df["shot_type"] == "3PT"]
    two_rows = df[df["shot_type"] == "2PT"]
    ft_rows = df[df["shot_type"] == "FT"]

    fg_made = fg_rows["shot_made"].sum()
    fg_attempts = len(fg_rows)
    fg_pct = (fg_made / fg_attempts * 100) if fg_attempts else 0.0

    three_made = three_rows["shot_made"].sum()
    three_attempts = len(three_rows)
    fg3_pct = (three_made / three_attempts * 100) if three_attempts else 0.0

    ft_made = ft_rows["shot_made"].sum()
    ft_attempts = len(ft_rows)
    ft_pct = (ft_made / ft_attempts * 100) if ft_attempts else 0.0

    two_made = two_rows["shot_made"].sum()
    points = two_made * 2 + three_made * 3 + ft_made * 1

    games = df["game_date"].nunique()
    ppg = points / games if games else 0.0

    return {
        "ppg": round(ppg, 1),
        "fg_pct": round(fg_pct, 1),
        "fg3_pct": round(fg3_pct, 1),
        "ft_pct": round(ft_pct, 1),
        "games": int(games),
        "fg_made": int(fg_made), "fg_attempts": int(fg_attempts),
        "ft_made": int(ft_made), "ft_attempts": int(ft_attempts),
    }
