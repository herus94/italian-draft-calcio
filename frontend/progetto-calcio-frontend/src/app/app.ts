import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

const API_URL = (window as unknown as Record<string, unknown>)['__API_URL__'] as string || `http://${window.location.hostname}:8000`;


type Formation = {
  id: string;
  label: string;
  slots: Record<string, number>;
};

type Player = {
  player_id: number;
  name: string;
  overall: number;
  roles: string[];
  team: string;
  mapped_team: string;
};

type DraftPlayer = Player & {
  departments: string[];
  pickable: boolean;
};

type DraftPick = {
  round: number;
  team: string;
  player: Player;
  assigned_department: string;
};

type FormationSlot = {
  id: string;
  department: string;
  index: number;
  player: DraftPick | null;
};

type DraftSession = {
  id: string;
  formation: Formation;
  selected_players: DraftPick[];
  current_team: string | null;
  completed: boolean;
  year: number;
  team_filter: string | null;
};

type GoalEvent = {
  minute: number;
  team: string;
  scorer: string;
};

type Match = {
  id: string;
  matchday: number;
  home_team: string;
  away_team: string;
  home_goals: number | null;
  away_goals: number | null;
  goals: GoalEvent[];
  played: boolean;
};

type StandingRow = {
  team: string;
  played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
};

