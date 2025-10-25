"""Tests for party_commands.py"""
import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock

from commands.party_commands import PartyCommands


@pytest.fixture
def party_cog():
    """Create PartyCommands cog for testing"""
    mock_bot = MagicMock()
    mock_bot.update_status_with_queue_count = AsyncMock()
    return PartyCommands(mock_bot)


@pytest.fixture
def mock_ctx():
    """Create a mock context"""
    ctx = MagicMock()
    ctx.channel = MagicMock()
    ctx.channel.id = 123456
    ctx.reply = AsyncMock()
    ctx.send = AsyncMock()
    return ctx


@pytest.fixture
def mock_context_manager():
    """Mock context manager"""
    with patch('commands.party_commands.context_manager') as mock_cm:
        mock_context = MagicMock()
        mock_context.bot_soloq_user_set = set()
        mock_context.bot_fullstack_user_set = set()
        mock_context.get_party_max_size.return_value = 5
        mock_context.set_party_max_size = MagicMock()
        mock_context.remove_user_from_everything.return_value = []
        mock_context.reset_users = MagicMock()
        mock_context.backup_state = MagicMock()
        mock_cm.get_context.return_value = mock_context
        mock_cm.save_context = MagicMock()
        yield mock_cm


class TestKickUser:
    """Test shootykick command"""

    @pytest.mark.asyncio
    async def test_kick_user_success(self, party_cog, mock_ctx, mock_context_manager):
        """Test kicking a user successfully"""
        context = mock_context_manager.get_context.return_value
        context.remove_user_from_everything.return_value = ["TestUser"]

        await party_cog.kick_user.callback(party_cog, mock_ctx, username="Test")

        # Should remove user
        context.remove_user_from_everything.assert_called_once_with(["Test"])

        # Should save context
        mock_context_manager.save_context.assert_called_once_with(123456)

        # Should reply with success message
        assert mock_ctx.reply.called

        # Should update bot status
        party_cog.bot.update_status_with_queue_count.assert_called_once()

    @pytest.mark.asyncio
    async def test_kick_user_not_found(self, party_cog, mock_ctx, mock_context_manager):
        """Test kicking a user that doesn't exist"""
        context = mock_context_manager.get_context.return_value
        context.remove_user_from_everything.return_value = []

        await party_cog.kick_user.callback(party_cog, mock_ctx, username="NonExistent")

        # Should not update bot status
        party_cog.bot.update_status_with_queue_count.assert_not_called()

        # Should send error
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_kick_multiple_users(self, party_cog, mock_ctx, mock_context_manager):
        """Test kicking multiple users matching prefix"""
        context = mock_context_manager.get_context.return_value
        context.remove_user_from_everything.return_value = ["TestUser1", "TestUser2"]

        await party_cog.kick_user.callback(party_cog, mock_ctx, username="Test")

        # Should reply with both usernames
        assert mock_ctx.reply.called


