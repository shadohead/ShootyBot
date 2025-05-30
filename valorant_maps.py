"""
Valorant map data including minimap images and coordinate scaling information
"""

# Map data with minimap URLs from Valorant Wiki and coordinate bounds
# Valorant uses a coordinate system where (0, 0) is typically the center of the map
# Game coordinates need to be converted to pixel coordinates for the minimap images

VALORANT_MAPS = {
    'Ascent': {
        'name': 'Ascent',
        'minimap_url': 'https://static.wikia.nocookie.net/valorant/images/0/04/Ascent_minimap.png',
        # Coordinate bounds are approximated based on typical Valorant map sizes
        # These will need fine-tuning based on actual match data
        'bounds': {
            'x_min': -7000,
            'x_max': 7000,
            'y_min': -7000,
            'y_max': 7000
        },
        'image_size': {
            'width': 1024,  # Standard minimap image dimensions
            'height': 1024
        }
    },
    'Bind': {
        'name': 'Bind',
        'minimap_url': 'https://static.wikia.nocookie.net/valorant/images/e/e6/Bind_minimap.png',
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
    },
    'Haven': {
        'name': 'Haven',
        'minimap_url': 'https://static.wikia.nocookie.net/valorant/images/2/25/Haven_minimap.png',
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
    },
    'Split': {
        'name': 'Split',
        'minimap_url': 'https://static.wikia.nocookie.net/valorant/images/f/ff/Split_minimap.png',
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
    },
    'Icebox': {
        'name': 'Icebox',
        'minimap_url': 'https://static.wikia.nocookie.net/valorant/images/c/cf/Icebox_minimap.png',
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
    },
    'Breeze': {
        'name': 'Breeze',
        'minimap_url': 'https://static.wikia.nocookie.net/valorant/images/7/78/Breeze_minimap.png',
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
    },
    'Fracture': {
        'name': 'Fracture',
        'minimap_url': 'https://static.wikia.nocookie.net/valorant/images/1/18/Fracture_minimap.png',
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
    },
    'Pearl': {
        'name': 'Pearl',
        'minimap_url': 'https://static.wikia.nocookie.net/valorant/images/6/63/Pearl_minimap.png',
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
    },
    'Lotus': {
        'name': 'Lotus',
        'minimap_url': 'https://static.wikia.nocookie.net/valorant/images/b/be/Lotus_minimap.png',
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
    },
    'Sunset': {
        'name': 'Sunset',
        'minimap_url': 'https://static.wikia.nocookie.net/valorant/images/7/7b/Sunset_minimap.png',
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
    },
    'Abyss': {
        'name': 'Abyss',
        'minimap_url': 'https://static.wikia.nocookie.net/valorant/images/5/5f/Abyss_minimap.png',
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
}

def get_map_data(map_name: str) -> dict:
    """Get map data by name (case-insensitive)"""
    # Normalize map name
    map_name_normalized = map_name.strip().title()
    
    # Try exact match first
    if map_name_normalized in VALORANT_MAPS:
        return VALORANT_MAPS[map_name_normalized]
    
    # Try case-insensitive search
    for map_key, map_data in VALORANT_MAPS.items():
        if map_key.lower() == map_name.lower():
            return map_data
    
    return None

def convert_game_coords_to_pixels(x: float, y: float, map_data: dict) -> tuple:
    """
    Convert game coordinates to pixel coordinates on the minimap image
    
    Args:
        x: Game X coordinate
        y: Game Y coordinate
        map_data: Map data dictionary containing bounds and image size
        
    Returns:
        Tuple of (pixel_x, pixel_y)
    """
    bounds = map_data['bounds']
    image_size = map_data['image_size']
    
    # Calculate normalized position (0-1)
    norm_x = (x - bounds['x_min']) / (bounds['x_max'] - bounds['x_min'])
    norm_y = (y - bounds['y_min']) / (bounds['y_max'] - bounds['y_min'])
    
    # Convert to pixel coordinates
    # Note: Y-axis is typically inverted in image coordinates
    pixel_x = int(norm_x * image_size['width'])
    pixel_y = int((1 - norm_y) * image_size['height'])
    
    # Clamp to image bounds
    pixel_x = max(0, min(pixel_x, image_size['width'] - 1))
    pixel_y = max(0, min(pixel_y, image_size['height'] - 1))
    
    return (pixel_x, pixel_y)