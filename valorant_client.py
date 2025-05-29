import logging
import requests
from typing import Optional, Dict, Any, List
import discord
from data_manager import data_manager
from config import HENRIK_API_KEY

class ValorantClient:
    """Client for interacting with Henrik's Valorant API"""
    
    def __init__(self):
        self.base_url = "https://api.henrikdev.xyz/valorant/v1"
        self.headers = {
            'User-Agent': 'ShootyBot/1.0 (Discord Bot)'
        }
        
        # Add API key if provided (for Advanced tier)
        if HENRIK_API_KEY:
            # Try different authorization formats
            self.headers['Authorization'] = HENRIK_API_KEY
            logging.info("Using Henrik API with Advanced key")
        else:
            logging.info("Using Henrik API Basic tier (no key)")
    
    async def get_account_info(self, username: str, tag: str) -> Optional[Dict[str, Any]]:
        """Get account information by username and tag"""
        try:
            url = f"{self.base_url}/account/{username}/{tag}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    return data['data']
                return data
            elif response.status_code == 401:
                logging.error("Henrik API now requires authentication. API key needed.")
                return None
            elif response.status_code == 404:
                logging.warning(f"Valorant account not found: {username}#{tag}")
                return None
            elif response.status_code == 429:
                logging.warning("Rate limited by Valorant API")
                return None
            else:
                logging.error(f"Valorant API error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logging.error(f"Error fetching Valorant account info: {e}")
            return None
    
    async def get_account_by_puuid(self, puuid: str) -> Optional[Dict[str, Any]]:
        """Get account information by PUUID"""
        try:
            url = f"{self.base_url}/by-puuid/account/{puuid}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    return data['data']
                return data
            else:
                logging.error(f"Error fetching account by PUUID: {response.status_code}")
                return None
                
        except Exception as e:
            logging.error(f"Error fetching account by PUUID: {e}")
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
            logging.error(f"Error unlinking account for {discord_id}: {e}")
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
    
    async def get_match_history(self, username: str, tag: str, size: int = 5) -> Optional[List[Dict[str, Any]]]:
        """Get match history for a player"""
        try:
            url = f"{self.base_url}/../v3/matches/na/{username}/{tag}?size={size}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    return data['data']
                return data
            else:
                logging.error(f"Error fetching match history: {response.status_code}")
                return None
                
        except Exception as e:
            logging.error(f"Error fetching match history: {e}")
            return None
    
    def calculate_player_stats(self, matches: List[Dict[str, Any]], player_puuid: str) -> Dict[str, Any]:
        """Calculate comprehensive player statistics from match history"""
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
            'recent_matches': []
        }
        
        for match in matches:
            if not match.get('is_available', True):
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
            
            # KAST calculation: estimated rounds where player had impact
            # Since we don't have round-by-round data, we estimate based on KDA contribution
            # This is an approximation: assume player had impact in proportion to their team contribution
            if rounds_played > 0 and (kills > 0 or assists > 0):
                # Estimate KAST rounds based on kill/assist participation
                # Assume each kill/assist represents impact in that round, capped by total rounds
                estimated_kast_rounds = min(rounds_played, kills + assists)
                stats['kast_rounds'] += estimated_kast_rounds
            
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
                'won': teams.get(player_team.lower(), {}).get('has_won', False) if player_team.lower() in teams else False
            })
        
        # Calculate derived stats
        if stats['total_matches'] > 0:
            stats['win_rate'] = (stats['wins'] / stats['total_matches']) * 100
            stats['avg_kills'] = stats['total_kills'] / stats['total_matches']
            stats['avg_deaths'] = stats['total_deaths'] / stats['total_matches']
            stats['avg_assists'] = stats['total_assists'] / stats['total_matches']
            stats['avg_score'] = stats['total_score'] / stats['total_matches']
            stats['avg_damage_made'] = stats['total_damage_made'] / stats['total_matches']
            stats['avg_damage_received'] = stats['total_damage_received'] / stats['total_matches']
            
            # Calculate DD (Damage Delta) - difference per round between damage dealt and received
            if stats['total_rounds'] > 0:
                stats['damage_delta_per_round'] = (stats['total_damage_made'] - stats['total_damage_received']) / stats['total_rounds']
            else:
                stats['damage_delta_per_round'] = 0
            
            # Calculate ACS (Average Combat Score) - simplified Valorant formula
            # ACS is roughly: (ADR + (K/D ratio * 50) + (First Kills * 5)) but we'll use a simplified version
            # Basic formula: (Damage per round + Kill contribution + Assist contribution)
            if stats['total_rounds'] > 0:
                adr = stats['total_damage_made'] / stats['total_rounds']
                kill_contribution = (stats['total_kills'] / stats['total_rounds']) * 70  # Kills are worth ~70 ACS per round
                assist_contribution = (stats['total_assists'] / stats['total_rounds']) * 25  # Assists worth ~25 ACS per round
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
            
            if stats['total_rounds'] > 0:
                stats['kast_percentage'] = (stats['kast_rounds'] / stats['total_rounds']) * 100
                # Calculate ADR (Average Damage per Round)
                stats['adr'] = stats['total_damage_made'] / stats['total_rounds']
            else:
                stats['kast_percentage'] = 0
                stats['adr'] = 0
        
        return stats

# Global Valorant client instance
valorant_client = ValorantClient()