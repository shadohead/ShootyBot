import pytest
import sys
import os
from unittest.mock import AsyncMock, Mock, patch

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from commands.session_commands import SessionCommands
from commands.valorant_commands import ValorantCommands

@pytest.fixture
def session_cog():
    mock_bot = Mock()
    mock_bot.update_status_with_queue_count = AsyncMock()
    with patch('commands.session_commands.BaseCommandCog.__init__', return_value=None):
        cog = SessionCommands(mock_bot)
        cog.bot = mock_bot
        cog.logger = Mock()
        return cog

@pytest.fixture
def valorant_cog():
    mock_bot = Mock()
    with patch('commands.valorant_commands.GameCommandCog.__init__', return_value=None):
        cog = ValorantCommands(mock_bot)
        cog.bot = mock_bot
        cog.logger = Mock()
        cog.send_embed = AsyncMock()
        cog.send_error_embed = AsyncMock()
        cog.defer_if_slash = AsyncMock()
        return cog

@pytest.mark.asyncio
@patch('commands.session_commands.add_react_options')
@patch('commands.session_commands.get_ping_shooty_message')
@patch('commands.session_commands.data_manager')
@patch('commands.session_commands.context_manager')
async def test_start_session_creates_session(mock_context_manager, mock_data_manager, mock_ping, mock_react, session_cog, mock_discord_context):
    shooty_context = Mock()
    shooty_context.current_session_id = None
    shooty_context.party_max_size = 5
    shooty_context.game_name = 'Valorant'
    shooty_context.role_code = '<@&1>'
    shooty_context.backup_state = Mock()
    shooty_context.reset_users = Mock()
    mock_context_manager.get_context.return_value = shooty_context

    session = Mock()
    session.session_id = 'session123'
    mock_data_manager.create_session.return_value = session
    mock_data_manager.get_user.return_value = Mock()

    mock_ping.return_value = 'ping'
    message = AsyncMock()
    message.id = 999
    mock_discord_context.send.return_value = message

    await SessionCommands.start_session.callback(session_cog, mock_discord_context)

    mock_data_manager.create_session.assert_called_once_with(
        channel_id=mock_discord_context.channel.id,
        started_by=mock_discord_context.author.id,
        game_name=shooty_context.game_name,
    )
    mock_context_manager.save_context.assert_any_call(mock_discord_context.channel.id)
    mock_react.assert_awaited_once_with(message)
    assert shooty_context.current_session_id == session.session_id

@pytest.mark.asyncio
@patch('commands.session_commands.add_react_options')
@patch('commands.session_commands.get_ping_shooty_message')
@patch('commands.session_commands.data_manager')
@patch('commands.session_commands.context_manager')
async def test_start_session_existing_session(mock_context_manager, mock_data_manager, mock_ping, mock_react, session_cog, mock_discord_context):
    shooty_context = Mock()
    shooty_context.current_session_id = 'old'
    shooty_context.party_max_size = 5
    shooty_context.game_name = 'Valorant'
    shooty_context.role_code = '<@&1>'
    shooty_context.backup_state = Mock()
    shooty_context.reset_users = Mock()
    mock_context_manager.get_context.return_value = shooty_context

    session_cog._end_current_session = AsyncMock()

    session = Mock()
    session.session_id = 'new'
    mock_data_manager.create_session.return_value = session
    mock_data_manager.get_user.return_value = Mock()

    mock_ping.return_value = 'ping'
    message = AsyncMock()
    message.id = 888
    mock_discord_context.send.return_value = message

    await SessionCommands.start_session.callback(session_cog, mock_discord_context)

    session_cog._end_current_session.assert_awaited_once_with(shooty_context)
    assert shooty_context.current_session_id == session.session_id

@pytest.mark.asyncio
@patch('commands.valorant_commands.valorant_client')
async def test_link_valorant_success(mock_valorant_client, valorant_cog, mock_discord_context):
    mock_valorant_client.link_account = AsyncMock(return_value={
        'success': True,
        'username': 'Player',
        'tag': 'NA1',
        'card': {'large': 'img'}
    })

    await ValorantCommands.link_valorant.callback(valorant_cog, mock_discord_context, 'Player', 'NA1')

    mock_valorant_client.link_account.assert_awaited_once_with(mock_discord_context.author.id, 'Player', 'NA1')
    valorant_cog.send_embed.assert_awaited_once()

@pytest.mark.asyncio
@patch('commands.valorant_commands.valorant_client')
async def test_link_valorant_failure(mock_valorant_client, valorant_cog, mock_discord_context):
    mock_valorant_client.link_account = AsyncMock(return_value={
        'success': False,
        'error': 'failed'
    })

    await ValorantCommands.link_valorant.callback(valorant_cog, mock_discord_context, 'Player', 'NA1')

    valorant_cog.send_error_embed.assert_awaited_once()
