"""Tests for the advanced per-match statlines (clutches, spike plays, economy,
behavior, kill records) and the scored highlight selection used by the
post-game recap."""

import os
import sys

import pytest
from unittest.mock import MagicMock, patch

import discord

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from valorant_client import ValorantClient
from match_tracker import MatchTracker


def make_player(puuid, team, kills=0, deaths=0, assists=0, character='Jett',
                behavior=None, ability_casts=None):
    return {
        'puuid': puuid,
        'team': team,
        'character': character,
        'stats': {'kills': kills, 'deaths': deaths, 'assists': assists,
                  'headshots': 0, 'bodyshots': 0, 'legshots': 0, 'score': 0},
        'damage_made': 0,
        'damage_received': 0,
        'behavior': behavior or {},
        'ability_casts': ability_casts or {},
    }


def build_advanced_match():
    """A 2v2 match crafted to exercise every advanced statline for A1:

    Round 1 (pistol): A2 dies first, A1 wins a 1v2 clutch (Sheriff kill from
    range + knife kill) after planting the spike. Red wins.
    Round 2: A1 dies first holding an expensive loadout; A1 also defused with
    an enemy still alive (ninja defuse). Blue wins.
    """
    return {
        'metadata': {
            'matchid': 'adv-match-1',
            'map': 'Ascent',
            'mode': 'Competitive',
            'mode_id': 'competitive',
            'rounds_played': 2,
            'game_start': 1700000000,
            'game_length': 1800,
        },
        'players': {
            'all_players': [
                make_player('A1', 'Red', kills=2, deaths=1,
                            behavior={'afk_rounds': 2,
                                      'friendly_fire': {'incoming': 0, 'outgoing': 150}},
                            ability_casts={'c_cast': 3, 'q_cast': 4, 'e_cast': 10, 'x_cast': 2}),
                make_player('A2', 'Red', deaths=1, character='Sage'),
                make_player('B1', 'Blue', kills=1, deaths=1, character='Omen'),
                make_player('B2', 'Blue', kills=1, deaths=1, character='Reyna'),
            ]
        },
        'teams': {'red': {'has_won': True, 'rounds_won': 1},
                  'blue': {'has_won': False, 'rounds_won': 1}},
        'rounds': [
            {
                'winning_team': 'Red',
                'plant_events': {'planted_by': {'puuid': 'A1'}, 'plant_site': 'A'},
                'defuse_events': {},
                'player_stats': [
                    {
                        'player_puuid': 'A1', 'kills': 2,
                        'economy': {'loadout_value': 800, 'spent': 800},
                        'kill_events': [
                            {'victim_puuid': 'B1', 'kill_time_in_round': 10000,
                             'damage_weapon_name': 'Sheriff', 'assistants': [],
                             'victim_death_location': {'x': 0, 'y': 4500},
                             'player_locations_on_kill': [
                                 {'player_puuid': 'A1', 'location': {'x': 0, 'y': 0}},
                             ]},
                            {'victim_puuid': 'B2', 'kill_time_in_round': 15000,
                             'damage_weapon_name': 'Melee', 'assistants': []},
                        ],
                    },
                    {'player_puuid': 'A2', 'kills': 0, 'kill_events': [],
                     'economy': {'loadout_value': 800, 'spent': 700}},
                    {
                        'player_puuid': 'B1', 'kills': 1,
                        'economy': {'loadout_value': 800, 'spent': 800},
                        'kill_events': [
                            {'victim_puuid': 'A2', 'kill_time_in_round': 5000,
                             'damage_weapon_name': 'Classic', 'assistants': []},
                        ],
                    },
                    {'player_puuid': 'B2', 'kills': 0, 'kill_events': [],
                     'economy': {'loadout_value': 800, 'spent': 800}},
                ],
            },
            {
                'winning_team': 'Blue',
                'plant_events': {},
                'defuse_events': {
                    'defused_by': {'puuid': 'A1'},
                    'player_locations_on_defuse': [
                        {'player_puuid': 'A1', 'location': {'x': 0, 'y': 0}},
                        {'player_puuid': 'B2', 'location': {'x': 100, 'y': 100}},
                    ],
                },
                'player_stats': [
                    {'player_puuid': 'A1', 'kills': 0, 'kill_events': [],
                     'economy': {'loadout_value': 5700, 'spent': 4500}},
                    {'player_puuid': 'A2', 'kills': 0, 'kill_events': [],
                     'economy': {'loadout_value': 3900, 'spent': 3600}},
                    {
                        'player_puuid': 'B2', 'kills': 1,
                        'economy': {'loadout_value': 3900, 'spent': 3600},
                        'kill_events': [
                            {'victim_puuid': 'A1', 'kill_time_in_round': 4000,
                             'damage_weapon_name': 'Vandal', 'assistants': []},
                        ],
                    },
                    {'player_puuid': 'B1', 'kills': 0, 'kill_events': [],
                     'economy': {'loadout_value': 3900, 'spent': 3600}},
                ],
            },
        ],
    }


