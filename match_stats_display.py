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

import logging
import re
from typing import Dict, List, Optional, Any

import discord

from valorant_client import valorant_client
from database import database_manager
from utils import log_error

logger = logging.getLogger(__name__)

# --- round flow -------------------------------------------------------------

_HALF_LENGTH = 12  # standard competitive half


def _round_attacking_team(round_data: Dict[str, Any],
                          puuid_team: Dict[str, str]) -> Optional[str]:
    """The team on attack for a round, inferred from who planted the spike.

    Only the attacking side can plant, so the planter's team is the attacker.
    Returns None for rounds with no plant (e.g. a full eliminate)."""
    planted_by = (round_data.get('plant_events') or {}).get('planted_by') or {}
    puuid = planted_by.get('puuid')
    if puuid and puuid in puuid_team:
        return puuid_team[puuid]
    return (planted_by.get('team') or '').lower() or None


def build_round_flow(match: Dict[str, Any], team_color: str) -> str:
    """Numbered, colour-coded round-by-round strip from the squad's view.

    Each round shows its number, coloured green when the squad won it and red
    when they lost, rendered in a monospace ``ansi`` block so the numbers line
    up and you can tell exactly which round was which. Each regulation half is
    tagged ATK/DEF (inferred from who planted the spike) and rows wrap per half
    (and again for overtime). Returns "" when round data is missing.
    """
    rounds = match.get('rounds', [])
    if not rounds or not team_color:
        return ""

    all_players = match.get('players', {}).get('all_players', [])
    puuid_team = {p.get('puuid'): (p.get('team') or '').lower()
                  for p in all_players if p.get('puuid')}

    outcomes = []  # (round_number, won | None)
    for i, rd in enumerate(rounds, start=1):
        winner = (rd.get('winning_team') or '').lower()
        outcomes.append((i, (winner == team_color) if winner else None))

    lines = []
    total = len(rounds)
    for start in range(0, total, _HALF_LENGTH):
        end = min(start + _HALF_LENGTH, total)

        # Side tag. Sides hold for a regulation half but swap every round in
        # overtime, so only the two regulation halves get an ATK/DEF label.
        if start < 2 * _HALF_LENGTH:
            attacker = next((t for t in (_round_attacking_team(rounds[i], puuid_team)
                                         for i in range(start, end)) if t), None)
            if attacker:
                tag = (f"{_ATK}ATK{_RESET}" if attacker == team_color
                       else f"{_DEF}DEF{_RESET}")
            else:
                tag = "  ?"
        else:
            tag = f"{_HDR} OT{_RESET}"

        cells = []
        for number, won in outcomes[start:end]:
            label = f"{number:>2}"
            if won is None:
                cells.append(label)
            elif won:
                cells.append(f"{_WIN}{label}{_RESET}")
            else:
                cells.append(f"{_LOSS}{label}{_RESET}")
        lines.append(f"{tag} │ " + " ".join(cells))

    return "```ansi\n" + "\n".join(lines) + "\n```"


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

    return {
        'kills': kills, 'deaths': deaths, 'assists': assists,
        'acs': round(score / rounds) if rounds else 0,
        'adr': round(damage / rounds) if rounds else 0,
        'kd': kills / deaths if deaths else float(kills),
        'hs': hs, 'kast': kast,
        'fk': first_kills, 'fd': first_deaths, 'mk': multikills,
    }


# --- advanced scoreboard (ANSI) --------------------------------------------

_RESET = "[0m"
_BEST_GAME = "[1;33m"   # bold yellow - best in the whole match
_BEST_TEAM = "[0;36m"   # cyan - best on the team
_HDR = "[1;37m"         # bold white header
_WIN = "[0;32m"         # green team label
_LOSS = "[0;31m"        # red team label

# Round-flow side tags reuse the highlight palette: yellow attack, cyan defense.
_ATK = _BEST_GAME
_DEF = _BEST_TEAM

_NAME_W = 14
# (header, key, width, higher_is_better)
_COLS = [
    ("ACS", 'acs', 4, True),
    ("K", 'kills', 3, True),
    ("D", 'deaths', 3, False),
    ("A", 'assists', 3, True),
    ("K/D", 'kd', 4, True),
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
    if key == 'kd':
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
        rows.append((stats, (player.get('team') or '').lower()))

    game_best = {key: max((r[key] for r, _ in rows), default=0)
                 for _, key, _, hib in _COLS if hib}

    header = "Player".ljust(_NAME_W) + "".join(
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
        lines.append(f"{_WIN if won else _LOSS}{label}{_RESET}")

        for r in members:
            cells = _truncate(r['name'], _NAME_W).ljust(_NAME_W)
            cells += "".join(
                " " + _cell(key, r[key], w, hib, game_best, team_best)
                for _, key, w, hib in _COLS)
            lines.append(cells)

    body = "\n".join(lines)
    title = f"📊 **Advanced Match Stats** — {metadata.get('map', 'Unknown')}"
    legend = "🟡 best in match · 🔵 best on team"
    return f"{title}\n```ansi\n{body}\n```\n_{legend}_"


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
        await interaction.followup.send(content, ephemeral=True)


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
