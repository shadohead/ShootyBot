"""
Match highlights generation system for Valorant matches.

This module contains classes for analyzing match statistics and generating
highlights for Discord display. It's extracted from match_tracker.py to
improve maintainability and testability.
"""

import random
from typing import Dict, List, Any
from datetime import datetime
import logging


class MatchStatsCollector:
    """Collects and organizes player statistics from match data."""

    def __init__(self, match_data: Dict[str, Any], discord_members: List[Dict[str, Any]]):
        self.match_data = match_data
        self.discord_members = discord_members
        self.player_stats: List[Dict[str, Any]] = []
        self.puuid_to_member: Dict[str, Any] = {}

    def collect_basic_stats(self) -> None:
        """Collect basic player statistics (K/D/A, damage, shots)."""
        for dm in self.discord_members:
            member = dm['member']
            player_data = dm['player_data']
            pstats = player_data.get('stats', {})
            puuid = dm.get('account', {}).get('puuid') or player_data.get('puuid')

            self.puuid_to_member[puuid] = member

            self.player_stats.append({
                'member': member,
                'puuid': puuid,
                'kills': pstats.get('kills', 0),
                'deaths': pstats.get('deaths', 0),
                'assists': pstats.get('assists', 0),
                'headshots': pstats.get('headshots', 0),
                'bodyshots': pstats.get('bodyshots', 0),
                'legshots': pstats.get('legshots', 0),
                'score': pstats.get('score', 0),
                'damage_made': player_data.get('damage_made', 0),
                'damage_received': player_data.get('damage_received', 0),
                'agent': player_data.get('character', 'Unknown')
            })

    def get_player_stats(self) -> List[Dict[str, Any]]:
        """Return collected player statistics."""
        return self.player_stats

    def get_puuid_map(self) -> Dict[str, Any]:
        """Return mapping of PUUID to Discord member."""
        return self.puuid_to_member


