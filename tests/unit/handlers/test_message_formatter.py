import pytest
from unittest.mock import Mock, patch
from context_manager import ShootyContext
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from handlers.message_formatter import (
    get_ping_shooty_message,
    get_kicked_user_message, 
    get_max_party_size_message,
    bold,
    italics,
    party_status_message
)

class TestMessageFormatterHelpers:
    """Test simple helper functions"""
    
    def test_get_ping_shooty_message_with_role(self):
        """Test ping message with role code"""
        role_code = "<@&123456789>"
        result = get_ping_shooty_message(role_code)
        expected = "‎<@&123456789>"  # DEFAULT_MSG + role_code
        assert result == expected
    
    def test_get_ping_shooty_message_no_role(self):
        """Test ping message without role code"""
        result = get_ping_shooty_message(None)
        expected = "First set the role for the bot to ping with ```$stsr <Role>```"
        assert result == expected
    
    def test_get_kicked_user_message_single_user(self):
        """Test kicked user message with single user"""
        kicked_users = ["TestUser"]
        result = get_kicked_user_message(kicked_users)
        assert result == "Kicked: ['TestUser']"
    
    def test_get_kicked_user_message_multiple_users(self):
        """Test kicked user message with multiple users"""
        kicked_users = ["User1", "User2", "User3"]
        result = get_kicked_user_message(kicked_users)
        assert result == "Kicked: ['User1', 'User2', 'User3']"
    
    def test_get_kicked_user_message_empty_list(self):
        """Test kicked user message with empty list"""
        kicked_users = []
        result = get_kicked_user_message(kicked_users)
        assert result == "Kicked: []"
    
    def test_get_max_party_size_message(self):
        """Test party size message formatting"""
        result = get_max_party_size_message(5)
        assert result == "Current party size: 5"
        
        result = get_max_party_size_message(3)
        assert result == "Current party size: 3"
    
    def test_bold_formatting(self):
        """Test Discord bold text formatting"""
        result = bold("test text")
        assert result == "**test text**"
        
        result = bold("5/5")
        assert result == "**5/5**"
    
    def test_italics_formatting(self):
        """Test Discord italic text formatting"""
        result = italics("test text")
        assert result == "*test text*"
        
        result = italics("emphasis")
        assert result == "*emphasis*"


