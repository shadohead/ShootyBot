import pytest
from unittest.mock import MagicMock, patch
import discord

from match_tracker import MatchTracker


@pytest.mark.asyncio
async def test_untracked_teammates_shown_with_ingame_tag(discord_member_factory):
    """Untracked teammates should appear in the squad list with their in-game name#tag."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    match = {
        'metadata': {
            'map': 'Ascent',
            'rounds_played': 13,
            'game_length': 1800,
            'game_start': '2024-01-01T00:00:00Z',
            'matchid': 'abc123',
        },
        'teams': {
            'red': {'has_won': True, 'rounds_won': 13},
            'blue': {'has_won': False, 'rounds_won': 8},
        },
        'players': {
            'all_players': [
                {'puuid': 'p1', 'name': 'TrackedPlayer', 'tag': 'NA1', 'team': 'Red',
                 'stats': {'kills': 20, 'deaths': 10, 'assists': 5}},
                {'puuid': 'p2', 'name': 'RandoTeammate', 'tag': 'EU1', 'team': 'Red',
                 'stats': {'kills': 15, 'deaths': 12, 'assists': 3}},
                {'puuid': 'p3', 'name': 'SoloQueueBuddy', 'tag': '420', 'team': 'Red',
                 'stats': {'kills': 8, 'deaths': 14, 'assists': 7}},
                {'puuid': 'enemy1', 'name': 'Enemy', 'tag': 'KR1', 'team': 'Blue',
                 'stats': {'kills': 18, 'deaths': 16, 'assists': 4}},
            ],
        },
    }

    member = discord_member_factory(user_id=1, name='TrackedDisplayName')
    discord_members = [
        {
            'member': member,
            'account': {'puuid': 'p1'},
            'player_data': match['players']['all_players'][0],
        }
    ]

    with patch('match_tracker.format_time_ago', return_value='just now'), \
         patch.object(tracker, '_calculate_fun_match_stats',
                      return_value={'highlights': [], 'top_performers': {}, 'funny_stats': {}}):
        embed = await tracker._create_match_embed(match, discord_members)

    squad_field = next(f for f in embed.fields if 'Squad' in f.name)

    # Tracked member shown by Discord display name
    assert 'TrackedDisplayName' in squad_field.value
    # Untracked teammates shown by in-game name#tag
    assert 'RandoTeammate#EU1' in squad_field.value
    assert 'SoloQueueBuddy#420' in squad_field.value
    # Enemy team is NOT included
    assert 'Enemy' not in squad_field.value
    # Squad count reflects tracked + untracked teammates
    assert 'Squad (3)' in squad_field.name


@pytest.mark.asyncio
async def test_untracked_player_without_tag_falls_back_to_name(discord_member_factory):
    """If an untracked player has no tag field, display just their name."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    match = {
        'metadata': {
            'map': 'Bind',
            'rounds_played': 13,
            'game_length': 1800,
            'game_start': '2024-01-01T00:00:00Z',
            'matchid': 'xyz',
        },
        'teams': {
            'red': {'has_won': False, 'rounds_won': 8},
            'blue': {'has_won': True, 'rounds_won': 13},
        },
        'players': {
            'all_players': [
                {'puuid': 'p1', 'name': 'Tracked', 'tag': 'NA1', 'team': 'Red',
                 'stats': {'kills': 5, 'deaths': 10, 'assists': 2}},
                {'puuid': 'p2', 'name': 'NoTagPlayer', 'tag': '', 'team': 'Red',
                 'stats': {'kills': 7, 'deaths': 9, 'assists': 1}},
            ],
        },
    }

    member = discord_member_factory(user_id=1, name='Tracked')
    discord_members = [
        {
            'member': member,
            'account': {'puuid': 'p1'},
            'player_data': match['players']['all_players'][0],
        }
    ]

    with patch('match_tracker.format_time_ago', return_value='just now'), \
         patch.object(tracker, '_calculate_fun_match_stats',
                      return_value={'highlights': [], 'top_performers': {}, 'funny_stats': {}}):
        embed = await tracker._create_match_embed(match, discord_members)

    squad_field = next(f for f in embed.fields if 'Squad' in f.name)
    assert 'NoTagPlayer' in squad_field.value
    assert 'NoTagPlayer#' not in squad_field.value
