"""Tests for automatic session ending — /stend is rarely used in practice, so
the tracker must close sessions (and post the recap) on its own:

- presence-based fast path: end once everyone closed Valorant for a grace period
- the presence path only arms after presence has actually shown someone in-game
- the 1.5h inactivity timer remains as the fallback
- auto-end posts the session recap to the stack channel
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


def make_context(stack_users, session_id='sess-1'):
    context = MagicMock()
    context.bot_soloq_user_set = set(stack_users)
    context.bot_fullstack_user_set = set()
    context.current_session_id = session_id
    return context


def make_tracker():
    bot = MagicMock(spec=discord.Client)
    bot.guilds = []
    bot.get_channel = MagicMock()
    bot.get_cog = MagicMock()
    return MatchTracker(bot)


class TestPresenceBasedAutoEnd:
    @pytest.mark.asyncio
    async def test_ends_after_everyone_offline_for_grace_period(self):
        tracker = make_tracker()
        member = make_member()
        context = make_context([member])
        channel = MagicMock()
        channel.id = 123
        tracker.bot.get_channel.return_value = channel

        tracker.stack_has_played[123] = True
        tracker._auto_end_inactive_stack = AsyncMock()

        mock_cm = MagicMock()
        mock_cm.contexts = {123: context}

        with patch('match_tracker.context_manager', mock_cm), \
                patch('match_tracker.valorant_client') as mock_client:
            # Cycle 1: someone is in-game — presence path arms, no end
            mock_client.is_playing_valorant.return_value = True
            await tracker._check_inactive_stacks()
            assert tracker.stack_seen_playing.get(123) is True
            tracker._auto_end_inactive_stack.assert_not_awaited()

            # Cycle 2: everyone closed Valorant — grace period starts, no end yet
            mock_client.is_playing_valorant.return_value = False
            await tracker._check_inactive_stacks()
            assert 123 in tracker.stack_offline_since
            tracker._auto_end_inactive_stack.assert_not_awaited()

            # Cycle 3: grace period elapsed — session ends
            tracker.stack_offline_since[123] = (
                datetime.now(timezone.utc)
                - timedelta(minutes=MatchTracker.STACK_OFFLINE_END_MINUTES + 1))
            await tracker._check_inactive_stacks()
            tracker._auto_end_inactive_stack.assert_awaited_once()
            assert tracker._auto_end_inactive_stack.await_args.kwargs['reason'] == 'everyone offline'

    @pytest.mark.asyncio
    async def test_coming_back_online_resets_the_grace_period(self):
        tracker = make_tracker()
        member = make_member()
        context = make_context([member])
        tracker.stack_has_played[123] = True
        tracker.stack_seen_playing[123] = True
        tracker.stack_offline_since[123] = (
            datetime.now(timezone.utc) - timedelta(minutes=15))
        tracker._auto_end_inactive_stack = AsyncMock()

        mock_cm = MagicMock()
        mock_cm.contexts = {123: context}

        with patch('match_tracker.context_manager', mock_cm), \
                patch('match_tracker.valorant_client') as mock_client:
            # A member relaunched the game — the offline clock must reset
            mock_client.is_playing_valorant.return_value = True
            await tracker._check_inactive_stacks()

            assert 123 not in tracker.stack_offline_since
            tracker._auto_end_inactive_stack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_never_arms_without_seeing_presence(self):
        """Hidden/broken presence must not end sessions early — the stack just
        falls back to the long inactivity timer."""
        tracker = make_tracker()
        member = make_member()
        context = make_context([member])
        tracker.stack_has_played[123] = True
        tracker._auto_end_inactive_stack = AsyncMock()

        mock_cm = MagicMock()
        mock_cm.contexts = {123: context}

        with patch('match_tracker.context_manager', mock_cm), \
                patch('match_tracker.valorant_client') as mock_client:
            mock_client.is_playing_valorant.return_value = False
            await tracker._check_inactive_stacks()
            await tracker._check_inactive_stacks()

            assert 123 not in tracker.stack_offline_since
            tracker._auto_end_inactive_stack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inactivity_timer_still_fires_as_fallback(self):
        tracker = make_tracker()
        member = make_member()
        context = make_context([member])
        channel = MagicMock()
        channel.id = 123
        tracker.bot.get_channel.return_value = channel

        tracker.stack_has_played[123] = True
        tracker.stack_last_activity[123] = (
            datetime.now(timezone.utc)
            - timedelta(hours=MatchTracker.STACK_INACTIVITY_HOURS + 0.1))
        tracker._auto_end_inactive_stack = AsyncMock()

        mock_cm = MagicMock()
        mock_cm.contexts = {123: context}

        with patch('match_tracker.context_manager', mock_cm), \
                patch('match_tracker.valorant_client') as mock_client:
            mock_client.is_playing_valorant.return_value = False
            await tracker._check_inactive_stacks()

            tracker._auto_end_inactive_stack.assert_awaited_once()
            assert tracker._auto_end_inactive_stack.await_args.kwargs['reason'] == 'inactivity'


class TestAutoEndPostsRecap:
    @pytest.mark.asyncio
    async def test_auto_end_ends_session_and_posts_recap(self):
        tracker = make_tracker()
        member = make_member()
        context = make_context([member], session_id='sess-1')
        channel = MagicMock()
        channel.id = 123
        channel.guild = MagicMock()
        channel.send = AsyncMock()

        session_cog = MagicMock()
        session_cog._end_current_session = AsyncMock()
        tracker.bot.get_cog.return_value = session_cog

        recap_embed = MagicMock(spec=discord.Embed)
        tracker.build_session_recap = AsyncMock(return_value=recap_embed)

        fake_session = MagicMock()
        mock_dm = MagicMock()
        mock_dm.sessions.get.return_value = fake_session

        with patch('data_manager.data_manager', mock_dm):
            await tracker._auto_end_inactive_stack(
                channel, context, timedelta(minutes=25), reason='everyone offline')

        # Session ended through the cog (records stats), recap posted with the
        # participants captured before the stack was reset
        session_cog._end_current_session.assert_awaited_once_with(context)
        tracker.build_session_recap.assert_awaited_once()
        assert tracker.build_session_recap.await_args.args[1] == [member]
        assert tracker.build_session_recap.await_args.args[2] is fake_session
        channel.send.assert_awaited_once()
        assert channel.send.await_args.kwargs['embed'] is recap_embed

    @pytest.mark.asyncio
    async def test_recap_failure_does_not_break_auto_end(self):
        tracker = make_tracker()
        member = make_member()
        context = make_context([member])
        channel = MagicMock()
        channel.id = 123
        channel.guild = MagicMock()
        channel.send = AsyncMock()

        session_cog = MagicMock()
        session_cog._end_current_session = AsyncMock()
        tracker.bot.get_cog.return_value = session_cog

        tracker.build_session_recap = AsyncMock(side_effect=RuntimeError('API down'))
        tracker.stack_has_played[123] = True

        fake_session = MagicMock()
        mock_dm = MagicMock()
        mock_dm.sessions.get.return_value = fake_session

        with patch('data_manager.data_manager', mock_dm):
            # Must not raise; stack cleanup still happens
            await tracker._auto_end_inactive_stack(channel, context, timedelta(hours=2))

        session_cog._end_current_session.assert_awaited_once()
        assert 123 not in tracker.stack_has_played

    @pytest.mark.asyncio
    async def test_no_participants_means_no_recap(self):
        tracker = make_tracker()
        channel = MagicMock()
        channel.id = 123
        channel.send = AsyncMock()

        await tracker._send_auto_end_recap(channel, 'sess-1', [])

        channel.send.assert_not_awaited()
