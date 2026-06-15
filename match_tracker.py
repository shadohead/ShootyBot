import asyncio
import logging
import discord
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from valorant_client import valorant_client, get_player_rank, rank_emoji
import random
from utils import log_error, format_time_ago, parse_henrik_timestamp
from context_manager import context_manager
from database import database_manager
from match_stats_display import (
    build_round_flow,
    player_display_stats,
    recap_view,
)

class MatchTracker:
    """Tracks Discord members' Valorant matches by polling for newly completed games in active shooty stacks"""
    
    # Configuration constants
    CHECK_INTERVAL_SECONDS = 60  # 1 minute
    MATCH_CUTOFF_HOURS = 2
    MIN_DISCORD_MEMBERS = 2
    LEG_SHOT_THRESHOLD_PERCENT = 15
    HEADSHOT_THRESHOLD_PERCENT = 30
    HIGH_DAMAGE_THRESHOLD = 3000
    STACK_INACTIVITY_HOURS = 1.5  # Auto-end stacks after 1.5 hours of no games
    
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        # State is now persisted to database - these are kept as memory caches for performance
        self.tracked_members: Dict[int, Dict[str, Any]] = {}  # {member_id: {'last_checked': datetime, 'last_match_id': str}}
        self.recent_matches: Dict[int, Dict[str, Dict[str, Any]]] = {}   # {server_id: {match_id: {'timestamp': datetime, 'members': []}}}
        self.stack_last_activity: Dict[int, datetime] = {}  # {channel_id: last_match_timestamp}
        self.stack_has_played: Dict[int, bool] = {}  # {channel_id: has_had_games}
        self.check_interval: int = self.CHECK_INTERVAL_SECONDS
        self.running: bool = False
        self._state_loaded: bool = False
        
    async def start_tracking(self) -> None:
        """Start the background match tracking task"""
        if self.running:
            return
        
        # Load state from database on startup
        if not self._state_loaded:
            await self._load_state_from_database()
            self._state_loaded = True
        
        self.running = True
        logging.info("Starting match tracker with 1-minute polling for active shooty stacks...")
        
        while self.running:
            try:
                await self._check_all_servers()
                await self._check_inactive_stacks()
                # Periodically save state to database
                await self._save_state_to_database()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                log_error("in match tracker", e)
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    def stop_tracking(self) -> None:
        """Stop the background match tracking"""
        self.running = False
        # Save final state to database before stopping
        asyncio.create_task(self._save_state_to_database())
        logging.info("Stopped match tracker")
    
    async def _check_all_servers(self) -> None:
        """Check all servers for recently finished matches"""
        for guild in self.bot.guilds:
            try:
                await self._check_server_matches(guild)
            except Exception as e:
                log_error(f"checking server {guild.id}", e)
    
    async def _check_server_matches(self, guild: discord.Guild) -> None:
        """Check a specific server for finished matches by polling members in active shooty stacks"""
        current_time = datetime.now(timezone.utc)
        members_to_check = []
        
        # Find channels with active shooty sessions in this guild
        for channel in guild.text_channels:
            context = context_manager.get_context(channel.id)
            
            # Get all users in the current stack (soloq + fullstack)
            all_stack_users = context.bot_soloq_user_set.union(context.bot_fullstack_user_set)
            
            # Skip if no one is in the stack
            if not all_stack_users:
                continue
            
            # Convert Discord user objects to member objects and check if they have linked accounts
            for user in all_stack_users:
                # user is a Discord Member object
                if user.bot:
                    continue
                    
                accounts = valorant_client.get_all_linked_accounts(user.id)
                if not accounts:
                    continue
                
                # Update last checked time
                if user.id not in self.tracked_members:
                    self.tracked_members[user.id] = {
                        'last_checked': current_time,
                        'last_match_id': None
                    }
                else:
                    self.tracked_members[user.id]['last_checked'] = current_time
                
                # Add to check list if not already added
                if user not in members_to_check:
                    members_to_check.append(user)
        
        if members_to_check:
            logging.debug(f"Checking {len(members_to_check)} stack members for new matches in {guild.name}")
            await self._check_recent_matches(guild, members_to_check)
        else:
            logging.debug(f"No active stack members with linked Valorant accounts in {guild.name}")
    
    async def _check_recent_matches(self, guild: discord.Guild, members: List[discord.Member]) -> None:
        """Check recent matches for specific members.

        Polls the lightweight competitive-updates endpoint (a few KB) to detect
        new matches; full match details (multi-MB) are fetched at most once per
        new match id and permanently cached in SQLite.
        """
        server_matches = self.recent_matches.setdefault(guild.id, {})
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.MATCH_CUTOFF_HOURS)

        for member in members:
            try:
                primary_account = valorant_client.get_linked_account(member.id)
                if not primary_account:
                    continue

                # Cheap poll: recent competitive match ids + timestamps only
                updates = await valorant_client.get_recent_competitive_updates(
                    primary_account['username'],
                    primary_account['tag'],
                    puuid=primary_account.get('puuid')
                )

                if not updates:
                    continue

                latest_update = updates[0]  # Most recent match
                latest_match_id = latest_update.get('match_id')

                if not latest_match_id:
                    continue

                # Check if this is a new match for this member
                last_known_match = self.tracked_members.get(member.id, {}).get('last_match_id')

                if last_known_match != latest_match_id:
                    # Update the last known match for this member
                    self.tracked_members[member.id]['last_match_id'] = latest_match_id

                    # Skip if we've already processed this match globally
                    if latest_match_id in server_matches:
                        continue

                    # Skip old matches (before paying for the full details)
                    match_time = latest_update.get('started_at')
                    if not match_time or match_time < cutoff_time:
                        continue

                    # New recent match: fetch full details once (SQLite-cached)
                    latest_match = await valorant_client.get_match_details(latest_match_id)
                    if not latest_match:
                        continue

                    # Skip if match is not completed
                    if not latest_match.get('metadata', {}).get('game_length', 0):
                        continue

                    # Find all Discord members in this match
                    discord_members_in_match = await self._find_discord_members_in_match(guild, latest_match)

                    # Persist per-match stat rows for every linked player in the
                    # match, so stats commands have warm data without API calls
                    valorant_client.record_match_stats_for_players(
                        latest_match,
                        [dm['account'].get('puuid') for dm in discord_members_in_match]
                    )

                    # Only process if minimum Discord members were in the match
                    if len(discord_members_in_match) >= self.MIN_DISCORD_MEMBERS:
                        server_matches[latest_match_id] = {
                            'timestamp': datetime.now(timezone.utc),
                            'members': discord_members_in_match,
                            'match_data': latest_match
                        }

                        # How many games this stack has run back-to-back today
                        # (recent_matches only retains the last MATCH_CUTOFF_HOURS)
                        game_number = len(server_matches)

                        # Send match results to appropriate channel
                        await self._send_match_results(
                            guild, latest_match, discord_members_in_match, game_number)

                        # Update stack activity tracking
                        await self._update_stack_activity(guild, discord_members_in_match, latest_match)

            except Exception as e:
                log_error(f"checking matches for {member.display_name}", e)

        # Clean up old matches
        for match_id in list(server_matches.keys()):
            if server_matches[match_id]['timestamp'] < cutoff_time:
                del server_matches[match_id]
    
    async def _find_discord_members_in_match(self, guild: discord.Guild, match: dict) -> List[Dict]:
        """Find which Discord members were in a specific match"""
        discord_members = []
        all_players = match.get('players', {}).get('all_players', [])
        
        for member in guild.members:
            if member.bot:
                continue
                
            accounts = valorant_client.get_all_linked_accounts(member.id)
            for account in accounts:
                puuid = account.get('puuid', '')
                
                # Find this player in the match
                for player in all_players:
                    if player.get('puuid') == puuid:
                        discord_members.append({
                            'member': member,
                            'account': account,
                            'player_data': player
                        })
                        break
        
        return discord_members
    
    async def _send_match_results(self, guild: discord.Guild, match: Dict[str, Any], discord_members: List[Dict[str, Any]], game_number: int = 1) -> None:
        """Send match results to relevant stack channels"""

        target_channels = []

        # Determine which channels have these members queued
        for channel in guild.text_channels:
            context = context_manager.get_context(channel.id)
            all_stack_users = context.bot_soloq_user_set.union(context.bot_fullstack_user_set)
            if not all_stack_users:
                continue

            participants = [dm for dm in discord_members if dm['member'] in all_stack_users]
            if len(participants) >= self.MIN_DISCORD_MEMBERS:
                target_channels.append(channel)

        # Fallback to a general channel if none matched
        if not target_channels:
            for ch in guild.text_channels:
                if ch.name.lower() in ['general', 'valorant', 'gaming', 'shooty']:
                    target_channels.append(ch)
                    break

        if not target_channels and guild.text_channels:
            target_channels.append(guild.text_channels[0])

        if not target_channels:
            return

        try:
            embed = await self._create_match_embed(match, discord_members, game_number)
            match_id = match.get('metadata', {}).get('matchid')
            for ch in target_channels:
                # A fresh view per send avoids reusing one View across messages.
                await ch.send(embed=embed, view=recap_view(match_id))

        except Exception as e:
            log_error("sending match results", e)
    
    async def _create_match_embed(self, match: dict, discord_members: List[Dict], game_number: int = 1) -> discord.Embed:
        """Create a fun match results embed"""
        metadata = match.get('metadata', {})
        map_name = metadata.get('map', 'Unknown')
        rounds_played = metadata.get('rounds_played', 0)
        game_length = metadata.get('game_length', 0)
        game_start = metadata.get('game_start', '')
        match_id = metadata.get('matchid', '')
        
        # Calculate match duration
        if game_length:
            # game_length is already in seconds
            duration_seconds = int(game_length)
            duration_minutes = duration_seconds // 60
            duration_seconds_remainder = duration_seconds % 60
            
            if duration_minutes >= 60:
                hours = duration_minutes // 60
                minutes = duration_minutes % 60
                duration_str = f"{hours}h {minutes}m"
            else:
                duration_str = f"{duration_minutes}m {duration_seconds_remainder}s"
        else:
            duration_str = "Unknown"
        
        # Parse match start time
        match_timestamp = parse_henrik_timestamp(game_start)
        if match_timestamp is None:
            match_timestamp = datetime.now(timezone.utc)
        
        # Calculate relative time
        if match_timestamp:
            time_ago_str = format_time_ago(match_timestamp)
        else:
            time_ago_str = "Recently"
        
        # Create tracker.gg link if match ID is available
        tracker_link = ""
        if match_id:
            tracker_link = f"[📊 View on Tracker.gg](https://tracker.gg/valorant/match/{match_id})"

        # Calculate fun stats
        fun_stats = self._calculate_fun_match_stats(match, discord_members)

        # Figure out which side the stack played on (all squad members are
        # together) so the whole recap can be framed from their perspective.
        # This drives the headline, the embed color, and the closing comment -
        # avoiding the old layout that repeated the score and win/loss state in
        # three different places.
        teams = match.get('teams', {})
        team_color = None
        for dm in discord_members:
            tc = (dm.get('player_data') or {}).get('team', '').lower()
            if tc:
                team_color = tc
                break

        team_won = False
        my_rounds = 0
        opponent_rounds = 0
        have_result = bool(teams and team_color in teams)
        if have_result:
            team_won = teams[team_color].get('has_won', False)
            my_rounds = teams[team_color].get('rounds_won', 0)
            for color, data in teams.items():
                if color != team_color:
                    opponent_rounds = data.get('rounds_won', 0)
                    break

        # Single, prominent result line: outcome + scoreline shown exactly once.
        meta_line = f"**{map_name}** • {rounds_played} rounds • {duration_str} • {time_ago_str}"
        description_parts = []
        if have_result:
            outcome = "🏆 **VICTORY**" if team_won else "💀 **DEFEAT**"
            description_parts.append(f"{outcome}　`{my_rounds} – {opponent_rounds}`")
            embed_color = 0x3ba55d if team_won else 0xed4245
        else:
            embed_color = 0xff4655
        description_parts.append(meta_line)
        if tracker_link:
            description_parts.append(tracker_link)

        embed = discord.Embed(
            title="🎯 Match Results",
            description="\n".join(description_parts),
            color=embed_color,
            timestamp=match_timestamp
        )

        # If we couldn't tie the squad to a team, fall back to a neutral
        # scoreboard so the result is still visible.
        if not have_result and teams:
            team_info = []
            for color, team_data in teams.items():
                rounds_won = team_data.get('rounds_won', 0)
                marker = "🏆" if team_data.get('has_won', False) else "▫️"
                team_info.append(f"{marker} {color.title()} — {rounds_won}")
            embed.add_field(
                name="🏆 Match Result",
                value="\n".join(team_info),
                inline=False
            )

        # Round-by-round win/loss flow, shown right under the result so the
        # game's story reads top-to-bottom (green = round won, red = lost).
        if have_result:
            flow = build_round_flow(match, team_color)
            if flow:
                embed.add_field(
                    name="🔄 Round Flow",
                    value=flow,
                    inline=False
                )

        # Add Discord members who played. Each line carries K/D/A plus the two
        # most useful per-round numbers (ACS, ADR); the top ACS in the squad
        # gets a 👑, and a one-line summary rolls the squad up.
        entries = []  # (display_name, stats, rank_str, rankup_str)
        tracked_puuids = set()

        # Members who crossed up a full tier this game (shown inline)
        ranked_up_ids = await self._get_ranked_up_member_ids(discord_members)

        for dm in discord_members:
            member = dm['member']
            player_data = dm['player_data']
            puuid = dm.get('account', {}).get('puuid') or player_data.get('puuid')
            if puuid:
                tracked_puuids.add(puuid)

            pstats = player_display_stats(match, player_data, puuid)
            rank = get_player_rank(player_data)
            rank_str = f" • {rank_emoji(rank)} {rank}" if rank else ""
            rankup_str = " ⬆️ **Rank Up!**" if member.id in ranked_up_ids else ""
            entries.append((member.display_name, pstats, rank_str, rankup_str))

        # Add untracked teammates (players on the same team who aren't linked via shootylink)
        all_players = match.get('players', {}).get('all_players', [])
        untracked_count = 0
        if team_color:
            for player in all_players:
                if player.get('team', '').lower() != team_color:
                    continue
                if player.get('puuid') in tracked_puuids:
                    continue
                name = player.get('name', 'Unknown')
                tag = player.get('tag', '')
                display_name = f"{name}#{tag}" if tag else name
                pstats = player_display_stats(match, player, player.get('puuid'))
                rank = get_player_rank(player)
                rank_str = f" • {rank_emoji(rank)} {rank}" if rank else ""
                entries.append((display_name, pstats, rank_str, ""))
                untracked_count += 1

        top_acs = max((s['acs'] for _, s, _, _ in entries), default=0)
        member_list = []
        for display_name, s, rank_str, rankup_str in entries:
            crown = "👑 " if top_acs and s['acs'] == top_acs else ""
            kda = f"{s['kills']}/{s['deaths']}/{s['assists']}"
            extra = f" · {s['acs']} ACS · {s['adr']} ADR" if (s['acs'] or s['adr']) else ""
            member_list.append(f"• {crown}**{display_name}**: {kda}{extra}{rank_str}{rankup_str}")

        # One-line squad roll-up above the per-player lines.
        if entries:
            tot_k = sum(s['kills'] for _, s, _, _ in entries)
            tot_d = sum(s['deaths'] for _, s, _, _ in entries)
            tot_a = sum(s['assists'] for _, s, _, _ in entries)
            avg_acs = round(sum(s['acs'] for _, s, _, _ in entries) / len(entries))
            tot_fk = sum(s['fk'] for _, s, _, _ in entries)
            tot_fd = sum(s['fd'] for _, s, _, _ in entries)
            summary = f"**Squad:** {tot_k}/{tot_d}/{tot_a}"
            if avg_acs:
                summary += f" · {avg_acs} avg ACS"
            if tot_fk or tot_fd:
                summary += f" · {tot_fk} FK / {tot_fd} FD"
            member_list.insert(0, summary)

        squad_size = len(discord_members) + untracked_count

        embed.add_field(
            name=f"👥 Squad ({squad_size})",
            value="\n".join(member_list) if member_list else "No squad members found",
            inline=False
        )

        # Add enhanced fun highlights
        if fun_stats['highlights']:
            # Limit to top 6 highlights to avoid embed limits
            top_highlights = fun_stats['highlights'][:6]
            highlights_text = "\n".join([f"{highlight}" for highlight in top_highlights])
            embed.add_field(
                name="🎆 Match Highlights",
                value=highlights_text,
                inline=False
            )

        # Add a post-match comment that reacts to the result, the margin, and
        # how many games deep the stack is into the session. The scoreline is
        # already in the headline, so the comment is pure flavor.
        if not team_won:
            name, value = self._build_loss_comment(my_rounds, opponent_rounds, game_number)
        else:
            name, value = self._build_win_comment(my_rounds, opponent_rounds, game_number)

        if value:
            embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text="Use /shootylink to show up in post-match recaps!")
        return embed

    @staticmethod
    def _build_loss_comment(my_rounds: int, opponent_rounds: int, game_number: int) -> tuple:
        """Build the post-match comment shown after a loss.

        Reacts to the margin (heartbreaker vs. blowout) and how deep into the
        session the stack is: game 1 is a warm-up, but after a few back-to-back
        games that excuse runs out and we just have to keep running it back.
        """
        margin = opponent_rounds - my_rounds
        lines = []

        if margin <= 2:
            lines.append(random.choice([
                "So close 😤 came right down to the wire.",
                "Coin-flip game, could've gone either way.",
                "One round away. We run it back.",
                "Heartbreaker. That one stings.",
            ]))
        elif margin >= 8:
            lines.append(random.choice([
                "Yeah... we don't talk about that one 💀",
                "Got stomped. Shake it off.",
                "That was a beatdown. Reset and refocus.",
                "Wrong server. Requeue. 🫠",
            ]))
        else:
            lines.append(random.choice([
                "Tough loss. On to the next one.",
                "Not our round. Let's run it back.",
                "We move. 🫡",
                "Lost the match, not the war.",
            ]))

        if game_number <= 1:
            lines.append(random.choice([
                "Warm up game 🔥",
                "Just shaking off the rust 🔥",
                "Doesn't count, we were warming up 😤",
            ]))
        elif game_number >= 3:
            lines.append(random.choice([
                f"{game_number} games deep — we are NOT ending on that one 😤",
                f"That's {game_number} in a row, one more to end on a W? 🙏",
                f"{game_number} games in and we can't end on that one 😅",
            ]))
        else:
            lines.append(random.choice([
                "Can't end it on that one 😅",
                "Run it back, we get the next one.",
            ]))

        return "😅 Tough Loss", "\n".join(lines)

    @staticmethod
    def _build_win_comment(my_rounds: int, opponent_rounds: int, game_number: int) -> tuple:
        """Build the post-match comment shown after a win, nudging the stack to
        end on a high note once they've played a few games."""
        margin = my_rounds - opponent_rounds
        lines = []

        if margin <= 2:
            lines.append(random.choice([
                "Clutched it out 😮‍💨 nail-biter.",
                "Down to the wire, but it's a dub 🏆",
                "We do not miss when it's close 😤",
            ]))
        elif margin >= 8:
            lines.append(random.choice([
                "Absolute domination 🧹",
                "Easy work 😎",
                "Sent them to the lobby 💀",
            ]))
        else:
            lines.append(random.choice([
                "GG — that's a dub 🏆",
                "Clean win 💪",
                "Business as usual 😎",
            ]))

        if game_number >= 3:
            lines.append(random.choice([
                f"{game_number} games in — end it on that one? 😏",
                "End on a high note? 🎉",
                "Perfect note to log off on 😌",
            ]))

        return "🏆 GG", "\n".join(lines)

    async def _get_ranked_up_member_ids(self, discord_members: List[Dict]) -> set:
        """Return the ids of squad members who crossed up a full tier this game.

        A promotion is detected when the last game's RR gain pushed the player
        past a tier boundary: their pre-game RR-in-tier
        (``ranking_in_tier - mmr_change``) was below zero.

        Best-effort: silently skips members whose MMR can't be fetched (private
        profile, API down, no key), so the recap still renders without them.
        """
        ranked_up = set()
        for dm in discord_members:
            account = dm.get('account', {}) or {}
            username = account.get('username')
            tag = account.get('tag')
            if not username or not tag:
                continue

            try:
                mmr = await valorant_client.get_mmr(username, tag, puuid=account.get('puuid'))
            except Exception as e:
                log_error(f"fetching rank for {username}#{tag}", e)
                mmr = None

            if not mmr:
                continue

            rr = mmr.get('rr')
            change = mmr.get('rr_change')
            # Genuine promotion: a positive RR change whose pre-game RR-in-tier
            # was negative means a tier boundary was crossed this game.
            if rr is None or change is None or change <= 0:
                continue
            if (rr - change) >= 0:
                continue

            ranked_up.add(dm['member'].id)

        return ranked_up

    async def build_session_recap(self, guild: discord.Guild, participants: List[discord.Member], session) -> discord.Embed:
        """Build an end-of-session recap embed.

        Ties the session (``/st`` -> ``/stend``) to the competitive matches the
        participants actually played during the session window. Always returns a
        usable embed, degrading gracefully when no Valorant data is available.

        Args:
            guild: The guild the session ran in.
            participants: Discord members who were in the stack at end time.
            session: The ended ``SessionData`` (provides the time window).
        """
        # Resolve the session time window
        start_dt = parse_henrik_timestamp(getattr(session, 'start_time', None))
        end_dt = parse_henrik_timestamp(getattr(session, 'end_time', None)) or datetime.now(timezone.utc)
        # Grace before start to catch a match already in progress when /st ran
        window_start = (start_dt - timedelta(minutes=10)) if start_dt else None
        window_end = end_dt + timedelta(minutes=5)

        # Collect matches played in-window across all participant accounts.
        # Discovery uses the lightweight competitive-updates endpoint (few KB);
        # full details come from the permanent SQLite cache - the tracker has
        # usually already stored them while the session was running.
        matches_by_id: Dict[str, Dict[str, Any]] = {}
        member_puuids: Dict[str, discord.Member] = {}

        for member in participants:
            if getattr(member, 'bot', False):
                continue
            accounts = valorant_client.get_all_linked_accounts(member.id)
            for account in accounts:
                puuid = account.get('puuid')
                if puuid:
                    member_puuids[puuid] = member
                try:
                    updates = await valorant_client.get_recent_competitive_updates(
                        account['username'], account['tag'], puuid=puuid
                    )
                except Exception as e:
                    log_error(f"fetching session matches for {account.get('username')}", e)
                    updates = None

                for update in updates or []:
                    mid = update.get('match_id')
                    if not mid or mid in matches_by_id:
                        continue
                    started = update.get('started_at')
                    if started is None:
                        continue
                    if window_start and started < window_start:
                        continue
                    if started > window_end:
                        continue
                    match = await valorant_client.get_match_details(mid)
                    if match:
                        matches_by_id[mid] = match

        # Warm the per-match stat rows for everyone we fetched details for
        for match in matches_by_id.values():
            valorant_client.record_match_stats_for_players(match, list(member_puuids.keys()))

        # Aggregate per-player stats and W/L across in-window matches
        player_totals: Dict[int, Dict[str, Any]] = {}
        wins = losses = 0
        for match in matches_by_id.values():
            all_players = match.get('players', {}).get('all_players', [])
            teams = match.get('teams', {})
            stack_team = None
            for player in all_players:
                if player.get('puuid') not in member_puuids:
                    continue
                member = member_puuids[player['puuid']]
                pstats = player.get('stats', {})
                totals = player_totals.setdefault(member.id, {
                    'member': member, 'kills': 0, 'deaths': 0, 'assists': 0, 'games': 0
                })
                totals['kills'] += pstats.get('kills', 0)
                totals['deaths'] += pstats.get('deaths', 0)
                totals['assists'] += pstats.get('assists', 0)
                totals['games'] += 1
                if stack_team is None:
                    stack_team = player.get('team', '').lower()
            if stack_team and stack_team in teams:
                if teams[stack_team].get('has_won', False):
                    wins += 1
                else:
                    losses += 1

        # Header
        games = len(matches_by_id)
        duration_min = getattr(session, 'duration_minutes', 0) or 0
        if duration_min >= 60:
            duration_str = f"{duration_min // 60}h {duration_min % 60}m"
        else:
            duration_str = f"{duration_min}m"

        if games == 0:
            color = 0x808080
        elif wins > losses:
            color = 0x00ff66
        elif losses > wins:
            color = 0xff4655
        else:
            color = 0xffaa00

        desc_parts = [f"🗓️ {len(participants)} player{'s' if len(participants) != 1 else ''}", f"⏱️ {duration_str}"]
        if games:
            desc_parts.append(f"🎮 {games} game{'s' if games != 1 else ''} · {wins}W-{losses}L")
        embed = discord.Embed(
            title="📊 Session Recap",
            description=" • ".join(desc_parts),
            color=color,
            timestamp=end_dt
        )

        if games == 0:
            embed.add_field(
                name="No tracked games this session",
                value=(
                    "No competitive matches were detected for the squad.\n"
                    "Use `/shootylink <username> <tag>` so your games show up in recaps!"
                ),
                inline=False
            )
            embed.set_footer(text="GG — see you next session!")
            return embed

        # Per-player session scoreboard, sorted by KDA, MVP crowned
        ranked = sorted(
            player_totals.values(),
            key=lambda t: (t['kills'] + t['assists']) / max(t['deaths'], 1),
            reverse=True
        )
        scoreboard = []
        for i, t in enumerate(ranked):
            kda = (t['kills'] + t['assists']) / max(t['deaths'], 1)
            crown = "👑 " if i == 0 and len(ranked) > 1 else ""
            scoreboard.append(
                f"{crown}**{t['member'].display_name}** — {t['kills']}/{t['deaths']}/{t['assists']} "
                f"({kda:.2f} KDA, {t['games']}G)"
            )
        embed.add_field(
            name="🏅 Squad Scoreboard",
            value="\n".join(scoreboard) or "No player data",
            inline=False
        )

        if len(ranked) > 1:
            embed.add_field(
                name="🌟 MVP of the Night",
                value=f"**{ranked[0]['member'].display_name}** carried the squad! 🔥",
                inline=False
            )

        # End-of-night ranks (best-effort)
        rank_lines = []
        for member in participants:
            account = valorant_client.get_linked_account(member.id)
            if not account:
                continue
            try:
                mmr = await valorant_client.get_mmr(account['username'], account['tag'],
                                                    puuid=account.get('puuid'))
            except Exception:
                mmr = None
            if mmr and mmr.get('tier'):
                rr = mmr.get('rr')
                rr_str = f" · {rr} RR" if rr is not None else ""
                rank_lines.append(f"• **{member.display_name}**: {mmr.get('emoji', '')} {mmr['tier']}{rr_str}")
        if rank_lines:
            embed.add_field(name="📈 Where You Landed", value="\n".join(rank_lines), inline=False)

        # Closing flavor
        if wins > losses:
            flavor = "🔥 Winning night — GG WP!"
        elif losses > wins:
            flavor = "😅 Rough night. Run it back next time! 💪"
        else:
            flavor = "⚖️ Even night — the grind continues."
        embed.set_footer(text=flavor)
        return embed

    def _calculate_fun_match_stats(self, match_data: dict, discord_members: List[Dict]) -> Dict:
        """Compute every candidate highlight for the match, score each by how
        interesting it is, then pick a varied set of the best ones.

        Every stat we can derive (scoreboard, round analysis, clutches, spike
        plays, economy, behavior, match flow) becomes a scored candidate;
        _select_highlights decides post-game which ones are actually worth
        showing instead of always leading with kills/damage.
        """
        stats = {
            'highlights': [],
            'top_performers': {},
            'funny_stats': {}
        }

        if not discord_members:
            return stats

        candidates: List[Dict[str, Any]] = []
        player_stats, mk_counts = self._collect_player_stats(match_data, discord_members)

        if len(player_stats) >= 2:
            self._add_scoreboard_candidates(candidates, player_stats, mk_counts)
            self._add_team_fact_candidates(candidates, player_stats, match_data)

        self._add_advanced_candidates(candidates, match_data, discord_members)
        self._add_match_flow_candidates(candidates, match_data, discord_members)

        stats['highlights'] = self._select_highlights(candidates)
        return stats

    @staticmethod
    def _add_candidate(candidates: List[Dict[str, Any]], score: float, category: str,
                       text: str, member_id: Optional[int] = None) -> None:
        candidates.append({'score': score, 'category': category,
                           'text': text, 'member_id': member_id})

    @staticmethod
    def _select_highlights(candidates: List[Dict[str, Any]], max_per_member: int = 2) -> List[str]:
        """Pick the most interesting highlights with some variety: highest
        score first, one highlight per category, and at most max_per_member
        highlights about any single squad member (team-wide ones are exempt)."""
        selected = []
        used_categories = set()
        member_counts: Dict[int, int] = {}
        for cand in sorted(candidates, key=lambda c: c['score'], reverse=True):
            if cand['category'] in used_categories:
                continue
            member_id = cand.get('member_id')
            if member_id is not None and member_counts.get(member_id, 0) >= max_per_member:
                continue
            used_categories.add(cand['category'])
            if member_id is not None:
                member_counts[member_id] = member_counts.get(member_id, 0) + 1
            selected.append(cand['text'])
        return selected

    @staticmethod
    def _collect_player_stats(match_data: dict, discord_members: List[Dict]):
        """Flatten scoreboard stats for each tracked member and count their
        multikill rounds from round data."""
        player_stats = []
        puuid_to_member = {}
        # ACS is the per-round average of combat score, not the raw match total.
        rounds_played = match_data.get('metadata', {}).get('rounds_played', 0) \
            or len(match_data.get('rounds', []))
        for dm in discord_members:
            member = dm['member']
            player_data = dm['player_data']
            pstats = player_data.get('stats', {})
            puuid = dm.get('account', {}).get('puuid') or player_data.get('puuid')

            puuid_to_member[puuid] = member

            score = pstats.get('score', 0)
            acs = round(score / rounds_played) if rounds_played else score
            player_stats.append({
                'member': member,
                'puuid': puuid,
                'kills': pstats.get('kills', 0),
                'deaths': pstats.get('deaths', 0),
                'assists': pstats.get('assists', 0),
                'headshots': pstats.get('headshots', 0),
                'bodyshots': pstats.get('bodyshots', 0),
                'legshots': pstats.get('legshots', 0),
                'score': score,
                'acs': acs,
                'damage_made': player_data.get('damage_made', 0),
                'damage_received': player_data.get('damage_received', 0),
                'agent': player_data.get('character', 'Unknown')
            })

        mk_counts = {puuid: {'2k': 0, '3k': 0, '4k': 0, '5k': 0} for puuid in puuid_to_member}
        for round_data in match_data.get('rounds', []):
            for ps in round_data.get('player_stats', []):
                puuid = ps.get('player_puuid')
                if puuid in mk_counts:
                    kills_in_round = len(ps.get('kill_events', []))
                    if kills_in_round >= 5:
                        mk_counts[puuid]['5k'] += 1
                    elif kills_in_round >= 4:
                        mk_counts[puuid]['4k'] += 1
                    elif kills_in_round >= 3:
                        mk_counts[puuid]['3k'] += 1
                    elif kills_in_round >= 2:
                        mk_counts[puuid]['2k'] += 1

        return player_stats, mk_counts

    def _add_scoreboard_candidates(self, candidates: List[Dict[str, Any]],
                                   player_stats: List[Dict], mk_counts: Dict) -> None:
        """Scored highlight candidates from basic scoreboard stats."""
        add = self._add_candidate

        # Top Fragger with more flair
        top_fragger = max(player_stats, key=lambda x: x['kills'])
        if top_fragger['kills'] >= 25:
            add(candidates, 78, 'top_fragger',
                f"🔥🔥 **DEMON MODE**: {top_fragger['member'].display_name} ({top_fragger['kills']} kills) - GOING NUCLEAR!",
                top_fragger['member'].id)
        elif top_fragger['kills'] >= 20:
            add(candidates, 62, 'top_fragger',
                f"🔥 **Top Fragger**: {top_fragger['member'].display_name} ({top_fragger['kills']} kills) - ON FIRE!",
                top_fragger['member'].id)
        elif top_fragger['kills'] > 0:
            add(candidates, 40, 'top_fragger',
                f"🎯 **Top Fragger**: {top_fragger['member'].display_name} ({top_fragger['kills']} kills)",
                top_fragger['member'].id)

        # Most Damage with context
        top_damage = max(player_stats, key=lambda x: x['damage_made'])
        if top_damage['damage_made'] >= 4000:
            add(candidates, 64, 'damage',
                f"💥 **DAMAGE MONSTER**: {top_damage['member'].display_name} ({top_damage['damage_made']:,} damage) - ANNIHILATION!",
                top_damage['member'].id)
        elif top_damage['damage_made'] >= 3000:
            add(candidates, 50, 'damage',
                f"💥 **Damage Dealer**: {top_damage['member'].display_name} ({top_damage['damage_made']:,} damage)",
                top_damage['member'].id)
        elif top_damage['damage_made'] > 0:
            add(candidates, 35, 'damage',
                f"💪 **Damage Leader**: {top_damage['member'].display_name} ({top_damage['damage_made']:,} damage)",
                top_damage['member'].id)

        # Best KDA with performance tiers
        kda_players = [(p, (p['kills'] + p['assists']) / max(p['deaths'], 1)) for p in player_stats]
        best_kda = max(kda_players, key=lambda x: x[1])
        if best_kda[1] >= 3.0:
            add(candidates, 60, 'kda',
                f"👑 **KDA KING**: {best_kda[0]['member'].display_name} ({best_kda[1]:.2f} KDA) - UNTOUCHABLE!",
                best_kda[0]['member'].id)
        elif best_kda[1] >= 2.0:
            add(candidates, 48, 'kda',
                f"⭐ **KDA Master**: {best_kda[0]['member'].display_name} ({best_kda[1]:.2f} KDA)",
                best_kda[0]['member'].id)
        else:
            add(candidates, 35, 'kda',
                f"💪 **Best KDA**: {best_kda[0]['member'].display_name} ({best_kda[1]:.2f} KDA)",
                best_kda[0]['member'].id)

        total_shots = sum(p['headshots'] + p['bodyshots'] + p['legshots'] for p in player_stats)
        if total_shots > 0:
            # Most leg shots with humor
            leg_shot_king = max(player_stats, key=lambda x: x['legshots'])
            if leg_shot_king['legshots'] > 0:
                leg_percentage = (leg_shot_king['legshots'] / max(leg_shot_king['headshots'] + leg_shot_king['bodyshots'] + leg_shot_king['legshots'], 1)) * 100
                if leg_percentage > self.LEG_SHOT_THRESHOLD_PERCENT:
                    if leg_percentage > 25:
                        add(candidates, 66, 'legshots',
                            f"🦵 **LEG DESTROYER**: {leg_shot_king['member'].display_name} ({leg_shot_king['legshots']} leg shots, {leg_percentage:.1f}%) - Ankle Biter!",
                            leg_shot_king['member'].id)
                    else:
                        add(candidates, 52, 'legshots',
                            f"🦵 **Leg Shot Specialist**: {leg_shot_king['member'].display_name} ({leg_shot_king['legshots']} leg shots, {leg_percentage:.1f}%)",
                            leg_shot_king['member'].id)

            # Headshot accuracy
            headshot_ace = max(player_stats, key=lambda x: x['headshots'] / max(x['headshots'] + x['bodyshots'] + x['legshots'], 1))
            total_shots_player = headshot_ace['headshots'] + headshot_ace['bodyshots'] + headshot_ace['legshots']
            if total_shots_player > 20:  # Only if they took enough shots
                hs_percentage = (headshot_ace['headshots'] / total_shots_player) * 100
                if hs_percentage > 40:
                    add(candidates, 70, 'headshots',
                        f"🎯 **HEADSHOT DEMON**: {headshot_ace['member'].display_name} ({hs_percentage:.1f}% HS) - INSANE AIM!",
                        headshot_ace['member'].id)
                elif hs_percentage > self.HEADSHOT_THRESHOLD_PERCENT:
                    add(candidates, 56, 'headshots',
                        f"🎯 **Headshot Machine**: {headshot_ace['member'].display_name} ({hs_percentage:.1f}% HS accuracy)",
                        headshot_ace['member'].id)

            # Support player recognition
            assist_king = max(player_stats, key=lambda x: x['assists'])
            if assist_king['assists'] >= 10:
                add(candidates, 54, 'assists',
                    f"🤝 **SUPPORT HERO**: {assist_king['member'].display_name} ({assist_king['assists']} assists) - Team Player!",
                    assist_king['member'].id)
            elif assist_king['assists'] >= 7:
                add(candidates, 42, 'assists',
                    f"🤝 **Team Player**: {assist_king['member'].display_name} ({assist_king['assists']} assists)",
                    assist_king['member'].id)

            # Multi-kill highlights using round data
            for p in player_stats:
                counts = mk_counts.get(p['puuid'], {})
                if counts.get('5k', 0) > 0:
                    ace_count = counts['5k']
                    plural = 's' if ace_count > 1 else ''
                    add(candidates, 95, f"multikill:{p['member'].id}",
                        f"🔥 **ACE ALERT**: {p['member'].display_name} scored {ace_count} ACE{plural}!",
                        p['member'].id)
                elif counts.get('4k', 0) > 0:
                    fourk = counts['4k']
                    plural = 's' if fourk > 1 else ''
                    add(candidates, 80, f"multikill:{p['member'].id}",
                        f"⚡ **MULTIKILL MASTER**: {p['member'].display_name} landed {fourk} 4K{plural}!",
                        p['member'].id)
                elif counts.get('3k', 0) >= 2:
                    threek = counts['3k']
                    plural = 's' if threek > 1 else ''
                    add(candidates, 58, f"multikill:{p['member'].id}",
                        f"💥 {p['member'].display_name} racked up {threek} 3K{plural}!",
                        p['member'].id)

        # Damage tanking analysis
        tank_player = max(player_stats, key=lambda x: x['damage_received'])
        glass_cannon = None
        for p in player_stats:
            if p['damage_made'] > 3000 and p['damage_received'] > self.HIGH_DAMAGE_THRESHOLD:
                glass_cannon = p
                break

        if glass_cannon:
            add(candidates, 55, 'damage_tank',
                f"💎 **GLASS CANNON**: {glass_cannon['member'].display_name} ({glass_cannon['damage_made']:,}D dealt, {glass_cannon['damage_received']:,}D taken)",
                glass_cannon['member'].id)
        elif tank_player['damage_received'] > self.HIGH_DAMAGE_THRESHOLD:
            if tank_player['damage_received'] > 4000:
                add(candidates, 53, 'damage_tank',
                    f"🛡️ **HUMAN FORTRESS**: {tank_player['member'].display_name} ({tank_player['damage_received']:,} damage tanked) - UNMOVABLE!",
                    tank_player['member'].id)
            else:
                add(candidates, 44, 'damage_tank',
                    f"🛡️ **Human Shield**: {tank_player['member'].display_name} ({tank_player['damage_received']:,} damage taken)",
                    tank_player['member'].id)

        # Economic efficiency (low deaths with good damage)
        efficient_player = min(player_stats, key=lambda x: x['deaths'] / max(x['damage_made'], 1))
        if efficient_player['deaths'] <= 12 and efficient_player['damage_made'] >= 2500:
            efficiency = efficient_player['damage_made'] / max(efficient_player['deaths'], 1)
            add(candidates, 45, 'efficiency',
                f"💰 **ECONOMY MASTER**: {efficient_player['member'].display_name} ({efficiency:.0f} damage per death) - Efficient!",
                efficient_player['member'].id)

        # The Survivor (lowest deaths)
        survivor = min(player_stats, key=lambda x: x['deaths'])
        if survivor['deaths'] <= 8 and len(player_stats) >= 3:
            if survivor['deaths'] <= 5:
                add(candidates, 56, 'survivor',
                    f"🛡️ **IMMORTAL**: {survivor['member'].display_name} ({survivor['deaths']} deaths) - Untouchable!",
                    survivor['member'].id)
            else:
                add(candidates, 44, 'survivor',
                    f"💚 **Survivor**: {survivor['member'].display_name} ({survivor['deaths']} deaths) - Hard to kill!",
                    survivor['member'].id)

        # The Feeder (highest deaths with humor)
        feeder = max(player_stats, key=lambda x: x['deaths'])
        if feeder['deaths'] >= 20 and len(player_stats) >= 3:
            if feeder['deaths'] >= 25:
                add(candidates, 60, 'feeder',
                    f"💀 **SACRIFICE**: {feeder['member'].display_name} ({feeder['deaths']} deaths) - Taking one for the team!",
                    feeder['member'].id)
            else:
                add(candidates, 50, 'feeder',
                    f"😵 **Brave Soul**: {feeder['member'].display_name} ({feeder['deaths']} deaths) - No fear!",
                    feeder['member'].id)

        # Score Leader (highest average combat score per round)
        score_leader = max(player_stats, key=lambda x: x['acs'])
        if score_leader['acs'] >= 250:
            if score_leader['acs'] >= 350:
                add(candidates, 66, 'acs',
                    f"🌟 **MVP PERFORMANCE**: {score_leader['member'].display_name} ({score_leader['acs']} ACS) - LEGENDARY!",
                    score_leader['member'].id)
            else:
                add(candidates, 50, 'acs',
                    f"⭐ **Score Leader**: {score_leader['member'].display_name} ({score_leader['acs']} ACS)",
                    score_leader['member'].id)

        # Kill/Death ratio extremes
        kd_ratios = [(p, p['kills'] / max(p['deaths'], 1)) for p in player_stats]
        best_kd = max(kd_ratios, key=lambda x: x[1])
        if best_kd[1] >= 2.5 and best_kd[0]['kills'] >= 15:
            add(candidates, 58, 'kd',
                f"🔥 **K/D MONSTER**: {best_kd[0]['member'].display_name} ({best_kd[1]:.2f} K/D) - Unstoppable!",
                best_kd[0]['member'].id)

        # The Spray Master (most bodyshots)
        spray_master = max(player_stats, key=lambda x: x['bodyshots'])
        total_shots_spray = spray_master['headshots'] + spray_master['bodyshots'] + spray_master['legshots']
        if total_shots_spray > 30:
            body_percentage = (spray_master['bodyshots'] / total_shots_spray) * 100
            if body_percentage > 60:
                add(candidates, 40, 'spray',
                    f"🎯 **SPRAY CONTROL**: {spray_master['member'].display_name} ({body_percentage:.1f}% body shots) - Consistent aim!",
                    spray_master['member'].id)

        # Damage vs Score efficiency
        for p in player_stats:
            if p['damage_made'] > 0 and p['score'] > 0:
                damage_per_score = p['damage_made'] / p['score']
                if damage_per_score > 12:  # High damage per score point
                    add(candidates, 38, 'dmg_per_score',
                        f"💥 **DAMAGE EFFICIENT**: {p['member'].display_name} (High damage-to-score ratio) - Pure DPS!",
                        p['member'].id)
                    break

        # The Clutch Factor (low assists but high kills - potential clutch player)
        for p in player_stats:
            if p['kills'] >= 15 and p['assists'] <= 5 and p['kills'] > p['assists'] * 2:
                add(candidates, 46, 'lone_wolf',
                    f"🎭 **LONE WOLF**: {p['member'].display_name} ({p['kills']} kills, {p['assists']} assists) - Solo carry!",
                    p['member'].id)
                break

        # Role-based callouts
        duelist_agents = ['Jett', 'Reyna', 'Phoenix', 'Raze', 'Yoru', 'Neon', 'Iso']
        duelists = [p for p in player_stats if p['agent'] in duelist_agents]
        if duelists:
            top_duelist = max(duelists, key=lambda x: x['kills'])
            if top_duelist['kills'] >= 20:
                add(candidates, 44, 'role_duelist',
                    f"⚔️ **DUELIST DIFF**: {top_duelist['member'].display_name} ({top_duelist['agent']}) - Entry fragging king!",
                    top_duelist['member'].id)

        controller_agents = ['Brimstone', 'Omen', 'Viper', 'Astra', 'Harbor', 'Clove']
        controllers = [p for p in player_stats if p['agent'] in controller_agents]
        if controllers:
            top_controller = max(controllers, key=lambda x: x['assists'])
            if top_controller['assists'] >= 12:
                add(candidates, 44, 'role_controller',
                    f"🧠 **BIG BRAIN**: {top_controller['member'].display_name} ({top_controller['agent']}) - Tactical genius!",
                    top_controller['member'].id)

        sentinel_agents = ['Killjoy', 'Cypher', 'Sage', 'Chamber', 'Deadlock', 'Vyse']
        sentinels = [p for p in player_stats if p['agent'] in sentinel_agents]
        if sentinels:
            top_sentinel = max(sentinels, key=lambda x: x['acs'])
            if top_sentinel['acs'] >= 250:
                add(candidates, 42, 'role_sentinel',
                    f"🔒 **SITE ANCHOR**: {top_sentinel['member'].display_name} ({top_sentinel['agent']}) - Holding it down!",
                    top_sentinel['member'].id)

        # The Balanced Player (good at everything)
        for p in player_stats:
            if (p['kills'] >= 15 and p['assists'] >= 8 and p['deaths'] <= 15 and
                    p['damage_made'] >= 2500):
                add(candidates, 47, 'complete',
                    f"⚖️ **COMPLETE PLAYER**: {p['member'].display_name} - Excels in all areas!",
                    p['member'].id)
                break

        # The Damage Dealer with Low Impact (high damage, low kills)
        for p in player_stats:
            if p['damage_made'] >= 3000 and p['kills'] <= 12:
                add(candidates, 40, 'dmg_low_kills',
                    f"💢 **DAMAGE DEALER**: {p['member'].display_name} ({p['damage_made']:,} damage, {p['kills']} kills) - Setting up teammates!",
                    p['member'].id)
                break

        # The Finisher (low damage but high kills - good at finishing)
        for p in player_stats:
            if p['kills'] >= 18 and p['damage_made'] <= 2500:
                add(candidates, 39, 'finisher',
                    f"🎯 **THE FINISHER**: {p['member'].display_name} - Efficient eliminations!",
                    p['member'].id)
                break

    def _add_team_fact_candidates(self, candidates: List[Dict[str, Any]],
                                  player_stats: List[Dict], match_data: dict) -> None:
        """Low-priority team-wide fun facts; two are sampled in as filler when
        nothing more interesting claims the slots."""
        total_team_damage = sum(p['damage_made'] for p in player_stats)
        total_team_kills = sum(p['kills'] for p in player_stats)
        total_team_deaths = sum(p['deaths'] for p in player_stats)
        total_team_assists = sum(p['assists'] for p in player_stats)
        total_team_headshots = sum(p['headshots'] for p in player_stats)
        total_team_score = sum(p['score'] for p in player_stats)
        total_shots = sum(p['headshots'] + p['bodyshots'] + p['legshots'] for p in player_stats)

        fun_facts = [
            f"💥 **Team Devastation**: {total_team_damage:,} total damage dealt!",
            f"⚔️ **Combined Scoreline**: {total_team_kills}/{total_team_deaths} K/D",
            f"🦸 **Agent Squad**: {', '.join(set(p['agent'] for p in player_stats))}"
        ]

        team_kda = (total_team_kills + total_team_assists) / max(total_team_deaths, 1)
        if team_kda >= 2.0:
            fun_facts.append(f"👑 **Team KDA**: {team_kda:.2f} - Dominant performance!")
        elif team_kda >= 1.5:
            fun_facts.append(f"💪 **Team KDA**: {team_kda:.2f} - Solid teamwork!")
        else:
            fun_facts.append(f"⚔️ **Team KDA**: {team_kda:.2f} - Hard fought!")

        if total_shots > 0:
            team_hs_rate = (total_team_headshots / total_shots) * 100
            if team_hs_rate >= 25:
                team_accuracy_type = "🎯 **LASER PRECISION**"
            elif team_hs_rate >= 20:
                team_accuracy_type = "🔥 **Sharp Shooting**"
            elif team_hs_rate >= 15:
                team_accuracy_type = "💪 **Decent Aim**"
            else:
                team_accuracy_type = "🎲 **Spray & Pray**"
            fun_facts.append(f"{team_accuracy_type}: {team_hs_rate:.1f}% headshot rate")

        avg_damage = total_team_damage / len(player_stats)
        if avg_damage >= 3500:
            fun_facts.append("💀 **DAMAGE GODS**: Everyone hitting hard!")
        elif avg_damage >= 2500:
            fun_facts.append("💥 **Balanced Attack**: Even damage spread!")

        rounds_played = match_data.get('metadata', {}).get('rounds_played', 0) \
            or len(match_data.get('rounds', []))
        avg_acs = (total_team_score / len(player_stats) / rounds_played) if rounds_played else 0
        if avg_acs >= 250:
            fun_facts.append("🌟 **ALL-STAR LINEUP**: High scoring across the board!")
        elif avg_acs >= 200:
            fun_facts.append("⭐ **Solid Squad**: Consistent performance!")

        kill_spread = max(p['kills'] for p in player_stats) - min(p['kills'] for p in player_stats)
        if kill_spread <= 5:
            fun_facts.append("🤝 **TEAM EFFORT**: Kills spread evenly!")
        elif kill_spread >= 15:
            fun_facts.append("🎭 **CARRY MODE**: Someone's doing the heavy lifting!")

        total_team_damage_taken = sum(p['damage_received'] for p in player_stats)
        if total_team_damage_taken > 20000:
            fun_facts.append("🛡️ **BULLET SPONGES**: Tank squad activated!")

        if total_team_damage > 15000:
            fun_facts.append("🔥 **INTENSITY**: OFF THE CHARTS!")
        elif total_team_damage > 10000:
            fun_facts.append("⚡ **INTENSITY**: High-octane match!")

        rounds_played = match_data.get('metadata', {}).get('rounds_played', 0)
        if rounds_played > 0:
            avg_kills_per_round = total_team_kills / rounds_played
            if avg_kills_per_round >= 3.0:
                fun_facts.append(f"🔥 **ROUND DOMINATION**: {avg_kills_per_round:.1f} kills/round!")
            elif avg_kills_per_round >= 2.0:
                fun_facts.append(f"💪 **STEADY PRESSURE**: {avg_kills_per_round:.1f} kills/round")

        if total_team_deaths <= 60:
            fun_facts.append("💰 **ECONOMY KINGS**: Minimal losses!")
        elif total_team_deaths >= 100:
            fun_facts.append("💸 **HIGH RISK, HIGH REWARD**: Going for broke!")

        for idx, fact in enumerate(random.sample(fun_facts, min(2, len(fun_facts)))):
            self._add_candidate(candidates, 22 - idx * 2, f'fun_fact_{idx}', fact)

    def _add_advanced_candidates(self, candidates: List[Dict[str, Any]], match_data: dict,
                                 discord_members: List[Dict]) -> None:
        """Candidates from the full per-player round analysis (clutches, entry
        duels, KAST, pistols, weapons, spike plays, economy, behavior)."""
        add = self._add_candidate

        rows = []
        for dm in discord_members:
            member = dm['member']
            puuid = dm.get('account', {}).get('puuid') or dm['player_data'].get('puuid')
            if not puuid:
                continue
            try:
                row = valorant_client.build_match_stats_row(match_data, puuid)
            except Exception as e:
                log_error("computing advanced match stats", e)
                row = None
            if row:
                rows.append((member, row))

        if not rows:
            return

        # Clutches: each member's biggest clutch win (near-misses aren't a
        # highlight - nobody wants to be reminded they choked the 1v3)
        clutch_scores = {'1v1': 55, '1v2': 75, '1v3': 88, '1v4': 93, '1v5': 97}
        for member, row in rows:
            clutches_won = row.get('clutches_won') or {}
            for key in ('1v5', '1v4', '1v3', '1v2', '1v1'):
                won = clutches_won.get(key, 0)
                if won:
                    times = f" {won} times" if won > 1 else ""
                    add(candidates, clutch_scores[key], f'clutch:{member.id}',
                        f"🧊 **CLUTCH MASTER**: {member.display_name} won a {key} clutch{times}!",
                        member.id)
                    break

        # Entry duels: first bloods and first deaths
        entry_king = max(rows, key=lambda mr: mr[1].get('first_bloods', 0) or 0)
        first_bloods = entry_king[1].get('first_bloods', 0) or 0
        if first_bloods >= 4:
            add(candidates, min(70, 45 + 4 * first_bloods), 'first_bloods',
                f"⚔️ **OPENING DUELIST**: {entry_king[0].display_name} drew first blood {first_bloods} times!",
                entry_king[0].id)

        first_to_fall = max(rows, key=lambda mr: mr[1].get('first_deaths', 0) or 0)
        first_deaths = first_to_fall[1].get('first_deaths', 0) or 0
        if first_deaths >= 6:
            add(candidates, 54, 'first_deaths',
                f"🪦 **FIRST TO FALL**: {first_to_fall[0].display_name} died first {first_deaths} times... someone has to go in",
                first_to_fall[0].id)

        # KAST: most (and least) useful round-over-round
        rounds_played = rows[0][1].get('rounds_played', 0) or 0
        if rounds_played >= 12:
            kast_sorted = sorted(rows, key=lambda mr: mr[1].get('kast_rounds', 0) or 0, reverse=True)
            top_member, top_row = kast_sorted[0]
            top_kast = ((top_row.get('kast_rounds', 0) or 0) / rounds_played) * 100
            if top_kast >= 75:
                add(candidates, 50, 'kast_high',
                    f"🤝 **MOST VALUABLE TEAMMATE**: {top_member.display_name} contributed in {top_kast:.0f}% of rounds (KAST)",
                    top_member.id)
            if len(kast_sorted) >= 2:
                low_member, low_row = kast_sorted[-1]
                low_kast = ((low_row.get('kast_rounds', 0) or 0) / rounds_played) * 100
                if low_kast < 45:
                    add(candidates, 52, 'kast_low',
                        f"👻 **SPECTATOR MODE**: {low_member.display_name} impacted only {low_kast:.0f}% of rounds",
                        low_member.id)

        # Pistol rounds (team-wide, same for everyone in the stack)
        pistols_played = rows[0][1].get('pistol_rounds_played', 0) or 0
        pistols_won = rows[0][1].get('pistol_rounds_won', 0) or 0
        if pistols_played == 2:
            if pistols_won == 2:
                add(candidates, 58, 'pistols', "🔫 **PISTOL SWEEP**: Won both pistol rounds!")
            elif pistols_won == 0:
                add(candidates, 50, 'pistols', "💸 **PISTOL PROBLEMS**: Lost both pistol rounds 😬")

        # Eco round wins
        eco_hero = max(rows, key=lambda mr: mr[1].get('eco_rounds_won', 0) or 0)
        eco_wins = eco_hero[1].get('eco_rounds_won', 0) or 0
        if eco_wins >= 2:
            add(candidates, 52, 'eco',
                f"🥄 **BUDGET WARRIOR**: {eco_hero[0].display_name} won {eco_wins} rounds on eco buys",
                eco_hero[0].id)

        # Weapon personality
        for member, row in rows:
            weapon_kills = {str(k).lower(): v for k, v in (row.get('weapon_kills') or {}).items()}
            knife_kills = sum(v for k, v in weapon_kills.items() if 'melee' in k or 'knife' in k)
            if knife_kills:
                plural = 's' if knife_kills > 1 else ''
                # Knife kills are rare and always worth showing - score them up
                # there with aces/ninja defuses, and reward stacking them.
                add(candidates, min(96, 90 + 2 * knife_kills), f'knife:{member.id}',
                    f"🔪 **HUMILIATION**: {member.display_name} got {knife_kills} knife kill{plural}!",
                    member.id)
            sheriff_kills = weapon_kills.get('sheriff', 0)
            if sheriff_kills >= 3:
                add(candidates, 60, 'sheriff',
                    f"🤠 **SHERIFF SHOWDOWN**: {member.display_name} landed {sheriff_kills} Sheriff kills",
                    member.id)
            odin_kills = weapon_kills.get('odin', 0) + weapon_kills.get('ares', 0)
            if odin_kills >= 4:
                add(candidates, 58, 'odin',
                    f"🚜 **MACHINE GUN MAIN**: {member.display_name} mowed down {odin_kills} with the LMG",
                    member.id)
            operator_kills = weapon_kills.get('operator', 0)
            if operator_kills >= 5:
                add(candidates, 56, 'operator',
                    f"🔭 **OPERATOR MENACE**: {member.display_name} got {operator_kills} Operator kills",
                    member.id)

        # Spike plays
        for member, row in rows:
            extra = row.get('extra') or {}
            ninja_defuses = extra.get('ninja_defuses', 0) or 0
            if ninja_defuses:
                add(candidates, 94, f'ninja:{member.id}',
                    f"🥷 **NINJA DEFUSE**: {member.display_name} defused with enemies still alive!",
                    member.id)

        plant_leader = max(rows, key=lambda mr: (mr[1].get('extra') or {}).get('plants', 0) or 0)
        plants = (plant_leader[1].get('extra') or {}).get('plants', 0) or 0
        if plants >= 3:
            add(candidates, min(55, 44 + plants), 'plants',
                f"💣 **DEMOLITION CREW**: {plant_leader[0].display_name} planted the spike {plants} times",
                plant_leader[0].id)

        defuse_leader = max(rows, key=lambda mr: (mr[1].get('extra') or {}).get('defuses', 0) or 0)
        defuses = (defuse_leader[1].get('extra') or {}).get('defuses', 0) or 0
        if defuses >= 2:
            add(candidates, 50, 'defuses',
                f"✂️ **WIRE CUTTER**: {defuse_leader[0].display_name} defused {defuses} spikes",
                defuse_leader[0].id)

        # Behavior roasts
        for member, row in rows:
            extra = row.get('extra') or {}
            friendly_fire = extra.get('friendly_fire_damage', 0) or 0
            if friendly_fire >= 100:
                add(candidates, 72, f'friendly_fire:{member.id}',
                    f"🤡 **FRIENDLY FIRE**: {member.display_name} dealt {friendly_fire:.0f} damage to their OWN team",
                    member.id)
            afk_rounds = extra.get('afk_rounds', 0) or 0
            if afk_rounds >= 2:
                add(candidates, 68, f'afk:{member.id}',
                    f"😴 **AFK MOMENT**: {member.display_name} sat out {afk_rounds:.0f} rounds",
                    member.id)

        # Record book: fastest kill and longest-range kill in the squad
        fastest = None
        for member, row in rows:
            fastest_kill_ms = (row.get('extra') or {}).get('fastest_kill_ms', 0) or 0
            if fastest_kill_ms > 0 and (fastest is None or fastest_kill_ms < fastest[1]):
                fastest = (member, fastest_kill_ms)
        if fastest and fastest[1] <= 5000:
            add(candidates, 55, 'fastest_kill',
                f"⚡ **INSTANT AGGRESSION**: {fastest[0].display_name}'s fastest kill came {fastest[1] / 1000:.1f}s into a round",
                fastest[0].id)

        long_shot = max(rows, key=lambda mr: (mr[1].get('extra') or {}).get('longest_kill_distance', 0) or 0)
        distance = (long_shot[1].get('extra') or {}).get('longest_kill_distance', 0) or 0
        if distance >= 4000:  # game units; ~100 units per meter
            add(candidates, 54 if distance >= 4500 else 50, 'long_range',
                f"📏 **LONG RANGE**: {long_shot[0].display_name} landed a kill from ~{distance / 100:.0f}m away",
                long_shot[0].id)

        # Economy extremes
        pricey = max(rows, key=lambda mr: (mr[1].get('extra') or {}).get('most_expensive_death', 0) or 0)
        loadout_lost = (pricey[1].get('extra') or {}).get('most_expensive_death', 0) or 0
        if loadout_lost >= 5500:
            add(candidates, 48, 'expensive_death',
                f"💎 **MOST EXPENSIVE DEATH**: {pricey[0].display_name} donated a {loadout_lost:,}-credit loadout",
                pricey[0].id)

        spender = max(rows, key=lambda mr: (mr[1].get('extra') or {}).get('money_spent', 0) or 0)
        money_spent = (spender[1].get('extra') or {}).get('money_spent', 0) or 0
        if money_spent >= 25000:
            add(candidates, 30, 'spender',
                f"🤑 **BIG SPENDER**: {spender[0].display_name} burned through {money_spent:,} credits",
                spender[0].id)

        # Ability usage extremes (None means the API omitted ability data)
        ability_rows = [(m, r, (r.get('extra') or {}).get('ability_casts'))
                        for m, r in rows]
        ability_rows = [(m, r, c) for m, r, c in ability_rows if c is not None]
        if ability_rows:
            util_wizard = max(ability_rows, key=lambda mrc: mrc[2])
            if util_wizard[2] >= 50:
                add(candidates, 40, 'util_max',
                    f"🧙 **UTILITY WIZARD**: {util_wizard[0].display_name} threw out {util_wizard[2]} abilities",
                    util_wizard[0].id)
            util_minimalist = min(ability_rows, key=lambda mrc: mrc[2])
            if util_minimalist[2] <= 8 and (util_minimalist[1].get('rounds_played', 0) or 0) >= 18:
                add(candidates, 46, 'util_min',
                    f"🔫 **AIM IS MY UTILITY**: {util_minimalist[0].display_name} cast only {util_minimalist[2]} abilities all match",
                    util_minimalist[0].id)

    def _add_match_flow_candidates(self, candidates: List[Dict[str, Any]], match_data: dict,
                                   discord_members: List[Dict]) -> None:
        """Match-level storylines: comebacks, throws, overtime, stomps and
        economy swing rounds."""
        add = self._add_candidate

        stack_team = None
        for dm in discord_members:
            team = (dm['player_data'].get('team') or '').lower()
            if team:
                stack_team = team
                break

        if stack_team:
            our_rounds = their_rounds = 0
            max_deficit = max_lead = 0
            for round_data in match_data.get('rounds', []):
                winner = (round_data.get('winning_team') or '').lower()
                if not winner:
                    continue
                if winner == stack_team:
                    our_rounds += 1
                else:
                    their_rounds += 1
                max_deficit = max(max_deficit, their_rounds - our_rounds)
                max_lead = max(max_lead, our_rounds - their_rounds)

            teams = match_data.get('teams', {})
            team_won = teams.get(stack_team, {}).get('has_won', False)

            if team_won and max_deficit >= 4:
                add(candidates, 86, 'comeback',
                    f"🔥 **COMEBACK KINGS**: Won after trailing by {max_deficit} rounds!")
            elif not team_won and max_lead >= 4:
                add(candidates, 80, 'comeback',
                    f"📉 **THE THROW**: Lost after leading by {max_lead} rounds 💀")

            if our_rounds >= 12 and their_rounds >= 12:
                add(candidates, 70, 'overtime',
                    f"⏱️ **OVERTIME THRILLER**: This one went the distance at {our_rounds}-{their_rounds}!")
            elif team_won and our_rounds >= 13 and their_rounds <= 3:
                add(candidates, 60, 'stomp',
                    f"🧹 **CLEAN SWEEP**: {our_rounds}-{their_rounds} stomp!")

        # Swing round analysis (lower-economy team stealing rounds)
        swing_rounds = self._identify_swing_rounds(match_data)
        if swing_rounds and stack_team:
            stack_swing = None
            enemy_swing = None
            for sr in swing_rounds:
                if sr['winner'] == stack_team:
                    if not stack_swing or sr['diff'] > stack_swing['diff']:
                        stack_swing = sr
                else:
                    if not enemy_swing or sr['diff'] > enemy_swing['diff']:
                        enemy_swing = sr

            if stack_swing:
                add(candidates, 62, 'swing',
                    f"💸 **ROBBERY**: We robbed Round {stack_swing['round']} despite a {stack_swing['diff']:,} credit disadvantage!")
            if enemy_swing:
                add(candidates, 56, 'enemy_swing',
                    f"😱 **ROBBED**: Opponents robbed Round {enemy_swing['round']} despite a {enemy_swing['diff']:,} credit disadvantage!")

    def _identify_swing_rounds(self, match_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify rounds where the lower economy team won."""
        swing_rounds = []
        for idx, round_data in enumerate(match_data.get('rounds', []), start=1):
            team_totals = {'red': 0, 'blue': 0}
            for ps in round_data.get('player_stats', []):
                team = (ps.get('team') or ps.get('player_team') or '').lower()
                if team in team_totals:
                    loadout = ps.get('economy', {}).get('loadout_value', 0)
                    team_totals[team] += loadout

            diff = abs(team_totals['red'] - team_totals['blue'])
            if diff >= 6000:
                winner = round_data.get('winning_team', '').lower()
                if not winner:
                    continue
                underdog = 'red' if team_totals['red'] < team_totals['blue'] else 'blue'
                if winner == underdog:
                    swing_rounds.append({'round': idx, 'diff': diff, 'winner': winner})

        swing_rounds.sort(key=lambda r: r['diff'], reverse=True)
        return swing_rounds
    
    async def _update_stack_activity(self, guild: discord.Guild, discord_members_in_match: List[Dict], match_data: Dict[str, Any]) -> None:
        """Update stack activity tracking when matches are found"""
        # Get match timestamp
        started_at = match_data.get('metadata', {}).get('game_start', '')
        match_timestamp = parse_henrik_timestamp(started_at)
        if match_timestamp is None:
            match_timestamp = datetime.now(timezone.utc)
        
        # Find which channels have these members in their stacks
        for channel in guild.text_channels:
            context = context_manager.get_context(channel.id)
            all_stack_users = context.bot_soloq_user_set.union(context.bot_fullstack_user_set)
            
            if not all_stack_users:
                continue
            
            # Check if any of the match participants are in this channel's stack
            stack_members_in_match = []
            for dm in discord_members_in_match:
                if dm['member'] in all_stack_users:
                    stack_members_in_match.append(dm['member'])
            
            # If stack members were in this match, update activity
            if len(stack_members_in_match) >= self.MIN_DISCORD_MEMBERS:
                self.stack_last_activity[channel.id] = match_timestamp
                self.stack_has_played[channel.id] = True
                logging.info(f"Updated activity for stack in channel {channel.id} - {len(stack_members_in_match)} members played")
    
    async def _check_inactive_stacks(self) -> None:
        """Check for stacks that have been inactive and auto-end them"""
        current_time = datetime.now(timezone.utc)
        inactivity_cutoff = timedelta(hours=self.STACK_INACTIVITY_HOURS)
        
        for guild in self.bot.guilds:
            try:
                for channel in guild.text_channels:
                    context = context_manager.get_context(channel.id)
                    all_stack_users = context.bot_soloq_user_set.union(context.bot_fullstack_user_set)
                    
                    # Skip if no one is in the stack
                    if not all_stack_users:
                        # Clean up tracking data for empty stacks
                        if channel.id in self.stack_last_activity:
                            del self.stack_last_activity[channel.id]
                        if channel.id in self.stack_has_played:
                            del self.stack_has_played[channel.id]
                        continue
                    
                    # Only check stacks that have had gaming activity
                    if not self.stack_has_played.get(channel.id, False):
                        continue
                    
                    # Check if stack has been inactive
                    last_activity = self.stack_last_activity.get(channel.id)
                    if last_activity and (current_time - last_activity) > inactivity_cutoff:
                        await self._auto_end_inactive_stack(channel, context, current_time - last_activity)
                        
            except Exception as e:
                log_error(f"checking inactive stacks for {guild.id}", e)
    
    async def _auto_end_inactive_stack(self, channel: discord.TextChannel, context, inactivity_duration: timedelta) -> None:
        """Automatically end an inactive stack"""
        try:
            # Get the session commands cog to end the session properly
            session_cog = self.bot.get_cog('SessionCommands')
            if session_cog:
                # Use the cog's method to properly end the session
                await session_cog._end_current_session(context)
            else:
                # Fallback: end session manually using data manager
                if hasattr(context, 'current_session_id') and context.current_session_id:
                    from data_manager import data_manager
                    session = data_manager.sessions.get(context.current_session_id)
                    if session:
                        # Add all current participants
                        all_users = context.bot_soloq_user_set.union(context.bot_fullstack_user_set)
                        for user in all_users:
                            session.add_participant(user.id)
                            user_data = data_manager.get_user(user.id)
                            user_data.add_session_to_history(context.current_session_id)
                            data_manager.save_user(user.id)
                        
                        # Check if party was full
                        if len(all_users) >= context.party_max_size:
                            session.was_full = True
                        
                        # End the session
                        session.end_session()
                        data_manager.save_session(context.current_session_id)
                    
                    # Clear session reference
                    context.current_session_id = None
            
            # Clear users from the stack
            context.reset_users()
            
            # Clean up tracking data
            if channel.id in self.stack_last_activity:
                del self.stack_last_activity[channel.id]
            if channel.id in self.stack_has_played:
                del self.stack_has_played[channel.id]
            
            # Silently end the stack and log the action
            logging.info(
                f"Auto-ended inactive stack in channel {channel.id} after {inactivity_duration}"
            )
            
        except Exception as e:
            log_error(f"auto-ending stack in channel {channel.id}", e)
    
    async def manual_check_recent_match(self, guild: discord.Guild, member: discord.Member = None, force_fresh: bool = False) -> Optional[discord.Embed]:
        """Manually check for a recent match and return embed if found"""
        if member:
            members_to_check = [member]
        else:
            # Check all members with linked accounts
            members_to_check = []
            for m in guild.members:
                if not m.bot and valorant_client.get_all_linked_accounts(m.id):
                    members_to_check.append(m)
        
        if not members_to_check:
            return None
        
        # Check the most recent matches for each member: discover match ids via
        # the lightweight competitive-updates endpoint, then pull full details
        # from the permanent SQLite cache (API only for genuinely new matches)
        for member in members_to_check:
            try:
                # Get all linked accounts for this user, not just primary
                all_accounts = valorant_client.get_all_linked_accounts(member.id)
                if not all_accounts:
                    continue

                # Check matches for all linked accounts to get better coverage
                for account in all_accounts:
                    updates = await valorant_client.get_recent_competitive_updates(
                        account['username'],
                        account['tag'],
                        puuid=account.get('puuid'),
                        force_refresh=force_fresh
                    )

                    if not updates:
                        continue

                    # Check the most recent matches to find one with Discord members
                    for update in updates[:5]:
                        match_id = update.get('match_id')
                        if not match_id:
                            continue

                        was_stored = database_manager.get_stored_match(match_id) is not None
                        match = await valorant_client.get_match_details(match_id)
                        if not match:
                            continue

                        # Find Discord members in this match
                        discord_members_in_match = await self._find_discord_members_in_match(guild, match)

                        if len(discord_members_in_match) >= 1:
                            embed = await self._create_match_embed(match, discord_members_in_match)
                            # Add manual check indicator
                            if embed:
                                if was_stored:
                                    embed.set_footer(text="🔍 Manual match lookup (cached) • ShootyBot")
                                else:
                                    embed.set_footer(text="🔍 Manual match lookup (fresh) • ShootyBot")
                            return embed

            except Exception as e:
                log_error(f"in manual check for {member.display_name}", e)

        return None

    async def _load_state_from_database(self) -> None:
        """Load match tracker state from database on startup"""
        try:
            # Load tracked members for all servers
            for guild in self.bot.guilds:
                tracked_users = database_manager.get_all_tracked_users(guild.id)
                for user_id, tracking_data in tracked_users.items():
                    # Convert stored datetime strings back to datetime objects
                    if 'last_checked' in tracking_data and tracking_data['last_checked']:
                        try:
                            tracking_data['last_checked'] = datetime.fromisoformat(tracking_data['last_checked'])
                        except (ValueError, TypeError):
                            tracking_data['last_checked'] = datetime.now(timezone.utc)
                    
                    self.tracked_members[user_id] = tracking_data
            
            # Load stack states
            stack_states = database_manager.get_all_stack_states()
            for channel_id, state_data in stack_states.items():
                self.stack_has_played[channel_id] = state_data['has_played']
                if state_data['last_activity']:
                    self.stack_last_activity[channel_id] = state_data['last_activity']
            
            logging.info(f"Loaded match tracker state: {len(self.tracked_members)} tracked users, {len(self.stack_has_played)} stack states")
            
        except Exception as e:
            log_error("loading match tracker state from database", e)
    
    async def _save_state_to_database(self) -> None:
        """Save current match tracker state to database"""
        try:
            # Save tracked members by server
            servers_processed = set()
            for guild in self.bot.guilds:
                server_id = guild.id
                if server_id in servers_processed:
                    continue
                servers_processed.add(server_id)
                
                # Collect tracking data for users in this server
                for user_id, tracking_data in self.tracked_members.items():
                    # Check if user is in this guild
                    member = guild.get_member(user_id)
                    if member:
                        # Convert datetime objects to strings for JSON storage
                        tracking_data_copy = tracking_data.copy()
                        if 'last_checked' in tracking_data_copy and isinstance(tracking_data_copy['last_checked'], datetime):
                            tracking_data_copy['last_checked'] = tracking_data_copy['last_checked'].isoformat()
                        
                        database_manager.save_match_tracker_state(user_id, server_id, tracking_data_copy)
            
            # Save stack states
            for channel_id, has_played in self.stack_has_played.items():
                last_activity = self.stack_last_activity.get(channel_id)
                # Get participant count from context if available
                try:
                    context = context_manager.get_context(channel_id)
                    participant_count = len(context.bot_soloq_user_set.union(context.bot_fullstack_user_set))
                except:
                    participant_count = 0
                
                database_manager.save_stack_state(
                    channel_id=channel_id,
                    has_played=has_played,
                    last_activity=last_activity,
                    participant_count=participant_count
                )
            
            # Clean up old state data (older than 30 days)
            database_manager.cleanup_old_tracker_state(days=30)
            
        except Exception as e:
            log_error("saving match tracker state to database", e)
    
    def get_persistence_stats(self) -> Dict[str, int]:
        """Get statistics about persisted state"""
        try:
            stats = database_manager.get_database_stats()
            return {
                'tracked_users_persisted': stats.get('match_tracker_state', 0),
                'stack_states_persisted': stats.get('stack_state', 0),
                'tracked_users_memory': len(self.tracked_members),
                'stack_states_memory': len(self.stack_has_played)
            }
        except Exception as e:
            log_error("getting persistence stats", e)
            return {}

# Global match tracker instance
match_tracker = None

def get_match_tracker(bot: discord.Client) -> MatchTracker:
    """Get or create the global match tracker instance"""
    global match_tracker
    if match_tracker is None:
        match_tracker = MatchTracker(bot)
    return match_tracker