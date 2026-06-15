"""Tests for the post-match recap rendering helpers."""
import discord
import pytest

import match_stats_display as msd


def _player(name, tag, team, k, d, a, score, dmg, hs=30, bs=40, ls=5):
    return {
        'puuid': f'{name}-id', 'name': name, 'tag': tag, 'team': team,
        'character': 'Jett', 'damage_made': dmg,
        'stats': {'kills': k, 'deaths': d, 'assists': a, 'score': score,
                  'headshots': hs, 'bodyshots': bs, 'legshots': ls},
    }


def _match():
    seq = (['Red', 'Red', 'Blue', 'Red', 'Blue', 'Blue', 'Red', 'Red',
            'Blue', 'Red', 'Blue', 'Red']            # first half (7-5)
           + ['Blue', 'Red', 'Blue', 'Red', 'Blue', 'Red'])  # 13-8 by round 18-ish
    rounds = [{'winning_team': w, 'player_stats': []} for w in seq]
    # Spike plants reveal the attacking side: Red plants in the first half,
    # Blue plants in the second half (so Red is ATK then DEF).
    rounds[0]['plant_events'] = {'planted_by': {'puuid': 'Shado-id'}}
    rounds[12]['plant_events'] = {'planted_by': {'puuid': 'Enemy1-id'}}
    return {
        'metadata': {'map': 'Ascent', 'rounds_played': len(seq), 'matchid': 'abc-123'},
        'teams': {'red': {'has_won': True, 'rounds_won': 13},
                  'blue': {'has_won': False, 'rounds_won': 8}},
        'rounds': rounds,
        'players': {'all_players': [
            _player('Shado', 'NA1', 'red', 24, 14, 7, 6200, 3900, hs=46),
            _player('Vyn', 'NA1', 'red', 18, 16, 10, 4100, 2900),
            _player('Enemy1', 'NA1', 'blue', 29, 14, 4, 8100, 5400, hs=10),
            _player('Enemy2', 'NA1', 'blue', 9, 23, 3, 2700, 1800),
        ]},
    }


# --- round flow -------------------------------------------------------------

def test_round_flow_numbers_rounds_and_colours_by_outcome():
    flow = msd.build_round_flow(_match(), 'red')
    # Rendered as a monospace ansi block with round numbers
    assert flow.startswith('```ansi')
    assert ' 1' in flow and '13' in flow
    # Round 1 (a Red win) is green; round 3 (a Blue win) is red, from red's view
    assert f'{msd._WIN} 1{msd._RESET}' in flow
    assert f'{msd._LOSS} 3{msd._RESET}' in flow
    # Wraps to a second row after the first half (more than 12 rounds)
    assert flow.count('\n') >= 3


def test_round_flow_labels_attack_and_defense_halves():
    flow = msd.build_round_flow(_match(), 'red')
    lines = [l for l in flow.splitlines() if '│' in l]
    # Red planted first half -> ATK; Blue planted second half -> Red on DEF
    assert 'ATK' in lines[0]
    assert 'DEF' in lines[1]


def test_round_flow_unknown_side_when_no_plants():
    match = _match()
    for rd in match['rounds']:
        rd.pop('plant_events', None)
    flow = msd.build_round_flow(match, 'red')
    # No plant data -> side can't be inferred, shown as '?'
    assert '?' in flow
    assert 'ATK' not in flow and 'DEF' not in flow


def test_round_flow_empty_without_rounds_or_team():
    assert msd.build_round_flow({'rounds': []}, 'red') == ""
    assert msd.build_round_flow(_match(), '') == ""


# --- per-player display stats ----------------------------------------------

def test_player_display_stats_falls_back_to_basic_scoreboard():
    """A player not present in the match's round data still gets ACS/ADR from
    the basic scoreboard (KAST/FK default to 0)."""
    match = {'metadata': {'rounds_played': 20}, 'rounds': [],
             'players': {'all_players': []}}
    pdata = {'stats': {'kills': 10, 'deaths': 5, 'assists': 3, 'score': 5000},
             'damage_made': 3000}
    s = msd.player_display_stats(match, pdata, puuid=None)
    assert s['kills'] == 10
    assert s['acs'] == 250   # 5000 / 20
    assert s['adr'] == 150   # 3000 / 20
    assert s['kast'] == 0 and s['fk'] == 0


# --- advanced scoreboard ----------------------------------------------------

def test_advanced_scoreboard_lists_all_players_in_ansi_block():
    out = msd.build_advanced_scoreboard(_match())
    assert '```ansi' in out
    for name in ('Shado', 'Vyn', 'Enemy1', 'Enemy2'):
        assert name in out
    # Winner listed first
    assert out.index('Red — 13') < out.index('Blue — 8')


def test_advanced_scoreboard_highlights_match_leader():
    out = msd.build_advanced_scoreboard(_match())
    # Enemy1 has the top ACS (8100/18=450) so it should carry the match-best
    # (bold yellow) ANSI code somewhere on its row.
    enemy_line = next(l for l in out.splitlines() if l.startswith('Enemy1'))
    assert msd._BEST_GAME in enemy_line


def test_advanced_scoreboard_empty_without_players():
    assert msd.build_advanced_scoreboard({'players': {'all_players': []}}) == ""


# --- views ------------------------------------------------------------------

def test_recap_view_none_without_match_id():
    assert msd.recap_view(None) is None
    assert msd.recap_view("") is None


def test_recap_view_encodes_match_id_in_button():
    view = msd.recap_view('match-xyz')
    assert view is not None
    button = view.children[0]
    assert button.custom_id == 'shooty:advstats:match-xyz'


def test_recap_view_from_embed_extracts_match_id():
    embed = discord.Embed(
        description="**Ascent**\n[📊 View on Tracker.gg]"
                    "(https://tracker.gg/valorant/match/dae1b62d-c3dd-4663)")
    view = msd.recap_view_from_embed(embed)
    assert view is not None
    assert view.children[0].custom_id == 'shooty:advstats:dae1b62d-c3dd-4663'


def test_recap_view_from_embed_none_without_link():
    embed = discord.Embed(description="**Ascent** • no link here")
    assert msd.recap_view_from_embed(embed) is None
