"""Integration tests for heatmap functionality"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from PIL import Image
import discord

from heatmap_generator import HeatmapGenerator
from valorant_maps import get_map_data, convert_game_coords_to_pixels


class TestHeatmapIntegration:
    """Integration tests for the complete heatmap system"""
    
    @pytest.fixture
    def sample_full_match_data(self):
        """Create comprehensive sample match data"""
        return {
            'metadata': {
                'map': 'Ascent',
                'matchid': 'integration_test_123',
                'mode': 'Competitive',
                'rounds_played': 13
            },
            'rounds': [
                {
                    'round_num': 0,
                    'player_stats': [
                        {
                            'player_puuid': 'team_player_1',
                            'kill_events': [
                                {
                                    'killer_puuid': 'team_player_1',
                                    'victim_puuid': 'enemy_player_1',
                                    'player_locations_on_kill': [
                                        {
                                            'player_puuid': 'team_player_1',
                                            'location': {'x': 2000, 'y': 1000}
                                        },
                                        {
                                            'player_puuid': 'enemy_player_1',
                                            'location': {'x': 2100, 'y': 1100}
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            'player_puuid': 'enemy_player_2',
                            'kill_events': [
                                {
                                    'killer_puuid': 'enemy_player_2',
                                    'victim_puuid': 'team_player_2',
                                    'player_locations_on_kill': [
                                        {
                                            'player_puuid': 'enemy_player_2',
                                            'location': {'x': -1500, 'y': -500}
                                        },
                                        {
                                            'player_puuid': 'team_player_2',
                                            'location': {'x': -1400, 'y': -400}
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    'round_num': 1,
                    'player_stats': [
                        {
                            'player_puuid': 'team_player_2',
                            'kill_events': [
                                {
                                    'killer_puuid': 'team_player_2',
                                    'victim_puuid': 'enemy_player_1',
                                    'player_locations_on_kill': [
                                        {
                                            'player_puuid': 'team_player_2',
                                            'location': {'x': 0, 'y': 0}
                                        },
                                        {
                                            'player_puuid': 'enemy_player_1',
                                            'location': {'x': 100, 'y': 50}
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    
    def test_valorant_maps_integration(self):
        """Test that valorant_maps module works correctly with real map data"""
        # Test that we can get map data for Ascent
        ascent_data = get_map_data('Ascent')
        assert ascent_data is not None
        assert ascent_data['name'] == 'Ascent'
        assert 'minimap_url' in ascent_data
        assert 'bounds' in ascent_data
        assert 'image_size' in ascent_data
        
        # Test coordinate conversion
        center_x, center_y = convert_game_coords_to_pixels(0, 0, ascent_data)
        assert center_x == 512  # Middle of 1024px image
        assert center_y == 512  # Middle of 1024px image
        
        # Test corner conversion
        corner_x, corner_y = convert_game_coords_to_pixels(7000, 7000, ascent_data)
        assert corner_x == 1023  # Right edge
        assert corner_y == 0     # Top edge (Y is inverted)
    
    def test_kill_event_extraction_integration(self, sample_full_match_data):
        """Test complete kill event extraction workflow"""
        generator = HeatmapGenerator()
        team_puuids = ['team_player_1', 'team_player_2']
        
        # Extract kill events
        kill_data = generator.extract_kill_events_from_match(sample_full_match_data, team_puuids)
        
        # Verify team kills
        assert len(kill_data['team_kills']) == 2
        # First team kill (round 0): team_player_1 at (2000, 1000)
        assert kill_data['team_kills'][0]['x'] == 2000
        assert kill_data['team_kills'][0]['y'] == 1000
        assert kill_data['team_kills'][0]['round'] == 0
        # Second team kill (round 1): team_player_2 at (0, 0)
        assert kill_data['team_kills'][1]['x'] == 0
        assert kill_data['team_kills'][1]['y'] == 0
        assert kill_data['team_kills'][1]['round'] == 1
        
        # Verify team deaths
        assert len(kill_data['team_deaths']) == 1
        # Team death (round 0): team_player_2 at (-1400, -400)
        assert kill_data['team_deaths'][0]['x'] == -1400
        assert kill_data['team_deaths'][0]['y'] == -400
        assert kill_data['team_deaths'][0]['round'] == 0
        
        # Verify enemy kills
        assert len(kill_data['enemy_kills']) == 1
        # Enemy kill (round 0): enemy_player_2 at (-1500, -500)
        assert kill_data['enemy_kills'][0]['x'] == -1500
        assert kill_data['enemy_kills'][0]['y'] == -500
        assert kill_data['enemy_kills'][0]['round'] == 0
        
        # Verify enemy deaths
        assert len(kill_data['enemy_deaths']) == 2
        # First enemy death (round 0): enemy_player_1 at (2100, 1100)
        assert kill_data['enemy_deaths'][0]['x'] == 2100
        assert kill_data['enemy_deaths'][0]['y'] == 1100
        assert kill_data['enemy_deaths'][0]['round'] == 0
        # Second enemy death (round 1): enemy_player_1 at (100, 50)
        assert kill_data['enemy_deaths'][1]['x'] == 100
        assert kill_data['enemy_deaths'][1]['y'] == 50
        assert kill_data['enemy_deaths'][1]['round'] == 1
    
    def test_coordinate_conversion_integration(self, sample_full_match_data):
        """Test that game coordinates can be properly converted to pixel coordinates"""
        # Get Ascent map data
        map_data = get_map_data('Ascent')
        assert map_data is not None
        
        # Extract some coordinates from the match data
        kill_events = sample_full_match_data['rounds'][0]['player_stats'][0]['kill_events'][0]
        killer_location = kill_events['player_locations_on_kill'][0]['location']
        
        # Convert to pixel coordinates
        pixel_x, pixel_y = convert_game_coords_to_pixels(
            killer_location['x'], 
            killer_location['y'], 
            map_data
        )
        
        # Verify coordinates are within image bounds
        assert 0 <= pixel_x < map_data['image_size']['width']
        assert 0 <= pixel_y < map_data['image_size']['height']
        
        # Verify specific conversion for (2000, 1000)
        # x: 2000 in range [-7000, 7000] -> normalized: (2000 + 7000) / 14000 = 0.643 -> pixel: 658
        # y: 1000 in range [-7000, 7000] -> normalized: (1000 + 7000) / 14000 = 0.571 -> inverted: 0.429 -> pixel: 438
        assert pixel_x == 658  # Roughly 2/3 to the right
        assert pixel_y == 438  # Roughly 1/3 down from top
    
    @pytest.mark.asyncio
    @patch('heatmap_generator.get_map_data')
    async def test_end_to_end_heatmap_generation(self, mock_get_map_data, sample_full_match_data):
        """Test the complete heatmap generation workflow"""
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
        
        # Create generator
        generator = HeatmapGenerator()
        
        # Mock the download method to return a test image
        test_image = Image.new('RGBA', (1024, 1024), (255, 255, 255, 255))
        generator.download_map_image = AsyncMock(return_value=test_image)
        
        # Team PUUIDs
        team_puuids = ['team_player_1', 'team_player_2']
        
        # Generate heatmap
        result = await generator.generate_heatmap(sample_full_match_data, team_puuids)
        
        # Verify result
        assert result is not None
        assert isinstance(result, discord.File)
        assert result.filename.startswith('heatmap_ascent_')
        assert result.filename.endswith('.png')
        # Check if part of the match ID is in the filename (it may be truncated)
        assert 'integrat' in result.filename  # Part of 'integration_test_123'
        
        # Verify the download method was called
        generator.download_map_image.assert_called_once()
    
    def test_error_handling_integration(self):
        """Test error handling in the integrated system"""
        generator = HeatmapGenerator()
        
        # Test with invalid map name
        invalid_match_data = {
            'metadata': {'map': 'NonExistentMap'},
            'rounds': []
        }
        
        # This should handle the error gracefully and return None
        import asyncio
        result = asyncio.run(generator.generate_heatmap(invalid_match_data, []))
        assert result is None
        
        # Test with no rounds data
        no_rounds_data = {
            'metadata': {'map': 'Ascent'},
            'rounds': []
        }
        
        # Should handle this gracefully
        kill_data = generator.extract_kill_events_from_match(no_rounds_data, ['player1'])
        assert all(len(kill_data[key]) == 0 for key in kill_data.keys())
    
    def test_performance_with_large_dataset(self):
        """Test performance with a larger dataset (simulated)"""
        generator = HeatmapGenerator()
        
        # Create match data with many rounds and kills
        large_match_data = {
            'metadata': {'map': 'Ascent'},
            'rounds': []
        }
        
        # Generate 30 rounds with multiple kills each
        for round_num in range(30):
            round_data = {
                'round_num': round_num,
                'player_stats': [
                    {
                        'player_puuid': f'player_{i}',
                        'kill_events': [
                            {
                                'killer_puuid': f'player_{i}',
                                'victim_puuid': f'enemy_{j}',
                                'player_locations_on_kill': [
                                    {
                                        'player_puuid': f'player_{i}',
                                        'location': {'x': i * 100, 'y': j * 100}
                                    },
                                    {
                                        'player_puuid': f'enemy_{j}',
                                        'location': {'x': i * 100 + 50, 'y': j * 100 + 50}
                                    }
                                ]
                            }
                            for j in range(3)  # 3 kills per player per round
                        ]
                    }
                    for i in range(5)  # 5 players
                ]
            }
            large_match_data['rounds'].append(round_data)
        
        team_puuids = ['player_0', 'player_1', 'player_2']
        
        # This should complete without issues
        import time
        start_time = time.time()
        kill_data = generator.extract_kill_events_from_match(large_match_data, team_puuids)
        end_time = time.time()
        
        # Should complete quickly (under 1 second for this dataset size)
        assert end_time - start_time < 1.0
        
        # Verify we got the expected amount of data
        # 30 rounds * 3 team players * 3 kills each = 270 team kills
        assert len(kill_data['team_kills']) == 270
        # 30 rounds * 2 enemy players * 3 kills each = 180 enemy kills
        assert len(kill_data['enemy_kills']) == 180