type Season = {
  id: string;
  user_team: string;
  replaced_team: string;
  current_matchday: number;
  matches: Match[];
  standings: StandingRow[];
  completed: boolean;
};

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly http = inject(HttpClient);

  formations = signal<Formation[]>([]);
  selectedFormationId = signal('4-3-3');
  years = signal<number[]>([]);
  allYearsMode = signal(true);
  selectedYear = signal<number>(2026);
  teams = signal<string[]>([]);
  teamFilter = signal<string | null>(null);
  difficulty = signal<string>('normale');
  opponentAllYears = signal(true);
  opponentYear = signal<number>(2026);
  draft = signal<DraftSession | null>(null);
  rolledPlayers = signal<DraftPlayer[]>([]);
  selectedPlayer = signal<DraftPlayer | null>(null);
  slotMap = signal<Record<string, Record<number, number>>>({});
  season = signal<Season | null>(null);
  loading = signal(false);
  message = signal('');


  remainingSlots = computed(() => {
    const draft = this.draft();
    if (!draft) {
      return {};
    }

    const remaining = { ...draft.formation.slots };
    for (const pick of draft.selected_players) {
      remaining[pick.assigned_department] -= 1;
    }
    return remaining;
  });

  teamOverall = computed(() => {
    const picks = this.draft()?.selected_players ?? [];
    if (!picks.length) {
      return 0;
    }
    const total = picks.reduce((sum, pick) => sum + pick.player.overall, 0);
    return Math.round((total / picks.length) * 10) / 10;
  });

  formationSlots = computed(() => {
    const draft = this.draft();
    const map = this.slotMap();
    const slots: FormationSlot[] = [];
    if (!draft) return slots;
    const deptOrder = ['POR', 'DIF', 'CC', 'ATT'];
    for (const dept of deptOrder) {
      const count = draft.formation.slots[dept] ?? 0;
      const deptPicks = draft.selected_players.filter(p => p.assigned_department === dept);
      const deptMap = map[dept] ?? {};
      const hasMapping = Object.keys(deptMap).length > 0;
      if (hasMapping) {
        const used = new Set<number>();
        const placed: (DraftPick | null)[] = new Array(count).fill(null);
        for (const [slotIdxStr, playerId] of Object.entries(deptMap)) {
          const slotIdx = parseInt(slotIdxStr);
          if (slotIdx < count) {
            const pick = deptPicks.find(p => p.player.player_id === playerId);
            if (pick) { placed[slotIdx] = pick; used.add(playerId); }
          }
        }
        let nextEmpty = 0;
        for (const pick of deptPicks) {
          if (used.has(pick.player.player_id)) continue;
          while (nextEmpty < count && placed[nextEmpty] !== null) nextEmpty++;
          if (nextEmpty < count) placed[nextEmpty] = pick;
        }
        for (let i = 0; i < count; i++) {
          slots.push({ id: `${dept}-${i}`, department: dept, index: i, player: placed[i] });
        }
      } else {
        for (let i = 0; i < count; i++) {
          slots.push({ id: `${dept}-${i}`, department: dept, index: i, player: deptPicks[i] ?? null });
        }
      }
    }
    return slots;
  });

  isChampion = computed(() => {
    const season = this.season();
    return season?.completed && season.standings[0]?.team === season.user_team;
  });

  userMatches = computed(() => {
    const season = this.season();
    if (!season) {
      return [];
    }
    return season.matches
      .filter((match) => match.home_team === season.user_team || match.away_team === season.user_team)
      .filter((match) => match.played)
      .slice(-5)
      .reverse();
  });

  constructor() {
    void this.loadFormations();
    void this.loadYears();
  }

  async loadFormations() {
    this.formations.set(await firstValueFrom(this.http.get<Formation[]>(`${API_URL}/formations`)));
  }

  async loadYears() {
    const years = await firstValueFrom(this.http.get<number[]>(`${API_URL}/years`));
    this.years.set(years);
    if (years.length) this.selectedYear.set(years[years.length - 1]);
    await this.loadTeams();
  }

  async loadTeams() {
    this.teams.set(await firstValueFrom(this.http.get<string[]>(`${API_URL}/teams`)));
  }

  onYearChange() {
  }

  onAllYearsToggle(event: Event) {
    this.allYearsMode.set((event.target as HTMLInputElement).checked);
  }

  onTeamChange(event: Event) {
    const value = (event.target as HTMLSelectElement).value;
    this.teamFilter.set(value || null);
  }

  async startDraft() {
    if (this.draft()) {
      this.draft.set(null);
      this.rolledPlayers.set([]);
      this.selectedPlayer.set(null);
      this.slotMap.set({});
      this.season.set(null);
      this.message.set('');
      return;
    }

    await this.run(async () => {
      const draft = await firstValueFrom(
        this.http.post<DraftSession>(`${API_URL}/draft/start`, {
          formation_id: this.selectedFormationId(),
          year: this.allYearsMode() ? 0 : this.selectedYear(),
          team_filter: this.teamFilter() || null,
          difficulty: this.difficulty(),
        }),
      );
      this.draft.set(draft);
      this.rolledPlayers.set([]);
      this.slotMap.set({});
      this.season.set(null);
      this.message.set('Draft iniziato. Tira il dado.');
    });
  }

  async rollTeam() {
    let draft = this.draft();
    if (!draft) {
      draft = await firstValueFrom(
        this.http.post<DraftSession>(`${API_URL}/draft/start`, {
          formation_id: this.selectedFormationId(),
          year: this.allYearsMode() ? 0 : this.selectedYear(),
          team_filter: this.teamFilter() || null,
          difficulty: this.difficulty(),
        }),
      );
      this.draft.set(draft);
      this.slotMap.set({});
      this.season.set(null);
    }

    await this.run(async () => {
      const response = await firstValueFrom(
        this.http.post<{ session: DraftSession; players: DraftPlayer[] }>(`${API_URL}/draft/${draft.id}/roll`, {}),
      );
      this.draft.set(response.session);
      this.rolledPlayers.set(response.players);
      this.selectedPlayer.set(null);
    });
  }

  async pickPlayer(player: DraftPlayer, department: string, slotIndex?: number) {
    const draft = this.draft();
    if (!draft || !player.pickable || this.remainingSlots()[department] <= 0) {
      return;
    }

    await this.run(async () => {
      const updated = await firstValueFrom(
        this.http.post<DraftSession>(`${API_URL}/draft/${draft.id}/pick`, {
          player_id: player.player_id,
          department,
        }),
      );

      if (slotIndex !== undefined) {
        const map = { ...this.slotMap() };
        if (!map[department]) map[department] = {};
        map[department][slotIndex] = player.player_id;
        this.slotMap.set(map);
      }

      this.draft.set({ ...updated });
      this.rolledPlayers.set([]);
      this.selectedPlayer.set(null);
      this.message.set(updated.completed ? 'Rosa completa. Puoi iniziare il campionato.' : 'Scelta salvata. Tira ancora.');
    });
  }

  async startSeason() {
    const draft = this.draft();
    if (!draft?.completed) {
      return;
    }

    await this.run(async () => {
      const season = await firstValueFrom(
        this.http.post<Season>(`${API_URL}/season/start`, {
          draft_session_id: draft.id,
          user_team_name: 'Draft FC',
          year: this.opponentAllYears() ? 0 : this.opponentYear(),
        }),
      );
      this.season.set(season);
      this.message.set(`Campionato creato: Draft FC prende il posto di ${season.replaced_team}.`);
    });
  }

  async simulateNext() {
    await this.simulate('simulate-next', 'Giornata simulata.');
  }

  async simulateMid() {
    await this.simulate('simulate-to-mid', 'Simulato fino a metà stagione.');
  }

  async simulateEnd() {
    await this.simulate('simulate-to-end', 'Stagione completata.');
  }

  selectPlayer(player: DraftPlayer) {
    if (!player.pickable) return;
    this.selectedPlayer.set(
      this.selectedPlayer()?.player_id === player.player_id ? null : player
    );
  }

  assignToSlot(slot: FormationSlot) {
    const player = this.selectedPlayer();
    if (!player || slot.player || !player.pickable) return;
    if (!player.departments.includes(slot.department)) return;
    if ((this.remainingSlots()[slot.department] ?? 0) <= 0) return;

    this.pickPlayer(player, slot.department, slot.index);
  }

  tierClass(overall: number): string {
    if (overall >= 85) return 'tier-elite';
    if (overall >= 80) return 'tier-gold';
    if (overall >= 75) return 'tier-silver';
    return 'tier-bronze';
  }

  shortName(name: string): string {
    const parts = name.trim().split(' ');
    if (parts.length <= 1) return name;
    return parts.slice(1).join(' ');
  }

  playerDepartments(player: DraftPlayer) {
    return player.departments.filter((department) => (this.remainingSlots()[department] ?? 0) > 0);
  }

  private async simulate(action: string, doneMessage: string) {
    const season = this.season();
    if (!season) {
      return;
    }

    await this.run(async () => {
      this.season.set(await firstValueFrom(this.http.post<Season>(`${API_URL}/season/${season.id}/${action}`, {})));
      this.message.set(doneMessage);
    });
  }

  private async run(action: () => Promise<void>) {
    this.loading.set(true);
    this.message.set('');
    try {
      await action();
    } catch (error) {
      this.message.set(error instanceof Error ? error.message : 'Qualcosa non ha funzionato.');
    } finally {
      this.loading.set(false);
    }
  }
}
