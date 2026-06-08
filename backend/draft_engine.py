from __future__ import annotations

import random
from uuid import uuid4

from data_loader import available_years, list_teams, load_players, load_team_overalls, strip_roster_suffix
from models import DraftPick, DraftPlayer, DraftSession, Formation, Player
from storage import Store


ROLE_TO_DEPARTMENT = {
    "POR": "POR",
    "DC": "DIF",
    "ADA": "DIF",
    "ASA": "DIF",
    "TD": "DIF",
    "TS": "DIF",
    "CDC": "CC",
    "CC": "CC",
    "COC": "CC",
    "ATT": "ATT",
    "ED": "CC",
    "ES": "CC",
    "AT": "ATT",
    "AD": "ATT",
    "AS": "ATT",
}

FORMATIONS = {
    "4-3-3": Formation(id="4-3-3", label="4-3-3", slots={"POR": 1, "DIF": 4, "CC": 3, "ATT": 3}),
    "4-4-2": Formation(id="4-4-2", label="4-4-2", slots={"POR": 1, "DIF": 4, "CC": 4, "ATT": 2}),
    "3-5-2": Formation(id="3-5-2", label="3-5-2", slots={"POR": 1, "DIF": 3, "CC": 5, "ATT": 2}),
    "3-4-3": Formation(id="3-4-3", label="3-4-3", slots={"POR": 1, "DIF": 3, "CC": 4, "ATT": 3}),
    "5-3-2": Formation(id="5-3-2", label="5-3-2", slots={"POR": 1, "DIF": 5, "CC": 3, "ATT": 2}),
}


