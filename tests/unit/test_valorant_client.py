import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from valorant_client import ValorantClient
import discord


class TestValorantClientInit:
    """Test ValorantClient initialization"""
    
    @patch('valorant_client.HENRIK_API_KEY', 'test_api_key')
    def test_init_with_api_key(self):
        """Test client initialization with API key"""
        client = ValorantClient()
        
        assert client.base_url == "https://api.henrikdev.xyz/valorant/v1"
        assert client.headers['User-Agent'] == 'ShootyBot/1.0 (Discord Bot)'
        assert client.headers['Authorization'] == 'test_api_key'
    
    @patch('valorant_client.HENRIK_API_KEY', '')
    def test_init_without_api_key(self):
        """Test client initialization without API key"""
        client = ValorantClient()
        
        assert client.base_url == "https://api.henrikdev.xyz/valorant/v1"
        assert client.headers['User-Agent'] == 'ShootyBot/1.0 (Discord Bot)'
        assert 'Authorization' not in client.headers


class TestAccountAPI:
    """Test API methods for account information"""
    
    @pytest.fixture
    def client(self):
        """Create a ValorantClient instance"""
        with patch('valorant_client.HENRIK_API_KEY', ''):
            return ValorantClient()
    
    @patch('valorant_client.requests.get')
    @pytest.mark.asyncio
    async def test_get_account_info_success(self, mock_get, client):
        """Test successful account info retrieval with real API response structure"""
        mock_response = Mock()
        mock_response.status_code = 200
        # Based on actual Henrik API response structure
        mock_response.json.return_value = {
            'status': 200,
            'data': {
                'puuid': '4b1d3c29-1b87-4a8e-9c47-2d8e5f6c7a9b',
                'name': 'TestPlayer',
                'tag': 'TEST',
                'card': {
                    'small': 'https://media.valorantapi.com/playercards/small/card_id.png',
                    'large': 'https://media.valorantapi.com/playercards/large/card_id.png',
                    'wide': 'https://media.valorantapi.com/playercards/wide/card_id.png',
                    'id': '9fb348bc-41a0-91ad-8a3e-818035c4e561'
                }
            }
        }
        mock_get.return_value = mock_response
        
        result = await client.get_account_info('TestPlayer', 'TEST')
        
        assert result['puuid'] == '4b1d3c29-1b87-4a8e-9c47-2d8e5f6c7a9b'
        assert result['name'] == 'TestPlayer'
        assert result['tag'] == 'TEST'
        assert result['card']['id'] == '9fb348bc-41a0-91ad-8a3e-818035c4e561'
        mock_get.assert_called_once_with(
            'https://api.henrikdev.xyz/valorant/v1/account/TestPlayer/TEST',
            headers=client.headers
        )
    
    @patch('valorant_client.requests.get')
    @pytest.mark.asyncio
    async def test_get_account_info_unauthorized(self, mock_get, client):
        """Test account info with 401 unauthorized"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        
        result = await client.get_account_info('TestPlayer', 'TEST')
        
        assert result is None
    
    @patch('valorant_client.requests.get')
    @pytest.mark.asyncio
    async def test_get_account_info_not_found(self, mock_get, client):
        """Test account info with 404 not found"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result = await client.get_account_info('NonExistent', 'USER')
        
        assert result is None
    
    @patch('valorant_client.requests.get')
    @pytest.mark.asyncio
    async def test_get_account_info_rate_limited(self, mock_get, client):
        """Test account info with 429 rate limit"""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        result = await client.get_account_info('TestPlayer', 'TEST')
        
        assert result is None
    
    @patch('valorant_client.requests.get')
    @pytest.mark.asyncio
    async def test_get_account_info_server_error(self, mock_get, client):
        """Test account info with server error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_get.return_value = mock_response
        
        result = await client.get_account_info('TestPlayer', 'TEST')
        
        assert result is None
    
    @patch('valorant_client.requests.get')
    @pytest.mark.asyncio
    async def test_get_account_info_exception(self, mock_get, client):
        """Test account info with request exception"""
        mock_get.side_effect = Exception("Network error")
        
        result = await client.get_account_info('TestPlayer', 'TEST')
        
        assert result is None
    
    @patch('valorant_client.requests.get')
    @pytest.mark.asyncio
    async def test_get_account_by_puuid_success(self, mock_get, client):
        """Test successful account info by PUUID"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': {
                'puuid': 'test-puuid-123',
                'name': 'TestPlayer',
                'tag': 'TEST'
            }
        }
        mock_get.return_value = mock_response
        
        result = await client.get_account_by_puuid('test-puuid-123')
        
        assert result['puuid'] == 'test-puuid-123'
        mock_get.assert_called_once_with(
            'https://api.henrikdev.xyz/valorant/v1/by-puuid/account/test-puuid-123',
            headers=client.headers
        )
    
    @patch('valorant_client.requests.get')
    @pytest.mark.asyncio
    async def test_get_account_by_puuid_error(self, mock_get, client):
        """Test account info by PUUID with error"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result = await client.get_account_by_puuid('invalid-puuid')
        
        assert result is None


class TestAccountLinking:
    """Test account linking functionality"""
    
    @pytest.fixture
    def client(self):
        """Create a ValorantClient instance"""
        with patch('valorant_client.HENRIK_API_KEY', ''):
            return ValorantClient()
    
    @patch('valorant_client.data_manager')
    @pytest.mark.asyncio
    async def test_link_account_success(self, mock_data_manager, client):
        """Test successful account linking"""
        # Mock the get_account_info method as async
        async def mock_get_account_info(username, tag):
            return {
                'puuid': 'test-puuid-123',
                'name': 'TestPlayer',
                'tag': 'TEST',
                'card': {'id': 'card123'}
            }
        client.get_account_info = mock_get_account_info
        
        # Mock user data
        mock_user_data = Mock()
        mock_data_manager.get_user.return_value = mock_user_data
        
        result = await client.link_account(123456789, 'TestPlayer', 'TEST')
        
        assert result['success'] is True
        assert result['username'] == 'TestPlayer'
        assert result['tag'] == 'TEST'
        assert result['puuid'] == 'test-puuid-123'
        
        mock_user_data.link_valorant_account.assert_called_once_with('TestPlayer', 'TEST', 'test-puuid-123')
        mock_data_manager.save_user.assert_called_once_with(123456789)
    
    @pytest.mark.asyncio
    async def test_link_account_remove_hash(self, client):
        """Test account linking removes # from tag"""
        # Mock the get_account_info method as async
        async def mock_get_account_info(username, tag):
            return {
                'puuid': 'test-puuid-123',
                'name': 'TestPlayer',
                'tag': 'TEST'
            }
        client.get_account_info = mock_get_account_info
        
        with patch('valorant_client.data_manager') as mock_data_manager:
            mock_user_data = Mock()
            mock_data_manager.get_user.return_value = mock_user_data
            
            # Track calls to verify the tag without # is used
            calls = []
            async def tracking_mock(username, tag):
                calls.append((username, tag))
                return {
                    'puuid': 'test-puuid-123',
                    'name': 'TestPlayer',
                    'tag': 'TEST'
                }
            client.get_account_info = tracking_mock
            
            await client.link_account(123456789, 'TestPlayer', '#TEST')
            
            # Should call get_account_info with tag without #
            assert calls[0] == ('TestPlayer', 'TEST')
    
    @pytest.mark.asyncio
    async def test_link_account_api_failure(self, client):
        """Test account linking when API fails"""
        # Mock the get_account_info method to return None
        async def mock_get_account_info(username, tag):
            return None
        client.get_account_info = mock_get_account_info
        
        result = await client.link_account(123456789, 'TestPlayer', 'TEST')
        
        assert result['success'] is False
        assert 'Henrik API now requires authentication' in result['error']
    
    @pytest.mark.asyncio
    async def test_link_account_no_puuid(self, client):
        """Test account linking when API returns data without PUUID"""
        # Mock the get_account_info method
        async def mock_get_account_info(username, tag):
            return {
                'name': 'TestPlayer',
                'tag': 'TEST'
                # Missing puuid
            }
        client.get_account_info = mock_get_account_info
        
        result = await client.link_account(123456789, 'TestPlayer', 'TEST')
        
        assert result['success'] is False
        assert result['error'] == 'Invalid account data from API'
    
    @patch('valorant_client.data_manager')
    @pytest.mark.asyncio
    async def test_unlink_account_success(self, mock_data_manager, client):
        """Test successful account unlinking"""
        mock_user_data = Mock()
        mock_data_manager.get_user.return_value = mock_user_data
        
        result = await client.unlink_account(123456789)
        
        assert result is True
        assert mock_user_data.valorant_username is None
        assert mock_user_data.valorant_tag is None
        assert mock_user_data.valorant_puuid is None
        mock_data_manager.save_user.assert_called_once_with(123456789)
    
    @patch('valorant_client.data_manager')
    @pytest.mark.asyncio
    async def test_unlink_account_error(self, mock_data_manager, client):
        """Test account unlinking with error"""
        mock_data_manager.get_user.side_effect = Exception("Database error")
        
        result = await client.unlink_account(123456789)
        
        assert result is False
    
    @patch('valorant_client.data_manager')
    def test_get_linked_account(self, mock_data_manager, client):
        """Test getting linked account"""
        mock_user_data = Mock()
        mock_user_data.get_primary_account.return_value = {
            'username': 'TestPlayer',
            'tag': 'TEST',
            'puuid': 'test-puuid-123'
        }
        mock_data_manager.get_user.return_value = mock_user_data
        
        result = client.get_linked_account(123456789)
        
        assert result['username'] == 'TestPlayer'
        assert result['tag'] == 'TEST'
        assert result['puuid'] == 'test-puuid-123'
    
    @patch('valorant_client.data_manager')
    def test_get_all_linked_accounts(self, mock_data_manager, client):
        """Test getting all linked accounts"""
        mock_user_data = Mock()
        mock_user_data.get_all_accounts.return_value = [
            {'username': 'TestPlayer1', 'tag': 'TEST1', 'puuid': 'puuid-1'},
            {'username': 'TestPlayer2', 'tag': 'TEST2', 'puuid': 'puuid-2'}
        ]
        mock_data_manager.get_user.return_value = mock_user_data
        
        result = client.get_all_linked_accounts(123456789)
        
        assert len(result) == 2
        assert result[0]['username'] == 'TestPlayer1'
        assert result[1]['username'] == 'TestPlayer2'


