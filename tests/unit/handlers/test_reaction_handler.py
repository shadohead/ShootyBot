import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import discord
from handlers.reaction_handler import ReactionHandler, add_react_options
from config import EMOJI, MESSAGES


class TestAddReactOptions:
    """Test the add_react_options helper function"""
    
    @pytest.mark.asyncio
    async def test_add_react_options(self):
        """Test adding reaction options to a message"""
        mock_message = AsyncMock()
        
        await add_react_options(mock_message)
        
        # Verify all required reactions were added
        expected_reactions = [
            EMOJI["THUMBS_UP"],
            EMOJI["FULL_STACK"], 
            EMOJI["REFRESH"],
            EMOJI["MENTION"]
        ]
        
        assert mock_message.add_reaction.call_count == len(expected_reactions)
        for emoji in expected_reactions:
            mock_message.add_reaction.assert_any_call(emoji)


class TestReactionHandler:
    """Simplified test cases for ReactionHandler class"""
    
    @pytest.fixture
    def handler(self):
        """Create a ReactionHandler instance with mocked bot"""
        bot = Mock()
        bot.user = Mock(id=999999999)
        return ReactionHandler(bot)
    
    @pytest.mark.asyncio
    async def test_ignore_bot_reactions(self, handler):
        """Test that bot reactions are ignored"""
        reaction = Mock()
        user = Mock(bot=True)
        
        # Should return early for bot users
        result = await handler.on_reaction_add(reaction, user)
        assert result is None
        
        result = await handler.on_reaction_remove(reaction, user)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_ignore_non_bot_messages(self, handler):
        """Test that reactions on non-bot messages are ignored"""
        reaction = Mock()
        reaction.message = Mock()
        reaction.message.author = Mock(id=123456)  # Not the bot
        user = Mock(bot=False)
        
        # Should return early for non-bot messages
        result = await handler.on_reaction_add(reaction, user)
        assert result is None
        
        result = await handler.on_reaction_remove(reaction, user)
        assert result is None
    
    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_ignore_outdated_messages(self, mock_context_manager, handler):
        """Test that reactions on outdated messages are ignored"""
        # Setup
        mock_context = Mock()
        mock_context.current_st_message_id = 999
        mock_context_manager.get_context.return_value = mock_context
        
        reaction = Mock()
        reaction.message = Mock()
        reaction.message.id = 123  # Different from current message
        reaction.message.author = handler.bot.user
        reaction.message.channel = Mock(id=111222333)
        
        user = Mock(bot=False)
        
        # Should return after checking message ID
        with patch('handlers.reaction_handler.logging'):
            result = await handler.on_reaction_add(reaction, user)
            assert result is None
    
    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.data_manager')
    async def test_track_session_participation(self, mock_data_manager, handler):
        """Test session participation tracking"""
        # Setup context with active session
        mock_context = Mock()
        mock_context.current_session_id = "session_123"
        
        # Setup session
        mock_session = Mock()
        mock_session.session_id = "session_123"
        mock_session.add_participant = Mock()
        mock_sessions = MagicMock()
        mock_sessions.get.return_value = mock_session
        mock_data_manager.sessions = mock_sessions
        
        # Setup user data
        mock_user_data = Mock()
        mock_data_manager.get_user.return_value = mock_user_data
        
        # Test user
        user = Mock(id=123456789, name="TestUser")
        
        # Call the method
        await handler._track_session_participation(mock_context, user)
        
        # Verify tracking occurred
        mock_session.add_participant.assert_called_once_with(123456789)
        mock_user_data.add_session_to_history.assert_called_once_with("session_123")
        mock_data_manager.save_session.assert_called_once_with("session_123")
        mock_data_manager.save_user.assert_called_once_with(123456789)
    
    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.data_manager')
    async def test_track_session_no_active_session(self, mock_data_manager, handler):
        """Test session tracking when no active session"""
        # Setup context without active session
        mock_context = Mock()
        mock_context.current_session_id = None
        
        user = Mock(id=123456789)
        
        # Call the method
        await handler._track_session_participation(mock_context, user)
        
        # Verify nothing was tracked
        mock_data_manager.sessions.get.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_refresh_status(self, handler):
        """Test refresh status functionality"""
        # Setup
        message = Mock()
        message.channel = Mock(id=111222333)
        
        mock_ctx = AsyncMock()
        handler.bot.get_context = AsyncMock(return_value=mock_ctx)
        
        mock_session_cog = AsyncMock()
        handler.bot.get_cog = Mock(return_value=mock_session_cog)
        
        # Call the method
        await handler._refresh_status(message)
        
        # Verify
        handler.bot.get_context.assert_called_once_with(message)
        handler.bot.get_cog.assert_called_once_with('SessionCommands')
        mock_session_cog.session_status.assert_called_once_with(mock_ctx)
    
    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_mention_party_no_members(self, mock_context_manager, handler):
        """Test mention party with no members"""
        # Setup
        mock_context = Mock()
        mock_context.bot_soloq_user_set = set()
        mock_context.bot_fullstack_user_set = set()
        mock_context_manager.get_context.return_value = mock_context
        
        message = Mock()
        message.channel = AsyncMock()
        
        # Call the method
        await handler._mention_party(message)
        
        # Verify
        message.channel.send.assert_called_once_with(MESSAGES["NO_MEMBERS"])
    
    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_mention_party_with_members(self, mock_context_manager, handler):
        """Test mention party with members"""
        # Setup
        user1 = Mock(mention="<@111>", bot=False)
        user2 = Mock(mention="<@222>", bot=False)
        bot_user = Mock(mention="<@999>", bot=True)
        
        mock_context = Mock()
        mock_context.bot_soloq_user_set = {user1, bot_user}
        mock_context.bot_fullstack_user_set = {user2}
        mock_context_manager.get_context.return_value = mock_context
        
        message = Mock()
        message.channel = AsyncMock()
        
        # Call the method
        await handler._mention_party(message)
        
        # Verify - should mention only non-bot users
        call_args = message.channel.send.call_args[0][0]
        assert "<@111>" in call_args
        assert "<@222>" in call_args
        assert "<@999>" not in call_args  # Bot user should be excluded


@pytest.mark.asyncio
async def test_setup():
    """Test the setup function"""
    mock_bot = AsyncMock()
    
    from handlers.reaction_handler import setup
    await setup(mock_bot)
    
    # Verify cog was added
    mock_bot.add_cog.assert_called_once()
    # Verify a ReactionHandler instance was passed
    from handlers.reaction_handler import ReactionHandler
    assert isinstance(mock_bot.add_cog.call_args[0][0], ReactionHandler)