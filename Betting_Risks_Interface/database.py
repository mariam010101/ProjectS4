"""
SQLite database — original normalized schema.

Tables (preserved from the original project design):

    Teams         (TeamID PK, TeamName UNIQUE)
    Leagues       (LeagueID PK, LeagueName UNIQUE)
    Seasons       (SeasonID PK, SeasonName UNIQUE)
    Matches       (MatchID PK, MatchDate, HomeTeamID FK, AwayTeamID FK,
                   HomeGoals, AwayGoals, Result, HalfTimeResult,
                   HomeShots, AwayShots, HomeShotsTarget, AwayShotsTarget,
                   HomeCorners, AwayCorners, HomeFouls, AwayFouls,
                   HomeYellow, AwayYellow, HomeOdds, DrawOdds, AwayOdds,
                   LeagueID FK, SeasonID FK, Status)
    MatchFeatures (FeatureID PK, MatchID FK, RiskScore, ConfidenceScore,
                   HomeWinRate, AwayWinRate, AvgHomeGoals, AvgAwayGoals,
                   ExpectedValue)

The tables start EMPTY. Real matches are inserted by `scraper.py` from
football-data.co.uk — there is no sample/fictional data in this file.
"""

import os
import sqlite3

DB_FILE = os.path.join(os.path.dirname(__file__), "football_predictor.db")


