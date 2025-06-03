import logging
import sys
import os
import time
from typing import List, Optional
import discord
from discord.ext import commands, tasks
import asyncio

from config import BOT_TOKEN, COMMAND_PREFIX, LOG_LEVEL, MESSAGES, APP_VERSION
from context_manager import context_manager
from handlers.message_formatter import DEFAULT_MSG
from handlers.reaction_handler import add_react_options
from match_tracker import get_match_tracker
from utils import log_error
from valorant_client import get_valorant_client


class ShootyBot(commands.Bot):
    """Main bot class for ShootyBot."""

    def __init__(self):
        # Set up intents
        intents = discord.Intents.all()
        intents.members = True

        # Initialize bot
        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            help_command=None,  # We use custom help
        )

        self.match_tracker: Optional[object] = None
        self._cogs_loaded: bool = False
        self.health_check_file = ".bot_health"

    @tasks.loop(minutes=2)
    async def health_check_task(self) -> None:
        """Update health check file every 2 minutes."""
        try:
            with open(self.health_check_file, "w") as f:
                f.write(str(int(time.time())))
        except Exception as e:
            logging.error(f"Failed to update health check file: {e}")

    @health_check_task.before_loop
    async def before_health_check(self) -> None:
        """Wait until bot is ready before starting health checks."""
        await self.wait_until_ready()

    @tasks.loop(hours=6)
    async def storage_monitoring_task(self) -> None:
        """Monitor storage usage and log statistics every 6 hours."""
        try:
            valorant_client = get_valorant_client()
            stats = valorant_client.get_storage_stats()

            total_size = stats.get("total_size_mb", 0)
            logging.info(
                f"📊 Henrik storage: {stats['stored_matches']} matches, "
                f"{stats['stored_player_stats']} player stats, "
                f"{stats['stored_accounts']} accounts "
                f"({total_size:.1f}MB total)"
            )

            # Log if approaching size limits
            if stats.get("matches_size_mb", 0) > 40:  # Warn at 40MB (limit is 50MB)
                logging.warning(
                    f"⚠️ Match storage approaching limit: {stats['matches_size_mb']:.1f}MB"
                )
            if (
                stats.get("player_stats_size_mb", 0) > 16
            ):  # Warn at 16MB (limit is 20MB)
                logging.warning(
                    f"⚠️ Player stats storage approaching limit: {stats['player_stats_size_mb']:.1f}MB"
                )

        except Exception as e:
            logging.error(f"Failed to monitor storage: {e}")

    @storage_monitoring_task.before_loop
    async def before_storage_monitoring(self) -> None:
        """Wait until bot is ready before starting storage monitoring."""
        await self.wait_until_ready()

    def setup_logging(self) -> None:
        """Configure logging with proper formatting."""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        logging.basicConfig(
            level=getattr(logging, LOG_LEVEL.upper()),
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler("shooty_bot.log", encoding="utf-8"),
            ],
        )

        # Reduce Discord.py logging verbosity
        discord_logger = logging.getLogger("discord")
        discord_logger.setLevel(logging.INFO)

    async def setup_hook(self) -> None:
        """Called when bot is setting up."""
        await self.load_cogs()

    async def on_ready(self) -> None:
        """Called when bot is ready."""
        logging.info(f"Bot logged in as {self.user} (ID: {self.user.id})")
        logging.info(f"Connected to {len(self.guilds)} guilds")
        logging.info(f"ShootyBot v{APP_VERSION} is starting up...")

        # Set bot presence
        await self.change_presence(
            activity=discord.Game(name=f"{COMMAND_PREFIX}shooty | v{APP_VERSION}")
        )

        # Sync commands
        await self.sync_commands()

        # Start match tracker
        await self.start_match_tracker()

        # Start health check task
        if not self.health_check_task.is_running():
            self.health_check_task.start()
            logging.info("💗 Health monitoring started")

        # Start storage monitoring task
        if not self.storage_monitoring_task.is_running():
            self.storage_monitoring_task.start()
            logging.info("📊 Storage monitoring started")

        logging.info("🤖 ShootyBot is fully operational!")

    async def sync_commands(self) -> None:
        """Sync slash commands to all guilds."""
        successful_syncs = 0
        failed_syncs = 0

        for guild in self.guilds:
            try:
                synced = await self.tree.sync(guild=guild)
                logging.info(f"Synced {len(synced)} commands to {guild.name}")
                successful_syncs += 1
            except Exception as e:
                log_error(f"syncing commands to {guild.name}", e)
                failed_syncs += 1

        # Also sync globally for DMs
        try:
            global_synced = await self.tree.sync()
            logging.info(f"Synced {len(global_synced)} commands globally")
        except Exception as e:
            log_error("syncing global commands", e)

        logging.info(
            f"Command sync complete: {successful_syncs} succeeded, {failed_syncs} failed"
        )

    async def start_match_tracker(self) -> None:
        """Start the Valorant match tracker."""
        try:
            self.match_tracker = get_match_tracker(self)
            self.loop.create_task(self.match_tracker.start_tracking())
            logging.info("🎯 Match tracker started successfully")
        except Exception as e:
            log_error("starting match tracker", e)
            logging.warning("Bot will continue without match tracking")

    async def update_status_with_queue_count(self) -> None:
        """Update bot status with total queue count and voice chat users across all channels."""
        try:
            total_queued = 0
            total_voice = 0
            total_max_size = 0
            active_channels = 0

            # Calculate total across all active contexts
            for context in context_manager.contexts.values():
                unique_count = context.get_unique_user_count()
                if unique_count > 0:
                    total_queued += unique_count
                    total_max_size += context.get_party_max_size()
                    active_channels += 1
                
                # Count users in voice channel for this context
                voice_count = context.get_voice_channel_user_count()
                total_voice += voice_count

            # Update status based on queue state
            if total_queued > 0:
                if total_voice > 0:
                    activity = discord.Game(
                        name=f"{total_queued} queued, {total_voice} in voice | {COMMAND_PREFIX}shooty"
                    )
                else:
                    activity = discord.Game(
                        name=f"{total_queued} queued | {COMMAND_PREFIX}shooty"
                    )
            elif total_voice > 0:
                activity = discord.Game(
                    name=f"{total_voice} in voice | {COMMAND_PREFIX}shooty"
                )
            else:
                activity = discord.Game(name=f"{COMMAND_PREFIX}shooty | v{APP_VERSION}")

            await self.change_presence(activity=activity)

        except Exception as e:
            log_error("updating bot status", e)

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming messages."""
        # Ignore DMs for now
        if message.guild is None:
            return

        # Process commands first
        await self.process_commands(message)

        # Handle special case for bot's own shooty messages (backward compatibility)
        if message.author == self.user and message.content.startswith(DEFAULT_MSG):
            await self.handle_shooty_message(message)

    async def handle_shooty_message(self, message: discord.Message) -> None:
        """Handle bot's own shooty messages for reaction setup."""
        try:
            channel_id = message.channel.id
            shooty_context = context_manager.get_context(channel_id)
            shooty_context.current_st_message_id = message.id
            await add_react_options(message)
        except Exception as e:
            log_error("handling shooty message", e)

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Global command error handler."""
        # Handle command not found for shooty commands
        if isinstance(error, commands.CommandNotFound):
            if any(
                ctx.message.content.startswith(prefix) for prefix in ["$shooty", "$st"]
            ):
                await ctx.send(MESSAGES["COMMAND_NOT_FOUND"])
            return

        # Helper function to safely send messages
        async def safe_send(message: str):
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    if not ctx.interaction.response.is_done():
                        await ctx.send(message)
                else:
                    await ctx.send(message)
            except discord.HTTPException:
                pass

        # Handle missing permissions
        if isinstance(error, commands.MissingPermissions):
            await safe_send("❌ You don't have permission to use this command.")
            return

        # Handle missing required argument
        if isinstance(error, commands.MissingRequiredArgument):
            await safe_send(f"❌ Missing required argument: `{error.param.name}`")
            return

        # Handle bad argument
        if isinstance(error, commands.BadArgument):
            await safe_send(f"❌ Invalid argument: {str(error)}")
            return

        # Handle command on cooldown
        if isinstance(error, commands.CommandOnCooldown):
            await safe_send(f"⏱️ Command on cooldown. Try again in {error.retry_after:.1f}s")
            return

        # Log unhandled errors
        command_name = ctx.command.qualified_name if ctx.command else "Unknown"
        log_error(f"executing command '{command_name}'", error)

        # Send generic error message only if interaction hasn't been handled
        await safe_send("❌ An error occurred while processing this command.")

    async def load_cogs(self) -> None:
        """Load all command cogs."""
        if self._cogs_loaded:
            return

        cogs: List[str] = [
            "commands.session_commands",
            "commands.party_commands",
            "commands.admin_commands",
            "commands.valorant_commands",
            "handlers.reaction_handler",
        ]

        loaded = 0
        failed = 0

        for cog in cogs:
            try:
                await self.load_extension(cog)
                logging.info(f"✅ Loaded cog: {cog}")
                loaded += 1
            except Exception as e:
                log_error(f"loading cog {cog}", e)
                failed += 1

        self._cogs_loaded = True
        logging.info(f"Cog loading complete: {loaded} loaded, {failed} failed")

        if failed > 0 and loaded == 0:
            raise RuntimeError("Failed to load any cogs")

    async def close(self) -> None:
        """Gracefully shut down the bot."""
        logging.info("Shutting down ShootyBot...")

        # Stop match tracker if running
        if self.match_tracker and hasattr(self.match_tracker, "stop_tracking"):
            self.match_tracker.stop_tracking()
            logging.info("Match tracker stopped")

        # Save any pending data
        try:
            context_manager.save_all_contexts()
            logging.info("All contexts saved")
        except Exception as e:
            log_error("saving contexts during shutdown", e)

        await super().close()
        logging.info("ShootyBot shutdown complete")


async def main() -> None:
    """Main bot startup function."""
    # Check for existing bot instances
    import psutil
    import os
    current_pid = os.getpid()
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Skip current process
            if proc.info['pid'] == current_pid:
                continue
                
            # Check if it's a Python process running bot.py
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                if proc.info['cmdline'] and any('bot.py' in arg for arg in proc.info['cmdline']):
                    print(f"\n⚠️  Another bot instance is already running (PID: {proc.info['pid']})")
                    print("Run './run_python_script.sh --start' to restart the bot properly")
                    sys.exit(1)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    bot = ShootyBot()
    bot.setup_logging()

    async with bot:
        await bot.start(BOT_TOKEN)


def check_requirements() -> bool:
    """Check if all requirements are met."""
    if not BOT_TOKEN:
        print("\n❌ Error: BOT_TOKEN not found!")
        print("\nPlease configure the bot token using one of these methods:")
        print("  1. Set BOT_TOKEN environment variable")
        print("  2. Create a .env file with BOT_TOKEN=your_token_here")
        print("  3. Copy example.DiscordConfig.py to DiscordConfig.py and update it")
        print("\nFor more information, see the README.md file.")
        return False

    if not COMMAND_PREFIX:
        print("\n❌ Error: COMMAND_PREFIX not configured!")
        return False

    return True


if __name__ == "__main__":
    # Check requirements
    if not check_requirements():
        sys.exit(1)

    # Print startup banner
    print(f"\n🤖 ShootyBot v{APP_VERSION}")
    print(f"Command Prefix: {COMMAND_PREFIX}")
    print(f"Log Level: {LOG_LEVEL}")
    print("Starting up...\n")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot shutdown requested by user")
    except Exception as e:
        print(f"\n💥 Bot crashed: {e}")
        logging.exception("Fatal error:")
        sys.exit(1)
