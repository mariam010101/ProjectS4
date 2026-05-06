"""
Football Match Predictor — FastAPI backend.

Loads the trained pipeline from `model_bundle.pkl` and exposes endpoints
that serve real match data from the SQLite database populated by `scraper.py`.

Endpoints
---------
GET  /                  Health check
GET  /matches           List matches (filterable by league/status/team)
GET  /matches/{id}      Match details + outcome probabilities + risk
GET  /leagues           List of leagues currently in the database
GET  /teams             List of teams currently in the database
POST /scrape            Trigger a fresh scrape from football-data.co.uk
"""

from datetime import datetime
from typing import List, Optional
import os
import pickle
import subprocess
import sys

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import database

# ----------------------------------------------------------------------
# Application
# ----------------------------------------------------------------------

app = FastAPI(title="Football Match Predictor", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialise database on first import
database.init_database()

# ----------------------------------------------------------------------
# Pydantic schemas
# ----------------------------------------------------------------------


class MatchSummary(BaseModel):
    id: int
    match_date: str
    home_team: str
    away_team: str
    league: str
    status: str
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    odds_home: Optional[float] = None
    odds_draw: Optional[float] = None
    odds_away: Optional[float] = None
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None


class Probabilities(BaseModel):
    home_win: float
    draw: float
    away_win: float


class Prediction(BaseModel):
    home_win: float
    draw: float
    away_win: float
    most_likely: str
    confidence: float
    risk_score: float
    risk_level: str
    used_rolling_form: bool
    explanation: str


# ----------------------------------------------------------------------
# Model loading
# ----------------------------------------------------------------------


def _load_bundle():
    path = os.path.join(os.path.dirname(__file__), "model_bundle.pkl")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"model_bundle.pkl not found at {path}. "
            "Place the trained pipeline next to main.py."
        )
    with open(path, "rb") as f:
        return pickle.load(f)


BUNDLE = _load_bundle()
MODEL = BUNDLE["model"]
SCALER = BUNDLE["scaler"]
FEATURES: List[str] = BUNDLE["features"]
LE_TARGET = BUNDLE["le_target"]
LE_TEAM = BUNDLE["le_team"]

TARGET_CLASSES = list(LE_TARGET.classes_)              # e.g. ['A','D','H']
KNOWN_TEAMS = set(LE_TEAM.classes_)


# ----------------------------------------------------------------------
# Feature engineering for a single match
# ----------------------------------------------------------------------

def _team_id(name: str) -> int:
    """Encode a team name with the bundled LabelEncoder; -1 if unknown."""
    if name in KNOWN_TEAMS:
        return int(LE_TEAM.transform([name])[0])
    return -1


def _season_label(date: str) -> str:
    """Return the football season label for the given date (YYYY-MM-DD)."""
    d = datetime.strptime(date, "%Y-%m-%d")
    if d.month >= 7:
        return f"{d.year}/{(d.year + 1) % 100:02d}"
    return f"{d.year - 1}/{d.year % 100:02d}"


def _fill_missing_stats(match: dict) -> dict:
    """
    Upcoming matches do not yet have in-game statistics.
    Fill them with the average of the last 5 finished matches per team.
    """
    needs = ("home_shots", "away_shots", "home_shots_target", "away_shots_target",
             "home_corners", "away_corners", "home_fouls", "away_fouls",
             "home_yellow", "away_yellow")
    if all(match.get(k) is not None for k in needs):
        return match

    home_form = database.get_team_recent_stats(
        match["home_team"], match["league"], match["match_date"]) or {}
    away_form = database.get_team_recent_stats(
        match["away_team"], match["league"], match["match_date"]) or {}

    fallback = {"shots": 12, "shots_target": 4.5, "corners": 5,
                "fouls": 11, "yellow": 2}
    home = {**fallback, **{k: v for k, v in home_form.items() if v is not None}}
    away = {**fallback, **{k: v for k, v in away_form.items() if v is not None}}

    defaults = {
        "home_shots":         home["shots"],
        "away_shots":         away["shots"],
        "home_shots_target":  home["shots_target"],
        "away_shots_target":  away["shots_target"],
        "home_corners":       home["corners"],
        "away_corners":       away["corners"],
        "home_fouls":         home["fouls"],
        "away_fouls":         away["fouls"],
        "home_yellow":        home["yellow"],
        "away_yellow":        away["yellow"],
    }
    for key, value in defaults.items():
        # Replace both missing keys and explicit None values
        if match.get(key) is None:
            match[key] = value
    return match


