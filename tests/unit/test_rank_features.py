"""Tests for rank/RR integration, head-to-head comparison, and session recap."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import discord

from valorant_client import ValorantClient, tier_name, rank_emoji, get_player_rank
from api_clients import APIResponse
from match_tracker import MatchTracker


# ---------------------------------------------------------------------------
# Rank helper functions
# ---------------------------------------------------------------------------

def test_tier_name_maps_known_tiers():
    assert tier_name(0) == "Unrated"
    assert tier_name(18) == "Diamond 1"
    assert tier_name(27) == "Radiant"


def test_tier_name_handles_bad_input():
    assert tier_name(None) == "Unrated"
    assert tier_name("not-a-number") == "Unrated"
    assert tier_name(999) == "Unrated"


def test_rank_emoji_by_family():
    assert rank_emoji("Diamond 1") == "💎"
    assert rank_emoji("Radiant") == "✨"
    assert rank_emoji(None) == "❔"


def test_get_player_rank_prefers_patched_string():
    assert get_player_rank({'currenttier_patched': 'Ascendant 2', 'currenttier': 22}) == "Ascendant 2"


def test_get_player_rank_falls_back_to_numeric():
    assert get_player_rank({'currenttier': 21}) == "Ascendant 1"


def test_get_player_rank_returns_none_when_absent():
    assert get_player_rank({'stats': {}}) is None


# ---------------------------------------------------------------------------
# get_mmr
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_mmr_parses_response():
    client = ValorantClient()
    mmr_data = {
        'current_data': {
            'currenttier': 18,
            'currenttierpatched': 'Diamond 1',
            'ranking_in_tier': 45,
            'mmr_change_to_last_game': 18,
            'elo': 1845,
        },
        'highest_rank': {'patched_tier': 'Diamond 2'},
    }
    client.get = AsyncMock(return_value=APIResponse(data={'data': mmr_data}, status_code=200))

    result = await client.get_mmr('user', 'tag')

    assert result['tier'] == 'Diamond 1'
    assert result['rr'] == 45
    assert result['rr_change'] == 18
    assert result['elo'] == 1845
    assert result['peak'] == 'Diamond 2'
    assert result['emoji'] == '💎'
    # base_url must be restored after the v2 swap
    assert client.base_url == "https://api.henrikdev.xyz/valorant/v1"


@pytest.mark.asyncio
async def test_get_mmr_returns_none_on_failure():
    client = ValorantClient()
    client.get = AsyncMock(return_value=APIResponse(data={}, status_code=404))
    assert await client.get_mmr('user', 'tag') is None


@pytest.mark.asyncio
async def test_get_mmr_returns_none_on_exception():
    client = ValorantClient()
    client.get = AsyncMock(side_effect=Exception("boom"))
    assert await client.get_mmr('user', 'tag') is None
    # base_url still restored even when the call blows up
    assert client.base_url == "https://api.henrikdev.xyz/valorant/v1"


# ---------------------------------------------------------------------------
# Rank shown in the match recap embed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_match_embed_shows_player_rank(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    match = {
        'metadata': {
            'map': 'Ascent', 'rounds_played': 13, 'game_length': 1800,
            'game_start': '2024-01-01T00:00:00Z', 'matchid': 'abc123',
        },
        'teams': {'red': {'has_won': True, 'rounds_won': 13},
                  'blue': {'has_won': False, 'rounds_won': 8}},
        'players': {'all_players': [
            {'puuid': 'p1', 'name': 'Tracked', 'tag': 'NA1', 'team': 'Red',
             'currenttier_patched': 'Diamond 1', 'currenttier': 18,
             'stats': {'kills': 20, 'deaths': 10, 'assists': 5}},
        ]},
    }
    member = discord_member_factory(user_id=1, name='TrackedName')
    discord_members = [{'member': member, 'account': {'puuid': 'p1'},
                        'player_data': match['players']['all_players'][0]}]

    with patch('match_tracker.format_time_ago', return_value='just now'), \
         patch.object(tracker, '_calculate_fun_match_stats',
                      return_value={'highlights': [], 'top_performers': {}, 'funny_stats': {}}), \
         patch.object(tracker, '_get_squad_rank_updates', AsyncMock(return_value=None)):
        embed = await tracker._create_match_embed(match, discord_members)

    squad_field = next(f for f in embed.fields if 'Squad' in f.name)
    assert 'Diamond 1' in squad_field.value


# ---------------------------------------------------------------------------
# _get_squad_rank_updates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_squad_rank_updates_formats_rr_change(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    member = discord_member_factory(user_id=1, name='Player1')
    discord_members = [{'member': member,
                        'account': {'puuid': 'p1', 'username': 'Player1', 'tag': 'NA1'}}]

    fake_client = MagicMock()
    fake_client.get_mmr = AsyncMock(return_value={
        'tier': 'Diamond 1', 'rr': 45, 'rr_change': 18, 'emoji': '💎', 'peak': 'Diamond 2',
    })
    with patch('match_tracker.valorant_client', fake_client):
        result = await tracker._get_squad_rank_updates(discord_members)

    assert 'Player1' in result
    assert 'Diamond 1' in result
    assert '45 RR' in result
    assert '+18' in result


@pytest.mark.asyncio
async def test_squad_rank_updates_skips_accounts_without_credentials(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    member = discord_member_factory(user_id=1, name='Player1')
    # No username/tag -> should not trigger an API call and returns None
    discord_members = [{'member': member, 'account': {'puuid': 'p1'}}]

    fake_client = MagicMock()
    fake_client.get_mmr = AsyncMock()
    with patch('match_tracker.valorant_client', fake_client):
        result = await tracker._get_squad_rank_updates(discord_members)

    assert result is None
    fake_client.get_mmr.assert_not_called()


# ---------------------------------------------------------------------------
# build_session_recap
# ---------------------------------------------------------------------------

def _make_session(start, end, duration):
    session = MagicMock()
    session.start_time = start
    session.end_time = end
    session.duration_minutes = duration
    return session


@pytest.mark.asyncio
async def test_session_recap_with_games(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    m1 = discord_member_factory(user_id=1, name='Alice')
    m2 = discord_member_factory(user_id=2, name='Bob')
    m1.bot = False
    m2.bot = False
    guild = MagicMock(spec=discord.Guild)

    match = {
        'metadata': {'matchid': 'm1', 'game_start': '2024-01-01T00:30:00Z'},
        'teams': {'red': {'has_won': True}, 'blue': {'has_won': False}},
        'players': {'all_players': [
            {'puuid': 'pa', 'team': 'Red', 'stats': {'kills': 25, 'deaths': 10, 'assists': 5}},
            {'puuid': 'pb', 'team': 'Red', 'stats': {'kills': 12, 'deaths': 15, 'assists': 8}},
        ]},
    }

    fake_client = MagicMock()
    accounts = {1: [{'username': 'Alice', 'tag': 'NA1', 'puuid': 'pa'}],
                2: [{'username': 'Bob', 'tag': 'NA1', 'puuid': 'pb'}]}
    fake_client.get_all_linked_accounts.side_effect = lambda uid: accounts.get(uid, [])
    fake_client.get_linked_account.side_effect = lambda uid: accounts.get(uid, [None])[0]
    fake_client.get_match_history = AsyncMock(return_value=[match])
    fake_client.get_mmr = AsyncMock(return_value=None)

    session = _make_session('2024-01-01T00:00:00+00:00', '2024-01-01T02:00:00+00:00', 120)

    with patch('match_tracker.valorant_client', fake_client):
        embed = await tracker.build_session_recap(guild, [m1, m2], session)

    assert embed.title == "📊 Session Recap"
    assert '1 game' in embed.description
    assert '1W-0L' in embed.description
    scoreboard = next(f for f in embed.fields if 'Scoreboard' in f.name)
    # Alice has the better KDA, so she is crowned MVP / listed first
    assert '👑' in scoreboard.value
    assert 'Alice' in scoreboard.value
    assert 'Bob' in scoreboard.value
    mvp = next(f for f in embed.fields if 'MVP' in f.name)
    assert 'Alice' in mvp.value


@pytest.mark.asyncio
async def test_session_recap_no_games(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    m1 = discord_member_factory(user_id=1, name='Alice')
    m1.bot = False
    guild = MagicMock(spec=discord.Guild)

    fake_client = MagicMock()
    fake_client.get_all_linked_accounts.return_value = []
    fake_client.get_linked_account.return_value = None
    fake_client.get_match_history = AsyncMock(return_value=[])
    fake_client.get_mmr = AsyncMock(return_value=None)

    session = _make_session('2024-01-01T00:00:00+00:00', '2024-01-01T00:45:00+00:00', 45)

    with patch('match_tracker.valorant_client', fake_client):
        embed = await tracker.build_session_recap(guild, [m1], session)

    assert embed.title == "📊 Session Recap"
    assert any('No tracked games' in f.name for f in embed.fields)


@pytest.mark.asyncio
async def test_session_recap_excludes_out_of_window_matches(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    m1 = discord_member_factory(user_id=1, name='Alice')
    m1.bot = False
    guild = MagicMock(spec=discord.Guild)

    # Match started long before the session window
    old_match = {
        'metadata': {'matchid': 'old', 'game_start': '2023-12-01T00:00:00Z'},
        'teams': {'red': {'has_won': True}, 'blue': {'has_won': False}},
        'players': {'all_players': [
            {'puuid': 'pa', 'team': 'Red', 'stats': {'kills': 25, 'deaths': 10, 'assists': 5}},
        ]},
    }
    fake_client = MagicMock()
    fake_client.get_all_linked_accounts.return_value = [{'username': 'Alice', 'tag': 'NA1', 'puuid': 'pa'}]
    fake_client.get_linked_account.return_value = {'username': 'Alice', 'tag': 'NA1', 'puuid': 'pa'}
    fake_client.get_match_history = AsyncMock(return_value=[old_match])
    fake_client.get_mmr = AsyncMock(return_value=None)

    session = _make_session('2024-01-01T00:00:00+00:00', '2024-01-01T02:00:00+00:00', 120)

    with patch('match_tracker.valorant_client', fake_client):
        embed = await tracker.build_session_recap(guild, [m1], session)

    assert any('No tracked games' in f.name for f in embed.fields)
