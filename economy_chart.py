"""Tracker.gg-style per-round economy chart for the post-match recap.

Renders the round-by-round *loadout-value differential* between the squad and
the enemy: the area is green in rounds where the squad out-spent the enemy and
red where they were out-spent, with a marker strip underneath showing who won
each round and how (elimination / spike detonation / defuse).

Everything is derived from the full match payload that the Advanced Stats
button already reloads from the permanent ``henrik_matches`` cache, so no extra
Henrik calls are made. ``loadout_value`` is the only economy field Henrik
reliably populates (see ``valorant_client._compute_round_stats``), so it's what
we chart.

matplotlib is imported lazily inside :func:`render_economy_chart`; if it isn't
installed the function returns ``None`` and callers fall back to the text-only
scoreboard. Rendering is blocking, so callers should run it in an executor.
"""

import io
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def warm_up() -> bool:
    """Eagerly import matplotlib and prime its font cache.

    The first matplotlib import is slow (tens of seconds on a Pi, reading many
    small modules off the SD card). Running this once at startup in an executor
    moves that cost off the first user's Advanced Stats click, so every click is
    sub-second. Blocking - run off the event loop. Returns True on success.
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig = plt.figure()          # first figure builds the font cache
        fig.savefig(io.BytesIO(), format='png')
        plt.close(fig)
        logger.info("Economy chart renderer warmed up")
        return True
    except Exception as e:  # pragma: no cover - depends on the host env
        logger.info("Economy chart warm-up skipped (matplotlib unavailable): %s", e)
        return False


def _puuid_team_map(match: Dict[str, Any]) -> Dict[str, str]:
    all_players = match.get('players', {}).get('all_players', [])
    return {p.get('puuid'): (p.get('team') or '').lower()
            for p in all_players if p.get('puuid')}


def pick_squad_team(match: Dict[str, Any], linked_puuids: set) -> Optional[str]:
    """Team colour (``'red'``/``'blue'``) hosting the most linked squad members.

    Falls back to the match winner so the chart still has a stable "positive"
    reference when nobody in the match is linked. Returns ``None`` only when
    there's no team data at all.
    """
    puuid_team = _puuid_team_map(match)
    counts: Dict[str, int] = {}
    for puuid, team in puuid_team.items():
        if team and puuid in linked_puuids:
            counts[team] = counts.get(team, 0) + 1
    if counts:
        return max(counts, key=counts.get)

    teams = match.get('teams', {})
    winner = next((c for c, d in teams.items() if d.get('has_won')), None)
    if winner:
        return winner.lower()
    return next(iter(teams), None)


def _round_condition(round_data: Dict[str, Any]) -> str:
    """How the round ended: ``'defuse'``, ``'plant'`` (detonation) or ``'elim'``."""
    if (round_data.get('defuse_events') or {}).get('defused_by'):
        return 'defuse'
    if (round_data.get('plant_events') or {}).get('planted_by'):
        return 'plant'
    return 'elim'


def compute_round_economy(match: Dict[str, Any],
                          squad_team: str) -> List[Dict[str, Any]]:
    """Per-round economy data from the squad's perspective.

    Returns one dict per round with the squad/enemy loadout totals, their
    difference, whether the squad won the round (``None`` if unknown) and the
    win condition. Returns ``[]`` when round data is missing.
    """
    rounds = match.get('rounds', [])
    if not rounds or not squad_team:
        return []
    squad_team = squad_team.lower()
    puuid_team = _puuid_team_map(match)

    result: List[Dict[str, Any]] = []
    for i, rd in enumerate(rounds, start=1):
        squad_loadout = enemy_loadout = 0
        for ps in rd.get('player_stats', []):
            team = puuid_team.get(ps.get('player_puuid'), '')
            loadout = (ps.get('economy') or {}).get('loadout_value', 0) or 0
            if team == squad_team:
                squad_loadout += loadout
            elif team:
                enemy_loadout += loadout

        winner = (rd.get('winning_team') or '').lower()
        result.append({
            'round': i,
            'squad_loadout': squad_loadout,
            'enemy_loadout': enemy_loadout,
            'diff': squad_loadout - enemy_loadout,
            'squad_won': (winner == squad_team) if winner else None,
            'condition': _round_condition(rd),
        })
    return result


# Marker shapes mirror the round-condition icons on tracker.gg's economy tab.
_CONDITION_MARKER = {'elim': 'x', 'plant': '^', 'defuse': 'v'}

_BG = '#101820'
# Sides keep their fixed Valorant identity: blue team is always blue, red team
# is always red. The chart plots the blue team's loadout advantage, so positive
# (blue richer) fills blue and negative (red richer) fills red — no need to work
# out which side the squad was on.
_BLUE = '#3b82f6'
_RED = '#ed4245'
_GRID = '#2b3543'
_TEXT = '#c8d0da'


def render_economy_chart(match: Dict[str, Any],
                         squad_team: Optional[str]) -> Optional[io.BytesIO]:
    """Render the economy chart to a PNG ``BytesIO``.

    Returns ``None`` (so callers fall back to text) when matplotlib is missing,
    round data is unavailable, or rendering fails. Blocking — run in an executor.
    """
    if not squad_team:
        return None
    # The chart is drawn in absolute team terms (blue vs red) rather than from
    # the squad's perspective, so colours always mean the same side. squad_team
    # is still required as the "we have a team to anchor on" guard.
    data = compute_round_economy(match, 'blue')
    if not data:
        return None

    try:
        import matplotlib
        matplotlib.use('Agg')  # headless: no display needed on the Pi
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter
    except Exception as e:  # pragma: no cover - depends on the host env
        logger.info("Economy chart skipped (matplotlib unavailable): %s", e)
        return None

    try:
        rounds = [d['round'] for d in data]
        diff_k = [d['diff'] / 1000 for d in data]

        teams = match.get('teams', {})
        blue_rounds = teams.get('blue', {}).get('rounds_won', 0)
        red_rounds = teams.get('red', {}).get('rounds_won', 0)
        map_name = match.get('metadata', {}).get('map', 'Unknown')

        fig, ax = plt.subplots(figsize=(9, 3.6), dpi=110)
        fig.patch.set_facecolor(_BG)
        ax.set_facecolor(_BG)

        # diff is the blue team's loadout advantage, so positive fills blue and
        # negative fills red.
        ax.fill_between(rounds, diff_k, 0, where=[v >= 0 for v in diff_k],
                        interpolate=True, color=_BLUE, alpha=0.45)
        ax.fill_between(rounds, diff_k, 0, where=[v <= 0 for v in diff_k],
                        interpolate=True, color=_RED, alpha=0.45)
        ax.plot(rounds, diff_k, color=_TEXT, linewidth=1.4, zorder=3)
        for d, y in zip(data, diff_k):
            ax.plot(d['round'], y, marker='o', markersize=4, zorder=4,
                    color=_BLUE if d['diff'] >= 0 else _RED)
        ax.axhline(0, color=_TEXT, linewidth=1.0, alpha=0.8)

        # Round-outcome strip beneath the plot, coloured by the winning team
        # (blue/red); marker shape encodes the win condition. squad_won here is
        # True when blue won, since the economy is computed from blue's side.
        span = max((abs(v) for v in diff_k), default=1) or 1
        strip_y = -span * 1.25
        for d in data:
            if d['squad_won'] is None:
                color = _GRID
            else:
                color = _BLUE if d['squad_won'] else _RED
            ax.scatter(d['round'], strip_y, s=46, zorder=5, color=color,
                       marker=_CONDITION_MARKER.get(d['condition'], 'x'),
                       linewidths=1.4)
        ax.set_ylim(strip_y - span * 0.35, span * 1.2)

        ax.set_xlim(0.5, len(rounds) + 0.5)
        ax.set_xticks(rounds)
        ax.tick_params(colors=_TEXT, labelsize=7)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}k"))
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.grid(axis='y', color=_GRID, linewidth=0.6, alpha=0.6)
        ax.set_axisbelow(True)

        ax.set_title(
            f"Economy — {map_name}   "
            f"Blue {blue_rounds} : {red_rounds} Red",
            color=_TEXT, fontsize=11, fontweight='bold', pad=10)
        ax.set_ylabel("Loadout advantage", color=_TEXT, fontsize=8)
        fig.text(0.5, 0.005,
                 "▲ blue = blue richer · ▼ red = red richer    "
                 "strip: ✕ elim · ▲ detonation · ▼ defuse",
                 color=_TEXT, fontsize=6.5, alpha=0.75, ha='center')

        fig.tight_layout(rect=(0, 0.04, 1, 1))
        buf = io.BytesIO()
        fig.savefig(buf, format='png', facecolor=_BG)
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as e:
        logger.warning("Failed to render economy chart: %s", e)
        try:
            plt.close('all')
        except Exception:
            pass
        return None
