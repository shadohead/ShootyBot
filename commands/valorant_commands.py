import asyncio
import logging
from typing import List, Optional
import discord
from discord import app_commands
from discord.ext import commands
from base_commands import BaseCommandCog
from valorant_client import valorant_client
from data_manager import data_manager
from datetime import datetime, timezone
from match_tracker import get_match_tracker
from config import VALORANT_WEAPON_LIST


async def weapon_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete handler for weapon names in the weapon leaderboard command."""
    current = (current or "").lower()
    matches = [w for w in VALORANT_WEAPON_LIST if current in w.lower()]
    return [app_commands.Choice(name=weapon, value=weapon) for weapon in matches[:25]]

class ValorantCommands(BaseCommandCog):
    """Commands for Valorant integration and account management"""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        self.match_tracker = get_match_tracker(bot)
    
    @commands.hybrid_command(
        name="shootylink",
        description="Link your Valorant account (e.g., /shootylink username tag)"
    )
    async def link_valorant(self, ctx: commands.Context, username: str, tag: str) -> None:
        """Link a Valorant account to Discord user"""
        try:
            await self.defer_if_slash(ctx)
            
            self.logger.info(f"Linking Valorant account {username}#{tag} for user {ctx.author.id}")
            
            result = await valorant_client.link_account(ctx.author.id, username, tag)
            
            if result['success']:
                thumbnail = result.get('card', {}).get('large')
                await self.send_embed(
                    ctx,
                    "✅ Valorant Account Linked",
                    f"Successfully linked **{result['username']}#{result['tag']}**",
                    color=0x00ff00,
                    thumbnail=thumbnail
                )
            else:
                await self.send_error_embed(
                    ctx,
                    "Link Failed",
                    f"Could not link account: {result['error']}"
                )
                
        except Exception as e:
            self.logger.error(f"Error in shootylink command: {e}")
            await self.send_error_embed(ctx, "Error Linking Account", str(e))
    
    @commands.hybrid_command(
        name="shootymanuallink", 
        description="Manually link Valorant account without API verification"
    )
    async def manual_link_valorant(self, ctx: commands.Context, username: str, tag: str) -> None:
        """Manually link a Valorant account (no verification)"""
        try:
            # Store account info without API verification
            user_data = data_manager.get_user(ctx.author.id)
            user_data.link_valorant_account(username, tag, f"manual_{username}_{tag}")
            data_manager.save_user(ctx.author.id)
            
            await self.send_success_embed(
                ctx,
                "Valorant Account Linked (Manual)",
                f"Manually linked **{username}#{tag}**\n*Note: Account not verified due to API limitations*"
            )
            
        except Exception as e:
            self.logger.error(f"Error in manual link: {e}")
            await self.send_error_embed(ctx, "Error Linking Account", str(e))
    
    @commands.hybrid_command(
        name="shootyunlink",
        description="Unlink your Valorant account"
    )
    async def unlink_valorant(self, ctx: commands.Context) -> None:
        """Unlink Valorant account from Discord user"""
        try:
            success = await valorant_client.unlink_account(ctx.author.id)
            
            if success:
                await self.send_success_embed(
                    ctx,
                    "Account Unlinked",
                    "Your Valorant account has been unlinked"
                )
            else:
                await self.send_error_embed(
                    ctx,
                    "Unlink Failed", 
                    "Could not unlink your account"
                )
        except Exception as e:
            self.logger.error(f"Error in unlink command: {e}")
            await self.send_error_embed(ctx, "Error Unlinking Account", str(e))
    
    @commands.hybrid_command(
        name="shootyinfo",
        description="Information about Valorant integration and API status"
    )
    async def valorant_info(self, ctx: commands.Context) -> None:
        """Show information about Valorant integration"""
        fields = [
            {
                "name": "📊 Available Features",
                "value": "• Link multiple accounts (`/shootylink`, `/shootyaddalt`)\n• Account management (`/shootylist`, `/shootyprimary`, `/shootyremove`)\n• Discord presence detection\n• Session stats tracking\n• In-game status display (🎮 emoji)",
                "inline": False
            },
            {
                "name": "⚠️ API Status",
                "value": "Henrik's Valorant API now requires authentication.\nAccount verification is temporarily disabled.\nUse `/shootymanuallink` for now.",
                "inline": False
            },
            {
                "name": "🔑 To Enable Full Features",
                "value": "1. Get API key from [docs.henrikdev.xyz](https://docs.henrikdev.xyz)\n2. Add `HENRIK_API_KEY=your_key` to .env file\n3. Restart bot to enable `/shootylink` verification",
                "inline": False
            }
        ]
        
        await self.send_embed(
            ctx,
            "🎯 Valorant Integration Info",
            "Current status of Valorant features in ShootyBot",
            color=0xff4655,
            fields=fields
        )
    
    @commands.hybrid_command(
        name="shootyaddalt",
        description="Add an additional Valorant account (e.g., /shootyaddalt username tag)"
    )
    async def add_alt_account(self, ctx: commands.Context, username: str, tag: str) -> None:
        """Add an additional Valorant account"""
        try:
            await self.defer_if_slash(ctx)
            
            self.logger.info(f"Adding alt Valorant account {username}#{tag} for user {ctx.author.id}")
            
            # Get current accounts count
            user_data = data_manager.get_user(ctx.author.id)
            current_accounts = len(user_data.get_all_accounts())
            
            if current_accounts >= 5:  # Limit to 5 accounts per user
                await self.send_error_embed(
                    ctx,
                    "Account Limit Reached",
                    "You can only link up to 5 Valorant accounts. Use `/shootyremove` to remove an account first."
                )
                return
            
            result = await valorant_client.link_account(ctx.author.id, username, tag)
            
            if result['success']:
                # Link as non-primary account
                user_data.link_valorant_account(result['username'], result['tag'], result['puuid'], set_primary=False)
                data_manager.save_user(ctx.author.id)
                
                thumbnail = result.get('card', {}).get('large')
                await self.send_embed(
                    ctx,
                    "✅ Alt Account Added",
                    f"Added **{result['username']}#{result['tag']}** as alternate account",
                    color=0x00ff00,
                    thumbnail=thumbnail
                )
            else:
                await self.send_error_embed(
                    ctx,
                    "Failed to Add Alt Account",
                    f"Could not add account: {result['error']}"
                )
                
        except Exception as e:
            self.logger.error(f"Error in shootyaddalt command: {e}")
            await self.send_error_embed(ctx, "Error Adding Alt Account", str(e))
    
    @commands.hybrid_command(
        name="shootylist",
        description="List all your linked Valorant accounts"
    )
    async def list_accounts(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """List all linked Valorant accounts"""
        target_user = member or ctx.author
        accounts = valorant_client.get_all_linked_accounts(target_user.id)
        
        if not accounts:
            await self.send_embed(
                ctx,
                "📋 Valorant Accounts",
                f"{target_user.display_name} has no linked Valorant accounts",
                color=0x808080
            )
        else:
            account_list = []
            for i, account in enumerate(accounts, 1):
                primary_marker = " 🌟" if account.get('primary', False) else ""
                account_list.append(f"{i}. **{account['username']}#{account['tag']}**{primary_marker}")
            
            await self.send_embed(
                ctx,
                f"📋 {target_user.display_name}'s Valorant Accounts",
                "\n".join(account_list),
                color=0xff4655,
                footer="🌟 = Primary Account"
            )
    
    @commands.hybrid_command(
        name="shootyprimary",
        description="Set a Valorant account as your primary (e.g., /shootyprimary username tag)"
    )
    async def set_primary_account(self, ctx: commands.Context, username: str, tag: str) -> None:
        """Set a Valorant account as primary"""
        try:
            user_data = data_manager.get_user(ctx.author.id)
            
            if user_data.set_primary_account(username, tag):
                data_manager.save_user(ctx.author.id)
                await self.send_success_embed(
                    ctx,
                    "Primary Account Set",
                    f"**{username}#{tag}** is now your primary Valorant account"
                )
            else:
                await self.send_error_embed(
                    ctx,
                    "Account Not Found",
                    f"Could not find **{username}#{tag}** in your linked accounts"
                )
        except Exception as e:
            self.logger.error(f"Error in set primary account: {e}")
            await self.send_error_embed(ctx, "Error Setting Primary Account", str(e))
    
    @commands.hybrid_command(
        name="shootyremove",
        description="Remove a linked Valorant account (e.g., /shootyremove username tag)"
    )
    async def remove_account(self, ctx: commands.Context, username: str, tag: str) -> None:
        """Remove a linked Valorant account"""
        try:
            user_data = data_manager.get_user(ctx.author.id)
            
            if user_data.remove_valorant_account(username, tag):
                data_manager.save_user(ctx.author.id)
                await self.send_success_embed(
                    ctx,
                    "Account Removed",
                    f"Removed **{username}#{tag}** from your linked accounts"
                )
            else:
                await self.send_error_embed(
                    ctx,
                    "Account Not Found",
                    f"Could not find **{username}#{tag}** in your linked accounts"
                )
        except Exception as e:
            self.logger.error(f"Error in remove account: {e}")
            await self.send_error_embed(ctx, "Error Removing Account", str(e))
    
    @commands.hybrid_command(
        name="shootywho",
        description="Show who is currently playing Valorant in this server"
    )
    async def who_playing(self, ctx: commands.Context) -> None:
        """Show members currently playing Valorant"""
        playing_members = valorant_client.get_playing_members(ctx.guild)
        
        if not playing_members:
            await self.send_embed(
                ctx,
                "🎮 Valorant Players",
                "No one is currently playing Valorant",
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
            
            await self.send_embed(
                ctx,
                "🎮 Currently Playing Valorant",
                "\n".join(player_list),
                color=0xff4655
            )
    
    @commands.hybrid_command(
        name="shootystats",
        description="Show your Shooty session stats"
    )
    async def valorant_stats(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """Show user's session statistics"""
        target_user = member or ctx.author
        user_data = data_manager.get_user(target_user.id)
        
        # Get linked accounts info
        all_accounts = valorant_client.get_all_linked_accounts(target_user.id)
        
        # Get recent sessions
        recent_sessions = data_manager.get_user_sessions(target_user.id, limit=5)
        
        fields = []
        
        # Add linked accounts info with tracker.gg links
        if all_accounts:
            if len(all_accounts) == 1:
                account = all_accounts[0]
                # Create tracker.gg URL
                tracker_url = f"https://tracker.gg/valorant/profile/riot/{account['username']}%23{account['tag']}/overview"
                fields.append({
                    "name": "🎯 Valorant Account",
                    "value": f"{account['username']}#{account['tag']}\n🔗 [View on Tracker.gg]({tracker_url})",
                    "inline": False
                })
            else:
                account_list = []
                for account in all_accounts:
                    primary_marker = " 🌟" if account.get('primary', False) else ""
                    tracker_url = f"https://tracker.gg/valorant/profile/riot/{account['username']}%23{account['tag']}/overview"
                    account_list.append(f"• {account['username']}#{account['tag']}{primary_marker}\n  🔗 [Tracker.gg]({tracker_url})")
                
                fields.append({
                    "name": f"🎯 Valorant Accounts ({len(all_accounts)})",
                    "value": "\n".join(account_list),
                    "inline": False
                })
        else:
            fields.append({
                "name": "🎯 Valorant Accounts",
                "value": "None linked (use `/shootylink` to link)",
                "inline": False
            })
        
        # Add session stats
        fields.append({
            "name": "📈 Session Stats",
            "value": f"Total Sessions: **{user_data.total_sessions}**\nGames Played: **{user_data.total_games_played}**",
            "inline": True
        })
        
        # Add playing status
        if valorant_client.is_playing_valorant(target_user):
            fields.append({
                "name": "🎮 Current Status",
                "value": "**Currently Playing Valorant!**",
                "inline": True
            })
        
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
            
            fields.append({
                "name": "📋 Recent Sessions",
                "value": "\n".join(session_list) or "No recent sessions",
                "inline": False
            })
        
        await self.send_embed(
            ctx,
            f"📊 Stats for {target_user.display_name}",
            color=0xff4655,
            fields=fields
        )
    
    @commands.hybrid_command(
        name="shootystatsdetailed",
        description="Show detailed Valorant match statistics (KDA, KAST, headshot %, etc.)"
    )
    async def detailed_valorant_stats(self, ctx: commands.Context, member: Optional[discord.Member] = None, account_name: Optional[str] = None) -> None:
        """Show detailed Valorant statistics from match history"""
        target_user = member or ctx.author
        
        try:
            await self.defer_if_slash(ctx)
            
            # Get user's Valorant accounts
            accounts = valorant_client.get_all_linked_accounts(target_user.id)
            
            if not accounts:
                await self.send_error_embed(
                    ctx,
                    "No Linked Accounts",
                    f"{target_user.display_name} has no linked Valorant accounts"
                )
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
                    await self.send_error_embed(
                        ctx,
                        "Account Not Found",
                        f"Could not find account '{account_name}' for {target_user.display_name}"
                    )
                    return
            else:
                # Use primary account
                selected_account = valorant_client.get_linked_account(target_user.id)
                if not selected_account:
                    selected_account = accounts[0]
            
            # Fetch match history (competitive only for accurate stats)
            matches = await valorant_client.get_match_history(
                selected_account['username'], 
                selected_account['tag'], 
                size=20,  # Analyze last 20 matches
                mode='competitive'  # Only analyze competitive matches
            )
            
            if not matches:
                await self.send_error_embed(
                    ctx,
                    "No Match Data",
                    "Could not fetch match history. Account may be private or no recent matches found."
                )
                return
            
            # Calculate comprehensive stats
            stats = valorant_client.calculate_player_stats(matches, selected_account['puuid'])
            
            if not stats or stats.get('total_matches', 0) == 0:
                await self.send_error_embed(
                    ctx,
                    "No Stats Available",
                    "No valid match data found for analysis"
                )
                return
            
            # Get performance ratings first
            performance_ratings = stats.get('performance_ratings', {})
            
            # Create tracker.gg URL for this account
            tracker_url = f"https://tracker.gg/valorant/profile/riot/{selected_account['username']}%23{selected_account['tag']}/overview"
            
            # Create detailed stats embed
            await self.send_embed(
                ctx,
                f"📊 Detailed Stats: {selected_account['username']}#{selected_account['tag']}",
                f"Analysis from last {stats['total_matches']} competitive matches\n🔗 [View on Tracker.gg]({tracker_url})",
                color=0xff4655,
                fields=[
                    {
                        "name": "📊 Core Performance",
                        "value": f"**ACS:** {stats.get('acs', 0):.0f} *(combat score)*\n"
                                f"**KD Ratio:** {stats.get('kd_ratio', 0):.2f}\n"
                                f"**KDA Ratio:** {stats.get('kda_ratio', 0):.2f}\n"
                                f"**KAST:** {stats.get('kast_percentage', 0):.1f}% *(impact %)*",
                        "inline": True
                    },
                    {
                        "name": "🏆 Performance Badges",
                        "value": "\n".join([
                            performance_ratings.get('fragger', ''),
                            performance_ratings.get('support', ''),
                            performance_ratings.get('accuracy', '')
                        ]) + "\n\n*Badges based on your combat stats*" if performance_ratings else "No badges yet",
                        "inline": True
                    } if performance_ratings else None,
                    {
                        "name": "💥 Damage",
                        "value": f"**ADR:** {stats.get('adr', 0):.0f} *(per round)*\n"
                                f"**DD (Δ):** {stats.get('damage_delta_per_round', 0):+.0f} *(dealt-taken)*\n"
                                f"**Damage/Game:** {stats.get('avg_damage_made', 0):.0f}\n"
                                f"**Headshot %:** {stats.get('headshot_percentage', 0):.1f}%",
                        "inline": True
                    },
                    {
                        "name": "🏆 Match Results",
                        "value": f"**Win Rate:** {stats.get('win_rate', 0):.1f}%\n"
                                f"**Wins:** {stats.get('wins', 0)}\n"
                                f"**Losses:** {stats.get('losses', 0)}\n"
                                f"**Total Matches:** {stats.get('total_matches', 0)}",
                        "inline": True
                    },
                    {
                        "name": "📈 Averages",
                        "value": f"**Kills:** {stats.get('avg_kills', 0):.1f}\n"
                              f"**Deaths:** {stats.get('avg_deaths', 0):.1f}\n"
                              f"**Assists:** {stats.get('avg_assists', 0):.1f}\n"
                              f"**Score:** {stats.get('avg_score', 0):.0f}",
                        "inline": True
                    },
                    {
                        "name": "🦸 Most Played Agents",
                        "value": "\n".join([f"{agent} ({count})" for agent, count in sorted(stats.get('agents_played', {}).items(), key=lambda x: x[1], reverse=True)[:3]]) or "No agent data",
                        "inline": True
                    },
                    {
                        "name": "🗺️ Most Played Maps",
                        "value": "\n".join([f"{map_name} ({count})" for map_name, count in sorted(stats.get('maps_played', {}).items(), key=lambda x: x[1], reverse=True)[:3]]) or "No map data",
                        "inline": True
                    },
                    {
                        "name": "🔥 Advanced Stats",
                        "value": f"**First Kills:** {stats.get('first_bloods', 0)}\n"
                                f"**First Deaths:** {stats.get('first_deaths', 0)}\n" 
                                f"**Multi-Kills:** {sum(stats.get('multikills', {}).values())} *(3+ kill rounds)*\n"
                                f"**FB Rate:** {stats.get('first_blood_rate', 0):.1f}%",
                        "inline": True
                    },
                    {
                        "name": "⚡ Streaks & Special Stats",
                        "value": "\n".join([
                            f"🔥 **Win Streak:** {stats.get('current_win_streak', 0)}" if stats.get('current_win_streak', 0) > 0 else f"💔 **Loss Streak:** {stats.get('current_loss_streak', 0)}" if stats.get('current_loss_streak', 0) > 0 else "⚖️ **Balanced**",
                            f"**Best Streak:** {stats.get('max_win_streak', 0)}W",
                            f"**First Blood Rate:** {stats.get('first_blood_rate', 0):.1f}%",
                            f"**Clutch Success:** {stats.get('clutch_success_rate', 0):.1f}%"
                        ]),
                        "inline": True
                    },
                    {
                        "name": "📋 Recent Matches",
                        "value": "\n".join([f"{'W' if match['won'] else 'L'} {match['kills']}/{match['deaths']}/{match['assists']} | {match['damage_made'] / max(match['rounds_played'], 1):.0f} ADR ({match['agent']})" for match in stats.get('recent_matches', [])[:5]]) or "No recent match data",
                        "inline": False
                    } if stats.get('recent_matches') else None,
                    {
                        "name": "🎭 Player Style",
                        "value": f"{performance_ratings.get('survival', '')}\n{performance_ratings.get('clutch', '')}\n\n*Your playstyle based on survival & clutch stats*",
                        "inline": False
                    } if performance_ratings and (performance_ratings.get('survival') or performance_ratings.get('clutch')) else None
                ],
                footer="📊 Competitive match analysis • /shootystatshelp for details"
            )
                
        except Exception as e:
            self.logger.error(f"Error in shootystatsdetailed command: {e}")
            await self.send_error_embed(ctx, "Error Fetching Detailed Stats", str(e))

    @commands.hybrid_command(
        name="shootyrank",
        description="Show current Valorant rank, RR, and last game's RR change"
    )
    async def valorant_rank(self, ctx: commands.Context, member: Optional[discord.Member] = None,
                            account_name: Optional[str] = None) -> None:
        """Show a player's current competitive rank and RR."""
        target_user = member or ctx.author

        try:
            await self.defer_if_slash(ctx)

            accounts = valorant_client.get_all_linked_accounts(target_user.id)
            if not accounts:
                await self.send_error_embed(
                    ctx, "No Linked Accounts",
                    f"{target_user.display_name} has no linked Valorant accounts"
                )
                return

            # Select which account to check
            selected_account = None
            if account_name:
                for account in accounts:
                    if account['username'].lower() == account_name.lower():
                        selected_account = account
                        break
                if not selected_account:
                    await self.send_error_embed(
                        ctx, "Account Not Found",
                        f"Could not find account '{account_name}' for {target_user.display_name}"
                    )
                    return
            else:
                selected_account = valorant_client.get_linked_account(target_user.id) or accounts[0]

            mmr = await valorant_client.get_mmr(selected_account['username'], selected_account['tag'])
            if not mmr or not mmr.get('tier'):
                await self.send_error_embed(
                    ctx, "No Rank Data",
                    "Could not fetch rank. The account may be private, unranked, or the API is unavailable."
                )
                return

            rr = mmr.get('rr')
            change = mmr.get('rr_change')
            peak = mmr.get('peak')
            elo = mmr.get('elo')

            lines = [f"{mmr.get('emoji', '')} **{mmr['tier']}**" + (f" — **{rr} RR**" if rr is not None else "")]
            if change is not None:
                if change > 0:
                    lines.append(f"🟢 **+{change} RR** last game")
                elif change < 0:
                    lines.append(f"🔴 **{change} RR** last game")
                else:
                    lines.append("⚪ **±0 RR** last game")
            if peak:
                lines.append(f"🏔️ Peak: **{peak}**")
            if elo is not None:
                lines.append(f"📊 Elo: **{elo}**")

            tracker_url = f"https://tracker.gg/valorant/profile/riot/{selected_account['username']}%23{selected_account['tag']}/overview"

            await self.send_embed(
                ctx,
                f"{mmr.get('emoji', '')} Rank: {selected_account['username']}#{selected_account['tag']}",
                "\n".join(lines) + f"\n\n🔗 [View on Tracker.gg]({tracker_url})",
                color=0xff4655
            )

        except Exception as e:
            self.logger.error(f"Error in shootyrank command: {e}")
            await self.send_error_embed(ctx, "Error Fetching Rank", str(e))

    @commands.hybrid_command(
        name="shootycompare",
        description="Compare two players' Valorant stats head-to-head"
    )
    async def compare_players(self, ctx: commands.Context, player1: discord.Member,
                              player2: Optional[discord.Member] = None) -> None:
        """Head-to-head comparison of two players' competitive stats."""
        try:
            await self.defer_if_slash(ctx)

            # Default the second player to the command author
            if player2 is None:
                player2 = ctx.author

            if player1.id == player2.id:
                await self.send_error_embed(
                    ctx, "Pick Two Players",
                    "Please choose two different players to compare."
                )
                return

            # Gather stats for both players
            results = []
            for member in (player1, player2):
                account = (valorant_client.get_linked_account(member.id)
                           or next(iter(valorant_client.get_all_linked_accounts(member.id)), None))
                if not account:
                    await self.send_error_embed(
                        ctx, "No Linked Accounts",
                        f"{member.display_name} has no linked Valorant accounts"
                    )
                    return

                matches = await valorant_client.get_match_history(
                    account['username'], account['tag'], size=20, mode='competitive'
                )
                if not matches:
                    await self.send_error_embed(
                        ctx, "No Match Data",
                        f"Could not fetch competitive match history for {member.display_name}."
                    )
                    return

                stats = valorant_client.calculate_player_stats(matches, account['puuid'])
                if not stats or stats.get('total_matches', 0) == 0:
                    await self.send_error_embed(
                        ctx, "No Stats Available",
                        f"No competitive match data found for {member.display_name}."
                    )
                    return

                results.append({'member': member, 'account': account, 'stats': stats})

            a, b = results[0], results[1]

            # Comparison rows: (label, value getter, formatter)  — higher is better for all
            rows = [
                ("ACS", lambda s: s.get('acs', 0), lambda v: f"{v:.0f}"),
                ("K/D", lambda s: s.get('kd_ratio', 0), lambda v: f"{v:.2f}"),
                ("KDA", lambda s: s.get('kda_ratio', 0), lambda v: f"{v:.2f}"),
                ("KAST", lambda s: s.get('kast_percentage', 0), lambda v: f"{v:.0f}%"),
                ("ADR", lambda s: s.get('adr', 0), lambda v: f"{v:.0f}"),
                ("HS%", lambda s: s.get('headshot_percentage', 0), lambda v: f"{v:.1f}%"),
                ("Win%", lambda s: s.get('win_rate', 0), lambda v: f"{v:.0f}%"),
                ("FB%", lambda s: s.get('first_blood_rate', 0), lambda v: f"{v:.1f}%"),
                ("Clutch%", lambda s: s.get('clutch_success_rate', 0), lambda v: f"{v:.0f}%"),
            ]

            name_a = a['member'].display_name[:9]
            name_b = b['member'].display_name[:9]
            header = f"{'Stat':<9}{name_a:<11}{name_b:<11}"
            table_lines = [header, "─" * len(header)]

            a_wins = b_wins = 0
            for label, getter, fmt in rows:
                va = getter(a['stats'])
                vb = getter(b['stats'])
                sa, sb = fmt(va), fmt(vb)
                if va > vb:
                    sa += " ★"
                    a_wins += 1
                elif vb > va:
                    sb += " ★"
                    b_wins += 1
                table_lines.append(f"{label:<9}{sa:<11}{sb:<11}")

            table = "```\n" + "\n".join(table_lines) + "\n```"

            if a_wins > b_wins:
                verdict = f"🏆 **{a['member'].display_name}** leads {a_wins}–{b_wins} categories"
                color = 0x00ff66
            elif b_wins > a_wins:
                verdict = f"🏆 **{b['member'].display_name}** leads {b_wins}–{a_wins} categories"
                color = 0x00ff66
            else:
                verdict = f"🤝 Dead even — {a_wins}–{b_wins}"
                color = 0xffaa00

            embed = discord.Embed(
                title="⚔️ Head-to-Head",
                description=f"**{a['member'].display_name}** vs **{b['member'].display_name}**\n{table}",
                color=color
            )
            embed.add_field(name="Verdict", value=verdict, inline=False)

            # Current ranks (best-effort)
            rank_a = await valorant_client.get_mmr(a['account']['username'], a['account']['tag'])
            rank_b = await valorant_client.get_mmr(b['account']['username'], b['account']['tag'])
            if (rank_a and rank_a.get('tier')) or (rank_b and rank_b.get('tier')):
                ra = f"{rank_a.get('emoji', '')} {rank_a['tier']}" if rank_a and rank_a.get('tier') else "Unranked"
                rb = f"{rank_b.get('emoji', '')} {rank_b['tier']}" if rank_b and rank_b.get('tier') else "Unranked"
                embed.add_field(
                    name="Current Rank",
                    value=f"**{a['member'].display_name}:** {ra}\n**{b['member'].display_name}:** {rb}",
                    inline=False
                )

            embed.set_footer(
                text=f"Last {a['stats']['total_matches']} vs {b['stats']['total_matches']} comp games • ★ = category leader"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            self.logger.error(f"Error in shootycompare command: {e}")
            await self.send_error_embed(ctx, "Error Comparing Players", str(e))

    # Cap concurrent Henrik API requests so leaderboards don't trip rate limits
    _LEADERBOARD_CONCURRENCY = 5

    async def _gather_member_stats(self, guild: discord.Guild, size: int = 10) -> List[dict]:
        """Fetch Valorant stats for every member with a linked account, concurrently.

        Results are cached at the client/DB layer, so warm runs make no API calls;
        cold runs are bounded by a semaphore to respect Henrik API rate limits.

        Returns a list of dicts: {'member', 'account', 'stats'}.
        """
        semaphore = asyncio.Semaphore(self._LEADERBOARD_CONCURRENCY)

        async def fetch(member: discord.Member, account: dict) -> Optional[dict]:
            async with semaphore:
                try:
                    matches = await valorant_client.get_match_history(
                        account['username'], account['tag'], size=size
                    )
                    if not matches:
                        return None
                    stats = valorant_client.calculate_player_stats(matches, account['puuid'])
                    return {'member': member, 'account': account, 'stats': stats}
                except Exception as e:
                    self.logger.warning(f"Error getting stats for {member.display_name}: {e}")
                    return None

        tasks = []
        for member in guild.members:
            if member.bot:
                continue
            account = valorant_client.get_linked_account(member.id)
            if not account:
                continue
            tasks.append(fetch(member, account))

        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    @commands.hybrid_command(
        name="shootyleaderboard",
        description="Show server leaderboard for Valorant stats (kda, kd, winrate, headshot, acs)"
    )
    async def valorant_leaderboard(self, ctx: commands.Context, stat_type: str = "kda") -> None:
        """Show server leaderboard for various Valorant stats"""
        await self.defer_if_slash(ctx)
        
        valid_stats = ["kda", "kd", "winrate", "headshot", "acs", "clutch", "multikill"]
        if stat_type.lower() not in valid_stats:
            await self.send_error_embed(
                ctx,
                "Invalid Stat Type",
                f"Valid options: {', '.join(valid_stats)}"
            )
            return
        
        try:
            # Collect stats for all members with linked accounts (concurrently)
            all_member_stats = await self._gather_member_stats(ctx.guild, size=10)
            # Minimum 3 matches for leaderboard
            member_stats = [
                m for m in all_member_stats if m['stats'].get('total_matches', 0) >= 3
            ]

            if not member_stats:
                await self.send_embed(
                    ctx,
                    "🏆 Server Valorant Leaderboard",
                    "No qualifying players found (need 3+ recent matches)",
                    color=0x808080
                )
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
            
            embed.set_footer(text=f"🔄 Use /shootyleaderboard {' | '.join(valid_stats)} • Use /shootystatsdetailed for tracker.gg links")
            
            await ctx.send(embed=embed)
        
        except Exception as e:
            self.logger.error(f"Error in leaderboard command: {e}")
            await self.send_error_embed(
                ctx,
                "Leaderboard Error",
                "Sorry, there was an error generating the leaderboard. Please try again later."
            )
    
    @commands.hybrid_command(
        name="shootyweaponstats",
        description="Server leaderboard of kills with a specific weapon (e.g., /shootyweaponstats Vandal)"
    )
    @app_commands.describe(weapon="The Valorant weapon to rank players by (start typing for suggestions)")
    @app_commands.autocomplete(weapon=weapon_autocomplete)
    async def weapon_leaderboard(self, ctx: commands.Context, *, weapon: str) -> None:
        """Show a server leaderboard ranking players by kills with a given weapon."""
        await self.defer_if_slash(ctx)

        # Resolve the requested weapon to a canonical name (case-insensitive)
        requested = weapon.strip()
        canonical_weapon = next(
            (w for w in VALORANT_WEAPON_LIST if w.lower() == requested.lower()),
            None
        )
        if not canonical_weapon:
            await self.send_error_embed(
                ctx,
                "Unknown Weapon",
                f"'{requested}' isn't a recognized weapon.\n"
                f"Valid weapons: {', '.join(VALORANT_WEAPON_LIST)}"
            )
            return

        try:
            # Collect stats for all members with linked accounts (concurrently),
            # then tally kills with the requested weapon
            all_member_stats = await self._gather_member_stats(ctx.guild, size=10)

            member_stats = []
            for entry in all_member_stats:
                stats = entry['stats']
                # Match weapon names case-insensitively against the player's tally
                weapon_kills = {
                    name.lower(): count
                    for name, count in stats.get('weapon_kills', {}).items()
                }
                kills = weapon_kills.get(canonical_weapon.lower(), 0)

                if kills > 0:
                    member_stats.append({
                        'member': entry['member'],
                        'kills': kills,
                        'matches': stats.get('total_matches', 0)
                    })

            if not member_stats:
                await self.send_embed(
                    ctx,
                    f"🔫 Server {canonical_weapon} Leaderboard",
                    f"No recent kills with the **{canonical_weapon}** found among linked players.",
                    color=0x808080
                )
                return

            # Sort by weapon kills (descending)
            member_stats.sort(key=lambda x: x['kills'], reverse=True)

            embed = discord.Embed(
                title=f"🔫 Server Leaderboard: {canonical_weapon} Kills",
                description=f"Top {min(10, len(member_stats))} players by **{canonical_weapon}** kills "
                            f"(based on each player's recent competitive matches)",
                color=0xff4655
            )

            leaderboard_text = []
            for i, player_data in enumerate(member_stats[:10]):
                member = player_data['member']
                kills = player_data['kills']
                matches = player_data['matches']
                rank_emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
                leaderboard_text.append(
                    f"{rank_emoji} **{member.display_name}** - {kills} kills ({matches}G)"
                )

            embed.add_field(
                name="🎯 Top Fraggers",
                value="\n".join(leaderboard_text),
                inline=False
            )

            total_weapon_kills = sum(p['kills'] for p in member_stats)
            embed.add_field(
                name="📊 Server Stats",
                value=f"**Players:** {len(member_stats)}\n**Total {canonical_weapon} Kills:** {total_weapon_kills}",
                inline=True
            )

            embed.set_footer(
                text="🔄 Try other weapons with /shootyweaponstats <weapon> • "
                     "Stats reflect each player's recent matches"
            )

            await ctx.send(embed=embed)

        except Exception as e:
            self.logger.error(f"Error in weapon leaderboard command: {e}")
            await self.send_error_embed(
                ctx,
                "Weapon Leaderboard Error",
                "Sorry, there was an error generating the weapon leaderboard. Please try again later."
            )

    @commands.hybrid_command(
        name="shootyhistory",
        description="Show session history for this channel"
    )
    async def session_history(self, ctx: commands.Context, limit: int = 5) -> None:
        """Show recent session history for the channel"""
        if limit > 10:
            limit = 10
        
        recent_sessions = data_manager.get_channel_sessions(ctx.channel.id, limit)
        
        if not recent_sessions:
            await self.send_embed(
                ctx,
                "📋 Session History",
                "No sessions found for this channel",
                color=0x808080
            )
        else:
            fields = []
            for i, session in enumerate(recent_sessions):
                start_time = datetime.fromisoformat(session.start_time)
                formatted_time = start_time.strftime("%m/%d/%Y %H:%M")
                
                # Get starter's name
                starter = ctx.guild.get_member(session.started_by)
                starter_name = starter.display_name if starter else "Unknown User"
                
                # Session info
                participants_count = len(session.participants)
                duration = f"{session.duration_minutes}m" if session.end_time else "ongoing"
                
                fields.append({
                    "name": f"Session {i+1} - {formatted_time}",
                    "value": f"Started by: {starter_name}\nParticipants: {participants_count}\nDuration: {duration}",
                    "inline": True
                })
            
            await self.send_embed(
                ctx,
                f"📋 Recent Sessions ({len(recent_sessions)})",
                color=0xff4655,
                fields=fields
            )
    
    @commands.hybrid_command(
        name="shootylastmatch",
        description="Show stats from the most recent match involving Discord members"
    )
    async def last_match(self, ctx: commands.Context, member: Optional[discord.Member] = None, fresh: bool = False) -> None:
        """Show the most recent match stats
        
        Args:
            member: Optional Discord member to check specifically 
            fresh: If True, force fresh data from API (bypass cache)
        """
        try:
            await self.defer_if_slash(ctx)
            
            # Use manual check to find recent match
            embed = await self.match_tracker.manual_check_recent_match(ctx.guild, member, force_fresh=fresh)
            
            if embed:
                await ctx.send(embed=embed)
            else:
                await self.send_embed(
                    ctx,
                    "🔍 No Recent Matches",
                    "No recent matches found with Discord members from this server.",
                    color=0x808080
                )
                    
        except Exception as e:
            self.logger.error(f"Error in shootylastmatch command: {e}")
            await self.send_error_embed(ctx, "Error Fetching Last Match", str(e))
    
    @commands.hybrid_command(
        name="shootymatchtracker",
        description="Control the automatic match tracking system"
    )
    @commands.has_permissions(administrator=True)
    async def match_tracker_control(self, ctx: commands.Context, action: str = "status") -> None:
        """Control match tracking (start/stop/status)"""
        try:
            if action.lower() == "start":
                if not self.match_tracker.running:
                    # Start the tracker in background
                    self.bot.loop.create_task(self.match_tracker.start_tracking())
                    await self.send_success_embed(
                        ctx,
                        "Match Tracker Started",
                        "Auto-detection of completed matches is now enabled.\nThe bot will check every 5 minutes for new matches."
                    )
                else:
                    await self.send_info_embed(
                        ctx,
                        "Already Running",
                        "Match tracker is already running."
                    )
                    
            elif action.lower() == "stop":
                self.match_tracker.stop_tracking()
                await self.send_embed(
                    ctx,
                    "⏹️ Match Tracker Stopped",
                    "Auto-detection has been disabled.\nYou can still use `/shootylastmatch` for manual checks.",
                    color=0xff4655
                )
                
            else:  # status
                status = "🟢 Running" if self.match_tracker.running else "🔴 Stopped"
                tracked_count = len(self.match_tracker.tracked_members)
                
                fields = [
                    {"name": "Status", "value": status, "inline": True},
                    {"name": "Tracked Members", "value": str(tracked_count), "inline": True},
                    {"name": "Check Interval", "value": f"{self.match_tracker.check_interval // 60} minutes", "inline": True}
                ]
                
                if ctx.guild.id in self.match_tracker.recent_matches:
                    recent_count = len(self.match_tracker.recent_matches[ctx.guild.id])
                    fields.append({"name": "Recent Matches (Last 2h)", "value": str(recent_count), "inline": True})
                
                await self.send_embed(
                    ctx,
                    "📊 Match Tracker Status",
                    color=0x00ff00 if self.match_tracker.running else 0xff0000,
                    fields=fields
                )
            
        except Exception as e:
            self.logger.error(f"Error in shootymatchtracker command: {e}")
            await self.send_error_embed(ctx, "Error Controlling Match Tracker", str(e))

    @commands.hybrid_command(
        name="shootystatshelp",
        description="Explains what all the Valorant statistics and badges mean"
    )
    async def stats_help(self, ctx: commands.Context) -> None:
        """Show detailed explanations of all statistics and badges"""
        embed = discord.Embed(
            title="📊 Valorant Statistics Guide",
            description="Understanding your performance metrics and badges",
            color=0xff4655
        )
        
        # Core stats explanation
        embed.add_field(
            name="📈 Core Performance Metrics",
            value=(
                "**ACS** - Average Combat Score per round\n"
                "**ADR** - Average Damage per Round\n"
                "**DD (Δ)** - Damage Delta (damage dealt - taken)\n"
                "**KD** - Kill/Death ratio\n"
                "**KDA** - (Kills + Assists) / Deaths\n"
                "**KAST** - % rounds with Kill/Assist/Survived/Traded"
            ),
            inline=False
        )
        
        # Badge explanations
        embed.add_field(
            name="🔥 Fragger Badges",
            value=(
                "**🔥 Demon Fragger** - 20+ avg kills (Top tier)\n"
                "**💀 Elite Fragger** - 15-19 avg kills (Excellent)\n"
                "**⚡ Solid Fragger** - 12-14 avg kills (Good)\n"
                "**🎯 Entry Fragger** - <12 avg kills (Standard)"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🤝 Support Badges",
            value=(
                "**👑 Support King** - 8+ avg assists (Amazing)\n"
                "**🤝 Team Player** - 6-7 avg assists (Great)\n"
                "**✨ Helper** - 4-5 avg assists (Good)\n"
                "**🔫 Solo Player** - <4 avg assists (Independent)"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🎯 Accuracy Badges",
            value=(
                "**🎯 Headshot Machine** - 35%+ headshots\n"
                "**🔥 Sharp Shooter** - 25-34% headshots\n"
                "**💯 Precise** - 70%+ shot accuracy\n"
                "**🌀 Spray Master** - Lower accuracy"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🛡️ Survival Badges",
            value=(
                "**🛡️ Untouchable** - 80%+ survival rate\n"
                "**🏃 Escape Artist** - 70-79% survival\n"
                "**💪 Survivor** - 60-69% survival\n"
                "**💥 Risk Taker** - <60% survival"
            ),
            inline=True
        )
        
        embed.add_field(
            name="💎 Clutch Badges",
            value=(
                "**🏆 Clutch God** - 5+ clutches, 60%+ success\n"
                "**⭐ Clutch King** - 3+ clutches, 50%+ success\n"
                "**💎 Clutch Player** - 1+ clutches won\n"
                "**🎲 Learning Clutches** - No clutches yet"
            ),
            inline=True
        )
        
        embed.add_field(
            name="📊 Other Key Stats",
            value=(
                "**First Blood Rate** - % of rounds where you got first blood\n"
                "**Win/Loss Streaks** - Current & best streaks\n"
                "**Multi-kills** - 2K/3K/4K/ACE counts\n"
                "**Map/Agent Performance** - Win rates by map/agent"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use /shootystatsdetailed to see your full stats breakdown!")
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="shootyfun",
        description="Show fun and quirky Valorant stats with achievements"
    )
    async def fun_valorant_stats(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        """Show fun stats, achievements, and quirky metrics"""
        target_user = member or ctx.author
        
        try:
            await self.defer_if_slash(ctx)
            
            # Get user's Valorant accounts
            accounts = valorant_client.get_all_linked_accounts(target_user.id)
            
            if not accounts:
                await self.send_error_embed(
                    ctx,
                    "No Linked Accounts",
                    f"{target_user.display_name} has no linked Valorant accounts"
                )
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
                await self.send_error_embed(
                    ctx,
                    "No Match Data",
                    "Could not fetch match history for fun stats analysis."
                )
                return
            
            # Calculate stats
            stats = valorant_client.calculate_player_stats(matches, selected_account['puuid'])
            
            if not stats or stats.get('total_matches', 0) == 0:
                await self.send_error_embed(
                    ctx,
                    "No Stats Available",
                    "No valid match data found for fun stats analysis"
                )
                return
            
            # Create tracker.gg URL for this account
            tracker_url = f"https://tracker.gg/valorant/profile/riot/{selected_account['username']}%23{selected_account['tag']}/overview"
            
            # Create fun stats embed
            embed = discord.Embed(
                title=f"🎉 Fun Stats: {selected_account['username']}#{selected_account['tag']}",
                description=f"Last {stats['total_matches']} competitive matches\n🔗 [View on Tracker.gg]({tracker_url})",
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
            
            await ctx.send(embed=embed)
                
        except Exception as e:
            self.logger.error(f"Error in shootyfun command: {e}")
            await self.send_error_embed(ctx, "Error Fetching Fun Stats", str(e))

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ValorantCommands(bot))