import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from database import DatabaseManager


def create_manager(tmp_path):
    db_path = os.path.join(tmp_path, "test.db")
    return DatabaseManager(db_path=db_path)


def test_create_or_update_user_logs_error(tmp_path):
    mgr = create_manager(tmp_path)
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = Exception("boom")
    mgr._get_connection = Mock(return_value=mock_conn)

    with patch('database.logging') as mock_logging:
        result = mgr.create_or_update_user(123)
        assert result is False
        mock_logging.error.assert_called()
        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()


def test_get_user_logs_error(tmp_path):
    mgr = create_manager(tmp_path)
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = Exception("boom")
    mgr._get_connection = Mock(return_value=mock_conn)

    with patch('database.logging') as mock_logging:
        result = mgr.get_user(321)
        assert result is None
        mock_logging.error.assert_called()
        mock_conn.close.assert_called_once()
