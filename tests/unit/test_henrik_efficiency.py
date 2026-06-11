"""Tests for the efficient Henrik API usage architecture:

- lightweight endpoints (stored-matches, mmr-history) for discovery/polling
- permanent SQLite caching of immutable match details
- per-match stat rows computed once and aggregated for stats commands
- client-level behavior: no retries on 4xx, rate-limit header tracking
"""

import os
import sys
import tempfile

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from api_clients import APIResponse
from database import DatabaseManager
from valorant_client import ValorantClient


def build_full_match(match_id='match-1', player_puuid='player-1', game_start=1700000000):
    """A minimal-but-complete competitive match with round data."""
    return {
        "metadata": {
            "matchid": match_id,
            "map": "Ascent",
            "mode": "Competitive",
            "mode_id": "competitive",
            "queue": "competitive",
            "rounds_played": 2,
            "game_start": game_start,
            "game_length": 1800,
        },
        "is_available": True,
        "players": {
            "all_players": [
                {
                    "puuid": player_puuid,
                    "team": "Red",
                    "character": "Jett",
                    "stats": {"kills": 3, "deaths": 1, "assists": 0,
                              "headshots": 2, "bodyshots": 1, "legshots": 0, "score": 600},
                    "damage_made": 400,
                    "damage_received": 200,
                },
                {
                    "puuid": "enemy-1",
                    "team": "Blue",
                    "character": "Sage",
                    "stats": {"kills": 1, "deaths": 3, "assists": 0,
                              "headshots": 0, "bodyshots": 3, "legshots": 0, "score": 150},
                    "damage_made": 150,
                    "damage_received": 400,
                },
            ]
        },
        "teams": {"red": {"has_won": True}, "blue": {"has_won": False}},
        "rounds": [
            {
                "winning_team": "Red",
                "player_stats": [
                    {
                        "player_puuid": player_puuid,
                        "kills": 2,
                        "kill_events": [
                            {"victim_puuid": "enemy-1", "kill_time_in_round": 1000,
                             "damage_weapon_name": "Vandal", "assistants": []},
                            {"victim_puuid": "enemy-1", "kill_time_in_round": 2000,
                             "damage_weapon_assets": {"display_name": "Phantom"}, "assistants": []},
                        ],
                        "economy": {"loadout_value": 800},
                    }
                ],
            },
            {
                "winning_team": "Red",
                "player_stats": [
                    {
                        "player_puuid": player_puuid,
                        "kills": 1,
                        "kill_events": [
                            {"victim_puuid": "enemy-1", "kill_time_in_round": 1500,
                             "damage_weapon_name": "Vandal", "assistants": []},
                        ],
                        "economy": {"loadout_value": 4000},
                    }
                ],
            },
        ],
    }


@pytest.fixture
def client():
    with patch('valorant_client.HENRIK_API_KEY', ''):
        return ValorantClient()


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield DatabaseManager(db_path=os.path.join(tmpdir, 'test.db'))


# ---------------------------------------------------------------------------
# Per-match stat rows + aggregation
# ---------------------------------------------------------------------------

class TestMatchStatsRows:
    def test_build_match_stats_row_basics(self, client):
        row = client.build_match_stats_row(build_full_match(), 'player-1')

        assert row['kills'] == 3
        assert row['deaths'] == 1
        assert row['won'] == 1
        assert row['mode'] == 'competitive'
        assert row['map'] == 'Ascent'
        assert row['agent'] == 'Jett'
        assert row['rounds_played'] == 2
        assert row['multikills_2k'] == 1
        assert row['first_bloods'] == 2  # first chronological kill both rounds
        assert row['weapon_kills'] == {'Vandal': 2, 'Phantom': 1}
        assert row['kast_rounds'] == 2
        assert row['pistol_rounds_played'] == 1  # round 0 only (2-round match)
        assert row['pistol_rounds_won'] == 1
        assert row['eco_rounds_played'] == 1  # loadout 800 in round 0
        assert row['started_at'] is not None

    def test_build_row_returns_none_for_absent_player(self, client):
        assert client.build_match_stats_row(build_full_match(), 'nobody') is None

    def test_aggregate_matches_calculate_player_stats(self, client):
        """Aggregating rows must equal the legacy full-match calculation."""
        matches = [build_full_match('m1'), build_full_match('m2')]

        legacy = client.calculate_player_stats(matches, 'player-1')
        rows = [client.build_match_stats_row(m, 'player-1') for m in matches]
        aggregated = client.aggregate_match_rows(rows)

        assert aggregated == legacy
        assert aggregated['total_matches'] == 2
        assert aggregated['total_kills'] == 6
        assert aggregated['weapon_kills'] == {'Vandal': 4, 'Phantom': 2}
        assert aggregated['win_rate'] == 100.0
        assert aggregated['kast_percentage'] == 100.0

    def test_aggregate_empty_rows(self, client):
        assert client.aggregate_match_rows([]) == {}


