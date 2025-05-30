import logging
import sys
from typing import List, Optional
import discord
from discord.ext import commands
import asyncio

from config import (
    BOT_TOKEN, COMMAND_PREFIX, LOG_LEVEL,
    MESSAGES, APP_VERSION
)
from context_manager import context_manager
from handlers.message_formatter import DEFAULT_MSG
from handlers.reaction_handler import add_react_options
from match_tracker import get_match_tracker
from utils import log_error


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
            help_command=None  # We use custom help
        )
        
        self.match_tracker: Optional[object] = None
        self._cogs_loaded: bool = False
        
    def setup_logging(self) -> None:
        """Configure logging with proper formatting."""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=getattr(logging, LOG_LEVEL.upper()),
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('shooty_bot.log', encoding='utf-8')
            ]
        )
        
        # Reduce Discord.py logging verbosity
        discord_logger = logging.getLogger('discord')
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
        
        logging.info(f"Command sync complete: {successful_syncs} succeeded, {failed_syncs} failed")
    
    async def start_match_tracker(self) -> None:
        """Start the Valorant match tracker."""
        try:
            self.match_tracker = get_match_tracker(self)
            self.loop.create_task(self.match_tracker.start_tracking())
            logging.info("🎯 Match tracker started successfully")
        except Exception as e:
            log_error("starting match tracker", e)
            logging.warning("Bot will continue without match tracking")

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

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Global command error handler."""
        # Handle command not found for shooty commands
        if isinstance(error, commands.CommandNotFound):
            if any(ctx.message.content.startswith(prefix) for prefix in ["$shooty", "$st"]):
                await ctx.send(MESSAGES["COMMAND_NOT_FOUND"])
            return
        
        # Handle missing permissions
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
            return
        
        # Handle missing required argument
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: `{error.param.name}`")
            return
        
        # Handle bad argument
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Invalid argument: {str(error)}")
            return
        
        # Handle command on cooldown
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏱️ Command on cooldown. Try again in {error.retry_after:.1f}s")
            return
        
        # Log unhandled errors
        command_name = ctx.command.qualified_name if ctx.command else 'Unknown'
        log_error(f"executing command '{command_name}'", error)
        
        # Send generic error message
        await ctx.send("❌ An error occurred while processing this command.")

    async def load_cogs(self) -> None:
        """Load all command cogs."""
        if self._cogs_loaded:
            return
        
        cogs: List[str] = [
            'commands.session_commands',
            'commands.party_commands', 
            'commands.admin_commands',
            'commands.valorant_commands',
            'handlers.reaction_handler'
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
        if self.match_tracker and hasattr(self.match_tracker, 'stop_tracking'):
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