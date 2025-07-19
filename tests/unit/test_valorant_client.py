import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from valorant_client import ValorantClient
from api_clients import APIResponse
import discord


class TestValorantClientInit:
    """Test ValorantClient initialization"""
    
    @patch('valorant_client.HENRIK_API_KEY', 'test_api_key')
    def test_init_with_api_key(self):
        """Test client initialization with API key"""
        client = ValorantClient()
        
        assert client.base_url == "https://api.henrikdev.xyz/valorant/v1"
        assert client.api_key == 'test_api_key'
        # Authorization header is now handled by BaseAPIClient
        auth_headers = client._get_auth_headers()
        assert auth_headers['Authorization'] == 'test_api_key'
    
    @patch('valorant_client.HENRIK_API_KEY', '')
    def test_init_without_api_key(self):
        """Test client initialization without API key"""
        client = ValorantClient()
        
        assert client.base_url == "https://api.henrikdev.xyz/valorant/v1"
        assert client.api_key == ''
        # No authorization headers when no API key
        auth_headers = client._get_auth_headers()
        assert 'Authorization' not in auth_headers


class TestAuthorizationHeaders:
    """Ensure aiohttp sessions include auth headers only with API key."""

    @pytest.mark.asyncio
    async def test_session_headers_with_key(self):
        with patch('valorant_client.HENRIK_API_KEY', 'secret'), \
             patch('api_clients.aiohttp.ClientSession') as mock_session, \
             patch('api_clients.aiohttp.TCPConnector'), \
             patch('api_clients.aiohttp.ClientTimeout'):

            client = ValorantClient()
            mock_session.return_value.closed = False
            await client._ensure_session()

            headers = mock_session.call_args.kwargs.get('headers', {})
            assert headers.get('Authorization') == 'secret'

    @pytest.mark.asyncio
    async def test_session_headers_without_key(self):
        with patch('valorant_client.HENRIK_API_KEY', ''), \
             patch('api_clients.aiohttp.ClientSession') as mock_session, \
             patch('api_clients.aiohttp.TCPConnector'), \
             patch('api_clients.aiohttp.ClientTimeout'):

            client = ValorantClient()
            mock_session.return_value.closed = False
            await client._ensure_session()

            headers = mock_session.call_args.kwargs.get('headers', {})
            assert 'Authorization' not in headers


class TestAccountAPI:
    """Test API methods for account information"""
    
    @pytest.fixture
    def client(self):
        """Create a ValorantClient instance"""
        with patch('valorant_client.HENRIK_API_KEY', ''):
            return ValorantClient()
    
    @patch.object(ValorantClient, 'get')
    @patch('valorant_client.database_manager.get_stored_account', return_value=None)
    @pytest.mark.asyncio
    async def test_get_account_info_success(self, mock_get_stored, mock_get, client):
        """Test successful account info retrieval with real API response structure"""
        # Mock the BaseAPIClient.get method
        api_response = APIResponse(
            data={
                "puuid": "test-puuid-123",
                "name": "TestPlayer",
                "tag": "NA1",
                "card": {
                    "small": "https://media.valorant-api.com/playercards/small.png",
                    "large": "https://media.valorant-api.com/playercards/large.png",
                    "wide": "https://media.valorant-api.com/playercards/wide.png",
                    "id": "card-id-123"
                }
            },
            status_code=200,
            headers={}
        )
        mock_get.return_value = api_response
        
        # Call the method
        result = await client.get_account_info("TestPlayer", "NA1")
        
        # Verify the call
        mock_get.assert_called_once_with('account/TestPlayer/NA1', cache_ttl=300)
        
        # Verify the result
        assert result is not None
        assert result['puuid'] == 'test-puuid-123'
        assert result['name'] == 'TestPlayer'
        assert result['tag'] == 'NA1'
    
    @patch.object(ValorantClient, 'get')
    @patch('valorant_client.database_manager.get_stored_account', return_value=None)
    @pytest.mark.asyncio
    async def test_get_account_info_error(self, mock_get_stored, mock_get, client):
        """Test account info with error response"""
        # Mock error response
        api_response = APIResponse(
            data=None,
            status_code=404,
            headers={}
        )
        mock_get.return_value = api_response

        result = await client.get_account_info("NonExistent", "USER")

        assert result is None
        mock_get.assert_called_once_with('account/NonExistent/USER', cache_ttl=300)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code,expected_none", [
        (200, False),
        (404, True),
        (429, True),
    ])
    async def test_get_account_info_various_responses(self, status_code, expected_none, client):
        """Parametrized test for different HTTP responses."""
        with patch.object(ValorantClient, 'get') as mock_get, \
             patch('valorant_client.database_manager.get_stored_account', return_value=None), \
             patch('valorant_client.database_manager.store_account'):

            data = {'data': {'puuid': 'abc'}} if status_code == 200 else {}
            mock_get.return_value = APIResponse(data=data, status_code=status_code, headers={})

            result = await client.get_account_info("User", "TAG")

            mock_get.assert_called_once_with('account/User/TAG', cache_ttl=300)

            if expected_none:
                assert result is None
            else:
                assert result == {'puuid': 'abc'}


