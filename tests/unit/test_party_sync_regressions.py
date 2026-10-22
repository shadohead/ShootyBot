"""Offline reproductions of the October 21 queue desynchronization report."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from bot import ShootyBot
from config import DEFAULT_MSG
from context_manager import ShootyContext
from handlers.reaction_handler import ReactionHandler, _rebuild_users_from_reactions


def player(user_id):
    user = Mock(id=user_id, bot=False)
    user.name = "Player%s" % user_id
    return user


@pytest.mark.asyncio
async def test_status_reply_does_not_steal_session_message():
    bot = ShootyBot()
    bot._connection.user = player(999)
    bot.process_commands = AsyncMock()
    context = ShootyContext(123)
    context.current_st_message_id = 100
    reply = SimpleNamespace(id=200, author=bot.user, guild=object(),
                            content=DEFAULT_MSG + "status", channel=SimpleNamespace(id=123),
                            add_reaction=AsyncMock())
    with patch("bot.context_manager.get_context", return_value=context):
        await bot.on_message(reply)
    assert context.current_st_message_id == 100
    reply.add_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_slow_old_edit_cannot_overwrite_new_queue():
    context = ShootyContext(123)
    context.current_st_message_id = 100
    first_started = asyncio.Event()
    finish_first = asyncio.Event()
    displayed = []

    async def edit(*, content, **kwargs):
        if not first_started.is_set():
            first_started.set()
            await finish_first.wait()
        displayed.append(content)

    message = SimpleNamespace(id=100, edit=edit)
    handler = ReactionHandler(Mock())
    context.add_soloq_user(player(1))
    first = asyncio.create_task(handler._update_party_message(message, context))
    await asyncio.wait_for(first_started.wait(), timeout=2)
    context.add_soloq_user(player(2))
    second = asyncio.create_task(handler._update_party_message(message, context))
    await asyncio.sleep(0)
    finish_first.set()
    await asyncio.gather(first, second)
    assert "Player2" in displayed[-1]


@pytest.mark.asyncio
async def test_failed_reaction_rebuild_leaves_existing_party_intact():
    context = ShootyContext(123)
    original = player(1)
    context.add_soloq_user(original)

    async def users():
        yield player(2)
        raise discord.HTTPException(SimpleNamespace(status=503, reason="Unavailable"), "retry")

    reaction = SimpleNamespace(emoji="👍", users=users)
    message = SimpleNamespace(reactions=[reaction], channel=SimpleNamespace(guild=None))
    with pytest.raises(discord.HTTPException):
        await _rebuild_users_from_reactions(message, context, Mock())
    assert context.bot_soloq_user_set == {original}


def test_restoring_then_mutating_does_not_corrupt_backup():
    context = ShootyContext(123)
    original = player(1)
    context.add_soloq_user(original)
    context.backup_state()
    context.reset_users()
    assert context.restore_state()
    context.reset_users()
    assert context.restore_state()
    assert context.bot_soloq_user_set == {original}
