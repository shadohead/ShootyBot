import logging
import discord
from discord.ext import commands
from config import *
from context_manager import context_manager
from handlers.message_formatter import DEFAULT_MSG
from handlers.reaction_handler import add_react_options

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
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} slash commands")
    except Exception as e:
        logging.error(f"Failed to sync commands: {e}")

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