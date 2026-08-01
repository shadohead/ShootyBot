"""Tests for rank/RR integration, head-to-head comparison, and session recap."""

import pytest
from datetime import datetime, timezone
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
    # versioned endpoints share one immutable base URL
    assert client.base_url == "https://api.henrikdev.xyz/valorant"


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
    # base URL is never mutated, even when the call blows up
    assert client.base_url == "https://api.henrikdev.xyz/valorant"


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
         patch.object(tracker, '_get_ranked_up_member_ids', AsyncMock(return_value=set())):
        embed = await tracker._create_match_embed(match, discord_members)

    squad_field = next(f for f in embed.fields if 'Squad' in f.name)
    assert 'Diamond 1' in squad_field.value
    # No rank-up marker when the member didn't get promoted
    assert 'Rank Up!' not in squad_field.value


@pytest.mark.asyncio
async def test_match_embed_shows_inline_rank_up(discord_member_factory):
    """A promoted member is flagged inline in the squad list (no separate field)."""
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
         patch.object(tracker, '_get_ranked_up_member_ids', AsyncMock(return_value={1})):
        embed = await tracker._create_match_embed(match, discord_members)

    squad_field = next(f for f in embed.fields if 'Squad' in f.name)
    assert 'Rank Up!' in squad_field.value
    # The promotion is inline, not a separate field
    assert not any('Rank Up' in f.name for f in embed.fields)


