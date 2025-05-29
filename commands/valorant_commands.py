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
        try:
            # Use defer() for slash commands, but check if it exists first
            if hasattr(ctx, 'interaction') and ctx.interaction:
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
            else:
                embed = discord.Embed(
                    title="❌ Link Failed",
                    description=f"Could not link account: {result['error']}",
                    color=0xff0000
                )
            
            # Use appropriate send method based on context type
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
                
        except Exception as e:
            error_msg = f"Error linking account: {str(e)}"
            logging.error(f"Error in vlink command: {e}")
            
            # Send error message using appropriate method
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(f"❌ {error_msg}")
                else:
                    await ctx.send(f"❌ {error_msg}")
            except:
                await ctx.send(f"❌ {error_msg}")
    
    @commands.hybrid_command(
        name="vmanuallink", 
        description="Manually link Valorant account without API verification"
    )
    async def manual_link_valorant(self, ctx, username: str, tag: str):
        """Manually link a Valorant account (no verification)"""
        try:
            # Store account info without API verification
            user_data = data_manager.get_user(ctx.author.id)
            user_data.link_valorant_account(username, tag, f"manual_{username}_{tag}")
            data_manager.save_user(ctx.author.id)
            
            embed = discord.Embed(
                title="✅ Valorant Account Linked (Manual)",
                description=f"Manually linked **{username}#{tag}**\n*Note: Account not verified due to API limitations*",
                color=0x00ff00
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Error in manual link: {e}")
            await ctx.send(f"❌ Error linking account: {str(e)}")
    
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
        name="vinfo",
        description="Information about Valorant integration and API status"
    )
    async def valorant_info(self, ctx):
        """Show information about Valorant integration"""
        embed = discord.Embed(
            title="🎯 Valorant Integration Info",
            description="Current status of Valorant features in ShootyBot",
            color=0xff4655
        )
        
        embed.add_field(
            name="📊 Available Features",
            value="• Link multiple accounts (`/vlink`, `/vaddalt`)\n• Account management (`/vlist`, `/vprimary`, `/vremove`)\n• Discord presence detection\n• Session stats tracking\n• In-game status display (🎮 emoji)",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ API Status",
            value="Henrik's Valorant API now requires authentication.\nAccount verification is temporarily disabled.\nUse `/vmanuallink` for now.",
            inline=False
        )
        
        embed.add_field(
            name="🔑 To Enable Full Features",
            value="1. Get API key from [docs.henrikdev.xyz](https://docs.henrikdev.xyz)\n2. Add `HENRIK_API_KEY=your_key` to .env file\n3. Restart bot to enable `/vlink` verification",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="vaddalt",
        description="Add an additional Valorant account (e.g., /vaddalt username tag)"
    )
    async def add_alt_account(self, ctx, username: str, tag: str):
        """Add an additional Valorant account"""
        try:
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.defer()
            
            logging.info(f"Adding alt Valorant account {username}#{tag} for user {ctx.author.id}")
            
            # Get current accounts count
            user_data = data_manager.get_user(ctx.author.id)
            current_accounts = len(user_data.get_all_accounts())
            
            if current_accounts >= 5:  # Limit to 5 accounts per user
                embed = discord.Embed(
                    title="❌ Account Limit Reached",
                    description="You can only link up to 5 Valorant accounts. Use `/vremove` to remove an account first.",
                    color=0xff0000
                )
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return
            
            result = await valorant_client.link_account(ctx.author.id, username, tag)
            
            if result['success']:
                # Link as non-primary account
                user_data.link_valorant_account(result['username'], result['tag'], result['puuid'], set_primary=False)
                data_manager.save_user(ctx.author.id)
                
                embed = discord.Embed(
                    title="✅ Alt Account Added",
                    description=f"Added **{result['username']}#{result['tag']}** as alternate account",
                    color=0x00ff00
                )
                
                if result.get('card', {}).get('large'):
                    embed.set_thumbnail(url=result['card']['large'])
            else:
                embed = discord.Embed(
                    title="❌ Failed to Add Alt Account",
                    description=f"Could not add account: {result['error']}",
                    color=0xff0000
                )
            
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
                
        except Exception as e:
            error_msg = f"Error adding alt account: {str(e)}"
            logging.error(f"Error in vaddalt command: {e}")
            
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(f"❌ {error_msg}")
                else:
                    await ctx.send(f"❌ {error_msg}")
            except:
                await ctx.send(f"❌ {error_msg}")
    
    @commands.hybrid_command(
        name="vlist",
        description="List all your linked Valorant accounts"
    )
    async def list_accounts(self, ctx, member: discord.Member = None):
        """List all linked Valorant accounts"""
        target_user = member or ctx.author
        accounts = valorant_client.get_all_linked_accounts(target_user.id)
        
        if not accounts:
            embed = discord.Embed(
                title="📋 Valorant Accounts",
                description=f"{target_user.display_name} has no linked Valorant accounts",
                color=0x808080
            )
        else:
            account_list = []
            for i, account in enumerate(accounts, 1):
                primary_marker = " 🌟" if account.get('primary', False) else ""
                account_list.append(f"{i}. **{account['username']}#{account['tag']}**{primary_marker}")
            
            embed = discord.Embed(
                title=f"📋 {target_user.display_name}'s Valorant Accounts",
                description="\n".join(account_list),
                color=0xff4655
            )
            
            embed.set_footer(text="🌟 = Primary Account")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="vprimary",
        description="Set a Valorant account as your primary (e.g., /vprimary username tag)"
    )
    async def set_primary_account(self, ctx, username: str, tag: str):
        """Set a Valorant account as primary"""
        user_data = data_manager.get_user(ctx.author.id)
        
        if user_data.set_primary_account(username, tag):
            data_manager.save_user(ctx.author.id)
            embed = discord.Embed(
                title="✅ Primary Account Set",
                description=f"**{username}#{tag}** is now your primary Valorant account",
                color=0x00ff00
            )
        else:
            embed = discord.Embed(
                title="❌ Account Not Found",
                description=f"Could not find **{username}#{tag}** in your linked accounts",
                color=0xff0000
            )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="vremove",
        description="Remove a linked Valorant account (e.g., /vremove username tag)"
    )
    async def remove_account(self, ctx, username: str, tag: str):
        """Remove a linked Valorant account"""
        user_data = data_manager.get_user(ctx.author.id)
        
        if user_data.remove_valorant_account(username, tag):
            data_manager.save_user(ctx.author.id)
            embed = discord.Embed(
                title="✅ Account Removed",
                description=f"Removed **{username}#{tag}** from your linked accounts",
                color=0x00ff00
            )
        else:
            embed = discord.Embed(
                title="❌ Account Not Found",
                description=f"Could not find **{username}#{tag}** in your linked accounts",
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
        
        # Get linked accounts info
        all_accounts = valorant_client.get_all_linked_accounts(target_user.id)
        primary_account = valorant_client.get_linked_account(target_user.id)
        
        # Get recent sessions
        recent_sessions = data_manager.get_user_sessions(target_user.id, limit=5)
        
        embed = discord.Embed(
            title=f"📊 Stats for {target_user.display_name}",
            color=0xff4655
        )
        
        # Add linked accounts info
        if all_accounts:
            if len(all_accounts) == 1:
                account = all_accounts[0]
                embed.add_field(
                    name="🎯 Valorant Account",
                    value=f"{account['username']}#{account['tag']}",
                    inline=False
                )
            else:
                account_list = []
                for account in all_accounts:
                    primary_marker = " 🌟" if account.get('primary', False) else ""
                    account_list.append(f"• {account['username']}#{account['tag']}{primary_marker}")
                
                embed.add_field(
                    name=f"🎯 Valorant Accounts ({len(all_accounts)})",
                    value="\n".join(account_list),
                    inline=False
                )
        else:
            embed.add_field(
                name="🎯 Valorant Accounts",
                value="None linked (use `/vlink` to link)",
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
        name="vstatsdetailed",
        description="Show detailed Valorant match statistics (KDA, KAST, headshot %, etc.)"
    )
    async def detailed_valorant_stats(self, ctx, member: discord.Member = None, account_name: str = None):
        """Show detailed Valorant statistics from match history"""
        target_user = member or ctx.author
        
        try:
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.defer()
            
            # Get user's Valorant accounts
            accounts = valorant_client.get_all_linked_accounts(target_user.id)
            
            if not accounts:
                embed = discord.Embed(
                    title="❌ No Linked Accounts",
                    description=f"{target_user.display_name} has no linked Valorant accounts",
                    color=0xff0000
                )
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return
            
            # Select which account to analyze
            selected_account = None
            if account_name:
                # Find specific account
                for account in accounts:
                    if account['username'].lower() == account_name.lower():
                        selected_account = account
                        break
                if not selected_account:
                    embed = discord.Embed(
                        title="❌ Account Not Found",
                        description=f"Could not find account '{account_name}' for {target_user.display_name}",
                        color=0xff0000
                    )
                    if hasattr(ctx, 'interaction') and ctx.interaction:
                        await ctx.followup.send(embed=embed)
                    else:
                        await ctx.send(embed=embed)
                    return
            else:
                # Use primary account
                selected_account = valorant_client.get_linked_account(target_user.id)
                if not selected_account:
                    selected_account = accounts[0]
            
            # Fetch match history
            matches = await valorant_client.get_match_history(
                selected_account['username'], 
                selected_account['tag'], 
                size=20  # Analyze last 20 matches
            )
            
            if not matches:
                embed = discord.Embed(
                    title="❌ No Match Data",
                    description="Could not fetch match history. Account may be private or no recent matches found.",
                    color=0xff0000
                )
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return
            
            # Calculate comprehensive stats
            stats = valorant_client.calculate_player_stats(matches, selected_account['puuid'])
            
            if not stats or stats.get('total_matches', 0) == 0:
                embed = discord.Embed(
                    title="❌ No Stats Available",
                    description="No valid match data found for analysis",
                    color=0xff0000
                )
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return
            
            # Create detailed stats embed
            embed = discord.Embed(
                title=f"🎯 Detailed Stats: {selected_account['username']}#{selected_account['tag']}",
                description=f"Analysis of last {stats['total_matches']} matches",
                color=0xff4655
            )
            
            # Performance Stats
            embed.add_field(
                name="📊 Performance",
                value=f"**KD Ratio:** {stats.get('kd_ratio', 0):.2f}\n"
                      f"**KDA Ratio:** {stats.get('kda_ratio', 0):.2f}\n"
                      f"**KAST:** {stats.get('kast_percentage', 0):.1f}%\n"
                      f"**Headshot %:** {stats.get('headshot_percentage', 0):.1f}%",
                inline=True
            )
            
            # Match Results
            embed.add_field(
                name="🏆 Match Results",
                value=f"**Win Rate:** {stats.get('win_rate', 0):.1f}%\n"
                      f"**Wins:** {stats.get('wins', 0)}\n"
                      f"**Losses:** {stats.get('losses', 0)}\n"
                      f"**Total Matches:** {stats.get('total_matches', 0)}",
                inline=True
            )
            
            # Averages
            embed.add_field(
                name="📈 Averages",
                value=f"**Kills:** {stats.get('avg_kills', 0):.1f}\n"
                      f"**Deaths:** {stats.get('avg_deaths', 0):.1f}\n"
                      f"**Assists:** {stats.get('avg_assists', 0):.1f}\n"
                      f"**Score:** {stats.get('avg_score', 0):.0f}",
                inline=True
            )
            
            # Most played agents
            agents = stats.get('agents_played', {})
            if agents:
                top_agents = sorted(agents.items(), key=lambda x: x[1], reverse=True)[:3]
                agent_list = [f"{agent} ({count})" for agent, count in top_agents]
                embed.add_field(
                    name="🦸 Most Played Agents",
                    value="\n".join(agent_list),
                    inline=True
                )
            
            # Most played maps
            maps = stats.get('maps_played', {})
            if maps:
                top_maps = sorted(maps.items(), key=lambda x: x[1], reverse=True)[:3]
                map_list = [f"{map_name} ({count})" for map_name, count in top_maps]
                embed.add_field(
                    name="🗺️ Most Played Maps",
                    value="\n".join(map_list),
                    inline=True
                )
            
            # Recent performance
            recent_matches = stats.get('recent_matches', [])[:5]
            if recent_matches:
                recent_list = []
                for match in recent_matches:
                    result = "W" if match['won'] else "L"
                    recent_list.append(f"{result} {match['kills']}/{match['deaths']}/{match['assists']} ({match['agent']})")
                embed.add_field(
                    name="📋 Recent Matches",
                    value="\n".join(recent_list),
                    inline=False
                )
            
            embed.set_footer(text="📊 Stats based on recent competitive matches")
            
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
                
        except Exception as e:
            error_msg = f"Error fetching detailed stats: {str(e)}"
            logging.error(f"Error in vstatsdetailed command: {e}")
            
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(f"❌ {error_msg}")
                else:
                    await ctx.send(f"❌ {error_msg}")
            except:
                await ctx.send(f"❌ {error_msg}")
    
    @commands.hybrid_command(
        name="vleaderboard",
        description="Show server leaderboard for Valorant stats"
    )
    async def valorant_leaderboard(self, ctx, stat_type: str = "kda"):
        """Show server leaderboard for various Valorant stats"""
        if hasattr(ctx, 'interaction') and ctx.interaction:
            await ctx.defer()
        
        valid_stats = ["kda", "kd", "winrate", "headshot", "kast"]
        if stat_type.lower() not in valid_stats:
            embed = discord.Embed(
                title="❌ Invalid Stat Type",
                description=f"Valid options: {', '.join(valid_stats)}",
                color=0xff0000
            )
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🏆 Server Valorant Leaderboard",
            description=f"Top players by {stat_type.upper()} (Coming Soon!)",
            color=0xff4655
        )
        
        embed.add_field(
            name="🚧 Under Development",
            value="The leaderboard feature is being developed.\nFor now, use `/vstatsdetailed` to see individual stats!",
            inline=False
        )
        
        if hasattr(ctx, 'interaction') and ctx.interaction:
            await ctx.followup.send(embed=embed)
        else:
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