import importlib
from unittest.mock import MagicMock

import pytest

import config
import database
import data_manager as dm_module



def test_crud_operations(temp_manager):
    manager, db = temp_manager

    # Create and update user
    user = manager.get_user(1)
    user.link_valorant_account("Player1", "NA1", "p1")
    user.link_valorant_account("Player2", "EU1", "p2", set_primary=False)
    stored = db.get_user(1)
    assert len(stored["valorant_accounts"]) == 2

    user.remove_valorant_account("Player2", "EU1")
    stored = db.get_user(1)
    assert len(stored["valorant_accounts"]) == 1

    user.increment_session_count()
    user.increment_games_played()
    stored = db.get_user(1)
    assert stored["total_sessions"] == 1
    assert stored["total_games_played"] == 1

    # Session lifecycle
    session = manager.create_session(123, 1, game_name="Test")
    session.add_participant(1)
    session.add_participant(2)
    session.end_session()

    stored_session = db.get_session(session.session_id)
    assert stored_session is not None
    assert len(stored_session["participants"]) == 2
    assert stored_session["end_time"] is not None

    # Queries
    user_sessions = manager.get_user_sessions(1)
    assert any(s.session_id == session.session_id for s in user_sessions)
    channel_sessions = manager.get_channel_sessions(123)
    assert any(s.session_id == session.session_id for s in channel_sessions)

def test_json_migration(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dm_module, "DATA_DIR", str(tmp_path))
    users_file = tmp_path / "users.json"
    sessions_file = tmp_path / "sessions.json"
    channel_file = tmp_path / "channel_data.json"
    for f in (users_file, sessions_file, channel_file):
        f.write_text("{}")

    db_path = tmp_path / "shooty_bot.db"
    test_db = database.DatabaseManager(db_path=str(db_path))
    migrate_mock = MagicMock(return_value=True)
    monkeypatch.setattr(test_db, "migrate_from_json", migrate_mock)

    monkeypatch.setattr(database, "database_manager", test_db)
    monkeypatch.setattr(dm_module, "database_manager", test_db)

    def fake_exists(path):
        if path == str(db_path):
            return False
        return True

    monkeypatch.setattr(dm_module.os.path, "exists", fake_exists)

    dm_module.DataManager()
    assert migrate_mock.called

def test_session_queries(temp_manager):
    manager, db = temp_manager
    manager.create_session(10, 1)
    s2 = manager.create_session(10, 2)
    s2.add_participant(1)

    user_sessions = manager.get_user_sessions(1)
    assert len(user_sessions) == 1
    channel_sessions = manager.get_channel_sessions(10)
    assert len(channel_sessions) == 2
