import logging
import discord
from discord.ext import commands
from config import *
from context_manager import context_manager
from handlers.message_formatter import DEFAULT_MSG
from handlers.reaction_handler import add_react_options
from match_tracker import get_match_tracker

# Configure logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper()))

# Set up bot intents
intents = discord.Intents.all()
intents.members = True

# Create bot instance
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

@bot.event
async def on_ready():
    logging.info(f"We have logged in as {bot.user}")
    logging.info(f"Bot is in {len(bot.guilds)} guilds")
    
    # Sync slash commands to all guilds for immediate availability
    for guild in bot.guilds:
        try:
            synced = await bot.tree.sync(guild=guild)
            logging.info(f"Synced {len(synced)} slash commands to {guild.name}")
        except Exception as e:
            logging.error(f"Failed to sync commands to {guild.name}: {e}")
    
    # Start the match tracker
    try:
        match_tracker = get_match_tracker(bot)
        bot.loop.create_task(match_tracker.start_tracking())
        logging.info("🎯 Match tracker started successfully")
    except Exception as e:
        logging.error(f"Failed to start match tracker: {e}")
    
    logging.info("🤖 Bot is ready and all commands are synced!")

@bot.event
async def on_message(message):
    # Process commands first
    await bot.process_commands(message)
    
    # Handle special case for shooty messages (backward compatibility)
    if message.author == bot.user and message.content.startswith(DEFAULT_MSG):
        channel_id = message.channel.id
        shooty_context = context_manager.get_context(channel_id)
        shooty_context.current_st_message_id = message.id
        await add_react_options(message)

@bot.event
async def on_command_error(ctx, error):
    """Global error handler"""
    if (ctx.message.content.startswith("$shooty") or 
        ctx.message.content.startswith("$st")) and \
        isinstance(error, discord.ext.commands.errors.CommandNotFound):
        await ctx.send(MESSAGES["COMMAND_NOT_FOUND"])
    else:
        logging.error(f"Unhandled error in command {ctx.command}: {error}")

async def load_cogs():
    """Load all command cogs"""
    cogs = [
        'commands.session_commands',
        'commands.party_commands', 
        'commands.admin_commands',
        'commands.valorant_commands',
        'handlers.reaction_handler'
    ]
    
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logging.info(f"Loaded cog: {cog}")
        except Exception as e:
            logging.error(f"Failed to load cog {cog}: {e}")

async def main():
    """Main bot startup function"""
    async with bot:
        # Load all cogs
        await load_cogs()
        
        # Start the bot
        await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    import asyncio
    
    # Check if token is set
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not found!")
        print("Please set BOT_TOKEN in your environment or create a .env file")
        print("You can also copy example.DiscordConfig.py to DiscordConfig.py and update it")
        exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot shutdown requested by user")
    except Exception as e:
        logging.error(f"Bot crashed: {e}")
        raise