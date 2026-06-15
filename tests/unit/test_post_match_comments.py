import pytest
from unittest.mock import MagicMock
import discord

from match_tracker import MatchTracker


def _tracker():
    return MatchTracker(MagicMock(spec=discord.Client))


def test_loss_comment_first_game_is_a_warmup():
    """Game 1 losses get a warm-up excuse."""
    name, value = _tracker()._build_loss_comment(my_rounds=9, opponent_rounds=13, game_number=1)
    assert name == "😅 Tough Loss"
    # Scoreline lives in the embed headline now, not the flavor comment.
    assert "9-13" not in value
    assert any(word in value.lower() for word in ("warm", "rust", "warming"))


def test_loss_comment_many_games_drops_warmup_and_wants_to_keep_going():
    """After several back-to-back games it's no longer a warm-up - we don't
    end on a loss."""
    name, value = _tracker()._build_loss_comment(my_rounds=10, opponent_rounds=13, game_number=4)
    assert "warm" not in value.lower()
    # references the streak and refuses to stop on a loss
    assert "4" in value


def test_loss_comment_close_game_acknowledges_heartbreak():
    name, value = _tracker()._build_loss_comment(my_rounds=12, opponent_rounds=13, game_number=2)
    assert name == "😅 Tough Loss"
    assert value  # close-game flavor present
    assert "12-13" not in value


def test_win_comment_after_streak_suggests_ending_on_a_high():
    name, value = _tracker()._build_win_comment(my_rounds=13, opponent_rounds=7, game_number=3)
    assert name == "🏆 GG"
    assert "13-7" not in value
    assert "end" in value.lower() or "high note" in value.lower() or "log off" in value.lower()


def test_win_comment_single_game_no_end_it_nudge():
    name, value = _tracker()._build_win_comment(my_rounds=13, opponent_rounds=5, game_number=1)
    assert name == "🏆 GG"
    # only a single flavor line, no scoreline and no "end on that one" nudge
    assert "13-5" not in value
    assert "end" not in value.lower()


@pytest.mark.asyncio
async def test_recap_shows_result_once_in_headline(discord_member_factory):
    """The scoreline and win/loss state appear once (in the headline), not
    duplicated across a team-result field, the squad header, and the comment."""
    from unittest.mock import patch, AsyncMock

    tracker = _tracker()
    match = {
        'metadata': {'map': 'Ascent', 'rounds_played': 21, 'game_length': 1800,
                     'game_start': '2024-01-01T00:00:00Z', 'matchid': 'abc123'},
        'teams': {'red': {'has_won': True, 'rounds_won': 13},
                  'blue': {'has_won': False, 'rounds_won': 8}},
        'players': {'all_players': [
            {'puuid': 'p1', 'name': 'Tracked', 'tag': 'NA1', 'team': 'Red',
             'stats': {'kills': 20, 'deaths': 10, 'assists': 5}},
        ]},
    }
    member = discord_member_factory(user_id=1, name='TrackedName')
    discord_members = [{'member': member, 'account': {'puuid': 'p1'},
                        'player_data': match['players']['all_players'][0]}]

    with patch('match_tracker.format_time_ago', return_value='just now'), \
         patch.object(tracker, '_calculate_fun_match_stats',
                      return_value={'highlights': [], 'top_performers': {}, 'funny_stats': {}}), \
         patch.object(tracker, '_get_ranked_up_member_ids', AsyncMock(return_value=set())):
        embed = await tracker._create_match_embed(match, discord_members)

    # Headline carries the outcome + scoreline once.
    assert 'VICTORY' in embed.description
    assert '13 – 8' in embed.description
    assert embed.color.value == 0x3ba55d

    # No separate per-team "Match Result" field when the squad's side is known.
    assert not any('Match Result' in f.name for f in embed.fields)

    # Squad header no longer restates WON/LOST.
    squad_field = next(f for f in embed.fields if 'Squad' in f.name)
    assert 'WON' not in squad_field.name and 'LOST' not in squad_field.name


@pytest.mark.asyncio
async def test_acs_is_per_round_average_not_match_total(discord_member_factory):
    """ACS in highlights should be score/rounds, not the raw match total."""
    tracker = _tracker()

    # 24 rounds, 6000 total combat score => 250 ACS (not 6000)
    rounds = [{'player_stats': [{'player_puuid': 'p1', 'kill_events': []}]} for _ in range(24)]
    match_data = {
        'metadata': {'rounds_played': 24},
        'rounds': rounds,
        'players': {
            'all_players': [
                {'puuid': 'p1', 'stats': {'kills': 20, 'deaths': 10, 'assists': 5,
                                          'headshots': 0, 'bodyshots': 0, 'legshots': 0,
                                          'score': 6000},
                 'damage_made': 0, 'damage_received': 0, 'character': 'Jett'},
                {'puuid': 'p2', 'stats': {'kills': 5, 'deaths': 18, 'assists': 2,
                                          'headshots': 0, 'bodyshots': 0, 'legshots': 0,
                                          'score': 2400},
                 'damage_made': 0, 'damage_received': 0, 'character': 'Sage'},
            ]
        }
    }
    members = [
        {'member': discord_member_factory(user_id=1, name='P1'),
         'account': {'puuid': 'p1'}, 'player_data': match_data['players']['all_players'][0]},
        {'member': discord_member_factory(user_id=2, name='P2'),
         'account': {'puuid': 'p2'}, 'player_data': match_data['players']['all_players'][1]},
    ]

    stats = tracker._calculate_fun_match_stats(match_data, members)
    highlights = '\n'.join(stats['highlights'])

    assert '250 ACS' in highlights
    assert '6000 ACS' not in highlights
