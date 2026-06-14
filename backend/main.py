from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from data_loader import available_years, list_teams, load_players, load_team_overalls
from draft_engine import FORMATIONS, DraftEngine
from match_engine import MATCHDAYS_PER_SEASON, MatchEngine
from models import PickPlayerRequest, RollResponse, StartDraftRequest, StartSeasonRequest


app = FastAPI(title="Draft Calcio API")
draft_engine = DraftEngine()
match_engine = MatchEngine()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    from storage import REDIS_URL, DATA_DIR
    has_redis = REDIS_URL is not None
    return {
        "status": "ok",
        "storage": "redis" if draft_engine.store._redis else "json",
        "redis_url_set": has_redis,
        "data_dir": str(DATA_DIR),
        "draft_sessions": len(draft_engine.sessions),
        "seasons": len(match_engine.seasons),
    }


@app.get("/api/years")
def years() -> list[int]:
    return available_years()


@app.get("/api/formations")
def formations() -> list:
    return list(FORMATIONS.values())


@app.get("/api/teams")
def teams(year: int = Query(default=0)) -> list[str]:
    return list_teams(year)


@app.get("/api/players")
def players(team: str | None = None, year: int = Query(default=0)) -> list:
    all_players = load_players(year)
    if team is None:
        return all_players
    return [player for player in all_players if player.mapped_team == team]


@app.get("/api/team-overalls")
def team_overalls(year: int = Query(default=0)) -> list[dict]:
    return load_team_overalls(year)


@app.post("/api/draft/start")
def start_draft(request: StartDraftRequest):
    try:
        return draft_engine.start(request.formation_id, request.year, request.team_filter, request.difficulty)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/draft/{session_id}")
def get_draft(session_id: str):
    try:
        return draft_engine.get(session_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/draft/{session_id}/roll", response_model=RollResponse)
def roll_draft_team(session_id: str):
    try:
        session, players_for_team = draft_engine.roll_team(session_id)
        return RollResponse(session=session, players=players_for_team)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/draft/{session_id}/pick")
def pick_draft_player(session_id: str, request: PickPlayerRequest):
    try:
        return draft_engine.pick_player(session_id, request.player_id, request.department)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/season/start")
def start_season(request: StartSeasonRequest):
    try:
        draft_session = draft_engine.get(request.draft_session_id)
        return match_engine.start_season(
            draft_session=draft_session,
            replaced_team=request.replaced_team,
            user_team_name=request.user_team_name,
            year=request.year,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/season/{season_id}")
def get_season(season_id: str):
    try:
        return match_engine.get(season_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/season/{season_id}/simulate-next")
def simulate_next_matchday(season_id: str):
    try:
        season = match_engine.get(season_id)
        draft_session = draft_engine.get(season.draft_session_id)
        return match_engine.simulate_next_matchday(season_id, draft_session)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/season/{season_id}/simulate-to-mid")
def simulate_to_midseason(season_id: str):
    try:
        season = match_engine.get(season_id)
        draft_session = draft_engine.get(season.draft_session_id)
        return match_engine.simulate_until_matchday(season_id, draft_session, target_matchday=19)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/season/{season_id}/simulate-to-end")
def simulate_to_end(season_id: str):
    try:
        season = match_engine.get(season_id)
        draft_session = draft_engine.get(season.draft_session_id)
        return match_engine.simulate_until_matchday(
            season_id,
            draft_session,
            target_matchday=MATCHDAYS_PER_SEASON,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error



