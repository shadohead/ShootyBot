import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
from commands.valorant_commands import ValorantCommands

class TestValorantCommands(unittest.IsolatedAsyncioTestCase):
    """Test valorant commands"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.bot = MagicMock(spec=commands.Bot)
        self.bot.loop = MagicMock()
        self.bot.loop.create_task = MagicMock()
        
        with patch('commands.valorant_commands.BaseCommandCog.__init__', return_value=None):
            self.cog = ValorantCommands(self.bot)
            self.cog.logger = MagicMock()
            self.cog.match_tracker = MagicMock()
            # Mock the send_embed method
            self.cog.send_embed = AsyncMock()
            self.cog.send_error_embed = AsyncMock()
            self.cog.defer_if_slash = AsyncMock()
        
        # Mock context
        self.ctx = MagicMock(spec=commands.Context)
        self.ctx.author = MagicMock(spec=discord.Member)
        self.ctx.author.id = 123456789
        self.ctx.author.display_name = "TestUser"
        self.ctx.guild = MagicMock(spec=discord.Guild)
        self.ctx.guild.id = 987654321
        self.ctx.send = AsyncMock()
        self.ctx.defer = AsyncMock()
        self.ctx.interaction = None  # Simulating prefix command

    @patch('commands.valorant_commands.data_manager')
    @patch('commands.valorant_commands.valorant_client')
    async def test_shootystatsdetailed_success(self, mock_valorant_client, mock_data_manager):
        """Test shootystatsdetailed command with valid data"""
        # Mock account data
        mock_valorant_client.get_all_linked_accounts.return_value = [{
            'username': 'TestPlayer',
            'tag': 'NA1',
            'puuid': 'test-puuid-123'
        }]
        mock_valorant_client.get_linked_account.return_value = {
            'username': 'TestPlayer',
            'tag': 'NA1',
            'puuid': 'test-puuid-123'
        }
        
        # Mock match history
        mock_valorant_client.get_match_history = AsyncMock(return_value=[{
            'metadata': {'matchid': '123', 'map': 'Ascent'},
            'players': {'all_players': [{
                'puuid': 'test-puuid-123',
                'stats': {
                    'kills': 20,
                    'deaths': 10,
                    'assists': 5,
                    'score': 5000,
                    'bodyshots': 30,
                    'headshots': 10,
                    'damage_made': 3000,
                    'damage_received': 2000
                },
                'character': 'Jett',
                'team': 'Red'
            }]},
            'rounds': [{'winning_team': 'Red'}] * 13 + [{'winning_team': 'Blue'}] * 5,
            'teams': {'red': {'has_won': True}}
        }])
        
        # Mock stats calculation
        mock_valorant_client.calculate_player_stats.return_value = {
            'total_matches': 1,
            'acs': 250,
            'kd_ratio': 2.0,
            'kda_ratio': 2.5,
            'kast_percentage': 75.0,
            'performance_ratings': {
                'fragger': '💥 Fragger',
                'support': '🤝 Team Player',
                'accuracy': '🎯 Sharpshooter'
            },
            'adr': 166.7,
            'damage_delta_per_round': 55.6,
            'avg_damage_made': 3000,
            'headshot_percentage': 25.0,
            'win_rate': 100.0,
            'wins': 1,
            'losses': 0,
            'avg_kills': 20,
            'avg_deaths': 10,
            'avg_assists': 5,
            'avg_score': 5000,
            'agents_played': {'Jett': 1},
            'maps_played': {'Ascent': 1},
            'multikills': {'2k': 3, '3k': 1},
            'current_win_streak': 1,
            'current_loss_streak': 0,
            'max_win_streak': 1,
            'first_blood_rate': 50.0,
            'clutch_success_rate': 66.7,
            'recent_matches': [{
                'won': True,
                'kills': 20,
                'deaths': 10,
                'assists': 5,
                'damage_made': 3000,
                'rounds_played': 18,
                'agent': 'Jett'
            }]
        }
        
        # Execute command - call the callback directly
        await self.cog.detailed_valorant_stats.callback(self.cog, self.ctx)
        
        # Verify send_embed was called with correct structure
        self.cog.send_embed.assert_called_once()
        
        # Get the call arguments
        call_args = self.cog.send_embed.call_args
        fields = call_args.kwargs.get('fields', [])
        
        # Filter out None fields
        non_none_fields = [f for f in fields if f is not None]
        
        # Verify we have fields
        self.assertGreater(len(non_none_fields), 5)
        
        # Verify performance badges field was included
        badge_fields = [f for f in non_none_fields if f.get('name') == '🏆 Performance Badges']
        self.assertEqual(len(badge_fields), 1)
        self.assertIn('Fragger', badge_fields[0]['value'])
        
    @patch('commands.valorant_commands.data_manager')
    @patch('commands.valorant_commands.valorant_client')
    async def test_shootystatsdetailed_no_performance_ratings(self, mock_valorant_client, mock_data_manager):
        """Test shootystatsdetailed command without performance ratings"""
        # Mock account data
        mock_valorant_client.get_all_linked_accounts.return_value = [{
            'username': 'TestPlayer',
            'tag': 'NA1',
            'puuid': 'test-puuid-123'
        }]
        mock_valorant_client.get_linked_account.return_value = {
            'username': 'TestPlayer',
            'tag': 'NA1',
            'puuid': 'test-puuid-123'
        }
        
        # Mock match history
        mock_valorant_client.get_match_history = AsyncMock(return_value=[{'fake': 'match'}])
        
        # Mock stats calculation without performance_ratings
        mock_valorant_client.calculate_player_stats.return_value = {
            'total_matches': 1,
            'acs': 200,
            'kd_ratio': 1.5,
            'kda_ratio': 1.8,
            'kast_percentage': 70.0,
            # No performance_ratings key
            'adr': 150,
            'damage_delta_per_round': 25,
            'avg_damage_made': 2700,
            'headshot_percentage': 20.0,
            'win_rate': 50.0,
            'wins': 1,
            'losses': 1,
            'avg_kills': 15,
            'avg_deaths': 10,
            'avg_assists': 3,
            'avg_score': 4000,
            'agents_played': {'Sage': 2},
            'maps_played': {'Haven': 2},
            'multikills': {},
            'current_win_streak': 0,
            'current_loss_streak': 0,
            'max_win_streak': 1,
            'first_blood_rate': 25.0,
            'clutch_success_rate': 50.0
        }
        
        # Execute command - should not error even without performance_ratings
        await self.cog.detailed_valorant_stats.callback(self.cog, self.ctx)
        
        # Verify command completed without error
        self.assertTrue(True)

    @patch('valorant_client.database_manager.remove_valorant_account')
    @patch('valorant_client.data_manager')
    async def test_unlink_account_removes_database_rows(self, mock_data_manager, mock_remove_account):
        """Unlinking should remove all Valorant accounts from the database"""

        # Mock user with two linked accounts
        mock_user = MagicMock()
        mock_user.get_all_accounts.return_value = [
            {'username': 'Player1', 'tag': 'NA1'},
            {'username': 'Player2', 'tag': 'EU1'}
        ]
        mock_data_manager.get_user.return_value = mock_user

        from valorant_client import ValorantClient
        client = ValorantClient()

        result = await client.unlink_account(1111)

        self.assertTrue(result)
        self.assertEqual(mock_remove_account.call_count, 2)
        mock_remove_account.assert_any_call(1111, 'Player1', 'NA1')
        mock_remove_account.assert_any_call(1111, 'Player2', 'EU1')
        mock_data_manager.save_user.assert_called_once_with(1111)

    @patch('commands.valorant_commands.valorant_client')
    async def test_shootyrank_success(self, mock_valorant_client):
        """shootyrank should display the player's current rank and RR."""
        mock_valorant_client.get_all_linked_accounts.return_value = [
            {'username': 'TestPlayer', 'tag': 'NA1', 'puuid': 'puuid-1'}
        ]
        mock_valorant_client.get_linked_account.return_value = {
            'username': 'TestPlayer', 'tag': 'NA1', 'puuid': 'puuid-1'
        }
        mock_valorant_client.get_mmr = AsyncMock(return_value={
            'tier': 'Diamond 1', 'rr': 45, 'rr_change': 18, 'elo': 1845,
            'peak': 'Diamond 2', 'emoji': '💎',
        })

        await self.cog.valorant_rank.callback(self.cog, self.ctx)

        self.cog.send_embed.assert_awaited()
        # Description should mention rank, RR and the positive RR change
        args, kwargs = self.cog.send_embed.call_args
        body = " ".join(str(a) for a in args) + " ".join(f"{v}" for v in kwargs.values())
        self.assertIn('Diamond 1', body)
        self.assertIn('+18', body)

    @patch('commands.valorant_commands.valorant_client')
    async def test_shootyrank_no_accounts(self, mock_valorant_client):
        """shootyrank should error gracefully when no accounts are linked."""
        mock_valorant_client.get_all_linked_accounts.return_value = []

        await self.cog.valorant_rank.callback(self.cog, self.ctx)

        self.cog.send_error_embed.assert_awaited()

    @patch('commands.valorant_commands.valorant_client')
    async def test_shootycompare_picks_winner(self, mock_valorant_client):
        """shootycompare should fetch both players and crown the stronger one."""
        player1 = MagicMock(spec=discord.Member)
        player1.id = 1
        player1.display_name = "Alice"
        # player2 defaults to ctx.author (id 123456789)

        accounts = {
            1: {'username': 'Alice', 'tag': 'NA1', 'puuid': 'pa'},
            123456789: {'username': 'TestUser', 'tag': 'NA1', 'puuid': 'pb'},
        }
        stats = {
            'pa': {'total_matches': 20, 'acs': 280, 'kd_ratio': 1.4, 'kda_ratio': 1.8,
                   'kast_percentage': 75, 'adr': 160, 'headshot_percentage': 28,
                   'win_rate': 60, 'first_blood_rate': 12, 'clutch_success_rate': 55},
            'pb': {'total_matches': 18, 'acs': 200, 'kd_ratio': 0.9, 'kda_ratio': 1.2,
                   'kast_percentage': 65, 'adr': 130, 'headshot_percentage': 20,
                   'win_rate': 45, 'first_blood_rate': 8, 'clutch_success_rate': 40},
        }
        mock_valorant_client.get_linked_account.side_effect = lambda uid: accounts.get(uid)
        mock_valorant_client.get_all_linked_accounts.side_effect = lambda uid: [accounts[uid]] if uid in accounts else []
        mock_valorant_client.get_match_history = AsyncMock(
            side_effect=lambda u, t, **kw: [{'puuid': 'pa' if u == 'Alice' else 'pb'}]
        )
        mock_valorant_client.calculate_player_stats.side_effect = (
            lambda matches, puuid, **kw: stats[matches[0]['puuid']]
        )
        mock_valorant_client.get_mmr = AsyncMock(return_value=None)

        await self.cog.compare_players.callback(self.cog, self.ctx, player1)

        self.ctx.send.assert_awaited()
        embed = self.ctx.send.call_args.kwargs['embed']
        verdict = next(f for f in embed.fields if f.name == 'Verdict')
        self.assertIn('Alice', verdict.value)

    def _make_member(self, member_id, name, is_bot=False):
        member = MagicMock(spec=discord.Member)
        member.id = member_id
        member.display_name = name
        member.bot = is_bot
        return member

    @patch('commands.valorant_commands.valorant_client')
    async def test_gather_member_stats_skips_bots_and_unlinked(self, mock_valorant_client):
        """The shared helper fetches only linked, non-bot members."""
        alice = self._make_member(1, 'Alice')
        bob = self._make_member(2, 'Bob')
        a_bot = self._make_member(3, 'BotUser', is_bot=True)
        unlinked = self._make_member(4, 'NoAccount')
        guild = MagicMock(spec=discord.Guild)
        guild.members = [alice, bob, a_bot, unlinked]

        accounts = {
            1: {'username': 'Alice', 'tag': 'NA1', 'puuid': 'pa'},
            2: {'username': 'Bob', 'tag': 'NA1', 'puuid': 'pb'},
        }
        mock_valorant_client.get_linked_account.side_effect = lambda uid: accounts.get(uid)
        mock_valorant_client.get_match_history = AsyncMock(
            side_effect=lambda u, t, **kw: [{'puuid': accounts[1]['puuid'] if u == 'Alice' else accounts[2]['puuid']}]
        )
        mock_valorant_client.calculate_player_stats.side_effect = (
            lambda matches, puuid, **kw: {'total_matches': 5, 'puuid': matches[0]['puuid']}
        )

        results = await self.cog._gather_member_stats(guild)

        # Only Alice and Bob qualify (bot and unlinked excluded)
        self.assertEqual({r['member'].display_name for r in results}, {'Alice', 'Bob'})
        self.assertEqual(mock_valorant_client.get_match_history.await_count, 2)

    @patch('commands.valorant_commands.valorant_client')
    async def test_weapon_leaderboard_success(self, mock_valorant_client):
        """Weapon leaderboard ranks members by kills with the chosen weapon."""
        alice = self._make_member(1, 'Alice')
        bob = self._make_member(2, 'Bob')
        a_bot = self._make_member(3, 'BotUser', is_bot=True)
        self.ctx.guild.members = [alice, bob, a_bot]

        accounts = {
            1: {'username': 'Alice', 'tag': 'NA1', 'puuid': 'pa'},
            2: {'username': 'Bob', 'tag': 'NA1', 'puuid': 'pb'},
        }
        weapon_stats = {
            'pa': {'total_matches': 5, 'weapon_kills': {'Vandal': 40, 'Phantom': 5}},
            'pb': {'total_matches': 5, 'weapon_kills': {'Vandal': 60, 'Sheriff': 3}},
        }
        mock_valorant_client.get_linked_account.side_effect = lambda uid: accounts.get(uid)
        mock_valorant_client.get_match_history = AsyncMock(
            side_effect=lambda u, t, **kw: [{'puuid': accounts[1]['puuid'] if u == 'Alice' else accounts[2]['puuid']}]
        )
        mock_valorant_client.calculate_player_stats.side_effect = (
            lambda matches, puuid, **kw: weapon_stats[matches[0]['puuid']]
        )

        await self.cog.weapon_leaderboard.callback(self.cog, self.ctx, weapon='vandal')

        self.ctx.send.assert_awaited()
        embed = self.ctx.send.call_args.kwargs['embed']
        self.assertIn('Vandal', embed.title)
        top = next(f for f in embed.fields if f.name == '🎯 Top Fraggers')
        # Bob (60) should rank above Alice (40)
        self.assertLess(top.value.index('Bob'), top.value.index('Alice'))
        self.assertIn('60 kills', top.value)

    @patch('commands.valorant_commands.valorant_client')
    async def test_weapon_leaderboard_unknown_weapon(self, mock_valorant_client):
        """An unrecognized weapon returns an error without querying stats."""
        self.ctx.guild.members = []
        await self.cog.weapon_leaderboard.callback(self.cog, self.ctx, weapon='banana')

        self.cog.send_error_embed.assert_awaited_once()
        mock_valorant_client.get_match_history.assert_not_called()

    @patch('commands.valorant_commands.valorant_client')
    async def test_weapon_leaderboard_no_kills(self, mock_valorant_client):
        """When no one has kills with the weapon, a friendly message is shown."""
        alice = self._make_member(1, 'Alice')
        self.ctx.guild.members = [alice]
        mock_valorant_client.get_linked_account.side_effect = (
            lambda uid: {'username': 'Alice', 'tag': 'NA1', 'puuid': 'pa'} if uid == 1 else None
        )
        mock_valorant_client.get_match_history = AsyncMock(return_value=[{'puuid': 'pa'}])
        mock_valorant_client.calculate_player_stats.return_value = {
            'total_matches': 5, 'weapon_kills': {'Phantom': 10}
        }

        await self.cog.weapon_leaderboard.callback(self.cog, self.ctx, weapon='Operator')

        self.cog.send_embed.assert_awaited()
        self.ctx.send.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()