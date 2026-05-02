PRINT '================================================================';
PRINT 'DATABASE DEPLOYMENT SCRIPT';
PRINT '================================================================';
GO

USE master;
GO

IF DB_ID('FootballPredictionDB') IS NOT NULL
BEGIN
    ALTER DATABASE FootballPredictionDB SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE FootballPredictionDB;
END
GO

CREATE DATABASE FootballPredictionDB;
GO

USE FootballPredictionDB;
GO

PRINT '================================================================';
PRINT 'DDL — CREATING TABLES';
PRINT '================================================================';
GO

IF OBJECT_ID('MatchFeatures', 'U') IS NOT NULL DROP TABLE MatchFeatures;
IF OBJECT_ID('Matches', 'U') IS NOT NULL DROP TABLE Matches;
IF OBJECT_ID('Teams', 'U') IS NOT NULL DROP TABLE Teams;
IF OBJECT_ID('Leagues', 'U') IS NOT NULL DROP TABLE Leagues;
IF OBJECT_ID('Seasons', 'U') IS NOT NULL DROP TABLE Seasons;
IF OBJECT_ID('raw_matches', 'U') IS NOT NULL DROP TABLE raw_matches;
GO


CREATE TABLE Teams (
    TeamID INT PRIMARY KEY,
    TeamName VARCHAR(100) UNIQUE
);

CREATE TABLE Leagues (
    LeagueID INT PRIMARY KEY,
    LeagueName VARCHAR(100)
);

CREATE TABLE Seasons (
    SeasonID INT PRIMARY KEY,
    SeasonName VARCHAR(20)
);

CREATE TABLE Matches (
    MatchID INT PRIMARY KEY,
    MatchDate DATE,
    HomeTeamID INT,
    AwayTeamID INT,
    HomeGoals INT,
    AwayGoals INT,
    Result CHAR(1),
    HalfTimeResult CHAR(1),
    HomeShots INT,
    AwayShots INT,
    HomeShotsTarget INT,
    AwayShotsTarget INT,
    HomeCorners INT,
    AwayCorners INT,
    HomeFouls INT,
    AwayFouls INT,
    HomeYellow INT,
    AwayYellow INT,
    HomeOdds FLOAT,
    DrawOdds FLOAT,
    AwayOdds FLOAT,
    LeagueID INT,
    SeasonID INT,
    FOREIGN KEY (HomeTeamID) REFERENCES Teams(TeamID),
    FOREIGN KEY (AwayTeamID) REFERENCES Teams(TeamID),
    FOREIGN KEY (LeagueID) REFERENCES Leagues(LeagueID),
    FOREIGN KEY (SeasonID) REFERENCES Seasons(SeasonID)
);

CREATE TABLE MatchFeatures (
    FeatureID INT PRIMARY KEY,
    MatchID INT,
    HomeWinRate FLOAT,
    AwayWinRate FLOAT,
    AvgHomeGoals FLOAT,
    AvgAwayGoals FLOAT,
    RiskScore FLOAT,
    ExpectedValue FLOAT,
    ConfidenceScore FLOAT,
    FOREIGN KEY (MatchID) REFERENCES Matches(MatchID)
);

-- ================================================================
-- RAW STAGING TABLE 
-- ================================================================
CREATE TABLE raw_matches (
    match_date VARCHAR(20),   -- FIX: was DATE (this caused your errors)
    home_team VARCHAR(100),
    away_team VARCHAR(100),
    home_goals FLOAT,
    away_goals FLOAT,
    result CHAR(1),
    halftime_result CHAR(1),
    home_shots FLOAT,
    away_shots FLOAT,
    home_shots_target FLOAT,
    away_shots_target FLOAT,
    home_corners FLOAT,
    away_corners FLOAT,
    home_fouls FLOAT,
    away_fouls FLOAT,
    home_yellow FLOAT,
    away_yellow FLOAT,
    home_odds FLOAT,
    draw_odds FLOAT,
    away_odds FLOAT,
    league VARCHAR(50),
    season VARCHAR(20)
);
GO

