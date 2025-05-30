import logging
from typing import Optional, Dict, Any, List
import discord
from data_manager import data_manager
from config import HENRIK_API_KEY
from utils import log_error
from api_clients import BaseAPIClient, RateLimitInfo, APIResponse

class ValorantClient(BaseAPIClient):
    """Client for interacting with Henrik's Valorant API"""
    
    def __init__(self):
        # Henrik API rate limits: 100 requests per 2 minutes for free tier
        # Advanced tier has higher limits
        rate_limit = RateLimitInfo(
            requests_per_second=1.0,
            requests_per_minute=50 if HENRIK_API_KEY else 30,
            requests_per_hour=1500 if HENRIK_API_KEY else 600,
            burst_limit=5
        )
        
        super().__init__(
            base_url="https://api.henrikdev.xyz/valorant/v1",
            api_key=HENRIK_API_KEY,
            rate_limit=rate_limit,
            timeout=30
        )
        
        if HENRIK_API_KEY:
            logging.info("Using Henrik API with Advanced key")
        else:
            logging.info("Using Henrik API Basic tier (no key)")
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get current headers for backward compatibility with tests."""
        return self._get_default_headers()
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for Henrik API."""
        if self.api_key:
            return {'Authorization': self.api_key}
        return {}
    
    async def health_check(self) -> bool:
        """Check if the Henrik API is healthy."""
        try:
            # Use a simple endpoint to check API health
            response = await self.get('status', use_cache=False, cache_ttl=0)
            return response.success
        except Exception:
            # If no status endpoint, try a basic query
            try:
                response = await self.get('account/test/0000', use_cache=False, cache_ttl=0)
                # Even 404 means API is responding
                return response.status_code in [200, 404]
            except Exception:
                return False
    
    async def get_account_info(self, username: str, tag: str) -> Optional[Dict[str, Any]]:
        """Get account information by username and tag"""
        try:
            response = await self.get(f'account/{username}/{tag}', cache_ttl=300)
            
            if response.success:
                # Henrik API wraps data in 'data' field
                if 'data' in response.data:
                    return response.data['data']
                return response.data
            elif response.status_code == 401:
                log_error("Henrik API authentication", Exception("API key needed"))
                return None
            elif response.status_code == 404:
                logging.warning(f"Valorant account not found: {username}#{tag}")
                return None
            else:
                log_error(f"Valorant API request", Exception(f"Status {response.status_code}"))
                return None
                
        except Exception as e:
            log_error("fetching Valorant account info", e)
            return None
    
    async def get_account_by_puuid(self, puuid: str) -> Optional[Dict[str, Any]]:
        """Get account information by PUUID"""
        try:
            response = await self.get(f'by-puuid/account/{puuid}', cache_ttl=300)
            
            if response.success:
                # Henrik API wraps data in 'data' field
                if 'data' in response.data:
                    return response.data['data']
                return response.data
            else:
                log_error("fetching account by PUUID", Exception(f"Status {response.status_code}"))
                return None
                
        except Exception as e:
            log_error("fetching account by PUUID", e)
            return None
    
    async def link_account(self, discord_id: int, username: str, tag: str) -> Dict[str, Any]:
        """Link a Discord user to a Valorant account"""
        # Remove # if user included it
        if tag.startswith('#'):
            tag = tag[1:]
        
        # Get account info from API
        account_info = await self.get_account_info(username, tag)
        
        if not account_info:
            return {
                'success': False,
                'error': 'Henrik API now requires authentication. Please get an API key from https://docs.henrikdev.xyz and add it to your .env file as HENRIK_API_KEY=your_key_here'
            }
        
        # Extract relevant data
        puuid = account_info.get('puuid')
        name = account_info.get('name', username)
        actual_tag = account_info.get('tag', tag)
        
        if not puuid:
            return {
                'success': False,
                'error': 'Invalid account data from API'
            }
        
        # Save to data manager
        user_data = data_manager.get_user(discord_id)
        user_data.link_valorant_account(name, actual_tag, puuid)
        data_manager.save_user(discord_id)
        
        return {
            'success': True,
            'username': name,
            'tag': actual_tag,
            'puuid': puuid,
            'card': account_info.get('card', {})
        }
    
    async def unlink_account(self, discord_id: int) -> bool:
        """Unlink a Discord user's Valorant account"""
        try:
            user_data = data_manager.get_user(discord_id)
            user_data.valorant_username = None
            user_data.valorant_tag = None
            user_data.valorant_puuid = None
            data_manager.save_user(discord_id)
            return True
        except Exception as e:
            log_error(f"unlinking account for {discord_id}", e)
            return False
    
    def get_linked_account(self, discord_id: int) -> Optional[Dict[str, str]]:
        """Get primary linked Valorant account for a Discord user"""
        user_data = data_manager.get_user(discord_id)
        return user_data.get_primary_account()
    
    def get_all_linked_accounts(self, discord_id: int) -> List[Dict[str, str]]:
        """Get all linked Valorant accounts for a Discord user"""
        user_data = data_manager.get_user(discord_id)
        return user_data.get_all_accounts()
    
    def is_playing_valorant(self, member: discord.Member) -> bool:
        """Check if a Discord member is currently playing Valorant"""
        if not member.activities:
            return False
        
        for activity in member.activities:
            if isinstance(activity, discord.Game):
                if activity.name and 'valorant' in activity.name.lower():
                    return True
            elif isinstance(activity, discord.Activity):
                if activity.name and 'valorant' in activity.name.lower():
                    return True
        
        return False
    
    def get_playing_members(self, guild: discord.Guild) -> list:
        """Get list of members currently playing Valorant"""
        playing_members = []
        
        for member in guild.members:
            if self.is_playing_valorant(member):
                playing_members.append(member)
        
        return playing_members
    
    async def get_match_history(self, username: str, tag: str, size: int = 5, mode: str = None) -> Optional[List[Dict[str, Any]]]:
        """Get match history for a player
        
        Args:
            username: Valorant username
            tag: Valorant tag
            size: Number of matches to fetch (default 5)
            mode: Game mode filter (competitive, unrated, replication, etc.)
        """
        try:
            # Match history uses v3 API with different base URL
            # Temporarily change the base URL for this request
            original_base_url = self.base_url
            self.base_url = "https://api.henrikdev.xyz/valorant/v3"
            
            try:
                params = {'size': size}
                if mode:
                    params['filter'] = mode
                    
                response = await self.get(
                    f'matches/na/{username}/{tag}',
                    params=params,
                    cache_ttl=180  # Cache for 3 minutes
                )
                
                if response.success:
                    # Henrik API wraps data in 'data' field
                    if 'data' in response.data:
                        return response.data['data']
                    return response.data
                else:
                    log_error("fetching match history", Exception(f"Status {response.status_code}"))
                    return None
            finally:
                # Restore original base URL
                self.base_url = original_base_url
                
        except Exception as e:
            log_error("fetching match history", e)
            return None
    
    def calculate_player_stats(self, matches: List[Dict[str, Any]], player_puuid: str, competitive_only: bool = True) -> Dict[str, Any]:
        """Calculate comprehensive player statistics from match history
        
        Args:
            matches: List of match data from API
            player_puuid: Player's PUUID to find in matches
            competitive_only: If True, only calculate stats from competitive matches
        """
        if not matches:
            return {}
        
        stats = {
            'total_matches': 0,
            'wins': 0,
            'losses': 0,
            'total_kills': 0,
            'total_deaths': 0,
            'total_assists': 0,
            'total_headshots': 0,
            'total_bodyshots': 0,
            'total_legshots': 0,
            'total_score': 0,
            'total_rounds': 0,
            'total_damage_made': 0,
            'total_damage_received': 0,
            'kast_rounds': 0,  # Rounds with Kill, Assist, Survived, or Traded
            'maps_played': {},
            'agents_played': {},
            'recent_matches': [],
            # Enhanced stats
            'multikills': {'2k': 0, '3k': 0, '4k': 0, '5k': 0},
            'clutches_attempted': {'1v2': 0, '1v3': 0, '1v4': 0, '1v5': 0},
            'clutches_won': {'1v2': 0, '1v3': 0, '1v4': 0, '1v5': 0},
            'first_bloods': 0,
            'first_deaths': 0,
            'total_rounds_played': 0,
            'rounds_survived': 0,
            'mvp_count': 0,
            'match_mvp_count': 0,
            'pistol_rounds_won': 0,
            'pistol_rounds_played': 0,
            'eco_rounds_won': 0,
            'eco_rounds_played': 0,
            'current_win_streak': 0,
            'current_loss_streak': 0,
            'max_win_streak': 0,
            'max_loss_streak': 0,
            'agent_performance': {},
            'map_performance': {},
            'total_shots_fired': 0,
            'total_shots_hit': 0
        }
        
        for match in matches:
            if not match.get('is_available', True):
                continue
            
            # Filter by game mode if requested
            if competitive_only:
                metadata = match.get('metadata', {})
                mode = metadata.get('mode', '').lower()
                mode_id = metadata.get('mode_id', '').lower()
                queue = metadata.get('queue', '').lower()
                
                # Skip non-competitive matches
                if not any('competitive' in field for field in [mode, mode_id, queue]):
                    continue
                
            # Find the player in this match
            player_data = None
            all_players = match.get('players', {}).get('all_players', [])
            
            for player in all_players:
                if player.get('puuid') == player_puuid:
                    player_data = player
                    break
            
            if not player_data:
                continue
            
            stats['total_matches'] += 1
            player_stats = player_data.get('stats', {})
            
            # Basic stats
            kills = player_stats.get('kills', 0)
            deaths = player_stats.get('deaths', 0)
            assists = player_stats.get('assists', 0)
            headshots = player_stats.get('headshots', 0)
            bodyshots = player_stats.get('bodyshots', 0)
            legshots = player_stats.get('legshots', 0)
            score = player_stats.get('score', 0)
            
            # Damage stats
            damage_made = player_data.get('damage_made', 0)
            damage_received = player_data.get('damage_received', 0)
            
            stats['total_kills'] += kills
            stats['total_deaths'] += deaths
            stats['total_assists'] += assists
            stats['total_headshots'] += headshots
            stats['total_bodyshots'] += bodyshots
            stats['total_legshots'] += legshots
            stats['total_score'] += score
            stats['total_damage_made'] += damage_made
            stats['total_damage_received'] += damage_received
            
            # Win/Loss calculation
            player_team = player_data.get('team', 'Red')
            teams = match.get('teams', {})
            
            if player_team.lower() in teams:
                team_data = teams[player_team.lower()]
                if team_data.get('has_won', False):
                    stats['wins'] += 1
                else:
                    stats['losses'] += 1
            
            # Map tracking
            map_name = match.get('metadata', {}).get('map', 'Unknown')
            stats['maps_played'][map_name] = stats['maps_played'].get(map_name, 0) + 1
            
            # Agent tracking
            agent_name = player_data.get('character', 'Unknown')
            stats['agents_played'][agent_name] = stats['agents_played'].get(agent_name, 0) + 1
            
            # Rounds for KAST calculation
            rounds_played = match.get('metadata', {}).get('rounds_played', 0)
            stats['total_rounds'] += rounds_played
            stats['total_rounds_played'] += rounds_played
            
            # KAST calculation: estimated rounds where player had impact
            # Since we don't have round-by-round data, we estimate based on KDA contribution
            # This is an approximation: assume player had impact in proportion to their team contribution
            if rounds_played > 0 and (kills > 0 or assists > 0):
                # Estimate KAST rounds based on kill/assist participation
                # Assume each kill/assist represents impact in that round, capped by total rounds
                estimated_kast_rounds = min(rounds_played, kills + assists)
                stats['kast_rounds'] += estimated_kast_rounds
            
            # Enhanced tracking
            match_won = teams.get(player_team.lower(), {}).get('has_won', False) if player_team.lower() in teams else False
            
            # Calculate advanced stats for this match
            self._calculate_match_advanced_stats(match, player_data, stats, rounds_played, match_won)
            
            # Agent performance tracking
            if agent_name not in stats['agent_performance']:
                stats['agent_performance'][agent_name] = {
                    'matches': 0, 'wins': 0, 'kills': 0, 'deaths': 0, 'assists': 0, 
                    'damage': 0, 'score': 0
                }
            
            agent_stats = stats['agent_performance'][agent_name]
            agent_stats['matches'] += 1
            if match_won:
                agent_stats['wins'] += 1
            agent_stats['kills'] += kills
            agent_stats['deaths'] += deaths
            agent_stats['assists'] += assists
            agent_stats['damage'] += damage_made
            agent_stats['score'] += score
            
            # Map performance tracking
            if map_name not in stats['map_performance']:
                stats['map_performance'][map_name] = {
                    'matches': 0, 'wins': 0, 'kills': 0, 'deaths': 0, 'damage': 0
                }
            
            map_stats = stats['map_performance'][map_name]
            map_stats['matches'] += 1
            if match_won:
                map_stats['wins'] += 1
            map_stats['kills'] += kills
            map_stats['deaths'] += deaths
            map_stats['damage'] += damage_made
            
            # Store recent match info
            stats['recent_matches'].append({
                'map': map_name,
                'agent': agent_name,
                'kills': kills,
                'deaths': deaths,
                'assists': assists,
                'score': score,
                'damage_made': damage_made,
                'damage_received': damage_received,
                'rounds_played': rounds_played,
                'won': match_won
            })
        
        # Calculate win/loss streaks
        self._calculate_streaks(stats)
        
        # Calculate derived stats
        if stats['total_matches'] > 0:
            stats['win_rate'] = (stats['wins'] / stats['total_matches']) * 100
            stats['avg_kills'] = stats['total_kills'] / stats['total_matches']
            stats['avg_deaths'] = stats['total_deaths'] / stats['total_matches']
            stats['avg_assists'] = stats['total_assists'] / stats['total_matches']
            stats['avg_score'] = stats['total_score'] / stats['total_matches']
            stats['avg_damage_made'] = stats['total_damage_made'] / stats['total_matches']
            stats['avg_damage_received'] = stats['total_damage_received'] / stats['total_matches']
            
            # Calculate enhanced derived stats
            stats['clutch_success_rate'] = self._calculate_clutch_success_rate(stats)
            # First blood rate: percentage of rounds where player got first blood
            if stats['total_rounds_played'] > 0:
                stats['first_blood_rate'] = (stats['first_bloods'] / stats['total_rounds_played']) * 100
            else:
                stats['first_blood_rate'] = 0
            # Survival rate: estimate based on deaths per round across all matches
            # Use actual match rounds for accurate calculation
            actual_match_rounds = sum(match.get('metadata', {}).get('rounds_played', 0) for match in matches if match.get('is_available', True) and self._player_in_match(match, player_puuid))
            if actual_match_rounds > 0:
                # Calculate estimated survival rate based on total deaths vs total rounds
                death_rate = stats['total_deaths'] / actual_match_rounds
                # Survival rate = percentage of rounds where player didn't die
                stats['survival_rate'] = max(0, (1.0 - death_rate) * 100)
            else:
                stats['survival_rate'] = 0
            
            if stats['pistol_rounds_played'] > 0:
                stats['pistol_win_rate'] = (stats['pistol_rounds_won'] / stats['pistol_rounds_played']) * 100
            else:
                stats['pistol_win_rate'] = 0
                
            if stats['eco_rounds_played'] > 0:
                stats['eco_win_rate'] = (stats['eco_rounds_won'] / stats['eco_rounds_played']) * 100
            else:
                stats['eco_win_rate'] = 0
                
            # Calculate accuracy (shots hit / shots fired)
            if stats['total_shots_fired'] > 0:
                stats['accuracy'] = (stats['total_shots_hit'] / stats['total_shots_fired']) * 100
            else:
                stats['accuracy'] = 0
                
            # Calculate performance ratings
            stats['performance_ratings'] = self._calculate_performance_ratings(stats)
            
            # Calculate DD (Damage Delta) - difference per round between damage dealt and received
            # Use only the actual match rounds, not the estimated enhanced rounds
            actual_match_rounds = sum(match.get('metadata', {}).get('rounds_played', 0) for match in matches if match.get('is_available', True) and self._player_in_match(match, player_puuid))
            if actual_match_rounds > 0:
                stats['damage_delta_per_round'] = (stats['total_damage_made'] - stats['total_damage_received']) / actual_match_rounds
            else:
                stats['damage_delta_per_round'] = 0
            
            # Calculate ACS (Average Combat Score) - simplified Valorant formula
            # ACS is roughly: (ADR + (K/D ratio * 50) + (First Kills * 5)) but we'll use a simplified version
            # Basic formula: (Damage per round + Kill contribution + Assist contribution)
            if actual_match_rounds > 0:
                adr = stats['total_damage_made'] / actual_match_rounds
                kill_contribution = (stats['total_kills'] / actual_match_rounds) * 70  # Kills are worth ~70 ACS per round
                assist_contribution = (stats['total_assists'] / actual_match_rounds) * 25  # Assists worth ~25 ACS per round
                stats['acs'] = adr + kill_contribution + assist_contribution
            else:
                stats['acs'] = 0
            
            if stats['total_deaths'] > 0:
                stats['kd_ratio'] = stats['total_kills'] / stats['total_deaths']
                stats['kda_ratio'] = (stats['total_kills'] + stats['total_assists']) / stats['total_deaths']
            else:
                stats['kd_ratio'] = float(stats['total_kills'])
                stats['kda_ratio'] = float(stats['total_kills'] + stats['total_assists'])
            
            total_shots = stats['total_headshots'] + stats['total_bodyshots'] + stats['total_legshots']
            if total_shots > 0:
                stats['headshot_percentage'] = (stats['total_headshots'] / total_shots) * 100
            else:
                stats['headshot_percentage'] = 0
            
            if actual_match_rounds > 0:
                stats['kast_percentage'] = (stats['kast_rounds'] / actual_match_rounds) * 100
                # Calculate ADR (Average Damage per Round)
                stats['adr'] = stats['total_damage_made'] / actual_match_rounds
            else:
                stats['kast_percentage'] = 0
                stats['adr'] = 0
        
        return stats
    
    def _player_in_match(self, match: Dict[str, Any], player_puuid: str) -> bool:
        """Check if a player is in a specific match"""
        all_players = match.get('players', {}).get('all_players', [])
        return any(player.get('puuid') == player_puuid for player in all_players)
    
    def _calculate_match_advanced_stats(self, match: Dict[str, Any], player_data: Dict[str, Any], stats: Dict[str, Any], rounds_played: int, match_won: bool):
        """Calculate advanced stats for a single match using round-by-round data"""
        player_puuid = player_data.get('puuid', '')
        
        # Get round-by-round data for accurate calculations
        rounds_data = match.get('rounds', [])
        
        if rounds_data and player_puuid:
            # Analyze each round for accurate stats
            self._analyze_rounds_for_player(rounds_data, player_puuid, stats, match_won, match)
        else:
            # Fallback to basic estimations if no round data available
            self._calculate_basic_estimates(player_data, stats, rounds_played, match_won)
    
    def _analyze_rounds_for_player(self, rounds_data: List[Dict[str, Any]], player_puuid: str, stats: Dict[str, Any], match_won: bool, match_data: Dict[str, Any] = None):
        """Analyze round-by-round data for accurate first blood, clutch, and multikill calculations"""
        for round_num, round_data in enumerate(rounds_data):
            # Analyze first bloods in this round
            self._analyze_first_bloods_in_round(round_data, player_puuid, stats)
            
            # Analyze clutches in this round
            self._analyze_clutches_in_round(round_data, player_puuid, stats, match_data)
            
            # Analyze multikills in this round
            self._analyze_multikills_in_round(round_data, player_puuid, stats)
            
            # Analyze survival in this round
            self._analyze_survival_in_round(round_data, player_puuid, stats)
            
            # Analyze pistol/eco rounds
            self._analyze_economy_rounds(round_data, round_num, player_puuid, stats, match_won, match_data)
    
    def _analyze_first_bloods_in_round(self, round_data: Dict[str, Any], player_puuid: str, stats: Dict[str, Any]):
        """Analyze first blood events in a round"""
        player_stats_in_round = round_data.get('player_stats', [])
        
        # Find our player in this round
        our_player_round = None
        for ps in player_stats_in_round:
            if ps.get('player_puuid') == player_puuid:
                our_player_round = ps
                break
        
        if not our_player_round:
            return
        
        # Check kill events for first blood
        kill_events = our_player_round.get('kill_events', [])
        if not kill_events:
            return
        
        # Find the earliest kill time in the round across all players
        all_kill_times = []
        for ps in player_stats_in_round:
            for event in ps.get('kill_events', []):
                kill_time = event.get('kill_time_in_round')
                if kill_time is not None:
                    all_kill_times.append(kill_time)
        
        if not all_kill_times:
            return
        
        earliest_kill_time = min(all_kill_times)
        
        # Check if our player got the first blood
        for event in kill_events:
            kill_time = event.get('kill_time_in_round')
            if kill_time == earliest_kill_time:
                stats['first_bloods'] += 1
                break
        
        # Check if our player died first
        for ps in player_stats_in_round:
            for event in ps.get('kill_events', []):
                if (event.get('victim_puuid') == player_puuid and 
                    event.get('kill_time_in_round') == earliest_kill_time):
                    stats['first_deaths'] += 1
                    break
    
    def _analyze_clutches_in_round(self, round_data: Dict[str, Any], player_puuid: str, stats: Dict[str, Any], match_data: Dict[str, Any] = None):
        """Analyze clutch situations in a round"""
        player_stats_in_round = round_data.get('player_stats', [])
        winning_team = round_data.get('winning_team', '')
        
        # Find our player and their team
        our_player_round = None
        for ps in player_stats_in_round:
            if ps.get('player_puuid') == player_puuid:
                our_player_round = ps
                break
        
        if not our_player_round:
            return
        
        # Get all kill events in chronological order
        all_kill_events = []
        for ps in player_stats_in_round:
            for event in ps.get('kill_events', []):
                event['round_player'] = ps.get('player_puuid')
                all_kill_events.append(event)
        
        # Sort by kill time
        all_kill_events.sort(key=lambda x: x.get('kill_time_in_round', 0))
        
        # Track alive players by team throughout the round
        # This is complex without initial team info, so we'll use a simplified approach
        # Look for situations where our player got multiple kills late in the round
        our_kills_in_round = len(our_player_round.get('kill_events', []))
        
        if our_kills_in_round >= 2:
            # Simple clutch detection: if player got 2+ kills and their team won the round
            # This is a simplified approach - real clutch detection would need full team tracking
            
            # Estimate clutch situation based on kill count and round outcome
            if our_kills_in_round >= 4:
                # Likely a 1v4 or 1v5 clutch
                stats['clutches_attempted']['1v5'] += 1
                if winning_team and self._player_team_won_round(player_puuid, winning_team, match_data):
                    stats['clutches_won']['1v5'] += 1
            elif our_kills_in_round >= 3:
                # Likely a 1v3 clutch
                stats['clutches_attempted']['1v3'] += 1
                if winning_team and self._player_team_won_round(player_puuid, winning_team, match_data):
                    stats['clutches_won']['1v3'] += 1
            elif our_kills_in_round >= 2:
                # Likely a 1v2 clutch
                stats['clutches_attempted']['1v2'] += 1
                if winning_team and self._player_team_won_round(player_puuid, winning_team, match_data):
                    stats['clutches_won']['1v2'] += 1
    
    def _analyze_multikills_in_round(self, round_data: Dict[str, Any], player_puuid: str, stats: Dict[str, Any]):
        """Analyze multikill events in a round"""
        player_stats_in_round = round_data.get('player_stats', [])
        
        # Find our player in this round
        our_player_round = None
        for ps in player_stats_in_round:
            if ps.get('player_puuid') == player_puuid:
                our_player_round = ps
                break
        
        if not our_player_round:
            return
        
        # Count kills in this round
        kills_in_round = len(our_player_round.get('kill_events', []))
        
        # Record multikills
        if kills_in_round >= 5:
            stats['multikills']['5k'] += 1
        elif kills_in_round >= 4:
            stats['multikills']['4k'] += 1
        elif kills_in_round >= 3:
            stats['multikills']['3k'] += 1
        elif kills_in_round >= 2:
            stats['multikills']['2k'] += 1
    
    def _analyze_survival_in_round(self, round_data: Dict[str, Any], player_puuid: str, stats: Dict[str, Any]):
        """Analyze whether the player survived the round (didn't die)"""
        player_stats_in_round = round_data.get('player_stats', [])
        
        # Check if our player died in this round by looking at all kill events
        player_died = False
        
        for ps in player_stats_in_round:
            for event in ps.get('kill_events', []):
                if event.get('victim_puuid') == player_puuid:
                    player_died = True
                    break
            if player_died:
                break
        
        # If player didn't die, they survived the round
        if not player_died:
            stats['rounds_survived'] += 1
    
    def _analyze_economy_rounds(self, round_data: Dict[str, Any], round_num: int, player_puuid: str, stats: Dict[str, Any], match_won: bool, match_data: Dict[str, Any] = None):
        """Analyze pistol and eco rounds"""
        # Pistol rounds are rounds 0 and 12 (first round of each half)
        if round_num == 0 or round_num == 12:
            stats['pistol_rounds_played'] += 1
            
            winning_team = round_data.get('winning_team', '')
            if self._player_team_won_round(player_puuid, winning_team, match_data):
                stats['pistol_rounds_won'] += 1
        
        # Eco round detection would require economy data analysis
        # For now, we'll use a simplified approach
        player_stats_in_round = round_data.get('player_stats', [])
        for ps in player_stats_in_round:
            if ps.get('player_puuid') == player_puuid:
                economy = ps.get('economy', {})
                loadout_value = economy.get('loadout_value', 0)
                
                # Simple eco detection: low loadout value
                if loadout_value and loadout_value < 2000:  # Less than $2000 loadout
                    stats['eco_rounds_played'] += 1
                    winning_team = round_data.get('winning_team', '')
                    if self._player_team_won_round(player_puuid, winning_team, match_data):
                        stats['eco_rounds_won'] += 1
                break
    
    def _player_team_won_round(self, player_puuid: str, winning_team: str, match_data: Dict[str, Any]) -> bool:
        """Check if the player's team won the round"""
        if not winning_team or not match_data:
            return False
        
        # Get the player's team from match-level data
        player_team = self._get_player_team(player_puuid, match_data)
        if not player_team:
            return False
        
        # Check if the player's team matches the winning team
        # The winning_team format might be 'Red' or 'Blue'
        return player_team.lower() == winning_team.lower()
    
    def _get_player_team(self, player_puuid: str, match_data: Dict[str, Any]) -> str:
        """Get the team (Red/Blue) that a player is on"""
        all_players = match_data.get('players', {}).get('all_players', [])
        
        for player in all_players:
            if player.get('puuid') == player_puuid:
                return player.get('team', '')
        
        # Fallback: check team-specific player lists
        players_data = match_data.get('players', {})
        
        # Check red team
        red_players = players_data.get('red', [])
        for player in red_players:
            if player.get('puuid') == player_puuid:
                return 'Red'
        
        # Check blue team  
        blue_players = players_data.get('blue', [])
        for player in blue_players:
            if player.get('puuid') == player_puuid:
                return 'Blue'
        
        return ''
    
    def _calculate_basic_estimates(self, player_data: Dict[str, Any], stats: Dict[str, Any], rounds_played: int, match_won: bool):
        """Fallback to basic estimations if no round data available"""
        player_stats = player_data.get('stats', {})
        kills = player_stats.get('kills', 0)
        
        # Basic multikill estimation
        if rounds_played > 0:
            kpr = kills / rounds_played
            if kpr >= 2.5:  # Very high KPR suggests multikills
                if kpr >= 4:
                    stats['multikills']['5k'] += max(1, int(kills // 5))
                elif kpr >= 3:
                    stats['multikills']['4k'] += max(1, int(kills // 4))
                elif kpr >= 2.5:
                    stats['multikills']['3k'] += max(1, int(kills // 3))
                stats['multikills']['2k'] += max(1, int(kills // 2))
        
        # Basic first blood estimation
        if rounds_played > 0:
            kpr = kills / rounds_played
            if kpr >= 1.5:
                estimated_first_bloods = int(rounds_played * 0.15)
            elif kpr >= 1.0:
                estimated_first_bloods = int(rounds_played * 0.10)
            elif kpr >= 0.7:
                estimated_first_bloods = int(rounds_played * 0.06)
            else:
                estimated_first_bloods = int(rounds_played * 0.03)
            stats['first_bloods'] += max(0, estimated_first_bloods)
        
        # Basic pistol round estimation
        if rounds_played >= 2:
            stats['pistol_rounds_played'] += 2
            if match_won:
                stats['pistol_rounds_won'] += 1
        
        # Basic survival estimation (estimate rounds survived based on deaths)
        deaths = player_stats.get('deaths', 0)
        if rounds_played > 0:
            # Estimate survival rate: assume death rate correlates with deaths per round
            death_rate = deaths / rounds_played
            # Estimate rounds survived (conservative estimation)
            estimated_survival_rate = max(0.3, 1.0 - death_rate)  # At least 30% survival
            estimated_rounds_survived = int(rounds_played * estimated_survival_rate)
            stats['rounds_survived'] += estimated_rounds_survived
        
        # Shot tracking (estimate from hit stats)
        total_shots_hit = player_stats.get('headshots', 0) + player_stats.get('bodyshots', 0) + player_stats.get('legshots', 0)
        stats['total_shots_hit'] += total_shots_hit
        # Estimate shots fired (assume 60-80% accuracy for good players)
        if total_shots_hit > 0:
            estimated_shots_fired = int(total_shots_hit * 1.4)  # Assume ~70% accuracy
            stats['total_shots_fired'] += estimated_shots_fired

    def _calculate_streaks(self, stats: Dict[str, Any]):
        """Calculate win/loss streaks from recent matches"""
        recent_matches = stats.get('recent_matches', [])
        if not recent_matches:
            return
        
        # Sort by most recent first (reverse order since we append chronologically)
        recent_matches.reverse()
        
        current_streak = 0
        current_streak_type = None  # 'win' or 'loss'
        max_win_streak = 0
        max_loss_streak = 0
        temp_win_streak = 0
        temp_loss_streak = 0
        
        for match in recent_matches:
            if match['won']:
                if current_streak_type == 'win':
                    current_streak += 1
                else:
                    current_streak = 1
                    current_streak_type = 'win'
                temp_win_streak += 1
                temp_loss_streak = 0
                max_win_streak = max(max_win_streak, temp_win_streak)
            else:
                if current_streak_type == 'loss':
                    current_streak += 1
                else:
                    current_streak = 1
                    current_streak_type = 'loss'
                temp_loss_streak += 1
                temp_win_streak = 0
                max_loss_streak = max(max_loss_streak, temp_loss_streak)
        
        if current_streak_type == 'win':
            stats['current_win_streak'] = current_streak
            stats['current_loss_streak'] = 0
        else:
            stats['current_loss_streak'] = current_streak
            stats['current_win_streak'] = 0
        
        stats['max_win_streak'] = max_win_streak
        stats['max_loss_streak'] = max_loss_streak
    
    def _calculate_clutch_success_rate(self, stats: Dict[str, Any]) -> float:
        """Calculate overall clutch success rate"""
        total_attempted = sum(stats['clutches_attempted'].values())
        total_won = sum(stats['clutches_won'].values())
        
        if total_attempted > 0:
            return (total_won / total_attempted) * 100
        return 0
    
    def _calculate_performance_ratings(self, stats: Dict[str, Any]) -> Dict[str, str]:
        """Calculate fun performance ratings/badges"""
        ratings = {}
        
        # Fragger rating
        avg_kills = stats.get('avg_kills', 0)
        if avg_kills >= 20:
            ratings['fragger'] = '🔥 Demon Fragger'
        elif avg_kills >= 15:
            ratings['fragger'] = '💀 Elite Fragger'
        elif avg_kills >= 12:
            ratings['fragger'] = '⚡ Solid Fragger'
        else:
            ratings['fragger'] = '🎯 Entry Fragger'
        
        # Support rating
        avg_assists = stats.get('avg_assists', 0)
        if avg_assists >= 8:
            ratings['support'] = '👑 Support King'
        elif avg_assists >= 6:
            ratings['support'] = '🤝 Team Player'
        elif avg_assists >= 4:
            ratings['support'] = '✨ Helper'
        else:
            ratings['support'] = '🔫 Solo Player'
        
        # Survival rating
        survival_rate = stats.get('survival_rate', 0)
        if survival_rate >= 80:
            ratings['survival'] = '🛡️ Untouchable'
        elif survival_rate >= 70:
            ratings['survival'] = '🏃 Escape Artist'
        elif survival_rate >= 60:
            ratings['survival'] = '💪 Survivor'
        else:
            ratings['survival'] = '💥 Risk Taker'
        
        # Accuracy rating
        accuracy = stats.get('accuracy', 0)
        headshot_percentage = stats.get('headshot_percentage', 0)
        if headshot_percentage >= 35:
            ratings['accuracy'] = '🎯 Headshot Machine'
        elif headshot_percentage >= 25:
            ratings['accuracy'] = '🔥 Sharp Shooter'
        elif accuracy >= 70:
            ratings['accuracy'] = '💯 Precise'
        else:
            ratings['accuracy'] = '🌀 Spray Master'
        
        # Clutch rating
        clutch_rate = stats.get('clutch_success_rate', 0)
        total_clutches = sum(stats.get('clutches_won', {}).values())
        if total_clutches >= 5 and clutch_rate >= 60:
            ratings['clutch'] = '🏆 Clutch God'
        elif total_clutches >= 3 and clutch_rate >= 50:
            ratings['clutch'] = '⭐ Clutch King'
        elif total_clutches >= 1:
            ratings['clutch'] = '💎 Clutch Player'
        else:
            ratings['clutch'] = '🎲 Learning Clutches'
        
        return ratings

# Global Valorant client instance
_valorant_client_instance: Optional[ValorantClient] = None

def get_valorant_client() -> ValorantClient:
    """Get the global Valorant client instance."""
    global _valorant_client_instance
    if _valorant_client_instance is None:
        _valorant_client_instance = ValorantClient()
    return _valorant_client_instance

async def close_valorant_client() -> None:
    """Close the global Valorant client session."""
    global _valorant_client_instance
    if _valorant_client_instance is not None:
        await _valorant_client_instance.close()
        _valorant_client_instance = None

# Maintain backward compatibility
valorant_client = get_valorant_client()