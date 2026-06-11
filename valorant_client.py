import logging
from collections import defaultdict
from typing import Optional, Dict, Any, List
import discord
from data_manager import data_manager
from config import HENRIK_API_KEY, VALORANT_REGION, HENRIK_REQUESTS_PER_MINUTE
from utils import log_error, parse_henrik_timestamp
from api_clients import BaseAPIClient, RateLimitInfo, APIResponse
from database import database_manager

# Henrik/Valorant competitive tier numbers -> human readable names.
# Tiers 1 and 2 are unused by Riot. 0 == Unrated.
RANK_TIERS = {
    0: "Unrated",
    3: "Iron 1", 4: "Iron 2", 5: "Iron 3",
    6: "Bronze 1", 7: "Bronze 2", 8: "Bronze 3",
    9: "Silver 1", 10: "Silver 2", 11: "Silver 3",
    12: "Gold 1", 13: "Gold 2", 14: "Gold 3",
    15: "Platinum 1", 16: "Platinum 2", 17: "Platinum 3",
    18: "Diamond 1", 19: "Diamond 2", 20: "Diamond 3",
    21: "Ascendant 1", 22: "Ascendant 2", 23: "Ascendant 3",
    24: "Immortal 1", 25: "Immortal 2", 26: "Immortal 3",
    27: "Radiant",
}

# Emoji flair per rank family (matched on the patched tier name).
RANK_EMOJIS = {
    "Unrated": "❔", "Iron": "🟤", "Bronze": "🥉", "Silver": "⚪",
    "Gold": "🥇", "Platinum": "💧", "Diamond": "💎", "Ascendant": "🟢",
    "Immortal": "🔴", "Radiant": "✨",
}


def tier_name(currenttier: Any) -> str:
    """Resolve a numeric competitive tier to its patched name."""
    try:
        return RANK_TIERS.get(int(currenttier), "Unrated")
    except (TypeError, ValueError):
        return "Unrated"


def rank_emoji(patched_tier: Optional[str]) -> str:
    """Get an emoji for a patched tier name (e.g. 'Diamond 1' -> 💎)."""
    if not patched_tier:
        return "❔"
    family = patched_tier.split(" ")[0]
    return RANK_EMOJIS.get(family, "🎖️")


def get_player_rank(player_data: Dict[str, Any]) -> Optional[str]:
    """Extract a patched rank name from a match player object.

    Henrik match data exposes ``currenttier`` (int) and sometimes
    ``currenttier_patched`` (str). Prefer the patched string, fall back to the
    numeric mapping.
    """
    patched = player_data.get('currenttier_patched')
    if patched:
        return patched
    currenttier = player_data.get('currenttier')
    if currenttier is not None:
        return tier_name(currenttier)
    return None


