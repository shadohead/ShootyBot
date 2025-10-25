"""Tests for bot.py main bot functionality"""
import pytest
import asyncio
import os
from unittest.mock import Mock, MagicMock, patch, AsyncMock, call
import discord
from discord.ext import commands

# Import bot components
from bot import ShootyBot, main, check_requirements


class TestShootyBotInit:
    """Test ShootyBot initialization"""

    def test_init_sets_correct_attributes(self):
        """Test that bot initializes with correct attributes"""
        bot = ShootyBot()

        assert bot.match_tracker is None
        assert bot._cogs_loaded is False
        assert bot.health_check_file == ".bot_health"
        assert bot.command_prefix is not None

    def test_init_sets_all_intents(self):
        """Test that bot has all intents enabled"""
        bot = ShootyBot()
        # Bot should have intents configured
        assert bot.intents is not None


class TestHealthCheckTask:
    """Test health check functionality"""

    @pytest.mark.asyncio
    async def test_health_check_creates_file(self):
        """Test that health check creates/updates the health file"""
        bot = ShootyBot()

        # Mock the file operations
        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            await bot.health_check_task()

            mock_open.assert_called_once_with(".bot_health", "w")
            # Should write a timestamp
            assert mock_file.write.called

    @pytest.mark.asyncio
    async def test_health_check_handles_errors(self):
        """Test that health check handles file errors gracefully"""
        bot = ShootyBot()

        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            with patch('logging.error') as mock_log:
                # Should not raise exception
                await bot.health_check_task()
                mock_log.assert_called()


class TestStorageMonitoring:
    """Test storage monitoring task"""

    @pytest.mark.asyncio
    async def test_storage_monitoring_logs_stats(self):
        """Test that storage monitoring logs statistics"""
        bot = ShootyBot()

        mock_stats = {
            'stored_matches': 100,
            'stored_player_stats': 50,
            'stored_accounts': 25,
            'total_size_mb': 5.5,
            'matches_size_mb': 3.0,
            'player_stats_size_mb': 2.0
        }

        with patch('bot.get_valorant_client') as mock_client:
            mock_valorant = MagicMock()
            mock_valorant.get_storage_stats.return_value = mock_stats
            mock_client.return_value = mock_valorant

            with patch('logging.info') as mock_log:
                await bot.storage_monitoring_task()

                # Should log storage stats
                assert mock_log.called
                log_message = str(mock_log.call_args[0][0])
                assert '100 matches' in log_message
                assert '50 player stats' in log_message

    @pytest.mark.asyncio
    async def test_storage_monitoring_warns_on_high_usage(self):
        """Test that storage monitoring warns when approaching limits"""
        bot = ShootyBot()

        mock_stats = {
            'stored_matches': 1000,
            'stored_player_stats': 500,
            'stored_accounts': 250,
            'total_size_mb': 100.0,
            'matches_size_mb': 55.0,  # Above default 50MB limit
            'player_stats_size_mb': 25.0
        }

        with patch('bot.get_valorant_client') as mock_client:
            mock_valorant = MagicMock()
            mock_valorant.get_storage_stats.return_value = mock_stats
            mock_client.return_value = mock_valorant

            with patch('logging.warning') as mock_warn:
                await bot.storage_monitoring_task()

                # Should log warning (check for either match or player stats warning)
                assert mock_warn.called
                warning_message = str(mock_warn.call_args[0][0])
                assert 'approaching limit' in warning_message


class TestSetupLogging:
    """Test logging configuration"""

    def test_setup_logging_configures_handlers(self):
        """Test that logging is configured with file and stream handlers"""
        bot = ShootyBot()

        with patch('logging.basicConfig') as mock_config:
            with patch('logging.getLogger') as mock_logger:
                mock_discord_logger = MagicMock()
                mock_logger.return_value = mock_discord_logger

                bot.setup_logging()

                # Should configure basic logging
                assert mock_config.called

                # Should set Discord logger level
                mock_discord_logger.setLevel.assert_called_once_with(20)  # INFO level


