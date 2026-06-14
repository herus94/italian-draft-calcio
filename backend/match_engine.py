from __future__ import annotations

import math
import random
from uuid import uuid4

from data_loader import latest_year, load_team_overalls, strip_roster_suffix
from draft_engine import departments_for_player
from models import DraftSession, GoalEvent, Match, Player, ScorerRow, Season, StandingRow
from storage import Store


USER_TEAM_DEFAULT = "Draft FC"
MATCHDAYS_PER_SEASON = 38


class MatchEngine:
    def __init__(self) -> None:
        self.store = Store("seasons.json")
        self.seasons: dict[str, Season] = self.store.load_all(Season)

    def _save_season(self, season: Season) -> None:
        self.store.save_one(season.id, season)

    def start_season(
        self,
        draft_session: DraftSession,
        replaced_team: str | None = None,
        user_team_name: str = USER_TEAM_DEFAULT,
        year: int = 0,
    ) -> Season:
        if not draft_session.completed:
            raise ValueError("Completa il draft prima di iniziare il campionato.")

        if year == 0:
            latest_teams = load_team_overalls(latest_year())
            all_entries = load_team_overalls(0)
            by_base: dict[str, list[dict]] = {}
            for entry in all_entries:
                base = strip_roster_suffix(entry["team"])
                by_base.setdefault(base, []).append(entry)
            team_overalls = []
            for team in latest_teams:
                base = strip_roster_suffix(team["team"])
                pool = by_base.get(base, [team])
                team_overalls.append(random.choice(pool))
            season_year = 0
        else:
            team_overalls = load_team_overalls(year)
            season_year = year
        replaced_team = replaced_team or min(team_overalls, key=lambda team: team["best_11_avg_overall"])["team"]

        real_teams = [team["team"] for team in team_overalls if team["team"] != replaced_team]
        teams = [user_team_name, *real_teams]
        matches = build_double_round_robin(teams)
        standings = [StandingRow(team=team) for team in teams]

        season = Season(
            id=str(uuid4()),
            draft_session_id=draft_session.id,
            user_team=user_team_name,
            replaced_team=replaced_team,
            matches=matches,
            standings=standings,
            year=season_year,
        )
        self.seasons[season.id] = season
        self._save_season(season)
        return season

    def get(self, season_id: str) -> Season:
        self.seasons = self.store.load_all(Season)
        season = self.seasons.get(season_id)
        if season is None:
            raise ValueError("Campionato non trovato.")
        return season

    def simulate_next_matchday(self, season_id: str, draft_session: DraftSession) -> Season:
        season = self.get(season_id)
        if season.completed:
            return season

        matchday = season.current_matchday
        for match in season.matches:
            if match.matchday == matchday and not match.played:
                simulate_match(match, season, draft_session)

        recalculate_standings(season)
        season.top_scorers = calculate_top_scorers(season)
        season.current_matchday += 1
        if season.current_matchday > MATCHDAYS_PER_SEASON:
            season.completed = True
            season.current_matchday = MATCHDAYS_PER_SEASON
        self._save_season(season)
        return season

    def simulate_until_matchday(self, season_id: str, draft_session: DraftSession, target_matchday: int) -> Season:
        season = self.get(season_id)
        while not season.completed and season.current_matchday <= target_matchday:
            self.simulate_next_matchday(season_id, draft_session)
        return season


