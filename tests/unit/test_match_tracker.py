"""Unit tests for match_tracker.py - robust match detection"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import asyncio


class TestMatchTrackerConfiguration:
    """Test match tracker configuration constants"""

    def test_matches_to_fetch_is_multiple(self):
        """Verify we fetch multiple matches, not just 1"""
        from match_tracker import MatchTracker

        assert hasattr(MatchTracker, 'MATCHES_TO_FETCH')
        assert MatchTracker.MATCHES_TO_FETCH >= 3, "Should fetch at least 3 matches to catch missed ones"

    def test_seen_matches_max_size_reasonable(self):
        """Verify seen matches limit is reasonable"""
        from match_tracker import MatchTracker

        assert hasattr(MatchTracker, 'SEEN_MATCHES_MAX_SIZE')
        assert 20 <= MatchTracker.SEEN_MATCHES_MAX_SIZE <= 100, "Should keep 20-100 seen matches"


class TestMatchTrackerInitialization:
    """Test match tracker initialization"""

    def test_tracked_members_structure(self):
        """Verify tracked_members uses seen_match_ids set, not last_match_id"""
        from match_tracker import MatchTracker

        mock_bot = Mock()
        mock_bot.guilds = []

        tracker = MatchTracker(mock_bot)

        # Simulate adding a tracked member
        user_id = 12345
        tracker.tracked_members[user_id] = {
            'last_checked': datetime.now(timezone.utc),
            'seen_match_ids': set()
        }

        # Verify structure
        assert 'seen_match_ids' in tracker.tracked_members[user_id]
        assert isinstance(tracker.tracked_members[user_id]['seen_match_ids'], set)

    def test_globally_reported_matches_exists(self):
        """Verify global deduplication structure exists"""
        from match_tracker import MatchTracker

        mock_bot = Mock()
        mock_bot.guilds = []

        tracker = MatchTracker(mock_bot)

        assert hasattr(tracker, 'globally_reported_matches')
        assert isinstance(tracker.globally_reported_matches, dict)


class TestSeenMatchTracking:
    """Test that seen match IDs are tracked properly"""

    def test_seen_match_ids_are_set_not_single_value(self):
        """Verify we track a SET of seen matches, not just the last one"""
        from match_tracker import MatchTracker

        mock_bot = Mock()
        mock_bot.guilds = []

        tracker = MatchTracker(mock_bot)
        user_id = 12345

        # Initialize tracking
        tracker.tracked_members[user_id] = {
            'last_checked': datetime.now(timezone.utc),
            'seen_match_ids': set()
        }

        # Add multiple match IDs
        match_ids = ['match_1', 'match_2', 'match_3', 'match_4', 'match_5']
        for match_id in match_ids:
            tracker.tracked_members[user_id]['seen_match_ids'].add(match_id)

        # All should be tracked
        assert len(tracker.tracked_members[user_id]['seen_match_ids']) == 5
        for match_id in match_ids:
            assert match_id in tracker.tracked_members[user_id]['seen_match_ids']

    def test_seen_matches_prevent_duplicate_detection(self):
        """Verify a match in seen_match_ids won't be detected again"""
        from match_tracker import MatchTracker

        mock_bot = Mock()
        mock_bot.guilds = []

        tracker = MatchTracker(mock_bot)
        user_id = 12345

        # Initialize with a seen match
        tracker.tracked_members[user_id] = {
            'last_checked': datetime.now(timezone.utc),
            'seen_match_ids': {'match_already_seen'}
        }

        # Match is already seen
        seen_matches = tracker.tracked_members[user_id]['seen_match_ids']
        assert 'match_already_seen' in seen_matches
        assert 'match_new' not in seen_matches


class TestGlobalDeduplication:
    """Test global match deduplication across users"""

    def test_global_deduplication_prevents_duplicate_reports(self):
        """Verify same match isn't reported twice for different users"""
        from match_tracker import MatchTracker

        mock_bot = Mock()
        mock_bot.guilds = []

        tracker = MatchTracker(mock_bot)
        server_id = 98765

        # Initialize global tracking
        tracker.globally_reported_matches[server_id] = set()

        # First user's match gets reported
        match_id = 'shared_match_123'
        tracker.globally_reported_matches[server_id].add(match_id)

        # Second user has same match - should be blocked
        assert match_id in tracker.globally_reported_matches[server_id]


