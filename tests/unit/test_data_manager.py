import pytest
from unittest.mock import Mock, patch, mock_open
import json
import os
from datetime import datetime, timezone, timedelta
from freezegun import freeze_time
from data_manager import UserData, SessionData, DataManager


class TestUserData:
    """Test cases for UserData class"""
    
    def test_init(self):
        """Test UserData initialization"""
        user = UserData(123456789)
        
        assert user.discord_id == 123456789
        assert user.valorant_accounts == []
        assert user.total_sessions == 0
        assert user.total_games_played == 0
        assert user.session_history == []
        assert user.last_updated is not None
        
        # Backward compatibility properties
        assert user._valorant_username is None
        assert user._valorant_tag is None
        assert user._valorant_puuid is None
    
    def test_link_valorant_account_new(self):
        """Test linking a new Valorant account"""
        user = UserData(123456789)
        
        user.link_valorant_account("Player1", "NA1", "puuid123")
        
        assert len(user.valorant_accounts) == 1
        assert user.valorant_accounts[0]['username'] == "Player1"
        assert user.valorant_accounts[0]['tag'] == "NA1"
        assert user.valorant_accounts[0]['puuid'] == "puuid123"
        assert user.valorant_accounts[0]['primary'] is True
        
        # Backward compatibility
        assert user.valorant_username == "Player1"
        assert user.valorant_tag == "NA1"
        assert user.valorant_puuid == "puuid123"
    
    def test_link_multiple_accounts(self):
        """Test linking multiple Valorant accounts"""
        user = UserData(123456789)
        
        # Link first account
        user.link_valorant_account("Player1", "NA1", "puuid1")
        
        # Link second account, not as primary
        user.link_valorant_account("Player2", "EU1", "puuid2", set_primary=False)
        
        assert len(user.valorant_accounts) == 2
        assert user.valorant_accounts[0]['primary'] is True
        assert user.valorant_accounts[1]['primary'] is False
        
        # Link third account as primary
        user.link_valorant_account("Player3", "ASIA", "puuid3", set_primary=True)
        
        assert len(user.valorant_accounts) == 3
        assert user.valorant_accounts[0]['primary'] is False
        assert user.valorant_accounts[1]['primary'] is False
        assert user.valorant_accounts[2]['primary'] is True
        
        # Backward compatibility should point to primary
        assert user.valorant_username == "Player3"
        assert user.valorant_tag == "ASIA"
        assert user.valorant_puuid == "puuid3"
    
    def test_link_existing_account_update(self):
        """Test updating an existing account"""
        user = UserData(123456789)
        
        user.link_valorant_account("Player1", "NA1", "puuid_old")
        user.link_valorant_account("Player1", "NA1", "puuid_new")
        
        assert len(user.valorant_accounts) == 1
        assert user.valorant_accounts[0]['puuid'] == "puuid_new"
    
    def test_link_account_case_insensitive(self):
        """Test that account linking is case insensitive"""
        user = UserData(123456789)
        
        user.link_valorant_account("Player1", "NA1", "puuid1")
        user.link_valorant_account("player1", "na1", "puuid_updated")
        
        assert len(user.valorant_accounts) == 1
        assert user.valorant_accounts[0]['puuid'] == "puuid_updated"
    
    def test_remove_valorant_account(self):
        """Test removing Valorant accounts"""
        user = UserData(123456789)
        
        # Add accounts
        user.link_valorant_account("Player1", "NA1", "puuid1")
        user.link_valorant_account("Player2", "EU1", "puuid2", set_primary=False)
        
        # Remove non-primary account
        result = user.remove_valorant_account("Player2", "EU1")
        assert result is True
        assert len(user.valorant_accounts) == 1
        assert user.valorant_accounts[0]['username'] == "Player1"
        
        # Remove primary account (last one)
        result = user.remove_valorant_account("Player1", "NA1")
        assert result is True
        assert len(user.valorant_accounts) == 0
        assert user.valorant_username is None
        assert user.valorant_tag is None
        assert user.valorant_puuid is None
    
    def test_remove_primary_account_with_others(self):
        """Test removing primary account when others exist"""
        user = UserData(123456789)
        
        user.link_valorant_account("Player1", "NA1", "puuid1")
        user.link_valorant_account("Player2", "EU1", "puuid2", set_primary=False)
        
        # Remove primary account
        result = user.remove_valorant_account("Player1", "NA1")
        assert result is True
        assert len(user.valorant_accounts) == 1
        assert user.valorant_accounts[0]['primary'] is True
        assert user.valorant_username == "Player2"
    
    def test_remove_nonexistent_account(self):
        """Test removing non-existent account"""
        user = UserData(123456789)
        user.link_valorant_account("Player1", "NA1", "puuid1")
        
        result = user.remove_valorant_account("NonExistent", "TAG")
        assert result is False
        assert len(user.valorant_accounts) == 1
    
    def test_get_primary_account(self):
        """Test getting primary account"""
        user = UserData(123456789)
        
        # No accounts
        assert user.get_primary_account() is None
        
        # One account
        user.link_valorant_account("Player1", "NA1", "puuid1")
        primary = user.get_primary_account()
        assert primary['username'] == "Player1"
        
        # Multiple accounts
        user.link_valorant_account("Player2", "EU1", "puuid2", set_primary=True)
        primary = user.get_primary_account()
        assert primary['username'] == "Player2"
    
    def test_get_all_accounts(self):
        """Test getting all accounts"""
        user = UserData(123456789)
        
        user.link_valorant_account("Player1", "NA1", "puuid1")
        user.link_valorant_account("Player2", "EU1", "puuid2")
        
        accounts = user.get_all_accounts()
        assert len(accounts) == 2
        assert accounts[0]['username'] == "Player1"
        assert accounts[1]['username'] == "Player2"
    
    def test_set_primary_account(self):
        """Test setting primary account"""
        user = UserData(123456789)
        
        user.link_valorant_account("Player1", "NA1", "puuid1")
        user.link_valorant_account("Player2", "EU1", "puuid2", set_primary=False)
        
        result = user.set_primary_account("Player2", "EU1")
        assert result is True
        assert user.valorant_accounts[0]['primary'] is False
        assert user.valorant_accounts[1]['primary'] is True
        assert user.valorant_username == "Player2"
        
        # Try setting non-existent as primary
        result = user.set_primary_account("NonExistent", "TAG")
        assert result is False
    
    def test_increment_counters(self):
        """Test incrementing session and game counters"""
        user = UserData(123456789)
        
        user.increment_session_count()
        assert user.total_sessions == 1
        
        user.increment_games_played()
        user.increment_games_played()
        assert user.total_games_played == 2
    
    def test_session_history(self):
        """Test session history management"""
        user = UserData(123456789)
        
        user.add_session_to_history("session_1")
        user.add_session_to_history("session_2")
        assert len(user.session_history) == 2
        
        # Don't add duplicates
        user.add_session_to_history("session_1")
        assert len(user.session_history) == 2
    
    def test_to_dict(self):
        """Test conversion to dictionary"""
        user = UserData(123456789)
        user.link_valorant_account("Player1", "NA1", "puuid1")
        user.increment_session_count()
        user.add_session_to_history("session_1")
        
        data = user.to_dict()
        
        assert data['discord_id'] == 123456789
        assert len(data['valorant_accounts']) == 1
        assert data['total_sessions'] == 1
        assert data['total_games_played'] == 0
        assert data['session_history'] == ["session_1"]
        assert data['valorant_username'] == "Player1"  # Backward compatibility
    
    def test_from_dict_new_format(self):
        """Test creating UserData from dictionary (new format)"""
        data = {
            'discord_id': 123456789,
            'valorant_accounts': [
                {'username': 'Player1', 'tag': 'NA1', 'puuid': 'puuid1', 'primary': True},
                {'username': 'Player2', 'tag': 'EU1', 'puuid': 'puuid2', 'primary': False}
            ],
            'total_sessions': 5,
            'total_games_played': 10,
            'session_history': ['session_1', 'session_2'],
            'last_updated': '2024-01-01T00:00:00'
        }
        
        user = UserData.from_dict(data)
        
        assert user.discord_id == 123456789
        assert len(user.valorant_accounts) == 2
        assert user.total_sessions == 5
        assert user.total_games_played == 10
        assert len(user.session_history) == 2
        assert user.valorant_username == 'Player1'  # Primary account
    
    def test_from_dict_old_format_migration(self):
        """Test migrating from old format to new format"""
        data = {
            'discord_id': 123456789,
            'valorant_username': 'OldPlayer',
            'valorant_tag': 'OLD1',
            'valorant_puuid': 'old_puuid',
            'total_sessions': 3,
            'total_games_played': 7
        }
        
        user = UserData.from_dict(data)
        
        assert user.discord_id == 123456789
        assert len(user.valorant_accounts) == 1
        assert user.valorant_accounts[0]['username'] == 'OldPlayer'
        assert user.valorant_accounts[0]['tag'] == 'OLD1'
        assert user.valorant_accounts[0]['puuid'] == 'old_puuid'
        assert user.valorant_accounts[0]['primary'] is True
        assert user.total_sessions == 3
    
    def test_from_dict_old_format_no_puuid(self):
        """Test migrating from old format without PUUID"""
        data = {
            'discord_id': 123456789,
            'valorant_username': 'OldPlayer',
            'valorant_tag': 'OLD1',
            'valorant_puuid': None
        }
        
        user = UserData.from_dict(data)
        
        assert len(user.valorant_accounts) == 1
        assert user.valorant_accounts[0]['puuid'] == 'legacy_OldPlayer_OLD1'


