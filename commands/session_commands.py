import logging
import asyncio
from datetime import datetime
import pytz
from dateutil import parser
from discord.ext import commands
from context_manager import context_manager
from handlers.message_formatter import get_ping_shooty_message, party_status_message
from handlers.reaction_handler import add_react_options
from data_manager import data_manager
from config import *

class SessionCommands(commands.Cog):
    """Commands for managing party sessions"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(
        name="st", 
        description="Starts a Fresh Shooty Session (FSS™)"
    )
    async def start_session(self, ctx):
        logging.info("Starting new shooty session")
        
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        # End previous session if one exists
        if hasattr(shooty_context, 'current_session_id') and shooty_context.current_session_id:
            await self._end_current_session(shooty_context)
        
        # Create new session in data manager
        session = data_manager.create_session(
            channel_id=channel_id,
            started_by=ctx.author.id,
            game_name=shooty_context.game_name
        )
        session.party_size = shooty_context.party_max_size
        
        # Store session reference in context
        shooty_context.current_session_id = session.session_id
        
        # Backup current state for restore functionality
        shooty_context.backup_state()
        
        # Reset users
        shooty_context.reset_users()
        
        # Send ping message
        response_string = get_ping_shooty_message(shooty_context.role_code)
        message = await ctx.send(response_string)
        
        # Track the message for reactions
        shooty_context.current_st_message_id = message.id
        
        # Add reaction options
        await add_react_options(message)
        
        # Save the context and session
        context_manager.save_context(channel_id)
        data_manager.save_session(session.session_id)
        
        # Update user stats for session starter
        user_data = data_manager.get_user(ctx.author.id)
        user_data.increment_session_count()
        user_data.add_session_to_history(session.session_id)
        data_manager.save_user(ctx.author.id)
    
    @commands.hybrid_command(
        name="sts", 
        description="Prints party status"
    )
    async def session_status(self, ctx):
        logging.info("Printing Status")
        
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        status_message = party_status_message(ctx.channel, shooty_context)
        await ctx.reply(status_message)
    
    @commands.hybrid_command(
        name="stm", 
        description="Mentions everyone in the party"
    )
    async def mention_session(self, ctx):
        logging.info("Mentioning everyone in the party.")
        
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        if not shooty_context.bot_soloq_user_set and not shooty_context.bot_fullstack_user_set:
            await ctx.send(MESSAGES["NO_MEMBERS"])
            return
        
        mention_message = "".join(
            user.mention + " "
            for user in shooty_context.bot_soloq_user_set.union(shooty_context.bot_fullstack_user_set)
            if not user.bot
        )
        
        await ctx.send(mention_message)
    
    @commands.hybrid_command(
        name="shootyrestore",
        description="Restores party to the previous state before it got reset"
    )
    async def restore_session(self, ctx):
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        # Restore backup
        shooty_context.restore_state()
        
        logging.info(
            "Restoring shooty_context: " + 
            str([user.name for user in shooty_context.bot_soloq_user_set.union(shooty_context.bot_fullstack_user_set)])
        )
        
        await ctx.channel.send(MESSAGES["RESTORED_SESSION"])
        await ctx.reply(party_status_message(ctx.channel, shooty_context))
    
    @commands.hybrid_command(
        name="shootytime",
        description="Schedule a time to ping the group. You must specify AM/PM or input the time as military time."
    )
    async def scheduled_session(self, ctx, game_time):
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        try:
            scheduled_time = parser.parse(game_time)
            
            # Create timezone objects
            old_timezone = pytz.timezone("US/Pacific")
            new_timezone = pytz.timezone("UTC")
            
            # Convert input time to UTC
            localized_timestamp = old_timezone.localize(scheduled_time)
            utc_scheduled_time = localized_timestamp.astimezone(new_timezone)
            
            seconds_to_wait = (utc_scheduled_time - datetime.now(pytz.UTC)).total_seconds()
            
            if seconds_to_wait < 0:
                await ctx.send(MESSAGES["PAST_TIME"])
                return
            elif seconds_to_wait > MAX_SCHEDULED_HOURS * 3600:  # Convert hours to seconds
                await ctx.send(MESSAGES["TOO_FAR_FUTURE"])
                return
            
            message = await ctx.send(f"Shooty at {scheduled_time.strftime('%I:%M %p')}?")
            await self.start_session(ctx)
            await asyncio.sleep(seconds_to_wait)
            
            await ctx.send(f"Shooty time now! - {scheduled_time.strftime('%I:%M %p')}")
            await ctx.reply(party_status_message(ctx.channel, shooty_context))
            
        except ValueError:
            await ctx.send(MESSAGES["INVALID_TIME"])
    
    @commands.hybrid_command(
        name="shootyhelp", 
        description="Show commands help message"
    )
    async def show_help(self, ctx):
        await ctx.reply(MESSAGES["HELP_MESSAGE"])
    
    @commands.hybrid_command(
        name="stend",
        description="End the current session"
    )
    async def end_session(self, ctx):
        """End the current session"""
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        if hasattr(shooty_context, 'current_session_id') and shooty_context.current_session_id:
            await self._end_current_session(shooty_context)
            await ctx.send("✅ Session ended and stats recorded!")
        else:
            await ctx.send("❌ No active session to end.")
    
    async def _end_current_session(self, shooty_context):
        """Helper method to end the current session"""
        if not hasattr(shooty_context, 'current_session_id') or not shooty_context.current_session_id:
            return
        
        session_id = shooty_context.current_session_id
        session = data_manager.sessions.get(session_id)
        
        if session:
            # Add all current participants to the session
            all_users = shooty_context.bot_soloq_user_set.union(shooty_context.bot_fullstack_user_set)
            for user in all_users:
                session.add_participant(user.id)
                # Update user stats
                user_data = data_manager.get_user(user.id)
                user_data.add_session_to_history(session_id)
                data_manager.save_user(user.id)
            
            # Check if party was full
            if len(all_users) >= shooty_context.party_max_size:
                session.was_full = True
            
            # End the session
            session.end_session()
            data_manager.save_session(session_id)
            
            logging.info(f"Ended session {session_id} with {len(all_users)} participants")
        
        # Clear session reference
        shooty_context.current_session_id = None

async def setup(bot):
    await bot.add_cog(SessionCommands(bot))