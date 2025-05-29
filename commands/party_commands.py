import logging
from discord.ext import commands
from context_manager import context_manager
from handlers.message_formatter import get_kicked_user_message, get_max_party_size_message
from config import *

class PartyCommands(commands.Cog):
    """Commands for managing party settings and members"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(
        name="shootykick", 
        description="Kicks user from party"
    )
    async def kick_user(self, ctx, args):
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        potential_user_names_list = [args]
        kicked_usernames_list = shooty_context.remove_user_from_everything(potential_user_names_list)
        
        await ctx.reply(get_kicked_user_message(kicked_usernames_list))
        
        # Save the context after modification
        context_manager.save_context(channel_id)
    
    @commands.hybrid_command(
        name="shootysize", 
        description="Sets party size"
    )
    async def set_session_size(self, ctx, size):
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        if size.isdigit():
            logging.info(f"Changing size to: {size}")
            new_party_max_size = int(size)
            shooty_context.set_party_max_size(new_party_max_size)
            
            # Save the context after modification
            context_manager.save_context(channel_id)
            
            await ctx.reply(get_max_party_size_message(new_party_max_size))
        else:
            await ctx.reply("Party size must be a number")
    
    async def clear_session(self, ctx):
        """Helper method for clearing session (can be exposed as command if needed)"""
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        # Backup in case of undo needed
        shooty_context.backup_state()
        
        logging.info(
            "Clearing user sets: " + 
            str([user.name for user in shooty_context.bot_soloq_user_set.union(shooty_context.bot_fullstack_user_set)])
        )
        
        shooty_context.reset_users()
        await ctx.send(MESSAGES["CLEARED_SESSION"])