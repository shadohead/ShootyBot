import pytest
from unittest.mock import MagicMock
import discord

from match_tracker import MatchTracker


@pytest.mark.asyncio
async def test_multikill_highlights():
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

    member1 = MagicMock(spec=discord.Member)
    member1.display_name = 'Player1'
    member2 = MagicMock(spec=discord.Member)
    member2.display_name = 'Player2'

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
