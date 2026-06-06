#!/usr/bin/env python3
"""Calculate team overall averages from the SoFIFA players JSON."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_PLAYERS_PATH = BACKEND_DIR / "roster_giocatori" / "players_sofifa_2026.json"
DEFAULT_TEAM_OVERALLS_PATH = BACKEND_DIR / "overall_squadre" / "team_overalls_2026.json"


def load_players(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as players_file:
        return json.load(players_file)


def calculate_team_overalls(players: list[dict[str, Any]], best_count: int) -> list[dict[str, Any]]:
    teams: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for player in players:
        team_name = player.get("mapped_team") or player.get("team")
        overall = player.get("overall")
        if team_name and isinstance(overall, int):
            teams[team_name].append(player)

    summaries = []
    for team_name, team_players in teams.items():
        sorted_players = sorted(team_players, key=lambda player: player["overall"], reverse=True)
        best_players = sorted_players[:best_count]
        summaries.append(
            {
                "team": team_name,
                "players_count": len(team_players),
                "avg_overall": round(mean(player["overall"] for player in team_players), 2),
                "best_11_avg_overall": round(mean(player["overall"] for player in best_players), 2),
                "best_players": [
                    {
                        "player_id": player["player_id"],
                        "name": player["name"],
                        "overall": player["overall"],
                        "roles": player["roles"],
                    }
                    for player in best_players
                ],
            }
        )

    return sorted(summaries, key=lambda team: team["best_11_avg_overall"], reverse=True)


def save_json(data: list[dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as output_file:
        json.dump(data, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def print_table(team_overalls: list[dict[str, Any]]) -> None:
    print(f"{'Team':24} {'Players':>7} {'Avg':>7} {'Best 11':>8}")
    print("-" * 51)
    for team in team_overalls:
        print(
            f"{team['team'][:24]:24} "
            f"{team['players_count']:>7} "
            f"{team['avg_overall']:>7.2f} "
            f"{team['best_11_avg_overall']:>8.2f}"
        )


def main() -> None:
    arg_parser = argparse.ArgumentParser(description="Calcola l'overall medio delle squadre.")
    arg_parser.add_argument("-i", "--input", default=None, help="File JSON giocatori.")
    arg_parser.add_argument("-o", "--output", default=None, help="File JSON di output.")
    arg_parser.add_argument("--year", type=int, default=None, help="Anno (es. 2026), costruisce percorsi automaticamente.")
    arg_parser.add_argument("--all", action="store_true", help="Calcola overall per tutti gli anni disponibili.")
    arg_parser.add_argument("--best-count", type=int, default=11, help="Numero di migliori giocatori da mediare.")
    args = arg_parser.parse_args()

    roster_dir = BACKEND_DIR / "roster_giocatori"
    overall_dir = BACKEND_DIR / "overall_squadre"
    overall_dir.mkdir(exist_ok=True)

    if args.all:
        for path in sorted(roster_dir.glob("players_sofifa_[0-9][0-9][0-9][0-9].json")):
            year_str = path.stem.replace("players_sofifa_", "")
            output_path = overall_dir / f"team_overalls_{year_str}.json"
            print(f"\n--- {year_str} ---")
            team_overalls = calculate_team_overalls(load_players(str(path)), best_count=args.best_count)
            save_json(team_overalls, str(output_path))
            print_table(team_overalls)
            print(f"Salvate {len(team_overalls)} squadre in {output_path}")
        print(f"\nTutti gli overall salvati in {overall_dir}/")
        return

    if args.year:
        input_path = roster_dir / f"players_sofifa_{args.year}.json"
        output_path = overall_dir / f"team_overalls_{args.year}.json"
    else:
        input_path = Path(args.input) if args.input else DEFAULT_PLAYERS_PATH
        output_path = Path(args.output) if args.output else DEFAULT_TEAM_OVERALLS_PATH

    if not input_path.exists():
        print(f"File non trovato: {input_path}")
        return

    team_overalls = calculate_team_overalls(load_players(str(input_path)), best_count=args.best_count)
    save_json(team_overalls, str(output_path))
    print_table(team_overalls)
    print(f"\nSalvate {len(team_overalls)} squadre in {output_path}")


if __name__ == "__main__":
    main()
