"""Tests for the database methods that back session restoration on restart."""
import os
from database import DatabaseManager


def create_manager(tmp_path):
    db_path = os.path.join(tmp_path, "test.db")
    return DatabaseManager(db_path=db_path)


def test_get_open_session_returns_unended(tmp_path):
    """Only the still-open (end_time IS NULL) session is returned."""
    mgr = create_manager(tmp_path)
    channel_id = 555

    mgr.create_session("old", channel_id, started_by=1)
    mgr.end_session("old", was_full=False)
    mgr.create_session("current", channel_id, started_by=1)

    open_session = mgr.get_open_session_for_channel(channel_id)
    assert open_session is not None
    assert open_session["session_id"] == "current"


def test_get_open_session_none_when_all_ended(tmp_path):
    mgr = create_manager(tmp_path)
    mgr.create_session("done", 777, started_by=1)
    mgr.end_session("done", was_full=False)

    assert mgr.get_open_session_for_channel(777) is None


def test_get_open_session_none_for_unknown_channel(tmp_path):
    mgr = create_manager(tmp_path)
    assert mgr.get_open_session_for_channel(999) is None


def test_get_open_session_picks_most_recent(tmp_path):
    """When two sessions are somehow open, the most recently started wins."""
    mgr = create_manager(tmp_path)
    channel_id = 123
    # start_time is ISO8601 so lexical ordering matches chronological ordering
    mgr.create_session("first", channel_id, started_by=1)
    import time
    time.sleep(0.01)
    mgr.create_session("second", channel_id, started_by=1)

    open_session = mgr.get_open_session_for_channel(channel_id)
    assert open_session["session_id"] == "second"


def test_get_all_channel_settings(tmp_path):
    mgr = create_manager(tmp_path)
    mgr.save_channel_settings(111, role_code="<@&1>", current_st_message_id=1001)
    mgr.save_channel_settings(222, role_code="<@&2>", current_st_message_id=2002)

    all_settings = mgr.get_all_channel_settings()
    by_channel = {row["channel_id"]: row for row in all_settings}

    assert set(by_channel) == {111, 222}
    assert by_channel[111]["current_st_message_id"] == 1001
    assert by_channel[222]["current_st_message_id"] == 2002


def test_get_all_channel_settings_empty(tmp_path):
    mgr = create_manager(tmp_path)
    assert mgr.get_all_channel_settings() == []
