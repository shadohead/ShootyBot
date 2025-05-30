"""Tests for valorant_maps module"""

import pytest
from valorant_maps import VALORANT_MAPS, get_map_data, convert_game_coords_to_pixels


class TestValorantMaps:
    """Test cases for Valorant map data and coordinate conversion"""
    
    def test_all_maps_have_required_fields(self):
        """Test that all maps have the required data fields"""
        required_fields = {'name', 'minimap_url', 'bounds', 'image_size'}
        required_bounds_fields = {'x_min', 'x_max', 'y_min', 'y_max'}
        required_image_fields = {'width', 'height'}
        
        for map_name, map_data in VALORANT_MAPS.items():
            # Check top-level fields
            assert all(field in map_data for field in required_fields), f"Missing fields in {map_name}"
            
            # Check bounds fields
            assert all(field in map_data['bounds'] for field in required_bounds_fields), f"Missing bounds fields in {map_name}"
            
            # Check image size fields
            assert all(field in map_data['image_size'] for field in required_image_fields), f"Missing image size fields in {map_name}"
            
            # Validate data types
            assert isinstance(map_data['name'], str)
            assert isinstance(map_data['minimap_url'], str)
            assert map_data['minimap_url'].startswith('https://')
            assert isinstance(map_data['bounds']['x_min'], (int, float))
            assert isinstance(map_data['bounds']['x_max'], (int, float))
            assert isinstance(map_data['bounds']['y_min'], (int, float))
            assert isinstance(map_data['bounds']['y_max'], (int, float))
            assert isinstance(map_data['image_size']['width'], int)
            assert isinstance(map_data['image_size']['height'], int)
            
            # Validate bounds make sense
            assert map_data['bounds']['x_min'] < map_data['bounds']['x_max']
            assert map_data['bounds']['y_min'] < map_data['bounds']['y_max']
            assert map_data['image_size']['width'] > 0
            assert map_data['image_size']['height'] > 0
    
    def test_get_map_data_exact_match(self):
        """Test getting map data with exact name match"""
        # Test exact match
        ascent_data = get_map_data('Ascent')
        assert ascent_data is not None
        assert ascent_data['name'] == 'Ascent'
        
        # Test case variations
        assert get_map_data('ascent') is not None
        assert get_map_data('ASCENT') is not None
        assert get_map_data(' Ascent ') is not None
    
    def test_get_map_data_invalid(self):
        """Test getting map data with invalid name"""
        assert get_map_data('InvalidMapName') is None
        assert get_map_data('') is None
        assert get_map_data('Map123') is None
    
    def test_convert_game_coords_center(self):
        """Test coordinate conversion at map center"""
        map_data = {
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
        
        # Test center point (0, 0) -> (512, 512)
        x, y = convert_game_coords_to_pixels(0, 0, map_data)
        assert x == 512
        assert y == 512
    
    def test_convert_game_coords_corners(self):
        """Test coordinate conversion at map corners"""
        map_data = {
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
        
        # Test top-left corner (-7000, 7000) -> (0, 0)
        x, y = convert_game_coords_to_pixels(-7000, 7000, map_data)
        assert x == 0
        assert y == 0
        
        # Test bottom-right corner (7000, -7000) -> (1023, 1023)
        x, y = convert_game_coords_to_pixels(7000, -7000, map_data)
        assert x == 1023
        assert y == 1023
        
        # Test top-right corner (7000, 7000) -> (1023, 0)
        x, y = convert_game_coords_to_pixels(7000, 7000, map_data)
        assert x == 1023
        assert y == 0
        
        # Test bottom-left corner (-7000, -7000) -> (0, 1023)
        x, y = convert_game_coords_to_pixels(-7000, -7000, map_data)
        assert x == 0
        assert y == 1023
    
    def test_convert_game_coords_clamping(self):
        """Test that coordinates outside bounds are clamped"""
        map_data = {
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
        
        # Test coordinates beyond bounds are clamped
        x, y = convert_game_coords_to_pixels(-10000, 10000, map_data)
        assert x == 0  # Clamped to left edge
        assert y == 0  # Clamped to top edge
        
        x, y = convert_game_coords_to_pixels(10000, -10000, map_data)
        assert x == 1023  # Clamped to right edge
        assert y == 1023  # Clamped to bottom edge
    
    def test_convert_game_coords_different_bounds(self):
        """Test coordinate conversion with non-symmetric bounds"""
        map_data = {
            'bounds': {
                'x_min': -5000,
                'x_max': 5000,
                'y_min': -3000,
                'y_max': 7000
            },
            'image_size': {
                'width': 800,
                'height': 600
            }
        }
        
        # Test center of bounds (0, 2000) -> (400, 300)
        x, y = convert_game_coords_to_pixels(0, 2000, map_data)
        assert x == 400
        assert y == 300
        
    def test_all_maps_accessible(self):
        """Test that all maps in VALORANT_MAPS can be accessed via get_map_data"""
        for map_name in VALORANT_MAPS.keys():
            map_data = get_map_data(map_name)
            assert map_data is not None
            assert map_data['name'] == map_name