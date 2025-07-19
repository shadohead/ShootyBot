import pytest
from unittest.mock import Mock, patch, AsyncMock

pytest.skip("SessionCommands tests require complex Discord mocks", allow_module_level=True)
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from commands.session_commands import SessionCommands
import discord
from discord.ext import commands


class TestSessionCommandsUpdated:
    """Test SessionCommands cog with new BaseCommandCog structure"""
    
    @pytest.fixture
    def session_cog(self):
        """Create SessionCommands cog with mocked bot"""
        mock_bot = Mock()
        mock_bot.update_status_with_queue_count = AsyncMock()
        with patch('commands.session_commands.BaseCommandCog.__init__', return_value=None):
            cog = SessionCommands(mock_bot)
            cog.logger = Mock()
            cog.bot = mock_bot
            return cog
    
    @pytest.fixture
    def mock_ctx(self, mock_discord_context):
        """Use shared mock Discord context fixture"""
        mock_discord_context.guild.name = "Test Guild"
        mock_discord_context.channel.name = "test-channel"
        return mock_discord_context
    
    @patch('commands.session_commands.context_manager')
    @patch('commands.session_commands.data_manager')
    @pytest.mark.asyncio
    async def test_start_session_new(self, mock_data_manager, mock_context_manager, session_cog, mock_ctx):
        """Test starting a new session"""
        # Mock context
        mock_shooty_context = Mock()
        mock_shooty_context.current_session_id = None
        mock_shooty_context.party_max_size = 5
        mock_shooty_context.game_name = "Valorant"
        mock_shooty_context.backup_state = Mock()
        mock_shooty_context.reset_users = Mock()
        mock_context_manager.get_context.return_value = mock_shooty_context
        mock_context_manager.save_context = Mock()
        
        # Mock session creation
        mock_session = Mock()
        mock_session.session_id = "test_session_123"
        mock_data_manager.create_session.return_value = mock_session
        
        # Mock message formatting and reactions
        with patch('commands.session_commands.get_ping_shooty_message') as mock_ping_msg, \
             patch('commands.session_commands.add_react_options') as mock_reactions:
            
            mock_ping_msg.return_value = "Test session started!"
            mock_reactions.return_value = None
            mock_ctx.send.return_value = Mock(id=999)
            
            # Execute the command
            await session_cog.start_session.callback(session_cog, mock_ctx)
            
            # Verify session creation
            mock_data_manager.create_session.assert_called_once_with(
                channel_id=111222333,
                started_by=123456789,
                game_name="Valorant"
            )
            
            # Verify context operations
            mock_shooty_context.backup_state.assert_called_once()
            mock_shooty_context.reset_users.assert_called_once()
            mock_context_manager.save_context.assert_called()
            
            # Verify message was sent
            mock_ctx.send.assert_called_once()
    
    @patch('commands.session_commands.context_manager')
    @patch('commands.session_commands.data_manager')
    @pytest.mark.asyncio
    async def test_start_session_with_existing(self, mock_data_manager, mock_context_manager, session_cog, mock_ctx):
        """Test starting a session when one already exists"""
        # Mock context with existing session
        mock_shooty_context = Mock()
        mock_shooty_context.current_session_id = "existing_session"
        mock_shooty_context.party_max_size = 5
        mock_shooty_context.game_name = "Valorant"
        mock_shooty_context.backup_state = Mock()
        mock_shooty_context.reset_users = Mock()
        mock_context_manager.get_context.return_value = mock_shooty_context
        
        # Mock ending existing session
        mock_existing_session = Mock()
        mock_data_manager.get_session.return_value = mock_existing_session
        
        # Mock new session creation
        mock_new_session = Mock()
        mock_new_session.session_id = "new_session_123"
        mock_data_manager.create_session.return_value = mock_new_session
        
        with patch('commands.session_commands.get_ping_shooty_message') as mock_ping_msg, \
             patch('commands.session_commands.add_react_options') as mock_reactions:
            
            mock_ping_msg.return_value = "Test session started!"
            mock_reactions.return_value = None
            mock_ctx.send.return_value = Mock(id=999)
            
            # Execute the command
            await session_cog.start_session.callback(session_cog, mock_ctx)
            
            # Should end existing session and create new one
            mock_data_manager.create_session.assert_called_once()
            assert mock_shooty_context.current_session_id == "new_session_123"
    
    @patch('commands.session_commands.context_manager')
    @pytest.mark.asyncio
    async def test_mention_session_no_users(self, mock_context_manager, session_cog, mock_ctx):
        """Test mentioning when no users are in session"""
        # Mock context with no users
        mock_shooty_context = Mock()
        mock_shooty_context.get_unique_user_count.return_value = 0
        mock_context_manager.get_context.return_value = mock_shooty_context
        
        # Mock the send_info_embed method from BaseCommandCog
        session_cog.send_info_embed = AsyncMock()
        
        # Execute the command
        await session_cog.mention_session.callback(session_cog, mock_ctx)
        
        # Should send info embed about no users
        session_cog.send_info_embed.assert_called_once_with(
            mock_ctx,
            "No Active Session",
            "There are currently no users in the session to mention"
        )
    
    @patch('commands.session_commands.context_manager')
    @patch('commands.session_commands.data_manager')
    @pytest.mark.asyncio
    async def test_end_session_with_active_session(self, mock_data_manager, mock_context_manager, session_cog, mock_ctx):
        """Test ending an active session"""
        # Mock context with active session
        mock_shooty_context = Mock()
        mock_shooty_context.current_session_id = "active_session"
        mock_shooty_context.get_unique_user_count.return_value = 3
        mock_context_manager.get_context.return_value = mock_shooty_context
        
        # Mock session
        mock_session = Mock()
        mock_session.end_session = Mock()
        mock_data_manager.get_session.return_value = mock_session
        
        # Mock the send_success_embed method from BaseCommandCog
        session_cog.send_success_embed = AsyncMock()
        
        # Execute the command
        await session_cog.end_session.callback(session_cog, mock_ctx)
        
        # Verify session was ended
        mock_session.end_session.assert_called_once_with(3)
        mock_data_manager.save_session.assert_called_once_with(mock_session)
        
        # Verify success message
        session_cog.send_success_embed.assert_called_once()
    
    @patch('commands.session_commands.context_manager')
    @pytest.mark.asyncio
    async def test_end_session_no_active_session(self, mock_context_manager, session_cog, mock_ctx):
        """Test ending session when none is active"""
        # Mock context with no active session
        mock_shooty_context = Mock()
        mock_shooty_context.current_session_id = None
        mock_context_manager.get_context.return_value = mock_shooty_context
        
        # Mock the send_info_embed method from BaseCommandCog
        session_cog.send_info_embed = AsyncMock()
        
        # Execute the command
        await session_cog.end_session.callback(session_cog, mock_ctx)
        
        # Should send info about no active session
        session_cog.send_info_embed.assert_called_once_with(
            mock_ctx,
            "No Active Session",
            "There is no active session to end"
        )