class TestDiscordActivity:
    """Test Discord activity detection"""
    
    @pytest.fixture
    def client(self):
        """Create a ValorantClient instance"""
        with patch('valorant_client.HENRIK_API_KEY', ''):
            return ValorantClient()
    
    def test_is_playing_valorant_game_activity(self, client):
        """Test Valorant detection with discord.Game activity"""
        mock_member = Mock()
        mock_game = Mock(spec=discord.Game)
        mock_game.name = "VALORANT"
        mock_member.activities = [mock_game]
        
        result = client.is_playing_valorant(mock_member)
        
        assert result is True
    
    def test_is_playing_valorant_activity_type(self, client):
        """Test Valorant detection with discord.Activity"""
        mock_member = Mock()
        mock_activity = Mock(spec=discord.Activity)
        mock_activity.name = "VALORANT"
        mock_member.activities = [mock_activity]
        
        result = client.is_playing_valorant(mock_member)
        
        assert result is True
    
    def test_is_playing_valorant_case_insensitive(self, client):
        """Test Valorant detection is case insensitive"""
        mock_member = Mock()
        mock_game = Mock(spec=discord.Game)
        mock_game.name = "valorant"
        mock_member.activities = [mock_game]
        
        result = client.is_playing_valorant(mock_member)
        
        assert result is True
    
    def test_is_playing_valorant_no_activities(self, client):
        """Test when member has no activities"""
        mock_member = Mock()
        mock_member.activities = None
        
        result = client.is_playing_valorant(mock_member)
        
        assert result is False
    
    def test_is_playing_valorant_different_game(self, client):
        """Test when member is playing different game"""
        mock_member = Mock()
        mock_game = Mock(spec=discord.Game)
        mock_game.name = "Overwatch 2"
        mock_member.activities = [mock_game]
        
        result = client.is_playing_valorant(mock_member)
        
        assert result is False
    
    def test_is_playing_valorant_no_activity_name(self, client):
        """Test when activity has no name"""
        mock_member = Mock()
        mock_game = Mock(spec=discord.Game)
        mock_game.name = None
        mock_member.activities = [mock_game]
        
        result = client.is_playing_valorant(mock_member)
        
        assert result is False
    
    def test_get_playing_members(self, client):
        """Test getting all members playing Valorant"""
        # Create mock members
        mock_valorant_member = Mock()
        mock_valorant_game = Mock(spec=discord.Game)
        mock_valorant_game.name = "VALORANT"
        mock_valorant_member.activities = [mock_valorant_game]
        
        mock_other_member = Mock()
        mock_other_game = Mock(spec=discord.Game)
        mock_other_game.name = "Minecraft"
        mock_other_member.activities = [mock_other_game]
        
        mock_guild = Mock()
        mock_guild.members = [mock_valorant_member, mock_other_member]
        
        result = client.get_playing_members(mock_guild)
        
        assert len(result) == 1
        assert result[0] == mock_valorant_member