@pytest.fixture
def client():
    with patch('valorant_client.HENRIK_API_KEY', ''):
        return ValorantClient()


class TestAdvancedRowStats:
    def test_clutch_won_recorded(self, client):
        row = client.build_match_stats_row(build_advanced_match(), 'A1')
        assert row['clutches_attempted']['1v2'] == 1
        assert row['clutches_won']['1v2'] == 1

    def test_clutch_lost_recorded(self, client):
        # In round 1, B2 ends up 1v1 against A1 after B1 dies, and loses
        row = client.build_match_stats_row(build_advanced_match(), 'B2')
        assert row['clutches_attempted']['1v1'] == 1
        assert row['clutches_won']['1v1'] == 0

    def test_clutch_attempt_for_last_teammate_standing(self, client):
        # A2 dies first in round 1 (no clutch there), but in round 2 A1's
        # death leaves A2 alone against both enemies - a lost 1v2 attempt
        row = client.build_match_stats_row(build_advanced_match(), 'A2')
        assert row['clutches_attempted'] == {'1v1': 0, '1v2': 1, '1v3': 0, '1v4': 0, '1v5': 0}
        assert sum(row['clutches_won'].values()) == 0

    def test_spike_plants_and_ninja_defuse(self, client):
        row = client.build_match_stats_row(build_advanced_match(), 'A1')
        extra = row['extra']
        assert extra['plants'] == 1
        assert extra['defuses'] == 1
        assert extra['ninja_defuses'] == 1

    def test_defuse_without_enemies_alive_is_not_ninja(self, client):
        match = build_advanced_match()
        match['rounds'][1]['defuse_events']['player_locations_on_defuse'] = [
            {'player_puuid': 'A1', 'location': {'x': 0, 'y': 0}},
            {'player_puuid': 'A2', 'location': {'x': 50, 'y': 50}},
        ]
        row = client.build_match_stats_row(match, 'A1')
        assert row['extra']['defuses'] == 1
        assert row['extra']['ninja_defuses'] == 0

    def test_economy_tracking(self, client):
        row = client.build_match_stats_row(build_advanced_match(), 'A1')
        extra = row['extra']
        assert extra['money_spent'] == 800 + 4500
        assert extra['loadout_value_total'] == 800 + 5700
        assert extra['rounds_with_economy'] == 2
        # A1 only died in round 2, holding a 5700 loadout
        assert extra['most_expensive_death'] == 5700

    def test_kill_records(self, client):
        row = client.build_match_stats_row(build_advanced_match(), 'A1')
        extra = row['extra']
        assert extra['fastest_kill_ms'] == 10000
        assert extra['longest_kill_distance'] == 4500

    def test_behavior_and_ability_stats(self, client):
        row = client.build_match_stats_row(build_advanced_match(), 'A1')
        extra = row['extra']
        assert extra['friendly_fire_damage'] == 150
        assert extra['afk_rounds'] == 2
        assert extra['ability_casts'] == 19

    def test_ability_casts_none_when_data_missing(self, client):
        # A2 has an empty ability_casts dict -> unknown, not zero
        row = client.build_match_stats_row(build_advanced_match(), 'A2')
        assert row['extra']['ability_casts'] is None

    def test_weapon_kills_still_collected(self, client):
        row = client.build_match_stats_row(build_advanced_match(), 'A1')
        assert row['weapon_kills'] == {'Sheriff': 1, 'Melee': 1}

    def test_no_round_data_leaves_extras_at_defaults(self, client):
        match = build_advanced_match()
        match['rounds'] = []
        row = client.build_match_stats_row(match, 'A1')
        extra = row['extra']
        assert extra['plants'] == 0
        assert extra['money_spent'] == 0
        assert extra['fastest_kill_ms'] == 0
        # Behavior stats come from the player record, not round data
        assert extra['friendly_fire_damage'] == 150