-- ================================================================
-- BULK INSERT--- DML 
-- ================================================================
BULK INSERT raw_matches
FROM 'C:\Users\maria\OneDrive\Рабочий стол\S4data 2.csv'
WITH (
    FIELDTERMINATOR = ';',
    ROWTERMINATOR = '0x0a',
    FIRSTROW = 2,
    TABLOCK
);

PRINT '-------------------------------'
PRINT 'DATA LOADED SUCCESSFULLY  (DML)';
PRINT '-------------------------------'
GO


/* -Checking Data-
SELECT * 
FROM raw_matches;
*/

-- ================================================================
-- DQL — RELATIONAL QUERIES STORED IN VIEWS
-- ================================================================


PRINT '================================================================';
PRINT 'DQL — RELATIONAL QUERIES';
PRINT '================================================================';
GO



USE FootballPredictionDB;
GO

-- View all data from raw table
SELECT *
FROM raw_matches;
GO

-- Select important match columns only
SELECT 
    match_date,
    home_team,
    away_team,
    home_goals,
    away_goals,
    result
FROM raw_matches;
GO

-- Count matches per league
SELECT 
    league,
    COUNT(*) AS total_matches
FROM raw_matches
GROUP BY league;
GO

-- Average total goals per match
SELECT 
    AVG(home_goals + away_goals) AS avg_total_goals
FROM raw_matches;
GO

-- Team performance (average goals scored and conceded)
SELECT 
    home_team,
    AVG(home_goals) AS avg_home_goals,
    AVG(away_goals) AS avg_away_goals
FROM raw_matches
GROUP BY home_team;
GO

-- Most winning home teams
SELECT 
    home_team,
    COUNT(*) AS wins
FROM raw_matches
WHERE result = 'H'
GROUP BY home_team
ORDER BY wins DESC;
GO

-- ================================================================
-- 2. VIEWS (SAVED DQL QUERIES)
-- ================================================================

-- View: Match Summary (basic match information)
IF OBJECT_ID('vw_MatchSummary', 'V') IS NOT NULL
    DROP VIEW vw_MatchSummary;
GO

CREATE VIEW vw_MatchSummary AS
SELECT 
    match_date,
    home_team,
    away_team,
    home_goals,
    away_goals,
    result,
    league,
    season
FROM raw_matches;
GO

-- View: High Scoring Matches (4+ total goals)
IF OBJECT_ID('vw_HighScoringMatches', 'V') IS NOT NULL
    DROP VIEW vw_HighScoringMatches;
GO

CREATE VIEW vw_HighScoringMatches AS
SELECT *
FROM raw_matches
WHERE (home_goals + away_goals) >= 4;
GO

-- View: League Statistics
IF OBJECT_ID('vw_LeagueStats', 'V') IS NOT NULL
    DROP VIEW vw_LeagueStats;
GO

CREATE VIEW vw_LeagueStats AS
SELECT 
    league,
    COUNT(*) AS total_matches,
    AVG(home_goals + away_goals) AS avg_goals
FROM raw_matches
GROUP BY league;
GO

-- View: Team Performance (home games analysis)
IF OBJECT_ID('vw_TeamPerformance', 'V') IS NOT NULL
    DROP VIEW vw_TeamPerformance;
GO

CREATE VIEW vw_TeamPerformance AS
SELECT 
    home_team AS team,
    COUNT(*) AS home_matches,
    SUM(CASE WHEN result = 'H' THEN 1 ELSE 0 END) AS home_wins,
    AVG(home_goals) AS avg_goals_scored
FROM raw_matches
GROUP BY home_team;
GO

-- Completion message
PRINT 'DQL QUERIES EXECUTED AND VIEWS CREATED SUCCESSFULLY';
GO



PRINT '================================================================';
PRINT 'INDEXES';
PRINT '================================================================';
GO 

-- ================================================================
-- INDEXING FOR QUERY OPTIMIZATION
-- Improves SELECT performance on large datasets
-- ================================================================

USE FootballPredictionDB;
GO 

-- Speeds up queries filtering or sorting by match date
CREATE INDEX idx_raw_matches_match_date
ON raw_matches(match_date);
GO 

