from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class Player(BaseModel):
    player_id: int
    name: str
    overall: int
    roles: list[str]
    team: str
    mapped_team: str


class Formation(BaseModel):
    id: str
    label: str
    slots: dict[str, int]


class DraftPlayer(Player):
    departments: list[str]
    pickable: bool


class DraftPick(BaseModel):
    round: int
    team: str
    player: Player
    assigned_department: str


class DraftSession(BaseModel):
    id: str
    formation: Formation
    selected_players: list[DraftPick]
    current_team: str | None = None
    completed: bool = False
    year: int = 0
    team_filter: str | None = None
    difficulty: str = "normale"


class StartDraftRequest(BaseModel):
    formation_id: str
    year: int = 0
    team_filter: str | None = None
    difficulty: str = "normale"


class PickPlayerRequest(BaseModel):
    player_id: int
    department: str


class RollResponse(BaseModel):
    session: DraftSession
    players: list[DraftPlayer]


class StartSeasonRequest(BaseModel):
    draft_session_id: str
    replaced_team: str | None = None
    user_team_name: str = "Draft FC"
    year: int = 0


class GoalEvent(BaseModel):
    minute: int
    team: str
    scorer: str


class Match(BaseModel):
    id: str
    matchday: int
    home_team: str
    away_team: str
    home_goals: int | None = None
    away_goals: int | None = None
    goals: list[GoalEvent] = Field(default_factory=list)
    played: bool = False


class StandingRow(BaseModel):
    team: str
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0

    @computed_field
    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


class ScorerRow(BaseModel):
    player: str
    team: str
    goals: int


class Season(BaseModel):
    id: str
    draft_session_id: str
    user_team: str
    replaced_team: str
    current_matchday: int = 1
    matches: list[Match]
    standings: list[StandingRow]
    top_scorers: list[ScorerRow] = Field(default_factory=list)
    completed: bool = False
    year: int = 2026