# ---------------------------------------------------------------------------
# Database round-trip for per-match rows
# ---------------------------------------------------------------------------

class TestPlayerMatchStatsStorage:
    def test_round_trip_preserves_aggregation(self, client, temp_db):
        match = build_full_match()
        row = client.build_match_stats_row(match, 'player-1')

        assert temp_db.store_player_match_stats('player-1', 'match-1', row)

        fetched = temp_db.get_player_match_stats('player-1', mode='competitive', limit=5)
        assert len(fetched) == 1

        # Aggregating the DB row gives the same stats as the in-memory row
        from_db = client.aggregate_match_rows(fetched)
        from_memory = client.aggregate_match_rows([row])
        assert from_db == from_memory

    def test_get_for_ids(self, client, temp_db):
        row = client.build_match_stats_row(build_full_match(), 'player-1')
        temp_db.store_player_match_stats('player-1', 'match-1', row)

        found = temp_db.get_player_match_stats_for_ids('player-1', ['match-1', 'match-2'])
        assert set(found.keys()) == {'match-1'}
        assert found['match-1']['kills'] == 3
        assert found['match-1']['weapon_kills'] == {'Vandal': 2, 'Phantom': 1}

    def test_store_is_idempotent(self, client, temp_db):
        row = client.build_match_stats_row(build_full_match(), 'player-1')
        temp_db.store_player_match_stats('player-1', 'match-1', row)
        temp_db.store_player_match_stats('player-1', 'match-1', row)
        assert len(temp_db.get_player_match_stats('player-1')) == 1

    def test_mode_filtering_and_ordering(self, client, temp_db):
        older = build_full_match('m-old', game_start=1700000000)
        newer = build_full_match('m-new', game_start=1700009999)
        temp_db.store_player_match_stats('player-1', 'm-old',
                                         client.build_match_stats_row(older, 'player-1'))
        temp_db.store_player_match_stats('player-1', 'm-new',
                                         client.build_match_stats_row(newer, 'player-1'))

        rows = temp_db.get_player_match_stats('player-1', mode='competitive')
        assert [r['match_id'] for r in rows] == ['m-new', 'm-old']
        assert temp_db.get_player_match_stats('player-1', mode='unrated') == []


# ---------------------------------------------------------------------------
# Lightweight endpoints
# ---------------------------------------------------------------------------