# ---------------------------------------------------------------------------
# _get_ranked_up_member_ids (inline marker only on a full-tier promotion)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ranked_up_detected_from_mmr_history_for_match(discord_member_factory):
    """Use the per-match mmr-history row so promotions aren't missed by stale MMR cache."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    member = discord_member_factory(user_id=1, name='Player1')
    discord_members = [{'member': member,
                        'account': {'puuid': 'p1', 'username': 'Player1', 'tag': 'NA1'}}]

    fake_client = MagicMock()
    fake_client.get_recent_competitive_updates = AsyncMock(return_value=[
        {'match_id': 'game-123', 'rr': 5, 'rr_change': 18, 'started_at': None},
    ])
    fake_client.get_mmr = AsyncMock()
    with patch('match_tracker.valorant_client', fake_client):
        result = await tracker._get_ranked_up_member_ids(
            discord_members, match_id='game-123'
        )

    assert result == {1}
    fake_client.get_mmr.assert_not_called()


@pytest.mark.asyncio
async def test_ranked_up_detected_on_promotion(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    member = discord_member_factory(user_id=1, name='Player1')
    discord_members = [{'member': member,
                        'account': {'puuid': 'p1', 'username': 'Player1', 'tag': 'NA1'}}]

    # rr=5, change=+18 -> pre-game RR-in-tier was -13 -> crossed a tier boundary
    fake_client = MagicMock()
    fake_client.get_mmr = AsyncMock(return_value={
        'tier': 'Diamond 1', 'rr': 5, 'rr_change': 18, 'emoji': '💎', 'peak': 'Diamond 1',
    })
    with patch('match_tracker.valorant_client', fake_client):
        result = await tracker._get_ranked_up_member_ids(discord_members)

    assert result == {1}


@pytest.mark.asyncio
async def test_ranked_up_empty_without_promotion(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    member = discord_member_factory(user_id=1, name='Player1')
    discord_members = [{'member': member,
                        'account': {'puuid': 'p1', 'username': 'Player1', 'tag': 'NA1'}}]

    # rr=45, change=+18 -> pre-game RR was 27, no boundary crossed
    fake_client = MagicMock()
    fake_client.get_mmr = AsyncMock(return_value={
        'tier': 'Diamond 1', 'rr': 45, 'rr_change': 18, 'emoji': '💎', 'peak': 'Diamond 2',
    })
    with patch('match_tracker.valorant_client', fake_client):
        result = await tracker._get_ranked_up_member_ids(discord_members)

    assert result == set()


@pytest.mark.asyncio
async def test_ranked_up_empty_on_rr_loss(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    member = discord_member_factory(user_id=1, name='Player1')
    discord_members = [{'member': member,
                        'account': {'puuid': 'p1', 'username': 'Player1', 'tag': 'NA1'}}]

    # Negative RR change is never a rank up, even at low RR
    fake_client = MagicMock()
    fake_client.get_mmr = AsyncMock(return_value={
        'tier': 'Diamond 1', 'rr': 5, 'rr_change': -16, 'emoji': '💎', 'peak': 'Diamond 2',
    })
    with patch('match_tracker.valorant_client', fake_client):
        result = await tracker._get_ranked_up_member_ids(discord_members)

    assert result == set()


@pytest.mark.asyncio
async def test_ranked_up_skips_accounts_without_credentials(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    member = discord_member_factory(user_id=1, name='Player1')
    # No username/tag -> should not trigger an API call
    discord_members = [{'member': member, 'account': {'puuid': 'p1'}}]

    fake_client = MagicMock()
    fake_client.get_mmr = AsyncMock()
    with patch('match_tracker.valorant_client', fake_client):
        result = await tracker._get_ranked_up_member_ids(discord_members)

    assert result == set()
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
    fake_client.get_recent_competitive_updates = AsyncMock(return_value=[
        {'match_id': 'm1',
         'started_at': datetime(2024, 1, 1, 0, 30, tzinfo=timezone.utc),
         'rr_change': 20}
    ])
    fake_client.get_match_details = AsyncMock(return_value=match)
    fake_client.record_match_stats_for_players = MagicMock(return_value=2)
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
async def test_session_recap_includes_unlinked_teammates(discord_member_factory):
    """Players on the stack's team without a linked account still make the
    session scoreboard (by riot name); enemies never do."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)

    m1 = discord_member_factory(user_id=1, name='Alice')
    m1.bot = False
    guild = MagicMock(spec=discord.Guild)

    match = {
        'metadata': {'matchid': 'm1', 'game_start': '2024-01-01T00:30:00Z'},
        'teams': {'red': {'has_won': True}, 'blue': {'has_won': False}},
        'players': {'all_players': [
            {'puuid': 'pa', 'name': 'Alice', 'tag': 'NA1', 'team': 'Red',
             'stats': {'kills': 12, 'deaths': 10, 'assists': 5}},
            {'puuid': 'pu', 'name': 'UnlinkedBuddy', 'tag': '007', 'team': 'Red',
             'stats': {'kills': 25, 'deaths': 5, 'assists': 9}},
            {'puuid': 'pe', 'name': 'EnemyGuy', 'tag': 'KR1', 'team': 'Blue',
             'stats': {'kills': 30, 'deaths': 12, 'assists': 2}},
        ]},
    }

    fake_client = MagicMock()
    fake_client.get_all_linked_accounts.side_effect = \
        lambda uid: [{'username': 'Alice', 'tag': 'NA1', 'puuid': 'pa'}] if uid == 1 else []
    fake_client.get_linked_account.side_effect = \
        lambda uid: {'username': 'Alice', 'tag': 'NA1', 'puuid': 'pa'} if uid == 1 else None
    fake_client.get_recent_competitive_updates = AsyncMock(return_value=[
        {'match_id': 'm1',
         'started_at': datetime(2024, 1, 1, 0, 30, tzinfo=timezone.utc),
         'rr_change': 20}
    ])
    fake_client.get_match_details = AsyncMock(return_value=match)
    fake_client.record_match_stats_for_players = MagicMock(return_value=1)
    fake_client.get_mmr = AsyncMock(return_value=None)

    session = _make_session('2024-01-01T00:00:00+00:00', '2024-01-01T02:00:00+00:00', 120)

    with patch('match_tracker.valorant_client', fake_client):
        embed = await tracker.build_session_recap(guild, [m1], session)

    scoreboard = next(f for f in embed.fields if 'Scoreboard' in f.name)
    assert 'Alice' in scoreboard.value
    assert 'UnlinkedBuddy#007' in scoreboard.value
    assert 'EnemyGuy' not in scoreboard.value
    # The unlinked buddy has the best KDA and takes the crown/MVP
    mvp = next(f for f in embed.fields if 'MVP' in f.name)
    assert 'UnlinkedBuddy#007' in mvp.value


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
    fake_client.get_recent_competitive_updates = AsyncMock(return_value=[])
    fake_client.get_match_details = AsyncMock(return_value=None)
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

    # Match played long before the session window
    fake_client = MagicMock()
    fake_client.get_all_linked_accounts.return_value = [{'username': 'Alice', 'tag': 'NA1', 'puuid': 'pa'}]
    fake_client.get_linked_account.return_value = {'username': 'Alice', 'tag': 'NA1', 'puuid': 'pa'}
    fake_client.get_recent_competitive_updates = AsyncMock(return_value=[
        {'match_id': 'old',
         'started_at': datetime(2023, 12, 1, 0, 0, tzinfo=timezone.utc),
         'rr_change': 20}
    ])
    fake_client.get_match_details = AsyncMock()
    fake_client.get_mmr = AsyncMock(return_value=None)

    session = _make_session('2024-01-01T00:00:00+00:00', '2024-01-01T02:00:00+00:00', 120)

    with patch('match_tracker.valorant_client', fake_client):
        embed = await tracker.build_session_recap(guild, [m1], session)

    assert any('No tracked games' in f.name for f in embed.fields)
    # Out-of-window matches must not trigger a (heavy) details fetch
    fake_client.get_match_details.assert_not_called()
