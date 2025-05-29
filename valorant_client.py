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

# Global Valorant client instance
valorant_client = ValorantClient()