def build_double_round_robin(teams: list[str]) -> list[Match]:
    if len(teams) % 2 != 0:
        raise ValueError("Il campionato richiede un numero pari di squadre.")

    first_shuffled = list(teams)
    random.shuffle(first_shuffled)
    first_leg = build_single_round_robin(first_shuffled)

    first_leg_home: dict[frozenset[str], str] = {}
    for day_matches in first_leg:
        for home, away in day_matches:
            first_leg_home[frozenset([home, away])] = home

    second_shuffled = list(teams)
    random.shuffle(second_shuffled)
    second_leg = build_single_round_robin(second_shuffled)

    for day_matches in second_leg:
        for i, (home, away) in enumerate(day_matches):
            pair = frozenset([home, away])
            if first_leg_home[pair] == home:
                day_matches[i] = (away, home)

    matches = []
    for matchday, day_matches in enumerate(first_leg, start=1):
        for home, away in day_matches:
            matches.append(Match(id=str(uuid4()), matchday=matchday, home_team=home, away_team=away))

    offset = len(first_leg)
    for matchday, day_matches in enumerate(second_leg, start=1):
        for home, away in day_matches:
            matches.append(Match(id=str(uuid4()), matchday=matchday + offset, home_team=home, away_team=away))

    return matches


def build_single_round_robin(teams: list[str]) -> list[list[tuple[str, str]]]:
    rotating = teams[:]
    rounds = []
    for round_index in range(len(rotating) - 1):
        pairings = []
        half = len(rotating) // 2
        for index in range(half):
            home = rotating[index]
            away = rotating[-index - 1]
            if round_index % 2:
                home, away = away, home
            pairings.append((home, away))
        rounds.append(pairings)
        rotating = [rotating[0], rotating[-1], *rotating[1:-1]]
    return rounds


def team_form_bonus(team: str, season: Season, window: int = 5) -> float:
    recent = [
        m for m in season.matches
        if m.played and m.home_goals is not None and m.away_goals is not None
        and (m.home_team == team or m.away_team == team)
    ]
    if not recent:
        return 0.0
    recent.sort(key=lambda m: m.matchday, reverse=True)
    recent = recent[:window]
    points = 0
    for m in recent:
        if m.home_team == team:
            if m.home_goals > m.away_goals:
                points += 3
            elif m.home_goals == m.away_goals:
                points += 1
        else:
            if m.away_goals > m.home_goals:
                points += 3
            elif m.away_goals == m.home_goals:
                points += 1
    max_points = len(recent) * 3
    ratio = points / max_points if max_points > 0 else 0.5
    return (ratio - 0.5) * 3.0


def match_variance(team_rating: float, opponent_rating: float) -> float:
    delta = team_rating - opponent_rating
    if delta > 7:
        return 2.0
    if delta > 4:
        return 3.0
    if delta < -7:
        return 5.5
    if delta < -4:
        return 5.0
    return 4.0


def simulate_match(match: Match, season: Season, draft_session: DraftSession) -> None:
    home_rating = team_rating(match.home_team, season, draft_session)
    away_rating = team_rating(match.away_team, season, draft_session)

    home_form = team_form_bonus(match.home_team, season)
    away_form = team_form_bonus(match.away_team, season)

    home_var = match_variance(home_rating, away_rating)
    away_var = match_variance(away_rating, home_rating)

    home_match_rating = home_rating + home_form + random.uniform(-home_var, home_var)
    away_match_rating = away_rating + away_form + random.uniform(-away_var, away_var)

    home_expected = expected_goals(home_match_rating, away_match_rating, home_advantage=0.22)
    away_expected = expected_goals(away_match_rating, home_match_rating, home_advantage=0)

    match.home_goals = sample_goals(home_expected)
    match.away_goals = sample_goals(away_expected)
    match.goals = build_goal_events(match, season, draft_session)
    match.played = True


def expected_goals(attack_rating: float, defense_rating: float, home_advantage: float) -> float:
    rating_delta = attack_rating - defense_rating
    return max(0.15, min(3.4, 1.25 + home_advantage + rating_delta * 0.065))


def sample_goals(expected: float) -> int:
    threshold = math.exp(-expected)
    product = 1.0
    goals = 0
    while product > threshold:
        goals += 1
        product *= random.random()
    return max(0, goals - 1)


