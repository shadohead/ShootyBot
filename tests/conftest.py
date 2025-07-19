import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
import asyncio
from datetime import datetime
import tempfile
import os
import json
import shutil
import importlib
import config
import database
import data_manager


@pytest.fixture
def mock_discord_user():
    """Create a mock Discord user object"""
    user = Mock()
    user.id = 123456789
    user.name = "TestUser"
    user.discriminator = "0001"
    user.mention = "<@123456789>"
    user.avatar_url = "https://example.com/avatar.png"
    return user


@pytest.fixture
def mock_discord_member():
    """Create a mock Discord member object"""
    member = Mock()
    member.id = 123456789
    member.name = "TestUser"
    member.discriminator = "0001"
    member.mention = "<@123456789>"
    member.avatar_url = "https://example.com/avatar.png"
    member.guild = Mock()
    member.guild.id = 987654321
    member.guild.name = "Test Guild"
    return member


@pytest.fixture
def mock_discord_channel():
    """Create a mock Discord channel object"""
    channel = AsyncMock()
    channel.id = 111222333
    channel.name = "test-channel"
    channel.guild = Mock()
    channel.guild.id = 987654321
    channel.send = AsyncMock()
    channel.fetch_message = AsyncMock()
    return channel


@pytest.fixture
def mock_discord_message():
    """Create a mock Discord message object"""
    message = AsyncMock()
    message.id = 555666777
    message.content = "Test message"
    message.author = Mock()
    message.author.id = 123456789
    message.channel = Mock()
    message.channel.id = 111222333
    message.edit = AsyncMock()
    message.add_reaction = AsyncMock()
    message.clear_reactions = AsyncMock()
    return message


@pytest.fixture
def mock_discord_reaction():
    """Create a mock Discord reaction object"""
    reaction = Mock()
    reaction.emoji = "👍"
    reaction.message = Mock()
    reaction.message.id = 555666777
    reaction.count = 1
    return reaction


@pytest.fixture
def mock_discord_context():
    """Create a mock Discord command context"""
    ctx = AsyncMock()
    ctx.author = Mock()
    ctx.author.id = 123456789
    ctx.author.name = "TestUser"
    ctx.channel = AsyncMock()
    ctx.channel.id = 111222333
    ctx.guild = Mock()
    ctx.guild.id = 987654321
    ctx.send = AsyncMock()
    ctx.reply = AsyncMock()
    return ctx


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data files"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_channel_data():
    """Sample channel data for testing"""
    return {
        "111222333": {
            "solo_users": ["123456789", "987654321"],
            "full_stack_users": ["111111111"],
            "required_users": 5,
            "channel_id": 111222333,
            "description": "Test Channel"
        }
    }


@pytest.fixture
def sample_user_data():
    """Sample user data for testing"""
    return {
        "123456789": {
            "discord_id": "123456789",
            "valorant_accounts": [
                {
                    "name": "TestPlayer",
                    "tag": "NA1",
                    "puuid": "test-puuid-123",
                    "region": "na",
                    "account_level": 100,
                    "linked_at": "2024-01-01T00:00:00",
                    "is_primary": True
                }
            ]
        }
    }


@pytest.fixture
def sample_session_data():
    """Sample session data for testing"""
    return {
        "session_123": {
            "id": "session_123",
            "channel_id": "111222333",
            "started_at": "2024-01-01T10:00:00",
            "ended_at": "2024-01-01T12:00:00",
            "participants": ["123456789", "987654321"],
            "duration_minutes": 120
        }
    }


@pytest.fixture
def mock_valorant_api_response():
    """Mock Valorant API response for testing"""
    return {
        "status": 200,
        "data": {
            "account": {
                "puuid": "test-puuid-123",
                "gameName": "TestPlayer",
                "tagLine": "NA1"
            },
            "level": 100,
            "progress": {
                "level": 100,
                "xp": 5000
            }
        }
    }


@pytest.fixture
def mock_match_history_response():
    """Mock match history response for testing"""
    return {
        "status": 200,
        "data": [
            {
                "meta": {
                    "id": "match_123",
                    "started_at": "2024-01-01T10:00:00",
                    "season": {
                        "short": "e5a3"
                    }
                },
                "stats": {
                    "puuid": "test-puuid-123",
                    "team": "Red",
                    "score": 25,
                    "kills": 20,
                    "deaths": 10,
                    "assists": 5
                },
                "teams": {
                    "red": {"won": True, "rounds": {"won": 13, "lost": 7}},
                    "blue": {"won": False, "rounds": {"won": 7, "lost": 13}}
                }
            }
        ]
    }


@pytest.fixture
def mock_filelock(mocker):
    """Mock filelock for testing"""
    mock = mocker.patch('filelock.FileLock')
    mock.return_value.__enter__ = Mock()
    mock.return_value.__exit__ = Mock()
    return mock


@pytest.fixture
async def async_mock_response():
    """Create an async mock response for aiohttp"""
    response = AsyncMock()
    response.status = 200
    response.json = AsyncMock(return_value={"status": "ok"})
    response.text = AsyncMock(return_value='{"status": "ok"}')
    return response


@pytest.fixture
def mock_datetime(mocker):
    """Mock datetime for consistent testing"""
    mock_dt = mocker.patch('datetime.datetime')
    mock_dt.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
    mock_dt.utcnow.return_value = datetime(2024, 1, 1, 12, 0, 0)
    return mock_dt

@pytest.fixture
def temp_manager(tmp_path, monkeypatch):
    """Provide a DataManager using a temporary SQLite database."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    db_path = os.path.join(tmp_path, "test.db")
    test_db = database.DatabaseManager(db_path=db_path)
    monkeypatch.setattr(database, "database_manager", test_db)
    monkeypatch.setattr(data_manager, "database_manager", test_db)
    manager = data_manager.DataManager()
    yield manager, test_db