-- Improves GROUP BY and WHERE queries on league
CREATE INDEX idx_raw_matches_league
ON raw_matches(league);
GO 

-- Helps queries filtering by season
CREATE INDEX idx_raw_matches_season
ON raw_matches(season);
GO

-- Optimizes queries that filter by BOTH league and season
CREATE INDEX idx_raw_matches_league_season
ON raw_matches(league, season);
GO 

-- Speeds up team performance queries (home team grouping)
CREATE INDEX idx_raw_matches_home_team
ON raw_matches(home_team);
GO 

-- Helps analysis of away team performance
CREATE INDEX idx_raw_matches_away_team
ON raw_matches(away_team);
GO

-- ================================================================
-- TRIGGERS 
-- ================================================================
PRINT '================================================================';
PRINT 'TRIGGERS';
PRINT '================================================================';
GO

USE FootballPredictionDB;
GO

-- 1. Trigger: Prevent Negative Goals
IF OBJECT_ID('tr_PreventNegativeGoals', 'TR') IS NOT NULL
    DROP TRIGGER tr_PreventNegativeGoals;
GO

CREATE TRIGGER tr_PreventNegativeGoals
ON raw_matches
INSTEAD OF INSERT
AS
BEGIN
    IF EXISTS (
        SELECT *
        FROM inserted
        WHERE home_goals < 0
           OR away_goals < 0
    )
    BEGIN
        PRINT 'Error: Goals cannot be negative.';
        ROLLBACK TRANSACTION;
        RETURN;
    END

    INSERT INTO raw_matches
    (
        match_date,
        home_team,
        away_team,
        home_goals,
        away_goals,
        result,
        halftime_result,
        home_shots,
        away_shots,
        home_shots_target,
        away_shots_target,
        home_corners,
        away_corners,
        home_fouls,
        away_fouls,
        home_yellow,
        away_yellow,
        home_odds,
        draw_odds,
        away_odds,
        league,
        season
    )
    SELECT *
    FROM inserted;
END;
GO

-- 2. Trigger: Prevent Same Team Playing Against Itself
IF OBJECT_ID('tr_PreventSameTeamMatch', 'TR') IS NOT NULL
    DROP TRIGGER tr_PreventSameTeamMatch;
GO

CREATE TRIGGER tr_PreventSameTeamMatch
ON raw_matches
AFTER INSERT, UPDATE
AS
BEGIN
    IF EXISTS (
        SELECT *
        FROM inserted
        WHERE home_team = away_team
    )
    BEGIN
        RAISERROR('Home team and away team cannot be the same.', 16, 1);
        ROLLBACK TRANSACTION;
    END
END;
GO

-- 3. Trigger: Auto Calculate Result Based On Goals
IF OBJECT_ID('tr_UpdateResultAutomatically', 'TR') IS NOT NULL
    DROP TRIGGER tr_UpdateResultAutomatically;
GO

CREATE TRIGGER tr_UpdateResultAutomatically
ON raw_matches
AFTER INSERT
AS
BEGIN
    UPDATE rm
    SET result =
        CASE
            WHEN rm.home_goals > rm.away_goals THEN 'H'
            WHEN rm.home_goals < rm.away_goals THEN 'A'
            ELSE 'D'
        END
    FROM raw_matches rm
    INNER JOIN inserted i
        ON rm.match_date = i.match_date
       AND rm.home_team = i.home_team
       AND rm.away_team = i.away_team;
END;
GO

-- 4. Trigger: Prevent Null Team Names
IF OBJECT_ID('tr_PreventNullTeams', 'TR') IS NOT NULL
    DROP TRIGGER tr_PreventNullTeams;
GO

CREATE TRIGGER tr_PreventNullTeams
ON raw_matches
AFTER INSERT, UPDATE
AS
BEGIN
    IF EXISTS (
        SELECT *
        FROM inserted
        WHERE home_team IS NULL
           OR away_team IS NULL
    )
    BEGIN
        RAISERROR('Team names cannot be NULL.', 16, 1);
        ROLLBACK TRANSACTION;
    END
END;
GO