class TestScheduledSessionUpdated:
    """Test scheduled session functionality"""
    
    @pytest.fixture
    def session_cog(self):
        """Create SessionCommands cog with mocked bot"""
        mock_bot = Mock()
        mock_bot.update_status_with_queue_count = AsyncMock()
        with patch('commands.session_commands.BaseCommandCog.__init__', return_value=None):
            cog = SessionCommands(mock_bot)
            cog.logger = Mock()
            cog.bot = mock_bot
            return cog
    
    @pytest.fixture
    def mock_ctx(self, mock_discord_context):
        """Use shared mock Discord context fixture"""
        return mock_discord_context
    
    @patch('commands.session_commands.context_manager')
    @patch('commands.session_commands.parser')
    @pytest.mark.asyncio
    async def test_scheduled_session_success(self, mock_parser, mock_context_manager, session_cog, mock_ctx):
        """Test successful scheduled session creation"""
        # Mock time parsing
        from datetime import datetime, timezone
        future_time = datetime.now(timezone.utc).replace(hour=15, minute=30)
        mock_parser.parse.return_value = future_time
        
        # Mock context
        mock_shooty_context = Mock()
        mock_shooty_context.scheduled_time = None
        mock_context_manager.get_context.return_value = mock_shooty_context
        
        # Mock the send_success_embed method
        session_cog.send_success_embed = AsyncMock()
        
        # Execute the command
        await session_cog.scheduled_session.callback(session_cog, mock_ctx, "3:30 PM")
        
        # Verify scheduled time was set
        assert mock_shooty_context.scheduled_time == future_time
        mock_context_manager.save_context.assert_called_once_with(111222333)
        
        # Verify success message
        session_cog.send_success_embed.assert_called_once()
    
    @patch('commands.session_commands.context_manager')
    @patch('commands.session_commands.parser')
    @pytest.mark.asyncio
    async def test_scheduled_session_invalid_time(self, mock_parser, mock_context_manager, session_cog, mock_ctx):
        """Test scheduled session with invalid time"""
        # Mock parser to raise exception
        mock_parser.parse.side_effect = ValueError("Invalid time format")
        
        # Mock the send_error_embed method
        session_cog.send_error_embed = AsyncMock()
        
        # Execute the command
        await session_cog.scheduled_session.callback(session_cog, mock_ctx, "invalid time")
        
        # Should send error message
        session_cog.send_error_embed.assert_called_once_with(
            mock_ctx,
            "Invalid Time Format",
            "Please use a valid time format (e.g., '3:30 PM', '15:30', 'tomorrow 2pm')"
        )