import pytest
from unittest.mock import Mock, patch, mock_open
import json
import os
from datetime import datetime, timezone, timedelta
from freezegun import freeze_time

# Mock the database and base models before importing data_manager
with patch('data_manager.database_manager') as mock_db, \
     patch('data_manager.TimestampedModel') as mock_ts, \
     patch('data_manager.ValidatedModel') as mock_val:
    
    # Configure the mocks
    mock_ts.__init__ = Mock(return_value=None)
    mock_val.__init__ = Mock(return_value=None)
    
    from data_manager import UserData, SessionData, DataManager


class TestUserDataUpdated:
    """Test cases for UserData class with new structure"""
    
    @patch('data_manager.database_manager')
    def test_init_new_user(self, mock_db):
        """Test UserData initialization for new user"""
        mock_db.get_user.return_value = None
        
        # Mock the base classes
        with patch('data_manager.TimestampedModel.__init__'), \
             patch('data_manager.ValidatedModel.__init__'):
            user = UserData(123456789)
        
        assert user.discord_id == 123456789
        assert user.valorant_accounts == []
        assert user.total_sessions == 0
        assert user.total_games_played == 0
        assert user.session_history == []
        
        # Verify database interaction
        mock_db.get_user.assert_called_once_with(123456789)
        mock_db.create_or_update_user.assert_called_once_with(123456789)
    
    @patch('data_manager.database_manager')
    def test_init_existing_user(self, mock_db):
        """Test UserData initialization for existing user"""
        existing_data = {
            'valorant_accounts': [{'username': 'Test', 'tag': 'NA1', 'puuid': 'test123', 'primary': True}],
            'total_sessions': 5,
            'total_games_played': 15,
            'session_history': ['session1', 'session2'],
            'created_at': '2023-01-01T00:00:00Z',
            'last_updated': '2023-01-02T00:00:00Z'
        }
        mock_db.get_user.return_value = existing_data
        
        with patch('data_manager.TimestampedModel.__init__'), \
             patch('data_manager.ValidatedModel.__init__'):
            user = UserData(123456789)
        
        assert user.discord_id == 123456789
        assert user.valorant_accounts == existing_data['valorant_accounts']
        assert user.total_sessions == 5
        assert user.total_games_played == 15
        assert user.session_history == existing_data['session_history']
        
        # Should not create new user
        mock_db.create_or_update_user.assert_not_called()


class TestSessionDataUpdated:
    """Test cases for SessionData class with new structure"""
    
    def test_init(self):
        """Test SessionData initialization"""
        with patch('data_manager.StatefulModel.__init__'):
            session = SessionData(
                session_id="test_session",
                channel_id=123456789,
                started_by=987654321
            )
        
        assert session.session_id == "test_session"
        assert session.channel_id == 123456789
        assert session.started_by == 987654321
        assert session.participants == []
        assert session.is_active is True


class TestDataManagerUpdated:
    """Test cases for DataManager class with new structure"""
    
    @patch('data_manager.database_manager')
    def test_init(self, mock_db):
        """Test DataManager initialization"""
        with patch('data_manager.DatabaseBackedManager.__init__'):
            manager = DataManager()
        
        # Should initialize the database
        mock_db.initialize.assert_called_once()
    
    @patch('data_manager.database_manager')
    def test_get_user_new(self, mock_db):
        """Test getting a new user"""
        mock_db.get_user.return_value = None
        
        with patch('data_manager.DatabaseBackedManager.__init__'), \
             patch('data_manager.UserData') as mock_user_data:
            
            manager = DataManager()
            mock_user_instance = Mock()
            mock_user_data.return_value = mock_user_instance
            
            result = manager.get_user(123456789)
            
            assert result == mock_user_instance
            mock_user_data.assert_called_once_with(123456789)
    
    @patch('data_manager.database_manager')  
    def test_create_session(self, mock_db):
        """Test creating a new session"""
        mock_db.create_session.return_value = "session123"
        
        with patch('data_manager.DatabaseBackedManager.__init__'), \
             patch('data_manager.SessionData') as mock_session_data:
            
            manager = DataManager()
            mock_session_instance = Mock()
            mock_session_data.return_value = mock_session_instance
            
            result = manager.create_session(
                channel_id=123456789,
                started_by=987654321,
                game_name="Valorant"
            )
            
            assert result == mock_session_instance
            mock_db.create_session.assert_called_once()


class TestIntegrationUpdated:
    """Integration tests for updated data manager"""
    
    @patch('data_manager.database_manager')
    def test_user_session_flow(self, mock_db):
        """Test complete user and session workflow"""
        # Mock database responses
        mock_db.get_user.return_value = None
        mock_db.create_session.return_value = "session123"
        
        with patch('data_manager.DatabaseBackedManager.__init__'), \
             patch('data_manager.TimestampedModel.__init__'), \
             patch('data_manager.ValidatedModel.__init__'), \
             patch('data_manager.StatefulModel.__init__'):
            
            manager = DataManager()
            
            # Get user (creates new one)
            user = manager.get_user(123456789)
            assert user is not None
            
            # Create session
            session = manager.create_session(
                channel_id=123456789,
                started_by=987654321,
                game_name="Valorant"
            )
            assert session is not None
            
            # Verify database calls
            mock_db.get_user.assert_called_with(123456789)
            mock_db.create_session.assert_called_once()