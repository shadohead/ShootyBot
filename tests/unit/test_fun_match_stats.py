import pytest
from unittest.mock import MagicMock
import discord

from match_tracker import MatchTracker


@pytest.mark.asyncio
async def test_multikill_highlights(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    match_data = {
        'rounds': [
            {
                'player_stats': [
                    {'player_puuid': 'p1', 'kill_events': [{}, {}, {}, {}, {}]},
                    {'player_puuid': 'p2', 'kill_events': []},
                ]
            },
            {
                'player_stats': [
                    {'player_puuid': 'p1', 'kill_events': [{}, {}, {}]},
                    {'player_puuid': 'p2', 'kill_events': [{}, {}, {}, {}]},
                ]
            }
        ],
        'players': {
            'all_players': [
                {
                    'puuid': 'p1',
                    'stats': {
                        'kills': 8,
                        'deaths': 2,
                        'assists': 1,
                        'headshots': 3,
                        'bodyshots': 1,
                        'legshots': 0,
                        'score': 1000,
                    },
                    'damage_made': 0,
                    'damage_received': 0,
                    'character': 'Jett'
                },
                {
                    'puuid': 'p2',
                    'stats': {
                        'kills': 5,
                        'deaths': 6,
                        'assists': 2,
                        'headshots': 1,
                        'bodyshots': 1,
                        'legshots': 0,
                        'score': 500,
                    },
                    'damage_made': 0,
                    'damage_received': 0,
                    'character': 'Sage'
                }
            ]
        }
    }

    member1 = discord_member_factory(user_id=1, name='Player1')
    member2 = discord_member_factory(user_id=2, name='Player2')

    discord_members = [
        {'member': member1, 'account': {'puuid': 'p1'}, 'player_data': match_data['players']['all_players'][0]},
        {'member': member2, 'account': {'puuid': 'p2'}, 'player_data': match_data['players']['all_players'][1]},
    ]

    stats = tracker._calculate_fun_match_stats(match_data, discord_members)
    highlights = '\n'.join(stats['highlights'])

    assert 'ACE ALERT' in highlights
    assert '1 ACE' in highlights
    assert 'MULTIKILL MASTER' in highlights
    assert '1 4K' in highlights
    assert 'likely' not in highlights
    assert 'probably' not in highlights


@pytest.mark.asyncio
async def test_swing_round_highlights(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    match_data = {
        'rounds': [
            {
                'winning_team': 'Red',
                'player_stats': [
                    {'player_puuid': 'p1', 'team': 'Red', 'economy': {'loadout_value': 1500}},
                    {'player_puuid': 'p2', 'team': 'Red', 'economy': {'loadout_value': 1500}},
                    {'player_puuid': 'p3', 'team': 'Blue', 'economy': {'loadout_value': 7000}},
                    {'player_puuid': 'p4', 'team': 'Blue', 'economy': {'loadout_value': 8000}},
                ]
            },
            {
                'winning_team': 'Blue',
                'player_stats': [
                    {'player_puuid': 'p1', 'team': 'Red', 'economy': {'loadout_value': 8000}},
                    {'player_puuid': 'p2', 'team': 'Red', 'economy': {'loadout_value': 8000}},
                    {'player_puuid': 'p3', 'team': 'Blue', 'economy': {'loadout_value': 1000}},
                    {'player_puuid': 'p4', 'team': 'Blue', 'economy': {'loadout_value': 1000}},
                ]
            }
        ],
        'players': {
            'all_players': [
                {'puuid': 'p1', 'team': 'Red', 'stats': {'kills': 0, 'deaths': 0, 'assists': 0, 'headshots': 0, 'bodyshots': 0, 'legshots': 0, 'score': 0}, 'damage_made': 0, 'damage_received': 0, 'character': 'Jett'},
                {'puuid': 'p2', 'team': 'Red', 'stats': {'kills': 0, 'deaths': 0, 'assists': 0, 'headshots': 0, 'bodyshots': 0, 'legshots': 0, 'score': 0}, 'damage_made': 0, 'damage_received': 0, 'character': 'Sage'},
                {'puuid': 'p3', 'team': 'Blue', 'stats': {'kills': 0, 'deaths': 0, 'assists': 0, 'headshots': 0, 'bodyshots': 0, 'legshots': 0, 'score': 0}, 'damage_made': 0, 'damage_received': 0, 'character': 'Fade'},
                {'puuid': 'p4', 'team': 'Blue', 'stats': {'kills': 0, 'deaths': 0, 'assists': 0, 'headshots': 0, 'bodyshots': 0, 'legshots': 0, 'score': 0}, 'damage_made': 0, 'damage_received': 0, 'character': 'Raze'},
            ]
        }
    }

    member1 = discord_member_factory(user_id=1, name='Player1')
    member2 = discord_member_factory(user_id=2, name='Player2')

    discord_members = [
        {'member': member1, 'account': {'puuid': 'p1'}, 'player_data': match_data['players']['all_players'][0]},
        {'member': member2, 'account': {'puuid': 'p2'}, 'player_data': match_data['players']['all_players'][1]},
    ]

    stats = tracker._calculate_fun_match_stats(match_data, discord_members)
    highlights = '\n'.join(stats['highlights'])

    assert 'Swing Round' in highlights
    assert 'Enemy Swing Round' in highlights