class TestLightweightEndpoints:
    @pytest.mark.asyncio
    async def test_stored_matches_light_normalization(self, client):
        payload = {'data': [
            {'meta': {'id': 'm1', 'map': {'id': 'x', 'name': 'Ascent'},
                      'mode': 'Competitive', 'started_at': '2024-01-02T00:00:00Z'},
             'stats': {'kills': 10}, 'teams': {'red': 13, 'blue': 8}},
            {'meta': {'id': 'm2', 'map': {'name': 'Bind'},
                      'mode': 'Competitive', 'started_at': '2024-01-03T00:00:00Z'},
             'stats': {'kills': 5}, 'teams': {}},
        ]}
        client.get = AsyncMock(return_value=APIResponse(data=payload, status_code=200))

        result = await client.get_stored_matches_light('User', 'TAG', puuid='abc', size=5,
                                                       mode='competitive')

        # by-puuid endpoint used, newest first
        endpoint = client.get.call_args.args[0]
        assert endpoint == 'v1/by-puuid/stored-matches/na/abc'
        assert client.get.call_args.kwargs['params'] == {'size': 5, 'mode': 'competitive'}
        assert [m['match_id'] for m in result] == ['m2', 'm1']
        assert result[0]['map'] == 'Bind'

    @pytest.mark.asyncio
    async def test_stored_matches_light_failure_returns_none(self, client):
        client.get = AsyncMock(return_value=APIResponse(data={}, status_code=404))
        assert await client.get_stored_matches_light('User', 'TAG') is None

    @pytest.mark.asyncio
    async def test_recent_competitive_updates_normalization(self, client):
        payload = {'data': [
            {'match_id': 'm-new', 'mmr_change_to_last_game': 18, 'date_raw': 1700009999},
            {'match_id': 'm-old', 'mmr_change_to_last_game': -12, 'date_raw': 1700000000},
        ]}
        client.get = AsyncMock(return_value=APIResponse(data=payload, status_code=200))

        result = await client.get_recent_competitive_updates('User', 'TAG', puuid='abc')

        endpoint = client.get.call_args.args[0]
        assert endpoint == 'v1/by-puuid/mmr-history/na/abc'
        assert result[0]['match_id'] == 'm-new'
        assert result[0]['rr_change'] == 18
        assert result[0]['started_at'] is not None

    @pytest.mark.asyncio
    async def test_manual_link_placeholder_puuid_not_used(self, client):
        """manual_<name>_<tag> placeholder puuids must not hit by-puuid endpoints."""
        client.get = AsyncMock(return_value=APIResponse(data={'data': []}, status_code=200))
        await client.get_recent_competitive_updates('User', 'TAG', puuid='manual_User_TAG')
        endpoint = client.get.call_args.args[0]
        assert endpoint == 'v1/mmr-history/na/User/TAG'


# ---------------------------------------------------------------------------
# Permanent match details cache
# ---------------------------------------------------------------------------

class TestMatchDetailsCache:
    @pytest.mark.asyncio
    async def test_db_hit_skips_api(self, client):
        stored = build_full_match()
        client.get = AsyncMock()
        with patch('valorant_client.database_manager.get_stored_match', return_value=stored):
            result = await client.get_match_details('match-1')

        assert result == stored
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_miss_fetches_and_stores(self, client):
        match = build_full_match()
        client.get = AsyncMock(return_value=APIResponse(data={'data': match}, status_code=200))
        with patch('valorant_client.database_manager.get_stored_match', return_value=None), \
             patch('valorant_client.database_manager.store_match') as mock_store:
            result = await client.get_match_details('match-1')

        assert result == match
        client.get.assert_called_once_with('v2/match/match-1', use_cache=False)
        mock_store.assert_called_once_with('match-1', match)


# ---------------------------------------------------------------------------
# get_player_stats orchestration
# ---------------------------------------------------------------------------

