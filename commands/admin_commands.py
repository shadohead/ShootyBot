import logging
from discord.ext import commands
from context_manager import context_manager
from config import *

class AdminCommands(commands.Cog):
    """Administrative commands for channel configuration"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(
        name="shootysetrole", 
        description="Set a role for the bot to ping"
    )
    async def set_role_code(self, ctx, role_code):
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        shooty_context.role_code = role_code
        
        # Save the context
        context_manager.save_context(channel_id)
        
        await ctx.send(f"Set this channel's role code for pings to {role_code}")
    
    @commands.hybrid_command(
        name="shootysetgame", 
        description="Set the game name for LFG features"
    )
    async def set_game_name(self, ctx, game_name):
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        shooty_context.game_name = game_name.upper()
        shooty_context.channel = ctx.channel
        
        # Save the context
        context_manager.save_context(channel_id)
        
        await ctx.send(f"Set this channel's game for LFG to {shooty_context.game_name}")
    
    @commands.hybrid_command(
        name="shootylfg",
        description="Ping all channels cross-server playing the same game as this one"
    )
    async def lfg(self, ctx):
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        if shooty_context.game_name is None:
            await ctx.send(MESSAGES["NEED_GAME_NAME"])
            return
        
        lobby_members_str = ""
        for context in context_manager.contexts.values():
            if context.game_name == shooty_context.game_name:
                lobby_members_str += f"{context.get_user_list_string_with_hashtag()}\n"
        
        await ctx.send(
            f"Cross channel users queued for {shooty_context.game_name}:\n{lobby_members_str}"
        )
    
    @commands.hybrid_command(
        name="shootybeacon",
        description="Sends a cross-server message to others playing the same game"
    )
    async def beacon(self, ctx, message):
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        if shooty_context.game_name is None:
            await ctx.send(MESSAGES["NEED_GAME_NAME"])
            return
        
        channels_pinged_str = ""
        for context in context_manager.contexts.values():
            if (context.game_name == shooty_context.game_name and 
                context.channel is not shooty_context.channel):
                
                await context.channel.send(
                    f"{context.role_code}\n{message}\n"
                    f"Sent from Server: *{shooty_context.channel.guild.name}*\n"
                    f"Channel: *{shooty_context.channel.name}*"
                )
                channels_pinged_str += f"Server: *{context.channel.guild.name}*, Channel: *{context.channel.name}*\n"
        
        await ctx.send(f"Sent beacon message to {channels_pinged_str}")
    
    @commands.command(name="shootysync")
    async def sync(self, ctx) -> None:
        """Sync slash commands to the current guild"""
        synced = await ctx.bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} commands to the current guild.")

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))