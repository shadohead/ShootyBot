"""Tests for the post-match economy chart data extraction and rendering.

The pure data functions are tested exactly; rendering is tested for graceful
behaviour whether or not matplotlib is importable on the host.
"""

import io
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from economy_chart import (
    compute_round_economy,
    pick_squad_team,
    render_economy_chart,
)


def build_match():
    """2v2 match: round 1 Red richer & wins by detonation, round 2 Blue richer
    & wins by defuse."""
    return {
        'metadata': {'map': 'Ascent', 'rounds_played': 2},
        'players': {'all_players': [
            {'puuid': 'A1', 'team': 'Red'},
            {'puuid': 'A2', 'team': 'Red'},
            {'puuid': 'B1', 'team': 'Blue'},
            {'puuid': 'B2', 'team': 'Blue'},
        ]},
        'teams': {'red': {'has_won': False, 'rounds_won': 1},
                  'blue': {'has_won': True, 'rounds_won': 1}},
        'rounds': [
            {
                'winning_team': 'Red',
                'plant_events': {'planted_by': {'puuid': 'A1'}},
                'defuse_events': {},
                'player_stats': [
                    {'player_puuid': 'A1', 'economy': {'loadout_value': 4000}},
                    {'player_puuid': 'A2', 'economy': {'loadout_value': 4000}},
                    {'player_puuid': 'B1', 'economy': {'loadout_value': 1000}},
                    {'player_puuid': 'B2', 'economy': {'loadout_value': 1000}},
                ],
            },
            {
                'winning_team': 'Blue',
                'plant_events': {},
                'defuse_events': {'defused_by': {'puuid': 'B1'}},
                'player_stats': [
                    {'player_puuid': 'A1', 'economy': {'loadout_value': 800}},
                    {'player_puuid': 'A2', 'economy': {'loadout_value': 800}},
                    {'player_puuid': 'B1', 'economy': {'loadout_value': 5000}},
                    {'player_puuid': 'B2', 'economy': {'loadout_value': 5000}},
                ],
            },
        ],
    }


def test_compute_round_economy_from_red_perspective():
    data = compute_round_economy(build_match(), 'red')
    assert len(data) == 2

    r1 = data[0]
    assert r1['round'] == 1
    assert r1['squad_loadout'] == 8000
    assert r1['enemy_loadout'] == 2000
    assert r1['diff'] == 6000          # Red richer
    assert r1['squad_won'] is True
    assert r1['condition'] == 'plant'  # detonation, spike was planted

    r2 = data[1]
    assert r2['diff'] == -8400         # Blue richer
    assert r2['squad_won'] is False
    assert r2['condition'] == 'defuse'


def test_compute_round_economy_perspective_flips_sign():
    red = compute_round_economy(build_match(), 'red')
    blue = compute_round_economy(build_match(), 'blue')
    assert blue[0]['diff'] == -red[0]['diff']
    assert blue[0]['squad_won'] is False


def test_compute_round_economy_no_rounds():
    assert compute_round_economy({'rounds': []}, 'red') == []
    assert compute_round_economy(build_match(), '') == []


def test_pick_squad_team_prefers_linked_members():
    # Two linked players sit on Blue -> Blue is the squad.
    assert pick_squad_team(build_match(), {'B1', 'B2'}) == 'blue'
    assert pick_squad_team(build_match(), {'A1'}) == 'red'


def test_pick_squad_team_falls_back_to_winner():
    # Nobody linked -> fall back to the match winner (Blue won here).
    assert pick_squad_team(build_match(), set()) == 'blue'


def test_render_economy_chart_returns_png_or_none():
    """With matplotlib present we get a non-empty PNG; without it, None."""
    result = render_economy_chart(build_match(), 'red')
    try:
        import matplotlib  # noqa: F401
        have_mpl = True
    except Exception:
        have_mpl = False

    if have_mpl:
        assert isinstance(result, io.BytesIO)
        head = result.getvalue()[:8]
        assert head.startswith(b'\x89PNG')
    else:
        assert result is None


def test_render_economy_chart_handles_missing_data():
    assert render_economy_chart(build_match(), None) is None
    assert render_economy_chart({'rounds': []}, 'red') is None
