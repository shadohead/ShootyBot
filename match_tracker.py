import asyncio
import logging
import discord
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from valorant_client import valorant_client
from utils import log_error, format_time_ago, parse_henrik_timestamp
from context_manager import context_manager
from database import database_manager
from match_highlights import MatchStatsCollector, RoundAnalyzer, HighlightsGenerator

class MatchTracker:
    """Tracks Discord members' Valorant matches by polling for newly completed games in active shooty stacks"""
    
    # Configuration constants
    CHECK_INTERVAL_SECONDS = 60  # 1 minute
    MATCH_CUTOFF_HOURS = 2
    MIN_DISCORD_MEMBERS = 2
    LEG_SHOT_THRESHOLD_PERCENT = 15
    HEADSHOT_THRESHOLD_PERCENT = 30
    HIGH_DAMAGE_THRESHOLD = 3000
    STACK_INACTIVITY_HOURS = 1.5  # Auto-end stacks after 1.5 hours of no games
    
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        # State is now persisted to database - these are kept as memory caches for performance
        self.tracked_members: Dict[int, Dict[str, Any]] = {}  # {member_id: {'last_checked': datetime, 'last_match_id': str}}
        self.recent_matches: Dict[int, Dict[str, Dict[str, Any]]] = {}   # {server_id: {match_id: {'timestamp': datetime, 'members': []}}}
        self.stack_last_activity: Dict[int, datetime] = {}  # {channel_id: last_match_timestamp}
        self.stack_has_played: Dict[int, bool] = {}  # {channel_id: has_had_games}
        self.check_interval: int = self.CHECK_INTERVAL_SECONDS
        self.running: bool = False
        self._state_loaded: bool = False
        
    async def start_tracking(self) -> None:
        """Start the background match tracking task"""
        if self.running:
            return
        
        # Load state from database on startup
        if not self._state_loaded:
            await self._load_state_from_database()
            self._state_loaded = True
        
        self.running = True
        logging.info("Starting match tracker with 1-minute polling for active shooty stacks...")
        
        while self.running:
            try:
                await self._check_all_servers()
                await self._check_inactive_stacks()
                # Periodically save state to database
                await self._save_state_to_database()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                log_error("in match tracker", e)
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    def stop_tracking(self) -> None:
        """Stop the background match tracking"""
        self.running = False
        # Save final state to database before stopping
        asyncio.create_task(self._save_state_to_database())
        logging.info("Stopped match tracker")
    
    async def _check_all_servers(self) -> None:
        """Check all servers for recently finished matches"""
        for guild in self.bot.guilds:
            try:
                await self._check_server_matches(guild)
            except Exception as e:
                log_error(f"checking server {guild.id}", e)
    
    async def _check_server_matches(self, guild: discord.Guild) -> None:
        """Check a specific server for finished matches by polling members in active shooty stacks"""
        current_time = datetime.now(timezone.utc)
        members_to_check = []
        
        # Find channels with active shooty sessions in this guild
        for channel in guild.text_channels:
            context = context_manager.get_context(channel.id)
            
            # Get all users in the current stack (soloq + fullstack)
            all_stack_users = context.bot_soloq_user_set.union(context.bot_fullstack_user_set)
            
            # Skip if no one is in the stack
            if not all_stack_users:
                continue
            
            # Convert Discord user objects to member objects and check if they have linked accounts
            for user in all_stack_users:
                # user is a Discord Member object
                if user.bot:
                    continue
                    
                accounts = valorant_client.get_all_linked_accounts(user.id)
                if not accounts:
                    continue
                
                # Update last checked time
                if user.id not in self.tracked_members:
                    self.tracked_members[user.id] = {
                        'last_checked': current_time,
                        'last_match_id': None
                    }
                else:
                    self.tracked_members[user.id]['last_checked'] = current_time
                
                # Add to check list if not already added
                if user not in members_to_check:
                    members_to_check.append(user)
        
        if members_to_check:
            logging.debug(f"Checking {len(members_to_check)} stack members for new matches in {guild.name}")
            await self._check_recent_matches(guild, members_to_check)
        else:
            logging.debug(f"No active stack members with linked Valorant accounts in {guild.name}")
    
    async def _check_recent_matches(self, guild: discord.Guild, members: List[discord.Member]) -> None:
        """Check recent matches for specific members"""
        server_matches = self.recent_matches.setdefault(guild.id, {})
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.MATCH_CUTOFF_HOURS)
        
        for member in members:
            try:
                primary_account = valorant_client.get_linked_account(member.id)
                if not primary_account:
                    continue
                
                # Get recent matches (competitive only)
                matches = await valorant_client.get_match_history(
                    primary_account['username'],
                    primary_account['tag'],
                    size=1,  # Only check most recent match for polling efficiency
                    mode='competitive'  # Only track competitive matches
                )
                
                if not matches:
                    continue
                
                # Check if this member has a new most recent match
                latest_match = matches[0]  # Most recent match
                latest_match_id = latest_match.get('metadata', {}).get('matchid')
                
                if not latest_match_id:
                    continue
                
                # Check if this is a new match for this member
                last_known_match = self.tracked_members.get(member.id, {}).get('last_match_id')
                
                if last_known_match != latest_match_id:
                    # Update the last known match for this member
                    self.tracked_members[member.id]['last_match_id'] = latest_match_id
                    
                    # Skip if we've already processed this match globally
                    if latest_match_id in server_matches:
                        continue
                    
                    # Skip old matches
                    started_at = latest_match.get('metadata', {}).get('game_start', '')
                    match_time = parse_henrik_timestamp(started_at)
                    if match_time:
                        if match_time < cutoff_time:
                            continue
                    else:
                        continue
                    
                    # Skip if match is not completed
                    if not latest_match.get('metadata', {}).get('game_length', 0):
                        continue
                    
                    # Find all Discord members in this match
                    discord_members_in_match = await self._find_discord_members_in_match(guild, latest_match)
                    
                    # Only process if minimum Discord members were in the match
                    if len(discord_members_in_match) >= self.MIN_DISCORD_MEMBERS:
                        server_matches[latest_match_id] = {
                            'timestamp': datetime.now(timezone.utc),
                            'members': discord_members_in_match,
                            'match_data': latest_match
                        }
                        
                        # Send match results to appropriate channel
                        await self._send_match_results(guild, latest_match, discord_members_in_match)
                        
                        # Update stack activity tracking
                        await self._update_stack_activity(guild, discord_members_in_match, latest_match)
                        
            except Exception as e:
                log_error(f"checking matches for {member.display_name}", e)
        
        # Clean up old matches
        for match_id in list(server_matches.keys()):
            if server_matches[match_id]['timestamp'] < cutoff_time:
                del server_matches[match_id]
    
    async def _find_discord_members_in_match(self, guild: discord.Guild, match: dict) -> List[Dict]:
        """Find which Discord members were in a specific match"""
        discord_members = []
        all_players = match.get('players', {}).get('all_players', [])
        
        for member in guild.members:
            if member.bot:
                continue
                
            accounts = valorant_client.get_all_linked_accounts(member.id)
            for account in accounts:
                puuid = account.get('puuid', '')
                
                # Find this player in the match
                for player in all_players:
                    if player.get('puuid') == puuid:
                        discord_members.append({
                            'member': member,
                            'account': account,
                            'player_data': player
                        })
                        break
        
        return discord_members
    
    async def _send_match_results(self, guild: discord.Guild, match: Dict[str, Any], discord_members: List[Dict[str, Any]]) -> None:
        """Send match results to relevant stack channels"""

        target_channels = []

        # Determine which channels have these members queued
        for channel in guild.text_channels:
            context = context_manager.get_context(channel.id)
            all_stack_users = context.bot_soloq_user_set.union(context.bot_fullstack_user_set)
            if not all_stack_users:
                continue

            participants = [dm for dm in discord_members if dm['member'] in all_stack_users]
            if len(participants) >= self.MIN_DISCORD_MEMBERS:
                target_channels.append(channel)

        # Fallback to a general channel if none matched
        if not target_channels:
            for ch in guild.text_channels:
                if ch.name.lower() in ['general', 'valorant', 'gaming', 'shooty']:
                    target_channels.append(ch)
                    break

        if not target_channels and guild.text_channels:
            target_channels.append(guild.text_channels[0])

        if not target_channels:
            return

        try:
            embed = await self._create_match_embed(match, discord_members)
            for ch in target_channels:
                await ch.send(embed=embed)

        except Exception as e:
            log_error("sending match results", e)
    
    async def _create_match_embed(self, match: dict, discord_members: List[Dict]) -> discord.Embed:
        """Create a fun match results embed"""
        metadata = match.get('metadata', {})
        map_name = metadata.get('map', 'Unknown')
        rounds_played = metadata.get('rounds_played', 0)
        game_length = metadata.get('game_length', 0)
        game_start = metadata.get('game_start', '')
        match_id = metadata.get('matchid', '')
        
        # Calculate match duration
        if game_length:
            # game_length is already in seconds
            duration_seconds = int(game_length)
            duration_minutes = duration_seconds // 60
            duration_seconds_remainder = duration_seconds % 60
            
            if duration_minutes >= 60:
                hours = duration_minutes // 60
                minutes = duration_minutes % 60
                duration_str = f"{hours}h {minutes}m"
            else:
                duration_str = f"{duration_minutes}m {duration_seconds_remainder}s"
        else:
            duration_str = "Unknown"
        
        # Parse match start time
        match_timestamp = parse_henrik_timestamp(game_start)
        if match_timestamp is None:
            match_timestamp = datetime.now(timezone.utc)
        
        # Calculate relative time
        if match_timestamp:
            time_ago_str = format_time_ago(match_timestamp)
        else:
            time_ago_str = "Recently"
        
        # Create tracker.gg link if match ID is available
        tracker_link = ""
        if match_id:
            tracker_link = f"\n[📊 View on Tracker.gg](https://tracker.gg/valorant/match/{match_id})"
        
        embed = discord.Embed(
            title="🎯 Match Results",
            description=f"**{map_name}** • {rounds_played} rounds • {duration_str} • {time_ago_str}{tracker_link}",
            color=0xff4655,
            timestamp=match_timestamp
        )
        
        # Calculate fun stats
        fun_stats = self._calculate_fun_match_stats(match, discord_members)
        
        # Add team results
        teams = match.get('teams', {})
        if teams:
            team_info = []
            for team_color, team_data in teams.items():
                result = "🏆 **WON**" if team_data.get('has_won', False) else "❌ **LOST**"
                rounds_won = team_data.get('rounds_won', 0)
                team_info.append(f"{team_color.title()}: {result} ({rounds_won} rounds)")
            
            embed.add_field(
                name="🏆 Match Result",
                value="\n".join(team_info),
                inline=False
            )
        
        # Add Discord members who played
        member_list = []
        stack_result = ""
        team_color = None
        team_won = False

        for dm in discord_members:
            member = dm['member']
            player_data = dm['player_data']
            stats = player_data.get('stats', {})

            # Determine stack result (same for all players since they're together)
            if not stack_result:
                team_color = player_data.get('team', '').lower()
                if teams and team_color in teams:
                    team_won = teams[team_color].get('has_won', False)
                stack_result = "🏆 WON" if team_won else "❌ LOST"

            agent = player_data.get('character', 'Unknown')
            kda = f"{stats.get('kills', 0)}/{stats.get('deaths', 0)}/{stats.get('assists', 0)}"
            member_list.append(f"• **{member.display_name}** ({agent}): {kda}")
        
        embed.add_field(
            name=f"👥 Squad ({len(discord_members)}) - {stack_result}",
            value="\n".join(member_list),
            inline=False
        )
        
        # Add enhanced fun highlights
        if fun_stats['highlights']:
            # Limit to top 6 highlights to avoid embed limits
            top_highlights = fun_stats['highlights'][:6]
            highlights_text = "\n".join([f"{highlight}" for highlight in top_highlights])
            embed.add_field(
                name="🎆 Epic Match Highlights",
                value=highlights_text,
                inline=False
            )
            
            # Add a motivational footer based on performance
            total_kills = sum(dm['player_data'].get('stats', {}).get('kills', 0) for dm in discord_members)
            if total_kills >= 50:
                embed.add_field(
                    name="🔥 Match Rating",
                    value="**LEGENDARY PERFORMANCE!** 🏆 This match will be remembered!",
                    inline=False
                )
            elif total_kills >= 35:
                embed.add_field(
                    name="⚡ Match Rating",
                    value="**INCREDIBLE GAME!** 🎆 Outstanding teamwork!",
                    inline=False
                )

            elif total_kills >= 25:
                embed.add_field(
                    name="💪 Match Rating",
                    value="**SOLID MATCH!** 🎉 Good coordination!",
                    inline=False
                )

        # Add humorous roast if the stack lost badly
        if not team_won:
            my_rounds = teams.get(team_color, {}).get('rounds_won', 0) if teams else 0
            opponent_rounds = 0
            if teams:
                for color, data in teams.items():
                    if color != team_color:
                        opponent_rounds = data.get('rounds_won', 0)
                        break

            total_kills = sum(dm['player_data'].get('stats', {}).get('kills', 0) for dm in discord_members)
            total_deaths = sum(dm['player_data'].get('stats', {}).get('deaths', 0) for dm in discord_members)
            total_assists = sum(dm['player_data'].get('stats', {}).get('assists', 0) for dm in discord_members)
            team_kda = (total_kills + total_assists) / max(total_deaths, 1)

            roast_lines = [f"Score {my_rounds}-{opponent_rounds}."]
            roast_lines.append("Warm up game 🔥")
            roast_lines.append("Can't end it on that one 😅")

            embed.add_field(
                name="😅 Tough Loss",
                value="\n".join(roast_lines),
                inline=False,
            )
        
        embed.set_footer(text="🔍 Auto-detected from shooty stack • ShootyBot tracking your epic moments!")
        return embed
    
    def _calculate_fun_match_stats(self, match_data: dict, discord_members: List[Dict]) -> Dict:
        """
        Calculate fun and interesting match statistics using refactored components.

        This method now delegates to specialized classes for better maintainability:
        - MatchStatsCollector: Collects basic player statistics
        - RoundAnalyzer: Analyzes round-by-round data for advanced stats
        - HighlightsGenerator: Generates highlights from analyzed stats
        """
        stats = {
            'highlights': [],
            'top_performers': {},
            'funny_stats': {}
        }

        if not discord_members:
            return stats

        # Step 1: Collect basic player statistics
        collector = MatchStatsCollector(match_data, discord_members)
        collector.collect_basic_stats()
        player_stats = collector.get_player_stats()
        puuid_to_member = collector.get_puuid_map()

        # Step 2: Analyze round-by-round data for advanced statistics
        analyzer = RoundAnalyzer(match_data, puuid_to_member)
        analyzer.analyze_all_rounds()
        round_stats = analyzer.get_stats()

        # Step 3: Generate highlights from all collected statistics
        generator = HighlightsGenerator(player_stats, round_stats, match_data)
        stats['highlights'] = generator.generate_all_highlights()

        return stats

    async def _update_stack_activity(self, guild: discord.Guild, discord_members_in_match: List[Dict], match_data: Dict[str, Any]) -> None:
        """Update stack activity tracking when matches are found"""
        # Get match timestamp
        started_at = match_data.get('metadata', {}).get('game_start', '')
        match_timestamp = parse_henrik_timestamp(started_at)
        if match_timestamp is None:
            match_timestamp = datetime.now(timezone.utc)
        
        # Find which channels have these members in their stacks
        for channel in guild.text_channels:
            context = context_manager.get_context(channel.id)
            all_stack_users = context.bot_soloq_user_set.union(context.bot_fullstack_user_set)
            
            if not all_stack_users:
                continue
            
            # Check if any of the match participants are in this channel's stack
            stack_members_in_match = []
            for dm in discord_members_in_match:
                if dm['member'] in all_stack_users:
                    stack_members_in_match.append(dm['member'])
            
            # If stack members were in this match, update activity
            if len(stack_members_in_match) >= self.MIN_DISCORD_MEMBERS:
                self.stack_last_activity[channel.id] = match_timestamp
                self.stack_has_played[channel.id] = True
                logging.info(f"Updated activity for stack in channel {channel.id} - {len(stack_members_in_match)} members played")
    
    async def _check_inactive_stacks(self) -> None:
        """Check for stacks that have been inactive and auto-end them"""
        current_time = datetime.now(timezone.utc)
        inactivity_cutoff = timedelta(hours=self.STACK_INACTIVITY_HOURS)
        
        for guild in self.bot.guilds:
            try:
                for channel in guild.text_channels:
                    context = context_manager.get_context(channel.id)
                    all_stack_users = context.bot_soloq_user_set.union(context.bot_fullstack_user_set)
                    
                    # Skip if no one is in the stack
                    if not all_stack_users:
                        # Clean up tracking data for empty stacks
                        if channel.id in self.stack_last_activity:
                            del self.stack_last_activity[channel.id]
                        if channel.id in self.stack_has_played:
                            del self.stack_has_played[channel.id]
                        continue
                    
                    # Only check stacks that have had gaming activity
                    if not self.stack_has_played.get(channel.id, False):
                        continue
                    
                    # Check if stack has been inactive
                    last_activity = self.stack_last_activity.get(channel.id)
                    if last_activity and (current_time - last_activity) > inactivity_cutoff:
                        await self._auto_end_inactive_stack(channel, context, current_time - last_activity)
                        
            except Exception as e:
                log_error(f"checking inactive stacks for {guild.id}", e)
    
    async def _auto_end_inactive_stack(self, channel: discord.TextChannel, context, inactivity_duration: timedelta) -> None:
        """Automatically end an inactive stack"""
        try:
            # Get the session commands cog to end the session properly
            session_cog = self.bot.get_cog('SessionCommands')
            if session_cog:
                # Use the cog's method to properly end the session
                await session_cog._end_current_session(context)
            else:
                # Fallback: end session manually using data manager
                if hasattr(context, 'current_session_id') and context.current_session_id:
                    from data_manager import data_manager
                    session = data_manager.sessions.get(context.current_session_id)
                    if session:
                        # Add all current participants
                        all_users = context.bot_soloq_user_set.union(context.bot_fullstack_user_set)
                        for user in all_users:
                            session.add_participant(user.id)
                            user_data = data_manager.get_user(user.id)
                            user_data.add_session_to_history(context.current_session_id)
                            data_manager.save_user(user.id)
                        
                        # Check if party was full
                        if len(all_users) >= context.party_max_size:
                            session.was_full = True
                        
                        # End the session
                        session.end_session()
                        data_manager.save_session(context.current_session_id)
                    
                    # Clear session reference
                    context.current_session_id = None
            
            # Clear users from the stack
            context.reset_users()
            
            # Clean up tracking data
            if channel.id in self.stack_last_activity:
                del self.stack_last_activity[channel.id]
            if channel.id in self.stack_has_played:
                del self.stack_has_played[channel.id]
            
            # Silently end the stack and log the action
            logging.info(
                f"Auto-ended inactive stack in channel {channel.id} after {inactivity_duration}"
            )
            
        except Exception as e:
            log_error(f"auto-ending stack in channel {channel.id}", e)
    
    async def manual_check_recent_match(self, guild: discord.Guild, member: discord.Member = None, force_fresh: bool = False) -> Optional[discord.Embed]:
        """Manually check for a recent match and return embed if found"""
        if member:
            members_to_check = [member]
        else:
            # Check all members with linked accounts
            members_to_check = []
            for m in guild.members:
                if not m.bot and valorant_client.get_all_linked_accounts(m.id):
                    members_to_check.append(m)
        
        if not members_to_check:
            return None
        
        # Check the most recent match for each member
        for member in members_to_check:
            try:
                # Get all linked accounts for this user, not just primary
                all_accounts = valorant_client.get_all_linked_accounts(member.id)
                if not all_accounts:
                    continue
                
                # Check matches for all linked accounts to get better coverage
                for account in all_accounts:
                    matches = await valorant_client.get_match_history(
                        account['username'],
                        account['tag'],
                        size=5,  # Get more recent matches for better coverage
                        mode='competitive',  # Only check competitive matches
                        force_refresh=force_fresh  # Use the parameter to control freshness
                    )
                    
                    if not matches:
                        continue
                    
                    # Check each match to find the most recent one with Discord members
                    for match in matches:
                        # Check if this match is already processed
                        match_id = match.get('metadata', {}).get('matchid')
                        if not match_id:
                            continue
                        
                        # Find Discord members in this match
                        discord_members_in_match = await self._find_discord_members_in_match(guild, match)
                        
                        if len(discord_members_in_match) >= 1:
                            # Check if we already have this match in our database
                            stored_match = database_manager.get_stored_match(match_id)
                            
                            embed = await self._create_match_embed(match, discord_members_in_match)
                            # Add manual check indicator
                            if embed:
                                if stored_match:
                                    embed.set_footer(text="🔍 Manual match lookup (cached) • ShootyBot")
                                else:
                                    embed.set_footer(text="🔍 Manual match lookup (fresh) • ShootyBot")
                            return embed
                    
            except Exception as e:
                log_error(f"in manual check for {member.display_name}", e)
        
        return None

    async def _load_state_from_database(self) -> None:
        """Load match tracker state from database on startup"""
        try:
            # Load tracked members for all servers
            for guild in self.bot.guilds:
                tracked_users = database_manager.get_all_tracked_users(guild.id)
                for user_id, tracking_data in tracked_users.items():
                    # Convert stored datetime strings back to datetime objects
                    if 'last_checked' in tracking_data and tracking_data['last_checked']:
                        try:
                            tracking_data['last_checked'] = datetime.fromisoformat(tracking_data['last_checked'])
                        except (ValueError, TypeError):
                            tracking_data['last_checked'] = datetime.now(timezone.utc)
                    
                    self.tracked_members[user_id] = tracking_data
            
            # Load stack states
            stack_states = database_manager.get_all_stack_states()
            for channel_id, state_data in stack_states.items():
                self.stack_has_played[channel_id] = state_data['has_played']
                if state_data['last_activity']:
                    self.stack_last_activity[channel_id] = state_data['last_activity']
            
            logging.info(f"Loaded match tracker state: {len(self.tracked_members)} tracked users, {len(self.stack_has_played)} stack states")
            
        except Exception as e:
            log_error("loading match tracker state from database", e)
    
    async def _save_state_to_database(self) -> None:
        """Save current match tracker state to database"""
        try:
            # Save tracked members by server
            servers_processed = set()
            for guild in self.bot.guilds:
                server_id = guild.id
                if server_id in servers_processed:
                    continue
                servers_processed.add(server_id)
                
                # Collect tracking data for users in this server
                for user_id, tracking_data in self.tracked_members.items():
                    # Check if user is in this guild
                    member = guild.get_member(user_id)
                    if member:
                        # Convert datetime objects to strings for JSON storage
                        tracking_data_copy = tracking_data.copy()
                        if 'last_checked' in tracking_data_copy and isinstance(tracking_data_copy['last_checked'], datetime):
                            tracking_data_copy['last_checked'] = tracking_data_copy['last_checked'].isoformat()
                        
                        database_manager.save_match_tracker_state(user_id, server_id, tracking_data_copy)
            
            # Save stack states
            for channel_id, has_played in self.stack_has_played.items():
                last_activity = self.stack_last_activity.get(channel_id)
                # Get participant count from context if available
                try:
                    context = context_manager.get_context(channel_id)
                    participant_count = len(context.bot_soloq_user_set.union(context.bot_fullstack_user_set))
                except:
                    participant_count = 0
                
                database_manager.save_stack_state(
                    channel_id=channel_id,
                    has_played=has_played,
                    last_activity=last_activity,
                    participant_count=participant_count
                )
            
            # Clean up old state data (older than 30 days)
            database_manager.cleanup_old_tracker_state(days=30)
            
        except Exception as e:
            log_error("saving match tracker state to database", e)
    
    def get_persistence_stats(self) -> Dict[str, int]:
        """Get statistics about persisted state"""
        try:
            stats = database_manager.get_database_stats()
            return {
                'tracked_users_persisted': stats.get('match_tracker_state', 0),
                'stack_states_persisted': stats.get('stack_state', 0),
                'tracked_users_memory': len(self.tracked_members),
                'stack_states_memory': len(self.stack_has_played)
            }
        except Exception as e:
            log_error("getting persistence stats", e)
            return {}

# Global match tracker instance
match_tracker = None

def get_match_tracker(bot: discord.Client) -> MatchTracker:
    """Get or create the global match tracker instance"""
    global match_tracker
    if match_tracker is None:
        match_tracker = MatchTracker(bot)
    return match_tracker