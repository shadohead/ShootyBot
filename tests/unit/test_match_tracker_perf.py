"""Tests for the match tracker's performance behavior:

- polling only iterates already-loaded contexts (no per-channel context churn)
- adaptive poll interval driven by Discord presence
- per-member polls fan out concurrently and still dedupe shared matches
- tracker state is persisted only when it actually changed (SD-card friendly)
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import discord

from match_tracker import MatchTracker


def make_member(user_id=1, name='Player'):
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.display_name = name
    member.bot = False
    return member


def make_context(stack_users):
    context = MagicMock()
    context.bot_soloq_user_set = set(stack_users)
    context.bot_fullstack_user_set = set()
    return context


def make_tracker():
    bot = MagicMock(spec=discord.Client)
    bot.guilds = []
    return MatchTracker(bot)


class TestActiveStackIteration:
    @pytest.mark.asyncio
    async def test_poll_does_not_instantiate_contexts(self):
        """The poll must only look at contexts already in memory — never call
        get_context(), which creates a context (plus a DB read) per channel."""
        tracker = make_tracker()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 1
        guild.name = 'Guild'

        member = make_member()
        channel = MagicMock()
        channel.id = 123
        guild.get_channel.return_value = channel

        mock_cm = MagicMock()
        mock_cm.contexts = {123: make_context([member])}

        tracker._check_recent_matches = AsyncMock()

        with patch('match_tracker.context_manager', mock_cm), \
                patch('match_tracker.valorant_client') as mock_client:
            mock_client.get_all_linked_accounts.return_value = [{'puuid': 'p1'}]
            mock_client.is_playing_valorant.return_value = False

            await tracker._check_server_matches(guild)

            mock_cm.get_context.assert_not_called()
            tracker._check_recent_matches.assert_awaited_once_with(guild, [member])

    @pytest.mark.asyncio
    async def test_contexts_from_other_guilds_are_skipped(self):
        tracker = make_tracker()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 1
        guild.name = 'Guild'
        guild.get_channel.return_value = None  # channel not in this guild

        mock_cm = MagicMock()
        mock_cm.contexts = {456: make_context([make_member()])}

        tracker._check_recent_matches = AsyncMock()

        with patch('match_tracker.context_manager', mock_cm), \
                patch('match_tracker.valorant_client') as mock_client:
            mock_client.get_all_linked_accounts.return_value = [{'puuid': 'p1'}]
            mock_client.is_playing_valorant.return_value = False

            await tracker._check_server_matches(guild)

            tracker._check_recent_matches.assert_not_awaited()


class TestAdaptivePollInterval:
    def test_interval_selection(self):
        tracker = make_tracker()
        tracker._any_tracked_playing = False
        assert tracker._current_check_interval() == MatchTracker.CHECK_INTERVAL_SECONDS
        tracker._any_tracked_playing = True
        assert tracker._current_check_interval() == MatchTracker.FAST_CHECK_INTERVAL_SECONDS
        assert (MatchTracker.FAST_CHECK_INTERVAL_SECONDS
                < MatchTracker.CHECK_INTERVAL_SECONDS)

    @pytest.mark.asyncio
    async def test_presence_sets_fast_polling_flag(self):
        tracker = make_tracker()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 1
        guild.name = 'Guild'

        member = make_member()
        channel = MagicMock()
        channel.id = 123
        guild.get_channel.return_value = channel

        mock_cm = MagicMock()
        mock_cm.contexts = {123: make_context([member])}

        tracker._check_recent_matches = AsyncMock()

        with patch('match_tracker.context_manager', mock_cm), \
                patch('match_tracker.valorant_client') as mock_client:
            mock_client.get_all_linked_accounts.return_value = [{'puuid': 'p1'}]

            mock_client.is_playing_valorant.return_value = True
            tracker._any_tracked_playing = False
            await tracker._check_server_matches(guild)
            assert tracker._any_tracked_playing is True

            mock_client.is_playing_valorant.return_value = False
            tracker._any_tracked_playing = False
            await tracker._check_server_matches(guild)
            assert tracker._any_tracked_playing is False


class TestConcurrentPolling:
    @pytest.mark.asyncio
    async def test_shared_match_still_processed_once(self):
        """Two stack members finishing the same game must produce exactly one
        detail fetch and one announcement, even with concurrent polls."""
        tracker = make_tracker()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 1

        m1 = make_member(1, 'One')
        m2 = make_member(2, 'Two')
        match = {'metadata': {'matchid': 'shared', 'game_length': 2400},
                 'players': {'all_players': []}}

        with patch('match_tracker.valorant_client') as mock_client:
            mock_client.get_linked_account.side_effect = lambda uid: {
                'username': f'U{uid}', 'tag': 'TAG', 'puuid': f'p{uid}'}
            mock_client.get_recent_competitive_updates = AsyncMock(return_value=[
                {'match_id': 'shared', 'started_at': datetime.now(timezone.utc),
                 'rr_change': 10}
            ])
            mock_client.get_match_details = AsyncMock(return_value=match)
            mock_client.record_match_stats_for_players = MagicMock(return_value=2)

            discord_members = [
                {'member': m1, 'account': {'puuid': 'p1'}, 'player_data': {}},
                {'member': m2, 'account': {'puuid': 'p2'}, 'player_data': {}},
            ]
            tracker._find_discord_members_in_match = AsyncMock(return_value=discord_members)
            tracker._send_match_results = AsyncMock()
            tracker._update_stack_activity = AsyncMock()

            await tracker._check_recent_matches(guild, [m1, m2])

            mock_client.get_match_details.assert_awaited_once_with('shared')
            tracker._send_match_results.assert_awaited_once()
            # Both members now know about the match id, and state is dirty so
            # it gets persisted this cycle
            assert tracker.tracked_members[m1.id]['last_match_id'] == 'shared'
            assert tracker.tracked_members[m2.id]['last_match_id'] == 'shared'
            assert tracker._state_dirty is True

    @pytest.mark.asyncio
    async def test_poll_bypasses_response_cache(self):
        """The tracker's poll must ask for fresh data — a cached mmr-history
        response would only delay detection of a finished game."""
        tracker = make_tracker()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 1
        member = make_member()

        with patch('match_tracker.valorant_client') as mock_client:
            mock_client.get_linked_account.return_value = {
                'username': 'U', 'tag': 'TAG', 'puuid': 'p1'}
            mock_client.get_recent_competitive_updates = AsyncMock(return_value=[])

            await tracker._check_recent_matches(guild, [member])

            kwargs = mock_client.get_recent_competitive_updates.await_args.kwargs
            assert kwargs.get('force_refresh') is True

    @pytest.mark.asyncio
    async def test_one_failing_member_does_not_block_others(self):
        tracker = make_tracker()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 1

        m1 = make_member(1, 'One')
        m2 = make_member(2, 'Two')
        match = {'metadata': {'matchid': 'new', 'game_length': 2400},
                 'players': {'all_players': []}}

        with patch('match_tracker.valorant_client') as mock_client:
            mock_client.get_linked_account.side_effect = lambda uid: {
                'username': f'U{uid}', 'tag': 'TAG', 'puuid': f'p{uid}'}

            async def updates_for(username, tag, **kwargs):
                if username == 'U1':
                    raise RuntimeError('API blew up')
                return [{'match_id': 'new',
                         'started_at': datetime.now(timezone.utc), 'rr_change': 5}]

            mock_client.get_recent_competitive_updates = AsyncMock(side_effect=updates_for)
            mock_client.get_match_details = AsyncMock(return_value=match)
            mock_client.record_match_stats_for_players = MagicMock(return_value=1)

            tracker._find_discord_members_in_match = AsyncMock(return_value=[
                {'member': m2, 'account': {'puuid': 'p2'}, 'player_data': {}},
                {'member': make_member(3), 'account': {'puuid': 'p3'}, 'player_data': {}},
            ])
            tracker._send_match_results = AsyncMock()
            tracker._update_stack_activity = AsyncMock()

            await tracker._check_recent_matches(guild, [m1, m2])

            # Member 2's new match is still detected and announced
            tracker._send_match_results.assert_awaited_once()


class TestDirtyGatedStateSaves:
    @pytest.mark.asyncio
    async def test_clean_state_writes_nothing(self):
        tracker = make_tracker()
        with patch('match_tracker.database_manager') as mock_db:
            await tracker._save_state_to_database()

            mock_db.save_match_tracker_state.assert_not_called()
            mock_db.save_stack_state.assert_not_called()
            mock_db.cleanup_old_tracker_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_dirty_state_is_saved_then_marked_clean(self):
        tracker = make_tracker()
        tracker._state_dirty = True
        tracker.stack_has_played[123] = True
        tracker.stack_last_activity[123] = datetime.now(timezone.utc)

        with patch('match_tracker.database_manager') as mock_db:
            await tracker._save_state_to_database()

            mock_db.save_stack_state.assert_called_once()
            assert tracker._state_dirty is False

            # Next cycle: nothing changed, nothing written
            await tracker._save_state_to_database()
            mock_db.save_stack_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_save_ignores_dirty_flag(self):
        tracker = make_tracker()
        tracker.stack_has_played[123] = True

        with patch('match_tracker.database_manager') as mock_db:
            await tracker._save_state_to_database(force=True)
            mock_db.save_stack_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_runs_at_most_daily(self):
        tracker = make_tracker()

        with patch('match_tracker.database_manager') as mock_db:
            tracker._state_dirty = True
            await tracker._save_state_to_database()
            assert mock_db.cleanup_old_tracker_state.call_count == 1

            # A second dirty save right after must not re-run the cleanup scan
            tracker._state_dirty = True
            await tracker._save_state_to_database()
            assert mock_db.cleanup_old_tracker_state.call_count == 1

            # ...but it runs again once a day has passed
            tracker._last_state_cleanup = (
                datetime.now(timezone.utc)
                - timedelta(hours=MatchTracker.STATE_CLEANUP_INTERVAL_HOURS + 1))
            tracker._state_dirty = True
            await tracker._save_state_to_database()
            assert mock_db.cleanup_old_tracker_state.call_count == 2
