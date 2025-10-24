import logging
import asyncio
from datetime import datetime
from typing import Optional
import pytz
from dateutil import parser
from discord.ext import commands
import discord
from base_commands import BaseCommandCog
from context_manager import context_manager
from handlers.message_formatter import get_ping_shooty_message, party_status_message
from handlers.reaction_handler import add_react_options
from data_manager import data_manager
from config import MESSAGES, MAX_SCHEDULED_HOURS
from utils import format_time_for_display

class SessionCommands(BaseCommandCog):
    """Commands for managing party sessions"""
    
    @commands.hybrid_command(
        name="st",
        description="Starts a Fresh Shooty Session (FSS™)"
    )
    async def start_session(self, ctx: commands.Context) -> None:
        try:
            await self.defer_if_slash(ctx)
            self.logger.info("Starting new shooty session")

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

            # Update bot status after resetting users
            await self.bot.update_status_with_queue_count()

            # Send ping message
            response_string = get_ping_shooty_message(shooty_context.role_code)
            message = await ctx.send(response_string)

            # Track the message for reactions
            shooty_context.current_st_message_id = message.id

            # Save context to persist the message ID
            context_manager.save_context(ctx.channel.id)

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
        except Exception as e:
            self.logger.error(f"Error starting session: {e}")
            await self.send_error_embed(ctx, "Session Start Failed", "Failed to start session. Please try again.")
    
    @commands.hybrid_command(
        name="sts",
        description="Prints party status"
    )
    async def session_status(self, ctx: commands.Context) -> None:
        try:
            self.logger.info("Printing Status")

            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)

            status_message = party_status_message(False, shooty_context)
            await ctx.reply(status_message)
        except Exception as e:
            self.logger.error(f"Error getting session status: {e}")
            await self.send_error_embed(ctx, "Status Error", "Failed to get party status.")
    
    @commands.hybrid_command(
        name="stm", 
        description="Mentions everyone in the party"
    )
    async def mention_session(self, ctx: commands.Context) -> None:
        self.logger.info("Mentioning everyone in the party.")
        
        channel_id = ctx.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
        if not shooty_context.bot_soloq_user_set and not shooty_context.bot_fullstack_user_set:
            await self.send_error_embed(ctx, "No Members", MESSAGES["NO_MEMBERS"])
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
    async def restore_session(self, ctx: commands.Context) -> None:
        try:
            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)

            # Restore backup
            restored = shooty_context.restore_state()

            if not restored:
                await self.send_error_embed(ctx, "No Backup", "No previous session state available to restore.")
                return

            self.logger.info(
                "Restoring shooty_context: " +
                str([user.name for user in shooty_context.bot_soloq_user_set.union(shooty_context.bot_fullstack_user_set)])
            )

            # Update bot status after restoring users
            await self.bot.update_status_with_queue_count()

            await self.send_success_embed(ctx, "Session Restored", MESSAGES["RESTORED_SESSION"])
            await ctx.send(party_status_message(False, shooty_context))
        except Exception as e:
            self.logger.error(f"Error restoring session: {e}")
            await self.send_error_embed(ctx, "Restore Failed", "Failed to restore session state.")
    
    @commands.hybrid_command(
        name="shootytime",
        description="Schedule a time to ping the group. You must specify AM/PM or input the time as military time."
    )
    async def scheduled_session(self, ctx: commands.Context, game_time: str) -> None:
        await self.defer_if_slash(ctx)
        
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
                await self.send_error_embed(ctx, "Invalid Time", MESSAGES["PAST_TIME"])
                return
            elif seconds_to_wait > MAX_SCHEDULED_HOURS * 3600:  # Convert hours to seconds
                await self.send_error_embed(ctx, "Too Far in Future", MESSAGES["TOO_FAR_FUTURE"])
                return
            
            message = await ctx.send(f"Shooty at {format_time_for_display(scheduled_time)}?")
            await self.start_session(ctx)
            await asyncio.sleep(seconds_to_wait)

            await ctx.send(f"Shooty time now! - {format_time_for_display(scheduled_time)}")
            await ctx.reply(party_status_message(False, shooty_context))
            
        except ValueError:
            await self.send_error_embed(ctx, "Invalid Time Format", MESSAGES["INVALID_TIME"])
    
    @commands.hybrid_command(
        name="shootyhelp", 
        description="Show comprehensive help for all ShootyBot commands"
    )
    async def show_help(self, ctx: commands.Context, category: str = "all") -> None:
        """Show comprehensive help organized by command categories"""
        import discord
        
        category = category.lower()
        
        if category == "all" or category == "main":
            # Main help embed with all categories
            embed = discord.Embed(
                title="🤖 ShootyBot Commands Help",
                description="Gaming session organizer and Valorant integration bot",
                color=0xff4655
            )
            
            # Core Session Commands
            embed.add_field(
                name="🎯 Core Session Commands",
                value=(
                    "`/st` - Start a Fresh Shooty Session (FSS™)\n"
                    "`/sts` - Check party status\n"
                    "`/stm` - Mention everyone in party\n"
                    "`/stplus <number>` - Add plus ones (guests you're bringing)\n"
                    "`/stend` - End current session\n"
                    "`/shootytime <time>` - Schedule session (e.g. 8:30 PM)\n"
                    "`/shootyrestore` - Restore previous party state"
                ),
                inline=False
            )
            
            # Party Management
            embed.add_field(
                name="👥 Party Management", 
                value=(
                    "`/shootysize <number>` - Set party size limit\n"
                    "`/shootykick <username>` - Remove user from party"
                ),
                inline=False
            )
            
            # Valorant Integration
            embed.add_field(
                name="🎮 Valorant Integration",
                value=(
                    "`/shootylink <username> <tag>` - Link Valorant account\n"
                    "`/shootystats [member]` - Show session & game stats\n"
                    "`/shootystatsdetailed [member]` - Detailed match statistics\n"
                    "`/shootyleaderboard [stat]` - Server leaderboards\n"
                    "`/shootywho` - Who's currently playing Valorant\n"
                    "`/shootyhelp valorant` - See all Valorant commands"
                ),
                inline=False
            )
            
            # Reaction Controls
            embed.add_field(
                name="🔮 Reaction Controls",
                value=(
                    "👍 - Join solo queue (open to any party size)\n"
                    "5️⃣ - Join full stack only (exact party size)\n"
                    "✅ - Mark yourself as ready\n"
                    "🔄 - Refresh party status\n"
                    "📣 - Mention all party members"
                ),
                inline=False
            )
            
            # Admin & Configuration
            embed.add_field(
                name="⚙️ Admin & Configuration",
                value=(
                    "`/shootysetrole <@role>` - Set ping role for channel\n"
                    "`/shootysetgame <name>` - Set game name for LFG\n"
                    "`/shootylfg` - Show cross-server players\n"
                    "`/shootybeacon <message>` - Send cross-server message\n"
                    "`/shootyhelp admin` - See all admin commands"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📖 Get Specific Help",
                value=(
                    "`/shootyhelp valorant` - All Valorant commands\n"
                    "`/shootyhelp admin` - Admin & sync commands\n"
                    "`/shootyhelp reactions` - Detailed reaction guide"
                ),
                inline=False
            )
            
            embed.set_footer(text="💡 Tip: Most commands work as both slash commands (/) and prefix commands ($)")
            
        elif category in ["valorant", "val", "valorant-commands"]:
            # Valorant-specific help
            embed = discord.Embed(
                title="🎯 Valorant Integration Commands",
                description="Link accounts, view stats, and track matches",
                color=0xff4655
            )
            
            embed.add_field(
                name="🔗 Account Management",
                value=(
                    "`/shootylink <username> <tag>` - Link & verify account\n"
                    "`/shootymanuallink <username> <tag>` - Link without verification\n"
                    "`/shootyaddalt <username> <tag>` - Add alternate account\n"
                    "`/shootylist [member]` - List linked accounts\n"
                    "`/shootyprimary <username> <tag>` - Set primary account\n"
                    "`/shootyremove <username> <tag>` - Remove account\n"
                    "`/shootyunlink` - Unlink all accounts"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📊 Statistics & Performance",
                value=(
                    "`/shootystats [member]` - Basic session stats\n"
                    "`/shootystatsdetailed [member] [account]` - Full match analysis\n"
                    "`/shootyfun [member]` - Fun stats & achievements\n"
                    "`/shootyleaderboard <stat>` - Server rankings\n"
                    "**Available stats:** kda, kd, winrate, headshot, acs, clutch, multikill"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🎮 Activity & Matches",
                value=(
                    "`/shootywho` - Who's playing Valorant now\n"
                    "`/shootylastmatch [member]` - Recent match details\n"
                    "`/shootyhistory [limit]` - Channel session history\n"
                    "`/shootymatchtracker <action>` - Control auto-tracking (admin)"
                ),
                inline=False
            )
            
            embed.add_field(
                name="ℹ️ Information & Setup",
                value=(
                    "`/shootyinfo` - API status & feature info\n"
                    "**Note:** Some features require Henrik API key in bot config"
                ),
                inline=False
            )
            
            embed.set_footer(text="🎯 Valorant integration includes match tracking, detailed stats, and leaderboards")
            
        elif category in ["admin", "administration", "config"]:
            # Admin-specific help
            embed = discord.Embed(
                title="⚙️ Admin & Configuration Commands",
                description="Server management and bot configuration",
                color=0xff4655
            )
            
            embed.add_field(
                name="🏠 Channel Configuration",
                value=(
                    "`/shootysetrole <@role>` - Set role to ping for sessions\n"
                    "`/shootysetgame <name>` - Set game name for this channel"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🌐 Cross-Server Features",
                value=(
                    "`/shootylfg` - Show players across all servers for same game\n"
                    "`/shootybeacon <message>` - Send message to other servers playing same game"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🔧 Bot Management (Prefix Commands Only)",
                value=(
                    "`$shootysync` - Sync slash commands to this server\n"
                    "`$shootysyncglobal` - Sync slash commands globally\n"
                    "`$shootycheck` - Check loaded commands and cogs"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🎯 Match Tracking (Admin Only)",
                value=(
                    "`/shootymatchtracker start` - Enable auto match detection\n"
                    "`/shootymatchtracker stop` - Disable auto match detection\n"
                    "`/shootymatchtracker status` - Check tracking status"
                ),
                inline=False
            )
            
            embed.set_footer(text="⚡ Admin commands require appropriate Discord permissions")
            
        elif category in ["reactions", "emojis", "controls"]:
            # Reaction-specific help
            embed = discord.Embed(
                title="🔮 Reaction Controls Guide",
                description="How to use emoji reactions to join parties",
                color=0xff4655
            )
            
            embed.add_field(
                name="👍 Solo Queue (Thumbs Up)",
                value=(
                    "**What it does:** Join the party regardless of current size\n"
                    "**When to use:** You're flexible and will play with any group size\n"
                    "**Example:** Party needs 3 more? No problem, you'll join anyway"
                ),
                inline=False
            )
            
            embed.add_field(
                name="5️⃣ Full Stack Only",
                value=(
                    "**What it does:** Only join when party reaches exact target size\n"
                    "**When to use:** You only want to play with a full team\n"
                    "**Example:** 5v5 competitive matches only"
                ),
                inline=False
            )
            
            embed.add_field(
                name="✅ Ready Status",
                value=(
                    "**What it does:** Mark yourself as ready to play immediately\n"
                    "**When to use:** You're online and ready to start right now\n"
                    "**Visual:** Shows ✅ next to your name in party status"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🔄 Refresh Status",
                value=(
                    "**What it does:** Bot posts updated party status message\n"
                    "**When to use:** Check who's currently in the party\n"
                    "**Result:** New message with current party composition"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📣 Mention Everyone",
                value=(
                    "**What it does:** Bot mentions all party members\n"
                    "**When to use:** Ready to start, need everyone's attention\n"
                    "**Result:** @mentions sent to notify all party members"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💡 Pro Tips",
                value=(
                    "• Remove your reaction to leave the party\n"
                    "• Reactions only work on the latest session message\n"
                    "• You can be in both solo queue AND full stack queue\n"
                    "• Ready status shows you're online and available"
                ),
                inline=False
            )
            
            embed.set_footer(text="🎮 React to the session message to join the party instantly!")
            
        else:
            # Invalid category
            embed = discord.Embed(
                title="❌ Invalid Help Category",
                description=f"Category '{category}' not found.",
                color=0xff0000
            )
            embed.add_field(
                name="Available Categories",
                value=(
                    "`/shootyhelp` or `/shootyhelp all` - All commands\n"
                    "`/shootyhelp valorant` - Valorant integration\n"
                    "`/shootyhelp admin` - Admin & configuration\n"
                    "`/shootyhelp reactions` - Reaction controls guide"
                ),
                inline=False
            )
        
        await ctx.reply(embed=embed)
    
    @commands.hybrid_command(
        name="stend",
        description="End the current session"
    )
    async def end_session(self, ctx: commands.Context) -> None:
        """End the current session"""
        try:
            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)

            if hasattr(shooty_context, 'current_session_id') and shooty_context.current_session_id:
                await self._end_current_session(shooty_context)
                # Update bot status after ending session
                await self.bot.update_status_with_queue_count()
                await self.send_success_embed(ctx, "Session Ended", "Session ended and stats recorded!")
            else:
                await self.send_error_embed(ctx, "No Active Session", "No active session to end.")
        except Exception as e:
            self.logger.error(f"Error ending session: {e}")
            await self.send_error_embed(ctx, "End Session Failed", "Failed to end session.")
    
    async def _end_current_session(self, shooty_context) -> None:
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

            self.logger.info(f"Ended session {session_id} with {len(all_users)} participants")

        # Clear session reference and reset users
        shooty_context.current_session_id = None
        shooty_context.reset_users()

    @commands.hybrid_command(
        name="stplus",
        description="Add plus ones to indicate you're bringing extra people"
    )
    async def set_plus_ones(self, ctx: commands.Context, count: int) -> None:
        """Set the number of plus ones (guests) you're bringing"""
        try:
            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)

            # Check if user is in the party
            user_in_party = (
                ctx.author in shooty_context.bot_soloq_user_set or
                ctx.author in shooty_context.bot_fullstack_user_set
            )

            if not user_in_party:
                await self.send_error_embed(
                    ctx,
                    "Not in Party",
                    "You must join the party first (react with 👍 or 5️⃣) before adding plus ones."
                )
                return

            # Validate count
            if count < 0:
                await self.send_error_embed(
                    ctx,
                    "Invalid Count",
                    "Plus ones count must be 0 or greater."
                )
                return

            # Set plus ones
            shooty_context.set_plus_ones(ctx.author, count)

            # Update the party message if it exists
            if shooty_context.current_st_message_id:
                try:
                    message = await ctx.channel.fetch_message(shooty_context.current_st_message_id)
                    new_message = party_status_message(True, shooty_context)
                    await message.edit(content=new_message)
                except discord.NotFound:
                    self.logger.warning("Could not find party message to update")

            # Send confirmation
            if count == 0:
                await ctx.send(f"{ctx.author.name} removed their plus ones")
            else:
                await ctx.send(f"{ctx.author.name} is bringing +{count}")

        except Exception as e:
            self.logger.error(f"Error setting plus ones: {e}")
            await self.send_error_embed(ctx, "Plus Ones Failed", "Failed to set plus ones. Please try again.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SessionCommands(bot))