class TestSetSessionSize:
    """Test shootysize command"""

    @pytest.mark.asyncio
    async def test_set_size_success(self, party_cog, mock_ctx, mock_context_manager):
        """Test setting party size successfully"""
        context = mock_context_manager.get_context.return_value

        await party_cog.set_session_size.callback(party_cog, mock_ctx, size="10")

        # Should set the new size
        context.set_party_max_size.assert_called_once_with(10)

        # Should save context
        mock_context_manager.save_context.assert_called_once_with(123456)

        # Should reply with success
        assert mock_ctx.reply.called

    @pytest.mark.asyncio
    async def test_set_size_invalid_number(self, party_cog, mock_ctx, mock_context_manager):
        """Test setting party size with non-numeric input"""
        context = mock_context_manager.get_context.return_value

        await party_cog.set_session_size.callback(party_cog, mock_ctx, size="abc")

        # Should not set size
        context.set_party_max_size.assert_not_called()

        # Should not save context
        mock_context_manager.save_context.assert_not_called()

        # Should send error
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_set_size_too_small(self, party_cog, mock_ctx, mock_context_manager):
        """Test setting party size below minimum (1)"""
        context = mock_context_manager.get_context.return_value

        await party_cog.set_session_size.callback(party_cog, mock_ctx, size="0")

        # Should not set size
        context.set_party_max_size.assert_not_called()

        # Should send error
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_set_size_too_large(self, party_cog, mock_ctx, mock_context_manager):
        """Test setting party size above maximum (20)"""
        context = mock_context_manager.get_context.return_value

        await party_cog.set_session_size.callback(party_cog, mock_ctx, size="21")

        # Should not set size
        context.set_party_max_size.assert_not_called()

        # Should send error
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_set_size_minimum_value(self, party_cog, mock_ctx, mock_context_manager):
        """Test setting party size to minimum valid value (1)"""
        context = mock_context_manager.get_context.return_value

        await party_cog.set_session_size.callback(party_cog, mock_ctx, size="1")

        # Should set size to 1
        context.set_party_max_size.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_set_size_maximum_value(self, party_cog, mock_ctx, mock_context_manager):
        """Test setting party size to maximum valid value (20)"""
        context = mock_context_manager.get_context.return_value

        await party_cog.set_session_size.callback(party_cog, mock_ctx, size="20")

        # Should set size to 20
        context.set_party_max_size.assert_called_once_with(20)

    @pytest.mark.asyncio
    async def test_set_size_negative_number(self, party_cog, mock_ctx, mock_context_manager):
        """Test setting party size to negative number"""
        context = mock_context_manager.get_context.return_value

        await party_cog.set_session_size.callback(party_cog, mock_ctx, size="-5")

        # Should not set size
        context.set_party_max_size.assert_not_called()


class TestClearSession:
    """Test shootyclear command"""

    @pytest.mark.asyncio
    async def test_clear_session_success(self, party_cog, mock_ctx, mock_context_manager):
        """Test clearing session with users"""
        # Create mock users
        user1 = MagicMock()
        user1.name = "User1"
        user2 = MagicMock()
        user2.name = "User2"

        context = mock_context_manager.get_context.return_value
        context.bot_soloq_user_set = {user1}
        context.bot_fullstack_user_set = {user2}

        await party_cog.clear_session.callback(party_cog, mock_ctx)

        # Should backup state first
        context.backup_state.assert_called_once()

        # Should reset users
        context.reset_users.assert_called_once()

        # Should save context
        mock_context_manager.save_context.assert_called_once_with(123456)

        # Should send success message
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_clear_session_empty(self, party_cog, mock_ctx, mock_context_manager):
        """Test clearing session with no users"""
        context = mock_context_manager.get_context.return_value
        context.bot_soloq_user_set = set()
        context.bot_fullstack_user_set = set()

        await party_cog.clear_session.callback(party_cog, mock_ctx)

        # Should not backup or reset
        context.backup_state.assert_not_called()
        context.reset_users.assert_not_called()

        # Should not save context
        mock_context_manager.save_context.assert_not_called()

        # Should send info message
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_clear_session_with_soloq_only(self, party_cog, mock_ctx, mock_context_manager):
        """Test clearing session with only solo queue users"""
        user1 = MagicMock()
        user1.name = "User1"

        context = mock_context_manager.get_context.return_value
        context.bot_soloq_user_set = {user1}
        context.bot_fullstack_user_set = set()

        await party_cog.clear_session.callback(party_cog, mock_ctx)

        # Should clear session
        context.reset_users.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_session_with_fullstack_only(self, party_cog, mock_ctx, mock_context_manager):
        """Test clearing session with only fullstack users"""
        user1 = MagicMock()
        user1.name = "User1"

        context = mock_context_manager.get_context.return_value
        context.bot_soloq_user_set = set()
        context.bot_fullstack_user_set = {user1}

        await party_cog.clear_session.callback(party_cog, mock_ctx)

        # Should clear session
        context.reset_users.assert_called_once()


class TestSetup:
    """Test cog setup"""

    @pytest.mark.asyncio
    async def test_setup_adds_cog(self):
        """Test that setup function adds the cog"""
        from commands.party_commands import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        # Should add the cog
        mock_bot.add_cog.assert_called_once()
        assert isinstance(mock_bot.add_cog.call_args[0][0], PartyCommands)
