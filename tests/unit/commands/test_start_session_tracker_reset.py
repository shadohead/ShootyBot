"""/st must start the match tracker's per-channel state from a clean slate.

(tests/unit/commands/test_session_commands.py is skipped module-wide, so this
guard lives in its own module.)
"""
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from commands.session_commands import SessionCommands


@pytest.fixture
def session_cog():
    bot = Mock()
    bot.update_status_with_queue_count = AsyncMock()
    bot.match_tracker = MagicMock()
    with patch('commands.session_commands.BaseCommandCog.__init__', return_value=None):
        cog = SessionCommands(bot)
    cog.logger = Mock()
    cog.bot = bot
    return cog


@pytest.mark.asyncio
@patch('commands.session_commands.add_react_options', new_callable=AsyncMock)
@patch('commands.session_commands.get_ping_shooty_message', return_value="ping")
@patch('commands.session_commands.data_manager')
@patch('commands.session_commands.context_manager')
async def test_start_session_resets_tracker_state(mock_cm, mock_dm, _ping, _react,
                                                  session_cog, mock_discord_context):
    context = MagicMock()
    context.current_session_id = None
    mock_cm.get_context.return_value = context
    mock_dm.create_session.return_value = Mock(session_id="sess-new")
    mock_discord_context.send = AsyncMock(return_value=Mock(id=999))

    await session_cog.start_session.callback(session_cog, mock_discord_context)

    session_cog.bot.match_tracker.reset_stack_tracking.assert_called_once_with(
        mock_discord_context.channel.id)
    assert context.current_session_id == "sess-new"


@pytest.mark.asyncio
@patch('commands.session_commands.add_react_options', new_callable=AsyncMock)
@patch('commands.session_commands.get_ping_shooty_message', return_value="ping")
@patch('commands.session_commands.data_manager')
@patch('commands.session_commands.context_manager')
async def test_start_session_without_tracker(mock_cm, mock_dm, _ping, _react,
                                             session_cog, mock_discord_context):
    """The tracker starts after on_ready; /st must still work without it."""
    session_cog.bot.match_tracker = None
    context = MagicMock()
    context.current_session_id = None
    mock_cm.get_context.return_value = context
    mock_dm.create_session.return_value = Mock(session_id="sess-new")
    mock_discord_context.send = AsyncMock(return_value=Mock(id=999))

    await session_cog.start_session.callback(session_cog, mock_discord_context)

    assert context.current_session_id == "sess-new"
    mock_discord_context.send.assert_awaited()
