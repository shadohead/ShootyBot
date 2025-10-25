"""Tests for admin_commands.py"""
import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import discord
from discord.ext import commands

from commands.admin_commands import AdminCommands


@pytest.fixture
def admin_cog():
    """Create AdminCommands cog for testing"""
    mock_bot = MagicMock()
    return AdminCommands(mock_bot)


@pytest.fixture
def mock_ctx():
    """Create a mock context"""
    ctx = MagicMock()
    ctx.channel = MagicMock()
    ctx.channel.id = 123456
    ctx.guild = MagicMock()
    ctx.author = MagicMock()
    ctx.send = AsyncMock()
    return ctx


@pytest.fixture
def mock_context_manager():
    """Mock context manager"""
    with patch('commands.admin_commands.context_manager') as mock_cm:
        mock_context = MagicMock()
        mock_context.role_code = None
        mock_context.game_name = None
        mock_context.voice_channel_id = None
        mock_context.channel = None
        mock_context.bot_soloq_user_set = set()
        mock_context.bot_fullstack_user_set = set()
        mock_cm.get_context.return_value = mock_context
        mock_cm.save_context = MagicMock()
        mock_cm.contexts = {}
        yield mock_cm


class TestSetRoleCode:
    """Test shootysetrole command"""

    @pytest.mark.asyncio
    async def test_set_role_code_with_valid_role(self, admin_cog, mock_ctx, mock_context_manager):
        """Test setting role with valid role mention"""
        # Create a mock role
        mock_role = MagicMock()
        mock_role.mention = "<@&999999>"

        with patch('commands.admin_commands.resolve_role', return_value=mock_role):
            await admin_cog.set_role_code.callback(admin_cog, mock_ctx, role_mention="<@&999999>")

            # Should set the role
            context = mock_context_manager.get_context.return_value
            assert context.role_code == "<@&999999>"

            # Should save context
            mock_context_manager.save_context.assert_called_once()

            # Should send success message
            assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_set_role_code_with_invalid_role(self, admin_cog, mock_ctx, mock_context_manager):
        """Test setting role with invalid role"""
        with patch('commands.admin_commands.resolve_role', return_value=None):
            await admin_cog.set_role_code.callback(admin_cog, mock_ctx, role_mention="invalid")

            # Should not save context
            mock_context_manager.save_context.assert_not_called()

            # Should send error
            assert mock_ctx.send.called


class TestSetGameName:
    """Test shootysetgame command"""

    @pytest.mark.asyncio
    async def test_set_game_name_success(self, admin_cog, mock_ctx, mock_context_manager):
        """Test setting game name successfully"""
        await admin_cog.set_game_name.callback(admin_cog, mock_ctx, game_name="Valorant")

        # Should set game name in uppercase
        context = mock_context_manager.get_context.return_value
        assert context.game_name == "VALORANT"

        # Should save context
        mock_context_manager.save_context.assert_called_once()

        # Should send success message
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_set_game_name_too_short(self, admin_cog, mock_ctx, mock_context_manager):
        """Test setting game name that's too short"""
        await admin_cog.set_game_name.callback(admin_cog, mock_ctx, game_name="A")

        # Should not save context
        mock_context_manager.save_context.assert_not_called()

        # Should send error
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_set_game_name_too_long(self, admin_cog, mock_ctx, mock_context_manager):
        """Test setting game name that's too long"""
        long_name = "A" * 51
        await admin_cog.set_game_name.callback(admin_cog, mock_ctx, game_name=long_name)

        # Should not save context
        mock_context_manager.save_context.assert_not_called()

        # Should send error
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_set_game_name_strips_whitespace(self, admin_cog, mock_ctx, mock_context_manager):
        """Test that game name strips whitespace"""
        await admin_cog.set_game_name.callback(admin_cog, mock_ctx, game_name="  Valorant  ")

        context = mock_context_manager.get_context.return_value
        assert context.game_name == "VALORANT"