class TestAggregateExtras:
    def test_aggregate_folds_extras(self, client):
        match = build_advanced_match()
        row1 = client.build_match_stats_row(match, 'A1')
        row2 = client.build_match_stats_row(match, 'A1')
        row2['extra'] = dict(row2['extra'])
        row2['extra']['fastest_kill_ms'] = 3000
        row2['extra']['longest_kill_distance'] = 2000
        row2['extra']['most_expensive_death'] = 3900

        stats = client.aggregate_match_rows([row1, row2])

        assert stats['plants'] == 2
        assert stats['defuses'] == 2
        assert stats['ninja_defuses'] == 2
        assert stats['money_spent'] == 2 * 5300
        assert stats['friendly_fire_damage'] == 300
        assert stats['afk_rounds'] == 4
        assert stats['ability_casts'] == 38
        assert stats['fastest_kill_ms'] == 3000          # min of 10000 / 3000
        assert stats['longest_kill_distance'] == 4500    # max of 4500 / 2000
        assert stats['most_expensive_death'] == 5700     # max of 5700 / 3900
        assert stats['clutches_attempted']['1v2'] == 2
        assert stats['clutches_won']['1v2'] == 2

    def test_aggregate_tolerates_rows_without_extra(self, client):
        row = client.build_match_stats_row(build_advanced_match(), 'A1')
        legacy_row = {k: v for k, v in row.items() if k != 'extra'}
        stats = client.aggregate_match_rows([row, legacy_row])
        assert stats['plants'] == 1
        assert stats['total_matches'] == 2


class TestHighlightSelection:
    def test_picks_highest_scores_with_category_dedupe(self):
        candidates = []
        MatchTracker._add_candidate(candidates, 90, 'clutch:1', 'big clutch', 1)
        MatchTracker._add_candidate(candidates, 80, 'damage', 'damage A', 1)
        MatchTracker._add_candidate(candidates, 70, 'damage', 'damage B', 2)
        MatchTracker._add_candidate(candidates, 20, 'fun_fact_0', 'filler')

        selected = MatchTracker._select_highlights(candidates)

        assert selected == ['big clutch', 'damage A', 'filler']

    def test_member_cap_enforced(self):
        candidates = []
        MatchTracker._add_candidate(candidates, 90, 'a', 'one', 1)
        MatchTracker._add_candidate(candidates, 80, 'b', 'two', 1)
        MatchTracker._add_candidate(candidates, 70, 'c', 'three', 1)
        MatchTracker._add_candidate(candidates, 60, 'd', 'team-wide')

        selected = MatchTracker._select_highlights(candidates)

        assert 'three' not in selected
        assert selected == ['one', 'two', 'team-wide']


@pytest.mark.asyncio
async def test_advanced_highlights_in_recap(discord_member_factory):
    """The recap surfaces the rare plays (ninja defuse, knife kill) ranked
    above generic scoreboard filler."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    match_data = build_advanced_match()
    member1 = discord_member_factory(user_id=1, name='Alpha')
    member2 = discord_member_factory(user_id=2, name='Bravo')
    all_players = match_data['players']['all_players']
    discord_members = [
        {'member': member1, 'account': {'puuid': 'A1'}, 'player_data': all_players[0]},
        {'member': member2, 'account': {'puuid': 'A2'}, 'player_data': all_players[1]},
    ]

    stats = tracker._calculate_fun_match_stats(match_data, discord_members)
    highlights = stats['highlights']
    joined = '\n'.join(highlights)

    assert 'NINJA DEFUSE' in joined
    assert 'Alpha' in joined
    # Ninja defuse (94) and knife kill (92) outrank everything else here
    assert 'NINJA DEFUSE' in highlights[0]
    assert 'HUMILIATION' in highlights[1]


@pytest.mark.asyncio
async def test_comeback_highlight(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    rounds = [{'winning_team': 'Blue', 'player_stats': []} for _ in range(4)]
    rounds += [{'winning_team': 'Red', 'player_stats': []} for _ in range(9)]
    all_players = [
        make_player('A1', 'Red', kills=10, deaths=8),
        make_player('A2', 'Red', kills=8, deaths=9, character='Sage'),
    ]
    match_data = {
        'metadata': {'map': 'Bind', 'rounds_played': 13, 'mode': 'Competitive',
                     'game_start': 1700000000},
        'players': {'all_players': all_players},
        'teams': {'red': {'has_won': True, 'rounds_won': 9},
                  'blue': {'has_won': False, 'rounds_won': 4}},
        'rounds': rounds,
    }

    member1 = discord_member_factory(user_id=1, name='Alpha')
    member2 = discord_member_factory(user_id=2, name='Bravo')
    discord_members = [
        {'member': member1, 'account': {'puuid': 'A1'}, 'player_data': all_players[0]},
        {'member': member2, 'account': {'puuid': 'A2'}, 'player_data': all_players[1]},
    ]

    stats = tracker._calculate_fun_match_stats(match_data, discord_members)
    joined = '\n'.join(stats['highlights'])

    assert 'COMEBACK KINGS' in joined
    assert 'trailing by 4' in joined