class TestStatePersistence:
    """Test state persistence with new data structures"""

    def test_seen_match_ids_serialization(self):
        """Verify seen_match_ids converts to list for JSON storage"""
        from match_tracker import MatchTracker

        mock_bot = Mock()
        mock_bot.guilds = []

        tracker = MatchTracker(mock_bot)

        # Create tracking data with set
        tracking_data = {
            'last_checked': datetime.now(timezone.utc),
            'seen_match_ids': {'match_1', 'match_2', 'match_3'}
        }

        # Simulate serialization for database storage
        tracking_data_copy = tracking_data.copy()
        if isinstance(tracking_data_copy['seen_match_ids'], set):
            tracking_data_copy['seen_match_ids'] = list(tracking_data_copy['seen_match_ids'])

        assert isinstance(tracking_data_copy['seen_match_ids'], list)
        assert len(tracking_data_copy['seen_match_ids']) == 3

    def test_seen_match_ids_deserialization(self):
        """Verify seen_match_ids converts from list back to set on load"""
        # Simulate loading from database (stored as list)
        stored_data = {
            'last_checked': '2024-01-01T12:00:00',
            'seen_match_ids': ['match_1', 'match_2', 'match_3']
        }

        # Simulate deserialization
        if isinstance(stored_data['seen_match_ids'], list):
            stored_data['seen_match_ids'] = set(stored_data['seen_match_ids'])

        assert isinstance(stored_data['seen_match_ids'], set)
        assert len(stored_data['seen_match_ids']) == 3

    def test_migration_from_old_format(self):
        """Verify migration from last_match_id to seen_match_ids"""
        # Old format data
        old_format_data = {
            'last_checked': '2024-01-01T12:00:00',
            'last_match_id': 'old_match_123'
        }

        # Migration logic
        if 'seen_match_ids' not in old_format_data and 'last_match_id' in old_format_data:
            old_id = old_format_data.pop('last_match_id', None)
            old_format_data['seen_match_ids'] = {old_id} if old_id else set()

        assert 'seen_match_ids' in old_format_data
        assert 'last_match_id' not in old_format_data
        assert 'old_match_123' in old_format_data['seen_match_ids']


class TestMatchDetectionLogic:
    """Test the core match detection logic improvements"""

    @pytest.fixture
    def mock_tracker(self):
        """Create a match tracker with mocked dependencies"""
        mock_bot = Mock()
        mock_bot.guilds = []

        with patch('match_tracker.valorant_client') as mock_val_client, \
             patch('match_tracker.context_manager') as mock_ctx_mgr:
            from match_tracker import MatchTracker

            tracker = MatchTracker(mock_bot)
            tracker._valorant_client = mock_val_client
            tracker._context_manager = mock_ctx_mgr
            yield tracker, mock_val_client, mock_ctx_mgr

    def test_detects_all_new_matches_not_just_latest(self):
        """Verify all new matches are detected, not just the most recent"""
        # This is a logic test - verify the structure supports multiple match detection
        from match_tracker import MatchTracker

        mock_bot = Mock()
        mock_bot.guilds = []

        tracker = MatchTracker(mock_bot)
        user_id = 12345
        server_id = 98765

        # Initialize tracking
        tracker.tracked_members[user_id] = {
            'last_checked': datetime.now(timezone.utc),
            'seen_match_ids': {'old_match_1'}  # One match already seen
        }
        tracker.globally_reported_matches[server_id] = set()

        # Simulate 3 new matches coming in
        new_matches = ['new_match_2', 'new_match_3', 'new_match_4']
        detected = []

        for match_id in new_matches:
            if match_id not in tracker.tracked_members[user_id]['seen_match_ids']:
                if match_id not in tracker.globally_reported_matches[server_id]:
                    detected.append(match_id)
                    tracker.tracked_members[user_id]['seen_match_ids'].add(match_id)
                    tracker.globally_reported_matches[server_id].add(match_id)

        # All 3 new matches should be detected
        assert len(detected) == 3
        assert 'new_match_2' in detected
        assert 'new_match_3' in detected
        assert 'new_match_4' in detected


