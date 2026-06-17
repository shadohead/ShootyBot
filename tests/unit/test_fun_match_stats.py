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

    assert 'ROBBERY' in highlights
    assert 'ROBBED' in highlights


@pytest.mark.asyncio
async def test_unlinked_teammates_eligible_for_highlights(discord_member_factory):
    """Highlights should cover every teammate on the stack's team, including
    unlinked randoms (by their in-game name#tag), not just shootylink-ed
    members."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    match_data = {
        'metadata': {'rounds_played': 24},
        'rounds': [],
        'players': {
            'all_players': [
                # Linked member - modest game
                {'puuid': 'p1', 'name': 'Linked', 'tag': 'NA1', 'team': 'Red',
                 'stats': {'kills': 10, 'deaths': 14, 'assists': 4,
                           'headshots': 5, 'bodyshots': 20, 'legshots': 2, 'score': 4000},
                 'damage_made': 1800, 'damage_received': 3000, 'character': 'Sage'},
                # Unlinked teammate - the actual top fragger / demon game
                {'puuid': 'p2', 'name': 'RandoCarry', 'tag': 'EU1', 'team': 'Red',
                 'stats': {'kills': 27, 'deaths': 9, 'assists': 6,
                           'headshots': 30, 'bodyshots': 20, 'legshots': 1, 'score': 8000},
                 'damage_made': 4200, 'damage_received': 2000, 'character': 'Jett'},
                # Enemy - should never be a highlight even with a huge game
                {'puuid': 'enemy1', 'name': 'Villain', 'tag': 'KR1', 'team': 'Blue',
                 'stats': {'kills': 35, 'deaths': 5, 'assists': 2,
                           'headshots': 40, 'bodyshots': 10, 'legshots': 0, 'score': 9000},
                 'damage_made': 5000, 'damage_received': 1500, 'character': 'Reyna'},
            ]
        },
    }

    member = discord_member_factory(user_id=1, name='Linked')
    discord_members = [
        {'member': member, 'account': {'puuid': 'p1'},
         'player_data': match_data['players']['all_players'][0]},
    ]

    stats = tracker._calculate_fun_match_stats(match_data, discord_members)
    highlights = '\n'.join(stats['highlights'])

    # The unlinked teammate's standout game produces highlights under their tag
    assert 'RandoCarry#EU1' in highlights
    assert 'DEMON MODE' in highlights  # 27 kills
    # The enemy is never credited despite the best scoreboard
    assert 'Villain' not in highlights
