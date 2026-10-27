"""Open sessions survive idle time, offline presence and process restarts."""
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import discord
import pytest
from freezegun import freeze_time

import context_manager as cm_module
import handlers.reaction_handler as reactions
from context_manager import ContextManager
from database import DatabaseManager
from match_tracker import MatchTracker
from tests.unit.test_party_snapshot_recovery import world


@pytest.mark.asyncio
@pytest.mark.parametrize('has_played', [False, True])
@pytest.mark.parametrize('has_users', [False, True])
async def test_idle_polling_preserves_session_and_queue(world, monkeypatch, has_played, has_users):
    w = world
    if has_users:
        w.context.add_soloq_user(w.people[1])
        w.context.bot_ready_user_set.add(w.people[1])
        w.context.set_plus_ones(w.people[1], 2)
    assert w.cm.save_context(123)
    before = w.context.party_snapshot()
    saved_session = w.db.get_session('live')
    w.bot.guilds = []
    w.bot.get_cog.return_value._end_current_session = AsyncMock(
        side_effect=lambda context: context.reset_users())
    tracker = MatchTracker(w.bot)
    tracker._state_dirty = True
    tracker.stack_has_played[123] = has_played
    tracker.stack_last_activity[123] = discord.utils.utcnow()
    monkeypatch.setattr('match_tracker.context_manager', w.cm)
    # Exercise the background loop, including its persistence step, with real
    # SQLite and no network requests or wall-clock waiting.
    monkeypatch.setattr('match_tracker.database_manager', w.db)
    tracker._state_loaded = True
    tracker._check_all_servers = AsyncMock()

    async def finish_cycle(seconds):
        tracker.stop_tracking()

    started_at = discord.utils.utcnow()
    for playing, elapsed in [(True, timedelta()), (False, timedelta()),
                             (False, timedelta(minutes=21)),
                             (False, timedelta(hours=2)), (False, timedelta(days=60))]:
        with freeze_time(started_at + elapsed), \
             patch('match_tracker.valorant_client.is_playing_valorant', return_value=playing), \
             patch('match_tracker.asyncio.sleep', side_effect=finish_cycle):
            await tracker.start_tracking()
        assert w.context.party_snapshot() == before
        assert w.db.get_session('live') == saved_session
        assert w.db.get_party_state(123)['soloq'] == ([1] if has_users else [])
        w.channel.fetch_message.assert_not_awaited()
        w.bot.get_cog.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('recent_message', [False, True])
async def test_old_open_session_survives_restart(world, monkeypatch, recent_message):
    w = world
    w.context.add_soloq_user(w.people[1])
    w.context.bot_fullstack_user_set.add(w.people[2])
    w.context.bot_ready_user_set.add(w.people[2])
    w.context.set_plus_ones(w.people[1], 2)
    assert w.cm.save_context(123)
    saved_session = w.db.get_session('live')
    with freeze_time(discord.utils.utcnow() + timedelta(days=60)):
        if recent_message:
            # A refresh can make the post recent while its session is old.
            w.message.id = discord.utils.time_snowflake(discord.utils.utcnow())
            w.context.current_st_message_id = w.message.id
            assert w.cm.save_context(123)
        # Reopen the same database through fresh managers, as on process start.
        db = DatabaseManager(w.db.db_path)
        monkeypatch.setattr(cm_module, 'database_manager', db)
        monkeypatch.setattr(reactions, 'database_manager', db)
        cm = ContextManager()
        monkeypatch.setattr(reactions, 'context_manager', cm)
        assert await reactions.restore_party_state_from_reactions(w.bot) == 1
        restored = cm.get_context(123)
        assert restored.current_session_id == 'live'
        assert restored.current_st_message_id == w.message.id
        assert restored.bot_soloq_user_set == {w.people[1]}
        assert restored.bot_fullstack_user_set == {w.people[2]}
        assert restored.bot_ready_user_set == {w.people[2]}
        assert restored.get_plus_ones(w.people[1]) == 2
        assert db.get_session('live') == saved_session
