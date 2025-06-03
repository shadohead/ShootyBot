import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
import json
import os
from context_manager import ShootyContext, ContextManager, get_shooty_context_from_channel_id, to_names_list


class TestShootyContext:
    """Test cases for ShootyContext class"""
    
    def test_init(self):
        """Test ShootyContext initialization"""
        context = ShootyContext(12345)
        
        assert context.channel_id == 12345
        assert context.channel is None
        assert len(context.bot_soloq_user_set) == 0
        assert len(context.bot_fullstack_user_set) == 0
        assert len(context.bot_ready_user_set) == 0
        assert context.current_st_message_id is None
        assert context.party_max_size == 5  # DEFAULT_PARTY_SIZE
        assert context._backup is None
    
    def test_backup_and_restore_state(self, mock_discord_user):
        """Test backup and restore functionality"""
        context = ShootyContext(12345)
        
        # Add some users
        user1 = Mock()
        user1.name = "User1"
        user2 = Mock()
        user2.name = "User2"
        
        context.add_soloq_user(user1)
        context.add_fullstack_user(user2)
        context.bot_ready_user_set.add(user1)
        
        # Backup state
        context.backup_state()
        
        # Modify state
        context.reset_users()
        assert len(context.bot_soloq_user_set) == 0
        assert len(context.bot_fullstack_user_set) == 0
        assert len(context.bot_ready_user_set) == 0
        
        # Restore state
        restored = context.restore_state()

        assert restored is True
        assert user1 in context.bot_soloq_user_set
        assert user2 in context.bot_fullstack_user_set
        assert user1 in context.bot_ready_user_set
    
    def test_restore_without_backup(self):
        """Test restore when no backup exists"""
        context = ShootyContext(12345)
        
        # Should not raise exception and return False
        restored = context.restore_state()

        assert restored is False
        assert context._backup is None
    
    def test_reset_users(self):
        """Test resetting all user sets"""
        context = ShootyContext(12345)
        
        # Add some users
        user1 = Mock()
        user2 = Mock()
        
        context.bot_soloq_user_set.add(user1)
        context.bot_fullstack_user_set.add(user2)
        context.bot_ready_user_set.add(user1)
        
        # Reset
        context.reset_users()
        
        assert len(context.bot_soloq_user_set) == 0
        assert len(context.bot_fullstack_user_set) == 0
        assert len(context.bot_ready_user_set) == 0
    
    def test_soloq_user_functions(self):
        """Test solo queue user management"""
        context = ShootyContext(12345)
        user1 = Mock()
        user2 = Mock()
        
        # Add users
        context.add_soloq_user(user1)
        assert context.get_soloq_user_count() == 1
        assert context.is_soloq_user(user1)
        assert not context.is_soloq_user(user2)
        
        # Adding to soloq should remove from fullstack
        context.add_fullstack_user(user2)
        context.add_soloq_user(user2)
        assert user2 not in context.bot_fullstack_user_set
        assert user2 in context.bot_soloq_user_set
        
        # Remove user
        context.remove_soloq_user(user1)
        assert context.get_soloq_user_count() == 1
        assert not context.is_soloq_user(user1)
    
    def test_fullstack_user_functions(self):
        """Test fullstack user management"""
        context = ShootyContext(12345)
        user1 = Mock()
        user2 = Mock()
        
        # Add users
        context.add_fullstack_user(user1)
        assert context.get_fullstack_user_count() == 1
        
        # Can't add to fullstack if already in soloq
        context.add_soloq_user(user2)
        context.add_fullstack_user(user2)
        assert user2 not in context.bot_fullstack_user_set
        
        # Remove user
        context.remove_fullstack_user(user1)
        assert context.get_fullstack_user_count() == 0
    
    def test_party_size_functions(self):
        """Test party size management"""
        context = ShootyContext(12345)
        
        # Default size
        assert context.get_party_max_size() == 5
        
        # Set new size
        context.set_party_max_size(10)
        assert context.get_party_max_size() == 10
    
    def test_get_unique_user_count(self):
        """Test unique user counting"""
        context = ShootyContext(12345)
        
        user1 = Mock()
        user2 = Mock()
        user3 = Mock()
        
        context.add_soloq_user(user1)
        context.add_soloq_user(user2)
        context.add_fullstack_user(user3)
        
        assert context.get_unique_user_count() == 3
    
    def test_remove_user_from_everything(self):
        """Test removing users by name prefix"""
        context = ShootyContext(12345)
        
        # Create users with specific names
        user1 = Mock()
        user1.name = "TestUser1"
        user2 = Mock()
        user2.name = "TestUser2"
        user3 = Mock()
        user3.name = "OtherUser"
        
        # Add users to different sets
        context.add_soloq_user(user1)
        context.add_soloq_user(user3)
        context.add_fullstack_user(user2)
        
        # Remove users starting with "Test"
        kicked = context.remove_user_from_everything(["Test"])
        
        assert len(kicked) == 2
        assert "TestUser1" in kicked
        assert "TestUser2" in kicked
        assert user3 in context.bot_soloq_user_set
        assert user1 not in context.bot_soloq_user_set
        assert user2 not in context.bot_fullstack_user_set
    
    def test_bold_readied_user(self):
        """Test user formatting with ready and Valorant status"""
        # Mock the valorant_client module import
        import sys
        mock_valorant_client = Mock()
        sys.modules['valorant_client'] = mock_valorant_client
        mock_valorant_client.valorant_client = Mock()
        mock_valorant_client.valorant_client.is_playing_valorant = Mock(return_value=False)
        
        context = ShootyContext(12345)
        user = Mock()
        user.name = "TestUser"
        user.__str__ = Mock(return_value="TestUser#1234")
        
        # Test normal user
        assert context.bold_readied_user(user) == "TestUser"
        
        # Test ready user
        context.bot_ready_user_set.add(user)
        assert context.bold_readied_user(user) == "**TestUser**"
        
        # Test user playing Valorant
        mock_valorant_client.valorant_client.is_playing_valorant.return_value = True
        assert context.bold_readied_user(user) == "**TestUser** 🎮"
        
        # Test with hashtag
        assert context.bold_readied_user(user, display_hashtag=True) == "**TestUser#1234** 🎮"
        
        # Clean up
        del sys.modules['valorant_client']
    
    def test_get_user_list_string(self):
        """Test formatted user list generation"""
        # Mock the valorant_client module import
        import sys
        mock_valorant_client = Mock()
        sys.modules['valorant_client'] = mock_valorant_client
        mock_valorant_client.valorant_client = Mock()
        mock_valorant_client.valorant_client.is_playing_valorant = Mock(return_value=False)
        
        context = ShootyContext(12345)
        
        # Create users
        user1 = Mock()
        user1.name = "User1"
        user2 = Mock()
        user2.name = "User2"
        user3 = Mock()
        user3.name = "User3"
        
        # Add users to different sets
        context.add_soloq_user(user1)
        context.add_soloq_user(user2)
        context.add_fullstack_user(user3)
        
        # Get user list
        user_list = context.get_user_list_string()
        
        # Should contain all users, fullstack users in italics
        assert "User1" in user_list
        assert "User2" in user_list
        assert "*User3*" in user_list  # Fullstack user in italics
        
        # Clean up
        del sys.modules['valorant_client']
    
    def test_to_dict(self):
        """Test context serialization to dictionary"""
        context = ShootyContext(12345)
        context.role_code = "test_role"
        context.game_name = "Valorant"
        context.party_max_size = 7
        
        data = context.to_dict()
        
        assert data['role_code'] == "test_role"
        assert data['game_name'] == "Valorant"
        assert data['party_max_size'] == 7
    
    def test_from_dict(self):
        """Test context deserialization from dictionary"""
        data = {
            'role_code': 'custom_role',
            'game_name': 'CS:GO',
            'party_max_size': 10
        }
        
        context = ShootyContext.from_dict(12345, data)
        
        assert context.channel_id == 12345
        assert context.role_code == 'custom_role'
        assert context.game_name == 'CS:GO'
        assert context.party_max_size == 10