def build_goal_events(match: Match, season: Season, draft_session: DraftSession) -> list[GoalEvent]:
    goals = []
    assert match.home_goals is not None and match.away_goals is not None

    for _ in range(match.home_goals):
        scorer_name, is_gk = pick_scorer(match.home_team, season, draft_session)
        minute = random.randint(90, 95) if is_gk else random.randint(1, 90)
        goals.append(GoalEvent(minute=minute, team=match.home_team, scorer=scorer_name))
    for _ in range(match.away_goals):
        scorer_name, is_gk = pick_scorer(match.away_team, season, draft_session)
        minute = random.randint(90, 95) if is_gk else random.randint(1, 90)
        goals.append(GoalEvent(minute=minute, team=match.away_team, scorer=scorer_name))

    return sorted(goals, key=lambda goal: goal.minute)


def pick_scorer(team: str, season: Season, draft_session: DraftSession) -> tuple[str, bool]:
    players = players_for_team(team, season, draft_session)
    weighted_players: list[tuple[Player, float]] = []
    for player in players:
        departments = departments_for_player(player)
        if "ATT" in departments:
            weight = 8.0
        elif "CC" in departments:
            weight = 4.0
        elif "DIF" in departments:
            weight = 1.0
        else:
            weight = 0.001
        weighted_players.append((player, weight * max(1, player.overall - 50)))

    chosen = random.choices(
        [item[0] for item in weighted_players],
        weights=[item[1] for item in weighted_players],
        k=1,
    )[0]

    is_gk = "POR" in departments_for_player(chosen)
    return chosen.name, is_gk


def players_for_team(team: str, season: Season, draft_session: DraftSession) -> list[Player]:
    if team == season.user_team:
        return [pick.player for pick in draft_session.selected_players]

    for team_overall in load_team_overalls(season.year):
        if team_overall["team"] == team:
            return [
                Player(
                    player_id=player["player_id"],
                    name=player["name"],
                    overall=player["overall"],
                    roles=player["roles"],
                    team=team,
                    mapped_team=team,
                )
                for player in team_overall["best_players"]
            ]

    raise ValueError("Squadra non trovata.")


def team_rating(team: str, season: Season, draft_session: DraftSession) -> float:
    if team == season.user_team:
        return sum(pick.player.overall for pick in draft_session.selected_players) / len(draft_session.selected_players)

    for team_overall in load_team_overalls(season.year):
        if team_overall["team"] == team:
            return team_overall["best_11_avg_overall"]

    raise ValueError("Squadra non trovata.")


def calculate_top_scorers(season: Season) -> list[ScorerRow]:
    scorer_goals: dict[tuple[str, str], int] = {}
    for match in season.matches:
        if not match.played:
            continue
        for goal in match.goals:
            key = (goal.scorer, goal.team)
            scorer_goals[key] = scorer_goals.get(key, 0) + 1
    rows = [ScorerRow(player=name, team=team, goals=goals) for (name, team), goals in scorer_goals.items()]
    rows.sort(key=lambda r: r.goals, reverse=True)
    return rows


def recalculate_standings(season: Season) -> None:
    rows = {row.team: StandingRow(team=row.team) for row in season.standings}
    for match in season.matches:
        if not match.played or match.home_goals is None or match.away_goals is None:
            continue

        home = rows[match.home_team]
        away = rows[match.away_team]
        home.played += 1
        away.played += 1
        home.goals_for += match.home_goals
        home.goals_against += match.away_goals
        away.goals_for += match.away_goals
        away.goals_against += match.home_goals

        if match.home_goals > match.away_goals:
            home.wins += 1
            away.losses += 1
            home.points += 3
        elif match.home_goals < match.away_goals:
            away.wins += 1
            home.losses += 1
            away.points += 3
        else:
            home.draws += 1
            away.draws += 1
            home.points += 1
            away.points += 1

    season.standings = sorted(
        rows.values(),
        key=lambda row: (row.points, row.goal_difference, row.goals_for, row.team),
        reverse=True,
    )
