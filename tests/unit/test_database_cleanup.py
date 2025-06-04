import os
import json
from database import DatabaseManager


def create_manager(tmp_path):
    db_path = os.path.join(tmp_path, "test.db")
    return DatabaseManager(db_path=db_path)


def test_match_cleanup_commits(tmp_path):
    mgr = create_manager(tmp_path)
    for i in range(4):
        mgr.store_match(f"m{i}", {"val": i})

    conn = mgr._get_connection()
    initial = conn.execute("SELECT COUNT(*) FROM henrik_matches").fetchone()[0]
    assert initial == 4

    mgr._check_and_cleanup_matches(conn, max_size_mb=0)
    conn.close()

    conn = mgr._get_connection()
    after = conn.execute("SELECT COUNT(*) FROM henrik_matches").fetchone()[0]
    conn.close()

    assert after < initial


def test_player_stats_cleanup_commits(tmp_path):
    mgr = create_manager(tmp_path)
    for i in range(4):
        mgr.store_player_stats(
            f"p{i}", "comp", 1, {"score": i}, [
                {"id": i}
            ]
        )

    conn = mgr._get_connection()
    initial = conn.execute("SELECT COUNT(*) FROM henrik_player_stats").fetchone()[0]
    assert initial == 4

    mgr._check_and_cleanup_player_stats(conn, max_size_mb=0)
    conn.close()

    conn = mgr._get_connection()
    after = conn.execute("SELECT COUNT(*) FROM henrik_player_stats").fetchone()[0]
    conn.close()

    assert after < initial


def test_account_cleanup_commits(tmp_path):
    mgr = create_manager(tmp_path)
    for i in range(4):
        mgr.store_account({"name": f"u{i}", "tag": "NA", "puuid": f"{i}"})

    conn = mgr._get_connection()
    initial = conn.execute("SELECT COUNT(*) FROM henrik_accounts").fetchone()[0]
    # Each store_account call creates entries by username_tag and puuid
    assert initial == 8

    mgr._check_and_cleanup_accounts(conn, max_size_mb=0)
    conn.close()

    conn = mgr._get_connection()
    after = conn.execute("SELECT COUNT(*) FROM henrik_accounts").fetchone()[0]
    conn.close()

    assert after < initial