class TestSessionData:
    """Test cases for SessionData class"""
    
    @freeze_time("2024-01-01 12:00:00")
    def test_init(self):
        """Test SessionData initialization"""
        session = SessionData("session_123", 111222333, 123456789)
        
        assert session.session_id == "session_123"
        assert session.channel_id == 111222333
        assert session.started_by == 123456789
        assert session.start_time == "2024-01-01T12:00:00+00:00"
        assert session.end_time is None
        assert session.participants == []
        assert session.game_name is None
        assert session.party_size == 5
        assert session.was_full is False
        assert session.duration_minutes == 0
    
    def test_add_participant(self):
        """Test adding participants"""
        session = SessionData("session_123", 111222333, 123456789)
        
        session.add_participant(123456789)
        session.add_participant(987654321)
        assert len(session.participants) == 2
        
        # Don't add duplicates
        session.add_participant(123456789)
        assert len(session.participants) == 2
    
    @freeze_time("2024-01-01 12:00:00")
    def test_end_session(self):
        """Test ending a session"""
        session = SessionData("session_123", 111222333, 123456789)
        
        # Advance time by 90 minutes
        with freeze_time("2024-01-01 13:30:00"):
            session.end_session()
        
        assert session.end_time == "2024-01-01T13:30:00+00:00"
        assert session.duration_minutes == 90
    
    def test_to_dict(self):
        """Test conversion to dictionary"""
        session = SessionData("session_123", 111222333, 123456789)
        session.add_participant(123456789)
        session.add_participant(987654321)
        session.game_name = "Valorant"
        session.was_full = True
        
        data = session.to_dict()
        
        assert data['session_id'] == "session_123"
        assert data['channel_id'] == 111222333
        assert data['started_by'] == 123456789
        assert len(data['participants']) == 2
        assert data['game_name'] == "Valorant"
        assert data['was_full'] is True
    
    def test_from_dict(self):
        """Test creating SessionData from dictionary"""
        data = {
            'session_id': 'session_123',
            'channel_id': 111222333,
            'started_by': 123456789,
            'start_time': '2024-01-01T12:00:00+00:00',
            'end_time': '2024-01-01T13:30:00+00:00',
            'participants': [123456789, 987654321],
            'game_name': 'Valorant',
            'party_size': 5,
            'was_full': True,
            'duration_minutes': 90
        }
        
        session = SessionData.from_dict(data)
        
        assert session.session_id == 'session_123'
        assert session.channel_id == 111222333
        assert session.started_by == 123456789
        assert session.end_time == '2024-01-01T13:30:00+00:00'
        assert len(session.participants) == 2
        assert session.game_name == 'Valorant'
        assert session.was_full is True
        assert session.duration_minutes == 90


