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


class TestAccountAPI:
    """Test API methods for account information"""
    
    @pytest.fixture
    def client(self):
        """Create a ValorantClient instance"""
        with patch('valorant_client.HENRIK_API_KEY', ''):
            return ValorantClient()
    
    @patch.object(ValorantClient, 'get')
    @pytest.mark.asyncio
    async def test_get_account_info_success(self, mock_get, client):
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
        mock_get.assert_called_once_with('account/TestPlayer/NA1')
        
        # Verify the result
        assert result is not None
        assert result['puuid'] == 'test-puuid-123'
        assert result['name'] == 'TestPlayer'
        assert result['tag'] == 'NA1'
    
    @patch.object(ValorantClient, 'get')
    @pytest.mark.asyncio
    async def test_get_account_info_error(self, mock_get, client):
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
        mock_get.assert_called_once_with('account/NonExistent/USER')


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
        mock_save_user.assert_called_once_with(mock_user)


class TestGlobalInstance:
    """Test global instance"""
    
    def test_global_instance_exists(self):
        """Test that global instance exists"""
        from valorant_client import valorant_client
        assert valorant_client is not None
        assert isinstance(valorant_client, ValorantClient)