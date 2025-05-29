import logging
import discord
from discord.ext import commands
from valorant_client import valorant_client
from data_manager import data_manager
from datetime import datetime, timezone

class ValorantCommands(commands.Cog):
    """Commands for Valorant integration and account management"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(
        name="vlink",
        description="Link your Valorant account (e.g., /vlink username tag)"
    )
    async def link_valorant(self, ctx, username: str, tag: str):
        """Link a Valorant account to Discord user"""
        await ctx.defer()
        
        logging.info(f"Linking Valorant account {username}#{tag} for user {ctx.author.id}")
        
        result = await valorant_client.link_account(ctx.author.id, username, tag)
        
        if result['success']:
            embed = discord.Embed(
                title="✅ Valorant Account Linked",
                description=f"Successfully linked **{result['username']}#{result['tag']}**",
                color=0x00ff00
            )
            
            # Add player card if available
            if result.get('card', {}).get('large'):
                embed.set_thumbnail(url=result['card']['large'])
            
            await ctx.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Link Failed",
                description=f"Could not link account: {result['error']}",
                color=0xff0000
            )
            await ctx.followup.send(embed=embed)
    
    @commands.hybrid_command(
        name="vunlink",
        description="Unlink your Valorant account"
    )
    async def unlink_valorant(self, ctx):
        """Unlink Valorant account from Discord user"""
        success = await valorant_client.unlink_account(ctx.author.id)
        
        if success:
            embed = discord.Embed(
                title="✅ Account Unlinked",
                description="Your Valorant account has been unlinked",
                color=0x00ff00
            )
        else:
            embed = discord.Embed(
                title="❌ Unlink Failed",
                description="Could not unlink your account",
                color=0xff0000
            )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="vwho",
        description="Show who is currently playing Valorant in this server"
    )
    async def who_playing(self, ctx):
        """Show members currently playing Valorant"""
        playing_members = valorant_client.get_playing_members(ctx.guild)
        
        if not playing_members:
            embed = discord.Embed(
                title="🎮 Valorant Players",
                description="No one is currently playing Valorant",
                color=0x808080
            )
        else:
            # Create list of playing members with their linked accounts
            player_list = []
            for member in playing_members:
                linked_account = valorant_client.get_linked_account(member.id)
                if linked_account:
                    player_list.append(f"🎯 **{member.display_name}** ({linked_account['username']}#{linked_account['tag']})")
                else:
                    player_list.append(f"🎯 **{member.display_name}** (no linked account)")
            
            embed = discord.Embed(
                title="🎮 Currently Playing Valorant",
                description="\n".join(player_list),
                color=0xff4655
            )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="vstats",
        description="Show your Shooty session stats"
    )
    async def valorant_stats(self, ctx, member: discord.Member = None):
        """Show user's session statistics"""
        target_user = member or ctx.author
        user_data = data_manager.get_user(target_user.id)
        
        # Get linked account info
        linked_account = valorant_client.get_linked_account(target_user.id)
        
        # Get recent sessions
        recent_sessions = data_manager.get_user_sessions(target_user.id, limit=5)
        
        embed = discord.Embed(
            title=f"📊 Stats for {target_user.display_name}",
            color=0xff4655
        )
        
        # Add linked account info
        if linked_account:
            embed.add_field(
                name="🎯 Linked Valorant Account",
                value=f"{linked_account['username']}#{linked_account['tag']}",
                inline=False
            )
        else:
            embed.add_field(
                name="🎯 Valorant Account",
                value="Not linked (use `/vlink` to link)",
                inline=False
            )
        
        # Add session stats
        embed.add_field(
            name="📈 Session Stats",
            value=f"Total Sessions: **{user_data.total_sessions}**\nGames Played: **{user_data.total_games_played}**",
            inline=True
        )
        
        # Add playing status
        if valorant_client.is_playing_valorant(target_user):
            embed.add_field(
                name="🎮 Current Status",
                value="**Currently Playing Valorant!**",
                inline=True
            )
        
        # Add recent sessions
        if recent_sessions:
            session_list = []
            for session in recent_sessions[:3]:
                start_time = datetime.fromisoformat(session.start_time)
                formatted_time = start_time.strftime("%m/%d %H:%M")
                participants_count = len(session.participants)
                if session.end_time:
                    session_list.append(f"• {formatted_time} - {participants_count} players ({session.duration_minutes}m)")
                else:
                    session_list.append(f"• {formatted_time} - {participants_count} players (ongoing)")
            
            embed.add_field(
                name="📋 Recent Sessions",
                value="\n".join(session_list) or "No recent sessions",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="vhistory",
        description="Show session history for this channel"
    )
    async def session_history(self, ctx, limit: int = 5):
        """Show recent session history for the channel"""
        if limit > 10:
            limit = 10
        
        recent_sessions = data_manager.get_channel_sessions(ctx.channel.id, limit)
        
        if not recent_sessions:
            embed = discord.Embed(
                title="📋 Session History",
                description="No sessions found for this channel",
                color=0x808080
            )
        else:
            embed = discord.Embed(
                title=f"📋 Recent Sessions ({len(recent_sessions)})",
                color=0xff4655
            )
            
            for i, session in enumerate(recent_sessions):
                start_time = datetime.fromisoformat(session.start_time)
                formatted_time = start_time.strftime("%m/%d/%Y %H:%M")
                
                # Get starter's name
                starter = ctx.guild.get_member(session.started_by)
                starter_name = starter.display_name if starter else "Unknown User"
                
                # Session info
                participants_count = len(session.participants)
                duration = f"{session.duration_minutes}m" if session.end_time else "ongoing"
                
                embed.add_field(
                    name=f"Session {i+1} - {formatted_time}",
                    value=f"Started by: {starter_name}\nParticipants: {participants_count}\nDuration: {duration}",
                    inline=True
                )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ValorantCommands(bot))