-- 5. Trigger: Log Deleted Matches
IF OBJECT_ID('tr_LogDeletedMatches', 'TR') IS NOT NULL
    DROP TRIGGER tr_LogDeletedMatches;
GO

-- Create log table if not exists
IF OBJECT_ID('DeletedMatchesLog', 'U') IS NULL
BEGIN
    CREATE TABLE DeletedMatchesLog
    (
        log_id INT IDENTITY(1,1) PRIMARY KEY,
        deleted_date DATETIME DEFAULT GETDATE(),
        home_team VARCHAR(100),
        away_team VARCHAR(100),
        match_date DATE
    );
END;
GO

CREATE TRIGGER tr_LogDeletedMatches
ON raw_matches
AFTER DELETE
AS
BEGIN
    INSERT INTO DeletedMatchesLog
    (
        home_team,
        away_team,
        match_date
    )
    SELECT
        home_team,
        away_team,
        match_date
    FROM deleted;
END;
GO

-- 6. Trigger: Prevent Unrealistic Odds
IF OBJECT_ID('tr_ValidateOdds', 'TR') IS NOT NULL
    DROP TRIGGER tr_ValidateOdds;
GO

CREATE TRIGGER tr_ValidateOdds
ON raw_matches
AFTER INSERT, UPDATE
AS
BEGIN
    IF EXISTS (
        SELECT *
        FROM inserted
        WHERE home_odds <= 1
           OR draw_odds <= 1
           OR away_odds <= 1
    )
    BEGIN
        RAISERROR('Odds must be greater than 1.', 16, 1);
        ROLLBACK TRANSACTION;
    END
END;
GO

-- 7. Trigger: Prevent Future Match Dates
IF OBJECT_ID('tr_PreventFutureDates', 'TR') IS NOT NULL
    DROP TRIGGER tr_PreventFutureDates;
GO

CREATE TRIGGER tr_PreventFutureDates
ON raw_matches
AFTER INSERT, UPDATE
AS
BEGIN
    IF EXISTS (
        SELECT *
        FROM inserted
        WHERE match_date > GETDATE()
    )
    BEGIN
        RAISERROR('Match date cannot be in the future.', 16, 1);
        ROLLBACK TRANSACTION;
    END
END;
GO

-- 8. Trigger: Auto Uppercase League Names
IF OBJECT_ID('tr_UppercaseLeague', 'TR') IS NOT NULL
    DROP TRIGGER tr_UppercaseLeague;
GO

CREATE TRIGGER tr_UppercaseLeague
ON raw_matches
AFTER INSERT, UPDATE
AS
BEGIN
    UPDATE rm
    SET league = UPPER(rm.league)
    FROM raw_matches rm
    INNER JOIN inserted i
        ON rm.match_date = i.match_date
       AND rm.home_team = i.home_team
       AND rm.away_team = i.away_team;
END;
GO

-- 9. Trigger: Prevent Duplicate Match Entry
IF OBJECT_ID('tr_PreventDuplicateMatch', 'TR') IS NOT NULL
    DROP TRIGGER tr_PreventDuplicateMatch;
GO

CREATE TRIGGER tr_PreventDuplicateMatch
ON raw_matches
AFTER INSERT
AS
BEGIN
    IF EXISTS (
        SELECT home_team, away_team, match_date
        FROM raw_matches
        GROUP BY home_team, away_team, match_date
        HAVING COUNT(*) > 1
    )
    BEGIN
        RAISERROR('Duplicate match detected.', 16, 1);
        ROLLBACK TRANSACTION;
    END
END;
GO

-- 10. Trigger: Prevent Negative Statistics
IF OBJECT_ID('tr_PreventNegativeStats', 'TR') IS NOT NULL
    DROP TRIGGER tr_PreventNegativeStats;
GO

CREATE TRIGGER tr_PreventNegativeStats
ON raw_matches
AFTER INSERT, UPDATE
AS
BEGIN
    IF EXISTS (
        SELECT *
        FROM inserted
        WHERE home_shots < 0
           OR away_shots < 0
           OR home_corners < 0
           OR away_corners < 0
           OR home_fouls < 0
           OR away_fouls < 0
    )
    BEGIN
        RAISERROR('Statistics cannot be negative.', 16, 1);
        ROLLBACK TRANSACTION;
    END