def _build_feature_row(match: dict) -> pd.DataFrame:
    """Build a single-row DataFrame matching exactly FEATURES."""
    match = _fill_missing_stats(dict(match))
    d = datetime.strptime(match["match_date"], "%Y-%m-%d")

    season_label = match.get("season") or _season_label(match["match_date"])

    odds_home = float(match.get("odds_home") or 2.5)
    odds_draw = float(match.get("odds_draw") or 3.3)
    odds_away = float(match.get("odds_away") or 2.8)

    home_shots = float(match["home_shots"])
    away_shots = float(match["away_shots"])

    base = {
        "HS":             home_shots,
        "AS":             away_shots,
        "HST":            float(match["home_shots_target"]),
        "AST":            float(match["away_shots_target"]),
        "HC":             float(match["home_corners"]),
        "AC":             float(match["away_corners"]),
        "HF":             float(match["home_fouls"]),
        "AF":             float(match["away_fouls"]),
        "HY":             float(match["home_yellow"]),
        "AY":             float(match["away_yellow"]),
        "B365H":          odds_home,
        "B365D":          odds_draw,
        "B365A":          odds_away,
        "year":           d.year,
        "month":          d.month,
        "dayofweek":      d.weekday(),
        "HomeTeam_enc":   _team_id(match["home_team"]),
        "AwayTeam_enc":   _team_id(match["away_team"]),
        "odds_diff":      odds_home - odds_away,
        "home_advantage": (home_shots - away_shots) / (home_shots + away_shots + 1e-3),
    }

    # League dummies (drop_first => Bundesliga is the reference category)
    league = match["league"]
    base["League_La Liga"]        = int(league == "La Liga")
    base["League_Premier League"] = int(league == "Premier League")
    base["League_Serie A"]        = int(league == "Serie A")

    # Season dummies (drop_first => 2015/16 is the reference)
    for s in ["2016/17", "2017/18", "2018/19", "2019/20",
              "2020/21", "2021/22", "2022/23", "2023/24", "2024/25"]:
        base[f"Season_{s}"] = int(season_label == s)

    # Reorder to match the trained pipeline; fill anything still missing with 0
    row = {col: base.get(col, 0) for col in FEATURES}
    return pd.DataFrame([row], columns=FEATURES)


# ----------------------------------------------------------------------
# Prediction
# ----------------------------------------------------------------------

def predict_match(match: dict) -> Prediction:
    """Return outcome probabilities and a risk score for one match."""
    used_rolling = (match.get("status") != "finished") or \
        any(match.get(k) is None for k in
            ("home_shots", "home_shots_target", "home_corners"))

    X = _build_feature_row(match)
    Xs = SCALER.transform(X)
    proba = MODEL.predict_proba(Xs)[0]

    probs = {cls: float(p) for cls, p in zip(TARGET_CLASSES, proba)}
    p_home = probs.get("H", 0.0)
    p_draw = probs.get("D", 0.0)
    p_away = probs.get("A", 0.0)

    # Most likely outcome
    label_lookup = {"H": "Home win", "D": "Draw", "A": "Away win"}
    top_class = max(probs, key=probs.get)
    most_likely = label_lookup.get(top_class, top_class)
    confidence = float(probs[top_class])

    # Risk score: 1 - max(probability), scaled to 0-100.
    # High value -> outcome is uncertain -> risky bet.
    risk_score = round((1.0 - confidence) * 100, 2)
    if risk_score < 35:
        risk_level = "low"
    elif risk_score < 55:
        risk_level = "medium"
    else:
        risk_level = "high"

    if used_rolling:
        explanation = ("In-game statistics are not yet available for this match; "
                       "rolling averages from each team's last finished games "
                       "were used.")
    else:
        explanation = "Prediction based on the actual match statistics."

    return Prediction(
        home_win=round(p_home, 4),
        draw=round(p_draw, 4),
        away_win=round(p_away, 4),
        most_likely=most_likely,
        confidence=round(confidence, 4),
        risk_score=risk_score,
        risk_level=risk_level,
        used_rolling_form=used_rolling,
        explanation=explanation,
    )


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "status": "ok",
        "model_loaded": MODEL is not None,
        "model_name": BUNDLE.get("model_name", "unknown"),
        "n_features": len(FEATURES),
        "n_known_teams": len(KNOWN_TEAMS),
        "matches_in_db": _matches_count(),
    }


def _matches_count():
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM Matches")
    n = cur.fetchone()[0]
    conn.close()
    return n


@app.get("/leagues")
def get_leagues():
    return database.list_leagues()


@app.get("/teams")
def get_teams():
    return database.list_teams()


@app.get("/matches", response_model=List[MatchSummary])
def get_matches(
    league: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="upcoming or finished"),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    rows = database.query_matches(league=league, status=status,
                                  search=search, limit=limit)
    out: List[MatchSummary] = []
    for r in rows:
        try:
            pred = predict_match(r)
            r["risk_score"] = pred.risk_score
            r["risk_level"] = pred.risk_level
        except Exception as e:
            r["risk_score"] = None
            r["risk_level"] = None
            print(f"[predict] match {r.get('id')}: {e}")
        out.append(MatchSummary(**{k: r.get(k) for k in MatchSummary.model_fields}))
    return out


@app.get("/matches/{match_id}")
def get_match_details(match_id: int):
    match = database.get_match_by_id(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    pred = predict_match(match)

    # Cache the prediction in MatchFeatures so the relational table is populated
    try:
        database.upsert_match_features(
            match_id,
            risk_score=pred.risk_score,
            confidence=pred.confidence,
            home_win_rate=pred.home_win,
            away_win_rate=pred.away_win,
        )
    except Exception as e:
        print(f"[features cache] match {match_id}: {e}")

    return {"match": match, "prediction": pred.model_dump()}


@app.post("/scrape")
def trigger_scrape():
    """Run scraper.py as a subprocess and return its stdout."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(here, "scraper.py")],
            capture_output=True, text=True, timeout=300, cwd=here,
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-2000:],
            "returncode": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Scraper timed out")


# ----------------------------------------------------------------------
# Static UI
# ----------------------------------------------------------------------

INDEX_PATH = os.path.join(os.path.dirname(__file__), "index.html")


@app.get("/ui")
def serve_ui():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH)
    raise HTTPException(status_code=404, detail="index.html not found")


# ----------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
