"""
Heatmap generator for Valorant match kill/death data
Creates dot-style heatmaps overlaid on map minimaps
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from io import BytesIO
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import discord
from valorant_maps import get_map_data, convert_game_coords_to_pixels
from utils import log_error

class HeatmapGenerator:
    """Generates heatmaps for Valorant matches showing kill/death locations"""
    
    # Configuration
    DOT_SIZE = 8  # Size of each kill/death dot
    KILL_COLOR = (0, 255, 0, 180)  # Green with transparency
    DEATH_COLOR = (255, 0, 0, 180)  # Red with transparency
    TEAM_KILL_COLOR = (100, 255, 100, 180)  # Light green for team kills
    TEAM_DEATH_COLOR = (255, 100, 100, 180)  # Light red for team deaths
    BACKGROUND_OPACITY = 0.3  # How much to darken the map background
    
    def __init__(self):
        self.session = None
        self._map_cache = {}  # Cache downloaded map images
        
    async def ensure_session(self):
        """Ensure aiohttp session exists"""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def download_map_image(self, map_url: str) -> Optional[Image.Image]:
        """Download and cache map minimap image"""
        # Check cache first
        if map_url in self._map_cache:
            return self._map_cache[map_url]
            
        try:
            await self.ensure_session()
            
            # Download the image
            async with self.session.get(map_url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    image = Image.open(BytesIO(image_data))
                    
                    # Convert to RGBA if needed
                    if image.mode != 'RGBA':
                        image = image.convert('RGBA')
                    
                    # Cache the image
                    self._map_cache[map_url] = image
                    return image
                else:
                    log_error("downloading map image", Exception(f"HTTP {response.status}"))
                    return None
                    
        except Exception as e:
            log_error("downloading map image", e)
            return None
    
    def extract_kill_events_from_match(self, match_data: Dict[str, Any], team_puuids: List[str]) -> Dict[str, List[Dict]]:
        """
        Extract kill events with coordinates from match data
        
        Args:
            match_data: Full match data from Henrik API
            team_puuids: List of PUUIDs for the team we're analyzing
            
        Returns:
            Dictionary with 'team_kills', 'team_deaths', 'enemy_kills', 'enemy_deaths'
        """
        kill_data = {
            'team_kills': [],
            'team_deaths': [],
            'enemy_kills': [],
            'enemy_deaths': []
        }
        
        # Get rounds data
        rounds_data = match_data.get('rounds', [])
        if not rounds_data:
            logging.warning("No round data available for heatmap generation")
            return kill_data
        
        # Process each round
        for round_data in rounds_data:
            player_stats = round_data.get('player_stats', [])
            
            # Process kill events from each player
            for player_stat in player_stats:
                player_puuid = player_stat.get('player_puuid', '')
                kill_events = player_stat.get('kill_events', [])
                
                for event in kill_events:
                    # Extract kill location
                    kill_location = event.get('player_locations_on_kill', [])
                    if not kill_location:
                        continue
                    
                    # Get killer and victim info
                    killer_puuid = event.get('killer_puuid', '')
                    victim_puuid = event.get('victim_puuid', '')
                    
                    # Find killer location (first entry is the killer)
                    killer_loc = None
                    victim_loc = None
                    
                    for loc in kill_location:
                        if loc.get('player_puuid') == killer_puuid:
                            killer_loc = loc.get('location', {})
                        elif loc.get('player_puuid') == victim_puuid:
                            victim_loc = loc.get('location', {})
                    
                    # Categorize the kill
                    if killer_puuid in team_puuids:
                        # Team member got a kill
                        if killer_loc and 'x' in killer_loc and 'y' in killer_loc:
                            kill_data['team_kills'].append({
                                'x': killer_loc['x'],
                                'y': killer_loc['y'],
                                'round': round_data.get('round_num', 0)
                            })
                    else:
                        # Enemy got a kill
                        if killer_loc and 'x' in killer_loc and 'y' in killer_loc:
                            kill_data['enemy_kills'].append({
                                'x': killer_loc['x'],
                                'y': killer_loc['y'],
                                'round': round_data.get('round_num', 0)
                            })
                    
                    # Categorize the death
                    if victim_puuid in team_puuids:
                        # Team member died
                        if victim_loc and 'x' in victim_loc and 'y' in victim_loc:
                            kill_data['team_deaths'].append({
                                'x': victim_loc['x'],
                                'y': victim_loc['y'],
                                'round': round_data.get('round_num', 0)
                            })
                    else:
                        # Enemy died
                        if victim_loc and 'x' in victim_loc and 'y' in victim_loc:
                            kill_data['enemy_deaths'].append({
                                'x': victim_loc['x'],
                                'y': victim_loc['y'],
                                'round': round_data.get('round_num', 0)
                            })
        
        return kill_data
    
    def draw_dot(self, draw: ImageDraw.Draw, x: int, y: int, color: Tuple[int, int, int, int]):
        """Draw a single dot on the heatmap"""
        # Draw a filled circle
        bbox = [x - self.DOT_SIZE//2, y - self.DOT_SIZE//2, 
                x + self.DOT_SIZE//2, y + self.DOT_SIZE//2]
        draw.ellipse(bbox, fill=color, outline=None)
    
    async def generate_heatmap(self, match_data: Dict[str, Any], team_puuids: List[str]) -> Optional[discord.File]:
        """
        Generate a heatmap image for the match
        
        Args:
            match_data: Full match data from Henrik API
            team_puuids: List of PUUIDs for the team we're analyzing
            
        Returns:
            Discord.File object ready to be sent, or None if generation failed
        """
        try:
            # Get map name
            map_name = match_data.get('metadata', {}).get('map', '')
            if not map_name:
                logging.error("No map name found in match data")
                return None
            
            # Get map data
            map_data = get_map_data(map_name)
            if not map_data:
                logging.error(f"No map data found for {map_name}")
                return None
            
            # Download map image
            map_image = await self.download_map_image(map_data['minimap_url'])
            if not map_image:
                logging.error(f"Failed to download map image for {map_name}")
                return None
            
            # Create a copy to draw on
            heatmap_image = map_image.copy()
            
            # Darken the background slightly
            overlay = Image.new('RGBA', heatmap_image.size, (0, 0, 0, int(255 * self.BACKGROUND_OPACITY)))
            heatmap_image = Image.alpha_composite(heatmap_image, overlay)
            
            # Extract kill events
            kill_data = self.extract_kill_events_from_match(match_data, team_puuids)
            
            # Create drawing context
            draw = ImageDraw.Draw(heatmap_image, 'RGBA')
            
            # Draw deaths first (so kills appear on top)
            for death in kill_data['team_deaths']:
                x, y = convert_game_coords_to_pixels(death['x'], death['y'], map_data)
                self.draw_dot(draw, x, y, self.TEAM_DEATH_COLOR)
            
            for death in kill_data['enemy_deaths']:
                x, y = convert_game_coords_to_pixels(death['x'], death['y'], map_data)
                self.draw_dot(draw, x, y, self.DEATH_COLOR)
            
            # Draw kills on top
            for kill in kill_data['team_kills']:
                x, y = convert_game_coords_to_pixels(kill['x'], kill['y'], map_data)
                self.draw_dot(draw, x, y, self.TEAM_KILL_COLOR)
            
            for kill in kill_data['enemy_kills']:
                x, y = convert_game_coords_to_pixels(kill['x'], kill['y'], map_data)
                self.draw_dot(draw, x, y, self.KILL_COLOR)
            
            # Add legend
            self.add_legend(draw, heatmap_image.size, kill_data)
            
            # Add title
            self.add_title(draw, heatmap_image.size, map_name, match_data)
            
            # Convert to bytes for Discord
            output = BytesIO()
            heatmap_image.save(output, format='PNG')
            output.seek(0)
            
            # Create Discord file
            filename = f"heatmap_{map_name.lower()}_{match_data.get('metadata', {}).get('matchid', 'unknown')[:8]}.png"
            return discord.File(output, filename=filename)
            
        except Exception as e:
            log_error("generating heatmap", e)
            return None
    
    def add_legend(self, draw: ImageDraw.Draw, image_size: Tuple[int, int], kill_data: Dict[str, List]):
        """Add a legend to the heatmap"""
        # Position legend in bottom left
        legend_x = 10
        legend_y = image_size[1] - 100
        
        # Background for legend
        legend_bg = [legend_x - 5, legend_y - 5, legend_x + 200, legend_y + 85]
        draw.rectangle(legend_bg, fill=(0, 0, 0, 200))
        
        # Draw legend items
        y_offset = legend_y
        
        # Team kills
        self.draw_dot(draw, legend_x + 10, y_offset + 5, self.TEAM_KILL_COLOR)
        draw.text((legend_x + 25, y_offset), f"Team Kills ({len(kill_data['team_kills'])})", 
                  fill=(255, 255, 255), font=None)
        
        y_offset += 20
        # Team deaths
        self.draw_dot(draw, legend_x + 10, y_offset + 5, self.TEAM_DEATH_COLOR)
        draw.text((legend_x + 25, y_offset), f"Team Deaths ({len(kill_data['team_deaths'])})", 
                  fill=(255, 255, 255), font=None)
        
        y_offset += 20
        # Enemy kills
        self.draw_dot(draw, legend_x + 10, y_offset + 5, self.KILL_COLOR)
        draw.text((legend_x + 25, y_offset), f"Enemy Kills ({len(kill_data['enemy_kills'])})", 
                  fill=(255, 255, 255), font=None)
        
        y_offset += 20
        # Enemy deaths
        self.draw_dot(draw, legend_x + 10, y_offset + 5, self.DEATH_COLOR)
        draw.text((legend_x + 25, y_offset), f"Enemy Deaths ({len(kill_data['enemy_deaths'])})", 
                  fill=(255, 255, 255), font=None)
    
    def add_title(self, draw: ImageDraw.Draw, image_size: Tuple[int, int], map_name: str, match_data: Dict[str, Any]):
        """Add title to the heatmap"""
        # Get match info
        metadata = match_data.get('metadata', {})
        mode = metadata.get('mode', 'Unknown')
        rounds_played = metadata.get('rounds_played', 0)
        
        # Create title
        title = f"{map_name} - {mode} - {rounds_played} rounds"
        
        # Position at top center
        title_bbox = draw.textbbox((0, 0), title)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (image_size[0] - title_width) // 2
        title_y = 10
        
        # Background for title
        title_bg = [title_x - 10, title_y - 5, title_x + title_width + 10, title_y + 20]
        draw.rectangle(title_bg, fill=(0, 0, 0, 200))
        
        # Draw title
        draw.text((title_x, title_y), title, fill=(255, 255, 255), font=None)

# Global heatmap generator instance
_heatmap_generator: Optional[HeatmapGenerator] = None

def get_heatmap_generator() -> HeatmapGenerator:
    """Get the global heatmap generator instance"""
    global _heatmap_generator
    if _heatmap_generator is None:
        _heatmap_generator = HeatmapGenerator()
    return _heatmap_generator

async def close_heatmap_generator():
    """Close the global heatmap generator"""
    global _heatmap_generator
    if _heatmap_generator is not None:
        await _heatmap_generator.close()
        _heatmap_generator = None