class TestSetVoiceChannel:
    """Test shootysetvoice command"""

    @pytest.mark.asyncio
    async def test_set_voice_channel_success(self, admin_cog, mock_ctx, mock_context_manager):
        """Test setting voice channel successfully"""
        mock_voice = MagicMock()
        mock_voice.id = 777777
        mock_voice.name = "Gaming Voice"
        mock_voice.guild = mock_ctx.guild

        with patch('commands.admin_commands.resolve_voice_channel', return_value=mock_voice):
            await admin_cog.set_voice_channel.callback(admin_cog, mock_ctx, voice_channel_input="777777")

            # Should set voice channel ID
            context = mock_context_manager.get_context.return_value
            assert context.voice_channel_id == 777777

            # Should save context
            mock_context_manager.save_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_voice_channel_clear(self, admin_cog, mock_ctx, mock_context_manager):
        """Test clearing voice channel setting"""
        await admin_cog.set_voice_channel.callback(admin_cog, mock_ctx, voice_channel_input=None)

        # Should clear voice channel ID
        context = mock_context_manager.get_context.return_value
        assert context.voice_channel_id is None

        # Should save context
        mock_context_manager.save_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_voice_channel_invalid(self, admin_cog, mock_ctx, mock_context_manager):
        """Test setting invalid voice channel"""
        with patch('commands.admin_commands.resolve_voice_channel', return_value=None):
            await admin_cog.set_voice_channel.callback(admin_cog, mock_ctx, voice_channel_input="invalid")

            # Should not save context
            mock_context_manager.save_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_voice_channel_wrong_guild(self, admin_cog, mock_ctx, mock_context_manager):
        """Test setting voice channel from different guild"""
        mock_voice = MagicMock()
        mock_voice.id = 777777
        mock_voice.guild = MagicMock()  # Different guild

        with patch('commands.admin_commands.resolve_voice_channel', return_value=mock_voice):
            await admin_cog.set_voice_channel.callback(admin_cog, mock_ctx, voice_channel_input="777777")

            # Should not save context
            mock_context_manager.save_context.assert_not_called()


class TestLFG:
    """Test shootylfg command"""

    @pytest.mark.asyncio
    async def test_lfg_no_game_set(self, admin_cog, mock_ctx, mock_context_manager):
        """Test LFG when no game is set"""
        context = mock_context_manager.get_context.return_value
        context.game_name = None

        await admin_cog.lfg.callback(admin_cog, mock_ctx)

        # Should send error about no game set
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_lfg_with_players(self, admin_cog, mock_ctx, mock_context_manager):
        """Test LFG with players queued"""
        # Setup current context
        current_context = mock_context_manager.get_context.return_value
        current_context.game_name = "VALORANT"

        # Setup another context with same game
        other_context = MagicMock()
        other_context.game_name = "VALORANT"
        other_context.bot_soloq_user_set = {123, 456}
        other_context.bot_fullstack_user_set = {789}
        other_context.get_user_list_string_with_hashtag.return_value = "User1, User2, User3"
        other_context.channel = MagicMock()
        other_context.channel.guild.name = "Test Guild"
        other_context.channel.name = "valorant"

        mock_context_manager.contexts = {
            123456: current_context,
            789012: other_context
        }

        await admin_cog.lfg.callback(admin_cog, mock_ctx)

        # Should send embed with player info
        assert mock_ctx.send.called
        call_args = mock_ctx.send.call_args
        assert 'embed' in call_args[1]

    @pytest.mark.asyncio
    async def test_lfg_no_players(self, admin_cog, mock_ctx, mock_context_manager):
        """Test LFG with no players queued"""
        current_context = mock_context_manager.get_context.return_value
        current_context.game_name = "VALORANT"

        # No other contexts
        mock_context_manager.contexts = {123456: current_context}

        await admin_cog.lfg.callback(admin_cog, mock_ctx)

        # Should send info about no players
        assert mock_ctx.send.called


class TestBeacon:
    """Test shootybeacon command"""

    @pytest.mark.asyncio
    async def test_beacon_no_game_set(self, admin_cog, mock_ctx, mock_context_manager):
        """Test beacon when no game is set"""
        context = mock_context_manager.get_context.return_value
        context.game_name = None

        with patch.object(admin_cog, 'defer_if_slash', new_callable=AsyncMock):
            await admin_cog.beacon.callback(admin_cog, mock_ctx, message="Looking for group!")

            # Should send error
            assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_beacon_message_too_short(self, admin_cog, mock_ctx, mock_context_manager):
        """Test beacon with message too short"""
        context = mock_context_manager.get_context.return_value
        context.game_name = "VALORANT"

        with patch.object(admin_cog, 'defer_if_slash', new_callable=AsyncMock):
            await admin_cog.beacon.callback(admin_cog, mock_ctx, message="Hi")

            # Should send error
            assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_beacon_message_too_long(self, admin_cog, mock_ctx, mock_context_manager):
        """Test beacon with message too long"""
        context = mock_context_manager.get_context.return_value
        context.game_name = "VALORANT"

        long_message = "A" * 501

        with patch.object(admin_cog, 'defer_if_slash', new_callable=AsyncMock):
            await admin_cog.beacon.callback(admin_cog, mock_ctx, message=long_message)

            # Should send error
            assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_beacon_success(self, admin_cog, mock_ctx, mock_context_manager):
        """Test beacon sends successfully"""
        # Setup current context
        current_context = mock_context_manager.get_context.return_value
        current_context.game_name = "VALORANT"
        current_context.channel = mock_ctx.channel
        current_context.role_code = "<@&123>"

        # Setup target context
        target_channel = MagicMock()
        target_channel.send = AsyncMock()
        target_channel.guild.name = "Test Guild"
        target_channel.name = "valorant"

        target_context = MagicMock()
        target_context.game_name = "VALORANT"
        target_context.channel = target_channel
        target_context.role_code = "<@&456>"

        mock_context_manager.contexts = {
            123456: current_context,
            789012: target_context
        }

        with patch.object(admin_cog, 'defer_if_slash', new_callable=AsyncMock):
            await admin_cog.beacon.callback(admin_cog, mock_ctx, message="Looking for group!")

            # Should send to target channel
            target_channel.send.assert_called_once()

            # Should send success message
            assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_beacon_no_targets(self, admin_cog, mock_ctx, mock_context_manager):
        """Test beacon with no target channels"""
        context = mock_context_manager.get_context.return_value
        context.game_name = "VALORANT"
        context.channel = mock_ctx.channel

        mock_context_manager.contexts = {123456: context}

        with patch.object(admin_cog, 'defer_if_slash', new_callable=AsyncMock):
            await admin_cog.beacon.callback(admin_cog, mock_ctx, message="Looking for group!")

            # Should send info about no targets
            assert mock_ctx.send.called


