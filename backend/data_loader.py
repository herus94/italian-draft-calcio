from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from models import Player


BACKEND_DIR = Path(__file__).resolve().parent
ROSTER_DIR = BACKEND_DIR / "roster_giocatori"
OVERALL_DIR = BACKEND_DIR / "overall_squadre"


def available_years() -> list[int]:
    years: list[int] = []
    for path in ROSTER_DIR.glob("players_sofifa_*.json"):
        name = path.stem.replace("players_sofifa_", "")
        if name.isdigit():
            years.append(int(name))
    return sorted(years)


def latest_year() -> int:
    years = available_years()
    return years[-1] if years else 2026


@lru_cache
def load_players(year: int = 0) -> list[Player]:
    if year == 0:
        result: list[Player] = []
        for y in available_years():
            path = ROSTER_DIR / f"players_sofifa_{y}.json"
            if not path.exists():
                continue
            label = str(y)[-2:]
            with open(path, encoding="utf-8") as f:
                for player in json.load(f):
                    player["mapped_team"] = _team_with_roster(player["mapped_team"], label)
                    result.append(Player.model_validate(player))
        return result

    path = ROSTER_DIR / f"players_sofifa_{year}.json"
    if not path.exists() and year == latest_year():
        path = ROSTER_DIR / "players_sofifa_all.json"
    label = str(year)[-2:]
    with open(path, encoding="utf-8") as f:
        return [
            Player.model_validate({**player, "mapped_team": _team_with_roster(player["mapped_team"], label)})
            for player in json.load(f)
        ]


@lru_cache
def load_team_overalls(year: int = 0) -> list[dict]:
    if year == 0:
        result: list[dict] = []
        for y in available_years():
            path = OVERALL_DIR / f"team_overalls_{y}.json"
            if not path.exists():
                continue
            label = str(y)[-2:]
            with open(path, encoding="utf-8") as f:
                for team_overall in json.load(f):
                    team_overall["team"] = _team_with_roster(team_overall["team"], label)
                    result.append(team_overall)
        return result

    path = OVERALL_DIR / f"team_overalls_{year}.json"
    label = str(year)[-2:]
    with open(path, encoding="utf-8") as f:
        return [
            {**team_overall, "team": _team_with_roster(team_overall["team"], label)}
            for team_overall in json.load(f)
        ]


def strip_roster_suffix(team_name: str) -> str:
    parts = team_name.rsplit(" ", 1)
    if len(parts) == 2 and len(parts[1]) == 2 and parts[1].isdigit():
        return parts[0]
    return team_name


def list_teams(year: int = 0) -> list[str]:
    teams = set()
    for player in load_players(year):
        teams.add(strip_roster_suffix(player.mapped_team))
    return sorted(teams)


def _team_with_roster(team_name: str, label: str) -> str:
    suffix = f" {label}"
    if team_name.endswith(suffix):
        return team_name
    return f"{team_name}{suffix}"