class TestCogLoading:
    """Test cog loading functionality"""

    @pytest.mark.asyncio
    async def test_load_cogs_loads_all_cogs(self):
        """Test that all cogs are loaded"""
        bot = ShootyBot()

        with patch.object(bot, 'load_extension', new_callable=AsyncMock) as mock_load:
            with patch('logging.info'):
                await bot.load_cogs()

                # Should load all 5 cogs
                assert mock_load.call_count == 5

                # Verify cog names
                loaded_cogs = [call[0][0] for call in mock_load.call_args_list]
                assert "commands.session_commands" in loaded_cogs
                assert "commands.party_commands" in loaded_cogs
                assert "commands.admin_commands" in loaded_cogs
                assert "commands.valorant_commands" in loaded_cogs
                assert "handlers.reaction_handler" in loaded_cogs

    @pytest.mark.asyncio
    async def test_load_cogs_sets_flag(self):
        """Test that cog loading sets the loaded flag"""
        bot = ShootyBot()

        with patch.object(bot, 'load_extension', new_callable=AsyncMock):
            with patch('logging.info'):
                await bot.load_cogs()

                assert bot._cogs_loaded is True

    @pytest.mark.asyncio
    async def test_load_cogs_only_loads_once(self):
        """Test that cogs are only loaded once"""
        bot = ShootyBot()

        with patch.object(bot, 'load_extension', new_callable=AsyncMock) as mock_load:
            with patch('logging.info'):
                await bot.load_cogs()
                await bot.load_cogs()  # Second call

                # Should only load once
                assert mock_load.call_count == 5

    @pytest.mark.asyncio
    async def test_load_cogs_handles_errors(self):
        """Test that cog loading handles errors gracefully"""
        bot = ShootyBot()

        # Make one cog fail to load
        async def load_with_error(cog_name):
            if cog_name == "commands.admin_commands":
                raise Exception("Failed to load")

        with patch.object(bot, 'load_extension', side_effect=load_with_error):
            with patch('logging.info'):
                with patch('bot.log_error') as mock_error:
                    # Should not raise exception
                    await bot.load_cogs()

                    # Should log error
                    assert mock_error.called

    @pytest.mark.asyncio
    async def test_load_cogs_raises_if_all_fail(self):
        """Test that bot raises error if all cogs fail to load"""
        bot = ShootyBot()

        with patch.object(bot, 'load_extension', new_callable=AsyncMock, side_effect=Exception("Failed")):
            with patch('logging.info'):
                with patch('bot.log_error'):
                    with pytest.raises(RuntimeError, match="Failed to load any cogs"):
                        await bot.load_cogs()


class TestCommandSync:
    """Test command synchronization"""

    @pytest.mark.asyncio
    async def test_sync_commands_to_all_guilds(self):
        """Test that commands are synced to all guilds"""
        bot = ShootyBot()

        # Create mock guilds
        guild1 = MagicMock(name="Guild1")
        guild2 = MagicMock(name="Guild2")

        # Mock tree.sync
        mock_synced_commands = [MagicMock(), MagicMock()]
        bot.tree = MagicMock()
        bot.tree.sync = AsyncMock(return_value=mock_synced_commands)

        # Patch the guilds property
        with patch.object(commands.Bot, 'guilds', new=[guild1, guild2]):
            with patch('logging.info'):
                await bot.sync_commands()

                # Should sync to both guilds + global
                assert bot.tree.sync.call_count == 3

    @pytest.mark.asyncio
    async def test_sync_commands_handles_guild_errors(self):
        """Test that command sync handles individual guild errors"""
        bot = ShootyBot()

        guild1 = MagicMock(name="Guild1")
        guild2 = MagicMock(name="Guild2")

        # Make sync fail for first guild
        async def sync_with_error(guild=None):
            if guild == guild1:
                raise Exception("Sync failed")
            return []

        bot.tree = MagicMock()
        bot.tree.sync = AsyncMock(side_effect=sync_with_error)

        # Patch the guilds property
        with patch.object(commands.Bot, 'guilds', new=[guild1, guild2]):
            with patch('logging.info'):
                with patch('bot.log_error') as mock_error:
                    # Should not raise exception
                    await bot.sync_commands()

                    # Should log error for failed guild
                    assert mock_error.called


class TestMatchTracker:
    """Test match tracker initialization"""

    @pytest.mark.asyncio
    async def test_start_match_tracker_success(self):
        """Test that match tracker starts successfully"""
        bot = ShootyBot()
        bot.loop = asyncio.get_event_loop()

        mock_tracker = MagicMock()
        mock_tracker.start_tracking = AsyncMock()

        with patch('bot.get_match_tracker', return_value=mock_tracker):
            with patch('logging.info'):
                await bot.start_match_tracker()

                assert bot.match_tracker == mock_tracker

    @pytest.mark.asyncio
    async def test_start_match_tracker_handles_errors(self):
        """Test that match tracker handles errors gracefully"""
        bot = ShootyBot()
        bot.loop = asyncio.get_event_loop()

        with patch('bot.get_match_tracker', side_effect=Exception("Tracker failed")):
            with patch('logging.warning') as mock_warn:
                with patch('bot.log_error'):
                    # Should not raise exception
                    await bot.start_match_tracker()

                    # Should log warning
                    assert mock_warn.called


class TestStatusUpdate:
    """Test bot status updates"""

    @pytest.mark.asyncio
    async def test_update_status_with_queued_users(self):
        """Test that status updates with queue count"""
        bot = ShootyBot()

        # Mock context manager with queued users
        mock_context = MagicMock()
        mock_context.get_unique_user_count.return_value = 5
        mock_context.get_party_max_size.return_value = 5
        mock_context.get_voice_channel_user_count.return_value = 0

        with patch('bot.context_manager') as mock_cm:
            mock_cm.contexts.values.return_value = [mock_context]

            bot.change_presence = AsyncMock()

            await bot.update_status_with_queue_count()

            # Should update presence with queue count
            assert bot.change_presence.called
            activity = bot.change_presence.call_args[1]['activity']
            assert '5 queued' in activity.name

    @pytest.mark.asyncio
    async def test_update_status_with_voice_users(self):
        """Test that status includes voice chat count"""
        bot = ShootyBot()

        mock_context = MagicMock()
        mock_context.get_unique_user_count.return_value = 0
        mock_context.get_party_max_size.return_value = 5
        mock_context.get_voice_channel_user_count.return_value = 3

        with patch('bot.context_manager') as mock_cm:
            mock_cm.contexts.values.return_value = [mock_context]

            bot.change_presence = AsyncMock()

            await bot.update_status_with_queue_count()

            # Should update presence with voice count
            assert bot.change_presence.called
            activity = bot.change_presence.call_args[1]['activity']
            assert '3 in voice' in activity.name