class TestGetPlayerStats:
    @pytest.mark.asyncio
    async def test_warm_path_makes_no_heavy_calls(self, client):
        """When all discovered matches already have rows, no match data is fetched."""
        match = build_full_match()
        row = client.build_match_stats_row(match, 'player-1')

        client.get_account_info = AsyncMock(return_value={'puuid': 'player-1'})
        client._discover_recent_match_ids = AsyncMock(return_value=['match-1'])
        client.get_match_history = AsyncMock()
        client.get_match_details = AsyncMock()

        with patch('valorant_client.database_manager.get_player_match_stats_for_ids',
                   return_value={'match-1': row}):
            stats = await client.get_player_stats('User', 'TAG', size=5)

        assert stats['total_matches'] == 1
        assert stats['total_kills'] == 3
        client.get_match_history.assert_not_called()
        client.get_match_details.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_match_fetched_individually_and_persisted(self, client):
        match = build_full_match()

        client.get_account_info = AsyncMock(return_value={'puuid': 'player-1'})
        client._discover_recent_match_ids = AsyncMock(return_value=['match-1'])
        client.get_match_history = AsyncMock()
        client.get_match_details = AsyncMock(return_value=match)

        with patch('valorant_client.database_manager.get_player_match_stats_for_ids',
                   return_value={}), \
             patch('valorant_client.database_manager.get_stored_match', return_value=None), \
             patch('valorant_client.database_manager.store_player_match_stats_bulk') as mock_store_rows:
            stats = await client.get_player_stats('User', 'TAG', size=5)

        assert stats['total_matches'] == 1
        client.get_match_details.assert_called_once_with('match-1')
        client.get_match_history.assert_not_called()  # below bulk threshold
        # the new row is persisted in the flush batch
        (entries,) = mock_store_rows.call_args.args
        assert [(e[0], e[1]) for e in entries] == [('player-1', 'match-1')]

    @pytest.mark.asyncio
    async def test_many_missing_matches_use_one_bulk_call(self, client):
        ids = [f'match-{i}' for i in range(5)]
        matches = [build_full_match(mid) for mid in ids]

        client.get_account_info = AsyncMock(return_value={'puuid': 'player-1'})
        client._discover_recent_match_ids = AsyncMock(return_value=ids)
        client.get_match_history = AsyncMock(return_value=matches)
        client.get_match_details = AsyncMock()

        with patch('valorant_client.database_manager.get_player_match_stats_for_ids',
                   return_value={}), \
             patch('valorant_client.database_manager.get_stored_match', return_value=None), \
             patch('valorant_client.database_manager.store_match'), \
             patch('valorant_client.database_manager.store_player_match_stats_bulk'):
            stats = await client.get_player_stats('User', 'TAG', size=5)

        assert stats['total_matches'] == 5
        client.get_match_history.assert_awaited_once()
        client.get_match_details.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_to_matchlist_when_discovery_fails(self, client):
        matches = [build_full_match('m1')]

        client.get_account_info = AsyncMock(return_value={'puuid': 'player-1'})
        client._discover_recent_match_ids = AsyncMock(return_value=[])
        client.get_match_history = AsyncMock(return_value=matches)

        with patch('valorant_client.database_manager.store_match'), \
             patch('valorant_client.database_manager.store_player_match_stats_bulk'):
            stats = await client.get_player_stats('User', 'TAG', size=20)

        assert stats['total_matches'] == 1
        # size must be clamped to the matchlist API max
        assert client.get_match_history.call_args.kwargs['size'] <= ValorantClient.MATCH_LIST_MAX_SIZE

    @pytest.mark.asyncio
    async def test_returns_none_without_account(self, client):
        client.get_account_info = AsyncMock(return_value=None)
        assert await client.get_player_stats('User', 'TAG') is None


# ---------------------------------------------------------------------------
# Tracker integration: record rows for everyone in a fetched match
# ---------------------------------------------------------------------------

class TestRecordMatchStats:
    def test_records_rows_for_each_player(self, client):
        match = build_full_match()
        with patch('valorant_client.database_manager.store_player_match_stats_bulk',
                   side_effect=len) as mock_store:
            count = client.record_match_stats_for_players(match, ['player-1', 'enemy-1', None])

        assert count == 2
        # all rows for the match go to the database in one batch
        (entries,) = mock_store.call_args.args
        assert {e[0] for e in entries} == {'player-1', 'enemy-1'}

    def test_no_match_id_stores_nothing(self, client):
        match = build_full_match()
        del match['metadata']['matchid']
        with patch('valorant_client.database_manager.store_player_match_stats_bulk') as mock_store:
            assert client.record_match_stats_for_players(match, ['player-1']) == 0
        mock_store.assert_not_called()


# ---------------------------------------------------------------------------
# Match tracker polling: lightweight detection, heavy fetch only on new match
# ---------------------------------------------------------------------------

