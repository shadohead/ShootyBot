"""Updater activity detection and explicit per-session tracker resets."""
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


def make_context(stack_users, session_id='sess-1', started_hours_ago=None):
    context = MagicMock()
    context.bot_soloq_user_set = set(stack_users)
    context.bot_fullstack_user_set = set()
    context.current_session_id = session_id
    context.current_st_message_id = (
        discord.utils.time_snowflake(
            datetime.now(timezone.utc) - timedelta(hours=started_hours_ago))
        if started_hours_ago is not None else None)
    return context


def make_tracker():
    bot = MagicMock(spec=discord.Client)
    bot.guilds = []
    bot.get_channel = MagicMock()
    bot.get_cog = MagicMock()
    return MatchTracker(bot)


class TestIsStackInProgress:
    def test_empty_stack_is_not_in_progress(self):
        assert make_tracker().is_stack_in_progress(123, set()) is False

    def test_someone_in_game_is_in_progress(self):
        tracker = make_tracker()
        with patch('match_tracker.valorant_client') as mock_client:
            mock_client.is_playing_valorant.return_value = True
            assert tracker.is_stack_in_progress(123, {make_member()}) is True

    def test_recent_game_counts_between_matches(self):
        tracker = make_tracker()
        tracker.stack_last_activity[123] = datetime.now(timezone.utc) - timedelta(minutes=30)
        with patch('match_tracker.valorant_client') as mock_client:
            mock_client.is_playing_valorant.return_value = False
            assert tracker.is_stack_in_progress(123, {make_member()}) is True

    def test_queued_but_never_played_is_not_in_progress(self):
        tracker = make_tracker()
        with patch('match_tracker.valorant_client') as mock_client:
            mock_client.is_playing_valorant.return_value = False
            assert tracker.is_stack_in_progress(123, {make_member()}) is False

    def test_long_idle_after_games_is_not_in_progress(self):
        tracker = make_tracker()
        tracker.stack_last_activity[123] = datetime.now(timezone.utc) - timedelta(
            hours=MatchTracker.RESTART_ACTIVITY_WINDOW_HOURS + 1)
        with patch('match_tracker.valorant_client') as mock_client:
            mock_client.is_playing_valorant.return_value = False
            assert tracker.is_stack_in_progress(123, {make_member()}) is False


class TestStackStateDoesNotLeakAcrossSessions:
    """Regression for 2026-09-25 14:27: a new /st was auto-ended 44s after it
    was posted ("inactivity after 17:18:43") because last night's has_played /
    last_activity row for the channel survived restarts in stack_state."""

    def _db(self, tmp_path):
        from database import DatabaseManager
        return DatabaseManager(db_path=str(tmp_path / "shooty_bot.db"))

    @pytest.mark.asyncio
    async def test_explicit_reset_deletes_stack_row_from_database(self, tmp_path):
        db = self._db(tmp_path)
        tracker = make_tracker()
        member = make_member()
        context = make_context([member], started_hours_ago=5)
        tracker.stack_has_played[123] = True
        tracker.stack_last_activity[123] = datetime.now(timezone.utc) - timedelta(hours=4)
        tracker._state_dirty = True
        channel = MagicMock()
        channel.id = 123

        mock_cm = MagicMock()
        mock_cm.contexts = {123: context}
        with patch('match_tracker.database_manager', db), \
                patch('match_tracker.context_manager', mock_cm):
            await tracker._save_state_to_database()
            assert 123 in db.get_all_stack_states()

            tracker.reset_stack_tracking(channel.id)
            await tracker._save_state_to_database()

        assert 123 not in db.get_all_stack_states()

    @pytest.mark.asyncio
    async def test_leftover_row_is_not_loaded_and_new_stack_survives(self, tmp_path):
        db = self._db(tmp_path)
        # Last night's row, left behind by the old save loop
        db.save_stack_state(channel_id=123, has_played=True,
                            last_activity=datetime.now(timezone.utc) - timedelta(hours=17),
                            participant_count=0)

        tracker = make_tracker()
        mock_cm = MagicMock()
        mock_cm.contexts = {}  # restart: nothing restored for the channel
        with patch('match_tracker.database_manager', db), \
                patch('match_tracker.context_manager', mock_cm):
            await tracker._load_state_from_database()
            assert 123 not in tracker.stack_has_played
            await tracker._save_state_to_database()
        assert 123 not in db.get_all_stack_states()

        # Someone runs /st in that channel a few hours later
        context = make_context([make_member()], started_hours_ago=0)
        mock_cm.contexts = {123: context}
        with patch('match_tracker.context_manager', mock_cm), \
                patch('match_tracker.valorant_client') as mock_client:
            mock_client.is_playing_valorant.return_value = False
            await tracker._check_inactive_stacks()
        assert context.current_session_id == 'sess-1'
        assert context.bot_soloq_user_set

    @pytest.mark.asyncio
    async def test_row_of_restored_live_stack_is_kept(self, tmp_path):
        """A stack rebuilt from reactions after a mid-session restart keeps its
        activity for match tracking and the updater restart guard."""
        db = self._db(tmp_path)
        last = datetime.now(timezone.utc) - timedelta(minutes=20)
        db.save_stack_state(channel_id=123, has_played=True, last_activity=last,
                            participant_count=3)

        tracker = make_tracker()
        mock_cm = MagicMock()
        mock_cm.contexts = {123: make_context([make_member()], started_hours_ago=1)}
        with patch('match_tracker.database_manager', db), \
                patch('match_tracker.context_manager', mock_cm):
            await tracker._load_state_from_database()

        assert tracker.stack_has_played[123] is True
        assert tracker.stack_last_activity[123] is not None

    def test_reset_stack_tracking_clears_everything(self):
        tracker = make_tracker()
        now = datetime.now(timezone.utc)
        tracker.stack_has_played[123] = True
        tracker.stack_last_activity[123] = now

        tracker.reset_stack_tracking(123)

        assert 123 not in tracker.stack_has_played
        assert 123 not in tracker.stack_last_activity
        assert 123 in tracker._stack_states_to_delete
        assert tracker._state_dirty is True
