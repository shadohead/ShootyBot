"""Rendering helpers for the post-match recap.

Keeps the heavier presentation logic out of ``match_tracker``:

* per-player display stats for the squad list (ACS / ADR),
* the round-flow strip (emoji squares, split at half-time),
* the advanced tracker.gg-style scoreboard rendered as a Discord ``ansi``
  code block with the best value per column colour-highlighted, and
* the persistent button (a ``DynamicItem`` keyed on the match id) that reveals
  that scoreboard on demand without cluttering the recap.

The button reloads the match from the permanent ``henrik_matches`` cache, so it
keeps working across bot restarts.
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional, Any

import discord

from valorant_client import valorant_client
from database import database_manager
from economy_chart import render_economy_chart, pick_squad_team
from utils import log_error

logger = logging.getLogger(__name__)

# --- per-player display stats ----------------------------------------------

def _rounds_played(match: Dict[str, Any]) -> int:
    return (match.get('metadata', {}).get('rounds_played')
            or len(match.get('rounds', []))
            or 0)


def player_display_stats(match: Dict[str, Any], player_data: Dict[str, Any],
                         puuid: Optional[str]) -> Dict[str, Any]:
    """Resolve the stats shown for one player in the recap.

    Uses the tournament-grade row (KAST/FK/FD/MK) when the player is found in
    the match's round data, otherwise falls back to the basic scoreboard so
    untracked teammates and sparse test data still render.
    """
    rounds = _rounds_played(match) or 1
    row = valorant_client.build_match_stats_row(match, puuid) if puuid else None

    if row:
        kills, deaths, assists = row['kills'], row['deaths'], row['assists']
        score, damage = row['score'], row['damage_made']
        shots = row['headshots'] + row['bodyshots'] + row['legshots']
        hs = round(row['headshots'] / shots * 100) if shots else 0
        kast = round(row['kast_rounds'] / rounds * 100) if rounds else 0
        first_kills, first_deaths = row['first_bloods'], row['first_deaths']
        multikills = row['multikills_3k'] + row['multikills_4k'] + row['multikills_5k']
    else:
        stats = player_data.get('stats', {})
        kills = stats.get('kills', 0)
        deaths = stats.get('deaths', 0)
        assists = stats.get('assists', 0)
        score = stats.get('score', 0)
        damage = player_data.get('damage_made', 0)
        shots = stats.get('headshots', 0) + stats.get('bodyshots', 0) + stats.get('legshots', 0)
        hs = round(stats.get('headshots', 0) / shots * 100) if shots else 0
        kast = first_kills = first_deaths = multikills = 0

    agent = player_data.get('character', '') or ''

    return {
        'kills': kills, 'deaths': deaths, 'assists': assists,
        'acs': round(score / rounds) if rounds else 0,
        'adr': round(damage / rounds) if rounds else 0,
        'kd': kills / deaths if deaths else float(kills),
        'kda': (kills + assists) / deaths if deaths else float(kills + assists),
        'hs': hs, 'kast': kast,
        'fk': first_kills, 'fd': first_deaths, 'mk': multikills,
        'agent': agent,
    }


# --- advanced scoreboard (ANSI) --------------------------------------------

_RESET = "[0m"
_BEST_GAME = "[1;33m"   # bold yellow - best in the whole match
_BEST_TEAM = "[0;36m"   # cyan - best on the team
_HDR = "[1;37m"         # bold white header
# Sides are coloured by their fixed Valorant identity: blue team always
# blue, red team always red — used for both the team headers and the
# round-flow strip, so no squad-side detection is needed.
_BLUE = "[1;34m"        # blue team
_RED = "[1;31m"         # red team

_NAME_W = 14
_AGENT_W = 9  # widest agent name (Brimstone) fits without truncation
# (header, key, width, higher_is_better)
_COLS = [
    ("ACS", 'acs', 4, True),
    ("K", 'kills', 3, True),
    ("D", 'deaths', 3, False),
    ("A", 'assists', 3, True),
    ("K/D", 'kd', 4, True),
    ("KDA", 'kda', 4, True),
    ("ADR", 'adr', 4, True),
    ("HS%", 'hs', 5, True),
    ("KAST", 'kast', 5, True),
    ("FK", 'fk', 3, True),
    ("FD", 'fd', 3, False),
    ("MK", 'mk', 3, True),
]


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[:width - 1] + "…"


def _format_value(key: str, value: Any) -> str:
    if key in ('kd', 'kda'):
        return f"{value:.1f}"
    if key in ('hs', 'kast'):
        return f"{value}%"
    return str(value)


def _cell(key: str, value: Any, width: int, higher_is_better: bool,
          game_best: Dict[str, Any], team_best: Dict[str, Any]) -> str:
    """Right-justified cell, colour-wrapped if it's a leading value.

    Padding happens before colour codes so column alignment is preserved (the
    escape sequences have zero visible width).
    """
    text = _format_value(key, value).rjust(width)
    if not higher_is_better or value in (0, 0.0):
        return text
    if value == game_best.get(key):
        return f"{_BEST_GAME}{text}{_RESET}"
    if value == team_best.get(key):
        return f"{_BEST_TEAM}{text}{_RESET}"
    return text


def build_advanced_scoreboard(match: Dict[str, Any]) -> str:
    """Full both-teams scoreboard as a colour-highlighted ``ansi`` code block."""
    all_players = match.get('players', {}).get('all_players', [])
    if not all_players:
        return ""

    teams = match.get('teams', {})
    metadata = match.get('metadata', {})

    rows = []
    for player in all_players:
        stats = player_display_stats(match, player, player.get('puuid'))
        name = player.get('name', 'Unknown')
        tag = player.get('tag', '')
        stats['name'] = f"{name}#{tag}" if tag else name
        stats['agent'] = player.get('character', '') or ''
        rows.append((stats, (player.get('team') or '').lower()))

    game_best = {key: max((r[key] for r, _ in rows), default=0)
                 for _, key, _, hib in _COLS if hib}

    header = "Player".ljust(_NAME_W) + "Agent".ljust(_AGENT_W) + "".join(
        h.rjust(w + 1) for h, _, w, _ in _COLS)

    lines = [f"{_HDR}{header}{_RESET}"]

    def team_rounds(tcol: str) -> int:
        return teams.get(tcol, {}).get('rounds_won', 0)

    by_team: Dict[str, List[Dict[str, Any]]] = {}
    for stats, tcol in rows:
        by_team.setdefault(tcol, []).append(stats)

    # Winner first so the scoreboard reads like the result.
    for tcol in sorted(by_team, key=team_rounds, reverse=True):
        members = sorted(by_team[tcol], key=lambda r: r['acs'], reverse=True)
        team_best = {key: max((r[key] for r in members), default=0)
                     for _, key, _, hib in _COLS if hib}

        won = teams.get(tcol, {}).get('has_won', False)
        label = f"{tcol.title() or 'Team'} — {team_rounds(tcol)}" + (" 🏆" if won else "")
        lines.append("")
        team_color = _BLUE if tcol == "blue" else _RED if tcol == "red" else _HDR
        lines.append(f"{team_color}{label}{_RESET}")

        for r in members:
            cells = _truncate(r['name'], _NAME_W).ljust(_NAME_W)
            cells += _truncate(r.get('agent', ''), _AGENT_W).ljust(_AGENT_W)
            cells += "".join(
                " " + _cell(key, r[key], w, hib, game_best, team_best)
                for _, key, w, hib in _COLS)
            lines.append(cells)

    body = "\n".join(lines)
    # Just the map name + the table; the recap headline and the economy chart
    # (which carries its own title) supply the rest of the context.
    title = f"**{metadata.get('map', 'Unknown')}**"
    return f"{title}\n```ansi\n{body}\n```"


# --- persistent reveal button ----------------------------------------------

class AdvancedStatsButton(
        discord.ui.DynamicItem[discord.ui.Button],
        template=r'shooty:advstats:(?P<match_id>[\w-]+)'):
    """Button that reveals the advanced scoreboard ephemerally.

    Because it's a ``DynamicItem`` registered on the bot, it survives restarts:
    the match id is encoded in the custom id and the match is reloaded from the
    permanent match cache when clicked.
    """

    def __init__(self, match_id: str) -> None:
        self.match_id = match_id
        super().__init__(
            discord.ui.Button(
                label="Advanced Stats",
                emoji="📊",
                style=discord.ButtonStyle.secondary,
                custom_id=f"shooty:advstats:{match_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction,
                             item: discord.ui.Button, match) -> "AdvancedStatsButton":
        return cls(match["match_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        match = database_manager.get_stored_match(self.match_id)
        if not match:
            await interaction.followup.send(
                "Detailed stats for this match aren't cached anymore.", ephemeral=True)
            return
        try:
            content = build_advanced_scoreboard(match)
        except Exception as e:
            log_error("building advanced scoreboard", e)
            content = ""
        if not content:
            await interaction.followup.send(
                "Couldn't build advanced stats for this match.", ephemeral=True)
            return

        chart_file = await self._build_economy_chart(match)
        if chart_file is not None:
            await interaction.followup.send(content, file=chart_file, ephemeral=True)
        else:
            await interaction.followup.send(content, ephemeral=True)

    @staticmethod
    async def _build_economy_chart(match) -> Optional[discord.File]:
        """Render the round-economy chart off the event loop, or None on failure.

        Rendering is CPU-bound (matplotlib), so it runs in the default executor
        to avoid stalling the bot. Any failure degrades silently to text-only.
        """
        try:
            squad_team = pick_squad_team(match, database_manager.get_linked_puuids())
            loop = asyncio.get_running_loop()
            buf = await loop.run_in_executor(
                None, render_economy_chart, match, squad_team)
            if buf is None:
                return None
            return discord.File(buf, filename="economy.png")
        except Exception as e:
            log_error("building economy chart", e)
            return None


def recap_view(match_id: Optional[str]) -> Optional[discord.ui.View]:
    """A view carrying the Advanced Stats button, or None without a match id."""
    if not match_id:
        return None
    view = discord.ui.View(timeout=None)
    view.add_item(AdvancedStatsButton(match_id))
    return view


_MATCH_ID_RE = re.compile(r'/valorant/match/([\w-]+)')


def recap_view_from_embed(embed: Optional[discord.Embed]) -> Optional[discord.ui.View]:
    """Build the recap view by recovering the match id from a recap embed's
    Tracker.gg link (used where only the embed is on hand)."""
    if not embed or not embed.description:
        return None
    found = _MATCH_ID_RE.search(embed.description)
    return recap_view(found.group(1)) if found else None
