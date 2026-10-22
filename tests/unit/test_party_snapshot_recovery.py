"""Restart, offline-reaction, and command regression tests using temporary SQLite."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch

import discord
import pytest

import context_manager as cm_module
import handlers.reaction_handler as reactions
from context_manager import ContextManager
from database import DatabaseManager
from config import EMOJI
from bot import ShootyBot


def player(uid):
    user = Mock(id=uid, bot=False)
    user.name = 'Player%s' % uid
    return user


def reaction(emoji, users):
    async def iterate():
        for user in users:
            yield user
    return SimpleNamespace(emoji=emoji, users=iterate)


@pytest.fixture
def world(tmp_path, monkeypatch):
    db = DatabaseManager(str(tmp_path / 'party.db'))
    monkeypatch.setattr(cm_module, 'database_manager', db)
    cm = ContextManager()
    monkeypatch.setattr(reactions, 'context_manager', cm)
    monkeypatch.setattr(reactions, 'database_manager', db)
    bot = Mock()
    bot.user = player(999)
    bot.update_status_with_queue_count = AsyncMock()
    channel = SimpleNamespace(id=123, guild=None, fetch_message=AsyncMock())
    message = SimpleNamespace(id=discord.utils.time_snowflake(discord.utils.utcnow()),
                              author=bot.user, channel=channel, reactions=[], edit=AsyncMock())
    channel.fetch_message.return_value = message
    bot.get_channel.return_value = channel
    people = {uid: player(uid) for uid in (1, 2, 3)}
    bot.fetch_user = AsyncMock(side_effect=lambda uid: people[uid])
    context = cm.get_context(123)
    context.channel = channel
    context.current_st_message_id = message.id
    context.current_session_id = 'live'
    db.create_session('live', 123, 1)
    return SimpleNamespace(db=db, cm=cm, bot=bot, channel=channel, message=message,
                           people=people, context=context)


@pytest.mark.asyncio
async def test_restart_preserves_initiator_guests_and_manual_kick(world):
    w = world
    starter, kicked, newcomer = (w.people[x] for x in (1, 2, 3))
    w.context.add_soloq_user(starter)  # /st auto-adds without a reaction
    w.context.set_plus_ones(starter, 2)
    reactions.apply_party_reaction(w.context, kicked, EMOJI['FULL_STACK'], True)
    w.context.remove_user_from_everything([kicked.name])
    assert w.cm.save_context(123)
    w.message.reactions = [reaction(EMOJI['FULL_STACK'], [kicked, newcomer])]
    w.cm.contexts.clear()  # process restart; no in-memory members remain

    assert await reactions.restore_party_state_from_reactions(w.bot) == 1
    restored = w.cm.get_context(123)
    assert restored.bot_soloq_user_set == {starter}
    assert restored.bot_fullstack_user_set == {newcomer}
    assert restored.get_plus_ones(starter) == 2
    assert restored.get_unique_user_count() == 4
    assert restored.current_session_id == 'live'
    assert w.db.get_party_state(123)['fullstack'] == [3]
    assert 'Player1+2' in w.message.edit.call_args.kwargs['content']
    assert w.message.edit.call_args.kwargs['allowed_mentions'].everyone is False


@pytest.mark.asyncio
async def test_cleared_queue_stays_empty_with_old_reactions(world):
    w = world
    reactions.apply_party_reaction(w.context, w.people[1], EMOJI['THUMBS_UP'], True)
    w.context.reset_users()  # /shootyclear, reactions intentionally left in place
    assert w.cm.save_context(123)
    w.message.reactions = [reaction(EMOJI['THUMBS_UP'], [w.people[1]])]
    w.cm.contexts.clear()
    assert await reactions.restore_party_state_from_reactions(w.bot) == 1
    assert w.cm.get_context(123).get_unique_user_count() == 0


@pytest.mark.asyncio
async def test_offline_removal_clears_guests(world):
    w = world
    reactions.apply_party_reaction(w.context, w.people[1], EMOJI['THUMBS_UP'], True)
    w.context.set_plus_ones(w.people[1], 2)
    assert w.cm.save_context(123)
    w.cm.contexts.clear()
    assert await reactions.restore_party_state_from_reactions(w.bot) == 1
    assert w.cm.get_context(123).get_unique_user_count() == 0
    assert w.cm.get_context(123).plus_ones == {}


@pytest.mark.asyncio
async def test_failed_restore_keeps_memory_and_durable_snapshot(world):
    w = world
    w.context.add_soloq_user(w.people[1])
    w.context.set_plus_ones(w.people[1], 2)
    assert w.cm.save_context(123)
    before = w.db.get_party_state(123)

    async def fail():
        yield w.people[2]
        raise discord.HTTPException(SimpleNamespace(status=503, reason='Unavailable'), 'retry')
    w.message.reactions = [SimpleNamespace(emoji='👍', users=fail)]
    assert await reactions.restore_party_state_from_reactions(w.bot) == 0
    assert w.context.bot_soloq_user_set == {w.people[1]}
    assert w.context.get_plus_ones(w.people[1]) == 2
    assert w.db.get_party_state(123) == before
    w.message.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_message_edit_still_persists_player(world):
    w = world
    w.context.add_soloq_user(w.people[1])
    w.message.edit.side_effect = discord.HTTPException(
        SimpleNamespace(status=503, reason='Unavailable'), 'retry')
    with pytest.raises(discord.HTTPException):
        await reactions.update_party_message(w.message, w.context)
    assert w.db.get_party_state(123)['soloq'] == [1]


@pytest.mark.asyncio
async def test_rapid_add_remove_serializes_message_fetch(world):
    w = world
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def fetch(mid):
        calls.append(mid)
        if len(calls) == 1:
            entered.set()
            await release.wait()
        return w.message
    w.channel.fetch_message.side_effect = fetch
    handler = reactions.ReactionHandler(w.bot)
    payload = SimpleNamespace(channel_id=123, message_id=w.message.id,
                              user_id=1, member=w.people[1], emoji='👍')
    handler._track_session_participation = AsyncMock()
    added = asyncio.create_task(handler.on_raw_reaction_add(payload))
    await asyncio.wait_for(entered.wait(), 2)
    removed = asyncio.create_task(handler.on_raw_reaction_remove(payload))
    await asyncio.sleep(0)
    assert len(calls) == 1
    release.set()
    await asyncio.gather(added, removed)
    assert w.context.get_unique_user_count() == 0
    assert w.db.get_party_state(123)['soloq'] == []
    assert 'Player1' not in w.message.edit.call_args.kwargs['content']


@pytest.mark.asyncio
async def test_new_session_during_fetch_rejects_old_reaction(world):
    w = world
    async def fetch(mid):
        w.context.current_st_message_id = mid + 1
        return w.message
    w.channel.fetch_message.side_effect = fetch
    handler = reactions.ReactionHandler(w.bot)
    payload = SimpleNamespace(channel_id=123, message_id=w.message.id,
                              user_id=1, member=w.people[1], emoji='👍')
    assert await handler._resolve_reaction(payload) is None
    assert w.context.get_unique_user_count() == 0
    w.message.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_repeated_ready_does_not_wipe_live_party_or_duplicate_tracker(world):
    w = world
    bot = ShootyBot()
    bot._connection.user = w.bot.user
    bot.change_presence = AsyncMock()
    bot.sync_commands = AsyncMock()
    bot.update_status_with_queue_count = AsyncMock()
    async def start_tracker():
        bot.match_tracker = object()
    bot.start_match_tracker = AsyncMock(side_effect=start_tracker)
    with patch('bot.restore_party_state_from_reactions', new_callable=AsyncMock) as restore, \
         patch.object(bot, 'health_check_task', Mock()), \
         patch.object(bot, 'storage_monitoring_task', Mock()):
        await bot.on_ready()
        w.context.add_soloq_user(w.people[1])
        w.context.set_plus_ones(w.people[1], 2)
        await bot.on_ready()
    restore.assert_awaited_once()
    bot.start_match_tracker.assert_awaited_once()
    assert w.context.get_unique_user_count() == 3


def test_removing_soloq_falls_back_to_existing_fullstack_reaction(world):
    w = world
    for emoji in ('5️⃣', '👍'):
        reactions.apply_party_reaction(w.context, w.people[1], emoji, True)
    w.context.set_plus_ones(w.people[1], 2)
    reactions.apply_party_reaction(w.context, w.people[1], '👍', False)
    assert w.context.bot_soloq_user_set == set()
    assert w.context.bot_fullstack_user_set == {w.people[1]}
    assert w.context.get_plus_ones(w.people[1]) == 2


def test_settings_and_snapshot_rollback_together(world):
    w = world
    assert w.cm.save_context(123)
    # Unserializable state fails after the settings UPDATE, so both must roll back.
    assert not w.db.save_channel_settings(123, current_st_message_id=999,
                                         party_state={'bad': object()})
    assert w.db.get_channel_settings(123)['current_st_message_id'] == w.message.id
    assert w.db.get_party_state(123)['message_id'] == w.message.id


@pytest.mark.asyncio
async def test_failed_recovery_retries_before_accepting_next_event(world):
    w = world
    w.context.add_soloq_user(w.people[1])
    w.context.set_plus_ones(w.people[1], 2)
    assert w.cm.save_context(123)
    w.cm.contexts.clear()
    async def fail():
        raise discord.HTTPException(SimpleNamespace(status=503, reason='Unavailable'), 'retry')
        yield
    w.message.reactions = [SimpleNamespace(emoji='👍', users=fail)]
    assert await reactions.restore_party_state_from_reactions(w.bot) == 0
    w.message.reactions = [reaction('5️⃣', [w.people[2]])]
    handler = reactions.ReactionHandler(w.bot)
    handler._track_session_participation = AsyncMock()
    payload = SimpleNamespace(channel_id=123, message_id=w.message.id,
                              user_id=2, member=w.people[2], emoji='5️⃣')
    await handler.on_raw_reaction_add(payload)
    restored = w.cm.get_context(123)
    assert restored.bot_soloq_user_set == {w.people[1]}
    assert restored.bot_fullstack_user_set == {w.people[2]}
    assert restored.get_plus_ones(w.people[1]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('operation, expected', [('kick', 0), ('clear', 0), ('resize', 1), ('guests', 3), ('restore', 1)])
async def test_queue_commands_update_existing_post_and_snapshot(world, monkeypatch, operation, expected):
    import commands.party_commands as party_module
    import commands.session_commands as session_module
    w = world
    monkeypatch.setattr(party_module, 'context_manager', w.cm)
    monkeypatch.setattr(session_module, 'context_manager', w.cm)
    w.context.add_soloq_user(w.people[1])
    ctx = SimpleNamespace(channel=w.channel, author=w.people[1], interaction=None,
                          send=AsyncMock(), reply=AsyncMock())
    party_cog = party_module.PartyCommands(w.bot)
    session_cog = session_module.SessionCommands(w.bot)
    if operation == 'kick':
        await party_cog.kick_user.callback(party_cog, ctx, 'Player1')
    elif operation == 'clear':
        await party_cog.clear_session.callback(party_cog, ctx)
    elif operation == 'resize':
        await party_cog.set_session_size.callback(party_cog, ctx, '7')
        assert '/7' in w.message.edit.call_args.kwargs['content']
    elif operation == 'guests':
        await session_cog.set_plus_ones.callback(session_cog, ctx, 2)
    else:
        w.context.backup_state()
        w.context.reset_users()
        await session_cog.restore_session.callback(session_cog, ctx)
    assert w.context.get_unique_user_count() == expected
    assert w.db.get_party_state(123)['soloq'] == ([] if expected == 0 else [1])
    assert w.context.current_st_message_id == w.message.id
    w.message.edit.assert_awaited_once()


@pytest.mark.asyncio
async def test_end_retires_message_and_cannot_revive_from_old_reactions(world, monkeypatch):
    import commands.session_commands as session_module
    w = world
    monkeypatch.setattr(session_module, 'context_manager', w.cm)
    monkeypatch.setattr(session_module, 'data_manager', Mock(sessions={}))
    w.context.add_soloq_user(w.people[1])
    cog = session_module.SessionCommands(w.bot)
    await cog._end_current_session(w.context)
    assert w.context.current_st_message_id is None
    assert w.db.get_channel_settings(123)['current_st_message_id'] is None
    handler = reactions.ReactionHandler(w.bot)
    payload = SimpleNamespace(channel_id=123, message_id=w.message.id,
                              user_id=1, member=w.people[1], emoji='👍')
    await handler.on_raw_reaction_add(payload)
    assert w.context.get_unique_user_count() == 0


@pytest.mark.asyncio
async def test_failed_new_session_send_preserves_old_party(world, monkeypatch):
    import commands.session_commands as session_module
    w = world
    monkeypatch.setattr(session_module, 'context_manager', w.cm)
    w.context.add_soloq_user(w.people[1])
    ctx = SimpleNamespace(channel=w.channel, author=w.people[1], interaction=None,
                          send=AsyncMock(side_effect=RuntimeError('unavailable')))
    cog = session_module.SessionCommands(w.bot)
    cog.send_error_embed = AsyncMock()
    await cog.start_session.callback(cog, ctx)
    assert w.context.current_session_id == 'live'
    assert w.context.current_st_message_id == w.message.id
    assert w.context.bot_soloq_user_set == {w.people[1]}


@pytest.mark.asyncio
async def test_new_session_immediately_displays_and_persists_starter(world, monkeypatch):
    import commands.session_commands as session_module
    w = world
    monkeypatch.setattr(session_module, 'context_manager', w.cm)
    manager = Mock(sessions={})
    manager.create_session.return_value = SimpleNamespace(session_id='next', party_size=5)
    monkeypatch.setattr(session_module, 'data_manager', manager)
    w.context.current_session_id = None
    new_message = SimpleNamespace(id=w.message.id + 1, edit=AsyncMock(), add_reaction=AsyncMock())
    w.channel.fetch_message.return_value = new_message
    ctx = SimpleNamespace(channel=w.channel, author=w.people[1], interaction=None,
                          send=AsyncMock(return_value=new_message))
    cog = session_module.SessionCommands(w.bot)
    await cog.start_session.callback(cog, ctx)
    assert w.context.current_st_message_id == new_message.id
    assert w.context.current_session_id == 'next'
    assert w.db.get_party_state(123)['soloq'] == [1]
    assert 'Player1' in new_message.edit.call_args.kwargs['content']
    assert new_message.add_reaction.await_count == 4