class RoundAnalyzer:
    """Analyzes round-by-round data for advanced statistics."""

    def __init__(self, match_data: Dict[str, Any], puuid_to_member: Dict[str, Any]):
        self.match_data = match_data
        self.puuid_to_member = puuid_to_member
        self.rounds = match_data.get('rounds', [])

        # Initialize tracking dictionaries
        self.mk_counts = {puuid: {'2k': 0, '3k': 0, '4k': 0, '5k': 0} for puuid in puuid_to_member}
        self.ability_usage = {puuid: {'total': 0, 'ult': 0} for puuid in puuid_to_member}
        self.plant_counts = {puuid: 0 for puuid in puuid_to_member}
        self.defuse_counts = {puuid: 0 for puuid in puuid_to_member}
        self.clutch_attempts = {puuid: {'1v2': 0, '1v3': 0, '1v4': 0, '1v5': 0} for puuid in puuid_to_member}
        self.clutch_wins = {puuid: {'1v2': 0, '1v3': 0, '1v4': 0, '1v5': 0} for puuid in puuid_to_member}
        self.eco_round_kills = {puuid: 0 for puuid in puuid_to_member}
        self.eco_rounds_won = {puuid: 0 for puuid in puuid_to_member}
        self.first_kill_rounds = {puuid: {'won': 0, 'lost': 0} for puuid in puuid_to_member}
        self.damage_per_kill = {puuid: [] for puuid in puuid_to_member}
        self.knife_kills = {puuid: 0 for puuid in puuid_to_member}

    def analyze_all_rounds(self) -> None:
        """Analyze all rounds in the match."""
        for round_data in self.rounds:
            self._analyze_single_round(round_data)

    def _analyze_single_round(self, round_data: Dict[str, Any]) -> None:
        """Analyze a single round for all statistics."""
        winning_team = round_data.get('winning_team', '').lower()

        # Analyze player stats within the round
        for ps in round_data.get('player_stats', []):
            puuid = ps.get('player_puuid')
            if puuid not in self.puuid_to_member:
                continue

            self._analyze_multikills(ps)
            self._analyze_ability_usage(ps)
            self._analyze_eco_rounds(ps, winning_team)
            self._analyze_damage_and_kills(ps)

        # Analyze round-wide events
        self._analyze_plants_defuses(round_data)
        self._analyze_clutches(round_data, winning_team)
        self._analyze_first_bloods(round_data, winning_team)

    def _analyze_multikills(self, player_stats: Dict[str, Any]) -> None:
        """Track multikill counts for a player in a round."""
        puuid = player_stats.get('player_puuid')
        kills_in_round = len(player_stats.get('kill_events', []))

        if kills_in_round >= 5:
            self.mk_counts[puuid]['5k'] += 1
        elif kills_in_round >= 4:
            self.mk_counts[puuid]['4k'] += 1
        elif kills_in_round >= 3:
            self.mk_counts[puuid]['3k'] += 1
        elif kills_in_round >= 2:
            self.mk_counts[puuid]['2k'] += 1

    def _analyze_ability_usage(self, player_stats: Dict[str, Any]) -> None:
        """Track ability usage for a player."""
        puuid = player_stats.get('player_puuid')
        ability_casts = player_stats.get('ability_casts', {})

        if ability_casts:
            total_abilities = (
                ability_casts.get('c_casts', 0) +
                ability_casts.get('q_casts', 0) +
                ability_casts.get('e_casts', 0)
            )
            ult_casts = ability_casts.get('x_casts', 0)
            self.ability_usage[puuid]['total'] += total_abilities
            self.ability_usage[puuid]['ult'] += ult_casts

    def _analyze_eco_rounds(self, player_stats: Dict[str, Any], winning_team: str) -> None:
        """Track eco round performance."""
        puuid = player_stats.get('player_puuid')
        loadout_value = player_stats.get('economy', {}).get('loadout_value', 0)
        player_team = player_stats.get('team', '').lower()
        kills_in_round = len(player_stats.get('kill_events', []))

        if loadout_value < 4000:
            self.eco_round_kills[puuid] += kills_in_round
            if winning_team == player_team:
                self.eco_rounds_won[puuid] += 1

    def _analyze_damage_and_kills(self, player_stats: Dict[str, Any]) -> None:
        """Analyze damage patterns and knife kills."""
        puuid = player_stats.get('player_puuid')
        kill_events = player_stats.get('kill_events', [])
        damage_events = player_stats.get('damage_events', [])

        # Track victims for one-tap detection
        killed_puuids = set(ke.get('victim_puuid') for ke in kill_events)

        # Track damage per kill
        for damage_event in damage_events:
            damage_dealt = damage_event.get('damage', 0)
            receiver_puuid = damage_event.get('receiver_puuid')

            if receiver_puuid in killed_puuids and damage_dealt > 0:
                self.damage_per_kill[puuid].append(damage_dealt)

        # Track knife kills
        for kill_event in kill_events:
            weapon_name = kill_event.get('damage_weapon_name', '')
            if weapon_name and weapon_name.lower() == 'melee':
                self.knife_kills[puuid] += 1

    def _analyze_plants_defuses(self, round_data: Dict[str, Any]) -> None:
        """Track plant and defuse counts."""
        # Plant events
        for plant_event in round_data.get('plant_events', []):
            planter_puuid = plant_event.get('player_puuid')
            if planter_puuid in self.plant_counts:
                self.plant_counts[planter_puuid] += 1

        # Defuse events
        for defuse_event in round_data.get('defuse_events', []):
            defuser_puuid = defuse_event.get('defuser_puuid')
            if defuser_puuid in self.defuse_counts:
                self.defuse_counts[defuser_puuid] += 1

    def _analyze_clutches(self, round_data: Dict[str, Any], winning_team: str) -> None:
        """Detect and track clutch situations (1vX)."""
        team_alive = {'red': [], 'blue': []}

        # Determine who survived the round
        all_round_kills = []
        for ps in round_data.get('player_stats', []):
            all_round_kills.extend(ps.get('kill_events', []))

        for ps in round_data.get('player_stats', []):
            puuid = ps.get('player_puuid')
            player_team = ps.get('team', '').lower()

            # Check if player was killed
            was_killed = any(ke.get('victim_puuid') == puuid for ke in all_round_kills)

            if not was_killed and player_team in team_alive:
                team_alive[player_team].append(puuid)

        # Check for clutch situations
        for team in ['red', 'blue']:
            if len(team_alive[team]) == 1:
                clutcher_puuid = team_alive[team][0]
                other_team = 'blue' if team == 'red' else 'red'
                enemies_alive = len(team_alive[other_team])

                if clutcher_puuid in self.clutch_attempts and enemies_alive >= 2:
                    clutch_key = f'1v{min(enemies_alive, 5)}'
                    if clutch_key in self.clutch_attempts[clutcher_puuid]:
                        self.clutch_attempts[clutcher_puuid][clutch_key] += 1

                        if winning_team == team:
                            self.clutch_wins[clutcher_puuid][clutch_key] += 1

    def _analyze_first_bloods(self, round_data: Dict[str, Any], winning_team: str) -> None:
        """Track first blood/kill statistics."""
        all_kill_events = []
        for ps in round_data.get('player_stats', []):
            all_kill_events.extend(ps.get('kill_events', []))

        if not all_kill_events:
            return

        # Sort by kill time to find first kill
        all_kill_events.sort(key=lambda x: x.get('kill_time_in_round', 0))
        first_kill_event = all_kill_events[0]
        first_victim_puuid = first_kill_event.get('victim_puuid')

        # Find the killer
        first_killer_puuid = None
        killer_team = None
        for ps in round_data.get('player_stats', []):
            if any(ke.get('victim_puuid') == first_victim_puuid and
                   ke.get('kill_time_in_round', 0) == first_kill_event.get('kill_time_in_round', 0)
                   for ke in ps.get('kill_events', [])):
                first_killer_puuid = ps.get('player_puuid')
                killer_team = ps.get('team', '').lower()
                break

        # Track first kill round outcomes
        if first_killer_puuid in self.first_kill_rounds and killer_team:
            if winning_team == killer_team:
                self.first_kill_rounds[first_killer_puuid]['won'] += 1
            else:
                self.first_kill_rounds[first_killer_puuid]['lost'] += 1

    def get_stats(self) -> Dict[str, Any]:
        """Return all analyzed statistics."""
        return {
            'mk_counts': self.mk_counts,
            'ability_usage': self.ability_usage,
            'plant_counts': self.plant_counts,
            'defuse_counts': self.defuse_counts,
            'clutch_attempts': self.clutch_attempts,
            'clutch_wins': self.clutch_wins,
            'eco_round_kills': self.eco_round_kills,
            'eco_rounds_won': self.eco_rounds_won,
            'first_kill_rounds': self.first_kill_rounds,
            'damage_per_kill': self.damage_per_kill,
            'knife_kills': self.knife_kills
        }


