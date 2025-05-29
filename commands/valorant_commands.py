import logging
import discord
from discord.ext import commands
from valorant_client import valorant_client
from data_manager import data_manager
from datetime import datetime, timezone
from match_tracker import get_match_tracker

class ValorantCommands(commands.Cog):
    """Commands for Valorant integration and account management"""
    
    def __init__(self, bot):
        self.bot = bot
        self.match_tracker = get_match_tracker(bot)
    
    @commands.hybrid_command(
        name="shootylink",
        description="Link your Valorant account (e.g., /shootylink username tag)"
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
            logging.error(f"Error in shootylink command: {e}")
            
            # Send error message using appropriate method
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(f"❌ {error_msg}")
                else:
                    await ctx.send(f"❌ {error_msg}")
            except:
                await ctx.send(f"❌ {error_msg}")
    
    @commands.hybrid_command(
        name="shootymanuallink", 
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
        name="shootyunlink",
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
        name="shootyinfo",
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
            value="• Link multiple accounts (`/shootylink`, `/shootyaddalt`)\n• Account management (`/shootylist`, `/shootyprimary`, `/shootyremove`)\n• Discord presence detection\n• Session stats tracking\n• In-game status display (🎮 emoji)",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ API Status",
            value="Henrik's Valorant API now requires authentication.\nAccount verification is temporarily disabled.\nUse `/shootymanuallink` for now.",
            inline=False
        )
        
        embed.add_field(
            name="🔑 To Enable Full Features",
            value="1. Get API key from [docs.henrikdev.xyz](https://docs.henrikdev.xyz)\n2. Add `HENRIK_API_KEY=your_key` to .env file\n3. Restart bot to enable `/shootylink` verification",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="shootyaddalt",
        description="Add an additional Valorant account (e.g., /shootyaddalt username tag)"
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
                    description="You can only link up to 5 Valorant accounts. Use `/shootyremove` to remove an account first.",
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
            logging.error(f"Error in shootyaddalt command: {e}")
            
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(f"❌ {error_msg}")
                else:
                    await ctx.send(f"❌ {error_msg}")
            except:
                await ctx.send(f"❌ {error_msg}")
    
    @commands.hybrid_command(
        name="shootylist",
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
        name="shootyprimary",
        description="Set a Valorant account as your primary (e.g., /shootyprimary username tag)"
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
        name="shootyremove",
        description="Remove a linked Valorant account (e.g., /shootyremove username tag)"
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
        name="shootywho",
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
        name="shootystats",
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
                value="None linked (use `/shootylink` to link)",
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
        name="shootystatsdetailed",
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
            performance_ratings = stats.get('performance_ratings', {})
            embed.add_field(
                name="📊 Core Performance",
                value=f"**ACS:** {stats.get('acs', 0):.0f}\n"
                      f"**KD Ratio:** {stats.get('kd_ratio', 0):.2f}\n"
                      f"**KDA Ratio:** {stats.get('kda_ratio', 0):.2f}\n"
                      f"**KAST:** {stats.get('kast_percentage', 0):.1f}%",
                inline=True
            )
            
            # Performance Badges
            if performance_ratings:
                badge_text = "\n".join([
                    performance_ratings.get('fragger', ''),
                    performance_ratings.get('support', ''),
                    performance_ratings.get('accuracy', '')
                ])
                embed.add_field(
                    name="🏆 Performance Badges",
                    value=badge_text or "No badges yet",
                    inline=True
                )
            
            # Damage Stats
            embed.add_field(
                name="💥 Damage",
                value=f"**ADR:** {stats.get('adr', 0):.0f}\n"
                      f"**DD (Δ):** {stats.get('damage_delta_per_round', 0):+.0f}\n"
                      f"**Damage/Game:** {stats.get('avg_damage_made', 0):.0f}\n"
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
            
            # Enhanced Stats Section
            multikills = stats.get('multikills', {})
            mk_text = []
            for mk_type, count in multikills.items():
                if count > 0:
                    mk_text.append(f"**{mk_type.upper()}s:** {count}")
            
            embed.add_field(
                name="🔥 Multi-Kills & Achievements",
                value="\n".join(mk_text) if mk_text else "No multi-kills recorded",
                inline=True
            )
            
            # Streaks and Special Stats
            current_win_streak = stats.get('current_win_streak', 0)
            current_loss_streak = stats.get('current_loss_streak', 0)
            max_win_streak = stats.get('max_win_streak', 0)
            first_blood_rate = stats.get('first_blood_rate', 0)
            clutch_success_rate = stats.get('clutch_success_rate', 0)
            
            streak_text = []
            if current_win_streak > 0:
                streak_text.append(f"🔥 **Win Streak:** {current_win_streak}")
            elif current_loss_streak > 0:
                streak_text.append(f"💔 **Loss Streak:** {current_loss_streak}")
            
            streak_text.extend([
                f"**Best Streak:** {max_win_streak}W",
                f"**First Blood Rate:** {first_blood_rate:.1f}%",
                f"**Clutch Success:** {clutch_success_rate:.1f}%"
            ])
            
            embed.add_field(
                name="⚡ Streaks & Special Stats",
                value="\n".join(streak_text),
                inline=True
            )
            
            # Recent performance
            recent_matches = stats.get('recent_matches', [])[:5]
            if recent_matches:
                recent_list = []
                for match in recent_matches:
                    result = "W" if match['won'] else "L"
                    adr_match = match['damage_made'] / max(match['rounds_played'], 1) if match['rounds_played'] > 0 else 0
                    recent_list.append(f"{result} {match['kills']}/{match['deaths']}/{match['assists']} | {adr_match:.0f} ADR ({match['agent']})")
                embed.add_field(
                    name="📋 Recent Matches",
                    value="\n".join(recent_list),
                    inline=False
                )
            
            # Fun facts and ratings
            performance_ratings = stats.get('performance_ratings', {})
            if performance_ratings:
                survival_rating = performance_ratings.get('survival', '')
                clutch_rating = performance_ratings.get('clutch', '')
                if survival_rating or clutch_rating:
                    embed.add_field(
                        name="🎭 Player Style",
                        value=f"{survival_rating}\n{clutch_rating}",
                        inline=False
                    )
            
            embed.set_footer(text="📊 Enhanced stats with performance tracking • ShootyBot")
            
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
                
        except Exception as e:
            error_msg = f"Error fetching detailed stats: {str(e)}"
            logging.error(f"Error in shootystatsdetailed command: {e}")
            
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(f"❌ {error_msg}")
                else:
                    await ctx.send(f"❌ {error_msg}")
            except:
                await ctx.send(f"❌ {error_msg}")
    
    @commands.hybrid_command(
        name="shootyleaderboard",
        description="Show server leaderboard for Valorant stats (kda, kd, winrate, headshot, acs)"
    )
    async def valorant_leaderboard(self, ctx, stat_type: str = "kda"):
        """Show server leaderboard for various Valorant stats"""
        if hasattr(ctx, 'interaction') and ctx.interaction:
            await ctx.defer()
        
        valid_stats = ["kda", "kd", "winrate", "headshot", "acs", "clutch", "multikill"]
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
        
        try:
            # Collect stats for all members with linked accounts
            member_stats = []
            
            for member in ctx.guild.members:
                if member.bot:
                    continue
                    
                accounts = valorant_client.get_all_linked_accounts(member.id)
                if not accounts:
                    continue
                
                primary_account = valorant_client.get_linked_account(member.id)
                if not primary_account:
                    continue
                
                try:
                    # Get recent matches for stats calculation
                    matches = await valorant_client.get_match_history(
                        primary_account['username'],
                        primary_account['tag'],
                        size=10  # Use fewer matches for leaderboard to be faster
                    )
                    
                    if matches:
                        stats = valorant_client.calculate_player_stats(matches, primary_account['puuid'])
                        if stats.get('total_matches', 0) >= 3:  # Minimum 3 matches for leaderboard
                            member_stats.append({
                                'member': member,
                                'account': primary_account,
                                'stats': stats
                            })
                except Exception as e:
                    logging.warning(f"Error getting stats for {member.display_name}: {e}")
                    continue
            
            if not member_stats:
                embed = discord.Embed(
                    title="🏆 Server Valorant Leaderboard",
                    description="No qualifying players found (need 3+ recent matches)",
                    color=0x808080
                )
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return
            
            # Sort by requested stat
            stat_key = stat_type.lower()
            if stat_key == "kda":
                sorted_stats = sorted(member_stats, key=lambda x: x['stats'].get('kda_ratio', 0), reverse=True)
                title_stat = "KDA Ratio"
                format_func = lambda x: f"{x:.2f}"
            elif stat_key == "kd":
                sorted_stats = sorted(member_stats, key=lambda x: x['stats'].get('kd_ratio', 0), reverse=True)
                title_stat = "K/D Ratio"
                format_func = lambda x: f"{x:.2f}"
            elif stat_key == "winrate":
                sorted_stats = sorted(member_stats, key=lambda x: x['stats'].get('win_rate', 0), reverse=True)
                title_stat = "Win Rate"
                format_func = lambda x: f"{x:.1f}%"
            elif stat_key == "headshot":
                sorted_stats = sorted(member_stats, key=lambda x: x['stats'].get('headshot_percentage', 0), reverse=True)
                title_stat = "Headshot %"
                format_func = lambda x: f"{x:.1f}%"
            elif stat_key == "acs":
                sorted_stats = sorted(member_stats, key=lambda x: x['stats'].get('acs', 0), reverse=True)
                title_stat = "Average Combat Score"
                format_func = lambda x: f"{x:.0f}"
            elif stat_key == "clutch":
                sorted_stats = sorted(member_stats, key=lambda x: x['stats'].get('clutch_success_rate', 0), reverse=True)
                title_stat = "Clutch Success Rate"
                format_func = lambda x: f"{x:.1f}%"
            elif stat_key == "multikill":
                sorted_stats = sorted(member_stats, key=lambda x: sum(x['stats'].get('multikills', {}).values()), reverse=True)
                title_stat = "Total Multi-Kills"
                format_func = lambda x: f"{int(x)}"
            
            # Create leaderboard embed
            embed = discord.Embed(
                title=f"🏆 Server Leaderboard: {title_stat}",
                description=f"Top {min(10, len(sorted_stats))} players based on recent matches",
                color=0xff4655
            )
            
            # Add top players
            leaderboard_text = []
            for i, player_data in enumerate(sorted_stats[:10]):
                member = player_data['member']
                stats = player_data['stats']
                account = player_data['account']
                
                # Get the stat value
                if stat_key == "kda":
                    value = stats.get('kda_ratio', 0)
                elif stat_key == "kd":
                    value = stats.get('kd_ratio', 0)
                elif stat_key == "winrate":
                    value = stats.get('win_rate', 0)
                elif stat_key == "headshot":
                    value = stats.get('headshot_percentage', 0)
                elif stat_key == "acs":
                    value = stats.get('acs', 0)
                elif stat_key == "clutch":
                    value = stats.get('clutch_success_rate', 0)
                elif stat_key == "multikill":
                    value = sum(stats.get('multikills', {}).values())
                
                # Add rank emoji
                rank_emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
                
                # Additional context stats
                matches = stats.get('total_matches', 0)
                if stat_key in ["kda", "kd"]:
                    context = f"({stats.get('avg_kills', 0):.1f}K avg, {matches}G)"
                elif stat_key == "winrate":
                    context = f"({stats.get('wins', 0)}W-{stats.get('losses', 0)}L, {matches}G)"
                elif stat_key == "acs":
                    context = f"({stats.get('kd_ratio', 0):.2f} KD, {matches}G)"
                elif stat_key == "multikill":
                    mk_breakdown = stats.get('multikills', {})
                    aces = mk_breakdown.get('5k', 0)
                    context = f"({aces} aces, {matches}G)" if aces > 0 else f"({matches}G)"
                else:
                    context = f"({matches}G)"
                
                leaderboard_text.append(
                    f"{rank_emoji} **{member.display_name}** - {format_func(value)} {context}"
                )
            
            embed.add_field(
                name=f"🎆 Top Performers",
                value="\n".join(leaderboard_text),
                inline=False
            )
            
            # Add some server stats
            total_matches = sum(p['stats'].get('total_matches', 0) for p in member_stats)
            total_players = len(member_stats)
            avg_stat = sum(p['stats'].get({
                'kda': 'kda_ratio',
                'kd': 'kd_ratio', 
                'winrate': 'win_rate',
                'headshot': 'headshot_percentage',
                'acs': 'acs',
                'clutch': 'clutch_success_rate',
                'multikill': lambda s: sum(s.get('multikills', {}).values())
            }.get(stat_key, 'kda_ratio'), 0) for p in member_stats) / max(total_players, 1)
            
            if callable(avg_stat):
                avg_stat = sum(p['stats'].get('multikills', {}).values() for p in member_stats) / max(total_players, 1)
            
            embed.add_field(
                name="📊 Server Stats",
                value=f"**Players:** {total_players}\n**Total Matches:** {total_matches}\n**Server Average:** {format_func(avg_stat)}",
                inline=True
            )
            
            # Add motivational message based on competition
            if len(sorted_stats) >= 5:
                top_value = sorted_stats[0]['stats'].get({
                    'kda': 'kda_ratio',
                    'kd': 'kd_ratio',
                    'winrate': 'win_rate', 
                    'headshot': 'headshot_percentage',
                    'acs': 'acs',
                    'clutch': 'clutch_success_rate'
                }.get(stat_key, 'kda_ratio'), 0)
                
                if stat_key == 'multikill':
                    top_value = sum(sorted_stats[0]['stats'].get('multikills', {}).values())
                
                if ((stat_key in ['kda', 'kd'] and top_value >= 2.0) or 
                    (stat_key == 'winrate' and top_value >= 70) or
                    (stat_key == 'headshot' and top_value >= 30) or
                    (stat_key == 'acs' and top_value >= 250) or
                    (stat_key == 'clutch' and top_value >= 50) or
                    (stat_key == 'multikill' and top_value >= 5)):
                    embed.add_field(
                        name="🔥 Competition Level",
                        value="**FIERCE COMPETITION!** 🏆\nThis server has some serious talent!",
                        inline=True
                    )
            
            embed.set_footer(text=f"🔄 Use /shootyleaderboard {' | '.join(valid_stats)} to see different rankings")
            
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
        
        except Exception as e:
            logging.error(f"Error in leaderboard command: {e}")
            embed = discord.Embed(
                title="❌ Leaderboard Error",
                description="Sorry, there was an error generating the leaderboard. Please try again later.",
                color=0xff0000
            )
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="shootyhistory",
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
    
    @commands.hybrid_command(
        name="shootylastmatch",
        description="Show stats from the most recent match involving Discord members"
    )
    async def last_match(self, ctx, member: discord.Member = None):
        """Show the most recent match stats"""
        try:
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.defer()
            
            # Use manual check to find recent match
            embed = await self.match_tracker.manual_check_recent_match(ctx.guild, member)
            
            if embed:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
            else:
                no_match_embed = discord.Embed(
                    title="🔍 No Recent Matches",
                    description="No recent matches found with Discord members from this server.",
                    color=0x808080
                )
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(embed=no_match_embed)
                else:
                    await ctx.send(embed=no_match_embed)
                    
        except Exception as e:
            error_msg = f"Error fetching last match: {str(e)}"
            logging.error(f"Error in shootylastmatch command: {e}")
            
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(f"❌ {error_msg}")
                else:
                    await ctx.send(f"❌ {error_msg}")
            except:
                await ctx.send(f"❌ {error_msg}")
    
    @commands.hybrid_command(
        name="shootymatchtracker",
        description="Control the automatic match tracking system"
    )
    @commands.has_permissions(administrator=True)
    async def match_tracker_control(self, ctx, action: str = "status"):
        """Control match tracking (start/stop/status)"""
        try:
            if action.lower() == "start":
                if not self.match_tracker.running:
                    # Start the tracker in background
                    self.bot.loop.create_task(self.match_tracker.start_tracking())
                    embed = discord.Embed(
                        title="✅ Match Tracker Started",
                        description="Auto-detection of completed matches is now enabled.\nThe bot will check every 5 minutes for new matches.",
                        color=0x00ff00
                    )
                else:
                    embed = discord.Embed(
                        title="ℹ️ Already Running",
                        description="Match tracker is already running.",
                        color=0x808080
                    )
                    
            elif action.lower() == "stop":
                self.match_tracker.stop_tracking()
                embed = discord.Embed(
                    title="⏹️ Match Tracker Stopped",
                    description="Auto-detection has been disabled.\nYou can still use `/shootylastmatch` for manual checks.",
                    color=0xff4655
                )
                
            else:  # status
                status = "🟢 Running" if self.match_tracker.running else "🔴 Stopped"
                tracked_count = len(self.match_tracker.tracked_members)
                
                embed = discord.Embed(
                    title="📊 Match Tracker Status",
                    color=0x00ff00 if self.match_tracker.running else 0xff0000
                )
                embed.add_field(
                    name="Status",
                    value=status,
                    inline=True
                )
                embed.add_field(
                    name="Tracked Members",
                    value=str(tracked_count),
                    inline=True
                )
                embed.add_field(
                    name="Check Interval",
                    value=f"{self.match_tracker.check_interval // 60} minutes",
                    inline=True
                )
                
                if ctx.guild.id in self.match_tracker.recent_matches:
                    recent_count = len(self.match_tracker.recent_matches[ctx.guild.id])
                    embed.add_field(
                        name="Recent Matches (Last 2h)",
                        value=str(recent_count),
                        inline=True
                    )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            error_msg = f"Error controlling match tracker: {str(e)}"
            logging.error(f"Error in shootymatchtracker command: {e}")
            await ctx.send(f"❌ {error_msg}")

    @commands.hybrid_command(
        name="shootyfun",
        description="Show fun and quirky Valorant stats with achievements"
    )
    async def fun_valorant_stats(self, ctx, member: discord.Member = None):
        """Show fun stats, achievements, and quirky metrics"""
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
            
            # Use primary account
            selected_account = valorant_client.get_linked_account(target_user.id)
            if not selected_account:
                selected_account = accounts[0]
            
            # Fetch match history
            matches = await valorant_client.get_match_history(
                selected_account['username'], 
                selected_account['tag'], 
                size=20
            )
            
            if not matches:
                embed = discord.Embed(
                    title="❌ No Match Data",
                    description="Could not fetch match history for fun stats analysis.",
                    color=0xff0000
                )
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return
            
            # Calculate stats
            stats = valorant_client.calculate_player_stats(matches, selected_account['puuid'])
            
            if not stats or stats.get('total_matches', 0) == 0:
                embed = discord.Embed(
                    title="❌ No Stats Available",
                    description="No valid match data found for fun stats analysis",
                    color=0xff0000
                )
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return
            
            # Create fun stats embed
            embed = discord.Embed(
                title=f"🎉 Fun Stats: {selected_account['username']}#{selected_account['tag']}",
                description=f"Quirky metrics from the last {stats['total_matches']} matches",
                color=0xff4655
            )
            
            # Performance Ratings/Badges
            performance_ratings = stats.get('performance_ratings', {})
            if performance_ratings:
                ratings_text = "\n".join([
                    f"{performance_ratings.get('fragger', 'Unknown Fragger')}",
                    f"{performance_ratings.get('support', 'Unknown Support')}",
                    f"{performance_ratings.get('survival', 'Unknown Survivor')}",
                    f"{performance_ratings.get('accuracy', 'Unknown Accuracy')}",
                    f"{performance_ratings.get('clutch', 'Unknown Clutcher')}"
                ])
                embed.add_field(
                    name="🏆 Your Player Archetype",
                    value=ratings_text,
                    inline=False
                )
            
            # Multi-Kill Achievements
            multikills = stats.get('multikills', {})
            mk_lines = []
            for mk_type, count in multikills.items():
                if count > 0:
                    if mk_type == '5k':
                        mk_lines.append(f"🔥 **ACE COUNT:** {count} (Legendary!)")
                    elif mk_type == '4k':
                        mk_lines.append(f"💀 **4K COUNT:** {count} (Impressive!)")
                    elif mk_type == '3k':
                        mk_lines.append(f"⚡ **3K COUNT:** {count} (Nice!)")
                    elif mk_type == '2k':
                        mk_lines.append(f"✨ **2K COUNT:** {count}")
            
            embed.add_field(
                name="🔥 Multi-Kill Hall of Fame",
                value="\n".join(mk_lines) if mk_lines else "No multi-kills yet... time to pop off! 💪",
                inline=True
            )
            
            # Streaks and Momentum
            current_win_streak = stats.get('current_win_streak', 0)
            current_loss_streak = stats.get('current_loss_streak', 0)
            max_win_streak = stats.get('max_win_streak', 0)
            max_loss_streak = stats.get('max_loss_streak', 0)
            
            streak_lines = []
            if current_win_streak > 0:
                if current_win_streak >= 5:
                    streak_lines.append(f"🔥🔥 **HOT STREAK:** {current_win_streak}W (ON FIRE!)")
                else:
                    streak_lines.append(f"🔥 **Current Win Streak:** {current_win_streak}")
            elif current_loss_streak > 0:
                if current_loss_streak >= 3:
                    streak_lines.append(f"💔💔 **Rough Patch:** {current_loss_streak}L (Shake it off!)")
                else:
                    streak_lines.append(f"💔 **Current Loss Streak:** {current_loss_streak}")
            else:
                streak_lines.append("⚖️ **Balanced** (Breaking even)")
            
            streak_lines.append(f"🏆 **Best Win Streak:** {max_win_streak}")
            if max_loss_streak > 0:
                streak_lines.append(f"😅 **Worst Loss Streak:** {max_loss_streak}")
            
            embed.add_field(
                name="📈 Momentum Tracker",
                value="\n".join(streak_lines),
                inline=True
            )
            
            # Clutch Performance
            clutches_won = stats.get('clutches_won', {})
            clutches_attempted = stats.get('clutches_attempted', {})
            clutch_success_rate = stats.get('clutch_success_rate', 0)
            
            clutch_lines = []
            total_clutches_won = sum(clutches_won.values())
            if total_clutches_won > 0:
                clutch_lines.append(f"🥇 **Total Clutches Won:** {total_clutches_won}")
                clutch_lines.append(f"📊 **Clutch Success Rate:** {clutch_success_rate:.1f}%")
                
                for situation, won in clutches_won.items():
                    if won > 0:
                        attempted = clutches_attempted.get(situation, 0)
                        clutch_lines.append(f"⚔️ **{situation.upper()}:** {won}/{attempted}")
            else:
                clutch_lines.append("🎯 **No clutches yet** - Your moment awaits!")
            
            embed.add_field(
                name="🔥 Clutch Master Status",
                value="\n".join(clutch_lines),
                inline=False
            )
            
            # Specialty Stats
            first_blood_rate = stats.get('first_blood_rate', 0)
            survival_rate = stats.get('survival_rate', 0)
            accuracy = stats.get('accuracy', 0)
            headshot_percentage = stats.get('headshot_percentage', 0)
            
            specialty_lines = [
                f"🎯 **Entry Success:** {first_blood_rate:.1f}% (First bloods)",
                f"🛡️ **Survival Rate:** {survival_rate:.1f}% (Staying alive)",
                f"🔫 **Shot Accuracy:** {accuracy:.1f}%",
                f"🎯 **Headshot Rate:** {headshot_percentage:.1f}%"
            ]
            
            # Fun damage stats
            avg_damage_made = stats.get('avg_damage_made', 0)
            avg_damage_received = stats.get('avg_damage_received', 0)
            damage_delta = avg_damage_made - avg_damage_received
            
            if damage_delta > 1000:
                specialty_lines.append(f"💥 **Damage Dealer:** +{damage_delta:.0f} damage delta")
            elif damage_delta < -500:
                specialty_lines.append(f"🛡️ **Damage Sponge:** {damage_delta:.0f} damage delta")
            else:
                specialty_lines.append(f"⚖️ **Balanced Fighter:** {damage_delta:+.0f} damage delta")
            
            embed.add_field(
                name="📊 Specialty Stats",
                value="\n".join(specialty_lines),
                inline=False
            )
            
            # Agent Mastery
            agent_performance = stats.get('agent_performance', {})
            if agent_performance:
                best_agents = sorted(agent_performance.items(), 
                                   key=lambda x: (x[1]['wins']/max(x[1]['matches'], 1), x[1]['matches']), 
                                   reverse=True)[:3]
                
                agent_lines = []
                for agent, perf in best_agents:
                    win_rate = (perf['wins'] / max(perf['matches'], 1)) * 100
                    avg_kills = perf['kills'] / max(perf['matches'], 1)
                    agent_lines.append(f"**{agent}:** {win_rate:.0f}%WR, {avg_kills:.1f}K avg ({perf['matches']}G)")
                
                embed.add_field(
                    name="🦸 Agent Mastery Top 3",
                    value="\n".join(agent_lines),
                    inline=True
                )
            
            # Map Performance
            map_performance = stats.get('map_performance', {})
            if map_performance:
                best_maps = sorted(map_performance.items(), 
                                 key=lambda x: (x[1]['wins']/max(x[1]['matches'], 1), x[1]['matches']), 
                                 reverse=True)[:3]
                
                map_lines = []
                for map_name, perf in best_maps:
                    win_rate = (perf['wins'] / max(perf['matches'], 1)) * 100
                    avg_damage = perf['damage'] / max(perf['matches'], 1)
                    map_lines.append(f"**{map_name}:** {win_rate:.0f}%WR, {avg_damage:.0f}ADR ({perf['matches']}G)")
                
                embed.add_field(
                    name="🗺️ Favorite Maps",
                    value="\n".join(map_lines),
                    inline=True
                )
            
            embed.set_footer(text="🎉 Fun stats that make you unique! • ShootyBot")
            
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
                
        except Exception as e:
            error_msg = f"Error fetching fun stats: {str(e)}"
            logging.error(f"Error in shootyfun command: {e}")
            
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    await ctx.followup.send(f"❌ {error_msg}")
                else:
                    await ctx.send(f"❌ {error_msg}")
            except:
                await ctx.send(f"❌ {error_msg}")

async def setup(bot):
    await bot.add_cog(ValorantCommands(bot))