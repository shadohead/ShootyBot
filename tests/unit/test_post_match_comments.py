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
    assert "9-13" in value
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
    assert "12-13" in value


def test_win_comment_after_streak_suggests_ending_on_a_high():
    name, value = _tracker()._build_win_comment(my_rounds=13, opponent_rounds=7, game_number=3)
    assert name == "🏆 GG"
    assert "13-7" in value
    assert "end" in value.lower() or "high note" in value.lower() or "log off" in value.lower()


def test_win_comment_single_game_no_end_it_nudge():
    name, value = _tracker()._build_win_comment(my_rounds=13, opponent_rounds=5, game_number=1)
    assert name == "🏆 GG"
    # only the score line + one flavor line, no "end on that one" nudge
    assert "13-5" in value


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