class DraftEngine:
    def __init__(self) -> None:
        self.store = Store("draft_sessions.json")
        self.sessions: dict[str, DraftSession] = self.store.load_all(DraftSession)

    def _save_session(self, session: DraftSession) -> None:
        self.store.save_one(session.id, session)

    def start(self, formation_id: str, year: int = 0, team_filter: str | None = None, difficulty: str = "normale") -> DraftSession:
        formation = FORMATIONS.get(formation_id)
        if formation is None:
            raise ValueError("Modulo non valido.")

        session = DraftSession(
            id=str(uuid4()),
            formation=formation,
            selected_players=[],
            year=year,
            team_filter=team_filter,
            difficulty=difficulty,
        )
        self.sessions[session.id] = session
        self._save_session(session)
        return session

    def get(self, session_id: str) -> DraftSession:
        session = self.sessions.get(session_id)
        if session is None:
            self.sessions = self.store.load_all(DraftSession)
            session = self.sessions.get(session_id)
        if session is None:
            raise ValueError("Sessione draft non trovata.")
        return session

    def roll_team(self, session_id: str) -> tuple[DraftSession, list[DraftPlayer]]:
        session = self.get(session_id)
        if session.completed:
            return session, []

        if session.team_filter:
            if session.year == 0:
                year = self._pick_year_for_team(session.team_filter)
            else:
                year = session.year
            team = self._find_team(session.team_filter, year)
            if team is None:
                raise ValueError(f"Squadra {session.team_filter} non trovata per l'annata selezionata.")
            session.current_team = team
            self._save_session(session)
        else:
            if session.year == 0:
                year = random.choice(available_years())
            else:
                year = session.year

            base_team = self._pick_team_by_difficulty(session.difficulty, year)
            team = self._find_team(base_team, year)
            session.current_team = team
            self._save_session(session)
        return session, self.players_for_current_team(session)

    def _pick_team_by_difficulty(self, difficulty: str, year: int) -> str:
        team_overalls = load_team_overalls(year)
        sorted_teams = sorted(team_overalls, key=lambda t: t["best_11_avg_overall"])
        n = len(sorted_teams)

        if difficulty == "facile":
            cutoff = n // 3
            pool = sorted_teams[-cutoff:] if cutoff > 0 else sorted_teams
        elif difficulty == "difficile":
            cutoff = n // 3
            pool = sorted_teams[:cutoff] if cutoff > 0 else sorted_teams
        else:
            pool = sorted_teams

        chosen = random.choice(pool)
        return strip_roster_suffix(chosen["team"])

    def _pick_year_for_team(self, base_team: str) -> int:
        years = [y for y in available_years() if self._team_exists(base_team, y)]
        if not years:
            raise ValueError(f"Squadra {base_team} non trovata in nessuna annata.")
        return random.choice(years)

    def _team_exists(self, base_team: str, year: int) -> bool:
        for player in load_players(year):
            if strip_roster_suffix(player.mapped_team) == base_team:
                return True
        return False

    def _find_team(self, base_team: str, year: int) -> str | None:
        for player in load_players(year):
            if strip_roster_suffix(player.mapped_team) == base_team:
                return player.mapped_team
        return None

    @staticmethod
    def _team_year(team_name: str) -> int:
        parts = team_name.rsplit(" ", 1)
        if len(parts) == 2 and len(parts[1]) == 2 and parts[1].isdigit():
            return 2000 + int(parts[1])
        return 0

    def pick_player(self, session_id: str, player_id: int, department: str) -> DraftSession:
        session = self.get(session_id)
        if session.current_team is None:
            raise ValueError("Prima devi tirare il dado.")
        if session.completed:
            raise ValueError("Draft gia' completato.")

        year = self._team_year(session.current_team) if session.year == 0 else session.year
        player = self._find_player(player_id, year)
        if strip_roster_suffix(player.mapped_team) != strip_roster_suffix(session.current_team):
            raise ValueError("Puoi scegliere solo un giocatore della squadra sorteggiata.")
        selected_ids, selected_names = self._selected_player_ids(session)
        if player.player_id in selected_ids or (session.year == 0 and player.name.lower().strip() in selected_names):
            raise ValueError("Giocatore gia' scelto.")
        if department not in self.remaining_slots(session):
            raise ValueError("Non hai slot liberi per questo reparto.")
        if department not in departments_for_player(player):
            raise ValueError("Il giocatore non e' compatibile con quel reparto.")

        pick = DraftPick(
            round=len(session.selected_players) + 1,
            team=session.current_team,
            player=player,
            assigned_department=department,
        )
        session.selected_players.append(pick)
        session.current_team = None
        session.completed = len(session.selected_players) == sum(session.formation.slots.values())
        self._save_session(session)
        return session

    def players_for_current_team(self, session: DraftSession) -> list[DraftPlayer]:
        if session.current_team is None:
            return []

        year = self._team_year(session.current_team) if session.year == 0 else session.year
        remaining = set(self.remaining_slots(session))
        selected_ids, selected_names = self._selected_player_ids(session)
        players = []
        for player in load_players(year):
            if strip_roster_suffix(player.mapped_team) != strip_roster_suffix(session.current_team):
                continue

            departments = departments_for_player(player)
            already_picked = (
                player.player_id in selected_ids
                or (session.year == 0 and player.name.lower().strip() in selected_names)
            )
            pickable = not already_picked and bool(remaining.intersection(departments))
            players.append(
                DraftPlayer(
                    **player.model_dump(),
                    departments=departments,
                    pickable=pickable,
                )
            )

        return sorted(players, key=lambda item: (not item.pickable, -item.overall, item.name))

    def remaining_slots(self, session: DraftSession) -> dict[str, int]:
        remaining = dict(session.formation.slots)
        for pick in session.selected_players:
            remaining[pick.assigned_department] -= 1
        return {department: count for department, count in remaining.items() if count > 0}

    def _find_player(self, player_id: int, year: int = 0) -> Player:
        for player in load_players(year):
            if player.player_id == player_id:
                return player
        raise ValueError("Giocatore non trovato.")

    def _selected_player_ids(self, session: DraftSession) -> set[int]:
        ids: set[int] = set()
        names: set[str] = set()
        for pick in session.selected_players:
            ids.add(pick.player.player_id)
            names.add(pick.player.name.lower().strip())
        return ids, names


def departments_for_player(player: Player) -> list[str]:
    departments = {
        ROLE_TO_DEPARTMENT[role]
        for role in player.roles
        if role in ROLE_TO_DEPARTMENT
    }
    return sorted(departments)

