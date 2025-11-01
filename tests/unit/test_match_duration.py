import pytest
from unittest.mock import MagicMock, patch
import discord

from match_tracker import MatchTracker


@pytest.mark.asyncio
async def test_embed_duration_seconds_to_minutes(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    match = {
        'metadata': {
            'map': 'Ascent',
            'rounds_played': 13,
            'game_length': 90,  # seconds
            'game_start': '2024-01-01T00:00:00Z',
            'matchid': 'abc123'
        },
        'teams': {
            'red': {'has_won': True, 'rounds_won': 13},
            'blue': {'has_won': False, 'rounds_won': 8}
        }
    }

    member = discord_member_factory(user_id=1, name='Player1')
    discord_members = [
        {
            'member': member,
            'player_data': {'stats': {'kills': 1, 'deaths': 2, 'assists': 3}, 'team': 'red', 'character': 'Jett'}
        }
    ]

    with patch('match_tracker.format_time_ago', return_value='just now'), \
         patch.object(tracker, '_calculate_fun_match_stats', return_value={'highlights': [], 'top_performers': {}, 'funny_stats': {}}):
        embed = await tracker._create_match_embed(match, discord_members)

    assert '1m 30s' in embed.description


@pytest.mark.asyncio
async def test_embed_duration_hours_format(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    match = {
        'metadata': {
            'map': 'Ascent',
            'rounds_played': 13,
            'game_length': 7320,  # seconds -> 2h 2m
            'game_start': '2024-01-01T00:00:00Z',
            'matchid': 'abc123'
        },
        'teams': {
            'red': {'has_won': True, 'rounds_won': 13},
            'blue': {'has_won': False, 'rounds_won': 8}
        }
    }

    member = discord_member_factory(user_id=1, name='Player1')
    discord_members = [
        {
            'member': member,
            'player_data': {'stats': {'kills': 1, 'deaths': 2, 'assists': 3}, 'team': 'red', 'character': 'Jett'}
        }
    ]

    with patch('match_tracker.format_time_ago', return_value='just now'), \
         patch.object(tracker, '_calculate_fun_match_stats', return_value={'highlights': [], 'top_performers': {}, 'funny_stats': {}}):
        embed = await tracker._create_match_embed(match, discord_members)

    assert '2h 2m' in embed.description