class TestCommandSync:
    """Test command sync commands"""

    @pytest.mark.asyncio
    async def test_sync_guild_success(self, admin_cog, mock_ctx):
        """Test syncing commands to guild"""
        mock_cmd1 = MagicMock()
        mock_cmd1.name = "shooty"
        mock_cmd2 = MagicMock()
        mock_cmd2.name = "shootystats"

        mock_ctx.bot.tree.sync = AsyncMock(return_value=[mock_cmd1, mock_cmd2])

        await admin_cog.sync.callback(admin_cog, mock_ctx)

        # Should sync to guild
        mock_ctx.bot.tree.sync.assert_called_once_with(guild=mock_ctx.guild)

        # Should send success message
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_sync_global_success(self, admin_cog, mock_ctx):
        """Test syncing commands globally"""
        mock_cmd1 = MagicMock()
        mock_cmd1.name = "shooty"

        mock_ctx.bot.tree.sync = AsyncMock(return_value=[mock_cmd1])

        await admin_cog.sync_global.callback(admin_cog, mock_ctx)

        # Should sync globally
        mock_ctx.bot.tree.sync.assert_called_once_with()

        # Should send success message with note about delay
        assert mock_ctx.send.called
        embed = mock_ctx.send.call_args[1]['embed']
        assert '1 hour' in embed.to_dict()['fields'][1]['value']


class TestCheckCommands:
    """Test shootycheck command"""

    @pytest.mark.asyncio
    async def test_check_commands_shows_status(self, admin_cog, mock_ctx, mock_context_manager):
        """Test checking bot status"""
        # Setup bot mock with proper command mocks
        mock_cmd = MagicMock()
        mock_cmd.name = "shooty"
        mock_ctx.bot.tree.get_commands.return_value = [mock_cmd]
        mock_ctx.bot.cogs = {'AdminCommands': admin_cog}
        mock_ctx.bot.get_cog.return_value = None

        mock_guild1 = MagicMock()
        mock_guild1.member_count = 100
        mock_guild2 = MagicMock()
        mock_guild2.member_count = 200
        mock_ctx.bot.guilds = [mock_guild1, mock_guild2]
        mock_ctx.bot.latency = 0.05  # 50ms
        mock_ctx.bot.user.id = 123456789

        # Setup context
        context = mock_context_manager.get_context.return_value
        context.game_name = "VALORANT"
        context.voice_channel_id = None

        await admin_cog.check_commands.callback(admin_cog, mock_ctx)

        # Should send embed with status
        assert mock_ctx.send.called
        embed = mock_ctx.send.call_args[1]['embed']
        assert 'Bot Status Check' in embed.title

    @pytest.mark.asyncio
    async def test_check_commands_with_voice_channel(self, admin_cog, mock_ctx, mock_context_manager):
        """Test checking bot status with voice channel set"""
        # Setup bot mock
        mock_ctx.bot.tree.get_commands.return_value = []
        mock_ctx.bot.cogs = {}
        mock_ctx.bot.get_cog.return_value = None
        mock_ctx.bot.guilds = [MagicMock(member_count=100)]
        mock_ctx.bot.latency = 0.05
        mock_ctx.bot.user.id = 123456789

        # Setup voice channel
        mock_voice = MagicMock()
        mock_voice.name = "Gaming Voice"
        mock_ctx.guild.get_channel.return_value = mock_voice

        # Setup context
        context = mock_context_manager.get_context.return_value
        context.game_name = "VALORANT"
        context.voice_channel_id = 777777

        await admin_cog.check_commands.callback(admin_cog, mock_ctx)

        # Should send embed showing voice channel
        assert mock_ctx.send.called


class TestSetup:
    """Test cog setup"""

    @pytest.mark.asyncio
    async def test_setup_adds_cog(self):
        """Test that setup function adds the cog"""
        from commands.admin_commands import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        # Should add the cog
        mock_bot.add_cog.assert_called_once()
        assert isinstance(mock_bot.add_cog.call_args[0][0], AdminCommands)
