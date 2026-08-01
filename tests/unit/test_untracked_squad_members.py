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


def _three_stack_match():
    """One tracked player and two same-team unlinked players, plus an enemy."""
    return {
        'metadata': {
            'map': 'Ascent',
            'rounds_played': 20,
            'game_length': 1800,
            'game_start': '2024-01-01T00:00:00Z',
            'matchid': 'abc123',
        },
        'teams': {
            'red': {'has_won': True, 'rounds_won': 13},
            'blue': {'has_won': False, 'rounds_won': 7},
        },
        'players': {
            'all_players': [
                {'puuid': 'p1', 'name': 'TrackedPlayer', 'tag': 'NA1', 'team': 'Red',
                 'character': 'Sage',
                 'stats': {'kills': 10, 'deaths': 12, 'assists': 5, 'headshots': 5,
                           'bodyshots': 20, 'legshots': 1, 'score': 3000},
                 'damage_made': 2000, 'damage_received': 2500},
                {'puuid': 'p2', 'name': 'UnlinkedCarry', 'tag': 'EU1', 'team': 'Red',
                 'character': 'Jett',
                 'stats': {'kills': 30, 'deaths': 8, 'assists': 2, 'headshots': 20,
                           'bodyshots': 30, 'legshots': 0, 'score': 7000},
                 'damage_made': 5000, 'damage_received': 1500},
                {'puuid': 'enemy1', 'name': 'Enemy', 'tag': 'KR1', 'team': 'Blue',
                 'character': 'Omen',
                 'stats': {'kills': 40, 'deaths': 16, 'assists': 4, 'headshots': 30,
                           'bodyshots': 10, 'legshots': 0, 'score': 9000},
                 'damage_made': 8000, 'damage_received': 3000},
            ],
        },
        'rounds': [],
    }


def _tracked_members(match, discord_member_factory):
    member = discord_member_factory(user_id=1, name='TrackedDisplayName')
    return [{
        'member': member,
        'account': {'puuid': 'p1'},
        'player_data': match['players']['all_players'][0],
    }]


def test_unlinked_teammates_helper_builds_member_shaped_entries(discord_member_factory):
    """_unlinked_teammates returns same-team unlinked players in the
    discord_members dict shape, and never enemies."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    match = _three_stack_match()
    discord_members = _tracked_members(match, discord_member_factory)

    unlinked = tracker._unlinked_teammates(match, discord_members)

    assert len(unlinked) == 1
    entry = unlinked[0]
    assert entry['member'].display_name == 'UnlinkedCarry#EU1'
    assert entry['member'].id == 'p2'
    assert entry['account']['puuid'] == 'p2'
    assert entry['player_data']['puuid'] == 'p2'


def test_unlinked_teammates_empty_without_team_info():
    """Without any linked member team data we can't tell friend from foe."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    match = _three_stack_match()

    assert tracker._unlinked_teammates(match, []) == []


def test_fun_stats_include_unlinked_teammates(discord_member_factory):
    """Highlights can feature unlinked teammates once they're in the roster."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    match = _three_stack_match()
    discord_members = _tracked_members(match, discord_member_factory)
    roster = discord_members + tracker._unlinked_teammates(match, discord_members)

    stats = tracker._calculate_fun_match_stats(match, roster)
    highlights = '\n'.join(stats['highlights'])

    # The unlinked player is the clear top fragger and should be credited
    assert 'UnlinkedCarry#EU1' in highlights
    # The enemy team never shows up in highlights
    assert 'Enemy#KR1' not in highlights


@pytest.mark.asyncio
async def test_match_embed_passes_unlinked_teammates_to_highlights(discord_member_factory):
    """_create_match_embed computes highlights over linked + unlinked players."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    match = _three_stack_match()
    discord_members = _tracked_members(match, discord_member_factory)

    with patch('match_tracker.format_time_ago', return_value='just now'), \
         patch.object(tracker, '_calculate_fun_match_stats',
                      return_value={'highlights': [], 'top_performers': {}, 'funny_stats': {}}) as fun_mock:
        embed = await tracker._create_match_embed(match, discord_members)

    roster = fun_mock.call_args.args[1]
    names = {dm['member'].display_name for dm in roster}
    assert names == {'TrackedDisplayName', 'UnlinkedCarry#EU1'}

    squad_field = next(f for f in embed.fields if 'Squad' in f.name)
    assert 'Squad (2)' in squad_field.name
    assert 'UnlinkedCarry#EU1' in squad_field.value