class TestDataManager:
    """Test cases for DataManager class"""
    
    @patch('data_manager.os.path.exists')
    @patch('data_manager.os.makedirs')
    def test_init_no_data_files(self, mock_makedirs, mock_exists):
        """Test DataManager initialization with no existing data"""
        mock_exists.return_value = False
        
        manager = DataManager()
        
        assert len(manager.users) == 0
        assert len(manager.sessions) == 0
        mock_makedirs.assert_called_once()
    
    @patch('data_manager.os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('data_manager.json.load')
    def test_init_with_data_files(self, mock_json_load, mock_file, mock_exists):
        """Test DataManager initialization with existing data"""
        mock_exists.return_value = True
        
        # Mock user data
        users_data = {
            "123456789": {
                "discord_id": 123456789,
                "valorant_accounts": [],
                "total_sessions": 0
            }
        }
        
        # Mock session data
        sessions_data = {
            "session_123": {
                "session_id": "session_123",
                "channel_id": 111222333,
                "started_by": 123456789,
                "start_time": "2024-01-01T12:00:00+00:00",
                "participants": []
            }
        }
        
        mock_json_load.side_effect = [users_data, sessions_data]
        
        manager = DataManager()
        
        assert len(manager.users) == 1
        assert 123456789 in manager.users
        assert len(manager.sessions) == 1
        assert "session_123" in manager.sessions
    
    def test_get_user_new(self):
        """Test getting a new user"""
        with patch('data_manager.os.path.exists', return_value=False):
            with patch('data_manager.os.makedirs'):
                manager = DataManager()
        
        user = manager.get_user(123456789)
        
        assert user.discord_id == 123456789
        assert 123456789 in manager.users
    
    def test_get_user_existing(self):
        """Test getting an existing user"""
        with patch('data_manager.os.path.exists', return_value=False):
            with patch('data_manager.os.makedirs'):
                manager = DataManager()
        
        # Get user twice
        user1 = manager.get_user(123456789)
        user2 = manager.get_user(123456789)
        
        # Should be the same instance
        assert user1 is user2
    
    @patch('data_manager.os.makedirs')
    @patch('data_manager.json.dump')
    @patch('data_manager.os.replace')
    def test_save_user(self, mock_replace, mock_json_dump, mock_makedirs):
        """Test saving user data"""
        saved_data = None
        
        def capture_json_dump(data, file, **kwargs):
            nonlocal saved_data
            saved_data = data
        
        mock_json_dump.side_effect = capture_json_dump
        
        with patch('data_manager.os.path.exists', return_value=False):
            with patch('builtins.open', mock_open()):
                manager = DataManager()
                
                user = manager.get_user(123456789)
                user.link_valorant_account("Player1", "NA1", "puuid1")
                
                manager.save_user(123456789)
                
                assert saved_data is not None
                assert "123456789" in saved_data
                assert len(saved_data["123456789"]["valorant_accounts"]) == 1
                mock_replace.assert_called_once()
    
    @freeze_time("2024-01-01 12:00:00")
    def test_create_session(self):
        """Test creating a new session"""
        with patch('data_manager.os.path.exists', return_value=False):
            with patch('data_manager.os.makedirs'):
                manager = DataManager()
        
        session = manager.create_session(111222333, 123456789, "Valorant")
        
        assert session.channel_id == 111222333
        assert session.started_by == 123456789
        assert session.game_name == "Valorant"
        assert session.session_id in manager.sessions
        assert session.session_id.startswith("111222333_")
    
    @patch('data_manager.os.makedirs')
    @patch('data_manager.json.dump')
    @patch('data_manager.os.replace')
    def test_save_session(self, mock_replace, mock_json_dump, mock_makedirs):
        """Test saving session data"""
        saved_data = None
        
        def capture_json_dump(data, file, **kwargs):
            nonlocal saved_data
            saved_data = data
        
        mock_json_dump.side_effect = capture_json_dump
        
        with patch('data_manager.os.path.exists', return_value=False):
            with patch('builtins.open', mock_open()):
                manager = DataManager()
                
                session = manager.create_session(111222333, 123456789, "Valorant")
                session.add_participant(123456789)
                
                manager.save_session(session.session_id)
                
                assert saved_data is not None
                assert session.session_id in saved_data
                assert saved_data[session.session_id]["game_name"] == "Valorant"
                mock_replace.assert_called_once()
    
    @freeze_time("2024-01-01 12:00:00")
    def test_get_user_sessions(self):
        """Test getting sessions for a user"""
        with patch('data_manager.os.path.exists', return_value=False):
            with patch('data_manager.os.makedirs'):
                manager = DataManager()
        
        # Create sessions manually to control IDs
        session1 = SessionData("session_001", 111222333, 123456789)
        session1.add_participant(123456789)
        session1.start_time = "2024-01-01T12:00:00+00:00"
        manager.sessions["session_001"] = session1
        
        session2 = SessionData("session_002", 111222333, 987654321)
        session2.add_participant(123456789)
        session2.add_participant(987654321)
        session2.start_time = "2024-01-02T12:00:00+00:00"
        manager.sessions["session_002"] = session2
        
        session3 = SessionData("session_003", 111222333, 111111111)
        session3.add_participant(111111111)  # User not in this session
        manager.sessions["session_003"] = session3
        
        # Get user sessions
        user_sessions = manager.get_user_sessions(123456789)
        
        assert len(user_sessions) == 2
        assert user_sessions[0].start_time == "2024-01-02T12:00:00+00:00"  # Most recent first
        assert user_sessions[1].start_time == "2024-01-01T12:00:00+00:00"
    
    @freeze_time("2024-01-01 12:00:00")
    def test_get_channel_sessions(self):
        """Test getting sessions for a channel"""
        with patch('data_manager.os.path.exists', return_value=False):
            with patch('data_manager.os.makedirs'):
                manager = DataManager()
        
        # Create sessions manually to control IDs
        session1 = SessionData("session_001", 111222333, 123456789)
        session1.start_time = "2024-01-01T12:00:00+00:00"
        manager.sessions["session_001"] = session1
        
        session2 = SessionData("session_002", 111222333, 987654321)
        session2.start_time = "2024-01-02T12:00:00+00:00"
        manager.sessions["session_002"] = session2
        
        session3 = SessionData("session_003", 999888777, 111111111)  # Different channel
        manager.sessions["session_003"] = session3
        
        # Get channel sessions
        channel_sessions = manager.get_channel_sessions(111222333)
        
        assert len(channel_sessions) == 2
        assert channel_sessions[0].start_time == "2024-01-02T12:00:00+00:00"  # Most recent first
    
    @patch('builtins.open', side_effect=Exception("Write error"))
    @patch('data_manager.os.path.exists')
    @patch('data_manager.os.remove')
    def test_write_json_atomic_error_handling(self, mock_remove, mock_exists, mock_file):
        """Test atomic write error handling"""
        mock_exists.return_value = True
        
        with patch('data_manager.os.makedirs'):
            manager = DataManager()
        
        with pytest.raises(Exception):
            manager._write_json_atomic("test.json", {"test": "data"})
        
        # Should attempt to clean up temp file
        mock_remove.assert_called()


class TestIntegration:
    """Integration tests for data manager functionality"""
    
    def test_user_session_flow(self):
        """Test complete user and session flow"""
        with patch('data_manager.os.path.exists', return_value=False):
            with patch('data_manager.os.makedirs'):
                with patch('builtins.open', mock_open()):
                    with patch('data_manager.os.replace'):
                        manager = DataManager()
                        
                        # Create user and link account
                        user = manager.get_user(123456789)
                        user.link_valorant_account("Player1", "NA1", "puuid1")
                        
                        # Create session
                        session = manager.create_session(111222333, 123456789, "Valorant")
                        session.add_participant(123456789)
                        session.add_participant(987654321)
                        
                        # Update user stats
                        user.increment_session_count()
                        user.add_session_to_history(session.session_id)
                        
                        # Get another user who participated
                        user2 = manager.get_user(987654321)
                        user2.increment_session_count()
                        user2.add_session_to_history(session.session_id)
                        
                        # End session
                        session.end_session()
                        
                        # Verify relationships
                        assert len(manager.get_user_sessions(123456789)) == 1
                        assert len(manager.get_user_sessions(987654321)) == 1
                        assert len(manager.get_channel_sessions(111222333)) == 1
    
    def test_data_persistence_integration(self):
        """Test that data persists correctly across saves and loads"""
        import tempfile
        import shutil
        
        # Create temporary directory for test
        temp_dir = tempfile.mkdtemp()
        
        try:
            with patch('data_manager.DATA_DIR', temp_dir):
                # Create and save data
                manager1 = DataManager()
                
                user = manager1.get_user(123456789)
                user.link_valorant_account("Player1", "NA1", "puuid1")
                manager1.save_user(123456789)
                
                session = manager1.create_session(111222333, 123456789)
                session.add_participant(123456789)
                manager1.save_session(session.session_id)
                
                # Create new manager instance (simulating restart)
                manager2 = DataManager()
                
                # Verify data was loaded
                assert 123456789 in manager2.users
                assert manager2.users[123456789].valorant_username == "Player1"
                assert len(manager2.sessions) == 1
                
        finally:
            # Clean up
            shutil.rmtree(temp_dir)