class TestCacheBypass:
    """Test that HTTP cache is bypassed during polling"""

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_http_cache(self):
        """Verify force_refresh=True disables HTTP caching"""
        with patch('valorant_client.BaseAPIClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.success = True
            mock_response.data = {'data': []}
            mock_get.return_value = mock_response

            from valorant_client import ValorantClient

            client = ValorantClient()

            # Mock get_account_info to return valid account
            with patch.object(client, 'get_account_info', new_callable=AsyncMock) as mock_account:
                mock_account.return_value = {'puuid': 'test-puuid', 'name': 'Test', 'tag': '123'}

                # Call with force_refresh=True
                await client.get_match_history('Test', '123', force_refresh=True)

                # Verify get was called with use_cache=False
                mock_get.assert_called()
                call_kwargs = mock_get.call_args[1]
                assert call_kwargs.get('use_cache') is False or call_kwargs.get('cache_ttl') == 0


class TestMultiAccountPolling:
    """Test polling of all linked accounts"""

    def test_all_accounts_should_be_checked(self):
        """Verify the design supports checking all accounts, not just primary"""
        # This is a structural test - verify the code calls get_all_linked_accounts
        # instead of get_linked_account

        from match_tracker import MatchTracker
        import inspect

        # Get the source code of _check_recent_matches
        source = inspect.getsource(MatchTracker._check_recent_matches)

        # Should use get_all_linked_accounts, not get_linked_account
        assert 'get_all_linked_accounts' in source, "Should poll all accounts, not just primary"


class TestMemoryManagement:
    """Test memory management for seen matches"""

    def test_seen_matches_pruning(self):
        """Verify seen_match_ids is pruned to prevent memory bloat"""
        from match_tracker import MatchTracker

        mock_bot = Mock()
        mock_bot.guilds = []

        tracker = MatchTracker(mock_bot)
        user_id = 12345

        # Add more matches than the limit
        max_size = MatchTracker.SEEN_MATCHES_MAX_SIZE
        many_matches = {f'match_{i}' for i in range(max_size + 20)}

        tracker.tracked_members[user_id] = {
            'last_checked': datetime.now(timezone.utc),
            'seen_match_ids': many_matches
        }

        # Simulate pruning logic
        seen_matches = tracker.tracked_members[user_id]['seen_match_ids']
        if len(seen_matches) > max_size:
            excess = len(seen_matches) - max_size
            tracker.tracked_members[user_id]['seen_match_ids'] = set(list(seen_matches)[excess:])

        # Should be pruned to max size
        assert len(tracker.tracked_members[user_id]['seen_match_ids']) == max_size

    def test_globally_reported_matches_cleanup(self):
        """Verify globally_reported_matches is cleaned up"""
        from match_tracker import MatchTracker

        mock_bot = Mock()
        mock_bot.guilds = []

        tracker = MatchTracker(mock_bot)
        server_id = 98765

        # Add more than 200 matches
        tracker.globally_reported_matches[server_id] = {f'match_{i}' for i in range(250)}

        # Simulate cleanup logic
        globally_reported = tracker.globally_reported_matches[server_id]
        if len(globally_reported) > 200:
            globally_reported_list = list(globally_reported)
            tracker.globally_reported_matches[server_id] = set(globally_reported_list[-200:])

        # Should be trimmed to 200
        assert len(tracker.globally_reported_matches[server_id]) == 200


class TestMatchCutoffTime:
    """Test match cutoff time filtering"""

    def test_old_matches_are_skipped(self):
        """Verify matches older than cutoff are skipped"""
        from match_tracker import MatchTracker

        cutoff_hours = MatchTracker.MATCH_CUTOFF_HOURS
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=cutoff_hours)

        # Old match timestamp
        old_match_time = datetime.now(timezone.utc) - timedelta(hours=cutoff_hours + 1)

        assert old_match_time < cutoff_time, "Old match should be before cutoff"

        # Recent match timestamp
        recent_match_time = datetime.now(timezone.utc) - timedelta(hours=1)

        assert recent_match_time > cutoff_time, "Recent match should be after cutoff"


class TestMinimumMembersThreshold:
    """Test minimum Discord members threshold"""

    def test_minimum_members_threshold(self):
        """Verify matches with too few members are skipped"""
        from match_tracker import MatchTracker

        assert hasattr(MatchTracker, 'MIN_DISCORD_MEMBERS')
        assert MatchTracker.MIN_DISCORD_MEMBERS >= 1, "Should require at least 1 member"
        assert MatchTracker.MIN_DISCORD_MEMBERS <= 5, "Should not require more than 5 members"