class TestMatchHistory:
    """Test match history functionality"""
    
    @pytest.fixture
    def client(self):
        """Create a ValorantClient instance"""
        with patch('valorant_client.HENRIK_API_KEY', ''):
            return ValorantClient()
    
    @patch('valorant_client.requests.get')
    @pytest.mark.asyncio
    async def test_get_match_history_success(self, mock_get, client):
        """Test successful match history retrieval with real API response structure"""
        mock_response = Mock()
        mock_response.status_code = 200
        # Based on actual Henrik API v3 match response structure
        mock_response.json.return_value = {
            'status': 200,
            'data': [
                {
                    'metadata': {
                        'map': 'Bind', 
                        'game_version': '8.0.1.10222',
                        'game_length': 1854000,
                        'game_start': 1705123456789,
                        'game_start_patched': '2024-01-13T10:30:56.789Z',
                        'rounds_played': 24,
                        'mode': 'Competitive',
                        'mode_id': 'competitive',
                        'queue': 'competitive',
                        'season_id': 'e5f1c2a3-4b8d-5c9e-7f1a-2b3c4d5e6f7g',
                        'platform': 'PC',
                        'matchid': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                        'premier_info': {
                            'tournament_id': None,
                            'matchup_id': None
                        }
                    },
                    'players': {
                        'all_players': [],
                        'red': [],
                        'blue': []
                    },
                    'teams': {
                        'red': {
                            'has_won': False,
                            'rounds_won': 11,
                            'rounds_lost': 13
                        },
                        'blue': {
                            'has_won': True,
                            'rounds_won': 13,
                            'rounds_lost': 11
                        }
                    }
                },
                {
                    'metadata': {
                        'map': 'Ascent', 
                        'game_version': '8.0.1.10222',
                        'game_length': 2156000,
                        'game_start': 1705120000000,
                        'game_start_patched': '2024-01-13T09:33:20.000Z',
                        'rounds_played': 25,
                        'mode': 'Competitive',
                        'mode_id': 'competitive',
                        'queue': 'competitive',
                        'season_id': 'e5f1c2a3-4b8d-5c9e-7f1a-2b3c4d5e6f7g',
                        'platform': 'PC',
                        'matchid': 'b2c3d4e5-f6g7-8901-bcde-f23456789012',
                        'premier_info': {
                            'tournament_id': None,
                            'matchup_id': None
                        }
                    },
                    'players': {
                        'all_players': [],
                        'red': [],
                        'blue': []
                    },
                    'teams': {
                        'red': {
                            'has_won': True,
                            'rounds_won': 13,
                            'rounds_lost': 12
                        },
                        'blue': {
                            'has_won': False,
                            'rounds_won': 12,
                            'rounds_lost': 13
                        }
                    }
                }
            ]
        }
        mock_get.return_value = mock_response
        
        result = await client.get_match_history('TestPlayer', 'TEST', 5)
        
        assert len(result) == 2
        assert result[0]['metadata']['map'] == 'Bind'
        mock_get.assert_called_once_with(
            'https://api.henrikdev.xyz/valorant/v1/../v3/matches/na/TestPlayer/TEST?size=5',
            headers=client.headers
        )
    
    @patch('valorant_client.requests.get')
    @pytest.mark.asyncio
    async def test_get_match_history_error(self, mock_get, client):
        """Test match history with error"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result = await client.get_match_history('TestPlayer', 'TEST')
        
        assert result is None
    
    @patch('valorant_client.requests.get')
    @pytest.mark.asyncio
    async def test_get_match_history_exception(self, mock_get, client):
        """Test match history with exception"""
        mock_get.side_effect = Exception("Network error")
        
        result = await client.get_match_history('TestPlayer', 'TEST')
        
        assert result is None


class TestPlayerStats:
    """Test player statistics calculation"""
    
    @pytest.fixture
    def client(self):
        """Create a ValorantClient instance"""
        with patch('valorant_client.HENRIK_API_KEY', ''):
            return ValorantClient()
    
    @pytest.fixture
    def sample_matches(self):
        """Create realistic sample match data based on actual Henrik API structure"""
        return [
            {
                'is_available': True,
                'metadata': {
                    'map': 'Bind',
                    'game_version': '8.0.1.10222',
                    'game_length': 1854000,
                    'game_start': 1705123456789,
                    'game_start_patched': '2024-01-13T10:30:56.789Z',
                    'rounds_played': 24,
                    'mode': 'Competitive',
                    'mode_id': 'competitive',
                    'queue': 'competitive',
                    'season_id': 'e5f1c2a3-4b8d-5c9e-7f1a-2b3c4d5e6f7g',
                    'platform': 'PC',
                    'matchid': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
                },
                'players': {
                    'all_players': [
                        {
                            'puuid': 'test-puuid-123',
                            'name': 'TestPlayer',
                            'tag': 'TEST',
                            'team': 'Red',
                            'level': 127,
                            'character': 'Sage',
                            'tier': 15,
                            'stats': {
                                'score': 4500,
                                'kills': 18,
                                'deaths': 12,
                                'assists': 6,
                                'bodyshots': 142,
                                'headshots': 28,
                                'legshots': 12
                            },
                            'ability_casts': {
                                'c_cast': 3,
                                'q_cast': 8,
                                'e_cast': 12,
                                'x_cast': 1
                            },
                            'assets': {
                                'card': {
                                    'small': 'https://media.valorantapi.com/playercards/small/card_id.png',
                                    'large': 'https://media.valorantapi.com/playercards/large/card_id.png',
                                    'wide': 'https://media.valorantapi.com/playercards/wide/card_id.png'
                                },
                                'agent': {
                                    'small': 'https://media.valorantapi.com/agents/sage/displayicon.png',
                                    'full': 'https://media.valorantapi.com/agents/sage/fullportrait.png',
                                    'bust': 'https://media.valorantapi.com/agents/sage/bustportrait.png'
                                }
                            },
                            'behaviour': {
                                'afk_rounds': 0,
                                'friendly_fire': {
                                    'incoming': 0,
                                    'outgoing': 24
                                },
                                'rounds_in_spawn': 0
                            },
                            'platform': {
                                'type': 'PC',
                                'os': {
                                    'name': 'Windows',
                                    'version': '10.0.19045.4170'
                                }
                            },
                            'damage_made': 3247,
                            'damage_received': 2834
                        }
                    ],
                    'red': [],
                    'blue': []
                },
                'teams': {
                    'red': {
                        'has_won': True,
                        'rounds_won': 13,
                        'rounds_lost': 11
                    },
                    'blue': {
                        'has_won': False,
                        'rounds_won': 11,
                        'rounds_lost': 13
                    }
                }
            },
            {
                'is_available': True,
                'metadata': {
                    'map': 'Ascent',
                    'game_version': '8.0.1.10222',
                    'game_length': 2156000,
                    'game_start': 1705120000000,
                    'game_start_patched': '2024-01-13T09:33:20.000Z',
                    'rounds_played': 25,
                    'mode': 'Competitive',
                    'mode_id': 'competitive',
                    'queue': 'competitive',
                    'season_id': 'e5f1c2a3-4b8d-5c9e-7f1a-2b3c4d5e6f7g',
                    'platform': 'PC',
                    'matchid': 'b2c3d4e5-f6g7-8901-bcde-f23456789012'
                },
                'players': {
                    'all_players': [
                        {
                            'puuid': 'test-puuid-123',
                            'name': 'TestPlayer',
                            'tag': 'TEST',
                            'team': 'Blue',
                            'level': 127,
                            'character': 'Jett',
                            'tier': 15,
                            'stats': {
                                'score': 5200,
                                'kills': 22,
                                'deaths': 15,
                                'assists': 4,
                                'bodyshots': 168,
                                'headshots': 41,
                                'legshots': 8
                            },
                            'ability_casts': {
                                'c_cast': 2,
                                'q_cast': 6,
                                'e_cast': 15,
                                'x_cast': 2
                            },
                            'assets': {
                                'card': {
                                    'small': 'https://media.valorantapi.com/playercards/small/card_id.png',
                                    'large': 'https://media.valorantapi.com/playercards/large/card_id.png',
                                    'wide': 'https://media.valorantapi.com/playercards/wide/card_id.png'
                                },
                                'agent': {
                                    'small': 'https://media.valorantapi.com/agents/jett/displayicon.png',
                                    'full': 'https://media.valorantapi.com/agents/jett/fullportrait.png',
                                    'bust': 'https://media.valorantapi.com/agents/jett/bustportrait.png'
                                }
                            },
                            'behaviour': {
                                'afk_rounds': 0,
                                'friendly_fire': {
                                    'incoming': 12,
                                    'outgoing': 8
                                },
                                'rounds_in_spawn': 0
                            },
                            'platform': {
                                'type': 'PC',
                                'os': {
                                    'name': 'Windows',
                                    'version': '10.0.19045.4170'
                                }
                            },
                            'damage_made': 3842,
                            'damage_received': 3198
                        }
                    ],
                    'red': [],
                    'blue': []
                },
                'teams': {
                    'red': {
                        'has_won': True,
                        'rounds_won': 13,
                        'rounds_lost': 12
                    },
                    'blue': {
                        'has_won': False,
                        'rounds_won': 12,
                        'rounds_lost': 13
                    }
                }
            }
        ]
    
    def test_calculate_player_stats_empty_matches(self, client):
        """Test stats calculation with empty match list"""
        result = client.calculate_player_stats([], 'test-puuid-123')
        
        assert result == {}
    
    def test_calculate_player_stats_basic(self, client, sample_matches):
        """Test basic stats calculation"""
        result = client.calculate_player_stats(sample_matches, 'test-puuid-123')
        
        # Basic counts
        assert result['total_matches'] == 2
        assert result['wins'] == 1
        assert result['losses'] == 1
        assert result['total_kills'] == 40
        assert result['total_deaths'] == 27
        assert result['total_assists'] == 10
        
        # Calculated stats with realistic values
        assert result['win_rate'] == 50.0
        assert result['avg_kills'] == 20.0
        assert result['avg_deaths'] == 13.5
        assert result['kd_ratio'] == pytest.approx(40/27, rel=1e-2)
        assert result['total_damage_made'] == 3247 + 3842
        assert result['total_damage_received'] == 2834 + 3198
    
    def test_calculate_player_stats_zero_deaths(self, client):
        """Test stats calculation with zero deaths"""
        matches = [
            {
                'is_available': True,
                'metadata': {'map': 'Bind', 'rounds_played': 24},
                'players': {
                    'all_players': [
                        {
                            'puuid': 'test-puuid-123',
                            'character': 'Sage',
                            'team': 'Red',
                            'stats': {
                                'kills': 25,
                                'deaths': 0,
                                'assists': 5,
                                'headshots': 10,
                                'bodyshots': 15,
                                'legshots': 0,
                                'score': 6000
                            },
                            'damage_made': 4000,
                            'damage_received': 1000
                        }
                    ]
                },
                'teams': {
                    'red': {'has_won': True}
                }
            }
        ]
        
        result = client.calculate_player_stats(matches, 'test-puuid-123')
        
        # Should handle zero deaths gracefully
        assert result['kd_ratio'] == 25.0
        assert result['kda_ratio'] == 30.0
    
    def test_calculate_player_stats_headshot_percentage(self, client, sample_matches):
        """Test headshot percentage calculation"""
        result = client.calculate_player_stats(sample_matches, 'test-puuid-123')
        
        total_shots = (28 + 41) + (142 + 168) + (12 + 8)  # headshots + bodyshots + legshots from both matches
        expected_hs_percentage = ((28 + 41) / total_shots) * 100
        
        assert result['headshot_percentage'] == pytest.approx(expected_hs_percentage, rel=1e-2)
    
    def test_calculate_player_stats_maps_and_agents(self, client, sample_matches):
        """Test map and agent tracking"""
        result = client.calculate_player_stats(sample_matches, 'test-puuid-123')
        
        assert result['maps_played']['Bind'] == 1
        assert result['maps_played']['Ascent'] == 1
        assert result['agents_played']['Sage'] == 1
        assert result['agents_played']['Jett'] == 1
    
    def test_calculate_player_stats_unavailable_match(self, client):
        """Test stats calculation skips unavailable matches"""
        matches = [
            {
                'is_available': False,
                'metadata': {'map': 'Bind', 'rounds_played': 24},
                'players': {
                    'all_players': [
                        {
                            'puuid': 'test-puuid-123',
                            'stats': {'kills': 20, 'deaths': 10, 'assists': 5}
                        }
                    ]
                }
            }
        ]
        
        result = client.calculate_player_stats(matches, 'test-puuid-123')
        
        assert result['total_matches'] == 0
    
    def test_calculate_player_stats_player_not_found(self, client):
        """Test stats calculation when player not found in match"""
        matches = [
            {
                'is_available': True,
                'metadata': {'map': 'Bind', 'rounds_played': 24},
                'players': {
                    'all_players': [
                        {
                            'puuid': 'different-puuid',
                            'stats': {'kills': 20, 'deaths': 10, 'assists': 5}
                        }
                    ]
                }
            }
        ]
        
        result = client.calculate_player_stats(matches, 'test-puuid-123')
        
        assert result['total_matches'] == 0
    
    def test_calculate_player_stats_acs_calculation(self, client, sample_matches):
        """Test ACS (Average Combat Score) calculation"""
        result = client.calculate_player_stats(sample_matches, 'test-puuid-123')
        
        # Should have calculated ACS
        assert 'acs' in result
        assert result['acs'] > 0
    
    def test_calculate_player_stats_damage_delta(self, client, sample_matches):
        """Test damage delta calculation"""
        result = client.calculate_player_stats(sample_matches, 'test-puuid-123')
        
        total_damage_made = 3200 + 3800
        total_damage_received = 2800 + 3200
        total_rounds = 24 + 25
        expected_delta = (total_damage_made - total_damage_received) / total_rounds
        
        assert result['damage_delta_per_round'] == pytest.approx(expected_delta, rel=1e-2)


class TestGlobalInstance:
    """Test the global valorant_client instance"""
    
    def test_global_instance_exists(self):
        """Test that global valorant_client instance is created"""
        from valorant_client import valorant_client
        
        assert valorant_client is not None
        assert isinstance(valorant_client, ValorantClient)