END;
GO

-- Completion message
PRINT '10 TRIGGERS CREATED SUCCESSFULLY';
GO

-- ================================================================
-- STORED PROCEDURES 
-- ================================================================
PRINT '================================================================';
PRINT 'STORED PROCEDURES';
PRINT '================================================================';
GO

USE FootballPredictionDB;
GO

-- 1. Get Matches By League
IF OBJECT_ID('sp_GetMatchesByLeague', 'P') IS NOT NULL
    DROP PROCEDURE sp_GetMatchesByLeague;
GO

CREATE PROCEDURE sp_GetMatchesByLeague
    @LeagueName VARCHAR(50)
AS
BEGIN
    SELECT *
    FROM raw_matches
    WHERE league = @LeagueName
    ORDER BY match_date DESC;
END;
GO

-- 2. Get Matches By Team
IF OBJECT_ID('sp_GetMatchesByTeam', 'P') IS NOT NULL
    DROP PROCEDURE sp_GetMatchesByTeam;
GO

CREATE PROCEDURE sp_GetMatchesByTeam
    @TeamName VARCHAR(100)
AS
BEGIN
    SELECT *
    FROM raw_matches
    WHERE home_team = @TeamName
       OR away_team = @TeamName
    ORDER BY match_date DESC;
END;
GO

-- 3. Get High Scoring Matches
IF OBJECT_ID('sp_GetHighScoringMatches', 'P') IS NOT NULL
    DROP PROCEDURE sp_GetHighScoringMatches;
GO

CREATE PROCEDURE sp_GetHighScoringMatches
    @MinGoals INT
AS
BEGIN
    SELECT *
    FROM raw_matches
    WHERE (home_goals + away_goals) >= @MinGoals
    ORDER BY (home_goals + away_goals) DESC;
END;
GO

-- 4. Get League Statistics
IF OBJECT_ID('sp_GetLeagueStatistics', 'P') IS NOT NULL
    DROP PROCEDURE sp_GetLeagueStatistics;
GO

CREATE PROCEDURE sp_GetLeagueStatistics
AS
BEGIN
    SELECT
        league,
        COUNT(*) AS total_matches,
        AVG(home_goals + away_goals) AS avg_goals
    FROM raw_matches
    GROUP BY league
    ORDER BY total_matches DESC;
END;
GO

-- 5. Get Team Win Count
IF OBJECT_ID('sp_GetTeamWins', 'P') IS NOT NULL
    DROP PROCEDURE sp_GetTeamWins;
GO

CREATE PROCEDURE sp_GetTeamWins
    @TeamName VARCHAR(100)
AS
BEGIN
    SELECT
        @TeamName AS Team,
        COUNT(*) AS TotalWins
    FROM raw_matches
    WHERE (home_team = @TeamName AND result = 'H')
       OR (away_team = @TeamName AND result = 'A');
END;
GO

-- 6. Get Head-to-Head Matches Between Two Teams
IF OBJECT_ID('sp_GetHeadToHead', 'P') IS NOT NULL
    DROP PROCEDURE sp_GetHeadToHead;
GO

CREATE PROCEDURE sp_GetHeadToHead
    @Team1 VARCHAR(100),
    @Team2 VARCHAR(100)
AS
BEGIN
    SELECT *
    FROM raw_matches
    WHERE (home_team = @Team1 AND away_team = @Team2)
       OR (home_team = @Team2 AND away_team = @Team1)
    ORDER BY match_date DESC;
END;
GO

-- 7. Get Average Odds By League
IF OBJECT_ID('sp_GetAverageOddsByLeague', 'P') IS NOT NULL
    DROP PROCEDURE sp_GetAverageOddsByLeague;
GO

CREATE PROCEDURE sp_GetAverageOddsByLeague
AS
BEGIN
    SELECT
        league,
        AVG(home_odds) AS avg_home_odds,
        AVG(draw_odds) AS avg_draw_odds,
        AVG(away_odds) AS avg_away_odds
    FROM raw_matches
    GROUP BY league;