class TestTrackerPolling:
    def _make_member(self, user_id=1, name='Player'):
        import discord
        member = MagicMock(spec=discord.Member)
        member.id = user_id
        member.display_name = name
        member.bot = False
        return member

    @pytest.mark.asyncio
    async def test_new_match_triggers_single_detail_fetch(self):
        import discord
        from datetime import datetime, timezone
        from match_tracker import MatchTracker

        bot = MagicMock(spec=discord.Client)
        tracker = MatchTracker(bot)
        guild = MagicMock(spec=discord.Guild)
        guild.id = 1

        member = self._make_member()
        match = build_full_match('new-match')
        account = {'username': 'User', 'tag': 'TAG', 'puuid': 'player-1'}

        with patch('match_tracker.valorant_client') as mock_client:
            mock_client.get_linked_account.return_value = account
            mock_client.get_recent_competitive_updates = AsyncMock(return_value=[
                {'match_id': 'new-match', 'started_at': datetime.now(timezone.utc),
                 'rr_change': 20}
            ])
            mock_client.get_match_details = AsyncMock(return_value=match)
            mock_client.record_match_stats_for_players = MagicMock(return_value=1)

            tracker.tracked_members[member.id] = {'last_checked': None, 'last_match_id': None}
            discord_members = [
                {'member': member, 'account': account,
                 'player_data': match['players']['all_players'][0]},
                {'member': self._make_member(2, 'Mate'), 'account': {'puuid': 'enemy-1'},
                 'player_data': match['players']['all_players'][1]},
            ]
            tracker._find_discord_members_in_match = AsyncMock(return_value=discord_members)
            tracker._send_match_results = AsyncMock()
            tracker._update_stack_activity = AsyncMock()

            await tracker._check_recent_matches(guild, [member])

            # Heavy match details fetched exactly once, results announced,
            # and stat rows persisted for every linked player in the match
            mock_client.get_match_details.assert_awaited_once_with('new-match')
            tracker._send_match_results.assert_awaited_once()
            mock_client.record_match_stats_for_players.assert_called_once()

            # Second poll with the same latest match: no further heavy fetches
            await tracker._check_recent_matches(guild, [member])
            mock_client.get_match_details.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_updates_means_no_fetches(self):
        import discord
        from match_tracker import MatchTracker

        bot = MagicMock(spec=discord.Client)
        tracker = MatchTracker(bot)
        guild = MagicMock(spec=discord.Guild)
        guild.id = 1
        member = self._make_member()

        with patch('match_tracker.valorant_client') as mock_client:
            mock_client.get_linked_account.return_value = {
                'username': 'User', 'tag': 'TAG', 'puuid': 'player-1'}
            mock_client.get_recent_competitive_updates = AsyncMock(return_value=[])
            mock_client.get_match_details = AsyncMock()

            tracker.tracked_members[member.id] = {'last_checked': None, 'last_match_id': None}
            await tracker._check_recent_matches(guild, [member])

            mock_client.get_match_details.assert_not_called()


# ---------------------------------------------------------------------------
# Base client behavior
# ---------------------------------------------------------------------------

class TestClientErrorHandling:
    def test_retry_after_parsing(self, client):
        assert client._get_retry_after_seconds({'Retry-After': '5'}) == 5
        assert client._get_retry_after_seconds({'x-ratelimit-reset': '12'}) == 12
        # Epoch-style values are capped instead of stalling for hours
        assert client._get_retry_after_seconds({'retry-after': '1700000000'}) == 60
        assert client._get_retry_after_seconds({}) == 30

    def test_rate_limit_header_tracking(self, client):
        info = client._parse_rate_limit_headers({
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': '15',
        })
        assert info is not None
        assert client._server_requests_remaining == 0
        assert client._server_limit_resets_at is not None

    @pytest.mark.asyncio
    async def test_4xx_response_not_retried(self, client):
        """A 404 must return immediately as a response, not raise/retry."""
        fake_response = MagicMock()
        fake_response.status = 404
        fake_response.headers = {'content-type': 'application/json'}
        fake_response.json = AsyncMock(return_value={'message': 'not found'})

        request_cm = MagicMock()
        request_cm.__aenter__ = AsyncMock(return_value=fake_response)
        request_cm.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.closed = False
        session.request = MagicMock(return_value=request_cm)
        client._session = session

        response = await client._make_request('GET', 'v1/account/none/none', use_cache=False)

        assert response.status_code == 404
        assert not response.success
        # exactly one attempt - no retries with backoff
        assert session.request.call_count == 1
