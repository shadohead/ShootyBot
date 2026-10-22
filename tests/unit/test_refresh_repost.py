"""The refresh reaction must repost an intact queue with usable controls."""
from types import SimpleNamespace
from datetime import timedelta
from unittest.mock import AsyncMock

import discord
import pytest

import handlers.reaction_handler as reactions
from config import EMOJI
from tests.unit.test_party_snapshot_recovery import world


@pytest.fixture
def repost(world):
    w = world
    w.message.id = discord.utils.time_snowflake(discord.utils.utcnow() - timedelta(minutes=30))
    w.context.current_st_message_id = w.message.id
    w.context.add_soloq_user(w.people[1])
    reactions.apply_party_reaction(w.context, w.people[2], EMOJI['FULL_STACK'], True)
    reactions.apply_party_reaction(w.context, w.people[2], EMOJI['READY'], True)
    w.context.set_plus_ones(w.people[1], 2)
    assert w.cm.save_context(123)
    new_message = SimpleNamespace(id=discord.utils.time_snowflake(discord.utils.utcnow()), channel=w.channel,
                                  author=w.bot.user, reactions=[], edit=AsyncMock(),
                                  add_reaction=AsyncMock(), delete=AsyncMock())
    w.message.reply = AsyncMock(return_value=new_message)
    w.new_message = new_message
    w.handler = reactions.ReactionHandler(w.bot)
    return w


def payload(w, message, emoji='🔄'):
    return SimpleNamespace(channel_id=123, message_id=message.id,
                           user_id=3, member=w.people[3], emoji=emoji)


@pytest.mark.asyncio
async def test_refresh_dispatch_reposts_and_transfers_controls_without_reset(repost):
    w = repost
    before = w.context.party_snapshot()
    await w.handler.on_raw_reaction_add(payload(w, w.message))
    w.message.reply.assert_awaited_once()
    content = w.message.reply.call_args.args[0]
    mentions = w.message.reply.call_args.kwargs['allowed_mentions']
    assert 'Player1+2' in content and 'Player2' in content
    assert mentions.everyone is False and mentions.roles is False and mentions.replied_user is False
    assert [call.args[0] for call in w.new_message.add_reaction.await_args_list] == ['👍', '5️⃣', '🔄', '📣']
    assert w.context.current_st_message_id == w.new_message.id
    assert w.context.party_started_message_id == w.message.id
    after = w.db.get_party_state(123)
    for field in ('session_id', 'soloq', 'fullstack', 'ready', 'plus_ones'):
        expected = before[field]
        if field == 'plus_ones':
            expected = {str(uid): count for uid, count in expected.items()}
        assert after[field] == expected
    assert after['message_id'] == w.new_message.id
    assert after['reaction_users'] == {}  # the replacement starts with bot-only reactions
    w.message.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reposted_queue_survives_restart_before_players_react_again(repost):
    w = repost
    await w.handler.on_raw_reaction_add(payload(w, w.message))
    w.cm.contexts.clear()
    w.channel.fetch_message.return_value = w.new_message
    assert await reactions.restore_party_state_from_reactions(w.bot) == 1
    restored = w.cm.get_context(123)
    assert restored.current_st_message_id == w.new_message.id
    assert restored.current_session_id == 'live'
    assert restored.bot_soloq_user_set == {w.people[1]}
    assert restored.bot_fullstack_user_set == {w.people[2]}
    assert restored.bot_ready_user_set == {w.people[2]}
    assert restored.get_plus_ones(w.people[1]) == 2


@pytest.mark.asyncio
async def test_repost_does_not_restart_session_expiry_clock(repost):
    from match_tracker import MatchTracker
    w = repost
    started_at = MatchTracker._stack_started_at(w.context)
    await w.handler.on_raw_reaction_add(payload(w, w.message))
    assert MatchTracker._stack_started_at(w.context) == started_at
    w.cm.contexts.clear()
    w.channel.fetch_message.return_value = w.new_message
    assert await reactions.restore_party_state_from_reactions(w.bot) == 1
    assert MatchTracker._stack_started_at(w.cm.get_context(123)) == started_at


@pytest.mark.asyncio
async def test_reposted_controls_accept_reactions_and_old_post_cannot_repost_again(repost):
    w = repost
    await w.handler.on_raw_reaction_add(payload(w, w.message))
    await w.handler.on_raw_reaction_add(payload(w, w.message))
    w.message.reply.assert_awaited_once()
    w.channel.fetch_message.return_value = w.new_message
    w.handler._track_session_participation = AsyncMock()
    await w.handler.on_raw_reaction_add(payload(w, w.new_message, '👍'))
    assert w.people[3] in w.context.bot_soloq_user_set
    assert w.db.get_party_state(123)['soloq'] == [1, 3]
    assert 'Player3' in w.new_message.edit.call_args.kwargs['content']


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['send', 'controls', 'save'])
async def test_failed_repost_preserves_active_queue_and_snapshot(repost, monkeypatch, failure):
    w = repost
    before = w.db.get_party_state(123)
    error = discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'test permissions')
    if failure == 'send':
        w.message.reply.side_effect = error
    elif failure == 'controls':
        w.new_message.add_reaction.side_effect = error
    else:
        monkeypatch.setattr(w.cm, 'save_context', lambda channel_id: False)
    with pytest.raises((discord.HTTPException, RuntimeError)):
        await w.handler.on_raw_reaction_add(payload(w, w.message))
    assert w.context.current_st_message_id == w.message.id
    assert w.context.party_snapshot()['reaction_users'] == before['reaction_users']
    assert w.db.get_party_state(123) == before
    if failure != 'send':
        w.new_message.delete.assert_awaited_once()
    assert w.context.get_unique_user_count() == 4