END;
GO

-- 8. Get Matches By Date Range
IF OBJECT_ID('sp_GetMatchesByDateRange', 'P') IS NOT NULL
    DROP PROCEDURE sp_GetMatchesByDateRange;
GO

CREATE PROCEDURE sp_GetMatchesByDateRange
    @StartDate DATE,
    @EndDate DATE
AS
BEGIN
    SELECT *
    FROM raw_matches
    WHERE match_date BETWEEN @StartDate AND @EndDate
    ORDER BY match_date;
END;
GO

-- 9. Get Team Goal Statistics
IF OBJECT_ID('sp_GetTeamGoalStats', 'P') IS NOT NULL
    DROP PROCEDURE sp_GetTeamGoalStats;
GO

CREATE PROCEDURE sp_GetTeamGoalStats
    @TeamName VARCHAR(100)
AS
BEGIN
    SELECT
        @TeamName AS Team,
        AVG(CASE WHEN home_team = @TeamName THEN home_goals END) AS AvgGoalsAtHome,
        AVG(CASE WHEN away_team = @TeamName THEN away_goals END) AS AvgGoalsAway
    FROM raw_matches
    WHERE home_team = @TeamName
       OR away_team = @TeamName;
END;
GO

-- 10. Predict Match Outcome Based On Odds
IF OBJECT_ID('sp_PredictMatchOutcome', 'P') IS NOT NULL
    DROP PROCEDURE sp_PredictMatchOutcome;
GO

CREATE PROCEDURE sp_PredictMatchOutcome
    @HomeOdds FLOAT,
    @DrawOdds FLOAT,
    @AwayOdds FLOAT
AS
BEGIN
    DECLARE @Prediction VARCHAR(20);

    IF @HomeOdds < @DrawOdds AND @HomeOdds < @AwayOdds
        SET @Prediction = 'Home Win';
    ELSE IF @AwayOdds < @HomeOdds AND @AwayOdds < @DrawOdds
        SET @Prediction = 'Away Win';
    ELSE
        SET @Prediction = 'Draw';

    SELECT
        @HomeOdds AS HomeOdds,
        @DrawOdds AS DrawOdds,
        @AwayOdds AS AwayOdds,
        @Prediction AS PredictedOutcome;
END;
GO

-- Completion message
PRINT '10 STORED PROCEDURES CREATED SUCCESSFULLY';
GO

PRINT '================ DCL (Access Control) =================';
GO

USE FootballPredictionDB;
GO

-- ================================================================
-- CLEANUP — wrapped in TRY/CATCH so re-runs never error
-- ================================================================

-- Remove role members
BEGIN TRY ALTER ROLE AdminRole         DROP MEMBER AdminUser;     END TRY BEGIN CATCH END CATCH
BEGIN TRY ALTER ROLE AnalystRole       DROP MEMBER AnalystUser;   END TRY BEGIN CATCH END CATCH
BEGIN TRY ALTER ROLE InterfaceUserRole DROP MEMBER InterfaceUser; END TRY BEGIN CATCH END CATCH
BEGIN TRY ALTER ROLE MLSystemRole      DROP MEMBER MLUser;        END TRY BEGIN CATCH END CATCH
BEGIN TRY ALTER ROLE ResearcherRole    DROP MEMBER ResearchUser;  END TRY BEGIN CATCH END CATCH
GO

-- Drop users
BEGIN TRY DROP USER AdminUser;     END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP USER AnalystUser;   END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP USER InterfaceUser; END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP USER MLUser;        END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP USER ResearchUser;  END TRY BEGIN CATCH END CATCH
GO

-- Drop roles
BEGIN TRY DROP ROLE AdminRole;         END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP ROLE AnalystRole;       END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP ROLE InterfaceUserRole; END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP ROLE MLSystemRole;      END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP ROLE ResearcherRole;    END TRY BEGIN CATCH END CATCH
GO

-- Drop logins (server level)
USE master;
GO

