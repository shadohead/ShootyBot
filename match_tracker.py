import asyncio
import logging
import discord
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from valorant_client import valorant_client
import random
from utils import log_error, format_time_ago
from context_manager import context_manager

class MatchTracker:
    """Tracks Discord members' Valorant matches by polling for newly completed games in active shooty stacks"""
    
    # Configuration constants
    CHECK_INTERVAL_SECONDS = 60  # 1 minute
    MATCH_CUTOFF_HOURS = 2
    MIN_DISCORD_MEMBERS = 2
    LEG_SHOT_THRESHOLD_PERCENT = 15
    HEADSHOT_THRESHOLD_PERCENT = 30
    HIGH_DAMAGE_THRESHOLD = 3000
    
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        self.tracked_members: Dict[int, Dict[str, Any]] = {}  # {member_id: {'last_checked': datetime, 'last_match_id': str}}
        self.recent_matches: Dict[int, Dict[str, Dict[str, Any]]] = {}   # {server_id: {match_id: {'timestamp': datetime, 'members': []}}}
        self.check_interval: int = self.CHECK_INTERVAL_SECONDS
        self.running: bool = False
        
    async def start_tracking(self) -> None:
        """Start the background match tracking task"""
        if self.running:
            return
        
        self.running = True
        logging.info("Starting match tracker with 1-minute polling for active shooty stacks...")
        
        while self.running:
            try:
                await self._check_all_servers()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                log_error("in match tracker", e)
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    def stop_tracking(self) -> None:
        """Stop the background match tracking"""
        self.running = False
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
                    if started_at:
                        try:
                            match_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                            if match_time < cutoff_time:
                                continue
                        except:
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
        match_timestamp = None
        if game_start:
            try:
                match_timestamp = datetime.fromisoformat(game_start.replace('Z', '+00:00'))
            except:
                match_timestamp = datetime.now(timezone.utc)
        else:
            match_timestamp = datetime.now(timezone.utc)
        
        # Calculate relative time
        if match_timestamp:
            time_ago_str = format_time_ago(match_timestamp)
        else:
            time_ago_str = "Recently"
        
        embed = discord.Embed(
            title="🎯 Match Results",
            description=f"**{map_name}** • {rounds_played} rounds • {duration_str} • {time_ago_str}",
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
        for dm in discord_members:
            member = dm['member']
            player_data = dm['player_data']
            stats = player_data.get('stats', {})
            
            kda = f"{stats.get('kills', 0)}/{stats.get('deaths', 0)}/{stats.get('assists', 0)}"
            member_list.append(f"• **{member.display_name}**: {kda}")
        
        embed.add_field(
            name=f"👥 Discord Squad ({len(discord_members)})",
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
            
            # Add intensity rating
            if total_team_damage > 15000:
                fun_facts.append("🔥 **INTENSITY**: OFF THE CHARTS!")
            elif total_team_damage > 10000:
                fun_facts.append("⚡ **INTENSITY**: High-octane match!")
            
            # Add agent diversity fun fact
            unique_agents = set(p['agent'] for p in player_stats)
            if len(unique_agents) == len(player_stats):
                fun_facts.append(f"🌈 **AGENT DIVERSITY**: Perfect variety! ({len(unique_agents)} different agents)")
            
            stats['highlights'].extend(random.sample(fun_facts, min(2, len(fun_facts))))
        
        return stats
    
    async def manual_check_recent_match(self, guild: discord.Guild, member: discord.Member = None) -> Optional[discord.Embed]:
        """Manually check for a recent match and return embed if found"""
        members_to_check = [member] if member else []
        
        if not member:
            # Check all members with linked accounts
            for m in guild.members:
                if not m.bot and valorant_client.get_all_linked_accounts(m.id):
                    members_to_check.append(m)
        
        if not members_to_check:
            return None
        
        # Check the most recent match for each member
        for member in members_to_check:
            try:
                primary_account = valorant_client.get_linked_account(member.id)
                if not primary_account:
                    continue
                
                matches = await valorant_client.get_match_history(
                    primary_account['username'],
                    primary_account['tag'],
                    size=1,
                    mode='competitive'  # Only check competitive matches
                )
                
                if not matches:
                    continue
                
                match = matches[0]
                
                # Find Discord members in this match
                discord_members_in_match = await self._find_discord_members_in_match(guild, match)
                
                if len(discord_members_in_match) >= 1:
                    embed = await self._create_match_embed(match, discord_members_in_match)
                    # Add manual check indicator
                    if embed:
                        embed.set_footer(text="🔍 Manual match lookup • ShootyBot")
                    return embed
                    
            except Exception as e:
                log_error(f"in manual check for {member.display_name}", e)
        
        return None

# Global match tracker instance
match_tracker = None

def get_match_tracker(bot: discord.Client) -> MatchTracker:
    """Get or create the global match tracker instance"""
    global match_tracker
    if match_tracker is None:
        match_tracker = MatchTracker(bot)
    return match_tracker