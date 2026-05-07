# Football Prediction & Betting Risk System

A two-layer data project combining a **machine learning pipeline** for match outcome prediction with a **fully normalised SQL Server database** for structured storage, querying, and access control. The system processes 10 seasons of English Premier League data (2015/16–2024/25), estimates result probabilities, and exposes computed risk features through a relational database designed to production database standards.Thpugh the interface uses real up-to-date matches by data scraping. 

---

## Table of contents

- [Project overview](#project-overview)
- [Repository structure](#repository-structure)
- [Data source](#data-source)
- [Machine learning layer](#machine-learning-layer)
  - [Data cleaning](#data-cleaning)
  - [Feature engineering](#feature-engineering)
  - [Models & results](#models--results)
  - [Risk scoring output](#risk-scoring-output)
- [Database layer](#database-layer)
  - [Schema & normalization](#schema--normalization)
  - [ER diagram summary](#er-diagram-summary)
  - [DDL & data loading](#ddl--data-loading)
  - [Views](#views)
  - [Stored procedures](#stored-procedures)
  - [Triggers](#triggers)
  - [Indexes](#indexes)
  - [Access control (DCL)](#access-control-dcl)
- [How the two layers connect](#how-the-two-layers-connect)
- [Setup & usage](#setup--usage)
- [Requirements](#requirements)

---

## Project overview

The goal is not to predict match outcomes with certainty, but to **estimate result probabilities** and identify potential value in betting decisions based on historical data. The project operates in two stages:

1. **ML layer (Python / Jupyter)** — cleans raw CSVs, engineers features, trains and evaluates four classifiers, and exports a cleaned dataset and serialised model bundle.
2. **SQL layer (T-SQL / SQL Server)** — receives the cleaned CSV via `BULK INSERT`, normalises the data into a relational schema, exposes analytics through views and stored procedures, and enforces data integrity through triggers and constraints.

---

## Repository structure

```
football-prediction/
│
├── BettingRisks.ipynb          # Full ML pipeline (EDA → cleaning → training → export)
├── FootballPrediction.sql      # Complete SQL Server deployment script
├── S4data 2.csv                # Cleaned dataset exported from the notebook (BULK INSERT source)
├── model_bundle.pkl            # Serialised best model + scaler + feature list
└── README.md
```

---

## Data source

Historical match data was obtained from [Football-Data.co.uk](https://www.football-data.co.uk), which provides structured CSV files per league per season. The English Premier League (`E0`) was selected for its data consistency, completeness, and detailed Bet365 odds columns.

**Coverage:** 10 seasons, 2015/16 through 2024/25  
**Raw rows:** 14,461 matches  
**Clean rows after preprocessing:** 14,455 (6 incomplete rows removed)

---

## Machine learning layer

### Data cleaning

The raw dataset contains over 100 columns spanning multiple bookmakers. A focused subset of 26 columns was selected based on interpretability, predictive value, and cross-season consistency:

| Category | Columns |
|---|---|
| Match info | `Date`, `League`, `Season` |
| Teams | `HomeTeam`, `AwayTeam` |
| Full-time result (target) | `FTHG`, `FTAG`, `FTR` |
| Half-time result | `HTHG`, `HTAG`, `HTR` |
| Match stats | `HS`, `AS`, `HST`, `AST`, `HC`, `AC`, `HF`, `AF`, `HY`, `AY`, `HR`, `AR` |
| Betting odds | `B365H`, `B365D`, `B365A` |

**Cleaning steps applied:**

- Null removal — 6 rows with any missing value were dropped (< 0.05% of data)
- Duplicate check — 0 duplicates found
- Outlier detection via IQR method on all numeric columns
- `StandardScaler` applied before distance-based models (KNN)
- Highly correlated features (r > 0.95) removed via upper-triangle correlation matrix to reduce dimensionality

### Feature engineering

Beyond the raw columns, the following engineered features were constructed:

- Rolling win rates per team (home and away separately)
- Average goals scored and conceded per team per context
- Implied probabilities derived from Bet365 odds (`1 / odds`, normalised to sum to 1)
- ANOVA test confirmed betting odds differ significantly across outcome classes (p < 0.05), validating their inclusion as features

The original dataset has a class imbalance (Home Win ~44%, Draw ~25%, Away Win ~31%). **SMOTE** (Synthetic Minority Over-sampling Technique) was applied to the training set to balance all three classes to 33.3% each before model fitting.

### Models & results

Four classifiers were trained with hyperparameter tuning via `GridSearchCV` / `RandomizedSearchCV` (3–5-fold cross-validation):

| Model | Best CV score | Test accuracy | Notes |
|---|---|---|---|
| Logistic Regression | 0.640 | ~64% | `solver=liblinear`, `C=1.67` |
| K-Nearest Neighbors | 0.570 | 58.8% | `k=15`, Manhattan distance, uniform weights |
| Decision Tree | 0.581 | ~58% | `max_depth=10`, `min_samples_leaf=2` |
| **K-Nearest Neighbors (SMOTE)** | — | **68%** | Best F1 overall after balancing |

The best-performing model (selected by macro F1-score) is serialised alongside the scaler and feature list into `model_bundle.pkl` using `pickle`.

**Best model classification report (KNN with SMOTE, test set):**

```
              precision    recall    f1-score   support
   Home Win       0.71      0.76      0.74      1278
       Draw       0.65      0.77      0.71      1278
   Away Win       0.70      0.52      0.60      1278

   accuracy                           0.68      3834
  macro avg       0.69      0.68      0.68      3834
```

### Risk scoring output

After training, the notebook computes per-match risk features that are written to the cleaned CSV exported for the SQL layer:

- `HomeWinRate` / `AwayWinRate` — rolling historical win rates
- `AvgHomeGoals` / `AvgAwayGoals` — rolling average goals per team context
- `RiskScore` — composite metric combining implied probabilities and model confidence
- `ExpectedValue` — estimated EV of a bet given the predicted probability vs offered odds
- `ConfidenceScore` — model's predicted probability for the most likely outcome

These five columns feed directly into the `MatchFeatures` table in the database.

---

## Database layer

### Schema & normalization

The database (`FootballPredictionDB`) is built to **Third Normal Form (3NF)**:

**1NF** — all columns are atomic; no repeating groups or multi-valued cells.

**2NF** — team names, league names, and season names that appeared as repeated strings in the flat CSV were extracted into their own tables (`Teams`, `Leagues`, `Seasons`) with surrogate integer PKs. `Matches` references them by ID, eliminating partial dependencies.

**3NF** — ML-computed analytics (win rates, risk scores, confidence) are functionally dependent on the match via a computed pipeline, not on the raw match attributes themselves. They are stored in a separate `MatchFeatures` table, eliminating transitive dependencies.

### ER diagram summary

```
Teams ──────────┐
                ├──── Matches ──── MatchFeatures
Teams ──────────┘        │
                         │
Leagues ─────────────────┤
                         │
Seasons ─────────────────┘

raw_matches  (staging — flat CSV, no FKs, ETL source)
```

| Relationship | Cardinality | FK column |
|---|---|---|
| Teams → Matches (home) | 1 : many | `Matches.HomeTeamID` |
| Teams → Matches (away) | 1 : many | `Matches.AwayTeamID` |
| Leagues → Matches | 1 : many | `Matches.LeagueID` |
| Seasons → Matches | 1 : many | `Matches.SeasonID` |
| Matches → MatchFeatures | 1 : 1 | `MatchFeatures.MatchID` |

There is no many-to-many relationship. The `Matches` table acts as the central hub.

### DDL & data loading

The SQL script creates all objects idempotently — it drops and recreates the database on each run. The `raw_matches` staging table uses loose typing (`FLOAT` for numeric columns, `VARCHAR` for dates) to accept imperfectly formatted CSV data from the ML export.

Data is loaded from the cleaned CSV using SQL Server's `BULK INSERT`:

```sql
BULK INSERT raw_matches
FROM 'S4data 2.csv'
WITH (
    FIELDTERMINATOR = ';',
    ROWTERMINATOR   = '0x0a',
    FIRSTROW        = 2,
    TABLOCK
);
```

After loading into `raw_matches`, normalised data is distributed into `Teams`, `Leagues`, `Seasons`, `Matches`, and `MatchFeatures` via `INSERT ... SELECT` statements.

### Views

Four views are defined over `raw_matches`:

| View | Type | Purpose |
|---|---|---|
| `vw_MatchSummary` | Projection | Exposes 8 key columns, hiding statistical noise from general consumers |
| `vw_HighScoringMatches` | Filter | Rows where total goals ≥ 4 — targets the over/under betting market |
| `vw_LeagueStats` | Aggregation | Total matches and average goals per league (`GROUP BY league`) |
| `vw_TeamPerformance` | Conditional aggregation | Per-team home match count, win count, and avg goals using `CASE WHEN` inside `SUM()` |

Views act as a stable API layer — role permissions are granted on views, not base tables.

### Stored procedures

Ten stored procedures cover parameterised retrieval, aggregation, and prediction logic:

| Procedure | Input | Purpose |
|---|---|---|
| `sp_GetMatchesByLeague` | `@LeagueName` | All matches for a league, date-ordered |
| `sp_GetMatchesByTeam` | `@TeamName` | All matches (home or away) for a team |
| `sp_GetMatchesByDateRange` | `@StartDate`, `@EndDate` | Time-window filtering |
| `sp_GetHighScoringMatches` | `@MinGoals` | Parameterised threshold (unlike the hard-coded view) |
| `sp_GetHeadToHead` | `@Team1`, `@Team2` | All matches between two specific teams, either order |
| `sp_GetLeagueStatistics` | — | Aggregated match count + avg goals per league |
| `sp_GetTeamWins` | `@TeamName` | Correct win count across both home and away contexts |
| `sp_GetTeamGoalStats` | `@TeamName` | Separate home and away goal averages via conditional aggregation |
| `sp_GetAverageOddsByLeague` | — | Average home/draw/away odds per league |
| `sp_PredictMatchOutcome` | `@HomeOdds`, `@DrawOdds`, `@AwayOdds` | Rules-based T-SQL prediction: lowest odds = predicted winner |

`sp_PredictMatchOutcome` is the only procedure containing control flow (`DECLARE`, `IF/ELSE`) — it implements a baseline odds-driven predictor entirely inside the database engine, used as a sanity check against `MatchFeatures.ConfidenceScore`.

### Triggers

Ten triggers enforce data integrity and automate derived values on `raw_matches`:

| Trigger | Type | Rule enforced |
|---|---|---|
| `tr_PreventNegativeGoals` | `INSTEAD OF INSERT` | Goals must be ≥ 0; intercepts before any write |
| `tr_PreventSameTeamMatch` | `AFTER INSERT, UPDATE` | Home team ≠ away team |
| `tr_UpdateResultAutomatically` | `AFTER INSERT` | Auto-computes `result` (H/A/D) from goal columns |
| `tr_PreventNullTeams` | `AFTER INSERT, UPDATE` | Team name columns must not be NULL |
| `tr_LogDeletedMatches` | `AFTER DELETE` | Writes deleted rows to `DeletedMatchesLog` with timestamp |
| `tr_ValidateOdds` | `AFTER INSERT, UPDATE` | Odds must be strictly > 1 |
| `tr_PreventFutureDates` | `AFTER INSERT, UPDATE` | Match date must not be in the future |
| `tr_UppercaseLeague` | `AFTER INSERT, UPDATE` | Normalises league names to UPPER CASE automatically |
| `tr_PreventDuplicateMatch` | `AFTER INSERT` | Rejects duplicate (home_team, away_team, match_date) combinations |
| `tr_PreventNegativeStats` | `AFTER INSERT, UPDATE` | Shots, corners, and fouls must be ≥ 0 |

`tr_UpdateResultAutomatically` and `tr_UppercaseLeague` are compute triggers — they do not reject inserts, they silently correct derived or formatting issues that the CSV export may introduce.

### Indexes

Six non-clustered indexes on `raw_matches` support the most frequent query patterns:

| Index | Column(s) | Supports |
|---|---|---|
| `idx_raw_matches_match_date` | `match_date` | Date ordering, range queries, future-date trigger |
| `idx_raw_matches_league` | `league` | League filtering, `GROUP BY league` |
| `idx_raw_matches_season` | `season` | Season-cohort analysis, train/test splits |
| `idx_raw_matches_league_season` | `(league, season)` | Combined league + season queries (composite) |
| `idx_raw_matches_home_team` | `home_team` | Team filtering, `GROUP BY home_team` in views |
| `idx_raw_matches_away_team` | `away_team` | Away-team filtering, head-to-head queries |

Because `raw_matches` is write-once (loaded via `BULK INSERT`, then read-only), the read performance gains outweigh the write overhead. `TABLOCK` in the `BULK INSERT` statement minimises index update contention during the initial load.

### Access control (DCL)

Five roles model a realistic multi-team environment with least-privilege access:

| Role | SELECT | INSERT | UPDATE | DELETE | Scope |
|---|---|---|---|---|---|
| `AdminRole` | ✓ | ✓ | ✓ | ✓ | All 5 tables |
| `AnalystRole` | ✓ | — | — | — | All tables (read-only) |
| `InterfaceUserRole` | ✓ | ✓ | ✓ | — | `Matches` only |
| `MLSystemRole` | ✓ | ✓ | ✓ | — | `MatchFeatures` only |
| `ResearcherRole` | ✓ | — | — | — | `Matches` + `MatchFeatures` only |

`MLSystemRole` is the database identity used by the Python pipeline when writing prediction results back into `MatchFeatures` — it has no access to raw match events. `ResearcherRole` can read analytical outputs without ever touching the staging or master data tables.

---

## How the two layers connect

```
Football-Data.co.uk CSVs
        │
        ▼
  BettingRisks.ipynb
  ┌─────────────────────────────────────┐
  │  1. Load & merge 10 seasons         │
  │  2. Clean & select 26 columns       │
  │  3. Outlier removal (IQR)           │
  │  4. Feature engineering             │
  │  5. SMOTE class balancing           │
  │  6. Train LR / KNN / DT / RF        │
  │  7. Export cleaned CSV (S4data.csv) │
  │  8. Export model_bundle.pkl         │
  └─────────────────────────────────────┘
        │
        │  S4data 2.csv  (semicolon-delimited)
        ▼
  FootballPrediction.sql
  ┌─────────────────────────────────────┐
  │  BULK INSERT → raw_matches          │
  │  Triggers fire (validate, compute)  │
  │  INSERT...SELECT → normalized tables│
  │  Views / SPs / Indexes ready        │
  │  DCL roles restrict access          │
  └─────────────────────────────────────┘
```

The five ML-computed columns (`HomeWinRate`, `AwayWinRate`, `AvgHomeGoals`, `AvgAwayGoals`, `ConfidenceScore`) flow from the notebook's feature engineering step into the CSV and ultimately into `MatchFeatures` via the ETL inserts. The SQL-layer `sp_PredictMatchOutcome` provides an independent rules-based baseline computed entirely from odds, allowing direct comparison with the model's `ConfidenceScore`.

---

## Setup & usage

### SQL Server setup

1. Open **SQL Server Management Studio** (SSMS) or Azure Data Studio.
2. Place `S4data 2.csv` at the path referenced in the `BULK INSERT` statement (default: `S4data 2.csv` in the SQL Server default data directory), or update the path in the script.
3. Run `FootballPrediction.sql` as a server admin — it will create `FootballPredictionDB` from scratch, set up all objects, load data, and configure roles.

```sql
-- Verify the load
SELECT COUNT(*) FROM raw_matches;           -- should return 14455
SELECT COUNT(*) FROM Matches;               -- should match after ETL inserts
SELECT * FROM vw_LeagueStats;
EXEC sp_GetTeamWins @TeamName = 'Arsenal';
```

### Python / Jupyter setup

```bash
pip install pandas numpy scikit-learn imbalanced-learn matplotlib seaborn scipy
```

Open `BettingRisks.ipynb` in Jupyter or Google Colab. The notebook is self-contained — update the CSV file paths in the data collection cells to point to your local copies of the Football-Data.co.uk season files, then run all cells top to bottom.

The final cells export `model_bundle.pkl` (the serialised best model) and the cleaned CSV used by the SQL script.

---

## Requirements

**Python**

| Package | Version |
|---|---|
| `pandas` | ≥ 1.5 |
| `numpy` | ≥ 1.23 |
| `scikit-learn` | ≥ 1.2 |
| `imbalanced-learn` | ≥ 0.10 |
| `matplotlib` | ≥ 3.6 |
| `seaborn` | ≥ 0.12 |
| `scipy` | ≥ 1.10 |

**SQL Server**

- SQL Server 2019 or later (T-SQL with `BULK INSERT`, `INSTEAD OF` triggers, and `TRY/CATCH` required)
- SQL Server Management Studio or Azure Data Studio for script execution
- Server-level permissions to create databases and logins (`sysadmin` or equivalent)