BEGIN TRY DROP LOGIN AdminUser;     END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP LOGIN AnalystUser;   END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP LOGIN InterfaceUser; END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP LOGIN MLUser;        END TRY BEGIN CATCH END CATCH
BEGIN TRY DROP LOGIN ResearchUser;  END TRY BEGIN CATCH END CATCH
GO

-- ================================================================
-- CREATE LOGINS
-- ================================================================
CREATE LOGIN AdminUser     WITH PASSWORD = 'AdminPassword123!';
CREATE LOGIN AnalystUser   WITH PASSWORD = 'AnalystPassword123!';
CREATE LOGIN InterfaceUser WITH PASSWORD = 'InterfacePassword123!';
CREATE LOGIN MLUser        WITH PASSWORD = 'MLPassword123!';
CREATE LOGIN ResearchUser  WITH PASSWORD = 'ResearchPassword123!';
GO

-- ================================================================
-- CREATE USERS
-- ================================================================
USE FootballPredictionDB;
GO

CREATE USER AdminUser     FOR LOGIN AdminUser;
CREATE USER AnalystUser   FOR LOGIN AnalystUser;
CREATE USER InterfaceUser FOR LOGIN InterfaceUser;
CREATE USER MLUser        FOR LOGIN MLUser;
CREATE USER ResearchUser  FOR LOGIN ResearchUser;
GO

-- ================================================================
-- CREATE ROLES
-- ================================================================
CREATE ROLE AdminRole;
CREATE ROLE AnalystRole;
CREATE ROLE InterfaceUserRole;
CREATE ROLE MLSystemRole;
CREATE ROLE ResearcherRole;
GO

-- ================================================================
-- ADD ROLE MEMBERS
-- ================================================================
ALTER ROLE AdminRole         ADD MEMBER AdminUser;
ALTER ROLE AnalystRole       ADD MEMBER AnalystUser;
ALTER ROLE InterfaceUserRole ADD MEMBER InterfaceUser;
ALTER ROLE MLSystemRole      ADD MEMBER MLUser;
ALTER ROLE ResearcherRole    ADD MEMBER ResearchUser;
GO

-- ================================================================
-- PERMISSIONS
-- ================================================================
GRANT SELECT, INSERT, UPDATE, DELETE ON Teams         TO AdminRole;
GRANT SELECT, INSERT, UPDATE, DELETE ON Matches       TO AdminRole;
GRANT SELECT, INSERT, UPDATE, DELETE ON MatchFeatures TO AdminRole;
GRANT SELECT, INSERT, UPDATE, DELETE ON Leagues       TO AdminRole;
GRANT SELECT, INSERT, UPDATE, DELETE ON Seasons       TO AdminRole;

GRANT SELECT ON Teams         TO AnalystRole;
GRANT SELECT ON Matches       TO AnalystRole;
GRANT SELECT ON MatchFeatures TO AnalystRole;
GRANT SELECT ON Leagues       TO AnalystRole;
GRANT SELECT ON Seasons       TO AnalystRole;

GRANT SELECT, INSERT, UPDATE ON Matches       TO InterfaceUserRole;
GRANT SELECT                 ON Teams         TO InterfaceUserRole;
GRANT SELECT                 ON MatchFeatures TO InterfaceUserRole;
GRANT SELECT                 ON Leagues       TO InterfaceUserRole;
GRANT SELECT                 ON Seasons       TO InterfaceUserRole;

GRANT SELECT         ON Teams         TO MLSystemRole;
GRANT SELECT         ON Matches       TO MLSystemRole;
GRANT SELECT         ON Leagues       TO MLSystemRole;
GRANT SELECT         ON Seasons       TO MLSystemRole;
GRANT INSERT, UPDATE ON MatchFeatures TO MLSystemRole;

GRANT SELECT ON Matches       TO ResearcherRole;
GRANT SELECT ON MatchFeatures TO ResearcherRole;
GO

PRINT '================ DCL SUCCESS (NO ERRORS) =================';
GO

-- ================================================================
-- RELATIONAL ALGEBRA
-- SQL EQUIVALENT QUERIES
-- ================================================================

USE FootballPredictionDB;
GO

