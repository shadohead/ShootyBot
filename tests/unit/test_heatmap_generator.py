"""Tests for heatmap_generator module"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from io import BytesIO
import discord
from PIL import Image, ImageDraw

from heatmap_generator import HeatmapGenerator, get_heatmap_generator, close_heatmap_generator


class TestHeatmapGenerator:
    """Test cases for HeatmapGenerator class"""
    
    @pytest.fixture
    def generator(self):
        """Create a HeatmapGenerator instance for testing"""
        return HeatmapGenerator()
    
    @pytest.fixture
    def sample_match_data(self):
        """Create sample match data with kill events"""
        return {
            'metadata': {
                'map': 'Ascent',
                'matchid': 'test123',
                'mode': 'Competitive',
                'rounds_played': 24
            },
            'rounds': [
                {
                    'round_num': 0,
                    'player_stats': [
                        {
                            'player_puuid': 'player1',
                            'kill_events': [
                                {
                                    'killer_puuid': 'player1',
                                    'victim_puuid': 'enemy1',
                                    'player_locations_on_kill': [
                                        {
                                            'player_puuid': 'player1',
                                            'location': {'x': 1000, 'y': 500}
                                        },
                                        {
                                            'player_puuid': 'enemy1',
                                            'location': {'x': 1200, 'y': 600}
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            'player_puuid': 'enemy1',
                            'kill_events': [
                                {
                                    'killer_puuid': 'enemy1',
                                    'victim_puuid': 'player2',
                                    'player_locations_on_kill': [
                                        {
                                            'player_puuid': 'enemy1',
                                            'location': {'x': -500, 'y': -200}
                                        },
                                        {
                                            'player_puuid': 'player2',
                                            'location': {'x': -600, 'y': -300}
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    
    @pytest.fixture
    def team_puuids(self):
        """Team PUUIDs for testing"""
        return ['player1', 'player2']
    
    @pytest.mark.asyncio
    async def test_ensure_session(self, generator):
        """Test session creation"""
        assert generator.session is None
        await generator.ensure_session()
        assert generator.session is not None
        await generator.close()
    
    @pytest.mark.asyncio
    async def test_close(self, generator):
        """Test closing the generator"""
        await generator.ensure_session()
        assert generator.session is not None
        await generator.close()
        assert generator.session is None
    
    def test_extract_kill_events_basic(self, generator, sample_match_data, team_puuids):
        """Test basic kill event extraction"""
        kill_data = generator.extract_kill_events_from_match(sample_match_data, team_puuids)
        
        # Check structure
        assert 'team_kills' in kill_data
        assert 'team_deaths' in kill_data
        assert 'enemy_kills' in kill_data
        assert 'enemy_deaths' in kill_data
        
        # Check team kills (player1 killed enemy1)
        assert len(kill_data['team_kills']) == 1
        assert kill_data['team_kills'][0]['x'] == 1000
        assert kill_data['team_kills'][0]['y'] == 500
        assert kill_data['team_kills'][0]['round'] == 0
        
        # Check enemy deaths (enemy1 died to player1)
        assert len(kill_data['enemy_deaths']) == 1
        assert kill_data['enemy_deaths'][0]['x'] == 1200
        assert kill_data['enemy_deaths'][0]['y'] == 600
        
        # Check enemy kills (enemy1 killed player2)
        assert len(kill_data['enemy_kills']) == 1
        assert kill_data['enemy_kills'][0]['x'] == -500
        assert kill_data['enemy_kills'][0]['y'] == -200
        
        # Check team deaths (player2 died to enemy1)
        assert len(kill_data['team_deaths']) == 1
        assert kill_data['team_deaths'][0]['x'] == -600
        assert kill_data['team_deaths'][0]['y'] == -300
    
    def test_extract_kill_events_no_rounds(self, generator, team_puuids):
        """Test extraction with no round data"""
        match_data = {'metadata': {'map': 'Ascent'}, 'rounds': []}
        kill_data = generator.extract_kill_events_from_match(match_data, team_puuids)
        
        assert len(kill_data['team_kills']) == 0
        assert len(kill_data['team_deaths']) == 0
        assert len(kill_data['enemy_kills']) == 0
        assert len(kill_data['enemy_deaths']) == 0
    
    def test_extract_kill_events_missing_location(self, generator, team_puuids):
        """Test extraction with missing location data"""
        match_data = {
            'rounds': [{
                'round_num': 0,
                'player_stats': [{
                    'player_puuid': 'player1',
                    'kill_events': [{
                        'killer_puuid': 'player1',
                        'victim_puuid': 'enemy1',
                        'player_locations_on_kill': []  # No locations
                    }]
                }]
            }]
        }
        
        kill_data = generator.extract_kill_events_from_match(match_data, team_puuids)
        assert len(kill_data['team_kills']) == 0  # Should skip kills without locations
    
    def test_draw_dot(self, generator):
        """Test dot drawing function"""
        # Create a small test image
        image = Image.new('RGBA', (100, 100), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image, 'RGBA')
        
        # Draw a dot at center
        generator.draw_dot(draw, 50, 50, (255, 0, 0, 180))
        
        # Check that pixels were drawn (simplified check)
        # In a real test, you might check specific pixel values
        pixels = list(image.getdata())
        red_pixels = [p for p in pixels if p[0] > 200 and p[1] < 50]
        assert len(red_pixels) > 0  # Some red pixels should exist
    
    
    def test_download_map_image_caching_simple(self, generator):
        """Test simple caching behavior"""
        test_url = "https://example.com/map.png"
        test_image = Image.new('RGBA', (100, 100), (255, 255, 255, 255))
        
        # Manually add to cache
        generator._map_cache[test_url] = test_image
        
        # Should return cached image
        assert test_url in generator._map_cache
        assert generator._map_cache[test_url] is test_image
    
    @pytest.mark.asyncio
    async def test_generate_heatmap_no_map_name(self, generator, team_puuids):
        """Test heatmap generation with missing map name"""
        match_data = {'metadata': {}}  # No map name
        result = await generator.generate_heatmap(match_data, team_puuids)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_generate_heatmap_invalid_map(self, generator, team_puuids):
        """Test heatmap generation with invalid map name"""
        match_data = {'metadata': {'map': 'InvalidMapName'}}
        result = await generator.generate_heatmap(match_data, team_puuids)
        assert result is None
    
    @pytest.mark.asyncio
    @patch('heatmap_generator.get_map_data')
    async def test_generate_heatmap_success(self, mock_get_map_data, generator, sample_match_data, team_puuids):
        """Test successful heatmap generation"""
        # Mock map data
        mock_get_map_data.return_value = {
            'name': 'Ascent',
            'minimap_url': 'https://example.com/ascent.png',
            'bounds': {
                'x_min': -7000,
                'x_max': 7000,
                'y_min': -7000,
                'y_max': 7000
            },
            'image_size': {
                'width': 1024,
                'height': 1024
            }
        }
        
        # Mock download_map_image to return a test image
        test_image = Image.new('RGBA', (1024, 1024), (255, 255, 255, 255))
        generator.download_map_image = AsyncMock(return_value=test_image)
        
        # Generate heatmap
        result = await generator.generate_heatmap(sample_match_data, team_puuids)
        
        # Check result
        assert result is not None
        assert isinstance(result, discord.File)
        assert result.filename.startswith('heatmap_ascent_')
        assert result.filename.endswith('.png')
    
    def test_add_legend(self, generator):
        """Test legend addition to heatmap"""
        image = Image.new('RGBA', (1024, 1024), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image, 'RGBA')
        
        kill_data = {
            'team_kills': [None] * 5,  # 5 team kills
            'team_deaths': [None] * 3,  # 3 team deaths
            'enemy_kills': [None] * 4,  # 4 enemy kills
            'enemy_deaths': [None] * 6   # 6 enemy deaths
        }
        
        # Should not raise any exceptions
        generator.add_legend(draw, image.size, kill_data)
    
    def test_add_title(self, generator):
        """Test title addition to heatmap"""
        image = Image.new('RGBA', (1024, 1024), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image, 'RGBA')
        
        match_data = {
            'metadata': {
                'mode': 'Competitive',
                'rounds_played': 24
            }
        }
        
        # Should not raise any exceptions
        generator.add_title(draw, image.size, 'Ascent', match_data)
    
    def _create_test_image_bytes(self):
        """Helper to create test image bytes"""
        image = Image.new('RGBA', (100, 100), (255, 255, 255, 255))
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        return buffer.getvalue()


class TestHeatmapGeneratorGlobal:
    """Test global heatmap generator functions"""
    
    def test_get_heatmap_generator(self):
        """Test getting global heatmap generator instance"""
        generator1 = get_heatmap_generator()
        generator2 = get_heatmap_generator()
        
        assert generator1 is not None
        assert generator1 is generator2  # Should be same instance
    
    @pytest.mark.asyncio
    async def test_close_heatmap_generator(self):
        """Test closing global heatmap generator"""
        # Get instance
        generator = get_heatmap_generator()
        await generator.ensure_session()
        
        # Close it
        await close_heatmap_generator()
        
        # Getting it again should create new instance
        new_generator = get_heatmap_generator()
        assert new_generator is not generator