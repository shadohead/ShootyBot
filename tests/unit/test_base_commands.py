import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from base_commands import BaseCommandCog, PaginatedEmbed, require_confirmation


class DummyInteraction:
    def __init__(self, responded=False):
        self.response = MagicMock()
        self.response.is_done = MagicMock(return_value=responded)
        self.response.send_message = AsyncMock()
        self.followup = MagicMock()
        self.followup.send = AsyncMock()


@pytest.mark.asyncio
async def test_send_embed_with_context():
    cog = BaseCommandCog(MagicMock())
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()

    result = await cog.send_embed(ctx, "Title", "Desc", color=0x123456)

    ctx.send.assert_called_once()
    embed = ctx.send.call_args.kwargs["embed"]
    assert embed.title == "Title"
    assert embed.description == "Desc"
    assert embed.color.value == 0x123456
    assert result == ctx.send.return_value

@pytest.mark.asyncio
async def test_send_embed_with_interaction_send_message():
    cog = BaseCommandCog(MagicMock())
    interaction = DummyInteraction(responded=False)
    with patch("base_commands.discord.Interaction", DummyInteraction):
        result = await cog.send_embed(interaction, "Title")

    interaction.response.send_message.assert_called_once()
    assert result == interaction.response.send_message.return_value

@pytest.mark.asyncio
async def test_send_embed_with_interaction_followup():
    cog = BaseCommandCog(MagicMock())
    interaction = DummyInteraction(responded=True)
    with patch("base_commands.discord.Interaction", DummyInteraction):
        result = await cog.send_embed(interaction, "Title")

    interaction.followup.send.assert_called_once()
    assert result == interaction.followup.send.return_value


@pytest.mark.asyncio
async def test_send_error_and_success_embed():
    cog = BaseCommandCog(MagicMock())
    with patch.object(cog, "send_embed", AsyncMock()) as mock_send:
        await cog.send_error_embed("ctx", "Oops", "fail")
        await cog.send_success_embed("ctx", "Great", "ok")

    assert mock_send.call_count == 2
    args1, kwargs1 = mock_send.call_args_list[0]
    assert args1[0] == "ctx"
    assert args1[1] == "❌ Oops"
    assert args1[2] == "fail"
    assert kwargs1["color"] == 0xff0000
    args2, kwargs2 = mock_send.call_args_list[1]
    assert args2[1] == "✅ Great"
    assert args2[2] == "ok"
    assert kwargs2["color"] == 0x00ff00


def test_paginated_embed_pages():
    paginator = PaginatedEmbed("Items", items_per_page=2, footer_base="Base")
    paginator.add_items(["a", "b", "c", "d", "e"])

    assert paginator.get_total_pages() == 3
    page1 = paginator.get_page(1)
    assert page1.title == "Items (Page 1/3)"
    assert page1.description == "a\nb"
    assert "Page 1 of 3" in page1.footer.text

    page3 = paginator.get_page(3)
    assert page3.description == "e"
    assert "Page 3 of 3" in page3.footer.text

    page_over = paginator.get_page(5)
    assert page_over.title == "Items (Page 3/3)"


def test_paginated_embed_empty():
    paginator = PaginatedEmbed("Empty", items_per_page=3)
    page = paginator.get_page()
    assert paginator.get_total_pages() == 1
    assert page.description == "No items"


class DummyView:
    def __init__(self, value=None, user=None):
        self.value = value
        if user is not None:
            self.interaction = MagicMock()
            self.interaction.user = user
            self.interaction.response = AsyncMock()
        else:
            self.interaction = None
        self.children = []

    async def wait(self):
        return

@pytest.mark.asyncio
async def test_require_confirmation_yes():
    ctx = MagicMock(spec=commands.Context)
    ctx.author = MagicMock()
    message = MagicMock()
    message.edit = AsyncMock()
    ctx.send = AsyncMock(return_value=message)

    view = DummyView(value=True, user=ctx.author)
    with patch("base_commands.ConfirmationView", return_value=view):
        result = await require_confirmation(ctx, "Confirm?")

    assert result is True
    view.interaction.response.defer.assert_called_once()
    message.edit.assert_not_called()

@pytest.mark.asyncio
async def test_require_confirmation_cancel():
    ctx = MagicMock(spec=commands.Context)
    ctx.author = MagicMock()
    message = MagicMock()
    message.edit = AsyncMock()
    ctx.send = AsyncMock(return_value=message)

    view = DummyView(value=False, user=ctx.author)
    with patch("base_commands.ConfirmationView", return_value=view):
        result = await require_confirmation(ctx, "Prompt")

    assert result is False
    view.interaction.response.defer.assert_called_once()
    message.edit.assert_called_once()
    embed = message.edit.call_args.kwargs["embed"]
    assert "❌ Cancelled." in embed.description

@pytest.mark.asyncio
async def test_require_confirmation_timeout():
    ctx = MagicMock(spec=commands.Context)
    ctx.author = MagicMock()
    message = MagicMock()
    message.edit = AsyncMock()
    ctx.send = AsyncMock(return_value=message)

    view = DummyView(value=None)
    with patch("base_commands.ConfirmationView", return_value=view):
        result = await require_confirmation(ctx, "Prompt")

    assert result is False
    message.edit.assert_called_once()
    embed = message.edit.call_args.kwargs["embed"]
    assert "timed out" in embed.description

