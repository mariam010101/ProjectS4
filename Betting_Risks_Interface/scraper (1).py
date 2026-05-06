"""
Real-data scraper.

Pulls real, up-to-date football match data from football-data.co.uk:
  * `mmz4281/<season>/<code>.csv` — completed matches with full statistics + odds
  * `fixtures.csv`               — upcoming fixtures with pre-match odds

Supported leagues:
    E0  -> Premier League
    SP1 -> La Liga
    D1  -> Bundesliga
    I1  -> Serie A

Usage:
    python scraper.py            # scrape current season + upcoming fixtures
    python scraper.py --season 2425 --leagues E0 SP1
"""

import argparse
import io
import sys
from datetime import datetime
from urllib.request import Request, urlopen

import pandas as pd

from database import init_database, insert_or_replace_matches

BASE_URL = "https://www.football-data.co.uk"

LEAGUE_NAMES = {
    "E0":  "Premier League",
    "SP1": "La Liga",
    "D1":  "Bundesliga",
    "I1":  "Serie A",
}

# Mapping from football-data.co.uk CSV columns to our DB columns
HISTORICAL_COLUMN_MAP = {
    "Date":  "match_date",
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "FTHG":  "home_goals",
    "FTAG":  "away_goals",
    "HS":    "home_shots",
    "AS":    "away_shots",
    "HST":   "home_shots_target",
    "AST":   "away_shots_target",
    "HC":    "home_corners",
    "AC":    "away_corners",
    "HF":    "home_fouls",
    "AF":    "away_fouls",
    "HY":    "home_yellow",
    "AY":    "away_yellow",
    "B365H": "odds_home",
    "B365D": "odds_draw",
    "B365A": "odds_away",
}

FIXTURES_COLUMN_MAP = {
    "Date":     "match_date",
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "B365H":    "odds_home",
    "B365D":    "odds_draw",
    "B365A":    "odds_away",
    "Div":      "league_code",
}


def _http_get(url, timeout=30):
    """Download a URL with a browser User-Agent to avoid 403 responses."""
    req = Request(url, headers={
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
    })
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _parse_date(value):
    """Parse the day-first date strings used by football-data.co.uk."""
    if pd.isna(value) or value == "":
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def fetch_historical(league_code, season_code):
    """Download finished matches for one league/season."""
    url = f"{BASE_URL}/mmz4281/{season_code}/{league_code}.csv"
    print(f"  Fetching {url} ...", end=" ", flush=True)
    try:
        raw = _http_get(url)
    except Exception as e:
        print(f"failed ({e})")
        return []

    df = pd.read_csv(io.BytesIO(raw))
    keep_cols = [c for c in HISTORICAL_COLUMN_MAP if c in df.columns]
    df = df[keep_cols].rename(columns=HISTORICAL_COLUMN_MAP)
    df["league"] = LEAGUE_NAMES.get(league_code, league_code)
    df["season"] = f"20{season_code[:2]}/{season_code[2:]}"
    df["status"] = "finished"
    df["match_date"] = df["match_date"].map(_parse_date)
    df = df.dropna(subset=["match_date", "home_team", "away_team"])

    rows = df.to_dict("records")
    print(f"got {len(rows)} matches")
    return rows


def fetch_fixtures():
    """Download upcoming fixtures (with pre-match odds) from football-data.co.uk."""
    url = f"{BASE_URL}/fixtures.csv"
    print(f"  Fetching {url} ...", end=" ", flush=True)
    try:
        raw = _http_get(url)
    except Exception as e:
        print(f"failed ({e})")
        return []

    df = pd.read_csv(io.BytesIO(raw))
    keep_cols = [c for c in FIXTURES_COLUMN_MAP if c in df.columns]
    df = df[keep_cols].rename(columns=FIXTURES_COLUMN_MAP)

    df = df[df["league_code"].isin(LEAGUE_NAMES)]
    df["league"] = df["league_code"].map(LEAGUE_NAMES)
    df = df.drop(columns=["league_code"])

    today = datetime.now()
    df["season"] = f"{today.year}/{(today.year + 1) % 100:02d}" \
        if today.month >= 7 else \
        f"{today.year - 1}/{today.year % 100:02d}"
    df["status"] = "upcoming"
    df["match_date"] = df["match_date"].map(_parse_date)
    df = df.dropna(subset=["match_date", "home_team", "away_team"])

    rows = df.to_dict("records")
    print(f"got {len(rows)} fixtures")
    return rows


def current_season_code():
    """Return the football-data.co.uk season code for today (e.g. '2425')."""
    today = datetime.now()
    if today.month >= 7:
        start, end = today.year, today.year + 1
    else:
        start, end = today.year - 1, today.year
    return f"{start % 100:02d}{end % 100:02d}"


def run(seasons, leagues):
    """Run the full scrape: history for the given seasons + upcoming fixtures."""
    init_database()
    total = 0

    print("Loading historical matches...")
    for season in seasons:
        for league in leagues:
            rows = fetch_historical(league, season)
            inserted = insert_or_replace_matches(rows)
            total += inserted

    print("\nLoading upcoming fixtures...")
    rows = fetch_fixtures()
    inserted = insert_or_replace_matches(rows)
    total += inserted

    print(f"\nDone. {total} rows inserted/updated.")


def main():
    parser = argparse.ArgumentParser(description="Football match scraper")
    parser.add_argument("--season", action="append", default=None,
                        help="Season code, e.g. 2425. May be repeated. "
                             "Defaults to the last 3 seasons including current.")
    parser.add_argument("--leagues", nargs="+", default=list(LEAGUE_NAMES.keys()),
                        help="League codes to scrape (default: all four).")
    args = parser.parse_args()

    if args.season:
        seasons = args.season
    else:
        cur = current_season_code()
        cur_start = int(cur[:2])
        seasons = []
        for back in range(3):
            s = (cur_start - back) % 100
            e = (s + 1) % 100
            seasons.append(f"{s:02d}{e:02d}")
        seasons = list(reversed(seasons))

    print(f"Seasons: {seasons}")
    print(f"Leagues: {args.leagues}\n")
    run(seasons, args.leagues)


if __name__ == "__main__":
    main()