class TestMessageHandling:
    """Test message handling"""

    @pytest.mark.asyncio
    async def test_on_message_ignores_dms(self):
        """Test that DMs are ignored"""
        bot = ShootyBot()

        mock_message = MagicMock()
        mock_message.guild = None  # DM message

        bot.process_commands = AsyncMock()

        await bot.on_message(mock_message)

        # Should not process commands for DMs
        bot.process_commands.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_processes_commands(self):
        """Test that guild messages are processed"""
        bot = ShootyBot()

        mock_message = MagicMock()
        mock_message.guild = MagicMock()  # Guild message
        mock_message.author = MagicMock()
        mock_message.content = "$help"

        bot.process_commands = AsyncMock()

        # Mock user property
        with patch.object(type(bot), 'user', new_callable=lambda: property(lambda self: MagicMock())):
            await bot.on_message(mock_message)

            # Should process commands
            bot.process_commands.assert_called_once_with(mock_message)


class TestErrorHandling:
    """Test command error handling"""

    @pytest.mark.asyncio
    async def test_command_not_found_for_shooty_commands(self):
        """Test that command not found is handled for shooty commands"""
        bot = ShootyBot()

        mock_ctx = MagicMock()
        mock_ctx.message.content = "$shooty invalid"
        mock_ctx.send = AsyncMock()

        error = commands.CommandNotFound()

        await bot.on_command_error(mock_ctx, error)

        # Should send command not found message
        assert mock_ctx.send.called

    @pytest.mark.asyncio
    async def test_missing_permissions_error(self):
        """Test that missing permissions error is handled"""
        bot = ShootyBot()

        mock_ctx = MagicMock()
        mock_ctx.send = AsyncMock()
        mock_ctx.interaction = None

        error = commands.MissingPermissions(['administrator'])

        await bot.on_command_error(mock_ctx, error)

        # Should send permissions error
        assert mock_ctx.send.called
        assert 'permission' in str(mock_ctx.send.call_args[0][0]).lower()

    @pytest.mark.asyncio
    async def test_missing_required_argument_error(self):
        """Test that missing argument error is handled"""
        bot = ShootyBot()

        mock_ctx = MagicMock()
        mock_ctx.send = AsyncMock()
        mock_ctx.interaction = None

        # Create a proper parameter object
        param = MagicMock()
        param.name = "test_param"
        error = commands.MissingRequiredArgument(param)

        await bot.on_command_error(mock_ctx, error)

        # Should send missing argument message
        assert mock_ctx.send.called
        assert 'test_param' in str(mock_ctx.send.call_args[0][0])


class TestBotShutdown:
    """Test bot shutdown"""

    @pytest.mark.asyncio
    async def test_close_stops_match_tracker(self):
        """Test that bot close stops match tracker"""
        bot = ShootyBot()

        mock_tracker = MagicMock()
        mock_tracker.stop_tracking = MagicMock()
        bot.match_tracker = mock_tracker

        with patch.object(commands.Bot, 'close', new_callable=AsyncMock):
            with patch('bot.context_manager') as mock_cm:
                mock_cm.save_all_contexts = MagicMock()
                with patch('logging.info'):
                    await bot.close()

                    # Should stop tracker
                    mock_tracker.stop_tracking.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_saves_contexts(self):
        """Test that bot close saves all contexts"""
        bot = ShootyBot()
        bot.match_tracker = None

        with patch.object(commands.Bot, 'close', new_callable=AsyncMock):
            with patch('bot.context_manager') as mock_cm:
                mock_cm.save_all_contexts = MagicMock()
                with patch('logging.info'):
                    await bot.close()

                    # Should save contexts
                    mock_cm.save_all_contexts.assert_called_once()


class TestRequirements:
    """Test requirement checking"""

    def test_check_requirements_with_token(self):
        """Test that requirements pass with valid token"""
        with patch('bot.BOT_TOKEN', 'valid_token_here'):
            with patch('bot.COMMAND_PREFIX', '$'):
                result = check_requirements()
                assert result is True

    def test_check_requirements_without_token(self):
        """Test that requirements fail without token"""
        with patch('bot.BOT_TOKEN', None):
            with patch('builtins.print'):
                result = check_requirements()
                assert result is False

    def test_check_requirements_without_prefix(self):
        """Test that requirements fail without command prefix"""
        with patch('bot.BOT_TOKEN', 'valid_token'):
            with patch('bot.COMMAND_PREFIX', None):
                with patch('builtins.print'):
                    result = check_requirements()
                    assert result is False
