#!/usr/bin/env python3
"""
Unit tests for match stats calculation to ensure accuracy with tracker.gg
"""

import unittest
import json
import requests
import os
from calculate_match_stats import get_match_data, calculate_stats

class TestMatchStatsAccuracy(unittest.TestCase):
    """Test that our calculated stats match tracker.gg exactly"""
    
    @classmethod
    def setUpClass(cls):
        """Load match data once for all tests"""
        cls.match_id = "dae1b62d-c3dd-4663-9131-2771c7f66b5a"
        # API key is read from the environment. Set HENRIK_API_KEY in your
        # environment or `.env` file for tests that require it.
        cls.api_key = os.getenv("HENRIK_API_KEY")
        
        # Expected values from tracker.gg
        cls.expected_stats = {
            "swu#rango": {"kast": 68, "fk": 4, "fd": 3, "mk": 1},
            "ewu#KR2": {"kast": 58, "fk": 1, "fd": 5, "mk": 1},
            "Swoopn#tf2": {"kast": 63, "fk": 0, "fd": 1, "mk": 1},
            "TwentyJuan123#NA1": {"kast": 58, "fk": 1, "fd": 0, "mk": 1},
            "Kastostik#erm": {"kast": 47, "fk": 0, "fd": 4, "mk": 0},
            "Seleção#NA1": {"kast": 74, "fk": 1, "fd": 2, "mk": 3},
            "xpfc#NA1": {"kast": 74, "fk": 4, "fd": 0, "mk": 0},
            "Naginata#NA1": {"kast": 68, "fk": 4, "fd": 2, "mk": 0},
            "Lens#NA1": {"kast": 84, "fk": 4, "fd": 0, "mk": 0},
            "Foil#001": {"kast": 74, "fk": 0, "fd": 2, "mk": 0}
        }
        
        # Load match data
        try:
            cls.match_data = get_match_data(cls.match_id, cls.api_key)
            cls.calculated_stats = calculate_stats(cls.match_data)
        except Exception as e:
            cls.skipTest(f"Failed to load match data: {e}")
    
    def test_first_kills_exact_match(self):
        """Test that First Kills (FK) match tracker.gg exactly"""
        for player_name, expected in self.expected_stats.items():
            with self.subTest(player=player_name):
                # Find player in calculated stats
                player_stats = None
                for puuid, stats in self.calculated_stats.items():
                    if stats["name"] == player_name:
                        player_stats = stats
                        break
                
                self.assertIsNotNone(player_stats, f"Player {player_name} not found in calculated stats")
                self.assertEqual(
                    player_stats["first_kills"], 
                    expected["fk"],
                    f"FK mismatch for {player_name}: got {player_stats['first_kills']}, expected {expected['fk']}"
                )
    
    def test_first_deaths_exact_match(self):
        """Test that First Deaths (FD) match tracker.gg exactly"""
        for player_name, expected in self.expected_stats.items():
            with self.subTest(player=player_name):
                # Find player in calculated stats
                player_stats = None
                for puuid, stats in self.calculated_stats.items():
                    if stats["name"] == player_name:
                        player_stats = stats
                        break
                
                self.assertIsNotNone(player_stats, f"Player {player_name} not found in calculated stats")
                self.assertEqual(
                    player_stats["first_deaths"], 
                    expected["fd"],
                    f"FD mismatch for {player_name}: got {player_stats['first_deaths']}, expected {expected['fd']}"
                )
    
    def test_kast_exact_match(self):
        """Test that KAST percentages match tracker.gg exactly"""
        for player_name, expected in self.expected_stats.items():
            with self.subTest(player=player_name):
                # Find player in calculated stats
                player_stats = None
                for puuid, stats in self.calculated_stats.items():
                    if stats["name"] == player_name:
                        player_stats = stats
                        break
                
                self.assertIsNotNone(player_stats, f"Player {player_name} not found in calculated stats")
                self.assertEqual(
                    player_stats["kast"], 
                    expected["kast"],
                    f"KAST mismatch for {player_name}: got {player_stats['kast']}%, expected {expected['kast']}%"
                )
    
    def test_multi_kills_exact_match(self):
        """Test that Multi Kills (MK) match tracker.gg exactly"""
        for player_name, expected in self.expected_stats.items():
            with self.subTest(player=player_name):
                # Find player in calculated stats
                player_stats = None
                for puuid, stats in self.calculated_stats.items():
                    if stats["name"] == player_name:
                        player_stats = stats
                        break
                
                self.assertIsNotNone(player_stats, f"Player {player_name} not found in calculated stats")
                self.assertEqual(
                    player_stats["multi_kills"], 
                    expected["mk"],
                    f"MK mismatch for {player_name}: got {player_stats['multi_kills']}, expected {expected['mk']}"
                )
    
    def test_all_stats_comprehensive(self):
        """Comprehensive test of all stats for all players"""
        print("\n" + "="*80)
        print("COMPREHENSIVE STATS VALIDATION")
        print("="*80)
        print(f"{'Player':<20} {'Stat':<5} {'Calculated':<10} {'Expected':<10} {'Match':<8}")
        print("-" * 70)
        
        all_passed = True
        
        for player_name, expected in self.expected_stats.items():
            # Find player in calculated stats
            player_stats = None
            for puuid, stats in self.calculated_stats.items():
                if stats["name"] == player_name:
                    player_stats = stats
                    break
            
            if player_stats is None:
                print(f"{player_name:<20} {'N/A':<5} {'NOT FOUND':<10} {'N/A':<10} {'FAIL':<8}")
                all_passed = False
                continue
            
            # Check each stat
            stats_to_check = [
                ("KAST", "kast", "kast"),
                ("FK", "first_kills", "fk"),
                ("FD", "first_deaths", "fd"),
                ("MK", "multi_kills", "mk")
            ]
            
            for stat_name, calc_key, exp_key in stats_to_check:
                calculated = player_stats[calc_key]
                expected_val = expected[exp_key]
                match = "PASS" if calculated == expected_val else "FAIL"
                
                if match == "FAIL":
                    all_passed = False
                
                print(f"{player_name:<20} {stat_name:<5} {calculated:<10} {expected_val:<10} {match:<8}")
        
        print("-" * 70)
        print(f"OVERALL RESULT: {'PASS' if all_passed else 'FAIL'}")
        print("="*80)
        
        self.assertTrue(all_passed, "Not all stats match tracker.gg values")

if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)