class TestPartyStatusMessage:
    """Test the complex party status message function"""
    
    @pytest.fixture
    def mock_user_sets(self):
        """Create a mock ShootyContext object"""
        user_sets = Mock(spec=ShootyContext)
        user_sets.role_code = "<@&123456789>"
        user_sets.get_party_max_size.return_value = 5
        user_sets.get_user_list_string.return_value = "TestUser1, TestUser2"
        return user_sets
    
    def test_party_status_empty_party(self, mock_user_sets):
        """Test party status with no users"""
        mock_user_sets.get_soloq_user_count.return_value = 0
        mock_user_sets.get_fullstack_user_count.return_value = 0
        mock_user_sets.get_unique_user_count.return_value = 0
        
        result = party_status_message(False, mock_user_sets)
        
        # Should contain the empty party message
        assert "sadge/5" in result
        assert "<:viper:725612569716326422>" in result
        assert "‎" in result  # DEFAULT_MSG
    
    def test_party_status_solo_queue_only(self, mock_user_sets):
        """Test party status with only solo queue users"""
        mock_user_sets.get_soloq_user_count.return_value = 3
        mock_user_sets.get_fullstack_user_count.return_value = 0
        mock_user_sets.get_unique_user_count.return_value = 3
        
        result = party_status_message(False, mock_user_sets)
        
        # Should show **3/5**
        assert "**3/5**" in result
        assert "TestUser1, TestUser2" in result
    
    def test_party_status_fullstack_only(self, mock_user_sets):
        """Test party status with only fullstack users"""
        mock_user_sets.get_soloq_user_count.return_value = 0
        mock_user_sets.get_fullstack_user_count.return_value = 2
        mock_user_sets.get_unique_user_count.return_value = 2
        
        result = party_status_message(False, mock_user_sets)
        
        # Should show (2)**/5**
        assert "(2)" in result
        assert "**/5**" in result
        assert "TestUser1, TestUser2" in result
    
    def test_party_status_mixed_users(self, mock_user_sets):
        """Test party status with mixed solo and fullstack users"""
        mock_user_sets.get_soloq_user_count.return_value = 2
        mock_user_sets.get_fullstack_user_count.return_value = 1
        mock_user_sets.get_unique_user_count.return_value = 3
        
        result = party_status_message(False, mock_user_sets)
        
        # Should show **2**(3)***/5***
        assert "**2**" in result
        assert "(3)" in result
        assert "**/5**" in result
        assert "TestUser1, TestUser2" in result
    
    def test_party_status_full_party(self, mock_user_sets):
        """Test party status when party is full"""
        mock_user_sets.get_soloq_user_count.return_value = 5
        mock_user_sets.get_fullstack_user_count.return_value = 0
        mock_user_sets.get_unique_user_count.return_value = 5
        
        result = party_status_message(False, mock_user_sets)
        
        # Should show **5/5** and party full emoji
        assert "**5/5**" in result
        assert "<:jettpog:724145370023591937>" in result
        assert "TestUser1, TestUser2" in result
    
    def test_party_status_with_ping(self, mock_user_sets):
        """Test party status with ping enabled"""
        mock_user_sets.get_soloq_user_count.return_value = 2
        mock_user_sets.get_fullstack_user_count.return_value = 0
        mock_user_sets.get_unique_user_count.return_value = 2
        
        result = party_status_message(True, mock_user_sets)
        
        # Should include role code when ping is True
        assert "<@&123456789>" in result
        assert "**2/5**" in result
    
    def test_party_status_without_ping(self, mock_user_sets):
        """Test party status without ping"""
        mock_user_sets.get_soloq_user_count.return_value = 2
        mock_user_sets.get_fullstack_user_count.return_value = 0
        mock_user_sets.get_unique_user_count.return_value = 2
        
        result = party_status_message(False, mock_user_sets)
        
        # Should not include role code when ping is False
        assert "<@&123456789>" not in result
        assert "**2/5**" in result
    
    def test_party_status_no_role_code(self, mock_user_sets):
        """Test party status when no role code is set"""
        mock_user_sets.role_code = None
        mock_user_sets.get_soloq_user_count.return_value = 2
        mock_user_sets.get_fullstack_user_count.return_value = 0
        mock_user_sets.get_unique_user_count.return_value = 2
        
        result = party_status_message(True, mock_user_sets)
        
        # Should not include role code even when ping is True
        assert "@&" not in result
        assert "**2/5**" in result
    
    def test_party_status_backward_compatibility_channel_object(self, mock_user_sets):
        """Test backward compatibility when is_ping is a channel object"""
        # Create a mock channel object that has an id attribute
        mock_channel = Mock()
        mock_channel.id = 123456789
        
        mock_user_sets.get_soloq_user_count.return_value = 1
        mock_user_sets.get_fullstack_user_count.return_value = 0
        mock_user_sets.get_unique_user_count.return_value = 1
        
        result = party_status_message(mock_channel, mock_user_sets)
        
        # Should treat channel object as False for ping
        assert "<@&123456789>" not in result
        assert "**1/5**" in result
    
    def test_party_status_different_party_sizes(self, mock_user_sets):
        """Test party status with different max party sizes"""
        # Test with party size 3
        mock_user_sets.get_party_max_size.return_value = 3
        mock_user_sets.get_soloq_user_count.return_value = 2
        mock_user_sets.get_fullstack_user_count.return_value = 0
        mock_user_sets.get_unique_user_count.return_value = 2
        
        result = party_status_message(False, mock_user_sets)
        assert "**2/3**" in result
        
        # Test with party size 10
        mock_user_sets.get_party_max_size.return_value = 10
        mock_user_sets.get_soloq_user_count.return_value = 7
        mock_user_sets.get_fullstack_user_count.return_value = 0
        mock_user_sets.get_unique_user_count.return_value = 7
        
        result = party_status_message(False, mock_user_sets)
        assert "**7/10**" in result