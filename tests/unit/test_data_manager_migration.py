import os
import logging
from unittest.mock import MagicMock

import pytest

import data_manager as dm


def create_dummy_json_files(tmp_path):
    for name in ["users.json", "sessions.json", "channel_data.json"]:
        (tmp_path / name).write_text("{}")


def test_migration_triggers_backup(tmp_path, monkeypatch):
    create_dummy_json_files(tmp_path)

    mock_db = MagicMock()
    mock_db.migrate_from_json.return_value = True

    monkeypatch.setattr(dm, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dm, "database_manager", mock_db)
    monkeypatch.setattr(dm, "get_timestamp_string", lambda: "123456")

    dm.DataManager()

    mock_db.migrate_from_json.assert_called_once_with(
        os.path.join(str(tmp_path), "users.json"),
        os.path.join(str(tmp_path), "sessions.json"),
        os.path.join(str(tmp_path), "channel_data.json"),
    )

    backup_dir = tmp_path / "json_backup_auto_123456"
    assert backup_dir.is_dir()
    for name in ["users.json", "sessions.json", "channel_data.json"]:
        assert (backup_dir / name).exists()


def test_migration_failure_logs_error(tmp_path, monkeypatch, caplog):
    create_dummy_json_files(tmp_path)

    mock_db = MagicMock()
    mock_db.migrate_from_json.side_effect = RuntimeError("fail")

    monkeypatch.setattr(dm, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dm, "database_manager", mock_db)
    monkeypatch.setattr(dm, "get_timestamp_string", lambda: "123456")

    with caplog.at_level(logging.ERROR):
        dm.DataManager()

    assert any("Auto-migration error" in m for m in caplog.text.splitlines())
    assert any("Please run migrate_to_sqlite.py manually" in m for m in caplog.text.splitlines())
    assert not any(p.is_dir() and p.name.startswith("json_backup_auto_") for p in tmp_path.iterdir())