def get_connection():
    """Open a SQLite connection that returns rows as dict-like objects."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database():
    """Create all tables if they do not exist yet. Inserts no data."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS Teams (
            TeamID   INTEGER PRIMARY KEY AUTOINCREMENT,
            TeamName TEXT UNIQUE NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS Leagues (
            LeagueID   INTEGER PRIMARY KEY AUTOINCREMENT,
            LeagueName TEXT UNIQUE NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS Seasons (
            SeasonID   INTEGER PRIMARY KEY AUTOINCREMENT,
            SeasonName TEXT UNIQUE NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS Matches (
            MatchID          INTEGER PRIMARY KEY AUTOINCREMENT,
            MatchDate        TEXT NOT NULL,
            HomeTeamID       INTEGER NOT NULL,
            AwayTeamID       INTEGER NOT NULL,
            LeagueID         INTEGER NOT NULL,
            SeasonID         INTEGER,
            Status           TEXT NOT NULL DEFAULT 'upcoming', -- 'upcoming' | 'finished'
            HomeGoals        INTEGER,
            AwayGoals        INTEGER,
            Result           CHAR(1),
            HalfTimeResult   CHAR(1),
            HomeShots        INTEGER,
            AwayShots        INTEGER,
            HomeShotsTarget  INTEGER,
            AwayShotsTarget  INTEGER,
            HomeCorners      INTEGER,
            AwayCorners      INTEGER,
            HomeFouls        INTEGER,
            AwayFouls        INTEGER,
            HomeYellow       INTEGER,
            AwayYellow       INTEGER,
            HomeOdds         REAL,
            DrawOdds         REAL,
            AwayOdds         REAL,
            FOREIGN KEY (HomeTeamID) REFERENCES Teams(TeamID),
            FOREIGN KEY (AwayTeamID) REFERENCES Teams(TeamID),
            FOREIGN KEY (LeagueID)   REFERENCES Leagues(LeagueID),
            FOREIGN KEY (SeasonID)   REFERENCES Seasons(SeasonID),
            UNIQUE (MatchDate, HomeTeamID, AwayTeamID)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS MatchFeatures (
            FeatureID        INTEGER PRIMARY KEY AUTOINCREMENT,
            MatchID          INTEGER NOT NULL UNIQUE,
            RiskScore        REAL,
            ConfidenceScore  REAL,
            HomeWinRate      REAL,
            AwayWinRate      REAL,
            AvgHomeGoals     REAL,
            AvgAwayGoals     REAL,
            ExpectedValue    REAL,
            FOREIGN KEY (MatchID) REFERENCES Matches(MatchID) ON DELETE CASCADE
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_date     ON Matches(MatchDate)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_status   ON Matches(Status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_league   ON Matches(LeagueID)")

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Lookup helpers — get-or-create rows in the dimension tables.
# ---------------------------------------------------------------------------

def _get_or_create(cur, table, name_column, name):
    """Return the primary key of a row in a lookup table, creating it if absent."""
    if name is None:
        return None
    cur.execute(f"SELECT {table[:-1]}ID FROM {table} WHERE {name_column} = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(f"INSERT INTO {table} ({name_column}) VALUES (?)", (name,))
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Bulk upsert — used by scraper.py
# ---------------------------------------------------------------------------

# Map between snake_case keys used in Python code and CamelCase columns in the DB
PY_TO_DB = {
    "match_date":         "MatchDate",
    "status":             "Status",
    "home_goals":         "HomeGoals",
    "away_goals":         "AwayGoals",
    "result":             "Result",
    "half_time_result":   "HalfTimeResult",
    "home_shots":         "HomeShots",
    "away_shots":         "AwayShots",
    "home_shots_target":  "HomeShotsTarget",
    "away_shots_target":  "AwayShotsTarget",
    "home_corners":       "HomeCorners",
    "away_corners":       "AwayCorners",
    "home_fouls":         "HomeFouls",
    "away_fouls":         "AwayFouls",
    "home_yellow":        "HomeYellow",
    "away_yellow":        "AwayYellow",
    "odds_home":          "HomeOdds",
    "odds_draw":          "DrawOdds",
    "odds_away":          "AwayOdds",
}


def insert_or_replace_matches(rows):
    """
    Bulk-insert match rows. Each row is a dict with snake_case keys:
        match_date, league, season, home_team, away_team, status, ...

    Team / League / Season text values are resolved into IDs (created on demand).
    Existing rows with the same (MatchDate, HomeTeamID, AwayTeamID) are replaced.
    """
    if not rows:
        return 0

    conn = get_connection()
    cur = conn.cursor()
    written = 0

    for row in rows:
        home_id   = _get_or_create(cur, "Teams",   "TeamName",   row.get("home_team"))
        away_id   = _get_or_create(cur, "Teams",   "TeamName",   row.get("away_team"))
        league_id = _get_or_create(cur, "Leagues", "LeagueName", row.get("league"))
        season_id = _get_or_create(cur, "Seasons", "SeasonName", row.get("season"))

        if not (home_id and away_id and league_id and row.get("match_date")):
            continue

        # Compute Result from goals if not provided
        if row.get("result") is None and row.get("home_goals") is not None \
                and row.get("away_goals") is not None:
            hg, ag = row["home_goals"], row["away_goals"]
            row["result"] = "H" if hg > ag else ("A" if hg < ag else "D")

        cur.execute("""
            INSERT OR REPLACE INTO Matches (
                MatchDate, HomeTeamID, AwayTeamID, LeagueID, SeasonID, Status,
                HomeGoals, AwayGoals, Result, HalfTimeResult,
                HomeShots, AwayShots, HomeShotsTarget, AwayShotsTarget,
                HomeCorners, AwayCorners, HomeFouls, AwayFouls,
                HomeYellow, AwayYellow, HomeOdds, DrawOdds, AwayOdds
            ) VALUES (?,?,?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?,?)
        """, (
            row.get("match_date"), home_id, away_id, league_id, season_id,
            row.get("status", "upcoming"),
            row.get("home_goals"), row.get("away_goals"),
            row.get("result"), row.get("half_time_result"),
            row.get("home_shots"), row.get("away_shots"),
            row.get("home_shots_target"), row.get("away_shots_target"),
            row.get("home_corners"), row.get("away_corners"),
            row.get("home_fouls"), row.get("away_fouls"),
            row.get("home_yellow"), row.get("away_yellow"),
            row.get("odds_home"), row.get("odds_draw"), row.get("odds_away"),
        ))
        written += 1

    conn.commit()
    conn.close()
    return written


# ---------------------------------------------------------------------------
# Read helpers — return rows as snake_case dicts (joined with dimension tables).
# ---------------------------------------------------------------------------

_BASE_SELECT = """
    SELECT
        m.MatchID         AS id,
        m.MatchDate       AS match_date,
        m.Status          AS status,
        ht.TeamName       AS home_team,
        at.TeamName       AS away_team,
        l.LeagueName      AS league,
        s.SeasonName      AS season,
        m.HomeGoals       AS home_goals,
        m.AwayGoals       AS away_goals,
        m.Result          AS result,
        m.HalfTimeResult  AS half_time_result,
        m.HomeShots       AS home_shots,
        m.AwayShots       AS away_shots,
        m.HomeShotsTarget AS home_shots_target,
        m.AwayShotsTarget AS away_shots_target,
        m.HomeCorners     AS home_corners,
        m.AwayCorners     AS away_corners,
        m.HomeFouls       AS home_fouls,
        m.AwayFouls       AS away_fouls,
        m.HomeYellow      AS home_yellow,
        m.AwayYellow      AS away_yellow,
        m.HomeOdds        AS odds_home,
        m.DrawOdds        AS odds_draw,
        m.AwayOdds        AS odds_away
    FROM Matches m
    JOIN Teams   ht ON m.HomeTeamID = ht.TeamID
    JOIN Teams   at ON m.AwayTeamID = at.TeamID
    JOIN Leagues l  ON m.LeagueID   = l.LeagueID
    LEFT JOIN Seasons s ON m.SeasonID = s.SeasonID
"""


def query_matches(league=None, status=None, search=None, limit=200):
    """List matches with optional filters."""
    conn = get_connection()
    cur = conn.cursor()
    clauses, params = ["1=1"], []
    if league:
        clauses.append("l.LeagueName = ?")
        params.append(league)
    if status:
        clauses.append("m.Status = ?")
        params.append(status)
    if search:
        clauses.append("(ht.TeamName LIKE ? OR at.TeamName LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    sql = f"{_BASE_SELECT} WHERE {' AND '.join(clauses)} " \
          f"ORDER BY m.MatchDate DESC, m.MatchID DESC LIMIT ?"
    params.append(limit)
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_match_by_id(match_id):
    """Fetch one match by its primary key."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"{_BASE_SELECT} WHERE m.MatchID = ?", (match_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def list_teams():
    """All team names, alphabetically."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT TeamName FROM Teams ORDER BY TeamName")
    teams = [r["TeamName"] for r in cur.fetchall()]
    conn.close()
    return teams


def list_leagues():
    """All league names currently in the database."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT LeagueName FROM Leagues ORDER BY LeagueName")
    leagues = [r["LeagueName"] for r in cur.fetchall()]
    conn.close()
    return leagues


def get_team_recent_stats(team, league, before_date, n=5):
    """
    Average per-match in-game statistics for `team` in the most recent `n`
    finished matches (in the same league) before `before_date`.

    Used to fill the post-match feature slots when predicting an upcoming
    match (for which no in-game stats are known yet).
    """
    conn = get_connection()
    cur = conn.cursor()
    sql = f"""
        {_BASE_SELECT}
        WHERE l.LeagueName = ?
          AND m.Status = 'finished'
          AND m.MatchDate < ?
          AND (ht.TeamName = ? OR at.TeamName = ?)
        ORDER BY m.MatchDate DESC
        LIMIT ?
    """
    cur.execute(sql, (league, before_date, team, team, n))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return None

    def _val(row, home_key, away_key):
        return row[home_key] if row["home_team"] == team else row[away_key]

    def _avg(home_key, away_key):
        vals = [_val(r, home_key, away_key) for r in rows
                if _val(r, home_key, away_key) is not None]
        return sum(vals) / len(vals) if vals else None

    return {
        "shots":        _avg("home_shots", "away_shots"),
        "shots_target": _avg("home_shots_target", "away_shots_target"),
        "corners":      _avg("home_corners", "away_corners"),
        "fouls":        _avg("home_fouls", "away_fouls"),
        "yellow":       _avg("home_yellow", "away_yellow"),
        "n_matches":    len(rows),
    }


# ---------------------------------------------------------------------------
# MatchFeatures — predicted risk/confidence cached per match.
# ---------------------------------------------------------------------------

def upsert_match_features(match_id, *, risk_score=None, confidence=None,
                          home_win_rate=None, away_win_rate=None,
                          avg_home_goals=None, avg_away_goals=None,
                          expected_value=None):
    """Insert or update a row in MatchFeatures for the given match."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO MatchFeatures
            (MatchID, RiskScore, ConfidenceScore, HomeWinRate, AwayWinRate,
             AvgHomeGoals, AvgAwayGoals, ExpectedValue)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(MatchID) DO UPDATE SET
            RiskScore       = excluded.RiskScore,
            ConfidenceScore = excluded.ConfidenceScore,
            HomeWinRate     = excluded.HomeWinRate,
            AwayWinRate     = excluded.AwayWinRate,
            AvgHomeGoals    = excluded.AvgHomeGoals,
            AvgAwayGoals    = excluded.AvgAwayGoals,
            ExpectedValue   = excluded.ExpectedValue
    """, (match_id, risk_score, confidence, home_win_rate, away_win_rate,
          avg_home_goals, avg_away_goals, expected_value))
    conn.commit()
    conn.close()


def get_match_features(match_id):
    """Return the cached features for a match, or None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM MatchFeatures WHERE MatchID = ?", (match_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


if __name__ == "__main__":
    init_database()
    print(f"Database ready at {DB_FILE}")
    print("Tables created (empty):")
    conn = get_connection()
    for t in ("Teams", "Leagues", "Seasons", "Matches", "MatchFeatures"):
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n} rows")
    conn.close()