class TestAccountLinking:
    """Test account linking functionality"""
    
    @pytest.fixture
    def client(self):
        """Create a ValorantClient instance"""
        with patch('valorant_client.HENRIK_API_KEY', ''):
            return ValorantClient()
    
    @patch('data_manager.data_manager.get_user')
    @patch('data_manager.data_manager.save_user')
    @patch.object(ValorantClient, 'get_account_info')
    @pytest.mark.asyncio
    async def test_link_account_success(self, mock_get_account, mock_save_user, mock_get_user, client):
        """Test successful account linking"""
        # Mock user data
        mock_user = Mock()
        mock_user.link_valorant_account = Mock()
        mock_get_user.return_value = mock_user
        
        # Mock account info
        mock_get_account.return_value = {
            'puuid': 'test-puuid',
            'name': 'TestPlayer',
            'tag': 'NA1'
        }
        
        result = await client.link_account(123456789, "TestPlayer", "NA1")
        
        # link_account returns the account info, not just True
        assert result is not None
        assert result['puuid'] == 'test-puuid'
        mock_get_account.assert_called_once_with("TestPlayer", "NA1")
        mock_user.link_valorant_account.assert_called_once_with("TestPlayer", "NA1", "test-puuid")
        mock_save_user.assert_called_once_with(123456789)


class TestMatchHistoryAPI:
    """Parametrized tests for match history retrieval"""

    @pytest.fixture
    def client(self):
        with patch('valorant_client.HENRIK_API_KEY', ''):
            return ValorantClient()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code,expected_none", [
        (200, False),
        (404, True),
        (429, True),
    ])
    async def test_get_match_history_various_responses(self, status_code, expected_none, client):
        with patch.object(ValorantClient, 'get_account_info', return_value={'puuid': 'abc'}), \
             patch('valorant_client.database_manager.get_stored_player_stats', return_value=None), \
             patch('valorant_client.database_manager.store_player_stats'), \
             patch.object(ValorantClient, 'calculate_player_stats', return_value={}), \
             patch.object(ValorantClient, 'get') as mock_get:

            data = {'data': [{'id': 'match1'}]} if status_code == 200 else {}
            mock_get.return_value = APIResponse(data=data, status_code=status_code, headers={})

            result = await client.get_match_history("User", "TAG")

            mock_get.assert_called_once_with(
                'matches/na/User/TAG',
                params={'size': 5},
                cache_ttl=180
            )

            if expected_none:
                assert result is None
            else:
                assert result == [{'id': 'match1'}]


class TestGlobalInstance:
    """Test global instance"""
    
    def test_global_instance_exists(self):
        """Test that global instance exists"""
        from valorant_client import valorant_client
        assert valorant_client is not None
        assert isinstance(valorant_client, ValorantClient)