import asyncio
import logging
import discord
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from valorant_client import valorant_client
import random
from utils import log_error, format_time_ago, parse_henrik_timestamp
from context_manager import context_manager
from database import database_manager

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
        """Send match results to the server"""
        # Find an appropriate channel (look for general, valorant, or any text channel)
        channel = None
        for ch in guild.text_channels:
            if ch.name.lower() in ['general', 'valorant', 'gaming', 'shooty']:
                channel = ch
                break
        
        if not channel:
            # Use first available text channel
            channel = guild.text_channels[0] if guild.text_channels else None
        
        if not channel:
            return
        
        try:
            # Calculate fun stats and create embed
            embed = await self._create_match_embed(match, discord_members)
            await channel.send(embed=embed)
            
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
            duration_seconds = game_length // 1000
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
        
        for dm in discord_members:
            member = dm['member']
            player_data = dm['player_data']
            stats = player_data.get('stats', {})
            
            # Determine stack result (same for all players since they're together)
            if not stack_result:
                team_color = player_data.get('team', '').lower()
                team_won = False
                if teams and team_color in teams:
                    team_won = teams[team_color].get('has_won', False)
                stack_result = "🏆 WON" if team_won else "❌ LOST"
            
            kda = f"{stats.get('kills', 0)}/{stats.get('deaths', 0)}/{stats.get('assists', 0)}"
            member_list.append(f"• **{member.display_name}**: {kda}")
        
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
        
        embed.set_footer(text="🔍 Auto-detected from shooty stack • ShootyBot tracking your epic moments!")
        return embed
    
    def _calculate_fun_match_stats(self, match_data: dict, discord_members: List[Dict]) -> Dict:
        """Calculate fun and interesting match statistics"""
        stats = {
            'highlights': [],
            'top_performers': {},
            'funny_stats': {}
        }
        
        if not discord_members:
            return stats
        
        # Collect player stats
        player_stats = []
        for dm in discord_members:
            member = dm['member']
            player_data = dm['player_data']
            pstats = player_data.get('stats', {})
            
            player_stats.append({
                'member': member,
                'kills': pstats.get('kills', 0),
                'deaths': pstats.get('deaths', 0),
                'assists': pstats.get('assists', 0),
                'headshots': pstats.get('headshots', 0),
                'bodyshots': pstats.get('bodyshots', 0),
                'legshots': pstats.get('legshots', 0),
                'score': pstats.get('score', 0),
                'damage_made': player_data.get('damage_made', 0),
                'damage_received': player_data.get('damage_received', 0),
                'agent': player_data.get('character', 'Unknown')
            })
        
        # Calculate enhanced highlights
        if len(player_stats) >= 2:
            # Top Fragger with more flair
            top_fragger = max(player_stats, key=lambda x: x['kills'])
            if top_fragger['kills'] >= 25:
                stats['highlights'].append(f"🔥🔥 **DEMON MODE**: {top_fragger['member'].display_name} ({top_fragger['kills']} kills) - GOING NUCLEAR!")
            elif top_fragger['kills'] >= 20:
                stats['highlights'].append(f"🔥 **Top Fragger**: {top_fragger['member'].display_name} ({top_fragger['kills']} kills) - ON FIRE!")
            else:
                stats['highlights'].append(f"🎯 **Top Fragger**: {top_fragger['member'].display_name} ({top_fragger['kills']} kills)")
            
            # Most Damage with context
            top_damage = max(player_stats, key=lambda x: x['damage_made'])
            if top_damage['damage_made'] >= 4000:
                stats['highlights'].append(f"💥 **DAMAGE MONSTER**: {top_damage['member'].display_name} ({top_damage['damage_made']:,} damage) - ANNIHILATION!")
            elif top_damage['damage_made'] >= 3000:
                stats['highlights'].append(f"💥 **Damage Dealer**: {top_damage['member'].display_name} ({top_damage['damage_made']:,} damage)")
            else:
                stats['highlights'].append(f"💪 **Damage Leader**: {top_damage['member'].display_name} ({top_damage['damage_made']:,} damage)")
            
            # Best KDA with performance tiers
            kda_players = [(p, (p['kills'] + p['assists']) / max(p['deaths'], 1)) for p in player_stats]
            best_kda = max(kda_players, key=lambda x: x[1])
            if best_kda[1] >= 3.0:
                stats['highlights'].append(f"👑 **KDA KING**: {best_kda[0]['member'].display_name} ({best_kda[1]:.2f} KDA) - UNTOUCHABLE!")
            elif best_kda[1] >= 2.0:
                stats['highlights'].append(f"⭐ **KDA Master**: {best_kda[0]['member'].display_name} ({best_kda[1]:.2f} KDA)")
            else:
                stats['highlights'].append(f"💪 **Best KDA**: {best_kda[0]['member'].display_name} ({best_kda[1]:.2f} KDA)")
            
            # Enhanced fun/weird stats
            total_shots = sum(p['headshots'] + p['bodyshots'] + p['legshots'] for p in player_stats)
            if total_shots > 0:
                # Most leg shots with humor
                leg_shot_king = max(player_stats, key=lambda x: x['legshots'])
                if leg_shot_king['legshots'] > 0:
                    leg_percentage = (leg_shot_king['legshots'] / max(leg_shot_king['headshots'] + leg_shot_king['bodyshots'] + leg_shot_king['legshots'], 1)) * 100
                    if leg_percentage > self.LEG_SHOT_THRESHOLD_PERCENT:
                        if leg_percentage > 25:
                            stats['highlights'].append(f"🦵 **LEG DESTROYER**: {leg_shot_king['member'].display_name} ({leg_shot_king['legshots']} leg shots, {leg_percentage:.1f}%) - Ankle Biter!")
                        else:
                            stats['highlights'].append(f"🦵 **Leg Shot Specialist**: {leg_shot_king['member'].display_name} ({leg_shot_king['legshots']} leg shots, {leg_percentage:.1f}%)")
                
                # Enhanced headshot accuracy
                headshot_ace = max(player_stats, key=lambda x: x['headshots'] / max(x['headshots'] + x['bodyshots'] + x['legshots'], 1))
                total_shots_player = headshot_ace['headshots'] + headshot_ace['bodyshots'] + headshot_ace['legshots']
                if total_shots_player > 20:  # Only if they took enough shots
                    hs_percentage = (headshot_ace['headshots'] / total_shots_player) * 100
                    if hs_percentage > 40:
                        stats['highlights'].append(f"🎯 **HEADSHOT DEMON**: {headshot_ace['member'].display_name} ({hs_percentage:.1f}% HS) - INSANE AIM!")
                    elif hs_percentage > self.HEADSHOT_THRESHOLD_PERCENT:
                        stats['highlights'].append(f"🎯 **Headshot Machine**: {headshot_ace['member'].display_name} ({hs_percentage:.1f}% HS accuracy)")
                
                # Support player recognition
                assist_king = max(player_stats, key=lambda x: x['assists'])
                if assist_king['assists'] >= 10:
                    stats['highlights'].append(f"🤝 **SUPPORT HERO**: {assist_king['member'].display_name} ({assist_king['assists']} assists) - Team Player!")
                elif assist_king['assists'] >= 7:
                    stats['highlights'].append(f"🤝 **Team Player**: {assist_king['member'].display_name} ({assist_king['assists']} assists)")
                
                # Multi-kill detection (estimated)
                potential_ace = max(player_stats, key=lambda x: x['kills'])
                if potential_ace['kills'] >= 25:  # Very high kill count suggests aces
                    stats['highlights'].append(f"🔥 **ACE ALERT**: {potential_ace['member'].display_name} likely got an ACE! ({potential_ace['kills']} total kills)")
                elif potential_ace['kills'] >= 20:
                    stats['highlights'].append(f"⚡ **MULTIKILL MASTER**: {potential_ace['member'].display_name} probably got some 4Ks! ({potential_ace['kills']} kills)")
            
            # Enhanced damage analysis
            tank_player = max(player_stats, key=lambda x: x['damage_received'])
            glass_cannon = None
            
            # Find glass cannon (high damage dealt, high damage taken)
            for p in player_stats:
                if p['damage_made'] > 3000 and p['damage_received'] > self.HIGH_DAMAGE_THRESHOLD:
                    glass_cannon = p
                    break
            
            if glass_cannon:
                ratio = glass_cannon['damage_made'] / max(glass_cannon['damage_received'], 1)
                stats['highlights'].append(f"💎 **GLASS CANNON**: {glass_cannon['member'].display_name} ({glass_cannon['damage_made']:,}D dealt, {glass_cannon['damage_received']:,}D taken)")
            elif tank_player['damage_received'] > self.HIGH_DAMAGE_THRESHOLD:
                if tank_player['damage_received'] > 4000:
                    stats['highlights'].append(f"🛡️ **HUMAN FORTRESS**: {tank_player['member'].display_name} ({tank_player['damage_received']:,} damage tanked) - UNMOVABLE!")
                else:
                    stats['highlights'].append(f"🛡️ **Human Shield**: {tank_player['member'].display_name} ({tank_player['damage_received']:,} damage taken)")
            
            # Economic efficiency (low deaths with good damage)
            efficient_player = min(player_stats, key=lambda x: x['deaths'] / max(x['damage_made'], 1))
            if efficient_player['deaths'] <= 12 and efficient_player['damage_made'] >= 2500:
                efficiency = efficient_player['damage_made'] / max(efficient_player['deaths'], 1)
                stats['highlights'].append(f"💰 **ECONOMY MASTER**: {efficient_player['member'].display_name} ({efficiency:.0f} damage per death) - Efficient!")
            
            # NEW FUN HIGHLIGHTS
            
            # The Survivor (lowest deaths)
            survivor = min(player_stats, key=lambda x: x['deaths'])
            if survivor['deaths'] <= 8 and len(player_stats) >= 3:
                if survivor['deaths'] <= 5:
                    stats['highlights'].append(f"🛡️ **IMMORTAL**: {survivor['member'].display_name} ({survivor['deaths']} deaths) - Untouchable!")
                else:
                    stats['highlights'].append(f"💚 **Survivor**: {survivor['member'].display_name} ({survivor['deaths']} deaths) - Hard to kill!")
            
            # The Feeder (highest deaths with humor)
            feeder = max(player_stats, key=lambda x: x['deaths'])
            if feeder['deaths'] >= 20 and len(player_stats) >= 3:
                if feeder['deaths'] >= 25:
                    stats['highlights'].append(f"💀 **SACRIFICE**: {feeder['member'].display_name} ({feeder['deaths']} deaths) - Taking one for the team!")
                else:
                    stats['highlights'].append(f"😵 **Brave Soul**: {feeder['member'].display_name} ({feeder['deaths']} deaths) - No fear!")
            
            # Score Leader (highest combat score)
            score_leader = max(player_stats, key=lambda x: x['score'])
            if score_leader['score'] >= 300:
                if score_leader['score'] >= 400:
                    stats['highlights'].append(f"🌟 **MVP PERFORMANCE**: {score_leader['member'].display_name} ({score_leader['score']} ACS) - LEGENDARY!")
                else:
                    stats['highlights'].append(f"⭐ **Score Leader**: {score_leader['member'].display_name} ({score_leader['score']} ACS)")
            
            # Kill/Death ratio extremes
            kd_ratios = [(p, p['kills'] / max(p['deaths'], 1)) for p in player_stats]
            best_kd = max(kd_ratios, key=lambda x: x[1])
            worst_kd = min(kd_ratios, key=lambda x: x[1])
            
            if best_kd[1] >= 2.5 and best_kd[0]['kills'] >= 15:
                stats['highlights'].append(f"🔥 **K/D MONSTER**: {best_kd[0]['member'].display_name} ({best_kd[1]:.2f} K/D) - Unstoppable!")
            
            # The Spray Master (most bodyshots)
            spray_master = max(player_stats, key=lambda x: x['bodyshots'])
            total_shots_spray = spray_master['headshots'] + spray_master['bodyshots'] + spray_master['legshots']
            if total_shots_spray > 30:
                body_percentage = (spray_master['bodyshots'] / total_shots_spray) * 100
                if body_percentage > 60:
                    stats['highlights'].append(f"🎯 **SPRAY CONTROL**: {spray_master['member'].display_name} ({body_percentage:.1f}% body shots) - Consistent aim!")
            
            # Damage vs Score efficiency
            for p in player_stats:
                if p['damage_made'] > 0 and p['score'] > 0:
                    damage_per_score = p['damage_made'] / p['score']
                    if damage_per_score > 12:  # High damage per score point
                        stats['highlights'].append(f"💥 **DAMAGE EFFICIENT**: {p['member'].display_name} (High damage-to-score ratio) - Pure DPS!")
                        break
            
            # The Clutch Factor (low assists but high kills - potential clutch player)
            for p in player_stats:
                if p['kills'] >= 15 and p['assists'] <= 5 and p['kills'] > p['assists'] * 2:
                    stats['highlights'].append(f"🎭 **LONE WOLF**: {p['member'].display_name} ({p['kills']} kills, {p['assists']} assists) - Solo carry!")
                    break
            
            # Agent-specific fun facts
            agent_counts = {}
            for p in player_stats:
                agent = p['agent']
                if agent not in agent_counts:
                    agent_counts[agent] = []
                agent_counts[agent].append(p)
            
            # Duelist performance
            duelist_agents = ['Jett', 'Reyna', 'Phoenix', 'Raze', 'Yoru', 'Neon', 'Iso']
            duelists = [p for p in player_stats if p['agent'] in duelist_agents]
            if duelists:
                top_duelist = max(duelists, key=lambda x: x['kills'])
                if top_duelist['kills'] >= 20:
                    stats['highlights'].append(f"⚔️ **DUELIST DIFF**: {top_duelist['member'].display_name} ({top_duelist['agent']}) - Entry fragging king!")
            
            # Controller performance (high assists)
            controller_agents = ['Brimstone', 'Omen', 'Viper', 'Astra', 'Harbor', 'Clove']
            controllers = [p for p in player_stats if p['agent'] in controller_agents]
            if controllers:
                top_controller = max(controllers, key=lambda x: x['assists'])
                if top_controller['assists'] >= 12:
                    stats['highlights'].append(f"🧠 **BIG BRAIN**: {top_controller['member'].display_name} ({top_controller['agent']}) - Tactical genius!")
            
            # Sentinel/Initiator highlights
            sentinel_agents = ['Killjoy', 'Cypher', 'Sage', 'Chamber', 'Deadlock', 'Vyse']
            sentinels = [p for p in player_stats if p['agent'] in sentinel_agents]
            if sentinels:
                top_sentinel = max(sentinels, key=lambda x: x['score'])
                if top_sentinel['score'] >= 300:
                    stats['highlights'].append(f"🔒 **SITE ANCHOR**: {top_sentinel['member'].display_name} ({top_sentinel['agent']}) - Holding it down!")
            
            # The Balanced Player (good at everything)
            for p in player_stats:
                if (p['kills'] >= 15 and p['assists'] >= 8 and p['deaths'] <= 15 and 
                    p['damage_made'] >= 2500):
                    stats['highlights'].append(f"⚖️ **COMPLETE PLAYER**: {p['member'].display_name} - Excels in all areas!")
                    break
            
            # The Damage Dealer with Low Impact (high damage, low kills)
            for p in player_stats:
                if p['damage_made'] >= 3000 and p['kills'] <= 12:
                    stats['highlights'].append(f"💢 **DAMAGE DEALER**: {p['member'].display_name} ({p['damage_made']:,} damage, {p['kills']} kills) - Setting up teammates!")
                    break
            
            # The Finisher (low damage but high kills - good at finishing)
            for p in player_stats:
                if p['kills'] >= 18 and p['damage_made'] <= 2500:
                    efficiency_ratio = p['kills'] / (p['damage_made'] / 1000)
                    stats['highlights'].append(f"🎯 **THE FINISHER**: {p['member'].display_name} - Efficient eliminations!")
                    break
            
            # Match intensity metrics
            total_team_damage = sum(p['damage_made'] for p in player_stats)
            total_team_kills = sum(p['kills'] for p in player_stats)
            total_team_deaths = sum(p['deaths'] for p in player_stats)
            
            # Fun match facts with more personality
            fun_facts = [
                f"💥 **Team Devastation**: {total_team_damage:,} total damage dealt!",
                f"⚔️ **Combined Scoreline**: {total_team_kills}/{total_team_deaths} K/D",
                f"🦸 **Agent Squad**: {', '.join(set(p['agent'] for p in player_stats))}"
            ]
            
            # Add more fun statistical insights
            total_team_assists = sum(p['assists'] for p in player_stats)
            total_team_headshots = sum(p['headshots'] for p in player_stats)
            total_team_bodyshots = sum(p['bodyshots'] for p in player_stats)
            total_team_legshots = sum(p['legshots'] for p in player_stats)
            total_team_score = sum(p['score'] for p in player_stats)
            
            # Team KDA
            team_kda = (total_team_kills + total_team_assists) / max(total_team_deaths, 1)
            if team_kda >= 2.0:
                fun_facts.append(f"👑 **Team KDA**: {team_kda:.2f} - Dominant performance!")
            elif team_kda >= 1.5:
                fun_facts.append(f"💪 **Team KDA**: {team_kda:.2f} - Solid teamwork!")
            else:
                fun_facts.append(f"⚔️ **Team KDA**: {team_kda:.2f} - Hard fought!")
            
            # Accuracy insights
            if total_shots > 0:
                team_hs_rate = (total_team_headshots / total_shots) * 100
                team_accuracy_type = ""
                if team_hs_rate >= 25:
                    team_accuracy_type = "🎯 **LASER PRECISION**"
                elif team_hs_rate >= 20:
                    team_accuracy_type = "🔥 **Sharp Shooting**"
                elif team_hs_rate >= 15:
                    team_accuracy_type = "💪 **Decent Aim**"
                else:
                    team_accuracy_type = "🎲 **Spray & Pray**"
                
                fun_facts.append(f"{team_accuracy_type}: {team_hs_rate:.1f}% headshot rate")
            
            # Damage distribution
            avg_damage = total_team_damage / len(player_stats)
            if avg_damage >= 3500:
                fun_facts.append("💀 **DAMAGE GODS**: Everyone hitting hard!")
            elif avg_damage >= 2500:
                fun_facts.append("💥 **Balanced Attack**: Even damage spread!")
            
            # Score distribution
            avg_score = total_team_score / len(player_stats)
            if avg_score >= 350:
                fun_facts.append("🌟 **ALL-STAR LINEUP**: High scoring across the board!")
            elif avg_score >= 250:
                fun_facts.append("⭐ **Solid Squad**: Consistent performance!")
            
            # Fun team dynamics
            kill_spread = max(p['kills'] for p in player_stats) - min(p['kills'] for p in player_stats)
            if kill_spread <= 5:
                fun_facts.append("🤝 **TEAM EFFORT**: Kills spread evenly!")
            elif kill_spread >= 15:
                fun_facts.append("🎭 **CARRY MODE**: Someone's doing the heavy lifting!")
            
            # Deaths analysis
            total_team_damage_taken = sum(p['damage_received'] for p in player_stats)
            if total_team_damage_taken > 20000:
                fun_facts.append("🛡️ **BULLET SPONGES**: Tank squad activated!")
            
            # Add intensity rating
            if total_team_damage > 15000:
                fun_facts.append("🔥 **INTENSITY**: OFF THE CHARTS!")
            elif total_team_damage > 10000:
                fun_facts.append("⚡ **INTENSITY**: High-octane match!")
            
            # Round-based insights (if available)
            rounds_played = match_data.get('metadata', {}).get('rounds_played', 0)
            if rounds_played > 0:
                avg_kills_per_round = total_team_kills / rounds_played
                if avg_kills_per_round >= 3.0:
                    fun_facts.append(f"🔥 **ROUND DOMINATION**: {avg_kills_per_round:.1f} kills/round!")
                elif avg_kills_per_round >= 2.0:
                    fun_facts.append(f"💪 **STEADY PRESSURE**: {avg_kills_per_round:.1f} kills/round")
            
            # Economic warfare
            if total_team_deaths <= 60:  # Low team deaths
                fun_facts.append("💰 **ECONOMY KINGS**: Minimal losses!")
            elif total_team_deaths >= 100:
                fun_facts.append("💸 **HIGH RISK, HIGH REWARD**: Going for broke!")
            
            
            stats['highlights'].extend(random.sample(fun_facts, min(2, len(fun_facts))))
        
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
            
            # Send notification message
            hours = int(inactivity_duration.total_seconds() // 3600)
            minutes = int((inactivity_duration.total_seconds() % 3600) // 60)
            
            auto_end_message = (
                f"🤖 **Auto-ended inactive stack** after {hours}h {minutes}m of no games detected.\n"
                f"Start a new session with `/st` when you're ready to play again!"
            )
            
            await channel.send(auto_end_message)
            logging.info(f"Auto-ended inactive stack in channel {channel.id} after {inactivity_duration}")
            
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