class HighlightsGenerator:
    """Generates match highlights from player and round statistics."""

    # Configuration thresholds
    LEG_SHOT_THRESHOLD_PERCENT = 15
    HEADSHOT_THRESHOLD_PERCENT = 30
    HIGH_DAMAGE_THRESHOLD = 3000

    def __init__(
        self,
        player_stats: List[Dict[str, Any]],
        round_stats: Dict[str, Any],
        match_data: Dict[str, Any]
    ):
        self.player_stats = player_stats
        self.round_stats = round_stats
        self.match_data = match_data
        self.highlights: List[str] = []

    def generate_all_highlights(self) -> List[str]:
        """Generate all highlights for the match."""
        if len(self.player_stats) < 2:
            return []

        self._add_performance_highlights()
        self._add_accuracy_highlights()
        self._add_support_highlights()
        self._add_multikill_highlights()
        self._add_knife_kill_highlights()
        self._add_damage_highlights()
        self._add_economic_highlights()
        self._add_role_specific_highlights()
        self._add_advanced_stat_highlights()
        self._add_swing_round_highlights()
        self._add_fun_facts()

        return self.highlights

    def _add_performance_highlights(self) -> None:
        """Add highlights for top performers."""
        # Top Fragger
        top_fragger = max(self.player_stats, key=lambda x: x['kills'])
        if top_fragger['kills'] >= 25:
            self.highlights.append(
                f"🔥🔥 **DEMON MODE**: {top_fragger['member'].display_name} "
                f"({top_fragger['kills']} kills) - GOING NUCLEAR!"
            )
        elif top_fragger['kills'] >= 20:
            self.highlights.append(
                f"🔥 **Top Fragger**: {top_fragger['member'].display_name} "
                f"({top_fragger['kills']} kills) - ON FIRE!"
            )
        else:
            self.highlights.append(
                f"🎯 **Top Fragger**: {top_fragger['member'].display_name} "
                f"({top_fragger['kills']} kills)"
            )

        # Most Damage
        top_damage = max(self.player_stats, key=lambda x: x['damage_made'])
        if top_damage['damage_made'] >= 4000:
            self.highlights.append(
                f"💥 **DAMAGE MONSTER**: {top_damage['member'].display_name} "
                f"({top_damage['damage_made']:,} damage) - ANNIHILATION!"
            )
        elif top_damage['damage_made'] >= 3000:
            self.highlights.append(
                f"💥 **Damage Dealer**: {top_damage['member'].display_name} "
                f"({top_damage['damage_made']:,} damage)"
            )
        else:
            self.highlights.append(
                f"💪 **Damage Leader**: {top_damage['member'].display_name} "
                f"({top_damage['damage_made']:,} damage)"
            )

        # Best KDA
        kda_players = [(p, (p['kills'] + p['assists']) / max(p['deaths'], 1)) for p in self.player_stats]
        best_kda = max(kda_players, key=lambda x: x[1])
        if best_kda[1] >= 3.0:
            self.highlights.append(
                f"👑 **KDA KING**: {best_kda[0]['member'].display_name} "
                f"({best_kda[1]:.2f} KDA) - UNTOUCHABLE!"
            )
        elif best_kda[1] >= 2.0:
            self.highlights.append(
                f"⭐ **KDA Master**: {best_kda[0]['member'].display_name} "
                f"({best_kda[1]:.2f} KDA)"
            )
        else:
            self.highlights.append(
                f"💪 **Best KDA**: {best_kda[0]['member'].display_name} "
                f"({best_kda[1]:.2f} KDA)"
            )

    def _add_accuracy_highlights(self) -> None:
        """Add highlights for shooting accuracy."""
        total_shots = sum(p['headshots'] + p['bodyshots'] + p['legshots'] for p in self.player_stats)
        if total_shots == 0:
            return

        # Leg shot specialist
        leg_shot_king = max(self.player_stats, key=lambda x: x['legshots'])
        if leg_shot_king['legshots'] > 0:
            total_shots_player = leg_shot_king['headshots'] + leg_shot_king['bodyshots'] + leg_shot_king['legshots']
            leg_percentage = (leg_shot_king['legshots'] / max(total_shots_player, 1)) * 100

            if leg_percentage > self.LEG_SHOT_THRESHOLD_PERCENT:
                if leg_percentage > 25:
                    self.highlights.append(
                        f"🦵 **LEG DESTROYER**: {leg_shot_king['member'].display_name} "
                        f"({leg_shot_king['legshots']} leg shots, {leg_percentage:.1f}%) - Ankle Biter!"
                    )
                else:
                    self.highlights.append(
                        f"🦵 **Leg Shot Specialist**: {leg_shot_king['member'].display_name} "
                        f"({leg_shot_king['legshots']} leg shots, {leg_percentage:.1f}%)"
                    )

        # Headshot accuracy
        headshot_ace = max(self.player_stats, key=lambda x: x['headshots'] / max(x['headshots'] + x['bodyshots'] + x['legshots'], 1))
        total_shots_player = headshot_ace['headshots'] + headshot_ace['bodyshots'] + headshot_ace['legshots']

        if total_shots_player > 20:
            hs_percentage = (headshot_ace['headshots'] / total_shots_player) * 100
            if hs_percentage > 40:
                self.highlights.append(
                    f"🎯 **HEADSHOT DEMON**: {headshot_ace['member'].display_name} "
                    f"({hs_percentage:.1f}% HS) - INSANE AIM!"
                )
            elif hs_percentage > self.HEADSHOT_THRESHOLD_PERCENT:
                self.highlights.append(
                    f"🎯 **Headshot Machine**: {headshot_ace['member'].display_name} "
                    f"({hs_percentage:.1f}% HS accuracy)"
                )

    def _add_support_highlights(self) -> None:
        """Add highlights for support players."""
        assist_king = max(self.player_stats, key=lambda x: x['assists'])
        if assist_king['assists'] >= 10:
            self.highlights.append(
                f"🤝 **SUPPORT HERO**: {assist_king['member'].display_name} "
                f"({assist_king['assists']} assists) - Team Player!"
            )
        elif assist_king['assists'] >= 7:
            self.highlights.append(
                f"🤝 **Team Player**: {assist_king['member'].display_name} "
                f"({assist_king['assists']} assists)"
            )

    def _add_multikill_highlights(self) -> None:
        """Add multikill highlights from round data."""
        mk_counts = self.round_stats['mk_counts']

        for p in self.player_stats:
            counts = mk_counts.get(p['puuid'], {})
            if counts.get('5k', 0) > 0:
                ace_count = counts['5k']
                plural = 's' if ace_count > 1 else ''
                self.highlights.append(
                    f"🔥 **ACE ALERT**: {p['member'].display_name} scored {ace_count} ACE{plural}!"
                )
            elif counts.get('4k', 0) > 0:
                fourk = counts['4k']
                plural = 's' if fourk > 1 else ''
                self.highlights.append(
                    f"⚡ **MULTIKILL MASTER**: {p['member'].display_name} landed {fourk} 4K{plural}!"
                )
            elif counts.get('3k', 0) >= 2:
                threek = counts['3k']
                plural = 's' if threek > 1 else ''
                self.highlights.append(
                    f"💥 {p['member'].display_name} racked up {threek} 3K{plural}!"
                )

    def _add_knife_kill_highlights(self) -> None:
        """Add knife kill highlights."""
        knife_kills = self.round_stats['knife_kills']

        for p in self.player_stats:
            knife_count = knife_kills.get(p['puuid'], 0)
            if knife_count > 0:
                plural = 's' if knife_count > 1 else ''
                if knife_count >= 3:
                    self.highlights.append(
                        f"🔪 **KNIFE MASTER**: {p['member'].display_name} "
                        f"got {knife_count} knife kill{plural}! RUTHLESS!"
                    )
                elif knife_count >= 2:
                    self.highlights.append(
                        f"🗡️ **BLADE WARRIOR**: {p['member'].display_name} "
                        f"secured {knife_count} knife kills!"
                    )
                else:
                    self.highlights.append(
                        f"🔪 {p['member'].display_name} got a knife kill! Disrespectful!"
                    )

    def _add_damage_highlights(self) -> None:
        """Add damage-related highlights."""
        tank_player = max(self.player_stats, key=lambda x: x['damage_received'])

        # Find glass cannon
        glass_cannon = None
        for p in self.player_stats:
            if p['damage_made'] > 3000 and p['damage_received'] > self.HIGH_DAMAGE_THRESHOLD:
                glass_cannon = p
                break

        if glass_cannon:
            self.highlights.append(
                f"💎 **GLASS CANNON**: {glass_cannon['member'].display_name} "
                f"({glass_cannon['damage_made']:,}D dealt, {glass_cannon['damage_received']:,}D taken)"
            )
        elif tank_player['damage_received'] > self.HIGH_DAMAGE_THRESHOLD:
            if tank_player['damage_received'] > 4000:
                self.highlights.append(
                    f"🛡️ **HUMAN FORTRESS**: {tank_player['member'].display_name} "
                    f"({tank_player['damage_received']:,} damage tanked) - UNMOVABLE!"
                )
            else:
                self.highlights.append(
                    f"🛡️ **Human Shield**: {tank_player['member'].display_name} "
                    f"({tank_player['damage_received']:,} damage taken)"
                )

        # Economic efficiency
        efficient_player = min(self.player_stats, key=lambda x: x['deaths'] / max(x['damage_made'], 1))
        if efficient_player['deaths'] <= 12 and efficient_player['damage_made'] >= 2500:
            efficiency = efficient_player['damage_made'] / max(efficient_player['deaths'], 1)
            self.highlights.append(
                f"💰 **ECONOMY MASTER**: {efficient_player['member'].display_name} "
                f"({efficiency:.0f} damage per death) - Efficient!"
            )

    def _add_economic_highlights(self) -> None:
        """Add survivor and score highlights."""
        if len(self.player_stats) >= 3:
            # The Survivor
            survivor = min(self.player_stats, key=lambda x: x['deaths'])
            if survivor['deaths'] <= 8:
                if survivor['deaths'] <= 5:
                    self.highlights.append(
                        f"🛡️ **IMMORTAL**: {survivor['member'].display_name} "
                        f"({survivor['deaths']} deaths) - Untouchable!"
                    )
                else:
                    self.highlights.append(
                        f"💚 **Survivor**: {survivor['member'].display_name} "
                        f"({survivor['deaths']} deaths) - Hard to kill!"
                    )

        # Score leader
        score_leader = max(self.player_stats, key=lambda x: x['score'])
        if score_leader['score'] >= 300:
            if score_leader['score'] >= 400:
                self.highlights.append(
                    f"🌟 **MVP PERFORMANCE**: {score_leader['member'].display_name} "
                    f"({score_leader['score']} ACS) - LEGENDARY!"
                )
            else:
                self.highlights.append(
                    f"⭐ **Score Leader**: {score_leader['member'].display_name} "
                    f"({score_leader['score']} ACS)"
                )

    def _add_role_specific_highlights(self) -> None:
        """Add agent role-specific highlights."""
        # Duelist performance
        duelist_agents = ['Jett', 'Reyna', 'Phoenix', 'Raze', 'Yoru', 'Neon', 'Iso']
        duelists = [p for p in self.player_stats if p['agent'] in duelist_agents]
        if duelists:
            top_duelist = max(duelists, key=lambda x: x['kills'])
            if top_duelist['kills'] >= 20:
                self.highlights.append(
                    f"⚔️ **DUELIST DIFF**: {top_duelist['member'].display_name} "
                    f"({top_duelist['agent']}) - Entry fragging king!"
                )

        # Controller performance
        controller_agents = ['Brimstone', 'Omen', 'Viper', 'Astra', 'Harbor', 'Clove']
        controllers = [p for p in self.player_stats if p['agent'] in controller_agents]
        if controllers:
            top_controller = max(controllers, key=lambda x: x['assists'])
            if top_controller['assists'] >= 12:
                self.highlights.append(
                    f"🧠 **BIG BRAIN**: {top_controller['member'].display_name} "
                    f"({top_controller['agent']}) - Tactical genius!"
                )

        # Sentinel performance
        sentinel_agents = ['Killjoy', 'Cypher', 'Sage', 'Chamber', 'Deadlock', 'Vyse']
        sentinels = [p for p in self.player_stats if p['agent'] in sentinel_agents]
        if sentinels:
            top_sentinel = max(sentinels, key=lambda x: x['score'])
            if top_sentinel['score'] >= 300:
                self.highlights.append(
                    f"🔒 **SITE ANCHOR**: {top_sentinel['member'].display_name} "
                    f"({top_sentinel['agent']}) - Holding it down!"
                )

    def _add_advanced_stat_highlights(self) -> None:
        """Add highlights from advanced round statistics."""
        # Ability usage
        ability_usage = self.round_stats['ability_usage']
        for p in self.player_stats:
            puuid = p['puuid']
            abilities_used = ability_usage.get(puuid, {}).get('total', 0)
            ults_used = ability_usage.get(puuid, {}).get('ult', 0)

            if abilities_used >= 40:
                self.highlights.append(
                    f"⚡ **UTILITY KING**: {p['member'].display_name} "
                    f"({abilities_used} abilities used) - Maximum impact!"
                )
                break
            elif ults_used >= 6:
                self.highlights.append(
                    f"🎭 **ULT MASTER**: {p['member'].display_name} "
                    f"({ults_used} ultimates) - High-impact plays!"
                )
                break

        # Plant/defuse heroes
        plant_counts = self.round_stats['plant_counts']
        defuse_counts = self.round_stats['defuse_counts']
        for p in self.player_stats:
            puuid = p['puuid']
            plants = plant_counts.get(puuid, 0)
            defuses = defuse_counts.get(puuid, 0)

            if plants >= 5:
                self.highlights.append(
                    f"🌱 **SPIKE SPECIALIST**: {p['member'].display_name} "
                    f"({plants} plants) - Objective focused!"
                )
                break
            elif defuses >= 2:
                self.highlights.append(
                    f"🛠️ **DEFUSE KING**: {p['member'].display_name} "
                    f"({defuses} defuses) - Clutch saves!"
                )
                break

        # Clutch performance
        clutch_wins = self.round_stats['clutch_wins']
        clutch_attempts = self.round_stats['clutch_attempts']
        for p in self.player_stats:
            puuid = p['puuid']
            total_clutch_wins = sum(clutch_wins.get(puuid, {}).values())
            total_clutch_attempts = sum(clutch_attempts.get(puuid, {}).values())

            if total_clutch_wins >= 2:
                clutch_str = ""
                for clutch_type in ['1v5', '1v4', '1v3', '1v2']:
                    if clutch_wins.get(puuid, {}).get(clutch_type, 0) > 0:
                        wins = clutch_wins[puuid][clutch_type]
                        clutch_str = f"{wins} {clutch_type}" if wins == 1 else f"{wins}x {clutch_type}"
                        break

                if clutch_str:
                    self.highlights.append(
                        f"🎭 **CLUTCH MASTER**: {p['member'].display_name} "
                        f"({clutch_str} wins) - Ice in their veins!"
                    )
                    break

        # Eco round performance
        eco_round_kills = self.round_stats['eco_round_kills']
        eco_rounds_won = self.round_stats['eco_rounds_won']
        for p in self.player_stats:
            puuid = p['puuid']
            eco_kills = eco_round_kills.get(puuid, 0)
            eco_wins = eco_rounds_won.get(puuid, 0)

            if eco_kills >= 5 or eco_wins >= 2:
                self.highlights.append(
                    f"💰 **ECO WARRIOR**: {p['member'].display_name} "
                    f"({eco_kills} eco kills, {eco_wins} eco wins) - Budget beast!"
                )
                break

        # Entry duel win rate
        first_kill_rounds = self.round_stats['first_kill_rounds']
        for p in self.player_stats:
            puuid = p['puuid']
            fk_won = first_kill_rounds.get(puuid, {}).get('won', 0)
            fk_lost = first_kill_rounds.get(puuid, {}).get('lost', 0)
            fk_total = fk_won + fk_lost

            if fk_total >= 5:
                win_rate = (fk_won / fk_total) * 100
                if win_rate >= 65:
                    self.highlights.append(
                        f"⚔️ **ENTRY GOD**: {p['member'].display_name} "
                        f"({fk_won}/{fk_total} opening duels won, {win_rate:.0f}%) - First blood king!"
                    )
                    break
                elif win_rate >= 55:
                    self.highlights.append(
                        f"⚡ **ENTRY FRAGGER**: {p['member'].display_name} "
                        f"({fk_won}/{fk_total} duels, {win_rate:.0f}%)"
                    )
                    break

        # One-tap detection
        damage_per_kill = self.round_stats['damage_per_kill']
        for p in self.player_stats:
            puuid = p['puuid']
            damages = damage_per_kill.get(puuid, [])

            if damages:
                avg_dpk = sum(damages) / len(damages)
                if avg_dpk <= 155 and p['kills'] >= 10:
                    self.highlights.append(
                        f"🎯 **ONE-TAP GOD**: {p['member'].display_name} "
                        f"({avg_dpk:.0f} avg damage/kill) - Efficient eliminations!"
                    )
                    break

    def _add_swing_round_highlights(self) -> None:
        """Add highlights for swing rounds (eco wins)."""
        swing_rounds = self._identify_swing_rounds()
        if not swing_rounds:
            return

        # Limit to most significant swing rounds
        for sr in swing_rounds[:2]:
            self.highlights.append(
                f"💸 **Swing Round**: Round {sr['round']} won with {sr['diff']:,} credit deficit!"
            )

    def _identify_swing_rounds(self) -> List[Dict[str, Any]]:
        """Identify rounds where the lower economy team won."""
        swing_rounds = []
        for idx, round_data in enumerate(self.match_data.get('rounds', []), start=1):
            team_totals = {'red': 0, 'blue': 0}
            for ps in round_data.get('player_stats', []):
                team = (ps.get('team') or ps.get('player_team') or '').lower()
                if team in team_totals:
                    loadout = ps.get('economy', {}).get('loadout_value', 0)
                    team_totals[team] += loadout

            diff = abs(team_totals['red'] - team_totals['blue'])
            if diff >= 6000:
                winner = round_data.get('winning_team', '').lower()
                if not winner:
                    continue
                underdog = 'red' if team_totals['red'] < team_totals['blue'] else 'blue'
                if winner == underdog:
                    swing_rounds.append({'round': idx, 'diff': diff, 'winner': winner})

        swing_rounds.sort(key=lambda r: r['diff'], reverse=True)
        return swing_rounds

    def _add_fun_facts(self) -> None:
        """Add fun team-wide statistics."""
        total_team_damage = sum(p['damage_made'] for p in self.player_stats)
        total_team_kills = sum(p['kills'] for p in self.player_stats)
        total_team_deaths = sum(p['deaths'] for p in self.player_stats)
        total_team_assists = sum(p['assists'] for p in self.player_stats)

        fun_facts = []

        # Team KDA
        team_kda = (total_team_kills + total_team_assists) / max(total_team_deaths, 1)
        if team_kda >= 2.0:
            fun_facts.append(f"👑 **Team KDA**: {team_kda:.2f} - Dominant performance!")
        elif team_kda >= 1.5:
            fun_facts.append(f"💪 **Team KDA**: {team_kda:.2f} - Solid teamwork!")
        else:
            fun_facts.append(f"⚔️ **Team KDA**: {team_kda:.2f} - Hard fought!")

        # Accuracy insights
        total_shots = sum(p['headshots'] + p['bodyshots'] + p['legshots'] for p in self.player_stats)
        if total_shots > 0:
            total_headshots = sum(p['headshots'] for p in self.player_stats)
            team_hs_rate = (total_headshots / total_shots) * 100

            if team_hs_rate >= 25:
                fun_facts.append(f"🎯 **LASER PRECISION**: {team_hs_rate:.1f}% headshot rate")
            elif team_hs_rate >= 20:
                fun_facts.append(f"🔥 **Sharp Shooting**: {team_hs_rate:.1f}% headshot rate")
            elif team_hs_rate >= 15:
                fun_facts.append(f"💪 **Decent Aim**: {team_hs_rate:.1f}% headshot rate")
            else:
                fun_facts.append(f"🎲 **Spray & Pray**: {team_hs_rate:.1f}% headshot rate")

        # Team dynamics
        kill_spread = max(p['kills'] for p in self.player_stats) - min(p['kills'] for p in self.player_stats)
        if kill_spread <= 5:
            fun_facts.append("🤝 **TEAM EFFORT**: Kills spread evenly!")
        elif kill_spread >= 15:
            fun_facts.append("🎭 **CARRY MODE**: Someone's doing the heavy lifting!")

        # Add a sample of fun facts
        self.highlights.extend(random.sample(fun_facts, min(2, len(fun_facts))))