-- ================================================================
-- 1. PROJECTION (π)
-- Select specific columns only
-- ================================================================

-- Projection: Show only team names
SELECT TeamName
FROM Teams;
GO

-- Projection: Show match date and result only
SELECT MatchDate, Result
FROM Matches;
GO


-- ================================================================
-- 2. SELECTION (σ)
-- Filter rows using conditions
-- ================================================================

-- Selection: Home wins only
SELECT *
FROM Matches
WHERE Result = 'H';
GO

-- Selection: Matches with more than 3 total goals
SELECT *
FROM Matches
WHERE (HomeGoals + AwayGoals) > 3;
GO


-- ================================================================
-- 3. JOIN (⨝)
-- Combine related tables
-- ================================================================

-- Join Matches with Home Team details
SELECT 
    M.MatchID,
    M.MatchDate,
    T.TeamName AS HomeTeam
FROM Matches M
INNER JOIN Teams T
    ON M.HomeTeamID = T.TeamID;
GO

-- Join Matches with League details
SELECT
    M.MatchID,
    M.MatchDate,
    L.LeagueName
FROM Matches M
INNER JOIN Leagues L
    ON M.LeagueID = L.LeagueID;
GO

-- Full Join: Match + Home Team + League
SELECT
    M.MatchID,
    M.MatchDate,
    T.TeamName AS HomeTeam,
    L.LeagueName
FROM Matches M
INNER JOIN Teams T
    ON M.HomeTeamID = T.TeamID
INNER JOIN Leagues L
    ON M.LeagueID = L.LeagueID;
GO


-- ================================================================
-- 4. UNION (∪)
-- Combine unique rows
-- ================================================================

-- Teams appearing as Home or Away
SELECT HomeTeamID AS TeamID
FROM Matches

UNION

SELECT AwayTeamID
FROM Matches;
GO


-- ================================================================
-- 5. INTERSECTION (∩)
-- Common rows between two queries
-- ================================================================

-- Teams appearing both as Home and Away
SELECT HomeTeamID
FROM Matches

INTERSECT

SELECT AwayTeamID
FROM Matches;
GO


-- ================================================================
-- 6. DIFFERENCE (−)
-- Records in first query but not second
-- ================================================================

-- Teams that only played home games
SELECT HomeTeamID
FROM Matches

EXCEPT

SELECT AwayTeamID
FROM Matches;
GO


-- ================================================================
-- 7. AGGREGATION (γ)
-- Grouping and aggregate functions
-- ================================================================

-- Count matches per league
SELECT
    LeagueID,
    COUNT(*) AS TotalMatches
FROM Matches
GROUP BY LeagueID;
GO

-- Average total goals per league
SELECT
    LeagueID,
    AVG(HomeGoals + AwayGoals) AS AvgGoals
FROM Matches
GROUP BY LeagueID;
GO

-- Count matches by result
SELECT
    Result,
    COUNT(*) AS MatchCount
FROM Matches
GROUP BY Result;
GO


-- ================================================================
-- 8. COMPLEX QUERY
-- High-scoring matches with league name
-- ================================================================

SELECT
    M.MatchDate,
    L.LeagueName,
    M.HomeGoals,
    M.AwayGoals
FROM Matches M
INNER JOIN Leagues L
    ON M.LeagueID = L.LeagueID
WHERE (M.HomeGoals + M.AwayGoals) >= 4;
GO


-- ================================================================
-- 9. JOIN WITH MATCH FEATURES
-- Match analytics
-- ================================================================

SELECT
    M.MatchID,
    M.MatchDate,
    MF.HomeWinRate,
    MF.AwayWinRate,
    MF.ConfidenceScore
FROM Matches M
INNER JOIN MatchFeatures MF
    ON M.MatchID = MF.MatchID;
GO


-- ================================================================
-- 10. ADVANCED AGGREGATION
-- Average confidence score by league
-- ================================================================

SELECT
    M.LeagueID,
    AVG(MF.ConfidenceScore) AS AvgConfidenceScore
FROM Matches M
INNER JOIN MatchFeatures MF
    ON M.MatchID = MF.MatchID
GROUP BY M.LeagueID;
GO