import pytest
from freezegun import freeze_time

from data_manager import SessionData
from database import database_manager

@freeze_time("2024-01-01 12:00:00")
def test_cancel_session_records_state_and_duration(tmp_path):
    session = SessionData("cancel_test_session", 111222333, 123456789)
    # Advance time 30 minutes and cancel
    with freeze_time("2024-01-01 12:30:00"):
        session.cancel_session()

    assert session.state == 'cancelled'
    assert session.end_time == "2024-01-01T12:30:00+00:00"
    assert session.duration_minutes == 30

    # Ensure persisted values were saved in database
    stored = database_manager.get_session(session.session_id)
    assert stored["end_time"] == "2024-01-01T12:30:00+00:00"
    assert stored["duration_minutes"] == 30
    # to_dict should reflect the cancelled state
    data = session.to_dict()
    assert data["state"] == 'cancelled'