class TestContextManager:
    """Test cases for ContextManager class"""
    
    @patch('context_manager.os.path.exists')
    @patch('context_manager.os.makedirs')
    def test_init_no_data_file(self, mock_makedirs, mock_exists):
        """Test ContextManager initialization with no existing data"""
        mock_exists.side_effect = [False, False]  # DATA_DIR doesn't exist, CHANNEL_DATA_FILE doesn't exist
        
        manager = ContextManager()
        
        assert len(manager.contexts) == 0
        mock_makedirs.assert_called_once()
    
    @patch('context_manager.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='{"12345": {"role_code": "test", "game_name": "Valorant", "party_max_size": 5}}')
    def test_init_with_data_file(self, mock_file, mock_exists):
        """Test ContextManager initialization with existing data"""
        mock_exists.return_value = True
        
        manager = ContextManager()
        
        assert len(manager.contexts) == 1
        assert 12345 in manager.contexts
        assert manager.contexts[12345].role_code == "test"
    
    def test_get_context_new(self):
        """Test getting a new context"""
        manager = ContextManager()
        
        context = manager.get_context(12345)
        
        assert context.channel_id == 12345
        assert 12345 in manager.contexts
    
    def test_get_context_existing(self):
        """Test getting an existing context"""
        manager = ContextManager()
        
        # Get context twice
        context1 = manager.get_context(12345)
        context2 = manager.get_context(12345)
        
        # Should be the same instance
        assert context1 is context2
    
    @patch('context_manager.os.makedirs')
    @patch('context_manager.os.path.exists')
    @patch('context_manager.json.dump')
    @patch('context_manager.os.replace')
    def test_save_context(self, mock_replace, mock_json_dump, mock_exists, mock_makedirs):
        """Test saving a context"""
        # Return False for all CHANNEL_DATA_FILE checks (none exists)
        mock_exists.return_value = False
        
        # Capture the data that would be written to JSON
        saved_data = None
        
        def capture_json_dump(data, file, **kwargs):
            nonlocal saved_data
            saved_data = data
        
        mock_json_dump.side_effect = capture_json_dump
        
        with patch('builtins.open', mock_open()):
            manager = ContextManager()
            context = manager.get_context(12345)
            context.role_code = "custom_role"
            
            manager.save_context(12345)
            
            # Verify data was written
            assert saved_data is not None
            assert "12345" in saved_data
            assert saved_data["12345"]["role_code"] == "custom_role"
            
            # Verify atomic write
            mock_replace.assert_called_once()
    
    @patch('context_manager.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='{"12345": {"role_code": "test"}}')
    def test_load_context_data(self, mock_file, mock_exists):
        """Test loading data for a specific context"""
        mock_exists.return_value = True
        
        manager = ContextManager()
        manager.contexts[12345] = ShootyContext(12345)
        
        manager.load_context_data(12345)
        
        assert manager.contexts[12345].role_code == "test"
    
    @patch('builtins.open', side_effect=Exception("File error"))
    @patch('context_manager.os.path.exists')
    @patch('context_manager.os.remove')
    def test_write_json_atomic_error_handling(self, mock_remove, mock_exists, mock_file):
        """Test atomic write error handling"""
        mock_exists.return_value = True
        
        manager = ContextManager()
        
        with pytest.raises(Exception):
            manager._write_json_atomic({"test": "data"})
        
        # Should attempt to clean up temp file
        mock_remove.assert_called()


class TestHelperFunctions:
    """Test helper functions"""
    
    def test_get_shooty_context_from_channel_id(self):
        """Test backward compatibility helper"""
        context = get_shooty_context_from_channel_id(12345)
        
        assert context.channel_id == 12345
        assert isinstance(context, ShootyContext)
    
    def test_to_names_list(self):
        """Test converting user set to names list"""
        user1 = Mock()
        user1.name = "User1"
        user2 = Mock()
        user2.name = "User2"
        
        user_set = {user1, user2}
        names = to_names_list(user_set)
        
        assert len(names) == 2
        assert "User1" in names
        assert "User2" in names


class TestIntegration:
    """Integration tests for context manager functionality"""
    
    @patch('context_manager.os.makedirs')
    @patch('context_manager.json.dump')
    @patch('context_manager.os.replace')
    def test_multiple_contexts_persistence(self, mock_replace, mock_json_dump, mock_makedirs):
        """Test managing multiple contexts with persistence"""
        # Track written data for each save
        saved_data_history = []
        saved_json_data = {}
        
        def capture_json_dump(data, file, **kwargs):
            saved_data_history.append(data.copy())
            # Update our "file" content for next read
            saved_json_data.clear()
            saved_json_data.update(data)
        
        mock_json_dump.side_effect = capture_json_dump
        
        # Mock file operations
        def mock_exists(path):
            # First check is for DATA_DIR, rest are for CHANNEL_DATA_FILE
            if "data" in path and not path.endswith(".json"):
                return False
            return len(saved_json_data) > 0
        
        def mock_open_func(path, mode):
            if 'r' in mode:
                return mock_open(read_data=json.dumps(saved_json_data))()
            return mock_open()()
        
        with patch('context_manager.os.path.exists', mock_exists):
            with patch('builtins.open', mock_open_func):
                manager = ContextManager()
                
                # Create multiple contexts
                context1 = manager.get_context(111)
                context1.role_code = "role1"
                context1.game_name = "Game1"
                
                context2 = manager.get_context(222)
                context2.role_code = "role2"
                context2.party_max_size = 10
                
                # Save both
                manager.save_context(111)
                manager.save_context(222)
                
                # Verify data structure - get the last JSON written
                assert len(saved_data_history) == 2
                
                # First save should only have context 111
                assert "111" in saved_data_history[0]
                assert "222" not in saved_data_history[0]
                
                # Second save should have both contexts
                final_data = saved_data_history[-1]
                assert "111" in final_data
                assert "222" in final_data
                assert final_data["111"]["game_name"] == "Game1"
                assert final_data["222"]["party_max_size"] == 10
    
    def test_user_state_transitions(self):
        """Test complex user state transitions"""
        context = ShootyContext(12345)
        
        user = Mock()
        user.name = "TestUser"
        
        # User joins soloq
        context.add_soloq_user(user)
        assert user in context.bot_soloq_user_set
        
        # User tries to join fullstack (should not work)
        context.add_fullstack_user(user)
        assert user not in context.bot_fullstack_user_set
        
        # Remove from soloq, then add to fullstack
        context.remove_soloq_user(user)
        context.add_fullstack_user(user)
        assert user in context.bot_fullstack_user_set
        
        # Add back to soloq (should remove from fullstack)
        context.add_soloq_user(user)
        assert user in context.bot_soloq_user_set
        assert user not in context.bot_fullstack_user_set