"""Tests for rank/RR integration, head-to-head comparison, and session recap."""

import asyncio
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

def _rank_match():
    return {
        'metadata': {
            'map': 'Ascent', 'rounds_played': 13, 'game_length': 1800,
            'game_start': '2024-01-01T00:00:00Z', 'matchid': 'abc123',
        },
        'teams': {'red': {'has_won': True, 'rounds_won': 13},
                  'blue': {'has_won': False, 'rounds_won': 8}},
        'players': {'all_players': [
            {'puuid': 'p1', 'name': 'Tracked', 'tag': 'NA1', 'team': 'Red',
             'currenttier_patched': 'Platinum 3', 'currenttier': 17,
             'stats': {'kills': 20, 'deaths': 10, 'assists': 5}},
        ]},
    }


@pytest.mark.asyncio
async def test_match_embed_shows_player_rank(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    match = _rank_match()
    member = discord_member_factory(user_id=1, name='TrackedName')
    discord_members = [{'member': member, 'account': {'puuid': 'p1'},
                        'player_data': match['players']['all_players'][0]}]

    with patch('match_tracker.format_time_ago', return_value='just now'), \
         patch.object(tracker, '_calculate_fun_match_stats',
                      return_value={'highlights': [], 'top_performers': {}, 'funny_stats': {}}):
        embed = await tracker._create_match_embed(match, discord_members, rank_ups={})

    squad_field = next(f for f in embed.fields if 'Squad' in f.name)
    assert 'Platinum 3' in squad_field.value
    # No rank-up marker when the member didn't get promoted
    assert 'Rank Up!' not in squad_field.value


@pytest.mark.asyncio
async def test_match_embed_shows_inline_rank_up_with_new_tier(discord_member_factory):
    """A promoted member is flagged inline with the rank they landed on (match
    data only knows the pre-game rank)."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    match = _rank_match()
    member = discord_member_factory(user_id=1, name='TrackedName')
    discord_members = [{'member': member, 'account': {'puuid': 'p1'},
                        'player_data': match['players']['all_players'][0]}]

    with patch('match_tracker.format_time_ago', return_value='just now'), \
         patch.object(tracker, '_calculate_fun_match_stats',
                      return_value={'highlights': [], 'top_performers': {}, 'funny_stats': {}}):
        embed = await tracker._create_match_embed(
            match, discord_members, rank_ups={1: 'Diamond 1'})

    squad_field = next(f for f in embed.fields if 'Squad' in f.name)
    assert '💎 Diamond 1 ⬆️ **Rank Up!**' in squad_field.value
    assert 'Platinum 3' not in squad_field.value
    # The promotion is inline, not a separate field
    assert not any('Rank Up' in f.name for f in embed.fields)


# ---------------------------------------------------------------------------
# Rank-up detection (only this match's own mmr-history row is trusted)
#
# Rows below are real Henrik v1 mmr-history data from 2026-09-25 (most recent
# first), normalized the way get_recent_competitive_updates returns them.
# ---------------------------------------------------------------------------

def _row(match_id, tier, rr, change):
    from valorant_client import tier_name as _tier_name
    return {'match_id': match_id, 'started_at': None, 'rr': rr, 'rr_change': change,
            'tier': tier, 'tier_name': _tier_name(tier)}


# Seleção: Platinum 3 (88 RR) -> Diamond 1 (10 RR) on a +22 win
SELECAO_HISTORY = [
    _row('a1bfd35f', 18, 10, 22),
    _row('5fba633e', 17, 88, 22),
    _row('b115447d', 17, 66, -15),
]
# spooky meme slam: promoted G3 -> P1 on 9d688a97, then a normal +33 win
SPOOKY_HISTORY = [
    _row('a1bfd35f', 15, 66, 21),
    _row('5fba633e', 15, 45, 33),
    _row('9d688a97', 15, 12, 25),
    _row('ac86b4d7', 14, 87, -13),
]


def test_promotion_detected_from_tier_change():
    assert MatchTracker._rank_up_from_history(SELECAO_HISTORY, 'a1bfd35f') == (True, 'Diamond 1')
    assert MatchTracker._rank_up_from_history(SPOOKY_HISTORY, '9d688a97') == (True, 'Platinum 1')


def test_ordinary_win_is_not_a_promotion():
    assert MatchTracker._rank_up_from_history(SELECAO_HISTORY, '5fba633e') == (False, 'Platinum 3')
    assert MatchTracker._rank_up_from_history(SPOOKY_HISTORY, '5fba633e') == (False, 'Platinum 1')


def test_missing_match_row_is_unknown_not_a_promotion():
    """Regression: the recap for 5fba633e posted before Henrik had spooky's
    row for it. His latest row was the previous game's promotion, which the old
    fallback re-reported as a rank up for this game."""
    history_before_row_landed = SPOOKY_HISTORY[2:]
    assert MatchTracker._rank_up_from_history(history_before_row_landed, '5fba633e') is None


def test_rr_loss_is_never_a_promotion():
    assert MatchTracker._is_promotion(_row('m', 18, 5, -16), _row('p', 17, 21, 10)) is False


def test_leaving_placements_is_not_a_promotion():
    assert MatchTracker._is_promotion(_row('m', 15, 10, 20), _row('p', 0, 0, 0)) is False


def test_rr_arithmetic_fallback_when_tiers_unknown():
    promoted = {'match_id': 'm', 'rr': 5, 'rr_change': 18}
    not_promoted = {'match_id': 'm', 'rr': 45, 'rr_change': 18}
    assert MatchTracker._is_promotion(promoted, None) is True
    assert MatchTracker._is_promotion(not_promoted, None) is False


@pytest.mark.asyncio
async def test_check_rank_ups_splits_promoted_and_pending(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    selecao = discord_member_factory(user_id=1, name='Ming')
    spooky = discord_member_factory(user_id=2, name='dabid')
    squad = [
        {'member': selecao, 'account': {'puuid': 'p-sel', 'username': 'Seleção', 'tag': 'NA1'}},
        {'member': spooky, 'account': {'puuid': 'p-spk', 'username': 'spooky meme slam', 'tag': 'kewk'}},
    ]
    histories = {'p-sel': SELECAO_HISTORY, 'p-spk': SPOOKY_HISTORY[2:]}

    fake_client = MagicMock()
    fake_client.get_recent_competitive_updates = AsyncMock(
        side_effect=lambda u, t, puuid=None, force_refresh=False: histories[puuid])
    fake_client.get_mmr = AsyncMock()
    with patch('match_tracker.valorant_client', fake_client):
        rank_ups, pending = await tracker._check_rank_ups(squad, 'a1bfd35f')

    assert rank_ups == {1: 'Diamond 1'}
    assert [dm['member'].id for dm in pending] == [2]
    # Current-MMR snapshots can describe an earlier game - never consulted
    fake_client.get_mmr.assert_not_called()


@pytest.mark.asyncio
async def test_check_rank_ups_covers_unlinked_and_skips_unidentifiable(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    unlinked = discord_member_factory(user_id='p-sel', name='Seleção#NA1')
    anonymous = discord_member_factory(user_id=3, name='Nobody')
    squad = [
        {'member': unlinked, 'account': {'puuid': 'p-sel'}},  # puuid only
        {'member': anonymous, 'account': {}},
    ]

    fake_client = MagicMock()
    fake_client.get_recent_competitive_updates = AsyncMock(return_value=SELECAO_HISTORY)
    with patch('match_tracker.valorant_client', fake_client):
        rank_ups, pending = await tracker._check_rank_ups(squad, 'a1bfd35f')

    assert rank_ups == {'p-sel': 'Diamond 1'}
    assert pending == []
    fake_client.get_recent_competitive_updates.assert_awaited_once_with(
        None, None, puuid='p-sel', force_refresh=True)


@pytest.mark.asyncio
async def test_check_rank_ups_failed_fetch_is_pending(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    member = discord_member_factory(user_id=1, name='Ming')
    squad = [{'member': member, 'account': {'puuid': 'p1'}}]

    fake_client = MagicMock()
    fake_client.get_recent_competitive_updates = AsyncMock(return_value=None)
    with patch('match_tracker.valorant_client', fake_client):
        rank_ups, pending = await tracker._check_rank_ups(squad, 'a1bfd35f')

    assert rank_ups == {}
    assert pending == squad


@pytest.mark.asyncio
async def test_follow_up_edits_recap_when_late_row_shows_rank_up(discord_member_factory):
    """A member whose row lands after the recap posted gets the marker added
    by editing only the squad field of the posted message."""
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    tracker.RANK_UP_RETRY_INTERVAL_SECONDS = 0
    match = _rank_match()
    member = discord_member_factory(user_id=1, name='Ming')
    discord_members = [{'member': member, 'account': {'puuid': 'p1'},
                        'player_data': match['players']['all_players'][0]}]

    embed = discord.Embed(title="🎯 Match Results")
    name, value = tracker._build_squad_field(match, discord_members, {})
    embed.add_field(name=name, value=value, inline=False)
    embed.add_field(name="🎆 Match Highlights", value="untouched", inline=False)
    message = MagicMock()
    message.embeds = [embed]
    message.edit = AsyncMock()

    fake_client = MagicMock()
    # First retry: row still missing; second retry: promotion row is there
    fake_client.get_recent_competitive_updates = AsyncMock(
        side_effect=[SELECAO_HISTORY[1:], SELECAO_HISTORY])
    with patch('match_tracker.valorant_client', fake_client):
        await tracker._follow_up_rank_ups(
            [message], match, discord_members, 'a1bfd35f', {}, discord_members)

    assert fake_client.get_recent_competitive_updates.await_count == 2
    message.edit.assert_awaited_once()
    edited = message.edit.await_args.kwargs['embed']
    assert 'Diamond 1 ⬆️ **Rank Up!**' in edited.fields[0].value
    assert edited.fields[1].value == "untouched"


@pytest.mark.asyncio
async def test_follow_up_gives_up_without_editing(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    tracker.RANK_UP_RETRY_INTERVAL_SECONDS = 0
    tracker.RANK_UP_RETRY_ATTEMPTS = 3
    match = _rank_match()
    member = discord_member_factory(user_id=1, name='Ming')
    discord_members = [{'member': member, 'account': {'puuid': 'p1'},
                        'player_data': match['players']['all_players'][0]}]
    message = MagicMock()
    message.edit = AsyncMock()

    fake_client = MagicMock()
    fake_client.get_recent_competitive_updates = AsyncMock(return_value=SELECAO_HISTORY[1:])
    with patch('match_tracker.valorant_client', fake_client):
        await tracker._follow_up_rank_ups(
            [message], match, discord_members, 'a1bfd35f', {}, discord_members)

    assert fake_client.get_recent_competitive_updates.await_count == 3
    message.edit.assert_not_awaited()


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

@pytest.mark.asyncio
async def test_send_match_results_schedules_follow_up_only_when_pending(discord_member_factory):
    bot = MagicMock(spec=discord.Client)
    tracker = MatchTracker(bot)
    match = _rank_match()
    member = discord_member_factory(user_id=1, name='Ming')
    discord_members = [{'member': member, 'account': {'puuid': 'p1'},
                        'player_data': match['players']['all_players'][0]}]
    channel = MagicMock()
    channel.name = 'shooty'
    channel.send = AsyncMock(return_value=MagicMock())
    guild = MagicMock()
    guild.text_channels = [channel]

    for pending, expect_follow_up in (([], False), (discord_members, True)):
        follow_up = AsyncMock()
        with patch.object(tracker, '_check_rank_ups', AsyncMock(return_value=({}, pending))), \
             patch.object(tracker, '_create_match_embed', AsyncMock(return_value=discord.Embed())), \
             patch.object(tracker, '_follow_up_rank_ups', follow_up), \
             patch.object(MatchTracker, '_iter_active_stacks', return_value=iter(())), \
             patch('match_tracker.recap_view', return_value=None):
            await tracker._send_match_results(guild, match, discord_members)
            await asyncio.gather(*tracker._background_tasks)

        assert follow_up.await_count == (1 if expect_follow_up else 0)