class ValorantClient(BaseAPIClient):
    """Client for interacting with Henrik's Valorant API.

    Endpoint paths carry an explicit version prefix (v1/v2/v3) against a single
    base URL, so concurrent requests to different API versions are safe — the
    base URL is never mutated. Wherever a PUUID is known, the by-puuid endpoint
    variants are used: they skip Henrik's internal Riot-ID resolution and keep
    working when players rename.
    """

    # v3 matchlist endpoints return full match details and cap size at 10
    MATCH_LIST_MAX_SIZE = 10
    # Bound how many single-match detail fetches one stats call may trigger
    MAX_DETAIL_FETCHES = 10
    # If at least this many matches are missing, bulk-fetch via the matchlist
    # endpoint (1 request for up to 10 matches) instead of per-match requests
    BULK_FETCH_THRESHOLD = 3

    def __init__(self):
        # Henrik API rate limits per key tier: Basic = 30 req/min, Advanced = 90
        # (configure HENRIK_REQUESTS_PER_MINUTE to match your key)
        rate_limit = RateLimitInfo(
            requests_per_second=2.0,
            requests_per_minute=HENRIK_REQUESTS_PER_MINUTE,
            requests_per_hour=HENRIK_REQUESTS_PER_MINUTE * 60,
            burst_limit=5
        )

        super().__init__(
            base_url="https://api.henrikdev.xyz/valorant",
            api_key=HENRIK_API_KEY,
            rate_limit=rate_limit,
            timeout=30
        )

        self.region = VALORANT_REGION

        if HENRIK_API_KEY:
            logging.info(f"Using Henrik API with key ({HENRIK_REQUESTS_PER_MINUTE} req/min, region {self.region})")
        else:
            logging.info("Using Henrik API without key - most endpoints now require one")
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get current headers for backward compatibility with tests."""
        return self._get_default_headers()
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for Henrik API."""
        if self.api_key:
            return {'Authorization': self.api_key}
        return {}
    
    async def health_check(self) -> bool:
        """Check if the Henrik API is healthy."""
        try:
            response = await self.get(f'v1/status/{self.region}', use_cache=False, cache_ttl=0)
            if response.success:
                return True
        except Exception:
            pass
        # If the status endpoint is unavailable, try a basic query
        try:
            response = await self.get('v1/account/test/0000', use_cache=False, cache_ttl=0)
            # Even 404 means API is responding
            return response.status_code in [200, 404]
        except Exception:
            return False
    
    async def get_account_info(self, username: str, tag: str) -> Optional[Dict[str, Any]]:
        """Get account information by username and tag"""
        try:
            # Check database storage first
            stored_account = database_manager.get_stored_account(username=username, tag=tag)
            if stored_account:
                logging.debug(f"Using stored account info for {username}#{tag}")
                return stored_account
            
            response = await self.get(f'v1/account/{username}/{tag}', cache_ttl=300)
            
            if response.success:
                account_data = self._unwrap(response)
                
                # Store the account data permanently
                database_manager.store_account(account_data, username=username, tag=tag)
                
                return account_data
            elif response.status_code == 401:
                log_error("Henrik API authentication", Exception("API key needed"))
                return None
            elif response.status_code == 404:
                logging.warning(f"Valorant account not found: {username}#{tag}")
                return None
            else:
                log_error(f"Valorant API request", Exception(f"Status {response.status_code}"))
                return None
                
        except Exception as e:
            log_error("fetching Valorant account info", e)
            return None
    
    async def link_account(self, discord_id: int, username: str, tag: str) -> Dict[str, Any]:
        """Link a Discord user to a Valorant account"""
        # Remove # if user included it
        if tag.startswith('#'):
            tag = tag[1:]
        
        # Get account info from API
        account_info = await self.get_account_info(username, tag)
        
        if not account_info:
            return {
                'success': False,
                'error': 'Henrik API now requires authentication. Please get an API key from https://docs.henrikdev.xyz and add it to your .env file as HENRIK_API_KEY=your_key_here'
            }
        
        # Extract relevant data
        puuid = account_info.get('puuid')
        name = account_info.get('name', username)
        actual_tag = account_info.get('tag', tag)
        
        if not puuid:
            return {
                'success': False,
                'error': 'Invalid account data from API'
            }
        
        # Save to data manager
        user_data = data_manager.get_user(discord_id)
        user_data.link_valorant_account(name, actual_tag, puuid)
        data_manager.save_user(discord_id)
        
        return {
            'success': True,
            'username': name,
            'tag': actual_tag,
            'puuid': puuid,
            'card': account_info.get('card', {})
        }
    
    async def unlink_account(self, discord_id: int) -> bool:
        """Unlink a Discord user's Valorant account"""
        try:
            user_data = data_manager.get_user(discord_id)

            # Remove all linked accounts from the database
            for account in user_data.get_all_accounts():
                database_manager.remove_valorant_account(
                    discord_id,
                    account.get("username"),
                    account.get("tag"),
                )

            # Clear cached compatibility fields
            user_data.valorant_username = None
            user_data.valorant_tag = None
            user_data.valorant_puuid = None

            data_manager.save_user(discord_id)
            return True
        except Exception as e:
            log_error(f"unlinking account for {discord_id}", e)
            return False
    
    def get_linked_account(self, discord_id: int) -> Optional[Dict[str, str]]:
        """Get primary linked Valorant account for a Discord user"""
        user_data = data_manager.get_user(discord_id)
        return user_data.get_primary_account()
    
    def get_all_linked_accounts(self, discord_id: int) -> List[Dict[str, str]]:
        """Get all linked Valorant accounts for a Discord user"""
        user_data = data_manager.get_user(discord_id)
        return user_data.get_all_accounts()
    
    def is_playing_valorant(self, member: discord.Member) -> bool:
        """Check if a Discord member is currently playing Valorant"""
        if not member.activities:
            return False
        
        for activity in member.activities:
            if isinstance(activity, discord.Game):
                if activity.name and 'valorant' in activity.name.lower():
                    return True
            elif isinstance(activity, discord.Activity):
                if activity.name and 'valorant' in activity.name.lower():
                    return True
        
        return False
    
    def get_playing_members(self, guild: discord.Guild) -> list:
        """Get list of members currently playing Valorant"""
        playing_members = []
        
        for member in guild.members:
            if self.is_playing_valorant(member):
                playing_members.append(member)
        
        return playing_members
    
    @staticmethod
    def _unwrap(response: APIResponse) -> Any:
        """Henrik API wraps payloads in a 'data' field."""
        if isinstance(response.data, dict) and 'data' in response.data:
            return response.data['data']
        return response.data

    @staticmethod
    def _usable_puuid(puuid: Optional[str]) -> Optional[str]:
        """Return the puuid unless it's a placeholder from /shootymanuallink."""
        if puuid and not str(puuid).startswith('manual_'):
            return puuid
        return None

    async def get_match_history(self, username: str, tag: str, size: int = 5, mode: str = None, force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Get full match details for a player's recent matches (heavy call).

        This hits the v3 matchlist endpoint which returns *complete* match
        objects (all players, all rounds, all kill events) fetched live from
        Riot — payloads are large. Prefer get_player_stats() for stats and
        get_stored_matches_light() / get_recent_competitive_updates() for
        polling; use this only when full match details are actually needed.

        Args:
            username: Valorant username
            tag: Valorant tag
            size: Number of matches to fetch (API max is 10)
            mode: Game mode filter (competitive, unrated, replication, etc.)
        """
        try:
            # First get the account to find PUUID for cache lookup
            account_info = await self.get_account_info(username, tag)
            if not account_info:
                return None

            puuid = account_info.get('puuid')
            if not puuid:
                return None

            size = min(size, self.MATCH_LIST_MAX_SIZE)

            # Check database storage first (unless forcing refresh)
            if not force_refresh:
                stored_data = database_manager.get_stored_player_stats(puuid, mode, size, max_age_minutes=10)
                if stored_data:
                    stats_data, match_history_data = stored_data
                    logging.debug(f"Using stored match history for {username}#{tag}")
                    return match_history_data

            params = {'size': size}
            if mode:
                # Henrik has accepted both names across versions; send both
                params['filter'] = mode
                params['mode'] = mode

            usable_puuid = self._usable_puuid(puuid)
            if usable_puuid:
                endpoint = f'v3/by-puuid/matches/{self.region}/{usable_puuid}'
            else:
                endpoint = f'v3/matches/{self.region}/{username}/{tag}'

            response = await self.get(endpoint, params=params, cache_ttl=180)

            if response.success:
                match_history = self._unwrap(response)

                # Calculate stats and store both together
                stats = self.calculate_player_stats(match_history, puuid, competitive_only=(mode == 'competitive'))
                database_manager.store_player_stats(puuid, mode, size, stats, match_history)

                return match_history
            else:
                log_error("fetching match history", Exception(f"Status {response.status_code}"))
                return None

        except Exception as e:
            log_error("fetching match history", e)
            return None

    async def get_stored_matches_light(self, username: str, tag: str, puuid: str = None,
                                       size: int = 20, mode: str = None,
                                       force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Get a lightweight match list from Henrik's stored-matches endpoint.

        Served from Henrik's database (no live Riot fetch): each entry has only
        match metadata, the requested player's own scoreboard line, and team
        scores — a tiny payload compared to full match details, and cheaper
        against the API quota. No round/kill-event data.

        Returns a normalized list (most recent first)::

            [{'match_id', 'started_at' (ISO str or None), 'map', 'mode',
              'stats' (player's own line), 'teams'}, ...]
        """
        try:
            usable_puuid = self._usable_puuid(puuid)
            if usable_puuid:
                endpoint = f'v1/by-puuid/stored-matches/{self.region}/{usable_puuid}'
            else:
                endpoint = f'v1/stored-matches/{self.region}/{username}/{tag}'

            params = {'size': size}
            if mode:
                params['mode'] = mode

            response = await self.get(
                endpoint, params=params,
                use_cache=not force_refresh,
                cache_ttl=60
            )
            if not response.success:
                logging.debug(f"stored-matches fetch failed for {username}#{tag}: {response.status_code}")
                return None

            entries = self._unwrap(response) or []
            normalized = []
            for entry in entries:
                meta = entry.get('meta', {}) or {}
                match_id = meta.get('id')
                if not match_id:
                    continue
                started = parse_henrik_timestamp(meta.get('started_at'))
                map_info = meta.get('map') or {}
                normalized.append({
                    'match_id': match_id,
                    'started_at': started.isoformat() if started else None,
                    'map': map_info.get('name') if isinstance(map_info, dict) else map_info,
                    'mode': (meta.get('mode') or '').lower() or None,
                    'stats': entry.get('stats', {}),
                    'teams': entry.get('teams', {}),
                })

            normalized.sort(key=lambda m: m['started_at'] or '', reverse=True)
            return normalized
        except Exception as e:
            log_error(f"fetching stored matches for {username}#{tag}", e)
            return None

    async def get_recent_competitive_updates(self, username: str, tag: str,
                                             puuid: str = None,
                                             force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Get the player's recent competitive updates (lightweight, live data).

        Uses the v1 mmr-history endpoint: a small payload listing recent
        competitive matches with match ids, timestamps and RR changes. This is
        the cheap way to detect "did this player finish a new comp match?" —
        the old approach pulled the full match details every poll.

        Returns a normalized list (most recent first)::

            [{'match_id', 'started_at' (datetime or None), 'rr_change'}, ...]
        """
        try:
            usable_puuid = self._usable_puuid(puuid)
            if usable_puuid:
                endpoint = f'v1/by-puuid/mmr-history/{self.region}/{usable_puuid}'
            else:
                endpoint = f'v1/mmr-history/{self.region}/{username}/{tag}'

            response = await self.get(endpoint, use_cache=not force_refresh, cache_ttl=60)
            if not response.success:
                logging.debug(f"mmr-history fetch failed for {username}#{tag}: {response.status_code}")
                return None

            entries = self._unwrap(response) or []
            normalized = []
            for entry in entries:
                match_id = entry.get('match_id')
                if not match_id:
                    continue
                started = None
                if entry.get('date_raw'):
                    started = parse_henrik_timestamp(entry.get('date_raw'))
                if started is None:
                    started = parse_henrik_timestamp(entry.get('date'))
                normalized.append({
                    'match_id': match_id,
                    'started_at': started,
                    'rr_change': entry.get('mmr_change_to_last_game'),
                })
            return normalized
        except Exception as e:
            log_error(f"fetching competitive updates for {username}#{tag}", e)
            return None

    async def get_match_details(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Get full details for a single match, permanently cached in SQLite.

        Completed matches are immutable, so once stored they are never fetched
        again. Skips the in-memory response cache — payloads are large and the
        database is the cache.
        """
        if not match_id:
            return None
        try:
            stored = database_manager.get_stored_match(match_id)
            if stored:
                return stored

            response = await self.get(f'v2/match/{match_id}', use_cache=False)
            if not response.success:
                logging.warning(f"Match details fetch failed for {match_id}: {response.status_code}")
                return None

            match_data = self._unwrap(response)
            if match_data:
                database_manager.store_match(match_id, match_data)
            return match_data
        except Exception as e:
            log_error(f"fetching match details for {match_id}", e)
            return None

    async def get_mmr(self, username: str, tag: str, region: str = None,
                      force_refresh: bool = False, puuid: str = None) -> Optional[Dict[str, Any]]:
        """Fetch a player's current rank / RR info from Henrik's MMR endpoint.

        Returns a normalized dict::

            {
                'tier': 'Diamond 1',          # patched current tier
                'rr': 45,                     # ranking_in_tier (0-100)
                'rr_change': 18,              # mmr_change_to_last_game (+/-)
                'elo': 1845,
                'peak': 'Diamond 2',          # highest rank achieved (best-effort)
                'emoji': '💎',
            }

        Returns ``None`` if the account is private, not found, or the API is
        unavailable. This is intentionally best-effort so callers can degrade
        gracefully.
        """
        try:
            region = region or self.region
            usable_puuid = self._usable_puuid(puuid)
            if usable_puuid:
                endpoint = f'v2/by-puuid/mmr/{region}/{usable_puuid}'
            else:
                endpoint = f'v2/mmr/{region}/{username}/{tag}'

            response = await self.get(
                endpoint,
                use_cache=not force_refresh,
                cache_ttl=120  # Cache rank for 2 minutes
            )

            if not response.success:
                logging.warning(f"MMR fetch failed for {username}#{tag}: {response.status_code}")
                return None

            data = self._unwrap(response)
            if not data:
                return None

            current = data.get('current_data', {}) or {}
            highest = data.get('highest_rank', {}) or {}

            patched = current.get('currenttierpatched') or tier_name(current.get('currenttier'))
            return {
                'tier': patched,
                'rr': current.get('ranking_in_tier'),
                'rr_change': current.get('mmr_change_to_last_game'),
                'elo': current.get('elo'),
                'peak': highest.get('patched_tier'),
                'emoji': rank_emoji(patched),
            }

        except Exception as e:
            log_error(f"fetching MMR for {username}#{tag}", e)
            return None

    # ------------------------------------------------------------------
    # Stats pipeline
    #
    # Architecture: completed matches are immutable, so each (player, match)
    # stat line is computed exactly once (build_match_stats_row), persisted to
    # the queryable player_match_stats table, and aggregate stats are built by
    # folding rows together (aggregate_match_rows). New statlines can be added
    # by extending the row dict / 'extra' JSON column without re-fetching
    # anything from the API.
    # ------------------------------------------------------------------

    @staticmethod
    def _is_competitive_match(match: Dict[str, Any]) -> bool:
        """Check whether a match was played in the competitive queue."""
        metadata = match.get('metadata', {})
        fields = [
            (metadata.get('mode') or '').lower(),
            (metadata.get('mode_id') or '').lower(),
            (metadata.get('queue') or '').lower(),
        ]
        return any('competitive' in field for field in fields)

    @staticmethod
    def _match_id_of(match: Dict[str, Any]) -> Optional[str]:
        """Extract the match id from a full match object."""
        metadata = match.get('metadata', {})
        return metadata.get('matchid') or metadata.get('match_id')

    def calculate_player_stats(self, matches: List[Dict[str, Any]], player_puuid: str, competitive_only: bool = True) -> Dict[str, Any]:
        """Calculate comprehensive player statistics from full match objects.

        Pure computation (no API or database access): builds one stat row per
        match and aggregates them. Prefer get_player_stats() in command code —
        it reuses previously computed rows from the database.

        Args:
            matches: List of full match data from the API
            player_puuid: Player's PUUID to find in matches
            competitive_only: If True, only calculate stats from competitive matches
        """
        if not matches:
            return {}

        rows = []
        for match in matches:
            if not match.get('is_available', True):
                continue
            if competitive_only and not self._is_competitive_match(match):
                continue
            row = self.build_match_stats_row(match, player_puuid)
            if row:
                rows.append(row)

        return self.aggregate_match_rows(rows)

    def build_match_stats_row(self, match: Dict[str, Any], player_puuid: str) -> Optional[Dict[str, Any]]:
        """Compute one player's full stat line for a single match.

        Returns a flat dict matching the player_match_stats table columns, or
        None when the player isn't in the match. Uses the tournament-grade
        round analysis (KAST/FK/FD/MK verified against tracker.gg) when round
        data is present, falling back to estimates otherwise.
        """
        all_players = match.get('players', {}).get('all_players', [])
        player_data = next((p for p in all_players if p.get('puuid') == player_puuid), None)
        if not player_data:
            return None

        metadata = match.get('metadata', {})
        pstats = player_data.get('stats', {})
        teams = match.get('teams', {})
        team_key = (player_data.get('team') or 'Red').lower()
        won = teams[team_key].get('has_won', False) if team_key in teams else None
        started = parse_henrik_timestamp(metadata.get('game_start'))

        row = {
            'mode': (metadata.get('mode_id') or metadata.get('mode') or metadata.get('queue') or '').lower() or None,
            'map': metadata.get('map', 'Unknown'),
            'agent': player_data.get('character', 'Unknown'),
            'started_at': started.isoformat() if started else None,
            'won': None if won is None else (1 if won else 0),
            'rounds_played': metadata.get('rounds_played', 0),
            'kills': pstats.get('kills', 0),
            'deaths': pstats.get('deaths', 0),
            'assists': pstats.get('assists', 0),
            'headshots': pstats.get('headshots', 0),
            'bodyshots': pstats.get('bodyshots', 0),
            'legshots': pstats.get('legshots', 0),
            'score': pstats.get('score', 0),
            'damage_made': player_data.get('damage_made', 0),
            'damage_received': player_data.get('damage_received', 0),
            'kast_rounds': 0,
            'first_bloods': 0,
            'first_deaths': 0,
            'multikills_2k': 0,
            'multikills_3k': 0,
            'multikills_4k': 0,
            'multikills_5k': 0,
            'rounds_survived': 0,
            'pistol_rounds_won': 0,
            'pistol_rounds_played': 0,
            'eco_rounds_won': 0,
            'eco_rounds_played': 0,
            'shots_hit': 0,
            'shots_fired': 0,
            'clutches_attempted': {},
            'clutches_won': {},
            'weapon_kills': {},
        }

        self._compute_round_stats(match, player_data, player_puuid, row)
        self._collect_weapon_kills(match, player_puuid, row)
        return row

    def _compute_round_stats(self, match: Dict[str, Any], player_data: Dict[str, Any],
                             player_puuid: str, row: Dict[str, Any]) -> None:
        """Round-by-round analysis for one match: KAST, FK/FD, multikills,
        survival and pistol/eco rounds.

        This is the proven algorithm that matches tracker.gg with 100% accuracy
        for KAST, FK, FD and MK (validated by unit tests against real data).
        """
        all_players = match.get('players', {}).get('all_players', [])
        players = {p['puuid']: p for p in all_players if p.get('puuid')}

        rounds_data = match.get('rounds', [])
        if not rounds_data:
            # No round data available - fall back to estimates over the
            # match's reported round count
            self._estimate_round_stats(player_data, row, row.get('rounds_played', 0) or 0,
                                       bool(row.get('won')))
            return

        player_team = (players.get(player_puuid, {}).get('team') or '').lower()

        for round_num, round_data in enumerate(rounds_data):
            round_events = round_data.get('player_stats', [])

            # Track kills/deaths/assists in this round for each player
            round_kills = defaultdict(int)
            round_assists = defaultdict(int)
            round_deaths = defaultdict(int)
            round_survivors = set(players)

            # Get kills from player_stats and deaths from events
            for player_round in round_events:
                puuid = player_round.get('player_puuid')
                if puuid in players:
                    round_kills[puuid] = player_round.get('kills', 0)

            # Collect all kill events and determine deaths/assists
            all_kill_events = []
            for player_round in round_events:
                puuid = player_round.get('player_puuid')
                for kill_event in player_round.get('kill_events', []):
                    all_kill_events.append({
                        'killer_puuid': puuid,
                        'victim_puuid': kill_event.get('victim_puuid'),
                        'kill_time': kill_event.get('kill_time_in_round', 0),
                    })

                    victim_puuid = kill_event.get('victim_puuid')
                    if victim_puuid in players:
                        round_deaths[victim_puuid] += 1
                        round_survivors.discard(victim_puuid)

                    for assistant in kill_event.get('assistants', []):
                        assist_puuid = assistant.get('puuid')
                        if assist_puuid in players:
                            round_assists[assist_puuid] += 1

            # Additional assists from damage events (50+ damage to a player who died)
            for player_round in round_events:
                puuid = player_round.get('player_puuid')
                if puuid in players and round_assists[puuid] == 0:
                    for damage_event in player_round.get('damage_events', []):
                        receiver_puuid = damage_event.get('receiver_puuid')
                        damage = damage_event.get('damage', 0)
                        if (receiver_puuid in round_deaths and
                                round_deaths[receiver_puuid] > 0 and
                                damage >= 50):
                            round_assists[puuid] += 1
                            break

            # Multi-kills - exact kill counts from round data
            kills_in_round = round_kills[player_puuid]
            if kills_in_round >= 5:
                row['multikills_5k'] += 1
            elif kills_in_round == 4:
                row['multikills_4k'] += 1
            elif kills_in_round == 3:
                row['multikills_3k'] += 1
            elif kills_in_round == 2:
                row['multikills_2k'] += 1

            # First kill and first death (chronological)
            if all_kill_events:
                all_kill_events.sort(key=lambda x: x['kill_time'])
                first_kill_event = all_kill_events[0]
                if first_kill_event['killer_puuid'] == player_puuid:
                    row['first_bloods'] += 1
                if first_kill_event['victim_puuid'] == player_puuid:
                    row['first_deaths'] += 1

            # KAST: Kill, Assist, Survived, or Traded
            kast_qualified = False
            if round_kills[player_puuid] > 0:
                kast_qualified = True
            elif round_assists[player_puuid] > 0:
                kast_qualified = True
            elif player_puuid in round_survivors:
                kast_qualified = True
                row['rounds_survived'] += 1
            elif round_deaths[player_puuid] > 0:
                # Conservative trade detection: a teammate killed our killer
                # within 3 seconds of our death
                death_times = [e['kill_time'] for e in all_kill_events
                               if e['victim_puuid'] == player_puuid]
                for death_time in death_times:
                    our_killer = next(
                        (e['killer_puuid'] for e in all_kill_events
                         if e['victim_puuid'] == player_puuid and e['kill_time'] == death_time),
                        None
                    )
                    for event in all_kill_events:
                        killer_team = (players.get(event['killer_puuid'], {}).get('team') or '').lower()
                        time_diff = event['kill_time'] - death_time
                        if (killer_team == player_team and
                                0 < time_diff <= 3000 and
                                event['victim_puuid'] == our_killer):
                            kast_qualified = True
                            break
                    if kast_qualified:
                        break

            if kast_qualified:
                row['kast_rounds'] += 1

            # Pistol / eco round tracking (queryable extras for fun statlines)
            winning_team = (round_data.get('winning_team') or '').lower()
            team_won_round = bool(winning_team) and winning_team == player_team

            if round_num in (0, 12):
                row['pistol_rounds_played'] += 1
                if team_won_round:
                    row['pistol_rounds_won'] += 1

            for player_round in round_events:
                if player_round.get('player_puuid') == player_puuid:
                    loadout_value = (player_round.get('economy') or {}).get('loadout_value', 0)
                    if loadout_value and loadout_value < 2000:
                        row['eco_rounds_played'] += 1
                        if team_won_round:
                            row['eco_rounds_won'] += 1
                    break

    def _estimate_round_stats(self, player_data: Dict[str, Any], row: Dict[str, Any],
                              rounds_played: int, match_won: bool) -> None:
        """Fallback estimates when a match has no round-by-round data."""
        player_stats = player_data.get('stats', {})
        kills = player_stats.get('kills', 0)

        if rounds_played > 0:
            kpr = kills / rounds_played

            # Basic multikill estimation
            if kpr >= 2.5:
                if kpr >= 4:
                    row['multikills_5k'] += max(1, int(kills // 5))
                elif kpr >= 3:
                    row['multikills_4k'] += max(1, int(kills // 4))
                else:
                    row['multikills_3k'] += max(1, int(kills // 3))
                row['multikills_2k'] += max(1, int(kills // 2))

            # Basic first blood estimation
            if kpr >= 1.5:
                estimated_first_bloods = int(rounds_played * 0.15)
            elif kpr >= 1.0:
                estimated_first_bloods = int(rounds_played * 0.10)
            elif kpr >= 0.7:
                estimated_first_bloods = int(rounds_played * 0.06)
            else:
                estimated_first_bloods = int(rounds_played * 0.03)
            row['first_bloods'] += max(0, estimated_first_bloods)

            # Basic survival estimation
            deaths = player_stats.get('deaths', 0)
            death_rate = deaths / rounds_played
            estimated_survival_rate = max(0.3, 1.0 - death_rate)
            row['rounds_survived'] += int(rounds_played * estimated_survival_rate)

        # Basic pistol round estimation
        if rounds_played >= 2:
            row['pistol_rounds_played'] += 2
            if match_won:
                row['pistol_rounds_won'] += 1

        # Shot tracking (estimate shots fired from hit stats, ~70% accuracy)
        total_shots_hit = (player_stats.get('headshots', 0) +
                           player_stats.get('bodyshots', 0) +
                           player_stats.get('legshots', 0))
        row['shots_hit'] += total_shots_hit
        if total_shots_hit > 0:
            row['shots_fired'] += int(total_shots_hit * 1.4)

    @staticmethod
    def _extract_weapon_name(kill_event: Dict[str, Any]) -> Optional[str]:
        """Extract a human-readable weapon name from a kill event.

        Henrik API kill events expose the weapon via ``damage_weapon_name`` and/or
        ``damage_weapon_assets.display_name``. We try the most reliable fields first
        and fall back to the raw id so unknown weapons are still grouped consistently.
        """
        assets = kill_event.get("damage_weapon_assets") or {}
        name = (
            kill_event.get("damage_weapon_name")
            or assets.get("display_name")
            or kill_event.get("damage_weapon_id")
        )
        if not name:
            return None
        name = str(name).strip()
        return name or None

    def _collect_weapon_kills(self, match: Dict[str, Any], player_puuid: str, row: Dict[str, Any]) -> None:
        """Tally the player's kills per weapon across all rounds of a match.

        Note: the Henrik API only tags weapons on kill events, not on damage
        events, so only per-weapon kill counts can be derived (not per-weapon
        headshot/bodyshot/legshot accuracy).
        """
        weapon_kills = row.setdefault('weapon_kills', {})

        for round_data in match.get('rounds', []):
            for player_round in round_data.get('player_stats', []):
                if player_round.get('player_puuid') != player_puuid:
                    continue

                for kill_event in player_round.get('kill_events', []):
                    weapon_name = self._extract_weapon_name(kill_event)
                    if not weapon_name:
                        continue
                    weapon_kills[weapon_name] = weapon_kills.get(weapon_name, 0) + 1

    def aggregate_match_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fold per-match stat rows (newest first) into the aggregate stats dict
        consumed by the stats/leaderboard/comparison commands."""
        if not rows:
            return {}

        stats = {
            'total_matches': 0,
            'wins': 0,
            'losses': 0,
            'total_kills': 0,
            'total_deaths': 0,
            'total_assists': 0,
            'total_headshots': 0,
            'total_bodyshots': 0,
            'total_legshots': 0,
            'total_score': 0,
            'total_rounds': 0,
            'total_damage_made': 0,
            'total_damage_received': 0,
            'kast_rounds': 0,
            'maps_played': {},
            'agents_played': {},
            'recent_matches': [],
            'multikills': {'2k': 0, '3k': 0, '4k': 0, '5k': 0},
            'clutches_attempted': {'1v2': 0, '1v3': 0, '1v4': 0, '1v5': 0},
            'clutches_won': {'1v2': 0, '1v3': 0, '1v4': 0, '1v5': 0},
            'first_bloods': 0,
            'first_deaths': 0,
            'total_rounds_played': 0,
            'rounds_survived': 0,
            'mvp_count': 0,
            'match_mvp_count': 0,
            'pistol_rounds_won': 0,
            'pistol_rounds_played': 0,
            'eco_rounds_won': 0,
            'eco_rounds_played': 0,
            'current_win_streak': 0,
            'current_loss_streak': 0,
            'max_win_streak': 0,
            'max_loss_streak': 0,
            'agent_performance': {},
            'map_performance': {},
            'total_shots_fired': 0,
            'total_shots_hit': 0,
            'weapon_kills': {}
        }

        for row in rows:
            stats['total_matches'] += 1

            kills = row.get('kills', 0) or 0
            deaths = row.get('deaths', 0) or 0
            assists = row.get('assists', 0) or 0
            score = row.get('score', 0) or 0
            damage_made = row.get('damage_made', 0) or 0
            damage_received = row.get('damage_received', 0) or 0
            rounds_played = row.get('rounds_played', 0) or 0

            stats['total_kills'] += kills
            stats['total_deaths'] += deaths
            stats['total_assists'] += assists
            stats['total_headshots'] += row.get('headshots', 0) or 0
            stats['total_bodyshots'] += row.get('bodyshots', 0) or 0
            stats['total_legshots'] += row.get('legshots', 0) or 0
            stats['total_score'] += score
            stats['total_damage_made'] += damage_made
            stats['total_damage_received'] += damage_received
            stats['total_rounds'] += rounds_played
            stats['total_rounds_played'] += rounds_played

            won = row.get('won')
            match_won = won == 1
            if won == 1:
                stats['wins'] += 1
            elif won == 0:
                stats['losses'] += 1

            map_name = row.get('map') or 'Unknown'
            agent_name = row.get('agent') or 'Unknown'
            stats['maps_played'][map_name] = stats['maps_played'].get(map_name, 0) + 1
            stats['agents_played'][agent_name] = stats['agents_played'].get(agent_name, 0) + 1

            stats['kast_rounds'] += row.get('kast_rounds', 0) or 0
            stats['first_bloods'] += row.get('first_bloods', 0) or 0
            stats['first_deaths'] += row.get('first_deaths', 0) or 0
            stats['rounds_survived'] += row.get('rounds_survived', 0) or 0
            stats['pistol_rounds_won'] += row.get('pistol_rounds_won', 0) or 0
            stats['pistol_rounds_played'] += row.get('pistol_rounds_played', 0) or 0
            stats['eco_rounds_won'] += row.get('eco_rounds_won', 0) or 0
            stats['eco_rounds_played'] += row.get('eco_rounds_played', 0) or 0
            stats['total_shots_hit'] += row.get('shots_hit', 0) or 0
            stats['total_shots_fired'] += row.get('shots_fired', 0) or 0

            for mk_key in ('2k', '3k', '4k', '5k'):
                stats['multikills'][mk_key] += row.get(f'multikills_{mk_key}', 0) or 0

            for clutch_key in ('1v2', '1v3', '1v4', '1v5'):
                stats['clutches_attempted'][clutch_key] += (row.get('clutches_attempted') or {}).get(clutch_key, 0)
                stats['clutches_won'][clutch_key] += (row.get('clutches_won') or {}).get(clutch_key, 0)

            for weapon, count in (row.get('weapon_kills') or {}).items():
                stats['weapon_kills'][weapon] = stats['weapon_kills'].get(weapon, 0) + count

            # Agent performance tracking
            agent_stats = stats['agent_performance'].setdefault(agent_name, {
                'matches': 0, 'wins': 0, 'kills': 0, 'deaths': 0, 'assists': 0,
                'damage': 0, 'score': 0
            })
            agent_stats['matches'] += 1
            if match_won:
                agent_stats['wins'] += 1
            agent_stats['kills'] += kills
            agent_stats['deaths'] += deaths
            agent_stats['assists'] += assists
            agent_stats['damage'] += damage_made
            agent_stats['score'] += score

            # Map performance tracking
            map_stats = stats['map_performance'].setdefault(map_name, {
                'matches': 0, 'wins': 0, 'kills': 0, 'deaths': 0, 'damage': 0
            })
            map_stats['matches'] += 1
            if match_won:
                map_stats['wins'] += 1
            map_stats['kills'] += kills
            map_stats['deaths'] += deaths
            map_stats['damage'] += damage_made

            stats['recent_matches'].append({
                'map': map_name,
                'agent': agent_name,
                'kills': kills,
                'deaths': deaths,
                'assists': assists,
                'score': score,
                'damage_made': damage_made,
                'damage_received': damage_received,
                'rounds_played': rounds_played,
                'won': match_won
            })

        # Calculate win/loss streaks
        self._calculate_streaks(stats)

        # Calculate derived stats
        self._finalize_aggregate_stats(stats)

        return stats

    def _finalize_aggregate_stats(self, stats: Dict[str, Any]) -> None:
        """Compute all derived/percentage stats from accumulated totals."""
        if stats['total_matches'] <= 0:
            return

        actual_match_rounds = stats['total_rounds']

        stats['win_rate'] = (stats['wins'] / stats['total_matches']) * 100
        stats['avg_kills'] = stats['total_kills'] / stats['total_matches']
        stats['avg_deaths'] = stats['total_deaths'] / stats['total_matches']
        stats['avg_assists'] = stats['total_assists'] / stats['total_matches']
        stats['avg_score'] = stats['total_score'] / stats['total_matches']
        stats['avg_damage_made'] = stats['total_damage_made'] / stats['total_matches']
        stats['avg_damage_received'] = stats['total_damage_received'] / stats['total_matches']

        stats['clutch_success_rate'] = self._calculate_clutch_success_rate(stats)

        # First blood rate: percentage of rounds where player got first blood
        if stats['total_rounds_played'] > 0:
            stats['first_blood_rate'] = (stats['first_bloods'] / stats['total_rounds_played']) * 100
        else:
            stats['first_blood_rate'] = 0

        # Survival rate: estimate based on deaths per round across all matches
        if actual_match_rounds > 0:
            death_rate = stats['total_deaths'] / actual_match_rounds
            stats['survival_rate'] = max(0, (1.0 - death_rate) * 100)
        else:
            stats['survival_rate'] = 0

        if stats['pistol_rounds_played'] > 0:
            stats['pistol_win_rate'] = (stats['pistol_rounds_won'] / stats['pistol_rounds_played']) * 100
        else:
            stats['pistol_win_rate'] = 0

        if stats['eco_rounds_played'] > 0:
            stats['eco_win_rate'] = (stats['eco_rounds_won'] / stats['eco_rounds_played']) * 100
        else:
            stats['eco_win_rate'] = 0

        # Accuracy (shots hit / shots fired)
        if stats['total_shots_fired'] > 0:
            stats['accuracy'] = (stats['total_shots_hit'] / stats['total_shots_fired']) * 100
        else:
            stats['accuracy'] = 0

        stats['performance_ratings'] = self._calculate_performance_ratings(stats)

        # DD (Damage Delta) - per-round difference between damage dealt and received
        if actual_match_rounds > 0:
            stats['damage_delta_per_round'] = (stats['total_damage_made'] - stats['total_damage_received']) / actual_match_rounds
        else:
            stats['damage_delta_per_round'] = 0

        # ACS (Average Combat Score) - simplified Valorant formula
        if actual_match_rounds > 0:
            adr = stats['total_damage_made'] / actual_match_rounds
            kill_contribution = (stats['total_kills'] / actual_match_rounds) * 70
            assist_contribution = (stats['total_assists'] / actual_match_rounds) * 25
            stats['acs'] = adr + kill_contribution + assist_contribution
        else:
            stats['acs'] = 0

        if stats['total_deaths'] > 0:
            stats['kd_ratio'] = stats['total_kills'] / stats['total_deaths']
            stats['kda_ratio'] = (stats['total_kills'] + stats['total_assists']) / stats['total_deaths']
        else:
            stats['kd_ratio'] = float(stats['total_kills'])
            stats['kda_ratio'] = float(stats['total_kills'] + stats['total_assists'])

        # Plus/Minus (+/-) - kills minus deaths
        stats['plus_minus'] = stats['total_kills'] - stats['total_deaths']

        total_shots = stats['total_headshots'] + stats['total_bodyshots'] + stats['total_legshots']
        if total_shots > 0:
            stats['headshot_percentage'] = (stats['total_headshots'] / total_shots) * 100
        else:
            stats['headshot_percentage'] = 0

        if actual_match_rounds > 0:
            stats['kast_percentage'] = (stats['kast_rounds'] / actual_match_rounds) * 100
            stats['adr'] = stats['total_damage_made'] / actual_match_rounds
        else:
            stats['kast_percentage'] = 0
            stats['adr'] = 0

    # ------------------------------------------------------------------
    # High-level stats orchestration (incremental fetch + SQLite rows)
    # ------------------------------------------------------------------

    async def get_player_stats(self, username: str, tag: str, size: int = 20,
                               mode: str = 'competitive',
                               force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get aggregate stats over a player's last `size` matches, cheaply.

        Strategy:
        1. Discover recent match ids via lightweight endpoints (stored-matches
           and, for competitive, mmr-history) - tiny payloads.
        2. Reuse per-match stat rows already in SQLite; matches are immutable
           so rows never need recomputation.
        3. Fetch full details only for unseen matches: one bulk matchlist call
           when several are missing, otherwise per-match requests (bounded).
        4. Aggregate rows into the same stats dict calculate_player_stats
           produces.

        Returns None when the account/API is unavailable; {} when no matches.
        """
        try:
            account_info = await self.get_account_info(username, tag)
            if not account_info:
                return None

            puuid = account_info.get('puuid')
            if not puuid:
                return None

            mode_norm = mode.lower() if mode else None

            ordered_ids = await self._discover_recent_match_ids(
                username, tag, puuid, size, mode_norm, force_refresh
            )

            if ordered_ids:
                known = database_manager.get_player_match_stats_for_ids(puuid, ordered_ids)
                missing = [mid for mid in ordered_ids if mid not in known]
                new_rows = []  # (puuid, match_id, row) persisted in one batch

                # Fill from permanently stored match data (no API cost)
                still_missing = []
                for mid in missing:
                    stored = database_manager.get_stored_match(mid)
                    row = self.build_match_stats_row(stored, puuid) if stored else None
                    if row:
                        new_rows.append((puuid, mid, row))
                        known[mid] = row
                    else:
                        still_missing.append(mid)

                # Several gaps: one bulk matchlist call covers up to 10 matches
                if len(still_missing) >= self.BULK_FETCH_THRESHOLD:
                    matches = await self.get_match_history(
                        username, tag, size=self.MATCH_LIST_MAX_SIZE,
                        mode=mode_norm, force_refresh=force_refresh
                    )
                    for match in matches or []:
                        mid = self._match_id_of(match)
                        if not mid:
                            continue
                        database_manager.store_match(mid, match)
                        if mid in still_missing:
                            row = self.build_match_stats_row(match, puuid)
                            if row:
                                new_rows.append((puuid, mid, row))
                                known[mid] = row
                    still_missing = [mid for mid in still_missing if mid not in known]

                # Fetch the remainder individually (bounded per call)
                for mid in still_missing[:self.MAX_DETAIL_FETCHES]:
                    match = await self.get_match_details(mid)
                    row = self.build_match_stats_row(match, puuid) if match else None
                    if row:
                        new_rows.append((puuid, mid, row))
                        known[mid] = row

                database_manager.store_player_match_stats_bulk(new_rows)

                rows = [known[mid] for mid in ordered_ids if mid in known]
                if mode_norm:
                    rows = [r for r in rows if not r.get('mode') or r.get('mode') == mode_norm]
                if rows:
                    return self.aggregate_match_rows(rows[:size])

            # Fallback: lightweight discovery unavailable - use the matchlist
            matches = await self.get_match_history(
                username, tag, size=min(size, self.MATCH_LIST_MAX_SIZE),
                mode=mode_norm, force_refresh=force_refresh
            )
            if matches is None:
                return None

            # Compute rows once: persist them for future incremental calls and
            # aggregate the same rows for the response
            rows = []
            new_rows = []
            for match in matches:
                if not match.get('is_available', True):
                    continue
                mid = self._match_id_of(match)
                if mid:
                    database_manager.store_match(mid, match)
                if mode_norm == 'competitive' and not self._is_competitive_match(match):
                    continue
                row = self.build_match_stats_row(match, puuid)
                if not row:
                    continue
                rows.append(row)
                if mid:
                    new_rows.append((puuid, mid, row))
            database_manager.store_player_match_stats_bulk(new_rows)

            return self.aggregate_match_rows(rows)
        except Exception as e:
            log_error(f"getting player stats for {username}#{tag}", e)
            return None

    async def _discover_recent_match_ids(self, username: str, tag: str, puuid: str,
                                         size: int, mode: Optional[str],
                                         force_refresh: bool) -> List[str]:
        """Discover a player's recent match ids using only lightweight calls.

        Combines Henrik's stored-matches (database-backed, deep history) with
        mmr-history (live competitive updates) so brand-new competitive matches
        are not missed. Returns ids ordered most recent first.
        """
        entries = []

        light = await self.get_stored_matches_light(
            username, tag, puuid=puuid, size=size, mode=mode, force_refresh=force_refresh
        )
        for match in light or []:
            entries.append((match.get('started_at') or '', match['match_id']))

        if mode == 'competitive':
            updates = await self.get_recent_competitive_updates(username, tag, puuid=puuid)
            for update in updates or []:
                started = update.get('started_at')
                entries.append((started.isoformat() if started else '', update['match_id']))

        seen = set()
        ordered = []
        for _, match_id in sorted(entries, key=lambda e: e[0], reverse=True):
            if match_id not in seen:
                seen.add(match_id)
                ordered.append(match_id)
        return ordered[:size]

    def record_match_stats_for_players(self, match_data: Dict[str, Any],
                                       puuids: List[str]) -> int:
        """Compute and persist per-match stat rows for the given players.

        Used by the match tracker so one fetched match warms the stats rows of
        every linked player who was in it. Returns the number of rows stored.
        """
        match_id = self._match_id_of(match_data)
        if not match_id:
            return 0

        entries = []
        for puuid in {p for p in puuids if p}:
            try:
                row = self.build_match_stats_row(match_data, puuid)
                if row:
                    entries.append((puuid, match_id, row))
            except Exception as e:
                log_error(f"recording match stats for {puuid} in {match_id}", e)
        return database_manager.store_player_match_stats_bulk(entries)

    def _calculate_streaks(self, stats: Dict[str, Any]):
        """Calculate win/loss streaks from recent matches"""
        recent_matches = stats.get('recent_matches', [])
        if not recent_matches:
            return
        
        # Sort by most recent first (reverse order since we append chronologically)
        recent_matches.reverse()
        
        current_streak = 0
        current_streak_type = None  # 'win' or 'loss'
        max_win_streak = 0
        max_loss_streak = 0
        temp_win_streak = 0
        temp_loss_streak = 0
        
        for match in recent_matches:
            if match['won']:
                if current_streak_type == 'win':
                    current_streak += 1
                else:
                    current_streak = 1
                    current_streak_type = 'win'
                temp_win_streak += 1
                temp_loss_streak = 0
                max_win_streak = max(max_win_streak, temp_win_streak)
            else:
                if current_streak_type == 'loss':
                    current_streak += 1
                else:
                    current_streak = 1
                    current_streak_type = 'loss'
                temp_loss_streak += 1
                temp_win_streak = 0
                max_loss_streak = max(max_loss_streak, temp_loss_streak)
        
        if current_streak_type == 'win':
            stats['current_win_streak'] = current_streak
            stats['current_loss_streak'] = 0
        else:
            stats['current_loss_streak'] = current_streak
            stats['current_win_streak'] = 0
        
        stats['max_win_streak'] = max_win_streak
        stats['max_loss_streak'] = max_loss_streak
    
    def _calculate_clutch_success_rate(self, stats: Dict[str, Any]) -> float:
        """Calculate overall clutch success rate"""
        total_attempted = sum(stats['clutches_attempted'].values())
        total_won = sum(stats['clutches_won'].values())
        
        if total_attempted > 0:
            return (total_won / total_attempted) * 100
        return 0
    
    def _calculate_performance_ratings(self, stats: Dict[str, Any]) -> Dict[str, str]:
        """Calculate fun performance ratings/badges"""
        ratings = {}
        
        # Fragger rating
        avg_kills = stats.get('avg_kills', 0)
        if avg_kills >= 20:
            ratings['fragger'] = '🔥 Demon Fragger'
        elif avg_kills >= 15:
            ratings['fragger'] = '💀 Elite Fragger'
        elif avg_kills >= 12:
            ratings['fragger'] = '⚡ Solid Fragger'
        else:
            ratings['fragger'] = '🎯 Entry Fragger'
        
        # Support rating
        avg_assists = stats.get('avg_assists', 0)
        if avg_assists >= 8:
            ratings['support'] = '👑 Support King'
        elif avg_assists >= 6:
            ratings['support'] = '🤝 Team Player'
        elif avg_assists >= 4:
            ratings['support'] = '✨ Helper'
        else:
            ratings['support'] = '🔫 Solo Player'
        
        # Survival rating
        survival_rate = stats.get('survival_rate', 0)
        if survival_rate >= 80:
            ratings['survival'] = '🛡️ Untouchable'
        elif survival_rate >= 70:
            ratings['survival'] = '🏃 Escape Artist'
        elif survival_rate >= 60:
            ratings['survival'] = '💪 Survivor'
        else:
            ratings['survival'] = '💥 Risk Taker'
        
        # Accuracy rating
        accuracy = stats.get('accuracy', 0)
        headshot_percentage = stats.get('headshot_percentage', 0)
        if headshot_percentage >= 35:
            ratings['accuracy'] = '🎯 Headshot Machine'
        elif headshot_percentage >= 25:
            ratings['accuracy'] = '🔥 Sharp Shooter'
        elif accuracy >= 70:
            ratings['accuracy'] = '💯 Precise'
        else:
            ratings['accuracy'] = '🌀 Spray Master'
        
        # Clutch rating
        clutch_rate = stats.get('clutch_success_rate', 0)
        total_clutches = sum(stats.get('clutches_won', {}).values())
        if total_clutches >= 5 and clutch_rate >= 60:
            ratings['clutch'] = '🏆 Clutch God'
        elif total_clutches >= 3 and clutch_rate >= 50:
            ratings['clutch'] = '⭐ Clutch King'
        elif total_clutches >= 1:
            ratings['clutch'] = '💎 Clutch Player'
        else:
            ratings['clutch'] = '🎲 Learning Clutches'
        
        return ratings
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage usage statistics"""
        try:
            henrik_stats = database_manager.get_henrik_storage_stats()
            db_stats = database_manager.get_database_stats()
            
            return {
                'stored_matches': henrik_stats.get('stored_matches', 0),
                'stored_player_stats': henrik_stats.get('stored_player_stats', 0),
                'stored_accounts': henrik_stats.get('stored_accounts', 0),
                'matches_size_mb': henrik_stats.get('matches_size_mb', 0),
                'player_stats_size_mb': henrik_stats.get('player_stats_size_mb', 0),
                'accounts_size_mb': henrik_stats.get('accounts_size_mb', 0),
                'total_size_mb': sum([
                    henrik_stats.get('matches_size_mb', 0),
                    henrik_stats.get('player_stats_size_mb', 0),
                    henrik_stats.get('accounts_size_mb', 0)
                ])
            }
        except Exception as e:
            logging.error(f"Error getting storage stats: {e}")
            return {
                'stored_matches': 0, 'stored_player_stats': 0, 'stored_accounts': 0,
                'matches_size_mb': 0, 'player_stats_size_mb': 0, 'accounts_size_mb': 0,
                'total_size_mb': 0
            }

# Global Valorant client instance
_valorant_client_instance: Optional[ValorantClient] = None

def get_valorant_client() -> ValorantClient:
    """Get the global Valorant client instance."""
    global _valorant_client_instance
    if _valorant_client_instance is None:
        _valorant_client_instance = ValorantClient()
    return _valorant_client_instance

async def close_valorant_client() -> None:
    """Close the global Valorant client session."""
    global _valorant_client_instance
    if _valorant_client_instance is not None:
        await _valorant_client_instance.close()
        _valorant_client_instance = None

# Maintain backward compatibility
valorant_client = get_valorant_client()